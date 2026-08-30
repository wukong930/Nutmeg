"""nutmeg-pair-ev-ledger — 配对 EV 测量(Phase 1,2026-07-25)。

**只读、只报告。不改判闸、不产生下注建议、不写 recommendation_sessions。**
口径逐条对应 `docs/pair_ev_prereg_2026-07-25.md`,**改这里就是改预注册** —— 别动。

为什么要测:竞彩只有 **17%** 的场次开单关(韩职 29%/瑞超 21%/挪超 13%;欧罗巴·
芬超·欧冠·巴甲·美职 0/59)。其余 83% 必须串关,而串关 EV 是乘的 ——
`EV_串 = (1+EV₁)(1+EV₂) − 1`,两条 +3% 的腿合成 **+6.09%** 过闸,逐腿闸看不见。

⚠️ 风险在,但**不是**「搜索空间放大 150×」——那句是错的,同日蒙特卡洛已更正
(prereg §7):`(1+a)(1+b)` 对两者单调递增 ⇒ **配对 argmax 恒等于观测最高的两条腿**,
搜索空间是 N 条腿不是 N² 对。真实代价是**选了两个顺序统计量而非一个**,虚高约
**2 倍**于单腿(N=300/σ=5% 实测:单腿 +7.5pp、二串 +15.7pp)。现行 z=1.0 按单腿标,
搬到串关等于把标准悄悄放松一半。**所以先测再谈上闸。**

复用 `clv_ledger` 的口径(捕获时刻选、对收盘量、无前视),不另立第二套。
"""
from __future__ import annotations

import argparse
import itertools
import math
import sqlite3
import statistics as st

from nutmeg.v4.cli._shared import write_report_with_history
from nutmeg.v4.cli.clv_ledger import (
    _HAD,
    _HC,
    _devig3,
    _hhad_cover_p,
    _pinn_close,
)
from nutmeg.v4.data.league_labels import canonical_league

#: 预注册常量 —— **看过任何结局之后都不许调**(prereg §2/§3)。
LEG_FLOOR = 0.02      # 每腿单独下限 = 单腿闸的一半。⚠️ **不是组合数杀手**
                      # (prereg §2 修订):argmax 下 top-2 腿必然远在它之上,
                      # 它改的是候选**计数**不是**选择**。留着当保底 + 给
                      # Phase 2 可能的阈值规则预留。
PAIR_GATE = 0.05      # 配对闸 = 单腿闸同一个数(要测的正是这条线搬过去成不成立)
_CORR_MIN_N = 10      # 次要结局 A 的最小 N —— 低于它不显示相关系数(见 render)
#: 最小可检出 |r| 用**真** t 临界值(``scipy.stats.t.ppf``),不是 1.96。
#: ⚠️ 1.96 是大样本近似,而 t 临界值**更大** ⇒ 用 1.96 会把门槛算**小**
#: (N=31:0.34 vs 真值 0.36)= **高估**自己的检出能力,正好是本行要防的那件事。
#: 「小到无关紧要」的 |r| —— 要宣布「分散化成立」必须整个 95% 区间落在带内
#: (等价检验),而不是「没测出显著」。0.3 沿用原阈值的量级,只是改了用法。
_CORR_NEGLIGIBLE = 0.3


def _t_crit(df: int) -> float:
    """双尾 α=.05 的 t 临界值;scipy 缺席时退回 1.96 并**由调用方承担**低估。"""
    if df < 1:
        return float("inf")
    try:
        from scipy.stats import t as _t
        return float(_t.ppf(0.975, df))
    except ImportError:
        return 1.96


def _legs_for_day(conn: sqlite3.Connection) -> list[dict]:
    """全部候选腿,各带 cap_ev(选择用)与 clv(评估用)。prereg §1。"""
    conn.row_factory = sqlite3.Row
    raw = conn.execute(
        "SELECT match_date, home_team, away_team, league, market, handicap_home, "
        "jc_home, jc_draw, jc_away, psc_home, psc_draw, psc_away, "
        "psc_over, psc_under, ou_line, captured_at FROM jingcai_sp").fetchall()
    latest: dict[tuple, dict] = {}
    for r in raw:                       # 每 (比赛, 玩法) 取最新一次捕获
        d = dict(r)
        k = (d["match_date"], d["home_team"], d["away_team"], d["market"] or "had")
        if k not in latest or (d["captured_at"] or "") >= (latest[k]["captured_at"] or ""):
            latest[k] = d

    out: list[dict] = []
    for d in latest.values():
        close = _pinn_close(conn, d)
        if close is None:
            continue
        market = d["market"] or "had"
        jc = (d["jc_home"], d["jc_draw"], d["jc_away"])
        if market == "hhad":
            p_close = _hhad_cover_p(close, d["handicap_home"])
            p_cap = _hhad_cover_p((d["psc_home"], d["psc_draw"], d["psc_away"],
                                   d["psc_over"], d["psc_under"], d["ou_line"]),
                                  d["handicap_home"])
            labels = _HC
        else:
            p_close = _devig3(close[0], close[1], close[2])
            p_cap = _devig3(d["psc_home"], d["psc_draw"], d["psc_away"])
            labels = _HAD
        if p_close is None or p_cap is None:
            continue
        for i in range(3):
            sp = jc[i]
            if not sp or sp <= 1:
                continue
            out.append({
                "date": d["match_date"],
                "match": (d["match_date"], d["home_team"], d["away_team"]),
                "label": f'{d["home_team"]} vs {d["away_team"]} {labels[i]}',
                "league": canonical_league(d["league"]),
                "market": market, "hc": d["handicap_home"],
                "cap_ev": p_cap[i] * float(sp) - 1.0,
                "clv": p_close[i] * float(sp) - 1.0,
            })
    return out


def _pairs(legs: list[dict]) -> list[tuple[dict, dict]]:
    """合法对:同投注日 · **不同比赛** · 两腿 cap_ev ≥ LEG_FLOOR。prereg §2。"""
    ok = [x for x in legs if x["cap_ev"] >= LEG_FLOOR]
    by_day: dict[str, list[dict]] = {}
    for x in ok:
        by_day.setdefault(x["date"], []).append(x)
    out = []
    for day_legs in by_day.values():
        for a, b in itertools.combinations(day_legs, 2):
            if a["match"] != b["match"]:      # 同场两腿互斥/强相关,竞彩本就不许
                out.append((a, b))
    return out


def _ev(a: dict, b: dict, key: str) -> float:
    return (1.0 + a[key]) * (1.0 + b[key]) - 1.0


def compute(db_path: str) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        legs = _legs_for_day(conn)
    finally:
        conn.close()
    pairs = _pairs(legs)

    # 每个投注日只选一对:argmax pair_ev(捕获时刻,无前视)。prereg §3。
    best_by_day: dict[str, tuple[dict, dict]] = {}
    n_by_day: dict[str, int] = {}
    for a, b in pairs:
        d = a["date"]
        n_by_day[d] = n_by_day.get(d, 0) + 1
        cur = best_by_day.get(d)
        if cur is None or _ev(a, b, "cap_ev") > _ev(*cur, "cap_ev"):
            best_by_day[d] = (a, b)
    selected = [(a, b) for a, b in best_by_day.values()
                if _ev(a, b, "cap_ev") >= PAIR_GATE]
    return {"legs": legs, "pairs": pairs, "selected": selected,
            "n_by_day": n_by_day}


def render(rep: dict) -> str:
    legs, pairs, sel = rep["legs"], rep["pairs"], rep["selected"]
    L = ["=" * 66,
         "配对 EV 账本 — Phase 1 测量(prereg docs/pair_ev_prereg_2026-07-25.md)",
         "⚠️ 只读:不改判闸 · 不产生下注建议 · 结论须等 N≥30 投注日",
         "=" * 66,
         f"候选腿 {len(legs)} · 过腿下限(≥{LEG_FLOOR:.0%}) "
         f"{sum(1 for x in legs if x['cap_ev'] >= LEG_FLOOR)} · "
         f"合法对 {len(pairs)} · 投注日 {len(rep['n_by_day'])}"]
    if not pairs:
        L.append("\n无合法对 —— 没有任何两条腿同日、异场、且都过 +2% 下限。")
        return "\n".join(L)

    all_clv = [_ev(a, b, "clv") for a, b in pairs]
    L.append(f"\n【对照组】全部合法对 N={len(all_clv)} · 平均 pair_CLV "
             f"{st.fmean(all_clv):+.1%} · 打败收盘 {sum(1 for c in all_clv if c > 0)}")

    L.append(f"\n【选中对】(每日 argmax,pair_EV≥{PAIR_GATE:.0%},无前视)  N={len(sel)}")
    if not sel:
        L.append("  一对都没过闸 —— 这本身就是结果,不是故障。")
    else:
        cl = [_ev(a, b, "clv") for a, b in sel]
        L.append(f"  平均 pair_CLV {st.fmean(cl):+.1%} · "
                 f"打败收盘 {sum(1 for c in cl if c > 0)}/{len(cl)}")
        # 次要结局 A —— ②的前提检验(prereg §4)
        # ⚠️ N<10 不算:3 个点的相关系数几乎必然是 ±0.7 量级的噪声,显示出来
        # 会被当成发现。宁可留白。
        if len(sel) >= _CORR_MIN_N:
            xs = [a["clv"] for a, _ in sel]
            ys = [b["clv"] for _, b in sel]
            try:
                r = st.correlation(xs, ys)
                # 🚨 2026-08-30 修:这里原来是 `if abs(r) < 0.3: "≈0 → 分散化成立"`
                #    —— 一个**不看功效**的硬阈值。实测 r=+0.22 / N=31 被判成
                #    「成立」,而 N=31 在 α=.05 下**最小可检出 |r| 是 0.36** ⇒
                #    r=0.22 根本落在测不出的区间里。**「测不出」被印成了「≈0」**,
                #    而 ② 那套「σ 平方和加」的论证正是靠这一行当前提。
                #    ⇒ 三态:成立 / 推翻 / **功效不足**。「不显著 ≠ 相等」——
                #    要说「成立」必须过**等价检验**(整个区间落在无关紧要的带内),
                #    不是「没测出显著」。
                n = len(sel)
                z = math.atanh(max(min(r, 0.999999), -0.999999))
                se = 1.0 / math.sqrt(n - 3) if n > 3 else float("inf")
                lo, hi = math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)
                _tc = _t_crit(n - 2)
                r_det = _tc / math.sqrt(n - 2 + _tc ** 2)        # 最小可检出 |r|
                if lo > 0:
                    verdict = "正相关 → 误差**同向**,σ 线性加,②的好处归零"
                elif hi < 0:
                    verdict = "负相关 → 误差**反向**,比独立还好;但先怀疑是样本假象"
                elif -_CORR_NEGLIGIBLE < lo and hi < _CORR_NEGLIGIBLE:
                    verdict = (f"等价检验通过(整个区间落在 ±{_CORR_NEGLIGIBLE:.1f} 内)"
                               " → 分散化成立(σ 平方和加,②的前提站得住)")
                else:
                    verdict = (f"⚠️ **功效不足,判不了** —— N={n} 最小可检出 |r|="
                               f"{r_det:.2f};⛔ 别把它读成「≈0」,②的前提**尚未验证**")
                L.append(f"  两腿 CLV 相关系数 r={r:+.2f} "
                         f"[95%CI {lo:+.2f}, {hi:+.2f}]  {verdict}")
            except st.StatisticsError:
                L.append("  两腿 CLV 相关系数:方差为零,算不了")
        else:
            L.append(f"  两腿 CLV 相关系数:N={len(sel)} < {_CORR_MIN_N},"
                     "不算 —— 小样本相关系数是噪声,不是发现")
        # 次要结局 B —— 多重性记账
        ns = [rep["n_by_day"][a["date"]] for a, _ in sel]
        z_need = st.fmean([math.sqrt(2 * math.log(n)) for n in ns if n > 1] or [0.0])
        L.append(f"  选中日的候选对数 中位 {int(st.median(ns))} → "
                 f"所需 z≈{z_need:.1f}(现行 z=1.0)")
        n2 = sum(1 for a, b in sel for x in (a, b)
                 if x["market"] == "hhad" and x["hc"] in (-2, 2))
        L.append(f"  ⚠️ ±2 让球腿占 {n2}/{2 * len(sel)} 条 —— 该线无 δ 校正"
                 f"(见 prereg §6-3),pair_EV 会继承其虚高")
        L.append("\n  明细:")
        for a, b in sorted(sel, key=lambda p: -_ev(*p, "cap_ev")):
            L.append(f"    {a['date']}  EV {_ev(a, b, 'cap_ev'):+.1%} → "
                     f"CLV {_ev(a, b, 'clv'):+.1%}")
            L.append(f"       {a['label']} ({a['cap_ev']:+.1%})")
            L.append(f"       {b['label']} ({b['cap_ev']:+.1%})")

    L.append(f"\n诚实:N={len(sel)} 个投注日。prereg §5 要求 N≥30 才看结论,"
             "确认性结论要 N≥200 + t≥2.8 + 过 FDR。现在只是攒数据。")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="配对 EV 测量(Phase 1,只读)")
    p.add_argument("--db", default="data/v4_observation.db")
    # 归档(2026-08-30)。prereg §4 的主结局要在 N≥30 时读,而本工具原来**只打印**
    # —— 跑完就没了,到评估点手上只有一个点。同 δ 仪表 2026-08 踩过的坑。
    p.add_argument("--out", default="logs/pair_ev_latest.md")
    p.add_argument("--no-archive", action="store_true")
    args = p.parse_args(argv)
    text = render(compute(args.db))
    print(text)
    if args.out:
        write_report_with_history(args.out, text, archive=not args.no_archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
