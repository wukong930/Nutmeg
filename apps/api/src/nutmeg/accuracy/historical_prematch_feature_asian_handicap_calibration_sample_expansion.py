from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_prematch_feature_asian_handicap_role_search import (
    HistoricalPrematchFeatureAsianHandicapRoleCandidate,
    HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    load_historical_prematch_feature_asian_handicap_role_search_report,
)
from nutmeg.accuracy.historical_prematch_feature_asian_handicap_segment_refinement import (
    HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision,
    HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport,
    load_historical_prematch_feature_asian_handicap_segment_refinement_report,
)

type HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionStatus = Literal[
    "measurement_ready",
    "shadow_only",
    "blocked",
]
type HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheckStatus = (
    Literal["passed", "failed"]
)

DEFAULT_ASIAN_HANDICAP_CALIBRATION_SAMPLE_EXPANSION_ID = (
    "prematch-feature-asian-handicap-calibration-sample-expansion-v3.2"
)


class HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions(BaseModel):
    experiment_id: str = DEFAULT_ASIAN_HANDICAP_CALIBRATION_SAMPLE_EXPANSION_ID
    target_segment_id: str | None = None
    min_validation_count: int = Field(default=40, ge=0)
    min_hit_rate_delta: float | None = 0.0
    max_brier_score_delta: float | None = 0.0
    max_log_loss_delta: float | None = 0.0
    max_expected_calibration_error_delta: float | None = 0.0
    require_refinement_ready: bool = True
    require_refinement_decision: bool = True
    require_refinement_action: bool = True
    require_strict_calibration_missing: bool = True
    require_relaxed_calibration_measurable: bool = True
    require_relaxed_bucket_floor_lower_than_strict: bool = True
    require_same_candidate_parameters: bool = True
    require_no_default_path_change: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True


class HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck(BaseModel):
    name: str
    status: HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport(BaseModel):
    report_key: str
    status: HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionStatus
    experiment_id: str
    target_segment_id: str
    source_refinement_report_key: str
    strict_role_search_report_key: str
    relaxed_role_search_report_key: str
    calibration_measurement_ready: bool
    activation_allowed: bool = False
    default_path_isolated: bool
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    strict_min_bucket_sample_size: int | None = None
    relaxed_min_bucket_sample_size: int | None = None
    strict_bucket_size: float | None = None
    relaxed_bucket_size: float | None = None
    strict_selected_candidate_id: str | None = None
    relaxed_selected_candidate_id: str | None = None
    strict_expected_calibration_error_delta: float | None = None
    relaxed_expected_calibration_error_delta: float | None = None
    relaxed_hit_rate_delta: float | None = None
    relaxed_brier_score_delta: float | None = None
    relaxed_log_loss_delta: float | None = None
    relaxed_average_actual_probability_delta: float | None = None
    relaxed_validation_count: int = Field(ge=0)
    checks: list[
        HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck
    ] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    decision_payload_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report(
    path: Path | str,
) -> HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport:
    return (
        HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    )


def build_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report(
    refinement_report: HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport,
    strict_role_search_report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    relaxed_role_search_report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    *,
    options: HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions
    | None = None,
) -> HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport:
    resolved_options = (
        options
        or HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions()
    )
    target_segment_id = _target_segment_id(refinement_report, options=resolved_options)
    refinement_decision = _refinement_decision(refinement_report, target_segment_id)
    strict_candidate = _selected_candidate(strict_role_search_report)
    relaxed_candidate = _selected_candidate(relaxed_role_search_report)
    strict_poisson_options = _poisson_options(strict_role_search_report)
    relaxed_poisson_options = _poisson_options(relaxed_role_search_report)
    metrics = _metrics(
        target_segment_id,
        strict_candidate=strict_candidate,
        relaxed_candidate=relaxed_candidate,
        strict_poisson_options=strict_poisson_options,
        relaxed_poisson_options=relaxed_poisson_options,
    )
    checks = _checks(
        refinement_report,
        target_segment_id=target_segment_id,
        refinement_decision=refinement_decision,
        strict_role_search_report=strict_role_search_report,
        relaxed_role_search_report=relaxed_role_search_report,
        strict_candidate=strict_candidate,
        relaxed_candidate=relaxed_candidate,
        metrics=metrics,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    calibration_measurement_ready = not failed_checks
    status = _status(
        calibration_measurement_ready=calibration_measurement_ready,
        checks=checks,
    )
    warnings = _warnings(status=status, checks=checks)
    decision_payload = _decision_payload(
        refinement_report,
        strict_role_search_report,
        relaxed_role_search_report,
        target_segment_id=target_segment_id,
        refinement_decision=refinement_decision,
        strict_candidate=strict_candidate,
        relaxed_candidate=relaxed_candidate,
        metrics=metrics,
        status=status,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_calibration_sample_expansion_v3_2"
        ),
        "experiment_id": resolved_options.experiment_id,
        "target_segment_id": target_segment_id,
        "source_refinement_report_key": refinement_report.report_key,
        "strict_role_search_report_key": strict_role_search_report.report_key,
        "relaxed_role_search_report_key": relaxed_role_search_report.report_key,
        "status": status,
        "calibration_measurement_ready": calibration_measurement_ready,
        "activation_allowed": False,
        "default_path_isolated": refinement_report.default_path_isolated,
        "production_recommendation_changed": (
            refinement_report.production_recommendation_changed
        ),
        "public_response_changed": refinement_report.public_response_changed,
        **metrics,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, decision_payload)
    return HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionReport(
        report_key=report_key,
        status=status,
        experiment_id=resolved_options.experiment_id,
        target_segment_id=target_segment_id,
        source_refinement_report_key=refinement_report.report_key,
        strict_role_search_report_key=strict_role_search_report.report_key,
        relaxed_role_search_report_key=relaxed_role_search_report.report_key,
        calibration_measurement_ready=calibration_measurement_ready,
        activation_allowed=False,
        default_path_isolated=refinement_report.default_path_isolated,
        production_recommendation_changed=(
            refinement_report.production_recommendation_changed
        ),
        public_response_changed=refinement_report.public_response_changed,
        strict_min_bucket_sample_size=_optional_int(
            metrics["strict_min_bucket_sample_size"]
        ),
        relaxed_min_bucket_sample_size=_optional_int(
            metrics["relaxed_min_bucket_sample_size"]
        ),
        strict_bucket_size=_optional_float(metrics["strict_bucket_size"]),
        relaxed_bucket_size=_optional_float(metrics["relaxed_bucket_size"]),
        strict_selected_candidate_id=(
            strict_candidate.candidate_id if strict_candidate is not None else None
        ),
        relaxed_selected_candidate_id=(
            relaxed_candidate.candidate_id if relaxed_candidate is not None else None
        ),
        strict_expected_calibration_error_delta=_optional_float(
            metrics["strict_expected_calibration_error_delta"]
        ),
        relaxed_expected_calibration_error_delta=_optional_float(
            metrics["relaxed_expected_calibration_error_delta"]
        ),
        relaxed_hit_rate_delta=_optional_float(metrics["relaxed_hit_rate_delta"]),
        relaxed_brier_score_delta=_optional_float(metrics["relaxed_brier_score_delta"]),
        relaxed_log_loss_delta=_optional_float(metrics["relaxed_log_loss_delta"]),
        relaxed_average_actual_probability_delta=_optional_float(
            metrics["relaxed_average_actual_probability_delta"]
        ),
        relaxed_validation_count=_int(metrics["relaxed_validation_count"]),
        checks=checks,
        warnings=warnings,
        decision_payload_json=decision_payload,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_prematch_feature_asian_handicap_calibration_sample_expansion_report(
        load_historical_prematch_feature_asian_handicap_segment_refinement_report(
            args.refinement_report
        ),
        load_historical_prematch_feature_asian_handicap_role_search_report(
            args.strict_role_search_report
        ),
        load_historical_prematch_feature_asian_handicap_role_search_report(
            args.relaxed_role_search_report
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
    if report.status == "blocked" and not args.no_fail_process:
        raise SystemExit(1)


def _target_segment_id(
    refinement_report: HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport,
    *,
    options: HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions,
) -> str:
    if options.target_segment_id:
        return options.target_segment_id
    for decision in refinement_report.decisions:
        if decision.recommended_action == "calibration_sample_expansion":
            return decision.segment_id
    if refinement_report.top_refinement_segment_ids:
        return refinement_report.top_refinement_segment_ids[0]
    return ""


def _refinement_decision(
    refinement_report: HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport,
    target_segment_id: str,
) -> HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision | None:
    for decision in refinement_report.decisions:
        if decision.segment_id == target_segment_id:
            return decision
    return None


def _selected_candidate(
    report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
) -> HistoricalPrematchFeatureAsianHandicapRoleCandidate | None:
    return (
        report.best_accepted_candidate
        or report.best_effective_candidate
        or report.best_candidate
    )


def _poisson_options(
    report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
) -> Mapping[str, object]:
    value = report.summary_json.get("poisson_options")
    return value if isinstance(value, Mapping) else {}


def _metrics(
    target_segment_id: str,
    *,
    strict_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    relaxed_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    strict_poisson_options: Mapping[str, object],
    relaxed_poisson_options: Mapping[str, object],
) -> dict[str, object]:
    return {
        "target_segment_id": target_segment_id,
        "strict_min_bucket_sample_size": _mapping_int(
            strict_poisson_options,
            "min_bucket_sample_size",
        ),
        "relaxed_min_bucket_sample_size": _mapping_int(
            relaxed_poisson_options,
            "min_bucket_sample_size",
        ),
        "strict_bucket_size": _mapping_float(strict_poisson_options, "bucket_size"),
        "relaxed_bucket_size": _mapping_float(relaxed_poisson_options, "bucket_size"),
        "strict_expected_calibration_error_delta": _candidate_delta(
            strict_candidate,
            "expected_calibration_error",
        ),
        "relaxed_expected_calibration_error_delta": _candidate_delta(
            relaxed_candidate,
            "expected_calibration_error",
        ),
        "relaxed_hit_rate_delta": _candidate_delta(relaxed_candidate, "hit_rate"),
        "relaxed_brier_score_delta": _candidate_delta(
            relaxed_candidate,
            "brier_score",
        ),
        "relaxed_log_loss_delta": _candidate_delta(relaxed_candidate, "log_loss"),
        "relaxed_average_actual_probability_delta": _candidate_delta(
            relaxed_candidate,
            "average_actual_probability",
        ),
        "relaxed_validation_count": (
            relaxed_candidate.candidate_validation_count
            if relaxed_candidate is not None
            else 0
        ),
        "same_candidate_parameters": _same_candidate_parameters(
            strict_candidate,
            relaxed_candidate,
        ),
    }


def _checks(
    refinement_report: HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport,
    *,
    target_segment_id: str,
    refinement_decision: HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision
    | None,
    strict_role_search_report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    relaxed_role_search_report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    strict_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    relaxed_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    metrics: Mapping[str, object],
    options: HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions,
) -> list[HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck]:
    checks = [
        _check_bool(
            "refinement_status_ready",
            refinement_report.status == "refinement_ready",
            True,
            detail="calibration sample expansion must start from a ready refinement report",
        ),
        _check_bool(
            "target_refinement_decision_present",
            refinement_decision is not None,
            True,
            detail="target segment must exist in the refinement report",
        ),
        _check_bool(
            "target_refinement_action",
            (
                refinement_decision is not None
                and refinement_decision.recommended_action
                == "calibration_sample_expansion"
            ),
            True,
            detail="target segment should be marked for calibration sample expansion",
        ),
        _check_bool(
            "strict_role_search_segment_matches",
            strict_role_search_report.role_search_id == target_segment_id,
            True,
            detail="strict role-search report should match the target segment",
        ),
        _check_bool(
            "relaxed_role_search_target_family",
            _role_search_family_matches(
                target_segment_id,
                relaxed_role_search_report.role_search_id,
            ),
            True,
            detail="relaxed role-search report should be a target-segment variant",
        ),
        _check_bool(
            "strict_selected_candidate_present",
            strict_candidate is not None,
            True,
            detail="strict report needs a selected candidate for comparison",
        ),
        _check_bool(
            "relaxed_selected_candidate_present",
            relaxed_candidate is not None,
            True,
            detail="relaxed report needs a selected candidate for comparison",
        ),
        _check_bool(
            "same_candidate_parameters",
            bool(metrics["same_candidate_parameters"]),
            True,
            detail="relaxed run should only change calibration measurability settings",
        ),
        _check_bool(
            "strict_calibration_missing",
            metrics["strict_expected_calibration_error_delta"] is None,
            True,
            detail="strict report should be missing ECE before sample expansion",
        ),
        _check_bool(
            "relaxed_calibration_measurable",
            metrics["relaxed_expected_calibration_error_delta"] is not None,
            True,
            detail="relaxed report should make ECE measurable",
        ),
        _check_bool(
            "relaxed_bucket_floor_lower_than_strict",
            _bucket_floor_lower_than_strict(metrics),
            True,
            detail="relaxed evidence must come from a lower bucket sample floor",
        ),
        _check_min(
            "relaxed_validation_count",
            _int(metrics["relaxed_validation_count"]),
            options.min_validation_count,
            detail="relaxed measurement needs enough validation samples",
        ),
        _check_metric_min(
            "relaxed_hit_rate_delta",
            _optional_float(metrics["relaxed_hit_rate_delta"]),
            options.min_hit_rate_delta,
            detail="relaxed measurement must not reduce hit rate",
        ),
        _check_metric_max(
            "relaxed_brier_score_delta",
            _optional_float(metrics["relaxed_brier_score_delta"]),
            options.max_brier_score_delta,
            detail="relaxed measurement must not worsen Brier score",
        ),
        _check_metric_max(
            "relaxed_log_loss_delta",
            _optional_float(metrics["relaxed_log_loss_delta"]),
            options.max_log_loss_delta,
            detail="relaxed measurement must not worsen log loss",
        ),
        _check_metric_max(
            "relaxed_expected_calibration_error_delta",
            _optional_float(metrics["relaxed_expected_calibration_error_delta"]),
            options.max_expected_calibration_error_delta,
            detail="relaxed measurement must not worsen ECE",
        ),
        _check_bool(
            "default_path_isolated",
            refinement_report.default_path_isolated,
            True,
            detail="measurement evidence must not change the default path",
        ),
        _check_bool(
            "production_recommendation_changed",
            refinement_report.production_recommendation_changed,
            False,
            detail="measurement evidence must not change production recommendations",
        ),
        _check_bool(
            "public_response_changed",
            refinement_report.public_response_changed,
            False,
            detail="measurement evidence must not change public responses",
        ),
        _check_bool(
            "activation_allowed",
            False,
            False,
            detail="calibration sample expansion is measurement-only evidence",
        ),
    ]
    if not options.require_refinement_ready:
        checks = [check for check in checks if check.name != "refinement_status_ready"]
    if not options.require_refinement_decision:
        checks = [
            check
            for check in checks
            if check.name != "target_refinement_decision_present"
        ]
    if not options.require_refinement_action:
        checks = [check for check in checks if check.name != "target_refinement_action"]
    if not options.require_strict_calibration_missing:
        checks = [check for check in checks if check.name != "strict_calibration_missing"]
    if not options.require_relaxed_calibration_measurable:
        checks = [
            check for check in checks if check.name != "relaxed_calibration_measurable"
        ]
    if not options.require_relaxed_bucket_floor_lower_than_strict:
        checks = [
            check
            for check in checks
            if check.name != "relaxed_bucket_floor_lower_than_strict"
        ]
    if not options.require_same_candidate_parameters:
        checks = [check for check in checks if check.name != "same_candidate_parameters"]
    if not options.require_no_default_path_change:
        checks = [check for check in checks if check.name != "default_path_isolated"]
    if not options.require_no_production_change:
        checks = [
            check
            for check in checks
            if check.name != "production_recommendation_changed"
        ]
    if not options.require_no_public_response_change:
        checks = [check for check in checks if check.name != "public_response_changed"]
    return checks


def _decision_payload(
    refinement_report: HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport,
    strict_role_search_report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    relaxed_role_search_report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    *,
    target_segment_id: str,
    refinement_decision: HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision
    | None,
    strict_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    relaxed_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    metrics: Mapping[str, object],
    status: HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionStatus,
    options: HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_calibration_sample_expansion_decision_v3_2"
        ),
        "status": status,
        "target_segment_id": target_segment_id,
        "source_refinement_report_key": refinement_report.report_key,
        "strict_role_search_report_key": strict_role_search_report.report_key,
        "relaxed_role_search_report_key": relaxed_role_search_report.report_key,
        "refinement_decision": (
            refinement_decision.model_dump(mode="json")
            if refinement_decision is not None
            else None
        ),
        "strict_candidate": (
            strict_candidate.model_dump(mode="json")
            if strict_candidate is not None
            else None
        ),
        "relaxed_candidate": (
            relaxed_candidate.model_dump(mode="json")
            if relaxed_candidate is not None
            else None
        ),
        "metrics": dict(metrics),
        "activation_allowed": False,
        "default_path_isolated": refinement_report.default_path_isolated,
        "production_recommendation_changed": (
            refinement_report.production_recommendation_changed
        ),
        "public_response_changed": refinement_report.public_response_changed,
        "options": options.model_dump(mode="json"),
    }


def _status(
    *,
    calibration_measurement_ready: bool,
    checks: Sequence[HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck],
) -> HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionStatus:
    hard_blockers = {
        "default_path_isolated",
        "production_recommendation_changed",
        "public_response_changed",
    }
    failed = {check.name for check in checks if check.status == "failed"}
    if failed & hard_blockers:
        return "blocked"
    if calibration_measurement_ready:
        return "measurement_ready"
    return "shadow_only"


def _warnings(
    *,
    status: HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionStatus,
    checks: Sequence[HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck],
) -> list[str]:
    warnings = [
        f"asian_handicap_calibration_sample_expansion:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    warnings.append(f"asian_handicap_calibration_sample_expansion:{status}")
    return warnings


def _candidate_delta(
    candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    metric_name: str,
) -> float | None:
    if candidate is None:
        return None
    metric_json = candidate.metric_deltas_json.get(metric_name)
    if not isinstance(metric_json, Mapping):
        return None
    value = metric_json.get("delta")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _same_candidate_parameters(
    strict_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    relaxed_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
) -> bool:
    if strict_candidate is None or relaxed_candidate is None:
        return False
    return (
        strict_candidate.asian_handicap_movement_weight
        == relaxed_candidate.asian_handicap_movement_weight
        and strict_candidate.min_asian_handicap_probability_delta
        == relaxed_candidate.min_asian_handicap_probability_delta
        and strict_candidate.asian_handicap_line_movement_weight
        == relaxed_candidate.asian_handicap_line_movement_weight
        and strict_candidate.min_asian_handicap_line_delta
        == relaxed_candidate.min_asian_handicap_line_delta
        and strict_candidate.asian_handicap_line_movement_scale
        == relaxed_candidate.asian_handicap_line_movement_scale
        and strict_candidate.asian_handicap_line_movement_transform
        == relaxed_candidate.asian_handicap_line_movement_transform
    )


def _role_search_family_matches(target_segment_id: str, role_search_id: str) -> bool:
    if role_search_id == target_segment_id or role_search_id.startswith(
        target_segment_id
    ):
        return True
    return any(
        bool(target_prefix) and role_search_id.startswith(target_prefix)
        for target_prefix in _role_search_family_prefixes(target_segment_id)
    )


def _role_search_family_prefixes(target_segment_id: str) -> tuple[str, ...]:
    prefixes = [target_segment_id.split("_role_search", maxsplit=1)[0]]
    if "_v" in target_segment_id:
        version_prefix, version_suffix = target_segment_id.rsplit("_v", maxsplit=1)
        if version_suffix.isdigit():
            prefixes.append(version_prefix)
    return tuple(dict.fromkeys(prefixes))


def _bucket_floor_lower_than_strict(metrics: Mapping[str, object]) -> bool:
    strict = _optional_int(metrics["strict_min_bucket_sample_size"])
    relaxed = _optional_int(metrics["relaxed_min_bucket_sample_size"])
    return strict is not None and relaxed is not None and relaxed < strict


def _mapping_int(mapping: Mapping[str, object], key: str) -> int | None:
    value = mapping.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _mapping_float(mapping: Mapping[str, object], key: str) -> float | None:
    value = mapping.get(key)
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


def _check_bool(
    name: str,
    actual: bool,
    threshold: bool,
    *,
    detail: str,
) -> HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck:
    return HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck(
        name=name,
        status="passed" if actual is threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_min(
    name: str,
    actual: int | float,
    threshold: int | float,
    *,
    detail: str,
) -> HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck:
    return HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
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
) -> HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck:
    return HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck(
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
) -> HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck:
    return HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck(
        name=name,
        status="passed" if _meets_max(actual, threshold) else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Compare strict and relaxed calibration-bucket evidence for a "
            "line-aware Asian-handicap segment without activating it."
        )
    )
    parser.add_argument("refinement_report", type=Path)
    parser.add_argument("strict_role_search_report", type=Path)
    parser.add_argument("relaxed_role_search_report", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--experiment-id",
        default=DEFAULT_ASIAN_HANDICAP_CALIBRATION_SAMPLE_EXPANSION_ID,
    )
    parser.add_argument("--target-segment-id")
    parser.add_argument("--min-validation-count", type=int, default=40)
    parser.add_argument("--min-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--max-expected-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--allow-refinement-not-ready", action="store_true")
    parser.add_argument("--allow-missing-refinement-decision", action="store_true")
    parser.add_argument("--allow-non-calibration-refinement-action", action="store_true")
    parser.add_argument("--allow-strict-calibration-measurable", action="store_true")
    parser.add_argument("--allow-relaxed-calibration-missing", action="store_true")
    parser.add_argument("--allow-same-or-higher-bucket-floor", action="store_true")
    parser.add_argument("--allow-candidate-parameter-drift", action="store_true")
    parser.add_argument("--allow-default-path-change", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions:
    return HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionOptions(
        experiment_id=args.experiment_id,
        target_segment_id=args.target_segment_id,
        min_validation_count=args.min_validation_count,
        min_hit_rate_delta=args.min_hit_rate_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_expected_calibration_error_delta=(
            args.max_expected_calibration_error_delta
        ),
        require_refinement_ready=not args.allow_refinement_not_ready,
        require_refinement_decision=not args.allow_missing_refinement_decision,
        require_refinement_action=not args.allow_non_calibration_refinement_action,
        require_strict_calibration_missing=not args.allow_strict_calibration_measurable,
        require_relaxed_calibration_measurable=(
            not args.allow_relaxed_calibration_missing
        ),
        require_relaxed_bucket_floor_lower_than_strict=(
            not args.allow_same_or_higher_bucket_floor
        ),
        require_same_candidate_parameters=not args.allow_candidate_parameter_drift,
        require_no_default_path_change=not args.allow_default_path_change,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[
        HistoricalPrematchFeatureAsianHandicapCalibrationSampleExpansionCheck
    ],
    decision_payload: Mapping[str, object],
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "decision_payload": decision_payload,
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return (
        "historical_prematch_feature_asian_handicap_calibration_sample_expansion:"
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


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None
