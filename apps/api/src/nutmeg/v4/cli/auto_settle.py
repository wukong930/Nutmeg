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

        # 竞彩 settles 胜平负/让球 on the 90-MINUTE result. For cup knockouts
        # decided in extra time / penalties (status AET / PEN), fixture["goals"]
        # is the score AFTER extra time, so prefer score.fulltime (the 90' line)
        # when both legs are present; fall back to goals for normal FT matches
        # (where fulltime == goals) and partial payloads.
        ft = (f.get("score") or {}).get("fulltime") or {}
        goals = f.get("goals") or {}
        if ft.get("home") is not None and ft.get("away") is not None:
            hg, ag = ft["home"], ft["away"]
        else:
            hg, ag = goals.get("home"), goals.get("away")
        if hg is None or ag is None:
            # Status said finished but no 90' score → don't fabricate
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


def pending_leagues(db_path: str | Path, start: dt.date, end: dt.date) -> list[str]:
    """V12 W8 — leagues with a recorded prediction in [start, end] but no
    match_outcome yet: exactly what auto-settle needs to fetch results for.

    Derives the settle league set from the DB instead of a hardcoded list, so
    it automatically covers the model leagues AND 市场模式 surfaces (J1, cups)
    the moment the user records a bet there — with zero API calls wasted on
    leagues that have nothing pending."""
    import sqlite3

    if not Path(db_path).exists():
        return []
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            """
            SELECT DISTINCT sp.league
            FROM single_predictions sp
            WHERE sp.match_date >= ? AND sp.match_date <= ?
              AND NOT EXISTS (
                SELECT 1 FROM match_outcomes mo
                WHERE mo.league = sp.league
                  AND mo.match_date = sp.match_date
                  AND mo.home_team = sp.home_team
                  AND mo.away_team = sp.away_team
              )
            ORDER BY sp.league
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
    finally:
        con.close()
    return [r[0] for r in rows if r[0]]


def pending_match_pairs(
    db_path: str | Path,
    *,
    before: dt.date,
    max_age_days: int = 90,
) -> list[tuple[str, dt.date]]:
    """体检(2026-06-10)— orphan rescue: (league, match_date) pairs recorded
    BEFORE the normal settle window that still have no outcome.

    The 3-day window used to be a CEILING: any bet that missed it (mis-labelled
    identity fixed later, cron down that night, API hiccup) hung 未结算 forever
    — the cron never looked back. Pairs are exact, so the rescue costs one
    /fixtures call per orphan day; bounded at ``max_age_days`` so antique rows
    can't burn quota."""
    import sqlite3

    if not Path(db_path).exists():
        return []
    floor = before - dt.timedelta(days=max_age_days)
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            """
            SELECT DISTINCT sp.league, sp.match_date
            FROM single_predictions sp
            WHERE sp.match_date < ? AND sp.match_date >= ?
              AND NOT EXISTS (
                SELECT 1 FROM match_outcomes mo
                WHERE mo.league = sp.league
                  AND mo.match_date = sp.match_date
                  AND mo.home_team = sp.home_team
                  AND mo.away_team = sp.away_team
              )
            ORDER BY sp.match_date, sp.league
            """,
            (before.isoformat(), floor.isoformat()),
        ).fetchall()
    finally:
        con.close()
    return [(r[0], dt.date.fromisoformat(r[1])) for r in rows]


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V7 W2 — auto-settle from API-Football")
    p.add_argument(
        "--leagues",
        default="EPL,ESP_LA_LIGA",
        help="Comma-separated V4 canonical league codes (incl cups: UCL, FAC, "
             "etc.), or 'auto' to derive the set from leagues with unsettled "
             "recorded bets in the DB (covers model leagues + J1 + cups).",
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
    p.add_argument(
        "--no-orphan-scan", action="store_true",
        help="体检 — skip the rescue pass for pending bets OLDER than the "
             "window (auto mode only; exact (league,date) pairs, ≤90d back).",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    end = args.end_date or dt.date.today()
    start = end - dt.timedelta(days=args.days)

    orphan_pairs: list[tuple[str, dt.date]] = []
    if args.leagues.strip().lower() == "auto":
        leagues = pending_leagues(args.db, start, end)
        if not args.no_orphan_scan:
            orphan_pairs = pending_match_pairs(args.db, before=start)
            if orphan_pairs:
                log.info(
                    "orphan scan: %d pending (league, date) pairs older than "
                    "the window → %s", len(orphan_pairs),
                    [(lg, d.isoformat()) for lg, d in orphan_pairs],
                )
        if not leagues and not orphan_pairs:
            log.info(
                "auto: no leagues with unresolved recorded fixtures in %s → %s "
                "and no orphans; nothing to settle (0 API calls)", start, end,
            )
            return 0
        if leagues:
            log.info("auto: leagues with pending recorded fixtures → %s", leagues)
    else:
        leagues = [s.strip() for s in args.leagues.split(",") if s.strip()]
        if not leagues:
            log.error("no leagues parsed from --leagues=%r", args.leagues)
            return 2

    log.info("Window: %s → %s (inclusive); leagues=%s; dry_run=%s",
             start, end, leagues, args.dry_run)

    db_path = Path(args.db)
    if not args.dry_run and not db_path.exists():
        # open_db creates the file + schema, but warn so the user notices
        # they're seeding a brand-new DB (typo in --db path?)
        log.warning("observation DB does not exist; will create: %s", db_path)

    if leagues:
        rows, n_calls, per_league = gather_finished_outcomes(
            leagues,
            start,
            end,
            cache_dir=args.cache_dir,
            refresh=args.refresh_fixtures,
        )
    else:  # orphan-only run (auto mode, nothing pending inside the window)
        rows, n_calls, per_league = [], 0, {}
    # 体检 — orphan rescue: exact (league, date) fetches for pending bets the
    # window aged out of. Each pair failing (unknown league code, API error)
    # must not poison the rest — log and continue.
    for lg, d in orphan_pairs:
        try:
            r2, c2, p2 = gather_finished_outcomes(
                [lg], d, d, cache_dir=args.cache_dir, refresh=args.refresh_fixtures,
            )
        except Exception:  # noqa: BLE001
            log.warning("orphan scan failed for (%s, %s); skipping", lg, d)
            continue
        rows.extend(r2)
        n_calls += c2
        for k, v in p2.items():
            per_league[k] = per_league.get(k, 0) + v
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
