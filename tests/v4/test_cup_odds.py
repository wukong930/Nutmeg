"""Tests for V7 W8 cup_odds module + nutmeg-ingest-cup-odds CLI.

Three layers:
  1. data.cup_odds — normalize_odds_envelope, parquet roundtrip,
     multi-season concat, merge_cup_fixtures_and_odds
  2. cli.ingest_cup_odds — CLI parsing, non-cup rejection, mocked
     end-to-end path
  3. Integration with V7 W6 cup_history parquets — the join shape that
     V7 W7's build_feature_frame consumes
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from nutmeg.v4.cli import ingest_cup_odds as ingest_cup_odds_cli
from nutmeg.v4.cli.ingest_cup_odds import main as cli_main
from nutmeg.v4.data import cup_odds as cup_odds_mod
from nutmeg.v4.data.cup_history import (
    cup_history_parquet_path,
    normalize_fixture as normalize_cup_fixture,
    write_cup_history_parquet,
)
from nutmeg.v4.data.cup_odds import (
    CUP_ODDS_COLUMNS,
    cup_odds_parquet_path,
    load_cup_odds_parquet,
    load_multi_season_cup_odds,
    merge_cup_fixtures_and_odds,
    normalize_odds_envelope,
    write_cup_odds_parquet,
)
from nutmeg.v4.data.odds_parser import (
    BET365_BOOKMAKER_ID,
    BET_MATCH_WINNER,
    PINNACLE_BOOKMAKER_ID,
)


# ---------- Envelope builders (copied from test_ingest_odds for isolation) ----

def _odds_envelope(
    *,
    fixture_id: int = 999,
    h: str = "2.10", d: str = "3.40", a: str = "3.50",
    over: str | None = "2.05",
    under: str | None = "1.80",
    book_id: int = PINNACLE_BOOKMAKER_ID,
) -> dict:
    bets = [{
        "id": BET_MATCH_WINNER,
        "name": "Match Winner",
        "values": [
            {"value": "Home", "odd": h},
            {"value": "Draw", "odd": d},
            {"value": "Away", "odd": a},
        ],
    }]
    if over is not None and under is not None:
        bets.append({
            "id": 5,
            "name": "Goals Over/Under",
            "values": [
                {"value": "Over 2.5", "odd": over},
                {"value": "Under 2.5", "odd": under},
            ],
        })
    return {
        "fixture": {"id": fixture_id, "date": "2024-11-05T20:00:00+00:00"},
        "league": {"id": 2, "season": 2024},
        "bookmakers": [{"id": book_id, "name": "Test", "bets": bets}],
    }


def _api_fixture(*, fid: int, home: str = "Real Madrid", away: str = "Bayern Munich"):
    return {
        "fixture": {
            "id": fid,
            "date": "2024-11-05T20:00:00+00:00",
            "status": {"short": "FT", "long": "FT"},
        },
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "goals": {"home": 2, "away": 1},
        "league": {"id": 2, "round": "Round of 16"},
    }


# ---------- normalize_odds_envelope ----------------------------------

class TestNormalizeOddsEnvelope:
    def test_full_payload(self):
        row = normalize_odds_envelope(
            _odds_envelope(), fixture_id=999, league_code="UCL", season=2024,
        )
        assert row == {
            "api_football_id": 999,
            "league": "UCL",
            "season": 2024,
            "bookmaker_id": PINNACLE_BOOKMAKER_ID,
            "psc_home": 2.10,
            "psc_draw": 3.40,
            "psc_away": 3.50,
            "psc_over25": 2.05,
            "psc_under25": 1.80,
        }

    def test_no_envelope_returns_none(self):
        assert normalize_odds_envelope(None, 1, "UCL", 2024) is None

    def test_missing_book_returns_none(self):
        env = _odds_envelope(book_id=BET365_BOOKMAKER_ID)
        # Requesting Pinnacle on a Bet365-only envelope → None
        row = normalize_odds_envelope(env, 999, "UCL", 2024,
                                       bookmaker_id=PINNACLE_BOOKMAKER_ID)
        assert row is None

    def test_no_ou_still_keeps_row_with_nones(self):
        env = _odds_envelope(over=None, under=None)
        row = normalize_odds_envelope(env, 1, "UCL", 2024)
        assert row is not None
        assert row["psc_home"] == 2.10
        assert row["psc_over25"] is None
        assert row["psc_under25"] is None

    def test_custom_bookmaker_id_recorded(self):
        env = _odds_envelope(book_id=BET365_BOOKMAKER_ID)
        row = normalize_odds_envelope(
            env, 1, "UCL", 2024, bookmaker_id=BET365_BOOKMAKER_ID,
        )
        assert row["bookmaker_id"] == BET365_BOOKMAKER_ID


# ---------- Parquet roundtrip --------------------------------------------

class TestParquetRoundtrip:
    def _rows(self):
        return [
            normalize_odds_envelope(_odds_envelope(fixture_id=100, h="2.10"),
                                     100, "UCL", 2024),
            normalize_odds_envelope(_odds_envelope(fixture_id=101, h="1.90"),
                                     101, "UCL", 2024),
        ]

    def test_write_then_load(self, tmp_path):
        rows = self._rows()
        out = tmp_path / "UCL_2024.parquet"
        write_cup_odds_parquet(rows, out)
        df = load_cup_odds_parquet(out)
        assert list(df.columns) == CUP_ODDS_COLUMNS
        assert len(df) == 2
        assert df.iloc[0]["api_football_id"] == 100
        assert df.iloc[0]["psc_home"] == 2.10

    def test_empty_rows_valid_empty_parquet(self, tmp_path):
        out = tmp_path / "empty.parquet"
        write_cup_odds_parquet([], out)
        df = load_cup_odds_parquet(out)
        assert len(df) == 0
        assert list(df.columns) == CUP_ODDS_COLUMNS

    def test_missing_path_load_returns_empty(self, tmp_path):
        df = load_cup_odds_parquet(tmp_path / "nope.parquet")
        assert len(df) == 0

    def test_canonical_filename_mirrors_cup_history(self, tmp_path):
        path = cup_odds_parquet_path(tmp_path, "UCL", 2024)
        assert path.name == "UCL_2024.parquet"


# ---------- Multi-season concat -----------------------------------------

class TestMultiSeasonConcat:
    def test_concat_across_combos(self, tmp_path):
        for league, season, fid in [
            ("UCL", 2023, 1), ("UCL", 2024, 2),
            ("UEL", 2023, 3), ("UEL", 2024, 4),
        ]:
            rows = [normalize_odds_envelope(
                _odds_envelope(fixture_id=fid), fid, league, season,
            )]
            write_cup_odds_parquet(
                rows, cup_odds_parquet_path(tmp_path, league, season),
            )
        df = load_multi_season_cup_odds(
            tmp_path, leagues=["UCL", "UEL"], seasons=[2023, 2024],
        )
        assert len(df) == 4

    def test_missing_combos_skipped(self, tmp_path):
        rows = [normalize_odds_envelope(_odds_envelope(fixture_id=10),
                                         10, "UCL", 2024)]
        write_cup_odds_parquet(rows, cup_odds_parquet_path(tmp_path, "UCL", 2024))
        df = load_multi_season_cup_odds(
            tmp_path, leagues=["UCL", "UEL"], seasons=[2021, 2022, 2023, 2024],
        )
        assert len(df) == 1
        assert df.iloc[0]["league"] == "UCL"

    def test_empty_dir_returns_empty(self, tmp_path):
        df = load_multi_season_cup_odds(
            tmp_path, leagues=["UCL"], seasons=[2024],
        )
        assert len(df) == 0


# ---------- merge_cup_fixtures_and_odds ---------------------------------

class TestMergeFixturesAndOdds:
    def _seed_fixtures(self, tmp_path: Path) -> pd.DataFrame:
        # 3 cup fixtures
        rows = [
            normalize_cup_fixture(_api_fixture(fid=10, home="Real Madrid",
                                               away="Bayern Munich"), "UCL", 2024),
            normalize_cup_fixture(_api_fixture(fid=11, home="Inter",
                                               away="Arsenal"), "UCL", 2024),
            normalize_cup_fixture(_api_fixture(fid=12, home="PSG",
                                               away="Atletico"), "UCL", 2024),
        ]
        path = cup_history_parquet_path(tmp_path / "fix", "UCL", 2024)
        write_cup_history_parquet(rows, path)
        from nutmeg.v4.data.cup_history import load_cup_history_parquet
        return load_cup_history_parquet(path)

    def _seed_odds(self, tmp_path: Path) -> pd.DataFrame:
        # Only fixtures 10 and 11 have Pinnacle quotes
        rows = [
            normalize_odds_envelope(_odds_envelope(fixture_id=10, h="2.10"),
                                     10, "UCL", 2024),
            normalize_odds_envelope(_odds_envelope(fixture_id=11, h="1.85"),
                                     11, "UCL", 2024),
        ]
        path = cup_odds_parquet_path(tmp_path / "odds", "UCL", 2024)
        write_cup_odds_parquet(rows, path)
        return load_cup_odds_parquet(path)

    def test_inner_join_drops_oddless_fixtures(self, tmp_path):
        fixtures = self._seed_fixtures(tmp_path)
        odds = self._seed_odds(tmp_path)
        joined = merge_cup_fixtures_and_odds(fixtures, odds, how="inner")
        # Only 2 of 3 fixtures have odds → inner join keeps 2
        assert len(joined) == 2
        # Both columns from each source survive
        assert "home_team" in joined.columns
        assert "psc_home" in joined.columns
        assert "round_label" in joined.columns

    def test_left_join_keeps_all_fixtures(self, tmp_path):
        fixtures = self._seed_fixtures(tmp_path)
        odds = self._seed_odds(tmp_path)
        joined = merge_cup_fixtures_and_odds(fixtures, odds, how="left")
        assert len(joined) == 3
        psg = joined[joined["home_team"] == "PSG"].iloc[0]
        # PSG fixture has no odds → psc_home is NaN
        assert pd.isna(psg["psc_home"])

    def test_empty_inputs_return_empty(self, tmp_path):
        assert len(merge_cup_fixtures_and_odds(
            pd.DataFrame(), pd.DataFrame(),
        )) == 0
        fixtures = self._seed_fixtures(tmp_path)
        assert len(merge_cup_fixtures_and_odds(
            fixtures, pd.DataFrame(),
        )) == 0


# ---------- CLI ------------------------------------------------------

class TestCLI:
    def _seed_cup_history(self, tmp_path: Path) -> Path:
        """Drop a tiny W6 parquet so the CLI has fixture IDs to query."""
        history_dir = tmp_path / "history"
        rows = [
            normalize_cup_fixture(_api_fixture(fid=100), "UCL", 2024),
            normalize_cup_fixture(_api_fixture(fid=101, home="Inter",
                                                away="Arsenal"), "UCL", 2024),
        ]
        write_cup_history_parquet(
            rows, cup_history_parquet_path(history_dir, "UCL", 2024),
        )
        return history_dir

    def test_non_cup_code_rejected(self, tmp_path):
        rc = cli_main([
            "--leagues", "EPL",
            "--seasons", "2024",
            "--cup-history-dir", str(tmp_path),
            "--out-dir", str(tmp_path / "out"),
            "--quiet",
        ])
        assert rc == 2

    def test_happy_path_writes_parquet(self, tmp_path):
        history_dir = self._seed_cup_history(tmp_path)
        out_dir = tmp_path / "odds"

        def fake_fetch_odds(fixture_id, **kw):
            # Both fixtures have a Pinnacle quote in this test
            return [_odds_envelope(fixture_id=fixture_id)]

        with patch.object(
            ingest_cup_odds_cli.api_football,
            "fetch_odds", side_effect=fake_fetch_odds,
        ):
            rc = cli_main([
                "--leagues", "UCL",
                "--seasons", "2024",
                "--cup-history-dir", str(history_dir),
                "--out-dir", str(out_dir),
                "--throttle-ms", "0",
                "--quiet",
            ])
        assert rc == 0
        out_parquet = out_dir / "UCL_2024.parquet"
        assert out_parquet.exists()
        df = load_cup_odds_parquet(out_parquet)
        assert len(df) == 2  # both fixtures had a quote
        assert {int(x) for x in df["api_football_id"]} == {100, 101}

    def test_skips_fixtures_without_quote(self, tmp_path):
        history_dir = self._seed_cup_history(tmp_path)
        out_dir = tmp_path / "odds"

        def fake_fetch_odds(fixture_id, **kw):
            if fixture_id == 100:
                return [_odds_envelope(fixture_id=fixture_id)]
            # Fixture 101 has only Bet365 — Pinnacle request → skip
            return [_odds_envelope(fixture_id=fixture_id,
                                    book_id=BET365_BOOKMAKER_ID)]

        with patch.object(
            ingest_cup_odds_cli.api_football,
            "fetch_odds", side_effect=fake_fetch_odds,
        ):
            rc = cli_main([
                "--leagues", "UCL",
                "--seasons", "2024",
                "--cup-history-dir", str(history_dir),
                "--out-dir", str(out_dir),
                "--throttle-ms", "0",
                "--quiet",
            ])
        assert rc == 0
        df = load_cup_odds_parquet(out_dir / "UCL_2024.parquet")
        # Only fixture 100 survives
        assert len(df) == 1
        assert int(df.iloc[0]["api_football_id"]) == 100

    def test_missing_w6_parquet_warns_but_succeeds(self, tmp_path):
        """If W6 hasn't been run, we should log + continue, not crash."""
        rc = cli_main([
            "--leagues", "UCL",
            "--seasons", "2024",
            "--cup-history-dir", str(tmp_path / "nope"),
            "--out-dir", str(tmp_path / "odds"),
            "--throttle-ms", "0",
            "--quiet",
        ])
        # Should write an empty parquet and return 0
        assert rc == 0
        out_parquet = tmp_path / "odds" / "UCL_2024.parquet"
        assert out_parquet.exists()
        assert len(load_cup_odds_parquet(out_parquet)) == 0

    def test_multi_combo_writes_separate_files(self, tmp_path):
        history_dir = self._seed_cup_history(tmp_path)
        # Also seed UEL 2024
        rows = [normalize_cup_fixture(_api_fixture(fid=200), "UEL", 2024)]
        write_cup_history_parquet(
            rows, cup_history_parquet_path(history_dir, "UEL", 2024),
        )
        out_dir = tmp_path / "odds"
        with patch.object(
            ingest_cup_odds_cli.api_football, "fetch_odds",
            side_effect=lambda fid, **kw: [_odds_envelope(fixture_id=fid)],
        ):
            rc = cli_main([
                "--leagues", "UCL,UEL",
                "--seasons", "2024",
                "--cup-history-dir", str(history_dir),
                "--out-dir", str(out_dir),
                "--throttle-ms", "0",
                "--quiet",
            ])
        assert rc == 0
        assert (out_dir / "UCL_2024.parquet").exists()
        assert (out_dir / "UEL_2024.parquet").exists()

    def test_empty_seasons_returns_2(self, tmp_path):
        rc = cli_main([
            "--leagues", "UCL",
            "--seasons", "",
            "--out-dir", str(tmp_path),
            "--quiet",
        ])
        assert rc == 2

    def test_unparseable_seasons_returns_2(self, tmp_path):
        rc = cli_main([
            "--leagues", "UCL",
            "--seasons", "twentytwentyfour",
            "--out-dir", str(tmp_path),
            "--quiet",
        ])
        assert rc == 2
