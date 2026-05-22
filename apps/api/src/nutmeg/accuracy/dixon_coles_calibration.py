from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from math import isclose

from pydantic import BaseModel, Field

from nutmeg.accuracy.calibration import calibration_bucket_key_for_probability
from nutmeg.accuracy.metrics import ONE_X_TWO_OUTCOMES, brier_score_1x2
from nutmeg.domain.accuracy import CalibrationBucketKey
from nutmeg.domain.settlement import OneXTwoOutcome
from nutmeg.market_resolver.one_x_two import resolve_1x2
from nutmeg.market_resolver.settlement import settle_1x2
from nutmeg.modeling import build_score_grid_from_estimate
from nutmeg.modeling.dixon_coles_training import (
    DixonColesTrainingMatch,
    DixonColesTrainingReport,
    estimate_dixon_coles_lambdas_for_match,
)

ONE_X_TWO_MARKET_TYPE = "1x2"


class DixonColesCalibrationObservation(BaseModel):
    fixture_id: str
    competition_id: str
    kickoff_time_utc: datetime
    outcome: OneXTwoOutcome
    predicted_probability: float = Field(ge=0.0, le=1.0)
    actual_occurred: bool
    bucket_key: CalibrationBucketKey


class DixonColesMatchCalibrationMetric(BaseModel):
    fixture_id: str
    competition_id: str
    kickoff_time_utc: datetime
    actual_outcome: OneXTwoOutcome
    home_win_probability: float = Field(ge=0.0, le=1.0)
    draw_probability: float = Field(ge=0.0, le=1.0)
    away_win_probability: float = Field(ge=0.0, le=1.0)
    actual_outcome_probability: float = Field(ge=0.0, le=1.0)
    brier_score: float = Field(ge=0.0)


class DixonColesCalibrationBucket(BaseModel):
    key: CalibrationBucketKey
    sample_size: int = Field(ge=0)
    predicted_probability_sum: float = Field(ge=0.0)
    actual_count: int = Field(ge=0)

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

    @property
    def absolute_error(self) -> float:
        return abs(self.average_predicted_probability - self.actual_frequency)

    def as_calibration_json(self) -> dict[str, object]:
        return {
            **self.model_dump(mode="json"),
            "average_predicted_probability": self.average_predicted_probability,
            "actual_frequency": self.actual_frequency,
            "absolute_error": self.absolute_error,
        }


class DixonColesValidationCalibrationReport(BaseModel):
    model_version: str
    market_type: str = ONE_X_TWO_MARKET_TYPE
    sample_size: int = Field(ge=1)
    observation_count: int = Field(ge=1)
    brier_score: float = Field(ge=0.0)
    expected_calibration_error: float = Field(ge=0.0)
    bucket_size: float = Field(gt=0.0, le=1.0)
    max_goals: int = Field(ge=1, le=20)
    validation_start_utc: datetime
    validation_end_utc: datetime
    competition_ids: list[str]
    match_metrics: list[DixonColesMatchCalibrationMetric]
    buckets: list[DixonColesCalibrationBucket]

    @property
    def metrics_json(self) -> dict[str, object]:
        return {
            "candidate_brier_score": self.brier_score,
            "candidate_ece": self.expected_calibration_error,
            "candidate_brier_score_source": "dixon_coles_validation_1x2",
            "candidate_ece_source": "dixon_coles_validation_1x2",
            "validation_calibration_sample_size": self.sample_size,
            "validation_calibration_observation_count": self.observation_count,
            "validation_calibration_bucket_size": self.bucket_size,
        }

    @property
    def calibration_json(self) -> dict[str, object]:
        return {
            "calibration_status": "validation_evidence_only",
            "calibration_required_before_promotion": True,
            "model_version": self.model_version,
            "market_type": self.market_type,
            "sample_size": self.sample_size,
            "observation_count": self.observation_count,
            "brier_score": self.brier_score,
            "expected_calibration_error": self.expected_calibration_error,
            "bucket_size": self.bucket_size,
            "max_goals": self.max_goals,
            "validation_start_utc": self.validation_start_utc.isoformat(),
            "validation_end_utc": self.validation_end_utc.isoformat(),
            "competition_ids": self.competition_ids,
            "buckets": [bucket.as_calibration_json() for bucket in self.buckets],
            "match_metrics": [
                metric.model_dump(mode="json") for metric in self.match_metrics
            ],
        }


def build_dixon_coles_validation_calibration_report(
    matches: Sequence[DixonColesTrainingMatch],
    *,
    report: DixonColesTrainingReport,
    max_goals: int = 8,
    bucket_size: float = 0.10,
) -> DixonColesValidationCalibrationReport:
    if not 0.0 < bucket_size <= 1.0:
        raise ValueError("bucket_size must be in (0, 1]")

    validation_matches = [
        match
        for match in matches
        if report.validation_start_utc
        <= _aware_utc(match.kickoff_time_utc)
        < report.validation_end_utc
    ]
    if not validation_matches:
        raise ValueError("validation window has no matches for calibration")

    match_metrics: list[DixonColesMatchCalibrationMetric] = []
    observations: list[DixonColesCalibrationObservation] = []
    buckets_by_stable_id: dict[str, DixonColesCalibrationBucket] = {}

    for match in validation_matches:
        probabilities = _market_probabilities_for_match(
            match,
            report=report,
            max_goals=max_goals,
        )
        actual_outcome = settle_1x2(match.home_goals, match.away_goals)
        match_metrics.append(
            DixonColesMatchCalibrationMetric(
                fixture_id=match.fixture_id,
                competition_id=match.competition_id,
                kickoff_time_utc=_aware_utc(match.kickoff_time_utc),
                actual_outcome=actual_outcome,
                home_win_probability=probabilities[OneXTwoOutcome.HOME_WIN],
                draw_probability=probabilities[OneXTwoOutcome.DRAW],
                away_win_probability=probabilities[OneXTwoOutcome.AWAY_WIN],
                actual_outcome_probability=probabilities[actual_outcome],
                brier_score=brier_score_1x2(probabilities, actual_outcome),
            )
        )

        for outcome in ONE_X_TWO_OUTCOMES:
            observation = _calibration_observation(
                match,
                outcome=outcome,
                predicted_probability=probabilities[outcome],
                actual_outcome=actual_outcome,
                model_version=report.model_version,
                bucket_size=bucket_size,
            )
            observations.append(observation)
            _add_observation_to_bucket(observation, buckets_by_stable_id)

    if len(observations) != len(validation_matches) * len(ONE_X_TWO_OUTCOMES):
        raise ValueError("1X2 calibration observations are incomplete")

    brier_score = sum(metric.brier_score for metric in match_metrics) / len(match_metrics)
    ece = _expected_calibration_error(buckets_by_stable_id.values(), len(observations))

    return DixonColesValidationCalibrationReport(
        model_version=report.model_version,
        sample_size=len(validation_matches),
        observation_count=len(observations),
        brier_score=brier_score,
        expected_calibration_error=ece,
        bucket_size=bucket_size,
        max_goals=max_goals,
        validation_start_utc=report.validation_start_utc,
        validation_end_utc=report.validation_end_utc,
        competition_ids=sorted({match.competition_id for match in validation_matches}),
        match_metrics=match_metrics,
        buckets=sorted(
            buckets_by_stable_id.values(),
            key=lambda bucket: bucket.key.stable_id,
        ),
    )


def _market_probabilities_for_match(
    match: DixonColesTrainingMatch,
    *,
    report: DixonColesTrainingReport,
    max_goals: int,
) -> dict[OneXTwoOutcome, float]:
    estimate = estimate_dixon_coles_lambdas_for_match(
        match,
        parameters=report.fitted_parameters,
        rho=report.selected_rho,
        as_of_time_utc=report.as_of_time_utc,
        time_decay_xi=report.time_decay_xi,
        model_version=report.model_version,
        feature_version="features-validation-calibration",
        calibration_version="calibration-validation-evidence",
    )
    resolved = resolve_1x2(build_score_grid_from_estimate(estimate, max_goals=max_goals))
    probabilities = {
        OneXTwoOutcome.HOME_WIN: resolved.home_win,
        OneXTwoOutcome.DRAW: resolved.draw,
        OneXTwoOutcome.AWAY_WIN: resolved.away_win,
    }
    total = sum(probabilities.values())
    if not isclose(total, 1.0, abs_tol=1e-6):
        raise ValueError("resolved 1X2 probabilities must sum to 1")
    return probabilities


def _calibration_observation(
    match: DixonColesTrainingMatch,
    *,
    outcome: OneXTwoOutcome,
    predicted_probability: float,
    actual_outcome: OneXTwoOutcome,
    model_version: str,
    bucket_size: float,
) -> DixonColesCalibrationObservation:
    return DixonColesCalibrationObservation(
        fixture_id=match.fixture_id,
        competition_id=match.competition_id,
        kickoff_time_utc=_aware_utc(match.kickoff_time_utc),
        outcome=outcome,
        predicted_probability=predicted_probability,
        actual_occurred=outcome is actual_outcome,
        bucket_key=calibration_bucket_key_for_probability(
            predicted_probability=predicted_probability,
            model_version=model_version,
            market_type=ONE_X_TWO_MARKET_TYPE,
            outcome=outcome.value,
            bucket_size=bucket_size,
            competition_id=match.competition_id,
        ),
    )


def _add_observation_to_bucket(
    observation: DixonColesCalibrationObservation,
    buckets_by_stable_id: dict[str, DixonColesCalibrationBucket],
) -> None:
    stable_id = observation.bucket_key.stable_id
    bucket = buckets_by_stable_id.get(stable_id)
    if bucket is None:
        bucket = DixonColesCalibrationBucket(
            key=observation.bucket_key,
            sample_size=0,
            predicted_probability_sum=0.0,
            actual_count=0,
        )
    buckets_by_stable_id[stable_id] = bucket.model_copy(
        update={
            "sample_size": bucket.sample_size + 1,
            "predicted_probability_sum": (
                bucket.predicted_probability_sum
                + observation.predicted_probability
            ),
            "actual_count": bucket.actual_count
            + (1 if observation.actual_occurred else 0),
        }
    )


def _expected_calibration_error(
    buckets: Iterable[DixonColesCalibrationBucket],
    observation_count: int,
) -> float:
    if observation_count <= 0:
        raise ValueError("observation_count must be positive")
    return sum(
        (bucket.sample_size / observation_count) * bucket.absolute_error
        for bucket in buckets
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
