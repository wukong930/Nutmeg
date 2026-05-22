"""GBM-λ: two lightgbm regressors predicting (lambda_home, lambda_away).

Architecture:
  features (market + Elo + form) → lightgbm regressor → exp() → lambda

Why two separate regressors instead of one multi-output model:
  - Conceptually clear: each predicts its own team's expected goals.
  - Allows symmetry trick at predict time (see swap_view).
  - lightgbm has no multi-output regression natively.

Why Poisson objective:
  - Target is goal count (non-negative integer).
  - Poisson is the natural loss for count data with conditional mean = exp(score).
  - Tweedie is more flexible but harder to tune; Poisson is the standard choice
    for football scores in literature.

Output:
  GbmLambdaModel.predict(feature_df) -> np.ndarray of shape (N, 2)
                                        columns = [lambda_home, lambda_away]

Hyperparameters chosen conservatively (n_estimators not too large, learning_rate
moderate, num_leaves modest) so model is not memorizing 22k training matches.
We use early stopping on a validation subset to be safe.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd


# Sensible defaults for football lambda regression on 5k-20k training samples
DEFAULT_PARAMS = dict(
    objective="poisson",
    metric="poisson",
    learning_rate=0.04,
    num_leaves=31,
    min_data_in_leaf=20,
    feature_fraction=0.85,
    bagging_fraction=0.85,
    bagging_freq=3,
    lambda_l2=1.0,
    verbosity=-1,
    random_state=42,
)
DEFAULT_NUM_BOOST_ROUND = 500
DEFAULT_EARLY_STOPPING_ROUNDS = 30


@dataclass
class GbmLambdaModel:
    """Two trained lightgbm boosters + feature column list."""
    feature_cols: list[str]
    model_home: lgb.Booster
    model_away: lgb.Booster
    train_n: int = 0
    val_n: int = 0
    best_iter_home: int = 0
    best_iter_away: int = 0

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Return (N, 2) array of (lambda_home, lambda_away)."""
        X = df[self.feature_cols].astype(float).values
        lh = self.model_home.predict(X, num_iteration=self.best_iter_home or None)
        la = self.model_away.predict(X, num_iteration=self.best_iter_away or None)
        # Floor lambdas at small positive number for DC compatibility
        lh = np.clip(lh, 0.05, 8.0)
        la = np.clip(la, 0.05, 8.0)
        return np.column_stack([lh, la])


def _make_dataset(df: pd.DataFrame, feature_cols: list[str], target_col: str) -> lgb.Dataset:
    X = df[feature_cols].astype(float).values
    y = df[target_col].astype(float).values
    return lgb.Dataset(X, label=y, feature_name=feature_cols)


def fit_gbm_lambda(
    train: pd.DataFrame,
    val: pd.DataFrame,
    *,
    feature_cols: list[str],
    params: dict | None = None,
    num_boost_round: int = DEFAULT_NUM_BOOST_ROUND,
    early_stopping_rounds: int = DEFAULT_EARLY_STOPPING_ROUNDS,
) -> GbmLambdaModel:
    """Train two Poisson lightgbm regressors on (train, val).

    `train` and `val` must contain `feature_cols` + ['home_goals', 'away_goals'].
    val is used for early stopping ONLY; do not use the test set here.

    Rows with any NaN in feature_cols are dropped (lightgbm handles NaN natively,
    but to keep targets aligned we drop). For coverage on 99% of rows this is fine.
    """
    p = {**DEFAULT_PARAMS, **(params or {})}

    tr = train.dropna(subset=feature_cols + ["home_goals", "away_goals"]).copy()
    va = val.dropna(subset=feature_cols + ["home_goals", "away_goals"]).copy()
    if len(tr) < 100:
        raise ValueError(f"too few clean training rows: {len(tr)}")

    tr_h_ds = _make_dataset(tr, feature_cols, "home_goals")
    tr_a_ds = _make_dataset(tr, feature_cols, "away_goals")

    callbacks = [lgb.log_evaluation(period=0)]
    valid_sets_h = [tr_h_ds]
    valid_sets_a = [tr_a_ds]
    if len(va) >= 30:
        va_h_ds = _make_dataset(va, feature_cols, "home_goals")
        va_a_ds = _make_dataset(va, feature_cols, "away_goals")
        valid_sets_h.append(va_h_ds)
        valid_sets_a.append(va_a_ds)
        callbacks.append(lgb.early_stopping(early_stopping_rounds, verbose=False))

    booster_h = lgb.train(
        p, tr_h_ds, num_boost_round=num_boost_round,
        valid_sets=valid_sets_h, callbacks=callbacks,
    )
    booster_a = lgb.train(
        p, tr_a_ds, num_boost_round=num_boost_round,
        valid_sets=valid_sets_a, callbacks=callbacks,
    )

    return GbmLambdaModel(
        feature_cols=list(feature_cols),
        model_home=booster_h,
        model_away=booster_a,
        train_n=len(tr),
        val_n=len(va),
        best_iter_home=booster_h.best_iteration or 0,
        best_iter_away=booster_a.best_iteration or 0,
    )
