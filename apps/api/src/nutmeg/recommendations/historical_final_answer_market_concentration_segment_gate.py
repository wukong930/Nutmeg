from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_final_answer_market_concentration_audit import (
    HistoricalFinalAnswerMarketConcentrationAuditReport,
)
from nutmeg.recommendations.models import RecommendationMode

type SegmentGateStatus = Literal["passed", "failed"]
type SegmentAdmissionDecision = Literal["promote_candidate", "block_segment"]


class HistoricalFinalAnswerMarketConcentrationConstraintProfile(BaseModel):
    profile_key: str
    pass_type: str
    mode: RecommendationMode | None = None
    constraint_profile_id: str
    constraint_profile_json: dict[str, object] = Field(default_factory=dict)


class HistoricalFinalAnswerMarketConcentrationSegmentDecision(BaseModel):
    report_path: str
    report_key: str
    pass_type: str
    mode: RecommendationMode | None = None
    constraint_profile_id: str = "default"
    constraint_profile_key: str = ""
    constraint_profile_json: dict[str, object] = Field(default_factory=dict)
    decision: SegmentAdmissionDecision
    status: str
    suite_status: str
    failed_checks: list[str] = Field(default_factory=list)
    slice_count: int = Field(ge=0)
    final_answer_count: int = Field(ge=0)
    dynamic_mixed_final_answer_count: int = Field(ge=0)
    dynamic_mixed_final_answer_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    multiple_choice_final_answer_count: int = Field(ge=0)
    candidate_final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    candidate_roi: float | None = None
    candidate_profit_loss: float
    final_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    reason_codes: list[str] = Field(default_factory=list)


class HistoricalFinalAnswerMarketConcentrationSegmentGateReport(BaseModel):
    report_key: str
    status: SegmentGateStatus
    passed: bool
    segment_count: int = Field(ge=0)
    promoted_segment_count: int = Field(ge=0)
    blocked_segment_count: int = Field(ge=0)
    promoted_pass_types: list[str] = Field(default_factory=list)
    blocked_pass_types: list[str] = Field(default_factory=list)
    promoted_constraint_profiles: list[
        HistoricalFinalAnswerMarketConcentrationConstraintProfile
    ] = Field(default_factory=list)
    blocked_constraint_profiles: list[
        HistoricalFinalAnswerMarketConcentrationConstraintProfile
    ] = Field(default_factory=list)
    decisions: list[HistoricalFinalAnswerMarketConcentrationSegmentDecision] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalFinalAnswerMarketConcentrationSegmentGateOptions(BaseModel):
    min_promoted_segment_count: int = Field(default=1, ge=0)
    require_all_segments_passed: bool = False


def build_historical_final_answer_market_concentration_segment_gate(
    reports: Sequence[HistoricalFinalAnswerMarketConcentrationAuditReport],
    *,
    report_paths: Sequence[Path | str] = (),
    options: HistoricalFinalAnswerMarketConcentrationSegmentGateOptions | None = None,
) -> HistoricalFinalAnswerMarketConcentrationSegmentGateReport:
    resolved_options = options or HistoricalFinalAnswerMarketConcentrationSegmentGateOptions()
    paths = [str(path) for path in report_paths]
    decisions = [
        _decision_from_report(
            report,
            report_path=paths[index] if index < len(paths) else "",
        )
        for index, report in enumerate(reports)
    ]
    promoted = [
        decision
        for decision in decisions
        if decision.decision == "promote_candidate"
    ]
    blocked = [
        decision
        for decision in decisions
        if decision.decision == "block_segment"
    ]
    passed = len(promoted) >= resolved_options.min_promoted_segment_count and (
        not resolved_options.require_all_segments_passed or not blocked
    )
    report_key = _segment_gate_report_key(
        decisions,
        options=resolved_options,
    )
    warnings = _warnings(
        decisions,
        min_promoted_segment_count=resolved_options.min_promoted_segment_count,
        require_all_segments_passed=resolved_options.require_all_segments_passed,
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_final_answer_market_concentration_segment_gate_v3_1"
        ),
        "report_key": report_key,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "segment_count": len(decisions),
        "promoted_segment_count": len(promoted),
        "blocked_segment_count": len(blocked),
        "promoted_pass_types": [decision.pass_type for decision in promoted],
        "blocked_pass_types": [decision.pass_type for decision in blocked],
        "promoted_constraint_profiles": [
            _constraint_profile_from_decision(decision).model_dump(mode="json")
            for decision in promoted
        ],
        "blocked_constraint_profiles": [
            _constraint_profile_from_decision(decision).model_dump(mode="json")
            for decision in blocked
        ],
        "warnings": warnings,
    }
    return HistoricalFinalAnswerMarketConcentrationSegmentGateReport(
        report_key=report_key,
        status="passed" if passed else "failed",
        passed=passed,
        segment_count=len(decisions),
        promoted_segment_count=len(promoted),
        blocked_segment_count=len(blocked),
        promoted_pass_types=[decision.pass_type for decision in promoted],
        blocked_pass_types=[decision.pass_type for decision in blocked],
        promoted_constraint_profiles=[
            _constraint_profile_from_decision(decision) for decision in promoted
        ],
        blocked_constraint_profiles=[
            _constraint_profile_from_decision(decision) for decision in blocked
        ],
        decisions=decisions,
        warnings=warnings,
        summary_json=summary,
    )


def load_historical_final_answer_market_concentration_segment_gate_report(
    path: Path | str,
) -> HistoricalFinalAnswerMarketConcentrationAuditReport:
    return HistoricalFinalAnswerMarketConcentrationAuditReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    reports = [
        load_historical_final_answer_market_concentration_segment_gate_report(path)
        for path in args.report_paths
    ]
    report = build_historical_final_answer_market_concentration_segment_gate(
        reports,
        report_paths=args.report_paths,
        options=HistoricalFinalAnswerMarketConcentrationSegmentGateOptions(
            min_promoted_segment_count=args.min_promoted_segment_count,
            require_all_segments_passed=args.require_all_segments_passed,
        ),
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
    if not report.passed and not args.no_fail_process:
        raise SystemExit(1)


def _decision_from_report(
    report: HistoricalFinalAnswerMarketConcentrationAuditReport,
    *,
    report_path: str,
) -> HistoricalFinalAnswerMarketConcentrationSegmentDecision:
    failed_checks = _failed_checks(report)
    pass_type = _pass_type(report)
    mode = _mode(report)
    constraint_profile_json = _constraint_profile_json(report)
    constraint_profile_id = _constraint_profile_id(constraint_profile_json)
    constraint_profile_key = _constraint_profile_key(
        pass_type=pass_type,
        mode=mode,
        constraint_profile_id=constraint_profile_id,
    )
    reason_codes = _reason_codes(failed_checks)
    decision: SegmentAdmissionDecision = (
        "promote_candidate" if report.passed else "block_segment"
    )
    return HistoricalFinalAnswerMarketConcentrationSegmentDecision(
        report_path=report_path,
        report_key=report.report_key,
        pass_type=pass_type,
        mode=mode,
        constraint_profile_id=constraint_profile_id,
        constraint_profile_key=constraint_profile_key,
        constraint_profile_json=constraint_profile_json,
        decision=decision,
        status=report.status,
        suite_status=report.suite_status,
        failed_checks=failed_checks,
        slice_count=report.slice_count,
        final_answer_count=report.final_answer_count,
        dynamic_mixed_final_answer_count=report.dynamic_mixed_final_answer_count,
        dynamic_mixed_final_answer_rate=report.dynamic_mixed_final_answer_rate,
        multiple_choice_final_answer_count=report.multiple_choice_final_answer_count,
        candidate_final_hit_rate=report.candidate_final_hit_rate,
        candidate_roi=report.candidate_roi,
        candidate_profit_loss=report.candidate_profit_loss,
        final_hit_rate_delta=_metric(report.aggregate_deltas_json, "final_hit_rate_delta"),
        roi_delta=_metric(report.aggregate_deltas_json, "roi_delta"),
        profit_loss_delta=_metric(report.aggregate_deltas_json, "profit_loss_delta"),
        brier_score_delta=_metric(report.aggregate_deltas_json, "brier_score_delta"),
        log_loss_delta=_metric(report.aggregate_deltas_json, "log_loss_delta"),
        mean_calibration_error_delta=_metric(
            report.aggregate_deltas_json,
            "mean_calibration_error_delta",
        ),
        reason_codes=reason_codes,
    )


def _failed_checks(
    report: HistoricalFinalAnswerMarketConcentrationAuditReport,
) -> list[str]:
    raw = report.summary_json.get("failed_checks", [])
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return [check.name for check in report.checks if check.status == "failed"]


def _constraint_profile_from_decision(
    decision: HistoricalFinalAnswerMarketConcentrationSegmentDecision,
) -> HistoricalFinalAnswerMarketConcentrationConstraintProfile:
    return HistoricalFinalAnswerMarketConcentrationConstraintProfile(
        profile_key=decision.constraint_profile_key
        or _constraint_profile_key(
            pass_type=decision.pass_type,
            mode=decision.mode,
            constraint_profile_id=decision.constraint_profile_id,
        ),
        pass_type=decision.pass_type,
        mode=decision.mode,
        constraint_profile_id=decision.constraint_profile_id,
        constraint_profile_json=dict(decision.constraint_profile_json),
    )


def _constraint_profile_json(
    report: HistoricalFinalAnswerMarketConcentrationAuditReport,
) -> dict[str, object]:
    max_outcomes_per_fixture = _summary_int(
        report.summary_json,
        "max_outcomes_per_fixture",
        default=2,
    )
    min_marginal_quality_gain = _summary_float(
        report.summary_json,
        "min_marginal_quality_gain",
        default=0.0,
    )
    return {
        "max_outcomes_per_fixture": max_outcomes_per_fixture,
        "min_marginal_quality_gain": min_marginal_quality_gain,
    }


def _constraint_profile_id(profile: Mapping[str, object]) -> str:
    max_outcomes = profile.get("max_outcomes_per_fixture", 2)
    min_gain = _coerce_float(profile.get("min_marginal_quality_gain"), default=0.0)
    return (
        f"max_outcomes_per_fixture={max_outcomes}|"
        f"min_marginal_quality_gain={min_gain:g}"
    )


def _constraint_profile_key(
    *,
    pass_type: str,
    mode: RecommendationMode | None,
    constraint_profile_id: str,
) -> str:
    return f"{pass_type}:{mode or 'any'}:{constraint_profile_id}"


def _summary_int(
    summary: Mapping[str, object],
    key: str,
    *,
    default: int,
) -> int:
    value = summary.get(key)
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _summary_float(
    summary: Mapping[str, object],
    key: str,
    *,
    default: float,
) -> float:
    value = summary.get(key)
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int | float | str):
        return _coerce_float(value, default=default)
    return default


def _coerce_float(value: object, *, default: float) -> float:
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int | float | str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _reason_codes(failed_checks: Sequence[str]) -> list[str]:
    if not failed_checks:
        return ["segment_gate_passed"]
    reasons: list[str] = []
    if "roi_delta" in failed_checks or "profit_loss_delta" in failed_checks:
        reasons.append("blocked_by_roi_profit_loss_no_harm_gate")
    quality_checks = {
        "final_hit_rate_delta",
        "brier_score_delta",
        "log_loss_delta",
        "mean_calibration_error_delta",
    }
    if any(check in quality_checks for check in failed_checks):
        reasons.append("blocked_by_probability_quality_gate")
    settlement_checks = {"roi_delta", "profit_loss_delta"}
    if any(
        check not in quality_checks | settlement_checks
        for check in failed_checks
    ):
        reasons.append("blocked_by_market_concentration_gate")
    return reasons


def _pass_type(report: HistoricalFinalAnswerMarketConcentrationAuditReport) -> str:
    pass_types = {
        sample.pass_type
        for sample in [*report.dynamic_mixed_slice_samples, *report.single_market_slice_samples]
        if sample.pass_type is not None
    }
    if len(pass_types) == 1:
        return next(iter(pass_types))
    return "unknown"


def _mode(
    report: HistoricalFinalAnswerMarketConcentrationAuditReport,
) -> RecommendationMode | None:
    modes = {
        sample.mode
        for sample in [*report.dynamic_mixed_slice_samples, *report.single_market_slice_samples]
        if sample.mode is not None
    }
    if len(modes) == 1:
        return next(iter(modes))
    return None


def _metric(summary: Mapping[str, object], key: str) -> float | None:
    value = summary.get(key)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        return float(value)
    return None


def _warnings(
    decisions: Sequence[HistoricalFinalAnswerMarketConcentrationSegmentDecision],
    *,
    min_promoted_segment_count: int,
    require_all_segments_passed: bool,
) -> list[str]:
    warnings: list[str] = []
    promoted_count = sum(
        1 for decision in decisions if decision.decision == "promote_candidate"
    )
    if promoted_count < min_promoted_segment_count:
        warnings.append("segment_gate:promoted_segment_count_below_threshold")
    if require_all_segments_passed and promoted_count != len(decisions):
        warnings.append("segment_gate:one_or_more_segments_blocked")
    for decision in decisions:
        if decision.decision == "block_segment":
            warnings.append(f"segment_gate:block:{decision.pass_type}")
    return _dedupe(warnings)


def _segment_gate_report_key(
    decisions: Sequence[HistoricalFinalAnswerMarketConcentrationSegmentDecision],
    *,
    options: HistoricalFinalAnswerMarketConcentrationSegmentGateOptions,
) -> str:
    payload = {
        "options": options.model_dump(mode="json"),
        "segments": [
            {
                "report_key": decision.report_key,
                "pass_type": decision.pass_type,
                "constraint_profile_key": decision.constraint_profile_key,
                "decision": decision.decision,
                "failed_checks": decision.failed_checks,
            }
            for decision in decisions
        ],
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_market_concentration_segment_gate:{digest}"


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Summarize pass-type segmented market-concentration admission reports."
        )
    )
    parser.add_argument("report_paths", nargs="+", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-promoted-segment-count", type=int, default=1)
    parser.add_argument("--require-all-segments-passed", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)
