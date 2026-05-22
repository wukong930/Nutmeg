from __future__ import annotations

from pytest import approx

from nutmeg.accuracy import (
    HistoricalPrematchFeatureAblationOptions,
    build_historical_prematch_feature_ablation_report,
)
from nutmeg.accuracy.historical_prematch_feature_ablation import (
    _options_from_args,
    _parse_args,
)
from nutmeg.recommendations import (
    build_enriched_historical_feature_sample,
    load_historical_recommendation_slice,
)


def test_prematch_feature_ablation_reads_enriched_payload_and_improves_smoke_metrics() -> None:
    historical_slice = build_enriched_historical_feature_sample().historical_slice

    report = build_historical_prematch_feature_ablation_report(
        [historical_slice],
        options=HistoricalPrematchFeatureAblationOptions(
            min_feature_data_quality_score=80.0,
            min_bucket_sample_size=1,
            prediction_sample_limit=10,
        ),
    )

    assert report.validation_count == 6
    assert report.skipped_count == 0
    assert report.summary_json["shadow_only"] is True
    assert report.overall.candidate.brier_score is not None
    assert report.overall.baseline.brier_score is not None
    assert (
        report.overall.candidate.brier_score
        < report.overall.baseline.brier_score
    )
    assert report.overall.candidate.average_actual_probability is not None
    assert report.overall.baseline.average_actual_probability is not None
    assert (
        report.overall.candidate.average_actual_probability
        > report.overall.baseline.average_actual_probability
    )

    fragile_favorite = _sample(report, "enriched_feature_002")
    assert fragile_favorite.tracked_outcome == "home_win"
    assert fragile_favorite.tracked_outcome_fragility_score > 0.25
    assert fragile_favorite.candidate_probabilities["draw"] > (
        fragile_favorite.baseline_probabilities["draw"]
    )
    assert "tracked_outcome_fragility_shift" in fragile_favorite.adjustment_json[
        "reason_codes"
    ]

    away_value_shift = _sample(report, "enriched_feature_003")
    assert away_value_shift.candidate_probabilities["away_win"] > (
        away_value_shift.baseline_probabilities["away_win"]
    )


def test_prematch_feature_ablation_skips_slices_without_feature_snapshots() -> None:
    historical_slice = build_enriched_historical_feature_sample().historical_slice
    missing_features = historical_slice.model_copy(
        update={
            "fixtures": [
                fixture.model_copy(update={"feature_snapshot": None})
                for fixture in historical_slice.fixtures
            ]
        }
    )

    report = build_historical_prematch_feature_ablation_report(
        [missing_features],
        options=HistoricalPrematchFeatureAblationOptions(),
    )

    assert report.validation_count == 0
    assert report.skipped_count == 6
    assert report.skipped_reason_counts == {"missing_feature_snapshot": 6}
    assert report.warnings == [
        "historical_prematch_feature_ablation:no_validation_fixtures",
        "historical_prematch_feature_ablation:skipped_fixtures",
    ]


def test_prematch_feature_ablation_quantifies_context_only_sample() -> None:
    historical_slice = load_historical_recommendation_slice(
        "configs/recommendations/historical_slices/enriched_features/"
        "euro_2024_knockout_prematch_context_enriched_v1.json"
    )

    report = build_historical_prematch_feature_ablation_report(
        [historical_slice],
        options=HistoricalPrematchFeatureAblationOptions(
            min_feature_data_quality_score=45.0,
            min_bucket_sample_size=1,
            prediction_sample_limit=5,
        ),
    )

    assert report.validation_count == 2
    assert report.skipped_count == 0
    assert report.summary_json["signal_family_counts"] == {
        "availability": 2,
        "lineup": 2,
        "semantic": 2,
    }
    assert report.summary_json["reason_code_counts"][
        "context_only_no_odds_movement"
    ] == 2
    assert report.summary_json["average_key_player_absence_score"] == approx(0.115)
    assert report.summary_json["average_semantic_risk_score"] == approx(0.34)

    upset_context = _sample(report, "euro2024_r16_sui_ita")
    assert upset_context.semantic_risk_score == 0.68
    assert upset_context.key_player_absence_score == 0.18
    assert upset_context.source_ref_count == 3
    assert "semantic_signal_present" in upset_context.adjustment_json["reason_codes"]

    stable_context = _sample(report, "euro2024_r16_ger_den")
    assert stable_context.lineup_strength_score > 0.40
    assert "lineup_strength_shift" in stable_context.adjustment_json["reason_codes"]


def test_prematch_feature_ablation_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/enriched_features/nutmeg_enriched_prematch_feature_sample_v1.json",
            "--output-path",
            "tmp/prematch_feature_ablation.json",
            "--min-feature-data-quality-score",
            "88",
            "--max-probability-shift",
            "0.09",
            "--odds-movement-weight",
            "0.50",
            "--tracked-fragility-weight",
            "0.80",
            "--lineup-strength-weight",
            "0.25",
            "--draw-signal-weight",
            "0.45",
            "--bucket-size",
            "0.05",
            "--min-bucket-sample-size",
            "3",
            "--allow-feature-after-prediction",
            "--allow-feature-not-before-kickoff",
            "--model-version",
            "prematch-feature-test",
            "--feature-version",
            "feature-test",
            "--calibration-version",
            "calibration-test",
            "--prediction-sample-limit",
            "4",
        ]
    )

    options = _options_from_args(args)

    assert options.min_feature_data_quality_score == 88
    assert options.max_probability_shift == 0.09
    assert options.odds_movement_weight == 0.50
    assert options.tracked_fragility_weight == 0.80
    assert options.lineup_strength_weight == 0.25
    assert options.draw_signal_weight == 0.45
    assert options.bucket_size == 0.05
    assert options.min_bucket_sample_size == 3
    assert options.require_feature_not_after_prediction is False
    assert options.require_feature_before_kickoff is False
    assert options.model_version == "prematch-feature-test"
    assert options.feature_version == "feature-test"
    assert options.calibration_version == "calibration-test"
    assert options.prediction_sample_limit == 4


def _sample(
    report: object,
    fixture_id: str,
):
    return next(
        sample
        for sample in report.sampled_predictions
        if sample.fixture_id == fixture_id
    )
