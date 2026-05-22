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

type HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementStatus = Literal[
    "scope_ready",
    "shadow_only",
    "blocked",
]
type HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheckStatus = (
    Literal["passed", "failed"]
)

DEFAULT_ASIAN_HANDICAP_CALIBRATION_SCOPE_REFINEMENT_ID = (
    "prematch-feature-asian-handicap-calibration-scope-refinement-v3.2"
)


class HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions(
    BaseModel
):
    experiment_id: str = DEFAULT_ASIAN_HANDICAP_CALIBRATION_SCOPE_REFINEMENT_ID
    target_segment_id: str | None = None
    min_scope_report_count: int = Field(default=1, ge=1)
    min_validation_count: int = Field(default=40, ge=0)
    min_hit_rate_delta: float | None = 0.0
    max_brier_score_delta: float | None = 0.0
    max_log_loss_delta: float | None = 0.0
    max_expected_calibration_error_delta: float | None = 0.0
    require_refinement_ready: bool = True
    require_refinement_action: bool = True
    require_source_calibration_regression: bool = True
    require_same_candidate_parameters: bool = True
    require_scope_change: bool = True
    require_no_default_path_change: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True


class HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck(
    BaseModel
):
    name: str
    status: HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalPrematchFeatureAsianHandicapCalibrationScopeAlternative(
    BaseModel
):
    role_search_id: str
    report_key: str
    candidate_id: str | None = None
    candidate_status: str | None = None
    bucket_size: float | None = None
    min_bucket_sample_size: int | None = None
    validation_count: int = Field(default=0, ge=0)
    same_candidate_parameters: bool = False
    calibration_scope_changed: bool = False
    passes_non_calibration_metrics: bool = False
    clears_calibration: bool = False
    hit_rate_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    expected_calibration_error_delta: float | None = None
    average_actual_probability_delta: float | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementReport(
    BaseModel
):
    report_key: str
    status: HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementStatus
    experiment_id: str
    target_segment_id: str
    source_refinement_report_key: str
    source_role_search_report_key: str
    scope_report_count: int = Field(ge=0)
    selected_scope_report_key: str | None = None
    selected_scope_role_search_id: str | None = None
    calibration_scope_ready: bool
    activation_allowed: bool = False
    default_path_isolated: bool
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    source_bucket_size: float | None = None
    source_min_bucket_sample_size: int | None = None
    source_expected_calibration_error_delta: float | None = None
    selected_bucket_size: float | None = None
    selected_min_bucket_sample_size: int | None = None
    selected_hit_rate_delta: float | None = None
    selected_brier_score_delta: float | None = None
    selected_log_loss_delta: float | None = None
    selected_expected_calibration_error_delta: float | None = None
    selected_average_actual_probability_delta: float | None = None
    selected_validation_count: int = Field(default=0, ge=0)
    scope_alternatives: list[
        HistoricalPrematchFeatureAsianHandicapCalibrationScopeAlternative
    ] = Field(default_factory=list)
    checks: list[
        HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck
    ] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    decision_payload_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_prematch_feature_asian_handicap_calibration_scope_refinement_report(
    path: Path | str,
) -> HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementReport:
    return (
        HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementReport.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    )


def build_historical_prematch_feature_asian_handicap_calibration_scope_refinement_report(
    refinement_report: HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport,
    source_role_search_report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    scope_role_search_reports: Sequence[
        HistoricalPrematchFeatureAsianHandicapRoleSearchReport
    ],
    *,
    options: HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions
    | None = None,
) -> HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementReport:
    resolved_options = (
        options
        or HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions()
    )
    target_segment_id = _target_segment_id(refinement_report, options=resolved_options)
    refinement_decision = _refinement_decision(refinement_report, target_segment_id)
    source_candidate = _selected_candidate(source_role_search_report)
    source_poisson_options = _poisson_options(source_role_search_report)
    alternatives = [
        _scope_alternative(
            scope_report,
            source_candidate=source_candidate,
            source_poisson_options=source_poisson_options,
            options=resolved_options,
        )
        for scope_report in scope_role_search_reports
    ]
    selected_alternative = _selected_alternative(alternatives)
    metrics = _metrics(
        target_segment_id,
        source_candidate=source_candidate,
        source_poisson_options=source_poisson_options,
        selected_alternative=selected_alternative,
    )
    checks = _checks(
        refinement_report,
        target_segment_id=target_segment_id,
        refinement_decision=refinement_decision,
        source_role_search_report=source_role_search_report,
        source_candidate=source_candidate,
        alternatives=alternatives,
        selected_alternative=selected_alternative,
        metrics=metrics,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    calibration_scope_ready = not failed_checks
    status = _status(calibration_scope_ready=calibration_scope_ready, checks=checks)
    warnings = _warnings(status=status, checks=checks)
    decision_payload = _decision_payload(
        refinement_report,
        source_role_search_report,
        scope_role_search_reports,
        target_segment_id=target_segment_id,
        refinement_decision=refinement_decision,
        source_candidate=source_candidate,
        selected_alternative=selected_alternative,
        alternatives=alternatives,
        status=status,
        metrics=metrics,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_calibration_scope_refinement_v3_2"
        ),
        "experiment_id": resolved_options.experiment_id,
        "target_segment_id": target_segment_id,
        "source_refinement_report_key": refinement_report.report_key,
        "source_role_search_report_key": source_role_search_report.report_key,
        "scope_report_count": len(scope_role_search_reports),
        "status": status,
        "calibration_scope_ready": calibration_scope_ready,
        "activation_allowed": False,
        "default_path_isolated": refinement_report.default_path_isolated,
        "production_recommendation_changed": (
            refinement_report.production_recommendation_changed
        ),
        "public_response_changed": refinement_report.public_response_changed,
        **metrics,
        "scope_alternatives": [
            alternative.model_dump(mode="json") for alternative in alternatives
        ],
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, decision_payload)
    return HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementReport(
        report_key=report_key,
        status=status,
        experiment_id=resolved_options.experiment_id,
        target_segment_id=target_segment_id,
        source_refinement_report_key=refinement_report.report_key,
        source_role_search_report_key=source_role_search_report.report_key,
        scope_report_count=len(scope_role_search_reports),
        selected_scope_report_key=(
            selected_alternative.report_key if selected_alternative is not None else None
        ),
        selected_scope_role_search_id=(
            selected_alternative.role_search_id
            if selected_alternative is not None
            else None
        ),
        calibration_scope_ready=calibration_scope_ready,
        activation_allowed=False,
        default_path_isolated=refinement_report.default_path_isolated,
        production_recommendation_changed=(
            refinement_report.production_recommendation_changed
        ),
        public_response_changed=refinement_report.public_response_changed,
        source_bucket_size=_optional_float(metrics["source_bucket_size"]),
        source_min_bucket_sample_size=_optional_int(
            metrics["source_min_bucket_sample_size"]
        ),
        source_expected_calibration_error_delta=_optional_float(
            metrics["source_expected_calibration_error_delta"]
        ),
        selected_bucket_size=_optional_float(metrics["selected_bucket_size"]),
        selected_min_bucket_sample_size=_optional_int(
            metrics["selected_min_bucket_sample_size"]
        ),
        selected_hit_rate_delta=_optional_float(metrics["selected_hit_rate_delta"]),
        selected_brier_score_delta=_optional_float(
            metrics["selected_brier_score_delta"]
        ),
        selected_log_loss_delta=_optional_float(metrics["selected_log_loss_delta"]),
        selected_expected_calibration_error_delta=_optional_float(
            metrics["selected_expected_calibration_error_delta"]
        ),
        selected_average_actual_probability_delta=_optional_float(
            metrics["selected_average_actual_probability_delta"]
        ),
        selected_validation_count=_int(metrics["selected_validation_count"]),
        scope_alternatives=alternatives,
        checks=checks,
        warnings=warnings,
        decision_payload_json=decision_payload,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    report = build_historical_prematch_feature_asian_handicap_calibration_scope_refinement_report(
        load_historical_prematch_feature_asian_handicap_segment_refinement_report(
            args.refinement_report
        ),
        load_historical_prematch_feature_asian_handicap_role_search_report(
            args.source_role_search_report
        ),
        [
            load_historical_prematch_feature_asian_handicap_role_search_report(path)
            for path in args.scope_role_search_reports
        ],
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
    options: HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions,
) -> str:
    if options.target_segment_id:
        return options.target_segment_id
    for decision in refinement_report.decisions:
        if decision.recommended_action == "calibration_scope_refinement":
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


def _scope_alternative(
    report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    *,
    source_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    source_poisson_options: Mapping[str, object],
    options: HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions,
) -> HistoricalPrematchFeatureAsianHandicapCalibrationScopeAlternative:
    candidate = _selected_candidate(report)
    poisson_options = _poisson_options(report)
    metric_deltas_json = candidate.metric_deltas_json if candidate is not None else {}
    same_candidate_parameters = _same_candidate_parameters(source_candidate, candidate)
    calibration_scope_changed = _calibration_scope_changed(
        source_poisson_options,
        poisson_options,
    )
    hit_rate_delta = _candidate_delta(candidate, "hit_rate")
    brier_score_delta = _candidate_delta(candidate, "brier_score")
    log_loss_delta = _candidate_delta(candidate, "log_loss")
    expected_calibration_error_delta = _candidate_delta(
        candidate,
        "expected_calibration_error",
    )
    passes_non_calibration_metrics = (
        _meets_min(hit_rate_delta, options.min_hit_rate_delta)
        and _meets_max(brier_score_delta, options.max_brier_score_delta)
        and _meets_max(log_loss_delta, options.max_log_loss_delta)
    )
    clears_calibration = _meets_max(
        expected_calibration_error_delta,
        options.max_expected_calibration_error_delta,
    )
    summary: dict[str, object] = {
        "role_search_id": report.role_search_id,
        "report_key": report.report_key,
        "candidate_id": candidate.candidate_id if candidate is not None else None,
        "candidate_status": candidate.status if candidate is not None else None,
        "bucket_size": _mapping_float(poisson_options, "bucket_size"),
        "min_bucket_sample_size": _mapping_int(
            poisson_options,
            "min_bucket_sample_size",
        ),
        "same_candidate_parameters": same_candidate_parameters,
        "calibration_scope_changed": calibration_scope_changed,
        "passes_non_calibration_metrics": passes_non_calibration_metrics,
        "clears_calibration": clears_calibration,
        "metric_deltas_json": metric_deltas_json,
    }
    return HistoricalPrematchFeatureAsianHandicapCalibrationScopeAlternative(
        role_search_id=report.role_search_id,
        report_key=report.report_key,
        candidate_id=candidate.candidate_id if candidate is not None else None,
        candidate_status=candidate.status if candidate is not None else None,
        bucket_size=_mapping_float(poisson_options, "bucket_size"),
        min_bucket_sample_size=_mapping_int(poisson_options, "min_bucket_sample_size"),
        validation_count=(
            candidate.candidate_validation_count if candidate is not None else 0
        ),
        same_candidate_parameters=same_candidate_parameters,
        calibration_scope_changed=calibration_scope_changed,
        passes_non_calibration_metrics=passes_non_calibration_metrics,
        clears_calibration=clears_calibration,
        hit_rate_delta=hit_rate_delta,
        brier_score_delta=brier_score_delta,
        log_loss_delta=log_loss_delta,
        expected_calibration_error_delta=expected_calibration_error_delta,
        average_actual_probability_delta=_candidate_delta(
            candidate,
            "average_actual_probability",
        ),
        summary_json=summary,
    )


def _selected_alternative(
    alternatives: Sequence[
        HistoricalPrematchFeatureAsianHandicapCalibrationScopeAlternative
    ],
) -> HistoricalPrematchFeatureAsianHandicapCalibrationScopeAlternative | None:
    viable = [
        alternative
        for alternative in alternatives
        if alternative.same_candidate_parameters
        and alternative.calibration_scope_changed
        and alternative.passes_non_calibration_metrics
    ]
    pool = viable or list(alternatives)
    if not pool:
        return None
    return sorted(
        pool,
        key=lambda item: (
            _none_last(item.expected_calibration_error_delta),
            -item.validation_count,
            item.role_search_id,
        ),
    )[0]


def _metrics(
    target_segment_id: str,
    *,
    source_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    source_poisson_options: Mapping[str, object],
    selected_alternative: (
        HistoricalPrematchFeatureAsianHandicapCalibrationScopeAlternative | None
    ),
) -> dict[str, object]:
    return {
        "target_segment_id": target_segment_id,
        "source_bucket_size": _mapping_float(source_poisson_options, "bucket_size"),
        "source_min_bucket_sample_size": _mapping_int(
            source_poisson_options,
            "min_bucket_sample_size",
        ),
        "source_expected_calibration_error_delta": _candidate_delta(
            source_candidate,
            "expected_calibration_error",
        ),
        "selected_scope_report_key": (
            selected_alternative.report_key
            if selected_alternative is not None
            else None
        ),
        "selected_scope_role_search_id": (
            selected_alternative.role_search_id
            if selected_alternative is not None
            else None
        ),
        "selected_bucket_size": (
            selected_alternative.bucket_size
            if selected_alternative is not None
            else None
        ),
        "selected_min_bucket_sample_size": (
            selected_alternative.min_bucket_sample_size
            if selected_alternative is not None
            else None
        ),
        "selected_validation_count": (
            selected_alternative.validation_count
            if selected_alternative is not None
            else 0
        ),
        "selected_hit_rate_delta": (
            selected_alternative.hit_rate_delta
            if selected_alternative is not None
            else None
        ),
        "selected_brier_score_delta": (
            selected_alternative.brier_score_delta
            if selected_alternative is not None
            else None
        ),
        "selected_log_loss_delta": (
            selected_alternative.log_loss_delta
            if selected_alternative is not None
            else None
        ),
        "selected_expected_calibration_error_delta": (
            selected_alternative.expected_calibration_error_delta
            if selected_alternative is not None
            else None
        ),
        "selected_average_actual_probability_delta": (
            selected_alternative.average_actual_probability_delta
            if selected_alternative is not None
            else None
        ),
        "selected_same_candidate_parameters": (
            selected_alternative.same_candidate_parameters
            if selected_alternative is not None
            else False
        ),
        "selected_calibration_scope_changed": (
            selected_alternative.calibration_scope_changed
            if selected_alternative is not None
            else False
        ),
    }


def _checks(
    refinement_report: HistoricalPrematchFeatureAsianHandicapSegmentRefinementReport,
    *,
    target_segment_id: str,
    refinement_decision: HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision
    | None,
    source_role_search_report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    source_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    alternatives: Sequence[
        HistoricalPrematchFeatureAsianHandicapCalibrationScopeAlternative
    ],
    selected_alternative: (
        HistoricalPrematchFeatureAsianHandicapCalibrationScopeAlternative | None
    ),
    metrics: Mapping[str, object],
    options: HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions,
) -> list[HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck]:
    source_calibration_delta = _optional_float(
        metrics["source_expected_calibration_error_delta"]
    )
    checks = [
        _check_bool(
            "refinement_status_ready",
            refinement_report.status == "refinement_ready",
            True,
            detail="calibration-scope refinement must start from a ready report",
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
                == "calibration_scope_refinement"
            ),
            True,
            detail="target segment should be marked for calibration-scope refinement",
        ),
        _check_bool(
            "source_role_search_segment_matches",
            source_role_search_report.role_search_id == target_segment_id,
            True,
            detail="source role-search report should match the target segment",
        ),
        _check_bool(
            "source_selected_candidate_present",
            source_candidate is not None,
            True,
            detail="source report needs a selected candidate for comparison",
        ),
        _check_bool(
            "source_calibration_regression_present",
            source_calibration_delta is not None and source_calibration_delta > 0,
            True,
            detail="scope refinement should target a measured calibration regression",
        ),
        _check_min(
            "scope_report_count",
            len(alternatives),
            options.min_scope_report_count,
            detail="scope refinement needs one or more replay reports",
        ),
        _check_bool(
            "selected_scope_candidate_present",
            selected_alternative is not None and selected_alternative.candidate_id is not None,
            True,
            detail="a scope replay needs a selected candidate",
        ),
        _check_bool(
            "same_candidate_parameters",
            bool(metrics["selected_same_candidate_parameters"]),
            True,
            detail="scope replay must keep the line-aware candidate parameters fixed",
        ),
        _check_bool(
            "calibration_scope_changed",
            bool(metrics["selected_calibration_scope_changed"]),
            True,
            detail="scope replay should only change calibration measurement scope",
        ),
        _check_min(
            "selected_validation_count",
            _int(metrics["selected_validation_count"]),
            options.min_validation_count,
            detail="selected scope replay needs enough validation samples",
        ),
        _check_metric_min(
            "selected_hit_rate_delta",
            _optional_float(metrics["selected_hit_rate_delta"]),
            options.min_hit_rate_delta,
            detail="scope replay must not reduce hit rate",
        ),
        _check_metric_max(
            "selected_brier_score_delta",
            _optional_float(metrics["selected_brier_score_delta"]),
            options.max_brier_score_delta,
            detail="scope replay must not worsen Brier score",
        ),
        _check_metric_max(
            "selected_log_loss_delta",
            _optional_float(metrics["selected_log_loss_delta"]),
            options.max_log_loss_delta,
            detail="scope replay must not worsen log loss",
        ),
        _check_metric_max(
            "selected_expected_calibration_error_delta",
            _optional_float(metrics["selected_expected_calibration_error_delta"]),
            options.max_expected_calibration_error_delta,
            detail="scope replay must clear the calibration regression",
        ),
        _check_bool(
            "default_path_isolated",
            refinement_report.default_path_isolated,
            True,
            detail="scope evidence must not change the default path",
        ),
        _check_bool(
            "production_recommendation_changed",
            refinement_report.production_recommendation_changed,
            False,
            detail="scope evidence must not change production recommendations",
        ),
        _check_bool(
            "public_response_changed",
            refinement_report.public_response_changed,
            False,
            detail="scope evidence must not change public responses",
        ),
        _check_bool(
            "activation_allowed",
            False,
            False,
            detail="calibration-scope refinement is measurement-only evidence",
        ),
    ]
    if not options.require_refinement_ready:
        checks = [check for check in checks if check.name != "refinement_status_ready"]
    if not options.require_refinement_action:
        checks = [check for check in checks if check.name != "target_refinement_action"]
    if not options.require_source_calibration_regression:
        checks = [
            check
            for check in checks
            if check.name != "source_calibration_regression_present"
        ]
    if not options.require_same_candidate_parameters:
        checks = [check for check in checks if check.name != "same_candidate_parameters"]
    if not options.require_scope_change:
        checks = [check for check in checks if check.name != "calibration_scope_changed"]
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
    source_role_search_report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    scope_role_search_reports: Sequence[
        HistoricalPrematchFeatureAsianHandicapRoleSearchReport
    ],
    *,
    target_segment_id: str,
    refinement_decision: HistoricalPrematchFeatureAsianHandicapSegmentRefinementDecision
    | None,
    source_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    selected_alternative: (
        HistoricalPrematchFeatureAsianHandicapCalibrationScopeAlternative | None
    ),
    alternatives: Sequence[
        HistoricalPrematchFeatureAsianHandicapCalibrationScopeAlternative
    ],
    status: HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementStatus,
    metrics: Mapping[str, object],
    options: HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_calibration_scope_refinement_decision_v3_2"
        ),
        "status": status,
        "target_segment_id": target_segment_id,
        "source_refinement_report_key": refinement_report.report_key,
        "source_role_search_report_key": source_role_search_report.report_key,
        "scope_role_search_report_keys": [
            report.report_key for report in scope_role_search_reports
        ],
        "refinement_decision": (
            refinement_decision.model_dump(mode="json")
            if refinement_decision is not None
            else None
        ),
        "source_candidate": (
            source_candidate.model_dump(mode="json")
            if source_candidate is not None
            else None
        ),
        "selected_alternative": (
            selected_alternative.model_dump(mode="json")
            if selected_alternative is not None
            else None
        ),
        "scope_alternatives": [
            alternative.model_dump(mode="json") for alternative in alternatives
        ],
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
    calibration_scope_ready: bool,
    checks: Sequence[
        HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck
    ],
) -> HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementStatus:
    hard_blockers = {
        "default_path_isolated",
        "production_recommendation_changed",
        "public_response_changed",
    }
    failed = {check.name for check in checks if check.status == "failed"}
    if failed & hard_blockers:
        return "blocked"
    if calibration_scope_ready:
        return "scope_ready"
    return "shadow_only"


def _warnings(
    *,
    status: HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementStatus,
    checks: Sequence[
        HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck
    ],
) -> list[str]:
    warnings = [
        f"asian_handicap_calibration_scope_refinement:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    warnings.append(f"asian_handicap_calibration_scope_refinement:{status}")
    return warnings


def _same_candidate_parameters(
    source_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    scope_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
) -> bool:
    if source_candidate is None or scope_candidate is None:
        return False
    return (
        source_candidate.asian_handicap_movement_weight
        == scope_candidate.asian_handicap_movement_weight
        and source_candidate.min_asian_handicap_probability_delta
        == scope_candidate.min_asian_handicap_probability_delta
        and source_candidate.asian_handicap_line_movement_weight
        == scope_candidate.asian_handicap_line_movement_weight
        and source_candidate.min_asian_handicap_line_delta
        == scope_candidate.min_asian_handicap_line_delta
        and source_candidate.asian_handicap_line_movement_scale
        == scope_candidate.asian_handicap_line_movement_scale
    )


def _calibration_scope_changed(
    source_poisson_options: Mapping[str, object],
    scope_poisson_options: Mapping[str, object],
) -> bool:
    return (
        _mapping_float(source_poisson_options, "bucket_size")
        != _mapping_float(scope_poisson_options, "bucket_size")
        or _mapping_int(source_poisson_options, "min_bucket_sample_size")
        != _mapping_int(scope_poisson_options, "min_bucket_sample_size")
    )


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
) -> HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck:
    return HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck(
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
) -> HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck:
    return HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck(
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
) -> HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck:
    return HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck(
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
) -> HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck:
    return HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck(
        name=name,
        status="passed" if _meets_max(actual, threshold) else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Compare calibration-scope replays for a line-aware Asian-handicap "
            "segment without activating it."
        )
    )
    parser.add_argument("refinement_report", type=Path)
    parser.add_argument("source_role_search_report", type=Path)
    parser.add_argument("scope_role_search_reports", nargs="+", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--experiment-id",
        default=DEFAULT_ASIAN_HANDICAP_CALIBRATION_SCOPE_REFINEMENT_ID,
    )
    parser.add_argument("--target-segment-id")
    parser.add_argument("--min-scope-report-count", type=int, default=1)
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
    parser.add_argument("--allow-non-scope-refinement-action", action="store_true")
    parser.add_argument("--allow-source-calibration-not-regressed", action="store_true")
    parser.add_argument("--allow-candidate-parameter-drift", action="store_true")
    parser.add_argument("--allow-unchanged-scope", action="store_true")
    parser.add_argument("--allow-default-path-change", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions:
    return HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementOptions(
        experiment_id=args.experiment_id,
        target_segment_id=args.target_segment_id,
        min_scope_report_count=args.min_scope_report_count,
        min_validation_count=args.min_validation_count,
        min_hit_rate_delta=args.min_hit_rate_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_expected_calibration_error_delta=(
            args.max_expected_calibration_error_delta
        ),
        require_refinement_ready=not args.allow_refinement_not_ready,
        require_refinement_action=not args.allow_non_scope_refinement_action,
        require_source_calibration_regression=(
            not args.allow_source_calibration_not_regressed
        ),
        require_same_candidate_parameters=not args.allow_candidate_parameter_drift,
        require_scope_change=not args.allow_unchanged_scope,
        require_no_default_path_change=not args.allow_default_path_change,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[
        HistoricalPrematchFeatureAsianHandicapCalibrationScopeRefinementCheck
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
        "historical_prematch_feature_asian_handicap_calibration_scope_refinement:"
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


def _none_last(value: float | None) -> float:
    return 1_000_000_000.0 if value is None else value
