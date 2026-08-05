"""Tests for V7 W6 cup_history module + nutmeg-ingest-cup-history CLI.

Three layers:
  1. data.cup_history — normalize_fixture, parquet roundtrip, multi-season concat
  2. data.cup_history — derive_round_flags integration with V6 W11's
     is_knockout_round
  3. cli.ingest_cup_history — argparse + non-cup rejection + mocked API path
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from nutmeg.v4.cli import ingest_cup_history as ingest_cup_history_cli
from nutmeg.v4.cli.ingest_cup_history import main as cli_main
from nutmeg.v4.data import cup_history as cup_history_mod
from nutmeg.v4.data.cup_history import (
    CUP_HISTORY_COLUMNS,
    cup_history_parquet_path,
    derive_round_flags,
    gather_cup_history_for_season,
    load_cup_history_parquet,
    load_multi_season_cup_history,
    normalize_fixture,
    write_cup_history_parquet,
)


# ---------- Fixture builders --------------------------------------------

def _api_fixture(
    *,
    fid: int = 999,
    status: str = "FT",
    iso_date: str = "2024-11-05T20:00:00+00:00",
    home: str = "Real Madrid",
    away: str = "Bayern Munich",
    home_goals: int | None = 2,
    away_goals: int | None = 1,
    round_label: str = "Round of 16",
) -> dict:
    return {
        "fixture": {
            "id": fid,
            "date": iso_date,
            "status": {"short": status, "long": status},
        },
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "goals": {"home": home_goals, "away": away_goals},
        "league": {"id": 2, "round": round_label},
    }


# ---------- normalize_fixture ----------------------------------------

class TestNormalizeFixture:
    def test_full_payload(self):
        row = normalize_fixture(_api_fixture(), "UCL", 2024)
        assert row == {
            "date": "2024-11-05",
            "league": "UCL",
            "home_team": "Real Madrid",
            "away_team": "Bayern Munich",
            "home_goals": 2,
            "away_goals": 1,
            "status_short": "FT",
            "round_label": "Round of 16",
            "api_football_id": 999,
            "season": 2024,
        }

    @pytest.mark.parametrize("status", ["NS", "PST", "CANC", "LIVE", "1H", "HT"])
    def test_non_finished_status_returns_none(self, status):
        row = normalize_fixture(_api_fixture(status=status), "UCL", 2024)
        assert row is None

    def test_aet_status_kept(self):
        row = normalize_fixture(
            _api_fixture(status="AET", home_goals=3, away_goals=3),
            "UCL", 2024,
        )
        assert row is not None
        assert row["status_short"] == "AET"

    def test_pen_status_kept(self):
        row = normalize_fixture(_api_fixture(status="PEN"), "UCL", 2024)
        assert row is not None
        assert row["status_short"] == "PEN"

    def test_missing_goals_returns_none(self):
        row = normalize_fixture(
            _api_fixture(home_goals=None, away_goals=None),
            "UCL", 2024,
        )
        assert row is None

    def test_missing_team_names_returns_none(self):
        fx = _api_fixture()
        fx["teams"] = {"home": {}, "away": {"name": "Bayern"}}
        assert normalize_fixture(fx, "UCL", 2024) is None

    def test_iso_date_truncated(self):
        row = normalize_fixture(
            _api_fixture(iso_date="2024-11-05T22:30:00+09:00"),
            "UCL", 2024,
        )
        assert row["date"] == "2024-11-05"

    def test_missing_round_label_defaults_empty_string(self):
        fx = _api_fixture()
        fx["league"] = {"id": 2}  # no round
        row = normalize_fixture(fx, "UCL", 2024)
        assert row["round_label"] == ""

    def test_season_coerced_to_int(self):
        row = normalize_fixture(_api_fixture(), "UCL", season=2024)
        assert isinstance(row["season"], int)
        assert row["season"] == 2024


# ---------- gather_cup_history_for_season (mocked API) -----------------

class TestGatherForSeason:
    def test_filters_to_finished_only(self, tmp_path):
        all_fixtures = [
            _api_fixture(fid=1, status="FT", home="A", away="B"),
            _api_fixture(fid=2, status="NS", home="C", away="D"),
            _api_fixture(fid=3, status="PEN", home="E", away="F"),
            _api_fixture(fid=4, status="PST", home="G", away="H"),
        ]
        with patch.object(
            cup_history_mod.api_football, "_request",
            return_value=all_fixtures,
        ) as mock_req:
            rows = gather_cup_history_for_season(
                "UCL", 2024, cache_dir=tmp_path,
            )
        # 1 API call, 2 rows kept (FT + PEN)
        assert mock_req.call_count == 1
        assert len(rows) == 2
        names = {(r["home_team"], r["away_team"]) for r in rows}
        assert names == {("A", "B"), ("E", "F")}


# ---------- Parquet roundtrip --------------------------------------------

class TestParquetRoundtrip:
    def _sample_rows(self):
        return [
            normalize_fixture(
                _api_fixture(fid=1, iso_date="2024-09-17T19:00:00+00:00",
                             home="Real Madrid", away="VfB Stuttgart",
                             round_label="Group Stage - 1"),
                "UCL", 2024,
            ),
            normalize_fixture(
                _api_fixture(fid=2, iso_date="2024-11-05T20:00:00+00:00",
                             home="Bayern Munich", away="Benfica",
                             round_label="Group Stage - 4"),
                "UCL", 2024,
            ),
        ]

    def test_write_then_load(self, tmp_path):
        rows = self._sample_rows()
        out = tmp_path / "UCL_2024.parquet"
        write_cup_history_parquet(rows, out)
        assert out.exists()
        df = load_cup_history_parquet(out)
        assert list(df.columns) == CUP_HISTORY_COLUMNS
        assert len(df) == 2
        assert df.iloc[0]["home_team"] == "Real Madrid"

    def test_empty_rows_writes_empty_parquet(self, tmp_path):
        out = tmp_path / "empty.parquet"
        write_cup_history_parquet([], out)
        df = load_cup_history_parquet(out)
        assert len(df) == 0
        assert list(df.columns) == CUP_HISTORY_COLUMNS

    def test_missing_path_load_returns_empty(self, tmp_path):
        df = load_cup_history_parquet(tmp_path / "nope.parquet")
        assert len(df) == 0
        assert list(df.columns) == CUP_HISTORY_COLUMNS

    def test_canonical_filename(self, tmp_path):
        path = cup_history_parquet_path(tmp_path, "UCL", 2024)
        assert path.name == "UCL_2024.parquet"
        assert path.parent == tmp_path


# ---------- Multi-season concat -------------------------------------------

class TestMultiSeasonConcat:
    def test_concats_across_leagues_and_seasons(self, tmp_path):
        # Seed two leagues × two seasons
        for league, season, home in [
            ("UCL", 2023, "A"), ("UCL", 2024, "B"),
            ("UEL", 2023, "C"), ("UEL", 2024, "D"),
        ]:
            rows = [normalize_fixture(
                _api_fixture(home=home, away="X"), league, season,
            )]
            write_cup_history_parquet(
                rows, cup_history_parquet_path(tmp_path, league, season),
            )
        df = load_multi_season_cup_history(
            tmp_path,
            leagues=["UCL", "UEL"],
            seasons=[2023, 2024],
        )
        assert len(df) == 4
        # date column auto-converted to datetime
        assert pd.api.types.is_datetime64_any_dtype(df["date"])

    def test_missing_combos_silently_skipped(self, tmp_path):
        # Only UCL 2024 exists
        rows = [normalize_fixture(_api_fixture(), "UCL", 2024)]
        write_cup_history_parquet(
            rows, cup_history_parquet_path(tmp_path, "UCL", 2024),
        )
        df = load_multi_season_cup_history(
            tmp_path,
            leagues=["UCL", "UEL"],
            seasons=[2021, 2022, 2023, 2024],
        )
        assert len(df) == 1
        assert df.iloc[0]["league"] == "UCL"

    def test_empty_directory_returns_empty(self, tmp_path):
        df = load_multi_season_cup_history(
            tmp_path,
            leagues=["UCL"],
            seasons=[2024],
        )
        assert len(df) == 0
        assert list(df.columns) == CUP_HISTORY_COLUMNS


# ---------- derive_round_flags integration --------------------------

class TestDeriveRoundFlags:
    def test_knockout_flag_fires(self, tmp_path):
        rows = [
            normalize_fixture(
                _api_fixture(fid=1, round_label="Group Stage - 1"),
                "UCL", 2024,
            ),
            normalize_fixture(
                _api_fixture(fid=2, round_label="Round of 16"),
                "UCL", 2024,
            ),
            normalize_fixture(
                _api_fixture(fid=3, round_label="Final"),
                "UCL", 2024,
            ),
        ]
        write_cup_history_parquet(rows, tmp_path / "UCL_2024.parquet")
        df = load_cup_history_parquet(tmp_path / "UCL_2024.parquet")
        out = derive_round_flags(df)
        assert "is_knockout" in out.columns
        # Group stage → 0; R16 + Final → 1
        flags = out["is_knockout"].tolist()
        assert flags == [0, 1, 1]

    def test_pure_knockout_cup_early_rounds(self, tmp_path):
        # FA Cup has no group phase, so every round is a knockout tie —
        # including the numbered early rounds the label heuristic used to
        # score 0. Labels are the real API-Football vocabulary.
        rows = [
            normalize_fixture(
                _api_fixture(fid=1, round_label="1st Round"), "FAC", 2024,
            ),
            normalize_fixture(
                _api_fixture(fid=2, round_label="3rd Round"), "FAC", 2024,
            ),
            normalize_fixture(
                _api_fixture(fid=3, round_label="Final"), "FAC", 2024,
            ),
        ]
        write_cup_history_parquet(rows, tmp_path / "FAC_2024.parquet")
        df = load_cup_history_parquet(tmp_path / "FAC_2024.parquet")
        out = derive_round_flags(df)
        assert out["is_knockout"].tolist() == [1, 1, 1]

    def test_euro_round_robin_qualifying_stays_zero(self, tmp_path):
        # EURO qualifying is round-robin groups over 10 matchdays; the
        # " - <N>" suffix is what separates it from UEFA's two-legged
        # "1st Qualifying Round".
        rows = [
            normalize_fixture(
                _api_fixture(fid=1, round_label="Qualifying Round - 3"),
                "EURO", 2024,
            ),
            normalize_fixture(
                _api_fixture(fid=2, round_label="Round of 16"), "EURO", 2024,
            ),
        ]
        write_cup_history_parquet(rows, tmp_path / "EURO_2024.parquet")
        df = load_cup_history_parquet(tmp_path / "EURO_2024.parquet")
        out = derive_round_flags(df)
        assert out["is_knockout"].tolist() == [0, 1]


# ---------- CLI -------------------------------------------------------

class TestCLI:
    def test_non_cup_code_rejected_by_default(self, tmp_path):
        rc = cli_main([
            "--leagues", "EPL",  # not a cup
            "--seasons", "2024",
            "--out-dir", str(tmp_path),
            "--quiet",
        ])
        assert rc == 2  # parse / validation failure

    def test_non_cup_allowed_with_override(self, tmp_path):
        # Will try to fetch — mock that out
        with patch.object(
            ingest_cup_history_cli, "gather_cup_history_for_season",
            return_value=[],
        ):
            rc = cli_main([
                "--leagues", "EPL",
                "--seasons", "2024",
                "--out-dir", str(tmp_path),
                "--allow-non-cup",
                "--quiet",
            ])
        assert rc == 0

    def test_writes_per_combo_parquets(self, tmp_path):
        # Mock the gather to return predictable rows
        with patch.object(
            ingest_cup_history_cli, "gather_cup_history_for_season",
            return_value=[
                normalize_fixture(_api_fixture(home="A", away="B"), "UCL", 2024),
                normalize_fixture(_api_fixture(home="C", away="D"), "UCL", 2024),
            ],
        ):
            rc = cli_main([
                "--leagues", "UCL",
                "--seasons", "2024",
                "--out-dir", str(tmp_path),
                "--quiet",
            ])
        assert rc == 0
        out = tmp_path / "UCL_2024.parquet"
        assert out.exists()
        df = load_cup_history_parquet(out)
        assert len(df) == 2

    def test_empty_leagues_returns_2(self, tmp_path):
        rc = cli_main([
            "--leagues", "",
            "--seasons", "2024",
            "--out-dir", str(tmp_path),
            "--quiet",
        ])
        assert rc == 2

    def test_unparseable_seasons_returns_2(self, tmp_path):
        rc = cli_main([
            "--leagues", "UCL",
            "--seasons", "abc",
            "--out-dir", str(tmp_path),
            "--quiet",
        ])
        assert rc == 2

    def test_multi_season_writes_separate_files(self, tmp_path):
        with patch.object(
            ingest_cup_history_cli, "gather_cup_history_for_season",
            return_value=[
                normalize_fixture(_api_fixture(home="X", away="Y"), "UCL", 2023),
            ],
        ):
            rc = cli_main([
                "--leagues", "UCL,UEL",
                "--seasons", "2023,2024",
                "--out-dir", str(tmp_path),
                "--quiet",
            ])
        assert rc == 0
        # 2 leagues × 2 seasons = 4 parquets
        expected = {"UCL_2023.parquet", "UCL_2024.parquet",
                    "UEL_2023.parquet", "UEL_2024.parquet"}
        produced = {p.name for p in tmp_path.glob("*.parquet")}
        assert produced == expected
