"""💸 Odds API 服务侧配额 (2026-07-17) — the PASSIVE serving path must not be the
thing that refreshes the Pinnacle cache.

MEASURED: with the 3 odds crons paused since 07-12, every 17 sport_key of a
`/predictions/cup-market?days=7` returned 401 OUT_OF_USAGE_CREDITS. Nothing in
the serving code had changed — the crons had been warming the on-disk cache, and
`odds_api._request` treats `ttl_seconds` as a refresh TRIGGER (an expired cache
fires a live call even at refresh=False), so pausing them silently promoted the
dashboard from cache READER to cache REFRESHER. The 3 polled endpoints
(today_rec / sp-calc / cup-market) share one sport_key-keyed cache spanning a
30-key union ⇒ 30 × 48 windows = 1,440 credits/day vs a 20K/month ≈ 667/day plan.

These pin the fix's two halves, which pull in opposite directions:
  - serving passes 6h  → a polled dashboard costs ≤120/day
  - the CLI default stays 1800 → predict_log keeps sampling FRESH lines into the
    odds_snapshots CLV history (it passes refresh_odds=False + snapshot_db, so
    this TTL is the only thing keeping its samples honest)
"""
from __future__ import annotations

import datetime as dt
import os
import time

import pytest

from nutmeg.v4.api import routes
from nutmeg.v4.cli import ingest_odds
from nutmeg.v4.data.sources import odds_api

# ---------- the meter itself ------------------------------------------

class _CountingClient:
    def __init__(self):
        self.calls = 0

    def get(self, endpoint, params=None):
        self.calls += 1
        return _Resp()


class _Resp:
    status_code = 200
    headers: dict = {}

    def json(self):
        return []


@pytest.fixture
def counting_client(monkeypatch):
    c = _CountingClient()
    monkeypatch.setattr(odds_api, "_client", lambda: c)
    return c


def _age_cache(cache_dir, seconds):
    """Backdate every cached pull so it looks `seconds` old."""
    old = time.time() - seconds
    n = 0
    for p in cache_dir.rglob("*.json"):
        os.utime(p, (old, old))
        n += 1
    assert n, "expected the warm-up call to have written a cache file"


class TestTtlIsTheMeter:
    """Why 1800 was expensive and 6h is not — same cache, same passive load."""

    def test_expired_cache_fires_a_live_call_even_without_refresh(
        self, tmp_path, counting_client
    ):
        # warm the cache the way a (now-paused) cron would
        odds_api.fetch_current_odds("soccer_epl", cache_dir=tmp_path)
        assert counting_client.calls == 1
        _age_cache(tmp_path, 1860)          # 31 min — just past the CLI TTL

        odds_api.fetch_current_odds(
            "soccer_epl", cache_dir=tmp_path, refresh=False, ttl_seconds=1800,
        )
        # refresh=False, yet it paid: the TTL is a trigger, not a cache-only gate.
        assert counting_client.calls == 2

    def test_serving_ttl_rides_the_same_stale_cache_for_free(
        self, tmp_path, counting_client
    ):
        odds_api.fetch_current_odds("soccer_epl", cache_dir=tmp_path)
        _age_cache(tmp_path, 1860)

        odds_api.fetch_current_odds(
            "soccer_epl", cache_dir=tmp_path, refresh=False,
            ttl_seconds=routes._SERVING_OA_TTL_SECONDS,
        )
        assert counting_client.calls == 1, "6h TTL must serve the 31min-old cache"

    def test_manual_refresh_still_bypasses_the_long_ttl(
        self, tmp_path, counting_client
    ):
        """🔄 must stay live — the fix may not cost the user their fresh line."""
        odds_api.fetch_current_odds("soccer_epl", cache_dir=tmp_path)
        odds_api.fetch_current_odds(
            "soccer_epl", cache_dir=tmp_path, refresh=True,
            ttl_seconds=routes._SERVING_OA_TTL_SECONDS,
        )
        assert counting_client.calls == 2


# ---------- the threading ---------------------------------------------

def _wire(monkeypatch, seen):
    """One NS fixture per league; capture the ttl handed to the Odds API."""
    env = {
        "fixture": {"id": 900, "date": "2026-07-18T19:00:00+00:00",
                    "status": {"short": "NS"}},
        "teams": {"home": {"name": "Mexico"}, "away": {"name": "South Africa"}},
        "update": "2026-07-17T00:00:00Z",
        "bookmakers": [],
    }
    monkeypatch.setattr(
        ingest_odds.api_football, "fetch_fixtures_for_date", lambda *a, **k: [env])
    monkeypatch.setattr(ingest_odds.api_football, "fetch_odds", lambda *a, **k: [env])

    def _capture(sport_key, *, refresh=False, ttl_seconds=None, **kw):
        seen.append(ttl_seconds)
        return {}

    monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", _capture)


class TestGatherRowsTtlThreading:
    def test_default_stays_1800_so_predict_log_keeps_clv_honest(
        self, tmp_path, monkeypatch
    ):
        """predict_log passes refresh_odds=False + snapshot_db and samples the
        result into odds_snapshots. If this default drifts up, that CLV line
        history silently starts recording stale quotes as closing evidence."""
        seen: list = []
        _wire(monkeypatch, seen)
        ingest_odds._gather_rows(
            ["WC"], dt.date(2026, 7, 18), cache_dir=tmp_path, bookmaker_id=4,
            refresh_fixtures=False, refresh_odds=False, require_odds=False,
            use_odds_api=True,
        )
        assert seen == [1800]

    def test_serving_ttl_is_threaded_through(self, tmp_path, monkeypatch):
        seen: list = []
        _wire(monkeypatch, seen)
        ingest_odds._gather_rows(
            ["WC"], dt.date(2026, 7, 18), cache_dir=tmp_path, bookmaker_id=4,
            refresh_fixtures=False, refresh_odds=False, require_odds=False,
            use_odds_api=True, oa_ttl_seconds=routes._SERVING_OA_TTL_SECONDS,
        )
        assert seen == [6 * 3600]


# ---------- every polled endpoint, not just the one that 401'd --------

class TestAllPolledEndpointsPassServingTtl:
    """cup-market was the one caught 401ing, but the dashboard polls three
    endpoints against ONE shared sport_key cache. Fixing only cup-market would
    leave today_rec / sp-calc re-arming the 30min meter for their 13 keys."""

    @pytest.fixture(autouse=True)
    def _stub(self, monkeypatch):
        self.seen: list = []

        def _fake_gather(*a, **kw):
            self.seen.append(kw.get("oa_ttl_seconds"))
            return ([], 0, 0)

        monkeypatch.setattr(ingest_odds, "_gather_rows", _fake_gather)
        monkeypatch.setattr(ingest_odds, "_odds_api_available", lambda: True)
        monkeypatch.setattr(routes, "_observation_db_path", lambda: None)

    def test_cup_market(self):
        routes.predictions_cup_market(days=1)
        assert self.seen == [6 * 3600]

    def test_sp_calc(self, monkeypatch):
        monkeypatch.setattr(routes, "get_artifact", lambda: object())
        monkeypatch.setattr(routes, "_calc_predictions", lambda *a, **k: [])
        routes.predictions_sp_calc(days=1)
        assert self.seen == [6 * 3600]

    def test_today_recommendations(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest

        routes.today_recommendations(TodayRecommendationsRequest(leagues=["EPL"]))
        assert self.seen == [6 * 3600]
