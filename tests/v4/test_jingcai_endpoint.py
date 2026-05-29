"""V12 W5 — POST /v4/recommend/jingcai (💴 竞彩盘口推荐).

Runs the SAME single+parlay+pool engine as /today-recommendations, but each
fixture's ``odds_1x2`` / handicap odds (= the 竞彩 SP the user typed) drive the
EV instead of Pinnacle. So this is the 竞彩 frame: EV = model P × 竞彩 SP − 1.

Tests use the production artifact (skipped if absent), except the hermetic
leg-count validation.
"""
from __future__ import annotations

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


def _fx(home, away, league, oh, od, oa, *, ph=2.0, pd=3.3, pa=3.6):
    """A fixture with 竞彩 odds_1x2 (oh/od/oa) + Pinnacle psc_* (model feature)."""
    return {
        "date": "2026-05-30", "league": league,
        "home_team": home, "away_team": away,
        "psc_home": ph, "psc_draw": pd, "psc_away": pa,
        "odds_1x2_H": oh, "odds_1x2_D": od, "odds_1x2_A": oa,
    }


class TestJingcaiValidation:
    def test_empty_fixtures_422(self, client):
        r = client.post("/api/v4/recommend/jingcai",
                        json={"fixtures": [], "bankroll": 1000})
        assert r.status_code == 422


class TestJingcaiBoard:
    def test_jingcai_odds_drive_ev_not_pinnacle(self, client):
        # Generous 竞彩 SP (> Pinnacle implied) → +EV singles. The SAME fixtures
        # priced AT Pinnacle (odds_1x2 stripped) → no edge → 0 recs. This is the
        # whole point of the 竞彩 frame.
        gen = [
            _fx("Granada CF", "Sporting Gijon", "ESP_SEGUNDA_DIVISION", 2.6, 3.2, 3.5),
            _fx("Vissel Kobe", "Kashima", "JPN_J1", 2.9, 3.3, 3.2, ph=2.33, pd=3.3, pa=3.0),
        ]
        r = client.post("/api/v4/recommend/jingcai",
                        json={"fixtures": gen, "bankroll": 1000, "min_ev": 0.05})
        if r.status_code == 503:
            pytest.skip("production artifact not available")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["single"] is not None and d["single"]["n_recommendations"] >= 1
        # every surfaced single is priced at the 竞彩 odds we sent + clears the gate
        for t in d["single"]["tickets"]:
            assert t["ev_per_unit"] >= 0.05

        flat = [{k: v for k, v in f.items() if not k.startswith("odds_1x2")} for f in gen]
        r2 = client.post("/api/v4/recommend/jingcai",
                         json={"fixtures": flat, "bankroll": 1000, "min_ev": 0.05})
        assert r2.status_code == 200
        # priced at Pinnacle now → the model finds no +5% edge → empty
        assert r2.json()["summary"]["total_recs"] == 0

    def test_parlay_board_survives_min_ev_gate(self, client):
        # Regression: RecommendResponse has NO total_stake field; the old
        # min_ev-gate code set it → raised → the 串关 board was silently dropped
        # (caught by the pipeline's except). With generous SP a parlay must now
        # appear. (Same bug existed in today-recommendations; fixed there too.)
        gen = [
            _fx("Granada CF", "Sporting Gijon", "ESP_SEGUNDA_DIVISION", 3.0, 3.4, 3.8),
            _fx("Vissel Kobe", "Kashima", "JPN_J1", 3.2, 3.4, 3.4, ph=2.33, pd=3.3, pa=3.0),
        ]
        r = client.post("/api/v4/recommend/jingcai",
                        json={"fixtures": gen, "bankroll": 1000, "min_ev": 0.05,
                              "include": ["parlay"]})
        if r.status_code == 503:
            pytest.skip("production artifact not available")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["parlay"] is not None and d["parlay"]["n_recommendations"] >= 1
        assert d["summary"]["total_stake"] > 0  # would be 0 if the board crashed out
