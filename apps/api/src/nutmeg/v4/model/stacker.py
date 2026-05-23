"""Logistic-regression stacker for V5 ensemble.

Inputs (concatenated horizontally):
    base_probs: list of (N, 3) arrays, one per base model (1X2 probs after DC).
                Expected len = 3 (lightgbm + xgboost + catboost).
    y_val: (N,) array of 'H'/'D'/'A' labels for fitting.

Internally we work in logit space — the LogisticRegression is multinomial with
L2 regularization, taking the concatenated 9-dim logit vector as features. This
is meaningfully different from a simple weighted-average of probabilities:
the stacker can learn that "if model A says home but model B says draw with
high confidence, prefer draw" — interaction effects a weighted-mean can't.

Fitting on the validation slice (not training!) prevents the stacker from
amplifying base-model overfit. Sample size: ~500-1500 val matches per fold
in our walk-forward — enough for a 9-feature L2 logistic with proper
regularization.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression


# Probability clamp before taking logit, to avoid log(0)
EPS = 1e-9


def _to_logit(p: np.ndarray) -> np.ndarray:
    """(N, 3) probs → (N, 3) logits = log(p / (1 - p))."""
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1.0 - p))


def _stack_logits(base_probs: list[np.ndarray]) -> np.ndarray:
    """Horizontally concat per-base logits into (N, 3*len(bases)) matrix."""
    if not base_probs:
        raise ValueError("base_probs must be non-empty")
    return np.hstack([_to_logit(p) for p in base_probs])


@dataclass
class StackerCalibrator:
    """LogisticRegression in logit space + a softmax output."""

    model: LogisticRegression
    classes_: np.ndarray  # ['A', 'D', 'H'] in sklearn order (sorted)
    n_bases: int

    def predict(self, base_probs: list[np.ndarray]) -> np.ndarray:
        """Return (N, 3) probabilities in [home, draw, away] order."""
        if len(base_probs) != self.n_bases:
            raise ValueError(
                f"expected {self.n_bases} base prob arrays, got {len(base_probs)}"
            )
        X = _stack_logits(base_probs)
        p_sklearn = self.model.predict_proba(X)  # columns ordered by classes_
        # Reorder to canonical [H, D, A]
        canonical = ["H", "D", "A"]
        idx = [list(self.classes_).index(c) for c in canonical]
        return p_sklearn[:, idx]


def fit_stacker(
    base_probs: list[np.ndarray],
    y: np.ndarray,
    *,
    C: float = 1.0,
) -> StackerCalibrator:
    """Fit a multinomial L2 LogisticRegression on stacked base logits.

    ``base_probs`` is a list of (N, 3) arrays. We expect each row's columns
    to be [P(home), P(draw), P(away)] — the same convention used everywhere
    else in V4.

    ``C`` is sklearn's inverse-regularization strength. Default 1.0 (= L2
    coefficient 1.0). With 3 bases × 3 classes = 9 features and a typical
    val set of ~1k matches, this is the conventional choice.
    """
    if len(base_probs) < 2:
        raise ValueError("ensemble stacker needs ≥ 2 base prob arrays")
    n = len(y)
    for i, p in enumerate(base_probs):
        if p.shape[0] != n:
            raise ValueError(
                f"base_probs[{i}].shape = {p.shape} doesn't match y len = {n}"
            )
        if p.shape[1] != 3:
            raise ValueError(f"base_probs[{i}] must have 3 columns, got {p.shape[1]}")

    X = _stack_logits(base_probs)

    # sklearn LogisticRegression(multi_class="multinomial") is deprecated in
    # newer versions — they always do multinomial when the data has >2 classes.
    # We explicitly set solver to keep behavior stable across versions.
    lr = LogisticRegression(
        C=C,
        solver="lbfgs",
        max_iter=2000,
        random_state=42,
    )
    lr.fit(X, y)

    return StackerCalibrator(model=lr, classes_=lr.classes_, n_bases=len(base_probs))
