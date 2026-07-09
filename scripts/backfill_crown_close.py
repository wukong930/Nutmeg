#!/usr/bin/env python
"""500 Crown 历史收盘回填(免费,C1 δ 估计 / §H CLV benchmark)。

按日期范围拉 500 hisdata 静态 XML → 解析 Crown 1X2/让球线/让球1X2/O·U/结果 → 写
`crown_close_history`。gentle 限速(sleep,防 China 站节流)。`fetch_hisdata` 已清代理。
免费 → 不动 Odds API 额度。`记忆 500-historical-odds-archive`。

用法: python scripts/backfill_crown_close.py <begin> <end> [--sleep S]
例:   python scripts/backfill_crown_close.py 2024-08-01 2025-05-31 --sleep 0.8
"""
from __future__ import annotations

import datetime as dt
import sys
import time

from nutmeg.v4.data.sources.five00_history import fetch_hisdata, parse_hisdata
from nutmeg.v4.observation.crown_close_history import record_match

DB = "data/v4_jingcai_history.db"


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    begin, end = sys.argv[1], sys.argv[2]
    sleep = 0.8
    if "--sleep" in sys.argv:
        sleep = float(sys.argv[sys.argv.index("--sleep") + 1])

    b, e = dt.date.fromisoformat(begin), dt.date.fromisoformat(end)
    d, total, days = b, 0, 0
    print(f"500 Crown 回填 {begin}→{end}  sleep={sleep}s")
    while d <= e:
        mr, orr = fetch_hisdata(d.isoformat())
        recs = parse_hisdata(mr, orr)
        n = sum(record_match(DB, r) for r in recs)
        total += n
        if recs:
            days += 1
            print(f"  {d}: {n} 场 (累计 {total})")
        d += dt.timedelta(days=1)
        time.sleep(sleep)
    print(f"完成: {days} 有数据日 · 存 {total} 场 · {begin}→{end}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
