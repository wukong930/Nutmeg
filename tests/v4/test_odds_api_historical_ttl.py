"""体检 F3 (2026-07-01) — fetch_historical_snapshot for a FUTURE timestamp returns
the ever-changing "latest available" line, so its cache must expire; a PAST
snapshot is immutable → cache forever."""
from __future__ import annotations

import datetime as dt
import json
import os
import time

from nutmeg.v4.data.sources import odds_api

_SK = "soccer_fifa_world_cup"


def _seed(tmp_path, snap_iso, age_hours):
    endpoint = f"historical/sports/{_SK}/odds"
    params = {"regions": "eu", "markets": "h2h", "oddsFormat": "decimal", "date": snap_iso}
    cf = odds_api._cache_path(endpoint, params, tmp_path)
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps({"data": [{"stale": 1}], "timestamp": snap_iso}))
    t = time.time() - age_hours * 3600
    os.utime(cf, (t, t))


def _mock_request(monkeypatch):
    calls: list[bool] = []

    def fake(endpoint, params, *, cache_dir=None, refresh=False, **kw):
        calls.append(refresh)
        return {"data": [{"fresh": 1}]} if refresh else {"data": [{"cached": 1}]}

    monkeypatch.setattr(odds_api, "_request", fake)
    return calls


def _future(days=3):
    return (dt.datetime.now(dt.UTC) + dt.timedelta(days=days)).strftime("%Y-%m-%dT23:00:00Z")


def _past(days=30):
    return (dt.datetime.now(dt.UTC) - dt.timedelta(days=days)).strftime("%Y-%m-%dT23:00:00Z")


def test_future_stale_cache_refetches(tmp_path, monkeypatch):
    iso = _future()
    _seed(tmp_path, iso, age_hours=7)      # older than the 6h TTL
    calls = _mock_request(monkeypatch)
    out = odds_api.fetch_historical_snapshot(_SK, iso, cache_dir=tmp_path)
    assert out["data"] == [{"fresh": 1}]
    assert True in calls


def test_past_snapshot_never_refetches(tmp_path, monkeypatch):
    iso = _past()
    _seed(tmp_path, iso, age_hours=999)    # ancient, but immutable
    calls = _mock_request(monkeypatch)
    odds_api.fetch_historical_snapshot(_SK, iso, cache_dir=tmp_path)
    assert calls == [False]                # permanent cache for a past snapshot


def test_future_fresh_cache_respected(tmp_path, monkeypatch):
    iso = _future()
    _seed(tmp_path, iso, age_hours=1)      # under the 6h TTL
    calls = _mock_request(monkeypatch)
    odds_api.fetch_historical_snapshot(_SK, iso, cache_dir=tmp_path)
    assert calls == [False]
