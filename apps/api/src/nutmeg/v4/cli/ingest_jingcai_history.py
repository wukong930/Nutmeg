"""竞彩 历史赔率走势回填 — enumerate → fetch → store.

`getUniformMatchResultV1`(按日期枚举 matchId+leagueId+精确 matchDate)→ 过滤到 13 受训
联赛 → `getFixedBonusV1`(每场全程胜平负/让球走势)→ `jingcai_odds_history`。喂预注册
§H 历史 held-out 分析(`docs/autumn_prereg_analysis_plan.md`,`记忆
jingcai-fixedbonus-history-endpoint`)。

只读抓取、FAIL-SOFT、**断点续**(默认跳过已入库 matchId → 中断可重跑)、限速。中国站:
调用前清代理(`HTTP_PROXY= HTTPS_PROXY=`),同 sporttery 其它 cron。
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import time

from nutmeg.v4.data.league_labels import TRAINED_LEAGUES_CN, canonical_league
from nutmeg.v4.data.sources.sporttery_history import fetch_and_parse, iter_match_ids
from nutmeg.v4.observation.jingcai_history import record_history_match


def _existing_ids(db_path: str) -> set[int]:
    """matchIds already in jingcai_odds_history (for resume/skip). {} on any error."""
    try:
        with sqlite3.connect(db_path) as conn:
            return {r[0] for r in conn.execute(
                "SELECT DISTINCT match_id FROM jingcai_odds_history")}
    except sqlite3.Error:
        return set()


def _date_chunks(begin: str, end: str, days: int):
    """Yield (chunk_begin, chunk_end) 'YYYY-MM-DD' spanning [begin, end], ≤`days` each
    (bounds enumeration query size + gives progress granularity)."""
    b, e = dt.date.fromisoformat(begin), dt.date.fromisoformat(end)
    while b <= e:
        ce = min(b + dt.timedelta(days=days - 1), e)
        yield b.isoformat(), ce.isoformat()
        b = ce + dt.timedelta(days=1)


def backfill(db_path: str, begin: str, end: str, *, leagues: frozenset[str] | None,
             sleep: float, limit: int, dry_run: bool, skip_existing: bool,
             chunk_days: int) -> dict:
    """Enumerate [begin,end], filter to `leagues` (None = all), fetch+store each new
    match's odds series. Returns a summary dict. `leagues` are canonical CN abbrevs."""
    seen = _existing_ids(db_path) if skip_existing else set()
    stat = {"enumerated": 0, "in_scope": 0, "fetched": 0, "stored_rows": 0,
            "skipped": 0, "failed": 0, "chunks_empty": 0}
    for cb, ce in _date_chunks(begin, end, chunk_days):
        # 一个 14 天窗口跨全部竞彩联赛 NEVER 真空 → 枚举返回 0 = 节流/网络失败,不是真没赛。
        # 退避重试(防「静默丢整段」——2024-25 首跑就这样丢了 09→05 段)。
        matches = list(iter_match_ids(cb, ce))
        tries = 0
        while not matches and tries < 4:
            tries += 1
            time.sleep(min(15 * tries, 60))
            matches = list(iter_match_ids(cb, ce))
        if not matches:
            stat["chunks_empty"] += 1
            print(f"  ⚠️ {cb}→{ce} 枚举空(退避 4 次仍空)— 记为缺口,勿当已覆盖")
            continue
        for m in matches:
            stat["enumerated"] += 1
            if leagues is not None and canonical_league(m.get("league_cn")) not in leagues:
                continue
            stat["in_scope"] += 1
            mid = m["match_id"]
            if mid in seen:
                stat["skipped"] += 1
                continue
            if dry_run:
                continue
            parsed = fetch_and_parse(mid)
            if not parsed:
                stat["failed"] += 1
                continue
            # enumeration's matchDate is authoritative (getFixedBonus has no kickoff)
            parsed["close_date"] = m.get("match_date") or parsed.get("close_date")
            stat["stored_rows"] += record_history_match(db_path, parsed)
            stat["fetched"] += 1
            seen.add(mid)
            if stat["fetched"] % 25 == 0:
                print(f"  …{cb}: 枚举 {stat['enumerated']} · 在范围 {stat['in_scope']} · "
                      f"已抓 {stat['fetched']} · 行 {stat['stored_rows']}")
            if sleep:
                time.sleep(sleep)
            if limit and stat["fetched"] >= limit:
                print(f"  达到 --limit {limit},停")
                return stat
    return stat


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="回填竞彩历史赔率走势 → jingcai_odds_history")
    ap.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    ap.add_argument("--begin", required=True, help="起始日 YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="结束日 YYYY-MM-DD")
    ap.add_argument("--leagues", default="trained",
                    help="'trained'(13 受训联赛,默认) | 'all' | 逗号分隔中文缩写")
    ap.add_argument("--sleep", type=float, default=0.15, help="每场之间限速(秒)")
    ap.add_argument("--chunk-days", type=int, default=14, help="枚举日期段大小")
    ap.add_argument("--limit", type=int, default=0, help="最多抓 N 场(0=不限;测试用)")
    ap.add_argument("--dry-run", action="store_true", help="只枚举计数,不 fetch/store")
    ap.add_argument("--no-skip-existing", action="store_true", help="不跳过已入库 matchId")
    a = ap.parse_args(argv)

    if a.leagues == "trained":
        leagues: frozenset[str] | None = TRAINED_LEAGUES_CN
    elif a.leagues == "all":
        leagues = None
    else:
        leagues = frozenset(x.strip() for x in a.leagues.split(",") if x.strip())

    print(f"回填 {a.begin} → {a.end} · 联赛="
          f"{'全部' if leagues is None else '/'.join(sorted(leagues))} · dry_run={a.dry_run}")
    stat = backfill(a.db, a.begin, a.end, leagues=leagues, sleep=a.sleep, limit=a.limit,
                    dry_run=a.dry_run, skip_existing=not a.no_skip_existing,
                    chunk_days=a.chunk_days)
    print("完成:", stat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
