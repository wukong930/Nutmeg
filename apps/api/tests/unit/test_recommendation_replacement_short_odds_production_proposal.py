from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations.replacement_short_odds_final_answer_gate import (
    HistoricalShortOddsFinalAnswerGateReport,
)
from nutmeg.recommendations.replacement_short_odds_production_proposal import (
    HistoricalShortOddsProductionProposalOptions,
    _options_from_args,
    _parse_args,
    build_historical_short_odds_production_proposal_report,
    load_historical_short_odds_final_answer_gate_report,
    load_historical_short_odds_rolling_admission_report,
    load_historical_short_odds_runtime_shadow_replay_report,
    load_historical_short_odds_suite_gate_report,
    main,
)
from nutmeg.recommendations.replacement_short_odds_rolling_admission import (
    HistoricalShortOddsRollingAdmissionReport,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayReport,
)
from nutmeg.recommendations.replacement_short_odds_suite_gate import (
    HistoricalShortOddsSuiteGateReport,
)


def test_short_odds_production_proposal_is_ready_when_all_gates_pass() -> None:
    report = build_historical_short_odds_production_proposal_report(
        _suite_gate_report(),
        _final_answer_gate_report(),
    )

    assert report.status == "production_proposal_ready"
    assert report.production_recommendation_allowed is True
    assert report.shadow_allowed is True
    assert report.proposal_count == 1
    assert report.ready_competition_ids == ["EPL", "FRA_LIGUE_1"]
    assert report.isolated_competition_ids == ["ESP_LA_LIGA"]
    assert all(check.status == "passed" for check in report.checks)
    assert report.proposal_rule is not None
    assert report.proposal_rule.proposed_production_enabled is True
    assert report.proposal_rule.production_recommendation_changed is False
    assert report.proposal_rule.allowed_competition_ids == ["EPL", "FRA_LIGUE_1"]
    assert report.proposal_rule.excluded_competition_ids == ["ESP_LA_LIGA"]
    assert report.proposal_rule.constraints_json["max_replacements_per_final_answer"] == 1
    assert (
        report.proposal_rule.constraints_json[
            "min_average_hit_probability_delta_vs_original"
        ]
        == -0.02
    )
    assert (
        "disable_if_production_harm_count_vs_original_exceeds_0"
        in report.proposal_rule.rollback_conditions
    )
    assert report.proposal_profile_set_json["production_recommendation_changed"] is False
    assert report.proposal_profile_set_json["rules"]


def test_short_odds_production_proposal_carries_runtime_guard_evidence() -> None:
    report = build_historical_short_odds_production_proposal_report(
        _suite_gate_report(),
        _final_answer_gate_report(),
        runtime_shadow_replay_report=_runtime_shadow_replay_report(),
    )

    assert report.status == "production_proposal_ready"
    assert report.source_runtime_shadow_replay_report_key == "unit-test-runtime-shadow"
    assert report.proposal_rule is not None
    assert report.proposal_rule.source_report_keys["runtime_shadow_replay"] == (
        "unit-test-runtime-shadow"
    )
    assert (
        report.proposal_rule.constraints_json[
            "min_candidate_hit_probability_delta_vs_original"
        ]
        == -0.025
    )
    assert report.proposal_rule.evidence_json["runtime_shadow_replay_passed"] is True
    assert report.proposal_rule.evidence_json["runtime_harm_count_vs_original"] == 0
    assert (
        "disable_if_runtime_shadow_replay_report_missing_or_failed"
        in report.proposal_rule.rollback_conditions
    )
    assert (
        "disable_if_candidate_hit_probability_delta_below_-0.025"
        in report.proposal_rule.rollback_conditions
    )


def test_short_odds_production_proposal_blocks_runtime_final_hit_harm() -> None:
    runtime_report = _runtime_shadow_replay_report().model_copy(
        update={
            "final_hit_harm_count_vs_original": 1,
            "profit_loss_harm_count_vs_original": 0,
            "harm_count_vs_original": 0,
        }
    )

    report = build_historical_short_odds_production_proposal_report(
        _suite_gate_report(),
        _final_answer_gate_report(),
        runtime_shadow_replay_report=runtime_report,
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}
    assert report.status == "shadow_only"
    assert "runtime_shadow_final_hit_harm_count_vs_original" in failed_checks
    assert report.proposal_rule is not None
    assert (
        report.proposal_rule.evidence_json[
            "runtime_final_hit_harm_count_vs_original"
        ]
        == 1
    )
    assert (
        report.proposal_rule.evidence_json[
            "runtime_profit_loss_harm_count_vs_original"
        ]
        == 0
    )


def test_short_odds_production_proposal_accepts_rule_sourced_runtime_guard() -> None:
    report = build_historical_short_odds_production_proposal_report(
        _suite_gate_report(),
        _final_answer_gate_report(),
        runtime_shadow_replay_report=_runtime_shadow_replay_report(
            guard_in_options=False
        ),
        options=HistoricalShortOddsProductionProposalOptions(
            require_runtime_shadow_replay_passed=True,
            min_candidate_hit_probability_delta_vs_original=-0.025,
        ),
    )

    assert report.status == "production_proposal_ready"
    assert report.proposal_rule is not None
    assert (
        report.proposal_rule.constraints_json[
            "min_candidate_hit_probability_delta_vs_original"
        ]
        == -0.025
    )


def test_short_odds_production_proposal_carries_rolling_admission_evidence() -> None:
    report = build_historical_short_odds_production_proposal_report(
        _suite_gate_report(),
        _final_answer_gate_report(),
        runtime_shadow_replay_report=_runtime_shadow_replay_report(),
        rolling_admission_report=_rolling_admission_report(),
        options=HistoricalShortOddsProductionProposalOptions(
            require_runtime_shadow_replay_passed=True,
            require_rolling_admission_accepted=True,
            min_candidate_hit_probability_delta_vs_original=-0.025,
        ),
    )

    assert report.status == "production_proposal_ready"
    assert report.source_rolling_admission_report_key == "unit-test-rolling-admission"
    assert report.proposal_rule is not None
    assert report.proposal_rule.source_report_keys["rolling_admission"] == (
        "unit-test-rolling-admission"
    )
    assert report.proposal_rule.evidence_json["rolling_admission_accepted"] is True
    assert report.proposal_rule.evidence_json["rolling_failed_fold_count"] == 0
    assert report.proposal_rule.evidence_json[
        "rolling_active_competition_fold_count"
    ] == 4
    assert report.proposal_rule.evidence_json["rolling_active_season_fold_count"] == 5
    assert report.proposal_rule.evidence_json["rolling_active_rolling_fold_count"] == 4
    assert (
        "disable_if_rolling_admission_report_missing_or_failed"
        in report.proposal_rule.rollback_conditions
    )


def test_short_odds_production_proposal_blocks_failed_runtime_shadow_replay() -> None:
    report = build_historical_short_odds_production_proposal_report(
        _suite_gate_report(),
        _final_answer_gate_report(),
        runtime_shadow_replay_report=_runtime_shadow_replay_report(passed=False),
        options=HistoricalShortOddsProductionProposalOptions(
            require_runtime_shadow_replay_passed=True
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_only"
    assert report.production_recommendation_allowed is False
    assert "runtime_shadow_replay_passed" in failed_checks


def test_short_odds_production_proposal_blocks_failed_rolling_admission() -> None:
    report = build_historical_short_odds_production_proposal_report(
        _suite_gate_report(),
        _final_answer_gate_report(),
        runtime_shadow_replay_report=_runtime_shadow_replay_report(),
        rolling_admission_report=_rolling_admission_report(accepted=False),
        options=HistoricalShortOddsProductionProposalOptions(
            require_runtime_shadow_replay_passed=True,
            require_rolling_admission_accepted=True,
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_only"
    assert report.production_recommendation_allowed is False
    assert "rolling_admission_status" in failed_checks
    assert "rolling_admission_failed_fold_count" in failed_checks


def test_short_odds_production_proposal_blocks_isolated_competition_overlap() -> None:
    report = build_historical_short_odds_production_proposal_report(
        _suite_gate_report(),
        _final_answer_gate_report(
            ready_competition_ids=["EPL", "ESP_LA_LIGA"],
            isolated_competition_ids=["ESP_LA_LIGA"],
        ),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_only"
    assert report.production_recommendation_allowed is False
    assert report.shadow_allowed is True
    assert "isolated_competitions_excluded" in failed_checks
    assert report.proposal_rule is not None
    assert report.proposal_rule.proposed_production_enabled is False
    assert "short_odds_production_proposal:shadow_only" in report.warnings


def test_short_odds_production_proposal_blocks_source_production_change() -> None:
    report = build_historical_short_odds_production_proposal_report(
        _suite_gate_report(production_recommendation_changed=True),
        _final_answer_gate_report(),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "shadow_only"
    assert report.production_recommendation_allowed is False
    assert "suite_gate_no_production_change" in failed_checks


def test_short_odds_production_proposal_cli_options_loader_and_main(
    tmp_path: Path,
) -> None:
    suite_path = tmp_path / "suite_gate.json"
    final_answer_path = tmp_path / "final_answer_gate.json"
    rolling_path = tmp_path / "rolling_admission.json"
    output_path = tmp_path / "production_proposal.json"
    suite_path.write_text(
        f"{_suite_gate_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    final_answer_path.write_text(
        f"{_final_answer_gate_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    rolling_path.write_text(
        f"{_rolling_admission_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    args = _parse_args(
        [
            "--suite-gate-report",
            str(suite_path),
            "--final-answer-gate-report",
            str(final_answer_path),
            "--rolling-admission-report",
            str(rolling_path),
            "--output-path",
            str(output_path),
            "--proposal-id",
            "custom-short-odds-rule",
            "--proposed-profile-version",
            "custom-profile-version",
            "--min-final-answer-count",
            "12",
            "--min-changed-final-answer-count",
            "4",
            "--min-final-answer-hit-rate-delta",
            "0.01",
            "--min-roi-delta",
            "0.02",
            "--min-profit-loss-delta",
            "0.5",
            "--max-harm-count-vs-original",
            "1",
            "--max-final-hit-harm-count-vs-original",
            "2",
            "--max-profit-loss-harm-count-vs-original",
            "3",
            "--min-average-hit-probability-delta-vs-original",
            "-0.03",
            "--min-candidate-hit-probability-delta-vs-original",
            "-0.025",
            "--min-rolling-active-competition-fold-count",
            "2",
            "--min-rolling-active-season-fold-count",
            "3",
            "--min-rolling-active-rolling-fold-count",
            "2",
            "--max-rolling-failed-fold-count",
            "1",
            "--allow-unpassed-suite-gate",
            "--allow-non-shadow-final-answer-gate",
            "--allow-unpassed-runtime-shadow-replay",
            "--allow-unaccepted-rolling-admission",
            "--allow-source-production-change",
            "--allow-isolated-competition-overlap",
            "--no-fail-process",
        ]
    )
    options = _options_from_args(args)

    assert options.proposal_id == "custom-short-odds-rule"
    assert options.proposed_profile_version == "custom-profile-version"
    assert options.min_final_answer_count == 12
    assert options.min_changed_final_answer_count == 4
    assert options.min_final_answer_hit_rate_delta == 0.01
    assert options.min_roi_delta == 0.02
    assert options.min_profit_loss_delta == 0.5
    assert options.max_harm_count_vs_original == 1
    assert options.max_final_hit_harm_count_vs_original == 2
    assert options.max_profit_loss_harm_count_vs_original == 3
    assert options.min_average_hit_probability_delta_vs_original == -0.03
    assert options.min_candidate_hit_probability_delta_vs_original == -0.025
    assert options.min_rolling_active_competition_fold_count == 2
    assert options.min_rolling_active_season_fold_count == 3
    assert options.min_rolling_active_rolling_fold_count == 2
    assert options.max_rolling_failed_fold_count == 1
    assert options.require_suite_gate_passed is False
    assert options.require_final_answer_shadow_candidate is False
    assert options.require_runtime_shadow_replay_passed is False
    assert options.require_rolling_admission_accepted is False
    assert options.require_no_source_production_change is False
    assert options.require_isolated_competitions_excluded is False
    assert load_historical_short_odds_suite_gate_report(suite_path).report_key == (
        "unit-test-suite-gate"
    )
    assert load_historical_short_odds_final_answer_gate_report(
        final_answer_path
    ).report_key == "unit-test-final-answer-gate"

    runtime_path = tmp_path / "runtime_shadow.json"
    runtime_path.write_text(
        f"{_runtime_shadow_replay_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    assert load_historical_short_odds_runtime_shadow_replay_report(
        runtime_path
    ).report_key == "unit-test-runtime-shadow"
    assert load_historical_short_odds_rolling_admission_report(
        rolling_path
    ).report_key == "unit-test-rolling-admission"

    main(
        [
            "--suite-gate-report",
            str(suite_path),
            "--final-answer-gate-report",
            str(final_answer_path),
            "--output-path",
            str(output_path),
            "--runtime-shadow-replay-report",
            str(runtime_path),
            "--rolling-admission-report",
            str(rolling_path),
            "--min-candidate-hit-probability-delta-vs-original",
            "-0.025",
            "--min-final-answer-count",
            "30",
            "--min-changed-final-answer-count",
            "5",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "production_proposal_ready"
    assert payload["production_recommendation_allowed"] is True


def _suite_gate_report(
    *,
    production_recommendation_changed: bool = False,
) -> HistoricalShortOddsSuiteGateReport:
    return HistoricalShortOddsSuiteGateReport(
        report_key="unit-test-suite-gate",
        status="passed",
        passed=True,
        source_audit_report_key="unit-test-audit",
        source_final_answer_gate_report_key="unit-test-final-answer-gate",
        final_answer_count=30,
        changed_final_answer_count=16,
        baseline_final_answer_hit_count=20,
        candidate_final_answer_hit_count=22,
        final_answer_hit_delta_count=2,
        baseline_final_answer_hit_rate=20 / 30,
        candidate_final_answer_hit_rate=22 / 30,
        final_answer_hit_rate_delta=2 / 30,
        baseline_profit_loss=3.0,
        candidate_profit_loss=9.4,
        profit_loss_delta=6.4,
        baseline_roi=0.05,
        candidate_roi=0.156,
        roi_delta=0.106,
        total_stake=60.0,
        harm_count_vs_original=0,
        final_hit_harm_count_vs_original=0,
        profit_loss_harm_count_vs_original=0,
        average_hit_probability_delta_vs_original=-0.0169,
        production_recommendation_changed=production_recommendation_changed,
        summary_json={
            "options": {
                "min_average_hit_probability_delta_vs_original": -0.02,
                "max_harm_count_vs_original": 0,
            }
        },
    )


def _runtime_shadow_replay_report(
    *,
    passed: bool = True,
    guard_in_options: bool = True,
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    return HistoricalShortOddsRuntimeShadowReplayReport(
        report_key="unit-test-runtime-shadow",
        status="shadow_replay_passed" if passed else "shadow_replay_failed",
        passed=passed,
        source_audit_report_key="unit-test-audit",
        source_rule_profile_version="runtime-shadow-test",
        rule_count=1,
        enabled_rule_count=1,
        final_answer_count=30,
        changed_final_answer_count=17,
        baseline_final_answer_hit_count=20,
        shadow_final_answer_hit_count=20 if passed else 19,
        final_answer_hit_delta_count=0 if passed else -1,
        baseline_final_answer_hit_rate=20 / 30,
        shadow_final_answer_hit_rate=20 / 30 if passed else 19 / 30,
        final_answer_hit_rate_delta=0.0 if passed else -1 / 30,
        baseline_profit_loss=3.0,
        shadow_profit_loss=4.0 if passed else 1.0,
        profit_loss_delta=1.0 if passed else -2.0,
        baseline_roi=0.05,
        shadow_roi=0.066 if passed else 0.016,
        roi_delta=0.016 if passed else -0.034,
        total_stake=60.0,
        harm_count_vs_original=0 if passed else 1,
        final_hit_harm_count_vs_original=0 if passed else 1,
        profit_loss_harm_count_vs_original=0 if passed else 1,
        average_hit_probability_delta_vs_original=-0.014,
        production_recommendation_changed=False,
        public_response_changed=False,
        rule_set_json={
            "rules": [
                {
                    "constraints_json": {
                        "min_candidate_hit_probability_delta_vs_original": -0.025
                    }
                }
            ]
        },
        summary_json={
            "options": {
                "min_candidate_hit_probability_delta_vs_original": (
                    -0.025 if guard_in_options else None
                ),
            }
        },
    )


def _rolling_admission_report(
    *,
    accepted: bool = True,
) -> HistoricalShortOddsRollingAdmissionReport:
    failed_fold_count = 0 if accepted else 1
    return HistoricalShortOddsRollingAdmissionReport(
        report_key="unit-test-rolling-admission",
        status="accepted" if accepted else "shadow_only",
        production_recommendation_allowed=accepted,
        shadow_allowed=True,
        source_audit_report_key="unit-test-audit",
        source_rule_profile_version="rolling-admission-test",
        overall_runtime_shadow_report_key="unit-test-runtime-shadow",
        fold_count=13,
        active_fold_count=13,
        failed_fold_count=failed_fold_count,
        active_competition_fold_count=4,
        active_season_fold_count=5,
        active_rolling_fold_count=4,
        checks=[],
        folds=[],
        summary_json={
            "overall_final_answer_hit_rate_delta": 0.0 if accepted else -0.01,
            "overall_roi_delta": 0.016 if accepted else -0.02,
            "overall_profit_loss_delta": 1.0 if accepted else -1.0,
            "overall_harm_count_vs_original": 0 if accepted else 1,
            "overall_final_hit_harm_count_vs_original": 0 if accepted else 1,
            "overall_profit_loss_harm_count_vs_original": 0 if accepted else 1,
            "overall_average_hit_probability_delta_vs_original": -0.014,
        },
    )


def _final_answer_gate_report(
    *,
    ready_competition_ids: list[str] | None = None,
    isolated_competition_ids: list[str] | None = None,
) -> HistoricalShortOddsFinalAnswerGateReport:
    return HistoricalShortOddsFinalAnswerGateReport(
        report_key="unit-test-final-answer-gate",
        status="generated",
        decision="final_answer_shadow_candidate",
        source_audit_report_key="unit-test-audit",
        source_competition_gate_report_key="unit-test-competition-gate",
        generated_shadow_report_key="unit-test-shadow",
        profile_id="max_short_odds_within_deficit_v1",
        ready_competition_ids=ready_competition_ids or ["EPL", "FRA_LIGUE_1"],
        isolated_competition_ids=isolated_competition_ids or ["ESP_LA_LIGA"],
        changed_final_answer_count=16,
        original_final_answer_hit_count=14,
        shadow_final_answer_hit_count=16,
        final_answer_hit_delta_count_vs_original=2,
        original_profit_loss=10.3,
        shadow_profit_loss=16.7,
        profit_loss_delta_vs_original=6.4,
        improvement_count_vs_original=16,
        harm_count_vs_original=0,
        expected_hit_probability_regression_count_vs_original=16,
        average_profit_loss_delta_vs_original=0.4,
        average_hit_probability_delta_vs_original=-0.0169,
        production_recommendation_changed=False,
        items=[],
        summary_json={
            "selection_rule": "highest_candidate_hit_probability",
            "options": {
                "max_replacements_per_final_answer": 1,
                "min_replacement_probability": 0.55,
                "max_replacement_decimal_odds": 1.75,
                "min_candidate_hit_probability_delta_vs_model_top": -0.015,
                "max_candidate_hit_probability_delta_vs_model_top": 0.0,
                "min_decimal_odds_delta_vs_model_top": 0.0,
            },
        },
    )
