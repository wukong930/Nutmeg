"""让球三元组组装器 — 〈竞彩让球 SP × Pinnacle 收盘重构 P × 让球结算〉.

The 让球 half of the forward-only proprietary triple. Verifies it joins the
captured tables, reconstructs the 3-way 让球 P exactly like serving, settles the
handicap correctly, and computes EV/ROI/Brier honestly — skipping (not faking)
matches that can't be priced.
"""
from __future__ import annotations

import sqlite3

import pytest

from nutmeg.v4.observation.handicap_triples import (
    HandicapTriple,
    assemble_handicap_triples,
    summarize,
)

_JC_COLS = (
    "market, handicap_home, match_date, league, home_team, away_team, "
    "jc_home, jc_draw, jc_away, home_goals, away_goals"
)
_SNAP_COLS = (
    "match_date, home_team, away_team, captured_at, "
    "psc_home, psc_draw, psc_away, psc_over, psc_under, ou_line"
)


def _make_db(tmp_path, jc_rows, snap_rows):
    db = tmp_path / "obs.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE jingcai_sp (market TEXT, handicap_home INTEGER, "
        "match_date TEXT, league TEXT, home_team TEXT, away_team TEXT, "
        "jc_home REAL, jc_draw REAL, jc_away REAL, home_goals INTEGER, "
        "away_goals INTEGER)"
    )
    con.execute(
        "CREATE TABLE odds_snapshots (match_date TEXT, home_team TEXT, "
        "away_team TEXT, captured_at TEXT, psc_home REAL, psc_draw REAL, "
        "psc_away REAL, psc_over REAL, psc_under REAL, ou_line REAL)"
    )
    con.executemany(
        f"INSERT INTO jingcai_sp ({_JC_COLS}) VALUES "
        f"({','.join('?' * 11)})", jc_rows
    )
    con.executemany(
        f"INSERT INTO odds_snapshots ({_SNAP_COLS}) VALUES "
        f"({','.join('?' * 10)})", snap_rows
    )
    con.commit()
    con.close()
    return str(db)


def _jc(home_goals=2, away_goals=0, hcap=-1, jc=(2.0, 3.25, 3.11),
        home="Mexico", away="South Africa", date="2026-06-11"):
    return ("hhad", hcap, date, "WC", home, away, jc[0], jc[1], jc[2],
            home_goals, away_goals)


def _snap(home="Mexico", away="South Africa", date="2026-06-11",
          pin=(1.43, 4.55, 8.51), ou=(2.18, 1.72, 2.5), cap="2026-06-11T18:00:00"):
    return (date, home, away, cap, pin[0], pin[1], pin[2], ou[0], ou[1], ou[2])


# ----- assemble: join + reconstruct + settle ------------------------------

def test_assembles_complete_triple(tmp_path):
    db = _make_db(tmp_path, [_jc()], [_snap()])
    triples = assemble_handicap_triples(db)
    assert len(triples) == 1
    t = triples[0]
    # 3-way reconstructed 让球 P sums to ~1 (handicap board is a proper dist).
    assert abs(sum(t.p_pin) - 1.0) < 0.02
    # EV is exactly P_pinnacle × 竞彩SP − 1, per outcome.
    for k in range(3):
        assert t.ev[k] == pytest.approx(t.p_pin[k] * t.jc[k] - 1.0, abs=1e-9)


def test_settlement_applies_handicap_not_raw_1x2(tmp_path):
    # Home wins 1-0 on a −1 line → handicapped diff = 0 → 让平 (D), NOT 让胜.
    db = _make_db(tmp_path, [_jc(home_goals=1, away_goals=0, hcap=-1)], [_snap()])
    t = assemble_handicap_triples(db)[0]
    assert t.result == "D"


@pytest.mark.parametrize("hg,ag,hcap,exp", [
    (2, 0, -1, "H"),   # 2-0, -1 → (2-1)-0=+1 → 让胜
    (1, 0, -1, "D"),   # 1-0, -1 → 0 → 让平
    (0, 0, -1, "A"),   # 0-0, -1 → -1 → 让负
    (0, 1, +1, "D"),   # 0-1, +1 → 0 → 让平 (受让)
    (0, 2, +1, "A"),   # 0-2, +1 → -1 → 让负
])
def test_handicap_settlement_table(tmp_path, hg, ag, hcap, exp):
    db = _make_db(tmp_path, [_jc(home_goals=hg, away_goals=ag, hcap=hcap)], [_snap()])
    assert assemble_handicap_triples(db)[0].result == exp


def test_skips_match_without_pinnacle_close(tmp_path):
    # 竞彩让球 SP present, but no odds_snapshots row → not priceable → skipped.
    db = _make_db(tmp_path, [_jc()], [])
    assert assemble_handicap_triples(db) == []


def test_skips_unsettled_row(tmp_path):
    # home_goals NULL (not yet played) → excluded by the SQL filter.
    row = list(_jc())
    row[9] = None  # home_goals
    db = _make_db(tmp_path, [tuple(row)], [_snap()])
    assert assemble_handicap_triples(db) == []


def test_only_hhad_rows_used(tmp_path):
    had = list(_jc())
    had[0] = "had"  # 1X2 row, not 让球
    db = _make_db(tmp_path, [tuple(had)], [_snap()])
    assert assemble_handicap_triples(db) == []


def test_picks_freshest_snapshot_as_close(tmp_path):
    stale = _snap(pin=(1.20, 6.0, 12.0), cap="2026-06-08T00:00:00")
    close = _snap(pin=(1.43, 4.55, 8.51), cap="2026-06-11T18:00:00")
    db = _make_db(tmp_path, [_jc()], [stale, close])
    t = assemble_handicap_triples(db)[0]
    assert t.pinnacle_captured_at == "2026-06-11T18:00:00"


# ----- summarize: betting-truth aggregation -------------------------------

def _tri(ev, jc, p_pin, result):
    return HandicapTriple(
        match_date="2026-06-11", league="WC", home_team="A", away_team="B",
        handicap_home=-1, jc=jc, p_pin=p_pin, home_goals=1, away_goals=0,
        result=result, ev=ev, pinnacle_captured_at="t",
    )


def test_summarize_positive_ev_roi_and_brier():
    triples = [
        # best=让胜(H), +EV, WON → flat pnl +(2.0-1)=+1.0
        _tri(ev=(0.10, -0.5, -0.3), jc=(2.0, 3.0, 3.0), p_pin=(0.55, 0.25, 0.20), result="H"),
        # best=让胜(H), +EV, LOST(actual 让负) → flat pnl −1.0
        _tri(ev=(0.20, -0.4, -0.2), jc=(2.0, 3.0, 3.0), p_pin=(0.60, 0.25, 0.15), result="A"),
        # best=让胜(H), below +5% gate → not a pick
        _tri(ev=(0.02, -0.5, -0.4), jc=(1.9, 3.0, 3.0), p_pin=(0.53, 0.25, 0.22), result="H"),
    ]
    s = summarize(triples, min_ev=0.05)
    assert s["n"] == 3
    assert s["n_positive"] == 2          # only the two ≥ +5%
    assert s["n_positive_won"] == 1
    assert s["positive_hit_rate"] == pytest.approx(0.5)
    assert s["avg_positive_ev"] == pytest.approx(0.15)
    assert s["realized_flat_roi"] == pytest.approx(0.0)   # (+1 −1)/2
    assert s["brier_reconstructed_p"] == pytest.approx(
        ((0.55 - 1) ** 2 + 0.25 ** 2 + 0.20 ** 2
         + 0.60 ** 2 + 0.25 ** 2 + (0.15 - 1) ** 2
         + (0.53 - 1) ** 2 + 0.25 ** 2 + 0.22 ** 2) / 3, abs=1e-9
    )


def test_summarize_empty_is_honest():
    s = summarize([], min_ev=0.05)
    assert s["n"] == 0 and s["n_positive"] == 0
    assert s["realized_flat_roi"] is None and s["brier_reconstructed_p"] is None
