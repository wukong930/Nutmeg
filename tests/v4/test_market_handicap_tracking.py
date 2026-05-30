"""V12 W8 — 市场模式 让球 tracking: record → settle → ROI compatibility.

A market-mode 让球 pick (J1 / cup) is recorded with the MARKET-IMPLIED P (not
the OOD model), tagged model_type=market_handicap. Because the recorded shape
matches the regular pipeline (match_id = "{league}_{home}_vs_{away}",
market_type=handicap_1x2, handicap_home on the single_prediction), the generic
``settle_unsettled`` settles it for free once the result lands.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nutmeg.v4.observation.recorder import record_market_handicap_session
from nutmeg.v4.observation.settlement import settle_unsettled
from nutmeg.v4.observation.store import init_db, open_db, upsert_outcome

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client():
    import os

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from nutmeg.v4.api import v4_router
    os.environ.setdefault(
        "NUTMEG_V4_ARTIFACT_PATH",
        str(REPO_ROOT / "data" / "v4_model_cat_lineups"),
    )
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


def _prep(tmp_path):
    db = tmp_path / "obs.db"
    init_db(db)
    return db


def _record_kobe(db, *, outcome="H", odds=5.50, ev=-0.01, line=-1):
    """神户 vs 鹿岛 · 让球-1 · market-implied P ≈ (18/22/60)."""
    return record_market_handicap_session(
        db,
        league="JPN_J1", match_date="2026-05-30",
        home_team="Vissel Kobe", away_team="Kashima",
        handicap_home=line,
        p_handicap=(0.18, 0.22, 0.60),
        p_1x2=(0.40, 0.32, 0.28),
        pick_outcome=outcome, pick_odds=odds, pick_ev=ev,
        pick_stake=2.0, pick_expected_return=2.0 * ev,
        bankroll=1000.0, psc_1x2=(2.43, 3.04, 3.41),
    )


# ============ Recorder shape ==========================================

class TestRecorderShape:
    def test_session_tagged_market_handicap(self, tmp_path):
        db = _prep(tmp_path)
        sid = _record_kobe(db)
        assert sid > 0
        with sqlite3.connect(db) as conn:
            mt, meta = conn.execute(
                "SELECT model_type, metadata_json FROM recommendation_sessions "
                "WHERE session_id=?", (sid,)
            ).fetchone()
        assert mt == "market_handicap"
        assert "market_handicap" in meta  # session_kind tag

    def test_single_prediction_pins_handicap(self, tmp_path):
        db = _prep(tmp_path)
        sid = _record_kobe(db)
        with sqlite3.connect(db) as conn:
            lg, hh, ph_hc = conn.execute(
                "SELECT league, handicap_home, p_home_handicap "
                "FROM single_predictions WHERE session_id=?", (sid,)
            ).fetchone()
        assert lg == "JPN_J1"
        assert hh == -1
        assert ph_hc == pytest.approx(0.18)

    def test_leg_is_handicap_1x2(self, tmp_path):
        db = _prep(tmp_path)
        sid = _record_kobe(db, outcome="H")
        with sqlite3.connect(db) as conn:
            k_legs, legs = conn.execute(
                "SELECT k_legs, legs_json FROM parlay_recommendations "
                "WHERE session_id=?", (sid,)
            ).fetchone()
        assert k_legs == 1
        assert '"market_type": "handicap_1x2"' in legs
        assert '"outcome": "H"' in legs
        assert "JPN_J1_Vissel Kobe_vs_Kashima" in legs  # settle-pipeline match_id

    def test_bad_outcome_raises(self, tmp_path):
        db = _prep(tmp_path)
        with pytest.raises(ValueError):
            _record_kobe(db, outcome="X")


# ============ End-to-end: record → result lands → settle ===============

class TestEndToEndSettlement:
    def test_win_settles_positive(self, tmp_path):
        """神户 5-0 → home wins by 5 → covers 让球-1 (outcome H) → hit, +PnL."""
        db = _prep(tmp_path)
        _record_kobe(db, outcome="H", odds=5.50)
        with open_db(db) as conn:
            upsert_outcome(
                conn, match_date="2026-05-30", league="JPN_J1",
                home_team="Vissel Kobe", away_team="Kashima",
                home_goals=5, away_goals=0,
            )
        with open_db(db) as conn:
            counts = settle_unsettled(conn)
        assert counts["settled"] == 1
        assert counts["still_unknown"] == 0
        with sqlite3.connect(db) as conn:
            hit, stake, payout, pnl = conn.execute(
                "SELECT hit, stake, actual_payout, profit_loss FROM settlements"
            ).fetchone()
        assert hit == 1
        assert payout > stake
        assert pnl > 0

    def test_loss_settles_negative(self, tmp_path):
        """神户 1-0 → at 让球-1, (1-1)=0 vs 0 → D on the line → H bet loses."""
        db = _prep(tmp_path)
        _record_kobe(db, outcome="H", odds=5.50)
        with open_db(db) as conn:
            upsert_outcome(
                conn, match_date="2026-05-30", league="JPN_J1",
                home_team="Vissel Kobe", away_team="Kashima",
                home_goals=1, away_goals=0,
            )
        with open_db(db) as conn:
            counts = settle_unsettled(conn)
        assert counts["settled"] == 1
        with sqlite3.connect(db) as conn:
            hit, pnl = conn.execute(
                "SELECT hit, profit_loss FROM settlements"
            ).fetchone()
        assert hit == 0
        assert pnl < 0


# ============ Endpoint ================================================

class TestMarketHandicapEndpoint:
    def _payload(self, **over):
        p = {
            "league": "JPN_J1", "date": "2026-05-30",
            "home_team": "Vissel Kobe", "away_team": "Kashima",
            "psc_home": 2.43, "psc_draw": 3.04, "psc_away": 3.41,
            "psc_over25": 1.95, "psc_under25": 1.95,
            "handicap_home": -1,
            "odds_handicap_H": 5.50, "odds_handicap_D": 3.80, "odds_handicap_A": 1.46,
            "bankroll": 1000.0, "kelly_fraction": 0.25,
            "record_session": False,
        }
        p.update(over)
        return p

    def test_computes_market_implied_p_and_ev(self, client):
        r = client.post("/api/v4/recommend/market-handicap", json=self._payload())
        assert r.status_code == 200, r.text
        b = r.json()
        assert len(b["market_implied_p"]) == 3
        assert abs(sum(b["market_implied_p"]) - 1.0) < 1e-6
        assert b["best_outcome"] in ("H", "D", "A")
        # every EV slot present (3 SPs supplied)
        assert all(e is not None for e in b["ev_per_unit"])
        assert b["recorded"] is False  # record_session False

    def test_handicap_line_out_of_range_422(self, client):
        r = client.post("/api/v4/recommend/market-handicap",
                        json=self._payload(handicap_home=9))
        assert r.status_code == 422

    def test_records_when_gate_on(self, client, tmp_path, monkeypatch):
        db = tmp_path / "obs.db"
        init_db(db)
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
        r = client.post("/api/v4/recommend/market-handicap",
                        json=self._payload(record_session=True))
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["recorded"] is True
        assert b["session_id"] is not None
        with sqlite3.connect(db) as conn:
            mt = conn.execute(
                "SELECT model_type FROM recommendation_sessions"
            ).fetchone()[0]
        assert mt == "market_handicap"

    def test_no_record_when_gate_off(self, client, tmp_path, monkeypatch):
        monkeypatch.delenv("NUTMEG_V4_OBSERVATION_DB", raising=False)
        r = client.post("/api/v4/recommend/market-handicap",
                        json=self._payload(record_session=True))
        assert r.status_code == 200, r.text
        assert r.json()["recorded"] is False
