"""nutmeg-ingest-cup-history — backfill cup competition historical fixtures.

V7 W6 + first deliverable of V7 Track B (cup-trained model). Pulls
N seasons of cup fixtures from API-Football, normalizes to V4 schema,
writes per-(league, season) parquets to `data/external/cup_history/`.

V7 W7 reads these parquets back into the training pipeline; V7 W8
ships the cup-aware artifact.

Usage:

    # 4 seasons of UCL + UEL
    nutmeg-ingest-cup-history --leagues UCL,UEL \\
        --seasons 2021,2022,2023,2024

    # Single season backfill
    nutmeg-ingest-cup-history --leagues UCL --seasons 2024

    # FA Cup + domestic cups (single-leg, includes lower divisions)
    nutmeg-ingest-cup-history \\
        --leagues FAC,COPA_DEL_REY,COPPA_ITALIA,DFB_POKAL,COUPE_DE_FRANCE \\
        --seasons 2023,2024

Budget:
    For UCL + UEL × 4 seasons: 8 API calls (one /fixtures per
    league-season). All-cup-13 leagues × 4 seasons ≈ 52 calls. Pro
    plan 7500/day → easy fit. Cached by (endpoint, params); re-runs
    same data costs 0.

Output:
    data/external/cup_history/
      UCL_2021.parquet
      UCL_2022.parquet
      UCL_2023.parquet
      UCL_2024.parquet
      UEL_2021.parquet
      ...

    Each parquet has CUP_HISTORY_COLUMNS schema:
      date, league, home_team, away_team, home_goals, away_goals,
      status_short, round_label, api_football_id, season
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from nutmeg.v4.data.competitions import is_cup_competition
from nutmeg.v4.data.cup_history import (
    cup_history_parquet_path,
    gather_cup_history_for_season,
    write_cup_history_parquet,
)


log = logging.getLogger("ingest_cup_history")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="V7 W6 cup historical fixture backfill",
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
        "--out-dir",
        type=Path,
        default=Path("data/external/cup_history"),
        help="Where parquets land (default data/external/cup_history/)",
    )
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/external/api_football"),
        help="API-Football response cache dir (shared with W1/W2 CLIs)",
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-fetch of /fixtures (overrides cache)",
    )
    p.add_argument(
        "--allow-non-cup",
        action="store_true",
        help="By default we reject non-cup league codes (EPL, etc.) — they "
             "have their own football-data.co.uk training rows. Pass this "
             "to override (e.g. for a one-off domestic-cup ingest).",
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
    per_combo: dict[tuple[str, int], int] = {}

    for league in leagues:
        for season in seasons:
            try:
                rows = gather_cup_history_for_season(
                    league, season,
                    cache_dir=args.cache_dir,
                    refresh=args.refresh,
                )
                total_calls += 1  # one /fixtures call per (league, season)
            except Exception as exc:  # noqa: BLE001
                log.warning("%s %d gather failed: %s", league, season, exc)
                continue

            out_path = cup_history_parquet_path(args.out_dir, league, season)
            write_cup_history_parquet(rows, out_path)
            per_combo[(league, season)] = len(rows)
            total_rows += len(rows)
            log.info(
                "%s %d: %d finished fixtures → %s",
                league, season, len(rows), out_path,
            )

    log.info(
        "DONE: %d finished fixtures across %d (league, season) combos, "
        "%d API calls",
        total_rows, len(per_combo), total_calls,
    )

    # Per-combo summary table on stderr (skipping --quiet so it always shows)
    if per_combo:
        print("\nPer-combo finished-fixture counts:", file=sys.stderr)
        print(f"  {'league':<18} {'season':>6} {'n':>6}", file=sys.stderr)
        for (league, season), n in sorted(per_combo.items()):
            print(f"  {league:<18} {season:>6} {n:>6}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
