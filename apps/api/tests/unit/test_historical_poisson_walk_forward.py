from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nutmeg.accuracy import (
    HistoricalPoissonWalkForwardOptions,
    build_historical_poisson_walk_forward_report,
)
from nutmeg.accuracy.historical_poisson_walk_forward import (
    _options_from_args,
    _parse_args,
    _prematch_odds_home_advantage_signal,
)
from nutmeg.domain.features import (
    PrematchAvailabilityFeature,
    PrematchLineupFeature,
    PrematchOddsMovementFeature,
    PrematchOddsMovementPoint,
    PrematchSemanticSignal,
    StructuredPrematchFeatureSet,
)
from nutmeg.features import build_structured_prematch_feature_snapshot
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)


def test_historical_poisson_walk_forward_compares_against_market_baseline() -> None:
    historical_slice = _walk_forward_slice()

    report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )

    assert report.validation_count == 2
    assert report.skipped_reason_counts == {"insufficient_prior_matches": 6}
    assert report.overall.candidate.sample_size == 2
    assert report.overall.baseline.sample_size == 2
    assert report.overall.candidate.brier_score is not None
    assert report.overall.baseline.brier_score is not None
    assert (
        report.overall.candidate.brier_score
        < report.overall.baseline.brier_score
    )
    assert report.overall.deltas_json["brier_score_delta"] is not None
    assert report.sampled_predictions[0].lambda_home > 0
    assert report.summary_json["dixon_coles_v15_compatible"] is True


def test_historical_poisson_walk_forward_skips_cold_start_samples() -> None:
    historical_slice = _walk_forward_slice()

    report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            min_prior_matches=100,
            min_team_matches=2,
        ),
    )

    assert report.validation_count == 0
    assert report.skipped_count == 8
    assert report.overall.candidate.brier_score is None
    assert report.warnings == [
        "historical_poisson_walk_forward:no_validation_fixtures",
        "historical_poisson_walk_forward:skipped_fixtures",
    ]


def test_historical_poisson_walk_forward_enhanced_variant_tracks_draw_correction() -> None:
    historical_slice = _walk_forward_slice()

    report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            lambda_method="enhanced_weighted_home_away",
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            recency_half_life_days=30,
            home_away_split_weight=0.60,
            draw_correction_weight=0.50,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )

    first_sample = report.sampled_predictions[0]

    assert report.validation_count == 2
    assert first_sample.lambda_method == "enhanced_weighted_home_away"
    assert first_sample.draw_rate_reference is not None
    assert first_sample.candidate_probabilities_before_draw_correction["draw"] != (
        first_sample.candidate_probabilities["draw"]
    )
    assert sum(first_sample.candidate_probabilities.values()) == pytest.approx(1)


def test_historical_poisson_walk_forward_market_anchor_blends_to_baseline() -> None:
    historical_slice = _walk_forward_slice()

    report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            market_anchor_weight=0.75,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )

    first_sample = report.sampled_predictions[0]

    assert report.validation_count == 2
    assert first_sample.market_anchor_weight == 0.75
    assert first_sample.model_signal_weight == pytest.approx(0.25)
    assert first_sample.candidate_probabilities != (
        first_sample.candidate_probabilities_before_market_anchor
    )
    assert first_sample.candidate_probabilities["home_win"] == pytest.approx(
        0.25
        * first_sample.candidate_probabilities_before_market_anchor["home_win"]
        + 0.75 * first_sample.baseline_probabilities["home_win"]
    )
    assert sum(first_sample.candidate_probabilities.values()) == pytest.approx(1)
    assert report.summary_json["market_anchor_weight"] == 0.75
    assert report.summary_json["market_anchor_calibration_shadow_only"] is True


def test_historical_poisson_walk_forward_shrunken_variant_tracks_sample_reliability() -> None:
    historical_slice = _walk_forward_slice()

    enhanced_report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            lambda_method="enhanced_weighted_home_away",
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            home_away_split_weight=0.60,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )
    shrunken_report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            lambda_method="shrunken_weighted_home_away",
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            home_away_split_weight=0.60,
            strength_shrinkage_matches=20.0,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )

    enhanced_sample = enhanced_report.sampled_predictions[0]
    shrunken_sample = shrunken_report.sampled_predictions[0]

    assert shrunken_report.validation_count == 2
    assert shrunken_sample.lambda_method == "shrunken_weighted_home_away"
    assert shrunken_sample.strength_shrinkage_matches == 20.0
    assert shrunken_sample.home_strength_reliability == pytest.approx(
        shrunken_sample.home_sample_matches
        / (shrunken_sample.home_sample_matches + 20.0)
    )
    assert shrunken_sample.away_strength_reliability == pytest.approx(
        shrunken_sample.away_sample_matches
        / (shrunken_sample.away_sample_matches + 20.0)
    )
    assert shrunken_sample.home_strength_reliability < 1.0
    assert shrunken_sample.lambda_home < enhanced_sample.lambda_home
    assert shrunken_sample.lambda_away > enhanced_sample.lambda_away
    assert shrunken_report.summary_json["sample_shrinkage_shadow_only"] is True
    assert shrunken_report.summary_json["strength_shrinkage_matches"] == 20.0
    assert sum(shrunken_sample.candidate_probabilities.values()) == pytest.approx(1)


def test_historical_poisson_walk_forward_hierarchical_variant_shrinks_strengths() -> None:
    historical_slice = _walk_forward_slice()

    enhanced_report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            lambda_method="enhanced_weighted_home_away",
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            home_away_split_weight=0.60,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )
    hierarchical_report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            lambda_method="hierarchical_weighted_home_away",
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            home_away_split_weight=0.60,
            strength_shrinkage_matches=20.0,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )

    enhanced_sample = enhanced_report.sampled_predictions[0]
    hierarchical_sample = hierarchical_report.sampled_predictions[0]

    assert hierarchical_report.validation_count == 2
    assert hierarchical_sample.lambda_method == "hierarchical_weighted_home_away"
    assert hierarchical_sample.strength_shrinkage_matches == 20.0
    assert hierarchical_sample.home_strength_reliability == pytest.approx(
        hierarchical_sample.home_sample_matches
        / (hierarchical_sample.home_sample_matches + 20.0)
    )
    assert hierarchical_sample.away_strength_reliability == pytest.approx(
        hierarchical_sample.away_sample_matches
        / (hierarchical_sample.away_sample_matches + 20.0)
    )
    assert hierarchical_sample.home_strength_reliability < 1.0
    assert hierarchical_sample.lambda_home != enhanced_sample.lambda_home
    assert hierarchical_sample.lambda_away != enhanced_sample.lambda_away
    assert hierarchical_report.summary_json["hierarchical_strength_shadow_only"] is True
    assert hierarchical_report.summary_json["strength_shrinkage_matches"] == 20.0
    assert sum(hierarchical_sample.candidate_probabilities.values()) == pytest.approx(1)


def test_historical_poisson_walk_forward_reliability_variant_downweights_split() -> None:
    historical_slice = _walk_forward_slice()

    enhanced_report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            lambda_method="enhanced_weighted_home_away",
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            home_away_split_weight=0.60,
            strength_shrinkage_matches=20.0,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )
    reliability_report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            lambda_method="reliability_weighted_home_away",
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            home_away_split_weight=0.60,
            strength_shrinkage_matches=20.0,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )

    enhanced_sample = enhanced_report.sampled_predictions[0]
    reliability_sample = reliability_report.sampled_predictions[0]

    assert reliability_report.validation_count == 2
    assert reliability_sample.lambda_method == "reliability_weighted_home_away"
    assert reliability_sample.strength_shrinkage_matches == 20.0
    assert reliability_sample.home_strength_reliability is not None
    assert reliability_sample.away_strength_reliability is not None
    assert reliability_sample.effective_home_away_split_weight is not None
    assert reliability_sample.effective_home_away_split_weight < 0.60
    assert reliability_sample.lambda_home != enhanced_sample.lambda_home
    assert reliability_sample.lambda_away != enhanced_sample.lambda_away
    assert (
        reliability_report.summary_json["reliability_weighted_home_away_shadow_only"]
        is True
    )
    assert sum(reliability_sample.candidate_probabilities.values()) == pytest.approx(1)


def test_historical_poisson_walk_forward_season_weighted_variant_tracks_counts() -> None:
    historical_slices = [
        _walk_forward_slice_for_season("2023", day_offset=0),
        _walk_forward_slice_for_season("2024", day_offset=365),
    ]

    report = build_historical_poisson_walk_forward_report(
        historical_slices,
        options=HistoricalPoissonWalkForwardOptions(
            lambda_method="season_weighted_home_away",
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            prior_season_weight=0.25,
            min_bucket_sample_size=2,
            prediction_sample_limit=20,
        ),
    )

    current_sample = next(
        sample
        for sample in report.sampled_predictions
        if sample.fixture_id == "2024_m7"
    )

    assert report.validation_count == 10
    assert current_sample.lambda_method == "season_weighted_home_away"
    assert current_sample.current_season_match_count == 6
    assert current_sample.prior_season_match_count == 8
    assert current_sample.prior_season_weight == 0.25
    assert report.summary_json["season_weighted_shadow_only"] is True
    assert report.summary_json["prior_season_weight"] == 0.25
    assert sum(current_sample.candidate_probabilities.values()) == pytest.approx(1)


def test_historical_poisson_walk_forward_dixon_coles_grid_records_rho() -> None:
    historical_slice = _walk_forward_slice()

    report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            score_grid_family="dixon_coles_low_score",
            dixon_coles_rho=-0.10,
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )

    first_sample = report.sampled_predictions[0]

    assert report.validation_count == 2
    assert first_sample.score_grid_family == "dixon_coles_low_score"
    assert first_sample.dixon_coles_rho == -0.10
    assert first_sample.lambda_home > 0
    assert first_sample.lambda_away > 0
    assert sum(first_sample.candidate_probabilities.values()) == pytest.approx(1)


def test_historical_poisson_walk_forward_form_rest_variant_tracks_features() -> None:
    historical_slice = _walk_forward_slice()

    report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            lambda_method="form_rest_adjusted",
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            form_window_matches=3,
            form_adjustment_weight=0.20,
            rest_adjustment_weight=0.10,
            rest_reference_days=3.0,
            max_lambda_adjustment=0.30,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )

    first_sample = report.sampled_predictions[0]

    assert report.validation_count == 2
    assert first_sample.lambda_method == "form_rest_adjusted"
    assert first_sample.home_form_sample_matches == 3
    assert first_sample.away_form_sample_matches == 3
    assert first_sample.home_form_points_per_match == pytest.approx(3.0)
    assert first_sample.away_form_points_per_match == pytest.approx(0.0)
    assert first_sample.home_rest_days == pytest.approx(4.0)
    assert first_sample.away_rest_days == pytest.approx(1.0)
    assert first_sample.form_adjustment_factor > 0
    assert first_sample.rest_adjustment_factor > 0
    assert first_sample.total_lambda_adjustment_factor > 0
    assert report.summary_json["form_window_matches"] == 3
    assert report.summary_json["rest_reference_days"] == 3.0
    assert sum(first_sample.candidate_probabilities.values()) == pytest.approx(1)


def test_historical_poisson_walk_forward_ema_form_variant_tracks_weighted_form() -> None:
    historical_slice = _walk_forward_slice()

    report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            lambda_method="ema_form_adjusted",
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            form_window_matches=4,
            ema_form_half_life_matches=1.5,
            form_adjustment_weight=0.20,
            max_lambda_adjustment=0.30,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )

    first_sample = report.sampled_predictions[0]

    assert report.validation_count == 2
    assert first_sample.lambda_method == "ema_form_adjusted"
    assert first_sample.ema_form_half_life_matches == 1.5
    assert first_sample.home_form_sample_matches is not None
    assert first_sample.home_form_sample_matches >= 3
    assert first_sample.away_form_sample_matches is not None
    assert first_sample.away_form_sample_matches >= 3
    assert first_sample.home_form_points_per_match is not None
    assert first_sample.away_form_points_per_match is not None
    assert first_sample.form_adjustment_factor > 0
    assert first_sample.rest_adjustment_factor == 0
    assert first_sample.total_lambda_adjustment_factor == (
        first_sample.form_adjustment_factor
    )
    assert report.summary_json["ema_form_adjustment_shadow_only"] is True
    assert report.summary_json["ema_form_half_life_matches"] == 1.5
    assert sum(first_sample.candidate_probabilities.values()) == pytest.approx(1)


def test_historical_poisson_walk_forward_prematch_feature_variant_adjusts_lambdas() -> None:
    historical_slice = _walk_forward_slice_with_prematch_features()

    report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            lambda_method="prematch_feature_adjusted",
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
            prematch_feature_odds_movement_weight=0.60,
            prematch_feature_lineup_strength_weight=0.08,
            prematch_feature_availability_risk_weight=0.03,
            prematch_feature_draw_risk_weight=0.04,
            prematch_feature_semantic_risk_weight=0.02,
            max_prematch_feature_lambda_adjustment=0.12,
            min_bucket_sample_size=2,
            prediction_sample_limit=10,
        ),
    )

    first_sample = report.sampled_predictions[0]

    assert report.validation_count == 2
    assert first_sample.lambda_method == "prematch_feature_adjusted"
    assert first_sample.lambda_home_before_prematch_feature_adjustment is not None
    assert first_sample.lambda_away_before_prematch_feature_adjustment is not None
    assert first_sample.lambda_home > (
        first_sample.lambda_home_before_prematch_feature_adjustment
    )
    assert first_sample.lambda_away <= (
        first_sample.lambda_away_before_prematch_feature_adjustment
    )
    assert first_sample.prematch_feature_data_quality_score is not None
    assert first_sample.prematch_feature_adjustment_factor > 0
    assert first_sample.prematch_feature_total_goals_adjustment_factor <= 0
    assert "prematch_feature_lambda_adjustment" in (
        first_sample.prematch_feature_reason_codes
    )
    assert first_sample.prematch_feature_readout_json["shadow_only"] is True
    assert report.summary_json["prematch_feature_lambda_adjustment_shadow_only"] is True
    assert sum(first_sample.candidate_probabilities.values()) == pytest.approx(1)


def test_historical_poisson_walk_forward_reads_asian_handicap_cover_movement() -> None:
    movements = [
        {
            "market_type": "asian_handicap",
            "outcome": "home_cover",
            "probability_delta": 0.08,
        },
        {
            "market_type": "asian_handicap",
            "outcome": "away_cover",
            "probability_delta": -0.04,
        },
    ]
    signal = _prematch_odds_home_advantage_signal(movements)

    assert signal == pytest.approx(0.06)
    assert _prematch_odds_home_advantage_signal(
        movements,
        asian_handicap_movement_weight=0.25,
    ) == pytest.approx(0.03)
    assert _prematch_odds_home_advantage_signal(
        movements,
        min_asian_handicap_probability_delta=0.05,
    ) == pytest.approx(0.04)


def test_historical_poisson_walk_forward_reads_asian_handicap_line_movement() -> None:
    movements = [
        {
            "market_type": "asian_handicap",
            "outcome": "home_cover",
            "probability_delta": 0.0,
            "metadata_json": {
                "opening_line": -0.5,
                "closing_line": -0.75,
                "line_delta": -0.25,
            },
        },
        {
            "market_type": "asian_handicap",
            "outcome": "away_cover",
            "probability_delta": 0.0,
            "metadata_json": {
                "opening_line": -0.5,
                "closing_line": -0.75,
                "line_delta": -0.25,
            },
        },
    ]

    signal = _prematch_odds_home_advantage_signal(
        movements,
        asian_handicap_movement_weight=0.0,
        asian_handicap_line_movement_weight=0.5,
        asian_handicap_line_movement_scale=1.0,
    )

    assert signal == pytest.approx(0.125)
    assert _prematch_odds_home_advantage_signal(
        movements,
        asian_handicap_movement_weight=0.0,
        asian_handicap_line_movement_weight=0.5,
        min_asian_handicap_line_delta=0.5,
        asian_handicap_line_movement_scale=1.0,
    ) == pytest.approx(0.0)
    assert _prematch_odds_home_advantage_signal(
        movements,
        asian_handicap_movement_weight=0.0,
        asian_handicap_line_movement_weight=0.5,
        asian_handicap_line_movement_scale=1.0,
        asian_handicap_line_movement_transform="signed_sqrt",
    ) == pytest.approx(0.25)
    assert _prematch_odds_home_advantage_signal(
        movements,
        asian_handicap_movement_weight=0.0,
        asian_handicap_line_movement_weight=0.5,
        asian_handicap_line_movement_scale=2.0,
        asian_handicap_line_movement_transform="quarter_step",
    ) == pytest.approx(0.25)


def test_historical_poisson_walk_forward_prematch_feature_variant_requires_snapshot() -> None:
    historical_slice = _walk_forward_slice()

    report = build_historical_poisson_walk_forward_report(
        [historical_slice],
        options=HistoricalPoissonWalkForwardOptions(
            lambda_method="prematch_feature_adjusted",
            min_prior_matches=6,
            min_team_matches=2,
            max_training_results=20,
        ),
    )

    assert report.validation_count == 0
    assert report.skipped_reason_counts == {
        "insufficient_prior_matches": 6,
        "missing_prematch_feature_snapshot": 2,
    }


def test_historical_poisson_walk_forward_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--lambda-method",
            "prematch_feature_adjusted",
            "--score-grid-family",
            "dixon_coles_low_score",
            "--dixon-coles-rho",
            "-0.08",
            "--min-prior-matches",
            "20",
            "--min-team-matches",
            "4",
            "--max-training-results",
            "180",
            "--max-goals",
            "7",
            "--bucket-size",
            "0.05",
            "--min-bucket-sample-size",
            "12",
            "--recency-half-life-days",
            "45",
            "--home-away-split-weight",
            "0.65",
            "--strength-shrinkage-matches",
            "12",
            "--prior-season-weight",
            "0.25",
            "--draw-correction-weight",
            "0.25",
            "--market-anchor-weight",
            "0.35",
            "--form-window-matches",
            "8",
            "--ema-form-half-life-matches",
            "2.5",
            "--form-adjustment-weight",
            "0.12",
            "--rest-adjustment-weight",
            "0.07",
            "--rest-reference-days",
            "5.5",
            "--max-lambda-adjustment",
            "0.18",
            "--min-prematch-feature-data-quality-score",
            "86",
            "--prematch-feature-odds-movement-weight",
            "0.7",
            "--prematch-feature-asian-handicap-movement-weight",
            "0.25",
            "--prematch-feature-min-asian-handicap-probability-delta",
            "0.04",
            "--prematch-feature-asian-handicap-line-movement-weight",
            "0.08",
            "--prematch-feature-min-asian-handicap-line-delta",
            "0.25",
            "--prematch-feature-asian-handicap-line-movement-scale",
            "1.5",
            "--prematch-feature-asian-handicap-line-movement-transform",
            "signed_sqrt",
            "--prematch-feature-lineup-strength-weight",
            "0.11",
            "--prematch-feature-availability-risk-weight",
            "0.09",
            "--prematch-feature-draw-risk-weight",
            "0.08",
            "--prematch-feature-semantic-risk-weight",
            "0.06",
            "--max-prematch-feature-lambda-adjustment",
            "0.14",
            "--allow-missing-prematch-feature-fallback",
            "--allow-feature-after-prediction",
            "--allow-feature-not-before-kickoff",
            "--model-version",
            "poisson-test",
            "--feature-version",
            "features-test",
            "--calibration-version",
            "calibration-test",
            "--prediction-sample-limit",
            "3",
        ]
    )

    options = _options_from_args(args)

    assert options.lambda_method == "prematch_feature_adjusted"
    assert options.score_grid_family == "dixon_coles_low_score"
    assert options.dixon_coles_rho == -0.08
    assert options.min_prior_matches == 20
    assert options.min_team_matches == 4
    assert options.max_training_results == 180
    assert options.max_goals == 7
    assert options.bucket_size == 0.05
    assert options.min_bucket_sample_size == 12
    assert options.recency_half_life_days == 45
    assert options.home_away_split_weight == 0.65
    assert options.strength_shrinkage_matches == 12
    assert options.prior_season_weight == 0.25
    assert options.draw_correction_weight == 0.25
    assert options.market_anchor_weight == 0.35
    assert options.form_window_matches == 8
    assert options.ema_form_half_life_matches == 2.5
    assert options.form_adjustment_weight == 0.12
    assert options.rest_adjustment_weight == 0.07
    assert options.rest_reference_days == 5.5
    assert options.max_lambda_adjustment == 0.18
    assert options.min_prematch_feature_data_quality_score == 86
    assert options.prematch_feature_odds_movement_weight == 0.7
    assert options.prematch_feature_asian_handicap_movement_weight == 0.25
    assert options.prematch_feature_min_asian_handicap_probability_delta == 0.04
    assert options.prematch_feature_asian_handicap_line_movement_weight == 0.08
    assert options.prematch_feature_min_asian_handicap_line_delta == 0.25
    assert options.prematch_feature_asian_handicap_line_movement_scale == 1.5
    assert options.prematch_feature_asian_handicap_line_movement_transform == "signed_sqrt"
    assert options.prematch_feature_lineup_strength_weight == 0.11
    assert options.prematch_feature_availability_risk_weight == 0.09
    assert options.prematch_feature_draw_risk_weight == 0.08
    assert options.prematch_feature_semantic_risk_weight == 0.06
    assert options.max_prematch_feature_lambda_adjustment == 0.14
    assert options.allow_missing_prematch_feature_fallback is True
    assert options.require_feature_not_after_prediction is False
    assert options.require_feature_before_kickoff is False
    assert options.model_version == "poisson-test"
    assert options.feature_version == "features-test"
    assert options.calibration_version == "calibration-test"
    assert options.prediction_sample_limit == 3


def _walk_forward_slice() -> HistoricalRecommendationSlice:
    base_time = datetime(2024, 8, 1, 12, tzinfo=UTC)
    fixtures = [
        _fixture("m1", base_time, "Alpha", "Bravo", 3, 0),
        _fixture("m2", base_time + timedelta(days=1), "Alpha", "Charlie", 2, 0),
        _fixture("m3", base_time + timedelta(days=2), "Delta", "Alpha", 0, 2),
        _fixture("m4", base_time + timedelta(days=3), "Bravo", "Charlie", 1, 1),
        _fixture("m5", base_time + timedelta(days=4), "Delta", "Bravo", 0, 1),
        _fixture("m6", base_time + timedelta(days=5), "Charlie", "Delta", 1, 0),
        _fixture("m7", base_time + timedelta(days=6), "Alpha", "Delta", 2, 0),
        _fixture("m8", base_time + timedelta(days=7), "Bravo", "Charlie", 1, 0),
    ]
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="poisson_walk_forward_test",
            name="Poisson walk-forward test",
            competition_id="TEST",
            season="2024",
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test market baseline",
        ),
        as_of_time_utc=base_time,
        fixtures=fixtures,
    )


def _walk_forward_slice_with_prematch_features() -> HistoricalRecommendationSlice:
    historical_slice = _walk_forward_slice()
    feature_fixture_ids = {"m7", "m8"}
    return historical_slice.model_copy(
        update={
            "fixtures": [
                fixture.model_copy(
                    update={"feature_snapshot": _prematch_feature_snapshot(fixture)}
                )
                if fixture.fixture_id in feature_fixture_ids
                else fixture
                for fixture in historical_slice.fixtures
            ]
        }
    )


def _walk_forward_slice_for_season(
    season: str,
    *,
    day_offset: int,
) -> HistoricalRecommendationSlice:
    historical_slice = _walk_forward_slice()
    offset = timedelta(days=day_offset)
    return historical_slice.model_copy(
        update={
            "metadata": historical_slice.metadata.model_copy(
                update={
                    "slice_id": f"poisson_walk_forward_test_{season}",
                    "season": season,
                }
            ),
            "as_of_time_utc": historical_slice.as_of_time_utc + offset,
            "fixtures": [
                fixture.model_copy(
                    update={
                        "fixture_id": f"{season}_{fixture.fixture_id}",
                        "kickoff_time_utc": fixture.kickoff_time_utc + offset,
                        "prediction_time_utc": fixture.prediction_time_utc + offset,
                    }
                )
                for fixture in historical_slice.fixtures
            ],
        }
    )


def _prematch_feature_snapshot(fixture: HistoricalFixture):
    feature_time = fixture.prediction_time_utc - timedelta(minutes=15)
    return build_structured_prematch_feature_snapshot(
        fixture_id=fixture.fixture_id,
        competition_id=fixture.competition_id,
        kickoff_time_utc=fixture.kickoff_time_utc,
        feature_time_utc=feature_time,
        historical_stats_completeness=0.84,
        provider_consistency=0.94,
        prematch_features=StructuredPrematchFeatureSet(
            lineup=PrematchLineupFeature(
                lineup_type="confirmed",
                snapshot_time_utc=feature_time - timedelta(minutes=45),
                expected_lineup_confidence=0.92,
                starting_xi_strength=0.91,
                bench_dropoff_score=0.04,
                source="unit-test",
                source_snapshot_ref=f"lineup:{fixture.fixture_id}",
            ),
            availability=PrematchAvailabilityFeature(
                snapshot_time_utc=feature_time - timedelta(hours=2),
                key_player_absence_score=0.02,
                defender_absence_score=0.01,
                goalkeeper_absence_score=0.0,
                striker_absence_score=0.03,
                source="unit-test",
                source_snapshot_ref=f"availability:{fixture.fixture_id}",
            ),
            odds_movements=[
                PrematchOddsMovementFeature(
                    market_type="1x2",
                    outcome="home_win",
                    bookmaker_disagreement=0.05,
                    market_delay_signal=0.02,
                    points=[
                        PrematchOddsMovementPoint(
                            snapshot_time_utc=feature_time - timedelta(hours=8),
                            market_type="1x2",
                            outcome="home_win",
                            decimal_odds=2.20,
                            fair_probability=0.44,
                            bookmaker_count=6,
                        ),
                        PrematchOddsMovementPoint(
                            snapshot_time_utc=feature_time - timedelta(minutes=5),
                            market_type="1x2",
                            outcome="home_win",
                            decimal_odds=1.85,
                            fair_probability=0.56,
                            bookmaker_count=7,
                        ),
                    ],
                )
            ],
            semantic_signals=[
                PrematchSemanticSignal(
                    signal_name="title_race_pressure",
                    source="unit-test",
                    confidence=0.32,
                    evidence_text_short="Home side still has a strong incentive.",
                    extracted_at_utc=feature_time - timedelta(minutes=20),
                )
            ],
        ),
    )


def _fixture(
    fixture_id: str,
    kickoff_time_utc: datetime,
    home_team_name: str,
    away_team_name: str,
    home_goals: int,
    away_goals: int,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=kickoff_time_utc,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        actual_home_goals=home_goals,
        actual_away_goals=away_goals,
        prediction_time_utc=kickoff_time_utc - timedelta(days=1),
        model_version="market-baseline-test",
        feature_version="unit-test",
        calibration_version="unit-test",
        predictions=[
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="home_win",
                probability=0.20,
                decimal_odds=5.00,
                market_probability=0.20,
            ),
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="draw",
                probability=0.30,
                decimal_odds=3.33,
                market_probability=0.30,
            ),
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="away_win",
                probability=0.50,
                decimal_odds=2.00,
                market_probability=0.50,
            ),
        ],
    )
