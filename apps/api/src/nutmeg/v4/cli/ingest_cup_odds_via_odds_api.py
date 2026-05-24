"""nutmeg-ingest-cup-odds-via-odds-api — post-v9 P1#20.

Backfills cup_odds parquets using The Odds API historical endpoint.
This is the fix for V8 W4's blocker: API-Football `/odds` is upcoming-
only, so we used a different paid source for historical depth.

Workflow:
  1. For each (league, season), load cup_history parquet to know what
     fixtures exist + their api_football_ids.
  2. Enumerate match dates (skip qualifying rounds pre-Sep — Odds API
     doesn't cover them anyway).
  3. For each date, fetch ONE historical snapshot from The Odds API.
     One call returns ALL fixtures around that timestamp — typically
     6-8 UCL matches on a midweek matchday.
  4. Parse each fixture's h2h (= 1X2) odds via the source module.
  5. Match Odds API fixture (home_team, away_team) to cup_history row
     to recover the api_football_id (cup_odds join key).
  6. Write parquet via existing `write_cup_odds_parquet`.

Each historical call costs 10 quota on Starter tier. Estimated full
backfill: ~180 calls × 10 = ~1,800 quota for 4 seasons of UCL+UEL.

Usage:

    # Default: backfill UCL+UEL 4 seasons
    nutmeg-ingest-cup-odds-via-odds-api

    # Custom range
    nutmeg-ingest-cup-odds-via-odds-api \\
        --leagues UCL,UEL,UECL \\
        --seasons 2023,2024 \\
        --skip-existing

    # Dry-run: enumerate snapshots without API calls
    nutmeg-ingest-cup-odds-via-odds-api --dry-run

The CLI emits an unmatched-team-name report so we can iterate on
CUP_TEAM_ALIASES (same pattern as P1#10 national-team fixes).
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from nutmeg.v4.data.cup_odds import (
    CUP_ODDS_COLUMNS,
    cup_odds_parquet_path,
    write_cup_odds_parquet,
)
from nutmeg.v4.data.sources.odds_api import (
    SPORT_KEYS,
    OddsApiError,
    fetch_historical_snapshot,
    parse_fixture_to_h2h,
)


log = logging.getLogger("ingest_cup_odds_via_odds_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ---- team name normalization for join ---------------------------------

# Manual aliases — keys are Odds API spellings, values are cup_history
# (api-football) spellings. Iterated based on the unmatched-report.
# Start empty; we'll add as we discover mismatches.
ODDS_API_TO_AF_TEAM_ALIASES: dict[str, str] = {
    # Only manual entries where _norm_for_match can't bridge the gap.
    # If norm("X") == norm("Y") (lowercase + diacritic strip + prefix strip),
    # no alias needed. Each entry below is a real mismatch from the
    # first-pass unmatched report.

    # Inter — Odds API "Internazionale Milano" → AF "Inter"
    "Internazionale Milano": "Inter",
    "Internazionale":        "Inter",
    "Inter Milan":           "Inter",
    # Lille — Odds API "LOSC Lille" → AF "Lille"
    "LOSC Lille":            "Lille",
    # Club Brugge — Odds API "Club Brugge" → AF "Club Brugge KV"
    "Club Brugge":           "Club Brugge KV",
    # Young Boys — Odds API "Young Boys" → AF "BSC Young Boys"
    "Young Boys":            "BSC Young Boys",
    # Salzburg — Odds API "Salzburg" → AF "Red Bull Salzburg"
    "Salzburg":              "Red Bull Salzburg",
    "RB Salzburg":           "Red Bull Salzburg",
    "FC Salzburg":           "Red Bull Salzburg",
    # SK Slovan — Odds API "ŠK Slovan Bratislava" → AF "Slovan Bratislava"
    "ŠK Slovan Bratislava":  "Slovan Bratislava",
    # SK Sturm Graz — Odds API "SK Sturm Graz" → AF "Sturm Graz"
    "SK Sturm Graz":         "Sturm Graz",
    # Stade Brestois — Odds API uses "Brest" → AF "Stade Brestois 29"
    "Brest":                 "Stade Brestois 29",
    # Sparta Praha — Odds API "Sparta Prague" → AF "Sparta Praha"
    "Sparta Prague":         "Sparta Praha",
    # GNK Dinamo Zagreb — same as AF; sometimes "Dinamo Zagreb"
    # Crvena Zvezda — Odds API "Crvena zvezda" → AF "FK Crvena Zvezda"
    "Crvena zvezda":         "FK Crvena Zvezda",
    "Red Star Belgrade":     "FK Crvena Zvezda",
    # Sporting CP — Odds API uses "Sporting Lisbon" → AF "Sporting CP"
    "Sporting Lisbon":       "Sporting CP",
    "Sporting CP":           "Sporting CP",
}


def _normalize_team(name: str) -> str:
    """Lowercase + strip common diacritics + apply manual alias map.
    Returns the cup_history (api-football) spelling when a match is found."""
    if not name:
        return ""
    if name in ODDS_API_TO_AF_TEAM_ALIASES:
        return ODDS_API_TO_AF_TEAM_ALIASES[name]
    return name


def _norm_for_match(name: str) -> str:
    """Loose comparison key — lower, no diacritics, no FC/AC/CF prefix."""
    import unicodedata
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    # Strip common club-type prefixes
    for prefix in ("fc ", "ac ", "as ", "rc ", "sc ", "afc "):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    # Strip suffix that varies
    for suffix in (" fc", " ac", " cf", " sc"):
        if s.endswith(suffix):
            s = s[:-len(suffix)]
    return s.replace("'", "").replace("-", " ").replace(".", "").strip()


# ---- snapshot enumeration ---------------------------------------------

def _matchday_snapshots(cup_history: pd.DataFrame, season: int) -> list[str]:
    """Enumerate unique snapshot timestamps to query.

    Strategy: one snapshot per matchday at 23:00 UTC (well after most
    UCL/UEL matches end at 22:45 CET). The Odds API returns the snapshot
    closest to the requested time, so picking 23:00 captures the
    closing-line state for that day's fixtures.

    Filter: skip pre-Sep dates (qualifying rounds usually not covered).
    """
    if cup_history.empty:
        return []
    df = cup_history.copy()
    # Coerce date to YYYY-MM-DD string
    df["date_str"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[df["date_str"] >= f"{season}-09-01"]
    dates = sorted(df["date_str"].unique())
    return [f"{d}T23:00:00Z" for d in dates]


# ---- core ingest loop --------------------------------------------------

def _ingest_one_season(
    league: str,
    season: int,
    cup_history_dir: Path,
    out_dir: Path,
    *,
    dry_run: bool = False,
    skip_existing: bool = False,
) -> dict[str, Any]:
    """Backfill one (league, season). Returns a stats dict."""
    stats = {
        "league": league, "season": season,
        "n_snapshots_requested": 0,
        "n_fixtures_seen": 0,
        "n_matched": 0,
        "n_unmatched": 0,
        "unmatched_pairs": [],
        "n_rows_written": 0,
        "out_path": None,
        "skipped": False,
    }

    out_path = cup_odds_parquet_path(out_dir, league, season)
    if skip_existing and out_path.exists():
        existing = pd.read_parquet(out_path)
        if len(existing) > 0:
            stats["skipped"] = True
            stats["n_rows_written"] = len(existing)
            stats["out_path"] = str(out_path)
            log.info("  skip-existing: %s has %d rows", out_path.name, len(existing))
            return stats

    # Load cup_history for this (league, season)
    ch_path = cup_history_dir / f"{league}_{season}.parquet"
    if not ch_path.exists():
        log.warning("  no cup_history parquet for %s_%d — skipping", league, season)
        return stats
    ch = pd.read_parquet(ch_path)
    if ch.empty:
        log.warning("  cup_history %s_%d is empty — skipping", league, season)
        return stats

    sport_key = SPORT_KEYS.get(league)
    if not sport_key:
        log.error("  no SPORT_KEYS mapping for %s — skipping", league)
        return stats

    snapshots = _matchday_snapshots(ch, season)
    stats["n_snapshots_requested"] = len(snapshots)
    log.info(
        "  %s_%d: %d cup_history rows → %d unique matchday snapshots",
        league, season, len(ch), len(snapshots),
    )

    if dry_run:
        return stats

    # Index cup_history by (date, normalized teams) for fast lookup
    ch["date_str"] = pd.to_datetime(ch["date"]).dt.strftime("%Y-%m-%d")
    ch["home_norm"] = ch["home_team"].apply(_norm_for_match)
    ch["away_norm"] = ch["away_team"].apply(_norm_for_match)

    rows: list[dict[str, Any]] = []
    unmatched: list[tuple[str, str, str]] = []  # (date, home, away)
    for snap_iso in snapshots:
        snap_date = snap_iso[:10]   # YYYY-MM-DD
        try:
            envelope = fetch_historical_snapshot(sport_key, snap_iso)
        except OddsApiError as e:
            # "snapshot not available" is common for some dates; skip
            if "404" in str(e) or "no data" in str(e).lower():
                log.debug("  no snapshot %s: %s", snap_iso, e)
                continue
            log.warning("  fetch failed for %s: %s", snap_iso, e)
            continue
        fixtures = envelope.get("data", [])
        for fx in fixtures:
            stats["n_fixtures_seen"] += 1
            parsed = parse_fixture_to_h2h(fx)
            if not parsed:
                continue
            # Apply alias map BEFORE normalization so manual fixes hit
            home_aliased = _normalize_team(parsed["home_team"])
            away_aliased = _normalize_team(parsed["away_team"])
            home_norm = _norm_for_match(home_aliased)
            away_norm = _norm_for_match(away_aliased)
            # Match against cup_history on the same date (Odds API
            # snapshot can include neighboring-day fixtures, so filter
            # by parsed commence_time too)
            commence_date = parsed["commence_time"][:10]
            candidates = ch[
                (ch["date_str"] == commence_date)
                & (ch["home_norm"] == home_norm)
                & (ch["away_norm"] == away_norm)
            ]
            if candidates.empty:
                unmatched.append((commence_date, parsed["home_team"], parsed["away_team"]))
                continue
            cup_history_row = candidates.iloc[0]
            # Build cup_odds row with shared schema
            row = {
                "api_football_id": int(cup_history_row["api_football_id"]),
                "league": league,
                "season": season,
                # bookmaker_id is API-Football specific; The Odds API uses
                # string keys ("marathonbet", "pinnacle"). Store -1 to
                # mark "not from API-Football" + put bookmaker key in
                # a string column. For now stick to -1 to keep schema.
                "bookmaker_id": -1,
                "psc_home": float(parsed["psc_home"]),
                "psc_draw": float(parsed["psc_draw"]),
                "psc_away": float(parsed["psc_away"]),
                "psc_over25": None,   # h2h only; O/U requires "totals" market
                "psc_under25": None,
            }
            rows.append(row)
            stats["n_matched"] += 1

    stats["n_unmatched"] = len(unmatched)
    # Dedupe unmatched (most are repeated across snapshots)
    seen = set()
    for u in unmatched:
        key = (u[1], u[2])  # (home, away)
        if key not in seen:
            stats["unmatched_pairs"].append(u)
            seen.add(key)

    if rows:
        # Dedupe within rows by api_football_id (one snapshot per fixture)
        # If the same fixture appears in multiple snapshots, keep first.
        seen_ids = set()
        unique_rows = []
        for r in rows:
            if r["api_football_id"] in seen_ids:
                continue
            seen_ids.add(r["api_football_id"])
            unique_rows.append(r)
        rows = unique_rows
        write_cup_odds_parquet(rows, out_path)
        stats["n_rows_written"] = len(rows)
        stats["out_path"] = str(out_path)
        log.info(
            "  %s_%d: %d/%d fixtures matched, %d unique rows written → %s",
            league, season,
            stats["n_matched"], stats["n_fixtures_seen"],
            len(rows), out_path.name,
        )
    else:
        log.warning(
            "  %s_%d: 0 rows written (saw %d fixtures, all unmatched or empty)",
            league, season, stats["n_fixtures_seen"],
        )

    return stats


# ---- CLI entry ---------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="P1#20 — backfill cup_odds via The Odds API")
    p.add_argument(
        "--leagues", default="UCL,UEL",
        help="Comma-separated V4 cup codes (must be in SPORT_KEYS)",
    )
    p.add_argument(
        "--seasons", default="2021,2022,2023,2024",
        help="Comma-separated season start years",
    )
    p.add_argument(
        "--cup-history-dir", default="data/external/cup_history",
        help="Where existing cup_history parquets live (join source)",
    )
    p.add_argument(
        "--out-dir", default="data/external/cup_odds",
        help="Where cup_odds parquets get written",
    )
    p.add_argument(
        "--skip-existing", action="store_true",
        help="Don't overwrite parquets that already have rows",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Enumerate snapshot timestamps without making API calls",
    )
    p.add_argument(
        "--unmatched-report", default=None,
        help="Optional: write unmatched team-name pairs to this file",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    leagues = [s.strip() for s in args.leagues.split(",") if s.strip()]
    seasons = [int(s.strip()) for s in args.seasons.split(",") if s.strip()]
    cup_history_dir = Path(args.cup_history_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Backfilling cup_odds for %s × %s", leagues, seasons)
    all_stats: list[dict[str, Any]] = []
    all_unmatched: list[tuple[str, str, str]] = []
    for league in leagues:
        for season in seasons:
            log.info("─── %s %d ───", league, season)
            stats = _ingest_one_season(
                league, season,
                cup_history_dir, out_dir,
                dry_run=args.dry_run,
                skip_existing=args.skip_existing,
            )
            all_stats.append(stats)
            all_unmatched.extend(stats["unmatched_pairs"])

    # Summary
    log.info("════════ Summary ════════")
    total_rows = sum(s["n_rows_written"] for s in all_stats)
    total_matched = sum(s["n_matched"] for s in all_stats)
    total_unmatched = sum(s["n_unmatched"] for s in all_stats)
    total_fixtures = sum(s["n_fixtures_seen"] for s in all_stats)
    for s in all_stats:
        skip_note = " (skipped)" if s["skipped"] else ""
        log.info(
            "  %s %d: %d rows%s",
            s["league"], s["season"], s["n_rows_written"], skip_note,
        )
    log.info("TOTAL rows written: %d", total_rows)
    log.info(
        "TOTAL fixtures seen: %d  matched: %d  unmatched (with dupes): %d",
        total_fixtures, total_matched, total_unmatched,
    )

    # Unmatched diagnostic
    if all_unmatched:
        # Dedupe across seasons
        unique = list(set((h, a) for _, h, a in all_unmatched))
        log.info("───── unique unmatched team pairs (%d) ─────", len(unique))
        for h, a in sorted(unique)[:30]:
            log.info("  %s vs %s", h, a)
        if len(unique) > 30:
            log.info("  ... and %d more", len(unique) - 30)
        if args.unmatched_report:
            with open(args.unmatched_report, "w") as f:
                for h, a in sorted(unique):
                    f.write(f"{h}\t{a}\n")
            log.info("Wrote unmatched-report → %s", args.unmatched_report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
