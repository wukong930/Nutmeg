"""V12 W8 — tests for market-implied 让球 (nutmeg.v4.model.market_handicap).

The module reverse-fits a Dixon-Coles goal grid to the de-vig Pinnacle 1X2
(+ over/under), then reads off integer handicap lines. These tests pin the
invariants that make it trustworthy: it reproduces its market anchors, every
line is a valid probability simplex, and the goal total responds to the O/U.
"""
from __future__ import annotations

import pytest

from nutmeg.v4.model.dixon_coles import (
    grid_to_1x2,
    grid_to_over_under,
    score_grid,
)
from nutmeg.v4.model.market_handicap import (
    DEFAULT_MAX_GOALS,
    DEFAULT_RHO,
    asian_total_over_prob,
    devig_over,
    fit_lambdas,
    implied_handicap_lines,
)


def _devig_1x2(h, d, a):
    inv = [1.0 / h, 1.0 / d, 1.0 / a]
    s = sum(inv)
    return [x / s for x in inv]


class TestDevigOver:
    def test_even_money(self):
        assert devig_over(2.0, 2.0) == pytest.approx(0.5)

    def test_over_favored(self):
        # 1/1.5 / (1/1.5 + 1/2.5) = 0.625
        assert devig_over(1.5, 2.5) == pytest.approx(0.625, abs=1e-6)

    @pytest.mark.parametrize("o,u", [(None, 1.9), (1.9, None), (None, None)])
    def test_missing_returns_none(self, o, u):
        assert devig_over(o, u) is None

    @pytest.mark.parametrize("o,u", [(1.0, 2.0), (0.0, 2.0), (2.0, 1.0), ("x", 2.0)])
    def test_invalid_returns_none(self, o, u):
        assert devig_over(o, u) is None


class TestFitLambdas:
    def test_reproduces_1x2(self):
        target = _devig_1x2(2.50, 3.20, 3.10)
        lh, la = fit_lambdas(*target)
        grid = score_grid(lh, la, rho=DEFAULT_RHO, max_goals=DEFAULT_MAX_GOALS)
        ph, pd_, pa = grid_to_1x2(grid)
        assert ph == pytest.approx(target[0], abs=0.01)
        assert pd_ == pytest.approx(target[1], abs=0.01)
        assert pa == pytest.approx(target[2], abs=0.01)

    def test_reproduces_over_with_anchor(self):
        target = _devig_1x2(2.43, 3.04, 3.41)
        p_over = devig_over(1.95, 1.95)  # 0.5
        lh, la = fit_lambdas(*target, p_over)
        grid = score_grid(lh, la, rho=DEFAULT_RHO, max_goals=DEFAULT_MAX_GOALS)
        over, _ = grid_to_over_under(grid, 2.5)
        assert over == pytest.approx(0.5, abs=0.03)

    def test_higher_over_means_higher_total(self):
        target = _devig_1x2(2.43, 3.04, 3.41)
        lo = sum(fit_lambdas(*target, devig_over(2.4, 1.6)))  # under favoured
        hi = sum(fit_lambdas(*target, devig_over(1.6, 2.4)))  # over favoured
        assert hi > lo

    def test_positive_lambdas_extreme_favorite(self):
        lh, la = fit_lambdas(*_devig_1x2(1.20, 6.5, 13.0))
        assert lh > 0 and la > 0
        assert lh > la  # heavy home favourite scores more

    def test_zero_sum_raises(self):
        with pytest.raises(ValueError):
            fit_lambdas(0.0, 0.0, 0.0)


class TestImpliedHandicapLines:
    def test_seven_lines_valid_simplex(self):
        lines = implied_handicap_lines(*_devig_1x2(2.43, 3.04, 3.41))
        assert [ln[0] for ln in lines] == list(range(-3, 4))
        for _, ph, pd_, pa in lines:
            assert ph + pd_ + pa == pytest.approx(1.0, abs=1e-6)
            assert all(0.0 <= x <= 1.0 for x in (ph, pd_, pa))

    def test_line_zero_equals_1x2(self):
        # 1X2-ONLY fit path (no p_over): line 0 reproduces the fitted grid's 1X2
        # exactly. NOTE: production always passes p_over — that path is covered
        # (and bounded) by test_line_zero_vs_1x2_with_ou_anchor_bounded below.
        target = _devig_1x2(2.43, 3.04, 3.41)
        line0 = next(ln for ln in implied_handicap_lines(*target) if ln[0] == 0)
        lh, la = fit_lambdas(*target)
        grid = score_grid(lh, la, rho=DEFAULT_RHO, max_goals=DEFAULT_MAX_GOALS)
        ph, pd_, pa = grid_to_1x2(grid)
        assert line0[1] == pytest.approx(ph, abs=1e-9)
        assert line0[2] == pytest.approx(pd_, abs=1e-9)
        assert line0[3] == pytest.approx(pa, abs=1e-9)

    def test_line_zero_vs_1x2_with_ou_anchor_bounded(self):
        """F2 — the PRODUCTION path passes a de-vig O/U, so the weighted
        (1X2 + O/U) fit trades a little 1X2 fidelity. The dashboard shows the
        exact de-vig 1X2 on the 胜平负 row AND this line-0 让球 on the same card,
        so the gap must stay SMALL and BOUNDED (it can't silently grow):

          - 让胜/让负 (the legs actually bet): within 2.5pp of the 1X2 de-vig.
          - 让平 (most λ_total-sensitive, rarely the bet leg): within 4.5pp.

        The old test only exercised the 1X2-only branch (p_over=None), which is
        exact — so it passed while never guarding the path users actually hit.
        """
        for (h, d, a), (over, under) in [
            ((2.05, 3.40, 3.70), (1.95, 1.95)),   # balanced total
            ((2.30, 3.10, 3.30), (2.95, 1.40)),   # low total (biggest draw pull)
            ((1.55, 4.10, 6.20), (1.50, 2.65)),   # high total, heavy favourite
        ]:
            t1x2 = _devig_1x2(h, d, a)
            p_over = devig_over(over, under)
            line0 = next(
                ln for ln in implied_handicap_lines(*t1x2, p_over, ou_line=2.5)
                if ln[0] == 0
            )
            assert line0[1] + line0[2] + line0[3] == pytest.approx(1.0, abs=1e-6)
            assert line0[1] == pytest.approx(t1x2[0], abs=0.025)  # 让胜 (bet leg)
            assert line0[3] == pytest.approx(t1x2[2], abs=0.025)  # 让负 (bet leg)
            assert line0[2] == pytest.approx(t1x2[1], abs=0.045)  # 让平 (sensitive)

    def test_home_cover_monotonic_in_line(self):
        # More head start for home (more positive line) ⇒ non-decreasing P(home covers).
        hc = {ln[0]: ln[1] for ln in implied_handicap_lines(*_devig_1x2(2.43, 3.04, 3.41))}
        assert hc[-3] <= hc[-2] <= hc[-1] <= hc[0] <= hc[1] <= hc[2] <= hc[3]

    def test_favorite_handicap_regression(self):
        # 神户 vs 鹿岛 (new line 2.43/3.04/3.41), 1X2-only fit. Pins the
        # interactively-validated ~18% 让胜 at the −1 line (home wins by ≥2).
        lines = {ln[0]: ln[1:] for ln in implied_handicap_lines(*_devig_1x2(2.430, 3.040, 3.410))}
        p_home_cover_m1 = lines[-1][0]
        assert p_home_cover_m1 == pytest.approx(0.178, abs=0.02)

    def test_ou_anchor_shifts_favorite_let_prob(self):
        # Double-anchor (1X2 + high O/U) raises 让胜 at −1 vs 1X2-only.
        target = _devig_1x2(2.430, 3.040, 3.410)
        base = {ln[0]: ln[1] for ln in implied_handicap_lines(*target)}
        hi_total = {
            ln[0]: ln[1]
            for ln in implied_handicap_lines(*target, devig_over(1.6, 2.4))
        }
        assert hi_total[-1] > base[-1]


class TestAsianTotalOverProb:
    """V12 W8b — push/quarter-aware Asian total. The serving path historically
    hard-coded a 2.5 line; Pinnacle's main J1 total is often 2.25."""

    GRIDS = [
        score_grid(lh, la, rho=DEFAULT_RHO, max_goals=DEFAULT_MAX_GOALS)
        for lh, la in [(1.2, 1.1), (1.8, 0.7), (0.9, 1.5), (1.35, 1.27)]
    ]
    LINES = [1.5, 2.0, 2.25, 2.5, 2.75, 3.0]

    def _under(self, grid, line):
        # symmetric: win=under, push=half
        import math
        tot: dict[int, float] = {}
        n = grid.shape[0]
        for i in range(n):
            for j in range(n):
                tot[i + j] = tot.get(i + j, 0.0) + float(grid[i, j])

        def single(ell):
            return sum(p * (1.0 if k < ell else 0.5 if k == ell else 0.0)
                       for k, p in tot.items())
        frac = line - math.floor(line)
        if abs(frac - 0.25) < 1e-9 or abs(frac - 0.75) < 1e-9:
            return 0.5 * single(line - 0.25) + 0.5 * single(line + 0.25)
        return single(line)

    def test_over_plus_under_is_one(self):
        """Push-as-half convention ⇒ over + under == 1 at EVERY line."""
        for g in self.GRIDS:
            for line in self.LINES:
                assert (
                    asian_total_over_prob(g, line) + self._under(g, line)
                    == pytest.approx(1.0, abs=1e-12)
                )

    def test_half_line_matches_grid_to_over_under(self):
        """Back-compat: at 2.5 (and any half line) identical to the old
        threshold function — the default serving path is unchanged."""
        for g in self.GRIDS:
            for line in (1.5, 2.5, 3.5):
                assert asian_total_over_prob(g, line) == pytest.approx(
                    grid_to_over_under(g, line=line)[0], abs=1e-12
                )

    def test_quarter_line_is_mean_of_neighbours(self):
        """2.25 = ½·(2.0 line) + ½·(2.5 line)."""
        for g in self.GRIDS:
            mid = 0.5 * (asian_total_over_prob(g, 2.0)
                         + asian_total_over_prob(g, 2.5))
            assert asian_total_over_prob(g, 2.25) == pytest.approx(mid, abs=1e-12)

    def test_whole_line_adds_half_push(self):
        """At a whole line the total==line mass is a push (half), so the over
        prob sits strictly above the bare P(total > line)."""
        for g in self.GRIDS:
            bare = grid_to_over_under(g, line=2.0)[0]  # strict total > 2
            assert asian_total_over_prob(g, 2.0) >= bare  # adds 0.5·P(==2)

    def test_monotonic_decreasing_in_line(self):
        for g in self.GRIDS:
            vals = [asian_total_over_prob(g, x) for x in self.LINES]
            assert all(a >= b - 1e-12 for a, b in zip(vals, vals[1:], strict=False))


class TestQuarterLineHandicap:
    """The ou_line argument must actually change the fitted handicap — and the
    2.25 fix must lower λ_total vs the (biased) 2.5 assumption."""

    def test_2_25_differs_from_2_5(self):
        th = _devig_1x2(2.91, 3.27, 2.6)          # 清水 (updated line)
        p_over = devig_over(1.909, 1.980)         # main total = 2.25
        at_225 = {ln[0]: ln[1] for ln in
                  implied_handicap_lines(*th, p_over, ou_line=2.25)}
        at_250 = {ln[0]: ln[1] for ln in
                  implied_handicap_lines(*th, p_over, ou_line=2.5)}
        # Treating 2.25 as 2.5 inflates λ_total → over-states 主队让胜 at −1.
        assert at_250[-1] > at_225[-1]
        # The validated 2.25 number (interactively reproduced).
        assert at_225[-1] == pytest.approx(0.143, abs=0.01)

    def test_2_25_lowers_lambda_total(self):
        th = _devig_1x2(2.91, 3.27, 2.6)
        p_over = devig_over(1.909, 1.980)
        lh25, la25 = fit_lambdas(*th, p_over, ou_line=2.5)
        lh225, la225 = fit_lambdas(*th, p_over, ou_line=2.25)
        assert (lh225 + la225) < (lh25 + la25)
