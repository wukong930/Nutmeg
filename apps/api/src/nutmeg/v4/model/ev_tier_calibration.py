"""V14 (Feature B) — empirical calibration of the EV-reliability tiers.

The dashboard grades every +EV by a heuristic P-band — sweet / edge / cold /
chalk — in ``_evRelTier`` (dashboard.html). Those boundaries (0.15 / 0.25 /
0.67 / 0.77) were drawn by hand. This module MEASURES, from realised results,
how well the Pinnacle de-vig P — the P in ``EV = P × 竞彩SP − 1`` — is actually
calibrated in each band. A band where the realised frequency tracks the implied
P ⇒ a +EV built on that P is the trustworthy kind; a band where realised drifts
from implied ⇒ the +EV there rests on a biased prior and earns its ⚠️.

Scope (honest): this measures the **P side** of EV (the de-vig prior), NOT the
竞彩 SP juice — 竞彩 odds are not in the API-Football cache. So it answers "is
our fair-P trustworthy per band", not "is the 竞彩 price fair per band". The
favorite-longshot bias (if any) shows up here as a band-dependent gap.

Pure functions only (no I/O) so the bucketing logic is unit-tested directly; the
CLI (cli/ev_tier_calibration.py) feeds it realised samples from the cache.
"""
from __future__ import annotations

from dataclasses import dataclass

# The five tiers, ordered as the dashboard shows them (best → worst-ish).
TIERS = ("sweet", "edge", "overpriced", "cold", "chalk")


def tier_of(p: float) -> str | None:
    """Mirror dashboard ``_evRelTier`` EXACTLY — these are the boundaries the
    dashboard ships, so they must not drift from the live badge.

      cold       : p < 0.15        (deep longshot, odds > ~6.7)
      overpriced : 0.15 ≤ p < 0.20 (the measured trap band, −6.9pp, n=323)
      chalk      : p > 0.77        (super-short favourite, odds < ~1.30)
      sweet      : 0.25 ≤ p ≤ 0.67 (odds ~1.5–4)
      edge       : otherwise       (0.20–0.25 or 0.67–0.77)

    The ``overpriced`` band was carved out of the old ``edge`` band by Feature B:
    a fine reliability sweep showed [0.15,0.20) is overpriced by −6.9pp while the
    rest of edge (0.20–0.25) is fine. Returns None for a non-probability so junk
    is dropped, not binned.
    """
    if not (p > 0.0 and p < 1.0):
        return None
    if p < 0.15:
        return "cold"
    if p < 0.20:
        return "overpriced"
    if p > 0.77:
        return "chalk"
    if 0.25 <= p <= 0.67:
        return "sweet"
    return "edge"


@dataclass
class BandStat:
    """Calibration of one band: how far the implied P sits from realised truth."""

    label: str
    n: int
    mean_p: float    # mean implied (de-vig) probability in the band
    hit_rate: float  # realised frequency (the outcome actually happened)
    gap: float       # hit_rate − mean_p  (signed calibration error)
    abs_gap: float   # |gap| — the band's reliability number (smaller = better)
    brier: float     # mean (p − y)² within the band


_NAN = float("nan")


def _stat(label: str, samples: list[tuple[float, int]]) -> BandStat:
    n = len(samples)
    if n == 0:
        return BandStat(label, 0, _NAN, _NAN, _NAN, _NAN, _NAN)
    mean_p = sum(p for p, _ in samples) / n
    hit = sum(y for _, y in samples) / n
    gap = hit - mean_p
    brier = sum((p - y) ** 2 for p, y in samples) / n
    return BandStat(label, n, mean_p, hit, gap, abs(gap), brier)


def by_tier(samples: list[tuple[float, int]]) -> dict[str, BandStat]:
    """``samples`` = ``[(implied_p, hit∈{0,1})]`` → one BandStat per tier.

    Each sample is one (outcome's de-vig P, did-it-happen) pair; pooling H/D/A
    across fixtures is the standard multiclass reliability construction.
    """
    buckets: dict[str, list[tuple[float, int]]] = {name: [] for name in TIERS}
    for p, y in samples:
        name = tier_of(p)
        if name is not None:
            buckets[name].append((p, y))
    return {name: _stat(name, buckets[name]) for name in TIERS}


def by_bins(samples: list[tuple[float, int]], edges: list[float]) -> list[BandStat]:
    """Fine reliability diagram: one BandStat per ``[edges[i], edges[i+1])`` bin
    (the final bin is closed on the right so p == edges[-1] is not dropped)."""
    out: list[BandStat] = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        last = i == len(edges) - 2
        seg = [
            (p, y) for p, y in samples
            if p >= lo and (p <= hi if last else p < hi)
        ]
        bracket = "]" if last else ")"
        out.append(_stat(f"[{lo:.2f},{hi:.2f}{bracket}", seg))
    return out
