from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.marginal_signal_groups import (
    HistoricalMarginalSignalGroupOptions,
    _options_from_args,
    _parse_args,
    build_historical_marginal_signal_group_report,
    load_historical_candidate_marginal_audit_report,
)


def test_marginal_signal_groups_promote_stable_model_top_profile() -> None:
    audit_report = _audit_report(
        [
            _item(
                "item_a",
                selected_probability=0.74,
                selected_decimal_odds=1.30,
                selected_model_edge=-0.04,
                replacement_probability=0.68,
                replacement_decimal_odds=1.55,
                replacement_model_edge=0.03,
                profit_loss_delta=2.4,
            ),
            _item(
                "item_b",
                selected_probability=0.76,
                selected_decimal_odds=1.32,
                selected_model_edge=-0.03,
                replacement_probability=0.69,
                replacement_decimal_odds=1.58,
                replacement_model_edge=0.04,
                profit_loss_delta=1.8,
            ),
            _item(
                "item_c",
                selected_probability=0.73,
                selected_decimal_odds=1.31,
                selected_model_edge=-0.05,
                replacement_probability=0.67,
                replacement_decimal_odds=1.56,
                replacement_model_edge=0.03,
                profit_loss_delta=0.7,
            ),
        ]
    )

    report = build_historical_marginal_signal_group_report(
        audit_report,
        options=HistoricalMarginalSignalGroupOptions(
            min_sample_size=3,
            min_improvement_rate=0.60,
            max_harm_rate=0.10,
            min_average_profit_loss_delta=0.10,
        ),
    )

    group = next(
        group
        for group in report.groups
        if group.group_key == "selected_probability_band:high"
    )
    assert group.decision == "profile_candidate"
    assert group.improvement_count == 3
    assert group.harm_count == 0
    assert group.average_profit_loss_delta == 1.6333333333333335
    assert report.profile_candidate_count > 0
    assert report.profile_candidates[0].average_profit_loss_delta is not None


def test_marginal_signal_groups_put_positive_but_risky_groups_on_watchlist() -> None:
    audit_report = _audit_report(
        [
            _item("item_a", profit_loss_delta=2.0),
            _item("item_b", profit_loss_delta=1.0),
            _item("item_c", profit_loss_delta=-0.2),
        ]
    )

    report = build_historical_marginal_signal_group_report(
        audit_report,
        options=HistoricalMarginalSignalGroupOptions(
            min_sample_size=3,
            min_improvement_rate=0.60,
            max_harm_rate=0.20,
            min_average_profit_loss_delta=0.0,
        ),
    )

    group = next(
        group
        for group in report.groups
        if group.group_key == "selected_probability_band:high"
    )
    assert group.decision == "watchlist"
    assert "harm_rate_above_threshold" in group.decision_reasons
    assert report.watchlist_count > 0


def test_marginal_signal_groups_cli_options_and_loader(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    audit_report = _audit_report([_item("item_a", profit_loss_delta=1.0)])
    audit_path.write_text(f"{audit_report.model_dump_json(indent=2)}\n", encoding="utf-8")

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--output-path",
            str(tmp_path / "groups.json"),
            "--min-sample-size",
            "5",
            "--min-improvement-rate",
            "0.7",
            "--max-harm-rate",
            "0.2",
            "--min-average-profit-loss-delta",
            "0.5",
            "--min-average-hit-probability-delta",
            "-0.02",
            "--min-replacement-hit-probability-delta",
            "0.0",
            "--no-profile-groups",
        ]
    )
    options = _options_from_args(args)
    loaded = load_historical_candidate_marginal_audit_report(audit_path)

    assert loaded.report_key == audit_report.report_key
    assert options.min_sample_size == 5
    assert options.min_improvement_rate == 0.7
    assert options.max_harm_rate == 0.2
    assert options.min_average_profit_loss_delta == 0.5
    assert options.min_average_hit_probability_delta == -0.02
    assert options.min_replacement_hit_probability_delta == 0.0
    assert options.include_profile_groups is False


def test_marginal_signal_groups_can_filter_to_accuracy_preserving_replacements() -> None:
    audit_report = _audit_report(
        [
            _item(
                "item_a",
                profit_loss_delta=1.0,
                hit_probability_delta=-0.02,
            ),
            _item(
                "item_b",
                profit_loss_delta=-0.4,
                hit_probability_delta=0.01,
            ),
        ]
    )

    report = build_historical_marginal_signal_group_report(
        audit_report,
        options=HistoricalMarginalSignalGroupOptions(
            min_sample_size=1,
            min_improvement_rate=0.50,
            max_harm_rate=0.30,
            min_average_profit_loss_delta=0.0,
            min_average_hit_probability_delta=0.0,
            min_replacement_hit_probability_delta=0.0,
        ),
    )

    assert report.source_model_top_replacement_count == 2
    assert report.evaluated_replacement_count == 1
    assert report.filtered_replacement_count == 1
    group = next(
        group
        for group in report.groups
        if group.group_key == "selected_probability_band:high"
    )
    assert group.decision == "rejected"
    assert group.harm_count == 1
    assert "average_profit_loss_delta_below_threshold" in group.decision_reasons


def _audit_report(
    items: list[HistoricalCandidateMarginalAuditItem],
) -> HistoricalCandidateMarginalAuditReport:
    return HistoricalCandidateMarginalAuditReport(
        report_key="unit-test-marginal-audit",
        status="generated",
        slice_count=1,
        competition_count=1,
        final_answer_count=1,
        selected_leg_count=len(items),
        missed_leg_count=sum(1 for item in items if not item.leg_actual_hit),
        replacement_simulation_count=len(items),
        actual_replacement_opportunity_count=sum(
            1
            for item in items
            if item.model_top_replacement is not None
            and item.model_top_replacement.profit_loss_delta > 0
        ),
        model_top_replacement_count=len(items),
        model_top_actual_improvement_count=sum(
            1
            for item in items
            if item.model_top_replacement is not None
            and item.model_top_replacement.profit_loss_delta > 0
        ),
        model_top_actual_harm_count=sum(
            1
            for item in items
            if item.model_top_replacement is not None
            and item.model_top_replacement.profit_loss_delta < 0
        ),
        items=items,
    )


def _item(
    item_key: str,
    *,
    selected_probability: float = 0.74,
    selected_decimal_odds: float = 1.30,
    selected_model_edge: float = -0.04,
    replacement_probability: float = 0.68,
    replacement_decimal_odds: float = 1.55,
    replacement_model_edge: float = 0.03,
    profit_loss_delta: float,
    hit_probability_delta: float = -0.03,
) -> HistoricalCandidateMarginalAuditItem:
    replacement = HistoricalCandidateReplacementSimulation(
        replacement_rank=1,
        replacement_fixture_id=f"{item_key}_replacement",
        replacement_market_type="1x2",
        replacement_outcome="home_win",
        replacement_probability=replacement_probability,
        replacement_decimal_odds=replacement_decimal_odds,
        replacement_model_edge=replacement_model_edge,
        replacement_score=0.82,
        replacement_quality_score=0.80,
        replacement_leg_actual_hit=profit_loss_delta > 0,
        simulated_actual_hit=profit_loss_delta > 0,
        simulated_actual_return=4.0 + profit_loss_delta,
        simulated_profit_loss=profit_loss_delta,
        simulated_hit_probability=0.64,
        simulated_roi=0.15,
        simulated_risk_score=0.36,
        actual_return_delta=profit_loss_delta,
        profit_loss_delta=profit_loss_delta,
        hit_probability_delta=hit_probability_delta,
        roi_delta=0.05,
        risk_score_delta=0.02,
        decision="actual_improved" if profit_loss_delta > 0 else "actual_regressed",
    )
    return HistoricalCandidateMarginalAuditItem(
        item_key=item_key,
        slice_id="unit_slice",
        competition_id="TEST",
        final_answer_scenario_key="2x1:single",
        pass_type="2x1",
        mode="single",
        final_answer_actual_hit=False,
        selected_fixture_id=f"{item_key}_selected",
        selected_market_type="1x2",
        selected_outcome="home_win",
        selected_probability=selected_probability,
        selected_decimal_odds=selected_decimal_odds,
        selected_model_edge=selected_model_edge,
        selected_score=0.78,
        selected_reason_codes=[],
        leg_actual_hit=False,
        original_actual_return=0.0,
        original_profit_loss=-2.0,
        original_hit_probability=0.67,
        original_roi=-1.0,
        original_risk_score=0.33,
        replacement_count=1,
        model_top_replacement=replacement,
        actual_best_replacement=replacement,
        replacement_candidates=[replacement],
    )
