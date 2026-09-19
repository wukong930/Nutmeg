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

from nutmeg.v4.data.odds_source_aliases import ODDS_SOURCE_ALIASES as _TABLE

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
            side[(lg, _slot(ko))].add((h, a))
    return g, cl, names


#: 🚨 **这个截断是承重的,不是格式化。** 见 `docs/kickoff_utc_dual_format_2026-08-14.md`。
#:
#: `odds_snapshots.kickoff_utc` 有**三种**字面,同一时刻写法不同:
#:   A `2026-07-01T16:00:00Z`      ← closing(Odds API commence_time 直抄,4,856 行)
#:   B `2026-06-13T12:00:00+00:00` ← 其余 5 个生产者(API-Football)
#:   C `2026-06-30 21:00:00+00`    ← polymarket_gaps(空格分隔;当前不在本表)
#: ⇒ `a.kickoff_utc = b.kickoff_utc` **永不成立**(实测:同一 join 不带它 144,686 行、
#:   带它 **0 行**)。本脚本是全仓**仅有的两处**真跨这条边界做等值配对的地方之一。
#:
#: ⭐ 安全**完全来自这个截断落在不变区间内**(A/B 共享前 19 位 `YYYY-MM-DDTHH:MM:SS`),
#:   不来自同源。变异检验(2026-08-14):
#:       [:16] → 别名 7 条   ·  [:19] → 7 条  ·  裸 ko → **0 条**  ·  [:20] → **0 条**
#:   悬崖精确落在第 20 位。而裸字面那一栏**不报错**,打印「别名 0 条 · 冲突 0 条」——
#:   与「两个源本来就同名」**完全同形**。⇒ 一次无辜的重构能静默关掉它,
#:   而它下游挂着 CLV 锚的 **31.9%**。
#: ⇒ 护栏是 `tests/v4/test_kickoff_slot_normalisation.py` 的**正负双对照夹具**,
#:   不是「源码里必须出现 [:16]」那种语法断言(那族会假红,最后被删掉)。
def _slot(ko: str) -> str:
    """开球时刻 → 跨三种字面通用的槽位键(分钟精度)。"""
    return ko.replace(" ", "T")[:16]


def derive(db: str = DB) -> tuple[dict, dict, list, list, set]:
    """→ (别名 {(联赛, closing名): (gather名, 证据数)}, 冲突, 未收敛, 单侧联赛, 种子键集)。

    ⚠️ 2026-08-14 修:签名与 docstring 此前都写「3 元组」,实际 `return` 了 **4 个**
    (末位 `one_sided`)。调用方按 3 个解包会 `ValueError` —— 属于「响的」那种漂移,
    不是静默的,所以危害有限;但既然碰到了就一起修。
    ⚠️ 2026-09-19 加第 5 位 `seeded`(跨联赛种子键集,仅供输出标注)——
    **同一处签名第二次变长了**,所以这次签名/docstring/调用方一起改。
    """
    g, cl, names = _load(db)
    ev: dict = collections.defaultdict(collections.Counter)

    def learn(lg, cp, gp):
        ev[(lg, cp[0])][gp[0]] += 1
        ev[(lg, cp[1])][gp[1]] += 1

    both = set(g) & set(cl)

    # ⓪ 跨联赛种子(2026-09-19)。同一 closing 名在**别的联赛**已建键 → T,
    #    且 T **确实出现在本联赛 gather 侧** ⇒ 同一俱乐部、同一正典目标,只是缺
    #    `(本联赛, 名)` 这把精确键。09-10 那批的 `('UCL','Bodø/Glimt')` 走的就是
    #    这条证据(注释里写作「别联赛已有别名 + 本联赛 gather 侧存在」),这里把它
    #    从手工变成探测器的一部分。
    # ⚠️ 这条**引入了表→推导的回授**:别处一条错键会顺着传播。两道闸挡它 ——
    #    ① 必须「T 在本联赛 gather 侧真的出现过」(独立于那条键的验证);
    #    ② 输出里单独标 `种子`,证据类型在决策点可见,不和共现证据混成一团。
    seeded: set = set()
    gather_names: dict = collections.defaultdict(set)
    for (lg, _slotkey), ps in g.items():
        for h, a in ps:
            gather_names[lg].update((h, a))
    closing_names: dict = collections.defaultdict(set)
    for (lg, _slotkey), ps in cl.items():
        for h, a in ps:
            closing_names[lg].update((h, a))
    by_name: dict = collections.defaultdict(set)
    for (_lg, n), v in _TABLE.items():
        by_name[n].add(v)
    for lg, ns in closing_names.items():
        for n in ns:
            if (lg, n) in _TABLE:
                continue
            tgt = {v for v in by_name.get(n, ()) if v in gather_names[lg]}
            if len(tgt) == 1:
                ev[(lg, n)][next(iter(tgt))] += 1
                seeded.add((lg, n))

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
                    # ⭐ 2026-09-19:锚有**两种**,此前只认第一种 ⇒ UEL 16 条推不出来。
                    #    ① 学到的别名;② **两侧逐字相同**(`Celtic` vs `Celtic`)。
                    #    ②和①一样硬:一支队在同一 (联赛,开球时刻) 只打一场,所以
                    #    只要 `len(m) == 1`,拿它钉另一侧就是唯一解。
                    #    ⛔ 这不是放宽成「名字相似」—— 要求的是**逐字相等**。
                    known = ev.get((k[0], cp[i]))
                    if known and len(known) == 1:
                        anchor = next(iter(known))
                    elif any(gp[i] == cp[i] for gp in g[k]):
                        anchor = cp[i]
                    else:
                        continue
                    m = [gp for gp in g[k] if gp[i] == anchor]
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
            # ⚠️ 2026-09-19:也要排掉**已经在表里**的。种子键一旦落表,⓪ 那条就
            #    `continue` 跳过它,于是本轮推不回来 ⇒ 它会被重新列进「未收敛」,
            #    也就是**报警指向已经修好的东西**(同 [[unmapped-banner-silences-not-fixes]]
            #    那条横幅点已修好队名的坑)。判据要问「它现在解不解得出」,
            #    不是「本轮推没推出来」。
            if (lg, n) not in alias and (lg, n) not in _TABLE:
                pending.append((lg, n))
    return alias, conflict, pending, one_sided, seeded


def main() -> int:
    alias, conflict, pending, one_sided, seeded = derive()
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
