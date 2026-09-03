"""nutmeg-book-consensus-review — 多书商共识层的**事后**复盘。

## 它回答的唯一问题

这一层存在的理由是:**「Pinnacle 这次的移动是真信息,还是它一家的抖动?」**
本工具在**已结算**的比赛上回头验它:当 Pinnacle 和 24 家共识分歧时,**谁更接近真相**?

⛔ 它**不**回答「多书商能不能赚钱」—— 那需要一个「按共识下注」的人口,而共识层
是 ⛔ 只显示不判闸的(支持样本 63 场全世界杯,人口偏斜)。本工具只量**准确度**。

## 🚨 三条设计纪律(都是本仓踩出来的)

1. **口径同源:共识直接调生产的 `_attach_book_consensus`,一行都不复刻。**
   复刻会在生产改口径时静默分叉;而这一层刚刚才因为「比例归一 vs WPO」两把尺子
   并排吃过亏。⇒ 本文件里没有任何 de-vig / median / min 的实现。
2. **样本不够就拒绝出聚合数,而不是出一个带大误差棒的数。**
   `_MIN_N_FOR_AGGREGATE` 以下只列逐场明细并打印「还差多少场」。
   (本仓反复的教训:一个 N=4 的百分比会被记住,而它的置信区间不会。)
3. **人口逐层报**,不只报最终数 —— 「有快照 → 有竞彩SP → 已结算」每一层剩几场
   都要看得见,否则「没有」和「没去看」分不开。

## ⏰ 为什么现在几乎没数据

`book_snapshots` 是 **2026-09-01 才建的 forward-only 表**,最早的比赛日就是 09-01。
2026-09-03 实测:已结算 ∩ 有竞彩SP = **4 场**(同期竞彩已结算 201 场 ⇒ 覆盖 2.0%)。
⛔ 补不回来:`odds_api` 缓存每个键只留最新一份,两周前的多书商报价已被覆盖;
500.com 那个历史档案是**皇冠单家**不是多书商;Odds API 历史端点单价 20 credit
且空窗返回错数据 —— 为一个不判闸的显示层花几百 credit,性价比不成立。
⇒ 正确做法是**等采集跑满**(`5249217` 放宽了采集闸),两周后自然有 200+ 场。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys

#: 低于这个场次数**不出任何聚合数字**。
#: ⚠️ 不是拍的:这一层要测的效应量级是「Pinnacle 与共识的分歧」,实测中位 0.44pp
#: (见 `multi-book-consensus-vs-single-anchor`)。要在 Brier 上把 0.005 量出来,
#: 配对检验大约需要 N≈150 场。50 是「能看出方向、但仍不许下结论」的下限。
_MIN_N_FOR_AGGREGATE = 50

_LABELS = ("主胜", "平局", "客胜")


def _en_league(label: str | None) -> str:
    """竞彩中文缩写 → V4 EN 联赛码(`SPORT_KEYS` 用的那套)。

    🚨 **两个写入方两套词汇**:`jingcai_sp.league` 由 sporttery cron 写的是竞彩中文
    缩写(英冠/日职/巴甲),而 `odds_api.SPORT_KEYS` 按 EN 码索引 ⇒ 不转换的话
    `_attach_book_consensus` 第一步就把每一场标成 `bk_unavailable`,而那看起来
    和「Odds API 没有这项赛事」**一模一样**(我第一版就这么静默丢了全部 4 场)。

    ⚠️ 反查 `league_labels._EN_TO_CN`(唯一那张表),并**断言它是双射** ——
    将来若有人加一条让两个 EN 码映到同一个中文名,这里会当场炸而不是静默取错一个。
    ⚠️ 转不出来就原样返回(fail-open):`SPORT_KEYS` 那边本来就会把它标成
    「未接入」,那是**正确**的降级。
    """
    from nutmeg.v4.data.league_labels import _EN_TO_CN
    global _CN_TO_EN
    if _CN_TO_EN is None:
        assert len(set(_EN_TO_CN.values())) == len(_EN_TO_CN), (
            "🚨 `_EN_TO_CN` 不再是双射 —— 反查会静默取错一个 EN 码")
        _CN_TO_EN = {cn: en for en, cn in _EN_TO_CN.items()}
    if not label:
        return ""
    from nutmeg.v4.data.league_labels import canonical_league
    return _CN_TO_EN.get(canonical_league(label), label)


#: `_en_league` 的缓存(建一次并断言双射)。
_CN_TO_EN: dict[str, str] | None = None


def _load(db: str, since: str | None, until: str | None) -> tuple[list, dict]:
    """→ (逐场结果, 人口漏斗)。共识由生产函数挂上,本文件不算。"""
    from nutmeg.v4.api import routes
    from nutmeg.v4.api.schemas import SinglePrediction

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    where = ["market='had'", "ft_outcome IS NOT NULL",
             "jc_home IS NOT NULL", "psc_home IS NOT NULL"]
    args: list = []
    if since:
        where.append("match_date >= ?"); args.append(since)
    if until:
        where.append("match_date <= ?"); args.append(until)
    rows = [dict(zip(
        ("match_date", "league", "home_team", "away_team", "jc_home", "jc_draw",
         "jc_away", "psc_home", "psc_draw", "psc_away", "ft_outcome"), r, strict=True))
        for r in conn.execute(
            "SELECT match_date, league, home_team, away_team, jc_home, jc_draw, jc_away,"
            " psc_home, psc_draw, psc_away, ft_outcome FROM jingcai_sp "
            f"WHERE {' AND '.join(where)} ORDER BY match_date", args)]
    conn.close()

    # ⭐ 共识**由生产函数挂**:构造 SinglePrediction 喂给 `_attach_book_consensus`。
    #    这样口径永远和面板一致 —— 生产哪天换了去vig,这里跟着换,不会分叉。
    import datetime as dt
    preds = []
    for r in rows:
        preds.append(SinglePrediction(
            date=dt.date.fromisoformat(r["match_date"]), league=_en_league(r["league"]),
            home_team=r["home_team"], away_team=r["away_team"],
            lambda_home=1.0, lambda_away=1.0,
            p_home_1x2=1 / 3, p_draw_1x2=1 / 3, p_away_1x2=1 / 3,
            jc_home=r["jc_home"], jc_draw=r["jc_draw"], jc_away=r["jc_away"]))
    # 🚨 **不能用 `os.environ.setdefault`** —— 环境变量若已设(daemon 环境、或同进程里
    #    上一次调用),`--db` 会被**静默忽略**,于是这里读的是另一个库而报告照常打印。
    #    (这个 bug 是端到端测试抓出来的:单测 `_en_league` 本身永远发现不了。)
    #    ⇒ 显式覆盖那个 sink,用完还原。
    _orig = routes._observation_db_path
    routes._observation_db_path = lambda: db
    try:
        routes._attach_book_consensus(preds)
    finally:
        routes._observation_db_path = _orig

    # 🚨 漏斗**从生产结果反推**,不另写一套 join。
    #    第一版我用 `_norm_team` 精确相等数「有快照」,而生产用 `same_team`(四级判据)
    #    ⇒ 数出「有快照 4 场、过闸 16 场」这种后一层比前一层大的自相矛盾。
    #    同一个错误我今天早些时候在另一处也犯过:**用一个连法去给另一个连法的结果贴标签**。
    funnel = {
        "竞彩已结算(有 SP + 有 Pinnacle 锚)": len(preds),
        "  − 联赛未接入多书商源": -sum(1 for p in preds if p.bk_unavailable),
        "  − 有快照但队名没连上": -sum(1 for p in preds if getattr(p, "bk_no_match", False)),
        "  − 那天没快照 / 家数不过闸": -sum(
            1 for p in preds if not p.bk_consensus and not p.bk_unavailable
            and not getattr(p, "bk_no_match", False)),
    }
    from nutmeg.v4.model.devig import devig_1x2
    out = []
    for r, p in zip(rows, preds, strict=True):
        if not p.bk_consensus:
            continue
        pin = devig_1x2(r["psc_home"], r["psc_draw"], r["psc_away"])
        if not pin:
            continue
        out.append({**r, "pin": list(pin), "cons": p.bk_consensus,
                    "low": p.bk_low, "spread": p.bk_spread, "n_books": p.bk_n,
                    "captured_at": p.bk_captured_at})
    funnel["= 可复盘"] = len(out)
    # ⚠️ 自洽断言:漏斗必须真的加得起来,否则它在撒谎(第一版就在撒谎)。
    assert sum(funnel.values()) - funnel["= 可复盘"] == funnel["= 可复盘"], (
        f"🚨 漏斗对不上:{funnel}")
    return out, funnel


def _fmt(m: dict) -> list[str]:
    """逐场明细 —— 样本少的时候这才是唯一有信息的东西。"""
    y = m["ft_outcome"]
    sp = (m["jc_home"], m["jc_draw"], m["jc_away"])
    lines = [
        f"  {m['match_date']}  [{m['league'] or '?'}] "
        f"{m['home_team']} vs {m['away_team']}   赛果 {_LABELS[y]}"
        f"   ({m['n_books']} 家,快照 {(m['captured_at'] or '')[:16]})",
        "      腿     竞彩SP   Pinnacle    共识    最保守   离散    EV(单锚)  EV(共识)",
    ]
    for i, lab in enumerate(_LABELS):
        hit = " ←中" if i == y else ""
        ev_p = m["pin"][i] * sp[i] - 1 if sp[i] else None
        ev_c = m["cons"][i] * sp[i] - 1 if sp[i] else None
        lines.append(
            f"      {lab}   {sp[i]:6.2f}   {m['pin'][i] * 100:6.2f}%  "
            f"{m['cons'][i] * 100:6.2f}%  {m['low'][i] * 100:6.2f}%  "
            f"{m['spread'][i]:5.2f}pp  "
            f"{ev_p * 100:+7.1f}%  {ev_c * 100:+7.1f}%{hit}")
    d = abs(m["pin"][y] - m["cons"][y]) * 100
    who = "共识" if m["cons"][y] > m["pin"][y] else "Pinnacle"
    lines.append(f"      ⇒ 命中腿上 {who} 给的 P 更高,两者差 {d:.2f}pp")
    return lines


def analyze(matches: list) -> dict:
    """⭐ 只算**准确度**,不算 ROI(共识不判闸 ⇒ 没有「按共识下注」的人口)。"""
    closer = sum(1 for m in matches if m["cons"][m["ft_outcome"]] > m["pin"][m["ft_outcome"]])
    brier_p = sum(sum((m["pin"][i] - (i == m["ft_outcome"])) ** 2 for i in range(3))
                  for m in matches)
    brier_c = sum(sum((m["cons"][i] - (i == m["ft_outcome"])) ** 2 for i in range(3))
                  for m in matches)
    n = len(matches)
    return {"n": n, "共识在命中腿上更高": closer,
            "Brier_单锚": brier_p / n if n else None,
            "Brier_共识": brier_c / n if n else None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="多书商共识 vs Pinnacle 单锚 —— 事后复盘")
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--since", help="比赛日下界 YYYY-MM-DD")
    ap.add_argument("--until", help="比赛日上界 YYYY-MM-DD")
    ap.add_argument("--detail", action="store_true", help="逐场明细(样本少时默认就开)")
    a = ap.parse_args(argv)

    matches, funnel = _load(a.db, a.since, a.until)

    print("=" * 78)
    print("多书商共识复盘 —— 「Pinnacle 是不是在自说自话」的事后检验")
    print("=" * 78)
    print("\n人口漏斗(每一层都报,否则「没有」和「没去看」分不开):")
    for k, v in funnel.items():
        print(f"   {k:26s} {v:4d}")

    n = len(matches)
    if not n:
        print("\n⏰ 可复盘人口为 0。`book_snapshots` 是 2026-09-01 才建的 forward-only 表,")
        print("   在那之前没有多书商快照,而且**补不回来**(缓存每键只留最新一份)。")
        print("   ⇒ 等采集跑满即可,不需要做任何事。")
        return 0

    if a.detail or n < _MIN_N_FOR_AGGREGATE:
        print(f"\n逐场明细({n} 场):")
        for m in matches:
            print()
            print("\n".join(_fmt(m)))

    if n < _MIN_N_FOR_AGGREGATE:
        # 🚨 拒绝出聚合数 —— 一个 N=4 的百分比会被记住,而它的置信区间不会。
        print(f"\n{'=' * 78}")
        print(f"🚨 **不出聚合数字**:N={n} < {_MIN_N_FOR_AGGREGATE}。")
        print(f"   还差 {_MIN_N_FOR_AGGREGATE - n} 场才到「能看方向」的下限;")
        print("   而要把 Brier 上 0.005 的差异测**显著**,配对检验约需 N≈150 场。")
        print("   ⛔ 这不是「样本小、姑且一看」—— 在这个量级上任何百分比都是噪声。")
        print("   ⏰ 采集闸已于 2026-09-03 放宽(`5249217`),覆盖率会从「每天几十场」")
        print("      变成全盘面 ⇒ 约两周后自然到 200+ 场,那时再跑这条命令。")
        return 0

    r = analyze(matches)
    print(f"\n{'=' * 78}")
    print(f"聚合(N={r['n']} 场):")
    print(f"   命中腿上共识给的 P 更高: {r['共识在命中腿上更高']}/{r['n']}"
          f" = {r['共识在命中腿上更高'] / r['n'] * 100:.1f}%   (50% = 无差别)")
    print(f"   Brier(越小越准)  单锚 {r['Brier_单锚']:.4f}  vs  共识 {r['Brier_共识']:.4f}")
    print("\n⚠️ 这是**准确度**不是盈利:共识 ⛔ 只显示不判闸,没有「按共识下注」的人口。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
