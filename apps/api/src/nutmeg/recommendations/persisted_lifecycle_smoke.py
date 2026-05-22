from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.config import get_settings
from nutmeg.database import DatabaseRow, PsycopgSyncDatabaseExecutor, QueryParams
from nutmeg.recommendations.baseline_seed import (
    BASELINE_COMPETITION_ID,
    BASELINE_MODEL_VERSION,
    DEFAULT_BASELINE_AS_OF_TIME_UTC,
    RecommendationBaselineSeedOptions,
    RecommendationBaselineSeedProfile,
    RecommendationBaselineSeedResult,
    run_recommendation_baseline_seed,
)
from nutmeg.recommendations.chain_integrity import (
    PostgresRecommendationChainIntegrityRepository,
    RecommendationChainIntegrityRepository,
)
from nutmeg.recommendations.global_planner import (
    RecommendationGlobalPlannerOptions,
    RecommendationGlobalPlannerResult,
    run_recommendation_global_planner,
)
from nutmeg.recommendations.models import (
    RecommendationCandidate,
    RecommendationMode,
    RecommendationStrategy,
)
from nutmeg.recommendations.repository import (
    PostgresRecommendationRepository,
    RecommendationLifecycleMutationResult,
)
from nutmeg.recommendations.source_status_sync import (
    RecommendationSourceStatusSyncOptions,
    RecommendationSourceStatusSyncRunResult,
    run_recommendation_source_status_sync,
)
from nutmeg.recommendations.successor import (
    RecommendationSuccessorRecomputeOptions,
    RecommendationSuccessorRecomputeRunResult,
    run_recommendation_successor_recompute,
)
from nutmeg.recommendations.successor_chain_evaluation import (
    RecommendationSuccessorChainEvaluationOptions,
    RecommendationSuccessorChainEvaluationResult,
    run_recommendation_successor_chain_evaluation,
)


class RecommendationPersistedLifecycleSmokeDatabase(Protocol):
    def execute(self, query: str, params: QueryParams) -> None:
        """Execute seed cleanup/write statements."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read rows for recommendation candidate and chain queries."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute writes with RETURNING and return one row."""


class RecommendationPersistedLifecycleSmokeSeedRunner(Protocol):
    def __call__(
        self,
        database: RecommendationPersistedLifecycleSmokeDatabase,
        *,
        options: RecommendationBaselineSeedOptions | None = None,
    ) -> RecommendationBaselineSeedResult: ...


class RecommendationPersistedLifecycleSmokeGlobalPlannerRunner(Protocol):
    def __call__(
        self,
        database: RecommendationPersistedLifecycleSmokeDatabase,
        *,
        options: RecommendationGlobalPlannerOptions,
        repository: PostgresRecommendationRepository | None = None,
    ) -> RecommendationGlobalPlannerResult: ...


class RecommendationPersistedLifecycleSmokeSuccessorRunner(Protocol):
    def __call__(
        self,
        database: RecommendationPersistedLifecycleSmokeDatabase,
        *,
        options: RecommendationSuccessorRecomputeOptions,
        recommendation_repository: PostgresRecommendationRepository | None = None,
    ) -> RecommendationSuccessorRecomputeRunResult: ...


class RecommendationPersistedLifecycleSmokeSourceSyncRunner(Protocol):
    def __call__(
        self,
        database: RecommendationPersistedLifecycleSmokeDatabase,
        *,
        options: RecommendationSourceStatusSyncOptions,
    ) -> RecommendationSourceStatusSyncRunResult: ...


class RecommendationPersistedLifecycleSmokeChainRunner(Protocol):
    def __call__(
        self,
        repository: RecommendationChainIntegrityRepository,
        *,
        options: RecommendationSuccessorChainEvaluationOptions,
    ) -> RecommendationSuccessorChainEvaluationResult: ...


class RecommendationPersistedLifecycleSmokeOptions(BaseModel):
    as_of_time_utc: datetime = DEFAULT_BASELINE_AS_OF_TIME_UTC
    profile: RecommendationBaselineSeedProfile = "happy_path"
    reset_seed: bool = True
    pass_type: str = Field(default="4x1", min_length=1)
    mode: RecommendationMode = "single"
    strategy: RecommendationStrategy = "accuracy_first"
    unit_stake: float = Field(default=2.0, gt=0.0)
    max_budget: float | None = Field(default=20.0, gt=0.0)
    min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    candidate_limit: int = Field(default=300, ge=1, le=3_000)
    require_odds: bool = True
    competition_id: str = Field(default=BASELINE_COMPETITION_ID, min_length=1)
    model_version: str = Field(default=BASELINE_MODEL_VERSION, min_length=1)
    lock_offset_hours: int = Field(default=12, ge=0, le=168)
    successor_offset_hours: int = Field(default=19, ge=1, le=336)
    window_padding_hours: int = Field(default=1, ge=0, le=48)
    dry_run: bool = True

    @property
    def normalized_as_of_time_utc(self) -> datetime:
        return _aware_utc(self.as_of_time_utc)

    @property
    def lock_time_utc(self) -> datetime:
        return self.normalized_as_of_time_utc + timedelta(hours=self.lock_offset_hours)

    @property
    def successor_as_of_time_utc(self) -> datetime:
        return self.normalized_as_of_time_utc + timedelta(
            hours=self.successor_offset_hours
        )

    @property
    def window_start_utc(self) -> datetime:
        return self.normalized_as_of_time_utc - timedelta(
            hours=self.window_padding_hours
        )

    @property
    def window_end_utc(self) -> datetime:
        return self.successor_as_of_time_utc + timedelta(
            hours=self.window_padding_hours
        )


class RecommendationPersistedLifecycleSmokeResult(BaseModel):
    passed: bool
    dry_run: bool
    executed: bool
    as_of_time_utc: datetime
    lock_time_utc: datetime
    successor_as_of_time_utc: datetime
    window_start_utc: datetime
    window_end_utc: datetime
    pass_type: str
    mode: RecommendationMode
    strategy: RecommendationStrategy
    seed: RecommendationBaselineSeedResult | None = None
    source_global_best: RecommendationGlobalPlannerResult | None = None
    lock_mutation: RecommendationLifecycleMutationResult | None = None
    successor_recompute: RecommendationSuccessorRecomputeRunResult | None = None
    source_status_sync: RecommendationSourceStatusSyncRunResult | None = None
    successor_chain_evaluation: RecommendationSuccessorChainEvaluationResult | None = (
        None
    )
    source_recommendation_run_id: int | None = Field(default=None, gt=0)
    successor_recommendation_run_id: int | None = Field(default=None, gt=0)
    locked_fixture_ids: list[str] = Field(default_factory=list)
    continuation_fixture_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def run_recommendation_persisted_lifecycle_smoke(
    database: RecommendationPersistedLifecycleSmokeDatabase,
    *,
    options: RecommendationPersistedLifecycleSmokeOptions,
    seed_runner: RecommendationPersistedLifecycleSmokeSeedRunner | None = None,
    global_planner_runner: (
        RecommendationPersistedLifecycleSmokeGlobalPlannerRunner | None
    ) = None,
    successor_runner: RecommendationPersistedLifecycleSmokeSuccessorRunner | None = None,
    source_sync_runner: RecommendationPersistedLifecycleSmokeSourceSyncRunner | None = (
        None
    ),
    successor_chain_runner: RecommendationPersistedLifecycleSmokeChainRunner | None = (
        None
    ),
    repository: PostgresRecommendationRepository | None = None,
    chain_repository: RecommendationChainIntegrityRepository | None = None,
) -> RecommendationPersistedLifecycleSmokeResult:
    if options.dry_run:
        return _result(
            options=options,
            passed=False,
            executed=False,
            warnings=["persisted_lifecycle_smoke_requires_commit"],
        )

    recommendation_repository = repository or PostgresRecommendationRepository(database)
    chain_reader = chain_repository or PostgresRecommendationChainIntegrityRepository(
        database
    )
    seed_result = (seed_runner or run_recommendation_baseline_seed)(
        database,
        options=RecommendationBaselineSeedOptions(
            as_of_time_utc=options.normalized_as_of_time_utc,
            reset=options.reset_seed,
            profile=options.profile,
            competition_id=options.competition_id,
            model_version=options.model_version,
        ),
    )
    source_result = (global_planner_runner or run_recommendation_global_planner)(
        database,
        options=RecommendationGlobalPlannerOptions(
            as_of_time_utc=options.normalized_as_of_time_utc,
            strategy=options.strategy,
            unit_stake=options.unit_stake,
            max_budget=options.max_budget,
            pass_types=(options.pass_type,),
            modes=(options.mode,),
            min_probability=options.min_probability,
            min_data_quality_score=options.min_data_quality_score,
            candidate_limit=options.candidate_limit,
            require_odds=options.require_odds,
            competition_id=options.competition_id,
            model_version=options.model_version,
            dry_run=False,
            internal_trace_json={
                "source": "recommendation_persisted_lifecycle_smoke_v3_1",
                "smoke_step": "source_global_best",
            },
        ),
        repository=recommendation_repository,
    )
    source_run_id = _stored_run_id(source_result)
    lock_candidate = _lock_candidate(source_result)
    if source_run_id is None or lock_candidate is None:
        return _result(
            options=options,
            passed=False,
            executed=True,
            seed=seed_result,
            source_global_best=source_result,
            warnings=[
                *_prefixed_warnings("source_global_best", source_result.warnings),
                "persisted_lifecycle_smoke_source_selection_unavailable",
            ],
        )

    lock_mutation = recommendation_repository.lock_leg(
        source_run_id,
        fixture_id=lock_candidate.fixture_id,
        market_type=lock_candidate.market_type,
        outcome=lock_candidate.outcome,
        locked_at_utc=options.lock_time_utc,
        reason_code="persisted_lifecycle_smoke_locked_leg",
        metadata_json={
            "source": "recommendation_persisted_lifecycle_smoke_v3_1",
            "pass_type": options.pass_type,
            "mode": options.mode,
        },
    )
    successor_result = (successor_runner or run_recommendation_successor_recompute)(
        database,
        options=RecommendationSuccessorRecomputeOptions(
            source_recommendation_run_id=source_run_id,
            as_of_time_utc=options.successor_as_of_time_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            unit_stake=options.unit_stake,
            max_budget=options.max_budget,
            preserve_locked_legs=True,
            dry_run=False,
        ),
        recommendation_repository=recommendation_repository,
    )
    successor_run_id = successor_result.generated_recommendation_run_id
    if successor_run_id is None:
        return _result(
            options=options,
            passed=False,
            executed=True,
            seed=seed_result,
            source_global_best=source_result,
            lock_mutation=lock_mutation,
            successor_recompute=successor_result,
            source_recommendation_run_id=source_run_id,
            locked_fixture_ids=successor_result.locked_fixture_ids,
            continuation_fixture_ids=successor_result.continuation_fixture_ids,
            warnings=[
                *_prefixed_warnings("source_global_best", source_result.warnings),
                *_prefixed_warnings("successor_recompute", successor_result.warnings),
                "persisted_lifecycle_smoke_successor_unavailable",
            ],
        )

    source_sync_result = (source_sync_runner or run_recommendation_source_status_sync)(
        database,
        options=RecommendationSourceStatusSyncOptions(
            window_start_utc=options.window_start_utc,
            window_end_utc=options.window_end_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            event_time_utc=options.successor_as_of_time_utc + timedelta(minutes=1),
            dry_run=False,
            reason_code="persisted_lifecycle_smoke_source_status_sync",
        ),
    )
    chain_result = (
        successor_chain_runner or run_recommendation_successor_chain_evaluation
    )(
        chain_reader,
        options=RecommendationSuccessorChainEvaluationOptions(
            window_start_utc=options.window_start_utc,
            window_end_utc=options.window_end_utc,
            pass_type=options.pass_type,
            mode=options.mode,
            strategy=options.strategy,
            min_effective_leaf_count=1,
            min_active_edge_count=1,
            max_critical_issue_count=0,
            max_ambiguous_successor_source_count=0,
            max_source_status_sync_required_count=0,
        ),
    )
    warnings = _dedupe_strings(
        [
            *_prefixed_warnings("source_global_best", source_result.warnings),
            *_prefixed_warnings("successor_recompute", successor_result.warnings),
            *_prefixed_warnings("source_status_sync", source_sync_result.warnings),
            *_prefixed_warnings("successor_chain_evaluation", chain_result.warnings),
        ]
    )
    return _result(
        options=options,
        passed=chain_result.passed,
        executed=True,
        seed=seed_result,
        source_global_best=source_result,
        lock_mutation=lock_mutation,
        successor_recompute=successor_result,
        source_status_sync=source_sync_result,
        successor_chain_evaluation=chain_result,
        source_recommendation_run_id=source_run_id,
        successor_recommendation_run_id=successor_run_id,
        locked_fixture_ids=successor_result.locked_fixture_ids,
        continuation_fixture_ids=successor_result.continuation_fixture_ids,
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
    result = run_recommendation_persisted_lifecycle_smoke(
        database,
        options=_options_from_args(args),
    )
    output = result.model_dump_json(indent=2)
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(f"{output}\n", encoding="utf-8")
    print(output)
    if args.commit and not result.passed and not args.no_fail_process:
        raise SystemExit(1)


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Run a committed Nutmeg recommendation lifecycle smoke.",
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--as-of-time-utc", default=None)
    parser.add_argument(
        "--profile",
        choices=[
            "happy_path",
            "mixed_outcomes",
            "upset_stress",
            "adverse_odds",
            "low_quality_filter",
            "missing_result",
        ],
        default="happy_path",
    )
    parser.add_argument("--no-seed-reset", action="store_true")
    parser.add_argument("--pass-type", default="4x1")
    parser.add_argument("--mode", choices=["single", "multiple"], default="single")
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
    parser.add_argument("--competition-id", default=BASELINE_COMPETITION_ID)
    parser.add_argument("--model-version", default=BASELINE_MODEL_VERSION)
    parser.add_argument("--lock-offset-hours", type=int, default=12)
    parser.add_argument("--successor-offset-hours", type=int, default=19)
    parser.add_argument("--window-padding-hours", type=int, default=1)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationPersistedLifecycleSmokeOptions:
    return RecommendationPersistedLifecycleSmokeOptions(
        as_of_time_utc=_optional_datetime(args.as_of_time_utc)
        or DEFAULT_BASELINE_AS_OF_TIME_UTC,
        profile=args.profile,
        reset_seed=not args.no_seed_reset,
        pass_type=args.pass_type,
        mode=args.mode,
        strategy=args.strategy,
        unit_stake=args.unit_stake,
        max_budget=None if args.no_max_budget else args.max_budget,
        min_probability=args.min_probability,
        min_data_quality_score=args.min_data_quality_score,
        candidate_limit=args.candidate_limit,
        require_odds=not args.no_require_odds,
        competition_id=args.competition_id,
        model_version=args.model_version,
        lock_offset_hours=args.lock_offset_hours,
        successor_offset_hours=args.successor_offset_hours,
        window_padding_hours=args.window_padding_hours,
        dry_run=not args.commit,
    )


def _result(
    *,
    options: RecommendationPersistedLifecycleSmokeOptions,
    passed: bool,
    executed: bool,
    seed: RecommendationBaselineSeedResult | None = None,
    source_global_best: RecommendationGlobalPlannerResult | None = None,
    lock_mutation: RecommendationLifecycleMutationResult | None = None,
    successor_recompute: RecommendationSuccessorRecomputeRunResult | None = None,
    source_status_sync: RecommendationSourceStatusSyncRunResult | None = None,
    successor_chain_evaluation: RecommendationSuccessorChainEvaluationResult | None = None,
    source_recommendation_run_id: int | None = None,
    successor_recommendation_run_id: int | None = None,
    locked_fixture_ids: Sequence[str] = (),
    continuation_fixture_ids: Sequence[str] = (),
    warnings: Sequence[str] = (),
) -> RecommendationPersistedLifecycleSmokeResult:
    summary: dict[str, object] = {
        "passed": passed,
        "executed": executed,
        "dry_run": options.dry_run,
        "profile": options.profile,
        "source_recommendation_run_id": source_recommendation_run_id,
        "successor_recommendation_run_id": successor_recommendation_run_id,
        "locked_fixture_ids": list(locked_fixture_ids),
        "continuation_fixture_ids": list(continuation_fixture_ids),
        "source_status_synced": _source_status_synced(
            source_status_sync,
            source_recommendation_run_id=source_recommendation_run_id,
        ),
        "successor_chain_evaluation_passed": (
            successor_chain_evaluation.passed
            if successor_chain_evaluation is not None
            else False
        ),
        "successor_chain_effective_leaf_count": _summary_int(
            successor_chain_evaluation,
            "effective_leaf_count",
        ),
        "successor_chain_active_edge_count": _summary_int(
            successor_chain_evaluation,
            "active_edge_count",
        ),
        "successor_chain_critical_issue_count": _summary_int(
            successor_chain_evaluation,
            "chain_integrity_critical_issue_count",
        ),
        "successor_chain_source_status_sync_required_count": _summary_int(
            successor_chain_evaluation,
            "source_status_sync_required_count",
        ),
        "warning_count": len(warnings),
        "calculation_basis": "recommendation_persisted_lifecycle_smoke_v3_1",
    }
    return RecommendationPersistedLifecycleSmokeResult(
        passed=passed,
        dry_run=options.dry_run,
        executed=executed,
        as_of_time_utc=options.normalized_as_of_time_utc,
        lock_time_utc=options.lock_time_utc,
        successor_as_of_time_utc=options.successor_as_of_time_utc,
        window_start_utc=options.window_start_utc,
        window_end_utc=options.window_end_utc,
        pass_type=options.pass_type,
        mode=options.mode,
        strategy=options.strategy,
        seed=seed,
        source_global_best=source_global_best,
        lock_mutation=lock_mutation,
        successor_recompute=successor_recompute,
        source_status_sync=source_status_sync,
        successor_chain_evaluation=successor_chain_evaluation,
        source_recommendation_run_id=source_recommendation_run_id,
        successor_recommendation_run_id=successor_recommendation_run_id,
        locked_fixture_ids=list(locked_fixture_ids),
        continuation_fixture_ids=list(continuation_fixture_ids),
        warnings=list(warnings),
        summary_json=summary,
    )


def _stored_run_id(result: RecommendationGlobalPlannerResult) -> int | None:
    if result.stored_run is None:
        return None
    return result.stored_run.recommendation_run_id


def _lock_candidate(
    result: RecommendationGlobalPlannerResult,
) -> RecommendationCandidate | None:
    if result.best_option is None:
        return None
    if not result.best_option.selection.selected_candidates:
        return None
    return result.best_option.selection.selected_candidates[0].candidate


def _source_status_synced(
    result: RecommendationSourceStatusSyncRunResult | None,
    *,
    source_recommendation_run_id: int | None,
) -> bool:
    if result is None or source_recommendation_run_id is None:
        return False
    return source_recommendation_run_id in result.synced_source_recommendation_run_ids


def _summary_int(
    result: RecommendationSuccessorChainEvaluationResult | None,
    key: str,
) -> int:
    if result is None:
        return 0
    value = result.summary_json.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _prefixed_warnings(prefix: str, warnings: Sequence[str]) -> list[str]:
    return [f"{prefix}:{warning}" for warning in warnings]


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value in result:
            continue
        result.append(value)
    return result


def _optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
