from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_reranker_shadow_admission import (
    HistoricalReplacementRerankerShadowAdmissionOptions,
    _options_from_args,
    _parse_args,
    build_historical_replacement_reranker_shadow_admission_report,
    main,
)
from nutmeg.recommendations.replacement_reranker_tolerance_grid import (
    HistoricalReplacementRerankerToleranceGridOptions,
    build_historical_replacement_reranker_tolerance_grid_report,
)


def test_shadow_admission_accepts_when_active_folds_pass() -> None:
    audit_report = _audit_report(
        [
            _item("EPL", "2020_2021", 1),
            _item("EPL", "2021_2022", 1),
            _item("FRA_LIGUE_2", "2020_2021", 1),
            _item("FRA_LIGUE_2", "2021_2022", 1),
        ]
    )
    tolerance_report = _tolerance_report(audit_report)

    report = build_historical_replacement_reranker_shadow_admission_report(
        audit_report,
        tolerance_grid_report=tolerance_report,
        options=HistoricalReplacementRerankerShadowAdmissionOptions(
            profile_id="edge_value_v1",
            hit_probability_delta_threshold=-0.02,
            min_overall_final_answer_count=4,
            min_overall_changed_from_model_top_count=4,
            min_active_competition_fold_count=2,
            min_active_season_fold_count=2,
            min_active_rolling_fold_count=2,
            rolling_window_slice_count=2,
            rolling_window_step=2,
        ),
    )

    assert report.status == "accepted"
    assert report.runtime_profile_candidate_allowed is True
    assert report.shadow_allowed is True
    assert report.active_competition_fold_count == 2
    assert report.active_season_fold_count == 2
    assert report.active_rolling_fold_count == 2
    assert report.failed_fold_count == 0
    assert report.summary_json["overall_final_hit_harm_count_vs_model_top"] == 0
    assert report.summary_json["overall_profit_loss_harm_count_vs_model_top"] == 0
    assert all(check.status == "passed" for check in report.checks)
    assert {fold.status for fold in report.folds} == {"passed"}


def test_shadow_admission_records_prematch_source_surface() -> None:
    audit_report = _audit_report(
        [
            _item("EPL", "2020_2021", 1),
            _item("EPL", "2021_2022", 1),
        ],
        missed_legs_only=False,
    )
    tolerance_report = _tolerance_report(audit_report)

    report = build_historical_replacement_reranker_shadow_admission_report(
        audit_report,
        tolerance_grid_report=tolerance_report,
        options=HistoricalReplacementRerankerShadowAdmissionOptions(
            profile_id="edge_value_v1",
            min_overall_final_answer_count=2,
            min_overall_changed_from_model_top_count=2,
            min_active_competition_fold_count=1,
            min_active_season_fold_count=2,
            min_active_rolling_fold_count=1,
            rolling_window_slice_count=2,
            rolling_window_step=1,
            require_prematch_source_surface=True,
        ),
    )

    assert report.status == "accepted"
    assert report.summary_json["source_surface_kind"] == "prematch_replacement_surface"
    assert report.summary_json["source_surface_missed_legs_only"] is False
    assert report.summary_json["source_surface"]["selected_leg_count"] == 2
    assert all(check.status == "passed" for check in report.checks)


def test_shadow_admission_blocks_missed_leg_source_surface_when_required() -> None:
    audit_report = _audit_report(
        [
            _item("EPL", "2020_2021", 1),
            _item("EPL", "2021_2022", 1),
        ],
        missed_legs_only=True,
    )
    tolerance_report = _tolerance_report(audit_report)

    report = build_historical_replacement_reranker_shadow_admission_report(
        audit_report,
        tolerance_grid_report=tolerance_report,
        options=HistoricalReplacementRerankerShadowAdmissionOptions(
            profile_id="edge_value_v1",
            min_overall_final_answer_count=2,
            min_overall_changed_from_model_top_count=2,
            min_active_competition_fold_count=1,
            min_active_season_fold_count=2,
            min_active_rolling_fold_count=1,
            rolling_window_slice_count=2,
            rolling_window_step=1,
            require_prematch_source_surface=True,
        ),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_only"
    assert report.runtime_profile_candidate_allowed is False
    assert report.shadow_allowed is True
    assert report.summary_json["source_surface_kind"] == "missed_leg_diagnostic_surface"
    assert "source_surface_prematch" in failed_checks


def test_shadow_admission_blocks_final_hit_harm_vs_model_top() -> None:
    audit_report = _audit_report(
        [
            _item(
                "EPL",
                "2020_2021",
                1,
                model_top_profit_delta=1.0,
                actual_best_profit_delta=1.2,
                actual_best_actual_hit=False,
            )
        ]
    )
    tolerance_report = _tolerance_report(audit_report)

    report = build_historical_replacement_reranker_shadow_admission_report(
        audit_report,
        tolerance_grid_report=tolerance_report,
        options=HistoricalReplacementRerankerShadowAdmissionOptions(
            profile_id="edge_value_v1",
            min_overall_final_answer_count=1,
            min_overall_changed_from_model_top_count=1,
            min_overall_final_answer_hit_delta_vs_model_top=-1,
            min_overall_replacement_leg_hit_delta_vs_model_top=-1,
            max_overall_final_hit_harm_count_vs_model_top=0,
            max_overall_profit_loss_harm_count_vs_model_top=0,
            min_fold_final_answer_hit_delta_vs_model_top=-1,
            min_fold_replacement_leg_hit_delta_vs_model_top=-1,
            max_fold_final_hit_harm_count_vs_model_top=0,
            max_fold_profit_loss_harm_count_vs_model_top=0,
            min_active_competition_fold_count=0,
            min_active_season_fold_count=0,
            min_active_rolling_fold_count=0,
            require_tolerance_candidate=False,
        ),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "rejected"
    assert report.summary_json["overall_final_hit_harm_count_vs_model_top"] == 1
    assert report.summary_json["overall_profit_loss_harm_count_vs_model_top"] == 0
    assert "overall_final_hit_harm_count_vs_model_top" in failed_checks
    assert "overall_profit_loss_harm_count_vs_model_top" not in failed_checks
    assert any(
        "final_hit_harm_count_vs_model_top_above_threshold" in fold.failure_reasons
        for fold in report.folds
        if fold.status == "failed"
    )


def test_shadow_admission_scopes_to_competition_season_regime() -> None:
    audit_report = _audit_report(
        [
            _item("EPL", "2020_2021", 1),
            _item("EPL", "2021_2022", 1),
            _item("FRA_LIGUE_2", "2020_2021", 1),
            _item("FRA_LIGUE_2", "2021_2022", 1),
        ]
    )
    tolerance_report = _tolerance_report(audit_report)

    report = build_historical_replacement_reranker_shadow_admission_report(
        audit_report,
        tolerance_grid_report=tolerance_report,
        options=HistoricalReplacementRerankerShadowAdmissionOptions(
            profile_id="edge_value_v1",
            hit_probability_delta_threshold=-0.02,
            scope_competition_ids=("FRA_LIGUE_2",),
            scope_min_competition_season_index=2,
            min_overall_final_answer_count=1,
            min_overall_changed_from_model_top_count=1,
            min_active_competition_fold_count=1,
            min_active_season_fold_count=1,
            min_active_rolling_fold_count=1,
            rolling_window_slice_count=1,
            rolling_window_step=1,
        ),
    )

    scope = report.summary_json["scope"]

    assert report.status == "accepted"
    assert report.source_audit_report_key == audit_report.report_key
    assert report.summary_json["overall_shadow_final_answer_count"] == 1
    assert scope["enabled"] is True
    assert scope["source_item_count"] == 4
    assert scope["scoped_item_count"] == 1
    assert scope["scoped_competition_ids"] == ["FRA_LIGUE_2"]
    assert scope["scoped_season_ids"] == ["2021_2022"]
    assert scope["scoped_competition_season_indexes"] == [
        {
            "competition_id": "FRA_LIGUE_2",
            "season_id": "2021_2022",
            "competition_season_index": 2,
        }
    ]
    assert {fold.fold_type for fold in report.folds} == {
        "competition",
        "season",
        "rolling_window",
    }
    assert all(
        fold.source_slice_ids
        == [
            "football_data_co_uk_fra_ligue_2_2021_2022_"
            "market_features_v1_rolling_window_v1_001"
        ]
        for fold in report.folds
    )


def test_shadow_admission_stays_shadow_only_when_fold_coverage_is_too_low() -> None:
    audit_report = _audit_report(
        [
            _item("EPL", "2020_2021", 1),
            _item("EPL", "2021_2022", 1),
        ]
    )
    tolerance_report = _tolerance_report(audit_report)

    report = build_historical_replacement_reranker_shadow_admission_report(
        audit_report,
        tolerance_grid_report=tolerance_report,
        options=HistoricalReplacementRerankerShadowAdmissionOptions(
            profile_id="edge_value_v1",
            hit_probability_delta_threshold=-0.02,
            min_overall_final_answer_count=2,
            min_overall_changed_from_model_top_count=2,
            min_active_competition_fold_count=2,
            min_active_season_fold_count=2,
            min_active_rolling_fold_count=1,
            rolling_window_slice_count=2,
            rolling_window_step=1,
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_only"
    assert report.runtime_profile_candidate_allowed is False
    assert report.shadow_allowed is True
    assert "active_competition_fold_count" in failed_checks


def test_shadow_admission_rejects_when_prematch_surface_harms_original() -> None:
    audit_report = _audit_report(
        [
            _item(
                "EPL",
                "2020_2021",
                1,
                final_answer_actual_hit=True,
                original_profit_loss=2.0,
                model_top_profit_delta=-4.0,
                actual_best_profit_delta=-1.0,
            )
        ]
    )
    tolerance_report = _tolerance_report(audit_report)

    report = build_historical_replacement_reranker_shadow_admission_report(
        audit_report,
        tolerance_grid_report=tolerance_report,
        options=HistoricalReplacementRerankerShadowAdmissionOptions(
            profile_id="edge_value_v1",
            min_actual_best_profit_loss_delta=-2.0,
            min_overall_final_answer_count=1,
            min_overall_changed_from_model_top_count=1,
            min_active_competition_fold_count=0,
            min_active_season_fold_count=0,
            min_active_rolling_fold_count=0,
            require_tolerance_candidate=False,
            min_overall_final_answer_hit_delta_vs_original=0,
            min_overall_profit_loss_delta_vs_original=0.0,
            min_overall_roi_delta_vs_original=0.0,
            max_overall_harm_count_vs_original=0,
            max_fold_harm_count_vs_original=0,
        ),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "rejected"
    assert report.runtime_profile_candidate_allowed is False
    assert report.summary_json["overall_hit_delta_vs_original_count"] == -1
    assert report.summary_json["overall_profit_loss_delta_vs_original"] == -1.0
    assert report.summary_json["overall_harm_count_vs_original"] == 1
    assert "overall_shadow_gate_passed" in failed_checks
    assert "overall_final_answer_hit_delta_vs_original" in failed_checks
    assert "overall_profit_loss_delta_vs_original" in failed_checks
    assert "overall_roi_delta_vs_original" in failed_checks
    assert "overall_harm_count_vs_original" in failed_checks


def test_shadow_admission_cli_options_loader_and_main(tmp_path: Path) -> None:
    audit_report = _audit_report([_item("EPL", "2020_2021", 1)])
    tolerance_report = _tolerance_report(audit_report)
    audit_path = tmp_path / "audit.json"
    tolerance_path = tmp_path / "tolerance.json"
    output_path = tmp_path / "admission.json"
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
            "--profile-id",
            "edge_value_v1",
            "--hit-probability-delta-threshold",
            "-0.02",
            "--min-actual-best-profit-loss-delta",
            "0.5",
            "--min-profit-loss-gap",
            "0.1",
            "--scope-competition-ids",
            "EPL,FRA_LIGUE_2",
            "--scope-season-ids",
            "2021_2022",
            "--scope-min-competition-season-index",
            "2",
            "--scope-max-competition-season-index",
            "4",
            "--min-overall-final-answer-count",
            "1",
            "--min-overall-changed-from-model-top-count",
            "1",
            "--min-overall-final-answer-hit-delta-vs-model-top",
            "0",
            "--min-overall-replacement-leg-hit-delta-vs-model-top",
            "0",
            "--min-overall-profit-loss-delta-vs-model-top",
            "0.2",
            "--min-overall-roi-delta-vs-model-top",
            "0.1",
            "--max-overall-harm-count-vs-model-top",
            "1",
            "--max-overall-final-hit-harm-count-vs-model-top",
            "2",
            "--max-overall-profit-loss-harm-count-vs-model-top",
            "3",
            "--min-overall-average-hit-probability-delta-vs-model-top",
            "-0.03",
            "--min-overall-final-answer-hit-delta-vs-original",
            "0",
            "--min-overall-profit-loss-delta-vs-original",
            "0.2",
            "--min-overall-roi-delta-vs-original",
            "0.1",
            "--max-overall-harm-count-vs-original",
            "1",
            "--max-overall-final-hit-harm-count-vs-original",
            "2",
            "--max-overall-profit-loss-harm-count-vs-original",
            "3",
            "--min-overall-average-hit-probability-delta-vs-original",
            "-0.04",
            "--min-fold-final-answer-count",
            "1",
            "--min-fold-changed-from-model-top-count",
            "1",
            "--min-fold-final-answer-hit-delta-vs-model-top",
            "0",
            "--min-fold-replacement-leg-hit-delta-vs-model-top",
            "0",
            "--min-fold-profit-loss-delta-vs-model-top",
            "0.2",
            "--min-fold-roi-delta-vs-model-top",
            "0.1",
            "--max-fold-harm-count-vs-model-top",
            "1",
            "--max-fold-final-hit-harm-count-vs-model-top",
            "2",
            "--max-fold-profit-loss-harm-count-vs-model-top",
            "3",
            "--min-fold-average-hit-probability-delta-vs-model-top",
            "-0.03",
            "--min-fold-final-answer-hit-delta-vs-original",
            "0",
            "--min-fold-profit-loss-delta-vs-original",
            "0.2",
            "--min-fold-roi-delta-vs-original",
            "0.1",
            "--max-fold-harm-count-vs-original",
            "1",
            "--max-fold-final-hit-harm-count-vs-original",
            "2",
            "--max-fold-profit-loss-harm-count-vs-original",
            "3",
            "--min-fold-average-hit-probability-delta-vs-original",
            "-0.04",
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
            "--max-failed-fold-count",
            "1",
            "--require-prematch-source-surface",
            "--allow-missing-tolerance-candidate",
            "--allowed-tolerance-statuses",
            "watchlist",
            "--allow-production-change",
            "--max-report-folds",
            "10",
            "--no-fail-process",
        ]
    )
    options = _options_from_args(args)

    assert options.profile_id == "edge_value_v1"
    assert options.hit_probability_delta_threshold == -0.02
    assert options.min_actual_best_profit_loss_delta == 0.5
    assert options.min_profit_loss_gap == 0.1
    assert options.scope_competition_ids == ("EPL", "FRA_LIGUE_2")
    assert options.scope_season_ids == ("2021_2022",)
    assert options.scope_min_competition_season_index == 2
    assert options.scope_max_competition_season_index == 4
    assert options.min_overall_final_answer_count == 1
    assert options.min_overall_changed_from_model_top_count == 1
    assert options.min_overall_profit_loss_delta_vs_model_top == 0.2
    assert options.min_overall_roi_delta_vs_model_top == 0.1
    assert options.max_overall_harm_count_vs_model_top == 1
    assert options.max_overall_final_hit_harm_count_vs_model_top == 2
    assert options.max_overall_profit_loss_harm_count_vs_model_top == 3
    assert options.min_overall_average_hit_probability_delta_vs_model_top == -0.03
    assert options.min_overall_final_answer_hit_delta_vs_original == 0
    assert options.min_overall_profit_loss_delta_vs_original == 0.2
    assert options.min_overall_roi_delta_vs_original == 0.1
    assert options.max_overall_harm_count_vs_original == 1
    assert options.max_overall_final_hit_harm_count_vs_original == 2
    assert options.max_overall_profit_loss_harm_count_vs_original == 3
    assert options.min_overall_average_hit_probability_delta_vs_original == -0.04
    assert options.min_fold_final_answer_count == 1
    assert options.min_fold_changed_from_model_top_count == 1
    assert options.min_fold_profit_loss_delta_vs_model_top == 0.2
    assert options.min_fold_roi_delta_vs_model_top == 0.1
    assert options.max_fold_harm_count_vs_model_top == 1
    assert options.max_fold_final_hit_harm_count_vs_model_top == 2
    assert options.max_fold_profit_loss_harm_count_vs_model_top == 3
    assert options.min_fold_average_hit_probability_delta_vs_model_top == -0.03
    assert options.min_fold_final_answer_hit_delta_vs_original == 0
    assert options.min_fold_profit_loss_delta_vs_original == 0.2
    assert options.min_fold_roi_delta_vs_original == 0.1
    assert options.max_fold_harm_count_vs_original == 1
    assert options.max_fold_final_hit_harm_count_vs_original == 2
    assert options.max_fold_profit_loss_harm_count_vs_original == 3
    assert options.min_fold_average_hit_probability_delta_vs_original == -0.04
    assert options.min_active_competition_fold_count == 1
    assert options.min_active_season_fold_count == 1
    assert options.min_active_rolling_fold_count == 1
    assert options.rolling_window_slice_count == 1
    assert options.rolling_window_step == 1
    assert options.max_failed_fold_count == 1
    assert options.require_prematch_source_surface is True
    assert options.require_tolerance_candidate is False
    assert options.allowed_tolerance_statuses == ("watchlist",)
    assert options.require_no_production_change is False
    assert options.max_report_folds == 10

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
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "accepted"
    assert payload["runtime_profile_candidate_allowed"] is True


def _tolerance_report(audit_report: HistoricalCandidateMarginalAuditReport):
    return build_historical_replacement_reranker_tolerance_grid_report(
        audit_report,
        options=HistoricalReplacementRerankerToleranceGridOptions(
            hit_probability_delta_thresholds=(-0.02,),
            min_evaluated_item_count=1,
        ),
    )


def _audit_report(
    items: list[HistoricalCandidateMarginalAuditItem],
    *,
    missed_legs_only: bool | None = None,
) -> HistoricalCandidateMarginalAuditReport:
    summary_json: dict[str, object] = {}
    if missed_legs_only is not None:
        summary_json["target_filter"] = {"missed_legs_only": missed_legs_only}
    return HistoricalCandidateMarginalAuditReport(
        report_key="unit-test-shadow-admission-audit",
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
        summary_json=summary_json,
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
    model_top_actual_hit: bool | None = None,
    actual_best_actual_hit: bool | None = None,
) -> HistoricalCandidateMarginalAuditItem:
    model_top = _replacement(
        rank=1,
        fixture_id=f"{competition_id}_{season_id}_{index}_model_top",
        probability=0.52,
        decimal_odds=1.90,
        model_edge=-0.02,
        profit_delta=model_top_profit_delta,
        actual_hit=model_top_actual_hit,
    )
    actual_best = _replacement(
        rank=2,
        fixture_id=f"{competition_id}_{season_id}_{index}_actual_best",
        probability=0.51,
        decimal_odds=2.60,
        model_edge=0.05,
        profit_delta=actual_best_profit_delta,
        actual_hit=actual_best_actual_hit,
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
    actual_hit: bool | None = None,
) -> HistoricalCandidateReplacementSimulation:
    simulated_profit = -2.0 + profit_delta
    resolved_actual_hit = profit_delta > 0 if actual_hit is None else actual_hit
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
        replacement_leg_actual_hit=resolved_actual_hit,
        simulated_actual_hit=resolved_actual_hit,
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
