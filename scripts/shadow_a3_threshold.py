"""A-3 影子模式 — 变时 σ_P(h) 门槛 vs 钉死 σ_P,在历史上回放对比(纯只读)。

**为什么是「零风险版」**:A-3 的完整形态是让方差门槛去**判闸**(拦推荐),那要碰
下注规则、须预注册。影子模式只做前两件事 —— 照常算、照常记录,**不改变任何推荐**
—— 于是可以现在就跑、随时看,而不欠任何预注册。

问题背景:冻结缺口(竞彩停售 → 开球,41% 凌晨场中位 6h)期间市场继续走,EV 会漂。
A-1(docs/freeze_gap_measurement_2026-07-18.md)测出漂移**点估无偏、方差真实**:
σ_P(h) = A·h^B。A-2 已把它做成显示用的 ± 带。但**门槛**那一侧还钉死在 σ_P=1.2pp
(≈ h≈4h 的水平)—— 于是凌晨场被低估、临开球被高估。本脚本量化那个误差有多大。

⚠️ **不需要新建表**:`jingcai_sp` 已经存了回放所需的全部输入 ——
  SP = `jc_*` · P = `psc_*` 走 WPO 去vig · h = `kickoff_utc` − `captured_at` ·
  结果 = `ft_outcome`。所以「影子记录」= 随时重放,而不是再养一条写入路径
  (少一条写入路径 = 少一处会和现实漂开的地方)。

⚠️⚠️ **样本极小**。配额耗尽期(2026-06~07)`psc_*` 大面积缺失,四项输入俱全的
行只有几十条。脚本会把 N 打在最显眼处;**N 不够时它报的是「口径差多大」,
不是「哪个门槛更赚钱」** —— 后者要等秋季样本。

用法:
  .venv/bin/python scripts/shadow_a3_threshold.py            # 全部
  .venv/bin/python scripts/shadow_a3_threshold.py --min-h 3  # 只看缺口 ≥3h 的
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import statistics as st
from pathlib import Path

from nutmeg.v4.model.devig import devig_1x2
from nutmeg.v4.model.ev_threshold import (
    BASE_THRESHOLD,
    SIGMA_P,
    variance_adjusted_threshold,
)

REPO = Path(__file__).resolve().parents[1]
DB_URI = f"file:{REPO}/data/v4_observation.db?mode=ro"
LEGS = (("主", "H", 0), ("平", "D", 1), ("客", "A", 2))


def _hours(captured: str, kickoff: str) -> float | None:
    """竞彩快照 → 开球的小时数。解析失败/已开球 → None(不装懂)。"""
    try:
        a = dt.datetime.fromisoformat(captured.replace("Z", "+00:00"))
        b = dt.datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None
    h = (b - a).total_seconds() / 3600
    return h if h > 0 else None


def load_legs(min_h: float) -> tuple[list[dict], dict]:
    """→ (每腿一条的记录, 数据可用性账)。账本是为了不让「空结果」冒充「没差别」。"""
    conn = sqlite3.connect(DB_URI, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT captured_at, kickoff_utc, league, home_team, away_team, "
            "jc_home, jc_draw, jc_away, psc_home, psc_draw, psc_away, ft_outcome "
            "FROM jingcai_sp WHERE market='had' ORDER BY kickoff_utc"
        ).fetchall()
    finally:
        conn.close()

    tally = {"总行": len(rows), "缺 psc": 0, "缺 jc": 0, "缺开球时刻": 0,
             "未结算": 0, "去vig 失败": 0, "h 太小被筛": 0, "可用行": 0}
    out: list[dict] = []
    for r in rows:
        psc = (r["psc_home"], r["psc_draw"], r["psc_away"])
        jc = (r["jc_home"], r["jc_draw"], r["jc_away"])
        if any(x is None for x in psc):
            tally["缺 psc"] += 1
            continue
        if any(x is None for x in jc):
            tally["缺 jc"] += 1
            continue
        if r["ft_outcome"] is None:
            tally["未结算"] += 1
            continue
        h = _hours(r["captured_at"], r["kickoff_utc"])
        if h is None:
            tally["缺开球时刻"] += 1
            continue
        probs = devig_1x2(*psc)
        if not probs:
            tally["去vig 失败"] += 1
            continue
        if h < min_h:
            tally["h 太小被筛"] += 1
            continue
        tally["可用行"] += 1
        for i, (zh, code, oc) in enumerate(LEGS):
            if not (jc[i] and jc[i] > 1.0 and 0 < probs[i] < 1):
                continue
            out.append({
                "赛事": f"{r['home_team']}-{r['away_team']}", "联赛": r["league"],
                "腿": zh, "code": code, "h": h, "p": probs[i], "sp": float(jc[i]),
                "ev": probs[i] * float(jc[i]) - 1.0, "won": r["ft_outcome"] == oc,
            })
    return out, tally


def _thresholds(rec: dict) -> tuple[float, float]:
    """(旧:钉死 σ_P, 新:σ_P(h))。两者只差 σ 的来源,别的一模一样。"""
    old = variance_adjusted_threshold(rec["p"], rec["sp"], sigma_p=SIGMA_P)
    new = variance_adjusted_threshold(
        rec["p"], rec["sp"], hours_to_kickoff=rec["h"], leg=rec["code"])
    return old, new


def report(recs: list[dict], tally: dict) -> None:
    print(f"\n{'═' * 78}\nA-3 影子模式 — σ_P(h) vs 钉死 σ_P={SIGMA_P * 100:.1f}pp")
    print("\n▸ 数据可用性(先看这里 —— 空结果 ≠ 没差别)")
    for k, v in tally.items():
        print(f"    {k:<14}{v:>6}")
    if not recs:
        print("\n  ⚠️ 没有可用腿 —— 本次**什么都没测到**,不是「两个门槛一样」。")
        return
    print(f"    {'可用腿数':<14}{len(recs):>6}")

    hs = [r["h"] for r in recs]
    print(f"\n▸ 冻结缺口 h:中位 {st.median(hs):.1f}h · 范围 {min(hs):.1f}–{max(hs):.1f}h")

    print("\n▸ 门槛口径差(pp。正 = 新门槛更严)")
    print(f"    {'h 档':<12}{'腿数':>6}{'旧门槛':>9}{'新门槛':>9}{'差':>9}")
    for lo, hi, name in ((0, 2, "<2h"), (2, 6, "2-6h"), (6, 24, "6-24h"), (24, 1e9, "≥24h")):
        sub = [r for r in recs if lo <= r["h"] < hi]
        if not sub:
            continue
        pairs = [_thresholds(r) for r in sub]
        o, n = st.mean([x[0] for x in pairs]), st.mean([x[1] for x in pairs])
        print(f"    {name:<12}{len(sub):>6}{o * 100:>8.1f}%{n * 100:>8.1f}%{(n - o) * 100:>+8.1f}")

    # 判闸差异:三个门槛各自会放行哪些腿。**显示口径**下这只是「会不会显示为可信」,
    # 不影响任何推荐 —— 真正 gate 仍是平 5%。
    print(f"\n▸ 判定差异(EV ≥ 门槛 的腿数;真正 gate 仍是平 {BASE_THRESHOLD * 100:.0f}%)")
    gates = {
        f"平 {BASE_THRESHOLD * 100:.0f}%": lambda r: r["ev"] >= BASE_THRESHOLD,
        "旧(钉死 σ_P)": lambda r: r["ev"] >= _thresholds(r)[0],
        "新(σ_P(h))": lambda r: r["ev"] >= _thresholds(r)[1],
    }
    print(f"    {'门槛':<16}{'放行':>6}{'其中赢':>8}{'实测回报':>10}")
    for name, ok in gates.items():
        passed = [r for r in recs if ok(r)]
        if not passed:
            print(f"    {name:<16}{0:>6}{'—':>8}{'—':>10}")
            continue
        won = [r for r in passed if r["won"]]
        # 回报 = 赢则 (SP−1),输则 −1。**N 小到没有统计意义,只是记账。**
        roi = st.mean([(r["sp"] - 1) if r["won"] else -1.0 for r in passed])
        print(f"    {name:<16}{len(passed):>6}{len(won):>8}{roi * 100:>+9.1f}%")

    flipped = [r for r in recs
               if (r["ev"] >= _thresholds(r)[0]) != (r["ev"] >= _thresholds(r)[1])]
    print(f"\n▸ 新旧门槛**判定反转**的腿:{len(flipped)} / {len(recs)}")
    for r in flipped[:12]:
        o, n = _thresholds(r)
        verdict = "新更严→拦下" if n > o else "新更松→放行"
        print(f"    {r['赛事'][:26]:<28}{r['腿']}  h={r['h']:>5.1f}  "
              f"EV{r['ev'] * 100:>+6.1f}%  {o * 100:>5.1f}%→{n * 100:>5.1f}%  {verdict}"
              f"  {'✓赢' if r['won'] else '✗输'}")
    if len(flipped) > 12:
        print(f"    …另有 {len(flipped) - 12} 条未列")

    print(f"\n⚠️ N={len(recs)} 腿 / {tally['可用行']} 行。这个量级只够回答"
          "「口径差多大」,**不够回答「哪个门槛更赚钱」**。")
    print("   影子模式 = 只显示不判闸;要让它进闸(A-3 正式版)须先预注册 + 前向验证。")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="A-3 影子门槛回放(只读)")
    p.add_argument("--min-h", type=float, default=0.0,
                   help="只看冻结缺口 ≥ 该小时数的行(默认 0 = 全部)")
    args = p.parse_args(argv)
    recs, tally = load_legs(args.min_h)
    report(recs, tally)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
