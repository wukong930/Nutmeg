"""nutmeg-ingest-lineups — pull lineup data for a league+season from API-Football.

V6 W5 — populates data/external/api_football/ with the fixture + lineup
JSON files that lineup_lookup builds into the feature-pipeline lookup.

Usage:

    nutmeg-ingest-lineups --league EPL --season 2024 --max-fixtures 50

Budget: each league-season = ~380 fixtures = 380 + 1 (fixtures list) calls.
At Pro plan 7,500/day we can do ~19 league-seasons/day comfortably.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
import time
from pathlib import Path

from nutmeg.v4.data.sources import api_football


log = logging.getLogger("ingest_lineups")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _request_fixtures_for_season(
    league_canonical: str,
    season: int,
    cache_dir: Path,
    refresh: bool,
) -> list[dict]:
    """Single API-Football /fixtures call covering an entire season.

    `/fixtures?league={id}&season={year}` returns all fixtures in one
    response — far more efficient than per-date queries.
    """
    return api_football._request(
        "/fixtures",
        {"league": api_football.league_id(league_canonical), "season": season},
        cache_dir=cache_dir,
        refresh=refresh,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V6 W5 lineup data ingest from API-Football")
    p.add_argument("--league", required=True,
                   help="V4 canonical league code (e.g. EPL, ESP_LA_LIGA)")
    p.add_argument("--season", type=int, required=True,
                   help="Season start year (e.g. 2024 for 2024-25)")
    p.add_argument("--max-fixtures", type=int, default=None,
                   help="Stop after N fixtures (debugging). Default: all fixtures in the season")
    p.add_argument("--cache-dir", default="data/external/api_football",
                   help="Where API-Football JSON caches go")
    p.add_argument("--refresh", action="store_true",
                   help="Re-fetch even if cache exists")
    p.add_argument("--throttle-ms", type=int, default=200,
                   help="Sleep between calls to be polite (default 200ms)")
    p.add_argument("--include-injuries", action="store_true",
                   help="Also fetch per-team injuries for each match (~2x calls)")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fixtures list (single call)
    log.info("Fetching fixtures: league=%s season=%d", args.league, args.season)
    fixtures = _request_fixtures_for_season(
        args.league, args.season, cache_dir, args.refresh,
    )
    log.info("Got %d fixtures", len(fixtures))

    if args.max_fixtures:
        fixtures = fixtures[: args.max_fixtures]
        log.info("Limiting to first %d fixtures (--max-fixtures)", args.max_fixtures)

    # Only fetch lineups for completed or in-progress fixtures (lineups
    # not yet published for matches > 1h in the future)
    valid_statuses = {"FT", "AET", "PEN", "1H", "2H", "HT", "ET", "P", "BT"}
    eligible = [
        f for f in fixtures
        if f.get("fixture", {}).get("status", {}).get("short") in valid_statuses
    ]
    log.info("Eligible (started/finished) fixtures: %d / %d", len(eligible), len(fixtures))

    throttle = args.throttle_ms / 1000.0
    n_fetched = 0
    n_missing = 0
    for i, f in enumerate(eligible):
        fixture_id = f["fixture"]["id"]
        home_name = f["teams"]["home"]["name"]
        away_name = f["teams"]["away"]["name"]
        date_str = f["fixture"]["date"][:10]

        try:
            lineups = api_football.fetch_lineups(
                fixture_id, cache_dir=cache_dir, refresh=args.refresh,
            )
        except api_football.ApiFootballError as e:
            log.warning("Fixture %d lineups error: %s", fixture_id, e)
            n_missing += 1
            continue

        if not lineups:
            n_missing += 1
        else:
            n_fetched += 1

        if (i + 1) % 25 == 0:
            log.info(
                "Progress %d/%d  (fixtures with lineups: %d, missing: %d)",
                i + 1, len(eligible), n_fetched, n_missing,
            )

        if args.include_injuries:
            for team in (f["teams"]["home"], f["teams"]["away"]):
                try:
                    api_football.fetch_injuries(
                        team["id"], args.season,
                        cache_dir=cache_dir, refresh=args.refresh,
                    )
                except api_football.ApiFootballError as e:
                    log.warning("Team %s injuries error: %s", team.get("name"), e)
            time.sleep(throttle)

        time.sleep(throttle)

    log.info(
        "DONE: %d fixtures with lineups, %d missing/empty (total %d eligible)",
        n_fetched, n_missing, len(eligible),
    )

    # Write a summary card so the next ablation knows what's in cache
    summary = {
        "league": args.league,
        "season": args.season,
        "n_fixtures_total": len(fixtures),
        "n_eligible": len(eligible),
        "n_lineups_fetched": n_fetched,
        "n_lineups_missing": n_missing,
        "include_injuries": args.include_injuries,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    summary_path = cache_dir / f"_summary_{args.league}_{args.season}.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info("Wrote summary: %s", summary_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
