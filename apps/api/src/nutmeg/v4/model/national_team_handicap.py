"""V11 post-ship — Path A++ hybrid for WC multi-market recommendation.

Bridges the gap between ``NationalTeamModel`` (which only outputs 1X2
probabilities) and the 竞彩 让球 market (which our domestic CatBoost
handles via DC grid → handicap probs).

Architecture (per the V11 design discussion):

  NationalTeamModel.predict_proba           market 让球 SP
        ↓ (1X2)                                 ↓ (raw odds)
  Pinnacle 1X2 blend (α=0.4 model)          dewedge → market q_HC
        ↓
  Reverse-map 1X2 → (λ_h, λ_a) with         ───────┐
    λ_total prior fixed to WC mean                 │
        ↓                                          │
  DC score_grid + grid_to_handicap_1x2            │
        ↓ (model p_HC)                            │
  bayesian_blend(p_HC_model, q_HC_market, ←──────┘
                 alpha=0.4)
        ↓
  Final 让球 probabilities → EV → Kelly → recommendation

Why this design (over training a Poisson WC model directly):
  - 128 WC training matches is borderline for a Poisson goals-likelihood
    model — too noisy, would overfit
  - The 1X2 → λ reverse map is non-unique BUT 1X2 marginal mostly fixes
    λ_diff = λ_h - λ_a; λ_total is the free parameter, fixing it at the
    WC mean (~2.6) captures most of the variance
  - Market handicap SP is calibrated by Pinnacle's actual money flow —
    using it as a Bayesian prior smooths the reverse-mapping noise

When market handicap SP isn't provided, falls back to pure-model
handicap probs (reverse-map + DC only).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.optimize import minimize_scalar

from nutmeg.v4.model.dixon_coles import (
    grid_to_1x2,
    grid_to_handicap_1x2,
    score_grid,
)


log = logging.getLogger(__name__)


# ============ Constants ===============================================

# WC 2018 + 2022 combined average goals/match was ~2.66. Round down to
# 2.6 as a slightly-conservative default (lower λ_total → fewer blowouts
# → higher draw probs → bigger 让平 weight; safer for handicap inference).
DEFAULT_WC_LAMBDA_TOTAL = 2.6

# Match production DC rho. National-team games show slightly less
# low-score correlation than club football (rosters change, less
# tactical continuity), but -0.10 is in the right neighborhood.
DEFAULT_RHO = -0.10

# Reverse-map search bounds. λ_diff = λ_h - λ_a; |diff| > 1.5 means
# one team scores 3x the other — rare in WC.
LAMBDA_DIFF_BOUNDS = (-1.5, 1.5)

# Match wc_predict.DEFAULT_BLEND_ALPHA for the handicap blend.
DEFAULT_HC_BLEND_ALPHA = 0.4


# ============ Reverse mapping: 1X2 → (λ_h, λ_a) =======================

def lambdas_from_1x2(
    p_h: float,
    p_d: float,
    p_a: float,
    *,
    lambda_total_prior: float = DEFAULT_WC_LAMBDA_TOTAL,
    rho: float = DEFAULT_RHO,
    max_goals: int = 10,
) -> tuple[float, float]:
    """Find (λ_h, λ_a) such that DC grid → (~p_h, ~p_d, ~p_a).

    Underdetermined system (3 outputs − 1 sum constraint = 2 dof vs
    3 unknowns including rho). We fix:
      - rho at the production default (-0.10)
      - λ_total = λ_h + λ_a at the WC historical mean

    Then solve 1D for λ_diff = λ_h - λ_a by minimizing KL divergence
    between target (p_h, p_d, p_a) and DC-predicted probabilities.

    Returns (λ_h, λ_a) with both > 0 and summing to lambda_total_prior.
    """
    target = np.array([p_h, p_d, p_a], dtype=float)
    target = target / target.sum()  # defensively normalize

    def kl_div(lambda_diff: float) -> float:
        lh = (lambda_total_prior + lambda_diff) / 2.0
        la = (lambda_total_prior - lambda_diff) / 2.0
        if lh <= 0.05 or la <= 0.05:
            return 1e6
        grid = score_grid(lh, la, rho=rho, max_goals=max_goals)
        pred_h, pred_d, pred_a = grid_to_1x2(grid)
        pred = np.array([pred_h, pred_d, pred_a], dtype=float)
        # KL(target || pred); clip to avoid log(0)
        pred = np.clip(pred, 1e-9, 1.0)
        return float(np.sum(target * np.log(target / pred)))

    res = minimize_scalar(
        kl_div,
        bounds=LAMBDA_DIFF_BOUNDS,
        method="bounded",
        options={"xatol": 1e-4},
    )
    lambda_diff = float(res.x)
    lh = (lambda_total_prior + lambda_diff) / 2.0
    la = (lambda_total_prior - lambda_diff) / 2.0
    return lh, la


# ============ Model-side handicap from 1X2 ============================

def model_handicap_probs(
    p_h: float,
    p_d: float,
    p_a: float,
    handicap_home: int,
    *,
    lambda_total_prior: float = DEFAULT_WC_LAMBDA_TOTAL,
    rho: float = DEFAULT_RHO,
    max_goals: int = 10,
) -> tuple[float, float, float]:
    """End-to-end: 1X2 → λ → DC grid → handicap (让胜/让平/让负) probs.

    Used when we have the model's 1X2 prediction and want the implied
    handicap probability for a given line. Wrap of ``lambdas_from_1x2``
    + ``score_grid`` + ``grid_to_handicap_1x2``.
    """
    lh, la = lambdas_from_1x2(
        p_h, p_d, p_a,
        lambda_total_prior=lambda_total_prior,
        rho=rho,
        max_goals=max_goals,
    )
    grid = score_grid(lh, la, rho=rho, max_goals=max_goals)
    return grid_to_handicap_1x2(grid, handicap_home)


# ============ Market-side dewedge ====================================

def market_handicap_probs(
    odds_h: float,
    odds_d: float,
    odds_a: float,
) -> tuple[float, float, float]:
    """Strip vig from 让球 SP → implied (P让胜, P让平, P让负).

    Standard inverse-and-normalize. Returns NaN tuple if any odds are
    missing / non-positive.
    """
    if not all(o is not None and o > 1.0 for o in (odds_h, odds_d, odds_a)):
        return float("nan"), float("nan"), float("nan")
    inv = np.array([1.0 / odds_h, 1.0 / odds_d, 1.0 / odds_a], dtype=float)
    total = inv.sum()
    if total <= 0:
        return float("nan"), float("nan"), float("nan")
    p = inv / total
    return float(p[0]), float(p[1]), float(p[2])


# ============ Bayesian blend ==========================================

def blend_handicap_probs(
    p_model: tuple[float, float, float],
    p_market: tuple[float, float, float],
    *,
    alpha: float = DEFAULT_HC_BLEND_ALPHA,
) -> tuple[float, float, float]:
    """Convex combine model + market 让球 probs.

    ``alpha`` is the MODEL weight; 1 - alpha is market weight. Default
    0.4 matches the WC 1X2 blend convention (small training set →
    weigh market higher).

    When market probs contain NaN (no SP provided), returns the model
    probs unchanged.
    """
    m = np.asarray(p_model, dtype=float)
    q = np.asarray(p_market, dtype=float)
    if np.isnan(q).any():
        return float(m[0]), float(m[1]), float(m[2])
    final = alpha * m + (1.0 - alpha) * q
    final = final / final.sum()  # defensively normalize
    return float(final[0]), float(final[1]), float(final[2])


# ============ Container =============================================

@dataclass
class HandicapRecommendation:
    """One WC fixture's combined handicap analysis. The 3 outcomes
    have independent EV / Kelly numbers — the caller picks which (if any)
    to stake on based on the EV gate."""
    handicap_home: int
    # Source-of-truth probability triples
    p_model_hc: tuple[float, float, float]    # from 1X2 → λ → DC
    p_market_hc: tuple[float, float, float]   # dewedged SP
    p_final_hc: tuple[float, float, float]    # blended (or model fallback)
    # Per-outcome economics (against the user-provided SP odds)
    odds_hc: tuple[float, float, float]
    ev_per_unit: tuple[float, float, float]   # P(outcome) * odds - 1
    kelly_fraction: tuple[float, float, float]  # full Kelly per outcome
    # Diagnostics
    inferred_lambda_home: float
    inferred_lambda_away: float


def evaluate_handicap_market(
    p_h: float, p_d: float, p_a: float,                 # blended 1X2 (from wc_predict)
    handicap_home: int,
    odds_handicap_H: float, odds_handicap_D: float, odds_handicap_A: float,
    *,
    blend_alpha: float = DEFAULT_HC_BLEND_ALPHA,
    lambda_total_prior: float = DEFAULT_WC_LAMBDA_TOTAL,
    rho: float = DEFAULT_RHO,
) -> HandicapRecommendation:
    """One-stop: take 1X2 + handicap SP → blended handicap probs +
    EV + Kelly per outcome.

    Returns a HandicapRecommendation dataclass with everything the
    recommendation engine needs to size + filter bets.
    """
    # 1. Reverse-map 1X2 → λ
    lh, la = lambdas_from_1x2(
        p_h, p_d, p_a,
        lambda_total_prior=lambda_total_prior, rho=rho,
    )
    # 2. Model handicap from DC grid
    grid = score_grid(lh, la, rho=rho)
    p_model = grid_to_handicap_1x2(grid, handicap_home)
    # 3. Market handicap from SP
    p_market = market_handicap_probs(
        odds_handicap_H, odds_handicap_D, odds_handicap_A,
    )
    # 4. Bayesian blend
    p_final = blend_handicap_probs(p_model, p_market, alpha=blend_alpha)
    # 5. EV + Kelly per outcome (let, drew, lost - against the handicap)
    odds = (odds_handicap_H, odds_handicap_D, odds_handicap_A)
    evs = tuple(p_final[i] * odds[i] - 1.0 for i in range(3))
    # Kelly: f* = (p * b - q) / b  where b = odds - 1, q = 1 - p
    def _kelly(p: float, o: float) -> float:
        b = o - 1.0
        if b <= 0 or p <= 0 or p >= 1:
            return 0.0
        f = (p * b - (1 - p)) / b
        return max(0.0, f)
    kellys = tuple(_kelly(p_final[i], odds[i]) for i in range(3))
    return HandicapRecommendation(
        handicap_home=handicap_home,
        p_model_hc=p_model,
        p_market_hc=p_market,
        p_final_hc=p_final,
        odds_hc=odds,
        ev_per_unit=evs,
        kelly_fraction=kellys,
        inferred_lambda_home=lh,
        inferred_lambda_away=la,
    )


__all__ = [
    "DEFAULT_WC_LAMBDA_TOTAL",
    "DEFAULT_RHO",
    "DEFAULT_HC_BLEND_ALPHA",
    "lambdas_from_1x2",
    "model_handicap_probs",
    "market_handicap_probs",
    "blend_handicap_probs",
    "HandicapRecommendation",
    "evaluate_handicap_market",
]
