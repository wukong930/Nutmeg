"""Tests for nutmeg.v4.model.dixon_coles — pure score-grid math."""
import numpy as np
import pytest

from nutmeg.v4.model.dixon_coles import (
    dc_tau,
    grid_to_1x2,
    grid_to_handicap_1x2,
    grid_to_over_under,
    lambdas_to_1x2_array,
    score_grid,
)


class TestScoreGrid:
    def test_grid_shape(self):
        g = score_grid(1.3, 1.1)
        assert g.shape == (9, 9)

    def test_grid_sums_to_one(self):
        for lh, la in [(1.0, 1.0), (2.5, 0.5), (0.3, 0.3), (3.0, 2.5)]:
            g = score_grid(lh, la)
            assert g.sum() == pytest.approx(1.0, abs=1e-9)

    def test_grid_with_rho_sums_to_one(self):
        for rho in [-0.15, -0.05, 0.0, 0.05, 0.1]:
            g = score_grid(1.5, 1.2, rho=rho)
            assert g.sum() == pytest.approx(1.0, abs=1e-9)

    def test_grid_nonnegative(self):
        g = score_grid(1.8, 1.4, rho=-0.1)
        assert (g >= 0).all()

    def test_lambdas_must_be_positive(self):
        with pytest.raises(ValueError):
            score_grid(0.0, 1.0)
        with pytest.raises(ValueError):
            score_grid(1.0, -0.5)


class TestGridTo1x2:
    def test_probs_sum_to_one(self):
        g = score_grid(1.4, 1.1, rho=-0.05)
        h, d, a = grid_to_1x2(g)
        assert h + d + a == pytest.approx(1.0, abs=1e-9)

    def test_symmetric_lambdas_give_higher_draw_than_extreme(self):
        # When teams are equal, draw should be reasonable
        g_eq = score_grid(1.3, 1.3)
        h_eq, d_eq, a_eq = grid_to_1x2(g_eq)
        # Home == away by symmetry
        assert h_eq == pytest.approx(a_eq, abs=1e-9)

    def test_strong_home_wins_more(self):
        g_strong_home = score_grid(2.5, 0.7)
        g_strong_away = score_grid(0.7, 2.5)
        h1, _, _ = grid_to_1x2(g_strong_home)
        _, _, a2 = grid_to_1x2(g_strong_away)
        assert h1 > 0.5
        assert a2 > 0.5
        # Symmetric: strong-home P(H) ~= strong-away P(A)
        assert h1 == pytest.approx(a2, abs=1e-9)


class TestHandicap1x2:
    def test_zero_handicap_equals_1x2(self):
        g = score_grid(1.5, 1.2)
        h, d, a = grid_to_1x2(g)
        h2, d2, a2 = grid_to_handicap_1x2(g, handicap_home=0)
        assert h2 == pytest.approx(h, abs=1e-9)
        assert d2 == pytest.approx(d, abs=1e-9)
        assert a2 == pytest.approx(a, abs=1e-9)

    def test_handicap_minus_one_shifts_toward_away(self):
        # home gives 1 goal means away gets +1 advantage when settling
        g = score_grid(1.5, 1.2)
        h0, _, a0 = grid_to_1x2(g)
        h_neg, _, a_neg = grid_to_handicap_1x2(g, handicap_home=-1)
        assert h_neg < h0
        assert a_neg > a0

    def test_handicap_sums_to_one(self):
        g = score_grid(1.3, 1.4, rho=-0.08)
        for k in (-2, -1, 0, 1, 2):
            h, d, a = grid_to_handicap_1x2(g, handicap_home=k)
            assert h + d + a == pytest.approx(1.0, abs=1e-9)


class TestOverUnder:
    def test_sums_to_one(self):
        g = score_grid(1.6, 1.3)
        for line in (0.5, 1.5, 2.5, 3.5, 4.5):
            o, u = grid_to_over_under(g, line=line)
            assert o + u == pytest.approx(1.0, abs=1e-9)

    def test_higher_lambdas_more_overs(self):
        g_low = score_grid(0.7, 0.7)
        g_high = score_grid(2.5, 2.5)
        o_low, _ = grid_to_over_under(g_low, line=2.5)
        o_high, _ = grid_to_over_under(g_high, line=2.5)
        assert o_high > o_low


class TestDCTau:
    def test_tau_one_for_non_low_scores(self):
        assert dc_tau(2, 3, 1.5, 1.2, -0.05) == 1.0
        assert dc_tau(0, 2, 1.5, 1.2, -0.05) == 1.0
        assert dc_tau(3, 0, 1.5, 1.2, -0.05) == 1.0

    def test_tau_low_score_with_negative_rho(self):
        # negative rho (typical empirical) should boost 0-0 and 1-1
        rho = -0.1
        assert dc_tau(0, 0, 1.5, 1.2, rho) > 1.0
        assert dc_tau(1, 1, 1.5, 1.2, rho) > 1.0
        # and suppress 0-1, 1-0
        assert dc_tau(0, 1, 1.5, 1.2, rho) < 1.0
        assert dc_tau(1, 0, 1.5, 1.2, rho) < 1.0

    def test_tau_nonnegative(self):
        for rho in (-0.3, -0.1, 0.0, 0.1, 0.3):
            for i in range(2):
                for j in range(2):
                    assert dc_tau(i, j, 1.5, 1.2, rho) >= 0.0


class TestLambdasTo1X2Array:
    def test_shape(self):
        lambdas = np.array([[1.2, 1.0], [2.0, 0.8], [1.5, 1.5]])
        probs = lambdas_to_1x2_array(lambdas)
        assert probs.shape == (3, 3)

    def test_rows_sum_to_one(self):
        lambdas = np.array([[1.2, 1.0], [2.0, 0.8], [0.6, 1.4]])
        probs = lambdas_to_1x2_array(lambdas, rho=-0.05)
        assert probs.sum(axis=1) == pytest.approx(np.ones(3), abs=1e-9)
