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
    HistoricalUpsetLaneAuditOptions,
    build_historical_upset_lane_audit_report,
)
from nutmeg.recommendations.upset_lane_audit import _options_from_args, _parse_args


def test_upset_lane_audit_records_near_miss_that_would_have_improved_actual_return() -> None:
    report = build_historical_upset_lane_audit_report(
        [_slice()],
        options=HistoricalUpsetLaneAuditOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
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
        ),
    )

    observation = report.observations[0]

    assert report.status == "generated"
    assert report.completed_lane_count == 1
    assert report.near_miss_count == 1
    assert report.selected_lane_count == 0
    assert report.actual_improvement_count == 1
    assert observation.status == "near_miss"
    assert observation.comparison_outcome == "actual_improved"
    assert observation.lane_rank is not None
    assert observation.lane_candidate_count == 1
    assert observation.lane_selected_outcomes == {"upset_draw": ["draw"]}
    assert observation.comparison_selected_outcomes == {"safe_home": ["home_win"]}
    assert observation.profit_loss_delta is not None
    assert observation.profit_loss_delta > 0
    assert observation.candidates[0].leg_actual_hit is True
    assert observation.candidates[0].model_edge == pytest.approx(-0.03)
    assert report.top_near_miss_improvement_cases[0].observation_key == (
        observation.observation_key
    )
    assert any(group.group_key == "status:near_miss" for group in report.groups)
    assert report.profile_candidate_count == 0
    profile_group = next(group for group in report.groups if group.group_type == "profile")
    assert profile_group.decision == "rejected"
    assert "sample_size_below_threshold" in profile_group.reason_codes
    assert "average_hit_probability_delta_below_threshold" in profile_group.reason_codes


def test_upset_lane_audit_marks_low_deficit_profile_candidate_when_thresholds_pass() -> None:
    report = build_historical_upset_lane_audit_report(
        [_slice()],
        options=HistoricalUpsetLaneAuditOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
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
            ),
            min_profile_candidate_sample_size=1,
            min_profile_candidate_improvement_rate=1.0,
            max_profile_candidate_harm_rate=0.0,
            min_profile_candidate_average_profit_loss_delta=1.0,
            min_profile_candidate_average_hit_probability_delta=-0.70,
        ),
    )

    assert report.profile_candidate_count == 1
    profile_candidate = report.profile_candidates[0]
    assert profile_candidate.group_type == "profile"
    assert profile_candidate.decision == "profile_candidate"
    assert profile_candidate.reason_codes == ["profile_candidate_thresholds_satisfied"]
    assert profile_candidate.actual_improvement_count == 1
    assert profile_candidate.harm_rate == 0.0
    assert profile_candidate.average_hit_probability_delta == pytest.approx(-0.58)
    assert (
        profile_candidate.group_key
        == "profile:near_miss:actual_improved:edge_lt_neg_0_02:odds_3_5_5_0"
    )


def test_upset_lane_audit_rejects_profile_candidate_on_accuracy_delta() -> None:
    report = build_historical_upset_lane_audit_report(
        [_slice()],
        options=HistoricalUpsetLaneAuditOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
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
            ),
            min_profile_candidate_sample_size=1,
            min_profile_candidate_improvement_rate=1.0,
            max_profile_candidate_harm_rate=0.0,
            min_profile_candidate_average_profit_loss_delta=1.0,
            min_profile_candidate_average_hit_probability_delta=-0.70,
            max_profile_candidate_average_brier_score_delta=0.0,
        ),
    )

    profile_group = next(group for group in report.groups if group.group_type == "profile")

    assert report.profile_candidate_count == 0
    assert profile_group.decision == "rejected"
    assert "average_brier_score_delta_above_threshold" in profile_group.reason_codes
    assert profile_group.average_brier_score_delta is not None
    assert profile_group.average_brier_score_delta > 0


def test_upset_lane_audit_records_selected_lane_against_best_non_lane_case() -> None:
    report = build_historical_upset_lane_audit_report(
        [_slice(slice_id="selected_lane_slice")],
        options=HistoricalUpsetLaneAuditOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
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
                upset_final_answer_lane_score_boost=1.0,
            )
        ),
    )

    observation = report.observations[0]

    assert report.selected_lane_count == 1
    assert report.near_miss_count == 0
    assert observation.status == "selected"
    assert observation.final_answer_scenario_key == "upset_lane:1x1:single"
    assert observation.comparison_scenario_key == "1x1:single"
    assert observation.comparison_selected_fixture_ids == ["safe_home"]
    assert report.top_selected_cases[0].observation_key == observation.observation_key


def test_upset_lane_audit_records_failed_quality_gate_lane() -> None:
    report = build_historical_upset_lane_audit_report(
        [_slice(slice_id="failed_lane_slice")],
        options=HistoricalUpsetLaneAuditOptions(
            backtest_options=HistoricalRecommendationBacktestOptions(
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
                upset_final_answer_lane_min_model_edge=0.0,
                upset_final_answer_lane_score_boost=1.0,
            )
        ),
    )

    observation = report.observations[0]

    assert report.failed_lane_count == 1
    assert report.completed_lane_count == 0
    assert observation.status == "failed"
    assert observation.comparison_outcome == "no_comparison"
    assert observation.error_message == "upset_final_answer_lane_no_candidates"


def test_upset_lane_audit_cli_options_map_to_backtest_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--output-path",
            "tmp/upset-lane-audit.json",
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
            "--upset-final-answer-lane",
            "--upset-final-answer-lane-pass-type",
            "1x1",
            "--upset-final-answer-lane-candidate-limit",
            "24",
            "--upset-final-answer-lane-min-protection-score",
            "0.45",
            "--upset-final-answer-lane-min-probability",
            "0.18",
            "--upset-final-answer-lane-min-decimal-odds",
            "3.5",
            "--upset-final-answer-lane-max-decimal-odds",
            "5.0",
            "--upset-final-answer-lane-min-model-edge",
            "-0.008",
            "--upset-final-answer-lane-max-model-edge",
            "0.0",
            "--upset-final-answer-lane-competitions",
            "GER_BUNDESLIGA,EPL",
            "--upset-final-answer-lane-excluded-competitions",
            "FRA_LIGUE_1",
            "--upset-final-answer-lane-min-calibration-score",
            "0.70",
            "--upset-final-answer-lane-min-model-confidence-score",
            "0.66",
            "--upset-final-answer-lane-min-odds-stability-score",
            "0.72",
            "--upset-final-answer-lane-max-volatility-penalty",
            "0.08",
            "--upset-final-answer-lane-max-hit-probability-deficit",
            "0.20",
            "--upset-final-answer-lane-score-boost",
            "0.15",
            "--focus-competitions",
            "ENG_PREMIER_LEAGUE,ESP_LA_LIGA",
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
            "--min-profile-candidate-average-hit-probability-delta",
            "-0.12",
            "--max-profile-candidate-average-brier-score-delta",
            "0.01",
            "--max-profile-candidate-average-log-loss-delta",
            "0.02",
            "--max-profile-candidate-average-calibration-error-delta",
            "0.03",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/upset-lane-audit.json")
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
    assert options.backtest_options.upset_final_answer_lane_min_probability == 0.18
    assert options.backtest_options.upset_final_answer_lane_min_decimal_odds == 3.5
    assert options.backtest_options.upset_final_answer_lane_max_decimal_odds == 5.0
    assert options.backtest_options.upset_final_answer_lane_min_model_edge == -0.008
    assert options.backtest_options.upset_final_answer_lane_max_model_edge == 0.0
    assert options.backtest_options.upset_final_answer_lane_competition_ids == (
        "GER_BUNDESLIGA",
        "EPL",
    )
    assert options.backtest_options.upset_final_answer_lane_excluded_competition_ids == (
        "FRA_LIGUE_1",
    )
    assert options.backtest_options.upset_final_answer_lane_min_calibration_score == 0.70
    assert (
        options.backtest_options.upset_final_answer_lane_min_model_confidence_score
        == 0.66
    )
    assert options.backtest_options.upset_final_answer_lane_min_odds_stability_score == 0.72
    assert options.backtest_options.upset_final_answer_lane_max_volatility_penalty == 0.08
    assert options.backtest_options.upset_final_answer_lane_max_hit_probability_deficit == 0.20
    assert options.backtest_options.upset_final_answer_lane_score_boost == 0.15
    assert options.focus_competition_ids == ("ENG_PREMIER_LEAGUE", "ESP_LA_LIGA")
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


def _slice(slice_id: str = "upset_lane_audit_slice") -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name="Upset lane audit unit slice",
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
                model_version="poisson-v3.1-upset-lane-audit-test",
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
                model_version="poisson-v3.1-upset-lane-audit-test",
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
