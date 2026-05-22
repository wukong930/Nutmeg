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
from nutmeg.recommendations.marginal_loss_driver_candidate_guardrail_grid import (
    HistoricalMarginalLossDriverCandidateGuardrailGridOptions,
    _options_from_args,
    _parse_args,
    build_historical_marginal_loss_driver_candidate_guardrail_grid_report,
    merge_historical_marginal_loss_driver_candidate_guardrail_grid_reports,
)


def test_loss_driver_candidate_guardrail_grid_evaluates_narrow_specs() -> None:
    report = build_historical_marginal_loss_driver_candidate_guardrail_grid_report(
        [_slice()],
        options=HistoricalMarginalLossDriverCandidateGuardrailGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
                optimizer_profile="heuristic",
            ),
            optimizer_profile="heuristic",
            competition_groups=(("TEST",), ("OTHER",)),
            probability_min_values=(0.65,),
            probability_max_values=(0.80,),
            max_decimal_odds_values=(1.50,),
            max_model_edge_values=(-0.02,),
            max_final_hit_harm_count_vs_baseline=0,
            max_profit_loss_harm_count_vs_baseline=0,
            require_objective_improvement=False,
        ),
    )

    assert report.candidate_count == 2
    assert report.evaluated_candidate_count == 2
    assert report.accepted_count == 0
    assert report.candidates[0].competition_ids == ("TEST",)
    assert report.candidates[0].excluded_candidate_count == 2
    assert report.candidates[0].status == "rejected"
    assert "loss_driver_guardrail:excluded_candidate_count_too_low" not in (
        report.candidates[0].reason_codes
    )
    assert report.candidates[1].competition_ids == ("OTHER",)
    assert report.candidates[1].excluded_candidate_count == 0
    assert "loss_driver_guardrail:excluded_candidate_count_too_low" in (
        report.candidates[1].reason_codes
    )
    assert report.best_candidate is not None


def test_loss_driver_candidate_guardrail_grid_selects_explicit_candidate_indices() -> None:
    report = build_historical_marginal_loss_driver_candidate_guardrail_grid_report(
        [_slice()],
        options=HistoricalMarginalLossDriverCandidateGuardrailGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
                optimizer_profile="heuristic",
            ),
            optimizer_profile="heuristic",
            competition_groups=(("TEST",), ("OTHER",), ("THIRD",)),
            probability_min_values=(0.65,),
            probability_max_values=(0.80,),
            max_decimal_odds_values=(1.50,),
            max_model_edge_values=(-0.02,),
            require_objective_improvement=False,
            candidate_indices=(1,),
        ),
    )

    assert report.candidate_count == 3
    assert report.evaluated_candidate_count == 1
    assert [candidate.candidate_index for candidate in report.candidates] == [1]
    assert report.summary_json["candidate_selection_mode"] == "explicit_indices"
    assert report.summary_json["requested_candidate_indices"] == [1]
    assert report.summary_json["unmatched_requested_candidate_indices"] == []
    assert report.summary_json["candidate_indices"] == [1]
    assert report.summary_json["missing_candidate_indices"] == [0, 2]
    assert report.summary_json["next_candidate_start_index"] == 2
    assert report.summary_json["is_full_grid"] is False


def test_loss_driver_candidate_guardrail_grid_merges_batch_reports() -> None:
    base_options = HistoricalMarginalLossDriverCandidateGuardrailGridOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("single",),
            unit_stake=2.0,
            max_budget=2.0,
            min_probability=0.10,
            optimizer_profile="heuristic",
        ),
        optimizer_profile="heuristic",
        competition_groups=(("TEST",), ("OTHER",)),
        probability_min_values=(0.65,),
        probability_max_values=(0.80,),
        max_decimal_odds_values=(1.50,),
        max_model_edge_values=(-0.02,),
        require_objective_improvement=False,
        candidate_limit=1,
    )
    first_report = build_historical_marginal_loss_driver_candidate_guardrail_grid_report(
        [_slice()],
        options=base_options.model_copy(update={"candidate_start_index": 0}),
    )
    second_report = build_historical_marginal_loss_driver_candidate_guardrail_grid_report(
        [_slice()],
        options=base_options.model_copy(update={"candidate_start_index": 1}),
    )

    merged = merge_historical_marginal_loss_driver_candidate_guardrail_grid_reports(
        [second_report, first_report],
        source_paths=(Path("batch-1.json"), Path("batch-0.json")),
    )

    assert merged.candidate_count == 2
    assert merged.evaluated_candidate_count == 2
    assert [candidate.candidate_index for candidate in merged.candidates] == [0, 1]
    assert merged.summary_json["candidate_selection_mode"] == "merged"
    assert merged.summary_json["missing_candidate_indices"] == []
    assert merged.summary_json["duplicate_candidate_indices"] == []
    assert merged.summary_json["is_full_grid"] is True
    assert merged.summary_json["source_report_paths"] == [
        "batch-1.json",
        "batch-0.json",
    ]


def test_loss_driver_candidate_guardrail_grid_rejects_original_harm() -> None:
    report = build_historical_marginal_loss_driver_candidate_guardrail_grid_report(
        [_harm_slice()],
        options=HistoricalMarginalLossDriverCandidateGuardrailGridOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                unit_stake=2.0,
                max_budget=2.0,
                min_probability=0.10,
                optimizer_profile="heuristic",
            ),
            optimizer_profile="heuristic",
            competition_groups=(("TEST",),),
            probability_min_values=(0.65,),
            probability_max_values=(0.80,),
            max_decimal_odds_values=(1.50,),
            max_model_edge_values=(-0.02,),
            max_final_hit_harm_count_vs_baseline=0,
            max_profit_loss_harm_count_vs_baseline=0,
            require_objective_improvement=False,
        ),
    )

    assert report.candidate_count == 1
    assert report.accepted_count == 0
    assert report.candidates[0].final_hit_harm_count_vs_baseline == 1
    assert report.candidates[0].profit_loss_harm_count_vs_baseline == 1
    assert report.candidates[0].status == "rejected"
    assert (
        "loss_driver_guardrail:final_hit_harm_count_above_threshold"
        in report.candidates[0].reason_codes
    )
    assert (
        "loss_driver_guardrail:profit_loss_harm_count_above_threshold"
        in report.candidates[0].reason_codes
    )


def test_loss_driver_candidate_guardrail_grid_cli_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--suite-manifest",
            "configs/recommendations/historical_suites/euro_2024_knockout_suite.json",
            "--output-path",
            "tmp/loss-driver-candidate-guardrail-grid.json",
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
            "--competition-group",
            "JPN_J1,ESP_LA_LIGA",
            "--competition-group",
            "FRA_LIGUE_2",
            "--probability-min-values",
            "0.45,0.55",
            "--probability-max-values",
            "0.55,0.65",
            "--max-decimal-odds-values",
            "1.60,2.00",
            "--max-model-edge-values=-0.01,-0.03",
            "--max-calibration-score-values",
            "none,0.85",
            "--max-model-confidence-score-values",
            "none,0.87",
            "--max-odds-stability-score-values",
            "none,0.74",
            "--candidate-start-index",
            "2",
            "--candidate-limit",
            "5",
            "--candidate-indices",
            "1,3",
            "--min-excluded-candidate-count",
            "2",
            "--max-final-hit-harm-count-vs-baseline",
            "0",
            "--max-profit-loss-harm-count-vs-baseline",
            "1",
            "--no-require-objective-improvement",
        ]
    )
    options = _options_from_args(args)

    assert args.output_path == Path("tmp/loss-driver-candidate-guardrail-grid.json")
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
    assert options.competition_groups == (
        ("JPN_J1", "ESP_LA_LIGA"),
        ("FRA_LIGUE_2",),
    )
    assert options.probability_min_values == (0.45, 0.55)
    assert options.probability_max_values == (0.55, 0.65)
    assert options.max_decimal_odds_values == (1.60, 2.00)
    assert options.max_model_edge_values == (-0.01, -0.03)
    assert options.max_calibration_score_values == (None, 0.85)
    assert options.max_model_confidence_score_values == (None, 0.87)
    assert options.max_odds_stability_score_values == (None, 0.74)
    assert options.candidate_start_index == 2
    assert options.candidate_limit == 5
    assert options.candidate_indices == (1, 3)
    assert options.min_excluded_candidate_count == 2
    assert options.max_final_hit_harm_count_vs_baseline == 0
    assert options.max_profit_loss_harm_count_vs_baseline == 1
    assert options.require_objective_improvement is False


def _slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="loss_driver_candidate_guardrail_grid_unit_slice",
            name="Loss-driver candidate guardrail grid unit slice",
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


def _harm_slice() -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id="loss_driver_candidate_guardrail_grid_harm_slice",
            name="Loss-driver candidate guardrail grid harm slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture(
                "risky_winner_a",
                actual_home_goals=2,
                actual_away_goals=0,
                probability=0.79,
                decimal_odds=1.30,
                model_edge=-0.04,
            ),
            _fixture(
                "risky_winner_b",
                actual_home_goals=1,
                actual_away_goals=0,
                probability=0.78,
                decimal_odds=1.31,
                model_edge=-0.04,
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
        model_version="poisson-v3.1-loss-driver-candidate-guardrail-grid-test",
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
