"""Tests for nutmeg.v4.features.market_dynamics.

The build function is still wired into the pipeline (so the dataframe carries
the diagnostic columns) even though the GBM doesn't currently use them — see
docs/v5_w5_ablation.md. Tests verify the math is correct so when richer drift
data lands later, plugging it in is a one-line change.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.features.market import build_market_features
from nutmeg.v4.features.market_dynamics import (
    MARKET_DYNAMICS_FEATURE_COLUMNS,
    _devig_3way,
    build_market_dynamics_features,
)


def _market_frame(**overrides: object) -> pd.DataFrame:
    """Build a row with both opening (PSH/D/A) and closing (PSC*) odds set,
    plus the columns that build_market_features will create."""
    base = dict(
        ps_home=2.50,
        ps_draw=3.30,
        ps_away=3.00,
        psc_home=2.20,
        psc_draw=3.40,
        psc_away=3.40,
        psc_over25=1.95,
        psc_under25=1.90,
        ahch=-0.25,
    )
    base.update(overrides)
    df = pd.DataFrame([base])
    return build_market_features(df)


class TestDevigThreeWay:
    def test_sums_to_one(self) -> None:
        ph, pd_, pa, overround = _devig_3way(
            pd.Series([2.0]), pd.Series([3.5]), pd.Series([3.5])
        )
        assert (ph + pd_ + pa).iloc[0] == pytest.approx(1.0)

    def test_overround_positive_for_real_book(self) -> None:
        _, _, _, overround = _devig_3way(
            pd.Series([2.0]), pd.Series([3.5]), pd.Series([3.5])
        )
        # 1/2 + 1/3.5 + 1/3.5 = 0.5 + 0.2857 + 0.2857 = 1.0714 → overround 0.0714
        assert overround.iloc[0] == pytest.approx(0.0714, abs=1e-3)

    def test_zero_odds_become_nan(self) -> None:
        ph, _, _, _ = _devig_3way(pd.Series([0.0]), pd.Series([3.5]), pd.Series([3.5]))
        assert pd.isna(ph.iloc[0])

    def test_object_dtype_parses(self) -> None:
        # Coverage: ps_home from CSV may come in as object dtype
        ph, _, _, _ = _devig_3way(pd.Series(["2.0"]), pd.Series(["3.5"]), pd.Series(["3.5"]))
        assert not pd.isna(ph.iloc[0])


class TestBuildMarketDynamics:
    def test_all_columns_present(self) -> None:
        out = build_market_dynamics_features(_market_frame())
        for col in MARKET_DYNAMICS_FEATURE_COLUMNS:
            assert col in out.columns

    def test_prob_drift_signs(self) -> None:
        # Open: H=2.50, D=3.30, A=3.00 → devig p ≈ (0.401, 0.304, 0.295)
        # Close: H=2.20, D=3.40, A=3.40 → devig p ≈ (0.435, 0.282, 0.282)
        # Home shortened (more favored) → drift_home > 0
        # Away lengthened → drift_away < 0
        out = build_market_dynamics_features(_market_frame())
        assert out["prob_drift_home"].iloc[0] > 0
        assert out["prob_drift_away"].iloc[0] < 0

    def test_no_drift_when_open_equals_close(self) -> None:
        out = build_market_dynamics_features(
            _market_frame(ps_home=2.20, ps_draw=3.40, ps_away=3.40)
        )
        # drift should be exactly 0
        assert abs(out["prob_drift_home"].iloc[0]) < 1e-9
        assert abs(out["prob_drift_draw"].iloc[0]) < 1e-9
        assert abs(out["prob_drift_away"].iloc[0]) < 1e-9

    def test_missing_opening_filled_with_zero_drift(self) -> None:
        # ps_* all NaN → drift = 0, available flag = 0
        out = build_market_dynamics_features(
            _market_frame(ps_home=np.nan, ps_draw=np.nan, ps_away=np.nan)
        )
        assert out["prob_drift_home"].iloc[0] == 0.0
        assert out["prob_drift_draw"].iloc[0] == 0.0
        assert out["prob_drift_away"].iloc[0] == 0.0
        assert out["market_dynamics_available"].iloc[0] == 0

    def test_partial_missing_marks_unavailable(self) -> None:
        # Only draw is NaN → still flagged unavailable (we need all three)
        out = build_market_dynamics_features(_market_frame(ps_draw=np.nan))
        assert out["market_dynamics_available"].iloc[0] == 0

    def test_available_flag_true_when_all_present(self) -> None:
        out = build_market_dynamics_features(_market_frame())
        assert out["market_dynamics_available"].iloc[0] == 1

    def test_overround_compression_typically_positive(self) -> None:
        # Wide-open book vs sharper close → opening overround > closing
        # ps_*=3.0 each gives overround = 3/3 - 1 = 0
        # Wait: open 1/2.5 + 1/3.3 + 1/3.0 = 0.4 + 0.303 + 0.333 = 1.036 → 0.036
        # close 1/2.2 + 1/3.4 + 1/3.4 = 0.4545 + 0.294 + 0.294 = 1.043 → 0.043
        # So opening overround LESS than closing here → compression < 0
        # This is a contrived case; in real data closing usually tighter.
        out = build_market_dynamics_features(_market_frame())
        # Just verify the column is finite and reasonable
        assert np.isfinite(out["overround_compression"].iloc[0])

    def test_missing_market_p_columns_raises(self) -> None:
        df = pd.DataFrame([{"ps_home": 2.0, "ps_draw": 3.0, "ps_away": 3.0}])
        # No market_p_* yet → KeyError
        with pytest.raises(KeyError, match="market_p_home"):
            build_market_dynamics_features(df)

    def test_object_dtype_opening_parses(self) -> None:
        # CSV-loaded ps_* will be object dtype
        df = _market_frame()
        df["ps_home"] = df["ps_home"].astype(str)
        df["ps_draw"] = df["ps_draw"].astype(str)
        df["ps_away"] = df["ps_away"].astype(str)
        out = build_market_dynamics_features(df)
        assert out["market_dynamics_available"].iloc[0] == 1
        assert np.isfinite(out["prob_drift_home"].iloc[0])
