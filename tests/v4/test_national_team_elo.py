"""Tests for V8 W7 national-team Elo (clubelo /<NationCode>) ingest + lookup.
"""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pandas as pd
import pytest

from nutmeg.v4.cli import ingest_national_elo as ingest_mod
from nutmeg.v4.cli.ingest_national_elo import main as ingest_main
from nutmeg.v4.data import national_team_elo as nte_mod
from nutmeg.v4.data.national_team_elo import (
    NATION_CLUBELO_CODES,
    _NAME_TO_CODE,
    build_nation_elo_lookup,
    fetch_nation_history,
    load_nation_parquet,
    lookup_nation_elo,
    nation_cache_path,
    write_nation_parquet,
)


# ---------- NATION_CLUBELO_CODES registry shape ----------------------

class TestRegistry:
    def test_known_top_nations_present(self):
        for code in ("ENG", "FRA", "ESP", "GER", "ITA", "BRA", "ARG",
                     "USA", "MEX", "JPN", "AUS", "MAR", "SAU"):
            assert code in NATION_CLUBELO_CODES, f"missing: {code}"

    def test_codes_are_uppercase_3_letter(self):
        for code in NATION_CLUBELO_CODES.keys():
            assert len(code) == 3
            assert code == code.upper()

    def test_each_code_has_at_least_one_alias(self):
        for code, aliases in NATION_CLUBELO_CODES.items():
            assert len(aliases) >= 1, f"{code}: no name aliases"

    def test_name_to_code_reverse_map_built(self):
        # The reverse map is built at import time
        assert _NAME_TO_CODE["england"] == "ENG"
        assert _NAME_TO_CODE["brazil"] == "BRA"
        # The 3-letter code itself should also self-resolve
        assert _NAME_TO_CODE["eng"] == "ENG"


# ---------- fetch_nation_history -----------------------------------

class TestFetchNationHistory:
    def _client_returning(self, body: str, status_code: int = 200):
        """Build a mock httpx.Client whose GET returns the given body."""
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.text = body
        resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "x", request=MagicMock(), response=resp,
            ) if status_code >= 400 and status_code != 404 else MagicMock(),
        )
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = resp
        return client

    def test_parses_csv_to_dataframe(self):
        body = "Country,Rank,From,To,Elo\n" \
               "ENG,5,2024-01-01,2024-06-30,1900.5\n" \
               "ENG,4,2024-07-01,2024-12-31,1920.0\n"
        client = self._client_returning(body)
        df = fetch_nation_history("ENG", client=client)
        assert len(df) == 2
        assert list(df.columns) == ["code", "from_date", "to_date", "elo"]
        assert df.iloc[0]["code"] == "ENG"
        assert df.iloc[0]["elo"] == 1900.5
        assert df.iloc[1]["elo"] == 1920.0

    def test_empty_body_returns_empty_frame(self):
        client = self._client_returning("")
        df = fetch_nation_history("XYZ", client=client)
        assert len(df) == 0
        assert list(df.columns) == ["code", "from_date", "to_date", "elo"]

    def test_404_returns_empty(self):
        client = self._client_returning("", status_code=404)
        df = fetch_nation_history("XYZ", client=client)
        assert len(df) == 0

    def test_code_uppercased(self):
        body = "Country,Rank,From,To,Elo\nbra,1,2024-01-01,2024-06-30,1950.0\n"
        client = self._client_returning(body)
        df = fetch_nation_history("bra", client=client)
        # Passed-in code "bra" → output uses "BRA"
        assert df.iloc[0]["code"] == "BRA"

    def test_invalid_dates_dropped(self):
        body = "Country,Rank,From,To,Elo\n" \
               "ENG,5,not-a-date,2024-06-30,1900.0\n" \
               "ENG,4,2024-07-01,2024-12-31,1920.0\n"
        client = self._client_returning(body)
        df = fetch_nation_history("ENG", client=client)
        # First row dropped (NaT from_date), second kept
        assert len(df) == 1
        assert df.iloc[0]["elo"] == 1920.0


# ---------- Parquet roundtrip --------------------------------------

class TestParquetRoundtrip:
    def test_write_then_load(self, tmp_path):
        df = pd.DataFrame({
            "code":      ["ENG", "ENG"],
            "from_date": pd.to_datetime(["2024-01-01", "2024-07-01"]),
            "to_date":   pd.to_datetime(["2024-06-30", "2024-12-31"]),
            "elo":       [1900.5, 1920.0],
        })
        path = nation_cache_path(tmp_path, "ENG")
        write_nation_parquet(df, path)
        assert path.exists()
        loaded = load_nation_parquet(path)
        assert len(loaded) == 2
        assert loaded.iloc[0]["elo"] == 1900.5

    def test_missing_path_returns_empty(self, tmp_path):
        df = load_nation_parquet(tmp_path / "nope.parquet")
        assert len(df) == 0
        assert list(df.columns) == ["code", "from_date", "to_date", "elo"]

    def test_canonical_filename(self, tmp_path):
        assert nation_cache_path(tmp_path, "ENG").name == "ENG.parquet"
        # Lowercase input is uppercased
        assert nation_cache_path(tmp_path, "bra").name == "BRA.parquet"


# ---------- build_nation_elo_lookup --------------------------------

class TestBuildLookup:
    def _seed(self, tmp_path: Path, code: str, rows: list[tuple]):
        df = pd.DataFrame({
            "code":      [code] * len(rows),
            "from_date": pd.to_datetime([r[0] for r in rows]),
            "to_date":   pd.to_datetime([r[1] for r in rows]),
            "elo":       [r[2] for r in rows],
        })
        write_nation_parquet(df, nation_cache_path(tmp_path, code))

    def test_picks_active_row(self, tmp_path):
        self._seed(tmp_path, "ENG", [
            ("2024-01-01", "2024-06-30", 1900.0),
            ("2024-07-01", "2024-12-31", 1920.0),
        ])
        lookup = build_nation_elo_lookup(
            tmp_path,
            as_of=pd.Timestamp("2024-08-15"),
        )
        assert lookup["ENG"] == 1920.0

    def test_falls_back_to_latest_when_no_active(self, tmp_path):
        # Cache stale — last row ended before as_of
        self._seed(tmp_path, "ENG", [
            ("2023-01-01", "2023-12-31", 1850.0),
            ("2024-01-01", "2024-06-30", 1900.0),
        ])
        lookup = build_nation_elo_lookup(
            tmp_path, as_of=pd.Timestamp("2025-08-15"),
        )
        # Most recent row's elo
        assert lookup["ENG"] == 1900.0

    def test_walks_all_parquets_by_default(self, tmp_path):
        self._seed(tmp_path, "ENG", [("2024-01-01", "2024-12-31", 1900.0)])
        self._seed(tmp_path, "BRA", [("2024-01-01", "2024-12-31", 1950.0)])
        lookup = build_nation_elo_lookup(
            tmp_path, as_of=pd.Timestamp("2024-06-01"),
        )
        assert lookup == {"ENG": 1900.0, "BRA": 1950.0}

    def test_subset_filter(self, tmp_path):
        self._seed(tmp_path, "ENG", [("2024-01-01", "2024-12-31", 1900.0)])
        self._seed(tmp_path, "BRA", [("2024-01-01", "2024-12-31", 1950.0)])
        lookup = build_nation_elo_lookup(
            tmp_path, as_of=pd.Timestamp("2024-06-01"),
            codes=["ENG"],
        )
        assert lookup == {"ENG": 1900.0}

    def test_empty_dir_returns_empty(self, tmp_path):
        lookup = build_nation_elo_lookup(tmp_path, as_of=pd.Timestamp("2024-06-01"))
        assert lookup == {}

    def test_default_as_of_utcnow(self, tmp_path):
        # Just verify it doesn't crash without explicit as_of
        self._seed(tmp_path, "ENG", [("2024-01-01", "2099-12-31", 1900.0)])
        lookup = build_nation_elo_lookup(tmp_path)
        assert "ENG" in lookup


# ---------- lookup_nation_elo --------------------------------------

class TestLookupNationElo:
    @pytest.fixture
    def state(self):
        return {"ENG": 1900.0, "BRA": 1950.0, "USA": 1750.0, "FRA": 1880.0}

    def test_exact_code(self, state):
        code, elo = lookup_nation_elo(state, "ENG")
        assert code == "ENG"
        assert elo == 1900.0

    def test_code_case_insensitive(self, state):
        code, elo = lookup_nation_elo(state, "eng")
        assert code == "ENG"

    def test_full_name_via_alias(self, state):
        code, elo = lookup_nation_elo(state, "England")
        assert code == "ENG"
        assert elo == 1900.0

    def test_alternate_name(self, state):
        # "United States" maps to USA
        code, elo = lookup_nation_elo(state, "United States")
        assert code == "USA"
        assert elo == 1750.0

    def test_alias_present_but_state_missing(self, state):
        # Argentina alias resolves to ARG, but state doesn't have ARG
        code, elo = lookup_nation_elo(state, "Argentina")
        assert code is None
        assert elo is None

    def test_unknown_name(self, state):
        code, elo = lookup_nation_elo(state, "Mystery Republic")
        assert code is None
        assert elo is None

    def test_empty_name(self, state):
        code, elo = lookup_nation_elo(state, "")
        assert code is None


# ---------- CLI ----------------------------------------------------

class TestIngestCLI:
    def test_unknown_country_warns_but_continues(self, tmp_path):
        # XYZ isn't in registry → warning + proceeds with HTTP (which would 404)
        with patch.object(ingest_mod, "fetch_nation_history",
                          return_value=nte_mod._empty_history_frame()):
            rc = ingest_main([
                "--countries", "XYZ",
                "--cache-dir", str(tmp_path),
                "--throttle-ms", "0",
                "--quiet",
            ])
        # Empty fetch is logged but not an error
        assert rc == 0
        # An empty parquet should still be written so loaders can distinguish
        assert (tmp_path / "XYZ.parquet").exists()

    def test_happy_path_two_countries(self, tmp_path):
        def fake_fetch(code, *, client):
            return pd.DataFrame({
                "code":      [code.upper()],
                "from_date": pd.to_datetime(["2024-01-01"]),
                "to_date":   pd.to_datetime(["2024-12-31"]),
                "elo":       [1900.0 if code.upper() == "ENG" else 1950.0],
            })

        with patch.object(ingest_mod, "fetch_nation_history",
                          side_effect=fake_fetch):
            rc = ingest_main([
                "--countries", "ENG,BRA",
                "--cache-dir", str(tmp_path),
                "--throttle-ms", "0",
                "--quiet",
            ])
        assert rc == 0
        eng = load_nation_parquet(tmp_path / "ENG.parquet")
        bra = load_nation_parquet(tmp_path / "BRA.parquet")
        assert eng.iloc[0]["elo"] == 1900.0
        assert bra.iloc[0]["elo"] == 1950.0

    def test_cache_skipped_without_refresh(self, tmp_path):
        # Pre-seed a parquet
        (tmp_path / "ENG.parquet").touch()
        # Mock fetch_nation_history — should NOT be called for cached ENG
        with patch.object(ingest_mod, "fetch_nation_history") as mock_fetch:
            rc = ingest_main([
                "--countries", "ENG",
                "--cache-dir", str(tmp_path),
                "--throttle-ms", "0",
                "--quiet",
            ])
        assert rc == 0
        mock_fetch.assert_not_called()

    def test_refresh_overrides_cache(self, tmp_path):
        (tmp_path / "ENG.parquet").touch()
        with patch.object(ingest_mod, "fetch_nation_history",
                          return_value=nte_mod._empty_history_frame()) as mock_fetch:
            rc = ingest_main([
                "--countries", "ENG",
                "--cache-dir", str(tmp_path),
                "--throttle-ms", "0",
                "--refresh",
                "--quiet",
            ])
        assert rc == 0
        mock_fetch.assert_called_once()

    def test_default_countries_uses_full_registry(self, tmp_path):
        # No --countries → uses all 68 codes
        with patch.object(ingest_mod, "fetch_nation_history",
                          return_value=nte_mod._empty_history_frame()) as mock_fetch:
            rc = ingest_main([
                "--cache-dir", str(tmp_path),
                "--throttle-ms", "0",
                "--quiet",
            ])
        assert rc == 0
        # 68 nations registered → 68 fetches
        assert mock_fetch.call_count == len(NATION_CLUBELO_CODES)

    def test_fetch_error_counted_as_failed(self, tmp_path):
        def boom(code, *, client):
            raise httpx.ConnectError("simulated network error")

        with patch.object(ingest_mod, "fetch_nation_history", side_effect=boom):
            rc = ingest_main([
                "--countries", "ENG",
                "--cache-dir", str(tmp_path),
                "--throttle-ms", "0",
                "--quiet",
            ])
        # Failed fetch → exit 1
        assert rc == 1
