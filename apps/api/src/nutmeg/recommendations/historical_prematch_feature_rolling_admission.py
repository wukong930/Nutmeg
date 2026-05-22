from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from re import search
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_prematch_feature_ablation_grid import (
    HistoricalPrematchFeatureAblationGridReport,
    build_historical_prematch_feature_ablation_grid_report,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_prematch_feature_final_answer_gate import (
    DEFAULT_PREMATCH_FEATURE_FINAL_ANSWER_GATE_ID,
    HistoricalPrematchFeatureFinalAnswerGateOptions,
    HistoricalPrematchFeatureFinalAnswerGateReport,
    _load_grid_report,
    build_historical_prematch_feature_final_answer_gate_report,
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

type HistoricalPrematchFeatureRollingAdmissionStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]
type HistoricalPrematchFeatureRollingAdmissionCheckStatus = Literal[
    "passed",
    "failed",
    "skipped",
]
type HistoricalPrematchFeatureRollingAdmissionFoldStatus = Literal[
    "passed",
    "failed",
    "skipped",
]
type HistoricalPrematchFeatureRollingAdmissionFoldType = Literal[
    "overall",
    "competition",
    "season_cutoff",
    "rolling_window",
]

DEFAULT_PREMATCH_FEATURE_ROLLING_ADMISSION_ID = (
    "prematch-feature-rolling-admission-shadow-v3.1"
)


class HistoricalPrematchFeatureRollingAdmissionOptions(BaseModel):
    admission_id: str = DEFAULT_PREMATCH_FEATURE_ROLLING_ADMISSION_ID
    sample_readiness_report_path: Path | None = None
    require_sample_readiness: bool = False
    require_sample_ready_allowed: bool = True
    final_answer_gate_options: HistoricalPrematchFeatureFinalAnswerGateOptions = Field(
        default_factory=HistoricalPrematchFeatureFinalAnswerGateOptions
    )
    min_overall_evaluated_candidate_count: int = Field(default=1, ge=0)
    min_overall_passing_candidate_count: int = Field(default=1, ge=0)
    min_fold_slice_count: int = Field(default=1, ge=0)
    min_fold_fixture_count: int = Field(default=1, ge=0)
    min_fold_evaluated_candidate_count: int = Field(default=1, ge=0)
    min_fold_passing_candidate_count: int = Field(default=1, ge=0)
    max_failed_fold_count: int = Field(default=0, ge=0)
    min_active_competition_fold_count: int = Field(default=1, ge=0)
    min_active_season_cutoff_fold_count: int = Field(default=1, ge=0)
    min_active_rolling_fold_count: int = Field(default=1, ge=0)
    rolling_window_season_count: int = Field(default=3, ge=1)
    rolling_window_step: int = Field(default=1, ge=1)
    max_report_folds: int = Field(default=120, ge=1, le=500)


class HistoricalPrematchFeatureRollingAdmissionCheck(BaseModel):
    name: str
    status: HistoricalPrematchFeatureRollingAdmissionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalPrematchFeatureRollingAdmissionFold(BaseModel):
    fold_id: str
    fold_type: HistoricalPrematchFeatureRollingAdmissionFoldType
    status: HistoricalPrematchFeatureRollingAdmissionFoldStatus
    source_slice_ids: list[str] = Field(default_factory=list)
    source_competition_ids: list[str] = Field(default_factory=list)
    source_season_ids: list[str] = Field(default_factory=list)
    grid_report_key: str | None = None
    gate_report_key: str | None = None
    passed_final_answer_gate: bool = False
    evaluated_candidate_count: int = Field(default=0, ge=0)
    passing_candidate_count: int = Field(default=0, ge=0)
    adjusted_fixture_count: int = Field(default=0, ge=0)
    best_feature_grid_candidate_id: str | None = None
    best_feature_grid_rank: int | None = Field(default=None, ge=1)
    best_quality_gate_passed: bool | None = None
    best_suite_status: str | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    final_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float | None = None
    failure_reasons: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchFeatureRollingAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalPrematchFeatureRollingAdmissionStatus
    candidate_feature_allowed: bool
    shadow_allowed: bool
    sample_readiness_report_path: Path | None = None
    sample_readiness_key: str | None = None
    sample_readiness_status: str | None = None
    sample_ready_allowed: bool | None = None
    sample_readiness_shadow_allowed: bool | None = None
    source_grid_report_key: str
    overall_gate_report_key: str | None = None
    overall_fold: HistoricalPrematchFeatureRollingAdmissionFold
    fold_count: int = Field(ge=0)
    active_fold_count: int = Field(ge=0)
    failed_fold_count: int = Field(ge=0)
    active_competition_fold_count: int = Field(ge=0)
    active_season_cutoff_fold_count: int = Field(ge=0)
    active_rolling_fold_count: int = Field(ge=0)
    checks: list[HistoricalPrematchFeatureRollingAdmissionCheck] = Field(
        default_factory=list
    )
    folds: list[HistoricalPrematchFeatureRollingAdmissionFold] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_prematch_feature_rolling_admission_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPrematchFeatureRollingAdmissionOptions | None = None,
    grid_report: HistoricalPrematchFeatureAblationGridReport | None = None,
    sample_readiness_report: HistoricalPrematchFeatureSampleReadinessReport | None = None,
) -> HistoricalPrematchFeatureRollingAdmissionReport:
    resolved_options = options or HistoricalPrematchFeatureRollingAdmissionOptions()
    resolved_grid_report = grid_report or build_historical_prematch_feature_ablation_grid_report(
        historical_slices,
        options=resolved_options.final_answer_gate_options.grid_options,
    )
    overall_fold = _gate_fold(
        "overall:all",
        "overall",
        historical_slices,
        grid_report=resolved_grid_report,
        options=resolved_options,
        is_overall=True,
    )
    folds = _fold_reports(
        historical_slices,
        grid_report=resolved_grid_report,
        options=resolved_options,
    )
    checks = _checks(
        overall_fold,
        folds=folds,
        sample_readiness_report=sample_readiness_report,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    active_folds = [fold for fold in folds if fold.status != "skipped"]
    failed_folds = [fold for fold in folds if fold.status == "failed"]
    if (
        _check_failed(checks, "prematch_feature_sample_readiness_present")
        or (
            sample_readiness_report is not None
            and sample_readiness_report.status == "rejected"
        )
        or _check_failed(checks, "overall_final_answer_gate_passed")
        or _check_failed(
            checks,
            "overall_passing_candidate_count",
        )
    ):
        status: HistoricalPrematchFeatureRollingAdmissionStatus = "rejected"
    elif failed_checks:
        status = "shadow_only"
    else:
        status = "accepted"
    candidate_feature_allowed = status == "accepted"
    shadow_allowed = status in {"accepted", "shadow_only"}
    warnings = [
        *overall_fold.warning_codes,
        *[
            f"prematch_feature_rolling_admission:failed_check:{check.name}"
            for check in failed_checks
        ],
        *[
            f"prematch_feature_rolling_admission:failed_fold:{fold.fold_id}"
            for fold in failed_folds
        ],
    ]
    summary: dict[str, object] = {
        "calculation_basis": "historical_prematch_feature_rolling_admission_v3_1",
        "admission_id": resolved_options.admission_id,
        "status": status,
        "candidate_feature_allowed": candidate_feature_allowed,
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
        "source_grid_report_key": resolved_grid_report.report_key,
        "overall_gate_report_key": overall_fold.gate_report_key,
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
    return HistoricalPrematchFeatureRollingAdmissionReport(
        report_key=report_key,
        status=status,
        candidate_feature_allowed=candidate_feature_allowed,
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
        source_grid_report_key=resolved_grid_report.report_key,
        overall_gate_report_key=overall_fold.gate_report_key,
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


def load_historical_prematch_feature_rolling_admission_report(
    path: Path | str,
) -> HistoricalPrematchFeatureRollingAdmissionReport:
    return HistoricalPrematchFeatureRollingAdmissionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    grid_report = _load_grid_report(args.grid_report_path)
    sample_readiness_report = _load_sample_readiness_report(
        args.sample_readiness_report_path
    )
    report = build_historical_prematch_feature_rolling_admission_report(
        loaded_slices.slices,
        options=_options_from_args(args),
        grid_report=grid_report,
        sample_readiness_report=sample_readiness_report,
    )
    if loaded_slices.manifest_result is not None:
        report.summary_json["suite_manifest"] = _manifest_summary(
            loaded_slices.manifest_result
        )
    if loaded_slices.warnings:
        report.warnings.extend(loaded_slices.warnings)
        report.summary_json["manifest_warnings"] = loaded_slices.warnings
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
    if not report.candidate_feature_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _fold_reports(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    grid_report: HistoricalPrematchFeatureAblationGridReport,
    options: HistoricalPrematchFeatureRollingAdmissionOptions,
) -> list[HistoricalPrematchFeatureRollingAdmissionFold]:
    folds: list[HistoricalPrematchFeatureRollingAdmissionFold] = []
    for competition_id, slices in _groups_by_competition(historical_slices).items():
        folds.append(
            _gate_fold(
                f"competition:{competition_id}",
                "competition",
                slices,
                grid_report=grid_report,
                options=options,
            )
        )
    for season_id, slices in _season_cutoff_groups(historical_slices, options).items():
        folds.append(
            _gate_fold(
                f"season_cutoff:{season_id}",
                "season_cutoff",
                slices,
                grid_report=grid_report,
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
                grid_report=grid_report,
                options=options,
            )
        )
    return folds


def _gate_fold(
    fold_id: str,
    fold_type: HistoricalPrematchFeatureRollingAdmissionFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    grid_report: HistoricalPrematchFeatureAblationGridReport,
    options: HistoricalPrematchFeatureRollingAdmissionOptions,
    is_overall: bool = False,
) -> HistoricalPrematchFeatureRollingAdmissionFold:
    if not is_overall and not _has_required_fold_sample(historical_slices, options=options):
        return _skipped_fold(
            fold_id,
            fold_type,
            historical_slices,
            reason="insufficient_fold_sample",
        )
    try:
        gate_report = build_historical_prematch_feature_final_answer_gate_report(
            historical_slices,
            options=options.final_answer_gate_options,
            grid_report=grid_report,
        )
    except ValueError as exc:
        return _failed_fold(
            fold_id,
            fold_type,
            historical_slices,
            reason=str(exc),
        )
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
    fold_type: HistoricalPrematchFeatureRollingAdmissionFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    gate_report: HistoricalPrematchFeatureFinalAnswerGateReport,
    options: HistoricalPrematchFeatureRollingAdmissionOptions,
    is_overall: bool,
) -> HistoricalPrematchFeatureRollingAdmissionFold:
    best = gate_report.best_evaluation
    failure_reasons = _fold_failure_reasons(
        gate_report,
        options=options,
        is_overall=is_overall,
    )
    status: HistoricalPrematchFeatureRollingAdmissionFoldStatus = (
        "failed" if failure_reasons else "passed"
    )
    return HistoricalPrematchFeatureRollingAdmissionFold(
        fold_id=fold_id,
        fold_type=fold_type,
        status=status,
        source_slice_ids=[
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        source_competition_ids=sorted(
            {historical_slice.metadata.competition_id for historical_slice in historical_slices}
        ),
        source_season_ids=sorted(
            {_slice_season_id(historical_slice) for historical_slice in historical_slices},
            key=_season_sort_key,
        ),
        grid_report_key=gate_report.grid_report_key,
        gate_report_key=gate_report.report_key,
        passed_final_answer_gate=gate_report.passing_candidate_count > 0,
        evaluated_candidate_count=gate_report.evaluated_candidate_count,
        passing_candidate_count=gate_report.passing_candidate_count,
        adjusted_fixture_count=best.adjusted_fixture_count,
        best_feature_grid_candidate_id=best.feature_grid_candidate_id,
        best_feature_grid_rank=best.feature_grid_rank,
        best_quality_gate_passed=best.quality_gate.passed,
        best_suite_status=best.suite.status,
        brier_score_delta=_delta_number(best.deltas_json, "brier_score_delta"),
        log_loss_delta=_delta_number(best.deltas_json, "log_loss_delta"),
        mean_calibration_error_delta=_delta_number(
            best.deltas_json,
            "mean_calibration_error_delta",
        ),
        final_hit_rate_delta=_delta_number(best.deltas_json, "final_hit_rate_delta"),
        roi_delta=_delta_number(best.deltas_json, "roi_delta"),
        profit_loss_delta=_delta_number(best.deltas_json, "profit_loss_delta"),
        failure_reasons=failure_reasons,
        warning_codes=list(gate_report.warnings),
        summary_json={
            "gate_report_key": gate_report.report_key,
            "gate_summary": gate_report.summary_json,
        },
    )


def _skipped_fold(
    fold_id: str,
    fold_type: HistoricalPrematchFeatureRollingAdmissionFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    reason: str,
) -> HistoricalPrematchFeatureRollingAdmissionFold:
    return HistoricalPrematchFeatureRollingAdmissionFold(
        fold_id=fold_id,
        fold_type=fold_type,
        status="skipped",
        source_slice_ids=[
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        source_competition_ids=sorted(
            {historical_slice.metadata.competition_id for historical_slice in historical_slices}
        ),
        source_season_ids=sorted(
            {_slice_season_id(historical_slice) for historical_slice in historical_slices},
            key=_season_sort_key,
        ),
        failure_reasons=[reason],
        warning_codes=[f"prematch_feature_rolling_admission:skipped:{reason}"],
        summary_json={"skip_reason": reason},
    )


def _failed_fold(
    fold_id: str,
    fold_type: HistoricalPrematchFeatureRollingAdmissionFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    reason: str,
) -> HistoricalPrematchFeatureRollingAdmissionFold:
    return HistoricalPrematchFeatureRollingAdmissionFold(
        fold_id=fold_id,
        fold_type=fold_type,
        status="failed",
        source_slice_ids=[
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        source_competition_ids=sorted(
            {historical_slice.metadata.competition_id for historical_slice in historical_slices}
        ),
        source_season_ids=sorted(
            {_slice_season_id(historical_slice) for historical_slice in historical_slices},
            key=_season_sort_key,
        ),
        failure_reasons=[reason],
        warning_codes=[f"prematch_feature_rolling_admission:failed:{reason}"],
        summary_json={"failure_reason": reason},
    )


def _fold_failure_reasons(
    gate_report: HistoricalPrematchFeatureFinalAnswerGateReport,
    *,
    options: HistoricalPrematchFeatureRollingAdmissionOptions,
    is_overall: bool,
) -> list[str]:
    min_evaluated = (
        options.min_overall_evaluated_candidate_count
        if is_overall
        else options.min_fold_evaluated_candidate_count
    )
    min_passing = (
        options.min_overall_passing_candidate_count
        if is_overall
        else options.min_fold_passing_candidate_count
    )
    failures: list[str] = []
    if gate_report.evaluated_candidate_count < min_evaluated:
        failures.append("evaluated_candidate_count_below_threshold")
    if gate_report.passing_candidate_count < min_passing:
        failures.append("passing_candidate_count_below_threshold")
    if gate_report.best_evaluation and not gate_report.best_evaluation.quality_gate.passed:
        failures.append("best_quality_gate_not_passed")
    return failures


def _checks(
    overall_fold: HistoricalPrematchFeatureRollingAdmissionFold,
    *,
    folds: Sequence[HistoricalPrematchFeatureRollingAdmissionFold],
    sample_readiness_report: HistoricalPrematchFeatureSampleReadinessReport | None,
    options: HistoricalPrematchFeatureRollingAdmissionOptions,
) -> list[HistoricalPrematchFeatureRollingAdmissionCheck]:
    failed_fold_count = sum(1 for fold in folds if fold.status == "failed")
    checks = _sample_readiness_checks(sample_readiness_report, options=options)
    checks.extend(
        [
            _boolean_check(
                name="overall_final_answer_gate_passed",
                actual=overall_fold.passed_final_answer_gate,
                expected=True,
                detail="overall prematch feature final-answer gate should pass",
            ),
            _minimum_check(
                name="overall_evaluated_candidate_count",
                actual=overall_fold.evaluated_candidate_count,
                threshold=options.min_overall_evaluated_candidate_count,
                detail="overall admission should evaluate enough feature candidates",
            ),
            _minimum_check(
                name="overall_passing_candidate_count",
                actual=overall_fold.passing_candidate_count,
                threshold=options.min_overall_passing_candidate_count,
                detail="overall admission should keep passing feature candidates",
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
    options: HistoricalPrematchFeatureRollingAdmissionOptions,
) -> list[HistoricalPrematchFeatureRollingAdmissionCheck]:
    checks = [
        _sample_readiness_present_check(sample_readiness_report, options=options)
    ]
    if sample_readiness_report is None:
        return checks
    required = (
        options.require_sample_readiness
        or sample_readiness_report.status != "accepted"
    )
    checks.extend(
        [
            _required_bool_check(
                name="prematch_feature_sample_readiness_accepted",
                actual=sample_readiness_report.status == "accepted",
                required=required,
                detail="prematch feature sample readiness should be accepted",
            ),
            _required_bool_check(
                name="prematch_feature_sample_ready_allowed",
                actual=sample_readiness_report.sample_ready_allowed,
                required=required and options.require_sample_ready_allowed,
                detail="prematch feature sample readiness should allow learning",
            ),
            _required_bool_check(
                name="prematch_feature_sample_readiness_shadow_allowed",
                actual=sample_readiness_report.shadow_allowed,
                required=required,
                detail="prematch feature sample readiness should remain shadow-allowed",
            ),
        ]
    )
    return checks


def _sample_readiness_present_check(
    sample_readiness_report: HistoricalPrematchFeatureSampleReadinessReport | None,
    *,
    options: HistoricalPrematchFeatureRollingAdmissionOptions,
) -> HistoricalPrematchFeatureRollingAdmissionCheck:
    if not options.require_sample_readiness:
        return _skipped_check(
            name="prematch_feature_sample_readiness_present",
            actual=sample_readiness_report is not None,
            detail="prematch feature sample-readiness evidence is optional",
        )
    return HistoricalPrematchFeatureRollingAdmissionCheck(
        name="prematch_feature_sample_readiness_present",
        status="passed" if sample_readiness_report is not None else "failed",
        actual=sample_readiness_report is not None,
        threshold=True,
        detail=(
            "prematch feature sample-readiness evidence must be attached before "
            "rolling admission can pass"
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
    options: HistoricalPrematchFeatureRollingAdmissionOptions,
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
        if _has_required_fold_sample(slices, options=options):
            groups[season_id] = sorted(slices, key=_slice_sort_key)
    return groups


def _rolling_window_groups(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    options: HistoricalPrematchFeatureRollingAdmissionOptions,
) -> list[list[HistoricalRecommendationSlice]]:
    ordered_seasons = _ordered_season_ids(historical_slices)
    windows: list[list[HistoricalRecommendationSlice]] = []
    for start in range(0, len(ordered_seasons), options.rolling_window_step):
        season_window = ordered_seasons[start : start + options.rolling_window_season_count]
        if len(season_window) < options.rolling_window_season_count:
            break
        selected_seasons = set(season_window)
        slices = [
            historical_slice
            for historical_slice in historical_slices
            if _slice_season_id(historical_slice) in selected_seasons
        ]
        if _has_required_fold_sample(slices, options=options):
            windows.append(sorted(slices, key=_slice_sort_key))
    return windows


def _has_required_fold_sample(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPrematchFeatureRollingAdmissionOptions,
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
    folds: Sequence[HistoricalPrematchFeatureRollingAdmissionFold],
    fold_type: HistoricalPrematchFeatureRollingAdmissionFoldType,
) -> int:
    return sum(
        1 for fold in folds if fold.fold_type == fold_type and fold.status != "skipped"
    )


def _check_failed(
    checks: Sequence[HistoricalPrematchFeatureRollingAdmissionCheck],
    name: str,
) -> bool:
    return any(check.name == name and check.status == "failed" for check in checks)


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
) -> HistoricalPrematchFeatureRollingAdmissionCheck:
    return HistoricalPrematchFeatureRollingAdmissionCheck(
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
) -> HistoricalPrematchFeatureRollingAdmissionCheck:
    if actual is None:
        return HistoricalPrematchFeatureRollingAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalPrematchFeatureRollingAdmissionCheck(
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
) -> HistoricalPrematchFeatureRollingAdmissionCheck:
    if actual is None:
        return HistoricalPrematchFeatureRollingAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalPrematchFeatureRollingAdmissionCheck(
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
) -> HistoricalPrematchFeatureRollingAdmissionCheck:
    if not required:
        return _skipped_check(name=name, actual=actual, detail=detail)
    return HistoricalPrematchFeatureRollingAdmissionCheck(
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
) -> HistoricalPrematchFeatureRollingAdmissionCheck:
    return HistoricalPrematchFeatureRollingAdmissionCheck(
        name=name,
        status="skipped",
        actual=actual,
        threshold=None,
        detail=detail,
    )


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
    checks: Sequence[HistoricalPrematchFeatureRollingAdmissionCheck],
    folds: Sequence[HistoricalPrematchFeatureRollingAdmissionFold],
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "folds": [fold.model_dump(mode="json") for fold in folds],
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_prematch_feature_rolling_admission:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run rolling admission for frozen prematch feature final-answer candidates."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--grid-report-path", type=Path)
    parser.add_argument("--sample-readiness-report-path", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--admission-id",
        "--rolling-admission-id",
        dest="admission_id",
        default=DEFAULT_PREMATCH_FEATURE_ROLLING_ADMISSION_ID,
    )
    parser.add_argument("--gate-id", default=DEFAULT_PREMATCH_FEATURE_FINAL_ANSWER_GATE_ID)
    parser.add_argument("--top-candidate-limit", type=int, default=5)
    parser.add_argument("--allow-grid-regression-candidates", action="store_true")
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
    parser.add_argument("--max-warning-count", type=int)
    parser.add_argument("--min-overall-evaluated-candidate-count", type=int, default=1)
    parser.add_argument("--min-overall-passing-candidate-count", type=int, default=1)
    parser.add_argument("--min-fold-slice-count", type=int, default=1)
    parser.add_argument("--min-fold-fixture-count", type=int, default=1)
    parser.add_argument("--min-fold-evaluated-candidate-count", type=int, default=1)
    parser.add_argument("--min-fold-passing-candidate-count", type=int, default=1)
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


def _options_from_args(args: Namespace) -> HistoricalPrematchFeatureRollingAdmissionOptions:
    final_answer_gate_options = HistoricalPrematchFeatureFinalAnswerGateOptions(
        gate_id=args.gate_id,
        top_candidate_limit=args.top_candidate_limit,
        require_grid_non_regression_candidate=not args.allow_grid_regression_candidates,
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
            max_warning_count=args.max_warning_count,
        ),
    )
    return HistoricalPrematchFeatureRollingAdmissionOptions(
        admission_id=args.admission_id,
        sample_readiness_report_path=args.sample_readiness_report_path,
        require_sample_readiness=args.require_sample_readiness,
        require_sample_ready_allowed=not args.allow_sample_readiness_shadow_only,
        final_answer_gate_options=final_answer_gate_options,
        min_overall_evaluated_candidate_count=args.min_overall_evaluated_candidate_count,
        min_overall_passing_candidate_count=args.min_overall_passing_candidate_count,
        min_fold_slice_count=args.min_fold_slice_count,
        min_fold_fixture_count=args.min_fold_fixture_count,
        min_fold_evaluated_candidate_count=args.min_fold_evaluated_candidate_count,
        min_fold_passing_candidate_count=args.min_fold_passing_candidate_count,
        max_failed_fold_count=args.max_failed_fold_count,
        min_active_competition_fold_count=args.min_active_competition_fold_count,
        min_active_season_cutoff_fold_count=args.min_active_season_cutoff_fold_count,
        min_active_rolling_fold_count=args.min_active_rolling_fold_count,
        rolling_window_season_count=args.rolling_window_season_count,
        rolling_window_step=args.rolling_window_step,
        max_report_folds=args.max_report_folds,
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
