"""nutmeg-beta-test — independent-signal diagnostic (article priority #1).

Re-runs the β blend test of model vs Pinnacle on the held-out walk-forward
set. Tracks, over seasons / retrains, whether our model has developed any
independent signal beyond the sharp on 1X2 closing lines.

    nutmeg-beta-test                 # full run (CatBoost; a few minutes)
    nutmeg-beta-test --output docs/beta_test_latest.md

NOTE: requires --with-ensemble-equivalent training (CatBoost), so it is slow
(~minutes). It is a periodic diagnostic, not a per-commit check.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nutmeg.v4.data import load_all_matches
from nutmeg.v4.eval.independent_signal import beta_sweep, verdict
from nutmeg.v4.eval.walk_forward import WalkForwardConfig, run_walk_forward

_VARIANTS = [("cat_dc", "raw CatBoost"), ("cat_dc_temp", "calibrated CatBoost")]


def _format_report(blocks: list[tuple[str, dict]]) -> str:
    lines = [
        "# Independent-signal (β) test — model vs Pinnacle",
        "",
        "`p_final ∝ p_pin^(1-β) · p_model^β` swept on the held-out walk-forward",
        "1X2 set. β≈0 ⇒ Pinnacle dominates; β>0 helping ⇒ model has independent",
        "signal. The argmin β is in-sample (optimistic) — read the SHAPE: does any",
        "β>0 beat pure Pinnacle?",
        "",
    ]
    for label, r in blocks:
        lines += [
            f"## {label}  (n={r['n']:,})",
            "",
            f"- model-alone log-loss : {r['model_logloss']:.4f}",
            f"- Pinnacle-alone       : {r['pin_logloss']:.4f}",
            f"- gap (model − pin)    : {r['gap']:+.4f}",
            f"- best β               : {r['best_beta']:+.2f}  "
            f"(log-loss {r['best_logloss']:.4f})",
            f"- any β>0 beats Pinnacle? : {'YES' if r['positive_beta_helps'] else 'NO'}",
            f"- **verdict**: {verdict(r)}",
            "",
            "| β | log-loss |",
            "|---|---|",
        ]
        for b, ll in r["curve"]:
            if b in (-0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5) or abs(
                b - r["best_beta"]
            ) < 1e-9:
                mark = " ← best" if abs(b - r["best_beta"]) < 1e-9 else ""
                lines.append(f"| {b:+.2f} | {ll:.4f}{mark} |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="β independent-signal test: model vs Pinnacle")
    ap.add_argument("--data", default="data/historical_sources/football_data_co_uk")
    ap.add_argument("--output", default=None, help="optional markdown report path")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if not args.quiet:
        print(f"loading matches from {args.data} ...", file=sys.stderr)
    df = load_all_matches(args.data)
    if not args.quiet:
        print(f"  {len(df):,} matches; running walk-forward (CatBoost) ...", file=sys.stderr)
    res = run_walk_forward(df, WalkForwardConfig(with_ensemble=True))
    pa = res["pooled_arrays"]

    pin = pa.get("pinnacle_gbm")
    y = pa.get("y_gbm")
    if pin is None or y is None or len(y) == 0:
        print("ERROR: no GBM-eligible held-out rows with Pinnacle", file=sys.stderr)
        return 1

    blocks: list[tuple[str, dict]] = []
    for key, label in _VARIANTS:
        model = pa.get(key)
        if model is None or len(model) == 0:
            continue
        blocks.append((label, beta_sweep(model, pin, y)))

    report = _format_report(blocks)
    print(report)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(report, encoding="utf-8")
        if not args.quiet:
            print(f"  wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
