"""Tests for post-V8 P1#4 — national-team Elo integration into
   build_elo_features via seed_elo_value's new nation_state path.
"""
from __future__ import annotations

import pandas as pd
import pytest

from nutmeg.v4.features.cross_league_state import seed_elo_value
from nutmeg.v4.features.elo import build_elo_features
from nutmeg.v4.features.pipeline import build_feature_frame


# ---------- seed_elo_value with nation_state ---------------------------

class TestSeedEloValueNationState:
    def test_nation_state_hit_seeds_pool(self):
        state: dict = {}
        nation_state = {"BRA": 1950.0}
        v = seed_elo_value(
            state, "WC", "Brazil", default=1500.0,
            nation_state=nation_state,
            is_national_team_league=True,
        )
        assert v == 1950.0
        # Mutated into pool for subsequent reads
        assert state["WC"]["Brazil"] == 1950.0

    def test_nation_state_alias_resolves(self):
        # "United States" → "USA" via NATION_CLUBELO_CODES alias
        nation_state = {"USA": 1750.0}
        v = seed_elo_value(
            {}, "WC", "United States", default=1500.0,
            nation_state=nation_state,
            is_national_team_league=True,
        )
        assert v == 1750.0

    def test_skipped_when_is_national_team_false(self):
        # nation_state provided but row's league isn't a national-team
        # cup → don't use nation lookup (could mis-resolve "Manchester"
        # to "ENG" for a club row)
        nation_state = {"ENG": 1850.0}
        v = seed_elo_value(
            {}, "UCL", "Manchester", default=1500.0,
            nation_state=nation_state,
            is_national_team_league=False,
        )
        # Should fall through to default — nation_state ignored
        assert v == 1500.0

    def test_skipped_when_nation_state_is_none(self):
        v = seed_elo_value(
            {}, "WC", "Brazil", default=1500.0,
            nation_state=None,
            is_national_team_league=True,
        )
        assert v == 1500.0

    def test_existing_pool_value_kept_over_nation_state(self):
        # If team already has a value in the WC pool, use it (don't re-seed)
        state = {"WC": {"Brazil": 1820.0}}
        nation_state = {"BRA": 1950.0}
        v = seed_elo_value(
            state, "WC", "Brazil", default=1500.0,
            nation_state=nation_state,
            is_national_team_league=True,
        )
        assert v == 1820.0  # pool wins

    def test_nation_state_unknown_team_falls_through(self):
        nation_state = {"BRA": 1950.0}
        v = seed_elo_value(
            {}, "WC", "Vatican City FC", default=1500.0,
            nation_state=nation_state,
            is_national_team_league=True,
        )
        # No alias for "Vatican City FC" → default
        assert v == 1500.0


# ---------- build_elo_features integration -----------------------------

class TestBuildEloWithNationState:
    def _df(self):
        return pd.DataFrame([
            # Pre-WC: Brazil has been seen in WC_QUAL via earlier matches
            # but the WC row is what we test — first time in "WC" league pool
            {"date": pd.Timestamp("2024-08-01"), "league": "EPL",
             "home_team": "Arsenal", "away_team": "Liverpool",
             "home_goals": 2, "away_goals": 1},
            {"date": pd.Timestamp("2024-11-15"), "league": "WC",
             "home_team": "Brazil", "away_team": "Argentina",
             "home_goals": 1, "away_goals": 1},
        ])

    def test_off_path_unchanged_no_nation_state(self):
        # Default behavior: no seeding, no nation_state → WC row sees 1500
        out = build_elo_features(self._df(), cross_league_seed=False)
        wc = out[out.league == "WC"].iloc[0]
        assert wc["elo_home"] == 1500.0
        assert wc["elo_away"] == 1500.0

    def test_nation_state_without_cross_league_seed_no_effect(self):
        # nation_state alone (without cross_league_seed=True) won't fire
        # because the seeding code path is gated on cross_league_seed
        out = build_elo_features(
            self._df(),
            cross_league_seed=False,
            nation_state={"BRA": 1950.0, "ARG": 1990.0},
        )
        wc = out[out.league == "WC"].iloc[0]
        assert wc["elo_home"] == 1500.0  # untouched

    def test_nation_state_with_seed_pulls_real_elo(self):
        out = build_elo_features(
            self._df(),
            cross_league_seed=True,
            nation_state={"BRA": 1950.0, "ARG": 1990.0},
        )
        wc = out[out.league == "WC"].iloc[0]
        assert wc["elo_home"] == 1950.0
        assert wc["elo_away"] == 1990.0

    def test_partial_nation_state_other_falls_back(self):
        # Only Brazil in nation_state; Argentina falls back to default
        out = build_elo_features(
            self._df(),
            cross_league_seed=True,
            nation_state={"BRA": 1950.0},
        )
        wc = out[out.league == "WC"].iloc[0]
        assert wc["elo_home"] == 1950.0
        assert wc["elo_away"] == 1500.0  # ARG not in nation_state


# ---------- build_feature_frame passthrough ----------------------------

class TestBuildFeatureFrameNationState:
    def test_accepts_nation_state_kwarg(self):
        from nutmeg.v4.data.schema import MATCH_COLUMNS
        df = pd.DataFrame([
            {**{c: None for c in MATCH_COLUMNS},
             "date": pd.Timestamp("2024-08-15"),
             "league": "WC", "season": 2024,
             "home_team": "Brazil", "away_team": "Argentina",
             "home_goals": 1, "away_goals": 1,
             "psc_home": 2.5, "psc_draw": 3.0, "psc_away": 2.8,
             "ps_home": 2.5, "ps_draw": 3.0, "ps_away": 2.8,
             "b365c_home": 2.5, "b365c_draw": 3.0, "b365c_away": 2.8,
             "avgc_home": 2.5, "avgc_draw": 3.0, "avgc_away": 2.8,
             "psc_over25": 2.05, "psc_under25": 1.80,
             "result_1x2": "D", "ht_home_goals": 0, "ht_away_goals": 0,
             "home_shots": 10, "away_shots": 8,
             "home_shots_on_target": 4, "away_shots_on_target": 3,
             "home_corners": 5, "away_corners": 4,
             "home_yellow": 1, "away_yellow": 1,
             "home_red": 0, "away_red": 0,
             "ahch": 0.0, "pcahh": 2.0, "pcaha": 1.85},
        ])
        out = build_feature_frame(
            df,
            clubelo_history=pd.DataFrame(),
            cross_league_seed=True,
            nation_state={"BRA": 1950.0, "ARG": 1990.0},
        )
        # Brazil's WC row should pick up nation Elo
        assert out.iloc[0]["elo_home"] == 1950.0
        assert out.iloc[0]["elo_away"] == 1990.0
