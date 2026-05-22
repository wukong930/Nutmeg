"""Fractional Kelly stake sizing for parlays (单式 + 复式).

Kelly for a single-event bet:
    f* = (b·p - q) / b
where:
    p = probability of winning (any outcome)
    q = 1 - p
    b = gross winning multiplier = average net payout per unit staked CONDITIONAL on winning

For a 单式 parlay: b = product(odds) - 1.
For a 复式 parlay: b = (expected_payout - stake_units * (1 - hit_p)) / (stake_units * hit_p) - 1
                    (i.e., average winning multiplier across winning sub-outcomes)

Equivalent form using EV (more convenient when EV is already computed):
    f* = ev_per_unit · p / (ev_per_unit + q)
This avoids re-deriving b. We use this form here.

Practical adjustments:
  - FRACTIONAL Kelly (e.g., 0.25×) for safety against model error.
  - Cap stake at max_stake_fraction of bankroll regardless of Kelly.
  - Stake = 0 when ev_per_unit ≤ 0.
"""
from __future__ import annotations

from dataclasses import dataclass


DEFAULT_KELLY_FRACTION = 0.25
DEFAULT_MAX_STAKE_FRACTION = 0.05


@dataclass(frozen=True)
class KellyResult:
    full_kelly: float          # raw Kelly fraction
    capped_kelly: float        # fractional × Kelly, capped at max
    recommended_stake: float   # absolute money units
    expected_return: float     # expected net profit at recommended stake
    win_multiplier_b: float    # the inferred b


def fractional_kelly_stake(
    *,
    hit_probability: float,
    ev_per_unit: float,
    bankroll: float,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    max_stake_fraction: float = DEFAULT_MAX_STAKE_FRACTION,
) -> KellyResult:
    """Compute fractional Kelly stake given EV/unit and hit probability.

    ev_per_unit is the expected net profit per unit stake (e.g., +0.788 means
    bet $1, expect $0.788 net profit over many trials).
    """
    p = hit_probability
    q = 1.0 - p
    if ev_per_unit <= 0 or p <= 0 or p >= 1:
        return KellyResult(0.0, 0.0, 0.0, 0.0, 0.0)
    # Derive b from EV identity: EV = p*b - q  =>  b = (EV + q) / p
    b = (ev_per_unit + q) / p
    if b <= 0:
        return KellyResult(0.0, 0.0, 0.0, 0.0, 0.0)
    full = (b * p - q) / b   # equals ev_per_unit / b
    if full <= 0:
        return KellyResult(0.0, 0.0, 0.0, 0.0, b)
    capped = min(full * kelly_fraction, max_stake_fraction)
    stake = bankroll * capped
    expected_return = stake * ev_per_unit
    return KellyResult(
        full_kelly=full,
        capped_kelly=capped,
        recommended_stake=stake,
        expected_return=expected_return,
        win_multiplier_b=b,
    )
