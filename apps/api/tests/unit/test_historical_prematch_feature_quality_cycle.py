from __future__ import annotations

from nutmeg.accuracy.historical_prematch_feature_ablation_grid import (
    HistoricalPrematchFeatureAblationGridOptions,
    build_historical_prematch_feature_ablation_grid_report,
)
from nutmeg.recommendations import build_enriched_historical_feature_sample
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestOptions,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_prematch_feature_final_answer_gate import (
    HistoricalPrematchFeatureFinalAnswerGateOptions,
    build_historical_prematch_feature_final_answer_gate_report,
)
from nutmeg.recommendations.historical_prematch_feature_quality_cycle import (
    HistoricalPrematchFeatureQualityCycleOptions,
    _options_from_args,
    _parse_args,
    run_historical_prematch_feature_quality_cycle,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)


def test_prematch_feature_quality_cycle_summarizes_final_answer_gate() -> None:
    historical_slice = build_enriched_historical_feature_sample().historical_slice
    grid_options = HistoricalPrematchFeatureAblationGridOptions(
        min_feature_data_quality_score=80.0,
        max_probability_shifts=(0.0, 0.08),
        odds_movement_weights=(0.0, 0.35),
        tracked_fragility_weights=(0.0, 1.0),
        lineup_strength_weights=(0.0,),
        draw_signal_weights=(0.0, 0.35),
        prediction_sample_limit=0,
    )
    grid_report = build_historical_prematch_feature_ablation_grid_report(
        [historical_slice],
        options=grid_options,
    )

    result = run_historical_prematch_feature_quality_cycle(
        [historical_slice],
        grid_report=grid_report,
        options=HistoricalPrematchFeatureQualityCycleOptions(
            final_answer_gate_options=HistoricalPrematchFeatureFinalAnswerGateOptions(
                top_candidate_limit=2,
                grid_options=grid_options,
                backtest_options=HistoricalRecommendationBacktestOptions(
                    pass_types=("1x1",),
                    modes=("single",),
                    unit_stake=2.0,
                    max_budget=4.0,
                    optimizer_profile="solver",
                ),
                quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
                    fail_on_suite_statuses=(),
                    min_final_hit_rate_delta=-1.0,
                    max_brier_score_delta=None,
                    max_log_loss_delta=None,
                    max_mean_calibration_error_delta=None,
                ),
            ),
        ),
    )

    assert result.status == "passed"
    assert result.passed is True
    assert result.slice_count == 1
    assert result.fixture_count == 6
    assert result.evaluated_candidate_count == 2
    assert result.passing_candidate_count >= 1
    assert result.best_quality_gate_passed is True
    assert result.summary_json["calculation_basis"] == (
        "historical_prematch_feature_quality_cycle_v3_1"
    )
    assert result.final_answer_gate_summary_json["shadow_only"] is True


def test_prematch_feature_quality_cycle_blocks_tiny_context_sample_promotion() -> None:
    historical_slice = load_historical_recommendation_slice(
        "configs/recommendations/historical_slices/enriched_features/"
        "euro_2024_knockout_prematch_context_enriched_v1.json"
    )
    grid_options = HistoricalPrematchFeatureAblationGridOptions(
        min_feature_data_quality_score=45.0,
        max_probability_shifts=(0.0, 0.12),
        odds_movement_weights=(0.0,),
        tracked_fragility_weights=(0.0, 1.0),
        lineup_strength_weights=(0.0, 0.7),
        draw_signal_weights=(0.0,),
        prediction_sample_limit=0,
    )
    grid_report = build_historical_prematch_feature_ablation_grid_report(
        [historical_slice],
        options=grid_options,
    )

    result = run_historical_prematch_feature_quality_cycle(
        [historical_slice],
        grid_report=grid_report,
        options=HistoricalPrematchFeatureQualityCycleOptions(
            final_answer_gate_options=HistoricalPrematchFeatureFinalAnswerGateOptions(
                top_candidate_limit=2,
                grid_options=grid_options,
                backtest_options=HistoricalRecommendationBacktestOptions(
                    pass_types=("1x1", "2x1"),
                    modes=("single",),
                    unit_stake=2.0,
                    max_budget=4.0,
                    optimizer_profile="solver",
                ),
                quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
                    fail_on_suite_statuses=(),
                    min_final_hit_sample_size=10,
                    min_final_hit_rate_delta=-1.0,
                    max_brier_score_delta=None,
                    max_log_loss_delta=None,
                    max_mean_calibration_error_delta=None,
                ),
            ),
        ),
    )

    assert result.status == "failed"
    assert result.passed is False
    assert result.slice_count == 1
    assert result.fixture_count == 2
    assert result.evaluated_candidate_count == 2
    assert result.passing_candidate_count == 0
    assert result.final_answer_gate_summary_json["shadow_only"] is True
    assert result.best_failed_quality_check_names == ["final_hit_sample_size"]
    assert "prematch_feature_final_answer_gate:no_passing_candidate" in result.warnings
    assert "prematch_feature_quality_cycle:no_passing_final_answer_candidate" in (
        result.warnings
    )


def test_prematch_feature_quality_cycle_can_summarize_existing_failed_gate() -> None:
    historical_slice = build_enriched_historical_feature_sample().historical_slice
    grid_options = HistoricalPrematchFeatureAblationGridOptions(
        min_feature_data_quality_score=80.0,
        max_probability_shifts=(0.0, 0.08),
        odds_movement_weights=(0.0,),
        tracked_fragility_weights=(0.0,),
        lineup_strength_weights=(0.0,),
        draw_signal_weights=(0.0,),
        prediction_sample_limit=0,
    )
    grid_report = build_historical_prematch_feature_ablation_grid_report(
        [historical_slice],
        options=grid_options,
    )
    gate_report = build_historical_prematch_feature_final_answer_gate_report(
        [historical_slice],
        grid_report=grid_report,
        options=HistoricalPrematchFeatureFinalAnswerGateOptions(
            top_candidate_limit=1,
            grid_options=grid_options,
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=4.0,
            ),
            quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
                fail_on_suite_statuses=(),
                min_final_hit_rate_delta=-1.0,
                max_brier_score_delta=None,
                max_log_loss_delta=None,
                max_mean_calibration_error_delta=None,
            ),
        ),
    )
    failed_gate = gate_report.model_copy(update={"passing_candidate_count": 0})

    result = run_historical_prematch_feature_quality_cycle(
        final_answer_gate_report=failed_gate,
    )

    assert result.status == "failed"
    assert result.passed is False
    assert "prematch_feature_quality_cycle:no_passing_final_answer_candidate" in (
        result.warnings
    )


def test_prematch_feature_quality_cycle_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--final-answer-gate-report-path",
            "tmp/final_answer_gate.json",
            "--output-path",
            "tmp/quality_cycle.json",
            "--final-answer-gate-output-path",
            "tmp/full_gate.json",
            "--cycle-id",
            "cycle-test",
            "--gate-id",
            "gate-test",
            "--top-candidate-limit",
            "3",
            "--allow-grid-regression-candidates",
            "--pass-types",
            "1x1,2x1",
            "--modes",
            "single",
            "--strategy",
            "value_first",
            "--unit-stake",
            "5",
            "--max-budget",
            "30",
            "--min-probability",
            "0.22",
            "--min-data-quality-score",
            "72",
            "--candidate-fixture-limit",
            "8",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "1",
            "--derive-market-context-signals",
            "--optimizer-profile",
            "heuristic",
            "--min-slice-count",
            "2",
            "--min-comparison-count",
            "2",
            "--min-final-hit-sample-size",
            "2",
            "--min-final-hit-rate-delta",
            "-0.10",
            "--max-brier-score-delta",
            "0.05",
            "--max-log-loss-delta",
            "0.06",
            "--max-mean-calibration-error-delta",
            "0.07",
            "--max-warning-count",
            "4",
            "--allow-no-passing-final-answer-candidate",
            "--max-cycle-warning-count",
            "5",
        ]
    )

    options = _options_from_args(args)

    assert options.cycle_id == "cycle-test"
    assert options.require_passing_final_answer_candidate is False
    assert options.max_cycle_warning_count == 5
    assert options.final_answer_gate_options.gate_id == "gate-test"
    assert options.final_answer_gate_options.top_candidate_limit == 3
    assert options.final_answer_gate_options.require_grid_non_regression_candidate is False
    assert options.final_answer_gate_options.backtest_options.pass_types == ("1x1", "2x1")
    assert options.final_answer_gate_options.backtest_options.modes == ("single",)
    assert options.final_answer_gate_options.backtest_options.strategy == "value_first"
    assert options.final_answer_gate_options.backtest_options.unit_stake == 5
    assert options.final_answer_gate_options.backtest_options.max_budget == 30
    assert options.final_answer_gate_options.backtest_options.min_probability == 0.22
    assert options.final_answer_gate_options.quality_gate_options.min_slice_count == 2
    assert options.final_answer_gate_options.quality_gate_options.max_warning_count == 4
