"""nutmeg-canonical-report-cup — diagnose cup-team-name resolution.

V8 W1. Reads the V7 W6 cup-history parquets, extracts every unique
team name, walks each through `to_v4_canonical_global`, and prints
the unmatched + fuzzy-only ones. The output is the action list for
extending `CUP_TEAM_ALIASES` in `nutmeg.utils.team_canonical`.

Usage:

    # Scan UCL + UEL parquets for unmatched teams; default league pool
    # is the V4 walk_forward leagues (EPL, La Liga, Serie A, etc.)
    nutmeg-canonical-report-cup --leagues UCL,UEL \\
        --seasons 2021,2022,2023,2024

    # Use a specific football-data tree to build the V4 team pool
    nutmeg-canonical-report-cup --leagues UCL --seasons 2024 \\
        --data data/historical_sources/football_data_co_uk \\
        --fuzzy-threshold 0.86

Output format:

    [match status]  external_name  →  canonical (confidence)

Where status is one of: `exact`, `alias`, `fuzzy`, `unmatched`. The
unmatched + fuzzy rows are the ones you want to review.

Exit codes:
    0 — completed (may have unmatched rows; caller checks output)
    1 — input error (no parquets found, no V4 data tree)
    2 — parsing error
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from nutmeg.utils.team_canonical import (
    build_global_team_pool,
    to_v4_canonical_global,
)
from nutmeg.v4.data.cup_history import (
    cup_history_parquet_path,
    load_cup_history_parquet,
)
from nutmeg.v4.eval.walk_forward import WalkForwardConfig


log = logging.getLogger("canonical_report_cup")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _gather_cup_team_names(
    cup_history_dir: Path,
    leagues: list[str],
    seasons: list[int],
) -> set[str]:
    """Walk W6 parquets, return the unique union of home + away team names."""
    names: set[str] = set()
    for league in leagues:
        for season in seasons:
            path = cup_history_parquet_path(cup_history_dir, league, season)
            df = load_cup_history_parquet(path)
            if len(df) == 0:
                continue
            for col in ("home_team", "away_team"):
                names.update(str(n) for n in df[col].dropna().unique())
    return names


def _build_pool_from_football_data(data_dir: Path | None) -> list[str]:
    """Construct the V4 global team pool from the football-data.co.uk tree.

    When `data_dir` is None or the tree is missing, returns an empty list
    (caller errors out — without a pool the lookup can't resolve anything).
    """
    if data_dir is None or not data_dir.exists():
        return []
    from nutmeg.v4.data.ingest import load_all_matches
    df = load_all_matches(str(data_dir))
    if len(df) == 0:
        return []
    # Pool = union of home/away across all leagues in the data tree
    league_pools: dict[str, set[str]] = {}
    for league, group in df.groupby("league"):
        teams = set()
        teams.update(str(n) for n in group["home_team"].dropna().unique())
        teams.update(str(n) for n in group["away_team"].dropna().unique())
        league_pools[league] = teams
    return build_global_team_pool(league_pools)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="V8 W1 — diagnose cup-team canonical-name resolution",
    )
    p.add_argument(
        "--leagues",
        default="UCL,UEL",
        help="Comma-separated cup codes whose parquets to scan",
    )
    p.add_argument(
        "--seasons",
        default="2021,2022,2023,2024",
        help="Comma-separated season start years",
    )
    p.add_argument(
        "--cup-history-dir",
        type=Path,
        default=Path("data/external/cup_history"),
        help="Where V7 W6 parquets live",
    )
    p.add_argument(
        "--data",
        type=Path,
        default=Path("data/historical_sources/football_data_co_uk"),
        help="Football-data.co.uk tree (drives the V4 team pool)",
    )
    p.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=0.86,
        help="Cutoff for fuzzy match (0..1; lower = more permissive)",
    )
    p.add_argument(
        "--show",
        choices=("all", "unmatched", "fuzzy"),
        default="all",
        help="Filter the printed table",
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

    log.info(
        "Scanning cup parquets: leagues=%s seasons=%s; cup-dir=%s; data=%s",
        leagues, seasons, args.cup_history_dir, args.data,
    )

    cup_names = _gather_cup_team_names(args.cup_history_dir, leagues, seasons)
    if not cup_names:
        log.error(
            "no cup team names found — did you run nutmeg-ingest-cup-history?"
        )
        return 1

    pool = _build_pool_from_football_data(args.data)
    if not pool:
        log.error(
            "could not build V4 team pool from %s — pass --data with a valid tree",
            args.data,
        )
        return 1

    log.info(
        "Pool size: %d teams; cup names to resolve: %d",
        len(pool), len(cup_names),
    )

    rows: list[tuple[str, str, str, float]] = []
    counts = {"exact": 0, "alias": 0, "fuzzy": 0, "unmatched": 0}
    for name in sorted(cup_names):
        result = to_v4_canonical_global(
            name, pool, fuzzy_threshold=args.fuzzy_threshold,
        )
        counts[result.method] = counts.get(result.method, 0) + 1
        rows.append((
            result.method, name,
            result.canonical or "—",
            result.confidence,
        ))

    # Filter
    if args.show == "unmatched":
        rows = [r for r in rows if r[0] == "unmatched"]
    elif args.show == "fuzzy":
        rows = [r for r in rows if r[0] in ("fuzzy", "unmatched")]

    # Print
    print(
        f"\n{'method':<10} {'external_name':<32} → {'canonical':<22} {'conf':>5}",
        file=sys.stderr,
    )
    print("-" * 80, file=sys.stderr)
    for method, ext, canonical, conf in rows:
        print(
            f"{method:<10} {ext:<32} → {canonical:<22} {conf:>5.2f}",
            file=sys.stderr,
        )
    print("-" * 80, file=sys.stderr)
    print(
        "Summary: exact=%d alias=%d fuzzy=%d unmatched=%d" % (
            counts.get("exact", 0), counts.get("alias", 0),
            counts.get("fuzzy", 0), counts.get("unmatched", 0),
        ),
        file=sys.stderr,
    )
    if counts.get("unmatched", 0) > 0:
        print(
            "\n→ Add the unmatched entries to CUP_TEAM_ALIASES in "
            "apps/api/src/nutmeg/utils/team_canonical.py",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
