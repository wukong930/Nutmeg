from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Iterable, Sequence
from hashlib import sha256
from json import dumps
from pathlib import Path
from time import perf_counter
from typing import Literal, cast

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_probability_calibration_transform import (
    HistoricalProbabilityCalibrationTransformOptions,
    HistoricalProbabilityCalibrationTransformReport,
    build_historical_probability_calibration_transform_report,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalOptimizerProfile,
    HistoricalRecommendationBacktestOptions,
    HistoricalRecommendationBacktestResult,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_probability_calibration_profile_artifact import (
    HistoricalProbabilityCalibrationProfileArtifactOptions,
)
from nutmeg.recommendations.historical_probability_calibration_profile_gate import (
    ONE_X_TWO_OUTCOMES,
    HistoricalProbabilityCalibrationProfileGateOptions,
    HistoricalProbabilityCalibrationProfileGateReport,
    build_historical_probability_calibration_profile_gate_report,
)
from nutmeg.recommendations.historical_probability_calibration_profile_rolling_admission import (
    HistoricalProbabilityCalibrationProfileRollingAdmissionOptions,
    HistoricalProbabilityCalibrationProfileRollingAdmissionReport,
    build_historical_probability_calibration_profile_rolling_admission_report,
)
from nutmeg.recommendations.historical_quality_gate import (
    HistoricalRecommendationSuiteQualityGateOptions,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)
from nutmeg.recommendations.models import RecommendationMode

type HistoricalProbabilityCalibrationProfileGridStatus = Literal["generated"]
type HistoricalProbabilityCalibrationProfileGridDecision = Literal["accepted", "rejected"]
type HistoricalProbabilityCalibrationProfileGridTransformCacheStatus = Literal[
    "hit",
    "miss",
]

DEFAULT_PROBABILITY_CALIBRATION_PROFILE_GRID_ID = (
    "probability-calibration-profile-grid-shadow-v3.1"
)


class HistoricalProbabilityCalibrationProfileGridOptions(BaseModel):
    grid_id: str = DEFAULT_PROBABILITY_CALIBRATION_PROFILE_GRID_ID
    blend_weights: tuple[float, ...] = (0.25, 0.50)
    target_outcome_groups: tuple[str, ...] = ONE_X_TWO_OUTCOMES
    probability_bands: tuple[str, ...] = ("0.00:0.35", "0.35:0.65", "0.65:1.00")
    decimal_odds_bands: tuple[str, ...] = ("all",)
    candidate_start_index: int = Field(default=0, ge=0)
    candidate_limit: int | None = Field(default=None, ge=1)
    progress_jsonl_path: Path | None = None
    gate_options: HistoricalProbabilityCalibrationProfileGateOptions = Field(
        default_factory=HistoricalProbabilityCalibrationProfileGateOptions
    )
    fold_objective_options: (
        HistoricalProbabilityCalibrationProfileRollingAdmissionOptions | None
    ) = None


class HistoricalProbabilityCalibrationProfileGridCandidate(BaseModel):
    candidate_key: str
    rank: int = Field(default=0, ge=0)
    candidate_index: int = Field(ge=0)
    transform_cache_key: str | None = None
    transform_cache_status: (
        HistoricalProbabilityCalibrationProfileGridTransformCacheStatus | None
    ) = None
    transform_report_key: str | None = None
    baseline_backtest_cache_hit_count: int = Field(default=0, ge=0)
    baseline_backtest_cache_miss_count: int = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0.0, ge=0.0)
    decision: HistoricalProbabilityCalibrationProfileGridDecision
    decision_reasons: list[str] = Field(default_factory=list)
    target_outcomes: list[str] = Field(default_factory=list)
    probability_min: float = Field(ge=0.0, le=1.0)
    probability_max: float = Field(ge=0.0, le=1.0)
    min_decimal_odds: float | None = Field(default=None, gt=1.0)
    max_decimal_odds: float | None = Field(default=None, gt=1.0)
    blend_weight: float = Field(ge=0.0, le=1.0)
    gate_report_key: str
    selected_competition_ids: list[str] = Field(default_factory=list)
    rejected_competition_ids: list[str] = Field(default_factory=list)
    adjusted_fixture_count: int = Field(ge=0)
    skipped_fixture_count: int = Field(ge=0)
    passed_final_answer_gate: bool = False
    suite_key: str | None = None
    suite_status: str | None = None
    quality_gate_key: str | None = None
    quality_gate_passed: bool = False
    deltas_json: dict[str, object] = Field(default_factory=dict)
    fold_objective_report_key: str | None = None
    fold_objective_status: str | None = None
    fold_objective_candidate_profile_allowed: bool | None = None
    fold_objective_failed_fold_count: int | None = Field(default=None, ge=0)
    fold_objective_active_fold_count: int | None = Field(default=None, ge=0)
    fold_objective_active_competition_fold_count: int | None = Field(default=None, ge=0)
    fold_objective_active_season_cutoff_fold_count: int | None = Field(default=None, ge=0)
    fold_objective_active_rolling_fold_count: int | None = Field(default=None, ge=0)
    fold_objective_json: dict[str, object] = Field(default_factory=dict)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalProbabilityCalibrationProfileGridReport(BaseModel):
    report_key: str
    status: HistoricalProbabilityCalibrationProfileGridStatus
    grid_id: str
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    total_grid_candidate_count: int = Field(ge=0)
    candidate_start_index: int = Field(default=0, ge=0)
    candidate_limit: int | None = Field(default=None, ge=1)
    candidate_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    transform_cache_hit_count: int = Field(default=0, ge=0)
    transform_cache_miss_count: int = Field(default=0, ge=0)
    unique_transform_report_count: int = Field(default=0, ge=0)
    baseline_backtest_cache_hit_count: int = Field(default=0, ge=0)
    baseline_backtest_cache_miss_count: int = Field(default=0, ge=0)
    unique_baseline_backtest_count: int = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0.0, ge=0.0)
    candidate_elapsed_seconds: float = Field(default=0.0, ge=0.0)
    slowest_candidate_index: int | None = Field(default=None, ge=0)
    slowest_candidate_elapsed_seconds: float | None = Field(default=None, ge=0.0)
    candidates: list[HistoricalProbabilityCalibrationProfileGridCandidate] = Field(
        default_factory=list
    )
    accepted_candidates: list[HistoricalProbabilityCalibrationProfileGridCandidate] = (
        Field(default_factory=list)
    )
    best_candidate: HistoricalProbabilityCalibrationProfileGridCandidate | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


class _GridCandidateSpec(BaseModel):
    candidate_index: int = Field(ge=0)
    target_outcomes: tuple[str, ...]
    probability_min: float = Field(ge=0.0, le=1.0)
    probability_max: float = Field(ge=0.0, le=1.0)
    min_decimal_odds: float | None = Field(default=None, gt=1.0)
    max_decimal_odds: float | None = Field(default=None, gt=1.0)
    blend_weight: float = Field(ge=0.0, le=1.0)


class _ProfileGridProgressJsonlWriter:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def write(self, event: str, payload: dict[str, object]) -> None:
        if self.path is None:
            return
        event_payload: dict[str, object] = {
            "calculation_basis": (
                "historical_probability_calibration_profile_grid_progress_v3_1"
            ),
            "event": event,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"{dumps(event_payload, ensure_ascii=False, sort_keys=True)}\n"
            )


def build_historical_probability_calibration_profile_grid_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationProfileGridOptions | None = None,
) -> HistoricalProbabilityCalibrationProfileGridReport:
    grid_started_at = perf_counter()
    resolved_options = options or HistoricalProbabilityCalibrationProfileGridOptions()
    all_specs = _grid_candidate_specs(resolved_options)
    selected_specs = _selected_grid_candidate_specs(all_specs, resolved_options)
    progress_writer = _ProfileGridProgressJsonlWriter(
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
    transform_report_cache: dict[str, HistoricalProbabilityCalibrationTransformReport] = {}
    baseline_backtest_cache: dict[str, HistoricalRecommendationBacktestResult] = {}
    transform_cache_hit_count = 0
    transform_cache_miss_count = 0
    baseline_backtest_cache_hit_count = 0
    baseline_backtest_cache_miss_count = 0
    candidate_results: list[HistoricalProbabilityCalibrationProfileGridCandidate] = []
    for candidate_position, spec in enumerate(selected_specs):
        progress_writer.write(
            "candidate_started",
            {
                "candidate_position": candidate_position,
                "selected_candidate_count": len(selected_specs),
                "candidate_index": spec.candidate_index,
                "target_outcomes": list(spec.target_outcomes),
                "probability_min": spec.probability_min,
                "probability_max": spec.probability_max,
                "min_decimal_odds": spec.min_decimal_odds,
                "max_decimal_odds": spec.max_decimal_odds,
                "blend_weight": spec.blend_weight,
            },
        )
        candidate_started_at = perf_counter()
        gate_options = _gate_options_for_spec(resolved_options, spec)
        transform_cache_key = _transform_cache_key(
            historical_slices,
            transform_options=gate_options.transform_options,
        )
        transform_report = transform_report_cache.get(transform_cache_key)
        if transform_report is None:
            transform_report = build_historical_probability_calibration_transform_report(
                historical_slices,
                options=gate_options.transform_options,
            )
            transform_report_cache[transform_cache_key] = transform_report
            transform_cache_status: (
                HistoricalProbabilityCalibrationProfileGridTransformCacheStatus
            ) = "miss"
            transform_cache_miss_count += 1
        else:
            transform_cache_status = "hit"
            transform_cache_hit_count += 1
        candidate = _candidate_result(
            historical_slices,
            options=resolved_options,
            spec=spec,
            gate_options=gate_options,
            transform_report=transform_report,
            transform_cache_key=transform_cache_key,
            transform_cache_status=transform_cache_status,
            baseline_backtest_cache=baseline_backtest_cache,
        )
        baseline_backtest_cache_hit_count += candidate.baseline_backtest_cache_hit_count
        baseline_backtest_cache_miss_count += candidate.baseline_backtest_cache_miss_count
        candidate_elapsed_seconds = _elapsed_seconds(candidate_started_at)
        candidate = candidate.model_copy(
            update={
                "elapsed_seconds": candidate_elapsed_seconds,
                "summary_json": {
                    **candidate.summary_json,
                    "elapsed_seconds": candidate_elapsed_seconds,
                },
            }
        )
        candidate_results.append(candidate)
        progress_writer.write(
            "candidate_completed",
            {
                "candidate_position": candidate_position,
                "selected_candidate_count": len(selected_specs),
                "candidate_index": candidate.candidate_index,
                "candidate_key": candidate.candidate_key,
                "decision": candidate.decision,
                "decision_reasons": candidate.decision_reasons,
                "transform_cache_status": candidate.transform_cache_status,
                "transform_report_key": candidate.transform_report_key,
                "baseline_backtest_cache_hit_count": (
                    candidate.baseline_backtest_cache_hit_count
                ),
                "baseline_backtest_cache_miss_count": (
                    candidate.baseline_backtest_cache_miss_count
                ),
                "gate_report_key": candidate.gate_report_key,
                "passed_final_answer_gate": candidate.passed_final_answer_gate,
                "fold_objective_status": candidate.fold_objective_status,
                "fold_objective_failed_fold_count": (
                    candidate.fold_objective_failed_fold_count
                ),
                "elapsed_seconds": candidate_elapsed_seconds,
            },
        )
    candidates = _ranked_candidates(candidate_results)
    accepted_candidates = [
        candidate for candidate in candidates if candidate.decision == "accepted"
    ]
    best_candidate = _best_candidate(accepted_candidates or candidates)
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    warnings = _report_warnings(candidates)
    candidate_elapsed_seconds = _rounded_sum(
        candidate.elapsed_seconds for candidate in candidates
    )
    slowest_candidate = max(
        candidates,
        key=lambda candidate: candidate.elapsed_seconds,
        default=None,
    )
    elapsed_seconds = _elapsed_seconds(grid_started_at)
    summary: dict[str, object] = {
        "calculation_basis": "historical_probability_calibration_profile_grid_v3_1",
        "grid_id": resolved_options.grid_id,
        "shadow_only": True,
        "slice_count": len(historical_slices),
        "fixture_count": fixture_count,
        "total_grid_candidate_count": len(all_specs),
        "candidate_start_index": resolved_options.candidate_start_index,
        "candidate_limit": resolved_options.candidate_limit,
        "candidate_indices": [candidate.candidate_index for candidate in candidates],
        "candidate_count": len(candidates),
        "accepted_count": len(accepted_candidates),
        "rejected_count": len(candidates) - len(accepted_candidates),
        "fold_objective_enabled": (
            resolved_options.fold_objective_options is not None
        ),
        "transform_cache_hit_count": transform_cache_hit_count,
        "transform_cache_miss_count": transform_cache_miss_count,
        "unique_transform_report_count": len(transform_report_cache),
        "baseline_backtest_cache_hit_count": baseline_backtest_cache_hit_count,
        "baseline_backtest_cache_miss_count": baseline_backtest_cache_miss_count,
        "unique_baseline_backtest_count": len(baseline_backtest_cache),
        "elapsed_seconds": elapsed_seconds,
        "candidate_elapsed_seconds": candidate_elapsed_seconds,
        "slowest_candidate_index": (
            slowest_candidate.candidate_index if slowest_candidate is not None else None
        ),
        "slowest_candidate_elapsed_seconds": (
            slowest_candidate.elapsed_seconds if slowest_candidate is not None else None
        ),
        "progress_jsonl_path": (
            str(resolved_options.progress_jsonl_path)
            if resolved_options.progress_jsonl_path is not None
            else None
        ),
        "best_candidate_key": (
            best_candidate.candidate_key if best_candidate is not None else None
        ),
        "best_candidate_decision": (
            best_candidate.decision if best_candidate is not None else None
        ),
        "best_candidate_fold_objective": (
            best_candidate.fold_objective_json if best_candidate is not None else {}
        ),
        "best_candidate_deltas": (
            best_candidate.deltas_json if best_candidate is not None else {}
        ),
        "rejection_reason_counts": _rejection_reason_counts(candidates),
        "warnings": warnings,
    }
    report_key = _report_key(
        historical_slices,
        options=resolved_options,
        candidates=candidates,
    )
    summary["report_key"] = report_key
    progress_writer.write(
        "grid_completed",
        {
            "report_key": report_key,
            "candidate_count": len(candidates),
            "accepted_count": len(accepted_candidates),
            "rejected_count": len(candidates) - len(accepted_candidates),
            "transform_cache_hit_count": transform_cache_hit_count,
            "transform_cache_miss_count": transform_cache_miss_count,
            "unique_transform_report_count": len(transform_report_cache),
            "baseline_backtest_cache_hit_count": baseline_backtest_cache_hit_count,
            "baseline_backtest_cache_miss_count": baseline_backtest_cache_miss_count,
            "unique_baseline_backtest_count": len(baseline_backtest_cache),
            "elapsed_seconds": elapsed_seconds,
            "candidate_elapsed_seconds": candidate_elapsed_seconds,
            "slowest_candidate_index": (
                slowest_candidate.candidate_index
                if slowest_candidate is not None
                else None
            ),
            "slowest_candidate_elapsed_seconds": (
                slowest_candidate.elapsed_seconds
                if slowest_candidate is not None
                else None
            ),
        },
    )
    return HistoricalProbabilityCalibrationProfileGridReport(
        report_key=report_key,
        status="generated",
        grid_id=resolved_options.grid_id,
        slice_count=len(historical_slices),
        fixture_count=fixture_count,
        total_grid_candidate_count=len(all_specs),
        candidate_start_index=resolved_options.candidate_start_index,
        candidate_limit=resolved_options.candidate_limit,
        candidate_count=len(candidates),
        accepted_count=len(accepted_candidates),
        rejected_count=len(candidates) - len(accepted_candidates),
        transform_cache_hit_count=transform_cache_hit_count,
        transform_cache_miss_count=transform_cache_miss_count,
        unique_transform_report_count=len(transform_report_cache),
        baseline_backtest_cache_hit_count=baseline_backtest_cache_hit_count,
        baseline_backtest_cache_miss_count=baseline_backtest_cache_miss_count,
        unique_baseline_backtest_count=len(baseline_backtest_cache),
        elapsed_seconds=elapsed_seconds,
        candidate_elapsed_seconds=candidate_elapsed_seconds,
        slowest_candidate_index=(
            slowest_candidate.candidate_index if slowest_candidate is not None else None
        ),
        slowest_candidate_elapsed_seconds=(
            slowest_candidate.elapsed_seconds if slowest_candidate is not None else None
        ),
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        best_candidate=best_candidate,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_probability_calibration_profile_grid_report(
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
            _stdout_payload(report, summary_only=args.stdout_summary_only),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if report.accepted_count == 0 and not args.no_fail_process:
        raise SystemExit(1)


def _stdout_payload(
    report: HistoricalProbabilityCalibrationProfileGridReport,
    *,
    summary_only: bool,
) -> dict[str, object]:
    if not summary_only:
        return report.model_dump(mode="json")
    summary = dict(report.summary_json)
    summary.pop("suite_manifest", None)
    return {
        "report_key": report.report_key,
        "status": report.status,
        "grid_id": report.grid_id,
        "slice_count": report.slice_count,
        "fixture_count": report.fixture_count,
        "total_grid_candidate_count": report.total_grid_candidate_count,
        "candidate_start_index": report.candidate_start_index,
        "candidate_limit": report.candidate_limit,
        "candidate_count": report.candidate_count,
        "accepted_count": report.accepted_count,
        "rejected_count": report.rejected_count,
        "transform_cache_hit_count": report.transform_cache_hit_count,
        "transform_cache_miss_count": report.transform_cache_miss_count,
        "unique_transform_report_count": report.unique_transform_report_count,
        "baseline_backtest_cache_hit_count": report.baseline_backtest_cache_hit_count,
        "baseline_backtest_cache_miss_count": report.baseline_backtest_cache_miss_count,
        "unique_baseline_backtest_count": report.unique_baseline_backtest_count,
        "elapsed_seconds": report.elapsed_seconds,
        "candidate_elapsed_seconds": report.candidate_elapsed_seconds,
        "slowest_candidate_index": report.slowest_candidate_index,
        "slowest_candidate_elapsed_seconds": report.slowest_candidate_elapsed_seconds,
        "best_candidate": _compact_candidate(report.best_candidate),
        "top_candidates": [
            _compact_candidate(candidate) for candidate in report.candidates[:10]
        ],
        "accepted_candidates": [
            _compact_candidate(candidate)
            for candidate in report.accepted_candidates[:10]
        ],
        "summary_json": summary,
        "warnings": report.warnings,
    }


def _compact_candidate(
    candidate: HistoricalProbabilityCalibrationProfileGridCandidate | None,
) -> dict[str, object] | None:
    if candidate is None:
        return None
    return {
        "candidate_key": candidate.candidate_key,
        "rank": candidate.rank,
        "candidate_index": candidate.candidate_index,
        "transform_cache_key": candidate.transform_cache_key,
        "transform_cache_status": candidate.transform_cache_status,
        "transform_report_key": candidate.transform_report_key,
        "baseline_backtest_cache_hit_count": (
            candidate.baseline_backtest_cache_hit_count
        ),
        "baseline_backtest_cache_miss_count": (
            candidate.baseline_backtest_cache_miss_count
        ),
        "elapsed_seconds": candidate.elapsed_seconds,
        "decision": candidate.decision,
        "decision_reasons": candidate.decision_reasons,
        "target_outcomes": candidate.target_outcomes,
        "probability_min": candidate.probability_min,
        "probability_max": candidate.probability_max,
        "min_decimal_odds": candidate.min_decimal_odds,
        "max_decimal_odds": candidate.max_decimal_odds,
        "blend_weight": candidate.blend_weight,
        "gate_report_key": candidate.gate_report_key,
        "selected_competition_ids": candidate.selected_competition_ids,
        "adjusted_fixture_count": candidate.adjusted_fixture_count,
        "skipped_fixture_count": candidate.skipped_fixture_count,
        "passed_final_answer_gate": candidate.passed_final_answer_gate,
        "suite_status": candidate.suite_status,
        "quality_gate_passed": candidate.quality_gate_passed,
        "deltas_json": candidate.deltas_json,
        "fold_objective_report_key": candidate.fold_objective_report_key,
        "fold_objective_status": candidate.fold_objective_status,
        "fold_objective_candidate_profile_allowed": (
            candidate.fold_objective_candidate_profile_allowed
        ),
        "fold_objective_failed_fold_count": (
            candidate.fold_objective_failed_fold_count
        ),
        "fold_objective_active_fold_count": candidate.fold_objective_active_fold_count,
        "fold_objective_json": candidate.fold_objective_json,
    }


def _candidate_result(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationProfileGridOptions,
    spec: _GridCandidateSpec,
    gate_options: HistoricalProbabilityCalibrationProfileGateOptions,
    transform_report: HistoricalProbabilityCalibrationTransformReport,
    transform_cache_key: str,
    transform_cache_status: HistoricalProbabilityCalibrationProfileGridTransformCacheStatus,
    baseline_backtest_cache: dict[str, HistoricalRecommendationBacktestResult],
) -> HistoricalProbabilityCalibrationProfileGridCandidate:
    gate_report = build_historical_probability_calibration_profile_gate_report(
        historical_slices,
        options=gate_options,
        transform_report=transform_report,
        baseline_backtest_cache=baseline_backtest_cache,
    )
    fold_objective_report = _candidate_fold_objective_report(
        historical_slices,
        options=options,
        spec=spec,
        gate_options=gate_options,
    )
    fold_objective = _fold_objective_summary(fold_objective_report)
    decision_reasons = _decision_reasons(
        gate_report,
        fold_objective_report=fold_objective_report,
    )
    decision: HistoricalProbabilityCalibrationProfileGridDecision = (
        "accepted" if not decision_reasons else "rejected"
    )
    suite = gate_report.suite
    quality_gate = gate_report.quality_gate
    deltas = suite.aggregate_deltas_json if suite is not None else {}
    summary: dict[str, object] = {
        "calculation_basis": (
            "historical_probability_calibration_profile_grid_candidate_v3_1"
        ),
        "grid_id": options.grid_id,
        "candidate_index": spec.candidate_index,
        "decision": decision,
        "decision_reasons": decision_reasons,
        "target_outcomes": list(spec.target_outcomes),
        "probability_min": spec.probability_min,
        "probability_max": spec.probability_max,
        "min_decimal_odds": spec.min_decimal_odds,
        "max_decimal_odds": spec.max_decimal_odds,
        "blend_weight": spec.blend_weight,
        "gate_report_key": gate_report.report_key,
        "selected_competition_ids": gate_report.selected_competition_ids,
        "rejected_competition_ids": gate_report.rejected_competition_ids,
        "adjusted_fixture_count": gate_report.adjusted_fixture_count,
        "skipped_fixture_count": gate_report.skipped_fixture_count,
        "suite_key": suite.suite_key if suite is not None else None,
        "suite_status": suite.status if suite is not None else None,
        "quality_gate_key": quality_gate.gate_key if quality_gate is not None else None,
        "quality_gate_passed": quality_gate.passed if quality_gate is not None else False,
        "passed_final_answer_gate": gate_report.passed_final_answer_gate,
        "aggregate_deltas_json": deltas,
        "fold_objective": fold_objective,
        "shadow_only": True,
    }
    candidate_key = _candidate_key(summary)
    candidate_summary = {
        **summary,
        "transform_cache_key": transform_cache_key,
        "transform_cache_status": transform_cache_status,
        "transform_report_key": transform_report.report_key,
        "baseline_backtest_cache_hit_count": (
            gate_report.baseline_backtest_cache_hit_count
        ),
        "baseline_backtest_cache_miss_count": (
            gate_report.baseline_backtest_cache_miss_count
        ),
    }
    return HistoricalProbabilityCalibrationProfileGridCandidate(
        candidate_key=candidate_key,
        candidate_index=spec.candidate_index,
        transform_cache_key=transform_cache_key,
        transform_cache_status=transform_cache_status,
        transform_report_key=transform_report.report_key,
        baseline_backtest_cache_hit_count=(
            gate_report.baseline_backtest_cache_hit_count
        ),
        baseline_backtest_cache_miss_count=(
            gate_report.baseline_backtest_cache_miss_count
        ),
        decision=decision,
        decision_reasons=decision_reasons,
        target_outcomes=list(spec.target_outcomes),
        probability_min=spec.probability_min,
        probability_max=spec.probability_max,
        min_decimal_odds=spec.min_decimal_odds,
        max_decimal_odds=spec.max_decimal_odds,
        blend_weight=spec.blend_weight,
        gate_report_key=gate_report.report_key,
        selected_competition_ids=gate_report.selected_competition_ids,
        rejected_competition_ids=gate_report.rejected_competition_ids,
        adjusted_fixture_count=gate_report.adjusted_fixture_count,
        skipped_fixture_count=gate_report.skipped_fixture_count,
        passed_final_answer_gate=gate_report.passed_final_answer_gate,
        suite_key=suite.suite_key if suite is not None else None,
        suite_status=suite.status if suite is not None else None,
        quality_gate_key=quality_gate.gate_key if quality_gate is not None else None,
        quality_gate_passed=quality_gate.passed if quality_gate is not None else False,
        deltas_json=deltas,
        fold_objective_report_key=(
            fold_objective_report.report_key
            if fold_objective_report is not None
            else None
        ),
        fold_objective_status=(
            fold_objective_report.status if fold_objective_report is not None else None
        ),
        fold_objective_candidate_profile_allowed=(
            fold_objective_report.candidate_profile_allowed
            if fold_objective_report is not None
            else None
        ),
        fold_objective_failed_fold_count=(
            fold_objective_report.failed_fold_count
            if fold_objective_report is not None
            else None
        ),
        fold_objective_active_fold_count=(
            fold_objective_report.active_fold_count
            if fold_objective_report is not None
            else None
        ),
        fold_objective_active_competition_fold_count=(
            fold_objective_report.active_competition_fold_count
            if fold_objective_report is not None
            else None
        ),
        fold_objective_active_season_cutoff_fold_count=(
            fold_objective_report.active_season_cutoff_fold_count
            if fold_objective_report is not None
            else None
        ),
        fold_objective_active_rolling_fold_count=(
            fold_objective_report.active_rolling_fold_count
            if fold_objective_report is not None
            else None
        ),
        fold_objective_json=fold_objective,
        summary_json=candidate_summary,
    )


def _gate_options_for_spec(
    options: HistoricalProbabilityCalibrationProfileGridOptions,
    spec: _GridCandidateSpec,
) -> HistoricalProbabilityCalibrationProfileGateOptions:
    base = options.gate_options
    transform_options = base.transform_options.model_copy(
        update={"blend_weight": spec.blend_weight}
    )
    return base.model_copy(
        update={
            "gate_id": f"{options.grid_id}:candidate-{spec.candidate_index}",
            "target_outcomes": spec.target_outcomes,
            "probability_min": spec.probability_min,
            "probability_max": spec.probability_max,
            "min_decimal_odds": spec.min_decimal_odds,
            "max_decimal_odds": spec.max_decimal_odds,
            "transform_options": transform_options,
        }
    )


def _candidate_fold_objective_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationProfileGridOptions,
    spec: _GridCandidateSpec,
    gate_options: HistoricalProbabilityCalibrationProfileGateOptions,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionReport | None:
    if options.fold_objective_options is None:
        return None
    fold_options = _fold_objective_options_for_spec(options, spec, gate_options)
    return build_historical_probability_calibration_profile_rolling_admission_report(
        historical_slices,
        options=fold_options,
    )


def _fold_objective_options_for_spec(
    options: HistoricalProbabilityCalibrationProfileGridOptions,
    spec: _GridCandidateSpec,
    gate_options: HistoricalProbabilityCalibrationProfileGateOptions,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionOptions:
    if options.fold_objective_options is None:
        raise ValueError("fold objective options are required")
    base = options.fold_objective_options
    artifact_options = base.artifact_options.model_copy(
        update={
            "artifact_id": f"{base.artifact_options.artifact_id}:candidate-{spec.candidate_index}",
            "gate_options": gate_options,
        }
    )
    return base.model_copy(
        update={
            "rolling_admission_id": (
                f"{base.rolling_admission_id}:candidate-{spec.candidate_index}"
            ),
            "artifact_options": artifact_options,
        }
    )


def _fold_objective_summary(
    report: HistoricalProbabilityCalibrationProfileRollingAdmissionReport | None,
) -> dict[str, object]:
    if report is None:
        return {}
    failed_folds = [fold for fold in report.folds if fold.status == "failed"]
    failed_checks = [check for check in report.checks if check.status == "failed"]
    return {
        "report_key": report.report_key,
        "status": report.status,
        "candidate_profile_allowed": report.candidate_profile_allowed,
        "shadow_allowed": report.shadow_allowed,
        "fold_count": report.fold_count,
        "active_fold_count": report.active_fold_count,
        "failed_fold_count": report.failed_fold_count,
        "active_competition_fold_count": report.active_competition_fold_count,
        "active_season_cutoff_fold_count": report.active_season_cutoff_fold_count,
        "active_rolling_fold_count": report.active_rolling_fold_count,
        "overall_status": report.overall_fold.status,
        "overall_passed_final_answer_gate": (
            report.overall_fold.passed_final_answer_gate
        ),
        "overall_emitted_profile": report.overall_fold.emitted_profile,
        "overall_adjusted_fixture_count": report.overall_fold.adjusted_fixture_count,
        "overall_bucket_count": report.overall_fold.bucket_count,
        "overall_final_hit_rate_delta": report.overall_fold.final_hit_rate_delta,
        "overall_roi_delta": report.overall_fold.roi_delta,
        "overall_profit_loss_delta": report.overall_fold.profit_loss_delta,
        "overall_brier_score_delta": report.overall_fold.brier_score_delta,
        "overall_log_loss_delta": report.overall_fold.log_loss_delta,
        "overall_mean_calibration_error_delta": (
            report.overall_fold.mean_calibration_error_delta
        ),
        "failed_fold_ids": [fold.fold_id for fold in failed_folds],
        "failed_check_names": [check.name for check in failed_checks],
    }


def _decision_reasons(
    gate_report: HistoricalProbabilityCalibrationProfileGateReport,
    *,
    fold_objective_report: (
        HistoricalProbabilityCalibrationProfileRollingAdmissionReport | None
    ) = None,
) -> list[str]:
    reasons: list[str] = []
    if not gate_report.selected_competition_ids:
        reasons.append("profile_grid:no_selected_competitions")
    if gate_report.adjusted_fixture_count == 0:
        reasons.append("profile_grid:no_adjusted_fixtures")
    if gate_report.suite is None:
        reasons.append("profile_grid:no_suite")
    if gate_report.quality_gate is None:
        reasons.append("profile_grid:no_quality_gate")
    if gate_report.quality_gate is not None and not gate_report.quality_gate.passed:
        reasons.extend(
            f"quality_gate:{check.name}"
            for check in gate_report.quality_gate.checks
            if check.status == "failed"
        )
    if not gate_report.passed_final_answer_gate and not reasons:
        reasons.append("profile_grid:final_answer_gate_failed")
    if fold_objective_report is not None:
        if not fold_objective_report.candidate_profile_allowed:
            reasons.append(f"fold_objective:status:{fold_objective_report.status}")
        if fold_objective_report.failed_fold_count > 0:
            reasons.append("fold_objective:failed_fold_count")
        reasons.extend(
            f"fold_objective:failed_check:{check.name}"
            for check in fold_objective_report.checks
            if check.status == "failed"
        )
    return sorted(set(reasons))


def _grid_candidate_specs(
    options: HistoricalProbabilityCalibrationProfileGridOptions,
) -> list[_GridCandidateSpec]:
    specs: list[_GridCandidateSpec] = []
    candidate_index = 0
    for blend_weight in options.blend_weights:
        for target_group in options.target_outcome_groups:
            target_outcomes = _parse_target_outcome_group(target_group)
            for probability_band in options.probability_bands:
                probability_min, probability_max = _parse_probability_band(probability_band)
                for odds_band in options.decimal_odds_bands:
                    min_decimal_odds, max_decimal_odds = _parse_decimal_odds_band(
                        odds_band
                    )
                    specs.append(
                        _GridCandidateSpec(
                            candidate_index=candidate_index,
                            target_outcomes=target_outcomes,
                            probability_min=probability_min,
                            probability_max=probability_max,
                            min_decimal_odds=min_decimal_odds,
                            max_decimal_odds=max_decimal_odds,
                            blend_weight=blend_weight,
                        )
                    )
                    candidate_index += 1
    return specs


def _selected_grid_candidate_specs(
    specs: Sequence[_GridCandidateSpec],
    options: HistoricalProbabilityCalibrationProfileGridOptions,
) -> list[_GridCandidateSpec]:
    end_index = (
        None
        if options.candidate_limit is None
        else options.candidate_start_index + options.candidate_limit
    )
    return list(specs[options.candidate_start_index : end_index])


def _ranked_candidates(
    candidates: Sequence[HistoricalProbabilityCalibrationProfileGridCandidate],
) -> list[HistoricalProbabilityCalibrationProfileGridCandidate]:
    sorted_candidates = sorted(candidates, key=_candidate_sort_key)
    return [
        candidate.model_copy(update={"rank": rank})
        for rank, candidate in enumerate(sorted_candidates, start=1)
    ]


def _best_candidate(
    candidates: Sequence[HistoricalProbabilityCalibrationProfileGridCandidate],
) -> HistoricalProbabilityCalibrationProfileGridCandidate | None:
    return _ranked_candidates(candidates)[0] if candidates else None


def _candidate_sort_key(
    candidate: HistoricalProbabilityCalibrationProfileGridCandidate,
) -> tuple[object, ...]:
    return (
        0 if candidate.decision == "accepted" else 1,
        _fold_objective_failed_count(candidate),
        -_delta_number(candidate.deltas_json, "final_answer_changed_count", default=0.0),
        _delta_number(candidate.deltas_json, "brier_score_delta", default=999.0),
        _delta_number(candidate.deltas_json, "log_loss_delta", default=999.0),
        _delta_number(
            candidate.deltas_json,
            "mean_calibration_error_delta",
            default=999.0,
        ),
        -_delta_number(candidate.deltas_json, "final_hit_rate_delta", default=-999.0),
        -_delta_number(candidate.deltas_json, "roi_delta", default=-999.0),
        candidate.candidate_index,
    )


def _fold_objective_failed_count(
    candidate: HistoricalProbabilityCalibrationProfileGridCandidate,
) -> int:
    if candidate.fold_objective_failed_fold_count is None:
        return 0
    return candidate.fold_objective_failed_fold_count


def _delta_number(
    deltas: dict[str, object],
    key: str,
    *,
    default: float,
) -> float:
    value = deltas.get(key)
    return float(value) if isinstance(value, int | float) else default


def _transform_cache_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    transform_options: HistoricalProbabilityCalibrationTransformOptions,
) -> str:
    payload = {
        "calculation_basis": (
            "historical_probability_calibration_profile_grid_transform_cache_v3_1"
        ),
        "slice_ids": [item.metadata.slice_id for item in historical_slices],
        "transform_options": transform_options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_grid_transform_cache:{digest}"


def _report_warnings(
    candidates: Sequence[HistoricalProbabilityCalibrationProfileGridCandidate],
) -> list[str]:
    warnings: list[str] = []
    if not candidates:
        warnings.append("historical_probability_calibration_profile_grid:no_candidates")
    if not any(candidate.decision == "accepted" for candidate in candidates):
        warnings.append(
            "historical_probability_calibration_profile_grid:no_accepted_candidates"
        )
    for reason, count in _rejection_reason_counts(candidates).items():
        warnings.append(
            f"historical_probability_calibration_profile_grid:rejection:{reason}:{count}"
        )
    return warnings


def _rejection_reason_counts(
    candidates: Sequence[HistoricalProbabilityCalibrationProfileGridCandidate],
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for candidate in candidates:
        if candidate.decision == "rejected":
            counter.update(candidate.decision_reasons)
    return dict(sorted(counter.items()))


def _parse_target_outcome_group(value: str) -> tuple[str, ...]:
    normalized = value.strip()
    if normalized in {"", "all"}:
        return ONE_X_TWO_OUTCOMES
    outcomes = tuple(part.strip() for part in normalized.split("+") if part.strip())
    invalid = [outcome for outcome in outcomes if outcome not in ONE_X_TWO_OUTCOMES]
    if not outcomes or invalid:
        raise ValueError(
            "target outcome groups must contain home_win, draw, away_win, or all"
        )
    return outcomes


def _parse_probability_band(value: str) -> tuple[float, float]:
    lower, upper = _parse_required_band(value, label="probability band")
    if lower < 0.0 or upper > 1.0 or lower > upper:
        raise ValueError("probability bands must be within 0.0:1.0")
    return lower, upper


def _parse_decimal_odds_band(value: str) -> tuple[float | None, float | None]:
    normalized = value.strip()
    if normalized in {"", "all", "*"}:
        return None, None
    parts = normalized.split(":", maxsplit=1)
    if len(parts) != 2:
        raise ValueError("decimal odds bands must use min:max or all")
    lower = float(parts[0]) if parts[0] else None
    upper = float(parts[1]) if parts[1] else None
    if lower is not None and lower <= 1.0:
        raise ValueError("minimum decimal odds must be greater than 1.0")
    if upper is not None and upper <= 1.0:
        raise ValueError("maximum decimal odds must be greater than 1.0")
    if lower is not None and upper is not None and lower > upper:
        raise ValueError("decimal odds band minimum cannot exceed maximum")
    return lower, upper


def _parse_required_band(value: str, *, label: str) -> tuple[float, float]:
    parts = value.strip().split(":", maxsplit=1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"{label} must use min:max")
    return float(parts[0]), float(parts[1])


def _candidate_key(summary: dict[str, object]) -> str:
    digest = sha256(
        dumps(summary, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_grid_candidate:{digest}"


def _report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationProfileGridOptions,
    candidates: Sequence[HistoricalProbabilityCalibrationProfileGridCandidate],
) -> str:
    payload = {
        "slice_ids": [item.metadata.slice_id for item in historical_slices],
        "options": options.model_dump(mode="json"),
        "candidate_keys": [candidate.candidate_key for candidate in candidates],
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_profile_grid:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run a shadow grid search over narrow probability calibration profiles."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--grid-id",
        default=DEFAULT_PROBABILITY_CALIBRATION_PROFILE_GRID_ID,
    )
    parser.add_argument("--blend-weights", default="0.25,0.50")
    parser.add_argument("--target-outcome-groups", default="home_win,draw,away_win")
    parser.add_argument("--probability-bands", default="0.00:0.35,0.35:0.65,0.65:1.00")
    parser.add_argument("--decimal-odds-bands", default="all")
    parser.add_argument("--candidate-start-index", type=int, default=0)
    parser.add_argument("--candidate-limit", type=int)
    parser.add_argument("--progress-jsonl-path", type=Path)
    parser.add_argument("--competition-ids", default="")
    parser.add_argument("--include-rejected-transform-competitions", action="store_true")
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
    parser.add_argument("--min-calibrated-probability", type=float, default=0.01)
    parser.add_argument("--max-calibrated-probability", type=float, default=0.95)
    parser.add_argument("--group-all-competitions", action="store_true")
    parser.add_argument("--pass-types", default="1x1,2x1,3x1,4x1")
    parser.add_argument("--modes", default="single,multiple")
    parser.add_argument("--optimizer-profile", choices=["heuristic", "solver"], default="solver")
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
    parser.add_argument("--enable-fold-objective", action="store_true")
    parser.add_argument("--fold-min-final-hit-sample-size", type=int)
    parser.add_argument("--fold-min-final-hit-rate-delta", type=float)
    parser.add_argument("--fold-min-final-answer-changed-count", type=int)
    parser.add_argument("--fold-min-roi-delta", type=float)
    parser.add_argument("--fold-min-profit-loss-delta", type=float)
    parser.add_argument("--fold-max-brier-score-delta", type=float)
    parser.add_argument("--fold-max-log-loss-delta", type=float)
    parser.add_argument("--fold-max-mean-calibration-error-delta", type=float)
    parser.add_argument("--fold-min-overall-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--fold-min-overall-bucket-count", type=int, default=1)
    parser.add_argument("--fold-min-adjusted-fixture-count", type=int, default=1)
    parser.add_argument("--fold-min-bucket-count", type=int, default=1)
    parser.add_argument("--fold-allow-without-profile", action="store_true")
    parser.add_argument("--fold-min-active-competition-fold-count", type=int, default=1)
    parser.add_argument("--fold-min-active-season-cutoff-fold-count", type=int, default=1)
    parser.add_argument("--fold-min-active-rolling-fold-count", type=int, default=1)
    parser.add_argument("--fold-rolling-window-season-count", type=int, default=3)
    parser.add_argument("--fold-rolling-window-step", type=int, default=1)
    parser.add_argument("--fold-max-failed-fold-count", type=int, default=0)
    parser.add_argument("--fold-max-report-folds", type=int, default=120)
    parser.add_argument(
        "--stdout-summary-only",
        action="store_true",
        help=(
            "Print a compact grid summary to stdout while keeping --output-path "
            "as the full report artifact."
        ),
    )
    parser.add_argument("--no-fail-process", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalProbabilityCalibrationProfileGridOptions:
    quality_gate_options = _quality_gate_options_from_args(args)
    return HistoricalProbabilityCalibrationProfileGridOptions(
        grid_id=args.grid_id,
        blend_weights=_float_csv(args.blend_weights),
        target_outcome_groups=_split_csv(args.target_outcome_groups),
        probability_bands=_split_csv(args.probability_bands),
        decimal_odds_bands=_split_csv(args.decimal_odds_bands),
        candidate_start_index=args.candidate_start_index,
        candidate_limit=args.candidate_limit,
        progress_jsonl_path=args.progress_jsonl_path,
        gate_options=HistoricalProbabilityCalibrationProfileGateOptions(
            competition_ids=_split_csv(args.competition_ids),
            require_transform_acceptance=not args.include_rejected_transform_competitions,
            transform_options=HistoricalProbabilityCalibrationTransformOptions(
                holdout_season_count=args.holdout_season_count,
                min_training_season_count=args.min_training_season_count,
                min_validation_sample_size=args.min_validation_sample_size,
                segment_mode=args.segment_mode,
                bucket_size=args.bucket_size,
                min_bucket_sample_size=args.min_bucket_sample_size,
                min_calibrated_probability=args.min_calibrated_probability,
                max_calibrated_probability=args.max_calibrated_probability,
                group_by_competition=not args.group_all_competitions,
                prediction_sample_limit=0,
            ),
            backtest_options=HistoricalRecommendationBacktestOptions(
                pass_types=_split_csv(args.pass_types),
                modes=cast(tuple[RecommendationMode, ...], _split_csv(args.modes)),
                optimizer_profile=cast(HistoricalOptimizerProfile, args.optimizer_profile),
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
        fold_objective_options=_fold_objective_options_from_args(args),
    )


def _quality_gate_options_from_args(
    args: Namespace,
) -> HistoricalRecommendationSuiteQualityGateOptions:
    return HistoricalRecommendationSuiteQualityGateOptions(
        min_final_hit_sample_size=args.min_final_hit_sample_size,
        min_final_hit_rate_delta=args.min_final_hit_rate_delta,
        min_final_answer_changed_count=args.min_final_answer_changed_count,
        min_roi_delta=args.min_roi_delta,
        min_profit_loss_delta=args.min_profit_loss_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_mean_calibration_error_delta=args.max_mean_calibration_error_delta,
    )


def _fold_objective_options_from_args(
    args: Namespace,
) -> HistoricalProbabilityCalibrationProfileRollingAdmissionOptions | None:
    if not args.enable_fold_objective:
        return None
    quality_gate_options = _quality_gate_options_from_args(args)
    artifact_options = HistoricalProbabilityCalibrationProfileArtifactOptions(
        profile_mode="active",
        require_passed_final_answer_gate=True,
        gate_options=HistoricalProbabilityCalibrationProfileGateOptions(
            quality_gate_options=quality_gate_options,
        ),
    )
    return HistoricalProbabilityCalibrationProfileRollingAdmissionOptions(
        rolling_admission_id=f"{args.grid_id}:fold-objective",
        artifact_options=artifact_options,
        fold_quality_gate_options=_fold_quality_gate_options_from_args(
            args,
            quality_gate_options,
        ),
        admitted_profile_mode="active",
        min_overall_adjusted_fixture_count=(
            args.fold_min_overall_adjusted_fixture_count
        ),
        min_overall_bucket_count=args.fold_min_overall_bucket_count,
        min_fold_adjusted_fixture_count=args.fold_min_adjusted_fixture_count,
        min_fold_bucket_count=args.fold_min_bucket_count,
        require_fold_emitted_profile=not args.fold_allow_without_profile,
        min_active_competition_fold_count=(
            args.fold_min_active_competition_fold_count
        ),
        min_active_season_cutoff_fold_count=(
            args.fold_min_active_season_cutoff_fold_count
        ),
        min_active_rolling_fold_count=args.fold_min_active_rolling_fold_count,
        rolling_window_season_count=args.fold_rolling_window_season_count,
        rolling_window_step=args.fold_rolling_window_step,
        max_failed_fold_count=args.fold_max_failed_fold_count,
        max_report_folds=args.fold_max_report_folds,
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
        load_historical_recommendation_slice(slice_path) for slice_path in args.slice_paths
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


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _float_csv(value: str) -> tuple[float, ...]:
    return tuple(float(part) for part in _split_csv(value))


def _elapsed_seconds(started_at: float) -> float:
    return round(perf_counter() - started_at, 6)


def _rounded_sum(values: Iterable[float]) -> float:
    return round(sum(values), 6)
