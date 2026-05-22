from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel

from nutmeg.accuracy.evaluator import evaluate_prediction_snapshot
from nutmeg.accuracy.summary import CalibrationObservation
from nutmeg.domain.accuracy import (
    ActualMatchResult,
    CalibrationBucket,
    PredictionEvaluation,
    StoredPredictionEvaluation,
)
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.domain.settlement import OneXTwoOutcome


class AccuracyWriteRepository(Protocol):
    def save_prediction_evaluation(
        self,
        evaluation: PredictionEvaluation,
    ) -> StoredPredictionEvaluation: ...

    def upsert_calibration_observations(
        self,
        observations: Sequence[CalibrationObservation],
        *,
        model_version: str,
        bucket_size: float = 0.10,
    ) -> list[CalibrationBucket]: ...


class PersistedPostMatchEvaluation(BaseModel):
    stored_evaluation: StoredPredictionEvaluation
    calibration_buckets: list[CalibrationBucket]


def evaluate_and_persist_post_match_result(
    *,
    snapshot: PredictionSnapshot,
    actual_result: ActualMatchResult,
    repository: AccuracyWriteRepository,
    prediction_snapshot_id: str | None = None,
    competition_id: str | None = None,
    bucket_size: float = 0.10,
) -> PersistedPostMatchEvaluation:
    evaluation = evaluate_prediction_snapshot(
        snapshot,
        actual_result,
        prediction_snapshot_id=prediction_snapshot_id,
    )
    stored = repository.save_prediction_evaluation(evaluation)
    buckets = repository.upsert_calibration_observations(
        one_x_two_calibration_observations(
            snapshot,
            actual_result,
            competition_id=competition_id,
        ),
        model_version=snapshot.model_version,
        bucket_size=bucket_size,
    )
    return PersistedPostMatchEvaluation(
        stored_evaluation=stored,
        calibration_buckets=buckets,
    )


def one_x_two_calibration_observations(
    snapshot: PredictionSnapshot,
    actual_result: ActualMatchResult,
    *,
    competition_id: str | None = None,
) -> tuple[CalibrationObservation, CalibrationObservation, CalibrationObservation]:
    if snapshot.fixture_id != actual_result.fixture_id:
        raise ValueError("prediction snapshot and actual result must share fixture_id")
    actual_outcome = actual_result.result_1x2
    return (
        CalibrationObservation(
            market_type="1x2",
            outcome=OneXTwoOutcome.HOME_WIN.value,
            predicted_probability=snapshot.p_home,
            actual_occurred=actual_outcome is OneXTwoOutcome.HOME_WIN,
            competition_id=competition_id,
        ),
        CalibrationObservation(
            market_type="1x2",
            outcome=OneXTwoOutcome.DRAW.value,
            predicted_probability=snapshot.p_draw,
            actual_occurred=actual_outcome is OneXTwoOutcome.DRAW,
            competition_id=competition_id,
        ),
        CalibrationObservation(
            market_type="1x2",
            outcome=OneXTwoOutcome.AWAY_WIN.value,
            predicted_probability=snapshot.p_away,
            actual_occurred=actual_outcome is OneXTwoOutcome.AWAY_WIN,
            competition_id=competition_id,
        ),
    )
