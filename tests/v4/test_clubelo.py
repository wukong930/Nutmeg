"""Tests for nutmeg.v4.data.sources.clubelo.

We avoid hitting the real http://api.clubelo.com network in unit tests; the
``ingest_teams`` path is exercised by the CLI integration test under
tests/v4/test_ingest_external.py once it's added.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pandas as pd
import pytest

from nutmeg.v4.data.sources import clubelo


SAMPLE_CSV = (
    "Rank,Club,Country,Level,Elo,From,To\n"
    "None,Arsenal,ENG,1,1551.14,1946-07-07,1946-08-31\n"
    "None,Arsenal,ENG,1,1700.0,2024-01-01,2024-06-30\n"
    "1,Arsenal,ENG,1,1975.82,2024-12-12,2024-12-15\n"
    "1,Arsenal,ENG,1,1980.5,2024-12-16,2024-12-22\n"
)


class TestSlugFor:
    def test_known_alias(self) -> None:
        assert clubelo._slug_for("Man United") == "ManUnited"
        assert clubelo._slug_for("Ath Madrid") == "Atletico"
        assert clubelo._slug_for("M'gladbach") == "Gladbach"
        assert clubelo._slug_for("Nott'm Forest") == "Forest"

    def test_unknown_falls_back_to_concatenation(self) -> None:
        # No spaces / apostrophes
        assert clubelo._slug_for("Arsenal") == "Arsenal"
        # Two words → joined
        assert clubelo._slug_for("Random Town") == "RandomTown"
        # Apostrophe stripped
        assert clubelo._slug_for("O'Brien FC") == "OBrienFC"


class TestFetchTeamHistory:
    def test_parses_csv_to_canonical_columns(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = SAMPLE_CSV
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        df = clubelo.fetch_team_history("Arsenal", client=mock_client)

        assert list(df.columns) == [
            "team_canonical",
            "clubelo_slug",
            "country",
            "elo",
            "from_date",
            "to_date",
        ]
        assert len(df) == 4
        assert df["team_canonical"].iloc[0] == "Arsenal"
        assert df["clubelo_slug"].iloc[0] == "Arsenal"
        assert df["country"].iloc[0] == "ENG"
        assert df["elo"].iloc[0] == pytest.approx(1551.14)
        assert df["from_date"].iloc[0] == dt.date(1946, 7, 7)

        mock_client.get.assert_called_once_with("http://api.clubelo.com/Arsenal")

    def test_empty_response_returns_empty_frame(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        df = clubelo.fetch_team_history("UnknownTeam", client=mock_client)
        assert df.empty
        assert list(df.columns) == [
            "team_canonical",
            "clubelo_slug",
            "country",
            "elo",
            "from_date",
            "to_date",
        ]


class TestEloOnDate:
    @pytest.fixture
    def history(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "team_canonical": ["Arsenal", "Arsenal", "Arsenal", "ManCity"],
                "clubelo_slug": ["Arsenal", "Arsenal", "Arsenal", "ManCity"],
                "country": ["ENG"] * 4,
                "elo": [1700.0, 1975.82, 1980.5, 1960.0],
                "from_date": [
                    dt.date(2024, 1, 1),
                    dt.date(2024, 12, 12),
                    dt.date(2024, 12, 16),
                    dt.date(2024, 12, 12),
                ],
                "to_date": [
                    dt.date(2024, 6, 30),
                    dt.date(2024, 12, 15),
                    dt.date(2024, 12, 22),
                    dt.date(2024, 12, 22),
                ],
            }
        )

    def test_date_within_first_interval(self, history: pd.DataFrame) -> None:
        elo = clubelo.elo_on_date(history, "Arsenal", "2024-05-15")
        assert elo == pytest.approx(1700.0)

    def test_date_within_later_interval(self, history: pd.DataFrame) -> None:
        elo = clubelo.elo_on_date(history, "Arsenal", "2024-12-13")
        assert elo == pytest.approx(1975.82)

    def test_date_on_boundary(self, history: pd.DataFrame) -> None:
        # Boundary should match the interval that ends or starts on it
        elo = clubelo.elo_on_date(history, "Arsenal", "2024-12-15")
        assert elo == pytest.approx(1975.82)
        elo = clubelo.elo_on_date(history, "Arsenal", "2024-12-16")
        assert elo == pytest.approx(1980.5)

    def test_date_outside_history(self, history: pd.DataFrame) -> None:
        # Before any interval → None
        assert clubelo.elo_on_date(history, "Arsenal", "2023-01-01") is None
        # Between intervals (gap) → None
        assert clubelo.elo_on_date(history, "Arsenal", "2024-09-15") is None

    def test_unknown_team_returns_none(self, history: pd.DataFrame) -> None:
        assert clubelo.elo_on_date(history, "Liverpool", "2024-12-15") is None

    def test_accepts_timestamp(self, history: pd.DataFrame) -> None:
        elo = clubelo.elo_on_date(history, "Arsenal", pd.Timestamp("2024-12-13"))
        assert elo == pytest.approx(1975.82)


class TestCachePath:
    def test_normalizes_team_name_for_filename(self, tmp_path: Path) -> None:
        assert clubelo.cache_path("Arsenal", tmp_path).name == "Arsenal.parquet"
        assert clubelo.cache_path("Man United", tmp_path).name == "Man_United.parquet"
        assert clubelo.cache_path("Nott'm Forest", tmp_path).name == "Nottm_Forest.parquet"

    def test_path_under_cache_dir(self, tmp_path: Path) -> None:
        p = clubelo.cache_path("Arsenal", tmp_path)
        assert p.parent == tmp_path


class TestIngestTeams:
    """ingest_teams + cache behavior, especially the new refresh_empty flag.

    The HTTP path is mocked via patching fetch_team_history; this isolates the
    cache logic from network flakiness.
    """

    def _write_history(
        self, cache_dir: Path, team: str, rows: int
    ) -> pd.DataFrame:
        df = pd.DataFrame(
            {
                "team_canonical": [team] * rows,
                "clubelo_slug": [clubelo._slug_for(team)] * rows,
                "country": ["ENG"] * rows,
                "elo": [1900.0 + i for i in range(rows)],
                "from_date": [dt.date(2024, 1, 1)] * rows,
                "to_date": [dt.date(2024, 6, 30)] * rows,
            }
        )
        df.to_parquet(clubelo.cache_path(team, cache_dir), index=False)
        return df

    def test_uses_cache_when_present_and_not_refresh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_history(tmp_path, "Arsenal", rows=3)
        fetch_calls: list[str] = []

        def fake_fetch(team: str, *, client: object) -> pd.DataFrame:
            fetch_calls.append(team)
            return clubelo._empty_history_frame(team, "Arsenal")

        monkeypatch.setattr(clubelo, "fetch_team_history", fake_fetch)

        out = clubelo.ingest_teams(["Arsenal"], cache_dir=tmp_path, throttle_seconds=0)
        assert len(out) == 3  # came from cache, not network
        assert fetch_calls == []  # network never hit

    def test_refresh_true_always_refetches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_history(tmp_path, "Arsenal", rows=3)
        fetch_calls: list[str] = []

        def fake_fetch(team: str, *, client: object) -> pd.DataFrame:
            fetch_calls.append(team)
            # Return 5 rows so we can detect that this path ran
            return pd.DataFrame(
                {
                    "team_canonical": [team] * 5,
                    "clubelo_slug": [clubelo._slug_for(team)] * 5,
                    "country": ["ENG"] * 5,
                    "elo": [2000.0] * 5,
                    "from_date": [dt.date(2024, 7, 1)] * 5,
                    "to_date": [dt.date(2024, 12, 31)] * 5,
                }
            )

        monkeypatch.setattr(clubelo, "fetch_team_history", fake_fetch)

        out = clubelo.ingest_teams(
            ["Arsenal"], cache_dir=tmp_path, refresh=True, throttle_seconds=0
        )
        assert fetch_calls == ["Arsenal"]
        assert len(out) == 5
        # And the cache was overwritten
        cached = pd.read_parquet(clubelo.cache_path("Arsenal", tmp_path))
        assert len(cached) == 5

    def test_refresh_empty_only_refetches_empty_caches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arsenal cache has 3 rows (non-empty) — must be kept
        self._write_history(tmp_path, "Arsenal", rows=3)
        # Milan cache is empty (simulates rate-limit casualty) — must be re-fetched
        empty = clubelo._empty_history_frame("Milan", "Milan")
        empty.to_parquet(clubelo.cache_path("Milan", tmp_path), index=False)

        fetch_calls: list[str] = []

        def fake_fetch(team: str, *, client: object) -> pd.DataFrame:
            fetch_calls.append(team)
            return pd.DataFrame(
                {
                    "team_canonical": [team] * 2,
                    "clubelo_slug": [clubelo._slug_for(team)] * 2,
                    "country": ["ITA"] * 2,
                    "elo": [1800.0, 1850.0],
                    "from_date": [dt.date(2024, 1, 1), dt.date(2024, 6, 1)],
                    "to_date": [dt.date(2024, 5, 31), dt.date(2024, 12, 31)],
                }
            )

        monkeypatch.setattr(clubelo, "fetch_team_history", fake_fetch)

        out = clubelo.ingest_teams(
            ["Arsenal", "Milan"],
            cache_dir=tmp_path,
            refresh_empty=True,
            throttle_seconds=0,
        )
        # Only Milan was re-fetched; Arsenal was served from cache
        assert fetch_calls == ["Milan"]
        # Out frame has both: Arsenal (3) + Milan (2 newly fetched) = 5
        assert len(out) == 5
        assert sorted(out["team_canonical"].unique()) == ["Arsenal", "Milan"]
        # Milan's cache was updated on disk
        milan_cached = pd.read_parquet(clubelo.cache_path("Milan", tmp_path))
        assert len(milan_cached) == 2

    def test_refresh_empty_skips_non_empty_caches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._write_history(tmp_path, "Arsenal", rows=3)
        fetch_calls: list[str] = []

        def fake_fetch(team: str, *, client: object) -> pd.DataFrame:
            fetch_calls.append(team)
            raise AssertionError(f"should not have been called for {team}")

        monkeypatch.setattr(clubelo, "fetch_team_history", fake_fetch)
        out = clubelo.ingest_teams(
            ["Arsenal"], cache_dir=tmp_path, refresh_empty=True, throttle_seconds=0
        )
        assert fetch_calls == []
        assert len(out) == 3

    def test_failed_fetch_writes_empty_parquet(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_fetch(team: str, *, client: object) -> pd.DataFrame:
            raise httpx.TimeoutException("simulated rate limit")

        monkeypatch.setattr(clubelo, "fetch_team_history", fake_fetch)

        out = clubelo.ingest_teams(
            ["Milan"], cache_dir=tmp_path, throttle_seconds=0
        )
        # Should not raise, returns empty
        assert out.empty
        # And the parquet exists but is empty (so refresh_empty can detect it later)
        assert clubelo.cache_path("Milan", tmp_path).exists()
        cached = pd.read_parquet(clubelo.cache_path("Milan", tmp_path))
        assert cached.empty
