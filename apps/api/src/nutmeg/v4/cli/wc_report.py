"""nutmeg-wc-report — V10 W4 Day 2.

Summarize WC predictions vs actual outcomes from the wc_predictions
table. Produces a markdown report with hit-rate, log-loss, ECE-like
calibration check, and a per-match breakdown.

The user-facing artifact during the tournament — answers the question
"how is our WC model actually doing?" once enough matches have settled.

Examples:

    # Markdown summary across all settled WC 2026 predictions
    nutmeg-wc-report --db data/v4_observation.db

    # Filter to one season
    nutmeg-wc-report --db data/v4_observation.db --season 2022

    # Write to a file (e.g., for the daily cron to commit to docs/)
    nutmeg-wc-report --db data/v4_observation.db \\
        --out docs/wc/2026_report_$(date +%Y-%m-%d).md
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import math
import sys
from pathlib import Path
from typing import Iterable

from nutmeg.v4.observation.wc_log import fetch_wc_predictions


log = logging.getLogger("wc-report")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _log_loss(rows: list[dict]) -> float:
    """Mean -log P(actual) across settled rows."""
    if not rows:
        return float("nan")
    eps = 1e-9
    total = 0.0
    for r in rows:
        ph = max(eps, min(1.0 - eps, r["p_home"]))
        pd = max(eps, min(1.0 - eps, r["p_draw"]))
        pa = max(eps, min(1.0 - eps, r["p_away"]))
        outc = r["outcome"]
        p_actual = (ph, pd, pa)[outc]
        total += -math.log(p_actual)
    return total / len(rows)


def _hit_rate(rows: list[dict]) -> tuple[int, int]:
    """Count of matches where the highest-probability outcome was the
    actual outcome. Returns (n_hits, n_total)."""
    if not rows:
        return 0, 0
    hits = 0
    for r in rows:
        probs = (r["p_home"], r["p_draw"], r["p_away"])
        pred_outcome = max(range(3), key=lambda i: probs[i])
        if pred_outcome == r["outcome"]:
            hits += 1
    return hits, len(rows)


def _calibration_bucket_summary(rows: list[dict], n_bins: int = 5) -> list[dict]:
    """Bucket predicted-max-probability vs actual hit-rate.

    For each row, take max(p_home, p_draw, p_away) — the model's
    confidence on its tip. Bucket into n_bins, compare mean predicted
    confidence vs mean hit rate within each bucket. Big divergence →
    calibration issue.
    """
    if not rows:
        return []
    buckets: list[list[dict]] = [[] for _ in range(n_bins)]
    for r in rows:
        probs = (r["p_home"], r["p_draw"], r["p_away"])
        pred_outcome = max(range(3), key=lambda i: probs[i])
        confidence = probs[pred_outcome]
        # Predicted confidence is bounded [1/3, 1.0] — bucket by that range
        # so the buckets correspond to meaningful confidence levels.
        # bin = floor((conf - 1/3) / (2/3) * n_bins)
        norm = (confidence - 1.0 / 3.0) / (2.0 / 3.0)
        idx = min(n_bins - 1, max(0, int(norm * n_bins)))
        buckets[idx].append({**r, "_pred": pred_outcome, "_conf": confidence})

    out = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        avg_conf = sum(b["_conf"] for b in bucket) / len(bucket)
        hits = sum(1 for b in bucket if b["_pred"] == b["outcome"])
        out.append({
            "bucket": i,
            "n": len(bucket),
            "avg_predicted_confidence": avg_conf,
            "actual_hit_rate": hits / len(bucket),
        })
    return out


def _format_match_line(r: dict) -> str:
    tip = "H" if r["p_home"] >= max(r["p_draw"], r["p_away"]) else \
          "D" if r["p_draw"] >= r["p_away"] else "A"
    outcome_label = ("H", "D", "A")[r["outcome"]]
    correct = "✓" if tip == outcome_label else "✗"
    return (
        f"| {r['match_date']} | {r['home_team']} | {r['away_team']} | "
        f"{r['p_home']:.2f} | {r['p_draw']:.2f} | {r['p_away']:.2f} | "
        f"{tip} | {r['home_goals']}-{r['away_goals']} | "
        f"**{outcome_label}** | {correct} |"
    )


def render_markdown(rows: list[dict], season: int | None) -> str:
    settled = [r for r in rows if r["outcome"] is not None]
    pending = [r for r in rows if r["outcome"] is None]

    season_label = f"WC {season}" if season else "WC (all seasons)"
    lines = [
        f"# {season_label} — Live Hit-Rate Report",
        "",
        f"_Generated {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}_",
        "",
        f"**Total predictions tracked:** {len(rows)}",
        f"**Settled (have outcomes):** {len(settled)}",
        f"**Pending (not yet played):** {len(pending)}",
        "",
    ]

    if not settled:
        lines.append("_No settled matches yet — report is informational only._\n")
        return "\n".join(lines)

    # Headline metrics
    log_loss = _log_loss(settled)
    n_hits, n_total = _hit_rate(settled)
    hit_pct = n_hits / n_total if n_total else 0.0

    lines.extend([
        "## Headline",
        "",
        f"- **Log-loss**: `{log_loss:.4f}`",
        f"- **Hit-rate** (tip = actual outcome): "
        f"**{n_hits}/{n_total} = {hit_pct:.1%}**",
        "",
        "Hit-rate baselines:",
        "  - **33.3%** = random guessing on 3 outcomes",
        "  - **~50%** = Pinnacle-blended ceiling (per V10 W1 walk-forward "
        "on WC 2018+2022)",
        "  - **>56%** = anomalously high; expect regression to mean",
        "",
    ])

    # Calibration buckets
    bucket_rows = _calibration_bucket_summary(settled)
    if bucket_rows and len(settled) >= 10:
        lines.extend([
            "## Calibration check",
            "",
            "Predicted confidence (max of p_H/p_D/p_A) vs actual hit-rate. "
            "Well-calibrated → avg confidence ≈ actual hit-rate per bucket.",
            "",
            "| Confidence bucket | n | Avg predicted | Actual hit-rate | Diff |",
            "|---:|---:|---:|---:|---:|",
        ])
        for b in bucket_rows:
            diff = b["actual_hit_rate"] - b["avg_predicted_confidence"]
            lines.append(
                f"| {b['bucket']} | {b['n']} | "
                f"{b['avg_predicted_confidence']:.2%} | "
                f"{b['actual_hit_rate']:.2%} | {diff:+.2%} |"
            )
        lines.append("")

    # Per-match table — settled only
    lines.extend([
        "## Settled matches (chronological)",
        "",
        "| Date | Home | Away | P(H) | P(D) | P(A) | Tip | Final | Result | ✓/✗ |",
        "|:-----|:-----|:-----|---:|---:|---:|:---:|:---:|:---:|:---:|",
    ])
    for r in sorted(settled, key=lambda x: x["kickoff_utc"] or x["match_date"]):
        lines.append(_format_match_line(r))
    lines.append("")

    # Pending list (just for awareness)
    if pending:
        lines.append("## Pending matches (not yet played)")
        lines.append("")
        for r in sorted(pending, key=lambda x: x["kickoff_utc"] or x["match_date"]):
            tip = "H" if r["p_home"] >= max(r["p_draw"], r["p_away"]) else \
                  "D" if r["p_draw"] >= r["p_away"] else "A"
            lines.append(
                f"- `{r['match_date']}` {r['home_team']} vs {r['away_team']} "
                f"(tip: **{tip}**, p={max(r['p_home'], r['p_draw'], r['p_away']):.2f})"
            )
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="V10 W4 — WC predictions vs outcomes summary"
    )
    p.add_argument(
        "--db", default="data/v4_observation.db",
        help="Observation DB path (default data/v4_observation.db)",
    )
    p.add_argument(
        "--season", type=int, default=None,
        help="Filter to one WC season (default: include all seasons)",
    )
    p.add_argument(
        "--out", default="-",
        help="Markdown output path; '-' for stdout (default)",
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.quiet:
        log.setLevel(logging.WARNING)

    db_path = Path(args.db)
    if not db_path.exists():
        log.error("observation DB not found: %s", db_path)
        return 1

    rows = fetch_wc_predictions(db_path, season=args.season)
    report = render_markdown(rows, season=args.season)
    if args.out == "-":
        print(report)
    else:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        log.info("wrote %d bytes → %s", len(report), out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
