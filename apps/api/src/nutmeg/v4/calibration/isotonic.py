"""Per-class isotonic regression for 1X2 probability calibration.

Why per-class instead of one-vs-rest 3-way:
  - Each isotonic learns a monotone f_c: raw_P(c) -> calibrated_P(c) for class c.
  - After applying f_H, f_D, f_A independently, rows no longer sum to 1, so we
    renormalize. This is the standard "Zadrozny & Elkan multiclass" approach
    and works well when the raw model is already reasonable.
  - The alternative (Dirichlet calibration / vector scaling) is fancier but
    overkill at 27k matches and harder to debug.

Usage:
    calib = fit_isotonic_1x2(raw_probs_val, y_val)
    probs_test_calibrated = calib.predict(raw_probs_test)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.isotonic import IsotonicRegression

from nutmeg.v4.eval.metrics import encode_labels

EPS = 1e-9


@dataclass
class IsotonicCalibrator1X2:
    """Three isotonic regressors, one per outcome class."""
    isotonics: list[IsotonicRegression] = field(default_factory=list)
    n_train: int = 0

    def predict(self, raw_probs: np.ndarray) -> np.ndarray:
        """Apply per-class calibration and renormalize so each row sums to 1."""
        raw = np.asarray(raw_probs, dtype=float)
        if raw.shape[1] != 3:
            raise ValueError(f"expected (N, 3) probs, got {raw.shape}")
        out = np.empty_like(raw)
        for c in range(3):
            out[:, c] = self.isotonics[c].predict(raw[:, c])
        # Floor to avoid zeros, then renormalize
        out = np.clip(out, EPS, 1.0 - EPS)
        out = out / out.sum(axis=1, keepdims=True)
        return out

    def __call__(self, raw_probs: np.ndarray) -> np.ndarray:
        return self.predict(raw_probs)


def fit_isotonic_1x2(raw_probs: np.ndarray, y) -> IsotonicCalibrator1X2:
    """Train three isotonic regressors from a held-out (raw_probs, y) sample.

    `y` is array of {'H','D','A'} or {0,1,2}.
    """
    raw = np.asarray(raw_probs, dtype=float)
    idx = encode_labels(y)

    if raw.shape[0] != len(idx):
        raise ValueError(f"raw_probs has {raw.shape[0]} rows but y has {len(idx)}")
    if raw.shape[0] < 50:
        raise ValueError(f"need at least 50 samples to fit isotonic, got {raw.shape[0]}")

    isotonics = []
    for c in range(3):
        one_hot = (idx == c).astype(float)
        ir = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        ir.fit(raw[:, c], one_hot)
        isotonics.append(ir)

    return IsotonicCalibrator1X2(isotonics=isotonics, n_train=len(idx))
