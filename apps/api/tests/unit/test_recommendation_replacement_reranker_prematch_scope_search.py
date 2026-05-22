from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_reranker_prematch_scope_search import (
    HistoricalReplacementRerankerPrematchScopeSearchOptions,
    build_historical_replacement_reranker_prematch_scope_search_report,
    load_historical_replacement_reranker_prematch_scope_search_report,
    main,
)
from nutmeg.recommendations.replacement_reranker_tolerance_grid import (
    HistoricalReplacementRerankerToleranceGridOptions,
    build_historical_replacement_reranker_tolerance_grid_report,
)


def test_prematch_scope_search_finds_no_harm_competition_scope() -> None:
    audit_report = _audit_report(
        [
            _item("EPL", "2020_2021", 1),
            _item("EPL", "2021_2022", 1),
            _item(
                "GER_2_BUNDESLIGA",
                "2020_2021",
                1,
                final_answer_actual_hit=True,
                original_profit_loss=2.0,
                model_top_profit_delta=-4.0,
                actual_best_profit_delta=-1.0,
            ),
            _item(
                "GER_2_BUNDESLIGA",
                "2021_2022",
                1,
                final_answer_actual_hit=True,
                original_profit_loss=2.0,
                model_top_profit_delta=-4.0,
                actual_best_profit_delta=-1.0,
            ),
        ],
        missed_legs_only=False,
    )
    tolerance_report = _tolerance_report(audit_report)

    report = build_historical_replacement_reranker_prematch_scope_search_report(
        audit_report,
        tolerance_grid_report=tolerance_report,
        options=_scope_options(),
    )

    assert report.status == "accepted_scope_found"
    assert report.accepted_scope_count == 1
    assert report.rejected_scope_count == 1
    assert report.best_scope is not None
    assert report.best_scope.scope_competition_ids == ["EPL"]
    assert report.best_scope.source_surface_kind == "prematch_replacement_surface"
    assert report.best_scope.overall_hit_delta_vs_original_count == 2
    assert report.best_scope.overall_profit_loss_delta_vs_original > 0.0
    assert report.best_scope.overall_harm_count_vs_original == 0
    assert report.best_scope.failed_fold_count == 0


def test_prematch_scope_search_cli_writes_report(tmp_path: Path) -> None:
    audit_report = _audit_report(
        [
            _item("EPL", "2020_2021", 1),
            _item("EPL", "2021_2022", 1),
            _item(
                "GER_2_BUNDESLIGA",
                "2020_2021",
                1,
                final_answer_actual_hit=True,
                original_profit_loss=2.0,
                model_top_profit_delta=-4.0,
                actual_best_profit_delta=-1.0,
            ),
        ],
        missed_legs_only=False,
    )
    tolerance_report = _tolerance_report(audit_report)
    audit_path = tmp_path / "audit.json"
    tolerance_path = tmp_path / "tolerance.json"
    output_path = tmp_path / "scope_search.json"
    audit_path.write_text(audit_report.model_dump_json(), encoding="utf-8")
    tolerance_path.write_text(tolerance_report.model_dump_json(), encoding="utf-8")

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
            "--hit-probability-delta-threshold",
            "-0.02",
            "--min-actual-best-profit-loss-delta",
            "-2.0",
            "--max-scope-competition-count",
            "1",
            "--exclude-full-scope",
            "--min-overall-final-answer-count",
            "1",
            "--min-overall-changed-from-model-top-count",
            "1",
            "--min-active-competition-fold-count",
            "1",
            "--min-active-season-fold-count",
            "1",
            "--min-active-rolling-fold-count",
            "1",
            "--rolling-window-slice-count",
            "1",
            "--rolling-window-step",
            "1",
            "--allow-missing-tolerance-candidate",
        ]
    )

    saved = load_historical_replacement_reranker_prematch_scope_search_report(
        output_path
    )
    assert saved.status == "accepted_scope_found"
    assert saved.best_scope is not None
    assert saved.best_scope.scope_competition_ids == ["EPL"]


def _scope_options() -> HistoricalReplacementRerankerPrematchScopeSearchOptions:
    return HistoricalReplacementRerankerPrematchScopeSearchOptions(
        profile_id="edge_value_v1",
        hit_probability_delta_threshold=-0.02,
        min_actual_best_profit_loss_delta=-2.0,
        min_scope_competition_count=1,
        max_scope_competition_count=1,
        include_full_scope=False,
        min_overall_final_answer_count=2,
        min_overall_changed_from_model_top_count=2,
        min_active_competition_fold_count=1,
        min_active_season_fold_count=2,
        min_active_rolling_fold_count=1,
        rolling_window_slice_count=2,
        rolling_window_step=1,
        require_tolerance_candidate=False,
    )


def _tolerance_report(audit_report: HistoricalCandidateMarginalAuditReport):
    return build_historical_replacement_reranker_tolerance_grid_report(
        audit_report,
        options=HistoricalReplacementRerankerToleranceGridOptions(
            hit_probability_delta_thresholds=(-0.02,),
            min_actual_best_profit_loss_delta=-2.0,
            min_evaluated_item_count=1,
        ),
    )


def _audit_report(
    items: list[HistoricalCandidateMarginalAuditItem],
    *,
    missed_legs_only: bool,
) -> HistoricalCandidateMarginalAuditReport:
    return HistoricalCandidateMarginalAuditReport(
        report_key="unit-test-prematch-scope-audit",
        status="generated",
        slice_count=len({item.slice_id for item in items}),
        competition_count=len({item.competition_id for item in items}),
        final_answer_count=len(items),
        selected_leg_count=len(items),
        missed_leg_count=len(items),
        replacement_simulation_count=sum(item.replacement_count for item in items),
        actual_replacement_opportunity_count=len(items),
        model_top_replacement_count=len(items),
        model_top_actual_improvement_count=0,
        model_top_actual_harm_count=0,
        items=items,
        summary_json={"target_filter": {"missed_legs_only": missed_legs_only}},
    )


def _item(
    competition_id: str,
    season_id: str,
    index: int,
    *,
    final_answer_actual_hit: bool = False,
    original_profit_loss: float = -2.0,
    model_top_profit_delta: float = 0.0,
    actual_best_profit_delta: float = 3.0,
) -> HistoricalCandidateMarginalAuditItem:
    model_top = _replacement(
        rank=1,
        fixture_id=f"{competition_id}_{season_id}_{index}_model_top",
        probability=0.52,
        decimal_odds=1.90,
        model_edge=-0.02,
        profit_delta=model_top_profit_delta,
    )
    actual_best = _replacement(
        rank=2,
        fixture_id=f"{competition_id}_{season_id}_{index}_actual_best",
        probability=0.51,
        decimal_odds=2.60,
        model_edge=0.05,
        profit_delta=actual_best_profit_delta,
    )
    normalized_competition = competition_id.lower()
    slice_id = (
        f"football_data_co_uk_{normalized_competition}_{season_id}_"
        f"market_features_v1_rolling_window_v1_{index:03d}"
    )
    original_actual_return = max(0.0, original_profit_loss + 2.0)
    original_roi = original_profit_loss / 2.0
    return HistoricalCandidateMarginalAuditItem(
        item_key=f"candidate_marginal:{slice_id}:{index}",
        slice_id=slice_id,
        competition_id=competition_id,
        final_answer_scenario_key="1x1:single",
        pass_type="1x1",
        mode="single",
        final_answer_actual_hit=final_answer_actual_hit,
        selected_fixture_id=f"{competition_id}_{season_id}_{index}_selected",
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
    fixture_id: str,
    probability: float,
    decimal_odds: float,
    model_edge: float,
    profit_delta: float,
) -> HistoricalCandidateReplacementSimulation:
    simulated_profit = -2.0 + profit_delta
    actual_hit = profit_delta > 0
    return HistoricalCandidateReplacementSimulation(
        replacement_rank=rank,
        replacement_fixture_id=fixture_id,
        replacement_market_type="1x2",
        replacement_outcome="home_win",
        replacement_probability=probability,
        replacement_decimal_odds=decimal_odds,
        replacement_model_edge=model_edge,
        replacement_score=0.52,
        replacement_quality_score=0.48,
        replacement_leg_actual_hit=actual_hit,
        simulated_actual_hit=actual_hit,
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
