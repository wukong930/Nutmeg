from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from json import dumps
from math import log
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from nutmeg.accuracy.calibration import calibration_bucket_key_for_probability
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

type HistoricalProbabilityCalibrationDecision = Literal[
    "calibrated",
    "insufficient_samples",
    "needs_calibration",
    "monitor",
]
type HistoricalProbabilityCalibrationStatus = Literal["generated"]

DEFAULT_HISTORICAL_PROBABILITY_CALIBRATION_MARKET_TYPES = ("1x2",)
DEFAULT_LOG_LOSS_EPSILON = 1e-12


class HistoricalProbabilityCalibrationOptions(BaseModel):
    market_types: tuple[str, ...] = DEFAULT_HISTORICAL_PROBABILITY_CALIBRATION_MARKET_TYPES
    bucket_size: float = Field(default=0.10, gt=0.0, le=1.0)
    min_bucket_sample_size: int = Field(default=5, ge=1)
    min_group_sample_size: int = Field(default=30, ge=1)
    max_expected_calibration_error: float = Field(default=0.08, ge=0.0, le=1.0)
    max_brier_score: float | None = Field(default=None, ge=0.0)
    max_brier_score_delta_vs_market: float | None = None
    max_log_loss_delta_vs_market: float | None = None
    include_market_baseline: bool = True
    group_by_competition: bool = True
    top_group_limit: int = Field(default=10, ge=1)


class HistoricalProbabilityCalibrationBucket(BaseModel):
    bucket_key: str
    group_key: str
    model_version: str
    calibration_version: str
    competition_id: str | None = None
    market_type: str
    outcome: str
    bucket_start: float = Field(ge=0.0, le=1.0)
    bucket_end: float = Field(ge=0.0, le=1.0)
    fixture_count: int = Field(ge=0)
    sample_size: int = Field(ge=0)
    predicted_probability_sum: float = Field(ge=0.0)
    average_predicted_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    actual_count: int = Field(ge=0)
    actual_frequency: float | None = Field(default=None, ge=0.0, le=1.0)
    calibration_error: float | None = Field(default=None, ge=0.0)
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    market_probability_sample_size: int = Field(default=0, ge=0)
    market_probability_sum: float = Field(default=0.0, ge=0.0)
    average_market_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    market_brier_score: float | None = Field(default=None, ge=0.0)
    market_log_loss: float | None = Field(default=None, ge=0.0)
    brier_score_delta_vs_market: float | None = None
    log_loss_delta_vs_market: float | None = None


class HistoricalProbabilityCalibrationGroup(BaseModel):
    group_key: str
    model_version: str
    calibration_version: str
    competition_id: str | None = None
    market_type: str
    outcome: str
    fixture_count: int = Field(ge=0)
    sample_size: int = Field(ge=0)
    bucket_count: int = Field(ge=0)
    included_bucket_count: int = Field(ge=0)
    skipped_small_bucket_count: int = Field(ge=0)
    expected_calibration_error: float | None = Field(default=None, ge=0.0)
    brier_score: float | None = Field(default=None, ge=0.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    market_probability_sample_size: int = Field(default=0, ge=0)
    market_brier_score: float | None = Field(default=None, ge=0.0)
    market_log_loss: float | None = Field(default=None, ge=0.0)
    brier_score_delta_vs_market: float | None = None
    log_loss_delta_vs_market: float | None = None
    decision: HistoricalProbabilityCalibrationDecision
    decision_reasons: list[str] = Field(default_factory=list)
    buckets: list[HistoricalProbabilityCalibrationBucket] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


class HistoricalProbabilityCalibrationReport(BaseModel):
    report_key: str
    status: HistoricalProbabilityCalibrationStatus
    slice_count: int = Field(ge=0)
    fixture_count: int = Field(ge=0)
    input_prediction_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    skipped_market_type_count: int = Field(ge=0)
    skipped_unsupported_actual_count: int = Field(ge=0)
    market_probability_missing_count: int = Field(ge=0)
    group_count: int = Field(ge=0)
    bucket_count: int = Field(ge=0)
    groups_needing_calibration_count: int = Field(ge=0)
    insufficient_group_count: int = Field(ge=0)
    overall_expected_calibration_error: float | None = Field(default=None, ge=0.0)
    overall_brier_score: float | None = Field(default=None, ge=0.0)
    overall_log_loss: float | None = Field(default=None, ge=0.0)
    overall_market_brier_score: float | None = Field(default=None, ge=0.0)
    overall_market_log_loss: float | None = Field(default=None, ge=0.0)
    groups: list[HistoricalProbabilityCalibrationGroup] = Field(default_factory=list)
    top_miscalibrated_groups: list[HistoricalProbabilityCalibrationGroup] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(default_factory=list)
    summary_json: dict[str, object] = Field(default_factory=dict)


@dataclass
class _BucketAccumulator:
    bucket_key: str
    group_key: str
    model_version: str
    calibration_version: str
    competition_id: str | None
    market_type: str
    outcome: str
    bucket_start: float
    bucket_end: float
    fixture_ids: set[str] = field(default_factory=set)
    sample_size: int = 0
    predicted_probability_sum: float = 0.0
    actual_count: int = 0
    brier_score_sum: float = 0.0
    log_loss_sum: float = 0.0
    market_probability_sample_size: int = 0
    market_probability_sum: float = 0.0
    market_brier_score_sum: float = 0.0
    market_log_loss_sum: float = 0.0

    def observe(
        self,
        *,
        fixture_id: str,
        predicted_probability: float,
        actual_occurred: bool,
        market_probability: float | None,
    ) -> None:
        actual_value = 1.0 if actual_occurred else 0.0
        self.fixture_ids.add(fixture_id)
        self.sample_size += 1
        self.predicted_probability_sum += predicted_probability
        self.actual_count += 1 if actual_occurred else 0
        self.brier_score_sum += (predicted_probability - actual_value) ** 2
        self.log_loss_sum += _binary_log_loss(predicted_probability, actual_occurred)
        if market_probability is not None:
            self.market_probability_sample_size += 1
            self.market_probability_sum += market_probability
            self.market_brier_score_sum += (market_probability - actual_value) ** 2
            self.market_log_loss_sum += _binary_log_loss(
                market_probability,
                actual_occurred,
            )


class _HistoricalProbabilityCalibrationObservations(BaseModel):
    buckets: list[HistoricalProbabilityCalibrationBucket]
    observation_count: int = Field(ge=0)
    skipped_market_type_count: int = Field(ge=0)
    skipped_unsupported_actual_count: int = Field(ge=0)
    market_probability_missing_count: int = Field(ge=0)


class _LoadedHistoricalSlices(BaseModel):
    slices: list[HistoricalRecommendationSlice] = Field(default_factory=list)
    manifest_result: HistoricalRecommendationSuiteManifestLoadResult | None = None
    warnings: list[str] = Field(default_factory=list)


def build_historical_probability_calibration_report(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationOptions | None = None,
) -> HistoricalProbabilityCalibrationReport:
    resolved_options = options or HistoricalProbabilityCalibrationOptions()
    observations = _collect_probability_calibration_observations(
        historical_slices,
        options=resolved_options,
    )
    groups = _calibration_groups(
        observations.buckets,
        options=resolved_options,
    )
    top_groups = _top_miscalibrated_groups(
        groups,
        limit=resolved_options.top_group_limit,
    )
    fixture_count = sum(len(historical_slice.fixtures) for historical_slice in historical_slices)
    input_prediction_count = sum(
        len(fixture.predictions)
        for historical_slice in historical_slices
        for fixture in historical_slice.fixtures
    )
    overall_expected_calibration_error = _overall_expected_calibration_error(
        groups,
        options=resolved_options,
    )
    overall_market_sample_size = sum(
        bucket.market_probability_sample_size for bucket in observations.buckets
    )
    warnings = _report_warnings(
        observations,
        groups=groups,
        options=resolved_options,
    )
    report_key = _report_key(
        historical_slices,
        observations=observations,
        options=resolved_options,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_probability_calibration_v3_1",
        "report_key": report_key,
        "market_types": list(resolved_options.market_types),
        "bucket_size": resolved_options.bucket_size,
        "min_bucket_sample_size": resolved_options.min_bucket_sample_size,
        "min_group_sample_size": resolved_options.min_group_sample_size,
        "max_expected_calibration_error": (
            resolved_options.max_expected_calibration_error
        ),
        "include_market_baseline": resolved_options.include_market_baseline,
        "group_by_competition": resolved_options.group_by_competition,
        "slice_count": len(historical_slices),
        "fixture_count": fixture_count,
        "input_prediction_count": input_prediction_count,
        "observation_count": observations.observation_count,
        "skipped_market_type_count": observations.skipped_market_type_count,
        "skipped_unsupported_actual_count": (
            observations.skipped_unsupported_actual_count
        ),
        "market_probability_missing_count": observations.market_probability_missing_count,
        "group_count": len(groups),
        "bucket_count": len(observations.buckets),
        "groups_needing_calibration_count": sum(
            1 for group in groups if group.decision == "needs_calibration"
        ),
        "insufficient_group_count": sum(
            1 for group in groups if group.decision == "insufficient_samples"
        ),
        "overall_expected_calibration_error": overall_expected_calibration_error,
        "overall_brier_score": _weighted_average(
            [
                (bucket.brier_score, bucket.sample_size)
                for bucket in observations.buckets
            ]
        ),
        "warnings": warnings,
    }
    return HistoricalProbabilityCalibrationReport(
        report_key=report_key,
        status="generated",
        slice_count=len(historical_slices),
        fixture_count=fixture_count,
        input_prediction_count=input_prediction_count,
        observation_count=observations.observation_count,
        skipped_market_type_count=observations.skipped_market_type_count,
        skipped_unsupported_actual_count=observations.skipped_unsupported_actual_count,
        market_probability_missing_count=observations.market_probability_missing_count,
        group_count=len(groups),
        bucket_count=len(observations.buckets),
        groups_needing_calibration_count=sum(
            1 for group in groups if group.decision == "needs_calibration"
        ),
        insufficient_group_count=sum(
            1 for group in groups if group.decision == "insufficient_samples"
        ),
        overall_expected_calibration_error=overall_expected_calibration_error,
        overall_brier_score=_weighted_average(
            [
                (bucket.brier_score, bucket.sample_size)
                for bucket in observations.buckets
            ]
        ),
        overall_log_loss=_weighted_average(
            [
                (bucket.log_loss, bucket.sample_size)
                for bucket in observations.buckets
            ]
        ),
        overall_market_brier_score=_weighted_average(
            [
                (bucket.market_brier_score, bucket.market_probability_sample_size)
                for bucket in observations.buckets
            ]
        )
        if overall_market_sample_size
        else None,
        overall_market_log_loss=_weighted_average(
            [
                (bucket.market_log_loss, bucket.market_probability_sample_size)
                for bucket in observations.buckets
            ]
        )
        if overall_market_sample_size
        else None,
        groups=groups,
        top_miscalibrated_groups=top_groups,
        warnings=warnings,
        summary_json=summary,
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    loaded_slices = _historical_slices_from_args(args)
    report = build_historical_probability_calibration_report(
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


def _collect_probability_calibration_observations(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    options: HistoricalProbabilityCalibrationOptions,
) -> _HistoricalProbabilityCalibrationObservations:
    bucket_accumulators: dict[str, _BucketAccumulator] = {}
    observation_count = 0
    skipped_market_type_count = 0
    skipped_unsupported_actual_count = 0
    market_probability_missing_count = 0
    market_types = set(options.market_types)
    for historical_slice in historical_slices:
        for fixture in historical_slice.fixtures:
            for prediction in fixture.predictions:
                if prediction.market_type not in market_types:
                    skipped_market_type_count += 1
                    continue
                actual_occurred = _actual_occurred(fixture, prediction)
                if actual_occurred is None:
                    skipped_unsupported_actual_count += 1
                    continue
                market_probability = (
                    prediction.market_probability
                    if options.include_market_baseline
                    else None
                )
                if options.include_market_baseline and market_probability is None:
                    market_probability_missing_count += 1
                accumulator = _bucket_accumulator(
                    bucket_accumulators,
                    fixture=fixture,
                    prediction=prediction,
                    options=options,
                )
                accumulator.observe(
                    fixture_id=fixture.fixture_id,
                    predicted_probability=prediction.probability,
                    actual_occurred=actual_occurred,
                    market_probability=market_probability,
                )
                observation_count += 1
    return _HistoricalProbabilityCalibrationObservations(
        buckets=[
            _bucket_from_accumulator(accumulator)
            for accumulator in sorted(
                bucket_accumulators.values(),
                key=lambda item: item.bucket_key,
            )
        ],
        observation_count=observation_count,
        skipped_market_type_count=skipped_market_type_count,
        skipped_unsupported_actual_count=skipped_unsupported_actual_count,
        market_probability_missing_count=market_probability_missing_count,
    )


def _bucket_accumulator(
    bucket_accumulators: dict[str, _BucketAccumulator],
    *,
    fixture: HistoricalFixture,
    prediction: HistoricalMarketPrediction,
    options: HistoricalProbabilityCalibrationOptions,
) -> _BucketAccumulator:
    competition_id = fixture.competition_id if options.group_by_competition else None
    calibration_version = fixture.calibration_version or "uncalibrated"
    bucket_key_model = calibration_bucket_key_for_probability(
        predicted_probability=prediction.probability,
        model_version=fixture.model_version,
        market_type=prediction.market_type,
        outcome=prediction.outcome,
        bucket_size=options.bucket_size,
        competition_id=competition_id,
    )
    group_key = _group_key(
        model_version=fixture.model_version,
        calibration_version=calibration_version,
        competition_id=competition_id,
        market_type=prediction.market_type,
        outcome=prediction.outcome,
    )
    bucket_key = "|".join(
        [
            group_key,
            f"{bucket_key_model.bucket_start:.10f}",
            f"{bucket_key_model.bucket_end:.10f}",
        ]
    )
    if bucket_key not in bucket_accumulators:
        bucket_accumulators[bucket_key] = _BucketAccumulator(
            bucket_key=bucket_key,
            group_key=group_key,
            model_version=fixture.model_version,
            calibration_version=calibration_version,
            competition_id=competition_id,
            market_type=prediction.market_type,
            outcome=prediction.outcome,
            bucket_start=bucket_key_model.bucket_start,
            bucket_end=bucket_key_model.bucket_end,
        )
    return bucket_accumulators[bucket_key]


def _bucket_from_accumulator(
    accumulator: _BucketAccumulator,
) -> HistoricalProbabilityCalibrationBucket:
    average_predicted_probability = _safe_divide(
        accumulator.predicted_probability_sum,
        accumulator.sample_size,
    )
    actual_frequency = _safe_divide(accumulator.actual_count, accumulator.sample_size)
    brier_score = _safe_divide(accumulator.brier_score_sum, accumulator.sample_size)
    log_loss_value = _safe_divide(accumulator.log_loss_sum, accumulator.sample_size)
    average_market_probability = _safe_divide(
        accumulator.market_probability_sum,
        accumulator.market_probability_sample_size,
    )
    market_brier_score = _safe_divide(
        accumulator.market_brier_score_sum,
        accumulator.market_probability_sample_size,
    )
    market_log_loss = _safe_divide(
        accumulator.market_log_loss_sum,
        accumulator.market_probability_sample_size,
    )
    return HistoricalProbabilityCalibrationBucket(
        bucket_key=accumulator.bucket_key,
        group_key=accumulator.group_key,
        model_version=accumulator.model_version,
        calibration_version=accumulator.calibration_version,
        competition_id=accumulator.competition_id,
        market_type=accumulator.market_type,
        outcome=accumulator.outcome,
        bucket_start=accumulator.bucket_start,
        bucket_end=accumulator.bucket_end,
        fixture_count=len(accumulator.fixture_ids),
        sample_size=accumulator.sample_size,
        predicted_probability_sum=accumulator.predicted_probability_sum,
        average_predicted_probability=average_predicted_probability,
        actual_count=accumulator.actual_count,
        actual_frequency=actual_frequency,
        calibration_error=(
            abs(average_predicted_probability - actual_frequency)
            if average_predicted_probability is not None
            and actual_frequency is not None
            else None
        ),
        brier_score=brier_score,
        log_loss=log_loss_value,
        market_probability_sample_size=accumulator.market_probability_sample_size,
        market_probability_sum=accumulator.market_probability_sum,
        average_market_probability=average_market_probability,
        market_brier_score=market_brier_score,
        market_log_loss=market_log_loss,
        brier_score_delta_vs_market=_optional_delta(
            brier_score,
            market_brier_score,
        ),
        log_loss_delta_vs_market=_optional_delta(log_loss_value, market_log_loss),
    )


def _calibration_groups(
    buckets: Sequence[HistoricalProbabilityCalibrationBucket],
    *,
    options: HistoricalProbabilityCalibrationOptions,
) -> list[HistoricalProbabilityCalibrationGroup]:
    groups_by_key: dict[str, list[HistoricalProbabilityCalibrationBucket]] = {}
    for bucket in buckets:
        groups_by_key.setdefault(bucket.group_key, []).append(bucket)
    return [
        _calibration_group(
            group_key,
            buckets=sorted(group_buckets, key=lambda item: item.bucket_start),
            options=options,
        )
        for group_key, group_buckets in sorted(groups_by_key.items())
    ]


def _calibration_group(
    group_key: str,
    *,
    buckets: Sequence[HistoricalProbabilityCalibrationBucket],
    options: HistoricalProbabilityCalibrationOptions,
) -> HistoricalProbabilityCalibrationGroup:
    first_bucket = buckets[0]
    included_buckets = [
        bucket
        for bucket in buckets
        if bucket.sample_size >= options.min_bucket_sample_size
    ]
    sample_size = sum(bucket.sample_size for bucket in buckets)
    fixture_count = sum(bucket.fixture_count for bucket in buckets)
    expected_calibration_error = _expected_calibration_error(included_buckets)
    brier_score = _weighted_average(
        [(bucket.brier_score, bucket.sample_size) for bucket in buckets]
    )
    log_loss_value = _weighted_average(
        [(bucket.log_loss, bucket.sample_size) for bucket in buckets]
    )
    market_sample_size = sum(bucket.market_probability_sample_size for bucket in buckets)
    market_brier_score = _weighted_average(
        [
            (bucket.market_brier_score, bucket.market_probability_sample_size)
            for bucket in buckets
        ]
    )
    market_log_loss = _weighted_average(
        [
            (bucket.market_log_loss, bucket.market_probability_sample_size)
            for bucket in buckets
        ]
    )
    brier_score_delta_vs_market = _optional_delta(brier_score, market_brier_score)
    log_loss_delta_vs_market = _optional_delta(log_loss_value, market_log_loss)
    decision, decision_reasons = _group_decision(
        sample_size=sample_size,
        included_bucket_count=len(included_buckets),
        expected_calibration_error=expected_calibration_error,
        brier_score=brier_score,
        brier_score_delta_vs_market=brier_score_delta_vs_market,
        log_loss_delta_vs_market=log_loss_delta_vs_market,
        options=options,
    )
    summary: dict[str, object] = {
        "calculation_basis": "historical_probability_calibration_group_v3_1",
        "group_key": group_key,
        "sample_size": sample_size,
        "bucket_count": len(buckets),
        "included_bucket_count": len(included_buckets),
        "expected_calibration_error": expected_calibration_error,
        "brier_score": brier_score,
        "log_loss": log_loss_value,
        "market_brier_score": market_brier_score,
        "market_log_loss": market_log_loss,
        "brier_score_delta_vs_market": brier_score_delta_vs_market,
        "log_loss_delta_vs_market": log_loss_delta_vs_market,
        "decision": decision,
        "decision_reasons": decision_reasons,
    }
    return HistoricalProbabilityCalibrationGroup(
        group_key=group_key,
        model_version=first_bucket.model_version,
        calibration_version=first_bucket.calibration_version,
        competition_id=first_bucket.competition_id,
        market_type=first_bucket.market_type,
        outcome=first_bucket.outcome,
        fixture_count=fixture_count,
        sample_size=sample_size,
        bucket_count=len(buckets),
        included_bucket_count=len(included_buckets),
        skipped_small_bucket_count=len(buckets) - len(included_buckets),
        expected_calibration_error=expected_calibration_error,
        brier_score=brier_score,
        log_loss=log_loss_value,
        market_probability_sample_size=market_sample_size,
        market_brier_score=market_brier_score,
        market_log_loss=market_log_loss,
        brier_score_delta_vs_market=brier_score_delta_vs_market,
        log_loss_delta_vs_market=log_loss_delta_vs_market,
        decision=decision,
        decision_reasons=decision_reasons,
        buckets=list(buckets),
        summary_json=summary,
    )


def _group_decision(
    *,
    sample_size: int,
    included_bucket_count: int,
    expected_calibration_error: float | None,
    brier_score: float | None,
    brier_score_delta_vs_market: float | None,
    log_loss_delta_vs_market: float | None,
    options: HistoricalProbabilityCalibrationOptions,
) -> tuple[HistoricalProbabilityCalibrationDecision, list[str]]:
    reasons: list[str] = []
    if sample_size < options.min_group_sample_size:
        reasons.append("sample_size_below_min_group_sample_size")
    if included_bucket_count == 0:
        reasons.append("no_bucket_meets_min_bucket_sample_size")
    if reasons:
        return "insufficient_samples", reasons
    if (
        expected_calibration_error is not None
        and expected_calibration_error > options.max_expected_calibration_error
    ):
        reasons.append("expected_calibration_error_above_threshold")
    if (
        options.max_brier_score is not None
        and brier_score is not None
        and brier_score > options.max_brier_score
    ):
        reasons.append("brier_score_above_threshold")
    if (
        options.max_brier_score_delta_vs_market is not None
        and brier_score_delta_vs_market is not None
        and brier_score_delta_vs_market > options.max_brier_score_delta_vs_market
    ):
        reasons.append("brier_score_delta_vs_market_above_threshold")
    if (
        options.max_log_loss_delta_vs_market is not None
        and log_loss_delta_vs_market is not None
        and log_loss_delta_vs_market > options.max_log_loss_delta_vs_market
    ):
        reasons.append("log_loss_delta_vs_market_above_threshold")
    if reasons:
        return "needs_calibration", reasons
    if expected_calibration_error is None:
        return "monitor", ["expected_calibration_error_unavailable"]
    return "calibrated", ["within_configured_thresholds"]


def _expected_calibration_error(
    buckets: Sequence[HistoricalProbabilityCalibrationBucket],
) -> float | None:
    numerator = sum(
        bucket.sample_size * (bucket.calibration_error or 0.0)
        for bucket in buckets
        if bucket.calibration_error is not None
    )
    denominator = sum(
        bucket.sample_size for bucket in buckets if bucket.calibration_error is not None
    )
    return _safe_divide(numerator, denominator)


def _overall_expected_calibration_error(
    groups: Sequence[HistoricalProbabilityCalibrationGroup],
    *,
    options: HistoricalProbabilityCalibrationOptions,
) -> float | None:
    return _weighted_average(
        [
            (group.expected_calibration_error, group.sample_size)
            for group in groups
            if group.sample_size >= options.min_group_sample_size
        ]
    )


def _top_miscalibrated_groups(
    groups: Sequence[HistoricalProbabilityCalibrationGroup],
    *,
    limit: int,
) -> list[HistoricalProbabilityCalibrationGroup]:
    ranked = sorted(
        groups,
        key=lambda group: (
            group.expected_calibration_error
            if group.expected_calibration_error is not None
            else -1.0,
            group.sample_size,
        ),
        reverse=True,
    )
    return ranked[:limit]


def _actual_occurred(
    fixture: HistoricalFixture,
    prediction: HistoricalMarketPrediction,
) -> bool | None:
    if prediction.market_type == "1x2":
        return prediction.outcome == fixture.actual_1x2_outcome
    if prediction.market_type == "correct_score":
        actual_score = f"{fixture.actual_home_goals}-{fixture.actual_away_goals}"
        alternate_actual_score = f"{fixture.actual_home_goals}:{fixture.actual_away_goals}"
        return prediction.outcome in {actual_score, alternate_actual_score}
    return None


def _report_warnings(
    observations: _HistoricalProbabilityCalibrationObservations,
    *,
    groups: Sequence[HistoricalProbabilityCalibrationGroup],
    options: HistoricalProbabilityCalibrationOptions,
) -> list[str]:
    warnings: list[str] = []
    if observations.observation_count == 0:
        warnings.append("historical_probability_calibration:no_observations")
    if observations.skipped_unsupported_actual_count:
        warnings.append("historical_probability_calibration:unsupported_actuals_skipped")
    if options.include_market_baseline and observations.market_probability_missing_count:
        warnings.append("historical_probability_calibration:market_probability_missing")
    if any(group.decision == "needs_calibration" for group in groups):
        warnings.append("historical_probability_calibration:groups_need_calibration")
    return warnings


def _report_key(
    historical_slices: Sequence[HistoricalRecommendationSlice],
    *,
    observations: _HistoricalProbabilityCalibrationObservations,
    options: HistoricalProbabilityCalibrationOptions,
) -> str:
    payload = {
        "slice_ids": [
            historical_slice.metadata.slice_id for historical_slice in historical_slices
        ],
        "as_of_times": [
            historical_slice.as_of_time_utc.isoformat()
            for historical_slice in historical_slices
        ],
        "observation_count": observations.observation_count,
        "bucket_count": len(observations.buckets),
        "options": options.model_dump(mode="json"),
    }
    digest = sha256(
        dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"historical_probability_calibration:{digest}"


def _parse_args(argv: Sequence[str] | None) -> Namespace:
    parser = ArgumentParser(
        description="Build calibration evidence from frozen historical probabilities."
    )
    parser.add_argument("slice_paths", nargs="*", type=Path)
    parser.add_argument("--suite-manifest", type=Path)
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--market-types", default="1x2")
    parser.add_argument("--bucket-size", type=float, default=0.10)
    parser.add_argument("--min-bucket-sample-size", type=int, default=5)
    parser.add_argument("--min-group-sample-size", type=int, default=30)
    parser.add_argument("--max-expected-calibration-error", type=float, default=0.08)
    parser.add_argument("--max-brier-score", type=float)
    parser.add_argument("--max-brier-score-delta-vs-market", type=float)
    parser.add_argument("--max-log-loss-delta-vs-market", type=float)
    parser.add_argument("--no-market-baseline", action="store_true")
    parser.add_argument("--group-all-competitions", action="store_true")
    parser.add_argument("--top-group-limit", type=int, default=10)
    args = parser.parse_args(argv)
    if not args.slice_paths and args.suite_manifest is None:
        parser.error("provide at least one slice path or --suite-manifest")
    return args


def _options_from_args(args: Namespace) -> HistoricalProbabilityCalibrationOptions:
    return HistoricalProbabilityCalibrationOptions(
        market_types=_split_csv(args.market_types),
        bucket_size=args.bucket_size,
        min_bucket_sample_size=args.min_bucket_sample_size,
        min_group_sample_size=args.min_group_sample_size,
        max_expected_calibration_error=args.max_expected_calibration_error,
        max_brier_score=args.max_brier_score,
        max_brier_score_delta_vs_market=args.max_brier_score_delta_vs_market,
        max_log_loss_delta_vs_market=args.max_log_loss_delta_vs_market,
        include_market_baseline=not args.no_market_baseline,
        group_by_competition=not args.group_all_competitions,
        top_group_limit=args.top_group_limit,
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


def _group_key(
    *,
    model_version: str,
    calibration_version: str,
    competition_id: str | None,
    market_type: str,
    outcome: str,
) -> str:
    return "|".join(
        [
            model_version,
            calibration_version,
            competition_id or "ALL_COMPETITIONS",
            market_type,
            outcome,
        ]
    )


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _safe_divide(numerator: float | int, denominator: float | int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator) / float(denominator)


def _weighted_average(values: Sequence[tuple[float | None, int]]) -> float | None:
    numerator = sum(value * weight for value, weight in values if value is not None)
    denominator = sum(weight for value, weight in values if value is not None)
    return _safe_divide(numerator, denominator)


def _optional_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def _binary_log_loss(probability: float, actual_occurred: bool) -> float:
    clipped_probability = min(
        max(probability, DEFAULT_LOG_LOSS_EPSILON),
        1.0 - DEFAULT_LOG_LOSS_EPSILON,
    )
    if actual_occurred:
        return -log(clipped_probability)
    return -log(1.0 - clipped_probability)
