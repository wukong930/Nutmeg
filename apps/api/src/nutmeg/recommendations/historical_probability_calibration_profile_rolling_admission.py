from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from re import search
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_probability_calibration_transform import (
    HistoricalProbabilityCalibrationTransformOptions,
)
from nutmeg.recommendations.candidate_probability_calibration import (
    CandidateProbabilityCalibrationMode,
    CandidateProbabilityCalibrationProfile,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_probability_calibration_profile_artifact import (
    DEFAULT_PROBABILITY_CALIBRATION_PROFILE_ARTIFACT_ID,
    HistoricalProbabilityCalibrationProfileArtifactOptions,
    HistoricalProbabilityCalibrationProfileArtifactReport,
    build_historical_probability_calibration_profile_artifact_report,
)
from nutmeg.recommendations.historical_probability_calibration_profile_gate import (
    DEFAULT_PROBABILITY_CALIBRATION_PROFILE_GATE_ID,
    HistoricalProbabilityCalibrationProfileGateOptions,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode

type HistoricalProbabilityCalibrationProfileRollingAdmissionStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]
type HistoricalProbabilityCalibrationProfileRollingAdmissionCheckStatus = Literal[
    "passed",
    "failed",
]
type HistoricalProbabilityCalibrationProfileRollingAdmissionFoldStatus = Literal[
    "passed",
    "failed",
    "skipped",
]
type HistoricalProbabilityCalibrationProfileRollingAdmissionFoldType = Literal[
    "overall",
    "competition",
    "season_cutoff",
    "rolling_window",
]

DEFAULT_PROBABILITY_CALIBRATION_PROFILE_ROLLING_ADMISSION_ID = (
    "probability-calibration-profile-rolling-admission-v3.1"
)


class HistoricalProbabilityCalibrationProfileRollingAdmissionOptions(BaseModel):
    rolling_admission_id: str = (
        DEFAULT_PROBABILITY_CALIBRATION_PROFILE_ROLLING_ADMISSION_ID
    )
    artifact_options: HistoricalProbabilityCalibrationProfileArtifactOptions = Field(
        default_factory=lambda: HistoricalProbabilityCalibrationProfileArtifactOptions(
            profile_mode="active",
        )
    )
    fold_quality_gate_options: HistoricalRecommendationSuiteQualityGateOptions | None = None
    admitted_profile_mode: CandidateProbabilityCalibrationMode = "active"
    min_overall_adjusted_fixture_count: int = Field(default=1, ge=0)
    min_overall_bucket_count: int = Field(default=1, ge=0)
    min_fold_adjusted_fixture_count: int = Field(default=1, ge=0)
    min_fold_bucket_count: int = Field(default=1, ge=0)
    require_fold_emitted_profile: bool = True
    min_active_competition_fold_count: int = Field(default=1, ge=0)
    min_active_season_cutoff_fold_count: int = Field(default=1, ge=0)
    min_active_rolling_fold_count: int = Field(default=1, ge=0)
    rolling_window_season_count: int = Field(default=3, ge=1)
    rolling_window_step: int = Field(default=1, ge=1)
    max_failed_fold_count: int = Field(default=0, ge=0)
    max_report_folds: int = Field(default=120, ge=1, le=500)


class HistoricalProbabilityCalibrationProfileRollingAdmissionCheck(BaseModel):
    name: str
    status: HistoricalProbabilityCalibrationProfileRollingAdmissionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalProbabilityCalibrationProfileRollingAdmissionFold(BaseModel):
    fold_id: str
    fold_type: HistoricalProbabilityCalibrationProfileRollingAdmissionFoldType
    status: HistoricalProbabilityCalibrationProfileRollingAdmissionFoldStatus
    source_slice_ids: list[str] = Field(default_factory=list)
    source_competition_ids: list[str] = Field(default_factory=list)
    source_season_ids: list[str] = Field(default_factory=list)
    artifact_report_key: str | None = None
    gate_report_key: str | None = None
    emitted_profile: bool = False
    passed_final_answer_gate: bool = False
    adjusted_fixture_count: int = Field(default=0, ge=0)
    bucket_count: int = Field(default=0, ge=0)
    selected_competition_ids: list[str] = Field(default_factory=list)
    rejected_competition_ids: list[str] = Field(default_factory=list)
    suite_status: str | None = None
    quality_gate_passed: bool | None = None
    final_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float | None = None
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    failure_reasons: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalProbabilityCalibrationProfileRollingAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalProbabilityCalibrationProfileRollingAdmissionStatus
    candidate_profile_allowed: bool
    shadow_allowed: bool
    source_artifact_report_key: str | None = None
    source_gate_report_key: str | None = None
    profile: CandidateProbabilityCalibrationProfile | None = None
    overall_fold: HistoricalProbabilityCalibrationProfileRollingAdmissionFold
    fold_count: int = Field(ge=0)
    active_fold_count: int = Field(ge=0)
    failed_fold_count: int = Field(ge=0)
    active_competition_fold_count: int = Field(ge=0)
    active_season_cutoff_fold_count: int = Field(ge=0)
    active_rolling_fold_count: int = Field(ge=0)
    checks: list[HistoricalProbabilityCalibrationProfileRollingAdmissionCheck] = Field(
        default_factory=list
    )
    folds: list[HistoricalProbabilityCalibrationProfileRollingAdmissionFold] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_probability_calibration_profile_rolling_admission_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: (
        HistoricalProbabilityCalibrationProfileRollingAdmissionOptions | None
    ) = None,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionReport:
    resolved_options = (
        options or HistoricalProbabilityCalibrationProfileRollingAdmissionOptions()
    )
    overall_artifact = build_historical_probability_calibration_profile_artifact_report(
        historical_slices,
        options=resolved_options.artifact_options,
    )
    overall_fold = _fold_report(
        "overall:all",
        "overall",
        historical_slices,
        artifact_report=overall_artifact,
        options=resolved_options,
        is_overall=True,
    )
    folds = _fold_reports(historical_slices, options=resolved_options)
    checks = _checks(overall_fold, folds=folds, options=resolved_options)
    failed_checks = [check for check in checks if check.status == "failed"]
    active_folds = [fold for fold in folds if fold.status != "skipped"]
    failed_folds = [fold for fold in folds if fold.status == "failed"]
    if _check_failed(checks, "overall_final_answer_gate_passed"):
        status: HistoricalProbabilityCalibrationProfileRollingAdmissionStatus = (
            "rejected"
        )
    elif failed_checks:
        status = "shadow_only"
    else:
        status = "accepted"
    candidate_profile_allowed = status == "accepted"
    shadow_allowed = status in {"accepted", "shadow_only"}
    profile = (
        _admitted_profile(overall_artifact.profile, options=resolved_options)
        if candidate_profile_allowed
        else None
    )
    warnings = [
        *overall_artifact.warning_codes,
        *[
            f"probability_calibration_profile_rolling_admission:"
            f"failed_check:{check.name}"
            for check in failed_checks
        ],
    ]
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_probability_calibration_profile_rolling_admission_v3_1"
        ),
        "rolling_admission_id": resolved_options.rolling_admission_id,
        "status": status,
        "candidate_profile_allowed": candidate_profile_allowed,
        "shadow_allowed": shadow_allowed,
        "source_artifact_report_key": overall_artifact.report_key,
        "source_gate_report_key": overall_artifact.gate_report_key,
        "admitted_profile_mode": resolved_options.admitted_profile_mode,
        "profile_key": profile.profile_key if profile is not None else None,
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
    return HistoricalProbabilityCalibrationProfileRollingAdmissionReport(
        report_key=report_key,
        status=status,
        candidate_profile_allowed=candidate_profile_allowed,
        shadow_allowed=shadow_allowed,
        source_artifact_report_key=overall_artifact.report_key,
        source_gate_report_key=overall_artifact.gate_report_key,
        profile=profile,
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


def load_historical_probability_calibration_profile_rolling_admission_report(
    path: Path | str,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionReport:
    return (
        HistoricalProbabilityCalibrationProfileRollingAdmissionReport.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_probability_calibration_profile_rolling_admission_report(
        loaded_slices.slices,
        options=_options_from_args(args),
    )
    if loaded_slices.manifest_result is not None:
        report.summary_json["suite_manifest"] = _manifest_summary(
            loaded_slices.manifest_result
        )
    if loaded_slices.warnings:
        report.warnings.extend(loaded_slices.warnings)
        report.summary_json["manifest_warnings"] = loaded_slices.warnings
    if args.profile_output_path is not None and report.profile is not None:
        args.profile_output_path.parent.mkdir(parents=True, exist_ok=True)
        args.profile_output_path.write_text(
            f"{report.profile.model_dump_json(indent=2)}\n",
            encoding="utf-8",
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
    if not report.candidate_profile_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _fold_reports(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
) -> list[HistoricalProbabilityCalibrationProfileRollingAdmissionFold]:
    folds: list[HistoricalProbabilityCalibrationProfileRollingAdmissionFold] = []
    for competition_id, slices in _groups_by_competition(historical_slices).items():
        folds.append(
            _artifact_fold(
                f"competition:{competition_id}",
                "competition",
                slices,
                options=options,
            )
        )
    for season_id, slices in _season_cutoff_groups(historical_slices, options).items():
        folds.append(
            _artifact_fold(
                f"season_cutoff:{season_id}",
                "season_cutoff",
                slices,
                options=options,
            )
        )
    for index, slices in enumerate(_rolling_window_groups(historical_slices, options)):
        season_ids = sorted({_slice_season_id(historical_slice) for historical_slice in slices})
        folds.append(
            _artifact_fold(
                f"rolling_window:{index + 1}:{season_ids[0]}..{season_ids[-1]}",
                "rolling_window",
                slices,
                options=options,
            )
        )
    return folds


def _artifact_fold(
    fold_id: str,
    fold_type: HistoricalProbabilityCalibrationProfileRollingAdmissionFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionFold:
    if not _has_required_calibration_history(historical_slices, options=options):
        return _skipped_fold(
            fold_id,
            fold_type,
            historical_slices,
            reason="insufficient_calibration_history",
        )
    artifact_report = build_historical_probability_calibration_profile_artifact_report(
        historical_slices,
        options=_fold_artifact_options(options),
    )
    return _fold_report(
        fold_id,
        fold_type,
        historical_slices,
        artifact_report=artifact_report,
        options=options,
        is_overall=False,
    )


def _fold_report(
    fold_id: str,
    fold_type: HistoricalProbabilityCalibrationProfileRollingAdmissionFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    artifact_report: HistoricalProbabilityCalibrationProfileArtifactReport,
    options: HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
    is_overall: bool,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionFold:
    bucket_count = len(artifact_report.profile.buckets) if artifact_report.profile else 0
    failure_reasons = _fold_failure_reasons(
        artifact_report,
        bucket_count=bucket_count,
        options=options,
        is_overall=is_overall,
    )
    status: HistoricalProbabilityCalibrationProfileRollingAdmissionFoldStatus = (
        "failed" if failure_reasons else "passed"
    )
    gate_report = artifact_report.gate_report
    aggregate_deltas = _aggregate_deltas(artifact_report)
    return HistoricalProbabilityCalibrationProfileRollingAdmissionFold(
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
        artifact_report_key=artifact_report.report_key,
        gate_report_key=artifact_report.gate_report_key,
        emitted_profile=artifact_report.emitted_profile,
        passed_final_answer_gate=gate_report.passed_final_answer_gate,
        adjusted_fixture_count=gate_report.adjusted_fixture_count,
        bucket_count=bucket_count,
        selected_competition_ids=list(gate_report.selected_competition_ids),
        rejected_competition_ids=list(gate_report.rejected_competition_ids),
        suite_status=gate_report.suite.status if gate_report.suite is not None else None,
        quality_gate_passed=(
            gate_report.quality_gate.passed if gate_report.quality_gate is not None else None
        ),
        final_hit_rate_delta=_delta_number(aggregate_deltas, "final_hit_rate_delta"),
        roi_delta=_delta_number(aggregate_deltas, "roi_delta"),
        profit_loss_delta=_delta_number(aggregate_deltas, "profit_loss_delta"),
        brier_score_delta=_delta_number(aggregate_deltas, "brier_score_delta"),
        log_loss_delta=_delta_number(aggregate_deltas, "log_loss_delta"),
        mean_calibration_error_delta=_delta_number(
            aggregate_deltas,
            "mean_calibration_error_delta",
        ),
        failure_reasons=failure_reasons,
        warning_codes=list(artifact_report.warning_codes),
        summary_json={
            "artifact_report_key": artifact_report.report_key,
            "gate_report_key": artifact_report.gate_report_key,
            "gate_summary": gate_report.summary_json,
        },
    )


def _fold_artifact_options(
    options: HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
) -> HistoricalProbabilityCalibrationProfileArtifactOptions:
    if options.fold_quality_gate_options is None:
        return options.artifact_options
    gate_options = options.artifact_options.gate_options.model_copy(
        update={"quality_gate_options": options.fold_quality_gate_options}
    )
    return options.artifact_options.model_copy(update={"gate_options": gate_options})


def _skipped_fold(
    fold_id: str,
    fold_type: HistoricalProbabilityCalibrationProfileRollingAdmissionFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    reason: str,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionFold:
    return HistoricalProbabilityCalibrationProfileRollingAdmissionFold(
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
        warning_codes=[
            f"probability_calibration_profile_rolling_admission:skipped:{reason}"
        ],
        summary_json={"skip_reason": reason},
    )


def _fold_failure_reasons(
    artifact_report: HistoricalProbabilityCalibrationProfileArtifactReport,
    *,
    bucket_count: int,
    options: HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
    is_overall: bool,
) -> list[str]:
    min_adjusted_fixture_count = (
        options.min_overall_adjusted_fixture_count
        if is_overall
        else options.min_fold_adjusted_fixture_count
    )
    min_bucket_count = (
        options.min_overall_bucket_count
        if is_overall
        else options.min_fold_bucket_count
    )
    failures: list[str] = []
    if not artifact_report.gate_report.passed_final_answer_gate:
        failures.append("final_answer_gate_not_passed")
    if options.require_fold_emitted_profile and not artifact_report.emitted_profile:
        failures.append("runtime_profile_not_emitted")
    if artifact_report.gate_report.adjusted_fixture_count < min_adjusted_fixture_count:
        failures.append("adjusted_fixture_count_below_threshold")
    if bucket_count < min_bucket_count:
        failures.append("bucket_count_below_threshold")
    return failures


def _checks(
    overall_fold: HistoricalProbabilityCalibrationProfileRollingAdmissionFold,
    *,
    folds: Sequence[HistoricalProbabilityCalibrationProfileRollingAdmissionFold],
    options: HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
) -> list[HistoricalProbabilityCalibrationProfileRollingAdmissionCheck]:
    failed_fold_count = sum(1 for fold in folds if fold.status == "failed")
    return [
        _boolean_check(
            name="overall_final_answer_gate_passed",
            actual=overall_fold.passed_final_answer_gate,
            expected=True,
            detail="overall probability calibration profile must pass final-answer gate",
        ),
        _boolean_check(
            name="overall_runtime_profile_emitted",
            actual=overall_fold.emitted_profile,
            expected=True,
            detail="overall admission must produce a runtime profile artifact",
        ),
        _minimum_check(
            name="overall_adjusted_fixture_count",
            actual=overall_fold.adjusted_fixture_count,
            threshold=options.min_overall_adjusted_fixture_count,
            detail="overall admission should adjust enough held-out fixtures",
        ),
        _minimum_check(
            name="overall_bucket_count",
            actual=overall_fold.bucket_count,
            threshold=options.min_overall_bucket_count,
            detail="overall admission should produce usable runtime buckets",
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


def _admitted_profile(
    profile: CandidateProbabilityCalibrationProfile | None,
    *,
    options: HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
) -> CandidateProbabilityCalibrationProfile | None:
    if profile is None:
        return None
    return profile.model_copy(update={"mode": options.admitted_profile_mode})


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
    options: HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
) -> dict[str, list[HistoricalRecommendationSlice]]:
    ordered_seasons = _ordered_season_ids(historical_slices)
    required_seasons = _required_season_count(options)
    groups: dict[str, list[HistoricalRecommendationSlice]] = {}
    for index in range(required_seasons - 1, len(ordered_seasons)):
        season_id = ordered_seasons[index]
        included_seasons = set(ordered_seasons[: index + 1])
        groups[season_id] = sorted(
            [
                historical_slice
                for historical_slice in historical_slices
                if _slice_season_id(historical_slice) in included_seasons
            ],
            key=_slice_sort_key,
        )
    return groups


def _rolling_window_groups(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    options: HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
) -> list[list[HistoricalRecommendationSlice]]:
    ordered_seasons = _ordered_season_ids(historical_slices)
    required_seasons = _required_season_count(options)
    window_size = max(options.rolling_window_season_count, required_seasons)
    windows: list[list[HistoricalRecommendationSlice]] = []
    for start in range(0, len(ordered_seasons), options.rolling_window_step):
        season_window = ordered_seasons[start : start + window_size]
        if len(season_window) < window_size:
            break
        selected_seasons = set(season_window)
        windows.append(
            sorted(
                [
                    historical_slice
                    for historical_slice in historical_slices
                    if _slice_season_id(historical_slice) in selected_seasons
                ],
                key=_slice_sort_key,
            )
        )
    return windows


def _has_required_calibration_history(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
) -> bool:
    required = _required_season_count(options)
    if not options.artifact_options.gate_options.transform_options.group_by_competition:
        return len(_ordered_season_ids(historical_slices)) >= required
    return any(
        len({_slice_season_id(historical_slice) for historical_slice in slices})
        >= required
        for slices in _groups_by_competition(historical_slices).values()
    )


def _required_season_count(
    options: HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
) -> int:
    transform_options = options.artifact_options.gate_options.transform_options
    return (
        transform_options.min_training_season_count
        + transform_options.holdout_season_count
    )


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
    folds: Sequence[HistoricalProbabilityCalibrationProfileRollingAdmissionFold],
    fold_type: HistoricalProbabilityCalibrationProfileRollingAdmissionFoldType,
) -> int:
    return sum(
        1 for fold in folds if fold.fold_type == fold_type and fold.status != "skipped"
    )


def _check_failed(
    checks: Sequence[HistoricalProbabilityCalibrationProfileRollingAdmissionCheck],
    name: str,
) -> bool:
    return any(check.name == name and check.status == "failed" for check in checks)


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionCheck:
    return HistoricalProbabilityCalibrationProfileRollingAdmissionCheck(
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
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionCheck:
    if actual is None:
        return HistoricalProbabilityCalibrationProfileRollingAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalProbabilityCalibrationProfileRollingAdmissionCheck(
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
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionCheck:
    if actual is None:
        return HistoricalProbabilityCalibrationProfileRollingAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalProbabilityCalibrationProfileRollingAdmissionCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _aggregate_deltas(
    artifact_report: HistoricalProbabilityCalibrationProfileArtifactReport,
) -> Mapping[str, object]:
    suite = artifact_report.gate_report.suite
    if suite is not None:
        return suite.aggregate_deltas_json
    value = artifact_report.gate_report.summary_json.get("aggregate_deltas_json")
    if isinstance(value, Mapping):
        return value
    return {}


def _delta_number(values: Mapping[str, object], key: str) -> float | None:
    value = values.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run rolling admission for historical probability calibration "
            "runtime profile artifacts."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--profile-output-path", type=Path)
    parser.add_argument(
        "--rolling-admission-id",
        default=DEFAULT_PROBABILITY_CALIBRATION_PROFILE_ROLLING_ADMISSION_ID,
    )
    parser.add_argument(
        "--artifact-id",
        default=DEFAULT_PROBABILITY_CALIBRATION_PROFILE_ARTIFACT_ID,
    )
    parser.add_argument("--profile-mode", choices=["active", "shadow"], default="active")
    parser.add_argument("--allow-failed-final-answer-gate", action="store_true")
    parser.add_argument("--gate-id", default=DEFAULT_PROBABILITY_CALIBRATION_PROFILE_GATE_ID)
    parser.add_argument("--competition-ids", default="")
    parser.add_argument("--include-rejected-transform-competitions", action="store_true")
    parser.add_argument("--target-outcomes", default="")
    parser.add_argument("--probability-min", type=float, default=0.0)
    parser.add_argument("--probability-max", type=float, default=1.0)
    parser.add_argument("--min-decimal-odds", type=float)
    parser.add_argument("--max-decimal-odds", type=float)
    parser.add_argument("--holdout-season-count", type=int, default=1)
    parser.add_argument("--min-training-season-count", type=int, default=2)
    parser.add_argument("--min-validation-sample-size", type=int, default=100)
    parser.add_argument(
        "--segment-mode",
        choices=["probability_bucket", "market_odds_band"],
        default="probability_bucket",
    )
    parser.add_argument("--bucket-size", type=float, default=0.10)
    parser.add_argument("--min-bucket-sample-size", type=int, default=30)
    parser.add_argument("--blend-weight", type=float, default=1.0)
    parser.add_argument("--min-calibrated-probability", type=float, default=0.01)
    parser.add_argument("--max-calibrated-probability", type=float, default=0.95)
    parser.add_argument("--group-all-competitions", action="store_true")
    parser.add_argument("--pass-types", default="1x1,2x1,3x1,4x1")
    parser.add_argument("--modes", default="single,multiple")
    parser.add_argument(
        "--optimizer-profile",
        choices=["heuristic", "solver"],
        default="solver",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--final-answer-scenario-variant-count", type=int, default=1)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument("--min-final-hit-sample-size", type=int, default=1)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-final-answer-changed-count", type=int, default=0)
    parser.add_argument("--min-roi-delta", type=float)
    parser.add_argument("--min-profit-loss-delta", type=float)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--fold-min-final-hit-sample-size", type=int)
    parser.add_argument("--fold-min-final-hit-rate-delta", type=float)
    parser.add_argument("--fold-min-final-answer-changed-count", type=int)
    parser.add_argument("--fold-min-roi-delta", type=float)
    parser.add_argument("--fold-min-profit-loss-delta", type=float)
    parser.add_argument("--fold-max-brier-score-delta", type=float)
    parser.add_argument("--fold-max-log-loss-delta", type=float)
    parser.add_argument("--fold-max-mean-calibration-error-delta", type=float)
    parser.add_argument("--min-overall-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--min-overall-bucket-count", type=int, default=1)
    parser.add_argument("--min-fold-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--min-fold-bucket-count", type=int, default=1)
    parser.add_argument("--allow-fold-without-profile", action="store_true")
    parser.add_argument("--min-active-competition-fold-count", type=int, default=1)
    parser.add_argument("--min-active-season-cutoff-fold-count", type=int, default=1)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=1)
    parser.add_argument("--rolling-window-season-count", type=int, default=3)
    parser.add_argument("--rolling-window-step", type=int, default=1)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--max-report-folds", type=int, default=120)
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionOptions:
    quality_gate_options = HistoricalRecommendationSuiteQualityGateOptions(
        min_final_hit_sample_size=args.min_final_hit_sample_size,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_final_answer_changed_count=args.min_final_answer_changed_count,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=(
            args.max_mean_calibration_error_delta
        ),
    )
    artifact_options = HistoricalProbabilityCalibrationProfileArtifactOptions(
        artifact_id=args.artifact_id,
        profile_mode=cast(CandidateProbabilityCalibrationMode, args.profile_mode),
        require_passed_final_answer_gate=not args.allow_failed_final_answer_gate,
        gate_options=HistoricalProbabilityCalibrationProfileGateOptions(
            gate_id=args.gate_id,
            competition_ids=_split_csv(args.competition_ids),
            require_transform_acceptance=not args.include_rejected_transform_competitions,
            target_outcomes=_split_csv(args.target_outcomes),
            probability_min=args.probability_min,
            probability_max=args.probability_max,
            min_decimal_odds=args.min_decimal_odds,
            max_decimal_odds=args.max_decimal_odds,
            transform_options=HistoricalProbabilityCalibrationTransformOptions(
                holdout_season_count=args.holdout_season_count,
                min_training_season_count=args.min_training_season_count,
                min_validation_sample_size=args.min_validation_sample_size,
                segment_mode=args.segment_mode,
                bucket_size=args.bucket_size,
                min_bucket_sample_size=args.min_bucket_sample_size,
                blend_weight=args.blend_weight,
                min_calibrated_probability=args.min_calibrated_probability,
                max_calibrated_probability=args.max_calibrated_probability,
                group_by_competition=not args.group_all_competitions,
                prediction_sample_limit=0,
            ),
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=_split_csv(args.pass_types),
                modes=cast(tuple[RecommendationMode, ...], _split_csv(args.modes)),
                optimizer_profile=cast(
                    HistoricalOptimizerProfile,
                    args.optimizer_profile,
                ),
                unit_stake=args.unit_stake,
                max_budget=args.max_budget,
                min_probability=args.min_probability,
                candidate_fixture_limit=args.candidate_fixture_limit,
                max_candidates_per_fixture=args.max_candidates_per_fixture,
                final_answer_scenario_variant_count=(
                    args.final_answer_scenario_variant_count
                ),
                derive_market_context_signals=args.derive_market_context_signals,
            ),
            quality_gate_options=quality_gate_options,
        ),
    )
    return HistoricalProbabilityCalibrationProfileRollingAdmissionOptions(
        rolling_admission_id=args.rolling_admission_id,
        artifact_options=artifact_options,
        fold_quality_gate_options=_fold_quality_gate_options_from_args(
            args,
            quality_gate_options,
        ),
        admitted_profile_mode=cast(CandidateProbabilityCalibrationMode, args.profile_mode),
        min_overall_adjusted_fixture_count=args.min_overall_adjusted_fixture_count,
        min_overall_bucket_count=args.min_overall_bucket_count,
        min_fold_adjusted_fixture_count=args.min_fold_adjusted_fixture_count,
        min_fold_bucket_count=args.min_fold_bucket_count,
        require_fold_emitted_profile=not args.allow_fold_without_profile,
        min_active_competition_fold_count=args.min_active_competition_fold_count,
        min_active_season_cutoff_fold_count=args.min_active_season_cutoff_fold_count,
        min_active_rolling_fold_count=args.min_active_rolling_fold_count,
        rolling_window_season_count=args.rolling_window_season_count,
        rolling_window_step=args.rolling_window_step,
        max_failed_fold_count=args.max_failed_fold_count,
        max_report_folds=args.max_report_folds,
    )


def _fold_quality_gate_options_from_args(
    args: Namespace,
    base_options: HistoricalRecommendationSuiteQualityGateOptions,
) -> HistoricalRecommendationSuiteQualityGateOptions | None:
    override_fields = {
        "min_final_hit_sample_size": args.fold_min_final_hit_sample_size,
        "min_final_hit_rate_delta": args.fold_min_final_hit_rate_delta,
        "min_final_answer_changed_count": args.fold_min_final_answer_changed_count,
        "min_roi_delta": args.fold_min_roi_delta,
        "min_profit_loss_delta": args.fold_min_profit_loss_delta,
        "max_brier_score_delta": args.fold_max_brier_score_delta,
        "max_log_loss_delta": args.fold_max_log_loss_delta,
        "max_mean_calibration_error_delta": (
            args.fold_max_mean_calibration_error_delta
        ),
    }
    updates = {
        field: value
        for field, value in override_fields.items()
        if value is not None
    }
    if not updates:
        return None
    return base_options.model_copy(update=updates)


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
        "slice_count": len(manifest_result.slices),
        "warnings": manifest_result.warnings,
    }


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalProbabilityCalibrationProfileRollingAdmissionCheck],
    folds: Sequence[HistoricalProbabilityCalibrationProfileRollingAdmissionFold],
) -> str:
    payload = {
        "summary": summary,
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "actual": check.actual,
                "threshold": check.threshold,
            }
            for check in checks
        ],
        "folds": [
            {
                "fold_id": fold.fold_id,
                "status": fold.status,
                "passed_final_answer_gate": fold.passed_final_answer_gate,
                "adjusted_fixture_count": fold.adjusted_fixture_count,
                "bucket_count": fold.bucket_count,
                "failure_reasons": fold.failure_reasons,
            }
            for fold in folds
        ],
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_rolling_admission:{digest}"


if __name__ == "__main__":
    main()
