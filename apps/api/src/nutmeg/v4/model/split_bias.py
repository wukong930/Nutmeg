"""S6 让球切分偏差复现 — pure statistics for the pre-registered autumn test.

Frozen 2026-07-05 to lock the recipe BEFORE the autumn (≥2026-08-01) data
arrives, so the验证 is byte-reproducible and not a forking-paths after-the-fact
fit. The spec lives in ``docs/autumn_prereg_analysis_plan.md`` §4 S6 + its 特别
条款 (C1); this module is the normative implementation.

The finding (``docs/ah_vs_grid_three_way_backtest_2026-07-04.md`` 附录, in-sample
2,747 matches): at |handicap| = 1 the DC grid **over-states 让胜 by ~2.7pp** and
**under-states 让平 by ~2.7pp**, while 让负 (= 1 − P(home win), pinned by the 1X2
fit) is exact — so the anchor is innocent and the bias is a net-margin split
error (win-by-one clustering the Poisson grid misses).

S6 measures, per |h|=1 sample, the residual ``r = 1{让平} − P_grid(让平)`` and
runs a one-sided cluster-robust t (clustered by match-day, reusing
``clv_gate.mean_clv_test``) of H1: E[r] > 0. The 让胜 residual (expected mirror-
negative) and the 让负 residual (expected ≈0, an anchor-integrity check) travel
alongside so one read confirms the whole structure, not just one leg.

This file is PURE (no I/O, no cache reads) — the CLI ``s6_split_check`` feeds it
samples. Constants below are the frozen prereg values; changing them is a prereg
amendment (log it in §9) and only applies to unread data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from nutmeg.v4.model.clv_gate import CONFIRM_T, MeanTest, mean_clv_test

# ── Frozen prereg constants (docs/autumn_prereg_analysis_plan.md v1.1) ──
S6_DELTA = 0.028            # C1 correction: |h|=1 让胜 −δ / 让平 +δ, 让负 unchanged
S6_WINDOW_START = "2026-08-01"   # confirmatory window; ≤2026-07 = discovery, void
S6_LINES = (-1, 1)         # |h|=1 only — the regime the finding is about

# Outcome codes for a handicap triple.
WIN, DRAW, LOSE = 0, 1, 2


@dataclass(frozen=True)
class S6Sample:
    """One (match, integer line h) observation. ``p_*`` are the RAW DC-grid
    handicap probabilities; ``y`` is the realized outcome (WIN/DRAW/LOSE)."""

    match_date: str
    fixture_id: int
    h: int
    p_win: float
    p_draw: float
    p_lose: float
    y: int


@dataclass(frozen=True)
class S6Result:
    n: int
    n_days: int
    draw_test: MeanTest     # residual 1{让平}−P_grid(让平), H1 mean>0
    win_test: MeanTest      # residual 1{让胜}−P_grid(让胜), expected mean<0
    lose_test: MeanTest     # residual 1{让负}−P_grid(让负), expected ≈0 (anchor)
    grid_win: float         # mean grid P
    grid_draw: float
    grid_lose: float
    real_win: float         # realized frequency
    real_draw: float
    real_lose: float
    delta: float            # the frozen C1 δ actually applied in the log-loss diag
    corrected_logloss_delta: float   # ll(C1-corrected) − ll(raw); <0 ⇒ C1 helps

    @property
    def symbol_consistent(self) -> bool:
        """Finding's structure: 让平 under-stated (draw residual>0) AND 让胜
        over-stated (win residual<0). Both signs must match to deploy C1."""
        return self.draw_test.mean > 0 and self.win_test.mean < 0

    @property
    def anchor_intact(self) -> bool:
        """让负 residual must show NO real move (the 1X2 fit pins it). Fails if
        the 让负 leg is itself significant — that would mean the anchor drifted
        and the whole grid, not just the split, is off."""
        t = self.lose_test.t
        return t is None or abs(t) < CONFIRM_T

    @property
    def draw_significant(self) -> bool:
        """S6's OWN one-sided significance (standalone). The real gate is the
        S-family BHY-FDR across S1–S6 — this flag is the per-test input to it,
        not the final decision."""
        return self.draw_test.t is not None and self.draw_test.t >= CONFIRM_T


def is_pure_half(line: float) -> bool:
    """A half-line with no push: ×2 is an odd integer (…, −1.5, −0.5, 0.5, …)."""
    x = line * 2
    return abs(x - round(x)) < 1e-9 and int(round(x)) % 2 == 1


def margin_pmf(grid: np.ndarray) -> dict[int, float]:
    """Net-margin (home − away) distribution from a score grid."""
    n = grid.shape[0]
    pmf: dict[int, float] = {}
    for i in range(n):
        for j in range(n):
            pmf[i - j] = pmf.get(i - j, 0.0) + float(grid[i, j])
    return pmf


def grid_triple(pmf: dict[int, float], h: int) -> tuple[float, float, float]:
    """让胜/让平/让负 at integer home-handicap ``h``: margin > −h / == −h / < −h."""
    win = math.fsum(p for m, p in pmf.items() if m > -h)
    push = pmf.get(-h, 0.0)
    return win, push, max(1.0 - win - push, 0.0)


def settle_handicap(hg: int, ag: int, h: int) -> int:
    """(home_goals + h) vs away_goals → WIN / DRAW / LOSE."""
    diff = (hg + h) - ag
    return WIN if diff > 0 else (DRAW if diff == 0 else LOSE)


def _mean(xs: list[float]) -> float:
    return float(np.mean(xs)) if xs else 0.0


def s6_result(samples: list[S6Sample]) -> S6Result:
    """Run the S6 residual tests over |h|=1 samples. Clusters by match-day."""
    samples = [s for s in samples if abs(s.h) == 1]
    n = len(samples)
    if n == 0:
        z = MeanTest(0, 0, 0.0, None, None)
        return S6Result(0, 0, z, z, z, 0, 0, 0, 0, 0, 0, S6_DELTA, 0.0)

    days = [s.match_date for s in samples]
    draw_res = [(1.0 if s.y == DRAW else 0.0) - s.p_draw for s in samples]
    win_res = [(1.0 if s.y == WIN else 0.0) - s.p_win for s in samples]
    lose_res = [(1.0 if s.y == LOSE else 0.0) - s.p_lose for s in samples]

    # C1-corrected 3-way log-loss vs raw, as a secondary calibration diagnostic.
    def ll(win, draw, lose, y):
        return -math.log(max((win, draw, lose)[y], 1e-9))
    raw_ll = _mean([ll(s.p_win, s.p_draw, s.p_lose, s.y) for s in samples])
    cor_ll = _mean([
        ll(s.p_win - S6_DELTA, s.p_draw + S6_DELTA, s.p_lose, s.y) for s in samples
    ])

    return S6Result(
        n=n,
        n_days=len(set(days)),
        draw_test=mean_clv_test(draw_res, days),
        win_test=mean_clv_test(win_res, days),
        lose_test=mean_clv_test(lose_res, days),
        grid_win=_mean([s.p_win for s in samples]),
        grid_draw=_mean([s.p_draw for s in samples]),
        grid_lose=_mean([s.p_lose for s in samples]),
        real_win=_mean([1.0 if s.y == WIN else 0.0 for s in samples]),
        real_draw=_mean([1.0 if s.y == DRAW else 0.0 for s in samples]),
        real_lose=_mean([1.0 if s.y == LOSE else 0.0 for s in samples]),
        delta=S6_DELTA,
        corrected_logloss_delta=cor_ll - raw_ll,
    )


__all__ = [
    "S6_DELTA", "S6_WINDOW_START", "S6_LINES", "WIN", "DRAW", "LOSE",
    "S6Sample", "S6Result", "is_pure_half", "margin_pmf", "grid_triple",
    "settle_handicap", "s6_result",
]
