from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from nutmeg.config import get_settings
from nutmeg.database import DatabaseRow, PsycopgSyncDatabaseExecutor, QueryParams
from nutmeg.recommendations.baseline_seed import (
    BASELINE_COMPETITION_ID,
    BASELINE_MODEL_VERSION,
    DEFAULT_BASELINE_SEED_PROFILE,
    RecommendationBaselineSeedOptions,
    RecommendationBaselineSeedProfile,
    RecommendationBaselineSeedResult,
    run_recommendation_baseline_seed,
)
from nutmeg.recommendations.benchmark_runner import (
    DEFAULT_BENCHMARK_BUDGETS,
    DEFAULT_BENCHMARK_MODES,
    DEFAULT_BENCHMARK_PASS_TYPES,
    DEFAULT_BENCHMARK_REQUESTED_BY,
    RecommendationBenchmarkOptions,
    RecommendationBenchmarkRunResult,
    run_recommendation_benchmark,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy


class RecommendationBenchmarkCoreReplaySeedDatabase(Protocol):
    def execute(self, query: str, params: QueryParams) -> None:
        """Execute deterministic seed cleanup/write statements."""

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read rows for the committed benchmark seed run."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute writes with RETURNING and return one row."""


class RecommendationBenchmarkCoreReplayBaselineSeedRunner(Protocol):
    def __call__(
        self,
        database: RecommendationBenchmarkCoreReplaySeedDatabase,
        *,
        options: RecommendationBaselineSeedOptions | None = None,
    ) -> RecommendationBaselineSeedResult: ...


class RecommendationBenchmarkCoreReplayBenchmarkRunner(Protocol):
    def __call__(
        self,
        database: RecommendationBenchmarkCoreReplaySeedDatabase,
        *,
        options: RecommendationBenchmarkOptions,
    ) -> RecommendationBenchmarkRunResult: ...


class RecommendationBenchmarkCoreReplaySeedOptions(BaseModel):
    as_of_time_utc: datetime
    profile: RecommendationBaselineSeedProfile = DEFAULT_BASELINE_SEED_PROFILE
    reset_seed: bool = True
    lookback_hours: int = Field(default=24, ge=1, le=720)
    pass_types: tuple[str, ...] = Field(default=DEFAULT_BENCHMARK_PASS_TYPES, min_length=1)
    modes: tuple[RecommendationMode, ...] = Field(
        default=DEFAULT_BENCHMARK_MODES, min_length=1
    )
    max_budgets: tuple[float, ...] = Field(
        default=DEFAULT_BENCHMARK_BUDGETS, min_length=1
    )
    seed_budget: float | None = Field(default=None, gt=0.0)
    strategy: RecommendationStrategy = "accuracy_first"
    unit_stake: float = Field(default=2.0, gt=0.0)
    min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    require_odds: bool = True
    candidate_limit: int = Field(default=300, ge=1, le=3_000)
    competition_id: str = Field(default=BASELINE_COMPETITION_ID, min_length=1)
    model_version: str = Field(default=BASELINE_MODEL_VERSION, min_length=1)
    requested_by: str | None = DEFAULT_BENCHMARK_REQUESTED_BY

    @property
    def normalized_as_of_time_utc(self) -> datetime:
        return _aware_utc(self.as_of_time_utc)


class RecommendationBenchmarkCoreReplaySeedResult(BaseModel):
    passed: bool
    as_of_time_utc: datetime
    profile: RecommendationBaselineSeedProfile
    reset_seed: bool
    seed_budget: float
    seed: RecommendationBaselineSeedResult
    benchmark: RecommendationBenchmarkRunResult
    stored_recommendation_run_ids: list[int] = Field(default_factory=list)
    expected_scenario_count: int = Field(ge=0)
    stored_run_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def run_recommendation_benchmark_core_replay_seed(
    database: RecommendationBenchmarkCoreReplaySeedDatabase,
    *,
    options: RecommendationBenchmarkCoreReplaySeedOptions,
    seed_runner: RecommendationBenchmarkCoreReplayBaselineSeedRunner | None = None,
    benchmark_runner: RecommendationBenchmarkCoreReplayBenchmarkRunner | None = None,
) -> RecommendationBenchmarkCoreReplaySeedResult:
    seed_budget = _seed_budget(options)
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
    benchmark_result = (benchmark_runner or run_recommendation_benchmark)(
        database,
        options=RecommendationBenchmarkOptions(
            as_of_times_utc=(options.normalized_as_of_time_utc,),
            lookback_hours=options.lookback_hours,
            pass_types=options.pass_types,
            modes=options.modes,
            max_budgets=(seed_budget,),
            strategy=options.strategy,
            unit_stake=options.unit_stake,
            min_probability=options.min_probability,
            min_data_quality_score=options.min_data_quality_score,
            require_odds=options.require_odds,
            candidate_limit=options.candidate_limit,
            competition_id=options.competition_id,
            model_version=options.model_version,
            run_global_best=True,
            run_prematch_pipeline=False,
            run_core_replay=False,
            run_chain_integrity=False,
            run_successor_chain_evaluation=False,
            dry_run=False,
            save_report=False,
            save_pipeline_audit=False,
            requested_by=options.requested_by,
            continue_on_error=True,
        ),
    )
    stored_run_ids = _stored_run_ids(benchmark_result)
    warnings = _warnings(
        benchmark_result,
        stored_run_count=len(stored_run_ids),
    )
    passed = (
        benchmark_result.failed_count == 0
        and len(stored_run_ids) >= benchmark_result.scenario_count
    )
    return RecommendationBenchmarkCoreReplaySeedResult(
        passed=passed,
        as_of_time_utc=options.normalized_as_of_time_utc,
        profile=options.profile,
        reset_seed=options.reset_seed,
        seed_budget=seed_budget,
        seed=seed_result,
        benchmark=benchmark_result,
        stored_recommendation_run_ids=stored_run_ids,
        expected_scenario_count=benchmark_result.scenario_count,
        stored_run_count=len(stored_run_ids),
        warnings=warnings,
        summary_json={
            "passed": passed,
            "as_of_time_utc": options.normalized_as_of_time_utc.isoformat(),
            "profile": options.profile,
            "reset_seed": options.reset_seed,
            "seed_budget": seed_budget,
            "competition_id": options.competition_id,
            "model_version": options.model_version,
            "fixture_count": seed_result.fixture_count,
            "result_count": seed_result.result_count,
            "benchmark_key": benchmark_result.benchmark_key,
            "benchmark_scenario_count": benchmark_result.scenario_count,
            "benchmark_completed_count": benchmark_result.completed_count,
            "benchmark_failed_count": benchmark_result.failed_count,
            "stored_recommendation_run_count": len(stored_run_ids),
            "stored_recommendation_run_ids": stored_run_ids,
            "warning_count": len(warnings),
            "calculation_basis": "recommendation_benchmark_core_replay_seed_v3_1",
        },
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
    result = run_recommendation_benchmark_core_replay_seed(
        database,
        options=_options_from_args(args),
    )
    output = result.model_dump_json(indent=2)
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(f"{output}\n", encoding="utf-8")
    print(output)
    if not result.passed and not args.no_fail_process:
        raise SystemExit(1)


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Seed deterministic committed recommendation runs for core replay.",
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--as-of-time-utc", required=True)
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
        default=DEFAULT_BASELINE_SEED_PROFILE,
    )
    parser.add_argument("--no-seed-reset", action="store_true")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--pass-types", default=",".join(DEFAULT_BENCHMARK_PASS_TYPES))
    parser.add_argument("--modes", default=",".join(DEFAULT_BENCHMARK_MODES))
    parser.add_argument(
        "--budgets",
        default=",".join(_budget_label(value) for value in DEFAULT_BENCHMARK_BUDGETS),
    )
    parser.add_argument("--seed-budget", type=float, default=None)
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
    parser.add_argument("--min-probability", type=float, default=0.20)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--candidate-limit", type=int, default=300)
    parser.add_argument("--no-require-odds", action="store_true")
    parser.add_argument("--competition-id", default=BASELINE_COMPETITION_ID)
    parser.add_argument("--model-version", default=BASELINE_MODEL_VERSION)
    parser.add_argument("--requested-by", default=DEFAULT_BENCHMARK_REQUESTED_BY)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationBenchmarkCoreReplaySeedOptions:
    return RecommendationBenchmarkCoreReplaySeedOptions(
        as_of_time_utc=_datetime(args.as_of_time_utc),
        profile=args.profile,
        reset_seed=not args.no_seed_reset,
        lookback_hours=args.lookback_hours,
        pass_types=tuple(_csv(args.pass_types)),
        modes=tuple(_mode(value) for value in _csv(args.modes)),
        max_budgets=tuple(_positive_float(value) for value in _csv(args.budgets)),
        seed_budget=args.seed_budget,
        strategy=args.strategy,
        unit_stake=args.unit_stake,
        min_probability=args.min_probability,
        min_data_quality_score=args.min_data_quality_score,
        require_odds=not args.no_require_odds,
        candidate_limit=args.candidate_limit,
        competition_id=args.competition_id,
        model_version=args.model_version,
        requested_by=args.requested_by,
    )


def _stored_run_ids(result: RecommendationBenchmarkRunResult) -> list[int]:
    stored_run_ids: list[int] = []
    for scenario in result.scenarios:
        validation = scenario.validation
        if validation is None:
            continue
        value = validation.summary_json.get("global_best_stored_run_id")
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int | float | str):
            stored_run_ids.append(int(value))
    return list(dict.fromkeys(stored_run_ids))


def _warnings(
    result: RecommendationBenchmarkRunResult,
    *,
    stored_run_count: int,
) -> list[str]:
    warnings = list(result.warnings)
    if result.failed_count:
        warnings.append("benchmark_seed_has_failed_scenarios")
    if stored_run_count < result.scenario_count:
        warnings.append("benchmark_seed_missing_committed_recommendation_runs")
    return _dedupe_strings(warnings)


def _seed_budget(options: RecommendationBenchmarkCoreReplaySeedOptions) -> float:
    if options.seed_budget is not None:
        return options.seed_budget
    return options.max_budgets[0]


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _mode(value: str) -> RecommendationMode:
    if value not in {"single", "multiple"}:
        raise ValueError(f"unknown benchmark mode: {value}")
    return value  # type: ignore[return-value]


def _positive_float(value: str) -> float:
    result = float(value)
    if result <= 0:
        raise ValueError("benchmark budgets must be positive")
    return result


def _datetime(value: str) -> datetime:
    return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _budget_label(value: float) -> str:
    return f"{value:g}"


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value in result:
            continue
        result.append(value)
    return result
