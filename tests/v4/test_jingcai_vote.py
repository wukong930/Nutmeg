"""竞彩 散户支持比例 capture — parse + upsert + fail-soft + settle-preserve."""
from __future__ import annotations

import sqlite3

from nutmeg.v4.observation.jingcai_vote import (
    fetch_jingcai_vote,
    parse_vote_row,
    record_jingcai_vote,
)


def _raw(**over):
    base = {
        "matchDate": "2026-07-01 03:00",
        "matchNum": "周二001",
        "leagueAllName": "世界杯",
        "homeTeamAllName": "法国",
        "awayTeamAllName": "火星联队",  # deliberately unmappable
        "hsupportRate": "77%", "dsupportRate": "15%", "asupportRate": "8%",
        "win": "2589843", "draw": "491465", "lose": "273300",
        "hprobability": "77%", "dprobability": "15%", "aprobability": "8%",
        "herror": "0%", "derror": "0%", "aerror": "0%",
        "h": "1.16", "d": "5.80", "a": "10.50",
        "goalLine": "-1",
    }
    base.update(over)
    return base


def test_parse_maps_support_counts_and_keeps_unmapped_row():
    kw = parse_vote_row(_raw(), "had")
    assert kw is not None
    assert kw["match_date"] == "2026-07-01"  # time suffix trimmed
    assert kw["pool_code"] == "HAD"  # uppercased
    assert (kw["h_support"], kw["d_support"], kw["a_support"]) == (77.0, 15.0, 8.0)
    assert (kw["h_count"], kw["d_count"], kw["a_count"]) == (2589843, 491465, 273300)
    assert kw["handicap_home"] == -1
    assert (kw["jc_home"], kw["jc_draw"], kw["jc_away"]) == (1.16, 5.80, 10.50)
    # mappable home → canonical EN; unmappable away → None but the ROW IS KEPT
    assert kw["home_team"] and isinstance(kw["home_team"], str)
    assert kw["away_team"] is None


def test_parse_drops_row_missing_teams_or_support():
    assert parse_vote_row(_raw(homeTeamAllName=""), "had") is None
    assert parse_vote_row(
        _raw(hsupportRate="", dsupportRate="", asupportRate=""), "had") is None


def test_record_upserts_latest_and_preserves_settlement(tmp_path):
    db = tmp_path / "obs.db"
    kw = parse_vote_row(_raw(), "had")
    assert record_jingcai_vote(db, **kw) is True

    rows = fetch_jingcai_vote(db)
    assert len(rows) == 1 and rows[0]["h_support"] == 77.0

    # simulate the settler having filled the result
    with sqlite3.connect(db) as c:
        c.execute("UPDATE jingcai_vote SET home_goals=2, away_goals=0, "
                  "ft_outcome=0, settled_at='2026-07-01T22:00:00'")

    # a later same-day re-capture (crowd shifted 77→81) must UPDATE support but
    # NEVER clobber the settled result
    kw2 = parse_vote_row(_raw(hsupportRate="81%"), "had")
    assert record_jingcai_vote(db, **kw2) is True
    rows = fetch_jingcai_vote(db)
    assert len(rows) == 1  # upsert, not a duplicate
    assert rows[0]["h_support"] == 81.0  # latest crowd
    assert rows[0]["ft_outcome"] == 0 and rows[0]["home_goals"] == 2  # preserved


def test_record_failsoft_on_missing_keys(tmp_path):
    db = tmp_path / "obs.db"
    # missing match_date → no-op False, no raise
    assert record_jingcai_vote(
        db, match_date="", home_zh="A", away_zh="B", pool_code="HAD",
        h_support=50.0) is False
    # no support triple → no-op False
    assert record_jingcai_vote(
        db, match_date="2026-07-01", home_zh="A", away_zh="B",
        pool_code="HAD") is False


def test_backfill_pinnacle_team_date_tolerant_latest_wins(tmp_path):
    from nutmeg.v4.observation.jingcai_vote import backfill_vote_pinnacle
    db = tmp_path / "obs.db"
    # vote row dated 竞彩 Beijing 2026-07-01, mapped to EN
    record_jingcai_vote(
        db, match_date="2026-07-01", home_zh="法国", away_zh="瑞典",
        home_team="France", away_team="Sweden", pool_code="HAD",
        h_support=77.0, d_support=15.0, a_support=8.0,
        jc_home=1.16, jc_draw=5.8, jc_away=10.5)
    # odds_snapshots Pinnacle dated UTC 2026-06-30 (off by 1 day) + two snapshots
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE odds_snapshots (captured_at TEXT, match_date TEXT, "
                     "home_team TEXT, away_team TEXT, psc_home REAL, psc_draw REAL, "
                     "psc_away REAL, ou_line REAL, kickoff_utc TEXT)")
        conn.executemany(
            "INSERT INTO odds_snapshots (captured_at, match_date, home_team, away_team, "
            "psc_home, psc_draw, psc_away, ou_line) VALUES (?,?,?,?,?,?,?,?)",
            [("2026-06-30T10:00:00", "2026-06-30", "France", "Sweden", 1.30, 5.0, 9.0, 2.5),
             ("2026-06-30T18:00:00", "2026-06-30", "France", "Sweden", 1.18, 5.9, 11.0, 2.5)])

    assert backfill_vote_pinnacle(db) == 1  # team-matched across the ±1-day TZ gap
    r = [x for x in fetch_jingcai_vote(db) if x["home_team"] == "France"][0]
    assert r["psc_home"] == 1.18 and r["ou_line"] == 2.5  # LATEST snapshot wins
    # an unmatched team gets nothing, no crash
    record_jingcai_vote(db, match_date="2026-07-01", home_zh="火星", away_zh="月球",
                        home_team="Mars", away_team="Moon", pool_code="HAD", h_support=50.0)
    backfill_vote_pinnacle(db)
    mars = [x for x in fetch_jingcai_vote(db) if x["home_team"] == "Mars"][0]
    assert mars["psc_home"] is None


def test_had_and_hhad_are_separate_rows(tmp_path):
    db = tmp_path / "obs.db"
    record_jingcai_vote(db, **parse_vote_row(_raw(), "had"))
    record_jingcai_vote(db, **parse_vote_row(_raw(hsupportRate="40%"), "hhad"))
    rows = fetch_jingcai_vote(db)
    assert len(rows) == 2  # same match, two pools → two rows
    assert {r["pool_code"] for r in rows} == {"HAD", "HHAD"}


class TestAlarmHeartbeatWatchdog:
    """体检 P0-2 — the vote cron watches the settle chain's data_freshness
    heartbeat (mutual watching; the osascript alarm must not be a single
    point of failure parasitic on the chain it monitors)."""

    def _run(self, tmp_path, monkeypatch, *, hb_age_hours=None):
        import os
        import subprocess as sp

        from nutmeg.v4.cli.data_freshness import HEARTBEAT_FILENAME
        from nutmeg.v4.cli.ingest_jingcai_vote import watch_alarm_heartbeat

        calls = []
        monkeypatch.setattr(sp, "run", lambda *a, **k: calls.append(a) or None)
        db = tmp_path / "obs.db"
        db.write_bytes(b"")
        if hb_age_hours is not None:
            hb = tmp_path / HEARTBEAT_FILENAME
            hb.write_text("2026-06-17T00:00:00+00:00\n")
            import time
            past = time.time() - hb_age_hours * 3600
            os.utime(hb, (past, past))
        alarmed = watch_alarm_heartbeat(db)
        return alarmed, calls

    def test_fresh_heartbeat_is_silent(self, tmp_path, monkeypatch):
        alarmed, calls = self._run(tmp_path, monkeypatch, hb_age_hours=5)
        assert not alarmed and not calls

    def test_stale_heartbeat_alarms(self, tmp_path, monkeypatch):
        alarmed, calls = self._run(tmp_path, monkeypatch, hb_age_hours=30)
        assert alarmed and len(calls) == 1
        assert "osascript" in calls[0][0][0]

    def test_missing_heartbeat_alarms(self, tmp_path, monkeypatch):
        alarmed, calls = self._run(tmp_path, monkeypatch, hb_age_hours=None)
        assert alarmed and len(calls) == 1

    def test_watchdog_failure_never_raises(self, tmp_path, monkeypatch):
        import subprocess as sp

        from nutmeg.v4.cli.ingest_jingcai_vote import watch_alarm_heartbeat

        def boom(*a, **k):
            raise OSError("osascript unavailable")

        monkeypatch.setattr(sp, "run", boom)
        # missing heartbeat → tries to alarm → alarm explodes → still no raise
        assert watch_alarm_heartbeat(tmp_path / "obs.db") is False
