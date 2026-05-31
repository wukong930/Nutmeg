"""Tests for post-V8 P1#5 — observation recorder extensions for
   single + pool sessions, and the NUTMEG_V4_OBSERVATION_DB env-var
   auto-record path on the new endpoints.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nutmeg.v4.observation import open_db
from nutmeg.v4.observation.recorder import (
    record_pool_session,
    record_single_session,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / "data" / "v4_model"


# ---------- record_single_session ------------------------------------

def _single_request_response(*, n_tickets: int = 2):
    """Build a fake SingleRecommendRequest + SingleRecommendResponse pair."""
    request = {
        "fixtures": [{
            "date": "2025-08-17", "league": "EPL",
            "home_team": "Arsenal", "away_team": "Liverpool",
            "psc_home": 2.10, "psc_draw": 3.40, "psc_away": 3.50,
        }],
        "bankroll": 500.0, "top_per_match": 1,
    }
    tickets = [
        {
            "match_id": f"EPL_Team{i}_vs_Other",
            "market_type": "1x2",
            "outcome": "H",
            "odds": 2.50,
            "probability": 0.55,
            "ev_per_unit": 0.125,
            "stake": 24.0 - i * 4,  # decreasing stakes
            "raw_kelly_stake": 24.3,
            "expected_return": 3.0,
        }
        for i in range(n_tickets)
    ]
    response = {
        "generated_at_utc": "2025-08-17T10:00:00+00:00",
        "model": {
            "trained_at_utc": "2025-06-01T00:00:00+00:00",
            "training_cutoff": "2025-06-01",
            "model_type": "catboost",
            "with_lineups": False,
        },
        "bankroll": 500.0,
        "n_fixtures": 1,
        "n_recommendations": n_tickets,
        "tickets": tickets,
        "total_stake": sum(t["stake"] for t in tickets),
        "total_expected_return": sum(t["expected_return"] for t in tickets),
    }
    return request, response


class TestRecordSingleSession:
    def test_writes_session_and_tickets(self, tmp_path):
        db = tmp_path / "obs.db"
        req, resp = _single_request_response(n_tickets=2)
        session_id = record_single_session(db, request=req, response=resp)
        assert session_id == 1
        with open_db(db) as conn:
            n_sess = conn.execute("SELECT COUNT(*) FROM recommendation_sessions").fetchone()[0]
            n_recs = conn.execute("SELECT COUNT(*) FROM parlay_recommendations").fetchone()[0]
        assert n_sess == 1
        assert n_recs == 2

    def test_tickets_marked_k_legs_1_not_compound(self, tmp_path):
        db = tmp_path / "obs.db"
        req, resp = _single_request_response()
        record_single_session(db, request=req, response=resp)
        with open_db(db) as conn:
            rows = list(conn.execute(
                "SELECT k_legs, is_compound FROM parlay_recommendations"
            ))
        for row in rows:
            assert row["k_legs"] == 1
            assert row["is_compound"] == 0  # SQLite int 0/1

    def test_stake_units_quantized_to_2(self, tmp_path):
        db = tmp_path / "obs.db"
        req, resp = _single_request_response()
        record_single_session(db, request=req, response=resp)
        with open_db(db) as conn:
            rows = list(conn.execute(
                "SELECT stake_units, kelly_stake FROM parlay_recommendations"
            ))
        # stake 24 → 12 units; stake 20 → 10 units
        units = sorted(r["stake_units"] for r in rows)
        assert units == [10, 12]

    def test_leg_json_settleable_shape(self, tmp_path):
        """legs_json must include match_id + market_type + selections so V4
        settlement can resolve outcomes."""
        import json
        db = tmp_path / "obs.db"
        req, resp = _single_request_response(n_tickets=1)
        record_single_session(db, request=req, response=resp)
        with open_db(db) as conn:
            row = conn.execute(
                "SELECT legs_json FROM parlay_recommendations LIMIT 1"
            ).fetchone()
        legs = json.loads(row["legs_json"])
        assert len(legs) == 1
        leg = legs[0]
        assert "match_id" in leg
        assert leg["market_type"] in ("1x2", "handicap_1x2")
        assert "selections" in leg and len(leg["selections"]) == 1
        sel = leg["selections"][0]
        for field in ("outcome", "odds", "probability", "edge"):
            assert field in sel

    def test_metadata_session_kind_single(self, tmp_path):
        import json
        db = tmp_path / "obs.db"
        req, resp = _single_request_response()
        record_single_session(db, request=req, response=resp)
        with open_db(db) as conn:
            row = conn.execute(
                "SELECT metadata_json FROM recommendation_sessions LIMIT 1"
            ).fetchone()
        meta = json.loads(row["metadata_json"])
        assert meta["session_kind"] == "single"
        assert meta["model"]["with_lineups"] is False

    def test_empty_tickets_writes_session_no_recs(self, tmp_path):
        db = tmp_path / "obs.db"
        req, resp = _single_request_response(n_tickets=0)
        session_id = record_single_session(db, request=req, response=resp)
        assert session_id == 1
        with open_db(db) as conn:
            n = conn.execute("SELECT COUNT(*) FROM parlay_recommendations").fetchone()[0]
        assert n == 0


# ---------- record_pool_session --------------------------------------

def _pool_request_response(*, n_kept: int = 2, n_skipped: int = 1):
    """Build a fake PoolRecommendRequest + PoolRecommendResponse with
    n_kept stake>0 tickets and n_skipped stake=0 (diagnostic) tickets."""
    request = {
        "fixtures": [
            {"date": "2025-08-17", "league": "EPL",
             "home_team": "Arsenal", "away_team": "Liverpool",
             "psc_home": 2.10, "psc_draw": 3.40, "psc_away": 3.50,
             "pick": "1x2_H"},
            {"date": "2025-08-17", "league": "EPL",
             "home_team": "Chelsea", "away_team": "Spurs",
             "psc_home": 2.30, "psc_draw": 3.30, "psc_away": 3.10,
             "pick": "1x2_H"},
        ],
        "n": 2, "bankroll": 1000.0,
    }
    tickets = []
    for i in range(n_kept):
        tickets.append({
            "legs": [
                {"match_id": f"EPL_A{i}_vs_B{i}", "market_type": "1x2",
                 "outcome": "H", "odds": 2.0, "probability": 0.55, "edge": 0.10},
                {"match_id": f"EPL_C{i}_vs_D{i}", "market_type": "1x2",
                 "outcome": "H", "odds": 1.8, "probability": 0.60, "edge": 0.08},
            ],
            "hit_probability": 0.33,
            "combined_odds": 3.60,
            "ev_per_unit": 0.188,
            "stake": 16.0 - i * 2,
            "raw_kelly_stake": 16.5,
            "expected_return": 3.0,
        })
    for i in range(n_skipped):
        tickets.append({
            "legs": [
                {"match_id": f"EPL_Z{i}_vs_Y", "market_type": "1x2",
                 "outcome": "H", "odds": 1.5, "probability": 0.40, "edge": -0.40},
            ],
            "hit_probability": 0.10,
            "combined_odds": 1.5,
            "ev_per_unit": -0.05,
            "stake": 0.0,  # diagnostic
            "raw_kelly_stake": 0.0,
            "expected_return": 0.0,
        })
    response = {
        "generated_at_utc": "2025-08-17T10:00:00+00:00",
        "model": {
            "trained_at_utc": "2025-06-01T00:00:00+00:00",
            "training_cutoff": "2025-06-01",
            "model_type": "catboost",
        },
        "bankroll": 1000.0,
        "m": 2, "n": 2,
        "n_combinations": n_kept + n_skipped,
        "n_selected": n_kept,
        "total_stake": sum(t["stake"] for t in tickets[:n_kept]),
        "total_expected_return": sum(t["expected_return"] for t in tickets[:n_kept]),
        "tickets": tickets,
    }
    return request, response


class TestRecordPoolSession:
    def test_records_selected_tickets_only(self, tmp_path):
        db = tmp_path / "obs.db"
        req, resp = _pool_request_response(n_kept=3, n_skipped=2)
        record_pool_session(db, request=req, response=resp)
        with open_db(db) as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM parlay_recommendations"
            ).fetchone()[0]
        # Only 3 (stake > 0) recorded; 2 diagnostic tickets dropped
        assert n == 3

    def test_tickets_marked_compound_with_k_legs(self, tmp_path):
        db = tmp_path / "obs.db"
        req, resp = _pool_request_response(n_kept=1, n_skipped=0)
        record_pool_session(db, request=req, response=resp)
        with open_db(db) as conn:
            row = conn.execute(
                "SELECT k_legs, is_compound FROM parlay_recommendations LIMIT 1"
            ).fetchone()
        assert row["is_compound"] == 1
        assert row["k_legs"] == 2  # the fake legs have 2 entries

    def test_metadata_session_kind_pool(self, tmp_path):
        import json
        db = tmp_path / "obs.db"
        req, resp = _pool_request_response(n_kept=1, n_skipped=0)
        record_pool_session(db, request=req, response=resp)
        with open_db(db) as conn:
            row = conn.execute(
                "SELECT metadata_json FROM recommendation_sessions LIMIT 1"
            ).fetchone()
        meta = json.loads(row["metadata_json"])
        assert meta["session_kind"] == "pool"
        assert meta["pool_n"] == 2
        assert meta["pool_n_combinations"] == 1  # n_kept + n_skipped

    def test_legs_keep_match_id_and_market_type(self, tmp_path):
        import json
        db = tmp_path / "obs.db"
        req, resp = _pool_request_response(n_kept=1, n_skipped=0)
        record_pool_session(db, request=req, response=resp)
        with open_db(db) as conn:
            row = conn.execute(
                "SELECT legs_json FROM parlay_recommendations LIMIT 1"
            ).fetchone()
        legs = json.loads(row["legs_json"])
        assert len(legs) == 2  # 2-leg pool ticket
        for leg in legs:
            assert "match_id" in leg
            assert "market_type" in leg
            assert leg["selections"][0]["outcome"] == "H"

    def test_n_fixtures_uses_m_not_pool_count(self, tmp_path):
        db = tmp_path / "obs.db"
        req, resp = _pool_request_response(n_kept=2, n_skipped=0)
        record_pool_session(db, request=req, response=resp)
        with open_db(db) as conn:
            row = conn.execute(
                "SELECT n_fixtures, n_recommendations FROM recommendation_sessions"
            ).fetchone()
        # m = 2 (pool size); n_recommendations = 2 (kept stake>0)
        assert row["n_fixtures"] == 2
        assert row["n_recommendations"] == 2


# ---------- Endpoint env-var auto-record -----------------------------

@pytest.fixture
def env_db(tmp_path, monkeypatch):
    """Set NUTMEG_V4_OBSERVATION_DB to a tmp DB path."""
    db = tmp_path / "auto_obs.db"
    monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(ARTIFACT_PATH))
    from nutmeg.v4.api import clear_artifact_cache
    clear_artifact_cache()
    yield db


@pytest.fixture
def env_no_db(monkeypatch):
    """Ensure NUTMEG_V4_OBSERVATION_DB is unset."""
    monkeypatch.delenv("NUTMEG_V4_OBSERVATION_DB", raising=False)
    monkeypatch.setenv("NUTMEG_V4_ARTIFACT_PATH", str(ARTIFACT_PATH))
    from nutmeg.v4.api import clear_artifact_cache
    clear_artifact_cache()
    yield


def _build_client():
    from nutmeg.v4.api import v4_router
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


@pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="v4 artifact not present")
class TestEndpointAutoRecord:
    def test_single_endpoint_records_when_env_set(self, env_db):
        client = _build_client()
        r = client.post("/api/v4/recommend/single", json={
            "fixtures": [{
                "date": "2025-08-17", "league": "EPL",
                "home_team": "Arsenal", "away_team": "Liverpool",
                "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60,
                "odds_1x2_H": 2.50, "odds_1x2_D": 3.30, "odds_1x2_A": 2.80,
            }],
            "bankroll": 500.0, "top_per_match": 1,
            "record_session": True,  # V9 W3 — must opt-in via request
        })
        assert r.status_code == 200
        # DB should now have one session
        assert env_db.exists()
        with open_db(env_db) as conn:
            n = conn.execute("SELECT COUNT(*) FROM recommendation_sessions").fetchone()[0]
        assert n == 1

    def test_single_ticket_echoes_psc_for_today_card_record(self, env_no_db):
        """V12 W8i — the 今日推荐 card records THIS pick at the user's 竞彩 SP, so
        each single ticket must echo the source fixture's Pinnacle inputs (the
        record endpoint recomputes P from these; it never trusts a client P)."""
        client = _build_client()
        r = client.post("/api/v4/recommend/single", json={
            "fixtures": [{
                "date": "2025-08-17", "league": "EPL",
                "home_team": "Arsenal", "away_team": "Liverpool",
                "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60,
                "psc_over25": 1.90, "psc_under25": 1.95,
                # Generous home odds so a +EV home ticket is virtually assured.
                "odds_1x2_H": 9.0, "odds_1x2_D": 3.30, "odds_1x2_A": 2.80,
            }],
            "bankroll": 500.0, "top_per_match": 3,
        })
        assert r.status_code == 200
        tickets = r.json()["tickets"]
        if not tickets:
            pytest.skip("model produced no +EV ticket for the test fixture")
        for tk in tickets:
            assert tk["psc_home"] == 2.85
            assert tk["psc_draw"] == 3.40
            assert tk["psc_away"] == 2.60
            assert tk["psc_over25"] == 1.90
            assert tk["psc_under25"] == 1.95

    def test_pool_endpoint_records_when_env_set(self, env_db):
        client = _build_client()
        r = client.post("/api/v4/recommend/pool", json={
            "fixtures": [
                {"date": "2025-08-17", "league": "EPL",
                 "home_team": "Arsenal", "away_team": "Liverpool",
                 "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60,
                 "pick": "1x2_H"},
                {"date": "2025-08-17", "league": "EPL",
                 "home_team": "Chelsea", "away_team": "Spurs",
                 "psc_home": 2.30, "psc_draw": 3.30, "psc_away": 3.10,
                 "pick": "1x2_H"},
            ],
            "n": 2, "bankroll": 1000.0,
            "record_session": True,  # V9 W3 — must opt-in via request
        })
        assert r.status_code == 200
        assert env_db.exists()
        with open_db(env_db) as conn:
            n = conn.execute("SELECT COUNT(*) FROM recommendation_sessions").fetchone()[0]
        assert n == 1

    def test_no_record_when_env_unset(self, env_no_db, tmp_path):
        client = _build_client()
        r = client.post("/api/v4/recommend/single", json={
            "fixtures": [{
                "date": "2025-08-17", "league": "EPL",
                "home_team": "Arsenal", "away_team": "Liverpool",
                "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60,
                "odds_1x2_H": 2.50, "odds_1x2_D": 3.30, "odds_1x2_A": 2.80,
            }],
            "bankroll": 500.0, "top_per_match": 1,
            "record_session": True,  # V9 W3 — env-off blocks anyway
        })
        assert r.status_code == 200
        # No DB written anywhere
        assert not (tmp_path / "auto_obs.db").exists()


# ---------- PoolLegResponse schema check -----------------------------

class TestPoolLegResponseSchema:
    """Pool legs must include match_id + market_type so recorded rows
    are settleable. Post-V8 P1#5 added these fields."""

    def test_pool_endpoint_returns_match_id_per_leg(self, env_no_db):
        if not ARTIFACT_PATH.exists():
            pytest.skip("v4 artifact not present")
        client = _build_client()
        r = client.post("/api/v4/recommend/pool", json={
            "fixtures": [
                {"date": "2025-08-17", "league": "EPL",
                 "home_team": "Arsenal", "away_team": "Liverpool",
                 "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60,
                 "pick": "1x2_H"},
                {"date": "2025-08-17", "league": "EPL",
                 "home_team": "Chelsea", "away_team": "Spurs",
                 "psc_home": 2.30, "psc_draw": 3.30, "psc_away": 3.10,
                 "pick": "1x2_H"},
            ],
            "n": 2, "bankroll": 1000.0,
        })
        assert r.status_code == 200
        body = r.json()
        for ticket in body["tickets"]:
            for leg in ticket["legs"]:
                assert "match_id" in leg, "PoolLegResponse must carry match_id"
                assert "market_type" in leg
                assert leg["market_type"] in ("1x2", "handicap_1x2")
