"""V12 W0 (post-V11 audit) — tests for GET /v4/predictions/wc-upcoming.

This endpoint (commit 5779e95) was the newest and most complex code with
ZERO test coverage when the 2026-05-29 audit flagged it. It:
  1. validates `days` ∈ [1,14] and `top_n` ∈ [1,20] (422 otherwise)
  2. trains a NationalTeamModel, fetches WC fixtures, filters to a window
  3. predicts 1X2 per fixture, applies a +EV gate, Kelly-sizes, sorts by hit
     probability, returns top_n.

The validation branch runs BEFORE any import / disk / network, so those
tests are fully hermetic. The happy / empty / EV-gate paths stub every
expensive dependency (mirrors test_wc_single_rec_endpoint.py) so the test
runs in milliseconds and needs no local parquets or API tokens.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _bare_client() -> TestClient:
    """A client with the real router and NO mocks — enough for the
    validation (422) tests, which short-circuit before any heavy work."""
    from nutmeg.v4.api import v4_router

    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


class _StubModel:
    """Stand-in for NationalTeamModel; never actually invoked by the
    stubbed _predict_one_fixture, but _train_combined_model must return
    *something*."""


def _build_client_with_mocks(monkeypatch, *, fixtures, predict_result):
    """TestClient where the whole WC pipeline is stubbed.

    ``fixtures``        : list of API-Football fixture dicts returned by
                          fetch_fixtures_for_league_season.
    ``predict_result``  : dict returned by _predict_one_fixture for every
                          fixture (or None to skip / has_pinnacle False).
    """
    from nutmeg.v4.api import v4_router

    monkeypatch.setattr(
        "nutmeg.v4.cli.wc_predict._train_combined_model",
        lambda *a, **k: _StubModel(),
    )
    monkeypatch.setattr(
        "nutmeg.v4.data.wc_training_frame.load_elo_snapshot",
        lambda _p: {"USA": {"elo": 1750.0}, "MEX": {"elo": 1700.0}},
    )
    monkeypatch.setattr(
        "nutmeg.v4.data.sources.api_football.fetch_fixtures_for_league_season",
        lambda *a, **k: fixtures,
    )
    monkeypatch.setattr(
        "nutmeg.v4.cli.wc_predict._predict_one_fixture",
        lambda *a, **k: predict_result,
    )

    # Make the eloratings snapshot glob look populated (file never read —
    # load_elo_snapshot is stubbed).
    fake_snapshot = Path("/tmp/__fake_elo_snapshot.parquet")
    real_glob = Path.glob

    def fake_glob(self, pattern):
        if "eloratings" in str(self) and pattern.startswith("eloratings_"):
            return iter([fake_snapshot])
        return real_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", fake_glob)

    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


def _fixture(home: str, away: str, *, days_from_today: int = 0, fid: int = 9001) -> dict:
    d = dt.date.today() + dt.timedelta(days=days_from_today)
    return {
        "fixture": {"id": fid, "date": f"{d.isoformat()}T19:00:00+00:00"},
        "teams": {"home": {"name": home}, "away": {"name": away}},
    }


def _predict(*, p_home, p_draw, p_away, sp_home, sp_draw, sp_away,
             has_pinnacle=True, fid=9001):
    return {
        "has_pinnacle": has_pinnacle,
        "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
        "psc_home": sp_home, "psc_draw": sp_draw, "psc_away": sp_away,
        "fixture_id": fid,
        "kickoff_utc": f"{dt.date.today().isoformat()}T19:00:00+00:00",
        "source": "elo+market",
    }


# ============ Validation (hermetic — no mocks needed) =================

class TestWcUpcomingValidation:

    @pytest.mark.parametrize("days", [0, 15, 100, -1])
    def test_days_out_of_range_422(self, days):
        client = _bare_client()
        r = client.get(f"/api/v4/predictions/wc-upcoming?days={days}&fetch_current_odds=false")
        assert r.status_code == 422, r.text
        assert "days" in r.text

    @pytest.mark.parametrize("top_n", [0, 21, 50, -3])
    def test_top_n_out_of_range_422(self, top_n):
        client = _bare_client()
        r = client.get(
            f"/api/v4/predictions/wc-upcoming?days=5&top_n={top_n}&fetch_current_odds=false"
        )
        assert r.status_code == 422, r.text
        assert "top_n" in r.text


# ============ Happy / empty / EV-gate paths (fully mocked) =============

class TestWcUpcomingPaths:

    def test_empty_fixtures_returns_empty_picks(self, monkeypatch):
        client = _build_client_with_mocks(monkeypatch, fixtures=[], predict_result=None)
        r = client.get("/api/v4/predictions/wc-upcoming?days=5&fetch_current_odds=false")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["n_fixtures_scanned"] == 0
        assert body["n_picks_after_ev_gate"] == 0
        assert body["picks"] == []
        assert body["days"] == 5
        assert body["blend_alpha"] == 0.4

    def test_positive_ev_pick_fires_and_is_kelly_sized(self, monkeypatch):
        # p_home 0.70 @ SP 1.60 → EV = 0.12 (clears +5% gate)
        fx = _fixture("USA", "Mexico", days_from_today=1)
        pred = _predict(p_home=0.70, p_draw=0.18, p_away=0.12,
                        sp_home=1.60, sp_draw=4.0, sp_away=6.0)
        client = _build_client_with_mocks(monkeypatch, fixtures=[fx], predict_result=pred)
        r = client.get(
            "/api/v4/predictions/wc-upcoming?days=5&top_n=5"
            "&fetch_current_odds=false&bankroll=1000&kelly_fraction=0.25"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["n_fixtures_scanned"] == 1
        assert body["n_picks_after_ev_gate"] >= 1
        pick = body["picks"][0]
        assert pick["outcome"] == "H"
        assert pick["home_team"] == "USA"
        assert abs(pick["hit_probability"] - 0.70) < 1e-6
        assert abs(pick["ev_per_unit"] - (0.70 * 1.60 - 1.0)) < 1e-6
        # Kelly stake = 1000 * 0.25 * (ev / (sp-1)) = 250 * 0.12/0.6 = 50
        assert abs(pick["stake"] - 50.0) < 0.5

    def test_ev_gate_filters_out_negative_ev(self, monkeypatch):
        # All outcomes priced at/under fair → none clears +5%.
        fx = _fixture("USA", "Mexico", days_from_today=1)
        pred = _predict(p_home=0.40, p_draw=0.30, p_away=0.30,
                        sp_home=1.50, sp_draw=3.0, sp_away=3.0)  # EVs all < 0.05
        client = _build_client_with_mocks(monkeypatch, fixtures=[fx], predict_result=pred)
        r = client.get(
            "/api/v4/predictions/wc-upcoming?days=5&min_ev=0.05&fetch_current_odds=false"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["n_fixtures_scanned"] == 1
        assert body["n_picks_after_ev_gate"] == 0

    def test_fixtures_outside_window_are_not_scanned(self, monkeypatch):
        # Fixture 30 days out, window is 5 → filtered before scan.
        fx = _fixture("USA", "Mexico", days_from_today=30)
        pred = _predict(p_home=0.90, p_draw=0.05, p_away=0.05,
                        sp_home=2.0, sp_draw=4.0, sp_away=6.0)
        client = _build_client_with_mocks(monkeypatch, fixtures=[fx], predict_result=pred)
        r = client.get("/api/v4/predictions/wc-upcoming?days=5&fetch_current_odds=false")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["n_fixtures_scanned"] == 0
        assert body["picks"] == []

    def test_no_pinnacle_means_skipped(self, monkeypatch):
        # has_pinnacle False → fixture scanned but no SP → no pick.
        fx = _fixture("USA", "Mexico", days_from_today=1)
        pred = _predict(p_home=0.90, p_draw=0.05, p_away=0.05,
                        sp_home=2.0, sp_draw=4.0, sp_away=6.0, has_pinnacle=False)
        client = _build_client_with_mocks(monkeypatch, fixtures=[fx], predict_result=pred)
        r = client.get("/api/v4/predictions/wc-upcoming?days=5&fetch_current_odds=false")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["n_fixtures_scanned"] == 1
        assert body["n_picks_after_ev_gate"] == 0
