"""竞彩 线源残差分解 — 软是因为陈旧,还是因为本土偏差?

Exploration direction #2 (2026-07-06). 竞彩 does two things: it mirrors Pinnacle
(with a lag) AND it adjusts on domestic handle. So when a 竞彩 SP sits off the
sharp truth (Pinnacle close), the gap has two causes, and telling them apart is
the whole game — they imply DIFFERENT edges:

  * **staleness** (freeze-gap, S1's domain): 竞彩 anchored to an OLD Pinnacle and
    the sharp line has since moved. Exploitable by a fresher line / late info.
  * **domestic residual** (retail bias, S2's domain, price-side): 竞彩 was set off
    the sharp market from the START — domestic money, home bias, local knowledge.

**The honest test (why a naïve open/close split is not enough).** A 竞彩 line that
perfectly mirrors the CLOSING sharp line has zero true domestic bias, yet naïvely
scoring "竞彩 − open" would tag it with a big residual. So staleness must be
credited with the FULL range the sharp line actually traversed. For each leg we
take the observed Pinnacle fair-P **band** [lo, hi] = (min, max) over every
snapshot. If 竞彩's de-vigged P sits INSIDE that band, some stale anchor could
have produced it → staleness suffices, domestic is not required. Only the part
where 竞彩 lands OUTSIDE the band is **irreducible domestic** — no stale-anchor
story explains it:

    irreducible_i = 竞彩_i − clamp(竞彩_i, lo_i, hi_i)   (0 when inside the band)

This is a conservative LOWER bound on domestic bias (it hands every benefit of the
doubt to staleness). The signed irreducible residual is also the honest shading
signal: bin legs by retail support and see whether 竞彩 lands its implied P above
the whole sharp band on crowd legs and below it on avoided legs. PURE module; the
CLI feeds de-vigged P triples + the band. EXPLORATORY — decomposes, no bets.
"""
from __future__ import annotations

from dataclasses import dataclass

_POS = ("主", "平", "客")


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


@dataclass(frozen=True)
class LineOriginSample:
    match_date: str
    home: str
    away: str
    jc_p: tuple[float, float, float]      # 竞彩 WPO fair P (主,平,客)
    open_p: tuple[float, float, float]    # Pinnacle earliest-snapshot fair P
    close_p: tuple[float, float, float]   # Pinnacle latest-pre-kickoff fair P
    band_lo: tuple[float, float, float]   # per-leg MIN fair P over all snapshots
    band_hi: tuple[float, float, float]   # per-leg MAX fair P over all snapshots
    support: tuple[float, float, float] | None = None

    @property
    def staleness(self) -> tuple[float, float, float]:
        """Observed net sharp move (open − close), per leg — context, not attribution."""
        return tuple(self.open_p[i] - self.close_p[i] for i in range(3))  # type: ignore[return-value]

    @property
    def total(self) -> tuple[float, float, float]:
        """竞彩's gap to the sharp truth (竞彩 − close), per leg."""
        return tuple(self.jc_p[i] - self.close_p[i] for i in range(3))  # type: ignore[return-value]

    @property
    def irreducible(self) -> tuple[float, float, float]:
        """Signed part of 竞彩 that lands OUTSIDE the whole observed Pinnacle band —
        the domestic residual no stale-anchor story can explain (0 when inside)."""
        return tuple(  # type: ignore[return-value]
            self.jc_p[i] - _clamp(self.jc_p[i], self.band_lo[i], self.band_hi[i])
            for i in range(3)
        )

    @property
    def fav(self) -> int:
        return max(range(3), key=lambda i: self.close_p[i])


@dataclass(frozen=True)
class LineOriginResult:
    n: int
    mean_abs_staleness: float          # mean |open−close| (observed sharp move, pp)
    mean_abs_total: float              # mean |竞彩−close| (gap to sharp truth, pp)
    mean_abs_irreducible: float        # mean |irreducible domestic| (pp) — the honest number
    frac_legs_outside_band: float      # share of legs where staleness is INSUFFICIENT
    domestic_share: float              # |irreducible| / |total| — gap fraction that's domestic
    by_position_irreducible: dict[str, float]  # signed mean irreducible per 主/平/客
    support_terciles: list[tuple[str, int, float, float]]  # (label,n,mean_sup,mean_irreducible)


def _mean(xs: list[float]) -> float:
    return float(sum(xs) / len(xs)) if xs else 0.0


def analyze(samples: list[LineOriginSample]) -> LineOriginResult:
    n = len(samples)
    stale = [abs(s.staleness[i]) for s in samples for i in range(3)]
    tot = [abs(s.total[i]) for s in samples for i in range(3)]
    irr = [abs(s.irreducible[i]) for s in samples for i in range(3)]
    mt, mi = _mean(tot), _mean(irr)
    outside = _mean([1.0 if abs(s.irreducible[i]) > 1e-9 else 0.0
                     for s in samples for i in range(3)])
    share = mi / mt if mt > 0 else 0.0
    by_pos = {_POS[i]: _mean([s.irreducible[i] for s in samples]) for i in range(3)}

    # honest shading: signed IRREDUCIBLE residual per leg, binned by retail support.
    legs = [(s.support[i], s.irreducible[i]) for s in samples if s.support for i in range(3)]
    terciles: list[tuple[str, int, float, float]] = []
    if len(legs) >= 6:
        legs.sort(key=lambda t: t[0])
        k = len(legs) // 3
        for label, grp in (("低票", legs[:k]), ("中票", legs[k:2 * k]), ("高票", legs[2 * k:])):
            terciles.append((label, len(grp),
                             _mean([g[0] for g in grp]), _mean([g[1] for g in grp])))
    return LineOriginResult(n, _mean(stale), mt, mi, outside, share, by_pos, terciles)


__all__ = ["LineOriginSample", "LineOriginResult", "analyze"]
