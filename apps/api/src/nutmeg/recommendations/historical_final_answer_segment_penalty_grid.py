from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from time import perf_counter
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.recommendations.competition_profiles import (
    default_competition_recommendation_profile_version,
)
from nutmeg.recommendations.historical_backtest import (
    DEFAULT_HISTORICAL_BACKTEST_MODES,
    DEFAULT_HISTORICAL_BACKTEST_PASS_TYPES,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestSuiteResult,
    HistoricalRecommendationSlice,
    _final_answer_signature,
    load_historical_recommendation_slice,
    run_historical_recommendation_backtest_suite,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode, RecommendationStrategy

type HistoricalFinalAnswerSegmentPenaltyGridStatus = Literal["generated"]
type HistoricalFinalAnswerSegmentPenaltyCandidateStatus = Literal[
    "accepted",
    "rejected",
]
type HistoricalFinalAnswerSegmentPenaltyCacheStatus = Literal["disabled", "hit", "miss"]

DEFAULT_SEGMENT_PENALTY_PASS_TYPE_GROUPS = (("3x1",),)
DEFAULT_SEGMENT_PENALTY_MODE_GROUPS: tuple[tuple[RecommendationMode, ...], ...] = (
    ("single",),
)
DEFAULT_SEGMENT_PENALTY_COMPETITION_GROUPS = (
    ("ESP_LA_LIGA", "GER_BUNDESLIGA"),
)
DEFAULT_SEGMENT_PENALTY_SEASON_GROUPS: tuple[tuple[str, ...], ...] = ((),)


class HistoricalFinalAnswerSegmentPenaltyGridOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    pass_type_groups: tuple[tuple[str, ...], ...] = (
        DEFAULT_SEGMENT_PENALTY_PASS_TYPE_GROUPS
    )
    mode_groups: tuple[tuple[RecommendationMode, ...], ...] = (
        DEFAULT_SEGMENT_PENALTY_MODE_GROUPS
    )
    competition_groups: tuple[tuple[str, ...], ...] = (
        DEFAULT_SEGMENT_PENALTY_COMPETITION_GROUPS
    )
    season_groups: tuple[tuple[str, ...], ...] = DEFAULT_SEGMENT_PENALTY_SEASON_GROUPS
    min_competition_season_index_values: tuple[int | None, ...] = (None,)
    max_competition_season_index_values: tuple[int | None, ...] = (None,)
    min_hit_probability_values: tuple[float | None, ...] = (None,)
    max_hit_probability_values: tuple[float | None, ...] = (None,)
    min_odds_product_values: tuple[float | None, ...] = (None,)
    max_odds_product_values: tuple[float | None, ...] = (None,)
    min_average_leg_decimal_odds_values: tuple[float | None, ...] = (None,)
    max_average_leg_decimal_odds_values: tuple[float | None, ...] = (None,)
    strength_values: tuple[float, ...] = (0.04, 0.08, 0.12, 0.16)
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic"
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver"
    fail_on_suite_statuses: tuple[str, ...] = ("regressed", "mixed")
    min_penalty_option_count: int = Field(default=1, ge=0)
    min_final_hit_count_delta: int = 0
    min_final_hit_rate_delta: float = 0.0
    min_candidate_roi: float | None = None
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_final_hit_harm_count_vs_baseline: int | None = Field(default=0, ge=0)
    max_profit_loss_harm_count_vs_baseline: int | None = Field(default=0, ge=0)
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    require_objective_improvement: bool = True
    min_objective_final_hit_count_delta: int = 0
    min_objective_roi_delta: float = 0.0
    min_objective_profit_loss_delta: float = 0.0
    comparison_epsilon: float = Field(default=1e-12, ge=0.0)
    baseline_cache_dir: Path | None = None
    read_baseline_cache: bool = True
    write_baseline_cache: bool = True
    progress_jsonl_path: Path | None = None
    candidate_checkpoint_jsonl_path: Path | None = None
    cached_candidates: tuple[HistoricalFinalAnswerSegmentPenaltyCandidate, ...] = ()
    candidate_start_index: int = Field(default=0, ge=0)
    candidate_limit: int | None = Field(default=None, ge=1)


class HistoricalFinalAnswerSegmentPenaltyCandidate(BaseModel):
    candidate_key: str
    candidate_index: int = Field(default=0, ge=0)
    status: HistoricalFinalAnswerSegmentPenaltyCandidateStatus
    pass_types: tuple[str, ...]
    modes: tuple[RecommendationMode, ...]
    competition_ids: tuple[str, ...] = ()
    season_ids: tuple[str, ...] = ()
    min_competition_season_index: int | None = Field(default=None, ge=1)
    max_competition_season_index: int | None = Field(default=None, ge=1)
    min_hit_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    max_hit_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    min_odds_product: float | None = Field(default=None, gt=1.0)
    max_odds_product: float | None = Field(default=None, gt=1.0)
    min_average_leg_decimal_odds: float | None = Field(default=None, gt=1.0)
    max_average_leg_decimal_odds: float | None = Field(default=None, gt=1.0)
    strength: float = Field(ge=0.0, le=1.0)
    suite_key: str
    suite_status: str
    penalty_option_count: int = Field(ge=0)
    final_hit_sample_size: int = Field(ge=0)
    final_hit_count: int = Field(ge=0)
    final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    roi: float | None = None
    profit_loss: float
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    mean_calibration_error: float | None = Field(default=None, ge=0.0)
    final_answer_changed_count: int = Field(default=0, ge=0)
    final_answer_changed_count_vs_baseline: int = Field(default=0, ge=0)
    final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    objective_improvement_satisfied: bool = False
    objective_improvement_metric_codes: list[str] = Field(default_factory=list)
    deltas_json: dict[str, object] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalFinalAnswerSegmentPenaltyGridReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerSegmentPenaltyGridStatus
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    total_grid_candidate_count: int = Field(default=0, ge=0)
    candidate_start_index: int = Field(default=0, ge=0)
    candidate_limit: int | None = Field(default=None, ge=1)
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    baseline_evaluation_elapsed_seconds: float = Field(default=0.0, ge=0.0)
    candidate_evaluation_elapsed_seconds: float = Field(default=0.0, ge=0.0)
    grid_evaluation_elapsed_seconds: float = Field(default=0.0, ge=0.0)
    progress_event_count: int = Field(default=0, ge=0)
    cached_candidate_count: int = Field(default=0, ge=0)
    reused_candidate_count: int = Field(default=0, ge=0)
    evaluated_candidate_count: int = Field(default=0, ge=0)
    baseline_cache_key: str | None = None
    baseline_cache_status: HistoricalFinalAnswerSegmentPenaltyCacheStatus = "disabled"
    baseline_cache_written: bool = False
    baseline_suite_key: str
    baseline_suite_status: str
    baseline_summary_json: dict[str, object] = Field(default_factory=dict)
    candidates: list[HistoricalFinalAnswerSegmentPenaltyCandidate] = Field(
        default_factory=list
    )
    accepted_candidates: list[HistoricalFinalAnswerSegmentPenaltyCandidate] = Field(
        default_factory=list
    )
    best_candidate: HistoricalFinalAnswerSegmentPenaltyCandidate | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    resolved_slice_paths: list[Path] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    manifest_results: list[HistoricalRecommendationSuiteManifestLoadResult] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)


class _GridCandidateSpec(BaseModel):
    candidate_index: int = Field(ge=0)
    pass_types: tuple[str, ...]
    modes: tuple[RecommendationMode, ...]
    competition_ids: tuple[str, ...] = ()
    season_ids: tuple[str, ...] = ()
    min_competition_season_index: int | None = Field(default=None, ge=1)
    max_competition_season_index: int | None = Field(default=None, ge=1)
    min_hit_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    max_hit_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    min_odds_product: float | None = Field(default=None, gt=1.0)
    max_odds_product: float | None = Field(default=None, gt=1.0)
    min_average_leg_decimal_odds: float | None = Field(default=None, gt=1.0)
    max_average_leg_decimal_odds: float | None = Field(default=None, gt=1.0)
    strength: float = Field(ge=0.0, le=1.0)


class _BaselineSuiteLoadResult(BaseModel):
    suite: HistoricalRecommendationBacktestSuiteResult
    cache_key: str | None = None
    cache_status: HistoricalFinalAnswerSegmentPenaltyCacheStatus = "disabled"
    cache_written: bool = False
    warnings: tuple[str, ...] = ()


def build_historical_final_answer_segment_penalty_grid_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalFinalAnswerSegmentPenaltyGridOptions | None = None,
) -> HistoricalFinalAnswerSegmentPenaltyGridReport:
    started_at = perf_counter()
    resolved_options = options or HistoricalFinalAnswerSegmentPenaltyGridOptions()
    all_specs = _grid_candidate_specs(resolved_options)
    selected_specs = _selected_grid_candidate_specs(all_specs, resolved_options)
    cached_candidates = _candidate_cache_for_specs(
        resolved_options.cached_candidates,
        selected_specs,
    )
    progress = _ProgressRecorder(resolved_options.progress_jsonl_path, started_at)
    progress.emit(
        "grid_started",
        slice_count=len(historical_slices),
        total_grid_candidate_count=len(all_specs),
        selected_candidate_count=len(selected_specs),
        cached_candidate_count=len(resolved_options.cached_candidates),
        reusable_candidate_count=len(cached_candidates),
        candidate_start_index=resolved_options.candidate_start_index,
        candidate_limit=resolved_options.candidate_limit,
    )
    baseline_started_at = perf_counter()
    progress.emit("baseline_started")
    baseline_result = _load_or_run_baseline_suite(
        historical_slices,
        options=resolved_options,
    )
    baseline_suite = baseline_result.suite
    baseline_elapsed = _elapsed_seconds(baseline_started_at)
    progress.emit(
        "baseline_completed",
        suite_key=baseline_suite.suite_key,
        suite_status=baseline_suite.status,
        cache_key=baseline_result.cache_key,
        cache_status=baseline_result.cache_status,
        cache_written=baseline_result.cache_written,
        elapsed_seconds=baseline_elapsed,
    )
    candidates: list[HistoricalFinalAnswerSegmentPenaltyCandidate] = []
    candidate_elapsed = 0.0
    reused_candidate_count = 0
    evaluated_candidate_count = 0
    for selected_index, spec in enumerate(selected_specs, start=1):
        cached_candidate = cached_candidates.get(spec.candidate_index)
        if cached_candidate is not None:
            candidates.append(cached_candidate)
            reused_candidate_count += 1
            progress.emit(
                "candidate_reused",
                selected_index=selected_index,
                selected_candidate_count=len(selected_specs),
                candidate_index=spec.candidate_index,
                candidate_key=cached_candidate.candidate_key,
                status=cached_candidate.status,
                reason_codes=cached_candidate.reason_codes,
                penalty_option_count=cached_candidate.penalty_option_count,
                final_hit_count_delta=cached_candidate.deltas_json.get(
                    "final_hit_count_delta"
                ),
                roi_delta=cached_candidate.deltas_json.get("roi_delta"),
                profit_loss_delta=cached_candidate.deltas_json.get(
                    "profit_loss_delta"
                ),
            )
            continue
        progress.emit(
            "candidate_started",
            selected_index=selected_index,
            selected_candidate_count=len(selected_specs),
            candidate_index=spec.candidate_index,
            pass_types=list(spec.pass_types),
            modes=list(spec.modes),
            competition_ids=list(spec.competition_ids),
            min_hit_probability=spec.min_hit_probability,
            max_hit_probability=spec.max_hit_probability,
            min_odds_product=spec.min_odds_product,
            max_odds_product=spec.max_odds_product,
            strength=spec.strength,
        )
        candidate_started_at = perf_counter()
        candidate = _evaluate_segment_penalty_candidate(
            historical_slices,
            baseline_suite=baseline_suite,
            options=resolved_options,
            spec=spec,
        )
        elapsed = _elapsed_seconds(candidate_started_at)
        candidate_elapsed += elapsed
        candidates.append(candidate)
        evaluated_candidate_count += 1
        _append_candidate_checkpoint(
            resolved_options.candidate_checkpoint_jsonl_path,
            candidate,
        )
        progress.emit(
            "candidate_completed",
            selected_index=selected_index,
            selected_candidate_count=len(selected_specs),
            candidate_index=spec.candidate_index,
            candidate_key=candidate.candidate_key,
            status=candidate.status,
            reason_codes=candidate.reason_codes,
            penalty_option_count=candidate.penalty_option_count,
            final_hit_count_delta=candidate.deltas_json.get("final_hit_count_delta"),
            roi_delta=candidate.deltas_json.get("roi_delta"),
            profit_loss_delta=candidate.deltas_json.get("profit_loss_delta"),
            elapsed_seconds=elapsed,
        )
    accepted_candidates = [candidate for candidate in candidates if candidate.status == "accepted"]
    best_candidate = _best_candidate(accepted_candidates or candidates)
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    prediction_count = sum(
        len(fixture.predictions)
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
    )
    warnings = [*baseline_result.warnings, *baseline_suite.warnings]
    for candidate in candidates:
        if candidate.suite_status in resolved_options.fail_on_suite_statuses:
            warnings.append(
                f"segment_penalty_grid:candidate_suite_status:{candidate.suite_status}"
            )
    grid_elapsed = _elapsed_seconds(started_at)
    summary: dict[str, object] = {
        "calculation_basis": "historical_final_answer_segment_penalty_grid_v3_1",
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
        "baseline_evaluation_elapsed_seconds": baseline_elapsed,
        "candidate_evaluation_elapsed_seconds": round(candidate_elapsed, 6),
        "grid_evaluation_elapsed_seconds": grid_elapsed,
        "progress_event_count": progress.event_count,
        "baseline_cache_key": baseline_result.cache_key,
        "baseline_cache_status": baseline_result.cache_status,
        "baseline_cache_written": baseline_result.cache_written,
        "baseline_cache_dir": (
            str(resolved_options.baseline_cache_dir)
            if resolved_options.baseline_cache_dir is not None
            else None
        ),
        "read_baseline_cache": resolved_options.read_baseline_cache,
        "write_baseline_cache": resolved_options.write_baseline_cache,
        "cached_candidate_count": len(resolved_options.cached_candidates),
        "reused_candidate_count": reused_candidate_count,
        "evaluated_candidate_count": evaluated_candidate_count,
        "candidate_checkpoint_jsonl_path": (
            str(resolved_options.candidate_checkpoint_jsonl_path)
            if resolved_options.candidate_checkpoint_jsonl_path is not None
            else None
        ),
        "baseline_suite_key": baseline_suite.suite_key,
        "baseline_suite_status": baseline_suite.status,
        "baseline_candidate_final_hit_rate": _summary_number(
            baseline_suite.summary_json,
            "candidate_final_hit_rate",
        ),
        "baseline_candidate_roi": _summary_number(
            baseline_suite.summary_json,
            "candidate_roi",
        ),
        "baseline_candidate_profit_loss": _summary_number(
            baseline_suite.summary_json,
            "candidate_profit_loss",
        ),
        "best_candidate_key": best_candidate.candidate_key if best_candidate else None,
        "best_candidate_status": best_candidate.status if best_candidate else None,
        "best_candidate_deltas": best_candidate.deltas_json if best_candidate else {},
        "accepted_candidate_keys": [candidate.candidate_key for candidate in accepted_candidates],
        "rejection_reason_counts": _rejection_reason_counts(candidates),
        "target_summary": _target_summary(candidates),
        "grid": _grid_summary(resolved_options),
        "warnings": warnings,
    }
    progress.emit(
        "grid_completed",
        report_key_placeholder="pending",
        accepted_count=len(accepted_candidates),
        rejected_count=len(candidates) - len(accepted_candidates),
        best_candidate_key=best_candidate.candidate_key if best_candidate else None,
        elapsed_seconds=grid_elapsed,
    )
    summary["progress_event_count"] = progress.event_count
    report_key = _report_key(summary, candidates)
    return HistoricalFinalAnswerSegmentPenaltyGridReport(
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
        baseline_evaluation_elapsed_seconds=baseline_elapsed,
        candidate_evaluation_elapsed_seconds=round(candidate_elapsed, 6),
        grid_evaluation_elapsed_seconds=grid_elapsed,
        progress_event_count=progress.event_count,
        baseline_cache_key=baseline_result.cache_key,
        baseline_cache_status=baseline_result.cache_status,
        baseline_cache_written=baseline_result.cache_written,
        cached_candidate_count=len(resolved_options.cached_candidates),
        reused_candidate_count=reused_candidate_count,
        evaluated_candidate_count=evaluated_candidate_count,
        baseline_suite_key=baseline_suite.suite_key,
        baseline_suite_status=baseline_suite.status,
        baseline_summary_json=baseline_suite.summary_json,
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        best_candidate=best_candidate,
        warnings=warnings,
        summary_json={**summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_final_answer_segment_penalty_grid_report(
        loaded_slices.slices,
        options=_options_from_args(args),
    )
    if loaded_slices.manifest_results:
        manifest_summaries = [
            _manifest_summary(manifest_result)
            for manifest_result in loaded_slices.manifest_results
        ]
        report.summary_json["suite_manifests"] = manifest_summaries
        if len(manifest_summaries) == 1:
            report.summary_json["suite_manifest"] = manifest_summaries[0]
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


def _load_or_run_baseline_suite(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalFinalAnswerSegmentPenaltyGridOptions,
) -> _BaselineSuiteLoadResult:
    cache_key: str | None = None
    warnings: tuple[str, ...] = ()
    if options.baseline_cache_dir is not None:
        cache_key = _baseline_cache_key(historical_slices, options)
        if options.read_baseline_cache:
            cached_suite, cache_warning = _read_cached_baseline_suite(
                options.baseline_cache_dir,
                cache_key,
            )
            if cache_warning is not None:
                warnings = (cache_warning,)
            if cached_suite is not None:
                return _BaselineSuiteLoadResult(
                    suite=cached_suite,
                    cache_key=cache_key,
                    cache_status="hit",
                    cache_written=False,
                    warnings=warnings,
                )
    suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=_baseline_backtest_options(options.backtest_options),
        baseline_optimizer_profile=options.baseline_optimizer_profile,
        candidate_optimizer_profile=options.candidate_optimizer_profile,
    )
    cache_status: HistoricalFinalAnswerSegmentPenaltyCacheStatus = (
        "miss" if options.baseline_cache_dir is not None else "disabled"
    )
    cache_written = False
    if (
        options.baseline_cache_dir is not None
        and options.write_baseline_cache
        and cache_key is not None
    ):
        cache_warning = _write_cached_baseline_suite(
            options.baseline_cache_dir,
            cache_key,
            suite,
        )
        cache_written = cache_warning is None
        if cache_warning is not None:
            warnings = (*warnings, cache_warning)
    return _BaselineSuiteLoadResult(
        suite=suite,
        cache_key=cache_key,
        cache_status=cache_status,
        cache_written=cache_written,
        warnings=warnings,
    )


def _grid_candidate_specs(
    options: HistoricalFinalAnswerSegmentPenaltyGridOptions,
) -> list[_GridCandidateSpec]:
    specs: list[_GridCandidateSpec] = []
    candidate_index = 0
    for pass_types in options.pass_type_groups:
        if not pass_types:
            continue
        for modes in options.mode_groups:
            if not modes:
                continue
            for competition_ids in options.competition_groups:
                for season_ids in options.season_groups:
                    for min_competition_index in (
                        options.min_competition_season_index_values
                    ):
                        for max_competition_index in (
                            options.max_competition_season_index_values
                        ):
                            if not _valid_min_max(
                                min_competition_index,
                                max_competition_index,
                            ):
                                continue
                            for min_hit_probability in options.min_hit_probability_values:
                                for max_hit_probability in options.max_hit_probability_values:
                                    if not _valid_min_max(
                                        min_hit_probability,
                                        max_hit_probability,
                                    ):
                                        continue
                                    for min_odds_product in options.min_odds_product_values:
                                        for max_odds_product in options.max_odds_product_values:
                                            if not _valid_min_max(
                                                min_odds_product,
                                                max_odds_product,
                                            ):
                                                continue
                                            for min_average_leg_odds in (
                                                options.min_average_leg_decimal_odds_values
                                            ):
                                                for max_average_leg_odds in (
                                                    options.max_average_leg_decimal_odds_values
                                                ):
                                                    if not _valid_min_max(
                                                        min_average_leg_odds,
                                                        max_average_leg_odds,
                                                    ):
                                                        continue
                                                    for strength in options.strength_values:
                                                        specs.append(
                                                            _GridCandidateSpec(
                                                                candidate_index=(
                                                                    candidate_index
                                                                ),
                                                                pass_types=pass_types,
                                                                modes=modes,
                                                                competition_ids=(
                                                                    competition_ids
                                                                ),
                                                                season_ids=season_ids,
                                                                min_competition_season_index=(
                                                                    min_competition_index
                                                                ),
                                                                max_competition_season_index=(
                                                                    max_competition_index
                                                                ),
                                                                min_hit_probability=(
                                                                    min_hit_probability
                                                                ),
                                                                max_hit_probability=(
                                                                    max_hit_probability
                                                                ),
                                                                min_odds_product=(
                                                                    min_odds_product
                                                                ),
                                                                max_odds_product=(
                                                                    max_odds_product
                                                                ),
                                                                min_average_leg_decimal_odds=(
                                                                    min_average_leg_odds
                                                                ),
                                                                max_average_leg_decimal_odds=(
                                                                    max_average_leg_odds
                                                                ),
                                                                strength=strength,
                                                            )
                                                        )
                                                        candidate_index += 1
    return specs


def _selected_grid_candidate_specs(
    specs: Sequence[_GridCandidateSpec],
    options: HistoricalFinalAnswerSegmentPenaltyGridOptions,
) -> list[_GridCandidateSpec]:
    start_index = min(options.candidate_start_index, len(specs))
    if options.candidate_limit is None:
        return list(specs[start_index:])
    end_index = min(start_index + options.candidate_limit, len(specs))
    return list(specs[start_index:end_index])


def _evaluate_segment_penalty_candidate(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    options: HistoricalFinalAnswerSegmentPenaltyGridOptions,
    spec: _GridCandidateSpec,
) -> HistoricalFinalAnswerSegmentPenaltyCandidate:
    candidate_options = options.backtest_options.model_copy(
        update={
            "final_answer_segment_penalty": True,
            "final_answer_segment_penalty_strength": spec.strength,
            "final_answer_segment_pass_types": spec.pass_types,
            "final_answer_segment_modes": spec.modes,
            "final_answer_segment_competition_ids": spec.competition_ids,
            "final_answer_segment_season_ids": spec.season_ids,
            "final_answer_segment_min_competition_season_index": (
                spec.min_competition_season_index
            ),
            "final_answer_segment_max_competition_season_index": (
                spec.max_competition_season_index
            ),
            "final_answer_segment_min_hit_probability": spec.min_hit_probability,
            "final_answer_segment_max_hit_probability": spec.max_hit_probability,
            "final_answer_segment_min_odds_product": spec.min_odds_product,
            "final_answer_segment_max_odds_product": spec.max_odds_product,
            "final_answer_segment_min_average_leg_decimal_odds": (
                spec.min_average_leg_decimal_odds
            ),
            "final_answer_segment_max_average_leg_decimal_odds": (
                spec.max_average_leg_decimal_odds
            ),
        }
    )
    suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=candidate_options,
        baseline_optimizer_profile=options.baseline_optimizer_profile,
        candidate_optimizer_profile=options.candidate_optimizer_profile,
    )
    deltas = _suite_deltas(baseline_suite, suite)
    objective_metric_codes = _objective_improvement_metric_codes(
        deltas,
        options=options,
    )
    objective_improvement_satisfied = not options.require_objective_improvement or bool(
        objective_metric_codes
    )
    reason_codes = _rejection_reason_codes(
        suite,
        deltas=deltas,
        objective_improvement_satisfied=objective_improvement_satisfied,
        options=options,
    )
    status: HistoricalFinalAnswerSegmentPenaltyCandidateStatus = (
        "accepted" if not reason_codes else "rejected"
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_final_answer_segment_penalty_candidate_v3_1",
        "status": status,
        "pass_types": list(spec.pass_types),
        "modes": list(spec.modes),
        "competition_ids": list(spec.competition_ids),
        "season_ids": list(spec.season_ids),
        "min_competition_season_index": spec.min_competition_season_index,
        "max_competition_season_index": spec.max_competition_season_index,
        "min_hit_probability": spec.min_hit_probability,
        "max_hit_probability": spec.max_hit_probability,
        "min_odds_product": spec.min_odds_product,
        "max_odds_product": spec.max_odds_product,
        "min_average_leg_decimal_odds": spec.min_average_leg_decimal_odds,
        "max_average_leg_decimal_odds": spec.max_average_leg_decimal_odds,
        "strength": spec.strength,
        "comparison_epsilon": options.comparison_epsilon,
        "require_objective_improvement": options.require_objective_improvement,
        "objective_improvement_satisfied": objective_improvement_satisfied,
        "objective_improvement_metric_codes": objective_metric_codes,
        "suite_key": suite.suite_key,
        "suite_status": suite.status,
        "penalty_option_count": _summary_int(
            suite.summary_json,
            "candidate_final_answer_segment_penalty_option_count",
        ),
        "deltas": deltas,
        "reason_codes": reason_codes,
    }
    candidate_key = _candidate_key(summary)
    return HistoricalFinalAnswerSegmentPenaltyCandidate(
        candidate_key=candidate_key,
        candidate_index=spec.candidate_index,
        status=status,
        pass_types=spec.pass_types,
        modes=spec.modes,
        competition_ids=spec.competition_ids,
        season_ids=spec.season_ids,
        min_competition_season_index=spec.min_competition_season_index,
        max_competition_season_index=spec.max_competition_season_index,
        min_hit_probability=spec.min_hit_probability,
        max_hit_probability=spec.max_hit_probability,
        min_odds_product=spec.min_odds_product,
        max_odds_product=spec.max_odds_product,
        min_average_leg_decimal_odds=spec.min_average_leg_decimal_odds,
        max_average_leg_decimal_odds=spec.max_average_leg_decimal_odds,
        strength=spec.strength,
        suite_key=suite.suite_key,
        suite_status=suite.status,
        penalty_option_count=_summary_int(
            suite.summary_json,
            "candidate_final_answer_segment_penalty_option_count",
        ),
        final_hit_sample_size=_summary_int(
            suite.summary_json,
            "candidate_final_hit_sample_size",
        ),
        final_hit_count=_summary_int(suite.summary_json, "candidate_final_hit_count"),
        final_hit_rate=_summary_number(suite.summary_json, "candidate_final_hit_rate"),
        roi=_summary_number(suite.summary_json, "candidate_roi"),
        profit_loss=_summary_number(suite.summary_json, "candidate_profit_loss") or 0.0,
        brier_score=_summary_number(suite.summary_json, "candidate_brier_score"),
        log_loss=_summary_number(suite.summary_json, "candidate_log_loss"),
        mean_calibration_error=_summary_number(
            suite.summary_json,
            "candidate_mean_calibration_error",
        ),
        final_answer_changed_count=_summary_int(
            suite.summary_json,
            "final_answer_changed_count",
        ),
        final_answer_changed_count_vs_baseline=_delta_int(
            deltas,
            "final_answer_changed_count_vs_baseline",
        ),
        final_hit_harm_count_vs_baseline=_delta_int(
            deltas,
            "final_hit_harm_count_vs_baseline",
        ),
        profit_loss_harm_count_vs_baseline=_delta_int(
            deltas,
            "profit_loss_harm_count_vs_baseline",
        ),
        objective_improvement_satisfied=objective_improvement_satisfied,
        objective_improvement_metric_codes=objective_metric_codes,
        deltas_json=deltas,
        reason_codes=reason_codes,
        summary_json={**summary, "candidate_key": candidate_key},
    )


def _suite_deltas(
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
) -> dict[str, object]:
    return {
        "final_hit_count_delta": _summary_int(
            candidate_suite.summary_json,
            "candidate_final_hit_count",
        )
        - _summary_int(baseline_suite.summary_json, "candidate_final_hit_count"),
        "final_hit_rate_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_final_hit_rate"),
            _summary_number(baseline_suite.summary_json, "candidate_final_hit_rate"),
        ),
        "candidate_roi": _summary_number(candidate_suite.summary_json, "candidate_roi"),
        "roi_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_roi"),
            _summary_number(baseline_suite.summary_json, "candidate_roi"),
        ),
        "profit_loss_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_profit_loss"),
            _summary_number(baseline_suite.summary_json, "candidate_profit_loss"),
        ),
        "brier_score_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_brier_score"),
            _summary_number(baseline_suite.summary_json, "candidate_brier_score"),
        ),
        "log_loss_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_log_loss"),
            _summary_number(baseline_suite.summary_json, "candidate_log_loss"),
        ),
        "mean_calibration_error_delta": _optional_delta(
            _summary_number(
                candidate_suite.summary_json,
                "candidate_mean_calibration_error",
            ),
            _summary_number(
                baseline_suite.summary_json,
                "candidate_mean_calibration_error",
            ),
        ),
        "penalty_option_count": _summary_int(
            candidate_suite.summary_json,
            "candidate_final_answer_segment_penalty_option_count",
        ),
        "final_answer_changed_count": _summary_int(
            candidate_suite.summary_json,
            "final_answer_changed_count",
        ),
        "final_answer_changed_count_vs_baseline": (
            _suite_final_answer_changed_count_vs_baseline(
                baseline_suite,
                candidate_suite,
            )
        ),
        "final_hit_harm_count_vs_baseline": _suite_final_hit_harm_count_vs_baseline(
            baseline_suite,
            candidate_suite,
        ),
        "profit_loss_harm_count_vs_baseline": (
            _suite_profit_loss_harm_count_vs_baseline(
                baseline_suite,
                candidate_suite,
            )
        ),
    }


def _suite_final_answer_changed_count_vs_baseline(
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
) -> int:
    return sum(
        1
        for baseline_comparison, candidate_comparison in zip(
            baseline_suite.comparisons,
            candidate_suite.comparisons,
            strict=True,
        )
        if _final_answer_signature(baseline_comparison.candidate.final_answer)
        != _final_answer_signature(candidate_comparison.candidate.final_answer)
    )


def _suite_final_hit_harm_count_vs_baseline(
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
) -> int:
    return sum(
        1
        for baseline_comparison, candidate_comparison in zip(
            baseline_suite.comparisons,
            candidate_suite.comparisons,
            strict=True,
        )
        if (
            candidate_comparison.candidate.final_hit_count
            < baseline_comparison.candidate.final_hit_count
        )
    )


def _suite_profit_loss_harm_count_vs_baseline(
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
) -> int:
    return sum(
        1
        for baseline_comparison, candidate_comparison in zip(
            baseline_suite.comparisons,
            candidate_suite.comparisons,
            strict=True,
        )
        if candidate_comparison.candidate.profit_loss < baseline_comparison.candidate.profit_loss
    )


def _rejection_reason_codes(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    deltas: Mapping[str, object],
    objective_improvement_satisfied: bool,
    options: HistoricalFinalAnswerSegmentPenaltyGridOptions,
) -> list[str]:
    reason_codes: list[str] = []
    if suite.status in options.fail_on_suite_statuses:
        reason_codes.append(f"segment_penalty:suite_status_{suite.status}")
    if _delta_int(deltas, "penalty_option_count") < options.min_penalty_option_count:
        reason_codes.append("segment_penalty:penalty_option_count_too_low")
    if _delta_int(deltas, "final_hit_count_delta") < options.min_final_hit_count_delta:
        reason_codes.append("segment_penalty:final_hit_count_regressed")
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="final_hit_rate_delta",
        threshold=options.min_final_hit_rate_delta,
        reason_code="segment_penalty:final_hit_rate_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_optional_minimum_reason(
        reason_codes,
        deltas,
        key="candidate_roi",
        threshold=options.min_candidate_roi,
        reason_code="segment_penalty:candidate_roi_below_floor",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="roi_delta",
        threshold=options.min_roi_delta,
        reason_code="segment_penalty:roi_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="profit_loss_delta",
        threshold=options.min_profit_loss_delta,
        reason_code="segment_penalty:profit_loss_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_optional_maximum_reason(
        reason_codes,
        deltas,
        key="final_hit_harm_count_vs_baseline",
        threshold=options.max_final_hit_harm_count_vs_baseline,
        reason_code="segment_penalty:final_hit_harm_count_above_threshold",
        epsilon=options.comparison_epsilon,
    )
    _append_optional_maximum_reason(
        reason_codes,
        deltas,
        key="profit_loss_harm_count_vs_baseline",
        threshold=options.max_profit_loss_harm_count_vs_baseline,
        reason_code="segment_penalty:profit_loss_harm_count_above_threshold",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="brier_score_delta",
        threshold=options.max_brier_score_delta,
        reason_code="segment_penalty:brier_score_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="log_loss_delta",
        threshold=options.max_log_loss_delta,
        reason_code="segment_penalty:log_loss_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="mean_calibration_error_delta",
        threshold=options.max_mean_calibration_error_delta,
        reason_code="segment_penalty:mean_calibration_error_regressed",
        epsilon=options.comparison_epsilon,
    )
    if not objective_improvement_satisfied:
        reason_codes.append("segment_penalty:objective_improvement_missing")
    return reason_codes


def _objective_improvement_metric_codes(
    deltas: Mapping[str, object],
    *,
    options: HistoricalFinalAnswerSegmentPenaltyGridOptions,
) -> list[str]:
    metric_codes: list[str] = []
    if _delta_int(deltas, "final_hit_count_delta") > options.min_objective_final_hit_count_delta:
        metric_codes.append("final_hit_count_delta")
    if _minimum_delta_exceeded(
        deltas,
        key="roi_delta",
        threshold=options.min_objective_roi_delta,
        epsilon=options.comparison_epsilon,
    ):
        metric_codes.append("roi_delta")
    if _minimum_delta_exceeded(
        deltas,
        key="profit_loss_delta",
        threshold=options.min_objective_profit_loss_delta,
        epsilon=options.comparison_epsilon,
    ):
        metric_codes.append("profit_loss_delta")
    return metric_codes


def _append_minimum_reason(
    reason_codes: list[str],
    deltas: Mapping[str, object],
    *,
    key: str,
    threshold: float,
    reason_code: str,
    epsilon: float,
) -> None:
    value = _delta_number(deltas, key)
    if value is None or value + epsilon < threshold:
        reason_codes.append(reason_code)


def _append_optional_minimum_reason(
    reason_codes: list[str],
    deltas: Mapping[str, object],
    *,
    key: str,
    threshold: float | None,
    reason_code: str,
    epsilon: float,
) -> None:
    if threshold is None:
        return
    value = _delta_number(deltas, key)
    if value is None or value + epsilon < threshold:
        reason_codes.append(reason_code)


def _append_maximum_reason(
    reason_codes: list[str],
    deltas: Mapping[str, object],
    *,
    key: str,
    threshold: float,
    reason_code: str,
    epsilon: float,
) -> None:
    value = _delta_number(deltas, key)
    if value is None or value - epsilon > threshold:
        reason_codes.append(reason_code)


def _append_optional_maximum_reason(
    reason_codes: list[str],
    deltas: Mapping[str, object],
    *,
    key: str,
    threshold: int | None,
    reason_code: str,
    epsilon: float,
) -> None:
    if threshold is None:
        return
    value = _delta_number(deltas, key)
    if value is None or value - epsilon > threshold:
        reason_codes.append(reason_code)


def _minimum_delta_exceeded(
    deltas: Mapping[str, object],
    *,
    key: str,
    threshold: float,
    epsilon: float,
) -> bool:
    value = _delta_number(deltas, key)
    if value is None:
        return False
    return value > threshold + epsilon


def _best_candidate(
    candidates: Sequence[HistoricalFinalAnswerSegmentPenaltyCandidate],
) -> HistoricalFinalAnswerSegmentPenaltyCandidate | None:
    if not candidates:
        return None
    return sorted(candidates, key=_candidate_sort_key, reverse=True)[0]


def _candidate_sort_key(
    candidate: HistoricalFinalAnswerSegmentPenaltyCandidate,
) -> tuple[int, int, float, float, float, float, int, str]:
    return (
        1 if candidate.status == "accepted" else 0,
        _delta_int(candidate.deltas_json, "final_hit_count_delta"),
        _delta_number(candidate.deltas_json, "final_hit_rate_delta") or -999.0,
        _delta_number(candidate.deltas_json, "roi_delta") or -999.0,
        _delta_number(candidate.deltas_json, "profit_loss_delta") or -999.0,
        -(_delta_number(candidate.deltas_json, "brier_score_delta") or 999.0),
        candidate.penalty_option_count,
        candidate.candidate_key,
    )


def _rejection_reason_counts(
    candidates: Sequence[HistoricalFinalAnswerSegmentPenaltyCandidate],
) -> dict[str, int]:
    counter: Counter[str] = Counter(
        reason_code
        for candidate in candidates
        if candidate.status == "rejected"
        for reason_code in candidate.reason_codes
    )
    return dict(sorted(counter.items()))


def _target_summary(
    candidates: Sequence[HistoricalFinalAnswerSegmentPenaltyCandidate],
) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for candidate in candidates:
        key = _target_key(candidate)
        bucket = summary.setdefault(
            key,
            {
                "pass_types": list(candidate.pass_types),
                "modes": list(candidate.modes),
                "competition_ids": list(candidate.competition_ids),
                "season_ids": list(candidate.season_ids),
                "min_competition_season_index": (
                    candidate.min_competition_season_index
                ),
                "max_competition_season_index": (
                    candidate.max_competition_season_index
                ),
                "candidate_count": 0,
                "accepted_count": 0,
                "rejected_count": 0,
                "penalty_option_count": 0,
                "best_candidate_key": None,
                "best_candidate_status": None,
                "best_candidate_deltas": {},
            },
        )
        bucket["candidate_count"] = _bucket_int(bucket, "candidate_count") + 1
        if candidate.status == "accepted":
            bucket["accepted_count"] = _bucket_int(bucket, "accepted_count") + 1
        else:
            bucket["rejected_count"] = _bucket_int(bucket, "rejected_count") + 1
        bucket["penalty_option_count"] = (
            _bucket_int(bucket, "penalty_option_count") + candidate.penalty_option_count
        )
        current_best_key = bucket.get("best_candidate_key")
        current_best = next(
            (
                existing
                for existing in candidates
                if existing.candidate_key == current_best_key
            ),
            None,
        )
        if current_best is None or _candidate_sort_key(candidate) > _candidate_sort_key(
            current_best
        ):
            bucket["best_candidate_key"] = candidate.candidate_key
            bucket["best_candidate_status"] = candidate.status
            bucket["best_candidate_deltas"] = candidate.deltas_json
    return dict(sorted(summary.items()))


def _target_key(candidate: HistoricalFinalAnswerSegmentPenaltyCandidate) -> str:
    return (
        f"pass={'+'.join(candidate.pass_types)}|"
        f"mode={'+'.join(candidate.modes)}|"
        f"competition={'+'.join(candidate.competition_ids) or 'ALL'}|"
        f"season={'+'.join(candidate.season_ids) or 'ALL'}|"
        f"season_index={candidate.min_competition_season_index or 'MIN'}.."
        f"{candidate.max_competition_season_index or 'MAX'}"
    )


def _grid_summary(
    options: HistoricalFinalAnswerSegmentPenaltyGridOptions,
) -> dict[str, object]:
    return {
        "pass_type_groups": [list(group) for group in options.pass_type_groups],
        "mode_groups": [list(group) for group in options.mode_groups],
        "competition_groups": [list(group) for group in options.competition_groups],
        "season_groups": [list(group) for group in options.season_groups],
        "min_competition_season_index_values": list(
            options.min_competition_season_index_values
        ),
        "max_competition_season_index_values": list(
            options.max_competition_season_index_values
        ),
        "min_hit_probability_values": list(options.min_hit_probability_values),
        "max_hit_probability_values": list(options.max_hit_probability_values),
        "min_odds_product_values": list(options.min_odds_product_values),
        "max_odds_product_values": list(options.max_odds_product_values),
        "min_average_leg_decimal_odds_values": list(
            options.min_average_leg_decimal_odds_values
        ),
        "max_average_leg_decimal_odds_values": list(
            options.max_average_leg_decimal_odds_values
        ),
        "strength_values": list(options.strength_values),
        "candidate_start_index": options.candidate_start_index,
        "candidate_limit": options.candidate_limit,
        "baseline_cache_dir": (
            str(options.baseline_cache_dir) if options.baseline_cache_dir is not None else None
        ),
        "read_baseline_cache": options.read_baseline_cache,
        "write_baseline_cache": options.write_baseline_cache,
        "candidate_checkpoint_jsonl_path": (
            str(options.candidate_checkpoint_jsonl_path)
            if options.candidate_checkpoint_jsonl_path is not None
            else None
        ),
        "gate_thresholds": {
            "fail_on_suite_statuses": list(options.fail_on_suite_statuses),
            "min_penalty_option_count": options.min_penalty_option_count,
            "min_final_hit_count_delta": options.min_final_hit_count_delta,
            "min_final_hit_rate_delta": options.min_final_hit_rate_delta,
            "min_candidate_roi": options.min_candidate_roi,
            "min_roi_delta": options.min_roi_delta,
            "min_profit_loss_delta": options.min_profit_loss_delta,
            "max_final_hit_harm_count_vs_baseline": (
                options.max_final_hit_harm_count_vs_baseline
            ),
            "max_profit_loss_harm_count_vs_baseline": (
                options.max_profit_loss_harm_count_vs_baseline
            ),
            "max_brier_score_delta": options.max_brier_score_delta,
            "max_log_loss_delta": options.max_log_loss_delta,
            "max_mean_calibration_error_delta": options.max_mean_calibration_error_delta,
            "require_objective_improvement": options.require_objective_improvement,
            "min_objective_final_hit_count_delta": (
                options.min_objective_final_hit_count_delta
            ),
            "min_objective_roi_delta": options.min_objective_roi_delta,
            "min_objective_profit_loss_delta": options.min_objective_profit_loss_delta,
            "comparison_epsilon": options.comparison_epsilon,
        },
    }


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Search final-answer segment penalty profile candidates."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", action="append", default=[], type=Path)
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
    parser.add_argument("--pass-type-group", action="append", default=[])
    parser.add_argument("--mode-group", action="append", default=[])
    parser.add_argument("--competition-group", action="append", default=[])
    parser.add_argument("--season-group", action="append", default=[])
    parser.add_argument("--min-competition-season-index-values", default="none")
    parser.add_argument("--max-competition-season-index-values", default="none")
    parser.add_argument("--min-hit-probability-values", default="none")
    parser.add_argument("--max-hit-probability-values", default="none")
    parser.add_argument("--min-odds-product-values", default="none")
    parser.add_argument("--max-odds-product-values", default="none")
    parser.add_argument("--min-average-leg-decimal-odds-values", default="none")
    parser.add_argument("--max-average-leg-decimal-odds-values", default="none")
    parser.add_argument("--strength-values", default="0.04,0.08,0.12,0.16")
    parser.add_argument("--fail-on-suite-statuses", default="regressed,mixed")
    parser.add_argument("--min-penalty-option-count", type=int, default=1)
    parser.add_argument("--min-final-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-candidate-roi", type=float)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-final-hit-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument("--max-profit-loss-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument(
        "--require-objective-improvement",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--min-objective-final-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-objective-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-objective-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--comparison-epsilon", type=float, default=1e-12)
    parser.add_argument("--baseline-cache-dir", type=Path)
    parser.add_argument(
        "--read-baseline-cache",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--write-baseline-cache",
        action=BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--progress-jsonl-path", type=Path)
    parser.add_argument("--candidate-checkpoint-jsonl-path", type=Path)
    parser.add_argument("--reuse-report", action="append", default=[], type=Path)
    parser.add_argument("--candidate-start-index", type=int, default=0)
    parser.add_argument("--candidate-limit", type=int)
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerSegmentPenaltyGridOptions:
    return HistoricalFinalAnswerSegmentPenaltyGridOptions(
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
        pass_type_groups=_string_groups_from_args(
            args.pass_type_group,
            default=DEFAULT_SEGMENT_PENALTY_PASS_TYPE_GROUPS,
        ),
        mode_groups=_mode_groups_from_args(
            args.mode_group,
            default=DEFAULT_SEGMENT_PENALTY_MODE_GROUPS,
        ),
        competition_groups=_string_groups_from_args(
            args.competition_group,
            default=DEFAULT_SEGMENT_PENALTY_COMPETITION_GROUPS,
        ),
        season_groups=_string_groups_from_args(
            args.season_group,
            default=DEFAULT_SEGMENT_PENALTY_SEASON_GROUPS,
        ),
        min_competition_season_index_values=_optional_int_tuple(
            args.min_competition_season_index_values
        ),
        max_competition_season_index_values=_optional_int_tuple(
            args.max_competition_season_index_values
        ),
        min_hit_probability_values=_optional_float_tuple(args.min_hit_probability_values),
        max_hit_probability_values=_optional_float_tuple(args.max_hit_probability_values),
        min_odds_product_values=_optional_float_tuple(args.min_odds_product_values),
        max_odds_product_values=_optional_float_tuple(args.max_odds_product_values),
        min_average_leg_decimal_odds_values=_optional_float_tuple(
            args.min_average_leg_decimal_odds_values
        ),
        max_average_leg_decimal_odds_values=_optional_float_tuple(
            args.max_average_leg_decimal_odds_values
        ),
        strength_values=_float_tuple(args.strength_values),
        baseline_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.baseline_optimizer_profile,
        ),
        candidate_optimizer_profile=cast(
            HistoricalOptimizerProfile,
            args.candidate_optimizer_profile,
        ),
        fail_on_suite_statuses=tuple(_csv(args.fail_on_suite_statuses)),
        min_penalty_option_count=args.min_penalty_option_count,
        min_final_hit_count_delta=args.min_final_hit_count_delta,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_candidate_roi=args.min_candidate_roi,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_final_hit_harm_count_vs_baseline=(
            args.max_final_hit_harm_count_vs_baseline
        ),
        max_profit_loss_harm_count_vs_baseline=(
            args.max_profit_loss_harm_count_vs_baseline
        ),
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
        require_objective_improvement=args.require_objective_improvement,
        min_objective_final_hit_count_delta=args.min_objective_final_hit_count_delta,
        min_objective_roi_delta=args.min_objective_roi_delta,
        min_objective_profit_loss_delta=args.min_objective_profit_loss_delta,
        comparison_epsilon=args.comparison_epsilon,
        baseline_cache_dir=args.baseline_cache_dir,
        read_baseline_cache=args.read_baseline_cache,
        write_baseline_cache=args.write_baseline_cache,
        progress_jsonl_path=args.progress_jsonl_path,
        candidate_checkpoint_jsonl_path=args.candidate_checkpoint_jsonl_path,
        cached_candidates=tuple(_cached_candidates_from_args(args)),
        candidate_start_index=args.candidate_start_index,
        candidate_limit=args.candidate_limit,
    )


def _historical_slices_from_args(args: Namespace) -> _LoadedHistoricalSlices:
    explicit_slices = [
        load_historical_recommendation_slice(slice_path) for slice_path in args.slice_paths
    ]
    suite_manifests = list(args.suite_manifest or [])
    if not suite_manifests:
        if not explicit_slices:
            raise ValueError("Provide at least one slice path or --suite-manifest")
        return _LoadedHistoricalSlices(
            slices=explicit_slices,
            resolved_slice_paths=list(args.slice_paths),
        )
    bundles = [
        load_historical_recommendation_suite_manifest_bundle(suite_manifest)
        for suite_manifest in suite_manifests
    ]
    manifest_slices = [
        historical_slice
        for bundle in bundles
        for historical_slice in bundle.slices
    ]
    resolved_slice_paths = [
        slice_path
        for bundle in bundles
        for slice_path in bundle.resolved_slice_paths
    ]
    warnings = [warning for bundle in bundles for warning in bundle.warnings]
    return _LoadedHistoricalSlices(
        slices=[*manifest_slices, *explicit_slices],
        resolved_slice_paths=[*resolved_slice_paths, *args.slice_paths],
        manifest_result=bundles[0] if len(bundles) == 1 else None,
        manifest_results=bundles,
        warnings=warnings,
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


class _ProgressRecorder:
    def __init__(self, path: Path | None, started_at: float) -> None:
        self.path = path
        self.started_at = started_at
        self.event_count = 0
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def emit(self, event: str, **payload: object) -> None:
        if self.path is None:
            return
        self.event_count += 1
        body = {
            "event_index": self.event_count,
            "event": event,
            "elapsed_since_grid_start_seconds": _elapsed_seconds(self.started_at),
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"{dumps(body, ensure_ascii=False, sort_keys=True)}\n")


def _elapsed_seconds(started_at: float) -> float:
    return round(max(perf_counter() - started_at, 0.0), 6)


def _cached_candidates_from_args(
    args: Namespace,
) -> list[HistoricalFinalAnswerSegmentPenaltyCandidate]:
    candidates: list[HistoricalFinalAnswerSegmentPenaltyCandidate] = []
    for report_path in args.reuse_report:
        candidates.extend(_load_report_candidates(report_path))
    checkpoint_path = args.candidate_checkpoint_jsonl_path
    if checkpoint_path is not None and checkpoint_path.exists():
        candidates.extend(_load_candidate_checkpoint(checkpoint_path))
    return candidates


def _load_report_candidates(
    path: Path,
) -> list[HistoricalFinalAnswerSegmentPenaltyCandidate]:
    payload = loads(path.read_text(encoding="utf-8"))
    return [
        HistoricalFinalAnswerSegmentPenaltyCandidate.model_validate(candidate_payload)
        for candidate_payload in payload.get("candidates", [])
    ]


def _load_candidate_checkpoint(
    path: Path,
) -> list[HistoricalFinalAnswerSegmentPenaltyCandidate]:
    candidates: list[HistoricalFinalAnswerSegmentPenaltyCandidate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        candidates.append(
            HistoricalFinalAnswerSegmentPenaltyCandidate.model_validate(loads(line))
        )
    return candidates


def _baseline_cache_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    options: HistoricalFinalAnswerSegmentPenaltyGridOptions,
) -> str:
    baseline_options = _baseline_backtest_options(options.backtest_options)
    payload = {
        "calculation_basis": "historical_final_answer_segment_penalty_baseline_cache_v3_1",
        "slice_ids": [
            {
                "slice_id": historical_slice.metadata.slice_id,
                "as_of_time_utc": historical_slice.as_of_time_utc.isoformat(),
            }
            for historical_slice in historical_slices
        ],
        "options": baseline_options.model_dump(mode="json"),
        "baseline_optimizer_profile": options.baseline_optimizer_profile,
        "candidate_optimizer_profile": options.candidate_optimizer_profile,
        "competition_profile_version": default_competition_recommendation_profile_version(),
    }
    digest = sha256(dumps(payload, sort_keys=True, default=str).encode("utf-8"))
    return f"historical_final_answer_segment_penalty_baseline_cache:{digest.hexdigest()[:16]}"


def _baseline_cache_path(cache_dir: Path, cache_key: str) -> Path:
    digest = cache_key.rsplit(":", 1)[-1]
    return cache_dir / f"baseline-{digest}.json"


def _read_cached_baseline_suite(
    cache_dir: Path,
    cache_key: str,
) -> tuple[HistoricalRecommendationBacktestSuiteResult | None, str | None]:
    cache_path = _baseline_cache_path(cache_dir, cache_key)
    if not cache_path.exists():
        return None, None
    try:
        return (
            HistoricalRecommendationBacktestSuiteResult.model_validate_json(
                cache_path.read_text(encoding="utf-8")
            ),
            None,
        )
    except Exception as exc:
        return None, f"{cache_key}:baseline_cache_read_failed:{exc}"


def _write_cached_baseline_suite(
    cache_dir: Path,
    cache_key: str,
    suite: HistoricalRecommendationBacktestSuiteResult,
) -> str | None:
    cache_path = _baseline_cache_path(cache_dir, cache_key)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            f"{suite.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
    except Exception as exc:
        return f"{cache_key}:baseline_cache_write_failed:{exc}"
    return None


def _candidate_cache_for_specs(
    candidates: Sequence[HistoricalFinalAnswerSegmentPenaltyCandidate],
    specs: Sequence[_GridCandidateSpec],
) -> dict[int, HistoricalFinalAnswerSegmentPenaltyCandidate]:
    spec_by_index = {spec.candidate_index: spec for spec in specs}
    cache: dict[int, HistoricalFinalAnswerSegmentPenaltyCandidate] = {}
    for candidate in candidates:
        spec = spec_by_index.get(candidate.candidate_index)
        if spec is None or not _candidate_matches_spec(candidate, spec):
            continue
        cache[candidate.candidate_index] = candidate
    return cache


def _candidate_matches_spec(
    candidate: HistoricalFinalAnswerSegmentPenaltyCandidate,
    spec: _GridCandidateSpec,
) -> bool:
    return (
        candidate.pass_types == spec.pass_types
        and candidate.modes == spec.modes
        and candidate.competition_ids == spec.competition_ids
        and candidate.season_ids == spec.season_ids
        and candidate.min_competition_season_index
        == spec.min_competition_season_index
        and candidate.max_competition_season_index
        == spec.max_competition_season_index
        and candidate.min_hit_probability == spec.min_hit_probability
        and candidate.max_hit_probability == spec.max_hit_probability
        and candidate.min_odds_product == spec.min_odds_product
        and candidate.max_odds_product == spec.max_odds_product
        and candidate.min_average_leg_decimal_odds
        == spec.min_average_leg_decimal_odds
        and candidate.max_average_leg_decimal_odds
        == spec.max_average_leg_decimal_odds
        and candidate.strength == spec.strength
    )


def _append_candidate_checkpoint(
    path: Path | None,
    candidate: HistoricalFinalAnswerSegmentPenaltyCandidate,
) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{candidate.model_dump_json()}\n")


def _string_groups_from_args(
    values: Sequence[str],
    *,
    default: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    if not values:
        return default
    return tuple(_string_group(value) for value in values)


def _string_group(value: str) -> tuple[str, ...]:
    items = _csv(value)
    if len(items) == 1 and items[0].lower() in {"all", "none", "null", "-"}:
        return ()
    return tuple(items)


def _mode_groups_from_args(
    values: Sequence[str],
    *,
    default: tuple[tuple[RecommendationMode, ...], ...],
) -> tuple[tuple[RecommendationMode, ...], ...]:
    if not values:
        return default
    return tuple(
        tuple(cast(RecommendationMode, mode) for mode in _csv(value))
        for value in values
    )


def _float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in _csv(value))


def _optional_float_tuple(value: str) -> tuple[float | None, ...]:
    parsed: list[float | None] = []
    for item in _csv(value):
        if item.lower() in {"none", "null", "-"}:
            parsed.append(None)
        else:
            parsed.append(float(item))
    return tuple(parsed) or (None,)


def _optional_int_tuple(value: str) -> tuple[int | None, ...]:
    parsed: list[int | None] = []
    for item in _csv(value):
        if item.lower() in {"none", "null", "-"}:
            parsed.append(None)
        else:
            parsed.append(int(item))
    return tuple(parsed) or (None,)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _valid_min_max(
    minimum: float | None,
    maximum: float | None,
) -> bool:
    return minimum is None or maximum is None or minimum < maximum


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


def _delta_number(deltas: Mapping[str, object], key: str) -> float | None:
    value = deltas.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _delta_int(deltas: Mapping[str, object], key: str) -> int:
    value = deltas.get(key, 0)
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


def _bucket_int(bucket: Mapping[str, object], field_name: str) -> int:
    value = bucket[field_name]
    if isinstance(value, int):
        return value
    return int(cast(float, value))


def _candidate_key(summary: Mapping[str, object]) -> str:
    digest = sha256(
        dumps(summary, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_segment_penalty_candidate:{digest}"


def _report_key(
    summary: Mapping[str, object],
    candidates: Sequence[HistoricalFinalAnswerSegmentPenaltyCandidate],
) -> str:
    payload = {
        "summary": summary,
        "candidates": [
            {
                "candidate_key": candidate.candidate_key,
                "status": candidate.status,
                "deltas": candidate.deltas_json,
                "penalty_option_count": candidate.penalty_option_count,
            }
            for candidate in candidates
        ],
    }
    digest = sha256(
        dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_segment_penalty_grid:{digest}"


if __name__ == "__main__":
    main()
