from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_market_movement_risk_filter_guarded_rolling_admission import (  # noqa: E501
    HistoricalMarketMovementRiskFilterGuardedAdmissionReport,
    load_historical_market_movement_risk_filter_guarded_admission_report,
)

type HistoricalMarketMovementRiskFilterRuntimeProposalStatus = Literal[
    "runtime_shadow_proposal_ready",
    "holdout_only",
    "blocked",
]
type HistoricalMarketMovementRiskFilterRuntimeProposalCheckStatus = Literal[
    "passed",
    "failed",
]

DEFAULT_MARKET_MOVEMENT_RISK_FILTER_RUNTIME_PROPOSAL_ID = (
    "market_movement_risk_filter_runtime_shadow_candidate_v1"
)
DEFAULT_MARKET_MOVEMENT_RISK_FILTER_RUNTIME_PROFILE_VERSION = (
    "v3_2_market_movement_risk_filter_runtime_shadow_candidate"
)


class HistoricalMarketMovementRiskFilterRuntimeProposalOptions(BaseModel):
    proposal_id: str = DEFAULT_MARKET_MOVEMENT_RISK_FILTER_RUNTIME_PROPOSAL_ID
    proposed_profile_version: str = (
        DEFAULT_MARKET_MOVEMENT_RISK_FILTER_RUNTIME_PROFILE_VERSION
    )
    source_segment_group_key: str | None = None
    min_adjusted_fixture_count: int = Field(default=1, ge=0)
    min_adjusted_prediction_count: int = Field(default=1, ge=0)
    min_active_fold_count: int = Field(default=1, ge=0)
    max_failed_fold_count: int = Field(default=0, ge=0)
    min_final_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    require_guarded_admission_accepted: bool = True
    require_guarded_risk_filter_allowed: bool = True
    require_production_recommendation_unchanged: bool = True
    require_overall_best_accepted: bool = True
    require_selected_segment_not_globally_blocked: bool = True


class HistoricalMarketMovementRiskFilterRuntimeProposalCheck(BaseModel):
    name: str
    status: HistoricalMarketMovementRiskFilterRuntimeProposalCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalMarketMovementRiskFilterRuntimeRuleProposal(BaseModel):
    rule_id: str
    proposed_profile_version: str
    proposed_production_enabled: bool = False
    holdout_candidate_enabled: bool
    shadow_replay_enabled: bool
    production_recommendation_changed: bool = False
    segment_group_keys: list[str] = Field(default_factory=list)
    movement_weight: float = Field(ge=0.0, le=2.0)
    max_probability_shift: float = Field(ge=0.0, le=0.35)
    source_guarded_admission_report_key: str
    source_segment_gate_report_key: str | None = None
    source_guarded_segment_gate_report_key: str | None = None
    source_candidate_id: str | None = None
    source_report_keys: dict[str, str] = Field(default_factory=dict)
    evidence_json: dict[str, object] = Field(default_factory=dict)
    constraints_json: dict[str, object] = Field(default_factory=dict)
    rollback_conditions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HistoricalMarketMovementRiskFilterRuntimeProposalReport(BaseModel):
    report_key: str
    status: HistoricalMarketMovementRiskFilterRuntimeProposalStatus
    runtime_shadow_proposal_allowed: bool
    holdout_candidate_allowed: bool
    proposal_count: int = Field(ge=0)
    source_guarded_admission_report_key: str
    source_guarded_admission_status: str
    source_segment_group_key: str | None = None
    checks: list[HistoricalMarketMovementRiskFilterRuntimeProposalCheck] = Field(
        default_factory=list
    )
    proposal_rule: HistoricalMarketMovementRiskFilterRuntimeRuleProposal | None = None
    proposal_profile_set_json: dict[str, object] = Field(default_factory=dict)
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_market_movement_risk_filter_runtime_proposal_report(
    guarded_admission_report: HistoricalMarketMovementRiskFilterGuardedAdmissionReport,
    *,
    options: HistoricalMarketMovementRiskFilterRuntimeProposalOptions | None = None,
) -> HistoricalMarketMovementRiskFilterRuntimeProposalReport:
    resolved_options = (
        options or HistoricalMarketMovementRiskFilterRuntimeProposalOptions()
    )
    segment_group_key = _source_segment_group_key(
        guarded_admission_report,
        options=resolved_options,
    )
    checks = _checks(
        guarded_admission_report,
        segment_group_key=segment_group_key,
        options=resolved_options,
    )
    runtime_allowed = all(check.status == "passed" for check in checks)
    holdout_allowed = _holdout_checks_passed(checks)
    status = _status(
        runtime_allowed=runtime_allowed,
        holdout_allowed=holdout_allowed,
    )
    proposal_rule = _proposal_rule(
        guarded_admission_report,
        segment_group_key=segment_group_key,
        holdout_allowed=holdout_allowed,
        shadow_replay_allowed=runtime_allowed,
        options=resolved_options,
    )
    proposal_profile_set = _proposal_profile_set_json(
        proposal_rule,
        status=status,
        runtime_allowed=runtime_allowed,
        holdout_allowed=holdout_allowed,
        options=resolved_options,
    )
    warnings = _warnings(status=status, checks=checks)
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_risk_filter_runtime_proposal_v3_2"
        ),
        "status": status,
        "runtime_shadow_proposal_allowed": runtime_allowed,
        "holdout_candidate_allowed": holdout_allowed,
        "proposal_id": resolved_options.proposal_id,
        "proposed_profile_version": resolved_options.proposed_profile_version,
        "source_guarded_admission_report_key": guarded_admission_report.report_key,
        "source_guarded_admission_status": guarded_admission_report.status,
        "source_segment_group_key": segment_group_key,
        "source_guarded_risk_filter_allowed": (
            guarded_admission_report.guarded_risk_filter_allowed
        ),
        "active_fold_count": guarded_admission_report.active_fold_count,
        "failed_fold_count": guarded_admission_report.failed_fold_count,
        "guarded_skipped_fold_count": (
            guarded_admission_report.guarded_skipped_fold_count
        ),
        "adjusted_fixture_count": (
            guarded_admission_report.overall_fold.adjusted_fixture_count
        ),
        "adjusted_prediction_count": (
            guarded_admission_report.overall_fold.adjusted_prediction_count
        ),
        "final_hit_rate_delta": guarded_admission_report.overall_fold.final_hit_rate_delta,
        "roi_delta": guarded_admission_report.overall_fold.roi_delta,
        "profit_loss_delta": guarded_admission_report.overall_fold.profit_loss_delta,
        "brier_score_delta": guarded_admission_report.overall_fold.brier_score_delta,
        "log_loss_delta": guarded_admission_report.overall_fold.log_loss_delta,
        "mean_calibration_error_delta": (
            guarded_admission_report.overall_fold.mean_calibration_error_delta
        ),
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, proposal_rule)
    return HistoricalMarketMovementRiskFilterRuntimeProposalReport(
        report_key=report_key,
        status=status,
        runtime_shadow_proposal_allowed=runtime_allowed,
        holdout_candidate_allowed=holdout_allowed,
        proposal_count=1 if proposal_rule is not None else 0,
        source_guarded_admission_report_key=guarded_admission_report.report_key,
        source_guarded_admission_status=guarded_admission_report.status,
        source_segment_group_key=segment_group_key,
        checks=checks,
        proposal_rule=proposal_rule,
        proposal_profile_set_json=proposal_profile_set,
        production_recommendation_changed=False,
        public_response_changed=False,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_market_movement_risk_filter_runtime_proposal_report(
        load_historical_market_movement_risk_filter_guarded_admission_report(
            args.guarded_admission_report
        ),
        options=_options_from_args(args),
    )
    output = dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(f"{output}\n", encoding="utf-8")
    if args.profile_output_path is not None and report.holdout_candidate_allowed:
        args.profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output_path.write_text(
            f"{dumps(report.proposal_profile_set_json, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
    print(output)
    if not report.runtime_shadow_proposal_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _checks(
    report: HistoricalMarketMovementRiskFilterGuardedAdmissionReport,
    *,
    segment_group_key: str | None,
    options: HistoricalMarketMovementRiskFilterRuntimeProposalOptions,
) -> list[HistoricalMarketMovementRiskFilterRuntimeProposalCheck]:
    overall = report.overall_fold
    return [
        _boolean_check(
            "source_guarded_admission_accepted",
            report.status == "accepted",
            expected=True,
            enabled=options.require_guarded_admission_accepted,
            detail="source guarded admission should be accepted before runtime proposal",
        ),
        _boolean_check(
            "source_guarded_risk_filter_allowed",
            report.guarded_risk_filter_allowed,
            expected=True,
            enabled=options.require_guarded_risk_filter_allowed,
            detail="source guarded admission must allow the risk-filter lane",
        ),
        _boolean_check(
            "production_recommendation_unchanged",
            not report.production_recommendation_changed,
            expected=True,
            enabled=options.require_production_recommendation_unchanged,
            detail="runtime proposal must start from evidence that did not change production",
        ),
        _boolean_check(
            "source_overall_best_segment_present",
            segment_group_key is not None,
            expected=True,
            detail="source report should expose a best segment group",
        ),
        _boolean_check(
            "source_overall_best_decision_accepted",
            overall.best_decision == "accepted",
            expected=True,
            enabled=options.require_overall_best_accepted,
            detail="source best segment should be accepted by guarded admission",
        ),
        _boolean_check(
            "selected_segment_not_globally_blocked",
            segment_group_key not in set(report.global_blocked_segment_group_keys),
            expected=True,
            enabled=options.require_selected_segment_not_globally_blocked,
            detail="runtime proposal must not select a globally blocked segment",
        ),
        _minimum_check(
            "adjusted_fixture_count",
            overall.adjusted_fixture_count,
            options.min_adjusted_fixture_count,
            detail="runtime proposal should have enough adjusted fixture coverage",
        ),
        _minimum_check(
            "adjusted_prediction_count",
            overall.adjusted_prediction_count,
            options.min_adjusted_prediction_count,
            detail="runtime proposal should have enough adjusted prediction coverage",
        ),
        _minimum_check(
            "active_fold_count",
            report.active_fold_count,
            options.min_active_fold_count,
            detail="runtime proposal should have enough active folds",
        ),
        _maximum_check(
            "failed_fold_count",
            report.failed_fold_count,
            options.max_failed_fold_count,
            detail="runtime proposal should not retain failed active folds",
        ),
        _minimum_optional_check(
            "final_hit_rate_delta",
            overall.final_hit_rate_delta,
            options.min_final_hit_rate_delta,
            detail="final-answer hit rate must not regress",
        ),
        _minimum_optional_check(
            "roi_delta",
            overall.roi_delta,
            options.min_roi_delta,
            detail="ROI must not regress",
        ),
        _minimum_optional_check(
            "profit_loss_delta",
            overall.profit_loss_delta,
            options.min_profit_loss_delta,
            detail="profit/loss must not regress",
        ),
        _maximum_optional_check(
            "brier_score_delta",
            overall.brier_score_delta,
            options.max_brier_score_delta,
            detail="Brier score must not regress",
        ),
        _maximum_optional_check(
            "log_loss_delta",
            overall.log_loss_delta,
            options.max_log_loss_delta,
            detail="log loss must not regress",
        ),
        _maximum_optional_check(
            "mean_calibration_error_delta",
            overall.mean_calibration_error_delta,
            options.max_mean_calibration_error_delta,
            detail="calibration error must not regress",
        ),
    ]


def _proposal_rule(
    report: HistoricalMarketMovementRiskFilterGuardedAdmissionReport,
    *,
    segment_group_key: str | None,
    holdout_allowed: bool,
    shadow_replay_allowed: bool,
    options: HistoricalMarketMovementRiskFilterRuntimeProposalOptions,
) -> HistoricalMarketMovementRiskFilterRuntimeRuleProposal | None:
    if segment_group_key is None or not holdout_allowed:
        return None
    segment_gate_options = _segment_gate_options_json(report)
    movement_weight = _float(segment_gate_options.get("movement_weight"), 0.50)
    max_probability_shift = _float(
        segment_gate_options.get("max_probability_shift"),
        0.08,
    )
    guarded_overall = report.guarded_overall_fold
    evidence: dict[str, object] = {
        "source_status": report.status,
        "source_guarded_risk_filter_allowed": report.guarded_risk_filter_allowed,
        "active_fold_count": report.active_fold_count,
        "failed_fold_count": report.failed_fold_count,
        "guarded_skipped_fold_count": report.guarded_skipped_fold_count,
        "removed_candidate_count": report.removed_candidate_count,
        "exact_guard_scope_count": report.exact_guard_scope_count,
        "global_blocked_segment_group_keys": report.global_blocked_segment_group_keys,
        "best_segment_group_key": segment_group_key,
        "best_segment_group_type": report.overall_fold.best_segment_group_type,
        "best_segment_label": report.overall_fold.best_segment_label,
        "adjusted_fixture_count": report.overall_fold.adjusted_fixture_count,
        "adjusted_prediction_count": report.overall_fold.adjusted_prediction_count,
        "final_hit_rate_delta": report.overall_fold.final_hit_rate_delta,
        "roi_delta": report.overall_fold.roi_delta,
        "profit_loss_delta": report.overall_fold.profit_loss_delta,
        "brier_score_delta": report.overall_fold.brier_score_delta,
        "log_loss_delta": report.overall_fold.log_loss_delta,
        "mean_calibration_error_delta": (
            report.overall_fold.mean_calibration_error_delta
        ),
    }
    return HistoricalMarketMovementRiskFilterRuntimeRuleProposal(
        rule_id=options.proposal_id,
        proposed_profile_version=options.proposed_profile_version,
        proposed_production_enabled=False,
        holdout_candidate_enabled=True,
        shadow_replay_enabled=shadow_replay_allowed,
        production_recommendation_changed=False,
        segment_group_keys=[segment_group_key],
        movement_weight=movement_weight,
        max_probability_shift=max_probability_shift,
        source_guarded_admission_report_key=report.report_key,
        source_segment_gate_report_key=guarded_overall.original_segment_gate_report_key,
        source_guarded_segment_gate_report_key=(
            guarded_overall.guarded_segment_gate_report_key
        ),
        source_candidate_id=report.overall_fold.best_candidate_id,
        source_report_keys={
            "guarded_admission": report.report_key,
            "scope_refinement": report.scope_refinement_report_key,
        },
        evidence_json=evidence,
        constraints_json={
            "segment_gate_options": segment_gate_options,
            "production_recommendation_changed": False,
            "public_response_changed": False,
            "shadow_replay_only": True,
        },
        rollback_conditions=[
            "disable_if_shadow_replay_fails_no_harm_gate",
            "disable_if_default_path_or_public_response_would_change",
            "disable_if_future_folds_regress_final_answer_or_probability_quality",
        ],
        notes=[
            "Runtime-shaped rule is shadow-only and does not alter the "
            "default recommendation path.",
            "Selected from guarded market-movement risk-filter admission evidence.",
        ],
    )


def _proposal_profile_set_json(
    rule: HistoricalMarketMovementRiskFilterRuntimeRuleProposal | None,
    *,
    status: HistoricalMarketMovementRiskFilterRuntimeProposalStatus,
    runtime_allowed: bool,
    holdout_allowed: bool,
    options: HistoricalMarketMovementRiskFilterRuntimeProposalOptions,
) -> dict[str, object]:
    rules = [rule.model_dump(mode="json")] if rule is not None else []
    return {
        "calculation_basis": (
            "historical_market_movement_risk_filter_runtime_profile_set_v3_2"
        ),
        "profile_version": options.proposed_profile_version,
        "status": status,
        "runtime_shadow_proposal_allowed": runtime_allowed,
        "runtime_profile_proposal_allowed": runtime_allowed,
        "holdout_candidate_allowed": holdout_allowed,
        "production_recommendation_changed": False,
        "default_recommendation_path_changed": False,
        "public_response_changed": False,
        "market_movement_risk_filter_rules": rules,
        "rules": rules,
        "notes": [
            "Shadow runtime profile only; not part of the user-facing default path.",
        ],
    }


def _source_segment_group_key(
    report: HistoricalMarketMovementRiskFilterGuardedAdmissionReport,
    *,
    options: HistoricalMarketMovementRiskFilterRuntimeProposalOptions,
) -> str | None:
    return options.source_segment_group_key or report.overall_fold.best_segment_group_key


def _segment_gate_options_json(
    report: HistoricalMarketMovementRiskFilterGuardedAdmissionReport,
) -> dict[str, object]:
    rolling_options = _mapping(report.summary_json.get("rolling_options"))
    if rolling_options is None:
        return {}
    segment_gate_options = _mapping(rolling_options.get("segment_gate_options"))
    return dict(segment_gate_options or {})


def _status(
    *,
    runtime_allowed: bool,
    holdout_allowed: bool,
) -> HistoricalMarketMovementRiskFilterRuntimeProposalStatus:
    if runtime_allowed:
        return "runtime_shadow_proposal_ready"
    if holdout_allowed:
        return "holdout_only"
    return "blocked"


def _holdout_checks_passed(
    checks: Sequence[HistoricalMarketMovementRiskFilterRuntimeProposalCheck],
) -> bool:
    blocking_names = {
        "source_guarded_admission_accepted",
        "source_guarded_risk_filter_allowed",
        "production_recommendation_unchanged",
        "source_overall_best_segment_present",
        "source_overall_best_decision_accepted",
        "selected_segment_not_globally_blocked",
        "failed_fold_count",
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
    status: HistoricalMarketMovementRiskFilterRuntimeProposalStatus,
    checks: Sequence[HistoricalMarketMovementRiskFilterRuntimeProposalCheck],
) -> list[str]:
    warnings = [
        f"market_movement_risk_filter_runtime_proposal:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    if status == "runtime_shadow_proposal_ready":
        warnings.append(
            "market_movement_risk_filter_runtime_proposal:ready_for_shadow_replay"
        )
    elif status == "holdout_only":
        warnings.append("market_movement_risk_filter_runtime_proposal:holdout_only")
    else:
        warnings.append("market_movement_risk_filter_runtime_proposal:blocked")
    return warnings


def _boolean_check(
    name: str,
    actual: bool,
    *,
    expected: bool,
    detail: str,
    enabled: bool = True,
) -> HistoricalMarketMovementRiskFilterRuntimeProposalCheck:
    if not enabled:
        return HistoricalMarketMovementRiskFilterRuntimeProposalCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=expected,
            detail=f"{detail} (disabled)",
        )
    return HistoricalMarketMovementRiskFilterRuntimeProposalCheck(
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
) -> HistoricalMarketMovementRiskFilterRuntimeProposalCheck:
    return HistoricalMarketMovementRiskFilterRuntimeProposalCheck(
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
) -> HistoricalMarketMovementRiskFilterRuntimeProposalCheck:
    return HistoricalMarketMovementRiskFilterRuntimeProposalCheck(
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
) -> HistoricalMarketMovementRiskFilterRuntimeProposalCheck:
    return HistoricalMarketMovementRiskFilterRuntimeProposalCheck(
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
) -> HistoricalMarketMovementRiskFilterRuntimeProposalCheck:
    return HistoricalMarketMovementRiskFilterRuntimeProposalCheck(
        name=name,
        status="passed" if actual is not None and actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Create a shadow runtime-rule proposal from guarded market-movement "
            "risk-filter admission evidence."
        )
    )
    parser.add_argument("guarded_admission_report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-output-path", type=Path)
    parser.add_argument(
        "--proposal-id",
        default=DEFAULT_MARKET_MOVEMENT_RISK_FILTER_RUNTIME_PROPOSAL_ID,
    )
    parser.add_argument(
        "--proposed-profile-version",
        default=DEFAULT_MARKET_MOVEMENT_RISK_FILTER_RUNTIME_PROFILE_VERSION,
    )
    parser.add_argument("--source-segment-group-key")
    parser.add_argument("--min-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--min-adjusted-prediction-count", type=int, default=1)
    parser.add_argument("--min-active-fold-count", type=int, default=1)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--allow-non-accepted-guarded-admission", action="store_true")
    parser.add_argument("--allow-guarded-risk-filter-not-allowed", action="store_true")
    parser.add_argument("--allow-production-recommendation-change", action="store_true")
    parser.add_argument("--allow-non-accepted-overall-best", action="store_true")
    parser.add_argument("--allow-globally-blocked-selected-segment", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalMarketMovementRiskFilterRuntimeProposalOptions:
    return HistoricalMarketMovementRiskFilterRuntimeProposalOptions(
        proposal_id=args.proposal_id,
        proposed_profile_version=args.proposed_profile_version,
        source_segment_group_key=args.source_segment_group_key,
        min_adjusted_fixture_count=args.min_adjusted_fixture_count,
        min_adjusted_prediction_count=args.min_adjusted_prediction_count,
        min_active_fold_count=args.min_active_fold_count,
        max_failed_fold_count=args.max_failed_fold_count,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        require_guarded_admission_accepted=(
            not args.allow_non_accepted_guarded_admission
        ),
        require_guarded_risk_filter_allowed=(
            not args.allow_guarded_risk_filter_not_allowed
        ),
        require_production_recommendation_unchanged=(
            not args.allow_production_recommendation_change
        ),
        require_overall_best_accepted=not args.allow_non_accepted_overall_best,
        require_selected_segment_not_globally_blocked=(
            not args.allow_globally_blocked_selected_segment
        ),
    )


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _float(value: object, fallback: float) -> float:
    if isinstance(value, bool) or value is None:
        return fallback
    if isinstance(value, int | float):
        return float(value)
    return fallback


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalMarketMovementRiskFilterRuntimeProposalCheck],
    rule: HistoricalMarketMovementRiskFilterRuntimeRuleProposal | None,
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "rule": rule.model_dump(mode="json") if rule is not None else None,
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_market_movement_risk_filter_runtime_proposal:{digest}"
