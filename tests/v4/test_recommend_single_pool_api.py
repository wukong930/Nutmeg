"""Tests for V8 W6 /api/v4/recommend/single + /pool endpoints + dashboard tabs.

Three layers:
  1. Endpoint shape + 503 when no artifact
  2. End-to-end happy path against the test artifact (skipped when
     data/v4_model isn't present, matching the pattern in test_api.py)
  3. Dashboard HTML regex checks for the new tabs + JS wiring
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
    os.environ["NUTMEG_V4_ARTIFACT_PATH"] = str(ARTIFACT_PATH)
    from nutmeg.v4.api import clear_artifact_cache, v4_router
    clear_artifact_cache()
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


@pytest.fixture(scope="module")
def degraded_client(tmp_path_factory):
    """Client with NO artifact path — for testing 503 responses."""
    tmp = tmp_path_factory.mktemp("no_artifact")
    os.environ["NUTMEG_V4_ARTIFACT_PATH"] = str(tmp / "missing")
    from nutmeg.v4.api import clear_artifact_cache, v4_router
    clear_artifact_cache()
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    yield TestClient(app)
    # Restore for downstream
    os.environ["NUTMEG_V4_ARTIFACT_PATH"] = str(ARTIFACT_PATH)
    clear_artifact_cache()


def _good_fixture(home="Arsenal", away="Liverpool", league="EPL"):
    return {
        "date": "2025-08-17", "league": league,
        "home_team": home, "away_team": away,
        "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60,
        "odds_1x2_H": 2.50, "odds_1x2_D": 3.30, "odds_1x2_A": 2.80,
    }


def _good_pool_fixture(home="Arsenal", away="Liverpool", league="EPL",
                       pick="1x2_H"):
    return {**_good_fixture(home=home, away=away, league=league), "pick": pick}


# ---------- Schema / 503 paths --------------------------------------------

class TestSingleEndpointShape:
    def test_503_when_no_artifact(self, degraded_client):
        r = degraded_client.post("/api/v4/recommend/single", json={
            "fixtures": [_good_fixture()],
            "bankroll": 500.0,
        })
        assert r.status_code == 503
        body = r.json()
        assert "V4 model artifact not loaded" in body["detail"]

    def test_validates_top_per_match_range(self, degraded_client):
        # top_per_match must be in [1, 3]
        r = degraded_client.post("/api/v4/recommend/single", json={
            "fixtures": [_good_fixture()],
            "bankroll": 500.0,
            "top_per_match": 5,
        })
        assert r.status_code == 422  # pydantic validation

    def test_requires_at_least_one_fixture(self, degraded_client):
        r = degraded_client.post("/api/v4/recommend/single", json={
            "fixtures": [],
            "bankroll": 500.0,
        })
        assert r.status_code == 422

    def test_validates_bankroll_positive(self, degraded_client):
        r = degraded_client.post("/api/v4/recommend/single", json={
            "fixtures": [_good_fixture()],
            "bankroll": 0,
        })
        assert r.status_code == 422


class TestPoolEndpointShape:
    def test_503_when_no_artifact(self, degraded_client):
        r = degraded_client.post("/api/v4/recommend/pool", json={
            "fixtures": [_good_pool_fixture(), _good_pool_fixture(home="C", away="D")],
            "n": 2, "bankroll": 500.0,
        })
        assert r.status_code == 503

    def test_validates_n_range(self, degraded_client):
        # n must be 1..8
        r = degraded_client.post("/api/v4/recommend/pool", json={
            "fixtures": [_good_pool_fixture()],
            "n": 9, "bankroll": 500.0,
        })
        assert r.status_code == 422

    def test_validates_pick_enum(self, degraded_client):
        # pick must be one of the 6 valid strings
        bad_fixture = _good_pool_fixture()
        bad_fixture["pick"] = "1x2_X"  # invalid
        r = degraded_client.post("/api/v4/recommend/pool", json={
            "fixtures": [bad_fixture],
            "n": 1, "bankroll": 500.0,
        })
        assert r.status_code == 422


# ---------- End-to-end (requires trained artifact) --------------------

@pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="v4 artifact not present")
class TestSingleEndpointE2E:
    def test_returns_recommendations(self, client):
        r = client.post("/api/v4/recommend/single", json={
            "fixtures": [
                _good_fixture("Arsenal", "Liverpool"),
                _good_fixture("Real Madrid", "Getafe", "ESP_LA_LIGA"),
            ],
            "bankroll": 1000.0,
            "top_per_match": 1,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        # Required envelope fields
        for field in ("generated_at_utc", "model", "bankroll", "n_fixtures",
                       "n_recommendations", "tickets", "total_stake",
                       "total_expected_return"):
            assert field in body, f"missing: {field}"
        assert body["n_fixtures"] == 2
        # Each ticket has the documented schema
        for t in body["tickets"]:
            assert t["outcome"] in ("H", "D", "A")
            assert t["market_type"] in ("1x2", "handicap_1x2")
            assert t["odds"] > 1.0
            assert 0.0 <= t["probability"] <= 1.0
            assert t["stake"] % 2 == 0  # ¥2 quantized
            assert t["expected_return"] == pytest.approx(
                t["stake"] * t["ev_per_unit"]
            )
            # V12 W7 — ticket carries match identity (today single board reads
            # these directly, doesn't parse match_id).
            assert t["home_team"] and t["away_team"] and t["league"] and t["date"]
            assert t["match_id"] == (
                f"{t['league']}_{t['home_team']}_vs_{t['away_team']}"
            )

    def test_tickets_carry_match_identity_v12_w7(self, client):
        """V12 W7 regression: the 今日推荐 single board renders home_team/league/
        date straight off each ticket — before the fix they were absent and the
        card showed 'VS · undefined · undefined'. An inflated +EV outcome
        guarantees ≥1 ticket so this always exercises the path."""
        fx = _good_fixture("Vissel Kobe", "Kashima", "JPN_J1")
        fx["psc_away"] = 6.0      # model P × 6.0 clears the EV gate → guaranteed
        fx["odds_1x2_A"] = 6.0
        r = client.post("/api/v4/recommend/single", json={
            "fixtures": [fx], "bankroll": 1000.0, "top_per_match": 3,
        })
        assert r.status_code == 200, r.text
        tickets = r.json()["tickets"]
        assert tickets, "inflated +EV outcome should yield ≥1 ticket"
        for t in tickets:
            assert t["home_team"] == "Vissel Kobe"
            assert t["away_team"] == "Kashima"
            assert t["league"] == "JPN_J1"
            assert t["date"] == "2025-08-17"
            assert t["match_id"] == "JPN_J1_Vissel Kobe_vs_Kashima"


@pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="v4 artifact not present")
class TestNoPinnacleFallbackForRecommendation:
    """拔根 regression: a 竞彩 recommendation requires a real 竞彩 SP. When only
    Pinnacle (psc_*) is present, /recommend/single and /recommend must NOT fall
    back to Pinnacle-as-SP. That fallback computed EV = model_P × Pinnacle_odds
    − 1 — model-vs-sharp divergence (noise) surfaced as a 'best bet' (the
    EV-vs-Pinnacle bug). These fixtures (psc_away inflated to 6.0) used to fire a
    ticket via the fallback; with the fallback gone they must yield none.
    """

    def _psc_only(self, home="Vissel Kobe", away="Kashima", league="JPN_J1"):
        # A balanced fixture (psc 2.85/3.40/2.60) with its 竞彩 1X2 odds STRIPPED
        # — only Pinnacle (psc_*) remains. The OLD code fell back to psc as the
        # bet odds (model P_home × 2.85 ≈ +EV → a noise ticket fired); the fix
        # yields none. Balanced psc also keeps model P(away) high enough that
        # adding a real 竞彩 SP below still clears the gate.
        fx = _good_fixture(home, away, league)
        for k in ("odds_1x2_H", "odds_1x2_D", "odds_1x2_A"):
            fx.pop(k, None)
        return fx

    def test_single_psc_only_yields_no_recommendation(self, client):
        r = client.post("/api/v4/recommend/single", json={
            "fixtures": [self._psc_only()], "bankroll": 1000.0, "top_per_match": 3,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["n_fixtures"] == 1
        assert body["n_recommendations"] == 0, (
            "psc-only fixture must NOT produce a Pinnacle-fallback recommendation"
        )
        assert body["tickets"] == []
        assert body["total_stake"] == 0.0

    def test_single_with_real_lottery_odds_still_recommends(self, client):
        # A FULL 竞彩 1X2 line (胜平负 is one all-or-nothing market) with a juicy
        # away price → the genuine +EV path is intact: the fix removes the
        # Pinnacle fallback, not the real recommender.
        fx = _good_fixture("Vissel Kobe", "Kashima", "JPN_J1")
        fx["odds_1x2_A"] = 6.0
        r = client.post("/api/v4/recommend/single", json={
            "fixtures": [fx], "bankroll": 1000.0, "top_per_match": 3,
        })
        assert r.status_code == 200, r.text
        assert r.json()["tickets"], "a real 竞彩 SP should still yield a ticket"

    def test_parlay_psc_only_yields_no_recommendation(self, client):
        r = client.post("/api/v4/recommend", json={
            "fixtures": [
                self._psc_only("Vissel Kobe", "Kashima", "JPN_J1"),
                self._psc_only("Urawa", "Gamba Osaka", "JPN_J1"),
            ],
            "bankroll": 1000.0, "k_min": 2, "k_max": 2, "top_n": 10,
        })
        assert r.status_code == 200, r.text
        assert r.json()["n_recommendations"] == 0, (
            "psc-only legs carry no rankable 竞彩 selection → no parlay"
        )


@pytest.mark.skipif(not ARTIFACT_PATH.exists(), reason="v4 artifact not present")
class TestPoolEndpointE2E:
    def test_returns_pool_recommendations(self, client):
        fixtures = [
            _good_pool_fixture("Arsenal", "Liverpool", pick="1x2_H"),
            _good_pool_fixture("Real Madrid", "Getafe", "ESP_LA_LIGA", pick="1x2_H"),
            _good_pool_fixture("Chelsea", "Spurs", pick="1x2_H"),
        ]
        r = client.post("/api/v4/recommend/pool", json={
            "fixtures": fixtures, "n": 2, "bankroll": 1000.0,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["m"] == 3
        assert body["n"] == 2
        # C(3, 2) = 3
        assert body["n_combinations"] == 3
        assert len(body["tickets"]) == 3
        # tickets sorted by ev_per_unit desc
        evs = [t["ev_per_unit"] for t in body["tickets"]]
        assert evs == sorted(evs, reverse=True)
        # all stakes ¥2 quantized
        for t in body["tickets"]:
            assert t["stake"] % 2 == 0
            assert len(t["legs"]) == 2

    def test_n_greater_than_m_returns_422(self, client):
        r = client.post("/api/v4/recommend/pool", json={
            "fixtures": [_good_pool_fixture()],
            "n": 2, "bankroll": 500.0,
        })
        assert r.status_code == 422
        assert "only" in r.json()["detail"]


# ---------- Dashboard HTML checks --------------------------------------

class TestDashboardSinglePoolTabs:
    @pytest.fixture
    def html(self, degraded_client):
        r = degraded_client.get("/api/v4/dashboard")
        assert r.status_code == 200
        return r.text

    def test_tabs_present(self, html):
        for needle in ("① 单关", "② 串关", "③ 复式"):
            assert needle in html, f"missing tab label: {needle}"

    def test_tab_panel_ids_present(self, html):
        for tab_id in ("tab-single", "tab-recommend", "tab-pool"):
            assert f'id="{tab_id}"' in html

    def test_endpoint_paths_wired(self, html):
        assert "/recommend/single" in html
        assert "/recommend/pool" in html

    def test_form_inputs_present(self, html):
        for input_id in ("single-bankroll", "single-top-per-match",
                         "single-kelly-fraction",
                         "pool-bankroll", "pool-n", "pool-max-budget",
                         "pool-kelly-fraction"):
            assert f'id="{input_id}"' in html

    def test_render_functions_defined(self, html):
        assert "function renderSingleRecommendations" in html
        assert "function renderPoolRecommendations" in html

    def test_market_label_chinese(self, html):
        # 胜平负 / 让球胜平负 labels referenced in render code
        assert "胜平负" in html
        assert "让球胜平负" in html

    def test_pool_sample_includes_pick_field(self, html):
        # POOL_SAMPLE constant has at least one row with pick: 'hc_H'
        assert "POOL_SAMPLE" in html
        assert "'1x2_H'" in html
        assert "'hc_H'" in html
