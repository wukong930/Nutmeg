from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_probability_calibration_profile_gate import (
    HistoricalProbabilityCalibrationProfileGateReport,
)

type HistoricalProbabilityCalibrationProfileModelQualityGateStatus = Literal[
    "model_quality_ready",
    "blocked",
]
type HistoricalProbabilityCalibrationProfileModelQualityGateCheckStatus = Literal[
    "passed",
    "failed",
]

DEFAULT_PROBABILITY_CALIBRATION_PROFILE_MODEL_QUALITY_GATE_ID = (
    "probability-calibration-profile-model-quality-shadow-v3.2"
)


class HistoricalProbabilityCalibrationProfileModelQualityGateOptions(BaseModel):
    gate_id: str = DEFAULT_PROBABILITY_CALIBRATION_PROFILE_MODEL_QUALITY_GATE_ID
    require_shadow_only: bool = True
    require_suite_status_improved: bool = True
    min_selected_competition_count: int = Field(default=1, ge=0)
    min_adjusted_slice_count: int = Field(default=1, ge=0)
    min_adjusted_fixture_count: int = Field(default=1, ge=0)
    max_skipped_fixture_count: int | None = Field(default=None, ge=0)
    max_final_answer_changed_count: int | None = Field(default=0, ge=0)
    min_final_answer_hit_count_delta: int = 0
    min_final_answer_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0


class HistoricalProbabilityCalibrationProfileModelQualityGateCheck(BaseModel):
    name: str
    status: HistoricalProbabilityCalibrationProfileModelQualityGateCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalProbabilityCalibrationProfileModelQualityGateReport(BaseModel):
    report_key: str
    status: HistoricalProbabilityCalibrationProfileModelQualityGateStatus
    gate_id: str
    profile_gate_report_key: str
    model_quality_gate_passed: bool
    selected_competition_ids: list[str] = Field(default_factory=list)
    adjusted_slice_count: int = Field(default=0, ge=0)
    adjusted_fixture_count: int = Field(default=0, ge=0)
    skipped_fixture_count: int = Field(default=0, ge=0)
    final_answer_changed_count: int = Field(default=0, ge=0)
    final_answer_hit_count_delta: int = 0
    final_answer_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float = 0.0
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    checks: list[HistoricalProbabilityCalibrationProfileModelQualityGateCheck] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


def build_historical_probability_calibration_profile_model_quality_gate_report(
    profile_gate_report: HistoricalProbabilityCalibrationProfileGateReport,
    *,
    options: HistoricalProbabilityCalibrationProfileModelQualityGateOptions | None = None,
) -> HistoricalProbabilityCalibrationProfileModelQualityGateReport:
    resolved_options = (
        options or HistoricalProbabilityCalibrationProfileModelQualityGateOptions()
    )
    summary = profile_gate_report.summary_json
    aggregate_deltas = _mapping(summary.get("aggregate_deltas_json"))
    final_answer_changed_count = _int(aggregate_deltas.get("final_answer_changed_count"))
    final_answer_hit_count_delta = _int(
        aggregate_deltas.get("final_hit_count_delta")
    )
    final_answer_hit_rate_delta = _optional_float(
        aggregate_deltas.get("final_hit_rate_delta")
    )
    roi_delta = _optional_float(aggregate_deltas.get("roi_delta"))
    profit_loss_delta = _float(aggregate_deltas.get("profit_loss_delta"))
    brier_score_delta = _optional_float(aggregate_deltas.get("brier_score_delta"))
    log_loss_delta = _optional_float(aggregate_deltas.get("log_loss_delta"))
    mean_calibration_error_delta = _optional_float(
        aggregate_deltas.get("mean_calibration_error_delta")
    )
    selected_competition_ids = [
        str(value) for value in profile_gate_report.selected_competition_ids
    ]
    suite_status = _optional_str(summary.get("suite_status"))
    shadow_only = bool(summary.get("shadow_only"))
    checks = [
        _boolean_check(
            name="profile_gate_shadow_only",
            actual=shadow_only,
            expected=True,
            enabled=resolved_options.require_shadow_only,
            detail="model-quality calibration evidence must stay shadow-only",
        ),
        _boolean_check(
            name="profile_gate_suite_status_improved",
            actual=suite_status == "improved",
            expected=True,
            enabled=resolved_options.require_suite_status_improved,
            detail="profile-gate suite status should improve probability quality",
        ),
        _minimum_check(
            name="selected_competition_count",
            actual=len(selected_competition_ids),
            threshold=resolved_options.min_selected_competition_count,
            detail="model-quality evidence should cover enough competitions",
        ),
        _minimum_check(
            name="adjusted_slice_count",
            actual=profile_gate_report.adjusted_slice_count,
            threshold=resolved_options.min_adjusted_slice_count,
            detail="model-quality evidence should cover enough adjusted slices",
        ),
        _minimum_check(
            name="adjusted_fixture_count",
            actual=profile_gate_report.adjusted_fixture_count,
            threshold=resolved_options.min_adjusted_fixture_count,
            detail="model-quality evidence should cover enough adjusted fixtures",
        ),
        _optional_maximum_check(
            name="skipped_fixture_count",
            actual=profile_gate_report.skipped_fixture_count,
            threshold=resolved_options.max_skipped_fixture_count,
            detail="model-quality evidence should not skip too many fixtures",
        ),
        _optional_maximum_check(
            name="final_answer_changed_count",
            actual=final_answer_changed_count,
            threshold=resolved_options.max_final_answer_changed_count,
            detail=(
                "this shadow gate tracks probability quality without changing "
                "final answers by default"
            ),
        ),
        _minimum_check(
            name="final_answer_hit_count_delta",
            actual=final_answer_hit_count_delta,
            threshold=resolved_options.min_final_answer_hit_count_delta,
            detail="final-answer hit count should not regress",
        ),
        _optional_minimum_check(
            name="final_answer_hit_rate_delta",
            actual=final_answer_hit_rate_delta,
            threshold=resolved_options.min_final_answer_hit_rate_delta,
            detail="final-answer hit rate should not regress",
        ),
        _optional_minimum_check(
            name="roi_delta",
            actual=roi_delta,
            threshold=resolved_options.min_roi_delta,
            detail="ROI should not regress",
        ),
        _minimum_check(
            name="profit_loss_delta",
            actual=profit_loss_delta,
            threshold=resolved_options.min_profit_loss_delta,
            detail="profit/loss should not regress",
        ),
        _optional_maximum_check(
            name="brier_score_delta",
            actual=brier_score_delta,
            threshold=resolved_options.max_brier_score_delta,
            detail="Brier score should improve or stay flat",
        ),
        _optional_maximum_check(
            name="log_loss_delta",
            actual=log_loss_delta,
            threshold=resolved_options.max_log_loss_delta,
            detail="log loss should improve or stay flat",
        ),
        _optional_maximum_check(
            name="mean_calibration_error_delta",
            actual=mean_calibration_error_delta,
            threshold=resolved_options.max_mean_calibration_error_delta,
            detail="mean calibration error should improve or stay flat",
        ),
    ]
    failed_checks = [check for check in checks if check.status == "failed"]
    status: HistoricalProbabilityCalibrationProfileModelQualityGateStatus = (
        "blocked" if failed_checks else "model_quality_ready"
    )
    report_summary: dict[str, object] = {
        "calculation_basis": (
            "historical_probability_calibration_profile_model_quality_gate_v3_2"
        ),
        "gate_id": resolved_options.gate_id,
        "profile_gate_report_key": profile_gate_report.report_key,
        "profile_gate_passed_final_answer_gate": (
            profile_gate_report.passed_final_answer_gate
        ),
        "profile_gate_quality_gate_passed": bool(summary.get("quality_gate_passed")),
        "profile_gate_suite_status": suite_status,
        "shadow_only": shadow_only,
        "selected_competition_ids": selected_competition_ids,
        "adjusted_slice_count": profile_gate_report.adjusted_slice_count,
        "adjusted_fixture_count": profile_gate_report.adjusted_fixture_count,
        "skipped_fixture_count": profile_gate_report.skipped_fixture_count,
        "final_answer_changed_count": final_answer_changed_count,
        "final_answer_hit_count_delta": final_answer_hit_count_delta,
        "final_answer_hit_rate_delta": final_answer_hit_rate_delta,
        "roi_delta": roi_delta,
        "profit_loss_delta": profit_loss_delta,
        "brier_score_delta": brier_score_delta,
        "log_loss_delta": log_loss_delta,
        "mean_calibration_error_delta": mean_calibration_error_delta,
        "failed_checks": [check.name for check in failed_checks],
        "warnings": profile_gate_report.warnings,
        "options": resolved_options.model_dump(mode="json"),
    }
    report_key = _report_key(report_summary)
    return HistoricalProbabilityCalibrationProfileModelQualityGateReport(
        report_key=report_key,
        status=status,
        gate_id=resolved_options.gate_id,
        profile_gate_report_key=profile_gate_report.report_key,
        model_quality_gate_passed=not failed_checks,
        selected_competition_ids=selected_competition_ids,
        adjusted_slice_count=profile_gate_report.adjusted_slice_count,
        adjusted_fixture_count=profile_gate_report.adjusted_fixture_count,
        skipped_fixture_count=profile_gate_report.skipped_fixture_count,
        final_answer_changed_count=final_answer_changed_count,
        final_answer_hit_count_delta=final_answer_hit_count_delta,
        final_answer_hit_rate_delta=final_answer_hit_rate_delta,
        roi_delta=roi_delta,
        profit_loss_delta=profit_loss_delta,
        brier_score_delta=brier_score_delta,
        log_loss_delta=log_loss_delta,
        mean_calibration_error_delta=mean_calibration_error_delta,
        checks=checks,
        warnings=list(profile_gate_report.warnings),
        summary_json={**report_summary, "report_key": report_key, "status": status},
    )


def load_historical_probability_calibration_profile_model_quality_gate_report(
    path: Path | str,
) -> HistoricalProbabilityCalibrationProfileModelQualityGateReport:
    return HistoricalProbabilityCalibrationProfileModelQualityGateReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    profile_gate_report = HistoricalProbabilityCalibrationProfileGateReport.model_validate_json(
        args.profile_gate_report.read_text(encoding="utf-8")
    )
    report = build_historical_probability_calibration_profile_model_quality_gate_report(
        profile_gate_report,
        options=_options_from_args(args),
    )
    if args.report_output_path is not None:
        args.report_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_output_path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
    print(report.model_dump_json(indent=2))
    if not report.model_quality_gate_passed and not args.no_fail_process:
        raise SystemExit(1)


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Gate a shadow probability-calibration profile as model-quality evidence "
            "without changing default recommendations."
        )
    )
    parser.add_argument("--profile-gate-report", type=Path, required=True)
    parser.add_argument("--report-output-path", type=Path)
    parser.add_argument(
        "--gate-id",
        default=DEFAULT_PROBABILITY_CALIBRATION_PROFILE_MODEL_QUALITY_GATE_ID,
    )
    parser.add_argument("--allow-non-shadow-profile-gate", action="store_true")
    parser.add_argument("--allow-non-improved-suite-status", action="store_true")
    parser.add_argument("--min-selected-competition-count", type=int, default=1)
    parser.add_argument("--min-adjusted-slice-count", type=int, default=1)
    parser.add_argument("--min-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--max-skipped-fixture-count", type=int, default=None)
    parser.add_argument("--max-final-answer-changed-count", type=int, default=0)
    parser.add_argument("--min-final-answer-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-final-answer-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalProbabilityCalibrationProfileModelQualityGateOptions:
    return HistoricalProbabilityCalibrationProfileModelQualityGateOptions(
        gate_id=args.gate_id,
        require_shadow_only=not args.allow_non_shadow_profile_gate,
        require_suite_status_improved=not args.allow_non_improved_suite_status,
        min_selected_competition_count=args.min_selected_competition_count,
        min_adjusted_slice_count=args.min_adjusted_slice_count,
        min_adjusted_fixture_count=args.min_adjusted_fixture_count,
        max_skipped_fixture_count=args.max_skipped_fixture_count,
        max_final_answer_changed_count=args.max_final_answer_changed_count,
        min_final_answer_hit_count_delta=args.min_final_answer_hit_count_delta,
        min_final_answer_hit_rate_delta=args.min_final_answer_hit_rate_delta,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
    )


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    enabled: bool,
    detail: str,
) -> HistoricalProbabilityCalibrationProfileModelQualityGateCheck:
    return HistoricalProbabilityCalibrationProfileModelQualityGateCheck(
        name=name,
        status="passed" if not enabled or actual == expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: float | int,
    threshold: float | int,
    detail: str,
) -> HistoricalProbabilityCalibrationProfileModelQualityGateCheck:
    return HistoricalProbabilityCalibrationProfileModelQualityGateCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _optional_minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> HistoricalProbabilityCalibrationProfileModelQualityGateCheck:
    if actual is None or threshold is None:
        return HistoricalProbabilityCalibrationProfileModelQualityGateCheck(
            name=name,
            status="failed",
            actual=actual,
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
    actual: float | int | None,
    threshold: float | int | None,
    detail: str,
) -> HistoricalProbabilityCalibrationProfileModelQualityGateCheck:
    if threshold is None:
        return HistoricalProbabilityCalibrationProfileModelQualityGateCheck(
            name=name,
            status="passed",
            actual=actual,
            threshold=threshold,
            detail=detail,
        )
    if actual is None:
        return HistoricalProbabilityCalibrationProfileModelQualityGateCheck(
            name=name,
            status="failed",
            actual=actual,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalProbabilityCalibrationProfileModelQualityGateCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _optional_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _float(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return None


def _report_key(summary: Mapping[str, object]) -> str:
    digest = sha256(dumps(summary, sort_keys=True, default=str).encode()).hexdigest()[
        :16
    ]
    return f"historical_probability_calibration_profile_model_quality_gate:{digest}"
