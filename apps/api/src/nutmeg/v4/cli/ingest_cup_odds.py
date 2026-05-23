"""nutmeg-ingest-cup-odds — backfill cup competition historical odds.

V7 W8 — second-to-last piece of Track B. Reads the V7 W6 cup-history
parquets to know which fixture IDs to query, calls API-Football
`/odds` per fixture, writes per-(league, season) cup-odds parquets
to `data/external/cup_odds/`. Joined with cup_history via
`merge_cup_fixtures_and_odds`, the result is a training-frame-
compatible cup match dataset.

Usage:

    # Default: read W6 fixtures from data/external/cup_history,
    # write odds to data/external/cup_odds; Pinnacle (4) as the sharp book
    nutmeg-ingest-cup-odds --leagues UCL,UEL --seasons 2021,2022,2023,2024

    # Override the sharp book (Bet365 = 8)
    nutmeg-ingest-cup-odds --leagues UCL --seasons 2024 --bookmaker-id 8

Budget:
    1 /odds call per cup fixture. UCL ~125 matches/season × 4 seasons =
    500 calls; UEL ~205 × 4 = 820. Total ~1320 calls for the typical
    backfill. Pro plan 7500/day → easy fit. Cached by (endpoint,
    params); re-runs cost 0.

Prerequisite: must run `nutmeg-ingest-cup-history` first to populate
the W6 fixture parquets that drive this loop.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from nutmeg.v4.data.competitions import is_cup_competition
from nutmeg.v4.data.cup_history import (
    cup_history_parquet_path,
    load_cup_history_parquet,
)
from nutmeg.v4.data.cup_odds import (
    cup_odds_parquet_path,
    normalize_odds_envelope,
    write_cup_odds_parquet,
)
from nutmeg.v4.data.odds_parser import PINNACLE_BOOKMAKER_ID
from nutmeg.v4.data.sources import api_football


log = logging.getLogger("ingest_cup_odds")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _gather_odds_for_combo(
    league_code: str,
    season: int,
    *,
    cup_history_dir: Path,
    cache_dir: Path,
    bookmaker_id: int,
    refresh: bool,
    throttle_ms: int,
) -> tuple[list[dict], int, int]:
    """Pull odds for every fixture in one (league, season) cup-history parquet.

    Returns (rows, n_api_calls, n_skipped_no_quote). Skipped count is
    the number of fixtures where the requested book didn't quote 1X2 —
    common for old qualifying matches or non-marquee fixtures.
    """
    fix_path = cup_history_parquet_path(cup_history_dir, league_code, season)
    fixtures = load_cup_history_parquet(fix_path)
    if len(fixtures) == 0:
        log.warning(
            "%s %d: no cup-history parquet at %s (run nutmeg-ingest-cup-history first?)",
            league_code, season, fix_path,
        )
        return [], 0, 0

    log.info("%s %d: %d fixtures to query", league_code, season, len(fixtures))

    rows: list[dict] = []
    n_calls = 0
    n_skipped = 0
    for _, fixture in fixtures.iterrows():
        fid = int(fixture["api_football_id"])
        try:
            odds_payload = api_football.fetch_odds(
                fid, cache_dir=cache_dir, refresh=refresh,
            )
            n_calls += 1
        except api_football.ApiFootballError as exc:
            log.warning("fixture %s odds error: %s", fid, exc)
            n_skipped += 1
            continue

        envelope = odds_payload[0] if odds_payload else None
        row = normalize_odds_envelope(
            envelope, fid, league_code, season,
            bookmaker_id=bookmaker_id,
        )
        if row is None:
            n_skipped += 1
            continue
        rows.append(row)

        if throttle_ms > 0:
            time.sleep(throttle_ms / 1000.0)

    return rows, n_calls, n_skipped


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="V7 W8 cup historical odds backfill",
    )
    p.add_argument(
        "--leagues",
        required=True,
        help="Comma-separated V4 cup codes (UCL, UEL, UECL, FAC, "
             "COPA_DEL_REY, COPPA_ITALIA, DFB_POKAL, COUPE_DE_FRANCE, "
             "WC, EURO, COPA_AMERICA, WC_QUAL_UEFA)",
    )
    p.add_argument(
        "--seasons",
        required=True,
        help="Comma-separated season start years (e.g. 2021,2022,2023,2024)",
    )
    p.add_argument(
        "--cup-history-dir",
        type=Path,
        default=Path("data/external/cup_history"),
        help="Where V7 W6 fixture parquets live (drives the loop)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/external/cup_odds"),
        help="Where odds parquets land (default data/external/cup_odds/)",
    )
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/external/api_football"),
        help="API-Football response cache dir (shared with V7 W1)",
    )
    p.add_argument(
        "--bookmaker-id",
        type=int,
        default=PINNACLE_BOOKMAKER_ID,
        help=f"API-Football bookmaker ID (default {PINNACLE_BOOKMAKER_ID} = Pinnacle)",
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-fetch of /odds (overrides cache)",
    )
    p.add_argument(
        "--throttle-ms",
        type=int,
        default=200,
        help="Sleep between /odds calls to be polite (default 200ms)",
    )
    p.add_argument(
        "--allow-non-cup",
        action="store_true",
        help="Same escape hatch as nutmeg-ingest-cup-history",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    leagues = [s.strip() for s in args.leagues.split(",") if s.strip()]
    try:
        seasons = [int(s.strip()) for s in args.seasons.split(",") if s.strip()]
    except ValueError as e:
        log.error("could not parse --seasons=%r: %s", args.seasons, e)
        return 2

    if not leagues or not seasons:
        log.error("empty leagues or seasons after parsing")
        return 2

    if not args.allow_non_cup:
        non_cup = [l for l in leagues if not is_cup_competition(l)]
        if non_cup:
            log.error(
                "non-cup codes refused (pass --allow-non-cup to override): %s",
                non_cup,
            )
            return 2

    total_rows = 0
    total_calls = 0
    total_skipped = 0
    per_combo: dict[tuple[str, int], tuple[int, int]] = {}

    for league in leagues:
        for season in seasons:
            try:
                rows, n_calls, n_skipped = _gather_odds_for_combo(
                    league, season,
                    cup_history_dir=args.cup_history_dir,
                    cache_dir=args.cache_dir,
                    bookmaker_id=args.bookmaker_id,
                    refresh=args.refresh,
                    throttle_ms=args.throttle_ms,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("%s %d gather failed: %s", league, season, exc)
                continue

            out_path = cup_odds_parquet_path(args.out_dir, league, season)
            write_cup_odds_parquet(rows, out_path)
            per_combo[(league, season)] = (len(rows), n_skipped)
            total_rows += len(rows)
            total_calls += n_calls
            total_skipped += n_skipped
            log.info(
                "%s %d: %d odds rows (%d skipped, no quote) → %s",
                league, season, len(rows), n_skipped, out_path,
            )

    log.info(
        "DONE: %d odds rows across %d (league, season) combos, "
        "%d API calls, %d skipped",
        total_rows, len(per_combo), total_calls, total_skipped,
    )

    if per_combo:
        print("\nPer-combo (kept / skipped) counts:", file=sys.stderr)
        print(f"  {'league':<18} {'season':>6} {'kept':>6} {'skip':>6}",
              file=sys.stderr)
        for (league, season), (kept, skipped) in sorted(per_combo.items()):
            print(f"  {league:<18} {season:>6} {kept:>6} {skipped:>6}",
                  file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
