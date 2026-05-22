from __future__ import annotations

from datetime import UTC, datetime
from math import isclose, log

from nutmeg.accuracy import evaluate_prediction_snapshot
from nutmeg.domain.accuracy import ActualMatchResult
from nutmeg.domain.prediction import PredictionSnapshot
from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.domain.settlement import OneXTwoOutcome


def _snapshot() -> PredictionSnapshot:
    score_grid = ScoreProbabilityGrid(
        fixture_id="fix_accuracy",
        max_goals=2,
        grid=[
            [0.05, 0.05, 0.05],
            [0.25, 0.20, 0.05],
            [0.20, 0.10, 0.05],
        ],
        lambda_home=1.6,
        lambda_away=0.9,
        model_version="poisson-test",
        calibration_version="cal-test",
    )
    return PredictionSnapshot(
        fixture_id="fix_accuracy",
        prediction_time_utc=datetime(2026, 5, 6, 12, 0, tzinfo=UTC),
        model_version="poisson-test",
        feature_version="features-test",
        calibration_version="cal-test",
        score_grid=score_grid,
        market_probabilities={
            "1x2": {"home_win": 0.55, "draw": 0.30, "away_win": 0.15},
        },
        p_home=0.55,
        p_draw=0.30,
        p_away=0.15,
    )


def test_post_match_evaluator_compares_prediction_with_actual_result() -> None:
    evaluation = evaluate_prediction_snapshot(
        _snapshot(),
        ActualMatchResult(fixture_id="fix_accuracy", home_goals=0, away_goals=1),
        prediction_snapshot_id="snap_1",
        created_at=datetime(2026, 5, 7, 0, 0, tzinfo=UTC),
    )

    assert evaluation.fixture_id == "fix_accuracy"
    assert evaluation.prediction_snapshot_id == "snap_1"
    assert evaluation.actual_result_1x2 is OneXTwoOutcome.AWAY_WIN
    assert evaluation.predicted_result_1x2 is OneXTwoOutcome.HOME_WIN
    assert evaluation.actual_result_probability == 0.15
    assert isclose(evaluation.log_loss_1x2, -log(0.15))
    assert isclose(evaluation.brier_score_1x2, 0.55**2 + 0.30**2 + 0.85**2)
    assert evaluation.actual_score_probability == 0.05
    assert evaluation.actual_score_rank == 6
    assert "favorite_overestimated" in evaluation.error_tags
    assert "underdog_underestimated" in evaluation.error_tags
    assert "home_advantage_overestimated" in evaluation.error_tags


def test_post_match_evaluator_rejects_fixture_mismatch() -> None:
    try:
        evaluate_prediction_snapshot(
            _snapshot(),
            ActualMatchResult(fixture_id="other_fixture", home_goals=0, away_goals=1),
        )
    except ValueError as exc:
        assert "fixture_id" in str(exc)
    else:
        raise AssertionError("expected fixture mismatch to raise ValueError")
