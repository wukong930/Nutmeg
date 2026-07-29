"""nutmeg-delta-calibration — 让球 δ 校准的常设仪表(只读,**永不 gate**)。

## 为什么要这个

δ₋₁/δ₊₁ 自 2026-07-17 上线、δ₋₂ 自 07-27 上线,但**没有任何东西在持续看着它们**。
2026-07-28 owner 随口一问「±1 修正后效果怎么样」,当场测出 δ₊₁ 在它自己的拟合人口
(俱乐部联赛)上 **log-loss 变差 −0.0111**、两条被修的腿都被推向**错误**方向。
——**如果不是被问到,我不会去测。** 这就是它该变成常设仪表的理由。

## 两块内容,回答两个不同的问题

**① 前向校准(「修对了吗」)**:把每条让球线的**裸网格 P** 和 **C1 修正后 P** 并排
和**实际命中率**比,再给 3-way log-loss 的 A/B。按 `is_domestic_club_league` 分
俱乐部 / 大赛两个人口 —— δ 是在**国内联赛**上拟合的,大赛不在那个人口里
(prereg v1.8 §2.1 的同一条纪律)。

**② 功效(「N 够了吗」)**:δ 的估计误差 ≈ 二项 `SE = √(p(1−p)/N)`。A′ 判闸用
`δ − 2SE`,所以**修正要真的做功,必须 δ > 2·SE**,即:

    N > 4·p·(1−p) / δ²

这条不等式是本仪表最有用的一行。它把「参数该定多少」翻译成「还差多少场」,
并且立刻暴露一件事:**δ 越小,确立它所需的 N 涨得越快(∝ 1/δ²)**。
δ₊₁=0.016 需要 N≈3,700(朴素)/ 5,500–7,400(算同日聚类)—— 曾据此判定「≈8 年、
实践上不可确立」。⭐ **2026-07-29 这个判定被推翻,但推翻它的不是耐心而是 join**:
δ₊₁ 之所以显得那么小,是因为 join 漏了别名层、丢掉 59% 样本。补上后 δ₊₁=0.0320、
N=1,803、t=3.16 —— **需 N 从 ~3,700 掉到 920,当场就够了**(N ∝ 1/δ²:δ 涨 2 倍,
需 N 掉 4 倍)。**教训:说「样本不够」之前,先确认没有样本被自己的管线丢掉。**

⚠️ 表里的 SE 是**朴素二项、无同日聚类** —— 与 `market_handicap` 的注记一致,
所以它是真实不确定性的**下限**,所需 N 是**下限**。经验设计效应 1.5–2×。

## 边界

只读,不写库,不产生下注建议,**永不影响退出码**。它**不**改任何 δ ——
改一个已部署的预注册常数需要 owner 口令 + prereg 修订(δ₋₂ 走的就是这条路)。
本仪表的职责是**让「该不该改」这件事一直可见**,不是自己去改。
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import statistics as st
from pathlib import Path

from nutmeg.v4.cli.clv_ledger import _devig3
from nutmeg.v4.data.league_labels import is_domestic_club_league
from nutmeg.v4.model import market_handicap as MH

_LEGS = ("让胜", "让平", "让负")

# 拟合 N + 该腿典型 p —— 来自各自的测量报告(代码里没有,故在此登记出处)。
# (标签, market_handicap 里的 δ 属性名, SE 属性名, 拟合N, 典型 p, 出处)
_FIT_META: tuple[tuple[str, str, str, int, float, str], ...] = (
    # ⭐ v2.0(2026-07-29)N 大幅上升:join 补上别名层后样本 3,038→4,934
    # (命中率 41%→67%)。N 变了功效算式的结论也跟着变,所以这里必须同步。
    ("−1 让胜", "_C1_DELTA", "_C1_DELTA_SE", 3131, 0.25,
     "handicap_delta_prereg_v2.0_2026-07-29 (独立估计)"),
    ("+1 让负", "_C1_DELTA_P1", "_C1_DELTA_P1_SE", 1803, 0.38,
     "handicap_delta_prereg_v2.0_2026-07-29 (独立估计)"),
    ("−2 让胜", "_C2_DELTA_H", "_C2_SE_H", 340, 0.44,
     "handicap_delta2_measurement_2026-07-20 (v1.8)"),
    ("−2 让负", "_C2_DELTA_A", "_C2_SE_A", 340, 0.35,
     "handicap_delta2_measurement_2026-07-20 (v1.8)"),
)


def _fit_rows():
    """⚠️ 存的是**属性名**不是值,每次调用现读 `market_handicap`。

    最初版本在模块加载时就把 δ 求值存进常量元组 —— 那样将来有人改了那边的 δ,
    本仪表会**悄悄停在旧值**上,而它的全部职责就是监督那些 δ。这正是本模块自己
    写的「抄一份必漂」的翻版,只是抄的时机从空间挪到了时间。
    """
    return [(lab, getattr(MH, dn), getattr(MH, sn), n, p, src)
            for lab, dn, sn, n, p, src in _FIT_META]


def required_n(delta: float, p: float) -> float:
    """要让 ``δ > 2·SE``(= 判闸下界为正 = 修正真的做功)所需的最小 N。

    SE = √(p(1−p)/N);令 δ = 2·SE 解得 N = 4p(1−p)/δ²。
    ⇒ **N ∝ 1/δ²**:δ 减半,所需样本变 4 倍。这是「小 δ 不可确立」的全部原因。
    """
    return float("inf") if delta <= 0 else 4.0 * p * (1.0 - p) / (delta ** 2)


def power_table() -> list[dict]:
    out = []
    for lab, d, se, n, p, src in _fit_rows():
        need = required_n(d, p)
        out.append({
            "leg": lab, "delta": d, "se": se, "n": n, "p": p, "src": src,
            "t": (d / se) if se > 0 else float("inf"),
            "lower": d - 2 * se, "need": need,
            "established": (d - 2 * se) > 0,
        })
    return out


def load_lines(db_path: str | Path) -> dict:
    """{(让球线, 人口): [(裸P三元组, C1后三元组, 命中腿下标)]} —— 已结算的行。"""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    buckets: dict = {}
    with conn:
        rows = conn.execute(
            "SELECT * FROM jingcai_sp WHERE market='hhad' AND psc_home IS NOT NULL "
            "AND home_goals IS NOT NULL AND handicap_home IS NOT NULL").fetchall()
    for r in rows:
        ln = int(r["handicap_home"])
        fair = _devig3(r["psc_home"], r["psc_draw"], r["psc_away"])
        if not fair:
            continue
        po = (MH.devig_over(r["psc_over"], r["psc_under"])
              if (r["psc_over"] and r["psc_under"]) else None)
        ou = float(r["ou_line"] or 2.5)
        try:
            raw = MH.implied_handicap_lines(*fair, po, ou_line=ou, lines=(ln,), c1=False)
            cor = MH.implied_handicap_lines(*fair, po, ou_line=ou, lines=(ln,), c1=True)
        except Exception:  # noqa: BLE001 — 网格拟合失败(深线常见)→ 丢该行
            continue
        if not raw or not cor:
            continue
        gd = r["home_goals"] + ln - r["away_goals"]
        won = 0 if gd > 0 else (1 if gd == 0 else 2)
        pop = "俱乐部" if is_domestic_club_league(r["league"]) else "大赛"
        buckets.setdefault((ln, pop), []).append((raw[0][1:], cor[0][1:], won))
    return buckets


def _logloss(rows, idx: int) -> float:
    return st.fmean(-math.log(max(x[idx][x[2]], 1e-9)) for x in rows)


def render(buckets: dict, *, min_n: int = 10) -> str:
    out = ["## ① 前向校准 —— 裸网格 vs C1 修正后 vs 实际", ""]
    if not buckets:
        out.append("  (无已结算的让球行)")
        return "\n".join(out) + "\n"
    for ln, pop in sorted(buckets, key=lambda k: (k[0], k[1])):
        rows = buckets[(ln, pop)]
        if len(rows) < min_n:
            out.append(f"### 让球线 {ln:+d} · {pop} — N={len(rows)} < {min_n},**样本太小,跳过**")
            out.append("")
            continue
        out.append(f"### 让球线 {ln:+d} · {pop} — N={len(rows)} 场")
        out.append("")
        out.append("| 腿 | 裸网格 P | C1 修正后 | 实际命中 | 谁更近 |")
        out.append("|---|---:|---:|---:|---|")
        for i in range(3):
            pr = st.fmean(x[0][i] for x in rows)
            pc = st.fmean(x[1][i] for x in rows)
            act = st.fmean(1.0 if x[2] == i else 0.0 for x in rows)
            if abs(pc - act) < abs(pr - act) - 1e-9:
                who = "C1 ✅"
            elif abs(pc - act) > abs(pr - act) + 1e-9:
                who = "裸 ⚠️"
            else:
                who = "= (δ 未碰)"
            out.append(f"| {_LEGS[i]} | {pr:.1%} | {pc:.1%} | **{act:.1%}** | {who} |")
        lr, lc = _logloss(rows, 0), _logloss(rows, 1)
        verdict = "✅ 改善" if lc < lr else "⚠️ **变差**"
        out.append("")
        out.append(f"- 3-way log-loss:裸 {lr:.4f} → C1 {lc:.4f} — {verdict} {lr - lc:+.4f}")
        out.append("")
    return "\n".join(out)


def render_power() -> str:
    out = ["## ② 功效 —— 「参数该定多少」还差多少场", "",
           "判闸走 `δ − 2SE` ⇒ 修正要真的做功必须 **δ > 2·SE** ⇒ **N > 4p(1−p)/δ²**。",
           "", "| 腿 | δ | SE | 拟合 N | t=δ/SE | δ−2SE | 需 N | 状态 |",
           "|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in power_table():
        need = "∞" if r["need"] == float("inf") else f"{r['need']:.0f}"
        state = "✅ 在做功" if r["established"] else "⚠️ **从未确立**"
        out.append(f"| {r['leg']} | {r['delta']:.3f} | {r['se']:.4f} | {r['n']} | "
                   f"{r['t']:.2f} | {r['lower']:+.3f} | {need} | {state} |")
    out += [
        "",
        "⚠️ SE 是**朴素二项、无同日聚类**(与 `market_handicap` 注记一致)⇒ 它是真实",
        "不确定性的**下限**,「需 N」也是**下限**;经验设计效应 1.5–2× 要乘上去。",
        "",
        "⭐ **N ∝ 1/δ²** —— δ 减半,所需样本变 4 倍。所以「等 N 攒够」对**小 δ 是",
        "无效策略**。⚠️ 但 2026-07-29 的教训是反向的:δ₊₁ 曾按 0.016 算出「需 ~3,700、",
        "≈8 年」,而那个小 δ 来自**漏了别名层的 join**(丢掉 59% 样本);补上后",
        "δ₊₁=0.0320、需 N 掉到 920,当场就够。**说「样本不够」前先确认没被自己丢掉** ——",
        "这不是「再等等」,是「这个参数定不下来」,该由 owner 决定留还是归零。",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="让球 δ 校准常设仪表(只读,永不 gate)")
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--min-n", type=int, default=10, help="低于该 N 的切片只报不解读")
    ap.add_argument("--out", default="logs/delta_calibration_latest.md",
                    help="写到哪(空串=只打 stdout)")
    args = ap.parse_args(argv)

    text = "\n".join([
        "# 让球 δ 校准(只读研究 · 永不 gate)", "",
        render(load_lines(args.db), min_n=args.min_n),
        render_power(),
        "> ⚠️ 本仪表**不改任何 δ**。改一个已部署的预注册常数需要 owner 口令 +",
        "> prereg 修订(δ₋₂ 走的就是这条路)。它的职责是让「该不该改」一直可见。",
        "",
    ])
    print(text)
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
