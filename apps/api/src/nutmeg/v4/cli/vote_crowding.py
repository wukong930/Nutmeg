"""nutmeg-vote-crowding — 竞彩 散户拥挤曲线(探索 #3,只读测量).

Reads the append-only ``jingcai_vote_snapshots`` intraday series (populated from
the 3×/day vote cron going forward) and reports how retail support MOVES between
capture and kickoff: per-match drift + bandwagon direction. Runs on whatever has
accumulated; near-empty until the cron lays down ≥2 snapshots per match.

The lead-lag-vs-Pinnacle question is deferred until the series is thick enough to
join to odds_snapshots by timestamp. EXPLORATORY, zero API, no bets.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from nutmeg.v4.model.vote_crowding import MatchSeries, summarize


def _series(conn: sqlite3.Connection, since: str) -> list[MatchSeries]:
    # table may not exist yet on a fresh DB — tolerate it.
    try:
        rows = conn.execute(
            "SELECT match_date, home_zh, away_zh, captured_at, "
            "h_support, d_support, a_support FROM jingcai_vote_snapshots "
            "WHERE pool_code='HAD' AND h_support IS NOT NULL AND match_date >= ? "
            "ORDER BY match_date, home_zh, away_zh, captured_at",
            (since,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    grouped: dict[tuple, list] = {}
    for md, h, a, cap, hs, ds, as_ in rows:
        grouped.setdefault((md, h, a), []).append(
            (cap, (hs or 0.0, ds or 0.0, as_ or 0.0)))
    return [MatchSeries(md, h, a, snaps) for (md, h, a), snaps in grouped.items()]


def run(db: str | Path, since: str) -> int:
    with sqlite3.connect(str(db)) as conn:
        series = _series(conn, since)
    res = summarize(series)
    print(f"竞彩 散户拥挤曲线 · 窗口 ≥{since} · 快照覆盖 {res.n_matches} 场"
          f"(探索,只读,赛前可测)")
    if res.n_series == 0:
        print("有 ≥2 次日内快照的场: 0 —— 时间序列刚开始累积"
              "(vote cron 每日 3 次,每场需跨窗口才成序列)。\n"
              "注:jingcai_vote_snapshots 从本次改动上线的下一次 cron 起累积;"
              "在此之前每场只有 1 个快照,拥挤曲线尚不可测。")
        return 0
    print(f"\n有 ≥2 次日内快照的场(可测轨迹): {res.n_series}/{res.n_matches}")
    print(f"① 支持位移(逐腿 max−min 均值): {res.mean_drift_pp:.1f}pp "
          f"· 单场最大 {res.max_drift_pp:.1f}pp")
    print(f"② 跟风指数 = 早期热门腿支持「涨向开赛」的场占比: {res.bandwagon_frac*100:.0f}%")
    print("   (>50% = 人群随开赛临近往热门堆;<50% = 后期逆向/分散)")
    print("\n注:散户拥挤仅描述人群怎么动;lead-lag(散户 vs Pinnacle 谁先动)待"
          "序列攒厚后接 odds_snapshots 时间戳联结再测。探索性,不动钱。")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="竞彩 散户拥挤曲线(探索 #3)")
    ap.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    ap.add_argument("--since", default="2000-01-01", help="起始 match_date(默认全量)")
    args = ap.parse_args(argv)
    return run(args.db, args.since)


if __name__ == "__main__":
    raise SystemExit(main())
