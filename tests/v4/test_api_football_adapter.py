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

import httpx
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


class TestFriendliesLeague:
    """体检(2026-06-10)— FRIENDLIES must be fetchable or manual-calculator
    friendly bets can never auto-settle (the Croatia/Slovenia 6/7 orphan)."""

    def test_league_id(self):
        assert api_football.league_id("FRIENDLIES") == 10  # from cached envelope

    def test_calendar_year_season(self):
        import datetime as dt
        # June date: the European Aug–Jul heuristic would say season 2025 →
        # the API returns 0 friendly fixtures; calendar-year gives 2026.
        assert api_football.season_for_date(dt.date(2026, 6, 7), "FRIENDLIES") == 2026


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


class _Resp:
    status_code = 200
    text = ""

    def json(self):
        return {"response": [{"ok": 1}], "errors": []}


class _FlakyClient:
    """Context-manager client whose .get() raises ReadTimeout the first
    ``fail_times`` calls, then returns ``response``. Shared across retries so
    the call counter persists."""

    def __init__(self, fail_times, response):
        self.fail_times = fail_times
        self.response = response
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, endpoint, params=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise httpx.ReadTimeout("simulated timeout")
        return self.response


class _Resp429:
    status_code = 429
    text = "rate limited"
    headers = {"Retry-After": "0"}  # numeric → _retry_after_seconds honors it

    def json(self):
        return {}


class _RateThenOkClient:
    """Returns a 429 the first ``limit_times`` calls, then ``ok_response``."""

    def __init__(self, limit_times, ok_response):
        self.limit_times = limit_times
        self.ok_response = ok_response
        self.calls = 0

    def get(self, endpoint, params=None):
        self.calls += 1
        if self.calls <= self.limit_times:
            return _Resp429()
        return self.ok_response


class TestRequestRetry:
    """V13 — a single transient timeout must not abort the call (the 2026-05-31
    settle cron died on one httpx.ReadTimeout, leaving the UCL final pending)."""

    def test_retries_then_succeeds(self, tmp_path, monkeypatch):
        flaky = _FlakyClient(fail_times=2, response=_Resp())
        monkeypatch.setattr(api_football, "_client", lambda: flaky)
        monkeypatch.setattr(api_football.time, "sleep", lambda s: None)
        out = api_football._request("/fixtures", {"date": "a"},
                                    cache_dir=tmp_path, refresh=True)
        assert out == [{"ok": 1}]
        assert flaky.calls == 3   # 2 timeouts + 1 success

    def test_raises_after_max_attempts(self, tmp_path, monkeypatch):
        flaky = _FlakyClient(fail_times=99, response=_Resp())
        monkeypatch.setattr(api_football, "_client", lambda: flaky)
        monkeypatch.setattr(api_football.time, "sleep", lambda s: None)
        with pytest.raises(api_football.ApiFootballError,
                           match="network error after 3 attempts"):
            api_football._request("/fixtures", {"date": "b"},
                                  cache_dir=tmp_path, refresh=True)
        assert flaky.calls == 3   # exactly _MAX_REQUEST_ATTEMPTS

    def test_http_error_not_retried(self, tmp_path, monkeypatch):
        class _Resp500:
            status_code = 500
            text = "boom"

        flaky = _FlakyClient(fail_times=0, response=_Resp500())
        monkeypatch.setattr(api_football, "_client", lambda: flaky)
        monkeypatch.setattr(api_football.time, "sleep", lambda s: None)
        with pytest.raises(api_football.ApiFootballError, match="HTTP 500"):
            api_football._request("/x", {"a": 1}, cache_dir=tmp_path, refresh=True)
        assert flaky.calls == 1   # HTTP errors are not transient → no retry

    def test_rate_limit_429_retried_then_succeeds(self, tmp_path, monkeypatch):
        # fetch-perf B — concurrency can briefly trip the per-second rate limit;
        # a 429 must be retried (with backoff) so the fixture isn't dropped.
        client = _RateThenOkClient(limit_times=2, ok_response=_Resp())
        monkeypatch.setattr(api_football, "_client", lambda: client)
        monkeypatch.setattr(api_football.time, "sleep", lambda s: None)
        out = api_football._request("/odds", {"fixture": 1},
                                    cache_dir=tmp_path, refresh=True)
        assert out == [{"ok": 1}]
        assert client.calls == 3   # 2× 429 + 1 success

    def test_rate_limit_429_exhausts_then_raises(self, tmp_path, monkeypatch):
        client = _RateThenOkClient(limit_times=99, ok_response=_Resp())
        monkeypatch.setattr(api_football, "_client", lambda: client)
        monkeypatch.setattr(api_football.time, "sleep", lambda s: None)
        with pytest.raises(api_football.ApiFootballError, match="HTTP 429"):
            api_football._request("/odds", {"fixture": 2},
                                  cache_dir=tmp_path, refresh=True)
        assert client.calls == 3   # capped at _MAX_REQUEST_ATTEMPTS


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

    def test_national_team_tournaments_use_date_year(self):
        import datetime as dt
        # V14 — WC 2026 (June–July) is season 2026. Under the European Aug–Jul
        # heuristic a June date → year−1 = 2025 → API returns 0 WC fixtures,
        # silently dropping the whole World Cup from the market-mode board +
        # predict-log. The WC-specific endpoints already used on_date.year; this
        # aligns the generic season resolver with them.
        assert api_football.season_for_date(dt.date(2026, 6, 11), "WC") == 2026
        assert api_football.season_for_date(dt.date(2026, 7, 19), "WC") == 2026
        for code in ("WC", "EURO", "COPA_AMERICA"):
            assert code in api_football.CALENDAR_YEAR_LEAGUES

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


class TestUpcomingFixtureTTL:
    """近期赛事 stale-cache bug (2026-07-01): an EMPTY WC fixtures result, cached
    days earlier before API-Football confirmed the matches, masked the whole World
    Cup from the market-mode board — the cache is permanent-until-refresh and the
    gather calls with refresh_fixtures=False, so it served the empty list forever.

    Fix: a today-or-later fixtures-by-date cache older than the TTL is refetched;
    past dates are settled → cache forever; a failed refetch falls back to the
    stale cache (never worse than the old permanent-cache behavior).
    """

    def _seed(self, tmp_path, on_date, age_hours):
        """Create the /fixtures cache file for (on_date, WC) with a given mtime age.
        Content is irrelevant — the fix only inspects existence + mtime."""
        import os
        import time
        params = {"date": on_date.isoformat(),
                  "league": api_football.league_id("WC"),
                  "season": api_football.season_for_date(on_date, "WC")}
        cf = api_football._cache_path("/fixtures", params, tmp_path)
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps([]))       # empty = the exact bug shape
        t = time.time() - age_hours * 3600
        os.utime(cf, (t, t))
        return cf

    @staticmethod
    def _record_request(monkeypatch, *, on_refresh, stale=None, raise_on_refresh=False):
        calls: list[bool] = []

        def fake_request(endpoint, params, *, cache_dir=None, refresh=False, **kw):
            calls.append(refresh)
            if refresh:
                if raise_on_refresh:
                    raise api_football.ApiFootballError("network down")
                return on_refresh
            return stale if stale is not None else []

        monkeypatch.setattr(api_football, "_request", fake_request)
        return calls

    def test_stale_empty_upcoming_refetches(self, tmp_path, monkeypatch):
        import datetime as dt
        upcoming = dt.datetime.now(dt.UTC).date() + dt.timedelta(days=2)
        self._seed(tmp_path, upcoming, age_hours=7)          # older than the 6h TTL
        fresh = [{"fixture": {"id": 42}}]
        calls = self._record_request(monkeypatch, on_refresh=fresh)
        out = api_football.fetch_fixtures_for_date(upcoming, "WC", cache_dir=tmp_path)
        assert out == fresh          # the not-yet-listed match now surfaces
        assert True in calls         # a refresh=True refetch was forced

    def test_fresh_upcoming_cache_not_refetched(self, tmp_path, monkeypatch):
        import datetime as dt
        upcoming = dt.datetime.now(dt.UTC).date() + dt.timedelta(days=2)
        self._seed(tmp_path, upcoming, age_hours=1)          # within the TTL
        calls = self._record_request(monkeypatch, on_refresh=[{"fixture": {"id": 99}}])
        api_football.fetch_fixtures_for_date(upcoming, "WC", cache_dir=tmp_path)
        assert calls == [False]      # no forced refresh → saves the API call

    def test_past_date_stale_cache_not_refetched(self, tmp_path, monkeypatch):
        import datetime as dt
        past = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=30)
        self._seed(tmp_path, past, age_hours=7)              # stale, but settled
        calls = self._record_request(monkeypatch, on_refresh=[{"fixture": {"id": 7}}])
        api_football.fetch_fixtures_for_date(past, "WC", cache_dir=tmp_path)
        assert calls == [False]      # past fixtures never change → permanent cache

    def test_failed_refetch_falls_back_to_stale_cache(self, tmp_path, monkeypatch):
        import datetime as dt
        upcoming = dt.datetime.now(dt.UTC).date() + dt.timedelta(days=2)
        self._seed(tmp_path, upcoming, age_hours=7)
        stale = [{"fixture": {"id": 1}}]
        calls = self._record_request(
            monkeypatch, on_refresh=None, stale=stale, raise_on_refresh=True)
        out = api_football.fetch_fixtures_for_date(upcoming, "WC", cache_dir=tmp_path)
        assert out == stale          # network down → stale beats crashing the board
        assert calls == [True, False]  # tried refresh, fell back to the cached read
