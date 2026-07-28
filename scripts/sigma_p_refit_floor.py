"""σ_P(h) 重拟合 —— 加地板项。预注册 v2.0(docs/sigma_p_floor_prereg_v2.0_2026-07-29.md)。

    σ(h) = √( floor² + (A · h^B)² )

纯幂律在 h→0 时 σ→0,但 σ_P 不只有漂移:报价粒度、去vig 自身估计误差、快照时刻
抖动都不随 h→0 消失。幂律硬穿带地板的数据 ⇒ **过陡的指数 + 过低的截距**
(A-1 实测 0.79pp×h^0.31;同口径在我们自己 187 条 held-out 轨迹上重拟合得
1.43pp×h^0.17,且 A-1 在 h<4h 低估 1.5-2.5×)。

⚠️ 口径逐条对齐 A-1,**不许改**(改了就不可比):近收盘锚 ≤1.5h、每轨每桶一条增量、
basic 归一化(不是 WPO)、稳健 σ=1.4826×MAD、逐腿(H/D/A)。

只读。不写库、不改任何常数 —— 输出供 owner 按预注册 §4 判据决策。
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import sqlite3
import statistics as st
from collections import defaultdict

_BUCKETS = ((0.5, 1), (1, 2), (2, 4), (4, 8), (8, 16), (16, 32), (32, 64), (64, 168))
_MIN_BUCKET_N = 20          # prereg §3:A-1 用 8,本次收紧
_ANCHOR_MAX_H = 1.5         # prereg §3:锚必须 ≤1.5h,否则整条轨迹丢弃
_LEGS = ("H", "D", "A")
#: A-1(2026-07-18)的现行系数,作对照基线
_A1 = {"H": (0.0079, 0.31), "D": (0.0042, 0.23), "A": (0.0077, 0.27)}


def _iso(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001 — 坏时间戳跳过,不该拖垮整个拟合
        return None


def load_trajectories(db: str) -> list[dict]:
    """→ [{date, points: [(h, pH, pD, pA)] 按 h 升序}],已过近收盘锚闸。"""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute(
            "SELECT home_team, away_team, substr(match_date,1,10) d, source, "
            "captured_at, kickoff_utc, psc_home, psc_draw, psc_away FROM odds_snapshots "
            "WHERE psc_home>1 AND psc_draw>1 AND psc_away>1 AND kickoff_utc IS NOT NULL "
            "ORDER BY home_team, away_team, d, captured_at").fetchall()
    raw: dict = defaultdict(list)
    for r in rows:
        ca, ko = _iso(r["captured_at"]), _iso(r["kickoff_utc"])
        if not ca or not ko or ca >= ko:
            continue
        # basic 归一化 —— A-1 用的就是这个;换 WPO 会让两次拟合不可比
        b = 1 / r["psc_home"] + 1 / r["psc_draw"] + 1 / r["psc_away"]
        raw[(r["home_team"], r["away_team"], r["d"], r["source"])].append(
            ((ko - ca).total_seconds() / 3600.0,
             (1 / r["psc_home"]) / b, (1 / r["psc_draw"]) / b, (1 / r["psc_away"]) / b))
    out = []
    for (_h, _a, d, _s), pts in raw.items():
        pts.sort()
        if not pts or pts[0][0] > _ANCHOR_MAX_H:
            continue                                    # 无近收盘锚 → 整条丢弃
        out.append({"date": d, "points": pts})
    return out


def buckets(trajs: list[dict]) -> dict:
    """→ {leg: {(lo,hi): [(h, Δ), ...]}};每轨每桶只取一条增量。"""
    acc: dict = {lg: defaultdict(list) for lg in _LEGS}
    for t in trajs:
        pts = t["points"]
        anchor = pts[0]
        seen = set()
        for h, ph, pd_, pa in pts[1:]:
            key = next(((lo, hi) for lo, hi in _BUCKETS if lo <= h < hi), None)
            if key is None or key in seen:
                continue
            seen.add(key)
            for i, lg in enumerate(_LEGS, start=1):
                acc[lg][key].append((h, (ph, pd_, pa)[i - 1] - anchor[i]))
    return acc


def robust_sigma(xs: list[float]) -> float:
    m = st.median(xs)
    return 1.4826 * st.median([abs(x - m) for x in xs])


def bucket_points(acc_leg: dict) -> list[tuple[float, float, int]]:
    """→ [(桶内 h 中位, 稳健σ, N)],已丢弃 N < _MIN_BUCKET_N 的桶。"""
    out = []
    for key in _BUCKETS:
        s = acc_leg.get(key, [])
        if len(s) < _MIN_BUCKET_N:
            continue
        out.append((st.median([h for h, _ in s]), robust_sigma([d for _, d in s]), len(s)))
    return out


def fit_floor(pts: list[tuple[float, float, int]]) -> tuple[float, float, float]:
    """拟合 σ(h)=√(floor²+(A·h^B)²),按桶 N 加权最小二乘(σ 空间)。

    σ² 对 floor²、A² 是线性的(B 固定时)⇒ 对 B 网格搜索、内层解析求解,
    比通用优化器稳,也不需要外部依赖。
    """
    best = (float("inf"), 0.0, 0.0, 0.0)
    for bi in range(1, 121):                       # B ∈ (0, 0.60]
        b = bi * 0.005
        # 令 x = h^(2b),拟合 σ² ≈ c0 + c1·x(加权),c0=floor², c1=A²
        xs = [h ** (2 * b) for h, _, _ in pts]
        ys = [s * s for _, s, _ in pts]
        ws = [float(n) for _, _, n in pts]
        sw = sum(ws)
        mx = sum(w * x for w, x in zip(ws, xs, strict=True)) / sw
        my = sum(w * y for w, y in zip(ws, ys, strict=True)) / sw
        den = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs, strict=True))
        if den <= 0:
            continue
        c1 = sum(w * (x - mx) * (y - my)
                 for w, x, y in zip(ws, xs, ys, strict=True)) / den
        c0 = my - c1 * mx
        if c1 <= 0:                                # A²≤0 无意义
            continue
        floor = math.sqrt(max(c0, 0.0))
        a = math.sqrt(c1)
        # 判优在 **σ 空间**(不是 σ²),与判据 2 的 RMSE 口径一致
        rmse = math.sqrt(sum(w * (s - math.sqrt(floor ** 2 + (a * h ** b) ** 2)) ** 2
                             for w, (h, s, _) in zip(ws, pts, strict=True)) / sw)
        if rmse < best[0]:
            best = (rmse, floor, a, b)
    return best[1], best[2], best[3]


def fit_power(pts: list[tuple[float, float, int]]) -> tuple[float, float]:
    """对照基线:纯幂律 σ=A·h^B,加权 log-log(A-1 的做法)。"""
    lx = [math.log(h) for h, _, _ in pts]
    ly = [math.log(max(s, 1e-9)) for _, s, _ in pts]
    ws = [float(n) for _, _, n in pts]
    sw = sum(ws)
    mx = sum(w * x for w, x in zip(ws, lx, strict=True)) / sw
    my = sum(w * y for w, y in zip(ws, ly, strict=True)) / sw
    den = sum(w * (x - mx) ** 2 for w, x in zip(ws, lx, strict=True))
    b = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, lx, ly, strict=True)) / den
    return math.exp(my - b * mx), b


def wrmse(pts, f) -> float:
    ws = [float(n) for _, _, n in pts]
    sw = sum(ws) or 1.0
    return math.sqrt(sum(w * (s - f(h)) ** 2
                         for w, (h, s, _) in zip(ws, pts, strict=True)) / sw)


def bootstrap_floor(trajs: list[dict], leg: str, n_boot: int, seed: int) -> list[float]:
    """按**轨迹**自举(不是按增量)—— 同一场的多个桶相关,按增量自举会高估精度。"""
    import random
    rng = random.Random(seed)
    n = len(trajs)
    out = []
    for _ in range(n_boot):
        samp = [trajs[rng.randrange(n)] for _ in range(n)]
        pts = bucket_points(buckets(samp)[leg])
        if len(pts) < 4:
            continue
        out.append(fit_floor(pts)[0])
    return sorted(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="σ_P(h) 重拟合加地板项(只读,预注册 v2.0)")
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20260729)
    args = ap.parse_args(argv)

    trajs = load_trajectories(args.db)
    print(f"轨迹 {len(trajs)} 条(有近收盘锚 ≤{_ANCHOR_MAX_H}h)")
    # prereg §4:评估集在拟合前按比赛日中位划定
    dates = sorted({t["date"] for t in trajs})
    cut = dates[len(dates) // 2]
    early = [t for t in trajs if t["date"] < cut]
    late = [t for t in trajs if t["date"] >= cut]
    print(f"时间切分 @ {cut}:前半 {len(early)} 条 / 后半 {len(late)} 条\n")

    acc_all, acc_e, acc_l = buckets(trajs), buckets(early), buckets(late)
    verdicts = {}
    for leg in _LEGS:
        pts = bucket_points(acc_all[leg])
        print(f"══ 腿 {leg} ══  可用桶 {len(pts)}")
        if len(pts) < 4:
            print("  桶太少,跳过\n")
            continue
        floor, a, b = fit_floor(pts)
        pa, pb = fit_power(pts)
        a1a, a1b = _A1[leg]
        print(f"  新形状 σ(h) = √({floor * 100:.2f}pp² + ({a * 100:.2f}pp·h^{b:.3f})²)")
        print(f"  纯幂律 σ(h) = {pa * 100:.2f}pp · h^{pb:.3f}"
              f"   |  A-1 现行 = {a1a * 100:.2f}pp · h^{a1b:.2f}")

        # 判据 1 —— 地板自举下界 > 0
        boots = bootstrap_floor(trajs, leg, args.boot, args.seed)
        lo = boots[int(0.025 * len(boots))] if boots else 0.0
        hi = boots[int(0.975 * len(boots))] if boots else 0.0
        c1 = lo > 0
        print(f"  判据①地板>0: floor={floor * 100:.2f}pp  自举95% "
              f"[{lo * 100:.2f}, {hi * 100:.2f}]pp  → {'✅' if c1 else '❌ 退回纯幂律'}")

        # 判据 2 —— 前半拟合、后半评估,新形状 RMSE ≤ 旧形状
        pe, pl = bucket_points(acc_e[leg]), bucket_points(acc_l[leg])
        c2 = c3 = None
        if len(pe) >= 4 and len(pl) >= 4:
            f0, a0, b0 = fit_floor(pe)
            q0, q1 = fit_power(pe)
            r_new = wrmse(pl, lambda h, f=f0, A=a0, B=b0: math.sqrt(f ** 2 + (A * h ** B) ** 2))
            r_old = wrmse(pl, lambda h, A=q0, B=q1: A * h ** B)
            r_a1 = wrmse(pl, lambda h, A=a1a, B=a1b: A * h ** B)
            c2 = r_new <= r_old
            print(f"  判据②外样本: 新 {r_new * 100:.3f}pp  幂律 {r_old * 100:.3f}pp  "
                  f"A-1 {r_a1 * 100:.3f}pp  → {'✅' if c2 else '❌'}")
            # 判据 3 —— 后半每个桶 预测/实测 ∈ [0.75, 1.33]
            ratios = [(h, math.sqrt(f0 ** 2 + (a0 * h ** b0) ** 2) / s) for h, s, _ in pl]
            bad = [(h, r) for h, r in ratios if not (0.75 <= r <= 1.33)]
            c3 = not bad
            worst = min(ratios, key=lambda x: abs(math.log(x[1])))
            print(f"  判据③无方向偏差: {len(bad)}/{len(ratios)} 桶越界"
                  f"(最偏 h={max(ratios, key=lambda x: abs(math.log(x[1])))[0]:.1f}h "
                  f"比值 {max(ratios, key=lambda x: abs(math.log(x[1])))[1]:.2f})"
                  f"  → {'✅' if c3 else '❌'}   [最准 h={worst[0]:.1f}h]")
        else:
            print("  判据②③: 切分后桶不足,无法评估 → ❌(按预注册=不部署)")
        verdicts[leg] = (c1, c2, c3, floor, a, b)
        print()

    print("═" * 62)
    print("预注册 §4:三条全过才部署;任一不过 ⇒ 保持现状。")
    for leg, (c1, c2, c3, floor, a, b) in verdicts.items():
        ok = bool(c1 and c2 and c3)
        print(f"  腿 {leg}: ①{'✅' if c1 else '❌'} ②{'✅' if c2 else '❌'} "
              f"③{'✅' if c3 else '❌'}  ⇒ {'部署' if ok else '**不部署**'}"
              + (f"  (floor={floor * 100:.2f}pp, A={a * 100:.2f}pp, B={b:.3f})" if ok else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
