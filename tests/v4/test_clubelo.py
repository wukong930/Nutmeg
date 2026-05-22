"""Tests for nutmeg.v4.data.sources.clubelo.

We avoid hitting the real http://api.clubelo.com network in unit tests; the
``ingest_teams`` path is exercised by the CLI integration test under
tests/v4/test_ingest_external.py once it's added.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock

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
