from __future__ import annotations

from nutmeg.accuracy.historical_prematch_feature_ablation_grid import (
    HistoricalPrematchFeatureAblationGridOptions,
    _options_from_args,
    _parse_args,
    build_historical_prematch_feature_ablation_grid_report,
)
from nutmeg.recommendations import build_enriched_historical_feature_sample


def test_prematch_feature_ablation_grid_ranks_shadow_candidates() -> None:
    historical_slice = build_enriched_historical_feature_sample().historical_slice

    report = build_historical_prematch_feature_ablation_grid_report(
        [historical_slice],
        options=HistoricalPrematchFeatureAblationGridOptions(
            min_feature_data_quality_score=80.0,
            max_probability_shifts=(0.0, 0.08),
            odds_movement_weights=(0.0, 0.35),
            tracked_fragility_weights=(0.0, 1.0),
            lineup_strength_weights=(0.0,),
            draw_signal_weights=(0.0, 0.35),
            prediction_sample_limit=0,
        ),
    )

    assert report.status == "generated"
    assert report.candidate_count == 16
    assert report.non_regression_candidate_count >= 1
    assert report.best_candidate.rank == 1
    assert report.best_candidate.validation_count == 6
    assert report.best_candidate.summary_json["passed_non_regression_gate"] is True
    assert report.best_brier_candidate.candidate.brier_score is not None


def test_prematch_feature_ablation_grid_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/enriched_features/nutmeg_enriched_prematch_feature_sample_v1.json",
            "--output-path",
            "tmp/prematch_feature_ablation_grid.json",
            "--grid-id",
            "grid-test",
            "--min-feature-data-quality-score",
            "82",
            "--max-probability-shifts",
            "0,0.04",
            "--odds-movement-weights",
            "0.2,0.4",
            "--tracked-fragility-weights",
            "0,0.8",
            "--lineup-strength-weights",
            "0,0.3",
            "--draw-signal-weights",
            "0,0.2",
            "--bucket-size",
            "0.05",
            "--min-bucket-sample-size",
            "3",
            "--prediction-sample-limit",
            "2",
            "--max-brier-score-regression",
            "0.01",
            "--max-log-loss-regression",
            "0.02",
            "--max-expected-calibration-error-regression",
            "0.03",
            "--min-hit-rate-delta",
            "-0.05",
            "--allow-feature-after-prediction",
            "--allow-feature-not-before-kickoff",
        ]
    )

    options = _options_from_args(args)

    assert options.grid_id == "grid-test"
    assert options.min_feature_data_quality_score == 82
    assert options.max_probability_shifts == (0.0, 0.04)
    assert options.odds_movement_weights == (0.2, 0.4)
    assert options.tracked_fragility_weights == (0.0, 0.8)
    assert options.lineup_strength_weights == (0.0, 0.3)
    assert options.draw_signal_weights == (0.0, 0.2)
    assert options.bucket_size == 0.05
    assert options.min_bucket_sample_size == 3
    assert options.prediction_sample_limit == 2
    assert options.max_brier_score_regression == 0.01
    assert options.max_log_loss_regression == 0.02
    assert options.max_expected_calibration_error_regression == 0.03
    assert options.min_hit_rate_delta == -0.05
    assert options.require_feature_not_after_prediction is False
    assert options.require_feature_before_kickoff is False
