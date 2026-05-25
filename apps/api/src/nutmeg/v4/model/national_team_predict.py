"""V10 W1 Track B Day 3 — National-team 1X2 predictor for WC / EURO / etc.

Three layers, each independently testable:

  1. `elo_to_1x2_probs(home_elo, away_elo, home_adv=0)` — closed-form
     Elo formula. Parameter-free given the registered elo_to_draw_param.
     Always available; serves as a fallback if the LightGBM doesn't ship.

  2. `NationalTeamModel.fit(df) → .predict_proba(df)` — lightweight
     LightGBM trained on 64-128 historical matches. Features kept
     small to avoid overfitting (4-5 features). Outcome: 1X2.

  3. `bayesian_blend(model_probs, market_probs, alpha=0.6)` — combines
     model output with Pinnacle market prior. Used when the model is
     uncertain (small training set) and Pinnacle is available.

Design rationale (per V10 Q1+Q2 discussion):
  - Domestic CatBoost won't transfer to national teams (V8 W4 + P1#20
    cup ablation both NEGATIVE)
  - Tiny training set (~128 matches) makes heavy models overfit
  - Elo is the dominant signal; market is the strongest available prior
  - Don't pretend we can beat Pinnacle's WC pricing — aim for "close enough"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

# Pure Elo win probability comes from FIFA / chess literature:
#   P(home_win | no draw) = 1 / (1 + 10 ** ((away - home - adv) / 400))
# With draw, we use an empirical wedge — see compute below.

ELO_SCALE = 400.0
DEFAULT_HOME_ADV = 0.0     # international football is mostly neutral venues
# Empirical draw rate at large competitive tournaments: ~22-25% across
# WC / EURO 1990-2022. We use a "draw wedge" param that scales DOWN
# the win-or-loss probability mass by this fraction (split equally
# between home/away if Elo difference is 0; weighted toward the
# stronger side as |Elo diff| grows — strong teams draw less).
TOURNAMENT_DRAW_RATE_BASE = 0.24
DRAW_FALLOFF = 0.0005   # per Elo-diff unit, draw rate drops by ~0.0005


def elo_to_1x2_probs(
    home_elo: float,
    away_elo: float,
    home_adv: float = DEFAULT_HOME_ADV,
    base_draw_rate: float = TOURNAMENT_DRAW_RATE_BASE,
    draw_falloff: float = DRAW_FALLOFF,
) -> tuple[float, float, float]:
    """Closed-form 1X2 from Elo. Returns (p_home, p_draw, p_away).

    Method:
      1. Compute "no-draw" win probability via Elo formula:
         p_home_nd = 1 / (1 + 10 ** ((away - home - adv) / 400))
      2. Compute expected draw rate, declining with |Elo diff|:
         p_draw = max(0.05, base_draw_rate - draw_falloff * |elo_diff|)
      3. Allocate remaining probability mass to home/away by p_home_nd
    """
    elo_diff = home_elo - away_elo + home_adv
    p_home_nd = 1.0 / (1.0 + 10.0 ** (-elo_diff / ELO_SCALE))
    p_draw = max(0.05, base_draw_rate - draw_falloff * abs(elo_diff))
    p_home = (1.0 - p_draw) * p_home_nd
    p_away = (1.0 - p_draw) * (1.0 - p_home_nd)
    # Normalize (should already sum to 1, but defensive)
    s = p_home + p_draw + p_away
    return (p_home / s, p_draw / s, p_away / s)


def elo_predict_frame(df: pd.DataFrame, home_adv_col: str | None = None) -> np.ndarray:
    """Vectorized elo_to_1x2_probs over a DataFrame.

    Returns an (N, 3) array of [p_home, p_draw, p_away].
    Rows missing either Elo get an equal-thirds default (1/3, 1/3, 1/3).
    """
    out = np.full((len(df), 3), 1.0 / 3.0)
    for i, row in enumerate(df.itertuples(index=False)):
        he = getattr(row, "home_elo", None)
        ae = getattr(row, "away_elo", None)
        if he is None or ae is None or pd.isna(he) or pd.isna(ae):
            continue
        adv = 0.0
        if home_adv_col is not None and hasattr(row, home_adv_col):
            v = getattr(row, home_adv_col)
            if v is not None and not pd.isna(v):
                adv = float(v)
        out[i] = elo_to_1x2_probs(float(he), float(ae), home_adv=adv)
    return out


@dataclass
class NationalTeamModel:
    """Lightweight LightGBM stacked on top of Elo + market features.

    Training is `fit(df, outcomes)` where df has columns:
      - home_elo, away_elo (required for elo_diff feature)
      - elo_diff (optional; derived if missing)
      - psc_home / psc_draw / psc_away (optional market features)
    outcomes is a vector of 0=home, 1=draw, 2=away.

    Inference is `predict_proba(df)` → (N, 3) probability matrix.

    Falls back to closed-form Elo predict if LightGBM isn't fitted yet
    or if a row is missing critical features.
    """
    booster: Any = None
    feature_cols: list[str] | None = None
    home_adv_per_team: dict[str, float] | None = None

    def fit(
        self,
        df: pd.DataFrame,
        outcomes: np.ndarray,
        *,
        host_country: str | None = None,
        host_advantage: float = 50.0,
    ) -> "NationalTeamModel":
        """Train LightGBM multiclass on the provided fixtures."""
        import lightgbm as lgb

        # Build feature frame
        X = self._build_features(df, host_country=host_country, host_advantage=host_advantage)
        y = outcomes

        # Lightweight + regularized — small training set forces tiny trees
        params = {
            "objective": "multiclass",
            "num_class": 3,
            "num_leaves": 8,
            "max_depth": 3,
            "min_data_in_leaf": 5,
            "learning_rate": 0.05,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.9,
            "bagging_freq": 1,
            "lambda_l2": 1.0,
            "verbose": -1,
        }
        dataset = lgb.Dataset(X, label=y)
        self.booster = lgb.train(params, dataset, num_boost_round=30)
        self.feature_cols = list(X.columns)
        if host_country is not None:
            self.home_adv_per_team = {host_country: host_advantage}
        return self

    def _build_features(
        self,
        df: pd.DataFrame,
        *,
        host_country: str | None = None,
        host_advantage: float = 50.0,
    ) -> pd.DataFrame:
        """Extract a small, regularization-friendly feature set."""
        feats = pd.DataFrame(index=df.index)
        # 1. elo_diff (signed)
        feats["elo_diff"] = (df["home_elo"] - df["away_elo"]).fillna(0.0)
        # 2. elo_sum (high vs high tend to draw more)
        feats["elo_sum"] = (df["home_elo"] + df["away_elo"]).fillna(3500.0)
        # 3. host advantage indicator
        if host_country is not None:
            feats["home_adv"] = df["home_team"].apply(
                lambda t: host_advantage if t == host_country else 0.0
            )
        else:
            feats["home_adv"] = 0.0
        # 4. log-implied market probabilities (only when odds present).
        # WC 2018 + earlier seasons have no Odds API coverage; rows are
        # all NA. Fall back to log(1/3) (= "no market signal") so the
        # LightGBM treats them uniformly.
        for col, name in [
            ("psc_home", "log_pin_home"),
            ("psc_draw", "log_pin_draw"),
            ("psc_away", "log_pin_away"),
        ]:
            if col in df.columns:
                # Coerce <NA> / None / Decimal → float, treat 0 or NA as missing
                series = pd.to_numeric(df[col], errors="coerce")
                inv = series.rdiv(1.0)  # 1.0 / series, safe with NaN
                feats[name] = np.log(
                    inv.where((inv.notna()) & (inv > 0), 1.0 / 3.0)
                )
            else:
                feats[name] = np.log(1.0 / 3.0)
        return feats

    def predict_proba(
        self,
        df: pd.DataFrame,
        *,
        host_country: str | None = None,
        host_advantage: float = 50.0,
    ) -> np.ndarray:
        """Predict 1X2 probabilities."""
        if self.booster is None:
            # Not fitted — fall back to pure Elo
            return elo_predict_frame(df)
        X = self._build_features(
            df, host_country=host_country, host_advantage=host_advantage,
        )
        # Ensure feature column order matches training
        if self.feature_cols:
            for c in self.feature_cols:
                if c not in X.columns:
                    X[c] = 0.0
            X = X[self.feature_cols]
        proba = self.booster.predict(X)
        return proba


def bayesian_blend(
    model_probs: np.ndarray,
    market_probs: np.ndarray,
    alpha: float = 0.6,
) -> np.ndarray:
    """Weighted average of model + market.

    alpha=1.0 → all model, alpha=0.0 → all market.
    Default 0.6 leans toward model but uses market as a regularizer.

    Both inputs must be shape (N, 3). Rows where market_probs is all
    NaN fall back to pure model_probs for that row.
    """
    model_probs = np.asarray(model_probs, dtype=float)
    market_probs = np.asarray(market_probs, dtype=float)
    out = np.empty_like(model_probs)
    for i in range(len(model_probs)):
        if np.isnan(market_probs[i]).any():
            out[i] = model_probs[i]
        else:
            out[i] = alpha * model_probs[i] + (1.0 - alpha) * market_probs[i]
            out[i] /= out[i].sum()
    return out


def market_implied_probs(
    psc_home: pd.Series,
    psc_draw: pd.Series,
    psc_away: pd.Series,
) -> np.ndarray:
    """Convert closing odds → vig-removed implied 1X2 probabilities."""
    # Inverse-odds → raw vig'd probs → normalize
    out = np.full((len(psc_home), 3), np.nan)
    for i in range(len(psc_home)):
        h, d, a = psc_home.iloc[i], psc_draw.iloc[i], psc_away.iloc[i]
        if pd.isna(h) or pd.isna(d) or pd.isna(a):
            continue
        inv = np.array([1.0 / h, 1.0 / d, 1.0 / a])
        out[i] = inv / inv.sum()
    return out


def outcomes_from_goals(home_goals: pd.Series, away_goals: pd.Series) -> np.ndarray:
    """Compute 0=H, 1=D, 2=A label vector. NaN for unplayed."""
    out = np.full(len(home_goals), -1, dtype=int)
    for i in range(len(home_goals)):
        hg, ag = home_goals.iloc[i], away_goals.iloc[i]
        if pd.isna(hg) or pd.isna(ag):
            continue
        if hg > ag:
            out[i] = 0
        elif hg < ag:
            out[i] = 2
        else:
            out[i] = 1
    return out


def log_loss_1x2(probs: np.ndarray, outcomes: np.ndarray, eps: float = 1e-9) -> float:
    """Multinomial log-loss for 1X2. Skips rows with outcome=-1 (unplayed)."""
    mask = outcomes >= 0
    probs_m = np.clip(probs[mask], eps, 1.0 - eps)
    outc_m = outcomes[mask]
    n = len(outc_m)
    if n == 0:
        return float("nan")
    ll = -np.mean(np.log(probs_m[np.arange(n), outc_m]))
    return float(ll)


def hit_rate_1x2(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Top-1 accuracy: how often argmax(probs) matches the actual outcome."""
    mask = outcomes >= 0
    if not mask.any():
        return float("nan")
    preds = np.argmax(probs[mask], axis=1)
    return float((preds == outcomes[mask]).mean())


__all__ = [
    "elo_to_1x2_probs",
    "elo_predict_frame",
    "NationalTeamModel",
    "bayesian_blend",
    "market_implied_probs",
    "outcomes_from_goals",
    "log_loss_1x2",
    "hit_rate_1x2",
]
