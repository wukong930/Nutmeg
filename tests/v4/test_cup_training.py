"""Tests for V8 W2 cup_training module.

Three layers:
  1. `_canonicalize_pair` + `_team_pool_from_league_df` — small helpers
  2. `build_cup_training_rows` — end-to-end: seed cup_history + cup_odds
     parquets, run the builder, verify MATCH_COLUMNS shape + pad rules
     + canonicalization drops
  3. `union_league_and_cup` — concat + re-sort semantics
  4. `nutmeg-train --with-cup-data` — argparse acceptance (full train
     covered by test_e2e)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nutmeg.v4.cli.train import main as train_main
from nutmeg.v4.data.cup_history import (
    cup_history_parquet_path,
    normalize_fixture as normalize_cup_fixture,
    write_cup_history_parquet,
)
from nutmeg.v4.data.cup_odds import (
    cup_odds_parquet_path,
    normalize_odds_envelope,
    write_cup_odds_parquet,
)
from nutmeg.v4.data.cup_training import (
    _canonicalize_pair,
    _team_pool_from_league_df,
    build_cup_training_rows,
    union_league_and_cup,
)
from nutmeg.v4.data.odds_parser import BET_MATCH_WINNER, PINNACLE_BOOKMAKER_ID
from nutmeg.v4.data.schema import MATCH_COLUMNS


# ---------- Fixture builders --------------------------------------------

def _league_df():
    """Minimal V4 training-shape DataFrame for canonical pool building."""
    rows = []
    for league, home, away in [
        ("EPL", "Arsenal", "Liverpool"),
        ("EPL", "Man United", "Man City"),
        ("ESP_LA_LIGA", "Real Madrid", "Barcelona"),
        ("ESP_LA_LIGA", "Ath Madrid", "Sociedad"),
        ("GER_BUNDESLIGA", "Bayern Munich", "Dortmund"),
    ]:
        rows.append({"league": league, "home_team": home, "away_team": away})
    return pd.DataFrame(rows)


def _cup_api_fixture(*, fid: int, home: str, away: str,
                     iso_date: str = "2024-11-05T20:00:00+00:00"):
    return {
        "fixture": {
            "id": fid,
            "date": iso_date,
            "status": {"short": "FT", "long": "FT"},
        },
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "goals": {"home": 2, "away": 1},
        "league": {"id": 2, "round": "Round of 16"},
    }


def _cup_odds_envelope(*, fid: int, h: str = "2.10", d: str = "3.40",
                       a: str = "3.50", with_ou: bool = True):
    bets = [{
        "id": BET_MATCH_WINNER, "name": "Match Winner",
        "values": [
            {"value": "Home", "odd": h},
            {"value": "Draw", "odd": d},
            {"value": "Away", "odd": a},
        ],
    }]
    if with_ou:
        bets.append({
            "id": 5, "name": "Goals Over/Under",
            "values": [
                {"value": "Over 2.5", "odd": "2.05"},
                {"value": "Under 2.5", "odd": "1.80"},
            ],
        })
    return {
        "fixture": {"id": fid, "date": "2024-11-05T20:00:00+00:00"},
        "league": {"id": 2, "season": 2024},
        "bookmakers": [{"id": PINNACLE_BOOKMAKER_ID, "name": "Pinnacle",
                        "bets": bets}],
    }


def _seed_cup_dirs(tmp_path, fixtures_and_odds):
    """Write paired W6 + W8 parquets. Returns (history_dir, odds_dir)."""
    hist_dir = tmp_path / "history"
    odds_dir = tmp_path / "odds"
    hist_rows = [normalize_cup_fixture(api_fix, "UCL", 2024)
                 for api_fix, _ in fixtures_and_odds]
    write_cup_history_parquet(
        hist_rows, cup_history_parquet_path(hist_dir, "UCL", 2024),
    )
    odds_rows = []
    for api_fix, env in fixtures_and_odds:
        if env is None:
            continue
        fid = api_fix["fixture"]["id"]
        odds_rows.append(normalize_odds_envelope(env, fid, "UCL", 2024))
    write_cup_odds_parquet(
        odds_rows, cup_odds_parquet_path(odds_dir, "UCL", 2024),
    )
    return hist_dir, odds_dir


# ---------- helpers --------------------------------------------------

class TestTeamPoolFromLeagueDF:
    def test_unions_all_leagues(self):
        pool = _team_pool_from_league_df(_league_df())
        for expected in ("Arsenal", "Real Madrid", "Bayern Munich",
                         "Liverpool", "Man United", "Man City"):
            assert expected in pool

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame({"league": [], "home_team": [], "away_team": []})
        pool = _team_pool_from_league_df(df)
        assert pool == []


class TestCanonicalizePair:
    @pytest.fixture
    def pool(self):
        return _team_pool_from_league_df(_league_df())

    def test_both_resolve_via_alias(self, pool):
        h, a, reason = _canonicalize_pair(
            "Manchester United", "Manchester City", pool,
        )
        assert h == "Man United"
        assert a == "Man City"
        assert reason == ""

    def test_real_madrid_cf_resolves(self, pool):
        h, a, reason = _canonicalize_pair(
            "Real Madrid CF", "Bayern Munich", pool,
        )
        assert h == "Real Madrid"
        assert a == "Bayern Munich"
        assert reason == ""

    def test_one_unresolved(self, pool):
        h, a, reason = _canonicalize_pair("Arsenal", "Random FC", pool)
        assert h == "Arsenal"
        assert a is None
        assert reason == "away_unresolved"

    def test_both_unresolved(self, pool):
        h, a, reason = _canonicalize_pair("Mystery A", "Mystery B", pool)
        assert h is None
        assert a is None
        assert reason == "both_unresolved"


# ---------- build_cup_training_rows ----------------------------------

class TestBuildCupTrainingRows:
    def test_happy_path(self, tmp_path):
        hist_dir, odds_dir = _seed_cup_dirs(tmp_path, [
            (_cup_api_fixture(fid=1, home="Real Madrid CF", away="Bayern Munich"),
             _cup_odds_envelope(fid=1)),
            (_cup_api_fixture(fid=2, home="Manchester United", away="Arsenal"),
             _cup_odds_envelope(fid=2, h="1.80", d="3.40", a="4.20", with_ou=False)),
        ])
        df = build_cup_training_rows(
            hist_dir, odds_dir,
            leagues=["UCL"], seasons=[2024],
            league_team_df=_league_df(),
        )
        # Schema check: every MATCH_COLUMN present
        assert list(df.columns) == MATCH_COLUMNS
        assert len(df) == 2

    def test_canonical_names_applied(self, tmp_path):
        hist_dir, odds_dir = _seed_cup_dirs(tmp_path, [
            (_cup_api_fixture(fid=1, home="Real Madrid CF", away="Manchester United"),
             _cup_odds_envelope(fid=1)),
        ])
        df = build_cup_training_rows(
            hist_dir, odds_dir,
            leagues=["UCL"], seasons=[2024],
            league_team_df=_league_df(),
        )
        # API-Football "Real Madrid CF" + "Manchester United" → V4 canonical
        assert df.iloc[0]["home_team"] == "Real Madrid"
        assert df.iloc[0]["away_team"] == "Man United"

    def test_pad_strategy(self, tmp_path):
        hist_dir, odds_dir = _seed_cup_dirs(tmp_path, [
            (_cup_api_fixture(fid=1, home="Real Madrid CF", away="Bayern Munich"),
             _cup_odds_envelope(fid=1)),
        ])
        df = build_cup_training_rows(
            hist_dir, odds_dir,
            leagues=["UCL"], seasons=[2024],
            league_team_df=_league_df(),
        )
        row = df.iloc[0]
        # Padded NaN columns (shots, corners, cards, ht_goals, ahch)
        for col in ("ht_home_goals", "ht_away_goals", "home_shots", "away_shots",
                    "home_shots_on_target", "away_shots_on_target",
                    "home_corners", "away_corners", "home_yellow", "away_yellow",
                    "home_red", "away_red", "ahch", "pcahh", "pcaha"):
            assert pd.isna(row[col]), f"{col} should be NaN"
        # Pinnacle copied into alt-book proxy cols (sharp fallback)
        assert row["ps_home"] == row["psc_home"]
        assert row["b365c_home"] == row["psc_home"]
        assert row["avgc_home"] == row["psc_home"]
        # O/U from envelope
        assert row["psc_over25"] == 2.05
        assert row["psc_under25"] == 1.80
        # result_1x2 derived (2-1 → H)
        assert row["result_1x2"] == "H"

    def test_ou_missing_padded_nan(self, tmp_path):
        hist_dir, odds_dir = _seed_cup_dirs(tmp_path, [
            (_cup_api_fixture(fid=1, home="Real Madrid CF", away="Bayern Munich"),
             _cup_odds_envelope(fid=1, with_ou=False)),
        ])
        df = build_cup_training_rows(
            hist_dir, odds_dir,
            leagues=["UCL"], seasons=[2024],
            league_team_df=_league_df(),
        )
        row = df.iloc[0]
        assert pd.isna(row["psc_over25"])
        assert pd.isna(row["psc_under25"])

    def test_unresolved_rows_dropped(self, tmp_path):
        hist_dir, odds_dir = _seed_cup_dirs(tmp_path, [
            (_cup_api_fixture(fid=1, home="Real Madrid CF", away="Bayern Munich"),
             _cup_odds_envelope(fid=1)),
            (_cup_api_fixture(fid=2, home="Mystery Club A", away="Mystery Club B"),
             _cup_odds_envelope(fid=2)),
        ])
        df = build_cup_training_rows(
            hist_dir, odds_dir,
            leagues=["UCL"], seasons=[2024],
            league_team_df=_league_df(),
        )
        # Only the resolvable row survives
        assert len(df) == 1
        assert df.iloc[0]["home_team"] == "Real Madrid"

    def test_no_odds_fixture_dropped_via_inner_join(self, tmp_path):
        # 2 fixtures, 1 with odds; inner join drops the oddless one
        api1 = _cup_api_fixture(fid=1, home="Real Madrid CF", away="Bayern Munich")
        api2 = _cup_api_fixture(fid=2, home="Manchester United", away="Arsenal")
        hist_dir, odds_dir = _seed_cup_dirs(tmp_path, [
            (api1, _cup_odds_envelope(fid=1)),
            (api2, None),  # no odds
        ])
        df = build_cup_training_rows(
            hist_dir, odds_dir,
            leagues=["UCL"], seasons=[2024],
            league_team_df=_league_df(),
        )
        assert len(df) == 1
        assert df.iloc[0]["home_team"] == "Real Madrid"

    def test_empty_inputs_returns_empty_schema(self, tmp_path):
        # No parquets seeded at all
        df = build_cup_training_rows(
            tmp_path / "no_hist", tmp_path / "no_odds",
            leagues=["UCL"], seasons=[2024],
            league_team_df=_league_df(),
        )
        assert len(df) == 0
        assert list(df.columns) == MATCH_COLUMNS

    def test_schema_dtypes(self, tmp_path):
        hist_dir, odds_dir = _seed_cup_dirs(tmp_path, [
            (_cup_api_fixture(fid=1, home="Real Madrid CF", away="Bayern Munich"),
             _cup_odds_envelope(fid=1)),
        ])
        df = build_cup_training_rows(
            hist_dir, odds_dir,
            leagues=["UCL"], seasons=[2024],
            league_team_df=_league_df(),
        )
        # date is datetime
        assert pd.api.types.is_datetime64_any_dtype(df["date"])
        # goals are int
        assert df["home_goals"].dtype.kind == "i"
        assert df["away_goals"].dtype.kind == "i"
        # season is int
        assert df["season"].dtype.kind == "i"
        # odds are float
        assert df["psc_home"].dtype.kind == "f"


# ---------- union_league_and_cup -----------------------------------

class TestUnionLeagueAndCup:
    def _league_v4(self):
        # Real V4 schema DataFrame
        return pd.DataFrame([
            {**{c: None for c in MATCH_COLUMNS},
             "league": "EPL", "season": 2024,
             "date": pd.Timestamp("2024-10-05"),
             "home_team": "Arsenal", "away_team": "Liverpool",
             "home_goals": 2, "away_goals": 1, "psc_home": 2.0,
             "psc_draw": 3.0, "psc_away": 4.0},
            {**{c: None for c in MATCH_COLUMNS},
             "league": "EPL", "season": 2024,
             "date": pd.Timestamp("2024-12-10"),
             "home_team": "Chelsea", "away_team": "Spurs",
             "home_goals": 1, "away_goals": 1, "psc_home": 2.5,
             "psc_draw": 3.2, "psc_away": 2.8},
        ])

    def _cup_v4(self):
        # Date intercalated with league dates so sort order matters
        return pd.DataFrame([
            {**{c: None for c in MATCH_COLUMNS},
             "league": "UCL", "season": 2024,
             "date": pd.Timestamp("2024-11-05"),
             "home_team": "Real Madrid", "away_team": "Bayern Munich",
             "home_goals": 2, "away_goals": 1, "psc_home": 1.9,
             "psc_draw": 3.8, "psc_away": 4.0},
        ])

    def test_empty_cup_returns_league_unchanged(self):
        league = self._league_v4()
        out = union_league_and_cup(league, pd.DataFrame())
        assert len(out) == len(league)

    def test_none_cup_returns_league_unchanged(self):
        league = self._league_v4()
        out = union_league_and_cup(league, None)
        assert len(out) == len(league)

    def test_concat_and_sort(self):
        league = self._league_v4()
        cup = self._cup_v4()
        out = union_league_and_cup(league, cup)
        assert len(out) == 3
        # Sorted by date: 2024-10-05 → 2024-11-05 (cup) → 2024-12-10
        dates = list(out["date"])
        assert dates == sorted(dates)
        # Middle row is the cup match
        assert out.iloc[1]["league"] == "UCL"


# ---------- train CLI --with-cup-data argparse -----------------------

class TestTrainWithCupDataArgparse:
    def test_flag_accepted(self):
        rc = train_main([
            "--data", "/nonexistent",
            "--with-cup-data",
            "--cup-leagues", "UCL",
            "--cup-seasons", "2024",
            "--quiet",
        ])
        # Either downstream fail OR success — argparse must accept the flag
        assert rc in (0, 1, 2)

    def test_combined_flags_parse(self):
        rc = train_main([
            "--data", "/nonexistent",
            "--with-cup-data",
            "--with-cup-features",
            "--with-lineups",
            "--quiet",
        ])
        assert rc in (0, 1, 2)

    def test_cup_canonical_fuzzy_accepted(self):
        rc = train_main([
            "--data", "/nonexistent",
            "--with-cup-data",
            "--cup-canonical-fuzzy", "0.90",
            "--quiet",
        ])
        assert rc in (0, 1, 2)
