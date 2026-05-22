from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_rolling_admission import (
    HistoricalMarketMovementRiskFilterAdmissionCheck,
    HistoricalMarketMovementRiskFilterFold,
    HistoricalMarketMovementRiskFilterFoldType,
    HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
    _active_fold_count,
    _candidate_final_delta,
    _candidate_single_delta,
    _checks,
    _fold_failure_reasons,
    _groups_by_competition,
    _rolling_window_groups,
    _season_cutoff_groups,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_scope_refinement import (
    HistoricalMarketMovementRiskFilterScopeRefinementReport,
    load_historical_market_movement_risk_filter_scope_refinement_report,
)
from nutmeg.recommendations.historical_market_movement_segment_gate import (
    HistoricalMarketMovementSegmentCandidate,
    HistoricalMarketMovementSegmentGateOptions,
    HistoricalMarketMovementSegmentGateReport,
    build_historical_market_movement_segment_gate_report,
)
from nutmeg.recommendations.historical_prematch_feature_sample_readiness import (
    HistoricalPrematchFeatureSampleReadinessReport,
    load_historical_prematch_feature_sample_readiness_report,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalMarketMovementRiskFilterGuardedAdmissionStatus = Literal[
    "accepted",
    "shadow_only",
    "rejected",
]

DEFAULT_MARKET_MOVEMENT_RISK_FILTER_GUARDED_ADMISSION_ID = (
    "market-movement-risk-filter-guarded-rolling-admission-shadow-v3.2"
)


class HistoricalMarketMovementRiskFilterGuardedAdmissionOptions(BaseModel):
    admission_id: str = DEFAULT_MARKET_MOVEMENT_RISK_FILTER_GUARDED_ADMISSION_ID
    sample_readiness_report_path: Path | None = None
    require_sample_readiness: bool = False
    require_sample_ready_allowed: bool = True
    rolling_options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions = Field(
        default_factory=HistoricalMarketMovementRiskFilterRollingAdmissionOptions
    )
    use_scope_refinement_gate_options: bool = True
    apply_failed_scope_guards: bool = True
    apply_block_actions_globally: bool = True
    skip_fully_guarded_non_overall_folds: bool = True
    max_report_folds: int = Field(default=120, ge=1, le=500)


class HistoricalMarketMovementRiskFilterGuardedFold(BaseModel):
    fold: HistoricalMarketMovementRiskFilterFold
    original_segment_gate_report_key: str | None = None
    guarded_segment_gate_report_key: str | None = None
    original_candidate_count: int = Field(default=0, ge=0)
    guarded_candidate_count: int = Field(default=0, ge=0)
    removed_candidate_count: int = Field(default=0, ge=0)
    removed_segment_group_keys: list[str] = Field(default_factory=list)
    removed_candidate_ids: list[str] = Field(default_factory=list)
    guard_reasons_by_segment_group_key: dict[str, list[str]] = Field(
        default_factory=dict
    )
    guarded_skip: bool = False
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketMovementRiskFilterGuardedAdmissionReport(BaseModel):
    report_key: str
    status: HistoricalMarketMovementRiskFilterGuardedAdmissionStatus
    guarded_risk_filter_allowed: bool
    shadow_allowed: bool
    production_recommendation_changed: bool = False
    scope_refinement_report_key: str
    scope_refinement_status: str
    sample_readiness_report_path: Path | None = None
    sample_readiness_key: str | None = None
    sample_readiness_status: str | None = None
    sample_ready_allowed: bool | None = None
    sample_readiness_shadow_allowed: bool | None = None
    overall_fold: HistoricalMarketMovementRiskFilterFold
    guarded_overall_fold: HistoricalMarketMovementRiskFilterGuardedFold
    fold_count: int = Field(ge=0)
    active_fold_count: int = Field(ge=0)
    guarded_skipped_fold_count: int = Field(ge=0)
    failed_fold_count: int = Field(ge=0)
    active_competition_fold_count: int = Field(ge=0)
    active_season_cutoff_fold_count: int = Field(ge=0)
    active_rolling_fold_count: int = Field(ge=0)
    removed_candidate_count: int = Field(ge=0)
    global_blocked_segment_group_keys: list[str] = Field(default_factory=list)
    exact_guard_scope_count: int = Field(ge=0)
    checks: list[HistoricalMarketMovementRiskFilterAdmissionCheck] = Field(
        default_factory=list
    )
    folds: list[HistoricalMarketMovementRiskFilterGuardedFold] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class _GuardResolution:
    global_blocked_segment_group_keys: frozenset[str]
    exact_guard_segment_group_keys_by_fold_id: Mapping[str, frozenset[str]]
    exact_guard_scope_count: int


def build_historical_market_movement_risk_filter_guarded_admission_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    scope_refinement_report: HistoricalMarketMovementRiskFilterScopeRefinementReport,
    options: HistoricalMarketMovementRiskFilterGuardedAdmissionOptions | None = None,
    sample_readiness_report: HistoricalPrematchFeatureSampleReadinessReport
    | None = None,
) -> HistoricalMarketMovementRiskFilterGuardedAdmissionReport:
    resolved_options = options or HistoricalMarketMovementRiskFilterGuardedAdmissionOptions()
    rolling_options = _rolling_options(
        resolved_options,
        scope_refinement_report=scope_refinement_report,
    )
    guards = _guard_resolution(scope_refinement_report, options=resolved_options)
    guarded_overall = _guarded_gate_fold(
        "overall:all",
        "overall",
        historical_slices,
        rolling_options=rolling_options,
        guards=guards,
        is_overall=True,
        skip_fully_guarded_non_overall_folds=(
            resolved_options.skip_fully_guarded_non_overall_folds
        ),
    )
    guarded_folds = _guarded_fold_reports(
        historical_slices,
        rolling_options=rolling_options,
        guards=guards,
        skip_fully_guarded_non_overall_folds=(
            resolved_options.skip_fully_guarded_non_overall_folds
        ),
    )
    folds = [guarded_fold.fold for guarded_fold in guarded_folds]
    checks = _checks(
        guarded_overall.fold,
        folds=folds,
        sample_readiness_report=sample_readiness_report,
        options=rolling_options,
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
        status: HistoricalMarketMovementRiskFilterGuardedAdmissionStatus = "rejected"
    elif failed_checks:
        status = "shadow_only"
    else:
        status = "accepted"
    guarded_risk_filter_allowed = status == "accepted"
    shadow_allowed = status in {"accepted", "shadow_only"}
    warnings = [
        *guarded_overall.fold.warning_codes,
        *[
            f"market_movement_risk_filter_guarded_admission:failed_check:{check.name}"
            for check in failed_checks
        ],
        *[
            f"market_movement_risk_filter_guarded_admission:failed_fold:{fold.fold_id}"
            for fold in failed_folds
        ],
    ]
    guarded_skipped_fold_count = sum(
        1 for guarded_fold in guarded_folds if guarded_fold.guarded_skip
    )
    removed_candidate_count = guarded_overall.removed_candidate_count + sum(
        guarded_fold.removed_candidate_count for guarded_fold in guarded_folds
    )
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_risk_filter_guarded_admission_v3_2"
        ),
        "admission_id": resolved_options.admission_id,
        "status": status,
        "guarded_risk_filter_allowed": guarded_risk_filter_allowed,
        "shadow_allowed": shadow_allowed,
        "production_recommendation_changed": False,
        "scope_refinement_report_key": scope_refinement_report.report_key,
        "scope_refinement_status": scope_refinement_report.status,
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
        "fold_count": len(guarded_folds),
        "active_fold_count": len(active_folds),
        "guarded_skipped_fold_count": guarded_skipped_fold_count,
        "failed_fold_count": len(failed_folds),
        "active_competition_fold_count": _active_fold_count(folds, "competition"),
        "active_season_cutoff_fold_count": _active_fold_count(folds, "season_cutoff"),
        "active_rolling_fold_count": _active_fold_count(folds, "rolling_window"),
        "removed_candidate_count": removed_candidate_count,
        "global_blocked_segment_group_keys": sorted(
            guards.global_blocked_segment_group_keys
        ),
        "exact_guard_scope_count": guards.exact_guard_scope_count,
        "options": resolved_options.model_dump(mode="json"),
        "rolling_options": rolling_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, checks, guarded_overall, guarded_folds)
    return HistoricalMarketMovementRiskFilterGuardedAdmissionReport(
        report_key=report_key,
        status=status,
        guarded_risk_filter_allowed=guarded_risk_filter_allowed,
        shadow_allowed=shadow_allowed,
        production_recommendation_changed=False,
        scope_refinement_report_key=scope_refinement_report.report_key,
        scope_refinement_status=scope_refinement_report.status,
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
        overall_fold=guarded_overall.fold,
        guarded_overall_fold=guarded_overall,
        fold_count=len(guarded_folds),
        active_fold_count=len(active_folds),
        guarded_skipped_fold_count=guarded_skipped_fold_count,
        failed_fold_count=len(failed_folds),
        active_competition_fold_count=_active_fold_count(folds, "competition"),
        active_season_cutoff_fold_count=_active_fold_count(folds, "season_cutoff"),
        active_rolling_fold_count=_active_fold_count(folds, "rolling_window"),
        removed_candidate_count=removed_candidate_count,
        global_blocked_segment_group_keys=sorted(
            guards.global_blocked_segment_group_keys
        ),
        exact_guard_scope_count=guards.exact_guard_scope_count,
        checks=checks,
        folds=guarded_folds[: resolved_options.max_report_folds],
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_market_movement_risk_filter_guarded_admission_report(
    path: Path | str,
) -> HistoricalMarketMovementRiskFilterGuardedAdmissionReport:
    return HistoricalMarketMovementRiskFilterGuardedAdmissionReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    scope_refinement_report = (
        load_historical_market_movement_risk_filter_scope_refinement_report(
            args.scope_refinement_report_path
        )
    )
    sample_readiness_report = _load_sample_readiness_report(
        args.sample_readiness_report_path
    )
    report = build_historical_market_movement_risk_filter_guarded_admission_report(
        loaded_slices.slices,
        scope_refinement_report=scope_refinement_report,
        options=_options_from_args(args),
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
    if not report.guarded_risk_filter_allowed and not args.no_fail_process:
        raise SystemExit(1)


def _guarded_fold_reports(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    rolling_options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
    guards: _GuardResolution,
    skip_fully_guarded_non_overall_folds: bool,
) -> list[HistoricalMarketMovementRiskFilterGuardedFold]:
    guarded_folds: list[HistoricalMarketMovementRiskFilterGuardedFold] = []
    for competition_id, slices in _groups_by_competition(historical_slices).items():
        guarded_folds.append(
            _guarded_gate_fold(
                f"competition:{competition_id}",
                "competition",
                slices,
                rolling_options=rolling_options,
                guards=guards,
                skip_fully_guarded_non_overall_folds=(
                    skip_fully_guarded_non_overall_folds
                ),
            )
        )
    for season_id, slices in _season_cutoff_groups(
        historical_slices,
        rolling_options,
    ).items():
        guarded_folds.append(
            _guarded_gate_fold(
                f"season_cutoff:{season_id}",
                "season_cutoff",
                slices,
                rolling_options=rolling_options,
                guards=guards,
                skip_fully_guarded_non_overall_folds=(
                    skip_fully_guarded_non_overall_folds
                ),
            )
        )
    for index, slices in enumerate(
        _rolling_window_groups(historical_slices, rolling_options)
    ):
        season_ids = sorted(
            {historical_slice.metadata.season or "unknown" for historical_slice in slices}
        )
        guarded_folds.append(
            _guarded_gate_fold(
                f"rolling_window:{index + 1}:{season_ids[0]}..{season_ids[-1]}",
                "rolling_window",
                slices,
                rolling_options=rolling_options,
                guards=guards,
                skip_fully_guarded_non_overall_folds=(
                    skip_fully_guarded_non_overall_folds
                ),
            )
        )
    return guarded_folds


def _guarded_gate_fold(
    fold_id: str,
    fold_type: HistoricalMarketMovementRiskFilterFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    rolling_options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
    guards: _GuardResolution,
    skip_fully_guarded_non_overall_folds: bool,
    is_overall: bool = False,
) -> HistoricalMarketMovementRiskFilterGuardedFold:
    base_report = build_historical_market_movement_segment_gate_report(
        historical_slices,
        options=rolling_options.segment_gate_options,
    )
    guarded_report, guard_summary = _guarded_segment_gate_report(
        fold_id,
        base_report,
        guards=guards,
    )
    if (
        not is_overall
        and skip_fully_guarded_non_overall_folds
        and base_report.candidate_count > 0
        and guarded_report.candidate_count == 0
    ):
        return _guarded_skipped_fold(
            fold_id,
            fold_type,
            historical_slices,
            base_report=base_report,
            guarded_report=guarded_report,
            guard_summary=guard_summary,
        )
    fold = _fold_from_segment_gate_report(
        fold_id,
        fold_type,
        historical_slices,
        gate_report=guarded_report,
        rolling_options=rolling_options,
        is_overall=is_overall,
    )
    return HistoricalMarketMovementRiskFilterGuardedFold(
        fold=fold,
        original_segment_gate_report_key=base_report.report_key,
        guarded_segment_gate_report_key=guarded_report.report_key,
        original_candidate_count=base_report.candidate_count,
        guarded_candidate_count=guarded_report.candidate_count,
        removed_candidate_count=guard_summary.removed_candidate_count,
        removed_segment_group_keys=guard_summary.removed_segment_group_keys,
        removed_candidate_ids=guard_summary.removed_candidate_ids,
        guard_reasons_by_segment_group_key=guard_summary.guard_reasons_by_segment_group_key,
        guarded_skip=False,
        summary_json={
            "guard_summary": guard_summary.model_dump(mode="json"),
            "guarded_segment_gate_summary": guarded_report.summary_json,
        },
    )


class _GuardedSegmentGateSummary(BaseModel):
    removed_candidate_count: int = Field(ge=0)
    removed_segment_group_keys: list[str] = Field(default_factory=list)
    removed_candidate_ids: list[str] = Field(default_factory=list)
    guard_reasons_by_segment_group_key: dict[str, list[str]] = Field(
        default_factory=dict
    )


def _guarded_segment_gate_report(
    fold_id: str,
    report: HistoricalMarketMovementSegmentGateReport,
    *,
    guards: _GuardResolution,
) -> tuple[HistoricalMarketMovementSegmentGateReport, _GuardedSegmentGateSummary]:
    kept: list[HistoricalMarketMovementSegmentCandidate] = []
    removed: list[HistoricalMarketMovementSegmentCandidate] = []
    reasons_by_segment_group_key: dict[str, list[str]] = {}
    for candidate in report.candidates:
        reasons = _candidate_guard_reasons(fold_id, candidate, guards=guards)
        if reasons:
            removed.append(candidate)
            reasons_by_segment_group_key[candidate.segment_group_key] = reasons
            continue
        kept.append(candidate)
    ranked_kept = [
        candidate.model_copy(update={"rank": rank})
        for rank, candidate in enumerate(kept, start=1)
    ]
    best_candidate = ranked_kept[0] if ranked_kept else None
    accepted_count = sum(1 for candidate in ranked_kept if candidate.decision == "accepted")
    guarded_summary = _GuardedSegmentGateSummary(
        removed_candidate_count=len(removed),
        removed_segment_group_keys=sorted(
            {candidate.segment_group_key for candidate in removed}
        ),
        removed_candidate_ids=[candidate.candidate_id for candidate in removed],
        guard_reasons_by_segment_group_key=reasons_by_segment_group_key,
    )
    guarded_report_key = _guarded_segment_gate_report_key(
        report,
        fold_id=fold_id,
        guard_summary=guarded_summary,
    )
    return (
        report.model_copy(
            update={
                "report_key": guarded_report_key,
                "candidate_count": len(ranked_kept),
                "accepted_count": accepted_count,
                "rejected_count": len(ranked_kept) - accepted_count,
                "best_candidate": best_candidate,
                "candidates": ranked_kept,
                "warnings": [
                    *report.warnings,
                    *(
                        [
                            "market_movement_risk_filter_guarded_admission:"
                            "all_candidates_guarded"
                        ]
                        if report.candidate_count > 0 and not ranked_kept
                        else []
                    ),
                ],
                "summary_json": {
                    **report.summary_json,
                    "guarded_report_key": guarded_report_key,
                    "source_segment_gate_report_key": report.report_key,
                    "guarded_candidate_count": len(ranked_kept),
                    "guarded_removed_candidate_count": len(removed),
                    "guarded_removed_segment_group_keys": (
                        guarded_summary.removed_segment_group_keys
                    ),
                    "guard_reasons_by_segment_group_key": (
                        guarded_summary.guard_reasons_by_segment_group_key
                    ),
                    "shadow_guard_only": True,
                },
            }
        ),
        guarded_summary,
    )


def _candidate_guard_reasons(
    fold_id: str,
    candidate: HistoricalMarketMovementSegmentCandidate,
    *,
    guards: _GuardResolution,
) -> list[str]:
    reasons: list[str] = []
    if candidate.segment_group_key in guards.global_blocked_segment_group_keys:
        reasons.append("global_blocked_segment_group_key")
    exact_keys = guards.exact_guard_segment_group_keys_by_fold_id.get(fold_id, frozenset())
    if candidate.segment_group_key in exact_keys:
        reasons.append("failed_fold_guarded_segment_group_key")
    return reasons


def _guarded_skipped_fold(
    fold_id: str,
    fold_type: HistoricalMarketMovementRiskFilterFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    base_report: HistoricalMarketMovementSegmentGateReport,
    guarded_report: HistoricalMarketMovementSegmentGateReport,
    guard_summary: _GuardedSegmentGateSummary,
) -> HistoricalMarketMovementRiskFilterGuardedFold:
    fold = HistoricalMarketMovementRiskFilterFold(
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
            {
                historical_slice.metadata.season or "unknown"
                for historical_slice in historical_slices
            }
        ),
        segment_gate_report_key=guarded_report.report_key,
        passed_segment_gate=False,
        candidate_count=0,
        accepted_count=0,
        adjusted_fixture_count=0,
        adjusted_prediction_count=0,
        failure_reasons=["all_candidates_removed_by_scope_guard"],
        warning_codes=[
            "market_movement_risk_filter_guarded_admission:skipped:"
            "all_candidates_removed_by_scope_guard"
        ],
        summary_json={
            "source_segment_gate_report_key": base_report.report_key,
            "guarded_segment_gate_report_key": guarded_report.report_key,
            "guard_summary": guard_summary.model_dump(mode="json"),
            "guarded_skip": True,
        },
    )
    return HistoricalMarketMovementRiskFilterGuardedFold(
        fold=fold,
        original_segment_gate_report_key=base_report.report_key,
        guarded_segment_gate_report_key=guarded_report.report_key,
        original_candidate_count=base_report.candidate_count,
        guarded_candidate_count=0,
        removed_candidate_count=guard_summary.removed_candidate_count,
        removed_segment_group_keys=guard_summary.removed_segment_group_keys,
        removed_candidate_ids=guard_summary.removed_candidate_ids,
        guard_reasons_by_segment_group_key=guard_summary.guard_reasons_by_segment_group_key,
        guarded_skip=True,
        summary_json=fold.summary_json,
    )


def _fold_from_segment_gate_report(
    fold_id: str,
    fold_type: HistoricalMarketMovementRiskFilterFoldType,
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    gate_report: HistoricalMarketMovementSegmentGateReport,
    rolling_options: HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
    is_overall: bool,
) -> HistoricalMarketMovementRiskFilterFold:
    best = gate_report.best_candidate
    failure_reasons = _fold_failure_reasons(
        gate_report,
        options=rolling_options,
        is_overall=is_overall,
    )
    return HistoricalMarketMovementRiskFilterFold(
        fold_id=fold_id,
        fold_type=fold_type,
        status="failed" if failure_reasons else "passed",
        source_slice_ids=[
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        source_competition_ids=sorted(
            {historical_slice.metadata.competition_id for historical_slice in historical_slices}
        ),
        source_season_ids=sorted(
            {
                historical_slice.metadata.season or "unknown"
                for historical_slice in historical_slices
            }
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
            "guarded_segment_gate_report_key": gate_report.report_key,
            "guarded_segment_gate_summary": gate_report.summary_json,
        },
    )


def _guard_resolution(
    scope_refinement_report: HistoricalMarketMovementRiskFilterScopeRefinementReport,
    *,
    options: HistoricalMarketMovementRiskFilterGuardedAdmissionOptions,
) -> _GuardResolution:
    exact: dict[str, set[str]] = {}
    if options.apply_failed_scope_guards:
        for blocked_scope in scope_refinement_report.blocked_scopes:
            exact.setdefault(blocked_scope.fold_id, set()).add(
                blocked_scope.segment_group_key
            )
    global_blocked: set[str] = set()
    if options.apply_block_actions_globally:
        global_blocked.update(
            scope.segment_group_key
            for scope in scope_refinement_report.scopes
            if scope.recommended_action == "block"
        )
    return _GuardResolution(
        global_blocked_segment_group_keys=frozenset(global_blocked),
        exact_guard_segment_group_keys_by_fold_id={
            fold_id: frozenset(keys) for fold_id, keys in exact.items()
        },
        exact_guard_scope_count=sum(len(keys) for keys in exact.values()),
    )


def _rolling_options(
    options: HistoricalMarketMovementRiskFilterGuardedAdmissionOptions,
    *,
    scope_refinement_report: HistoricalMarketMovementRiskFilterScopeRefinementReport,
) -> HistoricalMarketMovementRiskFilterRollingAdmissionOptions:
    if not options.use_scope_refinement_gate_options:
        return options.rolling_options.model_copy(
            update={
                "sample_readiness_report_path": options.sample_readiness_report_path,
                "require_sample_readiness": options.require_sample_readiness,
                "require_sample_ready_allowed": options.require_sample_ready_allowed,
            }
        )
    scope_options = scope_refinement_report.summary_json.get("options")
    if not isinstance(scope_options, dict):
        return options.rolling_options
    segment_gate_options_json = scope_options.get("segment_gate_options")
    if not isinstance(segment_gate_options_json, dict):
        return options.rolling_options
    segment_gate_options = HistoricalMarketMovementSegmentGateOptions.model_validate(
        segment_gate_options_json
    )
    return options.rolling_options.model_copy(
        update={
            "sample_readiness_report_path": options.sample_readiness_report_path,
            "require_sample_readiness": options.require_sample_readiness,
            "require_sample_ready_allowed": options.require_sample_ready_allowed,
            "segment_gate_options": segment_gate_options,
        }
    )


def _check_failed(
    checks: Sequence[HistoricalMarketMovementRiskFilterAdmissionCheck],
    name: str,
) -> bool:
    return any(check.name == name and check.status == "failed" for check in checks)


def _guarded_segment_gate_report_key(
    report: HistoricalMarketMovementSegmentGateReport,
    *,
    fold_id: str,
    guard_summary: _GuardedSegmentGateSummary,
) -> str:
    payload = {
        "source_report_key": report.report_key,
        "fold_id": fold_id,
        "guard_summary": guard_summary.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_market_movement_guarded_segment_gate:{digest}"


def _report_key(
    summary: dict[str, object],
    checks: Sequence[HistoricalMarketMovementRiskFilterAdmissionCheck],
    guarded_overall: HistoricalMarketMovementRiskFilterGuardedFold,
    guarded_folds: Sequence[HistoricalMarketMovementRiskFilterGuardedFold],
) -> str:
    payload = {
        "summary": summary,
        "checks": [check.model_dump(mode="json") for check in checks],
        "overall": guarded_overall.model_dump(mode="json"),
        "folds": [fold.model_dump(mode="json") for fold in guarded_folds],
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_market_movement_risk_filter_guarded_admission:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run guarded rolling admission for shadow market-movement risk-filter segments."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--scope-refinement-report-path", type=Path, required=True)
    parser.add_argument("--sample-readiness-report-path", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--admission-id",
        "--guarded-admission-id",
        dest="admission_id",
        default=DEFAULT_MARKET_MOVEMENT_RISK_FILTER_GUARDED_ADMISSION_ID,
    )
    parser.add_argument("--min-overall-candidate-count", type=int, default=1)
    parser.add_argument("--min-overall-accepted-count", type=int, default=1)
    parser.add_argument("--min-overall-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--min-fold-slice-count", type=int, default=1)
    parser.add_argument("--min-fold-fixture-count", type=int, default=1)
    parser.add_argument("--min-fold-candidate-count", type=int, default=1)
    parser.add_argument("--min-fold-accepted-count", type=int, default=1)
    parser.add_argument("--min-fold-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--max-failed-fold-count", type=int, default=0)
    parser.add_argument("--min-active-competition-fold-count", type=int, default=1)
    parser.add_argument("--min-active-season-cutoff-fold-count", type=int, default=1)
    parser.add_argument("--min-active-rolling-fold-count", type=int, default=1)
    parser.add_argument("--rolling-window-season-count", type=int, default=3)
    parser.add_argument("--rolling-window-step", type=int, default=1)
    parser.add_argument("--max-report-folds", type=int, default=120)
    parser.add_argument("--require-sample-readiness", action="store_true")
    parser.add_argument("--allow-sample-readiness-shadow-only", action="store_true")
    parser.add_argument(
        "--use-scope-refinement-gate-options",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--apply-failed-scope-guards",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--apply-block-actions-globally",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--skip-fully-guarded-non-overall-folds",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalMarketMovementRiskFilterGuardedAdmissionOptions:
    rolling_options = HistoricalMarketMovementRiskFilterRollingAdmissionOptions(
        sample_readiness_report_path=args.sample_readiness_report_path,
        require_sample_readiness=args.require_sample_readiness,
        require_sample_ready_allowed=not args.allow_sample_readiness_shadow_only,
        min_overall_candidate_count=args.min_overall_candidate_count,
        min_overall_accepted_count=args.min_overall_accepted_count,
        min_overall_adjusted_fixture_count=args.min_overall_adjusted_fixture_count,
        min_fold_slice_count=args.min_fold_slice_count,
        min_fold_fixture_count=args.min_fold_fixture_count,
        min_fold_candidate_count=args.min_fold_candidate_count,
        min_fold_accepted_count=args.min_fold_accepted_count,
        min_fold_adjusted_fixture_count=args.min_fold_adjusted_fixture_count,
        max_failed_fold_count=args.max_failed_fold_count,
        min_active_competition_fold_count=args.min_active_competition_fold_count,
        min_active_season_cutoff_fold_count=args.min_active_season_cutoff_fold_count,
        min_active_rolling_fold_count=args.min_active_rolling_fold_count,
        rolling_window_season_count=args.rolling_window_season_count,
        rolling_window_step=args.rolling_window_step,
        max_report_folds=args.max_report_folds,
    )
    return HistoricalMarketMovementRiskFilterGuardedAdmissionOptions(
        admission_id=args.admission_id,
        sample_readiness_report_path=args.sample_readiness_report_path,
        require_sample_readiness=args.require_sample_readiness,
        require_sample_ready_allowed=not args.allow_sample_readiness_shadow_only,
        rolling_options=rolling_options,
        use_scope_refinement_gate_options=args.use_scope_refinement_gate_options,
        apply_failed_scope_guards=args.apply_failed_scope_guards,
        apply_block_actions_globally=args.apply_block_actions_globally,
        skip_fully_guarded_non_overall_folds=(
            args.skip_fully_guarded_non_overall_folds
        ),
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
