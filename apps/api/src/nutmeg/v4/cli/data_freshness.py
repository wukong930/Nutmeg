"""nutmeg-data-freshness — capture-table leak sentinel.

The data-accumulation crons capture POINT-IN-TIME data that is gone forever if a
run is missed — a Pinnacle line or a 竞彩 SP at time *T* cannot be re-fetched
later (settle jobs can `--refresh`; capture jobs cannot). This sentinel flags any
capture table that has stopped growing within its expected cadence, so a
silently-dead cron (cf. `daily_wc_settle`, dead 3 weeks before it was noticed by
accident) is caught within a day.

Two classes of table:

  • CAPTURE tables — written by a cron on a schedule. Stalling = a leak.
      - odds_snapshots / jingcai_sp / vote / exotic / closing / polymarket /
        score_ev are CRITICAL (forward-only foundations) → a stale one exits
        non-zero.
      - league_predictions / wc_predictions are WARN (seasonal: summer break /
        only during the tournament) → flagged but never fail the gate.

  • USER-ACTIVITY tables — written only when the user records a bet / uses a tab.
    Staleness reflects the user being 空仓, NOT a leak → reported, never gated.

体检 2026-07-03 P0-1 — sub-stream awareness: a table written by SEVERAL crons
hides a dead one behind the live ones' `max()` (odds_snapshots stayed green while
the `source='closing'` anchor could die unseen). Entries therefore carry an
optional WHERE filter + display name, and sister forward-only DBs in the same
data dir (score_ev_forward.db) are probed too.

体检 2026-07-03 P0-2 — heartbeat: every run touches `<db dir>/.data_freshness_heartbeat`.
The vote-capture cron (independent launchd job) alarms if that file goes >26h
stale — mutual watching, so the alarm chain itself dying no longer means silence
(the wc_settle-dead-3-weeks failure mode).

`--porcelain` emits TSV (STATUS<TAB>name<TAB>…) for scripts (health_check.sh).
Exit 0 = all CRITICAL capture streams fresh; 1 = at least one CRITICAL is stale.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

# (table, ts_col, max_stale_days, critical, 说明, where, 显示名)
#   where — 子流过滤 (None = 整表)。同表多 writer 时必须用它切开,否则活着的
#           writer 的 max() 会把死掉的子流顶成绿的 (P0-1 的病根)。
#   显示名 — None = 用表名;子流用 "table[tag]" 以免与整表条目撞键。
CAPTURE_TABLES: list[tuple[str, str, int, bool, str, str | None, str | None]] = [
    ("odds_snapshots", "captured_at", 2, True,
     "Pinnacle 线史 (CLV 地基)", None, None),
    ("odds_snapshots", "captured_at", 2, True,
     "Pinnacle 收盘锚 (closing 子流; --sports auto 随赛程自选联赛)",
     "source='closing'", "odds_snapshots[closing]"),
    ("jingcai_sp", "captured_at", 2, True, "竞彩 SP 捕获 (软水)", None, None),
    ("jingcai_sp", "opened_at", 2, True,
     "竞彩 初盘 SP (jc_open 子流, 开→收位移)",
     "opened_at IS NOT NULL", "jingcai_sp[open]"),
    ("jingcai_exotic_sp", "captured_at", 2, True,
     "竞彩 比分/总进球 SP (秋季测量地基)", None, None),
    ("jingcai_vote", "captured_at", 2, True, "竞彩 散户支持比例 (软水)", None, None),
    ("polymarket_gaps", "recorded_at", 3, True,
     "Polymarket 缺口 (proxy 依赖, 3 窗/天)", None, None),
    ("league_predictions", "recorded_at", 4, False, "模型盘预测日志 (夏歇宽松)", None, None),
    ("wc_predictions", "recorded_at", 3, False, "WC 模型预测 (仅赛会期)", None, None),
]

# 别库前向捕获 — db 文件与主观测库同目录。文件缺失 = 写它的 cron 生态整体死
# (或路径漂移) → 按 critical stale 报,绝不静默跳过。
# (db 文件名, table, ts_col, max_stale_days, critical, 说明)
SISTER_CAPTURE_TABLES: list[tuple[str, str, str, int, bool, str]] = [
    ("score_ev_forward.db", "score_ev_flags", "captured_at", 2, True,
     "比分/总进球 EV 前向记录 (score_ev_forward.db 别库)"),
]

HEARTBEAT_FILENAME = ".data_freshness_heartbeat"

# Reported for context only — never gated (user-activity driven).
USER_TABLES: list[tuple[str, str]] = [
    ("recommendation_sessions", "created_at"),
    ("single_predictions", "match_date"),
    ("settlements", "settled_at"),
    ("match_outcomes", "recorded_at"),
]


@dataclass
class TableStatus:
    table: str  # display name (子流 = "table[tag]")
    rows: int
    last_day: str | None
    days_stale: int | None  # None = empty / unparseable
    max_days: int
    critical: bool
    note: str

    @property
    def stale(self) -> bool:
        return self.days_stale is None or self.days_stale > self.max_days


def _row_count(conn: sqlite3.Connection, table: str, where: str | None = None) -> int | None:
    """None if the table does not exist."""
    q = f"SELECT count(*) FROM {table}"
    if where:
        q += f" WHERE {where}"
    try:
        return conn.execute(q).fetchone()[0]
    except sqlite3.OperationalError:
        return None


def _last_day(
    conn: sqlite3.Connection, table: str, col: str, where: str | None = None
) -> str | None:
    """Most-recent calendar day in `col`, handling ISO-text or epoch ints."""
    cond = f"{col} IS NOT NULL" + (f" AND ({where})" if where else "")
    v = conn.execute(
        f"SELECT {col} FROM {table} WHERE {cond} LIMIT 1"
    ).fetchone()
    if v is None:
        return None
    if isinstance(v[0], (int, float)) and v[0] > 1e9:
        expr = f"date({col},'unixepoch')"
    else:
        expr = f"substr(CAST({col} AS TEXT),1,10)"
    return conn.execute(
        f"SELECT max({expr}) FROM {table} WHERE {cond}"
    ).fetchone()[0]


def _days_stale(last_day: str | None, today: date) -> int | None:
    if not last_day:
        return None
    try:
        return (today - date.fromisoformat(last_day[:10])).days
    except ValueError:
        return None


def _probe(
    conn: sqlite3.Connection, name: str, table: str, col: str,
    maxd: int, crit: bool, note: str, where: str | None, today: date,
) -> TableStatus:
    n = _row_count(conn, table, where)
    if n is None:  # table missing entirely
        return TableStatus(name, 0, None, None, maxd, crit, note)
    last = _last_day(conn, table, col, where) if n else None
    return TableStatus(name, n, last, _days_stale(last, today), maxd, crit, note)


def check_freshness(
    db_path: str | Path, *, today: date | None = None
) -> list[TableStatus]:
    """One TableStatus per CAPTURE stream (declared order), main DB then sisters."""
    today = today or date.today()
    conn = sqlite3.connect(str(db_path))
    try:
        out: list[TableStatus] = []
        for table, col, maxd, crit, note, where, name in CAPTURE_TABLES:
            out.append(_probe(conn, name or table, table, col, maxd, crit, note,
                              where, today))
    finally:
        conn.close()
    for db_file, table, col, maxd, crit, note in SISTER_CAPTURE_TABLES:
        sef = Path(db_path).parent / db_file
        if not sef.exists():
            out.append(TableStatus(table, 0, None, None, maxd, crit, note))
            continue
        sconn = sqlite3.connect(str(sef))
        try:
            out.append(_probe(sconn, table, table, col, maxd, crit, note, None, today))
        finally:
            sconn.close()
    return out


def check_api_quota() -> list[str]:
    """体检 Wave3 (P1#13) — quota-exhaustion alarm. Both feeds have PULL-only
    panels; hitting the cap means the fresher-line overlay/closing anchor
    silently fall back to stale mirrors (EV cards quietly go wrong). Probe the
    FREE endpoints (AF /status; OA /sports, whose response headers carry the
    credit counters) and return alarm lines when usage crosses the red line.
    Fail-soft + key-gated: no keys in env (tests, offline) → no probe, no alarm."""
    import os

    alarms: list[str] = []
    af_key = os.environ.get("NUTMEG_API_FOOTBALL_KEY")
    if af_key:
        try:
            import httpx
            r = httpx.get("https://v3.football.api-sports.io/status",
                          headers={"x-apisports-key": af_key}, timeout=6)
            req = ((r.json() or {}).get("response") or {}).get("requests") or {}
            cur, lim = req.get("current"), req.get("limit_day")
            if cur is not None and lim and float(cur) / float(lim) >= 0.9:
                alarms.append(
                    f"AF 日配额 {cur}/{lim} (≥90%) — 耗尽后叠加静默回落陈旧线")
        except Exception:  # noqa: BLE001 — probe failure ≠ quota alarm
            pass
    oa_key = os.environ.get("NUTMEG_ODDS_API_KEY")
    if oa_key:
        try:
            import httpx
            r = httpx.get("https://api.the-odds-api.com/v4/sports/",
                          params={"apiKey": oa_key}, timeout=6)
            rem = r.headers.get("x-requests-remaining")
            if rem is not None and float(rem) < 50:
                alarms.append(
                    f"Odds API 剩余 credit {rem} (<50) — 收盘锚/鲜线将断供")
        except Exception:  # noqa: BLE001
            pass
    return alarms


def write_heartbeat(db_path: str | Path) -> None:
    """Touch `<db dir>/.data_freshness_heartbeat` — proof the sentinel ran.
    Fail-soft: a heartbeat failure must never break the freshness report."""
    try:
        hb = Path(db_path).resolve().parent / HEARTBEAT_FILENAME
        hb.write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")
    except OSError:
        print(f"⚠ 心跳文件写入失败: {hb}", file=sys.stderr)


def _user_rows(db_path: str | Path, today: date) -> list[tuple[str, int, str | None, int | None]]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = []
        for table, col in USER_TABLES:
            n = _row_count(conn, table)
            if n is None:
                continue
            last = _last_day(conn, table, col) if n else None
            rows.append((table, n, last, _days_stale(last, today)))
        return rows
    finally:
        conn.close()


def render(statuses: list[TableStatus], db_path: str | Path, today: date) -> str:
    lines = [f"# 捕获表新鲜度哨兵 (today={today})", ""]
    bad = [s for s in statuses if s.stale and s.critical]
    warn = [s for s in statuses if s.stale and not s.critical]
    for s in statuses:
        mark = "✓" if not s.stale else ("✗" if s.critical else "⚠")
        age = "空/缺表" if s.days_stale is None else f"{s.days_stale}d"
        within = f"(≤{s.max_days}d)"
        tag = "CRIT" if s.critical else "warn"
        lines.append(
            f"  {mark} {s.table:<24} {s.rows:>6} 行 · 最后 {s.last_day or '—':<10} "
            f"· {age:>7} {within} [{tag}] {s.note}"
        )
    lines += ["", "  — 用户行为表(空仓即僵,不门控)—"]
    for table, n, last, ds in _user_rows(db_path, today):
        age = "—" if ds is None else f"{ds}d 前"
        lines.append(f"  · {table:<24} {n:>6} 行 · 最后 {last or '—':<10} · {age}")
    lines += [""]
    if bad:
        names = ", ".join(s.table for s in bad)
        lines.append(f"判定: ✗ STALE — critical 捕获流停长: {names}")
        lines.append("  → 某个捕获 cron 多半静默死了。`launchctl print` 查它真在跑没;")
        lines.append("    用产出物/数据验证,别信 log mtime。")
    elif warn:
        lines.append(f"判定: ⚠ 季节性捕获表偏旧(不致命): {', '.join(s.table for s in warn)}")
    else:
        lines.append("判定: ✓ 所有捕获流都在按节奏入库,无漏。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="捕获表漏数据哨兵 — 某个捕获流停止增长即报警"
    )
    p.add_argument("--db", default="data/v4_observation.db", help="观测库路径")
    p.add_argument("--today", default=None, help="覆盖今天 (YYYY-MM-DD, 测试用)")
    p.add_argument(
        "--porcelain", action="store_true",
        help="TSV 输出 (STATUS<TAB>name<TAB>rows<TAB>last<TAB>days<TAB>crit<TAB>note) 供脚本解析",
    )
    p.add_argument("--out", default=None, help="把人类报告写到文件 (cron 用)")
    p.add_argument("--no-quota", action="store_true",
                   help="跳过 AF/OA 配额探针 (默认: env 里有 key 才探,fail-soft)")
    args = p.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"✗ 观测库不存在: {db_path}", file=sys.stderr)
        return 1
    today = date.fromisoformat(args.today) if args.today else date.today()

    statuses = check_freshness(db_path, today=today)
    # Heartbeat even when stale — it means "the sentinel RAN", not "all green";
    # the vote-cron watchdog alarms on ITS absence (P0-2 mutual watching).
    write_heartbeat(db_path)
    crit_stale = [s for s in statuses if s.stale and s.critical]
    quota_alarms = [] if args.no_quota else check_api_quota()

    if args.porcelain:
        for s in statuses:
            status = "OK" if not s.stale else ("STALE" if s.critical else "OLD")
            print(
                f"{status}\t{s.table}\t{s.rows}\t{s.last_day or '-'}\t"
                f"{'-' if s.days_stale is None else s.days_stale}\t"
                f"{int(s.critical)}\t{s.note}"
            )
        for q in quota_alarms:
            print(f"QUOTA\t{q}")
    else:
        report = render(statuses, db_path, today)
        if quota_alarms:
            report += "\n" + "\n".join(f"⚠️ 配额: {q}" for q in quota_alarms)
        print(report)
        if args.out:
            Path(args.out).write_text(report + "\n", encoding="utf-8")

    # Quota exhaustion rides the SAME non-zero exit as a stale capture table →
    # the daily_settle chain's osascript push fires for it too (P1#13: the
    # pull-only panels meant a burned-out key was discovered days later).
    return 1 if (crit_stale or quota_alarms) else 0


if __name__ == "__main__":
    sys.exit(main())
