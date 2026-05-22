from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Mapping, Sequence
from hashlib import sha256
from itertools import product
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_prematch_feature_ablation import (
    HistoricalPrematchFeatureAblationMetricSet,
    HistoricalPrematchFeatureAblationOptions,
    HistoricalPrematchFeatureAblationReport,
    build_historical_prematch_feature_ablation_report,
)
from nutmeg.recommendations.historical_backtest import (
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalPrematchFeatureAblationGridStatus = Literal["generated"]

DEFAULT_PREMATCH_FEATURE_ABLATION_GRID_ID = (
    "prematch-feature-ablation-grid-shadow-v3.1"
)


class HistoricalPrematchFeatureAblationGridOptions(BaseModel):
    grid_id: str = DEFAULT_PREMATCH_FEATURE_ABLATION_GRID_ID
    min_feature_data_quality_score: float = Field(default=70.0, ge=0.0, le=100.0)
    max_probability_shifts: tuple[float, ...] = (0.0, 0.04, 0.08, 0.12)
    odds_movement_weights: tuple[float, ...] = (0.0, 0.20, 0.35, 0.50)
    tracked_fragility_weights: tuple[float, ...] = (0.0, 0.50, 1.0)
    lineup_strength_weights: tuple[float, ...] = (0.0,)
    draw_signal_weights: tuple[float, ...] = (0.0, 0.25, 0.35)
    bucket_size: float = Field(default=0.10, gt=0.0, le=1.0)
    min_bucket_sample_size: int = Field(default=1, ge=1)
    prediction_sample_limit: int = Field(default=0, ge=0)
    max_brier_score_regression: float = Field(default=0.0, ge=0.0)
    max_log_loss_regression: float = Field(default=0.0, ge=0.0)
    max_expected_calibration_error_regression: float = Field(default=0.0, ge=0.0)
    min_hit_rate_delta: float = -1.0
    require_feature_not_after_prediction: bool = True
    require_feature_before_kickoff: bool = True


class HistoricalPrematchFeatureAblationGridCandidate(BaseModel):
    rank: int = Field(default=1, ge=1)
    candidate_id: str
    ablation_report_key: str
    options_json: dict[str, object] = Field(default_factory=dict)
    validation_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    skipped_reason_counts: dict[str, int] = Field(default_factory=dict)
    candidate: HistoricalPrematchFeatureAblationMetricSet
    baseline: HistoricalPrematchFeatureAblationMetricSet
    deltas_json: dict[str, object] = Field(default_factory=dict)
    passed_non_regression_gate: bool
    ranking_score: float | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchFeatureAblationGridReport(BaseModel):
    report_key: str
    status: HistoricalPrematchFeatureAblationGridStatus
    grid_id: str
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    non_regression_candidate_count: int = Field(ge=0)
    best_candidate: HistoricalPrematchFeatureAblationGridCandidate
    best_brier_candidate: HistoricalPrematchFeatureAblationGridCandidate
    best_hit_rate_candidate: HistoricalPrematchFeatureAblationGridCandidate
    candidates: list[HistoricalPrematchFeatureAblationGridCandidate] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_prematch_feature_ablation_grid_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPrematchFeatureAblationGridOptions | None = None,
) -> HistoricalPrematchFeatureAblationGridReport:
    resolved_options = options or HistoricalPrematchFeatureAblationGridOptions()
    candidates = [
        _candidate_from_report(
            build_historical_prematch_feature_ablation_report(
                historical_slices,
                options=ablation_options,
            ),
            ablation_options=ablation_options,
            grid_options=resolved_options,
            candidate_index=candidate_index,
        )
        for candidate_index, ablation_options in enumerate(
            _ablation_options_grid(resolved_options),
            start=1,
        )
    ]
    if not candidates:
        raise ValueError("prematch feature ablation grid produced no candidates")

    ranked_candidates = [
        candidate.model_copy(update={"rank": rank})
        for rank, candidate in enumerate(
            sorted(candidates, key=_candidate_sort_key),
            start=1,
        )
    ]
    best_candidate = ranked_candidates[0]
    best_brier_candidate = min(
        ranked_candidates,
        key=lambda item: _none_last(
            _float_delta(item.deltas_json, "brier_score_delta")
        ),
    )
    best_hit_rate_candidate = max(
        ranked_candidates,
        key=lambda item: _none_first(_float_delta(item.deltas_json, "hit_rate_delta")),
    )
    non_regression_candidate_count = sum(
        1 for candidate in ranked_candidates if candidate.passed_non_regression_gate
    )
    warnings = _grid_warnings(
        ranked_candidates,
        non_regression_candidate_count=non_regression_candidate_count,
    )
    report_key = _grid_report_key(
        historical_slices,
        options=resolved_options,
        candidate_count=len(ranked_candidates),
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_prematch_feature_ablation_grid_v3_1",
        "report_key": report_key,
        "grid_id": resolved_options.grid_id,
        "shadow_only": True,
        "slice_count": len(historical_slices),
        "fixture_count": sum(len(item.fixtures) for item in historical_slices),
        "candidate_count": len(ranked_candidates),
        "non_regression_candidate_count": non_regression_candidate_count,
        "best_candidate_id": best_candidate.candidate_id,
        "best_brier_candidate_id": best_brier_candidate.candidate_id,
        "best_hit_rate_candidate_id": best_hit_rate_candidate.candidate_id,
        "best_candidate_options": best_candidate.options_json,
        "best_candidate_deltas": best_candidate.deltas_json,
        "warnings": warnings,
    }
    return HistoricalPrematchFeatureAblationGridReport(
        report_key=report_key,
        status="generated",
        grid_id=resolved_options.grid_id,
        slice_count=len(historical_slices),
        fixture_count=sum(len(item.fixtures) for item in historical_slices),
        candidate_count=len(ranked_candidates),
        non_regression_candidate_count=non_regression_candidate_count,
        best_candidate=best_candidate,
        best_brier_candidate=best_brier_candidate,
        best_hit_rate_candidate=best_hit_rate_candidate,
        candidates=ranked_candidates,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_prematch_feature_ablation_grid_report(
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


def _candidate_from_report(
    report: HistoricalPrematchFeatureAblationReport,
    *,
    ablation_options: HistoricalPrematchFeatureAblationOptions,
    grid_options: HistoricalPrematchFeatureAblationGridOptions,
    candidate_index: int,
) -> HistoricalPrematchFeatureAblationGridCandidate:
    passed_gate = _passes_non_regression_gate(report, options=grid_options)
    ranking_score = _ranking_score(report)
    candidate_id = f"{grid_options.grid_id}:candidate_{candidate_index:04d}"
    summary: dict[str, object] = {
        "candidate_id": candidate_id,
        "ablation_report_key": report.report_key,
        "passed_non_regression_gate": passed_gate,
        "ranking_score": ranking_score,
        "validation_count": report.validation_count,
        "skipped_count": report.skipped_count,
        "candidate_metrics": report.overall.candidate.model_dump(mode="json"),
        "baseline_metrics": report.overall.baseline.model_dump(mode="json"),
        "deltas_json": report.overall.deltas_json,
    }
    return HistoricalPrematchFeatureAblationGridCandidate(
        candidate_id=candidate_id,
        ablation_report_key=report.report_key,
        options_json=ablation_options.model_dump(mode="json"),
        validation_count=report.validation_count,
        skipped_count=report.skipped_count,
        skipped_reason_counts=report.skipped_reason_counts,
        candidate=report.overall.candidate,
        baseline=report.overall.baseline,
        deltas_json=report.overall.deltas_json,
        passed_non_regression_gate=passed_gate,
        ranking_score=ranking_score,
        warnings=report.warnings,
        summary_json=summary,
    )


def _ablation_options_grid(
    options: HistoricalPrematchFeatureAblationGridOptions,
) -> list[HistoricalPrematchFeatureAblationOptions]:
    ablation_options: list[HistoricalPrematchFeatureAblationOptions] = []
    seen_payloads: set[str] = set()
    for (
        max_probability_shift,
        odds_movement_weight,
        tracked_fragility_weight,
        lineup_strength_weight,
        draw_signal_weight,
    ) in product(
        options.max_probability_shifts,
        options.odds_movement_weights,
        options.tracked_fragility_weights,
        options.lineup_strength_weights,
        options.draw_signal_weights,
    ):
        candidate = HistoricalPrematchFeatureAblationOptions(
            min_feature_data_quality_score=options.min_feature_data_quality_score,
            max_probability_shift=max_probability_shift,
            odds_movement_weight=odds_movement_weight,
            tracked_fragility_weight=tracked_fragility_weight,
            lineup_strength_weight=lineup_strength_weight,
            draw_signal_weight=draw_signal_weight,
            bucket_size=options.bucket_size,
            min_bucket_sample_size=options.min_bucket_sample_size,
            prediction_sample_limit=options.prediction_sample_limit,
            require_feature_not_after_prediction=(
                options.require_feature_not_after_prediction
            ),
            require_feature_before_kickoff=options.require_feature_before_kickoff,
        )
        payload = dumps(candidate.model_dump(mode="json"), sort_keys=True)
        if payload in seen_payloads:
            continue
        seen_payloads.add(payload)
        ablation_options.append(candidate)
    return ablation_options


def _passes_non_regression_gate(
    report: HistoricalPrematchFeatureAblationReport,
    *,
    options: HistoricalPrematchFeatureAblationGridOptions,
) -> bool:
    if report.validation_count <= 0:
        return False
    return (
        _float_delta(report.overall.deltas_json, "brier_score_delta")
        <= options.max_brier_score_regression
        and _float_delta(report.overall.deltas_json, "log_loss_delta")
        <= options.max_log_loss_regression
        and _float_delta(report.overall.deltas_json, "expected_calibration_error_delta")
        <= options.max_expected_calibration_error_regression
        and _float_delta(report.overall.deltas_json, "hit_rate_delta")
        >= options.min_hit_rate_delta
    )


def _ranking_score(report: HistoricalPrematchFeatureAblationReport) -> float | None:
    brier_delta = _optional_float_delta(report.overall.deltas_json, "brier_score_delta")
    log_loss_delta = _optional_float_delta(report.overall.deltas_json, "log_loss_delta")
    hit_rate_delta = _optional_float_delta(report.overall.deltas_json, "hit_rate_delta")
    calibration_delta = _optional_float_delta(
        report.overall.deltas_json,
        "expected_calibration_error_delta",
    )
    if brier_delta is None or log_loss_delta is None or hit_rate_delta is None:
        return None
    return (
        brier_delta
        + 0.25 * log_loss_delta
        + 0.50 * (calibration_delta or 0.0)
        - 0.10 * hit_rate_delta
    )


def _candidate_sort_key(
    candidate: HistoricalPrematchFeatureAblationGridCandidate,
) -> tuple[int, float, float, float, float]:
    return (
        0 if candidate.passed_non_regression_gate else 1,
        _none_last(candidate.ranking_score),
        _none_last(_float_delta(candidate.deltas_json, "brier_score_delta")),
        _none_last(_float_delta(candidate.deltas_json, "log_loss_delta")),
        -_none_first(_float_delta(candidate.deltas_json, "hit_rate_delta")),
    )


def _grid_warnings(
    candidates: Sequence[HistoricalPrematchFeatureAblationGridCandidate],
    *,
    non_regression_candidate_count: int,
) -> list[str]:
    warnings: list[str] = []
    if non_regression_candidate_count == 0:
        warnings.append("historical_prematch_feature_ablation_grid:no_passing_candidate")
    if all(candidate.validation_count == 0 for candidate in candidates):
        warnings.append("historical_prematch_feature_ablation_grid:no_validation_fixtures")
    if any(candidate.skipped_count > 0 for candidate in candidates):
        warnings.append("historical_prematch_feature_ablation_grid:skipped_fixtures")
    return warnings


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Run a shadow parameter grid for structured pre-match FeatureSnapshot "
            "ablation."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--grid-id", default=DEFAULT_PREMATCH_FEATURE_ABLATION_GRID_ID)
    parser.add_argument("--min-feature-data-quality-score", type=float, default=70.0)
    parser.add_argument(
        "--max-probability-shifts",
        type=_float_tuple,
        default=(0.0, 0.04, 0.08, 0.12),
    )
    parser.add_argument(
        "--odds-movement-weights",
        type=_float_tuple,
        default=(0.0, 0.20, 0.35, 0.50),
    )
    parser.add_argument(
        "--tracked-fragility-weights",
        type=_float_tuple,
        default=(0.0, 0.50, 1.0),
    )
    parser.add_argument("--lineup-strength-weights", type=_float_tuple, default=(0.0,))
    parser.add_argument(
        "--draw-signal-weights",
        type=_float_tuple,
        default=(0.0, 0.25, 0.35),
    )
    parser.add_argument("--bucket-size", type=float, default=0.10)
    parser.add_argument("--min-bucket-sample-size", type=int, default=1)
    parser.add_argument("--prediction-sample-limit", type=int, default=0)
    parser.add_argument("--max-brier-score-regression", type=float, default=0.0)
    parser.add_argument("--max-log-loss-regression", type=float, default=0.0)
    parser.add_argument(
        "--max-expected-calibration-error-regression",
        type=float,
        default=0.0,
    )
    parser.add_argument("--min-hit-rate-delta", type=float, default=-1.0)
    parser.add_argument("--allow-feature-after-prediction", action="store_true")
    parser.add_argument("--allow-feature-not-before-kickoff", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalPrematchFeatureAblationGridOptions:
    return HistoricalPrematchFeatureAblationGridOptions(
        grid_id=args.grid_id,
        min_feature_data_quality_score=args.min_feature_data_quality_score,
        max_probability_shifts=args.max_probability_shifts,
        odds_movement_weights=args.odds_movement_weights,
        tracked_fragility_weights=args.tracked_fragility_weights,
        lineup_strength_weights=args.lineup_strength_weights,
        draw_signal_weights=args.draw_signal_weights,
        bucket_size=args.bucket_size,
        min_bucket_sample_size=args.min_bucket_sample_size,
        prediction_sample_limit=args.prediction_sample_limit,
        max_brier_score_regression=args.max_brier_score_regression,
        max_log_loss_regression=args.max_log_loss_regression,
        max_expected_calibration_error_regression=(
            args.max_expected_calibration_error_regression
        ),
        min_hit_rate_delta=args.min_hit_rate_delta,
        require_feature_not_after_prediction=not args.allow_feature_after_prediction,
        require_feature_before_kickoff=not args.allow_feature_not_before_kickoff,
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


def _grid_report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPrematchFeatureAblationGridOptions,
    candidate_count: int,
) -> str:
    payload = {
        "slice_ids": [
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        "as_of_times": [
            historical_slice.as_of_time_utc.isoformat()
            for historical_slice in historical_slices
        ],
        "candidate_count": candidate_count,
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_prematch_feature_ablation_grid:{digest}"


def _float_tuple(value: str) -> tuple[float, ...]:
    parsed = tuple(float(part.strip()) for part in value.split(",") if part.strip())
    if not parsed:
        raise ValueError("expected at least one comma-separated float")
    return parsed


def _float_delta(deltas: Mapping[str, object], key: str) -> float:
    return _optional_float_delta(deltas, key) or 0.0


def _optional_float_delta(deltas: Mapping[str, object], key: str) -> float | None:
    value = deltas.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _none_last(value: float | None) -> float:
    return 1_000_000_000.0 if value is None else value


def _none_first(value: float | None) -> float:
    return -1_000_000_000.0 if value is None else value
