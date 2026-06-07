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
from nutmeg.v4.model.sharp_consensus import consensus as _sharp_consensus
from nutmeg.v4.model.sharp_consensus import per_book_fair as _sharp_per_book


log = logging.getLogger("ingest_odds")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


CSV_COLUMNS = [
    "date", "league", "home_team", "away_team",
    "psc_home", "psc_draw", "psc_away",
    "psc_over25", "psc_under25",
    # Asian total line psc_over25/under25 belong to (2.5 when quoted, else the
    # book's main line — e.g. a 2.25 quarter total). The market-reverse 让球
    # anchors λ_total to THIS line; default 2.5 keeps every prior row valid.
    "ou_line",
    # Lottery-specific odds left blank — the user fills these from the
    # 竞彩 terminal at bet time (浮动 SP).
    "handicap_home",
    "odds_1x2_H", "odds_1x2_D", "odds_1x2_A",
    "odds_handicap_H", "odds_handicap_D", "odds_handicap_A",
    # V12 W0 (2026-05-28) — kickoff context for time-window filtering
    # (Plan A: morning + afternoon waves can produce different optimal
    # solutions because the set of "still-upcoming" fixtures differs).
    "kickoff_utc",
    "status_short",
]

# Statuses meaning "fixture is upcoming, not yet started" (per API-Football):
#   NS   = Not Started (the normal case)
#   TBD  = To Be Defined (kickoff time unconfirmed)
#   POSTP = Postponed (rescheduled, may move to later date)
# Anything else (IN_PLAY, HT, FT, ABD, CANC, etc.) means the match is no
# longer pre-game and the closing odds aren't actionable.
_UPCOMING_STATUSES: frozenset[str] = frozenset({"NS", "TBD", "POSTP", ""})


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
    require_odds: bool = True,
    min_kickoff_buffer_minutes: int = 0,
    now_utc: Optional[dt.datetime] = None,
) -> tuple[list[dict], int, int]:
    """Walk leagues × today's fixtures × /odds and produce CSV-ready rows.

    Returns (rows, n_api_calls, n_skipped_no_odds).

    ``require_odds`` (default True) drops fixtures without a sharp 1X2 quote —
    correct for the cron / 国际盘口 board, which can't score odds-less fixtures.
    Pass False (V12 W6 — 近期赛事 tab) to KEEP them as rows with psc_* = None so
    the UI can list them as '待开盘' until Pinnacle opens the line.

    V12 W0 (2026-05-28) Plan A — pass ``min_kickoff_buffer_minutes`` > 0
    to drop fixtures that are already kicked off (or about to kick off
    within the buffer). This is what lets the morning + afternoon cron
    waves produce different optimal recommendation sets: at 10:00 we
    include J1 12:00 matches; by 14:00 those are filtered out (started
    or already finished), leaving European fixtures only.

    Filtering rules (a fixture is dropped if ANY is true):
      - status_short ∉ {"NS", "TBD", "POSTP", ""}  (already kicked off
        or finished — closing odds no longer actionable)
      - kickoff_utc <= now_utc + buffer  (will start within buffer; too
        late to act on this recommendation safely)

    ``now_utc`` overrideable for tests; defaults to ``datetime.now(UTC)``.
    """
    rows: list[dict] = []
    api_calls = 0
    n_skipped = 0

    if now_utc is None:
        now_utc = dt.datetime.now(dt.UTC)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=dt.UTC)
    cutoff_utc = now_utc + dt.timedelta(minutes=min_kickoff_buffer_minutes)

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

            # V12 W0 — pre-flight time-window filter (skip API /odds call
            # for already-kicked-off fixtures to save quota).
            if min_kickoff_buffer_minutes > 0:
                f_payload = fixture.get("fixture", {})
                status = f_payload.get("status", {}).get("short", "")
                iso_date = f_payload.get("date", "")
                if status not in _UPCOMING_STATUSES:
                    log.debug(
                        "skip fixture %s: status=%r (already kicked off)",
                        fid, status,
                    )
                    n_skipped += 1
                    continue
                if iso_date:
                    try:
                        kickoff = dt.datetime.fromisoformat(iso_date)
                        if kickoff.tzinfo is None:
                            kickoff = kickoff.replace(tzinfo=dt.UTC)
                        if kickoff <= cutoff_utc:
                            log.debug(
                                "skip fixture %s: kickoff %s <= cutoff %s",
                                fid, iso_date, cutoff_utc.isoformat(),
                            )
                            n_skipped += 1
                            continue
                    except (ValueError, TypeError):
                        # Bad/missing ISO timestamp — let it through, the
                        # downstream model will deal with it
                        pass

            try:
                odds_payload = api_football.fetch_odds(
                    fid, cache_dir=cache_dir, refresh=refresh_odds,
                )
                api_calls += 1
            except api_football.ApiFootballError as exc:
                log.warning("fixture %s odds error: %s", fid, exc)
                if require_odds:
                    n_skipped += 1
                    continue
                # V12 W6 — 近期赛事 still lists the fixture (as 待开盘); the
                # row gets psc_* = None from the empty envelope below.
                odds_payload = []

            # /odds returns a list; take the first envelope (one per fixture).
            envelope = odds_payload[0] if odds_payload else None
            row = fixture_envelope_to_csv_row(
                fixture, envelope, league,
                sharp_bookmaker_id=bookmaker_id,
                require_1x2_odds=require_odds,
            )
            if row is None:
                n_skipped += 1
                continue
            # V14 — sharp-flip guard: the SAME envelope already carries Betfair +
            # SBOBET; flag the row when Pinnacle's de-vig favourite disagrees with
            # them (Pinnacle line is empirically much worse there → the card
            # downgrades the EV reliability tag to ⚠️ sharp 分歧).
            if envelope is not None:
                row["sharp_flip"] = _sharp_consensus(_sharp_per_book(envelope)).pinnacle_flip
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
    p.add_argument(
        "--min-kickoff-buffer-minutes",
        type=int,
        default=0,
        help=(
            "V12 W0 — drop fixtures whose kickoff is within this many "
            "minutes from now (or already started). 0 disables (legacy). "
            "Recommended for live cron: 30 (give ~30 min buffer to act). "
            "When set, fixtures with status_short ∉ {NS,TBD,POSTP} are "
            "also dropped pre-emptively (saves /odds API calls)."
        ),
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
        min_kickoff_buffer_minutes=args.min_kickoff_buffer_minutes,
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
