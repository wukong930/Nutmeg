from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from json import dumps, loads
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from nutmeg.config import get_settings
from nutmeg.database import DatabaseRow, PsycopgSyncDatabaseExecutor, QueryParams
from nutmeg.recommendations.core_validation_runner import (
    RecommendationCoreValidationDatabaseExecutor,
    RecommendationCoreValidationOptions,
    RecommendationCoreValidationRunResult,
    run_recommendation_core_validation,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

DEFAULT_BENCHMARK_PASS_TYPES = ("1x1", "2x1", "4x1", "6x1", "8x1")
DEFAULT_BENCHMARK_MODES: tuple[RecommendationMode, ...] = ("single", "multiple")
DEFAULT_BENCHMARK_BUDGETS = (10.0, 20.0, 50.0)
DEFAULT_BENCHMARK_REQUESTED_BY = "recommendation-benchmark-cli"

type RecommendationBenchmarkScenarioStatus = Literal["completed", "failed"]

INSERT_RECOMMENDATION_BENCHMARK_RUN_QUERY = """
INSERT INTO recommendation_benchmark_runs (
  benchmark_key,
  dry_run,
  strategy,
  scenario_count,
  completed_count,
  failed_count,
  as_of_times_json,
  pass_types_json,
  modes_json,
  budgets_json,
  global_best_selected_count,
  core_replay_ready_count,
  core_replay_total_run_count,
  core_replay_total_settled_run_count,
  final_hit_sample_size,
  final_hit_count,
  average_core_replay_roi,
  warning_count,
  history_comparison_json,
  summary_json,
  warnings_json,
  result_json,
  source
) VALUES (
  %(benchmark_key)s,
  %(dry_run)s,
  %(strategy)s,
  %(scenario_count)s,
  %(completed_count)s,
  %(failed_count)s,
  %(as_of_times_json)s::jsonb,
  %(pass_types_json)s::jsonb,
  %(modes_json)s::jsonb,
  %(budgets_json)s::jsonb,
  %(global_best_selected_count)s,
  %(core_replay_ready_count)s,
  %(core_replay_total_run_count)s,
  %(core_replay_total_settled_run_count)s,
  %(final_hit_sample_size)s,
  %(final_hit_count)s,
  %(average_core_replay_roi)s,
  %(warning_count)s,
  %(history_comparison_json)s::jsonb,
  %(summary_json)s::jsonb,
  %(warnings_json)s::jsonb,
  %(result_json)s::jsonb,
  %(source)s
)
RETURNING
  recommendation_benchmark_run_id,
  benchmark_key,
  dry_run,
  strategy,
  scenario_count,
  completed_count,
  failed_count,
  global_best_selected_count,
  core_replay_ready_count,
  core_replay_total_run_count,
  core_replay_total_settled_run_count,
  final_hit_sample_size,
  final_hit_count,
  average_core_replay_roi,
  warning_count,
  history_comparison_json,
  summary_json,
  created_at
"""

LIST_RECENT_RECOMMENDATION_BENCHMARK_RUNS_QUERY = """
SELECT
  recommendation_benchmark_run_id,
  benchmark_key,
  dry_run,
  strategy,
  scenario_count,
  completed_count,
  failed_count,
  global_best_selected_count,
  core_replay_ready_count,
  core_replay_total_run_count,
  core_replay_total_settled_run_count,
  final_hit_sample_size,
  final_hit_count,
  average_core_replay_roi,
  warning_count,
  history_comparison_json,
  summary_json,
  created_at
FROM recommendation_benchmark_runs
WHERE benchmark_key = %(benchmark_key)s
ORDER BY created_at DESC, recommendation_benchmark_run_id DESC
LIMIT %(limit)s
"""

LIST_RECOMMENDATION_BENCHMARK_HISTORY_QUERY = """
SELECT
  recommendation_benchmark_run_id,
  benchmark_key,
  dry_run,
  strategy,
  scenario_count,
  completed_count,
  failed_count,
  global_best_selected_count,
  core_replay_ready_count,
  core_replay_total_run_count,
  core_replay_total_settled_run_count,
  final_hit_sample_size,
  final_hit_count,
  average_core_replay_roi,
  warning_count,
  history_comparison_json,
  summary_json,
  created_at
FROM recommendation_benchmark_runs
WHERE (%(benchmark_key)s::text IS NULL OR benchmark_key = %(benchmark_key)s::text)
  AND (%(strategy)s::text IS NULL OR strategy = %(strategy)s::text)
ORDER BY created_at DESC, recommendation_benchmark_run_id DESC
LIMIT %(limit)s
"""


class RecommendationBenchmarkDatabaseExecutor(Protocol):
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        """Read rows for recommendation benchmark runners."""

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        """Execute optional writes when benchmark scenarios are explicitly committed."""


class RecommendationBenchmarkValidationRunner(Protocol):
    def __call__(
        self,
        database: RecommendationCoreValidationDatabaseExecutor,
        *,
        options: RecommendationCoreValidationOptions,
    ) -> RecommendationCoreValidationRunResult: ...


class RecommendationBenchmarkRunRepository(Protocol):
    def list_recent(
        self,
        *,
        benchmark_key: str,
        limit: int = 1,
    ) -> list[StoredRecommendationBenchmarkRun]:
        """List recent persisted runs for the same benchmark matrix."""

    def save_run(
        self,
        result: RecommendationBenchmarkRunResult,
        *,
        source: str = "recommendation_benchmark_runner_v3_1",
    ) -> StoredRecommendationBenchmarkRun:
        """Persist a recommendation benchmark report."""


class RecommendationBenchmarkScenario(BaseModel):
    scenario_key: str
    as_of_time_utc: datetime
    lookback_hours: int = Field(ge=1, le=720)
    pass_type: str
    mode: RecommendationMode
    max_budget: float = Field(gt=0.0)


class RecommendationBenchmarkOptions(BaseModel):
    as_of_times_utc: tuple[datetime, ...] = Field(default_factory=tuple)
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
    def normalized_as_of_times_utc(self) -> tuple[datetime, ...]:
        if not self.as_of_times_utc:
            return (_aware_utc(datetime.now(UTC)),)
        return tuple(_aware_utc(value) for value in self.as_of_times_utc)


class RecommendationBenchmarkScenarioResult(BaseModel):
    scenario: RecommendationBenchmarkScenario
    status: RecommendationBenchmarkScenarioStatus
    validation: RecommendationCoreValidationRunResult | None = None
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metrics_json: dict[str, object] = Field(default_factory=dict)


class RecommendationBenchmarkRunResult(BaseModel):
    benchmark_key: str
    dry_run: bool
    strategy: RecommendationStrategy
    scenario_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    scenarios: list[RecommendationBenchmarkScenarioResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    history_comparison_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)
    stored_report: StoredRecommendationBenchmarkRun | None = None


class StoredRecommendationBenchmarkRun(BaseModel):
    recommendation_benchmark_run_id: int = Field(gt=0)
    benchmark_key: str
    dry_run: bool
    strategy: RecommendationStrategy
    scenario_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    global_best_selected_count: int = Field(ge=0)
    core_replay_ready_count: int = Field(ge=0)
    core_replay_total_run_count: int = Field(ge=0)
    core_replay_total_settled_run_count: int = Field(ge=0)
    final_hit_sample_size: int = Field(ge=0)
    final_hit_count: int = Field(ge=0)
    average_core_replay_roi: float | None = None
    warning_count: int = Field(ge=0)
    history_comparison_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class PostgresRecommendationBenchmarkRunRepository:
    def __init__(self, database: RecommendationBenchmarkDatabaseExecutor) -> None:
        self.database = database

    def list_recent(
        self,
        *,
        benchmark_key: str,
        limit: int = 1,
    ) -> list[StoredRecommendationBenchmarkRun]:
        rows = self.database.fetch_all(
            LIST_RECENT_RECOMMENDATION_BENCHMARK_RUNS_QUERY,
            {"benchmark_key": benchmark_key, "limit": max(1, limit)},
        )
        return [_stored_run_from_row(row) for row in rows]

    def list_history(
        self,
        *,
        benchmark_key: str | None = None,
        strategy: RecommendationStrategy | None = None,
        limit: int = 20,
    ) -> list[StoredRecommendationBenchmarkRun]:
        rows = self.database.fetch_all(
            LIST_RECOMMENDATION_BENCHMARK_HISTORY_QUERY,
            {
                "benchmark_key": benchmark_key,
                "strategy": strategy,
                "limit": max(1, min(limit, 200)),
            },
        )
        return [_stored_run_from_row(row) for row in rows]

    def save_run(
        self,
        result: RecommendationBenchmarkRunResult,
        *,
        source: str = "recommendation_benchmark_runner_v3_1",
    ) -> StoredRecommendationBenchmarkRun:
        summary = result.summary_json
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_BENCHMARK_RUN_QUERY,
                {
                    "benchmark_key": result.benchmark_key,
                    "dry_run": result.dry_run,
                    "strategy": result.strategy,
                    "scenario_count": result.scenario_count,
                    "completed_count": result.completed_count,
                    "failed_count": result.failed_count,
                    "as_of_times_json": _json(summary.get("as_of_times", [])),
                    "pass_types_json": _json(summary.get("pass_types", [])),
                    "modes_json": _json(summary.get("modes", [])),
                    "budgets_json": _json(summary.get("budgets", [])),
                    "global_best_selected_count": _summary_int(
                        summary, "global_best_selected_count"
                    ),
                    "core_replay_ready_count": _summary_int(
                        summary, "core_replay_ready_count"
                    ),
                    "core_replay_total_run_count": _summary_int(
                        summary, "core_replay_total_run_count"
                    ),
                    "core_replay_total_settled_run_count": _summary_int(
                        summary, "core_replay_total_settled_run_count"
                    ),
                    "final_hit_sample_size": _summary_int(summary, "final_hit_sample_size"),
                    "final_hit_count": _summary_int(summary, "final_hit_count"),
                    "average_core_replay_roi": _optional_float(
                        summary.get("average_core_replay_roi")
                    ),
                    "warning_count": _summary_int(result.summary_json, "warning_count"),
                    "history_comparison_json": _json(result.history_comparison_json),
                    "summary_json": _json(result.summary_json),
                    "warnings_json": _json(result.warnings),
                    "result_json": _json(result.model_dump(mode="json")),
                    "source": source,
                },
            )
        )
        return _stored_run_from_row(row)


def run_recommendation_benchmark(
    database: RecommendationBenchmarkDatabaseExecutor,
    *,
    options: RecommendationBenchmarkOptions,
    validation_runner: RecommendationBenchmarkValidationRunner | None = None,
    benchmark_repository: RecommendationBenchmarkRunRepository | None = None,
) -> RecommendationBenchmarkRunResult:
    scenarios = build_recommendation_benchmark_scenarios(options)
    runner = validation_runner or run_recommendation_core_validation
    results: list[RecommendationBenchmarkScenarioResult] = []
    warnings: list[str] = []

    for scenario in scenarios:
        validation_options = _validation_options(options, scenario=scenario)
        try:
            validation = runner(database, options=validation_options)
        except Exception as exc:
            if not options.continue_on_error:
                raise
            scenario_result = RecommendationBenchmarkScenarioResult(
                scenario=scenario,
                status="failed",
                error_message=str(exc),
                warnings=[f"scenario_failed:{scenario.scenario_key}"],
                metrics_json={
                    "calculation_basis": "recommendation_benchmark_scenario_v3_1",
                    "error_type": type(exc).__name__,
                },
            )
        else:
            scenario_result = RecommendationBenchmarkScenarioResult(
                scenario=scenario,
                status="completed",
                validation=validation,
                warnings=validation.warnings,
                metrics_json=_scenario_metrics(validation),
            )
        results.append(scenario_result)
        warnings.extend(scenario_result.warnings)

    warnings = _dedupe_strings(warnings)
    summary = _benchmark_summary(
        options=options,
        scenarios=scenarios,
        results=results,
        warning_count=len(warnings),
    )
    result = RecommendationBenchmarkRunResult(
        benchmark_key=_benchmark_key(options, scenarios=scenarios),
        dry_run=options.dry_run,
        strategy=options.strategy,
        scenario_count=len(scenarios),
        completed_count=sum(1 for result in results if result.status == "completed"),
        failed_count=sum(1 for result in results if result.status == "failed"),
        scenarios=results,
        warnings=warnings,
        summary_json=summary,
    )
    if not options.save_report:
        return result

    repository = benchmark_repository or PostgresRecommendationBenchmarkRunRepository(database)
    previous_runs = repository.list_recent(benchmark_key=result.benchmark_key, limit=1)
    comparison = build_recommendation_benchmark_history_comparison(
        result,
        previous=previous_runs[0] if previous_runs else None,
    )
    result = result.model_copy(
        update={
            "history_comparison_json": comparison,
            "summary_json": {
                **result.summary_json,
                "history_status": comparison["status"],
                "previous_benchmark_run_id": comparison["previous_benchmark_run_id"],
            },
        }
    )
    stored = repository.save_run(result)
    return result.model_copy(update={"stored_report": stored})


def build_recommendation_benchmark_scenarios(
    options: RecommendationBenchmarkOptions,
) -> list[RecommendationBenchmarkScenario]:
    scenarios: list[RecommendationBenchmarkScenario] = []
    for as_of_time in options.normalized_as_of_times_utc:
        for budget in options.max_budgets:
            for pass_type in options.pass_types:
                for mode in _modes_for_pass_type(pass_type, options.modes):
                    scenarios.append(
                        RecommendationBenchmarkScenario(
                            scenario_key=_scenario_key(
                                as_of_time=as_of_time,
                                lookback_hours=options.lookback_hours,
                                pass_type=pass_type,
                                mode=mode,
                                max_budget=budget,
                            ),
                            as_of_time_utc=as_of_time,
                            lookback_hours=options.lookback_hours,
                            pass_type=pass_type,
                            mode=mode,
                            max_budget=budget,
                        )
                    )
    return scenarios


def build_recommendation_benchmark_history_comparison(
    current: RecommendationBenchmarkRunResult,
    *,
    previous: StoredRecommendationBenchmarkRun | None,
) -> dict[str, object]:
    if previous is None:
        return {
            "status": "baseline",
            "previous_benchmark_run_id": None,
            "calculation_basis": "recommendation_benchmark_history_comparison_v3_1",
        }
    current_summary = current.summary_json
    previous_summary = previous.summary_json
    current_hit_rate = _hit_rate(current_summary)
    previous_hit_rate = _hit_rate(previous_summary)
    current_roi = _optional_float(current_summary.get("average_core_replay_roi"))
    previous_roi = _optional_float(previous_summary.get("average_core_replay_roi"))
    current_upset_capture_rate = _upset_capture_rate(current_summary)
    previous_upset_capture_rate = _upset_capture_rate(previous_summary)
    deltas: dict[str, object] = {
        "final_hit_rate_delta": _optional_delta(current_hit_rate, previous_hit_rate),
        "average_core_replay_roi_delta": _optional_delta(current_roi, previous_roi),
        "upset_capture_rate_delta": _optional_delta(
            current_upset_capture_rate,
            previous_upset_capture_rate,
        ),
        "core_replay_ready_count_delta": (
            _summary_int(current_summary, "core_replay_ready_count")
            - _summary_int(previous_summary, "core_replay_ready_count")
        ),
        "ambiguous_successor_source_count_delta": (
            _summary_count(
                current_summary,
                count_key="ambiguous_successor_source_count",
                ids_key="ambiguous_successor_source_recommendation_run_ids",
            )
            - _summary_count(
                previous_summary,
                count_key="ambiguous_successor_source_count",
                ids_key="ambiguous_successor_source_recommendation_run_ids",
            )
        ),
        "stale_recommendation_count_delta": (
            _summary_count(
                current_summary,
                count_key="stale_recommendation_count",
                ids_key="stale_recommendation_run_ids",
            )
            - _summary_count(
                previous_summary,
                count_key="stale_recommendation_count",
                ids_key="stale_recommendation_run_ids",
            )
        ),
        "successor_recompute_required_count_delta": (
            _summary_count(
                current_summary,
                count_key="successor_recompute_required_count",
                ids_key="successor_recompute_required_recommendation_run_ids",
            )
            - _summary_count(
                previous_summary,
                count_key="successor_recompute_required_count",
                ids_key="successor_recompute_required_recommendation_run_ids",
            )
        ),
        "failed_count_delta": (
            _summary_int(current_summary, "failed_count")
            - _summary_int(previous_summary, "failed_count")
        ),
        "warning_count_delta": (
            _summary_int(current_summary, "warning_count")
            - _summary_int(previous_summary, "warning_count")
        ),
    }
    return {
        "status": _comparison_status(deltas),
        "previous_benchmark_run_id": previous.recommendation_benchmark_run_id,
        "previous_created_at": previous.created_at,
        "current_final_hit_rate": current_hit_rate,
        "previous_final_hit_rate": previous_hit_rate,
        "current_average_core_replay_roi": current_roi,
        "previous_average_core_replay_roi": previous_roi,
        "current_upset_capture_rate": current_upset_capture_rate,
        "previous_upset_capture_rate": previous_upset_capture_rate,
        "deltas": deltas,
        "calculation_basis": "recommendation_benchmark_history_comparison_v3_1",
    }


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = get_settings()
    database = PsycopgSyncDatabaseExecutor(
        args.database_url or settings.database_url,
        connect_timeout_seconds=(
            args.connect_timeout_seconds or settings.database_connect_timeout_seconds
        ),
    )
    result = run_recommendation_benchmark(database, options=_options_from_args(args))
    print(result.model_dump_json(indent=2))


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(description="Run Nutmeg recommendation benchmark matrix.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument("--as-of-time-utc", action="append", default=[])
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


def _options_from_args(args: Namespace) -> RecommendationBenchmarkOptions:
    return RecommendationBenchmarkOptions(
        as_of_times_utc=tuple(_datetime(value) for value in args.as_of_time_utc),
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


def _validation_options(
    options: RecommendationBenchmarkOptions,
    *,
    scenario: RecommendationBenchmarkScenario,
) -> RecommendationCoreValidationOptions:
    return RecommendationCoreValidationOptions(
        as_of_time_utc=scenario.as_of_time_utc,
        lookback_hours=scenario.lookback_hours,
        pass_type=scenario.pass_type,
        mode=scenario.mode,
        strategy=options.strategy,
        unit_stake=options.unit_stake,
        max_budget=scenario.max_budget,
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
        save_pipeline_audit=options.save_pipeline_audit,
        requested_by=options.requested_by,
        provider_observation_limit=options.provider_observation_limit,
        source_run_limit=options.source_run_limit,
        incident_limit=options.incident_limit,
        report_limit=options.report_limit,
        replay_limit=options.replay_limit,
        chain_integrity_limit=options.chain_integrity_limit,
    )


def _scenario_metrics(validation: RecommendationCoreValidationRunResult) -> dict[str, object]:
    summary = validation.summary_json
    return {
        "global_best_selected": summary.get("global_best_selected", False),
        "global_best_candidate_count": summary.get("global_best_candidate_count", 0),
        "global_best_generated_option_count": summary.get(
            "global_best_generated_option_count",
            0,
        ),
        "unified_candidate_pool_present": summary.get(
            "unified_candidate_pool_present",
            False,
        ),
        "unified_candidate_pool_candidate_count": summary.get(
            "unified_candidate_pool_candidate_count",
            0,
        ),
        "unified_candidate_pool_valid_candidate_count": summary.get(
            "unified_candidate_pool_valid_candidate_count",
            0,
        ),
        "unified_candidate_pool_family_count": summary.get(
            "unified_candidate_pool_family_count",
            0,
        ),
        "unified_candidate_pool_candidate_family_keys": summary.get(
            "unified_candidate_pool_candidate_family_keys",
            [],
        ),
        "unified_candidate_pool_selected_family_key": summary.get(
            "unified_candidate_pool_selected_family_key",
        ),
        "unified_candidate_pool_selected_pass_type": summary.get(
            "unified_candidate_pool_selected_pass_type",
        ),
        "unified_candidate_pool_two_x_one_is_candidate_family": summary.get(
            "unified_candidate_pool_two_x_one_is_candidate_family",
            False,
        ),
        "unified_candidate_pool_correct_score_candidate_present": summary.get(
            "unified_candidate_pool_correct_score_candidate_present",
            False,
        ),
        "unified_candidate_pool_handicap_candidate_present": summary.get(
            "unified_candidate_pool_handicap_candidate_present",
            False,
        ),
        "unified_candidate_pool_multiple_value_candidate_count": summary.get(
            "unified_candidate_pool_multiple_value_candidate_count",
            0,
        ),
        "unified_candidate_pool_multiple_value_admitted_candidate_count": (
            summary.get(
                "unified_candidate_pool_multiple_value_admitted_candidate_count",
                0,
            )
        ),
        "unified_candidate_pool_multiple_value_rejected_candidate_count": (
            summary.get(
                "unified_candidate_pool_multiple_value_rejected_candidate_count",
                0,
            )
        ),
        "unified_candidate_pool_multiple_value_extra_option_count": summary.get(
            "unified_candidate_pool_multiple_value_extra_option_count",
            0,
        ),
        "unified_candidate_pool_selected_multiple_value_status": summary.get(
            "unified_candidate_pool_selected_multiple_value_status",
        ),
        "unified_candidate_pool_selected_multiple_value_admitted": summary.get(
            "unified_candidate_pool_selected_multiple_value_admitted",
        ),
        "unified_candidate_pool_selected_multiple_extra_option_count": summary.get(
            "unified_candidate_pool_selected_multiple_extra_option_count",
            0,
        ),
        "unified_candidate_pool_multiple_value_rejection_reason_counts": summary.get(
            "unified_candidate_pool_multiple_value_rejection_reason_counts",
            {},
        ),
        "unified_candidate_pool_selection_mismatch": summary.get(
            "unified_candidate_pool_selection_mismatch",
            False,
        ),
        "unified_candidate_pool_selected_2x1": summary.get(
            "unified_candidate_pool_selected_2x1",
            False,
        ),
        "prematch_triggered_run_count": summary.get("prematch_triggered_run_count", 0),
        "core_replay_ready": summary.get("core_replay_ready", False),
        "core_replay_run_count": summary.get("core_replay_run_count", 0),
        "core_replay_settled_run_count": summary.get("core_replay_settled_run_count", 0),
        "core_replay_effective_evaluated_run_count": summary.get(
            "core_replay_effective_evaluated_run_count",
            0,
        ),
        "core_replay_final_hit": summary.get("core_replay_final_hit"),
        "core_replay_roi": summary.get("core_replay_roi"),
        "effective_chain_count": summary.get("effective_chain_count", 0),
        "effective_chain_active_edge_count": summary.get(
            "effective_chain_active_edge_count",
            0,
        ),
        "effective_leaf_run_count": summary.get("effective_leaf_run_count", 0),
        "superseded_source_run_count": summary.get("superseded_source_run_count", 0),
        "ambiguous_successor_source_count": summary.get(
            "ambiguous_successor_source_count",
            0,
        ),
        "current_answer_count": summary.get("current_answer_count", 0),
        "stale_recommendation_count": summary.get("stale_recommendation_count", 0),
        "expired_kickoff_recommendation_count": summary.get(
            "expired_kickoff_recommendation_count",
            0,
        ),
        "stale_incident_recommendation_count": summary.get(
            "stale_incident_recommendation_count",
            0,
        ),
        "successor_recompute_required_count": summary.get(
            "successor_recompute_required_count",
            0,
        ),
        "chain_integrity_ready": summary.get("chain_integrity_ready", False),
        "chain_integrity_issue_count": summary.get("chain_integrity_issue_count", 0),
        "chain_integrity_critical_issue_count": summary.get(
            "chain_integrity_critical_issue_count",
            0,
        ),
        "chain_integrity_source_status_sync_required_count": summary.get(
            "chain_integrity_source_status_sync_required_count",
            0,
        ),
        "successor_chain_evaluation_passed": summary.get(
            "successor_chain_evaluation_passed",
            False,
        ),
        "successor_chain_effective_leaf_count": summary.get(
            "successor_chain_effective_leaf_count",
            0,
        ),
        "successor_chain_active_edge_count": summary.get(
            "successor_chain_active_edge_count",
            0,
        ),
        "successor_chain_critical_issue_count": summary.get(
            "successor_chain_critical_issue_count",
            0,
        ),
        "successor_chain_ambiguous_source_count": summary.get(
            "successor_chain_ambiguous_source_count",
            0,
        ),
        "successor_chain_source_status_sync_required_count": summary.get(
            "successor_chain_source_status_sync_required_count",
            0,
        ),
        "upset_opportunity_count": summary.get("upset_opportunity_count", 0),
        "upset_capture_count": summary.get("upset_capture_count", 0),
        "upset_capture_rate": summary.get("upset_capture_rate"),
        "warning_count": summary.get("warning_count", len(validation.warnings)),
        "calculation_basis": "recommendation_benchmark_scenario_v3_1",
    }


def _benchmark_summary(
    *,
    options: RecommendationBenchmarkOptions,
    scenarios: Sequence[RecommendationBenchmarkScenario],
    results: Sequence[RecommendationBenchmarkScenarioResult],
    warning_count: int,
) -> dict[str, object]:
    completed = [result for result in results if result.status == "completed"]
    final_hits = [
        result.metrics_json.get("core_replay_final_hit")
        for result in completed
        if result.metrics_json.get("core_replay_final_hit") is not None
    ]
    rois = [
        roi
        for result in completed
        for roi in [_optional_float(result.metrics_json.get("core_replay_roi"))]
        if roi is not None
    ]
    upset_opportunity_count = sum(
        _summary_int(result.metrics_json, "upset_opportunity_count")
        for result in completed
    )
    upset_capture_count = sum(
        _summary_int(result.metrics_json, "upset_capture_count") for result in completed
    )
    unified_pool_unique_family_keys = _ordered_unique(
        family_key
        for result in completed
        for family_key in _summary_str_list(
            result.metrics_json,
            "unified_candidate_pool_candidate_family_keys",
        )
    )
    unified_pool_present_count = sum(
        1
        for result in completed
        if _summary_bool(result.metrics_json, "unified_candidate_pool_present")
    )
    unified_pool_selected_2x1_count = sum(
        1
        for result in completed
        if _summary_bool(result.metrics_json, "unified_candidate_pool_selected_2x1")
    )
    unified_pool_selected_multiple_value_statuses = _ordered_unique(
        status
        for result in completed
        for status in [
            _summary_str(
                result.metrics_json,
                "unified_candidate_pool_selected_multiple_value_status",
            )
        ]
        if status is not None
    )
    unified_pool_selected_multiple_value_admitted_count = sum(
        1
        for result in completed
        if _summary_str(
            result.metrics_json,
            "unified_candidate_pool_selected_multiple_value_status",
        )
        == "admitted"
    )
    unified_pool_selected_multiple_value_rejected_count = sum(
        1
        for result in completed
        if _summary_str(
            result.metrics_json,
            "unified_candidate_pool_selected_multiple_value_status",
        )
        == "rejected"
    )
    return {
        "scenario_count": len(scenarios),
        "completed_count": len(completed),
        "failed_count": sum(1 for result in results if result.status == "failed"),
        "as_of_time_count": len(options.normalized_as_of_times_utc),
        "as_of_times": [
            value.isoformat() for value in options.normalized_as_of_times_utc
        ],
        "pass_types": list(options.pass_types),
        "modes": list(options.modes),
        "budgets": list(options.max_budgets),
        "global_best_selected_count": sum(
            1 for result in completed if result.metrics_json.get("global_best_selected") is True
        ),
        "global_best_candidate_count": sum(
            _summary_int(result.metrics_json, "global_best_candidate_count")
            for result in completed
        ),
        "global_best_generated_option_count": sum(
            _summary_int(result.metrics_json, "global_best_generated_option_count")
            for result in completed
        ),
        "unified_candidate_pool_present_count": unified_pool_present_count,
        "unified_candidate_pool_candidate_count": sum(
            _summary_int(result.metrics_json, "unified_candidate_pool_candidate_count")
            for result in completed
        ),
        "unified_candidate_pool_valid_candidate_count": sum(
            _summary_int(
                result.metrics_json,
                "unified_candidate_pool_valid_candidate_count",
            )
            for result in completed
        ),
        "unified_candidate_pool_family_count": sum(
            _summary_int(result.metrics_json, "unified_candidate_pool_family_count")
            for result in completed
        ),
        "unified_candidate_pool_unique_family_keys": unified_pool_unique_family_keys,
        "unified_candidate_pool_unique_family_count": len(
            unified_pool_unique_family_keys
        ),
        "unified_candidate_pool_selected_family_keys": _ordered_unique(
            family_key
            for result in completed
            for family_key in [
                _summary_str(
                    result.metrics_json,
                    "unified_candidate_pool_selected_family_key",
                )
            ]
            if family_key is not None
        ),
        "unified_candidate_pool_selected_pass_types": _ordered_unique(
            pass_type
            for result in completed
            for pass_type in [
                _summary_str(
                    result.metrics_json,
                    "unified_candidate_pool_selected_pass_type",
                )
            ]
            if pass_type is not None
        ),
        "unified_candidate_pool_two_x_one_candidate_family_count": sum(
            1
            for result in completed
            if _summary_bool(
                result.metrics_json,
                "unified_candidate_pool_two_x_one_is_candidate_family",
            )
        ),
        "unified_candidate_pool_correct_score_candidate_present_count": sum(
            1
            for result in completed
            if _summary_bool(
                result.metrics_json,
                "unified_candidate_pool_correct_score_candidate_present",
            )
        ),
        "unified_candidate_pool_handicap_candidate_present_count": sum(
            1
            for result in completed
            if _summary_bool(
                result.metrics_json,
                "unified_candidate_pool_handicap_candidate_present",
            )
        ),
        "unified_candidate_pool_multiple_value_candidate_count": sum(
            _summary_int(
                result.metrics_json,
                "unified_candidate_pool_multiple_value_candidate_count",
            )
            for result in completed
        ),
        "unified_candidate_pool_multiple_value_admitted_candidate_count": sum(
            _summary_int(
                result.metrics_json,
                "unified_candidate_pool_multiple_value_admitted_candidate_count",
            )
            for result in completed
        ),
        "unified_candidate_pool_multiple_value_rejected_candidate_count": sum(
            _summary_int(
                result.metrics_json,
                "unified_candidate_pool_multiple_value_rejected_candidate_count",
            )
            for result in completed
        ),
        "unified_candidate_pool_multiple_value_extra_option_count": sum(
            _summary_int(
                result.metrics_json,
                "unified_candidate_pool_multiple_value_extra_option_count",
            )
            for result in completed
        ),
        "unified_candidate_pool_selected_multiple_value_statuses": (
            unified_pool_selected_multiple_value_statuses
        ),
        "unified_candidate_pool_selected_multiple_value_admitted_count": (
            unified_pool_selected_multiple_value_admitted_count
        ),
        "unified_candidate_pool_selected_multiple_value_rejected_count": (
            unified_pool_selected_multiple_value_rejected_count
        ),
        "unified_candidate_pool_selected_multiple_extra_option_count": sum(
            _summary_int(
                result.metrics_json,
                "unified_candidate_pool_selected_multiple_extra_option_count",
            )
            for result in completed
        ),
        "unified_candidate_pool_multiple_value_rejection_reason_counts": (
            _merge_int_count_mappings(
                _summary_mapping(
                    result.metrics_json,
                    "unified_candidate_pool_multiple_value_rejection_reason_counts",
                )
                for result in completed
            )
        ),
        "unified_candidate_pool_selection_mismatch_count": sum(
            1
            for result in completed
            if _summary_bool(
                result.metrics_json,
                "unified_candidate_pool_selection_mismatch",
            )
        ),
        "unified_candidate_pool_selected_2x1_count": unified_pool_selected_2x1_count,
        "unified_candidate_pool_selected_2x1_rate": _ratio(
            unified_pool_selected_2x1_count,
            unified_pool_present_count,
        ),
        "core_replay_ready_count": sum(
            1 for result in completed if result.metrics_json.get("core_replay_ready") is True
        ),
        "chain_integrity_ready_count": sum(
            1
            for result in completed
            if result.metrics_json.get("chain_integrity_ready") is True
        ),
        "chain_integrity_total_issue_count": sum(
            _summary_int(result.metrics_json, "chain_integrity_issue_count")
            for result in completed
        ),
        "chain_integrity_total_critical_issue_count": sum(
            _summary_int(result.metrics_json, "chain_integrity_critical_issue_count")
            for result in completed
        ),
        "chain_integrity_source_status_sync_required_count": sum(
            _summary_int(
                result.metrics_json,
                "chain_integrity_source_status_sync_required_count",
            )
            for result in completed
        ),
        "successor_chain_evaluation_passed_count": sum(
            1
            for result in completed
            if result.metrics_json.get("successor_chain_evaluation_passed") is True
        ),
        "successor_chain_effective_leaf_count": sum(
            _summary_int(result.metrics_json, "successor_chain_effective_leaf_count")
            for result in completed
        ),
        "successor_chain_active_edge_count": sum(
            _summary_int(result.metrics_json, "successor_chain_active_edge_count")
            for result in completed
        ),
        "successor_chain_critical_issue_count": sum(
            _summary_int(result.metrics_json, "successor_chain_critical_issue_count")
            for result in completed
        ),
        "successor_chain_ambiguous_source_count": sum(
            _summary_int(result.metrics_json, "successor_chain_ambiguous_source_count")
            for result in completed
        ),
        "successor_chain_source_status_sync_required_count": sum(
            _summary_int(
                result.metrics_json,
                "successor_chain_source_status_sync_required_count",
            )
            for result in completed
        ),
        "core_replay_total_run_count": sum(
            _summary_int(result.metrics_json, "core_replay_run_count")
            for result in completed
        ),
        "core_replay_total_settled_run_count": sum(
            _summary_int(result.metrics_json, "core_replay_settled_run_count")
            for result in completed
        ),
        "core_replay_effective_evaluated_run_count": sum(
            _summary_int(
                result.metrics_json,
                "core_replay_effective_evaluated_run_count",
            )
            for result in completed
        ),
        "effective_chain_count": sum(
            _summary_int(result.metrics_json, "effective_chain_count")
            for result in completed
        ),
        "effective_chain_active_edge_count": sum(
            _summary_int(result.metrics_json, "effective_chain_active_edge_count")
            for result in completed
        ),
        "effective_leaf_run_count": sum(
            _summary_int(result.metrics_json, "effective_leaf_run_count")
            for result in completed
        ),
        "superseded_source_run_count": sum(
            _summary_int(result.metrics_json, "superseded_source_run_count")
            for result in completed
        ),
        "ambiguous_successor_source_count": sum(
            _summary_int(result.metrics_json, "ambiguous_successor_source_count")
            for result in completed
        ),
        "current_answer_count": sum(
            _summary_int(result.metrics_json, "current_answer_count")
            for result in completed
        ),
        "stale_recommendation_count": sum(
            _summary_int(result.metrics_json, "stale_recommendation_count")
            for result in completed
        ),
        "expired_kickoff_recommendation_count": sum(
            _summary_int(result.metrics_json, "expired_kickoff_recommendation_count")
            for result in completed
        ),
        "stale_incident_recommendation_count": sum(
            _summary_int(result.metrics_json, "stale_incident_recommendation_count")
            for result in completed
        ),
        "successor_recompute_required_count": sum(
            _summary_int(result.metrics_json, "successor_recompute_required_count")
            for result in completed
        ),
        "final_hit_sample_size": len(final_hits),
        "final_hit_count": sum(1 for value in final_hits if value is True),
        "average_core_replay_roi": sum(rois) / len(rois) if rois else None,
        "upset_opportunity_count": upset_opportunity_count,
        "upset_capture_count": upset_capture_count,
        "upset_capture_rate": _ratio(upset_capture_count, upset_opportunity_count),
        "warning_count": warning_count,
        "dry_run": options.dry_run,
        "calculation_basis": "recommendation_benchmark_runner_v3_1",
    }


def _hit_rate(summary: dict[str, object]) -> float | None:
    sample_size = _summary_int(summary, "final_hit_sample_size")
    if sample_size <= 0:
        return None
    return _summary_int(summary, "final_hit_count") / sample_size


def _optional_delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return current - previous


def _comparison_status(deltas: dict[str, object]) -> str:
    improvements = 0
    regressions = 0
    for key in (
        "final_hit_rate_delta",
        "average_core_replay_roi_delta",
        "upset_capture_rate_delta",
    ):
        delta = _optional_float(deltas.get(key))
        if delta is None:
            continue
        if delta > 0:
            improvements += 1
        elif delta < 0:
            regressions += 1
    for key in ("core_replay_ready_count_delta",):
        delta = _summary_int(deltas, key)
        if delta > 0:
            improvements += 1
        elif delta < 0:
            regressions += 1
    for key in (
        "ambiguous_successor_source_count_delta",
        "stale_recommendation_count_delta",
        "successor_recompute_required_count_delta",
        "failed_count_delta",
        "warning_count_delta",
    ):
        delta = _summary_int(deltas, key)
        if delta < 0:
            improvements += 1
        elif delta > 0:
            regressions += 1
    if improvements and regressions:
        return "mixed"
    if improvements:
        return "improved"
    if regressions:
        return "regressed"
    return "unchanged"


def _benchmark_key(
    options: RecommendationBenchmarkOptions,
    *,
    scenarios: Sequence[RecommendationBenchmarkScenario],
) -> str:
    payload = "|".join(
        [
            ",".join(scenario.scenario_key for scenario in scenarios),
            options.strategy,
            str(options.dry_run),
            str(options.run_global_best),
            str(options.run_prematch_pipeline),
            str(options.run_core_replay),
            options.requested_by or "system",
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"recommendation_benchmark:{digest}"


def _scenario_key(
    *,
    as_of_time: datetime,
    lookback_hours: int,
    pass_type: str,
    mode: RecommendationMode,
    max_budget: float,
) -> str:
    digest = sha256(
        "|".join(
            [
                as_of_time.isoformat(),
                str(lookback_hours),
                pass_type,
                mode,
                _budget_label(max_budget),
            ]
        ).encode("utf-8")
    ).hexdigest()[:10]
    return (
        f"{as_of_time.strftime('%Y%m%dT%H%M%SZ')}:"
        f"{pass_type}:{mode}:budget_{_budget_label(max_budget)}:{digest}"
    )


def _modes_for_pass_type(
    pass_type: str,
    modes: Sequence[RecommendationMode],
) -> tuple[RecommendationMode, ...]:
    if pass_type == "1x1":
        return ("single",) if "single" in modes else ()
    return tuple(mode for mode in modes if mode in {"single", "multiple"})


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


def _stored_run_from_row(row: DatabaseRow) -> StoredRecommendationBenchmarkRun:
    return StoredRecommendationBenchmarkRun(
        recommendation_benchmark_run_id=_int(row["recommendation_benchmark_run_id"]),
        benchmark_key=str(row["benchmark_key"]),
        dry_run=_bool(row["dry_run"]),
        strategy=_strategy(row["strategy"]),
        scenario_count=_int(row["scenario_count"]),
        completed_count=_int(row["completed_count"]),
        failed_count=_int(row["failed_count"]),
        global_best_selected_count=_int(row["global_best_selected_count"]),
        core_replay_ready_count=_int(row["core_replay_ready_count"]),
        core_replay_total_run_count=_int(row["core_replay_total_run_count"]),
        core_replay_total_settled_run_count=_int(
            row["core_replay_total_settled_run_count"]
        ),
        final_hit_sample_size=_int(row["final_hit_sample_size"]),
        final_hit_count=_int(row["final_hit_count"]),
        average_core_replay_roi=_optional_float(row.get("average_core_replay_roi")),
        warning_count=_int(row["warning_count"]),
        history_comparison_json=_json_mapping(row.get("history_comparison_json")),
        summary_json=_json_mapping(row.get("summary_json")),
        created_at=_datetime_value(row["created_at"]),
    )


def _required_row(row: DatabaseRow | None) -> DatabaseRow:
    if row is None:
        raise RuntimeError("database statement did not return a row")
    return row


def _json(value: object) -> str:
    return dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _json_mapping(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str):
        parsed = loads(value)
        if isinstance(parsed, dict):
            return {str(key): item for key, item in parsed.items()}
    return {}


def _datetime(value: str) -> datetime:
    return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _datetime_value(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _datetime(value)
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


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


def _ordered_unique[ItemT](values: Iterable[ItemT]) -> list[ItemT]:
    result: list[ItemT] = []
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


def _summary_str(summary: Mapping[str, object], key: str) -> str | None:
    value = summary.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _summary_str_list(summary: Mapping[str, object], key: str) -> list[str]:
    value = summary.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [str(item) for item in value]


def _summary_mapping(summary: Mapping[str, object], key: str) -> dict[str, object]:
    value = summary.get(key)
    if not isinstance(value, Mapping):
        return {}
    return {str(item_key): item_value for item_key, item_value in value.items()}


def _summary_bool(summary: Mapping[str, object], key: str) -> bool:
    value = summary.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "passed"}
    return False


def _summary_count(
    summary: Mapping[str, object],
    *,
    count_key: str,
    ids_key: str,
) -> int:
    if count_key in summary:
        return _summary_int(dict(summary), count_key)
    value = summary.get(ids_key)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return len(value)
    return 0


def _merge_int_count_mappings(
    mappings: Iterable[Mapping[str, object]],
) -> dict[str, int]:
    result: dict[str, int] = {}
    for mapping in mappings:
        for key, value in mapping.items():
            if isinstance(value, bool):
                numeric_value = int(value)
            elif isinstance(value, int):
                numeric_value = value
            elif isinstance(value, Decimal | float | str):
                numeric_value = int(value)
            else:
                continue
            result[key] = result.get(key, 0) + numeric_value
    return dict(sorted(result.items()))


def _upset_capture_rate(summary: dict[str, object]) -> float | None:
    explicit = _optional_float(summary.get("upset_capture_rate"))
    if explicit is not None:
        return explicit
    opportunity_count = _summary_int(summary, "upset_opportunity_count")
    if opportunity_count <= 0:
        return None
    return _summary_int(summary, "upset_capture_count") / opportunity_count


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("expected integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal | float | str):
        return int(value)
    raise ValueError(f"expected integer value, got {type(value).__name__}")


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in {"1", "t", "true", "yes"}
    raise ValueError(f"expected boolean value, got {type(value).__name__}")


def _strategy(value: object) -> RecommendationStrategy:
    text = str(value)
    if text not in {
        "accuracy_first",
        "value_first",
        "upset_protection",
        "budget_constrained",
    }:
        raise ValueError(f"unknown recommendation strategy: {text}")
    return text  # type: ignore[return-value]


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal | str):
        return float(value)
    return None


if __name__ == "__main__":
    main()
