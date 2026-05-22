from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_reranker_diagnostics import (
    HistoricalReplacementRerankerDiagnosticOptions,
    _options_from_args,
    _parse_args,
    build_historical_replacement_reranker_diagnostic_report,
    load_historical_candidate_marginal_audit_report,
)


def test_replacement_reranker_diagnostics_identifies_probability_odds_bias() -> None:
    report = build_historical_replacement_reranker_diagnostic_report(
        _audit_report(
            [
                _item(
                    "item_a",
                    competition_id="FRA_LIGUE_2",
                    model_top=_replacement(
                        rank=1,
                        fixture_id="model_top",
                        probability=0.47,
                        decimal_odds=2.02,
                        model_edge=-0.03,
                        score=0.56,
                        quality=0.51,
                        profit_loss_delta=0.0,
                    ),
                    actual_best=_replacement(
                        rank=4,
                        fixture_id="actual_best",
                        probability=0.31,
                        decimal_odds=3.10,
                        model_edge=-0.01,
                        score=0.49,
                        quality=0.40,
                        profit_loss_delta=6.2,
                    ),
                )
            ]
        ),
        options=HistoricalReplacementRerankerDiagnosticOptions(
            min_profit_loss_gap=0.1,
        ),
    )

    assert report.evaluated_item_count == 1
    assert report.rank_gap_item_count == 1
    assert report.average_rank_gap == 3.0
    assert report.average_profit_loss_gap == 6.2
    assert report.bias_counts["actual_best_lower_probability"] == 1
    assert report.bias_counts["actual_best_higher_odds"] == 1
    assert report.bias_counts["actual_best_better_model_edge"] == 1
    assert report.bias_counts["actual_best_lower_candidate_score"] == 1
    assert report.competition_summaries[0].competition_id == "FRA_LIGUE_2"
    assert report.top_profit_gap_items[0].item_key == "item_a"


def test_replacement_reranker_diagnostics_filters_small_gaps() -> None:
    report = build_historical_replacement_reranker_diagnostic_report(
        _audit_report(
            [
                _item(
                    "item_a",
                    model_top=_replacement(rank=1, profit_loss_delta=1.0),
                    actual_best=_replacement(rank=2, profit_loss_delta=1.2),
                )
            ]
        ),
        options=HistoricalReplacementRerankerDiagnosticOptions(
            min_profit_loss_gap=0.5,
        ),
    )

    assert report.evaluated_item_count == 0
    assert report.items == []


def test_replacement_reranker_diagnostics_cli_options_and_loader(
    tmp_path: Path,
) -> None:
    audit_report = _audit_report(
        [_item("item_a", model_top=_replacement(rank=1), actual_best=_replacement(rank=3))]
    )
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(f"{audit_report.model_dump_json(indent=2)}\n", encoding="utf-8")

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--output-path",
            str(tmp_path / "reranker.json"),
            "--min-actual-best-profit-loss-delta",
            "0.5",
            "--min-profit-loss-gap",
            "0.25",
            "--max-report-items",
            "12",
            "--probability-gap-threshold",
            "0.03",
            "--decimal-odds-gap-threshold",
            "0.2",
            "--model-edge-gap-threshold",
            "0.02",
            "--score-gap-threshold",
            "0.04",
            "--risk-gap-threshold",
            "0.05",
        ]
    )
    options = _options_from_args(args)
    loaded = load_historical_candidate_marginal_audit_report(audit_path)

    assert loaded.report_key == audit_report.report_key
    assert options.min_actual_best_profit_loss_delta == 0.5
    assert options.min_profit_loss_gap == 0.25
    assert options.max_report_items == 12
    assert options.probability_gap_threshold == 0.03
    assert options.decimal_odds_gap_threshold == 0.2
    assert options.model_edge_gap_threshold == 0.02
    assert options.score_gap_threshold == 0.04
    assert options.risk_gap_threshold == 0.05


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
        replacement_simulation_count=len(items) * 2,
        actual_replacement_opportunity_count=len(items),
        model_top_replacement_count=len(items),
        model_top_actual_improvement_count=0,
        model_top_actual_harm_count=0,
        items=items,
    )


def _item(
    item_key: str,
    *,
    competition_id: str = "TEST",
    model_top: HistoricalCandidateReplacementSimulation,
    actual_best: HistoricalCandidateReplacementSimulation,
) -> HistoricalCandidateMarginalAuditItem:
    return HistoricalCandidateMarginalAuditItem(
        item_key=item_key,
        slice_id="unit_slice",
        competition_id=competition_id,
        final_answer_scenario_key="1x1:single",
        pass_type="1x1",
        mode="single",
        final_answer_actual_hit=False,
        selected_fixture_id=f"{item_key}_selected",
        selected_market_type="1x2",
        selected_outcome="home_win",
        selected_probability=0.48,
        selected_decimal_odds=2.0,
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
