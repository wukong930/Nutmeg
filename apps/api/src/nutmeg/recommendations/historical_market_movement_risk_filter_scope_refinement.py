from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections import defaultdict
from collections.abc import Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_market_movement_risk_filter_rolling_admission import (
    HistoricalMarketMovementRiskFilterFold,
    HistoricalMarketMovementRiskFilterRollingAdmissionOptions,
    HistoricalMarketMovementRiskFilterRollingAdmissionReport,
    load_historical_market_movement_risk_filter_rolling_admission_report,
)
from nutmeg.recommendations.historical_market_movement_segment_gate import (
    HistoricalMarketMovementSegmentCandidate,
    HistoricalMarketMovementSegmentGateOptions,
    build_historical_market_movement_segment_gate_report,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalMarketMovementRiskFilterScopeRefinementStatus = Literal[
    "no_failed_folds",
    "guarded_scope_required",
    "stable_scope_found",
    "no_stable_scope",
]
type HistoricalMarketMovementRiskFilterScopeCandidateStatus = Literal[
    "stable_shadow_candidate",
    "guarded_shadow_candidate",
    "blocked_candidate",
    "insufficient_evidence",
]
type HistoricalMarketMovementRiskFilterScopeAction = Literal[
    "keep_shadow",
    "guard_failed_scopes",
    "block",
    "collect_more_evidence",
]

DEFAULT_MARKET_MOVEMENT_RISK_FILTER_SCOPE_REFINEMENT_ID = (
    "market-movement-risk-filter-scope-refinement-shadow-v3.2"
)


class HistoricalMarketMovementRiskFilterScopeRefinementOptions(BaseModel):
    refinement_id: str = DEFAULT_MARKET_MOVEMENT_RISK_FILTER_SCOPE_REFINEMENT_ID
    segment_gate_options: HistoricalMarketMovementSegmentGateOptions = Field(
        default_factory=HistoricalMarketMovementSegmentGateOptions
    )
    include_overall_fold: bool = True
    include_passed_folds: bool = True
    target_failed_fold_ids: tuple[str, ...] = ()
    min_segment_evaluation_count: int = Field(default=1, ge=1)
    min_segment_accepted_count: int = Field(default=1, ge=0)
    max_segment_rejected_count_for_stable: int = Field(default=0, ge=0)
    max_failed_scope_count_for_stable: int = Field(default=0, ge=0)
    min_final_hit_rate_delta: float | None = 0.0
    max_brier_score_delta: float | None = 0.0
    max_log_loss_delta: float | None = 0.0
    max_mean_calibration_error_delta: float | None = 0.0
    max_report_candidates: int = Field(default=80, ge=1, le=500)
    max_report_evaluations: int = Field(default=240, ge=1, le=2000)
    use_rolling_report_gate_options: bool = True


class HistoricalMarketMovementRiskFilterScopeEvaluation(BaseModel):
    evaluation_id: str
    fold_id: str
    fold_type: str
    fold_status: str
    source_slice_ids: list[str] = Field(default_factory=list)
    source_competition_ids: list[str] = Field(default_factory=list)
    source_season_ids: list[str] = Field(default_factory=list)
    segment_gate_report_key: str
    candidate_id: str
    candidate_rank: int = Field(ge=1)
    segment_group_key: str
    segment_group_type: str
    segment_label: str
    candidate_decision: str
    accepted: bool
    failed_quality: bool
    failed_scope: bool
    adjusted_fixture_count: int = Field(ge=0)
    adjusted_prediction_count: int = Field(ge=0)
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
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketMovementRiskFilterBlockedScope(BaseModel):
    segment_group_key: str
    segment_group_type: str
    segment_label: str
    fold_id: str
    fold_type: str
    source_competition_ids: list[str] = Field(default_factory=list)
    source_season_ids: list[str] = Field(default_factory=list)
    candidate_id: str
    failure_reasons: list[str] = Field(default_factory=list)
    brier_score_delta: float | None = None
    log_loss_delta: float | None = None
    final_hit_rate_delta: float | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketMovementRiskFilterScopeCandidate(BaseModel):
    segment_group_key: str
    segment_group_type: str
    segment_label: str
    status: HistoricalMarketMovementRiskFilterScopeCandidateStatus
    recommended_action: HistoricalMarketMovementRiskFilterScopeAction
    evaluated_fold_count: int = Field(ge=0)
    accepted_fold_count: int = Field(ge=0)
    rejected_fold_count: int = Field(ge=0)
    failed_scope_count: int = Field(ge=0)
    failed_quality_count: int = Field(ge=0)
    passing_fold_ids: list[str] = Field(default_factory=list)
    rejected_fold_ids: list[str] = Field(default_factory=list)
    failed_scope_fold_ids: list[str] = Field(default_factory=list)
    source_competition_ids: list[str] = Field(default_factory=list)
    source_season_ids: list[str] = Field(default_factory=list)
    total_adjusted_fixture_count: int = Field(ge=0)
    total_adjusted_prediction_count: int = Field(ge=0)
    best_candidate_id: str | None = None
    best_final_hit_rate_delta: float | None = None
    best_brier_score_delta: float | None = None
    best_log_loss_delta: float | None = None
    best_mean_calibration_error_delta: float | None = None
    average_brier_score_delta: float | None = None
    average_log_loss_delta: float | None = None
    average_final_hit_rate_delta: float | None = None
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalMarketMovementRiskFilterScopeRefinementReport(BaseModel):
    report_key: str
    status: HistoricalMarketMovementRiskFilterScopeRefinementStatus
    refinement_id: str
    rolling_admission_report_key: str
    rolling_admission_status: str
    rolling_risk_filter_allowed: bool
    rolling_shadow_allowed: bool
    source_failed_fold_count: int = Field(ge=0)
    analyzed_fold_count: int = Field(ge=0)
    scope_candidate_count: int = Field(ge=0)
    stable_scope_count: int = Field(ge=0)
    guarded_scope_count: int = Field(ge=0)
    blocked_scope_count: int = Field(ge=0)
    insufficient_scope_count: int = Field(ge=0)
    blocked_guard_count: int = Field(ge=0)
    best_scope_key: str | None = None
    best_scope: HistoricalMarketMovementRiskFilterScopeCandidate | None = None
    scopes: list[HistoricalMarketMovementRiskFilterScopeCandidate] = Field(
        default_factory=list
    )
    evaluations: list[HistoricalMarketMovementRiskFilterScopeEvaluation] = Field(
        default_factory=list
    )
    blocked_scopes: list[HistoricalMarketMovementRiskFilterBlockedScope] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_market_movement_risk_filter_scope_refinement_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    rolling_admission_report: HistoricalMarketMovementRiskFilterRollingAdmissionReport,
    options: HistoricalMarketMovementRiskFilterScopeRefinementOptions | None = None,
) -> HistoricalMarketMovementRiskFilterScopeRefinementReport:
    resolved_options = options or HistoricalMarketMovementRiskFilterScopeRefinementOptions()
    slice_index = {
        historical_slice.metadata.slice_id: historical_slice
        for historical_slice in historical_slices
    }
    source_failed_folds = [
        fold for fold in rolling_admission_report.folds if fold.status == "failed"
    ]
    analyzed_folds = _selected_folds(
        rolling_admission_report,
        options=resolved_options,
    )
    warnings = [*rolling_admission_report.warnings]
    evaluations: list[HistoricalMarketMovementRiskFilterScopeEvaluation] = []
    for fold in analyzed_folds:
        fold_slices, missing_slice_ids = _fold_slices(fold, slice_index)
        if missing_slice_ids:
            warnings.append(
                "market_movement_risk_filter_scope_refinement:"
                f"missing_slices:{fold.fold_id}:{','.join(missing_slice_ids)}"
            )
        if not fold_slices:
            continue
        gate_report = build_historical_market_movement_segment_gate_report(
            fold_slices,
            options=resolved_options.segment_gate_options,
        )
        evaluations.extend(
            _candidate_evaluation(fold, gate_report.report_key, candidate, resolved_options)
            for candidate in gate_report.candidates
        )
    scopes = sorted(
        _scope_candidates(evaluations, options=resolved_options),
        key=_scope_sort_key,
        reverse=True,
    )
    blocked_scopes = _blocked_scopes(scopes, evaluations)
    status = _report_status(
        rolling_admission_report,
        source_failed_folds=source_failed_folds,
        blocked_scopes=blocked_scopes,
        scopes=scopes,
    )
    best_scope = scopes[0] if scopes else None
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_market_movement_risk_filter_scope_refinement_v3_2"
        ),
        "refinement_id": resolved_options.refinement_id,
        "status": status,
        "rolling_admission_report_key": rolling_admission_report.report_key,
        "rolling_admission_status": rolling_admission_report.status,
        "rolling_risk_filter_allowed": rolling_admission_report.risk_filter_allowed,
        "rolling_shadow_allowed": rolling_admission_report.shadow_allowed,
        "source_failed_fold_count": len(source_failed_folds),
        "source_failed_fold_ids": [fold.fold_id for fold in source_failed_folds],
        "analyzed_fold_count": len(analyzed_folds),
        "scope_candidate_count": len(scopes),
        "stable_scope_count": _scope_status_count(scopes, "stable_shadow_candidate"),
        "guarded_scope_count": _scope_status_count(scopes, "guarded_shadow_candidate"),
        "blocked_scope_count": _scope_status_count(scopes, "blocked_candidate"),
        "insufficient_scope_count": _scope_status_count(scopes, "insufficient_evidence"),
        "blocked_guard_count": len(blocked_scopes),
        "best_scope_key": best_scope.segment_group_key if best_scope else None,
        "options": resolved_options.model_dump(mode="json"),
        "warnings": warnings,
    }
    report_key = _report_key(summary, scopes, evaluations, blocked_scopes)
    return HistoricalMarketMovementRiskFilterScopeRefinementReport(
        report_key=report_key,
        status=status,
        refinement_id=resolved_options.refinement_id,
        rolling_admission_report_key=rolling_admission_report.report_key,
        rolling_admission_status=rolling_admission_report.status,
        rolling_risk_filter_allowed=rolling_admission_report.risk_filter_allowed,
        rolling_shadow_allowed=rolling_admission_report.shadow_allowed,
        source_failed_fold_count=len(source_failed_folds),
        analyzed_fold_count=len(analyzed_folds),
        scope_candidate_count=len(scopes),
        stable_scope_count=_scope_status_count(scopes, "stable_shadow_candidate"),
        guarded_scope_count=_scope_status_count(scopes, "guarded_shadow_candidate"),
        blocked_scope_count=_scope_status_count(scopes, "blocked_candidate"),
        insufficient_scope_count=_scope_status_count(scopes, "insufficient_evidence"),
        blocked_guard_count=len(blocked_scopes),
        best_scope_key=best_scope.segment_group_key if best_scope else None,
        best_scope=best_scope,
        scopes=scopes[: resolved_options.max_report_candidates],
        evaluations=evaluations[: resolved_options.max_report_evaluations],
        blocked_scopes=blocked_scopes[: resolved_options.max_report_evaluations],
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def load_historical_market_movement_risk_filter_scope_refinement_report(
    path: Path | str,
) -> HistoricalMarketMovementRiskFilterScopeRefinementReport:
    return HistoricalMarketMovementRiskFilterScopeRefinementReport.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    rolling_report = load_historical_market_movement_risk_filter_rolling_admission_report(
        args.rolling_admission_report_path,
    )
    options = _options_from_args(args)
    if options.use_rolling_report_gate_options:
        rolling_options = _rolling_options_from_report(rolling_report)
        if rolling_options is not None:
            options = options.model_copy(
                update={"segment_gate_options": rolling_options.segment_gate_options}
            )
    report = build_historical_market_movement_risk_filter_scope_refinement_report(
        loaded_slices.slices,
        rolling_admission_report=rolling_report,
        options=options,
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
    if report.status == "no_stable_scope" and not args.no_fail_process:
        raise SystemExit(1)


def _selected_folds(
    rolling_report: HistoricalMarketMovementRiskFilterRollingAdmissionReport,
    *,
    options: HistoricalMarketMovementRiskFilterScopeRefinementOptions,
) -> list[HistoricalMarketMovementRiskFilterFold]:
    target_fold_ids = set(options.target_failed_fold_ids)
    folds: list[HistoricalMarketMovementRiskFilterFold] = []
    if options.include_overall_fold and not target_fold_ids:
        folds.append(rolling_report.overall_fold)
    for fold in rolling_report.folds:
        if target_fold_ids and fold.fold_id not in target_fold_ids:
            continue
        if fold.status == "skipped":
            continue
        if not options.include_passed_folds and fold.status != "failed":
            continue
        folds.append(fold)
    return folds


def _fold_slices(
    fold: HistoricalMarketMovementRiskFilterFold,
    slice_index: dict[str, HistoricalRecommendationSlice],
) -> tuple[list[HistoricalRecommendationSlice], list[str]]:
    slices: list[HistoricalRecommendationSlice] = []
    missing: list[str] = []
    for slice_id in fold.source_slice_ids:
        historical_slice = slice_index.get(slice_id)
        if historical_slice is None:
            missing.append(slice_id)
            continue
        slices.append(historical_slice)
    return slices, missing


def _candidate_evaluation(
    fold: HistoricalMarketMovementRiskFilterFold,
    segment_gate_report_key: str,
    candidate: HistoricalMarketMovementSegmentCandidate,
    options: HistoricalMarketMovementRiskFilterScopeRefinementOptions,
) -> HistoricalMarketMovementRiskFilterScopeEvaluation:
    failure_reasons = _evaluation_failure_reasons(candidate, options)
    accepted = not failure_reasons
    failed_scope = fold.status == "failed" and not accepted
    evaluation_id = _evaluation_id(fold.fold_id, candidate.candidate_id)
    return HistoricalMarketMovementRiskFilterScopeEvaluation(
        evaluation_id=evaluation_id,
        fold_id=fold.fold_id,
        fold_type=fold.fold_type,
        fold_status=fold.status,
        source_slice_ids=fold.source_slice_ids,
        source_competition_ids=fold.source_competition_ids,
        source_season_ids=fold.source_season_ids,
        segment_gate_report_key=segment_gate_report_key,
        candidate_id=candidate.candidate_id,
        candidate_rank=candidate.rank,
        segment_group_key=candidate.segment_group_key,
        segment_group_type=candidate.segment_group_type,
        segment_label=candidate.segment_label,
        candidate_decision=candidate.decision,
        accepted=accepted,
        failed_quality=not accepted,
        failed_scope=failed_scope,
        adjusted_fixture_count=candidate.adjusted_fixture_count,
        adjusted_prediction_count=candidate.adjusted_prediction_count,
        single_match_hit_rate_delta=_delta_number(
            candidate.single_match_deltas_json,
            "hit_rate_delta",
        ),
        single_match_brier_score_delta=_delta_number(
            candidate.single_match_deltas_json,
            "brier_score_delta",
        ),
        single_match_log_loss_delta=_delta_number(
            candidate.single_match_deltas_json,
            "log_loss_delta",
        ),
        final_hit_rate_delta=_delta_number(
            candidate.final_answer_deltas_json,
            "final_hit_rate_delta",
        ),
        roi_delta=_delta_number(candidate.final_answer_deltas_json, "roi_delta"),
        profit_loss_delta=_delta_number(
            candidate.final_answer_deltas_json,
            "profit_loss_delta",
        ),
        brier_score_delta=_delta_number(
            candidate.final_answer_deltas_json,
            "brier_score_delta",
        ),
        log_loss_delta=_delta_number(
            candidate.final_answer_deltas_json,
            "log_loss_delta",
        ),
        mean_calibration_error_delta=_delta_number(
            candidate.final_answer_deltas_json,
            "mean_calibration_error_delta",
        ),
        failure_reasons=failure_reasons,
        summary_json={
            "candidate_summary": candidate.summary_json,
            "fold_failure_reasons": fold.failure_reasons,
        },
    )


def _evaluation_failure_reasons(
    candidate: HistoricalMarketMovementSegmentCandidate,
    options: HistoricalMarketMovementRiskFilterScopeRefinementOptions,
) -> list[str]:
    failures = list(candidate.decision_reasons if candidate.decision != "accepted" else [])
    if candidate.decision != "accepted":
        failures.append("candidate_not_accepted")
    if not candidate.passed_single_match_gate:
        failures.append("single_match_gate_not_passed")
    if not candidate.passed_final_answer_gate:
        failures.append("final_answer_gate_not_passed")
    if not candidate.quality_gate.passed:
        failures.append("quality_gate_not_passed")
    final_hit_rate_delta = _delta_number(
        candidate.final_answer_deltas_json,
        "final_hit_rate_delta",
    )
    if (
        options.min_final_hit_rate_delta is not None
        and (
            final_hit_rate_delta is None
            or final_hit_rate_delta < options.min_final_hit_rate_delta
        )
    ):
        failures.append("final_hit_rate_delta_below_threshold")
    brier_score_delta = _delta_number(
        candidate.final_answer_deltas_json,
        "brier_score_delta",
    )
    if (
        options.max_brier_score_delta is not None
        and (
            brier_score_delta is None
            or brier_score_delta > options.max_brier_score_delta
        )
    ):
        failures.append("brier_score_delta_above_threshold")
    log_loss_delta = _delta_number(candidate.final_answer_deltas_json, "log_loss_delta")
    if (
        options.max_log_loss_delta is not None
        and (log_loss_delta is None or log_loss_delta > options.max_log_loss_delta)
    ):
        failures.append("log_loss_delta_above_threshold")
    calibration_delta = _delta_number(
        candidate.final_answer_deltas_json,
        "mean_calibration_error_delta",
    )
    if (
        options.max_mean_calibration_error_delta is not None
        and (
            calibration_delta is None
            or calibration_delta > options.max_mean_calibration_error_delta
        )
    ):
        failures.append("mean_calibration_error_delta_above_threshold")
    return sorted(set(failures))


def _scope_candidates(
    evaluations: Sequence[HistoricalMarketMovementRiskFilterScopeEvaluation],
    *,
    options: HistoricalMarketMovementRiskFilterScopeRefinementOptions,
) -> list[HistoricalMarketMovementRiskFilterScopeCandidate]:
    grouped: dict[str, list[HistoricalMarketMovementRiskFilterScopeEvaluation]] = (
        defaultdict(list)
    )
    for evaluation in evaluations:
        grouped[evaluation.segment_group_key].append(evaluation)
    return [
        _scope_candidate(segment_group_key, group_evaluations, options=options)
        for segment_group_key, group_evaluations in grouped.items()
    ]


def _scope_candidate(
    segment_group_key: str,
    evaluations: Sequence[HistoricalMarketMovementRiskFilterScopeEvaluation],
    *,
    options: HistoricalMarketMovementRiskFilterScopeRefinementOptions,
) -> HistoricalMarketMovementRiskFilterScopeCandidate:
    first = evaluations[0]
    accepted = [evaluation for evaluation in evaluations if evaluation.accepted]
    rejected = [evaluation for evaluation in evaluations if not evaluation.accepted]
    failed_scope = [evaluation for evaluation in evaluations if evaluation.failed_scope]
    failed_quality = [
        evaluation for evaluation in evaluations if evaluation.failed_quality
    ]
    status, action = _scope_status_action(
        evaluations,
        accepted=accepted,
        rejected=rejected,
        failed_scope=failed_scope,
        options=options,
    )
    best = _best_evaluation(evaluations)
    summary: dict[str, object] = {
        "segment_group_key": segment_group_key,
        "status": status,
        "recommended_action": action,
        "evaluated_fold_count": len(evaluations),
        "accepted_fold_count": len(accepted),
        "rejected_fold_count": len(rejected),
        "failed_scope_count": len(failed_scope),
        "failed_quality_count": len(failed_quality),
        "failure_reason_counts": _failure_reason_counts(evaluations),
    }
    return HistoricalMarketMovementRiskFilterScopeCandidate(
        segment_group_key=segment_group_key,
        segment_group_type=first.segment_group_type,
        segment_label=first.segment_label,
        status=status,
        recommended_action=action,
        evaluated_fold_count=len(evaluations),
        accepted_fold_count=len(accepted),
        rejected_fold_count=len(rejected),
        failed_scope_count=len(failed_scope),
        failed_quality_count=len(failed_quality),
        passing_fold_ids=[evaluation.fold_id for evaluation in accepted],
        rejected_fold_ids=[evaluation.fold_id for evaluation in rejected],
        failed_scope_fold_ids=[evaluation.fold_id for evaluation in failed_scope],
        source_competition_ids=sorted(
            {
                competition_id
                for evaluation in evaluations
                for competition_id in evaluation.source_competition_ids
            }
        ),
        source_season_ids=sorted(
            {
                season_id
                for evaluation in evaluations
                for season_id in evaluation.source_season_ids
            },
            key=_season_sort_key,
        ),
        total_adjusted_fixture_count=sum(
            evaluation.adjusted_fixture_count for evaluation in evaluations
        ),
        total_adjusted_prediction_count=sum(
            evaluation.adjusted_prediction_count for evaluation in evaluations
        ),
        best_candidate_id=best.candidate_id if best is not None else None,
        best_final_hit_rate_delta=best.final_hit_rate_delta if best is not None else None,
        best_brier_score_delta=best.brier_score_delta if best is not None else None,
        best_log_loss_delta=best.log_loss_delta if best is not None else None,
        best_mean_calibration_error_delta=(
            best.mean_calibration_error_delta if best is not None else None
        ),
        average_brier_score_delta=_average_delta(
            evaluations,
            "brier_score_delta",
        ),
        average_log_loss_delta=_average_delta(evaluations, "log_loss_delta"),
        average_final_hit_rate_delta=_average_delta(
            evaluations,
            "final_hit_rate_delta",
        ),
        summary_json=summary,
    )


def _scope_status_action(
    evaluations: Sequence[HistoricalMarketMovementRiskFilterScopeEvaluation],
    *,
    accepted: Sequence[HistoricalMarketMovementRiskFilterScopeEvaluation],
    rejected: Sequence[HistoricalMarketMovementRiskFilterScopeEvaluation],
    failed_scope: Sequence[HistoricalMarketMovementRiskFilterScopeEvaluation],
    options: HistoricalMarketMovementRiskFilterScopeRefinementOptions,
) -> tuple[
    HistoricalMarketMovementRiskFilterScopeCandidateStatus,
    HistoricalMarketMovementRiskFilterScopeAction,
]:
    if len(evaluations) < options.min_segment_evaluation_count:
        return "insufficient_evidence", "collect_more_evidence"
    if len(accepted) < options.min_segment_accepted_count:
        return "blocked_candidate", "block"
    if (
        len(rejected) <= options.max_segment_rejected_count_for_stable
        and len(failed_scope) <= options.max_failed_scope_count_for_stable
    ):
        return "stable_shadow_candidate", "keep_shadow"
    if failed_scope:
        return "guarded_shadow_candidate", "guard_failed_scopes"
    return "insufficient_evidence", "collect_more_evidence"


def _blocked_scopes(
    scopes: Sequence[HistoricalMarketMovementRiskFilterScopeCandidate],
    evaluations: Sequence[HistoricalMarketMovementRiskFilterScopeEvaluation],
) -> list[HistoricalMarketMovementRiskFilterBlockedScope]:
    guarded_keys = {
        scope.segment_group_key
        for scope in scopes
        if scope.recommended_action in {"guard_failed_scopes", "block"}
    }
    blocked: list[HistoricalMarketMovementRiskFilterBlockedScope] = []
    for evaluation in evaluations:
        if evaluation.segment_group_key not in guarded_keys or not evaluation.failed_scope:
            continue
        blocked.append(
            HistoricalMarketMovementRiskFilterBlockedScope(
                segment_group_key=evaluation.segment_group_key,
                segment_group_type=evaluation.segment_group_type,
                segment_label=evaluation.segment_label,
                fold_id=evaluation.fold_id,
                fold_type=evaluation.fold_type,
                source_competition_ids=evaluation.source_competition_ids,
                source_season_ids=evaluation.source_season_ids,
                candidate_id=evaluation.candidate_id,
                failure_reasons=evaluation.failure_reasons,
                brier_score_delta=evaluation.brier_score_delta,
                log_loss_delta=evaluation.log_loss_delta,
                final_hit_rate_delta=evaluation.final_hit_rate_delta,
                summary_json={
                    "evaluation_id": evaluation.evaluation_id,
                    "recommended_runtime_change": False,
                    "shadow_guard_only": True,
                },
            )
        )
    return sorted(blocked, key=_blocked_scope_sort_key)


def _report_status(
    rolling_report: HistoricalMarketMovementRiskFilterRollingAdmissionReport,
    *,
    source_failed_folds: Sequence[HistoricalMarketMovementRiskFilterFold],
    blocked_scopes: Sequence[HistoricalMarketMovementRiskFilterBlockedScope],
    scopes: Sequence[HistoricalMarketMovementRiskFilterScopeCandidate],
) -> HistoricalMarketMovementRiskFilterScopeRefinementStatus:
    if rolling_report.failed_fold_count == 0 and not source_failed_folds:
        return "no_failed_folds"
    if blocked_scopes:
        return "guarded_scope_required"
    if any(scope.status == "stable_shadow_candidate" for scope in scopes):
        return "stable_scope_found"
    return "no_stable_scope"


def _rolling_options_from_report(
    rolling_report: HistoricalMarketMovementRiskFilterRollingAdmissionReport,
) -> HistoricalMarketMovementRiskFilterRollingAdmissionOptions | None:
    options_json = rolling_report.summary_json.get("options")
    if not isinstance(options_json, dict):
        return None
    return HistoricalMarketMovementRiskFilterRollingAdmissionOptions.model_validate(
        options_json
    )


def _best_evaluation(
    evaluations: Sequence[HistoricalMarketMovementRiskFilterScopeEvaluation],
) -> HistoricalMarketMovementRiskFilterScopeEvaluation | None:
    if not evaluations:
        return None
    return sorted(evaluations, key=_evaluation_sort_key, reverse=True)[0]


def _evaluation_sort_key(
    evaluation: HistoricalMarketMovementRiskFilterScopeEvaluation,
) -> tuple[int, int, float, float, float, int]:
    return (
        1 if evaluation.accepted else 0,
        1 if evaluation.fold_status != "failed" else 0,
        -(evaluation.brier_score_delta or 0.0),
        -(evaluation.log_loss_delta or 0.0),
        evaluation.final_hit_rate_delta or 0.0,
        evaluation.adjusted_fixture_count,
    )


def _scope_sort_key(
    scope: HistoricalMarketMovementRiskFilterScopeCandidate,
) -> tuple[int, int, int, int, float, float]:
    status_rank = {
        "stable_shadow_candidate": 3,
        "guarded_shadow_candidate": 2,
        "insufficient_evidence": 1,
        "blocked_candidate": 0,
    }[scope.status]
    return (
        status_rank,
        scope.accepted_fold_count,
        -scope.failed_scope_count,
        scope.total_adjusted_fixture_count,
        -(scope.average_brier_score_delta or 0.0),
        -(scope.average_log_loss_delta or 0.0),
    )


def _blocked_scope_sort_key(
    blocked_scope: HistoricalMarketMovementRiskFilterBlockedScope,
) -> tuple[str, str, str]:
    return (
        blocked_scope.segment_group_key,
        blocked_scope.fold_type,
        blocked_scope.fold_id,
    )


def _failure_reason_counts(
    evaluations: Sequence[HistoricalMarketMovementRiskFilterScopeEvaluation],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for evaluation in evaluations:
        for reason in evaluation.failure_reasons:
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _average_delta(
    evaluations: Sequence[HistoricalMarketMovementRiskFilterScopeEvaluation],
    field_name: str,
) -> float | None:
    values = [
        value
        for evaluation in evaluations
        if (value := getattr(evaluation, field_name)) is not None
    ]
    if not values:
        return None
    return sum(cast(float, value) for value in values) / len(values)


def _scope_status_count(
    scopes: Sequence[HistoricalMarketMovementRiskFilterScopeCandidate],
    status: HistoricalMarketMovementRiskFilterScopeCandidateStatus,
) -> int:
    return sum(1 for scope in scopes if scope.status == status)


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


def _evaluation_id(fold_id: str, candidate_id: str) -> str:
    digest = sha256(f"{fold_id}:{candidate_id}".encode()).hexdigest()[:12]
    return f"market_movement_risk_filter_scope_evaluation:{digest}"


def _season_sort_key(season_id: str) -> tuple[int, str]:
    year_token = next(
        (token for token in season_id.replace("_", "-").split("-") if token.isdigit()),
        "0",
    )
    return (int(year_token), season_id)


def _report_key(
    summary: dict[str, object],
    scopes: Sequence[HistoricalMarketMovementRiskFilterScopeCandidate],
    evaluations: Sequence[HistoricalMarketMovementRiskFilterScopeEvaluation],
    blocked_scopes: Sequence[HistoricalMarketMovementRiskFilterBlockedScope],
) -> str:
    payload = {
        "summary": summary,
        "scopes": [scope.model_dump(mode="json") for scope in scopes],
        "evaluations": [
            evaluation.model_dump(mode="json") for evaluation in evaluations
        ],
        "blocked_scopes": [
            blocked_scope.model_dump(mode="json") for blocked_scope in blocked_scopes
        ],
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_market_movement_risk_filter_scope_refinement:{digest}"


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Locate failed-fold scopes for shadow market-movement risk-filter segments."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--rolling-admission-report-path", type=Path, required=True)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--refinement-id",
        default=DEFAULT_MARKET_MOVEMENT_RISK_FILTER_SCOPE_REFINEMENT_ID,
    )
    parser.add_argument(
        "--include-overall-fold",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--include-passed-folds",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--target-failed-fold-ids", default="")
    parser.add_argument("--min-segment-evaluation-count", type=int, default=1)
    parser.add_argument("--min-segment-accepted-count", type=int, default=1)
    parser.add_argument("--max-segment-rejected-count-for-stable", type=int, default=0)
    parser.add_argument("--max-failed-scope-count-for-stable", type=int, default=0)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--max-report-candidates", type=int, default=80)
    parser.add_argument("--max-report-evaluations", type=int, default=240)
    parser.add_argument(
        "--use-rolling-report-gate-options",
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
) -> HistoricalMarketMovementRiskFilterScopeRefinementOptions:
    return HistoricalMarketMovementRiskFilterScopeRefinementOptions(
        refinement_id=args.refinement_id,
        include_overall_fold=args.include_overall_fold,
        include_passed_folds=args.include_passed_folds,
        target_failed_fold_ids=tuple(_csv(args.target_failed_fold_ids)),
        min_segment_evaluation_count=args.min_segment_evaluation_count,
        min_segment_accepted_count=args.min_segment_accepted_count,
        max_segment_rejected_count_for_stable=(
            args.max_segment_rejected_count_for_stable
        ),
        max_failed_scope_count_for_stable=args.max_failed_scope_count_for_stable,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        max_report_candidates=args.max_report_candidates,
        max_report_evaluations=args.max_report_evaluations,
        use_rolling_report_gate_options=args.use_rolling_report_gate_options,
    )


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
