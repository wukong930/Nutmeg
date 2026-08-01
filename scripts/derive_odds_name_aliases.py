#!/usr/bin/env python
"""从 `odds_snapshots` 的**赛事共现**推导「closing 拼法 → gather 拼法」别名,
并**探测**尚未收敛的新分裂。

为什么需要它 —— 两个上游对同一支球队用不同英文名:
  · API-Football(走 `cup_market` / `predict_log` = 盘面口径)
  · Odds API   (走 `closing` = 收盘锚)
实测 9 个联赛共 **61** 个名字只在 closing 侧出现。取错边 join 照样不通,
**而且没有任何报错** —— 收盘线静默叠加不上,CLV 少数据,日志全绿。

⚠️ 为什么不用现成的 `to_v4_canonical`:实测 61 个里只有 10 个能 exact 命中,
14 个要靠 **fuzzy**,而 fuzzy 是**猜**(δ join 那次已因同一条红线把它关掉)。
剩 37 个完全解不出。**解析器解决不了这个问题。**

⭐ 用的证据是「同一 (联赛, 开球时刻) 上两个源写的是同一场比赛」:
  ① 两侧各只有 1 场的键 → 直接对位;
  ② 同时刻多场的键 → 若一侧队名已学到,用它唯一钉住另一侧,迭代到不再增长。
一致性闸:同一个 closing 名若在不同证据里指向不同 gather 名 ⇒ **冲突,一律拒绝**。

**方法自带对照组**:两侧本来就同名的球队应当映射到自己。实测 93 条对照全部正确,
这才是敢信它推出的 54 条别名的理由 —— 不是因为看着像。

用法:
    python scripts/derive_odds_name_aliases.py            # 打印当前推导 + 未收敛项
    python scripts/derive_odds_name_aliases.py --emit     # 输出可粘贴的 Python 字面量
"""
from __future__ import annotations

import collections
import sqlite3
import sys

DB = "data/v4_observation.db"
_CLOSING = "closing"          # Odds API 侧;其余 source 一律算 gather(API-Football)


def _load(db: str = DB):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    g: dict = collections.defaultdict(set)
    cl: dict = collections.defaultdict(set)
    names: dict = collections.defaultdict(lambda: collections.defaultdict(set))
    for lg, src, ko, h, a in c.execute(
        "SELECT league, source, kickoff_utc, home_team, away_team FROM odds_snapshots "
        "WHERE league IS NOT NULL"
    ):
        side = cl if src == _CLOSING else g
        names[lg][src].add(h)
        names[lg][src].add(a)
        if ko:
            side[(lg, ko[:16])].add((h, a))
    return g, cl, names


def derive(db: str = DB) -> tuple[dict, dict, list]:
    """→ (别名 {(联赛, closing名): (gather名, 证据数)}, 冲突, 未收敛)。"""
    g, cl, names = _load(db)
    ev: dict = collections.defaultdict(collections.Counter)

    def learn(lg, cp, gp):
        ev[(lg, cp[0])][gp[0]] += 1
        ev[(lg, cp[1])][gp[1]] += 1

    both = set(g) & set(cl)
    for k in both:                                   # ① 无歧义键
        if len(g[k]) == 1 and len(cl[k]) == 1:
            learn(k[0], next(iter(cl[k])), next(iter(g[k])))
    for _ in range(8):                               # ② 靠已知一侧钉另一侧,迭代
        grew = 0
        for k in both:
            if len(g[k]) == 1 and len(cl[k]) == 1:
                continue
            for cp in cl[k]:
                for i in (0, 1):
                    known = ev.get((k[0], cp[i]))
                    if not known or len(known) != 1:
                        continue
                    m = [gp for gp in g[k] if gp[i] == next(iter(known))]
                    if len(m) == 1:
                        before = len(ev)
                        learn(k[0], cp, m[0])
                        grew += len(ev) > before
        if not grew:
            break

    alias, conflict = {}, {}
    for key, cnt in ev.items():
        if len(cnt) == 1:
            name, n = cnt.most_common(1)[0]
            if key[1] != name:                       # 同名的是对照组,不入表
                alias[key] = (name, n)
        else:
            conflict[key] = dict(cnt)

    # 探测:仍只在 closing 侧出现、且没推出别名的 → 需要人看
    pending, one_sided = [], []
    for lg in sorted(names):
        gs, cs = set(), set()
        for src, ns in names[lg].items():
            (cs if src == _CLOSING else gs).update(ns)
        if not gs or not cs:
            # ⚠️ 2026-08-01 —— 这里原来是 `continue`,理由是「只有单侧采集的联赛
            # 不是分裂」。**错了,而且是今天第三次踩同一形状**:单侧的一个主要成因
            # 恰恰是 league 值本身分裂(`soccer_usa_mls` vs `USA_MLS`),于是
            # 「查不出分裂」被当成「没有分裂」,47 行静默漏掉。
            # 现在照报不误 —— 分不出「没有」和「没去看」的探测器不算探测器。
            one_sided.append((lg, "gather" if gs else "closing", len(gs or cs)))
            continue
        for n in sorted(cs - gs):
            if (lg, n) not in alias:
                pending.append((lg, n))
    return alias, conflict, pending, one_sided


def main() -> int:
    alias, conflict, pending, one_sided = derive()
    print(f"别名 {len(alias)} 条 · 冲突 {len(conflict)} 条 · 未收敛 {len(pending)} 条 "
          f"· 单侧联赛 {len(one_sided)} 个\n")
    if "--emit" in sys.argv:
        print("ODDS_SOURCE_ALIASES: dict[tuple[str, str], str] = {")
        for (lg, cn), (gn, n) in sorted(alias.items()):
            print(f'    ({lg!r}, {cn!r}): {gn!r},   # 证据 {n} 场')
        print("}")
        return 0
    for (lg, cn), (gn, n) in sorted(alias.items()):
        print(f"  {lg:<20}{cn:<28}→ {gn:<28}({n} 场)")
    if conflict:
        print("\n⚠️ 冲突(证据自相矛盾,**不许硬填**,先查是不是同名不同队):")
        for k, v in conflict.items():
            print(f"   {k} → {v}")
    if pending:
        print(f"\n⚠️ 未收敛 {len(pending)} 条 —— 共现证据不足,**留空不猜**:")
        for lg, n in pending:
            print(f"   {lg:<20}{n}")
    if one_sided:
        print(f"\n📋 单侧联赛 {len(one_sided)} 个 —— 推不出别名,**但不等于没有分裂**。"
              "\n   先查 league 值本身是不是两套词汇(sport_key vs V4 码):")
        for lg, side, n in one_sided:
            print(f"   {lg:<32}只有 {side:<8}侧 · {n} 个队名")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
