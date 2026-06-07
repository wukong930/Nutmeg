"""V11 post-ship — WC settle mirrors into match_outcomes.

`settle_wc_prediction` previously only wrote to the WC-specific
`wc_predictions` table. That meant WC handicap recommendations
(recorded via `record_wc_handicap_session`) sat unsettled forever
because the regular `settle_unsettled` pipeline reads `match_outcomes`.

This bridge makes one CLI call (`nutmeg-wc-settle`) close out:
  1. wc_predictions (existing behavior)
  2. match_outcomes with league="WC" (NEW)
  3. → settle_unsettled picks up the recommendation rows

End-to-end: record a recommendation → settle the WC fixture → run
settle_unsettled → the rec lands in `settlements` with
hit/profit_loss computed.
"""
from __future__ import annotations

import sqlite3

from nutmeg.v4.observation.recorder import record_wc_handicap_session
from nutmeg.v4.observation.settlement import settle_unsettled
from nutmeg.v4.observation.store import init_db, open_db
from nutmeg.v4.observation.wc_log import (
    record_wc_prediction,
    settle_wc_prediction,
)


def _prep_db(tmp_path):
    db = tmp_path / "obs.db"
    init_db(db)
    return db


def _record_wc_pred_row(db, fixture_id=9001, match_date="2026-06-15",
                       home="USA", away="Mexico"):
    """Insert a wc_predictions row so settle_wc_prediction has something
    to update. Wraps the existing record_wc_prediction(prediction, ...)
    upsert helper."""
    prediction = {
        "fixture_id": fixture_id,
        "kickoff_utc": f"{match_date}T19:00:00+00:00",
        "round": None,
        "home_team": home,
        "away_team": away,
        "home_elo": 1750.0,
        "away_elo": 1700.0,
        "home_adv": 50.0,
        "has_pinnacle": True,
        "psc_home": 1.85, "psc_draw": 3.50, "psc_away": 4.20,
        "p_home": 0.60, "p_draw": 0.25, "p_away": 0.15,
        "p_home_elo_only": 0.55, "p_draw_elo_only": 0.27, "p_away_elo_only": 0.18,
        "source": "blend(α=0.4)",
        "blend_alpha": 0.4,
    }
    record_wc_prediction(db, prediction, season=2026)


# ============ Bridge: dual-write ========================================

class TestSettleBridgeWritesMatchOutcomes:

    def test_settle_writes_to_match_outcomes(self, tmp_path):
        """After settle_wc_prediction, match_outcomes has a WC row."""
        db = _prep_db(tmp_path)
        _record_wc_pred_row(db)

        ok = settle_wc_prediction(
            db, fixture_id=9001, home_goals=2, away_goals=1,
        )
        assert ok is True

        # match_outcomes now has the WC row
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT match_date, league, home_team, away_team, "
                "       home_goals, away_goals "
                "FROM match_outcomes WHERE league = 'WC'"
            ).fetchone()
        assert row is not None
        match_date, league, home, away, hg, ag = row
        assert league == "WC"
        assert home == "USA"
        assert away == "Mexico"
        assert hg == 2
        assert ag == 1
        assert match_date == "2026-06-15"

    def test_settle_no_pred_no_match_outcomes_write(self, tmp_path):
        """If wc_predictions has no row for this fixture, settle returns
        False AND doesn't pollute match_outcomes with a phantom row."""
        db = _prep_db(tmp_path)
        ok = settle_wc_prediction(
            db, fixture_id=9999, home_goals=1, away_goals=1,
        )
        assert ok is False
        with sqlite3.connect(db) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM match_outcomes WHERE league = 'WC'"
            ).fetchone()[0]
        assert count == 0

    def test_settle_idempotent_on_match_outcomes(self, tmp_path):
        """Re-settling (e.g. correcting a typo) overwrites match_outcomes
        in place — no duplicate rows."""
        db = _prep_db(tmp_path)
        _record_wc_pred_row(db)

        # First settle — wrong score
        settle_wc_prediction(db, fixture_id=9001, home_goals=3, away_goals=0)
        # Correction
        settle_wc_prediction(db, fixture_id=9001, home_goals=2, away_goals=1)

        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                "SELECT home_goals, away_goals FROM match_outcomes "
                "WHERE league = 'WC'"
            ).fetchall()
        assert len(rows) == 1
        assert rows[0] == (2, 1)

    def test_settle_still_returns_true_if_mirror_idempotent(self, tmp_path):
        """A WC fixture for which match_outcomes already has a (league,
        date, home, away) row (e.g. user manually inserted it) is OK —
        the upsert just refreshes it."""
        db = _prep_db(tmp_path)
        _record_wc_pred_row(db)
        # Pre-populate match_outcomes manually
        from nutmeg.v4.observation.store import upsert_outcome
        with open_db(db) as conn:
            upsert_outcome(
                conn, match_date="2026-06-15", league="WC",
                home_team="USA", away_team="Mexico",
                home_goals=0, away_goals=0,
            )
        # Now the proper settle should overwrite
        ok = settle_wc_prediction(
            db, fixture_id=9001, home_goals=2, away_goals=1,
        )
        assert ok is True
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT home_goals, away_goals FROM match_outcomes "
                "WHERE league = 'WC'"
            ).fetchone()
        assert row == (2, 1)


# ============ End-to-end: recommendation → settle → resolved ============

class TestEndToEndSettlement:
    """Path A++ recommendation → wc-settle → settle_unsettled → DONE."""

    def test_recorded_rec_settles_after_wc_settle(self, tmp_path):
        db = _prep_db(tmp_path)

        # 1. Record a WC handicap recommendation (stake>0 on H @ HC -1)
        #    Using a minimal but valid response payload.
        response = {
            "generated_at_utc": "2026-05-26T12:00:00+00:00",
            "bankroll": 10000.0,
            "n_fixtures": 1,
            "n_recommendations": 1,
            "matches": [{
                "fixture_id": 9001,
                "home_team": "USA",
                "away_team": "Mexico",
                "kickoff_utc": "2026-06-15T19:00:00+00:00",
                "handicap_home": -1,    # USA must win by 2+
                "p_1x2_blended": [0.55, 0.25, 0.20],
                "inferred_lambda_home": 1.50,
                "inferred_lambda_away": 1.10,
                "outcomes": [
                    {"outcome": "H", "p_final": 0.55, "p_model": 0.50,
                     "p_market": 0.45, "odds": 2.20, "ev_per_unit": 0.21,
                     "kelly_fraction": 0.18, "stake": 100.0,
                     "expected_return": 21.0},
                    {"outcome": "D", "p_final": 0.20, "p_model": 0.22,
                     "p_market": 0.30, "odds": 3.50, "ev_per_unit": -0.30,
                     "kelly_fraction": 0.0, "stake": 0.0,
                     "expected_return": 0.0},
                    {"outcome": "A", "p_final": 0.25, "p_model": 0.28,
                     "p_market": 0.25, "odds": 2.80, "ev_per_unit": -0.30,
                     "kelly_fraction": 0.0, "stake": 0.0,
                     "expected_return": 0.0},
                ],
            }],
            "total_stake": 100.0,
            "total_expected_return": 21.0,
            "blend_alpha": 0.4,
            "lambda_total_prior": 2.6,
        }
        record_wc_handicap_session(db, request={}, response=response)

        # 2. Record the WC prediction row (needed for settle_wc_prediction
        #    to find the fixture)
        _record_wc_pred_row(db)

        # 3. Settle the WC fixture — USA wins 3-1 (covers -1 line)
        settle_wc_prediction(db, fixture_id=9001, home_goals=3, away_goals=1)

        # 4. Run the regular auto-settle pipeline — it should pick up
        #    the recommendation via the new match_outcomes row
        with open_db(db) as conn:
            counts = settle_unsettled(conn)
        assert counts["checked"] == 1
        assert counts["settled"] == 1
        assert counts["still_unknown"] == 0

        # 5. Verify the settlements row was written
        with sqlite3.connect(db) as conn:
            srow = conn.execute(
                "SELECT hit, stake, actual_payout, profit_loss "
                "FROM settlements"
            ).fetchone()
        assert srow is not None
        hit, stake, payout, pnl = srow
        # USA covered -1 (won by 2) → outcome H hits → profit
        assert hit == 1
        assert stake > 0
        assert payout > stake   # winning bet
        assert pnl > 0

    def test_loss_settles_correctly(self, tmp_path):
        """USA bet at HC -1 loses if USA wins by exactly 1 (push for HC=-1
        in our settlement = away wins on the offset since 3-2-1=0...
        actually under integer handicap settlement it's a draw on the
        line → outcome D, not H → H bet loses)."""
        db = _prep_db(tmp_path)
        response = {
            "generated_at_utc": "2026-05-26T12:00:00+00:00",
            "bankroll": 10000.0, "n_fixtures": 1, "n_recommendations": 1,
            "matches": [{
                "fixture_id": 9002, "home_team": "USA", "away_team": "Mexico",
                "kickoff_utc": "2026-06-15T19:00:00+00:00",
                "handicap_home": -1,
                "p_1x2_blended": [0.55, 0.25, 0.20],
                "inferred_lambda_home": 1.50, "inferred_lambda_away": 1.10,
                "outcomes": [
                    {"outcome": "H", "p_final": 0.55, "p_model": 0.50,
                     "p_market": 0.45, "odds": 2.20, "ev_per_unit": 0.21,
                     "kelly_fraction": 0.18, "stake": 100.0,
                     "expected_return": 21.0},
                    {"outcome": "D", "p_final": 0.20, "p_model": 0.22,
                     "p_market": 0.30, "odds": 3.50, "ev_per_unit": -0.30,
                     "kelly_fraction": 0.0, "stake": 0.0,
                     "expected_return": 0.0},
                    {"outcome": "A", "p_final": 0.25, "p_model": 0.28,
                     "p_market": 0.25, "odds": 2.80, "ev_per_unit": -0.30,
                     "kelly_fraction": 0.0, "stake": 0.0,
                     "expected_return": 0.0},
                ],
            }],
            "total_stake": 100.0, "total_expected_return": 21.0,
            "blend_alpha": 0.4, "lambda_total_prior": 2.6,
        }
        record_wc_handicap_session(db, request={}, response=response)
        _record_wc_pred_row(db, fixture_id=9002)
        # USA wins 1-0 → at HC=-1, (1-1) vs 0 → D on handicap → H loses
        settle_wc_prediction(db, fixture_id=9002, home_goals=1, away_goals=0)
        with open_db(db) as conn:
            counts = settle_unsettled(conn)
        assert counts["settled"] == 1
        with sqlite3.connect(db) as conn:
            hit, pnl = conn.execute(
                "SELECT hit, profit_loss FROM settlements"
            ).fetchone()
        # 1-0 with HC -1 → home_goals + (-1) = 0 vs away_goals = 0 → D
        # We bet H → didn't hit → loss
        assert hit == 0
        assert pnl < 0


class TestExtractFinishedRows90Min:
    """V14 — wc-settle scores on the 90' result, NOT the ET-inclusive final.
    A knockout 1-1 at 90' decided 2-1 in extra time must settle as a 90' DRAW
    (mirrors prediction_log._ft_outcome and the 竞彩 90-minute convention)."""

    def test_uses_fulltime_not_extra_time(self):
        from nutmeg.v4.cli.wc_settle import _extract_finished_rows
        fx = [{
            "fixture": {"id": 7001, "status": {"short": "AET"},
                        "date": "2026-07-10T19:00:00+00:00"},
            "teams": {"home": {"name": "Spain"}, "away": {"name": "Brazil"}},
            "score": {"fulltime": {"home": 1, "away": 1}},   # 90' = draw
            "goals": {"home": 2, "away": 1},                 # decided in ET
        }]
        rows = _extract_finished_rows(fx)
        assert len(rows) == 1
        assert (rows[0]["home_goals"], rows[0]["away_goals"]) == (1, 1)  # 90', not 2-1

    def test_falls_back_to_goals_when_fulltime_absent(self):
        from nutmeg.v4.cli.wc_settle import _extract_finished_rows
        fx = [{
            "fixture": {"id": 7002, "status": {"short": "FT"},
                        "date": "2026-06-15T19:00:00+00:00"},
            "teams": {"home": {"name": "USA"}, "away": {"name": "Mexico"}},
            "goals": {"home": 2, "away": 0},   # no score.fulltime split present
        }]
        rows = _extract_finished_rows(fx)
        assert (rows[0]["home_goals"], rows[0]["away_goals"]) == (2, 0)
