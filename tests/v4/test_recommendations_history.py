"""V11 P1-FE#3 — tests for GET /v4/observation/recommendations-history.

The endpoint returns the last N days of parlay_recommendations grouped by
session date, joined with settlements to derive a hit/miss/partial/pending
outcome per recommendation.

Tests use a temp SQLite DB so the suite stays hermetic.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Create a temp observation DB + point routes at it via env var."""
    from nutmeg.v4.observation.store import init_db, open_db, insert_session, insert_parlay_recommendation, insert_settlement
    db = tmp_path / "observation.db"
    init_db(db)
    monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB", str(db))
    return {
        "path": str(db),
        "open_db": open_db,
        "insert_session": insert_session,
        "insert_parlay": insert_parlay_recommendation,
        "insert_settlement": insert_settlement,
    }


@pytest.fixture
def client():
    from nutmeg.v4.api import v4_router
    app = FastAPI()
    app.include_router(v4_router, prefix="/api")
    return TestClient(app)


def _utc_iso(days_ago: int = 0) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def _stub_legs():
    return [{
        "match_id": "EPL_Arsenal_vs_Liverpool",
        "home_team": "Arsenal",
        "away_team": "Liverpool",
        "league": "EPL",
        "market_type": "1x2",
        "outcome": "H",
        "odds": 1.85,
        "selections": [],
    }]


# ---------- Empty DB ---------------------------------------------------

class TestEmptyDB:
    def test_no_db_returns_empty(self, tmp_path, client, monkeypatch):
        """Missing observation DB → 200 with empty days + zero stats."""
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB",
                           str(tmp_path / "does-not-exist.db"))
        r = client.get("/api/v4/observation/recommendations-history?days=7")
        assert r.status_code == 200
        body = r.json()
        assert body["days"] == []
        assert body["stats"]["n_recommendations"] == 0
        assert body["stats"]["hit_rate"] is None

    def test_empty_db_with_schema_returns_empty(self, temp_db, client):
        """DB exists + schema but no rows → still empty."""
        r = client.get("/api/v4/observation/recommendations-history")
        assert r.status_code == 200
        assert r.json()["days"] == []


# ---------- Outcome derivation ----------------------------------------

class TestOutcomeDerivation:
    def test_outcome_label_helper(self):
        from nutmeg.v4.api.observation_routes import _outcome_label
        assert _outcome_label(1) == "hit"
        assert _outcome_label(0) == "miss"
        assert _outcome_label(-1) == "partial"
        assert _outcome_label(None) == "pending"

    def test_unsettled_recommendation_is_pending(self, temp_db, client):
        """parlay_rec without settlement row → outcome=pending."""
        with temp_db["open_db"](temp_db["path"]) as conn:
            sid = temp_db["insert_session"](
                conn, bankroll=1000, model_cutoff=None, model_trained_at=None,
                n_fixtures=1, n_recommendations=1, request={},
            )
            temp_db["insert_parlay"](
                conn, sid, rank=1, k_legs=2, is_compound=False,
                stake_units=10, kelly_stake=10.0, expected_return=20.0,
                hit_probability=0.5, ev_per_unit=0.1, log_growth=0.05,
                legs=_stub_legs(),
            )
        r = client.get("/api/v4/observation/recommendations-history")
        body = r.json()
        assert body["stats"]["n_recommendations"] == 1
        assert body["stats"]["n_pending"] == 1
        assert body["stats"]["n_hit"] == 0
        assert body["stats"]["hit_rate"] is None  # nothing settled

    def test_hit_settlement_marks_outcome_hit(self, temp_db, client):
        with temp_db["open_db"](temp_db["path"]) as conn:
            sid = temp_db["insert_session"](
                conn, bankroll=1000, model_cutoff=None, model_trained_at=None,
                n_fixtures=1, n_recommendations=1, request={},
            )
            rec_id = temp_db["insert_parlay"](
                conn, sid, rank=1, k_legs=2, is_compound=False,
                stake_units=10, kelly_stake=10.0, expected_return=20.0,
                hit_probability=0.5, ev_per_unit=0.1, log_growth=0.05,
                legs=_stub_legs(),
            )
            temp_db["insert_settlement"](
                conn, rec_id=rec_id, hit=1, stake=10.0,
                actual_payout=20.0, profit_loss=10.0,
            )
        body = client.get("/api/v4/observation/recommendations-history").json()
        assert body["stats"]["n_hit"] == 1
        assert body["stats"]["n_miss"] == 0
        assert body["stats"]["hit_rate"] == 1.0
        assert body["days"][0]["recommendations"][0]["outcome"] == "hit"
        assert body["days"][0]["recommendations"][0]["profit_loss"] == 10.0

    def test_partial_settlement_marks_partial(self, temp_db, client):
        with temp_db["open_db"](temp_db["path"]) as conn:
            sid = temp_db["insert_session"](
                conn, bankroll=1000, model_cutoff=None, model_trained_at=None,
                n_fixtures=1, n_recommendations=1, request={},
            )
            rec_id = temp_db["insert_parlay"](
                conn, sid, rank=1, k_legs=4, is_compound=True,
                stake_units=20, kelly_stake=20.0, expected_return=40.0,
                hit_probability=0.3, ev_per_unit=0.08, log_growth=0.02,
                legs=_stub_legs(),
            )
            temp_db["insert_settlement"](
                conn, rec_id=rec_id, hit=-1, stake=20.0,
                actual_payout=15.0, profit_loss=-5.0,
            )
        body = client.get("/api/v4/observation/recommendations-history").json()
        assert body["stats"]["n_partial"] == 1
        assert body["days"][0]["recommendations"][0]["outcome"] == "partial"


# ---------- Date grouping --------------------------------------------

class TestDateGrouping:
    def test_grouped_by_session_created_date(self, temp_db, client):
        """Two sessions on different dates → two day blocks."""
        from nutmeg.v4.observation.store import open_db
        with open_db(temp_db["path"]) as conn:
            # Insert two sessions and overwrite created_at to different days
            sid1 = temp_db["insert_session"](
                conn, bankroll=1000, model_cutoff=None, model_trained_at=None,
                n_fixtures=1, n_recommendations=1, request={},
            )
            sid2 = temp_db["insert_session"](
                conn, bankroll=1000, model_cutoff=None, model_trained_at=None,
                n_fixtures=1, n_recommendations=1, request={},
            )
            conn.execute(
                "UPDATE recommendation_sessions SET created_at = ? WHERE session_id = ?",
                (_utc_iso(days_ago=0), sid1),
            )
            conn.execute(
                "UPDATE recommendation_sessions SET created_at = ? WHERE session_id = ?",
                (_utc_iso(days_ago=3), sid2),
            )
            temp_db["insert_parlay"](
                conn, sid1, rank=1, k_legs=2, is_compound=False,
                stake_units=10, kelly_stake=10.0, expected_return=20.0,
                hit_probability=0.5, ev_per_unit=0.1, log_growth=0.05,
                legs=_stub_legs(),
            )
            temp_db["insert_parlay"](
                conn, sid2, rank=1, k_legs=2, is_compound=False,
                stake_units=10, kelly_stake=10.0, expected_return=20.0,
                hit_probability=0.5, ev_per_unit=0.1, log_growth=0.05,
                legs=_stub_legs(),
            )
        body = client.get("/api/v4/observation/recommendations-history?days=7").json()
        assert len(body["days"]) == 2
        # Days descending — most recent first
        assert body["days"][0]["date"] > body["days"][1]["date"]
        assert body["stats"]["n_recommendations"] == 2

    def test_excludes_rows_outside_window(self, temp_db, client):
        """days=7 → a 30-day-old recommendation must NOT appear."""
        from nutmeg.v4.observation.store import open_db
        with open_db(temp_db["path"]) as conn:
            sid = temp_db["insert_session"](
                conn, bankroll=1000, model_cutoff=None, model_trained_at=None,
                n_fixtures=1, n_recommendations=1, request={},
            )
            conn.execute(
                "UPDATE recommendation_sessions SET created_at = ? WHERE session_id = ?",
                (_utc_iso(days_ago=30), sid),
            )
            temp_db["insert_parlay"](
                conn, sid, rank=1, k_legs=2, is_compound=False,
                stake_units=10, kelly_stake=10.0, expected_return=20.0,
                hit_probability=0.5, ev_per_unit=0.1, log_growth=0.05,
                legs=_stub_legs(),
            )
        body = client.get("/api/v4/observation/recommendations-history?days=7").json()
        assert body["days"] == []
        assert body["stats"]["n_recommendations"] == 0


# ---------- Legs parsing ----------------------------------------------

class TestLegsParsing:
    def test_match_id_split_falls_back_when_home_away_missing(self):
        """legs_json without home_team/away_team keys → parse from match_id."""
        from nutmeg.v4.api.observation_routes import _parse_legs_json
        raw = json.dumps([{
            "match_id": "EPL_Arsenal_vs_Liverpool",
            "market_type": "1x2",
            "outcome": "H",
            "odds": 1.85,
        }])
        legs = _parse_legs_json(raw)
        assert len(legs) == 1
        assert legs[0].home_team == "Arsenal"
        assert legs[0].away_team == "Liverpool"

    def test_invalid_json_returns_empty(self):
        from nutmeg.v4.api.observation_routes import _parse_legs_json
        assert _parse_legs_json("not json") == []
        assert _parse_legs_json(None) == []
        assert _parse_legs_json("") == []

    def test_explicit_home_away_preserved(self):
        from nutmeg.v4.api.observation_routes import _parse_legs_json
        raw = json.dumps([{
            "match_id": "X",
            "home_team": "Real Madrid",
            "away_team": "Barcelona",
            "outcome": "A",
            "odds": 2.10,
        }])
        legs = _parse_legs_json(raw)
        assert legs[0].home_team == "Real Madrid"
        assert legs[0].away_team == "Barcelona"

    def test_match_id_with_digits_in_league_code_v12_w0_regression(self):
        """V12 W0 bug: league codes with digits (FRA_LIGUE_1, GER_2_BUNDESLIGA,
        PRT_LIGA_PORTUGAL_2, etc.) caused the regex ^[A-Z_]+_ to stop at
        the first digit, leaving e.g. "1_Saint Etienne" as the parsed
        home team. Fixed to ^[A-Z0-9_]+_ which strips the league prefix
        even when it contains digits.

        Caught 2026-05-28 when the V12 W0 first-real-bet session's
        Saint-Étienne and Greuther Fürth showed up in 推荐追溯 as
        "1_Saint Etienne" and "2_BUNDESLIGA_SpVgg Greuther Fürth".
        """
        from nutmeg.v4.api.observation_routes import _parse_legs_json

        # Ligue 1 — single trailing digit
        raw = json.dumps([{
            "match_id": "FRA_LIGUE_1_Saint Etienne_vs_Nice",
            "market_type": "handicap_1x2",
        }])
        legs = _parse_legs_json(raw)
        assert legs[0].home_team == "Saint Etienne", (
            f"Ligue 1: got home={legs[0].home_team!r} — digit in league code "
            "must not leak into team name"
        )
        assert legs[0].away_team == "Nice"

        # 2.Bundesliga — digit in the middle of league code
        raw2 = json.dumps([{
            "match_id": "GER_2_BUNDESLIGA_SpVgg Greuther Fürth_vs_Rot-Weiß Essen",
            "market_type": "handicap_1x2",
        }])
        legs2 = _parse_legs_json(raw2)
        assert legs2[0].home_team == "SpVgg Greuther Fürth", (
            f"2.BL: got home={legs2[0].home_team!r} — digits in middle "
            "of league code must not leak"
        )
        assert legs2[0].away_team == "Rot-Weiß Essen"

        # Sanity: digit-free league codes (EPL, La Liga) still work
        raw3 = json.dumps([{
            "match_id": "ESP_LA_LIGA_Real Madrid_vs_Barcelona",
            "market_type": "1x2",
        }])
        legs3 = _parse_legs_json(raw3)
        assert legs3[0].home_team == "Real Madrid"
        assert legs3[0].away_team == "Barcelona"

    def test_outcome_odds_read_from_selections_v12_w6_regression(self):
        """V12 W6 bug: recorder.py / record_parlay_session store the picked
        side + its odds under selections[0] — NOT at the leg top level.
        The history projection read d['outcome']/d['odds'] (both absent), so
        every 推荐追溯 leg rendered null outcome ('') and null odds ('—').
        Fixed to fall back to selections[0]."""
        from nutmeg.v4.api.observation_routes import _parse_legs_json
        raw = json.dumps([{
            "match_id": "FRA_LIGUE_1_Saint Etienne_vs_Nice",
            "market_type": "handicap_1x2",
            "selections": [
                {"outcome": "A", "odds": 1.51, "probability": 0.6418,
                 "edge": -0.031},
            ],
        }])
        legs = _parse_legs_json(raw)
        assert len(legs) == 1
        assert legs[0].outcome == "A", "picked side must come from selections[0]"
        assert legs[0].odds == 1.51, "odds must come from selections[0]"
        assert legs[0].market_type == "handicap_1x2"
        # league still recovered from the match_id prefix (no bridge map here)
        assert legs[0].league == "FRA_LIGUE_1"

    def test_top_level_outcome_odds_still_win_over_selections(self):
        """Backward-compat: a top-level outcome/odds (older rows / stubs)
        takes precedence over selections[0]."""
        from nutmeg.v4.api.observation_routes import _parse_legs_json
        raw = json.dumps([{
            "match_id": "EPL_Arsenal_vs_Liverpool",
            "market_type": "1x2",
            "outcome": "H",
            "odds": 1.85,
            "selections": [{"outcome": "A", "odds": 9.99}],
        }])
        legs = _parse_legs_json(raw)
        assert legs[0].outcome == "H"
        assert legs[0].odds == 1.85

    def test_session_meta_supplies_league_and_match_date(self):
        """league + match_date are NOT in the leg JSON; they come from the
        session's single_predictions bridge map passed by the caller (keyed
        f'{league}_{home}_vs_{away}', exactly like settlement.py)."""
        from nutmeg.v4.api.observation_routes import _parse_legs_json
        raw = json.dumps([{
            "match_id": "FRA_LIGUE_1_Saint Etienne_vs_Nice",
            "market_type": "handicap_1x2",
            "selections": [{"outcome": "A", "odds": 1.51}],
        }])
        meta = {
            "FRA_LIGUE_1_Saint Etienne_vs_Nice": {
                "league": "FRA_LIGUE_1",
                "match_date": "2026-05-26",
                "home_team": "Saint Etienne",
                "away_team": "Nice",
            }
        }
        legs = _parse_legs_json(raw, meta)
        assert legs[0].league == "FRA_LIGUE_1"
        assert legs[0].match_date == "2026-05-26"
        assert legs[0].home_team == "Saint Etienne"
        assert legs[0].away_team == "Nice"
        assert legs[0].outcome == "A"
        assert legs[0].odds == 1.51


# ---------- Leg enrichment end-to-end (V12 W6) ------------------------

class TestLegEnrichmentEndToEnd:
    """The history endpoint must enrich each leg with the picked outcome/odds
    (from selections[0]) AND league/match_date (from the session's
    single_predictions bridge), reproducing the exact shape the daily cron +
    /recommend/parlay recorder writes."""

    def test_legs_enriched_from_selections_and_bridge(self, temp_db, client):
        from nutmeg.v4.observation.store import (
            insert_single_prediction,
            open_db,
        )
        with open_db(temp_db["path"]) as conn:
            sid = temp_db["insert_session"](
                conn, bankroll=1000, model_cutoff=None, model_trained_at=None,
                n_fixtures=1, n_recommendations=1, request={},
            )
            # Bridge row — settlement keys it f"{league}_{home}_vs_{away}".
            insert_single_prediction(
                conn, sid, match_date="2026-05-26", league="FRA_LIGUE_1",
                home_team="Saint Etienne", away_team="Nice",
                lambda_home=1.1, lambda_away=1.3,
                p_home_1x2=0.30, p_draw_1x2=0.25, p_away_1x2=0.45,
                handicap_home=-1,
                p_home_handicap=0.30, p_draw_handicap=0.10,
                p_away_handicap=0.60,
            )
            # Parlay leg in the REAL recorder shape: selections-only, with NO
            # top-level outcome/odds/league/match_date.
            legs = [{
                "match_id": "FRA_LIGUE_1_Saint Etienne_vs_Nice",
                "market_type": "handicap_1x2",
                "selections": [
                    {"outcome": "A", "odds": 1.51,
                     "probability": 0.6418, "edge": -0.031},
                ],
            }]
            temp_db["insert_parlay"](
                conn, sid, rank=1, k_legs=1, is_compound=False,
                stake_units=10, kelly_stake=10.0, expected_return=15.1,
                hit_probability=0.64, ev_per_unit=-0.03, log_growth=0.0,
                legs=legs,
            )
        body = client.get(
            "/api/v4/observation/recommendations-history").json()
        leg = body["days"][0]["recommendations"][0]["legs"][0]
        assert leg["outcome"] == "A"             # from selections[0]
        assert leg["odds"] == 1.51               # from selections[0]
        assert leg["league"] == "FRA_LIGUE_1"    # from bridge
        assert leg["match_date"] == "2026-05-26"  # from bridge
        assert leg["home_team"] == "Saint Etienne"
        assert leg["away_team"] == "Nice"
        assert leg["market_type"] == "handicap_1x2"


# ---------- Query bounds ---------------------------------------------

class TestQueryBounds:
    def test_days_query_param_default_30(self, client, tmp_path, monkeypatch):
        """No days param → defaults to 30."""
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB",
                           str(tmp_path / "x.db"))
        r = client.get("/api/v4/observation/recommendations-history")
        assert r.status_code == 200

    def test_days_clamped_to_safe_bounds(self, client, tmp_path, monkeypatch):
        """days=0 / days=99999 must not break — clamped server-side."""
        monkeypatch.setenv("NUTMEG_V4_OBSERVATION_DB",
                           str(tmp_path / "x.db"))
        assert client.get("/api/v4/observation/recommendations-history?days=0").status_code == 200
        assert client.get("/api/v4/observation/recommendations-history?days=99999").status_code == 200


# ---------- Dashboard wiring (Day 2) ----------------------------------

class TestDashboardHistoryTab:
    @pytest.fixture(scope="class")
    def html(self):
        from nutmeg.v4.api import v4_router
        app = FastAPI()
        app.include_router(v4_router, prefix="/api")
        c = TestClient(app)
        return c.get("/api/v4/dashboard").text

    def test_tab_button_present(self, html):
        assert 'data-tab="history"' in html
        assert 'data-i18n="tab_history"' in html

    def test_tab_panel_present(self, html):
        assert 'id="tab-history"' in html

    def test_stats_card_present(self, html):
        # All 4 stat tiles
        for cid in ("history-n-total", "history-n-hit",
                    "history-n-pending", "history-hit-rate"):
            assert f'id="{cid}"' in html

    def test_range_filter_buttons(self, html):
        # 3-way segmented control
        for days in ("7", "30", "365"):
            assert f'data-history-range="{days}"' in html
        # One marked .active by default (30d)
        idx = html.index('data-history-range="30"')
        chunk = html[idx-200:idx+100]
        assert 'active' in chunk

    def test_outcome_chip_helper_defined(self, html):
        assert "function _outcomeChip" in html

    def test_load_and_render_functions_defined(self, html):
        assert "async function loadHistory" in html
        assert "function renderHistory" in html
        assert "function _historyRecCard" in html
        assert "function _historyDayBlock" in html

    def test_switchTab_triggers_load(self, html):
        """switchTab should call loadHistory when name === 'history'."""
        idx = html.index("function switchTab(name)")
        # Read the whole switchTab body (up to its column-0 closing brace) —
        # not a fixed char window. switchTab now has 3 tab auto-loaders
        # (wc / upcoming / history) so a hard-coded window false-failed once.
        end = html.index("\n}", idx)
        block = html[idx:end]
        assert "loadHistory" in block

    def test_endpoint_url_used(self, html):
        assert "/observation/recommendations-history?days=" in html

    def test_outcome_chip_classes_in_css(self, html):
        # All 4 chip styles
        for cls in (".chip-outcome-hit",
                    ".chip-outcome-miss",
                    ".chip-outcome-partial",
                    ".chip-outcome-pending"):
            assert cls in html

    def test_i18n_keys_present_both_locales(self, html):
        keys = ("tab_history", "h_history_title", "sub_history",
                "history_range_7d", "history_range_30d", "history_range_all",
                "metric_history_total", "metric_history_hit",
                "metric_history_pending", "metric_history_hit_rate",
                "history_outcome_hit", "history_outcome_miss",
                "history_outcome_partial", "history_outcome_pending",
                "history_empty_main", "history_empty_sub")
        for k in keys:
            assert html.count(f"{k}:") >= 2, f"{k} not in both i18n dicts"

    def test_uses_zhTeam_and_teamLogo(self, html):
        """History rec cards re-use the P1-FE#2 visual helpers."""
        idx = html.index("function _historyLegsHtml")
        body = html[idx:idx+1500]
        assert "zhTeam(" in body
        assert "teamLogo(" in body

    def test_history_leg_shows_market_badge(self, html):
        """V12 W6 — each leg row distinguishes 让球 vs 胜平负 (both reuse
        H/D/A → 主胜/平局/客胜 labels, so the market tag disambiguates)."""
        idx = html.index("function _historyLegsHtml")
        body = html[idx:idx+1500]
        assert "handicap_1x2" in body
        assert "让球" in body
        assert "胜平负" in body
        # Reads l.odds (the picked-side odds now populated by the backend).
        assert "l.odds" in body
