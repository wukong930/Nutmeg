from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from nutmeg.accuracy.workflow import (
    evaluate_and_persist_post_match_result,
    one_x_two_calibration_observations,
)
from nutmeg.domain.accuracy import (
    ActualMatchResult,
    CalibrationBucket,
    CalibrationBucketKey,
    PredictionEvaluation,
    StoredPredictionEvaluation,
)
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.domain.score_grid import ScoreProbabilityGrid


class FakeAccuracyWriteRepository:
    def __init__(self) -> None:
        self.saved_evaluation: PredictionEvaluation | None = None
        self.observations: list[object] = []

    def save_prediction_evaluation(
        self,
        evaluation: PredictionEvaluation,
    ) -> StoredPredictionEvaluation:
        self.saved_evaluation = evaluation
        return StoredPredictionEvaluation(evaluation_id=5, evaluation=evaluation)

    def upsert_calibration_observations(
        self,
        observations: Sequence[object],
        *,
        model_version: str,
        bucket_size: float = 0.10,
    ) -> list[CalibrationBucket]:
        self.observations = list(observations)
        return [
            CalibrationBucket(
                key=CalibrationBucketKey(
                    model_version=model_version,
                    market_type="1x2",
                    outcome="home_win",
                    competition_id="EPL",
                    bucket_start=0.4,
                    bucket_end=0.5,
                ),
                sample_size=1,
                predicted_probability_sum=0.45,
                actual_count=0,
            )
        ]


def test_one_x_two_calibration_observations_include_all_outcomes() -> None:
    observations = one_x_two_calibration_observations(
        _snapshot(),
        ActualMatchResult(fixture_id="fix_epl_001", home_goals=1, away_goals=1),
        competition_id="EPL",
    )

    assert [observation.outcome for observation in observations] == [
        "home_win",
        "draw",
        "away_win",
    ]
    assert [observation.actual_occurred for observation in observations] == [
        False,
        True,
        False,
    ]
    assert [observation.competition_id for observation in observations] == [
        "EPL",
        "EPL",
        "EPL",
    ]


def test_post_match_workflow_persists_evaluation_and_calibration() -> None:
    repository = FakeAccuracyWriteRepository()

    result = evaluate_and_persist_post_match_result(
        snapshot=_snapshot(),
        actual_result=ActualMatchResult(fixture_id="fix_epl_001", home_goals=1, away_goals=1),
        repository=repository,
        prediction_snapshot_id="42",
        competition_id="EPL",
    )

    assert result.stored_evaluation.evaluation_id == 5
    assert repository.saved_evaluation is not None
    assert repository.saved_evaluation.fixture_id == "fix_epl_001"
    assert repository.saved_evaluation.prediction_snapshot_id == "42"
    assert len(repository.observations) == 3
    assert result.calibration_buckets[0].key.competition_id == "EPL"


def _snapshot() -> PredictionSnapshot:
    score_grid = ScoreProbabilityGrid(
        fixture_id="fix_epl_001",
        max_goals=2,
        grid=[
            [0.10, 0.05, 0.05],
            [0.20, 0.15, 0.05],
            [0.20, 0.10, 0.10],
        ],
        lambda_home=1.4,
        lambda_away=1.0,
        model_version="poisson-m1.0.0",
        calibration_version="calibration-m1.0.0",
    )
    return PredictionSnapshot(
        fixture_id="fix_epl_001",
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        model_version="poisson-m1.0.0",
        feature_version="features-m1.0.0",
        calibration_version="calibration-m1.0.0",
        score_grid=score_grid,
        market_probabilities={"1x2": {"home_win": 0.45, "draw": 0.30, "away_win": 0.25}},
        p_home=0.45,
        p_draw=0.30,
        p_away=0.25,
    )
