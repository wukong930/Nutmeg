#!/usr/bin/env python
"""记一条「绿灯但没敢下」—— 全系统**唯一**只有人能提供的前向信号。

## 为什么需要它

`docs/autumn_restart_checklist.md` §1⑧(A-3 冻结带进闸)的启动条件 (a) 是
「**绿灯但 ⏳ 大到不敢下** ≥3 次」。2026-08-13 预检实查:

    recommendation_sessions  145 行 · single_predictions  81 行
    → 两张表都**没有任何字段**在记这件事

⇒ 那个触发条件**结构上永远不可能满足**,而它被写在清单里当「条件项」。
清单会一直显示「等条件」,而条件在等一个没人在记的东西。

⭐ 这是**唯一一条纯人类前向信号**:所有别的量(赔率、盘口、结算)都能事后
从上游重建,只有「你当时看到了什么、为什么没下手」不能。**今天不记就永久没有。**

## 为什么是文本日志而不是加数据库列

⛔ 加列必须**同时**改 DDL 和 `_MIGRATIONS` —— 已存在的表上
`CREATE TABLE IF NOT EXISTS` 是空操作,只改 DDL 会让 INSERT 直接
`no such column` 把 cron 打死(本仓惯例,见 health-check 护栏总账)。
为一条**每周可能只有 0-2 条**的人类记录冒这个险不值得。

`logs/` 被 gitignore ⇒ 数据留本地,不进仓库(与 `delta_calibration_history`
等同惯例)。

## 用法

    python scripts/log_hesitation.py \\
        --match "Bayern vs Dortmund" --league GER_BUNDESLIGA \\
        --leg 让球胜 --ev 7.2 --gap 6.5 --decision skip \\
        --note "凌晨 3 点开球,盘口是 6 小时前的"

最少只要 `--match` 和 `--decision`:

    python scripts/log_hesitation.py --match "Bayern vs Dortmund" --decision skip

`--decision` 三选一:
  · `skip`   看到绿灯但没下(**本工具的主要用途**)
  · `bet`    绿灯且下了 —— 记下来当对照组,否则只有拒绝样本
  · `unsure` 没想清楚

⚠️ **对照组很重要**:只记 `skip` 会得到一堆「我拒绝的都是坏的」——
那是选择偏差不是发现。`bet` 那些同样要记。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

LOG = Path("logs/hesitation.jsonl")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="记一条「绿灯但没敢下」(或下了)——秋季 A-3 的唯一人类信号源")
    p.add_argument("--match", required=True, help='"主队 vs 客队"')
    p.add_argument("--decision", required=True, choices=("skip", "bet", "unsure"),
                   help="skip=没下 · bet=下了(对照组,同样要记) · unsure=没想清")
    p.add_argument("--league", default=None)
    p.add_argument("--leg", default=None, help="胜/平/负/让球胜/让球平/让球负")
    p.add_argument("--ev", type=float, default=None, help="当时面板显示的 EV(%)")
    p.add_argument("--gap", type=float, default=None,
                   help="冻结缺口小时数(封盘到开球),面板 ⏳ 徽章旁边那个")
    p.add_argument("--note", default=None, help="一句话:为什么")
    p.add_argument("--out", default=str(LOG))
    a = p.parse_args(argv)

    rec = {
        # 本地时间带时区 —— 「我什么时候看的」本身是信号(凌晨场 vs 白天场)
        "ts": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "match": a.match,
        "league": a.league,
        "leg": a.leg,
        "ev_pct": a.ev,
        "freeze_gap_h": a.gap,
        "decision": a.decision,
        "note": a.note,
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n = sum(1 for _ in out.open(encoding="utf-8"))
    skips = sum(1 for ln in out.open(encoding="utf-8")
                if json.loads(ln).get("decision") == "skip")
    print(f"✓ 已记入 {out}  (累计 {n} 条 · 其中 skip {skips} 条)")
    # A-3 §1⑧ 的启动条件 (a) 要 ≥3 次 skip。到点了主动说,别让人自己去数。
    if skips == 3:
        print("⭐ skip 已达 3 条 —— autumn_restart_checklist §1⑧ 的启动条件 (a) 满足。"
              "\n   ⚠️ 满足的是**启动讨论**的条件,不是「该改判闸了」。A-3 进闸仍须预注册。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
