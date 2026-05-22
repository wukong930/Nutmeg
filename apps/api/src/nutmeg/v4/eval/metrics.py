"""Probabilistic-prediction metrics for 1X2.

All functions take numpy arrays in canonical (H, D, A) column order.

Conventions:
- probs:  shape (N, 3), each row sums to ~1, columns are P(home_win), P(draw), P(away_win)
- y:      shape (N,), values in {'H', 'D', 'A'} or {0, 1, 2}

The output is always a single scalar (mean of the metric across rows).
"""
from __future__ import annotations

import numpy as np

EPS = 1e-12

LABELS = ("H", "D", "A")
LABEL_TO_IDX = {label: i for i, label in enumerate(LABELS)}


def encode_labels(y) -> np.ndarray:
    """Encode 'H'/'D'/'A' (or already-int) labels into {0,1,2}."""
    arr = np.asarray(y)
    if np.issubdtype(arr.dtype, np.integer):
        return arr.astype(int)
    return np.asarray([LABEL_TO_IDX[str(v)] for v in y], dtype=int)


def log_loss(probs: np.ndarray, y) -> float:
    """Mean negative log-likelihood of the realised outcome under `probs`.

    Lower is better. Perfect prediction = 0. A uniform 1/3 baseline = log(3) ≈ 1.0986.
    """
    probs = np.clip(np.asarray(probs, dtype=float), EPS, 1.0)
    idx = encode_labels(y)
    chosen = probs[np.arange(len(idx)), idx]
    return float(-np.log(chosen).mean())


def brier(probs: np.ndarray, y) -> float:
    """Multiclass Brier score: mean squared error between `probs` and one-hot truth.

    Range [0, 2]. Lower is better. Uniform 1/3 = 2/3.
    """
    probs = np.asarray(probs, dtype=float)
    idx = encode_labels(y)
    one_hot = np.zeros_like(probs)
    one_hot[np.arange(len(idx)), idx] = 1.0
    return float(((probs - one_hot) ** 2).sum(axis=1).mean())


def hit_rate(probs: np.ndarray, y) -> float:
    """Fraction of rows where argmax(probs) == y."""
    probs = np.asarray(probs, dtype=float)
    idx = encode_labels(y)
    preds = probs.argmax(axis=1)
    return float((preds == idx).mean())


def ece(probs: np.ndarray, y, *, n_bins: int = 10) -> float:
    """Expected Calibration Error: weighted gap between predicted prob and observed freq,
    computed over the predicted probability of the predicted class.
    """
    probs = np.asarray(probs, dtype=float)
    idx = encode_labels(y)
    confidences = probs.max(axis=1)
    predictions = probs.argmax(axis=1)
    correct = (predictions == idx).astype(float)
    bins = np.linspace(0, 1, n_bins + 1)
    n = len(idx)
    out = 0.0
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (confidences > lo) & (confidences <= hi) if i > 0 else (confidences >= lo) & (confidences <= hi)
        if mask.sum() == 0:
            continue
        avg_conf = confidences[mask].mean()
        avg_acc = correct[mask].mean()
        weight = mask.sum() / n
        out += weight * abs(avg_conf - avg_acc)
    return float(out)


def summary(probs: np.ndarray, y) -> dict:
    """Return all standard metrics as a dict."""
    return {
        "n":         int(len(y)),
        "log_loss":  log_loss(probs, y),
        "brier":     brier(probs, y),
        "hit_rate":  hit_rate(probs, y),
        "ece":       ece(probs, y),
    }
