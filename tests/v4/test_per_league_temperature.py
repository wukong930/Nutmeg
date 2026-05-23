"""Tests for nutmeg.v4.calibration.per_league.

The per-league T strategy is wired into walk_forward but disabled in
production (default --model lgb continues to use the global temperature
fit). These unit tests cover the building blocks so when production val
windows get large enough (≥800/league), enabling per-league is a config
change rather than a code change.
"""
from __future__ import annotations

import numpy as np
import pytest

from nutmeg.v4.calibration.per_league import (
    DEFAULT_MIN_SAMPLES_PER_LEAGUE,
    PerLeagueTemperatureCalibrator,
    fit_per_league_temperature,
)


def _make_synthetic(n_per_league: dict[str, int], seed: int = 42):
    """Generate a synthetic 1X2 dataset where each league has a different
    `true_T` shift applied to the raw probabilities — so per-league T should
    in principle learn distinct values."""
    rng = np.random.default_rng(seed)
    all_probs = []
    all_labels = []
    all_leagues = []
    league_true_T = {"A": 0.7, "B": 1.0, "C": 1.5}
    for league, n in n_per_league.items():
        T_true = league_true_T.get(league, 1.0)
        true_p = rng.dirichlet([2.0, 1.5, 2.0], size=n)
        labels = np.array(
            ["HDA"[i] for i in [rng.choice(3, p=p) for p in true_p]]
        )
        # Apply inverse temperature → "raw" probs (model would output these)
        logits = np.log(np.clip(true_p, 1e-9, 1))
        raw = np.exp(logits * T_true)
        raw = raw / raw.sum(axis=1, keepdims=True)
        all_probs.append(raw)
        all_labels.append(labels)
        all_leagues.append(np.array([league] * n))
    return np.vstack(all_probs), np.concatenate(all_labels), np.concatenate(all_leagues)


class TestFitPerLeagueTemperature:
    def test_returns_calibrator(self) -> None:
        probs, labels, leagues = _make_synthetic({"A": 200, "B": 200, "C": 200})
        cal = fit_per_league_temperature(probs, labels, leagues, min_samples=100)
        assert isinstance(cal, PerLeagueTemperatureCalibrator)
        assert set(cal.per_league.keys()) == {"A", "B", "C"}
        # Global calibrator always present
        assert cal.global_calibrator.T > 0

    def test_skips_leagues_below_threshold(self) -> None:
        probs, labels, leagues = _make_synthetic({"A": 200, "B": 50, "C": 30})
        cal = fit_per_league_temperature(probs, labels, leagues, min_samples=100)
        # Only A qualifies; B and C fall back to global
        assert set(cal.per_league.keys()) == {"A"}
        assert cal.fit_sample_counts == {"A": 200, "B": 50, "C": 30}

    def test_length_mismatch_raises(self) -> None:
        probs = np.array([[0.4, 0.3, 0.3]] * 10)
        labels = np.array(["H"] * 10)
        leagues = np.array(["A"] * 9)
        with pytest.raises(ValueError, match="leagues length"):
            fit_per_league_temperature(probs, labels, leagues)

    def test_uses_default_min_samples_constant(self) -> None:
        assert DEFAULT_MIN_SAMPLES_PER_LEAGUE == 800


class TestPredict:
    def test_routes_each_row_to_its_league_T(self) -> None:
        # Two well-separated true Ts → per-league cal must produce different
        # post-calibration probabilities for the same raw input across leagues
        probs, labels, leagues = _make_synthetic({"A": 300, "C": 300})
        cal = fit_per_league_temperature(probs, labels, leagues, min_samples=100)

        same_raw = np.array([[0.5, 0.3, 0.2]] * 4)
        labels_test = np.array(["A", "A", "C", "C"])
        out = cal.predict(same_raw, labels_test)
        # A's calibration ≠ C's calibration → different rows differ
        assert not np.allclose(out[0], out[2], atol=1e-3)
        # Each row sums to 1
        np.testing.assert_allclose(out.sum(axis=1), 1.0, atol=1e-6)

    def test_unknown_league_falls_back_to_global(self) -> None:
        probs, labels, leagues = _make_synthetic({"A": 200})
        cal = fit_per_league_temperature(probs, labels, leagues, min_samples=100)
        # League "Z" was never seen → predict uses global_calibrator
        out = cal.predict(np.array([[0.5, 0.3, 0.2]]), np.array(["Z"]))
        global_out = cal.global_calibrator.predict(np.array([[0.5, 0.3, 0.2]]))
        np.testing.assert_allclose(out, global_out)

    def test_length_mismatch_raises_at_predict(self) -> None:
        probs, labels, leagues = _make_synthetic({"A": 200})
        cal = fit_per_league_temperature(probs, labels, leagues, min_samples=100)
        with pytest.raises(ValueError, match="leagues length"):
            cal.predict(np.array([[0.5, 0.3, 0.2]] * 3), np.array(["A", "A"]))

    def test_summary_has_fitted_rows(self) -> None:
        probs, labels, leagues = _make_synthetic({"A": 200, "B": 50})
        cal = fit_per_league_temperature(probs, labels, leagues, min_samples=100)
        s = cal.summary()
        assert s["min_samples"] == 100
        # A qualified, B did not
        leagues_in_summary = {r["league"] for r in s["per_league_rows"]}
        assert leagues_in_summary == {"A"}


class TestCallable:
    def test_works_as_callable(self) -> None:
        probs, labels, leagues = _make_synthetic({"A": 200})
        cal = fit_per_league_temperature(probs, labels, leagues, min_samples=100)
        a = cal(np.array([[0.5, 0.3, 0.2]]), np.array(["A"]))
        b = cal.predict(np.array([[0.5, 0.3, 0.2]]), np.array(["A"]))
        np.testing.assert_allclose(a, b)
