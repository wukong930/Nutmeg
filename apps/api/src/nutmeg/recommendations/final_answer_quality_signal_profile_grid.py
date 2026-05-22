from __future__ import annotations

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from json import dumps
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
    HistoricalFinalAnswerStakeEfficiencyScope,
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestComparisonResult,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
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

type HistoricalFinalAnswerQualitySignalProfileGridStatus = Literal["generated"]
type HistoricalFinalAnswerQualitySignalProfileCandidateStatus = Literal[
    "accepted",
    "rejected",
]
type HistoricalFinalAnswerQualitySignalProfileCacheStatus = Literal[
    "disabled",
    "hit",
    "miss",
]
type HistoricalFinalAnswerQualitySignalProfileComparisonItemFilter = Literal[
    "harmed",
    "changed",
    "all",
]


class HistoricalFinalAnswerQualitySignalProfileGridOptions(BaseModel):
    backtest_options: HistoricalRecommendationBacktestOptions = Field(
        default_factory=HistoricalRecommendationBacktestOptions
    )
    competition_groups: tuple[tuple[str, ...], ...] = ((),)
    probability_min_values: tuple[float, ...] = (0.65,)
    probability_max_values: tuple[float, ...] = (0.80,)
    min_decimal_odds_values: tuple[float, ...] = (1.0,)
    max_decimal_odds_values: tuple[float, ...] = (1.35,)
    max_model_edge_values: tuple[float, ...] = (0.0,)
    score_min_values: tuple[float, ...] = (0.0,)
    score_max_values: tuple[float, ...] = (1.0,)
    strength_values: tuple[float, ...] = (0.04,)
    baseline_optimizer_profile: HistoricalOptimizerProfile = "heuristic"
    candidate_optimizer_profile: HistoricalOptimizerProfile = "solver"
    fail_on_suite_statuses: tuple[str, ...] = ("regressed", "mixed")
    min_affected_leg_count: int = Field(default=1, ge=0)
    min_final_hit_count_delta: int = 0
    min_final_hit_rate_delta: float = 0.0
    min_roi_delta: float = 0.0
    min_profit_loss_delta: float = 0.0
    max_final_hit_harm_count_vs_baseline: int | None = Field(default=0, ge=0)
    max_profit_loss_harm_count_vs_baseline: int | None = Field(default=0, ge=0)
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_mean_calibration_error_delta: float = 0.0
    min_upset_capture_rate_delta: float = 0.0
    min_candidate_roi: float | None = None
    watchlist_max_candidate_roi_shortfall: float | None = Field(default=None, ge=0.0)
    watchlist_min_final_hit_count_delta: int = 0
    watchlist_min_roi_delta: float = 0.0
    watchlist_min_profit_loss_delta: float = 0.0
    watchlist_max_final_hit_harm_count_vs_baseline: int | None = Field(default=0, ge=0)
    watchlist_max_profit_loss_harm_count_vs_baseline: int | None = Field(default=0, ge=0)
    require_objective_improvement: bool = True
    min_objective_roi_delta: float = 0.0
    min_objective_upset_capture_rate_delta: float = 0.0
    comparison_epsilon: float = Field(default=1e-12, ge=0.0)
    candidate_start_index: int = Field(default=0, ge=0)
    candidate_limit: int | None = Field(default=None, ge=1)
    candidate_indices: tuple[int, ...] = ()
    candidate_cache_dir: Path | None = None
    read_candidate_cache: bool = True
    write_candidate_cache: bool = True
    baseline_cache_dir: Path | None = None
    read_baseline_cache: bool = True
    write_baseline_cache: bool = True
    progress_jsonl_path: Path | None = None
    include_comparison_items: bool = False
    comparison_item_filter: HistoricalFinalAnswerQualitySignalProfileComparisonItemFilter = (
        "harmed"
    )
    comparison_item_limit: int | None = Field(default=50, ge=1)


class HistoricalFinalAnswerQualitySignalProfileComparisonItem(BaseModel):
    slice_id: str
    competition_id: str
    season: str | None = None
    baseline_backtest_key: str
    candidate_backtest_key: str
    baseline_final_answer_scenario_key: str | None = None
    candidate_final_answer_scenario_key: str | None = None
    baseline_selected_fixture_ids: list[str] = Field(default_factory=list)
    candidate_selected_fixture_ids: list[str] = Field(default_factory=list)
    baseline_selected_outcomes: dict[str, list[str]] = Field(default_factory=dict)
    candidate_selected_outcomes: dict[str, list[str]] = Field(default_factory=dict)
    final_answer_changed: bool = False
    affected_leg_count: int = Field(default=0, ge=0)
    baseline_actual_hit: bool = False
    candidate_actual_hit: bool = False
    final_hit_harmed_vs_baseline: bool = False
    baseline_profit_loss: float
    candidate_profit_loss: float
    profit_loss_delta: float
    profit_loss_harmed_vs_baseline: bool = False
    baseline_expected_hit_probability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    candidate_expected_hit_probability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    reason_codes: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalFinalAnswerQualitySignalProfileCandidate(BaseModel):
    candidate_key: str
    candidate_index: int = Field(default=0, ge=0)
    candidate_cache_key: str | None = None
    candidate_cache_status: HistoricalFinalAnswerQualitySignalProfileCacheStatus = "disabled"
    status: HistoricalFinalAnswerQualitySignalProfileCandidateStatus
    competition_ids: tuple[str, ...] = ()
    probability_min: float
    probability_max: float
    min_decimal_odds: float = 1.0
    max_decimal_odds: float
    max_model_edge: float
    score_min: float = 0.0
    score_max: float = 1.0
    strength: float
    suite_key: str
    suite_status: str
    affected_leg_count: int = Field(ge=0)
    final_hit_sample_size: int = Field(ge=0)
    final_hit_count: int = Field(ge=0)
    final_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    roi: float | None = None
    profit_loss: float
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    mean_calibration_error: float | None = Field(default=None, ge=0.0)
    upset_capture_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    final_answer_changed_count: int = Field(default=0, ge=0)
    final_answer_changed_count_vs_baseline: int = Field(default=0, ge=0)
    final_hit_harm_count_vs_baseline: int = Field(default=0, ge=0)
    profit_loss_harm_count_vs_baseline: int = Field(default=0, ge=0)
    comparison_item_count: int = Field(default=0, ge=0)
    comparison_items: list[HistoricalFinalAnswerQualitySignalProfileComparisonItem] = (
        Field(default_factory=list)
    )
    objective_improvement_satisfied: bool = False
    objective_improvement_metric_codes: list[str] = Field(default_factory=list)
    deltas_json: dict[str, object] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)
    watchlist_eligible: bool = False
    watchlist_reason_codes: list[str] = Field(default_factory=list)
    evaluation_elapsed_seconds: float | None = Field(default=None, ge=0.0)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalFinalAnswerQualitySignalProfileGridReport(BaseModel):
    report_key: str
    status: HistoricalFinalAnswerQualitySignalProfileGridStatus
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    prediction_count: int = Field(ge=0)
    total_grid_candidate_count: int = Field(default=0, ge=0)
    candidate_start_index: int = Field(default=0, ge=0)
    candidate_limit: int | None = Field(default=None, ge=1)
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    watchlist_count: int = Field(default=0, ge=0)
    cache_hit_count: int = Field(default=0, ge=0)
    cache_miss_count: int = Field(default=0, ge=0)
    cache_write_count: int = Field(default=0, ge=0)
    baseline_evaluation_elapsed_seconds: float = Field(default=0.0, ge=0.0)
    candidate_evaluation_elapsed_seconds: float = Field(default=0.0, ge=0.0)
    grid_evaluation_elapsed_seconds: float = Field(default=0.0, ge=0.0)
    progress_event_count: int = Field(default=0, ge=0)
    baseline_cache_key: str | None = None
    baseline_cache_status: HistoricalFinalAnswerQualitySignalProfileCacheStatus = "disabled"
    baseline_cache_written: bool = False
    baseline_suite_key: str
    baseline_suite_status: str
    baseline_summary_json: dict[str, object] = Field(default_factory=dict)
    candidates: list[HistoricalFinalAnswerQualitySignalProfileCandidate] = Field(
        default_factory=list
    )
    accepted_candidates: list[HistoricalFinalAnswerQualitySignalProfileCandidate] = Field(
        default_factory=list
    )
    watchlist_candidates: list[HistoricalFinalAnswerQualitySignalProfileCandidate] = Field(
        default_factory=list
    )
    best_candidate: HistoricalFinalAnswerQualitySignalProfileCandidate | None = None
    best_watchlist_candidate: HistoricalFinalAnswerQualitySignalProfileCandidate | None = None
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
    competition_ids: tuple[str, ...] = ()
    probability_min: float
    probability_max: float
    min_decimal_odds: float = 1.0
    max_decimal_odds: float
    max_model_edge: float
    score_min: float
    score_max: float
    strength: float


@dataclass(frozen=True)
class _GridCandidateEvaluationResult:
    candidate: HistoricalFinalAnswerQualitySignalProfileCandidate
    cache_status: HistoricalFinalAnswerQualitySignalProfileCacheStatus
    cache_written: bool
    elapsed_seconds: float = 0.0
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _BaselineSuiteLoadResult:
    suite: HistoricalRecommendationBacktestSuiteResult
    cache_key: str | None
    cache_status: HistoricalFinalAnswerQualitySignalProfileCacheStatus
    cache_written: bool
    warnings: tuple[str, ...] = ()


class _QualitySignalProfileProgressJsonlWriter:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.event_count = 0
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def write(self, event: str, payload: Mapping[str, object]) -> None:
        if self.path is None:
            return
        self.event_count += 1
        event_payload: dict[str, object] = {
            "calculation_basis": (
                "historical_final_answer_quality_signal_profile_grid_progress_v3_1"
            ),
            "event": event,
            **dict(payload),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"{dumps(event_payload, sort_keys=True, default=str, ensure_ascii=False)}\n"
            )


def build_historical_final_answer_quality_signal_profile_grid_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalFinalAnswerQualitySignalProfileGridOptions | None = None,
) -> HistoricalFinalAnswerQualitySignalProfileGridReport:
    grid_started_at = perf_counter()
    resolved_options = options or HistoricalFinalAnswerQualitySignalProfileGridOptions()
    all_specs = _grid_candidate_specs(resolved_options)
    selected_specs = _selected_grid_candidate_specs(all_specs, resolved_options)
    progress_writer = _QualitySignalProfileProgressJsonlWriter(
        resolved_options.progress_jsonl_path
    )
    progress_writer.write(
        "grid_started",
        {
            "slice_count": len(historical_slices),
            "total_grid_candidate_count": len(all_specs),
            "selected_candidate_count": len(selected_specs),
            "candidate_start_index": resolved_options.candidate_start_index,
            "candidate_limit": resolved_options.candidate_limit,
            "candidate_indices": [spec.candidate_index for spec in selected_specs],
        },
    )
    baseline_started_at = perf_counter()
    baseline_result = _load_or_run_baseline_suite(
        historical_slices,
        options=resolved_options,
    )
    baseline_elapsed_seconds = _elapsed_seconds(baseline_started_at)
    baseline_suite = baseline_result.suite
    progress_writer.write(
        "baseline_completed",
        {
            "baseline_suite_key": baseline_suite.suite_key,
            "baseline_suite_status": baseline_suite.status,
            "baseline_cache_key": baseline_result.cache_key,
            "baseline_cache_status": baseline_result.cache_status,
            "baseline_cache_written": baseline_result.cache_written,
            "elapsed_seconds": baseline_elapsed_seconds,
        },
    )
    results: list[_GridCandidateEvaluationResult] = []
    for candidate_position, spec in enumerate(selected_specs):
        progress_writer.write(
            "candidate_started",
            {
                "candidate_position": candidate_position,
                "selected_candidate_count": len(selected_specs),
                "candidate_index": spec.candidate_index,
                "competition_ids": list(spec.competition_ids),
                "probability_min": spec.probability_min,
                "probability_max": spec.probability_max,
                "min_decimal_odds": spec.min_decimal_odds,
                "max_decimal_odds": spec.max_decimal_odds,
                "max_model_edge": spec.max_model_edge,
                "score_min": spec.score_min,
                "score_max": spec.score_max,
                "strength": spec.strength,
            },
        )
        result = _evaluate_or_load_profile_candidate(
            historical_slices,
            baseline_suite=baseline_suite,
            options=resolved_options,
            spec=spec,
        )
        results.append(result)
        progress_writer.write(
            "candidate_completed",
            {
                "candidate_position": candidate_position,
                "selected_candidate_count": len(selected_specs),
                "candidate_index": result.candidate.candidate_index,
                "candidate_key": result.candidate.candidate_key,
                "candidate_cache_key": result.candidate.candidate_cache_key,
                "candidate_cache_status": result.cache_status,
                "candidate_cache_written": result.cache_written,
                "status": result.candidate.status,
                "watchlist_eligible": result.candidate.watchlist_eligible,
                "reason_codes": result.candidate.reason_codes,
                "watchlist_reason_codes": result.candidate.watchlist_reason_codes,
                "elapsed_seconds": result.elapsed_seconds,
            },
        )
    candidates = [result.candidate for result in results]
    cache_hit_count = sum(1 for result in results if result.cache_status == "hit")
    cache_miss_count = sum(1 for result in results if result.cache_status == "miss")
    cache_write_count = sum(1 for result in results if result.cache_written)
    candidate_elapsed_seconds = _rounded_sum(result.elapsed_seconds for result in results)
    slowest_candidate_result = max(
        results,
        key=lambda result: result.elapsed_seconds,
        default=None,
    )
    accepted_candidates = [candidate for candidate in candidates if candidate.status == "accepted"]
    watchlist_candidates = [
        candidate for candidate in candidates if candidate.watchlist_eligible
    ]
    best_candidate = _best_candidate(accepted_candidates or candidates)
    best_watchlist_candidate = _best_candidate(watchlist_candidates)
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    prediction_count = sum(
        len(fixture.predictions)
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
    )
    warnings = [*baseline_suite.warnings, *baseline_result.warnings]
    warnings.extend(warning for result in results for warning in result.warnings)
    for candidate in candidates:
        if candidate.suite_status in resolved_options.fail_on_suite_statuses:
            warnings.append(
                f"quality_signal_profile:candidate_suite_status:{candidate.suite_status}"
            )
    rejection_reason_counts = _rejection_reason_counts(candidates)
    competition_summary = _competition_summary(candidates)
    candidate_indices = [candidate.candidate_index for candidate in candidates]
    selected_candidate_index_set = set(candidate_indices)
    missing_candidate_indices = _missing_candidate_indices(
        candidate_indices,
        len(all_specs),
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_final_answer_quality_signal_profile_grid_v3_1",
        "slice_count": len(historical_slices),
        "fixture_count": fixture_count,
        "prediction_count": prediction_count,
        "total_grid_candidate_count": len(all_specs),
        "candidate_selection_mode": (
            "explicit_indices" if resolved_options.candidate_indices else "range"
        ),
        "requested_candidate_indices": list(resolved_options.candidate_indices),
        "unmatched_requested_candidate_indices": [
            candidate_index
            for candidate_index in resolved_options.candidate_indices
            if candidate_index not in selected_candidate_index_set
        ],
        "candidate_start_index": resolved_options.candidate_start_index,
        "candidate_limit": resolved_options.candidate_limit,
        "candidate_indices": candidate_indices,
        "missing_candidate_indices": missing_candidate_indices,
        "next_candidate_start_index": (
            max(candidate_indices) + 1
            if candidate_indices and max(candidate_indices) + 1 < len(all_specs)
            else None
        ),
        "is_full_grid": bool(all_specs) and not missing_candidate_indices,
        "candidate_count": len(candidates),
        "accepted_count": len(accepted_candidates),
        "rejected_count": len(candidates) - len(accepted_candidates),
        "watchlist_count": len(watchlist_candidates),
        "cache_hit_count": cache_hit_count,
        "cache_miss_count": cache_miss_count,
        "cache_write_count": cache_write_count,
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
        "candidate_cache_dir": (
            str(resolved_options.candidate_cache_dir)
            if resolved_options.candidate_cache_dir is not None
            else None
        ),
        "read_candidate_cache": resolved_options.read_candidate_cache,
        "write_candidate_cache": resolved_options.write_candidate_cache,
        "include_comparison_items": resolved_options.include_comparison_items,
        "comparison_item_filter": resolved_options.comparison_item_filter,
        "comparison_item_limit": resolved_options.comparison_item_limit,
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
        "min_candidate_roi": resolved_options.min_candidate_roi,
        "watchlist_enabled": (
            resolved_options.watchlist_max_candidate_roi_shortfall is not None
        ),
        "watchlist_max_candidate_roi_shortfall": (
            resolved_options.watchlist_max_candidate_roi_shortfall
        ),
        "watchlist_min_final_hit_count_delta": (
            resolved_options.watchlist_min_final_hit_count_delta
        ),
        "watchlist_min_roi_delta": resolved_options.watchlist_min_roi_delta,
        "watchlist_min_profit_loss_delta": (
            resolved_options.watchlist_min_profit_loss_delta
        ),
        "watchlist_max_final_hit_harm_count_vs_baseline": (
            resolved_options.watchlist_max_final_hit_harm_count_vs_baseline
        ),
        "watchlist_max_profit_loss_harm_count_vs_baseline": (
            resolved_options.watchlist_max_profit_loss_harm_count_vs_baseline
        ),
        "max_final_hit_harm_count_vs_baseline": (
            resolved_options.max_final_hit_harm_count_vs_baseline
        ),
        "max_profit_loss_harm_count_vs_baseline": (
            resolved_options.max_profit_loss_harm_count_vs_baseline
        ),
        "require_objective_improvement": (resolved_options.require_objective_improvement),
        "min_objective_roi_delta": resolved_options.min_objective_roi_delta,
        "min_objective_upset_capture_rate_delta": (
            resolved_options.min_objective_upset_capture_rate_delta
        ),
        "comparison_epsilon": resolved_options.comparison_epsilon,
        "best_candidate_key": best_candidate.candidate_key if best_candidate is not None else None,
        "best_candidate_status": best_candidate.status if best_candidate is not None else None,
        "best_candidate_deltas": best_candidate.deltas_json if best_candidate is not None else {},
        "best_watchlist_candidate_key": (
            best_watchlist_candidate.candidate_key
            if best_watchlist_candidate is not None
            else None
        ),
        "best_watchlist_candidate_deltas": (
            best_watchlist_candidate.deltas_json
            if best_watchlist_candidate is not None
            else {}
        ),
        "accepted_candidate_keys": [candidate.candidate_key for candidate in accepted_candidates],
        "watchlist_candidate_keys": [
            candidate.candidate_key for candidate in watchlist_candidates
        ],
        "rejection_reason_counts": rejection_reason_counts,
        "competition_summary": competition_summary,
        "grid": _grid_summary(resolved_options),
        "warnings": warnings,
    }
    report_key = _report_key(summary, historical_slices)
    grid_elapsed_seconds = _elapsed_seconds(grid_started_at)
    progress_writer.write(
        "grid_completed",
        {
            "report_key": report_key,
            "candidate_count": len(candidates),
            "accepted_count": len(accepted_candidates),
            "rejected_count": len(candidates) - len(accepted_candidates),
            "watchlist_count": len(watchlist_candidates),
            "cache_hit_count": cache_hit_count,
            "cache_miss_count": cache_miss_count,
            "cache_write_count": cache_write_count,
            "baseline_evaluation_elapsed_seconds": baseline_elapsed_seconds,
            "candidate_evaluation_elapsed_seconds": candidate_elapsed_seconds,
            "grid_evaluation_elapsed_seconds": grid_elapsed_seconds,
        },
    )
    runtime_summary: dict[str, object] = {
        "baseline_evaluation_elapsed_seconds": baseline_elapsed_seconds,
        "candidate_evaluation_elapsed_seconds": candidate_elapsed_seconds,
        "grid_evaluation_elapsed_seconds": grid_elapsed_seconds,
        "progress_jsonl_path": (
            str(resolved_options.progress_jsonl_path)
            if resolved_options.progress_jsonl_path is not None
            else None
        ),
        "candidate_evaluation_elapsed_seconds_by_index": {
            str(result.candidate.candidate_index): result.elapsed_seconds
            for result in results
        },
        "slowest_candidate_index": (
            slowest_candidate_result.candidate.candidate_index
            if slowest_candidate_result is not None
            else None
        ),
        "slowest_candidate_elapsed_seconds": (
            slowest_candidate_result.elapsed_seconds
            if slowest_candidate_result is not None
            else None
        ),
        "progress_event_count": progress_writer.event_count,
    }
    return HistoricalFinalAnswerQualitySignalProfileGridReport(
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
        watchlist_count=len(watchlist_candidates),
        cache_hit_count=cache_hit_count,
        cache_miss_count=cache_miss_count,
        cache_write_count=cache_write_count,
        baseline_evaluation_elapsed_seconds=baseline_elapsed_seconds,
        candidate_evaluation_elapsed_seconds=candidate_elapsed_seconds,
        grid_evaluation_elapsed_seconds=grid_elapsed_seconds,
        progress_event_count=progress_writer.event_count,
        baseline_cache_key=baseline_result.cache_key,
        baseline_cache_status=baseline_result.cache_status,
        baseline_cache_written=baseline_result.cache_written,
        baseline_suite_key=baseline_suite.suite_key,
        baseline_suite_status=baseline_suite.status,
        baseline_summary_json=baseline_suite.summary_json,
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        watchlist_candidates=watchlist_candidates,
        best_candidate=best_candidate,
        best_watchlist_candidate=best_watchlist_candidate,
        warnings=warnings,
        summary_json={**summary, **runtime_summary, "report_key": report_key},
    )


def merge_historical_final_answer_quality_signal_profile_grid_reports(
    reports: Sequence[HistoricalFinalAnswerQualitySignalProfileGridReport],
    *,
    source_paths: Sequence[Path] = (),
) -> HistoricalFinalAnswerQualitySignalProfileGridReport:
    if not reports:
        raise ValueError("Provide at least one quality-signal profile grid report to merge")
    candidates = sorted(
        [candidate for report in reports for candidate in report.candidates],
        key=lambda candidate: (candidate.candidate_index, candidate.candidate_key),
    )
    accepted_candidates = [candidate for candidate in candidates if candidate.status == "accepted"]
    watchlist_candidates = [
        candidate for candidate in candidates if candidate.watchlist_eligible
    ]
    best_candidate = _best_candidate(accepted_candidates or candidates)
    best_watchlist_candidate = _best_candidate(watchlist_candidates)
    warnings = [warning for report in reports for warning in report.warnings]
    warnings.extend(_merge_warnings(reports, candidates))
    total_grid_candidate_count = _merged_total_grid_candidate_count(reports)
    candidate_indices = [candidate.candidate_index for candidate in candidates]
    candidate_start_index = min(candidate_indices) if candidate_indices else 0
    cache_hit_count = sum(report.cache_hit_count for report in reports)
    cache_miss_count = sum(report.cache_miss_count for report in reports)
    cache_write_count = sum(report.cache_write_count for report in reports)
    baseline_elapsed_seconds = _rounded_sum(
        report.baseline_evaluation_elapsed_seconds for report in reports
    )
    candidate_elapsed_seconds = _rounded_sum(
        report.candidate_evaluation_elapsed_seconds for report in reports
    )
    grid_elapsed_seconds = _rounded_sum(
        report.grid_evaluation_elapsed_seconds for report in reports
    )
    progress_event_count = sum(report.progress_event_count for report in reports)
    rejection_reason_counts = _rejection_reason_counts(candidates)
    competition_summary = _competition_summary(candidates)
    first_report = reports[0]
    summary: dict[str, object] = {
        "calculation_basis": ("historical_final_answer_quality_signal_profile_grid_merged_v3_1"),
        "source_report_count": len(reports),
        "source_report_keys": [report.report_key for report in reports],
        "source_report_paths": [str(path) for path in source_paths],
        "slice_count": first_report.slice_count,
        "fixture_count": first_report.fixture_count,
        "prediction_count": first_report.prediction_count,
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
        "watchlist_count": len(watchlist_candidates),
        "watchlist_enabled": any(
            report.summary_json.get("watchlist_enabled") is True for report in reports
        ),
        "cache_hit_count": cache_hit_count,
        "cache_miss_count": cache_miss_count,
        "cache_write_count": cache_write_count,
        "baseline_cache_status": None,
        "baseline_cache_written": None,
        "baseline_cache_key": None,
        "baseline_suite_key": first_report.baseline_suite_key,
        "baseline_suite_status": first_report.baseline_suite_status,
        "baseline_candidate_final_hit_rate": first_report.summary_json.get(
            "baseline_candidate_final_hit_rate"
        ),
        "baseline_candidate_roi": first_report.summary_json.get("baseline_candidate_roi"),
        "baseline_candidate_profit_loss": first_report.summary_json.get(
            "baseline_candidate_profit_loss"
        ),
        "include_comparison_items": any(
            report.summary_json.get("include_comparison_items") is True
            for report in reports
        ),
        "comparison_item_filter": first_report.summary_json.get("comparison_item_filter"),
        "comparison_item_limit": first_report.summary_json.get("comparison_item_limit"),
        "grid": _merged_grid_summary(reports),
        "best_candidate_key": best_candidate.candidate_key if best_candidate is not None else None,
        "best_candidate_status": best_candidate.status if best_candidate is not None else None,
        "best_candidate_deltas": best_candidate.deltas_json if best_candidate is not None else {},
        "best_watchlist_candidate_key": (
            best_watchlist_candidate.candidate_key
            if best_watchlist_candidate is not None
            else None
        ),
        "best_watchlist_candidate_deltas": (
            best_watchlist_candidate.deltas_json
            if best_watchlist_candidate is not None
            else {}
        ),
        "accepted_candidate_keys": [candidate.candidate_key for candidate in accepted_candidates],
        "watchlist_candidate_keys": [
            candidate.candidate_key for candidate in watchlist_candidates
        ],
        "rejection_reason_counts": rejection_reason_counts,
        "competition_summary": competition_summary,
        "warnings": warnings,
    }
    report_key = _report_key(summary, candidates)
    runtime_summary: dict[str, object] = {
        "baseline_evaluation_elapsed_seconds": baseline_elapsed_seconds,
        "candidate_evaluation_elapsed_seconds": candidate_elapsed_seconds,
        "grid_evaluation_elapsed_seconds": grid_elapsed_seconds,
        "progress_event_count": progress_event_count,
    }
    return HistoricalFinalAnswerQualitySignalProfileGridReport(
        report_key=report_key,
        status="generated",
        slice_count=first_report.slice_count,
        fixture_count=first_report.fixture_count,
        prediction_count=first_report.prediction_count,
        total_grid_candidate_count=total_grid_candidate_count,
        candidate_start_index=candidate_start_index,
        candidate_limit=len(candidates),
        candidate_count=len(candidates),
        accepted_count=len(accepted_candidates),
        rejected_count=len(candidates) - len(accepted_candidates),
        watchlist_count=len(watchlist_candidates),
        cache_hit_count=cache_hit_count,
        cache_miss_count=cache_miss_count,
        cache_write_count=cache_write_count,
        baseline_evaluation_elapsed_seconds=baseline_elapsed_seconds,
        candidate_evaluation_elapsed_seconds=candidate_elapsed_seconds,
        grid_evaluation_elapsed_seconds=grid_elapsed_seconds,
        progress_event_count=progress_event_count,
        baseline_cache_key=None,
        baseline_cache_status="disabled",
        baseline_cache_written=False,
        baseline_suite_key=first_report.baseline_suite_key,
        baseline_suite_status=first_report.baseline_suite_status,
        baseline_summary_json=first_report.baseline_summary_json,
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        watchlist_candidates=watchlist_candidates,
        best_candidate=best_candidate,
        best_watchlist_candidate=best_watchlist_candidate,
        warnings=warnings,
        summary_json={**summary, **runtime_summary, "report_key": report_key},
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_final_answer_quality_signal_profile_grid_report(
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


def merge_main(argv: Sequence[str] | None = None) -> None:
    args = _parse_merge_args(argv)
    reports = [
        HistoricalFinalAnswerQualitySignalProfileGridReport.model_validate_json(
            report_path.read_text(encoding="utf-8")
        )
        for report_path in args.report_paths
    ]
    report = merge_historical_final_answer_quality_signal_profile_grid_reports(
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


def _baseline_backtest_options(
    options: HistoricalRecommendationBacktestOptions,
) -> HistoricalRecommendationBacktestOptions:
    return options.model_copy(
        update={
            "final_answer_quality_signal_penalty": False,
            "final_answer_quality_signal_competition_ids": (),
        }
    )


def _load_or_run_baseline_suite(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalFinalAnswerQualitySignalProfileGridOptions,
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
    cache_status: HistoricalFinalAnswerQualitySignalProfileCacheStatus = (
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
    options: HistoricalFinalAnswerQualitySignalProfileGridOptions,
) -> list[_GridCandidateSpec]:
    specs: list[_GridCandidateSpec] = []
    candidate_index = 0
    for competition_ids in options.competition_groups:
        for probability_min in options.probability_min_values:
            for probability_max in options.probability_max_values:
                if probability_min >= probability_max:
                    continue
                for min_decimal_odds in options.min_decimal_odds_values:
                    for max_decimal_odds in options.max_decimal_odds_values:
                        if min_decimal_odds > max_decimal_odds:
                            continue
                        for max_model_edge in options.max_model_edge_values:
                            for score_min in options.score_min_values:
                                for score_max in options.score_max_values:
                                    if score_min > score_max:
                                        continue
                                    for strength in options.strength_values:
                                        specs.append(
                                            _GridCandidateSpec(
                                                candidate_index=candidate_index,
                                                competition_ids=competition_ids,
                                                probability_min=probability_min,
                                                probability_max=probability_max,
                                                min_decimal_odds=min_decimal_odds,
                                                max_decimal_odds=max_decimal_odds,
                                                max_model_edge=max_model_edge,
                                                score_min=score_min,
                                                score_max=score_max,
                                                strength=strength,
                                            )
                                        )
                                        candidate_index += 1
    return specs


def _selected_grid_candidate_specs(
    specs: Sequence[_GridCandidateSpec],
    options: HistoricalFinalAnswerQualitySignalProfileGridOptions,
) -> list[_GridCandidateSpec]:
    if options.candidate_indices:
        requested_indices = set(options.candidate_indices)
        return [
            spec
            for spec in specs
            if spec.candidate_index in requested_indices
        ]
    start_index = min(options.candidate_start_index, len(specs))
    if options.candidate_limit is None:
        return list(specs[start_index:])
    end_index = min(start_index + options.candidate_limit, len(specs))
    return list(specs[start_index:end_index])


def _elapsed_seconds(started_at: float) -> float:
    return round(max(perf_counter() - started_at, 0.0), 6)


def _rounded_sum(values: Iterable[float]) -> float:
    return round(sum(values), 6)


def _evaluate_or_load_profile_candidate(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    options: HistoricalFinalAnswerQualitySignalProfileGridOptions,
    spec: _GridCandidateSpec,
) -> _GridCandidateEvaluationResult:
    started_at = perf_counter()
    cache_key = _candidate_cache_key(
        options,
        spec,
        baseline_suite_key=baseline_suite.suite_key,
    )
    if options.candidate_cache_dir is not None and options.read_candidate_cache:
        cached_candidate, cache_warning = _read_cached_candidate(
            options.candidate_cache_dir,
            cache_key,
        )
        if cached_candidate is not None:
            elapsed_seconds = _elapsed_seconds(started_at)
            return _GridCandidateEvaluationResult(
                candidate=_candidate_with_evaluation_metadata(
                    _candidate_with_cache_metadata(
                        cached_candidate,
                        spec=spec,
                        cache_key=cache_key,
                        cache_status="hit",
                    ),
                    elapsed_seconds=elapsed_seconds,
                ),
                cache_status="hit",
                cache_written=False,
                elapsed_seconds=elapsed_seconds,
                warnings=(),
            )
        warnings: tuple[str, ...] = (cache_warning,) if cache_warning is not None else ()
    else:
        warnings = ()

    candidate = _evaluate_profile_candidate(
        historical_slices,
        baseline_suite=baseline_suite,
        options=options,
        competition_ids=spec.competition_ids,
        probability_min=spec.probability_min,
        probability_max=spec.probability_max,
        min_decimal_odds=spec.min_decimal_odds,
        max_decimal_odds=spec.max_decimal_odds,
        max_model_edge=spec.max_model_edge,
        score_min=spec.score_min,
        score_max=spec.score_max,
        strength=spec.strength,
    )
    cache_status: HistoricalFinalAnswerQualitySignalProfileCacheStatus = (
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
    elapsed_seconds = _elapsed_seconds(started_at)
    return _GridCandidateEvaluationResult(
        candidate=_candidate_with_evaluation_metadata(
            candidate,
            elapsed_seconds=elapsed_seconds,
        ),
        cache_status=cache_status,
        cache_written=cache_written,
        elapsed_seconds=elapsed_seconds,
        warnings=warnings,
    )


def _evaluate_profile_candidate(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    options: HistoricalFinalAnswerQualitySignalProfileGridOptions,
    competition_ids: tuple[str, ...],
    probability_min: float,
    probability_max: float,
    min_decimal_odds: float,
    max_decimal_odds: float,
    max_model_edge: float,
    score_min: float,
    score_max: float,
    strength: float,
) -> HistoricalFinalAnswerQualitySignalProfileCandidate:
    candidate_options = options.backtest_options.model_copy(
        update={
            "final_answer_quality_signal_penalty": True,
            "final_answer_quality_signal_penalty_strength": strength,
            "final_answer_quality_signal_probability_min": probability_min,
            "final_answer_quality_signal_probability_max": probability_max,
            "final_answer_quality_signal_min_decimal_odds": min_decimal_odds,
            "final_answer_quality_signal_max_decimal_odds": max_decimal_odds,
            "final_answer_quality_signal_max_model_edge": max_model_edge,
            "final_answer_quality_signal_score_min": score_min,
            "final_answer_quality_signal_score_max": score_max,
            "final_answer_quality_signal_competition_ids": competition_ids,
        }
    )
    suite = run_historical_recommendation_backtest_suite(
        historical_slices,
        options=candidate_options,
        baseline_optimizer_profile=options.baseline_optimizer_profile,
        candidate_optimizer_profile=options.candidate_optimizer_profile,
    )
    deltas = _suite_deltas(baseline_suite, suite)
    comparison_items = _quality_signal_profile_comparison_items(
        historical_slices,
        baseline_suite,
        suite,
        filter_mode=options.comparison_item_filter,
        limit=options.comparison_item_limit,
    ) if options.include_comparison_items else []
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
    status: HistoricalFinalAnswerQualitySignalProfileCandidateStatus = (
        "accepted" if not reason_codes else "rejected"
    )
    watchlist_reason_codes = (
        _watchlist_reason_codes(
            suite,
            deltas=deltas,
            rejection_reason_codes=reason_codes,
            options=options,
        )
        if reason_codes and options.watchlist_max_candidate_roi_shortfall is not None
        else []
    )
    watchlist_eligible = (
        bool(reason_codes)
        and options.watchlist_max_candidate_roi_shortfall is not None
        and not watchlist_reason_codes
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_final_answer_quality_signal_candidate_v3_1",
        "status": status,
        "competition_ids": list(competition_ids),
        "probability_min": probability_min,
        "probability_max": probability_max,
        "min_decimal_odds": min_decimal_odds,
        "max_decimal_odds": max_decimal_odds,
        "max_model_edge": max_model_edge,
        "score_min": score_min,
        "score_max": score_max,
        "strength": strength,
        "comparison_epsilon": options.comparison_epsilon,
        "require_objective_improvement": options.require_objective_improvement,
        "min_objective_roi_delta": options.min_objective_roi_delta,
        "min_objective_upset_capture_rate_delta": (options.min_objective_upset_capture_rate_delta),
        "min_candidate_roi": options.min_candidate_roi,
        "watchlist_enabled": options.watchlist_max_candidate_roi_shortfall is not None,
        "watchlist_max_candidate_roi_shortfall": (
            options.watchlist_max_candidate_roi_shortfall
        ),
        "watchlist_min_final_hit_count_delta": (
            options.watchlist_min_final_hit_count_delta
        ),
        "watchlist_min_roi_delta": options.watchlist_min_roi_delta,
        "watchlist_min_profit_loss_delta": options.watchlist_min_profit_loss_delta,
        "watchlist_max_final_hit_harm_count_vs_baseline": (
            options.watchlist_max_final_hit_harm_count_vs_baseline
        ),
        "watchlist_max_profit_loss_harm_count_vs_baseline": (
            options.watchlist_max_profit_loss_harm_count_vs_baseline
        ),
        "max_final_hit_harm_count_vs_baseline": (
            options.max_final_hit_harm_count_vs_baseline
        ),
        "max_profit_loss_harm_count_vs_baseline": (
            options.max_profit_loss_harm_count_vs_baseline
        ),
        "include_comparison_items": options.include_comparison_items,
        "comparison_item_filter": options.comparison_item_filter,
        "comparison_item_limit": options.comparison_item_limit,
        "comparison_item_count": len(comparison_items),
        "objective_improvement_satisfied": objective_improvement_satisfied,
        "objective_improvement_metric_codes": objective_metric_codes,
        "suite_key": suite.suite_key,
        "suite_status": suite.status,
        "affected_leg_count": _summary_int(
            suite.summary_json,
            "candidate_final_answer_quality_signal_affected_leg_count",
        ),
        "deltas": deltas,
        "reason_codes": reason_codes,
        "watchlist_eligible": watchlist_eligible,
        "watchlist_reason_codes": watchlist_reason_codes,
    }
    candidate_key = _candidate_key(summary)
    return HistoricalFinalAnswerQualitySignalProfileCandidate(
        candidate_key=candidate_key,
        status=status,
        competition_ids=competition_ids,
        probability_min=probability_min,
        probability_max=probability_max,
        min_decimal_odds=min_decimal_odds,
        max_decimal_odds=max_decimal_odds,
        max_model_edge=max_model_edge,
        score_min=score_min,
        score_max=score_max,
        strength=strength,
        suite_key=suite.suite_key,
        suite_status=suite.status,
        affected_leg_count=_summary_int(
            suite.summary_json,
            "candidate_final_answer_quality_signal_affected_leg_count",
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
        upset_capture_rate=_summary_number(
            suite.summary_json,
            "candidate_upset_capture_rate",
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
        comparison_item_count=len(comparison_items),
        comparison_items=comparison_items,
        objective_improvement_satisfied=objective_improvement_satisfied,
        objective_improvement_metric_codes=objective_metric_codes,
        deltas_json=deltas,
        reason_codes=reason_codes,
        watchlist_eligible=watchlist_eligible,
        watchlist_reason_codes=watchlist_reason_codes,
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
        "upset_capture_rate_delta": _optional_delta(
            _summary_number(candidate_suite.summary_json, "candidate_upset_capture_rate"),
            _summary_number(baseline_suite.summary_json, "candidate_upset_capture_rate"),
        ),
        "affected_leg_count": _summary_int(
            candidate_suite.summary_json,
            "candidate_final_answer_quality_signal_affected_leg_count",
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


def _quality_signal_profile_comparison_items(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    baseline_suite: HistoricalRecommendationBacktestSuiteResult,
    candidate_suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    filter_mode: HistoricalFinalAnswerQualitySignalProfileComparisonItemFilter,
    limit: int | None,
) -> list[HistoricalFinalAnswerQualitySignalProfileComparisonItem]:
    slice_by_id = {
        historical_slice.metadata.slice_id: historical_slice
        for historical_slice in historical_slices
    }
    items = [
        _quality_signal_profile_comparison_item(
            baseline_comparison,
            candidate_comparison,
            slice_by_id=slice_by_id,
        )
        for baseline_comparison, candidate_comparison in zip(
            baseline_suite.comparisons,
            candidate_suite.comparisons,
            strict=True,
        )
    ]
    filtered = [
        item
        for item in items
        if _include_quality_signal_profile_comparison_item(
            item,
            filter_mode=filter_mode,
        )
    ]
    filtered = sorted(filtered, key=_quality_signal_profile_comparison_item_sort_key)
    if limit is None:
        return filtered
    return filtered[:limit]


def _quality_signal_profile_comparison_item(
    baseline_comparison: HistoricalRecommendationBacktestComparisonResult,
    candidate_comparison: HistoricalRecommendationBacktestComparisonResult,
    *,
    slice_by_id: Mapping[str, HistoricalRecommendationSlice],
) -> HistoricalFinalAnswerQualitySignalProfileComparisonItem:
    baseline = baseline_comparison.candidate
    candidate = candidate_comparison.candidate
    historical_slice = slice_by_id.get(candidate.slice_id) or slice_by_id.get(
        baseline.slice_id
    )
    final_answer_changed = _final_answer_signature(
        baseline.final_answer
    ) != _final_answer_signature(candidate.final_answer)
    final_hit_harmed = candidate.final_hit_count < baseline.final_hit_count
    profit_loss_delta = candidate.profit_loss - baseline.profit_loss
    profit_loss_harmed = candidate.profit_loss < baseline.profit_loss
    affected_leg_count = _summary_int(
        candidate.summary_json,
        "final_answer_quality_signal_affected_leg_count",
    )
    reason_codes = _comparison_item_reason_codes(
        final_answer_changed=final_answer_changed,
        final_hit_harmed=final_hit_harmed,
        profit_loss_harmed=profit_loss_harmed,
        affected_leg_count=affected_leg_count,
    )
    return HistoricalFinalAnswerQualitySignalProfileComparisonItem(
        slice_id=candidate.slice_id,
        competition_id=(
            historical_slice.metadata.competition_id
            if historical_slice is not None
            else "unknown"
        ),
        season=historical_slice.metadata.season if historical_slice is not None else None,
        baseline_backtest_key=baseline.backtest_key,
        candidate_backtest_key=candidate.backtest_key,
        baseline_final_answer_scenario_key=_final_answer_scenario_key(baseline),
        candidate_final_answer_scenario_key=_final_answer_scenario_key(candidate),
        baseline_selected_fixture_ids=_final_answer_fixture_ids(baseline),
        candidate_selected_fixture_ids=_final_answer_fixture_ids(candidate),
        baseline_selected_outcomes=_final_answer_selected_outcomes(baseline),
        candidate_selected_outcomes=_final_answer_selected_outcomes(candidate),
        final_answer_changed=final_answer_changed,
        affected_leg_count=affected_leg_count,
        baseline_actual_hit=bool(baseline.final_answer and baseline.final_answer.actual_hit),
        candidate_actual_hit=bool(candidate.final_answer and candidate.final_answer.actual_hit),
        final_hit_harmed_vs_baseline=final_hit_harmed,
        baseline_profit_loss=baseline.profit_loss,
        candidate_profit_loss=candidate.profit_loss,
        profit_loss_delta=profit_loss_delta,
        profit_loss_harmed_vs_baseline=profit_loss_harmed,
        baseline_expected_hit_probability=_final_answer_expected_hit_probability(
            baseline
        ),
        candidate_expected_hit_probability=_final_answer_expected_hit_probability(
            candidate
        ),
        reason_codes=reason_codes,
        summary_json={
            "baseline_final_hit_count": baseline.final_hit_count,
            "candidate_final_hit_count": candidate.final_hit_count,
            "baseline_roi": baseline.roi,
            "candidate_roi": candidate.roi,
            "baseline_total_stake": baseline.total_stake,
            "candidate_total_stake": candidate.total_stake,
            "baseline_actual_return": baseline.actual_return,
            "candidate_actual_return": candidate.actual_return,
        },
    )


def _comparison_item_reason_codes(
    *,
    final_answer_changed: bool,
    final_hit_harmed: bool,
    profit_loss_harmed: bool,
    affected_leg_count: int,
) -> list[str]:
    reason_codes: list[str] = []
    if final_answer_changed:
        reason_codes.append("quality_signal_profile_item:final_answer_changed")
    if final_hit_harmed:
        reason_codes.append("quality_signal_profile_item:final_hit_harmed")
    if profit_loss_harmed:
        reason_codes.append("quality_signal_profile_item:profit_loss_harmed")
    if affected_leg_count > 0:
        reason_codes.append("quality_signal_profile_item:quality_signal_affected")
    return reason_codes


def _include_quality_signal_profile_comparison_item(
    item: HistoricalFinalAnswerQualitySignalProfileComparisonItem,
    *,
    filter_mode: HistoricalFinalAnswerQualitySignalProfileComparisonItemFilter,
) -> bool:
    if filter_mode == "all":
        return True
    if filter_mode == "changed":
        return (
            item.final_answer_changed
            or item.final_hit_harmed_vs_baseline
            or item.profit_loss_harmed_vs_baseline
        )
    return item.final_hit_harmed_vs_baseline or item.profit_loss_harmed_vs_baseline


def _quality_signal_profile_comparison_item_sort_key(
    item: HistoricalFinalAnswerQualitySignalProfileComparisonItem,
) -> tuple[int, int, float, int, str]:
    return (
        0 if item.final_hit_harmed_vs_baseline else 1,
        0 if item.profit_loss_harmed_vs_baseline else 1,
        item.profit_loss_delta,
        0 if item.final_answer_changed else 1,
        item.slice_id,
    )


def _final_answer_scenario_key(
    result: HistoricalRecommendationBacktestResult,
) -> str | None:
    if result.final_answer is None:
        return None
    return result.final_answer.scenario.scenario_key


def _final_answer_fixture_ids(
    result: HistoricalRecommendationBacktestResult,
) -> list[str]:
    if result.final_answer is None:
        return []
    return list(result.final_answer.selected_fixture_ids)


def _final_answer_selected_outcomes(
    result: HistoricalRecommendationBacktestResult,
) -> dict[str, list[str]]:
    if result.final_answer is None:
        return {}
    return {
        fixture_id: list(outcomes)
        for fixture_id, outcomes in result.final_answer.selected_outcomes.items()
    }


def _final_answer_expected_hit_probability(
    result: HistoricalRecommendationBacktestResult,
) -> float | None:
    if result.final_answer is None:
        return None
    return result.final_answer.expected_hit_probability


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
    options: HistoricalFinalAnswerQualitySignalProfileGridOptions,
) -> list[str]:
    reason_codes: list[str] = []
    if suite.status in options.fail_on_suite_statuses:
        reason_codes.append(f"quality_signal_profile:suite_status_{suite.status}")
    if _delta_int(deltas, "affected_leg_count") < options.min_affected_leg_count:
        reason_codes.append("quality_signal_profile:affected_leg_count_too_low")
    if _delta_int(deltas, "final_hit_count_delta") < options.min_final_hit_count_delta:
        reason_codes.append("quality_signal_profile:final_hit_count_regressed")
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="final_hit_rate_delta",
        threshold=options.min_final_hit_rate_delta,
        reason_code="quality_signal_profile:final_hit_rate_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="roi_delta",
        threshold=options.min_roi_delta,
        reason_code="quality_signal_profile:roi_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="profit_loss_delta",
        threshold=options.min_profit_loss_delta,
        reason_code="quality_signal_profile:profit_loss_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_optional_maximum_reason(
        reason_codes,
        deltas,
        key="final_hit_harm_count_vs_baseline",
        threshold=options.max_final_hit_harm_count_vs_baseline,
        reason_code="quality_signal_profile:final_hit_harm_count_above_threshold",
        epsilon=options.comparison_epsilon,
    )
    _append_optional_maximum_reason(
        reason_codes,
        deltas,
        key="profit_loss_harm_count_vs_baseline",
        threshold=options.max_profit_loss_harm_count_vs_baseline,
        reason_code="quality_signal_profile:profit_loss_harm_count_above_threshold",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="brier_score_delta",
        threshold=options.max_brier_score_delta,
        reason_code="quality_signal_profile:brier_score_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="log_loss_delta",
        threshold=options.max_log_loss_delta,
        reason_code="quality_signal_profile:log_loss_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_maximum_reason(
        reason_codes,
        deltas,
        key="mean_calibration_error_delta",
        threshold=options.max_mean_calibration_error_delta,
        reason_code="quality_signal_profile:mean_calibration_error_regressed",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="upset_capture_rate_delta",
        threshold=options.min_upset_capture_rate_delta,
        reason_code="quality_signal_profile:upset_capture_rate_regressed",
        epsilon=options.comparison_epsilon,
    )
    if options.min_candidate_roi is not None:
        candidate_roi = _summary_number(suite.summary_json, "candidate_roi")
        if (
            candidate_roi is None
            or candidate_roi + options.comparison_epsilon < options.min_candidate_roi
        ):
            reason_codes.append("quality_signal_profile:candidate_roi_below_floor")
    if not objective_improvement_satisfied:
        reason_codes.append("quality_signal_profile:objective_improvement_missing")
    return reason_codes


def _watchlist_reason_codes(
    suite: HistoricalRecommendationBacktestSuiteResult,
    *,
    deltas: Mapping[str, object],
    rejection_reason_codes: Sequence[str],
    options: HistoricalFinalAnswerQualitySignalProfileGridOptions,
) -> list[str]:
    reason_codes: list[str] = []
    blocking_rejection_reason_codes = [
        reason_code
        for reason_code in rejection_reason_codes
        if reason_code != "quality_signal_profile:candidate_roi_below_floor"
    ]
    if blocking_rejection_reason_codes:
        reason_codes.append("quality_signal_profile_watchlist:blocking_rejection_reasons_present")
    candidate_roi_floor = (
        options.min_candidate_roi if options.min_candidate_roi is not None else 0.0
    )
    candidate_roi = _summary_number(suite.summary_json, "candidate_roi")
    if candidate_roi is None:
        reason_codes.append("quality_signal_profile_watchlist:candidate_roi_missing")
    elif (
        options.watchlist_max_candidate_roi_shortfall is not None
        and candidate_roi_floor - candidate_roi
        > options.watchlist_max_candidate_roi_shortfall + options.comparison_epsilon
    ):
        reason_codes.append(
            "quality_signal_profile_watchlist:candidate_roi_shortfall_above_limit"
        )
    if _delta_int(deltas, "affected_leg_count") < options.min_affected_leg_count:
        reason_codes.append("quality_signal_profile_watchlist:affected_leg_count_too_low")
    if (
        _delta_int(deltas, "final_hit_count_delta")
        < options.watchlist_min_final_hit_count_delta
    ):
        reason_codes.append("quality_signal_profile_watchlist:final_hit_count_too_low")
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="roi_delta",
        threshold=options.watchlist_min_roi_delta,
        reason_code="quality_signal_profile_watchlist:roi_delta_too_low",
        epsilon=options.comparison_epsilon,
    )
    _append_minimum_reason(
        reason_codes,
        deltas,
        key="profit_loss_delta",
        threshold=options.watchlist_min_profit_loss_delta,
        reason_code="quality_signal_profile_watchlist:profit_loss_delta_too_low",
        epsilon=options.comparison_epsilon,
    )
    _append_optional_maximum_reason(
        reason_codes,
        deltas,
        key="final_hit_harm_count_vs_baseline",
        threshold=options.watchlist_max_final_hit_harm_count_vs_baseline,
        reason_code="quality_signal_profile_watchlist:final_hit_harm_count_above_threshold",
        epsilon=options.comparison_epsilon,
    )
    _append_optional_maximum_reason(
        reason_codes,
        deltas,
        key="profit_loss_harm_count_vs_baseline",
        threshold=options.watchlist_max_profit_loss_harm_count_vs_baseline,
        reason_code="quality_signal_profile_watchlist:profit_loss_harm_count_above_threshold",
        epsilon=options.comparison_epsilon,
    )
    return reason_codes


def _objective_improvement_metric_codes(
    deltas: Mapping[str, object],
    *,
    options: HistoricalFinalAnswerQualitySignalProfileGridOptions,
) -> list[str]:
    metric_codes: list[str] = []
    if _minimum_delta_exceeded(
        deltas,
        key="roi_delta",
        threshold=options.min_objective_roi_delta,
        epsilon=options.comparison_epsilon,
    ):
        metric_codes.append("roi_delta")
    if _minimum_delta_exceeded(
        deltas,
        key="upset_capture_rate_delta",
        threshold=options.min_objective_upset_capture_rate_delta,
        epsilon=options.comparison_epsilon,
    ):
        metric_codes.append("upset_capture_rate_delta")
    return metric_codes


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
    _append_maximum_reason(
        reason_codes,
        deltas,
        key=key,
        threshold=float(threshold),
        reason_code=reason_code,
        epsilon=epsilon,
    )


def _best_candidate(
    candidates: Sequence[HistoricalFinalAnswerQualitySignalProfileCandidate],
) -> HistoricalFinalAnswerQualitySignalProfileCandidate | None:
    if not candidates:
        return None
    return sorted(candidates, key=_candidate_sort_key, reverse=True)[0]


def _candidate_sort_key(
    candidate: HistoricalFinalAnswerQualitySignalProfileCandidate,
) -> tuple[int, float, float, float, float, int, str]:
    return (
        1 if candidate.status == "accepted" else 0,
        _delta_number(candidate.deltas_json, "roi_delta") or -999.0,
        _delta_number(candidate.deltas_json, "profit_loss_delta") or -999.0,
        _delta_number(candidate.deltas_json, "final_hit_rate_delta") or -999.0,
        -(_delta_number(candidate.deltas_json, "brier_score_delta") or 999.0),
        candidate.affected_leg_count,
        candidate.candidate_key,
    )


def _candidate_with_cache_metadata(
    candidate: HistoricalFinalAnswerQualitySignalProfileCandidate,
    *,
    spec: _GridCandidateSpec,
    cache_key: str,
    cache_status: HistoricalFinalAnswerQualitySignalProfileCacheStatus,
) -> HistoricalFinalAnswerQualitySignalProfileCandidate:
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


def _candidate_with_evaluation_metadata(
    candidate: HistoricalFinalAnswerQualitySignalProfileCandidate,
    *,
    elapsed_seconds: float,
) -> HistoricalFinalAnswerQualitySignalProfileCandidate:
    return candidate.model_copy(
        update={
            "evaluation_elapsed_seconds": elapsed_seconds,
            "summary_json": {
                **candidate.summary_json,
                "evaluation_elapsed_seconds": elapsed_seconds,
            },
        }
    )


def _candidate_cache_key(
    options: HistoricalFinalAnswerQualitySignalProfileGridOptions,
    spec: _GridCandidateSpec,
    *,
    baseline_suite_key: str,
) -> str:
    payload = {
        "calculation_basis": (
            "historical_final_answer_quality_signal_profile_candidate_cache_v3_1"
        ),
        "baseline_suite_key": baseline_suite_key,
        "spec": spec.model_dump(mode="json", exclude={"candidate_index"}),
        "options": options.model_dump(
            mode="json",
            exclude={
                "candidate_start_index",
                "candidate_limit",
                "candidate_indices",
                "candidate_cache_dir",
                "read_candidate_cache",
                "write_candidate_cache",
                "baseline_cache_dir",
                "read_baseline_cache",
                "write_baseline_cache",
                "progress_jsonl_path",
            },
        ),
    }
    digest = sha256(dumps(payload, sort_keys=True, default=str).encode("utf-8"))
    return (
        f"historical_final_answer_quality_signal_profile_candidate_cache:{digest.hexdigest()[:16]}"
    )


def _baseline_cache_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    options: HistoricalFinalAnswerQualitySignalProfileGridOptions,
) -> str:
    baseline_options = _baseline_backtest_options(options.backtest_options)
    payload = {
        "calculation_basis": "historical_final_answer_quality_signal_profile_baseline_cache_v3_1",
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
    return (
        f"historical_final_answer_quality_signal_profile_baseline_cache:{digest.hexdigest()[:16]}"
    )


def _candidate_cache_path(cache_dir: Path, cache_key: str) -> Path:
    digest = cache_key.rsplit(":", 1)[-1]
    return cache_dir / f"{digest}.json"


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


def _read_cached_candidate(
    cache_dir: Path,
    cache_key: str,
) -> tuple[HistoricalFinalAnswerQualitySignalProfileCandidate | None, str | None]:
    cache_path = _candidate_cache_path(cache_dir, cache_key)
    if not cache_path.exists():
        return None, None
    try:
        return (
            HistoricalFinalAnswerQualitySignalProfileCandidate.model_validate_json(
                cache_path.read_text(encoding="utf-8")
            ),
            None,
        )
    except Exception as exc:
        return None, f"{cache_key}:candidate_cache_read_failed:{exc}"


def _write_cached_candidate(
    cache_dir: Path,
    cache_key: str,
    candidate: HistoricalFinalAnswerQualitySignalProfileCandidate,
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
    candidates: Sequence[HistoricalFinalAnswerQualitySignalProfileCandidate],
) -> dict[str, int]:
    counter: Counter[str] = Counter(
        reason_code
        for candidate in candidates
        if candidate.status == "rejected"
        for reason_code in candidate.reason_codes
    )
    return dict(sorted(counter.items()))


def _competition_summary(
    candidates: Sequence[HistoricalFinalAnswerQualitySignalProfileCandidate],
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
                "watchlist_count": 0,
                "affected_leg_count": 0,
                "final_hit_count": 0,
                "final_answer_changed_count_vs_baseline": 0,
                "final_hit_harm_count_vs_baseline": 0,
                "profit_loss": 0.0,
                "profit_loss_harm_count_vs_baseline": 0,
                "rejection_reason_counts": {},
                "watchlist_reason_counts": {},
            },
        )
        bucket["candidate_count"] = _bucket_int(bucket, "candidate_count") + 1
        if candidate.status == "accepted":
            bucket["accepted_count"] = _bucket_int(bucket, "accepted_count") + 1
        else:
            bucket["rejected_count"] = _bucket_int(bucket, "rejected_count") + 1
        if candidate.watchlist_eligible:
            bucket["watchlist_count"] = _bucket_int(bucket, "watchlist_count") + 1
        _increment_int_bucket(bucket, "affected_leg_count", candidate.affected_leg_count)
        _increment_int_bucket(bucket, "final_hit_count", candidate.final_hit_count)
        _increment_int_bucket(
            bucket,
            "final_answer_changed_count_vs_baseline",
            candidate.final_answer_changed_count_vs_baseline,
        )
        _increment_int_bucket(
            bucket,
            "final_hit_harm_count_vs_baseline",
            candidate.final_hit_harm_count_vs_baseline,
        )
        bucket["profit_loss"] = _bucket_float(bucket, "profit_loss") + candidate.profit_loss
        _increment_int_bucket(
            bucket,
            "profit_loss_harm_count_vs_baseline",
            candidate.profit_loss_harm_count_vs_baseline,
        )
        _update_reason_bucket(
            bucket,
            "rejection_reason_counts",
            candidate.reason_codes if candidate.status == "rejected" else [],
        )
        _update_reason_bucket(
            bucket,
            "watchlist_reason_counts",
            candidate.watchlist_reason_codes,
        )
    return {
        key: {
            **bucket,
            "rejection_reason_counts": dict(
                sorted(cast(dict[str, int], bucket["rejection_reason_counts"]).items())
            ),
            "watchlist_reason_counts": dict(
                sorted(cast(dict[str, int], bucket["watchlist_reason_counts"]).items())
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


def _bucket_float(bucket: dict[str, object], field_name: str) -> float:
    return cast(float, bucket[field_name])


def _update_reason_bucket(
    bucket: dict[str, object],
    field_name: str,
    reason_codes: Sequence[object],
) -> None:
    counter = cast(dict[str, int], bucket[field_name])
    for reason_code in reason_codes:
        if isinstance(reason_code, str):
            counter[reason_code] = counter.get(reason_code, 0) + 1


def _grid_summary(
    options: HistoricalFinalAnswerQualitySignalProfileGridOptions,
) -> dict[str, object]:
    return {
        "competition_groups": [list(group) for group in options.competition_groups],
        "probability_min_values": list(options.probability_min_values),
        "probability_max_values": list(options.probability_max_values),
        "min_decimal_odds_values": list(options.min_decimal_odds_values),
        "max_decimal_odds_values": list(options.max_decimal_odds_values),
        "max_model_edge_values": list(options.max_model_edge_values),
        "score_min_values": list(options.score_min_values),
        "score_max_values": list(options.score_max_values),
        "strength_values": list(options.strength_values),
        "candidate_start_index": options.candidate_start_index,
        "candidate_limit": options.candidate_limit,
        "candidate_indices": list(options.candidate_indices),
        "candidate_cache_dir": (
            str(options.candidate_cache_dir) if options.candidate_cache_dir is not None else None
        ),
        "read_candidate_cache": options.read_candidate_cache,
        "write_candidate_cache": options.write_candidate_cache,
        "baseline_cache_dir": (
            str(options.baseline_cache_dir) if options.baseline_cache_dir is not None else None
        ),
        "read_baseline_cache": options.read_baseline_cache,
        "write_baseline_cache": options.write_baseline_cache,
        "include_comparison_items": options.include_comparison_items,
        "comparison_item_filter": options.comparison_item_filter,
        "comparison_item_limit": options.comparison_item_limit,
        "gate_thresholds": {
            "fail_on_suite_statuses": list(options.fail_on_suite_statuses),
            "min_affected_leg_count": options.min_affected_leg_count,
            "min_final_hit_count_delta": options.min_final_hit_count_delta,
            "min_final_hit_rate_delta": options.min_final_hit_rate_delta,
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
            "min_upset_capture_rate_delta": options.min_upset_capture_rate_delta,
            "min_candidate_roi": options.min_candidate_roi,
            "watchlist_max_candidate_roi_shortfall": (
                options.watchlist_max_candidate_roi_shortfall
            ),
            "watchlist_min_final_hit_count_delta": (
                options.watchlist_min_final_hit_count_delta
            ),
            "watchlist_min_roi_delta": options.watchlist_min_roi_delta,
            "watchlist_min_profit_loss_delta": options.watchlist_min_profit_loss_delta,
            "watchlist_max_final_hit_harm_count_vs_baseline": (
                options.watchlist_max_final_hit_harm_count_vs_baseline
            ),
            "watchlist_max_profit_loss_harm_count_vs_baseline": (
                options.watchlist_max_profit_loss_harm_count_vs_baseline
            ),
            "require_objective_improvement": options.require_objective_improvement,
            "min_objective_roi_delta": options.min_objective_roi_delta,
            "min_objective_upset_capture_rate_delta": (
                options.min_objective_upset_capture_rate_delta
            ),
            "comparison_epsilon": options.comparison_epsilon,
        },
    }


def _merge_warnings(
    reports: Sequence[HistoricalFinalAnswerQualitySignalProfileGridReport],
    candidates: Sequence[HistoricalFinalAnswerQualitySignalProfileCandidate],
) -> list[str]:
    warnings: list[str] = []
    for field_name in (
        "slice_count",
        "fixture_count",
        "prediction_count",
        "baseline_suite_key",
        "baseline_suite_status",
    ):
        values = {getattr(report, field_name) for report in reports}
        if len(values) > 1:
            warnings.append(f"quality_signal_profile_grid_merge:inconsistent_{field_name}")
    total_counts = {report.total_grid_candidate_count for report in reports}
    if len(total_counts) > 1:
        warnings.append("quality_signal_profile_grid_merge:inconsistent_total_grid_candidate_count")
    candidate_indices = [candidate.candidate_index for candidate in candidates]
    if _duplicate_candidate_indices(candidate_indices):
        warnings.append("quality_signal_profile_grid_merge:duplicate_candidate_indices")
    if _missing_candidate_indices(
        candidate_indices,
        _merged_total_grid_candidate_count(reports),
    ):
        warnings.append("quality_signal_profile_grid_merge:missing_candidate_indices")
    return warnings


def _merged_total_grid_candidate_count(
    reports: Sequence[HistoricalFinalAnswerQualitySignalProfileGridReport],
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
    return sorted(candidate_index for candidate_index, count in counter.items() if count > 1)


def _merged_grid_summary(
    reports: Sequence[HistoricalFinalAnswerQualitySignalProfileGridReport],
) -> dict[str, object]:
    grid = dict(cast(dict[str, object], reports[0].summary_json.get("grid", {})))
    grid["candidate_start_index"] = min(
        (candidate.candidate_index for report in reports for candidate in report.candidates),
        default=0,
    )
    grid["candidate_limit"] = sum(report.candidate_count for report in reports)
    grid["candidate_indices"] = [
        candidate.candidate_index
        for report in reports
        for candidate in report.candidates
    ]
    grid["candidate_cache_dir"] = None
    grid["read_candidate_cache"] = None
    grid["write_candidate_cache"] = None
    grid["baseline_cache_dir"] = None
    grid["read_baseline_cache"] = None
    grid["write_baseline_cache"] = None
    grid["include_comparison_items"] = any(
        report.summary_json.get("include_comparison_items") is True
        for report in reports
    )
    grid["comparison_item_filter"] = reports[0].summary_json.get("comparison_item_filter")
    grid["comparison_item_limit"] = reports[0].summary_json.get("comparison_item_limit")
    return grid


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Search final-answer quality-signal penalty profile candidates."
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
    parser.add_argument("--final-answer-stake-efficiency-guard", action="store_true")
    parser.add_argument(
        "--final-answer-stake-efficiency-penalty-strength",
        type=float,
        default=0.08,
    )
    parser.add_argument(
        "--final-answer-stake-efficiency-max-stake-multiplier",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--final-answer-stake-efficiency-min-roi",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--final-answer-stake-efficiency-modes",
        default="multiple",
    )
    parser.add_argument(
        "--final-answer-stake-efficiency-scope",
        choices=["all", "quality_signal_affected"],
        default="all",
    )
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
    parser.add_argument("--competition-group", action="append", default=[])
    parser.add_argument("--probability-min-values", default="0.65")
    parser.add_argument("--probability-max-values", default="0.80")
    parser.add_argument("--min-decimal-odds-values", default="1.0")
    parser.add_argument("--max-decimal-odds-values", default="1.35")
    parser.add_argument("--max-model-edge-values", default="0.0")
    parser.add_argument("--score-min-values", default="0.0")
    parser.add_argument("--score-max-values", default="1.0")
    parser.add_argument("--strength-values", default="0.04")
    parser.add_argument("--fail-on-suite-statuses", default="regressed,mixed")
    parser.add_argument("--min-affected-leg-count", type=int, default=1)
    parser.add_argument("--min-final-hit-count-delta", type=int, default=0)
    parser.add_argument("--min-final-hit-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-final-hit-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument("--max-profit-loss-harm-count-vs-baseline", type=int, default=0)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-mean-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--min-upset-capture-rate-delta", type=float, default=0.0)
    parser.add_argument("--min-candidate-roi", type=float)
    parser.add_argument("--watchlist-max-candidate-roi-shortfall", type=float)
    parser.add_argument("--watchlist-min-final-hit-count-delta", type=int, default=0)
    parser.add_argument("--watchlist-min-roi-delta", type=float, default=0.0)
    parser.add_argument("--watchlist-min-profit-loss-delta", type=float, default=0.0)
    parser.add_argument(
        "--watchlist-max-final-hit-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--watchlist-max-profit-loss-harm-count-vs-baseline",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--require-objective-improvement",
        action=BooleanOptionalAction,
        default=True,
        help=(
            "Require at least one promotion objective to improve, currently ROI "
            "or upset capture rate."
        ),
    )
    parser.add_argument("--min-objective-roi-delta", type=float, default=0.0)
    parser.add_argument("--min-objective-upset-capture-rate-delta", type=float, default=0.0)
    parser.add_argument("--comparison-epsilon", type=float, default=1e-12)
    parser.add_argument("--candidate-start-index", type=int, default=0)
    parser.add_argument("--candidate-limit", type=int)
    parser.add_argument("--candidate-indices", default="")
    parser.add_argument("--candidate-cache-dir", type=Path)
    parser.add_argument("--no-candidate-cache-read", action="store_true")
    parser.add_argument("--no-candidate-cache-write", action="store_true")
    parser.add_argument("--baseline-cache-dir", type=Path)
    parser.add_argument("--no-baseline-cache-read", action="store_true")
    parser.add_argument("--no-baseline-cache-write", action="store_true")
    parser.add_argument("--progress-jsonl-path", type=Path)
    parser.add_argument("--include-comparison-items", action="store_true")
    parser.add_argument(
        "--comparison-item-filter",
        choices=["harmed", "changed", "all"],
        default="harmed",
    )
    parser.add_argument("--comparison-item-limit", type=int, default=50)
    args = parser.parse_args(argv)
    if not args.slice_paths and not args.suite_manifest:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _parse_merge_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description="Merge final-answer quality-signal profile grid batch reports."
    )
    parser.add_argument("report_paths", nargs="+", type=Path)
    parser.add_argument("--output-path", type=Path)
    return parser.parse_args(argv)


def _options_from_args(
    args: Namespace,
) -> HistoricalFinalAnswerQualitySignalProfileGridOptions:
    return HistoricalFinalAnswerQualitySignalProfileGridOptions(
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
            final_answer_stake_efficiency_guard=(
                args.final_answer_stake_efficiency_guard
            ),
            final_answer_stake_efficiency_penalty_strength=(
                args.final_answer_stake_efficiency_penalty_strength
            ),
            final_answer_stake_efficiency_max_stake_multiplier=(
                args.final_answer_stake_efficiency_max_stake_multiplier
            ),
            final_answer_stake_efficiency_min_roi=(
                args.final_answer_stake_efficiency_min_roi
            ),
            final_answer_stake_efficiency_modes=tuple(
                cast(RecommendationMode, mode)
                for mode in _csv(args.final_answer_stake_efficiency_modes)
            ),
            final_answer_stake_efficiency_scope=cast(
                HistoricalFinalAnswerStakeEfficiencyScope,
                args.final_answer_stake_efficiency_scope,
            ),
        ),
        competition_groups=_competition_groups_from_args(args.competition_group),
        probability_min_values=_float_tuple(args.probability_min_values),
        probability_max_values=_float_tuple(args.probability_max_values),
        min_decimal_odds_values=_float_tuple(args.min_decimal_odds_values),
        max_decimal_odds_values=_float_tuple(args.max_decimal_odds_values),
        max_model_edge_values=_float_tuple(args.max_model_edge_values),
        score_min_values=_float_tuple(args.score_min_values),
        score_max_values=_float_tuple(args.score_max_values),
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
        min_affected_leg_count=args.min_affected_leg_count,
        min_final_hit_count_delta=args.min_final_hit_count_delta,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
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
        min_upset_capture_rate_delta=args.min_upset_capture_rate_delta,
        min_candidate_roi=args.min_candidate_roi,
        watchlist_max_candidate_roi_shortfall=(
            args.watchlist_max_candidate_roi_shortfall
        ),
        watchlist_min_final_hit_count_delta=args.watchlist_min_final_hit_count_delta,
        watchlist_min_roi_delta=args.watchlist_min_roi_delta,
        watchlist_min_profit_loss_delta=args.watchlist_min_profit_loss_delta,
        watchlist_max_final_hit_harm_count_vs_baseline=(
            args.watchlist_max_final_hit_harm_count_vs_baseline
        ),
        watchlist_max_profit_loss_harm_count_vs_baseline=(
            args.watchlist_max_profit_loss_harm_count_vs_baseline
        ),
        require_objective_improvement=args.require_objective_improvement,
        min_objective_roi_delta=args.min_objective_roi_delta,
        min_objective_upset_capture_rate_delta=(args.min_objective_upset_capture_rate_delta),
        comparison_epsilon=args.comparison_epsilon,
        candidate_start_index=args.candidate_start_index,
        candidate_limit=args.candidate_limit,
        candidate_indices=_int_tuple(args.candidate_indices),
        candidate_cache_dir=args.candidate_cache_dir,
        read_candidate_cache=not args.no_candidate_cache_read,
        write_candidate_cache=not args.no_candidate_cache_write,
        baseline_cache_dir=args.baseline_cache_dir,
        read_baseline_cache=not args.no_baseline_cache_read,
        write_baseline_cache=not args.no_baseline_cache_write,
        progress_jsonl_path=args.progress_jsonl_path,
        include_comparison_items=args.include_comparison_items,
        comparison_item_filter=cast(
            HistoricalFinalAnswerQualitySignalProfileComparisonItemFilter,
            args.comparison_item_filter,
        ),
        comparison_item_limit=args.comparison_item_limit,
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


def _competition_groups_from_args(values: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    if not values:
        return ((),)
    return tuple(tuple(_csv(value)) for value in values)


def _float_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(item) for item in _csv(value))


def _int_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in _csv(value))


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


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None and baseline is None:
        return 0.0
    if value is None or baseline is None:
        return None
    return value - baseline


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


def _candidate_key(summary: Mapping[str, object]) -> str:
    digest = sha256(dumps(summary, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"historical_final_answer_quality_signal_profile_candidate:{digest}"


def _report_key(
    summary: Mapping[str, object],
    subjects: Sequence[
        HistoricalRecommendationSlice | HistoricalFinalAnswerQualitySignalProfileCandidate
    ],
) -> str:
    digest = sha256(
        dumps(
            {
                "summary": summary,
                "subject_ids": _report_subject_ids(subjects),
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_final_answer_quality_signal_profile_grid:{digest}"


def _report_subject_ids(
    subjects: Sequence[
        HistoricalRecommendationSlice | HistoricalFinalAnswerQualitySignalProfileCandidate
    ],
) -> list[str]:
    ids: list[str] = []
    for subject in subjects:
        if isinstance(subject, HistoricalRecommendationSlice):
            ids.append(subject.metadata.slice_id)
        else:
            ids.append(f"{subject.candidate_index}:{subject.candidate_key}")
    return ids
