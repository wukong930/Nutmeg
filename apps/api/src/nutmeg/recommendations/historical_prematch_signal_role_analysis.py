from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

type HistoricalPrematchSignalRoleAnalysisStatus = Literal["generated"]
type HistoricalPrematchSignalRole = Literal[
    "lambda_adjustment",
    "probability_adjustment",
    "final_answer_filter",
    "risk_filter",
    "research_only",
]
type HistoricalPrematchSignalRoleDecisionStatus = Literal[
    "accepted",
    "shadow_candidate",
    "blocked",
    "insufficient_evidence",
]

DEFAULT_PREMATCH_SIGNAL_ROLE_ANALYSIS_ID = "prematch-signal-role-analysis-v3.2"


class HistoricalPrematchSignalRoleAnalysisOptions(BaseModel):
    analysis_id: str = DEFAULT_PREMATCH_SIGNAL_ROLE_ANALYSIS_ID
    min_sample_ready_fixture_count: int = Field(default=100, ge=0)
    min_sample_ready_competition_count: int = Field(default=1, ge=0)
    min_market_segment_accepted_count: int = Field(default=1, ge=0)
    require_market_segment_final_answer_gate: bool = True
    require_probability_rolling_admission: bool = False
    require_sample_readiness_for_shadow: bool = True


class HistoricalPrematchSignalRoleDecision(BaseModel):
    role: HistoricalPrematchSignalRole
    decision: HistoricalPrematchSignalRoleDecisionStatus
    evidence_report_key: str | None = None
    evidence_status: str | None = None
    evidence_present: bool = False
    sample_ready: bool | None = None
    sample_ready_fixture_count: int | None = Field(default=None, ge=0)
    sample_ready_competition_count: int | None = Field(default=None, ge=0)
    candidate_allowed: bool | None = None
    shadow_allowed: bool | None = None
    accepted_count: int | None = Field(default=None, ge=0)
    passing_candidate_count: int | None = Field(default=None, ge=0)
    failed_no_harm_count: int | None = Field(default=None, ge=0)
    hit_rate_delta: float | None = None
    final_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    calibration_error_delta: float | None = None
    reasons: list[str] = Field(default_factory=list)
    next_action: str
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchSignalRoleAnalysisReport(BaseModel):
    report_key: str
    status: HistoricalPrematchSignalRoleAnalysisStatus
    analysis_id: str
    sample_readiness_report_key: str | None = None
    sample_ready: bool | None = None
    sample_ready_fixture_count: int | None = Field(default=None, ge=0)
    sample_ready_competition_count: int | None = Field(default=None, ge=0)
    primary_recommended_role: HistoricalPrematchSignalRole
    production_allowed_role_count: int = Field(ge=0)
    shadow_candidate_role_count: int = Field(ge=0)
    blocked_role_count: int = Field(ge=0)
    insufficient_evidence_role_count: int = Field(ge=0)
    decisions: list[HistoricalPrematchSignalRoleDecision] = Field(
        default_factory=list
    )
    next_core_work_items: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_prematch_signal_role_analysis_report(
    *,
    sample_readiness_report: Mapping[str, object] | None = None,
    lambda_admission_report: Mapping[str, object] | None = None,
    final_answer_gate_report: Mapping[str, object] | None = None,
    rolling_admission_report: Mapping[str, object] | None = None,
    market_segment_gate_report: Mapping[str, object] | None = None,
    options: HistoricalPrematchSignalRoleAnalysisOptions | None = None,
) -> HistoricalPrematchSignalRoleAnalysisReport:
    resolved_options = options or HistoricalPrematchSignalRoleAnalysisOptions()
    sample_context = _sample_context(sample_readiness_report)
    decisions = [
        _lambda_decision(
            lambda_admission_report,
            sample_context=sample_context,
            options=resolved_options,
        ),
        _probability_adjustment_decision(
            final_answer_gate_report,
            rolling_admission_report=rolling_admission_report,
            sample_context=sample_context,
            options=resolved_options,
        ),
        _final_answer_filter_decision(
            final_answer_gate_report,
            rolling_admission_report=rolling_admission_report,
            sample_context=sample_context,
            options=resolved_options,
        ),
        _risk_filter_decision(
            market_segment_gate_report,
            sample_context=sample_context,
            options=resolved_options,
        ),
        _research_only_decision(
            sample_context=sample_context,
            options=resolved_options,
        ),
    ]
    primary_role = _primary_role(decisions)
    next_work = _next_core_work_items(decisions, primary_role=primary_role)
    warnings = _warnings(decisions, sample_context=sample_context)
    production_count = sum(1 for item in decisions if item.decision == "accepted")
    shadow_count = sum(1 for item in decisions if item.decision == "shadow_candidate")
    blocked_count = sum(1 for item in decisions if item.decision == "blocked")
    insufficient_count = sum(
        1 for item in decisions if item.decision == "insufficient_evidence"
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_prematch_signal_role_analysis_v3_2",
        "analysis_id": resolved_options.analysis_id,
        "sample_readiness_report_key": sample_context.report_key,
        "sample_ready": sample_context.ready,
        "sample_ready_fixture_count": sample_context.ready_fixture_count,
        "sample_ready_competition_count": sample_context.ready_competition_count,
        "primary_recommended_role": primary_role,
        "production_allowed_role_count": production_count,
        "shadow_candidate_role_count": shadow_count,
        "blocked_role_count": blocked_count,
        "insufficient_evidence_role_count": insufficient_count,
        "decisions": [decision.model_dump(mode="json") for decision in decisions],
        "next_core_work_items": next_work,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary)
    return HistoricalPrematchSignalRoleAnalysisReport(
        report_key=report_key,
        status="generated",
        analysis_id=resolved_options.analysis_id,
        sample_readiness_report_key=sample_context.report_key,
        sample_ready=sample_context.ready,
        sample_ready_fixture_count=sample_context.ready_fixture_count,
        sample_ready_competition_count=sample_context.ready_competition_count,
        primary_recommended_role=primary_role,
        production_allowed_role_count=production_count,
        shadow_candidate_role_count=shadow_count,
        blocked_role_count=blocked_count,
        insufficient_evidence_role_count=insufficient_count,
        decisions=decisions,
        next_core_work_items=next_work,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_prematch_signal_role_analysis_report(
    path: Path | str,
) -> HistoricalPrematchSignalRoleAnalysisReport:
    return HistoricalPrematchSignalRoleAnalysisReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_prematch_signal_role_analysis_report(
        sample_readiness_report=_load_optional_json(args.sample_readiness_report),
        lambda_admission_report=_load_optional_json(args.lambda_admission_report),
        final_answer_gate_report=_load_optional_json(args.final_answer_gate_report),
        rolling_admission_report=_load_optional_json(args.rolling_admission_report),
        market_segment_gate_report=_load_optional_json(args.market_segment_gate_report),
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
    print(output)


class _SampleContext(BaseModel):
    report_key: str | None = None
    ready: bool | None = None
    ready_fixture_count: int | None = Field(default=None, ge=0)
    ready_competition_count: int | None = Field(default=None, ge=0)
    ready_season_count: int | None = Field(default=None, ge=0)
    ready_competition_season_count: int | None = Field(default=None, ge=0)


def _sample_context(
    sample_readiness_report: Mapping[str, object] | None,
) -> _SampleContext:
    if sample_readiness_report is None:
        return _SampleContext()
    return _SampleContext(
        report_key=_optional_str(
            _first_value(sample_readiness_report, "readiness_key", "report_key")
        ),
        ready=_optional_bool(sample_readiness_report.get("sample_ready_allowed")),
        ready_fixture_count=_optional_int(
            sample_readiness_report.get("ready_fixture_count")
        ),
        ready_competition_count=_optional_int(
            sample_readiness_report.get("ready_competition_count")
        ),
        ready_season_count=_optional_int(
            sample_readiness_report.get("ready_season_count")
        ),
        ready_competition_season_count=_optional_int(
            sample_readiness_report.get("ready_competition_season_count")
        ),
    )


def _lambda_decision(
    report: Mapping[str, object] | None,
    *,
    sample_context: _SampleContext,
    options: HistoricalPrematchSignalRoleAnalysisOptions,
) -> HistoricalPrematchSignalRoleDecision:
    if report is None:
        return _decision(
            role="lambda_adjustment",
            decision="insufficient_evidence",
            sample_context=sample_context,
            reasons=["missing_lambda_admission_report"],
            next_action="Keep prematch features out of lambda until admission evidence exists.",
        )
    candidate_allowed = _optional_bool(report.get("candidate_model_allowed"))
    shadow_allowed = _optional_bool(report.get("shadow_allowed"))
    reasons: list[str] = []
    if not _sample_shadow_ready(sample_context, options=options):
        reasons.append("sample_readiness_below_shadow_floor")
    if candidate_allowed is True:
        decision: HistoricalPrematchSignalRoleDecisionStatus = "accepted"
        next_action = (
            "Prematch lambda adjustment can be promoted only through the model "
            "governance path."
        )
    elif shadow_allowed:
        decision = "blocked"
        reasons.extend(_failed_check_names(report))
        next_action = (
            "Do not tune lambda further from this signal; inspect whether the "
            "signal works as a filter."
        )
    else:
        decision = "insufficient_evidence"
        reasons.append("lambda_admission_not_shadow_allowed")
        next_action = "Rebuild lambda admission after sample quality improves."
    return _decision(
        role="lambda_adjustment",
        decision=decision,
        sample_context=sample_context,
        evidence_report=report,
        candidate_allowed=candidate_allowed,
        shadow_allowed=shadow_allowed,
        failed_no_harm_count=_optional_int(
            report.get("failed_competition_no_harm_count")
        ),
        hit_rate_delta=_optional_float(report.get("hit_rate_delta")),
        brier_score_delta=_optional_float(report.get("brier_score_delta")),
        log_loss_delta=_optional_float(report.get("log_loss_delta")),
        calibration_error_delta=_optional_float(
            report.get("expected_calibration_error_delta")
        ),
        reasons=_dedupe_strings(reasons),
        next_action=next_action,
    )


def _probability_adjustment_decision(
    final_answer_gate_report: Mapping[str, object] | None,
    *,
    rolling_admission_report: Mapping[str, object] | None,
    sample_context: _SampleContext,
    options: HistoricalPrematchSignalRoleAnalysisOptions,
) -> HistoricalPrematchSignalRoleDecision:
    if rolling_admission_report is not None:
        candidate_allowed = _optional_bool(
            rolling_admission_report.get("candidate_feature_allowed")
        )
        shadow_allowed = _optional_bool(rolling_admission_report.get("shadow_allowed"))
        decision: HistoricalPrematchSignalRoleDecisionStatus
        reasons = _failed_check_names(rolling_admission_report)
        if candidate_allowed is True:
            decision = "accepted"
            next_action = "Keep the probability adjustment behind rolling-admission governance."
        elif shadow_allowed:
            decision = "shadow_candidate"
            next_action = "Continue rolling-window validation before any runtime activation."
        else:
            decision = "blocked"
            next_action = "Block probability adjustment until rolling admission passes."
        return _decision(
            role="probability_adjustment",
            decision=decision,
            sample_context=sample_context,
            evidence_report=rolling_admission_report,
            candidate_allowed=candidate_allowed,
            shadow_allowed=shadow_allowed,
            passing_candidate_count=_optional_int(
                rolling_admission_report.get("overall_passing_candidate_count")
            ),
            final_hit_rate_delta=_optional_float(
                _nested_value(
                    rolling_admission_report,
                    ("overall_fold", "final_hit_rate_delta"),
                )
            ),
            roi_delta=_optional_float(
                _nested_value(rolling_admission_report, ("overall_fold", "roi_delta"))
            ),
            profit_loss_delta=_optional_float(
                _nested_value(
                    rolling_admission_report,
                    ("overall_fold", "profit_loss_delta"),
                )
            ),
            brier_score_delta=_optional_float(
                _nested_value(
                    rolling_admission_report,
                    ("overall_fold", "brier_score_delta"),
                )
            ),
            log_loss_delta=_optional_float(
                _nested_value(rolling_admission_report, ("overall_fold", "log_loss_delta"))
            ),
            calibration_error_delta=_optional_float(
                _nested_value(
                    rolling_admission_report,
                    ("overall_fold", "mean_calibration_error_delta"),
                )
            ),
            reasons=reasons,
            next_action=next_action,
        )
    if final_answer_gate_report is None:
        return _decision(
            role="probability_adjustment",
            decision="insufficient_evidence",
            sample_context=sample_context,
            reasons=["missing_final_answer_gate_or_rolling_admission"],
            next_action=(
                "Run final-answer and rolling admission before using this as a "
                "probability surface."
            ),
        )
    passing_count = _optional_int(final_answer_gate_report.get("passing_candidate_count"))
    best = _mapping(final_answer_gate_report.get("best_evaluation"))
    deltas = _mapping(best.get("deltas_json"))
    if options.require_probability_rolling_admission:
        decision = "insufficient_evidence"
        reasons = ["rolling_admission_required"]
        next_action = (
            "Generate prematch rolling admission before treating this as a "
            "probability adjustment."
        )
    elif (passing_count or 0) > 0:
        decision = "shadow_candidate"
        reasons = ["final_answer_gate_has_passing_candidate"]
        next_action = "Promote only after rolling-window admission passes."
    else:
        decision = "blocked"
        reasons = ["final_answer_gate_has_no_passing_candidate", *_failed_quality_checks(best)]
        next_action = "Do not use broad prematch probability adjustment; isolate narrower segments."
    return _decision(
        role="probability_adjustment",
        decision=decision,
        sample_context=sample_context,
        evidence_report=final_answer_gate_report,
        passing_candidate_count=passing_count,
        final_hit_rate_delta=_optional_float(deltas.get("final_hit_rate_delta")),
        roi_delta=_optional_float(deltas.get("roi_delta")),
        profit_loss_delta=_optional_float(deltas.get("profit_loss_delta")),
        brier_score_delta=_optional_float(deltas.get("brier_score_delta")),
        log_loss_delta=_optional_float(deltas.get("log_loss_delta")),
        calibration_error_delta=_optional_float(
            deltas.get("mean_calibration_error_delta")
        ),
        reasons=_dedupe_strings(reasons),
        next_action=next_action,
    )


def _final_answer_filter_decision(
    final_answer_gate_report: Mapping[str, object] | None,
    *,
    rolling_admission_report: Mapping[str, object] | None,
    sample_context: _SampleContext,
    options: HistoricalPrematchSignalRoleAnalysisOptions,
) -> HistoricalPrematchSignalRoleDecision:
    if rolling_admission_report is not None:
        return _probability_adjustment_decision(
            final_answer_gate_report,
            rolling_admission_report=rolling_admission_report,
            sample_context=sample_context,
            options=options,
        ).model_copy(update={"role": "final_answer_filter"})
    if final_answer_gate_report is None:
        return _decision(
            role="final_answer_filter",
            decision="insufficient_evidence",
            sample_context=sample_context,
            reasons=["missing_final_answer_gate_report"],
            next_action=(
                "Run final-answer gate before using prematch features as "
                "selection filters."
            ),
        )
    passing_count = _optional_int(final_answer_gate_report.get("passing_candidate_count"))
    best = _mapping(final_answer_gate_report.get("best_evaluation"))
    deltas = _mapping(best.get("deltas_json"))
    final_hit_delta = _optional_float(deltas.get("final_hit_rate_delta"))
    roi_delta = _optional_float(deltas.get("roi_delta"))
    if (passing_count or 0) > 0:
        decision: HistoricalPrematchSignalRoleDecisionStatus = "shadow_candidate"
        reasons = ["final_answer_gate_has_passing_candidate"]
        next_action = "Validate the filter across competition and rolling folds."
    elif (final_hit_delta or 0.0) > 0.0 or (roi_delta or 0.0) > 0.0:
        decision = "shadow_candidate"
        reasons = [
            "final_answer_has_local_benefit_but_quality_gate_failed",
            *_failed_quality_checks(best),
        ]
        next_action = (
            "Search narrower filters that keep final-hit gains without "
            "Brier/log-loss harm."
        )
    else:
        decision = "blocked"
        reasons = ["final_answer_gate_has_no_passing_candidate"]
        next_action = "Do not use broad prematch feature filters in final answer selection."
    return _decision(
        role="final_answer_filter",
        decision=decision,
        sample_context=sample_context,
        evidence_report=final_answer_gate_report,
        passing_candidate_count=passing_count,
        final_hit_rate_delta=final_hit_delta,
        roi_delta=roi_delta,
        profit_loss_delta=_optional_float(deltas.get("profit_loss_delta")),
        brier_score_delta=_optional_float(deltas.get("brier_score_delta")),
        log_loss_delta=_optional_float(deltas.get("log_loss_delta")),
        calibration_error_delta=_optional_float(
            deltas.get("mean_calibration_error_delta")
        ),
        reasons=_dedupe_strings(reasons),
        next_action=next_action,
    )


def _risk_filter_decision(
    report: Mapping[str, object] | None,
    *,
    sample_context: _SampleContext,
    options: HistoricalPrematchSignalRoleAnalysisOptions,
) -> HistoricalPrematchSignalRoleDecision:
    if report is None:
        return _decision(
            role="risk_filter",
            decision="insufficient_evidence",
            sample_context=sample_context,
            reasons=["missing_market_segment_gate_report"],
            next_action="Run market-movement segment gate to test risk/filter use.",
        )
    accepted_count = _optional_int(report.get("accepted_count")) or 0
    best = _mapping(report.get("best_candidate"))
    final_answer_deltas = _mapping(best.get("final_answer_deltas_json"))
    passed_final_answer = _optional_bool(best.get("passed_final_answer_gate"))
    reasons: list[str] = []
    if accepted_count < options.min_market_segment_accepted_count:
        reasons.append("accepted_segment_count_below_floor")
    if options.require_market_segment_final_answer_gate and passed_final_answer is not True:
        reasons.append("best_segment_final_answer_gate_not_passed")
    if not _sample_shadow_ready(sample_context, options=options):
        reasons.append("sample_readiness_below_shadow_floor")
    if not reasons:
        decision: HistoricalPrematchSignalRoleDecisionStatus = "shadow_candidate"
        next_action = "Build a rolling-admission risk-filter lane before runtime exposure."
    else:
        decision = "blocked"
        next_action = "Keep market movement as diagnostics until segment quality improves."
    return _decision(
        role="risk_filter",
        decision=decision,
        sample_context=sample_context,
        evidence_report=report,
        accepted_count=accepted_count,
        passing_candidate_count=1 if passed_final_answer else 0,
        final_hit_rate_delta=_optional_float(
            final_answer_deltas.get("final_hit_rate_delta")
        ),
        roi_delta=_optional_float(final_answer_deltas.get("roi_delta")),
        profit_loss_delta=_optional_float(final_answer_deltas.get("profit_loss_delta")),
        brier_score_delta=_optional_float(final_answer_deltas.get("brier_score_delta")),
        log_loss_delta=_optional_float(final_answer_deltas.get("log_loss_delta")),
        calibration_error_delta=_optional_float(
            final_answer_deltas.get("mean_calibration_error_delta")
        ),
        reasons=_dedupe_strings([*reasons, *_best_decision_reasons(best)]),
        next_action=next_action,
    )


def _research_only_decision(
    *,
    sample_context: _SampleContext,
    options: HistoricalPrematchSignalRoleAnalysisOptions,
) -> HistoricalPrematchSignalRoleDecision:
    decision: HistoricalPrematchSignalRoleDecisionStatus = (
        "shadow_candidate"
        if _sample_shadow_ready(sample_context, options=options)
        else "insufficient_evidence"
    )
    return _decision(
        role="research_only",
        decision=decision,
        sample_context=sample_context,
        reasons=["always_available_as_offline_evidence"],
        next_action=(
            "Keep collecting audited prematch evidence without changing "
            "user-facing recommendations."
        ),
    )


def _decision(
    *,
    role: HistoricalPrematchSignalRole,
    decision: HistoricalPrematchSignalRoleDecisionStatus,
    sample_context: _SampleContext,
    next_action: str,
    evidence_report: Mapping[str, object] | None = None,
    candidate_allowed: bool | None = None,
    shadow_allowed: bool | None = None,
    accepted_count: int | None = None,
    passing_candidate_count: int | None = None,
    failed_no_harm_count: int | None = None,
    hit_rate_delta: float | None = None,
    final_hit_rate_delta: float | None = None,
    roi_delta: float | None = None,
    profit_loss_delta: float | None = None,
    brier_score_delta: float | None = None,
    log_loss_delta: float | None = None,
    calibration_error_delta: float | None = None,
    reasons: Sequence[str] = (),
) -> HistoricalPrematchSignalRoleDecision:
    evidence_key = (
        _optional_str(_first_value(evidence_report, "report_key", "cycle_key"))
        if evidence_report is not None
        else None
    )
    evidence_status = (
        _optional_str(evidence_report.get("status"))
        if evidence_report is not None
        else None
    )
    summary: dict[str, object] = {
        "role": role,
        "decision": decision,
        "evidence_report_key": evidence_key,
        "evidence_status": evidence_status,
        "sample_ready": sample_context.ready,
        "reasons": list(reasons),
        "next_action": next_action,
    }
    return HistoricalPrematchSignalRoleDecision(
        role=role,
        decision=decision,
        evidence_report_key=evidence_key,
        evidence_status=evidence_status,
        evidence_present=evidence_report is not None,
        sample_ready=sample_context.ready,
        sample_ready_fixture_count=sample_context.ready_fixture_count,
        sample_ready_competition_count=sample_context.ready_competition_count,
        candidate_allowed=candidate_allowed,
        shadow_allowed=shadow_allowed,
        accepted_count=accepted_count,
        passing_candidate_count=passing_candidate_count,
        failed_no_harm_count=failed_no_harm_count,
        hit_rate_delta=hit_rate_delta,
        final_hit_rate_delta=final_hit_rate_delta,
        roi_delta=roi_delta,
        profit_loss_delta=profit_loss_delta,
        brier_score_delta=brier_score_delta,
        log_loss_delta=log_loss_delta,
        calibration_error_delta=calibration_error_delta,
        reasons=list(reasons),
        next_action=next_action,
        summary_json=summary,
    )


def _primary_role(
    decisions: Sequence[HistoricalPrematchSignalRoleDecision],
) -> HistoricalPrematchSignalRole:
    priority: dict[HistoricalPrematchSignalRoleDecisionStatus, int] = {
        "accepted": 0,
        "shadow_candidate": 1,
        "blocked": 2,
        "insufficient_evidence": 3,
    }
    role_priority: dict[HistoricalPrematchSignalRole, int] = {
        "risk_filter": 0,
        "final_answer_filter": 1,
        "probability_adjustment": 2,
        "lambda_adjustment": 3,
        "research_only": 4,
    }
    return min(
        decisions,
        key=lambda item: (priority[item.decision], role_priority[item.role]),
    ).role


def _next_core_work_items(
    decisions: Sequence[HistoricalPrematchSignalRoleDecision],
    *,
    primary_role: HistoricalPrematchSignalRole,
) -> list[str]:
    decision_by_role = {decision.role: decision for decision in decisions}
    work_items: list[str] = []
    if primary_role == "risk_filter":
        work_items.append(
            "Build market-movement risk-filter rolling admission before runtime activation."
        )
    if decision_by_role["lambda_adjustment"].decision == "blocked":
        work_items.append(
            "Stop broad prematch lambda tuning until a new signal family passes no-harm."
        )
    if decision_by_role["final_answer_filter"].decision == "shadow_candidate":
        work_items.append(
            "Search narrower final-answer filters that preserve Brier/log-loss "
            "while keeping hit-rate gains."
        )
    if not work_items:
        work_items.append("Collect more audited prematch samples before activation work.")
    return work_items


def _warnings(
    decisions: Sequence[HistoricalPrematchSignalRoleDecision],
    *,
    sample_context: _SampleContext,
) -> list[str]:
    warnings: list[str] = []
    if sample_context.ready is not True:
        warnings.append("prematch_signal_role_analysis:sample_not_ready")
    for decision in decisions:
        if decision.decision in {"blocked", "insufficient_evidence"}:
            warnings.append(
                f"prematch_signal_role_analysis:{decision.role}:{decision.decision}"
            )
    return warnings


def _sample_shadow_ready(
    sample_context: _SampleContext,
    *,
    options: HistoricalPrematchSignalRoleAnalysisOptions,
) -> bool:
    if not options.require_sample_readiness_for_shadow:
        return True
    return (
        sample_context.ready is True
        and (sample_context.ready_fixture_count or 0)
        >= options.min_sample_ready_fixture_count
        and (sample_context.ready_competition_count or 0)
        >= options.min_sample_ready_competition_count
    )


def _failed_check_names(report: Mapping[str, object]) -> list[str]:
    checks = report.get("checks")
    if not isinstance(checks, list):
        return []
    names: list[str] = []
    for check in checks:
        check_mapping = _mapping(check)
        if check_mapping.get("status") == "failed":
            name = _optional_str(check_mapping.get("name"))
            if name is not None:
                names.append(name)
    return names


def _failed_quality_checks(best_evaluation: Mapping[str, object]) -> list[str]:
    quality_gate = _mapping(best_evaluation.get("quality_gate"))
    checks = quality_gate.get("checks")
    if not isinstance(checks, list):
        return []
    failed: list[str] = []
    for check in checks:
        check_mapping = _mapping(check)
        if check_mapping.get("status") == "failed":
            name = _optional_str(check_mapping.get("name"))
            if name is not None:
                failed.append(f"quality_check_failed:{name}")
    return failed


def _best_decision_reasons(best_candidate: Mapping[str, object]) -> list[str]:
    reasons = best_candidate.get("decision_reasons")
    if not isinstance(reasons, list):
        return []
    return [reason for reason in reasons if isinstance(reason, str)]


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Classify how prematch signals should be used after shadow evidence."
    )
    parser.add_argument("--sample-readiness-report", type=Path)
    parser.add_argument("--lambda-admission-report", type=Path)
    parser.add_argument("--final-answer-gate-report", type=Path)
    parser.add_argument("--rolling-admission-report", type=Path)
    parser.add_argument("--market-segment-gate-report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--analysis-id",
        default=DEFAULT_PREMATCH_SIGNAL_ROLE_ANALYSIS_ID,
    )
    parser.add_argument("--min-sample-ready-fixture-count", type=int, default=100)
    parser.add_argument("--min-sample-ready-competition-count", type=int, default=1)
    parser.add_argument("--min-market-segment-accepted-count", type=int, default=1)
    parser.add_argument(
        "--allow-market-segment-without-final-answer-gate",
        action="store_true",
    )
    parser.add_argument("--require-probability-rolling-admission", action="store_true")
    parser.add_argument("--allow-shadow-without-sample-readiness", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalPrematchSignalRoleAnalysisOptions:
    return HistoricalPrematchSignalRoleAnalysisOptions(
        analysis_id=args.analysis_id,
        min_sample_ready_fixture_count=args.min_sample_ready_fixture_count,
        min_sample_ready_competition_count=args.min_sample_ready_competition_count,
        min_market_segment_accepted_count=args.min_market_segment_accepted_count,
        require_market_segment_final_answer_gate=(
            not args.allow_market_segment_without_final_answer_gate
        ),
        require_probability_rolling_admission=args.require_probability_rolling_admission,
        require_sample_readiness_for_shadow=(
            not args.allow_shadow_without_sample_readiness
        ),
    )


def _load_optional_json(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    payload = loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {path}")
    return {str(key): value for key, value in payload.items()}


def _report_key(summary: Mapping[str, object]) -> str:
    digest = sha256(
        dumps(summary, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_prematch_signal_role_analysis:{digest}"


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _nested_value(mapping: Mapping[str, object], path: Sequence[str]) -> object:
    current: object = mapping
    for key in path:
        current_mapping = _mapping(current)
        if key not in current_mapping:
            return None
        current = current_mapping[key]
    return current


def _first_value(
    mapping: Mapping[str, object] | None,
    *keys: str,
) -> object:
    if mapping is None:
        return None
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return None


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
