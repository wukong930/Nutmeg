"""Tests for nutmeg.v4.features.lineup_features (V6 W2)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.features.lineup_features import (
    DEFAULT_COMPACTNESS,
    DEFAULT_XI_MINUTES_SHARE_NO_LINEUP,
    DEFAULT_XI_MINUTES_SHARE_WITH_LINEUP,
    FORMATION_COMPACTNESS,
    LINEUP_FEATURE_COLUMNS,
    _fixture_key,
    build_lineup_features,
    derive_lineup_features_single,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "api_football"


@pytest.fixture
def real_lineups():
    """Hand-curated API-Football lineup payload from tests/v4/fixtures/."""
    return json.loads((FIXTURE_DIR / "lineups_arsenal_liverpool.json").read_text())


@pytest.fixture
def real_injuries():
    return json.loads((FIXTURE_DIR / "injuries_arsenal.json").read_text())


class TestDeriveSingle:
    def test_both_lineups_present(self, real_lineups):
        home, away = real_lineups[0], real_lineups[1]
        feats = derive_lineup_features_single(home, away)
        assert feats["lineup_home_xi_present_flag"] == 1.0
        assert feats["lineup_away_xi_present_flag"] == 1.0
        assert feats["lineup_available"] == 1.0

    def test_formation_compactness_lookup(self, real_lineups):
        # Arsenal: 4-3-3 → compactness 1.0
        # Liverpool: 4-2-3-1 → compactness 1.0
        feats = derive_lineup_features_single(real_lineups[0], real_lineups[1])
        assert feats["lineup_home_formation_compactness"] == FORMATION_COMPACTNESS["4-3-3"]
        assert feats["lineup_away_formation_compactness"] == FORMATION_COMPACTNESS["4-2-3-1"]

    def test_unknown_formation_uses_default(self):
        weird = {"formation": "9-1-0-0"}
        feats = derive_lineup_features_single(weird, weird)
        assert feats["lineup_home_formation_compactness"] == DEFAULT_COMPACTNESS

    def test_missing_lineup_falls_back_to_placeholders(self):
        feats = derive_lineup_features_single(None, None)
        assert feats["lineup_home_xi_present_flag"] == 0.0
        assert feats["lineup_away_xi_present_flag"] == 0.0
        assert feats["lineup_available"] == 0.0
        assert feats["lineup_home_xi_minutes_share"] == DEFAULT_XI_MINUTES_SHARE_NO_LINEUP
        assert feats["lineup_away_xi_minutes_share"] == DEFAULT_XI_MINUTES_SHARE_NO_LINEUP
        # Numeric outputs always finite, never NaN — same pattern as W4 xg_lite
        for k, v in feats.items():
            assert np.isfinite(v), f"{k} should be finite, got {v}"

    def test_one_lineup_missing_partial(self, real_lineups):
        feats = derive_lineup_features_single(real_lineups[0], None)
        assert feats["lineup_home_xi_present_flag"] == 1.0
        assert feats["lineup_away_xi_present_flag"] == 0.0
        assert feats["lineup_available"] == 0.0  # AND of both, not OR
        assert feats["lineup_home_xi_minutes_share"] == DEFAULT_XI_MINUTES_SHARE_WITH_LINEUP
        assert feats["lineup_away_xi_minutes_share"] == DEFAULT_XI_MINUTES_SHARE_NO_LINEUP

    def test_injuries_counted(self, real_lineups, real_injuries):
        home_inj = real_injuries  # 2 records in fixture
        feats = derive_lineup_features_single(
            real_lineups[0], real_lineups[1],
            home_injuries=home_inj,
        )
        assert feats["lineup_home_n_injuries"] == 2.0
        assert feats["lineup_away_n_injuries"] == 0.0  # away_injuries was None → defaults

    def test_explicit_minutes_share_overrides_default(self, real_lineups):
        feats = derive_lineup_features_single(
            real_lineups[0], real_lineups[1],
            home_minutes_share=0.75, away_minutes_share=0.92,
        )
        assert feats["lineup_home_xi_minutes_share"] == 0.75
        assert feats["lineup_away_xi_minutes_share"] == 0.92


class TestBuildLineupFeatures:
    @pytest.fixture
    def df(self):
        return pd.DataFrame([
            {"league": "EPL", "date": pd.Timestamp("2025-05-11"),
             "home_team": "Arsenal", "away_team": "Liverpool"},
            {"league": "EPL", "date": pd.Timestamp("2025-05-11"),
             "home_team": "Man City", "away_team": "Man United"},
        ])

    def test_adds_all_columns(self, df):
        out = build_lineup_features(df)
        for col in LINEUP_FEATURE_COLUMNS:
            assert col in out.columns

    def test_empty_lookup_yields_placeholders_only(self, df):
        out = build_lineup_features(df)
        # No lineup data → all flags 0
        assert (out["lineup_home_xi_present_flag"] == 0.0).all()
        assert (out["lineup_away_xi_present_flag"] == 0.0).all()
        assert (out["lineup_available"] == 0.0).all()
        # But every value is finite (placeholder pattern)
        for col in LINEUP_FEATURE_COLUMNS:
            assert out[col].notna().all()

    def test_lookup_populates_matched_rows(self, df, real_lineups):
        key = _fixture_key(df.iloc[0])
        lookup = {key: (real_lineups[0], real_lineups[1])}
        out = build_lineup_features(df, lookup)
        # Row 0 has lineup → flag=1; row 1 doesn't → flag=0
        assert out["lineup_home_xi_present_flag"].iloc[0] == 1.0
        assert out["lineup_home_xi_present_flag"].iloc[1] == 0.0
        assert out["lineup_available"].iloc[0] == 1.0
        assert out["lineup_available"].iloc[1] == 0.0

    def test_injury_lookup_drives_count(self, df, real_lineups, real_injuries):
        key = _fixture_key(df.iloc[0])
        out = build_lineup_features(
            df,
            lineup_lookup={key: (real_lineups[0], real_lineups[1])},
            injury_lookup={key: (real_injuries, None)},
        )
        assert out["lineup_home_n_injuries"].iloc[0] == 2.0


class TestFixtureKey:
    def test_format(self):
        row = pd.Series({
            "league": "EPL", "date": pd.Timestamp("2025-05-11"),
            "home_team": "Arsenal", "away_team": "Liverpool",
        })
        # itertuples row simulation
        from collections import namedtuple
        Row = namedtuple("Row", ["league", "date", "home_team", "away_team"])
        r = Row("EPL", pd.Timestamp("2025-05-11"), "Arsenal", "Liverpool")
        assert _fixture_key(r) == "EPL__2025-05-11__Arsenal__Liverpool"

    def test_string_date_fallback(self):
        from collections import namedtuple
        Row = namedtuple("Row", ["league", "date", "home_team", "away_team"])
        r = Row("EPL", "2025-05-11T18:00:00", "Arsenal", "Liverpool")
        # str(d)[:10] → "2025-05-11"
        assert _fixture_key(r) == "EPL__2025-05-11__Arsenal__Liverpool"
