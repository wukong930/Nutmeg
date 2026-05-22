"""Tests for nutmeg.v4.features.xg_lite."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.features.xg_lite import (
    NON_SOT_WEIGHT,
    SOT_RATIO_PLACEHOLDER,
    SOT_WEIGHT,
    XG_LITE_FEATURE_COLUMNS,
    XG_PLACEHOLDER,
    build_xg_lite_features,
)


def _form_frame(**overrides: object) -> pd.DataFrame:
    """Build a single-row DataFrame with all required form_* columns."""
    base = dict(
        form_home_shots_n=12.0,
        form_home_shots_on_target_n=4.5,
        form_home_shots_against_n=10.0,
        form_home_sot_against_n=3.5,
        form_away_shots_n=11.0,
        form_away_shots_on_target_n=4.0,
        form_away_shots_against_n=13.0,
        form_away_sot_against_n=5.0,
        form_home_goals_for_n=1.4,
        form_away_goals_for_n=1.2,
    )
    base.update(overrides)
    return pd.DataFrame([base])


class TestBuildXgLite:
    def test_all_columns_present(self) -> None:
        out = build_xg_lite_features(_form_frame())
        for col in XG_LITE_FEATURE_COLUMNS:
            assert col in out.columns, f"missing {col}"

    def test_xg_proxy_formula(self) -> None:
        out = build_xg_lite_features(_form_frame())
        # home_for: 0.04*(12 - 4.5) + 0.30*4.5 = 0.04*7.5 + 1.35 = 1.65
        expected = NON_SOT_WEIGHT * (12.0 - 4.5) + SOT_WEIGHT * 4.5
        assert out["xg_lite_home_for_n"].iloc[0] == pytest.approx(expected)

    def test_xg_against_uses_opponent_shots(self) -> None:
        out = build_xg_lite_features(_form_frame())
        # home_against derived from home's shots_against_n / sot_against_n
        # = 0.04*(10 - 3.5) + 0.30*3.5 = 0.26 + 1.05 = 1.31
        expected = NON_SOT_WEIGHT * (10.0 - 3.5) + SOT_WEIGHT * 3.5
        assert out["xg_lite_home_against_n"].iloc[0] == pytest.approx(expected)

    def test_diff_combines_for_and_against(self) -> None:
        out = build_xg_lite_features(_form_frame())
        # diff = (home_for - home_against) - (away_for - away_against)
        # Just verify it equals the formula
        hf = out["xg_lite_home_for_n"].iloc[0]
        ha = out["xg_lite_home_against_n"].iloc[0]
        af = out["xg_lite_away_for_n"].iloc[0]
        aa = out["xg_lite_away_against_n"].iloc[0]
        assert out["xg_lite_diff_n"].iloc[0] == pytest.approx((hf - ha) - (af - aa))

    def test_minus_goals_diff_positive_when_unlucky(self) -> None:
        # xG = 1.65, goals = 1.4 → diff = +0.25 (unlucky)
        out = build_xg_lite_features(_form_frame())
        assert out["xg_lite_home_minus_goals_diff_n"].iloc[0] > 0

    def test_minus_goals_diff_negative_when_overperforming(self) -> None:
        # xG ~1.65, goals=2.5 (very lucky) → diff < 0
        out = build_xg_lite_features(_form_frame(form_home_goals_for_n=2.5))
        assert out["xg_lite_home_minus_goals_diff_n"].iloc[0] < 0

    def test_sot_ratio(self) -> None:
        out = build_xg_lite_features(_form_frame())
        # home: 12 / 4.5 = 2.667
        assert out["shots_to_sot_ratio_home_n"].iloc[0] == pytest.approx(12.0 / 4.5)

    def test_available_flag_true_when_all_inputs_present(self) -> None:
        out = build_xg_lite_features(_form_frame())
        assert out["xg_lite_available"].iloc[0] == 1

    def test_available_flag_false_with_any_nan_input(self) -> None:
        df = _form_frame(form_home_shots_n=np.nan)
        out = build_xg_lite_features(df)
        assert out["xg_lite_available"].iloc[0] == 0

    def test_missing_inputs_use_placeholder(self) -> None:
        """When upstream form_* is NaN, xg_lite_* must be filled with placeholder
        rather than NaN — so rows survive the GBM dropna."""
        df = _form_frame(
            form_home_shots_n=np.nan,
            form_home_shots_on_target_n=np.nan,
            form_home_goals_for_n=np.nan,
        )
        out = build_xg_lite_features(df)
        # All numeric outputs must be non-NaN
        for col in [
            "xg_lite_home_for_n",
            "xg_lite_home_against_n",
            "xg_lite_diff_n",
            "xg_lite_home_minus_goals_diff_n",
            "shots_to_sot_ratio_home_n",
        ]:
            assert not pd.isna(out[col].iloc[0]), f"{col} should be filled, got NaN"
        # And the flag should be 0
        assert out["xg_lite_available"].iloc[0] == 0
        # And the home_for xG should equal the placeholder
        assert out["xg_lite_home_for_n"].iloc[0] == pytest.approx(XG_PLACEHOLDER)

    def test_sot_ratio_uses_placeholder_when_zero_shots(self) -> None:
        # shots=0 → undefined ratio → fill placeholder
        out = build_xg_lite_features(_form_frame(form_home_shots_n=0.0))
        assert out["shots_to_sot_ratio_home_n"].iloc[0] == pytest.approx(SOT_RATIO_PLACEHOLDER)

    def test_missing_required_columns_raises(self) -> None:
        df = pd.DataFrame([{"form_home_shots_n": 10.0}])  # missing many
        with pytest.raises(KeyError, match="missing"):
            build_xg_lite_features(df)
