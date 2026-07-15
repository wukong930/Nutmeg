"""Tests for nutmeg-data-freshness — the capture-table leak sentinel."""
from __future__ import annotations

import re
import sqlite3
from datetime import date

from nutmeg.v4.cli.data_freshness import (
    CAPTURE_TABLES,
    HEARTBEAT_FILENAME,
    SISTER_CAPTURE_TABLES,
    check_freshness,
    main,
)

TODAY = date(2026, 6, 17)


def _entry_key(table: str, where: str | None, name: str | None) -> str:
    return name or table


def _mk_db(tmp_path, rows: dict[str, list[str]], name: str = "obs.db"):
    """Build a temp observation DB (+ sister DBs) with the capture streams.

    `rows` is keyed by DISPLAY name (entry name or table). Sub-stream inserts
    also satisfy their WHERE filter (e.g. source='closing' rows get that col).
    """
    db = tmp_path / name
    if db.exists():
        db.unlink()
    conn = sqlite3.connect(db)
    cols_by_table: dict[str, set[str]] = {}
    for table, col, _maxd, _crit, _note, where, _nm in CAPTURE_TABLES:
        cols_by_table.setdefault(table, set()).add(col)
        for wc in re.findall(r"(\w+)\s*(?:=|IS)", where or ""):
            cols_by_table[table].add(wc)
    for table, cols in cols_by_table.items():
        conn.execute(
            f"CREATE TABLE {table} ({', '.join(f'{c} TEXT' for c in sorted(cols))})"
        )
    for table, col, _maxd, _crit, _note, where, nm in CAPTURE_TABLES:
        key = _entry_key(table, where, nm)
        extra = dict(re.findall(r"(\w+)\s*=\s*'([^']*)'", where or ""))
        for v in rows.get(key, []):
            data = {col: v, **extra}
            conn.execute(
                f"INSERT INTO {table} ({','.join(data)}) "
                f"VALUES ({','.join('?' * len(data))})",
                tuple(data.values()),
            )
    conn.commit()
    conn.close()
    # Sister forward-only DBs live next to the main DB.
    for db_file, table, col, _maxd, _crit, _note in SISTER_CAPTURE_TABLES:
        sef = tmp_path / db_file
        if sef.exists():
            sef.unlink()
        sconn = sqlite3.connect(sef)
        sconn.execute(f"CREATE TABLE {table} ({col} TEXT)")
        for v in rows.get(table, []):
            sconn.execute(f"INSERT INTO {table} ({col}) VALUES (?)", (v,))
        sconn.commit()
        sconn.close()
    return db


def _all_today():
    fresh = {
        _entry_key(t, w, nm): ["2026-06-17"]
        for t, _c, _m, _cr, _n, w, nm in CAPTURE_TABLES
    }
    for _f, table, _c, _m, _cr, _n in SISTER_CAPTURE_TABLES:
        fresh[table] = ["2026-06-17"]
    return fresh


# ⚠️ 下面每个 main() 调用都必须带 --no-quota,别删。
# 2026-07-15:`main()` 的返回码是 `1 if (crit_stale or quota_alarms) else 0`,而配额探针
# 打的是【线上】AF/Odds API。于是这些本该只测「新鲜度逻辑」的单元测试被真实世界耦合了:
#   · Odds API 月配额耗尽(credit 0)那天,断言 ==0 的两个直接转红 —— 跟被测逻辑无关;
#   · 更糟的是断言 ==1 的那几个会【因为配额告警而"通过"】,不是因为它们造的陈旧数据
#     ——即静默变成空测试,看着绿其实什么都没守。
# --no-quota 把探针关掉 → 每个测试只对自己声称在测的东西负责。配额本身该由 cron/
# health_check 在真实环境里报,不该由单元测试的返回码承担。
def test_all_fresh_exits_zero(tmp_path):
    db = _mk_db(tmp_path, _all_today())
    statuses = check_freshness(db, today=TODAY)
    assert all(not s.stale for s in statuses)
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota"]) == 0


def test_critical_stale_exits_one(tmp_path):
    rows = _all_today()
    # Both the whole-table stream AND the closing sub-stream must be old to
    # stale the base entry (sub-stream rows live in the same table).
    rows["odds_snapshots"] = ["2026-06-05"]
    rows["odds_snapshots[closing]"] = ["2026-06-05"]
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["odds_snapshots"].stale and by["odds_snapshots"].critical
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota"]) == 1


def test_closing_substream_stale_behind_fresh_table(tmp_path):
    # 体检 P0-1 regression: other writers (cup_market/predict_log) keep the
    # whole-table max() green while the closing anchor dies. The sub-stream
    # entry must flag it anyway.
    rows = _all_today()
    rows["odds_snapshots"] = ["2026-06-17"]          # live writers, fresh
    rows["odds_snapshots[closing]"] = ["2026-06-05"]  # closing cron dead
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert not by["odds_snapshots"].stale
    assert by["odds_snapshots[closing]"].stale and by["odds_snapshots[closing]"].critical
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota"]) == 1


def test_jc_open_substream_tracked_separately(tmp_path):
    # jingcai_sp fresh (capture cron alive) but opened_at stalled (open-SP
    # sub-flow dead) must flag the [open] stream only.
    rows = _all_today()
    rows["jingcai_sp"] = ["2026-06-17"]
    rows["jingcai_sp[open]"] = ["2026-06-01"]
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert not by["jingcai_sp"].stale
    assert by["jingcai_sp[open]"].stale and by["jingcai_sp[open]"].critical


def test_sister_db_missing_is_critical_stale(tmp_path):
    db = _mk_db(tmp_path, _all_today())
    (tmp_path / "score_ev_forward.db").unlink()
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["score_ev_flags"].stale and by["score_ev_flags"].critical
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota"]) == 1


def test_heartbeat_written_even_when_stale(tmp_path):
    # P0-2: the heartbeat proves the sentinel RAN (not that all is green) —
    # written on both the all-fresh and the critical-stale paths.
    rows = _all_today()
    rows["jingcai_vote"] = ["2026-06-01"]  # critical stale
    db = _mk_db(tmp_path, rows)
    hb = tmp_path / HEARTBEAT_FILENAME
    assert not hb.exists()
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota"]) == 1
    assert hb.exists() and hb.read_text().strip()


def test_seasonal_old_does_not_gate(tmp_path):
    # A stale WARN table (league_predictions) must NOT fail the gate.
    rows = _all_today()
    rows["league_predictions"] = ["2026-06-01"]  # stale but non-critical
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["league_predictions"].stale and not by["league_predictions"].critical
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota"]) == 0


def test_within_cadence_not_stale(tmp_path):
    # odds_snapshots cadence = 2d: a 2-day-old row is still fresh, 3-day is stale.
    rows = _all_today()
    rows["odds_snapshots"] = ["2026-06-15"]  # exactly 2d → OK
    rows["odds_snapshots[closing]"] = ["2026-06-15"]
    by = {s.table: s for s in check_freshness(_mk_db(tmp_path, rows, "a.db"), today=TODAY)}
    assert not by["odds_snapshots"].stale
    rows["odds_snapshots"] = ["2026-06-14"]  # 3d → stale
    rows["odds_snapshots[closing]"] = ["2026-06-14"]
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
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota"]) == 1


def test_empty_table_is_stale(tmp_path):
    rows = _all_today()
    rows["jingcai_sp"] = []  # exists but empty
    rows["jingcai_sp[open]"] = []
    db = _mk_db(tmp_path, rows)
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["jingcai_sp"].stale and by["jingcai_sp"].days_stale is None
    assert main(["--db", str(db), "--today", "2026-06-17", "--no-quota"]) == 1


def test_porcelain_format(tmp_path, capsys):
    db = _mk_db(tmp_path, _all_today())
    # --no-quota:本测试只管输出【格式】。放开探针会去打线上 API(慢+依赖网络),
    # 且配额告警行可能混进正在解析的 porcelain 输出里。
    main(["--db", str(db), "--today", "2026-06-17", "--porcelain", "--no-quota"])
    out = capsys.readouterr().out
    assert "OK\todds_snapshots\t" in out
    assert "OK\todds_snapshots[closing]\t" in out
    assert "OK\tjingcai_sp\t" in out
    assert "OK\tscore_ev_flags\t" in out
    # critical flag column = 1 for odds_snapshots
    line = next(r for r in out.splitlines() if r.startswith("OK\todds_snapshots\t"))
    assert line.split("\t")[5] == "1"


def test_missing_db_exits_one(tmp_path, capsys):
    # --no-quota:今天库不存在会早退返回 1,加不加都过。但【配额告警同样返回 1】——
    # 万一哪天早退逻辑坏了,这条会靠配额"过"= 假绿。关掉探针才是真在测早退。
    assert main(["--db", str(tmp_path / "nope.db"), "--no-quota"]) == 1


def test_epoch_timestamp_handled(tmp_path):
    # A capture table storing epoch ints (not ISO text) must still parse.
    import datetime as _dt

    epoch = int(_dt.datetime(2026, 6, 17, 12, 0, tzinfo=_dt.UTC).timestamp())
    rows = _all_today()
    rows.pop("odds_snapshots")
    rows.pop("odds_snapshots[closing]")
    db = _mk_db(tmp_path, rows)
    conn = sqlite3.connect(db)
    # INTEGER column (epoch), unlike the TEXT tables _mk_db builds.
    conn.execute("DROP TABLE odds_snapshots")
    conn.execute("CREATE TABLE odds_snapshots (captured_at INTEGER, source TEXT)")
    conn.execute(
        "INSERT INTO odds_snapshots (captured_at, source) VALUES (?, 'closing')",
        (epoch,),
    )
    conn.commit()
    conn.close()
    by = {s.table: s for s in check_freshness(db, today=TODAY)}
    assert by["odds_snapshots"].last_day == "2026-06-17"
    assert not by["odds_snapshots"].stale
    assert by["odds_snapshots[closing]"].last_day == "2026-06-17"
