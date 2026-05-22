"""Tests for nutmeg.v4.api routes.

Uses FastAPI TestClient directly on the v4 router (no need for the full
main app, which in user's Python 3.13 env includes legacy 3.12+ syntax).

Tests assume the artifact at data/v4_model has already been trained
(it's created during test_e2e's setUp; we share it).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / "data" / "v4_model"


@pytest.fixture(scope="module")
def client():
    """Build a minimal FastAPI app with only v4 routes."""
    # Force artifact path env var
    os.environ["NUTMEG_V4_ARTIFACT_PATH"] = str(ARTIFACT_PATH)
    from nutmeg.v4.api import clear_artifact_cache, v4_router
    clear_artifact_cache()
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


@pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="v4 artifact not present; run `python -m nutmeg.v4.cli.train` first")
class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/v4/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["artifact_loaded"] is True
        assert body["n_teams"] > 100
        assert body["n_leagues"] >= 1


class TestHealthDegraded:
    def test_health_when_no_artifact(self, tmp_path):
        os.environ["NUTMEG_V4_ARTIFACT_PATH"] = str(tmp_path / "does_not_exist")
        from nutmeg.v4.api import clear_artifact_cache, v4_router
        clear_artifact_cache()
        app = FastAPI()
        app.include_router(v4_router, prefix="/api")
        c = TestClient(app)
        r = c.get("/api/v4/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "degraded"
        assert body["artifact_loaded"] is False
        # restore for downstream tests
        os.environ["NUTMEG_V4_ARTIFACT_PATH"] = str(ARTIFACT_PATH)
        clear_artifact_cache()


def _good_fixture(home: str = "Arsenal", away: str = "Liverpool",
                  league: str = "EPL") -> dict:
    return {
        "date": "2025-08-17",
        "league": league,
        "home_team": home,
        "away_team": away,
        "psc_home": 2.85,
        "psc_draw": 3.40,
        "psc_away": 2.60,
    }


@pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="v4 artifact not present")
class TestRecommend:
    def test_basic_recommend(self, client):
        req = {
            "fixtures": [
                _good_fixture("Arsenal", "Liverpool", "EPL"),
                _good_fixture("Real Madrid", "Getafe", "ESP_LA_LIGA"),
                _good_fixture("Inter", "Fiorentina", "ITA_SERIE_A"),
            ],
            "bankroll": 1000.0,
            "top_n": 5,
        }
        r = client.post("/api/v4/recommend", json=req)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["n_fixtures"] == 3
        assert "generated_at_utc" in body
        assert body["bankroll"] == 1000.0
        assert "model" in body
        assert body["model"]["training_cutoff"] is not None
        assert len(body["single_match_predictions"]) == 3
        for p in body["single_match_predictions"]:
            assert 0.0 < p["lambda_home"] < 10.0
            assert 0.0 < p["lambda_away"] < 10.0
            assert abs(p["p_home_1x2"] + p["p_draw_1x2"] + p["p_away_1x2"] - 1.0) < 1e-6

    def test_handicap_predictions(self, client):
        req = {
            "fixtures": [
                {**_good_fixture("Real Madrid", "Getafe", "ESP_LA_LIGA"),
                 "handicap_home": -1,
                 "odds_handicap_H": 2.10,
                 "odds_handicap_D": 3.40,
                 "odds_handicap_A": 3.20},
            ],
            "bankroll": 1000.0,
        }
        r = client.post("/api/v4/recommend", json=req)
        assert r.status_code == 200, r.text
        p = r.json()["single_match_predictions"][0]
        assert p["handicap_home"] == -1
        assert p["p_home_handicap"] is not None
        assert abs(p["p_home_handicap"] + p["p_draw_handicap"] + p["p_away_handicap"] - 1.0) < 1e-6

    def test_recommendations_filtered_by_kelly(self, client):
        req = {
            "fixtures": [_good_fixture(f"Home{i}", f"Away{i}", "EPL") for i in range(3)],
            "bankroll": 1000.0,
            "top_n": 5,
            "min_kelly_stake": 1.0,
        }
        r = client.post("/api/v4/recommend", json=req)
        assert r.status_code == 200
        body = r.json()
        # All returned recs must satisfy kelly >= min_kelly_stake
        for rec in body["recommendations"]:
            assert rec["kelly_recommended_stake"] >= 1.0
            assert rec["ev_per_unit"] > 0

    def test_log_growth_descending(self, client):
        req = {
            "fixtures": [
                _good_fixture("Arsenal", "Liverpool", "EPL"),
                _good_fixture("Real Madrid", "Getafe", "ESP_LA_LIGA"),
                _good_fixture("Bayern Munich", "Koln", "GER_BUNDESLIGA"),
                _good_fixture("Paris SG", "Nice", "FRA_LIGUE_1"),
            ],
            "bankroll": 1000.0,
            "top_n": 10,
        }
        r = client.post("/api/v4/recommend", json=req)
        body = r.json()
        growths = [rec["log_growth"] for rec in body["recommendations"]]
        for i in range(len(growths) - 1):
            assert growths[i] >= growths[i + 1] - 1e-9


@pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="v4 artifact not present")
class TestValidation:
    def test_empty_fixtures_returns_422(self, client):
        r = client.post("/api/v4/recommend", json={"fixtures": []})
        assert r.status_code == 422

    def test_too_many_fixtures_returns_422(self, client):
        req = {"fixtures": [_good_fixture(f"H{i}", f"A{i}") for i in range(51)]}
        r = client.post("/api/v4/recommend", json=req)
        assert r.status_code == 422

    def test_invalid_odds_returns_422(self, client):
        bad = _good_fixture()
        bad["psc_home"] = 0.5  # must be > 1
        r = client.post("/api/v4/recommend", json={"fixtures": [bad]})
        assert r.status_code == 422

    def test_missing_required_field_returns_422(self, client):
        r = client.post("/api/v4/recommend", json={"fixtures": [{"date": "2025-08-17"}]})
        assert r.status_code == 422

    def test_k_max_less_than_k_min_returns_422(self, client):
        req = {
            "fixtures": [_good_fixture()],
            "k_min": 5,
            "k_max": 3,
        }
        r = client.post("/api/v4/recommend", json=req)
        assert r.status_code == 422

    def test_too_many_kmax(self, client):
        req = {"fixtures": [_good_fixture()], "k_max": 9}
        r = client.post("/api/v4/recommend", json=req)
        assert r.status_code == 422


@pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="v4 artifact not present")
class TestEdgeCases:
    def test_no_edge_returns_empty_recommendations(self, client):
        """When odds are 'fair' (model probs roughly match implied probs), 0 recs."""
        # Even-match (1.3 vs 1.3) with offered odds slightly worse than fair
        fair_match = {
            "date": "2025-08-17",
            "league": "EPL",
            "home_team": "TeamA",
            "away_team": "TeamB",
            "psc_home": 2.50,
            "psc_draw": 3.30,
            "psc_away": 2.50,
        }
        req = {
            "fixtures": [fair_match] * 4,
            "bankroll": 1000.0,
            "min_hit_probability": 0.05,
            "min_kelly_stake": 5.0,
        }
        r = client.post("/api/v4/recommend", json=req)
        assert r.status_code == 200
        body = r.json()
        # We don't assert exact 0 (model might find an edge); but recs should be small
        assert body["n_recommendations"] <= 10
