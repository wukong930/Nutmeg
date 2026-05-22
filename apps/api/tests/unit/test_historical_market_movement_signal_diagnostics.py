from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nutmeg.accuracy.historical_market_movement_signal_diagnostics import (
    HistoricalMarketMovementSignalDiagnosticOptions,
    HistoricalMarketMovementSignalGroup,
    _options_from_args,
    _parse_args,
    build_historical_market_movement_signal_diagnostic_report,
)
from nutmeg.domain.features import FeatureSnapshot
from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)


def test_market_movement_signal_diagnostics_groups_directional_reliability() -> None:
    report = build_historical_market_movement_signal_diagnostic_report(
        [_movement_slice()],
        options=HistoricalMarketMovementSignalDiagnosticOptions(
            min_group_sample_size=1,
            observation_sample_limit=0,
        ),
    )

    assert report.observation_count == 9
    assert report.strongest_observation_count == 3
    assert report.skipped_reason_counts == {}
    assert report.skipped_fixture_count == 0
    assert report.overall.closing_improved_rate == 7 / 9
    assert report.overall.brier_score_delta is not None
    assert report.summary_json["shadow_only"] is True

    shortened = _group(report.groups, "movement_direction:probability_shortened")
    assert shortened.sample_count == 3
    assert shortened.actual_count == 2
    assert shortened.actual_rate == 2 / 3
    assert shortened.closing_improved_count == 2

    drifted = _group(report.groups, "movement_direction:probability_drifted")
    assert drifted.sample_count == 6
    assert drifted.actual_count == 1
    assert drifted.closing_improved_count == 5

    strongest_shortened = _group(
        report.groups,
        "strongest_movement_direction:probability_shortened",
    )
    assert strongest_shortened.sample_count == 3
    assert strongest_shortened.actual_count == 2
    assert strongest_shortened.average_abs_probability_delta is not None
    assert strongest_shortened.average_abs_probability_delta > 0.07

    large_delta = _group(report.groups, "delta_band:0.06:")
    assert large_delta.sample_count == 2
    assert large_delta.actual_count == 2


def test_market_movement_signal_diagnostics_can_filter_small_movements() -> None:
    report = build_historical_market_movement_signal_diagnostic_report(
        [_movement_slice()],
        options=HistoricalMarketMovementSignalDiagnosticOptions(
            min_abs_probability_delta=0.06,
            observation_sample_limit=20,
        ),
    )

    assert report.observation_count == 2
    assert report.sampled_observations
    assert all(
        observation.abs_probability_delta >= 0.06
        for observation in report.sampled_observations
    )
    assert report.strongest_observation_count == 2
    assert report.skipped_reason_counts == {"missing_valid_odds_movement": 1}


def test_market_movement_signal_diagnostics_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/enriched_features/"
            "football_data_co_uk_market_features_multi/"
            "football_data_co_uk_epl_2024_2025_market_features_v1.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/"
            "football_data_co_uk_market_feature_multi_season_suite.json",
            "--output-path",
            "tmp/market-movement-signal-diagnostics.json",
            "--min-abs-probability-delta",
            "0.02",
            "--movement-direction-epsilon",
            "0.004",
            "--delta-bands",
            "0.00:0.02,0.02:0.05,0.05:",
            "--opening-probability-bands",
            "0.00:0.30,0.30:0.60,0.60:1.00",
            "--min-group-sample-size",
            "5",
            "--no-include-competition-groups",
            "--observation-sample-limit",
            "7",
        ]
    )

    options = _options_from_args(args)

    assert options.min_abs_probability_delta == 0.02
    assert options.movement_direction_epsilon == 0.004
    assert options.delta_bands == ("0.00:0.02", "0.02:0.05", "0.05:")
    assert options.opening_probability_bands == (
        "0.00:0.30",
        "0.30:0.60",
        "0.60:1.00",
    )
    assert options.min_group_sample_size == 5
    assert options.include_competition_groups is False
    assert options.observation_sample_limit == 7


def _group(
    groups: list[HistoricalMarketMovementSignalGroup],
    group_key: str,
) -> HistoricalMarketMovementSignalGroup:
    for group in groups:
        if group.group_key == group_key:
            return group
    raise AssertionError(f"group not found: {group_key}")


def _movement_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="market_movement_signal_unit_slice",
            name="Market movement signal unit slice",
            competition_id="TEST",
            season="2024-2025",
            result_source="unit-test",
            odds_source="unit-test",
            prediction_source="unit-test",
        ),
        as_of_time_utc=_dt(2024, 8, 1, 12),
        fixtures=[
            _fixture(
                "fixture_1",
                day_offset=1,
                actual_home_goals=2,
                actual_away_goals=0,
                opening=(0.50, 0.30, 0.20),
                closing=(0.60, 0.25, 0.15),
            ),
            _fixture(
                "fixture_2",
                day_offset=2,
                actual_home_goals=0,
                actual_away_goals=1,
                opening=(0.60, 0.20, 0.20),
                closing=(0.55, 0.15, 0.30),
            ),
            _fixture(
                "fixture_3",
                day_offset=3,
                actual_home_goals=1,
                actual_away_goals=1,
                opening=(0.50, 0.28, 0.22),
                closing=(0.52, 0.27, 0.21),
            ),
        ],
    )


def _fixture(
    fixture_id: str,
    *,
    day_offset: int,
    actual_home_goals: int,
    actual_away_goals: int,
    opening: tuple[float, float, float],
    closing: tuple[float, float, float],
) -> HistoricalFixture:
    kickoff = _dt(2024, 8, 1, 12) + timedelta(days=day_offset)
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=kickoff,
        home_team_name=f"{fixture_id} Home",
        away_team_name=f"{fixture_id} Away",
        actual_home_goals=actual_home_goals,
        actual_away_goals=actual_away_goals,
        prediction_time_utc=kickoff - timedelta(days=1),
        model_version="market-movement-signal-test",
        feature_version="market-movement-feature-test",
        calibration_version="uncalibrated",
        predictions=[
            HistoricalMarketPrediction(
                market_type="1x2",
                outcome=outcome,
                probability=probability,
                decimal_odds=1.0 / probability,
                market_probability=probability,
            )
            for outcome, probability in zip(
                ("home_win", "draw", "away_win"),
                opening,
                strict=True,
            )
        ],
        feature_snapshot=FeatureSnapshot(
            fixture_id=fixture_id,
            feature_time_utc=kickoff - timedelta(days=1),
            feature_version="market-movement-feature-test",
            data_quality_score=80.0,
            features_json={
                "prematch_context": {
                    "odds_movement": [
                        _movement(outcome, opening_probability, closing_probability)
                        for outcome, opening_probability, closing_probability in zip(
                            ("home_win", "draw", "away_win"),
                            opening,
                            closing,
                            strict=True,
                        )
                    ]
                }
            },
            source_snapshot_refs={"prematch": {"odds_movement": [fixture_id]}},
        ),
    )


def _movement(
    outcome: str,
    opening_probability: float,
    closing_probability: float,
) -> dict[str, object]:
    return {
        "market_type": "1x2",
        "outcome": outcome,
        "opening_prob": opening_probability,
        "current_prob": closing_probability,
        "probability_delta": closing_probability - opening_probability,
        "opening_decimal_odds": 1.0 / opening_probability,
        "current_decimal_odds": 1.0 / closing_probability,
        "points": [
            {"source_snapshot_ref": f"{outcome}:open"},
            {"source_snapshot_ref": f"{outcome}:close"},
        ],
    }


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
