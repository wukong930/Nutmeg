from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalOptimizerProfile,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_market_movement_segment_gate import (
    HistoricalMarketMovementSegmentCandidate,
    HistoricalMarketMovementSegmentGateOptions,
    HistoricalMarketMovementSegmentGateReport,
    build_historical_market_movement_segment_gate_report,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalMarketMovementRiskFilterRuntimeReplayStatus = Literal[
    "runtime_shadow_replay_passed",
    "holdout_replay_passed",
    "shadow_replay_failed",
    "disabled",
    "no_rules",
    "blocked",
]
type HistoricalMarketMovementRiskFilterRuntimeReplayCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]


class MarketMovementRiskFilterRuntimeRule(BaseModel):
    rule_id: str
    proposed_profile_version: str | None = None
    proposed_production_enabled: bool = False
    holdout_candidate_enabled: bool = False
    shadow_replay_enabled: bool = False
    production_recommendation_changed: bool = False
    segment_group_keys: list[str] = Field(default_factory=list)
    movement_weight: float = Field(default=0.50, ge=0.0, le=2.0)
    max_probability_shift: float = Field(default=0.08, ge=0.0, le=0.35)
    source_guarded_admission_report_key: str | None = None
    source_segment_gate_report_key: str | None = None
    source_guarded_segment_gate_report_key: str | None = None
    source_candidate_id: str | None = None
    constraints_json: dict[str, object] = Field(default_factory=dict)
    evidence_json: dict[str, object] = Field(default_factory=dict)
    source_report_keys: dict[str, str] = Field(default_factory=dict)
    rollback_conditions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MarketMovementRiskFilterRuntimeRuleSet(BaseModel):
    profile_version: str = "unknown"
    calculation_basis: str = (
        "market_movement_risk_filter_runtime_rule_loader_v3_2"
    )
    status: str | None = None
    runtime_shadow_proposal_allowed: bool = False
    runtime_profile_proposal_allowed: bool = False
    holdout_candidate_allowed: bool = False
    shadow_replay_enabled: bool = False
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    rules: list[MarketMovementRiskFilterRuntimeRule] = Field(default_factory=list)
    source_json_path: str | None = None
    notes: list[str] = Field(default_factory=list)


class HistoricalMarketMovementRiskFilterRuntimeReplayOptions(BaseModel):
    enable_shadow_replay: bool = False
    rule_ids: tuple[str, ...] = ()
    min_candidate_count: int = Field(default=1, ge=0)
    min_accepted_count: int = Field(default=1, ge=0)
    min_adjusted_fixture_count: int = Field(default=1, ge=0)
    min_adjusted_prediction_count: int = Field(default=1, ge=0)
    min_final_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    require_profile_runtime_shadow_allowed: bool = False
    require_holdout_candidate_enabled: bool = True
    require_rule_shadow_replay_enabled: bool = True
    require_proposed_production_disabled: bool = True
    require_production_recommendation_unchanged: bool = True
    require_no_public_response_change: bool = True
    max_selected_rule_count: int = Field(default=1, ge=1)
    gate_id_suffix: str = "runtime-shadow-replay"
    override_pass_types: tuple[str, ...] = ()
    override_modes: tuple[RecommendationMode, ...] = ()
    override_strategy: RecommendationStrategy | None = None
    override_unit_stake: float | None = Field(default=None, gt=0.0)
    override_max_budget: float | None = Field(default=None, gt=0.0)
    override_optimizer_profile: HistoricalOptimizerProfile | None = None


class HistoricalMarketMovementRiskFilterRuntimeReplayCheck(BaseModel):
    name: str
    status: HistoricalMarketMovementRiskFilterRuntimeReplayCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalMarketMovementRiskFilterRuntimeReplayReport(BaseModel):
    report_key: str
    status: HistoricalMarketMovementRiskFilterRuntimeReplayStatus
    runtime_shadow_replay_allowed: bool
    holdout_replay_allowed: bool
    source_rule_profile_version: str
    rule_count: int = Field(ge=0)
    selected_rule_count: int = Field(ge=0)
    selected_rule_id: str | None = None
    segment_gate_report_key: str | None = None
    selected_candidate_id: str | None = None
    selected_segment_group_key: str | None = None
    candidate_count: int = Field(default=0, ge=0)
    accepted_count: int = Field(default=0, ge=0)
    adjusted_fixture_count: int = Field(default=0, ge=0)
    adjusted_prediction_count: int = Field(default=0, ge=0)
    final_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    checks: list[HistoricalMarketMovementRiskFilterRuntimeReplayCheck] = Field(
        default_factory=list
    )
    rule_set_json: dict[str, object] = Field(default_factory=dict)
    selected_rule_json: dict[str, object] | None = None
    segment_gate_report_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def load_market_movement_risk_filter_runtime_rule_set(
    path: Path | str,
    *,
    enable_shadow_replay: bool = False,
) -> MarketMovementRiskFilterRuntimeRuleSet:
    payload = loads(Path(path).read_text(encoding="utf-8"))
    profile_json = _extract_profile_json(payload)
    rules = [
        MarketMovementRiskFilterRuntimeRule.model_validate(rule)
        for rule in _mapping_list(profile_json.get("market_movement_risk_filter_rules"))
    ]
    if not rules:
        rules = [
            MarketMovementRiskFilterRuntimeRule.model_validate(rule)
            for rule in _mapping_list(profile_json.get("rules"))
        ]
    return MarketMovementRiskFilterRuntimeRuleSet(
        profile_version=(
            _string(profile_json.get("profile_version"))
            or _string(profile_json.get("proposed_profile_version"))
            or "unknown"
        ),
        calculation_basis=(
            _string(profile_json.get("calculation_basis"))
            or "market_movement_risk_filter_runtime_rule_loader_v3_2"
        ),
        status=_string(profile_json.get("status")),
        runtime_shadow_proposal_allowed=_bool(
            profile_json.get("runtime_shadow_proposal_allowed")
        ),
        runtime_profile_proposal_allowed=_bool(
            profile_json.get("runtime_profile_proposal_allowed")
        ),
        holdout_candidate_allowed=_bool(profile_json.get("holdout_candidate_allowed")),
        shadow_replay_enabled=enable_shadow_replay,
        production_recommendation_changed=_bool(
            profile_json.get("production_recommendation_changed")
        )
        or _bool(profile_json.get("default_recommendation_path_changed")),
        public_response_changed=_bool(profile_json.get("public_response_changed")),
        rules=rules,
        source_json_path=str(path),
        notes=_string_list(profile_json.get("notes")),
    )


def build_historical_market_movement_risk_filter_runtime_replay_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    rule_set: MarketMovementRiskFilterRuntimeRuleSet,
    options: HistoricalMarketMovementRiskFilterRuntimeReplayOptions | None = None,
) -> HistoricalMarketMovementRiskFilterRuntimeReplayReport:
    resolved_options = options or HistoricalMarketMovementRiskFilterRuntimeReplayOptions()
    resolved_rule_set = rule_set.model_copy(
        update={"shadow_replay_enabled": resolved_options.enable_shadow_replay}
    )
    selected_rules = _selected_rules(resolved_rule_set, options=resolved_options)
    warnings: list[str] = []
    if not resolved_options.enable_shadow_replay:
        warnings.append(
            "market_movement_risk_filter_runtime_replay:disabled_by_feature_flag"
        )
        return _empty_report(
            resolved_rule_set,
            selected_rules=selected_rules,
            checks=[],
            status="disabled",
            warnings=warnings,
            options=resolved_options,
        )
    if not selected_rules:
        warnings.append("market_movement_risk_filter_runtime_replay:no_selected_rules")
        return _empty_report(
            resolved_rule_set,
            selected_rules=selected_rules,
            checks=[],
            status="no_rules",
            warnings=warnings,
            options=resolved_options,
        )
    if len(selected_rules) > resolved_options.max_selected_rule_count:
        checks = [
            _maximum_check(
                "selected_rule_count",
                len(selected_rules),
                resolved_options.max_selected_rule_count,
                detail="runtime replay currently supports a bounded rule set",
            )
        ]
        warnings.append(
            "market_movement_risk_filter_runtime_replay:too_many_selected_rules"
        )
        return _empty_report(
            resolved_rule_set,
            selected_rules=selected_rules,
            checks=checks,
            status="blocked",
            warnings=warnings,
            options=resolved_options,
        )
    selected_rule = selected_rules[0]
    segment_gate_report = build_historical_market_movement_segment_gate_report(
        historical_slices,
        options=_segment_gate_options(selected_rule, resolved_options),
    )
    candidate = segment_gate_report.best_candidate
    checks = _checks(
        resolved_rule_set,
        selected_rule,
        segment_gate_report=segment_gate_report,
        candidate=candidate,
        selected_rule_count=len(selected_rules),
        options=resolved_options,
    )
    runtime_allowed = all(check.status == "passed" for check in checks)
    holdout_allowed = _holdout_checks_passed(checks)
    status = _status(
        runtime_allowed=runtime_allowed,
        holdout_allowed=holdout_allowed,
    )
    warnings.extend(_warnings(status=status, checks=checks))
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_risk_filter_runtime_replay_v3_2"
        ),
        "status": status,
        "runtime_shadow_replay_allowed": runtime_allowed,
        "holdout_replay_allowed": holdout_allowed,
        "source_rule_profile_version": resolved_rule_set.profile_version,
        "source_rule_profile_status": resolved_rule_set.status,
        "rule_count": len(resolved_rule_set.rules),
        "selected_rule_count": len(selected_rules),
        "selected_rule_id": selected_rule.rule_id,
        "segment_gate_report_key": segment_gate_report.report_key,
        "selected_candidate_id": candidate.candidate_id if candidate else None,
        "selected_segment_group_key": (
            candidate.segment_group_key if candidate else None
        ),
        "candidate_count": segment_gate_report.candidate_count,
        "accepted_count": segment_gate_report.accepted_count,
        "adjusted_fixture_count": candidate.adjusted_fixture_count if candidate else 0,
        "adjusted_prediction_count": (
            candidate.adjusted_prediction_count if candidate else 0
        ),
        "final_hit_rate_delta": _candidate_delta(candidate, "final_hit_rate_delta"),
        "roi_delta": _candidate_delta(candidate, "roi_delta"),
        "profit_loss_delta": _candidate_delta(candidate, "profit_loss_delta"),
        "brier_score_delta": _candidate_delta(candidate, "brier_score_delta"),
        "log_loss_delta": _candidate_delta(candidate, "log_loss_delta"),
        "mean_calibration_error_delta": _candidate_delta(
            candidate,
            "mean_calibration_error_delta",
        ),
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(
        summary,
        checks,
        rule_set=resolved_rule_set,
        selected_rule=selected_rule,
        segment_gate_report=segment_gate_report,
    )
    return HistoricalMarketMovementRiskFilterRuntimeReplayReport(
        report_key=report_key,
        status=status,
        runtime_shadow_replay_allowed=runtime_allowed,
        holdout_replay_allowed=holdout_allowed,
        source_rule_profile_version=resolved_rule_set.profile_version,
        rule_count=len(resolved_rule_set.rules),
        selected_rule_count=len(selected_rules),
        selected_rule_id=selected_rule.rule_id,
        segment_gate_report_key=segment_gate_report.report_key,
        selected_candidate_id=candidate.candidate_id if candidate else None,
        selected_segment_group_key=candidate.segment_group_key if candidate else None,
        candidate_count=segment_gate_report.candidate_count,
        accepted_count=segment_gate_report.accepted_count,
        adjusted_fixture_count=candidate.adjusted_fixture_count if candidate else 0,
        adjusted_prediction_count=(
            candidate.adjusted_prediction_count if candidate else 0
        ),
        final_hit_rate_delta=_candidate_delta(candidate, "final_hit_rate_delta"),
        roi_delta=_candidate_delta(candidate, "roi_delta"),
        profit_loss_delta=_candidate_delta(candidate, "profit_loss_delta"),
        brier_score_delta=_candidate_delta(candidate, "brier_score_delta"),
        log_loss_delta=_candidate_delta(candidate, "log_loss_delta"),
        mean_calibration_error_delta=_candidate_delta(
            candidate,
            "mean_calibration_error_delta",
        ),
        production_recommendation_changed=False,
        public_response_changed=False,
        checks=checks,
        rule_set_json=resolved_rule_set.model_dump(mode="json"),
        selected_rule_json=selected_rule.model_dump(mode="json"),
        segment_gate_report_json=segment_gate_report.summary_json,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_market_movement_risk_filter_runtime_replay_report(
        loaded_slices.slices,
        rule_set=load_market_movement_risk_filter_runtime_rule_set(
            args.rule_profile,
            enable_shadow_replay=args.enable_shadow_replay,
        ),
        options=_options_from_args(args),
    )
    if loaded_slices.manifest_result is not None:
        report.summary_json["suite_manifest"] = _manifest_summary(
            loaded_slices.manifest_result
        )
    if loaded_slices.warnings:
        report.warnings.extend(loaded_slices.warnings)
        report.summary_json["manifest_warnings"] = loaded_slices.warnings
    output = dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(f"{output}\n", encoding="utf-8")
    print(output)
    if not report.runtime_shadow_replay_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _selected_rules(
    rule_set: MarketMovementRiskFilterRuntimeRuleSet,
    *,
    options: HistoricalMarketMovementRiskFilterRuntimeReplayOptions,
) -> list[MarketMovementRiskFilterRuntimeRule]:
    rule_ids = set(options.rule_ids)
    rules = [
        rule
        for rule in rule_set.rules
        if not rule_ids or rule.rule_id in rule_ids
    ]
    return sorted(rules, key=lambda rule: rule.rule_id)


def _segment_gate_options(
    rule: MarketMovementRiskFilterRuntimeRule,
    options: HistoricalMarketMovementRiskFilterRuntimeReplayOptions,
) -> HistoricalMarketMovementSegmentGateOptions:
    constraints = _mapping(rule.constraints_json.get("segment_gate_options")) or {}
    segment_options = (
        HistoricalMarketMovementSegmentGateOptions.model_validate(constraints)
        if constraints
        else HistoricalMarketMovementSegmentGateOptions()
    )
    backtest_options = segment_options.backtest_options
    backtest_updates: dict[str, object] = {}
    if options.override_pass_types:
        backtest_updates["pass_types"] = options.override_pass_types
    if options.override_modes:
        backtest_updates["modes"] = options.override_modes
    if options.override_strategy is not None:
        backtest_updates["strategy"] = options.override_strategy
    if options.override_unit_stake is not None:
        backtest_updates["unit_stake"] = options.override_unit_stake
    if options.override_max_budget is not None:
        backtest_updates["max_budget"] = options.override_max_budget
    if options.override_optimizer_profile is not None:
        backtest_updates["optimizer_profile"] = options.override_optimizer_profile
    if backtest_updates:
        backtest_options = backtest_options.model_copy(update=backtest_updates)
    return segment_options.model_copy(
        update={
            "gate_id": f"{segment_options.gate_id}:{options.gate_id_suffix}",
            "segment_group_keys": tuple(rule.segment_group_keys),
            "movement_weight": rule.movement_weight,
            "max_probability_shift": rule.max_probability_shift,
            "backtest_options": backtest_options,
        }
    )


def _checks(
    rule_set: MarketMovementRiskFilterRuntimeRuleSet,
    selected_rule: MarketMovementRiskFilterRuntimeRule,
    *,
    segment_gate_report: HistoricalMarketMovementSegmentGateReport,
    candidate: HistoricalMarketMovementSegmentCandidate | None,
    selected_rule_count: int,
    options: HistoricalMarketMovementRiskFilterRuntimeReplayOptions,
) -> list[HistoricalMarketMovementRiskFilterRuntimeReplayCheck]:
    return [
        _boolean_check(
            "shadow_replay_enabled",
            options.enable_shadow_replay,
            expected=True,
            detail="shadow replay must be explicitly enabled",
        ),
        _maximum_check(
            "selected_rule_count",
            selected_rule_count,
            options.max_selected_rule_count,
            detail="runtime replay currently supports a bounded rule set",
        ),
        _boolean_check(
            "profile_runtime_shadow_allowed",
            rule_set.runtime_shadow_proposal_allowed
            or rule_set.runtime_profile_proposal_allowed,
            expected=True,
            enabled=options.require_profile_runtime_shadow_allowed,
            detail="source profile must already be shadow runtime proposal allowed",
        ),
        _boolean_check(
            "rule_holdout_candidate_enabled",
            selected_rule.holdout_candidate_enabled,
            expected=True,
            enabled=options.require_holdout_candidate_enabled,
            detail="selected rule must be enabled for holdout replay",
        ),
        _boolean_check(
            "rule_shadow_replay_enabled",
            selected_rule.shadow_replay_enabled,
            expected=True,
            enabled=options.require_rule_shadow_replay_enabled,
            detail="selected rule must explicitly allow shadow replay",
        ),
        _boolean_check(
            "proposed_production_disabled",
            not selected_rule.proposed_production_enabled,
            expected=True,
            enabled=options.require_proposed_production_disabled,
            detail="risk-filter runtime replay must not propose production enablement",
        ),
        _boolean_check(
            "production_recommendation_unchanged",
            not rule_set.production_recommendation_changed
            and not selected_rule.production_recommendation_changed,
            expected=True,
            enabled=options.require_production_recommendation_unchanged,
            detail="runtime replay must not change production recommendations",
        ),
        _boolean_check(
            "public_response_unchanged",
            not rule_set.public_response_changed,
            expected=True,
            enabled=options.require_no_public_response_change,
            detail="runtime replay must not change the public response",
        ),
        _minimum_check(
            "candidate_count",
            segment_gate_report.candidate_count,
            options.min_candidate_count,
            detail="runtime replay should evaluate enough segment candidates",
        ),
        _minimum_check(
            "accepted_count",
            segment_gate_report.accepted_count,
            options.min_accepted_count,
            detail="runtime replay should accept the selected segment",
        ),
        _boolean_check(
            "selected_segment_replayed",
            candidate is not None
            and candidate.segment_group_key in set(selected_rule.segment_group_keys),
            expected=True,
            detail="runtime replay should evaluate the selected rule segment",
        ),
        _minimum_check(
            "adjusted_fixture_count",
            candidate.adjusted_fixture_count if candidate is not None else 0,
            options.min_adjusted_fixture_count,
            detail="runtime replay should adjust enough fixtures",
        ),
        _minimum_check(
            "adjusted_prediction_count",
            candidate.adjusted_prediction_count if candidate is not None else 0,
            options.min_adjusted_prediction_count,
            detail="runtime replay should adjust enough predictions",
        ),
        _minimum_optional_check(
            "final_hit_rate_delta",
            _candidate_delta(candidate, "final_hit_rate_delta"),
            options.min_final_hit_rate_delta,
            detail="runtime replay final-answer hit rate should not regress",
        ),
        _minimum_optional_check(
            "roi_delta",
            _candidate_delta(candidate, "roi_delta"),
            options.min_roi_delta,
            detail="runtime replay ROI should not regress",
        ),
        _minimum_optional_check(
            "profit_loss_delta",
            _candidate_delta(candidate, "profit_loss_delta"),
            options.min_profit_loss_delta,
            detail="runtime replay profit/loss should not regress",
        ),
        _maximum_optional_check(
            "brier_score_delta",
            _candidate_delta(candidate, "brier_score_delta"),
            options.max_brier_score_delta,
            detail="runtime replay Brier score should not regress",
        ),
        _maximum_optional_check(
            "log_loss_delta",
            _candidate_delta(candidate, "log_loss_delta"),
            options.max_log_loss_delta,
            detail="runtime replay log loss should not regress",
        ),
        _maximum_optional_check(
            "mean_calibration_error_delta",
            _candidate_delta(candidate, "mean_calibration_error_delta"),
            options.max_mean_calibration_error_delta,
            detail="runtime replay calibration error should not regress",
        ),
    ]


def _empty_report(
    rule_set: MarketMovementRiskFilterRuntimeRuleSet,
    *,
    selected_rules: Sequence[MarketMovementRiskFilterRuntimeRule],
    checks: Sequence[HistoricalMarketMovementRiskFilterRuntimeReplayCheck],
    status: HistoricalMarketMovementRiskFilterRuntimeReplayStatus,
    warnings: Sequence[str],
    options: HistoricalMarketMovementRiskFilterRuntimeReplayOptions,
) -> HistoricalMarketMovementRiskFilterRuntimeReplayReport:
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_risk_filter_runtime_replay_v3_2"
        ),
        "status": status,
        "runtime_shadow_replay_allowed": False,
        "holdout_replay_allowed": False,
        "source_rule_profile_version": rule_set.profile_version,
        "source_rule_profile_status": rule_set.status,
        "rule_count": len(rule_set.rules),
        "selected_rule_count": len(selected_rules),
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "options": options.model_dump(mode="json"),
        "warnings": list(warnings),
    }
    report_key = _report_key(
        summary,
        checks,
        rule_set=rule_set,
        selected_rule=selected_rules[0] if selected_rules else None,
        segment_gate_report=None,
    )
    return HistoricalMarketMovementRiskFilterRuntimeReplayReport(
        report_key=report_key,
        status=status,
        runtime_shadow_replay_allowed=False,
        holdout_replay_allowed=False,
        source_rule_profile_version=rule_set.profile_version,
        rule_count=len(rule_set.rules),
        selected_rule_count=len(selected_rules),
        selected_rule_id=selected_rules[0].rule_id if selected_rules else None,
        production_recommendation_changed=False,
        public_response_changed=False,
        checks=list(checks),
        rule_set_json=rule_set.model_dump(mode="json"),
        selected_rule_json=(
            selected_rules[0].model_dump(mode="json") if selected_rules else None
        ),
        warnings=list(warnings),
        summary_json={**summary, "report_key": report_key},
    )


def _status(
    *,
    runtime_allowed: bool,
    holdout_allowed: bool,
) -> HistoricalMarketMovementRiskFilterRuntimeReplayStatus:
    if runtime_allowed:
        return "runtime_shadow_replay_passed"
    if holdout_allowed:
        return "holdout_replay_passed"
    return "shadow_replay_failed"


def _holdout_checks_passed(
    checks: Sequence[HistoricalMarketMovementRiskFilterRuntimeReplayCheck],
) -> bool:
    blocking_names = {
        "shadow_replay_enabled",
        "rule_holdout_candidate_enabled",
        "rule_shadow_replay_enabled",
        "proposed_production_disabled",
        "production_recommendation_unchanged",
        "public_response_unchanged",
        "accepted_count",
        "selected_segment_replayed",
        "final_hit_rate_delta",
        "roi_delta",
        "profit_loss_delta",
        "brier_score_delta",
        "log_loss_delta",
        "mean_calibration_error_delta",
    }
    return all(
        check.status == "passed"
        for check in checks
        if check.name in blocking_names
    )


def _warnings(
    *,
    status: HistoricalMarketMovementRiskFilterRuntimeReplayStatus,
    checks: Sequence[HistoricalMarketMovementRiskFilterRuntimeReplayCheck],
) -> list[str]:
    warnings = [
        f"market_movement_risk_filter_runtime_replay:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    if status == "runtime_shadow_replay_passed":
        warnings.append("market_movement_risk_filter_runtime_replay:passed")
    elif status == "holdout_replay_passed":
        warnings.append("market_movement_risk_filter_runtime_replay:holdout_only")
    else:
        warnings.append("market_movement_risk_filter_runtime_replay:failed")
    return warnings


def _boolean_check(
    name: str,
    actual: bool,
    *,
    expected: bool,
    detail: str,
    enabled: bool = True,
) -> HistoricalMarketMovementRiskFilterRuntimeReplayCheck:
    if not enabled:
        return HistoricalMarketMovementRiskFilterRuntimeReplayCheck(
            name=name,
            status="skipped",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return HistoricalMarketMovementRiskFilterRuntimeReplayCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _minimum_check(
    name: str,
    actual: int,
    threshold: int,
    *,
    detail: str,
) -> HistoricalMarketMovementRiskFilterRuntimeReplayCheck:
    return HistoricalMarketMovementRiskFilterRuntimeReplayCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    name: str,
    actual: int,
    threshold: int,
    *,
    detail: str,
) -> HistoricalMarketMovementRiskFilterRuntimeReplayCheck:
    return HistoricalMarketMovementRiskFilterRuntimeReplayCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _minimum_optional_check(
    name: str,
    actual: float | None,
    threshold: float,
    *,
    detail: str,
) -> HistoricalMarketMovementRiskFilterRuntimeReplayCheck:
    return HistoricalMarketMovementRiskFilterRuntimeReplayCheck(
        name=name,
        status="passed" if actual is not None and actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_optional_check(
    name: str,
    actual: float | None,
    threshold: float,
    *,
    detail: str,
) -> HistoricalMarketMovementRiskFilterRuntimeReplayCheck:
    return HistoricalMarketMovementRiskFilterRuntimeReplayCheck(
        name=name,
        status="passed" if actual is not None and actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _candidate_delta(
    candidate: HistoricalMarketMovementSegmentCandidate | None,
    key: str,
) -> float | None:
    if candidate is None:
        return None
    value = candidate.final_answer_deltas_json.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Replay a shadow market-movement risk-filter runtime profile against "
            "the historical final-answer path."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--rule-profile", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--enable-shadow-replay", action="store_true")
    parser.add_argument("--rule-ids", default="")
    parser.add_argument("--min-candidate-count", type=int, default=1)
    parser.add_argument("--min-accepted-count", type=int, default=1)
    parser.add_argument("--min-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--min-adjusted-prediction-count", type=int, default=1)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--require-profile-runtime-shadow-allowed", action="store_true")
    parser.add_argument("--allow-rule-holdout-disabled", action="store_true")
    parser.add_argument("--allow-rule-shadow-replay-disabled", action="store_true")
    parser.add_argument("--allow-proposed-production-enabled", action="store_true")
    parser.add_argument("--allow-production-recommendation-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--max-selected-rule-count", type=int, default=1)
    parser.add_argument("--gate-id-suffix", default="runtime-shadow-replay")
    parser.add_argument("--pass-types", default="")
    parser.add_argument("--modes", default="")
    parser.add_argument(
        "--strategy",
        choices=[
            "accuracy_first",
            "value_first",
            "upset_protection",
            "budget_constrained",
        ],
    )
    parser.add_argument("--unit-stake", type=float)
    parser.add_argument("--max-budget", type=float)
    parser.add_argument("--optimizer-profile", choices=["heuristic", "solver"])
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalMarketMovementRiskFilterRuntimeReplayOptions:
    return HistoricalMarketMovementRiskFilterRuntimeReplayOptions(
        enable_shadow_replay=args.enable_shadow_replay,
        rule_ids=tuple(_csv(args.rule_ids)),
        min_candidate_count=args.min_candidate_count,
        min_accepted_count=args.min_accepted_count,
        min_adjusted_fixture_count=args.min_adjusted_fixture_count,
        min_adjusted_prediction_count=args.min_adjusted_prediction_count,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        require_profile_runtime_shadow_allowed=(
            args.require_profile_runtime_shadow_allowed
        ),
        require_holdout_candidate_enabled=not args.allow_rule_holdout_disabled,
        require_rule_shadow_replay_enabled=not args.allow_rule_shadow_replay_disabled,
        require_proposed_production_disabled=(
            not args.allow_proposed_production_enabled
        ),
        require_production_recommendation_unchanged=(
            not args.allow_production_recommendation_change
        ),
        require_no_public_response_change=not args.allow_public_response_change,
        max_selected_rule_count=args.max_selected_rule_count,
        gate_id_suffix=args.gate_id_suffix,
        override_pass_types=tuple(_csv(args.pass_types)),
        override_modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
        override_strategy=(
            cast(RecommendationStrategy, args.strategy)
            if args.strategy is not None
            else None
        ),
        override_unit_stake=args.unit_stake,
        override_max_budget=args.max_budget,
        override_optimizer_profile=(
            cast(HistoricalOptimizerProfile, args.optimizer_profile)
            if args.optimizer_profile is not None
            else None
        ),
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    historical_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = []
    resolved_slice_paths: list[Path] = []
    if args.suite_manifest is not None:
        manifest_result = load_historical_recommendation_suite_manifest_bundle(
            args.suite_manifest
        )
        historical_slices = [*manifest_result.slices, *historical_slices]
        resolved_slice_paths.extend(manifest_result.resolved_slice_paths)
        warnings.extend(manifest_result.warnings)
    resolved_slice_paths.extend(args.slice_paths)
    return _LoadedHistoricalSlices(
        slices=historical_slices,
        resolved_slice_paths=resolved_slice_paths,
        manifest_result=manifest_result,
        warnings=warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "enabled_slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }


def _extract_profile_json(payload: Mapping[str, object]) -> Mapping[str, object]:
    profile = payload.get("proposal_profile_set_json")
    if isinstance(profile, Mapping):
        return profile
    return payload


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _bool(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalMarketMovementRiskFilterRuntimeReplayCheck],
    *,
    rule_set: MarketMovementRiskFilterRuntimeRuleSet,
    selected_rule: MarketMovementRiskFilterRuntimeRule | None,
    segment_gate_report: HistoricalMarketMovementSegmentGateReport | None,
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "rule_set": rule_set.model_dump(mode="json"),
        "selected_rule": (
            selected_rule.model_dump(mode="json") if selected_rule is not None else None
        ),
        "segment_gate_report_key": (
            segment_gate_report.report_key if segment_gate_report is not None else None
        ),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_market_movement_risk_filter_runtime_replay:{digest}"
