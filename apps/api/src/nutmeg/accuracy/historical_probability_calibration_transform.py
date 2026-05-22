from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from json import dumps
from math import floor, log
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.recommendations.historical_backtest import (
    HistoricalFixture,
    HistoricalMarketPrediction,
    HistoricalRecommendationSlice,
    load_historical_recommendation_slice,
)
from nutmeg.recommendations.historical_suite_manifest import (
    HistoricalRecommendationSuiteManifestLoadResult,
    load_historical_recommendation_suite_manifest_bundle,
)

type HistoricalProbabilityCalibrationTransformStatus = Literal["generated"]
type HistoricalProbabilityCalibrationTransformDecision = Literal[
    "accepted",
    "rejected",
]
type HistoricalProbabilityCalibrationTransformSegmentMode = Literal[
    "probability_bucket",
    "market_odds_band",
]

ONE_X_TWO_OUTCOMES = ("home_win", "draw", "away_win")
DEFAULT_LOG_LOSS_EPSILON = 1e-12


class HistoricalProbabilityCalibrationTransformOptions(BaseModel):
    holdout_season_count: int = Field(default=1, ge=1)
    min_training_season_count: int = Field(default=2, ge=1)
    min_validation_sample_size: int = Field(default=100, ge=1)
    segment_mode: HistoricalProbabilityCalibrationTransformSegmentMode = (
        "probability_bucket"
    )
    bucket_size: float = Field(default=0.10, gt=0.0, le=1.0)
    min_bucket_sample_size: int = Field(default=30, ge=1)
    blend_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    min_calibrated_probability: float = Field(default=0.01, ge=0.0, le=1.0)
    max_calibrated_probability: float = Field(default=0.95, ge=0.0, le=1.0)
    group_by_competition: bool = True
    min_hit_rate_delta: float = -0.0000001
    max_brier_score_delta: float = 0.0
    max_log_loss_delta: float = 0.0
    max_expected_calibration_error_delta: float = 0.0
    min_objective_improvement: float = 0.0
    prediction_sample_limit: int = Field(default=20, ge=0)


class HistoricalProbabilityCalibrationTransformMetricSet(BaseModel):
    sample_size: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    average_actual_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    expected_calibration_error: float | None = Field(default=None, ge=0.0)
    calibration_observation_count: int = Field(default=0, ge=0)
    included_calibration_bucket_count: int = Field(default=0, ge=0)
    skipped_small_calibration_bucket_count: int = Field(default=0, ge=0)


class HistoricalProbabilityCalibrationTransformBucket(BaseModel):
    group_key: str
    competition_id: str | None = None
    outcome: str
    segment_mode: HistoricalProbabilityCalibrationTransformSegmentMode = (
        "probability_bucket"
    )
    bucket_start: float = Field(ge=0.0, le=1.0)
    bucket_end: float = Field(ge=0.0, le=1.0)
    sample_size: int = Field(ge=0)
    predicted_probability_sum: float = Field(ge=0.0)
    average_predicted_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    actual_count: int = Field(ge=0)
    actual_frequency: float | None = Field(default=None, ge=0.0, le=1.0)
    calibrated_probability: float | None = Field(default=None, ge=0.0, le=1.0)


class HistoricalProbabilityCalibrationTransformFixtureSample(BaseModel):
    fixture_id: str
    slice_id: str
    competition_id: str
    season: str | None = None
    actual_outcome: str
    baseline_probabilities: dict[str, float]
    candidate_probabilities: dict[str, float]
    applied_segment_probabilities: dict[str, float] = Field(default_factory=dict)
    applied_bucket_keys: dict[str, str | None] = Field(default_factory=dict)
    fallback_reason_counts: dict[str, int] = Field(default_factory=dict)
    baseline_actual_probability: float = Field(ge=0.0, le=1.0)
    candidate_actual_probability: float = Field(ge=0.0, le=1.0)
    baseline_brier_score: float = Field(ge=0.0)
    candidate_brier_score: float = Field(ge=0.0)
    baseline_log_loss: float = Field(ge=0.0)
    candidate_log_loss: float = Field(ge=0.0)
    brier_score_delta_vs_baseline: float
    log_loss_delta_vs_baseline: float
    actual_probability_delta_vs_baseline: float


class HistoricalProbabilityCalibrationTransformCompetitionResult(BaseModel):
    competition_id: str
    training_seasons: list[str] = Field(default_factory=list)
    validation_seasons: list[str] = Field(default_factory=list)
    training_fixture_count: int = Field(ge=0)
    validation_fixture_count: int = Field(ge=0)
    calibration_bucket_count: int = Field(ge=0)
    usable_calibration_bucket_count: int = Field(ge=0)
    validation_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    skipped_reason_counts: dict[str, int] = Field(default_factory=dict)
    candidate: HistoricalProbabilityCalibrationTransformMetricSet
    baseline: HistoricalProbabilityCalibrationTransformMetricSet
    deltas_json: dict[str, object] = Field(default_factory=dict)
    decision: HistoricalProbabilityCalibrationTransformDecision
    decision_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sampled_predictions: list[HistoricalProbabilityCalibrationTransformFixtureSample] = (
        Field(default_factory=list)
    )
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalProbabilityCalibrationTransformReport(BaseModel):
    report_key: str
    status: HistoricalProbabilityCalibrationTransformStatus
    competition_count: int = Field(ge=0)
    learned_competition_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    validation_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    accepted_competition_count: int = Field(ge=0)
    rejected_competition_count: int = Field(ge=0)
    calibration_bucket_count: int = Field(ge=0)
    usable_calibration_bucket_count: int = Field(ge=0)
    overall_candidate: HistoricalProbabilityCalibrationTransformMetricSet | None = None
    overall_baseline: HistoricalProbabilityCalibrationTransformMetricSet | None = None
    overall_deltas_json: dict[str, object] = Field(default_factory=dict)
    competitions: list[HistoricalProbabilityCalibrationTransformCompetitionResult] = (
        Field(default_factory=list)
    )
    sampled_calibration_buckets: list[HistoricalProbabilityCalibrationTransformBucket] = (
        Field(default_factory=list)
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


@dataclass(frozen=True)
class _FixtureContext:
    slice_id: str
    season: str | None
    fixture: HistoricalFixture


@dataclass(frozen=True)
class _SkippedFixture:
    fixture_id: str
    competition_id: str
    season: str | None
    reason: str


@dataclass
class _CalibrationBucketAccumulator:
    group_key: str
    competition_id: str | None
    outcome: str
    segment_mode: HistoricalProbabilityCalibrationTransformSegmentMode
    bucket_start: float
    bucket_end: float
    sample_size: int = 0
    predicted_probability_sum: float = 0.0
    actual_count: int = 0

    def observe(self, *, predicted_probability: float, actual_occurred: bool) -> None:
        self.sample_size += 1
        self.predicted_probability_sum += predicted_probability
        self.actual_count += 1 if actual_occurred else 0


@dataclass
class _CalibrationObservationBucket:
    sample_size: int = 0
    predicted_probability_sum: float = 0.0
    actual_count: int = 0

    def observe(self, *, predicted_probability: float, actual_occurred: bool) -> None:
        self.sample_size += 1
        self.predicted_probability_sum += predicted_probability
        self.actual_count += 1 if actual_occurred else 0


@dataclass
class _MetricAccumulator:
    sample_size: int = 0
    hit_count: int = 0
    brier_score_sum: float = 0.0
    log_loss_sum: float = 0.0
    actual_probability_sum: float = 0.0
    calibration_buckets: dict[tuple[str, float, float], _CalibrationObservationBucket] = field(
        default_factory=dict
    )

    def observe(
        self,
        *,
        probabilities: Mapping[str, float],
        actual_outcome: str,
        bucket_size: float,
    ) -> None:
        self.sample_size += 1
        if _predicted_outcome(probabilities) == actual_outcome:
            self.hit_count += 1
        actual_probability = probabilities[actual_outcome]
        self.actual_probability_sum += actual_probability
        self.brier_score_sum += _brier_score(probabilities, actual_outcome)
        self.log_loss_sum += _log_loss(actual_probability)
        for outcome, probability in probabilities.items():
            bucket_start, bucket_end = _probability_bucket(probability, bucket_size)
            bucket = self.calibration_buckets.setdefault(
                (outcome, bucket_start, bucket_end),
                _CalibrationObservationBucket(),
            )
            bucket.observe(
                predicted_probability=probability,
                actual_occurred=outcome == actual_outcome,
            )


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_probability_calibration_transform_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationTransformOptions | None = None,
) -> HistoricalProbabilityCalibrationTransformReport:
    resolved_options = options or HistoricalProbabilityCalibrationTransformOptions()
    competition_results = [
        _competition_result(
            competition_id,
            slices=competition_slices,
            options=resolved_options,
        )
        for competition_id, competition_slices in sorted(
            _slices_by_competition(historical_slices).items()
        )
    ]
    learned_results = [
        result for result in competition_results if result.validation_count > 0
    ]
    overall_candidate = _combine_metric_sets(
        [result.candidate for result in learned_results]
    )
    overall_baseline = _combine_metric_sets(
        [result.baseline for result in learned_results]
    )
    overall_deltas = (
        _metric_deltas(overall_candidate, overall_baseline)
        if overall_candidate is not None and overall_baseline is not None
        else {}
    )
    warnings = [
        warning for result in competition_results for warning in result.warnings
    ]
    if not learned_results:
        warnings.append("historical_probability_calibration_transform:no_validation")
    report_key = _report_key(historical_slices, options=resolved_options)
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    validation_count = sum(result.validation_count for result in competition_results)
    skipped_count = sum(result.skipped_count for result in competition_results)
    accepted_count = sum(1 for result in competition_results if result.decision == "accepted")
    rejected_count = sum(1 for result in competition_results if result.decision == "rejected")
    bucket_count = sum(result.calibration_bucket_count for result in competition_results)
    usable_bucket_count = sum(
        result.usable_calibration_bucket_count for result in competition_results
    )
    sampled_buckets = _sampled_calibration_buckets(
        historical_slices,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_probability_calibration_transform_v3_1",
        "report_key": report_key,
        "holdout_season_count": resolved_options.holdout_season_count,
        "min_training_season_count": resolved_options.min_training_season_count,
        "min_validation_sample_size": resolved_options.min_validation_sample_size,
        "segment_mode": resolved_options.segment_mode,
        "bucket_size": resolved_options.bucket_size,
        "min_bucket_sample_size": resolved_options.min_bucket_sample_size,
        "blend_weight": resolved_options.blend_weight,
        "group_by_competition": resolved_options.group_by_competition,
        "competition_count": len(competition_results),
        "learned_competition_count": len(learned_results),
        "fixture_count": fixture_count,
        "validation_count": validation_count,
        "skipped_count": skipped_count,
        "accepted_competition_count": accepted_count,
        "rejected_competition_count": rejected_count,
        "calibration_bucket_count": bucket_count,
        "usable_calibration_bucket_count": usable_bucket_count,
        "overall_deltas_json": overall_deltas,
        "warnings": warnings,
        "shadow_only": True,
    }
    return HistoricalProbabilityCalibrationTransformReport(
        report_key=report_key,
        status="generated",
        competition_count=len(competition_results),
        learned_competition_count=len(learned_results),
        fixture_count=fixture_count,
        validation_count=validation_count,
        skipped_count=skipped_count,
        accepted_competition_count=accepted_count,
        rejected_competition_count=rejected_count,
        calibration_bucket_count=bucket_count,
        usable_calibration_bucket_count=usable_bucket_count,
        overall_candidate=overall_candidate,
        overall_baseline=overall_baseline,
        overall_deltas_json=overall_deltas,
        competitions=competition_results,
        sampled_calibration_buckets=sampled_buckets,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_probability_calibration_transform_report(
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


def _competition_result(
    competition_id: str,
    *,
    slices: Sequence[HistoricalRecommendationSlice],
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> HistoricalProbabilityCalibrationTransformCompetitionResult:
    sorted_slices = sorted(slices, key=_slice_sort_key)
    training_slices, validation_slices = _split_by_holdout_seasons(
        sorted_slices,
        holdout_season_count=options.holdout_season_count,
    )
    training_seasons = _slice_seasons(training_slices)
    validation_seasons = _slice_seasons(validation_slices)
    training_fixture_count = sum(len(slice_item.fixtures) for slice_item in training_slices)
    validation_fixture_count = sum(len(slice_item.fixtures) for slice_item in validation_slices)
    warnings: list[str] = []
    if _training_season_count(training_slices) < options.min_training_season_count:
        warnings.append(
            f"historical_probability_calibration_transform:{competition_id}:"
            "insufficient_training_seasons"
        )
        return _empty_competition_result(
            competition_id,
            training_seasons=training_seasons,
            validation_seasons=validation_seasons,
            training_fixture_count=training_fixture_count,
            validation_fixture_count=validation_fixture_count,
            segment_mode=options.segment_mode,
            warnings=warnings,
        )
    calibration_buckets = _calibration_buckets(training_slices, options=options)
    usable_bucket_count = sum(
        1
        for bucket in calibration_buckets.values()
        if bucket.sample_size >= options.min_bucket_sample_size
    )
    evaluations, skipped = _validation_evaluations(
        validation_slices,
        calibration_buckets=calibration_buckets,
        options=options,
    )
    candidate = _metric_set(
        evaluations,
        probability_fn=lambda item: item.candidate_probabilities,
        options=options,
    )
    baseline = _metric_set(
        evaluations,
        probability_fn=lambda item: item.baseline_probabilities,
        options=options,
    )
    deltas = _metric_deltas(candidate, baseline)
    decision, decision_reasons = _decision(
        candidate,
        baseline,
        validation_count=len(evaluations),
        deltas=deltas,
        options=options,
    )
    skipped_reason_counts = dict(Counter(item.reason for item in skipped))
    if skipped:
        warnings.append(
            f"historical_probability_calibration_transform:{competition_id}:"
            "skipped_validation_fixtures"
        )
    if len(evaluations) < options.min_validation_sample_size:
        warnings.append(
            f"historical_probability_calibration_transform:{competition_id}:"
            "insufficient_validation_samples"
        )
    summary: dict[str, object] = {
        "calculation_basis": "historical_probability_calibration_transform_competition_v3_1",
        "competition_id": competition_id,
        "training_seasons": training_seasons,
        "validation_seasons": validation_seasons,
        "training_fixture_count": training_fixture_count,
        "validation_fixture_count": validation_fixture_count,
        "segment_mode": options.segment_mode,
        "calibration_bucket_count": len(calibration_buckets),
        "usable_calibration_bucket_count": usable_bucket_count,
        "validation_count": len(evaluations),
        "skipped_count": len(skipped),
        "skipped_reason_counts": skipped_reason_counts,
        "deltas_json": deltas,
        "decision": decision,
        "decision_reasons": decision_reasons,
        "warnings": warnings,
        "shadow_only": True,
    }
    return HistoricalProbabilityCalibrationTransformCompetitionResult(
        competition_id=competition_id,
        training_seasons=training_seasons,
        validation_seasons=validation_seasons,
        training_fixture_count=training_fixture_count,
        validation_fixture_count=validation_fixture_count,
        calibration_bucket_count=len(calibration_buckets),
        usable_calibration_bucket_count=usable_bucket_count,
        validation_count=len(evaluations),
        skipped_count=len(skipped),
        skipped_reason_counts=skipped_reason_counts,
        candidate=candidate,
        baseline=baseline,
        deltas_json=deltas,
        decision=decision,
        decision_reasons=decision_reasons,
        warnings=warnings,
        sampled_predictions=evaluations[: options.prediction_sample_limit],
        summary_json=summary,
    )


def _validation_evaluations(
    validation_slices: Sequence[HistoricalRecommendationSlice],
    *,
    calibration_buckets: Mapping[str, HistoricalProbabilityCalibrationTransformBucket],
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> tuple[list[HistoricalProbabilityCalibrationTransformFixtureSample], list[_SkippedFixture]]:
    evaluations: list[HistoricalProbabilityCalibrationTransformFixtureSample] = []
    skipped: list[_SkippedFixture] = []
    for context in _fixture_contexts(validation_slices):
        baseline_probabilities = _one_x_two_probabilities(context.fixture)
        if baseline_probabilities is None:
            skipped.append(_skipped(context, "missing_complete_1x2_probabilities"))
            continue
        transformed = _calibrated_probabilities(
            context.fixture,
            baseline_probabilities,
            calibration_buckets=calibration_buckets,
            options=options,
        )
        if transformed is None:
            skipped.append(_skipped(context, "calibrated_probability_normalization_failed"))
            continue
        (
            candidate_probabilities,
            applied_bucket_keys,
            fallback_reasons,
            applied_segment_probabilities,
        ) = transformed
        actual_outcome = context.fixture.actual_1x2_outcome
        evaluations.append(
            _fixture_sample(
                context,
                baseline_probabilities=baseline_probabilities,
                candidate_probabilities=candidate_probabilities,
                applied_segment_probabilities=applied_segment_probabilities,
                applied_bucket_keys=applied_bucket_keys,
                fallback_reason_counts=dict(Counter(fallback_reasons)),
                actual_outcome=actual_outcome,
            )
        )
    return evaluations, skipped


def _fixture_sample(
    context: _FixtureContext,
    *,
    baseline_probabilities: dict[str, float],
    candidate_probabilities: dict[str, float],
    applied_segment_probabilities: dict[str, float],
    applied_bucket_keys: dict[str, str | None],
    fallback_reason_counts: dict[str, int],
    actual_outcome: str,
) -> HistoricalProbabilityCalibrationTransformFixtureSample:
    baseline_actual_probability = baseline_probabilities[actual_outcome]
    candidate_actual_probability = candidate_probabilities[actual_outcome]
    baseline_brier_score = _brier_score(baseline_probabilities, actual_outcome)
    candidate_brier_score = _brier_score(candidate_probabilities, actual_outcome)
    baseline_log_loss = _log_loss(baseline_actual_probability)
    candidate_log_loss = _log_loss(candidate_actual_probability)
    fixture = context.fixture
    return HistoricalProbabilityCalibrationTransformFixtureSample(
        fixture_id=fixture.fixture_id,
        slice_id=context.slice_id,
        competition_id=fixture.competition_id,
        season=context.season,
        actual_outcome=actual_outcome,
        baseline_probabilities=baseline_probabilities,
        candidate_probabilities=candidate_probabilities,
        applied_segment_probabilities=applied_segment_probabilities,
        applied_bucket_keys=applied_bucket_keys,
        fallback_reason_counts=fallback_reason_counts,
        baseline_actual_probability=baseline_actual_probability,
        candidate_actual_probability=candidate_actual_probability,
        baseline_brier_score=baseline_brier_score,
        candidate_brier_score=candidate_brier_score,
        baseline_log_loss=baseline_log_loss,
        candidate_log_loss=candidate_log_loss,
        brier_score_delta_vs_baseline=candidate_brier_score - baseline_brier_score,
        log_loss_delta_vs_baseline=candidate_log_loss - baseline_log_loss,
        actual_probability_delta_vs_baseline=(
            candidate_actual_probability - baseline_actual_probability
        ),
    )


def _calibration_buckets(
    training_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> dict[str, HistoricalProbabilityCalibrationTransformBucket]:
    accumulators: dict[str, _CalibrationBucketAccumulator] = {}
    for context in _fixture_contexts(training_slices):
        probabilities = _one_x_two_probabilities(context.fixture)
        if probabilities is None:
            continue
        segment_probabilities = _segment_probabilities(
            context.fixture,
            probabilities,
            options=options,
        )
        for outcome, probability in probabilities.items():
            bucket_probability = _bucket_basis_probability(
                probability,
                segment_probability=segment_probabilities[outcome],
                options=options,
            )
            bucket_start, bucket_end = _probability_bucket(
                bucket_probability,
                options.bucket_size,
            )
            group_key = _bucket_group_key(
                competition_id=(
                    context.fixture.competition_id if options.group_by_competition else None
                ),
                outcome=outcome,
                bucket_start=bucket_start,
                bucket_end=bucket_end,
            )
            accumulator = accumulators.setdefault(
                group_key,
                _CalibrationBucketAccumulator(
                    group_key=group_key,
                    competition_id=(
                        context.fixture.competition_id
                        if options.group_by_competition
                        else None
                    ),
                    outcome=outcome,
                    segment_mode=options.segment_mode,
                    bucket_start=bucket_start,
                    bucket_end=bucket_end,
                ),
            )
            accumulator.observe(
                predicted_probability=probability,
                actual_occurred=outcome == context.fixture.actual_1x2_outcome,
            )
    return {
        key: _calibration_bucket_from_accumulator(accumulator, options=options)
        for key, accumulator in sorted(accumulators.items())
    }


def _calibrated_probabilities(
    fixture: HistoricalFixture,
    probabilities: Mapping[str, float],
    *,
    calibration_buckets: Mapping[str, HistoricalProbabilityCalibrationTransformBucket],
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> tuple[dict[str, float], dict[str, str | None], list[str], dict[str, float]] | None:
    adjusted: dict[str, float] = {}
    applied_bucket_keys: dict[str, str | None] = {}
    fallback_reasons: list[str] = []
    segment_probabilities = _segment_probabilities(fixture, probabilities, options=options)
    for outcome in ONE_X_TWO_OUTCOMES:
        probability = probabilities[outcome]
        bucket_probability = _bucket_basis_probability(
            probability,
            segment_probability=segment_probabilities[outcome],
            options=options,
        )
        bucket_start, bucket_end = _probability_bucket(
            bucket_probability,
            options.bucket_size,
        )
        bucket_key = _bucket_group_key(
            competition_id=fixture.competition_id if options.group_by_competition else None,
            outcome=outcome,
            bucket_start=bucket_start,
            bucket_end=bucket_end,
        )
        bucket = calibration_buckets.get(bucket_key)
        applied_bucket_keys[outcome] = bucket_key if bucket is not None else None
        if bucket is None:
            adjusted[outcome] = probability
            fallback_reasons.append("missing_calibration_bucket")
            continue
        if (
            bucket.calibrated_probability is None
            or bucket.sample_size < options.min_bucket_sample_size
        ):
            adjusted[outcome] = probability
            fallback_reasons.append("insufficient_calibration_bucket_samples")
            continue
        calibrated_probability = _clamp(
            bucket.calibrated_probability,
            options.min_calibrated_probability,
            options.max_calibrated_probability,
        )
        adjusted[outcome] = (
            (1.0 - options.blend_weight) * probability
            + options.blend_weight * calibrated_probability
        )
    total_probability = sum(adjusted.values())
    if total_probability <= 0:
        return None
    return (
        {
            outcome: adjusted[outcome] / total_probability
            for outcome in ONE_X_TWO_OUTCOMES
        },
        applied_bucket_keys,
        fallback_reasons,
        segment_probabilities,
    )


def _calibration_bucket_from_accumulator(
    accumulator: _CalibrationBucketAccumulator,
    *,
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> HistoricalProbabilityCalibrationTransformBucket:
    average_predicted_probability = _safe_divide(
        accumulator.predicted_probability_sum,
        accumulator.sample_size,
    )
    actual_frequency = _safe_divide(accumulator.actual_count, accumulator.sample_size)
    calibrated_probability = (
        _clamp(
            actual_frequency,
            options.min_calibrated_probability,
            options.max_calibrated_probability,
        )
        if actual_frequency is not None
        else None
    )
    return HistoricalProbabilityCalibrationTransformBucket(
        group_key=accumulator.group_key,
        competition_id=accumulator.competition_id,
        outcome=accumulator.outcome,
        segment_mode=accumulator.segment_mode,
        bucket_start=accumulator.bucket_start,
        bucket_end=accumulator.bucket_end,
        sample_size=accumulator.sample_size,
        predicted_probability_sum=accumulator.predicted_probability_sum,
        average_predicted_probability=average_predicted_probability,
        actual_count=accumulator.actual_count,
        actual_frequency=actual_frequency,
        calibrated_probability=calibrated_probability,
    )


def _sampled_calibration_buckets(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> list[HistoricalProbabilityCalibrationTransformBucket]:
    sampled: list[HistoricalProbabilityCalibrationTransformBucket] = []
    for _competition_id, slices in sorted(_slices_by_competition(historical_slices).items()):
        sorted_slices = sorted(slices, key=_slice_sort_key)
        training_slices, _validation_slices = _split_by_holdout_seasons(
            sorted_slices,
            holdout_season_count=options.holdout_season_count,
        )
        if _training_season_count(training_slices) < options.min_training_season_count:
            continue
        sampled.extend(
            bucket
            for bucket in _calibration_buckets(training_slices, options=options).values()
            if bucket.sample_size >= options.min_bucket_sample_size
        )
    return sorted(
        sampled,
        key=lambda bucket: (
            bucket.competition_id or "",
            bucket.outcome,
            bucket.bucket_start,
        ),
    )[:50]


def _metric_set(
    evaluations: Sequence[HistoricalProbabilityCalibrationTransformFixtureSample],
    *,
    probability_fn: Callable[
        [HistoricalProbabilityCalibrationTransformFixtureSample],
        dict[str, float],
    ],
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> HistoricalProbabilityCalibrationTransformMetricSet:
    accumulator = _MetricAccumulator()
    for evaluation in evaluations:
        accumulator.observe(
            probabilities=probability_fn(evaluation),
            actual_outcome=evaluation.actual_outcome,
            bucket_size=options.bucket_size,
        )
    return _metric_set_from_accumulator(accumulator, options=options)


def _metric_set_from_accumulator(
    accumulator: _MetricAccumulator,
    *,
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> HistoricalProbabilityCalibrationTransformMetricSet:
    if accumulator.sample_size == 0:
        return HistoricalProbabilityCalibrationTransformMetricSet(
            sample_size=0,
            hit_count=0,
        )
    expected_calibration_error, included_bucket_count, skipped_bucket_count = (
        _expected_calibration_error(
            accumulator.calibration_buckets,
            min_bucket_sample_size=options.min_bucket_sample_size,
        )
    )
    return HistoricalProbabilityCalibrationTransformMetricSet(
        sample_size=accumulator.sample_size,
        hit_count=accumulator.hit_count,
        hit_rate=accumulator.hit_count / accumulator.sample_size,
        brier_score=accumulator.brier_score_sum / accumulator.sample_size,
        log_loss=accumulator.log_loss_sum / accumulator.sample_size,
        average_actual_probability=(
            accumulator.actual_probability_sum / accumulator.sample_size
        ),
        expected_calibration_error=expected_calibration_error,
        calibration_observation_count=sum(
            bucket.sample_size for bucket in accumulator.calibration_buckets.values()
        ),
        included_calibration_bucket_count=included_bucket_count,
        skipped_small_calibration_bucket_count=skipped_bucket_count,
    )


def _decision(
    candidate: HistoricalProbabilityCalibrationTransformMetricSet,
    baseline: HistoricalProbabilityCalibrationTransformMetricSet,
    *,
    validation_count: int,
    deltas: Mapping[str, object],
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> tuple[HistoricalProbabilityCalibrationTransformDecision, list[str]]:
    reasons: list[str] = []
    if validation_count < options.min_validation_sample_size:
        reasons.append("validation_sample_size_below_minimum")
    hit_delta = _float_delta(deltas, "hit_rate_delta")
    brier_delta = _float_delta(deltas, "brier_score_delta")
    log_loss_delta = _float_delta(deltas, "log_loss_delta")
    ece_delta = _float_delta(deltas, "expected_calibration_error_delta")
    if hit_delta is not None and hit_delta < options.min_hit_rate_delta:
        reasons.append("hit_rate_delta_below_threshold")
    if brier_delta is not None and brier_delta > options.max_brier_score_delta:
        reasons.append("brier_score_regressed")
    if log_loss_delta is not None and log_loss_delta > options.max_log_loss_delta:
        reasons.append("log_loss_regressed")
    if (
        ece_delta is not None
        and ece_delta > options.max_expected_calibration_error_delta
    ):
        reasons.append("expected_calibration_error_regressed")
    if not _has_objective_improvement(candidate, baseline, options=options):
        reasons.append("objective_improvement_missing")
    if reasons:
        return "rejected", reasons
    return "accepted", ["non_regressing_holdout_improvement"]


def _has_objective_improvement(
    candidate: HistoricalProbabilityCalibrationTransformMetricSet,
    baseline: HistoricalProbabilityCalibrationTransformMetricSet,
    *,
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> bool:
    improvements = [
        _optional_delta(baseline.brier_score, candidate.brier_score),
        _optional_delta(baseline.log_loss, candidate.log_loss),
        _optional_delta(
            baseline.expected_calibration_error,
            candidate.expected_calibration_error,
        ),
        _optional_delta(candidate.hit_rate, baseline.hit_rate),
    ]
    return any(
        improvement is not None and improvement > options.min_objective_improvement
        for improvement in improvements
    )


def _metric_deltas(
    candidate: HistoricalProbabilityCalibrationTransformMetricSet,
    baseline: HistoricalProbabilityCalibrationTransformMetricSet,
) -> dict[str, object]:
    return {
        "hit_rate_delta": _optional_delta(candidate.hit_rate, baseline.hit_rate),
        "brier_score_delta": _optional_delta(candidate.brier_score, baseline.brier_score),
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


def _combine_metric_sets(
    metric_sets: Sequence[HistoricalProbabilityCalibrationTransformMetricSet],
) -> HistoricalProbabilityCalibrationTransformMetricSet | None:
    sample_size = sum(metric.sample_size for metric in metric_sets)
    if sample_size == 0:
        return None
    return HistoricalProbabilityCalibrationTransformMetricSet(
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
    metric_sets: Sequence[HistoricalProbabilityCalibrationTransformMetricSet],
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


def _one_x_two_probabilities(fixture: HistoricalFixture) -> dict[str, float] | None:
    predictions = _one_x_two_predictions(fixture)
    if predictions is None:
        return None
    normalized = _normalize_probabilities(
        {
            outcome: predictions[outcome].probability
            for outcome in ONE_X_TWO_OUTCOMES
        }
    )
    return normalized


def _one_x_two_predictions(
    fixture: HistoricalFixture,
) -> dict[str, HistoricalMarketPrediction] | None:
    probabilities: dict[str, float] = {}
    predictions: dict[str, HistoricalMarketPrediction] = {}
    for prediction in fixture.predictions:
        if prediction.market_type == "1x2" and prediction.outcome in ONE_X_TWO_OUTCOMES:
            probabilities[prediction.outcome] = prediction.probability
            predictions[prediction.outcome] = prediction
    if set(probabilities) != set(ONE_X_TWO_OUTCOMES):
        return None
    return predictions


def _segment_probabilities(
    fixture: HistoricalFixture,
    probabilities: Mapping[str, float],
    *,
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> dict[str, float]:
    if options.segment_mode == "probability_bucket":
        return dict(probabilities)
    predictions = _one_x_two_predictions(fixture)
    if predictions is None:
        return dict(probabilities)
    market_probabilities = {
        outcome: _market_segment_probability(
            predictions[outcome],
            fallback_probability=probabilities[outcome],
        )
        for outcome in ONE_X_TWO_OUTCOMES
    }
    normalized = _normalize_probabilities(market_probabilities)
    return normalized if normalized is not None else dict(probabilities)


def _market_segment_probability(
    prediction: HistoricalMarketPrediction,
    *,
    fallback_probability: float,
) -> float:
    if prediction.market_probability is not None:
        return _clamp(prediction.market_probability, 0.0, 1.0)
    if prediction.decimal_odds > 0:
        return _clamp(1.0 / prediction.decimal_odds, 0.0, 1.0)
    return _clamp(fallback_probability, 0.0, 1.0)


def _bucket_basis_probability(
    probability: float,
    *,
    segment_probability: float,
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> float:
    if options.segment_mode == "market_odds_band":
        return segment_probability
    return probability


def _normalize_probabilities(probabilities: Mapping[str, float]) -> dict[str, float] | None:
    total = sum(probabilities.values())
    if total <= 0:
        return None
    return {outcome: probabilities[outcome] / total for outcome in ONE_X_TWO_OUTCOMES}


def _brier_score(probabilities: Mapping[str, float], actual_outcome: str) -> float:
    return sum(
        (
            probabilities[outcome]
            - (1.0 if outcome == actual_outcome else 0.0)
        )
        ** 2
        for outcome in ONE_X_TWO_OUTCOMES
    )


def _log_loss(actual_probability: float) -> float:
    return -log(_clamp(actual_probability, DEFAULT_LOG_LOSS_EPSILON, 1.0))


def _predicted_outcome(probabilities: Mapping[str, float]) -> str:
    return max(ONE_X_TWO_OUTCOMES, key=lambda outcome: probabilities[outcome])


def _probability_bucket(probability: float, bucket_size: float) -> tuple[float, float]:
    if probability >= 1.0:
        return 1.0 - bucket_size, 1.0
    bucket_index = floor(max(0.0, probability) / bucket_size)
    bucket_start = bucket_index * bucket_size
    bucket_end = min(1.0, bucket_start + bucket_size)
    return round(bucket_start, 10), round(bucket_end, 10)


def _expected_calibration_error(
    buckets: Mapping[tuple[str, float, float], _CalibrationObservationBucket],
    *,
    min_bucket_sample_size: int,
) -> tuple[float | None, int, int]:
    included = [
        bucket for bucket in buckets.values() if bucket.sample_size >= min_bucket_sample_size
    ]
    skipped_count = len(buckets) - len(included)
    denominator = sum(bucket.sample_size for bucket in included)
    if denominator == 0:
        return None, 0, skipped_count
    numerator = 0.0
    for bucket in included:
        average_probability = bucket.predicted_probability_sum / bucket.sample_size
        actual_frequency = bucket.actual_count / bucket.sample_size
        numerator += bucket.sample_size * abs(average_probability - actual_frequency)
    return numerator / denominator, len(included), skipped_count


def _bucket_group_key(
    *,
    competition_id: str | None,
    outcome: str,
    bucket_start: float,
    bucket_end: float,
) -> str:
    competition_key = competition_id or "ALL_COMPETITIONS"
    return "|".join(
        [
            competition_key,
            outcome,
            f"{bucket_start:.10f}",
            f"{bucket_end:.10f}",
        ]
    )


def _fixture_contexts(
    historical_slices: Sequence[HistoricalRecommendationSlice],
) -> list[_FixtureContext]:
    return [
        _FixtureContext(
            slice_id=historical_slice.metadata.slice_id,
            season=historical_slice.metadata.season,
            fixture=fixture,
        )
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
    ]


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


def _split_by_holdout_seasons(
    sorted_slices: Sequence[HistoricalRecommendationSlice],
    *,
    holdout_season_count: int,
) -> tuple[list[HistoricalRecommendationSlice], list[HistoricalRecommendationSlice]]:
    if not sorted_slices:
        return [], []
    season_order: list[str] = []
    for historical_slice in sorted_slices:
        season = _slice_season(historical_slice)
        if season not in season_order:
            season_order.append(season)
    if len(season_order) == 1 and season_order[0] == "unknown":
        holdout_count = min(holdout_season_count, len(sorted_slices))
        return list(sorted_slices[:-holdout_count]), list(sorted_slices[-holdout_count:])
    holdout_seasons = set(season_order[-holdout_season_count:])
    training_slices = [
        historical_slice
        for historical_slice in sorted_slices
        if _slice_season(historical_slice) not in holdout_seasons
    ]
    validation_slices = [
        historical_slice
        for historical_slice in sorted_slices
        if _slice_season(historical_slice) in holdout_seasons
    ]
    return training_slices, validation_slices


def _slice_seasons(
    slices: Sequence[HistoricalRecommendationSlice],
) -> list[str]:
    seasons: list[str] = []
    for historical_slice in slices:
        season = _slice_season(historical_slice)
        if season not in seasons:
            seasons.append(season)
    return seasons


def _training_season_count(
    slices: Sequence[HistoricalRecommendationSlice],
) -> int:
    seasons = _slice_seasons(slices)
    if seasons == ["unknown"]:
        return len(slices)
    return len(seasons)


def _slice_season(historical_slice: HistoricalRecommendationSlice) -> str:
    return historical_slice.metadata.season or "unknown"


def _skipped(context: _FixtureContext, reason: str) -> _SkippedFixture:
    return _SkippedFixture(
        fixture_id=context.fixture.fixture_id,
        competition_id=context.fixture.competition_id,
        season=context.season,
        reason=reason,
    )


def _empty_competition_result(
    competition_id: str,
    *,
    training_seasons: Sequence[str],
    validation_seasons: Sequence[str],
    training_fixture_count: int,
    validation_fixture_count: int,
    segment_mode: HistoricalProbabilityCalibrationTransformSegmentMode,
    warnings: Sequence[str],
) -> HistoricalProbabilityCalibrationTransformCompetitionResult:
    empty_metric_set = HistoricalProbabilityCalibrationTransformMetricSet(
        sample_size=0,
        hit_count=0,
    )
    return HistoricalProbabilityCalibrationTransformCompetitionResult(
        competition_id=competition_id,
        training_seasons=list(training_seasons),
        validation_seasons=list(validation_seasons),
        training_fixture_count=training_fixture_count,
        validation_fixture_count=validation_fixture_count,
        calibration_bucket_count=0,
        usable_calibration_bucket_count=0,
        validation_count=0,
        skipped_count=0,
        candidate=empty_metric_set,
        baseline=empty_metric_set,
        decision="rejected",
        decision_reasons=["insufficient_training_seasons"],
        warnings=list(warnings),
        summary_json={
            "calculation_basis": "historical_probability_calibration_transform_competition_v3_1",
            "competition_id": competition_id,
            "segment_mode": segment_mode,
            "decision": "rejected",
            "decision_reasons": ["insufficient_training_seasons"],
            "warnings": list(warnings),
        },
    )


def _report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationTransformOptions,
) -> str:
    payload = {
        "slice_ids": [
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration_transform:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Learn frozen probability calibration buckets on training seasons "
            "and validate the transform on holdout seasons."
        )
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
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
    parser.add_argument("--min-hit-rate-delta", type=float, default=-0.0000001)
    parser.add_argument("--max-brier-score-delta", type=float, default=0.0)
    parser.add_argument("--max-log-loss-delta", type=float, default=0.0)
    parser.add_argument("--max-expected-calibration-error-delta", type=float, default=0.0)
    parser.add_argument("--min-objective-improvement", type=float, default=0.0)
    parser.add_argument("--prediction-sample-limit", type=int, default=20)
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalProbabilityCalibrationTransformOptions:
    return HistoricalProbabilityCalibrationTransformOptions(
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
        min_hit_rate_delta=args.min_hit_rate_delta,
        max_brier_score_delta=args.max_brier_score_delta,
        max_log_loss_delta=args.max_log_loss_delta,
        max_expected_calibration_error_delta=(
            args.max_expected_calibration_error_delta
        ),
        min_objective_improvement=args.min_objective_improvement,
        prediction_sample_limit=args.prediction_sample_limit,
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


def _safe_divide(numerator: float | int, denominator: float | int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def _float_delta(deltas: Mapping[str, object], key: str) -> float | None:
    value = deltas.get(key)
    if isinstance(value, int | float):
        return float(value)
    return None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)
