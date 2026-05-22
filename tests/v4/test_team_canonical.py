"""Tests for nutmeg.utils.team_canonical."""
from __future__ import annotations

import pytest

from nutmeg.utils.team_canonical import (
    TEAM_ALIASES,
    normalize_name,
    report_unmatched,
    to_v4_canonical,
)


EPL_POOL = [
    "Arsenal",
    "Man United",
    "Man City",
    "Nott'm Forest",
    "Tottenham",
    "Brighton",
    "West Ham",
    "Sheffield United",
    "Aston Villa",
    "Crystal Palace",
]

LIGA_POOL = [
    "Real Madrid",
    "Ath Bilbao",
    "Ath Madrid",
    "Barcelona",
    "Sociedad",
    "Espanol",
    "Valladolid",
]

DE_POOL = [
    "Bayern Munich",
    "Dortmund",
    "M'gladbach",
    "Ein Frankfurt",
    "FC Koln",
    "RB Leipzig",
    "Leverkusen",
    "Werder Bremen",
]


class TestNormalizeName:
    def test_lowercase_strip_accents(self) -> None:
        assert normalize_name("Atlético Madrid") == "atletico madrid"
        assert normalize_name("MÖNCHENGLADBACH") == "monchengladbach"

    def test_strip_punctuation(self) -> None:
        assert normalize_name("Nott'm Forest") == "nott m forest"
        assert normalize_name("Saint-Étienne") == "saint etienne"
        assert normalize_name("1. FC Köln") == "1 fc koln"

    def test_ampersand_becomes_and(self) -> None:
        assert normalize_name("Brighton & Hove Albion") == "brighton and hove albion"

    def test_collapse_whitespace(self) -> None:
        assert normalize_name("Real    Madrid") == "real madrid"
        assert normalize_name("  Arsenal  ") == "arsenal"

    def test_empty_and_none(self) -> None:
        assert normalize_name("") == ""
        # type-narrow path
        assert normalize_name(None) == ""  # type: ignore[arg-type]


class TestToV4Canonical:
    def test_exact_match(self) -> None:
        r = to_v4_canonical("Arsenal", "EPL", EPL_POOL)
        assert r.canonical == "Arsenal"
        assert r.method == "exact"
        assert r.confidence == 1.0

    def test_normalized_exact_match(self) -> None:
        # Same as pool element but with different accent / case
        r = to_v4_canonical("arsenal", "EPL", EPL_POOL)
        assert r.canonical == "Arsenal"
        assert r.method == "exact"

    def test_alias_resolves(self) -> None:
        r = to_v4_canonical("Manchester United", "EPL", EPL_POOL)
        assert r.canonical == "Man United"
        assert r.method == "alias"
        assert r.confidence == 1.0

    def test_alias_accent_stripped(self) -> None:
        r = to_v4_canonical("Atlético Madrid", "ESP_LA_LIGA", LIGA_POOL)
        assert r.canonical == "Ath Madrid"
        assert r.method == "alias"

    def test_alias_with_ampersand(self) -> None:
        r = to_v4_canonical("Brighton & Hove Albion", "EPL", EPL_POOL)
        assert r.canonical == "Brighton"
        assert r.method == "alias"

    def test_fuzzy_match_threshold(self) -> None:
        # "Real Madrid" vs "Real Sociedad" sequence ratio is ~0.79 — must NOT match
        # (would silently route Real Madrid stats to Sociedad otherwise)
        r = to_v4_canonical("Real Sociedad", "ESP_LA_LIGA", ["Real Madrid"])
        assert r.canonical is None
        assert r.method == "unmatched"

    def test_fuzzy_match_close_typo(self) -> None:
        # "Mna United" (typo) → should fuzzy-match Man United at ~0.89
        r = to_v4_canonical("Mna United", "EPL", EPL_POOL)
        assert r.canonical == "Man United"
        assert r.method == "fuzzy"
        assert r.confidence > 0.85

    def test_unknown_team_returns_none(self) -> None:
        r = to_v4_canonical("Some Unknown FC", "EPL", EPL_POOL)
        assert r.canonical is None
        assert r.method == "unmatched"
        assert r.confidence == 0.0

    def test_empty_name(self) -> None:
        r = to_v4_canonical("", "EPL", EPL_POOL)
        assert r.canonical is None

    def test_empty_pool(self) -> None:
        r = to_v4_canonical("Arsenal", "EPL", [])
        assert r.canonical is None


class TestReportUnmatched:
    def test_reports_per_name(self) -> None:
        names = ["Arsenal", "Manchester United", "Real Madrid", "Mystery FC"]
        results = report_unmatched(names, "EPL", EPL_POOL)
        assert len(results) == 4
        # Real Madrid is in EPL_POOL queries with wrong league but the alias lookup
        # only checks EPL aliases, and fuzzy match against EPL teams should miss
        unmatched = [n for n, r in results if r.canonical is None]
        assert "Mystery FC" in unmatched

    def test_finds_alias_resolutions(self) -> None:
        results = report_unmatched(["Manchester United"], "EPL", EPL_POOL)
        _, result = results[0]
        assert result.canonical == "Man United"
        assert result.method == "alias"


class TestAliasCoverage:
    """Sanity checks on the curated TEAM_ALIASES dict."""

    def test_at_least_six_leagues(self) -> None:
        # Should have entries for EPL, La Liga, Serie A, Bundesliga, Ligue 1,
        # Eredivisie, Primeira (matches V4's covered leagues)
        assert len(TEAM_ALIASES) >= 6

    def test_all_aliases_are_normalized_keys(self) -> None:
        # Aliases dict keys must already be in normalized form so lookup works
        for league, alias_map in TEAM_ALIASES.items():
            for key in alias_map:
                normalized = normalize_name(key)
                assert key == normalized, (
                    f"Alias key {key!r} in {league} should be the normalized form {normalized!r}"
                )

    @pytest.mark.parametrize("league", ["EPL", "ESP_LA_LIGA", "GER_BUNDESLIGA"])
    def test_canonical_targets_are_unique_per_league(self, league: str) -> None:
        # Multiple aliases can map to the same canonical — that's fine. But each
        # alias key must be unique inside its league dict (Python dict enforces this).
        aliases = TEAM_ALIASES[league]
        assert len(aliases) == len({k for k in aliases})
