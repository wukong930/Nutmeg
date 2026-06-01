"""Unit tests for the β independent-signal test (eval/independent_signal.py).

Synthetic data with known answers — no walk-forward needed.
"""
from __future__ import annotations

import numpy as np
import pytest

from nutmeg.v4.eval.independent_signal import beta_sweep, blend, verdict


def _norm(a):
    a = np.asarray(a, dtype=float)
    return a / a.sum(axis=1, keepdims=True)


class TestBlendIdentities:
    def test_beta0_recovers_pinnacle(self):
        pin = _norm([[0.5, 0.3, 0.2], [0.2, 0.3, 0.5]])
        model = _norm([[0.1, 0.1, 0.8], [0.8, 0.1, 0.1]])
        np.testing.assert_allclose(blend(pin, model, 0.0), pin, atol=1e-9)

    def test_beta1_recovers_model(self):
        pin = _norm([[0.5, 0.3, 0.2], [0.2, 0.3, 0.5]])
        model = _norm([[0.1, 0.1, 0.8], [0.8, 0.1, 0.1]])
        np.testing.assert_allclose(blend(pin, model, 1.0), model, atol=1e-9)


class TestBetaSweep:
    def test_model_identical_to_pin_adds_nothing(self):
        # Geometric mean of identical distributions is flat across β: a model
        # that exactly equals the sharp carries zero independent signal.
        y = ["H", "D", "A"] * 10
        idx = {"H": 0, "D": 1, "A": 2}
        pin = np.full((len(y), 3), 0.1)
        for i, yy in enumerate(y):
            pin[i, idx[yy]] = 0.8
        pin = _norm(pin)
        r = beta_sweep(pin.copy(), pin.copy(), y)  # model == pin
        assert r["positive_beta_helps"] is False
        assert r["gap"] == pytest.approx(0.0, abs=1e-9)
        assert r["best_logloss"] == pytest.approx(r["pin_logloss"], abs=1e-9)
        assert "无独立增量" in verdict(r)

    def test_informative_aligned_model_helps(self):
        # Model concentrates on the true outcome; pin is uninformative (uniform)
        # → blending the model IN (β>0) must reduce log-loss.
        y = ["H", "D", "A"] * 10
        idx = {"H": 0, "D": 1, "A": 2}
        model = np.full((len(y), 3), 0.1)
        for i, yy in enumerate(y):
            model[i, idx[yy]] = 0.8
        model = _norm(model)
        pin = np.full((len(y), 3), 1.0 / 3.0)
        r = beta_sweep(model, pin, y)
        assert r["positive_beta_helps"] is True
        assert r["best_beta"] > 0.0
        assert r["gap"] < 0.0  # model better than (uniform) pin
        assert "独立信号" in verdict(r)

    def test_drops_invalid_rows(self):
        y = ["H", "D", "A"]
        pin = _norm([[0.5, 0.3, 0.2], [0.2, 0.3, 0.5], [0.4, 0.3, 0.3]])
        model = np.array([[0.3, 0.3, 0.4], [np.nan, 0.3, 0.5], [0.4, 0.3, 0.3]])
        r = beta_sweep(model, pin, y)
        assert r["n"] == 2  # the NaN row is dropped

    def test_accepts_integer_outcomes(self):
        y = [0, 1, 2]
        pin = _norm([[0.6, 0.2, 0.2], [0.2, 0.6, 0.2], [0.2, 0.2, 0.6]])
        r = beta_sweep(pin.copy(), pin.copy(), y)
        assert r["n"] == 3


class TestCliImports:
    def test_module_imports(self):
        from nutmeg.v4.cli import beta_test
        assert callable(beta_test.main)
