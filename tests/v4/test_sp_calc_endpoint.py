"""V12 W3 — GET /v4/predictions/sp-calc + the playoff→market blend.

The sp-calc endpoint feeds the 近期赛事 tab's 竞彩 SP calculator: fixtures
across an N-day window, each with model 1X2 P + Pinnacle odds + handicap-line
P. Validation (days bounds) is hermetic. The blend + shape tests use the
production artifact (skipped if absent).
"""
from __future__ import annotations

from datetime import date
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


# ============ _pinnacle_devig_1x2 (pure) ==============================

class TestPinnacleDevig:
    def test_sums_to_one(self):
        from nutmeg.v4.api.routes import _pinnacle_devig_1x2
        p = _pinnacle_devig_1x2(2.0, 3.4, 3.6)
        assert p is not None
        assert abs(sum(p) - 1.0) < 1e-9

    def test_favorite_has_highest_prob(self):
        from nutmeg.v4.api.routes import _pinnacle_devig_1x2
        ph, pd_, pa = _pinnacle_devig_1x2(1.30, 5.0, 9.0)  # strong home favorite
        assert ph > pd_ and ph > pa

    def test_missing_leg_returns_none(self):
        from nutmeg.v4.api.routes import _pinnacle_devig_1x2
        assert _pinnacle_devig_1x2(2.0, None, 3.6) is None


# ============ Endpoint validation (hermetic) ==========================

class TestSpCalcValidation:
    @pytest.mark.parametrize("days", [0, 8, 99, -1])
    def test_days_out_of_range_422(self, client, days):
        r = client.get(f"/api/v4/predictions/sp-calc?days={days}")
        assert r.status_code == 422, r.text
        assert "days" in r.text


class TestSpCalcHappyPath:
    """Exercises the endpoint PAST validation (mocked fetch) so a missing
    import / NameError in the body can't slip through — it did once
    (_gather_rows/_Path/PINNACLE_BOOKMAKER_ID were local to today route)."""

    def _row(self, home, away):
        from datetime import date as _date
        return {
            "date": _date.today().isoformat(), "league": "EPL",
            "home_team": home, "away_team": away,
            "kickoff_utc": _date.today().isoformat() + "T19:00:00+00:00",
            "psc_home": 1.90, "psc_draw": 3.5, "psc_away": 4.2,
        }

    def test_returns_predictions_with_handicap_lines(self, client):
        from unittest.mock import patch
        rows = [self._row("Arsenal", "Chelsea")]
        with patch("nutmeg.v4.cli.ingest_odds._gather_rows",
                   return_value=(rows, 1, 0)):
            r = client.get("/api/v4/predictions/sp-calc?days=1")
        if r.status_code == 503:
            pytest.skip("production artifact not available")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["days"] == 1
        assert body["fixtures_fetched"] == 1
        assert len(body["predictions"]) == 1
        p = body["predictions"][0]
        assert {h["line"] for h in p["handicap_lines"]} == {-3, -2, -1, 0, 1, 2, 3}
        assert p["psc_home"] == 1.90
        # V12 W4 — kickoff_utc threads from the odds row → FixtureOddsInput →
        # SinglePrediction so the 近期赛事 cards can show + sort by time.
        assert p["kickoff_utc"] == rows[0]["kickoff_utc"]


# ============ Playoff→market blend (needs artifact) ===================

class TestPlayoffBlend:
    def _fixture(self, league="EPL"):
        from nutmeg.v4.api.schemas import FixtureOddsInput
        # strong home favorite per the market → de-vig p_home is large, so a
        # blend toward market is easy to detect.
        return FixtureOddsInput(
            date=date(2026, 3, 1), league=league,
            home_team="HomeTeamX", away_team="AwayTeamY",
            psc_home=1.30, psc_draw=5.0, psc_away=9.0,
        )

    def _load_art(self):
        from nutmeg.v4.model.persist import load_artifact
        adir = REPO_ROOT / "data" / "v4_model_cat_lineups"
        if not adir.exists():
            pytest.skip("production artifact not available")
        try:
            return load_artifact(adir)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"artifact load failed: {exc}")

    def test_handicap_lines_and_psc_echo(self, monkeypatch):
        from nutmeg.v4.api import routes
        monkeypatch.setattr("nutmeg.v4.data.playoff_context.detect_playoff",
                            lambda league, d: None)
        art = self._load_art()
        preds = routes._calc_predictions(art, [self._fixture()])
        assert len(preds) == 1
        p = preds[0]
        assert {h.line for h in p.handicap_lines} == {-3, -2, -1, 0, 1, 2, 3}
        assert p.psc_home == 1.30 and p.psc_away == 9.0

    def test_flagged_fixture_pulls_toward_market(self, monkeypatch):
        from nutmeg.v4.api import routes
        from nutmeg.v4.api.routes import _pinnacle_devig_1x2
        art = self._load_art()
        fx = [self._fixture()]
        pin_home = _pinnacle_devig_1x2(1.30, 5.0, 9.0)[0]

        # No playoff → raw model P (baseline).
        monkeypatch.setattr("nutmeg.v4.data.playoff_context.detect_playoff",
                            lambda league, d: None)
        base = routes._calc_predictions(art, fx)[0].p_home_1x2

        # Flagged playoff → P blended 0.3*model + 0.7*market.
        monkeypatch.setattr("nutmeg.v4.data.playoff_context.detect_playoff",
                            lambda league, d: object())
        blended = routes._calc_predictions(art, fx)[0].p_home_1x2

        # Same artifact + fixture → only the blend differs. Blended P must be
        # strictly closer to the Pinnacle de-vig P than the raw model P
        # (unless they already coincided).
        if abs(base - pin_home) > 1e-6:
            assert abs(blended - pin_home) < abs(base - pin_home)
            # And it should equal the exact convex combination.
            assert abs(blended - (0.3 * base + 0.7 * pin_home)) < 1e-6
