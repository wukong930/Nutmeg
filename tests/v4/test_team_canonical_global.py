"""Tests for V8 W1 team_canonical global / cross-league lookup.

Verifies:
  1. build_global_team_pool unions league pools, de-dupes, sorts
  2. to_v4_canonical_global lookup precedence (exact / normalized /
     CUP_TEAM_ALIASES / per-league walk / fuzzy)
  3. report_unmatched_global diagnostic shape
  4. nutmeg-canonical-report-cup CLI (parser + mocked parquets)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from nutmeg.utils.team_canonical import (
    CUP_TEAM_ALIASES,
    TEAM_ALIASES,
    build_global_team_pool,
    report_unmatched_global,
    to_v4_canonical_global,
)
from nutmeg.v4.cli import canonical_report_cup as cli_mod
from nutmeg.v4.cli.canonical_report_cup import (
    _gather_cup_team_names,
    main as cli_main,
)
from nutmeg.v4.data.cup_history import (
    cup_history_parquet_path,
    normalize_fixture,
    write_cup_history_parquet,
)


# ---------- build_global_team_pool -----------------------------------

class TestBuildGlobalTeamPool:
    def test_unions_leagues(self):
        pool = build_global_team_pool({
            "EPL": ["Arsenal", "Liverpool"],
            "ESP_LA_LIGA": ["Real Madrid", "Barcelona"],
        })
        assert set(pool) == {"Arsenal", "Liverpool", "Real Madrid", "Barcelona"}

    def test_dedupes(self):
        # Two leagues sharing a team (rare but possible w/ promotions)
        pool = build_global_team_pool({
            "EPL": ["Burnley", "Watford"],
            "ENG_CHAMPIONSHIP": ["Burnley", "Norwich"],
        })
        assert pool.count("Burnley") == 1

    def test_sorted_output(self):
        pool = build_global_team_pool({
            "EPL": ["Zorro", "Apple"],
            "ESP_LA_LIGA": ["Mango"],
        })
        assert pool == sorted(pool)

    def test_empty_pools_returns_empty(self):
        assert build_global_team_pool({}) == []
        assert build_global_team_pool({"EPL": []}) == []

    def test_filters_falsy_names(self):
        pool = build_global_team_pool({
            "EPL": ["Arsenal", None, ""],
        })
        assert pool == ["Arsenal"]


# ---------- to_v4_canonical_global -----------------------------------

class TestGlobalLookup:
    @pytest.fixture
    def pool(self):
        return build_global_team_pool({
            "EPL": ["Arsenal", "Liverpool", "Man United", "Man City",
                    "Tottenham", "Newcastle"],
            "ESP_LA_LIGA": ["Real Madrid", "Barcelona", "Ath Madrid",
                            "Ath Bilbao", "Sociedad"],
            "GER_BUNDESLIGA": ["Bayern Munich", "Dortmund", "Leverkusen",
                                "RB Leipzig"],
            "FRA_LIGUE_1": ["Paris SG", "Marseille", "Lyon", "Monaco"],
            "ITA_SERIE_A": ["Inter", "Milan", "Juventus", "Napoli"],
        })

    def test_exact_match(self, pool):
        r = to_v4_canonical_global("Real Madrid", pool)
        assert r.canonical == "Real Madrid"
        assert r.method == "exact"
        assert r.confidence == 1.0

    def test_normalized_match_accents(self, pool):
        r = to_v4_canonical_global("Atlético Madrid", pool)
        # No exact match, no alias for this normalized form (norm "atletico
        # madrid" IS in CUP_TEAM_ALIASES → "Ath Madrid") → alias path
        assert r.canonical == "Ath Madrid"
        # method is "alias" because CUP_TEAM_ALIASES caught it
        assert r.method in ("exact", "alias")

    def test_cup_team_alias_resolves(self, pool):
        # "Manchester United" → "Man United" via CUP_TEAM_ALIASES
        r = to_v4_canonical_global("Manchester United", pool)
        assert r.canonical == "Man United"
        assert r.method == "alias"

    def test_cup_alias_real_madrid_cf(self, pool):
        # API-Football uses "Real Madrid CF" — resolves via CUP_TEAM_ALIASES
        r = to_v4_canonical_global("Real Madrid CF", pool)
        assert r.canonical == "Real Madrid"
        assert r.method == "alias"

    def test_falls_back_to_per_league_alias(self, pool):
        # "Bayer 04 Leverkusen" → "Leverkusen" via per-league GER_BUNDESLIGA alias
        # (also in CUP_TEAM_ALIASES; test that either path works)
        r = to_v4_canonical_global("Bayer 04 Leverkusen", pool)
        assert r.canonical == "Leverkusen"
        assert r.method == "alias"

    def test_per_league_only_alias_still_works(self, pool):
        # An alias only in TEAM_ALIASES, not CUP_TEAM_ALIASES — should still
        # resolve via the per-league walk
        # "Borussia Monchengladbach" is in TEAM_ALIASES["GER_BUNDESLIGA"]
        # but only if we add the canonical to the pool — add it for this test
        pool_with_gladbach = pool + ["M'gladbach"]
        r = to_v4_canonical_global("Borussia Monchengladbach", pool_with_gladbach)
        assert r.canonical == "M'gladbach"
        assert r.method == "alias"

    def test_fuzzy_match(self, pool):
        # Misspelled enough to miss exact + alias, close enough for fuzzy.
        # Use "Man Cty" — typo of "Man City"; ratio against "man city"
        # ≈ 0.93, above the 0.86 threshold.
        r = to_v4_canonical_global("Man Cty", pool)
        assert r.canonical == "Man City"
        assert r.method == "fuzzy"
        assert r.confidence < 1.0
        assert r.confidence >= 0.86

    def test_unmatched_returns_none(self, pool):
        r = to_v4_canonical_global("Brand New Club FC", pool)
        assert r.canonical is None
        assert r.method == "unmatched"

    def test_empty_pool_unmatched(self):
        r = to_v4_canonical_global("Arsenal", [])
        assert r.method == "unmatched"

    def test_empty_name_unmatched(self, pool):
        r = to_v4_canonical_global("", pool)
        assert r.method == "unmatched"

    def test_alias_canonical_not_in_pool_falls_through(self, pool):
        # If CUP_TEAM_ALIASES maps "manchester united" → "Man United" but
        # "Man United" isn't in the pool, the alias step should be skipped
        # (returns the next-best resolution).
        pool_no_united = [t for t in pool if t != "Man United"]
        r = to_v4_canonical_global("Manchester United", pool_no_united)
        # Either fuzzy lands on Man City (closest), or unmatched. Either
        # way it should NOT claim "Man United"
        assert r.canonical != "Man United"


# ---------- CUP_TEAM_ALIASES shape -----------------------------------

class TestCupTeamAliasesShape:
    def test_keys_are_normalized(self):
        from nutmeg.utils.team_canonical import normalize_name
        for key in CUP_TEAM_ALIASES.keys():
            assert key == normalize_name(key), (
                f"key {key!r} is not normalized"
            )

    def test_known_top_clubs_present(self):
        # The CLI exists to add missing ones; these are the ones V8 W1
        # ships hand-curated and should remain in the catch-all
        for canonical_expected, alias in [
            ("Man United", "manchester united"),
            ("Real Madrid", "real madrid cf"),
            ("Bayern Munich", "fc bayern munchen"),
            ("Inter", "internazionale"),
            ("Paris SG", "paris saint germain"),
            ("Porto", "fc porto"),
        ]:
            assert CUP_TEAM_ALIASES.get(alias) == canonical_expected


# ---------- report_unmatched_global --------------------------------

class TestReportUnmatched:
    def test_shape(self):
        pool = ["Arsenal", "Liverpool", "Real Madrid"]
        report = report_unmatched_global(
            ["Arsenal", "Manchester United", "Random FC"], pool,
        )
        assert len(report) == 3
        # Same input → same length output
        for name, result in report:
            assert isinstance(name, str)
            assert hasattr(result, "canonical")
            assert hasattr(result, "method")


# ---------- CLI ------------------------------------------------------

class TestCanonicalReportCupCLI:
    def _seed_cup_parquet(self, tmp_path: Path) -> Path:
        cup_dir = tmp_path / "cup_history"
        rows = []
        for fid, home, away in [
            (1, "Real Madrid", "Manchester United"),
            (2, "Bayern Munich", "Paris Saint Germain"),
            (3, "Arsenal", "Some Random Team"),
        ]:
            api_fix = {
                "fixture": {
                    "id": fid,
                    "date": "2024-11-05T20:00:00+00:00",
                    "status": {"short": "FT", "long": "FT"},
                },
                "teams": {"home": {"name": home}, "away": {"name": away}},
                "goals": {"home": 1, "away": 0},
                "league": {"id": 2, "round": "Group Stage - 1"},
            }
            rows.append(normalize_fixture(api_fix, "UCL", 2024))
        write_cup_history_parquet(
            rows, cup_history_parquet_path(cup_dir, "UCL", 2024),
        )
        return cup_dir

    def test_gather_cup_team_names(self, tmp_path):
        cup_dir = self._seed_cup_parquet(tmp_path)
        names = _gather_cup_team_names(cup_dir, ["UCL"], [2024])
        assert "Real Madrid" in names
        assert "Manchester United" in names
        assert "Paris Saint Germain" in names
        assert "Arsenal" in names
        assert "Some Random Team" in names

    def test_missing_data_returns_1(self, tmp_path):
        # Seed parquet but no --data path
        cup_dir = self._seed_cup_parquet(tmp_path)
        rc = cli_main([
            "--leagues", "UCL",
            "--seasons", "2024",
            "--cup-history-dir", str(cup_dir),
            "--data", str(tmp_path / "nonexistent_data"),
            "--quiet",
        ])
        assert rc == 1

    def test_missing_parquets_returns_1(self, tmp_path):
        rc = cli_main([
            "--leagues", "UCL",
            "--seasons", "2024",
            "--cup-history-dir", str(tmp_path / "no_parquets"),
            "--data", "data/historical_sources/football_data_co_uk",
            "--quiet",
        ])
        assert rc == 1

    def test_empty_seasons_returns_2(self, tmp_path):
        rc = cli_main([
            "--leagues", "UCL",
            "--seasons", "",
            "--quiet",
        ])
        assert rc == 2

    def test_happy_path_with_mocked_pool(self, tmp_path):
        # Mock the data-loader to return a controlled pool so we don't
        # require the football-data tree at test time
        cup_dir = self._seed_cup_parquet(tmp_path)

        def fake_pool(data_dir):
            return [
                "Arsenal", "Liverpool", "Man United", "Real Madrid",
                "Bayern Munich", "Paris SG",
            ]

        with patch.object(cli_mod, "_build_pool_from_football_data",
                          side_effect=fake_pool):
            rc = cli_main([
                "--leagues", "UCL",
                "--seasons", "2024",
                "--cup-history-dir", str(cup_dir),
                "--data", str(tmp_path),  # any non-empty path
                "--show", "all",
                "--quiet",
            ])
        assert rc == 0
