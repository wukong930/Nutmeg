from __future__ import annotations

from pathlib import Path

from nutmeg.recommendations.replacement_short_odds_competition_gate import (
    HistoricalShortOddsCompetitionGateOptions,
    _options_from_args,
    _parse_args,
    build_historical_short_odds_competition_gate_report,
    load_historical_short_odds_shadow_rerank_report,
    main,
)
from nutmeg.recommendations.replacement_short_odds_shadow_rerank import (
    HistoricalShortOddsShadowCompetitionSummary,
    HistoricalShortOddsShadowProfileSummary,
    HistoricalShortOddsShadowRerankReport,
)


def test_short_odds_competition_gate_splits_ready_and_isolated_leagues() -> None:
    shadow_report = _shadow_report(
        [
            _profile_summary(
                "max_short_odds_within_deficit_v1",
                [
                    _competition_summary(
                        "EPL",
                        evaluated=20,
                        changed=20,
                        hit_delta=5,
                        profit_delta=0.96,
                        harm=0,
                    ),
                    _competition_summary(
                        "ESP_LA_LIGA",
                        evaluated=11,
                        changed=11,
                        hit_delta=1,
                        profit_delta=0.64,
                        harm=5,
                    ),
                ],
            )
        ]
    )

    report = build_historical_short_odds_competition_gate_report(
        shadow_report,
        options=HistoricalShortOddsCompetitionGateOptions(
            profile_ids=("max_short_odds_within_deficit_v1",),
            min_evaluated_item_count=5,
        ),
    )

    epl_candidate = next(
        candidate for candidate in report.candidates if candidate.competition_id == "EPL"
    )
    la_liga_candidate = next(
        candidate
        for candidate in report.candidates
        if candidate.competition_id == "ESP_LA_LIGA"
    )

    assert report.production_recommendation_changed is False
    assert report.ready_competition_ids == ["EPL"]
    assert report.isolated_competition_ids == ["ESP_LA_LIGA"]
    assert epl_candidate.decision == "final_answer_gate_ready"
    assert epl_candidate.decision_reasons == []
    assert la_liga_candidate.decision == "isolated_rejected"
    assert "harm_count_vs_model_top_above_threshold" in (
        la_liga_candidate.decision_reasons
    )
    assert report.best_profile_set is not None
    assert report.best_profile_set.ready_competition_ids == ["EPL"]
    assert report.best_profile_set.isolated_competition_ids == ["ESP_LA_LIGA"]
    assert "isolated_competitions_require_separate_guard" in (
        report.best_profile_set.decision_reasons
    )


def test_short_odds_competition_gate_marks_positive_under_sample_as_watchlist() -> None:
    shadow_report = _shadow_report(
        [
            _profile_summary(
                "max_short_odds_within_deficit_v1",
                [
                    _competition_summary(
                        "ITA_SERIE_A",
                        evaluated=3,
                        changed=3,
                        hit_delta=2,
                        profit_delta=0.7,
                        harm=0,
                    )
                ],
            )
        ]
    )

    report = build_historical_short_odds_competition_gate_report(
        shadow_report,
        options=HistoricalShortOddsCompetitionGateOptions(
            profile_ids=("max_short_odds_within_deficit_v1",),
            min_evaluated_item_count=5,
        ),
    )

    candidate = report.candidates[0]

    assert candidate.decision == "holdout_watchlist"
    assert "sample_size_below_threshold" in candidate.decision_reasons
    assert report.final_answer_gate_ready_count == 0
    assert report.holdout_watchlist_count == 1
    assert report.best_profile_set is None


def test_short_odds_competition_gate_cli_options_loader_and_main(
    tmp_path: Path,
) -> None:
    shadow_report = _shadow_report(
        [
            _profile_summary(
                "max_short_odds_within_deficit_v1",
                [
                    _competition_summary(
                        "EPL",
                        evaluated=20,
                        changed=20,
                        hit_delta=5,
                        profit_delta=0.96,
                        harm=0,
                    )
                ],
            )
        ]
    )
    shadow_path = tmp_path / "shadow.json"
    output_path = tmp_path / "competition_gate.json"
    shadow_path.write_text(
        f"{shadow_report.model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            "--shadow-report",
            str(shadow_path),
            "--output-path",
            str(output_path),
            "--profile-ids",
            "max_short_odds_within_deficit_v1,max_model_edge_within_deficit_v1",
            "--min-evaluated-item-count",
            "8",
            "--min-changed-count-vs-model-top",
            "2",
            "--min-simulated-actual-hit-delta-count-vs-model-top",
            "2",
            "--min-replacement-leg-hit-delta-count-vs-model-top",
            "2",
            "--min-average-profit-loss-delta-vs-model-top",
            "0.2",
            "--min-average-hit-probability-delta-vs-model-top",
            "-0.012",
            "--max-harm-count-vs-model-top",
            "1",
            "--max-report-candidates",
            "12",
        ]
    )
    options = _options_from_args(args)

    assert options.profile_ids == (
        "max_short_odds_within_deficit_v1",
        "max_model_edge_within_deficit_v1",
    )
    assert options.min_evaluated_item_count == 8
    assert options.min_changed_count_vs_model_top == 2
    assert options.min_simulated_actual_hit_delta_count_vs_model_top == 2
    assert options.min_replacement_leg_hit_delta_count_vs_model_top == 2
    assert options.min_average_profit_loss_delta_vs_model_top == 0.2
    assert options.min_average_hit_probability_delta_vs_model_top == -0.012
    assert options.max_harm_count_vs_model_top == 1
    assert options.max_report_candidates == 12

    loaded = load_historical_short_odds_shadow_rerank_report(shadow_path)
    assert loaded.report_key == shadow_report.report_key

    main(
        [
            "--shadow-report",
            str(shadow_path),
            "--output-path",
            str(output_path),
            "--min-evaluated-item-count",
            "5",
        ]
    )

    assert output_path.exists()


def _shadow_report(
    profile_summaries: list[HistoricalShortOddsShadowProfileSummary],
) -> HistoricalShortOddsShadowRerankReport:
    return HistoricalShortOddsShadowRerankReport(
        report_key="unit-test-short-odds-shadow",
        status="generated",
        source_audit_report_key="unit-test-audit",
        eligible_item_count=sum(
            competition.evaluated_item_count
            for profile in profile_summaries
            for competition in profile.competition_summaries
        ),
        profile_count=len(profile_summaries),
        shadow_candidate_count=0,
        shadow_watchlist_count=len(profile_summaries),
        rejected_count=0,
        pre_match_feature_names=["replacement_probability"],
        offline_evaluation_fields=["profit_loss_delta"],
        production_recommendation_changed=False,
        profile_summaries=profile_summaries,
    )


def _profile_summary(
    profile_id: str,
    competition_summaries: list[HistoricalShortOddsShadowCompetitionSummary],
) -> HistoricalShortOddsShadowProfileSummary:
    evaluated_count = sum(
        competition.evaluated_item_count for competition in competition_summaries
    )
    changed_count = sum(
        competition.changed_count_vs_model_top for competition in competition_summaries
    )
    hit_delta = sum(
        competition.simulated_actual_hit_delta_count_vs_model_top
        for competition in competition_summaries
    )
    selected_actual_best_count = sum(
        competition.selected_actual_best_count for competition in competition_summaries
    )
    harm_count = sum(
        competition.harm_count_vs_model_top for competition in competition_summaries
    )
    improvement_count = sum(
        competition.improvement_count_vs_model_top
        for competition in competition_summaries
    )
    return HistoricalShortOddsShadowProfileSummary(
        profile_id=profile_id,
        selection_rule="max_short_odds_within_deficit",
        status="shadow_watchlist",
        evaluated_item_count=evaluated_count,
        changed_count_vs_model_top=changed_count,
        selected_model_top_count=evaluated_count - changed_count,
        selected_actual_best_count=selected_actual_best_count,
        qualified_candidate_count=changed_count,
        improvement_count_vs_model_top=improvement_count,
        harm_count_vs_model_top=harm_count,
        simulated_actual_hit_count=0,
        model_top_simulated_actual_hit_count=0,
        simulated_actual_hit_delta_count_vs_model_top=hit_delta,
        replacement_leg_hit_count=0,
        model_top_replacement_leg_hit_count=0,
        replacement_leg_hit_delta_count_vs_model_top=hit_delta,
        expected_hit_probability_regression_count=changed_count,
        competition_summaries=competition_summaries,
    )


def _competition_summary(
    competition_id: str,
    *,
    evaluated: int,
    changed: int,
    hit_delta: int,
    profit_delta: float,
    harm: int,
) -> HistoricalShortOddsShadowCompetitionSummary:
    return HistoricalShortOddsShadowCompetitionSummary(
        competition_id=competition_id,
        evaluated_item_count=evaluated,
        changed_count_vs_model_top=changed,
        simulated_actual_hit_delta_count_vs_model_top=hit_delta,
        replacement_leg_hit_delta_count_vs_model_top=hit_delta,
        improvement_count_vs_model_top=max(changed - harm, 0),
        harm_count_vs_model_top=harm,
        selected_actual_best_count=max(changed - harm, 0),
        average_profit_loss_delta_vs_model_top=profit_delta,
        average_hit_probability_delta_vs_model_top=-0.01,
        average_decimal_odds_delta_vs_model_top=0.02,
    )
