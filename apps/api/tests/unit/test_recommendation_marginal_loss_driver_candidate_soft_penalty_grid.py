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
    marginal_loss_driver_candidate_soft_penalty_grid,
)
from nutmeg.recommendations.marginal_loss_driver_candidate_soft_penalty_grid import (
    HistoricalMarginalLossDriverCandidateSoftPenaltyGridOptions,
    _options_from_args,
    _parse_args,
    build_historical_marginal_loss_driver_candidate_soft_penalty_grid_report,
)


def test_loss_driver_candidate_soft_penalty_grid_counts_penalized_candidates() -> None:
    report = build_historical_marginal_loss_driver_candidate_soft_penalty_grid_report(
        [_slice()],
        options=HistoricalMarginalLossDriverCandidateSoftPenaltyGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
                optimizer_profile="heuristic",
            ),
            optimizer_profile="heuristic",
            competition_ids=("TEST",),
            probability_min=0.65,
            probability_max=0.80,
            max_decimal_odds=1.50,
            max_model_edge=-0.02,
            strength_values=(0.0, 1.0),
            min_penalized_candidate_count=2,
        ),
    )

    assert report.candidate_count == 2
    assert [candidate.penalized_candidate_count for candidate in report.candidates] == [
        2,
        2,
    ]
    assert [
        candidate.penalized_candidate_pool_count for candidate in report.candidates
    ] == [
        2,
        2,
    ]
    assert [
        candidate.penalized_completed_scenario_selected_candidate_count
        for candidate in report.candidates
    ] == [
        0,
        0,
    ]
    assert report.candidates[0].status == "rejected"
    assert "loss_driver_soft_penalty:objective_improvement_missing" in (
        report.candidates[0].reason_codes
    )
    assert report.best_candidate is not None


def test_loss_driver_candidate_soft_penalty_grid_rejects_inactive_competition() -> None:
    report = build_historical_marginal_loss_driver_candidate_soft_penalty_grid_report(
        [_slice()],
        options=HistoricalMarginalLossDriverCandidateSoftPenaltyGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
                optimizer_profile="heuristic",
            ),
            optimizer_profile="heuristic",
            competition_ids=("OTHER",),
            strength_values=(1.0,),
        ),
    )

    assert report.accepted_count == 0
    assert report.candidates[0].penalized_candidate_count == 0
    assert "loss_driver_soft_penalty:penalized_candidate_count_too_low" in (
        report.candidates[0].reason_codes
    )


def test_loss_driver_candidate_soft_penalty_grid_reports_fixture_exposure_dropoff() -> None:
    report = build_historical_marginal_loss_driver_candidate_soft_penalty_grid_report(
        [_slice()],
        options=HistoricalMarginalLossDriverCandidateSoftPenaltyGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
                optimizer_profile="heuristic",
                candidate_fixture_limit=2,
                max_candidates_per_fixture=1,
                scenario_candidate_fixture_buffer=0,
            ),
            optimizer_profile="heuristic",
            competition_ids=("TEST",),
            probability_min=0.65,
            probability_max=0.80,
            max_decimal_odds=1.50,
            max_model_edge=-0.02,
            strength_values=(0.0,),
            min_penalized_candidate_count=2,
            require_objective_improvement=False,
        ),
    )

    candidate = report.candidates[0]
    assert candidate.penalized_candidate_count == 2
    assert candidate.penalized_fixture_exposure_rankable_candidate_count == 2
    assert candidate.penalized_fixture_exposure_rankable_fixture_count == 2
    assert candidate.penalized_fixture_exposure_within_limit_count == 0
    assert candidate.penalized_candidate_pool_count == 0


def test_loss_driver_candidate_soft_penalty_grid_rejects_slice_level_harm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_backtest(
        historical_slice: HistoricalRecommendationSlice,
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
    ) -> HistoricalRecommendationBacktestResult:
        is_candidate = bool(
            options is not None
            and options.marginal_loss_driver_candidate_soft_penalty
        )
        if historical_slice.metadata.slice_id == "harm_slice":
            return _backtest_result(
                historical_slice.metadata.slice_id,
                final_hit_count=0 if is_candidate else 1,
                profit_loss=-2.0 if is_candidate else 5.0,
                soft_penalty_count=3 if is_candidate else 0,
            )
        return _backtest_result(
            historical_slice.metadata.slice_id,
            final_hit_count=2 if is_candidate else 0,
            profit_loss=12.0 if is_candidate else -4.0,
            soft_penalty_count=4 if is_candidate else 0,
        )

    monkeypatch.setattr(
        marginal_loss_driver_candidate_soft_penalty_grid,
        "run_historical_recommendation_backtest",
        fake_backtest,
    )

    report = build_historical_marginal_loss_driver_candidate_soft_penalty_grid_report(
        [_slice_with_id("harm_slice"), _slice_with_id("gain_slice")],
        options=HistoricalMarginalLossDriverCandidateSoftPenaltyGridOptions(
            strength_values=(0.10,),
            max_final_hit_harm_count_vs_baseline=0,
            max_profit_loss_harm_count_vs_baseline=0,
        ),
    )

    candidate = report.candidates[0]
    assert candidate.status == "rejected"
    assert candidate.penalized_candidate_count == 7
    assert candidate.penalized_final_answer_count == 0
    assert candidate.penalized_final_answer_leg_count == 0
    assert candidate.candidate_final_hit_count > candidate.baseline_final_hit_count
    assert candidate.final_hit_harm_count_vs_baseline == 1
    assert candidate.profit_loss_harm_count_vs_baseline == 1
    assert "loss_driver_soft_penalty:final_hit_harm_count_above_threshold" in (
        candidate.reason_codes
    )
    assert "loss_driver_soft_penalty:profit_loss_harm_count_above_threshold" in (
        candidate.reason_codes
    )


def test_loss_driver_candidate_soft_penalty_grid_cli_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_knockout_suite.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_upset_stress_suite.json",
            "--output-path",
            "tmp/loss-driver-soft-penalty-grid.json",
            "--pass-types",
            "2x1,3x1",
            "--modes",
            "single",
            "--unit-stake",
            "3",
            "--max-budget",
            "12",
            "--min-data-quality-score",
            "70",
            "--candidate-fixture-limit",
            "48",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "4",
            "--derive-market-context-signals",
            "--optimizer-profile",
            "solver",
            "--competitions",
            "JPN_J1,ESP_LA_LIGA",
            "--probability-min",
            "0.60",
            "--probability-max",
            "0.82",
            "--max-decimal-odds",
            "1.55",
            "--max-model-edge",
            "-0.01",
            "--max-calibration-score",
            "0.85",
            "--max-model-confidence-score",
            "0.87",
            "--max-odds-stability-score",
            "0.74",
            "--strength-values",
            "0.05,0.2",
            "--min-penalized-candidate-count",
            "2",
            "--max-final-hit-harm-count-vs-baseline",
            "0",
            "--max-profit-loss-harm-count-vs-baseline",
            "1",
            "--no-require-objective-improvement",
        ]
    )
    options = _options_from_args(args)

    assert args.output_path == Path("tmp/loss-driver-soft-penalty-grid.json")
    assert args.suite_manifest == [
        Path("configs/recommendations/historical_suites/euro_2024_knockout_suite.json"),
        Path("configs/recommendations/historical_suites/euro_2024_upset_stress_suite.json"),
    ]
    assert options.backtest_options.pass_types == ("2x1", "3x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 12
    assert options.backtest_options.min_data_quality_score == 70
    assert options.backtest_options.candidate_fixture_limit == 48
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 4
    assert options.backtest_options.derive_market_context_signals is True
    assert options.optimizer_profile == "solver"
    assert options.competition_ids == ("JPN_J1", "ESP_LA_LIGA")
    assert options.probability_min == 0.60
    assert options.probability_max == 0.82
    assert options.max_decimal_odds == 1.55
    assert options.max_model_edge == -0.01
    assert options.max_calibration_score == 0.85
    assert options.max_model_confidence_score == 0.87
    assert options.max_odds_stability_score == 0.74
    assert options.strength_values == (0.05, 0.2)
    assert options.min_penalized_candidate_count == 2
    assert options.max_final_hit_harm_count_vs_baseline == 0
    assert options.max_profit_loss_harm_count_vs_baseline == 1
    assert options.require_objective_improvement is False


def _slice_with_id(slice_id: str) -> HistoricalRecommendationSlice:
    source = _slice()
    return source.model_copy(
        update={
            "metadata": source.metadata.model_copy(update={"slice_id": slice_id}),
        },
    )


def _backtest_result(
    slice_id: str,
    *,
    final_hit_count: int,
    profit_loss: float,
    soft_penalty_count: int,
) -> HistoricalRecommendationBacktestResult:
    return HistoricalRecommendationBacktestResult(
        backtest_key=f"fake_{slice_id}_{final_hit_count}_{profit_loss}",
        slice_id=slice_id,
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixture_count=2,
        candidate_count=4,
        scenario_count=1,
        completed_count=1,
        failed_count=0,
        final_answer=None,
        scenarios=[],
        final_hit_sample_size=2,
        final_hit_count=final_hit_count,
        final_hit_rate=final_hit_count / 2,
        total_stake=4.0,
        actual_return=4.0 + profit_loss if profit_loss >= -4.0 else 0.0,
        profit_loss=profit_loss,
        roi=profit_loss / 4.0,
        mean_calibration_error=0.20,
        brier_score=0.20,
        log_loss=0.50,
        upset_opportunity_count=1,
        upset_capture_count=0,
        upset_capture_rate=0.0,
        summary_json={
            "marginal_loss_driver_candidate_soft_penalty_candidate_count": (
                soft_penalty_count
            ),
        },
    )


def _slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="loss_driver_soft_penalty_grid_unit_slice",
            name="Loss-driver soft penalty grid unit slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture(
                "bad_profile_a",
                actual_home_goals=1,
                actual_away_goals=1,
                probability=0.79,
                decimal_odds=1.30,
                model_edge=-0.04,
            ),
            _fixture(
                "bad_profile_b",
                actual_home_goals=0,
                actual_away_goals=1,
                probability=0.78,
                decimal_odds=1.31,
                model_edge=-0.04,
            ),
            _fixture(
                "good_value_a",
                actual_home_goals=2,
                actual_away_goals=0,
                probability=0.66,
                decimal_odds=1.82,
                model_edge=0.11,
            ),
            _fixture(
                "good_value_b",
                actual_home_goals=3,
                actual_away_goals=1,
                probability=0.65,
                decimal_odds=1.86,
                model_edge=0.11,
            ),
        ],
    )


def _fixture(
    fixture_id: str,
    *,
    actual_home_goals: int,
    actual_away_goals: int,
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
        model_version="poisson-v3.1-loss-driver-soft-penalty-test",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
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
