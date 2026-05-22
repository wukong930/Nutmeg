from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.short_odds_adapter_activation_grid import (
    ShortOddsAdapterActivationGridOptions,
    ShortOddsAdapterActivationGridReport,
    build_short_odds_adapter_activation_grid_report,
)
from nutmeg.recommendations.short_odds_adapter_activation_scope_search import (
    ShortOddsAdapterActivationScopeSearchOptions,
    build_short_odds_adapter_activation_scope_search_report,
    load_short_odds_adapter_activation_scope_search_report,
    main,
)
from nutmeg.recommendations.short_odds_replacement_rules import (
    ShortOddsRuntimeReplacementRule,
    ShortOddsRuntimeRuleSet,
)


def test_activation_scope_search_finds_stable_competition_scope() -> None:
    audit_report = _audit_report(
        [
            _audit_item(
                suffix="a1",
                competition_id="FRA_LIGUE_2",
                replacement_probability=0.53,
            ),
            _audit_item(
                suffix="a2",
                competition_id="FRA_LIGUE_2",
                replacement_probability=0.53,
            ),
            _audit_item(
                suffix="b1",
                competition_id="GER_2_BUNDESLIGA",
                replacement_probability=0.49,
            ),
        ]
    )
    rule_set = _rule_set(allowed_competition_ids=["EPL"])
    grid_report = _grid_report(audit_report, rule_set)

    report = build_short_odds_adapter_activation_scope_search_report(
        audit_report,
        rule_set=rule_set,
        grid_report=grid_report,
        options=_scope_options(),
    )

    assert report.status == "accepted_scope_found"
    assert report.accepted_scope_count >= 1
    assert report.best_scope is not None
    assert report.best_scope.status == "accepted"
    assert report.best_scope.scope_competition_ids == ["FRA_LIGUE_2"]
    assert report.best_scope.overall_changed_final_answer_count == 2
    assert report.best_scope.rolling_failed_fold_count == 0
    assert report.best_scope.overall_average_hit_probability_delta_vs_original == (
        -0.025000000000000022
    )


def test_activation_scope_search_cli_writes_report(tmp_path: Path) -> None:
    audit_report = _audit_report(
        [
            _audit_item(
                suffix="a1",
                competition_id="FRA_LIGUE_2",
                replacement_probability=0.53,
            ),
            _audit_item(
                suffix="a2",
                competition_id="FRA_LIGUE_2",
                replacement_probability=0.53,
            ),
            _audit_item(
                suffix="b1",
                competition_id="GER_2_BUNDESLIGA",
                replacement_probability=0.49,
            ),
        ]
    )
    rule_set = _rule_set(allowed_competition_ids=["EPL"])
    grid_report = _grid_report(audit_report, rule_set)
    audit_path = tmp_path / "audit.json"
    rule_path = tmp_path / "rules.json"
    grid_path = tmp_path / "grid.json"
    output_path = tmp_path / "scope_search.json"
    audit_path.write_text(audit_report.model_dump_json(), encoding="utf-8")
    rule_path.write_text(rule_set.model_dump_json(), encoding="utf-8")
    grid_path.write_text(grid_report.model_dump_json(), encoding="utf-8")

    main(
        [
            "--audit-report",
            str(audit_path),
            "--rule-profile",
            str(rule_path),
            "--grid-report",
            str(grid_path),
            "--output-path",
            str(output_path),
            "--max-source-candidate-count",
            "1",
            "--min-overall-final-answer-count",
            "1",
            "--min-overall-changed-final-answer-count",
            "2",
            "--min-overall-average-hit-probability-delta-vs-original=-0.05",
            "--min-fold-average-hit-probability-delta-vs-original=-0.05",
            "--min-active-competition-fold-count",
            "1",
            "--min-active-season-fold-count",
            "1",
            "--min-active-rolling-fold-count",
            "1",
            "--rolling-window-final-answer-count",
            "1",
            "--rolling-window-step",
            "1",
        ]
    )

    saved = load_short_odds_adapter_activation_scope_search_report(output_path)
    assert saved.status == "accepted_scope_found"
    assert saved.best_scope is not None
    assert saved.best_scope.scope_competition_ids == ["FRA_LIGUE_2"]


def _grid_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    rule_set: ShortOddsRuntimeRuleSet,
) -> ShortOddsAdapterActivationGridReport:
    return build_short_odds_adapter_activation_grid_report(
        audit_report,
        rule_set=rule_set,
        options=ShortOddsAdapterActivationGridOptions(
            min_replacement_probability_values=(0.48,),
            max_replacement_decimal_odds_values=(1.75,),
            min_candidate_hit_probability_delta_vs_model_top_values=(-0.08,),
            min_candidate_hit_probability_delta_vs_original_values=(-0.08,),
            min_changed_final_answer_count=3,
            min_average_hit_probability_delta_vs_original=-0.08,
        ),
    )


def _scope_options() -> ShortOddsAdapterActivationScopeSearchOptions:
    return ShortOddsAdapterActivationScopeSearchOptions(
        max_source_candidate_count=1,
        min_overall_final_answer_count=1,
        min_overall_changed_final_answer_count=2,
        min_overall_average_hit_probability_delta_vs_original=-0.05,
        min_fold_average_hit_probability_delta_vs_original=-0.05,
        min_active_competition_fold_count=1,
        min_active_season_fold_count=1,
        min_active_rolling_fold_count=1,
        rolling_window_final_answer_count=1,
        rolling_window_step=1,
    )


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
) -> HistoricalCandidateMarginalAuditItem:
    model_top = _replacement(
        replacement_rank=1,
        fixture_id=f"fixture_model_top_{suffix}",
        probability=0.57,
        actual_hit=False,
        profit_loss=-2.0,
    )
    replacement = _replacement(
        replacement_rank=2,
        fixture_id=f"fixture_replacement_{suffix}",
        probability=replacement_probability,
        actual_hit=True,
        profit_loss=1.40,
    )
    return HistoricalCandidateMarginalAuditItem(
        item_key=f"{competition_id}:item:{suffix}",
        slice_id=f"{competition_id}_2021_2022_slice_{suffix}",
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
        replacement_decimal_odds=1.70 if replacement_rank > 1 else 1.60,
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
