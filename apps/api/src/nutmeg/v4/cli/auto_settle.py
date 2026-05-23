"""nutmeg-auto-settle — pull finished fixtures from API-Football and settle them.

V7 W2. Closes the manual-input gap that V6 W8's `nutmeg-record-outcome`
left open: pull yesterday's (or past N days') finished match scores
from API-Football, upsert into `match_outcomes`, run `settle_unsettled`
to close out any pending parlay recommendations.

Designed for the user's local crontab (NOT GH Actions — the
observation DB is user-local). Idempotent: re-running the same window
is free (upsert overwrites with identical values; settle skips
already-settled recs).

Usage:

    # Last 3 days, two leagues, write to local observation DB
    nutmeg-auto-settle --leagues EPL,ESP_LA_LIGA \\
        --db data/v4_observation.db --days 3

    # Dry run: report what WOULD be upserted/settled, don't write
    nutmeg-auto-settle --leagues EPL --db data/v4_observation.db \\
        --days 1 --dry-run

Status filter: only API-Football's "match is complete" statuses are
counted as settled outcomes. Live / in-progress / postponed / abandoned
are skipped (they'd settle the recommendation wrong).
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path
from typing import Iterable, Optional

from nutmeg.v4.data.sources import api_football
from nutmeg.v4.observation import open_db, settle_unsettled, upsert_outcome


log = logging.getLogger("auto_settle")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# API-Football short status codes that mean "match is complete, final
# score is real". Anything else (LIVE, HT, 1H, 2H, ET, P, BT, NS,
# PST, CANC, ABD, AWD, WO) is excluded — we'd record either a partial
# or a fabricated score otherwise.
FINISHED_STATUSES = frozenset({
    "FT",   # Match Finished
    "AET",  # Finished after Extra Time
    "PEN",  # Finished after Penalty shootout
})


def _date_range(start: dt.date, end: dt.date) -> list[dt.date]:
    """Inclusive list of dates from start..end."""
    n = (end - start).days
    return [start + dt.timedelta(days=i) for i in range(n + 1)]


def _extract_outcome_rows(
    fixtures: Iterable[dict],
    league_canonical: str,
) -> list[dict]:
    """Filter to finished fixtures + project to upsert_outcome's kwargs.

    Skips:
      - Non-finished status codes (LIVE / NS / PST / CANC / etc.)
      - Records missing goals (defensive against partial API payloads)
      - Records missing team names
    """
    rows: list[dict] = []
    for f in fixtures:
        fixture_blob = f.get("fixture") or {}
        status_short = (fixture_blob.get("status") or {}).get("short")
        if status_short not in FINISHED_STATUSES:
            continue

        iso_date = fixture_blob.get("date", "")
        match_date = iso_date[:10] if iso_date else None
        if not match_date:
            continue

        teams = f.get("teams") or {}
        home = (teams.get("home") or {}).get("name")
        away = (teams.get("away") or {}).get("name")
        if not (home and away):
            continue

        goals = f.get("goals") or {}
        hg = goals.get("home")
        ag = goals.get("away")
        if hg is None or ag is None:
            # Status said finished but goals missing → don't fabricate
            continue

        rows.append({
            "match_date": match_date,
            "league": league_canonical,
            "home_team": home,
            "away_team": away,
            "home_goals": int(hg),
            "away_goals": int(ag),
        })
    return rows


def gather_finished_outcomes(
    leagues: list[str],
    start_date: dt.date,
    end_date: dt.date,
    *,
    cache_dir: Path,
    refresh: bool = False,
) -> tuple[list[dict], int, dict[str, int]]:
    """Walk leagues × date-range, return (outcome rows, n_api_calls, per_league_count).

    The per-league count is a small diagnostic for the daily log so the
    user can spot a league that suddenly drops fixtures (API outage,
    league rename, etc.).
    """
    all_rows: list[dict] = []
    api_calls = 0
    per_league: dict[str, int] = {league: 0 for league in leagues}

    for league in leagues:
        for d in _date_range(start_date, end_date):
            try:
                fixtures = api_football.fetch_fixtures_for_date(
                    d,
                    league_canonical=league,
                    cache_dir=cache_dir,
                    refresh=refresh,
                )
                api_calls += 1
            except api_football.ApiFootballError as exc:
                log.warning("%s %s fixtures error: %s", league, d, exc)
                continue

            rows = _extract_outcome_rows(fixtures, league)
            per_league[league] += len(rows)
            all_rows.extend(rows)

    return all_rows, api_calls, per_league


def apply_outcomes(
    db_path: str | Path,
    outcome_rows: list[dict],
    *,
    dry_run: bool = False,
) -> dict:
    """Upsert outcome rows into the observation DB and run settle.

    Returns a summary dict — counts of upserted outcomes + settle results.
    In dry-run mode, the function returns the same summary shape but
    skips both writes and the settle pass (still useful for cron logs).
    """
    summary = {
        "n_outcome_rows": len(outcome_rows),
        "settled": 0,
        "still_unknown": 0,
        "dry_run": dry_run,
    }

    if dry_run or not outcome_rows:
        return summary

    with open_db(db_path) as conn:
        for row in outcome_rows:
            upsert_outcome(
                conn,
                match_date=row["match_date"],
                league=row["league"],
                home_team=row["home_team"],
                away_team=row["away_team"],
                home_goals=row["home_goals"],
                away_goals=row["away_goals"],
            )
        counts = settle_unsettled(conn)
    summary["settled"] = counts.get("settled", 0)
    summary["still_unknown"] = counts.get("still_unknown", 0)
    return summary


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V7 W2 — auto-settle from API-Football")
    p.add_argument(
        "--leagues",
        default="EPL,ESP_LA_LIGA",
        help="Comma-separated V4 canonical league codes (incl cups: UCL, FAC, etc.)",
    )
    p.add_argument(
        "--db", required=True,
        help="Local observation DB path (data/v4_observation.db typically)",
    )
    p.add_argument(
        "--days", type=int, default=3,
        help="Look back N days (inclusive of today). Default 3 catches yesterday + buffer.",
    )
    p.add_argument(
        "--end-date", type=_parse_date, default=None,
        help="YYYY-MM-DD end of window (default today)",
    )
    p.add_argument(
        "--cache-dir", type=Path,
        default=Path("data/external/api_football"),
    )
    p.add_argument(
        "--refresh-fixtures", action="store_true",
        help="Force re-fetch of /fixtures (overrides cache)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Don't write to DB; just report what would be upserted/settled",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    leagues = [s.strip() for s in args.leagues.split(",") if s.strip()]
    if not leagues:
        log.error("no leagues parsed from --leagues=%r", args.leagues)
        return 2

    end = args.end_date or dt.date.today()
    start = end - dt.timedelta(days=args.days)
    log.info("Window: %s → %s (inclusive); leagues=%s; dry_run=%s",
             start, end, leagues, args.dry_run)

    db_path = Path(args.db)
    if not args.dry_run and not db_path.exists():
        # open_db creates the file + schema, but warn so the user notices
        # they're seeding a brand-new DB (typo in --db path?)
        log.warning("observation DB does not exist; will create: %s", db_path)

    rows, n_calls, per_league = gather_finished_outcomes(
        leagues,
        start,
        end,
        cache_dir=args.cache_dir,
        refresh=args.refresh_fixtures,
    )
    log.info("Per-league finished-fixture counts: %s", per_league)
    log.info("Total: %d outcomes, %d API calls", len(rows), n_calls)

    summary = apply_outcomes(args.db, rows, dry_run=args.dry_run)

    if args.dry_run:
        log.info(
            "DRY-RUN: would upsert %d outcomes (not written; settle skipped)",
            summary["n_outcome_rows"],
        )
    else:
        log.info(
            "DONE: %d outcomes upserted, %d recs settled, %d still unknown",
            summary["n_outcome_rows"],
            summary["settled"],
            summary["still_unknown"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
