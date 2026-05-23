"""XgbLambdaModel — XGBoost Poisson regressor for V5 ensemble base.

Mirrors the API of nutmeg.v4.model.gbm_lambda (lightgbm-based) so the ensemble
orchestrator can swap in any of the three bases (lightgbm / xgboost / catboost)
through a uniform interface. Differences from lightgbm:

- XGBoost's count:poisson objective expects log-link output by default, so
  predict() returns lambda directly (no exp() needed).
- Default depth is 4 (vs lightgbm's 6) and L2 regularization is stronger,
  to ensure the three base models have meaningfully different decision
  surfaces — otherwise the ensemble stacker just averages near-identical
  predictions.

Output:
    XgbLambdaModel.predict(feature_df) -> np.ndarray (N, 2)
                                          columns = [lambda_home, lambda_away]
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import xgboost as xgb


# Sensible defaults — different from gbm_lambda's so ensemble bases disagree
DEFAULT_PARAMS = dict(
    objective="count:poisson",
    eval_metric="poisson-nloglik",
    eta=0.04,
    max_depth=4,
    min_child_weight=8,
    subsample=0.85,
    colsample_bytree=0.85,
    reg_lambda=3.0,  # stronger L2 than lightgbm (which uses 1.0)
    reg_alpha=0.0,
    verbosity=0,
    seed=42,
    tree_method="hist",
)
DEFAULT_NUM_BOOST_ROUND = 500
DEFAULT_EARLY_STOPPING_ROUNDS = 30


@dataclass
class XgbLambdaModel:
    """Two trained XGBoost boosters + feature column list."""
    feature_cols: list[str]
    model_home: xgb.Booster
    model_away: xgb.Booster
    train_n: int = 0
    val_n: int = 0
    best_iter_home: int = 0
    best_iter_away: int = 0

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Return (N, 2) array of (lambda_home, lambda_away)."""
        X = df[self.feature_cols].astype(float).values
        d = xgb.DMatrix(X, feature_names=self.feature_cols)
        lh = self.model_home.predict(d, iteration_range=(0, (self.best_iter_home or 0) + 1))
        la = self.model_away.predict(d, iteration_range=(0, (self.best_iter_away or 0) + 1))
        # XGBoost count:poisson returns lambda directly (log-link applied internally)
        lh = np.clip(lh, 0.05, 8.0)
        la = np.clip(la, 0.05, 8.0)
        return np.column_stack([lh, la])


def _make_dmatrix(df: pd.DataFrame, feature_cols: list[str], target_col: str) -> xgb.DMatrix:
    X = df[feature_cols].astype(float).values
    y = df[target_col].astype(float).values
    return xgb.DMatrix(X, label=y, feature_names=feature_cols)


def fit_xgb_lambda(
    train: pd.DataFrame,
    val: pd.DataFrame,
    *,
    feature_cols: list[str],
    params: dict | None = None,
    num_boost_round: int = DEFAULT_NUM_BOOST_ROUND,
    early_stopping_rounds: int = DEFAULT_EARLY_STOPPING_ROUNDS,
) -> XgbLambdaModel:
    """Train two XGBoost Poisson regressors on (train, val).

    `train` and `val` must contain `feature_cols` + ['home_goals', 'away_goals'].
    Rows with any NaN in feature_cols are dropped (XGBoost handles NaN natively,
    but we drop for parity with the lightgbm path).
    """
    p = {**DEFAULT_PARAMS, **(params or {})}

    tr = train.dropna(subset=feature_cols + ["home_goals", "away_goals"]).copy()
    va = val.dropna(subset=feature_cols + ["home_goals", "away_goals"]).copy()
    if len(tr) < 100:
        raise ValueError(f"too few clean training rows: {len(tr)}")

    tr_h_dm = _make_dmatrix(tr, feature_cols, "home_goals")
    tr_a_dm = _make_dmatrix(tr, feature_cols, "away_goals")

    use_val = len(va) >= 30
    if use_val:
        va_h_dm = _make_dmatrix(va, feature_cols, "home_goals")
        va_a_dm = _make_dmatrix(va, feature_cols, "away_goals")
        evals_h = [(tr_h_dm, "train"), (va_h_dm, "val")]
        evals_a = [(tr_a_dm, "train"), (va_a_dm, "val")]
        es_kwargs = {"early_stopping_rounds": early_stopping_rounds}
    else:
        evals_h = [(tr_h_dm, "train")]
        evals_a = [(tr_a_dm, "train")]
        es_kwargs = {}

    booster_h = xgb.train(
        p, tr_h_dm, num_boost_round=num_boost_round,
        evals=evals_h, verbose_eval=False, **es_kwargs,
    )
    booster_a = xgb.train(
        p, tr_a_dm, num_boost_round=num_boost_round,
        evals=evals_a, verbose_eval=False, **es_kwargs,
    )

    return XgbLambdaModel(
        feature_cols=list(feature_cols),
        model_home=booster_h,
        model_away=booster_a,
        train_n=len(tr),
        val_n=len(va),
        best_iter_home=booster_h.best_iteration if use_val else 0,
        best_iter_away=booster_a.best_iteration if use_val else 0,
    )
