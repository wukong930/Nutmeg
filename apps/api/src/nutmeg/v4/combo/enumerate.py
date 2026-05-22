"""Parlay enumeration with pruning.

A parlay (串关) is a list of selections from distinct matches. We support
both 单式 (single outcome per leg) and 复式 (multiple outcomes per leg).

For combinatorial control:
  - Per match, we keep at most TOP_K_PER_MATCH (default 2) selections, ranked
    by edge. Negative-edge selections are discarded by default.
  - Total parlays are then bounded by C(N, k) × TOP_K^k which is feasible
    for k up to 8 with N up to ~14.

A parlay's metrics:
  - stake_units:       number of atomic combinations × 1 unit (单式 = 1)
  - hit_probability:   product of (selection probabilities) for each leg
                       For 复式 leg: sum of selected outcome probabilities
                       (assumes outcomes within a leg are mutually exclusive,
                       which they ARE for 1X2 and handicap 1X2 markets.)
  - expected_payout:   probability-weighted return
  - ev_per_unit:       expected_payout / stake_units - 1 (per-unit edge)

Note: 复式 ROI is generally lower than picking the single best outcome — but
it pays off if you're unsure and want hit-rate. We rank candidates by
ev_per_unit by default; user-facing layer can choose a different criterion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations, product
from typing import Sequence

from nutmeg.v4.combo.selections import Selection


TOP_K_PER_MATCH = 2  # number of selections per match to consider
MIN_LEGS = 2
MAX_LEGS = 8


@dataclass(frozen=True)
class ParlayLeg:
    """One leg of a parlay = one match, 1+ selected outcomes from one market."""
    match_id: str
    market_type: str
    selections: tuple[Selection, ...]   # all selections are from same match+market

    def hit_probability(self) -> float:
        # Outcomes within 1X2 (or handicap 1X2) are mutually exclusive
        return sum(s.probability for s in self.selections)

    def num_combinations(self) -> int:
        return len(self.selections)


@dataclass(frozen=True)
class Parlay:
    """A 串关 = ordered list of legs from distinct matches."""
    legs: tuple[ParlayLeg, ...]
    stake_units: int     # number of atomic single-parlays this 复式 ticket covers
    hit_probability: float
    expected_payout: float  # in units (1 unit per atomic combination)

    @property
    def k(self) -> int:
        return len(self.legs)

    @property
    def ev_per_unit(self) -> float:
        # expected_payout already in units; stake_units is the unit cost
        return (self.expected_payout / self.stake_units) - 1.0 if self.stake_units > 0 else 0.0

    @property
    def edge(self) -> float:
        return self.ev_per_unit

    @property
    def is_compound(self) -> bool:
        return any(leg.num_combinations() > 1 for leg in self.legs)


def _top_selections_per_match(
    selections: Sequence[Selection],
    top_k: int = TOP_K_PER_MATCH,
    min_edge: float = 0.0,
) -> dict[str, list[Selection]]:
    """Group by match_id, return top-k by edge (filtered to edge >= min_edge)."""
    by_match: dict[str, list[Selection]] = {}
    for s in selections:
        if s.edge < min_edge:
            continue
        by_match.setdefault(s.match_id, []).append(s)
    for mid in list(by_match.keys()):
        by_match[mid] = sorted(by_match[mid], key=lambda s: s.edge, reverse=True)[:top_k]
        if not by_match[mid]:
            del by_match[mid]
    return by_match


def _evaluate_parlay(legs: tuple[ParlayLeg, ...]) -> Parlay:
    """Compute stake_units, hit_probability, expected_payout for a parlay."""
    stake_units = 1
    for leg in legs:
        stake_units *= leg.num_combinations()
    hit_prob = 1.0
    for leg in legs:
        hit_prob *= leg.hit_probability()
    # Expected payout in units: sum over all atomic combinations of
    # (P(this combination) × product(odds in this combination))
    payout = 0.0
    leg_options = [leg.selections for leg in legs]
    for combo in product(*leg_options):
        p = 1.0
        odds_prod = 1.0
        for sel in combo:
            p *= sel.probability
            odds_prod *= sel.odds
        payout += p * odds_prod
    return Parlay(
        legs=legs,
        stake_units=stake_units,
        hit_probability=hit_prob,
        expected_payout=payout,
    )


def _expand_to_compound_legs(
    by_match: dict[str, list[Selection]],
) -> dict[str, list[ParlayLeg]]:
    """For each match, produce candidate legs: single-outcome legs + 复式 legs.

    复式 only combines selections within the same market_type (1X2 with 1X2,
    or handicap_1x2 with handicap_1x2 — not cross-market).
    """
    out: dict[str, list[ParlayLeg]] = {}
    for mid, sels in by_match.items():
        legs: list[ParlayLeg] = []
        # Single-outcome legs
        for s in sels:
            legs.append(ParlayLeg(match_id=mid, market_type=s.market_type, selections=(s,)))
        # 复式: combine 2 selections within same market
        by_market: dict[str, list[Selection]] = {}
        for s in sels:
            by_market.setdefault(s.market_type, []).append(s)
        for market_type, market_sels in by_market.items():
            if len(market_sels) >= 2:
                legs.append(ParlayLeg(
                    match_id=mid,
                    market_type=market_type,
                    selections=tuple(market_sels),
                ))
        out[mid] = legs
    return out


def generate_single_parlays(
    selections: Sequence[Selection],
    *,
    k_min: int = MIN_LEGS,
    k_max: int = MAX_LEGS,
    top_k_per_match: int = TOP_K_PER_MATCH,
    min_edge_per_leg: float = 0.0,
    include_compound: bool = True,
) -> list[Parlay]:
    """Enumerate all parlays with k_min..k_max legs.

    By default, only single-outcome legs are generated. Set include_compound=True
    to also enumerate 复式 (multiple outcomes within a leg).
    """
    by_match = _top_selections_per_match(selections, top_k_per_match, min_edge_per_leg)
    if len(by_match) < k_min:
        return []

    if include_compound:
        legs_per_match = _expand_to_compound_legs(by_match)
    else:
        legs_per_match = {
            mid: [ParlayLeg(match_id=mid, market_type=s.market_type, selections=(s,))
                  for s in sels]
            for mid, sels in by_match.items()
        }

    parlays: list[Parlay] = []
    match_ids = list(legs_per_match.keys())
    for k in range(k_min, min(k_max, len(match_ids)) + 1):
        for match_combo in combinations(match_ids, k):
            leg_options = [legs_per_match[mid] for mid in match_combo]
            for legs in product(*leg_options):
                parlays.append(_evaluate_parlay(legs))
    return parlays


def rank_parlays(
    parlays: Sequence[Parlay],
    *,
    by: str = "ev_per_unit",
    top_n: int | None = 20,
) -> list[Parlay]:
    """Sort parlays by a metric and optionally return top-N."""
    if by == "ev_per_unit":
        key = lambda p: p.ev_per_unit
    elif by == "hit_probability":
        key = lambda p: p.hit_probability
    elif by == "expected_payout":
        key = lambda p: p.expected_payout / p.stake_units
    else:
        raise ValueError(f"unknown ranking key: {by}")
    out = sorted(parlays, key=key, reverse=True)
    return out[:top_n] if top_n else out
