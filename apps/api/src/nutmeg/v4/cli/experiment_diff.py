"""nutmeg-experiment-diff — compare two tracked walk-forward experiments.

Usage:

    # List all experiments
    nutmeg-experiment-diff --list

    # Show the most recent diff (latest two experiments)
    nutmeg-experiment-diff

    # Compare two specific experiments by SHA prefix
    nutmeg-experiment-diff --a abc1234 --b def5678 \\
        --out docs/weekly/diff-2025-W18.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nutmeg.v4.eval.experiment_tracker import (
    DEFAULT_EXPERIMENTS_DIR,
    format_diff_card,
    list_experiments,
)


def _select_record(records, sha_prefix: str | None):
    """Find one record matching the prefix, or raise."""
    if sha_prefix is None:
        return None
    matches = [r for r in records if r.sha.startswith(sha_prefix)]
    if not matches:
        raise SystemExit(f"no experiment matching SHA prefix {sha_prefix!r}")
    if len(matches) > 1:
        raise SystemExit(
            f"ambiguous SHA prefix {sha_prefix!r}: matches {[m.sha for m in matches]}"
        )
    return matches[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V5 W10 experiment diff CLI")
    parser.add_argument(
        "--experiments-dir",
        default=str(DEFAULT_EXPERIMENTS_DIR),
        help="Directory containing tracked experiments",
    )
    parser.add_argument("--list", action="store_true", help="List all experiments and exit")
    parser.add_argument("--a", default=None, help="SHA prefix of the 'before' experiment")
    parser.add_argument("--b", default=None, help="SHA prefix of the 'after' experiment")
    parser.add_argument("--out", default=None, help="Write Markdown diff to this file")
    args = parser.parse_args(argv)

    records = list_experiments(args.experiments_dir)
    if not records:
        print(f"No experiments found under {args.experiments_dir}", file=sys.stderr)
        return 1

    if args.list:
        for r in records:
            slots = ", ".join(
                k for k in ("gbm_dc_temp", "cat_dc", "ensemble") if k in r.pooled
            )
            print(f"{r.sha:8s}  {r.timestamp_utc}  {r.model_type:9s}  slots: {slots}")
        return 0

    # Default: diff latest two
    if args.a and args.b:
        a, b = _select_record(records, args.a), _select_record(records, args.b)
    elif len(records) >= 2:
        a, b = records[-2], records[-1]
    else:
        print("Need at least 2 experiments to diff (or pass --a/--b explicitly)",
              file=sys.stderr)
        return 1

    card = format_diff_card(a, b)
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(card)
        print(f"Wrote {p}", file=sys.stderr)
    else:
        print(card)
    return 0


if __name__ == "__main__":
    sys.exit(main())
