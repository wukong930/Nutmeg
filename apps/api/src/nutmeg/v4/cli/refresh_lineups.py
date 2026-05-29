"""nutmeg-refresh-lineups — daily incremental refresh of API-Football data.

V6 W8 daily-cron helper. Pulls fixtures + lineups + injuries for the past
N days (default 3) so the lineup cache stays fresh enough for daily
recommendations. Designed to be cron-friendly: idempotent, low API budget,
fast no-op when nothing's new.

Usage:

    # Daily: refresh yesterday + today
    nutmeg-refresh-lineups --leagues EPL,ESP_LA_LIGA --days 3

    # Initial backfill (already done by nutmeg-ingest-lineups; just here for
    # operational symmetry)
    nutmeg-refresh-lineups --leagues EPL --days 30

Budget:
    For N=3, 13 leagues:  ~150 fixtures + 150 lineup calls + 40 injuries
    ≈ 350 calls/day. Pro plan 7500/day → easy fit.
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


log = logging.getLogger("refresh_lineups")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _seasons_in_window(
    start_date: dt.date, end_date: dt.date, leagues: list[str] | None = None
) -> list[int]:
    """Football seasons whose calendar dates overlap [start, end].

    European leagues' 2024/25 season runs Aug 2024 - May 2025 (season-start
    year 2024). Calendar-year leagues (J-League etc.) run within one year, so
    their season-start year is just the date's year — handled by
    ``season_for_date``. Without ``leagues`` this falls back to the European
    heuristic (back-compatible).
    """
    from nutmeg.v4.data.sources.api_football import season_for_date

    seasons: set[int] = set()
    for lg in (leagues or [None]):
        for d in (start_date, end_date):
            seasons.add(season_for_date(d, lg))
    return sorted(seasons)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V6 W8 daily lineup refresh")
    p.add_argument(
        "--leagues",
        default="EPL,ESP_LA_LIGA",
        help="V4 canonical league codes (comma-separated)",
    )
    p.add_argument(
        "--days",
        type=int,
        default=3,
        help="Refresh window: today + N days before (default 3)",
    )
    p.add_argument(
        "--cache-dir",
        default="data/external/api_football",
    )
    p.add_argument(
        "--throttle-ms",
        type=int,
        default=200,
    )
    p.add_argument(
        "--include-injuries",
        action="store_true",
        help="Also fetch per-(team, season) injuries (per-season, ~one call each)",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    leagues = [s.strip() for s in args.leagues.split(",") if s.strip()]
    today = dt.date.today()
    earliest = today - dt.timedelta(days=args.days)
    seasons = _seasons_in_window(earliest, today, leagues)
    cache_dir = Path(args.cache_dir)
    throttle = args.throttle_ms / 1000.0

    log.info(
        "Refresh window: %s → %s; leagues=%s; seasons=%s",
        earliest, today, leagues, seasons,
    )

    total_calls = 0
    n_fixtures_refreshed = 0
    n_lineups = 0

    for league in leagues:
        for season in seasons:
            # 1. /fixtures for the season (force refresh = catch newly-finalized fixtures)
            try:
                fixtures = api_football._request(
                    "/fixtures",
                    {
                        "league": api_football.league_id(league),
                        "season": season,
                    },
                    cache_dir=cache_dir,
                    refresh=True,
                )
                total_calls += 1
            except api_football.ApiFootballError as exc:
                log.warning("%s %d fixtures error: %s", league, season, exc)
                continue

            # 2. Filter to fixtures inside the refresh window
            in_window = [
                f for f in fixtures
                if (f["fixture"]["date"][:10]
                    >= earliest.isoformat()
                    and f["fixture"]["date"][:10] <= today.isoformat())
            ]
            log.info(
                "%s %d/%d: %d fixtures in window",
                league, season % 100, (season + 1) % 100, len(in_window),
            )

            # 3. /fixtures/lineups for each (idempotent: cached fixtures skip the API call
            #    UNLESS we pass refresh=True, which we don't here so finished matches
            #    keep their cached lineups)
            for f in in_window:
                fid = f["fixture"]["id"]
                status = f["fixture"]["status"]["short"]
                valid = {"FT", "AET", "PEN", "1H", "2H", "HT", "ET", "P", "BT"}
                if status not in valid:
                    continue
                try:
                    payload = api_football.fetch_lineups(fid, cache_dir=cache_dir)
                    total_calls += 1
                    if payload:
                        n_lineups += 1
                        n_fixtures_refreshed += 1
                except api_football.ApiFootballError as exc:
                    log.warning("fixture %d lineups error: %s", fid, exc)
                time.sleep(throttle)

            # 4. Injuries (per-team, per-season). Only call if requested AND
            #    the team appeared in the window.
            if args.include_injuries:
                team_ids = {
                    f["teams"]["home"]["id"] for f in in_window
                } | {
                    f["teams"]["away"]["id"] for f in in_window
                }
                for tid in team_ids:
                    try:
                        api_football.fetch_injuries(
                            tid, season, cache_dir=cache_dir, refresh=True,
                        )
                        total_calls += 1
                    except api_football.ApiFootballError as exc:
                        log.warning("team %d injuries error: %s", tid, exc)
                    time.sleep(throttle)

    log.info(
        "DONE: %d API calls, %d fixtures refreshed, %d lineup payloads",
        total_calls, n_fixtures_refreshed, n_lineups,
    )

    # Write a small summary card so the daily cron has something to commit
    summary = {
        "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "leagues": leagues,
        "seasons": seasons,
        "window_start": earliest.isoformat(),
        "window_end": today.isoformat(),
        "n_api_calls": total_calls,
        "n_fixtures_refreshed": n_fixtures_refreshed,
        "n_lineups_fetched": n_lineups,
    }
    summary_path = cache_dir / f"_daily_refresh_{today.isoformat()}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info("Summary → %s", summary_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
