"""nutmeg-ingest-odds — pull today's /odds from API-Football → fixtures CSV.

V7 W1. The first piece of Track C: remove the manual `fixtures.csv`
typing step from the daily prediction loop. Pulls per-fixture odds for
the requested leagues + date, parses the sharp book's 1X2 (and O/U
where available), writes a CSV that drops straight into
`nutmeg-recommend` / `nutmeg-rec`.

Usage:

    # Today's EPL + La Liga, write CSV to disk
    nutmeg-ingest-odds --leagues EPL,ESP_LA_LIGA \\
        --date 2025-08-17 --out today.csv

    # Stdout (pipe into nutmeg-recommend directly)
    nutmeg-ingest-odds --leagues EPL --date 2025-08-17 | \\
        nutmeg-recommend --fixtures - --bankroll 1000

Default bookmaker is Pinnacle (id=4) — the sharpest book, so its 1X2
closing odds are the canonical "market truth" the V4/V5/V6 model was
trained against. Pass `--bookmaker-id 8` for Bet365 etc.

Budget: 1 /fixtures call per league + 1 /odds call per fixture. For
EPL today (~10 matches) ≈ 11 API calls. Cached by (endpoint, params)
so re-runs the same day are free.

Cup competitions work too:
    nutmeg-ingest-odds --leagues UCL,EPL --date 2025-09-15
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import sys
from io import StringIO
from pathlib import Path
from typing import Optional

from nutmeg.v4.data.odds_parser import (
    PINNACLE_BOOKMAKER_ID,
    fixture_envelope_to_csv_row,
)
from nutmeg.v4.data.sources import api_football


log = logging.getLogger("ingest_odds")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


CSV_COLUMNS = [
    "date", "league", "home_team", "away_team",
    "psc_home", "psc_draw", "psc_away",
    "psc_over25", "psc_under25",
    # Lottery-specific odds left blank — the user fills these from the
    # 竞彩 terminal at bet time (浮动 SP).
    "handicap_home",
    "odds_1x2_H", "odds_1x2_D", "odds_1x2_A",
    "odds_handicap_H", "odds_handicap_D", "odds_handicap_A",
]


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _gather_rows(
    leagues: list[str],
    on_date: dt.date,
    *,
    cache_dir: Path,
    bookmaker_id: int,
    refresh_fixtures: bool,
    refresh_odds: bool,
) -> tuple[list[dict], int, int]:
    """Walk leagues × today's fixtures × /odds and produce CSV-ready rows.

    Returns (rows, n_api_calls, n_skipped_no_odds).
    """
    rows: list[dict] = []
    api_calls = 0
    n_skipped = 0

    for league in leagues:
        try:
            fixtures = api_football.fetch_fixtures_for_date(
                on_date,
                league_canonical=league,
                cache_dir=cache_dir,
                refresh=refresh_fixtures,
            )
            api_calls += 1
        except api_football.ApiFootballError as exc:
            log.warning("%s fixtures error: %s", league, exc)
            continue

        log.info("%s: %d fixtures on %s", league, len(fixtures), on_date)

        for fixture in fixtures:
            fid = fixture.get("fixture", {}).get("id")
            if fid is None:
                continue
            try:
                odds_payload = api_football.fetch_odds(
                    fid, cache_dir=cache_dir, refresh=refresh_odds,
                )
                api_calls += 1
            except api_football.ApiFootballError as exc:
                log.warning("fixture %s odds error: %s", fid, exc)
                n_skipped += 1
                continue

            # /odds returns a list; take the first envelope (one per fixture).
            envelope = odds_payload[0] if odds_payload else None
            row = fixture_envelope_to_csv_row(
                fixture, envelope, league,
                sharp_bookmaker_id=bookmaker_id,
            )
            if row is None:
                n_skipped += 1
                continue
            rows.append(row)

    return rows, api_calls, n_skipped


def _write_csv(rows: list[dict], out_target) -> None:
    """Write rows as CSV to `out_target` (file path or already-open file-like)."""
    if isinstance(out_target, (str, Path)):
        out_path = Path(out_target)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        f = open(out_path, "w", encoding="utf-8", newline="")
        close_after = True
    else:
        f = out_target
        close_after = False

    writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    if close_after:
        f.close()


def render_rows_as_csv(rows: list[dict]) -> str:
    """Return CSV body as a string (used by `nutmeg-rec --auto-fetch`)."""
    buf = StringIO()
    _write_csv(rows, buf)
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V7 W1 — pull /odds → fixtures CSV")
    p.add_argument(
        "--leagues",
        default="EPL,ESP_LA_LIGA",
        help="Comma-separated V4 canonical league codes (incl cups: UCL, FAC, etc.)",
    )
    p.add_argument(
        "--date",
        type=_parse_date,
        default=dt.date.today(),
        help="YYYY-MM-DD; defaults to today (UTC)",
    )
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/external/api_football"),
    )
    p.add_argument(
        "--bookmaker-id",
        type=int,
        default=PINNACLE_BOOKMAKER_ID,
        help=f"API-Football bookmaker ID (default {PINNACLE_BOOKMAKER_ID} = Pinnacle)",
    )
    p.add_argument(
        "--refresh-fixtures",
        action="store_true",
        help="Force re-fetch of /fixtures (skip cache). Re-runs same day still free.",
    )
    p.add_argument(
        "--refresh-odds",
        action="store_true",
        help="Force re-fetch of /odds. Use when refreshing intraday for closing line.",
    )
    p.add_argument(
        "--out",
        default="-",
        help="Output path; '-' for stdout (default)",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    leagues = [s.strip() for s in args.leagues.split(",") if s.strip()]
    if not leagues:
        log.error("no leagues parsed from --leagues=%r", args.leagues)
        return 2

    rows, n_calls, n_skipped = _gather_rows(
        leagues,
        args.date,
        cache_dir=args.cache_dir,
        bookmaker_id=args.bookmaker_id,
        refresh_fixtures=args.refresh_fixtures,
        refresh_odds=args.refresh_odds,
    )

    log.info(
        "DONE: %d rows, %d API calls, %d skipped (no odds/bookmaker quote)",
        len(rows), n_calls, n_skipped,
    )

    if not rows:
        log.warning("no fixtures with odds on %s for %s", args.date, leagues)
        # Still write an empty CSV (header only) so downstream callers see "no
        # fixtures today" rather than choking on a missing file.

    if args.out == "-":
        _write_csv(rows, sys.stdout)
    else:
        _write_csv(rows, args.out)
        log.info("wrote %d rows → %s", len(rows), args.out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
