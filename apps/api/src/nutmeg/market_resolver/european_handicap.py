from __future__ import annotations

from nutmeg.domain.market import CNHandicapProbabilities
from nutmeg.domain.score_grid import ScoreProbabilityGrid
from nutmeg.market_resolver.cn_handicap import resolve_cn_handicap_1x2


def resolve_european_handicap_1x2(
    score_grid: ScoreProbabilityGrid,
    *,
    handicap: int,
) -> CNHandicapProbabilities:
    return resolve_cn_handicap_1x2(score_grid, handicap=handicap)
