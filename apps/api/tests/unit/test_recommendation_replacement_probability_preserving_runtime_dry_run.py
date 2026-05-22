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
)
from nutmeg.recommendations.replacement_probability_preserving_admission import (
    HistoricalReplacementProbabilityPreservingAdmissionOptions,
    build_historical_replacement_probability_preserving_admission_report,
)
from nutmeg.recommendations.replacement_probability_preserving_runtime_dry_run import (
    HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions,
    _options_from_args,
    _parse_args,
    build_historical_replacement_probability_preserving_runtime_dry_run_report,
    load_historical_replacement_probability_preserving_runtime_dry_run_report,
    main,
)
from nutmeg.recommendations.replacement_probability_preserving_surface_replay import (
    HistoricalReplacementProbabilityPreservingSurfaceReplayOptions,
    build_historical_replacement_probability_preserving_surface_replay_report,
)
from nutmeg.recommendations.replacement_short_odds_competition_gate import (
    HistoricalShortOddsCompetitionGateReport,
    HistoricalShortOddsCompetitionGateSet,
)


def test_probability_preserving_runtime_dry_run_passes_shadow_only() -> None:
    audit_report = _audit_report()
    competition_gate_report = _competition_gate_report()
    grid_report = _grid_report(audit_report, competition_gate_report)
    surface_report = _surface_report(audit_report, competition_gate_report, grid_report)
    admission_report = _admission_report(
        audit_report,
        competition_gate_report,
        grid_report,
    )

    report = build_historical_replacement_probability_preserving_runtime_dry_run_report(
        audit_report,
        grid_report,
        surface_report,
        admission_report,
        options=HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions(
            min_final_answer_count=2,
            min_changed_final_answer_count=2,
            min_active_surface_count=3,
            min_active_competition_fold_count=1,
            min_active_season_fold_count=2,
            min_active_rolling_fold_count=2,
        ),
    )

    assert report.status == "runtime_dry_run_passed"
    assert report.shadow_runtime_candidate_allowed is True
    assert report.production_recommendation_allowed is False
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False
    assert report.changed_final_answer_count == 2
    assert report.final_answer_hit_delta_count == 1
    assert report.profit_loss_delta > 0
    assert report.harm_count_vs_original == 0
    assert report.generated_runtime_shadow_replay_report_key is not None
    assert report.runtime_proposal_profile_set_json["dry_run_only"] is True
    assert all(check.status == "passed" for check in report.checks)


def test_probability_preserving_runtime_dry_run_watchlists_failed_admission() -> None:
    audit_report = _audit_report()
    competition_gate_report = _competition_gate_report()
    grid_report = _grid_report(audit_report, competition_gate_report)
    surface_report = _surface_report(audit_report, competition_gate_report, grid_report)
    admission_report = _admission_report(
        audit_report,
        competition_gate_report,
        grid_report,
        min_active_season_fold_count=3,
    )

    report = build_historical_replacement_probability_preserving_runtime_dry_run_report(
        audit_report,
        grid_report,
        surface_report,
        admission_report,
        options=HistoricalReplacementProbabilityPreservingRuntimeDryRunOptions(
            min_final_answer_count=2,
            min_changed_final_answer_count=2,
            min_active_surface_count=3,
            min_active_competition_fold_count=1,
            min_active_season_fold_count=3,
            min_active_rolling_fold_count=2,
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "runtime_dry_run_watchlist"
    assert report.shadow_runtime_candidate_allowed is False
    assert "admission_status" in failed_checks
    assert "active_season_fold_count" in failed_checks
    assert report.production_recommendation_allowed is False


def test_probability_preserving_runtime_dry_run_cli_options_and_main(
    tmp_path: Path,
) -> None:
    audit_report = _audit_report()
    competition_gate_report = _competition_gate_report()
    grid_report = _grid_report(audit_report, competition_gate_report)
    surface_report = _surface_report(audit_report, competition_gate_report, grid_report)
    admission_report = _admission_report(
        audit_report,
        competition_gate_report,
        grid_report,
    )
    audit_path = tmp_path / "audit.json"
    grid_path = tmp_path / "grid.json"
    surface_path = tmp_path / "surface.json"
    admission_path = tmp_path / "admission.json"
    output_path = tmp_path / "runtime_dry_run.json"
    audit_path.write_text(f"{audit_report.model_dump_json(indent=2)}\n", encoding="utf-8")
    grid_path.write_text(f"{grid_report.model_dump_json(indent=2)}\n", encoding="utf-8")
    surface_path.write_text(
        f"{surface_report.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    admission_path.write_text(
        f"{admission_report.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--grid-report",
            str(grid_path),
            "--surface-replay-report",
            str(surface_path),
            "--admission-report",
            str(admission_path),
            "--output-path",
            str(output_path),
            "--candidate-key",
            grid_report.best_candidate_key or "",
            "--min-final-answer-count",
            "2",
            "--min-changed-final-answer-count",
            "2",
            "--min-final-answer-hit-delta-count",
            "0",
            "--min-average-hit-probability-delta-vs-original=-0.02",
            "--min-active-surface-count",
            "3",
            "--min-active-competition-fold-count",
            "1",
            "--min-active-season-fold-count",
            "2",
            "--min-active-rolling-fold-count",
            "2",
            "--allow-public-response-change",
            "--max-report-items",
            "10",
        ]
    )
    options = _options_from_args(args)

    assert options.candidate_key == grid_report.best_candidate_key
    assert options.min_changed_final_answer_count == 2
    assert options.require_no_public_response_change is False
    assert options.max_report_items == 10

    main(
        [
            "--audit-report",
            str(audit_path),
            "--grid-report",
            str(grid_path),
            "--surface-replay-report",
            str(surface_path),
            "--admission-report",
            str(admission_path),
            "--output-path",
            str(output_path),
            "--min-final-answer-count",
            "2",
            "--min-changed-final-answer-count",
            "2",
            "--min-active-surface-count",
            "3",
            "--min-active-competition-fold-count",
            "1",
            "--min-active-season-fold-count",
            "2",
            "--min-active-rolling-fold-count",
            "2",
        ]
    )

    saved = load_historical_replacement_probability_preserving_runtime_dry_run_report(
        output_path
    )
    assert saved.status == "runtime_dry_run_passed"
    assert saved.production_recommendation_allowed is False


def _grid_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    competition_gate_report: HistoricalShortOddsCompetitionGateReport,
):
    return build_historical_replacement_probability_preserving_grid_report(
        audit_report,
        competition_gate_report,
        options=HistoricalReplacementProbabilityPreservingGridOptions(
            profile_id="max_model_edge_within_deficit_v1",
            ready_competition_ids=("FRA_LIGUE_2",),
            selection_rules=("highest_candidate_hit_probability",),
            shadow_selection_rules=("probability_preserving_model_edge",),
            min_replacement_probability_values=(0.45,),
            min_replacement_decimal_odds=1.75,
            max_replacement_decimal_odds_values=(2.10,),
            min_candidate_hit_probability_delta_vs_model_top_values=(-0.02,),
            max_candidate_hit_probability_delta_vs_model_top=0.0,
            min_item_hit_probability_delta_vs_original_values=(-0.02,),
            min_changed_final_answer_count=2,
            min_average_hit_probability_delta_vs_original=-0.02,
            max_candidate_count=1,
        ),
    )


def _surface_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    competition_gate_report: HistoricalShortOddsCompetitionGateReport,
    grid_report,
):
    return build_historical_replacement_probability_preserving_surface_replay_report(
        audit_report,
        competition_gate_report,
        grid_report,
        options=HistoricalReplacementProbabilityPreservingSurfaceReplayOptions(
            min_active_surface_count=3,
            min_all_audit_changed_final_answer_count=2,
            min_non_source_changed_final_answer_count=0,
            min_changed_final_answer_count_without_small_sample_warning=2,
        ),
    )


def _admission_report(
    audit_report: HistoricalCandidateMarginalAuditReport,
    competition_gate_report: HistoricalShortOddsCompetitionGateReport,
    grid_report,
    *,
    min_active_season_fold_count: int = 2,
):
    return build_historical_replacement_probability_preserving_admission_report(
        audit_report,
        competition_gate_report,
        grid_report,
        options=HistoricalReplacementProbabilityPreservingAdmissionOptions(
            min_overall_final_answer_count=2,
            min_overall_changed_final_answer_count=2,
            min_active_competition_fold_count=1,
            min_active_season_fold_count=min_active_season_fold_count,
            min_active_rolling_fold_count=2,
            rolling_window_final_answer_count=1,
            rolling_window_step=1,
            min_changed_final_answer_count_without_small_sample_warning=2,
        ),
    )


def _audit_report() -> HistoricalCandidateMarginalAuditReport:
    items = [
        _item("2021_2022", original_hit=False, replacement_profit=1.10),
        _item("2022_2023", original_hit=True, replacement_profit=1.20),
    ]
    return HistoricalCandidateMarginalAuditReport(
        report_key="historical_candidate_marginal_audit:runtime_dry_run_test",
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
        improvement_count_vs_model_top=2,
        harm_count_vs_model_top=0,
        selected_actual_best_count=2,
    )
    return HistoricalShortOddsCompetitionGateReport(
        report_key="historical_short_odds_competition_gate:runtime_dry_run_test",
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
    season_id: str,
    *,
    original_hit: bool,
    replacement_profit: float,
) -> HistoricalCandidateMarginalAuditItem:
    original_profit = 1.0 if original_hit else -2.0
    model_top = _replacement(
        rank=1,
        fixture_id=f"{season_id}_model_top",
        simulated_hit=original_hit,
        simulated_profit=original_profit,
        simulated_hit_probability=0.61,
        decimal_odds=1.82,
        model_edge=0.0,
        profit_loss_delta=0.0,
    )
    replacement = _replacement(
        rank=2,
        fixture_id=f"{season_id}_replacement",
        simulated_hit=True,
        simulated_profit=replacement_profit,
        simulated_hit_probability=0.60,
        decimal_odds=1.95,
        model_edge=0.08,
        profit_loss_delta=replacement_profit - original_profit,
    )
    return HistoricalCandidateMarginalAuditItem(
        item_key=f"fra_ligue_2:{season_id}:selected",
        slice_id=f"football_data_co_uk_fra_ligue_2_{season_id}_market_features_v1",
        competition_id="FRA_LIGUE_2",
        final_answer_scenario_key="1x1:single",
        pass_type="1x1",
        mode="single",
        final_answer_actual_hit=original_hit,
        selected_fixture_id=f"{season_id}_selected",
        selected_market_type="1x2",
        selected_outcome="home_win",
        selected_probability=0.62,
        selected_decimal_odds=1.70,
        selected_model_edge=-0.02,
        selected_score=0.60,
        leg_actual_hit=original_hit,
        original_actual_return=3.0 if original_hit else 0.0,
        original_profit_loss=original_profit,
        original_hit_probability=0.61,
        original_roi=0.50 if original_hit else -1.0,
        original_risk_score=0.39,
        replacement_count=2,
        model_top_replacement=model_top,
        actual_best_replacement=replacement,
        replacement_candidates=[model_top, replacement],
    )


def _replacement(
    *,
    rank: int,
    fixture_id: str,
    simulated_hit: bool,
    simulated_profit: float,
    simulated_hit_probability: float,
    decimal_odds: float,
    model_edge: float,
    profit_loss_delta: float,
) -> HistoricalCandidateReplacementSimulation:
    return HistoricalCandidateReplacementSimulation(
        replacement_rank=rank,
        replacement_fixture_id=fixture_id,
        replacement_market_type="1x2",
        replacement_outcome="home_win",
        replacement_probability=simulated_hit_probability,
        replacement_decimal_odds=decimal_odds,
        replacement_model_edge=model_edge,
        replacement_score=0.70,
        replacement_quality_score=0.70,
        replacement_leg_actual_hit=simulated_hit,
        simulated_actual_hit=simulated_hit,
        simulated_actual_return=max(simulated_profit + 2.0, 0.0),
        simulated_profit_loss=simulated_profit,
        simulated_hit_probability=simulated_hit_probability,
        simulated_roi=simulated_profit / 2.0,
        simulated_risk_score=1.0 - simulated_hit_probability,
        actual_return_delta=profit_loss_delta,
        profit_loss_delta=profit_loss_delta,
        hit_probability_delta=simulated_hit_probability - 0.61,
        roi_delta=profit_loss_delta / 2.0,
        risk_score_delta=0.0,
        decision="actual_improved" if profit_loss_delta > 0 else "actual_unchanged",
    )
