"""竞彩 散户拥挤曲线 — how retail support MOVES between capture and kickoff.

Exploration direction #3 (2026-07-06), reader half. The old jingcai_vote table
upserts to latest (one row per match), so the intraday support trajectory was
being discarded; ``jingcai_vote_snapshots`` now retains it (append-only). This
module summarizes that time-series PURELY:

  * **drift** — per-leg (max − min) support over a match's snapshots: how much
    the crowd moved at all.
  * **bandwagon** — does the EARLY favourite's support GROW toward kickoff (crowd
    piles onto the front-runner) or shrink (late contrarian money)?

The eventual lead-lag question — does retail support move BEFORE or AFTER the
Pinnacle line — needs the vote series joined to odds_snapshots by timestamp and
is deferred until the series accumulates (autumn). This is the descriptive base.
EXPLORATORY, read-only; a crowding pattern is an autumn hypothesis, not a bet.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MatchSeries:
    """One match's intraday support snapshots, sorted by captured_at.
    ``snaps`` = list of (captured_at, (h_support, d_support, a_support))."""

    match_date: str
    home: str
    away: str
    snaps: list[tuple[str, tuple[float, float, float]]]

    @property
    def n(self) -> int:
        return len(self.snaps)

    @property
    def drift(self) -> tuple[float, float, float]:
        """Per-leg (max − min) support across the snapshots (0 if <2 snaps)."""
        if self.n < 2:
            return (0.0, 0.0, 0.0)
        return tuple(  # type: ignore[return-value]
            max(s[1][i] for s in self.snaps) - min(s[1][i] for s in self.snaps)
            for i in range(3)
        )

    @property
    def fav_early(self) -> int:
        """Outcome the crowd favours at the FIRST snapshot (max support)."""
        return max(range(3), key=lambda i: self.snaps[0][1][i])

    @property
    def fav_support_delta(self) -> float:
        """Early-favourite's support change (last − first snapshot). >0 = bandwagon."""
        i = self.fav_early
        return self.snaps[-1][1][i] - self.snaps[0][1][i]


@dataclass(frozen=True)
class CrowdingResult:
    n_matches: int
    n_series: int          # matches with ≥2 snapshots (a real trajectory)
    mean_drift_pp: float   # mean per-leg drift over series-matches
    max_drift_pp: float
    bandwagon_frac: float  # share of series-matches where early-fav support rose


def summarize(series: list[MatchSeries]) -> CrowdingResult:
    n = len(series)
    ser = [s for s in series if s.n >= 2]
    if not ser:
        return CrowdingResult(n, 0, 0.0, 0.0, 0.0)
    drifts = [d for s in ser for d in s.drift]
    mean_drift = float(sum(drifts) / len(drifts))
    bw = sum(1 for s in ser if s.fav_support_delta > 0) / len(ser)
    return CrowdingResult(n, len(ser), mean_drift, float(max(drifts)), bw)


__all__ = ["MatchSeries", "CrowdingResult", "summarize"]
