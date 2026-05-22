from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
)
from nutmeg.recommendations.replacement_short_odds_final_answer_gate import (
    HistoricalShortOddsFinalAnswerGateItem,
    HistoricalShortOddsFinalAnswerGateReport,
)
from nutmeg.recommendations.replacement_short_odds_suite_gate import (
    HistoricalShortOddsSuiteGateOptions,
    _options_from_args,
    _parse_args,
    build_historical_short_odds_suite_gate_report,
    load_historical_short_odds_final_answer_gate_report,
    main,
)


def test_short_odds_suite_gate_merges_changed_and_unchanged_answers() -> None:
    audit_report = _audit_report(
        [
            _audit_item(
                "item_a",
                slice_id="slice_a",
                actual_hit=False,
                profit_loss=-2.0,
                actual_return=0.0,
                hit_probability=0.62,
            ),
            _audit_item(
                "item_b",
                slice_id="slice_b",
                actual_hit=True,
                profit_loss=1.0,
                actual_return=3.0,
                hit_probability=0.55,
            ),
        ]
    )
    final_answer_gate = _final_answer_gate_report(
        [
            _gate_item(
                "slice_a:2x1:single",
                item_key="item_a",
                original_hit=False,
                shadow_hit=True,
                original_profit=-2.0,
                shadow_profit=0.4,
                original_hit_probability=0.62,
                shadow_hit_probability=0.61,
            )
        ]
    )

    report = build_historical_short_odds_suite_gate_report(
        audit_report,
        final_answer_gate,
        options=HistoricalShortOddsSuiteGateOptions(
            min_final_answer_count=2,
            min_changed_final_answer_count=1,
        ),
    )

    assert report.passed is True
    assert report.final_answer_count == 2
    assert report.changed_final_answer_count == 1
    assert report.baseline_final_answer_hit_count == 1
    assert report.candidate_final_answer_hit_count == 2
    assert report.final_answer_hit_delta_count == 1
    assert report.baseline_profit_loss == -1.0
    assert report.candidate_profit_loss == 1.4
    assert report.profit_loss_delta == 2.4
    assert report.total_stake == 4.0
    assert report.roi_delta == 0.6
    assert report.harm_count_vs_original == 0
    assert report.final_hit_harm_count_vs_original == 0
    assert report.profit_loss_harm_count_vs_original == 0
    assert [item.final_answer_key for item in report.changed_items] == [
        "slice_a:2x1:single"
    ]


def test_short_odds_suite_gate_fails_on_harm_and_source_decision() -> None:
    audit_report = _audit_report(
        [
            _audit_item(
                "item_a",
                slice_id="slice_a",
                actual_hit=True,
                profit_loss=1.0,
                actual_return=3.0,
                hit_probability=0.62,
            )
        ]
    )
    final_answer_gate = _final_answer_gate_report(
        [
            _gate_item(
                "slice_a:2x1:single",
                item_key="item_a",
                original_hit=True,
                shadow_hit=False,
                original_profit=1.0,
                shadow_profit=-2.0,
                original_hit_probability=0.62,
                shadow_hit_probability=0.58,
            )
        ],
        decision="rejected",
    )

    report = build_historical_short_odds_suite_gate_report(
        audit_report,
        final_answer_gate,
        options=HistoricalShortOddsSuiteGateOptions(
            min_final_answer_count=1,
            min_changed_final_answer_count=1,
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.passed is False
    assert report.status == "failed"
    assert report.harm_count_vs_original == 1
    assert report.final_hit_harm_count_vs_original == 1
    assert report.profit_loss_harm_count_vs_original == 1
    assert "final_answer_hit_rate_delta" in failed_checks
    assert "roi_delta" in failed_checks
    assert "profit_loss_delta" in failed_checks
    assert "harm_count_vs_original" in failed_checks
    assert "final_hit_harm_count_vs_original" in failed_checks
    assert "profit_loss_harm_count_vs_original" in failed_checks
    assert "final_answer_gate_decision" in failed_checks


def test_short_odds_suite_gate_cli_options_loader_and_main(tmp_path: Path) -> None:
    audit_report = _audit_report(
        [
            _audit_item(
                "item_a",
                slice_id="slice_a",
                actual_hit=False,
                profit_loss=-2.0,
                actual_return=0.0,
                hit_probability=0.62,
            )
        ]
    )
    final_answer_gate = _final_answer_gate_report(
        [
            _gate_item(
                "slice_a:2x1:single",
                item_key="item_a",
                original_hit=False,
                shadow_hit=True,
                original_profit=-2.0,
                shadow_profit=0.4,
                original_hit_probability=0.62,
                shadow_hit_probability=0.61,
            )
        ]
    )
    audit_path = tmp_path / "audit.json"
    final_answer_gate_path = tmp_path / "final_answer_gate.json"
    output_path = tmp_path / "suite_gate.json"
    audit_path.write_text(f"{audit_report.model_dump_json(indent=2)}\n", encoding="utf-8")
    final_answer_gate_path.write_text(
        f"{final_answer_gate.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--final-answer-gate-report",
            str(final_answer_gate_path),
            "--output-path",
            str(output_path),
            "--min-final-answer-count",
            "1",
            "--min-changed-final-answer-count",
            "1",
            "--min-final-answer-hit-rate-delta",
            "0.1",
            "--min-roi-delta",
            "0.2",
            "--min-profit-loss-delta",
            "0.3",
            "--max-harm-count-vs-original",
            "1",
            "--max-final-hit-harm-count-vs-original",
            "2",
            "--max-profit-loss-harm-count-vs-original",
            "3",
            "--min-average-hit-probability-delta-vs-original",
            "-0.03",
            "--no-require-final-answer-shadow-candidate",
            "--max-report-changed-items",
            "12",
            "--no-fail-process",
        ]
    )
    options = _options_from_args(args)

    assert options.min_final_answer_count == 1
    assert options.min_changed_final_answer_count == 1
    assert options.min_final_answer_hit_rate_delta == 0.1
    assert options.min_roi_delta == 0.2
    assert options.min_profit_loss_delta == 0.3
    assert options.max_harm_count_vs_original == 1
    assert options.max_final_hit_harm_count_vs_original == 2
    assert options.max_profit_loss_harm_count_vs_original == 3
    assert options.min_average_hit_probability_delta_vs_original == -0.03
    assert options.require_final_answer_shadow_candidate is False
    assert options.max_report_changed_items == 12

    loaded = load_historical_short_odds_final_answer_gate_report(final_answer_gate_path)
    assert loaded.report_key == final_answer_gate.report_key

    main(
        [
            "--audit-report",
            str(audit_path),
            "--final-answer-gate-report",
            str(final_answer_gate_path),
            "--output-path",
            str(output_path),
            "--min-final-answer-count",
            "1",
            "--min-changed-final-answer-count",
            "1",
        ]
    )

    assert output_path.exists()


def _audit_report(
    items: list[HistoricalCandidateMarginalAuditItem],
) -> HistoricalCandidateMarginalAuditReport:
    return HistoricalCandidateMarginalAuditReport(
        report_key="unit-test-candidate-replacement-audit",
        status="generated",
        slice_count=1,
        competition_count=1,
        final_answer_count=len(items),
        selected_leg_count=len(items),
        missed_leg_count=0,
        replacement_simulation_count=0,
        actual_replacement_opportunity_count=0,
        model_top_replacement_count=0,
        model_top_actual_improvement_count=0,
        model_top_actual_harm_count=0,
        items=items,
    )


def _audit_item(
    item_key: str,
    *,
    slice_id: str,
    actual_hit: bool,
    profit_loss: float,
    actual_return: float,
    hit_probability: float,
) -> HistoricalCandidateMarginalAuditItem:
    return HistoricalCandidateMarginalAuditItem(
        item_key=item_key,
        slice_id=slice_id,
        competition_id="EPL",
        final_answer_scenario_key="2x1:single",
        pass_type="2x1",
        mode="single",
        final_answer_actual_hit=actual_hit,
        selected_fixture_id=f"{item_key}_fixture",
        selected_market_type="1x2",
        selected_outcome="home_win",
        selected_probability=0.62,
        selected_decimal_odds=1.50,
        selected_model_edge=0.02,
        selected_score=0.60,
        leg_actual_hit=actual_hit,
        original_actual_return=actual_return,
        original_profit_loss=profit_loss,
        original_hit_probability=hit_probability,
        original_roi=profit_loss / 2.0,
        original_risk_score=1.0 - hit_probability,
        replacement_count=0,
        replacement_candidates=[],
    )


def _final_answer_gate_report(
    items: list[HistoricalShortOddsFinalAnswerGateItem],
    *,
    decision: str = "final_answer_shadow_candidate",
) -> HistoricalShortOddsFinalAnswerGateReport:
    return HistoricalShortOddsFinalAnswerGateReport(
        report_key="unit-test-short-odds-final-answer-gate",
        status="generated",
        decision=decision,
        source_audit_report_key="unit-test-candidate-replacement-audit",
        source_competition_gate_report_key="unit-test-competition-gate",
        generated_shadow_report_key="unit-test-shadow",
        profile_id="max_short_odds_within_deficit_v1",
        ready_competition_ids=["EPL"],
        isolated_competition_ids=[],
        changed_final_answer_count=len(items),
        original_final_answer_hit_count=sum(1 for item in items if item.original_actual_hit),
        shadow_final_answer_hit_count=sum(1 for item in items if item.shadow_actual_hit),
        final_answer_hit_delta_count_vs_original=sum(
            item.final_answer_hit_delta_vs_original for item in items
        ),
        original_profit_loss=sum(item.original_profit_loss for item in items),
        shadow_profit_loss=sum(item.shadow_profit_loss for item in items),
        profit_loss_delta_vs_original=sum(
            item.profit_loss_delta_vs_original for item in items
        ),
        improvement_count_vs_original=sum(
            1 for item in items if item.profit_loss_delta_vs_original > 0
        ),
        harm_count_vs_original=sum(
            1 for item in items if item.harmed_profit_loss_vs_original
        ),
        expected_hit_probability_regression_count_vs_original=sum(
            1 for item in items if item.expected_hit_probability_regressed_vs_original
        ),
        average_profit_loss_delta_vs_original=(
            sum(item.profit_loss_delta_vs_original for item in items) / len(items)
            if items
            else None
        ),
        average_hit_probability_delta_vs_original=(
            sum(item.hit_probability_delta_vs_original for item in items) / len(items)
            if items
            else None
        ),
        production_recommendation_changed=False,
        items=items,
    )


def _gate_item(
    final_answer_key: str,
    *,
    item_key: str,
    original_hit: bool,
    shadow_hit: bool,
    original_profit: float,
    shadow_profit: float,
    original_hit_probability: float,
    shadow_hit_probability: float,
) -> HistoricalShortOddsFinalAnswerGateItem:
    profit_delta = shadow_profit - original_profit
    hit_probability_delta = shadow_hit_probability - original_hit_probability
    return HistoricalShortOddsFinalAnswerGateItem(
        final_answer_key=final_answer_key,
        profile_id="max_short_odds_within_deficit_v1",
        selection_rule="highest_candidate_hit_probability",
        item_key=item_key,
        slice_id=final_answer_key.split(":", 1)[0],
        competition_id="EPL",
        final_answer_scenario_key="2x1:single",
        pass_type="2x1",
        mode="single",
        removed_fixture_id=f"{item_key}_fixture",
        removed_outcome="home_win",
        replacement_fixture_id=f"{item_key}_replacement",
        replacement_outcome="away_win",
        replacement_rank=2,
        original_actual_hit=original_hit,
        shadow_actual_hit=shadow_hit,
        final_answer_hit_delta_vs_original=int(shadow_hit) - int(original_hit),
        original_profit_loss=original_profit,
        shadow_profit_loss=shadow_profit,
        profit_loss_delta_vs_original=profit_delta,
        original_hit_probability=original_hit_probability,
        shadow_hit_probability=shadow_hit_probability,
        hit_probability_delta_vs_original=hit_probability_delta,
        replacement_hit_probability_delta_vs_model_top=-0.01,
        decimal_odds_delta_vs_model_top=0.02,
        model_edge_delta_vs_model_top=0.01,
        quality_score_delta_vs_model_top=-0.01,
        expected_hit_probability_regressed_vs_original=hit_probability_delta < 0,
        harmed_profit_loss_vs_original=profit_delta < 0,
    )
