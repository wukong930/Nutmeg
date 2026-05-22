from __future__ import annotations

from nutmeg.accuracy.historical_prematch_feature_ablation_grid import (
    HistoricalPrematchFeatureAblationGridOptions,
    build_historical_prematch_feature_ablation_grid_report,
)
from nutmeg.recommendations import build_enriched_historical_feature_sample
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestOptions,
)
from nutmeg.recommendations.historical_prematch_feature_final_answer_gate import (
    HistoricalPrematchFeatureFinalAnswerGateOptions,
    _options_from_args,
    _parse_args,
    build_historical_prematch_feature_final_answer_gate_report,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)


def test_prematch_feature_final_answer_gate_evaluates_grid_candidates() -> None:
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

    report = build_historical_prematch_feature_final_answer_gate_report(
        [historical_slice],
        grid_report=grid_report,
        options=HistoricalPrematchFeatureFinalAnswerGateOptions(
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
    )

    best = report.best_evaluation
    comparison = best.suite.comparisons[0]

    assert report.status == "generated"
    assert report.evaluated_candidate_count == 2
    assert report.passing_candidate_count >= 1
    assert best.adjusted_fixture_count == 6
    assert best.quality_gate.passed is True
    assert best.suite.summary_json["shadow_only"] is True
    assert best.suite.summary_json["feature_grid_candidate_id"].startswith(
        "prematch-feature-ablation-grid-shadow-v3.1"
    )
    assert comparison.baseline.slice_id == "nutmeg_enriched_prematch_feature_sample_v1"
    assert "__prematch_feature_shadow_" in comparison.candidate.slice_id
    assert comparison.candidate.final_answer is not None


def test_prematch_feature_final_answer_gate_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/enriched_features/nutmeg_enriched_prematch_feature_sample_v1.json",
            "--grid-report-path",
            "tmp/grid.json",
            "--output-path",
            "tmp/final_answer_gate.json",
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
        ]
    )

    options = _options_from_args(args)

    assert options.gate_id == "gate-test"
    assert options.top_candidate_limit == 3
    assert options.require_grid_non_regression_candidate is False
    assert options.backtest_options.pass_types == ("1x1", "2x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.strategy == "value_first"
    assert options.backtest_options.unit_stake == 5
    assert options.backtest_options.max_budget == 30
    assert options.backtest_options.min_probability == 0.22
    assert options.backtest_options.min_data_quality_score == 72
    assert options.backtest_options.candidate_fixture_limit == 8
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 1
    assert options.backtest_options.derive_market_context_signals is True
    assert options.backtest_options.optimizer_profile == "heuristic"
    assert options.quality_gate_options.min_slice_count == 2
    assert options.quality_gate_options.min_comparison_count == 2
    assert options.quality_gate_options.min_final_hit_sample_size == 2
    assert options.quality_gate_options.min_final_hit_rate_delta == -0.10
    assert options.quality_gate_options.max_brier_score_delta == 0.05
    assert options.quality_gate_options.max_log_loss_delta == 0.06
    assert options.quality_gate_options.max_mean_calibration_error_delta == 0.07
    assert options.quality_gate_options.max_warning_count == 4
