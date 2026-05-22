from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
    HistoricalFeatureCompletenessOptions,
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    evaluate_historical_feature_completeness,
    evaluate_historical_feature_completeness_suite,
)
from nutmeg.recommendations.historical_feature_completeness import (
    _options_from_args,
    _parse_args,
)


def test_historical_feature_completeness_passes_structured_prematch_slice() -> None:
    historical_slice = _feature_slice()

    result = evaluate_historical_feature_completeness(
        historical_slice,
        options=HistoricalFeatureCompletenessOptions(
            min_fixture_count=2,
            min_feature_snapshot_coverage=1.0,
            min_lineup_coverage=1.0,
            min_availability_coverage=1.0,
            min_odds_movement_coverage=1.0,
            min_semantic_signal_coverage=1.0,
            min_source_ref_coverage=1.0,
            min_feature_data_quality_score=85.0,
        ),
    )

    assert result.passed is True
    assert result.status == "passed"
    assert result.summary_json["fixture_count"] == 2
    assert result.summary_json["feature_snapshot_coverage"] == 1.0
    assert result.summary_json["lineup_coverage"] == 1.0
    assert result.summary_json["odds_movement_coverage"] == 1.0
    assert result.summary_json["failed_checks"] == []


def test_historical_feature_completeness_fails_missing_and_leaky_features() -> None:
    historical_slice = _feature_slice()
    historical_slice.fixtures[0] = historical_slice.fixtures[0].model_copy(
        update={"feature_snapshot": None},
    )
    late_snapshot = historical_slice.fixtures[1].feature_snapshot
    assert late_snapshot is not None
    historical_slice.fixtures[1] = historical_slice.fixtures[1].model_copy(
        update={
            "feature_snapshot": late_snapshot.model_copy(
                update={
                    "feature_time_utc": historical_slice.fixtures[
                        1
                    ].prediction_time_utc
                    + timedelta(minutes=10),
                    "features_json": {
                        **late_snapshot.features_json,
                        "prematch_context": {
                            **late_snapshot.features_json["prematch_context"],
                            "availability": None,
                            "semantic_signals": [],
                        },
                    },
                },
            )
        },
    )

    result = evaluate_historical_feature_completeness(
        historical_slice,
        options=HistoricalFeatureCompletenessOptions(
            min_feature_snapshot_coverage=1.0,
            min_availability_coverage=1.0,
            min_semantic_signal_coverage=1.0,
        ),
    )
    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert failed_checks == {
        "feature_snapshot_coverage",
        "prematch_context_coverage",
        "availability_coverage",
        "semantic_signal_coverage",
        "feature_after_prediction_count",
    }
    assert result.summary_json["missing_prematch_context_fixture_ids"] == [
        "feature_gate_001"
    ]
    assert result.summary_json["feature_after_prediction_fixture_ids"] == [
        "feature_gate_002"
    ]


def test_historical_feature_completeness_suite_aggregates_results() -> None:
    good_slice = _feature_slice()
    bad_slice = _feature_slice("bad_feature_slice")
    bad_slice.fixtures[0] = bad_slice.fixtures[0].model_copy(
        update={"feature_snapshot": None},
    )

    result = evaluate_historical_feature_completeness_suite(
        [good_slice, bad_slice],
        options=HistoricalFeatureCompletenessOptions(
            min_feature_snapshot_coverage=1.0,
        ),
    )

    assert result.passed is False
    assert result.slice_count == 2
    assert result.summary_json["passed_slice_count"] == 1
    assert result.summary_json["failed_slice_ids"] == ["bad_feature_slice"]
    assert result.summary_json["feature_snapshot_coverage"] == 0.75


def test_historical_feature_completeness_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--output-path",
            "tmp/feature_completeness.json",
            "--min-fixture-count",
            "10",
            "--min-feature-snapshot-coverage",
            "0.90",
            "--min-lineup-coverage",
            "0.80",
            "--min-availability-coverage",
            "0.75",
            "--min-odds-movement-coverage",
            "0.70",
            "--min-semantic-signal-coverage",
            "0.25",
            "--min-source-ref-coverage",
            "0.95",
            "--min-average-feature-data-quality-score",
            "82",
            "--min-feature-data-quality-score",
            "70",
            "--allow-missing-prematch-context",
            "--allow-feature-after-prediction",
            "--allow-feature-not-before-kickoff",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path.name == "feature_completeness.json"
    assert options.min_fixture_count == 10
    assert options.min_feature_snapshot_coverage == 0.90
    assert options.min_lineup_coverage == 0.80
    assert options.min_availability_coverage == 0.75
    assert options.min_odds_movement_coverage == 0.70
    assert options.min_semantic_signal_coverage == 0.25
    assert options.min_source_ref_coverage == 0.95
    assert options.min_average_feature_data_quality_score == 82
    assert options.min_feature_data_quality_score == 70
    assert options.require_prematch_context is False
    assert options.require_feature_not_after_prediction is False
    assert options.require_feature_before_kickoff is False


def _feature_slice(slice_id: str = "feature_gate_slice") -> HistoricalRecommendationSlice:
    kickoff = datetime(2026, 5, 8, 19, 0, tzinfo=UTC)
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name="Feature gate slice",
            competition_id="EPL",
            season="2025-2026",
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=kickoff - timedelta(hours=1),
        fixtures=[
            _fixture("feature_gate_001", kickoff),
            _fixture("feature_gate_002", kickoff + timedelta(days=1)),
        ],
    )


def _fixture(fixture_id: str, kickoff_time_utc: datetime) -> HistoricalFixture:
    prediction_time = kickoff_time_utc - timedelta(hours=1)
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="EPL",
        kickoff_time_utc=kickoff_time_utc,
        home_team_name="Alpha",
        away_team_name="Bravo",
        actual_home_goals=2,
        actual_away_goals=1,
        prediction_time_utc=prediction_time,
        model_version="feature-gate-test-model",
        feature_version="features-v3.1-prematch-structured",
        calibration_version="unit-test",
        predictions=[
            _prediction("home_win", 0.52, 1.95),
            _prediction("draw", 0.25, 3.40),
            _prediction("away_win", 0.23, 4.10),
        ],
        feature_snapshot=build_structured_prematch_feature_snapshot(
            fixture_id=fixture_id,
            competition_id="EPL",
            kickoff_time_utc=kickoff_time_utc,
            feature_time_utc=prediction_time,
            historical_stats_completeness=0.82,
            provider_consistency=0.93,
            prematch_features=_prematch_features(prediction_time),
        ),
    )


def _prediction(outcome: str, probability: float, odds: float) -> HistoricalMarketPrediction:
    return HistoricalMarketPrediction(
        market_type="1x2",
        outcome=outcome,
        probability=probability,
        decimal_odds=odds,
        market_probability=probability,
    )


def _prematch_features(feature_time_utc: datetime) -> StructuredPrematchFeatureSet:
    return StructuredPrematchFeatureSet(
        lineup=PrematchLineupFeature(
            lineup_type="expected",
            snapshot_time_utc=feature_time_utc - timedelta(minutes=30),
            expected_lineup_confidence=0.85,
            starting_xi_strength=0.80,
            source="sportmonks",
            source_snapshot_ref="lineup:unit-test",
        ),
        availability=PrematchAvailabilityFeature(
            snapshot_time_utc=feature_time_utc - timedelta(hours=2),
            unavailable_key_player_count=1,
            key_player_absence_score=0.30,
            source="sportmonks",
            source_snapshot_ref="availability:unit-test",
        ),
        odds_movements=[
            PrematchOddsMovementFeature(
                market_type="1x2",
                outcome="home_win",
                points=[
                    PrematchOddsMovementPoint(
                        snapshot_time_utc=feature_time_utc - timedelta(hours=6),
                        market_type="1x2",
                        outcome="home_win",
                        decimal_odds=2.10,
                        fair_probability=0.48,
                        source="the_odds_api",
                        source_snapshot_ref="odds:opening",
                    ),
                    PrematchOddsMovementPoint(
                        snapshot_time_utc=feature_time_utc - timedelta(minutes=10),
                        market_type="1x2",
                        outcome="home_win",
                        decimal_odds=1.95,
                        fair_probability=0.52,
                        source="the_odds_api",
                        source_snapshot_ref="odds:current",
                    ),
                ],
            )
        ],
        semantic_signals=[
            PrematchSemanticSignal(
                signal_name="press_conference_injury_hint",
                source="club_press_conference",
                confidence=0.72,
                evidence_text_short="Coach said the striker is a late decision.",
                extracted_at_utc=feature_time_utc - timedelta(minutes=20),
            )
        ],
    )
