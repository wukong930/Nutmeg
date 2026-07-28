"""nutmeg-ev-ranking — 「EV 是排序器,还是只是排除器?」的常设仪表。

只读。**永不 gate**,永不产生下注建议。

## 为什么要这个

现有的 ROI 尺子按**注**累积(N=34,±30pp,要等几个月),而这个按**场**累积 ——
每一场结算了的比赛都是一个数据点,不管我们下没下注。前向已有 543 场 / 1,629 腿,
历史库另有几千场。同样的问题,样本多一个量级。

它测的是一句话:**当 Pinnacle 和竞彩分歧时,结果站在谁那边?**
这正是 2026-07-25/27 两次检验留下的悬空问题 —— 1X2 盘说 argmax 有害、让球盘说
argmax 有益,两边只在「argmin 很差」上一致(见 docs/parlay_backtest_2026-07-25.md
的 🚩 更正块)。

## 两个统计量,和各自的坑

**① 分档 ROI 表(主)** —— model-free:「EV 落在 [a,b) 的腿,实际回报多少」。
不需要任何零假设,基准(全部腿)就在同一张表里。
⚠️ **绝不拟合单一斜率**:1X2 那批实测是**倒 U**(0–5% 最好、≥5% 最差),
一条直线会把它平均成约零、报告「无信号」,而实际上是有结构、只是不单调。

**② 场内对比(次)** —— `EV(命中腿) − Σᵢ Pᵢ·EVᵢ`,按比赛日聚类做 t 检验。
⚠️ 减的**必须**是锚加权期望 `Σ Pᵢ·EVᵢ`,不是三腿的**算术**均值。
竞彩的 vig 不均匀分布(散户买热门 ⇒ 热门被压价 ⇒ 热门 EV 天然低),而热门又赢
得多 —— 用算术均值当基准,会**机械地**得到负值,和「EV 反向」长得一模一样。
用锚自己的概率加权,零假设「锚校准良好 ⇒ 期望 0」才成立。

**③ 命中腿平均 EV(仅作反例展示)** —— 这是最直觉的写法,也是**没有信息的**那个:
它主要由「这段时间热门赢了多少」决定(热门赢约 45%、冷门约 25%,而热门 SP 低)。
留在报告里是为了让人看见它和 ② 的差,而不是为了读它。

## ⚠️ 它测「信息」,不测「钱」

排序完全正确 + 12.9% 的竞彩 vig,和「每一注都亏」可以同时成立。若斜率是
「EV +1pp → ROI +0.5pp」,要 +26pp 的 EV 才回本。**别把这里的正数读成能赢钱。**

## 口径

前向锚 = 捕获时 Pinnacle(`jingcai_sp.psc_*`,2026-07-27 起 sink 侧自动补录,
带「不许用未来快照」闸);历史锚 = 皇冠收盘。**两者永不合并**,分开报。
"""
from __future__ import annotations

import argparse
import math
import sqlite3
from pathlib import Path

from nutmeg.v4.cli.clv_ledger import _devig3, _hhad_cover_p
from nutmeg.v4.model.clv_gate import mean_clv_test

# EV 分档:与 docs/parlay_backtest_2026-07-25.md 同一套边界,便于并排读。
_BANDS: tuple[tuple[str, float, float], ...] = (
    ("EV <0%", -9.99, 0.0),
    ("EV 0–5%", 0.0, 0.05),
    ("EV 5–15%", 0.05, 0.15),
    ("EV ≥15%", 0.15, 99.0),
)
_MARKETS = ("had", "hhad")


def _band(ev: float) -> str | None:
    for name, lo, hi in _BANDS:
        if lo <= ev < hi:
            return name
    return None


def _two_se(vals: list[float]) -> float:
    """±2SE(i.i.d.)—— 分档表用。分档内跨日,聚类收益小于场内对比,故不聚类。"""
    n = len(vals)
    if n < 2:
        return float("nan")
    m = math.fsum(vals) / n
    var = math.fsum((x - m) ** 2 for x in vals) / (n - 1)
    return 2.0 * math.sqrt(var / n)


def load_forward(db_path: str | Path) -> list[dict]:
    """前向:jingcai_sp × 捕获时 Pinnacle。每场返回三腿 EV + 命中腿下标。"""
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT match_date, league, market, handicap_home, "
            "jc_home, jc_draw, jc_away, psc_home, psc_draw, psc_away, "
            "psc_over, psc_under, ou_line, home_goals, away_goals "
            "FROM jingcai_sp WHERE home_goals IS NOT NULL AND psc_home IS NOT NULL"
        ).fetchall()
    return [m for m in (_match_from_row(dict(r)) for r in rows) if m]


def _match_from_row(d: dict) -> dict | None:
    market = d.get("market") or "had"
    if market == "hhad":
        line = d.get("handicap_home")
        if line is None:
            return None
        p = _hhad_cover_p((d["psc_home"], d["psc_draw"], d["psc_away"],
                           d["psc_over"], d["psc_under"], d["ou_line"]), line)
        # 让球后净胜:竞彩 DC 约定 −1 = 主队让 1 球
        gd = d["home_goals"] + int(line) - d["away_goals"]
    else:
        p = _devig3(d["psc_home"], d["psc_draw"], d["psc_away"])
        gd = d["home_goals"] - d["away_goals"]
    if not p:
        return None
    won = 0 if gd > 0 else (1 if gd == 0 else 2)
    return _assemble(p, (d["jc_home"], d["jc_draw"], d["jc_away"]),
                     won, d["match_date"], d.get("league"), market)


def _assemble(p, sp, won: int, day: str, league, market: str) -> dict | None:
    """三腿齐全且赔率合法才算一场 —— 缺腿会让 Σ Pᵢ·EVᵢ 的零假设失真。"""
    if any(x is None or x <= 1 for x in sp):
        return None
    evs = [p[i] * float(sp[i]) - 1.0 for i in range(3)]
    return {"day": str(day)[:10], "league": league, "market": market,
            "p": list(p), "sp": [float(x) for x in sp], "ev": evs, "won": won}


def load_history(db_path: str | Path) -> list[dict]:
    """历史基线:竞彩历史档案 × 皇冠收盘锚。一次性回算,**不与前向合并**。"""
    from collections import defaultdict

    def _dn(s: str) -> int:      # 粗日序,只用于 ±1 天窗
        return int(s[:4]) * 372 + int(s[5:7]) * 31 + int(s[8:10])

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        crown = defaultdict(list)
        for r in conn.execute(
                # 皇冠 1X2 列名是 c_*(不是 p_*);让球三腿是 rq_*
                "SELECT home_team, away_team, match_date, league_cn, rangqiu, "
                "c_home, c_draw, c_away, rq_home, rq_draw, rq_away "
                "FROM crown_close_history"):
            crown[(r["home_team"], r["away_team"])].append(dict(r))
        jc: dict = {}
        for r in conn.execute(
                "SELECT match_id, close_date, home_team, away_team, market, "
                "h, d, a, goal_line, home_goals, away_goals "
                "FROM jingcai_odds_history ORDER BY match_id, seq"):
            jc[(r["match_id"], r["market"])] = dict(r)   # 末条 = 终盘

    out = []
    for m in jc.values():
        if m["home_goals"] is None:
            continue
        cands = [c for c in crown.get((m["home_team"], m["away_team"]), [])
                 if abs(_dn(c["match_date"]) - _dn(m["close_date"])) <= 1]
        if not cands:
            continue
        c = cands[0]
        if m["market"] == "hhad":
            line = m["goal_line"]
            # 让球线必须两边相同,否则比的是两个不同的盘
            if line is None or c["rangqiu"] is None or int(c["rangqiu"]) != int(line):
                continue
            p = _devig3(c["rq_home"], c["rq_draw"], c["rq_away"])
            gd = m["home_goals"] + int(line) - m["away_goals"]
        else:
            p = _devig3(c["c_home"], c["c_draw"], c["c_away"])
            gd = m["home_goals"] - m["away_goals"]
        if not p:
            continue
        won = 0 if gd > 0 else (1 if gd == 0 else 2)
        got = _assemble(p, (m["h"], m["d"], m["a"]), won,
                        m["close_date"], c["league_cn"], m["market"])
        if got:
            out.append(got)
    return out


def bands_table(matches: list[dict]) -> list[tuple[str, int, float, float]]:
    """(档名, N, 实际 ROI, ±2SE) —— 主统计量,model-free。含「全部腿」基准行。"""
    buckets: dict[str, list[float]] = {name: [] for name, _, _ in _BANDS}
    every: list[float] = []
    for m in matches:
        for i in range(3):
            ret = m["sp"][i] - 1.0 if i == m["won"] else -1.0
            every.append(ret)
            b = _band(m["ev"][i])
            if b:
                buckets[b].append(ret)
    rows = [("全部腿(基准)", len(every),
             math.fsum(every) / len(every) if every else float("nan"),
             _two_se(every))]
    for name, _, _ in _BANDS:
        v = buckets[name]
        rows.append((name, len(v),
                     math.fsum(v) / len(v) if v else float("nan"), _two_se(v)))
    return rows


def within_match(matches: list[dict]):
    """场内对比 `EV(命中) − Σ Pᵢ·EVᵢ`,按比赛日聚类。返回 (MeanTest, 命中腿平均 EV)。"""
    contrasts, days, hit_ev = [], [], []
    for m in matches:
        null = math.fsum(m["p"][i] * m["ev"][i] for i in range(3))
        contrasts.append(m["ev"][m["won"]] - null)
        hit_ev.append(m["ev"][m["won"]])
        days.append(m["day"])
    test = mean_clv_test(contrasts, days)
    return test, (math.fsum(hit_ev) / len(hit_ev) if hit_ev else float("nan"))


def render(matches: list[dict], *, title: str, caveat: str = "") -> str:
    out = [f"## {title}", ""]
    if caveat:
        out += [caveat, ""]
    if not matches:
        return "\n".join([*out, "  (无可用比赛 — 锚缺失或未结算)", ""])
    for mk in (None, *_MARKETS):
        sub = matches if mk is None else [m for m in matches if m["market"] == mk]
        if not sub:
            continue
        label = "全部玩法" if mk is None else {"had": "1X2", "hhad": "让球"}[mk]
        out.append(f"### {label} — {len(sub)} 场 / {len(sub) * 3} 腿")
        out.append("")
        if mk == "hhad":
            # 两个玩法的 P 不是同一种东西,合读会出错:
            #  · 1X2  = Pinnacle 三元组直接 WPO 去vig(一步)
            #  · 让球 = 从 1X2 + O/U 反推比分网格再切让球线(_hhad_cover_p,多一层建模误差)
            # 且本仪表按既有惯例走 **raw**(implied_handicap_lines 的 c1=False
            # ——「serving path 用 c1=True;eval/measurement keeps raw」)。
            # 尺子里不该烘焙进一个拟合出来的修正,否则是拿被评估对象评估自己。
            # 代价必须说清:面板把 δ₋₁=0.046 从让胜移到让平(−1 线占让球盘 59%),
            # 所以**本表的让胜 EV 比面板高、让平 EV 比面板低**,SP≈2.5 时量级 ~±11pp。
            out.append("> ⚠️ 让球的 P 是从 1X2+O/U **反推**的(比 1X2 多一层建模误差),")
            out.append("> 且按测量惯例走 **raw、不含 δ 校准**(面板走 `c1=True`)。")
            out.append("> ⇒ 本表让胜 EV 比面板**高**、让平 EV 比面板**低**(δ₋₁=0.046,")
            out.append("> −1 线占让球盘 59%,SP≈2.5 时约 ±11pp)。**别和面板的数直接对**。")
            out.append("")
        out.append("| EV 档 | N | 实际 ROI | ±2SE |")
        out.append("|---|---:|---:|---:|")
        for name, n, roi, se in bands_table(sub):
            se_s = "—" if se != se else f"{se * 100:.1f}pp"
            roi_s = "—" if roi != roi else f"{roi:+.1%}"
            out.append(f"| {name} | {n} | {roi_s} | {se_s} |")
        t, hit = within_match(sub)
        out.append("")
        out.append(f"- **场内对比** `EV(命中) − Σ Pᵢ·EVᵢ`:**{t.mean:+.2%}** "
                   f"(N={t.n} 场 / {t.n_clusters} 比赛日"
                   + (f", t={t.t:.2f}, p={t.p:.3f})" if t.t is not None else ", t 未定义)"))
        out.append(f"- 命中腿平均 EV:{hit:+.2%} ⚠️ **别读这个** —— 它由热门/冷门"
                   "谁赢得多决定,不由 EV 准不准决定(见模块头 ③)")
        out.append("")
    out.append("> ⚠️ 这里的数测的是**信息**不是**钱**:排序正确 + 12.9% vig,")
    out.append("> 和「每一注都亏」可以同时成立。**永不 gate,不改任何门槛。**")
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="EV 排序力常设仪表(只读,永不 gate)")
    ap.add_argument("--db", default="data/v4_observation.db", help="前向观测库")
    ap.add_argument("--history-db", default="data/v4_jingcai_history.db",
                    help="竞彩历史档案(皇冠锚基线)")
    ap.add_argument("--historical", action="store_true",
                    help="也算历史基线(皇冠收盘锚)—— 与前向分开报,永不合并")
    ap.add_argument("--out", default="logs/ev_ranking_latest.md",
                    help="写到哪(空串=只打到 stdout)")
    args = ap.parse_args(argv)

    parts = ["# EV 排序力(只读研究 · 永不 gate)", ""]
    parts.append(render(load_forward(args.db), title="前向 — 捕获时 Pinnacle 锚"))
    if args.historical:
        parts.append(render(
            load_history(args.history_db),
            title="历史基线 — 皇冠收盘锚(一次性回算)",
            # 皇冠去vig 有已测的 +1.52pp 平局偏差(N=5,813,半分稳定;见
            # docs/parlay_backtest_2026-07-25.md §2.3)。本仪表**不做**该校正 ——
            # 只对 1X2 的平局腿打补丁会让三腿口径不一致,比不补更难解释。
            # 后果(**两个统计量都中招**,别以为分档表免疫):平局的 P 被高估
            # ⇒ 平局腿 EV 虚高 ⇒ ① 高 EV 档被平局腿**富集**,而平局命中率低
            # ⇒ 高档 ROI 被拉低;② 场内对比同向被拉低。两者的偏都是**负向**。
            # ⇒ **历史侧的负号不能当「EV 反向」的证据**,只能当量级参考。
            # 前向侧走 Pinnacle(自身偏差 ≤1pp),没有这个问题 —— 那才是主仪表。
            # 注:「全部腿(基准)」那一行**确实**免疫 —— 实际 ROI 只用 SP 和赛果,
            # 完全不碰 P。所以基准能和 docs 里的数逐格对上,分档行不能。
            caveat="> ⚠️ 皇冠去vig 有 **+1.52pp 平局偏差且未校正**。平局腿 EV 因此虚高,\n"
                   "> 会**富集**到高 EV 档里(而平局命中率低)—— 所以**分档表和场内对比\n"
                   "> 都带方向已知的负偏**,只能当量级参考,不能当符号证据。\n"
                   "> (「全部腿」基准行免疫:它只用 SP 和赛果,不碰 P。)"))
    text = "\n".join(parts)
    print(text)
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
