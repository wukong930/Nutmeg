"""V4 multi-season benchmark.

Usage:
    python -m nutmeg.v4.cli.multi_season_bench [--data DIR] [--output PATH]
                                                [--cutoffs YYYY-MM-DD,YYYY-MM-DD,...]

Runs walk-forward at multiple cutoffs and produces a stability report.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from nutmeg.v4.data import load_all_matches
from nutmeg.v4.eval.multi_season import DEFAULT_CUTOFFS, run_multi_season
from nutmeg.v4.eval.multi_season_report import format_multi_season


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V4 multi-season benchmark")
    parser.add_argument("--data", default="data/historical_sources/football_data_co_uk")
    parser.add_argument(
        "--cutoffs", default=None,
        help="Comma-separated YYYY-MM-DD list (default: 22/23, 23/24, 24/25 season starts)",
    )
    parser.add_argument("--output", default="docs/v4_multi_season_card.md")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if not args.quiet:
        print(f"Loading matches ...", file=sys.stderr)
    df = load_all_matches(args.data)
    if not args.quiet:
        print(f"  {len(df):,} matches", file=sys.stderr)

    if args.cutoffs:
        cutoffs = tuple(pd.Timestamp(c) for c in args.cutoffs.split(","))
    else:
        cutoffs = DEFAULT_CUTOFFS

    if not args.quiet:
        print(f"Running walk-forward for {len(cutoffs)} cutoffs ...", file=sys.stderr)
    result = run_multi_season(df, cutoffs=cutoffs)
    if not args.quiet:
        print(f"  collected {result['n_seasons']} seasons", file=sys.stderr)

    card = format_multi_season(result)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(card, encoding="utf-8")
    if not args.quiet:
        print(f"  wrote {out}", file=sys.stderr)
        print()
        print(card)
    return 0


if __name__ == "__main__":
    sys.exit(main())
