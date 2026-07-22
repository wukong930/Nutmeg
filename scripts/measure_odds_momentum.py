"""竞彩赔率动量 — 早期变盘能否预测后续?(4 年历史,纯只读)。

起因:`docs/vote_drift_direction_2026-07-22.md` 测出散户支持率能预测竞彩 SP 漂移
方向,但 support 是 **forward-only** 源(2026-06-30 才开采)——**预测变量在历史里
根本不存在**,那条关系永远无法回测。本脚本找一个**有 4 年历史、可回测**的替代:
赔率自身的早期变盘。

假设:竞彩随国内 handle 调价,而 handle 持续累积 ⇒ 早期调价方向应预示后续。

⚠️ **探索性 · 禁动钱**。它只测 SP 侧(EV 的一个输入),见那份报告 §7。

三个伪相关陷阱及对策(`--mode` 可逐个复现):
  ① **共享端点** early=(o1-o0)/o0 与 later=(o2-o1)/o1 共用 o1 → o1 的噪声抬高
     early、压低 later ⇒ 虚假**负**相关(即会**低估**真动量)。
     对策:不重叠窗口 —— early 用 seq0→1,later 用 seq2→3。
  ② **赔率水平** 冷赔率本身漂得多,而早期漂得多的常是冷腿 ⇒ 虚假正相关。
     对策:控制 odds(t) 的偏相关。
  ③ **时间间隔** 长间隔天然漂得多。对策:一并控制 Δt。

⚠️⚠️ **第四个陷阱不在本脚本能修的范围内,但必须知道**:`jingcai_vote_snapshots`
是**定时快照**(每 ~6.3h 拍一张,50% 的相邻记录间赔率没变),而本脚本用的
`jingcai_odds_history` 是**变盘触发**记录(仅 7% 重复)。**拿两者比会得到假答案** ——
2026-07-22 实测:用 vote 表算同一个量得 r=0.885,那是成对零值撑起来的,不是动量。
见 `--mode cadence` 与报告 §5。

报告:docs/odds_momentum_2026-07-23.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import sqlite3
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HIST_DB = f"file:{REPO}/data/v4_jingcai_history.db?mode=ro"
OBS_DB = f"file:{REPO}/data/v4_observation.db?mode=ro"
LEGS = (("主", "h"), ("平", "d"), ("客", "a"))
_EPS = 1e-9


def pearson(xs: list, ys: list) -> tuple:
    n = len(xs)
    if n < 4:
        return None, None
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    if not den:
        return None, None
    r = num / den
    return r, (r * math.sqrt((n - 2) / (1 - r * r)) if abs(r) < 1 else float("inf"))


def partial(xs: list, ys: list, zs: list) -> tuple:
    rxy, _ = pearson(xs, ys)
    rxz, _ = pearson(xs, zs)
    ryz, _ = pearson(ys, zs)
    if None in (rxy, rxz, ryz):
        return None, None
    den = math.sqrt((1 - rxz ** 2) * (1 - ryz ** 2))
    if not den:
        return None, None
    rp = (rxy - rxz * ryz) / den
    n = len(xs)
    return rp, (rp * math.sqrt((n - 3) / (1 - rp * rp)) if abs(rp) < 1 and n > 3 else float("inf"))


def partial2(xs: list, ys: list, z1: list, z2: list) -> tuple:
    """控制两个协变量(逐次剔除)。"""
    a, _ = partial(xs, ys, z1)
    b, _ = partial(xs, z2, z1)
    c, _ = partial(ys, z2, z1)
    if None in (a, b, c):
        return None, None
    den = math.sqrt((1 - b ** 2) * (1 - c ** 2))
    if not den:
        return None, None
    rp = (a - b * c) / den
    n = len(xs)
    return rp, (rp * math.sqrt((n - 4) / (1 - rp * rp)) if abs(rp) < 1 and n > 4 else float("inf"))


def _hours(a: str, b: str) -> float:
    return (dt.datetime.fromisoformat(b) - dt.datetime.fromisoformat(a)).total_seconds() / 3600


def load_history() -> dict:
    conn = sqlite3.connect(HIST_DB, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT match_id, seq, update_dt, h, d, a, close_date FROM jingcai_odds_history "
            "WHERE market='had' AND h IS NOT NULL ORDER BY match_id, update_dt, seq"
        ).fetchall()
    finally:
        conn.close()
    g: dict = {}
    for r in rows:
        g.setdefault(r["match_id"], []).append(r)
    return g


def build(groups: dict, *, overlap: bool) -> dict:
    """overlap=True 复刻陷阱①(共享 o1);False = 不重叠窗口(干净)。"""
    out = {leg: {"early": [], "later": [], "odds": [], "dt_l": [], "season": []}
           for leg, _ in LEGS}
    need = 3 if overlap else 4
    for snaps in groups.values():
        if len(snaps) < need:
            continue
        if overlap:
            a, b, c, d = snaps[0], snaps[1], snaps[1], snaps[-1]
        else:
            a, b, c, d = snaps[0], snaps[1], snaps[2], snaps[3]
        season = (snaps[0]["close_date"] or "")[:4]
        for leg, k in LEGS:
            try:
                oa, ob, oc, od = float(a[k]), float(b[k]), float(c[k]), float(d[k])
            except (TypeError, ValueError):
                continue
            if min(oa, ob, oc) <= 0:
                continue
            he = _hours(a["update_dt"], b["update_dt"])
            hl = _hours(c["update_dt"], d["update_dt"])
            if he <= 0 or hl <= 0:
                continue
            s = out[leg]
            s["early"].append((ob - oa) / oa * 100)
            s["later"].append((od - oc) / oc * 100)
            s["odds"].append(oa)
            s["dt_l"].append(hl)
            s["season"].append(season)
    return out


def _table(tag: str, data: dict) -> None:
    print(f"\n{'═' * 78}\n{tag}")
    print(f"{'腿':<4}{'N':>7}{'原始r':>9}{'t':>7}{'控赔率':>9}{'t':>7}{'控赔率+Δt':>11}{'t':>7}")
    for leg, _ in LEGS:
        s = data[leg]
        if len(s["early"]) < 50:
            continue
        r0, t0 = pearson(s["early"], s["later"])
        r1, t1 = partial(s["early"], s["later"], s["odds"])
        r2, t2 = partial2(s["early"], s["later"], s["odds"], s["dt_l"])
        print(f"{leg:<4}{len(s['early']):>7}{r0:>9.3f}{t0:>7.1f}"
              f"{r1:>9.3f}{t1:>7.1f}{r2:>11.3f}{t2:>7.1f}")


def walk_forward(clean: dict) -> None:
    print(f"\n{'═' * 78}\n③ 跨赛季 walk-forward(不重叠窗口 + 控赔率&Δt)")
    print(f"{'赛季':<8}{'N':>7}{'主 r':>9}{'t':>7}{'平 r':>9}{'t':>7}{'客 r':>9}{'t':>7}")
    for yr in sorted({s for s in clean["主"]["season"] if s}):
        cells, n_show = [], 0
        for leg, _ in LEGS:
            s = clean[leg]
            idx = [i for i, y in enumerate(s["season"]) if y == yr]
            if len(idx) < 50:
                cells.append((None, None))
                continue
            cells.append(partial2(*([s[k][i] for i in idx] for k in
                                    ("early", "later", "odds", "dt_l"))))
            n_show = len(idx)
        if all(c[0] is None for c in cells):
            continue
        row = f"{yr:<8}{n_show:>7}"
        for r, t in cells:
            row += f"{r:>9.3f}{t:>7.1f}" if r is not None else f"{'—':>9}{'—':>7}"
        print(row)


def cadence_check() -> None:
    """⚠️ 陷阱④:两个源的采样机制不可比 —— 这是 r=0.885 假象的根因。"""
    print(f"\n{'═' * 78}\n④ 采样口径诊断(为什么不能拿 vote 表做交叉验证)")
    conn = sqlite3.connect(OBS_DB, uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT match_date, home_team, captured_at, jc_home FROM jingcai_vote_snapshots "
        "WHERE pool_code='HAD' AND jc_home IS NOT NULL "
        "ORDER BY match_date, home_team, captured_at"
    ).fetchall()
    conn.close()
    g: dict = {}
    for r in rows:
        g.setdefault((r["match_date"], r["home_team"]), []).append(r)
    gaps, same, total = [], 0, 0
    for snaps in g.values():
        for a, b in zip(snaps, snaps[1:], strict=False):
            ta = dt.datetime.fromisoformat(a["captured_at"].replace("Z", "+00:00"))
            tb = dt.datetime.fromisoformat(b["captured_at"].replace("Z", "+00:00"))
            gaps.append((tb - ta).total_seconds() / 3600)
            total += 1
            if abs(float(b["jc_home"]) - float(a["jc_home"])) < _EPS:
                same += 1
    hist = load_history()
    hg, hsame, htot = [], 0, 0
    for snaps in hist.values():
        for a, b in zip(snaps, snaps[1:], strict=False):
            hg.append(_hours(a["update_dt"], b["update_dt"]))
            htot += 1
            if abs(float(b["h"]) - float(a["h"])) < _EPS:
                hsame += 1
    print(f"  {'源':<26}{'间隔中位':>10}{'赔率未变占比':>14}{'性质':>12}")
    print(f"  {'vote_snapshots(定时)':<26}{st.median(gaps):>9.1f}h"
          f"{same / total * 100:>13.0f}%{'定时快照':>12}")
    print(f"  {'odds_history(变盘触发)':<26}{st.median(hg):>9.1f}h"
          f"{hsame / htot * 100:>13.0f}%{'变盘触发':>12}")
    print("  ⇒ vote 表一半的相邻记录赔率没动,成对零值会把相关系数吹到 0.885。")
    print("    交叉验证必须先按「仅真实变盘」压缩 —— 但压缩后 N 仅 17-25,不可用。")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="竞彩赔率动量(探索性)")
    p.add_argument("--mode", default="all",
                   choices=["all", "naive", "clean", "walk", "cadence"],
                   help="naive=复刻陷阱① / clean=干净窗口 / walk=跨赛季 / cadence=采样诊断")
    args = p.parse_args(argv)

    if args.mode == "cadence":
        cadence_check()
        return 0

    g = load_history()
    print(f"载入 {len(g)} 场 had 变盘史")
    if args.mode in ("all", "naive"):
        _table("① 复刻粗测(共享端点 o1 — 含陷阱①,仅供对照,勿引用)",
               build(g, overlap=True))
    if args.mode in ("all", "clean", "walk"):
        clean = build(g, overlap=False)
        if args.mode in ("all", "clean"):
            _table("② 不重叠窗口(seq0→1 预测 seq2→3 — 干净口径)", clean)
        if args.mode in ("all", "walk"):
            walk_forward(clean)
    if args.mode == "all":
        cadence_check()
        print("\n⚠️ 探索性,禁直接动钱 — 见 docs/odds_momentum_2026-07-23.md 的边界节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
