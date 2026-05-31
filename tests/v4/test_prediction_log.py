"""V12 W8j — model-board prediction accuracy log + report.

Guards the non-竞彩 prediction tracker: a forward-only log of the model's 1X2
prediction per upcoming match, settled on the 90' score, scored for hit-rate /
calibration / vs-Pinnacle. Independent of betting ROI.
"""
from __future__ import annotations

import datetime as dt

from nutmeg.v4.cli.predict_report import (
    _brier,
    _devig,
    _hits,
    _log_loss,
    _model_p,
    _pin_p,
    build_report,
)
from nutmeg.v4.observation.prediction_log import (
    ensure_league_predictions_table,
    fetch_league_predictions,
    record_league_prediction,
    settle_league_predictions,
)


def _pred(home, away, ph, pdr, pa, **kw):
    base = dict(
        date="2026-05-31", league="ESP_SEGUNDA_DIVISION",
        home_team=home, away_team=away, kickoff_utc=None, market_mode=False,
        p_home_1x2=ph, p_draw_1x2=pdr, p_away_1x2=pa,
        psc_home=2.0, psc_draw=3.4, psc_away=3.6,
    )
    base.update(kw)
    return base


def _finished(home, away, hg, ag, status="FT", et_goals=None):
    """A finished fixture. et_goals (after extra time) differs from the 90'
    fulltime score for AET/PEN ties — settle must use the 90' score."""
    g = et_goals or {"home": hg, "away": ag}
    return {
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "fixture": {"status": {"short": status}},
        "score": {"fulltime": {"home": hg, "away": ag}},
        "goals": g,
    }


class TestLog:
    def test_record_and_fetch(self, tmp_path):
        db = str(tmp_path / "p.db")
        ensure_league_predictions_table(db)
        record_league_prediction(db, _pred("A", "B", 0.5, 0.3, 0.2))
        rows = fetch_league_predictions(db)
        assert len(rows) == 1
        assert rows[0]["home_team"] == "A"
        assert rows[0]["outcome"] is None
        assert rows[0]["p_home"] == 0.5

    def test_relog_is_idempotent_and_updates_p(self, tmp_path):
        db = str(tmp_path / "p.db")
        record_league_prediction(db, _pred("A", "B", 0.5, 0.3, 0.2))
        record_league_prediction(db, _pred("A", "B", 0.4, 0.35, 0.25))
        rows = fetch_league_predictions(db)
        assert len(rows) == 1          # no duplicate row
        assert rows[0]["p_home"] == 0.4  # latest P wins

    def test_settle_uses_90min_score_not_extra_time(self, tmp_path):
        db = str(tmp_path / "p.db")
        record_league_prediction(db, _pred("A", "B", 0.5, 0.3, 0.2))
        # 90' was 1-1 (draw); decided 2-1 in extra time. Outcome must be DRAW.
        fx = [_finished("A", "B", 1, 1, status="AET", et_goals={"home": 2, "away": 1})]
        n = settle_league_predictions(
            db, fetch_fixtures=lambda d, lg: fx, today=dt.date(2026, 6, 1))
        assert n == 1
        row = fetch_league_predictions(db, settled_only=True)[0]
        assert (row["home_goals"], row["away_goals"], row["outcome"]) == (1, 1, 1)

    def test_resettle_is_idempotent(self, tmp_path):
        db = str(tmp_path / "p.db")
        record_league_prediction(db, _pred("A", "B", 0.5, 0.3, 0.2))
        fx = [_finished("A", "B", 2, 0)]
        n1 = settle_league_predictions(db, fetch_fixtures=lambda d, lg: fx,
                                       today=dt.date(2026, 6, 1))
        n2 = settle_league_predictions(db, fetch_fixtures=lambda d, lg: fx,
                                       today=dt.date(2026, 6, 1))
        assert (n1, n2) == (1, 0)

    def test_relog_does_not_clobber_settled_outcome(self, tmp_path):
        db = str(tmp_path / "p.db")
        record_league_prediction(db, _pred("A", "B", 0.5, 0.3, 0.2))
        settle_league_predictions(db, fetch_fixtures=lambda d, lg: [_finished("A", "B", 2, 0)],
                                  today=dt.date(2026, 6, 1))
        record_league_prediction(db, _pred("A", "B", 0.1, 0.1, 0.8))  # re-log
        row = fetch_league_predictions(db, settled_only=True)[0]
        assert row["outcome"] == 0       # outcome preserved
        assert row["p_home"] == 0.1      # prediction still updated

    def test_unfinished_not_settled(self, tmp_path):
        db = str(tmp_path / "p.db")
        record_league_prediction(db, _pred("A", "B", 0.5, 0.3, 0.2))
        fx = [_finished("A", "B", None, None, status="NS")]
        n = settle_league_predictions(db, fetch_fixtures=lambda d, lg: fx,
                                      today=dt.date(2026, 6, 1))
        assert n == 0

    def test_future_dates_skipped_in_settle(self, tmp_path):
        db = str(tmp_path / "p.db")
        record_league_prediction(db, _pred("A", "B", 0.5, 0.3, 0.2,
                                           date="2026-12-31"))
        called = {"n": 0}

        def fetch(d, lg):
            called["n"] += 1
            return []
        settle_league_predictions(db, fetch_fixtures=fetch, today=dt.date(2026, 6, 1))
        assert called["n"] == 0          # never fetched a future date


class TestReportMetrics:
    def test_devig_sums_to_one(self):
        q = _devig(2.0, 3.4, 3.6)
        assert abs(sum(q) - 1.0) < 1e-9

    def test_log_loss_and_hits(self):
        rows = [
            dict(p_home=0.6, p_draw=0.25, p_away=0.15, outcome=0,
                 psc_home=1.8, psc_draw=3.5, psc_away=4.5),  # model right (H)
            dict(p_home=0.2, p_draw=0.3, p_away=0.5, outcome=1,
                 psc_home=4.0, psc_draw=3.3, psc_away=1.9),  # model wrong (picked A)
        ]
        h, n = _hits(rows, _model_p)
        assert (h, n) == (1, 2)
        ll, n2 = _log_loss(rows, _model_p)
        assert n2 == 2 and ll > 0
        br, _ = _brier(rows, _model_p)
        assert 0 < br < 2

    def test_pinnacle_baseline_skips_rows_without_odds(self):
        row = dict(p_home=0.5, p_draw=0.3, p_away=0.2, outcome=0,
                   psc_home=None, psc_draw=None, psc_away=None)
        assert _pin_p(row) is None

    def test_build_report_empty(self):
        md = build_report([])
        assert "尚无已结算" in md

    def test_build_report_has_all_sections(self):
        rows = [
            dict(match_date="2026-05-31", league="X", home_team="A", away_team="B",
                 p_home=0.6, p_draw=0.25, p_away=0.15, outcome=0,
                 psc_home=1.8, psc_draw=3.5, psc_away=4.5,
                 home_goals=2, away_goals=0),
        ]
        md = build_report(rows)
        assert "命中率" in md
        assert "log-loss" in md
        assert "Pinnacle" in md
        assert "分歧" in md
