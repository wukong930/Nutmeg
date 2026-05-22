from __future__ import annotations

from pathlib import Path

import pytest

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_reranker_weight_experiment import (
    LEAKAGE_EXCLUDED_FIELDS,
    HistoricalReplacementRerankerProfile,
    HistoricalReplacementRerankerWeightExperimentOptions,
    _options_from_args,
    _parse_args,
    _selected_profiles,
    build_historical_replacement_reranker_weight_experiment_report,
    default_historical_replacement_reranker_profiles,
    main,
)


def test_replacement_reranker_weight_experiment_uses_pre_match_features() -> None:
    baseline = default_historical_replacement_reranker_profiles()[0]
    edge_profile = HistoricalReplacementRerankerProfile(
        profile_id="unit_edge_capture",
        description="Unit profile that favors visible edge and price.",
        model_edge_weight=0.55,
        decimal_odds_weight=0.35,
        replacement_quality_weight=0.10,
    )
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        probability=0.56,
        decimal_odds=1.80,
        model_edge=-0.03,
        score=0.61,
        quality=0.58,
        profit_loss_delta=0.0,
    )
    actual_best = _replacement(
        rank=3,
        fixture_id="actual_best",
        probability=0.31,
        decimal_odds=3.40,
        model_edge=0.05,
        score=0.46,
        quality=0.42,
        profit_loss_delta=6.8,
    )

    report = build_historical_replacement_reranker_weight_experiment_report(
        _audit_report([_item("item_a", model_top=model_top, actual_best=actual_best)]),
        options=HistoricalReplacementRerankerWeightExperimentOptions(
            profiles=(baseline, edge_profile),
            min_evaluated_item_count=1,
            max_hit_probability_regression_rate=1.0,
        ),
    )

    edge_summary = next(
        summary
        for summary in report.profile_summaries
        if summary.profile_id == "unit_edge_capture"
    )
    edge_item = next(
        item
        for item in report.items
        if item.profile_id == "unit_edge_capture"
    )

    assert report.pre_match_feature_names
    assert "profit_loss_delta" in report.leakage_excluded_fields
    assert set(LEAKAGE_EXCLUDED_FIELDS).isdisjoint(edge_summary.used_feature_names)
    assert edge_summary.selected_actual_best_count == 1
    assert edge_summary.improvement_count_vs_model_top == 1
    assert edge_summary.average_profit_loss_delta_vs_model_top == 6.8
    assert edge_item.selected_actual_best is True
    assert edge_item.profit_loss_delta_vs_model_top == 6.8
    assert "captured_actual_best_for_evaluation" in edge_item.reason_codes


def test_replacement_reranker_weight_experiment_respects_probability_guard() -> None:
    guarded_profile = HistoricalReplacementRerankerProfile(
        profile_id="unit_probability_guard",
        model_edge_weight=0.60,
        decimal_odds_weight=0.40,
        min_probability=0.40,
    )
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        probability=0.51,
        decimal_odds=1.90,
        model_edge=-0.02,
        profit_loss_delta=0.0,
    )
    actual_best = _replacement(
        rank=4,
        fixture_id="actual_best",
        probability=0.29,
        decimal_odds=3.60,
        model_edge=0.05,
        profit_loss_delta=5.2,
    )

    report = build_historical_replacement_reranker_weight_experiment_report(
        _audit_report([_item("item_a", model_top=model_top, actual_best=actual_best)]),
        options=HistoricalReplacementRerankerWeightExperimentOptions(
            profiles=(guarded_profile,),
            min_evaluated_item_count=1,
        ),
    )

    summary = report.profile_summaries[0]
    item = report.items[0]

    assert "min_probability_guard" in summary.used_feature_names
    assert summary.selected_model_top_count == 1
    assert summary.selected_actual_best_count == 0
    assert item.selected_model_top is True
    assert item.selected_actual_best is False


def test_replacement_reranker_weight_experiment_respects_hit_probability_guard() -> None:
    edge_profile = HistoricalReplacementRerankerProfile(
        profile_id="unit_edge_guarded",
        model_edge_weight=0.60,
        decimal_odds_weight=0.40,
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
        probability=0.30,
        decimal_odds=3.40,
        model_edge=0.05,
        profit_loss_delta=5.0,
    )

    report = build_historical_replacement_reranker_weight_experiment_report(
        _audit_report([_item("item_a", model_top=model_top, actual_best=actual_best)]),
        options=HistoricalReplacementRerankerWeightExperimentOptions(
            profiles=(edge_profile,),
            min_candidate_hit_probability_delta_vs_model_top=0.0,
            min_evaluated_item_count=1,
        ),
    )

    summary = report.profile_summaries[0]
    item = report.items[0]

    assert report.candidate_hit_probability_guard_filtered_count == 1
    assert summary.hit_probability_guard_filtered_count == 1
    assert "min_candidate_hit_probability_delta_vs_model_top_guard" in (
        summary.used_feature_names
    )
    assert item.selected_model_top is True
    assert item.hit_probability_delta_vs_model_top == 0.0


def test_replacement_reranker_weight_experiment_cli_options_and_main(
    tmp_path: Path,
) -> None:
    audit_report = _audit_report(
        [
            _item(
                "item_a",
                model_top=_replacement(rank=1, fixture_id="model_top"),
                actual_best=_replacement(
                    rank=3,
                    fixture_id="actual_best",
                    profit_loss_delta=2.4,
                ),
            )
        ]
    )
    audit_path = tmp_path / "audit.json"
    output_path = tmp_path / "weight_experiment.json"
    audit_path.write_text(f"{audit_report.model_dump_json(indent=2)}\n", encoding="utf-8")

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--output-path",
            str(output_path),
            "--profile-ids",
            "current_quality_baseline,edge_value_v1",
            "--min-actual-best-profit-loss-delta",
            "0.5",
            "--min-profit-loss-gap",
            "0.1",
            "--min-candidate-hit-probability-delta-vs-model-top",
            "0.0",
            "--min-evaluated-item-count",
            "1",
            "--max-hit-probability-regression-rate",
            "0.5",
            "--min-average-profit-loss-delta-vs-model-top",
            "0.2",
            "--max-report-items",
            "10",
        ]
    )
    options = _options_from_args(args)

    assert [profile.profile_id for profile in options.profiles] == [
        "current_quality_baseline",
        "edge_value_v1",
    ]
    assert options.min_actual_best_profit_loss_delta == 0.5
    assert options.min_profit_loss_gap == 0.1
    assert options.min_candidate_hit_probability_delta_vs_model_top == 0.0
    assert options.min_evaluated_item_count == 1
    assert options.max_hit_probability_regression_rate == 0.5
    assert options.min_average_profit_loss_delta_vs_model_top == 0.2
    assert options.max_report_items == 10

    main(
        [
            "--audit-report",
            str(audit_path),
            "--output-path",
            str(output_path),
            "--profile-ids",
            "current_quality_baseline",
            "--min-evaluated-item-count",
            "1",
        ]
    )

    assert output_path.exists()
    with pytest.raises(SystemExit):
        _selected_profiles("missing_profile")


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
