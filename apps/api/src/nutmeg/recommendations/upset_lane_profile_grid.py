from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy
from nutmeg.recommendations.upset_lane_audit import (
    HistoricalUpsetLaneAuditGroup,
    HistoricalUpsetLaneAuditOptions,
    HistoricalUpsetLaneAuditReport,
    build_historical_upset_lane_audit_report,
)

type HistoricalUpsetLaneProfileGridStatus = Literal["generated"]
type HistoricalUpsetLaneProfileGridCandidateStatus = Literal["accepted", "rejected"]
type HistoricalUpsetLaneProfileGridCacheStatus = Literal["disabled", "hit", "miss"]


class HistoricalUpsetLaneProfileGridOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    competition_groups: tuple[tuple[str, ...], ...] = ((),)
    lane_min_probability_values: tuple[float, ...] = (0.18,)
    lane_min_decimal_odds_values: tuple[float | None, ...] = (None,)
    lane_max_decimal_odds_values: tuple[float | None, ...] = (5.0,)
    lane_min_model_edge_values: tuple[float | None, ...] = (-0.008,)
    lane_max_model_edge_values: tuple[float | None, ...] = (0.0,)
    lane_max_hit_probability_deficit_values: tuple[float | None, ...] = (0.20,)
    lane_score_boost_values: tuple[float, ...] = (0.25,)
    optimizer_profile: HistoricalOptimizerProfile = "solver"
    min_group_sample_size: int = Field(default=1, ge=1)
    top_case_limit: int = Field(default=10, ge=1, le=100)
    min_profile_candidate_sample_size: int = Field(default=1, ge=1)
    min_profile_candidate_improvement_rate: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
    )
    max_profile_candidate_harm_rate: float = Field(default=0.25, ge=0.0, le=1.0)
    min_profile_candidate_average_profit_loss_delta: float = 0.0
    min_profile_candidate_average_hit_probability_delta: float | None = Field(
        default=-0.20,
        ge=-1.0,
        le=1.0,
    )
    max_profile_candidate_average_brier_score_delta: float | None = 0.0
    max_profile_candidate_average_log_loss_delta: float | None = 0.0
    max_profile_candidate_average_calibration_error_delta: float | None = 0.0
    candidate_start_index: int = Field(default=0, ge=0)
    candidate_limit: int | None = Field(default=None, ge=1)
    candidate_cache_dir: Path | None = None
    read_candidate_cache: bool = True
    write_candidate_cache: bool = True


class HistoricalUpsetLaneProfileGridCandidate(BaseModel):
    candidate_key: str
    candidate_index: int = Field(default=0, ge=0)
    candidate_cache_key: str | None = None
    candidate_cache_status: HistoricalUpsetLaneProfileGridCacheStatus = "disabled"
    status: HistoricalUpsetLaneProfileGridCandidateStatus
    competition_ids: tuple[str, ...] = ()
    lane_min_probability: float
    lane_min_decimal_odds: float | None = None
    lane_max_decimal_odds: float | None = None
    lane_min_model_edge: float | None = None
    lane_max_model_edge: float | None = None
    lane_max_hit_probability_deficit: float | None = None
    lane_score_boost: float
    audit_report_key: str
    completed_lane_count: int = Field(ge=0)
    selected_lane_count: int = Field(ge=0)
    near_miss_count: int = Field(ge=0)
    failed_lane_count: int = Field(ge=0)
    lane_candidate_count: int = Field(ge=0)
    actual_improvement_count: int = Field(ge=0)
    actual_harm_count: int = Field(ge=0)
    actual_unchanged_count: int = Field(ge=0)
    average_profit_loss_delta: float | None = None
    average_hit_probability_delta: float | None = None
    profile_candidate_count: int = Field(ge=0)
    best_profile_candidate_key: str | None = None
    best_profile_candidate_summary_json: dict[str, object] = Field(default_factory=dict)
    closest_rejected_profile_key: str | None = None
    closest_rejected_profile_summary_json: dict[str, object] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalUpsetLaneProfileGridReport(BaseModel):
    report_key: str
    status: HistoricalUpsetLaneProfileGridStatus
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    total_grid_candidate_count: int = Field(default=0, ge=0)
    candidate_start_index: int = Field(default=0, ge=0)
    candidate_limit: int | None = Field(default=None, ge=1)
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    cache_hit_count: int = Field(default=0, ge=0)
    cache_miss_count: int = Field(default=0, ge=0)
    cache_write_count: int = Field(default=0, ge=0)
    candidates: list[HistoricalUpsetLaneProfileGridCandidate] = Field(
        default_factory=list
    )
    accepted_candidates: list[HistoricalUpsetLaneProfileGridCandidate] = Field(
        default_factory=list
    )
    best_candidate: HistoricalUpsetLaneProfileGridCandidate | None = None
    rejection_reason_counts: dict[str, int] = Field(default_factory=dict)
    profile_rejection_reason_counts: dict[str, int] = Field(default_factory=dict)
    competition_summary_json: dict[str, dict[str, object]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


class _GridCandidateSpec(BaseModel):
    candidate_index: int = Field(ge=0)
    competition_ids: tuple[str, ...] = ()
    lane_min_probability: float
    lane_min_decimal_odds: float | None = None
    lane_max_decimal_odds: float | None = None
    lane_min_model_edge: float | None = None
    lane_max_model_edge: float | None = None
    lane_max_hit_probability_deficit: float | None = None
    lane_score_boost: float


@dataclass(frozen=True)
class _GridCandidateEvaluationResult:
    candidate: HistoricalUpsetLaneProfileGridCandidate
    cache_status: HistoricalUpsetLaneProfileGridCacheStatus
    cache_written: bool
    warnings: tuple[str, ...] = ()


def build_historical_upset_lane_profile_grid_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalUpsetLaneProfileGridOptions | None = None,
) -> HistoricalUpsetLaneProfileGridReport:
    resolved_options = options or HistoricalUpsetLaneProfileGridOptions()
    all_specs = _grid_candidate_specs(resolved_options)
    selected_specs = _selected_grid_candidate_specs(all_specs, resolved_options)
    results = [
        _evaluate_or_load_grid_candidate(
            historical_slices,
            options=resolved_options,
            spec=spec,
        )
        for spec in selected_specs
    ]
    candidates = [result.candidate for result in results]
    cache_hit_count = sum(1 for result in results if result.cache_status == "hit")
    cache_miss_count = sum(1 for result in results if result.cache_status == "miss")
    cache_write_count = sum(1 for result in results if result.cache_written)
    accepted_candidates = [
        candidate for candidate in candidates if candidate.status == "accepted"
    ]
    best_candidate = _best_candidate(accepted_candidates or candidates)
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    prediction_count = sum(
        len(fixture.predictions)
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
    )
    warnings = [
        warning
        for candidate in candidates
        for warning in _candidate_warnings(candidate)
    ]
    warnings.extend(warning for result in results for warning in result.warnings)
    rejection_reason_counts = _rejection_reason_counts(candidates)
    profile_rejection_reason_counts = _profile_rejection_reason_counts(candidates)
    competition_summary = _competition_summary(candidates)
    summary: dict[str, object] = {
        "calculation_basis": "historical_upset_lane_profile_grid_v3_1",
        "slice_count": len(historical_slices),
        "fixture_count": fixture_count,
        "prediction_count": prediction_count,
        "total_grid_candidate_count": len(all_specs),
        "candidate_start_index": resolved_options.candidate_start_index,
        "candidate_limit": resolved_options.candidate_limit,
        "candidate_indices": [candidate.candidate_index for candidate in candidates],
        "candidate_count": len(candidates),
        "accepted_count": len(accepted_candidates),
        "rejected_count": len(candidates) - len(accepted_candidates),
        "cache_hit_count": cache_hit_count,
        "cache_miss_count": cache_miss_count,
        "cache_write_count": cache_write_count,
        "candidate_cache_dir": (
            str(resolved_options.candidate_cache_dir)
            if resolved_options.candidate_cache_dir is not None
            else None
        ),
        "read_candidate_cache": resolved_options.read_candidate_cache,
        "write_candidate_cache": resolved_options.write_candidate_cache,
        "optimizer_profile": resolved_options.optimizer_profile,
        "grid": _grid_summary(resolved_options),
        "best_candidate_key": (
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        "best_candidate_status": (
            best_candidate.status if best_candidate is not None else None
        ),
        "accepted_candidate_keys": [
            candidate.candidate_key for candidate in accepted_candidates
        ],
        "rejection_reason_counts": rejection_reason_counts,
        "profile_rejection_reason_counts": profile_rejection_reason_counts,
        "competition_summary": competition_summary,
        "warnings": warnings,
    }
    report_key = _report_key(summary, candidates)
    return HistoricalUpsetLaneProfileGridReport(
        report_key=report_key,
        status="generated",
        slice_count=len(historical_slices),
        fixture_count=fixture_count,
        prediction_count=prediction_count,
        total_grid_candidate_count=len(all_specs),
        candidate_start_index=resolved_options.candidate_start_index,
        candidate_limit=resolved_options.candidate_limit,
        candidate_count=len(candidates),
        accepted_count=len(accepted_candidates),
        rejected_count=len(candidates) - len(accepted_candidates),
        cache_hit_count=cache_hit_count,
        cache_miss_count=cache_miss_count,
        cache_write_count=cache_write_count,
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        best_candidate=best_candidate,
        rejection_reason_counts=rejection_reason_counts,
        profile_rejection_reason_counts=profile_rejection_reason_counts,
        competition_summary_json=competition_summary,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def merge_historical_upset_lane_profile_grid_reports(
    reports: Sequence[HistoricalUpsetLaneProfileGridReport],
    *,
    source_paths: Sequence[Path] = (),
) -> HistoricalUpsetLaneProfileGridReport:
    if not reports:
        raise ValueError("Provide at least one profile grid report to merge")
    candidates = sorted(
        [
            candidate
            for report in reports
            for candidate in report.candidates
        ],
        key=lambda candidate: (candidate.candidate_index, candidate.candidate_key),
    )
    accepted_candidates = [
        candidate for candidate in candidates if candidate.status == "accepted"
    ]
    best_candidate = _best_candidate(accepted_candidates or candidates)
    warnings = [
        warning
        for report in reports
        for warning in report.warnings
    ]
    warnings.extend(_merge_warnings(reports, candidates))
    total_grid_candidate_count = _merged_total_grid_candidate_count(reports)
    candidate_indices = [candidate.candidate_index for candidate in candidates]
    candidate_start_index = min(candidate_indices) if candidate_indices else 0
    rejection_reason_counts = _rejection_reason_counts(candidates)
    profile_rejection_reason_counts = _profile_rejection_reason_counts(candidates)
    competition_summary = _competition_summary(candidates)
    cache_hit_count = sum(report.cache_hit_count for report in reports)
    cache_miss_count = sum(report.cache_miss_count for report in reports)
    cache_write_count = sum(report.cache_write_count for report in reports)
    slice_count = reports[0].slice_count
    fixture_count = reports[0].fixture_count
    prediction_count = reports[0].prediction_count
    summary: dict[str, object] = {
        "calculation_basis": "historical_upset_lane_profile_grid_merged_v3_1",
        "source_report_count": len(reports),
        "source_report_keys": [report.report_key for report in reports],
        "source_report_paths": [str(path) for path in source_paths],
        "slice_count": slice_count,
        "fixture_count": fixture_count,
        "prediction_count": prediction_count,
        "total_grid_candidate_count": total_grid_candidate_count,
        "candidate_start_index": candidate_start_index,
        "candidate_limit": len(candidates),
        "candidate_indices": candidate_indices,
        "missing_candidate_indices": _missing_candidate_indices(
            candidate_indices,
            total_grid_candidate_count,
        ),
        "duplicate_candidate_indices": _duplicate_candidate_indices(candidate_indices),
        "is_full_grid": (
            bool(candidates)
            and len(candidates) == total_grid_candidate_count
            and not _missing_candidate_indices(candidate_indices, total_grid_candidate_count)
            and not _duplicate_candidate_indices(candidate_indices)
        ),
        "candidate_count": len(candidates),
        "accepted_count": len(accepted_candidates),
        "rejected_count": len(candidates) - len(accepted_candidates),
        "cache_hit_count": cache_hit_count,
        "cache_miss_count": cache_miss_count,
        "cache_write_count": cache_write_count,
        "optimizer_profile": reports[0].summary_json.get("optimizer_profile"),
        "grid": _merged_grid_summary(reports),
        "best_candidate_key": (
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        "best_candidate_status": (
            best_candidate.status if best_candidate is not None else None
        ),
        "accepted_candidate_keys": [
            candidate.candidate_key for candidate in accepted_candidates
        ],
        "rejection_reason_counts": rejection_reason_counts,
        "profile_rejection_reason_counts": profile_rejection_reason_counts,
        "competition_summary": competition_summary,
        "warnings": warnings,
    }
    report_key = _report_key(summary, candidates)
    return HistoricalUpsetLaneProfileGridReport(
        report_key=report_key,
        status="generated",
        slice_count=slice_count,
        fixture_count=fixture_count,
        prediction_count=prediction_count,
        total_grid_candidate_count=total_grid_candidate_count,
        candidate_start_index=candidate_start_index,
        candidate_limit=len(candidates),
        candidate_count=len(candidates),
        accepted_count=len(accepted_candidates),
        rejected_count=len(candidates) - len(accepted_candidates),
        cache_hit_count=cache_hit_count,
        cache_miss_count=cache_miss_count,
        cache_write_count=cache_write_count,
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        best_candidate=best_candidate,
        rejection_reason_counts=rejection_reason_counts,
        profile_rejection_reason_counts=profile_rejection_reason_counts,
        competition_summary_json=competition_summary,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_upset_lane_profile_grid_report(
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


def merge_main(argv: Sequence[str] | None = None) -> None:
    args = _parse_merge_args(argv)
    reports = [
        HistoricalUpsetLaneProfileGridReport.model_validate_json(
            report_path.read_text(encoding="utf-8")
        )
        for report_path in args.report_paths
    ]
    report = merge_historical_upset_lane_profile_grid_reports(
        reports,
        source_paths=args.report_paths,
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


def _grid_candidate_specs(
    options: HistoricalUpsetLaneProfileGridOptions,
) -> list[_GridCandidateSpec]:
    specs: list[_GridCandidateSpec] = []
    candidate_index = 0
    for competition_ids in options.competition_groups:
        for lane_min_probability in options.lane_min_probability_values:
            for lane_min_decimal_odds in options.lane_min_decimal_odds_values:
                for lane_max_decimal_odds in options.lane_max_decimal_odds_values:
                    for lane_min_model_edge in options.lane_min_model_edge_values:
                        for lane_max_model_edge in options.lane_max_model_edge_values:
                            for lane_max_hit_probability_deficit in (
                                options.lane_max_hit_probability_deficit_values
                            ):
                                for lane_score_boost in options.lane_score_boost_values:
                                    specs.append(
                                        _GridCandidateSpec(
                                            candidate_index=candidate_index,
                                            competition_ids=competition_ids,
                                            lane_min_probability=lane_min_probability,
                                            lane_min_decimal_odds=(
                                                lane_min_decimal_odds
                                            ),
                                            lane_max_decimal_odds=(
                                                lane_max_decimal_odds
                                            ),
                                            lane_min_model_edge=lane_min_model_edge,
                                            lane_max_model_edge=lane_max_model_edge,
                                            lane_max_hit_probability_deficit=(
                                                lane_max_hit_probability_deficit
                                            ),
                                            lane_score_boost=lane_score_boost,
                                        )
                                    )
                                    candidate_index += 1
    return specs


def _selected_grid_candidate_specs(
    specs: Sequence[_GridCandidateSpec],
    options: HistoricalUpsetLaneProfileGridOptions,
) -> list[_GridCandidateSpec]:
    start_index = min(options.candidate_start_index, len(specs))
    if options.candidate_limit is None:
        return list(specs[start_index:])
    end_index = min(start_index + options.candidate_limit, len(specs))
    return list(specs[start_index:end_index])


def _evaluate_or_load_grid_candidate(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalUpsetLaneProfileGridOptions,
    spec: _GridCandidateSpec,
) -> _GridCandidateEvaluationResult:
    cache_key = _candidate_cache_key(options, spec)
    if options.candidate_cache_dir is not None and options.read_candidate_cache:
        cached_candidate, cache_warning = _read_cached_candidate(
            options.candidate_cache_dir,
            cache_key,
        )
        if cached_candidate is not None:
            return _GridCandidateEvaluationResult(
                candidate=_candidate_with_cache_metadata(
                    cached_candidate,
                    spec=spec,
                    cache_key=cache_key,
                    cache_status="hit",
                ),
                cache_status="hit",
                cache_written=False,
                warnings=(),
            )
        warnings: tuple[str, ...] = (
            (cache_warning,) if cache_warning is not None else ()
        )
    else:
        warnings = ()

    candidate = _evaluate_grid_candidate(
        historical_slices,
        options=options,
        competition_ids=spec.competition_ids,
        lane_min_probability=spec.lane_min_probability,
        lane_min_decimal_odds=spec.lane_min_decimal_odds,
        lane_max_decimal_odds=spec.lane_max_decimal_odds,
        lane_min_model_edge=spec.lane_min_model_edge,
        lane_max_model_edge=spec.lane_max_model_edge,
        lane_max_hit_probability_deficit=spec.lane_max_hit_probability_deficit,
        lane_score_boost=spec.lane_score_boost,
    )
    cache_status: HistoricalUpsetLaneProfileGridCacheStatus = (
        "miss" if options.candidate_cache_dir is not None else "disabled"
    )
    candidate = _candidate_with_cache_metadata(
        candidate,
        spec=spec,
        cache_key=cache_key,
        cache_status=cache_status,
    )
    cache_written = False
    if options.candidate_cache_dir is not None and options.write_candidate_cache:
        cache_warning = _write_cached_candidate(
            options.candidate_cache_dir,
            cache_key,
            candidate,
        )
        cache_written = cache_warning is None
        if cache_warning is not None:
            warnings = (*warnings, cache_warning)
    return _GridCandidateEvaluationResult(
        candidate=candidate,
        cache_status=cache_status,
        cache_written=cache_written,
        warnings=warnings,
    )


def _evaluate_grid_candidate(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalUpsetLaneProfileGridOptions,
    competition_ids: tuple[str, ...],
    lane_min_probability: float,
    lane_min_decimal_odds: float | None,
    lane_max_decimal_odds: float | None,
    lane_min_model_edge: float | None,
    lane_max_model_edge: float | None,
    lane_max_hit_probability_deficit: float | None,
    lane_score_boost: float,
) -> HistoricalUpsetLaneProfileGridCandidate:
    audit_options = _audit_options(
        options,
        competition_ids=competition_ids,
        lane_min_probability=lane_min_probability,
        lane_min_decimal_odds=lane_min_decimal_odds,
        lane_max_decimal_odds=lane_max_decimal_odds,
        lane_min_model_edge=lane_min_model_edge,
        lane_max_model_edge=lane_max_model_edge,
        lane_max_hit_probability_deficit=lane_max_hit_probability_deficit,
        lane_score_boost=lane_score_boost,
    )
    audit = build_historical_upset_lane_audit_report(
        historical_slices,
        options=audit_options,
    )
    best_profile_candidate = _best_profile_candidate(audit)
    closest_rejected_profile = _closest_rejected_profile(audit)
    reason_codes = _grid_rejection_reason_codes(audit)
    status: HistoricalUpsetLaneProfileGridCandidateStatus = (
        "accepted" if not reason_codes else "rejected"
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_upset_lane_profile_grid_candidate_v3_1",
        "status": status,
        "competition_ids": list(competition_ids),
        "lane_min_probability": lane_min_probability,
        "lane_min_decimal_odds": lane_min_decimal_odds,
        "lane_max_decimal_odds": lane_max_decimal_odds,
        "lane_min_model_edge": lane_min_model_edge,
        "lane_max_model_edge": lane_max_model_edge,
        "lane_max_hit_probability_deficit": lane_max_hit_probability_deficit,
        "lane_score_boost": lane_score_boost,
        "audit_report_key": audit.report_key,
        "audit_summary": _audit_summary(audit),
        "best_profile_candidate_key": (
            best_profile_candidate.group_key
            if best_profile_candidate is not None
            else None
        ),
        "closest_rejected_profile_key": (
            closest_rejected_profile.group_key
            if closest_rejected_profile is not None
            else None
        ),
        "reason_codes": reason_codes,
    }
    candidate_key = _candidate_key(summary)
    return HistoricalUpsetLaneProfileGridCandidate(
        candidate_key=candidate_key,
        status=status,
        competition_ids=competition_ids,
        lane_min_probability=lane_min_probability,
        lane_min_decimal_odds=lane_min_decimal_odds,
        lane_max_decimal_odds=lane_max_decimal_odds,
        lane_min_model_edge=lane_min_model_edge,
        lane_max_model_edge=lane_max_model_edge,
        lane_max_hit_probability_deficit=lane_max_hit_probability_deficit,
        lane_score_boost=lane_score_boost,
        audit_report_key=audit.report_key,
        completed_lane_count=audit.completed_lane_count,
        selected_lane_count=audit.selected_lane_count,
        near_miss_count=audit.near_miss_count,
        failed_lane_count=audit.failed_lane_count,
        lane_candidate_count=audit.lane_candidate_count,
        actual_improvement_count=audit.actual_improvement_count,
        actual_harm_count=audit.actual_harm_count,
        actual_unchanged_count=audit.actual_unchanged_count,
        average_profit_loss_delta=audit.average_profit_loss_delta,
        average_hit_probability_delta=audit.average_hit_probability_delta,
        profile_candidate_count=audit.profile_candidate_count,
        best_profile_candidate_key=(
            best_profile_candidate.group_key
            if best_profile_candidate is not None
            else None
        ),
        best_profile_candidate_summary_json=(
            best_profile_candidate.model_dump(mode="json")
            if best_profile_candidate is not None
            else {}
        ),
        closest_rejected_profile_key=(
            closest_rejected_profile.group_key
            if closest_rejected_profile is not None
            else None
        ),
        closest_rejected_profile_summary_json=(
            closest_rejected_profile.model_dump(mode="json")
            if closest_rejected_profile is not None
            else {}
        ),
        reason_codes=reason_codes,
        summary_json={**summary, "candidate_key": candidate_key},
    )


def _audit_options(
    options: HistoricalUpsetLaneProfileGridOptions,
    *,
    competition_ids: tuple[str, ...],
    lane_min_probability: float,
    lane_min_decimal_odds: float | None,
    lane_max_decimal_odds: float | None,
    lane_min_model_edge: float | None,
    lane_max_model_edge: float | None,
    lane_max_hit_probability_deficit: float | None,
    lane_score_boost: float,
) -> HistoricalUpsetLaneAuditOptions:
    return HistoricalUpsetLaneAuditOptions(
        backtest_options=options.backtest_options.model_copy(
            update={
                "optimizer_profile": options.optimizer_profile,
                "upset_final_answer_lane": True,
                "upset_final_answer_lane_min_probability": lane_min_probability,
                "upset_final_answer_lane_min_decimal_odds": lane_min_decimal_odds,
                "upset_final_answer_lane_max_decimal_odds": lane_max_decimal_odds,
                "upset_final_answer_lane_min_model_edge": lane_min_model_edge,
                "upset_final_answer_lane_max_model_edge": lane_max_model_edge,
                "upset_final_answer_lane_competition_ids": competition_ids,
                "upset_final_answer_lane_max_hit_probability_deficit": (
                    lane_max_hit_probability_deficit
                ),
                "upset_final_answer_lane_score_boost": lane_score_boost,
            }
        ),
        min_group_sample_size=options.min_group_sample_size,
        top_case_limit=options.top_case_limit,
        min_profile_candidate_sample_size=options.min_profile_candidate_sample_size,
        min_profile_candidate_improvement_rate=(
            options.min_profile_candidate_improvement_rate
        ),
        max_profile_candidate_harm_rate=options.max_profile_candidate_harm_rate,
        min_profile_candidate_average_profit_loss_delta=(
            options.min_profile_candidate_average_profit_loss_delta
        ),
        min_profile_candidate_average_hit_probability_delta=(
            options.min_profile_candidate_average_hit_probability_delta
        ),
        max_profile_candidate_average_brier_score_delta=(
            options.max_profile_candidate_average_brier_score_delta
        ),
        max_profile_candidate_average_log_loss_delta=(
            options.max_profile_candidate_average_log_loss_delta
        ),
        max_profile_candidate_average_calibration_error_delta=(
            options.max_profile_candidate_average_calibration_error_delta
        ),
    )


def _grid_rejection_reason_codes(
    audit: HistoricalUpsetLaneAuditReport,
) -> list[str]:
    reason_codes: list[str] = []
    if audit.lane_candidate_count == 0:
        reason_codes.append("upset_lane_profile_grid:no_lane_candidates")
    if audit.completed_lane_count == 0:
        reason_codes.append("upset_lane_profile_grid:no_completed_lane")
    if audit.profile_candidate_count == 0:
        reason_codes.append("upset_lane_profile_grid:no_profile_candidates")
    return reason_codes


def _audit_summary(audit: HistoricalUpsetLaneAuditReport) -> dict[str, object]:
    return {
        "report_key": audit.report_key,
        "completed_lane_count": audit.completed_lane_count,
        "selected_lane_count": audit.selected_lane_count,
        "near_miss_count": audit.near_miss_count,
        "failed_lane_count": audit.failed_lane_count,
        "lane_candidate_count": audit.lane_candidate_count,
        "actual_improvement_count": audit.actual_improvement_count,
        "actual_harm_count": audit.actual_harm_count,
        "actual_unchanged_count": audit.actual_unchanged_count,
        "average_profit_loss_delta": audit.average_profit_loss_delta,
        "average_hit_probability_delta": audit.average_hit_probability_delta,
        "profile_candidate_count": audit.profile_candidate_count,
        "profile_candidate_group_keys": audit.summary_json.get(
            "profile_candidate_group_keys",
            [],
        ),
    }


def _best_profile_candidate(
    audit: HistoricalUpsetLaneAuditReport,
) -> HistoricalUpsetLaneAuditGroup | None:
    if not audit.profile_candidates:
        return None
    return sorted(
        audit.profile_candidates,
        key=lambda group: (
            group.actual_improvement_count,
            -(group.actual_harm_count),
            group.improvement_rate or 0.0,
            group.average_profit_loss_delta or 0.0,
            group.average_hit_probability_delta or -1.0,
            group.group_key,
        ),
        reverse=True,
    )[0]


def _closest_rejected_profile(
    audit: HistoricalUpsetLaneAuditReport,
) -> HistoricalUpsetLaneAuditGroup | None:
    rejected = [
        group
        for group in audit.groups
        if group.group_type == "profile" and group.decision == "rejected"
    ]
    if not rejected:
        return None
    return sorted(
        rejected,
        key=lambda group: (
            group.actual_improvement_count,
            -(group.actual_harm_count),
            group.improvement_rate or 0.0,
            group.average_profit_loss_delta or -999.0,
            group.average_hit_probability_delta or -1.0,
            -(group.average_brier_score_delta or 999.0),
            group.group_key,
        ),
        reverse=True,
    )[0]


def _best_candidate(
    candidates: Sequence[HistoricalUpsetLaneProfileGridCandidate],
) -> HistoricalUpsetLaneProfileGridCandidate | None:
    if not candidates:
        return None
    return sorted(candidates, key=_candidate_sort_key, reverse=True)[0]


def _candidate_sort_key(
    candidate: HistoricalUpsetLaneProfileGridCandidate,
) -> tuple[int, int, int, int, float, float, float, str]:
    return (
        1 if candidate.status == "accepted" else 0,
        candidate.profile_candidate_count,
        candidate.actual_improvement_count,
        -candidate.actual_harm_count,
        candidate.average_profit_loss_delta or -999.0,
        candidate.average_hit_probability_delta or -1.0,
        float(candidate.completed_lane_count),
        candidate.candidate_key,
    )


def _candidate_warnings(
    candidate: HistoricalUpsetLaneProfileGridCandidate,
) -> list[str]:
    if candidate.status == "accepted":
        return []
    return [
        f"{candidate.candidate_key}:{reason_code}"
        for reason_code in candidate.reason_codes
    ]


def _merge_warnings(
    reports: Sequence[HistoricalUpsetLaneProfileGridReport],
    candidates: Sequence[HistoricalUpsetLaneProfileGridCandidate],
) -> list[str]:
    warnings: list[str] = []
    for field_name in ("slice_count", "fixture_count", "prediction_count"):
        values = {getattr(report, field_name) for report in reports}
        if len(values) > 1:
            warnings.append(
                f"upset_lane_profile_grid_merge:inconsistent_{field_name}"
            )
    total_counts = {report.total_grid_candidate_count for report in reports}
    if len(total_counts) > 1:
        warnings.append(
            "upset_lane_profile_grid_merge:inconsistent_total_grid_candidate_count"
        )
    candidate_indices = [candidate.candidate_index for candidate in candidates]
    if _duplicate_candidate_indices(candidate_indices):
        warnings.append("upset_lane_profile_grid_merge:duplicate_candidate_indices")
    if _missing_candidate_indices(
        candidate_indices,
        _merged_total_grid_candidate_count(reports),
    ):
        warnings.append("upset_lane_profile_grid_merge:missing_candidate_indices")
    return warnings


def _merged_total_grid_candidate_count(
    reports: Sequence[HistoricalUpsetLaneProfileGridReport],
) -> int:
    return max(report.total_grid_candidate_count for report in reports)


def _missing_candidate_indices(
    candidate_indices: Sequence[int],
    total_grid_candidate_count: int,
) -> list[int]:
    present = set(candidate_indices)
    return [
        candidate_index
        for candidate_index in range(total_grid_candidate_count)
        if candidate_index not in present
    ]


def _duplicate_candidate_indices(candidate_indices: Sequence[int]) -> list[int]:
    counter: Counter[int] = Counter(candidate_indices)
    return sorted(
        candidate_index
        for candidate_index, count in counter.items()
        if count > 1
    )


def _merged_grid_summary(
    reports: Sequence[HistoricalUpsetLaneProfileGridReport],
) -> dict[str, object]:
    grid = dict(cast(dict[str, object], reports[0].summary_json.get("grid", {})))
    grid["candidate_start_index"] = min(
        (candidate.candidate_index for report in reports for candidate in report.candidates),
        default=0,
    )
    grid["candidate_limit"] = sum(report.candidate_count for report in reports)
    grid["candidate_cache_dir"] = None
    grid["read_candidate_cache"] = None
    grid["write_candidate_cache"] = None
    return grid


def _candidate_with_cache_metadata(
    candidate: HistoricalUpsetLaneProfileGridCandidate,
    *,
    spec: _GridCandidateSpec,
    cache_key: str,
    cache_status: HistoricalUpsetLaneProfileGridCacheStatus,
) -> HistoricalUpsetLaneProfileGridCandidate:
    return candidate.model_copy(
        update={
            "candidate_index": spec.candidate_index,
            "candidate_cache_key": cache_key,
            "candidate_cache_status": cache_status,
            "summary_json": {
                **candidate.summary_json,
                "candidate_index": spec.candidate_index,
                "candidate_cache_key": cache_key,
                "candidate_cache_status": cache_status,
            },
        }
    )


def _candidate_cache_key(
    options: HistoricalUpsetLaneProfileGridOptions,
    spec: _GridCandidateSpec,
) -> str:
    audit_options = _audit_options(
        options,
        competition_ids=spec.competition_ids,
        lane_min_probability=spec.lane_min_probability,
        lane_min_decimal_odds=spec.lane_min_decimal_odds,
        lane_max_decimal_odds=spec.lane_max_decimal_odds,
        lane_min_model_edge=spec.lane_min_model_edge,
        lane_max_model_edge=spec.lane_max_model_edge,
        lane_max_hit_probability_deficit=spec.lane_max_hit_probability_deficit,
        lane_score_boost=spec.lane_score_boost,
    )
    payload = {
        "calculation_basis": "historical_upset_lane_profile_grid_candidate_cache_v3_1",
        "spec": spec.model_dump(mode="json", exclude={"candidate_index"}),
        "audit_options": audit_options.model_dump(mode="json"),
    }
    digest = sha256(dumps(payload, sort_keys=True, default=str).encode("utf-8"))
    return f"historical_upset_lane_profile_grid_candidate_cache:{digest.hexdigest()[:16]}"


def _candidate_cache_path(cache_dir: Path, cache_key: str) -> Path:
    digest = cache_key.rsplit(":", 1)[-1]
    return cache_dir / f"{digest}.json"


def _read_cached_candidate(
    cache_dir: Path,
    cache_key: str,
) -> tuple[HistoricalUpsetLaneProfileGridCandidate | None, str | None]:
    cache_path = _candidate_cache_path(cache_dir, cache_key)
    if not cache_path.exists():
        return None, None
    try:
        return (
            HistoricalUpsetLaneProfileGridCandidate.model_validate_json(
                cache_path.read_text(encoding="utf-8")
            ),
            None,
        )
    except Exception as exc:
        return None, f"{cache_key}:candidate_cache_read_failed:{exc}"


def _write_cached_candidate(
    cache_dir: Path,
    cache_key: str,
    candidate: HistoricalUpsetLaneProfileGridCandidate,
) -> str | None:
    cache_path = _candidate_cache_path(cache_dir, cache_key)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            f"{candidate.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    except Exception as exc:
        return f"{cache_key}:candidate_cache_write_failed:{exc}"
    return None


def _rejection_reason_counts(
    candidates: Sequence[HistoricalUpsetLaneProfileGridCandidate],
) -> dict[str, int]:
    counter: Counter[str] = Counter(
        reason_code
        for candidate in candidates
        if candidate.status == "rejected"
        for reason_code in candidate.reason_codes
    )
    return dict(sorted(counter.items()))


def _profile_rejection_reason_counts(
    candidates: Sequence[HistoricalUpsetLaneProfileGridCandidate],
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for candidate in candidates:
        if candidate.status != "rejected":
            continue
        reason_codes = candidate.closest_rejected_profile_summary_json.get(
            "reason_codes",
            [],
        )
        if not isinstance(reason_codes, list):
            continue
        counter.update(
            reason_code
            for reason_code in reason_codes
            if isinstance(reason_code, str)
        )
    return dict(sorted(counter.items()))


def _competition_summary(
    candidates: Sequence[HistoricalUpsetLaneProfileGridCandidate],
) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        key = _competition_group_key(candidate.competition_ids)
        bucket = summary.setdefault(
            key,
            {
                "competition_ids": list(candidate.competition_ids),
                "candidate_count": 0,
                "accepted_count": 0,
                "rejected_count": 0,
                "lane_candidate_count": 0,
                "completed_lane_count": 0,
                "selected_lane_count": 0,
                "near_miss_count": 0,
                "actual_improvement_count": 0,
                "actual_harm_count": 0,
                "actual_unchanged_count": 0,
                "profile_candidate_count": 0,
                "rejection_reason_counts": {},
                "profile_rejection_reason_counts": {},
            },
        )
        bucket["candidate_count"] = _bucket_int(bucket, "candidate_count") + 1
        if candidate.status == "accepted":
            bucket["accepted_count"] = _bucket_int(bucket, "accepted_count") + 1
        else:
            bucket["rejected_count"] = _bucket_int(bucket, "rejected_count") + 1
        _increment_int_bucket(bucket, "lane_candidate_count", candidate.lane_candidate_count)
        _increment_int_bucket(bucket, "completed_lane_count", candidate.completed_lane_count)
        _increment_int_bucket(bucket, "selected_lane_count", candidate.selected_lane_count)
        _increment_int_bucket(bucket, "near_miss_count", candidate.near_miss_count)
        _increment_int_bucket(
            bucket,
            "actual_improvement_count",
            candidate.actual_improvement_count,
        )
        _increment_int_bucket(bucket, "actual_harm_count", candidate.actual_harm_count)
        _increment_int_bucket(
            bucket,
            "actual_unchanged_count",
            candidate.actual_unchanged_count,
        )
        _increment_int_bucket(
            bucket,
            "profile_candidate_count",
            candidate.profile_candidate_count,
        )
        _update_reason_bucket(
            bucket,
            "rejection_reason_counts",
            candidate.reason_codes if candidate.status == "rejected" else [],
        )
        profile_reason_codes = candidate.closest_rejected_profile_summary_json.get(
            "reason_codes",
            [],
        )
        _update_reason_bucket(
            bucket,
            "profile_rejection_reason_counts",
            profile_reason_codes if isinstance(profile_reason_codes, list) else [],
        )
    return {
        key: {
            **bucket,
            "rejection_reason_counts": dict(
                sorted(cast(dict[str, int], bucket["rejection_reason_counts"]).items())
            ),
            "profile_rejection_reason_counts": dict(
                sorted(
                    cast(
                        dict[str, int],
                        bucket["profile_rejection_reason_counts"],
                    ).items()
                )
            ),
        }
        for key, bucket in sorted(summary.items())
    }


def _competition_group_key(competition_ids: Sequence[str]) -> str:
    return "+".join(competition_ids) if competition_ids else "ALL"


def _increment_int_bucket(
    bucket: dict[str, object],
    field_name: str,
    amount: int,
) -> None:
    bucket[field_name] = _bucket_int(bucket, field_name) + amount


def _bucket_int(bucket: dict[str, object], field_name: str) -> int:
    return cast(int, bucket[field_name])


def _update_reason_bucket(
    bucket: dict[str, object],
    field_name: str,
    reason_codes: Sequence[object],
) -> None:
    counter = cast(dict[str, int], bucket[field_name])
    for reason_code in reason_codes:
        if isinstance(reason_code, str):
            counter[reason_code] = counter.get(reason_code, 0) + 1


def _grid_summary(options: HistoricalUpsetLaneProfileGridOptions) -> dict[str, object]:
    return {
        "competition_groups": [list(group) for group in options.competition_groups],
        "lane_min_probability_values": list(options.lane_min_probability_values),
        "lane_min_decimal_odds_values": list(options.lane_min_decimal_odds_values),
        "lane_max_decimal_odds_values": list(options.lane_max_decimal_odds_values),
        "lane_min_model_edge_values": list(options.lane_min_model_edge_values),
        "lane_max_model_edge_values": list(options.lane_max_model_edge_values),
        "lane_max_hit_probability_deficit_values": list(
            options.lane_max_hit_probability_deficit_values
        ),
        "lane_score_boost_values": list(options.lane_score_boost_values),
        "upset_signal_calibration_filters": {
            "max_signal_calibration_risk": (
                options.backtest_options.upset_final_answer_lane_max_signal_calibration_risk
            ),
            "min_signal_reliability_score": (
                options.backtest_options.upset_final_answer_lane_min_signal_reliability_score
            ),
        },
        "candidate_start_index": options.candidate_start_index,
        "candidate_limit": options.candidate_limit,
        "candidate_cache_dir": (
            str(options.candidate_cache_dir)
            if options.candidate_cache_dir is not None
            else None
        ),
        "read_candidate_cache": options.read_candidate_cache,
        "write_candidate_cache": options.write_candidate_cache,
        "profile_candidate_thresholds": {
            "min_sample_size": options.min_profile_candidate_sample_size,
            "min_improvement_rate": options.min_profile_candidate_improvement_rate,
            "max_harm_rate": options.max_profile_candidate_harm_rate,
            "min_average_profit_loss_delta": (
                options.min_profile_candidate_average_profit_loss_delta
            ),
            "min_average_hit_probability_delta": (
                options.min_profile_candidate_average_hit_probability_delta
            ),
            "max_average_brier_score_delta": (
                options.max_profile_candidate_average_brier_score_delta
            ),
            "max_average_log_loss_delta": (
                options.max_profile_candidate_average_log_loss_delta
            ),
            "max_average_calibration_error_delta": (
                options.max_profile_candidate_average_calibration_error_delta
            ),
        },
    }


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Search upset final-answer lane profile grids with audit gates."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--pass-types", default=",".join(DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES))
    parser.add_argument("--modes", default="single")
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
    parser.add_argument("--optimizer-profile", choices=["heuristic", "solver"], default="solver")
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
    parser.add_argument("--upset-final-answer-lane-pass-type", default="1x1")
    parser.add_argument(
        "--upset-final-answer-lane-mode",
        choices=["single", "multiple"],
        default="single",
    )
    parser.add_argument("--upset-final-answer-lane-candidate-limit", type=int, default=24)
    parser.add_argument(
        "--upset-final-answer-lane-min-protection-score",
        type=float,
        default=0.45,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-calibration-score",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-model-confidence-score",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-odds-stability-score",
        type=float,
        default=0.0,
    )
    parser.add_argument("--upset-final-answer-lane-max-volatility-penalty", type=float)
    parser.add_argument(
        "--upset-final-answer-lane-max-signal-calibration-risk",
        type=float,
    )
    parser.add_argument(
        "--upset-final-answer-lane-min-signal-reliability-score",
        type=float,
        default=0.0,
    )
    parser.add_argument("--competition-group", action="append", default=[])
    parser.add_argument("--lane-min-probability-values", default="0.18")
    parser.add_argument("--lane-min-decimal-odds-values", default="none")
    parser.add_argument("--lane-max-decimal-odds-values", default="5.0")
    parser.add_argument("--lane-min-model-edge-values", default="-0.008")
    parser.add_argument("--lane-max-model-edge-values", default="0.0")
    parser.add_argument("--lane-max-hit-probability-deficit-values", default="0.20")
    parser.add_argument("--lane-score-boost-values", default="0.25")
    parser.add_argument("--candidate-start-index", type=int, default=0)
    parser.add_argument("--candidate-limit", type=int)
    parser.add_argument("--candidate-cache-dir", type=Path)
    parser.add_argument("--no-candidate-cache-read", action="store_true")
    parser.add_argument("--no-candidate-cache-write", action="store_true")
    parser.add_argument("--min-group-sample-size", type=int, default=1)
    parser.add_argument("--top-case-limit", type=int, default=10)
    parser.add_argument("--min-profile-candidate-sample-size", type=int, default=1)
    parser.add_argument("--min-profile-candidate-improvement-rate", type=float, default=0.55)
    parser.add_argument("--max-profile-candidate-harm-rate", type=float, default=0.25)
    parser.add_argument(
        "--min-profile-candidate-average-profit-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--min-profile-candidate-average-hit-probability-delta",
        type=float,
        default=-0.20,
    )
    parser.add_argument(
        "--max-profile-candidate-average-brier-score-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-profile-candidate-average-log-loss-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-profile-candidate-average-calibration-error-delta",
        type=float,
        default=0.0,
    )
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _parse_merge_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Merge upset final-answer lane profile grid batch reports."
    )
    parser.add_argument("report_paths", nargs="+", type=Path)
    parser.add_argument("--output-path", type=Path)
    return parser.parse_args(argv)


def _options_from_args(args: Namespace) -> HistoricalUpsetLaneProfileGridOptions:
    return HistoricalUpsetLaneProfileGridOptions(
        backtest_options=HistoricalRecommendationBacktestOptions(
            pass_types=tuple(_csv(args.pass_types)),
            modes=tuple(cast(RecommendationMode, mode) for mode in _csv(args.modes)),
            strategy=cast(RecommendationStrategy, args.strategy),
            optimizer_profile=cast(HistoricalOptimizerProfile, args.optimizer_profile),
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
            upset_final_answer_lane=True,
            upset_final_answer_lane_pass_type=args.upset_final_answer_lane_pass_type,
            upset_final_answer_lane_mode=cast(
                RecommendationMode,
                args.upset_final_answer_lane_mode,
            ),
            upset_final_answer_lane_candidate_limit=(
                args.upset_final_answer_lane_candidate_limit
            ),
            upset_final_answer_lane_min_protection_score=(
                args.upset_final_answer_lane_min_protection_score
            ),
            upset_final_answer_lane_min_calibration_score=(
                args.upset_final_answer_lane_min_calibration_score
            ),
            upset_final_answer_lane_min_model_confidence_score=(
                args.upset_final_answer_lane_min_model_confidence_score
            ),
            upset_final_answer_lane_min_odds_stability_score=(
                args.upset_final_answer_lane_min_odds_stability_score
            ),
            upset_final_answer_lane_max_volatility_penalty=(
                args.upset_final_answer_lane_max_volatility_penalty
            ),
            upset_final_answer_lane_max_signal_calibration_risk=(
                args.upset_final_answer_lane_max_signal_calibration_risk
            ),
            upset_final_answer_lane_min_signal_reliability_score=(
                args.upset_final_answer_lane_min_signal_reliability_score
            ),
        ),
        competition_groups=_competition_groups_from_args(args.competition_group),
        lane_min_probability_values=_float_tuple(args.lane_min_probability_values),
        lane_min_decimal_odds_values=_optional_float_tuple(
            args.lane_min_decimal_odds_values
        ),
        lane_max_decimal_odds_values=_optional_float_tuple(
            args.lane_max_decimal_odds_values
        ),
        lane_min_model_edge_values=_optional_float_tuple(
            args.lane_min_model_edge_values
        ),
        lane_max_model_edge_values=_optional_float_tuple(
            args.lane_max_model_edge_values
        ),
        lane_max_hit_probability_deficit_values=_optional_float_tuple(
            args.lane_max_hit_probability_deficit_values
        ),
        lane_score_boost_values=_float_tuple(args.lane_score_boost_values),
        candidate_start_index=args.candidate_start_index,
        candidate_limit=args.candidate_limit,
        candidate_cache_dir=args.candidate_cache_dir,
        read_candidate_cache=not args.no_candidate_cache_read,
        write_candidate_cache=not args.no_candidate_cache_write,
        optimizer_profile=cast(HistoricalOptimizerProfile, args.optimizer_profile),
        min_group_sample_size=args.min_group_sample_size,
        top_case_limit=args.top_case_limit,
        min_profile_candidate_sample_size=args.min_profile_candidate_sample_size,
        min_profile_candidate_improvement_rate=(
            args.min_profile_candidate_improvement_rate
        ),
        max_profile_candidate_harm_rate=args.max_profile_candidate_harm_rate,
        min_profile_candidate_average_profit_loss_delta=(
            args.min_profile_candidate_average_profit_loss_delta
        ),
        min_profile_candidate_average_hit_probability_delta=(
            args.min_profile_candidate_average_hit_probability_delta
        ),
        max_profile_candidate_average_brier_score_delta=(
            args.max_profile_candidate_average_brier_score_delta
        ),
        max_profile_candidate_average_log_loss_delta=(
            args.max_profile_candidate_average_log_loss_delta
        ),
        max_profile_candidate_average_calibration_error_delta=(
            args.max_profile_candidate_average_calibration_error_delta
        ),
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path)
        for slice_path in args.slice_paths
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


def _competition_groups_from_args(values: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    if not values:
        return ((),)
    return tuple(tuple(_csv(value)) for value in values)


def _float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in _csv(value))


def _optional_float_tuple(value: str) -> tuple[float | None, ...]:
    return tuple(None if item.lower() == "none" else float(item) for item in _csv(value))


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _candidate_key(summary: Mapping[str, object]) -> str:
    digest = sha256(
        dumps(summary, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_upset_lane_profile_grid_candidate:{digest}"


def _report_key(
    summary: Mapping[str, object],
    candidates: Sequence[HistoricalUpsetLaneProfileGridCandidate],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "candidate_keys": [candidate.candidate_key for candidate in candidates],
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_upset_lane_profile_grid:{digest}"
