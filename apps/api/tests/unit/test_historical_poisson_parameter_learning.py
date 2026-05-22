from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nutmeg.accuracy import (
    HistoricalPoissonParameterLearningOptions,
    build_historical_poisson_parameter_learning_report,
)
from nutmeg.accuracy.historical_poisson_parameter_learning import (
    HistoricalPoissonParameterCandidate,
    _candidate_grid,
    _options_from_args,
    _parse_args,
    _selection_metric_value,
    _walk_forward_options,
)
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)


def test_historical_poisson_parameter_learning_selects_holdout_candidate() -> None:
    slices = [
        _season_slice("2021", 0),
        _season_slice("2022", 10),
        _season_slice("2023", 20),
    ]

    report = build_historical_poisson_parameter_learning_report(
        slices,
        options=HistoricalPoissonParameterLearningOptions(
            holdout_season_count=1,
            min_training_season_count=2,
            min_validation_sample_size=1,
            include_dixon_coles_candidates=False,
            candidate_draw_correction_weights=(0.0, 0.4),
            min_prior_matches=2,
            min_team_matches=1,
            max_training_results=20,
        ),
    )

    result = report.competitions[0]

    assert report.learned_competition_count == 1
    assert report.candidate_count == 2
    assert result.status == "learned"
    assert result.training_seasons == ["2021", "2022"]
    assert result.validation_seasons == ["2023"]
    assert result.selected_candidate is not None
    assert result.selected_validation is not None
    assert result.selected_validation.validation_count > 0
    assert report.overall_validation_candidate is not None
    assert report.overall_validation_baseline is not None


def test_historical_poisson_parameter_learning_includes_form_rest_weight_grid() -> None:
    slices = [
        _season_slice("2021", 0),
        _season_slice("2022", 10),
        _season_slice("2023", 20),
    ]

    report = build_historical_poisson_parameter_learning_report(
        slices,
        options=HistoricalPoissonParameterLearningOptions(
            lambda_method="form_rest_adjusted",
            holdout_season_count=1,
            min_training_season_count=2,
            min_validation_sample_size=1,
            include_dixon_coles_candidates=False,
            candidate_draw_correction_weights=(0.0,),
            candidate_form_adjustment_weights=(0.0, 0.2),
            candidate_rest_adjustment_weights=(0.0, 0.1),
            min_prior_matches=2,
            min_team_matches=1,
            max_training_results=20,
            form_window_matches=3,
            rest_reference_days=4.0,
            max_lambda_adjustment=0.25,
        ),
    )

    result = report.competitions[0]
    candidate_keys = {item.candidate.candidate_key for item in result.training_results}
    weight_pairs = {
        (item.candidate.form_adjustment_weight, item.candidate.rest_adjustment_weight)
        for item in result.training_results
    }

    assert report.candidate_count == 4
    assert candidate_keys == {
        "poisson_draw_0_0_form_0_0_rest_0_0",
        "poisson_draw_0_0_form_0_0_rest_0_1",
        "poisson_draw_0_0_form_0_2_rest_0_0",
        "poisson_draw_0_0_form_0_2_rest_0_1",
    }
    assert weight_pairs == {(0.0, 0.0), (0.0, 0.1), (0.2, 0.0), (0.2, 0.1)}
    assert all(
        item.candidate.lambda_method == "form_rest_adjusted"
        for item in result.training_results
    )
    assert result.selected_validation is not None


def test_historical_poisson_parameter_learning_includes_ema_form_grid() -> None:
    slices = [
        _season_slice("2021", 0),
        _season_slice("2022", 10),
        _season_slice("2023", 20),
    ]

    report = build_historical_poisson_parameter_learning_report(
        slices,
        options=HistoricalPoissonParameterLearningOptions(
            lambda_method="ema_form_adjusted",
            holdout_season_count=1,
            min_training_season_count=2,
            min_validation_sample_size=1,
            include_dixon_coles_candidates=False,
            candidate_draw_correction_weights=(0.4,),
            candidate_form_adjustment_weights=(0.0, 0.2),
            candidate_ema_form_half_life_matches=(1.5, 3.0),
            min_prior_matches=2,
            min_team_matches=1,
            max_training_results=20,
            form_window_matches=4,
        ),
    )

    result = report.competitions[0]
    candidate_keys = {item.candidate.candidate_key for item in result.training_results}
    parameter_pairs = {
        (
            item.candidate.ema_form_half_life_matches,
            item.candidate.form_adjustment_weight,
            item.candidate.rest_adjustment_weight,
        )
        for item in result.training_results
    }

    assert report.candidate_count == 4
    assert candidate_keys == {
        "poisson_draw_0_4_ema_1_5_form_0_0",
        "poisson_draw_0_4_ema_1_5_form_0_2",
        "poisson_draw_0_4_ema_3_0_form_0_0",
        "poisson_draw_0_4_ema_3_0_form_0_2",
    }
    assert parameter_pairs == {
        (1.5, 0.0, 0.0),
        (1.5, 0.2, 0.0),
        (3.0, 0.0, 0.0),
        (3.0, 0.2, 0.0),
    }
    assert result.selected_validation is not None
    assert report.summary_json["candidate_ema_form_half_life_matches"] == (1.5, 3.0)


def test_historical_poisson_parameter_learning_includes_recency_home_away_grid() -> None:
    slices = [
        _season_slice("2021", 0),
        _season_slice("2022", 10),
        _season_slice("2023", 20),
    ]

    report = build_historical_poisson_parameter_learning_report(
        slices,
        options=HistoricalPoissonParameterLearningOptions(
            lambda_method="enhanced_weighted_home_away",
            holdout_season_count=1,
            min_training_season_count=2,
            min_validation_sample_size=1,
            include_dixon_coles_candidates=False,
            candidate_draw_correction_weights=(0.0,),
            candidate_recency_half_life_days=(None, 45.0),
            candidate_home_away_split_weights=(0.0, 0.5),
            min_prior_matches=2,
            min_team_matches=1,
            max_training_results=20,
        ),
    )

    result = report.competitions[0]
    candidate_keys = {item.candidate.candidate_key for item in result.training_results}
    parameter_pairs = {
        (
            item.candidate.recency_half_life_days,
            item.candidate.home_away_split_weight,
        )
        for item in result.training_results
    }

    assert report.candidate_count == 4
    assert candidate_keys == {
        "poisson_draw_0_0",
        "poisson_draw_0_0_homeaway_0_5",
        "poisson_draw_0_0_recency_45_0",
        "poisson_draw_0_0_recency_45_0_homeaway_0_5",
    }
    assert parameter_pairs == {
        (None, 0.0),
        (None, 0.5),
        (45.0, 0.0),
        (45.0, 0.5),
    }
    assert result.selected_validation is not None
    assert report.summary_json["candidate_recency_half_life_days"] == (None, 45.0)
    assert report.summary_json["candidate_home_away_split_weights"] == (0.0, 0.5)


def test_historical_poisson_parameter_learning_includes_market_anchor_grid() -> None:
    slices = [
        _season_slice("2021", 0),
        _season_slice("2022", 10),
        _season_slice("2023", 20),
    ]

    report = build_historical_poisson_parameter_learning_report(
        slices,
        options=HistoricalPoissonParameterLearningOptions(
            holdout_season_count=1,
            min_training_season_count=2,
            min_validation_sample_size=1,
            include_dixon_coles_candidates=False,
            candidate_draw_correction_weights=(0.0,),
            candidate_market_anchor_weights=(0.0, 0.5),
            min_prior_matches=2,
            min_team_matches=1,
            max_training_results=20,
        ),
    )

    result = report.competitions[0]
    candidate_keys = {item.candidate.candidate_key for item in result.training_results}
    market_anchor_weights = {
        item.candidate.market_anchor_weight for item in result.training_results
    }
    walk_options = _walk_forward_options(
        result.training_results[-1].candidate,
        options=HistoricalPoissonParameterLearningOptions(),
        prediction_sample_limit=0,
    )

    assert report.candidate_count == 2
    assert candidate_keys == {
        "poisson_draw_0_0",
        "poisson_draw_0_0_marketanchor_0_5",
    }
    assert market_anchor_weights == {0.0, 0.5}
    assert walk_options.market_anchor_weight in {0.0, 0.5}
    assert report.summary_json["candidate_market_anchor_weights"] == (0.0, 0.5)
    assert result.selected_validation is not None


def test_historical_poisson_parameter_learning_no_harm_score_penalizes_regressions() -> None:
    options = HistoricalPoissonParameterLearningOptions(
        selection_metric="no_harm_score",
        selection_hit_rate_regression_penalty=20.0,
        selection_brier_regression_penalty=10.0,
        selection_log_loss_regression_penalty=5.0,
        selection_calibration_regression_penalty=5.0,
        selection_actual_probability_regression_penalty=10.0,
        selection_min_model_signal_weight=0.20,
        selection_low_model_signal_penalty=2.0,
    )
    regression_candidate = HistoricalPoissonParameterCandidate(
        candidate_key="poisson_draw_0_4_marketanchor_0_95",
        lambda_method="enhanced_weighted_home_away",
        score_grid_family="poisson",
        draw_correction_weight=0.4,
        market_anchor_weight=0.95,
    )
    no_harm_candidate = regression_candidate.model_copy(
        update={
            "candidate_key": "poisson_draw_0_4_marketanchor_0_8",
            "market_anchor_weight": 0.8,
        }
    )

    regression_score = _selection_metric_value(
        {
            "hit_rate_delta": -0.01,
            "brier_score_delta": -0.005,
            "log_loss_delta": 0.002,
            "expected_calibration_error_delta": -0.001,
            "average_actual_probability_delta": -0.003,
        },
        metric="no_harm_score",
        candidate=regression_candidate,
        options=options,
    )
    no_harm_score = _selection_metric_value(
        {
            "hit_rate_delta": 0.0,
            "brier_score_delta": -0.002,
            "log_loss_delta": -0.001,
            "expected_calibration_error_delta": 0.0,
            "average_actual_probability_delta": 0.0,
        },
        metric="no_harm_score",
        candidate=no_harm_candidate,
        options=options,
    )

    assert regression_score is not None
    assert no_harm_score is not None
    assert no_harm_score < regression_score


def test_historical_poisson_parameter_learning_includes_strength_shrinkage_grid() -> None:
    slices = [
        _season_slice("2021", 0),
        _season_slice("2022", 10),
        _season_slice("2023", 20),
    ]

    report = build_historical_poisson_parameter_learning_report(
        slices,
        options=HistoricalPoissonParameterLearningOptions(
            lambda_method="shrunken_weighted_home_away",
            holdout_season_count=1,
            min_training_season_count=2,
            min_validation_sample_size=1,
            include_dixon_coles_candidates=False,
            candidate_draw_correction_weights=(0.0,),
            candidate_recency_half_life_days=(None,),
            candidate_home_away_split_weights=(0.5,),
            candidate_strength_shrinkage_matches=(4.0, 12.0),
            min_prior_matches=2,
            min_team_matches=1,
            max_training_results=20,
        ),
    )

    result = report.competitions[0]
    candidate_keys = {item.candidate.candidate_key for item in result.training_results}
    shrinkage_values = {
        item.candidate.strength_shrinkage_matches for item in result.training_results
    }

    assert report.candidate_count == 2
    assert candidate_keys == {
        "poisson_draw_0_0_homeaway_0_5_shrink_4_0",
        "poisson_draw_0_0_homeaway_0_5_shrink_12_0",
    }
    assert shrinkage_values == {4.0, 12.0}
    assert result.selected_validation is not None
    assert report.summary_json["candidate_strength_shrinkage_matches"] == (4.0, 12.0)


def test_historical_poisson_parameter_learning_includes_hierarchical_shrinkage_grid() -> None:
    slices = [
        _season_slice("2021", 0),
        _season_slice("2022", 10),
        _season_slice("2023", 20),
    ]

    report = build_historical_poisson_parameter_learning_report(
        slices,
        options=HistoricalPoissonParameterLearningOptions(
            lambda_method="hierarchical_weighted_home_away",
            holdout_season_count=1,
            min_training_season_count=2,
            min_validation_sample_size=1,
            include_dixon_coles_candidates=False,
            candidate_draw_correction_weights=(0.4,),
            candidate_home_away_split_weights=(0.25,),
            candidate_strength_shrinkage_matches=(4.0, 12.0),
            min_prior_matches=2,
            min_team_matches=1,
            max_training_results=20,
        ),
    )

    result = report.competitions[0]
    candidate_keys = {item.candidate.candidate_key for item in result.training_results}
    shrinkage_values = {
        item.candidate.strength_shrinkage_matches for item in result.training_results
    }

    assert report.candidate_count == 2
    assert candidate_keys == {
        "poisson_draw_0_4_homeaway_0_25_shrink_4_0",
        "poisson_draw_0_4_homeaway_0_25_shrink_12_0",
    }
    assert shrinkage_values == {4.0, 12.0}
    assert result.selected_validation is not None
    assert report.summary_json["candidate_strength_shrinkage_matches"] == (4.0, 12.0)


def test_historical_poisson_parameter_learning_includes_reliability_weighted_grid() -> None:
    slices = [
        _season_slice("2021", 0),
        _season_slice("2022", 10),
        _season_slice("2023", 20),
    ]

    report = build_historical_poisson_parameter_learning_report(
        slices,
        options=HistoricalPoissonParameterLearningOptions(
            lambda_method="reliability_weighted_home_away",
            holdout_season_count=1,
            min_training_season_count=2,
            min_validation_sample_size=1,
            include_dixon_coles_candidates=False,
            candidate_draw_correction_weights=(0.4,),
            candidate_home_away_split_weights=(0.25,),
            candidate_strength_shrinkage_matches=(4.0, 12.0),
            min_prior_matches=2,
            min_team_matches=1,
            max_training_results=20,
        ),
    )

    result = report.competitions[0]
    candidate_keys = {item.candidate.candidate_key for item in result.training_results}
    shrinkage_values = {
        item.candidate.strength_shrinkage_matches for item in result.training_results
    }

    assert report.candidate_count == 2
    assert candidate_keys == {
        "poisson_draw_0_4_homeaway_0_25_shrink_4_0",
        "poisson_draw_0_4_homeaway_0_25_shrink_12_0",
    }
    assert shrinkage_values == {4.0, 12.0}
    assert all(
        item.candidate.lambda_method == "reliability_weighted_home_away"
        for item in result.training_results
    )
    assert result.selected_validation is not None
    assert report.summary_json["candidate_strength_shrinkage_matches"] == (4.0, 12.0)


def test_historical_poisson_parameter_learning_includes_prior_season_weight_grid() -> None:
    slices = [
        _season_slice("2021", 0),
        _season_slice("2022", 10),
        _season_slice("2023", 20),
    ]

    report = build_historical_poisson_parameter_learning_report(
        slices,
        options=HistoricalPoissonParameterLearningOptions(
            lambda_method="season_weighted_home_away",
            holdout_season_count=1,
            min_training_season_count=2,
            min_validation_sample_size=1,
            include_dixon_coles_candidates=False,
            candidate_draw_correction_weights=(0.4,),
            candidate_home_away_split_weights=(0.25,),
            candidate_prior_season_weights=(0.2, 0.5),
            min_prior_matches=2,
            min_team_matches=1,
            max_training_results=20,
        ),
    )

    result = report.competitions[0]
    candidate_keys = {item.candidate.candidate_key for item in result.training_results}
    prior_weights = {
        item.candidate.prior_season_weight for item in result.training_results
    }

    assert report.candidate_count == 2
    assert candidate_keys == {
        "poisson_draw_0_4_homeaway_0_25_priorseason_0_2",
        "poisson_draw_0_4_homeaway_0_25_priorseason_0_5",
    }
    assert prior_weights == {0.2, 0.5}
    assert result.selected_validation is not None
    assert report.summary_json["candidate_prior_season_weights"] == (0.2, 0.5)


def test_historical_poisson_parameter_learning_includes_prematch_feature_lambda_grid() -> None:
    options = HistoricalPoissonParameterLearningOptions(
        lambda_method="prematch_feature_adjusted",
        include_dixon_coles_candidates=False,
        candidate_draw_correction_weights=(0.4,),
        candidate_form_adjustment_weights=(0.0,),
        candidate_rest_adjustment_weights=(0.0,),
        candidate_prematch_feature_odds_movement_weights=(0.0, 0.25),
        candidate_prematch_feature_draw_risk_weights=(0.0, 0.02),
        candidate_max_prematch_feature_lambda_adjustments=(0.04, 0.08),
        min_prematch_feature_data_quality_score=70.0,
        prematch_feature_lineup_strength_weight=0.0,
        prematch_feature_availability_risk_weight=0.0,
        prematch_feature_semantic_risk_weight=0.0,
    )

    candidates = _candidate_grid(options)
    candidate_keys = {candidate.candidate_key for candidate in candidates}
    walk_options = _walk_forward_options(
        candidates[-1],
        options=options,
        prediction_sample_limit=3,
    )

    assert len(candidates) == 8
    assert (
        "poisson_draw_0_4_form_0_0_rest_0_0_"
        "prematch_odds_0_25_prematch_draw_0_02_prematch_max_0_08"
    ) in candidate_keys
    assert walk_options.lambda_method == "prematch_feature_adjusted"
    assert walk_options.min_prematch_feature_data_quality_score == 70.0
    assert walk_options.prematch_feature_odds_movement_weight in {0.0, 0.25}
    assert walk_options.prematch_feature_lineup_strength_weight == 0.0
    assert walk_options.prematch_feature_availability_risk_weight == 0.0
    assert walk_options.prematch_feature_semantic_risk_weight == 0.0
    assert walk_options.max_prematch_feature_lambda_adjustment in {0.04, 0.08}
    assert walk_options.prediction_sample_limit == 3


def test_historical_poisson_parameter_learning_preserves_zero_dixon_coles_rho() -> None:
    candidate = HistoricalPoissonParameterCandidate(
        candidate_key="dc_rho_0_0_draw_0_4",
        lambda_method="enhanced_weighted_home_away",
        score_grid_family="dixon_coles_low_score",
        dixon_coles_rho=0.0,
        draw_correction_weight=0.4,
    )

    options = _walk_forward_options(
        candidate,
        options=HistoricalPoissonParameterLearningOptions(),
        prediction_sample_limit=0,
    )

    assert options.dixon_coles_rho == 0.0


def test_historical_poisson_parameter_learning_skips_without_training_seasons() -> None:
    report = build_historical_poisson_parameter_learning_report(
        [_season_slice("2023", 0)],
        options=HistoricalPoissonParameterLearningOptions(
            min_training_season_count=2,
            min_validation_sample_size=1,
        ),
    )

    assert report.learned_competition_count == 0
    assert report.competitions[0].status == "skipped"
    assert "insufficient_training_seasons" in report.warnings[0]


def test_historical_poisson_parameter_learning_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--holdout-season-count",
            "2",
            "--min-training-season-count",
            "3",
            "--min-validation-sample-size",
            "50",
            "--selection-metric",
            "no_harm_score",
            "--selection-primary-metric-weight",
            "1.2",
            "--selection-hit-rate-regression-penalty",
            "20",
            "--selection-brier-regression-penalty",
            "8",
            "--selection-log-loss-regression-penalty",
            "4",
            "--selection-calibration-regression-penalty",
            "3",
            "--selection-actual-probability-regression-penalty",
            "6",
            "--selection-min-model-signal-weight",
            "0.2",
            "--selection-low-model-signal-penalty",
            "2",
            "--lambda-method",
            "prematch_feature_adjusted",
            "--disable-dixon-coles-candidates",
            "--candidate-draw-correction-weights",
            "0,0.2,0.4",
            "--candidate-market-anchor-weights",
            "0,0.5,0.9",
            "--candidate-dixon-coles-rhos=-0.1,-0.05",
            "--candidate-form-adjustment-weights",
            "0,0.03,0.05",
            "--candidate-ema-form-half-life-matches",
            "1.5,3,6",
            "--candidate-prior-season-weights",
            "0.2,0.5",
            "--candidate-rest-adjustment-weights",
            "0,0.02",
            "--candidate-prematch-feature-odds-movement-weights",
            "0,0.1,0.25",
            "--candidate-prematch-feature-draw-risk-weights",
            "0,0.02",
            "--candidate-max-prematch-feature-lambda-adjustments",
            "0.04,0.08",
            "--candidate-recency-half-life-days",
            "none,45,180",
            "--candidate-home-away-split-weights",
            "0,0.25,0.5",
            "--candidate-strength-shrinkage-matches",
            "4,8,16",
            "--min-prior-matches",
            "20",
            "--min-team-matches",
            "3",
            "--max-training-results",
            "100",
            "--max-goals",
            "7",
            "--bucket-size",
            "0.05",
            "--min-bucket-sample-size",
            "8",
            "--recency-half-life-days",
            "180",
            "--home-away-split-weight",
            "0.25",
            "--strength-shrinkage-matches",
            "12",
            "--prior-season-weight",
            "0.35",
            "--form-window-matches",
            "8",
            "--ema-form-half-life-matches",
            "2.5",
            "--rest-reference-days",
            "5.5",
            "--max-lambda-adjustment",
            "0.18",
            "--min-prematch-feature-data-quality-score",
            "70",
            "--prematch-feature-lineup-strength-weight",
            "0.01",
            "--prematch-feature-availability-risk-weight",
            "0.02",
            "--prematch-feature-semantic-risk-weight",
            "0.03",
            "--prediction-sample-limit",
            "4",
        ]
    )

    options = _options_from_args(args)

    assert options.holdout_season_count == 2
    assert options.min_training_season_count == 3
    assert options.min_validation_sample_size == 50
    assert options.selection_metric == "no_harm_score"
    assert options.selection_primary_metric_weight == 1.2
    assert options.selection_hit_rate_regression_penalty == 20
    assert options.selection_brier_regression_penalty == 8
    assert options.selection_log_loss_regression_penalty == 4
    assert options.selection_calibration_regression_penalty == 3
    assert options.selection_actual_probability_regression_penalty == 6
    assert options.selection_min_model_signal_weight == 0.2
    assert options.selection_low_model_signal_penalty == 2
    assert options.lambda_method == "prematch_feature_adjusted"
    assert options.include_dixon_coles_candidates is False
    assert options.candidate_draw_correction_weights == (0.0, 0.2, 0.4)
    assert options.candidate_market_anchor_weights == (0.0, 0.5, 0.9)
    assert options.candidate_dixon_coles_rhos == (-0.1, -0.05)
    assert options.candidate_form_adjustment_weights == (0.0, 0.03, 0.05)
    assert options.candidate_ema_form_half_life_matches == (1.5, 3.0, 6.0)
    assert options.candidate_prior_season_weights == (0.2, 0.5)
    assert options.candidate_rest_adjustment_weights == (0.0, 0.02)
    assert options.candidate_prematch_feature_odds_movement_weights == (
        0.0,
        0.1,
        0.25,
    )
    assert options.candidate_prematch_feature_draw_risk_weights == (0.0, 0.02)
    assert options.candidate_max_prematch_feature_lambda_adjustments == (0.04, 0.08)
    assert options.candidate_recency_half_life_days == (None, 45.0, 180.0)
    assert options.candidate_home_away_split_weights == (0.0, 0.25, 0.5)
    assert options.candidate_strength_shrinkage_matches == (4.0, 8.0, 16.0)
    assert options.min_prior_matches == 20
    assert options.min_team_matches == 3
    assert options.max_training_results == 100
    assert options.max_goals == 7
    assert options.bucket_size == 0.05
    assert options.min_bucket_sample_size == 8
    assert options.recency_half_life_days == 180
    assert options.home_away_split_weight == 0.25
    assert options.strength_shrinkage_matches == 12
    assert options.prior_season_weight == 0.35
    assert options.form_window_matches == 8
    assert options.ema_form_half_life_matches == 2.5
    assert options.rest_reference_days == 5.5
    assert options.max_lambda_adjustment == 0.18
    assert options.min_prematch_feature_data_quality_score == 70
    assert options.prematch_feature_lineup_strength_weight == 0.01
    assert options.prematch_feature_availability_risk_weight == 0.02
    assert options.prematch_feature_semantic_risk_weight == 0.03
    assert options.prediction_sample_limit == 4


def _season_slice(season: str, day_offset: int) -> HistoricalRecommendationSlice:
    base_time = datetime(2024, 8, 1, 12, tzinfo=UTC) + timedelta(days=day_offset)
    fixtures = [
        _fixture("alpha_bravo", base_time, "Alpha", "Bravo", 2, 0),
        _fixture("charlie_delta", base_time + timedelta(days=1), "Charlie", "Delta", 1, 1),
        _fixture("alpha_charlie", base_time + timedelta(days=2), "Alpha", "Charlie", 1, 0),
        _fixture("bravo_delta", base_time + timedelta(days=3), "Bravo", "Delta", 0, 1),
        _fixture("delta_alpha", base_time + timedelta(days=4), "Delta", "Alpha", 0, 2),
        _fixture("bravo_charlie", base_time + timedelta(days=5), "Bravo", "Charlie", 1, 0),
    ]
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=f"learning_{season}",
            name=f"Learning {season}",
            competition_id="TEST",
            season=season,
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=base_time,
        fixtures=[
            fixture.model_copy(update={"fixture_id": f"{season}_{fixture.fixture_id}"})
            for fixture in fixtures
        ],
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
                probability=0.45,
                decimal_odds=2.20,
                market_probability=0.45,
            ),
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="draw",
                probability=0.25,
                decimal_odds=4.00,
                market_probability=0.25,
            ),
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="away_win",
                probability=0.30,
                decimal_odds=3.30,
                market_probability=0.30,
            ),
        ],
    )
