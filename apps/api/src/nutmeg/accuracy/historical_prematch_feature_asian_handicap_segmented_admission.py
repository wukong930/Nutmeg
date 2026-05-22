from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_prematch_feature_asian_handicap_role_search import (
    HistoricalPrematchFeatureAsianHandicapRoleCandidate,
    HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    load_historical_prematch_feature_asian_handicap_role_search_report,
)

if TYPE_CHECKING:
    from nutmeg.accuracy.historical_prematch_feature_asian_handicap_calibration_sample_expansion import (  # noqa: E501
        HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport,
    )

type HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]
type HistoricalPrematchFeatureAsianHandicapSegmentStatus = Literal[
    "accepted",
    "shadow_only",
    "baseline_fallback",
    "rejected",
]
type HistoricalPrematchFeatureAsianHandicapSegmentCheckStatus = Literal[
    "passed",
    "failed",
]

DEFAULT_ASIAN_HANDICAP_SEGMENTED_ADMISSION_ID = (
    "prematch-feature-asian-handicap-segmented-admission-v3.2"
)


class HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions(BaseModel):
    admission_id: str = DEFAULT_ASIAN_HANDICAP_SEGMENTED_ADMISSION_ID
    min_source_report_count: int = Field(default=1, ge=1)
    min_accepted_segment_count: int = Field(default=1, ge=0)
    min_accepted_validation_count: int = Field(default=100, ge=0)
    min_candidate_count: int = Field(default=1, ge=0)
    min_accepted_nonzero_candidate_count: int = Field(default=1, ge=0)
    min_segment_validation_count: int = Field(default=40, ge=0)
    min_selected_effective_weight: float = Field(default=0.01, ge=0.0)
    min_selected_line_movement_weight: float = Field(default=0.01, ge=0.0)
    min_hit_rate_delta: float | None = 0.0
    max_brier_score_delta: float | None = 0.0
    max_log_loss_delta: float | None = 0.0
    max_expected_calibration_error_delta: float | None = 0.0
    min_average_actual_probability_delta: float | None = None
    max_warning_count: int | None = Field(default=0, ge=0)
    require_source_status_generated: bool = True
    require_source_shadow_only: bool = True
    require_selected_candidate_accepted: bool = True
    require_expected_calibration_error_delta: bool = True
    require_default_path_isolated: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True


class HistoricalPrematchFeatureAsianHandicapSegmentCheck(BaseModel):
    name: str
    status: HistoricalPrematchFeatureAsianHandicapSegmentCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalPrematchFeatureAsianHandicapSegmentDecision(BaseModel):
    segment_id: str
    source_report_key: str
    source_role_search_id: str
    status: HistoricalPrematchFeatureAsianHandicapSegmentStatus
    selected_candidate_id: str | None = None
    selected_candidate_status: str | None = None
    accepted_nonzero_candidate_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    validation_count: int = Field(default=0, ge=0)
    asian_handicap_movement_weight: float | None = Field(default=None, ge=0.0)
    min_asian_handicap_probability_delta: float | None = Field(default=None, ge=0.0)
    asian_handicap_line_movement_weight: float | None = Field(default=None, ge=0.0)
    min_asian_handicap_line_delta: float | None = Field(default=None, ge=0.0)
    asian_handicap_line_movement_transform: str | None = None
    hit_rate_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    expected_calibration_error_delta: float | None = None
    average_actual_probability_delta: float | None = None
    calibration_sample_expansion_report_key: str | None = None
    calibration_sample_expansion_applied: bool = False
    failure_reasons: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionStatus
    segmented_candidate_model_allowed: bool
    shadow_allowed: bool
    default_path_isolated: bool
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    admission_id: str
    source_report_count: int = Field(ge=0)
    accepted_segment_count: int = Field(ge=0)
    shadow_segment_count: int = Field(ge=0)
    fallback_segment_count: int = Field(ge=0)
    rejected_segment_count: int = Field(ge=0)
    calibration_sample_expansion_report_count: int = Field(default=0, ge=0)
    calibration_sample_expansion_applied_count: int = Field(default=0, ge=0)
    accepted_validation_count: int = Field(ge=0)
    shadow_validation_count: int = Field(ge=0)
    fallback_validation_count: int = Field(ge=0)
    accepted_segment_deltas_json: dict[str, object] = Field(default_factory=dict)
    accepted_segment_ids: list[str] = Field(default_factory=list)
    fallback_segment_ids: list[str] = Field(default_factory=list)
    shadow_segment_ids: list[str] = Field(default_factory=list)
    rejected_segment_ids: list[str] = Field(default_factory=list)
    decisions: list[HistoricalPrematchFeatureAsianHandicapSegmentDecision] = Field(
        default_factory=list
    )
    checks: list[HistoricalPrematchFeatureAsianHandicapSegmentCheck] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    decision_payload_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_prematch_feature_asian_handicap_segmented_admission_report(
    path: Path | str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport:
    return (
        HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    )


def build_historical_prematch_feature_asian_handicap_segmented_admission_report(
    source_reports: Sequence[HistoricalPrematchFeatureAsianHandicapRoleSearchReport],
    *,
    calibration_sample_expansion_reports: Sequence[
        HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport
    ] = (),
    options: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions | None = None,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport:
    resolved_options = (
        options or HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions()
    )
    decisions = [
        _segment_decision(
            report,
            calibration_sample_expansion_reports=calibration_sample_expansion_reports,
            options=resolved_options,
        )
        for report in source_reports
    ]
    metrics = _segment_metrics(decisions)
    checks = _checks(
        source_reports,
        decisions=decisions,
        metrics=metrics,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    segmented_candidate_model_allowed = not failed_checks
    shadow_allowed = bool(source_reports) and any(
        decision.status in {"accepted", "shadow_only", "baseline_fallback"}
        for decision in decisions
    )
    status = _status(
        segmented_candidate_model_allowed=segmented_candidate_model_allowed,
        shadow_allowed=shadow_allowed,
    )
    default_path_isolated = True
    warnings = _warnings(status=status, checks=checks, decisions=decisions)
    decision_payload = _decision_payload(
        source_reports,
        decisions=decisions,
        metrics=metrics,
        status=status,
        segmented_candidate_model_allowed=segmented_candidate_model_allowed,
        shadow_allowed=shadow_allowed,
        default_path_isolated=default_path_isolated,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_segmented_admission_v3_2"
        ),
        "admission_id": resolved_options.admission_id,
        "status": status,
        "segmented_candidate_model_allowed": segmented_candidate_model_allowed,
        "shadow_allowed": shadow_allowed,
        "default_path_isolated": default_path_isolated,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "source_report_count": len(source_reports),
        "calibration_sample_expansion_report_count": len(
            calibration_sample_expansion_reports
        ),
        **metrics,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, decisions, decision_payload)
    return HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionReport(
        report_key=report_key,
        status=status,
        segmented_candidate_model_allowed=segmented_candidate_model_allowed,
        shadow_allowed=shadow_allowed,
        default_path_isolated=default_path_isolated,
        production_recommendation_changed=False,
        public_response_changed=False,
        admission_id=resolved_options.admission_id,
        source_report_count=len(source_reports),
        accepted_segment_count=_int(metrics["accepted_segment_count"]),
        shadow_segment_count=_int(metrics["shadow_segment_count"]),
        fallback_segment_count=_int(metrics["fallback_segment_count"]),
        rejected_segment_count=_int(metrics["rejected_segment_count"]),
        calibration_sample_expansion_report_count=len(
            calibration_sample_expansion_reports
        ),
        calibration_sample_expansion_applied_count=_int(
            metrics["calibration_sample_expansion_applied_count"]
        ),
        accepted_validation_count=_int(metrics["accepted_validation_count"]),
        shadow_validation_count=_int(metrics["shadow_validation_count"]),
        fallback_validation_count=_int(metrics["fallback_validation_count"]),
        accepted_segment_deltas_json=_mapping_dict(
            metrics["accepted_segment_deltas_json"]
        ),
        accepted_segment_ids=_string_list(metrics["accepted_segment_ids"]),
        fallback_segment_ids=_string_list(metrics["fallback_segment_ids"]),
        shadow_segment_ids=_string_list(metrics["shadow_segment_ids"]),
        rejected_segment_ids=_string_list(metrics["rejected_segment_ids"]),
        decisions=decisions,
        checks=checks,
        warnings=warnings,
        decision_payload_json=decision_payload,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    source_reports = [
        load_historical_prematch_feature_asian_handicap_role_search_report(path)
        for path in args.segment_role_search_reports
    ]
    from nutmeg.accuracy.historical_prematch_feature_asian_handicap_calibration_sample_expansion import (  # noqa: E501
        load_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report,
    )

    calibration_sample_expansion_reports = [
        load_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report(
            path
        )
        for path in args.calibration_sample_expansion_reports
    ]
    report = build_historical_prematch_feature_asian_handicap_segmented_admission_report(
        source_reports,
        calibration_sample_expansion_reports=calibration_sample_expansion_reports,
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
    if not report.segmented_candidate_model_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _segment_decision(
    report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    *,
    calibration_sample_expansion_reports: Sequence[
        HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport
    ],
    options: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions,
) -> HistoricalPrematchFeatureAsianHandicapSegmentDecision:
    candidate = (
        report.best_accepted_candidate
        or report.best_effective_candidate
        or report.best_candidate
    )
    segment_id = _segment_id(report)
    calibration_sample_expansion = _applicable_calibration_sample_expansion(
        segment_id,
        report,
        candidate=candidate,
        calibration_sample_expansion_reports=calibration_sample_expansion_reports,
        options=options,
    )
    failure_reasons = _segment_failures(
        report,
        candidate=candidate,
        calibration_sample_expansion=calibration_sample_expansion,
        options=options,
    )
    status = _segment_status(candidate, failure_reasons)
    metric_deltas = candidate.metric_deltas_json if candidate is not None else {}
    expected_calibration_error_delta = _calibration_adjusted_ece_delta(
        metric_deltas,
        calibration_sample_expansion=calibration_sample_expansion,
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_segment_decision_v3_2"
        ),
        "segment_id": segment_id,
        "source_report_key": report.report_key,
        "source_role_search_id": report.role_search_id,
        "status": status,
        "selected_candidate_id": candidate.candidate_id if candidate else None,
        "selected_candidate_status": candidate.status if candidate else None,
        "accepted_nonzero_candidate_count": report.accepted_nonzero_candidate_count,
        "candidate_count": report.candidate_count,
        "validation_count": candidate.candidate_validation_count if candidate else 0,
        "calibration_sample_expansion_report_key": (
            calibration_sample_expansion.report_key
            if calibration_sample_expansion is not None
            else None
        ),
        "calibration_sample_expansion_applied": (
            calibration_sample_expansion is not None
        ),
        "asian_handicap_line_movement_transform": (
            candidate.asian_handicap_line_movement_transform if candidate else None
        ),
        "failure_reasons": failure_reasons,
        "warning_codes": report.warnings,
    }
    return HistoricalPrematchFeatureAsianHandicapSegmentDecision(
        segment_id=segment_id,
        source_report_key=report.report_key,
        source_role_search_id=report.role_search_id,
        status=status,
        selected_candidate_id=candidate.candidate_id if candidate else None,
        selected_candidate_status=candidate.status if candidate else None,
        accepted_nonzero_candidate_count=report.accepted_nonzero_candidate_count,
        candidate_count=report.candidate_count,
        validation_count=candidate.candidate_validation_count if candidate else 0,
        asian_handicap_movement_weight=(
            candidate.asian_handicap_movement_weight if candidate else None
        ),
        min_asian_handicap_probability_delta=(
            candidate.min_asian_handicap_probability_delta if candidate else None
        ),
        asian_handicap_line_movement_weight=(
            candidate.asian_handicap_line_movement_weight if candidate else None
        ),
        min_asian_handicap_line_delta=(
            candidate.min_asian_handicap_line_delta if candidate else None
        ),
        asian_handicap_line_movement_transform=(
            candidate.asian_handicap_line_movement_transform if candidate else None
        ),
        hit_rate_delta=_metric_delta(metric_deltas, "hit_rate"),
        brier_score_delta=_metric_delta(metric_deltas, "brier_score"),
        log_loss_delta=_metric_delta(metric_deltas, "log_loss"),
        expected_calibration_error_delta=expected_calibration_error_delta,
        average_actual_probability_delta=_metric_delta(
            metric_deltas,
            "average_actual_probability",
        ),
        calibration_sample_expansion_report_key=(
            calibration_sample_expansion.report_key
            if calibration_sample_expansion is not None
            else None
        ),
        calibration_sample_expansion_applied=calibration_sample_expansion is not None,
        failure_reasons=failure_reasons,
        warning_codes=report.warnings,
        summary_json=summary,
    )


def _segment_failures(
    report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    *,
    candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    calibration_sample_expansion: (
        HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport | None
    ),
    options: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions,
) -> list[str]:
    failures: list[str] = []
    if options.require_source_status_generated and str(report.status) != "generated":
        failures.append("source_status_not_generated")
    if options.require_source_shadow_only and not _source_shadow_only(report):
        failures.append("source_not_shadow_only")
    if report.candidate_count < options.min_candidate_count:
        failures.append("candidate_count_below_minimum")
    if (
        report.accepted_nonzero_candidate_count
        < options.min_accepted_nonzero_candidate_count
    ):
        failures.append("accepted_nonzero_candidate_count_below_minimum")
    if report.best_accepted_candidate is None:
        failures.append("missing_best_accepted_candidate")
    if candidate is None:
        return failures
    if options.require_selected_candidate_accepted and candidate.status != "accepted":
        failures.append("selected_candidate_not_accepted")
    if not candidate.passed_non_regression_gate:
        failures.append("selected_candidate_failed_non_regression_gate")
    if candidate.candidate_validation_count < options.min_segment_validation_count:
        failures.append("validation_count_below_minimum")
    effective_weight = max(
        candidate.asian_handicap_movement_weight,
        candidate.asian_handicap_line_movement_weight,
    )
    if effective_weight < options.min_selected_effective_weight:
        failures.append("selected_effective_weight_below_minimum")
    if (
        candidate.asian_handicap_line_movement_weight
        < options.min_selected_line_movement_weight
    ):
        failures.append("selected_line_movement_weight_below_minimum")
    failures.extend(
        _metric_failures(
            candidate.metric_deltas_json,
            calibration_sample_expansion=calibration_sample_expansion,
            options=options,
        )
    )
    if (
        options.max_warning_count is not None
        and len(report.warnings) > options.max_warning_count
    ):
        failures.append("source_warning_count_above_maximum")
    return failures


def _metric_failures(
    metric_deltas_json: Mapping[str, object],
    *,
    calibration_sample_expansion: (
        HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport | None
    ),
    options: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions,
) -> list[str]:
    failures: list[str] = []
    if not _meets_min(
        _metric_delta(metric_deltas_json, "hit_rate"),
        options.min_hit_rate_delta,
    ):
        failures.append("hit_rate_delta_below_minimum")
    if not _meets_max(
        _metric_delta(metric_deltas_json, "brier_score"),
        options.max_brier_score_delta,
    ):
        failures.append("brier_score_delta_above_maximum")
    if not _meets_max(
        _metric_delta(metric_deltas_json, "log_loss"),
        options.max_log_loss_delta,
    ):
        failures.append("log_loss_delta_above_maximum")
    ece_delta = _calibration_adjusted_ece_delta(
        metric_deltas_json,
        calibration_sample_expansion=calibration_sample_expansion,
    )
    if ece_delta is None:
        if options.require_expected_calibration_error_delta:
            failures.append("expected_calibration_error_delta_missing")
    elif not _meets_max(ece_delta, options.max_expected_calibration_error_delta):
        failures.append("expected_calibration_error_delta_above_maximum")
    if not _meets_min(
        _metric_delta(metric_deltas_json, "average_actual_probability"),
        options.min_average_actual_probability_delta,
    ):
        failures.append("average_actual_probability_delta_below_minimum")
    return failures


def _applicable_calibration_sample_expansion(
    segment_id: str,
    report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    *,
    candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    calibration_sample_expansion_reports: Sequence[
        HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport
    ],
    options: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions,
) -> HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport | None:
    for calibration_report in calibration_sample_expansion_reports:
        if not _calibration_sample_expansion_matches_segment(
            calibration_report,
            segment_id=segment_id,
            report=report,
        ):
            continue
        if _calibration_sample_expansion_is_usable(
            calibration_report,
            candidate=candidate,
            options=options,
        ):
            return calibration_report
    return None


def _calibration_sample_expansion_matches_segment(
    calibration_report: HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport,
    *,
    segment_id: str,
    report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
) -> bool:
    return (
        calibration_report.strict_role_search_report_key == report.report_key
        or calibration_report.target_segment_id == segment_id
        or calibration_report.target_segment_id == report.role_search_id
    )


def _calibration_sample_expansion_is_usable(
    calibration_report: HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport,
    *,
    candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    options: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions,
) -> bool:
    if candidate is None:
        return False
    if calibration_report.status != "measurement_ready":
        return False
    if not calibration_report.calibration_measurement_ready:
        return False
    if calibration_report.activation_allowed:
        return False
    if not calibration_report.default_path_isolated:
        return False
    if calibration_report.production_recommendation_changed:
        return False
    if calibration_report.public_response_changed:
        return False
    if calibration_report.strict_selected_candidate_id != candidate.candidate_id:
        return False
    if calibration_report.strict_expected_calibration_error_delta is not None:
        return False
    if calibration_report.relaxed_expected_calibration_error_delta is None:
        return False
    if (
        calibration_report.relaxed_validation_count
        < options.min_segment_validation_count
    ):
        return False
    return (
        _meets_min(calibration_report.relaxed_hit_rate_delta, options.min_hit_rate_delta)
        and _meets_max(
            calibration_report.relaxed_brier_score_delta,
            options.max_brier_score_delta,
        )
        and _meets_max(
            calibration_report.relaxed_log_loss_delta,
            options.max_log_loss_delta,
        )
        and _meets_max(
            calibration_report.relaxed_expected_calibration_error_delta,
            options.max_expected_calibration_error_delta,
        )
    )


def _calibration_adjusted_ece_delta(
    metric_deltas_json: Mapping[str, object],
    *,
    calibration_sample_expansion: (
        HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport | None
    ),
) -> float | None:
    if calibration_sample_expansion is not None:
        return calibration_sample_expansion.relaxed_expected_calibration_error_delta
    return _metric_delta(metric_deltas_json, "expected_calibration_error")


def _segment_status(
    candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    failure_reasons: Sequence[str],
) -> HistoricalPrematchFeatureAsianHandicapSegmentStatus:
    if not failure_reasons:
        return "accepted"
    if candidate is None or "source_status_not_generated" in failure_reasons:
        return "rejected"
    if any(reason in _HARD_FALLBACK_REASONS for reason in failure_reasons):
        return "baseline_fallback"
    return "shadow_only"


_HARD_FALLBACK_REASONS = {
    "selected_candidate_failed_non_regression_gate",
    "hit_rate_delta_below_minimum",
    "brier_score_delta_above_maximum",
    "log_loss_delta_above_maximum",
    "average_actual_probability_delta_below_minimum",
}


def _segment_metrics(
    decisions: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentDecision],
) -> dict[str, object]:
    accepted = [decision for decision in decisions if decision.status == "accepted"]
    shadow = [decision for decision in decisions if decision.status == "shadow_only"]
    fallback = [
        decision for decision in decisions if decision.status == "baseline_fallback"
    ]
    rejected = [decision for decision in decisions if decision.status == "rejected"]
    return {
        "accepted_segment_count": len(accepted),
        "shadow_segment_count": len(shadow),
        "fallback_segment_count": len(fallback),
        "rejected_segment_count": len(rejected),
        "calibration_sample_expansion_applied_count": sum(
            1 for decision in decisions if decision.calibration_sample_expansion_applied
        ),
        "accepted_validation_count": sum(
            decision.validation_count for decision in accepted
        ),
        "shadow_validation_count": sum(decision.validation_count for decision in shadow),
        "fallback_validation_count": sum(
            decision.validation_count for decision in fallback
        ),
        "accepted_segment_deltas_json": _weighted_delta_summary(accepted),
        "accepted_segment_ids": [decision.segment_id for decision in accepted],
        "shadow_segment_ids": [decision.segment_id for decision in shadow],
        "fallback_segment_ids": [decision.segment_id for decision in fallback],
        "rejected_segment_ids": [decision.segment_id for decision in rejected],
    }


def _weighted_delta_summary(
    decisions: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentDecision],
) -> dict[str, object]:
    return {
        "hit_rate_delta": _weighted_decision_delta(decisions, "hit_rate_delta"),
        "brier_score_delta": _weighted_decision_delta(decisions, "brier_score_delta"),
        "log_loss_delta": _weighted_decision_delta(decisions, "log_loss_delta"),
        "expected_calibration_error_delta": _weighted_decision_delta(
            decisions,
            "expected_calibration_error_delta",
        ),
        "average_actual_probability_delta": _weighted_decision_delta(
            decisions,
            "average_actual_probability_delta",
        ),
    }


def _weighted_decision_delta(
    decisions: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentDecision],
    field_name: str,
) -> float | None:
    weighted_total = 0.0
    weight_total = 0
    for decision in decisions:
        value = getattr(decision, field_name)
        if value is None:
            continue
        weighted_total += value * decision.validation_count
        weight_total += decision.validation_count
    if weight_total == 0:
        return None
    return weighted_total / weight_total


def _checks(
    source_reports: Sequence[HistoricalPrematchFeatureAsianHandicapRoleSearchReport],
    *,
    decisions: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentDecision],
    metrics: Mapping[str, object],
    options: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions,
) -> list[HistoricalPrematchFeatureAsianHandicapSegmentCheck]:
    default_path_isolated = True
    production_recommendation_changed = False
    public_response_changed = False
    checks = [
        _check_min(
            "source_report_count",
            len(source_reports),
            options.min_source_report_count,
            detail="segmented admission needs enough source role-search reports",
        ),
        _check_min(
            "accepted_segment_count",
            _int(metrics["accepted_segment_count"]),
            options.min_accepted_segment_count,
            detail="at least one segment must pass strict local no-harm",
        ),
        _check_min(
            "accepted_validation_count",
            _int(metrics["accepted_validation_count"]),
            options.min_accepted_validation_count,
            detail="accepted segments need enough held-out validation samples",
        ),
        _check_metric_min(
            "accepted_hit_rate_delta",
            _delta_from_summary(metrics, "hit_rate_delta"),
            options.min_hit_rate_delta,
            detail="accepted segments must not reduce held-out hit rate",
        ),
        _check_metric_max(
            "accepted_brier_score_delta",
            _delta_from_summary(metrics, "brier_score_delta"),
            options.max_brier_score_delta,
            detail="accepted segments must not worsen Brier score",
        ),
        _check_metric_max(
            "accepted_log_loss_delta",
            _delta_from_summary(metrics, "log_loss_delta"),
            options.max_log_loss_delta,
            detail="accepted segments must not worsen log loss",
        ),
        _check_metric_max(
            "accepted_expected_calibration_error_delta",
            _delta_from_summary(metrics, "expected_calibration_error_delta"),
            options.max_expected_calibration_error_delta,
            detail="accepted segments must not worsen calibration",
            require_value=options.require_expected_calibration_error_delta,
        ),
        _check_metric_min(
            "accepted_average_actual_probability_delta",
            _delta_from_summary(metrics, "average_actual_probability_delta"),
            options.min_average_actual_probability_delta,
            detail="accepted segments must not reduce actual-outcome probability",
        ),
        _check_bool(
            "default_path_isolated",
            default_path_isolated,
            True,
            detail="segmented admission evidence must not change the default path",
        ),
        _check_bool(
            "production_recommendation_changed",
            production_recommendation_changed,
            False,
            detail="segmented admission evidence must not change production output",
        ),
        _check_bool(
            "public_response_changed",
            public_response_changed,
            False,
            detail="segmented admission evidence must not change public responses",
        ),
    ]
    if not options.require_default_path_isolated:
        checks = [
            check for check in checks if check.name != "default_path_isolated"
        ]
    if not options.require_no_production_change:
        checks = [
            check
            for check in checks
            if check.name != "production_recommendation_changed"
        ]
    if not options.require_no_public_response_change:
        checks = [
            check for check in checks if check.name != "public_response_changed"
        ]
    return checks


def _decision_payload(
    source_reports: Sequence[HistoricalPrematchFeatureAsianHandicapRoleSearchReport],
    *,
    decisions: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentDecision],
    metrics: Mapping[str, object],
    status: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionStatus,
    segmented_candidate_model_allowed: bool,
    shadow_allowed: bool,
    default_path_isolated: bool,
    options: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_segmented_admission_decision_v3_2"
        ),
        "status": status,
        "segmented_candidate_model_allowed": segmented_candidate_model_allowed,
        "shadow_allowed": shadow_allowed,
        "default_path_isolated": default_path_isolated,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "source_report_keys": [report.report_key for report in source_reports],
        "metrics": dict(metrics),
        "decisions": [decision.model_dump(mode="json") for decision in decisions],
        "fallback_policy": {
            "accepted_segments": "candidate_line_aware_asian_handicap_role",
            "shadow_segments": "research_only_until_missing_or_unstable_evidence_clears",
            "baseline_fallback_segments": "baseline_prediction_path",
            "rejected_segments": "ignored",
        },
        "options": options.model_dump(mode="json"),
    }


def _status(
    *,
    segmented_candidate_model_allowed: bool,
    shadow_allowed: bool,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionStatus:
    if segmented_candidate_model_allowed:
        return "accepted"
    if shadow_allowed:
        return "shadow_only"
    return "rejected"


def _warnings(
    *,
    status: HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionStatus,
    checks: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentCheck],
    decisions: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentDecision],
) -> list[str]:
    warnings = [
        f"asian_handicap_segmented_admission:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    warnings.extend(
        (
            "asian_handicap_segmented_admission:"
            f"{decision.status}:{decision.segment_id}"
        )
        for decision in decisions
        if decision.status != "accepted"
    )
    warnings.append(f"asian_handicap_segmented_admission:{status}")
    return warnings


def _source_shadow_only(
    report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
) -> bool:
    value = report.summary_json.get("shadow_only")
    return value is True


def _segment_id(report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport) -> str:
    summary_segment = report.summary_json.get("segment_id")
    if isinstance(summary_segment, str) and summary_segment:
        return summary_segment
    return report.role_search_id


def _metric_delta(metric_deltas_json: Mapping[str, object], metric_name: str) -> float | None:
    metric_json = metric_deltas_json.get(metric_name)
    if not isinstance(metric_json, Mapping):
        return None
    value = metric_json.get("delta")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _delta_from_summary(metrics: Mapping[str, object], metric_name: str) -> float | None:
    deltas = metrics.get("accepted_segment_deltas_json")
    if not isinstance(deltas, Mapping):
        return None
    value = deltas.get(metric_name)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _meets_min(value: float | None, threshold: float | None) -> bool:
    if threshold is None:
        return True
    return value is not None and value >= threshold


def _meets_max(value: float | None, threshold: float | None) -> bool:
    if threshold is None:
        return True
    return value is not None and value <= threshold


def _check_min(
    name: str,
    actual: int | float,
    threshold: int | float,
    *,
    detail: str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentCheck:
    return HistoricalPrematchFeatureAsianHandicapSegmentCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_bool(
    name: str,
    actual: bool,
    threshold: bool,
    *,
    detail: str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentCheck:
    return HistoricalPrematchFeatureAsianHandicapSegmentCheck(
        name=name,
        status="passed" if actual is threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_metric_min(
    name: str,
    actual: float | None,
    threshold: float | None,
    *,
    detail: str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentCheck:
    return HistoricalPrematchFeatureAsianHandicapSegmentCheck(
        name=name,
        status="passed" if _meets_min(actual, threshold) else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_metric_max(
    name: str,
    actual: float | None,
    threshold: float | None,
    *,
    detail: str,
    require_value: bool = True,
) -> HistoricalPrematchFeatureAsianHandicapSegmentCheck:
    if threshold is None:
        status: HistoricalPrematchFeatureAsianHandicapSegmentCheckStatus = "passed"
    elif actual is None and not require_value:
        status = "passed"
    else:
        status = "passed" if _meets_max(actual, threshold) else "failed"
    return HistoricalPrematchFeatureAsianHandicapSegmentCheck(
        name=name,
        status=status,
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Admit line-aware Asian-handicap pre-match roles segment by segment, "
            "leaving weak segments on the baseline fallback path."
        )
    )
    parser.add_argument(
        "--segment-role-search-report",
        dest="segment_role_search_reports",
        action="append",
        type=Path,
        default=[],
        required=True,
    )
    parser.add_argument(
        "--calibration-sample-expansion-report",
        dest="calibration_sample_expansion_reports",
        action="append",
        type=Path,
        default=[],
    )
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--admission-id",
        default=DEFAULT_ASIAN_HANDICAP_SEGMENTED_ADMISSION_ID,
    )
    parser.add_argument("--min-source-report-count", type=int, default=1)
    parser.add_argument("--min-accepted-segment-count", type=int, default=1)
    parser.add_argument("--min-accepted-validation-count", type=int, default=100)
    parser.add_argument("--min-candidate-count", type=int, default=1)
    parser.add_argument("--min-accepted-nonzero-candidate-count", type=int, default=1)
    parser.add_argument("--min-segment-validation-count", type=int, default=40)
    parser.add_argument("--min-selected-effective-weight", type=float, default=0.01)
    parser.add_argument("--min-selected-line-movement-weight", type=float, default=0.01)
    parser.add_argument("--min-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--max-expected-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-average-actual-probability-delta", type=float)
    parser.add_argument("--max-warning-count", type=int, default=0)
    parser.add_argument("--allow-source-not-generated", action="store_true")
    parser.add_argument("--allow-source-not-shadow-only", action="store_true")
    parser.add_argument("--allow-selected-candidate-not-accepted", action="store_true")
    parser.add_argument("--allow-missing-calibration-delta", action="store_true")
    parser.add_argument("--allow-default-path-not-isolated", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions:
    return HistoricalPrematchFeatureAsianHandicapSegmentedAdmissionOptions(
        admission_id=args.admission_id,
        min_source_report_count=args.min_source_report_count,
        min_accepted_segment_count=args.min_accepted_segment_count,
        min_accepted_validation_count=args.min_accepted_validation_count,
        min_candidate_count=args.min_candidate_count,
        min_accepted_nonzero_candidate_count=args.min_accepted_nonzero_candidate_count,
        min_segment_validation_count=args.min_segment_validation_count,
        min_selected_effective_weight=args.min_selected_effective_weight,
        min_selected_line_movement_weight=args.min_selected_line_movement_weight,
        min_hit_rate_delta=args.min_hit_rate_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_expected_calibration_error_delta=(
            args.max_expected_calibration_error_delta
        ),
        min_average_actual_probability_delta=args.min_average_actual_probability_delta,
        max_warning_count=args.max_warning_count,
        require_source_status_generated=not args.allow_source_not_generated,
        require_source_shadow_only=not args.allow_source_not_shadow_only,
        require_selected_candidate_accepted=(
            not args.allow_selected_candidate_not_accepted
        ),
        require_expected_calibration_error_delta=(
            not args.allow_missing_calibration_delta
        ),
        require_default_path_isolated=not args.allow_default_path_not_isolated,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentCheck],
    decisions: Sequence[HistoricalPrematchFeatureAsianHandicapSegmentDecision],
    decision_payload: Mapping[str, object],
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "decisions": [decision.model_dump(mode="json") for decision in decisions],
        "decision_payload": decision_payload,
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return (
        "historical_prematch_feature_asian_handicap_segmented_admission:"
        f"{digest}"
    )


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _mapping_dict(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): nested_value for key, nested_value in value.items()}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [str(item) for item in value]
