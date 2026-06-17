"""Tests for nutmeg-data-freshness — the capture-table leak sentinel."""
from __future__ import annotations

import sqlite3
from datetime import date

from nutmeg.v4.cli.data_freshness import CAPTURE_TABLES, check_freshness, main

TODAY = date(2026, 6, 17)


def _mk_db(tmp_path, rows: dict[str, list[str]], name: str = "obs.db"):
    """Build a temp observation DB with the capture tables + given ts values."""
    db = tmp_path / name
    conn = sqlite3.connect(db)
    for table, col, *_ in CAPTURE_TABLES:
        conn.execute(f"CREATE TABLE {table} ({col} TEXT)")
        for v in rows.get(table, []):
            conn.execute(f"INSERT INTO {table} ({col}) VALUES (?)", (v,))
    conn.commit()
    conn.close()
    return db


def _all_today():
    return {t: ["2026-06-17"] for t, *_ in CAPTURE_TABLES}


def test_all_fresh_exits_zero(tmp_path):
    db = _mk_db(tmp_path, _all_today())
    statuses = check_freshness(db, today=TODAY)
    assert all(not s.stale for s in statuses)
    assert main(["--db", str(db), "--today", "2026-06-17"]) == 0


def test_critical_stale_exits_one(tmp_path):
    rows = _all_today()
    rows["odds_snapshots"] = ["2026-06-05"]  # 12d stale, CRITICAL
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["odds_snapshots"].stale and by["odds_snapshots"].critical
    assert main(["--db", str(db), "--today", "2026-06-17"]) == 1


def test_seasonal_old_does_not_gate(tmp_path):
    # A stale WARN table (league_predictions) must NOT fail the gate.
    rows = _all_today()
    rows["league_predictions"] = ["2026-06-01"]  # stale but non-critical
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["league_predictions"].stale and not by["league_predictions"].critical
    assert main(["--db", str(db), "--today", "2026-06-17"]) == 0


def test_within_cadence_not_stale(tmp_path):
    # odds_snapshots cadence = 2d: a 2-day-old row is still fresh, 3-day is stale.
    rows = _all_today()
    rows["odds_snapshots"] = ["2026-06-15"]  # exactly 2d → OK
    by = {s.table: s for s in check_freshness(_mk_db(tmp_path, rows, "a.db"), today=TODAY)}
    assert not by["odds_snapshots"].stale
    rows["odds_snapshots"] = ["2026-06-14"]  # 3d → stale
    by = {s.table: s for s in check_freshness(_mk_db(tmp_path, rows, "b.db"), today=TODAY)}
    assert by["odds_snapshots"].stale


def test_missing_critical_table_is_stale(tmp_path):
    # Only a non-critical table exists; the missing CRITICAL ones must gate.
    db = tmp_path / "obs.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE league_predictions (recorded_at TEXT)")
    conn.execute("INSERT INTO league_predictions VALUES ('2026-06-17')")
    conn.commit()
    conn.close()
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["odds_snapshots"].stale  # missing entirely → treated as stale
    assert by["odds_snapshots"].rows == 0
    assert main(["--db", str(db), "--today", "2026-06-17"]) == 1


def test_empty_table_is_stale(tmp_path):
    rows = _all_today()
    rows["jingcai_sp"] = []  # exists but empty
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["jingcai_sp"].stale and by["jingcai_sp"].days_stale is None
    assert main(["--db", str(db), "--today", "2026-06-17"]) == 1


def test_porcelain_format(tmp_path, capsys):
    db = _mk_db(tmp_path, _all_today())
    main(["--db", str(db), "--today", "2026-06-17", "--porcelain"])
    out = capsys.readouterr().out
    assert "OK\todds_snapshots\t" in out
    assert "OK\tjingcai_sp\t" in out
    # critical flag column = 1 for odds_snapshots
    line = next(r for r in out.splitlines() if r.startswith("OK\todds_snapshots"))
    assert line.split("\t")[5] == "1"


def test_missing_db_exits_one(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "nope.db")]) == 1


def test_epoch_timestamp_handled(tmp_path):
    # A capture table storing epoch ints (not ISO text) must still parse.
    import datetime as _dt

    epoch = int(_dt.datetime(2026, 6, 17, 12, 0, tzinfo=_dt.UTC).timestamp())
    db = tmp_path / "obs.db"
    conn = sqlite3.connect(db)
    for table, col, *_ in CAPTURE_TABLES:
        typ = "INTEGER" if table == "odds_snapshots" else "TEXT"
        conn.execute(f"CREATE TABLE {table} ({col} {typ})")
    conn.execute("INSERT INTO odds_snapshots (captured_at) VALUES (?)", (epoch,))
    for table, col, *_ in CAPTURE_TABLES:
        if table != "odds_snapshots":
            conn.execute(f"INSERT INTO {table} ({col}) VALUES ('2026-06-17')")
    conn.commit()
    conn.close()
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["odds_snapshots"].last_day == "2026-06-17"
    assert not by["odds_snapshots"].stale
