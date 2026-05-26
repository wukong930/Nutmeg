"""V11 post-ship — Path A++ WC handicap session recording.

Tests both the recorder unit (write to SQLite) and the env-gated dual-gate
endpoint integration:

  1. Server-side env var NUTMEG_V4_OBSERVATION_DB set
  2. Request-side record_session=True

Either gate off → no recording. Both on + at least one outcome with
stake>0 → session inserted into recommendation_sessions, single_predictions,
and parlay_recommendations.

Mirrors the V9 W3 test_record_session_gate.py pattern.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ============ Helpers (mirror test_wc_single_rec_endpoint) ===============

class _StubNationalTeamModel:
    """Hard-coded probs so EV is predictable."""
    def __init__(self, p_h=0.55, p_d=0.25, p_a=0.20):
        self._p = np.array([p_h, p_d, p_a], dtype=float)
        self._p /= self._p.sum()

    def predict_proba(self, df, host_country=None, host_advantage=0.0):
        return np.tile(self._p, (len(df), 1))


_FAKE_ELO = {
    "USA": {"elo": 1750.0, "rank": 25},
    "MEX": {"elo": 1700.0, "rank": 35},
}


def _build_client_with_mocks(monkeypatch, p_h=0.80, p_d=0.15, p_a=0.05):
    """Build a TestClient with WC training stubbed.

    Default p_h=0.80 produces a positive-EV outcome at typical SP, so the
    recorder actually has something to write (stake > 0)."""
    fake_snapshot = Path("/tmp/__fake_elo_recorder.parquet")

    from nutmeg.v4.api import v4_router

    monkeypatch.setattr(
        "nutmeg.v4.cli.wc_predict._train_combined_model",
        lambda *args, **kwargs: _StubNationalTeamModel(p_h, p_d, p_a),
    )
    monkeypatch.setattr(
        "nutmeg.v4.data.wc_training_frame.load_elo_snapshot",
        lambda _path: _FAKE_ELO,
    )

    real_glob = Path.glob
    def fake_glob(self, pattern):
        if "eloratings" in str(self) and pattern.startswith("eloratings_"):
            return iter([fake_snapshot])
        return real_glob(self, pattern)
    monkeypatch.setattr(Path, "glob", fake_glob)

    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


def _favorable_payload(record_session: bool):
    """A payload that should produce ≥1 stake>0 outcome with the
    stub model (p_h=0.80 vs odds 3.20 → big edge on H)."""
    return {
        "fixtures": [{
            "fixture_id": 12345,
            "home_team": "USA",
            "away_team": "Mexico",
            "kickoff_utc": "2026-06-15T19:00:00+00:00",
            "psc_home": 1.40,
            "psc_draw": 4.50,
            "psc_away": 8.00,
            "handicap_home": -1,
            "odds_handicap_H": 3.20,
            "odds_handicap_D": 3.50,
            "odds_handicap_A": 2.10,
        }],
        "bankroll": 10000.0,
        "kelly_fraction": 0.25,
        "max_stake_fraction": 0.05,
        "min_ev": 0.05,
        "blend_alpha": 0.4,
        "record_session": record_session,
    }


def _count_sessions(db_path: str) -> int:
    import sqlite3
    if not Path(db_path).exists():
        return 0
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM recommendation_sessions"
        ).fetchone()[0]


def _count_parlay_recs(db_path: str) -> int:
    import sqlite3
    if not Path(db_path).exists():
        return 0
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM parlay_recommendations"
        ).fetchone()[0]


def _count_single_preds(db_path: str) -> int:
    import sqlite3
    if not Path(db_path).exists():
        return 0
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM single_predictions"
        ).fetchone()[0]


# ============ Unit test: recorder writes the expected schema ===========

class TestRecorderUnit:
    """Directly test record_wc_handicap_session without the HTTP layer."""

    def test_writes_session_with_single_preds_and_parlay_recs(self, tmp_path):
        from nutmeg.v4.observation.recorder import record_wc_handicap_session
        from nutmeg.v4.observation.store import init_db

        db = tmp_path / "obs.db"
        init_db(db)

        request = {
            "fixtures": [{"fixture_id": 1, "home_team": "USA", "away_team": "Mexico"}],
            "bankroll": 10000.0,
            "blend_alpha": 0.4,
            "record_session": True,
        }
        response = {
            "generated_at_utc": "2026-05-26T12:00:00+00:00",
            "bankroll": 10000.0,
            "n_fixtures": 1,
            "n_recommendations": 1,
            "matches": [{
                "fixture_id": 1,
                "home_team": "USA",
                "away_team": "Mexico",
                "kickoff_utc": "2026-06-15T19:00:00+00:00",
                "handicap_home": -1,
                "p_1x2_blended": [0.65, 0.20, 0.15],
                "inferred_lambda_home": 1.50,
                "inferred_lambda_away": 1.10,
                "outcomes": [
                    {
                        "outcome": "H", "p_final": 0.55, "p_model": 0.50,
                        "p_market": 0.45, "odds": 2.20, "ev_per_unit": 0.21,
                        "kelly_fraction": 0.18, "stake": 200.0,
                        "expected_return": 42.0,
                    },
                    {
                        # Sub-EV — stake = 0, should NOT be recorded
                        "outcome": "D", "p_final": 0.20, "p_model": 0.22,
                        "p_market": 0.30, "odds": 3.50, "ev_per_unit": -0.30,
                        "kelly_fraction": 0.0, "stake": 0.0,
                        "expected_return": 0.0,
                    },
                    {
                        "outcome": "A", "p_final": 0.25, "p_model": 0.28,
                        "p_market": 0.25, "odds": 2.80, "ev_per_unit": -0.30,
                        "kelly_fraction": 0.0, "stake": 0.0,
                        "expected_return": 0.0,
                    },
                ],
            }],
            "total_stake": 200.0,
            "total_expected_return": 42.0,
            "blend_alpha": 0.4,
            "lambda_total_prior": 2.6,
        }

        sid = record_wc_handicap_session(db, request=request, response=response)
        assert isinstance(sid, int) and sid > 0

        # 1 session, 1 single_prediction (per fixture), 1 parlay_rec (only stake>0)
        assert _count_sessions(str(db)) == 1
        assert _count_single_preds(str(db)) == 1
        assert _count_parlay_recs(str(db)) == 1

        # Verify session metadata fields
        import sqlite3
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT model_type, n_fixtures, n_recommendations FROM recommendation_sessions"
            ).fetchone()
            assert row[0] == "national_team_handicap"
            assert row[1] == 1
            assert row[2] == 1

            # Verify the leg has the expected match_id pattern
            leg_json = conn.execute(
                "SELECT legs_json FROM parlay_recommendations"
            ).fetchone()[0]
            import json as _j
            legs = _j.loads(leg_json)
            assert legs[0]["match_id"] == "WC_USA_vs_Mexico"
            assert legs[0]["market_type"] == "handicap_1x2"
            assert legs[0]["selections"][0]["outcome"] == "H"

            # single_predictions row should have handicap_home + league=WC
            sp = conn.execute(
                "SELECT league, home_team, away_team, handicap_home "
                "FROM single_predictions"
            ).fetchone()
            assert sp[0] == "WC"
            assert sp[1] == "USA"
            assert sp[2] == "Mexico"
            assert sp[3] == -1

    def test_skips_when_all_outcomes_have_zero_stake(self, tmp_path):
        """No outcomes pass EV gate → session row inserted but 0 parlay rows."""
        from nutmeg.v4.observation.recorder import record_wc_handicap_session
        from nutmeg.v4.observation.store import init_db

        db = tmp_path / "obs.db"
        init_db(db)

        # Real endpoint always emits 3 outcomes (H/D/A) — when none pass
        # the EV gate they're surfaced with stake=0 (diagnostic). Mirror that.
        response_no_stakes = {
            "generated_at_utc": "2026-05-26T12:00:00+00:00",
            "bankroll": 1000.0, "n_fixtures": 1, "n_recommendations": 0,
            "matches": [{
                "fixture_id": 1, "home_team": "A", "away_team": "B",
                "kickoff_utc": "2026-06-15T19:00:00+00:00", "handicap_home": 0,
                "p_1x2_blended": [0.33, 0.34, 0.33],
                "inferred_lambda_home": 1.3, "inferred_lambda_away": 1.3,
                "outcomes": [
                    {"outcome": "H", "p_final": 0.30, "p_model": 0.30,
                     "p_market": 0.33, "odds": 2.90, "ev_per_unit": -0.13,
                     "kelly_fraction": 0.0, "stake": 0.0, "expected_return": 0.0},
                    {"outcome": "D", "p_final": 0.34, "p_model": 0.30,
                     "p_market": 0.33, "odds": 3.00, "ev_per_unit": 0.02,
                     "kelly_fraction": 0.0, "stake": 0.0, "expected_return": 0.0},
                    {"outcome": "A", "p_final": 0.36, "p_model": 0.30,
                     "p_market": 0.34, "odds": 2.80, "ev_per_unit": 0.01,
                     "kelly_fraction": 0.0, "stake": 0.0, "expected_return": 0.0},
                ],
            }],
            "total_stake": 0.0, "total_expected_return": 0.0,
            "blend_alpha": 0.4, "lambda_total_prior": 2.6,
        }
        sid = record_wc_handicap_session(db, request={}, response=response_no_stakes)
        assert sid > 0
        assert _count_sessions(str(db)) == 1
        assert _count_single_preds(str(db)) == 1  # fixture row still written
        assert _count_parlay_recs(str(db)) == 0   # but no recommendation rows


# ============ Endpoint-side dual gate ===================================

class TestEndpointDualGate:
    """Mirrors V9 W3 — both env var AND request flag must be on."""

    def test_env_off_request_on_no_write(self, monkeypatch, tmp_path):
        """No env var → recorder skipped regardless of request flag."""
        monkeypatch.delenv("NUTMEG_V4_OBSERVATION_DB", raising=False)
        client = _build_client_with_mocks(monkeypatch)
        r = client.post(
            "/api/v4/recommend/wc/single",
            json=_favorable_payload(record_session=True),
        )
        assert r.status_code == 200
        # Spot a hypothetical DB path — it shouldn't exist
        guess = tmp_path / "shouldnt_exist.db"
        assert not guess.exists()

    def test_env_on_request_off_no_write(self, monkeypatch, tmp_path):
        """Env set + flag off → no write."""
        db = tmp_path / "obs.db"
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
        client = _build_client_with_mocks(monkeypatch)
        r = client.post(
            "/api/v4/recommend/wc/single",
            json=_favorable_payload(record_session=False),
        )
        assert r.status_code == 200
        assert _count_sessions(str(db)) == 0

    def test_both_gates_on_writes_session(self, monkeypatch, tmp_path):
        """Env + flag → session written."""
        db = tmp_path / "obs.db"
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
        client = _build_client_with_mocks(monkeypatch)
        r = client.post(
            "/api/v4/recommend/wc/single",
            json=_favorable_payload(record_session=True),
        )
        assert r.status_code == 200
        body = r.json()
        # Sanity: the favorable payload should produce ≥1 recommendation
        assert body["n_recommendations"] >= 1
        # ... and a corresponding session row
        assert _count_sessions(str(db)) == 1
        assert _count_parlay_recs(str(db)) >= 1
        assert _count_single_preds(str(db)) == 1

    def test_endpoint_doesnt_500_on_recorder_failure(self, monkeypatch, tmp_path):
        """If the recorder raises, the response should still be returned."""
        db_dir = tmp_path / "definitely-not-a-dir"
        # Point env at a path whose parent doesn't exist → recorder explodes
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db_dir / "obs.db"))
        client = _build_client_with_mocks(monkeypatch)
        r = client.post(
            "/api/v4/recommend/wc/single",
            json=_favorable_payload(record_session=True),
        )
        # Endpoint must still return 200 — recorder errors are caught
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["n_fixtures"] == 1


# ============ Schema sanity ============================================

class TestSchemaShape:
    def test_record_session_field_defaults_false(self):
        from nutmeg.v4.api.schemas import WcSingleRecRequest, WcFixtureRecInput
        req = WcSingleRecRequest(fixtures=[WcFixtureRecInput(
            fixture_id=1, home_team="A", away_team="B",
            kickoff_utc="2026-06-15T19:00:00+00:00",
            psc_home=2.0, psc_draw=3.0, psc_away=4.0,
            handicap_home=0,
            odds_handicap_H=2.0, odds_handicap_D=3.0, odds_handicap_A=4.0,
        )])
        # Default False — backward-compat with V11 ship
        assert req.record_session is False
