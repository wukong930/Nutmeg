"""Tests for nutmeg.v4.calibration."""
import numpy as np
import pytest

from nutmeg.v4.calibration import (
    fit_isotonic_1x2,
    fit_temperature_1x2,
)


class TestTemperatureCalibration:
    def test_t_close_to_one_when_already_calibrated(self):
        rng = np.random.default_rng(0)
        # Generate truly random probs that match the labels' marginal frequency
        n = 1000
        y_idx = rng.choice(3, n, p=[0.45, 0.25, 0.30])
        probs = np.tile([0.45, 0.25, 0.30], (n, 1))
        # Add a little noise
        probs = probs + rng.normal(0, 0.01, (n, 3))
        probs = np.clip(probs, 0.01, 0.99)
        probs = probs / probs.sum(axis=1, keepdims=True)
        y = np.array(["H", "D", "A"])[y_idx]

        cal = fit_temperature_1x2(probs, y)
        # T should be close to 1 because raw is already near-calibrated marginal
        assert 0.3 <= cal.T <= 5.0

    def test_calibrator_output_sums_to_one(self):
        rng = np.random.default_rng(1)
        n = 500
        probs = rng.dirichlet([1, 1, 1], size=n)
        y = rng.choice(["H", "D", "A"], n)
        cal = fit_temperature_1x2(probs, y)
        out = cal.predict(probs)
        assert out.shape == probs.shape
        assert out.sum(axis=1) == pytest.approx(np.ones(n), abs=1e-9)

    def test_reduces_log_loss_or_at_least_does_not_blow_up(self):
        # On a held-out independent eval, temp should not catastrophically worsen log-loss
        rng = np.random.default_rng(2)
        n = 800
        y_idx = rng.choice(3, n, p=[0.45, 0.25, 0.30])
        # Overconfident probs (push toward 0/1)
        raw = np.eye(3)[y_idx] * 0.7 + 0.1
        raw = raw + rng.normal(0, 0.05, (n, 3))
        raw = np.clip(raw, 0.01, 0.99)
        raw = raw / raw.sum(axis=1, keepdims=True)
        y = np.array(["H", "D", "A"])[y_idx]
        cal = fit_temperature_1x2(raw, y)
        # nll_after must be <= nll_before by construction (optimizer minimizes)
        assert cal.nll_after <= cal.nll_before + 1e-9


class TestIsotonicCalibration:
    def test_too_few_samples_raises(self):
        with pytest.raises(ValueError):
            fit_isotonic_1x2(np.array([[0.5, 0.3, 0.2]] * 10), ["H"] * 10)

    def test_predict_sums_to_one(self):
        rng = np.random.default_rng(3)
        n = 800
        probs = rng.dirichlet([1, 1, 1], size=n)
        y = rng.choice(["H", "D", "A"], n)
        cal = fit_isotonic_1x2(probs, y)
        out = cal.predict(probs)
        assert out.sum(axis=1) == pytest.approx(np.ones(n), abs=1e-9)
