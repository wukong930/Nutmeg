"""M-select-N compound parlay pool — V6 W3.

The user's core workflow: pick M matches (each with one pre-decided
outcome — 1X2 or handicap), pick N (the parlay size), buy ALL C(M, N)
tickets. Each ticket is an N-leg parlay; user wins on every ticket whose
N legs all hit. Aggregate hit-rate scales with the binomial structure.

Example: M=6, N=4 → 15 tickets, each a different 4-leg parlay over the
same 6-match pool. If exactly 4 of 6 legs hit, the user wins 1 ticket;
if 5 hit → C(5,4)=5 tickets win; if 6 hit → C(6,4)=15 win.

Why this matters in the China lottery context: the lottery's vig (~31%)
means single-ticket EV is usually negative unless edge is very large.
Compound betting spreads risk across many tickets — a "5 out of 6"
outcome still pays something. It's also the standard 复式投注 product:
users buy 复式 tickets routinely.

Stake constraints inherited from China lottery (`竞彩足球`):
- ¥2 per unit
- Stake must be a 2's multiple
- Single-ticket cap ¥20,000 (V6 W4 will enforce)
- Mixed-parlay max 8 legs (n ≤ 8)

Per-ticket sizing:
1. Independent Kelly on each ticket's (hit_p, ev_per_unit, bankroll-slice)
2. Quantize down to nearest ¥2 (drop below ¥2 → zero stake → skip ticket)
3. Optionally rescale all stakes proportionally if Σ exceeds max_total_budget

Independence assumption:
For hit_p of an N-leg parlay we use Π p_i across legs — this assumes
the N legs are independent. In practice some matches in a fixture pool
share information (same day weather, same broadcaster, same referee
crew). The independence assumption slightly OVERestimates hit_p when
matches are positively correlated; using fractional Kelly (default 0.25)
gives margin against this.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from math import comb

from nutmeg.v4.combo.kelly import (
    DEFAULT_KELLY_FRACTION,
    DEFAULT_MAX_STAKE_FRACTION,
    fractional_kelly_stake,
)
from nutmeg.v4.combo.selections import Selection


# Stake unit for 中国体彩 竞彩足球
STAKE_UNIT_CNY = 2.0

# Mixed-parlay max legs per 竞彩 rules (V6 W4 also enforces)
MAX_LEGS_PER_TICKET = 8


def quantize_stake(raw_stake: float, unit: float = STAKE_UNIT_CNY) -> float:
    """Round DOWN to the nearest stake_unit. Sub-unit stakes → 0."""
    if raw_stake < unit:
        return 0.0
    return (int(raw_stake // unit)) * unit


@dataclass(frozen=True)
class PoolTicket:
    """One ticket in the M-select-N pool: N legs as a tuple of Selection."""

    legs: tuple[Selection, ...]
    hit_probability: float
    combined_odds: float       # product of leg odds
    ev_per_unit: float         # combined_odds * hit_p - 1
    raw_kelly_stake: float     # unquantized recommended stake
    stake: float               # quantized stake (¥2 multiples)
    expected_return: float     # stake * ev_per_unit (after quantization)

    @property
    def n_legs(self) -> int:
        return len(self.legs)

    @property
    def match_ids(self) -> tuple[str, ...]:
        return tuple(leg.match_id for leg in self.legs)


@dataclass
class PoolRecommendation:
    """Output of `recommend_pool` — every C(M,N) ticket + aggregates."""

    m: int                                      # input pool size
    n: int                                      # legs per ticket
    n_combinations: int                         # = C(M, N)
    tickets: list[PoolTicket]                   # sorted by EV desc
    selected_tickets: list[PoolTicket] = field(default_factory=list)  # stake > 0 only
    total_stake: float = 0.0
    total_expected_return: float = 0.0


def evaluate_ticket(
    legs: tuple[Selection, ...],
    *,
    bankroll: float,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake_fraction_per_ticket: float = DEFAULT_MAX_STAKE_FRACTION,
    stake_unit: float = STAKE_UNIT_CNY,
) -> PoolTicket:
    """Compute hit_p / odds / EV / quantized stake for a single ticket.

    ``max_stake_fraction_per_ticket`` is the per-ticket cap; the multi-
    ticket budget cap is applied separately by recommend_pool.
    """
    if not legs:
        raise ValueError("ticket must have at least 1 leg")

    hit_p = 1.0
    odds = 1.0
    for leg in legs:
        hit_p *= leg.probability
        odds *= leg.odds
    ev = odds * hit_p - 1.0

    kr = fractional_kelly_stake(
        hit_probability=hit_p,
        ev_per_unit=ev,
        bankroll=bankroll,
        kelly_fraction=kelly_fraction,
        max_stake_fraction=max_stake_fraction_per_ticket,
    )
    quantized = quantize_stake(kr.recommended_stake, stake_unit)
    expected_return = quantized * ev
    return PoolTicket(
        legs=legs,
        hit_probability=hit_p,
        combined_odds=odds,
        ev_per_unit=ev,
        raw_kelly_stake=kr.recommended_stake,
        stake=quantized,
        expected_return=expected_return,
    )


def enumerate_combinations(
    chosen_per_match: list[Selection],
    n: int,
) -> list[tuple[Selection, ...]]:
    """C(M, N) ticket-shape: each combo picks N of the M user-chosen selections.

    ``chosen_per_match`` is one Selection per match (the user's pre-decided
    outcome for that match — they've already picked H/D/A and/or handicap).
    Compound (multi-outcome-per-match) pools are a different product;
    use ``combo.enumerate.enumerate_parlays`` for that.

    Raises ValueError on n < 1, n > len(chosen_per_match), or n > MAX_LEGS_PER_TICKET.
    """
    m = len(chosen_per_match)
    if not (1 <= n <= m):
        raise ValueError(f"n must be in [1, {m}], got {n}")
    if n > MAX_LEGS_PER_TICKET:
        raise ValueError(
            f"竞彩 mixed-parlay max legs = {MAX_LEGS_PER_TICKET}, got n={n}"
        )
    return list(combinations(chosen_per_match, n))


def recommend_pool(
    chosen_per_match: list[Selection],
    n: int,
    *,
    bankroll: float,
    max_total_budget: float | None = None,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake_fraction_per_ticket: float = DEFAULT_MAX_STAKE_FRACTION,
    stake_unit: float = STAKE_UNIT_CNY,
) -> PoolRecommendation:
    """Recommend C(M,N) tickets, sized via independent Kelly + ¥2 quantization.

    Workflow:
    1. Enumerate every C(M, N) leg combination
    2. For each: compute hit_p (Π p_i) and combined_odds (Π odds_i)
    3. Independent Kelly stake on each; quantize down to ¥2
    4. If sum(stakes) > max_total_budget: proportionally rescale + re-quantize

    Sort tickets by EV-per-unit descending so users see the best-value
    combinations first.
    """
    m = len(chosen_per_match)
    n_combos = comb(m, n)

    raw_combos = enumerate_combinations(chosen_per_match, n)
    tickets = [
        evaluate_ticket(
            legs=combo_legs,
            bankroll=bankroll,
            kelly_fraction=kelly_fraction,
            max_stake_fraction_per_ticket=max_stake_fraction_per_ticket,
            stake_unit=stake_unit,
        )
        for combo_legs in raw_combos
    ]
    # Sort by EV descending (most-valuable first)
    tickets.sort(key=lambda t: t.ev_per_unit, reverse=True)

    # Apply total-budget cap by proportional rescale
    total_stake = sum(t.stake for t in tickets)
    if max_total_budget is not None and total_stake > max_total_budget > 0:
        scale = max_total_budget / total_stake
        rescaled: list[PoolTicket] = []
        for t in tickets:
            new_stake = quantize_stake(t.stake * scale, stake_unit)
            rescaled.append(PoolTicket(
                legs=t.legs,
                hit_probability=t.hit_probability,
                combined_odds=t.combined_odds,
                ev_per_unit=t.ev_per_unit,
                raw_kelly_stake=t.raw_kelly_stake,
                stake=new_stake,
                expected_return=new_stake * t.ev_per_unit,
            ))
        tickets = rescaled

    selected = [t for t in tickets if t.stake > 0]
    return PoolRecommendation(
        m=m,
        n=n,
        n_combinations=n_combos,
        tickets=tickets,
        selected_tickets=selected,
        total_stake=sum(t.stake for t in selected),
        total_expected_return=sum(t.expected_return for t in selected),
    )


__all__ = [
    "MAX_LEGS_PER_TICKET",
    "STAKE_UNIT_CNY",
    "PoolTicket",
    "PoolRecommendation",
    "quantize_stake",
    "evaluate_ticket",
    "enumerate_combinations",
    "recommend_pool",
]
