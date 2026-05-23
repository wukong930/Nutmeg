"""V4 benchmark CLI.

Usage:
    python -m nutmeg.v4.cli.bench [--data DIR] [--output PATH]

Runs the canonical walk-forward evaluation (Pinnacle baseline vs V4 MLE DC vs uniform)
and writes a Markdown card.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nutmeg.v4.data import load_all_matches
from nutmeg.v4.eval.report import format_card
from nutmeg.v4.eval.walk_forward import WalkForwardConfig, run_walk_forward


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V4 walk-forward benchmark")
    parser.add_argument(
        "--data",
        default="data/historical_sources/football_data_co_uk",
        help="Path to football-data.co.uk source tree",
    )
    parser.add_argument(
        "--output",
        default="docs/v4_baseline_card.md",
        help="Where to write the Markdown card",
    )
    parser.add_argument(
        "--json-output",
        default=None,
        help="Optional path to also write the raw result as JSON",
    )
    parser.add_argument(
        "--with-ensemble",
        action="store_true",
        help="Also train XGBoost + CatBoost + stacker (V5 W6 ensemble path). "
        "Adds ~60s per fold; required to see xgb/cat/ensemble columns in the card.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if not args.quiet:
        print(f"Loading matches from {args.data} ...", file=sys.stderr)
    df = load_all_matches(args.data)
    if not args.quiet:
        print(f"  loaded {len(df):,} matches", file=sys.stderr)

    cfg = WalkForwardConfig(with_ensemble=args.with_ensemble)
    if not args.quiet:
        ens_msg = " + ensemble (xgb+cat+stacker)" if args.with_ensemble else ""
        print(
            f"Running walk-forward{ens_msg}: cutoff={cfg.test_cutoff.date()}, "
            f"train_window={cfg.train_window_days}d ...",
            file=sys.stderr,
        )
    result = run_walk_forward(df, cfg)

    card = format_card(result)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(card, encoding="utf-8")
    if not args.quiet:
        print(f"  wrote {out_path}", file=sys.stderr)

    if args.json_output:
        # Strip numpy arrays before dumping
        def _scrub(o):
            if isinstance(o, dict):
                return {k: _scrub(v) for k, v in o.items()}
            if isinstance(o, list):
                return [_scrub(v) for v in o]
            if hasattr(o, "tolist"):
                return o.tolist()
            return o
        Path(args.json_output).write_text(json.dumps(_scrub(result), indent=2, default=str))

    # Echo to stdout for convenience
    if not args.quiet:
        print()
        print(card)

    return 0


if __name__ == "__main__":
    sys.exit(main())
