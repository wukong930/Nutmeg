"""Tests for nutmeg.v4.cli.ingest_external.

Focus on argument parsing + dispatch + deferred-source error handling. The
clubelo network path is exercised indirectly by ``test_clubelo.py`` mocks.
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from nutmeg.v4.cli import ingest_external
from nutmeg.v4.data.sources import fbref, oddsportal, understat


class TestArgParse:
    def test_clubelo_minimal(self) -> None:
        ns = ingest_external.parse_args(["--source", "clubelo"])
        assert ns.source == "clubelo"
        assert ns.refresh is False
        assert ns.teams is None
        assert ns.skip_coverage_card is False

    def test_clubelo_with_refresh_and_teams(self) -> None:
        ns = ingest_external.parse_args(
            ["--source", "clubelo", "--refresh", "--teams", "Arsenal,Liverpool"]
        )
        assert ns.source == "clubelo"
        assert ns.refresh is True
        assert ns.teams == "Arsenal,Liverpool"

    def test_invalid_source_rejected(self) -> None:
        with pytest.raises(SystemExit):
            ingest_external.parse_args(["--source", "nonsense"])

    def test_source_required(self) -> None:
        with pytest.raises(SystemExit):
            ingest_external.parse_args([])


class TestDeferredSources:
    """All three blocked sources should exit non-zero with a clear error."""

    def test_understat_exits_with_error(self) -> None:
        exit_code = ingest_external.main(["--source", "understat"])
        assert exit_code == 2

    def test_fbref_exits_with_error(self) -> None:
        exit_code = ingest_external.main(["--source", "fbref"])
        assert exit_code == 2

    def test_oddsportal_exits_with_error(self) -> None:
        exit_code = ingest_external.main(["--source", "oddsportal"])
        assert exit_code == 2


class TestDeferredSourceModules:
    """Each deferred adapter must raise its dedicated error class with a useful message."""

    def test_understat_raises(self) -> None:
        with pytest.raises(understat.UnderstatNotAvailableError) as exc:
            understat.fetch_league_season("EPL", 2024)
        assert "JS-rendered" in str(exc.value) or "blocked" in str(exc.value)

    def test_fbref_raises(self) -> None:
        with pytest.raises(fbref.FbrefNotAvailableError) as exc:
            fbref.fetch_match_summary("EPL", 2024)
        assert "403" in str(exc.value) or "blocked" in str(exc.value)

    def test_oddsportal_raises(self) -> None:
        with pytest.raises(oddsportal.OddsPortalNotAvailableError) as exc:
            oddsportal.fetch_opening_odds("EPL", 2024)
        assert "deferred" in str(exc.value) or "OddsPortal" in str(exc.value)


class TestClubeloDispatch:
    """The clubelo path: mock ``ingest_teams`` to avoid network."""

    def test_main_calls_ingest_teams_with_v4_teams(self, tmp_path) -> None:
        # _collect_v4_teams hits real V4 data on disk — mock both that and ingest_teams
        with (
            patch.object(
                ingest_external, "_collect_v4_teams", return_value={"EPL": ["Arsenal", "Liverpool"]}
            ),
            patch.object(ingest_external.clubelo, "ingest_teams") as mock_ingest,
            patch.object(ingest_external, "COVERAGE_CARD", tmp_path / "card.md"),
        ):
            mock_ingest.return_value = pd.DataFrame(
                {
                    "team_canonical": ["Arsenal"],
                    "clubelo_slug": ["Arsenal"],
                    "country": ["ENG"],
                    "elo": [1900.0],
                    "from_date": [pd.Timestamp("2024-01-01").date()],
                    "to_date": [pd.Timestamp("2024-06-30").date()],
                }
            )
            exit_code = ingest_external.main(["--source", "clubelo"])
            assert exit_code == 0
            mock_ingest.assert_called_once()
            # Both teams from the league should be passed in
            args, kwargs = mock_ingest.call_args
            assert "Arsenal" in args[0]
            assert "Liverpool" in args[0]
            assert kwargs["refresh"] is False
            assert kwargs["refresh_empty"] is False

    def test_explicit_teams_override_v4_collection(self, tmp_path) -> None:
        with (
            patch.object(
                ingest_external, "_collect_v4_teams", return_value={"EPL": ["Arsenal", "Liverpool"]}
            ),
            patch.object(ingest_external.clubelo, "ingest_teams") as mock_ingest,
            patch.object(ingest_external, "COVERAGE_CARD", tmp_path / "card.md"),
        ):
            mock_ingest.return_value = pd.DataFrame(
                {
                    "team_canonical": ["Real Madrid"],
                    "clubelo_slug": ["RealMadrid"],
                    "country": ["ESP"],
                    "elo": [1900.0],
                    "from_date": [pd.Timestamp("2024-01-01").date()],
                    "to_date": [pd.Timestamp("2024-06-30").date()],
                }
            )
            exit_code = ingest_external.main(
                ["--source", "clubelo", "--teams", "Real Madrid,Barcelona"]
            )
            assert exit_code == 0
            args, _ = mock_ingest.call_args
            assert args[0] == ["Real Madrid", "Barcelona"]

    def test_refresh_flag_propagates(self, tmp_path) -> None:
        with (
            patch.object(ingest_external, "_collect_v4_teams", return_value={"EPL": ["Arsenal"]}),
            patch.object(ingest_external.clubelo, "ingest_teams") as mock_ingest,
            patch.object(ingest_external, "COVERAGE_CARD", tmp_path / "card.md"),
        ):
            mock_ingest.return_value = pd.DataFrame(
                {
                    "team_canonical": ["Arsenal"],
                    "clubelo_slug": ["Arsenal"],
                    "country": ["ENG"],
                    "elo": [1900.0],
                    "from_date": [pd.Timestamp("2024-01-01").date()],
                    "to_date": [pd.Timestamp("2024-06-30").date()],
                }
            )
            exit_code = ingest_external.main(["--source", "clubelo", "--refresh"])
            assert exit_code == 0
            _, kwargs = mock_ingest.call_args
            assert kwargs["refresh"] is True

    def test_refresh_empty_flag_propagates(self, tmp_path) -> None:
        with (
            patch.object(ingest_external, "_collect_v4_teams", return_value={"EPL": ["Arsenal"]}),
            patch.object(ingest_external.clubelo, "ingest_teams") as mock_ingest,
            patch.object(ingest_external, "COVERAGE_CARD", tmp_path / "card.md"),
        ):
            mock_ingest.return_value = pd.DataFrame(
                {
                    "team_canonical": ["Arsenal"],
                    "clubelo_slug": ["Arsenal"],
                    "country": ["ENG"],
                    "elo": [1900.0],
                    "from_date": [pd.Timestamp("2024-01-01").date()],
                    "to_date": [pd.Timestamp("2024-06-30").date()],
                }
            )
            exit_code = ingest_external.main(["--source", "clubelo", "--refresh-empty"])
            assert exit_code == 0
            _, kwargs = mock_ingest.call_args
            assert kwargs["refresh"] is False
            assert kwargs["refresh_empty"] is True


class TestCoverageCardGeneration:
    def test_writes_card_with_expected_sections(self, tmp_path) -> None:
        teams_by_league = {"EPL": ["Arsenal", "Liverpool"], "ESP_LA_LIGA": ["Barcelona"]}
        hist = pd.DataFrame(
            {
                "team_canonical": ["Arsenal", "Barcelona"],  # Liverpool missing
                "clubelo_slug": ["Arsenal", "Barcelona"],
                "country": ["ENG", "ESP"],
                "elo": [1900.0, 1950.0],
                "from_date": [pd.Timestamp("2024-01-01").date()] * 2,
                "to_date": [pd.Timestamp("2024-06-30").date()] * 2,
            }
        )
        with patch.object(ingest_external, "COVERAGE_CARD", tmp_path / "card.md"):
            ingest_external._write_coverage_card(teams_by_league, hist)
            content = (tmp_path / "card.md").read_text()

        assert "# V5 External Data Coverage" in content
        assert "Clubelo" in content
        assert "Deferred Sources" in content
        # Coverage math: 1/2 EPL (50%), 1/1 La Liga (100%), 2/3 total (66.7%)
        assert "| EPL | 2 | 1 | 50.0% |" in content
        assert "| ESP_LA_LIGA | 1 | 1 | 100.0% |" in content
        assert "**2** | **3**" not in content  # ordering check; total is "3" then "2"
        assert "**3** | **2**" in content  # totals row: total_v4=3, total_hit=2
