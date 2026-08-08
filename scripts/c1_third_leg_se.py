#!/usr/bin/env python3
"""±1 让球线「第三腿」的判闸下界 SE —— 只读测量。

预注册 `docs/c1_third_leg_se_prereg_v1.0_2026-08-08.md`(测量前提交)。

被测的缺陷:`c1_leg_lower_bounds` 在 −1 线返回 `float(p_away)`、在 +1 线返回
`float(p_home)` —— 即那条**没被 C1 重构碰过**的腿,下界 == 点估。
「没被这次校准碰过」被消费者 `_boardLegs` 读成了「没有不确定性」,而 `evLo`
是排序键 + 5% 闸。同一病灶第三次发作(前两次:`_UNCAL_SE` 修 |line|≥2、
δ₁ₓ₂ 修 1X2 家族),±1 线的第三腿两次都没盖到。

⭐ 本脚本**不新建管线**:`build_sample` / `cluster_se` 直接从
`handicap_delta_homogeneity.py` import —— 那是 δ₋₁/δ₊₁ 当初用的同一把尺子,
一行不改。样本里三条腿的 p/hit 本来就都在,原脚本只是没报另外两条。
两把尺子量同一件事是这个仓库反复踩过的坑。

用法(只读,零网络):
    .venv/bin/python scripts/c1_third_leg_se.py
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api/src"))

from handicap_delta_homogeneity import (  # noqa: E402
    build_sample,
    cluster_se,
    load_football_data,
)

from nutmeg.v4.model.market_handicap import (  # noqa: E402
    _C1_DELTA,
    _C1_DELTA_P1,
    _C1_DELTA_P1_SE,
    _C1_DELTA_SE,
    _C1_SE_K,
)

#: prereg §3.1 —— 管线自验:让平腿必须复现线上部署值,否则本轮作废。
_SELFCHECK = {-1: (_C1_DELTA, _C1_DELTA_SE), 1: (_C1_DELTA_P1, _C1_DELTA_P1_SE)}
_SELFCHECK_TOL_SE = 1.0

#: prereg §4.2 —— 上线条件。
_SAME_ORDER = (0.5, 2.0)     # 第三腿 SE 与同线兄弟的比值须落在此区间
_MIN_N, _MIN_DAYS = 1500, 400

#: 每条线上「没被 C1 碰过」的那条腿(即当前零收缩的那条)。
_THIRD_LEG = {-1: "away", 1: "home"}
_CN = {"home": "让胜", "draw": "让平", "away": "让负"}


def _leg_stats(sample: list[dict], leg: str) -> tuple[float, float, float, float]:
    """(预测均值, 实际命中率, δ̂, 聚类SE)。δ̂ = 实际 − 预测,与 δ₋₁ 同号约定。"""
    p = [x[f"p_{leg}"] for x in sample]
    hit = [x[f"hit_{leg}"] for x in sample]
    days = [x["date"] for x in sample]
    resid = [h - q for h, q in zip(hit, p, strict=True)]
    return st.fmean(p), st.fmean(hit), st.fmean(resid), cluster_se(resid, days)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="±1 线第三腿 SE(只读)")
    ap.add_argument("--db", default="data/v4_jingcai_history.db")
    a = ap.parse_args(argv)

    fd, pool = load_football_data()
    print(f"football-data Pinnacle 索引 {len(fd)} 场 · 队名池 {len(pool)}")
    sample, diag = build_sample(a.db, fd, pool)
    print("样本诊断:", " · ".join(f"{k}={v}" for k, v in diag.items()))
    print(f"入样 {len(sample)} 场\n")

    verdicts: dict[int, str] = {}
    for ln in (-1, 1):
        s = [x for x in sample if x["line"] == ln]
        days = len({x["date"] for x in s})
        print(f"═══ 让球线 {ln:+d}   N={len(s)} 场 / {days} 比赛日 ═══")
        stats = {leg: _leg_stats(s, leg) for leg in ("home", "draw", "away")}
        third = _THIRD_LEG[ln]
        for leg in ("home", "draw", "away"):
            pbar, hit, d, se = stats[leg]
            t = d / se if se and se == se else float("nan")
            mark = "  ← 当前零收缩" if leg == third else ""
            print(f"  {_CN[leg]}  P̄={pbar:.1%} 实际={hit:.1%}  "
                  f"δ̂={d:+.4f} ±{se:.4f}  t={t:+.2f}  k·SE={_C1_SE_K*se*100:.2f}pp{mark}")

        # ── prereg §3.1 管线自验:不过就停,不解释结果 ──────────────────
        want_d, want_se = _SELFCHECK[ln]
        got_d = stats["draw"][2]
        off = abs(got_d - want_d) / want_se
        ok = off <= _SELFCHECK_TOL_SE
        print(f"  自验:让平 δ̂={got_d:+.4f} vs 线上 {want_d:+.4f} "
              f"(差 {off:.2f} SE,容差 {_SELFCHECK_TOL_SE})  {'✅' if ok else '❌ 本轮作废'}")
        if not ok:
            verdicts[ln] = "PIPELINE_FAIL"
            print()
            continue

        # ── prereg §4.2 上线条件 ──────────────────────────────────────
        se3 = stats[third][3]
        sibs = [stats[leg][3] for leg in ("home", "draw", "away") if leg != third]
        ratio_lo, ratio_hi = se3 / max(sibs), se3 / min(sibs)
        same_order = _SAME_ORDER[0] <= ratio_lo and ratio_hi <= _SAME_ORDER[1]
        enough = len(s) >= _MIN_N and days >= _MIN_DAYS
        if not enough:
            verdicts[ln] = "SAMPLE_TOO_SMALL"
        elif not same_order:
            verdicts[ln] = "SE_OUT_OF_BAND"
        else:
            verdicts[ln] = f"SHIP se={se3:.4f}"
        print(f"  第三腿({_CN[third]})SE={se3:.4f};兄弟 {min(sibs):.4f}–{max(sibs):.4f}"
              f"  比值 {ratio_lo:.2f}–{ratio_hi:.2f}(须落在 {_SAME_ORDER[0]}–{_SAME_ORDER[1]})")
        print(f"  样本 N≥{_MIN_N}? {len(s) >= _MIN_N}   比赛日≥{_MIN_DAYS}? {days >= _MIN_DAYS}")
        print(f"  ⇒ 判决 {verdicts[ln]}\n")

    print("═══ 汇总(按 prereg §4.2)═══")
    for ln, v in verdicts.items():
        print(f"  线{ln:+d}: {v}")
    if all(v.startswith("SHIP") for v in verdicts.values()):
        print("\n上线常数(prereg §4.1:点估一律不动,只加下界):")
        for ln, v in verdicts.items():
            name = "_C1_THIRD_SE_M1" if ln == -1 else "_C1_THIRD_SE_P1"
            print(f"  {name} = {float(v.split('=')[1]):.4f}   # 线{ln:+d} {_CN[_THIRD_LEG[ln]]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
