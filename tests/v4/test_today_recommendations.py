"""V10 W1 Track A — tests for POST /v4/today-recommendations.

The endpoint:
  1. Server-side fetches fixtures via _gather_rows (V7 W1)
  2. Runs recommend_single + recommend with default bankroll
  3. Returns unified TodayRecommendationsResponse

We mock _gather_rows so tests don't hit API-Football. Three scenarios:
  A. fixtures present → both single + parlay populated; summary aggregates
  B. 0 fixtures (API down or no matches today) → both None, summary zeros
  C. 1 fixture → single populated, parlay None (needs ≥2 for k_min=2)
  D. include=["single"] → parlay skipped even with many fixtures
  E. invalid date → 422
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_fixture_row(home: str, away: str, league: str = "EPL",
                      psc_h: float = 2.00, psc_d: float = 3.40, psc_a: float = 3.60,
                      dt: str = "2026-05-25") -> dict:
    """Build a fake CSV row matching ingest_odds.CSV_COLUMNS shape."""
    return {
        "date": dt,
        "league": league,
        "home_team": home,
        "away_team": away,
        "psc_home": psc_h,
        "psc_draw": psc_d,
        "psc_away": psc_a,
        "psc_over25": "",
        "psc_under25": "",
        "handicap_home": "",
        "odds_1x2_H": psc_h,
        "odds_1x2_D": psc_d,
        "odds_1x2_A": psc_a,
        "odds_handicap_H": "",
        "odds_handicap_D": "",
        "odds_handicap_A": "",
    }


@pytest.fixture
def client():
    """FastAPI test client with v4 router mounted."""
    from nutmeg.v4.api import v4_router
    import os
    # Point artifact path at production lineup-aware (default since P1#18).
    # Falls back gracefully if missing — service returns 503.
    os.environ.setdefault(
        "NUTMEG_V4_ARTIFACT_PATH",
        str(REPO_ROOT / "data" / "v4_model_cat_lineups"),
    )
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


class TestFixtureRowsToInputs:
    """The pure-function helper. No HTTP."""

    def test_drops_rows_missing_psc(self):
        from nutmeg.v4.api.routes import _fixture_rows_to_inputs
        rows = [
            _make_fixture_row("Arsenal", "Liverpool"),
            {**_make_fixture_row("Chelsea", "Spurs"), "psc_home": ""},  # missing
        ]
        out = _fixture_rows_to_inputs(rows)
        assert len(out) == 1
        assert out[0].home_team == "Arsenal"

    def test_coerces_string_numerics(self):
        from nutmeg.v4.api.routes import _fixture_rows_to_inputs
        rows = [{
            "date": "2026-05-25",
            "league": "EPL",
            "home_team": "A",
            "away_team": "B",
            "psc_home": "1.85",     # string
            "psc_draw": "3.50",     # string
            "psc_away": "4.00",     # string
        }]
        out = _fixture_rows_to_inputs(rows)
        assert len(out) == 1
        assert out[0].psc_home == 1.85

    def test_tolerates_per_row_failures(self):
        """Bad row shape shouldn't 500 the whole endpoint."""
        from nutmeg.v4.api.routes import _fixture_rows_to_inputs
        rows = [
            _make_fixture_row("A", "B"),
            {"date": "garbage", "league": "X"},  # invalid shape → drops
            _make_fixture_row("C", "D"),
        ]
        out = _fixture_rows_to_inputs(rows)
        assert len(out) == 2


class TestTodayRecommendationsHappyPath:
    """Fixtures mocked at the _gather_rows boundary."""

    def test_returns_unified_response_with_fixtures(self, client):
        # 5 fixtures (enough for both single + parlay)
        fake_rows = [
            _make_fixture_row("Arsenal", "Liverpool", psc_h=1.90),
            _make_fixture_row("Chelsea", "Manchester United", psc_h=2.50),
            _make_fixture_row("Real Madrid", "Barcelona", league="ESP_LA_LIGA", psc_h=2.10),
            _make_fixture_row("Bayern", "Dortmund", league="GER_BUNDESLIGA", psc_h=1.65),
            _make_fixture_row("PSG", "Marseille", league="FRA_LIGUE_1", psc_h=1.45),
        ]
        with patch(
            "nutmeg.v4.cli.ingest_odds._gather_rows",
            return_value=(fake_rows, 5, 0),
        ):
            resp = client.post(
                "/api/v4/today-recommendations",
                json={"leagues": ["EPL"], "bankroll": 1000.0, "date": "2026-05-25"},
            )

        if resp.status_code == 503:
            pytest.skip("Production artifact not available — skip integration test")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["fixtures_fetched"] == 5
        assert body["date"] == "2026-05-25"
        assert body["bankroll"] == 1000.0
        assert body["summary"]["total_recs"] >= 0
        # Either single or parlay (or both) should have a result, OR both
        # None if EV gate filtered everything out. Both being None is valid.

    def test_empty_fixtures_returns_zero_summary(self, client):
        """No fixtures today → 200 OK, both arms None, summary zeros."""
        with patch(
            "nutmeg.v4.cli.ingest_odds._gather_rows",
            return_value=([], 0, 0),
        ):
            resp = client.post(
                "/api/v4/today-recommendations",
                json={"leagues": ["EPL"], "bankroll": 1000.0, "date": "2026-05-25"},
            )

        if resp.status_code == 503:
            pytest.skip("Production artifact not available")

        assert resp.status_code == 200
        body = resp.json()
        assert body["fixtures_fetched"] == 0
        assert body["single"] is None
        assert body["parlay"] is None
        assert body["summary"]["total_recs"] == 0
        assert body["summary"]["total_stake"] == 0.0
        assert body["summary"]["weighted_ev"] is None

    def test_single_fixture_only_runs_single_arm(self, client):
        """1 fixture → single can run, parlay cannot (needs ≥2 for k_min=2)."""
        fake_rows = [_make_fixture_row("Arsenal", "Liverpool")]
        with patch(
            "nutmeg.v4.cli.ingest_odds._gather_rows",
            return_value=(fake_rows, 1, 0),
        ):
            resp = client.post(
                "/api/v4/today-recommendations",
                json={"leagues": ["EPL"], "bankroll": 1000.0, "date": "2026-05-25"},
            )

        if resp.status_code == 503:
            pytest.skip("Production artifact not available")

        assert resp.status_code == 200
        body = resp.json()
        assert body["fixtures_fetched"] == 1
        # parlay was skipped (need >= 2 fixtures)
        assert body["parlay"] is None

    def test_include_filter_skips_arm(self, client):
        """include=['single'] → parlay must be None even with many fixtures."""
        fake_rows = [_make_fixture_row(f"H{i}", f"A{i}") for i in range(5)]
        with patch(
            "nutmeg.v4.cli.ingest_odds._gather_rows",
            return_value=(fake_rows, 5, 0),
        ):
            resp = client.post(
                "/api/v4/today-recommendations",
                json={
                    "leagues": ["EPL"], "bankroll": 1000.0,
                    "date": "2026-05-25", "include": ["single"],
                },
            )

        if resp.status_code == 503:
            pytest.skip("Production artifact not available")

        assert resp.status_code == 200
        body = resp.json()
        assert body["parlay"] is None

    def test_invalid_date_returns_422(self, client):
        resp = client.post(
            "/api/v4/today-recommendations",
            json={"leagues": ["EPL"], "bankroll": 1000.0, "date": "not-a-date"},
        )
        assert resp.status_code == 422
        assert "date must be ISO" in resp.json()["detail"]

    def test_api_fetch_failure_returns_zero_fixtures_not_500(self, client):
        """If _gather_rows raises (API down, no key, etc.) → graceful response."""
        with patch(
            "nutmeg.v4.cli.ingest_odds._gather_rows",
            side_effect=RuntimeError("API-Football: 401 Unauthorized"),
        ):
            resp = client.post(
                "/api/v4/today-recommendations",
                json={"leagues": ["EPL"], "bankroll": 1000.0, "date": "2026-05-25"},
            )

        if resp.status_code == 503:
            pytest.skip("Production artifact not available")

        assert resp.status_code == 200
        body = resp.json()
        assert body["fixtures_fetched"] == 0
        assert body["single"] is None
        assert body["parlay"] is None


class TestTodayRecommendationsDefaults:
    """The defaults should match V10 wireframe expectations."""

    def test_default_leagues_is_top2_european(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        req = TodayRecommendationsRequest()
        assert "EPL" in req.leagues
        assert "ESP_LA_LIGA" in req.leagues

    def test_default_bankroll_is_1000(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        req = TodayRecommendationsRequest()
        assert req.bankroll == 1000.0


class TestTodayRecommendationsPlayoffWarnings:
    """V12 W0 (2026-05-27) — endpoint surfaces fixtures in playoff windows."""

    def test_playoff_window_fixture_produces_warning(self, client):
        """法甲 fixture on 2026-05-26 (Ligue 1 barrage window) → warning."""
        fake_rows = [
            _make_fixture_row("Saint Etienne", "Nice",
                              league="FRA_LIGUE_1", dt="2026-05-26"),
        ]
        with patch(
            "nutmeg.v4.cli.ingest_odds._gather_rows",
            return_value=(fake_rows, 1, 0),
        ):
            resp = client.post(
                "/api/v4/today-recommendations",
                json={"leagues": ["FRA_LIGUE_1"], "bankroll": 1000.0,
                      "date": "2026-05-26"},
            )

        if resp.status_code == 503:
            pytest.skip("Production artifact not available")

        assert resp.status_code == 200
        body = resp.json()
        warnings = body.get("playoff_warnings", [])
        assert len(warnings) == 1
        w = warnings[0]
        assert w["league"] == "FRA_LIGUE_1"
        assert w["home_team"] == "Saint Etienne"
        assert w["away_team"] == "Nice"
        assert w["date"] == "2026-05-26"
        assert "barrage" in w["context"].lower()
        assert w["model_bias_note"].strip()

    def test_non_playoff_window_produces_no_warning(self, client):
        """EPL fixture (no playoff window configured for EPL) → empty list."""
        fake_rows = [
            _make_fixture_row("Arsenal", "Liverpool",
                              league="EPL", dt="2026-05-26"),
        ]
        with patch(
            "nutmeg.v4.cli.ingest_odds._gather_rows",
            return_value=(fake_rows, 1, 0),
        ):
            resp = client.post(
                "/api/v4/today-recommendations",
                json={"leagues": ["EPL"], "bankroll": 1000.0,
                      "date": "2026-05-26"},
            )

        if resp.status_code == 503:
            pytest.skip("Production artifact not available")

        assert resp.status_code == 200
        body = resp.json()
        assert body.get("playoff_warnings", []) == []

    def test_empty_fixtures_returns_empty_warnings(self, client):
        """0 fixtures → playoff_warnings is [] (not missing, not null)."""
        with patch(
            "nutmeg.v4.cli.ingest_odds._gather_rows",
            return_value=([], 0, 0),
        ):
            resp = client.post(
                "/api/v4/today-recommendations",
                json={"leagues": ["EPL"], "bankroll": 1000.0,
                      "date": "2026-05-26"},
            )

        if resp.status_code == 503:
            pytest.skip("Production artifact not available")

        assert resp.status_code == 200
        body = resp.json()
        assert body["playoff_warnings"] == []

    def test_default_include_is_all_four(self):
        """V11 P1-FE#4: pool added; V11 post-ship: 'wc' added.
        Default now covers single + parlay + pool + WC (informational)."""
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        req = TodayRecommendationsRequest()
        assert set(req.include) == {"single", "parlay", "pool", "wc"}

    def test_default_risk_preference_is_balanced(self):
        """V11 P1-FE#4 — risk dial defaults to 中 (Kelly 0.25)."""
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        req = TodayRecommendationsRequest()
        assert req.risk_preference == "balanced"

    def test_default_min_ev_matches_jingcai(self):
        """V11 P1-FE#4 — min_ev default = +5% matches JINGCAI_DEFAULT."""
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        req = TodayRecommendationsRequest()
        assert req.min_ev == 0.05

    def test_default_pool_n_is_3(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        req = TodayRecommendationsRequest()
        assert req.pool_n == 3

    def test_default_record_session_is_false(self):
        """Carry-over from P1#7 / V9 W3: opt-in, never auto-record."""
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        req = TodayRecommendationsRequest()
        assert req.record_session is False
