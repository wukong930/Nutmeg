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
from nutmeg.recommendations.short_price_threshold_grid import (
    HistoricalShortPriceThresholdGridOptions,
    _append_maximum_reason,
    _append_minimum_reason,
    _options_from_args,
    _parse_args,
    build_historical_short_price_threshold_grid_report,
)


def test_threshold_grid_accepts_soft_penalty_candidate_when_metrics_improve() -> None:
    report = build_historical_short_price_threshold_grid_report(
        [_threshold_slice()],
        options=HistoricalShortPriceThresholdGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
            ),
            competition_groups=(("TEST",),),
            max_decimal_odds_values=(1.35,),
            min_probability_values=(0.70,),
            max_model_edge_values=(0.0,),
            strength_values=(1.0,),
            baseline_optimizer_profile="heuristic",
            candidate_optimizer_profile="heuristic",
        ),
    )

    assert report.accepted_count == 1
    assert report.rejected_count == 0
    candidate = report.accepted_candidates[0]
    assert candidate.status == "accepted"
    assert candidate.penalized_candidate_count == 2
    assert candidate.reason_codes == []
    assert candidate.deltas_json["final_hit_count_delta"] == 1
    assert candidate.deltas_json["roi_delta"] is not None
    assert candidate.deltas_json["roi_delta"] > 0
    assert report.best_candidate == candidate


def test_threshold_grid_rejects_inactive_competition_group() -> None:
    report = build_historical_short_price_threshold_grid_report(
        [_threshold_slice()],
        options=HistoricalShortPriceThresholdGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
            ),
            competition_groups=(("OTHER",),),
            baseline_optimizer_profile="heuristic",
            candidate_optimizer_profile="heuristic",
        ),
    )

    assert report.accepted_count == 0
    assert report.rejected_count == 1
    candidate = report.candidates[0]
    assert candidate.penalized_candidate_count == 0
    assert "threshold_grid:penalized_candidate_count_too_low" in candidate.reason_codes


def test_threshold_grid_requires_objective_improvement_for_promotion() -> None:
    report = build_historical_short_price_threshold_grid_report(
        [_threshold_slice()],
        options=HistoricalShortPriceThresholdGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
            ),
            competition_groups=(("TEST",),),
            max_decimal_odds_values=(1.35,),
            min_probability_values=(0.70,),
            max_model_edge_values=(0.0,),
            strength_values=(0.0,),
            baseline_optimizer_profile="heuristic",
            candidate_optimizer_profile="heuristic",
        ),
    )

    assert report.accepted_count == 0
    candidate = report.candidates[0]
    assert candidate.status == "rejected"
    assert candidate.penalized_candidate_count == 2
    assert candidate.objective_improvement_satisfied is False
    assert candidate.objective_improvement_metric_codes == []
    assert "threshold_grid:objective_improvement_missing" in candidate.reason_codes


def test_short_price_threshold_grid_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_knockout_suite.json",
            "--output-path",
            "tmp/threshold-grid.json",
            "--pass-types",
            "2x1,4x1",
            "--modes",
            "single",
            "--strategy",
            "accuracy_first",
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
            "--baseline-optimizer-profile",
            "heuristic",
            "--candidate-optimizer-profile",
            "solver",
            "--competition-group",
            "ESP_LA_LIGA,JPN_J1",
            "--competition-group",
            "GER_BUNDESLIGA",
            "--max-decimal-odds-values",
            "1.25,1.35",
            "--min-probability-values",
            "0.70,0.75",
            "--max-model-edge-values",
            "0.0,-0.02",
            "--strength-values",
            "0.5,1.0",
            "--fail-on-suite-statuses",
            "regressed,mixed,unchanged",
            "--min-penalized-candidate-count",
            "2",
            "--min-final-hit-count-delta",
            "1",
            "--min-final-hit-rate-delta",
            "0.01",
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
            "--min-upset-capture-rate-delta",
            "0.06",
            "--no-require-objective-improvement",
            "--min-objective-roi-delta",
            "0.07",
            "--min-objective-upset-capture-rate-delta",
            "0.08",
            "--comparison-epsilon",
            "0.000000001",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/threshold-grid.json")
    assert options.backtest_options.pass_types == ("2x1", "4x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.strategy == "accuracy_first"
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 12
    assert options.backtest_options.min_probability == 0.2
    assert options.backtest_options.min_data_quality_score == 70
    assert options.backtest_options.max_outcomes_per_fixture == 3
    assert options.backtest_options.upset_threshold == 0.4
    assert options.backtest_options.candidate_fixture_limit == 48
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 6
    assert options.backtest_options.derive_market_context_signals is True
    assert options.baseline_optimizer_profile == "heuristic"
    assert options.candidate_optimizer_profile == "solver"
    assert options.competition_groups == (
        ("ESP_LA_LIGA", "JPN_J1"),
        ("GER_BUNDESLIGA",),
    )
    assert options.max_decimal_odds_values == (1.25, 1.35)
    assert options.min_probability_values == (0.70, 0.75)
    assert options.max_model_edge_values == (0.0, -0.02)
    assert options.strength_values == (0.5, 1.0)
    assert options.fail_on_suite_statuses == ("regressed", "mixed", "unchanged")
    assert options.min_penalized_candidate_count == 2
    assert options.min_final_hit_count_delta == 1
    assert options.min_final_hit_rate_delta == 0.01
    assert options.min_roi_delta == 0.02
    assert options.min_profit_loss_delta == 1.5
    assert options.max_brier_score_delta == 0.03
    assert options.max_log_loss_delta == 0.04
    assert options.max_mean_calibration_error_delta == 0.05
    assert options.min_upset_capture_rate_delta == 0.06
    assert options.require_objective_improvement is False
    assert options.min_objective_roi_delta == 0.07
    assert options.min_objective_upset_capture_rate_delta == 0.08
    assert options.comparison_epsilon == 0.000000001


def test_threshold_grid_comparison_epsilon_ignores_float_noise() -> None:
    reason_codes: list[str] = []

    _append_minimum_reason(
        reason_codes,
        {"roi_delta": -1e-14},
        key="roi_delta",
        threshold=0.0,
        reason_code="threshold_grid:roi_regressed",
        epsilon=1e-12,
    )
    _append_maximum_reason(
        reason_codes,
        {"brier_score_delta": 1e-14},
        key="brier_score_delta",
        threshold=0.0,
        reason_code="threshold_grid:brier_score_regressed",
        epsilon=1e-12,
    )

    assert reason_codes == []

    _append_minimum_reason(
        reason_codes,
        {"roi_delta": -1e-14},
        key="roi_delta",
        threshold=0.0,
        reason_code="threshold_grid:roi_regressed",
        epsilon=0.0,
    )

    assert reason_codes == ["threshold_grid:roi_regressed"]


def _threshold_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="threshold_grid_unit_slice",
            name="Threshold grid unit slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture(
                "bad_a",
                actual_home_goals=1,
                actual_away_goals=1,
                probability=0.86,
                decimal_odds=1.18,
                model_edge=-0.035,
            ),
            _fixture(
                "bad_b",
                actual_home_goals=0,
                actual_away_goals=1,
                probability=0.85,
                decimal_odds=1.20,
                model_edge=-0.025,
            ),
            _fixture(
                "good_a",
                actual_home_goals=2,
                actual_away_goals=0,
                probability=0.66,
                decimal_odds=1.82,
                model_edge=0.11,
            ),
            _fixture(
                "good_b",
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
        model_version="poisson-v3.1-threshold-grid-test",
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
