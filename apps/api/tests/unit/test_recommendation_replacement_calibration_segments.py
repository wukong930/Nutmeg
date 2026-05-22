from __future__ import annotations

from pathlib import Path

import pytest

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_calibration_segments import (
    HistoricalReplacementCalibrationSegmentOptions,
    _options_from_args,
    _parse_args,
    build_historical_replacement_calibration_segment_report,
    main,
)


def test_replacement_calibration_segments_identify_underpriced_group() -> None:
    items = [
        _item(
            f"item_{index}",
            competition_id="UNIT_LEAGUE",
            model_top=_replacement(
                rank=1,
                fixture_id=f"model_top_{index}",
                probability=0.52,
                decimal_odds=1.90,
                model_edge=-0.02,
                score=0.58,
                quality=0.54,
                profit_loss_delta=0.0,
            ),
            actual_best=_replacement(
                rank=4,
                fixture_id=f"actual_best_{index}",
                probability=0.42,
                decimal_odds=2.70,
                model_edge=0.03,
                score=0.49,
                quality=0.43,
                profit_loss_delta=3.0,
            ),
        )
        for index in range(3)
    ]

    report = build_historical_replacement_calibration_segment_report(
        _audit_report(items),
        options=HistoricalReplacementCalibrationSegmentOptions(
            min_group_sample_size=2,
            min_simulated_actual_hit_delta_count_vs_model_top=0,
            min_replacement_leg_hit_delta_count_vs_model_top=0,
        ),
    )

    competition_group = next(
        group for group in report.groups if group.group_key == "competition:UNIT_LEAGUE"
    )
    odds_group = next(
        group for group in report.groups if group.group_key == "replacement_odds_band:value"
    )

    assert report.observation_count == 3
    assert report.calibration_candidate_count > 0
    assert competition_group.decision == "calibration_candidate"
    assert competition_group.observation_count == 3
    assert competition_group.simulated_actual_hit_delta_count_vs_model_top == 3
    assert competition_group.average_profit_loss_delta_vs_model_top == 3.0
    assert competition_group.average_hit_probability_delta_vs_model_top == pytest.approx(
        -0.1
    )
    assert odds_group.decision == "calibration_candidate"
    assert report.top_observations[0].replacement_odds_band == "value"
    assert report.top_observations[0].hit_probability_delta_band == "large_deficit"
    assert report.search_plan_count >= 1
    assert report.recommended_next_action_json["action"] == (
        "run_replacement_shadow_rerank_from_search_plan"
    )

    plan = report.search_plans[0]
    assert plan.status == "search_ready"
    assert plan.competition_ids == ["UNIT_LEAGUE"]
    assert plan.replacement_odds_band == "value"
    assert plan.hit_probability_delta_band == "large_deficit"
    assert plan.min_replacement_decimal_odds == 2.30
    assert plan.max_replacement_decimal_odds == 3.20
    assert plan.min_candidate_hit_probability_delta_vs_model_top == -1.0
    assert plan.max_candidate_hit_probability_delta_vs_model_top == -0.02
    assert plan.runtime_candidate_surface_allowed is True
    assert "runtime_shadow_replay" in plan.required_next_gates


def test_replacement_calibration_segments_flags_missed_leg_surface() -> None:
    items = [
        _item(
            f"item_{index}",
            competition_id="UNIT_LEAGUE",
            model_top=_replacement(
                rank=1,
                fixture_id=f"model_top_{index}",
                probability=0.52,
                decimal_odds=1.90,
                profit_loss_delta=0.0,
            ),
            actual_best=_replacement(
                rank=4,
                fixture_id=f"actual_best_{index}",
                probability=0.42,
                decimal_odds=2.10,
                profit_loss_delta=3.0,
            ),
        )
        for index in range(3)
    ]

    report = build_historical_replacement_calibration_segment_report(
        _audit_report(items, missed_legs_only=True),
        options=HistoricalReplacementCalibrationSegmentOptions(min_group_sample_size=2),
    )

    assert report.source_surface_kind == "missed_leg_loss_driver_surface"
    assert report.source_surface_missed_legs_only is True
    assert report.runtime_candidate_surface_allowed is False
    assert report.search_plans[0].required_next_gates[0] == "full_prematch_surface_audit"
    assert report.recommended_next_action_json["action"] == (
        "rerun_on_full_prematch_surface_before_runtime_gate"
    )


def test_replacement_calibration_segments_cli_options_and_main(
    tmp_path: Path,
) -> None:
    audit_report = _audit_report(
        [
            _item(
                "item_a",
                model_top=_replacement(rank=1, fixture_id="model_top"),
                actual_best=_replacement(rank=2, fixture_id="actual_best"),
            )
        ]
    )
    audit_path = tmp_path / "audit.json"
    output_path = tmp_path / "segments.json"
    audit_path.write_text(f"{audit_report.model_dump_json(indent=2)}\n", encoding="utf-8")

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--output-path",
            str(output_path),
            "--min-actual-best-profit-loss-delta",
            "0.5",
            "--min-profit-loss-delta-vs-model-top",
            "0.25",
            "--min-group-sample-size",
            "2",
            "--min-average-profit-loss-delta-vs-model-top",
            "0.2",
            "--max-average-hit-probability-delta-vs-model-top",
            "-0.01",
            "--min-simulated-actual-hit-delta-count-vs-model-top",
            "1",
            "--min-replacement-leg-hit-delta-count-vs-model-top",
            "1",
            "--no-include-profile-groups",
            "--max-report-groups",
            "12",
            "--max-report-observations",
            "8",
            "--max-search-plans",
            "4",
        ]
    )
    options = _options_from_args(args)

    assert options.min_actual_best_profit_loss_delta == 0.5
    assert options.min_profit_loss_delta_vs_model_top == 0.25
    assert options.min_group_sample_size == 2
    assert options.min_average_profit_loss_delta_vs_model_top == 0.2
    assert options.max_average_hit_probability_delta_vs_model_top == -0.01
    assert options.min_simulated_actual_hit_delta_count_vs_model_top == 1
    assert options.min_replacement_leg_hit_delta_count_vs_model_top == 1
    assert options.include_profile_groups is False
    assert options.max_report_groups == 12
    assert options.max_report_observations == 8
    assert options.max_search_plans == 4

    main(
        [
            "--audit-report",
            str(audit_path),
            "--output-path",
            str(output_path),
            "--min-group-sample-size",
            "1",
        ]
    )

    assert output_path.exists()


def _audit_report(
    items: list[HistoricalCandidateMarginalAuditItem],
    *,
    missed_legs_only: bool = False,
) -> HistoricalCandidateMarginalAuditReport:
    return HistoricalCandidateMarginalAuditReport(
        report_key="unit-test-candidate-replacement-audit",
        status="generated",
        slice_count=1,
        competition_count=1,
        final_answer_count=1,
        selected_leg_count=len(items),
        missed_leg_count=len(items),
        replacement_simulation_count=len(items) * 2,
        actual_replacement_opportunity_count=len(items),
        model_top_replacement_count=len(items),
        model_top_actual_improvement_count=0,
        model_top_actual_harm_count=0,
        items=items,
        summary_json={
            "target_filter": {
                "missed_legs_only": missed_legs_only,
            }
        },
    )


def _item(
    item_key: str,
    *,
    competition_id: str = "UNIT",
    model_top: HistoricalCandidateReplacementSimulation,
    actual_best: HistoricalCandidateReplacementSimulation,
) -> HistoricalCandidateMarginalAuditItem:
    return HistoricalCandidateMarginalAuditItem(
        item_key=item_key,
        slice_id="unit_slice",
        competition_id=competition_id,
        final_answer_scenario_key="1x1:single",
        pass_type="1x1",
        mode="single",
        final_answer_actual_hit=False,
        selected_fixture_id=f"{item_key}_selected",
        selected_market_type="1x2",
        selected_outcome="home_win",
        selected_probability=0.48,
        selected_decimal_odds=2.00,
        selected_model_edge=-0.03,
        selected_score=0.55,
        leg_actual_hit=False,
        original_actual_return=0.0,
        original_profit_loss=-2.0,
        original_hit_probability=0.48,
        original_roi=-1.0,
        original_risk_score=0.52,
        replacement_count=2,
        model_top_replacement=model_top,
        actual_best_replacement=actual_best,
        replacement_candidates=[model_top, actual_best],
    )


def _replacement(
    *,
    rank: int,
    fixture_id: str = "replacement",
    probability: float = 0.42,
    decimal_odds: float = 2.30,
    model_edge: float = -0.02,
    score: float = 0.52,
    quality: float = 0.48,
    profit_loss_delta: float = 2.0,
) -> HistoricalCandidateReplacementSimulation:
    return HistoricalCandidateReplacementSimulation(
        replacement_rank=rank,
        replacement_fixture_id=fixture_id,
        replacement_market_type="1x2",
        replacement_outcome="home_win",
        replacement_probability=probability,
        replacement_decimal_odds=decimal_odds,
        replacement_model_edge=model_edge,
        replacement_score=score,
        replacement_quality_score=quality,
        replacement_leg_actual_hit=profit_loss_delta > 0,
        simulated_actual_hit=profit_loss_delta > 0,
        simulated_actual_return=2.0 + profit_loss_delta,
        simulated_profit_loss=profit_loss_delta,
        simulated_hit_probability=probability,
        simulated_roi=0.10,
        simulated_risk_score=1.0 - probability,
        actual_return_delta=profit_loss_delta,
        profit_loss_delta=profit_loss_delta,
        hit_probability_delta=probability - 0.48,
        roi_delta=0.10,
        risk_score_delta=0.02,
        decision="actual_improved" if profit_loss_delta > 0 else "actual_unchanged",
    )
