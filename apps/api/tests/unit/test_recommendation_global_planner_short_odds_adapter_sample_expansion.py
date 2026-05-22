from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations.global_planner_short_odds_adapter_gate import (
    HistoricalGlobalPlannerShortOddsAdapterGateReport,
)
from nutmeg.recommendations.global_planner_short_odds_adapter_sample_expansion import (
    HistoricalGlobalPlannerShortOddsAdapterSampleExpansionOptions,
    build_global_planner_short_odds_adapter_sample_expansion_report,
    main,
)
from nutmeg.recommendations.replacement_short_odds_runtime_shadow import (
    HistoricalShortOddsRuntimeShadowReplayReport,
)


def test_sample_expansion_marks_safe_but_inactive_supplement_as_research_only() -> None:
    report = build_global_planner_short_odds_adapter_sample_expansion_report(
        _base_gate_report(),
        supplemental_replays=[_runtime_shadow_replay_report(changed_count=0)],
    )
    watchlist_checks = {
        check.name for check in report.checks if check.status == "watchlist"
    }

    assert report.status == "research_only"
    assert report.passed is True
    assert report.promotion_ready is False
    assert report.supplemental_final_answer_count == 56
    assert report.supplemental_changed_final_answer_count == 0
    assert report.combined_final_answer_count == 86
    assert report.combined_changed_final_answer_count == 17
    assert report.combined_harm_count_vs_original == 0
    assert "supplemental_changed_final_answer_count" in watchlist_checks


def test_sample_expansion_is_ready_when_supplement_activates_without_regression() -> None:
    report = build_global_planner_short_odds_adapter_sample_expansion_report(
        _base_gate_report(),
        supplemental_replays=[
            _runtime_shadow_replay_report(
                changed_count=2,
                profit_loss_delta=2.0,
                roi_delta=0.02,
                average_hit_probability_delta=-0.01,
            )
        ],
    )

    assert report.status == "expansion_ready"
    assert report.passed is True
    assert report.promotion_ready is True
    assert report.supplemental_activation_rate == 2 / 56
    assert report.combined_changed_final_answer_count == 19
    assert report.summary_json["watchlist_checks"] == []


def test_sample_expansion_blocks_harmful_supplemental_evidence() -> None:
    report = build_global_planner_short_odds_adapter_sample_expansion_report(
        _base_gate_report(),
        supplemental_replays=[
            _runtime_shadow_replay_report(
                changed_count=2,
                passed=False,
                profit_loss_delta=-1.0,
                roi_delta=-0.01,
                harm_count=1,
                final_hit_harm_count=1,
                profit_loss_harm_count=1,
            )
        ],
        options=HistoricalGlobalPlannerShortOddsAdapterSampleExpansionOptions(
            min_combined_roi_delta=0.01,
        ),
    )
    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.passed is False
    assert report.promotion_ready is False
    assert "supplemental_failed_report_count" in failed_checks
    assert "combined_harm_count_vs_original" in failed_checks
    assert "combined_final_hit_harm_count_vs_original" in failed_checks
    assert "combined_profit_loss_harm_count_vs_original" in failed_checks


def test_sample_expansion_cli_writes_report(tmp_path: Path) -> None:
    base_path = tmp_path / "base_gate.json"
    supplemental_path = tmp_path / "supplemental.json"
    output_path = tmp_path / "sample_expansion.json"
    base_path.write_text(
        f"{_base_gate_report().model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )
    supplemental_path.write_text(
        f"{_runtime_shadow_replay_report(changed_count=0).model_dump_json(indent=2)}\n",
        encoding="utf-8",
    )

    main(
        [
            "--base-gate-report",
            str(base_path),
            "--supplemental-runtime-shadow-replay-report",
            str(supplemental_path),
            "--output-path",
            str(output_path),
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "research_only"
    assert payload["passed"] is True
    assert payload["promotion_ready"] is False
    assert payload["summary_json"]["watchlist_checks"] == [
        "supplemental_changed_final_answer_count"
    ]


def _base_gate_report() -> HistoricalGlobalPlannerShortOddsAdapterGateReport:
    return HistoricalGlobalPlannerShortOddsAdapterGateReport.model_validate(
        {
            "report_key": "global_planner_short_odds_adapter_gate:test",
            "status": "passed",
            "passed": True,
            "source_planner_branch_report_key": "planner-branch:test",
            "source_runtime_shadow_replay_report_key": "runtime-shadow:test",
            "source_rule_profile_version": "short-odds-profile-test",
            "planner_default_path_changed": False,
            "planner_shadow_path_changed": False,
            "planner_explicit_opt_in_changed": True,
            "planner_shadow_adapter_status": "applied",
            "planner_opt_in_adapter_status": "applied",
            "runtime_replay_passed": True,
            "runtime_replay_status": "shadow_replay_passed",
            "runtime_final_answer_count": 30,
            "runtime_changed_final_answer_count": 17,
            "runtime_final_answer_hit_rate_delta": 0.0,
            "runtime_roi_delta": 0.017638871546666643,
            "runtime_profit_loss_delta": 1.058332292799999,
            "runtime_harm_count_vs_original": 0,
            "runtime_final_hit_harm_count_vs_original": 0,
            "runtime_profit_loss_harm_count_vs_original": 0,
            "runtime_average_hit_probability_delta": -0.014697457992009506,
            "runtime_public_response_changed": False,
            "runtime_production_recommendation_changed": False,
            "checks": [],
            "warnings": [],
            "summary_json": {},
        }
    )


def _runtime_shadow_replay_report(
    *,
    changed_count: int,
    passed: bool = True,
    profit_loss_delta: float = 0.0,
    roi_delta: float = 0.0,
    average_hit_probability_delta: float = 0.0,
    harm_count: int = 0,
    final_hit_harm_count: int = 0,
    profit_loss_harm_count: int = 0,
) -> HistoricalShortOddsRuntimeShadowReplayReport:
    return HistoricalShortOddsRuntimeShadowReplayReport.model_validate(
        {
            "report_key": "historical_short_odds_runtime_shadow_replay:supplemental",
            "status": "shadow_replay_passed" if passed else "shadow_replay_failed",
            "passed": passed,
            "source_audit_report_key": "historical_candidate_marginal_audit:test",
            "source_rule_profile_version": "short-odds-profile-test",
            "rule_count": 1,
            "enabled_rule_count": 1,
            "final_answer_count": 56,
            "changed_final_answer_count": changed_count,
            "baseline_final_answer_hit_count": 15,
            "shadow_final_answer_hit_count": 15,
            "final_answer_hit_delta_count": 0,
            "baseline_final_answer_hit_rate": 15 / 56,
            "shadow_final_answer_hit_rate": 15 / 56,
            "final_answer_hit_rate_delta": 0.0,
            "baseline_profit_loss": -36.17099999999999,
            "shadow_profit_loss": -36.17099999999999 + profit_loss_delta,
            "profit_loss_delta": profit_loss_delta,
            "baseline_roi": -0.13496641791044772,
            "shadow_roi": -0.13496641791044772 + roi_delta,
            "roi_delta": roi_delta,
            "total_stake": 268.0,
            "harm_count_vs_original": harm_count,
            "final_hit_harm_count_vs_original": final_hit_harm_count,
            "profit_loss_harm_count_vs_original": profit_loss_harm_count,
            "average_hit_probability_delta_vs_original": average_hit_probability_delta,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "checks": [],
            "rule_set_json": {},
            "changed_items": [],
            "warnings": [],
            "summary_json": {},
        }
    )
