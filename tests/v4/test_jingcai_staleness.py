"""竞彩 staleness analysis — EV(Pinnacle-close × 竞彩SP) candidate + realized ROI."""
from __future__ import annotations

import datetime as dt

from nutmeg.v4.cli.jingcai_staleness import _devig3, _roi, analyze
from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp, settle_jingcai_sp
from nutmeg.v4.observation.odds_snapshots import record_row_snapshot


def _fx(home, away, hg, ag):
    return {
        "fixture": {"status": {"short": "FT"}},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "score": {"fulltime": {"home": hg, "away": ag}},
        "goals": {"home": hg, "away": ag},
    }


def _snapshot_pinn_close(db, *, fixture_id, h, d, a):
    record_row_snapshot(db, {
        "psc_home": h, "psc_draw": d, "psc_away": a,
        "date": "2026-06-20", "league": "WC",
        "home_team": "Mexico", "away_team": "South Africa",
        "ou_line": 2.5, "psc_over25": 1.9, "psc_under25": 1.9,
        "odds_update": "2026-06-20T18:00:00Z", "kickoff_utc": None,
    }, fixture_id=fixture_id, source="test")


def test_devig3():
    p = _devig3(2.0, 4.0, 4.0)
    assert p is not None and abs(sum(p) - 1.0) < 1e-9
    assert p[0] > p[1]  # shorter price → higher prob


def _seed(db, jc_home):
    record_jingcai_sp(
        db, match_date="2026-06-20", home_team="Mexico", away_team="South Africa",
        jc_home=jc_home, jc_draw=3.3, jc_away=3.4,
        psc_home=1.90, psc_draw=3.6, psc_away=4.4,  # Pinnacle AT CAPTURE
        fixture_id=12345, league="WC")
    settle_jingcai_sp(db, fetch_fixtures=lambda d: [_fx("Mexico", "South Africa", 2, 0)],
                      today=dt.date(2026, 6, 21))


def test_candidate_detected_and_realized(tmp_path):
    db = str(tmp_path / "obs.db")
    # 竞彩 prices home @2.10; Pinnacle CLOSE drifts to P_home≈0.585 (1.70/4.0/6.0)
    _seed(db, jc_home=2.10)
    _snapshot_pinn_close(db, fixture_id=12345, h=1.70, d=4.0, a=6.0)
    rep = analyze(db)
    assert rep["n_settled"] == 1 and rep["no_close"] == 0
    assert len(rep["candidates"]) == 1
    c = rep["candidates"][0]
    assert c["pick"] == "主胜" and c["won"] is True   # home won 2-0
    assert c["ev"] > 0.05 and abs(c["profit"] - 1.10) < 1e-9
    n, wr, roi = _roi(rep["candidates"])
    assert (n, wr) == (1, 1.0) and abs(roi - 1.10) < 1e-9


def test_no_candidate_when_no_edge(tmp_path):
    db = str(tmp_path / "obs.db")
    _seed(db, jc_home=1.50)              # too short: 0.585×1.50−1 = −0.12
    _snapshot_pinn_close(db, fixture_id=12345, h=1.70, d=4.0, a=6.0)
    rep = analyze(db)
    assert rep["n_settled"] == 1 and rep["candidates"] == []


def test_no_pinnacle_close_is_skipped(tmp_path):
    db = str(tmp_path / "obs.db")
    _seed(db, jc_home=2.10)              # settled, but NO odds_snapshot recorded
    rep = analyze(db)
    assert rep["no_close"] == 1 and rep["candidates"] == []


def test_hhad_reverse_fit_candidate_and_realized(tmp_path):
    """让球: reverse-fit Pinnacle's cover P at the 竞彩 line from its CLOSE 1X2+O/U,
    +EV candidate, realized via (margin + handicap)."""
    from nutmeg.v4.model.market_handicap import devig_over, implied_handicap_lines
    db = str(tmp_path / "obs.db")
    _snapshot_pinn_close(db, fixture_id=12345, h=1.50, d=4.0, a=6.0)   # strong home + O/U 1.9/1.9
    # the 让胜 cover P at line −1, computed the SAME way the analysis does
    fair = _devig3(1.50, 4.0, 6.0)
    p_letwin = implied_handicap_lines(
        fair[0], fair[1], fair[2], devig_over(1.9, 1.9), ou_line=2.5, lines=(-1,))[0][1]
    jc_letwin = round(1.12 / p_letwin, 2)            # ⇒ EV ≈ +12% on 让胜
    record_jingcai_sp(
        db, match_date="2026-06-20", home_team="Mexico", away_team="South Africa",
        jc_home=jc_letwin, jc_draw=2.0, jc_away=2.0,
        market="hhad", handicap_home=-1, fixture_id=12345)
    # home wins 3-0 → margin 3, +(−1) = 2 > 0 → 让胜 covered (idx 0)
    settle_jingcai_sp(db, fetch_fixtures=lambda d: [_fx("Mexico", "South Africa", 3, 0)],
                      today=dt.date(2026, 6, 21))
    rep = analyze(db)
    hh = [c for c in rep["candidates"] if c["market"] == "hhad"]
    assert hh, "no 让球 candidate produced"
    win = next(c for c in hh if c["pick"] == "让胜")
    assert win["ev"] > 0.05 and win["won"] is True
    assert abs(win["profit"] - (jc_letwin - 1.0)) < 1e-9


def test_hhad_realized_loss_when_not_covered(tmp_path):
    """让胜 at −1 but home only wins 1-0 (margin 1, +(−1)=0 → 让平) → 让胜 loses."""
    db = str(tmp_path / "obs.db")
    _snapshot_pinn_close(db, fixture_id=99, h=1.50, d=4.0, a=6.0)
    record_jingcai_sp(
        db, match_date="2026-06-20", home_team="Mexico", away_team="South Africa",
        jc_home=5.0, jc_draw=2.0, jc_away=2.0,   # jc_home huge → 让胜 is +EV
        market="hhad", handicap_home=-1, fixture_id=99)
    settle_jingcai_sp(db, fetch_fixtures=lambda d: [_fx("Mexico", "South Africa", 1, 0)],
                      today=dt.date(2026, 6, 21))
    rep = analyze(db)
    win = next(c for c in rep["candidates"] if c["market"] == "hhad" and c["pick"] == "让胜")
    assert win["won"] is False and win["profit"] == -1.0   # push on the line → 让胜 lost
