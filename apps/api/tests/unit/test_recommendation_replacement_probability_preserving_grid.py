from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_final_answer_probability_preserving_grid import (
    HistoricalReplacementProbabilityPreservingGridOptions,
    build_historical_replacement_probability_preserving_grid_report,
    load_historical_replacement_probability_preserving_grid_report,
    main,
)
from nutmeg.recommendations.replacement_short_odds_competition_gate import (
    HistoricalShortOddsCompetitionGateReport,
    HistoricalShortOddsCompetitionGateSet,
)


def test_probability_preserving_grid_finds_original_safe_candidate() -> None:
    report = build_historical_replacement_probability_preserving_grid_report(
        _audit_report(),
        _competition_gate_report(),
        options=_grid_options(),
    )

    assert report.status == "accepted_candidate_found"
    assert report.accepted_candidate_found is True
    assert report.accepted_count >= 1
    assert report.best_candidate is not None
    assert report.best_candidate.status == "accepted"
    assert report.best_candidate.harm_count_vs_original == 0
    assert report.best_candidate.average_hit_probability_delta_vs_original is not None
    assert report.best_candidate.average_hit_probability_delta_vs_original >= -0.02
    assert report.best_candidate.original_safe_excluded_count == 1
    assert report.best_candidate.original_safe_exclusion_counts_json == {
        "item_hit_probability_delta_vs_original_below_threshold": 1,
        "original_hit_harm_excluded": 1,
    }


def test_probability_preserving_grid_cli_writes_report(tmp_path: Path) -> None:
    audit_report = _audit_report()
    competition_gate_report = _competition_gate_report()
    audit_path = tmp_path / "audit.json"
    competition_gate_path = tmp_path / "competition_gate.json"
    output_path = tmp_path / "grid.json"
    audit_path.write_text(f"{audit_report.model_dump_json(indent=2)}\n", encoding="utf-8")
    competition_gate_path.write_text(
        f"{competition_gate_report.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            "--audit-report",
            str(audit_path),
            "--competition-gate-report",
            str(competition_gate_path),
            "--output-path",
            str(output_path),
            "--profile-id",
            "max_model_edge_within_deficit_v1",
            "--ready-competitions",
            "FRA_LIGUE_2",
            "--selection-rules",
            "highest_candidate_hit_probability",
            "--shadow-selection-rules",
            "max_model_edge_within_deficit",
            "--min-replacement-probability-values",
            "0.35",
            "--min-replacement-decimal-odds",
            "1.75",
            "--max-replacement-decimal-odds-values",
            "2.30",
            "--min-candidate-hit-probability-delta-vs-model-top-values=-1.0",
            "--min-item-hit-probability-delta-vs-original-values=-0.02,0.0",
            "--min-changed-final-answer-count",
            "1",
            "--min-average-hit-probability-delta-vs-original=-0.02",
        ]
    )

    saved = load_historical_replacement_probability_preserving_grid_report(output_path)
    assert saved.accepted_candidate_found is True
    assert saved.best_candidate_key is not None


def _grid_options() -> HistoricalReplacementProbabilityPreservingGridOptions:
    return HistoricalReplacementProbabilityPreservingGridOptions(
        profile_id="max_model_edge_within_deficit_v1",
        ready_competition_ids=("FRA_LIGUE_2",),
        selection_rules=("highest_candidate_hit_probability",),
        shadow_selection_rules=("max_model_edge_within_deficit",),
        min_replacement_probability_values=(0.35,),
        min_replacement_decimal_odds=1.75,
        max_replacement_decimal_odds_values=(2.30,),
        min_candidate_hit_probability_delta_vs_model_top_values=(-1.0,),
        min_item_hit_probability_delta_vs_original_values=(-0.02, 0.0),
        min_changed_final_answer_count=1,
        min_average_hit_probability_delta_vs_original=-0.02,
    )


def _audit_report() -> HistoricalCandidateMarginalAuditReport:
    items = [
        _item(
            "unsafe_item",
            final_answer_actual_hit=True,
            original_profit_loss=1.40,
            original_hit_probability=0.65,
            model_top=_replacement(
                rank=1,
                fixture_id="unsafe_model_top",
                probability=0.65,
                decimal_odds=1.70,
                model_edge=0.00,
                simulated_hit_probability=0.66,
                simulated_actual_hit=True,
                simulated_profit_loss=1.40,
                profit_loss_delta=0.0,
            ),
            actual_best=_replacement(
                rank=2,
                fixture_id="unsafe_candidate",
                probability=0.43,
                decimal_odds=1.90,
                model_edge=0.08,
                simulated_hit_probability=0.61,
                simulated_actual_hit=False,
                simulated_profit_loss=-2.0,
                profit_loss_delta=3.0,
            ),
        ),
        _item(
            "safe_item",
            original_hit_probability=0.58,
            model_top=_replacement(
                rank=1,
                fixture_id="safe_model_top",
                probability=0.66,
                decimal_odds=1.68,
                model_edge=0.00,
                simulated_hit_probability=0.65,
                profit_loss_delta=0.0,
            ),
            actual_best=_replacement(
                rank=2,
                fixture_id="safe_candidate",
                probability=0.42,
                decimal_odds=1.88,
                model_edge=0.07,
                simulated_hit_probability=0.59,
                simulated_actual_hit=True,
                simulated_profit_loss=1.2,
                profit_loss_delta=2.5,
            ),
        ),
    ]
    return HistoricalCandidateMarginalAuditReport(
        report_key="historical_candidate_marginal_audit:test",
        status="generated",
        slice_count=2,
        competition_count=1,
        final_answer_count=2,
        selected_leg_count=2,
        missed_leg_count=1,
        replacement_simulation_count=4,
        actual_replacement_opportunity_count=2,
        model_top_replacement_count=2,
        model_top_actual_improvement_count=0,
        model_top_actual_harm_count=0,
        items=items,
    )


def _competition_gate_report() -> HistoricalShortOddsCompetitionGateReport:
    profile_set = HistoricalShortOddsCompetitionGateSet(
        profile_id="max_model_edge_within_deficit_v1",
        decision="final_answer_gate_ready",
        ready_competition_ids=["FRA_LIGUE_2"],
        evaluated_item_count=2,
        changed_count_vs_model_top=2,
        simulated_actual_hit_delta_count_vs_model_top=1,
        replacement_leg_hit_delta_count_vs_model_top=1,
        improvement_count_vs_model_top=1,
        harm_count_vs_model_top=0,
        selected_actual_best_count=1,
    )
    return HistoricalShortOddsCompetitionGateReport(
        report_key="historical_short_odds_competition_gate:test",
        status="generated",
        source_shadow_report_key="historical_short_odds_shadow_rerank:test",
        profile_count=1,
        candidate_count=1,
        final_answer_gate_ready_count=1,
        holdout_watchlist_count=0,
        isolated_rejected_count=0,
        ready_competition_ids=["FRA_LIGUE_2"],
        isolated_competition_ids=[],
        production_recommendation_changed=False,
        profile_sets=[profile_set],
        best_profile_set=profile_set,
    )


def _item(
    item_key: str,
    *,
    final_answer_actual_hit: bool = False,
    original_profit_loss: float = -2.0,
    original_hit_probability: float,
    model_top: HistoricalCandidateReplacementSimulation,
    actual_best: HistoricalCandidateReplacementSimulation,
) -> HistoricalCandidateMarginalAuditItem:
    return HistoricalCandidateMarginalAuditItem(
        item_key=item_key,
        slice_id="unit_slice",
        competition_id="FRA_LIGUE_2",
        final_answer_scenario_key="1x1:single",
        pass_type="1x1",
        mode="single",
        final_answer_actual_hit=final_answer_actual_hit,
        selected_fixture_id=f"{item_key}_selected",
        selected_market_type="1x2",
        selected_outcome="home_win",
        selected_probability=0.58,
        selected_decimal_odds=1.55,
        selected_model_edge=-0.03,
        selected_score=0.70,
        leg_actual_hit=final_answer_actual_hit,
        original_actual_return=max(original_profit_loss + 2.0, 0.0),
        original_profit_loss=original_profit_loss,
        original_hit_probability=original_hit_probability,
        original_roi=original_profit_loss / 2.0,
        original_risk_score=1.0 - original_hit_probability,
        replacement_count=2,
        model_top_replacement=model_top,
        actual_best_replacement=actual_best,
        replacement_candidates=[model_top, actual_best],
    )


def _replacement(
    *,
    rank: int,
    fixture_id: str,
    probability: float,
    decimal_odds: float,
    model_edge: float,
    simulated_hit_probability: float,
    simulated_actual_hit: bool = False,
    simulated_profit_loss: float = -2.0,
    profit_loss_delta: float,
) -> HistoricalCandidateReplacementSimulation:
    return HistoricalCandidateReplacementSimulation(
        replacement_rank=rank,
        replacement_fixture_id=fixture_id,
        replacement_market_type="1x2",
        replacement_outcome="home_win",
        replacement_probability=probability,
        replacement_decimal_odds=decimal_odds,
        replacement_model_edge=model_edge,
        replacement_score=0.72,
        replacement_quality_score=0.70,
        replacement_leg_actual_hit=simulated_actual_hit,
        simulated_actual_hit=simulated_actual_hit,
        simulated_actual_return=max(simulated_profit_loss + 2.0, 0.0),
        simulated_profit_loss=simulated_profit_loss,
        simulated_hit_probability=simulated_hit_probability,
        simulated_roi=simulated_profit_loss / 2.0,
        simulated_risk_score=1.0 - simulated_hit_probability,
        actual_return_delta=profit_loss_delta,
        profit_loss_delta=profit_loss_delta,
        hit_probability_delta=simulated_hit_probability - 0.58,
        roi_delta=simulated_profit_loss / 2.0,
        risk_score_delta=0.0,
        decision="actual_improved" if profit_loss_delta > 0 else "actual_unchanged",
    )
