"""Close-drift measurement — how well does the CURRENT Pinnacle line estimate the CLOSE?

Freeze-gap betting prices EV off the live Pinnacle line as a stand-in for the
close (the EV yardstick is P_close). The implicit estimator today is IDENTITY
(p̂_close = p_now). This harness measures, from accumulated ``odds_snapshots``
trajectories:

  1. σ_P(τ): RMSE of the identity estimator by time-to-kickoff bucket — the
     direct input to the variance threshold (σ_EV(τ) ≈ σ_P(τ)·SP): how much the
     +5% bar must widen when betting τ hours before kickoff.
  2. Systematic drift: does the FAVOURITE's fair P move in a predictable
     direction toward the close (favourite-longshot unwind)? Mean signed drift
     + OLS slope on (p_fav − 0.5), with honest t-stats (fixtures = units).
  3. Verdict guidance: a drift CORRECTION is only worth building if (2) is
     significant; otherwise identity stands and (1) is the deliverable.

Read-only; rerun any time (the closing cron thickens true closes daily).

    PYTHONPATH=apps/api/src .venv/bin/python scripts/measure_close_drift.py \
        [--db data/v4_observation.db] [--close-win-min 75]
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import statistics as st
from datetime import UTC, datetime

from nutmeg.v4.model.devig import devig_1x2

BUCKETS: list[tuple[float, float]] = [
    (0, 3), (3, 6), (6, 12), (12, 24), (24, 48), (48, 96), (96, 1e9)]


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    t = str(s).strip().replace("T", " ")[:19]
    try:
        return datetime.strptime(t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def load_trajectories(db: str) -> dict[tuple, dict]:
    """fixture → {"ko": kickoff, "league": str, "snaps": [(t, (pH,pD,pA)), ...]}
    De-vigged (WPO), pre-kickoff only, deduped by capture time, sorted."""
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT match_date, home_team, away_team, league, captured_at, kickoff_utc,"
        "       psc_home, psc_draw, psc_away FROM odds_snapshots"
        " WHERE psc_home>1 AND psc_draw>1 AND psc_away>1"
        "   AND kickoff_utc IS NOT NULL").fetchall()
    fx: dict[tuple, dict] = {}
    for r in rows:
        t, ko = _ts(r["captured_at"]), _ts(r["kickoff_utc"])
        if not t or not ko or t > ko:      # close = PRE-kickoff by definition
            continue
        p = devig_1x2(r["psc_home"], r["psc_draw"], r["psc_away"])
        if p is None:
            continue
        k = (r["match_date"], r["home_team"], r["away_team"])
        d = fx.setdefault(k, {"ko": ko, "league": r["league"], "snaps": {}})
        d["snaps"][t] = tuple(p)           # dedup identical capture times
    for d in fx.values():
        d["snaps"] = sorted(d["snaps"].items())
    return fx


def build_pairs(fx: dict, close_win_h: float) -> tuple[list[dict], int]:
    """One (predictor → close) pair per fixture per τ-bucket: the LAST snapshot
    inside the bucket. Returns (pairs, n_fixtures_with_close)."""
    pairs: list[dict] = []
    n_close = 0
    for key, d in fx.items():
        snaps, ko = d["snaps"], d["ko"]
        t_last, p_close = snaps[-1]
        if (ko - t_last).total_seconds() / 3600 > close_win_h:
            continue                       # no true close for this fixture
        n_close += 1
        for lo, hi in BUCKETS:
            best = None
            for t, p in snaps[:-1]:
                tau = (ko - t).total_seconds() / 3600
                if tau <= close_win_h:     # that's the close itself, not a predictor
                    continue
                if lo < tau <= hi and (best is None or t > best[0]):
                    best = (t, p, tau)
            if best:
                _, p_snap, tau = best
                fav = max(range(3), key=lambda i: p_snap[i])
                pairs.append({
                    "fixture": key, "league": d["league"], "bucket": (lo, hi),
                    "tau": tau, "p_snap": p_snap, "p_close": p_close, "fav": fav,
                })
    return pairs, n_close


def _fmt_bucket(b: tuple[float, float]) -> str:
    return f"{b[0]:.0f}-{'∞' if b[1] > 500 else f'{b[1]:.0f}'}h"


def report(pairs: list[dict], n_close: int, close_win_h: float) -> None:
    print(f"\n== 收盘线漂移测量 · 真收盘定义 ≤{close_win_h*60:.0f}min · "
          f"有收盘场次 N={n_close} ==")
    print("   τ桶      场次  RMSE(pp)  MAE(pp)  |Δp|p90   fav漂移(pp)     t     slope b     t_b")
    print("   " + "-" * 92)
    for b in BUCKETS:
        grp = [x for x in pairs if x["bucket"] == b]
        if len(grp) < 3:
            if grp:
                print(f"   {_fmt_bucket(b):8} {len(grp):4}   (n<3 不报)")
            continue
        # (1) identity error, all 3 legs pooled
        diffs = [x["p_close"][i] - x["p_snap"][i] for x in grp for i in range(3)]
        rmse = math.sqrt(st.fmean(d * d for d in diffs)) * 100
        mae = st.fmean(abs(d) for d in diffs) * 100
        p90 = sorted(abs(d) for d in diffs)[int(0.9 * (len(diffs) - 1))] * 100
        # (2) favourite signed drift (1 obs per fixture → honest units)
        fd = [x["p_close"][x["fav"]] - x["p_snap"][x["fav"]] for x in grp]
        m = st.fmean(fd)
        sd = st.stdev(fd) if len(fd) > 1 else float("nan")
        t = m / (sd / math.sqrt(len(fd))) if sd and sd > 0 else float("nan")
        # OLS slope of fav drift on (p_fav − 0.5): favourite-longshot signature
        xs = [x["p_snap"][x["fav"]] - 0.5 for x in grp]
        sxx = sum(v * v for v in xs)
        if sxx > 1e-9:
            bb = sum(v * w for v, w in zip(xs, fd, strict=True)) / sxx
            resid = [w - bb * v for v, w in zip(xs, fd, strict=True)]
            dfree = max(len(xs) - 1, 1)
            se = math.sqrt(st.fmean(r * r for r in resid) * len(xs) / dfree / sxx)
            tb = bb / se if se > 0 else float("nan")
        else:
            bb, tb = float("nan"), float("nan")
        print(f"   {_fmt_bucket(b):8} {len(grp):4}   {rmse:6.2f}   {mae:6.2f}"
              f"   {p90:6.2f}   {m*100:+9.2f}  {t:+6.2f}   {bb:+8.3f}  {tb:+6.2f}")
    print("\n   读法: RMSE(τ)=σ_P(τ) → σ_EV≈σ_P·SP(方差门槛的直接输入)。")
    print("   fav漂移 t 与 slope t_b 任一 |t|≥2.8 才算可建模的系统性成分(小N原型,")
    print("   门槛沿用预注册口径);否则恒等映射成立,产出=σ_P(τ) 曲线本身。")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--close-win-min", type=float, default=75.0,
                    help="真收盘 = 距开赛 ≤ 这么多分钟的最后一拍 (default 75)")
    args = ap.parse_args(argv)

    fx = load_trajectories(args.db)
    pairs, n_close = build_pairs(fx, args.close_win_min / 60)
    if not pairs:
        print("没有 (τ快照 → 真收盘) 配对 — closing cron 攒几天后再跑。")
        return 0
    report(pairs, n_close, args.close_win_min / 60)
    # league mix (applicability caveat: WC-dominated sample ≠ autumn leagues)
    from collections import Counter
    mix = Counter(x["league"] or "?" for x in pairs)
    print(f"\n   样本联赛构成: {dict(mix.most_common(6))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
