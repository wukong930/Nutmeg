from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.short_odds_adapter_activation_gap import (
    build_short_odds_adapter_activation_gap_report,
    load_short_odds_adapter_activation_gap_report,
    main,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsRuntimeReplacementRule,
    ShortOddsRuntimeRuleSet,
)


def test_activation_gap_finds_probe_candidate_when_allowlist_blocks_current_rule() -> None:
    report = build_short_odds_adapter_activation_gap_report(
        _audit_report(
            [
                _audit_item(
                    competition_id="FRA_LIGUE_2",
                    replacement_probability=0.56,
                    replacement_decimal_odds=1.70,
                    replacement_hit=True,
                    replacement_profit_loss=1.40,
                )
            ]
        ),
        rule_set=_rule_set(allowed_competition_ids=["EPL"]),
    )

    assert report.status == "activation_candidate_found"
    assert report.activation_candidate_found is True
    assert report.current_item_reason_counts == {"competition_not_allowed": 1}
    assert report.probe_qualified_item_count == 1
    assert report.probe_changed_final_answer_count == 1
    assert report.probe_final_answer_hit_rate_delta == 1.0
    assert report.probe_profit_loss_delta == 3.4
    assert report.probe_harm_count_vs_original == 0
    assert report.probe_changed_competition_counts == {"FRA_LIGUE_2": 1}
    assert report.public_response_changed is False
    assert report.production_recommendation_changed is False


def test_activation_gap_reports_constraint_blockers_without_probe_candidate() -> None:
    report = build_short_odds_adapter_activation_gap_report(
        _audit_report(
            [
                _audit_item(
                    competition_id="FRA_LIGUE_2",
                    replacement_probability=0.50,
                    replacement_decimal_odds=1.70,
                    replacement_hit=True,
                    replacement_profit_loss=1.40,
                )
            ]
        ),
        rule_set=_rule_set(allowed_competition_ids=["FRA_LIGUE_2"]),
    )

    assert report.status == "no_activation_candidate"
    assert report.activation_candidate_found is False
    assert report.current_qualified_item_count == 0
    assert report.current_candidate_reason_counts == {
        "replacement_probability_below_floor": 1,
        "same_as_model_top": 1,
    }
    assert report.probe_changed_final_answer_count == 0


def test_activation_gap_cli_writes_report(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    rule_path = tmp_path / "rules.json"
    output_path = tmp_path / "activation_gap.json"
    audit_path.write_text(
        _audit_report(
            [
                _audit_item(
                    competition_id="FRA_LIGUE_2",
                    replacement_probability=0.56,
                    replacement_decimal_odds=1.70,
                    replacement_hit=True,
                    replacement_profit_loss=1.40,
                )
            ]
        ).model_dump_json(),
        encoding="utf-8",
    )
    rule_path.write_text(
        _rule_set(allowed_competition_ids=["EPL"]).model_dump_json(),
        encoding="utf-8",
    )

    main(
        [
            "--audit-report",
            str(audit_path),
            "--rule-profile",
            str(rule_path),
            "--output-path",
            str(output_path),
        ]
    )

    saved = load_short_odds_adapter_activation_gap_report(output_path)
    assert saved.status == "activation_candidate_found"
    assert saved.probe_changed_final_answer_count == 1


def _audit_report(
    items: list[HistoricalCandidateMarginalAuditItem],
) -> HistoricalCandidateMarginalAuditReport:
    return HistoricalCandidateMarginalAuditReport(
        report_key="historical_candidate_marginal_audit:test",
        status="generated",
        slice_count=1,
        competition_count=len({item.competition_id for item in items}),
        final_answer_count=len(items),
        selected_leg_count=len(items),
        missed_leg_count=len(items),
        replacement_simulation_count=sum(item.replacement_count for item in items),
        actual_replacement_opportunity_count=1,
        model_top_replacement_count=len(
            [item for item in items if item.model_top_replacement is not None]
        ),
        model_top_actual_improvement_count=0,
        model_top_actual_harm_count=0,
        items=items,
    )


def _audit_item(
    *,
    competition_id: str,
    replacement_probability: float,
    replacement_decimal_odds: float,
    replacement_hit: bool,
    replacement_profit_loss: float,
) -> HistoricalCandidateMarginalAuditItem:
    model_top = _replacement(
        replacement_rank=1,
        fixture_id="fixture_model_top",
        probability=0.57,
        decimal_odds=1.60,
        actual_hit=False,
        profit_loss=-2.0,
    )
    replacement = _replacement(
        replacement_rank=2,
        fixture_id="fixture_replacement",
        probability=replacement_probability,
        decimal_odds=replacement_decimal_odds,
        actual_hit=replacement_hit,
        profit_loss=replacement_profit_loss,
    )
    return HistoricalCandidateMarginalAuditItem(
        item_key=f"{competition_id}:item",
        slice_id=f"{competition_id}:slice",
        competition_id=competition_id,
        final_answer_scenario_key="1x1:single",
        pass_type="1x1",
        mode="single",
        final_answer_actual_hit=False,
        selected_fixture_id="fixture_selected",
        selected_market_type="1x2",
        selected_outcome="home_win",
        selected_probability=0.58,
        selected_decimal_odds=1.55,
        selected_model_edge=-0.03,
        selected_score=0.70,
        leg_actual_hit=False,
        original_actual_return=0.0,
        original_profit_loss=-2.0,
        original_hit_probability=0.555,
        original_roi=-1.0,
        original_risk_score=0.40,
        replacement_count=2,
        model_top_replacement=model_top,
        actual_best_replacement=replacement,
        replacement_candidates=[model_top, replacement],
    )


def _replacement(
    *,
    replacement_rank: int,
    fixture_id: str,
    probability: float,
    decimal_odds: float,
    actual_hit: bool,
    profit_loss: float,
) -> HistoricalCandidateReplacementSimulation:
    return HistoricalCandidateReplacementSimulation(
        replacement_rank=replacement_rank,
        replacement_fixture_id=fixture_id,
        replacement_market_type="1x2",
        replacement_outcome="home_win",
        replacement_probability=probability,
        replacement_decimal_odds=decimal_odds,
        replacement_model_edge=-0.01,
        replacement_score=0.72,
        replacement_quality_score=0.70,
        replacement_leg_actual_hit=actual_hit,
        simulated_actual_hit=actual_hit,
        simulated_actual_return=3.40 if actual_hit else 0.0,
        simulated_profit_loss=profit_loss,
        simulated_hit_probability=probability,
        simulated_roi=profit_loss / 2.0,
        simulated_risk_score=0.35,
        actual_return_delta=(3.40 if actual_hit else 0.0),
        profit_loss_delta=profit_loss - (-2.0),
        hit_probability_delta=probability - 0.555,
        roi_delta=(profit_loss / 2.0) - (-1.0),
        risk_score_delta=-0.05,
        decision="actual_improved" if profit_loss > -2.0 else "actual_unchanged",
    )


def _rule_set(*, allowed_competition_ids: list[str]) -> ShortOddsRuntimeRuleSet:
    return ShortOddsRuntimeRuleSet(
        profile_version="short_odds_rule_test_v1",
        shadow_replay_enabled=True,
        rules=[
            ShortOddsRuntimeReplacementRule(
                rule_id="short_odds_final_answer_replacement_v1",
                profile_id="max_short_odds_within_deficit_v1",
                proposed_production_enabled=True,
                production_recommendation_changed=False,
                allowed_competition_ids=allowed_competition_ids,
                excluded_competition_ids=[],
                constraints_json={
                    "min_replacement_probability": 0.55,
                    "max_replacement_decimal_odds": 1.75,
                    "min_candidate_hit_probability_delta_vs_model_top": -0.015,
                    "max_candidate_hit_probability_delta_vs_model_top": 0.0,
                    "min_decimal_odds_delta_vs_model_top": 0.0,
                    "min_candidate_hit_probability_delta_vs_original": -0.025,
                    "max_harm_count_vs_original": 0,
                    "max_final_hit_harm_count_vs_original": 0,
                    "max_profit_loss_harm_count_vs_original": 0,
                },
            )
        ],
    )
