from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from json import dumps, loads
from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field

from nutmeg.config import get_settings
from nutmeg.database import DatabaseRow, PsycopgSyncDatabaseExecutor
from nutmeg.recommendations.benchmark_runner import (
    DEFAULT_BENCHMARK_BUDGETS,
    DEFAULT_BENCHMARK_MODES,
    DEFAULT_BENCHMARK_PASS_TYPES,
    DEFAULT_BENCHMARK_REQUESTED_BY,
    RecommendationBenchmarkDatabaseExecutor,
    StoredRecommendationBenchmarkRun,
)
from nutmeg.recommendations.benchmark_schedule import (
    RecommendationBenchmarkScheduleCadence,
    RecommendationBenchmarkScheduleOptions,
    RecommendationBenchmarkScheduleRunResult,
    run_recommendation_benchmark_schedule,
)
from nutmeg.recommendations.benchmark_strategy_comparison import (
    RecommendationBenchmarkStrategyComparisonOptions,
    RecommendationBenchmarkStrategyComparisonResult,
    build_recommendation_benchmark_strategy_comparison,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type RecommendationBenchmarkStrategyPairStatus = Literal["passed", "failed"]

INSERT_RECOMMENDATION_BENCHMARK_STRATEGY_PAIR_RUN_QUERY = """
INSERT INTO recommendation_benchmark_strategy_pair_runs (
  pair_key,
  status,
  passed,
  baseline_strategy,
  candidate_strategy,
  baseline_benchmark_key,
  candidate_benchmark_key,
  baseline_benchmark_run_id,
  candidate_benchmark_run_id,
  comparison_key,
  comparison_status,
  comparison_passed,
  average_core_replay_roi_delta,
  final_hit_rate_delta,
  core_replay_ready_ratio_delta,
  matrix_match,
  failed_checks_json,
  summary_json,
  warnings_json,
  result_json,
  source
) VALUES (
  %(pair_key)s,
  %(status)s,
  %(passed)s,
  %(baseline_strategy)s,
  %(candidate_strategy)s,
  %(baseline_benchmark_key)s,
  %(candidate_benchmark_key)s,
  %(baseline_benchmark_run_id)s,
  %(candidate_benchmark_run_id)s,
  %(comparison_key)s,
  %(comparison_status)s,
  %(comparison_passed)s,
  %(average_core_replay_roi_delta)s,
  %(final_hit_rate_delta)s,
  %(core_replay_ready_ratio_delta)s,
  %(matrix_match)s,
  %(failed_checks_json)s::jsonb,
  %(summary_json)s::jsonb,
  %(warnings_json)s::jsonb,
  %(result_json)s::jsonb,
  %(source)s
)
RETURNING
  recommendation_benchmark_strategy_pair_run_id,
  pair_key,
  status,
  passed,
  baseline_strategy,
  candidate_strategy,
  baseline_benchmark_key,
  candidate_benchmark_key,
  baseline_benchmark_run_id,
  candidate_benchmark_run_id,
  comparison_key,
  comparison_status,
  comparison_passed,
  average_core_replay_roi_delta,
  final_hit_rate_delta,
  core_replay_ready_ratio_delta,
  matrix_match,
  failed_checks_json,
  summary_json,
  warnings_json,
  created_at
"""

LIST_RECOMMENDATION_BENCHMARK_STRATEGY_PAIR_RUNS_QUERY = """
SELECT
  recommendation_benchmark_strategy_pair_run_id,
  pair_key,
  status,
  passed,
  baseline_strategy,
  candidate_strategy,
  baseline_benchmark_key,
  candidate_benchmark_key,
  baseline_benchmark_run_id,
  candidate_benchmark_run_id,
  comparison_key,
  comparison_status,
  comparison_passed,
  average_core_replay_roi_delta,
  final_hit_rate_delta,
  core_replay_ready_ratio_delta,
  matrix_match,
  failed_checks_json,
  summary_json,
  warnings_json,
  created_at
FROM recommendation_benchmark_strategy_pair_runs
WHERE (%(pair_key)s::text IS NULL OR pair_key = %(pair_key)s::text)
  AND (%(baseline_strategy)s::text IS NULL OR baseline_strategy = %(baseline_strategy)s::text)
  AND (%(candidate_strategy)s::text IS NULL OR candidate_strategy = %(candidate_strategy)s::text)
ORDER BY created_at DESC, recommendation_benchmark_strategy_pair_run_id DESC
LIMIT %(limit)s
"""

RECOMMENDATION_STRATEGY_CHOICES = (
    "accuracy_first",
    "value_first",
    "upset_protection",
    "budget_constrained",
)


class RecommendationBenchmarkStrategyPairScheduleRunner(Protocol):
    def __call__(
        self,
        database: RecommendationBenchmarkDatabaseExecutor,
        *,
        options: RecommendationBenchmarkScheduleOptions,
    ) -> RecommendationBenchmarkScheduleRunResult: ...


class RecommendationBenchmarkStrategyPairRunRepository(Protocol):
    def list_history(
        self,
        *,
        pair_key: str | None = None,
        baseline_strategy: RecommendationStrategy | None = None,
        candidate_strategy: RecommendationStrategy | None = None,
        limit: int = 20,
    ) -> list[StoredRecommendationBenchmarkStrategyPairRun]:
        """Read persisted paired benchmark comparison reports."""

    def save_run(
        self,
        result: RecommendationBenchmarkStrategyPairRunResult,
        *,
        source: str = "recommendation_benchmark_strategy_pair_v3_1",
    ) -> StoredRecommendationBenchmarkStrategyPairRun:
        """Persist a paired benchmark comparison report."""


class RecommendationBenchmarkStrategyPairOptions(BaseModel):
    schedule_options: RecommendationBenchmarkScheduleOptions = Field(
        default_factory=RecommendationBenchmarkScheduleOptions
    )
    baseline_strategy: RecommendationStrategy = "accuracy_first"
    candidate_strategy: RecommendationStrategy = "value_first"
    comparison_options: RecommendationBenchmarkStrategyComparisonOptions = Field(
        default_factory=RecommendationBenchmarkStrategyComparisonOptions
    )
    save_pair_report: bool = False


class RecommendationBenchmarkStrategyPairRunResult(BaseModel):
    pair_key: str
    status: RecommendationBenchmarkStrategyPairStatus
    passed: bool
    baseline_schedule: RecommendationBenchmarkScheduleRunResult
    candidate_schedule: RecommendationBenchmarkScheduleRunResult
    comparison: RecommendationBenchmarkStrategyComparisonResult
    stored_pair_report: StoredRecommendationBenchmarkStrategyPairRun | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class StoredRecommendationBenchmarkStrategyPairRun(BaseModel):
    recommendation_benchmark_strategy_pair_run_id: int = Field(gt=0)
    pair_key: str
    status: RecommendationBenchmarkStrategyPairStatus
    passed: bool
    baseline_strategy: RecommendationStrategy
    candidate_strategy: RecommendationStrategy
    baseline_benchmark_key: str
    candidate_benchmark_key: str
    baseline_benchmark_run_id: int | None = None
    candidate_benchmark_run_id: int | None = None
    comparison_key: str
    comparison_status: str
    comparison_passed: bool
    average_core_replay_roi_delta: float | None = None
    final_hit_rate_delta: float | None = None
    core_replay_ready_ratio_delta: float | None = None
    matrix_match: bool
    failed_checks_json: list[object] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)
    warnings_json: list[object] = Field(default_factory=list)
    created_at: datetime


class PostgresRecommendationBenchmarkStrategyPairRunRepository:
    def __init__(self, database: RecommendationBenchmarkDatabaseExecutor) -> None:
        self.database = database

    def list_history(
        self,
        *,
        pair_key: str | None = None,
        baseline_strategy: RecommendationStrategy | None = None,
        candidate_strategy: RecommendationStrategy | None = None,
        limit: int = 20,
    ) -> list[StoredRecommendationBenchmarkStrategyPairRun]:
        rows = self.database.fetch_all(
            LIST_RECOMMENDATION_BENCHMARK_STRATEGY_PAIR_RUNS_QUERY,
            {
                "pair_key": pair_key,
                "baseline_strategy": baseline_strategy,
                "candidate_strategy": candidate_strategy,
                "limit": max(1, min(limit, 200)),
            },
        )
        return [_stored_pair_run_from_row(row) for row in rows]

    def save_run(
        self,
        result: RecommendationBenchmarkStrategyPairRunResult,
        *,
        source: str = "recommendation_benchmark_strategy_pair_v3_1",
    ) -> StoredRecommendationBenchmarkStrategyPairRun:
        summary = result.summary_json
        comparison_summary = result.comparison.summary_json
        row = _required_row(
            self.database.fetch_one(
                INSERT_RECOMMENDATION_BENCHMARK_STRATEGY_PAIR_RUN_QUERY,
                {
                    "pair_key": result.pair_key,
                    "status": result.status,
                    "passed": result.passed,
                    "baseline_strategy": _summary_str(
                        summary,
                        "baseline_strategy",
                    ),
                    "candidate_strategy": _summary_str(
                        summary,
                        "candidate_strategy",
                    ),
                    "baseline_benchmark_key": _summary_str(
                        summary,
                        "baseline_benchmark_key",
                    ),
                    "candidate_benchmark_key": _summary_str(
                        summary,
                        "candidate_benchmark_key",
                    ),
                    "baseline_benchmark_run_id": _optional_int(
                        summary.get("baseline_stored_report_id")
                    ),
                    "candidate_benchmark_run_id": _optional_int(
                        summary.get("candidate_stored_report_id")
                    ),
                    "comparison_key": result.comparison.comparison_key,
                    "comparison_status": result.comparison.status,
                    "comparison_passed": result.comparison.passed,
                    "average_core_replay_roi_delta": _optional_float(
                        comparison_summary.get("average_core_replay_roi_delta")
                    ),
                    "final_hit_rate_delta": _optional_float(
                        comparison_summary.get("final_hit_rate_delta")
                    ),
                    "core_replay_ready_ratio_delta": _optional_float(
                        comparison_summary.get("core_replay_ready_ratio_delta")
                    ),
                    "matrix_match": _summary_bool(comparison_summary, "matrix_match"),
                    "failed_checks_json": _json(
                        comparison_summary.get("failed_checks", [])
                    ),
                    "summary_json": _json(summary),
                    "warnings_json": _json(result.warnings),
                    "result_json": _json(result.model_dump(mode="json")),
                    "source": source,
                },
            )
        )
        return _stored_pair_run_from_row(row)


def run_recommendation_benchmark_strategy_pair(
    database: RecommendationBenchmarkDatabaseExecutor,
    *,
    options: RecommendationBenchmarkStrategyPairOptions,
    schedule_runner: RecommendationBenchmarkStrategyPairScheduleRunner | None = None,
    pair_repository: RecommendationBenchmarkStrategyPairRunRepository | None = None,
) -> RecommendationBenchmarkStrategyPairRunResult:
    frozen_schedule_options = _freeze_schedule_run_at(options.schedule_options)
    runner = schedule_runner or run_recommendation_benchmark_schedule
    baseline_schedule = runner(
        database,
        options=frozen_schedule_options.model_copy(
            update={"strategy": options.baseline_strategy}
        ),
    )
    candidate_schedule = runner(
        database,
        options=frozen_schedule_options.model_copy(
            update={"strategy": options.candidate_strategy}
        ),
    )
    baseline_run, baseline_warning = _comparison_run(
        baseline_schedule,
        fallback_run_id=1,
    )
    candidate_run, candidate_warning = _comparison_run(
        candidate_schedule,
        fallback_run_id=2,
    )
    comparison_options = _comparison_options(options)
    comparison = build_recommendation_benchmark_strategy_comparison(
        candidate=candidate_run,
        baseline=baseline_run,
        options=comparison_options,
    )
    warnings = _dedupe_strings(
        [
            *baseline_schedule.warnings,
            *candidate_schedule.warnings,
            *([baseline_warning] if baseline_warning else []),
            *([candidate_warning] if candidate_warning else []),
            *comparison.warnings,
        ]
    )
    pair_key = _pair_key(options, schedule_options=frozen_schedule_options)
    result = RecommendationBenchmarkStrategyPairRunResult(
        pair_key=pair_key,
        status="passed" if comparison.passed else "failed",
        passed=comparison.passed,
        baseline_schedule=baseline_schedule,
        candidate_schedule=candidate_schedule,
        comparison=comparison,
        warnings=warnings,
        summary_json=_pair_summary(
            pair_key=pair_key,
            baseline_schedule=baseline_schedule,
            candidate_schedule=candidate_schedule,
            comparison=comparison,
            warnings=warnings,
        ),
    )
    if not options.save_pair_report:
        return result
    repository = pair_repository or PostgresRecommendationBenchmarkStrategyPairRunRepository(
        database
    )
    stored = repository.save_run(result)
    return result.model_copy(update={"stored_pair_report": stored})


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = get_settings()
    database = PsycopgSyncDatabaseExecutor(
        args.database_url or settings.database_url,
        connect_timeout_seconds=(
            args.connect_timeout_seconds or settings.database_connect_timeout_seconds
        ),
    )
    result = run_recommendation_benchmark_strategy_pair(
        database,
        options=_options_from_args(args),
    )
    print(result.model_dump_json(indent=2))
    if not result.passed and not args.no_fail_process:
        raise SystemExit(1)


def _comparison_options(
    options: RecommendationBenchmarkStrategyPairOptions,
) -> RecommendationBenchmarkStrategyComparisonOptions:
    return options.comparison_options.model_copy(
        update={
            "baseline_strategy": options.baseline_strategy,
            "candidate_strategy": options.candidate_strategy,
            "baseline_benchmark_key": None,
            "candidate_benchmark_key": None,
            "benchmark_key": None,
        }
    )


def _freeze_schedule_run_at(
    options: RecommendationBenchmarkScheduleOptions,
) -> RecommendationBenchmarkScheduleOptions:
    return options.model_copy(update={"run_at_utc": options.normalized_run_at_utc})


def _comparison_run(
    schedule: RecommendationBenchmarkScheduleRunResult,
    *,
    fallback_run_id: int,
) -> tuple[StoredRecommendationBenchmarkRun, str | None]:
    if schedule.benchmark.stored_report is not None:
        return schedule.benchmark.stored_report, None
    summary = schedule.benchmark.summary_json
    return (
        StoredRecommendationBenchmarkRun(
            recommendation_benchmark_run_id=fallback_run_id,
            benchmark_key=schedule.benchmark.benchmark_key,
            dry_run=schedule.benchmark.dry_run,
            strategy=schedule.benchmark.strategy,
            scenario_count=schedule.benchmark.scenario_count,
            completed_count=schedule.benchmark.completed_count,
            failed_count=schedule.benchmark.failed_count,
            global_best_selected_count=_summary_int(
                summary,
                "global_best_selected_count",
            ),
            core_replay_ready_count=_summary_int(summary, "core_replay_ready_count"),
            core_replay_total_run_count=_summary_int(
                summary,
                "core_replay_total_run_count",
            ),
            core_replay_total_settled_run_count=_summary_int(
                summary,
                "core_replay_total_settled_run_count",
            ),
            final_hit_sample_size=_summary_int(summary, "final_hit_sample_size"),
            final_hit_count=_summary_int(summary, "final_hit_count"),
            average_core_replay_roi=_optional_float(
                summary.get("average_core_replay_roi")
            ),
            warning_count=_summary_int(summary, "warning_count"),
            summary_json=summary,
            created_at=schedule.run_at_utc,
        ),
        f"benchmark_strategy_pair:using_unsaved_current_report:{schedule.benchmark.strategy}",
    )


def _pair_summary(
    *,
    pair_key: str,
    baseline_schedule: RecommendationBenchmarkScheduleRunResult,
    candidate_schedule: RecommendationBenchmarkScheduleRunResult,
    comparison: RecommendationBenchmarkStrategyComparisonResult,
    warnings: Sequence[str],
) -> dict[str, object]:
    return {
        "pair_key": pair_key,
        "status": "passed" if comparison.passed else "failed",
        "passed": comparison.passed,
        "baseline_strategy": baseline_schedule.benchmark.strategy,
        "candidate_strategy": candidate_schedule.benchmark.strategy,
        "baseline_benchmark_key": baseline_schedule.benchmark.benchmark_key,
        "candidate_benchmark_key": candidate_schedule.benchmark.benchmark_key,
        "baseline_stored_report_id": (
            baseline_schedule.benchmark.stored_report.recommendation_benchmark_run_id
            if baseline_schedule.benchmark.stored_report is not None
            else None
        ),
        "candidate_stored_report_id": (
            candidate_schedule.benchmark.stored_report.recommendation_benchmark_run_id
            if candidate_schedule.benchmark.stored_report is not None
            else None
        ),
        "comparison_key": comparison.comparison_key,
        "comparison_status": comparison.status,
        "comparison_passed": comparison.passed,
        "comparison_failed_checks": comparison.summary_json.get("failed_checks", []),
        "warnings": list(warnings),
        "calculation_basis": "recommendation_benchmark_strategy_pair_v3_1",
    }


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Run paired Nutmeg recommendation benchmarks and compare strategies."
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=None)
    parser.add_argument("--schedule-name", default="strategy-pair")
    parser.add_argument(
        "--cadence",
        choices=["once", "daily", "weekly"],
        default="once",
    )
    parser.add_argument("--run-at-utc", default=None)
    parser.add_argument("--window-count", type=int, default=1)
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--pass-types", default=",".join(DEFAULT_BENCHMARK_PASS_TYPES))
    parser.add_argument("--modes", default=",".join(DEFAULT_BENCHMARK_MODES))
    parser.add_argument(
        "--budgets",
        default=",".join(_budget_label(value) for value in DEFAULT_BENCHMARK_BUDGETS),
    )
    parser.add_argument(
        "--baseline-strategy",
        choices=list(RECOMMENDATION_STRATEGY_CHOICES),
        default="accuracy_first",
    )
    parser.add_argument(
        "--candidate-strategy",
        choices=list(RECOMMENDATION_STRATEGY_CHOICES),
        default="value_first",
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
    parser.add_argument("--save-pair-report", action="store_true")
    parser.add_argument("--save-audit", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--no-require-matrix-match", action="store_true")
    parser.add_argument("--comparison-history-limit", type=int, default=20)
    parser.add_argument("--allow-missing-history", action="store_true")
    parser.add_argument("--min-scenario-count", type=int, default=1)
    parser.add_argument("--min-completed-ratio", type=float, default=1.0)
    parser.add_argument("--max-failed-count", type=int, default=0)
    parser.add_argument("--min-core-replay-ready-ratio", type=float, default=None)
    parser.add_argument("--min-final-hit-sample-size", type=int, default=0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--skip-roi-delta-check", action="store_true")
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=None)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> RecommendationBenchmarkStrategyPairOptions:
    schedule_options = RecommendationBenchmarkScheduleOptions(
        schedule_name=args.schedule_name,
        cadence=_cadence(args.cadence),
        run_at_utc=_datetime(args.run_at_utc) if args.run_at_utc else None,
        window_count=args.window_count,
        lookback_hours=args.lookback_hours,
        pass_types=tuple(_csv(args.pass_types)),
        modes=tuple(_mode(value) for value in _csv(args.modes)),
        max_budgets=tuple(_positive_float(value) for value in _csv(args.budgets)),
        strategy=_strategy(args.baseline_strategy),
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
    comparison_options = RecommendationBenchmarkStrategyComparisonOptions(
        candidate_strategy=_strategy(args.candidate_strategy),
        baseline_strategy=_strategy(args.baseline_strategy),
        history_limit=args.comparison_history_limit,
        allow_missing_history=args.allow_missing_history,
        require_matrix_match=not args.no_require_matrix_match,
        min_scenario_count=args.min_scenario_count,
        min_completed_ratio=args.min_completed_ratio,
        max_failed_count=args.max_failed_count,
        min_core_replay_ready_ratio=args.min_core_replay_ready_ratio,
        min_final_hit_sample_size=args.min_final_hit_sample_size,
        min_average_core_replay_roi_delta=(
            None if args.skip_roi_delta_check else args.min_roi_delta
        ),
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
    )
    return RecommendationBenchmarkStrategyPairOptions(
        schedule_options=schedule_options,
        baseline_strategy=_strategy(args.baseline_strategy),
        candidate_strategy=_strategy(args.candidate_strategy),
        comparison_options=comparison_options,
        save_pair_report=args.save_pair_report,
    )


def _summary_int(summary: dict[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float | Decimal | str):
        return float(value)
    return None


def _summary_str(summary: dict[str, object], key: str) -> str:
    value = summary.get(key, "")
    if isinstance(value, str):
        return value
    return str(value)


def _summary_bool(summary: dict[str, object], key: str) -> bool:
    value = summary.get(key, False)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes"}
    return False


def _stored_pair_run_from_row(
    row: DatabaseRow,
) -> StoredRecommendationBenchmarkStrategyPairRun:
    return StoredRecommendationBenchmarkStrategyPairRun(
        recommendation_benchmark_strategy_pair_run_id=_int(
            row["recommendation_benchmark_strategy_pair_run_id"]
        ),
        pair_key=str(row["pair_key"]),
        status=_pair_status(row["status"]),
        passed=_bool(row["passed"]),
        baseline_strategy=_strategy(str(row["baseline_strategy"])),
        candidate_strategy=_strategy(str(row["candidate_strategy"])),
        baseline_benchmark_key=str(row["baseline_benchmark_key"]),
        candidate_benchmark_key=str(row["candidate_benchmark_key"]),
        baseline_benchmark_run_id=_optional_int(row.get("baseline_benchmark_run_id")),
        candidate_benchmark_run_id=_optional_int(row.get("candidate_benchmark_run_id")),
        comparison_key=str(row["comparison_key"]),
        comparison_status=str(row["comparison_status"]),
        comparison_passed=_bool(row["comparison_passed"]),
        average_core_replay_roi_delta=_optional_float(
            row.get("average_core_replay_roi_delta")
        ),
        final_hit_rate_delta=_optional_float(row.get("final_hit_rate_delta")),
        core_replay_ready_ratio_delta=_optional_float(
            row.get("core_replay_ready_ratio_delta")
        ),
        matrix_match=_bool(row["matrix_match"]),
        failed_checks_json=_json_list(row.get("failed_checks_json")),
        summary_json=_json_mapping(row.get("summary_json")),
        warnings_json=_json_list(row.get("warnings_json")),
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


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    raise ValueError(f"expected int-like value, got {type(value).__name__}")


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes"}
    return False


def _pair_status(value: object) -> RecommendationBenchmarkStrategyPairStatus:
    if value in {"passed", "failed"}:
        return cast(RecommendationBenchmarkStrategyPairStatus, value)
    raise ValueError(f"unknown strategy pair status: {value}")


def _datetime_value(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, str):
        return _datetime(value)
    raise ValueError(f"expected datetime value, got {type(value).__name__}")


def _pair_key(
    options: RecommendationBenchmarkStrategyPairOptions,
    *,
    schedule_options: RecommendationBenchmarkScheduleOptions,
) -> str:
    payload = "|".join(
        [
            schedule_options.schedule_name,
            schedule_options.cadence,
            schedule_options.normalized_run_at_utc.isoformat(),
            ",".join(schedule_options.pass_types),
            ",".join(schedule_options.modes),
            ",".join(_budget_label(value) for value in schedule_options.max_budgets),
            options.baseline_strategy,
            options.candidate_strategy,
            str(schedule_options.dry_run),
            str(schedule_options.save_report),
        ]
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"recommendation_benchmark_strategy_pair:{digest}"


def _strategy(value: str) -> RecommendationStrategy:
    if value not in RECOMMENDATION_STRATEGY_CHOICES:
        raise ValueError(f"unknown recommendation strategy: {value}")
    return cast(RecommendationStrategy, value)


def _cadence(value: str) -> RecommendationBenchmarkScheduleCadence:
    if value not in {"once", "daily", "weekly"}:
        raise ValueError(f"unknown benchmark cadence: {value}")
    return cast(RecommendationBenchmarkScheduleCadence, value)


def _mode(value: str) -> RecommendationMode:
    if value not in {"single", "multiple"}:
        raise ValueError(f"unknown benchmark mode: {value}")
    return cast(RecommendationMode, value)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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
