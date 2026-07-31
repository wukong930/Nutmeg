#!/usr/bin/env python
"""一次性:回填 2025-07-28 → 2026-06-10 的竞彩历史缺口。

**这个洞是怎么来的**:`scripts/jingcai_history_trickle.py` 的 `END` 硬编码成
2025-07-31(预注册 §H 的窗口),跑完就再没往前走;而观测库 `jingcai_sp` 从
2026-06-11 才开始 ⇒ 中间 ~10.5 个月两边都没有。2026-05-30 那场神户 5:0 鹿岛
就掉在洞里(owner 2026-07-31 问「当时 EV 多少」时发现)。

**为什么不直接一把梭**:涓流当初的设计理由是「避免持续抓触发 sporttery 的
403 IP 封」——它是 7 天窗/小时,占空比 ~3%。缺口有 2,600 场,连续跑 ≈100 分钟
是 30× 的占空比。这里折中:**按月分批 + 批间静默 + 403 熔断**,并把每批的
统计打出来,坏了能当场看见而不是跑完才发现。

⚠️ 中国站:必须清代理(6 个变量,不是 4 个 —— `ALL_PROXY/all_proxy` 也算)。
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)

from nutmeg.v4.cli.ingest_jingcai_history import backfill  # noqa: E402
from nutmeg.v4.data.league_labels import TRAINED_LEAGUES_CN  # noqa: E402

DB = "data/v4_jingcai_history.db"
BEGIN, END = dt.date(2025, 7, 28), dt.date(2026, 6, 10)
# 联赛范围:默认 13 受训联赛(第一遍)。传 `all` 抓全部 —— ⚠️ 缺口里 **45%**
# (2,161/4,761)是北欧/韩职/巴甲/杯赛这类**非受训但竞彩真在卖**的场次,
# 只跑 trained 会留下一个看不见的半缺口(第一遍就是这么留的)。
#
# ⚠️ 「全部」必须是 **None**,不能是字符串 "all"。`backfill` 里的过滤是
# `canonical_league(...) not in leagues` —— 传字符串会退化成**子串判断**
# (「西甲」不是 "all" 的子串)⇒ 全部被静默过滤,`in_scope=0`、零报错、
# 日志看着像「这段没有比赛」。踩过一次(2026-07-31 第二轮回填首批)。
LEAGUES = None if len(sys.argv) > 1 and sys.argv[1] == "all" else TRAINED_LEAGUES_CN
CHUNK_DAYS = 30          # 按月分批 —— 批小到坏了只丢一批,大到不至于跑一整天
PAUSE_S = 90.0           # 批间静默,把占空比压到 ~80% 以下
SLEEP_S = 2.0            # 场间限速,沿用涓流实测无 403 的节奏
_ABORT_FAIL_RATE = 0.30  # 单批失败率 >30% ⇒ 大概率被限流,停下来别硬撞


def main() -> int:
    cur, n_chunk, tot = BEGIN, 0, {"in_scope": 0, "fetched": 0, "stored_rows": 0,
                                   "skipped": 0, "failed": 0}
    t0 = time.time()
    while cur <= END:
        w_end = min(cur + dt.timedelta(days=CHUNK_DAYS - 1), END)
        n_chunk += 1
        st = backfill(DB, cur.isoformat(), w_end.isoformat(),
                      leagues=LEAGUES, sleep=SLEEP_S, limit=0,
                      dry_run=False, skip_existing=True, chunk_days=CHUNK_DAYS)
        for k in tot:
            tot[k] += int(st.get(k, 0))
        el = int(time.time() - t0)
        print(f"[批{n_chunk:02d}] {cur}→{w_end}  "
              f"in_scope={st.get('in_scope',0):>4} fetched={st.get('fetched',0):>4} "
              f"rows={st.get('stored_rows',0):>5} skip={st.get('skipped',0):>4} "
              f"fail={st.get('failed',0):>3}   累计 rows={tot['stored_rows']:,} "
              f"用时 {el//60}m{el%60:02d}s", flush=True)

        # 403 熔断:抓了不少却大半失败 ⇒ 被限流,停。**不重试、不加速**。
        tried = int(st.get("fetched", 0)) + int(st.get("failed", 0))
        if tried >= 20 and int(st.get("failed", 0)) / tried > _ABORT_FAIL_RATE:
            print(f"🚨 熔断:本批失败率 {st.get('failed')}/{tried} > {_ABORT_FAIL_RATE:.0%}"
                  f" —— 疑似 403 限流,已停在 {w_end}。等几小时再从这里续。", flush=True)
            return 2
        cur = w_end + dt.timedelta(days=1)
        if cur <= END:
            time.sleep(PAUSE_S)
    el = int(time.time() - t0)
    print(f"\n✅ 完成 {n_chunk} 批 · {BEGIN}→{END} · {tot} · 总用时 {el//60}m{el%60:02d}s",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
