"""CLV ledger — settlement-independent soft-water measurement."""
from __future__ import annotations

import sqlite3

from nutmeg.v4.cli.clv_ledger import _hhad_cover_p, _tier, compute_ledger
from nutmeg.v4.model.devig import devig_1x2
from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp


def _seed_close(db, date, h, a, psc):
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE IF NOT EXISTS odds_snapshots (id INTEGER PRIMARY KEY, "
                  "captured_at TEXT, fixture_id INTEGER, match_date TEXT, home_team TEXT, "
                  "away_team TEXT, psc_home REAL, psc_draw REAL, psc_away REAL, "
                  "psc_over REAL, psc_under REAL, ou_line REAL)")
        c.execute("INSERT INTO odds_snapshots (captured_at, match_date, home_team, "
                  "away_team, psc_home, psc_draw, psc_away, psc_over, psc_under, ou_line) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                  ("2026-01-01T00:00:00+00:00", date, h, a, psc[0], psc[1], psc[2],
                   1.9, 1.9, 2.5))


def test_tier_boundaries():
    assert _tier(0.10).startswith("cold")
    assert _tier(0.17).startswith("高估区")
    assert _tier(0.22).startswith("边缘")
    assert _tier(0.45).startswith("甜区")
    assert _tier(0.72).startswith("边缘")
    assert _tier(0.90).startswith("chalk")


def test_hhad_cover_p_partitions():
    # close = (psc_home, psc_draw, psc_away, psc_over, psc_under, ou_line)
    p = _hhad_cover_p((1.8, 3.6, 4.8, 1.9, 1.9, 2.5), -1)
    assert p is not None and abs(sum(p) - 1.0) < 0.05  # 让胜/让平/让负 exhaust the space


def test_settlement_independent_and_selected(tmp_path):
    """A row that NEVER settles still produces 3 legs; the capture-+EV leg becomes
    a selected observation whose CLV is measured vs the CLOSE (no look-ahead)."""
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(db, match_date="2026-06-20", home_team="A", away_team="B",
                      jc_home=2.0, jc_draw=3.5, jc_away=4.5,
                      psc_home=1.8, psc_draw=3.6, psc_away=4.8, market="had")
    _seed_close(db, "2026-06-20", "A", "B", (1.85, 3.5, 4.6))
    rep = compute_ledger(db, min_ev=0.05)
    assert len(rep["legs"]) == 3 and rep["no_close"] == 0 and rep["n_matches"] == 1
    # capture home EV = devig(1.8,3.6,4.8)[0]*2.0 − 1 ≈ +8.3% (WPO) ≥ 5% → selected, 主胜
    assert len(rep["selected"]) == 1
    s = rep["selected"][0]
    assert s["pos"] == "主胜"
    p_close_home = devig_1x2(1.85, 3.5, 4.6)[0]   # WPO, production de-vig (single source)
    assert abs(s["clv"] - (p_close_home * 2.0 - 1)) < 1e-6  # CLV vs CLOSE, not capture


def test_no_close_skipped(tmp_path):
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(db, match_date="2026-06-21", home_team="C", away_team="D",
                      jc_home=2.0, jc_draw=3.5, jc_away=4.5, market="had")
    rep = compute_ledger(db)
    assert rep["legs"] == [] and rep["no_close"] == 1


def test_below_threshold_not_selected(tmp_path):
    db = str(tmp_path / "obs.db")  # 竞彩 == Pinnacle → every leg is just −vig, none +EV
    record_jingcai_sp(db, match_date="2026-06-22", home_team="E", away_team="F",
                      jc_home=1.9, jc_draw=3.3, jc_away=4.0,
                      psc_home=1.9, psc_draw=3.3, psc_away=4.0, market="had")
    _seed_close(db, "2026-06-22", "E", "F", (1.9, 3.3, 4.0))
    rep = compute_ledger(db, min_ev=0.05)
    assert len(rep["legs"]) == 3 and rep["selected"] == []


def test_hhad_selected_reverse_fits_capture_ou(tmp_path):
    """让球选中腿: capture-time cover-P is reverse-fit from the stored 1X2 + O/U
    (psc_over/under), so an hhad +EV pick enters the validation counter."""
    db = str(tmp_path / "obs.db")
    record_jingcai_sp(db, match_date="2026-06-23", home_team="G", away_team="H",
                      jc_home=5.0, jc_draw=5.0, jc_away=5.0,   # absurdly soft → some leg +EV
                      psc_home=1.5, psc_draw=4.0, psc_away=7.0,
                      psc_over=1.9, psc_under=1.9, ou_line=2.5,
                      market="hhad", handicap_home=-1)
    _seed_close(db, "2026-06-23", "G", "H", (1.55, 3.9, 6.5))
    rep = compute_ledger(db, min_ev=0.05)
    assert len(rep["legs"]) == 3
    assert len(rep["selected"]) == 1 and rep["selected"][0]["market"] == "hhad"
