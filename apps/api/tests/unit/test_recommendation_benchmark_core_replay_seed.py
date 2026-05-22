from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations.baseline_seed import RecommendationBaselineSeedResult
from nutmeg.recommendations.benchmark_core_replay_seed import (
    RecommendationBenchmarkCoreReplaySeedOptions,
    run_recommendation_benchmark_core_replay_seed,
)
from nutmeg.recommendations.benchmark_runner import (
    RecommendationBenchmarkOptions,
    RecommendationBenchmarkRunResult,
    RecommendationBenchmarkScenario,
    RecommendationBenchmarkScenarioResult,
)
from nutmeg.recommendations.core_validation_runner import (
    RecommendationCoreValidationRunResult,
)


def test_core_replay_seed_commits_baseline_then_benchmark_matrix() -> None:
    seed_calls: list[object] = []
    benchmark_calls: list[RecommendationBenchmarkOptions] = []

    result = run_recommendation_benchmark_core_replay_seed(
        FakeDatabase(),
        options=RecommendationBenchmarkCoreReplaySeedOptions(
            as_of_time_utc=_dt(2026, 5, 12, 0),
            pass_types=("1x1", "2x1"),
            modes=("single", "multiple"),
            max_budgets=(10.0, 20.0, 50.0),
            requested_by="seed-test",
        ),
        seed_runner=lambda database, *, options: _seed_result(
            seed_calls=seed_calls,
            options=options,
        ),
        benchmark_runner=lambda database, *, options: _benchmark_result(
            benchmark_calls=benchmark_calls,
            options=options,
            stored_run_ids=[11, 12, 13],
        ),
    )

    assert result.passed is True
    assert result.seed_budget == 10.0
    assert result.stored_recommendation_run_ids == [11, 12, 13]
    assert result.summary_json["stored_recommendation_run_count"] == 3
    assert result.summary_json["seed_budget"] == 10.0
    assert seed_calls
    assert benchmark_calls[0].max_budgets == (10.0,)
    assert benchmark_calls[0].dry_run is False
    assert benchmark_calls[0].run_core_replay is False
    assert benchmark_calls[0].run_chain_integrity is False
    assert benchmark_calls[0].run_successor_chain_evaluation is False
    assert benchmark_calls[0].competition_id == "BENCH_V3"
    assert benchmark_calls[0].model_version == "poisson-v3.1-baseline"
    assert benchmark_calls[0].requested_by == "seed-test"


def test_core_replay_seed_warns_when_committed_runs_are_missing() -> None:
    result = run_recommendation_benchmark_core_replay_seed(
        FakeDatabase(),
        options=RecommendationBenchmarkCoreReplaySeedOptions(
            as_of_time_utc=_dt(2026, 5, 12, 0),
            pass_types=("1x1", "2x1"),
            modes=("single",),
            max_budgets=(10.0,),
        ),
        seed_runner=lambda database, *, options: _seed_result(options=options),
        benchmark_runner=lambda database, *, options: _benchmark_result(
            options=options,
            stored_run_ids=[21],
        ),
    )

    assert result.passed is False
    assert result.expected_scenario_count == 2
    assert result.stored_run_count == 1
    assert result.warnings == ["benchmark_seed_missing_committed_recommendation_runs"]


class FakeDatabase:
    def execute(self, query: str, params: QueryParams) -> None:
        raise AssertionError(f"unexpected execute: {query} {params}")

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise AssertionError(f"unexpected fetch_all: {query} {params}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError(f"unexpected fetch_one: {query} {params}")


def _seed_result(
    *,
    options: object,
    seed_calls: list[object] | None = None,
) -> RecommendationBaselineSeedResult:
    if seed_calls is not None:
        seed_calls.append(options)
    return RecommendationBaselineSeedResult(
        as_of_time_utc=_dt(2026, 5, 12, 0),
        reset=True,
        profile="happy_path",
        competition_id="BENCH_V3",
        fixture_count=8,
        fixture_ids=[f"bench_v3_{index:03d}" for index in range(1, 9)],
        odds_snapshot_count=24,
        result_count=8,
        summary_json={},
    )


def _benchmark_result(
    *,
    options: RecommendationBenchmarkOptions,
    stored_run_ids: list[int],
    benchmark_calls: list[RecommendationBenchmarkOptions] | None = None,
) -> RecommendationBenchmarkRunResult:
    if benchmark_calls is not None:
        benchmark_calls.append(options)
    scenarios = [
        _scenario_result(options, index=index, stored_run_id=stored_run_id)
        for index, stored_run_id in enumerate(stored_run_ids, 1)
    ]
    scenario_count = len(options.pass_types) * len(options.max_budgets)
    if "multiple" in options.modes and "2x1" in options.pass_types:
        scenario_count += len(options.max_budgets)
    return RecommendationBenchmarkRunResult(
        benchmark_key="recommendation_benchmark:seed",
        dry_run=False,
        strategy=options.strategy,
        scenario_count=scenario_count,
        completed_count=len(scenarios),
        failed_count=0,
        scenarios=scenarios,
        warnings=[],
        summary_json={},
    )


def _scenario_result(
    options: RecommendationBenchmarkOptions,
    *,
    index: int,
    stored_run_id: int,
) -> RecommendationBenchmarkScenarioResult:
    mode = "multiple" if index == 3 else "single"
    pass_type = "2x1" if index >= 2 else "1x1"
    scenario = RecommendationBenchmarkScenario(
        scenario_key=f"seed:{index}",
        as_of_time_utc=options.normalized_as_of_times_utc[0],
        lookback_hours=options.lookback_hours,
        pass_type=pass_type,
        mode=mode,
        max_budget=options.max_budgets[0],
    )
    validation = RecommendationCoreValidationRunResult(
        run_key=f"core_validation:{index}",
        dry_run=False,
        as_of_time_utc=options.normalized_as_of_times_utc[0],
        window_start_utc=options.normalized_as_of_times_utc[0],
        window_end_utc=options.normalized_as_of_times_utc[0],
        replay_window_start_utc=options.normalized_as_of_times_utc[0],
        replay_window_end_utc=options.normalized_as_of_times_utc[0],
        pass_type=pass_type,
        mode=mode,
        strategy=options.strategy,
        warnings=[],
        summary_json={"global_best_stored_run_id": stored_run_id},
    )
    return RecommendationBenchmarkScenarioResult(
        scenario=scenario,
        status="completed",
        validation=validation,
        warnings=[],
        metrics_json={},
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
