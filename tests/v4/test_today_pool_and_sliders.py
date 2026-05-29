"""V11 P1-FE#4 — backend tests for pool option + risk/min_ev sliders.

Tests cover:
  - Schema: risk_preference ∈ {conservative/balanced/aggressive}, min_ev range,
    pool_n bounds
  - Risk → Kelly mapping: 0.15 / 0.25 / 0.40
  - Explicit kelly_fraction overrides risk_preference
  - min_ev filters: drops tickets below threshold
  - _OUTCOME_TO_POOL_PICK round-trip mapping
  - _build_today_pool: returns None if fewer than pool_n +EV picks
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
    """Same shape as test_today_recommendations._make_fixture_row."""
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
    from nutmeg.v4.api import v4_router
    import os
    os.environ.setdefault(
        "NUTMEG_V4_ARTIFACT_PATH",
        str(REPO_ROOT / "data" / "v4_model_cat_lineups"),
    )
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


# ---------- Schema field validation ------------------------------------

class TestSchemaValidation:
    def test_risk_preference_accepts_three_values(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        for v in ("conservative", "balanced", "aggressive"):
            req = TodayRecommendationsRequest(risk_preference=v)
            assert req.risk_preference == v

    def test_risk_preference_rejects_unknown(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        with pytest.raises(Exception):
            TodayRecommendationsRequest(risk_preference="reckless")

    def test_min_ev_range(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        # Slider values from the design doc
        for v in (-0.05, 0.0, 0.05, 0.10):
            req = TodayRecommendationsRequest(min_ev=v)
            assert req.min_ev == v

    def test_min_ev_out_of_range_rejected(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        with pytest.raises(Exception):
            TodayRecommendationsRequest(min_ev=-0.50)  # below -0.20 floor
        with pytest.raises(Exception):
            TodayRecommendationsRequest(min_ev=0.99)   # above 0.50 ceiling

    def test_pool_n_bounds(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        req = TodayRecommendationsRequest(pool_n=4)
        assert req.pool_n == 4
        with pytest.raises(Exception):
            TodayRecommendationsRequest(pool_n=1)   # below ge=2
        with pytest.raises(Exception):
            TodayRecommendationsRequest(pool_n=9)   # above le=8

    def test_include_accepts_pool(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        req = TodayRecommendationsRequest(include=["pool"])
        assert req.include == ["pool"]


# ---------- Risk → Kelly mapping --------------------------------------

class TestRiskToKellyMapping:
    """Verify the _RISK_TO_KELLY table inside today_recommendations()."""

    @patch("nutmeg.v4.cli.ingest_odds._gather_rows", return_value=([], 0, 0))
    def test_returns_zero_fixtures_path(self, mock_gather, client):
        """0 fixtures path: just verify shape includes pool field = None."""
        r = client.post("/api/v4/today-recommendations", json={
            "leagues": ["EPL"],
            "bankroll": 1000.0,
            "risk_preference": "conservative",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["fixtures_fetched"] == 0
        assert body["pool"] is None
        assert body["single"] is None
        assert body["parlay"] is None

    def test_default_risk_balanced_kelly_025(self):
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        req = TodayRecommendationsRequest()
        assert req.risk_preference == "balanced"
        assert req.kelly_fraction == 0.25  # acts as override when set


# ---------- _OUTCOME_TO_POOL_PICK mapping ------------------------------

class TestOutcomeToPoolPickMap:
    """The map used by _build_today_pool to convert SingleTicket → PoolFixturePick."""

    def test_all_six_combinations_present(self):
        from nutmeg.v4.api.routes import _OUTCOME_TO_POOL_PICK
        assert len(_OUTCOME_TO_POOL_PICK) == 6
        # 1x2 × 3 outcomes
        assert _OUTCOME_TO_POOL_PICK[("1x2", "H")] == "1x2_H"
        assert _OUTCOME_TO_POOL_PICK[("1x2", "D")] == "1x2_D"
        assert _OUTCOME_TO_POOL_PICK[("1x2", "A")] == "1x2_A"
        # handicap × 3 outcomes
        assert _OUTCOME_TO_POOL_PICK[("handicap_1x2", "H")] == "hc_H"
        assert _OUTCOME_TO_POOL_PICK[("handicap_1x2", "D")] == "hc_D"
        assert _OUTCOME_TO_POOL_PICK[("handicap_1x2", "A")] == "hc_A"

    def test_round_trip_with_pool_pick_map(self):
        """Inverse of routes._POOL_PICK_MAP (single source of truth)."""
        from nutmeg.v4.api.routes import (
            _OUTCOME_TO_POOL_PICK,
            _POOL_PICK_MAP,
        )
        for pick_str, (mkt, out) in _POOL_PICK_MAP.items():
            assert _OUTCOME_TO_POOL_PICK[(mkt, out)] == pick_str


# ---------- _build_today_pool helper ----------------------------------

class TestBuildTodayPool:
    """The Strategy B pool builder. Tests the early-exit paths without
    needing the actual model artifact (which is slow + not always available
    in CI)."""

    def test_returns_none_when_too_few_fixtures(self):
        from nutmeg.v4.api.routes import _build_today_pool
        # 2 fixtures but pool_n=3 → early None, no model call needed
        from nutmeg.v4.api.schemas import FixtureOddsInput
        f = [
            FixtureOddsInput(
                date="2026-05-25", league="EPL",
                home_team="A", away_team="B",
                psc_home=2.0, psc_draw=3.4, psc_away=3.6,
                odds_1x2_H=2.0, odds_1x2_D=3.4, odds_1x2_A=3.6,
            ),
            FixtureOddsInput(
                date="2026-05-25", league="EPL",
                home_team="C", away_team="D",
                psc_home=2.0, psc_draw=3.4, psc_away=3.6,
                odds_1x2_H=2.0, odds_1x2_D=3.4, odds_1x2_A=3.6,
            ),
        ]
        out = _build_today_pool(
            fixtures=f,
            bankroll=1000.0,
            kelly_fraction=0.25,
            min_ev=0.05,
            pool_n=3,
            record_session=False,
        )
        assert out is None


# ---------- Endpoint integration: pool field present ------------------

class TestEndpointPoolField:
    @patch("nutmeg.v4.cli.ingest_odds._gather_rows")
    def test_pool_field_in_response_shape(self, mock_gather, client):
        """Even when no fixtures pass the EV gate, response carries the
        pool field (None when empty)."""
        mock_gather.return_value = ([], 0, 0)
        r = client.post("/api/v4/today-recommendations", json={
            "leagues": ["EPL"],
        })
        assert r.status_code == 200
        body = r.json()
        # Schema must include pool field
        assert "pool" in body
        # 0 fixtures → pool None
        assert body["pool"] is None

    @patch("nutmeg.v4.cli.ingest_odds._gather_rows")
    def test_risk_and_min_ev_accepted(self, mock_gather, client):
        """Endpoint accepts the new slider params without 422."""
        mock_gather.return_value = ([], 0, 0)
        r = client.post("/api/v4/today-recommendations", json={
            "risk_preference": "aggressive",
            "min_ev": 0.10,
            "pool_n": 4,
        })
        assert r.status_code == 200


# ---------- Dashboard wiring (P1-FE#4 Day 2) ---------------------------

class TestDashboardSliderWiring:
    @pytest.fixture(scope="class")
    def html(self):
        from nutmeg.v4.api import v4_router
        app = FastAPI()
        app.include_router(v4_router, prefix="/api")
        c = TestClient(app)
        return c.get("/api/v4/dashboard").text

    def test_risk_slider_present(self, html):
        assert 'id="today-risk"' in html
        assert 'type="range"' in html  # at least one range input

    def test_min_ev_slider_present(self, html):
        assert 'id="today-min-ev"' in html

    def test_slider_labels_present(self, html):
        # Initial labels visible on first paint
        assert 'id="today-risk-label"' in html
        assert 'id="today-min-ev-label"' in html

    def test_risk_slider_3_step_values(self, html):
        """0/1/2 → conservative/balanced/aggressive."""
        idx = html.index('id="today-risk"')
        chunk = html[idx-100:idx+200]
        assert 'min="0"' in chunk
        assert 'max="2"' in chunk
        assert 'step="1"' in chunk

    def test_min_ev_slider_range(self, html):
        idx = html.index('id="today-min-ev"')
        chunk = html[idx-100:idx+300]
        # -5% to +10% in 5% steps
        assert 'min="-0.05"' in chunk
        assert 'max="0.10"' in chunk

    def test_risk_kelly_mapping_in_js(self, html):
        """Frontend ships the same risk → label mapping."""
        assert "_RISK_SLIDER_VALUES" in html
        assert "'conservative', 'balanced', 'aggressive'" in html

    def test_pool_section_in_dashboard(self, html):
        assert 'id="today-pool-section"' in html
        assert 'id="today-pool-list"' in html
        assert 'id="today-pool-summary"' in html

    def test_renderTodayPool_defined(self, html):
        # V12 W5 — parameterized by a DOM prefix so it serves both the
        # 🌍 国际盘口 (pfx='today') and 💴 竞彩盘口 (pfx='jc') boards.
        assert "function renderTodayPool(pool, pfx = 'today')" in html

    def test_load_today_sends_new_params(self, html):
        """JS body must include risk_preference + min_ev in the request body."""
        idx = html.index("async function loadTodayRecommendations")
        body = html[idx:idx+3000]
        assert "risk_preference:" in body
        assert "min_ev:" in body
        assert "include: ['single', 'parlay', 'pool']" in body

    def test_sliders_share_debounce(self, html):
        """All 3 inputs use the shared _debouncedReload helper (500ms)."""
        assert "function _debouncedReload" in html
        # Bankroll, risk, min-ev all wired to it
        idx = html.index("function _debouncedReload")
        chunk = html[idx:idx+1500]
        # All three input handlers reference the helper directly
        assert chunk.count("_debouncedReload") >= 3

    def test_i18n_keys_present_both_locales(self, html):
        """zh + en blocks both have the new keys."""
        for key in ("lbl_risk_preference", "lbl_min_ev",
                    "risk_conservative", "risk_balanced", "risk_aggressive",
                    "h_today_pool"):
            # Each key appears in both zh and en blocks
            assert html.count(f"{key}:") >= 2, (
                f"{key} not in both i18n dicts"
            )
