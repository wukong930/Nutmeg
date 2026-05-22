from __future__ import annotations

from nutmeg.domain.market import AsianHandicapProbabilities
from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.domain.settlement import AsianHandicapSettlement
from nutmeg.market_resolver.settlement import settle_asian_handicap


def resolve_asian_handicap(
    score_grid: ScoreProbabilityGrid,
    *,
    line: float,
    side: str = "home",
) -> AsianHandicapProbabilities:
    if side not in {"home", "away"}:
        raise ValueError("side must be 'home' or 'away'")

    settlement_probabilities = {
        AsianHandicapSettlement.FULL_WIN: 0.0,
        AsianHandicapSettlement.HALF_WIN: 0.0,
        AsianHandicapSettlement.PUSH: 0.0,
        AsianHandicapSettlement.HALF_LOSS: 0.0,
        AsianHandicapSettlement.FULL_LOSS: 0.0,
    }

    for score in score_grid.iter_scores():
        settlement = settle_asian_handicap(
            score.home_goals,
            score.away_goals,
            line=line,
            side=side,
        )
        settlement_probabilities[settlement] += score.probability

    total = sum(settlement_probabilities.values())
    if total <= 0:
        raise ValueError("score grid must contain positive probability mass")
    full_win = settlement_probabilities[AsianHandicapSettlement.FULL_WIN] / total
    half_win = settlement_probabilities[AsianHandicapSettlement.HALF_WIN] / total
    push = settlement_probabilities[AsianHandicapSettlement.PUSH] / total
    half_loss = settlement_probabilities[AsianHandicapSettlement.HALF_LOSS] / total
    full_loss = settlement_probabilities[AsianHandicapSettlement.FULL_LOSS] / total
    expected_return = full_win + 0.5 * half_win - 0.5 * half_loss - full_loss
    return AsianHandicapProbabilities(
        line=line,
        side=side,
        full_win_prob=full_win,
        half_win_prob=half_win,
        push_prob=push,
        half_loss_prob=half_loss,
        full_loss_prob=full_loss,
        expected_return_prob=expected_return,
    )
