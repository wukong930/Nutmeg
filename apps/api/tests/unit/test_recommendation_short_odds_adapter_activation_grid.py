from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.short_odds_adapter_activation_grid import (
    ShortOddsAdapterActivationGridOptions,
    build_short_odds_adapter_activation_grid_report,
    load_short_odds_adapter_activation_grid_report,
    main,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsRuntimeReplacementRule,
    ShortOddsRuntimeRuleSet,
)


def test_activation_grid_accepts_relaxed_no_harm_threshold_candidate() -> None:
    report = build_short_odds_adapter_activation_grid_report(
        _audit_report(
            [
                _audit_item(
                    suffix="a",
                    competition_id="FRA_LIGUE_2",
                    replacement_probability=0.53,
                    replacement_decimal_odds=1.70,
                    replacement_hit=True,
                    replacement_profit_loss=1.40,
                ),
                _audit_item(
                    suffix="b",
                    competition_id="FRA_LIGUE_2",
                    replacement_probability=0.53,
                    replacement_decimal_odds=1.70,
                    replacement_hit=True,
                    replacement_profit_loss=1.40,
                ),
            ]
        ),
        rule_set=_rule_set(allowed_competition_ids=["EPL"]),
        options=ShortOddsAdapterActivationGridOptions(
            min_replacement_probability_values=(0.55, 0.50),
            max_replacement_decimal_odds_values=(1.75,),
            min_candidate_hit_probability_delta_vs_model_top_values=(-0.015, -0.05),
            min_candidate_hit_probability_delta_vs_original_values=(-0.05,),
            min_changed_final_answer_count=2,
            min_average_hit_probability_delta_vs_original=-0.05,
        ),
    )

    assert report.status == "accepted_candidate_found"
    assert report.accepted_count == 1
    assert report.rejected_count == 3
    assert report.best_candidate is not None
    assert report.best_candidate.min_replacement_probability == 0.50
    assert report.best_candidate.min_candidate_hit_probability_delta_vs_model_top == (
        -0.05
    )
    assert report.best_candidate.changed_final_answer_count == 2
    assert report.best_candidate.final_answer_hit_rate_delta == 1.0
    assert report.best_candidate.profit_loss_delta == 6.8
    assert report.best_candidate.harm_count_vs_original == 0
    assert report.best_candidate.changed_competition_counts == {"FRA_LIGUE_2": 2}
    assert report.public_response_changed is False
    assert report.production_recommendation_changed is False


def test_activation_grid_rejects_candidate_that_harms_original_profit_loss() -> None:
    report = build_short_odds_adapter_activation_grid_report(
        _audit_report(
            [
                _audit_item(
                    suffix="a",
                    competition_id="FRA_LIGUE_2",
                    replacement_probability=0.53,
                    replacement_decimal_odds=1.70,
                    replacement_hit=False,
                    replacement_profit_loss=-2.20,
                )
            ]
        ),
        rule_set=_rule_set(allowed_competition_ids=["FRA_LIGUE_2"]),
        options=ShortOddsAdapterActivationGridOptions(
            min_replacement_probability_values=(0.50,),
            max_replacement_decimal_odds_values=(1.75,),
            min_candidate_hit_probability_delta_vs_model_top_values=(-0.05,),
            min_candidate_hit_probability_delta_vs_original_values=(-0.05,),
            min_changed_final_answer_count=1,
        ),
    )

    assert report.status == "no_accepted_candidate"
    assert report.accepted_count == 0
    assert report.candidate_count == 1
    candidate = report.candidates[0]
    assert candidate.status == "rejected"
    assert candidate.changed_final_answer_count == 1
    assert candidate.profit_loss_harm_count_vs_original == 1
    assert "profit_loss_delta" in candidate.failed_checks
    assert "harm_count_vs_original" in candidate.failed_checks


def test_activation_grid_cli_writes_report(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    rule_path = tmp_path / "rules.json"
    output_path = tmp_path / "activation_grid.json"
    audit_path.write_text(
        _audit_report(
            [
                _audit_item(
                    suffix="a",
                    competition_id="FRA_LIGUE_2",
                    replacement_probability=0.53,
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
            "--min-replacement-probability-values",
            "0.55,0.50",
            "--max-replacement-decimal-odds-values",
            "1.75",
            "--min-candidate-hit-probability-delta-vs-model-top-values=-0.015,-0.05",
            "--min-candidate-hit-probability-delta-vs-original-values=-0.05",
            "--min-changed-final-answer-count",
            "1",
            "--min-average-hit-probability-delta-vs-original",
            "-0.05",
        ]
    )

    saved = load_short_odds_adapter_activation_grid_report(output_path)
    assert saved.status == "accepted_candidate_found"
    assert saved.best_candidate is not None
    assert saved.best_candidate.changed_final_answer_count == 1


def _audit_report(
    items: list[HistoricalCandidateMarginalAuditItem],
) -> HistoricalCandidateMarginalAuditReport:
    return HistoricalCandidateMarginalAuditReport(
        report_key="historical_candidate_marginal_audit:test",
        status="generated",
        slice_count=len(items),
        competition_count=len({item.competition_id for item in items}),
        final_answer_count=len(items),
        selected_leg_count=len(items),
        missed_leg_count=len(items),
        replacement_simulation_count=sum(item.replacement_count for item in items),
        actual_replacement_opportunity_count=len(items),
        model_top_replacement_count=len(
            [item for item in items if item.model_top_replacement is not None]
        ),
        model_top_actual_improvement_count=0,
        model_top_actual_harm_count=0,
        items=items,
    )


def _audit_item(
    *,
    suffix: str,
    competition_id: str,
    replacement_probability: float,
    replacement_decimal_odds: float,
    replacement_hit: bool,
    replacement_profit_loss: float,
) -> HistoricalCandidateMarginalAuditItem:
    model_top = _replacement(
        replacement_rank=1,
        fixture_id=f"fixture_model_top_{suffix}",
        probability=0.57,
        decimal_odds=1.60,
        actual_hit=False,
        profit_loss=-2.0,
    )
    replacement = _replacement(
        replacement_rank=2,
        fixture_id=f"fixture_replacement_{suffix}",
        probability=replacement_probability,
        decimal_odds=replacement_decimal_odds,
        actual_hit=replacement_hit,
        profit_loss=replacement_profit_loss,
    )
    return HistoricalCandidateMarginalAuditItem(
        item_key=f"{competition_id}:item:{suffix}",
        slice_id=f"{competition_id}:slice:{suffix}",
        competition_id=competition_id,
        final_answer_scenario_key="1x1:single",
        pass_type="1x1",
        mode="single",
        final_answer_actual_hit=False,
        selected_fixture_id=f"fixture_selected_{suffix}",
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
    actual_return = 3.40 if actual_hit else 0.0
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
        simulated_actual_return=actual_return,
        simulated_profit_loss=profit_loss,
        simulated_hit_probability=probability,
        simulated_roi=profit_loss / 2.0,
        simulated_risk_score=0.35,
        actual_return_delta=actual_return,
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
