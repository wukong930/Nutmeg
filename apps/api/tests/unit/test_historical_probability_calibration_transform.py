from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nutmeg.accuracy import (
    HistoricalProbabilityCalibrationTransformOptions,
    build_historical_probability_calibration_transform_report,
)
from nutmeg.accuracy.historical_probability_calibration_transform import (
    _options_from_args,
    _parse_args,
)
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)


def test_historical_probability_calibration_transform_improves_holdout() -> None:
    slices = [
        _season_slice("2021", 0, [(1, 0), (0, 0), (0, 1), (0, 2)]),
        _season_slice("2022", 10, [(2, 0), (1, 1), (1, 2), (2, 2)]),
        _season_slice("2023", 20, [(0, 0), (0, 1), (2, 2), (1, 3)]),
    ]

    report = build_historical_probability_calibration_transform_report(
        slices,
        options=HistoricalProbabilityCalibrationTransformOptions(
            min_training_season_count=2,
            min_validation_sample_size=1,
            min_bucket_sample_size=1,
            bucket_size=0.10,
            prediction_sample_limit=10,
        ),
    )

    result = report.competitions[0]

    assert report.learned_competition_count == 1
    assert result.training_seasons == ["2021", "2022"]
    assert result.validation_seasons == ["2023"]
    assert result.decision == "accepted"
    assert result.usable_calibration_bucket_count == 3
    assert result.candidate.brier_score is not None
    assert result.baseline.brier_score is not None
    assert result.candidate.brier_score < result.baseline.brier_score
    assert result.candidate.log_loss is not None
    assert result.baseline.log_loss is not None
    assert result.candidate.log_loss < result.baseline.log_loss
    assert result.candidate.hit_rate is not None
    assert result.baseline.hit_rate is not None
    assert result.candidate.hit_rate > result.baseline.hit_rate
    assert report.overall_deltas_json["brier_score_delta"] < 0
    assert report.summary_json["shadow_only"] is True
    assert result.sampled_predictions[0].candidate_probabilities["home_win"] < (
        result.sampled_predictions[0].baseline_probabilities["home_win"]
    )


def test_historical_probability_calibration_transform_holdout_groups_windows_by_season() -> None:
    slices = [
        _windowed_season_slice("2021", 1, 0, [(1, 0), (0, 0)]),
        _windowed_season_slice("2021", 2, 2, [(0, 1), (0, 2)]),
        _windowed_season_slice("2022", 1, 10, [(2, 0), (1, 1)]),
        _windowed_season_slice("2022", 2, 12, [(1, 2), (2, 2)]),
        _windowed_season_slice("2023", 1, 20, [(0, 0), (0, 1)]),
        _windowed_season_slice("2023", 2, 22, [(2, 2), (1, 3)]),
    ]

    report = build_historical_probability_calibration_transform_report(
        slices,
        options=HistoricalProbabilityCalibrationTransformOptions(
            min_training_season_count=2,
            min_validation_sample_size=1,
            min_bucket_sample_size=1,
            bucket_size=0.10,
            prediction_sample_limit=10,
        ),
    )

    result = report.competitions[0]

    assert result.training_seasons == ["2021", "2022"]
    assert result.validation_seasons == ["2023"]
    assert result.training_fixture_count == 8
    assert result.validation_fixture_count == 4
    assert result.validation_count == 4


def test_historical_probability_calibration_transform_rejects_insufficient_buckets() -> None:
    slices = [
        _season_slice("2021", 0, [(1, 0), (0, 0), (0, 1), (0, 2)]),
        _season_slice("2022", 10, [(2, 0), (1, 1), (1, 2), (2, 2)]),
        _season_slice("2023", 20, [(0, 0), (0, 1), (2, 2), (1, 3)]),
    ]

    report = build_historical_probability_calibration_transform_report(
        slices,
        options=HistoricalProbabilityCalibrationTransformOptions(
            min_training_season_count=2,
            min_validation_sample_size=1,
            min_bucket_sample_size=100,
            bucket_size=0.10,
            prediction_sample_limit=10,
        ),
    )

    result = report.competitions[0]
    first_sample = result.sampled_predictions[0]

    assert result.decision == "rejected"
    assert "objective_improvement_missing" in result.decision_reasons
    assert result.usable_calibration_bucket_count == 0
    assert first_sample.candidate_probabilities == first_sample.baseline_probabilities
    assert first_sample.fallback_reason_counts == {
        "insufficient_calibration_bucket_samples": 3
    }


def test_historical_probability_calibration_transform_skips_without_training_seasons() -> None:
    report = build_historical_probability_calibration_transform_report(
        [_season_slice("2023", 0, [(1, 0), (0, 0), (0, 1), (0, 2)])],
        options=HistoricalProbabilityCalibrationTransformOptions(
            min_training_season_count=2,
            min_validation_sample_size=1,
        ),
    )

    result = report.competitions[0]

    assert report.learned_competition_count == 0
    assert result.decision == "rejected"
    assert result.decision_reasons == ["insufficient_training_seasons"]
    assert "insufficient_training_seasons" in report.warnings[0]


def test_historical_probability_calibration_transform_can_bucket_by_market_odds_band() -> None:
    slices = [
        _market_segment_slice("2021", 0, [(1, 0), (0, 0)]),
        _market_segment_slice("2022", 10, [(0, 1), (0, 2)]),
        _market_segment_slice("2023", 20, [(1, 1), (2, 2)]),
    ]

    report = build_historical_probability_calibration_transform_report(
        slices,
        options=HistoricalProbabilityCalibrationTransformOptions(
            min_training_season_count=2,
            min_validation_sample_size=1,
            min_bucket_sample_size=1,
            segment_mode="market_odds_band",
            bucket_size=0.10,
            prediction_sample_limit=10,
        ),
    )

    result = report.competitions[0]
    home_buckets = [
        bucket for bucket in report.sampled_calibration_buckets if bucket.outcome == "home_win"
    ]

    assert report.summary_json["segment_mode"] == "market_odds_band"
    assert result.summary_json["segment_mode"] == "market_odds_band"
    assert {bucket.segment_mode for bucket in home_buckets} == {"market_odds_band"}
    assert {bucket.bucket_start for bucket in home_buckets} == {0.5}
    assert result.sampled_predictions[0].applied_segment_probabilities["home_win"] == (
        pytest.approx(0.55)
    )
    assert result.sampled_predictions[0].applied_bucket_keys["home_win"].endswith(
        "|0.5000000000|0.6000000000"
    )


def test_historical_probability_calibration_transform_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--holdout-season-count",
            "2",
            "--min-training-season-count",
            "3",
            "--min-validation-sample-size",
            "50",
            "--segment-mode",
            "market_odds_band",
            "--bucket-size",
            "0.05",
            "--min-bucket-sample-size",
            "12",
            "--blend-weight",
            "0.65",
            "--min-calibrated-probability",
            "0.02",
            "--max-calibrated-probability",
            "0.90",
            "--group-all-competitions",
            "--min-hit-rate-delta",
            "0.01",
            "--max-brier-score-delta",
            "0.02",
            "--max-log-loss-delta",
            "0.03",
            "--max-expected-calibration-error-delta",
            "0.04",
            "--min-objective-improvement",
            "0.005",
            "--prediction-sample-limit",
            "4",
        ]
    )

    options = _options_from_args(args)

    assert options.holdout_season_count == 2
    assert options.min_training_season_count == 3
    assert options.min_validation_sample_size == 50
    assert options.segment_mode == "market_odds_band"
    assert options.bucket_size == 0.05
    assert options.min_bucket_sample_size == 12
    assert options.blend_weight == 0.65
    assert options.min_calibrated_probability == 0.02
    assert options.max_calibrated_probability == 0.90
    assert options.group_by_competition is False
    assert options.min_hit_rate_delta == 0.01
    assert options.max_brier_score_delta == 0.02
    assert options.max_log_loss_delta == 0.03
    assert options.max_expected_calibration_error_delta == 0.04
    assert options.min_objective_improvement == 0.005
    assert options.prediction_sample_limit == 4


def _season_slice(
    season: str,
    day_offset: int,
    results: list[tuple[int, int]],
) -> HistoricalRecommendationSlice:
    base_time = datetime(2024, 8, 1, 12, tzinfo=UTC) + timedelta(days=day_offset)
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=f"calibration_transform_{season}",
            name=f"Calibration transform {season}",
            competition_id="TEST",
            season=season,
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=base_time,
        fixtures=[
            _fixture(
                f"{season}_{index}",
                base_time + timedelta(days=index + 1),
                home_goals,
                away_goals,
            )
            for index, (home_goals, away_goals) in enumerate(results)
        ],
    )


def _market_segment_slice(
    season: str,
    day_offset: int,
    results: list[tuple[int, int]],
) -> HistoricalRecommendationSlice:
    base_time = datetime(2024, 8, 1, 12, tzinfo=UTC) + timedelta(days=day_offset)
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=f"market_segment_calibration_transform_{season}",
            name=f"Market segment calibration transform {season}",
            competition_id="TEST",
            season=season,
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=base_time,
        fixtures=[
            _market_segment_fixture(
                f"{season}_{index}",
                base_time + timedelta(days=index + 1),
                home_goals,
                away_goals,
            )
            for index, (home_goals, away_goals) in enumerate(results)
        ],
    )


def _windowed_season_slice(
    season: str,
    window_index: int,
    day_offset: int,
    results: list[tuple[int, int]],
) -> HistoricalRecommendationSlice:
    source = _season_slice(season, day_offset, results)
    return source.model_copy(
        update={
            "metadata": source.metadata.model_copy(
                update={
                    "slice_id": f"{source.metadata.slice_id}_window_{window_index:03d}",
                    "name": f"{source.metadata.name} window {window_index:03d}",
                }
            )
        }
    )


def _fixture(
    fixture_id: str,
    kickoff_time_utc: datetime,
    home_goals: int,
    away_goals: int,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=kickoff_time_utc,
        home_team_name=f"Home {fixture_id}",
        away_team_name=f"Away {fixture_id}",
        actual_home_goals=home_goals,
        actual_away_goals=away_goals,
        prediction_time_utc=kickoff_time_utc - timedelta(days=1),
        model_version="overconfident-home-v1",
        feature_version="unit-test",
        calibration_version="uncalibrated-v1",
        predictions=[
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="home_win",
                probability=0.80,
                decimal_odds=1.25,
                market_probability=0.80,
            ),
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="draw",
                probability=0.10,
                decimal_odds=10.0,
                market_probability=0.10,
            ),
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="away_win",
                probability=0.10,
                decimal_odds=10.0,
                market_probability=0.10,
            ),
        ],
    )


def _market_segment_fixture(
    fixture_id: str,
    kickoff_time_utc: datetime,
    home_goals: int,
    away_goals: int,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=kickoff_time_utc,
        home_team_name=f"Home {fixture_id}",
        away_team_name=f"Away {fixture_id}",
        actual_home_goals=home_goals,
        actual_away_goals=away_goals,
        prediction_time_utc=kickoff_time_utc - timedelta(days=1),
        model_version="overconfident-home-v1",
        feature_version="unit-test",
        calibration_version="uncalibrated-v1",
        predictions=[
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="home_win",
                probability=0.80,
                decimal_odds=1.82,
                market_probability=0.55,
            ),
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="draw",
                probability=0.10,
                decimal_odds=4.00,
                market_probability=0.25,
            ),
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome="away_win",
                probability=0.10,
                decimal_odds=5.00,
                market_probability=0.20,
            ),
        ],
    )
