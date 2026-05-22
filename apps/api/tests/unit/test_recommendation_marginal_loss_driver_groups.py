from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.marginal_loss_driver_groups import (
    HistoricalMarginalLossDriverOptions,
    _options_from_args,
    _parse_args,
    build_historical_marginal_loss_driver_report,
    load_historical_candidate_marginal_audit_report,
)


def test_marginal_loss_driver_groups_promote_guard_candidate() -> None:
    audit_report = _audit_report(
        [
            _item("item_a", actual_best_delta=2.0, model_top_delta=0.6),
            _item("item_b", actual_best_delta=1.0, model_top_delta=0.3),
            _item(
                "item_c",
                actual_best_delta=0.0,
                model_top_delta=0.0,
                leg_actual_hit=True,
            ),
        ]
    )

    report = build_historical_marginal_loss_driver_report(
        audit_report,
        options=HistoricalMarginalLossDriverOptions(
            min_sample_size=3,
            min_miss_rate=0.50,
            min_actual_replacement_opportunity_rate=0.50,
            min_average_actual_best_profit_loss_delta=0.10,
        ),
    )

    group = next(
        group
        for group in report.groups
        if group.group_key == "selected_probability_band:high"
    )
    assert group.decision == "guard_candidate"
    assert group.missed_leg_count == 2
    assert group.actual_replacement_opportunity_count == 2
    assert group.average_actual_best_profit_loss_delta == 1.0
    assert report.guard_candidate_count > 0
    assert report.guard_candidates[0].average_actual_best_profit_loss_delta is not None


def test_marginal_loss_driver_groups_watchlist_when_model_top_harms_too_often() -> None:
    audit_report = _audit_report(
        [
            _item("item_a", actual_best_delta=2.0, model_top_delta=-0.6),
            _item("item_b", actual_best_delta=1.0, model_top_delta=-0.3),
            _item("item_c", actual_best_delta=1.5, model_top_delta=0.4),
        ]
    )

    report = build_historical_marginal_loss_driver_report(
        audit_report,
        options=HistoricalMarginalLossDriverOptions(
            min_sample_size=3,
            min_miss_rate=0.20,
            min_actual_replacement_opportunity_rate=0.50,
            min_average_actual_best_profit_loss_delta=0.0,
            max_model_top_harm_rate=0.30,
        ),
    )

    group = next(
        group
        for group in report.groups
        if group.group_key == "selected_probability_band:high"
    )
    assert group.decision == "watchlist"
    assert group.model_top_harm_count == 2
    assert "model_top_harm_rate_above_threshold" in group.decision_reasons
    assert report.watchlist_count > 0


def test_marginal_loss_driver_groups_reject_small_samples() -> None:
    audit_report = _audit_report(
        [_item("item_a", actual_best_delta=2.0, model_top_delta=1.0)]
    )

    report = build_historical_marginal_loss_driver_report(
        audit_report,
        options=HistoricalMarginalLossDriverOptions(min_sample_size=2),
    )

    group = next(
        group
        for group in report.groups
        if group.group_key == "selected_probability_band:high"
    )
    assert group.decision == "rejected"
    assert "sample_size_below_threshold" in group.decision_reasons


def test_marginal_loss_driver_groups_cli_options_and_loader(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    audit_report = _audit_report(
        [_item("item_a", actual_best_delta=2.0, model_top_delta=1.0)]
    )
    audit_path.write_text(f"{audit_report.model_dump_json(indent=2)}\n", encoding="utf-8")

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--output-path",
            str(tmp_path / "loss_drivers.json"),
            "--min-sample-size",
            "5",
            "--min-miss-rate",
            "0.40",
            "--min-actual-replacement-opportunity-rate",
            "0.60",
            "--min-average-actual-best-profit-loss-delta",
            "0.20",
            "--max-model-top-harm-rate",
            "0.25",
            "--no-profile-groups",
        ]
    )
    options = _options_from_args(args)
    loaded = load_historical_candidate_marginal_audit_report(audit_path)

    assert loaded.report_key == audit_report.report_key
    assert options.min_sample_size == 5
    assert options.min_miss_rate == 0.40
    assert options.min_actual_replacement_opportunity_rate == 0.60
    assert options.min_average_actual_best_profit_loss_delta == 0.20
    assert options.max_model_top_harm_rate == 0.25
    assert options.include_profile_groups is False


def _audit_report(
    items: list[HistoricalCandidateMarginalAuditItem],
) -> HistoricalCandidateMarginalAuditReport:
    model_top_replacements = [
        item.model_top_replacement
        for item in items
        if item.model_top_replacement is not None
    ]
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
            if item.actual_best_replacement is not None
            and item.actual_best_replacement.profit_loss_delta > 0
        ),
        model_top_replacement_count=len(model_top_replacements),
        model_top_actual_improvement_count=sum(
            1
            for replacement in model_top_replacements
            if replacement.profit_loss_delta > 0
        ),
        model_top_actual_harm_count=sum(
            1
            for replacement in model_top_replacements
            if replacement.profit_loss_delta < 0
        ),
        items=items,
    )


def _item(
    item_key: str,
    *,
    actual_best_delta: float,
    model_top_delta: float,
    selected_probability: float = 0.74,
    selected_decimal_odds: float = 1.30,
    selected_model_edge: float = -0.04,
    leg_actual_hit: bool = False,
) -> HistoricalCandidateMarginalAuditItem:
    actual_best = _replacement(
        item_key,
        suffix="actual_best",
        profit_loss_delta=actual_best_delta,
        hit_probability_delta=-0.01,
        rank=1,
    )
    model_top = _replacement(
        item_key,
        suffix="model_top",
        profit_loss_delta=model_top_delta,
        hit_probability_delta=-0.02,
        rank=1,
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
        leg_actual_hit=leg_actual_hit,
        original_actual_return=2.0 if leg_actual_hit else 0.0,
        original_profit_loss=0.5 if leg_actual_hit else -2.0,
        original_hit_probability=0.67,
        original_roi=0.25 if leg_actual_hit else -1.0,
        original_risk_score=0.33,
        replacement_count=2,
        model_top_replacement=model_top,
        actual_best_replacement=actual_best,
        replacement_candidates=[actual_best, model_top],
    )


def _replacement(
    item_key: str,
    *,
    suffix: str,
    profit_loss_delta: float,
    hit_probability_delta: float,
    rank: int,
) -> HistoricalCandidateReplacementSimulation:
    return HistoricalCandidateReplacementSimulation(
        replacement_rank=rank,
        replacement_fixture_id=f"{item_key}_{suffix}",
        replacement_market_type="1x2",
        replacement_outcome="away_win",
        replacement_probability=0.68,
        replacement_decimal_odds=1.55,
        replacement_model_edge=0.03,
        replacement_score=0.82,
        replacement_quality_score=0.80,
        replacement_leg_actual_hit=profit_loss_delta > 0,
        simulated_actual_hit=profit_loss_delta > 0,
        simulated_actual_return=max(0.0, 4.0 + profit_loss_delta),
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
