"""Tests for v4 observation layer: store, recorder, settlement, ROI."""
import json
import sqlite3
from pathlib import Path

import pytest

from nutmeg.v4.observation import (
    open_db,
    record_session,
    settle_unsettled,
    upsert_outcome,
)
from nutmeg.v4.observation.roi import (
    compute_headline,
    group_by_k_legs,
    group_by_league,
    calibration_buckets,
)
from nutmeg.v4.observation.settlement import _outcome_1x2, _outcome_handicap_1x2


# ---------- Helpers ----------

def _response_with_one_2_leg(handicap_home=None, sel_a="H", sel_b="H", odds_a=2.5, odds_b=3.0):
    """Build a minimal recommend response with ONE 2-串-1 recommendation."""
    legs = [
        {
            "match_id": "EPL_TeamA_vs_TeamB",
            "market_type": "1x2",
            "selections": [{"outcome": sel_a, "odds": odds_a, "probability": 0.4, "edge": 0.1}],
        },
        {
            "match_id": "ITA_SERIE_A_TeamC_vs_TeamD",
            "market_type": "handicap_1x2" if handicap_home is not None else "1x2",
            "selections": [{"outcome": sel_b, "odds": odds_b, "probability": 0.4, "edge": 0.1}],
        },
    ]
    return {
        "generated_at_utc": "2026-05-22T10:00:00+00:00",
        "model": {"training_cutoff": "2025-06-01", "trained_at_utc": "2026-05-22T09:00:00+00:00"},
        "bankroll": 1000.0,
        "n_fixtures": 2,
        "n_recommendations": 1,
        "single_match_predictions": [
            {"date": "2025-08-17", "league": "EPL", "home_team": "TeamA", "away_team": "TeamB",
             "lambda_home": 1.5, "lambda_away": 1.0, "p_home_1x2": 0.50, "p_draw_1x2": 0.25, "p_away_1x2": 0.25},
            {"date": "2025-08-17", "league": "ITA_SERIE_A", "home_team": "TeamC", "away_team": "TeamD",
             "lambda_home": 1.4, "lambda_away": 1.1, "p_home_1x2": 0.45, "p_draw_1x2": 0.28, "p_away_1x2": 0.27,
             "handicap_home": handicap_home},
        ],
        "recommendations": [
            {"rank": 1, "k_legs": 2, "is_compound": False, "stake_units": 1,
             "kelly_recommended_stake": 10.0, "expected_return": 5.0,
             "hit_probability": 0.16, "ev_per_unit": 0.50, "log_growth": 0.02,
             "legs": legs},
        ],
    }


# ---------- Pure functions ----------

class TestOutcomeMath:
    def test_1x2_home(self):
        assert _outcome_1x2(2, 1) == "H"
    def test_1x2_draw(self):
        assert _outcome_1x2(1, 1) == "D"
    def test_1x2_away(self):
        assert _outcome_1x2(0, 1) == "A"

    def test_handicap_zero_equals_1x2(self):
        for hg, ag in [(2, 1), (1, 1), (0, 1), (3, 0)]:
            assert _outcome_handicap_1x2(hg, ag, 0) == _outcome_1x2(hg, ag)

    def test_handicap_minus_one(self):
        # 3-0 with home -1 → 3-1-0 = 2 → H
        assert _outcome_handicap_1x2(3, 0, -1) == "H"
        # 1-0 with home -1 → 1-1-0 = 0 → D
        assert _outcome_handicap_1x2(1, 0, -1) == "D"
        # 0-0 with home -1 → 0-1-0 = -1 → A
        assert _outcome_handicap_1x2(0, 0, -1) == "A"

    def test_handicap_plus_one(self):
        # 0-1 with home +1 → 0+1-1 = 0 → D
        assert _outcome_handicap_1x2(0, 1, 1) == "D"


# ---------- Schema + recording ----------

class TestStore:
    def test_open_db_creates_schema(self, tmp_path):
        db = tmp_path / "x.db"
        with open_db(db) as conn:
            tables = [r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )]
        for expected in ("recommendation_sessions", "single_predictions",
                         "parlay_recommendations", "match_outcomes", "settlements"):
            assert expected in tables

    def test_record_session(self, tmp_path):
        db = tmp_path / "obs.db"
        sid = record_session(db, request={"foo": "bar"}, response=_response_with_one_2_leg())
        assert sid == 1
        with open_db(db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM recommendation_sessions").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM single_predictions").fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM parlay_recommendations").fetchone()[0] == 1


# ---------- Settlement ----------

class TestSettlement:
    def test_settle_with_no_outcomes_still_unknown(self, tmp_path):
        db = tmp_path / "obs.db"
        record_session(db, request={}, response=_response_with_one_2_leg())
        with open_db(db) as conn:
            counts = settle_unsettled(conn)
        assert counts["settled"] == 0
        assert counts["still_unknown"] == 1

    def test_settle_full_hit(self, tmp_path):
        db = tmp_path / "obs.db"
        # Both selections = H
        record_session(db, request={}, response=_response_with_one_2_leg(sel_a="H", sel_b="H"))
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2025-08-17", league="EPL",
                            home_team="TeamA", away_team="TeamB",
                            home_goals=2, away_goals=0)
            upsert_outcome(conn, match_date="2025-08-17", league="ITA_SERIE_A",
                            home_team="TeamC", away_team="TeamD",
                            home_goals=3, away_goals=1)
        with open_db(db) as conn:
            counts = settle_unsettled(conn)
        assert counts["settled"] == 1
        with open_db(db) as conn:
            s = conn.execute("SELECT * FROM settlements").fetchone()
        assert s["hit"] == 1
        assert s["stake"] == 10.0
        assert s["actual_payout"] == pytest.approx(10.0 * 2.5 * 3.0)
        assert s["profit_loss"] == pytest.approx(10.0 * 2.5 * 3.0 - 10.0)

    def test_settle_miss(self, tmp_path):
        db = tmp_path / "obs.db"
        record_session(db, request={}, response=_response_with_one_2_leg(sel_a="H", sel_b="A"))
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2025-08-17", league="EPL",
                            home_team="TeamA", away_team="TeamB",
                            home_goals=2, away_goals=0)
            upsert_outcome(conn, match_date="2025-08-17", league="ITA_SERIE_A",
                            home_team="TeamC", away_team="TeamD",
                            home_goals=3, away_goals=1)  # H, not A
        with open_db(db) as conn:
            settle_unsettled(conn)
            s = conn.execute("SELECT * FROM settlements").fetchone()
        assert s["hit"] == 0
        assert s["actual_payout"] == 0.0
        assert s["profit_loss"] == -10.0

    def test_settle_handicap(self, tmp_path):
        db = tmp_path / "obs.db"
        # Second leg handicap -1, select H. If home wins by 2+ → H wins.
        record_session(db, request={},
                        response=_response_with_one_2_leg(handicap_home=-1, sel_a="H", sel_b="H"))
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2025-08-17", league="EPL",
                            home_team="TeamA", away_team="TeamB",
                            home_goals=2, away_goals=0)
            upsert_outcome(conn, match_date="2025-08-17", league="ITA_SERIE_A",
                            home_team="TeamC", away_team="TeamD",
                            home_goals=2, away_goals=0)  # 2-1-0 = 1 > 0 → H
        with open_db(db) as conn:
            settle_unsettled(conn)
            s = conn.execute("SELECT * FROM settlements").fetchone()
        assert s["hit"] == 1

    def test_settle_idempotent(self, tmp_path):
        """Calling settle_unsettled twice should not duplicate settlements."""
        db = tmp_path / "obs.db"
        record_session(db, request={}, response=_response_with_one_2_leg(sel_a="H", sel_b="H"))
        with open_db(db) as conn:
            upsert_outcome(conn, match_date="2025-08-17", league="EPL",
                            home_team="TeamA", away_team="TeamB",
                            home_goals=2, away_goals=0)
            upsert_outcome(conn, match_date="2025-08-17", league="ITA_SERIE_A",
                            home_team="TeamC", away_team="TeamD",
                            home_goals=3, away_goals=1)
            settle_unsettled(conn)
        with open_db(db) as conn:
            counts2 = settle_unsettled(conn)
            n = conn.execute("SELECT COUNT(*) FROM settlements").fetchone()[0]
        assert counts2["settled"] == 0  # already settled, nothing new
        assert n == 1


# ---------- ROI ----------

class TestROI:
    def _setup_three_settled(self, db_path):
        """Helper: 3 different 2-leg parlays, 2 hit, 1 miss."""
        team_pairs = [("Arsenal","Liverpool","Inter","Fiorentina"),
                       ("Chelsea","Spurs","Milan","Roma"),
                       ("United","City","Juventus","Lazio")]
        for i, ((sel_a, sel_b, hg, ag), tp) in enumerate(zip([
            ("H", "H", 2, 0),
            ("H", "A", 2, 0),
            ("H", "H", 1, 0),
        ], team_pairs)):
            resp = _response_with_one_2_leg(sel_a=sel_a, sel_b=sel_b)
            ah, aw, ih, iw = tp
            resp["single_match_predictions"][0]["home_team"] = ah
            resp["single_match_predictions"][0]["away_team"] = aw
            resp["single_match_predictions"][1]["home_team"] = ih
            resp["single_match_predictions"][1]["away_team"] = iw
            resp["recommendations"][0]["legs"][0]["match_id"] = f"EPL_{ah}_vs_{aw}"
            resp["recommendations"][0]["legs"][1]["match_id"] = f"ITA_SERIE_A_{ih}_vs_{iw}"
            record_session(db_path, request={}, response=resp)
            with open_db(db_path) as conn:
                upsert_outcome(conn, match_date="2025-08-17", league="EPL",
                                home_team=ah, away_team=aw,
                                home_goals=hg, away_goals=ag)
                upsert_outcome(conn, match_date="2025-08-17", league="ITA_SERIE_A",
                                home_team=ih, away_team=iw,
                                home_goals=3, away_goals=1)
        with open_db(db_path) as conn:
            settle_unsettled(conn)

    def test_headline(self, tmp_path):
        db = tmp_path / "obs.db"
        self._setup_three_settled(db)
        with open_db(db) as conn:
            h = compute_headline(conn)
        assert h.n_settled == 3
        assert h.n_hit == 2
        assert h.n_miss == 1
        assert h.total_stake == 30.0  # 3 × 10
        # Each hit pays 10 × 2.5 × 3 = 75, two hits = 150 payout; profit = 150 - 30 = 120
        assert h.total_payout == pytest.approx(150.0)
        assert h.profit_loss == pytest.approx(120.0)
        assert h.roi == pytest.approx(4.0)

    def test_group_by_k_legs(self, tmp_path):
        db = tmp_path / "obs.db"
        self._setup_three_settled(db)
        with open_db(db) as conn:
            by_k = group_by_k_legs(conn)
        assert len(by_k) == 1
        assert by_k[0]["k_legs"] == 2
        assert by_k[0]["n"] == 3

    def test_group_by_league(self, tmp_path):
        db = tmp_path / "obs.db"
        self._setup_three_settled(db)
        with open_db(db) as conn:
            by_lg = group_by_league(conn)
        # First leg's league should be EPL (matches our test setup)
        leagues = {r["league"] for r in by_lg}
        assert "EPL" in leagues

    def test_calibration(self, tmp_path):
        db = tmp_path / "obs.db"
        self._setup_three_settled(db)
        with open_db(db) as conn:
            cal = calibration_buckets(conn, n_bins=5)
        # We have predictions around 0.16 → should fall in 0-20% bucket
        assert len(cal) >= 1
        for b in cal:
            assert 0 <= b["avg_predicted"] <= 1
            assert 0 <= b["actual_hit_rate"] <= 1
