"""体检 A3 — record-failure visibility.

Before this fix every recorder call swallowed DB-write exceptions and the
response came back recorded=False — indistinguishable from "gate off", so the
UI told the user "记录开关未开" while the bet silently vanished. Now:

- /observation/record-bet (recording IS its whole job) → HTTP 503 on failure.
- compute+record endpoints (/recommend, /recommend/single, /recommend/pool,
  /recommend/market-handicap, /recommend/parlay — identical pattern) → 200
  with ``record_failed=True`` so the dashboard shows a red ⚠️ instead of the
  amber gate-off note.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / "data" / "v4_model"
DASH = REPO_ROOT / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _build_client():
    from nutmeg.v4.api import clear_artifact_cache, v4_router
    clear_artifact_cache()
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def env_on(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(tmp_path / "obs.db"))
    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(ARTIFACT_PATH))
    yield


def _boom(*_a, **_k):
    raise RuntimeError("synthetic DB failure")


_MANUAL = {
    "league": "WC", "date": "2026-06-11", "home_team": "A", "away_team": "B",
    "outcome": "H", "odds": 2.0, "probability": 0.5, "stake": 10.0,
    "record_session": True,
}

_SINGLE = {
    "fixtures": [{
        "date": "2025-08-17", "league": "EPL",
        "home_team": "Arsenal", "away_team": "Liverpool",
        "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60,
        "odds_1x2_H": 2.50, "odds_1x2_D": 3.30, "odds_1x2_A": 2.80,
    }],
    "bankroll": 500.0, "top_per_match": 1, "record_session": True,
}

_POOL = {
    "fixtures": [
        {"date": "2025-08-17", "league": "EPL",
         "home_team": "Arsenal", "away_team": "Liverpool",
         "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60,
         "odds_1x2_H": 2.85, "odds_1x2_D": 3.40, "odds_1x2_A": 2.60,
         "pick": "1x2_H"},
        {"date": "2025-08-17", "league": "EPL",
         "home_team": "Chelsea", "away_team": "Spurs",
         "psc_home": 2.30, "psc_draw": 3.30, "psc_away": 3.10,
         "odds_1x2_H": 2.30, "odds_1x2_D": 3.30, "odds_1x2_A": 3.10,
         "pick": "1x2_H"},
    ],
    "n": 2, "bankroll": 1000.0, "record_session": True,
}

_RECOMMEND = {
    "fixtures": _POOL["fixtures"][:2],
    "bankroll": 1000.0, "top_n": 5, "record_session": True,
}

# Strong home + generous 让球 SP ⇒ +EV leg so the record path actually runs.
_MKT_HC = {
    "league": "WC", "date": "2026-06-11", "home_team": "A", "away_team": "B",
    "psc_home": 1.30, "psc_draw": 5.50, "psc_away": 9.00,
    "handicap_home": -1, "odds_handicap_H": 3.0, "record_session": True,
}


class TestManualBetFailsLoudly:
    def test_db_failure_returns_503(self, env_on, monkeypatch):
        import nutmeg.v4.observation as obs
        monkeypatch.setattr(obs, "record_manual_bet", _boom)
        r = _build_client().post("/api/v4/observation/record-bet", json=_MANUAL)
        assert r.status_code == 503
        assert "未入库" in r.json()["detail"]

    def test_gate_off_still_200(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NUTMEG_V4_OBSERVATION_DB", raising=False)
        monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(ARTIFACT_PATH))
        r = _build_client().post("/api/v4/observation/record-bet", json=_MANUAL)
        assert r.status_code == 200
        assert r.json()["recorded"] is False


class TestComputeEndpointsFlagFailure:
    def test_recommend_record_failed(self, env_on, monkeypatch):
        import nutmeg.v4.observation as obs
        monkeypatch.setattr(obs, "record_session", _boom)
        r = _build_client().post("/api/v4/recommend", json=_RECOMMEND)
        assert r.status_code == 200
        assert r.json()["record_failed"] is True

    def test_single_record_failed(self, env_on, monkeypatch):
        import nutmeg.v4.observation.recorder as rec
        monkeypatch.setattr(rec, "record_single_session", _boom)
        r = _build_client().post("/api/v4/recommend/single", json=_SINGLE)
        assert r.status_code == 200
        assert r.json()["record_failed"] is True

    def test_pool_record_failed(self, env_on, monkeypatch):
        import nutmeg.v4.observation.recorder as rec
        monkeypatch.setattr(rec, "record_pool_session", _boom)
        r = _build_client().post("/api/v4/recommend/pool", json=_POOL)
        assert r.status_code == 200
        assert r.json()["record_failed"] is True

    def test_market_handicap_record_failed(self, env_on, monkeypatch):
        import nutmeg.v4.observation.recorder as rec
        monkeypatch.setattr(rec, "record_market_handicap_session", _boom)
        r = _build_client().post("/api/v4/recommend/market-handicap", json=_MKT_HC)
        assert r.status_code == 200
        body = r.json()
        assert body["record_failed"] is True
        assert body["recorded"] is False

    def test_market_handicap_success_not_flagged(self, env_on):
        # control: real recorder, tmp DB → recorded=True, record_failed=False
        r = _build_client().post("/api/v4/recommend/market-handicap", json=_MKT_HC)
        assert r.status_code == 200
        body = r.json()
        assert body["recorded"] is True
        assert body["record_failed"] is False


class TestDashboardWiring:
    def test_i18n_and_consumers(self):
        html = DASH.read_text(encoding="utf-8")
        assert html.count("rec_record_failed:") >= 2  # zh + en locales
        assert "b.record_failed" in html
        assert "data.record_failed" in html
        assert "recordFailed" in html

    def test_cache_version_bumped(self):
        routes = (REPO_ROOT / "apps/api/src/nutmeg/v4/api/routes.py").read_text()
        assert "nutmeg-v39-fe-recfail" in routes
