"""串关回测 + EV 闸负筛选证据 —— 只读复现脚本(2026-07-25)。

报告:`docs/parlay_backtest_2026-07-25.md`。**改这里就是改那份报告的口径。**

**只读**:不写任何库、不产生下注建议、不接判闸。

结论一句话:+5% 平门槛在两个独立 sharp 锚下都把 ROI 推到**比随机下注更差**,
而紧邻它下方的 0–5% 档是全场最好的一档。⚠️ 但**没有任何单格统计显著** ——
力度来自三条独立证据同向,不来自任何一个数字。**别据此改闸**(见报告 §6)。

三种运行模式:
  (默认)         皇冠锚回测 + EV×SP 交叉表 + 分层内检验
  --anchor pinnacle  换 Pinnacle 锚重跑(排除「锚不够 sharp」)
  --anchor-quality   两锚头对头校准(log-loss / Brier,与下注策略无关)
"""
from __future__ import annotations

import argparse
import itertools
import math
import sqlite3
import statistics as st
from collections import defaultdict

from nutmeg.v4.cli.clv_ledger import _devig3

DB = "data/v4_jingcai_history.db"
FLOOR, GATE = 0.02, 0.05
BACKTEST_END = "2025-05-31"      # 皇冠校正量只用这之后的样本估 = 真正样本外


def _dnum(s: str) -> int:
    return int(s[:4]) * 372 + int(s[5:7]) * 31 + int(s[8:10])


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def crown_adjustment(c: sqlite3.Connection) -> list[float]:
    """皇冠去vig 的三腿偏差,**只用回测窗口之后的比赛**估(见报告 §2.3)。

    为什么不用全样本:用同一批数据既估校正又做评估 = 循环。半分检验已确认偏差
    在两半都存在(+1.04pp / +1.99pp 平局),所以外推到窗口内是合理的。
    """
    rows = c.execute(
        "SELECT c_home,c_draw,c_away,home_goals,away_goals FROM crown_close_history "
        "WHERE match_date > ? AND c_home>1 AND c_draw>1 AND c_away>1 "
        "AND home_goals IS NOT NULL", (BACKTEST_END,)).fetchall()
    n, s, o = 0, [0.0] * 3, [0.0] * 3
    for r in rows:
        p = _devig3(r["c_home"], r["c_draw"], r["c_away"])
        if not p:
            continue
        n += 1
        for i in range(3):
            s[i] += p[i]
        gd = r["home_goals"] - r["away_goals"]
        o[0] += gd > 0
        o[1] += gd == 0
        o[2] += gd < 0
    return [(o[i] - s[i]) / n for i in range(3)] if n else [0.0] * 3


def build_legs(c: sqlite3.Connection, anchor: str) -> list[dict]:
    """竞彩终盘 SP × 锚收盘去vig P → 每腿一条记录(含结算)。"""
    jc: dict[int, dict] = {}
    for r in c.execute(
            "SELECT match_id,close_date,home_team,away_team,h,d,a,"
            "home_goals,away_goals,single_available FROM jingcai_odds_history "
            "WHERE market='had' ORDER BY match_id, seq"):
        jc[r["match_id"]] = dict(r)      # 后写覆盖 ⇒ 终盘

    if anchor == "crown":
        q = ("SELECT home_team,away_team,match_date,c_home o1,c_draw o2,c_away o3 "
             "FROM crown_close_history WHERE c_home>1 AND c_draw>1 AND c_away>1")
        adj = crown_adjustment(c)
    else:
        q = ("SELECT home_team,away_team,match_date,p_home o1,p_draw o2,p_away o3 "
             "FROM pinnacle_close_history")
        adj = [0.0] * 3                  # Pinnacle 自身偏差 ≤1pp,不校正

    anc: dict[tuple, list] = defaultdict(list)
    for r in c.execute(q):
        anc[(r["home_team"], r["away_team"])].append(r)

    legs: list[dict] = []
    for m in jc.values():
        if m["home_goals"] is None:
            continue
        hit = [x for x in anc.get((m["home_team"], m["away_team"]), [])
               if abs(_dnum(x["match_date"]) - _dnum(m["close_date"])) <= 1]
        if not hit:
            continue
        p = _devig3(hit[0]["o1"], hit[0]["o2"], hit[0]["o3"])
        if not p:
            continue
        p = [max(1e-4, p[i] + adj[i]) for i in range(3)]
        tot = sum(p)
        p = [x / tot for x in p]
        gd = m["home_goals"] - m["away_goals"]
        win = (gd > 0, gd == 0, gd < 0)
        sp = (m["h"], m["d"], m["a"])
        for i in range(3):
            if sp[i] and sp[i] > 1:
                legs.append({"day": m["close_date"], "mid": m["match_id"],
                             "ev": p[i] * sp[i] - 1.0, "sp": sp[i], "win": win[i],
                             "single": m["single_available"]})
    return legs


def _roi(v: list[dict]) -> tuple[int, float, float, float]:
    """→ (N, 命中率, ROI, ±2SE)。空/过小交给调用方判断。"""
    if not v:
        return 0, 0.0, 0.0, 0.0
    r = [x["sp"] if x["win"] else 0.0 for x in v]
    sd = st.stdev(r) if len(v) > 1 else 0.0
    return (len(v), sum(1 for x in v if x["win"]) / len(v),
            st.fmean(r) - 1.0, 2 * sd / math.sqrt(len(v)))


def _line(lbl: str, v: list[dict], min_n: int = 10) -> str:
    n, h, roi, se = _roi(v)
    if n < min_n:
        return f"  {lbl:<24}N={n:>5}   —— N 太小,不报"
    return (f"  {lbl:<24}N={n:>5}  命中 {h:>5.1%}  ROI {roi:>+7.1%}  "
            f"±2SE {se * 100:>5.1f}pp")


def report_backtest(legs: list[dict], anchor: str) -> str:
    L = ["=" * 70,
         f"串关回测 — {anchor} 锚 · 结算实况",
         "⚠️ **上界**:选择用的是收盘线,而你下注时看不到收盘线。",
         "⚠️ 没有任何单格统计显著 —— 别据此改闸(见报告 §5.2/§6)。",
         "=" * 70,
         f"{len(legs)} 条腿 · {len({x['mid'] for x in legs})} 场 · "
         f"{len({x['day'] for x in legs})} 个投注日"]

    byday: dict[str, list[dict]] = defaultdict(list)
    for x in legs:
        byday[x["day"]].append(x)

    # 单腿 / 二串:每日 argmax,过闸才下
    single, pair = [], []
    for day_legs in byday.values():
        b = max(day_legs, key=lambda x: x["ev"])
        if b["ev"] >= GATE:
            single.append(b)
        ok = sorted([x for x in day_legs if x["ev"] >= FLOOR],
                    key=lambda x: -x["ev"])[:8]
        best = None
        for a, b2 in itertools.combinations(ok, 2):
            if a["mid"] == b2["mid"]:       # 同场两腿互斥,竞彩不许
                continue
            e = (1 + a["ev"]) * (1 + b2["ev"]) - 1
            if best is None or e > best[0]:
                best = (e, a, b2)
        if best and best[0] >= GATE:
            e, a, b2 = best
            pair.append({"sp": a["sp"] * b2["sp"], "win": a["win"] and b2["win"],
                         "ev": e})

    L += ["", "【宣称 EV vs 实际 ROI】"]
    for lbl, bets in (("单腿", single), ("二串", pair)):
        n, h, roi, se = _roi(bets)
        if n:
            ev = st.fmean(b["ev"] for b in bets)
            L.append(f"  {lbl}  N={n}  命中 {h:.1%}  宣称 EV {ev:+.1%} → "
                     f"实际 ROI {roi:+.1%}  (差 {(roi - ev) * 100:+.1f}pp · "
                     f"95% [{(roi - se) * 100:+.0f}%, {(roi + se) * 100:+.0f}%])")

    L += ["", "【对照:同一批腿的不同筛选】"]
    L.append(_line("① 全部腿(随机基准)", legs))
    L.append(_line("② EV ≥ 0", [x for x in legs if x["ev"] >= 0]))
    L.append(_line("③ EV 0-5%", [x for x in legs if 0 <= x["ev"] < GATE]))
    L.append(_line("④ EV ≥ +5%(真闸)", [x for x in legs if x["ev"] >= GATE]))
    L.append(_line("⑤ 每日 argmax", [max(v, key=lambda x: x["ev"])
                                    for v in byday.values()]))

    # EV × SP 交叉 + 分层内检验(报告 §4)
    def spb(sp: float) -> str:
        return "短<2.0" if sp < 2 else "中2-4" if sp < 4 else "长4-7" if sp < 7 else "超长≥7"

    def evb(e: float) -> str:
        return "<0%" if e < 0 else "0-5%" if e < GATE else "≥5%"

    g: dict[tuple, list] = defaultdict(list)
    for x in legs:
        g[(evb(x["ev"]), spb(x["sp"]))].append(x)
    SPB = ("短<2.0", "中2-4", "长4-7", "超长≥7")
    L += ["", "【高 EV 的腿躲在哪个赔率档】(格=占该 EV 档的%)",
          "  " + " " * 10 + "".join(f"{s:>12}" for s in SPB)]
    for e in ("<0%", "0-5%", "≥5%"):
        tot = sum(len(g[(e, s)]) for s in SPB) or 1
        L.append(f"  EV {e:<7}" + "".join(
            f"{100 * len(g[(e, s)]) / tot:>11.0f}%" for s in SPB))

    L += ["", "【决定性:同一赔率档内,EV 还预测 ROI 吗】"]
    for s in SPB:
        rows = [(e, g[(e, s)]) for e in ("<0%", "0-5%", "≥5%") if len(g[(e, s)]) >= 15]
        if rows:
            L.append("  " + s + ":  " + "   ".join(
                f"EV {e} {_roi(v)[2]:+.1%}(N={len(v)})" for e, v in rows))
    return "\n".join(L)


def report_anchor_quality(c: sqlite3.Connection) -> str:
    """两锚头对头 —— 与下注策略**无关**的纯校准检验(报告 §4.3)。"""
    pin: dict[tuple, list] = defaultdict(list)
    for r in c.execute("SELECT home_team,away_team,match_date,p_home,p_draw,p_away "
                       "FROM pinnacle_close_history"):
        pin[(r["home_team"], r["away_team"])].append(r)
    both = []
    for r in c.execute("SELECT home_team,away_team,match_date,c_home,c_draw,c_away,"
                       "home_goals,away_goals FROM crown_close_history "
                       "WHERE home_goals IS NOT NULL AND c_home>1"):
        for q in pin.get((r["home_team"], r["away_team"]), []):
            if abs(_dnum(q["match_date"]) - _dnum(r["match_date"])) <= 1:
                pc = _devig3(r["c_home"], r["c_draw"], r["c_away"])
                pp = _devig3(q["p_home"], q["p_draw"], q["p_away"])
                if pc and pp:
                    gd = r["home_goals"] - r["away_goals"]
                    both.append((pc, pp, 0 if gd > 0 else 1 if gd == 0 else 2))
                break
    if not both:
        return "两锚无重叠比赛。"
    L = [f"两锚头对头(N={len(both)} 场,与下注策略无关)"]
    for lbl, i in (("皇冠", 0), ("Pinnacle", 1)):
        ll = -st.fmean(math.log(max(1e-9, x[i][x[2]])) for x in both)
        br = st.fmean(sum((x[i][j] - (j == x[2])) ** 2 for j in range(3)) for x in both)
        L.append(f"  {lbl:<10} log-loss {ll:.4f}   Brier {br:.4f}")
    d = [-math.log(max(1e-9, x[0][x[2]])) + math.log(max(1e-9, x[1][x[2]]))
         for x in both]
    se = 2 * st.stdev(d) / math.sqrt(len(d))
    L.append(f"  差(皇冠−Pinnacle) {st.fmean(d):+.4f} ± {se:.4f} (2SE) → "
             + ("Pinnacle 显著更准" if st.fmean(d) - se > 0 else
                "**分不出** —— 皇冠不是弱锚"))
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="串关回测(只读复现)")
    p.add_argument("--anchor", choices=("crown", "pinnacle"), default="crown")
    p.add_argument("--anchor-quality", action="store_true",
                   help="只跑两锚头对头校准")
    args = p.parse_args(argv)
    c = _conn()
    try:
        if args.anchor_quality:
            print(report_anchor_quality(c))
        else:
            print(report_backtest(build_legs(c, args.anchor), args.anchor))
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
