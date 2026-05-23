"""Tests for nutmeg.v4.model.xgb_lambda — XGBoost Poisson base."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.model.xgb_lambda import (
    DEFAULT_PARAMS,
    XgbLambdaModel,
    fit_xgb_lambda,
)


FEATURE_COLS = ["x1", "x2", "x3"]


@pytest.fixture
def synthetic_train_val():
    """A tiny but learnable dataset: lambda_home is a clean linear function of x1+x2,
    lambda_away of x3, plus Poisson noise. ~600 train + 100 val rows."""
    rng = np.random.default_rng(42)
    n_tr, n_va = 600, 100

    def make(n: int) -> pd.DataFrame:
        x1 = rng.uniform(-2, 2, n)
        x2 = rng.uniform(-1, 1, n)
        x3 = rng.uniform(-2, 2, n)
        lam_h = np.exp(0.4 + 0.3 * x1 + 0.2 * x2)
        lam_a = np.exp(0.3 + 0.25 * x3)
        hg = rng.poisson(lam_h)
        ag = rng.poisson(lam_a)
        return pd.DataFrame(
            {"x1": x1, "x2": x2, "x3": x3, "home_goals": hg, "away_goals": ag}
        )

    return make(n_tr), make(n_va)


class TestFitXgbLambda:
    def test_returns_model(self, synthetic_train_val) -> None:
        tr, va = synthetic_train_val
        model = fit_xgb_lambda(tr, va, feature_cols=FEATURE_COLS)
        assert isinstance(model, XgbLambdaModel)
        assert model.feature_cols == FEATURE_COLS
        assert model.train_n > 500
        assert model.val_n >= 30

    def test_raises_when_train_too_small(self, synthetic_train_val) -> None:
        tr, va = synthetic_train_val
        tiny = tr.head(50)
        with pytest.raises(ValueError, match="too few"):
            fit_xgb_lambda(tiny, va, feature_cols=FEATURE_COLS)

    def test_dropna_removes_nan_target_rows(self, synthetic_train_val) -> None:
        tr, va = synthetic_train_val
        bad = tr.copy()
        bad.loc[bad.index[:5], "x1"] = np.nan
        model = fit_xgb_lambda(bad, va, feature_cols=FEATURE_COLS)
        assert model.train_n == len(tr) - 5

    def test_default_params_set(self) -> None:
        # Sanity: defaults are reasonable for ~500-row Poisson
        assert DEFAULT_PARAMS["objective"] == "count:poisson"
        assert DEFAULT_PARAMS["max_depth"] == 4
        assert DEFAULT_PARAMS["reg_lambda"] >= 1.0  # stronger L2 than lightgbm


class TestPredict:
    def test_returns_two_column_array(self, synthetic_train_val) -> None:
        tr, va = synthetic_train_val
        model = fit_xgb_lambda(tr, va, feature_cols=FEATURE_COLS)
        preds = model.predict(va.head(10))
        assert preds.shape == (10, 2)

    def test_lambdas_clipped_to_safe_range(self, synthetic_train_val) -> None:
        tr, va = synthetic_train_val
        model = fit_xgb_lambda(tr, va, feature_cols=FEATURE_COLS)
        preds = model.predict(va)
        assert (preds >= 0.05).all()
        assert (preds <= 8.0).all()

    def test_lambdas_correlate_with_features(self, synthetic_train_val) -> None:
        # Increasing x1 should increase predicted lambda_home (we trained that signal in)
        tr, va = synthetic_train_val
        model = fit_xgb_lambda(tr, va, feature_cols=FEATURE_COLS)
        low_x1 = pd.DataFrame({"x1": [-2.0], "x2": [0.0], "x3": [0.0]})
        high_x1 = pd.DataFrame({"x1": [2.0], "x2": [0.0], "x3": [0.0]})
        lam_low = model.predict(low_x1)[0, 0]
        lam_high = model.predict(high_x1)[0, 0]
        assert lam_high > lam_low
