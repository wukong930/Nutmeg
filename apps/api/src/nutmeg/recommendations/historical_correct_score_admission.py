from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateResult,
)

type HistoricalCorrectScoreAdmissionStatus = Literal[
    "accepted",
    "holdout_only",
    "rejected",
]
type HistoricalCorrectScoreAdmissionCheckStatus = Literal["passed", "failed"]


class HistoricalCorrectScoreAdmissionOptions(BaseModel):
    min_slice_count: int = Field(default=1, ge=0)
    min_comparison_count: int = Field(default=1, ge=0)
    min_final_hit_sample_size: int = Field(default=1, ge=0)
    min_candidate_final_hit_coverage_ratio: float | None = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )
    min_candidate_final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    min_candidate_roi: float | None = 0.0
    min_candidate_correct_score_final_answer_count: int = Field(default=1, ge=0)
    min_candidate_correct_score_final_answer_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    min_final_hit_rate_delta: float | None = 0.0
    min_roi_delta: float | None = 0.0
    min_profit_loss_delta: float | None = 0.0
    max_brier_score_delta: float | None = 0.0
    max_log_loss_delta: float | None = 0.0
    max_mean_calibration_error_delta: float | None = 0.0
    max_failed_check_count: int | None = Field(default=0, ge=0)
    require_source_gate_passed: bool = True
    fail_on_suite_statuses: tuple[str, ...] = ("regressed", "mixed", "failed")
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True


class HistoricalCorrectScoreAdmissionCheck(BaseModel):
    name: str
    status: HistoricalCorrectScoreAdmissionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalCorrectScoreAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalCorrectScoreAdmissionStatus
    production_recommendation_allowed: bool
    holdout_allowed: bool
    source_gate_key: str
    source_gate_status: str
    source_suite_status: str
    slice_count: int = Field(ge=0)
    comparison_count: int = Field(ge=0)
    candidate_final_hit_sample_size: int = Field(ge=0)
    candidate_final_hit_coverage_ratio: float | None = None
    candidate_final_hit_rate: float | None = None
    candidate_roi: float | None = None
    candidate_correct_score_final_answer_count: int = Field(ge=0)
    candidate_correct_score_final_answer_rate: float | None = None
    final_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    no_harm_delta_basis: str = "aggregate_deltas"
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    checks: list[HistoricalCorrectScoreAdmissionCheck] = Field(default_factory=list)
    decision_payload_json: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_correct_score_source_gate_report(
    path: Path | str,
) -> HistoricalRecommendationSuiteQualityGateResult:
    return HistoricalRecommendationSuiteQualityGateResult.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_historical_correct_score_admission_report(
    path: Path | str,
) -> HistoricalCorrectScoreAdmissionReport:
    return HistoricalCorrectScoreAdmissionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_correct_score_admission_report(
    source_gate: HistoricalRecommendationSuiteQualityGateResult,
    *,
    options: HistoricalCorrectScoreAdmissionOptions | None = None,
) -> HistoricalCorrectScoreAdmissionReport:
    resolved_options = options or HistoricalCorrectScoreAdmissionOptions()
    metrics = _metrics(source_gate)
    checks = _checks(source_gate, metrics=metrics, options=resolved_options)
    source_passed = _source_checks_passed(checks)
    no_harm_passed = _no_harm_checks_passed(checks)
    admission_evidence_passed = _admission_evidence_checks_passed(checks)
    production_allowed = source_passed and no_harm_passed and admission_evidence_passed
    holdout_allowed = source_passed and no_harm_passed
    status = _status(
        production_allowed=production_allowed,
        holdout_allowed=holdout_allowed,
    )
    decision_payload = _decision_payload(
        source_gate,
        metrics=metrics,
        status=status,
        production_allowed=production_allowed,
        holdout_allowed=holdout_allowed,
        options=resolved_options,
    )
    warnings = _warnings(status=status, checks=checks)
    summary: dict[str, object] = {
        "calculation_basis": "historical_correct_score_admission_v3_2",
        "status": status,
        "production_recommendation_allowed": production_allowed,
        "holdout_allowed": holdout_allowed,
        "source_gate_key": source_gate.gate_key,
        "source_gate_status": source_gate.status,
        "source_suite_status": source_gate.suite_status,
        **metrics,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, decision_payload)
    return HistoricalCorrectScoreAdmissionReport(
        report_key=report_key,
        status=status,
        production_recommendation_allowed=production_allowed,
        holdout_allowed=holdout_allowed,
        source_gate_key=source_gate.gate_key,
        source_gate_status=source_gate.status,
        source_suite_status=source_gate.suite_status,
        slice_count=_int(metrics["slice_count"]),
        comparison_count=_int(metrics["comparison_count"]),
        candidate_final_hit_sample_size=_int(
            metrics["candidate_final_hit_sample_size"]
        ),
        candidate_final_hit_coverage_ratio=_optional_float(
            metrics["candidate_final_hit_coverage_ratio"]
        ),
        candidate_final_hit_rate=_optional_float(metrics["candidate_final_hit_rate"]),
        candidate_roi=_optional_float(metrics["candidate_roi"]),
        candidate_correct_score_final_answer_count=_int(
            metrics["candidate_correct_score_final_answer_count"]
        ),
        candidate_correct_score_final_answer_rate=_optional_float(
            metrics["candidate_correct_score_final_answer_rate"]
        ),
        final_hit_rate_delta=_optional_float(metrics["final_hit_rate_delta"]),
        roi_delta=_optional_float(metrics["roi_delta"]),
        profit_loss_delta=_optional_float(metrics["profit_loss_delta"]),
        brier_score_delta=_optional_float(metrics["brier_score_delta"]),
        log_loss_delta=_optional_float(metrics["log_loss_delta"]),
        mean_calibration_error_delta=_optional_float(
            metrics["mean_calibration_error_delta"]
        ),
        no_harm_delta_basis=str(metrics["no_harm_delta_basis"]),
        production_recommendation_changed=False,
        public_response_changed=False,
        checks=checks,
        decision_payload_json=decision_payload,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_correct_score_admission_report(
        load_historical_correct_score_source_gate_report(args.source_gate_report),
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


def _metrics(
    source_gate: HistoricalRecommendationSuiteQualityGateResult,
) -> dict[str, object]:
    summary = source_gate.summary_json
    no_harm_deltas = _no_harm_deltas(source_gate)
    comparison_count = _summary_int(summary, "comparison_count")
    correct_score_count = _summary_int(
        summary,
        "candidate_correct_score_final_answer_count",
    )
    return {
        "slice_count": _summary_int(summary, "slice_count"),
        "comparison_count": comparison_count,
        "candidate_final_hit_sample_size": _summary_int(
            summary,
            "candidate_final_hit_sample_size",
        ),
        "candidate_final_hit_coverage_ratio": _summary_float(
            summary,
            "candidate_final_hit_coverage_ratio",
        ),
        "candidate_final_hit_rate": _summary_float(
            summary,
            "candidate_final_hit_rate",
        ),
        "candidate_roi": _summary_float(summary, "candidate_roi"),
        "candidate_correct_score_final_answer_count": correct_score_count,
        "candidate_correct_score_final_answer_rate": _ratio(
            correct_score_count,
            comparison_count,
        ),
        "source_failed_check_count": _source_failed_check_count(source_gate),
        "final_hit_rate_delta": _summary_float(
            no_harm_deltas.values,
            "final_hit_rate_delta",
        ),
        "roi_delta": _summary_float(no_harm_deltas.values, "roi_delta"),
        "profit_loss_delta": _summary_float(
            no_harm_deltas.values,
            "profit_loss_delta",
        ),
        "brier_score_delta": _summary_float(
            no_harm_deltas.values,
            "brier_score_delta",
        ),
        "log_loss_delta": _summary_float(no_harm_deltas.values, "log_loss_delta"),
        "mean_calibration_error_delta": _summary_float(
            no_harm_deltas.values,
            "mean_calibration_error_delta",
        ),
        "no_harm_delta_basis": no_harm_deltas.basis,
    }


def _aggregate_deltas(
    source_gate: HistoricalRecommendationSuiteQualityGateResult,
) -> dict[str, object]:
    if source_gate.aggregate_deltas_json:
        return dict(source_gate.aggregate_deltas_json)
    value = source_gate.summary_json.get("aggregate_deltas", {})
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


class _NoHarmDeltas(BaseModel):
    basis: str
    values: dict[str, object]


def _no_harm_deltas(
    source_gate: HistoricalRecommendationSuiteQualityGateResult,
) -> _NoHarmDeltas:
    if source_gate.summary_json.get(
        "profile_reference_correct_score_final_answer_lane_disabled"
    ) is True:
        value = source_gate.summary_json.get("profile_reference_deltas", {})
        if isinstance(value, Mapping):
            return _NoHarmDeltas(
                basis="profile_reference_deltas",
                values={str(key): item for key, item in value.items()},
            )
    return _NoHarmDeltas(
        basis="aggregate_deltas",
        values=_aggregate_deltas(source_gate),
    )


def _checks(
    source_gate: HistoricalRecommendationSuiteQualityGateResult,
    *,
    metrics: Mapping[str, object],
    options: HistoricalCorrectScoreAdmissionOptions,
) -> list[HistoricalCorrectScoreAdmissionCheck]:
    suite_status_allowed = source_gate.suite_status not in options.fail_on_suite_statuses
    return [
        _boolean_check(
            "source_gate_passed",
            source_gate.passed,
            enabled=options.require_source_gate_passed,
            detail="derived-market suite quality gate must be passed",
        ),
        _maximum_check(
            "source_failed_check_count",
            _optional_float(metrics["source_failed_check_count"]),
            options.max_failed_check_count,
            detail="source quality gate should not contain failed checks",
        ),
        _boolean_check(
            "suite_status_allowed",
            suite_status_allowed,
            enabled=bool(options.fail_on_suite_statuses),
            detail="source suite status must not be a blocked status",
        ),
        _minimum_check(
            "slice_count",
            _optional_float(metrics["slice_count"]),
            options.min_slice_count,
            detail="correct-score admission needs enough historical slices",
        ),
        _minimum_check(
            "comparison_count",
            _optional_float(metrics["comparison_count"]),
            options.min_comparison_count,
            detail="correct-score admission needs enough historical comparisons",
        ),
        _minimum_check(
            "candidate_final_hit_sample_size",
            _optional_float(metrics["candidate_final_hit_sample_size"]),
            options.min_final_hit_sample_size,
            detail="correct-score admission needs enough final-answer samples",
        ),
        _minimum_check(
            "candidate_final_hit_coverage_ratio",
            _optional_float(metrics["candidate_final_hit_coverage_ratio"]),
            options.min_candidate_final_hit_coverage_ratio,
            detail="correct-score admission should cover final answers",
        ),
        _minimum_check(
            "candidate_final_hit_rate",
            _optional_float(metrics["candidate_final_hit_rate"]),
            options.min_candidate_final_hit_rate,
            detail="correct-score admission should retain hit-rate quality",
        ),
        _minimum_check(
            "candidate_roi",
            _optional_float(metrics["candidate_roi"]),
            options.min_candidate_roi,
            detail="correct-score admission requires non-negative candidate ROI",
        ),
        _minimum_check(
            "candidate_correct_score_final_answer_count",
            _optional_float(metrics["candidate_correct_score_final_answer_count"]),
            options.min_candidate_correct_score_final_answer_count,
            detail="correct-score must actually enter bounded final answers",
        ),
        _minimum_check(
            "candidate_correct_score_final_answer_rate",
            _optional_float(metrics["candidate_correct_score_final_answer_rate"]),
            options.min_candidate_correct_score_final_answer_rate,
            detail="correct-score final-answer rate should meet admission coverage",
        ),
        _minimum_check(
            "final_hit_rate_delta",
            _optional_float(metrics["final_hit_rate_delta"]),
            options.min_final_hit_rate_delta,
            detail="correct-score candidate suite must not reduce hit rate",
        ),
        _minimum_check(
            "roi_delta",
            _optional_float(metrics["roi_delta"]),
            options.min_roi_delta,
            detail="correct-score candidate suite must not reduce ROI",
        ),
        _minimum_check(
            "profit_loss_delta",
            _optional_float(metrics["profit_loss_delta"]),
            options.min_profit_loss_delta,
            detail="correct-score candidate suite must not reduce profit/loss",
        ),
        _maximum_check(
            "brier_score_delta",
            _optional_float(metrics["brier_score_delta"]),
            options.max_brier_score_delta,
            detail="correct-score candidate suite must not worsen Brier score",
        ),
        _maximum_check(
            "log_loss_delta",
            _optional_float(metrics["log_loss_delta"]),
            options.max_log_loss_delta,
            detail="correct-score candidate suite must not worsen log loss",
        ),
        _maximum_check(
            "mean_calibration_error_delta",
            _optional_float(metrics["mean_calibration_error_delta"]),
            options.max_mean_calibration_error_delta,
            detail="correct-score candidate suite must not worsen calibration error",
        ),
        _boolean_check(
            "production_recommendation_unchanged",
            True,
            enabled=options.require_no_production_change,
            detail="admission report itself must not change production recommendations",
        ),
        _boolean_check(
            "public_response_unchanged",
            True,
            enabled=options.require_no_public_response_change,
            detail="admission report itself must not change public response",
        ),
    ]


def _decision_payload(
    source_gate: HistoricalRecommendationSuiteQualityGateResult,
    *,
    metrics: Mapping[str, object],
    status: HistoricalCorrectScoreAdmissionStatus,
    production_allowed: bool,
    holdout_allowed: bool,
    options: HistoricalCorrectScoreAdmissionOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": "historical_correct_score_admission_decision_v3_2",
        "status": status,
        "production_recommendation_allowed": production_allowed,
        "holdout_allowed": holdout_allowed,
        "default_recommendation_path_changed": False,
        "source_gate_key": source_gate.gate_key,
        "source_suite_status": source_gate.suite_status,
        "candidate_correct_score_final_answer_count": metrics[
            "candidate_correct_score_final_answer_count"
        ],
        "candidate_correct_score_final_answer_rate": metrics[
            "candidate_correct_score_final_answer_rate"
        ],
        "no_harm_delta_basis": metrics["no_harm_delta_basis"],
        "minimum_correct_score_final_answer_count": (
            options.min_candidate_correct_score_final_answer_count
        ),
        "rollback_conditions": [
            "disable_if_source_gate_missing_or_failed",
            "disable_if_correct_score_final_answer_count_below_floor",
            "disable_if_final_hit_rate_regresses",
            "disable_if_roi_or_profit_loss_regresses",
            "disable_if_probability_quality_regresses",
        ],
        "notes": [
            "Admission is governance evidence only; it does not modify defaults.",
            "Insufficient correct-score final-answer coverage remains holdout-only.",
        ],
    }


def _status(
    *,
    production_allowed: bool,
    holdout_allowed: bool,
) -> HistoricalCorrectScoreAdmissionStatus:
    if production_allowed:
        return "accepted"
    if holdout_allowed:
        return "holdout_only"
    return "rejected"


def _source_checks_passed(
    checks: Sequence[HistoricalCorrectScoreAdmissionCheck],
) -> bool:
    source_names = {
        "source_gate_passed",
        "source_failed_check_count",
        "suite_status_allowed",
        "slice_count",
        "comparison_count",
        "candidate_final_hit_sample_size",
        "candidate_final_hit_coverage_ratio",
        "production_recommendation_unchanged",
        "public_response_unchanged",
    }
    return all(check.status == "passed" for check in checks if check.name in source_names)


def _no_harm_checks_passed(
    checks: Sequence[HistoricalCorrectScoreAdmissionCheck],
) -> bool:
    no_harm_names = {
        "candidate_final_hit_rate",
        "final_hit_rate_delta",
        "roi_delta",
        "profit_loss_delta",
        "brier_score_delta",
        "log_loss_delta",
        "mean_calibration_error_delta",
    }
    return all(check.status == "passed" for check in checks if check.name in no_harm_names)


def _admission_evidence_checks_passed(
    checks: Sequence[HistoricalCorrectScoreAdmissionCheck],
) -> bool:
    evidence_names = {
        "candidate_roi",
        "candidate_correct_score_final_answer_count",
        "candidate_correct_score_final_answer_rate",
    }
    return all(
        check.status == "passed" for check in checks if check.name in evidence_names
    )


def _warnings(
    *,
    status: HistoricalCorrectScoreAdmissionStatus,
    checks: Sequence[HistoricalCorrectScoreAdmissionCheck],
) -> list[str]:
    warnings = [
        f"correct_score_admission:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    warnings.append(f"correct_score_admission:{status}")
    return warnings


def _boolean_check(
    name: str,
    passed: bool,
    *,
    enabled: bool = True,
    detail: str,
) -> HistoricalCorrectScoreAdmissionCheck:
    return HistoricalCorrectScoreAdmissionCheck(
        name=name,
        status="passed" if (not enabled or passed) else "failed",
        actual=passed,
        threshold=True if enabled else None,
        detail=detail,
    )


def _minimum_check(
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    *,
    detail: str,
) -> HistoricalCorrectScoreAdmissionCheck:
    passed = threshold is None or (actual is not None and actual >= threshold)
    return HistoricalCorrectScoreAdmissionCheck(
        name=name,
        status="passed" if passed else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    *,
    detail: str,
) -> HistoricalCorrectScoreAdmissionCheck:
    passed = threshold is None or (actual is not None and actual <= threshold)
    return HistoricalCorrectScoreAdmissionCheck(
        name=name,
        status="passed" if passed else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Create a correct-score admission decision from a suite gate."
    )
    parser.add_argument("source_gate_report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-slice-count", type=int, default=1)
    parser.add_argument("--min-comparison-count", type=int, default=1)
    parser.add_argument("--min-final-hit-sample-size", type=int, default=1)
    parser.add_argument(
        "--min-candidate-final-hit-coverage-ratio",
        type=float,
        default=1.0,
    )
    parser.add_argument("--min-candidate-final-hit-rate", type=float, default=None)
    parser.add_argument("--min-candidate-roi", type=float, default=0.0)
    parser.add_argument(
        "--min-candidate-correct-score-final-answer-count",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--min-candidate-correct-score-final-answer-rate",
        type=float,
        default=None,
    )
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--max-failed-check-count", type=int, default=0)
    parser.add_argument("--allow-source-gate-failed", action="store_true")
    parser.add_argument("--fail-on-suite-statuses", default="regressed,mixed,failed")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalCorrectScoreAdmissionOptions:
    return HistoricalCorrectScoreAdmissionOptions(
        min_slice_count=args.min_slice_count,
        min_comparison_count=args.min_comparison_count,
        min_final_hit_sample_size=args.min_final_hit_sample_size,
        min_candidate_final_hit_coverage_ratio=(
            args.min_candidate_final_hit_coverage_ratio
        ),
        min_candidate_final_hit_rate=args.min_candidate_final_hit_rate,
        min_candidate_roi=args.min_candidate_roi,
        min_candidate_correct_score_final_answer_count=(
            args.min_candidate_correct_score_final_answer_count
        ),
        min_candidate_correct_score_final_answer_rate=(
            args.min_candidate_correct_score_final_answer_rate
        ),
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        max_failed_check_count=args.max_failed_check_count,
        require_source_gate_passed=not args.allow_source_gate_failed,
        fail_on_suite_statuses=tuple(_csv(args.fail_on_suite_statuses)),
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _source_failed_check_count(
    source_gate: HistoricalRecommendationSuiteQualityGateResult,
) -> int:
    failed_checks = source_gate.summary_json.get("failed_checks")
    if isinstance(failed_checks, Sequence) and not isinstance(
        failed_checks,
        str | bytes | bytearray,
    ):
        return len(failed_checks)
    return sum(1 for check in source_gate.checks if check.status == "failed")


def _summary_int(summary: Mapping[str, object], key: str) -> int:
    value = summary.get(key, 0)
    return _int(value)


def _summary_float(summary: Mapping[str, object], key: str) -> float | None:
    return _optional_float(summary.get(key))


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalCorrectScoreAdmissionCheck],
    decision_payload: Mapping[str, object],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "checks": [check.model_dump(mode="json") for check in checks],
                "decision_payload": decision_payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_correct_score_admission:{digest}"


if __name__ == "__main__":
    main()
