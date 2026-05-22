from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations import (
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationDiagnosticOptions,
    build_historical_recommendation_diagnostic_report,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_diagnostics import _options_from_args, _parse_args


def test_historical_diagnostics_groups_real_slices_by_competition_and_season() -> None:
    euro_slice = load_historical_recommendation_slice(
        "configs/recommendations/historical_slices/euro_2024_knockout_sample.json"
    )
    epl_slice = euro_slice.model_copy(
        update={
            "metadata": euro_slice.metadata.model_copy(
                update={
                    "slice_id": "diagnostic_epl_sample",
                    "competition_id": "EPL",
                    "season": "2024-2025",
                }
            )
        }
    )

    report = build_historical_recommendation_diagnostic_report(
        [euro_slice, epl_slice],
        options=HistoricalRecommendationDiagnosticOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=("2x1",),
                modes=("single",),
                max_budget=4.0,
            ),
        ),
    )

    assert report.status == "generated"
    assert report.slice_count == 2
    assert report.fixture_count == len(euro_slice.fixtures) * 2
    assert report.prediction_count == (
        sum(len(fixture.predictions) for fixture in euro_slice.fixtures) * 2
    )
    assert report.comparison_count == 2
    assert report.overall.candidate.final_hit_sample_size == 2
    assert report.overall.candidate.total_stake == 4.0
    assert report.overall.summary_json["candidate_final_hit_rate"] is not None
    assert [group.group_key for group in report.by_competition] == ["EPL", "UEFA_EURO"]
    assert [group.group_key for group in report.by_season] == ["2024", "2024-2025"]
    assert {
        group.group_key for group in report.by_competition_season
    } == {"EPL|2024-2025", "UEFA_EURO|2024"}


def test_historical_diagnostics_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--output-path",
            "tmp/diagnostics.json",
            "--pass-types",
            "2x1,4x1",
            "--modes",
            "single",
            "--strategy",
            "upset_protection",
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
            "0.42",
            "--candidate-fixture-limit",
            "48",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "6",
            "--derive-market-context-signals",
            "--upset-exposure-reserve",
            "--upset-exposure-reserve-fixture-count",
            "5",
            "--upset-exposure-reserve-max-candidates-per-fixture",
            "2",
            "--upset-exposure-reserve-min-protection-score",
            "0.48",
            "--upset-exposure-reserve-min-probability",
            "0.18",
            "--upset-exposure-reserve-max-decimal-odds",
            "8.5",
            "--upset-final-answer-lane",
            "--upset-final-answer-lane-pass-type",
            "2x1",
            "--upset-final-answer-lane-mode",
            "single",
            "--upset-final-answer-lane-candidate-limit",
            "16",
            "--upset-final-answer-lane-min-protection-score",
            "0.52",
            "--upset-final-answer-lane-min-probability",
            "0.21",
            "--upset-final-answer-lane-min-decimal-odds",
            "3.5",
            "--upset-final-answer-lane-max-decimal-odds",
            "7.5",
            "--upset-final-answer-lane-min-model-edge",
            "-0.01",
            "--upset-final-answer-lane-max-model-edge",
            "0.02",
            "--upset-final-answer-lane-competitions",
            "ESP_LA_LIGA,JPN_J1",
            "--upset-final-answer-lane-excluded-competitions",
            "FRA_LIGUE_1",
            "--upset-final-answer-lane-min-calibration-score",
            "0.87",
            "--upset-final-answer-lane-min-model-confidence-score",
            "0.86",
            "--upset-final-answer-lane-min-odds-stability-score",
            "0.74",
            "--upset-final-answer-lane-max-volatility-penalty",
            "0.08",
            "--upset-final-answer-lane-max-hit-probability-deficit",
            "0.20",
            "--upset-final-answer-lane-score-boost",
            "0.35",
            "--short-price-negative-edge-guardrail",
            "--short-price-negative-edge-max-decimal-odds",
            "1.42",
            "--short-price-negative-edge-min-probability",
            "0.72",
            "--short-price-negative-edge-max-model-edge",
            "-0.02",
            "--short-price-negative-edge-soft-penalty",
            "--short-price-negative-edge-soft-penalty-strength",
            "0.8",
            "--short-price-negative-edge-soft-penalty-competitions",
            "ESP_LA_LIGA,JPN_J1",
            "--baseline-optimizer-profile",
            "heuristic",
            "--candidate-optimizer-profile",
            "solver",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/diagnostics.json")
    assert options.backtest_options.pass_types == ("2x1", "4x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.strategy == "upset_protection"
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 12
    assert options.backtest_options.min_probability == 0.2
    assert options.backtest_options.min_data_quality_score == 70
    assert options.backtest_options.max_outcomes_per_fixture == 3
    assert options.backtest_options.upset_threshold == 0.42
    assert options.backtest_options.candidate_fixture_limit == 48
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 6
    assert options.backtest_options.derive_market_context_signals is True
    assert options.backtest_options.upset_exposure_reserve is True
    assert options.backtest_options.upset_exposure_reserve_fixture_count == 5
    assert options.backtest_options.upset_exposure_reserve_max_candidates_per_fixture == 2
    assert options.backtest_options.upset_exposure_reserve_min_protection_score == 0.48
    assert options.backtest_options.upset_exposure_reserve_min_probability == 0.18
    assert options.backtest_options.upset_exposure_reserve_max_decimal_odds == 8.5
    assert options.backtest_options.upset_final_answer_lane is True
    assert options.backtest_options.upset_final_answer_lane_pass_type == "2x1"
    assert options.backtest_options.upset_final_answer_lane_mode == "single"
    assert options.backtest_options.upset_final_answer_lane_candidate_limit == 16
    assert options.backtest_options.upset_final_answer_lane_min_protection_score == 0.52
    assert options.backtest_options.upset_final_answer_lane_min_probability == 0.21
    assert options.backtest_options.upset_final_answer_lane_min_decimal_odds == 3.5
    assert options.backtest_options.upset_final_answer_lane_max_decimal_odds == 7.5
    assert options.backtest_options.upset_final_answer_lane_min_model_edge == -0.01
    assert options.backtest_options.upset_final_answer_lane_max_model_edge == 0.02
    assert options.backtest_options.upset_final_answer_lane_competition_ids == (
        "ESP_LA_LIGA",
        "JPN_J1",
    )
    assert options.backtest_options.upset_final_answer_lane_excluded_competition_ids == (
        "FRA_LIGUE_1",
    )
    assert options.backtest_options.upset_final_answer_lane_min_calibration_score == 0.87
    assert (
        options.backtest_options.upset_final_answer_lane_min_model_confidence_score
        == 0.86
    )
    assert (
        options.backtest_options.upset_final_answer_lane_min_odds_stability_score
        == 0.74
    )
    assert (
        options.backtest_options.upset_final_answer_lane_max_volatility_penalty
        == 0.08
    )
    assert (
        options.backtest_options.upset_final_answer_lane_max_hit_probability_deficit
        == 0.20
    )
    assert options.backtest_options.upset_final_answer_lane_score_boost == 0.35
    assert options.backtest_options.short_price_negative_edge_guardrail is True
    assert options.backtest_options.short_price_negative_edge_max_decimal_odds == 1.42
    assert options.backtest_options.short_price_negative_edge_min_probability == 0.72
    assert options.backtest_options.short_price_negative_edge_max_model_edge == -0.02
    assert options.backtest_options.short_price_negative_edge_soft_penalty is True
    assert options.backtest_options.short_price_negative_edge_soft_penalty_strength == 0.8
    assert options.backtest_options.short_price_negative_edge_soft_penalty_competition_ids == (
        "ESP_LA_LIGA",
        "JPN_J1",
    )
    assert options.baseline_optimizer_profile == "heuristic"
    assert options.candidate_optimizer_profile == "solver"
