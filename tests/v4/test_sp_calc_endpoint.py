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


# ============ Pending fixtures (V12 W6 — 待开盘) =======================

class TestSpCalcPendingFixtures:
    """V12 W6 — fixtures whose Pinnacle line hasn't opened (psc_* = None) are
    returned as `pending_fixtures` (待开盘), NOT scored — psc is a strong model
    feature, so a psc-free P would mislead."""

    def _scored(self, home, away):
        from datetime import date as _date
        return {
            "date": _date.today().isoformat(), "league": "JPN_J1",
            "home_team": home, "away_team": away,
            "kickoff_utc": _date.today().isoformat() + "T05:00:00+00:00",
            "psc_home": 2.34, "psc_draw": 3.21, "psc_away": 3.33,
        }

    def _pending(self, home, away):
        from datetime import date as _date
        return {
            "date": _date.today().isoformat(), "league": "JPN_J1",
            "home_team": home, "away_team": away,
            "kickoff_utc": _date.today().isoformat() + "T06:00:00+00:00",
            "psc_home": None, "psc_draw": None, "psc_away": None,
        }

    def test_no_pinnacle_fixtures_are_pending_not_scored(self, client):
        from unittest.mock import patch
        rows = [
            self._scored("Vissel Kobe", "Kashima"),
            self._pending("Sanfrecce Hiroshima", "Kawasaki Frontale"),
            self._pending("Nagoya Grampus", "Machida Zelvia"),
        ]
        with patch("nutmeg.v4.cli.ingest_odds._gather_rows",
                   return_value=(rows, 3, 0)):
            r = client.get("/api/v4/predictions/sp-calc?days=1")
        if r.status_code == 503:
            pytest.skip("production artifact not available")
        assert r.status_code == 200, r.text
        body = r.json()
        # 1 scored (has psc), 2 待开盘
        assert len(body["predictions"]) == 1
        assert body["predictions"][0]["home_team"] == "Vissel Kobe"
        assert len(body["pending_fixtures"]) == 2
        assert {p["home_team"] for p in body["pending_fixtures"]} == {
            "Sanfrecce Hiroshima", "Nagoya Grampus"}
        # pending carry metadata but NO probabilities
        pf = body["pending_fixtures"][0]
        assert pf["league"] == "JPN_J1"
        assert pf["reason"] == "pinnacle_not_open"
        assert "p_home_1x2" not in pf
        # fixtures_fetched counts BOTH scored + pending
        assert body["fixtures_fetched"] == 3

    def test_endpoint_calls_gather_with_require_odds_false(self, client):
        """The endpoint must pass require_odds=False, else no-Pinnacle fixtures
        are dropped before we can list them as 待开盘."""
        from unittest.mock import patch
        with patch("nutmeg.v4.cli.ingest_odds._gather_rows",
                   return_value=([], 0, 0)) as gr:
            r = client.get("/api/v4/predictions/sp-calc?days=1")
        if r.status_code == 503:
            pytest.skip("production artifact not available")
        assert gr.called
        assert gr.call_args.kwargs.get("require_odds") is False


# ============ Cup market mode (V12 W7) ================================

class TestCupMarket:
    """V12 W7 — /predictions/cup-market: Tier-1 cups priced off Pinnacle de-vig
    (market mode), NOT the model. No-line fixtures → 待开盘."""

    @pytest.mark.parametrize("days", [0, 8, -1])
    def test_days_out_of_range_422(self, client, days):
        r = client.get(f"/api/v4/predictions/cup-market?days={days}")
        assert r.status_code == 422, r.text

    def test_devig_drives_probability_not_model(self, client):
        from unittest.mock import patch
        # PSG–Arsenal UCL final Pinnacle line → de-vig ≈ 41.0 / 28.7 / 30.3
        rows = [{
            "date": "2026-05-30", "league": "UCL",
            "home_team": "Paris Saint Germain", "away_team": "Arsenal",
            "kickoff_utc": "2026-05-30T16:00:00+00:00",
            "psc_home": 2.36, "psc_draw": 3.37, "psc_away": 3.20,
        }]
        with patch("nutmeg.v4.cli.ingest_odds._gather_rows", return_value=(rows, 1, 0)):
            r = client.get("/api/v4/predictions/cup-market?days=1")
        assert r.status_code == 200, r.text
        p = r.json()["predictions"][0]
        assert p["market_mode"] is True
        # V12 W8 — market mode now carries market-implied 让球 lines (a DC grid
        # reverse-fit to the de-vig 1X2; O/U absent here → 1X2-only fit). Still
        # NOT a model prediction (λ stays 0, P is pure Pinnacle de-vig).
        assert len(p["handicap_lines"]) == 7    # integer lines −3..+3
        assert p["lambda_home"] == 0.0          # λ not surfaced for market mode
        # handicap line 0 == straight 1X2 (the fit reproduces the de-vig 1X2)
        hl0 = next(h for h in p["handicap_lines"] if h["line"] == 0)
        assert abs(hl0["p_home"] - p["p_home_1x2"]) < 0.02
        # de-vig of 2.36 / 3.37 / 3.20 (sums to 1.0)
        assert abs(p["p_home_1x2"] - 0.410) < 0.005
        assert abs(p["p_draw_1x2"] - 0.287) < 0.005
        assert abs(p["p_away_1x2"] - 0.303) < 0.005
        assert abs(sum((p["p_home_1x2"], p["p_draw_1x2"], p["p_away_1x2"])) - 1.0) < 1e-6
        assert p["psc_home"] == 2.36            # echoes Pinnacle odds

    def test_market_handicap_uses_over_under_anchor(self, client):
        """V12 W8 — when the row carries Pinnacle O/U, the market-implied 让球
        is double-anchored (1X2 + total). A higher P(over) → higher goal total
        → more favourite blowouts → higher 让胜 at the −1 line."""
        from unittest.mock import patch

        def _row(over, under):
            return [{
                "date": "2026-05-30", "league": "JPN_J1",
                "home_team": "Vissel Kobe", "away_team": "Kashima",
                "kickoff_utc": "2026-05-30T04:00:00+00:00",
                "psc_home": 2.43, "psc_draw": 3.04, "psc_away": 3.41,
                "psc_over25": over, "psc_under25": under,
            }]
        # Low-total line (under favoured) vs high-total line (over favoured).
        with patch("nutmeg.v4.cli.ingest_odds._gather_rows", return_value=(_row(2.6, 1.5), 1, 0)):
            lo = client.get("/api/v4/predictions/cup-market?days=1").json()["predictions"][0]
        with patch("nutmeg.v4.cli.ingest_odds._gather_rows", return_value=(_row(1.5, 2.6), 1, 0)):
            hi = client.get("/api/v4/predictions/cup-market?days=1").json()["predictions"][0]
        hc_lo = next(h for h in lo["handicap_lines"] if h["line"] == -1)["p_home"]
        hc_hi = next(h for h in hi["handicap_lines"] if h["line"] == -1)["p_home"]
        assert hc_hi > hc_lo, "higher total should raise P(home wins by ≥2)"

    def test_no_line_cup_is_pending(self, client):
        from unittest.mock import patch
        rows = [{
            "date": "2026-05-31", "league": "FAC",
            "home_team": "Lower Club", "away_team": "Other Club",
            "kickoff_utc": "2026-05-31T14:00:00+00:00",
            "psc_home": None, "psc_draw": None, "psc_away": None,
        }]
        with patch("nutmeg.v4.cli.ingest_odds._gather_rows", return_value=(rows, 1, 0)):
            r = client.get("/api/v4/predictions/cup-market?days=1")
        body = r.json()
        assert body["predictions"] == []
        assert len(body["pending_fixtures"]) == 1
        assert body["pending_fixtures"][0]["league"] == "FAC"

    def test_tier1_competition_set(self):
        from nutmeg.v4.api.routes import _CUP_MARKET_COMPETITIONS
        for c in ("UCL", "UEL", "UECL", "FAC", "COPA_DEL_REY", "COPPA_ITALIA",
                  "DFB_POKAL", "COUPE_DE_FRANCE", "WC", "EURO", "WC_QUAL_UEFA"):
            assert c in _CUP_MARKET_COMPETITIONS, f"{c} missing from Tier-1 cups"
        # must NOT include leagues, nor excluded (Asian/SA) competitions
        assert "EPL" not in _CUP_MARKET_COMPETITIONS
        assert "COPA_AMERICA" not in _CUP_MARKET_COMPETITIONS


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
