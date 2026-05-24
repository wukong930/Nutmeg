"""Maximum-likelihood Dixon-Coles fit.

Parameters fitted jointly via scipy.optimize.minimize (L-BFGS-B):
  - mu                : log of expected goals baseline (per team per match)
  - home_advantage    : log home/away goal ratio
  - attack[team]      : team-specific attacking strength (in log space)
  - defense[team]     : team-specific defensive weakness (in log space)
  - rho               : DC low-score correlation parameter, constrained to [-0.2, 0.2]

Identifiability constraint: sum(attack) = 0 and sum(defense) = 0.
This is enforced by parameterising N-1 teams freely and setting the Nth to minus the sum.

Goal model:
  lambda_home = exp(mu + home_advantage + attack[home] - defense[away])
  lambda_away = exp(mu                  + attack[away] - defense[home])

Time decay: each match is weighted by exp(-xi * days_before_as_of). Larger xi = recent matches matter more.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson


# ---- Hyper-defaults (sane starting points; can be overridden) ----
DEFAULT_TIME_DECAY_XI = 0.0026  # half-life ~265 days
DEFAULT_TRAIN_WINDOW_DAYS = 540  # ~1.5 seasons
DEFAULT_MAX_GOALS = 8
DEFAULT_RHO_BOUNDS = (-0.18, 0.18)


@dataclass
class DCParams:
    """Fitted parameters for one league (or pooled set of leagues)."""
    teams: list[str]
    mu: float
    home_advantage: float
    rho: float
    attack: dict[str, float]
    defense: dict[str, float]
    train_n: int
    iterations: int
    converged: bool


def _weights(dates: np.ndarray, as_of: pd.Timestamp, xi: float) -> np.ndarray:
    """Exponential time-decay weights."""
    days_back = (pd.to_datetime(as_of).to_datetime64() - dates).astype("timedelta64[D]").astype(float)
    days_back = np.clip(days_back, 0.0, None)
    return np.exp(-xi * days_back)


def _unpack(theta: np.ndarray, n_teams: int) -> tuple[float, float, float, np.ndarray, np.ndarray]:
    """Unpack theta into (mu, home_adv, rho, attack[N], defense[N]) where last attack/defense
    are pinned to minus the sum of the first N-1 (zero-sum constraint)."""
    mu = theta[0]
    home_adv = theta[1]
    rho = theta[2]
    free_attack = theta[3 : 3 + (n_teams - 1)]
    free_defense = theta[3 + (n_teams - 1) :]
    attack = np.concatenate([free_attack, [-free_attack.sum()]])
    defense = np.concatenate([free_defense, [-free_defense.sum()]])
    return mu, home_adv, rho, attack, defense


def _neg_log_likelihood(
    theta: np.ndarray,
    home_idx: np.ndarray,
    away_idx: np.ndarray,
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    weights: np.ndarray,
    n_teams: int,
) -> float:
    mu, home_adv, rho, attack, defense = _unpack(theta, n_teams)

    log_lh = mu + home_adv + attack[home_idx] - defense[away_idx]
    log_la = mu              + attack[away_idx] - defense[home_idx]
    # Numerical guard: clip log-lambda to a sane range to avoid overflow.
    log_lh = np.clip(log_lh, -3.0, 2.5)
    log_la = np.clip(log_la, -3.0, 2.5)
    lh = np.exp(log_lh)
    la = np.exp(log_la)

    # log P(home_goals | lh) + log P(away_goals | la) for independent Poisson
    ll = poisson.logpmf(home_goals, lh) + poisson.logpmf(away_goals, la)

    # Dixon-Coles low-score correction (vectorised)
    # tau_00 = 1 - lh*la*rho ; tau_01 = 1 + lh*rho ; tau_10 = 1 + la*rho ; tau_11 = 1 - rho
    is_00 = (home_goals == 0) & (away_goals == 0)
    is_01 = (home_goals == 0) & (away_goals == 1)
    is_10 = (home_goals == 1) & (away_goals == 0)
    is_11 = (home_goals == 1) & (away_goals == 1)
    tau = np.ones_like(lh)
    tau[is_00] = np.clip(1.0 - lh[is_00] * la[is_00] * rho, 1e-9, None)
    tau[is_01] = np.clip(1.0 + lh[is_01] * rho, 1e-9, None)
    tau[is_10] = np.clip(1.0 + la[is_10] * rho, 1e-9, None)
    tau[is_11] = np.clip(1.0 - rho, 1e-9, None)
    ll = ll + np.log(tau)

    return float(-(weights * ll).sum())


def fit_dixon_coles(
    train: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
    time_decay_xi: float = DEFAULT_TIME_DECAY_XI,
    rho_bounds: tuple[float, float] = DEFAULT_RHO_BOUNDS,
    max_iter: int = 200,
    verbose: bool = False,
) -> DCParams:
    """Fit Dixon-Coles parameters via L-BFGS-B.

    `train` is a DataFrame with at least: date, home_team, away_team, home_goals, away_goals.
    """
    if len(train) == 0:
        raise ValueError("no training matches")

    teams = sorted(set(train.home_team) | set(train.away_team))
    n_teams = len(teams)
    team_idx = {t: i for i, t in enumerate(teams)}

    home_idx = train.home_team.map(team_idx).to_numpy(dtype=int)
    away_idx = train.away_team.map(team_idx).to_numpy(dtype=int)
    home_goals = train.home_goals.to_numpy(dtype=int)
    away_goals = train.away_goals.to_numpy(dtype=int)
    weights = _weights(train.date.to_numpy(), as_of, time_decay_xi)

    # Initial point: mu = log(mean goals per team per match), home_adv = log(home/away),
    # attack/defense = 0, rho = -0.05 (typical empirical value).
    avg_home = max(0.3, home_goals.mean())
    avg_away = max(0.3, away_goals.mean())
    mu0 = float(np.log(avg_away))
    ha0 = float(np.log(avg_home / avg_away))
    theta0 = np.concatenate([
        [mu0, ha0, -0.05],
        np.zeros(n_teams - 1),  # free attack params
        np.zeros(n_teams - 1),  # free defense params
    ])

    # Bounds: mu in [-1, 2], home_adv in [-0.5, 1.0], rho per arg, attack/defense in [-1, 1]
    bounds = [(-1.0, 2.0), (-0.5, 1.0), rho_bounds]
    bounds += [(-1.0, 1.0)] * (n_teams - 1)  # attack
    bounds += [(-1.0, 1.0)] * (n_teams - 1)  # defense

    # post-v9 P1#6: scipy 1.18+ deprecates BOTH `disp` and `iprint` for
    # L-BFGS-B; the verbose-flag chatter was never used in production
    # (verbose=False everywhere) so we drop the option entirely. If actual
    # convergence diagnostics are needed in the future, attach a callback
    # or read `result.message` / `result.nit` after the fact.
    options = {"maxiter": max_iter}
    result = minimize(
        _neg_log_likelihood,
        theta0,
        args=(home_idx, away_idx, home_goals, away_goals, weights, n_teams),
        method="L-BFGS-B",
        bounds=bounds,
        options=options,
    )

    mu, home_adv, rho, attack, defense = _unpack(result.x, n_teams)
    return DCParams(
        teams=teams,
        mu=float(mu),
        home_advantage=float(home_adv),
        rho=float(rho),
        attack={t: float(attack[i]) for i, t in enumerate(teams)},
        defense={t: float(defense[i]) for i, t in enumerate(teams)},
        train_n=len(train),
        iterations=int(result.nit),
        converged=bool(result.success),
    )


def predict_lambdas(fixtures: pd.DataFrame, params: DCParams) -> np.ndarray:
    """For each fixture, return (lambda_home, lambda_away) using fitted params.

    Unknown teams (not in training set) fall back to attack=defense=0 (league average).
    """
    lambdas = np.empty((len(fixtures), 2), dtype=float)
    for k, row in enumerate(fixtures.itertuples(index=False)):
        ah = params.attack.get(row.home_team, 0.0)
        aa = params.attack.get(row.away_team, 0.0)
        dh = params.defense.get(row.home_team, 0.0)
        da = params.defense.get(row.away_team, 0.0)
        lh = np.exp(np.clip(params.mu + params.home_advantage + ah - da, -3.0, 2.5))
        la = np.exp(np.clip(params.mu                          + aa - dh, -3.0, 2.5))
        lambdas[k] = (lh, la)
    return lambdas
