"""V12 W5 — POST /v4/recommend/parlay (hand-picked 竞彩 串关).

The endpoint scores the EXACT legs the user selected in 近期赛事: server
recomputes each leg's model P → parlay hit P = ∏P, parlay odds = ∏ 竞彩 SP,
EV, fractional Kelly stake (same pipeline as 单关/复式). Optionally records
the combo as one settlement-compatible 单式 parlay row.

- Validation (leg count) is hermetic (pydantic, pre-artifact).
- Math + distinct-match check use the production artifact (skipped if absent).
- The record path is tested hermetically against a temp DB, including that the
  recorded parlay is SETTLEABLE by the existing V4 settlement.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client():
    import os

    from nutmeg.v4.api import v4_router
    os.environ.setdefault(
        "NUTMEG_V4_ARTIFACT_PATH",
        str(REPO_ROOT / "data" / "v4_model_cat_lineups"),
    )
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


def _leg(home, away, league="ESP_SEGUNDA_DIVISION", outcome="H", sp=2.1):
    return {
        "date": "2026-05-30", "league": league,
        "home_team": home, "away_team": away,
        "market_type": "1x2", "outcome": outcome, "sp": sp,
        "psc_home": 2.0, "psc_draw": 3.3, "psc_away": 3.6,
    }


# ============ Validation (hermetic — pydantic, pre-artifact) ===========

class TestParlayValidation:
    def test_one_leg_422(self, client):
        r = client.post("/api/v4/recommend/parlay",
                        json={"legs": [_leg("A", "B")], "bankroll": 1000})
        assert r.status_code == 422

    def test_nine_legs_422(self, client):
        legs = [_leg(f"H{i}", f"A{i}") for i in range(9)]
        r = client.post("/api/v4/recommend/parlay",
                        json={"legs": legs, "bankroll": 1000})
        assert r.status_code == 422


# ============ Math + distinct-match (needs artifact) ===================

class TestParlayMath:
    def test_distinct_matches_enforced(self, client):
        leg = _leg("Granada CF", "Sporting Gijon")
        r = client.post("/api/v4/recommend/parlay",
                        json={"legs": [leg, dict(leg)], "bankroll": 1000})
        if r.status_code == 503:
            pytest.skip("production artifact not available")
        assert r.status_code == 422
        assert "distinct" in r.text

    def test_product_math(self, client):
        legs = [
            _leg("Granada CF", "Sporting Gijon", sp=2.10),
            _leg("Vissel Kobe", "Kashima", league="JPN_J1", sp=2.33),
        ]
        r = client.post("/api/v4/recommend/parlay",
                        json={"legs": legs, "bankroll": 1000,
                              "kelly_fraction": 0.25, "max_stake_fraction": 0.05})
        if r.status_code == 503:
            pytest.skip("production artifact not available")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["k_legs"] == 2
        # hit_probability == ∏ leg model_p ; odds == ∏ leg sp ; ev == P*odds-1
        prod_p = 1.0
        prod_o = 1.0
        for le in d["legs"]:
            prod_p *= le["model_p"]
            prod_o *= le["sp"]
        assert abs(d["hit_probability"] - prod_p) < 1e-9
        assert abs(d["odds"] - prod_o) < 1e-9
        assert abs(d["ev_per_unit"] - (prod_p * prod_o - 1.0)) < 1e-9
        # stake is ¥2-quantized and only > 0 when the gate passes
        assert d["stake"] % 2 == 0
        if not d["passes_gate"]:
            assert d["stake"] == 0


# ============ Record path → settlement-compatible (temp DB) ============

class TestParlayRecordSettleable:
    def _response_dict(self):
        # A minimal ParlayRecordResponse-shaped dict (2 home picks).
        return {
            "generated_at_utc": "2026-05-29T12:00:00+00:00",
            "model": {"model_type": "catboost", "training_cutoff": "2025-05-01"},
            "bankroll": 1000.0,
            "k_legs": 2,
            "hit_probability": 0.25,
            "odds": 4.0,
            "ev_per_unit": 0.0,
            "raw_kelly_stake": 20.0,
            "stake": 20.0,
            "passes_gate": True,
            "recorded": False,
            "legs": [
                {"match_id": "ESP_SEGUNDA_DIVISION_Granada CF_vs_Sporting Gijon",
                 "league": "ESP_SEGUNDA_DIVISION", "market_type": "1x2",
                 "outcome": "H", "handicap_home": None, "sp": 2.0, "model_p": 0.5},
                {"match_id": "JPN_J1_Vissel Kobe_vs_Kashima",
                 "league": "JPN_J1", "market_type": "1x2",
                 "outcome": "H", "handicap_home": None, "sp": 2.0, "model_p": 0.5},
            ],
            # Bridge rows for settlement (match_id → outcome).
            "single_match_predictions": [
                {"date": "2026-05-30", "league": "ESP_SEGUNDA_DIVISION",
                 "home_team": "Granada CF", "away_team": "Sporting Gijon",
                 "lambda_home": 1.4, "lambda_away": 1.0,
                 "p_home_1x2": 0.5, "p_draw_1x2": 0.25, "p_away_1x2": 0.25,
                 "handicap_home": None, "p_home_handicap": None,
                 "p_draw_handicap": None, "p_away_handicap": None},
                {"date": "2026-05-30", "league": "JPN_J1",
                 "home_team": "Vissel Kobe", "away_team": "Kashima",
                 "lambda_home": 1.5, "lambda_away": 1.1,
                 "p_home_1x2": 0.5, "p_draw_1x2": 0.25, "p_away_1x2": 0.25,
                 "handicap_home": None, "p_home_handicap": None,
                 "p_draw_handicap": None, "p_away_handicap": None},
            ],
        }

    def test_records_one_settlement_compatible_parlay(self, tmp_path):
        from nutmeg.v4.observation import open_db, settle_unsettled, upsert_outcome
        from nutmeg.v4.observation.recorder import record_parlay_session

        db = tmp_path / "obs.db"
        sid = record_parlay_session(db, request={"bankroll": 1000.0},
                                    response=self._response_dict())
        assert isinstance(sid, int)

        # One parlay row, k_legs=2, is_compound=False, leg shape intact.
        with open_db(db) as conn:
            rows = conn.execute(
                "SELECT k_legs, is_compound, stake_units, kelly_stake, legs_json "
                "FROM parlay_recommendations"
            ).fetchall()
            assert len(rows) == 1
            row = rows[0]
            assert row["k_legs"] == 2
            assert not row["is_compound"]
            # AUDIT FIX (B1): a 串关 ticket = exactly 1 atomic combo (all legs
            # must hit), so stake_units == 1 (NOT ¥stake/¥2). The old ==10
            # pinned the bug that shrank every winning payout by ~stake/2.
            assert row["stake_units"] == 1
            legs = json.loads(row["legs_json"])
            assert legs[0]["match_id"] == "ESP_SEGUNDA_DIVISION_Granada CF_vs_Sporting Gijon"
            assert legs[0]["selections"][0]["outcome"] == "H"

        # Both legs hit (home wins) → the parlay must settle.
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2026-05-30",
                           league="ESP_SEGUNDA_DIVISION",
                           home_team="Granada CF", away_team="Sporting Gijon",
                           home_goals=2, away_goals=0)
            upsert_outcome(conn, match_date="2026-05-30", league="JPN_J1",
                           home_team="Vissel Kobe", away_team="Kashima",
                           home_goals=1, away_goals=0)
            counts = settle_unsettled(conn)
        assert counts["settled"] == 1, counts

    def test_handicap_leg_records_leg_level_handicap(self, tmp_path):
        from nutmeg.v4.observation import open_db
        from nutmeg.v4.observation.recorder import record_parlay_session

        resp = self._response_dict()
        resp["legs"][0]["market_type"] = "handicap"
        resp["legs"][0]["handicap_home"] = -1
        db = tmp_path / "obs.db"
        record_parlay_session(db, request={}, response=resp)
        with open_db(db) as conn:
            legs = json.loads(conn.execute(
                "SELECT legs_json FROM parlay_recommendations").fetchone()["legs_json"])
        # 'handicap' normalized to settlement vocab + leg-level handicap_home.
        assert legs[0]["market_type"] == "handicap_1x2"
        assert legs[0]["handicap_home"] == -1
