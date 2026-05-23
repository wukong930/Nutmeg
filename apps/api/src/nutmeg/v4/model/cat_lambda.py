"""CatLambdaModel — CatBoost Poisson regressor for V5 ensemble base.

Mirrors the API of nutmeg.v4.model.gbm_lambda (lightgbm-based). Difference
from the other two bases:

- CatBoost natively handles **categorical features** without one-hot encoding.
  We exploit this by passing the league code (`league` column) as a categorical
  feature; the model can learn league-specific lambda corrections without us
  manually building 13 dummy columns.
- Default depth is 5 (between lightgbm's 6 and xgboost's 4) — again to keep
  the base learners decorrelated.

Output:
    CatLambdaModel.predict(feature_df) -> np.ndarray (N, 2)
                                          columns = [lambda_home, lambda_away]
"""
from __future__ import annotations

from dataclasses import dataclass, field

import catboost as cb
import numpy as np
import pandas as pd


# Sensible defaults — different from xgboost + lightgbm so the bases disagree
DEFAULT_PARAMS = dict(
    loss_function="Poisson",
    eval_metric="Poisson",
    iterations=500,
    learning_rate=0.04,
    depth=5,
    l2_leaf_reg=2.0,
    random_strength=1.0,
    subsample=0.85,
    bootstrap_type="Bernoulli",
    verbose=False,
    allow_writing_files=False,
    random_seed=42,
)
DEFAULT_EARLY_STOPPING_ROUNDS = 30


@dataclass
class CatLambdaModel:
    """Two trained CatBoost regressors + feature column list + cat-feature names."""
    feature_cols: list[str]
    cat_features: list[str]
    model_home: cb.CatBoostRegressor
    model_away: cb.CatBoostRegressor
    train_n: int = 0
    val_n: int = 0
    best_iter_home: int = 0
    best_iter_away: int = 0

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Return (N, 2) array of (lambda_home, lambda_away)."""
        # CatBoost wants categorical columns as string dtype
        X = df[self.feature_cols].copy()
        for c in self.cat_features:
            if c in X.columns:
                X[c] = X[c].astype(str).fillna("UNK")
        # Predict in normal space — CatBoost Poisson by default returns expected
        # count (no exp needed); pred_to_use is mean of distribution.
        lh = self.model_home.predict(X)
        la = self.model_away.predict(X)
        # CatBoost can occasionally output near-zero or negative tiny float;
        # clip to the same safe band the other bases use.
        lh = np.clip(np.asarray(lh, dtype=float), 0.05, 8.0)
        la = np.clip(np.asarray(la, dtype=float), 0.05, 8.0)
        return np.column_stack([lh, la])


def fit_cat_lambda(
    train: pd.DataFrame,
    val: pd.DataFrame,
    *,
    feature_cols: list[str],
    cat_features: list[str] | None = None,
    params: dict | None = None,
    early_stopping_rounds: int = DEFAULT_EARLY_STOPPING_ROUNDS,
) -> CatLambdaModel:
    """Train two CatBoost Poisson regressors on (train, val).

    `cat_features` lists the names of categorical columns IN `feature_cols`
    (default: empty list). `train` and `val` must include `feature_cols` +
    ['home_goals', 'away_goals'].

    Numeric columns may contain NaN (CatBoost handles natively); categorical
    columns are coerced to string and "UNK" fills missing.
    """
    p = {**DEFAULT_PARAMS, **(params or {})}
    cat_features = list(cat_features or [])

    # Don't dropna on cat columns (we fill with "UNK"); only require targets present.
    tr = train.dropna(subset=["home_goals", "away_goals"]).copy()
    va = val.dropna(subset=["home_goals", "away_goals"]).copy()
    if len(tr) < 100:
        raise ValueError(f"too few clean training rows: {len(tr)}")

    def _prep(df: pd.DataFrame) -> pd.DataFrame:
        X = df[feature_cols].copy()
        for c in cat_features:
            if c in X.columns:
                X[c] = X[c].astype(str).fillna("UNK")
        return X

    X_tr = _prep(tr)
    X_va = _prep(va) if len(va) >= 30 else None

    booster_h = cb.CatBoostRegressor(**p)
    booster_a = cb.CatBoostRegressor(**p)

    cat_idx = [feature_cols.index(c) for c in cat_features if c in feature_cols]
    fit_kwargs = dict(cat_features=cat_idx, early_stopping_rounds=early_stopping_rounds)
    if X_va is not None:
        booster_h.fit(X_tr, tr["home_goals"].astype(float), eval_set=(X_va, va["home_goals"].astype(float)), **fit_kwargs)
        booster_a.fit(X_tr, tr["away_goals"].astype(float), eval_set=(X_va, va["away_goals"].astype(float)), **fit_kwargs)
    else:
        booster_h.fit(X_tr, tr["home_goals"].astype(float), cat_features=cat_idx)
        booster_a.fit(X_tr, tr["away_goals"].astype(float), cat_features=cat_idx)

    return CatLambdaModel(
        feature_cols=list(feature_cols),
        cat_features=cat_features,
        model_home=booster_h,
        model_away=booster_a,
        train_n=len(tr),
        val_n=len(va),
        best_iter_home=int(booster_h.get_best_iteration() or 0),
        best_iter_away=int(booster_a.get_best_iteration() or 0),
    )
