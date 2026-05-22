from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Iterable, Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

type HistoricalMarketMovementRiskFilterRuntimeActivationStatus = Literal[
    "staged_activation_ready",
    "watchlist",
    "blocked",
]
type HistoricalMarketMovementRiskFilterRuntimeActivationCheckStatus = Literal[
    "passed",
    "failed",
]

DEFAULT_ROLLBACK_CONDITIONS = (
    "disable_if_shadow_replay_fails_no_harm_gate",
    "disable_if_default_path_or_public_response_would_change",
    "disable_if_future_folds_regress_final_answer_or_probability_quality",
)


class HistoricalMarketMovementRiskFilterRuntimeActivationOptions(BaseModel):
    staged_profile_version: str = (
        "v3_2_market_movement_risk_filter_runtime_staged_activation_candidate"
    )
    min_rule_count: int = Field(default=1, ge=1)
    min_selected_rule_count: int = Field(default=1, ge=1)
    max_selected_rule_count: int = Field(default=1, ge=1)
    min_adjusted_fixture_count: int = Field(default=1, ge=0)
    min_adjusted_prediction_count: int = Field(default=1, ge=0)
    min_final_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    require_suite_gate_passed: bool = True
    require_suite_gate_runtime_evidence: bool = True
    require_runtime_replay_allowed: bool = True
    require_runtime_replay_passed_status: bool = True
    require_profile_runtime_shadow_allowed: bool = True
    require_profile_holdout_allowed: bool = True
    require_rules_holdout_enabled: bool = True
    require_rules_shadow_replay_enabled: bool = True
    require_rules_production_disabled: bool = True
    require_rule_source_chain_complete: bool = True
    require_rule_rollback_conditions: bool = True
    required_rollback_conditions: tuple[str, ...] = DEFAULT_ROLLBACK_CONDITIONS
    require_no_default_path_change: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True


class HistoricalMarketMovementRiskFilterRuntimeActivationCheck(BaseModel):
    name: str
    status: HistoricalMarketMovementRiskFilterRuntimeActivationCheckStatus
    actual: float | int | str | bool | list[str] | None = None
    threshold: float | int | str | bool | list[str] | None = None
    detail: str


class HistoricalMarketMovementRiskFilterRuntimeActivationReport(BaseModel):
    report_key: str
    status: HistoricalMarketMovementRiskFilterRuntimeActivationStatus
    staged_activation_ready: bool
    staged_profile_version: str
    source_suite_gate_key: str | None = None
    source_runtime_replay_report_key: str | None = None
    source_runtime_profile_version: str
    rule_count: int = Field(ge=0)
    selected_rule_count: int = Field(ge=0)
    selected_rule_ids: list[str] = Field(default_factory=list)
    selected_segment_group_keys: list[str] = Field(default_factory=list)
    rollback_conditions: list[str] = Field(default_factory=list)
    adjusted_fixture_count: int = Field(ge=0)
    adjusted_prediction_count: int = Field(ge=0)
    final_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    default_profile_write_requested: bool = False
    default_profile_written: bool = False
    production_recommendation_allowed: bool = False
    production_recommendation_changed: bool = False
    default_recommendation_path_changed: bool = False
    public_response_changed: bool = False
    checks: list[HistoricalMarketMovementRiskFilterRuntimeActivationCheck] = Field(
        default_factory=list
    )
    blockers: list[str] = Field(default_factory=list)
    staged_profile_json: dict[str, object] = Field(default_factory=dict)
    public_contract_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_market_movement_risk_filter_runtime_activation_report(
    *,
    rule_profile: Mapping[str, object] | object,
    runtime_replay_report: Mapping[str, object] | object,
    suite_quality_gate_report: Mapping[str, object] | object,
    options: (
        HistoricalMarketMovementRiskFilterRuntimeActivationOptions | None
    ) = None,
) -> HistoricalMarketMovementRiskFilterRuntimeActivationReport:
    resolved_options = (
        options or HistoricalMarketMovementRiskFilterRuntimeActivationOptions()
    )
    raw_profile = _object_mapping(rule_profile)
    replay = _object_mapping(runtime_replay_report)
    suite_gate = _object_mapping(suite_quality_gate_report)
    rules = _rule_list(raw_profile)
    selected_rule_id = _string(replay.get("selected_rule_id"))
    selected_rules = _selected_rules(
        rules,
        selected_rule_id=selected_rule_id,
        options=resolved_options,
    )
    selected_rule_ids = [
        rule_id
        for rule in selected_rules
        for rule_id in [_string(rule.get("rule_id"))]
        if rule_id
    ]
    selected_segment_group_keys = _unique(
        segment
        for rule in selected_rules
        for segment in _string_list(rule.get("segment_group_keys"))
    )
    rollback_conditions = _unique(
        condition
        for rule in selected_rules
        for condition in _string_list(rule.get("rollback_conditions"))
    )
    public_contract_json: dict[str, object] = {
        "public_response_changed": False,
        "frontend_changed": False,
        "ordinary_user_path_changed": False,
        "internal_strategy_details_exposed": False,
        "production_recommendation_changed": False,
        "default_recommendation_path_changed": False,
        "default_profile_written": False,
    }
    checks = _checks(
        profile=raw_profile,
        replay=replay,
        suite_gate=suite_gate,
        rules=rules,
        selected_rules=selected_rules,
        selected_rule_ids=selected_rule_ids,
        selected_segment_group_keys=selected_segment_group_keys,
        rollback_conditions=rollback_conditions,
        public_contract_json=public_contract_json,
        options=resolved_options,
    )
    blockers = [check.name for check in checks if check.status == "failed"]
    status = _status(blockers)
    staged_activation_ready = status == "staged_activation_ready"
    staged_profile = _staged_profile_json(
        profile=raw_profile,
        selected_rules=selected_rules if staged_activation_ready else [],
        suite_gate=suite_gate,
        replay=replay,
        rollback_conditions=rollback_conditions,
        options=resolved_options,
    )
    warnings = _warnings(status=status, blockers=blockers)
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_risk_filter_runtime_activation_v3_2"
        ),
        "status": status,
        "staged_activation_ready": staged_activation_ready,
        "staged_profile_version": resolved_options.staged_profile_version,
        "source_suite_gate_key": _string(suite_gate.get("gate_key")),
        "source_runtime_replay_report_key": _string(replay.get("report_key")),
        "source_runtime_profile_version": _profile_version(raw_profile),
        "source_runtime_profile_status": _string(raw_profile.get("status")),
        "rule_count": len(rules),
        "selected_rule_count": len(selected_rules),
        "selected_rule_ids": selected_rule_ids,
        "selected_segment_group_keys": selected_segment_group_keys,
        "rollback_conditions": rollback_conditions,
        "adjusted_fixture_count": _int(replay.get("adjusted_fixture_count")),
        "adjusted_prediction_count": _int(replay.get("adjusted_prediction_count")),
        "final_hit_rate_delta": _float(replay.get("final_hit_rate_delta")),
        "roi_delta": _float(replay.get("roi_delta")),
        "profit_loss_delta": _float(replay.get("profit_loss_delta")),
        "brier_score_delta": _float(replay.get("brier_score_delta")),
        "log_loss_delta": _float(replay.get("log_loss_delta")),
        "mean_calibration_error_delta": _float(
            replay.get("mean_calibration_error_delta")
        ),
        "default_profile_write_requested": False,
        "default_profile_written": False,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "default_recommendation_path_changed": False,
        "public_response_changed": False,
        "blockers": blockers,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, staged_profile)
    return HistoricalMarketMovementRiskFilterRuntimeActivationReport(
        report_key=report_key,
        status=status,
        staged_activation_ready=staged_activation_ready,
        staged_profile_version=resolved_options.staged_profile_version,
        source_suite_gate_key=_string(suite_gate.get("gate_key")),
        source_runtime_replay_report_key=_string(replay.get("report_key")),
        source_runtime_profile_version=_profile_version(raw_profile),
        rule_count=len(rules),
        selected_rule_count=len(selected_rules),
        selected_rule_ids=selected_rule_ids,
        selected_segment_group_keys=selected_segment_group_keys,
        rollback_conditions=rollback_conditions,
        adjusted_fixture_count=_int(replay.get("adjusted_fixture_count")),
        adjusted_prediction_count=_int(replay.get("adjusted_prediction_count")),
        final_hit_rate_delta=_float(replay.get("final_hit_rate_delta")),
        roi_delta=_float(replay.get("roi_delta")),
        profit_loss_delta=_float(replay.get("profit_loss_delta")),
        brier_score_delta=_float(replay.get("brier_score_delta")),
        log_loss_delta=_float(replay.get("log_loss_delta")),
        mean_calibration_error_delta=_float(
            replay.get("mean_calibration_error_delta")
        ),
        checks=checks,
        blockers=blockers,
        staged_profile_json=staged_profile,
        public_contract_json=public_contract_json,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_market_movement_risk_filter_runtime_activation_report(
    path: Path | str,
) -> HistoricalMarketMovementRiskFilterRuntimeActivationReport:
    return HistoricalMarketMovementRiskFilterRuntimeActivationReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_market_movement_risk_filter_runtime_activation_report(
        rule_profile=_load_json(args.rule_profile),
        runtime_replay_report=_load_json(args.runtime_replay_report),
        suite_quality_gate_report=_load_json(args.suite_quality_gate_report),
        options=_options_from_args(args),
    )
    if args.staged_profile_output_path is not None and report.staged_activation_ready:
        args.staged_profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.staged_profile_output_path.write_text(
            f"{dumps(report.staged_profile_json, indent=2)}\n",
            encoding="utf-8",
        )
    if args.report_output_path is not None:
        args.report_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_output_path.write_text(
            f"{report.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    print(
        dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if report.status == "blocked" and not args.no_fail_process:
        raise SystemExit(1)


def _checks(
    *,
    profile: Mapping[str, object],
    replay: Mapping[str, object],
    suite_gate: Mapping[str, object],
    rules: Sequence[Mapping[str, object]],
    selected_rules: Sequence[Mapping[str, object]],
    selected_rule_ids: Sequence[str],
    selected_segment_group_keys: Sequence[str],
    rollback_conditions: Sequence[str],
    public_contract_json: Mapping[str, object],
    options: HistoricalMarketMovementRiskFilterRuntimeActivationOptions,
) -> list[HistoricalMarketMovementRiskFilterRuntimeActivationCheck]:
    suite_summary = _object_mapping(suite_gate.get("summary_json", {}))
    return [
        _boolean_check(
            name="suite_gate_passed",
            actual=_bool(suite_gate.get("passed")),
            expected=True,
            enabled=options.require_suite_gate_passed,
            detail="source suite quality gate should pass",
        ),
        _boolean_check(
            name="suite_gate_runtime_replay_present",
            actual=_bool(suite_summary.get("market_movement_runtime_replay_present")),
            expected=True,
            enabled=options.require_suite_gate_runtime_evidence,
            detail="source suite gate should carry runtime replay evidence",
        ),
        _boolean_check(
            name="suite_gate_runtime_replay_allowed",
            actual=_bool(suite_summary.get("market_movement_runtime_replay_allowed")),
            expected=True,
            enabled=options.require_suite_gate_runtime_evidence,
            detail="source suite gate runtime replay evidence should be allowed",
        ),
        _boolean_check(
            name="suite_gate_replay_key_matches",
            actual=(
                _string(suite_summary.get("market_movement_runtime_replay_key"))
                == _string(replay.get("report_key"))
            ),
            expected=True,
            enabled=options.require_suite_gate_runtime_evidence,
            detail="source suite gate should reference the same runtime replay report",
        ),
        _equality_check(
            name="runtime_replay_status",
            actual=_string(replay.get("status")) or "",
            expected="runtime_shadow_replay_passed",
            enabled=options.require_runtime_replay_passed_status,
            detail="runtime replay should have the pass status",
        ),
        _boolean_check(
            name="runtime_replay_allowed",
            actual=_bool(replay.get("runtime_shadow_replay_allowed")),
            expected=True,
            enabled=options.require_runtime_replay_allowed,
            detail="runtime replay should be shadow-allowed",
        ),
        _boolean_check(
            name="runtime_replay_holdout_allowed",
            actual=_bool(replay.get("holdout_replay_allowed")),
            expected=True,
            enabled=options.require_runtime_replay_allowed,
            detail="runtime replay should remain holdout-allowed",
        ),
        _minimum_check(
            name="rule_count",
            actual=len(rules),
            threshold=options.min_rule_count,
            detail="runtime profile should contain enough rules",
        ),
        _minimum_check(
            name="selected_rule_count",
            actual=len(selected_rules),
            threshold=options.min_selected_rule_count,
            detail="activation preflight should select enough matching rules",
        ),
        _maximum_check(
            name="selected_rule_count_max",
            actual=len(selected_rules),
            threshold=options.max_selected_rule_count,
            detail="activation preflight should keep the selected rule set bounded",
        ),
        _boolean_check(
            name="selected_rule_matches_replay",
            actual=(
                _string(replay.get("selected_rule_id")) in set(selected_rule_ids)
                if _string(replay.get("selected_rule_id")) is not None
                else bool(selected_rule_ids)
            ),
            expected=True,
            detail="selected runtime rule should match the replay report",
        ),
        _boolean_check(
            name="selected_segment_matches_replay",
            actual=(
                _string(replay.get("selected_segment_group_key"))
                in set(selected_segment_group_keys)
                if _string(replay.get("selected_segment_group_key")) is not None
                else bool(selected_segment_group_keys)
            ),
            expected=True,
            detail="selected segment should match the replay report",
        ),
        _boolean_check(
            name="profile_runtime_shadow_allowed",
            actual=(
                _bool(profile.get("runtime_shadow_proposal_allowed"))
                or _bool(profile.get("runtime_profile_proposal_allowed"))
            ),
            expected=True,
            enabled=options.require_profile_runtime_shadow_allowed,
            detail="runtime profile should be shadow proposal allowed",
        ),
        _boolean_check(
            name="profile_holdout_allowed",
            actual=_bool(profile.get("holdout_candidate_allowed")),
            expected=True,
            enabled=options.require_profile_holdout_allowed,
            detail="runtime profile should be holdout allowed",
        ),
        _boolean_check(
            name="rules_holdout_enabled",
            actual=all(_bool(rule.get("holdout_candidate_enabled")) for rule in selected_rules),
            expected=True,
            enabled=options.require_rules_holdout_enabled,
            detail="selected rules should keep holdout enabled",
        ),
        _boolean_check(
            name="rules_shadow_replay_enabled",
            actual=all(_bool(rule.get("shadow_replay_enabled")) for rule in selected_rules),
            expected=True,
            enabled=options.require_rules_shadow_replay_enabled,
            detail="selected rules should keep shadow replay enabled",
        ),
        _boolean_check(
            name="rules_production_disabled",
            actual=not any(
                _bool(rule.get("proposed_production_enabled"))
                for rule in selected_rules
            ),
            expected=True,
            enabled=options.require_rules_production_disabled,
            detail="selected rules should remain production-disabled",
        ),
        _boolean_check(
            name="rule_source_chain_complete",
            actual=all(_rule_source_chain_complete(rule) for rule in selected_rules),
            expected=True,
            enabled=options.require_rule_source_chain_complete,
            detail="selected rules should preserve source evidence lineage",
        ),
        _boolean_check(
            name="rollback_conditions_present",
            actual=set(options.required_rollback_conditions).issubset(
                set(rollback_conditions)
            ),
            expected=True,
            enabled=options.require_rule_rollback_conditions,
            detail="selected rules should include required rollback conditions",
        ),
        _minimum_check(
            name="adjusted_fixture_count",
            actual=_int(replay.get("adjusted_fixture_count")),
            threshold=options.min_adjusted_fixture_count,
            detail="runtime replay should adjust enough fixtures",
        ),
        _minimum_check(
            name="adjusted_prediction_count",
            actual=_int(replay.get("adjusted_prediction_count")),
            threshold=options.min_adjusted_prediction_count,
            detail="runtime replay should adjust enough predictions",
        ),
        _optional_minimum_check(
            name="final_hit_rate_delta",
            actual=_float(replay.get("final_hit_rate_delta")),
            threshold=options.min_final_hit_rate_delta,
            detail="runtime replay final-hit rate should not regress",
        ),
        _optional_minimum_check(
            name="roi_delta",
            actual=_float(replay.get("roi_delta")),
            threshold=options.min_roi_delta,
            detail="runtime replay ROI should not regress",
        ),
        _optional_minimum_check(
            name="profit_loss_delta",
            actual=_float(replay.get("profit_loss_delta")),
            threshold=options.min_profit_loss_delta,
            detail="runtime replay profit/loss should not regress",
        ),
        _optional_maximum_check(
            name="brier_score_delta",
            actual=_float(replay.get("brier_score_delta")),
            threshold=options.max_brier_score_delta,
            detail="runtime replay Brier score should not regress",
        ),
        _optional_maximum_check(
            name="log_loss_delta",
            actual=_float(replay.get("log_loss_delta")),
            threshold=options.max_log_loss_delta,
            detail="runtime replay log loss should not regress",
        ),
        _optional_maximum_check(
            name="mean_calibration_error_delta",
            actual=_float(replay.get("mean_calibration_error_delta")),
            threshold=options.max_mean_calibration_error_delta,
            detail="runtime replay calibration should not regress",
        ),
        _boolean_check(
            name="no_default_path_change",
            actual=not _bool(profile.get("default_recommendation_path_changed")),
            expected=True,
            enabled=options.require_no_default_path_change,
            detail="activation preflight should not change the default path",
        ),
        _boolean_check(
            name="no_production_recommendation_change",
            actual=not _bool(profile.get("production_recommendation_changed"))
            and not _bool(replay.get("production_recommendation_changed"))
            and not any(
                _bool(rule.get("production_recommendation_changed"))
                for rule in selected_rules
            ),
            expected=True,
            enabled=options.require_no_production_change,
            detail="activation preflight should not change production recommendations",
        ),
        _boolean_check(
            name="no_public_response_change",
            actual=not _bool(profile.get("public_response_changed"))
            and not _bool(replay.get("public_response_changed")),
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="activation preflight should not change public responses",
        ),
        _boolean_check(
            name="public_contract_unchanged",
            actual=not _bool(public_contract_json.get("public_response_changed"))
            and not _bool(public_contract_json.get("ordinary_user_path_changed"))
            and not _bool(public_contract_json.get("internal_strategy_details_exposed")),
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="public contract should remain unchanged",
        ),
    ]


def _staged_profile_json(
    *,
    profile: Mapping[str, object],
    selected_rules: Sequence[Mapping[str, object]],
    suite_gate: Mapping[str, object],
    replay: Mapping[str, object],
    rollback_conditions: Sequence[str],
    options: HistoricalMarketMovementRiskFilterRuntimeActivationOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": (
            "historical_market_movement_risk_filter_runtime_staged_profile_v3_2"
        ),
        "profile_version": options.staged_profile_version,
        "staged_only": True,
        "shadow_replay_enabled": True,
        "default_profile_write_requested": False,
        "default_profile_written": False,
        "production_recommendation_allowed": False,
        "production_recommendation_changed": False,
        "default_recommendation_path_changed": False,
        "public_response_changed": False,
        "base_runtime_profile_version": _profile_version(profile),
        "source_suite_gate_key": _string(suite_gate.get("gate_key")),
        "source_runtime_replay_report_key": _string(replay.get("report_key")),
        "rollback_conditions": list(rollback_conditions),
        "market_movement_risk_filter_rules": [
            dict(rule) for rule in selected_rules
        ],
        "rules": [dict(rule) for rule in selected_rules],
        "source_profile_json": {
            "profile_version": _profile_version(profile),
            "status": _string(profile.get("status")),
            "runtime_shadow_proposal_allowed": _bool(
                profile.get("runtime_shadow_proposal_allowed")
            ),
            "runtime_profile_proposal_allowed": _bool(
                profile.get("runtime_profile_proposal_allowed")
            ),
            "holdout_candidate_allowed": _bool(profile.get("holdout_candidate_allowed")),
        },
        "notes": [
            "Staged activation preflight only; not written to the default profile.",
            "User-facing recommendations and public responses remain unchanged.",
        ],
    }


def _selected_rules(
    rules: Sequence[Mapping[str, object]],
    *,
    selected_rule_id: str | None,
    options: HistoricalMarketMovementRiskFilterRuntimeActivationOptions,
) -> list[Mapping[str, object]]:
    selected = [
        rule
        for rule in rules
        if selected_rule_id is None or _string(rule.get("rule_id")) == selected_rule_id
    ]
    if not options.require_rules_shadow_replay_enabled:
        return selected
    return [rule for rule in selected if _bool(rule.get("shadow_replay_enabled"))]


def _status(
    blockers: Sequence[str],
) -> HistoricalMarketMovementRiskFilterRuntimeActivationStatus:
    if blockers:
        return "blocked"
    return "staged_activation_ready"


def _rule_source_chain_complete(rule: Mapping[str, object]) -> bool:
    source_report_keys = _object_mapping(rule.get("source_report_keys", {}))
    return all(
        bool(_string(rule.get(key)))
        for key in (
            "source_guarded_admission_report_key",
            "source_segment_gate_report_key",
            "source_guarded_segment_gate_report_key",
            "source_candidate_id",
        )
    ) and all(
        bool(_string(source_report_keys.get(key)))
        for key in ("guarded_admission", "scope_refinement")
    )


def _warnings(
    *,
    status: HistoricalMarketMovementRiskFilterRuntimeActivationStatus,
    blockers: Sequence[str],
) -> list[str]:
    if not blockers:
        return ["market_movement_runtime_activation:staged_activation_ready"]
    return [
        *[
            f"market_movement_runtime_activation:failed_check:{blocker}"
            for blocker in blockers
        ],
        f"market_movement_runtime_activation:{status}",
    ]


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
    enabled: bool = True,
) -> HistoricalMarketMovementRiskFilterRuntimeActivationCheck:
    if not enabled:
        return HistoricalMarketMovementRiskFilterRuntimeActivationCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return HistoricalMarketMovementRiskFilterRuntimeActivationCheck(
        name=name,
        status="passed" if actual == expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _equality_check(
    *,
    name: str,
    actual: str,
    expected: str,
    detail: str,
    enabled: bool = True,
) -> HistoricalMarketMovementRiskFilterRuntimeActivationCheck:
    if not enabled:
        return HistoricalMarketMovementRiskFilterRuntimeActivationCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return HistoricalMarketMovementRiskFilterRuntimeActivationCheck(
        name=name,
        status="passed" if actual == expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: int | float,
    threshold: int | float,
    detail: str,
) -> HistoricalMarketMovementRiskFilterRuntimeActivationCheck:
    return HistoricalMarketMovementRiskFilterRuntimeActivationCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    *,
    name: str,
    actual: int | float,
    threshold: int | float,
    detail: str,
) -> HistoricalMarketMovementRiskFilterRuntimeActivationCheck:
    return HistoricalMarketMovementRiskFilterRuntimeActivationCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_minimum_check(
    *,
    name: str,
    actual: int | float | None,
    threshold: int | float,
    detail: str,
) -> HistoricalMarketMovementRiskFilterRuntimeActivationCheck:
    if actual is None:
        return HistoricalMarketMovementRiskFilterRuntimeActivationCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return _minimum_check(
        name=name,
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_maximum_check(
    *,
    name: str,
    actual: int | float | None,
    threshold: int | float,
    detail: str,
) -> HistoricalMarketMovementRiskFilterRuntimeActivationCheck:
    if actual is None:
        return HistoricalMarketMovementRiskFilterRuntimeActivationCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return _maximum_check(
        name=name,
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _rule_list(profile: Mapping[str, object]) -> list[Mapping[str, object]]:
    rules = _mapping_list(profile.get("market_movement_risk_filter_rules"))
    return rules or _mapping_list(profile.get("rules"))


def _profile_version(profile: Mapping[str, object]) -> str:
    return _string(profile.get("profile_version")) or "unknown"


def _load_json(path: Path | str) -> dict[str, object]:
    payload = loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _object_mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
        if isinstance(payload, Mapping):
            return dict(payload)
    return {}


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, str)]


def _unique(values: Iterable[str | None]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _bool(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        return float(value)
    return None


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalMarketMovementRiskFilterRuntimeActivationCheck],
    staged_profile: Mapping[str, object],
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "staged_profile": staged_profile,
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_market_movement_risk_filter_runtime_activation:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run a staged-only activation preflight for market-movement "
            "risk-filter runtime rules."
        )
    )
    parser.add_argument("--rule-profile", type=Path, required=True)
    parser.add_argument("--runtime-replay-report", type=Path, required=True)
    parser.add_argument("--suite-quality-gate-report", type=Path, required=True)
    parser.add_argument("--report-output-path", type=Path)
    parser.add_argument("--staged-profile-output-path", type=Path)
    parser.add_argument(
        "--staged-profile-version",
        default="v3_2_market_movement_risk_filter_runtime_staged_activation_candidate",
    )
    parser.add_argument("--min-rule-count", type=int, default=1)
    parser.add_argument("--min-selected-rule-count", type=int, default=1)
    parser.add_argument("--max-selected-rule-count", type=int, default=1)
    parser.add_argument("--min-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--min-adjusted-prediction-count", type=int, default=1)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--allow-suite-gate-not-passed", action="store_true")
    parser.add_argument("--allow-missing-suite-runtime-evidence", action="store_true")
    parser.add_argument("--allow-runtime-replay-not-allowed", action="store_true")
    parser.add_argument("--allow-runtime-replay-non-passed-status", action="store_true")
    parser.add_argument("--allow-profile-not-runtime-shadow-allowed", action="store_true")
    parser.add_argument("--allow-profile-not-holdout-allowed", action="store_true")
    parser.add_argument("--allow-rule-holdout-disabled", action="store_true")
    parser.add_argument("--allow-rule-shadow-replay-disabled", action="store_true")
    parser.add_argument("--allow-rule-production-enabled", action="store_true")
    parser.add_argument("--allow-incomplete-rule-source-chain", action="store_true")
    parser.add_argument("--allow-missing-rollback-conditions", action="store_true")
    parser.add_argument("--allow-default-path-change", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalMarketMovementRiskFilterRuntimeActivationOptions:
    return HistoricalMarketMovementRiskFilterRuntimeActivationOptions(
        staged_profile_version=args.staged_profile_version,
        min_rule_count=args.min_rule_count,
        min_selected_rule_count=args.min_selected_rule_count,
        max_selected_rule_count=args.max_selected_rule_count,
        min_adjusted_fixture_count=args.min_adjusted_fixture_count,
        min_adjusted_prediction_count=args.min_adjusted_prediction_count,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        require_suite_gate_passed=not args.allow_suite_gate_not_passed,
        require_suite_gate_runtime_evidence=(
            not args.allow_missing_suite_runtime_evidence
        ),
        require_runtime_replay_allowed=not args.allow_runtime_replay_not_allowed,
        require_runtime_replay_passed_status=(
            not args.allow_runtime_replay_non_passed_status
        ),
        require_profile_runtime_shadow_allowed=(
            not args.allow_profile_not_runtime_shadow_allowed
        ),
        require_profile_holdout_allowed=not args.allow_profile_not_holdout_allowed,
        require_rules_holdout_enabled=not args.allow_rule_holdout_disabled,
        require_rules_shadow_replay_enabled=not args.allow_rule_shadow_replay_disabled,
        require_rules_production_disabled=not args.allow_rule_production_enabled,
        require_rule_source_chain_complete=(
            not args.allow_incomplete_rule_source_chain
        ),
        require_rule_rollback_conditions=not args.allow_missing_rollback_conditions,
        require_no_default_path_change=not args.allow_default_path_change,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
    )


if __name__ == "__main__":
    main()
