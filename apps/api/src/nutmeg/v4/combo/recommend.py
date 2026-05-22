"""End-to-end recommendation: matches → selections → parlays → Kelly stakes.

Ranking strategy (matters more than people realize):
  - Ranking by raw ev_per_unit produces all-longshot tickets (0.1% hit-rate
    × 1000x payout has huge EV but is useless in practice).
  - Better criterion: expected log-growth (Kelly's actual objective). Tickets
    with too-low hit-probability give NEGATIVE log-growth even when raw EV is
    positive, because the rare hit doesn't outweigh the certain losses.
  - We rank by `kelly_log_growth`, which is the expected log-return PER UNIT
    of bankroll committed via the (capped fractional) Kelly stake.
  - Tickets with Kelly stake = 0 (capped) are excluded from the user-facing
    list since they can't actually be played.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from nutmeg.v4.combo.enumerate import Parlay, generate_single_parlays, rank_parlays
from nutmeg.v4.combo.kelly import KellyResult, fractional_kelly_stake
from nutmeg.v4.combo.selections import MatchInput, Selection, build_selections_from_match


@dataclass(frozen=True)
class Recommendation:
    """One recommended ticket = parlay + stake + diagnostics."""
    parlay: Parlay
    stake_units: int
    kelly: KellyResult
    kelly_log_growth: float
    rank: int

    @property
    def hit_probability(self) -> float:
        return self.parlay.hit_probability

    @property
    def ev_per_unit(self) -> float:
        return self.parlay.ev_per_unit

    @property
    def k_legs(self) -> int:
        return self.parlay.k


def _kelly_log_growth(hit_p: float, payout_per_unit: float, kelly_frac: float) -> float:
    """Expected log-growth of bankroll for a fractional-Kelly bet.

    If we bet fraction f of bankroll at odds b (=payout_per_unit - 1, where
    payout_per_unit > 1):
        new_bankroll = (1 - f) + f * payout_per_unit   if win   (prob p)
                    = (1 - f)                          if lose  (prob 1-p)
    Expected log-growth per period = p log(1-f + f*payout) + (1-p) log(1-f).
    Pure Kelly maximizes this analytically.
    """
    if kelly_frac <= 0 or payout_per_unit <= 1:
        return 0.0
    f = kelly_frac
    win = (1.0 - f) + f * payout_per_unit
    lose = max(1.0 - f, 1e-9)
    return hit_p * math.log(win) + (1.0 - hit_p) * math.log(lose)


def recommend_combinations(
    matches: Sequence[MatchInput],
    *,
    bankroll: float = 1000.0,
    k_min: int = 2,
    k_max: int = 8,
    top_k_per_match: int = 2,
    min_edge_per_leg: float = 0.0,
    include_compound: bool = True,
    top_n_recommendations: int = 10,
    kelly_fraction: float = 0.25,
    max_stake_fraction: float = 0.05,
    min_hit_probability: float = 0.02,
    min_kelly_stake: float = 1.0,
) -> list[Recommendation]:
    """Generate parlay recommendations.

    Filters applied (in order):
      1. ev_per_unit > 0           (no -EV bets)
      2. hit_probability >= min_hit_probability  (no pure longshots)
      3. kelly.recommended_stake >= min_kelly_stake  (large enough to play)
    Then sort surviving by kelly_log_growth descending.
    """
    all_selections: list[Selection] = []
    for m in matches:
        all_selections.extend(build_selections_from_match(m))

    parlays = generate_single_parlays(
        all_selections,
        k_min=k_min,
        k_max=k_max,
        top_k_per_match=top_k_per_match,
        min_edge_per_leg=min_edge_per_leg,
        include_compound=include_compound,
    )

    candidates: list[Recommendation] = []
    for p in parlays:
        if p.ev_per_unit <= 0:
            continue
        if p.hit_probability < min_hit_probability:
            continue
        k = fractional_kelly_stake(
            hit_probability=p.hit_probability,
            ev_per_unit=p.ev_per_unit,
            bankroll=bankroll,
            kelly_fraction=kelly_fraction,
            max_stake_fraction=max_stake_fraction,
        )
        if k.recommended_stake < min_kelly_stake:
            continue
        log_growth = _kelly_log_growth(p.hit_probability, 1.0 + k.win_multiplier_b, k.capped_kelly)
        candidates.append(Recommendation(
            parlay=p,
            stake_units=p.stake_units,
            kelly=k,
            kelly_log_growth=log_growth,
            rank=0,
        ))

    candidates.sort(key=lambda r: r.kelly_log_growth, reverse=True)
    out: list[Recommendation] = []
    for i, c in enumerate(candidates[:top_n_recommendations], start=1):
        out.append(Recommendation(
            parlay=c.parlay,
            stake_units=c.stake_units,
            kelly=c.kelly,
            kelly_log_growth=c.kelly_log_growth,
            rank=i,
        ))
    return out
