"""Tests for nutmeg.v4.eval.baselines."""
import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.eval.baselines import (
    avg_market_baseline, devig_odds, pinnacle_baseline,
    priors_baseline, uniform_baseline,
)


class TestUniform:
    def test_uniform_shape_and_sum(self):
        u = uniform_baseline(10)
        assert u.shape == (10, 3)
        assert u.sum(axis=1) == pytest.approx(np.ones(10), abs=1e-9)
        assert (u == 1/3).all()


class TestDevig:
    def test_sums_to_one(self):
        p = devig_odds([2.0, 1.5, 4.0], [3.5, 4.0, 3.2], [3.8, 6.0, 2.1])
        assert p.shape == (3, 3)
        assert p.sum(axis=1) == pytest.approx(np.ones(3), abs=1e-9)

    def test_known_devig(self):
        # Fair odds 2/4/4 → implied 1/2, 1/4, 1/4 → sum = 1, so already fair
        p = devig_odds([2.0], [4.0], [4.0])
        assert p[0] == pytest.approx([0.5, 0.25, 0.25], abs=1e-9)

    def test_overround_normalised(self):
        # Slight overround case (sum of implied = 1.05)
        p = devig_odds([2.0], [3.5], [4.5])
        # Fair probs are normalized to 1
        assert p.sum(axis=1) == pytest.approx(np.ones(1), abs=1e-9)
        # Home is the biggest
        assert p[0, 0] > p[0, 1]
        assert p[0, 0] > p[0, 2]


class TestPinnacleBaseline:
    def test_extracts_psc_columns(self):
        df = pd.DataFrame({
            "psc_home": [2.0, 1.5],
            "psc_draw": [3.5, 4.0],
            "psc_away": [4.0, 6.0],
        })
        p = pinnacle_baseline(df)
        assert p.shape == (2, 3)
        # First row: implied (0.5, ~0.286, ~0.25) before devig; after devig sums to 1
        assert p[0].sum() == pytest.approx(1.0, abs=1e-9)


class TestPriors:
    def test_uses_train_marginals(self):
        train = pd.DataFrame({"result_1x2": ["H"] * 60 + ["D"] * 20 + ["A"] * 20})
        p = priors_baseline(train, n_test=5)
        assert p.shape == (5, 3)
        # All rows identical (it's a marginal baseline)
        assert (p[0] == p[1]).all()
        assert p[0, 0] == pytest.approx(0.6, abs=1e-9)
        assert p[0, 1] == pytest.approx(0.2, abs=1e-9)
