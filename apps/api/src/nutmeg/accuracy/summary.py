from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from nutmeg.accuracy.calibration import calibration_bucket_key_for_probability
from nutmeg.api.schemas import (
    AccuracyCompetitionMetrics,
    AccuracyMarketMetrics,
    AccuracySummaryFilters,
    AccuracySummaryResponse,
    CalibrationBucketPayload,
    ErrorTypeSummaryPayload,
    ModelComparisonPayload,
)
from nutmeg.domain.accuracy import ModelComparisonStub

ERROR_TYPE_LABELS: dict[str, str] = {
    "favorite_overestimated": "热门高估",
    "underdog_underestimated": "冷门低估",
    "draw_underestimated": "平局低估",
    "goals_overestimated": "进球高估",
    "goals_underestimated": "进球低估",
    "home_advantage_overestimated": "主场优势高估",
    "low_score_correlation_miss": "低比分相关性偏差",
    "blowout_tail_underestimated": "大比分尾部低估",
    "league_calibration_drift": "联赛校准漂移",
    "handicap_miss": "让球结算偏差",
}

COMPARISON_REASON_LABELS: dict[str, str] = {
    "candidate_log_loss_not_worse": "候选模型 Log Loss 未恶化。",
    "candidate_log_loss_worse": "候选模型 Log Loss 恶化。",
    "candidate_brier_not_worse": "候选模型 Brier Score 未恶化。",
    "candidate_brier_worse": "候选模型 Brier Score 恶化。",
    "candidate_sample_size_low": "候选模型样本量偏低，需继续复核。",
}


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    market_type: str
    outcome: str
    predicted_probability: float
    actual_occurred: bool
    competition_id: str | None = None


@dataclass(frozen=True, slots=True)
class AccuracyEvaluationEvent:
    fixture_id: str
    competition_id: str
    competition_name: str
    market_type: str
    model_version: str
    prediction_time_utc: datetime
    log_loss: float
    brier_score: float
    calibration_observations: tuple[CalibrationObservation, ...]
    error_tags: tuple[str, ...] = ()


@dataclass(slots=True)
class _BucketAccumulator:
    bucket_start: float
    bucket_end: float
    sample_size: int = 0
    predicted_probability_sum: float = 0.0
    actual_count: int = 0

    def add(self, observation: CalibrationObservation) -> None:
        self.sample_size += 1
        self.predicted_probability_sum += observation.predicted_probability
        self.actual_count += 1 if observation.actual_occurred else 0

    @property
    def average_predicted_probability(self) -> float:
        if self.sample_size == 0:
            return 0.0
        return self.predicted_probability_sum / self.sample_size

    @property
    def actual_frequency(self) -> float:
        if self.sample_size == 0:
            return 0.0
        return self.actual_count / self.sample_size


def build_accuracy_summary(
    events: list[AccuracyEvaluationEvent],
    *,
    model_version: str,
    competition_id: str,
    market: str,
    window: str,
    generated_at_utc: datetime,
    active_model_version: str,
    model_comparisons: list[ModelComparisonStub] | None = None,
) -> AccuracySummaryResponse:
    filtered_events = _filter_events(
        events,
        model_version=model_version,
        competition_id=competition_id,
        market=market,
        window=window,
        generated_at_utc=generated_at_utc,
        active_model_version=active_model_version,
    )

    return AccuracySummaryResponse(
        log_loss=_average([event.log_loss for event in filtered_events]),
        brier_score=_average([event.brier_score for event in filtered_events]),
        ece=_expected_calibration_error(_observations_for(filtered_events)),
        sample_size=len(filtered_events),
        by_market=_metrics_by_market(filtered_events),
        by_competition=_metrics_by_competition(filtered_events),
        calibration_buckets=_calibration_buckets(_observations_for(filtered_events)),
        error_types=_error_type_summaries(filtered_events),
        model_comparisons=_model_comparison_payloads(model_comparisons or []),
        model_version=model_version,
        window=window,
        filters=AccuracySummaryFilters(
            model_version=model_version,
            competition_id=competition_id,
            market=market,
            window=window,
        ),
        generated_at_utc=generated_at_utc,
        stale=False,
    )


def _filter_events(
    events: list[AccuracyEvaluationEvent],
    *,
    model_version: str,
    competition_id: str,
    market: str,
    window: str,
    generated_at_utc: datetime,
    active_model_version: str,
) -> list[AccuracyEvaluationEvent]:
    cutoff = _window_cutoff(window, generated_at_utc)
    return [
        event
        for event in events
        if _model_version_matches(
            event.model_version,
            requested_model_version=model_version,
            active_model_version=active_model_version,
        )
        and (competition_id == "all" or event.competition_id == competition_id)
        and (market == "all" or event.market_type == market)
        and (cutoff is None or event.prediction_time_utc >= cutoff)
    ]


def _model_version_matches(
    event_model_version: str,
    *,
    requested_model_version: str,
    active_model_version: str,
) -> bool:
    if requested_model_version == "active":
        return event_model_version == active_model_version
    return event_model_version == requested_model_version


def _window_cutoff(window: str, generated_at_utc: datetime) -> datetime | None:
    if not window.endswith("d"):
        return None
    try:
        days = int(window.removesuffix("d"))
    except ValueError:
        return None
    if days <= 0:
        return None
    return generated_at_utc - timedelta(days=days)


def _metrics_by_market(
    events: list[AccuracyEvaluationEvent],
) -> dict[str, AccuracyMarketMetrics]:
    metrics: dict[str, AccuracyMarketMetrics] = {}
    for market_type in sorted({event.market_type for event in events}):
        group = [event for event in events if event.market_type == market_type]
        metrics[market_type] = _market_metrics_for(group)
    return metrics


def _metrics_by_competition(
    events: list[AccuracyEvaluationEvent],
) -> list[AccuracyCompetitionMetrics]:
    rows: list[AccuracyCompetitionMetrics] = []
    competition_ids = sorted({event.competition_id for event in events})
    for competition_id in competition_ids:
        group = [event for event in events if event.competition_id == competition_id]
        if not group:
            continue
        first = group[0]
        rows.append(
            AccuracyCompetitionMetrics(
                competition_id=first.competition_id,
                competition_name=first.competition_name,
                log_loss=_average([event.log_loss for event in group]),
                brier_score=_average([event.brier_score for event in group]),
                ece=_expected_calibration_error(_observations_for(group)),
                sample_size=len(group),
            )
        )
    return rows


def _market_metrics_for(events: list[AccuracyEvaluationEvent]) -> AccuracyMarketMetrics:
    return AccuracyMarketMetrics(
        log_loss=_average([event.log_loss for event in events]),
        brier_score=_average([event.brier_score for event in events]),
        ece=_expected_calibration_error(_observations_for(events)),
        sample_size=len(events),
    )


def _observations_for(events: list[AccuracyEvaluationEvent]) -> list[CalibrationObservation]:
    return [
        observation
        for event in events
        for observation in event.calibration_observations
    ]


def _calibration_buckets(
    observations: list[CalibrationObservation],
) -> list[CalibrationBucketPayload]:
    buckets = _bucket_accumulators(observations)
    return [
        CalibrationBucketPayload(
            bucket_start=bucket.bucket_start,
            bucket_end=bucket.bucket_end,
            average_predicted_probability=bucket.average_predicted_probability,
            actual_frequency=bucket.actual_frequency,
            sample_size=bucket.sample_size,
        )
        for bucket in sorted(
            buckets.values(),
            key=lambda item: (item.bucket_start, item.bucket_end),
        )
    ]


def _bucket_accumulators(
    observations: list[CalibrationObservation],
) -> dict[tuple[float, float], _BucketAccumulator]:
    buckets: dict[tuple[float, float], _BucketAccumulator] = {}
    for observation in observations:
        key = calibration_bucket_key_for_probability(
            predicted_probability=observation.predicted_probability,
            model_version="summary",
            market_type=observation.market_type,
            outcome=observation.outcome,
            competition_id=observation.competition_id,
        )
        bucket_key = (key.bucket_start, key.bucket_end)
        bucket = buckets.get(bucket_key)
        if bucket is None:
            bucket = _BucketAccumulator(
                bucket_start=key.bucket_start,
                bucket_end=key.bucket_end,
            )
            buckets[bucket_key] = bucket
        bucket.add(observation)
    return buckets


def _expected_calibration_error(observations: list[CalibrationObservation]) -> float | None:
    buckets = _bucket_accumulators(observations)
    total = sum(bucket.sample_size for bucket in buckets.values())
    if total == 0:
        return None
    weighted_error = sum(
        bucket.sample_size
        * abs(bucket.average_predicted_probability - bucket.actual_frequency)
        for bucket in buckets.values()
    )
    return weighted_error / total


def _error_type_summaries(
    events: list[AccuracyEvaluationEvent],
) -> list[ErrorTypeSummaryPayload]:
    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    for event in events:
        for tag in event.error_tags:
            counts[tag] = counts.get(tag, 0) + 1
            tag_examples = examples.setdefault(tag, [])
            if event.fixture_id not in tag_examples and len(tag_examples) < 3:
                tag_examples.append(event.fixture_id)

    denominator = len(events) if events else 1
    return [
        ErrorTypeSummaryPayload(
            tag=tag,
            label=ERROR_TYPE_LABELS.get(tag, tag),
            count=count,
            share=count / denominator,
            examples=examples.get(tag, []),
        )
        for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _model_comparison_payloads(
    comparisons: list[ModelComparisonStub],
) -> list[ModelComparisonPayload]:
    return [
        ModelComparisonPayload(
            baseline_model_version=comparison.baseline_model_version,
            candidate_model_version=comparison.candidate_model_version,
            baseline_log_loss=comparison.baseline_metrics.log_loss,
            candidate_log_loss=comparison.candidate_metrics.log_loss,
            baseline_brier_score=comparison.baseline_metrics.brier_score,
            candidate_brier_score=comparison.candidate_metrics.brier_score,
            calibration_delta=_calibration_delta(comparison),
            sample_size=comparison.candidate_metrics.sample_size,
            decision=comparison.decision_stub,
            reasons=[
                COMPARISON_REASON_LABELS.get(reason, reason)
                for reason in comparison.reasons
            ],
        )
        for comparison in comparisons
    ]


def _calibration_delta(comparison: ModelComparisonStub) -> float | None:
    candidate_ece = comparison.candidate_metrics.ece
    baseline_ece = comparison.baseline_metrics.ece
    if candidate_ece is None or baseline_ece is None:
        return None
    return candidate_ece - baseline_ece


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)
