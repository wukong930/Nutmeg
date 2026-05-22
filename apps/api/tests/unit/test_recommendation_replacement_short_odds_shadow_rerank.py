from __future__ import annotations

from pathlib import Path

import pytest

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_short_odds_shadow_rerank import (
    OFFLINE_SHORT_ODDS_SHADOW_EVALUATION_FIELDS,
    HistoricalShortOddsShadowRerankOptions,
    _options_from_args,
    _parse_args,
    _selected_profiles,
    build_historical_short_odds_shadow_rerank_report,
    default_historical_short_odds_shadow_profiles,
    main,
)


def test_short_odds_shadow_rerank_uses_pre_match_features() -> None:
    baseline = default_historical_short_odds_shadow_profiles()[0]
    max_short_odds = default_historical_short_odds_shadow_profiles()[1]
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        probability=0.82,
        decimal_odds=1.12,
        model_edge=-0.04,
        score=0.68,
        quality=0.52,
        simulated_hit_probability=0.62,
        profit_loss_delta=0.0,
    )
    shadow_candidate = _replacement(
        rank=4,
        fixture_id="shadow_candidate",
        probability=0.80,
        decimal_odds=1.18,
        model_edge=-0.02,
        score=0.65,
        quality=0.49,
        simulated_hit_probability=0.609,
        profit_loss_delta=1.8,
    )
    lower_price_candidate = _replacement(
        rank=2,
        fixture_id="lower_price_candidate",
        probability=0.81,
        decimal_odds=1.14,
        model_edge=-0.03,
        score=0.66,
        quality=0.50,
        simulated_hit_probability=0.615,
        profit_loss_delta=0.0,
    )

    report = build_historical_short_odds_shadow_rerank_report(
        _audit_report(
            [
                _item(
                    "item_a",
                    model_top=model_top,
                    actual_best=shadow_candidate,
                    replacement_candidates=[
                        model_top,
                        lower_price_candidate,
                        shadow_candidate,
                    ],
                )
            ]
        ),
        options=HistoricalShortOddsShadowRerankOptions(
            profiles=(baseline, max_short_odds),
            focus_competition_ids=("UNIT_LEAGUE",),
            min_evaluated_item_count=1,
        ),
    )

    summary = next(
        item
        for item in report.profile_summaries
        if item.profile_id == "max_short_odds_within_deficit_v1"
    )
    shadow_item = next(
        item
        for item in report.items
        if item.profile_id == "max_short_odds_within_deficit_v1"
    )

    assert report.production_recommendation_changed is False
    assert "profit_loss_delta" in report.offline_evaluation_fields
    assert set(OFFLINE_SHORT_ODDS_SHADOW_EVALUATION_FIELDS).isdisjoint(
        summary.used_feature_names
    )
    assert summary.status == "shadow_watchlist"
    assert summary.changed_count_vs_model_top == 1
    assert summary.selected_actual_best_count == 1
    assert summary.simulated_actual_hit_delta_count_vs_model_top == 1
    assert summary.average_profit_loss_delta_vs_model_top == 1.8
    assert summary.average_hit_probability_delta_vs_model_top == pytest.approx(-0.011)
    assert shadow_item.shadow_replacement_fixture_id == "shadow_candidate"
    assert shadow_item.selected_actual_best is True
    assert "lower_expected_hit_probability_than_model_top" in shadow_item.reason_codes


def test_short_odds_shadow_rerank_respects_competition_and_deficit_guards() -> None:
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        probability=0.82,
        decimal_odds=1.12,
        simulated_hit_probability=0.62,
        profit_loss_delta=0.0,
    )
    large_deficit_candidate = _replacement(
        rank=3,
        fixture_id="large_deficit",
        probability=0.75,
        decimal_odds=1.24,
        simulated_hit_probability=0.58,
        profit_loss_delta=2.0,
    )
    outside_focus_candidate = _replacement(
        rank=2,
        fixture_id="outside_focus",
        probability=0.80,
        decimal_odds=1.18,
        simulated_hit_probability=0.612,
        profit_loss_delta=2.0,
    )
    max_short_odds = default_historical_short_odds_shadow_profiles()[1]

    report = build_historical_short_odds_shadow_rerank_report(
        _audit_report(
            [
                _item(
                    "item_a",
                    competition_id="UNIT_LEAGUE",
                    model_top=model_top,
                    actual_best=large_deficit_candidate,
                    replacement_candidates=[model_top, large_deficit_candidate],
                ),
                _item(
                    "item_b",
                    competition_id="OUTSIDE_LEAGUE",
                    model_top=model_top,
                    actual_best=outside_focus_candidate,
                    replacement_candidates=[model_top, outside_focus_candidate],
                ),
            ]
        ),
        options=HistoricalShortOddsShadowRerankOptions(
            profiles=(max_short_odds,),
            focus_competition_ids=("UNIT_LEAGUE",),
            min_evaluated_item_count=1,
        ),
    )

    summary = report.profile_summaries[0]
    item = report.items[0]

    assert report.eligible_item_count == 1
    assert summary.changed_count_vs_model_top == 0
    assert summary.qualified_candidate_count == 0
    assert summary.status == "rejected"
    assert item.selected_model_top is True
    assert "no_qualified_short_odds_shadow_candidate" in item.reason_codes


def test_short_odds_shadow_rerank_can_apply_decimal_odds_floor() -> None:
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        probability=0.82,
        decimal_odds=1.70,
        simulated_hit_probability=0.62,
        profit_loss_delta=0.0,
    )
    below_floor_candidate = _replacement(
        rank=2,
        fixture_id="below_floor",
        probability=0.80,
        decimal_odds=1.72,
        simulated_hit_probability=0.61,
        profit_loss_delta=1.2,
    )
    in_band_candidate = _replacement(
        rank=3,
        fixture_id="in_band",
        probability=0.78,
        decimal_odds=1.90,
        simulated_hit_probability=0.609,
        profit_loss_delta=1.8,
    )
    max_short_odds = default_historical_short_odds_shadow_profiles()[1]

    report = build_historical_short_odds_shadow_rerank_report(
        _audit_report(
            [
                _item(
                    "item_a",
                    model_top=model_top,
                    actual_best=in_band_candidate,
                    replacement_candidates=[
                        model_top,
                        below_floor_candidate,
                        in_band_candidate,
                    ],
                )
            ]
        ),
        options=HistoricalShortOddsShadowRerankOptions(
            profiles=(max_short_odds,),
            focus_competition_ids=("UNIT_LEAGUE",),
            min_replacement_decimal_odds=1.75,
            max_replacement_decimal_odds=2.30,
            min_evaluated_item_count=1,
        ),
    )

    item = report.items[0]

    assert item.qualified_candidate_count == 1
    assert item.shadow_replacement_fixture_id == "in_band"
    assert item.selected_actual_best is True


def test_short_odds_shadow_rerank_probability_preserving_model_edge_bucket() -> None:
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        probability=0.82,
        decimal_odds=1.70,
        model_edge=0.00,
        simulated_hit_probability=0.62,
        profit_loss_delta=0.0,
    )
    nearest_probability_candidate = _replacement(
        rank=2,
        fixture_id="nearest_probability",
        probability=0.80,
        decimal_odds=1.86,
        model_edge=0.01,
        simulated_hit_probability=0.608,
        profit_loss_delta=1.0,
    )
    edge_candidate_same_probability_bucket = _replacement(
        rank=3,
        fixture_id="edge_candidate",
        probability=0.79,
        decimal_odds=1.82,
        model_edge=0.08,
        simulated_hit_probability=0.601,
        profit_loss_delta=1.8,
    )
    profile = next(
        profile
        for profile in default_historical_short_odds_shadow_profiles()
        if profile.profile_id == "probability_preserving_model_edge_v1"
    )

    report = build_historical_short_odds_shadow_rerank_report(
        _audit_report(
            [
                _item(
                    "item_a",
                    model_top=model_top,
                    actual_best=edge_candidate_same_probability_bucket,
                    replacement_candidates=[
                        model_top,
                        nearest_probability_candidate,
                        edge_candidate_same_probability_bucket,
                    ],
                )
            ]
        ),
        options=HistoricalShortOddsShadowRerankOptions(
            profiles=(profile,),
            focus_competition_ids=("UNIT_LEAGUE",),
            min_replacement_probability=0.70,
            min_replacement_decimal_odds=1.75,
            max_replacement_decimal_odds=2.30,
            min_candidate_hit_probability_delta_vs_model_top=-0.03,
            max_candidate_hit_probability_delta_vs_model_top=0.0,
            min_evaluated_item_count=1,
        ),
    )

    summary = report.profile_summaries[0]
    item = report.items[0]

    assert profile.profile_id == "probability_preserving_model_edge_v1"
    assert summary.used_feature_names[-1] == "probability_preserving_model_edge"
    assert item.shadow_replacement_fixture_id == "edge_candidate"
    assert item.selected_actual_best is True
    assert item.hit_probability_delta_vs_model_top == pytest.approx(-0.019)


def test_short_odds_shadow_rerank_probability_preserving_quality_score_bucket() -> None:
    model_top = _replacement(
        rank=1,
        fixture_id="model_top",
        probability=0.82,
        decimal_odds=1.70,
        model_edge=0.00,
        score=0.66,
        quality=0.60,
        simulated_hit_probability=0.62,
        profit_loss_delta=0.0,
    )
    edge_candidate = _replacement(
        rank=2,
        fixture_id="edge_candidate",
        probability=0.80,
        decimal_odds=1.86,
        model_edge=0.08,
        score=0.62,
        quality=0.61,
        simulated_hit_probability=0.609,
        profit_loss_delta=1.0,
    )
    quality_candidate_same_probability_bucket = _replacement(
        rank=3,
        fixture_id="quality_candidate",
        probability=0.79,
        decimal_odds=1.82,
        model_edge=0.02,
        score=0.74,
        quality=0.76,
        simulated_hit_probability=0.601,
        profit_loss_delta=1.8,
    )
    profile = next(
        profile
        for profile in default_historical_short_odds_shadow_profiles()
        if profile.profile_id == "probability_preserving_quality_score_v1"
    )

    report = build_historical_short_odds_shadow_rerank_report(
        _audit_report(
            [
                _item(
                    "item_a",
                    model_top=model_top,
                    actual_best=quality_candidate_same_probability_bucket,
                    replacement_candidates=[
                        model_top,
                        edge_candidate,
                        quality_candidate_same_probability_bucket,
                    ],
                )
            ]
        ),
        options=HistoricalShortOddsShadowRerankOptions(
            profiles=(profile,),
            focus_competition_ids=("UNIT_LEAGUE",),
            min_replacement_probability=0.70,
            min_replacement_decimal_odds=1.75,
            max_replacement_decimal_odds=2.30,
            min_candidate_hit_probability_delta_vs_model_top=-0.03,
            max_candidate_hit_probability_delta_vs_model_top=0.0,
            min_evaluated_item_count=1,
        ),
    )

    summary = report.profile_summaries[0]
    item = report.items[0]

    assert summary.used_feature_names[-1] == "probability_preserving_quality_score"
    assert item.shadow_replacement_fixture_id == "quality_candidate"
    assert item.selected_actual_best is True
    assert item.hit_probability_delta_vs_model_top == pytest.approx(-0.019)


def test_short_odds_shadow_rerank_cli_options_and_main(tmp_path: Path) -> None:
    audit_report = _audit_report(
        [
            _item(
                "item_a",
                model_top=_replacement(rank=1, fixture_id="model_top"),
                actual_best=_replacement(
                    rank=2,
                    fixture_id="actual_best",
                    decimal_odds=1.18,
                    simulated_hit_probability=0.61,
                    profit_loss_delta=1.4,
                ),
            )
        ]
    )
    audit_path = tmp_path / "audit.json"
    output_path = tmp_path / "short_odds_shadow.json"
    audit_path.write_text(f"{audit_report.model_dump_json(indent=2)}\n", encoding="utf-8")

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--output-path",
            str(output_path),
            "--profile-ids",
            "current_model_top,probability_preserving_model_edge_v1",
            "--focus-competitions",
            "UNIT_LEAGUE,EPL",
            "--min-actual-best-profit-loss-delta",
            "0.5",
            "--min-profit-loss-gap",
            "0.1",
            "--min-replacement-probability",
            "0.6",
            "--min-replacement-decimal-odds",
            "1.2",
            "--max-replacement-decimal-odds",
            "1.6",
            "--min-candidate-hit-probability-delta-vs-model-top",
            "-0.02",
            "--max-candidate-hit-probability-delta-vs-model-top",
            "0.0",
            "--min-decimal-odds-delta-vs-model-top",
            "0.01",
            "--min-evaluated-item-count",
            "1",
            "--min-simulated-actual-hit-delta-count-vs-model-top",
            "1",
            "--min-replacement-leg-hit-delta-count-vs-model-top",
            "1",
            "--min-average-profit-loss-delta-vs-model-top",
            "0.2",
            "--max-harm-count-vs-model-top",
            "2",
            "--max-report-items",
            "12",
        ]
    )
    options = _options_from_args(args)

    assert [profile.profile_id for profile in options.profiles] == [
        "current_model_top",
        "probability_preserving_model_edge_v1",
    ]
    assert options.focus_competition_ids == ("UNIT_LEAGUE", "EPL")
    assert options.min_actual_best_profit_loss_delta == 0.5
    assert options.min_profit_loss_gap == 0.1
    assert options.min_replacement_probability == 0.6
    assert options.min_replacement_decimal_odds == 1.2
    assert options.max_replacement_decimal_odds == 1.6
    assert options.min_candidate_hit_probability_delta_vs_model_top == -0.02
    assert options.max_candidate_hit_probability_delta_vs_model_top == 0.0
    assert options.min_decimal_odds_delta_vs_model_top == 0.01
    assert options.min_evaluated_item_count == 1
    assert options.min_simulated_actual_hit_delta_count_vs_model_top == 1
    assert options.min_replacement_leg_hit_delta_count_vs_model_top == 1
    assert options.min_average_profit_loss_delta_vs_model_top == 0.2
    assert options.max_harm_count_vs_model_top == 2
    assert options.max_report_items == 12

    main(
        [
            "--audit-report",
            str(audit_path),
            "--output-path",
            str(output_path),
            "--focus-competitions",
            "UNIT_LEAGUE",
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
    competition_id: str = "UNIT_LEAGUE",
    model_top: HistoricalCandidateReplacementSimulation,
    actual_best: HistoricalCandidateReplacementSimulation,
    replacement_candidates: list[HistoricalCandidateReplacementSimulation] | None = None,
) -> HistoricalCandidateMarginalAuditItem:
    resolved_candidates = replacement_candidates or [model_top, actual_best]
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
        selected_decimal_odds=2.00,
        selected_model_edge=-0.03,
        selected_score=0.55,
        leg_actual_hit=False,
        original_actual_return=0.0,
        original_profit_loss=-2.0,
        original_hit_probability=0.48,
        original_roi=-1.0,
        original_risk_score=0.52,
        replacement_count=len(resolved_candidates),
        model_top_replacement=model_top,
        actual_best_replacement=actual_best,
        replacement_candidates=resolved_candidates,
    )


def _replacement(
    *,
    rank: int,
    fixture_id: str = "replacement",
    probability: float = 0.82,
    decimal_odds: float = 1.12,
    model_edge: float = -0.03,
    score: float = 0.66,
    quality: float = 0.50,
    simulated_hit_probability: float = 0.62,
    profit_loss_delta: float = 1.0,
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
        simulated_hit_probability=simulated_hit_probability,
        simulated_roi=profit_loss_delta / 2.0,
        simulated_risk_score=1.0 - simulated_hit_probability,
        actual_return_delta=profit_loss_delta,
        profit_loss_delta=profit_loss_delta,
        hit_probability_delta=simulated_hit_probability - 0.48,
        roi_delta=profit_loss_delta / 2.0,
        risk_score_delta=0.02,
        decision="actual_improved" if profit_loss_delta > 0 else "actual_unchanged",
    )
