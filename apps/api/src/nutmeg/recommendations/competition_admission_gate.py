from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

type CompetitionAdmissionDecision = Literal["accepted", "shadow_only", "rejected"]


class CompetitionAdmissionGateOptions(BaseModel):
    gate_id: str = "competition-admission-v3.1"
    min_final_hit_sample_size: int = Field(default=30, ge=1)
    min_final_hit_rate: float = Field(default=0.55, ge=0.0, le=1.0)
    min_roi: float = -0.30
    min_competition_roi: float = -0.50
    min_final_hit_rate_delta: float = 0.0
    max_feature_brier_delta: float = 0.0
    max_feature_log_loss_delta: float = 0.0
    max_feature_ece_delta: float = 0.0
    allow_feature_metric_regression_for_shadow: bool = True


class CompetitionAdmissionGateReport(BaseModel):
    report_key: str
    decision: CompetitionAdmissionDecision
    production_recommendation_allowed: bool
    training_pool_allowed: bool
    shadow_allowed: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_competition_admission_gate_report(
    *,
    final_answer_gate_report: Mapping[str, object],
    options: CompetitionAdmissionGateOptions | None = None,
    feature_learning_report: Mapping[str, object] | None = None,
    coverage_audit_report: Mapping[str, object] | None = None,
) -> CompetitionAdmissionGateReport:
    resolved_options = options or CompetitionAdmissionGateOptions()
    final_summary = _summary(final_answer_gate_report)
    feature_summary = _summary(feature_learning_report or {})
    coverage_summary = _summary(coverage_audit_report or {})

    blockers = _final_answer_blockers(final_summary, options=resolved_options)
    warnings = _feature_warnings(feature_summary, options=resolved_options)
    if not final_summary:
        blockers.append("missing_final_answer_gate_summary")

    sample_size = _int(final_summary.get("candidate_final_hit_sample_size"))
    if sample_size < resolved_options.min_final_hit_sample_size:
        decision: CompetitionAdmissionDecision = "rejected"
    elif blockers or (
        warnings and not resolved_options.allow_feature_metric_regression_for_shadow
    ):
        decision = "shadow_only"
    else:
        decision = "accepted"

    production_allowed = decision == "accepted"
    training_allowed = decision == "accepted"
    shadow_allowed = decision in {"accepted", "shadow_only"}
    report_key = _report_key(
        gate_id=resolved_options.gate_id,
        final_summary=final_summary,
        feature_summary=feature_summary,
        coverage_summary=coverage_summary,
        decision=decision,
        blockers=blockers,
        warnings=warnings,
    )
    summary: dict[str, object] = {
        "calculation_basis": "competition_admission_gate_v3_1",
        "gate_id": resolved_options.gate_id,
        "decision": decision,
        "production_recommendation_allowed": production_allowed,
        "training_pool_allowed": training_allowed,
        "shadow_allowed": shadow_allowed,
        "blockers": blockers,
        "warnings": warnings,
        "final_answer_gate_key": final_summary.get("gate_key"),
        "final_answer_gate_passed": final_summary.get("passed"),
        "suite_status": final_summary.get("suite_status"),
        "candidate_final_hit_sample_size": sample_size,
        "candidate_final_hit_rate": final_summary.get("candidate_final_hit_rate"),
        "candidate_roi": final_summary.get("candidate_roi"),
        "worst_competition_id": final_summary.get("worst_competition_id"),
        "worst_competition_candidate_roi": final_summary.get(
            "worst_competition_candidate_roi"
        ),
        "final_hit_rate_delta": _delta(final_summary, "final_hit_rate_delta"),
        "roi_delta": _delta(final_summary, "roi_delta"),
        "feature_learning_report_key": feature_summary.get("report_key"),
        "feature_brier_score_delta": _delta(feature_summary, "brier_score_delta"),
        "feature_log_loss_delta": _delta(feature_summary, "log_loss_delta"),
        "feature_expected_calibration_error_delta": _delta(
            feature_summary,
            "expected_calibration_error_delta",
        ),
        "allow_feature_metric_regression_for_shadow": (
            resolved_options.allow_feature_metric_regression_for_shadow
        ),
        "coverage_audit_key": coverage_summary.get("audit_key"),
        "coverage_slice_count": coverage_summary.get("slice_count"),
        "coverage_fixture_count": coverage_summary.get("fixture_count"),
        "market_feature_ready_source_ids": coverage_summary.get(
            "market_feature_ready_source_ids",
            [],
        ),
    }
    return CompetitionAdmissionGateReport(
        report_key=report_key,
        decision=decision,
        production_recommendation_allowed=production_allowed,
        training_pool_allowed=training_allowed,
        shadow_allowed=shadow_allowed,
        blockers=blockers,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_competition_admission_gate_report(
        final_answer_gate_report=_load_json(args.final_answer_gate_report),
        feature_learning_report=(
            _load_json(args.feature_learning_report)
            if args.feature_learning_report is not None
            else None
        ),
        coverage_audit_report=(
            _load_json(args.coverage_audit_report)
            if args.coverage_audit_report is not None
            else None
        ),
        options=_options_from_args(args),
    )
    if args.output_path is not None:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(
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
    if not report.production_recommendation_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _final_answer_blockers(
    summary: Mapping[str, object],
    *,
    options: CompetitionAdmissionGateOptions,
) -> list[str]:
    blockers: list[str] = []
    if summary.get("passed") is not True:
        blockers.append("final_answer_gate_not_passed")
    if summary.get("suite_status") in {"regressed", "mixed"}:
        blockers.append(f"suite_status_{summary.get('suite_status')}")
    if _int(summary.get("candidate_final_hit_sample_size")) < options.min_final_hit_sample_size:
        blockers.append("final_hit_sample_size_below_threshold")
    if _float(summary.get("candidate_final_hit_rate")) < options.min_final_hit_rate:
        blockers.append("candidate_final_hit_rate_below_threshold")
    if _float(summary.get("candidate_roi")) < options.min_roi:
        blockers.append("candidate_roi_below_threshold")
    if _float(summary.get("worst_competition_candidate_roi")) < options.min_competition_roi:
        blockers.append("competition_roi_below_threshold")
    if _delta(summary, "final_hit_rate_delta") < options.min_final_hit_rate_delta:
        blockers.append("final_hit_rate_delta_below_threshold")
    failed_checks = summary.get("failed_checks")
    if isinstance(failed_checks, list):
        for check in failed_checks:
            if isinstance(check, str):
                blockers.append(f"failed_check:{check}")
    return _unique(blockers)


def _feature_warnings(
    summary: Mapping[str, object],
    *,
    options: CompetitionAdmissionGateOptions,
) -> list[str]:
    if not summary:
        return []
    warnings: list[str] = []
    if _delta(summary, "brier_score_delta") > options.max_feature_brier_delta:
        warnings.append("feature_brier_score_regressed")
    if _delta(summary, "log_loss_delta") > options.max_feature_log_loss_delta:
        warnings.append("feature_log_loss_regressed")
    if (
        _delta(summary, "expected_calibration_error_delta")
        > options.max_feature_ece_delta
    ):
        warnings.append("feature_expected_calibration_error_regressed")
    return warnings


def _summary(report: Mapping[str, object]) -> Mapping[str, object]:
    summary = report.get("summary_json")
    return summary if isinstance(summary, Mapping) else report


def _delta(summary: Mapping[str, object], key: str) -> float:
    deltas = summary.get("overall_validation_deltas_json")
    if isinstance(deltas, Mapping) and key in deltas:
        return _float(deltas.get(key))
    aggregate = summary.get("aggregate_deltas")
    if isinstance(aggregate, Mapping) and key in aggregate:
        return _float(aggregate.get(key))
    return _float(summary.get(key))


def _float(value: object) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _int(value: object) -> int:
    return int(_float(value))


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value not in seen:
            unique_values.append(value)
            seen.add(value)
    return unique_values


def _report_key(
    *,
    gate_id: str,
    final_summary: Mapping[str, object],
    feature_summary: Mapping[str, object],
    coverage_summary: Mapping[str, object],
    decision: CompetitionAdmissionDecision,
    blockers: Sequence[str],
    warnings: Sequence[str],
) -> str:
    payload = dumps(
        {
            "gate_id": gate_id,
            "final_summary": final_summary,
            "feature_summary": feature_summary,
            "coverage_summary": coverage_summary,
            "decision": decision,
            "blockers": list(blockers),
            "warnings": list(warnings),
        },
        sort_keys=True,
        default=str,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"competition_admission_gate:{digest}"


def _load_json(path: Path) -> dict[str, object]:
    payload = loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Gate new competition suites before they enter default recommendations."
    )
    parser.add_argument("--final-answer-gate-report", type=Path, required=True)
    parser.add_argument("--feature-learning-report", type=Path)
    parser.add_argument("--coverage-audit-report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--gate-id", default="competition-admission-v3.1")
    parser.add_argument("--min-final-hit-sample-size", type=int, default=30)
    parser.add_argument("--min-final-hit-rate", type=float, default=0.55)
    parser.add_argument("--min-roi", type=float, default=-0.30)
    parser.add_argument("--min-competition-roi", type=float, default=-0.50)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-feature-brier-delta", type=float, default=0.0)
    parser.add_argument("--max-feature-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-feature-ece-delta", type=float, default=0.0)
    parser.add_argument(
        "--block-feature-regression",
        action="store_true",
        help="Keep the suite shadow-only when feature learning metrics regress.",
    )
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> CompetitionAdmissionGateOptions:
    return CompetitionAdmissionGateOptions(
        gate_id=args.gate_id,
        min_final_hit_sample_size=args.min_final_hit_sample_size,
        min_final_hit_rate=args.min_final_hit_rate,
        min_roi=args.min_roi,
        min_competition_roi=args.min_competition_roi,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        max_feature_brier_delta=args.max_feature_brier_delta,
        max_feature_log_loss_delta=args.max_feature_log_loss_delta,
        max_feature_ece_delta=args.max_feature_ece_delta,
        allow_feature_metric_regression_for_shadow=not args.block_feature_regression,
    )
