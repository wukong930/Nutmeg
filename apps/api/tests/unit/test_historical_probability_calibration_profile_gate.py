from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nutmeg.accuracy import HistoricalProbabilityCalibrationTransformOptions
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationBacktestOptions,
)
from nutmeg.recommendations.historical_probability_calibration_profile_gate import (
    HistoricalProbabilityCalibrationProfileGateOptions,
    _options_from_args,
    _parse_args,
    _profile_gate_slices,
    _stdout_payload,
    build_historical_probability_calibration_profile_gate_report,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)


def test_probability_calibration_profile_gate_runs_accepted_competition_holdout() -> None:
    slices = [
        _season_slice("2021", 0, [(1, 0), (0, 0), (0, 1), (0, 2)]),
        _season_slice("2022", 10, [(2, 0), (1, 1), (1, 2), (2, 2)]),
        _season_slice("2023", 20, [(0, 0), (0, 1), (2, 2), (1, 3)]),
    ]

    report = build_historical_probability_calibration_profile_gate_report(
        slices,
        options=HistoricalProbabilityCalibrationProfileGateOptions(
            transform_options=HistoricalProbabilityCalibrationTransformOptions(
                min_training_season_count=2,
                min_validation_sample_size=1,
                segment_mode="market_odds_band",
                min_bucket_sample_size=1,
                bucket_size=0.10,
                prediction_sample_limit=0,
            ),
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1",),
                modes=("single",),
                optimizer_profile="solver",
                min_probability=0.05,
                max_candidates_per_fixture=3,
            ),
            quality_gate_options=_permissive_quality_gate_options(),
        ),
    )

    assert report.selected_competition_ids == ["TEST"]
    assert report.rejected_competition_ids == []
    assert report.baseline_slice_count == 1
    assert report.adjusted_slice_count == 1
    assert report.adjusted_fixture_count == 4
    assert report.suite is not None
    assert report.quality_gate is not None
    assert report.passed_final_answer_gate is True
    assert report.summary_json["shadow_only"] is True
    assert report.summary_json["segment_mode"] == "market_odds_band"


def test_probability_calibration_profile_gate_blocks_without_accepted_transform() -> None:
    slices = [
        _season_slice("2021", 0, [(1, 0), (0, 0), (0, 1), (0, 2)]),
        _season_slice("2022", 10, [(2, 0), (1, 1), (1, 2), (2, 2)]),
        _season_slice("2023", 20, [(0, 0), (0, 1), (2, 2), (1, 3)]),
    ]

    report = build_historical_probability_calibration_profile_gate_report(
        slices,
        options=HistoricalProbabilityCalibrationProfileGateOptions(
            transform_options=HistoricalProbabilityCalibrationTransformOptions(
                min_training_season_count=2,
                min_validation_sample_size=1,
                min_bucket_sample_size=100,
                bucket_size=0.10,
                prediction_sample_limit=0,
            ),
            quality_gate_options=_permissive_quality_gate_options(),
        ),
    )

    assert report.selected_competition_ids == []
    assert report.rejected_competition_ids == ["TEST"]
    assert report.suite is None
    assert report.quality_gate is None
    assert report.passed_final_answer_gate is False
    assert "no_selected_competitions" in report.warnings[-1]


def test_probability_calibration_profile_gate_stdout_summary_is_compact() -> None:
    slices = [
        _season_slice("2021", 0, [(1, 0), (0, 0), (0, 1), (0, 2)]),
        _season_slice("2022", 10, [(2, 0), (1, 1), (1, 2), (2, 2)]),
        _season_slice("2023", 20, [(0, 0), (0, 1), (2, 2), (1, 3)]),
    ]
    report = build_historical_probability_calibration_profile_gate_report(
        slices,
        options=HistoricalProbabilityCalibrationProfileGateOptions(
            transform_options=HistoricalProbabilityCalibrationTransformOptions(
                min_training_season_count=2,
                min_validation_sample_size=1,
                min_bucket_sample_size=1,
                prediction_sample_limit=0,
            ),
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1",),
                modes=("single",),
                optimizer_profile="solver",
                min_probability=0.05,
                max_candidates_per_fixture=3,
            ),
            quality_gate_options=_permissive_quality_gate_options(),
        ),
    )
    report.summary_json["suite_manifest"] = {"resolved_slice_paths": ["large.json"]}

    payload = _stdout_payload(report, summary_only=True)

    assert payload["report_key"] == report.report_key
    assert payload["suite"] is not None
    assert "aggregate_deltas_json" in payload["suite"]
    assert payload["quality_gate"] is not None
    assert payload["quality_gate"]["failed_checks"] == []
    assert "suite_manifest" not in payload["summary_json"]
    assert "comparisons" not in payload["suite"]


def test_probability_calibration_profile_gate_can_target_one_outcome_band() -> None:
    slices = [
        _season_slice("2021", 0, [(1, 0), (0, 0), (0, 1), (0, 2)]),
        _season_slice("2022", 10, [(2, 0), (1, 1), (1, 2), (2, 2)]),
        _season_slice("2023", 20, [(0, 0), (0, 1), (2, 2), (1, 3)]),
    ]
    options = HistoricalProbabilityCalibrationProfileGateOptions(
        target_outcomes=("home_win",),
        probability_min=0.70,
        probability_max=0.90,
        max_decimal_odds=1.30,
        transform_options=HistoricalProbabilityCalibrationTransformOptions(
            min_training_season_count=2,
            min_validation_sample_size=1,
            min_bucket_sample_size=1,
            bucket_size=0.10,
            prediction_sample_limit=0,
        ),
    )

    baseline_slices, adjusted_slices, adjusted_count, skipped_count = _profile_gate_slices(
        slices,
        selected_competition_ids=["TEST"],
        options=options,
        transform_report_key="transform:test",
    )

    first_fixture = adjusted_slices[0].fixtures[0]
    adjusted_predictions = [
        prediction
        for prediction in first_fixture.predictions
        if prediction.metadata_json.get("probability_calibration_profile_shadow_adjusted")
        is True
    ]

    assert len(baseline_slices) == 1
    assert len(adjusted_slices) == 1
    assert adjusted_count == 4
    assert skipped_count == 0
    assert [prediction.outcome for prediction in adjusted_predictions] == ["home_win"]
    assert adjusted_predictions[0].metadata_json[
        "probability_calibration_profile_target_outcomes"
    ] == ["home_win"]
    assert adjusted_predictions[0].metadata_json[
        "probability_calibration_profile_segment_mode"
    ] == "probability_bucket"


def test_probability_calibration_profile_gate_holdout_keeps_all_windows_in_last_season() -> None:
    slices = [
        _windowed_season_slice("2021", 1, 0, [(1, 0), (0, 0)]),
        _windowed_season_slice("2021", 2, 2, [(0, 1), (0, 2)]),
        _windowed_season_slice("2022", 1, 10, [(2, 0), (1, 1)]),
        _windowed_season_slice("2022", 2, 12, [(1, 2), (2, 2)]),
        _windowed_season_slice("2023", 1, 20, [(0, 0), (0, 1)]),
        _windowed_season_slice("2023", 2, 22, [(2, 2), (1, 3)]),
    ]
    options = HistoricalProbabilityCalibrationProfileGateOptions(
        target_outcomes=("home_win",),
        transform_options=HistoricalProbabilityCalibrationTransformOptions(
            min_training_season_count=2,
            min_validation_sample_size=1,
            min_bucket_sample_size=1,
            bucket_size=0.10,
            prediction_sample_limit=0,
        ),
    )

    baseline_slices, adjusted_slices, adjusted_count, skipped_count = _profile_gate_slices(
        slices,
        selected_competition_ids=["TEST"],
        options=options,
        transform_report_key="transform:test",
    )

    assert [item.metadata.season for item in baseline_slices] == ["2023", "2023"]
    assert len(adjusted_slices) == 2
    assert adjusted_count == 4
    assert skipped_count == 0


def test_probability_calibration_profile_gate_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--gate-id",
            "calibration-profile-test",
            "--competition-ids",
            "ESP_LA_LIGA,ITA_SERIE_A",
            "--include-rejected-transform-competitions",
            "--target-outcomes",
            "home_win,draw",
            "--probability-min",
            "0.30",
            "--probability-max",
            "0.80",
            "--min-decimal-odds",
            "1.40",
            "--max-decimal-odds",
            "3.50",
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
            "0.6",
            "--min-calibrated-probability",
            "0.02",
            "--max-calibrated-probability",
            "0.90",
            "--group-all-competitions",
            "--pass-types",
            "1x1,2x1",
            "--modes",
            "single",
            "--optimizer-profile",
            "heuristic",
            "--unit-stake",
            "3",
            "--max-budget",
            "30",
            "--min-probability",
            "0.2",
            "--candidate-fixture-limit",
            "24",
            "--max-candidates-per-fixture",
            "2",
            "--final-answer-scenario-variant-count",
            "3",
            "--derive-market-context-signals",
            "--min-final-hit-sample-size",
            "20",
            "--min-final-hit-rate-delta",
            "0.01",
            "--min-final-answer-changed-count",
            "3",
            "--min-roi-delta",
            "0.02",
            "--min-profit-loss-delta",
            "1.5",
            "--max-brier-score-delta",
            "0.03",
            "--max-log-loss-delta",
            "0.04",
            "--max-mean-calibration-error-delta",
            "0.05",
            "--stdout-summary-only",
        ]
    )

    options = _options_from_args(args)

    assert options.gate_id == "calibration-profile-test"
    assert options.competition_ids == ("ESP_LA_LIGA", "ITA_SERIE_A")
    assert options.require_transform_acceptance is False
    assert options.target_outcomes == ("home_win", "draw")
    assert options.probability_min == 0.30
    assert options.probability_max == 0.80
    assert options.min_decimal_odds == 1.40
    assert options.max_decimal_odds == 3.50
    assert options.transform_options.holdout_season_count == 2
    assert options.transform_options.min_training_season_count == 3
    assert options.transform_options.min_validation_sample_size == 50
    assert options.transform_options.segment_mode == "market_odds_band"
    assert options.transform_options.bucket_size == 0.05
    assert options.transform_options.min_bucket_sample_size == 12
    assert options.transform_options.blend_weight == 0.6
    assert options.transform_options.min_calibrated_probability == 0.02
    assert options.transform_options.max_calibrated_probability == 0.90
    assert options.transform_options.group_by_competition is False
    assert options.backtest_options.pass_types == ("1x1", "2x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.optimizer_profile == "heuristic"
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 30
    assert options.backtest_options.min_probability == 0.2
    assert options.backtest_options.candidate_fixture_limit == 24
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.final_answer_scenario_variant_count == 3
    assert options.backtest_options.derive_market_context_signals is True
    assert options.quality_gate_options.min_final_hit_sample_size == 20
    assert options.quality_gate_options.min_final_hit_rate_delta == 0.01
    assert options.quality_gate_options.min_final_answer_changed_count == 3
    assert options.quality_gate_options.min_roi_delta == 0.02
    assert options.quality_gate_options.min_profit_loss_delta == 1.5
    assert options.quality_gate_options.max_brier_score_delta == 0.03
    assert options.quality_gate_options.max_log_loss_delta == 0.04
    assert options.quality_gate_options.max_mean_calibration_error_delta == 0.05
    assert args.stdout_summary_only is True


def _permissive_quality_gate_options() -> HistoricalRecommendationSuiteQualityGateOptions:
    return HistoricalRecommendationSuiteQualityGateOptions(
        min_final_hit_sample_size=1,
        fail_on_suite_statuses=(),
        min_final_hit_rate_delta=None,
        max_brier_score_delta=None,
        max_log_loss_delta=None,
        max_mean_calibration_error_delta=None,
    )


def _season_slice(
    season: str,
    day_offset: int,
    results: list[tuple[int, int]],
) -> HistoricalRecommendationSlice:
    base_time = datetime(2024, 8, 1, 12, tzinfo=UTC) + timedelta(days=day_offset)
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=f"calibration_profile_gate_{season}",
            name=f"Calibration profile gate {season}",
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
