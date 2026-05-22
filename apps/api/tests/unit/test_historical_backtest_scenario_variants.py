from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    run_historical_recommendation_backtest,
)


def test_historical_backtest_generates_shadow_scenario_variants() -> None:
    result = run_historical_recommendation_backtest(
        _variant_slice(),
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("1x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
            final_answer_scenario_variant_count=3,
        ),
    )

    assert result.scenario_count == 3
    assert result.completed_count == 3
    assert result.summary_json["final_answer_scenario_variant_count"] == 3
    assert result.summary_json["completed_scenario_variant_count"] == 2
    assert [item.scenario.scenario_key for item in result.scenarios] == [
        "1x1:single",
        "1x1:single#variant1",
        "1x1:single#variant2",
    ]
    assert len({item.option.option_key for item in result.scenarios if item.option}) == 3
    assert len({item.selected_fixture_ids[0] for item in result.scenarios}) == 3
    assert result.scenarios[1].selection_diagnostics_json["scenario_variant"] is True
    assert result.scenarios[1].selection_diagnostics_json["base_scenario_key"] == "1x1:single"
    assert result.scenarios[1].option is not None
    assert "historical_backtest_shadow_variant" in result.scenarios[1].option.reason_codes


def _variant_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="scenario_variant_slice",
            name="Scenario variant slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 8, 1, 10),
        fixtures=[
            _fixture("fixture_a", probability=0.76, decimal_odds=1.45),
            _fixture("fixture_b", probability=0.72, decimal_odds=1.50),
            _fixture("fixture_c", probability=0.68, decimal_odds=1.60),
            _fixture("fixture_d", probability=0.64, decimal_odds=1.70),
        ],
    )


def _fixture(
    fixture_id: str,
    *,
    probability: float,
    decimal_odds: float,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=_dt(2024, 8, 2, 18),
        home_team_name=f"{fixture_id} Home",
        away_team_name=f"{fixture_id} Away",
        actual_home_goals=1,
        actual_away_goals=0,
        prediction_time_utc=_dt(2024, 8, 1, 9),
        model_version="poisson-v3.1-scenario-variant-test",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=probability,
                decimal_odds=decimal_odds,
                market_probability=1.0 / decimal_odds,
                model_edge=probability - (1.0 / decimal_odds),
                data_quality_score=90,
                model_confidence_score=0.86,
                calibration_score=0.84,
                odds_stability_score=0.80,
            )
        ],
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
