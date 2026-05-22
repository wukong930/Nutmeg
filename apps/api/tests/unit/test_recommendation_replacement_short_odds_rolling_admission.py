from __future__ import annotations

from json import dumps, loads
from pathlib import Path

from nutmeg.recommendations.marginal_contribution_diagnostics import (
    HistoricalCandidateMarginalAuditItem,
    HistoricalCandidateMarginalAuditReport,
    HistoricalCandidateReplacementSimulation,
)
from nutmeg.recommendations.replacement_short_odds_rolling_admission import (
    HistoricalShortOddsRollingAdmissionOptions,
    _options_from_args,
    _parse_args,
    build_historical_short_odds_rolling_admission_report,
    main,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    load_short_odds_runtime_rule_set,
)


def test_short_odds_rolling_admission_accepts_when_all_active_folds_pass(
    tmp_path: Path,
) -> None:
    report = build_historical_short_odds_rolling_admission_report(
        _audit_report(
            [
                _audit_item("EPL", "2020_2021"),
                _audit_item("EPL", "2021_2022"),
                _audit_item("FRA_LIGUE_1", "2020_2021"),
                _audit_item("FRA_LIGUE_1", "2021_2022"),
            ]
        ),
        rule_set=_rule_set(tmp_path),
        options=HistoricalShortOddsRollingAdmissionOptions(
            min_overall_final_answer_count=4,
            min_overall_changed_final_answer_count=4,
            min_active_competition_fold_count=2,
            min_active_season_fold_count=2,
            min_active_rolling_fold_count=2,
            rolling_window_final_answer_count=2,
            rolling_window_step=2,
        ),
    )

    assert report.status == "accepted"
    assert report.production_recommendation_allowed is True
    assert report.failed_fold_count == 0
    assert report.summary_json["overall_final_hit_harm_count_vs_original"] == 0
    assert report.summary_json["overall_profit_loss_harm_count_vs_original"] == 0
    assert report.active_competition_fold_count == 2
    assert report.active_season_fold_count == 2
    assert report.active_rolling_fold_count == 2
    assert all(check.status == "passed" for check in report.checks)
    assert {fold.status for fold in report.folds} == {"passed"}


def test_short_odds_rolling_admission_rejects_when_overall_runtime_replay_fails(
    tmp_path: Path,
) -> None:
    report = build_historical_short_odds_rolling_admission_report(
        _audit_report(
            [
                _audit_item("EPL", "2020_2021"),
                _audit_item("EPL", "2021_2022", replacement_hit=False),
                _audit_item("FRA_LIGUE_1", "2020_2021"),
                _audit_item("FRA_LIGUE_1", "2021_2022"),
            ]
        ),
        rule_set=_rule_set(tmp_path),
        options=HistoricalShortOddsRollingAdmissionOptions(
            min_overall_final_answer_count=4,
            min_overall_changed_final_answer_count=4,
            min_active_competition_fold_count=2,
            min_active_season_fold_count=2,
            min_active_rolling_fold_count=2,
            rolling_window_final_answer_count=2,
            rolling_window_step=2,
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "rejected"
    assert report.production_recommendation_allowed is False
    assert report.failed_fold_count >= 1
    assert "overall_runtime_shadow_replay_passed" in failed_checks
    assert "failed_fold_count" in failed_checks


def test_short_odds_rolling_admission_cli_options_loader_and_main(
    tmp_path: Path,
) -> None:
    audit_path = tmp_path / "audit.json"
    rule_path = tmp_path / "rules.json"
    output_path = tmp_path / "rolling_admission.json"
    audit_path.write_text(
        f"{_audit_report([_audit_item('EPL', '2020_2021')]).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    rule_path.write_text(_json(_rule_profile()), encoding="utf-8")

    args = _parse_args(
        [
            "--audit-report",
            str(audit_path),
            "--rule-profile",
            str(rule_path),
            "--output-path",
            str(output_path),
            "--rule-ids",
            "short_odds_final_answer_replacement_v1",
            "--min-overall-final-answer-count",
            "1",
            "--min-overall-changed-final-answer-count",
            "1",
            "--min-overall-final-answer-hit-rate-delta",
            "0.01",
            "--min-overall-roi-delta",
            "0.02",
            "--min-overall-profit-loss-delta",
            "0.03",
            "--max-overall-harm-count-vs-original",
            "1",
            "--max-overall-final-hit-harm-count-vs-original",
            "2",
            "--max-overall-profit-loss-harm-count-vs-original",
            "3",
            "--min-overall-average-hit-probability-delta-vs-original",
            "-0.03",
            "--min-fold-final-answer-count",
            "1",
            "--min-fold-changed-final-answer-count",
            "1",
            "--min-fold-final-answer-hit-rate-delta",
            "0.01",
            "--min-fold-roi-delta",
            "0.02",
            "--min-fold-profit-loss-delta",
            "0.03",
            "--max-fold-harm-count-vs-original",
            "1",
            "--max-fold-final-hit-harm-count-vs-original",
            "2",
            "--max-fold-profit-loss-harm-count-vs-original",
            "3",
            "--min-fold-average-hit-probability-delta-vs-original",
            "-0.03",
            "--min-active-competition-fold-count",
            "1",
            "--min-active-season-fold-count",
            "1",
            "--min-active-rolling-fold-count",
            "1",
            "--rolling-window-final-answer-count",
            "1",
            "--rolling-window-step",
            "1",
            "--max-failed-fold-count",
            "1",
            "--allow-production-change",
            "--max-report-folds",
            "10",
            "--no-fail-process",
        ]
    )
    options = _options_from_args(args)

    assert options.rule_ids == ("short_odds_final_answer_replacement_v1",)
    assert options.min_overall_final_answer_count == 1
    assert options.min_overall_changed_final_answer_count == 1
    assert options.min_overall_final_answer_hit_rate_delta == 0.01
    assert options.min_overall_roi_delta == 0.02
    assert options.min_overall_profit_loss_delta == 0.03
    assert options.max_overall_harm_count_vs_original == 1
    assert options.max_overall_final_hit_harm_count_vs_original == 2
    assert options.max_overall_profit_loss_harm_count_vs_original == 3
    assert options.min_overall_average_hit_probability_delta_vs_original == -0.03
    assert options.min_fold_final_answer_count == 1
    assert options.min_fold_changed_final_answer_count == 1
    assert options.min_fold_final_answer_hit_rate_delta == 0.01
    assert options.min_fold_roi_delta == 0.02
    assert options.min_fold_profit_loss_delta == 0.03
    assert options.max_fold_harm_count_vs_original == 1
    assert options.max_fold_final_hit_harm_count_vs_original == 2
    assert options.max_fold_profit_loss_harm_count_vs_original == 3
    assert options.min_fold_average_hit_probability_delta_vs_original == -0.03
    assert options.min_active_competition_fold_count == 1
    assert options.min_active_season_fold_count == 1
    assert options.min_active_rolling_fold_count == 1
    assert options.rolling_window_final_answer_count == 1
    assert options.rolling_window_step == 1
    assert options.max_failed_fold_count == 1
    assert options.require_no_production_change is False
    assert options.max_report_folds == 10

    main(
        [
            "--audit-report",
            str(audit_path),
            "--rule-profile",
            str(rule_path),
            "--output-path",
            str(output_path),
            "--min-overall-final-answer-count",
            "1",
            "--min-overall-changed-final-answer-count",
            "1",
            "--min-active-competition-fold-count",
            "1",
            "--min-active-season-fold-count",
            "1",
            "--min-active-rolling-fold-count",
            "1",
            "--rolling-window-final-answer-count",
            "1",
            "--rolling-window-step",
            "1",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "accepted"
    assert payload["production_recommendation_allowed"] is True


def _rule_set(tmp_path: Path):
    path = tmp_path / "short_odds_rules.json"
    path.write_text(_json(_rule_profile()), encoding="utf-8")
    return load_short_odds_runtime_rule_set(path, enable_shadow_replay=True)


def _rule_profile() -> dict[str, object]:
    return {
        "profile_version": "rolling-admission-test",
        "short_odds_replacement_rules": [
            {
                "rule_id": "short_odds_final_answer_replacement_v1",
                "profile_id": "max_short_odds_within_deficit_v1",
                "proposed_production_enabled": True,
                "production_recommendation_changed": False,
                "allowed_competition_ids": ["EPL", "FRA_LIGUE_1"],
                "excluded_competition_ids": [],
                "constraints_json": {
                    "max_replacements_per_final_answer": 1,
                    "min_replacement_probability": 0.55,
                    "max_replacement_decimal_odds": 1.75,
                    "min_candidate_hit_probability_delta_vs_model_top": -0.015,
                    "max_candidate_hit_probability_delta_vs_model_top": 0.0,
                    "min_candidate_hit_probability_delta_vs_original": -0.025,
                    "min_decimal_odds_delta_vs_model_top": 0.0,
                },
            }
        ],
    }


def _audit_report(
    items: list[HistoricalCandidateMarginalAuditItem],
) -> HistoricalCandidateMarginalAuditReport:
    return HistoricalCandidateMarginalAuditReport(
        report_key="unit-test-rolling-audit",
        status="generated",
        slice_count=len({item.slice_id for item in items}),
        competition_count=len({item.competition_id for item in items}),
        final_answer_count=len(items),
        selected_leg_count=len(items),
        missed_leg_count=0,
        replacement_simulation_count=sum(item.replacement_count for item in items),
        actual_replacement_opportunity_count=0,
        model_top_replacement_count=len(items),
        model_top_actual_improvement_count=len(items),
        model_top_actual_harm_count=0,
        items=items,
    )


def _audit_item(
    competition_id: str,
    season_id: str,
    *,
    replacement_hit: bool = True,
) -> HistoricalCandidateMarginalAuditItem:
    model_top = _replacement(
        rank=1,
        fixture_id=f"{competition_id}_{season_id}_model_top",
        odds=1.15,
        simulated_hp=0.61,
        simulated_hit=True,
        simulated_profit=1.1,
    )
    replacement = _replacement(
        rank=2,
        fixture_id=f"{competition_id}_{season_id}_replacement",
        odds=1.17,
        simulated_hp=0.601,
        simulated_hit=replacement_hit,
        simulated_profit=1.2 if replacement_hit else -2.0,
    )
    return HistoricalCandidateMarginalAuditItem(
        item_key=f"{competition_id}:{season_id}:selected",
        slice_id=f"fdcuk_{competition_id.lower()}_{season_id}_test",
        competition_id=competition_id,
        final_answer_scenario_key="2x1:single",
        pass_type="2x1",
        mode="single",
        final_answer_actual_hit=True,
        selected_fixture_id=f"{competition_id}_{season_id}_selected",
        selected_market_type="1x2",
        selected_outcome="home_win",
        selected_probability=0.80,
        selected_decimal_odds=1.12,
        selected_model_edge=-0.02,
        selected_score=0.60,
        leg_actual_hit=True,
        original_actual_return=3.0,
        original_profit_loss=1.0,
        original_hit_probability=0.62,
        original_roi=0.50,
        original_risk_score=0.38,
        replacement_count=2,
        model_top_replacement=model_top,
        actual_best_replacement=replacement,
        replacement_candidates=[model_top, replacement],
    )


def _replacement(
    *,
    rank: int,
    fixture_id: str,
    odds: float,
    simulated_hp: float,
    simulated_hit: bool,
    simulated_profit: float,
) -> HistoricalCandidateReplacementSimulation:
    return HistoricalCandidateReplacementSimulation(
        replacement_rank=rank,
        replacement_fixture_id=fixture_id,
        replacement_market_type="1x2",
        replacement_outcome="home_win",
        replacement_probability=0.80,
        replacement_decimal_odds=odds,
        replacement_model_edge=-0.02,
        replacement_score=0.60,
        replacement_quality_score=0.50,
        replacement_leg_actual_hit=simulated_hit,
        simulated_actual_hit=simulated_hit,
        simulated_actual_return=max(simulated_profit + 2.0, 0.0),
        simulated_profit_loss=simulated_profit,
        simulated_hit_probability=simulated_hp,
        simulated_roi=simulated_profit / 2.0,
        simulated_risk_score=1.0 - simulated_hp,
        actual_return_delta=simulated_profit - 1.0,
        profit_loss_delta=simulated_profit - 1.0,
        hit_probability_delta=simulated_hp - 0.62,
        roi_delta=(simulated_profit - 1.0) / 2.0,
        risk_score_delta=0.0,
        decision="actual_improved" if simulated_profit > 1.0 else "actual_regressed",
    )


def _json(payload: dict[str, object]) -> str:
    return f"{dumps(payload)}\n"
