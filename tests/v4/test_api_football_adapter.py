"""Tests for nutmeg.v4.data.sources.api_football (V6 W1+W2).

We avoid hitting the real API. Tests cover:
- league_id lookup + error on unknown league
- cache path generation (hash determinism)
- compute_xi_minutes_share math
- error surfaced when API key missing
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from nutmeg.v4.data.sources import api_football


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "api_football"


class TestLeagueId:
    def test_known_league(self):
        assert api_football.league_id("EPL") == 39
        assert api_football.league_id("ESP_LA_LIGA") == 140

    def test_unknown_raises(self):
        with pytest.raises(api_football.ApiFootballError, match="no API-Football league ID"):
            api_football.league_id("MLS")


class TestCachePath:
    def test_deterministic(self, tmp_path):
        a = api_football._cache_path("/fixtures", {"league": 39, "date": "2025-05-11"}, tmp_path)
        b = api_football._cache_path("/fixtures", {"league": 39, "date": "2025-05-11"}, tmp_path)
        assert a == b

    def test_params_order_invariant(self, tmp_path):
        # JSON dumps with sort_keys=True → same hash regardless of dict order
        a = api_football._cache_path("/x", {"a": 1, "b": 2}, tmp_path)
        b = api_football._cache_path("/x", {"b": 2, "a": 1}, tmp_path)
        assert a == b

    def test_endpoint_in_path(self, tmp_path):
        p = api_football._cache_path("/fixtures/lineups", {"fixture": 1}, tmp_path)
        # Slashes replaced with underscores
        assert p.parent.name == "_fixtures_lineups"


class TestCachePersistence:
    def test_returns_cached_without_http_call(self, tmp_path, monkeypatch):
        # Pre-populate cache
        canned = [{"fixture": {"id": 999}}]
        cp = api_football._cache_path("/fixtures", {"date": "2025-05-11"}, tmp_path)
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(canned))

        # _client() must NOT be called when cache hits
        def boom():
            raise AssertionError("should not have hit network")
        monkeypatch.setattr(api_football, "_client", boom)

        result = api_football._request("/fixtures", {"date": "2025-05-11"},
                                       cache_dir=tmp_path)
        assert result == canned


class TestComputeXiMinutesShare:
    def test_empty_xi(self):
        assert api_football.compute_xi_minutes_share([], [{"player": {"id": 1}}]) == 1.0

    def test_empty_squad_stats(self):
        assert api_football.compute_xi_minutes_share([1, 2, 3], []) == 0.5

    def test_full_xi_overlap(self):
        # Both stats rows are for our XI players → ratio 1.0
        stats = [
            {"player": {"id": 1}, "statistics": [{"games": {"lineups": 30}}]},
            {"player": {"id": 2}, "statistics": [{"games": {"lineups": 28}}]},
        ]
        assert api_football.compute_xi_minutes_share([1, 2], stats) == 1.0

    def test_partial_overlap(self):
        # XI = [1, 2]; squad has players 1, 2, 3. Player 1+2 starts = 50, total = 80.
        stats = [
            {"player": {"id": 1}, "statistics": [{"games": {"lineups": 30}}]},
            {"player": {"id": 2}, "statistics": [{"games": {"lineups": 20}}]},
            {"player": {"id": 3}, "statistics": [{"games": {"lineups": 30}}]},
        ]
        assert api_football.compute_xi_minutes_share([1, 2], stats) == pytest.approx(50 / 80)

    def test_no_xi_in_squad(self):
        # XI players not in the squad stats → 0 overlap, but total > 0 so ratio 0
        stats = [
            {"player": {"id": 999}, "statistics": [{"games": {"lineups": 30}}]},
        ]
        assert api_football.compute_xi_minutes_share([1, 2], stats) == 0.0

    def test_handles_none_lineups_field(self):
        # API-Football sometimes returns null/None for games.lineups
        stats = [
            {"player": {"id": 1}, "statistics": [{"games": {"lineups": None}}]},
        ]
        # total_starts = 0 → 0.5 fallback
        assert api_football.compute_xi_minutes_share([1], stats) == 0.5

    def test_handles_multiple_competitions(self):
        # A player's "statistics" list has one entry per competition; sum across
        stats = [
            {"player": {"id": 1}, "statistics": [
                {"games": {"lineups": 20}},  # league
                {"games": {"lineups": 5}},   # cup
            ]},
        ]
        assert api_football.compute_xi_minutes_share([1], stats) == 1.0


class TestClientErrorWhenNoKey:
    def test_raises_when_key_missing(self):
        """When get_settings() returns a Settings with no api_football_key,
        the client constructor must surface a clear error rather than
        sending an unauthenticated request."""
        with patch("nutmeg.v4.data.sources.api_football.get_settings") as gs:
            class FakeSettings:
                api_football_key = None
                api_football_base_url = "https://v3.football.api-sports.io"
                api_football_timeout_seconds = 15.0
            gs.return_value = FakeSettings()
            with pytest.raises(api_football.ApiFootballError, match="NUTMEG_API_FOOTBALL_KEY"):
                api_football._client()


class TestFetchersUseCache:
    """Smoke: top-level fetch_* delegate to _request with the right endpoint."""

    def test_fetch_fixtures_passes_date(self, tmp_path, monkeypatch):
        # Pre-populate the cache so no network is needed
        import datetime as dt
        params = {"date": "2025-05-11", "league": 39, "season": 2024}
        cp = api_football._cache_path("/fixtures", params, tmp_path)
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps([{"fixture": {"id": 1}}]))

        def boom():
            raise AssertionError("should not hit network when cache exists")
        monkeypatch.setattr(api_football, "_client", boom)

        result = api_football.fetch_fixtures_for_date(
            dt.date(2025, 5, 11), "EPL", cache_dir=tmp_path,
        )
        assert result == [{"fixture": {"id": 1}}]

    def test_fetch_lineups_uses_fixture_id_param(self, tmp_path, monkeypatch):
        cp = api_football._cache_path("/fixtures/lineups", {"fixture": 1208620}, tmp_path)
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps([{"team": {"id": 42}}]))
        monkeypatch.setattr(
            api_football, "_client",
            lambda: (_ for _ in ()).throw(AssertionError("network attempted")),
        )
        result = api_football.fetch_lineups(1208620, cache_dir=tmp_path)
        assert result == [{"team": {"id": 42}}]


class TestSeasonForDate:
    """V12 W4 fix — calendar-year leagues (J1) vs European Aug–Jul leagues.

    The bug: J1 (calendar-year) spring dates were queried under the European
    heuristic (year-1), asking API-Football for the prior finished season →
    0 fixtures → next-day J1 matches went undetected.
    """

    def test_european_spring_uses_prev_year(self):
        import datetime as dt
        # 2026-05 belongs to the 2025/26 season → season start 2025
        assert api_football.season_for_date(dt.date(2026, 5, 30), "EPL") == 2025
        assert api_football.season_for_date(dt.date(2026, 5, 30), "ESP_SEGUNDA_DIVISION") == 2025

    def test_european_autumn_uses_current_year(self):
        import datetime as dt
        assert api_football.season_for_date(dt.date(2025, 9, 1), "EPL") == 2025

    def test_calendar_year_league_uses_date_year(self):
        import datetime as dt
        # J1 runs Feb–Dec within one year → season is the date's year, NOT 2025
        assert api_football.season_for_date(dt.date(2026, 5, 30), "JPN_J1") == 2026
        assert api_football.season_for_date(dt.date(2026, 2, 20), "JPN_J1") == 2026
        assert "JPN_J1" in api_football.CALENDAR_YEAR_LEAGUES

    def test_none_league_falls_back_to_european(self):
        import datetime as dt
        assert api_football.season_for_date(dt.date(2026, 5, 30), None) == 2025

    def test_fetch_fixtures_for_date_uses_calendar_season_for_j1(self, tmp_path, monkeypatch):
        import datetime as dt
        captured = {}

        def fake_request(endpoint, params, **kw):
            captured.update(params)
            return []

        monkeypatch.setattr(api_football, "_request", fake_request)
        api_football.fetch_fixtures_for_date(dt.date(2026, 5, 30), "JPN_J1", cache_dir=tmp_path)
        assert captured["season"] == 2026   # not 2025
