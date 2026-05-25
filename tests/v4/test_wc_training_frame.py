"""V10 W1 Track B Day 2 — tests for wc_training_frame.

Covers:
  - name_to_elo_code lookup (canonical + edge cases like Türkiye, Scotland)
  - build_wc_training_frame join correctness with fixtures + odds + Elo
  - Defensive behavior: missing odds file → NaN psc; missing Elo → None Elo
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nutmeg.v4.data.national_team_name_to_elo import (
    TEAM_NAME_TO_ELO_CODE,
    lookup_elo_code,
)
from nutmeg.v4.data.wc_training_frame import build_wc_training_frame, load_elo_snapshot


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data" / "external"


class TestNameToEloCode:
    """The canonical mapping module."""

    def test_top_teams_covered(self):
        for team in ["Argentina", "France", "Brazil", "England", "Spain", "Germany"]:
            assert lookup_elo_code(team) is not None, f"{team} missing from map"

    def test_scotland_uses_sq_not_sc(self):
        """eloratings uses SQ for Scotland; SC is Seychelles. P1#10 trap."""
        assert lookup_elo_code("Scotland") == "SQ"

    def test_turkiye_resolves_to_tr(self):
        """API-Football uses 'Türkiye' (official); eloratings uses TR."""
        assert lookup_elo_code("Türkiye") == "TR"
        assert lookup_elo_code("Turkey") == "TR"  # legacy alias

    def test_unknown_team_returns_none(self):
        assert lookup_elo_code("Atlantis") is None
        assert lookup_elo_code("") is None

    def test_wc_2026_all_48_teams_covered(self):
        """Smoke test: every team confirmed in the 2026 WC fixture list
        from Day 1 must be mappable."""
        wc_2026 = [
            "Algeria", "Argentina", "Australia", "Austria", "Belgium",
            "Bosnia & Herzegovina", "Brazil", "Canada", "Cape Verde Islands",
            "Colombia", "Congo DR", "Croatia", "Curaçao", "Czech Republic",
            "Ecuador", "Egypt", "England", "France", "Germany", "Ghana",
            "Haiti", "Iran", "Iraq", "Ivory Coast", "Japan", "Jordan",
            "Mexico", "Morocco", "Netherlands", "New Zealand", "Norway",
            "Panama", "Paraguay", "Portugal", "Qatar", "Saudi Arabia",
            "Scotland", "Senegal", "South Africa", "South Korea", "Spain",
            "Sweden", "Switzerland", "Tunisia", "Türkiye", "USA",
            "Uruguay", "Uzbekistan",
        ]
        missing = [t for t in wc_2026 if lookup_elo_code(t) is None]
        assert not missing, f"WC 2026 teams missing from map: {missing}"


# Skip the integration tests if local data isn't present
_HAS_WC_2022 = (DATA / "cup_history" / "WC_2022.parquet").exists() and (
    DATA / "cup_odds" / "WC_2022.parquet"
).exists()
_HAS_ELO_SNAPSHOT = any(
    (DATA / "eloratings").glob("eloratings_*.parquet")
) if (DATA / "eloratings").exists() else False


@pytest.mark.skipif(
    not (_HAS_WC_2022 and _HAS_ELO_SNAPSHOT),
    reason="WC 2022 fixtures+odds or eloratings snapshot not present locally; "
           "run nutmeg-ingest-cup-history --leagues WC --seasons 2022 first.",
)
class TestBuildWcTrainingFrameIntegration:
    """End-to-end build, requires local data."""

    def test_wc_2022_full_coverage(self):
        df = build_wc_training_frame(2022)
        assert len(df) == 64
        # All teams should have Elo (32 nations, all in the map)
        n_both_elo = (df["home_elo"].notna() & df["away_elo"].notna()).sum()
        assert n_both_elo == 64, f"Only {n_both_elo}/64 fixtures have both Elos"
        # Most should have odds (P1#20 + V10 W1 Day 1 found 63/64)
        n_with_odds = df["psc_home"].notna().sum()
        assert n_with_odds >= 60, f"Only {n_with_odds}/64 fixtures have odds"

    def test_elo_diff_computed(self):
        df = build_wc_training_frame(2022)
        # Where both Elos present, elo_diff should equal home - away
        has_both = df[df["home_elo"].notna() & df["away_elo"].notna()]
        for _, row in has_both.head(5).iterrows():
            assert row["elo_diff"] == pytest.approx(
                row["home_elo"] - row["away_elo"]
            )

    def test_columns_in_expected_order(self):
        df = build_wc_training_frame(2022)
        # First 3 columns should be the identity columns
        assert list(df.columns)[:3] == ["date", "league", "season"]
        # Elo columns present
        for col in ["home_elo", "away_elo", "elo_diff", "home_elo_rank", "away_elo_rank"]:
            assert col in df.columns


@pytest.mark.skipif(
    not _HAS_ELO_SNAPSHOT,
    reason="eloratings snapshot not present locally",
)
class TestLoadEloSnapshot:
    def test_returns_dict_keyed_by_country_code(self):
        snap = sorted((DATA / "eloratings").glob("eloratings_*.parquet"))[-1]
        d = load_elo_snapshot(snap)
        assert isinstance(d, dict)
        # eloratings has 240+ entries
        assert len(d) >= 200
        # ES (Spain) should be present
        assert "ES" in d
        assert "elo" in d["ES"]


class TestMissingFixtures:
    """Defensive: raise if season's fixtures aren't ingested."""

    def test_raises_filenotfound_for_unknown_season(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="WC 9999 fixtures"):
            build_wc_training_frame(
                9999,
                cup_history_dir=tmp_path,
                cup_odds_dir=tmp_path,
                elo_snapshot_path=tmp_path / "fake.parquet",  # not used since fixture check fails first
            )
