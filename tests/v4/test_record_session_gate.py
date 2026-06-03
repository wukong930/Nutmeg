"""Tests for V9 W3 — request.record_session + NUTMEG_V4_OBSERVATION_DB
   double gate. Both must be on for an endpoint to actually record.

All 3 endpoints (/recommend, /recommend/single, /recommend/pool) covered,
each with the 4 combinations of (env on/off, request flag on/off).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / "data" / "v4_model"


# ---------- fixtures --------------------------------------------------

def _build_client():
    from nutmeg.v4.api import clear_artifact_cache, v4_router
    clear_artifact_cache()
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_env_on(tmp_path, monkeypatch):
    """ENV set → server-side recording enabled."""
    db = tmp_path / "obs.db"
    monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(ARTIFACT_PATH))
    yield db


@pytest.fixture
def db_env_off(tmp_path, monkeypatch):
    """ENV unset → server-side recording disabled."""
    monkeypatch.delenv("NUTMEG_V4_OBSERVATION_DB", raising=False)
    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(ARTIFACT_PATH))
    # Return what the DB path WOULD be if recording happened (for negative checks)
    yield tmp_path / "would_be.db"


def _count_sessions(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    from nutmeg.v4.observation import open_db
    with open_db(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM recommendation_sessions"
        ).fetchone()[0]


# Request payload builders ---------------------------------------------

def _parlay_payload(record_session: bool):
    return {
        "fixtures": [
            {"date": "2025-08-17", "league": "EPL",
             "home_team": "Arsenal", "away_team": "Liverpool",
             "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60,
             "odds_1x2_H": 2.50, "odds_1x2_D": 3.30, "odds_1x2_A": 2.80},
            {"date": "2025-08-17", "league": "ESP_LA_LIGA",
             "home_team": "Real Madrid", "away_team": "Getafe",
             "psc_home": 1.40, "psc_draw": 4.80, "psc_away": 7.00,
             "odds_1x2_H": 1.45, "odds_1x2_D": 4.50, "odds_1x2_A": 6.50},
        ],
        "bankroll": 1000.0, "top_n": 5,
        "record_session": record_session,
    }


def _single_payload(record_session: bool):
    return {
        "fixtures": [{
            "date": "2025-08-17", "league": "EPL",
            "home_team": "Arsenal", "away_team": "Liverpool",
            "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60,
            "odds_1x2_H": 2.50, "odds_1x2_D": 3.30, "odds_1x2_A": 2.80,
        }],
        "bankroll": 500.0, "top_per_match": 1,
        "record_session": record_session,
    }


def _pool_payload(record_session: bool):
    return {
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
        "n": 2, "bankroll": 1000.0,
        "record_session": record_session,
    }


# ---------- schema-level: defaults ------------------------------------

class TestSchemaDefault:
    def test_recommend_default_false(self):
        from nutmeg.v4.api.schemas import RecommendRequest
        req = RecommendRequest(fixtures=[{
            "date": "2025-08-17", "league": "EPL",
            "home_team": "A", "away_team": "B",
            "psc_home": 2.0, "psc_draw": 3.0, "psc_away": 4.0,
        }], bankroll=500.0)
        assert req.record_session is False

    def test_single_default_false(self):
        from nutmeg.v4.api.schemas import SingleRecommendRequest
        req = SingleRecommendRequest(fixtures=[{
            "date": "2025-08-17", "league": "EPL",
            "home_team": "A", "away_team": "B",
            "psc_home": 2.0, "psc_draw": 3.0, "psc_away": 4.0,
        }], bankroll=500.0)
        assert req.record_session is False

    def test_pool_default_false(self):
        from nutmeg.v4.api.schemas import PoolRecommendRequest
        req = PoolRecommendRequest(fixtures=[{
            "date": "2025-08-17", "league": "EPL",
            "home_team": "A", "away_team": "B",
            "psc_home": 2.0, "psc_draw": 3.0, "psc_away": 4.0,
            "pick": "1x2_H",
        }], n=1, bankroll=500.0)
        assert req.record_session is False


# ---------- helper-level: _should_record_session ----------------------

class TestShouldRecordSessionHelper:
    def test_both_on_returns_db_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(tmp_path / "obs.db"))
        from nutmeg.v4.api.routes import _should_record_session
        assert _should_record_session(True) == str(tmp_path / "obs.db")

    def test_env_off_returns_none_even_if_req_on(self, monkeypatch):
        monkeypatch.delenv("NUTMEG_V4_OBSERVATION_DB", raising=False)
        from nutmeg.v4.api.routes import _should_record_session
        assert _should_record_session(True) is None

    def test_req_off_returns_none_even_if_env_on(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(tmp_path / "obs.db"))
        from nutmeg.v4.api.routes import _should_record_session
        assert _should_record_session(False) is None

    def test_both_off_returns_none(self, monkeypatch):
        monkeypatch.delenv("NUTMEG_V4_OBSERVATION_DB", raising=False)
        from nutmeg.v4.api.routes import _should_record_session
        assert _should_record_session(False) is None


# ---------- endpoint-level: 4 combos × 3 endpoints --------------------

@pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="v4 artifact not present")
class TestRecommendEndpointGate:
    """串关 endpoint — previously NEVER recorded (V5 W11 no-op).
       V9 W3 makes it follow the same 2-gate pattern as single/pool."""

    def test_env_on_req_on_records(self, db_env_on):
        client = _build_client()
        r = client.post("/api/v4/recommend", json=_parlay_payload(record_session=True))
        assert r.status_code == 200
        assert _count_sessions(db_env_on) == 1

    def test_env_on_req_off_no_record(self, db_env_on):
        client = _build_client()
        r = client.post("/api/v4/recommend", json=_parlay_payload(record_session=False))
        assert r.status_code == 200
        assert _count_sessions(db_env_on) == 0

    def test_env_off_req_on_no_record(self, db_env_off):
        client = _build_client()
        r = client.post("/api/v4/recommend", json=_parlay_payload(record_session=True))
        assert r.status_code == 200
        # No DB written anywhere
        assert not db_env_off.exists()

    def test_env_off_req_off_no_record(self, db_env_off):
        client = _build_client()
        r = client.post("/api/v4/recommend", json=_parlay_payload(record_session=False))
        assert r.status_code == 200
        assert not db_env_off.exists()


@pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="v4 artifact not present")
class TestSingleEndpointGate:
    def test_env_on_req_on_records(self, db_env_on):
        client = _build_client()
        r = client.post("/api/v4/recommend/single", json=_single_payload(record_session=True))
        assert r.status_code == 200
        assert _count_sessions(db_env_on) == 1

    def test_env_on_req_off_no_record(self, db_env_on):
        # Post-V8 P1#5 originally recorded on env alone. V9 W3 tightens
        # to require req.record_session=True. This was a behavior change.
        client = _build_client()
        r = client.post("/api/v4/recommend/single", json=_single_payload(record_session=False))
        assert r.status_code == 200
        assert _count_sessions(db_env_on) == 0

    def test_env_off_req_on_no_record(self, db_env_off):
        client = _build_client()
        r = client.post("/api/v4/recommend/single", json=_single_payload(record_session=True))
        assert r.status_code == 200
        assert not db_env_off.exists()


@pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="v4 artifact not present")
class TestPoolEndpointGate:
    def test_env_on_req_on_records(self, db_env_on):
        client = _build_client()
        r = client.post("/api/v4/recommend/pool", json=_pool_payload(record_session=True))
        assert r.status_code == 200
        assert _count_sessions(db_env_on) == 1

    def test_env_on_req_off_no_record(self, db_env_on):
        client = _build_client()
        r = client.post("/api/v4/recommend/pool", json=_pool_payload(record_session=False))
        assert r.status_code == 200
        assert _count_sessions(db_env_on) == 0

    def test_env_off_req_on_no_record(self, db_env_off):
        client = _build_client()
        r = client.post("/api/v4/recommend/pool", json=_pool_payload(record_session=True))
        assert r.status_code == 200
        assert not db_env_off.exists()


# ---------- dashboard HTML wiring -------------------------------------

class TestDashboardWiring:
    @pytest.fixture
    def html(self, db_env_off):
        # Need a client to fetch dashboard.html; env state doesn't matter here
        client = _build_client()
        r = client.get("/api/v4/dashboard")
        assert r.status_code == 200
        return r.text

    def test_all_three_tabs_have_checkbox(self, html):
        for cid in ("record-session",            # 串关 (existing since V5 W11)
                    "single-record-session",     # V9 W3 added
                    "pool-record-session"):      # V9 W3 added
            assert f'id="{cid}"' in html, f"checkbox missing: {cid}"

    def test_all_three_tabs_post_record_session(self, html):
        # Each tab's POST body should include record_session: <checked>
        # Look for the assignment patterns in JS
        for var in ("recordChecked",          # 串关
                    "recordCheckedSingle",    # 单关
                    "recordCheckedPool"):     # 复式
            assert var in html, f"JS missing var: {var}"
        # And the field name in each POST body
        assert html.count("record_session:") >= 3

    def test_visible_feedback_when_checked(self, html):
        # post-v9 P1#14: the literal string moved to the I18N dict.
        # 3 JS call sites now use t('status_recorded_req'). Verify:
        # (a) the i18n key is referenced 3 times (one per success branch)
        # (b) the literal still appears at least once (in the zh dictionary)
        assert html.count("t('status_recorded_req')") >= 3, \
            "3 success branches should call t('status_recorded_req')"
        assert "已请求录入观测库" in html, \
            "zh dictionary should still contain the original literal"

    # post-v9 P1#7: localStorage persistence across page reloads --------

    def test_localstorage_init_helper_present(self, html):
        # P1#7 added initRecordSessionPersistence + a key map
        assert "initRecordSessionPersistence" in html
        assert "RECORD_LS_KEYS" in html

    def test_localstorage_keys_namespaced(self, html):
        # All 3 keys should be under nutmeg.record_session.* namespace
        for key in (
            "nutmeg.record_session.parlay",
            "nutmeg.record_session.single",
            "nutmeg.record_session.pool",
        ):
            assert key in html, f"localStorage key missing: {key}"

    def test_localstorage_init_called_at_startup(self, html):
        # Must be invoked in the Init section, not just defined
        idx_def = html.index("function initRecordSessionPersistence")
        idx_call = html.rindex("initRecordSessionPersistence()")
        # The call site appears AFTER the definition
        assert idx_call > idx_def

    def test_localstorage_private_mode_safe(self, html):
        # Both read + write paths must be try/catch wrapped so private
        # browser mode (localStorage throws) doesn't break the page
        # Cheap heuristic: catch keyword should appear at least twice
        # in the helper's scope (read + write)
        helper_start = html.index("function initRecordSessionPersistence")
        helper_end = html.index("setInterval(loadHealth")
        helper_src = html[helper_start:helper_end]
        assert helper_src.count("catch") >= 2

    # post-v9 P1#8: real write-back confirmation via /sessions/latest -----

    def test_sessions_latest_helpers_present(self, html):
        assert "getLatestSessionId" in html
        assert "verifyRecordedAndAppend" in html
        assert "/observation/sessions/latest" in html

    def test_all_three_branches_capture_beforeid_and_verify(self, html):
        # Each of the 3 success branches should: (a) capture beforeId
        # before POST, (b) call verifyRecordedAndAppend after POST.
        # Per-tab var names: beforeId / beforeIdSingle / beforeIdPool
        for var in ("beforeId", "beforeIdSingle", "beforeIdPool"):
            assert var in html, f"missing beforeId variable: {var}"
        # The verify helper is called for all 3 status elements
        assert html.count("verifyRecordedAndAppend(") >= 3

    def test_verify_uses_correct_status_selectors(self, html):
        # Each branch verifies its own status element
        for sel in ("'#recommend-status'", "'#single-status'", "'#pool-status'"):
            assert f"verifyRecordedAndAppend({sel}" in html, (
                f"verify call missing for selector {sel}"
            )
