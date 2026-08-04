#!/usr/bin/env python3
"""σ_P 按**锚点 P 分档**的只读诊断 —— prereg v2.2 §0 那张表的可复现版本。

    .venv/bin/python scripts/sigma_p_by_tier.py

## 为什么存在

v2.2 §0 的观测(2026-08-03)是用一次**临时脚本**跑的,没存。2026-08-04 owner 问
「有没有严格验证过」时,我因此**无法确认它的 CI 是怎么算的** —— 那本身就是答案的
一部分。同族:[[health-check-guardrails]] 的「零新增 ≠ 扫完了」、δ 仪表「要求连续
两周却不留历史」。⭐ **一次性脚本 = 一个将来无法被质询的结论。**

## 口径

复用 `sigma_p_fit` 的加载器与稳健 σ,保证与主仪表同源:
锚 ≤1.5h · ΔP 相对锚 · 每轨每桶一条增量 · σ = 1.4826×MAD ·
档位边界取 `ev_tier_calibration.tier_of`(0.15 / 0.25 / 0.67 / 0.77,手画的)。

## ⚠️ 两种自举都报,因为它们答的不是同一个问题

同一场比赛在不同 h 桶上的增量**相关**(共享那场的定价、消息面、流动性)。
按增量自举把它们当独立样本 ⇒ **高估精度**。实测两者差 1.5-1.9×。
**判据一律看「按轨迹」那一列**;按增量那列只用来显示这个差有多大。

这也是 v2.2 §3 把 N 钉成**轨迹数**的原因:两者差约 12 倍,不写清楚,
闸门会在一个远比预期弱的证据上放行。

⛔ 只读。不写库、不判闸、不影响任何生产常数。
"""
from __future__ import annotations

import random
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api/src"))

from nutmeg.v4.cli.sigma_p_fit import (  # noqa: E402
    _BUCKETS,
    load_trajectories,
    robust_sigma,
)
from nutmeg.v4.model.ev_tier_calibration import tier_of  # noqa: E402

_LEGS = ("H", "D", "A")
_MIN_N = 20          # 与 sigma_p_fit._MIN_BUCKET_N 同
_N_BOOT = 400
_SEED = 7


def collect(trajs: list[dict]) -> list[tuple[str, float, float, int]]:
    """→ [(档, ΔP, 锚点P, 轨迹序号)];每轨每腿每桶一条。"""
    out = []
    for ti, t in enumerate(trajs):
        pts = t["points"]
        anchors = pts[0][1:]
        for li, _leg in enumerate(_LEGS):
            a = anchors[li]
            if not (0 < a < 1):
                continue
            tier = tier_of(a)
            if tier is None:
                continue
            seen: set = set()
            for row in pts[1:]:
                h = row[0]
                for lo, hi in _BUCKETS:
                    if lo <= h < hi and lo not in seen:
                        seen.add(lo)
                        out.append((tier, row[1 + li] - a, a, ti))
                        break
    return out


def _boot(recs, by_traj, tier, mode, rng) -> tuple[float, float]:
    """mode='inc' 按增量重抽(高估精度) / 'traj' 按轨迹重抽(正确)。"""
    out = []
    ids = sorted({r[3] for r in recs})
    for _ in range(_N_BOOT):
        if mode == "inc":
            samp = [recs[rng.randrange(len(recs))] for _ in range(len(recs))]
        else:
            samp = []
            for _ in range(len(ids)):
                samp += [x for x in by_traj[ids[rng.randrange(len(ids))]] if x[0] == tier]
        if len(samp) >= _MIN_N:
            out.append(robust_sigma([d for _, d, _, _ in samp]))
    if not out:
        return float("nan"), float("nan")
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def main() -> int:
    db = sys.argv[1] if len(sys.argv) > 1 else "data/v4_observation.db"
    trajs = load_trajectories(db)
    recs = collect(trajs)
    by_traj: dict = {}
    for r in recs:
        by_traj.setdefault(r[3], []).append(r)
    print(f"合格轨迹 {len(trajs)} 条 → 增量 {len(recs)} 条(来自 {len(by_traj)} 条轨迹)\n")
    rng = random.Random(_SEED)
    print(f"{'档':<8}{'n增量':>7}{'n轨迹':>7}{'σ_P':>9}{'中位P':>8}{'σ_P/P':>8}"
          f"   {'按增量 95%CI':<20}{'按轨迹 95%CI(判据看这列)'}")
    for tier in ("sweet", "edge", "cold", "chalk"):
        rs = [r for r in recs if r[0] == tier]
        if len(rs) < _MIN_N:
            print(f"{tier:<8}{len(rs):>7}{'-':>7}   n<{_MIN_N},不报")
            continue
        s = robust_sigma([d for _, d, _, _ in rs])
        mp = st.median([r[2] for r in rs])
        il, ih = _boot(rs, by_traj, tier, "inc", rng)
        tl, th = _boot(rs, by_traj, tier, "traj", rng)
        print(f"{tier:<8}{len(rs):>7}{len({r[3] for r in rs}):>7}{s * 100:>8.2f}pp"
              f"{mp * 100:>7.1f}%{s / mp:>8.3f}   "
              f"[{il * 100:.2f}, {ih * 100:.2f}]pp      [{tl * 100:.2f}, {th * 100:.2f}]pp")
    print("\n⚠️ 判据一律读「按轨迹」列。prereg v2.2 §3 的 N = **轨迹数**,不是增量数。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
