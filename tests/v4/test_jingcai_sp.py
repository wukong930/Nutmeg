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
    for jc in (1.70, 1.71, 1.68):  # user re-fills 3× before kickoff (全部在 booksum 带内)
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
                      away_team="South Africa", jc_home=1.8, jc_draw=3.3, jc_away=4.1)
    r = fetch_jingcai_sp(db)[0]
    assert r["jc_home"] == 1.8                       # line refreshed
    assert r["ft_outcome"] == 1 and r["settled_at"]  # draw result preserved


def test_handicap_home_stored(tmp_path):
    db = _db(tmp_path)
    record_jingcai_sp(db, match_date="2026-06-20", home_team="A", away_team="B",
                      jc_home=2.45, jc_draw=3.15, jc_away=2.55,
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
                           jc_home=2.45, jc_draw=3.15, jc_away=2.55,
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
                           away_team="South Africa", jc_home=1.90, jc_draw=3.2,
                           jc_away=3.6, source="sporttery", protect_manual=True)
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


def test_settle_skips_ambiguous_duplicate_pairing(tmp_path):
    """体检 D2 — two DISTINCT fixtures with the same normalized team-pair on one
    date → ambiguous; neither is settled (bare last-write-wins would attach the
    wrong 90' score). Realized only for obscure same-name lower-league clubs."""
    db = _db(tmp_path)
    record_jingcai_sp(db, match_date="2026-06-20", home_team="A", away_team="B",
                      jc_home=1.7, jc_draw=3.4, jc_away=4.5)

    def fetch(d: dt.date):
        return [
            {**_fx("A", "B", 2, 1), "fixture": {"id": 111, "status": {"short": "FT"}}},
            {**_fx("A", "B", 0, 0), "fixture": {"id": 222, "status": {"short": "FT"}}},
        ]

    n = settle_jingcai_sp(db, fetch_fixtures=fetch, today=dt.date(2026, 6, 21))
    assert n == 0   # ambiguous → not settled


def test_settle_unique_pairing_still_settles(tmp_path):
    # control: a single fixture (the normal case) still settles
    db = _db(tmp_path)
    record_jingcai_sp(db, match_date="2026-06-20", home_team="A", away_team="B",
                      jc_home=1.7, jc_draw=3.4, jc_away=4.5)
    n = settle_jingcai_sp(
        db, fetch_fixtures=lambda d: [{**_fx("A", "B", 2, 1),
                                       "fixture": {"id": 111, "status": {"short": "FT"}}}],
        today=dt.date(2026, 6, 21))
    assert n == 1


# ── 捕获端 sanity 闸(2026-07-19 RCA:SJK vs KuPS hhad a 腿 5.25 手滑 7.25,
#    market_mode 静默捕获写成「终盘」后被 protect_manual 永生化)──────────────


def test_booksum_gate_rejects_single_leg_garbage(tmp_path):
    """SJK 案原样:官方终盘 1.40/4.45/5.25 的 a 腿写成 7.25 → booksum 1.077 拒写。"""
    db = _db(tmp_path)
    ok = record_jingcai_sp(db, match_date="2026-07-18", home_team="SJK", away_team="KuPS",
                           jc_home=1.40, jc_draw=4.45, jc_away=7.25,
                           market="hhad", handicap_home=1, source="market_mode")
    assert ok is False
    assert fetch_jingcai_sp(db) == []


def test_booksum_gate_accepts_real_jingcai_shapes(tmp_path):
    """官方真值全在带内:SJK 官方终盘 + 深让极端盘(1.15/6.45/9.5,booksum 1.130)。"""
    db = _db(tmp_path)
    assert record_jingcai_sp(db, match_date="2026-07-18", home_team="SJK",
                             away_team="KuPS", jc_home=1.40, jc_draw=4.45,
                             jc_away=5.25, market="hhad", handicap_home=1) is True
    assert record_jingcai_sp(db, match_date="2026-07-18", home_team="Viking",
                             away_team="Sandefjord", jc_home=1.15, jc_draw=6.45,
                             jc_away=9.50, market="had") is True


def test_booksum_gate_guards_official_source_too(tmp_path):
    """上游 calculator 若吐出脏三元组,sporttery 源同样拒写,旧行保留。"""
    db = _db(tmp_path)
    record_jingcai_sp(db, match_date="2026-07-18", home_team="SJK", away_team="KuPS",
                      jc_home=1.42, jc_draw=4.36, jc_away=5.10, market="hhad",
                      handicap_home=1, source="sporttery")
    ok = record_jingcai_sp(db, match_date="2026-07-18", home_team="SJK", away_team="KuPS",
                           jc_home=1.42, jc_draw=4.36, jc_away=51.0, market="hhad",
                           handicap_home=1, source="sporttery")
    assert ok is False
    assert fetch_jingcai_sp(db)[0]["jc_away"] == 5.10   # 旧行未被脏值覆盖


def test_post_kickoff_gate_blocks_market_mode(tmp_path):
    """开球 15min 后的 market_mode 手填拒写(kickoff 从已存行回读)— 官方行不动。"""
    db = _db(tmp_path)
    record_jingcai_sp(db, match_date="2026-07-18", home_team="SJK", away_team="KuPS",
                      jc_home=1.40, jc_draw=4.45, jc_away=5.25, market="hhad",
                      handicap_home=1, source="sporttery",
                      kickoff_utc="2026-07-18T14:00:00+00:00")   # sporttery 不受闸
    ok = record_jingcai_sp(db, match_date="2026-07-18", home_team="SJK", away_team="KuPS",
                           jc_home=1.40, jc_draw=4.45, jc_away=5.20, market="hhad",
                           handicap_home=1, source="market_mode")   # booksum 合法,靠闸 2 拒
    assert ok is False
    r = fetch_jingcai_sp(db)[0]
    assert r["jc_away"] == 5.25 and r["source"] == "sporttery"


def test_post_kickoff_gate_open_before_kickoff_and_unknown(tmp_path):
    """开球前正常写;kickoff 两处都未知(手填新场)fail-open 仍可写。"""
    db = _db(tmp_path)
    future = (dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)).isoformat(timespec="seconds")
    assert record_jingcai_sp(db, match_date="2099-01-01", home_team="A", away_team="B",
                             jc_home=1.70, jc_draw=3.40, jc_away=4.50,
                             kickoff_utc=future, source="market_mode") is True
    assert record_jingcai_sp(db, match_date="2099-01-02", home_team="C", away_team="D",
                             jc_home=1.70, jc_draw=3.40, jc_away=4.50,
                             source="market_mode") is True
