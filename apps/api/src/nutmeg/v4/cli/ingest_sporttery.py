"""nutmeg-ingest-sporttery — harvest 竞彩 SP into jingcai_sp (the soft-book feed).

Pulls the current 竞彩 matches from the public sporttery uniform endpoint, maps
team names to our canonical English (so they join Pinnacle/odds_snapshots + the
settler), and writes one ``had`` + one ``hhad`` row per mappable match
(source='sporttery', protect_manual=True so it NEVER clobbers a line you
hand-priced in 市场/标准 模式). Fail-soft: a fetch failure just writes 0 rows.

Low-frequency by design — run once after the ~23:00 竞彩 freeze. Read-only; never
touches your betting account. Personal/local use only.
"""
from __future__ import annotations

import argparse
import logging


def harvest_to_db(db_path, *, pool_codes: str = "had,hhad", refresh: bool = False,
                  matches: list[dict] | None = None, protect_manual: bool = True,
                  phase: str = "close") -> dict:
    """Upsert the current 竞彩 SP into jingcai_sp (source=sporttery). Fetches if
    ``matches`` is None. Returns ``{matches, mapped, unmapped, had, hhad}``. Shared
    by the CLI and the 🎯 刷新竞彩 endpoint.

    ``protect_manual``: True (default, for the unattended cron) skips any row a user
    hand-priced in 市场/标准 模式. The 🎯 button passes False — an *explicit* refresh
    means "give me the latest official SP", so it must overwrite the (often stale)
    market_mode capture; otherwise the button fetches fresh data but can't show it."""
    from nutmeg.v4.observation.jingcai_sp import record_jingcai_sp
    if matches is None:
        from nutmeg.v4.data.sources.sporttery import fetch_lottery_matches
        matches = fetch_lottery_matches(pool_codes=pool_codes, refresh=refresh)
    mapped = [m for m in matches if m["home_en"] and m["away_en"]]
    had_w = hhad_w = 0
    for m in mapped:
        common = {
            "match_date": m["match_date"], "home_team": m["home_en"],
            "away_team": m["away_en"], "league": m["league_cn"],
            "kickoff_utc": m.get("kickoff_utc"),
            "source": "sporttery", "protect_manual": protect_manual,
            "phase": phase,  # 'open' (11:00 开售) stamps jc_open_*; 'close' = 终盘 (default)
        }
        if m["had"]:
            jh, jd, ja = m["had"]
            had_w += int(record_jingcai_sp(
                db_path, jc_home=jh, jc_draw=jd, jc_away=ja, market="had", **common))
        if m["hhad"]:
            jh, jd, ja, line = m["hhad"]
            hhad_w += int(record_jingcai_sp(
                db_path, jc_home=jh, jc_draw=jd, jc_away=ja, market="hhad",
                handicap_home=line, **common))
    return {"matches": len(matches), "mapped": len(mapped),
            "unmapped": len(matches) - len(mapped), "had": had_w, "hhad": hhad_w}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="harvest 竞彩 SP → jingcai_sp (软盘喂数)")
    ap.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    ap.add_argument("--pool-codes", default="had,hhad", help="竞彩 pools to pull")
    ap.add_argument("--refresh", action="store_true", help="bypass the TTL cache")
    ap.add_argument("--dry-run", action="store_true", help="show what would be written")
    ap.add_argument("--phase", choices=["open", "close"], default="close",
                    help="open=11:00 开售初盘(记 jc_open_*,set-once) | close=终盘(默认)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from nutmeg.v4.data.sources.sporttery import fetch_lottery_matches

    matches = fetch_lottery_matches(pool_codes=args.pool_codes, refresh=args.refresh)
    print(f"竞彩抓取: {len(matches)} 场")
    if not matches:
        print("  (端点无数据或失败 — 失败软,未写入)")
        return 0

    mapped = [m for m in matches if m["home_en"] and m["away_en"]]
    unmapped = [m for m in matches if not (m["home_en"] and m["away_en"])]
    print(f"队名映射: {len(mapped)}/{len(matches)} 成功", end="")
    if unmapped:
        print(" · 未映射: " + ", ".join(
            f"{m['home_cn']}/{m['away_cn']}" for m in unmapped[:8]))
    else:
        print()

    if args.dry_run:
        print("\n样例(将写入,英文规范名):")
        for m in mapped[:6]:
            print(f"  {m['home_en']} vs {m['away_en']}  {m['match_date']}  "
                  f"had={m['had']}  hhad={m['hhad']}")
        print("\n(dry-run — 未写库)")
        return 0

    r = harvest_to_db(args.db, matches=matches, phase=args.phase)
    print(f"\n写入 jingcai_sp: 胜平负 {r['had']} · 让球 {r['hhad']}  "
          f"(source=sporttery, phase={args.phase}, 不覆盖手填)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
