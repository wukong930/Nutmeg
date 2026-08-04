"""nutmeg-backfill-odds-names — 把库里**已有的**行补归一到正典队名。

`odds_source_aliases` 修的是**写入侧**:新行进 `odds_snapshots` 时就归一了。
但表是 append-only 的,别名表补一条,**之前落下的行还是分开的** —— 收盘线依旧
接不上盘面那一行,CLV 依旧少数据。这个 CLI 补的就是那个存量。

    nutmeg-backfill-odds-names              # 默认 dry-run,只报不写
    nutmeg-backfill-odds-names --apply      # 真写(先自动备份)

## 纪律

* **默认 dry-run。** 数据迁移的默认值必须是「不动」。
* **复用 sink 的同两个函数**(`canonical_league` / `canonical_team`),不另写一套
  归一逻辑 —— 否则哪天两边漂了,库里会出现「写入侧归一了、回填按另一套走」的
  第三种状态,而且没有任何东西会喊。
* **撞车就跳过,不合并、不删除。** `odds_snapshots` 上**没有 UNIQUE 索引**
  (只有两个普通索引),所以 UPDATE 撞车不会报错,而是**静默多出一行重复**。
  遇到就原样留着并打印出来,让人去看 —— 删数据不是这个工具该做的事。
* **每一步收窄都打印。** 「改了 0 行」必须能和「没去看」区分开。

## league 列也要一起归一

`canonical_team` 是按 (联赛, 队名) 查表的 ⇒ 只要 `league` 还写着 sport_key
(`soccer_usa_mls` 而不是 `USA_MLS`),队名归一就整个落空。所以两列一起处理,
顺序是先 league 后队名 —— 反过来会漏。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import logging
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from nutmeg.v4.data.odds_source_aliases import canonical_league, canonical_team

log = logging.getLogger("backfill_odds_names")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

#: 判定「同一条快照」的键。**不是**数据库约束(表上没有 UNIQUE)—— 是这个工具
#: 自己的撞车判据,和 `record_row_snapshot` 的去重口径一致。
_ROW_KEY = ("league", "match_date", "home_team", "away_team", "captured_at")


def plan(conn: sqlite3.Connection) -> tuple[list[tuple], Counter, list[tuple]]:
    """→ (要改的行, 每条别名命中数, 会撞车因而跳过的行)。只读,不写。"""
    rows = conn.execute(
        "SELECT id, league, match_date, home_team, away_team, captured_at "
        "FROM odds_snapshots").fetchall()
    # 现存键 → 好判断改完会不会和别的行重合
    seen: set[tuple] = {(r[1], r[2], r[3], r[4], r[5]) for r in rows}
    changes: list[tuple] = []
    hits: Counter = Counter()
    collisions: list[tuple] = []
    for rid, lg, md, home, away, cap in rows:
        new_lg = canonical_league(lg) or lg
        new_home = canonical_team(lg, home) or home
        new_away = canonical_team(lg, away) or away
        if (new_lg, new_home, new_away) == (lg, home, away):
            continue
        if new_lg != lg:
            hits[("<league>", lg)] += 1
        for old, new in ((home, new_home), (away, new_away)):
            if old != new:
                hits[(new_lg, old)] += 1
        key = (new_lg, md, new_home, new_away, cap)
        if key in seen:          # 改完会和另一行完全同键 ⇒ 静默重复,不碰
            collisions.append((rid, lg, home, away, new_lg, new_home, new_away))
            continue
        seen.discard((lg, md, home, away, cap))
        seen.add(key)
        changes.append((new_lg, new_home, new_away, rid))
    return changes, hits, collisions


def _backup(db: Path) -> Path:
    """WAL 下安全的**在线**备份(不锁 daemon)—— 同 scripts/backup_observation_db.sh。"""
    ts = _dt.datetime.now(_dt.UTC).strftime("%Y%m%dT%H%M%S")
    dest = db.with_name(f"{db.name}.bak-{ts}-pre-name-backfill")
    with sqlite3.connect(db) as src, sqlite3.connect(dest) as dst:
        src.backup(dst)
    return dest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="把 odds_snapshots 存量行补归一到正典队名")
    p.add_argument("--db", default="data/v4_observation.db")
    p.add_argument("--apply", action="store_true",
                   help="真写。不给就是 dry-run(默认),只报不改。")
    p.add_argument("--no-backup", action="store_true",
                   help="跳过 --apply 前的自动备份(不建议;给测试用)")
    args = p.parse_args(argv)

    db = Path(args.db)
    if not db.exists():
        log.error("库不存在:%s", db)
        return 1

    conn = sqlite3.connect(db)
    try:
        changes, hits, collisions = plan(conn)
        total = conn.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0]
        log.info("扫描 %d 行 → 需要改 %d 行,撞车跳过 %d 行", total, len(changes), len(collisions))
        for (lg, old), n in sorted(hits.items(), key=lambda x: (-x[1], x[0])):
            log.info("   %-20s %-26s %4d 处", lg, old, n)
        for rid, lg, h, a, nlg, nh, na in collisions:
            log.warning("   ⚠️ 撞车跳过 id=%s  %s/%s vs %s → %s/%s vs %s",
                        rid, lg, h, a, nlg, nh, na)

        if not args.apply:
            log.info("dry-run(没写任何东西)。确认无误后加 --apply。")
            return 0
        if not changes:
            log.info("没有要改的行 —— 存量已经是归一的。")
            return 0

        if not args.no_backup:
            log.info("备份 → %s", _backup(db))
        conn.executemany(
            "UPDATE odds_snapshots SET league=?, home_team=?, away_team=? WHERE id=?", changes)
        conn.commit()
        log.info("已写入 %d 行。", len(changes))

        left, _, _ = plan(conn)   # 自查:再规划一次必须为空(幂等)
        if left:
            log.error("⚠️ 复查仍有 %d 行待改 —— 归一不是幂等的,请查", len(left))
            return 1
        log.info("复查:0 行待改(幂等)。")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
