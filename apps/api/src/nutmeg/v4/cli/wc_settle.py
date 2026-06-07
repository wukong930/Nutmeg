"""nutmeg-wc-settle — V10 W4 Day 2.

Pulls finished WC fixtures from API-Football and fills the outcome
columns on previously-recorded `wc_predictions` rows.

Designed to run AFTER each match completes — typically once daily
during the tournament window via the `com.nutmeg.daily_wc_settle`
launchd job (Day 2 of W4).

The settle key is `fixture_id` (the API-Football integer). This makes
the operation idempotent: re-running for a date that's already settled
overwrites with the same goals, no duplicates.

Examples:

    # Settle finished WC fixtures from yesterday
    nutmeg-wc-settle --db data/v4_observation.db

    # Settle a specific date range
    nutmeg-wc-settle --db data/v4_observation.db \\
        --start-date 2026-06-11 --end-date 2026-06-14

    # Dry-run: print what WOULD be settled, don't write
    nutmeg-wc-settle --db data/v4_observation.db --dry-run

Exit codes:
  0  success (≥0 settlements happened)
  1  setup/input error (DB missing, API key missing, etc.)
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterable
from pathlib import Path

from nutmeg.v4.observation.wc_log import (
    ensure_wc_predictions_table,
    settle_wc_prediction,
)

log = logging.getLogger("wc-settle")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# Reuse the finished-match statuses from auto_settle — same semantics
FINISHED_STATUSES = frozenset({
    "FT",   # Match Finished
    "AET",  # Finished after Extra Time
    "PEN",  # Finished after Penalty shootout
})


def _extract_finished_rows(fixtures: Iterable[dict]) -> list[dict]:
    """Filter to finished fixtures with real (int) goal totals."""
    rows: list[dict] = []
    for f in fixtures:
        fb = f.get("fixture") or {}
        status_short = (fb.get("status") or {}).get("short")
        if status_short not in FINISHED_STATUSES:
            continue
        fid = fb.get("id")
        if fid is None:
            continue
        # V14 — settle on the 90' result (score.fulltime), NOT the ET-inclusive
        # `goals`. A knockout decided in extra time still carries its 90' score
        # in score.fulltime; the WC model predicts a 90' 1X2, so scoring it
        # against the post-ET final would wrongly mark a correct 90'-draw
        # prediction as wrong. Mirrors prediction_log._ft_outcome / 竞彩 rule.
        ft = (f.get("score") or {}).get("fulltime") or {}
        goals = f.get("goals") or {}
        hg = ft.get("home")
        ag = ft.get("away")
        if hg is None or ag is None:  # fall back to final goals if FT split absent
            hg, ag = goals.get("home"), goals.get("away")
        if hg is None or ag is None:
            continue
        teams = f.get("teams") or {}
        home = (teams.get("home") or {}).get("name")
        away = (teams.get("away") or {}).get("name")
        rows.append({
            "fixture_id": int(fid),
            "home_team": home,
            "away_team": away,
            "home_goals": int(hg),
            "away_goals": int(ag),
            "kickoff_utc": fb.get("date"),
            "status": status_short,
        })
    return rows


def settle_for_seasons(
    db_path: Path | str,
    seasons: list[int],
    *,
    dry_run: bool = False,
    refresh: bool = False,
) -> tuple[int, int, list[dict]]:
    """Iterate API-Football WC fixtures for each season, settle matches.

    Returns ``(n_finished_pulled, n_settled, settled_rows)`` so the
    caller (CLI) can decide log verbosity. ``n_finished_pulled`` is
    every FT/AET/PEN row API returned; ``n_settled`` only counts those
    whose fixture_id matched a previously-recorded prediction.
    """
    from nutmeg.v4.data.sources.api_football import fetch_fixtures_for_league_season

    n_finished = 0
    n_settled = 0
    settled_rows: list[dict] = []

    for season in seasons:
        try:
            fixtures = fetch_fixtures_for_league_season(
                "WC", season, refresh=refresh,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("WC %d fixtures fetch failed: %s", season, exc)
            continue

        finished = _extract_finished_rows(fixtures)
        n_finished += len(finished)
        log.info(
            "WC %d: %d/%d fixtures finished (status FT/AET/PEN)",
            season, len(finished), len(fixtures),
        )

        for row in finished:
            if dry_run:
                log.info(
                    "[dry-run] would settle fixture=%d %s %d-%d %s",
                    row["fixture_id"], row["home_team"],
                    row["home_goals"], row["away_goals"], row["away_team"],
                )
                continue
            updated = settle_wc_prediction(
                db_path,
                fixture_id=row["fixture_id"],
                home_goals=row["home_goals"],
                away_goals=row["away_goals"],
            )
            if updated:
                n_settled += 1
                settled_rows.append(row)
            else:
                # Match finished but we never recorded a prediction for it
                # (e.g., happened before we deployed wc-predict, or the
                # fixture was added late). Log + skip.
                log.debug(
                    "fixture=%d (%s vs %s) finished but no prediction "
                    "recorded — skipping settle", row["fixture_id"],
                    row["home_team"], row["away_team"],
                )

    return n_finished, n_settled, settled_rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="V10 W4 — settle finished WC fixtures into wc_predictions"
    )
    p.add_argument(
        "--db", default="data/v4_observation.db",
        help="Observation DB path (default data/v4_observation.db)",
    )
    p.add_argument(
        "--seasons", default="2026",
        help="Comma-separated WC seasons to scan (default 2026)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print what WOULD be settled; no DB writes",
    )
    p.add_argument(
        "--refresh", action="store_true",
        help="Force re-fetch from API-Football (overrides cache)",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    db_path = Path(args.db)
    if not db_path.exists() and not args.dry_run:
        log.error("observation DB not found: %s", db_path)
        return 1
    if not args.dry_run:
        ensure_wc_predictions_table(db_path)

    try:
        seasons = [int(s.strip()) for s in args.seasons.split(",")]
    except ValueError:
        log.error("--seasons must be comma-separated integers, got %r", args.seasons)
        return 1

    n_finished, n_settled, rows = settle_for_seasons(
        db_path, seasons, dry_run=args.dry_run, refresh=args.refresh,
    )
    log.info(
        "%s WC fixtures (%d finished, %d settled into wc_predictions)",
        "[dry-run] would have settled" if args.dry_run else "Settled",
        n_finished, n_settled,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
