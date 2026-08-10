"""让平腿 δ 同源性检验 —— δ₋₁ 与 δ₊₁ 是同一个物理机制吗?(2026-07-28)

## 问题

C1 修正的靶子是**让平腿**:DC 网格把主胜质量在「净胜恰 1 vs ≥2」之间切得太深
(领先方收缩防守 = win-by-one clustering,文献已知的 Poisson 偏差),导致让球盘上
让平腿被系统性低估。A′(v1.7)对 −1 和 +1 **分开拟合**,得到 δ₋₁=0.046 / δ₊₁=0.016。

但 2026-07-28 的功效分析发现:**δ₊₁ 是在 t=1.19、判闸下界为负的情况下上线的** ——
它从未确立过。而 `N > 4p(1−p)/δ²` 说明要确立 δ=0.016 需要 N≈3,700(朴素),
竞彩每年只开约 660 场 +1 线 ⇒ **≈8 年**。「再等等攒 N」是无效策略。

**如果 −1 和 +1 是同一个机制**,就该合并拟合:合并后 N=2,926、t≈4.4,问题消失。
本脚本就是检验这个前提 —— 而不是直接假设它成立。

## ⚠️ 两条口径红线

1. **锚必须是 Pinnacle,不能用皇冠** —— 皇冠去vig 有已测的 **−1.5pp 平局偏差**
   (`handicap_h2_calibration_2026-07-17` §4)。拿它测让平腿 = 把要测的东西注进输入。
2. **必须在真实竞彩让球线上测** —— 合成线会洗掉竞彩的选线信息、把偏差稀释一半
   (A′ 报告 §0 的铁律,我当初差点因此宣布问题已解决)。

## join

真实竞彩让球线(`jingcai_odds_history`)× football-data Pinnacle 收盘
(`PSCH/PSCD/PSCA` + `PC>2.5/PC<2.5`),队名 `normalize_name` + 日期 ±1,
**比分硬闸门**(两侧比分必须完全相同,否则拒绝)。实测拒绝率 0.00%。

只读。不写库,不改任何 δ。
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import math
import sqlite3
import statistics as st

import pandas as pd

from nutmeg.utils.team_canonical import normalize_name as nn
from nutmeg.utils.team_canonical import to_v4_canonical
from nutmeg.v4.cli.clv_ledger import _devig3
from nutmeg.v4.data.league_labels import _EN_TO_CN, canonical_league
from nutmeg.v4.model.market_handicap import (
    devig_over,
    handicap_outcome,
    implied_handicap_lines,
)

#: 中文联赛名 → TEAM_ALIASES 的联赛码(别名表按联赛分桶)。
_CN_TO_CODE = {v: k for k, v in _EN_TO_CN.items()}

#: ⚠️ **模糊匹配关闭**(阈值 1.0 = 只有完全相同才算)。
#: to_v4_canonical 默认 0.86,但它自己的注释就警告「Real Madrid vs Real Sociedad
#: 比值 ~0.79」—— 实测开模糊只多捞 64 场(+1%),不值得把**猜**放进 δ 的地基。
#: 与「绝不瞎猜 team-name mappings」同一条红线。
_FUZZY_OFF = 1.0

_FD_GLOB = "data/historical_sources/football_data_co_uk/**/*.csv"
_NEED = {"PSCH", "PSCD", "PSCA", "HomeTeam", "AwayTeam", "Date", "FTHG", "FTAG"}


def _parse_date(s: str):
    s = str(s)
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def load_football_data() -> tuple[dict, list[str]]:
    """→ ({(norm_home, norm_away, date): (psc3, over, under, fthg, ftag)}, 原始队名池)

    ⚠️ **两个返回值都是承重的。** 索引的 key 是归一化名(join 用),但
    ``to_v4_canonical`` 要的 ``v4_team_pool`` 必须是 football-data 的**原始写法**
    —— 它内部会自己归一化,传归一化池进去会让别名层**静默零命中**
    (别名值 ``"Man United"`` 不在 ``{"man united", …}`` 里)。我第一版就这么传的,
    表面上「命中率没变」,实际是整条别名链没被走到。
    """
    out: dict = {}
    raw_names: set[str] = set()
    for f in glob.glob(_FD_GLOB, recursive=True):
        try:
            d = pd.read_csv(f, low_memory=False)
        except Exception:  # noqa: BLE001 — 坏 CSV 跳过,不该拖垮整个研究
            continue
        if not set(d.columns) >= _NEED:
            continue
        oc = next((a for a in ("PC>2.5", "P>2.5") if a in d.columns), None)
        uc = next((a for a in ("PC<2.5", "P<2.5") if a in d.columns), None)
        # ⚠️ 用 to_dict('records') 而不是 itertuples:后者会把 'PC>2.5' 这种
        # 非标识符列名重命名成位置属性(_12),取不到。我第一版就踩了这个。
        for r in d.to_dict("records"):
            if pd.isna(r.get("PSCH")) or pd.isna(r.get("FTHG")):
                continue
            date = _parse_date(r["Date"])
            if date is None:
                continue
            ov = r.get(oc) if oc else None
            un = r.get(uc) if uc else None
            raw_names.add(str(r["HomeTeam"]))
            raw_names.add(str(r["AwayTeam"]))
            out[(nn(str(r["HomeTeam"])), nn(str(r["AwayTeam"])), date)] = (
                (r["PSCH"], r["PSCD"], r["PSCA"]),
                None if (ov is None or pd.isna(ov)) else float(ov),
                None if (un is None or pd.isna(un)) else float(un),
                int(r["FTHG"]), int(r["FTAG"]))
    return out, sorted(raw_names)


def resolve_team(raw: str, league_cn: str, pool: list[str]) -> str:
    """竞彩队名 → football-data 归一化名。**必经解析器,不许裸 normalize_name。**

    ⚠️ 这是本次(2026-07-29)修掉的根因:原版两侧都只做 ``normalize_name``,
    把 ``to_v4_canonical`` 的**别名层整个跳过**了 —— 「Manchester United」永远
    对不上「Man United」。join 命中率因此卡在 41%;走解析器后 **67%**(+1,900 场),
    而 ``TEAM_ALIASES`` 一条新别名都没加(需要的早就在表里)。
    与记忆「跨源 join 别裸 normalize_name」是同一条规则。
    """
    code = _CN_TO_CODE.get(canonical_league(league_cn) or "", "")
    r = to_v4_canonical(raw or "", code, pool, fuzzy_threshold=_FUZZY_OFF)
    return nn(r.canonical) if r.canonical else nn(raw or "")


def build_sample(db: str, fd: dict, pool: list[str]) -> tuple[list[dict], dict]:
    """真实竞彩让球线 × Pinnacle 锚,比分硬闸门。返回 (样本, 诊断计数)。"""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute(
            "SELECT match_id, close_date, home_team, away_team, goal_line, league_cn, "
            "home_goals, away_goals FROM jingcai_odds_history WHERE market='hhad' "
            "AND goal_line IS NOT NULL AND home_goals IS NOT NULL "
            "ORDER BY match_id, seq").fetchall()
    jc = {r["match_id"]: dict(r) for r in rows}      # 末条 = 终盘
    diag = {"竞彩让球场次": len(jc), "名字未中": 0, "比分闸门拒": 0,
            "缺 Pinnacle O/U": 0, "网格拟合失败": 0, "去vig 失败": 0}
    out: list[dict] = []
    for m in jc.values():
        ln = int(m["goal_line"])
        if abs(ln) != 1:                              # 本检验只关心 ±1
            continue
        h = resolve_team(m["home_team"], m["league_cn"], pool)
        a = resolve_team(m["away_team"], m["league_cn"], pool)
        d0 = dt.date.fromisoformat(m["close_date"][:10])
        got = next((fd[(h, a, d0 + dt.timedelta(days=o))]
                    for o in (0, -1, 1) if (h, a, d0 + dt.timedelta(days=o)) in fd), None)
        if not got:
            diag["名字未中"] += 1
            continue
        psc3, ov, un, fh, fa = got
        if (fh, fa) != (m["home_goals"], m["away_goals"]):
            diag["比分闸门拒"] += 1                     # ⭐ 硬闸门:比分不同 = 不是同一场
            continue
        fair = _devig3(*psc3)
        if not fair:
            diag["去vig 失败"] += 1
            continue
        p_over = devig_over(ov, un) if (ov and un) else None
        if p_over is None:
            diag["缺 Pinnacle O/U"] += 1
            continue
        try:
            grid = implied_handicap_lines(*fair, p_over, ou_line=2.5, lines=(ln,), c1=False)
        except Exception:  # noqa: BLE001
            diag["网格拟合失败"] += 1
            continue
        if not grid:
            diag["网格拟合失败"] += 1
            continue
        _, ph, pd_, pa = grid[0]
        # ⛔ 唯一实现在 market_handicap.handicap_outcome —— 别再写第四份(2026-08-10 收口)
        _won = handicap_outcome(m["home_goals"], m["away_goals"], ln)
        if _won is None:
            continue
        gd = 0 if _won == 1 else (1 if _won == 0 else -1)   # 只用于下面的三元判定
        out.append({"line": ln, "date": m["close_date"][:10], "league": m["league_cn"],
                    "p_draw": pd_, "hit_draw": 1.0 if gd == 0 else 0.0,
                    "p_home": ph, "hit_home": 1.0 if gd > 0 else 0.0,
                    "p_away": pa, "hit_away": 1.0 if gd < 0 else 0.0})
    return out, diag


def cluster_se(vals: list[float], clusters: list) -> float:
    """按 cluster(比赛日)聚类的均值 SE —— 同轮比赛相关,朴素 SE 会高估精度。"""
    n = len(vals)
    if n < 2:
        return float("nan")
    mean = st.fmean(vals)
    groups: dict = {}
    for v, c in zip(vals, clusters, strict=True):
        groups.setdefault(c, []).append(v)
    g = len(groups)
    if g < 2:
        return float("nan")
    meat = math.fsum(math.fsum(x - mean for x in mem) ** 2 for mem in groups.values())
    return math.sqrt((g / (g - 1)) * meat / n ** 2)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="让平腿 δ 同源性检验(只读)")
    ap.add_argument("--db", default="data/v4_jingcai_history.db")
    args = ap.parse_args(argv)

    fd, pool = load_football_data()
    print(f"football-data Pinnacle 索引: {len(fd)} 场 · 原始队名池 {len(pool)} 个")
    sample, diag = build_sample(args.db, fd, pool)
    print("join 诊断:", " · ".join(f"{k} {v}" for k, v in diag.items()))
    rej = diag["比分闸门拒"]
    tot = rej + len(sample) + diag["缺 Pinnacle O/U"]
    print(f"  ⇒ 比分闸门拒绝率 {rej / max(tot, 1):.2%}(A′ 报告同口径为 0.00%)")
    print(f"  可用样本 {len(sample)} 场\n")

    res = {}
    for ln in (-1, 1):
        s = [x for x in sample if x["line"] == ln]
        if len(s) < 50:
            print(f"让球线 {ln:+d}: N={len(s)} 太小,跳过")
            continue
        r = [x["hit_draw"] - x["p_draw"] for x in s]       # 残差 = 实际 − 预测
        se = cluster_se(r, [x["date"] for x in s])
        res[ln] = (st.fmean(r), se, len(s), len({x["date"] for x in s}))
        print(f"让球线 {ln:+d}  N={len(s)} 场 / {res[ln][3]} 比赛日")
        print(f"  让平 预测 {st.fmean(x['p_draw'] for x in s):.1%} → "
              f"实际 {st.fmean(x['hit_draw'] for x in s):.1%}")
        print(f"  **δ̂ = {res[ln][0]:+.4f}**  聚类SE {se:.4f}  t={res[ln][0] / se:.2f}  "
              f"95% [{res[ln][0] - 2 * se:+.4f}, {res[ln][0] + 2 * se:+.4f}]")
        print()

    if len(res) == 2:
        d1, s1, *_ = res[-1]
        d2, s2, *_ = res[1]
        diff = d1 - d2
        sd = math.sqrt(s1 ** 2 + s2 ** 2)
        z = diff / sd
        print("=" * 66)
        print(f"同源性:δ₋₁ − δ₊₁ = {diff:+.4f} ± {sd:.4f}  **z = {z:+.2f}**")
        verdict = ("❌ 拒绝同源(两条线机制不同,必须分开拟合)" if abs(z) > 2
                   else "✅ **拒绝不了同源** —— 合并是可辩护的")
        print(f"  ⇒ {verdict}")
        w1, w2 = 1 / s1 ** 2, 1 / s2 ** 2
        dp, sp = (d1 * w1 + d2 * w2) / (w1 + w2), 1 / math.sqrt(w1 + w2)
        print(f"\n合并 δ = {dp:.4f}  SE = {sp:.5f}  **t = {dp / sp:.2f}**  "
              f"判闸下界 δ−2SE = {dp - 2 * sp:+.4f}")
        print(f"  对比现状:δ₋₁={d1:.4f}(t={d1/s1:.2f}) / δ₊₁={d2:.4f}(t={d2/s2:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
