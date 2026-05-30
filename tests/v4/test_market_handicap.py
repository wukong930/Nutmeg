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
        target = _devig_1x2(2.43, 3.04, 3.41)
        line0 = next(ln for ln in implied_handicap_lines(*target) if ln[0] == 0)
        lh, la = fit_lambdas(*target)
        grid = score_grid(lh, la, rho=DEFAULT_RHO, max_goals=DEFAULT_MAX_GOALS)
        ph, pd_, pa = grid_to_1x2(grid)
        assert line0[1] == pytest.approx(ph, abs=1e-9)
        assert line0[2] == pytest.approx(pd_, abs=1e-9)
        assert line0[3] == pytest.approx(pa, abs=1e-9)

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
