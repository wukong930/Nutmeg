from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketMovementRuntimeReplayEvidence,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    HistoricalRecommendationSuccessorChainEvaluationEvidence,
    HistoricalRecommendationSuiteQualityGateOptions,
    run_historical_recommendation_backtest_suite,
    run_historical_recommendation_suite_quality_gate,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationLifecycleQualityCycleEvidence,
    _backtest_options_from_args,
    _historical_slices_from_args,
    _options_from_args,
    _parse_args,
    _profile_reference_no_correct_score_lane_options,
    _profile_reference_no_upset_lane_options,
)


def test_historical_suite_quality_gate_passes_improved_solver_suite() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [
            _solver_improvement_slice(slice_id="solver_gate_slice_a"),
            _solver_improvement_slice(slice_id="solver_gate_slice_b"),
        ],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )

    result = run_historical_recommendation_suite_quality_gate(
        suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            min_slice_count=2,
            min_comparison_count=2,
            min_final_hit_sample_size=2,
            min_candidate_final_hit_rate=1.0,
            min_profit_loss_delta=0.01,
            min_solver_selected_scenario_count=2,
            min_final_answer_changed_count=2,
            max_warning_count=0,
        ),
    )

    assert result.passed is True
    assert result.status == "passed"
    assert result.suite_status == "improved"
    assert result.summary_json["failed_checks"] == []
    assert result.summary_json["candidate_final_hit_sample_size"] == 2
    assert result.aggregate_deltas_json["final_hit_rate_delta"] == 1.0


def test_historical_suite_quality_gate_fails_regression_and_threshold_breaks() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [_solver_improvement_slice(slice_id="solver_gate_regression_slice")],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )
    regressed_suite = suite.model_copy(
        update={
            "status": "mixed",
            "warnings": ["historical_suite_regressed"],
            "summary_json": {
                **suite.summary_json,
                "candidate_roi": -0.50,
            },
            "aggregate_deltas_json": {
                "final_hit_rate_delta": -0.25,
                "final_hit_count_delta": -1,
                "roi_delta": -0.10,
                "profit_loss_delta": -2.0,
                "brier_score_delta": 0.15,
                "log_loss_delta": 0.20,
                "mean_calibration_error_delta": 0.10,
                "upset_capture_rate_delta": -0.25,
                "upset_capture_count_delta": -1,
                "candidate_solver_selected_scenario_count": 0,
                "final_answer_changed_count": 0,
            },
        }
    )

    result = run_historical_recommendation_suite_quality_gate(
        regressed_suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            min_final_hit_rate_delta=0.0,
            min_candidate_roi=0.0,
            min_roi_delta=0.0,
            min_profit_loss_delta=0.0,
            max_brier_score_delta=0.0,
            max_log_loss_delta=0.0,
            max_mean_calibration_error_delta=0.0,
            min_upset_capture_rate_delta=0.0,
            min_solver_selected_scenario_count=1,
            min_final_answer_changed_count=1,
            max_warning_count=0,
        ),
    )

    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert result.status == "failed"
    assert failed_checks == {
        "suite_status",
        "candidate_roi",
        "final_hit_rate_delta",
        "roi_delta",
        "profit_loss_delta",
        "brier_score_delta",
        "log_loss_delta",
        "mean_calibration_error_delta",
        "upset_capture_rate_delta",
        "solver_selected_scenario_count",
        "final_answer_changed_count",
        "warning_count",
    }
    assert result.summary_json["suite_status"] == "mixed"
    assert result.warnings == [
        "historical_suite_quality_gate:failed_check:candidate_roi",
        "historical_suite_quality_gate:failed_check:suite_status",
        "historical_suite_quality_gate:failed_check:final_hit_rate_delta",
        "historical_suite_quality_gate:failed_check:roi_delta",
        "historical_suite_quality_gate:failed_check:profit_loss_delta",
        "historical_suite_quality_gate:failed_check:brier_score_delta",
        "historical_suite_quality_gate:failed_check:log_loss_delta",
        "historical_suite_quality_gate:failed_check:mean_calibration_error_delta",
        "historical_suite_quality_gate:failed_check:upset_capture_rate_delta",
        "historical_suite_quality_gate:failed_check:solver_selected_scenario_count",
        "historical_suite_quality_gate:failed_check:final_answer_changed_count",
        "historical_suite_quality_gate:failed_check:warning_count",
    ]


def test_historical_suite_quality_gate_blocks_incomplete_final_hit_coverage() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [
            _solver_improvement_slice(slice_id="solver_gate_coverage_slice_a"),
            _solver_improvement_slice(slice_id="solver_gate_coverage_slice_b"),
        ],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )
    incomplete_suite = suite.model_copy(
        update={
            "summary_json": {
                **suite.summary_json,
                "candidate_final_hit_sample_size": 1,
                "candidate_final_hit_rate": 1.0,
            },
        },
    )

    result = run_historical_recommendation_suite_quality_gate(
        incomplete_suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            min_final_hit_sample_size=1,
            min_final_hit_coverage_ratio=1.0,
        ),
    )

    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert "final_hit_coverage_ratio" in failed_checks
    assert result.summary_json["candidate_final_hit_sample_size"] == 1
    assert result.summary_json["candidate_final_hit_coverage_ratio"] == 0.5


def test_historical_suite_quality_gate_can_require_dynamic_mixed_final_answers() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [
            _dynamic_mixed_recommendation_slice("dynamic_mixed_gate_slice_a"),
            _dynamic_mixed_recommendation_slice("dynamic_mixed_gate_slice_b"),
        ],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=4.0,
            min_probability=0.10,
            allowed_markets=("1x2", "cn_handicap_1x2"),
        ),
    )

    result = run_historical_recommendation_suite_quality_gate(
        suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            min_slice_count=2,
            min_comparison_count=2,
            min_final_hit_sample_size=2,
            min_candidate_dynamic_mixed_final_answer_count=2,
            min_candidate_dynamic_mixed_final_answer_rate=1.0,
            min_candidate_handicap_final_answer_count=2,
        ),
    )
    failed_result = run_historical_recommendation_suite_quality_gate(
        suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            min_final_hit_sample_size=2,
            min_candidate_correct_score_final_answer_count=1,
        ),
    )

    assert suite.summary_json["candidate_dynamic_mixed_final_answer_count"] == 2
    assert suite.summary_json["candidate_dynamic_mixed_final_answer_rate"] == 1.0
    assert suite.summary_json["candidate_handicap_final_answer_count"] == 2
    assert suite.summary_json["candidate_final_answer_market_type_counts"] == {
        "1x2": 2,
        "cn_handicap_1x2": 2,
    }
    assert result.passed is True
    assert result.summary_json["candidate_dynamic_mixed_final_answer_count"] == 2
    assert result.summary_json["candidate_dynamic_mixed_final_answer_rate"] == 1.0
    assert result.summary_json["candidate_handicap_final_answer_count"] == 2
    assert result.summary_json["candidate_final_answer_market_type_counts"] == {
        "1x2": 2,
        "cn_handicap_1x2": 2,
    }
    assert failed_result.passed is False
    assert "candidate_correct_score_final_answer_count" in {
        check.name for check in failed_result.checks if check.status == "failed"
    }


def test_historical_suite_quality_gate_requires_successor_effective_final_only_evidence() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [_solver_improvement_slice(slice_id="successor_gate_slice")],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )

    missing_result = run_historical_recommendation_suite_quality_gate(
        suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            require_successor_chain_evaluation=True,
            min_successor_effective_leaf_count=1,
            min_successor_active_edge_count=1,
        ),
    )

    assert missing_result.passed is False
    assert "successor_chain_evaluation_present" in {
        check.name for check in missing_result.checks if check.status == "failed"
    }

    successor_evidence = HistoricalRecommendationSuccessorChainEvaluationEvidence(
        passed=True,
        summary_json={
            "effective_leaf_count": 1,
            "active_edge_count": 1,
            "chain_integrity_critical_issue_count": 0,
            "ambiguous_successor_source_count": 0,
            "source_status_sync_required_count": 0,
        },
    )

    result = run_historical_recommendation_suite_quality_gate(
        suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            require_successor_chain_evaluation=True,
            min_successor_effective_leaf_count=1,
            min_successor_active_edge_count=1,
            max_successor_critical_issue_count=0,
            max_successor_ambiguous_source_count=0,
            max_successor_source_status_sync_required_count=0,
        ),
        successor_chain_evaluation=successor_evidence,
    )

    assert result.passed is True
    assert result.summary_json["successor_chain_evaluation_present"] is True
    assert result.summary_json["successor_chain_evaluation_passed"] is True
    assert result.summary_json["successor_effective_final_only_ready"] is True
    assert result.summary_json["successor_effective_leaf_count"] == 1
    assert result.summary_json["successor_active_edge_count"] == 1


def test_historical_suite_quality_gate_requires_market_movement_runtime_replay_evidence() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [_solver_improvement_slice(slice_id="market_movement_runtime_gate_slice")],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )

    missing_result = run_historical_recommendation_suite_quality_gate(
        suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            require_market_movement_runtime_replay=True,
            min_market_movement_runtime_replay_rule_count=1,
            min_market_movement_runtime_replay_selected_rule_count=1,
            min_market_movement_runtime_replay_accepted_count=1,
            min_market_movement_runtime_replay_adjusted_fixture_count=1,
            min_market_movement_runtime_replay_adjusted_prediction_count=1,
        ),
    )
    result = run_historical_recommendation_suite_quality_gate(
        suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            require_market_movement_runtime_replay=True,
            min_market_movement_runtime_replay_rule_count=1,
            min_market_movement_runtime_replay_selected_rule_count=1,
            min_market_movement_runtime_replay_accepted_count=1,
            min_market_movement_runtime_replay_adjusted_fixture_count=100,
            min_market_movement_runtime_replay_adjusted_prediction_count=300,
            min_market_movement_runtime_replay_final_hit_rate_delta=0.0,
            min_market_movement_runtime_replay_roi_delta=0.0,
            min_market_movement_runtime_replay_profit_loss_delta=0.0,
            max_market_movement_runtime_replay_brier_score_delta=0.0,
            max_market_movement_runtime_replay_log_loss_delta=0.0,
            max_market_movement_runtime_replay_mean_calibration_error_delta=0.0,
        ),
        market_movement_runtime_replay=_market_movement_runtime_replay_evidence(),
        market_movement_runtime_replay_report_path=Path("tmp/runtime_replay.json"),
    )

    assert missing_result.passed is False
    assert "market_movement_runtime_replay_present" in {
        check.name for check in missing_result.checks if check.status == "failed"
    }
    assert result.passed is True
    assert result.market_movement_runtime_replay_present is True
    assert result.market_movement_runtime_replay_passed is True
    assert result.summary_json["market_movement_runtime_replay_present"] is True
    assert result.summary_json["market_movement_runtime_replay_allowed"] is True
    assert result.summary_json["market_movement_runtime_replay_status"] == (
        "runtime_shadow_replay_passed"
    )
    assert result.summary_json["market_movement_runtime_replay_adjusted_fixture_count"] == 120
    assert result.summary_json["market_movement_runtime_replay_brier_score_delta"] == (
        -0.001288
    )
    assert result.summary_json["market_movement_runtime_replay_public_changed"] is False


def test_historical_suite_quality_gate_blocks_harmful_market_movement_runtime_replay() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [_solver_improvement_slice(slice_id="market_movement_runtime_harm_slice")],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )

    result = run_historical_recommendation_suite_quality_gate(
        suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            require_market_movement_runtime_replay=True,
            min_market_movement_runtime_replay_final_hit_rate_delta=0.0,
            max_market_movement_runtime_replay_brier_score_delta=0.0,
        ),
        market_movement_runtime_replay=_market_movement_runtime_replay_evidence(
            passed=False,
            runtime_allowed=False,
            status="shadow_replay_failed",
            final_hit_rate_delta=-0.01,
            brier_score_delta=0.02,
            production_changed=True,
            public_changed=True,
        ),
    )

    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert {
        "market_movement_runtime_replay_passed",
        "market_movement_runtime_replay_allowed",
        "market_movement_runtime_replay_passed_status",
        "market_movement_runtime_replay_final_hit_rate_delta",
        "market_movement_runtime_replay_brier_score_delta",
        "market_movement_runtime_replay_production_unchanged",
        "market_movement_runtime_replay_public_unchanged",
    }.issubset(failed_checks)


def test_historical_suite_quality_gate_blocks_weak_competition_roi() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [_solver_improvement_slice(slice_id="solver_gate_competition_roi_slice")],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )

    result = run_historical_recommendation_suite_quality_gate(
        suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            min_competition_candidate_roi=10.0,
        ),
    )

    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert "competition_candidate_roi" in failed_checks
    assert result.summary_json["worst_competition_id"] == "TEST"
    competition_candidate_roi = result.summary_json["competition_candidate_roi"]
    assert isinstance(competition_candidate_roi, dict)
    assert "TEST" in competition_candidate_roi


def test_historical_suite_quality_gate_blocks_profile_reference_calibration_regression() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [_solver_improvement_slice(slice_id="solver_gate_profile_reference_slice")],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )
    candidate_suite = suite.model_copy(
        update={
            "summary_json": {
                **suite.summary_json,
                "candidate_final_hit_rate": 0.70,
                "candidate_roi": 0.20,
                "candidate_profit_loss": 2.0,
                "candidate_brier_score": 0.25,
                "candidate_log_loss": 0.65,
                "candidate_mean_calibration_error": 0.45,
                "candidate_upset_capture_rate": 0.02,
            }
        }
    )
    reference_suite = suite.model_copy(
        update={
            "suite_key": "historical_recommendation_backtest_suite:reference_no_lane",
            "summary_json": {
                **suite.summary_json,
                "candidate_final_hit_rate": 0.70,
                "candidate_roi": 0.10,
                "candidate_profit_loss": 1.0,
                "candidate_brier_score": 0.20,
                "candidate_log_loss": 0.60,
                "candidate_mean_calibration_error": 0.40,
                "candidate_upset_capture_rate": 0.02,
            },
        }
    )

    result = run_historical_recommendation_suite_quality_gate(
        candidate_suite,
        reference_suite=reference_suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            min_profile_reference_final_hit_rate_delta=0.0,
            min_profile_reference_roi_delta=0.0,
            min_profile_reference_profit_loss_delta=0.0,
            max_profile_reference_brier_score_delta=0.0,
            max_profile_reference_log_loss_delta=0.0,
            max_profile_reference_mean_calibration_error_delta=0.0,
            min_profile_reference_upset_capture_rate_delta=0.0,
        ),
    )

    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert failed_checks == {
        "profile_reference_brier_score_delta",
        "profile_reference_log_loss_delta",
        "profile_reference_mean_calibration_error_delta",
    }
    assert result.summary_json["profile_reference_enabled"] is True
    assert result.summary_json["profile_reference_suite_key"] == (
        "historical_recommendation_backtest_suite:reference_no_lane"
    )
    assert result.summary_json["profile_reference_deltas"] == {
        "final_hit_rate_delta": 0.0,
        "roi_delta": 0.1,
        "profit_loss_delta": 1.0,
        "brier_score_delta": 0.04999999999999999,
        "log_loss_delta": 0.050000000000000044,
        "mean_calibration_error_delta": 0.04999999999999999,
        "upset_capture_rate_delta": 0.0,
    }


def test_historical_suite_quality_gate_profile_reference_passes_without_regression() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [_solver_improvement_slice(slice_id="solver_gate_profile_reference_pass_slice")],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )
    candidate_suite = suite.model_copy(
        update={
            "summary_json": {
                **suite.summary_json,
                "candidate_upset_capture_rate": 0.01,
            }
        }
    )
    reference_suite = suite.model_copy(
        update={
            "suite_key": "historical_recommendation_backtest_suite:reference_no_lane",
            "summary_json": {
                **suite.summary_json,
                "candidate_final_hit_rate": 0.50,
                "candidate_roi": -0.10,
                "candidate_profit_loss": -1.0,
                "candidate_brier_score": 0.40,
                "candidate_log_loss": 1.00,
                "candidate_mean_calibration_error": 0.60,
                "candidate_upset_capture_rate": 0.0,
            },
        }
    )

    result = run_historical_recommendation_suite_quality_gate(
        candidate_suite,
        reference_suite=reference_suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            min_profile_reference_final_hit_rate_delta=0.0,
            min_profile_reference_roi_delta=0.0,
            min_profile_reference_profit_loss_delta=0.0,
            max_profile_reference_brier_score_delta=0.0,
            max_profile_reference_log_loss_delta=0.0,
            max_profile_reference_mean_calibration_error_delta=0.0,
            min_profile_reference_upset_capture_rate_delta=0.0,
        ),
    )

    assert result.passed is True
    profile_reference_deltas = result.summary_json["profile_reference_deltas"]
    assert isinstance(profile_reference_deltas, dict)
    final_hit_rate_delta = profile_reference_deltas["final_hit_rate_delta"]
    brier_score_delta = profile_reference_deltas["brier_score_delta"]
    assert isinstance(final_hit_rate_delta, int | float)
    assert isinstance(brier_score_delta, int | float)
    assert final_hit_rate_delta > 0
    assert brier_score_delta <= 0


def test_historical_suite_quality_gate_blocks_concentrated_correlation_exposure() -> None:
    source_slice = _solver_improvement_slice(slice_id="solver_gate_correlation_exposure_slice")
    concentrated_slice = source_slice.model_copy(
        deep=True,
        update={
            "fixtures": [
                fixture.model_copy(update={"home_team_name": "Favorite FC"})
                for fixture in source_slice.fixtures
            ],
        },
    )
    suite = run_historical_recommendation_backtest_suite(
        [concentrated_slice],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )

    result = run_historical_recommendation_suite_quality_gate(
        suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            max_final_answer_correlation_exposure=1,
        ),
    )

    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert "final_answer_correlation_exposure" in failed_checks
    assert result.summary_json["max_final_answer_correlation_exposure"] == 2
    assert result.summary_json["correlated_final_answer_count"] == 1


def test_historical_suite_quality_gate_passes_with_lifecycle_quality_cycle() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [_solver_improvement_slice(slice_id="solver_gate_lifecycle_slice")],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )
    lifecycle_cycle = _lifecycle_quality_cycle()

    result = run_historical_recommendation_suite_quality_gate(
        suite,
        lifecycle_quality_cycle=lifecycle_cycle,
        lifecycle_quality_cycle_report_path=Path("tmp/lifecycle_cycle.json"),
        options=HistoricalRecommendationSuiteQualityGateOptions(
            require_lifecycle_quality_cycle=True,
            min_lifecycle_effective_leaf_count=1,
            min_lifecycle_active_edge_count=1,
            max_lifecycle_critical_issue_count=0,
            max_lifecycle_source_status_sync_required_count=0,
        ),
    )

    assert result.passed is True
    assert result.lifecycle_quality_cycle_present is True
    assert result.lifecycle_quality_cycle_passed is True
    assert result.summary_json["lifecycle_quality_cycle_present"] is True
    assert result.summary_json["lifecycle_persisted_smoke_present"] is True
    assert result.summary_json["lifecycle_source_status_synced"] is True
    assert result.summary_json["lifecycle_effective_leaf_count"] == 1
    assert result.summary_json["lifecycle_active_edge_count"] == 1


def test_historical_suite_quality_gate_blocks_missing_lifecycle_cycle_when_required() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [_solver_improvement_slice(slice_id="solver_gate_missing_lifecycle_slice")],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )

    result = run_historical_recommendation_suite_quality_gate(
        suite,
        options=HistoricalRecommendationSuiteQualityGateOptions(
            require_lifecycle_quality_cycle=True,
        ),
    )

    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert "lifecycle_quality_cycle_present" in failed_checks
    assert (
        "historical_suite_quality_gate:failed_check:lifecycle_quality_cycle_present"
        in result.warnings
    )


def test_historical_suite_quality_gate_blocks_unsynced_lifecycle_source() -> None:
    suite = run_historical_recommendation_backtest_suite(
        [_solver_improvement_slice(slice_id="solver_gate_unsynced_lifecycle_slice")],
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
        ),
    )

    result = run_historical_recommendation_suite_quality_gate(
        suite,
        lifecycle_quality_cycle=_lifecycle_quality_cycle(source_status_synced=False),
        options=HistoricalRecommendationSuiteQualityGateOptions(
            require_lifecycle_quality_cycle=True,
        ),
    )

    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert "lifecycle_source_status_synced" in failed_checks


def test_historical_suite_quality_gate_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--output-path",
            "tmp/gate.json",
            "--pass-types",
            "2x1,4x1",
            "--modes",
            "single",
            "--strategy",
            "accuracy_first",
            "--unit-stake",
            "3",
            "--max-budget",
            "12",
            "--min-probability",
            "0.2",
            "--min-data-quality-score",
            "70",
            "--allowed-markets",
            "1x2,cn_handicap_1x2,correct_score",
            "--max-outcomes-per-fixture",
            "3",
            "--upset-threshold",
            "0.4",
            "--candidate-fixture-limit",
            "48",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "6",
            "--final-answer-scenario-variant-count",
            "4",
            "--derive-market-context-signals",
            "--upset-exposure-reserve",
            "--upset-exposure-reserve-fixture-count",
            "5",
            "--upset-exposure-reserve-max-candidates-per-fixture",
            "2",
            "--upset-exposure-reserve-min-protection-score",
            "0.48",
            "--upset-exposure-reserve-min-probability",
            "0.18",
            "--upset-exposure-reserve-max-decimal-odds",
            "8.5",
            "--upset-final-answer-lane",
            "--upset-final-answer-lane-pass-type",
            "2x1",
            "--upset-final-answer-lane-mode",
            "single",
            "--upset-final-answer-lane-candidate-limit",
            "16",
            "--upset-final-answer-lane-min-protection-score",
            "0.52",
            "--upset-final-answer-lane-min-probability",
            "0.21",
            "--upset-final-answer-lane-min-decimal-odds",
            "3.5",
            "--upset-final-answer-lane-max-decimal-odds",
            "7.5",
            "--upset-final-answer-lane-min-model-edge",
            "-0.01",
            "--upset-final-answer-lane-max-model-edge",
            "0.02",
            "--upset-final-answer-lane-competitions",
            "ESP_LA_LIGA,JPN_J1",
            "--upset-final-answer-lane-excluded-competitions",
            "FRA_LIGUE_1",
            "--upset-final-answer-lane-min-calibration-score",
            "0.87",
            "--upset-final-answer-lane-min-model-confidence-score",
            "0.86",
            "--upset-final-answer-lane-min-odds-stability-score",
            "0.74",
            "--upset-final-answer-lane-max-volatility-penalty",
            "0.08",
            "--upset-final-answer-lane-max-hit-probability-deficit",
            "0.20",
            "--upset-final-answer-lane-score-boost",
            "0.35",
            "--short-price-negative-edge-guardrail",
            "--short-price-negative-edge-max-decimal-odds",
            "1.42",
            "--short-price-negative-edge-min-probability",
            "0.72",
            "--short-price-negative-edge-max-model-edge",
            "-0.02",
            "--short-price-negative-edge-soft-penalty",
            "--short-price-negative-edge-soft-penalty-strength",
            "0.8",
            "--short-price-negative-edge-soft-penalty-competitions",
            "ESP_LA_LIGA,JPN_J1",
            "--final-answer-quality-signal-penalty",
            "--final-answer-quality-signal-penalty-strength",
            "0.06",
            "--final-answer-quality-signal-probability-min",
            "0.10",
            "--final-answer-quality-signal-probability-max",
            "0.52",
            "--final-answer-quality-signal-min-decimal-odds",
            "2.00",
            "--final-answer-quality-signal-max-decimal-odds",
            "10.00",
            "--final-answer-quality-signal-max-model-edge",
            "0.01",
            "--final-answer-quality-signal-score-min",
            "0.20",
            "--final-answer-quality-signal-score-max",
            "0.90",
            "--final-answer-quality-signal-competitions",
            "ESP_SEGUNDA_DIVISION",
            "--correct-score-final-answer-lane",
            "--correct-score-final-answer-lane-pass-types",
            "2x1,8x1",
            "--correct-score-final-answer-lane-mode",
            "single",
            "--correct-score-final-answer-lane-modes",
            "single,multiple",
            "--correct-score-final-answer-lane-candidate-limit",
            "64",
            "--correct-score-final-answer-lane-min-probability",
            "0.02",
            "--correct-score-final-answer-lane-min-correct-score-probability",
            "0.08",
            "--correct-score-final-answer-lane-max-correct-score-per-selection",
            "2",
            "--correct-score-final-answer-lane-score-boost",
            "0.25",
            "--correct-score-final-answer-lane-max-hit-probability-deficit",
            "0.18",
            "--correct-score-final-answer-lane-min-roi-delta",
            "-0.04",
            "--correct-score-final-answer-lane-outcomes",
            "1-0,2-1",
            "--baseline-optimizer-profile",
            "heuristic",
            "--candidate-optimizer-profile",
            "solver",
            "--min-slice-count",
            "2",
            "--min-comparison-count",
            "3",
            "--min-final-hit-sample-size",
            "4",
            "--min-final-hit-coverage-ratio",
            "0.8",
            "--min-candidate-final-hit-rate",
            "0.62",
            "--min-candidate-roi",
            "-0.10",
            "--min-competition-candidate-roi",
            "-0.30",
            "--max-final-answer-correlation-exposure",
            "3",
            "--min-candidate-dynamic-mixed-final-answer-count",
            "6",
            "--min-candidate-dynamic-mixed-final-answer-rate",
            "0.7",
            "--min-candidate-handicap-final-answer-count",
            "5",
            "--min-candidate-correct-score-final-answer-count",
            "4",
            "--min-candidate-multiple-choice-final-answer-count",
            "3",
            "--fail-on-suite-statuses",
            "regressed,mixed,unchanged",
            "--min-final-hit-rate-delta",
            "0.01",
            "--min-roi-delta",
            "-0.05",
            "--min-profit-loss-delta",
            "-1",
            "--max-brier-score-delta",
            "0.02",
            "--max-log-loss-delta",
            "0.03",
            "--max-mean-calibration-error-delta",
            "0.04",
            "--profile-reference-no-upset-lane",
            "--profile-reference-no-correct-score-lane",
            "--lifecycle-quality-cycle-report-path",
            "tmp/lifecycle_cycle.json",
            "--require-lifecycle-quality-cycle",
            "--allow-missing-lifecycle-persisted-smoke",
            "--allow-unsynced-lifecycle-source-status",
            "--min-lifecycle-effective-leaf-count",
            "6",
            "--min-lifecycle-active-edge-count",
            "3",
            "--max-lifecycle-critical-issue-count",
            "1",
            "--max-lifecycle-source-status-sync-required-count",
            "2",
            "--successor-chain-evaluation-report-path",
            "tmp/successor_chain.json",
            "--require-successor-chain-evaluation",
            "--min-successor-effective-leaf-count",
            "2",
            "--min-successor-active-edge-count",
            "1",
            "--max-successor-critical-issue-count",
            "0",
            "--max-successor-ambiguous-source-count",
            "0",
            "--max-successor-source-status-sync-required-count",
            "0",
            "--market-movement-runtime-replay-report-path",
            "tmp/market_movement_runtime_replay.json",
            "--require-market-movement-runtime-replay",
            "--allow-market-movement-runtime-replay-not-allowed",
            "--allow-market-movement-runtime-replay-non-passed-status",
            "--min-market-movement-runtime-replay-rule-count",
            "1",
            "--min-market-movement-runtime-replay-selected-rule-count",
            "1",
            "--min-market-movement-runtime-replay-accepted-count",
            "1",
            "--min-market-movement-runtime-replay-adjusted-fixture-count",
            "120",
            "--min-market-movement-runtime-replay-adjusted-prediction-count",
            "360",
            "--min-market-movement-runtime-replay-final-hit-rate-delta",
            "0.0",
            "--min-market-movement-runtime-replay-roi-delta",
            "0.01",
            "--min-market-movement-runtime-replay-profit-loss-delta",
            "1.0",
            "--max-market-movement-runtime-replay-brier-score-delta",
            "0.02",
            "--max-market-movement-runtime-replay-log-loss-delta",
            "0.03",
            "--max-market-movement-runtime-replay-mean-calibration-error-delta",
            "0.04",
            "--allow-market-movement-runtime-replay-production-change",
            "--allow-market-movement-runtime-replay-public-change",
            "--min-profile-reference-final-hit-rate-delta",
            "0.0",
            "--min-profile-reference-roi-delta",
            "0.01",
            "--min-profile-reference-profit-loss-delta",
            "1.5",
            "--max-profile-reference-brier-score-delta",
            "0.0",
            "--max-profile-reference-log-loss-delta",
            "0.0",
            "--max-profile-reference-mean-calibration-error-delta",
            "0.0",
            "--min-profile-reference-upset-capture-rate-delta",
            "0.001",
            "--min-upset-capture-sample-size",
            "5",
            "--min-upset-capture-rate-delta",
            "0.06",
            "--min-upset-final-answer-lane-selected-candidate-count",
            "9",
            "--min-solver-selected-scenario-count",
            "7",
            "--min-final-answer-changed-count",
            "8",
            "--max-warning-count",
            "1",
        ]
    )

    backtest_options = _backtest_options_from_args(args)
    gate_options = _options_from_args(args)

    assert args.output_path == Path("tmp/gate.json")
    assert backtest_options.pass_types == ("2x1", "4x1")
    assert backtest_options.modes == ("single",)
    assert backtest_options.unit_stake == 3
    assert backtest_options.max_budget == 12
    assert backtest_options.min_probability == 0.2
    assert backtest_options.min_data_quality_score == 70
    assert backtest_options.allowed_markets == (
        "1x2",
        "cn_handicap_1x2",
        "correct_score",
    )
    assert backtest_options.max_outcomes_per_fixture == 3
    assert backtest_options.upset_threshold == 0.4
    assert backtest_options.candidate_fixture_limit == 48
    assert backtest_options.max_candidates_per_fixture == 2
    assert backtest_options.scenario_candidate_fixture_buffer == 6
    assert backtest_options.final_answer_scenario_variant_count == 4
    assert backtest_options.derive_market_context_signals is True
    assert backtest_options.upset_exposure_reserve is True
    assert backtest_options.upset_exposure_reserve_fixture_count == 5
    assert backtest_options.upset_exposure_reserve_max_candidates_per_fixture == 2
    assert backtest_options.upset_exposure_reserve_min_protection_score == 0.48
    assert backtest_options.upset_exposure_reserve_min_probability == 0.18
    assert backtest_options.upset_exposure_reserve_max_decimal_odds == 8.5
    assert backtest_options.upset_final_answer_lane is True
    assert backtest_options.upset_final_answer_lane_pass_type == "2x1"
    assert backtest_options.upset_final_answer_lane_mode == "single"
    assert backtest_options.upset_final_answer_lane_candidate_limit == 16
    assert backtest_options.upset_final_answer_lane_min_protection_score == 0.52
    assert backtest_options.upset_final_answer_lane_min_probability == 0.21
    assert backtest_options.upset_final_answer_lane_min_decimal_odds == 3.5
    assert backtest_options.upset_final_answer_lane_max_decimal_odds == 7.5
    assert backtest_options.upset_final_answer_lane_min_model_edge == -0.01
    assert backtest_options.upset_final_answer_lane_max_model_edge == 0.02
    assert backtest_options.upset_final_answer_lane_competition_ids == (
        "ESP_LA_LIGA",
        "JPN_J1",
    )
    assert backtest_options.upset_final_answer_lane_excluded_competition_ids == ("FRA_LIGUE_1",)
    assert backtest_options.upset_final_answer_lane_min_calibration_score == 0.87
    assert backtest_options.upset_final_answer_lane_min_model_confidence_score == 0.86
    assert backtest_options.upset_final_answer_lane_min_odds_stability_score == 0.74
    assert backtest_options.upset_final_answer_lane_max_volatility_penalty == 0.08
    assert backtest_options.upset_final_answer_lane_max_hit_probability_deficit == 0.20
    assert backtest_options.upset_final_answer_lane_score_boost == 0.35
    assert backtest_options.short_price_negative_edge_guardrail is True
    assert backtest_options.short_price_negative_edge_max_decimal_odds == 1.42
    assert backtest_options.short_price_negative_edge_min_probability == 0.72
    assert backtest_options.short_price_negative_edge_max_model_edge == -0.02
    assert backtest_options.short_price_negative_edge_soft_penalty is True
    assert backtest_options.short_price_negative_edge_soft_penalty_strength == 0.8
    assert backtest_options.short_price_negative_edge_soft_penalty_competition_ids == (
        "ESP_LA_LIGA",
        "JPN_J1",
    )
    assert backtest_options.final_answer_quality_signal_penalty is True
    assert backtest_options.final_answer_quality_signal_penalty_strength == 0.06
    assert backtest_options.final_answer_quality_signal_probability_min == 0.10
    assert backtest_options.final_answer_quality_signal_probability_max == 0.52
    assert backtest_options.final_answer_quality_signal_min_decimal_odds == 2.00
    assert backtest_options.final_answer_quality_signal_max_decimal_odds == 10.00
    assert backtest_options.final_answer_quality_signal_max_model_edge == 0.01
    assert backtest_options.final_answer_quality_signal_score_min == 0.20
    assert backtest_options.final_answer_quality_signal_score_max == 0.90
    assert backtest_options.final_answer_quality_signal_competition_ids == ("ESP_SEGUNDA_DIVISION",)
    assert backtest_options.correct_score_final_answer_lane is True
    assert backtest_options.correct_score_final_answer_lane_pass_types == ("2x1", "8x1")
    assert backtest_options.correct_score_final_answer_lane_mode == "single"
    assert backtest_options.correct_score_final_answer_lane_modes == ("single", "multiple")
    assert backtest_options.correct_score_final_answer_lane_candidate_limit == 64
    assert backtest_options.correct_score_final_answer_lane_min_probability == 0.02
    assert backtest_options.correct_score_final_answer_lane_min_correct_score_probability == 0.08
    assert backtest_options.correct_score_final_answer_lane_max_correct_score_per_selection == 2
    assert backtest_options.correct_score_final_answer_lane_score_boost == 0.25
    assert backtest_options.correct_score_final_answer_lane_max_hit_probability_deficit == 0.18
    assert backtest_options.correct_score_final_answer_lane_min_roi_delta == -0.04
    assert backtest_options.correct_score_final_answer_lane_outcomes == ("1-0", "2-1")
    assert gate_options.min_slice_count == 2
    assert gate_options.min_comparison_count == 3
    assert gate_options.min_final_hit_sample_size == 4
    assert gate_options.min_final_hit_coverage_ratio == 0.8
    assert gate_options.min_candidate_final_hit_rate == 0.62
    assert gate_options.min_candidate_roi == -0.10
    assert gate_options.min_competition_candidate_roi == -0.30
    assert gate_options.max_final_answer_correlation_exposure == 3
    assert gate_options.min_candidate_dynamic_mixed_final_answer_count == 6
    assert gate_options.min_candidate_dynamic_mixed_final_answer_rate == 0.7
    assert gate_options.min_candidate_handicap_final_answer_count == 5
    assert gate_options.min_candidate_correct_score_final_answer_count == 4
    assert gate_options.min_candidate_multiple_choice_final_answer_count == 3
    assert gate_options.fail_on_suite_statuses == ("regressed", "mixed", "unchanged")
    assert gate_options.min_final_hit_rate_delta == 0.01
    assert gate_options.min_roi_delta == -0.05
    assert gate_options.min_profit_loss_delta == -1
    assert gate_options.max_brier_score_delta == 0.02
    assert gate_options.max_log_loss_delta == 0.03
    assert gate_options.max_mean_calibration_error_delta == 0.04
    assert args.profile_reference_no_upset_lane is True
    assert args.profile_reference_no_correct_score_lane is True
    assert args.lifecycle_quality_cycle_report_path == Path("tmp/lifecycle_cycle.json")
    assert gate_options.require_lifecycle_quality_cycle is True
    assert gate_options.require_lifecycle_persisted_smoke is False
    assert gate_options.require_lifecycle_source_status_synced is False
    assert gate_options.min_lifecycle_effective_leaf_count == 6
    assert gate_options.min_lifecycle_active_edge_count == 3
    assert gate_options.max_lifecycle_critical_issue_count == 1
    assert gate_options.max_lifecycle_source_status_sync_required_count == 2
    assert args.successor_chain_evaluation_report_path == Path(
        "tmp/successor_chain.json"
    )
    assert gate_options.require_successor_chain_evaluation is True
    assert gate_options.min_successor_effective_leaf_count == 2
    assert gate_options.min_successor_active_edge_count == 1
    assert gate_options.max_successor_critical_issue_count == 0
    assert gate_options.max_successor_ambiguous_source_count == 0
    assert gate_options.max_successor_source_status_sync_required_count == 0
    assert args.market_movement_runtime_replay_report_path == Path(
        "tmp/market_movement_runtime_replay.json"
    )
    assert gate_options.require_market_movement_runtime_replay is True
    assert gate_options.require_market_movement_runtime_replay_allowed is False
    assert gate_options.require_market_movement_runtime_replay_passed_status is False
    assert gate_options.min_market_movement_runtime_replay_rule_count == 1
    assert gate_options.min_market_movement_runtime_replay_selected_rule_count == 1
    assert gate_options.min_market_movement_runtime_replay_accepted_count == 1
    assert gate_options.min_market_movement_runtime_replay_adjusted_fixture_count == 120
    assert gate_options.min_market_movement_runtime_replay_adjusted_prediction_count == 360
    assert gate_options.min_market_movement_runtime_replay_final_hit_rate_delta == 0.0
    assert gate_options.min_market_movement_runtime_replay_roi_delta == 0.01
    assert gate_options.min_market_movement_runtime_replay_profit_loss_delta == 1.0
    assert gate_options.max_market_movement_runtime_replay_brier_score_delta == 0.02
    assert gate_options.max_market_movement_runtime_replay_log_loss_delta == 0.03
    assert gate_options.max_market_movement_runtime_replay_mean_calibration_error_delta == (
        0.04
    )
    assert gate_options.require_market_movement_runtime_replay_production_unchanged is False
    assert gate_options.require_market_movement_runtime_replay_public_response_unchanged is False
    assert gate_options.min_profile_reference_final_hit_rate_delta == 0.0
    assert gate_options.min_profile_reference_roi_delta == 0.01
    assert gate_options.min_profile_reference_profit_loss_delta == 1.5
    assert gate_options.max_profile_reference_brier_score_delta == 0.0
    assert gate_options.max_profile_reference_log_loss_delta == 0.0
    assert gate_options.max_profile_reference_mean_calibration_error_delta == 0.0
    assert gate_options.min_profile_reference_upset_capture_rate_delta == 0.001
    assert gate_options.min_upset_capture_sample_size == 5
    assert gate_options.min_upset_capture_rate_delta == 0.06
    assert gate_options.min_upset_final_answer_lane_selected_candidate_count == 9
    assert gate_options.min_solver_selected_scenario_count == 7
    assert gate_options.min_final_answer_changed_count == 8
    assert gate_options.max_warning_count == 1


def test_profile_reference_no_upset_lane_options_disable_lane_only() -> None:
    options = HistoricalRecommendationBacktestOptions(
        pass_types=("2x1",),
        modes=("single",),
        upset_final_answer_lane=True,
        upset_final_answer_lane_score_boost=0.25,
        upset_final_answer_lane_competition_ids=("GER_BUNDESLIGA",),
    )

    reference_options = _profile_reference_no_upset_lane_options(options)

    assert reference_options.upset_final_answer_lane is False
    assert reference_options.upset_final_answer_lane_score_boost == 0.0
    assert reference_options.upset_final_answer_lane_competition_ids == ("GER_BUNDESLIGA",)
    assert reference_options.pass_types == options.pass_types


def test_profile_reference_no_correct_score_lane_options_disable_lane_only() -> None:
    options = HistoricalRecommendationBacktestOptions(
        pass_types=("2x1",),
        modes=("single",),
        correct_score_final_answer_lane=True,
        correct_score_final_answer_lane_score_boost=0.25,
        correct_score_final_answer_lane_pass_types=("2x1", "3x1"),
    )

    reference_options = _profile_reference_no_correct_score_lane_options(options)

    assert reference_options.correct_score_final_answer_lane is False
    assert reference_options.correct_score_final_answer_lane_score_boost == 0.0
    assert reference_options.correct_score_final_answer_lane_pass_types == (
        "2x1",
        "3x1",
    )
    assert reference_options.pass_types == options.pass_types


def test_historical_suite_quality_gate_cli_loads_manifest_without_slice_paths() -> None:
    args = _parse_args(
        [
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_knockout_suite.json",
            "--pass-types",
            "2x1",
            "--modes",
            "single",
        ]
    )

    loaded = _historical_slices_from_args(args)

    assert len(loaded.slices) == 1
    assert loaded.slices[0].metadata.slice_id == "euro_2024_knockout_sample_v1"
    assert loaded.manifest is not None
    assert loaded.manifest.manifest.suite_id == "euro_2024_knockout_suite_v1"
    assert loaded.warnings == []


def test_historical_suite_quality_gate_cli_accepts_multiple_manifests(
    tmp_path: Path,
) -> None:
    first_slice_path = tmp_path / "first_slice.json"
    second_slice_path = tmp_path / "second_slice.json"
    first_slice_path.write_text(
        _solver_improvement_slice("first_suite_slice").model_dump_json(indent=2),
        encoding="utf-8",
    )
    second_slice_path.write_text(
        _solver_improvement_slice("second_suite_slice").model_dump_json(indent=2),
        encoding="utf-8",
    )
    first_manifest_path = tmp_path / "first_manifest.json"
    second_manifest_path = tmp_path / "second_manifest.json"
    first_manifest_path.write_text(
        _manifest_json(suite_id="first_suite", slice_path=first_slice_path.name),
        encoding="utf-8",
    )
    second_manifest_path.write_text(
        _manifest_json(suite_id="second_suite", slice_path=second_slice_path.name),
        encoding="utf-8",
    )

    loaded = _historical_slices_from_args(
        _parse_args(
            [
                "--suite-manifest",
                str(first_manifest_path),
                "--suite-manifest",
                str(second_manifest_path),
            ]
        )
    )

    assert [historical_slice.metadata.slice_id for historical_slice in loaded.slices] == [
        "first_suite_slice",
        "second_suite_slice",
    ]
    assert loaded.manifest is None
    assert [manifest.manifest.suite_id for manifest in loaded.manifests] == [
        "first_suite",
        "second_suite",
    ]
    assert loaded.warnings == []


def _manifest_json(*, suite_id: str, slice_path: str) -> str:
    return (
        "{"
        f'"suite_id":"{suite_id}",'
        f'"name":"{suite_id}",'
        f'"slices":[{{"slice_path":"{slice_path}"}}]'
        "}"
    )


def _solver_improvement_slice(slice_id: str) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name="Unit test historical suite gate slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _comparison_fixture(
                "fixture_a",
                actual_home_goals=0,
                actual_away_goals=1,
                probability=0.75,
                decimal_odds=1.30,
                model_edge=0.20,
            ),
            _comparison_fixture(
                "fixture_b",
                actual_home_goals=1,
                actual_away_goals=1,
                probability=0.74,
                decimal_odds=1.31,
                model_edge=0.20,
            ),
            _comparison_fixture(
                "fixture_c",
                actual_home_goals=2,
                actual_away_goals=0,
                probability=0.67,
                decimal_odds=2.00,
                model_edge=-0.20,
            ),
            _comparison_fixture(
                "fixture_d",
                actual_home_goals=3,
                actual_away_goals=1,
                probability=0.67,
                decimal_odds=2.00,
                model_edge=-0.20,
            ),
        ],
    )


def _dynamic_mixed_recommendation_slice(slice_id: str) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name="Unit test dynamic mixed suite gate slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test mixed odds",
            prediction_source="unit test mixed predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id=f"{slice_id}_fixture_1x2",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="Plain Home",
                away_team_name="Plain Away",
                actual_home_goals=2,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-dynamic-mixed-gate-test",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="home_win",
                        probability=0.64,
                        decimal_odds=1.80,
                        market_probability=1 / 1.80,
                        data_quality_score=92,
                        model_confidence_score=0.88,
                        calibration_score=0.86,
                    )
                ],
            ),
            HistoricalFixture(
                fixture_id=f"{slice_id}_fixture_cn_handicap",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 20),
                home_team_name="Handicap Home",
                away_team_name="Handicap Away",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-dynamic-mixed-gate-test",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="cn_handicap_1x2",
                        outcome="handicap_draw",
                        probability=0.56,
                        decimal_odds=2.75,
                        market_probability=1 / 2.75,
                        data_quality_score=91,
                        model_confidence_score=0.87,
                        calibration_score=0.85,
                        line=-1.0,
                    )
                ],
            ),
        ],
    )


def _comparison_fixture(
    fixture_id: str,
    *,
    actual_home_goals: int,
    actual_away_goals: int,
    probability: float,
    decimal_odds: float,
    model_edge: float,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=_dt(2024, 6, 30, 18),
        home_team_name=f"{fixture_id} Home",
        away_team_name=f"{fixture_id} Away",
        actual_home_goals=actual_home_goals,
        actual_away_goals=actual_away_goals,
        prediction_time_utc=_dt(2024, 6, 29, 10),
        model_version="poisson-v3.1-historical-gate-test",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=probability,
                decimal_odds=decimal_odds,
                market_probability=1.0 / decimal_odds,
                model_edge=model_edge,
                data_quality_score=90,
                model_confidence_score=0.88,
                calibration_score=0.86,
                odds_stability_score=0.75,
            )
        ],
    )


def _lifecycle_quality_cycle(
    *,
    passed: bool = True,
    source_status_synced: bool = True,
) -> HistoricalRecommendationLifecycleQualityCycleEvidence:
    return HistoricalRecommendationLifecycleQualityCycleEvidence(
        cycle_key="historical_market_movement_segment_quality_cycle:unit-test",
        passed=passed,
        summary_json={
            "passed": passed,
            "persisted_lifecycle_smoke_present": True,
            "persisted_lifecycle_smoke_passed": passed,
            "persisted_lifecycle_source_status_synced": source_status_synced,
            "persisted_lifecycle_effective_leaf_count": 1,
            "persisted_lifecycle_active_edge_count": 1,
            "persisted_lifecycle_critical_issue_count": 0,
            "persisted_lifecycle_source_status_sync_required_count": 0,
        },
    )


def _market_movement_runtime_replay_evidence(
    *,
    passed: bool = True,
    runtime_allowed: bool = True,
    status: str = "runtime_shadow_replay_passed",
    final_hit_rate_delta: float = 0.0,
    brier_score_delta: float = -0.001288,
    production_changed: bool = False,
    public_changed: bool = False,
) -> HistoricalMarketMovementRuntimeReplayEvidence:
    return HistoricalMarketMovementRuntimeReplayEvidence(
        passed=passed,
        summary_json={
            "report_key": "historical_market_movement_risk_filter_runtime_replay:test",
            "status": status,
            "runtime_shadow_replay_allowed": runtime_allowed,
            "holdout_replay_allowed": runtime_allowed,
            "source_rule_profile_version": "market-movement-runtime-shadow-test",
            "rule_count": 1,
            "selected_rule_count": 1,
            "candidate_count": 1,
            "accepted_count": 1,
            "adjusted_fixture_count": 120,
            "adjusted_prediction_count": 360,
            "final_hit_rate_delta": final_hit_rate_delta,
            "roi_delta": 0.0,
            "profit_loss_delta": 0.0,
            "brier_score_delta": brier_score_delta,
            "log_loss_delta": -0.002761,
            "mean_calibration_error_delta": -0.001278,
            "production_recommendation_changed": production_changed,
            "public_response_changed": public_changed,
        },
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
