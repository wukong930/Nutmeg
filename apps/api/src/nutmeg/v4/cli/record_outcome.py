"""V4 outcome recording CLI.

Two modes:

  Single match:
    python -m nutmeg.v4.cli.record_outcome \
      --db data/v4_observation.db \
      --date 2025-08-17 --league EPL \
      --home Arsenal --away Liverpool \
      --home-goals 2 --away-goals 1

  Batch from CSV (one row per match):
    python -m nutmeg.v4.cli.record_outcome --db data/v4_observation.db --csv results.csv

  CSV format: date,league,home_team,away_team,home_goals,away_goals

After recording, automatically attempts to settle any unsettled recommendation
whose all legs now have known outcomes. Prints how many were settled.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from nutmeg.v4.observation import open_db, settle_unsettled, upsert_outcome


def _record_one(conn, *, match_date, league, home_team, away_team, home_goals, away_goals) -> None:
    upsert_outcome(
        conn,
        match_date=str(match_date),
        league=league,
        home_team=home_team,
        away_team=away_team,
        home_goals=int(home_goals),
        away_goals=int(away_goals),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record actual match outcomes + auto-settle")
    parser.add_argument("--db", default="data/v4_observation.db",
                        help="SQLite observation DB path")
    # Single mode
    parser.add_argument("--date", help="Match date YYYY-MM-DD (single mode)")
    parser.add_argument("--league")
    parser.add_argument("--home", dest="home_team")
    parser.add_argument("--away", dest="away_team")
    parser.add_argument("--home-goals", type=int)
    parser.add_argument("--away-goals", type=int)
    # Batch mode
    parser.add_argument("--csv", help="CSV with columns date,league,home_team,away_team,home_goals,away_goals")
    # Settlement control
    parser.add_argument("--no-settle", action="store_true",
                        help="Skip auto-settlement after recording")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if not args.csv and not (args.date and args.league and args.home_team and
                              args.away_team and args.home_goals is not None and
                              args.away_goals is not None):
        parser.error("Either --csv or all single-mode args (--date --league --home --away --home-goals --away-goals)")

    n_recorded = 0
    with open_db(args.db) as conn:
        if args.csv:
            csv_path = Path(args.csv)
            if not csv_path.exists():
                print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
                return 1
            with csv_path.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                required = {"date", "league", "home_team", "away_team", "home_goals", "away_goals"}
                missing = required - set(reader.fieldnames or [])
                if missing:
                    print(f"ERROR: CSV missing columns: {missing}", file=sys.stderr)
                    return 1
                for row in reader:
                    _record_one(
                        conn,
                        match_date=row["date"],
                        league=row["league"],
                        home_team=row["home_team"],
                        away_team=row["away_team"],
                        home_goals=row["home_goals"],
                        away_goals=row["away_goals"],
                    )
                    n_recorded += 1
        else:
            _record_one(
                conn,
                match_date=args.date,
                league=args.league,
                home_team=args.home_team,
                away_team=args.away_team,
                home_goals=args.home_goals,
                away_goals=args.away_goals,
            )
            n_recorded = 1

        if not args.quiet:
            print(f"Recorded {n_recorded} outcome(s) to {args.db}", file=sys.stderr)

        if not args.no_settle:
            counts = settle_unsettled(conn)
            if not args.quiet:
                print(f"Settlement: {counts['settled']} settled, "
                      f"{counts['still_unknown']} still pending, "
                      f"{counts['errors']} errors", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
