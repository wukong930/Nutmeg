"""Parlay combination optimizer (2 串 1 to 8 串 1, 单式 + 复式)."""
from nutmeg.v4.combo.selections import (
    MatchInput, Selection, build_selections_from_match,
)
from nutmeg.v4.combo.enumerate import (
    Parlay, generate_single_parlays, rank_parlays,
)
from nutmeg.v4.combo.kelly import fractional_kelly_stake
from nutmeg.v4.combo.recommend import recommend_combinations
from nutmeg.v4.combo.single_match import (
    SingleMatchRecommendation,
    SingleMatchTicket,
    recommend_singles,
)

__all__ = [
    "MatchInput", "Selection", "build_selections_from_match",
    "Parlay", "generate_single_parlays", "rank_parlays",
    "fractional_kelly_stake",
    "recommend_combinations",
    "recommend_singles",
    "SingleMatchRecommendation", "SingleMatchTicket",
]
