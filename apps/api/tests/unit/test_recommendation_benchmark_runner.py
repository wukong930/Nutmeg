from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from nutmeg.database import DatabaseRow, QueryParams
from nutmeg.recommendations import (
    RecommendationBenchmarkOptions,
    RecommendationBenchmarkRunResult,
    RecommendationCoreValidationOptions,
    RecommendationCoreValidationRunResult,
    StoredRecommendationBenchmarkRun,
    build_recommendation_benchmark_history_comparison,
    build_recommendation_benchmark_scenarios,
    run_recommendation_benchmark,
)
from nutmeg.recommendations.benchmark_runner import (
    INSERT_RECOMMENDATION_BENCHMARK_RUN_QUERY,
    LIST_RECENT_RECOMMENDATION_BENCHMARK_RUNS_QUERY,
    LIST_RECOMMENDATION_BENCHMARK_HISTORY_QUERY,
    PostgresRecommendationBenchmarkRunRepository,
    _options_from_args,
    _parse_args,
)


def test_benchmark_runner_builds_budget_pass_type_mode_matrix() -> None:
    options = RecommendationBenchmarkOptions(
        as_of_times_utc=(_dt(2026, 5, 4, 12),),
        lookback_hours=12,
        pass_types=("1x1", "6x1"),
        modes=("single", "multiple"),
        max_budgets=(10.0, 20.0),
        run_prematch_pipeline=True,
    )
    scenarios = build_recommendation_benchmark_scenarios(options)

    assert [scenario.pass_type for scenario in scenarios] == [
        "1x1",
        "6x1",
        "6x1",
        "1x1",
        "6x1",
        "6x1",
    ]
    assert [scenario.mode for scenario in scenarios] == [
        "single",
        "single",
        "multiple",
        "single",
        "single",
        "multiple",
    ]
    assert [scenario.max_budget for scenario in scenarios] == [
        10.0,
        10.0,
        10.0,
        20.0,
        20.0,
        20.0,
    ]


def test_benchmark_runner_aggregates_core_validation_metrics() -> None:
    calls: list[RecommendationCoreValidationOptions] = []

    def validation_runner(
        database: object,
        *,
        options: RecommendationCoreValidationOptions,
    ) -> RecommendationCoreValidationRunResult:
        calls.append(options)
        return _validation_result(
            options,
            final_hit=options.max_budget == 20.0 and options.mode == "multiple",
            roi=0.10 if options.max_budget == 20.0 else -0.05,
            effective_chain_count=2 if options.max_budget == 20.0 else 1,
            effective_chain_active_edge_count=1 if options.max_budget == 20.0 else 0,
            superseded_source_run_count=1 if options.max_budget == 20.0 else 0,
            ambiguous_successor_source_count=1 if options.pass_type == "1x1" else 0,
            stale_recommendation_count=1 if options.max_budget == 10.0 else 0,
            successor_recompute_required_count=(
                1 if options.pass_type == "6x1" and options.mode == "multiple" else 0
            ),
            upset_opportunity_count=1,
            upset_capture_count=1 if options.pass_type == "1x1" else 0,
            warning=(
                "core_replay:no_result_rows_for_replayed_recommendation_fixtures"
                if options.pass_type == "1x1"
                else None
            ),
        )

    result = run_recommendation_benchmark(
        FakeDatabase(),
        options=RecommendationBenchmarkOptions(
            as_of_times_utc=(_dt(2026, 5, 4, 12),),
            pass_types=("1x1", "6x1"),
            modes=("single", "multiple"),
            max_budgets=(10.0, 20.0),
            run_prematch_pipeline=False,
        ),
        validation_runner=validation_runner,
    )

    assert len(calls) == 6
    assert calls[0].run_prematch_pipeline is False
    assert calls[0].pass_type == "1x1"
    assert calls[0].mode == "single"
    assert calls[-1].pass_type == "6x1"
    assert calls[-1].mode == "multiple"
    assert calls[-1].max_budget == 20.0
    assert result.benchmark_key.startswith("recommendation_benchmark:")
    assert result.scenario_count == 6
    assert result.completed_count == 6
    assert result.failed_count == 0
    assert result.summary_json["global_best_selected_count"] == 6
    assert result.summary_json["unified_candidate_pool_present_count"] == 6
    assert result.summary_json["unified_candidate_pool_valid_candidate_count"] == 12
    assert result.summary_json["unified_candidate_pool_unique_family_count"] == 3
    assert result.summary_json["unified_candidate_pool_unique_family_keys"] == [
        "standalone_single:1x1:single",
        "single_parlay:6x1:single",
        "multiple_parlay:6x1:multiple",
    ]
    assert result.summary_json["unified_candidate_pool_selection_mismatch_count"] == 0
    assert result.summary_json["unified_candidate_pool_selected_2x1_count"] == 0
    assert result.summary_json["unified_candidate_pool_multiple_value_candidate_count"] == 2
    assert (
        result.summary_json[
            "unified_candidate_pool_multiple_value_admitted_candidate_count"
        ]
        == 2
    )
    assert (
        result.summary_json[
            "unified_candidate_pool_multiple_value_rejected_candidate_count"
        ]
        == 0
    )
    assert (
        result.summary_json["unified_candidate_pool_multiple_value_extra_option_count"]
        == 4
    )
    assert result.summary_json[
        "unified_candidate_pool_selected_multiple_value_statuses"
    ] == ["not_multiple", "admitted"]
    assert (
        result.summary_json[
            "unified_candidate_pool_selected_multiple_value_admitted_count"
        ]
        == 2
    )
    assert (
        result.summary_json[
            "unified_candidate_pool_selected_multiple_value_rejected_count"
        ]
        == 0
    )
    assert (
        result.summary_json[
            "unified_candidate_pool_selected_multiple_extra_option_count"
        ]
        == 4
    )
    assert result.summary_json[
        "unified_candidate_pool_multiple_value_rejection_reason_counts"
    ] == {}
    assert result.summary_json["core_replay_ready_count"] == 6
    assert result.summary_json["chain_integrity_ready_count"] == 6
    assert result.summary_json["chain_integrity_total_critical_issue_count"] == 0
    assert result.summary_json["successor_chain_evaluation_passed_count"] == 6
    assert result.summary_json["successor_chain_effective_leaf_count"] == 6
    assert result.summary_json["successor_chain_active_edge_count"] == 3
    assert result.summary_json["successor_chain_critical_issue_count"] == 0
    assert result.summary_json["successor_chain_ambiguous_source_count"] == 2
    assert result.summary_json["core_replay_effective_evaluated_run_count"] == 6
    assert result.summary_json["effective_chain_count"] == 9
    assert result.summary_json["effective_chain_active_edge_count"] == 3
    assert result.summary_json["superseded_source_run_count"] == 3
    assert result.summary_json["ambiguous_successor_source_count"] == 2
    assert result.summary_json["stale_recommendation_count"] == 3
    assert result.summary_json["successor_recompute_required_count"] == 2
    assert result.summary_json["final_hit_sample_size"] == 6
    assert result.summary_json["final_hit_count"] == 1
    assert result.summary_json["average_core_replay_roi"] == pytest.approx(0.025)
    assert result.summary_json["upset_opportunity_count"] == 6
    assert result.summary_json["upset_capture_count"] == 2
    assert result.summary_json["upset_capture_rate"] == pytest.approx(1 / 3)
    assert result.warnings == [
        "core_replay:no_result_rows_for_replayed_recommendation_fixtures"
    ]


def test_benchmark_runner_records_failed_scenarios_when_configured() -> None:
    def validation_runner(
        database: object,
        *,
        options: RecommendationCoreValidationOptions,
    ) -> RecommendationCoreValidationRunResult:
        if options.max_budget == 20.0:
            raise RuntimeError("validation database unavailable")
        return _validation_result(options, final_hit=False, roi=0.0)

    result = run_recommendation_benchmark(
        FakeDatabase(),
        options=RecommendationBenchmarkOptions(
            as_of_times_utc=(_dt(2026, 5, 4, 12),),
            pass_types=("2x1",),
            modes=("single",),
            max_budgets=(10.0, 20.0),
            continue_on_error=True,
        ),
        validation_runner=validation_runner,
    )

    assert result.completed_count == 1
    assert result.failed_count == 1
    assert result.summary_json["failed_count"] == 1
    assert result.scenarios[1].status == "failed"
    assert result.scenarios[1].error_message == "validation database unavailable"
    assert result.scenarios[1].metrics_json["error_type"] == "RuntimeError"


def test_benchmark_runner_saves_report_and_compares_with_previous_run() -> None:
    previous = StoredRecommendationBenchmarkRun(
        recommendation_benchmark_run_id=41,
        benchmark_key="same-key",
        dry_run=True,
        strategy="accuracy_first",
        scenario_count=1,
        completed_count=1,
        failed_count=0,
        global_best_selected_count=1,
        core_replay_ready_count=0,
        core_replay_total_run_count=1,
        core_replay_total_settled_run_count=1,
        final_hit_sample_size=1,
        final_hit_count=0,
        average_core_replay_roi=-0.10,
        warning_count=2,
        summary_json={
            "core_replay_ready_count": 0,
            "final_hit_sample_size": 1,
            "final_hit_count": 0,
            "average_core_replay_roi": -0.10,
            "failed_count": 0,
            "warning_count": 2,
        },
        created_at=_dt(2026, 5, 3, 12),
    )
    repository = FakeBenchmarkRepository(previous=previous)

    result = run_recommendation_benchmark(
        FakeDatabase(),
        options=RecommendationBenchmarkOptions(
            as_of_times_utc=(_dt(2026, 5, 4, 12),),
            pass_types=("2x1",),
            modes=("single",),
            max_budgets=(10.0,),
            save_report=True,
        ),
        validation_runner=lambda database, *, options: _validation_result(
            options,
            final_hit=True,
            roi=0.20,
        ),
        benchmark_repository=repository,
    )

    assert repository.listed_key == result.benchmark_key
    assert repository.saved is not None
    assert result.stored_report is not None
    assert result.stored_report.recommendation_benchmark_run_id == 99
    assert result.history_comparison_json["status"] == "improved"
    assert result.summary_json["history_status"] == "improved"
    assert result.summary_json["previous_benchmark_run_id"] == 41


def test_benchmark_history_comparison_marks_mixed_results() -> None:
    current = _benchmark_result(summary={
        "core_replay_ready_count": 0,
        "final_hit_sample_size": 2,
        "final_hit_count": 2,
        "average_core_replay_roi": 0.12,
        "failed_count": 1,
        "warning_count": 3,
    })
    previous = StoredRecommendationBenchmarkRun(
        recommendation_benchmark_run_id=11,
        benchmark_key=current.benchmark_key,
        dry_run=True,
        strategy="accuracy_first",
        scenario_count=2,
        completed_count=2,
        failed_count=0,
        global_best_selected_count=2,
        core_replay_ready_count=2,
        core_replay_total_run_count=2,
        core_replay_total_settled_run_count=2,
        final_hit_sample_size=2,
        final_hit_count=1,
        average_core_replay_roi=0.02,
        warning_count=0,
        summary_json={
            "core_replay_ready_count": 2,
            "final_hit_sample_size": 2,
            "final_hit_count": 1,
            "average_core_replay_roi": 0.02,
            "failed_count": 0,
            "warning_count": 0,
        },
        created_at=_dt(2026, 5, 2, 12),
    )

    comparison = build_recommendation_benchmark_history_comparison(
        current,
        previous=previous,
    )

    assert comparison["status"] == "mixed"
    assert comparison["previous_benchmark_run_id"] == 11
    assert comparison["current_final_hit_rate"] == 1.0
    assert comparison["previous_final_hit_rate"] == 0.5
    assert comparison["deltas"] == {
        "final_hit_rate_delta": 0.5,
        "average_core_replay_roi_delta": 0.09999999999999999,
        "upset_capture_rate_delta": None,
        "core_replay_ready_count_delta": -2,
        "ambiguous_successor_source_count_delta": 0,
        "stale_recommendation_count_delta": 0,
        "successor_recompute_required_count_delta": 0,
        "failed_count_delta": 1,
        "warning_count_delta": 3,
    }


def test_postgres_benchmark_repository_writes_and_lists_runs() -> None:
    database = FakeBenchmarkDatabase()
    repository = PostgresRecommendationBenchmarkRunRepository(database)
    result = _benchmark_result(summary={
        "as_of_times": ["2026-05-04T12:00:00+00:00"],
        "pass_types": ["2x1"],
        "modes": ["single"],
        "budgets": [10.0],
        "global_best_selected_count": 1,
        "core_replay_ready_count": 1,
        "core_replay_total_run_count": 2,
        "core_replay_total_settled_run_count": 2,
        "final_hit_sample_size": 1,
        "final_hit_count": 1,
        "average_core_replay_roi": 0.15,
        "warning_count": 0,
    })

    listed = repository.list_recent(benchmark_key=result.benchmark_key, limit=1)
    stored = repository.save_run(result)

    assert listed[0].recommendation_benchmark_run_id == 98
    assert stored.recommendation_benchmark_run_id == 99
    assert database.fetch_all_calls == [
        (
            LIST_RECENT_RECOMMENDATION_BENCHMARK_RUNS_QUERY,
            {"benchmark_key": result.benchmark_key, "limit": 1},
        )
    ]
    insert_query, params = database.fetch_one_calls[0]
    assert insert_query == INSERT_RECOMMENDATION_BENCHMARK_RUN_QUERY
    assert params["benchmark_key"] == result.benchmark_key
    assert params["average_core_replay_roi"] == 0.15
    assert params["source"] == "recommendation_benchmark_runner_v3_1"


def test_postgres_benchmark_repository_lists_history_with_optional_filters() -> None:
    database = FakeBenchmarkDatabase()
    repository = PostgresRecommendationBenchmarkRunRepository(database)

    items = repository.list_history(
        benchmark_key="recommendation_benchmark:test",
        strategy="accuracy_first",
        limit=500,
    )

    assert items[0].benchmark_key == "recommendation_benchmark:test"
    assert database.fetch_all_calls == [
        (
            LIST_RECOMMENDATION_BENCHMARK_HISTORY_QUERY,
            {
                "benchmark_key": "recommendation_benchmark:test",
                "strategy": "accuracy_first",
                "limit": 200,
            },
        )
    ]


def test_benchmark_runner_can_stop_on_first_error() -> None:
    def validation_runner(
        database: object,
        *,
        options: RecommendationCoreValidationOptions,
    ) -> RecommendationCoreValidationRunResult:
        raise RuntimeError("stop immediately")

    with pytest.raises(RuntimeError, match="stop immediately"):
        run_recommendation_benchmark(
            FakeDatabase(),
            options=RecommendationBenchmarkOptions(
                as_of_times_utc=(_dt(2026, 5, 4, 12),),
                pass_types=("2x1",),
                modes=("single",),
                max_budgets=(10.0,),
                continue_on_error=False,
            ),
            validation_runner=validation_runner,
        )


def test_benchmark_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--as-of-time-utc",
            "2026-05-04T12:00:00Z",
            "--as-of-time-utc",
            "2026-05-05T12:00:00Z",
            "--lookback-hours",
            "48",
            "--pass-types",
            "2x1,6x1",
            "--modes",
            "single,multiple",
            "--budgets",
            "10,30",
            "--include-prematch-pipeline",
            "--skip-chain-integrity",
            "--commit",
            "--save-report",
            "--save-audit",
            "--stop-on-error",
            "--no-require-odds",
        ]
    )

    options = _options_from_args(args)

    assert options.as_of_times_utc == (
        _dt(2026, 5, 4, 12),
        _dt(2026, 5, 5, 12),
    )
    assert options.lookback_hours == 48
    assert options.pass_types == ("2x1", "6x1")
    assert options.modes == ("single", "multiple")
    assert options.max_budgets == (10.0, 30.0)
    assert options.run_prematch_pipeline is True
    assert options.run_chain_integrity is False
    assert options.run_successor_chain_evaluation is False
    assert options.dry_run is False
    assert options.save_report is True
    assert options.save_pipeline_audit is True
    assert options.continue_on_error is False
    assert options.require_odds is False


class FakeDatabase:
    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        raise AssertionError(f"unexpected fetch_all: {query} {params}")

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        raise AssertionError(f"unexpected fetch_one: {query} {params}")


class FakeBenchmarkRepository:
    def __init__(self, previous: StoredRecommendationBenchmarkRun | None = None) -> None:
        self.previous = previous
        self.listed_key: str | None = None
        self.saved: object | None = None

    def list_recent(
        self,
        *,
        benchmark_key: str,
        limit: int = 1,
    ) -> list[StoredRecommendationBenchmarkRun]:
        self.listed_key = benchmark_key
        return [self.previous] if self.previous is not None else []

    def save_run(
        self,
        result: RecommendationBenchmarkRunResult,
        *,
        source: str = "recommendation_benchmark_runner_v3_1",
    ) -> StoredRecommendationBenchmarkRun:
        self.saved = result
        return StoredRecommendationBenchmarkRun(
            recommendation_benchmark_run_id=99,
            benchmark_key=result.benchmark_key,
            dry_run=True,
            strategy="accuracy_first",
            scenario_count=result.scenario_count,
            completed_count=result.completed_count,
            failed_count=result.failed_count,
            global_best_selected_count=1,
            core_replay_ready_count=1,
            core_replay_total_run_count=1,
            core_replay_total_settled_run_count=1,
            final_hit_sample_size=1,
            final_hit_count=1,
            average_core_replay_roi=0.20,
            warning_count=0,
            summary_json=result.summary_json,
            created_at=_dt(2026, 5, 4, 13),
        )


class FakeBenchmarkDatabase:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, QueryParams]] = []
        self.fetch_one_calls: list[tuple[str, QueryParams]] = []

    def fetch_all(self, query: str, params: QueryParams) -> Sequence[DatabaseRow]:
        self.fetch_all_calls.append((query, params))
        return [
            {
                "recommendation_benchmark_run_id": 98,
                "benchmark_key": params["benchmark_key"],
                "dry_run": True,
                "strategy": "accuracy_first",
                "scenario_count": 1,
                "completed_count": 1,
                "failed_count": 0,
                "global_best_selected_count": 1,
                "core_replay_ready_count": 1,
                "core_replay_total_run_count": 2,
                "core_replay_total_settled_run_count": 2,
                "final_hit_sample_size": 1,
                "final_hit_count": 1,
                "average_core_replay_roi": 0.10,
                "warning_count": 0,
                "history_comparison_json": {},
                "summary_json": {"average_core_replay_roi": 0.10},
                "created_at": _dt(2026, 5, 3, 12),
            }
        ]

    def fetch_one(self, query: str, params: QueryParams) -> DatabaseRow | None:
        self.fetch_one_calls.append((query, params))
        return {
            "recommendation_benchmark_run_id": 99,
            "benchmark_key": params["benchmark_key"],
            "dry_run": params["dry_run"],
            "strategy": params["strategy"],
            "scenario_count": params["scenario_count"],
            "completed_count": params["completed_count"],
            "failed_count": params["failed_count"],
            "global_best_selected_count": params["global_best_selected_count"],
            "core_replay_ready_count": params["core_replay_ready_count"],
            "core_replay_total_run_count": params["core_replay_total_run_count"],
            "core_replay_total_settled_run_count": (
                params["core_replay_total_settled_run_count"]
            ),
            "final_hit_sample_size": params["final_hit_sample_size"],
            "final_hit_count": params["final_hit_count"],
            "average_core_replay_roi": params["average_core_replay_roi"],
            "warning_count": params["warning_count"],
            "history_comparison_json": params["history_comparison_json"],
            "summary_json": params["summary_json"],
            "created_at": _dt(2026, 5, 4, 12),
        }


def _benchmark_result(*, summary: dict[str, object]) -> RecommendationBenchmarkRunResult:
    return RecommendationBenchmarkRunResult(
        benchmark_key="recommendation_benchmark:test",
        dry_run=True,
        strategy="accuracy_first",
        scenario_count=1,
        completed_count=1,
        failed_count=0,
        warnings=[],
        summary_json=summary,
    )


def _validation_result(
    options: RecommendationCoreValidationOptions,
    *,
    final_hit: bool,
    roi: float,
    effective_chain_count: int = 1,
    effective_chain_active_edge_count: int = 0,
    superseded_source_run_count: int = 0,
    ambiguous_successor_source_count: int = 0,
    stale_recommendation_count: int = 0,
    successor_recompute_required_count: int = 0,
    successor_chain_evaluation_passed: bool = True,
    upset_opportunity_count: int = 0,
    upset_capture_count: int = 0,
    warning: str | None = None,
) -> RecommendationCoreValidationRunResult:
    warnings = [warning] if warning is not None else []
    return RecommendationCoreValidationRunResult(
        run_key=f"core_validation:{options.pass_type}:{options.mode}:{options.max_budget}",
        dry_run=options.dry_run,
        as_of_time_utc=options.normalized_as_of_time_utc,
        window_start_utc=options.pipeline_window_start_utc,
        window_end_utc=options.normalized_as_of_time_utc,
        replay_window_start_utc=options.normalized_replay_window_start_utc,
        replay_window_end_utc=options.normalized_replay_window_end_utc,
        pass_type=options.pass_type,
        mode=options.mode,
        strategy=options.strategy,
        warnings=warnings,
        summary_json={
            "global_best_candidate_count": 10,
            "global_best_generated_option_count": 2,
            "global_best_selected": True,
            "unified_candidate_pool_present": True,
            "unified_candidate_pool_candidate_count": 2,
            "unified_candidate_pool_valid_candidate_count": 2,
            "unified_candidate_pool_family_count": 1,
            "unified_candidate_pool_candidate_family_keys": [
                _family_key(options.pass_type, options.mode)
            ],
            "unified_candidate_pool_selected_family_key": _family_key(
                options.pass_type,
                options.mode,
            ),
            "unified_candidate_pool_selected_pass_type": options.pass_type,
            "unified_candidate_pool_two_x_one_is_candidate_family": (
                options.pass_type == "2x1"
            ),
            "unified_candidate_pool_correct_score_candidate_present": False,
            "unified_candidate_pool_handicap_candidate_present": (
                options.pass_type != "1x1"
            ),
            "unified_candidate_pool_multiple_value_candidate_count": (
                1 if options.mode == "multiple" else 0
            ),
            "unified_candidate_pool_multiple_value_admitted_candidate_count": (
                1 if options.mode == "multiple" else 0
            ),
            "unified_candidate_pool_multiple_value_rejected_candidate_count": 0,
            "unified_candidate_pool_multiple_value_extra_option_count": (
                2 if options.mode == "multiple" else 0
            ),
            "unified_candidate_pool_selected_multiple_value_status": (
                "admitted" if options.mode == "multiple" else "not_multiple"
            ),
            "unified_candidate_pool_selected_multiple_value_admitted": True,
            "unified_candidate_pool_selected_multiple_extra_option_count": (
                2 if options.mode == "multiple" else 0
            ),
            "unified_candidate_pool_multiple_value_rejection_reason_counts": {},
            "unified_candidate_pool_selection_mismatch": False,
            "unified_candidate_pool_selected_2x1": options.pass_type == "2x1",
            "prematch_triggered_run_count": 0,
            "core_replay_ready": True,
            "core_replay_run_count": 1,
            "core_replay_settled_run_count": 1,
            "core_replay_effective_evaluated_run_count": 1,
            "core_replay_final_hit": final_hit,
            "core_replay_roi": roi,
            "effective_chain_count": effective_chain_count,
            "effective_chain_active_edge_count": effective_chain_active_edge_count,
            "effective_leaf_run_count": 1,
            "superseded_source_run_count": superseded_source_run_count,
            "ambiguous_successor_source_count": ambiguous_successor_source_count,
            "current_answer_count": 1,
            "stale_recommendation_count": stale_recommendation_count,
            "expired_kickoff_recommendation_count": 0,
            "stale_incident_recommendation_count": 0,
            "successor_recompute_required_count": successor_recompute_required_count,
            "chain_integrity_ready": True,
            "chain_integrity_issue_count": 0,
            "chain_integrity_critical_issue_count": 0,
            "chain_integrity_source_status_sync_required_count": 0,
            "successor_chain_evaluation_passed": successor_chain_evaluation_passed,
            "successor_chain_effective_leaf_count": 1,
            "successor_chain_active_edge_count": effective_chain_active_edge_count,
            "successor_chain_critical_issue_count": 0,
            "successor_chain_ambiguous_source_count": ambiguous_successor_source_count,
            "successor_chain_source_status_sync_required_count": 0,
            "upset_opportunity_count": upset_opportunity_count,
            "upset_capture_count": upset_capture_count,
            "warning_count": len(warnings),
        },
    )


def _family_key(pass_type: str | None, mode: str | None) -> str:
    if pass_type == "1x1":
        return "standalone_single:1x1:single"
    option_type = "multiple_parlay" if mode == "multiple" else "single_parlay"
    return f"{option_type}:{pass_type}:{mode}"


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
