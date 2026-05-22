from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from re import search
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_market_movement_signal_diagnostics import (
    HistoricalMarketMovementSignalDiagnosticOptions,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_market_movement_segment_gate import (
    DEFAULT_MARKET_MOVEMENT_SEGMENT_GATE_ID,
    HistoricalMarketMovementSegmentCandidate,
    HistoricalMarketMovementSegmentGateOptions,
    HistoricalMarketMovementSegmentGateReport,
    build_historical_market_movement_segment_gate_report,
)
from nutmeg.recommendations.historical_prematch_feature_sample_readiness import (
    HistoricalPrematchFeatureSampleReadinessReport,
    load_historical_prematch_feature_sample_readiness_report,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalMarketMovementRiskFilterRollingAdmissionStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]
type HistoricalMarketMovementRiskFilterAdmissionCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]
type HistoricalMarketMovementRiskFilterFoldStatus = Literal[
    "passed",
    "failed",
    "skipped",
]
type HistoricalMarketMovementRiskFilterFoldType = Literal[
    "overall",
    "competition",
    "season_cutoff",
    "rolling_window",
]

DEFAULT_MARKET_MOVEMENT_RISK_FILTER_ROLLING_ADMISSION_ID = (
    "market-movement-risk-filter-rolling-admission-shadow-v3.2"
)


class HistoricalMarketMovementRiskFilterRollingAdmissionOptions(BaseModel):
    admission_id: str = DEFAULT_MARKET_MOVEMENT_RISK_FILTER_ROLLING_ADMISSION_ID
    sample_readiness_report_path: Path | None = None
    require_sample_readiness: bool = False
    require_sample_ready_allowed: bool = True
    segment_gate_options: HistoricalMarketMovementSegmentGateOptions = Field(
        default_factory=HistoricalMarketMovementSegmentGateOptions
    )
    min_overall_candidate_count: int = Field(default=1, ge=0)
    min_overall_accepted_count: int = Field(default=1, ge=0)
    min_overall_adjusted_fixture_count: int = Field(default=1, ge=0)
    require_overall_best_candidate_accepted: bool = True
    min_fold_slice_count: int = Field(default=1, ge=0)
    min_fold_fixture_count: int = Field(default=1, ge=0)
    min_fold_candidate_count: int = Field(default=1, ge=0)
    min_fold_accepted_count: int = Field(default=1, ge=0)
    min_fold_adjusted_fixture_count: int = Field(default=1, ge=0)
    require_fold_best_candidate_accepted: bool = True
    max_failed_fold_count: int = Field(default=0, ge=0)
    min_active_competition_fold_count: int = Field(default=1, ge=0)
    min_active_season_cutoff_fold_count: int = Field(default=1, ge=0)
    min_active_rolling_fold_count: int = Field(default=1, ge=0)
    rolling_window_season_count: int = Field(default=3, ge=1)
    rolling_window_step: int = Field(default=1, ge=1)
    max_report_folds: int = Field(default=120, ge=1, le=500)


class HistoricalMarketMovementRiskFilterAdmissionCheck(BaseModel):
    name: str
    status: HistoricalMarketMovementRiskFilterAdmissionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalMarketMovementRiskFilterFold(BaseModel):
    fold_id: str
    fold_type: HistoricalMarketMovementRiskFilterFoldType
    status: HistoricalMarketMovementRiskFilterFoldStatus
    source_slice_ids: list[str] = Field(default_factory=list)
    source_competition_ids: list[str] = Field(default_factory=list)
    source_season_ids: list[str] = Field(default_factory=list)
    segment_gate_report_key: str | None = None
    passed_segment_gate: bool = False
    candidate_count: int = Field(default=0, ge=0)
    accepted_count: int = Field(default=0, ge=0)
    adjusted_fixture_count: int = Field(default=0, ge=0)
    adjusted_prediction_count: int = Field(default=0, ge=0)
    best_candidate_id: str | None = None
    best_segment_group_key: str | None = None
    best_segment_group_type: str | None = None
    best_segment_label: str | None = None
    best_decision: str | None = None
    best_passed_single_match_gate: bool | None = None
    best_passed_final_answer_gate: bool | None = None
    best_quality_gate_passed: bool | None = None
    best_suite_status: str | None = None
    single_match_hit_rate_delta: float | None = None
    single_match_brier_score_delta: float | None = None
    single_match_log_loss_delta: float | None = None
    final_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    failure_reasons: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketMovementRiskFilterRollingAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalMarketMovementRiskFilterRollingAdmissionStatus
    risk_filter_allowed: bool
    shadow_allowed: bool
    sample_readiness_report_path: Path | None = None
    sample_readiness_key: str | None = None
    sample_readiness_status: str | None = None
    sample_ready_allowed: bool | None = None
    sample_readiness_shadow_allowed: bool | None = None
    source_segment_gate_report_key: str
    overall_fold: HistoricalMarketMovementRiskFilterFold
    fold_count: int = Field(ge=0)
    active_fold_count: int = Field(ge=0)
    failed_fold_count: int = Field(ge=0)
    active_competition_fold_count: int = Field(ge=0)
    active_season_cutoff_fold_count: int = Field(ge=0)
    active_rolling_fold_count: int = Field(ge=0)
    checks: list[HistoricalMarketMovementRiskFilterAdmissionCheck] = Field(
        default_factory=list
    )
    folds: list[HistoricalMarketMovementRiskFilterFold] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_market_movement_risk_filter_rolling_admission_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions | None = None,
    segment_gate_report: HistoricalMarketMovementSegmentGateReport | None = None,
    sample_readiness_report: HistoricalPrematchFeatureSampleReadinessReport
    | None = None,
) -> HistoricalMarketMovementRiskFilterRollingAdmissionReport:
    resolved_options = (
        options or HistoricalMarketMovementRiskFilterRollingAdmissionOptions()
    )
    resolved_segment_gate_report = (
        segment_gate_report
        or build_historical_market_movement_segment_gate_report(
            historical_slices,
            options=resolved_options.segment_gate_options,
        )
    )
    overall_fold = _gate_fold(
        "overall:all",
        "overall",
        historical_slices,
        options=resolved_options,
        is_overall=True,
        segment_gate_report=resolved_segment_gate_report,
    )
    folds = _fold_reports(historical_slices, options=resolved_options)
    checks = _checks(
        overall_fold,
        folds=folds,
        sample_readiness_report=sample_readiness_report,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    failed_folds = [fold for fold in folds if fold.status == "failed"]
    active_folds = [fold for fold in folds if fold.status != "skipped"]
    if (
        _check_failed(checks, "market_movement_sample_readiness_present")
        or (
            sample_readiness_report is not None
            and sample_readiness_report.status == "rejected"
        )
        or _check_failed(checks, "overall_segment_gate_passed")
        or _check_failed(checks, "overall_accepted_count")
        or _check_failed(checks, "overall_adjusted_fixture_count")
    ):
        status: HistoricalMarketMovementRiskFilterRollingAdmissionStatus = "rejected"
    elif failed_checks:
        status = "shadow_only"
    else:
        status = "accepted"
    risk_filter_allowed = status == "accepted"
    shadow_allowed = status in {"accepted", "shadow_only"}
    warnings = [
        *overall_fold.warning_codes,
        *[
            f"market_movement_risk_filter_rolling_admission:failed_check:{check.name}"
            for check in failed_checks
        ],
        *[
            f"market_movement_risk_filter_rolling_admission:failed_fold:{fold.fold_id}"
            for fold in failed_folds
        ],
    ]
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_risk_filter_rolling_admission_v3_2"
        ),
        "admission_id": resolved_options.admission_id,
        "status": status,
        "risk_filter_allowed": risk_filter_allowed,
        "shadow_allowed": shadow_allowed,
        "sample_readiness_report_path": (
            str(resolved_options.sample_readiness_report_path)
            if resolved_options.sample_readiness_report_path is not None
            else None
        ),
        "sample_readiness_key": (
            sample_readiness_report.readiness_key
            if sample_readiness_report is not None
            else None
        ),
        "sample_readiness_status": (
            sample_readiness_report.status
            if sample_readiness_report is not None
            else None
        ),
        "sample_ready_allowed": (
            sample_readiness_report.sample_ready_allowed
            if sample_readiness_report is not None
            else None
        ),
        "sample_readiness_shadow_allowed": (
            sample_readiness_report.shadow_allowed
            if sample_readiness_report is not None
            else None
        ),
        "source_segment_gate_report_key": resolved_segment_gate_report.report_key,
        "overall": overall_fold.model_dump(mode="json"),
        "fold_count": len(folds),
        "active_fold_count": len(active_folds),
        "failed_fold_count": len(failed_folds),
        "active_competition_fold_count": _active_fold_count(folds, "competition"),
        "active_season_cutoff_fold_count": _active_fold_count(
            folds,
            "season_cutoff",
        ),
        "active_rolling_fold_count": _active_fold_count(folds, "rolling_window"),
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, folds)
    return HistoricalMarketMovementRiskFilterRollingAdmissionReport(
        report_key=report_key,
        status=status,
        risk_filter_allowed=risk_filter_allowed,
        shadow_allowed=shadow_allowed,
        sample_readiness_report_path=resolved_options.sample_readiness_report_path,
        sample_readiness_key=(
            sample_readiness_report.readiness_key
            if sample_readiness_report is not None
            else None
        ),
        sample_readiness_status=(
            sample_readiness_report.status
            if sample_readiness_report is not None
            else None
        ),
        sample_ready_allowed=(
            sample_readiness_report.sample_ready_allowed
            if sample_readiness_report is not None
            else None
        ),
        sample_readiness_shadow_allowed=(
            sample_readiness_report.shadow_allowed
            if sample_readiness_report is not None
            else None
        ),
        source_segment_gate_report_key=resolved_segment_gate_report.report_key,
        overall_fold=overall_fold,
        fold_count=len(folds),
        active_fold_count=len(active_folds),
        failed_fold_count=len(failed_folds),
        active_competition_fold_count=_active_fold_count(folds, "competition"),
        active_season_cutoff_fold_count=_active_fold_count(folds, "season_cutoff"),
        active_rolling_fold_count=_active_fold_count(folds, "rolling_window"),
        checks=checks,
        folds=folds[: resolved_options.max_report_folds],
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_market_movement_risk_filter_rolling_admission_report(
    path: Path | str,
) -> HistoricalMarketMovementRiskFilterRollingAdmissionReport:
    return HistoricalMarketMovementRiskFilterRollingAdmissionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    segment_gate_report = _load_segment_gate_report(args.segment_gate_report_path)
    sample_readiness_report = _load_sample_readiness_report(
        args.sample_readiness_report_path
    )
    report = build_historical_market_movement_risk_filter_rolling_admission_report(
        loaded_slices.slices,
        options=_options_from_args(args),
        segment_gate_report=segment_gate_report,
        sample_readiness_report=sample_readiness_report,
    )
    if loaded_slices.manifest_result is not None:
        report.summary_json["suite_manifest"] = _manifest_summary(
            loaded_slices.manifest_result
        )
    if loaded_slices.warnings:
        report.warnings.extend(loaded_slices.warnings)
        report.summary_json["manifest_warnings"] = loaded_slices.warnings
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
    if not report.risk_filter_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _fold_reports(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
) -> list[HistoricalMarketMovementRiskFilterFold]:
    folds: list[HistoricalMarketMovementRiskFilterFold] = []
    for competition_id, slices in _groups_by_competition(historical_slices).items():
        folds.append(
            _gate_fold(
                f"competition:{competition_id}",
                "competition",
                slices,
                options=options,
            )
        )
    for season_id, slices in _season_cutoff_groups(historical_slices, options).items():
        folds.append(
            _gate_fold(
                f"season_cutoff:{season_id}",
                "season_cutoff",
                slices,
                options=options,
            )
        )
    for index, slices in enumerate(_rolling_window_groups(historical_slices, options)):
        season_ids = sorted(
            {_slice_season_id(historical_slice) for historical_slice in slices},
            key=_season_sort_key,
        )
        folds.append(
            _gate_fold(
                f"rolling_window:{index + 1}:{season_ids[0]}..{season_ids[-1]}",
                "rolling_window",
                slices,
                options=options,
            )
        )
    return folds


def _gate_fold(
    fold_id: str,
    fold_type: HistoricalMarketMovementRiskFilterFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
    is_overall: bool = False,
    segment_gate_report: HistoricalMarketMovementSegmentGateReport | None = None,
) -> HistoricalMarketMovementRiskFilterFold:
    if not is_overall and not _has_required_fold_sample(historical_slices, options):
        return _skipped_fold(
            fold_id,
            fold_type,
            historical_slices,
            reason="insufficient_fold_sample",
        )
    try:
        gate_report = segment_gate_report or (
            build_historical_market_movement_segment_gate_report(
                historical_slices,
                options=options.segment_gate_options,
            )
        )
    except ValueError as exc:
        return _failed_fold(fold_id, fold_type, historical_slices, reason=str(exc))
    return _fold_report(
        fold_id,
        fold_type,
        historical_slices,
        gate_report=gate_report,
        options=options,
        is_overall=is_overall,
    )


def _fold_report(
    fold_id: str,
    fold_type: HistoricalMarketMovementRiskFilterFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    gate_report: HistoricalMarketMovementSegmentGateReport,
    options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
    is_overall: bool,
) -> HistoricalMarketMovementRiskFilterFold:
    best = gate_report.best_candidate
    failure_reasons = _fold_failure_reasons(
        gate_report,
        options=options,
        is_overall=is_overall,
    )
    status: HistoricalMarketMovementRiskFilterFoldStatus = (
        "failed" if failure_reasons else "passed"
    )
    return HistoricalMarketMovementRiskFilterFold(
        fold_id=fold_id,
        fold_type=fold_type,
        status=status,
        source_slice_ids=[
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        source_competition_ids=sorted(
            {
                historical_slice.metadata.competition_id
                for historical_slice in historical_slices
            }
        ),
        source_season_ids=sorted(
            {_slice_season_id(historical_slice) for historical_slice in historical_slices},
            key=_season_sort_key,
        ),
        segment_gate_report_key=gate_report.report_key,
        passed_segment_gate=gate_report.accepted_count > 0,
        candidate_count=gate_report.candidate_count,
        accepted_count=gate_report.accepted_count,
        adjusted_fixture_count=best.adjusted_fixture_count if best is not None else 0,
        adjusted_prediction_count=(
            best.adjusted_prediction_count if best is not None else 0
        ),
        best_candidate_id=best.candidate_id if best is not None else None,
        best_segment_group_key=best.segment_group_key if best is not None else None,
        best_segment_group_type=best.segment_group_type if best is not None else None,
        best_segment_label=best.segment_label if best is not None else None,
        best_decision=best.decision if best is not None else None,
        best_passed_single_match_gate=(
            best.passed_single_match_gate if best is not None else None
        ),
        best_passed_final_answer_gate=(
            best.passed_final_answer_gate if best is not None else None
        ),
        best_quality_gate_passed=(
            best.quality_gate.passed if best is not None else None
        ),
        best_suite_status=best.suite.status if best is not None else None,
        single_match_hit_rate_delta=_candidate_single_delta(best, "hit_rate_delta"),
        single_match_brier_score_delta=_candidate_single_delta(
            best,
            "brier_score_delta",
        ),
        single_match_log_loss_delta=_candidate_single_delta(best, "log_loss_delta"),
        final_hit_rate_delta=_candidate_final_delta(best, "final_hit_rate_delta"),
        roi_delta=_candidate_final_delta(best, "roi_delta"),
        profit_loss_delta=_candidate_final_delta(best, "profit_loss_delta"),
        brier_score_delta=_candidate_final_delta(best, "brier_score_delta"),
        log_loss_delta=_candidate_final_delta(best, "log_loss_delta"),
        mean_calibration_error_delta=_candidate_final_delta(
            best,
            "mean_calibration_error_delta",
        ),
        failure_reasons=failure_reasons,
        warning_codes=list(gate_report.warnings),
        summary_json={
            "segment_gate_report_key": gate_report.report_key,
            "segment_gate_summary": gate_report.summary_json,
        },
    )


def _skipped_fold(
    fold_id: str,
    fold_type: HistoricalMarketMovementRiskFilterFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    reason: str,
) -> HistoricalMarketMovementRiskFilterFold:
    return HistoricalMarketMovementRiskFilterFold(
        fold_id=fold_id,
        fold_type=fold_type,
        status="skipped",
        source_slice_ids=[
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        source_competition_ids=sorted(
            {
                historical_slice.metadata.competition_id
                for historical_slice in historical_slices
            }
        ),
        source_season_ids=sorted(
            {_slice_season_id(historical_slice) for historical_slice in historical_slices},
            key=_season_sort_key,
        ),
        failure_reasons=[reason],
        warning_codes=[
            f"market_movement_risk_filter_rolling_admission:skipped:{reason}"
        ],
        summary_json={"skip_reason": reason},
    )


def _failed_fold(
    fold_id: str,
    fold_type: HistoricalMarketMovementRiskFilterFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    reason: str,
) -> HistoricalMarketMovementRiskFilterFold:
    return HistoricalMarketMovementRiskFilterFold(
        fold_id=fold_id,
        fold_type=fold_type,
        status="failed",
        source_slice_ids=[
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        source_competition_ids=sorted(
            {
                historical_slice.metadata.competition_id
                for historical_slice in historical_slices
            }
        ),
        source_season_ids=sorted(
            {_slice_season_id(historical_slice) for historical_slice in historical_slices},
            key=_season_sort_key,
        ),
        failure_reasons=[reason],
        warning_codes=[
            f"market_movement_risk_filter_rolling_admission:failed:{reason}"
        ],
        summary_json={"failure_reason": reason},
    )


def _fold_failure_reasons(
    gate_report: HistoricalMarketMovementSegmentGateReport,
    *,
    options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
    is_overall: bool,
) -> list[str]:
    min_candidate_count = (
        options.min_overall_candidate_count
        if is_overall
        else options.min_fold_candidate_count
    )
    min_accepted_count = (
        options.min_overall_accepted_count
        if is_overall
        else options.min_fold_accepted_count
    )
    min_adjusted_fixture_count = (
        options.min_overall_adjusted_fixture_count
        if is_overall
        else options.min_fold_adjusted_fixture_count
    )
    require_best_accepted = (
        options.require_overall_best_candidate_accepted
        if is_overall
        else options.require_fold_best_candidate_accepted
    )
    best = gate_report.best_candidate
    failures: list[str] = []
    if gate_report.candidate_count < min_candidate_count:
        failures.append("candidate_count_below_threshold")
    if gate_report.accepted_count < min_accepted_count:
        failures.append("accepted_count_below_threshold")
    if best is None:
        failures.append("no_best_candidate")
        return failures
    if best.adjusted_fixture_count < min_adjusted_fixture_count:
        failures.append("adjusted_fixture_count_below_threshold")
    if require_best_accepted and best.decision != "accepted":
        failures.append("best_candidate_not_accepted")
    if not best.passed_single_match_gate:
        failures.append("best_single_match_gate_not_passed")
    if not best.passed_final_answer_gate:
        failures.append("best_final_answer_gate_not_passed")
    if not best.quality_gate.passed:
        failures.append("best_quality_gate_not_passed")
    return failures


def _checks(
    overall_fold: HistoricalMarketMovementRiskFilterFold,
    *,
    folds: Sequence[HistoricalMarketMovementRiskFilterFold],
    sample_readiness_report: HistoricalPrematchFeatureSampleReadinessReport | None,
    options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
) -> list[HistoricalMarketMovementRiskFilterAdmissionCheck]:
    failed_fold_count = sum(1 for fold in folds if fold.status == "failed")
    checks = _sample_readiness_checks(sample_readiness_report, options=options)
    checks.extend(
        [
            _boolean_check(
                name="overall_segment_gate_passed",
                actual=overall_fold.passed_segment_gate,
                expected=True,
                detail="overall market-movement segment gate should pass",
            ),
            _minimum_check(
                name="overall_candidate_count",
                actual=overall_fold.candidate_count,
                threshold=options.min_overall_candidate_count,
                detail="overall admission should evaluate enough segment candidates",
            ),
            _minimum_check(
                name="overall_accepted_count",
                actual=overall_fold.accepted_count,
                threshold=options.min_overall_accepted_count,
                detail="overall admission should keep accepted segment candidates",
            ),
            _minimum_check(
                name="overall_adjusted_fixture_count",
                actual=overall_fold.adjusted_fixture_count,
                threshold=options.min_overall_adjusted_fixture_count,
                detail="overall accepted candidate should touch enough fixtures",
            ),
            _maximum_check(
                name="failed_fold_count",
                actual=failed_fold_count,
                threshold=options.max_failed_fold_count,
                detail="rolling admission should not have failing active folds",
            ),
            _minimum_check(
                name="active_competition_fold_count",
                actual=_active_fold_count(folds, "competition"),
                threshold=options.min_active_competition_fold_count,
                detail="admission should validate enough competition folds",
            ),
            _minimum_check(
                name="active_season_cutoff_fold_count",
                actual=_active_fold_count(folds, "season_cutoff"),
                threshold=options.min_active_season_cutoff_fold_count,
                detail="admission should validate enough cumulative season cutoffs",
            ),
            _minimum_check(
                name="active_rolling_fold_count",
                actual=_active_fold_count(folds, "rolling_window"),
                threshold=options.min_active_rolling_fold_count,
                detail="admission should validate enough rolling season windows",
            ),
        ]
    )
    return checks


def _sample_readiness_checks(
    sample_readiness_report: HistoricalPrematchFeatureSampleReadinessReport | None,
    *,
    options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
) -> list[HistoricalMarketMovementRiskFilterAdmissionCheck]:
    checks = [_sample_readiness_present_check(sample_readiness_report, options=options)]
    if sample_readiness_report is None:
        return checks
    required = (
        options.require_sample_readiness
        or sample_readiness_report.status != "accepted"
    )
    checks.extend(
        [
            _required_bool_check(
                name="market_movement_sample_readiness_accepted",
                actual=sample_readiness_report.status == "accepted",
                required=required,
                detail="market-movement sample readiness should be accepted",
            ),
            _required_bool_check(
                name="market_movement_sample_ready_allowed",
                actual=sample_readiness_report.sample_ready_allowed,
                required=required and options.require_sample_ready_allowed,
                detail="market-movement sample readiness should allow learning",
            ),
            _required_bool_check(
                name="market_movement_sample_readiness_shadow_allowed",
                actual=sample_readiness_report.shadow_allowed,
                required=required,
                detail="market-movement sample readiness should remain shadow-allowed",
            ),
        ]
    )
    return checks


def _sample_readiness_present_check(
    sample_readiness_report: HistoricalPrematchFeatureSampleReadinessReport | None,
    *,
    options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
) -> HistoricalMarketMovementRiskFilterAdmissionCheck:
    if not options.require_sample_readiness:
        return _skipped_check(
            name="market_movement_sample_readiness_present",
            actual=sample_readiness_report is not None,
            detail="market-movement sample-readiness evidence is optional",
        )
    return HistoricalMarketMovementRiskFilterAdmissionCheck(
        name="market_movement_sample_readiness_present",
        status="passed" if sample_readiness_report is not None else "failed",
        actual=sample_readiness_report is not None,
        threshold=True,
        detail=(
            "market-movement sample-readiness evidence must be attached before "
            "risk-filter rolling admission can pass"
        ),
    )


def _groups_by_competition(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> dict[str, list[HistoricalRecommendationSlice]]:
    grouped: dict[str, list[HistoricalRecommendationSlice]] = {}
    for historical_slice in historical_slices:
        grouped.setdefault(historical_slice.metadata.competition_id, []).append(
            historical_slice
        )
    return {
        competition_id: sorted(slices, key=_slice_sort_key)
        for competition_id, slices in sorted(grouped.items())
    }


def _season_cutoff_groups(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
) -> dict[str, list[HistoricalRecommendationSlice]]:
    ordered_seasons = _ordered_season_ids(historical_slices)
    groups: dict[str, list[HistoricalRecommendationSlice]] = {}
    for index, season_id in enumerate(ordered_seasons):
        included_seasons = set(ordered_seasons[: index + 1])
        slices = [
            historical_slice
            for historical_slice in historical_slices
            if _slice_season_id(historical_slice) in included_seasons
        ]
        if _has_required_fold_sample(slices, options):
            groups[season_id] = sorted(slices, key=_slice_sort_key)
    return groups


def _rolling_window_groups(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
) -> list[list[HistoricalRecommendationSlice]]:
    ordered_seasons = _ordered_season_ids(historical_slices)
    windows: list[list[HistoricalRecommendationSlice]] = []
    for start in range(0, len(ordered_seasons), options.rolling_window_step):
        season_window = ordered_seasons[
            start : start + options.rolling_window_season_count
        ]
        if len(season_window) < options.rolling_window_season_count:
            break
        selected_seasons = set(season_window)
        slices = [
            historical_slice
            for historical_slice in historical_slices
            if _slice_season_id(historical_slice) in selected_seasons
        ]
        if _has_required_fold_sample(slices, options):
            windows.append(sorted(slices, key=_slice_sort_key))
    return windows


def _has_required_fold_sample(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
) -> bool:
    if len(historical_slices) < options.min_fold_slice_count:
        return False
    return _fixture_count(historical_slices) >= options.min_fold_fixture_count


def _fixture_count(historical_slices: Sequence[HistoricalRecommendationSlice]) -> int:
    return sum(len(historical_slice.fixtures) for historical_slice in historical_slices)


def _ordered_season_ids(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> list[str]:
    return sorted(
        {_slice_season_id(historical_slice) for historical_slice in historical_slices},
        key=_season_sort_key,
    )


def _slice_sort_key(historical_slice: HistoricalRecommendationSlice) -> tuple[int, str, str]:
    season_id = _slice_season_id(historical_slice)
    return (
        _season_sort_key(season_id)[0],
        historical_slice.metadata.competition_id,
        historical_slice.metadata.slice_id,
    )


def _slice_season_id(historical_slice: HistoricalRecommendationSlice) -> str:
    if historical_slice.metadata.season:
        return historical_slice.metadata.season
    match = search(r"_(\d{4}(?:_\d{4})?)_", historical_slice.metadata.slice_id)
    return match.group(1) if match else "unknown"


def _season_sort_key(season_id: str) -> tuple[int, str]:
    match = search(r"\d{4}", season_id)
    return (int(match.group(0)) if match else 0, season_id)


def _active_fold_count(
    folds: Sequence[HistoricalMarketMovementRiskFilterFold],
    fold_type: HistoricalMarketMovementRiskFilterFoldType,
) -> int:
    return sum(
        1 for fold in folds if fold.fold_type == fold_type and fold.status != "skipped"
    )


def _check_failed(
    checks: Sequence[HistoricalMarketMovementRiskFilterAdmissionCheck],
    name: str,
) -> bool:
    return any(check.name == name and check.status == "failed" for check in checks)


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
) -> HistoricalMarketMovementRiskFilterAdmissionCheck:
    return HistoricalMarketMovementRiskFilterAdmissionCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: int | float | None,
    threshold: int | float,
    detail: str,
) -> HistoricalMarketMovementRiskFilterAdmissionCheck:
    if actual is None:
        return HistoricalMarketMovementRiskFilterAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalMarketMovementRiskFilterAdmissionCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    *,
    name: str,
    actual: int | float | None,
    threshold: int | float,
    detail: str,
) -> HistoricalMarketMovementRiskFilterAdmissionCheck:
    if actual is None:
        return HistoricalMarketMovementRiskFilterAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalMarketMovementRiskFilterAdmissionCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _required_bool_check(
    *,
    name: str,
    actual: bool,
    required: bool,
    detail: str,
) -> HistoricalMarketMovementRiskFilterAdmissionCheck:
    if not required:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalMarketMovementRiskFilterAdmissionCheck(
        name=name,
        status="passed" if actual else "failed",
        actual=actual,
        threshold=True,
        detail=detail,
    )


def _skipped_check(
    *,
    name: str,
    actual: float | int | str | bool | None,
    detail: str,
) -> HistoricalMarketMovementRiskFilterAdmissionCheck:
    return HistoricalMarketMovementRiskFilterAdmissionCheck(
        name=name,
        status="skipped",
        actual=actual,
        threshold=None,
        detail=detail,
    )


def _candidate_single_delta(
    candidate: HistoricalMarketMovementSegmentCandidate | None,
    key: str,
) -> float | None:
    if candidate is None:
        return None
    return _delta_number(candidate.single_match_deltas_json, key)


def _candidate_final_delta(
    candidate: HistoricalMarketMovementSegmentCandidate | None,
    key: str,
) -> float | None:
    if candidate is None:
        return None
    return _delta_number(candidate.final_answer_deltas_json, key)


def _delta_number(values: dict[str, object], key: str) -> float | None:
    value = values.get(key)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _report_key(
    summary: dict[str, object],
    checks: Sequence[HistoricalMarketMovementRiskFilterAdmissionCheck],
    folds: Sequence[HistoricalMarketMovementRiskFilterFold],
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "folds": [fold.model_dump(mode="json") for fold in folds],
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_market_movement_risk_filter_rolling_admission:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run rolling admission for shadow market-movement risk-filter segments."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--segment-gate-report-path", type=Path)
    parser.add_argument("--sample-readiness-report-path", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--admission-id",
        "--rolling-admission-id",
        dest="admission_id",
        default=DEFAULT_MARKET_MOVEMENT_RISK_FILTER_ROLLING_ADMISSION_ID,
    )
    parser.add_argument("--gate-id", default=DEFAULT_MARKET_MOVEMENT_SEGMENT_GATE_ID)
    parser.add_argument("--segment-group-keys", default="")
    parser.add_argument("--top-positive-segment-limit", type=int, default=5)
    parser.add_argument("--min-segment-sample-size", type=int, default=20)
    parser.add_argument("--max-segment-brier-delta", type=float, default=0.0)
    parser.add_argument("--max-segment-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-segment-calibration-error-delta", type=float)
    parser.add_argument("--min-segment-closing-improved-rate", type=float)
    parser.add_argument("--movement-weight", type=float, default=0.50)
    parser.add_argument("--max-probability-shift", type=float, default=0.08)
    parser.add_argument("--min-single-match-sample-size", type=int, default=1)
    parser.add_argument("--min-single-match-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-single-match-brier-delta", type=float, default=0.0)
    parser.add_argument("--max-single-match-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--min-abs-probability-delta", type=float, default=0.0)
    parser.add_argument("--movement-direction-epsilon", type=float, default=0.001)
    parser.add_argument(
        "--delta-bands",
        default="0.00:0.01,0.01:0.03,0.03:0.06,0.06:",
    )
    parser.add_argument(
        "--opening-probability-bands",
        default="0.00:0.25,0.25:0.45,0.45:0.65,0.65:1.00",
    )
    parser.add_argument("--min-diagnostics-group-sample-size", type=int, default=1)
    parser.add_argument(
        "--include-competition-groups",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--observation-sample-limit", type=int, default=20)
    parser.add_argument("--pass-types", default="1x1,2x1,3x1,4x1")
    parser.add_argument("--modes", default="single,multiple")
    parser.add_argument(
        "--strategy",
        choices=["accuracy_first", "value_first", "upset_protection", "budget_constrained"],
        default="accuracy_first",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument(
        "--optimizer-profile",
        choices=["heuristic", "solver"],
        default="solver",
    )
    parser.add_argument("--min-slice-count", type=int, default=1)
    parser.add_argument("--min-comparison-count", type=int, default=1)
    parser.add_argument("--min-final-hit-sample-size", type=int, default=1)
    parser.add_argument("--min-candidate-final-hit-rate", type=float)
    parser.add_argument("--min-candidate-roi", type=float)
    parser.add_argument("--fail-on-suite-statuses", default="regressed,mixed")
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float)
    parser.add_argument("--min-profit-loss-delta", type=float)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--min-final-answer-changed-count", type=int, default=0)
    parser.add_argument("--max-warning-count", type=int)
    parser.add_argument("--min-overall-candidate-count", type=int, default=1)
    parser.add_argument("--min-overall-accepted-count", type=int, default=1)
    parser.add_argument("--min-overall-adjusted-fixture-count", type=int, default=1)
    parser.add_argument(
        "--require-overall-best-candidate-accepted",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--min-fold-slice-count", type=int, default=1)
    parser.add_argument("--min-fold-fixture-count", type=int, default=1)
    parser.add_argument("--min-fold-candidate-count", type=int, default=1)
    parser.add_argument("--min-fold-accepted-count", type=int, default=1)
    parser.add_argument("--min-fold-adjusted-fixture-count", type=int, default=1)
    parser.add_argument(
        "--require-fold-best-candidate-accepted",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--min-active-competition-fold-count", type=int, default=1)
    parser.add_argument("--min-active-season-cutoff-fold-count", type=int, default=1)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=1)
    parser.add_argument("--rolling-window-season-count", type=int, default=3)
    parser.add_argument("--rolling-window-step", type=int, default=1)
    parser.add_argument("--max-report-folds", type=int, default=120)
    parser.add_argument("--require-sample-readiness", action="store_true")
    parser.add_argument("--allow-sample-readiness-shadow-only", action="store_true")
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalMarketMovementRiskFilterRollingAdmissionOptions:
    segment_gate_options = HistoricalMarketMovementSegmentGateOptions(
        gate_id=args.gate_id,
        segment_group_keys=tuple(_csv(args.segment_group_keys)),
        top_positive_segment_limit=args.top_positive_segment_limit,
        min_segment_sample_size=args.min_segment_sample_size,
        max_segment_brier_delta=args.max_segment_brier_delta,
        max_segment_log_loss_delta=args.max_segment_log_loss_delta,
        max_segment_calibration_error_delta=args.max_segment_calibration_error_delta,
        min_segment_closing_improved_rate=args.min_segment_closing_improved_rate,
        movement_weight=args.movement_weight,
        max_probability_shift=args.max_probability_shift,
        min_single_match_sample_size=args.min_single_match_sample_size,
        min_single_match_hit_rate_delta=args.min_single_match_hit_rate_delta,
        max_single_match_brier_delta=args.max_single_match_brier_delta,
        max_single_match_log_loss_delta=args.max_single_match_log_loss_delta,
        diagnostics_options=HistoricalMarketMovementSignalDiagnosticOptions(
            min_abs_probability_delta=args.min_abs_probability_delta,
            movement_direction_epsilon=args.movement_direction_epsilon,
            delta_bands=tuple(_csv(args.delta_bands)),
            opening_probability_bands=tuple(_csv(args.opening_probability_bands)),
            min_group_sample_size=args.min_diagnostics_group_sample_size,
            include_competition_groups=args.include_competition_groups,
            observation_sample_limit=args.observation_sample_limit,
        ),
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=tuple(_csv(args.pass_types)),
            modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
            strategy=cast(RecommendationStrategy, args.strategy),
            unit_stake=args.unit_stake,
            max_budget=args.max_budget,
            min_probability=args.min_probability,
            min_data_quality_score=args.min_data_quality_score,
            max_outcomes_per_fixture=args.max_outcomes_per_fixture,
            candidate_fixture_limit=args.candidate_fixture_limit,
            max_candidates_per_fixture=args.max_candidates_per_fixture,
            scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
            derive_market_context_signals=args.derive_market_context_signals,
            optimizer_profile=cast(HistoricalOptimizerProfile, args.optimizer_profile),
        ),
        quality_gate_options=HistoricalRecommendationSuiteQualityGateOptions(
            min_slice_count=args.min_slice_count,
            min_comparison_count=args.min_comparison_count,
            min_final_hit_sample_size=args.min_final_hit_sample_size,
            min_candidate_final_hit_rate=args.min_candidate_final_hit_rate,
            min_candidate_roi=args.min_candidate_roi,
            fail_on_suite_statuses=tuple(_csv(args.fail_on_suite_statuses)),
            min_final_hit_rate_delta=args.min_final_hit_rate_delta,
            min_roi_delta=args.min_roi_delta,
            min_profit_loss_delta=args.min_profit_loss_delta,
            max_brier_score_delta=args.max_brier_score_delta,
            max_log_loss_delta=args.max_log_loss_delta,
            max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
            min_final_answer_changed_count=args.min_final_answer_changed_count,
            max_warning_count=args.max_warning_count,
        ),
    )
    return HistoricalMarketMovementRiskFilterRollingAdmissionOptions(
        admission_id=args.admission_id,
        sample_readiness_report_path=args.sample_readiness_report_path,
        require_sample_readiness=args.require_sample_readiness,
        require_sample_ready_allowed=not args.allow_sample_readiness_shadow_only,
        segment_gate_options=segment_gate_options,
        min_overall_candidate_count=args.min_overall_candidate_count,
        min_overall_accepted_count=args.min_overall_accepted_count,
        min_overall_adjusted_fixture_count=args.min_overall_adjusted_fixture_count,
        require_overall_best_candidate_accepted=(
            args.require_overall_best_candidate_accepted
        ),
        min_fold_slice_count=args.min_fold_slice_count,
        min_fold_fixture_count=args.min_fold_fixture_count,
        min_fold_candidate_count=args.min_fold_candidate_count,
        min_fold_accepted_count=args.min_fold_accepted_count,
        min_fold_adjusted_fixture_count=args.min_fold_adjusted_fixture_count,
        require_fold_best_candidate_accepted=args.require_fold_best_candidate_accepted,
        max_failed_fold_count=args.max_failed_fold_count,
        min_active_competition_fold_count=args.min_active_competition_fold_count,
        min_active_season_cutoff_fold_count=args.min_active_season_cutoff_fold_count,
        min_active_rolling_fold_count=args.min_active_rolling_fold_count,
        rolling_window_season_count=args.rolling_window_season_count,
        rolling_window_step=args.rolling_window_step,
        max_report_folds=args.max_report_folds,
    )


def _load_segment_gate_report(
    path: Path | None,
) -> HistoricalMarketMovementSegmentGateReport | None:
    if path is None:
        return None
    return HistoricalMarketMovementSegmentGateReport.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _load_sample_readiness_report(
    path: Path | None,
) -> HistoricalPrematchFeatureSampleReadinessReport | None:
    if path is None:
        return None
    return load_historical_prematch_feature_sample_readiness_report(path)


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    historical_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
    ]
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = []
    if args.suite_manifest is not None:
        manifest_result = load_historical_recommendation_suite_manifest_bundle(
            args.suite_manifest
        )
        historical_slices = [*manifest_result.slices, *historical_slices]
        warnings.extend(manifest_result.warnings)
    return _LoadedHistoricalSlices(
        slices=historical_slices,
        manifest_result=manifest_result,
        warnings=warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "enabled_slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
