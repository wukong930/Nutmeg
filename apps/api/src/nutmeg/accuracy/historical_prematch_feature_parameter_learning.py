from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Sequence
from hashlib import sha256
from itertools import product
from json import dumps
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.historical_prematch_feature_ablation import (
    HistoricalPrematchFeatureAblationComparisonGroup,
    HistoricalPrematchFeatureAblationMetricSet,
    HistoricalPrematchFeatureAblationOptions,
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

type HistoricalPrematchFeatureParameterLearningStatus = Literal["generated"]
type HistoricalPrematchFeatureParameterSelectionMetric = Literal[
    "brier_score_delta",
    "log_loss_delta",
    "expected_calibration_error_delta",
]

CALIBRATION_DELTA_EPSILON = 1e-12


class HistoricalPrematchFeatureParameterLearningOptions(BaseModel):
    holdout_season_count: int = Field(default=1, ge=1)
    min_training_season_count: int = Field(default=2, ge=1)
    min_training_sample_size: int = Field(default=20, ge=1)
    min_validation_sample_size: int = Field(default=20, ge=1)
    selection_metric: HistoricalPrematchFeatureParameterSelectionMetric = (
        "brier_score_delta"
    )
    max_training_expected_calibration_error_delta: float = Field(default=0.0, ge=0.0)
    max_validation_expected_calibration_error_delta: float = Field(default=0.0, ge=0.0)
    min_feature_data_quality_score: float = Field(default=70.0, ge=0.0, le=100.0)
    max_probability_shifts: tuple[float, ...] = (0.0, 0.04, 0.08, 0.12)
    odds_movement_weights: tuple[float, ...] = (0.0, 0.20, 0.35, 0.50)
    tracked_fragility_weights: tuple[float, ...] = (0.0, 0.50, 1.0)
    lineup_strength_weights: tuple[float, ...] = (0.0,)
    draw_signal_weights: tuple[float, ...] = (0.0, 0.25, 0.35)
    bucket_size: float = Field(default=0.10, gt=0.0, le=1.0)
    min_bucket_sample_size: int = Field(default=1, ge=1)
    prediction_sample_limit: int = Field(default=0, ge=0)
    require_feature_not_after_prediction: bool = True
    require_feature_before_kickoff: bool = True


class HistoricalPrematchFeatureParameterCandidate(BaseModel):
    candidate_key: str
    max_probability_shift: float = Field(ge=0.0, le=0.35)
    odds_movement_weight: float = Field(ge=0.0, le=2.0)
    tracked_fragility_weight: float = Field(ge=0.0, le=2.0)
    lineup_strength_weight: float = Field(ge=0.0, le=2.0)
    draw_signal_weight: float = Field(ge=0.0, le=2.0)


class HistoricalPrematchFeatureParameterCandidateTrainingResult(BaseModel):
    candidate: HistoricalPrematchFeatureParameterCandidate
    training_report_key: str
    training_sample_size: int = Field(ge=0)
    training_candidate: HistoricalPrematchFeatureAblationMetricSet
    training_baseline: HistoricalPrematchFeatureAblationMetricSet
    training_deltas_json: dict[str, object] = Field(default_factory=dict)
    selection_metric_value: float | None = None


class HistoricalPrematchFeatureCompetitionParameterLearningResult(BaseModel):
    competition_id: str
    training_seasons: list[str] = Field(default_factory=list)
    validation_seasons: list[str] = Field(default_factory=list)
    candidate_count: int = Field(ge=0)
    training_fixture_count: int = Field(ge=0)
    validation_fixture_count: int = Field(ge=0)
    selected_candidate: HistoricalPrematchFeatureParameterCandidate | None = None
    selected_training_result: (
        HistoricalPrematchFeatureParameterCandidateTrainingResult | None
    ) = None
    selected_validation_report_key: str | None = None
    selected_validation: HistoricalPrematchFeatureAblationComparisonGroup | None = None
    baseline_validation: HistoricalPrematchFeatureAblationMetricSet | None = None
    status: str
    warnings: list[str] = Field(default_factory=list)
    training_results: list[HistoricalPrematchFeatureParameterCandidateTrainingResult] = (
        Field(default_factory=list)
    )
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalPrematchFeatureParameterLearningReport(BaseModel):
    report_key: str
    status: HistoricalPrematchFeatureParameterLearningStatus
    competition_count: int = Field(ge=0)
    learned_competition_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    validation_count: int = Field(ge=0)
    selected_candidate_counts: dict[str, int] = Field(default_factory=dict)
    overall_validation_candidate: HistoricalPrematchFeatureAblationMetricSet | None = (
        None
    )
    overall_validation_baseline: HistoricalPrematchFeatureAblationMetricSet | None = (
        None
    )
    overall_validation_deltas_json: dict[str, object] = Field(default_factory=dict)
    competitions: list[HistoricalPrematchFeatureCompetitionParameterLearningResult] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_prematch_feature_parameter_learning_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalPrematchFeatureParameterLearningOptions | None = None,
) -> HistoricalPrematchFeatureParameterLearningReport:
    resolved_options = options or HistoricalPrematchFeatureParameterLearningOptions()
    candidates = _candidate_grid(resolved_options)
    competition_results = [
        _competition_learning_result(
            competition_id,
            slices=competition_slices,
            candidates=candidates,
            options=resolved_options,
        )
        for competition_id, competition_slices in sorted(
            _slices_by_competition(historical_slices).items()
        )
    ]
    learned_results = [
        result
        for result in competition_results
        if result.status in {"learned", "learned_with_warnings"}
    ]
    overall_candidate = _combine_metric_sets(
        [
            result.selected_validation.candidate
            for result in learned_results
            if result.selected_validation is not None
        ]
    )
    overall_baseline = _combine_metric_sets(
        [
            result.selected_validation.baseline
            for result in learned_results
            if result.selected_validation is not None
        ]
    )
    selected_counts = Counter(
        result.selected_candidate.candidate_key
        for result in learned_results
        if result.selected_candidate is not None
    )
    warnings = [
        warning for result in competition_results for warning in result.warnings
    ]
    if not learned_results:
        warnings.append("prematch_feature_parameter_learning:no_learned_competitions")
    report_key = _report_key(
        historical_slices,
        candidates=candidates,
        options=resolved_options,
    )
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    validation_count = (
        overall_candidate.sample_size if overall_candidate is not None else 0
    )
    deltas = (
        _metric_deltas(overall_candidate, overall_baseline)
        if overall_candidate is not None and overall_baseline is not None
        else {}
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_prematch_feature_parameter_learning_v3_1",
        "report_key": report_key,
        "selection_metric": resolved_options.selection_metric,
        "max_training_expected_calibration_error_delta": (
            resolved_options.max_training_expected_calibration_error_delta
        ),
        "max_validation_expected_calibration_error_delta": (
            resolved_options.max_validation_expected_calibration_error_delta
        ),
        "holdout_season_count": resolved_options.holdout_season_count,
        "candidate_count": len(candidates),
        "competition_count": len(competition_results),
        "learned_competition_count": len(learned_results),
        "fixture_count": fixture_count,
        "validation_count": validation_count,
        "selected_candidate_counts": dict(selected_counts),
        "overall_validation_deltas_json": deltas,
        "shadow_only": True,
        "warnings": warnings,
    }
    return HistoricalPrematchFeatureParameterLearningReport(
        report_key=report_key,
        status="generated",
        competition_count=len(competition_results),
        learned_competition_count=len(learned_results),
        candidate_count=len(candidates),
        fixture_count=fixture_count,
        validation_count=validation_count,
        selected_candidate_counts=dict(selected_counts),
        overall_validation_candidate=overall_candidate,
        overall_validation_baseline=overall_baseline,
        overall_validation_deltas_json=deltas,
        competitions=competition_results,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_prematch_feature_parameter_learning_report(
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


def _competition_learning_result(
    competition_id: str,
    *,
    slices: Sequence[HistoricalRecommendationSlice],
    candidates: Sequence[HistoricalPrematchFeatureParameterCandidate],
    options: HistoricalPrematchFeatureParameterLearningOptions,
) -> HistoricalPrematchFeatureCompetitionParameterLearningResult:
    sorted_slices = sorted(slices, key=_slice_sort_key)
    holdout_count = min(options.holdout_season_count, len(sorted_slices))
    training_slices = sorted_slices[:-holdout_count]
    validation_slices = sorted_slices[-holdout_count:]
    training_seasons = [_slice_season(slice_item) for slice_item in training_slices]
    validation_seasons = [_slice_season(slice_item) for slice_item in validation_slices]
    training_fixture_count = sum(len(slice_item.fixtures) for slice_item in training_slices)
    validation_fixture_count = sum(len(slice_item.fixtures) for slice_item in validation_slices)
    warnings: list[str] = []
    if len(training_slices) < options.min_training_season_count:
        warnings.append(
            f"prematch_feature_parameter_learning:{competition_id}:insufficient_training_seasons"
        )
        return _skipped_competition_result(
            competition_id,
            training_seasons=training_seasons,
            validation_seasons=validation_seasons,
            candidate_count=len(candidates),
            training_fixture_count=training_fixture_count,
            validation_fixture_count=validation_fixture_count,
            warnings=warnings,
        )

    training_results = [
        _candidate_training_result(
            candidate,
            training_slices=training_slices,
            options=options,
        )
        for candidate in candidates
    ]
    selected_training = _select_candidate(training_results, options=options)
    if selected_training is None:
        warnings.append(
            f"prematch_feature_parameter_learning:{competition_id}:no_selectable_candidate"
        )
        return _skipped_competition_result(
            competition_id,
            training_seasons=training_seasons,
            validation_seasons=validation_seasons,
            candidate_count=len(candidates),
            training_fixture_count=training_fixture_count,
            validation_fixture_count=validation_fixture_count,
            warnings=warnings,
            training_results=training_results,
        )

    validation_report = build_historical_prematch_feature_ablation_report(
        validation_slices,
        options=_ablation_options(selected_training.candidate, options=options),
    )
    validation_group = validation_report.overall
    if _validation_ece_regressed(validation_group, options=options):
        noop_training = _noop_training_result(training_results, options=options)
        if noop_training is not None and noop_training != selected_training:
            warnings.append(
                f"prematch_feature_parameter_learning:{competition_id}:"
                "validation_ece_regression_fallback_to_noop"
            )
            selected_training = noop_training
            validation_report = build_historical_prematch_feature_ablation_report(
                validation_slices,
                options=_ablation_options(selected_training.candidate, options=options),
            )
            validation_group = validation_report.overall
        else:
            warnings.append(
                f"prematch_feature_parameter_learning:{competition_id}:"
                "validation_ece_regressed"
            )
    if validation_group.validation_count < options.min_validation_sample_size:
        warnings.append(
            f"prematch_feature_parameter_learning:{competition_id}:insufficient_validation_samples"
        )
    status = "learned" if not warnings else "learned_with_warnings"
    summary: dict[str, object] = {
        "calculation_basis": "historical_prematch_feature_competition_parameter_learning_v3_1",
        "competition_id": competition_id,
        "training_seasons": training_seasons,
        "validation_seasons": validation_seasons,
        "candidate_count": len(candidates),
        "selected_candidate": selected_training.candidate.model_dump(mode="json"),
        "selection_metric": options.selection_metric,
        "selection_metric_value": selected_training.selection_metric_value,
        "max_training_expected_calibration_error_delta": (
            options.max_training_expected_calibration_error_delta
        ),
        "max_validation_expected_calibration_error_delta": (
            options.max_validation_expected_calibration_error_delta
        ),
        "selected_validation_report_key": validation_report.report_key,
        "selected_validation_deltas_json": validation_group.deltas_json,
        "status": status,
        "warnings": warnings,
    }
    return HistoricalPrematchFeatureCompetitionParameterLearningResult(
        competition_id=competition_id,
        training_seasons=training_seasons,
        validation_seasons=validation_seasons,
        candidate_count=len(candidates),
        training_fixture_count=training_fixture_count,
        validation_fixture_count=validation_fixture_count,
        selected_candidate=selected_training.candidate,
        selected_training_result=selected_training,
        selected_validation_report_key=validation_report.report_key,
        selected_validation=validation_group,
        baseline_validation=validation_group.baseline,
        status=status,
        warnings=warnings,
        training_results=training_results,
        summary_json=summary,
    )


def _candidate_training_result(
    candidate: HistoricalPrematchFeatureParameterCandidate,
    *,
    training_slices: Sequence[HistoricalRecommendationSlice],
    options: HistoricalPrematchFeatureParameterLearningOptions,
) -> HistoricalPrematchFeatureParameterCandidateTrainingResult:
    training_report = build_historical_prematch_feature_ablation_report(
        training_slices,
        options=_ablation_options(candidate, options=options),
    )
    selection_metric_value = _selection_metric_value(
        training_report.overall.deltas_json,
        metric=options.selection_metric,
    )
    return HistoricalPrematchFeatureParameterCandidateTrainingResult(
        candidate=candidate,
        training_report_key=training_report.report_key,
        training_sample_size=training_report.validation_count,
        training_candidate=training_report.overall.candidate,
        training_baseline=training_report.overall.baseline,
        training_deltas_json=training_report.overall.deltas_json,
        selection_metric_value=selection_metric_value,
    )


def _candidate_grid(
    options: HistoricalPrematchFeatureParameterLearningOptions,
) -> list[HistoricalPrematchFeatureParameterCandidate]:
    candidates: list[HistoricalPrematchFeatureParameterCandidate] = []
    seen_payloads: set[str] = set()
    for (
        max_probability_shift,
        odds_movement_weight,
        tracked_fragility_weight,
        lineup_strength_weight,
        draw_signal_weight,
    ) in product(
        tuple(dict.fromkeys(options.max_probability_shifts)),
        tuple(dict.fromkeys(options.odds_movement_weights)),
        tuple(dict.fromkeys(options.tracked_fragility_weights)),
        tuple(dict.fromkeys(options.lineup_strength_weights)),
        tuple(dict.fromkeys(options.draw_signal_weights)),
    ):
        candidate = HistoricalPrematchFeatureParameterCandidate(
            candidate_key=_candidate_key(
                max_probability_shift=max_probability_shift,
                odds_movement_weight=odds_movement_weight,
                tracked_fragility_weight=tracked_fragility_weight,
                lineup_strength_weight=lineup_strength_weight,
                draw_signal_weight=draw_signal_weight,
            ),
            max_probability_shift=max_probability_shift,
            odds_movement_weight=odds_movement_weight,
            tracked_fragility_weight=tracked_fragility_weight,
            lineup_strength_weight=lineup_strength_weight,
            draw_signal_weight=draw_signal_weight,
        )
        payload = candidate.model_dump_json()
        if payload in seen_payloads:
            continue
        seen_payloads.add(payload)
        candidates.append(candidate)
    return candidates


def _ablation_options(
    candidate: HistoricalPrematchFeatureParameterCandidate,
    *,
    options: HistoricalPrematchFeatureParameterLearningOptions,
) -> HistoricalPrematchFeatureAblationOptions:
    return HistoricalPrematchFeatureAblationOptions(
        min_feature_data_quality_score=options.min_feature_data_quality_score,
        max_probability_shift=candidate.max_probability_shift,
        odds_movement_weight=candidate.odds_movement_weight,
        tracked_fragility_weight=candidate.tracked_fragility_weight,
        lineup_strength_weight=candidate.lineup_strength_weight,
        draw_signal_weight=candidate.draw_signal_weight,
        bucket_size=options.bucket_size,
        min_bucket_sample_size=options.min_bucket_sample_size,
        prediction_sample_limit=options.prediction_sample_limit,
        require_feature_not_after_prediction=options.require_feature_not_after_prediction,
        require_feature_before_kickoff=options.require_feature_before_kickoff,
    )


def _select_candidate(
    training_results: Sequence[HistoricalPrematchFeatureParameterCandidateTrainingResult],
    *,
    options: HistoricalPrematchFeatureParameterLearningOptions,
) -> HistoricalPrematchFeatureParameterCandidateTrainingResult | None:
    selectable = [
        result
        for result in training_results
        if result.selection_metric_value is not None
        and result.training_sample_size >= options.min_training_sample_size
    ]
    if not selectable:
        return None
    calibration_safe = [
        result
        for result in selectable
        if _metric_within_max_delta(
            _training_metric_value(result, "expected_calibration_error_delta"),
            options.max_training_expected_calibration_error_delta,
        )
    ]
    if not calibration_safe:
        return None
    return min(
        calibration_safe,
        key=lambda result: (
            result.selection_metric_value
            if result.selection_metric_value is not None
            else float("inf"),
            _training_metric_value(result, "expected_calibration_error_delta"),
            result.candidate.candidate_key,
        ),
    )


def _skipped_competition_result(
    competition_id: str,
    *,
    training_seasons: Sequence[str],
    validation_seasons: Sequence[str],
    candidate_count: int,
    training_fixture_count: int,
    validation_fixture_count: int,
    warnings: Sequence[str],
    training_results: Sequence[HistoricalPrematchFeatureParameterCandidateTrainingResult] = (),
) -> HistoricalPrematchFeatureCompetitionParameterLearningResult:
    return HistoricalPrematchFeatureCompetitionParameterLearningResult(
        competition_id=competition_id,
        training_seasons=list(training_seasons),
        validation_seasons=list(validation_seasons),
        candidate_count=candidate_count,
        training_fixture_count=training_fixture_count,
        validation_fixture_count=validation_fixture_count,
        status="skipped",
        warnings=list(warnings),
        training_results=list(training_results),
        summary_json={
            "calculation_basis": "historical_prematch_feature_competition_parameter_learning_v3_1",
            "competition_id": competition_id,
            "status": "skipped",
            "warnings": list(warnings),
        },
    )


def _combine_metric_sets(
    metric_sets: Sequence[HistoricalPrematchFeatureAblationMetricSet],
) -> HistoricalPrematchFeatureAblationMetricSet | None:
    sample_size = sum(metric.sample_size for metric in metric_sets)
    if sample_size == 0:
        return None
    return HistoricalPrematchFeatureAblationMetricSet(
        sample_size=sample_size,
        hit_count=sum(metric.hit_count for metric in metric_sets),
        hit_rate=_safe_divide(sum(metric.hit_count for metric in metric_sets), sample_size),
        brier_score=_weighted_metric(metric_sets, "brier_score"),
        log_loss=_weighted_metric(metric_sets, "log_loss"),
        average_actual_probability=_weighted_metric(
            metric_sets,
            "average_actual_probability",
        ),
        expected_calibration_error=_weighted_metric(
            metric_sets,
            "expected_calibration_error",
        ),
        calibration_observation_count=sum(
            metric.calibration_observation_count for metric in metric_sets
        ),
        included_calibration_bucket_count=sum(
            metric.included_calibration_bucket_count for metric in metric_sets
        ),
        skipped_small_calibration_bucket_count=sum(
            metric.skipped_small_calibration_bucket_count for metric in metric_sets
        ),
    )


def _weighted_metric(
    metric_sets: Sequence[HistoricalPrematchFeatureAblationMetricSet],
    metric_name: str,
) -> float | None:
    numerator = 0.0
    denominator = 0
    for metric in metric_sets:
        value = getattr(metric, metric_name)
        if value is None:
            continue
        numerator += value * metric.sample_size
        denominator += metric.sample_size
    return _safe_divide(numerator, denominator)


def _metric_deltas(
    candidate: HistoricalPrematchFeatureAblationMetricSet,
    baseline: HistoricalPrematchFeatureAblationMetricSet,
) -> dict[str, object]:
    return {
        "hit_rate_delta": _optional_delta(candidate.hit_rate, baseline.hit_rate),
        "brier_score_delta": _optional_delta(
            candidate.brier_score,
            baseline.brier_score,
        ),
        "log_loss_delta": _optional_delta(candidate.log_loss, baseline.log_loss),
        "average_actual_probability_delta": _optional_delta(
            candidate.average_actual_probability,
            baseline.average_actual_probability,
        ),
        "expected_calibration_error_delta": _optional_delta(
            candidate.expected_calibration_error,
            baseline.expected_calibration_error,
        ),
    }


def _selection_metric_value(
    deltas_json: dict[str, object],
    *,
    metric: HistoricalPrematchFeatureParameterSelectionMetric,
) -> float | None:
    value = deltas_json.get(metric)
    if isinstance(value, int | float):
        return float(value)
    return None


def _training_metric_value(
    result: HistoricalPrematchFeatureParameterCandidateTrainingResult,
    metric: HistoricalPrematchFeatureParameterSelectionMetric,
) -> float:
    value = _selection_metric_value(result.training_deltas_json, metric=metric)
    return value if value is not None else float("inf")


def _validation_ece_regressed(
    validation_group: HistoricalPrematchFeatureAblationComparisonGroup,
    *,
    options: HistoricalPrematchFeatureParameterLearningOptions,
) -> bool:
    value = _selection_metric_value(
        validation_group.deltas_json,
        metric="expected_calibration_error_delta",
    )
    if value is None:
        return False
    return not _metric_within_max_delta(
        value,
        options.max_validation_expected_calibration_error_delta,
    )


def _metric_within_max_delta(value: float, max_delta: float) -> bool:
    return value <= max_delta + CALIBRATION_DELTA_EPSILON


def _noop_training_result(
    training_results: Sequence[HistoricalPrematchFeatureParameterCandidateTrainingResult],
    *,
    options: HistoricalPrematchFeatureParameterLearningOptions,
) -> HistoricalPrematchFeatureParameterCandidateTrainingResult | None:
    for result in training_results:
        if (
            _candidate_is_noop(result.candidate)
            and result.selection_metric_value is not None
            and result.training_sample_size >= options.min_training_sample_size
        ):
            return result
    return None


def _candidate_is_noop(candidate: HistoricalPrematchFeatureParameterCandidate) -> bool:
    max_shift_zero = abs(candidate.max_probability_shift) <= CALIBRATION_DELTA_EPSILON
    feature_weights_zero = (
        abs(candidate.odds_movement_weight) <= CALIBRATION_DELTA_EPSILON
        and abs(candidate.tracked_fragility_weight) <= CALIBRATION_DELTA_EPSILON
        and abs(candidate.lineup_strength_weight) <= CALIBRATION_DELTA_EPSILON
        and abs(candidate.draw_signal_weight) <= CALIBRATION_DELTA_EPSILON
    )
    return max_shift_zero or feature_weights_zero


def _slices_by_competition(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> dict[str, list[HistoricalRecommendationSlice]]:
    grouped: dict[str, list[HistoricalRecommendationSlice]] = {}
    for historical_slice in historical_slices:
        grouped.setdefault(historical_slice.metadata.competition_id, []).append(
            historical_slice
        )
    return grouped


def _slice_sort_key(historical_slice: HistoricalRecommendationSlice) -> tuple[str, str]:
    return (
        historical_slice.metadata.season or "",
        historical_slice.metadata.slice_id,
    )


def _slice_season(historical_slice: HistoricalRecommendationSlice) -> str:
    return historical_slice.metadata.season or "unknown"


def _candidate_key(
    *,
    max_probability_shift: float,
    odds_movement_weight: float,
    tracked_fragility_weight: float,
    lineup_strength_weight: float,
    draw_signal_weight: float,
) -> str:
    return (
        f"shift_{_weight_key(max_probability_shift)}"
        f"_odds_{_weight_key(odds_movement_weight)}"
        f"_fragility_{_weight_key(tracked_fragility_weight)}"
        f"_lineup_{_weight_key(lineup_strength_weight)}"
        f"_draw_{_weight_key(draw_signal_weight)}"
    )


def _weight_key(value: float) -> str:
    return str(value).replace("-", "neg_").replace(".", "_")


def _report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    candidates: Sequence[HistoricalPrematchFeatureParameterCandidate],
    options: HistoricalPrematchFeatureParameterLearningOptions,
) -> str:
    payload = {
        "slice_ids": [
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        "candidate_keys": [candidate.candidate_key for candidate in candidates],
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_prematch_feature_parameter_learning:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Learn structured pre-match feature adjustment weights with "
            "competition holdout validation."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--holdout-season-count", type=int, default=1)
    parser.add_argument("--min-training-season-count", type=int, default=2)
    parser.add_argument("--min-training-sample-size", type=int, default=20)
    parser.add_argument("--min-validation-sample-size", type=int, default=20)
    parser.add_argument(
        "--selection-metric",
        choices=[
            "brier_score_delta",
            "log_loss_delta",
            "expected_calibration_error_delta",
        ],
        default="brier_score_delta",
    )
    parser.add_argument(
        "--max-training-expected-calibration-error-delta",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--max-validation-expected-calibration-error-delta",
        type=float,
        default=0.0,
    )
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
    parser.add_argument("--allow-feature-after-prediction", action="store_true")
    parser.add_argument("--allow-feature-not-before-kickoff", action="store_true")
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(
    args: Namespace,
) -> HistoricalPrematchFeatureParameterLearningOptions:
    return HistoricalPrematchFeatureParameterLearningOptions(
        holdout_season_count=args.holdout_season_count,
        min_training_season_count=args.min_training_season_count,
        min_training_sample_size=args.min_training_sample_size,
        min_validation_sample_size=args.min_validation_sample_size,
        selection_metric=args.selection_metric,
        max_training_expected_calibration_error_delta=(
            args.max_training_expected_calibration_error_delta
        ),
        max_validation_expected_calibration_error_delta=(
            args.max_validation_expected_calibration_error_delta
        ),
        min_feature_data_quality_score=args.min_feature_data_quality_score,
        max_probability_shifts=args.max_probability_shifts,
        odds_movement_weights=args.odds_movement_weights,
        tracked_fragility_weights=args.tracked_fragility_weights,
        lineup_strength_weights=args.lineup_strength_weights,
        draw_signal_weights=args.draw_signal_weights,
        bucket_size=args.bucket_size,
        min_bucket_sample_size=args.min_bucket_sample_size,
        prediction_sample_limit=args.prediction_sample_limit,
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


def _float_tuple(value: str) -> tuple[float, ...]:
    parsed = tuple(float(part.strip()) for part in value.split(",") if part.strip())
    if not parsed:
        raise ValueError("expected at least one comma-separated float")
    return parsed


def _safe_divide(numerator: float | int, denominator: float | int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline
