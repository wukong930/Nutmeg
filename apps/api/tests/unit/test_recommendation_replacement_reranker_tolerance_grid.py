from __future__ import annotations

from pathlib import Path

import pytest

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_reranker_tolerance_grid import (
    HistoricalReplacementRerankerToleranceGridOptions,
    _options_from_args,
    _parse_args,
    _parse_float_csv,
    build_historical_replacement_reranker_tolerance_grid_report,
    main,
)
from nutmeg.recommendations.replacement_reranker_weight_experiment import (
    HistoricalReplacementRerankerProfile,
)


def test_replacement_reranker_tolerance_grid_surfaces_watchlist_only() -> None:
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
        profit_loss_delta=0.0,
    )
    actual_best = _replacement(
        rank=3,
        fixture_id="actual_best",
        probability=0.51,
        decimal_odds=2.60,
        model_edge=0.05,
        profit_loss_delta=3.0,
    )

    report = build_historical_replacement_reranker_tolerance_grid_report(
        _audit_report([_item("item_a", model_top=model_top, actual_best=actual_best)]),
        options=HistoricalReplacementRerankerToleranceGridOptions(
            hit_probability_delta_thresholds=(0.0, -0.02),
            profiles=(profile,),
            min_evaluated_item_count=1,
        ),
    )

    strict_candidate = next(
        candidate
        for candidate in report.candidates
        if candidate.profile_id == "unit_edge_tolerance"
        and candidate.hit_probability_delta_threshold == 0.0
    )
    tolerant_candidate = next(
        candidate
        for candidate in report.candidates
        if candidate.profile_id == "unit_edge_tolerance"
        and candidate.hit_probability_delta_threshold == -0.02
    )

    assert report.profile_candidate_count == 0
    assert report.watchlist_count == 1
    assert report.baseline_count == 2
    assert report.best_candidate_key is None
    assert strict_candidate.status == "rejected"
    assert strict_candidate.selected_model_top_count == 1
    assert tolerant_candidate.status == "watchlist"
    assert tolerant_candidate.selected_model_top_count == 0
    assert tolerant_candidate.simulated_actual_hit_delta_vs_baseline == 1
    assert tolerant_candidate.average_profit_loss_delta_vs_model_top == 3.0
    assert tolerant_candidate.status_reasons == ["uses_hit_probability_tolerance"]


def test_replacement_reranker_tolerance_grid_cli_options_and_main(
    tmp_path: Path,
) -> None:
    audit_report = _audit_report(
        [
            _item(
                "item_a",
                model_top=_replacement(rank=1, fixture_id="model_top"),
                actual_best=_replacement(
                    rank=2,
                    fixture_id="actual_best",
                    probability=0.41,
                    decimal_odds=2.50,
                    model_edge=0.03,
                    profit_loss_delta=2.0,
                ),
            )
        ]
    )
    audit_path = tmp_path / "audit.json"
    output_path = tmp_path / "tolerance_grid.json"
    audit_path.write_text(f"{audit_report.model_dump_json(indent=2)}\n", encoding="utf-8")

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--output-path",
            str(output_path),
            "--hit-probability-delta-thresholds",
            "0,-0.01",
            "--profile-ids",
            "edge_value_v1",
            "--min-actual-best-profit-loss-delta",
            "0.5",
            "--min-profit-loss-gap",
            "0.1",
            "--min-evaluated-item-count",
            "1",
            "--min-average-profit-loss-delta-vs-model-top",
            "0.2",
            "--min-simulated-actual-hit-delta-vs-baseline",
            "0",
            "--min-replacement-leg-actual-hit-delta-vs-baseline",
            "0",
            "--max-harm-count-vs-model-top",
            "1",
            "--max-report-items-per-experiment",
            "10",
        ]
    )
    options = _options_from_args(args)

    assert options.hit_probability_delta_thresholds == (0.0, -0.01)
    assert [profile.profile_id for profile in options.profiles] == ["edge_value_v1"]
    assert options.min_actual_best_profit_loss_delta == 0.5
    assert options.min_profit_loss_gap == 0.1
    assert options.min_evaluated_item_count == 1
    assert options.min_average_profit_loss_delta_vs_model_top == 0.2
    assert options.max_harm_count_vs_model_top == 1
    assert options.max_report_items_per_experiment == 10

    main(
        [
            "--audit-report",
            str(audit_path),
            "--output-path",
            str(output_path),
            "--profile-ids",
            "edge_value_v1",
            "--min-evaluated-item-count",
            "1",
        ]
    )

    assert output_path.exists()
    assert _parse_float_csv("0,-0.005") == (0.0, -0.005)
    with pytest.raises(SystemExit):
        _parse_float_csv("")


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
) -> HistoricalCandidateMarginalAuditItem:
    return HistoricalCandidateMarginalAuditItem(
        item_key=item_key,
        slice_id="unit_slice",
        competition_id="UNIT",
        final_answer_scenario_key="1x1:single",
        pass_type="1x1",
        mode="single",
        final_answer_actual_hit=False,
        selected_fixture_id=f"{item_key}_selected",
        selected_market_type="1x2",
        selected_outcome="home_win",
        selected_probability=0.48,
        selected_decimal_odds=2.00,
        selected_model_edge=-0.03,
        selected_score=0.55,
        leg_actual_hit=False,
        original_actual_return=0.0,
        original_profit_loss=-2.0,
        original_hit_probability=0.48,
        original_roi=-1.0,
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
    probability: float = 0.42,
    decimal_odds: float = 2.30,
    model_edge: float = -0.02,
    score: float = 0.52,
    quality: float = 0.48,
    profit_loss_delta: float = 2.0,
) -> HistoricalCandidateReplacementSimulation:
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
        replacement_leg_actual_hit=profit_loss_delta > 0,
        simulated_actual_hit=profit_loss_delta > 0,
        simulated_actual_return=2.0 + profit_loss_delta,
        simulated_profit_loss=profit_loss_delta,
        simulated_hit_probability=probability,
        simulated_roi=0.10,
        simulated_risk_score=1.0 - probability,
        actual_return_delta=profit_loss_delta,
        profit_loss_delta=profit_loss_delta,
        hit_probability_delta=probability - 0.48,
        roi_delta=0.10,
        risk_score_delta=0.02,
        decision="actual_improved" if profit_loss_delta > 0 else "actual_unchanged",
    )
