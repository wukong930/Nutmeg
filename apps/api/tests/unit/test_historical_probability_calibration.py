from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nutmeg.accuracy import (
    HistoricalProbabilityCalibrationGroup,
    HistoricalProbabilityCalibrationOptions,
    HistoricalProbabilityCalibrationReport,
    build_historical_probability_calibration_report,
)
from nutmeg.accuracy.historical_probability_calibration import (
    _options_from_args,
    _parse_args,
)
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)


def test_historical_probability_calibration_detects_overconfident_1x2_bucket() -> None:
    historical_slice = _calibration_slice()

    report = build_historical_probability_calibration_report(
        [historical_slice],
        options=HistoricalProbabilityCalibrationOptions(
            min_bucket_sample_size=4,
            min_group_sample_size=4,
            max_expected_calibration_error=0.20,
            top_group_limit=3,
        ),
    )

    home_group = _group(report, outcome="home_win")

    assert report.observation_count == 12
    assert report.groups_needing_calibration_count >= 1
    assert report.warnings == [
        "historical_probability_calibration:groups_need_calibration"
    ]
    assert home_group.decision == "needs_calibration"
    assert home_group.expected_calibration_error == pytest.approx(0.45)
    assert home_group.brier_score == pytest.approx(0.39)
    assert home_group.brier_score_delta_vs_market == pytest.approx(0.2025)
    assert home_group.decision_reasons == [
        "expected_calibration_error_above_threshold"
    ]


def test_historical_probability_calibration_marks_small_groups_insufficient() -> None:
    historical_slice = _calibration_slice()

    report = build_historical_probability_calibration_report(
        [historical_slice],
        options=HistoricalProbabilityCalibrationOptions(
            min_bucket_sample_size=5,
            min_group_sample_size=5,
        ),
    )

    assert {group.decision for group in report.groups} == {"insufficient_samples"}
    assert report.insufficient_group_count == 3
    assert report.overall_expected_calibration_error is None


def test_historical_probability_calibration_can_group_all_competitions() -> None:
    first_slice = _calibration_slice()
    second_slice = _calibration_slice(competition_id="ESP_LA_LIGA", fixture_prefix="laliga")

    report = build_historical_probability_calibration_report(
        [first_slice, second_slice],
        options=HistoricalProbabilityCalibrationOptions(
            min_bucket_sample_size=8,
            min_group_sample_size=8,
            group_by_competition=False,
        ),
    )

    home_group = _group(report, outcome="home_win")

    assert home_group.competition_id is None
    assert home_group.sample_size == 8
    assert home_group.group_key.split("|")[2] == "ALL_COMPETITIONS"


def test_historical_probability_calibration_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--market-types",
            "1x2,correct_score",
            "--bucket-size",
            "0.05",
            "--min-bucket-sample-size",
            "8",
            "--min-group-sample-size",
            "40",
            "--max-expected-calibration-error",
            "0.06",
            "--max-brier-score",
            "0.24",
            "--max-brier-score-delta-vs-market",
            "0.02",
            "--max-log-loss-delta-vs-market",
            "0.05",
            "--no-market-baseline",
            "--group-all-competitions",
            "--top-group-limit",
            "5",
        ]
    )

    options = _options_from_args(args)

    assert options.market_types == ("1x2", "correct_score")
    assert options.bucket_size == 0.05
    assert options.min_bucket_sample_size == 8
    assert options.min_group_sample_size == 40
    assert options.max_expected_calibration_error == 0.06
    assert options.max_brier_score == 0.24
    assert options.max_brier_score_delta_vs_market == 0.02
    assert options.max_log_loss_delta_vs_market == 0.05
    assert options.include_market_baseline is False
    assert options.group_by_competition is False
    assert options.top_group_limit == 5


def _group(
    report: HistoricalProbabilityCalibrationReport,
    *,
    outcome: str,
) -> HistoricalProbabilityCalibrationGroup:
    matching_groups = [
        group
        for group in report.groups
        if group.market_type == "1x2" and group.outcome == outcome
    ]
    assert len(matching_groups) == 1
    return matching_groups[0]


def _calibration_slice(
    *,
    competition_id: str = "EPL",
    fixture_prefix: str = "epl",
) -> HistoricalRecommendationSlice:
    base_time = datetime(2024, 8, 1, 12, tzinfo=UTC)
    results = [(1, 0), (0, 1), (1, 2), (2, 2)]
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=f"{fixture_prefix}_calibration_slice",
            name="Calibration slice",
            competition_id=competition_id,
            season="2024-2025",
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=base_time,
        fixtures=[
            HistoricalFixture(
                fixture_id=f"{fixture_prefix}_{index}",
                competition_id=competition_id,
                kickoff_time_utc=base_time + timedelta(days=index + 1),
                home_team_name=f"Home {index}",
                away_team_name=f"Away {index}",
                actual_home_goals=home_goals,
                actual_away_goals=away_goals,
                prediction_time_utc=base_time,
                model_version="overconfident-poisson-v1",
                feature_version="unit-test",
                calibration_version="uncalibrated-v1",
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="home_win",
                        probability=0.70,
                        decimal_odds=1.45,
                        market_probability=0.25,
                    ),
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="draw",
                        probability=0.15,
                        decimal_odds=4.50,
                        market_probability=0.25,
                    ),
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="away_win",
                        probability=0.15,
                        decimal_odds=4.50,
                        market_probability=0.50,
                    ),
                ],
            )
            for index, (home_goals, away_goals) in enumerate(results)
        ],
    )
