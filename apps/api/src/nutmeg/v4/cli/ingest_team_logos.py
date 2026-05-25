"""nutmeg-ingest-team-logos — download team logo PNGs from API-Football.

V11 P1-FE#2 Day 2 — one-shot ingest. For each (league, season) pair,
calls API-Football ``/teams`` to harvest logo URLs, then downloads each
PNG to ``data/external/team_logos/<slug>.png``.

Usage:

    # Single league
    nutmeg-ingest-team-logos --league EPL --season 2024

    # Top-5 European leagues (most common case)
    nutmeg-ingest-team-logos \\
        --league EPL --league ESP_LA_LIGA --league ITA_SERIE_A \\
        --league GER_BUNDESLIGA --league FRA_LIGUE_1 \\
        --season 2024

API budget:
    - 1 call per (league, season) for the team list
    - 1 download per team (cached; skips if already downloaded)
    Total for top-5 leagues + 2024-25 season ≈ 5 + 96 = 101 calls.
    Negligible on API-Football Pro / Tier 2 plans.

Logos already on disk are skipped (idempotent re-runs).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from nutmeg.v4.data.sources import api_football
from nutmeg.v4.data.team_logos import logo_path, team_slug


log = logging.getLogger("ingest_team_logos")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def _download_logo(url: str, dest: Path, *, timeout: float = 15.0) -> bool:
    """Download a single logo. Returns True on success, False on failure.

    Skips if dest already exists (idempotent).
    """
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            r = c.get(url)
        if r.status_code != 200:
            log.warning("logo HTTP %s for %s", r.status_code, url)
            return False
        # Sniff content-type briefly — accept image/*; reject HTML error pages
        ctype = r.headers.get("content-type", "")
        if not ctype.startswith("image/"):
            log.warning("non-image content-type %s for %s", ctype, url)
            return False
        dest.write_bytes(r.content)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("logo download failed %s → %s", url, e)
        return False


def _extract_team_records(
    teams_response: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """From the /teams response, return (api_name, logo_url) tuples.

    API-Football payload shape:
        [{ "team": { "id": int, "name": str, "logo": str }, "venue": {...} }, …]
    """
    out: list[tuple[str, str]] = []
    for rec in teams_response:
        t = rec.get("team") or {}
        name = t.get("name")
        logo = t.get("logo")
        if name and logo:
            out.append((str(name), str(logo)))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="V11 P1-FE#2 — download team logos from API-Football"
    )
    p.add_argument(
        "--league",
        action="append",
        required=True,
        help="V4 canonical league code (repeatable). E.g. --league EPL --league ESP_LA_LIGA",
    )
    p.add_argument(
        "--season",
        type=int,
        required=True,
        help="Season start year (e.g. 2024 for 2024-25)",
    )
    p.add_argument(
        "--out-dir",
        default="data/external/team_logos",
        help="Where to save logo PNGs (default: data/external/team_logos)",
    )
    p.add_argument(
        "--api-cache-dir",
        default="data/external/api_football",
        help="API-Football cache dir for /teams responses",
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="Re-fetch /teams responses (does NOT re-download already-cached logos)",
    )
    p.add_argument(
        "--throttle-ms",
        type=int,
        default=200,
        help="Delay between logo downloads in milliseconds (default 200)",
    )
    args = p.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    api_cache_dir = Path(args.api_cache_dir)

    total_teams = 0
    total_downloaded = 0
    total_skipped = 0
    total_failed = 0

    for league in args.league:
        log.info("[%s/%d] fetching team list…", league, args.season)
        try:
            resp = api_football.fetch_teams_for_league_season(
                league,
                args.season,
                cache_dir=api_cache_dir,
                refresh=args.refresh,
            )
        except api_football.ApiFootballError as e:
            log.error("[%s] %s — skipping", league, e)
            continue

        records = _extract_team_records(resp)
        log.info("[%s/%d] %d teams from /teams", league, args.season, len(records))

        for api_name, url in records:
            total_teams += 1
            # Save under the API name's slug. Dashboard does the same
            # `slug(home_team)` lookup at render time. Cases where the
            # V4 canonical name slugs to something different fall back
            # to the 2-letter initials circle (still looks polished).
            dest = logo_path(api_name, cache_dir=out_dir)
            if dest.exists() and dest.stat().st_size > 0:
                total_skipped += 1
                continue
            ok = _download_logo(url, dest)
            if ok:
                total_downloaded += 1
                log.info("  ✓ %s → %s", api_name, dest.name)
            else:
                total_failed += 1
            if args.throttle_ms > 0:
                time.sleep(args.throttle_ms / 1000.0)

    log.info("=" * 60)
    log.info("Total teams seen:    %d", total_teams)
    log.info("Newly downloaded:    %d", total_downloaded)
    log.info("Skipped (cached):    %d", total_skipped)
    log.info("Failed:              %d", total_failed)
    log.info("Logo cache:          %s", out_dir.resolve())
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
