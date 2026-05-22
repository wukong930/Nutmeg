from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.config import get_settings
from nutmeg.database import DatabaseRow, PsycopgSyncDatabaseExecutor, QueryParams
from nutmeg.recommendations.chain_integrity import (
    PostgresRecommendationChainIntegrityRepository,
    RecommendationChainIntegrityOptions,
    RecommendationChainIntegrityReport,
    RecommendationChainIntegrityRepository,
    run_recommendation_chain_integrity_check,
)
from nutmeg.recommendations.core_replay import (
    RecommendationCoreReplayOptions,
    RecommendationCoreReplayRunResult,
    run_recommendation_core_replay,
)
from nutmeg.recommendations.global_planner import (
    RecommendationGlobalPlannerOptions,
    RecommendationGlobalPlannerResult,
    run_recommendation_global_planner,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy
from nutmeg.recommendations.prematch_pipeline import (
    RecommendationPrematchPipelineAuditRepository,
    RecommendationPrematchPipelineOptions,
    RecommendationPrematchPipelineRunRecord,
    RecommendationPrematchPipelineRunResult,
    run_recommendation_prematch_pipeline,
)
from nutmeg.recommendations.successor_chain_evaluation import (
    RecommendationSuccessorChainEvaluationOptions,
    RecommendationSuccessorChainEvaluationResult,
    build_recommendation_successor_chain_evaluation_result,
)

DEFAULT_REQUESTED_BY = "core-validation-cli"


class RecommendationCoreValidationDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read rows for recommendation validation runners."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute write statements when a sub-runner is configured to persist."""


class RecommendationCoreValidationGlobalPlannerRunner(Protocol):
    def __call__(
        self,
        database: RecommendationCoreValidationDatabaseExecutor,
        *,
        options: RecommendationGlobalPlannerOptions,
    ) -> RecommendationGlobalPlannerResult: ...


class RecommendationCoreValidationPrematchPipelineRunner(Protocol):
    def __call__(
        self,
        database: RecommendationCoreValidationDatabaseExecutor,
        *,
        options: RecommendationPrematchPipelineOptions,
        requested_by: str | None = None,
        audit_repository: RecommendationPrematchPipelineAuditRepository | None = None,
    ) -> RecommendationPrematchPipelineRunResult: ...


class RecommendationCoreValidationReplayRunner(Protocol):
    def __call__(
        self,
        database: RecommendationCoreValidationDatabaseExecutor,
        *,
        options: RecommendationCoreReplayOptions,
    ) -> RecommendationCoreReplayRunResult: ...


class RecommendationCoreValidationChainIntegrityRunner(Protocol):
    def __call__(
        self,
        repository: RecommendationChainIntegrityRepository,
        *,
        options: RecommendationChainIntegrityOptions,
    ) -> RecommendationChainIntegrityReport: ...


class RecommendationCoreValidationOptions(BaseModel):
    as_of_time_utc: datetime | None = None
    lookback_hours: int = Field(default=24, ge=1, le=720)
    replay_window_start_utc: datetime | None = None
    replay_window_end_utc: datetime | None = None
    pass_type: str | None = Field(default=None, min_length=1)
    mode: RecommendationMode | None = None
    strategy: RecommendationStrategy = "accuracy_first"
    unit_stake: float = Field(default=2.0, gt=0.0)
    max_budget: float | None = Field(default=20.0, gt=0.0)
    min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    require_odds: bool = True
    candidate_limit: int = Field(default=300, ge=1, le=3_000)
    competition_id: str | None = Field(default=None, min_length=1)
    model_version: str | None = Field(default=None, min_length=1)
    provider_name: str | None = Field(default=None, min_length=1)
    canonical_fixture_id: str | None = Field(default=None, min_length=1)
    run_global_best: bool = True
    run_prematch_pipeline: bool = True
    run_core_replay: bool = True
    run_chain_integrity: bool = True
    run_successor_chain_evaluation: bool = True
    dry_run: bool = True
    save_pipeline_audit: bool = False
    requested_by: str | None = DEFAULT_REQUESTED_BY
    provider_observation_limit: int = Field(default=2_000, ge=1, le=5_000)
    source_run_limit: int = Field(default=100, ge=1, le=2_000)
    incident_limit: int = Field(default=1_000, ge=1, le=5_000)
    report_limit: int = Field(default=200, ge=1, le=2_000)
    replay_limit: int = Field(default=200, ge=1, le=2_000)
    chain_integrity_limit: int = Field(default=500, ge=1, le=5_000)
    successor_chain_min_effective_leaf_count: int = Field(default=0, ge=0)
    successor_chain_min_active_edge_count: int = Field(default=0, ge=0)
    successor_chain_max_critical_issue_count: int | None = Field(default=0, ge=0)
    successor_chain_max_ambiguous_successor_source_count: int | None = Field(
        default=0,
        ge=0,
    )
    successor_chain_max_source_status_sync_required_count: int | None = Field(
        default=None,
        ge=0,
    )

    @property
    def normalized_as_of_time_utc(self) -> datetime:
        return _aware_utc(self.as_of_time_utc or datetime.now(UTC))

    @property
    def pipeline_window_start_utc(self) -> datetime:
        return self.normalized_as_of_time_utc - timedelta(hours=self.lookback_hours)

    @property
    def normalized_replay_window_start_utc(self) -> datetime:
        return _aware_utc(self.replay_window_start_utc or self.pipeline_window_start_utc)

    @property
    def normalized_replay_window_end_utc(self) -> datetime:
        return _aware_utc(self.replay_window_end_utc or self.normalized_as_of_time_utc)


class RecommendationCoreValidationRunResult(BaseModel):
    run_key: str
    dry_run: bool
    as_of_time_utc: datetime
    window_start_utc: datetime
    window_end_utc: datetime
    replay_window_start_utc: datetime
    replay_window_end_utc: datetime
    pass_type: str | None = None
    mode: RecommendationMode | None = None
    strategy: RecommendationStrategy
    global_best: RecommendationGlobalPlannerResult | None = None
    prematch_pipeline: RecommendationPrematchPipelineRunResult | None = None
    core_replay: RecommendationCoreReplayRunResult | None = None
    chain_integrity: RecommendationChainIntegrityReport | None = None
    successor_chain_evaluation: RecommendationSuccessorChainEvaluationResult | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class NoopRecommendationPrematchPipelineAuditRepository:
    def __init__(self, options: RecommendationCoreValidationOptions) -> None:
        self.options = options

    def start_run(
        self,
        *,
        options: RecommendationPrematchPipelineOptions,
        requested_by: str | None,
        source: str,
    ) -> RecommendationPrematchPipelineRunRecord:
        as_of_time = options.normalized_as_of_time_utc
        return RecommendationPrematchPipelineRunRecord(
            recommendation_prematch_pipeline_run_id=1,
            run_key=_run_key(self.options),
            status="running",
            dry_run=options.dry_run,
            as_of_time_utc=as_of_time,
            window_start_utc=options.window_start_utc,
            window_end_utc=as_of_time,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            requested_by=requested_by,
            source=source,
            started_at=as_of_time,
            created_at=as_of_time,
            updated_at=as_of_time,
        )

    def complete_run(
        self,
        *,
        recommendation_prematch_pipeline_run_id: int,
        result: RecommendationPrematchPipelineRunResult,
    ) -> RecommendationPrematchPipelineRunRecord:
        as_of_time = result.as_of_time_utc
        return RecommendationPrematchPipelineRunRecord(
            recommendation_prematch_pipeline_run_id=recommendation_prematch_pipeline_run_id,
            run_key=_run_key(self.options),
            status="completed",
            dry_run=result.dry_run,
            as_of_time_utc=as_of_time,
            window_start_utc=result.window_start_utc,
            window_end_utc=result.window_end_utc,
            pass_type=result.pass_type,
            mode=result.mode,
            strategy=result.strategy,
            requested_by=result.requested_by,
            mapped_incident_count=result.mapped_incident_count,
            stored_incident_count=result.stored_incident_count,
            checked_run_count=result.checked_run_count,
            triggered_run_count=result.triggered_run_count,
            skipped_run_count=result.skipped_run_count,
            generated_recommendation_run_ids=result.generated_recommendation_run_ids,
            prematch_report_key=result.prematch_report_key,
            warnings=result.warnings,
            source="recommendation_core_validation_runner_v3_1",
            started_at=as_of_time,
            completed_at=as_of_time,
            duration_ms=0,
            created_at=as_of_time,
            updated_at=as_of_time,
        )

    def fail_run(
        self,
        *,
        recommendation_prematch_pipeline_run_id: int,
        error_message: str,
        warnings: Sequence[str],
    ) -> RecommendationPrematchPipelineRunRecord:
        as_of_time = self.options.normalized_as_of_time_utc
        return RecommendationPrematchPipelineRunRecord(
            recommendation_prematch_pipeline_run_id=recommendation_prematch_pipeline_run_id,
            run_key=_run_key(self.options),
            status="failed",
            dry_run=self.options.dry_run,
            as_of_time_utc=as_of_time,
            window_start_utc=self.options.pipeline_window_start_utc,
            window_end_utc=as_of_time,
            pass_type=self.options.pass_type,
            mode=self.options.mode,
            strategy=self.options.strategy,
            requested_by=self.options.requested_by,
            warnings=list(warnings),
            error_message=error_message,
            source="recommendation_core_validation_runner_v3_1",
            started_at=as_of_time,
            completed_at=as_of_time,
            duration_ms=0,
            created_at=as_of_time,
            updated_at=as_of_time,
        )


def run_recommendation_core_validation(
    database: RecommendationCoreValidationDatabaseExecutor,
    *,
    options: RecommendationCoreValidationOptions,
    global_planner_runner: RecommendationCoreValidationGlobalPlannerRunner | None = None,
    prematch_pipeline_runner: (
        RecommendationCoreValidationPrematchPipelineRunner | None
    ) = None,
    core_replay_runner: RecommendationCoreValidationReplayRunner | None = None,
    chain_integrity_runner: RecommendationCoreValidationChainIntegrityRunner | None = None,
) -> RecommendationCoreValidationRunResult:
    as_of_time = options.normalized_as_of_time_utc
    run_key = _run_key(options)
    warnings: list[str] = []

    global_result = None
    if options.run_global_best:
        global_result = (global_planner_runner or run_recommendation_global_planner)(
            database,
            options=RecommendationGlobalPlannerOptions(
                as_of_time_utc=as_of_time,
                strategy=options.strategy,
                unit_stake=options.unit_stake,
                max_budget=options.max_budget,
                pass_types=_global_pass_types(options),
                modes=_global_modes(options),
                min_probability=options.min_probability,
                min_data_quality_score=options.min_data_quality_score,
                candidate_limit=options.candidate_limit,
                require_odds=options.require_odds,
                competition_id=options.competition_id,
                model_version=options.model_version,
                dry_run=options.dry_run,
                internal_trace_json={
                    "source": "recommendation_core_validation_runner_v3_1",
                    "core_validation_run_key": run_key,
                },
            ),
        )
        warnings.extend(f"global_best:{item}" for item in global_result.warnings)

    pipeline_result = None
    if options.run_prematch_pipeline:
        pipeline_result = (
            prematch_pipeline_runner or run_recommendation_prematch_pipeline
        )(
            database,
            options=RecommendationPrematchPipelineOptions(
                as_of_time_utc=as_of_time,
                lookback_hours=options.lookback_hours,
                pass_type=options.pass_type,
                mode=options.mode,
                strategy=options.strategy,
                provider_name=options.provider_name,
                canonical_fixture_id=options.canonical_fixture_id,
                dry_run=options.dry_run,
                provider_observation_limit=options.provider_observation_limit,
                source_run_limit=options.source_run_limit,
                incident_limit=options.incident_limit,
                report_limit=options.report_limit,
            ),
            requested_by=options.requested_by,
            audit_repository=(
                None
                if options.save_pipeline_audit
                else NoopRecommendationPrematchPipelineAuditRepository(options)
            ),
        )
        if not options.save_pipeline_audit:
            pipeline_result = pipeline_result.model_copy(update={"stored_run": None})
        warnings.extend(f"prematch_pipeline:{item}" for item in pipeline_result.warnings)

    replay_result = None
    if options.run_core_replay:
        replay_result = (core_replay_runner or run_recommendation_core_replay)(
            database,
            options=RecommendationCoreReplayOptions(
                window_start_utc=options.normalized_replay_window_start_utc,
                window_end_utc=options.normalized_replay_window_end_utc,
                pass_type=options.pass_type,
                mode=options.mode,
                strategy=options.strategy,
                limit=options.replay_limit,
            ),
        )
        warnings.extend(f"core_replay:{item}" for item in replay_result.warnings)

    chain_integrity_result = None
    if options.run_chain_integrity:
        chain_integrity_result = (
            chain_integrity_runner or run_recommendation_chain_integrity_check
        )(
            PostgresRecommendationChainIntegrityRepository(database),
            options=RecommendationChainIntegrityOptions(
                window_start_utc=options.normalized_replay_window_start_utc,
                window_end_utc=options.normalized_replay_window_end_utc,
                pass_type=options.pass_type,
                mode=options.mode,
                strategy=options.strategy,
                limit=options.chain_integrity_limit,
            ),
        )
        warnings.extend(
            f"chain_integrity:{issue.severity}:{issue.code}"
            for issue in chain_integrity_result.issues
            if issue.severity == "critical"
        )

    successor_chain_evaluation_result = None
    if options.run_successor_chain_evaluation and chain_integrity_result is not None:
        successor_chain_evaluation_result = (
            build_recommendation_successor_chain_evaluation_result(
                chain_integrity_result,
                options=RecommendationSuccessorChainEvaluationOptions(
                    window_start_utc=options.normalized_replay_window_start_utc,
                    window_end_utc=options.normalized_replay_window_end_utc,
                    pass_type=options.pass_type,
                    mode=options.mode,
                    strategy=options.strategy,
                    limit=options.chain_integrity_limit,
                    min_effective_leaf_count=(
                        options.successor_chain_min_effective_leaf_count
                    ),
                    min_active_edge_count=options.successor_chain_min_active_edge_count,
                    max_critical_issue_count=(
                        options.successor_chain_max_critical_issue_count
                    ),
                    max_ambiguous_successor_source_count=(
                        options.successor_chain_max_ambiguous_successor_source_count
                    ),
                    max_source_status_sync_required_count=(
                        options.successor_chain_max_source_status_sync_required_count
                    ),
                ),
            )
        )
        warnings.extend(
            f"successor_chain_evaluation:failed_check:{check.name}"
            for check in successor_chain_evaluation_result.checks
            if check.status == "failed"
        )

    warnings = _dedupe_strings(warnings)
    summary = _summary(
        global_result=global_result,
        pipeline_result=pipeline_result,
        replay_result=replay_result,
        chain_integrity_result=chain_integrity_result,
        successor_chain_evaluation_result=successor_chain_evaluation_result,
        warning_count=len(warnings),
    )
    return RecommendationCoreValidationRunResult(
        run_key=run_key,
        dry_run=options.dry_run,
        as_of_time_utc=as_of_time,
        window_start_utc=options.pipeline_window_start_utc,
        window_end_utc=as_of_time,
        replay_window_start_utc=options.normalized_replay_window_start_utc,
        replay_window_end_utc=options.normalized_replay_window_end_utc,
        pass_type=options.pass_type,
        mode=options.mode,
        strategy=options.strategy,
        global_best=global_result,
        prematch_pipeline=pipeline_result,
        core_replay=replay_result,
        chain_integrity=chain_integrity_result,
        successor_chain_evaluation=successor_chain_evaluation_result,
        warnings=warnings,
        summary_json=summary,
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
    result = run_recommendation_core_validation(
        database,
        options=_options_from_args(args),
    )
    print(result.model_dump_json(indent=2))


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Run Nutmeg recommendation core validation chain.",
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument("--as-of-time-utc", default=None)
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--replay-window-start-utc", default=None)
    parser.add_argument("--replay-window-end-utc", default=None)
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
        default="accuracy_first",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--no-max-budget", action="store_true")
    parser.add_argument("--min-probability", type=float, default=0.20)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--candidate-limit", type=int, default=300)
    parser.add_argument("--no-require-odds", action="store_true")
    parser.add_argument("--competition-id", default=None)
    parser.add_argument("--model-version", default=None)
    parser.add_argument("--provider-name", default=None)
    parser.add_argument("--canonical-fixture-id", default=None)
    parser.add_argument("--requested-by", default=DEFAULT_REQUESTED_BY)
    parser.add_argument("--provider-observation-limit", type=int, default=2_000)
    parser.add_argument("--source-run-limit", type=int, default=100)
    parser.add_argument("--incident-limit", type=int, default=1_000)
    parser.add_argument("--report-limit", type=int, default=200)
    parser.add_argument("--replay-limit", type=int, default=200)
    parser.add_argument("--chain-integrity-limit", type=int, default=500)
    parser.add_argument("--skip-global-best", action="store_true")
    parser.add_argument("--skip-prematch-pipeline", action="store_true")
    parser.add_argument("--skip-core-replay", action="store_true")
    parser.add_argument("--skip-chain-integrity", action="store_true")
    parser.add_argument("--skip-successor-chain-evaluation", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--save-audit", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationCoreValidationOptions:
    return RecommendationCoreValidationOptions(
        as_of_time_utc=_optional_datetime(args.as_of_time_utc),
        lookback_hours=args.lookback_hours,
        replay_window_start_utc=_optional_datetime(args.replay_window_start_utc),
        replay_window_end_utc=_optional_datetime(args.replay_window_end_utc),
        pass_type=args.pass_type,
        mode=args.mode,
        strategy=args.strategy,
        unit_stake=args.unit_stake,
        max_budget=None if args.no_max_budget else args.max_budget,
        min_probability=args.min_probability,
        min_data_quality_score=args.min_data_quality_score,
        require_odds=not args.no_require_odds,
        candidate_limit=args.candidate_limit,
        competition_id=args.competition_id,
        model_version=args.model_version,
        provider_name=args.provider_name,
        canonical_fixture_id=args.canonical_fixture_id,
        run_global_best=not args.skip_global_best,
        run_prematch_pipeline=not args.skip_prematch_pipeline,
        run_core_replay=not args.skip_core_replay,
        run_chain_integrity=not args.skip_chain_integrity,
        run_successor_chain_evaluation=(
            not args.skip_chain_integrity and not args.skip_successor_chain_evaluation
        ),
        dry_run=not args.commit,
        save_pipeline_audit=args.save_audit,
        requested_by=args.requested_by,
        provider_observation_limit=args.provider_observation_limit,
        source_run_limit=args.source_run_limit,
        incident_limit=args.incident_limit,
        report_limit=args.report_limit,
        replay_limit=args.replay_limit,
        chain_integrity_limit=args.chain_integrity_limit,
    )


def _summary(
    *,
    global_result: RecommendationGlobalPlannerResult | None,
    pipeline_result: RecommendationPrematchPipelineRunResult | None,
    replay_result: RecommendationCoreReplayRunResult | None,
    chain_integrity_result: RecommendationChainIntegrityReport | None,
    successor_chain_evaluation_result: RecommendationSuccessorChainEvaluationResult | None,
    warning_count: int,
) -> dict[str, object]:
    replay_summary = (
        replay_result.report.summary_json if replay_result is not None else {}
    )
    chain_summary = (
        chain_integrity_result.summary_json if chain_integrity_result is not None else {}
    )
    successor_summary = (
        successor_chain_evaluation_result.summary_json
        if successor_chain_evaluation_result is not None
        else {}
    )
    unified_candidate_pool_summary = _unified_candidate_pool_summary(global_result)
    return {
        "global_best_candidate_count": (
            global_result.candidate_count if global_result is not None else 0
        ),
        "global_best_generated_option_count": (
            global_result.generated_option_count if global_result is not None else 0
        ),
        "global_best_selected": (
            global_result.best_option is not None if global_result is not None else False
        ),
        "global_best_stored_run_id": _stored_global_run_id(global_result),
        **unified_candidate_pool_summary,
        "prematch_checked_run_count": (
            pipeline_result.checked_run_count if pipeline_result is not None else 0
        ),
        "prematch_triggered_run_count": (
            pipeline_result.triggered_run_count if pipeline_result is not None else 0
        ),
        "prematch_generated_run_count": (
            len(pipeline_result.generated_recommendation_run_ids)
            if pipeline_result is not None
            else 0
        ),
        "prematch_report_key": (
            pipeline_result.prematch_report_key if pipeline_result is not None else None
        ),
        "core_replay_ready": bool(replay_summary.get("core_flow_ready", False)),
        "core_replay_run_count": _summary_int(replay_summary, "run_count"),
        "core_replay_settled_run_count": _summary_int(
            replay_summary,
            "settled_run_count",
        ),
        "core_replay_effective_evaluated_run_count": _summary_int(
            replay_summary,
            "effective_evaluated_run_count",
        ),
        "core_replay_final_hit": replay_summary.get("final_hit"),
        "core_replay_roi": replay_summary.get("roi"),
        "effective_chain_count": _summary_int(replay_summary, "effective_chain_count"),
        "effective_chain_active_edge_count": _summary_int(
            replay_summary,
            "effective_chain_active_edge_count",
        ),
        "effective_leaf_run_count": _summary_sequence_count(
            replay_summary,
            "effective_leaf_recommendation_run_ids",
        ),
        "superseded_source_run_count": _summary_int(
            replay_summary,
            "superseded_source_run_count",
        ),
        "ambiguous_successor_source_count": _summary_sequence_count(
            replay_summary,
            "ambiguous_successor_source_recommendation_run_ids",
        ),
        "validity_window_status_counts": _summary_mapping(
            replay_summary,
            "validity_window_status_counts",
        ),
        "current_answer_count": _summary_sequence_count(
            replay_summary,
            "current_answer_recommendation_run_ids",
        ),
        "stale_recommendation_count": _summary_sequence_count(
            replay_summary,
            "stale_recommendation_run_ids",
        ),
        "expired_kickoff_recommendation_count": _summary_sequence_count(
            replay_summary,
            "expired_kickoff_recommendation_run_ids",
        ),
        "stale_incident_recommendation_count": _summary_sequence_count(
            replay_summary,
            "stale_incident_recommendation_run_ids",
        ),
        "successor_recompute_required_count": _summary_sequence_count(
            replay_summary,
            "successor_recompute_required_recommendation_run_ids",
        ),
        "chain_integrity_ready": (
            chain_integrity_result.ready if chain_integrity_result is not None else False
        ),
        "chain_integrity_issue_count": _summary_int(chain_summary, "issue_count"),
        "chain_integrity_critical_issue_count": _summary_int(
            chain_summary,
            "critical_issue_count",
        ),
        "chain_integrity_warning_issue_count": _summary_int(
            chain_summary,
            "warning_issue_count",
        ),
        "chain_integrity_source_status_sync_required_count": _summary_int(
            chain_summary,
            "source_status_sync_required_count",
        ),
        "successor_chain_evaluation_passed": (
            successor_chain_evaluation_result.passed
            if successor_chain_evaluation_result is not None
            else False
        ),
        "successor_chain_effective_leaf_count": _summary_int(
            successor_summary,
            "effective_leaf_count",
        ),
        "successor_chain_active_edge_count": _summary_int(
            successor_summary,
            "active_edge_count",
        ),
        "successor_chain_critical_issue_count": _summary_int(
            successor_summary,
            "chain_integrity_critical_issue_count",
        ),
        "successor_chain_ambiguous_source_count": _summary_int(
            successor_summary,
            "ambiguous_successor_source_count",
        ),
        "successor_chain_source_status_sync_required_count": _summary_int(
            successor_summary,
            "source_status_sync_required_count",
        ),
        "warning_count": warning_count,
        "calculation_basis": "recommendation_core_validation_runner_v3_1",
    }


def _stored_global_run_id(
    global_result: RecommendationGlobalPlannerResult | None,
) -> int | None:
    if global_result is None or global_result.stored_run is None:
        return None
    return global_result.stored_run.recommendation_run_id


def _unified_candidate_pool_summary(
    global_result: RecommendationGlobalPlannerResult | None,
) -> dict[str, object]:
    if global_result is None:
        return _empty_unified_candidate_pool_summary()
    pool = _summary_mapping(
        global_result.final_answer_decision_json,
        "unified_candidate_pool",
    )
    if not pool:
        return _empty_unified_candidate_pool_summary()
    family_keys = _summary_sequence(pool, "candidate_family_keys")
    selected_family_key = _summary_string(pool, "selected_family_key")
    selected_pass_type = _summary_string(pool, "selected_pass_type")
    return {
        "unified_candidate_pool_present": True,
        "unified_candidate_pool_candidate_count": _summary_int(
            pool,
            "candidate_count",
        ),
        "unified_candidate_pool_valid_candidate_count": _summary_int(
            pool,
            "valid_candidate_count",
        ),
        "unified_candidate_pool_family_count": _summary_int(pool, "family_count"),
        "unified_candidate_pool_candidate_family_keys": family_keys,
        "unified_candidate_pool_selected_family_key": selected_family_key,
        "unified_candidate_pool_selected_pass_type": selected_pass_type,
        "unified_candidate_pool_selected_mode": _summary_string(pool, "selected_mode"),
        "unified_candidate_pool_two_x_one_is_candidate_family": _summary_bool(
            pool,
            "two_x_one_is_candidate_family",
        ),
        "unified_candidate_pool_correct_score_candidate_present": _summary_bool(
            pool,
            "correct_score_candidate_present",
        ),
        "unified_candidate_pool_handicap_candidate_present": _summary_bool(
            pool,
            "handicap_candidate_present",
        ),
        "unified_candidate_pool_multiple_value_candidate_count": _summary_int(
            pool,
            "multiple_value_candidate_count",
        ),
        "unified_candidate_pool_multiple_value_admitted_candidate_count": (
            _summary_int(pool, "multiple_value_admitted_candidate_count")
        ),
        "unified_candidate_pool_multiple_value_rejected_candidate_count": (
            _summary_int(pool, "multiple_value_rejected_candidate_count")
        ),
        "unified_candidate_pool_multiple_value_extra_option_count": _summary_int(
            pool,
            "multiple_value_extra_option_count",
        ),
        "unified_candidate_pool_selected_multiple_value_status": _summary_string(
            pool,
            "selected_multiple_value_status",
        ),
        "unified_candidate_pool_selected_multiple_value_admitted": (
            _summary_optional_bool(pool, "selected_multiple_value_admitted")
        ),
        "unified_candidate_pool_selected_multiple_extra_option_count": _summary_int(
            pool,
            "selected_multiple_extra_option_count",
        ),
        "unified_candidate_pool_multiple_value_rejection_reason_counts": (
            _summary_int_mapping(pool, "multiple_value_rejection_reason_counts")
        ),
        "unified_candidate_pool_selection_mismatch": (
            selected_family_key is not None and selected_family_key not in family_keys
        ),
        "unified_candidate_pool_selected_2x1": selected_pass_type == "2x1",
    }


def _empty_unified_candidate_pool_summary() -> dict[str, object]:
    return {
        "unified_candidate_pool_present": False,
        "unified_candidate_pool_candidate_count": 0,
        "unified_candidate_pool_valid_candidate_count": 0,
        "unified_candidate_pool_family_count": 0,
        "unified_candidate_pool_candidate_family_keys": [],
        "unified_candidate_pool_selected_family_key": None,
        "unified_candidate_pool_selected_pass_type": None,
        "unified_candidate_pool_selected_mode": None,
        "unified_candidate_pool_two_x_one_is_candidate_family": False,
        "unified_candidate_pool_correct_score_candidate_present": False,
        "unified_candidate_pool_handicap_candidate_present": False,
        "unified_candidate_pool_multiple_value_candidate_count": 0,
        "unified_candidate_pool_multiple_value_admitted_candidate_count": 0,
        "unified_candidate_pool_multiple_value_rejected_candidate_count": 0,
        "unified_candidate_pool_multiple_value_extra_option_count": 0,
        "unified_candidate_pool_selected_multiple_value_status": None,
        "unified_candidate_pool_selected_multiple_value_admitted": None,
        "unified_candidate_pool_selected_multiple_extra_option_count": 0,
        "unified_candidate_pool_multiple_value_rejection_reason_counts": {},
        "unified_candidate_pool_selection_mismatch": False,
        "unified_candidate_pool_selected_2x1": False,
    }


def _global_pass_types(options: RecommendationCoreValidationOptions) -> tuple[str, ...]:
    if options.pass_type is not None:
        return (options.pass_type,)
    return ("1x1", "2x1", "3x1", "4x1", "5x1", "6x1", "7x1", "8x1")


def _global_modes(
    options: RecommendationCoreValidationOptions,
) -> tuple[RecommendationMode, ...]:
    if options.mode is not None:
        return (options.mode,)
    return ("single", "multiple")


def _run_key(options: RecommendationCoreValidationOptions) -> str:
    payload = "|".join(
        [
            options.normalized_as_of_time_utc.isoformat(),
            options.pipeline_window_start_utc.isoformat(),
            options.normalized_replay_window_start_utc.isoformat(),
            options.normalized_replay_window_end_utc.isoformat(),
            options.pass_type or "all_pass_types",
            options.mode or "all_modes",
            options.strategy,
            str(options.dry_run),
            str(options.run_global_best),
            str(options.run_prematch_pipeline),
            str(options.run_core_replay),
            str(options.run_chain_integrity),
            options.requested_by or "system",
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"core_validation:{digest}"


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value in result:
            continue
        result.append(value)
    return result


def _summary_int(summary: dict[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    return 0


def _summary_mapping(summary: Mapping[str, object], key: str) -> dict[str, object]:
    value = summary.get(key)
    if not isinstance(value, Mapping):
        return {}
    return {str(item_key): item_value for item_key, item_value in value.items()}


def _summary_int_mapping(summary: Mapping[str, object], key: str) -> dict[str, int]:
    value = summary.get(key)
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for item_key, item_value in value.items():
        if isinstance(item_value, bool):
            result[str(item_key)] = int(item_value)
        elif isinstance(item_value, int):
            result[str(item_key)] = item_value
        elif isinstance(item_value, float | str):
            result[str(item_key)] = int(item_value)
    return dict(sorted(result.items()))


def _summary_sequence(summary: Mapping[str, object], key: str) -> list[str]:
    value = summary.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [str(item) for item in value]


def _summary_sequence_count(summary: Mapping[str, object], key: str) -> int:
    value = summary.get(key)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return len(value)
    return 0


def _summary_string(summary: Mapping[str, object], key: str) -> str | None:
    value = summary.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _summary_bool(summary: Mapping[str, object], key: str) -> bool:
    value = summary.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "passed"}
    return False


def _summary_optional_bool(summary: Mapping[str, object], key: str) -> bool | None:
    value = summary.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "passed"}:
            return True
        if normalized in {"0", "false", "no", "failed", "none", "null"}:
            return False
    return None


def _optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


if __name__ == "__main__":
    main()
