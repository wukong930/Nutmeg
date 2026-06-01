"""Independent-signal test — does the model add anything beyond the sharp?

Geometric (log-opinion-pool) blend of a sharp baseline (Pinnacle de-vig) and
the model, swept over an exponent β:

    p_final_k ∝ p_pin_k^(1-β) · p_model_k^β        (k ∈ {H, D, A})

The β that minimises held-out log-loss says how much INDEPENDENT signal the
model carries on top of the sharp:

    β ≈ 0      → sharp already dominates; model adds no increment
    0 < β < .5 → model has a little independent signal
    β ≈ 0.5    → both carry real information
    β > 0.5    → model is strong, maybe ahead of the sharp in places
    β ≤ 0      → model has no increment (and may be a noisier echo of the sharp)

HONESTY: the robust signal is the SHAPE of the curve — does ANY β>0 beat pure
Pinnacle? The exact argmin β is fit and evaluated on the same set here, so it
is an in-sample (optimistic) estimate; do not ship it as a serving weight
without a separate held-out split. See `positive_beta_helps`.
"""
from __future__ import annotations

import numpy as np

# result_1x2 is 'H'/'D'/'A'; Pinnacle/​model prob columns are [home, draw, away].
_OUTCOME_INDEX = {"H": 0, "D": 1, "A": 2, 0: 0, 1: 1, 2: 2, "0": 0, "1": 1, "2": 2}

DEFAULT_BETAS = np.round(np.arange(-0.50, 1.51, 0.05), 2)


def _logloss(P: np.ndarray, y: np.ndarray) -> float:
    eps = 1e-15
    return float(-np.mean(np.log(np.clip(P[np.arange(len(y)), y], eps, 1.0))))


def blend(pin_p: np.ndarray, model_p: np.ndarray, beta: float) -> np.ndarray:
    """p ∝ pin^(1-β) · model^β, row-normalised. β=0 → pin, β=1 → model."""
    logf = (1.0 - beta) * np.log(pin_p) + beta * np.log(model_p)
    logf -= logf.max(axis=1, keepdims=True)  # stabilise; normalise-invariant
    P = np.exp(logf)
    return P / P.sum(axis=1, keepdims=True)


def beta_sweep(
    model_p, pin_p, y, betas: np.ndarray | None = None
) -> dict:
    """Sweep β over the geometric blend; return the curve + a robust verdict.

    Rows with non-finite or non-positive probabilities are dropped. Returns a
    dict: n, model_logloss, pin_logloss, gap (= model−pin), curve [(β, ll)],
    best_beta, best_logloss, positive_beta_helps.
    """
    model_p = np.asarray(model_p, dtype=float)
    pin_p = np.asarray(pin_p, dtype=float)
    y = np.array([_OUTCOME_INDEX[v] for v in np.asarray(y).ravel()], dtype=int)

    ok = (
        np.isfinite(model_p).all(1)
        & np.isfinite(pin_p).all(1)
        & (model_p > 0).all(1)
        & (pin_p > 0).all(1)
    )
    model_p, pin_p, y = model_p[ok], pin_p[ok], y[ok]
    if len(y) == 0:
        raise ValueError("no valid rows after filtering")

    betas = DEFAULT_BETAS if betas is None else np.asarray(betas, dtype=float)
    curve = [(float(b), _logloss(blend(pin_p, model_p, b), y)) for b in betas]

    model_ll = _logloss(model_p, y)
    pin_ll = _logloss(pin_p, y)
    best_beta, best_ll = min(curve, key=lambda t: t[1])
    # Robust signal: does ANY β>0 strictly beat pure Pinnacle?
    pos_lls = [ll for b, ll in curve if b > 1e-9]
    positive_beta_helps = bool(pos_lls and min(pos_lls) < pin_ll - 1e-6)

    return {
        "n": int(len(y)),
        "model_logloss": model_ll,
        "pin_logloss": pin_ll,
        "gap": model_ll - pin_ll,
        "curve": curve,
        "best_beta": best_beta,
        "best_logloss": best_ll,
        "positive_beta_helps": positive_beta_helps,
    }


def verdict(res: dict) -> str:
    """One-line human verdict from a beta_sweep result."""
    if res["positive_beta_helps"]:
        if res["best_beta"] >= 0.5:
            return "模型有强独立信号 (β≥0.5) — 可能在某些场合领先 sharp"
        return "模型有少量独立信号 (0<β<0.5) — 加权进来有正收益"
    return (
        "模型在 sharp 之外无独立增量 (最优 β≤0) — "
        "该市场上 Pinnacle 已盖过模型"
    )
