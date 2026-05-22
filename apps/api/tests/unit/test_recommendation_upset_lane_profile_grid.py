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
    HistoricalUpsetLaneProfileGridOptions,
    build_historical_upset_lane_profile_grid_report,
    merge_historical_upset_lane_profile_grid_reports,
)
from nutmeg.recommendations.upset_lane_profile_grid import (
    _options_from_args,
    _parse_args,
    _parse_merge_args,
)


def test_upset_lane_profile_grid_accepts_profile_when_thresholds_pass() -> None:
    report = build_historical_upset_lane_profile_grid_report(
        [_slice()],
        options=HistoricalUpsetLaneProfileGridOptions(
            backtest_options=_backtest_options(),
            lane_min_probability_values=(0.18,),
            lane_max_decimal_odds_values=(5.0,),
            lane_min_model_edge_values=(-0.05,),
            lane_max_model_edge_values=(0.0,),
            lane_max_hit_probability_deficit_values=(None,),
            lane_score_boost_values=(0.0,),
            min_profile_candidate_sample_size=1,
            min_profile_candidate_improvement_rate=1.0,
            max_profile_candidate_harm_rate=0.0,
            min_profile_candidate_average_profit_loss_delta=1.0,
            min_profile_candidate_average_hit_probability_delta=-0.70,
            max_profile_candidate_average_brier_score_delta=None,
            max_profile_candidate_average_log_loss_delta=None,
            max_profile_candidate_average_calibration_error_delta=None,
        ),
    )

    candidate = report.candidates[0]

    assert report.status == "generated"
    assert report.total_grid_candidate_count == 1
    assert report.candidate_count == 1
    assert report.accepted_count == 1
    assert report.cache_hit_count == 0
    assert report.cache_miss_count == 0
    assert report.cache_write_count == 0
    assert report.best_candidate is not None
    assert report.best_candidate.status == "accepted"
    assert candidate.status == "accepted"
    assert candidate.candidate_index == 0
    assert candidate.candidate_cache_status == "disabled"
    assert candidate.profile_candidate_count == 1
    assert candidate.actual_improvement_count == 1
    assert candidate.actual_harm_count == 0
    assert candidate.reason_codes == []
    assert report.rejection_reason_counts == {}
    assert report.profile_rejection_reason_counts == {}
    assert report.competition_summary_json["ALL"]["accepted_count"] == 1
    assert report.summary_json["competition_summary"]["ALL"]["profile_candidate_count"] == 1
    assert (
        candidate.best_profile_candidate_key
        == "profile:near_miss:actual_improved:edge_lt_neg_0_02:odds_3_5_5_0"
    )


def test_upset_lane_profile_grid_rejects_profile_when_accuracy_gate_fails() -> None:
    report = build_historical_upset_lane_profile_grid_report(
        [_slice()],
        options=HistoricalUpsetLaneProfileGridOptions(
            backtest_options=_backtest_options(),
            lane_min_probability_values=(0.18,),
            lane_max_decimal_odds_values=(5.0,),
            lane_min_model_edge_values=(-0.05,),
            lane_max_model_edge_values=(0.0,),
            lane_max_hit_probability_deficit_values=(None,),
            lane_score_boost_values=(0.0,),
            min_profile_candidate_sample_size=1,
            min_profile_candidate_improvement_rate=1.0,
            max_profile_candidate_harm_rate=0.0,
            min_profile_candidate_average_profit_loss_delta=1.0,
            min_profile_candidate_average_hit_probability_delta=-0.70,
            max_profile_candidate_average_brier_score_delta=0.0,
        ),
    )

    candidate = report.candidates[0]

    assert report.accepted_count == 0
    assert report.rejected_count == 1
    assert candidate.status == "rejected"
    assert candidate.profile_candidate_count == 0
    assert candidate.reason_codes == ["upset_lane_profile_grid:no_profile_candidates"]
    assert report.rejection_reason_counts == {
        "upset_lane_profile_grid:no_profile_candidates": 1
    }
    assert report.profile_rejection_reason_counts == {
        "average_brier_score_delta_above_threshold": 1,
        "average_calibration_error_delta_above_threshold": 1,
        "average_log_loss_delta_above_threshold": 1,
    }
    competition_summary = report.competition_summary_json["ALL"]
    assert competition_summary["candidate_count"] == 1
    assert competition_summary["rejected_count"] == 1
    assert competition_summary["profile_rejection_reason_counts"] == {
        "average_brier_score_delta_above_threshold": 1,
        "average_calibration_error_delta_above_threshold": 1,
        "average_log_loss_delta_above_threshold": 1,
    }
    assert candidate.closest_rejected_profile_key == (
        "profile:near_miss:actual_improved:edge_lt_neg_0_02:odds_3_5_5_0"
    )
    rejected_summary = candidate.closest_rejected_profile_summary_json
    assert rejected_summary["average_brier_score_delta"] == pytest.approx(0.5452)
    assert "average_brier_score_delta_above_threshold" in rejected_summary[
        "reason_codes"
    ]


def test_upset_lane_profile_grid_batches_and_reuses_candidate_cache(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "candidate-cache"
    options = HistoricalUpsetLaneProfileGridOptions(
        backtest_options=_backtest_options(),
        lane_min_probability_values=(0.18,),
        lane_max_decimal_odds_values=(5.0,),
        lane_min_model_edge_values=(-0.05, -0.04),
        lane_max_model_edge_values=(0.0,),
        lane_max_hit_probability_deficit_values=(None,),
        lane_score_boost_values=(0.0,),
        candidate_start_index=1,
        candidate_limit=1,
        candidate_cache_dir=cache_dir,
        min_profile_candidate_sample_size=1,
        min_profile_candidate_improvement_rate=1.0,
        max_profile_candidate_harm_rate=0.0,
        min_profile_candidate_average_profit_loss_delta=1.0,
        min_profile_candidate_average_hit_probability_delta=-0.70,
        max_profile_candidate_average_brier_score_delta=None,
        max_profile_candidate_average_log_loss_delta=None,
        max_profile_candidate_average_calibration_error_delta=None,
    )

    first_report = build_historical_upset_lane_profile_grid_report(
        [_slice()],
        options=options,
    )
    second_report = build_historical_upset_lane_profile_grid_report(
        [_slice()],
        options=options,
    )

    first_candidate = first_report.candidates[0]
    second_candidate = second_report.candidates[0]

    assert first_report.total_grid_candidate_count == 2
    assert first_report.candidate_count == 1
    assert first_report.candidate_start_index == 1
    assert first_report.candidate_limit == 1
    assert first_report.cache_hit_count == 0
    assert first_report.cache_miss_count == 1
    assert first_report.cache_write_count == 1
    assert first_candidate.candidate_index == 1
    assert first_candidate.candidate_cache_status == "miss"
    assert first_candidate.candidate_cache_key is not None
    assert len(list(cache_dir.glob("*.json"))) == 1

    assert second_report.cache_hit_count == 1
    assert second_report.cache_miss_count == 0
    assert second_report.cache_write_count == 0
    assert second_candidate.candidate_index == 1
    assert second_candidate.candidate_cache_status == "hit"
    assert second_candidate.candidate_key == first_candidate.candidate_key
    assert second_candidate.candidate_cache_key == first_candidate.candidate_cache_key
    assert second_report.summary_json["candidate_indices"] == [1]


def test_upset_lane_profile_grid_merges_batch_reports() -> None:
    base_options = {
        "backtest_options": _backtest_options(),
        "lane_min_probability_values": (0.18,),
        "lane_max_decimal_odds_values": (5.0,),
        "lane_min_model_edge_values": (-0.05, -0.04),
        "lane_max_model_edge_values": (0.0,),
        "lane_max_hit_probability_deficit_values": (None,),
        "lane_score_boost_values": (0.0,),
        "candidate_limit": 1,
        "min_profile_candidate_sample_size": 1,
        "min_profile_candidate_improvement_rate": 1.0,
        "max_profile_candidate_harm_rate": 0.0,
        "min_profile_candidate_average_profit_loss_delta": 1.0,
        "min_profile_candidate_average_hit_probability_delta": -0.70,
        "max_profile_candidate_average_brier_score_delta": None,
        "max_profile_candidate_average_log_loss_delta": None,
        "max_profile_candidate_average_calibration_error_delta": None,
    }
    first_report = build_historical_upset_lane_profile_grid_report(
        [_slice()],
        options=HistoricalUpsetLaneProfileGridOptions(
            **base_options,
            candidate_start_index=0,
        ),
    )
    second_report = build_historical_upset_lane_profile_grid_report(
        [_slice()],
        options=HistoricalUpsetLaneProfileGridOptions(
            **base_options,
            candidate_start_index=1,
        ),
    )

    merged = merge_historical_upset_lane_profile_grid_reports(
        [second_report, first_report],
        source_paths=(Path("batch-1.json"), Path("batch-0.json")),
    )

    assert merged.total_grid_candidate_count == 2
    assert merged.candidate_count == 2
    assert merged.candidate_start_index == 0
    assert merged.candidate_limit == 2
    assert merged.accepted_count == 2
    assert merged.rejected_count == 0
    assert [candidate.candidate_index for candidate in merged.candidates] == [0, 1]
    assert merged.summary_json["missing_candidate_indices"] == []
    assert merged.summary_json["duplicate_candidate_indices"] == []
    assert merged.summary_json["is_full_grid"] is True
    assert merged.summary_json["source_report_paths"] == [
        "batch-1.json",
        "batch-0.json",
    ]


def test_upset_lane_profile_grid_cli_options_map_to_grid_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--output-path",
            "tmp/upset-lane-profile-grid.json",
            "--pass-types",
            "2x1,8x1",
            "--modes",
            "single",
            "--strategy",
            "accuracy_first",
            "--optimizer-profile",
            "solver",
            "--unit-stake",
            "3",
            "--max-budget",
            "18",
            "--min-probability",
            "0.20",
            "--min-data-quality-score",
            "80",
            "--candidate-fixture-limit",
            "48",
            "--max-candidates-per-fixture",
            "2",
            "--scenario-candidate-fixture-buffer",
            "4",
            "--derive-market-context-signals",
            "--upset-final-answer-lane-pass-type",
            "1x1",
            "--upset-final-answer-lane-candidate-limit",
            "24",
            "--upset-final-answer-lane-min-protection-score",
            "0.45",
            "--upset-final-answer-lane-min-calibration-score",
            "0.70",
            "--upset-final-answer-lane-min-model-confidence-score",
            "0.66",
            "--upset-final-answer-lane-min-odds-stability-score",
            "0.72",
            "--upset-final-answer-lane-max-volatility-penalty",
            "0.08",
            "--upset-final-answer-lane-max-signal-calibration-risk",
            "0.20",
            "--upset-final-answer-lane-min-signal-reliability-score",
            "0.80",
            "--competition-group",
            "GER_BUNDESLIGA",
            "--competition-group",
            "EPL,ESP_LA_LIGA",
            "--lane-min-probability-values",
            "0.18,0.22",
            "--lane-min-decimal-odds-values",
            "none,3.5",
            "--lane-max-decimal-odds-values",
            "4.5,5.0",
            "--lane-min-model-edge-values=-0.008,-0.004",
            "--lane-max-model-edge-values",
            "0.0",
            "--lane-max-hit-probability-deficit-values",
            "none,0.20",
            "--lane-score-boost-values",
            "0.0,0.25",
            "--candidate-start-index",
            "4",
            "--candidate-limit",
            "8",
            "--candidate-cache-dir",
            "tmp/upset-lane-profile-grid-cache",
            "--no-candidate-cache-read",
            "--min-group-sample-size",
            "2",
            "--top-case-limit",
            "5",
            "--min-profile-candidate-sample-size",
            "4",
            "--min-profile-candidate-improvement-rate",
            "0.60",
            "--max-profile-candidate-harm-rate",
            "0.10",
            "--min-profile-candidate-average-profit-loss-delta",
            "1.2",
            "--min-profile-candidate-average-hit-probability-delta=-0.12",
            "--max-profile-candidate-average-brier-score-delta",
            "0.01",
            "--max-profile-candidate-average-log-loss-delta",
            "0.02",
            "--max-profile-candidate-average-calibration-error-delta",
            "0.03",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/upset-lane-profile-grid.json")
    assert options.backtest_options.pass_types == ("2x1", "8x1")
    assert options.backtest_options.modes == ("single",)
    assert options.backtest_options.unit_stake == 3
    assert options.backtest_options.max_budget == 18
    assert options.backtest_options.min_probability == 0.20
    assert options.backtest_options.min_data_quality_score == 80
    assert options.backtest_options.candidate_fixture_limit == 48
    assert options.backtest_options.max_candidates_per_fixture == 2
    assert options.backtest_options.scenario_candidate_fixture_buffer == 4
    assert options.backtest_options.derive_market_context_signals is True
    assert options.backtest_options.upset_final_answer_lane is True
    assert options.backtest_options.upset_final_answer_lane_min_calibration_score == 0.70
    assert (
        options.backtest_options.upset_final_answer_lane_min_model_confidence_score
        == 0.66
    )
    assert options.backtest_options.upset_final_answer_lane_min_odds_stability_score == 0.72
    assert options.backtest_options.upset_final_answer_lane_max_volatility_penalty == 0.08
    assert (
        options.backtest_options.upset_final_answer_lane_max_signal_calibration_risk
        == 0.20
    )
    assert (
        options.backtest_options.upset_final_answer_lane_min_signal_reliability_score
        == 0.80
    )
    assert options.competition_groups == (
        ("GER_BUNDESLIGA",),
        ("EPL", "ESP_LA_LIGA"),
    )
    assert options.lane_min_probability_values == (0.18, 0.22)
    assert options.lane_min_decimal_odds_values == (None, 3.5)
    assert options.lane_max_decimal_odds_values == (4.5, 5.0)
    assert options.lane_min_model_edge_values == (-0.008, -0.004)
    assert options.lane_max_model_edge_values == (0.0,)
    assert options.lane_max_hit_probability_deficit_values == (None, 0.20)
    assert options.lane_score_boost_values == (0.0, 0.25)
    assert options.candidate_start_index == 4
    assert options.candidate_limit == 8
    assert options.candidate_cache_dir == Path("tmp/upset-lane-profile-grid-cache")
    assert options.read_candidate_cache is False
    assert options.write_candidate_cache is True
    assert options.min_group_sample_size == 2
    assert options.top_case_limit == 5
    assert options.min_profile_candidate_sample_size == 4
    assert options.min_profile_candidate_improvement_rate == 0.60
    assert options.max_profile_candidate_harm_rate == 0.10
    assert options.min_profile_candidate_average_profit_loss_delta == 1.2
    assert options.min_profile_candidate_average_hit_probability_delta == -0.12
    assert options.max_profile_candidate_average_brier_score_delta == 0.01
    assert options.max_profile_candidate_average_log_loss_delta == 0.02
    assert options.max_profile_candidate_average_calibration_error_delta == 0.03


def test_upset_lane_profile_grid_merge_cli_args_map_to_paths() -> None:
    args = _parse_merge_args(
        [
            "tmp/batch-0.json",
            "tmp/batch-1.json",
            "--output-path",
            "tmp/merged.json",
        ]
    )

    assert args.report_paths == [Path("tmp/batch-0.json"), Path("tmp/batch-1.json")]
    assert args.output_path == Path("tmp/merged.json")


def _backtest_options() -> HistoricalRecommendationBacktestOptions:
    return HistoricalRecommendationBacktestOptions(
        pass_types=("1x1",),
        modes=("single",),
        unit_stake=2.0,
        max_budget=2.0,
        min_probability=0.10,
        candidate_fixture_limit=1,
        max_candidates_per_fixture=1,
        upset_final_answer_lane=True,
        upset_final_answer_lane_pass_type="1x1",
        upset_final_answer_lane_min_protection_score=0.45,
        upset_final_answer_lane_min_probability=0.15,
        upset_final_answer_lane_score_boost=0.0,
    )


def _slice(slice_id: str = "upset_lane_profile_grid_slice") -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name="Upset lane profile grid unit slice",
            competition_id="TEST",
            result_source="unit test final scores",
            odds_source="unit test odds",
            prediction_source="unit test predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            HistoricalFixture(
                fixture_id="safe_home",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 16),
                home_team_name="Safe FC",
                away_team_name="Away FC",
                actual_home_goals=2,
                actual_away_goals=0,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-upset-lane-profile-grid-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="home_win",
                        probability=0.82,
                        decimal_odds=1.30,
                        market_probability=0.76,
                        model_edge=0.06,
                        data_quality_score=95.0,
                        calibration_score=0.90,
                        model_confidence_score=0.90,
                    )
                ],
            ),
            HistoricalFixture(
                fixture_id="upset_draw",
                competition_id="TEST",
                kickoff_time_utc=_dt(2024, 6, 30, 18),
                home_team_name="Fragile Favorite",
                away_team_name="Draw Town",
                actual_home_goals=1,
                actual_away_goals=1,
                prediction_time_utc=_dt(2024, 6, 29, 10),
                model_version="poisson-v3.1-upset-lane-profile-grid-test",
                predictions=[
                    HistoricalMarketPrediction(
                        outcome="draw",
                        probability=0.24,
                        decimal_odds=3.80,
                        market_probability=0.27,
                        model_edge=-0.03,
                        data_quality_score=92.0,
                        calibration_score=0.70,
                        model_confidence_score=0.66,
                        odds_stability_score=0.72,
                        volatility_penalty=0.08,
                        upset_protection_score=0.84,
                        metadata_json={
                            "target_outcome": "draw",
                            "upset_score": 0.84,
                            "upset_direction": "draw_overlooked",
                        },
                    )
                ],
            ),
        ],
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
