from __future__ import annotations

from nutmeg.domain.market import OneXTwoProbabilities
from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.domain.settlement import OneXTwoOutcome
from nutmeg.market_resolver.settlement import settle_1x2


def resolve_1x2(score_grid: ScoreProbabilityGrid) -> OneXTwoProbabilities:
    home_win = 0.0
    draw = 0.0
    away_win = 0.0
    for score in score_grid.iter_scores():
        outcome = settle_1x2(score.home_goals, score.away_goals)
        if outcome is OneXTwoOutcome.HOME_WIN:
            home_win += score.probability
        elif outcome is OneXTwoOutcome.DRAW:
            draw += score.probability
        else:
            away_win += score.probability
    total = home_win + draw + away_win
    if total <= 0:
        raise ValueError("score grid must contain positive probability mass")
    return OneXTwoProbabilities(
        home_win=home_win / total,
        draw=draw / total,
        away_win=away_win / total,
    )
