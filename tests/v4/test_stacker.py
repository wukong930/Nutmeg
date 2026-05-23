"""Tests for nutmeg.v4.model.stacker — LogisticRegression ensemble stacker."""
from __future__ import annotations

import numpy as np
import pytest

from nutmeg.v4.model.stacker import (
    StackerCalibrator,
    _stack_logits,
    _to_logit,
    fit_stacker,
)


def _rand_probs(n: int, rng: np.random.Generator) -> np.ndarray:
    """Generate (n, 3) probability arrays summing to 1 per row."""
    raw = rng.exponential(scale=1.0, size=(n, 3))
    return raw / raw.sum(axis=1, keepdims=True)


@pytest.fixture
def synthetic_val():
    rng = np.random.default_rng(42)
    n = 600
    y_true = rng.choice(["H", "D", "A"], n, p=[0.45, 0.27, 0.28])

    # Three "base models" with slightly different biases
    def model_probs(noise: float, bias: dict[str, float]) -> np.ndarray:
        truth = np.zeros((n, 3))
        for i, lbl in enumerate(y_true):
            idx = {"H": 0, "D": 1, "A": 2}[lbl]
            truth[i, idx] = 0.6
        # spread + bias
        p = truth + rng.uniform(0, noise, (n, 3))
        for j, k in enumerate(["H", "D", "A"]):
            p[:, j] += bias[k]
        p = np.clip(p, 0.01, None)
        return p / p.sum(axis=1, keepdims=True)

    base1 = model_probs(0.3, {"H": 0.05, "D": -0.02, "A": -0.03})
    base2 = model_probs(0.3, {"H": -0.03, "D": 0.05, "A": -0.02})
    base3 = model_probs(0.3, {"H": -0.02, "D": -0.03, "A": 0.05})
    return [base1, base2, base3], y_true


class TestLogitHelpers:
    def test_to_logit_inverse(self) -> None:
        p = np.array([[0.3, 0.5, 0.2]])
        logit = _to_logit(p)
        # Re-invert
        recovered = 1.0 / (1.0 + np.exp(-logit))
        np.testing.assert_allclose(recovered, p, atol=1e-9)

    def test_to_logit_handles_boundary(self) -> None:
        # 0 and 1 should not produce inf
        p = np.array([[0.0, 1.0, 0.5]])
        logit = _to_logit(p)
        assert np.isfinite(logit).all()

    def test_stack_logits_concatenates(self, synthetic_val) -> None:
        bases, _ = synthetic_val
        stacked = _stack_logits(bases)
        assert stacked.shape == (len(bases[0]), 3 * len(bases))

    def test_stack_logits_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            _stack_logits([])


class TestFitStacker:
    def test_returns_calibrator(self, synthetic_val) -> None:
        bases, y = synthetic_val
        stacker = fit_stacker(bases, y)
        assert isinstance(stacker, StackerCalibrator)
        assert stacker.n_bases == 3

    def test_rejects_too_few_bases(self) -> None:
        rng = np.random.default_rng(0)
        with pytest.raises(ValueError, match="≥ 2"):
            fit_stacker([_rand_probs(100, rng)], np.array(["H"] * 100))

    def test_rejects_length_mismatch(self) -> None:
        rng = np.random.default_rng(0)
        b1 = _rand_probs(100, rng)
        b2 = _rand_probs(80, rng)
        with pytest.raises(ValueError, match="match y len"):
            fit_stacker([b1, b2], np.array(["H"] * 100))

    def test_rejects_wrong_column_count(self) -> None:
        rng = np.random.default_rng(0)
        b1 = _rand_probs(100, rng)
        bad = rng.uniform(0, 1, (100, 4))  # 4 cols instead of 3
        with pytest.raises(ValueError, match="3 columns"):
            fit_stacker([b1, bad], np.array(["H"] * 100))


class TestPredict:
    def test_output_shape(self, synthetic_val) -> None:
        bases, y = synthetic_val
        stacker = fit_stacker(bases, y)
        preds = stacker.predict(bases)
        assert preds.shape == bases[0].shape

    def test_rows_sum_to_one(self, synthetic_val) -> None:
        bases, y = synthetic_val
        stacker = fit_stacker(bases, y)
        preds = stacker.predict(bases)
        np.testing.assert_allclose(preds.sum(axis=1), 1.0, atol=1e-6)

    def test_columns_ordered_HDA(self, synthetic_val) -> None:
        bases, y = synthetic_val
        # Force a strong H signal in all three bases
        forced = [np.array([[0.9, 0.05, 0.05]])] * 3
        stacker = fit_stacker(bases, y)
        preds = stacker.predict(forced)
        # Column 0 should be the largest
        assert preds[0, 0] > preds[0, 1]
        assert preds[0, 0] > preds[0, 2]

    def test_rejects_wrong_base_count(self, synthetic_val) -> None:
        bases, y = synthetic_val
        stacker = fit_stacker(bases, y)
        with pytest.raises(ValueError, match="expected"):
            stacker.predict(bases[:2])  # 2 instead of 3
