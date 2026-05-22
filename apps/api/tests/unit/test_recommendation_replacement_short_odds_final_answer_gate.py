from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_short_odds_competition_gate import (
    HistoricalShortOddsCompetitionGateReport,
    HistoricalShortOddsCompetitionGateSet,
)
from nutmeg.recommendations.replacement_short_odds_final_answer_gate import (
    HistoricalShortOddsFinalAnswerGateOptions,
    _options_from_args,
    _parse_args,
    build_historical_short_odds_final_answer_gate_report,
    load_historical_short_odds_competition_gate_report,
    main,
)


def test_short_odds_final_answer_gate_limits_one_replacement_per_answer() -> None:
    model_top_a = _replacement(
        rank=1,
        fixture_id="model_top_a",
        simulated_hit_probability=0.60,
        profit_loss_delta=0.0,
    )
    candidate_a = _replacement(
        rank=2,
        fixture_id="candidate_a",
        decimal_odds=1.18,
        simulated_hit_probability=0.589,
        simulated_actual_hit=True,
        simulated_profit_loss=-0.8,
        profit_loss_delta=1.2,
    )
    model_top_b = _replacement(
        rank=1,
        fixture_id="model_top_b",
        simulated_hit_probability=0.61,
        profit_loss_delta=0.0,
    )
    candidate_b = _replacement(
        rank=2,
        fixture_id="candidate_b",
        decimal_odds=1.17,
        simulated_hit_probability=0.604,
        simulated_actual_hit=True,
        simulated_profit_loss=0.4,
        profit_loss_delta=2.4,
    )
    isolated_candidate = _replacement(
        rank=2,
        fixture_id="isolated_candidate",
        decimal_odds=1.18,
        simulated_hit_probability=0.59,
        simulated_actual_hit=True,
        simulated_profit_loss=1.0,
        profit_loss_delta=3.0,
    )

    report = build_historical_short_odds_final_answer_gate_report(
        _audit_report(
            [
                _item(
                    "item_a",
                    model_top=model_top_a,
                    actual_best=candidate_a,
                    replacement_candidates=[model_top_a, candidate_a],
                ),
                _item(
                    "item_b",
                    selected_fixture_id="selected_b",
                    model_top=model_top_b,
                    actual_best=candidate_b,
                    replacement_candidates=[model_top_b, candidate_b],
                ),
                _item(
                    "item_c",
                    competition_id="ESP_LA_LIGA",
                    selected_fixture_id="selected_c",
                    model_top=model_top_a,
                    actual_best=isolated_candidate,
                    replacement_candidates=[model_top_a, isolated_candidate],
                ),
            ]
        ),
        _competition_gate_report(),
        options=HistoricalShortOddsFinalAnswerGateOptions(
            min_changed_final_answer_count=1,
        ),
    )

    assert report.decision == "final_answer_shadow_candidate"
    assert report.production_recommendation_changed is False
    assert report.ready_competition_ids == ["EPL"]
    assert report.isolated_competition_ids == ["ESP_LA_LIGA"]
    assert report.changed_final_answer_count == 1
    assert report.shadow_final_answer_hit_count == 1
    assert report.final_answer_hit_delta_count_vs_original == 1
    assert report.harm_count_vs_original == 0
    assert report.profit_loss_delta_vs_original == 2.4
    assert report.items[0].item_key == "item_b"
    assert report.items[0].replacement_fixture_id == "candidate_b"


def test_short_odds_final_answer_gate_rejects_profit_harm() -> None:
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        simulated_hit_probability=0.61,
        simulated_profit_loss=-4.0,
        profit_loss_delta=-2.0,
    )
    harmful_candidate = _replacement(
        rank=2,
        fixture_id="harmful_candidate",
        decimal_odds=1.19,
        simulated_hit_probability=0.604,
        simulated_actual_hit=False,
        simulated_profit_loss=-3.0,
        profit_loss_delta=-1.0,
    )
    actual_best_candidate = _replacement(
        rank=3,
        fixture_id="actual_best_candidate",
        decimal_odds=1.17,
        simulated_hit_probability=0.606,
        simulated_actual_hit=True,
        simulated_profit_loss=0.2,
        profit_loss_delta=2.2,
    )

    report = build_historical_short_odds_final_answer_gate_report(
        _audit_report(
            [
                _item(
                    "item_a",
                    model_top=model_top,
                    actual_best=actual_best_candidate,
                    replacement_candidates=[
                        model_top,
                        harmful_candidate,
                        actual_best_candidate,
                    ],
                )
            ]
        ),
        _competition_gate_report(),
        options=HistoricalShortOddsFinalAnswerGateOptions(
            min_changed_final_answer_count=1,
        ),
    )

    assert report.decision == "rejected"
    assert report.harm_count_vs_original == 1
    assert "profit_loss_delta_vs_original_below_threshold" in report.decision_reasons
    assert "harm_count_vs_original_above_threshold" in report.decision_reasons


def test_short_odds_final_answer_gate_supports_medium_price_model_edge_profile() -> None:
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        probability=0.65,
        decimal_odds=1.70,
        model_edge=0.00,
        simulated_hit_probability=0.66,
        profit_loss_delta=0.0,
    )
    higher_price_candidate = _replacement(
        rank=2,
        fixture_id="higher_price_candidate",
        probability=0.43,
        decimal_odds=2.10,
        model_edge=0.01,
        simulated_hit_probability=0.61,
        simulated_actual_hit=True,
        simulated_profit_loss=0.5,
        profit_loss_delta=1.0,
    )
    max_edge_candidate = _replacement(
        rank=3,
        fixture_id="max_edge_candidate",
        probability=0.44,
        decimal_odds=1.90,
        model_edge=0.08,
        simulated_hit_probability=0.60,
        simulated_actual_hit=True,
        simulated_profit_loss=1.8,
        profit_loss_delta=3.0,
    )

    report = build_historical_short_odds_final_answer_gate_report(
        _audit_report(
            [
                _item(
                    "item_a",
                    original_hit_probability=0.58,
                    model_top=model_top,
                    actual_best=max_edge_candidate,
                    replacement_candidates=[
                        model_top,
                        higher_price_candidate,
                        max_edge_candidate,
                    ],
                )
            ]
        ),
        _competition_gate_report(
            profile_id="max_model_edge_within_deficit_v1",
        ),
        options=HistoricalShortOddsFinalAnswerGateOptions(
            profile_id="max_model_edge_within_deficit_v1",
            shadow_selection_rule="max_model_edge_within_deficit",
            min_changed_final_answer_count=1,
            min_replacement_probability=0.35,
            min_replacement_decimal_odds=1.75,
            max_replacement_decimal_odds=2.30,
            min_candidate_hit_probability_delta_vs_model_top=-1.0,
            max_candidate_hit_probability_delta_vs_model_top=-0.02,
            min_average_hit_probability_delta_vs_original=0.0,
        ),
    )

    assert report.decision == "final_answer_shadow_candidate"
    assert report.profile_id == "max_model_edge_within_deficit_v1"
    assert report.changed_final_answer_count == 1
    assert report.final_answer_hit_delta_count_vs_original == 1
    assert report.harm_count_vs_original == 0
    assert report.expected_hit_probability_regression_count_vs_original == 0
    assert report.items[0].replacement_fixture_id == "max_edge_candidate"
    assert report.items[0].shadow_hit_probability == 0.60
    assert report.summary_json["options"]["min_replacement_decimal_odds"] == 1.75
    assert report.summary_json["options"]["shadow_selection_rule"] == (
        "max_model_edge_within_deficit"
    )


def test_short_odds_final_answer_gate_original_safe_subset_guard() -> None:
    unsafe_model_top = _replacement(
        rank=1,
        fixture_id="unsafe_model_top",
        probability=0.65,
        decimal_odds=1.70,
        model_edge=0.00,
        simulated_hit_probability=0.66,
        profit_loss_delta=0.0,
    )
    unsafe_candidate = _replacement(
        rank=2,
        fixture_id="unsafe_candidate",
        probability=0.43,
        decimal_odds=1.90,
        model_edge=0.08,
        simulated_hit_probability=0.61,
        simulated_actual_hit=False,
        simulated_profit_loss=-2.0,
        profit_loss_delta=3.0,
    )
    safe_model_top = _replacement(
        rank=1,
        fixture_id="safe_model_top",
        probability=0.66,
        decimal_odds=1.68,
        model_edge=0.00,
        simulated_hit_probability=0.65,
        profit_loss_delta=0.0,
    )
    safe_candidate = _replacement(
        rank=2,
        fixture_id="safe_candidate",
        probability=0.42,
        decimal_odds=1.88,
        model_edge=0.07,
        simulated_hit_probability=0.59,
        simulated_actual_hit=True,
        simulated_profit_loss=1.2,
        profit_loss_delta=2.5,
    )

    report = build_historical_short_odds_final_answer_gate_report(
        _audit_report(
            [
                _item(
                    "unsafe_item",
                    final_answer_actual_hit=True,
                    original_profit_loss=1.4,
                    original_hit_probability=0.65,
                    model_top=unsafe_model_top,
                    actual_best=unsafe_candidate,
                    replacement_candidates=[unsafe_model_top, unsafe_candidate],
                ),
                _item(
                    "safe_item",
                    original_hit_probability=0.58,
                    model_top=safe_model_top,
                    actual_best=safe_candidate,
                    replacement_candidates=[safe_model_top, safe_candidate],
                ),
            ]
        ),
        _competition_gate_report(
            profile_id="max_model_edge_within_deficit_v1",
        ),
        options=HistoricalShortOddsFinalAnswerGateOptions(
            profile_id="max_model_edge_within_deficit_v1",
            shadow_selection_rule="max_model_edge_within_deficit",
            min_changed_final_answer_count=1,
            min_replacement_probability=0.35,
            min_replacement_decimal_odds=1.75,
            max_replacement_decimal_odds=2.30,
            min_candidate_hit_probability_delta_vs_model_top=-1.0,
            max_candidate_hit_probability_delta_vs_model_top=-0.02,
            min_average_hit_probability_delta_vs_original=0.0,
            min_item_hit_probability_delta_vs_original=-0.02,
            exclude_original_hit_harm=True,
        ),
    )

    assert report.decision == "final_answer_shadow_candidate"
    assert report.candidate_replacement_option_count == 2
    assert report.original_safe_replacement_option_count == 1
    assert report.original_safe_excluded_count == 1
    assert report.original_safe_exclusion_counts_json == {
        "item_hit_probability_delta_vs_original_below_threshold": 1,
        "original_hit_harm_excluded": 1,
    }
    assert report.changed_final_answer_count == 1
    assert report.final_answer_hit_delta_count_vs_original == 1
    assert report.harm_count_vs_original == 0
    assert report.items[0].replacement_fixture_id == "safe_candidate"
    assert "short_odds_final_answer_gate:original_safe_subset_applied" in (
        report.warnings
    )


def test_short_odds_final_answer_gate_cli_options_loader_and_main(
    tmp_path: Path,
) -> None:
    model_top = _replacement(rank=1, fixture_id="model_top")
    candidate = _replacement(
        rank=2,
        fixture_id="candidate",
        decimal_odds=1.18,
        simulated_hit_probability=0.604,
        simulated_actual_hit=True,
        simulated_profit_loss=0.4,
        profit_loss_delta=2.4,
    )
    audit_report = _audit_report(
        [
            _item(
                "item_a",
                model_top=model_top,
                actual_best=candidate,
                replacement_candidates=[model_top, candidate],
            )
        ]
    )
    competition_gate_report = _competition_gate_report()
    audit_path = tmp_path / "audit.json"
    competition_gate_path = tmp_path / "competition_gate.json"
    output_path = tmp_path / "final_answer_gate.json"
    audit_path.write_text(f"{audit_report.model_dump_json(indent=2)}\n", encoding="utf-8")
    competition_gate_path.write_text(
        f"{competition_gate_report.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--competition-gate-report",
            str(competition_gate_path),
            "--output-path",
            str(output_path),
            "--profile-id",
            "max_short_odds_within_deficit_v1",
            "--ready-competitions",
            "EPL,FRA_LIGUE_1",
            "--selection-rule",
            "highest_decimal_odds_delta",
            "--shadow-selection-rule",
            "max_model_edge_within_deficit",
            "--min-changed-final-answer-count",
            "1",
            "--min-final-answer-hit-delta-count-vs-original",
            "1",
            "--min-profit-loss-delta-vs-original",
            "0.2",
            "--min-average-hit-probability-delta-vs-original",
            "-0.03",
            "--max-harm-count-vs-original",
            "1",
            "--min-item-hit-probability-delta-vs-original",
            "-0.01",
            "--exclude-original-hit-harm",
            "--min-replacement-probability",
            "0.60",
            "--min-replacement-decimal-odds",
            "1.20",
            "--max-replacement-decimal-odds",
            "1.60",
            "--min-candidate-hit-probability-delta-vs-model-top",
            "-0.02",
            "--max-candidate-hit-probability-delta-vs-model-top",
            "0.0",
            "--min-decimal-odds-delta-vs-model-top",
            "0.01",
            "--max-report-items",
            "12",
        ]
    )
    options = _options_from_args(args)

    assert options.ready_competition_ids == ("EPL", "FRA_LIGUE_1")
    assert options.selection_rule == "highest_decimal_odds_delta"
    assert options.shadow_selection_rule == "max_model_edge_within_deficit"
    assert options.min_changed_final_answer_count == 1
    assert options.min_final_answer_hit_delta_count_vs_original == 1
    assert options.min_profit_loss_delta_vs_original == 0.2
    assert options.min_average_hit_probability_delta_vs_original == -0.03
    assert options.max_harm_count_vs_original == 1
    assert options.min_item_hit_probability_delta_vs_original == -0.01
    assert options.exclude_original_hit_harm is True
    assert options.min_replacement_probability == 0.60
    assert options.min_replacement_decimal_odds == 1.20
    assert options.max_replacement_decimal_odds == 1.60
    assert options.min_candidate_hit_probability_delta_vs_model_top == -0.02
    assert options.max_candidate_hit_probability_delta_vs_model_top == 0.0
    assert options.min_decimal_odds_delta_vs_model_top == 0.01
    assert options.max_report_items == 12

    loaded = load_historical_short_odds_competition_gate_report(competition_gate_path)
    assert loaded.report_key == competition_gate_report.report_key

    main(
        [
            "--audit-report",
            str(audit_path),
            "--competition-gate-report",
            str(competition_gate_path),
            "--output-path",
            str(output_path),
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


def _competition_gate_report(
    *,
    profile_id: str = "max_short_odds_within_deficit_v1",
) -> HistoricalShortOddsCompetitionGateReport:
    profile_set = HistoricalShortOddsCompetitionGateSet(
        profile_id=profile_id,
        decision="final_answer_gate_ready",
        decision_reasons=["isolated_competitions_require_separate_guard"],
        ready_competition_ids=["EPL"],
        isolated_competition_ids=["ESP_LA_LIGA"],
        evaluated_item_count=2,
        changed_count_vs_model_top=2,
        simulated_actual_hit_delta_count_vs_model_top=1,
        replacement_leg_hit_delta_count_vs_model_top=1,
        improvement_count_vs_model_top=2,
        harm_count_vs_model_top=0,
        selected_actual_best_count=2,
    )
    return HistoricalShortOddsCompetitionGateReport(
        report_key="unit-test-short-odds-competition-gate",
        status="generated",
        source_shadow_report_key="unit-test-shadow",
        profile_count=1,
        candidate_count=2,
        final_answer_gate_ready_count=1,
        holdout_watchlist_count=0,
        isolated_rejected_count=1,
        ready_competition_ids=["EPL"],
        isolated_competition_ids=["ESP_LA_LIGA"],
        production_recommendation_changed=False,
        profile_sets=[profile_set],
        best_profile_set=profile_set,
    )


def _item(
    item_key: str,
    *,
    competition_id: str = "EPL",
    selected_fixture_id: str = "selected_a",
    final_answer_actual_hit: bool = False,
    original_profit_loss: float = -2.0,
    original_hit_probability: float = 0.62,
    model_top: HistoricalCandidateReplacementSimulation,
    actual_best: HistoricalCandidateReplacementSimulation,
    replacement_candidates: list[HistoricalCandidateReplacementSimulation],
) -> HistoricalCandidateMarginalAuditItem:
    return HistoricalCandidateMarginalAuditItem(
        item_key=item_key,
        slice_id="unit_slice",
        competition_id=competition_id,
        final_answer_scenario_key="2x1:single",
        pass_type="2x1",
        mode="single",
        final_answer_actual_hit=final_answer_actual_hit,
        selected_fixture_id=selected_fixture_id,
        selected_market_type="1x2",
        selected_outcome="home_win",
        selected_probability=0.80,
        selected_decimal_odds=1.12,
        selected_model_edge=-0.03,
        selected_score=0.60,
        leg_actual_hit=False,
        original_actual_return=0.0,
        original_profit_loss=original_profit_loss,
        original_hit_probability=original_hit_probability,
        original_roi=-1.0,
        original_risk_score=0.38,
        replacement_count=len(replacement_candidates),
        model_top_replacement=model_top,
        actual_best_replacement=actual_best,
        replacement_candidates=replacement_candidates,
    )


def _replacement(
    *,
    rank: int,
    fixture_id: str,
    probability: float = 0.80,
    decimal_odds: float = 1.12,
    model_edge: float = -0.03,
    score: float = 0.60,
    quality: float = 0.50,
    simulated_hit_probability: float = 0.61,
    simulated_actual_hit: bool = False,
    simulated_profit_loss: float = -2.0,
    profit_loss_delta: float = 0.0,
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
        replacement_leg_actual_hit=simulated_actual_hit,
        simulated_actual_hit=simulated_actual_hit,
        simulated_actual_return=max(simulated_profit_loss + 2.0, 0.0),
        simulated_profit_loss=simulated_profit_loss,
        simulated_hit_probability=simulated_hit_probability,
        simulated_roi=simulated_profit_loss / 2.0,
        simulated_risk_score=1.0 - simulated_hit_probability,
        actual_return_delta=profit_loss_delta,
        profit_loss_delta=profit_loss_delta,
        hit_probability_delta=simulated_hit_probability - 0.62,
        roi_delta=simulated_profit_loss / 2.0,
        risk_score_delta=0.0,
        decision="actual_improved" if profit_loss_delta > 0 else "actual_unchanged",
    )
