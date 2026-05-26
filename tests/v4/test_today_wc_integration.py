"""V11 post-ship — today-recommendations WC block.

Verifies:
  - `include` list accepts "wc" without rejection
  - When "wc" excluded → response.wc is None
  - When "wc" included + predictions_wc returns predictions → response.wc populated
  - When "wc" included + predictions_wc 503s (no training data) → response.wc is None
    (graceful degradation; the rest of the response still works)
  - WC predictions do NOT count toward total_recs / total_stake / weighted_ev
    (they're informational only — no handicap means no EV yet)

The today endpoint internally calls `predictions_wc(...)`. We monkeypatch
that function to control return values without depending on local data.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient


# ============ Helpers ===================================================

def _fake_wc_response(n_fixtures: int = 2, *, has_pinnacle: bool = True):
    """A minimal WcPredictionsResponse-shaped object for monkeypatching.

    Returns a real WcPredictionsResponse so pydantic serialization works
    inside the today endpoint's response_model validation.
    """
    from nutmeg.v4.api.schemas import WcMatchPrediction, WcPredictionsResponse

    preds = [
        WcMatchPrediction(
            fixture_id=8000 + i,
            kickoff_utc=f"2026-06-1{i+1}T19:00:00+00:00",
            round="Group Stage - 1",
            home_team=("USA" if i == 0 else "Argentina"),
            away_team=("Mexico" if i == 0 else "Brazil"),
            home_elo=1700.0 + 50 * i,
            away_elo=1680.0 + 50 * i,
            elo_diff=20.0,
            home_adv=50.0 if i == 0 else 0.0,
            has_pinnacle=has_pinnacle,
            psc_home=1.85 if has_pinnacle else None,
            psc_draw=3.50 if has_pinnacle else None,
            psc_away=4.20 if has_pinnacle else None,
            p_home=0.55,
            p_draw=0.25,
            p_away=0.20,
            p_home_elo_only=0.50,
            p_draw_elo_only=0.27,
            p_away_elo_only=0.23,
            source="blend(α=0.4)" if has_pinnacle else "lightgbm_only",
        )
        for i in range(n_fixtures)
    ]
    return WcPredictionsResponse(
        date="2026-06-11",
        season=2026,
        n_fixtures=len(preds),
        blend_alpha=0.4,
        elo_snapshot="eloratings_2026-05-26.parquet",
        host_country_hint={"USA": 50.0, "Mexico": 50.0, "Canada": 50.0},
        predictions=preds,
        generated_at_utc=dt.datetime.now(dt.UTC).isoformat(),
    )


def _build_client_with_no_fixtures(monkeypatch, *, wc_resp=None, wc_raises=None):
    """Build a TestClient where the league pipeline returns 0 fixtures
    (so single/parlay/pool are no-ops) and predictions_wc is replaced
    with a deterministic mock.
    """
    # Force no league fixtures → only WC arm runs
    def _no_rows(*args, **kwargs):
        return ([], 0, 0)
    monkeypatch.setattr(
        "nutmeg.v4.cli.ingest_odds._gather_rows",
        _no_rows,
    )

    # Monkeypatch the predictions_wc function on the routes module
    if wc_raises is not None:
        def _raise(*args, **kwargs):
            raise wc_raises
        monkeypatch.setattr(
            "nutmeg.v4.api.routes.predictions_wc",
            _raise,
        )
    elif wc_resp is not None:
        def _ret(*args, **kwargs):
            return wc_resp
        monkeypatch.setattr(
            "nutmeg.v4.api.routes.predictions_wc",
            _ret,
        )
    else:
        # Default: return an empty WC response (n_fixtures=0)
        empty = _fake_wc_response(n_fixtures=0)
        def _empty(*args, **kwargs):
            return empty
        monkeypatch.setattr(
            "nutmeg.v4.api.routes.predictions_wc",
            _empty,
        )

    from nutmeg.v4.api import v4_router
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


# ============ include="wc" + populated response =========================

class TestWcIncluded:

    def test_wc_block_populated_when_predictions_exist(self, monkeypatch):
        wc = _fake_wc_response(n_fixtures=2)
        client = _build_client_with_no_fixtures(monkeypatch, wc_resp=wc)
        r = client.post("/api/v4/today-recommendations", json={
            "date": "2026-06-11",
            "leagues": ["EPL"],
            "include": ["wc"],
            "bankroll": 1000.0,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["wc"] is not None
        assert body["wc"]["n_fixtures"] == 2
        assert len(body["wc"]["predictions"]) == 2
        # WC doesn't contribute to total_recs (no EV yet)
        assert body["summary"]["total_recs"] == 0
        assert body["summary"]["total_stake"] == 0.0
        # The first prediction should round-trip
        p = body["wc"]["predictions"][0]
        assert p["home_team"] == "USA"
        assert p["has_pinnacle"] is True

    def test_default_include_contains_wc(self):
        """V11 post-ship: 'wc' is in the default include list."""
        from nutmeg.v4.api.schemas import TodayRecommendationsRequest
        defaults = TodayRecommendationsRequest()
        assert "wc" in defaults.include

    def test_wc_excluded_when_not_in_include(self, monkeypatch):
        """Explicit `include` without 'wc' → wc field is None."""
        client = _build_client_with_no_fixtures(monkeypatch)
        r = client.post("/api/v4/today-recommendations", json={
            "date": "2026-06-11",
            "leagues": ["EPL"],
            "include": ["single"],  # exclude wc
            "bankroll": 1000.0,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["wc"] is None


# ============ Graceful degradation ======================================

class TestWcGracefulDegradation:

    def test_503_from_predictions_wc_returns_none_not_500(self, monkeypatch):
        """When WC training data is missing, the today endpoint should
        return wc=None without 500-ing the whole response."""
        exc = HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WC training data missing",
        )
        client = _build_client_with_no_fixtures(monkeypatch, wc_raises=exc)
        r = client.post("/api/v4/today-recommendations", json={
            "date": "2026-06-11",
            "leagues": ["EPL"],
            "include": ["wc"],
            "bankroll": 1000.0,
        })
        assert r.status_code == 200  # not 503/500 — today endpoint resilient
        body = r.json()
        assert body["wc"] is None

    def test_unexpected_exception_returns_none(self, monkeypatch):
        """Same for any non-HTTPException raised by the WC arm."""
        client = _build_client_with_no_fixtures(
            monkeypatch, wc_raises=RuntimeError("kaboom"),
        )
        r = client.post("/api/v4/today-recommendations", json={
            "date": "2026-06-11",
            "leagues": ["EPL"],
            "include": ["wc"],
            "bankroll": 1000.0,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["wc"] is None

    def test_zero_fixtures_returns_none(self, monkeypatch):
        """Empty WC predictions → response.wc is None (frontend hides section)."""
        client = _build_client_with_no_fixtures(monkeypatch)  # default empty
        r = client.post("/api/v4/today-recommendations", json={
            "date": "2026-06-11",
            "leagues": ["EPL"],
            "include": ["wc"],
            "bankroll": 1000.0,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["wc"] is None
