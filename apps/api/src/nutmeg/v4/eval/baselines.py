"""Baseline probability sources.

These are not models — they're reference benchmarks. Every model we train must
report its delta vs. these:

1. uniform_baseline: 1/3 1/3 1/3 (lower bound — log_loss = log(3))
2. priors_baseline: empirical 1X2 marginals on training set (slightly better than uniform)
3. pinnacle_baseline: vig-adjusted Pinnacle closing odds (this is the HARD baseline;
   beating it on closing-line tagged matches is the entire game)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def uniform_baseline(n: int) -> np.ndarray:
    return np.full((n, 3), 1.0 / 3.0)


def priors_baseline(train_df: pd.DataFrame, n_test: int) -> np.ndarray:
    """Empirical marginal P(H), P(D), P(A) on training set, repeated n_test times."""
    counts = train_df["result_1x2"].value_counts(normalize=True)
    probs = np.array([counts.get(c, 0.0) for c in ("H", "D", "A")])
    probs = probs / probs.sum()  # ensure normalised
    return np.tile(probs, (n_test, 1))


def devig_odds(home_odds, draw_odds, away_odds) -> np.ndarray:
    """Convert decimal odds to fair probabilities by removing the overround.

    Multiplicative method: p_i = (1/o_i) / sum(1/o_j). This is the simplest
    and most common devig method. More principled alternatives:
    - Shin (1992): assumes some bettors are informed; gives slightly different probs.
    - Power: solves for k such that sum p_i^k = 1.
    Multiplicative is fine for Pinnacle closing because the overround is small (~2%).

    Inputs: array-like of decimal odds (e.g. 2.10 means $1 returns $2.10).
    Output: (N, 3) array of probabilities; NaN-safe (NaN rows become NaN).
    """
    arr = np.column_stack([
        np.asarray(home_odds, dtype=float),
        np.asarray(draw_odds, dtype=float),
        np.asarray(away_odds, dtype=float),
    ])
    inv = 1.0 / arr
    total = inv.sum(axis=1, keepdims=True)
    return inv / total


def pinnacle_baseline(df: pd.DataFrame) -> np.ndarray:
    """Pinnacle closing 1X2 → fair probs. Returns NaN rows when PSC missing."""
    return devig_odds(df["psc_home"], df["psc_draw"], df["psc_away"])


def bet365_baseline(df: pd.DataFrame) -> np.ndarray:
    """Bet365 closing 1X2 → fair probs."""
    return devig_odds(df["b365c_home"], df["b365c_draw"], df["b365c_away"])


def avg_market_baseline(df: pd.DataFrame) -> np.ndarray:
    """Market consensus (average across many books) closing 1X2 → fair probs."""
    return devig_odds(df["avgc_home"], df["avgc_draw"], df["avgc_away"])
