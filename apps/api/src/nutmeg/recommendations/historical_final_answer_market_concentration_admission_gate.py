from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_final_answer_market_concentration_audit import (
    HistoricalFinalAnswerMarketConcentrationAuditReport,
)
from nutmeg.recommendations.historical_final_answer_market_concentration_segment_gate import (
    HistoricalFinalAnswerMarketConcentrationConstraintProfile,
    HistoricalFinalAnswerMarketConcentrationSegmentGateReport,
)

type AdmissionGateStatus = Literal["passed", "failed"]
type AdmissionGateCheckStatus = Literal["passed", "failed", "skipped"]


class HistoricalFinalAnswerMarketConcentrationAdmissionGateOptions(BaseModel):
    requested_pass_types: tuple[str, ...] = ()
    constraint_profile_admission: bool = False
    min_admitted_pass_type_count: int = Field(default=1, ge=0)
    require_segment_gate_passed: bool = True
    require_bounded_admission_smoke: bool = False
    min_bounded_smoke_slice_count: int = Field(default=0, ge=0)
    min_bounded_smoke_dynamic_mixed_final_answer_count: int = Field(default=0, ge=0)
    min_bounded_smoke_multiple_choice_final_answer_count: int = Field(default=0, ge=0)
    require_bounded_smoke_effective_pass_types_match_admitted: bool = True


class HistoricalFinalAnswerMarketConcentrationAdmissionGateCheck(BaseModel):
    name: str
    status: AdmissionGateCheckStatus
    actual: object = None
    threshold: object = None
    detail: str


class HistoricalFinalAnswerMarketConcentrationAdmissionGateReport(BaseModel):
    report_key: str
    status: AdmissionGateStatus
    passed: bool
    segment_gate_report_key: str
    segment_gate_report_path: str | None = None
    bounded_admission_report_key: str | None = None
    bounded_admission_report_path: str | None = None
    requested_pass_types: list[str] = Field(default_factory=list)
    admitted_pass_types: list[str] = Field(default_factory=list)
    blocked_pass_types: list[str] = Field(default_factory=list)
    effective_pass_types: list[str] = Field(default_factory=list)
    constraint_profile_admission: bool = False
    admitted_constraint_profiles: list[dict[str, object]] = Field(default_factory=list)
    blocked_constraint_profiles: list[dict[str, object]] = Field(default_factory=list)
    effective_constraint_profiles: list[dict[str, object]] = Field(default_factory=list)
    checks: list[HistoricalFinalAnswerMarketConcentrationAdmissionGateCheck] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_final_answer_market_concentration_admission_gate(
    segment_gate_report: HistoricalFinalAnswerMarketConcentrationSegmentGateReport,
    *,
    segment_gate_report_path: Path | str | None = None,
    bounded_admission_report: HistoricalFinalAnswerMarketConcentrationAuditReport
    | None = None,
    bounded_admission_report_path: Path | str | None = None,
    options: HistoricalFinalAnswerMarketConcentrationAdmissionGateOptions
    | None = None,
) -> HistoricalFinalAnswerMarketConcentrationAdmissionGateReport:
    resolved_options = (
        options or HistoricalFinalAnswerMarketConcentrationAdmissionGateOptions()
    )
    requested_pass_types = _requested_pass_types(
        resolved_options.requested_pass_types,
        segment_gate_report=segment_gate_report,
    )
    admitted_profiles = _constraint_profiles(segment_gate_report, promoted=True)
    blocked_profiles = _constraint_profiles(segment_gate_report, promoted=False)
    if resolved_options.constraint_profile_admission:
        effective_profiles = [
            profile
            for profile in admitted_profiles
            if profile.pass_type in requested_pass_types
            and profile.profile_key
            not in {blocked.profile_key for blocked in blocked_profiles}
        ]
        admitted_pass_types = _dedupe(
            [profile.pass_type for profile in admitted_profiles]
        )
        blocked_pass_types = _dedupe([profile.pass_type for profile in blocked_profiles])
        effective_pass_types = _dedupe(
            [profile.pass_type for profile in effective_profiles]
        )
    else:
        admitted_pass_types = _dedupe(segment_gate_report.promoted_pass_types)
        blocked_pass_types = _dedupe(segment_gate_report.blocked_pass_types)
        effective_pass_types = [
            pass_type
            for pass_type in requested_pass_types
            if pass_type in admitted_pass_types and pass_type not in blocked_pass_types
        ]
        effective_profiles = [
            profile
            for profile in admitted_profiles
            if profile.pass_type in effective_pass_types
        ]
    checks = _checks(
        segment_gate_report,
        bounded_admission_report,
        requested_pass_types=requested_pass_types,
        admitted_pass_types=admitted_pass_types,
        blocked_pass_types=blocked_pass_types,
        effective_pass_types=effective_pass_types,
        admitted_constraint_profiles=admitted_profiles,
        blocked_constraint_profiles=blocked_profiles,
        effective_constraint_profiles=effective_profiles,
        options=resolved_options,
    )
    passed = not any(check.status == "failed" for check in checks)
    report_key = _report_key(
        segment_gate_report,
        bounded_admission_report,
        requested_pass_types=requested_pass_types,
        effective_pass_types=effective_pass_types,
        effective_constraint_profiles=effective_profiles,
        options=resolved_options,
    )
    warnings = _warnings(
        segment_gate_report,
        requested_pass_types=requested_pass_types,
        admitted_pass_types=admitted_pass_types,
        blocked_pass_types=blocked_pass_types,
        effective_pass_types=effective_pass_types,
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_final_answer_market_concentration_admission_gate_v3_1"
        ),
        "report_key": report_key,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "segment_gate_report_key": segment_gate_report.report_key,
        "segment_gate_report_path": (
            str(segment_gate_report_path)
            if segment_gate_report_path is not None
            else None
        ),
        "bounded_admission_report_key": (
            bounded_admission_report.report_key
            if bounded_admission_report is not None
            else None
        ),
        "bounded_admission_report_path": (
            str(bounded_admission_report_path)
            if bounded_admission_report_path is not None
            else None
        ),
        "requested_pass_types": requested_pass_types,
        "admitted_pass_types": admitted_pass_types,
        "blocked_pass_types": blocked_pass_types,
        "effective_pass_types": effective_pass_types,
        "constraint_profile_admission": resolved_options.constraint_profile_admission,
        "admitted_constraint_profiles": [
            profile.model_dump(mode="json") for profile in admitted_profiles
        ],
        "blocked_constraint_profiles": [
            profile.model_dump(mode="json") for profile in blocked_profiles
        ],
        "effective_constraint_profiles": [
            profile.model_dump(mode="json") for profile in effective_profiles
        ],
        "failed_checks": [check.name for check in checks if check.status == "failed"],
        "warnings": warnings,
    }
    return HistoricalFinalAnswerMarketConcentrationAdmissionGateReport(
        report_key=report_key,
        status="passed" if passed else "failed",
        passed=passed,
        segment_gate_report_key=segment_gate_report.report_key,
        segment_gate_report_path=(
            str(segment_gate_report_path)
            if segment_gate_report_path is not None
            else None
        ),
        bounded_admission_report_key=(
            bounded_admission_report.report_key
            if bounded_admission_report is not None
            else None
        ),
        bounded_admission_report_path=(
            str(bounded_admission_report_path)
            if bounded_admission_report_path is not None
            else None
        ),
        requested_pass_types=requested_pass_types,
        admitted_pass_types=admitted_pass_types,
        blocked_pass_types=blocked_pass_types,
        effective_pass_types=effective_pass_types,
        constraint_profile_admission=resolved_options.constraint_profile_admission,
        admitted_constraint_profiles=[
            profile.model_dump(mode="json") for profile in admitted_profiles
        ],
        blocked_constraint_profiles=[
            profile.model_dump(mode="json") for profile in blocked_profiles
        ],
        effective_constraint_profiles=[
            profile.model_dump(mode="json") for profile in effective_profiles
        ],
        checks=checks,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    segment_gate_report = _load_segment_gate_report(args.segment_gate_report_path)
    bounded_admission_report = (
        _load_audit_report(args.bounded_admission_report_path)
        if args.bounded_admission_report_path is not None
        else None
    )
    report = build_historical_final_answer_market_concentration_admission_gate(
        segment_gate_report,
        segment_gate_report_path=args.segment_gate_report_path,
        bounded_admission_report=bounded_admission_report,
        bounded_admission_report_path=args.bounded_admission_report_path,
        options=HistoricalFinalAnswerMarketConcentrationAdmissionGateOptions(
            requested_pass_types=tuple(_csv(args.requested_pass_types)),
            min_admitted_pass_type_count=args.min_admitted_pass_type_count,
            constraint_profile_admission=args.constraint_profile_admission,
            require_segment_gate_passed=not args.allow_failed_segment_gate,
            require_bounded_admission_smoke=args.require_bounded_admission_smoke,
            min_bounded_smoke_slice_count=args.min_bounded_smoke_slice_count,
            min_bounded_smoke_dynamic_mixed_final_answer_count=(
                args.min_bounded_smoke_dynamic_mixed_final_answer_count
            ),
            min_bounded_smoke_multiple_choice_final_answer_count=(
                args.min_bounded_smoke_multiple_choice_final_answer_count
            ),
            require_bounded_smoke_effective_pass_types_match_admitted=(
                not args.allow_smoke_effective_pass_type_mismatch
            ),
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


def _checks(
    segment_gate_report: HistoricalFinalAnswerMarketConcentrationSegmentGateReport,
    bounded_admission_report: HistoricalFinalAnswerMarketConcentrationAuditReport
    | None,
    *,
    requested_pass_types: Sequence[str],
    admitted_pass_types: Sequence[str],
    blocked_pass_types: Sequence[str],
    effective_pass_types: Sequence[str],
    admitted_constraint_profiles: Sequence[
        HistoricalFinalAnswerMarketConcentrationConstraintProfile
    ],
    blocked_constraint_profiles: Sequence[
        HistoricalFinalAnswerMarketConcentrationConstraintProfile
    ],
    effective_constraint_profiles: Sequence[
        HistoricalFinalAnswerMarketConcentrationConstraintProfile
    ],
    options: HistoricalFinalAnswerMarketConcentrationAdmissionGateOptions,
) -> list[HistoricalFinalAnswerMarketConcentrationAdmissionGateCheck]:
    checks: list[HistoricalFinalAnswerMarketConcentrationAdmissionGateCheck] = []
    checks.append(
        _check(
            "segment_gate_passed",
            passed=segment_gate_report.passed or not options.require_segment_gate_passed,
            actual=segment_gate_report.status,
            threshold="passed",
            detail="The source segment gate must pass before admission is allowed.",
        )
    )
    checks.append(
        _check(
            "admitted_pass_type_count",
            passed=len(effective_pass_types) >= options.min_admitted_pass_type_count,
            actual=len(effective_pass_types),
            threshold=options.min_admitted_pass_type_count,
            detail="At least the configured number of requested pass types must be admitted.",
        )
    )
    blocked_effective = [
        pass_type for pass_type in effective_pass_types if pass_type in blocked_pass_types
    ] if not options.constraint_profile_admission else []
    checks.append(
        _check(
            "blocked_pass_type_exclusion",
            passed=not blocked_effective,
            actual=blocked_effective,
            threshold=[],
            detail="Blocked pass types must not be present in the effective admission set.",
        )
    )
    blocked_profile_keys = {profile.profile_key for profile in blocked_constraint_profiles}
    blocked_effective_profiles = [
        profile.profile_key
        for profile in effective_constraint_profiles
        if profile.profile_key in blocked_profile_keys
    ]
    checks.append(
        _check(
            "blocked_constraint_profile_exclusion",
            passed=not blocked_effective_profiles,
            actual=blocked_effective_profiles,
            threshold=[],
            detail=(
                "Blocked constraint profiles must not be present in the effective "
                "admission set."
            ),
        )
    )
    uncovered_requested = [
        pass_type
        for pass_type in requested_pass_types
        if pass_type not in admitted_pass_types
        and pass_type not in blocked_pass_types
        and not any(
            profile.pass_type == pass_type
            for profile in [
                *admitted_constraint_profiles,
                *blocked_constraint_profiles,
            ]
        )
    ]
    checks.append(
        _check(
            "requested_pass_type_coverage",
            passed=not uncovered_requested,
            actual=uncovered_requested,
            threshold=[],
            detail="Every requested pass type should be covered by the segment gate.",
        )
    )
    smoke_checks = _bounded_smoke_checks(
        bounded_admission_report,
        effective_pass_types=effective_pass_types,
        options=options,
    )
    checks.extend(smoke_checks)
    return checks


def _bounded_smoke_checks(
    report: HistoricalFinalAnswerMarketConcentrationAuditReport | None,
    *,
    effective_pass_types: Sequence[str],
    options: HistoricalFinalAnswerMarketConcentrationAdmissionGateOptions,
) -> list[HistoricalFinalAnswerMarketConcentrationAdmissionGateCheck]:
    if report is None:
        status: AdmissionGateCheckStatus = (
            "failed" if options.require_bounded_admission_smoke else "skipped"
        )
        return [
            HistoricalFinalAnswerMarketConcentrationAdmissionGateCheck(
                name="bounded_admission_smoke_present",
                status=status,
                actual=False,
                threshold=options.require_bounded_admission_smoke,
                detail="A bounded combined admission smoke report is optional unless required.",
            )
        ]
    smoke_effective_pass_types = _string_list(
        report.summary_json.get("dynamic_mix_final_answer_lane_effective_pass_types")
    )
    return [
        _check(
            "bounded_admission_smoke_present",
            passed=True,
            actual=True,
            threshold=True,
            detail="A bounded combined admission smoke report was provided.",
        ),
        _check(
            "bounded_admission_smoke_passed",
            passed=report.passed,
            actual=report.status,
            threshold="passed",
            detail="The bounded smoke must pass its own market concentration checks.",
        ),
        _check(
            "bounded_admission_smoke_slice_count",
            passed=report.slice_count >= options.min_bounded_smoke_slice_count,
            actual=report.slice_count,
            threshold=options.min_bounded_smoke_slice_count,
            detail="The bounded smoke must include enough historical slices.",
        ),
        _check(
            "bounded_admission_smoke_dynamic_mixed_final_answer_count",
            passed=(
                report.dynamic_mixed_final_answer_count
                >= options.min_bounded_smoke_dynamic_mixed_final_answer_count
            ),
            actual=report.dynamic_mixed_final_answer_count,
            threshold=options.min_bounded_smoke_dynamic_mixed_final_answer_count,
            detail="The bounded smoke must produce enough dynamic mixed final answers.",
        ),
        _check(
            "bounded_admission_smoke_multiple_choice_final_answer_count",
            passed=(
                report.multiple_choice_final_answer_count
                >= options.min_bounded_smoke_multiple_choice_final_answer_count
            ),
            actual=report.multiple_choice_final_answer_count,
            threshold=options.min_bounded_smoke_multiple_choice_final_answer_count,
            detail="The bounded smoke must produce enough multiple-choice final answers.",
        ),
        _check(
            "bounded_admission_smoke_effective_pass_types",
            passed=(
                not options.require_bounded_smoke_effective_pass_types_match_admitted
                or smoke_effective_pass_types == list(effective_pass_types)
            ),
            actual=smoke_effective_pass_types,
            threshold=list(effective_pass_types),
            detail=(
                "The bounded smoke must only run the same effective pass types "
                "admitted by the segment gate."
            ),
        ),
    ]


def _check(
    name: str,
    *,
    passed: bool,
    actual: object,
    threshold: object,
    detail: str,
) -> HistoricalFinalAnswerMarketConcentrationAdmissionGateCheck:
    return HistoricalFinalAnswerMarketConcentrationAdmissionGateCheck(
        name=name,
        status="passed" if passed else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _warnings(
    segment_gate_report: HistoricalFinalAnswerMarketConcentrationSegmentGateReport,
    *,
    requested_pass_types: Sequence[str],
    admitted_pass_types: Sequence[str],
    blocked_pass_types: Sequence[str],
    effective_pass_types: Sequence[str],
) -> list[str]:
    warnings = list(segment_gate_report.warnings)
    if blocked_pass_types:
        warnings.append(
            "admission_gate:blocked_pass_types:"
            + ",".join(blocked_pass_types)
        )
    uncovered_requested = [
        pass_type
        for pass_type in requested_pass_types
        if pass_type not in admitted_pass_types and pass_type not in blocked_pass_types
    ]
    for pass_type in uncovered_requested:
        warnings.append(f"admission_gate:requested_pass_type_not_covered:{pass_type}")
    if not effective_pass_types:
        warnings.append("admission_gate:no_effective_pass_types")
    return _dedupe(warnings)


def _requested_pass_types(
    requested: Sequence[str],
    *,
    segment_gate_report: HistoricalFinalAnswerMarketConcentrationSegmentGateReport,
) -> list[str]:
    if requested:
        return _dedupe(requested)
    return _dedupe(
        [
            *segment_gate_report.promoted_pass_types,
            *segment_gate_report.blocked_pass_types,
        ]
    )


def _constraint_profiles(
    segment_gate_report: HistoricalFinalAnswerMarketConcentrationSegmentGateReport,
    *,
    promoted: bool,
) -> list[HistoricalFinalAnswerMarketConcentrationConstraintProfile]:
    profiles = (
        segment_gate_report.promoted_constraint_profiles
        if promoted
        else segment_gate_report.blocked_constraint_profiles
    )
    if profiles:
        return list(profiles)
    decision_name = "promote_candidate" if promoted else "block_segment"
    return [
        HistoricalFinalAnswerMarketConcentrationConstraintProfile(
            profile_key=decision.constraint_profile_key
            or (
                f"{decision.pass_type}:{decision.mode or 'any'}:"
                f"{decision.constraint_profile_id}"
            ),
            pass_type=decision.pass_type,
            mode=decision.mode,
            constraint_profile_id=decision.constraint_profile_id,
            constraint_profile_json=dict(decision.constraint_profile_json),
        )
        for decision in segment_gate_report.decisions
        if decision.decision == decision_name
    ]


def _report_key(
    segment_gate_report: HistoricalFinalAnswerMarketConcentrationSegmentGateReport,
    bounded_admission_report: HistoricalFinalAnswerMarketConcentrationAuditReport
    | None,
    *,
    requested_pass_types: Sequence[str],
    effective_pass_types: Sequence[str],
    effective_constraint_profiles: Sequence[
        HistoricalFinalAnswerMarketConcentrationConstraintProfile
    ],
    options: HistoricalFinalAnswerMarketConcentrationAdmissionGateOptions,
) -> str:
    payload = {
        "bounded_admission_report_key": (
            bounded_admission_report.report_key
            if bounded_admission_report is not None
            else None
        ),
        "effective_pass_types": list(effective_pass_types),
        "effective_constraint_profile_keys": [
            profile.profile_key for profile in effective_constraint_profiles
        ],
        "options": options.model_dump(mode="json"),
        "requested_pass_types": list(requested_pass_types),
        "segment_gate_report_key": segment_gate_report.report_key,
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_market_concentration_admission_gate:{digest}"


def _load_segment_gate_report(
    path: Path,
) -> HistoricalFinalAnswerMarketConcentrationSegmentGateReport:
    return HistoricalFinalAnswerMarketConcentrationSegmentGateReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_audit_report(path: Path) -> HistoricalFinalAnswerMarketConcentrationAuditReport:
    return HistoricalFinalAnswerMarketConcentrationAuditReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item)]


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
            "Build a lightweight admission gate from market-concentration segment "
            "evidence and an optional bounded combined smoke report."
        )
    )
    parser.add_argument("--segment-gate-report-path", required=True, type=Path)
    parser.add_argument("--bounded-admission-report-path", type=Path)
    parser.add_argument("--requested-pass-types", default="")
    parser.add_argument("--constraint-profile-admission", action="store_true")
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-admitted-pass-type-count", type=int, default=1)
    parser.add_argument("--allow-failed-segment-gate", action="store_true")
    parser.add_argument("--require-bounded-admission-smoke", action="store_true")
    parser.add_argument("--min-bounded-smoke-slice-count", type=int, default=0)
    parser.add_argument(
        "--min-bounded-smoke-dynamic-mixed-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-bounded-smoke-multiple-choice-final-answer-count",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--allow-smoke-effective-pass-type-mismatch",
        action="store_true",
    )
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)
