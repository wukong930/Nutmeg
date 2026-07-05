"""竞彩 per-outcome vig decomposition — read the SHAPE of the water, not its size.

Exploration direction #1 (2026-07-06). The overall 竞彩 overround (~12.9%) is
known; nobody has asked whether it's spread EVENLY across 主/平/客 or SHADED —
loaded thick on the retail-favoured leg, thin on the leg the crowd avoids.

The clean null: under **proportional** (basic) vig, every leg carries the SAME
per-leg margin. Proof — if ``SP_i = 1 / (P_i·(1+OR))`` then ``P_i·SP_i = 1/(1+OR)``
for all i, so the per-leg −EV ``vig_i = 1 − P_i·SP_i = OR/(1+OR)`` is identical.
Therefore ANY deviation from equal per-leg vig is 竞彩 shading its margin
unevenly, and it is observable PRE-RESULT (no settlement needed) — which is the
whole point: if the shading tracks retail support, the soft (thin-vig) leg is
locatable from the price shape alone, before a ball is kicked.

Here ``P_i`` is the SHARP fair probability (Pinnacle WPO de-vig) and ``SP_i`` is
the 竞彩 stake-price. ``vig_i = 1 − P_i·SP_i`` is exactly the bettor's per-leg
−EV. This module is PURE (the CLI feeds it de-vigged samples). Exploratory: it
描述s the market, it does NOT unlock money — a shading pattern is a hypothesis to
pre-register for the autumn CLV gate, not a bet trigger.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

HOME, DRAW, AWAY = 0, 1, 2
_POS = ("主", "平", "客")


@dataclass(frozen=True)
class VigSample:
    """One match's per-leg vig. ``vig`` = (主,平,客) per-leg −EV = 1 − P·SP.
    ``support`` = retail ticket share (主,平,客) summing ~100, or None."""

    match_date: str
    home: str
    away: str
    vig: tuple[float, float, float]
    fair_p: tuple[float, float, float]
    sp: tuple[float, float, float]
    support: tuple[float, float, float] | None = None

    @property
    def fav(self) -> int:
        """Outcome position of the sharp favourite (max fair P)."""
        return max(range(3), key=lambda i: self.fair_p[i])

    @property
    def spread(self) -> float:
        """Within-match vig spread (max − min). 0 ⇔ proportional (unshaded)."""
        return max(self.vig) - min(self.vig)


def per_leg_vig(sp: tuple[float, float, float],
                fair_p: tuple[float, float, float]) -> tuple[float, float, float]:
    """Per-leg margin ``1 − P_i·SP_i`` for each outcome (= the bettor's −EV)."""
    return tuple(1.0 - fair_p[i] * sp[i] for i in range(3))  # type: ignore[return-value]


def overround(sp: tuple[float, float, float]) -> float:
    """竞彩 total overround ``Σ 1/SP_i − 1``."""
    return math.fsum(1.0 / s for s in sp) - 1.0


@dataclass(frozen=True)
class VigShapeResult:
    n: int
    by_position: dict[str, float]      # mean vig for 主/平/客
    fav_vig: float                     # mean vig on the sharp-favourite leg
    dog_vig: float                     # mean vig on the two non-favourite legs
    mean_spread: float                 # mean within-match (max−min) vig; 0=proportional
    mean_overround: float
    support_terciles: list[tuple[str, int, float, float]]  # (label, n_legs, mean_support, mean_vig)
    dog_support_terciles: list[tuple[str, int, float, float]]  # same, NON-favourite legs only


def _mean(xs: list[float]) -> float:
    return float(sum(xs) / len(xs)) if xs else 0.0


def analyze(samples: list[VigSample]) -> VigShapeResult:
    """Aggregate the vig shape. The shading test: bin every LEG by its retail
    support (terciles) and read mean per-leg vig — a rising vig-with-support
    curve is 竞彩 loading margin onto the crowd (soft leg = low-support side)."""
    n = len(samples)
    by_pos = {_POS[i]: _mean([s.vig[i] for s in samples]) for i in range(3)}
    fav_vig = _mean([s.vig[s.fav] for s in samples])
    dog_vig = _mean([s.vig[i] for s in samples for i in range(3) if i != s.fav])
    mean_spread = _mean([s.spread for s in samples])
    mean_or = _mean([overround(s.sp) for s in samples])

    def _terciles(pairs: list[tuple[float, float]]) -> list[tuple[str, int, float, float]]:
        """(support, vig) pairs → low/mid/high-support terciles with mean vig."""
        if len(pairs) < 6:
            return []
        pairs = sorted(pairs, key=lambda t: t[0])
        k = len(pairs) // 3
        cuts = [("低票", pairs[:k]), ("中票", pairs[k:2 * k]), ("高票", pairs[2 * k:])]
        return [(lab, len(g), _mean([p[0] for p in g]), _mean([p[1] for p in g]))
                for lab, g in cuts]

    # ALL legs by support (the raw razor), and NON-FAVOURITE legs only (controls
    # for favourite-ness — is support shading real BEYOND "favourites cost more"?)
    all_legs = [(s.support[i], s.vig[i]) for s in samples if s.support for i in range(3)]
    dog_legs = [(s.support[i], s.vig[i]) for s in samples if s.support
                for i in range(3) if i != s.fav]
    return VigShapeResult(n, by_pos, fav_vig, dog_vig, mean_spread, mean_or,
                          _terciles(all_legs), _terciles(dog_legs))


__all__ = [
    "HOME", "DRAW", "AWAY", "VigSample", "VigShapeResult",
    "per_leg_vig", "overround", "analyze",
]
