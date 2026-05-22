from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nutmeg.recommendations.historical_backtest import (
    HistoricalDynamicMixFinalAnswerLaneConstraintProfile,
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    HistoricalRecommendationSliceMetadata,
    run_historical_recommendation_backtest,
)
from nutmeg.recommendations.historical_final_answer_market_concentration_audit import (
    HistoricalFinalAnswerMarketConcentrationAuditOptions,
    _options_from_args,
    _parse_args,
    main,
    run_historical_final_answer_market_concentration_audit,
)


def test_market_concentration_audit_flags_single_market_dominance() -> None:
    report = run_historical_final_answer_market_concentration_audit(
        [
            _handicap_only_slice("single_market_slice_a"),
            _handicap_only_slice("single_market_slice_b"),
        ],
        options=HistoricalFinalAnswerMarketConcentrationAuditOptions(
            pass_types=("1x1",),
            modes=("single",),
            allowed_markets=("cn_handicap_1x2",),
            min_probability=0.10,
            min_data_quality_score=0.0,
            min_final_answer_count=2,
            min_market_type_count=2,
            max_dominant_single_market_rate=0.50,
            min_dynamic_mixed_final_answer_count=1,
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.passed is False
    assert report.status == "failed"
    assert report.final_answer_count == 2
    assert report.market_type_counts == {"cn_handicap_1x2": 2}
    assert report.single_market_type_counts == {"cn_handicap_1x2": 2}
    assert report.dominant_single_market_type == "cn_handicap_1x2"
    assert report.dominant_single_market_rate == 1.0
    assert report.dynamic_mixed_final_answer_count == 0
    assert failed_checks == {
        "market_type_count",
        "dominant_single_market_rate",
        "dynamic_mixed_final_answer_count",
    }
    assert (
        "final_answer_market_concentration_audit:single_market_final_answer_dominance"
        in report.warnings
    )
    assert len(report.single_market_slice_samples) == 2


def test_market_concentration_audit_passes_true_dynamic_mixed_answers() -> None:
    report = run_historical_final_answer_market_concentration_audit(
        [
            _dynamic_mixed_slice("mixed_slice_a"),
            _dynamic_mixed_slice("mixed_slice_b"),
        ],
        options=HistoricalFinalAnswerMarketConcentrationAuditOptions(
            pass_types=("2x1",),
            modes=("single",),
            allowed_markets=("1x2", "cn_handicap_1x2"),
            min_probability=0.10,
            min_data_quality_score=0.0,
            min_final_answer_count=2,
            min_market_type_count=2,
            max_dominant_single_market_rate=0.0,
            min_dynamic_mixed_final_answer_count=2,
            min_dynamic_mixed_final_answer_rate=1.0,
        ),
    )

    assert report.passed is True
    assert report.status == "passed"
    assert report.market_type_counts == {"1x2": 2, "cn_handicap_1x2": 2}
    assert report.single_market_final_answer_count == 0
    assert report.dominant_single_market_rate == 0.0
    assert report.dynamic_mixed_final_answer_count == 2
    assert report.dynamic_mixed_final_answer_rate == 1.0
    assert len(report.dynamic_mixed_slice_samples) == 2
    assert report.warnings == []


def test_market_concentration_audit_can_limit_slice_count() -> None:
    report = run_historical_final_answer_market_concentration_audit(
        [
            _dynamic_mixed_slice("limited_slice_a"),
            _dynamic_mixed_slice("limited_slice_b"),
        ],
        options=HistoricalFinalAnswerMarketConcentrationAuditOptions(
            pass_types=("2x1",),
            modes=("single",),
            allowed_markets=("1x2", "cn_handicap_1x2"),
            min_probability=0.10,
            min_data_quality_score=0.0,
            slice_limit=1,
            min_final_answer_count=1,
            min_market_type_count=2,
            min_dynamic_mixed_final_answer_count=1,
        ),
    )

    assert report.slice_count == 1
    assert report.comparison_count == 1
    assert report.final_answer_count == 1
    assert report.dynamic_mixed_final_answer_count == 1


def test_market_concentration_audit_dynamic_mix_lane_can_select_replacement() -> None:
    report = run_historical_final_answer_market_concentration_audit(
        [_dynamic_mix_lane_replacement_slice("lane_slice")],
        options=HistoricalFinalAnswerMarketConcentrationAuditOptions(
            pass_types=("2x1",),
            modes=("single",),
            allowed_markets=("1x2", "cn_handicap_1x2"),
            min_probability=0.10,
            min_data_quality_score=0.0,
            max_candidates_per_fixture=1,
            dynamic_mix_final_answer_lane=True,
            dynamic_mix_final_answer_lane_pass_types=("2x1",),
            dynamic_mix_final_answer_lane_candidate_limit=8,
            dynamic_mix_final_answer_lane_score_boost=1.0,
            min_final_answer_count=1,
            min_market_type_count=2,
            max_dominant_single_market_rate=0.0,
            min_dynamic_mixed_final_answer_count=1,
        ),
    )

    assert report.passed is True
    assert report.status == "passed"
    assert report.dynamic_mixed_final_answer_count == 1
    assert report.single_market_final_answer_count == 0
    assert report.market_type_counts == {"1x2": 1, "cn_handicap_1x2": 1}
    assert (
        report.summary_json["candidate_completed_dynamic_mix_final_answer_lane_count"]
        == 1
    )
    assert (
        report.summary_json[
            "candidate_final_answer_dynamic_mix_final_answer_lane_count"
        ]
        == 1
    )


def test_market_concentration_audit_dynamic_mix_lane_supports_8x1() -> None:
    report = run_historical_final_answer_market_concentration_audit(
        [_dynamic_mix_lane_replacement_slice("lane_8x1", fixture_count=8)],
        options=HistoricalFinalAnswerMarketConcentrationAuditOptions(
            pass_types=("8x1",),
            modes=("single",),
            allowed_markets=("1x2", "cn_handicap_1x2"),
            min_probability=0.10,
            min_data_quality_score=0.0,
            max_candidates_per_fixture=1,
            dynamic_mix_final_answer_lane=True,
            dynamic_mix_final_answer_lane_pass_types=("8x1",),
            dynamic_mix_final_answer_lane_candidate_limit=24,
            dynamic_mix_final_answer_lane_score_boost=1.0,
            min_final_answer_count=1,
            min_market_type_count=2,
            max_dominant_single_market_rate=0.0,
            min_dynamic_mixed_final_answer_count=1,
        ),
    )

    assert report.passed is True
    assert report.dynamic_mixed_final_answer_count == 1
    assert report.dynamic_mixed_slice_samples[0].pass_type == "8x1"
    assert report.dynamic_mixed_slice_samples[0].selected_candidate_count == 8


def test_market_concentration_audit_dynamic_mix_lane_supports_multiple_mode() -> None:
    report = run_historical_final_answer_market_concentration_audit(
        [_dynamic_mix_lane_replacement_slice("lane_multiple", fixture_count=3)],
        options=HistoricalFinalAnswerMarketConcentrationAuditOptions(
            pass_types=("3x1",),
            modes=("multiple",),
            allowed_markets=("1x2", "cn_handicap_1x2"),
            max_budget=8.0,
            min_probability=0.10,
            min_data_quality_score=0.0,
            max_candidates_per_fixture=1,
            dynamic_mix_final_answer_lane=True,
            dynamic_mix_final_answer_lane_pass_types=("3x1",),
            dynamic_mix_final_answer_lane_modes=("multiple",),
            dynamic_mix_final_answer_lane_candidate_limit=12,
            dynamic_mix_final_answer_lane_score_boost=1.0,
            min_final_answer_count=1,
            min_market_type_count=2,
            max_dominant_single_market_rate=0.0,
            min_dynamic_mixed_final_answer_count=1,
        ),
    )

    assert report.passed is True
    assert report.dynamic_mixed_final_answer_count == 1
    assert report.dynamic_mixed_slice_samples[0].mode == "multiple"
    assert (
        report.summary_json[
            "candidate_final_answer_dynamic_mix_final_answer_lane_count"
        ]
        == 1
    )


def test_dynamic_mix_lane_consumes_constraint_profile_for_multiple_runtime() -> None:
    result = run_historical_recommendation_backtest(
        _dynamic_mix_lane_replacement_slice("lane_constraint_profile", fixture_count=3),
        options=HistoricalRecommendationBacktestOptions(
            pass_types=("2x1",),
            modes=("multiple",),
            allowed_markets=("1x2", "cn_handicap_1x2"),
            max_budget=8.0,
            min_probability=0.10,
            min_data_quality_score=0.0,
            max_candidates_per_fixture=1,
            max_outcomes_per_fixture=2,
            dynamic_mix_final_answer_lane=True,
            dynamic_mix_final_answer_lane_pass_types=("2x1", "3x1"),
            dynamic_mix_final_answer_lane_modes=("multiple",),
            dynamic_mix_final_answer_lane_admitted_pass_types=("2x1", "3x1"),
            dynamic_mix_final_answer_lane_blocked_pass_types=("2x1", "4x1"),
            dynamic_mix_final_answer_lane_constraint_profiles=(
                HistoricalDynamicMixFinalAnswerLaneConstraintProfile(
                    profile_key=(
                        "2x1:multiple:"
                        "max_outcomes_per_fixture=1|min_marginal_quality_gain=0"
                    ),
                    pass_type="2x1",
                    mode="multiple",
                    constraint_profile_id=(
                        "max_outcomes_per_fixture=1|min_marginal_quality_gain=0"
                    ),
                    constraint_profile_json={
                        "max_outcomes_per_fixture": 1,
                        "min_marginal_quality_gain": 0.0,
                    },
                ),
            ),
            dynamic_mix_final_answer_lane_candidate_limit=12,
            dynamic_mix_final_answer_lane_score_boost=1.0,
        ),
    )

    lane_result = next(
        scenario
        for scenario in result.scenarios
        if scenario.scenario.scenario_key.startswith("dynamic_mix_lane:2x1:multiple")
    )

    assert lane_result.option is not None
    assert lane_result.option.mode == "multiple"
    assert result.summary_json["dynamic_mix_final_answer_lane_effective_pass_types"] == [
        "2x1"
    ]
    profiles = result.summary_json[
        "dynamic_mix_final_answer_lane_effective_constraint_profiles"
    ]
    assert profiles[0]["constraint_profile_json"]["max_outcomes_per_fixture"] == 1
    lane_payload = lane_result.option.explanation_json["dynamic_mix_final_answer_lane"]
    assert lane_payload["constraint_profile_id"] == (
        "max_outcomes_per_fixture=1|min_marginal_quality_gain=0"
    )
    assert lane_result.option.selection.explanation_json[
        "dynamic_mix_final_answer_lane"
    ]["max_outcomes_per_fixture"] == 1


def test_market_concentration_audit_cli_writes_report(tmp_path: Path) -> None:
    slice_path = tmp_path / "handicap_slice.json"
    output_path = tmp_path / "market_concentration.json"
    slice_path.write_text(
        f"{_handicap_only_slice('cli_single_market_slice').model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            str(slice_path),
            "--output-path",
            str(output_path),
            "--pass-types",
            "1x1",
            "--modes",
            "single",
            "--allowed-markets",
            "cn_handicap_1x2",
            "--min-probability",
            "0.10",
            "--min-data-quality-score",
            "0",
            "--max-dominant-single-market-rate",
            "1.0",
        ]
    )

    report_text = output_path.read_text(encoding="utf-8")

    assert output_path.exists()
    assert "historical_final_answer_market_concentration_audit" in report_text
    assert "cn_handicap_1x2" in report_text


def test_market_concentration_audit_cli_args_map_to_options() -> None:
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--output-path",
            "tmp/market_concentration.json",
            "--audit-id",
            "unit-audit",
            "--pass-types",
            "2x1,6x1",
            "--modes",
            "single,multiple",
            "--strategy",
            "accuracy_first",
            "--allowed-markets",
            "1x2,cn_handicap_1x2,correct_score",
            "--unit-stake",
            "3",
            "--max-budget",
            "18",
            "--min-probability",
            "0.04",
            "--min-data-quality-score",
            "12",
            "--candidate-fixture-limit",
            "8",
            "--max-candidates-per-fixture",
            "4",
            "--max-outcomes-per-fixture",
            "2",
            "--min-marginal-quality-gain",
            "0.03",
            "--scenario-candidate-fixture-buffer",
            "5",
            "--final-answer-scenario-variant-count",
            "3",
            "--final-answer-stake-efficiency-guard",
            "--final-answer-stake-efficiency-penalty-strength",
            "0.2",
            "--final-answer-stake-efficiency-max-stake-multiplier",
            "1.5",
            "--final-answer-stake-efficiency-min-roi",
            "0.03",
            "--final-answer-stake-efficiency-modes",
            "multiple",
            "--final-answer-stake-efficiency-scope",
            "all",
            "--dynamic-mix-final-answer-lane",
            "--dynamic-mix-final-answer-lane-pass-types",
            "2x1,3x1",
            "--dynamic-mix-final-answer-lane-mode",
            "single",
            "--dynamic-mix-final-answer-lane-modes",
            "single,multiple",
            "--dynamic-mix-final-answer-lane-admitted-pass-types",
            "3x1",
            "--dynamic-mix-final-answer-lane-blocked-pass-types",
            "2x1,4x1",
            "--dynamic-mix-final-answer-lane-min-market-count",
            "2",
            "--dynamic-mix-final-answer-lane-candidate-limit",
            "64",
            "--dynamic-mix-final-answer-lane-solver-search",
            "--dynamic-mix-final-answer-lane-min-probability",
            "0.01",
            "--dynamic-mix-final-answer-lane-score-boost",
            "0.12",
            "--dynamic-mix-final-answer-lane-max-hit-probability-deficit",
            "0.2",
            "--dynamic-mix-final-answer-lane-min-roi-delta",
            "-0.05",
            "--correct-score-final-answer-lane",
            "--correct-score-final-answer-lane-pass-types",
            "2x1,8x1",
            "--correct-score-final-answer-lane-mode",
            "single",
            "--correct-score-final-answer-lane-modes",
            "single,multiple",
            "--correct-score-final-answer-lane-candidate-limit",
            "48",
            "--correct-score-final-answer-lane-min-probability",
            "0.02",
            "--correct-score-final-answer-lane-min-correct-score-probability",
            "0.08",
            "--correct-score-final-answer-lane-max-correct-score-per-selection",
            "2",
            "--correct-score-final-answer-lane-score-boost",
            "0.2",
            "--correct-score-final-answer-lane-max-hit-probability-deficit",
            "0.15",
            "--correct-score-final-answer-lane-min-roi-delta",
            "-0.03",
            "--correct-score-final-answer-lane-outcomes",
            "1-0,2-1",
            "--baseline-optimizer-profile",
            "heuristic",
            "--candidate-optimizer-profile",
            "solver",
            "--slice-limit",
            "9",
            "--min-final-answer-count",
            "50",
            "--min-market-type-count",
            "2",
            "--max-dominant-single-market-rate",
            "0.85",
            "--min-dynamic-mixed-final-answer-count",
            "6",
            "--min-dynamic-mixed-final-answer-rate",
            "0.1",
            "--min-correct-score-final-answer-count",
            "3",
            "--min-multiple-choice-final-answer-count",
            "4",
            "--min-final-hit-rate-delta",
            "0",
            "--min-roi-delta",
            "-0.01",
            "--min-profit-loss-delta",
            "-1",
            "--max-brier-score-delta",
            "0.02",
            "--max-log-loss-delta",
            "0.03",
            "--max-mean-calibration-error-delta",
            "0.04",
            "--top-slice-limit",
            "7",
        ]
    )

    options = _options_from_args(args)

    assert args.output_path == Path("tmp/market_concentration.json")
    assert options.audit_id == "unit-audit"
    assert options.pass_types == ("2x1", "6x1")
    assert options.modes == ("single", "multiple")
    assert options.allowed_markets == ("1x2", "cn_handicap_1x2", "correct_score")
    assert options.unit_stake == 3
    assert options.max_budget == 18
    assert options.min_probability == 0.04
    assert options.min_data_quality_score == 12
    assert options.candidate_fixture_limit == 8
    assert options.max_candidates_per_fixture == 4
    assert options.max_outcomes_per_fixture == 2
    assert options.min_marginal_quality_gain == 0.03
    assert options.scenario_candidate_fixture_buffer == 5
    assert options.final_answer_scenario_variant_count == 3
    assert options.final_answer_stake_efficiency_guard is True
    assert options.final_answer_stake_efficiency_penalty_strength == 0.2
    assert options.final_answer_stake_efficiency_max_stake_multiplier == 1.5
    assert options.final_answer_stake_efficiency_min_roi == 0.03
    assert options.final_answer_stake_efficiency_modes == ("multiple",)
    assert options.final_answer_stake_efficiency_scope == "all"
    assert options.dynamic_mix_final_answer_lane is True
    assert options.dynamic_mix_final_answer_lane_pass_types == ("2x1", "3x1")
    assert options.dynamic_mix_final_answer_lane_mode == "single"
    assert options.dynamic_mix_final_answer_lane_modes == ("single", "multiple")
    assert options.dynamic_mix_final_answer_lane_admitted_pass_types == ("3x1",)
    assert options.dynamic_mix_final_answer_lane_blocked_pass_types == ("2x1", "4x1")
    assert options.dynamic_mix_final_answer_lane_min_market_count == 2
    assert options.dynamic_mix_final_answer_lane_candidate_limit == 64
    assert options.dynamic_mix_final_answer_lane_solver_search is True
    assert options.dynamic_mix_final_answer_lane_min_probability == 0.01
    assert options.dynamic_mix_final_answer_lane_score_boost == 0.12
    assert options.dynamic_mix_final_answer_lane_max_hit_probability_deficit == 0.2
    assert options.dynamic_mix_final_answer_lane_min_roi_delta == -0.05
    assert options.correct_score_final_answer_lane is True
    assert options.correct_score_final_answer_lane_pass_types == ("2x1", "8x1")
    assert options.correct_score_final_answer_lane_mode == "single"
    assert options.correct_score_final_answer_lane_modes == ("single", "multiple")
    assert options.correct_score_final_answer_lane_candidate_limit == 48
    assert options.correct_score_final_answer_lane_min_probability == 0.02
    assert options.correct_score_final_answer_lane_min_correct_score_probability == 0.08
    assert options.correct_score_final_answer_lane_max_correct_score_per_selection == 2
    assert options.correct_score_final_answer_lane_score_boost == 0.2
    assert options.correct_score_final_answer_lane_max_hit_probability_deficit == 0.15
    assert options.correct_score_final_answer_lane_min_roi_delta == -0.03
    assert options.correct_score_final_answer_lane_outcomes == ("1-0", "2-1")
    assert options.slice_limit == 9
    assert options.min_final_answer_count == 50
    assert options.min_market_type_count == 2
    assert options.max_dominant_single_market_rate == 0.85
    assert options.min_dynamic_mixed_final_answer_count == 6
    assert options.min_dynamic_mixed_final_answer_rate == 0.1
    assert options.min_correct_score_final_answer_count == 3
    assert options.min_multiple_choice_final_answer_count == 4
    assert options.min_final_hit_rate_delta == 0
    assert options.min_roi_delta == -0.01
    assert options.min_profit_loss_delta == -1
    assert options.max_brier_score_delta == 0.02
    assert options.max_log_loss_delta == 0.03
    assert options.max_mean_calibration_error_delta == 0.04
    assert options.top_slice_limit == 7


def test_market_concentration_audit_cli_can_read_segment_gate_report(
    tmp_path: Path,
) -> None:
    segment_gate_path = tmp_path / "segment_gate.json"
    segment_gate_path.write_text(
        """
{
  "promoted_pass_types": ["3x1"],
  "blocked_pass_types": ["2x1", "4x1"]
}
""".strip(),
        encoding="utf-8",
    )
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--dynamic-mix-final-answer-lane-segment-gate-report",
            str(segment_gate_path),
        ]
    )

    options = _options_from_args(args)

    assert options.dynamic_mix_final_answer_lane_segment_gate_report == segment_gate_path
    assert options.dynamic_mix_final_answer_lane_admitted_pass_types == ("3x1",)
    assert options.dynamic_mix_final_answer_lane_blocked_pass_types == ("2x1", "4x1")


def test_market_concentration_audit_cli_can_read_constraint_admission_gate_report(
    tmp_path: Path,
) -> None:
    admission_gate_path = tmp_path / "admission_gate.json"
    admission_gate_path.write_text(
        """
{
  "effective_pass_types": ["2x1", "3x1"],
  "blocked_pass_types": ["2x1", "4x1"],
  "effective_constraint_profiles": [
    {
      "profile_key": "2x1:multiple:max_outcomes_per_fixture=1|min_marginal_quality_gain=0",
      "pass_type": "2x1",
      "mode": "multiple",
      "constraint_profile_id": "max_outcomes_per_fixture=1|min_marginal_quality_gain=0",
      "constraint_profile_json": {
        "max_outcomes_per_fixture": 1,
        "min_marginal_quality_gain": 0.0
      }
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    args = _parse_args(
        [
            "configs/recommendations/historical_slices/euro_2024_knockout_sample.json",
            "--dynamic-mix-final-answer-lane-admission-gate-report",
            str(admission_gate_path),
        ]
    )

    options = _options_from_args(args)

    assert (
        options.dynamic_mix_final_answer_lane_admission_gate_report
        == admission_gate_path
    )
    assert options.dynamic_mix_final_answer_lane_admitted_pass_types == (
        "2x1",
        "3x1",
    )
    assert options.dynamic_mix_final_answer_lane_blocked_pass_types == ("2x1", "4x1")
    assert len(options.dynamic_mix_final_answer_lane_constraint_profiles) == 1
    profile = options.dynamic_mix_final_answer_lane_constraint_profiles[0]
    assert profile.pass_type == "2x1"
    assert profile.mode == "multiple"
    assert profile.constraint_profile_json["max_outcomes_per_fixture"] == 1


def _dynamic_mixed_slice(slice_id: str) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name="Unit dynamic mixed market concentration slice",
            competition_id="TEST",
            result_source="unit final scores",
            odds_source="unit odds",
            prediction_source="unit predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture(
                fixture_id=f"{slice_id}_plain",
                actual_home_goals=2,
                actual_away_goals=0,
                prediction=HistoricalMarketPrediction(
                    market_type="1x2",
                    outcome="home_win",
                    probability=0.64,
                    decimal_odds=1.80,
                    market_probability=1 / 1.80,
                    data_quality_score=92,
                    model_confidence_score=0.88,
                    calibration_score=0.86,
                ),
            ),
            _fixture(
                fixture_id=f"{slice_id}_handicap",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction=HistoricalMarketPrediction(
                    market_type="cn_handicap_1x2",
                    outcome="handicap_draw",
                    probability=0.56,
                    decimal_odds=2.75,
                    market_probability=1 / 2.75,
                    data_quality_score=91,
                    model_confidence_score=0.87,
                    calibration_score=0.85,
                    line=-1.0,
                ),
            ),
        ],
    )


def _handicap_only_slice(slice_id: str) -> HistoricalRecommendationSlice:
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name="Unit single-market concentration slice",
            competition_id="TEST",
            result_source="unit final scores",
            odds_source="unit handicap odds",
            prediction_source="unit handicap predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=[
            _fixture(
                fixture_id=f"{slice_id}_handicap",
                actual_home_goals=1,
                actual_away_goals=0,
                prediction=HistoricalMarketPrediction(
                    market_type="cn_handicap_1x2",
                    outcome="handicap_home_win",
                    probability=0.62,
                    decimal_odds=1.95,
                    market_probability=1 / 1.95,
                    data_quality_score=91,
                    model_confidence_score=0.87,
                    calibration_score=0.85,
                    line=0.0,
                ),
            )
        ],
    )


def _dynamic_mix_lane_replacement_slice(
    slice_id: str,
    *,
    fixture_count: int = 2,
) -> HistoricalRecommendationSlice:
    fixtures: list[HistoricalFixture] = []
    for index in range(fixture_count):
        fixture_suffix = chr(ord("a") + index)
        fixtures.append(
            _fixture_with_predictions(
                fixture_id=f"{slice_id}_{fixture_suffix}",
                actual_home_goals=1 + index % 2,
                actual_away_goals=0,
                predictions=[
                    HistoricalMarketPrediction(
                        market_type="cn_handicap_1x2",
                        outcome="handicap_home_win",
                        probability=max(0.60, 0.72 - index * 0.005),
                        decimal_odds=1.55 + index * 0.01,
                        market_probability=1 / (1.55 + index * 0.01),
                        data_quality_score=94,
                        model_confidence_score=0.90,
                        calibration_score=0.88,
                        line=0.0,
                    ),
                    HistoricalMarketPrediction(
                        market_type="1x2",
                        outcome="home_win",
                        probability=max(0.45, 0.58 - index * 0.004),
                        decimal_odds=2.05 + index * 0.02,
                        market_probability=1 / (2.05 + index * 0.02),
                        data_quality_score=93,
                        model_confidence_score=0.87,
                        calibration_score=0.86,
                    ),
                ],
            )
        )
    return HistoricalRecommendationSlice(
        metadata=HistoricalRecommendationSliceMetadata(
            slice_id=slice_id,
            name="Unit dynamic mix lane replacement slice",
            competition_id="TEST",
            result_source="unit final scores",
            odds_source="unit mixed odds",
            prediction_source="unit mixed predictions",
        ),
        as_of_time_utc=_dt(2024, 6, 29, 12),
        fixtures=fixtures,
    )


def _fixture(
    *,
    fixture_id: str,
    actual_home_goals: int,
    actual_away_goals: int,
    prediction: HistoricalMarketPrediction,
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
        model_version="poisson-v3.1-market-concentration-test",
        predictions=[prediction],
    )


def _fixture_with_predictions(
    *,
    fixture_id: str,
    actual_home_goals: int,
    actual_away_goals: int,
    predictions: list[HistoricalMarketPrediction],
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
        model_version="poisson-v3.1-dynamic-mix-lane-test",
        predictions=predictions,
    )


def _dt(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
