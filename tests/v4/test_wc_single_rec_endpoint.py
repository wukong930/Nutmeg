"""V11 post-ship — tests for POST /v4/recommend/wc/single.

The endpoint runs:
  1. NationalTeamModel.predict_proba(1X2)
  2. Bayesian blend with user-provided Pinnacle 1X2
  3. Path A++ handicap evaluation (DC reverse-map + market blend)
  4. EV gate + fractional Kelly → ¥2-quantized stake

Tests use lightweight mocks for the expensive pieces:
  - The model is replaced with a stub returning deterministic probs
  - load_elo_snapshot returns a tiny dict
  - The eloratings Path.glob is patched to look populated

This way the endpoint test runs in milliseconds and doesn't depend on
local cup_history parquets being present.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ============ Fixtures / mock helpers ===================================

class _StubNationalTeamModel:
    """A drop-in for NationalTeamModel that returns hard-coded 1X2.

    The output is (n_rows, 3) — one row per fixture passed in. Allows tests
    to predict expected handicap behavior."""

    def __init__(self, p_h: float = 0.55, p_d: float = 0.25, p_a: float = 0.20):
        self._p = np.array([p_h, p_d, p_a], dtype=float)
        self._p /= self._p.sum()

    def predict_proba(self, df, host_country=None, host_advantage=0.0):
        n = len(df)
        return np.tile(self._p, (n, 1))


_FAKE_ELO = {
    "USA": {"elo": 1750.0, "rank": 25},
    "MEX": {"elo": 1700.0, "rank": 35},
    "ARG": {"elo": 2050.0, "rank": 1},
    "BRA": {"elo": 2030.0, "rank": 2},
}


def _build_client_with_mocks(monkeypatch, p_h=0.55, p_d=0.25, p_a=0.20):
    """Build a TestClient where the WC training pipeline is fully stubbed."""
    fake_snapshot = Path("/tmp/__fake_elo_snapshot.parquet")  # must look "exists"

    # Patch the path glob on the routes module's _Path import:
    from nutmeg.v4.api import v4_router

    # Apply mocks to the exact import paths used inside the endpoint
    monkeypatch.setattr(
        "nutmeg.v4.cli.wc_predict._train_combined_model",
        lambda *args, **kwargs: _StubNationalTeamModel(p_h, p_d, p_a),
    )
    monkeypatch.setattr(
        "nutmeg.v4.data.wc_training_frame.load_elo_snapshot",
        lambda _path: _FAKE_ELO,
    )

    # Patch Path.glob to return our fake snapshot when called on eloratings
    real_glob = Path.glob

    def fake_glob(self, pattern):
        if "eloratings" in str(self) and pattern.startswith("eloratings_"):
            return iter([fake_snapshot])
        return real_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", fake_glob)

    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


# ============ Happy-path response shape =================================

class TestRecommendWcSingleHappyPath:

    def test_returns_200_with_expected_shape(self, monkeypatch):
        """Single fixture in, full response shape out."""
        client = _build_client_with_mocks(monkeypatch)
        payload = {
            "fixtures": [{
                "fixture_id": 9001,
                "home_team": "USA",
                "away_team": "Mexico",
                "kickoff_utc": "2026-06-15T19:00:00+00:00",
                "psc_home": 1.85,
                "psc_draw": 3.50,
                "psc_away": 4.20,
                "handicap_home": -1,
                "odds_handicap_H": 2.40,
                "odds_handicap_D": 3.50,
                "odds_handicap_A": 2.80,
            }],
            "bankroll": 1000.0,
            "kelly_fraction": 0.25,
            "min_ev": 0.05,
            "blend_alpha": 0.4,
        }
        r = client.post("/api/v4/recommend/wc/single", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()

        # Top-level structure
        assert body["n_fixtures"] == 1
        assert body["bankroll"] == 1000.0
        assert body["blend_alpha"] == 0.4
        assert body["lambda_total_prior"] == 2.6  # WC mean
        assert "generated_at_utc" in body
        assert len(body["matches"]) == 1

        # Match-level structure
        match = body["matches"][0]
        assert match["fixture_id"] == 9001
        assert match["home_team"] == "USA"
        assert match["handicap_home"] == -1
        assert len(match["p_1x2_blended"]) == 3
        assert abs(sum(match["p_1x2_blended"]) - 1.0) < 1e-3
        assert match["inferred_lambda_home"] > 0
        assert match["inferred_lambda_away"] > 0

        # Outcomes: 3 (H/D/A), each with stake/EV
        assert len(match["outcomes"]) == 3
        labels = {o["outcome"] for o in match["outcomes"]}
        assert labels == {"H", "D", "A"}
        for o in match["outcomes"]:
            assert "p_final" in o
            assert "p_model" in o
            assert "p_market" in o  # may be None if no SP
            assert "ev_per_unit" in o
            assert "kelly_fraction" in o
            assert "stake" in o
            assert o["stake"] >= 0.0


# ============ EV gate + Kelly sizing ====================================

class TestEvGateAndKelly:

    def test_ev_gate_drops_low_edge_outcomes(self, monkeypatch):
        """When all outcomes are sub-min_ev, n_recommendations == 0."""
        # Make the model VERY uncertain → no outcome has +5% EV vs SP
        client = _build_client_with_mocks(monkeypatch, p_h=0.34, p_d=0.33, p_a=0.33)
        payload = {
            "fixtures": [{
                "fixture_id": 1,
                "home_team": "USA",
                "away_team": "Mexico",
                "kickoff_utc": "2026-06-15T19:00:00+00:00",
                "psc_home": 2.90,
                "psc_draw": 3.05,
                "psc_away": 2.90,
                "handicap_home": 0,
                "odds_handicap_H": 2.90,
                "odds_handicap_D": 3.05,
                "odds_handicap_A": 2.90,
            }],
            "bankroll": 1000.0,
            "min_ev": 0.05,
            "blend_alpha": 0.4,
        }
        r = client.post("/api/v4/recommend/wc/single", json=payload)
        assert r.status_code == 200
        body = r.json()
        # All 3 outcomes surface — but with stake=0 since EV ≈ 0 (Pinnacle vig)
        assert body["n_recommendations"] == 0
        assert body["total_stake"] == 0.0
        for o in body["matches"][0]["outcomes"]:
            assert o["stake"] == 0.0
            # EV should be roughly 0 (sub-min_ev when market ≈ model)
            assert o["ev_per_unit"] < 0.05

    def test_strong_edge_produces_stake(self, monkeypatch):
        """Strong model signal + bad market price → recommendation."""
        # Model very confident in home win, market gives big odds → big edge
        client = _build_client_with_mocks(monkeypatch, p_h=0.80, p_d=0.15, p_a=0.05)
        payload = {
            "fixtures": [{
                "fixture_id": 2,
                "home_team": "USA",
                "away_team": "Mexico",
                "kickoff_utc": "2026-06-15T19:00:00+00:00",
                # Pinnacle 1X2 ALSO favors home — keeps blended p_h high
                "psc_home": 1.40,
                "psc_draw": 4.50,
                "psc_away": 8.00,
                # But 让球 -1 odds on H are juicy
                "handicap_home": -1,
                "odds_handicap_H": 3.20,   # mispriced
                "odds_handicap_D": 3.50,
                "odds_handicap_A": 2.10,
            }],
            "bankroll": 10000.0,
            "kelly_fraction": 0.25,
            "max_stake_fraction": 0.05,
            "min_ev": 0.05,
            "blend_alpha": 0.4,
        }
        r = client.post("/api/v4/recommend/wc/single", json=payload)
        assert r.status_code == 200
        body = r.json()
        # Should produce ≥1 recommendation with positive stake
        assert body["n_recommendations"] >= 1
        assert body["total_stake"] > 0.0
        # All stakes are ¥2-multiples
        for m in body["matches"]:
            for o in m["outcomes"]:
                if o["stake"] > 0:
                    assert (o["stake"] % 2.0) == 0.0


# ============ Multi-fixture aggregation =================================

class TestMultiFixture:

    def test_two_fixtures_aggregated(self, monkeypatch):
        client = _build_client_with_mocks(monkeypatch, p_h=0.50, p_d=0.30, p_a=0.20)
        payload = {
            "fixtures": [
                {
                    "fixture_id": 100,
                    "home_team": "USA",
                    "away_team": "Mexico",
                    "kickoff_utc": "2026-06-15T19:00:00+00:00",
                    "psc_home": 1.85, "psc_draw": 3.50, "psc_away": 4.20,
                    "handicap_home": -1,
                    "odds_handicap_H": 2.40, "odds_handicap_D": 3.50,
                    "odds_handicap_A": 2.80,
                },
                {
                    "fixture_id": 101,
                    "home_team": "Argentina",
                    "away_team": "Brazil",
                    "kickoff_utc": "2026-06-15T22:00:00+00:00",
                    "psc_home": 2.50, "psc_draw": 3.10, "psc_away": 2.80,
                    "handicap_home": 0,
                    "odds_handicap_H": 2.50, "odds_handicap_D": 3.10,
                    "odds_handicap_A": 2.80,
                },
            ],
            "bankroll": 5000.0,
            "min_ev": 0.05,
            "blend_alpha": 0.4,
        }
        r = client.post("/api/v4/recommend/wc/single", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["n_fixtures"] == 2
        assert len(body["matches"]) == 2
        # Each match has its own 3 outcomes
        for m in body["matches"]:
            assert len(m["outcomes"]) == 3


# ============ Validation errors =========================================

class TestValidation:

    def test_missing_fixtures_field_rejected(self, monkeypatch):
        client = _build_client_with_mocks(monkeypatch)
        r = client.post("/api/v4/recommend/wc/single", json={})
        assert r.status_code == 422

    def test_empty_fixtures_rejected(self, monkeypatch):
        client = _build_client_with_mocks(monkeypatch)
        r = client.post(
            "/api/v4/recommend/wc/single",
            json={"fixtures": [], "bankroll": 1000.0},
        )
        assert r.status_code == 422  # min_length=1

    def test_handicap_out_of_bounds(self, monkeypatch):
        client = _build_client_with_mocks(monkeypatch)
        r = client.post("/api/v4/recommend/wc/single", json={
            "fixtures": [{
                "fixture_id": 1,
                "home_team": "USA",
                "away_team": "Mexico",
                "kickoff_utc": "2026-06-15T19:00:00+00:00",
                "psc_home": 2.0, "psc_draw": 3.0, "psc_away": 4.0,
                "handicap_home": 10,   # ge=-5, le=5 → 10 is invalid
                "odds_handicap_H": 2.0, "odds_handicap_D": 3.0,
                "odds_handicap_A": 4.0,
            }],
        })
        assert r.status_code == 422

    def test_odds_below_one_rejected(self, monkeypatch):
        client = _build_client_with_mocks(monkeypatch)
        r = client.post("/api/v4/recommend/wc/single", json={
            "fixtures": [{
                "fixture_id": 1,
                "home_team": "USA",
                "away_team": "Mexico",
                "kickoff_utc": "2026-06-15T19:00:00+00:00",
                "psc_home": 0.5,   # gt=1.0 → 0.5 is invalid
                "psc_draw": 3.0, "psc_away": 4.0,
                "handicap_home": 0,
                "odds_handicap_H": 2.0, "odds_handicap_D": 3.0,
                "odds_handicap_A": 4.0,
            }],
        })
        assert r.status_code == 422


# ============ Degraded paths ============================================

class TestDegraded:

    def test_503_when_no_eloratings_snapshot(self, monkeypatch):
        """No eloratings parquets → 503 (degraded)."""
        from nutmeg.v4.api import v4_router

        # Empty glob — no snapshots
        real_glob = Path.glob
        def empty_glob(self, pattern):
            if "eloratings" in str(self) and pattern.startswith("eloratings_"):
                return iter([])
            return real_glob(self, pattern)
        monkeypatch.setattr(Path, "glob", empty_glob)

        app = FastAPI()
        app.include_router(v4_router, prefix="/api")
        client = TestClient(app)

        r = client.post("/api/v4/recommend/wc/single", json={
            "fixtures": [{
                "fixture_id": 1,
                "home_team": "USA",
                "away_team": "Mexico",
                "kickoff_utc": "2026-06-15T19:00:00+00:00",
                "psc_home": 1.85, "psc_draw": 3.50, "psc_away": 4.20,
                "handicap_home": -1,
                "odds_handicap_H": 2.40, "odds_handicap_D": 3.50,
                "odds_handicap_A": 2.80,
            }],
        })
        assert r.status_code == 503
        assert "eloratings" in r.json()["detail"].lower()

    def test_503_when_training_data_missing(self, monkeypatch):
        """Eloratings present but cup_history missing → 503 from train call."""
        client_base = _build_client_with_mocks(monkeypatch)  # set up the glob + elo snapshot

        # Override training to raise (simulates missing parquets)
        def raise_missing(*args, **kwargs):
            raise FileNotFoundError("WC_2018.parquet")
        monkeypatch.setattr(
            "nutmeg.v4.cli.wc_predict._train_combined_model",
            raise_missing,
        )

        r = client_base.post("/api/v4/recommend/wc/single", json={
            "fixtures": [{
                "fixture_id": 1,
                "home_team": "USA",
                "away_team": "Mexico",
                "kickoff_utc": "2026-06-15T19:00:00+00:00",
                "psc_home": 1.85, "psc_draw": 3.50, "psc_away": 4.20,
                "handicap_home": -1,
                "odds_handicap_H": 2.40, "odds_handicap_D": 3.50,
                "odds_handicap_A": 2.80,
            }],
        })
        assert r.status_code == 503
        assert "training data" in r.json()["detail"].lower()


# ============ Host-country handling =====================================

class TestHostCountry:

    def test_host_country_included_without_error(self, monkeypatch):
        """Optional host_country + host_advantage shouldn't break flow."""
        client = _build_client_with_mocks(monkeypatch)
        r = client.post("/api/v4/recommend/wc/single", json={
            "fixtures": [{
                "fixture_id": 1,
                "home_team": "USA",
                "away_team": "Mexico",
                "kickoff_utc": "2026-06-15T19:00:00+00:00",
                "psc_home": 1.85, "psc_draw": 3.50, "psc_away": 4.20,
                "handicap_home": -1,
                "odds_handicap_H": 2.40, "odds_handicap_D": 3.50,
                "odds_handicap_A": 2.80,
            }],
            "bankroll": 1000.0,
            "host_country": "USA",
            "host_advantage": 75.0,
        })
        assert r.status_code == 200
