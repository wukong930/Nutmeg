from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from json import dumps, loads
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy
from nutmeg.recommendations.prematch_report import (
    RecommendationPrematchChangeReportOptions,
    RecommendationPrematchChangeReportRunResult,
    run_recommendation_prematch_change_report,
)
from nutmeg.recommendations.provider_incident_mapping import (
    RecommendationProviderIncidentMappingOptions,
    RecommendationProviderIncidentMappingResult,
    run_recommendation_provider_incident_mapping,
)
from nutmeg.recommendations.recompute_trigger import (
    RecommendationRecomputeTriggerOptions,
    RecommendationRecomputeTriggerRunResult,
    run_recommendation_recompute_trigger,
)

type RecommendationPrematchPipelineRunStatus = Literal[
    "running",
    "completed",
    "failed",
]

INSERT_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY = """
INSERT INTO recommendation_prematch_pipeline_runs (
  run_key,
  status,
  dry_run,
  as_of_time_utc,
  window_start_utc,
  window_end_utc,
  pass_type,
  mode,
  strategy,
  requested_by,
  result_json,
  source
) VALUES (
  %(run_key)s,
  'running',
  %(dry_run)s,
  %(as_of_time_utc)s,
  %(window_start_utc)s,
  %(window_end_utc)s,
  %(pass_type)s,
  %(mode)s,
  %(strategy)s,
  %(requested_by)s,
  '{}'::jsonb,
  %(source)s
)
RETURNING
  recommendation_prematch_pipeline_run_id,
  run_key,
  status,
  dry_run,
  as_of_time_utc,
  window_start_utc,
  window_end_utc,
  pass_type,
  mode,
  strategy,
  requested_by,
  mapped_incident_count,
  stored_incident_count,
  checked_run_count,
  triggered_run_count,
  skipped_run_count,
  generated_recommendation_run_ids_json,
  prematch_report_key,
  warnings_json,
  error_message,
  source,
  started_at,
  completed_at,
  duration_ms,
  created_at,
  updated_at
"""

COMPLETE_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY = """
UPDATE recommendation_prematch_pipeline_runs
SET
  status = 'completed',
  mapped_incident_count = %(mapped_incident_count)s,
  stored_incident_count = %(stored_incident_count)s,
  checked_run_count = %(checked_run_count)s,
  triggered_run_count = %(triggered_run_count)s,
  skipped_run_count = %(skipped_run_count)s,
  generated_recommendation_run_ids_json = %(generated_recommendation_run_ids_json)s::jsonb,
  prematch_report_key = %(prematch_report_key)s,
  warnings_json = %(warnings_json)s::jsonb,
  error_message = NULL,
  result_json = %(result_json)s::jsonb,
  completed_at = now(),
  duration_ms = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) * 1000))::INT,
  updated_at = now()
WHERE recommendation_prematch_pipeline_run_id = %(recommendation_prematch_pipeline_run_id)s
RETURNING
  recommendation_prematch_pipeline_run_id,
  run_key,
  status,
  dry_run,
  as_of_time_utc,
  window_start_utc,
  window_end_utc,
  pass_type,
  mode,
  strategy,
  requested_by,
  mapped_incident_count,
  stored_incident_count,
  checked_run_count,
  triggered_run_count,
  skipped_run_count,
  generated_recommendation_run_ids_json,
  prematch_report_key,
  warnings_json,
  error_message,
  source,
  started_at,
  completed_at,
  duration_ms,
  created_at,
  updated_at
"""

FAIL_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY = """
UPDATE recommendation_prematch_pipeline_runs
SET
  status = 'failed',
  warnings_json = %(warnings_json)s::jsonb,
  error_message = %(error_message)s,
  completed_at = now(),
  duration_ms = GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (now() - started_at)) * 1000))::INT,
  updated_at = now()
WHERE recommendation_prematch_pipeline_run_id = %(recommendation_prematch_pipeline_run_id)s
RETURNING
  recommendation_prematch_pipeline_run_id,
  run_key,
  status,
  dry_run,
  as_of_time_utc,
  window_start_utc,
  window_end_utc,
  pass_type,
  mode,
  strategy,
  requested_by,
  mapped_incident_count,
  stored_incident_count,
  checked_run_count,
  triggered_run_count,
  skipped_run_count,
  generated_recommendation_run_ids_json,
  prematch_report_key,
  warnings_json,
  error_message,
  source,
  started_at,
  completed_at,
  duration_ms,
  created_at,
  updated_at
"""


class RecommendationPrematchPipelineDatabase(Protocol):
    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute a statement with RETURNING and return one row."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Execute a query and return mapping rows."""


class RecommendationPrematchPipelineOptions(BaseModel):
    as_of_time_utc: datetime | None = None
    lookback_hours: int = Field(default=24, ge=1, le=720)
    pass_type: str | None = Field(default=None, min_length=1)
    mode: RecommendationMode | None = None
    strategy: RecommendationStrategy | None = None
    provider_name: str | None = Field(default=None, min_length=1)
    canonical_fixture_id: str | None = Field(default=None, min_length=1)
    run_provider_incident_mapping: bool = True
    run_recompute_trigger: bool = True
    run_prematch_change_report: bool = True
    include_candidate_pool_incidents: bool = True
    include_provider_incidents_in_report: bool = True
    preserve_locked_legs: bool = True
    trigger_locked_successors: bool = True
    dry_run: bool = True
    provider_observation_limit: int = Field(default=2_000, ge=1, le=5_000)
    source_run_limit: int = Field(default=100, ge=1, le=2_000)
    incident_limit: int = Field(default=1_000, ge=1, le=5_000)
    report_limit: int = Field(default=200, ge=1, le=2_000)
    critical_availability_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    odds_probability_shift_threshold: float = Field(default=0.12, ge=0.01, le=1.0)
    critical_odds_probability_shift_threshold: float = Field(
        default=0.25,
        ge=0.01,
        le=1.0,
    )

    @property
    def normalized_as_of_time_utc(self) -> datetime:
        return _aware_utc(self.as_of_time_utc or datetime.now(UTC))

    @property
    def window_start_utc(self) -> datetime:
        return self.normalized_as_of_time_utc - timedelta(hours=self.lookback_hours)


class RecommendationPrematchPipelineRunRecord(BaseModel):
    recommendation_prematch_pipeline_run_id: int = Field(gt=0)
    run_key: str
    status: RecommendationPrematchPipelineRunStatus
    dry_run: bool
    as_of_time_utc: datetime
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = None
    mode: RecommendationMode | None = None
    strategy: RecommendationStrategy | None = None
    requested_by: str | None = None
    mapped_incident_count: int = Field(default=0, ge=0)
    stored_incident_count: int = Field(default=0, ge=0)
    checked_run_count: int = Field(default=0, ge=0)
    triggered_run_count: int = Field(default=0, ge=0)
    skipped_run_count: int = Field(default=0, ge=0)
    generated_recommendation_run_ids: list[int] = Field(default_factory=list)
    prematch_report_key: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    source: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    created_at: datetime
    updated_at: datetime


class RecommendationPrematchPipelineRunResult(BaseModel):
    recommendation_prematch_pipeline_run_id: int | None = Field(default=None, gt=0)
    status: Literal["completed"] = "completed"
    dry_run: bool
    as_of_time_utc: datetime
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = None
    mode: RecommendationMode | None = None
    strategy: RecommendationStrategy | None = None
    requested_by: str | None = None
    provider_incident_mapping: RecommendationProviderIncidentMappingResult | None = None
    recompute_trigger: RecommendationRecomputeTriggerRunResult | None = None
    prematch_change_report: RecommendationPrematchChangeReportRunResult | None = None
    mapped_incident_count: int = Field(default=0, ge=0)
    stored_incident_count: int = Field(default=0, ge=0)
    checked_run_count: int = Field(default=0, ge=0)
    triggered_run_count: int = Field(default=0, ge=0)
    skipped_run_count: int = Field(default=0, ge=0)
    generated_recommendation_run_ids: list[int] = Field(default_factory=list)
    prematch_report_key: str | None = None
    warnings: list[str] = Field(default_factory=list)
    stored_run: RecommendationPrematchPipelineRunRecord | None = None


class RecommendationPrematchPipelineAuditRepository(Protocol):
    def start_run(
        self,
        *,
        options: RecommendationPrematchPipelineOptions,
        requested_by: str | None,
        source: str,
    ) -> RecommendationPrematchPipelineRunRecord: ...

    def complete_run(
        self,
        *,
        recommendation_prematch_pipeline_run_id: int,
        result: RecommendationPrematchPipelineRunResult,
    ) -> RecommendationPrematchPipelineRunRecord: ...

    def fail_run(
        self,
        *,
        recommendation_prematch_pipeline_run_id: int,
        error_message: str,
        warnings: Sequence[str],
    ) -> RecommendationPrematchPipelineRunRecord: ...


class RecommendationProviderIncidentMappingRunner(Protocol):
    def __call__(
        self,
        database: RecommendationPrematchPipelineDatabase,
        *,
        options: RecommendationProviderIncidentMappingOptions,
    ) -> RecommendationProviderIncidentMappingResult: ...


class RecommendationRecomputeTriggerRunner(Protocol):
    def __call__(
        self,
        database: RecommendationPrematchPipelineDatabase,
        *,
        options: RecommendationRecomputeTriggerOptions,
    ) -> RecommendationRecomputeTriggerRunResult: ...


class RecommendationPrematchChangeReportRunner(Protocol):
    def __call__(
        self,
        database: RecommendationPrematchPipelineDatabase,
        *,
        options: RecommendationPrematchChangeReportOptions,
    ) -> RecommendationPrematchChangeReportRunResult: ...


class PostgresRecommendationPrematchPipelineRunRepository:
    def __init__(self, database: RecommendationPrematchPipelineDatabase) -> None:
        self.database = database

    def start_run(
        self,
        *,
        options: RecommendationPrematchPipelineOptions,
        requested_by: str | None,
        source: str = "recommendation_prematch_pipeline_v3_1",
    ) -> RecommendationPrematchPipelineRunRecord:
        as_of_time = options.normalized_as_of_time_utc
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY,
                {
                    "run_key": _run_key(options, requested_by=requested_by),
                    "dry_run": options.dry_run,
                    "as_of_time_utc": as_of_time,
                    "window_start_utc": options.window_start_utc,
                    "window_end_utc": as_of_time,
                    "pass_type": options.pass_type,
                    "mode": options.mode,
                    "strategy": options.strategy,
                    "requested_by": requested_by,
                    "source": source,
                },
            )
        )
        return _record_from_row(row)

    def complete_run(
        self,
        *,
        recommendation_prematch_pipeline_run_id: int,
        result: RecommendationPrematchPipelineRunResult,
    ) -> RecommendationPrematchPipelineRunRecord:
        row = _required_row(
            self.database.fetch_one(
                COMPLETE_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY,
                {
                    "recommendation_prematch_pipeline_run_id": (
                        recommendation_prematch_pipeline_run_id
                    ),
                    "mapped_incident_count": result.mapped_incident_count,
                    "stored_incident_count": result.stored_incident_count,
                    "checked_run_count": result.checked_run_count,
                    "triggered_run_count": result.triggered_run_count,
                    "skipped_run_count": result.skipped_run_count,
                    "generated_recommendation_run_ids_json": _json(
                        result.generated_recommendation_run_ids
                    ),
                    "prematch_report_key": result.prematch_report_key,
                    "warnings_json": _json(result.warnings),
                    "result_json": _json(result.model_dump(mode="json")),
                },
            )
        )
        return _record_from_row(row)

    def fail_run(
        self,
        *,
        recommendation_prematch_pipeline_run_id: int,
        error_message: str,
        warnings: Sequence[str],
    ) -> RecommendationPrematchPipelineRunRecord:
        row = _required_row(
            self.database.fetch_one(
                FAIL_RECOMMENDATION_PREMATCH_PIPELINE_RUN_QUERY,
                {
                    "recommendation_prematch_pipeline_run_id": (
                        recommendation_prematch_pipeline_run_id
                    ),
                    "error_message": error_message[:500],
                    "warnings_json": _json(list(warnings)),
                },
            )
        )
        return _record_from_row(row)


def run_recommendation_prematch_pipeline(
    database: RecommendationPrematchPipelineDatabase,
    *,
    options: RecommendationPrematchPipelineOptions,
    requested_by: str | None = None,
    audit_repository: RecommendationPrematchPipelineAuditRepository | None = None,
    provider_incident_mapping_runner: (
        RecommendationProviderIncidentMappingRunner | None
    ) = None,
    recompute_trigger_runner: RecommendationRecomputeTriggerRunner | None = None,
    prematch_change_report_runner: (
        RecommendationPrematchChangeReportRunner | None
    ) = None,
) -> RecommendationPrematchPipelineRunResult:
    as_of_time = options.normalized_as_of_time_utc
    audit = audit_repository or PostgresRecommendationPrematchPipelineRunRepository(database)
    started = audit.start_run(
        options=options,
        requested_by=requested_by,
        source="recommendation_prematch_pipeline_v3_1",
    )
    warnings: list[str] = []
    try:
        mapping_result = _run_mapping_if_requested(
            database,
            options=options,
            runner=(
                provider_incident_mapping_runner
                or run_recommendation_provider_incident_mapping
            ),
        )
        if (
            options.dry_run
            and mapping_result is not None
            and mapping_result.mapped_incident_count > 0
        ):
            warnings.append("dry_run_provider_incidents_not_persisted_before_recompute")
        recompute_result = _run_recompute_if_requested(
            database,
            options=options,
            runner=recompute_trigger_runner or run_recommendation_recompute_trigger,
        )
        report_result = _run_report_if_requested(
            database,
            options=options,
            runner=prematch_change_report_runner
            or run_recommendation_prematch_change_report,
        )
        warnings.extend(_result_warnings(mapping_result, recompute_result, report_result))
        result = _pipeline_result(
            options,
            as_of_time=as_of_time,
            requested_by=requested_by,
            mapping_result=mapping_result,
            recompute_result=recompute_result,
            report_result=report_result,
            warnings=warnings,
        )
        completed = audit.complete_run(
            recommendation_prematch_pipeline_run_id=(
                started.recommendation_prematch_pipeline_run_id
            ),
            result=result,
        )
        return result.model_copy(
            update={
                "recommendation_prematch_pipeline_run_id": (
                    completed.recommendation_prematch_pipeline_run_id
                ),
                "stored_run": completed,
            }
        )
    except Exception as exc:
        audit.fail_run(
            recommendation_prematch_pipeline_run_id=(
                started.recommendation_prematch_pipeline_run_id
            ),
            error_message=str(exc),
            warnings=warnings,
        )
        raise


def _run_mapping_if_requested(
    database: RecommendationPrematchPipelineDatabase,
    *,
    options: RecommendationPrematchPipelineOptions,
    runner: RecommendationProviderIncidentMappingRunner,
) -> RecommendationProviderIncidentMappingResult | None:
    if not options.run_provider_incident_mapping:
        return None
    return runner(
        database,
        options=RecommendationProviderIncidentMappingOptions(
            as_of_time_utc=options.normalized_as_of_time_utc,
            lookback_hours=options.lookback_hours,
            provider_name=options.provider_name,
            canonical_fixture_id=options.canonical_fixture_id,
            limit=options.provider_observation_limit,
            critical_availability_confidence=options.critical_availability_confidence,
            odds_probability_shift_threshold=options.odds_probability_shift_threshold,
            critical_odds_probability_shift_threshold=(
                options.critical_odds_probability_shift_threshold
            ),
            dry_run=options.dry_run,
        ),
    )


def _run_recompute_if_requested(
    database: RecommendationPrematchPipelineDatabase,
    *,
    options: RecommendationPrematchPipelineOptions,
    runner: RecommendationRecomputeTriggerRunner,
) -> RecommendationRecomputeTriggerRunResult | None:
    if not options.run_recompute_trigger:
        return None
    return runner(
        database,
        options=RecommendationRecomputeTriggerOptions(
            as_of_time_utc=options.normalized_as_of_time_utc,
            lookback_hours=options.lookback_hours,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            include_candidate_pool_incidents=options.include_candidate_pool_incidents,
            preserve_locked_legs=options.preserve_locked_legs,
            trigger_locked_successors=options.trigger_locked_successors,
            dry_run=options.dry_run,
            source_run_limit=options.source_run_limit,
            incident_limit=options.incident_limit,
        ),
    )


def _run_report_if_requested(
    database: RecommendationPrematchPipelineDatabase,
    *,
    options: RecommendationPrematchPipelineOptions,
    runner: RecommendationPrematchChangeReportRunner,
) -> RecommendationPrematchChangeReportRunResult | None:
    if not options.run_prematch_change_report:
        return None
    return runner(
        database,
        options=RecommendationPrematchChangeReportOptions(
            window_start_utc=options.window_start_utc,
            window_end_utc=options.normalized_as_of_time_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            include_provider_incidents=options.include_provider_incidents_in_report,
            dry_run=options.dry_run,
            limit=options.report_limit,
        ),
    )


def _pipeline_result(
    options: RecommendationPrematchPipelineOptions,
    *,
    as_of_time: datetime,
    requested_by: str | None,
    mapping_result: RecommendationProviderIncidentMappingResult | None,
    recompute_result: RecommendationRecomputeTriggerRunResult | None,
    report_result: RecommendationPrematchChangeReportRunResult | None,
    warnings: Sequence[str],
) -> RecommendationPrematchPipelineRunResult:
    generated_run_ids = (
        recompute_result.generated_recommendation_run_ids
        if recompute_result is not None
        else []
    )
    return RecommendationPrematchPipelineRunResult(
        dry_run=options.dry_run,
        as_of_time_utc=as_of_time,
        window_start_utc=options.window_start_utc,
        window_end_utc=as_of_time,
        pass_type=options.pass_type,
        mode=options.mode,
        strategy=options.strategy,
        requested_by=requested_by,
        provider_incident_mapping=mapping_result,
        recompute_trigger=recompute_result,
        prematch_change_report=report_result,
        mapped_incident_count=(
            mapping_result.mapped_incident_count if mapping_result is not None else 0
        ),
        stored_incident_count=(
            mapping_result.stored_incident_count if mapping_result is not None else 0
        ),
        checked_run_count=(
            recompute_result.checked_run_count if recompute_result is not None else 0
        ),
        triggered_run_count=(
            recompute_result.triggered_run_count if recompute_result is not None else 0
        ),
        skipped_run_count=(
            recompute_result.skipped_run_count if recompute_result is not None else 0
        ),
        generated_recommendation_run_ids=generated_run_ids,
        prematch_report_key=(
            report_result.report.report_key if report_result is not None else None
        ),
        warnings=_dedupe_strings(warnings),
    )


def _result_warnings(
    mapping_result: RecommendationProviderIncidentMappingResult | None,
    recompute_result: RecommendationRecomputeTriggerRunResult | None,
    report_result: RecommendationPrematchChangeReportRunResult | None,
) -> list[str]:
    warnings: list[str] = []
    if mapping_result is not None:
        warnings.extend(f"provider_incident_mapping:{item}" for item in mapping_result.warnings)
    if recompute_result is not None:
        warnings.extend(f"recompute_trigger:{item}" for item in recompute_result.warnings)
    if report_result is not None:
        warnings.extend(f"prematch_change_report:{item}" for item in report_result.warnings)
    return warnings


def _record_from_row(row: DatabaseRow) -> RecommendationPrematchPipelineRunRecord:
    return RecommendationPrematchPipelineRunRecord(
        recommendation_prematch_pipeline_run_id=_int(
            row["recommendation_prematch_pipeline_run_id"]
        ),
        run_key=str(row["run_key"]),
        status=_status(row["status"]),
        dry_run=_bool(row["dry_run"]),
        as_of_time_utc=_datetime(row["as_of_time_utc"]),
        window_start_utc=_datetime(row["window_start_utc"]),
        window_end_utc=_datetime(row["window_end_utc"]),
        pass_type=_optional_str(row.get("pass_type")),
        mode=_optional_mode(row.get("mode")),
        strategy=_optional_strategy(row.get("strategy")),
        requested_by=_optional_str(row.get("requested_by")),
        mapped_incident_count=_int(row.get("mapped_incident_count", 0)),
        stored_incident_count=_int(row.get("stored_incident_count", 0)),
        checked_run_count=_int(row.get("checked_run_count", 0)),
        triggered_run_count=_int(row.get("triggered_run_count", 0)),
        skipped_run_count=_int(row.get("skipped_run_count", 0)),
        generated_recommendation_run_ids=[
            _int(item)
            for item in _json_list(row.get("generated_recommendation_run_ids_json"))
        ],
        prematch_report_key=_optional_str(row.get("prematch_report_key")),
        warnings=[str(item) for item in _json_list(row.get("warnings_json"))],
        error_message=_optional_str(row.get("error_message")),
        source=str(row["source"]),
        started_at=_datetime(row["started_at"]),
        completed_at=_optional_datetime(row.get("completed_at")),
        duration_ms=_optional_int(row.get("duration_ms")),
        created_at=_datetime(row["created_at"]),
        updated_at=_datetime(row["updated_at"]),
    )


def _run_key(
    options: RecommendationPrematchPipelineOptions,
    *,
    requested_by: str | None,
) -> str:
    payload = "|".join(
        [
            options.normalized_as_of_time_utc.isoformat(),
            options.window_start_utc.isoformat(),
            options.pass_type or "all_pass_types",
            options.mode or "all_modes",
            options.strategy or "all_strategies",
            options.provider_name or "all_providers",
            options.canonical_fixture_id or "all_fixtures",
            str(options.dry_run),
            requested_by or "system",
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"prematch_pipeline:{digest}"


def _json(value: object) -> str:
    return dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _json_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        parsed = loads(value)
        if isinstance(parsed, list):
            return parsed
        return []
    if isinstance(value, Mapping):
        return []
    return []


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value in result:
            continue
        result.append(value)
    return result


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise RuntimeError("database statement did not return a row")
    return row


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


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in {"1", "t", "true", "yes"}
    raise ValueError(f"expected boolean value, got {type(value).__name__}")


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _status(value: object) -> RecommendationPrematchPipelineRunStatus:
    text = str(value)
    if text not in {"running", "completed", "failed"}:
        raise ValueError(f"unknown prematch pipeline run status: {text}")
    return text  # type: ignore[return-value]


def _optional_mode(value: object) -> RecommendationMode | None:
    text = _optional_str(value)
    if text is None:
        return None
    if text not in {"single", "multiple"}:
        raise ValueError(f"unknown recommendation mode: {text}")
    return text  # type: ignore[return-value]


def _optional_strategy(value: object) -> RecommendationStrategy | None:
    text = _optional_str(value)
    if text is None:
        return None
    if text not in {
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    }:
        raise ValueError(f"unknown recommendation strategy: {text}")
    return text  # type: ignore[return-value]
