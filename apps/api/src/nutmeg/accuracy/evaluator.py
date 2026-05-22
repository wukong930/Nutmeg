from __future__ import annotations

from datetime import UTC, datetime

from nutmeg.accuracy.error_classifier import classify_prediction_error
from nutmeg.accuracy.metrics import (
    actual_score_probability,
    brier_score_1x2,
    log_loss_1x2,
    score_rank,
)
from nutmeg.domain.accuracy import ActualMatchResult, PredictionEvaluation
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.domain.settlement import OneXTwoOutcome


def one_x_two_probabilities_from_snapshot(
    snapshot: PredictionSnapshot,
) -> dict[OneXTwoOutcome, float]:
    return {
        OneXTwoOutcome.HOME_WIN: snapshot.p_home,
        OneXTwoOutcome.DRAW: snapshot.p_draw,
        OneXTwoOutcome.AWAY_WIN: snapshot.p_away,
    }


def predicted_1x2_outcome(snapshot: PredictionSnapshot) -> OneXTwoOutcome:
    probabilities = one_x_two_probabilities_from_snapshot(snapshot)
    return max(probabilities, key=lambda outcome: probabilities[outcome])


def evaluate_prediction_snapshot(
    snapshot: PredictionSnapshot,
    actual_result: ActualMatchResult,
    *,
    prediction_snapshot_id: str | None = None,
    market_comparison_json: dict[str, object] | None = None,
    created_at: datetime | None = None,
) -> PredictionEvaluation:
    if snapshot.fixture_id != actual_result.fixture_id:
        raise ValueError("prediction snapshot and actual result must share fixture_id")

    probabilities = one_x_two_probabilities_from_snapshot(snapshot)
    actual_outcome = actual_result.result_1x2
    predicted_outcome = predicted_1x2_outcome(snapshot)
    actual_outcome_probability = probabilities[actual_outcome]
    score_probability = actual_score_probability(
        snapshot.score_grid,
        home_goals=actual_result.home_goals,
        away_goals=actual_result.away_goals,
    )
    rank = score_rank(
        snapshot.score_grid,
        home_goals=actual_result.home_goals,
        away_goals=actual_result.away_goals,
    )
    error_tags = classify_prediction_error(
        snapshot,
        actual_result,
        predicted_outcome=predicted_outcome,
        actual_outcome_probability=actual_outcome_probability,
        actual_score_probability=score_probability,
    )

    return PredictionEvaluation(
        fixture_id=snapshot.fixture_id,
        prediction_snapshot_id=prediction_snapshot_id,
        prediction_time_utc=snapshot.prediction_time_utc,
        model_version=snapshot.model_version,
        feature_version=snapshot.feature_version,
        calibration_version=snapshot.calibration_version,
        actual_home_goals=actual_result.home_goals,
        actual_away_goals=actual_result.away_goals,
        actual_result_1x2=actual_outcome,
        predicted_result_1x2=predicted_outcome,
        actual_result_probability=actual_outcome_probability,
        log_loss_1x2=log_loss_1x2(probabilities, actual_outcome),
        brier_score_1x2=brier_score_1x2(probabilities, actual_outcome),
        actual_score_probability=score_probability,
        actual_score_rank=rank,
        market_comparison_json=market_comparison_json or {},
        error_tags=error_tags,
        created_at=created_at or datetime.now(tz=UTC),
    )
