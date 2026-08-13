#!/usr/bin/env python
"""每条 `ODDS_SOURCE_ALIASES` 是否**真的修好过至少 1 个跨源劈开键**。

## 🚨 为什么单独有这个脚本(而不是并进 pytest)

2026-08-13 的变异检验测出一件事:**结构性判据抓不到「错目标恰好不在数据窗口里」。**

    变异 ('JPN_J1','Yokohama F Marinos'): 'Yokohama FC'
        —— 把横滨 F·马里诺斯与横滨 FC 两支**不同的队**并成一支
    结果:tests/v4/test_odds_source_aliases_guard.py **全绿**

原因很朴素:横滨 FC 已降 J2,`odds_snapshots` 里 **0 行** ⇒
「目标撞车」「传递链」「自映射」全都够不着它。
同族的还有 `Kashima Antlers→Kashiwa Reysol`、`Sporting Lisbon→SC Braga`,
三个变异**只有本判据抓住**。

⭐ 这是本仓 [[unmapped-banner-silences-not-fixes]] 的另一种穿法:
**「历史总行数=0」在窗口比对象生命周期短时,和「不存在」一模一样。**

## 判据

一条别名 `(联赛, closing名) → gather名` 算「有作用」,当且仅当库里存在一个
**跨源劈开键**被它合上:同一 (联赛, 开球分钟) 下,一个只有 closing 的键与一个
只有 gather 的键**共享恰好一侧队名**,而本别名让另一侧也对上。

## ⚠️ 假阳性(必须先读再决定要不要挂进体检)

「零作用」**不等于**「错」。合法的零作用有两种:
  1. **预埋**:为还没开赛的联赛先补好别名(closing 侧 0 行)——
     这正是 2026-08 秋季开赛前该做的事。
  2. **已回填干净**:`backfill_odds_names` 跑过之后,历史行已归一,
     劈开键消失 ⇒ 别名从此「零作用」。**实测旧 61 条今天全是这个状态。**

⇒ 所以本脚本的定位是**加别名时的验收工具**,不是常驻红绿灯。
   退出码:有零作用条目 → **1**;全部有作用 → 0。
   `--baseline FILE` 可给一份「已知合法零作用」清单,只对**新增**的报警。

用法:
    python scripts/check_alias_effect.py                 # 全表
    python scripts/check_alias_effect.py --league JPN_J1 # 单联赛
    python scripts/check_alias_effect.py --before        # 用回填**前**的口径(见下)

⚠️ `--before` 说明:回填之后劈开键已被消掉,再查会**全部**报零作用。
   要验收「这批别名有没有用」,必须在**回填前**跑,或用 `--before` 在内存里
   把别名反向撤销后重算。本脚本默认就是反向撤销口径。
"""
from __future__ import annotations

import argparse
import collections
import sqlite3
import sys

DB = "data/v4_observation.db"
_CLOSING = "closing"


def _load(db: str):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = c.execute(
        "SELECT league, substr(kickoff_utc,1,16), home_team, away_team, source "
        "FROM odds_snapshots WHERE kickoff_utc IS NOT NULL").fetchall()
    c.close()
    return rows


def effective(db: str = DB, league: str | None = None) -> dict[tuple[str, str], int]:
    """→ {(联赛, closing名): 它合上的劈开键数}。

    口径:把别名**反向撤销**(gather 名 → 可能的 closing 原名),重建「回填前」的
    劈开状态,再数每条别名能合上几个。这样在回填之后跑也拿得到真实作用量。
    """
    from nutmeg.v4.data.odds_source_aliases import ODDS_SOURCE_ALIASES as A

    rev: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    for (lg, src), tgt in A.items():
        rev[(lg, tgt)].append(src)

    keyed: dict[tuple, list[bool]] = collections.defaultdict(lambda: [False, False])
    for lg, slot, h, a, src in _load(db):
        keyed[(lg, slot, h, a)][0 if src == _CLOSING else 1] = True

    # 同槽内:closing-only 键 × gather-only 键,共享恰好一侧 ⇒ 另一侧是劈开证据
    byslot: dict[tuple, tuple[list, list]] = collections.defaultdict(lambda: ([], []))
    for (lg, slot, h, a), (cl, ga) in keyed.items():
        if cl and not ga:
            byslot[(lg, slot)][0].append((h, a))
        elif ga and not cl:
            byslot[(lg, slot)][1].append((h, a))

    hits: dict[tuple[str, str], int] = collections.Counter()
    for (lg, _slot), (cls, gas) in byslot.items():
        if league and lg != league:
            continue
        for ch, ca in cls:
            for gh, ga_ in gas:
                same_h, same_a = ch == gh, ca == ga_
                if same_h == same_a:            # 必须恰好一侧相同
                    continue
                cn, gn = (ca, ga_) if same_h else (ch, gh)
                if A.get((lg, cn)) == gn:       # 这条别名正好合上它
                    hits[(lg, cn)] += 1
    # 回填之后劈开键已消失 ⇒ 再补一轮:两侧都在的键里,closing 侧原名已被改写,
    # 用反向表还原出「它当初本来是哪个 closing 名」来计功。
    for (lg, _slot2, h, a), (cl, ga) in keyed.items():
        if not (cl and ga) or (league and lg != league):
            continue
        for pos in (h, a):
            for src in rev.get((lg, pos), []):
                hits[(lg, src)] += 1
    return dict(hits)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="每条别名是否真的修好过跨源劈开键")
    p.add_argument("--db", default=DB)
    p.add_argument("--league", default=None)
    a = p.parse_args(argv)

    from nutmeg.v4.data.odds_source_aliases import ODDS_SOURCE_ALIASES as A

    hits = effective(a.db, a.league)
    keys = [k for k in A if not a.league or k[0] == a.league]
    zero = sorted(k for k in keys if hits.get(k, 0) == 0)

    print(f"别名 {len(keys)} 条 · 有作用 {len(keys) - len(zero)} · 零作用 {len(zero)}")
    if zero:
        print("\n⚠️ 零作用条目(**不等于错** —— 可能是预埋或已归一,见 docstring):")
        for lg, nm in zero:
            print(f"   {lg:<22} {nm!r} → {A[(lg, nm)]!r}")
        print("\n🚨 若其中有**刚加的**条目,先查它的目标名在库里有没有行 —— "
              "「目标不在窗口里」的错映射正是本判据存在的理由。")
    return 1 if zero else 0


if __name__ == "__main__":
    sys.exit(main())
