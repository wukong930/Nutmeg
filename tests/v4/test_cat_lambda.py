"""Tests for nutmeg.v4.model.cat_lambda — CatBoost Poisson base."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.model.cat_lambda import CatLambdaModel, fit_cat_lambda


FEATURE_COLS = ["x1", "x2", "league"]


@pytest.fixture
def synthetic_train_val():
    """Numeric + 1 categorical (league) — CatBoost's distinguishing feature."""
    rng = np.random.default_rng(7)
    n_tr, n_va = 600, 100
    leagues = ["EPL", "ITA_SERIE_A", "GER_BUNDESLIGA"]

    def make(n: int) -> pd.DataFrame:
        x1 = rng.uniform(-2, 2, n)
        x2 = rng.uniform(-1, 1, n)
        lg = rng.choice(leagues, n)
        # League-specific offsets — CatBoost should learn these from the
        # categorical column without explicit one-hot.
        offsets = {"EPL": 0.4, "ITA_SERIE_A": 0.2, "GER_BUNDESLIGA": 0.5}
        lam_h = np.exp([offsets[l] + 0.3 * a + 0.2 * b for l, a, b in zip(lg, x1, x2)])
        lam_a = np.exp(0.3 + 0.1 * x1)
        return pd.DataFrame(
            {
                "x1": x1, "x2": x2, "league": lg,
                "home_goals": rng.poisson(lam_h),
                "away_goals": rng.poisson(lam_a),
            }
        )

    return make(n_tr), make(n_va)


class TestFitCatLambda:
    def test_returns_model_with_cat_features(self, synthetic_train_val) -> None:
        tr, va = synthetic_train_val
        model = fit_cat_lambda(
            tr, va, feature_cols=FEATURE_COLS, cat_features=["league"]
        )
        assert isinstance(model, CatLambdaModel)
        assert model.feature_cols == FEATURE_COLS
        assert model.cat_features == ["league"]
        assert model.train_n > 500

    def test_works_without_cat_features(self, synthetic_train_val) -> None:
        tr, va = synthetic_train_val
        # Drop league entirely
        tr2 = tr.drop(columns=["league"])
        va2 = va.drop(columns=["league"])
        model = fit_cat_lambda(tr2, va2, feature_cols=["x1", "x2"])
        assert model.cat_features == []
        # Predictions still valid
        preds = model.predict(va2.head(5))
        assert preds.shape == (5, 2)

    def test_raises_when_train_too_small(self, synthetic_train_val) -> None:
        tr, va = synthetic_train_val
        with pytest.raises(ValueError, match="too few"):
            fit_cat_lambda(tr.head(50), va, feature_cols=FEATURE_COLS, cat_features=["league"])


class TestPredict:
    def test_returns_two_columns(self, synthetic_train_val) -> None:
        tr, va = synthetic_train_val
        model = fit_cat_lambda(tr, va, feature_cols=FEATURE_COLS, cat_features=["league"])
        preds = model.predict(va.head(10))
        assert preds.shape == (10, 2)

    def test_clipped_to_safe_range(self, synthetic_train_val) -> None:
        tr, va = synthetic_train_val
        model = fit_cat_lambda(tr, va, feature_cols=FEATURE_COLS, cat_features=["league"])
        preds = model.predict(va)
        assert (preds >= 0.05).all() and (preds <= 8.0).all()

    def test_unseen_league_gets_unk(self, synthetic_train_val) -> None:
        tr, va = synthetic_train_val
        model = fit_cat_lambda(tr, va, feature_cols=FEATURE_COLS, cat_features=["league"])
        unseen = pd.DataFrame(
            {"x1": [0.0], "x2": [0.0], "league": ["BRAND_NEW_LEAGUE_XYZ"]}
        )
        preds = model.predict(unseen)
        # Doesn't crash; returns finite lambda
        assert np.isfinite(preds).all()

    def test_categorical_signal_learned(self, synthetic_train_val) -> None:
        # We injected a league offset of +0.5 in GER_BUNDESLIGA vs +0.2 in ITA_SERIE_A
        tr, va = synthetic_train_val
        model = fit_cat_lambda(tr, va, feature_cols=FEATURE_COLS, cat_features=["league"])
        df_de = pd.DataFrame({"x1": [0.0], "x2": [0.0], "league": ["GER_BUNDESLIGA"]})
        df_it = pd.DataFrame({"x1": [0.0], "x2": [0.0], "league": ["ITA_SERIE_A"]})
        lam_de = model.predict(df_de)[0, 0]
        lam_it = model.predict(df_it)[0, 0]
        # GER offset higher → CatBoost should predict higher home goals there
        assert lam_de > lam_it
