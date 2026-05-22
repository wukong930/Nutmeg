from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.config import get_settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.recommendations.chain_integrity import (
    PostgresRecommendationChainIntegrityRepository,
    RecommendationChainIntegrityOptions,
    RecommendationChainIntegrityReport,
    RecommendationChainIntegrityRepository,
    run_recommendation_chain_integrity_check,
)
from nutmeg.recommendations.lifecycle import RecommendationLifecycleStatus
from nutmeg.recommendations.models import RecommendationMode
from nutmeg.recommendations.repository import (
    PostgresRecommendationRepository,
    RecommendationDatabaseExecutor,
    RecommendationLifecycleMutationResult,
)


class RecommendationSourceStatusSyncRepository(Protocol):
    def transition_run_status(
        self,
        recommendation_run_id: int,
        *,
        to_status: RecommendationLifecycleStatus,
        event_time_utc: datetime,
        reason_code: str,
        metadata_json: dict[str, object] | None = None,
    ) -> RecommendationLifecycleMutationResult:
        """Update recommendation run lifecycle status and record an event."""


class RecommendationSourceStatusSyncOptions(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str | None = Field(default=None, min_length=1)
    mode: RecommendationMode | None = None
    strategy: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=500, ge=1, le=5_000)
    event_time_utc: datetime | None = None
    dry_run: bool = True
    allowed_source_statuses: tuple[str, ...] = ("current", "locked")
    reason_code: str = Field(default="successor_source_status_sync", min_length=1)

    @property
    def normalized_window_start_utc(self) -> datetime:
        return _aware_utc(self.window_start_utc)

    @property
    def normalized_window_end_utc(self) -> datetime:
        return _aware_utc(self.window_end_utc)

    @property
    def normalized_event_time_utc(self) -> datetime:
        return _aware_utc(self.event_time_utc or datetime.now(UTC))


class RecommendationSourceStatusSyncCandidate(BaseModel):
    recommendation_run_id: int = Field(gt=0)
    run_key: str | None = None
    current_status: str
    target_status: str = "superseded"
    successor_recommendation_run_ids: list[int] = Field(default_factory=list)


class RecommendationSourceStatusSyncRunResult(BaseModel):
    dry_run: bool
    blocked: bool
    block_reason: str | None = None
    report: RecommendationChainIntegrityReport
    candidates: list[RecommendationSourceStatusSyncCandidate] = Field(default_factory=list)
    synced_source_recommendation_run_ids: list[int] = Field(default_factory=list)
    skipped_source_recommendation_run_ids: list[int] = Field(default_factory=list)
    mutations: list[RecommendationLifecycleMutationResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def run_recommendation_source_status_sync(
    database: RecommendationDatabaseExecutor,
    *,
    options: RecommendationSourceStatusSyncOptions,
    chain_repository: RecommendationChainIntegrityRepository | None = None,
    status_repository: RecommendationSourceStatusSyncRepository | None = None,
) -> RecommendationSourceStatusSyncRunResult:
    chain_reader = chain_repository or PostgresRecommendationChainIntegrityRepository(database)
    status_writer = status_repository or PostgresRecommendationRepository(database)
    report = run_recommendation_chain_integrity_check(
        chain_reader,
        options=RecommendationChainIntegrityOptions(
            window_start_utc=options.normalized_window_start_utc,
            window_end_utc=options.normalized_window_end_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            limit=options.limit,
        ),
    )
    candidates, candidate_warnings = _sync_candidates(report, options=options)
    critical_issues = [
        issue for issue in report.issues if issue.severity == "critical"
    ]
    if critical_issues:
        warnings = [
            *candidate_warnings,
            *[
                f"source_status_sync_blocked_by_chain_integrity:{issue.code}"
                for issue in critical_issues
            ],
        ]
        return _result(
            options=options,
            report=report,
            blocked=True,
            block_reason="chain_integrity_critical_issues",
            candidates=candidates,
            skipped_source_recommendation_run_ids=[
                candidate.recommendation_run_id for candidate in candidates
            ],
            warnings=warnings,
        )

    if options.dry_run:
        return _result(
            options=options,
            report=report,
            blocked=False,
            candidates=candidates,
            warnings=candidate_warnings,
        )

    mutations: list[RecommendationLifecycleMutationResult] = []
    synced_ids: list[int] = []
    warnings = list(candidate_warnings)
    for candidate in candidates:
        mutation = status_writer.transition_run_status(
            candidate.recommendation_run_id,
            to_status="superseded",
            event_time_utc=options.normalized_event_time_utc,
            reason_code=options.reason_code,
            metadata_json={
                "successor_recommendation_run_ids": (
                    candidate.successor_recommendation_run_ids
                ),
                "previous_status": candidate.current_status,
                "source": "recommendation_source_status_sync_v3_1",
            },
        )
        mutations.append(mutation)
        synced_ids.append(candidate.recommendation_run_id)

    return _result(
        options=options,
        report=report,
        blocked=False,
        candidates=candidates,
        synced_source_recommendation_run_ids=synced_ids,
        mutations=mutations,
        warnings=warnings,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = get_settings()
    database = PsycopgSyncDatabaseExecutor(
        args.database_url or settings.database_url,
        connect_timeout_seconds=(
            args.connect_timeout_seconds or settings.database_connect_timeout_seconds
        ),
    )
    result = run_recommendation_source_status_sync(
        database,
        options=_options_from_args(args),
    )
    print(result.model_dump_json(indent=2))
    if result.blocked and not args.no_fail_process:
        raise SystemExit(1)


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Run Nutmeg recommendation source status sync.",
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument("--window-start-utc", required=True)
    parser.add_argument("--window-end-utc", required=True)
    parser.add_argument("--pass-type", default=None)
    parser.add_argument("--mode", choices=["single", "multiple"], default=None)
    parser.add_argument(
        "--strategy",
        choices=[
            "accuracy_first",
            "value_first",
            "upset_protection",
            "budget_constrained",
        ],
        default=None,
    )
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--event-time-utc", default=None)
    parser.add_argument(
        "--allowed-source-statuses",
        default="current,locked",
        help="Comma-separated source statuses eligible for sync.",
    )
    parser.add_argument(
        "--reason-code",
        default="successor_source_status_sync",
    )
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationSourceStatusSyncOptions:
    return RecommendationSourceStatusSyncOptions(
        window_start_utc=_datetime(args.window_start_utc),
        window_end_utc=_datetime(args.window_end_utc),
        pass_type=args.pass_type,
        mode=args.mode,
        strategy=args.strategy,
        limit=args.limit,
        event_time_utc=_optional_datetime(args.event_time_utc),
        dry_run=not args.commit,
        allowed_source_statuses=tuple(_csv(args.allowed_source_statuses)),
        reason_code=args.reason_code,
    )


def _sync_candidates(
    report: RecommendationChainIntegrityReport,
    *,
    options: RecommendationSourceStatusSyncOptions,
) -> tuple[list[RecommendationSourceStatusSyncCandidate], list[str]]:
    node_by_id = {node.recommendation_run_id: node for node in report.nodes}
    candidates: list[RecommendationSourceStatusSyncCandidate] = []
    warnings: list[str] = []
    used_ids: set[int] = set()
    for issue in report.issues:
        if issue.code != "source_status_not_superseded":
            continue
        run_id = issue.recommendation_run_id
        if run_id is None or run_id in used_ids:
            continue
        node = node_by_id.get(run_id)
        if node is None:
            warnings.append(f"source_status_sync_candidate_missing:{run_id}")
            continue
        if node.status not in set(options.allowed_source_statuses):
            warnings.append(
                f"source_status_sync_unsupported_status:{run_id}:{node.status}"
            )
            continue
        candidates.append(
            RecommendationSourceStatusSyncCandidate(
                recommendation_run_id=node.recommendation_run_id,
                run_key=node.run_key,
                current_status=node.status,
                successor_recommendation_run_ids=list(
                    issue.successor_recommendation_run_ids
                ),
            )
        )
        used_ids.add(run_id)
    return candidates, warnings


def _result(
    *,
    options: RecommendationSourceStatusSyncOptions,
    report: RecommendationChainIntegrityReport,
    blocked: bool,
    block_reason: str | None = None,
    candidates: Sequence[RecommendationSourceStatusSyncCandidate] = (),
    synced_source_recommendation_run_ids: Sequence[int] = (),
    skipped_source_recommendation_run_ids: Sequence[int] = (),
    mutations: Sequence[RecommendationLifecycleMutationResult] = (),
    warnings: Sequence[str] = (),
) -> RecommendationSourceStatusSyncRunResult:
    summary: dict[str, object] = {
        "dry_run": options.dry_run,
        "blocked": blocked,
        "block_reason": block_reason,
        "candidate_count": len(candidates),
        "synced_source_count": len(synced_source_recommendation_run_ids),
        "skipped_source_count": len(skipped_source_recommendation_run_ids),
        "candidate_source_recommendation_run_ids": [
            candidate.recommendation_run_id for candidate in candidates
        ],
        "synced_source_recommendation_run_ids": list(
            synced_source_recommendation_run_ids
        ),
        "skipped_source_recommendation_run_ids": list(
            skipped_source_recommendation_run_ids
        ),
        "chain_integrity_ready": report.ready,
        "chain_integrity_critical_issue_count": _summary_int(
            report.summary_json,
            "critical_issue_count",
        ),
        "calculation_basis": "recommendation_source_status_sync_v3_1",
    }
    return RecommendationSourceStatusSyncRunResult(
        dry_run=options.dry_run,
        blocked=blocked,
        block_reason=block_reason,
        report=report,
        candidates=list(candidates),
        synced_source_recommendation_run_ids=list(synced_source_recommendation_run_ids),
        skipped_source_recommendation_run_ids=list(
            skipped_source_recommendation_run_ids
        ),
        mutations=list(mutations),
        warnings=list(warnings),
        summary_json=summary,
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _datetime(value: str) -> datetime:
    return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _summary_int(summary_json: dict[str, object], key: str) -> int:
    value = summary_json.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
