from __future__ import annotations

from json import dumps, loads
from pathlib import Path

from nutmeg.recommendations.global_planner_short_odds_adapter_gate import (
    HistoricalGlobalPlannerShortOddsAdapterGateOptions,
    build_global_planner_short_odds_adapter_gate_report,
    main,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayReport,
)


def test_global_planner_short_odds_adapter_gate_passes_real_history_evidence() -> None:
    report = build_global_planner_short_odds_adapter_gate_report(
        _planner_branch_report(),
        _runtime_shadow_replay_report(),
    )

    assert report.passed is True
    assert report.status == "passed"
    assert report.planner_default_path_changed is False
    assert report.planner_shadow_path_changed is False
    assert report.planner_explicit_opt_in_changed is True
    assert report.planner_shadow_adapter_status == "applied"
    assert report.runtime_final_answer_count == 30
    assert report.runtime_changed_final_answer_count == 17
    assert report.runtime_final_hit_harm_count_vs_original == 0
    assert report.runtime_profit_loss_harm_count_vs_original == 0
    assert report.summary_json["failed_checks"] == []


def test_global_planner_short_odds_adapter_gate_blocks_path_and_history_regression() -> None:
    planner_report = _planner_branch_report(
        default_path_changed=True,
        shadow_path_changed=True,
        explicit_opt_in_changed=False,
        shadow_status="unchanged",
    )
    runtime_report = _runtime_shadow_replay_report(
        passed=False,
        final_answer_hit_rate_delta=-0.01,
        roi_delta=-0.02,
        profit_loss_delta=-1.0,
        final_hit_harm_count_vs_original=1,
        profit_loss_harm_count_vs_original=1,
    )

    report = build_global_planner_short_odds_adapter_gate_report(
        planner_report,
        runtime_report,
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.passed is False
    assert {
        "planner_default_path_unchanged",
        "planner_shadow_path_unchanged",
        "planner_explicit_opt_in_changed",
        "planner_shadow_adapter_applied",
        "runtime_shadow_replay_passed",
        "runtime_shadow_replay_status_passed",
        "runtime_final_answer_hit_rate_delta",
        "runtime_roi_delta",
        "runtime_profit_loss_delta",
        "runtime_final_hit_harm_count_vs_original",
        "runtime_profit_loss_harm_count_vs_original",
    }.issubset(failed_checks)


def test_global_planner_short_odds_adapter_gate_cli_writes_report(
    tmp_path: Path,
) -> None:
    planner_path = tmp_path / "planner_branch.json"
    replay_path = tmp_path / "runtime_replay.json"
    output_path = tmp_path / "adapter_gate.json"
    planner_path.write_text(
        f"{dumps(_planner_branch_report(), indent=2)}\n",
        encoding="utf-8",
    )
    replay_path.write_text(
        _runtime_shadow_replay_report().model_dump_json(),
        encoding="utf-8",
    )

    main(
        [
            "--planner-branch-report",
            str(planner_path),
            "--runtime-shadow-replay-report",
            str(replay_path),
            "--output-path",
            str(output_path),
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["runtime_changed_final_answer_count"] == 17
    assert payload["summary_json"]["planner_shadow_adapter_status"] == "applied"


def test_global_planner_short_odds_adapter_gate_can_keep_opt_in_optional() -> None:
    report = build_global_planner_short_odds_adapter_gate_report(
        _planner_branch_report(explicit_opt_in_changed=False, opt_in_status="unchanged"),
        _runtime_shadow_replay_report(),
        options=HistoricalGlobalPlannerShortOddsAdapterGateOptions(
            require_explicit_opt_in_changed=False,
            require_opt_in_adapter_applied=False,
        ),
    )

    assert report.passed is True
    skipped = {check.name for check in report.checks if check.status == "skipped"}
    assert {
        "planner_explicit_opt_in_changed",
        "planner_opt_in_adapter_applied",
    }.issubset(skipped)


def _planner_branch_report(
    *,
    default_path_changed: bool = False,
    shadow_path_changed: bool = False,
    explicit_opt_in_changed: bool = True,
    shadow_status: str = "applied",
    opt_in_status: str = "applied",
) -> dict[str, object]:
    return {
        "calculation_basis": "global_planner_short_odds_adapter_branch_smoke_v3_1",
        "default_path_changed": default_path_changed,
        "shadow_path_changed": shadow_path_changed,
        "explicit_opt_in_changed": explicit_opt_in_changed,
        "cases": [
            {
                "case": "default_disabled",
                "best_fixture_ids": ["B", "A"],
                "adapter_summary": None,
            },
            {
                "case": "shadow_only",
                "best_fixture_ids": ["B", "A"],
                "adapter_summary": {
                    "status": shadow_status,
                    "planner_option_changed": False,
                },
            },
            {
                "case": "explicit_opt_in",
                "best_fixture_ids": ["B", "C"],
                "adapter_summary": {
                    "status": opt_in_status,
                    "planner_option_changed": explicit_opt_in_changed,
                },
            },
        ],
    }


def _runtime_shadow_replay_report(
    *,
    passed: bool = True,
    final_answer_hit_rate_delta: float = 0.0,
    roi_delta: float = 0.016,
    profit_loss_delta: float = 1.0,
    harm_count_vs_original: int = 0,
    final_hit_harm_count_vs_original: int = 0,
    profit_loss_harm_count_vs_original: int = 0,
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    return HistoricalShortOddsRuntimeShadowReplayReport.model_validate(
        {
            "report_key": "historical_short_odds_runtime_shadow_replay:test",
            "status": "shadow_replay_passed" if passed else "shadow_replay_failed",
            "passed": passed,
            "source_audit_report_key": "historical_candidate_marginal_audit:test",
            "source_rule_profile_version": "activated-profile-v1",
            "rule_count": 1,
            "enabled_rule_count": 1,
            "final_answer_count": 30,
            "changed_final_answer_count": 17,
            "baseline_final_answer_hit_count": 20,
            "shadow_final_answer_hit_count": 20,
            "final_answer_hit_delta_count": 0,
            "baseline_final_answer_hit_rate": 20 / 30,
            "shadow_final_answer_hit_rate": 20 / 30,
            "final_answer_hit_rate_delta": final_answer_hit_rate_delta,
            "baseline_profit_loss": 3.0,
            "shadow_profit_loss": 4.0,
            "profit_loss_delta": profit_loss_delta,
            "baseline_roi": 0.05,
            "shadow_roi": 0.066,
            "roi_delta": roi_delta,
            "total_stake": 60.0,
            "harm_count_vs_original": harm_count_vs_original,
            "final_hit_harm_count_vs_original": final_hit_harm_count_vs_original,
            "profit_loss_harm_count_vs_original": profit_loss_harm_count_vs_original,
            "average_hit_probability_delta_vs_original": -0.014,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "checks": [],
            "rule_set_json": {},
            "changed_items": [],
            "warnings": [],
            "summary_json": {},
        }
    )
