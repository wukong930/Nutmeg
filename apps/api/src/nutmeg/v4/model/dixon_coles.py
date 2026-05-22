"""Dixon-Coles model primitives.

This module is pure math: given (lambda_home, lambda_away, rho) it builds the
9x9 score grid; given a score grid it produces 1X2 and integer-handicap-1X2
market probabilities. It does NOT know about parameter fitting (see dc_mle.py)
or feature engineering — those are upstream.

Key reference: Dixon & Coles (1997), "Modelling Association Football Scores
and Inefficiencies in the Football Betting Market".
"""
from __future__ import annotations

from math import exp, log

import numpy as np
from scipy.stats import poisson


MAX_GOALS_DEFAULT = 8


def dc_tau(home_goals: int, away_goals: int, lh: float, la: float, rho: float) -> float:
    """Dixon-Coles low-score correction. Adjusts the four cells (0-0, 0-1, 1-0, 1-1)
    to better fit the empirical correlation between home and away goals in low-scoring games.

    rho > 0 increases 1-1, decreases 0-1 and 1-0 (positive corr).
    rho < 0 (typical) increases 0-0 and 1-1, decreases 0-1 and 1-0 (the empirically observed pattern).
    """
    if home_goals == 0 and away_goals == 0:
        return max(0.0, 1.0 - lh * la * rho)
    if home_goals == 0 and away_goals == 1:
        return max(0.0, 1.0 + lh * rho)
    if home_goals == 1 and away_goals == 0:
        return max(0.0, 1.0 + la * rho)
    if home_goals == 1 and away_goals == 1:
        return max(0.0, 1.0 - rho)
    return 1.0


def score_grid(
    lambda_home: float,
    lambda_away: float,
    *,
    rho: float = 0.0,
    max_goals: int = MAX_GOALS_DEFAULT,
) -> np.ndarray:
    """Build the (max_goals+1) x (max_goals+1) joint score probability grid.

    grid[i, j] = P(home_goals = i, away_goals = j).
    Mass beyond max_goals is folded into the diagonal element by row-sum normalisation.
    """
    if lambda_home <= 0 or lambda_away <= 0:
        raise ValueError("lambdas must be positive")
    n = max_goals + 1
    pmf_h = poisson.pmf(np.arange(n), lambda_home)
    pmf_a = poisson.pmf(np.arange(n), lambda_away)
    grid = np.outer(pmf_h, pmf_a)
    # Apply DC low-score tau correction
    if rho != 0.0:
        grid[0, 0] *= max(0.0, 1.0 - lambda_home * lambda_away * rho)
        grid[0, 1] *= max(0.0, 1.0 + lambda_home * rho)
        grid[1, 0] *= max(0.0, 1.0 + lambda_away * rho)
        grid[1, 1] *= max(0.0, 1.0 - rho)
    # Renormalise so the bounded grid is a valid distribution.
    s = grid.sum()
    if s <= 0:
        raise ValueError("score grid has non-positive mass")
    return grid / s


def grid_to_1x2(grid: np.ndarray) -> tuple[float, float, float]:
    """Integrate the score grid into home_win / draw / away_win probabilities."""
    n = grid.shape[0]
    home = 0.0
    draw = 0.0
    away = 0.0
    for i in range(n):
        for j in range(n):
            p = float(grid[i, j])
            if i > j:
                home += p
            elif i == j:
                draw += p
            else:
                away += p
    return home, draw, away


def grid_to_handicap_1x2(grid: np.ndarray, handicap_home: int) -> tuple[float, float, float]:
    """China-style integer handicap settlement.

    handicap_home is what home gets ADDED to its score (positive = home gets a head start,
    negative = home gives goals). Typical CN sport lottery values: -2, -1, 0, +1, +2.

    Returns (P(home_wins_after_handicap), P(draw_after_handicap), P(away_wins_after_handicap)).
    """
    n = grid.shape[0]
    p_h = 0.0
    p_d = 0.0
    p_a = 0.0
    for i in range(n):
        for j in range(n):
            p = float(grid[i, j])
            diff = (i + handicap_home) - j
            if diff > 0:
                p_h += p
            elif diff == 0:
                p_d += p
            else:
                p_a += p
    return p_h, p_d, p_a


def grid_to_over_under(grid: np.ndarray, line: float = 2.5) -> tuple[float, float]:
    """Over/Under total goals at given line (typically a half-integer like 2.5)."""
    n = grid.shape[0]
    p_over = 0.0
    p_under = 0.0
    for i in range(n):
        for j in range(n):
            p = float(grid[i, j])
            total = i + j
            if total > line:
                p_over += p
            else:
                p_under += p
    return p_over, p_under


def lambdas_to_1x2_array(lambdas: np.ndarray, rho: float = 0.0, max_goals: int = MAX_GOALS_DEFAULT) -> np.ndarray:
    """Vectorised: array of (lambda_h, lambda_a) → (N, 3) array of (P_H, P_D, P_A)."""
    out = np.empty((len(lambdas), 3), dtype=float)
    for i, (lh, la) in enumerate(lambdas):
        grid = score_grid(lh, la, rho=rho, max_goals=max_goals)
        out[i] = grid_to_1x2(grid)
    return out
