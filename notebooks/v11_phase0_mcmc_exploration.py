"""V11 Phase 0 #5 — Bayesian Poisson (MCMC) vs Dixon-Coles MLE.

Exploration script: do we benefit from putting a Bayesian hierarchical
model behind production, replacing the current DC MLE backbone? This
file runs the comparison end-to-end on EPL 2023-24 (train) / 2024-25
(test), and writes a markdown report to docs/v11_phase0_mcmc_report.md.

Why hand-rolled MCMC?
    PyMC + JAX + NumPyro add ~500 MB to the env. For a Phase 0
    *exploration* I want a self-contained NumPy/SciPy implementation
    that runs in 1-2 minutes. If the verdict is "MCMC wins, ship it",
    the production path would adopt NumPyro (faster). If the verdict
    is "DC matches", we save the dependency footprint.

Model
=====
Hierarchical Poisson with team strengths:

    log(λ_home) = home_adv + attack[home] - defense[away]
    log(λ_away) =           attack[away] - defense[home]
    goals_home ~ Poisson(λ_home)
    goals_away ~ Poisson(λ_away)
    Dixon-Coles low-score correction with parameter rho

Priors (weakly informative):
    home_adv      ~ Normal(0, 0.25)        # log-multiplier
    attack[t]     ~ Normal(0, 0.5)         # zero-sum constrained at the end
    defense[t]    ~ Normal(0, 0.5)
    rho           ~ Normal(-0.1, 0.05)    # match DC's typical -0.10 prior

MCMC
====
Metropolis-Hastings with adaptive proposal scale. 40 params for a
20-team league; samples in <60s with N=4000 iterations and 1000 burn-in.

Verdict format
==============
- Train log-loss / test log-loss for: Bayesian MCMC, DC MLE, market.
- Effective sample size + R-hat across 4 chains.
- Compute-time delta (MCMC vs MLE).
- Recommendation (ship to prod / hold / re-explore later).
"""
from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import math

import numpy as np
import pandas as pd
from scipy.special import gammaln
from scipy.stats import norm


log = logging.getLogger("v11_phase0_mcmc")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

REPO_ROOT = Path(__file__).resolve().parents[1]


# ============ Data loading ============================================

def load_epl_season(year: str) -> pd.DataFrame:
    """Load one EPL season from football-data.co.uk CSV.

    Returns DataFrame with columns:
      date, home, away, home_goals, away_goals,
      psh, psd, psa   (Pinnacle closing 1X2 odds; bookmaker reference)
    """
    path = REPO_ROOT / "data" / "historical_sources" / "football_data_co_uk" / "europe" / year / "E0.csv"
    df = pd.read_csv(path, encoding="utf-8-sig")
    # Football-data CSVs use UK date format
    df["date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
    df = df.rename(columns={
        "HomeTeam": "home", "AwayTeam": "away",
        "FTHG": "home_goals", "FTAG": "away_goals",
        "PSH": "psh", "PSD": "psd", "PSA": "psa",
    })
    df = df[["date", "home", "away", "home_goals", "away_goals", "psh", "psd", "psa"]]
    df = df.dropna(subset=["home_goals", "away_goals", "psh", "psd", "psa"])
    df["home_goals"] = df["home_goals"].astype(int)
    df["away_goals"] = df["away_goals"].astype(int)
    return df.reset_index(drop=True)


# ============ Model: log-likelihood ====================================

def _log_factorial(k: np.ndarray) -> np.ndarray:
    """log(k!) via gammaln(k+1) — vectorized + stable."""
    return gammaln(k + 1.0)


def dc_tau_log(hg: np.ndarray, ag: np.ndarray, lh: np.ndarray, la: np.ndarray, rho: float) -> np.ndarray:
    """Dixon-Coles low-score correction in log space.

    Returns ``log(tau(h, a, λh, λa, rho))`` for vectorized inputs. Falls
    back to 0 when (hg, ag) isn't in the corrected set {(0,0),(0,1),(1,0),(1,1)}.
    """
    tau = np.ones_like(lh)
    # (0, 0): 1 - λh*λa*rho
    mask = (hg == 0) & (ag == 0)
    tau[mask] = 1.0 - lh[mask] * la[mask] * rho
    # (1, 0): 1 + λa*rho
    mask = (hg == 1) & (ag == 0)
    tau[mask] = 1.0 + la[mask] * rho
    # (0, 1): 1 + λh*rho
    mask = (hg == 0) & (ag == 1)
    tau[mask] = 1.0 + lh[mask] * rho
    # (1, 1): 1 - rho
    mask = (hg == 1) & (ag == 1)
    tau[mask] = 1.0 - rho
    # Floor to avoid log(neg) when rho is at extremes
    tau = np.clip(tau, 1e-6, None)
    return np.log(tau)


def poisson_loglik(
    hg: np.ndarray, ag: np.ndarray,
    lh: np.ndarray, la: np.ndarray, rho: float,
) -> float:
    """Total log-lik over a batch of matches under DC-Poisson."""
    ll = (
        -lh + hg * np.log(lh) - _log_factorial(hg) +
        -la + ag * np.log(la) - _log_factorial(ag) +
        dc_tau_log(hg, ag, lh, la, rho)
    )
    return float(ll.sum())


# ============ Parameter packing =======================================

@dataclass
class ModelDims:
    teams: list[str]
    n_teams: int

    @property
    def n_params(self) -> int:
        # home_adv (1) + attack (n_teams) + defense (n_teams) + rho (1)
        return 1 + 2 * self.n_teams + 1


def build_dims(train_df: pd.DataFrame) -> ModelDims:
    teams = sorted(set(train_df["home"]).union(set(train_df["away"])))
    return ModelDims(teams=teams, n_teams=len(teams))


def unpack(theta: np.ndarray, dims: ModelDims) -> tuple[float, np.ndarray, np.ndarray, float]:
    """theta layout: [home_adv, attack..., defense..., rho]."""
    n = dims.n_teams
    home_adv = float(theta[0])
    attack = theta[1 : 1 + n]
    defense = theta[1 + n : 1 + 2 * n]
    rho = float(theta[-1])
    return home_adv, attack, defense, rho


def compute_lambdas(
    home_idx: np.ndarray, away_idx: np.ndarray,
    home_adv: float, attack: np.ndarray, defense: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    lh = np.exp(home_adv + attack[home_idx] - defense[away_idx])
    la = np.exp(           attack[away_idx] - defense[home_idx])
    return lh, la


# ============ Priors ==================================================

def log_prior(theta: np.ndarray, dims: ModelDims) -> float:
    home_adv, attack, defense, rho = unpack(theta, dims)
    lp = 0.0
    lp += norm.logpdf(home_adv, loc=0.0,  scale=0.25)
    lp += norm.logpdf(attack,   loc=0.0,  scale=0.5).sum()
    lp += norm.logpdf(defense,  loc=0.0,  scale=0.5).sum()
    lp += norm.logpdf(rho,      loc=-0.1, scale=0.05)
    return float(lp)


def log_posterior(
    theta: np.ndarray, dims: ModelDims,
    home_idx: np.ndarray, away_idx: np.ndarray,
    hg: np.ndarray, ag: np.ndarray,
) -> float:
    home_adv, attack, defense, rho = unpack(theta, dims)
    if not (-0.25 < rho < 0.25):
        return -np.inf
    lh, la = compute_lambdas(home_idx, away_idx, home_adv, attack, defense)
    ll = poisson_loglik(hg, ag, lh, la, rho)
    return ll + log_prior(theta, dims)


# ============ MAP via gradient-free optimization ======================

def fit_map(
    dims: ModelDims,
    home_idx: np.ndarray, away_idx: np.ndarray,
    hg: np.ndarray, ag: np.ndarray,
) -> np.ndarray:
    """Find a posterior mode via repeated coordinate descent + line search.

    Used as the starting point for MCMC chains. Mostly we just want
    something near the mode so the burn-in isn't wasteful.
    """
    from scipy.optimize import minimize
    n = dims.n_teams

    def neg_log_post(theta: np.ndarray) -> float:
        return -log_posterior(theta, dims, home_idx, away_idx, hg, ag)

    # Init: home_adv ~ 0.25, attack/defense ~ small, rho ~ -0.1
    theta0 = np.zeros(dims.n_params)
    theta0[0] = 0.25
    theta0[-1] = -0.10

    res = minimize(
        neg_log_post, theta0,
        method="L-BFGS-B",
        bounds=[(-1.0, 1.0)] + [(-2.0, 2.0)] * (2 * n) + [(-0.24, 0.24)],
        options={"maxiter": 300, "disp": False},
    )
    log.info("MAP optimization: success=%s, fun=%.2f", res.success, res.fun)
    return res.x


# ============ Metropolis-Hastings sampler =============================

def mh_sample(
    dims: ModelDims,
    home_idx: np.ndarray, away_idx: np.ndarray,
    hg: np.ndarray, ag: np.ndarray,
    *,
    n_chains: int = 4,
    n_iter: int = 4000,
    n_burn: int = 1000,
    seed: int = 42,
) -> np.ndarray:
    """Block-componentwise Metropolis-Hastings with adaptive scale.

    Returns array of shape (n_chains, n_iter - n_burn, n_params).
    """
    rng = np.random.default_rng(seed)
    theta_map = fit_map(dims, home_idx, away_idx, hg, ag)

    # Initial proposal scales (per-coord). Tuned heuristically — get
    # refined during burn-in via Robbins-Monro adaptation targeting
    # acceptance rate 0.35 (good for ~30D blocks).
    init_scale = np.full(dims.n_params, 0.04)
    init_scale[0] = 0.03              # home_adv tighter
    init_scale[-1] = 0.015            # rho — moderate (was too tight at 0.005)

    all_samples = np.zeros((n_chains, n_iter - n_burn, dims.n_params), dtype=np.float64)

    for c in range(n_chains):
        # Each chain starts MAP + small perturbation
        theta = theta_map + rng.normal(0, 0.05, size=dims.n_params)
        cur_lp = log_posterior(theta, dims, home_idx, away_idx, hg, ag)
        scale = init_scale.copy()
        accepts = 0
        kept = 0

        for it in range(n_iter):
            prop = theta + rng.normal(0, scale, size=dims.n_params)
            prop_lp = log_posterior(prop, dims, home_idx, away_idx, hg, ag)
            if np.log(rng.random()) < prop_lp - cur_lp:
                theta = prop
                cur_lp = prop_lp
                accepts += 1
            # Burn-in adaptation: target 35% acceptance
            if it < n_burn:
                rate = accepts / max(1, it + 1)
                if rate < 0.20:
                    scale *= 0.97
                elif rate > 0.50:
                    scale *= 1.03
            else:
                all_samples[c, kept] = theta
                kept += 1
        rate = accepts / n_iter
        log.info("Chain %d acceptance: %.2f%%, final scale[0]=%.4f, scale[-1]=%.4f",
                 c, rate * 100, scale[0], scale[-1])

    return all_samples


# ============ MCMC diagnostics ========================================

def effective_sample_size(chains: np.ndarray) -> float:
    """ESS via simple autocorrelation cutoff. chains: (n_chains, n_iter)."""
    n_chains, n = chains.shape
    flat = chains.flatten()
    # Compute autocorrelation up to lag n//4
    mean = flat.mean()
    var = flat.var()
    if var == 0:
        return float(n_chains * n)
    rho_sum = 0.0
    for lag in range(1, min(n // 4, 500)):
        c = ((flat[:-lag] - mean) * (flat[lag:] - mean)).mean() / var
        if c < 0.05:
            break
        rho_sum += c
    ess = n_chains * n / (1.0 + 2.0 * rho_sum)
    return float(ess)


def r_hat(chains: np.ndarray) -> float:
    """Gelman-Rubin R-hat for a parameter across chains.

    chains: (n_chains, n_iter)
    Returns sqrt((W + B/n) / W). Values near 1.0 indicate convergence.
    """
    n_chains, n = chains.shape
    if n_chains < 2:
        return float("nan")
    chain_means = chains.mean(axis=1)
    chain_vars = chains.var(axis=1, ddof=1)
    W = chain_vars.mean()
    B = n * chain_means.var(ddof=1)
    if W == 0:
        return 1.0
    var_hat = ((n - 1) / n) * W + B / n
    return float(np.sqrt(var_hat / W))


# ============ Prediction + log-loss ===================================

def predict_3way_from_lambdas(lh: float, la: float, rho: float, max_goals: int = 10) -> tuple[float, float, float]:
    """Compute (P_home, P_draw, P_away) under DC-Poisson."""
    grid = np.zeros((max_goals + 1, max_goals + 1))
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            tau = 1.0
            if i == 0 and j == 0:
                tau = 1.0 - lh * la * rho
            elif i == 1 and j == 0:
                tau = 1.0 + la * rho
            elif i == 0 and j == 1:
                tau = 1.0 + lh * rho
            elif i == 1 and j == 1:
                tau = 1.0 - rho
            tau = max(1e-6, tau)
            p_ij = (
                np.exp(-lh - la)
                * (lh ** i) * (la ** j)
                / (math.factorial(i) * math.factorial(j))
                * tau
            )
            grid[i, j] = p_ij
    grid = grid / grid.sum()
    p_h = float(np.tril(grid, -1).sum())
    p_d = float(np.diag(grid).sum())
    p_a = float(np.triu(grid, 1).sum())
    return p_h, p_d, p_a


def log_loss_3way(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Mean log-loss. probs: (N, 3). outcomes: (N,) ∈ {0, 1, 2} for H/D/A."""
    p = np.clip(probs[np.arange(len(outcomes)), outcomes], 1e-12, 1.0)
    return float(-np.log(p).mean())


def outcome_label(home_goals: int, away_goals: int) -> int:
    if home_goals > away_goals: return 0
    if home_goals == away_goals: return 1
    return 2


# ============ MLE baseline (Dixon-Coles fit) ==========================

def fit_mle(
    dims: ModelDims,
    home_idx: np.ndarray, away_idx: np.ndarray,
    hg: np.ndarray, ag: np.ndarray,
) -> np.ndarray:
    """Maximum-likelihood DC fit — same model, just no prior + optimizer.

    Used as the "DC MLE" baseline to compare MCMC posterior mean against.
    """
    from scipy.optimize import minimize
    n = dims.n_teams

    def neg_ll(theta: np.ndarray) -> float:
        home_adv, attack, defense, rho = unpack(theta, dims)
        if not (-0.25 < rho < 0.25):
            return 1e10
        lh, la = compute_lambdas(home_idx, away_idx, home_adv, attack, defense)
        return -poisson_loglik(hg, ag, lh, la, rho)

    theta0 = np.zeros(dims.n_params)
    theta0[0] = 0.25
    theta0[-1] = -0.10
    res = minimize(
        neg_ll, theta0, method="L-BFGS-B",
        bounds=[(-1.0, 1.0)] + [(-2.0, 2.0)] * (2 * n) + [(-0.24, 0.24)],
        options={"maxiter": 500},
    )
    log.info("MLE fit: success=%s, fun=%.2f", res.success, res.fun)
    return res.x


# ============ Market baseline (Pinnacle) ===============================

def market_probs(psh: np.ndarray, psd: np.ndarray, psa: np.ndarray) -> np.ndarray:
    """Pinnacle closing-line probabilities (after vig removal)."""
    inv = np.column_stack([1.0 / psh, 1.0 / psd, 1.0 / psa])
    return inv / inv.sum(axis=1, keepdims=True)


# ============ End-to-end run ==========================================

def run_comparison() -> dict:
    """Train on 2023-24, test on 2024-25, compare MCMC / MLE / market."""
    train = load_epl_season("2324")
    test = load_epl_season("2425")
    log.info("Train: %d EPL matches (2023-24)", len(train))
    log.info("Test:  %d EPL matches (2024-25)", len(test))

    # Team universe from train
    dims = build_dims(train)
    team_to_idx = {t: i for i, t in enumerate(dims.teams)}
    # Drop test rows referencing unseen teams (promoted clubs not in train)
    seen = set(dims.teams)
    test_clean = test[test["home"].isin(seen) & test["away"].isin(seen)].reset_index(drop=True)
    log.info("Test after dropping promoted teams (no prior): %d (dropped %d)",
             len(test_clean), len(test) - len(test_clean))

    home_idx = train["home"].map(team_to_idx).values
    away_idx = train["away"].map(team_to_idx).values
    hg = train["home_goals"].values
    ag = train["away_goals"].values

    # ----- MLE -----
    t0 = time.perf_counter()
    mle_theta = fit_mle(dims, home_idx, away_idx, hg, ag)
    mle_time = time.perf_counter() - t0

    # ----- MCMC -----
    t0 = time.perf_counter()
    mcmc_chains = mh_sample(dims, home_idx, away_idx, hg, ag,
                            n_chains=6, n_iter=20000, n_burn=5000)
    mcmc_time = time.perf_counter() - t0
    # Posterior mean across all (chain, sample)
    posterior_mean = mcmc_chains.reshape(-1, dims.n_params).mean(axis=0)

    # ----- Predict on test -----
    h_idx_te = test_clean["home"].map(team_to_idx).values
    a_idx_te = test_clean["away"].map(team_to_idx).values
    hg_te = test_clean["home_goals"].values
    ag_te = test_clean["away_goals"].values
    outcomes_te = np.array([outcome_label(h, a) for h, a in zip(hg_te, ag_te)])

    def predict_all(theta: np.ndarray) -> np.ndarray:
        ha, atk, dfn, rho = unpack(theta, dims)
        lh, la = compute_lambdas(h_idx_te, a_idx_te, ha, atk, dfn)
        probs = np.zeros((len(hg_te), 3))
        for i in range(len(hg_te)):
            probs[i] = predict_3way_from_lambdas(float(lh[i]), float(la[i]), rho)
        return probs

    mle_probs = predict_all(mle_theta)
    mcmc_probs = predict_all(posterior_mean)
    market_p = market_probs(test_clean["psh"].values, test_clean["psd"].values, test_clean["psa"].values)

    mle_ll = log_loss_3way(mle_probs, outcomes_te)
    mcmc_ll = log_loss_3way(mcmc_probs, outcomes_te)
    market_ll = log_loss_3way(market_p, outcomes_te)
    uniform_ll = float(np.log(3.0))

    # ----- Diagnostics -----
    # ESS + R-hat on the ROW with the lowest ESS (worst-converged param)
    ess_per_param = [effective_sample_size(mcmc_chains[:, :, p]) for p in range(dims.n_params)]
    rhat_per_param = [r_hat(mcmc_chains[:, :, p]) for p in range(dims.n_params)]
    rho_idx = dims.n_params - 1  # last param
    home_adv_idx = 0

    return {
        "n_train": len(train),
        "n_test": len(test_clean),
        "n_test_dropped": len(test) - len(test_clean),
        "n_teams": dims.n_teams,
        "n_params": dims.n_params,
        "n_chains": mcmc_chains.shape[0],
        "n_samples_per_chain": mcmc_chains.shape[1],
        "mle_time_s": mle_time,
        "mcmc_time_s": mcmc_time,
        "mcmc_time_ratio": mcmc_time / max(mle_time, 1e-6),
        "uniform_ll": uniform_ll,
        "market_ll": market_ll,
        "mle_ll": mle_ll,
        "mcmc_ll": mcmc_ll,
        "delta_mcmc_mle": mcmc_ll - mle_ll,
        "delta_mcmc_market": mcmc_ll - market_ll,
        "delta_mle_market": mle_ll - market_ll,
        "min_ess": min(ess_per_param),
        "median_ess": float(np.median(ess_per_param)),
        "max_rhat": max(rhat_per_param),
        "median_rhat": float(np.median(rhat_per_param)),
        "ess_home_adv": ess_per_param[home_adv_idx],
        "ess_rho": ess_per_param[rho_idx],
        "rhat_home_adv": rhat_per_param[home_adv_idx],
        "rhat_rho": rhat_per_param[rho_idx],
        "posterior_home_adv": float(posterior_mean[home_adv_idx]),
        "posterior_rho": float(posterior_mean[rho_idx]),
        "mle_home_adv": float(mle_theta[home_adv_idx]),
        "mle_rho": float(mle_theta[rho_idx]),
    }


def render_report(result: dict) -> str:
    """Write the human-readable verdict."""
    r = result
    # Verdict logic: tier the convergence quality, then layer the log-loss
    # comparison on top.
    full_converged    = (r["max_rhat"] < 1.05) and (r["min_ess"] > 100)
    borderline_conv   = (r["max_rhat"] < 1.10) and (r["min_ess"] > 100)
    convergence_label = (
        "fully converged"  if full_converged
        else "borderline-converged (acceptable for exploration; not production)"
        if borderline_conv
        else "NOT converged"
    )
    if not borderline_conv:
        verdict = "🟡 INCONCLUSIVE — MCMC did not converge. R-hat / ESS thresholds failed."
    elif r["mcmc_ll"] < r["mle_ll"] - 0.005:
        if full_converged:
            verdict = "🟢 MCMC WINS — log-loss improved ≥ 5 milli-pts AND chains fully converged."
        else:
            verdict = "🟡 MCMC SUGGESTIVE — log-loss improved ≥ 5 milli-pts, but R-hat in [1.05, 1.10]. Confirm with NUTS before production."
    elif r["mcmc_ll"] > r["mle_ll"] + 0.005:
        verdict = "🔴 MCMC LOSES — DC MLE is better. Stay on production."
    else:
        verdict = "⚪ TIE — MCMC matches DC MLE within noise. Stay on DC; revisit only when uncertainty quantification is needed."

    full_converged    = (r["max_rhat"] < 1.05) and (r["min_ess"] > 100)
    borderline_conv   = (r["max_rhat"] < 1.10) and (r["min_ess"] > 100)
    md = f"""# V11 Phase 0 #5 — MCMC vs DC MLE Comparison

> Generated by `notebooks/v11_phase0_mcmc_exploration.py`
>
> Question: should we replace the current Dixon-Coles MLE backbone with a
> hierarchical Bayesian Poisson model (PyMC / NumPyro)?

## Verdict

**{verdict}**

| Metric | Value |
|---|---|
| Train season | EPL 2023-24 ({r['n_train']} matches) |
| Test season  | EPL 2024-25 ({r['n_test']} matches; dropped {r['n_test_dropped']} with promoted teams) |
| Teams (train universe) | {r['n_teams']} |
| Params per fit         | {r['n_params']} |

## Out-of-sample log-loss

Lower is better. Uniform baseline = `log(3) ≈ 1.0986`. Pinnacle market is
the ceiling.

| Model        | Log-loss | Δ vs market | Δ vs MLE |
|---|---:|---:|---:|
| Uniform      | {r['uniform_ll']:.4f} | {r['uniform_ll'] - r['market_ll']:+.4f} | — |
| Pinnacle     | {r['market_ll']:.4f} | 0.0000 | — |
| **DC MLE**   | **{r['mle_ll']:.4f}** | {r['delta_mle_market']:+.4f} | 0.0000 |
| **MCMC mean** | **{r['mcmc_ll']:.4f}** | {r['delta_mcmc_market']:+.4f} | {r['delta_mcmc_mle']:+.4f} |

## Convergence diagnostics

Status: **{convergence_label}**

| Metric | Value | Strict threshold | Exploration threshold |
|---|---:|---|---|
| Median R-hat       | {r['median_rhat']:.4f} | < 1.05 | < 1.10 |
| Max R-hat          | {r['max_rhat']:.4f} | < 1.05 | < 1.10 |
| Median ESS         | {r['median_ess']:.0f}   | > 100  | > 100 |
| Min ESS            | {r['min_ess']:.0f}   | > 100  | > 100 |
| ESS / R-hat (home_adv) | {r['ess_home_adv']:.0f} / {r['rhat_home_adv']:.3f} | per-param | |
| ESS / R-hat (rho)      | {r['ess_rho']:.0f} / {r['rhat_rho']:.3f} | per-param | |

## Parameter agreement

| Param        | DC MLE  | MCMC mean |
|---|---:|---:|
| home advantage | {r['mle_home_adv']:.4f} | {r['posterior_home_adv']:.4f} |
| ρ (DC low-score corr.) | {r['mle_rho']:.4f} | {r['posterior_rho']:.4f} |

## Compute cost

| Operation | Time | Ratio |
|---|---:|---:|
| DC MLE fit | {r['mle_time_s']:.2f} s | 1.0× |
| MCMC ({r['n_chains']} chains × {r['n_samples_per_chain']} samples) | {r['mcmc_time_s']:.2f} s | {r['mcmc_time_ratio']:.1f}× |

## Recommendation

{_recommendation_paragraph(r, full_converged, borderline_conv)}
"""
    return md


def _recommendation_paragraph(r: dict, full_converged: bool, borderline_conv: bool) -> str:
    delta = r["delta_mcmc_mle"]
    if not borderline_conv:
        return (
            "Run did not converge (R-hat ≥ 1.10 OR ESS < 100). "
            "Before any further interpretation, raise iterations to ≥ 30k, "
            "tighten the proposal scale for under-converged params, or "
            "switch to a NUTS sampler (NumPyro). The numbers above should "
            "be treated as preliminary."
        )
    rhat_caveat = (
        ""
        if full_converged
        else " (R-hat in [1.05, 1.10] — borderline, confirm with NUTS before any "
        "production decision)"
    )
    if abs(delta) < 0.002:
        return (
            "MCMC and DC MLE produce indistinguishable predictive log-loss "
            "(|Δ| < 0.002). The Bayesian framework offers posterior "
            "uncertainty intervals, but we don't currently surface those "
            "anywhere in the production stack. **Recommendation: stay on "
            "DC MLE.** Revisit MCMC only if/when we add a feature that "
            "consumes parameter uncertainty (e.g. predictive interval "
            "bands on individual match probabilities, or fixture-level "
            "Kelly sizing with a wider confidence haircut)." + rhat_caveat
        )
    if delta < -0.005:
        return (
            "MCMC posterior mean predictions outperformed DC MLE by ≥ 5 "
            "milli-log-loss points on this single season" + rhat_caveat + ". "
            "This is a candidate for production migration, but the delta "
            "is small enough to be noise on one season. **Recommendation: "
            "confirm on 2-3 additional held-out seasons (and switch from "
            "hand-rolled MH → NumPyro NUTS for cleaner posterior coverage) "
            "before investing in the PyMC/NumPyro dependency footprint.** "
            "If the gap holds, NumPyro (JAX-accelerated NUTS) would be "
            "~10× faster than the MH used here and would push R-hat well "
            "below 1.05 in the same wall-clock budget."
        )
    if delta > 0.005:
        return (
            "MCMC underperformed DC MLE by ≥ 5 milli-log-loss points" + rhat_caveat + ". "
            "Most likely the M-H sampler hasn't fully explored the "
            "posterior at this iteration budget. "
            "**Recommendation: stay on DC MLE.** Re-run with a NUTS sampler "
            "before any future decision; M-H is not the right tool for a "
            "40-dimensional posterior."
        )
    return (
        "Δ ≈ {:+.4f} log-loss — within noise. **Recommendation: stay on "
        "DC MLE** unless posterior uncertainty becomes a product "
        "requirement.".format(delta)
    )


def main() -> int:
    out_path = REPO_ROOT / "docs" / "v11_phase0_mcmc_report.md"
    log.info("Starting comparison…")
    result = run_comparison()
    md = render_report(result)
    out_path.write_text(md, encoding="utf-8")
    log.info("Report written to %s", out_path)
    print()
    print("=" * 60)
    print(f"Verdict: see {out_path}")
    print(f"  DC MLE  log-loss: {result['mle_ll']:.4f}")
    print(f"  MCMC    log-loss: {result['mcmc_ll']:.4f}")
    print(f"  Pinnacle log-loss: {result['market_ll']:.4f}")
    print(f"  Δ MCMC-MLE: {result['delta_mcmc_mle']:+.4f}")
    print(f"  Max R-hat: {result['max_rhat']:.4f}  · Min ESS: {result['min_ess']:.0f}")
    print(f"  Compute: MLE {result['mle_time_s']:.1f}s · MCMC {result['mcmc_time_s']:.1f}s ({result['mcmc_time_ratio']:.1f}×)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
