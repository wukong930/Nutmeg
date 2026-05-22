from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nutmeg.recommendations import (
    HistoricalRecommendationSampleQualityOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceBuildOptions,
    build_historical_recommendation_slice_from_csv,
    evaluate_historical_recommendation_sample_quality,
    evaluate_historical_recommendation_sample_quality_suite,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_sample_quality import _options_from_args, _parse_args


def test_historical_sample_quality_passes_complete_builder_slice() -> None:
    historical_slice = _builder_slice()

    result = evaluate_historical_recommendation_sample_quality(
        historical_slice,
        options=HistoricalRecommendationSampleQualityOptions(
            min_fixture_count=2,
            require_market_probability=True,
            min_data_quality_score=80,
        ),
    )

    assert result.passed is True
    assert result.status == "passed"
    assert result.summary_json["fixture_count"] == 2
    assert result.summary_json["complete_1x2_fixture_count"] == 2
    assert result.summary_json["max_1x2_probability_sum_error"] == 0
    assert result.summary_json["failed_checks"] == []


def test_historical_sample_quality_passes_group_upset_stress_slice() -> None:
    historical_slice = load_historical_recommendation_slice(
        Path("configs/recommendations/historical_slices/euro_2024_group_upset_sample.json")
    )

    result = evaluate_historical_recommendation_sample_quality(
        historical_slice,
        options=HistoricalRecommendationSampleQualityOptions(
            min_fixture_count=7,
            require_market_probability=True,
            min_data_quality_score=80,
        ),
    )

    assert result.passed is True
    assert result.summary_json["fixture_count"] == 7
    assert result.summary_json["prediction_count"] == 21
    assert result.summary_json["complete_1x2_fixture_count"] == 7
    assert result.summary_json["minimum_data_quality_score"] == 83


def test_historical_sample_quality_fails_incomplete_and_duplicate_slice() -> None:
    historical_slice = _builder_slice().model_copy(deep=True)
    historical_slice.fixtures[0].predictions = historical_slice.fixtures[0].predictions[:1]
    historical_slice.fixtures.append(historical_slice.fixtures[0].model_copy(deep=True))

    result = evaluate_historical_recommendation_sample_quality(
        historical_slice,
        options=HistoricalRecommendationSampleQualityOptions(
            min_fixture_count=3,
            require_market_probability=True,
        ),
    )
    failed_checks = {check.name for check in result.checks if check.status == "failed"}

    assert result.passed is False
    assert result.status == "failed"
    assert failed_checks == {
        "duplicate_fixture_id_count",
        "duplicate_kickoff_matchup_count",
        "complete_1x2_fixture_count",
        "max_1x2_probability_sum_error",
    }
    assert result.summary_json["duplicate_fixture_id_count"] == 1
    assert result.summary_json["missing_1x2_fixture_ids"] == [
        "euro2024_r16_sui_ita",
        "euro2024_r16_sui_ita",
    ]


def test_historical_sample_quality_suite_aggregates_failures() -> None:
    good_slice = _builder_slice()
    bad_slice = _builder_slice().model_copy(deep=True)
    bad_slice.fixtures[0].predictions = bad_slice.fixtures[0].predictions[:1]

    result = evaluate_historical_recommendation_sample_quality_suite(
        [good_slice, bad_slice],
        options=HistoricalRecommendationSampleQualityOptions(),
    )

    assert result.passed is False
    assert result.slice_count == 2
    assert result.summary_json["passed_slice_count"] == 1
    assert result.summary_json["failed_slice_count"] == 1
    assert result.summary_json["failed_slice_ids"] == ["quality_test_slice"]


def test_historical_sample_quality_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--min-fixture-count",
            "4",
            "--allow-duplicate-fixture-ids",
            "--allow-duplicate-kickoff-matchups",
            "--allow-prediction-after-as-of",
            "--allow-kickoff-not-after-as-of",
            "--allow-incomplete-1x2",
            "--probability-sum-tolerance",
            "0.05",
            "--allow-missing-decimal-odds",
            "--require-market-probability",
            "--min-data-quality-score",
            "75",
        ]
    )

    options = _options_from_args(args)

    assert options.min_fixture_count == 4
    assert options.require_unique_fixture_ids is False
    assert options.require_unique_kickoff_matchups is False
    assert options.require_prediction_not_after_as_of is False
    assert options.require_kickoff_after_as_of is False
    assert options.require_1x2_complete is False
    assert options.probability_sum_tolerance == 0.05
    assert options.require_decimal_odds is False
    assert options.require_market_probability is True
    assert options.min_data_quality_score == 75


def _builder_slice() -> HistoricalRecommendationSlice:
    return build_historical_recommendation_slice_from_csv(
        Path("configs/recommendations/historical_slice_inputs/euro_2024_knockout_sample.csv"),
        options=HistoricalRecommendationSliceBuildOptions(
            slice_id="quality_test_slice",
            name="Quality test slice",
            competition_id="UEFA_EURO",
            as_of_time_utc=datetime(2024, 6, 29, 12, tzinfo=UTC),
            season="2024",
            result_source="unit test results",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
    ).slice
