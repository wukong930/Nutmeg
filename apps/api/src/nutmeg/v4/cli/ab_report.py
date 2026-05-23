"""nutmeg-ab-report — markdown A/B card: lineup-aware vs lineup-free settlements.

V6 W8. Reads the observation SQLite, slices settled recommendations by the
artifact's `model.with_lineups` flag (persisted into the recommend response
and onward into `recommendation_sessions.metadata_json`), and prints a
side-by-side comparison.

Usage:

    nutmeg-ab-report --db data/v4_observation.db --weeks 4 \\
        --out docs/weekly/2025-W18-ab.md

Exit codes:
    0 — report produced (regardless of which side wins, or no data)
    1 — DB missing or unreadable
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nutmeg.v4.observation import open_db
from nutmeg.v4.observation.ab_report import (
    format_ab_card,
    slice_lineup_aware,
    slice_lineup_free,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V6 W8 lineup A/B report")
    parser.add_argument("--db", required=True, help="Observation SQLite path")
    parser.add_argument(
        "--weeks",
        type=int,
        default=4,
        help="Restrict to sessions in the last N weeks (default 4). 0 = all-time.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output markdown file (default stdout)",
    )
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"ERROR: observation DB not found: {args.db}", file=sys.stderr)
        return 1

    start_iso = None
    if args.weeks and args.weeks > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=args.weeks)
        start_iso = cutoff.isoformat(timespec="seconds")

    with open_db(args.db) as conn:
        free = slice_lineup_free(conn, start_iso=start_iso)
        aware = slice_lineup_aware(conn, start_iso=start_iso)
    card = format_ab_card(free, aware, weeks=(args.weeks or None))

    if args.out:
        out_p = Path(args.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(card)
        print(f"Wrote {out_p}", file=sys.stderr)
    else:
        print(card)

    return 0


if __name__ == "__main__":
    sys.exit(main())
