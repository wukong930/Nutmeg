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
import contextlib
import datetime as dt
import json
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
#: ⭐ **秋季重测触发点**(owner 指示 2026-07-29:「现在是最优解,秋天攒够回来重测」)。
#: 绑在 **+1 线**上 —— 它是两条里的约束项(N 1,803 vs −1 的 3,131)。
#: 2,250 ≈ 再攒一个赛季(可 join 的 +1 线实测 **449 场/年**),SE 约收窄 10%
#: (0.0101→~0.0091,判闸下界 +0.0118→~+0.0138)。
#:
#: ⚠️ **这是漂移检查,不是精度追逐。** δ 是「足球怎么踢 + DC 怎么错配」的性质,
#: 战术趋势变了它会漂;重测首要目的是发现漂移,SE 收窄只是顺带。
#: ⚠️ 到点后由 owner 更新本常数(手动闸,不自动推进)—— 与 sigma_p_fit 的
#: NEXT_EVAL_N 同一条纪律:自动推进 = 无人看管的反复检验。
NEXT_DELTA_EVAL_N_P1 = 2250

#: ⛔ **已退役的问题**:「δ₋₁ 与 δ₊₁ 是否真的不同(主场优势)」。
#: 现状 diff = +0.0144 ± 0.0128(z=1.12)。要推到 80% 功效需 **样本 ×6.2 ≈ 21 年**
#: (按 +1 线 449 场/年)。**在这条数据路径上永远测不出来** —— 别再把它当
#: 「秋天再看」的待办挂着。v2.0 选独立估计**不是因为证明了它们不同**,
#: 而是因为各自都够用了、不必假设(prereg v2.0 §6.1)。
_HOMOGENEITY_UNRESOLVABLE_YEARS = 21

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
        # ⛔ 唯一实现在 market_handicap.handicap_outcome —— 别再写第四份(2026-08-10 收口)
        won = MH.handicap_outcome(r["home_goals"], r["away_goals"], ln)
        if won is None:
            continue
        pop = "俱乐部" if is_domestic_club_league(r["league"]) else "大赛"
        buckets.setdefault((ln, pop), []).append((raw[0][1:], cor[0][1:], won))
    return buckets


def _logloss(rows, idx: int) -> float:
    return st.fmean(-math.log(max(x[idx][x[2]], 1e-9)) for x in rows)


def slice_key(ln: int, pop: str) -> str:
    """机读键 —— 存档 JSON 与跨次比对都用它。"""
    return f"{ln:+d}·{pop}"


def slice_stats(buckets: dict, *, min_n: int = 10) -> dict:
    """→ {切片: {n, raw_ll, c1_ll}} —— 只收 N ≥ min_n 的,和报告口径一致。"""
    out = {}
    for (ln, pop), rows in buckets.items():
        if len(rows) < min_n:
            continue
        out[slice_key(ln, pop)] = {
            "n": len(rows),
            "raw_ll": _logloss(rows, 0),
            "c1_ll": _logloss(rows, 1),
        }
    return out


def render(buckets: dict, *, min_n: int = 10, prev: dict | None = None) -> str:
    """``prev`` = 上一次存档的 `slice_stats`(含 `_date`)。

    ⭐ 2026-08-03 加。prereg v2.0 §5.1 的回滚条件是「log-loss 比裸网格更差,
    **且连续两周如此**」—— 但本仪表原来只写 `_latest.md` **每次覆盖、不留历史**,
    于是那个条件在产物上**根本无法判定**。这和涓流「END 写成常量 ⇒ 零新增必然」、
    s6「用今天为空证明过滤器接通」是同一族:**检查和它的前提不匹配**。
    现在存档 + 自比,让报告自己回答「连续两周了吗」,不靠人记得手动 diff。
    """
    out = ["## ① 前向校准 —— 裸网格 vs C1 修正后 vs 实际", ""]
    prev_date = (prev or {}).get("_date")
    if prev_date:
        out += [f"> 对比基准:上次存档 **{prev_date}**"
                f"(间隔 {(prev or {}).get('_gap_days', '?')} 天)", ""]
    else:
        out += ["> ⚠️ **没有上次存档** —— 本次是基线,「连续两周」这一条要下次才判得了。", ""]
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
        worse = lc > lr
        verdict = "⚠️ **变差**" if worse else "✅ 改善"
        out.append("")
        out.append(f"- 3-way log-loss:裸 {lr:.4f} → C1 {lc:.4f} — {verdict} {lr - lc:+.4f}")
        pv = (prev or {}).get(slice_key(ln, pop))
        if pv:
            was = pv["c1_ll"] > pv["raw_ll"]
            out.append(f"- 上次({prev_date}, N={pv['n']}):"
                       f"{pv['raw_ll'] - pv['c1_ll']:+.4f} {'⚠️ 变差' if was else '✅ 改善'}")
            if worse and was and abs(ln) == 1:
                gap = (prev or {}).get("_gap_days") or 0
                near = (f"  ⚠️ 但两次间隔仅 {gap} 天,**不足一周** —— "
                        "「连续两周」不该由同周两跑凑" if gap < 5 else "")
                out.append(f"- ⛔ **连续两次变差** ⇒ prereg v2.0 §5.1 的回滚条件成立"
                           f"(±1 线,回滚到 v1.9:`_C1_DELTA_P1` → 0.03220)。{near}")
        elif prev_date:
            out.append(f"- 上次({prev_date}):该切片当时 N 不足,无可比读数")
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
        "## ③ 秋季重测进度(owner 指示 2026-07-29)",
        "",
    ]
    # ⚠️ 拟合 N 存在 `_FIT_META` 里(手工记录上次拟合的样本量),不是实时查库 ——
    # 所以这行报的是「上次拟合以来该不该重测」的**门槛对照**,不是自动进度条。
    # 真要推进得重跑 scripts/handicap_delta_homogeneity.py 拿新 N。
    n_p1 = next((n for lab, _d, _s, n, _p, _src in _FIT_META if lab == "+1 让负"), 0)
    hit = n_p1 >= NEXT_DELTA_EVAL_N_P1
    out += [
        f"- **+1 线**(两条里的约束项)上次拟合 N = **{n_p1:,} / {NEXT_DELTA_EVAL_N_P1:,}**"
        f"(还差 {max(NEXT_DELTA_EVAL_N_P1 - n_p1, 0):,} 场;可 join 的 +1 线实测 "
        f"**449 场/年** ⇒ 约 {max(NEXT_DELTA_EVAL_N_P1 - n_p1, 0) / 449:.1f} 年)",
        f"- 状态:{'🟢 **已到重测点** — 重跑 homogeneity 脚本并按 prereg v2.0 §8 判定'
                  if hit else '⏳ **未到重测点**'}",
        "",
        "> ⭐ **这是漂移检查,不是精度追逐。** δ 是「足球怎么踢 + DC 怎么错配」的性质,",
        "> 战术趋势变了它会漂。重测首要目的是发现漂移,SE 收窄(~10%)只是顺带。",
        "",
        "> ⛔ **已退役的问题**:「δ₋₁ 与 δ₊₁ 是否真的不同(主场优势)」。现状",
        f"> diff = +0.0144 ± 0.0128(z=1.12),推到 80% 功效需**样本 ×6.2 ≈ "
        f"{_HOMOGENEITY_UNRESOLVABLE_YEARS} 年**。",
        "> **在这条数据路径上永远测不出来** —— 别再把它当「秋天再看」挂着。",
        "> v2.0 选独立估计**不是因为证明了它们不同**,而是各自都够用、不必假设。",
        "",
    ]
    return "\n".join(out)


def load_prev(hist_dir: Path, today: str) -> dict | None:
    """读**今天之前**最近的一份存档(JSON)。

    ⚠️ 必须排除今天 —— 同一天重跑时,今天的档案会先被覆盖,若不排除就会拿自己
    当基准,「连续两次变差」永远成立。这是自比工具的经典自噬。
    """
    if not hist_dir.exists():
        return None
    cands = sorted(f for f in hist_dir.glob("*.json") if f.stem < today)
    if not cands:
        return None
    prev = json.loads(cands[-1].read_text(encoding="utf-8"))
    prev["_date"] = cands[-1].stem
    with contextlib.suppress(ValueError):
        prev["_gap_days"] = (dt.date.fromisoformat(today)
                             - dt.date.fromisoformat(cands[-1].stem)).days
    return prev


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="让球 δ 校准常设仪表(只读,永不 gate)")
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--min-n", type=int, default=10, help="低于该 N 的切片只报不解读")
    ap.add_argument("--out", default="logs/delta_calibration_latest.md",
                    help="写到哪(空串=只打 stdout)")
    ap.add_argument("--no-archive", action="store_true",
                    help="不写带日期的存档(默认写;存档是「连续两周」判定的唯一依据)")
    args = ap.parse_args(argv)

    buckets = load_lines(args.db)
    stats = slice_stats(buckets, min_n=args.min_n)
    today = dt.datetime.now(dt.UTC).date().isoformat()
    hist = (Path(args.out).parent / "delta_calibration_history") if args.out else None
    prev = load_prev(hist, today) if hist else None

    text = "\n".join([
        "# 让球 δ 校准(只读研究 · 永不 gate)", "",
        render(buckets, min_n=args.min_n, prev=prev),
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
        # ⭐ 自动存档(2026-08-03)。prereg v2.0 §5.1 要「连续两周」,而本仪表原来
        # 只写 _latest.md 每次覆盖 —— 那个条件在产物上判不了。md 给人看,json 给
        # 下次自比用(解析 markdown 太脆)。同日重跑覆盖当天这份 = 当天最新读数。
        if not args.no_archive and hist is not None:
            hist.mkdir(parents=True, exist_ok=True)
            (hist / f"{today}.md").write_text(text, encoding="utf-8")
            (hist / f"{today}.json").write_text(
                json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[archive] {hist}/{today}.{{md,json}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
