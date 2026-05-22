from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
)
from nutmeg.recommendations.quality_signal_diagnostics import (
    HistoricalQualitySignalDiagnosticOptions,
    HistoricalQualitySignalGroup,
    _options_from_args,
    _parse_args,
    build_historical_quality_signal_diagnostic_report,
)


def test_quality_signal_diagnostics_groups_final_answer_selected_legs() -> None:
    report = build_historical_quality_signal_diagnostic_report(
        [_quality_signal_slice()],
        options=HistoricalQualitySignalDiagnosticOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                optimizer_profile="heuristic",
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
            ),
            component_names=("probability", "model_edge"),
        ),
    )

    assert report.final_answer_count == 1
    assert report.selected_leg_count == 2
    assert report.missed_leg_count == 1
    assert report.leg_hit_rate == 0.5
    assert report.roi == -1.0

    reason_group = _group(report.groups, "reason_code:accuracy_first_probability_component")
    assert reason_group.selected_leg_count == 2
    assert reason_group.leg_hit_count == 1
    assert reason_group.final_answer_count == 1
    assert reason_group.roi == -1.0

    probability_group = _group(report.groups, "component_score_band:probability:high")
    assert probability_group.selected_leg_count == 2
    assert probability_group.average_component_value == 0.75

    competition_odds_group = _group(
        report.groups,
        "competition_odds_band:TEST:medium_short_price",
    )
    assert competition_odds_group.selected_leg_count == 2
    assert competition_odds_group.leg_hit_count == 1
    assert competition_odds_group.final_answer_count == 1

    assert report.top_negative_signal_groups
    assert report.summary_json["top_negative_signal_group_keys"]
    assert report.summary_json["include_competition_bands"] is True


def test_quality_signal_diagnostics_can_filter_competitions() -> None:
    report = build_historical_quality_signal_diagnostic_report(
        [_quality_signal_slice()],
        options=HistoricalQualitySignalDiagnosticOptions(
            focus_competition_ids=("OTHER",),
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
            ),
        ),
    )

    assert report.final_answer_count == 0
    assert report.groups == []
    assert report.summary_json["focus_competition_ids"] == ["OTHER"]


def test_quality_signal_diagnostics_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_knockout_suite.json",
            "--output-path",
            "tmp/quality-signals.json",
            "--pass-types",
            "2x1,3x1",
            "--modes",
            "single",
            "--strategy",
            "value_first",
            "--optimizer-profile",
            "heuristic",
            "--unit-stake",
            "3",
            "--max-budget",
            "12",
            "--min-probability",
            "0.2",
            "--min-data-quality-score",
            "70",
            "--max-outcomes-per-fixture",
            "3",
            "--upset-threshold",
            "0.4",
            "--candidate-fixture-limit",
            "48",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "6",
            "--derive-market-context-signals",
            "--focus-competitions",
            "ESP_LA_LIGA,JPN_J1",
            "--component-names",
            "probability,calibration_risk",
            "--min-group-selected-leg-count",
            "2",
            "--no-include-reason-codes",
            "--no-include-basic-bands",
            "--no-include-competition-bands",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/quality-signals.json")
    assert options.backtest_options.pass_types == ("2x1", "3x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.strategy == "value_first"
    assert options.backtest_options.optimizer_profile == "heuristic"
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 12
    assert options.backtest_options.min_probability == 0.2
    assert options.backtest_options.min_data_quality_score == 70
    assert options.backtest_options.max_outcomes_per_fixture == 3
    assert options.backtest_options.upset_threshold == 0.4
    assert options.backtest_options.candidate_fixture_limit == 48
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 6
    assert options.derive_market_context_signals is True
    assert options.focus_competition_ids == ("ESP_LA_LIGA", "JPN_J1")
    assert options.component_names == ("probability", "calibration_risk")
    assert options.min_group_selected_leg_count == 2
    assert options.include_reason_codes is False
    assert options.include_basic_bands is False
    assert options.include_competition_bands is False


def _group(
    groups: list[HistoricalQualitySignalGroup],
    group_key: str,
) -> HistoricalQualitySignalGroup:
    for group in groups:
        if group.group_key == group_key:
            return group
    raise AssertionError(f"group not found: {group_key}")


def _quality_signal_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="quality_signal_unit_slice",
            name="Quality signal unit slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture(
                "hit_leg",
                actual_home_goals=2,
                actual_away_goals=0,
                outcome="home_win",
                probability=0.76,
                decimal_odds=1.55,
                model_edge=0.11,
            ),
            _fixture(
                "miss_leg",
                actual_home_goals=1,
                actual_away_goals=1,
                outcome="away_win",
                probability=0.74,
                decimal_odds=1.62,
                model_edge=0.09,
            ),
        ],
    )


def _fixture(
    fixture_id: str,
    *,
    actual_home_goals: int,
    actual_away_goals: int,
    outcome: str,
    probability: float,
    decimal_odds: float,
    model_edge: float,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=_dt(2024, 6, 30, 18),
        home_team_name=f"{fixture_id} Home",
        away_team_name=f"{fixture_id} Away",
        actual_home_goals=actual_home_goals,
        actual_away_goals=actual_away_goals,
        prediction_time_utc=_dt(2024, 6, 29, 10),
        model_version="poisson-v3.1-quality-signal-test",
        predictions=[
            HistoricalMarketPrediction(
                outcome=outcome,
                probability=probability,
                decimal_odds=decimal_odds,
                market_probability=1.0 / decimal_odds,
                model_edge=model_edge,
                data_quality_score=90.0,
                model_confidence_score=0.88,
                calibration_score=0.86,
                odds_stability_score=0.75,
            )
        ],
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
