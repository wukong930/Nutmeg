from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    PostgresRecommendationBenchmarkStrategyPairRunRepository,
    RecommendationBenchmarkRunResult,
    RecommendationBenchmarkScheduleOptions,
    RecommendationBenchmarkScheduleRunResult,
    RecommendationBenchmarkStrategyComparisonOptions,
    RecommendationBenchmarkStrategyPairOptions,
    RecommendationBenchmarkStrategyPairRunResult,
    StoredRecommendationBenchmarkRun,
    StoredRecommendationBenchmarkStrategyPairRun,
    run_recommendation_benchmark_strategy_pair,
)
from nutmeg.recommendations.benchmark_strategy_pair import (
    INSERT_RECOMMENDATION_BENCHMARK_STRATEGY_PAIR_RUN_QUERY,
    LIST_RECOMMENDATION_BENCHMARK_STRATEGY_PAIR_RUNS_QUERY,
    _options_from_args,
    _parse_args,
)
from nutmeg.recommendations.models import RecommendationStrategy


def test_strategy_pair_runs_same_matrix_for_baseline_and_candidate() -> None:
    calls: list[RecommendationBenchmarkScheduleOptions] = []

    result = run_recommendation_benchmark_strategy_pair(
        FakeDatabase(),
        options=RecommendationBenchmarkStrategyPairOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                schedule_name="adverse-odds-pair",
                cadence="once",
                run_at_utc=_dt(2026, 5, 12, 0),
                pass_types=("2x1", "4x1"),
                modes=("multiple",),
                max_budgets=(10.0,),
                save_report=True,
                dry_run=False,
            ),
            comparison_options=RecommendationBenchmarkStrategyComparisonOptions(
                min_final_hit_sample_size=4,
                min_final_hit_rate_delta=0.0,
            ),
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            calls=calls,
            stored_report=True,
        ),
    )

    assert result.passed is True
    assert result.status == "passed"
    assert [call.strategy for call in calls] == ["accuracy_first", "value_first"]
    assert calls[0].run_at_utc == _dt(2026, 5, 12, 0)
    assert calls[1].run_at_utc == _dt(2026, 5, 12, 0)
    assert calls[0].pass_types == calls[1].pass_types
    assert calls[0].modes == calls[1].modes
    assert calls[0].max_budgets == calls[1].max_budgets
    assert result.comparison.summary_json["matrix_match"] is True
    assert _summary_float(result.comparison.summary_json, "final_hit_rate_delta") == (
        pytest.approx(0.25)
    )
    assert result.summary_json["baseline_stored_report_id"] == 101
    assert result.summary_json["candidate_stored_report_id"] == 202


def test_strategy_pair_can_compare_unsaved_current_reports_with_warning() -> None:
    result = run_recommendation_benchmark_strategy_pair(
        FakeDatabase(),
        options=RecommendationBenchmarkStrategyPairOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                run_at_utc=_dt(2026, 5, 12, 0),
                save_report=False,
            )
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=False,
        ),
    )

    assert result.passed is True
    assert result.summary_json["baseline_stored_report_id"] is None
    assert result.summary_json["candidate_stored_report_id"] is None
    assert result.warnings == [
        "benchmark_strategy_pair:using_unsaved_current_report:accuracy_first",
        "benchmark_strategy_pair:using_unsaved_current_report:value_first",
    ]


def test_strategy_pair_fails_when_candidate_roi_delta_breaks_threshold() -> None:
    result = run_recommendation_benchmark_strategy_pair(
        FakeDatabase(),
        options=RecommendationBenchmarkStrategyPairOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                run_at_utc=_dt(2026, 5, 12, 0),
            ),
            comparison_options=RecommendationBenchmarkStrategyComparisonOptions(
                min_average_core_replay_roi_delta=0.20,
            ),
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
    )

    assert result.passed is False
    assert result.status == "failed"
    assert result.summary_json["comparison_failed_checks"] == [
        "average_core_replay_roi_delta"
    ]


def test_strategy_pair_saves_pair_report_when_enabled() -> None:
    repository = FakePairRunRepository()

    result = run_recommendation_benchmark_strategy_pair(
        FakeDatabase(),
        options=RecommendationBenchmarkStrategyPairOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                run_at_utc=_dt(2026, 5, 12, 0),
                save_report=True,
            ),
            save_pair_report=True,
        ),
        schedule_runner=lambda database, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
        pair_repository=repository,
    )

    assert result.stored_pair_report is not None
    assert result.stored_pair_report.recommendation_benchmark_strategy_pair_run_id == 301
    assert repository.saved is not None
    assert repository.saved.pair_key == result.pair_key
    assert repository.saved.comparison.passed is True


def test_postgres_strategy_pair_repository_writes_and_lists_runs() -> None:
    database = FakePairDatabase()
    repository = PostgresRecommendationBenchmarkStrategyPairRunRepository(database)
    result = run_recommendation_benchmark_strategy_pair(
        FakeDatabase(),
        options=RecommendationBenchmarkStrategyPairOptions(
            schedule_options=RecommendationBenchmarkScheduleOptions(
                run_at_utc=_dt(2026, 5, 12, 0),
                save_report=True,
            )
        ),
        schedule_runner=lambda db, *, options: _schedule_result(
            options=options,
            stored_report=True,
        ),
    )

    listed = repository.list_history(
        pair_key=result.pair_key,
        baseline_strategy="accuracy_first",
        candidate_strategy="value_first",
        limit=500,
    )
    stored = repository.save_run(result)

    assert listed[0].pair_key == result.pair_key
    assert stored.recommendation_benchmark_strategy_pair_run_id == 302
    assert stored.average_core_replay_roi_delta == pytest.approx(0.10)
    assert database.fetch_all_calls == [
        (
            LIST_RECOMMENDATION_BENCHMARK_STRATEGY_PAIR_RUNS_QUERY,
            {
                "pair_key": result.pair_key,
                "baseline_strategy": "accuracy_first",
                "candidate_strategy": "value_first",
                "limit": 200,
            },
        )
    ]
    insert_query, params = database.fetch_one_calls[0]
    assert insert_query == INSERT_RECOMMENDATION_BENCHMARK_STRATEGY_PAIR_RUN_QUERY
    assert params["pair_key"] == result.pair_key
    assert params["baseline_benchmark_run_id"] == 101
    assert params["candidate_benchmark_run_id"] == 202
    assert params["average_core_replay_roi_delta"] == pytest.approx(0.10)
    assert params["final_hit_rate_delta"] == pytest.approx(0.25)


def test_strategy_pair_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--schedule-name",
            "pair-smoke",
            "--cadence",
            "weekly",
            "--run-at-utc",
            "2026-05-12T00:00:00Z",
            "--window-count",
            "2",
            "--lookback-hours",
            "48",
            "--pass-types",
            "2x1,6x1",
            "--modes",
            "single,multiple",
            "--budgets",
            "10,30",
            "--baseline-strategy",
            "accuracy_first",
            "--candidate-strategy",
            "value_first",
            "--commit",
            "--save-report",
            "--save-pair-report",
            "--include-prematch-pipeline",
            "--no-require-matrix-match",
            "--comparison-history-limit",
            "5",
            "--min-final-hit-sample-size",
            "8",
            "--min-roi-delta",
            "0.03",
            "--min-final-hit-rate-delta",
            "-0.02",
            "--no-fail-process",
        ]
    )

    options = _options_from_args(args)

    assert options.schedule_options.schedule_name == "pair-smoke"
    assert options.schedule_options.cadence == "weekly"
    assert options.schedule_options.run_at_utc == _dt(2026, 5, 12, 0)
    assert options.schedule_options.window_count == 2
    assert options.schedule_options.lookback_hours == 48
    assert options.schedule_options.pass_types == ("2x1", "6x1")
    assert options.schedule_options.modes == ("single", "multiple")
    assert options.schedule_options.max_budgets == (10.0, 30.0)
    assert options.schedule_options.dry_run is False
    assert options.schedule_options.save_report is True
    assert options.schedule_options.run_prematch_pipeline is True
    assert options.schedule_options.run_successor_chain_evaluation is True
    assert options.save_pair_report is True
    assert options.baseline_strategy == "accuracy_first"
    assert options.candidate_strategy == "value_first"
    assert options.comparison_options.history_limit == 5
    assert options.comparison_options.require_matrix_match is False
    assert options.comparison_options.min_final_hit_sample_size == 8
    assert options.comparison_options.min_average_core_replay_roi_delta == 0.03
    assert options.comparison_options.min_final_hit_rate_delta == -0.02


class FakeDatabase:
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise AssertionError(f"unexpected fetch_all: {query} {params}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError(f"unexpected fetch_one: {query} {params}")


class FakePairRunRepository:
    def __init__(self) -> None:
        self.saved: RecommendationBenchmarkStrategyPairRunResult | None = None

    def list_history(
        self,
        *,
        pair_key: str | None = None,
        baseline_strategy: RecommendationStrategy | None = None,
        candidate_strategy: RecommendationStrategy | None = None,
        limit: int = 20,
    ) -> list[StoredRecommendationBenchmarkStrategyPairRun]:
        raise AssertionError("unexpected list_history")

    def save_run(
        self,
        result: RecommendationBenchmarkStrategyPairRunResult,
        *,
        source: str = "recommendation_benchmark_strategy_pair_v3_1",
    ) -> StoredRecommendationBenchmarkStrategyPairRun:
        self.saved = result
        return _stored_pair_run()


class FakePairDatabase:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        return [
            _pair_row(
                recommendation_benchmark_strategy_pair_run_id=301,
                pair_key=str(params["pair_key"]),
            )
        ]

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        return _pair_row(
            recommendation_benchmark_strategy_pair_run_id=302,
            pair_key=str(params["pair_key"]),
        )


def _schedule_result(
    *,
    options: RecommendationBenchmarkScheduleOptions,
    calls: list[RecommendationBenchmarkScheduleOptions] | None = None,
    stored_report: bool,
) -> RecommendationBenchmarkScheduleRunResult:
    if calls is not None:
        calls.append(options)
    benchmark = RecommendationBenchmarkRunResult(
        benchmark_key=f"recommendation_benchmark:{options.strategy}",
        dry_run=options.dry_run,
        strategy=options.strategy,
        scenario_count=4,
        completed_count=4,
        failed_count=0,
        summary_json=_summary(options.strategy),
        stored_report=(
            _stored_run(options.strategy, dry_run=options.dry_run)
            if stored_report
            else None
        ),
    )
    return RecommendationBenchmarkScheduleRunResult(
        schedule_key=f"recommendation_benchmark_schedule:{options.schedule_name}",
        schedule_name=options.schedule_name,
        cadence=options.cadence,
        run_at_utc=options.normalized_run_at_utc,
        generated_as_of_times_utc=[options.normalized_run_at_utc],
        dry_run=options.dry_run,
        save_report=options.save_report,
        benchmark=benchmark,
        summary_json={"benchmark_key": benchmark.benchmark_key},
    )


def _stored_run(
    strategy: RecommendationStrategy,
    *,
    dry_run: bool,
) -> StoredRecommendationBenchmarkRun:
    summary = _summary(strategy)
    return StoredRecommendationBenchmarkRun(
        recommendation_benchmark_run_id=202 if strategy == "value_first" else 101,
        benchmark_key=f"recommendation_benchmark:{strategy}",
        dry_run=dry_run,
        strategy=strategy,
        scenario_count=4,
        completed_count=4,
        failed_count=0,
        global_best_selected_count=4,
        core_replay_ready_count=4,
        core_replay_total_run_count=4,
        core_replay_total_settled_run_count=4,
        final_hit_sample_size=4,
        final_hit_count=3 if strategy == "value_first" else 2,
        average_core_replay_roi=0.08 if strategy == "value_first" else -0.02,
        warning_count=0,
        summary_json=summary,
        created_at=_dt(2026, 5, 12, 0),
    )


def _stored_pair_run() -> StoredRecommendationBenchmarkStrategyPairRun:
    return StoredRecommendationBenchmarkStrategyPairRun(
        recommendation_benchmark_strategy_pair_run_id=301,
        pair_key="recommendation_benchmark_strategy_pair:test",
        status="passed",
        passed=True,
        baseline_strategy="accuracy_first",
        candidate_strategy="value_first",
        baseline_benchmark_key="recommendation_benchmark:accuracy_first",
        candidate_benchmark_key="recommendation_benchmark:value_first",
        baseline_benchmark_run_id=101,
        candidate_benchmark_run_id=202,
        comparison_key="recommendation_benchmark_strategy_comparison:test",
        comparison_status="passed",
        comparison_passed=True,
        average_core_replay_roi_delta=0.10,
        final_hit_rate_delta=0.25,
        core_replay_ready_ratio_delta=0.0,
        matrix_match=True,
        failed_checks_json=[],
        summary_json={"status": "passed"},
        warnings_json=[],
        created_at=_dt(2026, 5, 12, 0),
    )


def _pair_row(
    *,
    recommendation_benchmark_strategy_pair_run_id: int,
    pair_key: str = "recommendation_benchmark_strategy_pair:test",
) -> DatabaseRow:
    return {
        "recommendation_benchmark_strategy_pair_run_id": (
            recommendation_benchmark_strategy_pair_run_id
        ),
        "pair_key": pair_key,
        "status": "passed",
        "passed": True,
        "baseline_strategy": "accuracy_first",
        "candidate_strategy": "value_first",
        "baseline_benchmark_key": "recommendation_benchmark:accuracy_first",
        "candidate_benchmark_key": "recommendation_benchmark:value_first",
        "baseline_benchmark_run_id": 101,
        "candidate_benchmark_run_id": 202,
        "comparison_key": "recommendation_benchmark_strategy_comparison:test",
        "comparison_status": "passed",
        "comparison_passed": True,
        "average_core_replay_roi_delta": 0.10,
        "final_hit_rate_delta": 0.25,
        "core_replay_ready_ratio_delta": 0.0,
        "matrix_match": True,
        "failed_checks_json": [],
        "summary_json": {"status": "passed"},
        "warnings_json": [],
        "created_at": _dt(2026, 5, 12, 0),
    }


def _summary(strategy: RecommendationStrategy) -> dict[str, object]:
    return {
        "as_of_times": ["2026-05-12T00:00:00+00:00"],
        "pass_types": ["2x1", "4x1"],
        "modes": ["multiple"],
        "budgets": [10.0],
        "global_best_selected_count": 4,
        "core_replay_ready_count": 4,
        "core_replay_total_run_count": 4,
        "core_replay_total_settled_run_count": 4,
        "final_hit_sample_size": 4,
        "final_hit_count": 3 if strategy == "value_first" else 2,
        "average_core_replay_roi": 0.08 if strategy == "value_first" else -0.02,
        "warning_count": 0,
    }


def _summary_float(summary: dict[str, object], key: str) -> float:
    value = summary[key]
    assert isinstance(value, float)
    return value


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
