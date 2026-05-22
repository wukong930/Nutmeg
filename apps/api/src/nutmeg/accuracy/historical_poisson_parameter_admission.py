from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_poisson_parameter_learning import (
    HistoricalPoissonParameterLearningReport,
)

type HistoricalPoissonParameterAdmissionStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]
type HistoricalPoissonParameterAdmissionCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]


class HistoricalPoissonParameterAdmissionOptions(BaseModel):
    min_learned_competition_count: int = Field(default=1, ge=0)
    min_validation_count: int = Field(default=100, ge=0)
    min_candidate_count: int = Field(default=1, ge=0)
    max_warning_count: int | None = Field(default=0, ge=0)
    min_hit_rate_delta: float | None = 0.0
    max_brier_score_delta: float | None = 0.0
    max_log_loss_delta: float | None = 0.0
    max_expected_calibration_error_delta: float | None = 0.0
    min_average_actual_probability_delta: float | None = None
    max_failed_competition_no_harm_count: int | None = Field(default=0, ge=0)
    min_selected_model_signal_weight: float | None = Field(default=0.05, ge=0.0, le=1.0)
    require_source_status_generated: bool = True
    require_no_public_prediction_change: bool = True


class HistoricalPoissonParameterAdmissionCheck(BaseModel):
    name: str
    status: HistoricalPoissonParameterAdmissionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalPoissonParameterAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalPoissonParameterAdmissionStatus
    candidate_model_allowed: bool
    shadow_allowed: bool
    source_report_key: str
    source_status: str
    competition_count: int = Field(ge=0)
    learned_competition_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    validation_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    failed_competition_no_harm_count: int = Field(ge=0)
    hit_rate_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    expected_calibration_error_delta: float | None = None
    average_actual_probability_delta: float | None = None
    min_selected_model_signal_weight: float | None = None
    average_selected_model_signal_weight: float | None = None
    selected_candidate_counts: dict[str, int] = Field(default_factory=dict)
    public_prediction_changed: bool = False
    checks: list[HistoricalPoissonParameterAdmissionCheck] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    decision_payload_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_poisson_parameter_learning_report(
    path: Path | str,
) -> HistoricalPoissonParameterLearningReport:
    return HistoricalPoissonParameterLearningReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def load_historical_poisson_parameter_admission_report(
    path: Path | str,
) -> HistoricalPoissonParameterAdmissionReport:
    return HistoricalPoissonParameterAdmissionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_poisson_parameter_admission_report(
    source_report: HistoricalPoissonParameterLearningReport,
    *,
    options: HistoricalPoissonParameterAdmissionOptions | None = None,
) -> HistoricalPoissonParameterAdmissionReport:
    resolved_options = options or HistoricalPoissonParameterAdmissionOptions()
    metrics = _metrics(source_report)
    checks = _checks(source_report, metrics=metrics, options=resolved_options)
    source_ready = _source_ready(checks)
    no_harm = _no_harm_passed(checks)
    model_signal_ready = _model_signal_ready(checks)
    candidate_model_allowed = source_ready and no_harm and model_signal_ready
    shadow_allowed = source_ready
    status = _status(
        candidate_model_allowed=candidate_model_allowed,
        shadow_allowed=shadow_allowed,
    )
    warnings = _warnings(status=status, checks=checks)
    decision_payload = _decision_payload(
        source_report,
        metrics=metrics,
        status=status,
        candidate_model_allowed=candidate_model_allowed,
        shadow_allowed=shadow_allowed,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_poisson_parameter_admission_v3_2",
        "status": status,
        "candidate_model_allowed": candidate_model_allowed,
        "shadow_allowed": shadow_allowed,
        "source_report_key": source_report.report_key,
        "source_status": source_report.status,
        **metrics,
        "public_prediction_changed": False,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, decision_payload)
    return HistoricalPoissonParameterAdmissionReport(
        report_key=report_key,
        status=status,
        candidate_model_allowed=candidate_model_allowed,
        shadow_allowed=shadow_allowed,
        source_report_key=source_report.report_key,
        source_status=source_report.status,
        competition_count=_int(metrics["competition_count"]),
        learned_competition_count=_int(metrics["learned_competition_count"]),
        candidate_count=_int(metrics["candidate_count"]),
        fixture_count=_int(metrics["fixture_count"]),
        validation_count=_int(metrics["validation_count"]),
        warning_count=_int(metrics["warning_count"]),
        failed_competition_no_harm_count=_int(
            metrics["failed_competition_no_harm_count"]
        ),
        hit_rate_delta=_optional_float(metrics["hit_rate_delta"]),
        brier_score_delta=_optional_float(metrics["brier_score_delta"]),
        log_loss_delta=_optional_float(metrics["log_loss_delta"]),
        expected_calibration_error_delta=_optional_float(
            metrics["expected_calibration_error_delta"]
        ),
        average_actual_probability_delta=_optional_float(
            metrics["average_actual_probability_delta"]
        ),
        min_selected_model_signal_weight=_optional_float(
            metrics["min_selected_model_signal_weight"]
        ),
        average_selected_model_signal_weight=_optional_float(
            metrics["average_selected_model_signal_weight"]
        ),
        selected_candidate_counts={
            str(key): _int(value)
            for key, value in _mapping(metrics["selected_candidate_counts"]).items()
        },
        public_prediction_changed=False,
        checks=checks,
        warnings=warnings,
        decision_payload_json=decision_payload,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_poisson_parameter_admission_report(
        load_historical_poisson_parameter_learning_report(args.source_learning_report),
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
    if not report.candidate_model_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _metrics(source_report: HistoricalPoissonParameterLearningReport) -> dict[str, object]:
    deltas = dict(source_report.overall_validation_deltas_json)
    selected_model_signal_weights = _selected_model_signal_weights(source_report)
    return {
        "competition_count": source_report.competition_count,
        "learned_competition_count": source_report.learned_competition_count,
        "candidate_count": source_report.candidate_count,
        "fixture_count": source_report.fixture_count,
        "validation_count": source_report.validation_count,
        "warning_count": len(source_report.warnings),
        "failed_competition_no_harm_count": _failed_competition_no_harm_count(
            source_report
        ),
        "hit_rate_delta": _mapping_float(deltas, "hit_rate_delta"),
        "brier_score_delta": _mapping_float(deltas, "brier_score_delta"),
        "log_loss_delta": _mapping_float(deltas, "log_loss_delta"),
        "expected_calibration_error_delta": _mapping_float(
            deltas,
            "expected_calibration_error_delta",
        ),
        "average_actual_probability_delta": _mapping_float(
            deltas,
            "average_actual_probability_delta",
        ),
        "min_selected_model_signal_weight": (
            min(selected_model_signal_weights) if selected_model_signal_weights else None
        ),
        "average_selected_model_signal_weight": (
            sum(selected_model_signal_weights) / len(selected_model_signal_weights)
            if selected_model_signal_weights
            else None
        ),
        "selected_candidate_counts": dict(source_report.selected_candidate_counts),
    }


def _selected_model_signal_weights(
    source_report: HistoricalPoissonParameterLearningReport,
) -> list[float]:
    weights: list[float] = []
    for competition in source_report.competitions:
        candidate = competition.selected_candidate
        if candidate is None:
            continue
        weights.append(max(0.0, min(1.0, 1.0 - candidate.market_anchor_weight)))
    return weights


def _failed_competition_no_harm_count(
    source_report: HistoricalPoissonParameterLearningReport,
) -> int:
    failed_count = 0
    for competition in source_report.competitions:
        if competition.selected_validation is None:
            continue
        deltas = competition.selected_validation.deltas_json
        if (
            _mapping_float_or_zero(deltas, "brier_score_delta") > 0.0
            or _mapping_float_or_zero(deltas, "log_loss_delta") > 0.0
            or _mapping_float_or_zero(deltas, "expected_calibration_error_delta") > 0.0
        ):
            failed_count += 1
    return failed_count


def _checks(
    source_report: HistoricalPoissonParameterLearningReport,
    *,
    metrics: Mapping[str, object],
    options: HistoricalPoissonParameterAdmissionOptions,
) -> list[HistoricalPoissonParameterAdmissionCheck]:
    return [
        _boolean_check(
            "source_status_generated",
            source_report.status == "generated",
            enabled=options.require_source_status_generated,
            detail="parameter learning report must be generated before admission",
        ),
        _minimum_check(
            "learned_competition_count",
            _optional_float(metrics["learned_competition_count"]),
            options.min_learned_competition_count,
            detail="parameter learning needs enough learned competitions",
        ),
        _minimum_check(
            "validation_count",
            _optional_float(metrics["validation_count"]),
            options.min_validation_count,
            detail="parameter learning needs enough held-out validation samples",
        ),
        _minimum_check(
            "candidate_count",
            _optional_float(metrics["candidate_count"]),
            options.min_candidate_count,
            detail="parameter learning must evaluate at least one candidate",
        ),
        _maximum_check(
            "warning_count",
            _optional_float(metrics["warning_count"]),
            options.max_warning_count,
            detail="parameter learning warnings should remain within the limit",
        ),
        _minimum_check(
            "hit_rate_delta",
            _optional_float(metrics["hit_rate_delta"]),
            options.min_hit_rate_delta,
            detail="candidate parameters should not reduce 1X2 hit rate",
        ),
        _maximum_check(
            "brier_score_delta",
            _optional_float(metrics["brier_score_delta"]),
            options.max_brier_score_delta,
            detail="candidate parameters should not worsen Brier score",
        ),
        _maximum_check(
            "log_loss_delta",
            _optional_float(metrics["log_loss_delta"]),
            options.max_log_loss_delta,
            detail="candidate parameters should not worsen log loss",
        ),
        _maximum_check(
            "expected_calibration_error_delta",
            _optional_float(metrics["expected_calibration_error_delta"]),
            options.max_expected_calibration_error_delta,
            detail="candidate parameters should not worsen calibration error",
        ),
        _minimum_check(
            "average_actual_probability_delta",
            _optional_float(metrics["average_actual_probability_delta"]),
            options.min_average_actual_probability_delta,
            detail="candidate parameters should not reduce actual-outcome probability",
        ),
        _maximum_check(
            "failed_competition_no_harm_count",
            _optional_float(metrics["failed_competition_no_harm_count"]),
            options.max_failed_competition_no_harm_count,
            detail="competition-level parameter regressions should stay within limit",
        ),
        _minimum_check(
            "selected_model_signal_weight",
            _optional_float(metrics["min_selected_model_signal_weight"]),
            options.min_selected_model_signal_weight,
            detail="selected candidates must retain enough score-grid model signal",
        ),
        _boolean_check(
            "public_prediction_unchanged",
            True,
            enabled=options.require_no_public_prediction_change,
            detail="admission report must not change the public prediction path",
        ),
    ]


def _decision_payload(
    source_report: HistoricalPoissonParameterLearningReport,
    *,
    metrics: Mapping[str, object],
    status: HistoricalPoissonParameterAdmissionStatus,
    candidate_model_allowed: bool,
    shadow_allowed: bool,
    options: HistoricalPoissonParameterAdmissionOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": "historical_poisson_parameter_admission_decision_v3_2",
        "status": status,
        "candidate_model_allowed": candidate_model_allowed,
        "shadow_allowed": shadow_allowed,
        "default_prediction_path_changed": False,
        "source_report_key": source_report.report_key,
        "learned_competition_count": metrics["learned_competition_count"],
        "validation_count": metrics["validation_count"],
        "min_selected_model_signal_weight": metrics["min_selected_model_signal_weight"],
        "average_selected_model_signal_weight": metrics[
            "average_selected_model_signal_weight"
        ],
        "selected_candidate_counts": metrics["selected_candidate_counts"],
        "minimum_validation_count": options.min_validation_count,
        "minimum_selected_model_signal_weight": (
            options.min_selected_model_signal_weight
        ),
        "rollback_conditions": [
            "disable_if_learning_report_missing_or_not_generated",
            "disable_if_validation_sample_count_below_floor",
            "disable_if_brier_or_log_loss_regresses",
            "disable_if_calibration_error_regresses",
            "disable_if_competition_level_regressions_exceed_limit",
            "disable_if_selected_candidate_is_only_market_anchor",
        ],
        "notes": [
            "Admission is governance evidence only; it does not modify defaults.",
            "Shadow-only status means the learned parameters remain research evidence.",
        ],
    }


def _status(
    *,
    candidate_model_allowed: bool,
    shadow_allowed: bool,
) -> HistoricalPoissonParameterAdmissionStatus:
    if candidate_model_allowed:
        return "accepted"
    if shadow_allowed:
        return "shadow_only"
    return "rejected"


def _source_ready(checks: Sequence[HistoricalPoissonParameterAdmissionCheck]) -> bool:
    source_names = {
        "source_status_generated",
        "learned_competition_count",
        "validation_count",
        "candidate_count",
        "warning_count",
        "public_prediction_unchanged",
    }
    return all(check.status != "failed" for check in checks if check.name in source_names)


def _no_harm_passed(checks: Sequence[HistoricalPoissonParameterAdmissionCheck]) -> bool:
    no_harm_names = {
        "hit_rate_delta",
        "brier_score_delta",
        "log_loss_delta",
        "expected_calibration_error_delta",
        "average_actual_probability_delta",
        "failed_competition_no_harm_count",
    }
    return all(check.status != "failed" for check in checks if check.name in no_harm_names)


def _model_signal_ready(
    checks: Sequence[HistoricalPoissonParameterAdmissionCheck],
) -> bool:
    signal_names = {"selected_model_signal_weight"}
    return all(check.status != "failed" for check in checks if check.name in signal_names)


def _warnings(
    *,
    status: HistoricalPoissonParameterAdmissionStatus,
    checks: Sequence[HistoricalPoissonParameterAdmissionCheck],
) -> list[str]:
    warnings = [
        f"poisson_parameter_admission:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    warnings.append(f"poisson_parameter_admission:{status}")
    return warnings


def _boolean_check(
    name: str,
    passed: bool,
    *,
    enabled: bool = True,
    detail: str,
) -> HistoricalPoissonParameterAdmissionCheck:
    if not enabled:
        return _skipped_check(name=name, actual=passed, detail=detail)
    return HistoricalPoissonParameterAdmissionCheck(
        name=name,
        status="passed" if passed else "failed",
        actual=passed,
        threshold=True,
        detail=detail,
    )


def _minimum_check(
    name: str,
    actual: float | int | None,
    threshold: float | int | None,
    *,
    detail: str,
) -> HistoricalPoissonParameterAdmissionCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalPoissonParameterAdmissionCheck(
        name=name,
        status="passed" if actual is not None and actual >= threshold else "failed",
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
) -> HistoricalPoissonParameterAdmissionCheck:
    if threshold is None:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalPoissonParameterAdmissionCheck(
        name=name,
        status="passed" if actual is not None and actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _skipped_check(
    *,
    name: str,
    actual: float | int | str | bool | None,
    detail: str,
) -> HistoricalPoissonParameterAdmissionCheck:
    return HistoricalPoissonParameterAdmissionCheck(
        name=name,
        status="skipped",
        actual=actual,
        threshold=None,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Gate learned Poisson/Dixon-Coles parameters before promotion."
    )
    parser.add_argument("source_learning_report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--min-learned-competition-count", type=int, default=1)
    parser.add_argument("--min-validation-count", type=int, default=100)
    parser.add_argument("--min-candidate-count", type=int, default=1)
    parser.add_argument("--max-warning-count", type=int, default=0)
    parser.add_argument("--min-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--max-expected-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-average-actual-probability-delta", type=float)
    parser.add_argument(
        "--max-failed-competition-no-harm-count",
        type=int,
        default=0,
    )
    parser.add_argument("--min-selected-model-signal-weight", type=float, default=0.05)
    parser.add_argument("--allow-source-status-not-generated", action="store_true")
    parser.add_argument("--allow-public-prediction-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalPoissonParameterAdmissionOptions:
    return HistoricalPoissonParameterAdmissionOptions(
        min_learned_competition_count=args.min_learned_competition_count,
        min_validation_count=args.min_validation_count,
        min_candidate_count=args.min_candidate_count,
        max_warning_count=args.max_warning_count,
        min_hit_rate_delta=args.min_hit_rate_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_expected_calibration_error_delta=(
            args.max_expected_calibration_error_delta
        ),
        min_average_actual_probability_delta=(
            args.min_average_actual_probability_delta
        ),
        max_failed_competition_no_harm_count=(
            args.max_failed_competition_no_harm_count
        ),
        min_selected_model_signal_weight=args.min_selected_model_signal_weight,
        require_source_status_generated=not args.allow_source_status_not_generated,
        require_no_public_prediction_change=not args.allow_public_prediction_change,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalPoissonParameterAdmissionCheck],
    decision_payload: Mapping[str, object],
) -> str:
    payload = {
        "summary": dict(summary),
        "checks": [check.model_dump(mode="json") for check in checks],
        "decision_payload": dict(decision_payload),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_poisson_parameter_admission:{digest}"


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _mapping_float(
    value: Mapping[str, object],
    key: str,
    *,
    default: float | None = None,
) -> float | None:
    raw_value = value.get(key, default)
    if isinstance(raw_value, bool):
        return float(raw_value)
    if isinstance(raw_value, int | float | str):
        return float(raw_value)
    return None


def _mapping_float_or_zero(value: Mapping[str, object], key: str) -> float:
    return _mapping_float(value, key, default=0.0) or 0.0


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float | str):
        return float(value)
    return None


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0
