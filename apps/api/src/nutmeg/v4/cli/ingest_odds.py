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


def _odds_api_available() -> bool:
    """True when an Odds API key is configured — the fresher-line overlay is
    opt-in on it; absent key → graceful fallback to API-Football."""
    try:
        from nutmeg.config import get_settings
        return bool(get_settings().odds_api_key)
    except Exception:  # noqa: BLE001
        return False


def _iso_newer(a: str | None, b: str | None) -> bool:
    """True if ISO timestamp ``a`` is strictly newer than ``b`` (None-safe)."""
    if not a:
        return False
    if not b:
        return True
    try:
        return (dt.datetime.fromisoformat(a.replace("Z", "+00:00"))
                > dt.datetime.fromisoformat(b.replace("Z", "+00:00")))
    except (ValueError, TypeError):
        return False


def _apply_odds_api_overlay(row: dict, oa_lookup: dict) -> bool:
    """Patch a row's Pinnacle 1X2 (+ O/U) from the fresher Odds API line when it
    covers this fixture. API-Football keeps identity/results; we swap only the
    PRICE — and only when Odds API is fresher, or AF had no line (待开盘 fill).
    Sets ``row['odds_source']='odds_api'`` on a patch. Returns True if patched."""
    from nutmeg.v4.data.sources.odds_api import _norm_team
    rec = oa_lookup.get((_norm_team(row.get("home_team")),
                         _norm_team(row.get("away_team")), row.get("date")))
    if not rec or rec.get("psc_home") is None:
        return False
    af_missing = row.get("psc_home") is None
    if not (af_missing or _iso_newer(rec.get("last_update"), row.get("odds_update"))):
        return False  # API-Football line is as-fresh-or-fresher → keep it
    row["psc_home"] = rec["psc_home"]
    row["psc_draw"] = rec["psc_draw"]
    row["psc_away"] = rec["psc_away"]
    if rec.get("ou_line") is not None:
        row["psc_over25"] = rec["psc_over"]
        row["psc_under25"] = rec["psc_under"]
        row["ou_line"] = rec["ou_line"]
    row["odds_update"] = rec.get("last_update")
    row["odds_source"] = "odds_api"
    return True


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
    snapshot_db: str | Path | None = None,
    snapshot_source: str = "gather",
    use_odds_api: bool = False,
    odds_api_refresh: bool = False,
) -> tuple[list[dict], int, int]:
    """Walk leagues × today's fixtures × /odds and produce CSV-ready rows.

    Returns (rows, n_api_calls, n_skipped_no_odds).

    体检 A1 — pass ``snapshot_db`` to append each quoted row's line state to the
    ``odds_snapshots`` history (CLV foundation). This is THE choke point every
    odds flow walks (ingest crons, predict-log, sp-calc, 市场模式 + 🔄), so one
    hook covers them all; the recorder dedups unchanged states and never raises.

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
    n_snapshots = 0
    n_overlay = 0

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

        # 体检(2026-06-10)— fresher Pinnacle line overlay. ONE Odds API call per
        # league (h2h+totals), matched to AF fixtures by team identity; the AF
        # envelope still owns identity / results / sharp-flip books. Any failure
        # → empty lookup → silent fallback to API-Football.
        oa_lookup: dict = {}
        if use_odds_api:
            from nutmeg.v4.data.sources import odds_api
            sport_key = odds_api.SPORT_KEYS.get(league)
            if sport_key:
                try:
                    oa_lookup = odds_api.fetch_pinnacle_lookup(
                        sport_key, refresh=odds_api_refresh, ttl_seconds=1800,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("odds_api overlay failed for %s: %s", league, exc)

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
                if require_odds and not use_odds_api:
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
                # overlay can FILL psc, so don't drop odds-less rows yet — the
                # require_odds gate is re-applied AFTER the overlay below.
                require_1x2_odds=(require_odds and not use_odds_api),
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
            # 体检 — overlay the fresher Pinnacle line where Odds API has it.
            if oa_lookup and _apply_odds_api_overlay(row, oa_lookup):
                n_overlay += 1
            # require_odds re-applied POST-overlay (overlay may have filled psc).
            if require_odds and row.get("psc_home") is None:
                n_skipped += 1
                continue
            rows.append(row)
            if snapshot_db is not None:
                from nutmeg.v4.observation.odds_snapshots import record_row_snapshot
                if record_row_snapshot(
                    snapshot_db, row, fixture_id=fid, envelope=envelope,
                    bookmaker_id=bookmaker_id, source=snapshot_source,
                ):
                    n_snapshots += 1

    if snapshot_db is not None and n_snapshots:
        log.info("line snapshots: +%d new state(s) → %s", n_snapshots, snapshot_db)
    if use_odds_api and n_overlay:
        log.info("odds_api overlay: %d/%d rows took the fresher Pinnacle line",
                 n_overlay, len(rows))
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
    p.add_argument(
        "--snapshot-db",
        default="data/v4_observation.db",
        help=(
            "体检 A1 — append new Pinnacle line states to odds_snapshots in this "
            "observation DB (CLV line history). Default on so the existing "
            "daily/morning crons accumulate history with no plist change."
        ),
    )
    p.add_argument(
        "--no-snapshot",
        action="store_true",
        help="Disable line-history snapshots for this run.",
    )
    p.add_argument(
        "--no-odds-api",
        action="store_true",
        help=(
            "体检 — disable the Odds API fresher-Pinnacle-line overlay (default "
            "ON when NUTMEG_ODDS_API_KEY is set). The Odds API line is ~3h "
            "fresher than API-Football's mirror; AF still owns identity/results."
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
        snapshot_db=(None if (args.no_snapshot or not args.snapshot_db)
                     else args.snapshot_db),
        snapshot_source="ingest_odds",
        use_odds_api=(_odds_api_available() and not args.no_odds_api),
        odds_api_refresh=args.refresh_odds,
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
