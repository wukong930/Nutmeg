"""nutmeg-closing-odds — capture near-KO Pinnacle CLOSING lines → odds_snapshots.

Snapshots ``odds_api.fetch_pinnacle_lookup`` straight into
``odds_snapshots(source='closing')``, bypassing the cup-market gather (whose
fixture-matching drops most matches → it writes ~nothing). Run frequently (cron,
~every 30 min) so each match gets a Pinnacle line captured close to its OWN
kickoff = the true close — fixes the median ~5h-stale anchor (③), de-noises the
soft-water ② comparison, and gives proper CLV. The 23:20 vote backfill then
co-locates the freshest line onto each jingcai_vote row. Read-only on the betting
side; cheap (~1 Odds-API request per sport). Fail-soft.
"""
from __future__ import annotations

import argparse
import logging


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="capture Pinnacle 收盘线 → odds_snapshots(source=closing)")
    ap.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    ap.add_argument("--sports", default="WC",
                    help="逗号分隔的运动短键 (WC,UCL,UEL,EPL,…) — 只拉在季的(每个=1 Odds-API 调)")
    ap.add_argument("--no-refresh", action="store_true",
                    help="用缓存(默认强制拉鲜,收盘捕获要鲜)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from nutmeg.v4.observation.closing_odds import capture_closing_pinnacle

    sports = [s.strip() for s in args.sports.split(",") if s.strip()]
    r = capture_closing_pinnacle(args.db, sports, refresh=not args.no_refresh)
    total = sum(r.values())
    print("收盘锚写入 odds_snapshots(source=closing): "
          + " · ".join(f"{k} {v}" for k, v in r.items())
          + f"  (共 {total} 行新状态)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
