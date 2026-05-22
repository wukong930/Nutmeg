from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    HistoricalUpsetCaptureGroup,
    HistoricalUpsetCaptureProfileOptions,
    build_historical_upset_capture_profile_report,
)
from nutmeg.recommendations.upset_capture_profiles import (
    _options_from_args,
    _parse_args,
)


def test_upset_capture_profiles_flag_selected_fragile_favorite_miss() -> None:
    report = build_historical_upset_capture_profile_report(
        [_slice(fixtures=[_fragile_favorite_miss_fixture("fragile_miss")])],
        options=HistoricalUpsetCaptureProfileOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1",),
                modes=("single",),
                strategy="accuracy_first",
                min_probability=0.01,
                unit_stake=2.0,
                max_budget=2.0,
            ),
            upset_threshold=0.35,
        ),
    )

    observation = report.observations[0]
    selection_group = _group(
        report.groups,
        "selection_state",
        "selection_state:selected_wrong_fixture",
    )
    favorite_fragility_group = _group(
        report.groups,
        "selected_favorite_fragility_band",
        "selected_favorite_fragility:score_0_45_0_64",
    )

    assert report.opportunity_count == 1
    assert report.capture_count == 0
    assert report.selected_wrong_fixture_count == 1
    assert report.selected_favorite_miss_count == 1
    assert observation.direction == "draw_overlooked"
    assert observation.selection_state == "selected_wrong_fixture"
    assert observation.selected_outcomes == ["home_win"]
    assert observation.selected_favorite_outcomes == ["home_win"]
    assert observation.selected_favorite_miss is True
    assert observation.selected_favorite_fragility_score == pytest.approx(0.55)
    assert selection_group.selected_favorite_miss_count == 1
    assert favorite_fragility_group.average_selected_favorite_fragility_score == pytest.approx(
        0.55
    )
    assert any(
        group.group_key == "selected_favorite_fragility:score_0_45_0_64"
        for group in report.favorite_fragility_miss_groups
    )


def test_upset_capture_profiles_keep_opportunity_diagnostic_after_core_first() -> None:
    report = build_historical_upset_capture_profile_report(
        [_slice(slice_id="captured_slice", fixtures=[_captured_draw_fixture()])],
        options=HistoricalUpsetCaptureProfileOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1",),
                modes=("single",),
                strategy="upset_protection",
                min_probability=0.01,
                unit_stake=2.0,
                max_budget=2.0,
            ),
            upset_threshold=0.35,
            derive_market_context_signals=True,
        ),
    )

    observation = report.observations[0]
    direction_group = _group(report.groups, "direction", "direction:draw_overlooked")

    assert report.opportunity_count == 1
    assert report.capture_count == 0
    assert report.capture_rate == 0.0
    assert not report.top_capture_groups
    assert observation.selection_state == "selected_wrong_fixture"
    assert observation.selected_outcomes == ["home_win"]
    assert observation.market_favorite_outcome == "home_win"
    assert observation.market_favorite_decimal_odds == pytest.approx(1.95)
    assert direction_group.opportunity_count == 1
    assert direction_group.capture_count == 0


def test_upset_capture_profiles_separate_unselected_upset_opportunities() -> None:
    report = build_historical_upset_capture_profile_report(
        [
            _slice(
                slice_id="not_selected_slice",
                fixtures=[
                    _safe_home_win_fixture("safe_home"),
                    _fragile_favorite_miss_fixture("missed_elsewhere"),
                ],
            )
        ],
        options=HistoricalUpsetCaptureProfileOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("1x1",),
                modes=("single",),
                strategy="accuracy_first",
                min_probability=0.01,
                unit_stake=2.0,
                max_budget=2.0,
            ),
            upset_threshold=0.35,
        ),
    )

    observation = report.observations[0]
    not_selected_group = _group(
        report.groups,
        "selection_state",
        "selection_state:not_selected",
    )

    assert report.opportunity_count == 1
    assert report.not_selected_count == 1
    assert observation.fixture_id == "missed_elsewhere"
    assert observation.selection_state == "not_selected"
    assert observation.selected_outcomes == []
    assert not_selected_group.not_selected_count == 1


def test_upset_capture_profiles_cli_options_map_to_backtest_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--output-path",
            "tmp/upset-capture-profiles.json",
            "--pass-types",
            "2x1,6x1",
            "--modes",
            "single",
            "--strategy",
            "upset_protection",
            "--optimizer-profile",
            "heuristic",
            "--unit-stake",
            "3",
            "--max-budget",
            "18",
            "--min-probability",
            "0.24",
            "--min-data-quality-score",
            "72",
            "--max-outcomes-per-fixture",
            "3",
            "--upset-threshold",
            "0.45",
            "--candidate-fixture-limit",
            "40",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "5",
            "--derive-market-context-signals",
            "--focus-competitions",
            "ESP_LA_LIGA,JPN_J1",
            "--min-group-sample-size",
            "4",
            "--no-profile-groups",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/upset-capture-profiles.json")
    assert options.backtest_options.pass_types == ("2x1", "6x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.strategy == "upset_protection"
    assert options.backtest_options.optimizer_profile == "heuristic"
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 18
    assert options.backtest_options.min_probability == 0.24
    assert options.backtest_options.min_data_quality_score == 72
    assert options.backtest_options.max_outcomes_per_fixture == 3
    assert options.backtest_options.upset_threshold == 0.45
    assert options.backtest_options.candidate_fixture_limit == 40
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 5
    assert options.backtest_options.derive_market_context_signals is True
    assert options.focus_competition_ids == ("ESP_LA_LIGA", "JPN_J1")
    assert options.min_group_sample_size == 4
    assert options.include_profile_groups is False


def _group(
    groups: list[HistoricalUpsetCaptureGroup],
    group_type: str,
    group_key: str,
) -> HistoricalUpsetCaptureGroup:
    for group in groups:
        if group.group_type == group_type and group.group_key == group_key:
            return group
    raise AssertionError(f"group not found: {group_type} {group_key}")


def _slice(
    *,
    slice_id: str = "upset_profile_slice",
    fixtures: list[HistoricalFixture],
) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name=slice_id,
            competition_id="UPSET_TEST",
            season="2024",
            result_source="deterministic_test_fixture",
            odds_source="deterministic_test_fixture",
            prediction_source="deterministic_test_fixture",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=fixtures,
    )


def _fragile_favorite_miss_fixture(fixture_id: str) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="UPSET_TEST",
        kickoff_time_utc=_dt(2024, 6, 30, 18),
        home_team_name="Favorite FC",
        away_team_name="Trap Town",
        actual_home_goals=1,
        actual_away_goals=1,
        prediction_time_utc=_dt(2024, 6, 29, 10),
        model_version="test-model-v1",
        feature_version="test-features-v1",
        calibration_version="test-calibration-v1",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=0.72,
                decimal_odds=1.35,
                market_probability=0.70,
                model_edge=0.02,
                data_quality_score=95.0,
                model_confidence_score=0.90,
                calibration_score=0.90,
                metadata_json={
                    "favorite_fragility_score": 0.55,
                    "is_market_favorite": True,
                },
            ),
            HistoricalMarketPrediction(
                outcome="draw",
                probability=0.24,
                decimal_odds=3.80,
                market_probability=0.26,
                model_edge=-0.02,
                upset_protection_score=0.75,
                data_quality_score=95.0,
                model_confidence_score=0.78,
                calibration_score=0.84,
                metadata_json={
                    "target_outcome": "draw",
                    "upset_score": 0.75,
                    "upset_direction": "draw_overlooked",
                },
            ),
            HistoricalMarketPrediction(
                outcome="away_win",
                probability=0.04,
                decimal_odds=9.00,
                market_probability=0.11,
                model_edge=-0.07,
            ),
        ],
    )


def _captured_draw_fixture() -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id="captured_draw",
        competition_id="UPSET_TEST",
        kickoff_time_utc=_dt(2024, 6, 30, 18),
        home_team_name="Favorite FC",
        away_team_name="Draw Town",
        actual_home_goals=1,
        actual_away_goals=1,
        prediction_time_utc=_dt(2024, 6, 29, 10),
        model_version="test-model-v1",
        feature_version="test-features-v1",
        calibration_version="test-calibration-v1",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=0.48,
                decimal_odds=1.95,
                market_probability=0.52,
                model_edge=-0.03,
                metadata_json={
                    "favorite_fragility_score": 0.70,
                    "is_market_favorite": True,
                },
            ),
            HistoricalMarketPrediction(
                outcome="draw",
                probability=0.28,
                decimal_odds=3.20,
                market_probability=0.24,
                model_edge=0.08,
                upset_protection_score=0.95,
                data_quality_score=95.0,
                model_confidence_score=0.90,
                calibration_score=0.92,
                metadata_json={
                    "target_outcome": "draw",
                    "upset_score": 0.95,
                    "upset_direction": "draw_overlooked",
                },
            ),
            HistoricalMarketPrediction(
                outcome="away_win",
                probability=0.12,
                decimal_odds=5.00,
                market_probability=0.20,
                model_edge=-0.08,
            ),
        ],
    )


def _safe_home_win_fixture(fixture_id: str) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="UPSET_TEST",
        kickoff_time_utc=_dt(2024, 6, 30, 17),
        home_team_name="Reliable FC",
        away_team_name="Away FC",
        actual_home_goals=2,
        actual_away_goals=0,
        prediction_time_utc=_dt(2024, 6, 29, 10),
        model_version="test-model-v1",
        feature_version="test-features-v1",
        calibration_version="test-calibration-v1",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=0.82,
                decimal_odds=1.42,
                market_probability=0.70,
                model_edge=0.12,
                data_quality_score=95.0,
                model_confidence_score=0.95,
                calibration_score=0.95,
                metadata_json={"is_market_favorite": True},
            ),
            HistoricalMarketPrediction(
                outcome="draw",
                probability=0.12,
                decimal_odds=4.50,
                market_probability=0.22,
                model_edge=-0.10,
            ),
            HistoricalMarketPrediction(
                outcome="away_win",
                probability=0.06,
                decimal_odds=7.50,
                market_probability=0.13,
                model_edge=-0.07,
            ),
        ],
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
