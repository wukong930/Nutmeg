#!/usr/bin/env python
"""竞彩历史回填 · 涓流(gentle trickle,防 403)。

每次跑跑一个小日期窗口(7 天),cursor 前进;到末尾绕回起点 → skip_existing 让 re-sweep
只补此前被节流丢的缺口(cheap)。温柔限速(sleep 2s)+ 小批,避免持续抓触发 sporttery
的 403 IP 封。装为 hourly launchd `com.nutmeg.jingcai_history_trickle`;几天覆盖 prereg §H
主窗口 2021-08→2025-07 × 13 受训联赛。覆盖齐(连续 sweep 增量≈0)后 bootout 停用。

`记忆 jingcai-fixedbonus-history-endpoint` · `docs/autumn_prereg_analysis_plan.md §H`。
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

# 中国站:清代理(净 launchd 环境或本机代理都够不着/会干扰)。同 sporttery 其它 cron。
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)

from nutmeg.v4.cli.ingest_jingcai_history import backfill  # noqa: E402
from nutmeg.v4.data.league_labels import TRAINED_LEAGUES_CN  # noqa: E402

DB = "data/v4_jingcai_history.db"
CURSOR = Path("data/jingcai_history_cursor.txt")
BEGIN, END = dt.date(2021, 8, 1), dt.date(2025, 7, 31)
WINDOW_DAYS = 7


def main() -> int:
    try:
        cur = dt.date.fromisoformat(CURSOR.read_text().strip())
    except (OSError, ValueError):
        cur = BEGIN
    if cur > END:  # 绕回起点 → re-sweep 补缺口(skip_existing = 已入库跳过,便宜)
        cur = BEGIN
    w_end = min(cur + dt.timedelta(days=WINDOW_DAYS - 1), END)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[trickle {stamp}] 窗口 {cur}→{w_end}")
    stat = backfill(DB, cur.isoformat(), w_end.isoformat(), leagues=TRAINED_LEAGUES_CN,
                    sleep=2.0, limit=0, dry_run=False, skip_existing=True, chunk_days=7)
    print(f"[trickle {stamp}] {stat}")
    CURSOR.write_text((cur + dt.timedelta(days=WINDOW_DAYS)).isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
