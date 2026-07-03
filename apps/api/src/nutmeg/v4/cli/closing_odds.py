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
    ap.add_argument("--sports", default="auto",
                    help="逗号分隔的运动短键 (WC,UCL,EPL,…),或 auto = 从 AF 赛程算"
                         "「未来 75 分钟内开球」的联赛集(体检 Wave2 — 只在临开球时"
                         "拉该 sport,静默时段 0 credit;硬编单一联赛=季末链停摆雷)")
    ap.add_argument("--lookahead-minutes", type=int, default=75,
                    help="auto 模式的开球前瞻窗 (默认 75 = 30min cron 的 2 tick+余量)")
    ap.add_argument("--no-refresh", action="store_true",
                    help="用缓存(默认强制拉鲜,收盘捕获要鲜)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from nutmeg.v4.observation.closing_odds import (
        capture_closing_pinnacle,
        resolve_auto_sports,
    )

    if args.sports.strip().lower() == "auto":
        sports = resolve_auto_sports(lookahead_minutes=args.lookahead_minutes)
        if not sports:
            print("收盘锚: 前瞻窗内无 SPORT_KEYS 联赛开球 — 本轮 0 次 Odds-API 调用")
            return 0
        print(f"收盘锚 auto: 前瞻 {args.lookahead_minutes}min 内开球联赛 = {','.join(sports)}")
    else:
        sports = [s.strip() for s in args.sports.split(",") if s.strip()]
    r = capture_closing_pinnacle(args.db, sports, refresh=not args.no_refresh)
    total = sum(r.values())
    print("收盘锚写入 odds_snapshots(source=closing): "
          + " · ".join(f"{k} {v}" for k, v in r.items())
          + f"  (共 {total} 行新状态)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
