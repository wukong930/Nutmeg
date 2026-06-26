"""B2 — variance-adjusted EV threshold: threshold(P) = base + z·σ_P·lf·SP."""
from __future__ import annotations

import pytest

from nutmeg.v4.model.ev_threshold import BASE_THRESHOLD
from nutmeg.v4.model.ev_threshold import variance_adjusted_threshold as vt


def test_sweet_small_haircut():
    # P=0.4 → SP=2.5 → 0.05 + 1·0.012·1·2.5 = 0.08
    assert vt(0.40) == pytest.approx(0.08)


def test_deep_longshot_big_haircut():
    # P=0.08 → SP=12.5 → 0.05 + 0.012·12.5 = 0.20
    assert vt(0.08) == pytest.approx(0.20)


def test_monotone_rises_for_longshots():
    assert vt(0.08) > vt(0.40) > vt(0.80) > BASE_THRESHOLD


def test_non_probability_falls_back_to_flat_base():
    for bad in (0.0, 1.0, -0.1, 1.2):
        assert vt(bad) == BASE_THRESHOLD


def test_explicit_sp_overrides_fair_odds():
    # sp given → use it, not 1/p. P=0.5 but 竞彩 SP=3.0 → 0.05 + 0.012·3.0
    assert vt(0.50, sp=3.0) == pytest.approx(0.05 + 0.012 * 3.0)
    # default (sp=None) uses 1/p = 2.0
    assert vt(0.50) == pytest.approx(0.05 + 0.012 * 2.0)


def test_league_factor_and_z_scale_the_haircut():
    base_hair = vt(0.08) - BASE_THRESHOLD
    assert vt(0.08, league_factor=1.39) - BASE_THRESHOLD == pytest.approx(base_hair * 1.39)
    assert vt(0.08, z=1.65) - BASE_THRESHOLD == pytest.approx(base_hair * 1.65)


def test_zero_sigma_recovers_flat_bar():
    # σ_P=0 (no estimation error) → the flat base at every P
    for p in (0.05, 0.4, 0.9):
        assert vt(p, sigma_p=0.0) == BASE_THRESHOLD
