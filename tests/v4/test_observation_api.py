"""Tests for /v4/observation/* endpoints."""
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fresh_db_client(tmp_path):
    """A client with a fresh empty observation DB and no artifact required."""
    db = tmp_path / "obs.db"
    os.environ["NUTMEG_V4_OBSERVATION_DB"] = str(db)
    os.environ["NUTMEG_V4_ARTIFACT_PATH"] = str(REPO_ROOT / "data" / "v4_model")
    from nutmeg.v4.api import clear_artifact_cache, v4_router
    clear_artifact_cache()
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app), str(db)


@pytest.fixture
def populated_db_client(tmp_path):
    """Client whose observation DB has 1 session + 2 recs + 2 settled."""
    db = tmp_path / "obs.db"
    os.environ["NUTMEG_V4_OBSERVATION_DB"] = str(db)
    os.environ["NUTMEG_V4_ARTIFACT_PATH"] = str(REPO_ROOT / "data" / "v4_model")

    # Seed: insert a session + recs + outcomes + settle
    from nutmeg.v4.observation import open_db, record_session, settle_unsettled, upsert_outcome
    resp = {
        "generated_at_utc": "2026-05-22T10:00:00+00:00",
        "model": {"training_cutoff": "2025-06-01", "trained_at_utc": "2026-05-22T09:00:00+00:00"},
        "bankroll": 1000.0, "n_fixtures": 2, "n_recommendations": 2,
        "single_match_predictions": [
            {"date": "2025-08-17", "league": "EPL", "home_team": "Arsenal", "away_team": "Liverpool",
             "lambda_home": 1.5, "lambda_away": 1.0, "p_home_1x2": 0.50, "p_draw_1x2": 0.25, "p_away_1x2": 0.25},
            {"date": "2025-08-17", "league": "ITA_SERIE_A", "home_team": "Inter", "away_team": "Roma",
             "lambda_home": 1.4, "lambda_away": 1.1, "p_home_1x2": 0.45, "p_draw_1x2": 0.28, "p_away_1x2": 0.27},
        ],
        "recommendations": [
            {"rank": 1, "k_legs": 2, "is_compound": False, "stake_units": 1,
             "kelly_recommended_stake": 10.0, "expected_return": 5.0,
             "hit_probability": 0.20, "ev_per_unit": 0.50, "log_growth": 0.02,
             "legs": [
                {"match_id": "EPL_Arsenal_vs_Liverpool", "market_type": "1x2",
                 "selections": [{"outcome": "H", "odds": 2.5, "probability": 0.5, "edge": 0.25}]},
                {"match_id": "ITA_SERIE_A_Inter_vs_Roma", "market_type": "1x2",
                 "selections": [{"outcome": "H", "odds": 2.2, "probability": 0.45, "edge": -0.01}]},
            ]},
            {"rank": 2, "k_legs": 2, "is_compound": False, "stake_units": 1,
             "kelly_recommended_stake": 8.0, "expected_return": 3.0,
             "hit_probability": 0.18, "ev_per_unit": 0.40, "log_growth": 0.015,
             "legs": [
                {"match_id": "EPL_Arsenal_vs_Liverpool", "market_type": "1x2",
                 "selections": [{"outcome": "D", "odds": 3.4, "probability": 0.25, "edge": -0.15}]},
                {"match_id": "ITA_SERIE_A_Inter_vs_Roma", "market_type": "1x2",
                 "selections": [{"outcome": "H", "odds": 2.2, "probability": 0.45, "edge": -0.01}]},
            ]},
        ],
    }
    record_session(db, request={}, response=resp)
    with open_db(db) as conn:
        upsert_outcome(conn, match_date="2025-08-17", league="EPL",
                        home_team="Arsenal", away_team="Liverpool",
                        home_goals=2, away_goals=0)
        upsert_outcome(conn, match_date="2025-08-17", league="ITA_SERIE_A",
                        home_team="Inter", away_team="Roma",
                        home_goals=1, away_goals=0)
        settle_unsettled(conn)

    from nutmeg.v4.api import clear_artifact_cache, v4_router
    clear_artifact_cache()
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app), str(db)


class TestObservationHealth:
    def test_empty_db(self, fresh_db_client):
        client, _ = fresh_db_client
        # Fresh DB doesn't exist yet → status "empty"
        r = client.get("/api/v4/observation/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "empty"
        assert body["db_exists"] is False
        assert body["n_recommendations"] == 0

    def test_populated_db(self, populated_db_client):
        client, _ = populated_db_client
        r = client.get("/api/v4/observation/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["db_exists"] is True
        assert body["n_sessions"] == 1
        assert body["n_recommendations"] == 2
        assert body["n_outcomes"] == 2
        assert body["n_settled"] == 2


class TestROIEndpoint:
    def test_404_when_no_db(self, fresh_db_client):
        client, _ = fresh_db_client
        r = client.get("/api/v4/observation/roi")
        assert r.status_code == 404

    def test_roi_schema(self, populated_db_client):
        client, _ = populated_db_client
        r = client.get("/api/v4/observation/roi")
        assert r.status_code == 200
        body = r.json()
        # Top-level shape
        for k in ("headline", "by_k_legs", "by_league", "calibration", "weekly"):
            assert k in body
        h = body["headline"]
        assert h["n_settled"] == 2
        assert h["total_stake"] == pytest.approx(18.0)  # 10 + 8

    def test_roi_consistency(self, populated_db_client):
        """Pooled n in by_k_legs equals headline n_settled."""
        client, _ = populated_db_client
        body = client.get("/api/v4/observation/roi").json()
        sum_by_k = sum(r["n"] for r in body["by_k_legs"])
        assert sum_by_k == body["headline"]["n_settled"]


class TestSessionsEndpoint:
    def test_empty_when_no_db(self, fresh_db_client):
        client, _ = fresh_db_client
        r = client.get("/api/v4/observation/sessions")
        assert r.status_code == 200
        assert r.json()["n"] == 0

    def test_lists_sessions(self, populated_db_client):
        client, _ = populated_db_client
        r = client.get("/api/v4/observation/sessions?limit=10")
        assert r.status_code == 200
        body = r.json()
        assert body["n"] == 1
        sess = body["sessions"][0]
        assert sess["bankroll"] == 1000.0
        assert sess["n_fixtures"] == 2
        assert sess["n_recommendations"] == 2

    def test_limit_respected(self, populated_db_client):
        client, _ = populated_db_client
        r = client.get("/api/v4/observation/sessions?limit=0")
        # limit=0 may return all or none depending on impl; we just check no error
        assert r.status_code == 200


class TestPostOutcomes:
    def test_post_and_auto_settle(self, fresh_db_client):
        client, db = fresh_db_client
        # Need a recommendation first for settle to do anything; we just test that
        # outcomes can be posted and the settle_counts dict is returned.
        req = {
            "outcomes": [
                {"match_date": "2025-08-17", "league": "EPL",
                 "home_team": "Arsenal", "away_team": "Liverpool",
                 "home_goals": 2, "away_goals": 1},
                {"match_date": "2025-08-18", "league": "EPL",
                 "home_team": "Chelsea", "away_team": "Spurs",
                 "home_goals": 0, "away_goals": 0},
            ]
        }
        r = client.post("/api/v4/observation/outcomes", json=req)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["n_recorded"] == 2
        assert "settle_counts" in body

    def test_invalid_goals_returns_422(self, fresh_db_client):
        client, _ = fresh_db_client
        bad = {"outcomes": [{
            "match_date": "2025-08-17", "league": "EPL",
            "home_team": "A", "away_team": "B",
            "home_goals": -1, "away_goals": 1,
        }]}
        r = client.post("/api/v4/observation/outcomes", json=bad)
        assert r.status_code == 422

    def test_empty_batch_returns_422(self, fresh_db_client):
        client, _ = fresh_db_client
        r = client.post("/api/v4/observation/outcomes", json={"outcomes": []})
        assert r.status_code == 422


class TestDashboard:
    """Smoke-test the static dashboard HTML route."""
    def test_dashboard_served(self, fresh_db_client):
        client, _ = fresh_db_client
        r = client.get("/api/v4/dashboard")
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("text/html")
        html = r.text
        assert "<title>" in html
        assert "Nutmeg V4" in html
        assert "/api/v4" in html  # JS calls our endpoints


class TestLiveVsBacktestEndpoint:
    """V5 W11 — GET /v4/observation/live-vs-backtest."""

    def test_503_when_no_db(self, fresh_db_client):
        """fresh_db_client points NUTMEG_V4_OBSERVATION_DB at a path that
        doesn't exist on disk yet — the endpoint should 503 rather than
        crash trying to read."""
        client, _ = fresh_db_client
        r = client.get("/api/v4/observation/live-vs-backtest")
        assert r.status_code == 503
        assert "observation DB not found" in r.json()["detail"]

    def test_shape_with_populated_db(self, populated_db_client):
        client, _ = populated_db_client
        r = client.get("/api/v4/observation/live-vs-backtest?weeks=4")
        assert r.status_code == 200, r.text
        body = r.json()
        # Required keys
        assert body["weeks"] == 4
        assert body["tolerance_pp"] == 5.0
        for k in ("n_sessions", "n_settled", "n_hit", "n_partial", "n_miss",
                  "total_stake", "total_payout", "profit_loss", "roi",
                  "avg_hit_p_predicted", "actual_hit_rate"):
            assert k in body["live"]
        # No backtest provided from HTTP → backtest field null
        assert body["backtest"] is None
        # Default snapshot_phase = no filter → live counts include populated data
        # (created within last 4 weeks)
        assert body["live"]["n_settled"] >= 0

    def test_snapshot_phase_filter(self, populated_db_client):
        client, _ = populated_db_client
        r = client.get(
            "/api/v4/observation/live-vs-backtest?weeks=4&snapshot_phase=pre_close"
        )
        assert r.status_code == 200
        body = r.json()
        # The populated_db_client fixture used default 'closing' phase, so a
        # pre_close filter should see zero
        assert body["snapshot_phase"] == "pre_close"
        assert body["live"]["n_settled"] == 0

    def test_within_tolerance_by_default(self, populated_db_client):
        client, _ = populated_db_client
        body = client.get("/api/v4/observation/live-vs-backtest").json()
        # No backtest → not over tolerance (we only flag when both sides exist)
        assert body["over_tolerance"] is False
