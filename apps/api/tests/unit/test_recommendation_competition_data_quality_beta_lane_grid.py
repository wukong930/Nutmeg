from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nutmeg.recommendations import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    competition_data_quality_beta_lane_grid,
)
from nutmeg.recommendations.competition_data_quality_beta_lane_grid import (
    HistoricalCompetitionDataQualityBetaLaneGridOptions,
    _options_from_args,
    _parse_args,
    build_historical_competition_data_quality_beta_lane_grid_report,
)


def test_competition_data_quality_beta_lane_grid_uses_beta_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_log: list[
        tuple[
            float,
            dict[str, float],
            bool,
            tuple[str, ...],
            int | None,
            int | None,
            float | None,
            bool,
            float,
            float,
        ]
    ] = []

    def fake_backtest(
        historical_slice: HistoricalRecommendationSlice,
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
    ) -> HistoricalRecommendationBacktestResult:
        assert options is not None
        call_log.append(
            (
                options.min_data_quality_score,
                dict(options.min_data_quality_score_by_competition_id),
                options.data_quality_beta_lane_enabled,
                options.data_quality_beta_lane_season_ids,
                options.data_quality_beta_lane_min_competition_season_index,
                options.data_quality_beta_lane_max_competition_season_index,
                options.data_quality_beta_lane_max_decimal_odds,
                options.data_quality_beta_lane_probability_repair_enabled,
                options.data_quality_beta_lane_probability_repair_strength,
                options.data_quality_beta_lane_probability_repair_extra_uplift,
            )
        )
        if (
            options.data_quality_beta_lane_enabled
            and options.data_quality_beta_lane_max_decimal_odds == 2.30
        ):
            return _backtest_result(
                historical_slice.metadata.slice_id,
                final_hit_sample_size=2,
                final_hit_count=2,
                profit_loss=4.0,
            )
        return _backtest_result(
            historical_slice.metadata.slice_id,
            final_hit_sample_size=1,
            final_hit_count=1,
            profit_loss=2.0,
        )

    monkeypatch.setattr(
        competition_data_quality_beta_lane_grid,
        "run_historical_recommendation_backtest",
        fake_backtest,
    )

    report = build_historical_competition_data_quality_beta_lane_grid_report(
        [_slice()],
        options=HistoricalCompetitionDataQualityBetaLaneGridOptions(
            baseline_min_data_quality_score=80,
            beta_min_data_quality_score_values=(70.0,),
            competition_ids=("FRA_LIGUE_2",),
            season_groups=(("2022_2023",),),
            min_competition_season_index_values=(1,),
            max_competition_season_index_values=(1,),
            min_probability_values=(0.50,),
            max_decimal_odds_values=(2.30,),
            min_model_edge_values=(0.0,),
            min_model_confidence_score_values=(0.66,),
            min_calibration_score_values=(0.70,),
            min_odds_stability_score_values=(0.90,),
            max_volatility_penalty_values=(0.08,),
            probability_repair_strength_values=(0.50,),
            probability_repair_max_delta_values=(0.04,),
            probability_repair_extra_uplift_values=(0.01,),
            max_final_hit_harm_count_vs_baseline=0,
            max_profit_loss_harm_count_vs_baseline=0,
        ),
    )

    assert call_log == [
        (80.0, {}, False, (), None, None, None, False, 0.0, 0.0),
        (
            80.0,
            {"FRA_LIGUE_2": 70.0},
            True,
            ("2022_2023",),
            1,
            1,
            2.30,
            True,
            0.50,
            0.01,
        ),
    ]
    assert report.candidate_count == 1
    candidate = report.candidates[0]
    assert candidate.status == "accepted"
    assert candidate.season_ids == ("2022_2023",)
    assert candidate.min_competition_season_index == 1
    assert candidate.max_competition_season_index == 1
    assert candidate.beta_lane_prediction_count == 1
    assert candidate.beta_lane_fixture_count == 1
    assert candidate.probability_repair_strength == 0.50
    assert candidate.probability_repair_max_delta == 0.04
    assert candidate.probability_repair_extra_uplift == 0.01
    assert candidate.final_hit_sample_size_delta == 1
    assert candidate.objective_improvement_metric_codes == [
        "final_hit_count_delta",
    ]


def test_competition_data_quality_beta_lane_grid_cli_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_knockout_suite.json",
            "--output-path",
            "tmp/competition-data-quality-beta-lane-grid.json",
            "--pass-types",
            "2x1,3x1",
            "--modes",
            "single",
            "--strategy",
            "value_first",
            "--unit-stake",
            "3",
            "--max-budget",
            "12",
            "--candidate-fixture-limit",
            "48",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "4",
            "--derive-market-context-signals",
            "--optimizer-profile",
            "solver",
            "--baseline-min-data-quality-score",
            "80",
            "--beta-min-data-quality-score-values",
            "70",
            "--competitions",
            "FRA_LIGUE_2,ENG_CHAMPIONSHIP",
            "--season-group",
            "2021_2022,2022_2023",
            "--season-group",
            "2023_2024",
            "--min-competition-season-index-values",
            "none,2",
            "--max-competition-season-index-values",
            "none,4",
            "--beta-min-probability-values",
            "0.45,0.50",
            "--beta-max-decimal-odds-values",
            "2.30",
            "--beta-min-model-edge-values=-0.02,0.0",
            "--beta-min-model-confidence-score-values",
            "0.66",
            "--beta-min-calibration-score-values",
            "0.70",
            "--beta-min-odds-stability-score-values",
            "0.90",
            "--beta-max-volatility-penalty-values",
            "0.08",
            "--probability-repair-strength-values",
            "0.25,0.50",
            "--probability-repair-max-delta-values",
            "0.03",
            "--probability-repair-min-market-probability-delta-values",
            "0.01",
            "--probability-repair-extra-uplift-values",
            "0.02",
            "--probability-repair-data-quality-gap-weight-values",
            "0.01",
            "--probability-repair-odds-stability-weight-values",
            "0.03",
            "--probability-repair-max-probability-values",
            "0.92",
            "--min-beta-lane-prediction-count",
            "2",
            "--max-final-hit-harm-count-vs-baseline",
            "0",
            "--max-profit-loss-harm-count-vs-baseline",
            "1",
            "--no-require-objective-improvement",
        ]
    )
    options = _options_from_args(args)

    assert args.output_path == Path("tmp/competition-data-quality-beta-lane-grid.json")
    assert options.backtest_options.pass_types == ("2x1", "3x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.strategy == "value_first"
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 12
    assert options.backtest_options.candidate_fixture_limit == 48
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 4
    assert options.backtest_options.derive_market_context_signals is True
    assert options.optimizer_profile == "solver"
    assert options.baseline_min_data_quality_score == 80
    assert options.beta_min_data_quality_score_values == (70.0,)
    assert options.competition_ids == ("FRA_LIGUE_2", "ENG_CHAMPIONSHIP")
    assert options.season_groups == (("2021_2022", "2022_2023"), ("2023_2024",))
    assert options.min_competition_season_index_values == (None, 2)
    assert options.max_competition_season_index_values == (None, 4)
    assert options.min_probability_values == (0.45, 0.50)
    assert options.max_decimal_odds_values == (2.30,)
    assert options.min_model_edge_values == (-0.02, 0.0)
    assert options.min_model_confidence_score_values == (0.66,)
    assert options.min_calibration_score_values == (0.70,)
    assert options.min_odds_stability_score_values == (0.90,)
    assert options.max_volatility_penalty_values == (0.08,)
    assert options.probability_repair_strength_values == (0.25, 0.50)
    assert options.probability_repair_max_delta_values == (0.03,)
    assert options.probability_repair_min_market_probability_delta_values == (0.01,)
    assert options.probability_repair_extra_uplift_values == (0.02,)
    assert options.probability_repair_data_quality_gap_weight_values == (0.01,)
    assert options.probability_repair_odds_stability_weight_values == (0.03,)
    assert options.probability_repair_max_probability_values == (0.92,)
    assert options.min_beta_lane_prediction_count == 2
    assert options.max_final_hit_harm_count_vs_baseline == 0
    assert options.max_profit_loss_harm_count_vs_baseline == 1
    assert options.require_objective_improvement is False


def _backtest_result(
    slice_id: str,
    *,
    final_hit_sample_size: int,
    final_hit_count: int,
    profit_loss: float,
) -> HistoricalRecommendationBacktestResult:
    return HistoricalRecommendationBacktestResult(
        backtest_key=f"fake_{slice_id}_{final_hit_sample_size}_{final_hit_count}",
        slice_id=slice_id,
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixture_count=2,
        candidate_count=4,
        scenario_count=1,
        completed_count=1,
        failed_count=0,
        final_answer=None,
        scenarios=[],
        final_hit_sample_size=final_hit_sample_size,
        final_hit_count=final_hit_count,
        final_hit_rate=final_hit_count / final_hit_sample_size,
        total_stake=float(final_hit_sample_size * 2),
        actual_return=float(final_hit_sample_size * 2) + profit_loss,
        profit_loss=profit_loss,
        roi=profit_loss / float(final_hit_sample_size * 2),
        mean_calibration_error=0.20,
        brier_score=0.20,
        log_loss=0.50,
        upset_opportunity_count=1,
        upset_capture_count=0,
        upset_capture_rate=0.0,
    )


def _slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="competition_data_quality_beta_lane_grid_unit_slice",
            name="Competition data quality beta lane grid unit slice",
            competition_id="TEST",
            season="2022_2023",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture(
                "stable_candidate",
                competition_id="FRA_LIGUE_2",
                data_quality_score=72,
                probability=0.56,
                decimal_odds=2.10,
                market_probability=0.49,
                odds_stability_score=0.96,
                volatility_penalty=0.03,
            ),
            _fixture(
                "volatile_candidate",
                competition_id="FRA_LIGUE_2",
                data_quality_score=72,
                probability=0.57,
                decimal_odds=2.05,
                market_probability=0.49,
                odds_stability_score=0.82,
                volatility_penalty=0.12,
            ),
        ],
    )


def _fixture(
    fixture_id: str,
    *,
    competition_id: str,
    data_quality_score: float,
    probability: float,
    decimal_odds: float,
    market_probability: float,
    odds_stability_score: float,
    volatility_penalty: float,
) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id=competition_id,
        kickoff_time_utc=_dt(2024, 6, 30, 18),
        home_team_name=f"{fixture_id} Home",
        away_team_name=f"{fixture_id} Away",
        actual_home_goals=1,
        actual_away_goals=0,
        prediction_time_utc=_dt(2024, 6, 29, 10),
        model_version="poisson-v3.1-competition-quality-beta-lane-test",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=probability,
                decimal_odds=decimal_odds,
                market_probability=market_probability,
                model_edge=None,
                data_quality_score=data_quality_score,
                model_confidence_score=0.66,
                calibration_score=0.70,
                odds_stability_score=odds_stability_score,
                volatility_penalty=volatility_penalty,
            )
        ],
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
