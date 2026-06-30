"""nutmeg-data-freshness — capture-table leak sentinel.

The data-accumulation crons capture POINT-IN-TIME data that is gone forever if a
run is missed — a Pinnacle line or a 竞彩 SP at time *T* cannot be re-fetched
later (settle jobs can `--refresh`; capture jobs cannot). This sentinel flags any
capture table that has stopped growing within its expected cadence, so a
silently-dead cron (cf. `daily_wc_settle`, dead 3 weeks before it was noticed by
accident) is caught within a day.

Two classes of table:

  • CAPTURE tables — written by a cron on a schedule. Stalling = a leak.
      - odds_snapshots / jingcai_sp are CRITICAL (the CLV + 竞彩 soft-water
        foundation, year-round) → a stale one exits non-zero.
      - league_predictions / wc_predictions are WARN (seasonal: summer break /
        only during the tournament) → flagged but never fail the gate.

  • USER-ACTIVITY tables — written only when the user records a bet / uses a tab.
    Staleness reflects the user being 空仓, NOT a leak → reported, never gated.

`--porcelain` emits TSV (STATUS<TAB>table<TAB>…) for scripts (health_check.sh).
Exit 0 = all CRITICAL capture tables fresh; 1 = at least one CRITICAL is stale.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# (table, ts_col, max_stale_days, critical, 说明)
CAPTURE_TABLES: list[tuple[str, str, int, bool, str]] = [
    ("odds_snapshots", "captured_at", 2, True, "Pinnacle 线史 (CLV 地基)"),
    ("jingcai_sp", "captured_at", 2, True, "竞彩 SP 捕获 (软水)"),
    ("jingcai_vote", "captured_at", 2, True, "竞彩 散户支持比例 (软水)"),
    ("league_predictions", "recorded_at", 4, False, "模型盘预测日志 (夏歇宽松)"),
    ("wc_predictions", "recorded_at", 3, False, "WC 模型预测 (仅赛会期)"),
]

# Reported for context only — never gated (user-activity driven).
USER_TABLES: list[tuple[str, str]] = [
    ("recommendation_sessions", "created_at"),
    ("single_predictions", "match_date"),
    ("settlements", "settled_at"),
    ("match_outcomes", "recorded_at"),
]


@dataclass
class TableStatus:
    table: str
    rows: int
    last_day: str | None
    days_stale: int | None  # None = empty / unparseable
    max_days: int
    critical: bool
    note: str

    @property
    def stale(self) -> bool:
        return self.days_stale is None or self.days_stale > self.max_days


def _row_count(conn: sqlite3.Connection, table: str) -> int | None:
    """None if the table does not exist."""
    try:
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return None


def _last_day(conn: sqlite3.Connection, table: str, col: str) -> str | None:
    """Most-recent calendar day in `col`, handling ISO-text or epoch ints."""
    v = conn.execute(
        f"SELECT {col} FROM {table} WHERE {col} IS NOT NULL LIMIT 1"
    ).fetchone()
    if v is None:
        return None
    if isinstance(v[0], (int, float)) and v[0] > 1e9:
        expr = f"date({col},'unixepoch')"
    else:
        expr = f"substr(CAST({col} AS TEXT),1,10)"
    return conn.execute(
        f"SELECT max({expr}) FROM {table} WHERE {col} IS NOT NULL"
    ).fetchone()[0]


def _days_stale(last_day: str | None, today: date) -> int | None:
    if not last_day:
        return None
    try:
        return (today - date.fromisoformat(last_day[:10])).days
    except ValueError:
        return None


def check_freshness(
    db_path: str | Path, *, today: date | None = None
) -> list[TableStatus]:
    """One TableStatus per CAPTURE table (in declared order)."""
    today = today or date.today()
    conn = sqlite3.connect(str(db_path))
    try:
        out: list[TableStatus] = []
        for table, col, maxd, crit, note in CAPTURE_TABLES:
            n = _row_count(conn, table)
            if n is None:  # table missing entirely
                out.append(TableStatus(table, 0, None, None, maxd, crit, note))
                continue
            last = _last_day(conn, table, col) if n else None
            out.append(
                TableStatus(table, n, last, _days_stale(last, today), maxd, crit, note)
            )
        return out
    finally:
        conn.close()


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
            f"  {mark} {s.table:<22} {s.rows:>6} 行 · 最后 {s.last_day or '—':<10} "
            f"· {age:>7} {within} [{tag}] {s.note}"
        )
    lines += ["", "  — 用户行为表(空仓即僵,不门控)—"]
    for table, n, last, ds in _user_rows(db_path, today):
        age = "—" if ds is None else f"{ds}d 前"
        lines.append(f"  · {table:<24} {n:>6} 行 · 最后 {last or '—':<10} · {age}")
    lines += [""]
    if bad:
        names = ", ".join(s.table for s in bad)
        lines.append(f"判定: ✗ STALE — critical 捕获表停长: {names}")
        lines.append("  → 某个捕获 cron 多半静默死了。`launchctl print` 查它真在跑没;")
        lines.append("    用产出物/数据验证,别信 log mtime。")
    elif warn:
        lines.append(f"判定: ⚠ 季节性捕获表偏旧(不致命): {', '.join(s.table for s in warn)}")
    else:
        lines.append("判定: ✓ 所有捕获表都在按节奏入库,无漏。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="捕获表漏数据哨兵 — 某张捕获表停止增长即报警"
    )
    p.add_argument("--db", default="data/v4_observation.db", help="观测库路径")
    p.add_argument("--today", default=None, help="覆盖今天 (YYYY-MM-DD, 测试用)")
    p.add_argument(
        "--porcelain", action="store_true",
        help="TSV 输出 (STATUS<TAB>table<TAB>rows<TAB>last<TAB>days<TAB>crit<TAB>note) 供脚本解析",
    )
    p.add_argument("--out", default=None, help="把人类报告写到文件 (cron 用)")
    args = p.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"✗ 观测库不存在: {db_path}", file=sys.stderr)
        return 1
    today = date.fromisoformat(args.today) if args.today else date.today()

    statuses = check_freshness(db_path, today=today)
    crit_stale = [s for s in statuses if s.stale and s.critical]

    if args.porcelain:
        for s in statuses:
            status = "OK" if not s.stale else ("STALE" if s.critical else "OLD")
            print(
                f"{status}\t{s.table}\t{s.rows}\t{s.last_day or '-'}\t"
                f"{'-' if s.days_stale is None else s.days_stale}\t"
                f"{int(s.critical)}\t{s.note}"
            )
    else:
        report = render(statuses, db_path, today)
        print(report)
        if args.out:
            Path(args.out).write_text(report + "\n", encoding="utf-8")

    return 1 if crit_stale else 0


if __name__ == "__main__":
    sys.exit(main())
