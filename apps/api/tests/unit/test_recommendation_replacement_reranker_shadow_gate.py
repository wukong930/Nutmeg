from __future__ import annotations

from json import loads
from pathlib import Path

import pytest

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_reranker_shadow_gate import (
    HistoricalReplacementRerankerShadowGateOptions,
    _options_from_args,
    _parse_args,
    build_historical_replacement_reranker_shadow_gate_report,
    main,
)
from nutmeg.recommendations.replacement_reranker_tolerance_grid import (
    HistoricalReplacementRerankerToleranceGridOptions,
    build_historical_replacement_reranker_tolerance_grid_report,
)
from nutmeg.recommendations.replacement_reranker_weight_experiment import (
    HistoricalReplacementRerankerProfile,
)


def test_replacement_reranker_shadow_gate_passes_watchlisted_tolerance() -> None:
    profile = HistoricalReplacementRerankerProfile(
        profile_id="unit_edge_tolerance",
        model_edge_weight=0.65,
        decimal_odds_weight=0.35,
    )
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        probability=0.52,
        decimal_odds=1.90,
        model_edge=-0.02,
        profit_delta=0.0,
    )
    actual_best = _replacement(
        rank=2,
        fixture_id="actual_best",
        probability=0.51,
        decimal_odds=2.60,
        model_edge=0.05,
        profit_delta=3.0,
    )
    audit_report = _audit_report(
        [_item("item_a", model_top=model_top, actual_best=actual_best)]
    )
    tolerance_report = build_historical_replacement_reranker_tolerance_grid_report(
        audit_report,
        options=HistoricalReplacementRerankerToleranceGridOptions(
            hit_probability_delta_thresholds=(-0.02,),
            profiles=(profile,),
            min_evaluated_item_count=1,
        ),
    )

    report = build_historical_replacement_reranker_shadow_gate_report(
        audit_report,
        tolerance_grid_report=tolerance_report,
        options=HistoricalReplacementRerankerShadowGateOptions(
            enable_shadow_gate=True,
            profile_id="unit_edge_tolerance",
            hit_probability_delta_threshold=-0.02,
            profiles=(profile,),
            min_final_answer_count=1,
            min_changed_from_model_top_count=1,
        ),
    )

    assert report.status == "shadow_gate_passed"
    assert report.passed is True
    assert report.source_tolerance_candidate_status == "watchlist"
    assert report.shadow_final_answer_count == 1
    assert report.changed_from_model_top_count == 1
    assert report.selected_actual_best_count == 1
    assert report.hit_delta_vs_model_top_count == 1
    assert report.replacement_leg_hit_delta_vs_model_top_count == 1
    assert report.profit_loss_delta_vs_model_top == 3.0
    assert report.harm_count_vs_model_top == 0
    assert report.final_hit_harm_count_vs_model_top == 0
    assert report.profit_loss_harm_count_vs_model_top == 0
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False


def test_replacement_reranker_shadow_gate_blocks_final_hit_harm_vs_model_top() -> None:
    model_top = _replacement(
        rank=1,
        fixture_id="model_top_hit",
        probability=0.52,
        decimal_odds=1.90,
        model_edge=-0.02,
        profit_delta=1.0,
    )
    actual_best = _replacement(
        rank=2,
        fixture_id="profitable_miss",
        probability=0.51,
        decimal_odds=2.70,
        model_edge=0.08,
        profit_delta=1.2,
    ).model_copy(
        update={
            "replacement_leg_actual_hit": False,
            "simulated_actual_hit": False,
        }
    )
    audit_report = _audit_report(
        [_item("item_a", model_top=model_top, actual_best=actual_best)]
    )

    report = build_historical_replacement_reranker_shadow_gate_report(
        audit_report,
        options=HistoricalReplacementRerankerShadowGateOptions(
            enable_shadow_gate=True,
            profile_id="edge_value_v1",
            min_final_answer_count=1,
            min_changed_from_model_top_count=1,
            min_final_answer_hit_delta_vs_model_top=-1,
            min_replacement_leg_hit_delta_vs_model_top=-1,
            require_tolerance_candidate=False,
            max_final_hit_harm_count_vs_model_top=0,
            max_profit_loss_harm_count_vs_model_top=0,
        ),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_gate_failed"
    assert report.final_hit_harm_count_vs_model_top == 1
    assert report.profit_loss_harm_count_vs_model_top == 0
    assert "final_hit_harm_count_vs_model_top" in failed_checks
    assert "profit_loss_harm_count_vs_model_top" not in failed_checks


def test_replacement_reranker_shadow_gate_requires_feature_flag() -> None:
    audit_report = _audit_report(
        [
            _item(
                "item_a",
                model_top=_replacement(rank=1, fixture_id="model_top"),
                actual_best=_replacement(
                    rank=2,
                    fixture_id="actual_best",
                    probability=0.51,
                    decimal_odds=2.50,
                    model_edge=0.04,
                    profit_delta=2.0,
                ),
            )
        ]
    )

    report = build_historical_replacement_reranker_shadow_gate_report(audit_report)

    assert report.status == "disabled"
    assert report.passed is False
    assert report.shadow_final_answer_count == 0
    assert "replacement_reranker_shadow_gate:disabled_by_feature_flag" in report.warnings


def test_replacement_reranker_shadow_gate_can_protect_original_recommendations() -> None:
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        probability=0.52,
        decimal_odds=1.90,
        model_edge=-0.02,
        profit_delta=-4.0,
    )
    actual_best = _replacement(
        rank=2,
        fixture_id="less_bad_replacement",
        probability=0.51,
        decimal_odds=2.60,
        model_edge=0.05,
        profit_delta=-1.0,
    )
    audit_report = _audit_report(
        [
            _item(
                "item_a",
                model_top=model_top,
                actual_best=actual_best,
                final_answer_actual_hit=True,
                original_profit_loss=2.0,
            )
        ]
    )

    report = build_historical_replacement_reranker_shadow_gate_report(
        audit_report,
        options=HistoricalReplacementRerankerShadowGateOptions(
            enable_shadow_gate=True,
            profile_id="edge_value_v1",
            min_actual_best_profit_loss_delta=-2.0,
            min_final_answer_count=1,
            min_changed_from_model_top_count=1,
            require_tolerance_candidate=False,
            min_final_answer_hit_delta_vs_original=0,
            min_profit_loss_delta_vs_original=0.0,
            min_roi_delta_vs_original=0.0,
            max_harm_count_vs_original=0,
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_gate_failed"
    assert report.passed is False
    assert report.hit_delta_vs_original_count == -1
    assert report.profit_loss_delta_vs_original == -1.0
    assert report.harm_count_vs_original == 1
    assert "final_answer_hit_delta_vs_original" in failed_checks
    assert "profit_loss_delta_vs_original" in failed_checks
    assert "roi_delta_vs_original" in failed_checks
    assert "harm_count_vs_original" in failed_checks


def test_replacement_reranker_shadow_gate_cli_options_and_main(tmp_path: Path) -> None:
    audit_report = _audit_report(
        [
            _item(
                "item_a",
                model_top=_replacement(rank=1, fixture_id="model_top"),
                actual_best=_replacement(
                    rank=2,
                    fixture_id="actual_best",
                    probability=0.51,
                    decimal_odds=2.50,
                    model_edge=0.04,
                    profit_delta=2.0,
                ),
            )
        ]
    )
    tolerance_report = build_historical_replacement_reranker_tolerance_grid_report(
        audit_report,
        options=HistoricalReplacementRerankerToleranceGridOptions(
            hit_probability_delta_thresholds=(-0.02,),
            min_evaluated_item_count=1,
        ),
    )
    audit_path = tmp_path / "audit.json"
    tolerance_path = tmp_path / "tolerance.json"
    output_path = tmp_path / "shadow_gate.json"
    audit_path.write_text(f"{audit_report.model_dump_json(indent=2)}\n", encoding="utf-8")
    tolerance_path.write_text(
        f"{tolerance_report.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--tolerance-grid-report",
            str(tolerance_path),
            "--output-path",
            str(output_path),
            "--enable-shadow-gate",
            "--profile-id",
            "edge_value_v1",
            "--hit-probability-delta-threshold",
            "-0.02",
            "--min-actual-best-profit-loss-delta",
            "0.5",
            "--min-profit-loss-gap",
            "0.1",
            "--min-final-answer-count",
            "1",
            "--min-changed-from-model-top-count",
            "1",
            "--min-final-answer-hit-delta-vs-model-top",
            "0",
            "--min-replacement-leg-hit-delta-vs-model-top",
            "0",
            "--min-profit-loss-delta-vs-model-top",
            "0.2",
            "--min-roi-delta-vs-model-top",
            "0.1",
            "--max-harm-count-vs-model-top",
            "1",
            "--max-final-hit-harm-count-vs-model-top",
            "2",
            "--max-profit-loss-harm-count-vs-model-top",
            "3",
            "--min-average-hit-probability-delta-vs-model-top",
            "-0.03",
            "--min-final-answer-hit-delta-vs-original",
            "0",
            "--min-profit-loss-delta-vs-original",
            "0.2",
            "--min-roi-delta-vs-original",
            "0.1",
            "--max-harm-count-vs-original",
            "1",
            "--max-final-hit-harm-count-vs-original",
            "2",
            "--max-profit-loss-harm-count-vs-original",
            "3",
            "--min-average-hit-probability-delta-vs-original",
            "-0.04",
            "--allow-missing-tolerance-candidate",
            "--allowed-tolerance-statuses",
            "watchlist",
            "--allow-source-audit-mismatch",
            "--allow-production-change",
            "--max-report-items",
            "12",
            "--no-fail-process",
        ]
    )
    options = _options_from_args(args)

    assert args.audit_report == audit_path
    assert args.tolerance_grid_report == tolerance_path
    assert args.output_path == output_path
    assert options.enable_shadow_gate is True
    assert options.profile_id == "edge_value_v1"
    assert options.hit_probability_delta_threshold == -0.02
    assert options.min_actual_best_profit_loss_delta == 0.5
    assert options.min_profit_loss_gap == 0.1
    assert options.min_final_answer_count == 1
    assert options.min_changed_from_model_top_count == 1
    assert options.min_profit_loss_delta_vs_model_top == 0.2
    assert options.min_roi_delta_vs_model_top == 0.1
    assert options.max_harm_count_vs_model_top == 1
    assert options.max_final_hit_harm_count_vs_model_top == 2
    assert options.max_profit_loss_harm_count_vs_model_top == 3
    assert options.min_average_hit_probability_delta_vs_model_top == -0.03
    assert options.min_final_answer_hit_delta_vs_original == 0
    assert options.min_profit_loss_delta_vs_original == 0.2
    assert options.min_roi_delta_vs_original == 0.1
    assert options.max_harm_count_vs_original == 1
    assert options.max_final_hit_harm_count_vs_original == 2
    assert options.max_profit_loss_harm_count_vs_original == 3
    assert options.min_average_hit_probability_delta_vs_original == -0.04
    assert options.require_tolerance_candidate is False
    assert options.allowed_tolerance_statuses == ("watchlist",)
    assert options.require_source_audit_match is False
    assert options.require_no_production_change is False
    assert options.max_report_items == 12

    main(
        [
            "--audit-report",
            str(audit_path),
            "--tolerance-grid-report",
            str(tolerance_path),
            "--output-path",
            str(output_path),
            "--enable-shadow-gate",
            "--profile-id",
            "edge_value_v1",
            "--hit-probability-delta-threshold",
            "-0.02",
            "--min-final-answer-count",
            "1",
            "--min-changed-from-model-top-count",
            "1",
            "--no-fail-process",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "shadow_gate_passed"
    assert payload["production_recommendation_changed"] is False
    assert payload["public_response_changed"] is False

    with pytest.raises(SystemExit):
        main(
            [
                "--audit-report",
                str(audit_path),
                "--tolerance-grid-report",
                str(tolerance_path),
                "--output-path",
                str(output_path),
                "--profile-id",
                "edge_value_v1",
                "--min-final-answer-count",
                "1",
            ]
        )


def _audit_report(
    items: list[HistoricalCandidateMarginalAuditItem],
) -> HistoricalCandidateMarginalAuditReport:
    return HistoricalCandidateMarginalAuditReport(
        report_key="unit-test-candidate-replacement-audit",
        status="generated",
        slice_count=1,
        competition_count=1,
        final_answer_count=1,
        selected_leg_count=len(items),
        missed_leg_count=len(items),
        replacement_simulation_count=sum(item.replacement_count for item in items),
        actual_replacement_opportunity_count=len(items),
        model_top_replacement_count=len(items),
        model_top_actual_improvement_count=0,
        model_top_actual_harm_count=0,
        items=items,
    )


def _item(
    item_key: str,
    *,
    model_top: HistoricalCandidateReplacementSimulation,
    actual_best: HistoricalCandidateReplacementSimulation,
    final_answer_actual_hit: bool = False,
    original_profit_loss: float = -2.0,
) -> HistoricalCandidateMarginalAuditItem:
    original_actual_return = max(0.0, original_profit_loss + 2.0)
    original_roi = original_profit_loss / 2.0
    return HistoricalCandidateMarginalAuditItem(
        item_key=item_key,
        slice_id="unit_slice",
        competition_id="UNIT",
        final_answer_scenario_key="1x1:single",
        pass_type="1x1",
        mode="single",
        final_answer_actual_hit=final_answer_actual_hit,
        selected_fixture_id=f"{item_key}_selected",
        selected_market_type="1x2",
        selected_outcome="home_win",
        selected_probability=0.48,
        selected_decimal_odds=2.00,
        selected_model_edge=-0.03,
        selected_score=0.55,
        leg_actual_hit=final_answer_actual_hit,
        original_actual_return=original_actual_return,
        original_profit_loss=original_profit_loss,
        original_hit_probability=0.48,
        original_roi=original_roi,
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
    probability: float = 0.52,
    decimal_odds: float = 1.90,
    model_edge: float = -0.02,
    score: float = 0.52,
    quality: float = 0.48,
    profit_delta: float = 0.0,
) -> HistoricalCandidateReplacementSimulation:
    simulated_profit = -2.0 + profit_delta
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
        replacement_leg_actual_hit=profit_delta > 0,
        simulated_actual_hit=profit_delta > 0,
        simulated_actual_return=max(0.0, simulated_profit + 2.0),
        simulated_profit_loss=simulated_profit,
        simulated_hit_probability=probability,
        simulated_roi=simulated_profit / 2.0,
        simulated_risk_score=1.0 - probability,
        actual_return_delta=profit_delta,
        profit_loss_delta=profit_delta,
        hit_probability_delta=probability - 0.48,
        roi_delta=profit_delta / 2.0,
        risk_score_delta=0.02,
        decision="actual_improved" if profit_delta > 0 else "actual_unchanged",
    )
