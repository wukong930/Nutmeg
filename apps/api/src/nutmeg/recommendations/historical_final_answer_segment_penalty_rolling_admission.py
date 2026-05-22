from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from re import search
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationScenarioResult,
    HistoricalRecommendationSlice,
    build_historical_competition_season_index_by_slice_id,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest_suite,
)
from nutmeg.recommendations.historical_final_answer_segment_penalty_grid import (
    HistoricalFinalAnswerSegmentPenaltyCandidate,
    HistoricalFinalAnswerSegmentPenaltyGridReport,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalFinalAnswerSegmentPenaltyRollingAdmissionStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]
type HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheckStatus = Literal[
    "passed",
    "failed",
]
type HistoricalFinalAnswerSegmentPenaltyFoldStatus = Literal[
    "passed",
    "failed",
    "skipped",
]


class HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions(BaseModel):
    candidate_key: str | None = None
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic"
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver"
    require_grid_candidate_accepted: bool = True
    min_overall_final_answer_count: int = Field(default=30, ge=1)
    min_overall_penalty_option_count: int = Field(default=1, ge=0)
    min_overall_final_hit_count_delta: int = 0
    min_overall_final_hit_rate_delta: float = 0.0
    min_overall_roi_delta: float = 0.0
    min_overall_profit_loss_delta: float = 0.0
    max_overall_brier_score_delta: float = 0.0
    max_overall_log_loss_delta: float = 0.0
    max_overall_mean_calibration_error_delta: float = 0.0
    max_overall_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_overall_final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_overall_profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    min_fold_final_answer_count: int = Field(default=1, ge=1)
    min_fold_penalty_option_count: int = Field(default=1, ge=0)
    min_fold_final_hit_count_delta: int = 0
    min_fold_final_hit_rate_delta: float = 0.0
    min_fold_roi_delta: float = 0.0
    min_fold_profit_loss_delta: float = 0.0
    max_fold_brier_score_delta: float = 0.0
    max_fold_log_loss_delta: float = 0.0
    max_fold_mean_calibration_error_delta: float = 0.0
    max_fold_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_fold_final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    max_fold_profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    min_active_competition_fold_count: int = Field(default=2, ge=0)
    min_active_season_fold_count: int = Field(default=1, ge=0)
    min_active_rolling_fold_count: int = Field(default=1, ge=0)
    rolling_window_slice_count: int = Field(default=12, ge=1)
    rolling_window_step: int = Field(default=6, ge=1)
    max_failed_fold_count: int = Field(default=0, ge=0)
    max_report_folds: int = Field(default=120, ge=1, le=500)


class HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck(BaseModel):
    name: str
    status: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheckStatus
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    detail: str


class HistoricalFinalAnswerSegmentPenaltyFold(BaseModel):
    fold_id: str
    fold_type: str
    status: HistoricalFinalAnswerSegmentPenaltyFoldStatus
    source_slice_ids: list[str] = Field(default_factory=list)
    final_answer_count: int = Field(ge=0)
    penalty_option_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    baseline_final_answer_hit_count: int = Field(ge=0)
    candidate_final_answer_hit_count: int = Field(ge=0)
    final_answer_hit_delta_count: int
    final_answer_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    harm_count_vs_baseline: int = Field(ge=0)
    final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    improvement_count_vs_baseline: int = Field(ge=0)
    failure_reasons: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionStatus
    candidate_profile_allowed: bool
    shadow_allowed: bool
    source_grid_report_key: str
    source_candidate_key: str
    candidate_summary_json: dict[str, object] = Field(default_factory=dict)
    overall_fold: HistoricalFinalAnswerSegmentPenaltyFold
    fold_count: int = Field(ge=0)
    active_fold_count: int = Field(ge=0)
    failed_fold_count: int = Field(ge=0)
    active_competition_fold_count: int = Field(ge=0)
    active_season_fold_count: int = Field(ge=0)
    active_rolling_fold_count: int = Field(ge=0)
    checks: list[HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck] = Field(
        default_factory=list
    )
    folds: list[HistoricalFinalAnswerSegmentPenaltyFold] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def load_historical_final_answer_segment_penalty_grid_report(
    path: Path | str,
) -> HistoricalFinalAnswerSegmentPenaltyGridReport:
    return HistoricalFinalAnswerSegmentPenaltyGridReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def build_historical_final_answer_segment_penalty_rolling_admission_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    grid_report: HistoricalFinalAnswerSegmentPenaltyGridReport,
    options: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions | None = None,
) -> HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport:
    resolved_options = (
        options or HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions()
    )
    resolved_options = _options_with_global_competition_season_context(
        resolved_options,
        historical_slices,
    )
    candidate = _selected_candidate(grid_report, resolved_options)
    overall_fold = _fold_report(
        "overall:all",
        "overall",
        historical_slices,
        candidate=candidate,
        options=resolved_options,
    )
    folds = _fold_reports(historical_slices, candidate=candidate, options=resolved_options)
    checks = _checks(
        grid_report,
        candidate,
        overall_fold=overall_fold,
        folds=folds,
        options=resolved_options,
    )
    failed_checks = [check for check in checks if check.status == "failed"]
    active_folds = [fold for fold in folds if fold.status != "skipped"]
    failed_folds = [fold for fold in folds if fold.status == "failed"]
    if _check_failed(checks, "overall_gate_passed"):
        status: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionStatus = "rejected"
    elif failed_checks:
        status = "shadow_only"
    else:
        status = "accepted"
    candidate_allowed = status == "accepted"
    shadow_allowed = status in {"accepted", "shadow_only"}
    warnings = [
        f"segment_penalty_rolling_admission:failed_check:{check.name}"
        for check in failed_checks
    ]
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_final_answer_segment_penalty_rolling_admission_v3_1"
        ),
        "status": status,
        "candidate_profile_allowed": candidate_allowed,
        "shadow_allowed": shadow_allowed,
        "source_grid_report_key": grid_report.report_key,
        "source_candidate_key": candidate.candidate_key,
        "candidate_status": candidate.status,
        "candidate_strength": candidate.strength,
        "candidate_pass_types": list(candidate.pass_types),
        "candidate_modes": list(candidate.modes),
        "candidate_competition_ids": list(candidate.competition_ids),
        "candidate_season_ids": list(candidate.season_ids),
        "candidate_min_competition_season_index": (
            candidate.min_competition_season_index
        ),
        "candidate_max_competition_season_index": (
            candidate.max_competition_season_index
        ),
        "overall": overall_fold.model_dump(mode="json"),
        "fold_count": len(folds),
        "active_fold_count": len(active_folds),
        "failed_fold_count": len(failed_folds),
        "active_competition_fold_count": _active_fold_count(folds, "competition"),
        "active_season_fold_count": _active_fold_count(folds, "season"),
        "active_rolling_fold_count": _active_fold_count(folds, "rolling_window"),
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, folds)
    return HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport(
        report_key=report_key,
        status=status,
        candidate_profile_allowed=candidate_allowed,
        shadow_allowed=shadow_allowed,
        source_grid_report_key=grid_report.report_key,
        source_candidate_key=candidate.candidate_key,
        candidate_summary_json=candidate.summary_json,
        overall_fold=overall_fold,
        fold_count=len(folds),
        active_fold_count=len(active_folds),
        failed_fold_count=len(failed_folds),
        active_competition_fold_count=_active_fold_count(folds, "competition"),
        active_season_fold_count=_active_fold_count(folds, "season"),
        active_rolling_fold_count=_active_fold_count(folds, "rolling_window"),
        checks=checks,
        folds=folds[: resolved_options.max_report_folds],
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def _options_with_global_competition_season_context(
    options: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions,
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions:
    if options.backtest_options.competition_season_index_by_slice_id:
        return options
    return options.model_copy(
        update={
            "backtest_options": options.backtest_options.model_copy(
                update={
                    "competition_season_index_by_slice_id": (
                        build_historical_competition_season_index_by_slice_id(
                            historical_slices
                        )
                    )
                }
            )
        }
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_final_answer_segment_penalty_rolling_admission_report(
        loaded_slices.slices,
        grid_report=load_historical_final_answer_segment_penalty_grid_report(
            args.grid_report
        ),
        options=_options_from_args(args),
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
    if not report.candidate_profile_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _selected_candidate(
    grid_report: HistoricalFinalAnswerSegmentPenaltyGridReport,
    options: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions,
) -> HistoricalFinalAnswerSegmentPenaltyCandidate:
    candidates = [*grid_report.accepted_candidates, *grid_report.candidates]
    if options.candidate_key is not None:
        candidate = next(
            (
                candidate
                for candidate in candidates
                if candidate.candidate_key == options.candidate_key
            ),
            None,
        )
        if candidate is None:
            raise ValueError(f"Candidate not found in grid report: {options.candidate_key}")
        return candidate
    if grid_report.best_candidate is None:
        raise ValueError("Grid report has no best_candidate")
    return grid_report.best_candidate


def _fold_reports(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    candidate: HistoricalFinalAnswerSegmentPenaltyCandidate,
    options: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions,
) -> list[HistoricalFinalAnswerSegmentPenaltyFold]:
    folds: list[HistoricalFinalAnswerSegmentPenaltyFold] = []
    for competition_id, slices in _groups_by_competition(historical_slices).items():
        folds.append(
            _fold_report(
                f"competition:{competition_id}",
                "competition",
                slices,
                candidate=candidate,
                options=options,
            )
        )
    for season_id, slices in _groups_by_season(historical_slices).items():
        folds.append(
            _fold_report(
                f"season:{season_id}",
                "season",
                slices,
                candidate=candidate,
                options=options,
            )
        )
    for index, slices in enumerate(_rolling_window_groups(historical_slices, options)):
        slice_ids = [historical_slice.metadata.slice_id for historical_slice in slices]
        folds.append(
            _fold_report(
                f"rolling_window:{index + 1}:{slice_ids[0]}..{slice_ids[-1]}",
                "rolling_window",
                slices,
                candidate=candidate,
                options=options,
            )
        )
    return folds


def _fold_report(
    fold_id: str,
    fold_type: str,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    candidate: HistoricalFinalAnswerSegmentPenaltyCandidate,
    options: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions,
) -> HistoricalFinalAnswerSegmentPenaltyFold:
    baseline_suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=_baseline_backtest_options(options.backtest_options),
        baseline_optimizer_profile=options.baseline_optimizer_profile,
        candidate_optimizer_profile=options.candidate_optimizer_profile,
    )
    candidate_suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=_candidate_backtest_options(options.backtest_options, candidate),
        baseline_optimizer_profile=options.baseline_optimizer_profile,
        candidate_optimizer_profile=options.candidate_optimizer_profile,
    )
    metrics = _suite_pair_metrics(baseline_suite, candidate_suite)
    failure_reasons = _fold_failure_reasons(metrics, options=options)
    skipped = (
        metrics.final_answer_count < options.min_fold_final_answer_count
        or metrics.penalty_option_count < options.min_fold_penalty_option_count
    )
    status: HistoricalFinalAnswerSegmentPenaltyFoldStatus = (
        "skipped" if skipped else "failed" if failure_reasons else "passed"
    )
    return HistoricalFinalAnswerSegmentPenaltyFold(
        fold_id=fold_id,
        fold_type=fold_type,
        status=status,
        source_slice_ids=[
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        final_answer_count=metrics.final_answer_count,
        penalty_option_count=metrics.penalty_option_count,
        changed_final_answer_count=metrics.changed_final_answer_count,
        baseline_final_answer_hit_count=metrics.baseline_final_answer_hit_count,
        candidate_final_answer_hit_count=metrics.candidate_final_answer_hit_count,
        final_answer_hit_delta_count=metrics.final_answer_hit_delta_count,
        final_answer_hit_rate_delta=metrics.final_answer_hit_rate_delta,
        roi_delta=metrics.roi_delta,
        profit_loss_delta=metrics.profit_loss_delta,
        brier_score_delta=metrics.brier_score_delta,
        log_loss_delta=metrics.log_loss_delta,
        mean_calibration_error_delta=metrics.mean_calibration_error_delta,
        harm_count_vs_baseline=metrics.harm_count_vs_baseline,
        final_hit_harm_count_vs_baseline=metrics.final_hit_harm_count_vs_baseline,
        profit_loss_harm_count_vs_baseline=metrics.profit_loss_harm_count_vs_baseline,
        improvement_count_vs_baseline=metrics.improvement_count_vs_baseline,
        failure_reasons=[] if skipped else failure_reasons,
        summary_json={
            "baseline_suite_key": baseline_suite.suite_key,
            "candidate_suite_key": candidate_suite.suite_key,
            "baseline_suite_status": baseline_suite.status,
            "candidate_suite_status": candidate_suite.status,
        },
    )


class _SuitePairMetrics(BaseModel):
    final_answer_count: int = Field(ge=0)
    penalty_option_count: int = Field(ge=0)
    changed_final_answer_count: int = Field(ge=0)
    baseline_final_answer_hit_count: int = Field(ge=0)
    candidate_final_answer_hit_count: int = Field(ge=0)
    final_answer_hit_delta_count: int
    final_answer_hit_rate_delta: float | None = None
    roi_delta: float | None = None
    profit_loss_delta: float
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    mean_calibration_error_delta: float | None = None
    harm_count_vs_baseline: int = Field(ge=0)
    final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    improvement_count_vs_baseline: int = Field(ge=0)


def _suite_pair_metrics(
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
) -> _SuitePairMetrics:
    baseline_by_slice = {
        comparison.slice_id: comparison.candidate
        for comparison in baseline_suite.comparisons
    }
    candidate_by_slice = {
        comparison.slice_id: comparison.candidate
        for comparison in candidate_suite.comparisons
    }
    paired_slice_ids = sorted(set(baseline_by_slice) & set(candidate_by_slice))
    changed_count = 0
    final_hit_harm_count = 0
    profit_loss_harm_count = 0
    improvement_count = 0
    for slice_id in paired_slice_ids:
        baseline_result = baseline_by_slice[slice_id]
        candidate_result = candidate_by_slice[slice_id]
        baseline_final = baseline_result.final_answer
        candidate_final = candidate_result.final_answer
        if _final_answer_signature(baseline_final) != _final_answer_signature(
            candidate_final
        ):
            changed_count += 1
        if candidate_result.final_hit_count < baseline_result.final_hit_count:
            final_hit_harm_count += 1
        if candidate_result.profit_loss < baseline_result.profit_loss:
            profit_loss_harm_count += 1
        if candidate_result.final_hit_count > baseline_result.final_hit_count:
            improvement_count += 1
    baseline_hit_count = _summary_int(
        baseline_suite.summary_json,
        "candidate_final_hit_count",
    )
    candidate_hit_count = _summary_int(
        candidate_suite.summary_json,
        "candidate_final_hit_count",
    )
    return _SuitePairMetrics(
        final_answer_count=_summary_int(
            candidate_suite.summary_json,
            "candidate_final_hit_sample_size",
        ),
        penalty_option_count=_summary_int(
            candidate_suite.summary_json,
            "candidate_final_answer_segment_penalty_option_count",
        ),
        changed_final_answer_count=changed_count,
        baseline_final_answer_hit_count=baseline_hit_count,
        candidate_final_answer_hit_count=candidate_hit_count,
        final_answer_hit_delta_count=candidate_hit_count - baseline_hit_count,
        final_answer_hit_rate_delta=_optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_final_hit_rate"),
            _summary_number(baseline_suite.summary_json, "candidate_final_hit_rate"),
        ),
        roi_delta=_optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_roi"),
            _summary_number(baseline_suite.summary_json, "candidate_roi"),
        ),
        profit_loss_delta=(
            (
                _summary_number(candidate_suite.summary_json, "candidate_profit_loss")
                or 0.0
            )
            - (
                _summary_number(baseline_suite.summary_json, "candidate_profit_loss")
                or 0.0
            )
        ),
        brier_score_delta=_optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_brier_score"),
            _summary_number(baseline_suite.summary_json, "candidate_brier_score"),
        ),
        log_loss_delta=_optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_log_loss"),
            _summary_number(baseline_suite.summary_json, "candidate_log_loss"),
        ),
        mean_calibration_error_delta=_optional_delta(
            _summary_number(
                candidate_suite.summary_json,
                "candidate_mean_calibration_error",
            ),
            _summary_number(
                baseline_suite.summary_json,
                "candidate_mean_calibration_error",
            ),
        ),
        harm_count_vs_baseline=final_hit_harm_count,
        final_hit_harm_count_vs_baseline=final_hit_harm_count,
        profit_loss_harm_count_vs_baseline=profit_loss_harm_count,
        improvement_count_vs_baseline=improvement_count,
    )


def _fold_failure_reasons(
    metrics: _SuitePairMetrics,
    *,
    options: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions,
) -> list[str]:
    failures: list[str] = []
    if metrics.final_answer_hit_delta_count < options.min_fold_final_hit_count_delta:
        failures.append("final_answer_hit_count_delta_below_threshold")
    if metrics.final_answer_hit_rate_delta is None or (
        metrics.final_answer_hit_rate_delta < options.min_fold_final_hit_rate_delta
    ):
        failures.append("final_answer_hit_rate_delta_below_threshold")
    if metrics.roi_delta is None or metrics.roi_delta < options.min_fold_roi_delta:
        failures.append("roi_delta_below_threshold")
    if metrics.profit_loss_delta < options.min_fold_profit_loss_delta:
        failures.append("profit_loss_delta_below_threshold")
    if metrics.brier_score_delta is None or (
        metrics.brier_score_delta > options.max_fold_brier_score_delta
    ):
        failures.append("brier_score_delta_above_threshold")
    if metrics.log_loss_delta is None or (
        metrics.log_loss_delta > options.max_fold_log_loss_delta
    ):
        failures.append("log_loss_delta_above_threshold")
    if metrics.mean_calibration_error_delta is None or (
        metrics.mean_calibration_error_delta
        > options.max_fold_mean_calibration_error_delta
    ):
        failures.append("mean_calibration_error_delta_above_threshold")
    if metrics.harm_count_vs_baseline > options.max_fold_harm_count_vs_baseline:
        failures.append("harm_count_vs_baseline_above_threshold")
    if (
        metrics.final_hit_harm_count_vs_baseline
        > options.max_fold_final_hit_harm_count_vs_baseline
    ):
        failures.append("final_hit_harm_count_vs_baseline_above_threshold")
    if (
        metrics.profit_loss_harm_count_vs_baseline
        > options.max_fold_profit_loss_harm_count_vs_baseline
    ):
        failures.append("profit_loss_harm_count_vs_baseline_above_threshold")
    return failures


def _checks(
    grid_report: HistoricalFinalAnswerSegmentPenaltyGridReport,
    candidate: HistoricalFinalAnswerSegmentPenaltyCandidate,
    *,
    overall_fold: HistoricalFinalAnswerSegmentPenaltyFold,
    folds: Sequence[HistoricalFinalAnswerSegmentPenaltyFold],
    options: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions,
) -> list[HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck]:
    failed_fold_count = sum(1 for fold in folds if fold.status == "failed")
    return [
        _boolean_check(
            name="grid_report_generated",
            actual=grid_report.status == "generated",
            expected=True,
            detail="source segment penalty grid report must be generated",
        ),
        _boolean_check(
            name="grid_candidate_accepted",
            actual=candidate.status == "accepted",
            expected=True,
            detail="source grid candidate should be accepted",
            enabled=options.require_grid_candidate_accepted,
        ),
        _minimum_check(
            name="overall_final_answer_count",
            actual=overall_fold.final_answer_count,
            threshold=options.min_overall_final_answer_count,
            detail="overall admission should cover enough final answers",
        ),
        _minimum_check(
            name="overall_penalty_option_count",
            actual=overall_fold.penalty_option_count,
            threshold=options.min_overall_penalty_option_count,
            detail="overall admission should exercise the segment penalty",
        ),
        _minimum_check(
            name="overall_final_hit_count_delta",
            actual=overall_fold.final_answer_hit_delta_count,
            threshold=options.min_overall_final_hit_count_delta,
            detail="overall final-answer hit count should not regress",
        ),
        _minimum_check(
            name="overall_final_hit_rate_delta",
            actual=overall_fold.final_answer_hit_rate_delta,
            threshold=options.min_overall_final_hit_rate_delta,
            detail="overall final-answer hit rate should not regress",
        ),
        _minimum_check(
            name="overall_roi_delta",
            actual=overall_fold.roi_delta,
            threshold=options.min_overall_roi_delta,
            detail="overall ROI should not regress",
        ),
        _minimum_check(
            name="overall_profit_loss_delta",
            actual=overall_fold.profit_loss_delta,
            threshold=options.min_overall_profit_loss_delta,
            detail="overall profit/loss should not regress",
        ),
        _maximum_check(
            name="overall_brier_score_delta",
            actual=overall_fold.brier_score_delta,
            threshold=options.max_overall_brier_score_delta,
            detail="overall Brier score should not regress",
        ),
        _maximum_check(
            name="overall_log_loss_delta",
            actual=overall_fold.log_loss_delta,
            threshold=options.max_overall_log_loss_delta,
            detail="overall log loss should not regress",
        ),
        _maximum_check(
            name="overall_mean_calibration_error_delta",
            actual=overall_fold.mean_calibration_error_delta,
            threshold=options.max_overall_mean_calibration_error_delta,
            detail="overall calibration error should not regress",
        ),
        _maximum_check(
            name="overall_harm_count_vs_baseline",
            actual=overall_fold.harm_count_vs_baseline,
            threshold=options.max_overall_harm_count_vs_baseline,
            detail="overall admission should not turn correct final answers into misses",
        ),
        _maximum_check(
            name="overall_final_hit_harm_count_vs_baseline",
            actual=overall_fold.final_hit_harm_count_vs_baseline,
            threshold=options.max_overall_final_hit_harm_count_vs_baseline,
            detail="overall admission should not reduce original final-answer hit counts",
        ),
        _maximum_check(
            name="overall_profit_loss_harm_count_vs_baseline",
            actual=overall_fold.profit_loss_harm_count_vs_baseline,
            threshold=options.max_overall_profit_loss_harm_count_vs_baseline,
            detail="overall admission should not reduce original final-answer profit/loss",
        ),
        _boolean_check(
            name="overall_gate_passed",
            actual=overall_fold.status == "passed",
            expected=True,
            detail="overall fold must pass strict admission thresholds",
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
            detail="admission should validate enough active competition folds",
        ),
        _minimum_check(
            name="active_season_fold_count",
            actual=_active_fold_count(folds, "season"),
            threshold=options.min_active_season_fold_count,
            detail="admission should validate enough active season folds",
        ),
        _minimum_check(
            name="active_rolling_fold_count",
            actual=_active_fold_count(folds, "rolling_window"),
            threshold=options.min_active_rolling_fold_count,
            detail="admission should validate enough active rolling-window folds",
        ),
    ]


def _baseline_backtest_options(
    options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestOptions:
    return options.model_copy(
        update={
            "final_answer_segment_penalty": False,
            "final_answer_segment_pass_types": (),
            "final_answer_segment_modes": (),
            "final_answer_segment_competition_ids": (),
            "final_answer_segment_season_ids": (),
            "final_answer_segment_min_competition_season_index": None,
            "final_answer_segment_max_competition_season_index": None,
        }
    )


def _candidate_backtest_options(
    options: HistoricalRecommendationBacktestOptions,
    candidate: HistoricalFinalAnswerSegmentPenaltyCandidate,
) -> HistoricalRecommendationBacktestOptions:
    return options.model_copy(
        update={
            "final_answer_segment_penalty": True,
            "final_answer_segment_penalty_strength": candidate.strength,
            "final_answer_segment_pass_types": candidate.pass_types,
            "final_answer_segment_modes": candidate.modes,
            "final_answer_segment_competition_ids": candidate.competition_ids,
            "final_answer_segment_season_ids": candidate.season_ids,
            "final_answer_segment_min_competition_season_index": (
                candidate.min_competition_season_index
            ),
            "final_answer_segment_max_competition_season_index": (
                candidate.max_competition_season_index
            ),
            "final_answer_segment_min_hit_probability": candidate.min_hit_probability,
            "final_answer_segment_max_hit_probability": candidate.max_hit_probability,
            "final_answer_segment_min_odds_product": candidate.min_odds_product,
            "final_answer_segment_max_odds_product": candidate.max_odds_product,
            "final_answer_segment_min_average_leg_decimal_odds": (
                candidate.min_average_leg_decimal_odds
            ),
            "final_answer_segment_max_average_leg_decimal_odds": (
                candidate.max_average_leg_decimal_odds
            ),
        }
    )


def _groups_by_competition(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> dict[str, list[HistoricalRecommendationSlice]]:
    grouped: dict[str, list[HistoricalRecommendationSlice]] = {}
    for historical_slice in historical_slices:
        grouped.setdefault(historical_slice.metadata.competition_id, []).append(
            historical_slice
        )
    return dict(sorted(grouped.items()))


def _groups_by_season(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> dict[str, list[HistoricalRecommendationSlice]]:
    grouped: dict[str, list[HistoricalRecommendationSlice]] = {}
    for historical_slice in historical_slices:
        grouped.setdefault(_slice_season_id(historical_slice), []).append(
            historical_slice
        )
    return dict(sorted(grouped.items(), key=lambda item: (_season_sort_key(item[0]), item[0])))


def _rolling_window_groups(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    options: HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions,
) -> list[list[HistoricalRecommendationSlice]]:
    ordered_slices = sorted(
        historical_slices,
        key=lambda historical_slice: (
            _season_sort_key(_slice_season_id(historical_slice)),
            historical_slice.metadata.competition_id,
            historical_slice.metadata.slice_id,
        ),
    )
    windows: list[list[HistoricalRecommendationSlice]] = []
    for start in range(0, len(ordered_slices), options.rolling_window_step):
        window = ordered_slices[start : start + options.rolling_window_slice_count]
        if len(window) < options.rolling_window_slice_count:
            break
        windows.append(list(window))
    return windows


def _slice_season_id(historical_slice: HistoricalRecommendationSlice) -> str:
    if historical_slice.metadata.season:
        return historical_slice.metadata.season
    match = search(r"_(\d{4}(?:_\d{4})?)_", historical_slice.metadata.slice_id)
    return match.group(1) if match else "unknown"


def _season_sort_key(season_id: str) -> tuple[int, str]:
    match = search(r"\d{4}", season_id)
    return (int(match.group(0)) if match else 0, season_id)


def _active_fold_count(
    folds: Sequence[HistoricalFinalAnswerSegmentPenaltyFold],
    fold_type: str,
) -> int:
    return sum(
        1 for fold in folds if fold.fold_type == fold_type and fold.status != "skipped"
    )


def _check_failed(
    checks: Sequence[HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck],
    name: str,
) -> bool:
    return any(check.name == name and check.status == "failed" for check in checks)


def _final_answer_signature(
    final_answer: HistoricalRecommendationScenarioResult | None,
) -> tuple[object, ...] | None:
    if final_answer is None:
        return None
    selected_outcomes = tuple(
        (fixture_id, tuple(outcomes))
        for fixture_id, outcomes in sorted(final_answer.selected_outcomes.items())
    )
    return (
        final_answer.scenario.scenario_key,
        tuple(final_answer.selected_fixture_ids),
        selected_outcomes,
    )


def _boolean_check(
    *,
    name: str,
    actual: bool,
    expected: bool,
    detail: str,
    enabled: bool = True,
) -> HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck:
    if not enabled:
        return HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck(
            name=name,
            status="passed",
            actual=None,
            threshold="not_required",
            detail="check disabled by options",
        )
    return HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck(
        name=name,
        status="passed" if actual is expected else "failed",
        actual=actual,
        threshold=expected,
        detail=detail,
    )


def _minimum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck:
    if actual is None:
        return HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck(
        name=name,
        status="passed" if actual >= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _maximum_check(
    *,
    name: str,
    actual: float | int | None,
    threshold: float | int,
    detail: str,
) -> HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck:
    if actual is None:
        return HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck(
            name=name,
            status="failed",
            actual=None,
            threshold=threshold,
            detail=detail,
        )
    return HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck(
        name=name,
        status="passed" if actual <= threshold else "failed",
        actual=actual,
        threshold=threshold,
        detail=detail,
    )


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Run rolling/holdout admission for final-answer segment penalty."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--grid-report", type=Path, required=True)
    parser.add_argument("--candidate-key")
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--pass-types", default=",".join(DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES))
    parser.add_argument("--modes", default=",".join(DEFAULT_HISTORICAL_BACKTEST_MODES))
    parser.add_argument(
        "--strategy",
        choices=[
            "accuracy_first",
            "value_first",
            "upset_protection",
            "budget_constrained",
        ],
        default="accuracy_first",
    )
    parser.add_argument("--unit-stake", type=float, default=2.0)
    parser.add_argument("--max-budget", type=float, default=20.0)
    parser.add_argument("--min-probability", type=float, default=0.15)
    parser.add_argument("--min-data-quality-score", type=float, default=50.0)
    parser.add_argument("--max-outcomes-per-fixture", type=int, default=2)
    parser.add_argument("--upset-threshold", type=float, default=0.35)
    parser.add_argument("--candidate-fixture-limit", type=int)
    parser.add_argument("--max-candidates-per-fixture", type=int, default=3)
    parser.add_argument("--scenario-candidate-fixture-buffer", type=int)
    parser.add_argument("--derive-market-context-signals", action="store_true")
    parser.add_argument(
        "--baseline-optimizer-profile",
        choices=["heuristic", "solver"],
        default="heuristic",
    )
    parser.add_argument(
        "--candidate-optimizer-profile",
        choices=["heuristic", "solver"],
        default="solver",
    )
    parser.add_argument("--allow-unaccepted-grid-candidate", action="store_true")
    parser.add_argument("--min-overall-final-answer-count", type=int, default=30)
    parser.add_argument("--min-overall-penalty-option-count", type=int, default=1)
    parser.add_argument("--min-overall-final-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-overall-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-overall-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-overall-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-overall-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-overall-log-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--max-overall-mean-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument("--max-overall-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument(
        "--max-overall-final-hit-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-overall-profit-loss-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument("--min-fold-final-answer-count", type=int, default=1)
    parser.add_argument("--min-fold-penalty-option-count", type=int, default=1)
    parser.add_argument("--min-fold-final-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-fold-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-fold-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-fold-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-fold-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-fold-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-fold-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--max-fold-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument(
        "--max-fold-final-hit-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--max-fold-profit-loss-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument("--min-active-competition-fold-count", type=int, default=2)
    parser.add_argument("--min-active-season-fold-count", type=int, default=1)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=1)
    parser.add_argument("--rolling-window-slice-count", type=int, default=12)
    parser.add_argument("--rolling-window-step", type=int, default=6)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--max-report-folds", type=int, default=120)
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions:
    return HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions(
        candidate_key=args.candidate_key,
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=tuple(_csv(args.pass_types)),
            modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
            strategy=cast(RecommendationStrategy, args.strategy),
            unit_stake=args.unit_stake,
            max_budget=args.max_budget,
            min_probability=args.min_probability,
            min_data_quality_score=args.min_data_quality_score,
            max_outcomes_per_fixture=args.max_outcomes_per_fixture,
            upset_threshold=args.upset_threshold,
            candidate_fixture_limit=args.candidate_fixture_limit,
            max_candidates_per_fixture=args.max_candidates_per_fixture,
            scenario_candidate_fixture_buffer=args.scenario_candidate_fixture_buffer,
            derive_market_context_signals=args.derive_market_context_signals,
        ),
        baseline_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.baseline_optimizer_profile,
        ),
        candidate_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.candidate_optimizer_profile,
        ),
        require_grid_candidate_accepted=not args.allow_unaccepted_grid_candidate,
        min_overall_final_answer_count=args.min_overall_final_answer_count,
        min_overall_penalty_option_count=args.min_overall_penalty_option_count,
        min_overall_final_hit_count_delta=args.min_overall_final_hit_count_delta,
        min_overall_final_hit_rate_delta=args.min_overall_final_hit_rate_delta,
        min_overall_roi_delta=args.min_overall_roi_delta,
        min_overall_profit_loss_delta=args.min_overall_profit_loss_delta,
        max_overall_brier_score_delta=args.max_overall_brier_score_delta,
        max_overall_log_loss_delta=args.max_overall_log_loss_delta,
        max_overall_mean_calibration_error_delta=(
            args.max_overall_mean_calibration_error_delta
        ),
        max_overall_harm_count_vs_baseline=args.max_overall_harm_count_vs_baseline,
        max_overall_final_hit_harm_count_vs_baseline=(
            args.max_overall_final_hit_harm_count_vs_baseline
        ),
        max_overall_profit_loss_harm_count_vs_baseline=(
            args.max_overall_profit_loss_harm_count_vs_baseline
        ),
        min_fold_final_answer_count=args.min_fold_final_answer_count,
        min_fold_penalty_option_count=args.min_fold_penalty_option_count,
        min_fold_final_hit_count_delta=args.min_fold_final_hit_count_delta,
        min_fold_final_hit_rate_delta=args.min_fold_final_hit_rate_delta,
        min_fold_roi_delta=args.min_fold_roi_delta,
        min_fold_profit_loss_delta=args.min_fold_profit_loss_delta,
        max_fold_brier_score_delta=args.max_fold_brier_score_delta,
        max_fold_log_loss_delta=args.max_fold_log_loss_delta,
        max_fold_mean_calibration_error_delta=args.max_fold_mean_calibration_error_delta,
        max_fold_harm_count_vs_baseline=args.max_fold_harm_count_vs_baseline,
        max_fold_final_hit_harm_count_vs_baseline=(
            args.max_fold_final_hit_harm_count_vs_baseline
        ),
        max_fold_profit_loss_harm_count_vs_baseline=(
            args.max_fold_profit_loss_harm_count_vs_baseline
        ),
        min_active_competition_fold_count=args.min_active_competition_fold_count,
        min_active_season_fold_count=args.min_active_season_fold_count,
        min_active_rolling_fold_count=args.min_active_rolling_fold_count,
        rolling_window_slice_count=args.rolling_window_slice_count,
        rolling_window_step=args.rolling_window_step,
        max_failed_fold_count=args.max_failed_fold_count,
        max_report_folds=args.max_report_folds,
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path) for slice_path in args.slice_paths
    ]
    if args.suite_manifest is None:
        if not explicit_slices:
            raise ValueError("Provide at least one slice path or --suite-manifest")
        return _LoadedHistoricalSlices(
            slices=explicit_slices,
            resolved_slice_paths=list(args.slice_paths),
        )
    bundle = load_historical_recommendation_suite_manifest_bundle(args.suite_manifest)
    return _LoadedHistoricalSlices(
        slices=[*bundle.slices, *explicit_slices],
        resolved_slice_paths=[*bundle.resolved_slice_paths, *args.slice_paths],
        manifest_result=bundle,
        warnings=bundle.warnings,
    )


def _manifest_summary(
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult,
) -> dict[str, object]:
    return {
        "manifest_path": str(manifest_result.manifest_path),
        "suite_id": manifest_result.manifest.suite_id,
        "name": manifest_result.manifest.name,
        "slice_count": len(manifest_result.slices),
        "resolved_slice_paths": [
            str(slice_path) for slice_path in manifest_result.resolved_slice_paths
        ],
        "warnings": manifest_result.warnings,
    }


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _summary_number(summary: Mapping[str, object], key: str) -> float | None:
    value = summary.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _summary_int(summary: Mapping[str, object], key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    return 0


def _optional_delta(candidate_value: float | None, baseline_value: float | None) -> float | None:
    if candidate_value is None or baseline_value is None:
        return None
    return candidate_value - baseline_value


def _report_key(
    summary: Mapping[str, object],
    checks: Sequence[HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck],
    folds: Sequence[HistoricalFinalAnswerSegmentPenaltyFold],
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
                "final_answer_hit_delta_count": fold.final_answer_hit_delta_count,
                "roi_delta": fold.roi_delta,
                "profit_loss_delta": fold.profit_loss_delta,
                "failure_reasons": fold.failure_reasons,
            }
            for fold in folds
        ],
    }
    digest = sha256(
        dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_segment_penalty_rolling_admission:{digest}"


if __name__ == "__main__":
    main()
