"""V10 W1 Track B Day 3 — tests for national_team_predict module."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.model.national_team_predict import (
    NationalTeamModel,
    bayesian_blend,
    elo_predict_frame,
    elo_to_1x2_probs,
    hit_rate_1x2,
    log_loss_1x2,
    market_implied_probs,
    outcomes_from_goals,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data" / "external"
_HAS_WC_DATA = (DATA / "cup_history" / "WC_2022.parquet").exists() and any(
    (DATA / "eloratings").glob("eloratings_*.parquet")
) if (DATA / "eloratings").exists() else False


class TestEloToOneXTwoProbs:
    """Closed-form Elo → 1X2."""

    def test_equal_elos_yield_near_one_third(self):
        p_h, p_d, p_a = elo_to_1x2_probs(1900, 1900)
        # Equal Elo → home/away should be near (1-draw)/2 each
        assert abs(p_h - p_a) < 1e-6
        assert p_d > 0.20  # tournament base draw
        assert abs(p_h + p_d + p_a - 1.0) < 1e-9

    def test_strong_home_skews_home_probability(self):
        # Spain (2165) vs Qatar (1425)
        p_h, p_d, p_a = elo_to_1x2_probs(2165, 1425)
        assert p_h > 0.85
        assert p_a < 0.05
        # Draw rate falls off for big gaps
        assert p_d < 0.10

    def test_home_advantage_shifts_probability(self):
        baseline = elo_to_1x2_probs(1800, 1800, home_adv=0)
        with_adv = elo_to_1x2_probs(1800, 1800, home_adv=50)
        # 50-point Elo home advantage should bump home prob
        assert with_adv[0] > baseline[0]
        assert with_adv[2] < baseline[2]

    def test_normalized_to_one(self):
        # Sanity across a range
        for h_elo, a_elo in [(1500, 2000), (2000, 2000), (2200, 1300)]:
            probs = elo_to_1x2_probs(h_elo, a_elo)
            assert abs(sum(probs) - 1.0) < 1e-9


class TestEloPredictFrame:
    def test_missing_elo_defaults_to_uniform(self):
        df = pd.DataFrame([
            {"home_team": "A", "away_team": "B", "home_elo": None, "away_elo": 1500},
            {"home_team": "C", "away_team": "D", "home_elo": 1800, "away_elo": 1800},
        ])
        probs = elo_predict_frame(df)
        assert probs.shape == (2, 3)
        # Row 0 — missing elo → uniform
        np.testing.assert_allclose(probs[0], [1/3, 1/3, 1/3])
        # Row 1 — equal Elos
        assert probs[1].sum() == pytest.approx(1.0)


class TestMarketImpliedProbs:
    def test_basic_normalization(self):
        ph = pd.Series([2.0])
        pd_ = pd.Series([3.0])
        pa = pd.Series([6.0])
        probs = market_implied_probs(ph, pd_, pa)
        # 1/2 + 1/3 + 1/6 = 1.0 (no vig); should yield [0.5, 0.333, 0.167]
        np.testing.assert_allclose(probs[0], [0.5, 1/3, 1/6], atol=1e-6)
        assert probs[0].sum() == pytest.approx(1.0)

    def test_nan_passes_through(self):
        probs = market_implied_probs(
            pd.Series([2.0, np.nan]),
            pd.Series([3.0, 3.0]),
            pd.Series([3.0, 3.0]),
        )
        assert not np.isnan(probs[0]).any()
        assert np.isnan(probs[1]).all()


class TestOutcomesFromGoals:
    def test_basic_outcomes(self):
        out = outcomes_from_goals(
            pd.Series([2, 1, 1, np.nan]),
            pd.Series([1, 1, 2, 0]),
        )
        np.testing.assert_array_equal(out, [0, 1, 2, -1])  # H, D, A, unplayed


class TestLogLossAndHitRate:
    def test_log_loss_skips_unplayed(self):
        probs = np.array([[0.5, 0.3, 0.2], [0.3, 0.4, 0.3]])
        outcomes = np.array([0, -1])  # 1st: H (matches), 2nd: unplayed (skip)
        ll = log_loss_1x2(probs, outcomes)
        # Only 1 row → log(0.5) = 0.693
        assert ll == pytest.approx(-np.log(0.5), abs=1e-6)

    def test_hit_rate_basic(self):
        probs = np.array([[0.6, 0.2, 0.2], [0.1, 0.7, 0.2], [0.2, 0.3, 0.5]])
        outcomes = np.array([0, 1, 0])  # 2/3 correct
        assert hit_rate_1x2(probs, outcomes) == pytest.approx(2.0 / 3.0)


class TestBayesianBlend:
    def test_alpha_one_returns_model(self):
        m = np.array([[0.5, 0.3, 0.2]])
        k = np.array([[0.1, 0.1, 0.8]])
        out = bayesian_blend(m, k, alpha=1.0)
        np.testing.assert_allclose(out, m)

    def test_alpha_zero_returns_market(self):
        m = np.array([[0.5, 0.3, 0.2]])
        k = np.array([[0.1, 0.1, 0.8]])
        out = bayesian_blend(m, k, alpha=0.0)
        np.testing.assert_allclose(out, k)

    def test_market_nan_falls_back_to_model(self):
        m = np.array([[0.5, 0.3, 0.2]])
        k = np.array([[np.nan, np.nan, np.nan]])
        out = bayesian_blend(m, k, alpha=0.5)
        np.testing.assert_allclose(out, m)


class TestNationalTeamModelUnit:
    """Doesn't require local WC data — uses synthetic features."""

    def test_predict_without_fit_falls_back_to_elo(self):
        df = pd.DataFrame([
            {"home_team": "Spain", "away_team": "Qatar",
             "home_elo": 2165, "away_elo": 1425},
        ])
        model = NationalTeamModel()
        probs = model.predict_proba(df)
        # Should match closed-form Elo
        expected = elo_to_1x2_probs(2165, 1425)
        np.testing.assert_allclose(probs[0], expected, atol=1e-6)

    def test_fit_then_predict_returns_valid_probs(self):
        # Synthetic training set, 20 rows
        rng = np.random.default_rng(42)
        n = 30
        df = pd.DataFrame({
            "home_team": [f"H{i}" for i in range(n)],
            "away_team": [f"A{i}" for i in range(n)],
            "home_elo": rng.normal(1800, 150, n),
            "away_elo": rng.normal(1800, 150, n),
            "psc_home": [None] * n,
            "psc_draw": [None] * n,
            "psc_away": [None] * n,
        })
        y = rng.integers(0, 3, n)
        model = NationalTeamModel()
        model.fit(df, y)
        probs = model.predict_proba(df)
        assert probs.shape == (n, 3)
        # All probs in [0, 1] and rows sum ≈ 1
        assert (probs >= 0).all() and (probs <= 1).all()
        np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-5)


@pytest.mark.skipif(
    not _HAS_WC_DATA,
    reason="WC 2022 fixtures/odds + eloratings snapshot required",
)
class TestWalkForwardOnWC:
    """Integration: actual 2018→2022 walk-forward must meet the ship gate."""

    def test_blend_meets_ship_gate(self):
        from nutmeg.v4.data.wc_training_frame import build_wc_training_frame

        df_train = build_wc_training_frame(2018)
        df_test = build_wc_training_frame(2022)
        y_train = outcomes_from_goals(df_train["home_goals"], df_train["away_goals"])
        y_test = outcomes_from_goals(df_test["home_goals"], df_test["away_goals"])

        mask_t = (df_train["home_elo"].notna()
                  & df_train["away_elo"].notna()
                  & (y_train >= 0))
        df_train_ok = df_train[mask_t].reset_index(drop=True)
        y_train_ok = y_train[mask_t]

        mask_v = (df_test["home_elo"].notna()
                  & df_test["away_elo"].notna()
                  & (y_test >= 0))
        df_test_ok = df_test[mask_v].reset_index(drop=True)
        y_test_ok = y_test[mask_v]

        model = NationalTeamModel()
        model.fit(df_train_ok, y_train_ok, host_country="Russia", host_advantage=50.0)

        lgb_probs = model.predict_proba(df_test_ok, host_country="Qatar", host_advantage=50.0)
        pin_probs = market_implied_probs(
            df_test_ok["psc_home"], df_test_ok["psc_draw"], df_test_ok["psc_away"]
        )

        # Best alpha per Day 3 walk-forward: α=0.4
        blend = bayesian_blend(lgb_probs, pin_probs, alpha=0.4)
        ll = log_loss_1x2(blend, y_test_ok)
        SHIP_GATE = 1.00
        assert ll <= SHIP_GATE, (
            f"WC walk-forward log-loss {ll:.4f} exceeds ship gate {SHIP_GATE}; "
            f"investigate before shipping WC predictions."
        )
