from __future__ import annotations

from nutmeg.domain.market import CNHandicapProbabilities
from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.domain.settlement import HandicapOneXTwoOutcome
from nutmeg.market_resolver.settlement import settle_cn_handicap_1x2


def resolve_cn_handicap_1x2(
    score_grid: ScoreProbabilityGrid,
    *,
    handicap: int,
) -> CNHandicapProbabilities:
    handicap_home_win = 0.0
    handicap_draw = 0.0
    handicap_away_win = 0.0
    for score in score_grid.iter_scores():
        outcome = settle_cn_handicap_1x2(score.home_goals, score.away_goals, handicap=handicap)
        if outcome is HandicapOneXTwoOutcome.HANDICAP_HOME_WIN:
            handicap_home_win += score.probability
        elif outcome is HandicapOneXTwoOutcome.HANDICAP_DRAW:
            handicap_draw += score.probability
        else:
            handicap_away_win += score.probability
    total = handicap_home_win + handicap_draw + handicap_away_win
    if total <= 0:
        raise ValueError("score grid must contain positive probability mass")
    return CNHandicapProbabilities(
        handicap=handicap,
        handicap_home_win=handicap_home_win / total,
        handicap_draw=handicap_draw / total,
        handicap_away_win=handicap_away_win / total,
    )
