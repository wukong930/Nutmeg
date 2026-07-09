#!/usr/bin/env python
"""真 Pinnacle 历史收盘回填(§H 确诊 CLV)。

2-pass 避 in-play:pass1 每比赛日 T00:00 快照 → 得当日各场 kickoff;pass2 把 kickoff 按
30min 分桶,每桶 (桶起−5min) 快照 → Pinnacle 收盘(只用 commence≥快照时刻的场)。
record_close 只在快照更贴近开赛时覆盖 → 每场落到其开赛前最近一桶 ≈ 5–35min 紧收盘
(freeze-gap 的 late-movement 信号才不被粗收盘抹平)。分桶把逐 kickoff(6–8/天)砍到
真槽数(2–4/天)≈ 半成本。比赛日来自 jingcai_odds_history(只抓竞彩真有的日子)。

用法:
  python scripts/backfill_pinnacle_close.py <league_cn> <sport_key> <begin> <end>
        [--limit-days N] [--dry-run]
例:python scripts/backfill_pinnacle_close.py 英超 soccer_epl 2024-08-01 2024-10-31
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
import time

from dotenv import load_dotenv

load_dotenv(dotenv_path="/Users/ninoo/Nutmeg/.env")

from nutmeg.v4.data.sources.odds_api_history import (  # noqa: E402
    fetch_historical,
    parse_pinnacle_close,
)
from nutmeg.v4.observation.pinnacle_close_history import record_close  # noqa: E402

DB = "data/v4_jingcai_history.db"


def _match_days(league_cn: str, begin: str, end: str) -> list[str]:
    with sqlite3.connect(DB) as c:
        rows = c.execute(
            "SELECT DISTINCT close_date FROM jingcai_odds_history "
            "WHERE league_cn=? AND close_date BETWEEN ? AND ? ORDER BY close_date",
            (league_cn, begin, end)).fetchall()
    return [r[0] for r in rows]


def _floor30(iso: str) -> dt.datetime:
    """Floor an ISO commence time to its 30-min bucket start (UTC-aware)."""
    d = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return d.replace(minute=(d.minute // 30) * 30, second=0, microsecond=0)


def _snap_at(sport: str, iso: str,
             markets: str = "h2h,totals") -> tuple[list[dict], str | None, int]:
    """(matches, snapshot_ts, cost). matches only where commence >= snapshot_ts (pre-KO).
    ``markets='h2h'`` halves the credit cost (10 vs 20) for 1X2-only confirmatory runs
    — drops O/U, so HHAD DC reconstruction is unavailable, but HAD CLV is unaffected."""
    snap = fetch_historical(sport, iso, markets=markets)
    if not snap:
        return [], None, 0
    ts = snap.get("timestamp")
    cost = int(snap.get("_cost") or 0)
    rows = [r for r in parse_pinnacle_close(snap) if (r.get("commence_time") or "") >= (ts or "")]
    return rows, ts, cost


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    league_cn, sport, begin, end = sys.argv[1:5]
    dry = "--dry-run" in sys.argv
    limit_days = 0
    if "--limit-days" in sys.argv:
        limit_days = int(sys.argv[sys.argv.index("--limit-days") + 1])
    markets = "h2h" if "--h2h-only" in sys.argv else "h2h,totals"

    days = _match_days(league_cn, begin, end)
    if limit_days:
        days = days[:limit_days]
    print(f"{league_cn}/{sport}: {len(days)} 比赛日 {begin}→{end}  dry={dry}")
    # pass1 每天看未来 ~2 周 upcoming → 桶会跨多天且重叠。全局去重:每个 kickoff 桶只抓一次
    # (按真实 commence,不按竞彩日 → 自动兼容竞彩/UTC 日期错位,不漏场也不重复付费)。
    seen: set[str] = set()
    spent = stored = 0
    for d in days:
        # pass1: 当日 T00:00 → 各场 kickoff(commence_time,含未来 ~2 周)
        rows0, ts0, c0 = _snap_at(sport, f"{d}T00:00:00Z", markets)
        spent += c0
        buckets = sorted({_floor30(r["commence_time"]) for r in rows0 if r.get("commence_time")})
        snaps = [(b - dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ") for b in buckets]
        new_snaps = [s for s in snaps if s not in seen]
        if dry:
            print(f"  {d}: {len(rows0)}场·{len(buckets)}桶·新{len(new_snaps)} (cost {c0})")
            seen.update(snaps)
            continue
        for r in rows0:  # 早盘先存(pass2 更贴近会覆盖)
            stored += record_close(DB, r, snapshot_utc=ts0 or "")
        # pass2: 逐「未抓过」的桶 (桶起−5min) 取紧收盘
        for snap in new_snaps:
            seen.add(snap)
            rows, ts, c = _snap_at(sport, snap, markets)
            spent += c
            for r in rows:
                record_close(DB, r, snapshot_utc=ts or "")
            time.sleep(0.3)
        print(f"  {d}: {len(rows0)} 场 · {len(buckets)} 桶(新 {len(new_snaps)})· 累计 cost {spent}")
    print(f"完成: 存 {stored} 场 · 总 cost {spent} credits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
