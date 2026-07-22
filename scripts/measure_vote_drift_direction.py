"""竞彩散户支持率 → 后续赔率漂移**方向**(探索性,纯只读)。

问题:冻结缺口的 ±X% 带子,有没有办法判断是加还是减?
A-1(docs/freeze_gap_measurement_2026-07-18.md)测出漂移**无偏**——但那是
**边际**无偏。本脚本测**条件**分布:给定散户支持率之后,方向是否可预测。

假设(源自 `记忆 jingcai-market-microstructure`「竞彩=admin 定价+随国内 handle 调」):
  support(t) 高 → 竞彩压低该腿赔率 → 后续 Δodds < 0   (相关应为负)

⚠️ **探索性 · 禁动钱**。要用它改任何下注/择时规则,须另立预注册 + 前向验证。

方法要点(比首末粗测更收紧):
  · 用**相邻快照对**:support(t) → Δodds(t→t+1)/odds(t),而非首次 vs 首末
  · 控制 odds(t) 水平(偏相关)—— 冷腿本身漂移幅度就大,不控会高估
  · HAD / HHAD 两个盘**独立跑**,互为交叉验证
  · 另测 Δsupport 与同期 Δodds 的关联(更接近实时联动)

报告:docs/vote_drift_direction_2026-07-22.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import sqlite3
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DB_URI = f"file:{REPO}/data/v4_observation.db?mode=ro"
LEGS = (("主", "h_support", "jc_home"), ("平", "d_support", "jc_draw"),
        ("客", "a_support", "jc_away"))
BUCKETS = ((15.0, "≤15% 极冷"), (30.0, "15-30%"), (50.0, "30-50%"), (101.0, ">50% 热"))


def pearson(xs: list, ys: list) -> tuple:
    """→ (r, t)。样本不足或零方差 → (None, None)。"""
    n = len(xs)
    if n < 3:
        return None, None
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    if not den:
        return None, None
    r = num / den
    t = r * math.sqrt((n - 2) / (1 - r * r)) if abs(r) < 1 else float("inf")
    return r, t


def partial_corr(xs: list, ys: list, zs: list) -> tuple:
    """控制 z 之后 x–y 的偏相关 → (r, t)。"""
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
    t = rp * math.sqrt((n - 3) / (1 - rp * rp)) if abs(rp) < 1 and n > 3 else float("inf")
    return rp, t


def _hours(a: str, b: str) -> float:
    fa = dt.datetime.fromisoformat(a.replace("Z", "+00:00"))
    fb = dt.datetime.fromisoformat(b.replace("Z", "+00:00"))
    return abs((fb - fa).total_seconds()) / 3600


def load_snapshots(pool: str) -> dict:
    """→ {(日期, 主, 客): [按时间排序的快照行]}。"""
    conn = sqlite3.connect(DB_URI, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT match_date, home_team, away_team, captured_at, "
            "h_support, d_support, a_support, jc_home, jc_draw, jc_away "
            "FROM jingcai_vote_snapshots WHERE pool_code=? AND jc_home IS NOT NULL "
            "AND h_support IS NOT NULL ORDER BY match_date, home_team, captured_at",
            (pool,),
        ).fetchall()
    finally:
        conn.close()
    out: dict = {}
    for r in rows:
        out.setdefault((r["match_date"], r["home_team"], r["away_team"]), []).append(r)
    return out


def build_pairs(groups: dict) -> tuple[dict, int]:
    """相邻快照对 → 每腿的 (support_t, drift%, odds_t, Δsupport)。"""
    per_leg = {leg: {"sup": [], "drift": [], "odds": [], "dsup": []} for leg, _, _ in LEGS}
    n_match = 0
    for snaps in groups.values():
        if len(snaps) < 2:
            continue
        n_match += 1
        for a, b in zip(snaps, snaps[1:], strict=False):   # 相邻配对,长度差 1
            if _hours(a["captured_at"], b["captured_at"]) <= 0:
                continue
            for leg, sup_k, odd_k in LEGS:
                if a[odd_k] and b[odd_k] and a[sup_k] is not None and b[sup_k] is not None:
                    d = per_leg[leg]
                    d["sup"].append(float(a[sup_k]))
                    d["drift"].append((float(b[odd_k]) - float(a[odd_k])) / float(a[odd_k]) * 100)
                    d["odds"].append(float(a[odd_k]))
                    d["dsup"].append(float(b[sup_k]) - float(a[sup_k]))
    return per_leg, n_match


def report(pool: str, label: str) -> None:
    per_leg, n_match = build_pairs(load_snapshots(pool))
    print(f"\n{'═' * 76}")
    print(f"{label}  ({n_match} 场有 ≥2 次快照)")
    print(f"{'腿':<4}{'配对N':>7}{'support(t)':>12}{'漂移均值':>11}"
          f"{'r':>8}{'t':>7}{'控赔率后r':>11}{'t':>7}")
    for leg, _, _ in LEGS:
        d = per_leg[leg]
        if len(d["sup"]) < 10:
            continue
        r, t = pearson(d["sup"], d["drift"])
        rp, tp = partial_corr(d["sup"], d["drift"], d["odds"])
        print(f"{leg:<4}{len(d['sup']):>7}{st.mean(d['sup']):>11.1f}%"
              f"{st.mean(d['drift']):>+10.2f}%{r:>8.3f}{t:>7.1f}{rp:>11.3f}{tp:>7.1f}")

    print("\n  ▸ 剂量-反应:按 support(t) 分档看后续漂移(比 r 直观)")
    print(f"    {'档':<12}{'N':>6}{'漂移均值':>11}{'SE':>8}{'t':>7}")
    pooled: dict = {name: [] for _, name in BUCKETS}
    for leg, _, _ in LEGS:
        d = per_leg[leg]
        for s, drift in zip(d["sup"], d["drift"], strict=True):
            for hi, name in BUCKETS:
                if s <= hi:
                    pooled[name].append(drift)
                    break
    for _, name in BUCKETS:
        v = pooled[name]
        if len(v) < 10:
            continue
        m = st.mean(v)
        se = st.stdev(v) / math.sqrt(len(v))
        print(f"    {name:<12}{len(v):>6}{m:>+10.2f}%{se:>8.2f}{m / se:>7.1f}")

    print("\n  ▸ Δsupport(t→t+1) vs 同期 Δ赔率(测实时联动)")
    for leg, _, _ in LEGS:
        d = per_leg[leg]
        if len(d["dsup"]) < 10:
            continue
        r, t = pearson(d["dsup"], d["drift"])
        print(f"    {leg}  N={len(d['dsup']):>4}  r={r:>7.3f}  t={t:>6.1f}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="竞彩散户支持率 → 赔率漂移方向(探索性)")
    p.add_argument("--pools", default="HAD,HHAD", help="盘口,逗号分隔(默认两个都跑)")
    args = p.parse_args(argv)
    names = {"HAD": "① 1X2 盘 (HAD)", "HHAD": "② 让球盘 (HHAD) — 独立交叉验证"}
    for pool in [x.strip().upper() for x in args.pools.split(",") if x.strip()]:
        report(pool, names.get(pool, pool))
    print("\n⚠️ 探索性测量,禁直接动钱 — 见 docs/vote_drift_direction_2026-07-22.md 的边界节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
