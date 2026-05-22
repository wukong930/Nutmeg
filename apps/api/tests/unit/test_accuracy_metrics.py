from __future__ import annotations

from math import isclose, log

from nutmeg.accuracy.metrics import (
    actual_score_probability,
    brier_score_1x2,
    expected_total_goals,
    log_loss,
    log_loss_1x2,
    score_rank,
)
from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.domain.settlement import OneXTwoOutcome


def test_log_loss_bounds_extreme_probabilities() -> None:
    assert isclose(log_loss(0.25), -log(0.25))
    assert log_loss(0.0) < 40
    assert log_loss(1.0) < 1e-12


def test_brier_and_log_loss_for_1x2_distribution() -> None:
    probabilities = {
        OneXTwoOutcome.HOME_WIN: 0.60,
        OneXTwoOutcome.DRAW: 0.25,
        OneXTwoOutcome.AWAY_WIN: 0.15,
    }

    assert isclose(log_loss_1x2(probabilities, OneXTwoOutcome.AWAY_WIN), -log(0.15))
    assert isclose(
        brier_score_1x2(probabilities, OneXTwoOutcome.AWAY_WIN),
        0.60**2 + 0.25**2 + (0.15 - 1.0) ** 2,
    )


def test_score_probability_rank_and_expected_total_goals() -> None:
    score_grid = ScoreProbabilityGrid(
        max_goals=1,
        grid=[
            [0.10, 0.20],
            [0.30, 0.40],
        ],
    )

    assert actual_score_probability(score_grid, home_goals=1, away_goals=0) == 0.30
    assert score_rank(score_grid, home_goals=1, away_goals=1) == 1
    assert score_rank(score_grid, home_goals=2, away_goals=0) is None
    assert isclose(expected_total_goals(score_grid), 1.30)
