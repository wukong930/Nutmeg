"""Market resolver layer.

Resolvers consume score probability grids only. They do not train models or
modify underlying model probabilities.
"""

from nutmeg.market_resolver.asian_handicap import resolve_asian_handicap
from nutmeg.market_resolver.cn_handicap import resolve_cn_handicap_1x2
from nutmeg.market_resolver.converter import score_grid_to_market_probabilities
from nutmeg.market_resolver.correct_score import resolve_correct_score
from nutmeg.market_resolver.european_handicap import resolve_european_handicap_1x2
from nutmeg.market_resolver.one_x_two import resolve_1x2
from nutmeg.market_resolver.settlement import (
    correct_score_option_key,
    settle_1x2,
    settle_asian_1x2,
    settle_asian_handicap,
    settle_cn_handicap_1x2,
    settle_correct_score,
    settle_european_handicap_1x2,
)

__all__ = [
    "resolve_1x2",
    "resolve_asian_handicap",
    "resolve_cn_handicap_1x2",
    "resolve_correct_score",
    "resolve_european_handicap_1x2",
    "score_grid_to_market_probabilities",
    "settle_1x2",
    "settle_asian_1x2",
    "settle_asian_handicap",
    "settle_cn_handicap_1x2",
    "settle_correct_score",
    "settle_european_handicap_1x2",
    "correct_score_option_key",
]
