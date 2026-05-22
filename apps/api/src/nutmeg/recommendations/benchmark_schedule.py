from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.config import get_settings
from nutmeg.database import PsycopgSyncDatabaseExecutor
from nutmeg.recommendations.benchmark_runner import (
    DEFAULT_BENCHMARK_BUDGETS,
    DEFAULT_BENCHMARK_MODES,
    DEFAULT_BENCHMARK_PASS_TYPES,
    DEFAULT_BENCHMARK_REQUESTED_BY,
    RecommendationBenchmarkDatabaseExecutor,
    RecommendationBenchmarkOptions,
    RecommendationBenchmarkRunResult,
    run_recommendation_benchmark,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type RecommendationBenchmarkScheduleCadence = Literal["once", "daily", "weekly"]


class RecommendationBenchmarkScheduleRunner(Protocol):
    def __call__(
        self,
        database: RecommendationBenchmarkDatabaseExecutor,
        *,
        options: RecommendationBenchmarkOptions,
    ) -> RecommendationBenchmarkRunResult: ...


class RecommendationBenchmarkScheduleOptions(BaseModel):
    schedule_name: str = Field(default="default", min_length=1, max_length=80)
    cadence: RecommendationBenchmarkScheduleCadence = "daily"
    run_at_utc: datetime | None = None
    window_count: int = Field(default=1, ge=1, le=52)
    lookback_hours: int = Field(default=24, ge=1, le=720)
    pass_types: tuple[str, ...] = DEFAULT_BENCHMARK_PASS_TYPES
    modes: tuple[RecommendationMode, ...] = DEFAULT_BENCHMARK_MODES
    max_budgets: tuple[float, ...] = DEFAULT_BENCHMARK_BUDGETS
    strategy: RecommendationStrategy = "accuracy_first"
    unit_stake: float = Field(default=2.0, gt=0.0)
    min_probability: float = Field(default=0.20, ge=0.0, le=1.0)
    min_data_quality_score: float = Field(default=50.0, ge=0.0, le=100.0)
    require_odds: bool = True
    candidate_limit: int = Field(default=300, ge=1, le=3_000)
    competition_id: str | None = Field(default=None, min_length=1)
    model_version: str | None = Field(default=None, min_length=1)
    provider_name: str | None = Field(default=None, min_length=1)
    canonical_fixture_id: str | None = Field(default=None, min_length=1)
    run_global_best: bool = True
    run_prematch_pipeline: bool = False
    run_core_replay: bool = True
    run_chain_integrity: bool = True
    run_successor_chain_evaluation: bool = True
    dry_run: bool = True
    save_report: bool = False
    save_pipeline_audit: bool = False
    requested_by: str | None = DEFAULT_BENCHMARK_REQUESTED_BY
    provider_observation_limit: int = Field(default=2_000, ge=1, le=5_000)
    source_run_limit: int = Field(default=100, ge=1, le=2_000)
    incident_limit: int = Field(default=1_000, ge=1, le=5_000)
    report_limit: int = Field(default=200, ge=1, le=2_000)
    replay_limit: int = Field(default=200, ge=1, le=2_000)
    chain_integrity_limit: int = Field(default=500, ge=1, le=5_000)
    continue_on_error: bool = True

    @property
    def normalized_run_at_utc(self) -> datetime:
        return _aware_utc(self.run_at_utc or datetime.now(UTC))


class RecommendationBenchmarkScheduleRunResult(BaseModel):
    schedule_key: str
    schedule_name: str
    cadence: RecommendationBenchmarkScheduleCadence
    run_at_utc: datetime
    generated_as_of_times_utc: list[datetime] = Field(default_factory=list)
    dry_run: bool
    save_report: bool
    benchmark: RecommendationBenchmarkRunResult
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_scheduled_benchmark_as_of_times(
    options: RecommendationBenchmarkScheduleOptions,
) -> tuple[datetime, ...]:
    run_at = options.normalized_run_at_utc
    if options.cadence == "once":
        return (run_at,)
    step = timedelta(days=1 if options.cadence == "daily" else 7)
    return tuple(run_at - (step * offset) for offset in reversed(range(options.window_count)))


def run_recommendation_benchmark_schedule(
    database: RecommendationBenchmarkDatabaseExecutor,
    *,
    options: RecommendationBenchmarkScheduleOptions,
    benchmark_runner: RecommendationBenchmarkScheduleRunner | None = None,
) -> RecommendationBenchmarkScheduleRunResult:
    as_of_times = build_scheduled_benchmark_as_of_times(options)
    run_at = as_of_times[-1]
    benchmark_options = RecommendationBenchmarkOptions(
        as_of_times_utc=as_of_times,
        lookback_hours=options.lookback_hours,
        pass_types=options.pass_types,
        modes=options.modes,
        max_budgets=options.max_budgets,
        strategy=options.strategy,
        unit_stake=options.unit_stake,
        min_probability=options.min_probability,
        min_data_quality_score=options.min_data_quality_score,
        require_odds=options.require_odds,
        candidate_limit=options.candidate_limit,
        competition_id=options.competition_id,
        model_version=options.model_version,
        provider_name=options.provider_name,
        canonical_fixture_id=options.canonical_fixture_id,
        run_global_best=options.run_global_best,
        run_prematch_pipeline=options.run_prematch_pipeline,
        run_core_replay=options.run_core_replay,
        run_chain_integrity=options.run_chain_integrity,
        run_successor_chain_evaluation=options.run_successor_chain_evaluation,
        dry_run=options.dry_run,
        save_report=options.save_report,
        save_pipeline_audit=options.save_pipeline_audit,
        requested_by=options.requested_by,
        provider_observation_limit=options.provider_observation_limit,
        source_run_limit=options.source_run_limit,
        incident_limit=options.incident_limit,
        report_limit=options.report_limit,
        replay_limit=options.replay_limit,
        chain_integrity_limit=options.chain_integrity_limit,
        continue_on_error=options.continue_on_error,
    )
    runner = benchmark_runner or run_recommendation_benchmark
    benchmark = runner(database, options=benchmark_options)
    warnings = list(benchmark.warnings)
    schedule_key = _schedule_key(options)
    summary = {
        "schedule_name": options.schedule_name,
        "schedule_key": schedule_key,
        "cadence": options.cadence,
        "run_at_utc": run_at.isoformat(),
        "window_count": len(as_of_times),
        "generated_as_of_times": [value.isoformat() for value in as_of_times],
        "benchmark_key": benchmark.benchmark_key,
        "benchmark_scenario_count": benchmark.scenario_count,
        "benchmark_completed_count": benchmark.completed_count,
        "benchmark_failed_count": benchmark.failed_count,
        "stored_report_id": (
            benchmark.stored_report.recommendation_benchmark_run_id
            if benchmark.stored_report is not None
            else None
        ),
        "history_status": benchmark.summary_json.get("history_status"),
        "dry_run": options.dry_run,
        "save_report": options.save_report,
        "calculation_basis": "recommendation_benchmark_schedule_v3_1",
    }
    return RecommendationBenchmarkScheduleRunResult(
        schedule_key=schedule_key,
        schedule_name=options.schedule_name,
        cadence=options.cadence,
        run_at_utc=run_at,
        generated_as_of_times_utc=list(as_of_times),
        dry_run=options.dry_run,
        save_report=options.save_report,
        benchmark=benchmark,
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
    result = run_recommendation_benchmark_schedule(
        database,
        options=_options_from_args(args),
    )
    print(result.model_dump_json(indent=2))


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Run a cron-friendly Nutmeg recommendation benchmark schedule."
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument("--schedule-name", default="default")
    parser.add_argument(
        "--cadence",
        choices=["once", "daily", "weekly"],
        default="daily",
    )
    parser.add_argument("--run-at-utc", default=None)
    parser.add_argument("--window-count", type=int, default=1)
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--pass-types", default=",".join(DEFAULT_BENCHMARK_PASS_TYPES))
    parser.add_argument("--modes", default=",".join(DEFAULT_BENCHMARK_MODES))
    parser.add_argument(
        "--budgets",
        default=",".join(_budget_label(v) for v in DEFAULT_BENCHMARK_BUDGETS),
    )
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
    parser.add_argument("--competition-id", default=None)
    parser.add_argument("--model-version", default=None)
    parser.add_argument("--provider-name", default=None)
    parser.add_argument("--canonical-fixture-id", default=None)
    parser.add_argument("--requested-by", default=DEFAULT_BENCHMARK_REQUESTED_BY)
    parser.add_argument("--provider-observation-limit", type=int, default=2_000)
    parser.add_argument("--source-run-limit", type=int, default=100)
    parser.add_argument("--incident-limit", type=int, default=1_000)
    parser.add_argument("--report-limit", type=int, default=200)
    parser.add_argument("--replay-limit", type=int, default=200)
    parser.add_argument("--chain-integrity-limit", type=int, default=500)
    parser.add_argument("--include-prematch-pipeline", action="store_true")
    parser.add_argument("--skip-global-best", action="store_true")
    parser.add_argument("--skip-core-replay", action="store_true")
    parser.add_argument("--skip-chain-integrity", action="store_true")
    parser.add_argument("--skip-successor-chain-evaluation", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--save-report", action="store_true")
    parser.add_argument("--save-audit", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationBenchmarkScheduleOptions:
    return RecommendationBenchmarkScheduleOptions(
        schedule_name=args.schedule_name,
        cadence=args.cadence,
        run_at_utc=_datetime(args.run_at_utc) if args.run_at_utc else None,
        window_count=args.window_count,
        lookback_hours=args.lookback_hours,
        pass_types=tuple(_csv(args.pass_types)),
        modes=tuple(_mode(value) for value in _csv(args.modes)),
        max_budgets=tuple(_positive_float(value) for value in _csv(args.budgets)),
        strategy=args.strategy,
        unit_stake=args.unit_stake,
        min_probability=args.min_probability,
        min_data_quality_score=args.min_data_quality_score,
        require_odds=not args.no_require_odds,
        candidate_limit=args.candidate_limit,
        competition_id=args.competition_id,
        model_version=args.model_version,
        provider_name=args.provider_name,
        canonical_fixture_id=args.canonical_fixture_id,
        run_global_best=not args.skip_global_best,
        run_prematch_pipeline=args.include_prematch_pipeline,
        run_core_replay=not args.skip_core_replay,
        run_chain_integrity=not args.skip_chain_integrity,
        run_successor_chain_evaluation=(
            not args.skip_chain_integrity and not args.skip_successor_chain_evaluation
        ),
        dry_run=not args.commit,
        save_report=args.save_report,
        save_pipeline_audit=args.save_audit,
        requested_by=args.requested_by,
        provider_observation_limit=args.provider_observation_limit,
        source_run_limit=args.source_run_limit,
        incident_limit=args.incident_limit,
        report_limit=args.report_limit,
        replay_limit=args.replay_limit,
        chain_integrity_limit=args.chain_integrity_limit,
        continue_on_error=not args.stop_on_error,
    )


def _schedule_key(options: RecommendationBenchmarkScheduleOptions) -> str:
    return f"recommendation_benchmark_schedule:{options.schedule_name}:{options.cadence}"


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
