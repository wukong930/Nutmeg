"""China sports lottery (竞彩足球) rule constants + enforcement helpers.

V6 W4 — central place for the structural constraints of 中国体彩 竞彩足球.
Other modules import from here rather than hard-coding magic numbers so a
future rule change is a one-file edit.

Reference: 中国体彩官网 竞彩游戏规则
(https://www.lottery.gov.cn/jc/jcgz/index.shtml)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# Stake constraints ------------------------------------------------------

STAKE_UNIT_CNY: float = 2.0
"""Minimum stake unit. Every ticket stake must be a multiple of ¥2."""

MAX_TICKET_STAKE_CNY: float = 20_000.0
"""Maximum single-ticket stake. Beyond this the lottery system refuses."""

MAX_PERIOD_STAKE_CNY: float = 200_000.0
"""Aggregate single-period stake limit. Documentation hook; not enforced
in compound_pool (which operates on one user's session, not a period)."""


# Parlay constraints -----------------------------------------------------

MIN_LEGS_PER_TICKET: int = 1
"""Minimum legs per ticket. 1 = 单关 (single bet). Note: real lottery
allows 1-only for 单关 game variants; the standard 'mixed parlay' product
(混合过关) requires ≥ 2. The validator below enforces this for parlay
products specifically."""

MIN_PARLAY_LEGS: int = 2
"""Minimum legs for the 'mixed parlay' (混合过关) product."""

MAX_LEGS_PER_TICKET: int = 8
"""Maximum legs per parlay ticket (max 8串1 mixed parlay)."""


# Market / vig ------------------------------------------------------------

LOTTERY_PAYOUT_RATIO: float = 0.685
"""Average payout ratio (盘口返还率) — what fraction of pool is paid out.
Roughly: ¥1 in → ¥0.685 out long-run. So lottery vig ≈ 31.5%, vastly
higher than Pinnacle's ~2.5%."""

LOTTERY_VIG: float = 1.0 - LOTTERY_PAYOUT_RATIO  # ≈ 0.315


# Minimum EV thresholds --------------------------------------------------

# At vig 31.5% the "no edge" baseline is ev_per_unit ≈ -0.315 (you lose
# 31.5% of stake long-run if you bet randomly). So a positive EV at all
# means we beat a coin-flip-style bettor. But to overcome model error +
# correlation drift, we want some safety margin.
DEFAULT_MIN_EV_PER_UNIT: float = 0.05
"""Default minimum ev_per_unit to recommend a ticket. 5% means the model
expects at least ¥0.05 net profit per ¥1 staked over many trials, which
is generous enough to absorb some model miscalibration."""

DEFAULT_MIN_HIT_PROBABILITY: float = 0.05
"""Default minimum hit probability to surface a recommendation. Lower
hit-rate tickets with the same EV are riskier (variance dominates) so
we screen them out by default."""


# Game variant discriminator (for documentation / future expansion) ------

GameVariant = Literal[
    "胜平负",        # 1X2
    "让球胜平负",    # handicap 1X2 (integer handicap)
    "混合过关",      # mixed parlay across markets
    "比分",          # correct score (V6 skipped per user)
    "总进球数",      # over/under totals (V6 skipped per user)
    "半全场",        # half-time/full-time (V6 skipped per user)
]


@dataclass(frozen=True)
class LotteryRules:
    """Aggregated rule set passed through the recommendation pipeline.

    Default values match 中国体彩 竞彩足球 as of 2025. Override individual
    fields when modeling a different lottery (北京单场, exchange book, etc.).
    """

    stake_unit: float = STAKE_UNIT_CNY
    max_ticket_stake: float = MAX_TICKET_STAKE_CNY
    max_period_stake: float = MAX_PERIOD_STAKE_CNY
    min_parlay_legs: int = MIN_PARLAY_LEGS
    max_legs_per_ticket: int = MAX_LEGS_PER_TICKET
    payout_ratio: float = LOTTERY_PAYOUT_RATIO
    min_ev_per_unit: float = DEFAULT_MIN_EV_PER_UNIT
    min_hit_probability: float = DEFAULT_MIN_HIT_PROBABILITY

    @property
    def vig(self) -> float:
        return 1.0 - self.payout_ratio


JINGCAI_DEFAULT = LotteryRules()
"""Default rule set: 竞彩足球 standard."""


# Enforcement helpers ----------------------------------------------------

def cap_ticket_stake(raw_stake: float, rules: LotteryRules = JINGCAI_DEFAULT) -> float:
    """Apply the ¥20k single-ticket cap. Returns stake clipped to [0, cap]."""
    if raw_stake < 0:
        return 0.0
    return min(raw_stake, rules.max_ticket_stake)


def validate_legs_count(
    n: int,
    *,
    require_parlay: bool = False,
    rules: LotteryRules = JINGCAI_DEFAULT,
) -> None:
    """Raise ValueError when n is outside the lottery's allowed leg range.

    ``require_parlay=True`` enforces n ≥ 2 (混合过关 minimum), otherwise
    n ≥ 1 (allows 单关 product).
    """
    floor = rules.min_parlay_legs if require_parlay else 1
    if n < floor:
        raise ValueError(
            f"legs must be ≥ {floor} for this product; got {n}"
        )
    if n > rules.max_legs_per_ticket:
        raise ValueError(
            f"legs must be ≤ {rules.max_legs_per_ticket} (竞彩 limit); got {n}"
        )


def passes_recommendation_thresholds(
    *,
    hit_probability: float,
    ev_per_unit: float,
    rules: LotteryRules = JINGCAI_DEFAULT,
) -> bool:
    """Return True if a ticket meets the rule-defined recommendation gates.

    Used by recommend_pool / recommend_combinations to drop sub-threshold
    tickets BEFORE Kelly sizing (avoids spending Kelly budget on losers).
    """
    if hit_probability < rules.min_hit_probability:
        return False
    if ev_per_unit < rules.min_ev_per_unit:
        return False
    return True


__all__ = [
    "STAKE_UNIT_CNY",
    "MAX_TICKET_STAKE_CNY",
    "MAX_PERIOD_STAKE_CNY",
    "MIN_LEGS_PER_TICKET",
    "MIN_PARLAY_LEGS",
    "MAX_LEGS_PER_TICKET",
    "LOTTERY_PAYOUT_RATIO",
    "LOTTERY_VIG",
    "DEFAULT_MIN_EV_PER_UNIT",
    "DEFAULT_MIN_HIT_PROBABILITY",
    "GameVariant",
    "LotteryRules",
    "JINGCAI_DEFAULT",
    "cap_ticket_stake",
    "validate_legs_count",
    "passes_recommendation_thresholds",
]
