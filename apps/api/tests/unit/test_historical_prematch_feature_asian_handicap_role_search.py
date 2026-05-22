from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nutmeg.accuracy import (
    HistoricalPoissonWalkForwardOptions,
    HistoricalPrematchFeatureAsianHandicapRoleSearchOptions,
    build_historical_prematch_feature_asian_handicap_role_search_report,
)
from nutmeg.accuracy.historical_prematch_feature_asian_handicap_role_search import (
    _options_from_args,
    _parse_args,
)
from nutmeg.domain.features import (
    PrematchOddsMovementFeature,
    PrematchOddsMovementPoint,
    StructuredPrematchFeatureSet,
)
from nutmeg.features import build_structured_prematch_feature_snapshot
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)


def test_asian_handicap_role_search_marks_zero_weight_as_control() -> None:
    baseline_slice = _walk_forward_slice(include_asian_handicap=False)
    candidate_slice = _walk_forward_slice(include_asian_handicap=True)

    report = build_historical_prematch_feature_asian_handicap_role_search_report(
        [baseline_slice],
        [candidate_slice],
        options=HistoricalPrematchFeatureAsianHandicapRoleSearchOptions(
            role_search_id="ah-role-search-test",
            poisson_options=_poisson_options(),
            asian_handicap_movement_weights=(0.0, 0.20),
            min_asian_handicap_probability_deltas=(0.0,),
            asian_handicap_line_movement_weights=(0.0,),
            min_asian_handicap_line_deltas=(0.0,),
            min_validation_count=2,
        ),
    )

    assert report.candidate_count == 2
    assert report.best_control_candidate is not None
    assert report.best_control_candidate.status == "control_passed"
    assert report.best_control_candidate.effective_asian_handicap_role is False
    assert report.best_control_candidate.asian_handicap_movement_weight == 0.0
    assert report.best_control_candidate.asian_handicap_line_movement_weight == 0.0
    assert report.best_effective_candidate is not None
    assert report.best_effective_candidate.effective_asian_handicap_role is True
    assert report.summary_json["shadow_only"] is True


def test_asian_handicap_role_search_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "--baseline-slice-path",
            "baseline.json",
            "--candidate-slice-path",
            "candidate.json",
            "--role-search-id",
            "ah-role-cli-test",
            "--baseline-label",
            "base",
            "--candidate-label",
            "candidate",
            "--asian-handicap-movement-weights",
            "0,0.1,0.25",
            "--min-asian-handicap-probability-deltas",
            "0,0.04",
            "--asian-handicap-line-movement-weights",
            "0,0.05",
            "--min-asian-handicap-line-deltas",
            "0,0.25",
            "--asian-handicap-line-movement-scale",
            "1.5",
            "--asian-handicap-line-movement-transforms",
            "linear,signed_sqrt",
            "--min-effective-asian-handicap-weight",
            "0.05",
            "--min-validation-count",
            "24",
            "--max-brier-score-regression",
            "0.01",
            "--max-log-loss-regression",
            "0.02",
            "--max-expected-calibration-error-regression",
            "0.03",
            "--min-hit-rate-delta",
            "-0.01",
            "--lambda-method",
            "prematch_feature_adjusted",
            "--min-prior-matches",
            "12",
            "--min-team-matches",
            "3",
            "--prematch-feature-odds-movement-weight",
            "0.7",
            "--prematch-feature-asian-handicap-movement-weight",
            "0.5",
            "--prematch-feature-min-asian-handicap-probability-delta",
            "0.02",
            "--prematch-feature-asian-handicap-line-movement-weight",
            "0.1",
            "--prematch-feature-min-asian-handicap-line-delta",
            "0.25",
            "--prematch-feature-asian-handicap-line-movement-scale",
            "1.5",
            "--prematch-feature-asian-handicap-line-movement-transform",
            "signed_sqrt",
            "--min-prematch-feature-data-quality-score",
            "72",
            "--prediction-sample-limit",
            "4",
        ]
    )

    options = _options_from_args(args)

    assert options.role_search_id == "ah-role-cli-test"
    assert options.baseline_label == "base"
    assert options.candidate_label == "candidate"
    assert options.asian_handicap_movement_weights == (0.0, 0.1, 0.25)
    assert options.min_asian_handicap_probability_deltas == (0.0, 0.04)
    assert options.asian_handicap_line_movement_weights == (0.0, 0.05)
    assert options.min_asian_handicap_line_deltas == (0.0, 0.25)
    assert options.asian_handicap_line_movement_scale == 1.5
    assert options.asian_handicap_line_movement_transforms == ("linear", "signed_sqrt")
    assert options.min_effective_asian_handicap_weight == 0.05
    assert options.min_validation_count == 24
    assert options.max_brier_score_regression == 0.01
    assert options.max_log_loss_regression == 0.02
    assert options.max_expected_calibration_error_regression == 0.03
    assert options.min_hit_rate_delta == -0.01
    assert options.poisson_options.lambda_method == "prematch_feature_adjusted"
    assert options.poisson_options.min_prior_matches == 12
    assert options.poisson_options.min_team_matches == 3
    assert options.poisson_options.prematch_feature_odds_movement_weight == 0.7
    assert options.poisson_options.prematch_feature_asian_handicap_movement_weight == 0.5
    assert (
        options.poisson_options.prematch_feature_min_asian_handicap_probability_delta
        == 0.02
    )
    assert (
        options.poisson_options.prematch_feature_asian_handicap_line_movement_weight
        == 0.1
    )
    assert options.poisson_options.prematch_feature_min_asian_handicap_line_delta == 0.25
    assert (
        options.poisson_options.prematch_feature_asian_handicap_line_movement_scale
        == 1.5
    )
    assert (
        options.poisson_options.prematch_feature_asian_handicap_line_movement_transform
        == "signed_sqrt"
    )
    assert options.poisson_options.min_prematch_feature_data_quality_score == 72
    assert options.poisson_options.prediction_sample_limit == 4


def _poisson_options() -> HistoricalPoissonWalkForwardOptions:
    return HistoricalPoissonWalkForwardOptions(
        lambda_method="prematch_feature_adjusted",
        min_prior_matches=6,
        min_team_matches=2,
        max_training_results=20,
        min_bucket_sample_size=1,
        min_prematch_feature_data_quality_score=70.0,
        prediction_sample_limit=10,
    )


def _walk_forward_slice(
    *,
    include_asian_handicap: bool,
) -> HistoricalRecommendationSlice:
    base_time = datetime(2024, 8, 1, 12, tzinfo=UTC)
    raw_fixtures = [
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
            slice_id=(
                "prematch_feature_ah_role_with_ah_test"
                if include_asian_handicap
                else "prematch_feature_ah_role_1x2_only_test"
            ),
            name="Prematch feature Asian-handicap role search test",
            competition_id="TEST",
            season="2024",
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test market movement",
        ),
        as_of_time_utc=base_time,
        fixtures=[
            fixture.model_copy(
                update={
                    "feature_snapshot": _prematch_feature_snapshot(
                        fixture,
                        include_asian_handicap=include_asian_handicap,
                    )
                }
            )
            for fixture in raw_fixtures
        ],
    )


def _prematch_feature_snapshot(
    fixture: HistoricalFixture,
    *,
    include_asian_handicap: bool,
):
    feature_time = fixture.prediction_time_utc - timedelta(minutes=15)
    odds_movements = [
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
    ]
    if include_asian_handicap:
        odds_movements.append(
            PrematchOddsMovementFeature(
                market_type="asian_handicap",
                outcome="home_cover",
                bookmaker_disagreement=0.04,
                market_delay_signal=0.01,
                points=[
                    PrematchOddsMovementPoint(
                        snapshot_time_utc=feature_time - timedelta(hours=8),
                        market_type="asian_handicap",
                        outcome="home_cover",
                        decimal_odds=1.95,
                        fair_probability=0.50,
                        bookmaker_count=6,
                    ),
                    PrematchOddsMovementPoint(
                        snapshot_time_utc=feature_time - timedelta(minutes=5),
                        market_type="asian_handicap",
                        outcome="home_cover",
                        decimal_odds=1.75,
                        fair_probability=0.58,
                        bookmaker_count=7,
                    ),
                ],
            )
        )
    return build_structured_prematch_feature_snapshot(
        fixture_id=fixture.fixture_id,
        competition_id=fixture.competition_id,
        kickoff_time_utc=fixture.kickoff_time_utc,
        feature_time_utc=feature_time,
        fixture_reliability=1.0,
        historical_stats_completeness=0.90,
        provider_consistency=0.95,
        prematch_features=StructuredPrematchFeatureSet(
            odds_movements=odds_movements,
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
