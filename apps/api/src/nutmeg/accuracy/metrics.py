from __future__ import annotations

from math import log

from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.domain.settlement import OneXTwoOutcome

ONE_X_TWO_OUTCOMES = (
    OneXTwoOutcome.HOME_WIN,
    OneXTwoOutcome.DRAW,
    OneXTwoOutcome.AWAY_WIN,
)


def log_loss(probability: float, *, epsilon: float = 1e-15) -> float:
    bounded_probability = max(epsilon, min(1.0 - epsilon, probability))
    return -log(bounded_probability)


def log_loss_1x2(
    probabilities: dict[OneXTwoOutcome, float],
    actual_outcome: OneXTwoOutcome,
) -> float:
    return log_loss(probabilities[actual_outcome])


def brier_score_1x2(
    probabilities: dict[OneXTwoOutcome, float],
    actual_outcome: OneXTwoOutcome,
) -> float:
    return sum(
        (probabilities[outcome] - (1.0 if outcome is actual_outcome else 0.0)) ** 2
        for outcome in ONE_X_TWO_OUTCOMES
    )


def actual_score_probability(
    score_grid: ScoreProbabilityGrid,
    *,
    home_goals: int,
    away_goals: int,
) -> float:
    return score_grid.probability_for(home_goals, away_goals)


def score_rank(
    score_grid: ScoreProbabilityGrid,
    *,
    home_goals: int,
    away_goals: int,
) -> int | None:
    if home_goals > score_grid.max_goals or away_goals > score_grid.max_goals:
        return None
    sorted_scores = sorted(
        score_grid.iter_scores(),
        key=lambda score: score.probability,
        reverse=True,
    )
    for index, score in enumerate(sorted_scores, start=1):
        if score.home_goals == home_goals and score.away_goals == away_goals:
            return index
    return None


def expected_total_goals(score_grid: ScoreProbabilityGrid) -> float:
    return sum(
        (score.home_goals + score.away_goals) * score.probability
        for score in score_grid.iter_scores()
    )
