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

type HistoricalPrematchFeatureAsianHandicapRoleAdmissionStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]
type HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheckStatus = Literal[
    "passed",
    "failed",
]
type HistoricalPrematchFeatureAsianHandicapRoleAdmissionFoldStatus = Literal[
    "passed",
    "failed",
]

DEFAULT_ASIAN_HANDICAP_ROLE_ADMISSION_ID = (
    "prematch-feature-asian-handicap-role-admission-v3.2"
)


class HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions(BaseModel):
    admission_id: str = DEFAULT_ASIAN_HANDICAP_ROLE_ADMISSION_ID
    min_source_report_count: int = Field(default=1, ge=1)
    min_accepted_report_count: int = Field(default=1, ge=0)
    max_failed_report_count: int = Field(default=0, ge=0)
    min_candidate_count: int = Field(default=1, ge=0)
    min_accepted_nonzero_candidate_count: int = Field(default=1, ge=0)
    min_validation_count: int = Field(default=100, ge=0)
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
    require_default_path_isolated: bool = True
    require_no_production_change: bool = True
    require_no_public_response_change: bool = True


class HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheck(BaseModel):
    name: str
    status: HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalPrematchFeatureAsianHandicapRoleAdmissionFold(BaseModel):
    fold_id: str
    source_report_key: str
    source_role_search_id: str
    status: HistoricalPrematchFeatureAsianHandicapRoleAdmissionFoldStatus
    selected_candidate_id: str | None = None
    selected_candidate_status: str | None = None
    accepted_nonzero_candidate_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    validation_count: int = Field(default=0, ge=0)
    asian_handicap_movement_weight: float | None = Field(default=None, ge=0.0)
    min_asian_handicap_probability_delta: float | None = Field(default=None, ge=0.0)
    asian_handicap_line_movement_weight: float | None = Field(default=None, ge=0.0)
    min_asian_handicap_line_delta: float | None = Field(default=None, ge=0.0)
    hit_rate_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    expected_calibration_error_delta: float | None = None
    average_actual_probability_delta: float | None = None
    failure_reasons: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchFeatureAsianHandicapRoleAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalPrematchFeatureAsianHandicapRoleAdmissionStatus
    candidate_model_allowed: bool
    shadow_allowed: bool
    default_path_isolated: bool
    production_recommendation_changed: bool = False
    public_response_changed: bool = False
    admission_id: str
    source_report_count: int = Field(ge=0)
    accepted_report_count: int = Field(ge=0)
    failed_report_count: int = Field(ge=0)
    selected_candidate_id: str | None = None
    selected_candidate_source_report_key: str | None = None
    selected_candidate_json: dict[str, object] = Field(default_factory=dict)
    checks: list[HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheck] = Field(
        default_factory=list
    )
    folds: list[HistoricalPrematchFeatureAsianHandicapRoleAdmissionFold] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    decision_payload_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


def load_historical_prematch_feature_asian_handicap_role_admission_report(
    path: Path | str,
) -> HistoricalPrematchFeatureAsianHandicapRoleAdmissionReport:
    return HistoricalPrematchFeatureAsianHandicapRoleAdmissionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_prematch_feature_asian_handicap_role_admission_report(
    source_reports: Sequence[HistoricalPrematchFeatureAsianHandicapRoleSearchReport],
    *,
    options: HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions | None = None,
) -> HistoricalPrematchFeatureAsianHandicapRoleAdmissionReport:
    resolved_options = (
        options or HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions()
    )
    folds = [
        _fold_from_report(report, index=index, options=resolved_options)
        for index, report in enumerate(source_reports, start=1)
    ]
    failed_folds = [fold for fold in folds if fold.status == "failed"]
    passed_folds = [fold for fold in folds if fold.status == "passed"]
    selected_candidate = _selected_candidate(source_reports)
    checks = _checks(
        source_reports,
        folds=folds,
        selected_candidate=selected_candidate,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    candidate_model_allowed = not failed_checks and not failed_folds
    shadow_allowed = bool(source_reports) and any(
        _source_shadow_only(report) for report in source_reports
    )
    status = _status(
        candidate_model_allowed=candidate_model_allowed,
        shadow_allowed=shadow_allowed,
        accepted_report_count=len(passed_folds),
    )
    default_path_isolated = True
    warnings = _warnings(status=status, checks=checks, failed_folds=failed_folds)
    decision_payload = _decision_payload(
        source_reports,
        folds=folds,
        selected_candidate=selected_candidate,
        status=status,
        candidate_model_allowed=candidate_model_allowed,
        shadow_allowed=shadow_allowed,
        default_path_isolated=default_path_isolated,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_role_admission_v3_2"
        ),
        "admission_id": resolved_options.admission_id,
        "status": status,
        "candidate_model_allowed": candidate_model_allowed,
        "shadow_allowed": shadow_allowed,
        "default_path_isolated": default_path_isolated,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "source_report_count": len(source_reports),
        "accepted_report_count": len(passed_folds),
        "failed_report_count": len(failed_folds),
        "selected_candidate_id": (
            selected_candidate.candidate_id if selected_candidate is not None else None
        ),
        "selected_candidate_source_report_key": _selected_candidate_report_key(
            source_reports,
            selected_candidate,
        ),
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, folds, decision_payload)
    return HistoricalPrematchFeatureAsianHandicapRoleAdmissionReport(
        report_key=report_key,
        status=status,
        candidate_model_allowed=candidate_model_allowed,
        shadow_allowed=shadow_allowed,
        default_path_isolated=default_path_isolated,
        production_recommendation_changed=False,
        public_response_changed=False,
        admission_id=resolved_options.admission_id,
        source_report_count=len(source_reports),
        accepted_report_count=len(passed_folds),
        failed_report_count=len(failed_folds),
        selected_candidate_id=(
            selected_candidate.candidate_id if selected_candidate is not None else None
        ),
        selected_candidate_source_report_key=_selected_candidate_report_key(
            source_reports,
            selected_candidate,
        ),
        selected_candidate_json=(
            selected_candidate.model_dump(mode="json")
            if selected_candidate is not None
            else {}
        ),
        checks=checks,
        folds=folds,
        warnings=warnings,
        decision_payload_json=decision_payload,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    source_reports = [
        load_historical_prematch_feature_asian_handicap_role_search_report(path)
        for path in args.source_role_search_reports
    ]
    report = build_historical_prematch_feature_asian_handicap_role_admission_report(
        source_reports,
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


def _fold_from_report(
    report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    *,
    index: int,
    options: HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions,
) -> HistoricalPrematchFeatureAsianHandicapRoleAdmissionFold:
    candidate = (
        report.best_accepted_candidate
        or report.best_effective_candidate
        or report.best_candidate
    )
    failures = _fold_failures(report, candidate=candidate, options=options)
    status: HistoricalPrematchFeatureAsianHandicapRoleAdmissionFoldStatus = (
        "failed" if failures else "passed"
    )
    metric_deltas = candidate.metric_deltas_json if candidate is not None else {}
    summary: dict[str, object] = {
        "fold_id": f"source_report:{index}:{report.role_search_id}",
        "source_report_key": report.report_key,
        "source_role_search_id": report.role_search_id,
        "status": status,
        "selected_candidate_id": candidate.candidate_id if candidate else None,
        "accepted_nonzero_candidate_count": report.accepted_nonzero_candidate_count,
        "candidate_count": report.candidate_count,
        "validation_count": candidate.candidate_validation_count if candidate else 0,
        "failure_reasons": failures,
        "warning_codes": report.warnings,
    }
    return HistoricalPrematchFeatureAsianHandicapRoleAdmissionFold(
        fold_id=f"source_report:{index}:{report.role_search_id}",
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
        hit_rate_delta=_metric_delta(metric_deltas, "hit_rate"),
        brier_score_delta=_metric_delta(metric_deltas, "brier_score"),
        log_loss_delta=_metric_delta(metric_deltas, "log_loss"),
        expected_calibration_error_delta=_metric_delta(
            metric_deltas,
            "expected_calibration_error",
        ),
        average_actual_probability_delta=_metric_delta(
            metric_deltas,
            "average_actual_probability",
        ),
        failure_reasons=failures,
        warning_codes=report.warnings,
        summary_json=summary,
    )


def _fold_failures(
    report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
    *,
    candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    options: HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions,
) -> list[str]:
    failures: list[str] = []
    if options.require_source_status_generated and _source_status(report) != "generated":
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
    if candidate.candidate_validation_count < options.min_validation_count:
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
    failures.extend(_metric_failures(candidate.metric_deltas_json, options=options))
    if (
        options.max_warning_count is not None
        and len(report.warnings) > options.max_warning_count
    ):
        failures.append("source_warning_count_above_maximum")
    return failures


def _metric_failures(
    metric_deltas_json: Mapping[str, object],
    *,
    options: HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions,
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
    if not _meets_max(
        _metric_delta(metric_deltas_json, "expected_calibration_error"),
        options.max_expected_calibration_error_delta,
    ):
        failures.append("expected_calibration_error_delta_above_maximum")
    if not _meets_min(
        _metric_delta(metric_deltas_json, "average_actual_probability"),
        options.min_average_actual_probability_delta,
    ):
        failures.append("average_actual_probability_delta_below_minimum")
    return failures


def _checks(
    source_reports: Sequence[HistoricalPrematchFeatureAsianHandicapRoleSearchReport],
    *,
    folds: Sequence[HistoricalPrematchFeatureAsianHandicapRoleAdmissionFold],
    selected_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    options: HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions,
) -> list[HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheck]:
    failed_report_count = sum(1 for fold in folds if fold.status == "failed")
    accepted_report_count = sum(1 for fold in folds if fold.status == "passed")
    default_path_isolated = True
    production_recommendation_changed = False
    public_response_changed = False
    checks = [
        _check_min(
            "source_report_count",
            len(source_reports),
            options.min_source_report_count,
            detail="admission needs enough independent or rolling source reports",
        ),
        _check_min(
            "accepted_report_count",
            accepted_report_count,
            options.min_accepted_report_count,
            detail="enough source reports must pass the same no-harm checks",
        ),
        _check_max(
            "failed_report_count",
            failed_report_count,
            options.max_failed_report_count,
            detail="failed source-report folds must stay within tolerance",
        ),
        _check_bool(
            "selected_candidate_present",
            selected_candidate is not None,
            True,
            detail="admission needs a best accepted nonzero candidate",
        ),
        _check_bool(
            "default_path_isolated",
            default_path_isolated,
            True,
            detail="admission evidence must not change the default prediction path",
        ),
        _check_bool(
            "production_recommendation_changed",
            production_recommendation_changed,
            False,
            detail="admission evidence must not alter production recommendations",
        ),
        _check_bool(
            "public_response_changed",
            public_response_changed,
            False,
            detail="admission evidence must not alter public recommendation responses",
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
    folds: Sequence[HistoricalPrematchFeatureAsianHandicapRoleAdmissionFold],
    selected_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
    status: HistoricalPrematchFeatureAsianHandicapRoleAdmissionStatus,
    candidate_model_allowed: bool,
    shadow_allowed: bool,
    default_path_isolated: bool,
    options: HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions,
) -> dict[str, object]:
    return {
        "calculation_basis": (
            "historical_prematch_feature_asian_handicap_role_admission_decision_v3_2"
        ),
        "status": status,
        "candidate_model_allowed": candidate_model_allowed,
        "shadow_allowed": shadow_allowed,
        "default_path_isolated": default_path_isolated,
        "production_recommendation_changed": False,
        "public_response_changed": False,
        "selected_candidate": (
            selected_candidate.model_dump(mode="json")
            if selected_candidate is not None
            else None
        ),
        "source_report_keys": [report.report_key for report in source_reports],
        "folds": [fold.model_dump(mode="json") for fold in folds],
        "options": options.model_dump(mode="json"),
    }


def _status(
    *,
    candidate_model_allowed: bool,
    shadow_allowed: bool,
    accepted_report_count: int,
) -> HistoricalPrematchFeatureAsianHandicapRoleAdmissionStatus:
    if candidate_model_allowed:
        return "accepted"
    if shadow_allowed and accepted_report_count > 0:
        return "shadow_only"
    return "rejected"


def _warnings(
    *,
    status: HistoricalPrematchFeatureAsianHandicapRoleAdmissionStatus,
    checks: Sequence[HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheck],
    failed_folds: Sequence[HistoricalPrematchFeatureAsianHandicapRoleAdmissionFold],
) -> list[str]:
    warnings = [
        f"asian_handicap_role_admission:failed_check:{check.name}"
        for check in checks
        if check.status == "failed"
    ]
    warnings.extend(
        f"asian_handicap_role_admission:failed_fold:{fold.fold_id}"
        for fold in failed_folds
    )
    warnings.append(f"asian_handicap_role_admission:{status}")
    return warnings


def _selected_candidate(
    source_reports: Sequence[HistoricalPrematchFeatureAsianHandicapRoleSearchReport],
) -> HistoricalPrematchFeatureAsianHandicapRoleCandidate | None:
    candidates = [
        report.best_accepted_candidate
        for report in source_reports
        if report.best_accepted_candidate is not None
    ]
    if not candidates:
        return None
    return sorted(candidates, key=_candidate_sort_key)[0]


def _candidate_sort_key(
    candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate,
) -> tuple[float, float, float, float, float]:
    return (
        _none_last(candidate.ranking_score),
        _none_last(_metric_delta(candidate.metric_deltas_json, "brier_score")),
        _none_last(_metric_delta(candidate.metric_deltas_json, "log_loss")),
        _none_last(
            _metric_delta(candidate.metric_deltas_json, "expected_calibration_error")
        ),
        -_none_first(_metric_delta(candidate.metric_deltas_json, "hit_rate")),
    )


def _selected_candidate_report_key(
    source_reports: Sequence[HistoricalPrematchFeatureAsianHandicapRoleSearchReport],
    selected_candidate: HistoricalPrematchFeatureAsianHandicapRoleCandidate | None,
) -> str | None:
    if selected_candidate is None:
        return None
    for report in source_reports:
        if (
            report.best_accepted_candidate is not None
            and report.best_accepted_candidate.candidate_id
            == selected_candidate.candidate_id
        ):
            return report.report_key
    return None


def _source_shadow_only(
    report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
) -> bool:
    value = report.summary_json.get("shadow_only")
    return value is True


def _source_status(
    report: HistoricalPrematchFeatureAsianHandicapRoleSearchReport,
) -> str:
    return str(report.status)


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
) -> HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheck:
    return HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _check_max(
    name: str,
    actual: int | float,
    threshold: int | float,
    *,
    detail: str,
) -> HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheck:
    return HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
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
) -> HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheck:
    return HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheck(
        name=name,
        status="passed" if actual is threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Admit or hold back a line-aware Asian-handicap pre-match role "
            "search candidate without changing the default recommendation path."
        )
    )
    parser.add_argument(
        "--source-role-search-report",
        dest="source_role_search_reports",
        action="append",
        type=Path,
        default=[],
        required=True,
    )
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--admission-id", default=DEFAULT_ASIAN_HANDICAP_ROLE_ADMISSION_ID)
    parser.add_argument("--min-source-report-count", type=int, default=1)
    parser.add_argument("--min-accepted-report-count", type=int, default=1)
    parser.add_argument("--max-failed-report-count", type=int, default=0)
    parser.add_argument("--min-candidate-count", type=int, default=1)
    parser.add_argument("--min-accepted-nonzero-candidate-count", type=int, default=1)
    parser.add_argument("--min-validation-count", type=int, default=100)
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
    parser.add_argument("--allow-default-path-not-isolated", action="store_true")
    parser.add_argument("--allow-production-change", action="store_true")
    parser.add_argument("--allow-public-response-change", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions:
    return HistoricalPrematchFeatureAsianHandicapRoleAdmissionOptions(
        admission_id=args.admission_id,
        min_source_report_count=args.min_source_report_count,
        min_accepted_report_count=args.min_accepted_report_count,
        max_failed_report_count=args.max_failed_report_count,
        min_candidate_count=args.min_candidate_count,
        min_accepted_nonzero_candidate_count=args.min_accepted_nonzero_candidate_count,
        min_validation_count=args.min_validation_count,
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
        require_default_path_isolated=not args.allow_default_path_not_isolated,
        require_no_production_change=not args.allow_production_change,
        require_no_public_response_change=not args.allow_public_response_change,
    )


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalPrematchFeatureAsianHandicapRoleAdmissionCheck],
    folds: Sequence[HistoricalPrematchFeatureAsianHandicapRoleAdmissionFold],
    decision_payload: Mapping[str, object],
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "folds": [fold.model_dump(mode="json") for fold in folds],
        "decision_payload": decision_payload,
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_prematch_feature_asian_handicap_role_admission:{digest}"


def _none_last(value: float | None) -> float:
    return 1_000_000_000.0 if value is None else value


def _none_first(value: float | None) -> float:
    return -1_000_000_000.0 if value is None else value
