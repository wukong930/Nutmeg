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
    marginal_loss_driver_data_quality_threshold_grid,
)
from nutmeg.recommendations.marginal_loss_driver_data_quality_threshold_grid import (
    HistoricalMarginalLossDriverDataQualityThresholdGridOptions,
    _options_from_args,
    _parse_args,
    build_historical_marginal_loss_driver_data_quality_threshold_grid_report,
)


def test_loss_driver_data_quality_threshold_grid_compares_fixed_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_log: list[tuple[float, bool]] = []

    def fake_backtest(
        historical_slice: HistoricalRecommendationSlice,
        *,
        options: HistoricalRecommendationBacktestOptions | None = None,
    ) -> HistoricalRecommendationBacktestResult:
        assert options is not None
        call_log.append(
            (
                options.min_data_quality_score,
                options.marginal_loss_driver_candidate_soft_penalty,
            )
        )
        is_candidate = options.marginal_loss_driver_candidate_soft_penalty
        if is_candidate and options.min_data_quality_score <= 50.0:
            return _backtest_result(
                historical_slice.metadata.slice_id,
                final_hit_sample_size=2,
                final_hit_count=2,
                profit_loss=4.0,
                soft_summary={
                    "marginal_loss_driver_candidate_soft_penalty_candidate_count": 3,
                    (
                        "marginal_loss_driver_candidate_soft_penalty_"
                        "fixture_exposure_rankable_candidate_count"
                    ): 3,
                    (
                        "marginal_loss_driver_candidate_soft_penalty_"
                        "candidate_pool_candidate_count"
                    ): 2,
                    (
                        "marginal_loss_driver_candidate_soft_penalty_"
                        "candidate_pool_fixture_count"
                    ): 2,
                    (
                        "marginal_loss_driver_candidate_soft_penalty_"
                        "completed_scenario_selected_candidate_count"
                    ): 1,
                    (
                        "marginal_loss_driver_candidate_soft_penalty_"
                        "completed_scenario_selected_option_count"
                    ): 1,
                },
            )
        if is_candidate:
            return _backtest_result(
                historical_slice.metadata.slice_id,
                final_hit_sample_size=1,
                final_hit_count=1,
                profit_loss=2.0,
                soft_summary={
                    "marginal_loss_driver_candidate_soft_penalty_candidate_count": 3,
                    (
                        "marginal_loss_driver_candidate_soft_penalty_"
                        "fixture_exposure_excluded_candidate_count"
                    ): 3,
                    (
                        "marginal_loss_driver_candidate_soft_penalty_"
                        "fixture_exposure_exclusion_reason_counts"
                    ): {"data_quality_too_low": 3},
                },
            )
        return _backtest_result(
            historical_slice.metadata.slice_id,
            final_hit_sample_size=1,
            final_hit_count=1,
            profit_loss=2.0,
            soft_summary={},
        )

    monkeypatch.setattr(
        marginal_loss_driver_data_quality_threshold_grid,
        "run_historical_recommendation_backtest",
        fake_backtest,
    )

    report = build_historical_marginal_loss_driver_data_quality_threshold_grid_report(
        [_slice()],
        options=HistoricalMarginalLossDriverDataQualityThresholdGridOptions(
            baseline_min_data_quality_score=80.0,
            candidate_min_data_quality_score_values=(80.0, 50.0),
            min_final_hit_rate_delta=0.0,
            min_roi_delta=0.0,
            min_profit_loss_delta=0.0,
            max_final_hit_harm_count_vs_baseline=0,
            max_profit_loss_harm_count_vs_baseline=0,
        ),
    )

    assert call_log == [(80.0, False), (80.0, True), (50.0, True)]
    assert report.candidate_count == 2
    threshold_80 = report.candidates[0]
    threshold_50 = report.candidates[1]
    assert threshold_80.status == "rejected"
    assert threshold_80.target_excluded_candidate_count == 3
    assert threshold_80.target_exclusion_reason_counts == {"data_quality_too_low": 3}
    assert "loss_driver_data_quality_threshold:objective_improvement_missing" in (
        threshold_80.reason_codes
    )
    assert threshold_50.status == "accepted"
    assert threshold_50.target_candidate_count == 3
    assert threshold_50.target_rankable_candidate_count == 3
    assert threshold_50.target_candidate_pool_count == 2
    assert threshold_50.target_completed_scenario_selected_candidate_count == 1
    assert threshold_50.final_hit_sample_size_delta == 1
    assert threshold_50.candidate_final_hit_count == 2
    assert threshold_50.objective_improvement_metric_codes == [
        "final_hit_sample_size_delta",
        "final_hit_count_delta",
    ]


def test_loss_driver_data_quality_threshold_grid_cli_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_knockout_suite.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_upset_stress_suite.json",
            "--output-path",
            "tmp/loss-driver-data-quality-threshold-grid.json",
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
            "--candidate-min-data-quality-score-values",
            "80,60,50",
            "--competitions",
            "FRA_LIGUE_2,JPN_J1",
            "--probability-min",
            "0.45",
            "--probability-max",
            "0.65",
            "--max-decimal-odds",
            "2.30",
            "--max-model-edge",
            "-0.02",
            "--max-calibration-score",
            "0.85",
            "--max-model-confidence-score",
            "0.87",
            "--max-odds-stability-score",
            "0.74",
            "--min-target-candidate-count",
            "2",
            "--min-target-final-answer-count",
            "1",
            "--min-final-hit-sample-size-delta",
            "1",
            "--max-final-hit-harm-count-vs-baseline",
            "0",
            "--max-profit-loss-harm-count-vs-baseline",
            "1",
            "--no-require-objective-improvement",
        ]
    )
    options = _options_from_args(args)

    assert args.output_path == Path("tmp/loss-driver-data-quality-threshold-grid.json")
    assert args.suite_manifest == [
        Path("configs/recommendations/historical_suites/euro_2024_knockout_suite.json"),
        Path("configs/recommendations/historical_suites/euro_2024_upset_stress_suite.json"),
    ]
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
    assert options.candidate_min_data_quality_score_values == (80.0, 60.0, 50.0)
    assert options.competition_ids == ("FRA_LIGUE_2", "JPN_J1")
    assert options.probability_min == 0.45
    assert options.probability_max == 0.65
    assert options.max_decimal_odds == 2.30
    assert options.max_model_edge == -0.02
    assert options.max_calibration_score == 0.85
    assert options.max_model_confidence_score == 0.87
    assert options.max_odds_stability_score == 0.74
    assert options.min_target_candidate_count == 2
    assert options.min_target_final_answer_count == 1
    assert options.min_final_hit_sample_size_delta == 1
    assert options.max_final_hit_harm_count_vs_baseline == 0
    assert options.max_profit_loss_harm_count_vs_baseline == 1
    assert options.require_objective_improvement is False


def _backtest_result(
    slice_id: str,
    *,
    final_hit_sample_size: int,
    final_hit_count: int,
    profit_loss: float,
    soft_summary: dict[str, object],
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
        summary_json=soft_summary,
    )


def _slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="loss_driver_data_quality_threshold_grid_unit_slice",
            name="Loss-driver data quality threshold grid unit slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture("candidate_a", data_quality_score=60.0),
            _fixture("candidate_b", data_quality_score=90.0),
        ],
    )


def _fixture(fixture_id: str, *, data_quality_score: float) -> HistoricalFixture:
    return HistoricalFixture(
        fixture_id=fixture_id,
        competition_id="TEST",
        kickoff_time_utc=_dt(2024, 6, 30, 18),
        home_team_name=f"{fixture_id} Home",
        away_team_name=f"{fixture_id} Away",
        actual_home_goals=1,
        actual_away_goals=0,
        prediction_time_utc=_dt(2024, 6, 29, 10),
        model_version="poisson-v3.1-data-quality-threshold-test",
        predictions=[
            HistoricalMarketPrediction(
                outcome="home_win",
                probability=0.55,
                decimal_odds=2.10,
                market_probability=1.0 / 2.10,
                model_edge=-0.03,
                data_quality_score=data_quality_score,
                model_confidence_score=0.70,
                calibration_score=0.70,
                odds_stability_score=0.70,
            )
        ],
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
