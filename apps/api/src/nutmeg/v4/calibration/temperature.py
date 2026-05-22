"""Temperature scaling for multiclass probability calibration.

Given raw probabilities p (N, 3), temperature scaling computes:
    logits = log(p)
    p_calibrated = softmax(logits / T)

T > 1 makes the distribution softer (less confident).
T < 1 makes it sharper (more confident).
T is fit on a validation set by minimizing log-loss via 1-D scalar optimization.

Why this over isotonic at small sample size:
  - Isotonic has unbounded degrees of freedom and overfits on <1000 samples.
  - Temperature has 1 parameter, so it cannot overfit; it can only shift
    overall confidence uniformly.
  - Empirically (Guo et al. 2017, "On Calibration of Modern Neural Networks"),
    temperature scaling is surprisingly competitive with isotonic even at
    large sample size, and dominates at small N.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize_scalar

from nutmeg.v4.eval.metrics import encode_labels

EPS = 1e-9


def _softmax_logits(logits: np.ndarray, T: float) -> np.ndarray:
    """Numerically stable softmax(logits / T) per row."""
    z = logits / T
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _neg_log_likelihood(T: float, logits: np.ndarray, y_idx: np.ndarray) -> float:
    if T <= 0:
        return 1e9
    p = _softmax_logits(logits, T)
    p = np.clip(p, EPS, 1.0)
    n = len(y_idx)
    return float(-np.log(p[np.arange(n), y_idx]).mean())


@dataclass
class TemperatureCalibrator:
    """One-parameter calibrator: predict() applies softmax(log(p_raw)/T)."""
    T: float
    n_train: int = 0
    nll_before: float = 0.0
    nll_after: float = 0.0

    def predict(self, raw_probs: np.ndarray) -> np.ndarray:
        raw = np.clip(np.asarray(raw_probs, dtype=float), EPS, 1.0)
        logits = np.log(raw)
        return _softmax_logits(logits, self.T)

    def __call__(self, raw_probs: np.ndarray) -> np.ndarray:
        return self.predict(raw_probs)


def fit_temperature_1x2(raw_probs: np.ndarray, y, *, t_bounds: tuple[float, float] = (0.3, 5.0)) -> TemperatureCalibrator:
    """Fit T by minimizing log-loss on (raw_probs, y) pool.

    `y` is array of {'H','D','A'} or {0,1,2}.
    """
    raw = np.clip(np.asarray(raw_probs, dtype=float), EPS, 1.0)
    if raw.shape[1] != 3:
        raise ValueError(f"expected (N, 3) probs, got {raw.shape}")
    y_idx = encode_labels(y)
    if len(y_idx) != raw.shape[0]:
        raise ValueError("raw_probs and y length mismatch")
    if len(y_idx) < 30:
        raise ValueError(f"need at least 30 samples to fit temperature, got {len(y_idx)}")

    logits = np.log(raw)
    nll_before = _neg_log_likelihood(1.0, logits, y_idx)

    res = minimize_scalar(
        _neg_log_likelihood,
        args=(logits, y_idx),
        bounds=t_bounds,
        method="bounded",
    )
    T = float(res.x)
    nll_after = float(res.fun)

    return TemperatureCalibrator(
        T=T, n_train=len(y_idx),
        nll_before=nll_before, nll_after=nll_after,
    )
