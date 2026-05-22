from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from json import dumps
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations.incidents import (
    PostgresRecommendationProviderIncidentRepository,
    RecommendationProviderIncidentEventRecord,
    RecommendationProviderIncidentQueryOptions,
)
from nutmeg.recommendations.lifecycle_replay import (
    PersistedRecommendationLifecycleReplayQueryOptions,
    PersistedRecommendationLifecycleReplayResult,
    PersistedRecommendationRunSnapshot,
    PostgresPersistedRecommendationLifecycleReplayRepository,
    build_persisted_recommendation_lifecycle_replay,
    build_prematch_backtest_checkpoints_from_persisted_snapshots,
)
from nutmeg.recommendations.models import RecommendationMode

INSERT_RECOMMENDATION_PREMATCH_CHANGE_REPORT_QUERY = """
INSERT INTO recommendation_prematch_change_reports (
  report_key,
  window_start_utc,
  window_end_utc,
  pass_type,
  mode,
  strategy,
  stage_count,
  changed_stage_count,
  incident_count,
  critical_incident_count,
  locked_preservation_stage_count,
  report_json,
  source
) VALUES (
  %(report_key)s,
  %(window_start_utc)s,
  %(window_end_utc)s,
  %(pass_type)s,
  %(mode)s,
  %(strategy)s,
  %(stage_count)s,
  %(changed_stage_count)s,
  %(incident_count)s,
  %(critical_incident_count)s,
  %(locked_preservation_stage_count)s,
  %(report_json)s::jsonb,
  %(source)s
)
ON CONFLICT (report_key) DO UPDATE
SET
  stage_count = EXCLUDED.stage_count,
  changed_stage_count = EXCLUDED.changed_stage_count,
  incident_count = EXCLUDED.incident_count,
  critical_incident_count = EXCLUDED.critical_incident_count,
  locked_preservation_stage_count = EXCLUDED.locked_preservation_stage_count,
  report_json = EXCLUDED.report_json,
  source = EXCLUDED.source,
  updated_at = now()
RETURNING recommendation_prematch_change_report_id, created_at, updated_at
"""


class RecommendationPrematchChangeReportDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read recommendation report source rows."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Write recommendation report rows."""


class RecommendationPrematchChangeReportOptions(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = Field(default=None, min_length=1)
    mode: RecommendationMode | None = None
    strategy: str | None = Field(default=None, min_length=1)
    include_provider_incidents: bool = True
    dry_run: bool = True
    limit: int = Field(default=200, ge=1, le=2_000)

    @property
    def normalized_window_start_utc(self) -> datetime:
        return _aware_utc(self.window_start_utc)

    @property
    def normalized_window_end_utc(self) -> datetime:
        return _aware_utc(self.window_end_utc)


class RecommendationPrematchChangeReport(BaseModel):
    report_key: str
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = None
    mode: RecommendationMode | None = None
    strategy: str | None = None
    replay: PersistedRecommendationLifecycleReplayResult
    provider_incidents: list[RecommendationProviderIncidentEventRecord] = Field(
        default_factory=list
    )
    checkpoint_count: int = Field(ge=0)
    summary_json: dict[str, object] = Field(default_factory=dict)


class StoredRecommendationPrematchChangeReport(BaseModel):
    recommendation_prematch_change_report_id: int = Field(gt=0)
    report_key: str
    created_at: datetime
    updated_at: datetime


class RecommendationPrematchChangeReportRunResult(BaseModel):
    dry_run: bool
    report: RecommendationPrematchChangeReport
    stored_report: StoredRecommendationPrematchChangeReport | None = None
    warnings: list[str] = Field(default_factory=list)


class PostgresRecommendationPrematchChangeReportRepository:
    def __init__(self, database: RecommendationPrematchChangeReportDatabaseExecutor) -> None:
        self.database = database

    def save_report(
        self,
        report: RecommendationPrematchChangeReport,
        *,
        source: str = "recommendation_prematch_change_report_v3_1",
    ) -> StoredRecommendationPrematchChangeReport:
        summary = report.summary_json
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_PREMATCH_CHANGE_REPORT_QUERY,
                {
                    "report_key": report.report_key,
                    "window_start_utc": _aware_utc(report.window_start_utc),
                    "window_end_utc": _aware_utc(report.window_end_utc),
                    "pass_type": report.pass_type,
                    "mode": report.mode,
                    "strategy": report.strategy,
                    "stage_count": _summary_int(summary, "stage_count"),
                    "changed_stage_count": _summary_int(summary, "changed_stage_count"),
                    "incident_count": _summary_int(summary, "incident_count"),
                    "critical_incident_count": _summary_int(
                        summary,
                        "critical_incident_count",
                    ),
                    "locked_preservation_stage_count": _summary_int(
                        summary,
                        "locked_preservation_stage_count",
                    ),
                    "report_json": _json(report.model_dump(mode="json")),
                    "source": source,
                },
            )
        )
        return StoredRecommendationPrematchChangeReport(
            recommendation_prematch_change_report_id=_int(
                row["recommendation_prematch_change_report_id"]
            ),
            report_key=report.report_key,
            created_at=_datetime(row["created_at"]),
            updated_at=_datetime(row["updated_at"]),
        )


def build_recommendation_prematch_change_report(
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
    provider_incidents: Sequence[RecommendationProviderIncidentEventRecord],
    *,
    options: RecommendationPrematchChangeReportOptions,
) -> RecommendationPrematchChangeReport:
    replay = build_persisted_recommendation_lifecycle_replay(snapshots)
    checkpoints = build_prematch_backtest_checkpoints_from_persisted_snapshots(
        snapshots,
        provider_incidents=provider_incidents
        if options.include_provider_incidents
        else (),
    )
    summary = _report_summary(
        replay,
        checkpoints_count=len(checkpoints),
        provider_incidents=provider_incidents,
    )
    report_key = _report_key(options, summary=summary)
    return RecommendationPrematchChangeReport(
        report_key=report_key,
        window_start_utc=options.normalized_window_start_utc,
        window_end_utc=options.normalized_window_end_utc,
        pass_type=options.pass_type,
        mode=options.mode,
        strategy=options.strategy,
        replay=replay,
        provider_incidents=list(provider_incidents),
        checkpoint_count=len(checkpoints),
        summary_json=summary,
    )


def run_recommendation_prematch_change_report(
    database: RecommendationPrematchChangeReportDatabaseExecutor,
    *,
    options: RecommendationPrematchChangeReportOptions,
    replay_repository: PostgresPersistedRecommendationLifecycleReplayRepository | None = None,
    incident_repository: PostgresRecommendationProviderIncidentRepository | None = None,
    report_repository: PostgresRecommendationPrematchChangeReportRepository | None = None,
) -> RecommendationPrematchChangeReportRunResult:
    replay_reader = replay_repository or PostgresPersistedRecommendationLifecycleReplayRepository(
        database
    )
    snapshots = replay_reader.list_snapshots(
        options=PersistedRecommendationLifecycleReplayQueryOptions(
            window_start_utc=options.normalized_window_start_utc,
            window_end_utc=options.normalized_window_end_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            limit=options.limit,
        )
    )
    provider_incidents: list[RecommendationProviderIncidentEventRecord] = []
    if options.include_provider_incidents:
        incident_reader = incident_repository or PostgresRecommendationProviderIncidentRepository(
            database
        )
        provider_incidents = incident_reader.list_events(
            options=_provider_incident_query_options(options, snapshots)
        )
    report = build_recommendation_prematch_change_report(
        snapshots,
        provider_incidents,
        options=options,
    )
    stored_report = None
    if not options.dry_run:
        writer = report_repository or PostgresRecommendationPrematchChangeReportRepository(
            database
        )
        stored_report = writer.save_report(report)
    return RecommendationPrematchChangeReportRunResult(
        dry_run=options.dry_run,
        report=report,
        stored_report=stored_report,
    )


def _provider_incident_query_options(
    options: RecommendationPrematchChangeReportOptions,
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
) -> RecommendationProviderIncidentQueryOptions:
    return RecommendationProviderIncidentQueryOptions(
        window_start_utc=options.normalized_window_start_utc,
        window_end_utc=options.normalized_window_end_utc,
        only_affecting_recommendations=True,
        fixture_ids=tuple(_snapshot_fixture_ids(snapshots)),
        limit=min(5_000, max(100, options.limit * 10)),
    )


def _report_summary(
    replay: PersistedRecommendationLifecycleReplayResult,
    *,
    checkpoints_count: int,
    provider_incidents: Sequence[RecommendationProviderIncidentEventRecord],
) -> dict[str, object]:
    replay_summary = replay.summary_json
    return {
        "stage_count": _summary_int(replay_summary, "stage_count"),
        "selected_stage_count": _summary_int(replay_summary, "selected_stage_count"),
        "changed_stage_count": _summary_int(replay_summary, "changed_stage_count"),
        "incident_stage_count": _summary_int(replay_summary, "incident_stage_count"),
        "locked_preservation_stage_count": _summary_int(
            replay_summary,
            "locked_preservation_stage_count",
        ),
        "started_locked_stage_count": _summary_int(
            replay_summary,
            "started_locked_stage_count",
        ),
        "continuation_stage_count": _summary_int(
            replay_summary,
            "continuation_stage_count",
        ),
        "checkpoint_count": checkpoints_count,
        "incident_count": len(provider_incidents),
        "critical_incident_count": sum(
            1 for incident in provider_incidents if incident.severity == "critical"
        ),
        "provider_incident_event_keys": [
            incident.provider_incident_key for incident in provider_incidents
        ],
        "final_run_key": replay_summary.get("final_run_key"),
        "final_selected_fixture_ids": replay_summary.get("final_selected_fixture_ids", []),
        "final_continuation_fixture_ids": replay_summary.get(
            "final_continuation_fixture_ids",
            [],
        ),
        "final_remaining_open_leg_count": _summary_int(
            replay_summary,
            "final_remaining_open_leg_count",
        ),
        "calculation_basis": "recommendation_prematch_change_report_summary",
    }


def _snapshot_fixture_ids(
    snapshots: Sequence[PersistedRecommendationRunSnapshot],
) -> list[str]:
    fixture_ids: list[str] = []
    for snapshot in snapshots:
        fixture_ids.extend(snapshot.selected_fixture_ids)
        fixture_ids.extend(snapshot.locked_fixture_ids)
        fixture_ids.extend(
            candidate.fixture_id for candidate in snapshot.selected_candidates
        )
        fixture_ids.extend(
            candidate.fixture_id for candidate in snapshot.candidate_pool_candidates
        )
    return _dedupe_strings(fixture_ids)


def _report_key(
    options: RecommendationPrematchChangeReportOptions,
    *,
    summary: dict[str, object],
) -> str:
    payload = "|".join(
        [
            options.normalized_window_start_utc.isoformat(),
            options.normalized_window_end_utc.isoformat(),
            options.pass_type or "all_pass_types",
            options.mode or "all_modes",
            options.strategy or "all_strategies",
            str(summary.get("stage_count", 0)),
            str(summary.get("changed_stage_count", 0)),
            str(summary.get("incident_count", 0)),
            str(summary.get("continuation_stage_count", 0)),
            str(summary.get("final_remaining_open_leg_count", 0)),
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"prematch_change:{digest}"


def _summary_int(summary: dict[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | Decimal | str):
        return int(value)
    return 0


def _json(value: object) -> str:
    return dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise RuntimeError("database statement did not return a row")
    return row


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in result:
            continue
        result.append(text)
    return result


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")
