"""把观测库里被劈成两轨的 ``league`` 归一到规范形(2026-08-05)。

## 病

``jingcai_sp`` 有**两个写入方、两套联赛词汇**:sporttery cron 写竞彩中文缩写
(芬超/欧冠/…),面板「记一笔」(source=market_mode)写 V4 EN 代码
(FIN_VEIKKAUSLIIGA/UCL/…)。按 RAW 字符串分组 ⇒ **一个联赛被算成两组**:
per-league N 被稀释,CLV 闸的 BHY-FDR 家族凭空多一个成员(2026-07-02 实测:
芬超 40 行 + FIN_VEIKKAUSLIIGA 8 行本是同一个联赛)。

实测(2026-08-05)真被劈开的只有两张表:
  · ``jingcai_sp``            7 个联赛(世界杯/挪超/欧冠/欧罗巴/瑞超/芬超/韩职)
  · ``jingcai_sp_snapshots``  1 个(挪超)
其余表都是单轨。``polymarket_gaps`` 两轨并存但规范化后**零重叠**(EN 是外盘
33 个联赛、中文是竞彩侧 2 个),那是正常的,**不在本工具范围**。

## 为什么回填,而 `league_labels` 说「在读取方修」

两件事,都要,不互斥:
  · 读取方 ``canonical_league`` 修的是**分组**(GROUP BY 之后再归一)——
    但它要先把行取出来才有得归,``WHERE league IN (…)`` 是在取出来**之前**跑的。
  · 回填修的是**存量**:回填之后 ``GROUP BY league`` 直接就是对的,不依赖每个
    分析脚本记得调 canonical。临时查询(最容易出错的地方)因此免疫。

⚠️ **回填不能替代 `league_filter_variants`**:归到中文一轨之后,拿 V4 代码去
``WHERE`` 照样 0 行 —— 只是换了哪一轨会错。两个一起才闭合。

## 安全性

· 默认 dry-run,``--apply`` 才写,写前自备份(``Path.backup``)。
· 只改 ``league`` 一列,``source`` 列原样保留 ⇒ **写入方溯源一点没丢**。
· ``jingcai_sp`` 的 UNIQUE 键是 ``(match_date, home_team, away_team, market)``,
  ``league`` **不在键里**;``jingcai_sp_snapshots`` 没有 UNIQUE ⇒ 改 league
  在这两张表上不可能撞键。(已实测,不是推断 —— 见 ``test_backfill_league_labels``
  里那条拿真 schema 断言的用例。)
· 归一方向 = ``canonical_league``,**不另写一套映射**;它认不出来的标签原样
  不动(fail-open),并由 ``data_freshness.check_league_labels`` 报成 unknown。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from nutmeg.v4.data.league_labels import canonical_league

#: (表, 列)。和 `data_freshness._LEAGUE_TRACK_TABLES` 是同一份现实的两个副本;
#: 加表时两处都要动 —— 探针报了却没工具修,和有工具却没人报,一样是半个闭环。
TABLES: tuple[tuple[str, str], ...] = (
    ("jingcai_sp", "league"),
    ("jingcai_sp_snapshots", "league"),
)


def plan(conn: sqlite3.Connection) -> list[tuple[str, str, str, str, int]]:
    """→ ``[(表, 列, 旧写法, 新写法, 行数)]``,只含真正会变的。"""
    out: list[tuple[str, str, str, str, int]] = []
    for table, col in TABLES:
        try:
            rows = conn.execute(
                f"SELECT {col}, COUNT(*) FROM {table} WHERE {col} IS NOT NULL "
                f"GROUP BY {col}").fetchall()
        except sqlite3.Error:
            continue                      # 表不存在 = 跳过,不是错误
        for raw, n in rows:
            new = canonical_league(raw)
            if new != str(raw).strip():
                out.append((table, col, str(raw), new, int(n)))
    return out


def apply(conn: sqlite3.Connection, changes) -> int:
    n = 0
    for table, col, old, new, _ in changes:
        cur = conn.execute(f"UPDATE {table} SET {col} = ? WHERE {col} = ?", (new, old))
        n += cur.rowcount
    conn.commit()
    return n


def _backup(db: Path) -> Path:
    """拷贝(不是 move)一份带时间戳的副本,和库里其它 .bak-* 同一套命名。"""
    import shutil
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    dst = db.with_name(f"{db.name}.bak-{stamp}-pre-league-canon")
    shutil.copy2(db, dst)
    return dst


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="把观测库里劈成两轨的 league 归一到规范形")
    p.add_argument("--db", default="data/v4_observation.db")
    p.add_argument("--apply", action="store_true", help="真写(默认只预演)")
    p.add_argument("--no-backup", action="store_true", help="--apply 时不自备份(不建议)")
    args = p.parse_args(argv)

    db = Path(args.db)
    if not db.exists():
        print(f"✗ 观测库不存在: {db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(db)
    try:
        changes = plan(conn)
    finally:
        conn.close()

    if not changes:
        # ⚠️ 「零改动」必须说清是**扫过了**才零,不是没扫 —— 同族教训见
        # [[health-check-guardrails]] 的「零新增 ≠ 扫完了」。
        print(f"✓ 无需回填:{len(TABLES)} 张表全部已是规范形 "
              f"({', '.join(t for t, _ in TABLES)})")
        return 0

    by_table = Counter(c[0] for c in changes)
    print(f"计划改 {len(changes)} 组写法 / {sum(c[4] for c in changes)} 行 "
          f"({dict(by_table)}):")
    for table, col, old, new, n in changes:
        print(f"  {table}.{col}: {old!r} → {new!r}  ({n} 行)")

    if not args.apply:
        print("\n(预演。加 --apply 真写)")
        return 0

    if not args.no_backup:
        print(f"备份 → {_backup(db).name}")
    conn = sqlite3.connect(db)
    try:
        n = apply(conn, changes)
        # 幂等自检:改完再算一遍 plan,必须为空。空 ≠「跑过了」,所以明说。
        left = plan(conn)
    finally:
        conn.close()
    print(f"✓ 已更新 {n} 行;复查残留 {len(left)} 组"
          + ("" if not left else f" ⚠️ {left}"))
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())
