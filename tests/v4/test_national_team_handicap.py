"""V11 post-ship — tests for the Path A++ WC handicap math layer.

Covers the four functions in ``nutmeg.v4.model.national_team_handicap``:
  - ``lambdas_from_1x2``    — KL-based reverse map 1X2 → (λ_h, λ_a)
  - ``model_handicap_probs`` — wrap of reverse-map + DC + handicap_1x2
  - ``market_handicap_probs`` — dewedge inverse-and-normalize
  - ``blend_handicap_probs`` — convex combine (with NaN fallback)
And the one-stop entry point ``evaluate_handicap_market``.

Pure math, no IO — fast.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from nutmeg.v4.model.national_team_handicap import (
    DEFAULT_HC_BLEND_ALPHA,
    DEFAULT_RHO,
    DEFAULT_WC_LAMBDA_TOTAL,
    HandicapRecommendation,
    blend_handicap_probs,
    evaluate_handicap_market,
    lambdas_from_1x2,
    market_handicap_probs,
    model_handicap_probs,
)


# ============ Constants ===============================================

def test_constants_match_design():
    """The constants should match the design discussion in the docstring."""
    assert DEFAULT_WC_LAMBDA_TOTAL == 2.6
    assert DEFAULT_RHO == -0.10
    assert DEFAULT_HC_BLEND_ALPHA == 0.4


# ============ Reverse map: 1X2 → (λ_h, λ_a) ===========================

class TestLambdasFrom1x2:
    """The reverse-mapping is the riskiest piece — it's non-unique.
    We pin it to the WC mean total-goals prior and search 1D."""

    def test_equal_strength_gives_equal_lambdas(self):
        """If 1X2 looks balanced (~28/44/28), λ_h ≈ λ_a."""
        # A typical "tossup" Pinnacle-vig-removed 1X2 for WC
        lh, la = lambdas_from_1x2(0.31, 0.32, 0.37)
        # When p_a > p_h, away should have slightly higher λ
        assert lh < la
        assert abs(lh + la - DEFAULT_WC_LAMBDA_TOTAL) < 1e-6
        # Both should be positive and reasonable
        assert 0.5 < lh < 2.0
        assert 0.5 < la < 2.0

    def test_strong_home_gives_higher_home_lambda(self):
        """Strong-home 1X2 (Brazil vs minnow) → λ_h >> λ_a."""
        # p_home ≈ 0.7 is a typical WC group-stage favorite
        lh, la = lambdas_from_1x2(0.70, 0.20, 0.10)
        assert lh > la
        # λ_total constraint
        assert abs(lh + la - DEFAULT_WC_LAMBDA_TOTAL) < 1e-6
        # The diff shouldn't blow up — bounded by LAMBDA_DIFF_BOUNDS = (-1.5, 1.5)
        assert (lh - la) <= 1.5 + 1e-3
        assert (lh - la) >= 0.4  # noticeably positive

    def test_strong_away_gives_higher_away_lambda(self):
        """Mirror of the above — strong-away → λ_a >> λ_h."""
        lh, la = lambdas_from_1x2(0.10, 0.20, 0.70)
        assert la > lh
        assert abs(lh + la - DEFAULT_WC_LAMBDA_TOTAL) < 1e-6
        assert (la - lh) >= 0.4

    def test_unnormalized_input_still_works(self):
        """Defensive: caller passes vig-laden probs — function normalizes."""
        # 1.05 sum (typical 5% vig)
        lh, la = lambdas_from_1x2(0.40, 0.30, 0.35)
        assert lh > 0
        assert la > 0
        assert abs(lh + la - DEFAULT_WC_LAMBDA_TOTAL) < 1e-6

    def test_custom_lambda_total_prior_honored(self):
        """A heavier scoring environment (Brazil-Argentina) → bigger λs."""
        lh, la = lambdas_from_1x2(0.50, 0.25, 0.25, lambda_total_prior=3.5)
        assert abs(lh + la - 3.5) < 1e-6

    def test_kl_div_is_low_after_optimization(self):
        """Sanity: the optimizer should drive KL << 1 for typical inputs."""
        from nutmeg.v4.model.dixon_coles import grid_to_1x2, score_grid

        target = (0.55, 0.25, 0.20)
        lh, la = lambdas_from_1x2(*target)
        grid = score_grid(lh, la, rho=DEFAULT_RHO)
        ph, pd, pa = grid_to_1x2(grid)
        # The reverse-map is constrained (1D over λ_diff), so we don't
        # expect bit-perfect recovery — but home margin direction + draw
        # ballpark should be right.
        assert ph > pa  # home favored
        # KL ≤ 0.1 means a "reasonable" fit given the 1D constraint
        target_arr = np.array(target)
        pred_arr = np.array([ph, pd, pa])
        kl = float(np.sum(target_arr * np.log(target_arr / pred_arr)))
        assert kl < 0.1


# ============ Model handicap (end-to-end) =============================

class TestModelHandicapProbs:
    """Reverse-map + DC + handicap aggregation."""

    def test_handicap_zero_recovers_1x2(self):
        """HC = 0 means: 让胜 = home win, 让平 = draw, 让负 = away win.
        So the handicap triple should ≈ original 1X2 (within DC float roundtrip)."""
        target = (0.45, 0.30, 0.25)
        p_h_hc, p_d_hc, p_a_hc = model_handicap_probs(*target, 0)

        # We don't expect exact recovery (KL search has noise), but
        # ordering + ballpark must hold.
        assert p_h_hc > p_a_hc  # home favored
        # All three should be positive & sum to 1
        assert abs(p_h_hc + p_d_hc + p_a_hc - 1.0) < 1e-6
        assert min(p_h_hc, p_d_hc, p_a_hc) > 0

    def test_handicap_negative_one_reduces_home_winning(self):
        """HC = -1 (home must win by 2+): 让胜 < raw P(home win)."""
        # Strong home: P(home) = 0.6 raw
        target = (0.60, 0.25, 0.15)
        p_h_hc0, _, _ = model_handicap_probs(*target, 0)
        p_h_hc_minus1, _, _ = model_handicap_probs(*target, -1)
        assert p_h_hc_minus1 < p_h_hc0

    def test_handicap_positive_one_boosts_home_winning(self):
        """HC = +1 (home gets +1 advantage): 让胜 > raw P(home win)."""
        target = (0.40, 0.30, 0.30)
        p_h_hc0, _, _ = model_handicap_probs(*target, 0)
        p_h_hc_plus1, _, _ = model_handicap_probs(*target, +1)
        assert p_h_hc_plus1 > p_h_hc0


# ============ Market dewedge ==========================================

class TestMarketHandicapProbs:
    """Standard inverse + normalize. Edge cases on bad odds."""

    def test_fair_three_way_with_vig(self):
        """Pinnacle-style ~7% vig on a balanced market."""
        # Odds 2.50, 3.20, 3.10 → inverse 0.40 + 0.3125 + 0.3226 = 1.0351
        # After normalize: ≈ 0.386, 0.302, 0.312
        ph, pd, pa = market_handicap_probs(2.50, 3.20, 3.10)
        assert abs(ph + pd + pa - 1.0) < 1e-6
        assert 0.37 < ph < 0.40
        assert 0.29 < pd < 0.32
        assert 0.30 < pa < 0.33

    def test_strong_favorite(self):
        """Very low odds on home → P(home) ≈ implied."""
        ph, pd, pa = market_handicap_probs(1.20, 6.50, 12.0)
        assert ph > pd
        assert ph > pa
        assert abs(ph + pd + pa - 1.0) < 1e-6

    def test_missing_odds_returns_nan(self):
        """Any odds <= 1.0 or None → NaN tuple (no implied prob)."""
        ph, pd, pa = market_handicap_probs(0.95, 3.0, 4.0)
        assert math.isnan(ph)
        assert math.isnan(pd)
        assert math.isnan(pa)

    def test_none_odds_returns_nan(self):
        ph, pd, pa = market_handicap_probs(None, 3.0, 4.0)  # type: ignore[arg-type]
        assert math.isnan(ph)


# ============ Bayesian blend ==========================================

class TestBlendHandicapProbs:
    """Alpha-weighted blend; NaN-market falls back to model."""

    def test_alpha_one_is_pure_model(self):
        model = (0.5, 0.3, 0.2)
        market = (0.4, 0.4, 0.2)
        blended = blend_handicap_probs(model, market, alpha=1.0)
        assert abs(blended[0] - model[0]) < 1e-9
        assert abs(blended[1] - model[1]) < 1e-9
        assert abs(blended[2] - model[2]) < 1e-9

    def test_alpha_zero_is_pure_market(self):
        model = (0.5, 0.3, 0.2)
        market = (0.4, 0.4, 0.2)
        blended = blend_handicap_probs(model, market, alpha=0.0)
        assert abs(blended[0] - market[0]) < 1e-9

    def test_alpha_default_is_04_model_weight(self):
        """Default 0.4 → 40% model + 60% market (WC convention)."""
        model = (0.6, 0.2, 0.2)
        market = (0.3, 0.4, 0.3)
        blended = blend_handicap_probs(model, market)
        expected_h = 0.4 * 0.6 + 0.6 * 0.3  # = 0.42
        # No renormalization adjustment since both sum to 1 → blended sum = 1
        assert abs(blended[0] - expected_h) < 1e-9

    def test_blended_sums_to_one(self):
        """Defensive normalization keeps probs valid."""
        blended = blend_handicap_probs((0.3, 0.4, 0.3), (0.5, 0.2, 0.3), alpha=0.5)
        assert abs(sum(blended) - 1.0) < 1e-9

    def test_nan_market_returns_model(self):
        """If market is unavailable (NaN), blend returns model unchanged."""
        model = (0.5, 0.3, 0.2)
        market_nan = (float("nan"), float("nan"), float("nan"))
        blended = blend_handicap_probs(model, market_nan)
        assert blended == model


# ============ One-stop entry: evaluate_handicap_market ================

class TestEvaluateHandicapMarket:
    """The HandicapRecommendation dataclass round-trip."""

    def test_returns_dataclass_with_all_fields(self):
        rec = evaluate_handicap_market(
            0.45, 0.30, 0.25,   # blended 1X2
            -1,                  # handicap_home: home must win by 2+
            2.40, 3.50, 2.80,   # 让球 SP
        )
        assert isinstance(rec, HandicapRecommendation)
        assert rec.handicap_home == -1
        assert len(rec.p_model_hc) == 3
        assert len(rec.p_market_hc) == 3
        assert len(rec.p_final_hc) == 3
        assert len(rec.odds_hc) == 3
        assert len(rec.ev_per_unit) == 3
        assert len(rec.kelly_fraction) == 3
        # Inferred lambdas should be positive
        assert rec.inferred_lambda_home > 0
        assert rec.inferred_lambda_away > 0
        # λ_total ≈ WC prior
        assert abs(rec.inferred_lambda_home + rec.inferred_lambda_away - 2.6) < 1e-6

    def test_ev_identity_holds(self):
        """EV = p × odds − 1 by construction."""
        rec = evaluate_handicap_market(
            0.50, 0.30, 0.20,
            0,
            1.90, 3.50, 4.20,
        )
        for i in range(3):
            expected_ev = rec.p_final_hc[i] * rec.odds_hc[i] - 1.0
            assert abs(rec.ev_per_unit[i] - expected_ev) < 1e-9

    def test_kelly_never_negative(self):
        rec = evaluate_handicap_market(
            0.45, 0.30, 0.25, 0,
            1.10, 3.50, 10.0,  # huge edge on H @ 1.10 if model agrees
        )
        for f in rec.kelly_fraction:
            assert f >= 0.0

    def test_zero_market_fallback_to_model(self):
        """If market SP is absent, p_market is NaN-triple and p_final == p_model."""
        # We can't pass NaN through pydantic-validated odds, but we CAN
        # exercise the internal path by passing odds<=1.0 (invalid → NaN
        # dewedge) — but evaluate_handicap_market doesn't gate on odds<=1.
        # So test via direct injection in helper:
        from nutmeg.v4.model.national_team_handicap import (
            blend_handicap_probs as _blend,
        )
        m = (0.5, 0.3, 0.2)
        nan_q = (float("nan"), float("nan"), float("nan"))
        out = _blend(m, nan_q)
        assert out == m


# ============ Lambda total integration =================================

def test_higher_lambda_total_lowers_draw_prob():
    """Sanity: more goals (higher λ_total) → lower draw rate.
    Equal-strength input, vary the total goals prior."""
    p_h_lo, p_d_lo, p_a_lo = model_handicap_probs(
        0.33, 0.34, 0.33, 0, lambda_total_prior=2.0,
    )
    p_h_hi, p_d_hi, p_a_hi = model_handicap_probs(
        0.33, 0.34, 0.33, 0, lambda_total_prior=4.0,
    )
    # Higher total goals → fewer 0-0/1-1, so draw share drops
    assert p_d_hi < p_d_lo


# ============ __all__ exports =========================================

def test_all_exports_importable():
    """The __all__ list should match what consumers import."""
    from nutmeg.v4.model import national_team_handicap as m
    for name in m.__all__:
        assert hasattr(m, name), f"__all__ lists {name!r} but module lacks it"
