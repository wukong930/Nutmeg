from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    RecommendationBenchmarkStrategyComparisonOptions,
    StoredRecommendationBenchmarkRun,
    run_recommendation_benchmark_strategy_comparison,
)
from nutmeg.recommendations.benchmark_strategy_comparison import (
    _options_from_args,
    _parse_args,
)
from nutmeg.recommendations.models import RecommendationStrategy


def test_strategy_comparison_passes_when_candidate_beats_baseline() -> None:
    baseline = _benchmark_run(
        recommendation_benchmark_run_id=21,
        benchmark_key="recommendation_benchmark:accuracy",
        strategy="accuracy_first",
        final_hit_sample_size=4,
        final_hit_count=2,
        average_core_replay_roi=-0.03,
    )
    candidate = _benchmark_run(
        recommendation_benchmark_run_id=22,
        benchmark_key="recommendation_benchmark:value",
        strategy="value_first",
        final_hit_sample_size=4,
        final_hit_count=3,
        average_core_replay_roi=0.08,
    )
    repository = FakeStrategyComparisonRepository([candidate, baseline])

    result = run_recommendation_benchmark_strategy_comparison(
        FakeDatabase(),
        options=RecommendationBenchmarkStrategyComparisonOptions(
            min_final_hit_sample_size=4,
            min_final_hit_rate_delta=0.0,
        ),
        repository=repository,
    )

    assert result.passed is True
    assert result.status == "passed"
    assert result.candidate_run == candidate
    assert result.baseline_run == baseline
    assert _summary_float(result.summary_json, "average_core_replay_roi_delta") == (
        pytest.approx(0.11)
    )
    assert _summary_float(result.summary_json, "final_hit_rate_delta") == pytest.approx(
        0.25
    )
    assert result.summary_json["matrix_match"] is True
    assert repository.calls == [
        {"benchmark_key": None, "strategy": "value_first", "limit": 20},
        {"benchmark_key": None, "strategy": "accuracy_first", "limit": 20},
    ]


def test_strategy_comparison_fails_on_matrix_mismatch() -> None:
    baseline = _benchmark_run(
        recommendation_benchmark_run_id=31,
        benchmark_key="recommendation_benchmark:accuracy",
        strategy="accuracy_first",
        average_core_replay_roi=0.00,
    )
    candidate = _benchmark_run(
        recommendation_benchmark_run_id=32,
        benchmark_key="recommendation_benchmark:value",
        strategy="value_first",
        average_core_replay_roi=0.10,
        as_of_times=["2026-05-13T00:00:00+00:00"],
    )

    result = run_recommendation_benchmark_strategy_comparison(
        FakeDatabase(),
        options=RecommendationBenchmarkStrategyComparisonOptions(),
        repository=FakeStrategyComparisonRepository([candidate, baseline]),
    )

    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert result.status == "failed"
    assert failed_checks == {"matrix_match"}
    assert result.summary_json["matrix_match"] is False
    assert result.warnings == [
        "benchmark_strategy_comparison:failed_check:matrix_match"
    ]


def test_strategy_comparison_handles_missing_history_strictly() -> None:
    result = run_recommendation_benchmark_strategy_comparison(
        FakeDatabase(),
        options=RecommendationBenchmarkStrategyComparisonOptions(),
        repository=FakeStrategyComparisonRepository([]),
    )

    assert result.passed is False
    assert result.status == "insufficient_history"
    assert result.summary_json["candidate_history_count"] == 0
    assert result.summary_json["baseline_history_count"] == 0
    assert result.warnings == [
        "benchmark_strategy_comparison:no_candidate_history",
        "benchmark_strategy_comparison:no_baseline_history",
    ]


def test_strategy_comparison_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--benchmark-key",
            "recommendation_benchmark:matrix",
            "--candidate-benchmark-key",
            "recommendation_benchmark:value",
            "--baseline-benchmark-key",
            "recommendation_benchmark:accuracy",
            "--candidate-strategy",
            "value_first",
            "--baseline-strategy",
            "accuracy_first",
            "--history-limit",
            "5",
            "--allow-missing-history",
            "--no-require-matrix-match",
            "--min-scenario-count",
            "4",
            "--min-completed-ratio",
            "0.9",
            "--max-failed-count",
            "1",
            "--min-core-replay-ready-ratio",
            "0.8",
            "--min-final-hit-sample-size",
            "10",
            "--min-roi-delta",
            "0.02",
            "--skip-roi-delta-check",
            "--min-final-hit-rate-delta",
            "-0.05",
            "--no-fail-process",
        ]
    )

    options = _options_from_args(args)

    assert options.benchmark_key == "recommendation_benchmark:matrix"
    assert options.candidate_benchmark_key == "recommendation_benchmark:value"
    assert options.baseline_benchmark_key == "recommendation_benchmark:accuracy"
    assert options.candidate_strategy == "value_first"
    assert options.baseline_strategy == "accuracy_first"
    assert options.history_limit == 5
    assert options.allow_missing_history is True
    assert options.require_matrix_match is False
    assert options.min_scenario_count == 4
    assert options.min_completed_ratio == 0.9
    assert options.max_failed_count == 1
    assert options.min_core_replay_ready_ratio == 0.8
    assert options.min_final_hit_sample_size == 10
    assert options.min_average_core_replay_roi_delta is None
    assert options.min_final_hit_rate_delta == -0.05


class FakeStrategyComparisonRepository:
    def __init__(self, history: list[StoredRecommendationBenchmarkRun]) -> None:
        self.history = history
        self.calls: list[dict[str, object]] = []

    def list_history(
        self,
        *,
        benchmark_key: str | None = None,
        strategy: RecommendationStrategy | None = None,
        limit: int = 20,
    ) -> list[StoredRecommendationBenchmarkRun]:
        self.calls.append(
            {
                "benchmark_key": benchmark_key,
                "strategy": strategy,
                "limit": limit,
            }
        )
        return [
            item
            for item in self.history
            if (benchmark_key is None or item.benchmark_key == benchmark_key)
            and (strategy is None or item.strategy == strategy)
        ][:limit]


class FakeDatabase:
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise AssertionError(f"unexpected fetch_all: {query} {params}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError(f"unexpected fetch_one: {query} {params}")


def _benchmark_run(
    *,
    recommendation_benchmark_run_id: int,
    benchmark_key: str,
    strategy: RecommendationStrategy,
    scenario_count: int = 4,
    completed_count: int = 4,
    failed_count: int = 0,
    core_replay_ready_count: int = 4,
    final_hit_sample_size: int = 4,
    final_hit_count: int = 2,
    average_core_replay_roi: float | None = 0.0,
    as_of_times: list[str] | None = None,
) -> StoredRecommendationBenchmarkRun:
    matrix_as_of_times = as_of_times or ["2026-05-12T00:00:00+00:00"]
    return StoredRecommendationBenchmarkRun(
        recommendation_benchmark_run_id=recommendation_benchmark_run_id,
        benchmark_key=benchmark_key,
        dry_run=False,
        strategy=strategy,
        scenario_count=scenario_count,
        completed_count=completed_count,
        failed_count=failed_count,
        global_best_selected_count=completed_count,
        core_replay_ready_count=core_replay_ready_count,
        core_replay_total_run_count=completed_count,
        core_replay_total_settled_run_count=final_hit_sample_size,
        final_hit_sample_size=final_hit_sample_size,
        final_hit_count=final_hit_count,
        average_core_replay_roi=average_core_replay_roi,
        warning_count=0,
        summary_json={
            "as_of_times": matrix_as_of_times,
            "pass_types": ["2x1", "4x1"],
            "modes": ["multiple"],
            "budgets": [10.0],
            "failed_count": failed_count,
            "warning_count": 0,
            "core_replay_ready_count": core_replay_ready_count,
            "final_hit_sample_size": final_hit_sample_size,
            "final_hit_count": final_hit_count,
            "average_core_replay_roi": average_core_replay_roi,
        },
        created_at=datetime(2026, 5, 12, 0, tzinfo=UTC),
    )


def _summary_float(summary: dict[str, object], key: str) -> float:
    value = summary[key]
    assert isinstance(value, float)
    return value
