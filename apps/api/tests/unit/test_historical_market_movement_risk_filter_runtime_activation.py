from __future__ import annotations

from json import loads
from pathlib import Path

from nutmeg.recommendations.historical_market_movement_risk_filter_runtime_activation import (
    HistoricalMarketMovementRiskFilterRuntimeActivationOptions,
    _options_from_args,
    _parse_args,
    build_historical_market_movement_risk_filter_runtime_activation_report,
    main,
)


def test_market_movement_runtime_activation_ready_from_replay_and_suite_gate() -> None:
    report = build_historical_market_movement_risk_filter_runtime_activation_report(
        rule_profile=_runtime_profile(),
        runtime_replay_report=_runtime_replay_report(),
        suite_quality_gate_report=_suite_gate_report(),
        options=HistoricalMarketMovementRiskFilterRuntimeActivationOptions(
            min_adjusted_fixture_count=100,
            min_adjusted_prediction_count=300,
        ),
    )

    assert report.status == "staged_activation_ready"
    assert report.staged_activation_ready is True
    assert report.blockers == []
    assert all(check.status == "passed" for check in report.checks)
    assert report.selected_rule_ids == ["market_movement_risk_filter_runtime_shadow_candidate_v1"]
    assert report.selected_segment_group_keys == ["competition_outcome:LA_LIGA:home_win"]
    assert set(report.rollback_conditions) == {
        "disable_if_shadow_replay_fails_no_harm_gate",
        "disable_if_default_path_or_public_response_would_change",
        "disable_if_future_folds_regress_final_answer_or_probability_quality",
    }
    assert report.default_profile_written is False
    assert report.production_recommendation_changed is False
    assert report.public_response_changed is False
    assert report.staged_profile_json["staged_only"] is True
    assert report.staged_profile_json["default_recommendation_path_changed"] is False
    assert report.staged_profile_json["public_response_changed"] is False


def test_market_movement_runtime_activation_blocks_missing_safety_guards() -> None:
    report = build_historical_market_movement_risk_filter_runtime_activation_report(
        rule_profile=_runtime_profile(
            default_path_changed=True,
            rollback_conditions=["disable_if_shadow_replay_fails_no_harm_gate"],
        ),
        runtime_replay_report=_runtime_replay_report(
            status="shadow_replay_failed",
            runtime_allowed=False,
            brier_score_delta=0.01,
            public_response_changed=True,
        ),
        suite_quality_gate_report=_suite_gate_report(passed=False),
    )

    failed_checks = {check.name for check in report.checks if check.status == "failed"}

    assert report.status == "blocked"
    assert report.staged_activation_ready is False
    assert report.staged_profile_json["market_movement_risk_filter_rules"] == []
    assert {
        "suite_gate_passed",
        "runtime_replay_status",
        "runtime_replay_allowed",
        "rollback_conditions_present",
        "brier_score_delta",
        "no_default_path_change",
        "no_public_response_change",
    }.issubset(failed_checks)


def test_market_movement_runtime_activation_cli_writes_report_and_profile(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "profile.json"
    replay_path = tmp_path / "replay.json"
    suite_gate_path = tmp_path / "suite_gate.json"
    output_path = tmp_path / "activation.json"
    staged_profile_path = tmp_path / "staged_profile.json"
    profile_path.write_text(_json(_runtime_profile()), encoding="utf-8")
    replay_path.write_text(_json(_runtime_replay_report()), encoding="utf-8")
    suite_gate_path.write_text(_json(_suite_gate_report()), encoding="utf-8")

    args = _parse_args(
        [
            "--rule-profile",
            str(profile_path),
            "--runtime-replay-report",
            str(replay_path),
            "--suite-quality-gate-report",
            str(suite_gate_path),
            "--report-output-path",
            str(output_path),
            "--staged-profile-output-path",
            str(staged_profile_path),
            "--staged-profile-version",
            "market-movement-staged:test",
            "--min-adjusted-fixture-count",
            "120",
            "--min-adjusted-prediction-count",
            "360",
            "--no-fail-process",
        ]
    )
    options = _options_from_args(args)

    assert options.staged_profile_version == "market-movement-staged:test"
    assert options.min_adjusted_fixture_count == 120
    assert options.min_adjusted_prediction_count == 360

    main(
        [
            "--rule-profile",
            str(profile_path),
            "--runtime-replay-report",
            str(replay_path),
            "--suite-quality-gate-report",
            str(suite_gate_path),
            "--report-output-path",
            str(output_path),
            "--staged-profile-output-path",
            str(staged_profile_path),
            "--staged-profile-version",
            "market-movement-staged:test",
        ]
    )

    payload = loads(output_path.read_text(encoding="utf-8"))
    staged_profile = loads(staged_profile_path.read_text(encoding="utf-8"))
    assert payload["status"] == "staged_activation_ready"
    assert staged_profile["profile_version"] == "market-movement-staged:test"
    assert staged_profile["default_profile_written"] is False
    assert staged_profile["market_movement_risk_filter_rules"][0]["rule_id"] == (
        "market_movement_risk_filter_runtime_shadow_candidate_v1"
    )


def _runtime_profile(
    *,
    default_path_changed: bool = False,
    rollback_conditions: list[str] | None = None,
) -> dict[str, object]:
    rule = {
        "rule_id": "market_movement_risk_filter_runtime_shadow_candidate_v1",
        "proposed_profile_version": "v3_2_market_movement_risk_filter_runtime_shadow_candidate",
        "proposed_production_enabled": False,
        "holdout_candidate_enabled": True,
        "shadow_replay_enabled": True,
        "production_recommendation_changed": False,
        "segment_group_keys": ["competition_outcome:LA_LIGA:home_win"],
        "movement_weight": 0.5,
        "max_probability_shift": 0.08,
        "source_guarded_admission_report_key": (
            "historical_market_movement_risk_filter_guarded_admission:test"
        ),
        "source_segment_gate_report_key": "historical_market_movement_segment_gate:test",
        "source_guarded_segment_gate_report_key": (
            "historical_market_movement_guarded_segment_gate:test"
        ),
        "source_candidate_id": "market-movement-segment-gate:test",
        "source_report_keys": {
            "guarded_admission": (
                "historical_market_movement_risk_filter_guarded_admission:test"
            ),
            "scope_refinement": (
                "historical_market_movement_risk_filter_scope_refinement:test"
            ),
        },
        "evidence_json": {
            "best_segment_group_key": "competition_outcome:LA_LIGA:home_win",
        },
        "constraints_json": {
            "shadow_replay_only": True,
            "production_recommendation_changed": False,
            "public_response_changed": False,
        },
        "rollback_conditions": rollback_conditions
        or [
            "disable_if_shadow_replay_fails_no_harm_gate",
            "disable_if_default_path_or_public_response_would_change",
            "disable_if_future_folds_regress_final_answer_or_probability_quality",
        ],
    }
    return {
        "calculation_basis": (
            "historical_market_movement_risk_filter_runtime_profile_set_v3_2"
        ),
        "profile_version": "v3_2_market_movement_risk_filter_runtime_shadow_candidate",
        "status": "runtime_shadow_proposal_ready",
        "runtime_shadow_proposal_allowed": True,
        "runtime_profile_proposal_allowed": True,
        "holdout_candidate_allowed": True,
        "production_recommendation_changed": False,
        "default_recommendation_path_changed": default_path_changed,
        "public_response_changed": False,
        "market_movement_risk_filter_rules": [rule],
        "rules": [rule],
    }


def _runtime_replay_report(
    *,
    status: str = "runtime_shadow_replay_passed",
    runtime_allowed: bool = True,
    brier_score_delta: float = -0.001288,
    public_response_changed: bool = False,
) -> dict[str, object]:
    return {
        "report_key": "historical_market_movement_risk_filter_runtime_replay:test",
        "status": status,
        "runtime_shadow_replay_allowed": runtime_allowed,
        "holdout_replay_allowed": runtime_allowed,
        "source_rule_profile_version": (
            "v3_2_market_movement_risk_filter_runtime_shadow_candidate"
        ),
        "rule_count": 1,
        "selected_rule_count": 1,
        "selected_rule_id": "market_movement_risk_filter_runtime_shadow_candidate_v1",
        "selected_segment_group_key": "competition_outcome:LA_LIGA:home_win",
        "candidate_count": 1,
        "accepted_count": 1,
        "adjusted_fixture_count": 120,
        "adjusted_prediction_count": 360,
        "final_hit_rate_delta": 0.0,
        "roi_delta": 0.0,
        "profit_loss_delta": 0.0,
        "brier_score_delta": brier_score_delta,
        "log_loss_delta": -0.002761,
        "mean_calibration_error_delta": -0.001278,
        "production_recommendation_changed": False,
        "public_response_changed": public_response_changed,
    }


def _suite_gate_report(*, passed: bool = True) -> dict[str, object]:
    return {
        "gate_key": "historical_recommendation_suite_quality_gate:test",
        "status": "passed" if passed else "failed",
        "passed": passed,
        "summary_json": {
            "market_movement_runtime_replay_present": True,
            "market_movement_runtime_replay_passed": True,
            "market_movement_runtime_replay_key": (
                "historical_market_movement_risk_filter_runtime_replay:test"
            ),
            "market_movement_runtime_replay_allowed": True,
        },
    }


def _json(payload: dict[str, object]) -> str:
    import json

    return f"{json.dumps(payload, indent=2)}\n"
