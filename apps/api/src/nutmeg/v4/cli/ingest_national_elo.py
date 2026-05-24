"""nutmeg-ingest-national-elo — backfill clubelo per-nation Elo histories.

V8 W7. Walks `NATION_CLUBELO_CODES` (or a user-supplied subset), pulls
each nation's full Elo history from `http://api.clubelo.com/<code>`,
writes per-nation parquets to `data/external/clubelo_national/`.

Usage:

    # All ~60 registered nations
    nutmeg-ingest-national-elo

    # Just WC 2026 likely participants
    nutmeg-ingest-national-elo --countries ENG,FRA,ESP,GER,ITA,BRA,ARG,USA,MEX

    # Force re-fetch (override cache)
    nutmeg-ingest-national-elo --countries ENG --refresh

Budget:
    1 HTTP call per nation. ~60 calls for full registry. clubelo doesn't
    enforce a per-IP throttle but it's a free public service, so we add
    a 250ms sleep between requests as politeness.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import httpx

from nutmeg.v4.data.national_team_elo import (
    NATION_CLUBELO_CODES,
    fetch_nation_history,
    nation_cache_path,
    write_nation_parquet,
)


log = logging.getLogger("ingest_national_elo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="V8 W7 — backfill national-team Elo histories from clubelo",
    )
    p.add_argument(
        "--countries",
        default=None,
        help="Comma-separated 3-letter clubelo codes "
             "(default: all in NATION_CLUBELO_CODES, ~60 nations)",
    )
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/external/clubelo_national"),
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch even when a parquet already exists",
    )
    p.add_argument(
        "--throttle-ms",
        type=int,
        default=250,
        help="Sleep between requests (default 250 ms; clubelo is a free service)",
    )
    p.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Log + continue when one nation's fetch fails (default behavior anyway)",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    if args.countries:
        codes = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
        unknown = [c for c in codes if c not in NATION_CLUBELO_CODES]
        if unknown:
            log.warning(
                "unknown codes (not in NATION_CLUBELO_CODES; will try anyway): %s",
                unknown,
            )
    else:
        codes = sorted(NATION_CLUBELO_CODES.keys())

    if not codes:
        log.error("no countries to fetch")
        return 2

    cache_dir = args.cache_dir
    log.info("Ingesting %d nations → %s", len(codes), cache_dir)

    n_ok = 0
    n_skipped_cached = 0
    n_failed = 0
    n_empty = 0

    with httpx.Client(timeout=20.0) as client:
        for code in codes:
            out_path = nation_cache_path(cache_dir, code)
            if out_path.exists() and not args.refresh:
                n_skipped_cached += 1
                continue
            try:
                df = fetch_nation_history(code, client=client)
            except Exception as exc:  # noqa: BLE001
                log.warning("%s fetch error: %s", code, exc)
                n_failed += 1
                continue

            if len(df) == 0:
                log.warning("%s: clubelo returned empty data", code)
                n_empty += 1
                # Still write the empty parquet so downstream loaders
                # can detect "tried but no data" vs "never tried"
                write_nation_parquet(df, out_path)
                continue

            write_nation_parquet(df, out_path)
            log.info("%s: %d rows → %s", code, len(df), out_path)
            n_ok += 1

            if args.throttle_ms > 0:
                time.sleep(args.throttle_ms / 1000.0)

    log.info(
        "DONE: ok=%d, cached-skipped=%d, empty=%d, failed=%d (cache=%s)",
        n_ok, n_skipped_cached, n_empty, n_failed, cache_dir,
    )
    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
