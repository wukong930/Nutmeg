"""Post-V13 — record_manual_bet: the "记此注" path.

Records EXACTLY the outcome + real stake the user placed (NOT the model's best
pick), INCLUDING −EV, and stays settlement-compatible (writes single_predictions
+ a stake_units=1 parlay_recommendations row). These tests guard the money path
end-to-end: record → settle → correct payout, for 1X2 and 让球, win and loss.
"""
from __future__ import annotations

import sqlite3

from nutmeg.v4.observation.recorder import record_manual_bet
from nutmeg.v4.observation.settlement import settle_unsettled
from nutmeg.v4.observation.store import init_db, open_db, upsert_outcome


def _bet(**over):
    b = {
        "league": "JPN_J1", "match_date": "2026-06-06",
        "home_team": "Kashima", "away_team": "Vissel Kobe",
        "market_type": "1x2", "handicap_home": None,
        "outcome": "H", "odds": 2.50, "probability": 0.35,  # ev = -0.125
        "stake": 100.0, "bankroll": 1000.0,
    }
    b.update(over)
    return b


def _settlement_row(db):
    """Return (hit, actual_payout, profit_loss) of the single settled rec, or None."""
    with sqlite3.connect(db) as conn:
        r = conn.execute(
            "SELECT hit, actual_payout, profit_loss FROM settlements"
        ).fetchone()
    return r


class TestRecordsNegativeEV:
    def test_writes_schema_for_a_negative_ev_bet(self, tmp_path):
        db = tmp_path / "obs.db"
        init_db(db)
        sid = record_manual_bet(db, bet=_bet())  # −EV by construction
        assert sid > 0
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM recommendation_sessions").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM single_predictions").fetchone()[0] == 1
            row = conn.execute(
                "SELECT stake_units, kelly_stake, ev_per_unit FROM parlay_recommendations"
            ).fetchone()
            assert row[0] == 1                      # stake_units=1 (the money trap)
            assert abs(row[1] - 100.0) < 1e-9       # real money in kelly_stake
            assert row[2] < 0                       # −EV recorded, not gated away
            mt = conn.execute("SELECT model_type FROM recommendation_sessions").fetchone()[0]
            assert mt == "manual"

    def test_rejects_zero_stake(self, tmp_path):
        db = tmp_path / "obs.db"
        init_db(db)
        try:
            record_manual_bet(db, bet=_bet(stake=0.0))
            raised = False
        except ValueError:
            raised = True
        assert raised


class TestSettles1x2:
    def test_home_bet_wins_on_home_win(self, tmp_path):
        db = tmp_path / "obs.db"
        init_db(db)
        record_manual_bet(db, bet=_bet(outcome="H", odds=2.50, stake=100.0))
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2026-06-06", league="JPN_J1",
                           home_team="Kashima", away_team="Vissel Kobe",
                           home_goals=2, away_goals=0)
            counts = settle_unsettled(conn)
        assert counts["settled"] == 1
        hit, payout, pl = _settlement_row(db)
        assert hit == 1
        assert abs(payout - 250.0) < 1e-6          # stake × odds
        assert abs(pl - 150.0) < 1e-6              # +150 profit

    def test_away_bet_loses_on_home_win(self, tmp_path):
        db = tmp_path / "obs.db"
        init_db(db)
        record_manual_bet(db, bet=_bet(outcome="A", odds=3.40, stake=100.0))
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2026-06-06", league="JPN_J1",
                           home_team="Kashima", away_team="Vissel Kobe",
                           home_goals=2, away_goals=0)
            settle_unsettled(conn)
        hit, payout, pl = _settlement_row(db)
        assert hit == 0
        assert abs(payout) < 1e-6
        assert abs(pl + 100.0) < 1e-6              # −100 loss


class TestSettlesHandicap:
    def test_home_minus1_covers_on_2_0(self, tmp_path):
        db = tmp_path / "obs.db"
        init_db(db)
        # 让主-1: home must win by ≥2. 2-0 covers → 让胜 (H) wins.
        record_manual_bet(db, bet=_bet(
            market_type="handicap", handicap_home=-1, outcome="H",
            odds=2.10, stake=100.0))
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2026-06-06", league="JPN_J1",
                           home_team="Kashima", away_team="Vissel Kobe",
                           home_goals=2, away_goals=0)
            counts = settle_unsettled(conn)
        assert counts["settled"] == 1
        hit, payout, pl = _settlement_row(db)
        assert hit == 1
        assert abs(payout - 210.0) < 1e-6

    def test_home_minus1_pushes_to_loss_on_1_0(self, tmp_path):
        db = tmp_path / "obs.db"
        init_db(db)
        # 让主-1, home wins by exactly 1 (1-0) → handicap result is a draw (D),
        # so the 让胜 (H) bet does NOT win.
        record_manual_bet(db, bet=_bet(
            market_type="handicap", handicap_home=-1, outcome="H",
            odds=2.10, stake=100.0))
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2026-06-06", league="JPN_J1",
                           home_team="Kashima", away_team="Vissel Kobe",
                           home_goals=1, away_goals=0)
            settle_unsettled(conn)
        hit, _, pl = _settlement_row(db)
        assert hit == 0
        assert abs(pl + 100.0) < 1e-6


# ============ Endpoint dual-gate (env + request flag) ==================

class TestEndpoint:
    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from nutmeg.v4.api import v4_router
        app = FastAPI()
        app.include_router(v4_router, prefix="/api")
        return TestClient(app)

    def _payload(self, record_session):
        return {
            "league": "JPN_J1", "date": "2026-06-06",
            "home_team": "Kashima", "away_team": "Vissel Kobe",
            "market_type": "1x2", "outcome": "H",
            "odds": 2.5, "probability": 0.35, "stake": 100.0,
            "bankroll": 1000.0, "record_session": record_session,
        }

    def test_both_gates_record_negative_ev(self, monkeypatch, tmp_path):
        db = tmp_path / "obs.db"
        init_db(db)
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
        r = self._client().post("/api/v4/observation/record-bet",
                                json=self._payload(True))
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["recorded"] is True
        assert abs(b["ev"] - (-0.125)) < 1e-6     # 0.35*2.5-1, −EV recorded
        assert b["session_id"]
        assert _settlement_count_recs(db) == 1

    def test_env_off_not_recorded_but_ev_returned(self, monkeypatch):
        monkeypatch.delenv("NUTMEG_V4_OBSERVATION_DB", raising=False)
        r = self._client().post("/api/v4/observation/record-bet",
                                json=self._payload(True))
        assert r.status_code == 200
        b = r.json()
        assert b["recorded"] is False
        assert abs(b["ev"] - (-0.125)) < 1e-6     # EV still computed

    def test_request_flag_off_not_recorded(self, monkeypatch, tmp_path):
        db = tmp_path / "obs.db"
        init_db(db)
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
        r = self._client().post("/api/v4/observation/record-bet",
                                json=self._payload(False))
        assert r.status_code == 200
        assert r.json()["recorded"] is False
        assert _settlement_count_recs(db) == 0


def _settlement_count_recs(db):
    with sqlite3.connect(db) as conn:
        return conn.execute("SELECT COUNT(*) FROM parlay_recommendations").fetchone()[0]
