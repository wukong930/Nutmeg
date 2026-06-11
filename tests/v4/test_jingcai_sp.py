"""竞彩 SP staleness table — capture (upsert-latest), no-op guards, settlement."""
from __future__ import annotations

import datetime as dt

from nutmeg.v4.observation.jingcai_sp import (
    fetch_jingcai_sp,
    record_jingcai_sp,
    settle_jingcai_sp,
)


def _db(tmp_path):
    return str(tmp_path / "obs.db")


def test_record_and_fetch(tmp_path):
    db = _db(tmp_path)
    ok = record_jingcai_sp(
        db, match_date="2026-06-20", home_team="Mexico", away_team="South Africa",
        jc_home=1.70, jc_draw=3.40, jc_away=4.50,
        psc_home=1.43, psc_draw=4.43, psc_away=8.70, ou_line=2.25,
        league="WC", source="market_mode")
    assert ok is True
    rows = fetch_jingcai_sp(db)
    assert len(rows) == 1
    assert rows[0]["jc_home"] == 1.70 and rows[0]["psc_home"] == 1.43
    assert rows[0]["settled_at"] is None


def test_upsert_latest_dedup(tmp_path):
    """Re-pricing the same match overwrites — ONE canonical (latest) row."""
    db = _db(tmp_path)
    for jc in (1.80, 1.75, 1.68):  # user re-fills 3× before kickoff
        record_jingcai_sp(
            db, match_date="2026-06-20", home_team="Mexico", away_team="South Africa",
            jc_home=jc, jc_draw=3.4, jc_away=4.5)
    rows = fetch_jingcai_sp(db)
    assert len(rows) == 1              # not 3
    assert rows[0]["jc_home"] == 1.68  # the LAST (canonical) value


def test_missing_jingcai_line_is_noop(tmp_path):
    db = _db(tmp_path)
    assert record_jingcai_sp(
        db, match_date="2026-06-20", home_team="A", away_team="B",
        jc_home=None, jc_draw=None, jc_away=None) is False
    assert fetch_jingcai_sp(db) == []


def test_different_markets_coexist(tmp_path):
    db = _db(tmp_path)
    record_jingcai_sp(db, match_date="2026-06-20", home_team="A", away_team="B",
                      jc_home=1.5, jc_draw=3.5, jc_away=6.0, market="had")
    record_jingcai_sp(db, match_date="2026-06-20", home_team="A", away_team="B",
                      jc_home=2.0, jc_draw=3.2, jc_away=3.3, market="hhad")
    assert len(fetch_jingcai_sp(db)) == 2  # 1X2 and handicap are separate rows


def _fx(home, away, hg, ag):
    return {
        "fixture": {"status": {"short": "FT"}},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "score": {"fulltime": {"home": hg, "away": ag}},
        "goals": {"home": hg, "away": ag},
    }


def test_settle_fills_result(tmp_path):
    db = _db(tmp_path)
    record_jingcai_sp(db, match_date="2026-06-20", home_team="Mexico",
                      away_team="South Africa", jc_home=1.7, jc_draw=3.4, jc_away=4.5)

    def fetch(d: dt.date):
        assert d == dt.date(2026, 6, 20)
        return [_fx("Mexico", "South Africa", 2, 1)]

    n = settle_jingcai_sp(db, fetch_fixtures=fetch, today=dt.date(2026, 6, 21))
    assert n == 1
    r = fetch_jingcai_sp(db, settled=True)[0]
    assert (r["home_goals"], r["away_goals"], r["ft_outcome"]) == (2, 1, 0)  # home win


def test_settle_skips_future(tmp_path):
    db = _db(tmp_path)
    record_jingcai_sp(db, match_date="2026-06-25", home_team="Mexico",
                      away_team="South Africa", jc_home=1.7, jc_draw=3.4, jc_away=4.5)
    called = []
    n = settle_jingcai_sp(db, fetch_fixtures=lambda d: called.append(d) or [],
                          today=dt.date(2026, 6, 21))  # match is in the future
    assert n == 0 and called == []  # never even fetched


def test_settle_preserved_on_recapture(tmp_path):
    db = _db(tmp_path)
    record_jingcai_sp(db, match_date="2026-06-20", home_team="Mexico",
                      away_team="South Africa", jc_home=1.7, jc_draw=3.4, jc_away=4.5)
    settle_jingcai_sp(db, fetch_fixtures=lambda d: [_fx("Mexico", "South Africa", 0, 0)],
                      today=dt.date(2026, 6, 21))
    # re-price AFTER settlement → line updates, result must NOT be clobbered
    record_jingcai_sp(db, match_date="2026-06-20", home_team="Mexico",
                      away_team="South Africa", jc_home=1.9, jc_draw=3.3, jc_away=4.0)
    r = fetch_jingcai_sp(db)[0]
    assert r["jc_home"] == 1.9                       # line refreshed
    assert r["ft_outcome"] == 1 and r["settled_at"]  # draw result preserved


def test_handicap_home_stored(tmp_path):
    db = _db(tmp_path)
    record_jingcai_sp(db, match_date="2026-06-20", home_team="A", away_team="B",
                      jc_home=2.5, jc_draw=3.2, jc_away=2.6,
                      market="hhad", handicap_home=-1)
    r = fetch_jingcai_sp(db)[0]
    assert r["market"] == "hhad" and r["handicap_home"] == -1


def test_migration_adds_handicap_home(tmp_path):
    """A jingcai_sp table created before 让球 support lacks handicap_home; ensure()
    must ALTER it in so an hhad capture doesn't fail."""
    import sqlite3
    db = _db(tmp_path)
    with sqlite3.connect(db) as c:   # simulate the OLD (pre-hhad) schema
        c.execute(
            "CREATE TABLE jingcai_sp (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "captured_at TEXT NOT NULL, source TEXT NOT NULL, fixture_id INTEGER, "
            "league TEXT, match_date TEXT NOT NULL, home_team TEXT NOT NULL, "
            "away_team TEXT NOT NULL, kickoff_utc TEXT, market TEXT NOT NULL DEFAULT 'had', "
            "jc_home REAL, jc_draw REAL, jc_away REAL, psc_home REAL, psc_draw REAL, "
            "psc_away REAL, ou_line REAL, home_goals INTEGER, away_goals INTEGER, "
            "ft_outcome INTEGER, settled_at TEXT, "
            "UNIQUE(match_date, home_team, away_team, market))")
    ok = record_jingcai_sp(db, match_date="2026-06-20", home_team="A", away_team="B",
                           jc_home=2.5, jc_draw=3.2, jc_away=2.6,
                           market="hhad", handicap_home=-2)
    assert ok is True
    assert fetch_jingcai_sp(db)[0]["handicap_home"] == -2


def test_protect_manual_not_clobbered(tmp_path):
    """A sporttery harvest must NOT overwrite a line the user hand-priced."""
    db = _db(tmp_path)
    record_jingcai_sp(db, match_date="2026-06-20", home_team="Mexico",
                      away_team="South Africa", jc_home=1.70, jc_draw=3.4, jc_away=4.5,
                      source="market_mode")
    ok = record_jingcai_sp(db, match_date="2026-06-20", home_team="Mexico",
                           away_team="South Africa", jc_home=1.99, jc_draw=3.3,
                           jc_away=4.0, source="sporttery", protect_manual=True)
    assert ok is False                       # skipped
    r = fetch_jingcai_sp(db)[0]
    assert r["jc_home"] == 1.70 and r["source"] == "market_mode"   # manual preserved


def test_protect_manual_inserts_when_no_manual(tmp_path):
    db = _db(tmp_path)
    ok = record_jingcai_sp(db, match_date="2026-06-20", home_team="A", away_team="B",
                           jc_home=2.0, jc_draw=3.0, jc_away=3.5,
                           source="sporttery", protect_manual=True)
    assert ok is True
    assert fetch_jingcai_sp(db)[0]["source"] == "sporttery"
