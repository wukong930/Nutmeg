"""Per-bucket Brier + log-loss decomposition — V9 W5.

The V5 W12 mystery: CatBoost ECE (0.0120) is BETTER than Pinnacle
(0.0123) yet log-loss is 0.0056 worse. ECE averages calibration gaps;
log-loss penalizes confident-and-wrong predictions much more harshly
than confident-and-right. The two metrics can disagree when the model
is well-calibrated on average but mis-confidently wrong in specific
buckets.

This module splits per-class predictions by predicted-probability bin
and decomposes Brier + log-loss inside each bin. If CatBoost's gap to
Pinnacle is concentrated in (say) 0.6-0.8 buckets, that's a fixable
calibration weakness; if the gap spreads uniformly across all buckets,
it's structural — Pinnacle just has information CatBoost doesn't.

The module is pure analysis — no training, no model dependency. Input
is two probability arrays (shape (N, 3) for H/D/A) plus the integer
label vector. Output is a per-bucket DataFrame + markdown summary.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from nutmeg.v4.eval.metrics import encode_labels


DEFAULT_BIN_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
"""5 equal-width bins covering [0, 1]. Adjustable per call but stable
across the audit so all comparisons use the same buckets."""


@dataclass(frozen=True)
class BucketStats:
    """Per-bucket aggregates for one model on one prediction stream.

    `predicted_prob` is the predicted probability for the ACTUAL outcome
    on each row (not the argmax). This makes log-loss / Brier directly
    decomposable: each row's loss is fully captured by p(true_class).
    """

    bin_lo: float
    bin_hi: float
    n: int
    avg_predicted_prob: float       # mean p(true_class) in this bucket
    log_loss_contribution: float    # -log(p) averaged across rows in bucket
    brier_contribution: float       # (1 - p)^2 averaged across rows


def _per_row_p_true(probs: np.ndarray, y) -> np.ndarray:
    """Extract p(true_class) for each row of a (N, 3) probability matrix.

    Used as the bucketing variable AND the decomposition target.
    """
    idx = encode_labels(y)
    probs = np.asarray(probs, dtype=float)
    n = probs.shape[0]
    # Floor at 1e-15 to avoid log(0) — same epsilon as metrics.log_loss
    p_true = np.maximum(probs[np.arange(n), idx], 1e-15)
    return p_true


def bucket_breakdown(
    probs: np.ndarray,
    y,
    *,
    bin_edges: tuple = DEFAULT_BIN_EDGES,
) -> list[BucketStats]:
    """Decompose log-loss + Brier into per-bucket contributions.

    Bins are defined by `bin_edges` on `p(true_class)`. The bottom-bucket
    is left-closed `[lo, hi]`; higher buckets are left-open `(lo, hi]`
    to avoid double-counting the boundary.
    """
    p_true = _per_row_p_true(probs, y)
    out: list[BucketStats] = []
    for i in range(len(bin_edges) - 1):
        lo = float(bin_edges[i])
        hi = float(bin_edges[i + 1])
        if i == 0:
            mask = (p_true >= lo) & (p_true <= hi)
        else:
            mask = (p_true > lo) & (p_true <= hi)
        n = int(mask.sum())
        if n == 0:
            out.append(BucketStats(
                bin_lo=lo, bin_hi=hi, n=0,
                avg_predicted_prob=float("nan"),
                log_loss_contribution=float("nan"),
                brier_contribution=float("nan"),
            ))
            continue
        bucket_p = p_true[mask]
        out.append(BucketStats(
            bin_lo=lo, bin_hi=hi, n=n,
            avg_predicted_prob=float(bucket_p.mean()),
            log_loss_contribution=float(-np.log(bucket_p).mean()),
            brier_contribution=float(((1.0 - bucket_p) ** 2).mean()),
        ))
    return out


def bucket_breakdown_df(
    probs: np.ndarray,
    y,
    *,
    bin_edges: tuple = DEFAULT_BIN_EDGES,
) -> pd.DataFrame:
    """Same as `bucket_breakdown` but returns a DataFrame for easy joining."""
    rows = bucket_breakdown(probs, y, bin_edges=bin_edges)
    return pd.DataFrame([{
        "bin": f"({r.bin_lo:.1f}, {r.bin_hi:.1f}]" if i > 0 else f"[{r.bin_lo:.1f}, {r.bin_hi:.1f}]",
        "n": r.n,
        "avg_p_true": r.avg_predicted_prob,
        "log_loss": r.log_loss_contribution,
        "brier": r.brier_contribution,
    } for i, r in enumerate(rows)])


def compare_two_models(
    name_a: str, probs_a: np.ndarray,
    name_b: str, probs_b: np.ndarray,
    y,
    *,
    bin_edges: tuple = DEFAULT_BIN_EDGES,
) -> pd.DataFrame:
    """Side-by-side decomp + per-bucket log-loss delta.

    Returns DataFrame with columns:
        bin, n_a, n_b, ll_a, ll_b, ll_diff (b - a),
        bucket_contribution_pct (where the test-set total gap is concentrated)

    Crucially: n_a and n_b can DIFFER per bucket because each model's
    p(true_class) lands in different bins for the same row. That's the
    whole point — the model's confidence distribution matters.
    """
    df_a = bucket_breakdown_df(probs_a, y, bin_edges=bin_edges)
    df_b = bucket_breakdown_df(probs_b, y, bin_edges=bin_edges)

    out = pd.DataFrame({
        "bin": df_a["bin"],
        f"n_{name_a}": df_a["n"],
        f"n_{name_b}": df_b["n"],
        f"avg_p_{name_a}": df_a["avg_p_true"],
        f"avg_p_{name_b}": df_b["avg_p_true"],
        f"ll_{name_a}": df_a["log_loss"],
        f"ll_{name_b}": df_b["log_loss"],
    })
    # Per-bucket weighted log-loss contribution (n * mean_ll / total_n)
    n_total_a = int(df_a["n"].sum())
    n_total_b = int(df_b["n"].sum())
    out[f"weighted_ll_{name_a}"] = (df_a["n"] / max(n_total_a, 1)) * df_a["log_loss"]
    out[f"weighted_ll_{name_b}"] = (df_b["n"] / max(n_total_b, 1)) * df_b["log_loss"]
    out["weighted_ll_diff"] = out[f"weighted_ll_{name_b}"] - out[f"weighted_ll_{name_a}"]

    # Sanity: column sums should equal each model's pooled log-loss
    return out


def format_audit_card(
    name_a: str, probs_a: np.ndarray,
    name_b: str, probs_b: np.ndarray,
    y,
    *,
    bin_edges: tuple = DEFAULT_BIN_EDGES,
    test_label: str = "24/25",
) -> str:
    """Markdown card with per-bucket breakdown + verdict.

    `name_a` is the baseline ceiling (Pinnacle); `name_b` is the
    challenger model (CatBoost). The verdict heuristic flags the
    bucket with the largest weighted_ll_diff > 0.001 as a candidate
    fixable bucket. If no bucket clears that threshold, the gap is
    spread uniformly → "structural" verdict.

    **Note (post-v9 P1#9)**: single-cutoff verdicts can be misleading
    when bucket-level patterns are non-stationary across seasons (see
    V9 W5/W6: the bucket flagged at 2024-08-01 was unstable across
    2022/2023/2024). For investigations, prefer
    `format_multi_cutoff_audit_card` which requires the same bucket
    to dominate on ≥ 2/3 cutoffs before flagging it as fixable.
    """
    cmp = compare_two_models(name_a, probs_a, name_b, probs_b, y, bin_edges=bin_edges)

    lines: list[str] = []
    lines.append(f"# ECE-vs-log-loss audit — {test_label} test set\n")
    lines.append(
        f"Two-model decomposition of where the pooled log-loss gap concentrates.\n"
    )

    # Pooled
    p_true_a = _per_row_p_true(probs_a, y)
    p_true_b = _per_row_p_true(probs_b, y)
    pooled_ll_a = float(-np.log(p_true_a).mean())
    pooled_ll_b = float(-np.log(p_true_b).mean())
    pooled_diff = pooled_ll_b - pooled_ll_a
    n = len(y)

    lines.append(f"**Pooled** (n = {n:,})\n")
    lines.append(f"| Model | log-loss |")
    lines.append(f"|---|---:|")
    lines.append(f"| {name_a} (ceiling) | {pooled_ll_a:.4f} |")
    lines.append(f"| {name_b} | {pooled_ll_b:.4f} |")
    lines.append(f"| **Gap** | **{pooled_diff:+.4f}** |\n")

    # Per-bucket
    lines.append("## Per-bucket breakdown (binned on p(true_class))\n")
    lines.append(
        f"| Bin | n_{name_a} | n_{name_b} | "
        f"avg p_{name_a} | avg p_{name_b} | "
        f"weighted-ll {name_a} | weighted-ll {name_b} | Δ ({name_b} − {name_a}) |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|"
    )
    for _, row in cmp.iterrows():
        lines.append(
            f"| {row['bin']} | {row[f'n_{name_a}']} | {row[f'n_{name_b}']} | "
            f"{row[f'avg_p_{name_a}']:.3f} | {row[f'avg_p_{name_b}']:.3f} | "
            f"{row[f'weighted_ll_{name_a}']:.4f} | {row[f'weighted_ll_{name_b}']:.4f} | "
            f"{row['weighted_ll_diff']:+.4f} |"
        )
    sum_a = float(cmp[f"weighted_ll_{name_a}"].sum())
    sum_b = float(cmp[f"weighted_ll_{name_b}"].sum())
    sum_diff = float(cmp["weighted_ll_diff"].sum())
    lines.append(
        f"| **Sum** | — | — | — | — | "
        f"**{sum_a:.4f}** | **{sum_b:.4f}** | **{sum_diff:+.4f}** |\n"
    )

    # Verdict
    biggest = cmp.loc[cmp["weighted_ll_diff"].idxmax()]
    biggest_diff = float(biggest["weighted_ll_diff"])
    biggest_bin = str(biggest["bin"])

    lines.append("## Verdict\n")
    if biggest_diff > 0.001:
        share = (biggest_diff / pooled_diff * 100) if pooled_diff > 0 else 0
        lines.append(
            f"🎯 **Concentrated bucket found**: bucket `{biggest_bin}` contributes "
            f"**+{biggest_diff:.4f}** to the gap "
            f"({share:.0f}% of the total {pooled_diff:+.4f}).\n"
        )
        lines.append(
            f"→ V9 W6 candidate fix: calibration tweak on `p(true_class) ∈ {biggest_bin}`. "
            f"Likely a per-bucket isotonic or temperature adjustment.\n"
        )
    else:
        lines.append(
            f"❌ **Gap is spread uniformly** — no bucket above the +0.001 threshold "
            f"(biggest: `{biggest_bin}` at {biggest_diff:+.4f}). "
            f"The {pooled_diff:+.4f} log-loss gap to {name_a} appears to be "
            f"**structural** — Pinnacle has information CatBoost doesn't access "
            f"(typically lineups + late-injury news), not a fixable miscalibration.\n"
        )
        lines.append(
            f"→ V9 W6: **skip** the calibration fix. Remove ECE-vs-log-loss "
            f"mystery from the backlog. Future log-loss gains require new "
            f"features, not better calibration of existing ones.\n"
        )

    return "\n".join(lines)


def format_multi_cutoff_audit_card(
    name_a: str, name_b: str,
    per_cutoff: list[dict],
    *,
    bin_edges: tuple = DEFAULT_BIN_EDGES,
    min_dominant_bin_count: int | None = None,
) -> str:
    """post-v9 P1#9: multi-cutoff verdict closing V9 retrospective W5 self-criticism.

    The V9 W5 single-cutoff verdict ("🎯 concentrated bucket found") over-promised
    because it couldn't see year-to-year stability. V9 W6's multi-cutoff ablation
    proved the (0.6, 0.8] bucket pattern was non-stationary (iso fixed it at
    2022-08-01 but worsened it at 2023/2024). This function bakes the multi-cutoff
    check into the audit itself so future investigations don't fall into the same
    trap.

    Parameters
    ----------
    per_cutoff : list of dict
        Each dict has keys ``cutoff`` (str date), ``probs_a`` (ndarray (N, 3)),
        ``probs_b`` (ndarray (N, 3)), ``y`` (label vector). Must contain ≥ 2
        entries — single-cutoff calls should use ``format_audit_card`` directly.
    min_dominant_bin_count : int, optional
        Minimum number of cutoffs the same bin must dominate before the verdict
        flags it as a fixable candidate. Default = ceil(2/3 of cutoffs); for 3
        cutoffs that's 2.
    """
    if len(per_cutoff) < 2:
        raise ValueError(
            "format_multi_cutoff_audit_card requires ≥ 2 cutoffs; "
            "use format_audit_card for single-cutoff analysis"
        )
    if min_dominant_bin_count is None:
        # 2/3-rounded-up rule: stable enough to flag, lenient enough to surface
        min_dominant_bin_count = (2 * len(per_cutoff) + 2) // 3

    # Per-cutoff aggregates
    per_cutoff_summary: list[dict] = []
    for entry in per_cutoff:
        cutoff = entry["cutoff"]
        probs_a, probs_b, y = entry["probs_a"], entry["probs_b"], entry["y"]
        cmp = compare_two_models(name_a, probs_a, name_b, probs_b, y, bin_edges=bin_edges)
        p_true_a = _per_row_p_true(probs_a, y)
        p_true_b = _per_row_p_true(probs_b, y)
        pooled_a = float(-np.log(p_true_a).mean())
        pooled_b = float(-np.log(p_true_b).mean())
        biggest_row = cmp.loc[cmp["weighted_ll_diff"].idxmax()]
        per_cutoff_summary.append({
            "cutoff": cutoff,
            "n": int(len(y)),
            "pooled_a": pooled_a,
            "pooled_b": pooled_b,
            "pooled_diff": pooled_b - pooled_a,
            "biggest_bin": str(biggest_row["bin"]),
            "biggest_diff": float(biggest_row["weighted_ll_diff"]),
            "cmp": cmp,
        })

    lines: list[str] = []
    lines.append(
        f"# Multi-cutoff ECE-vs-log-loss audit — "
        f"{len(per_cutoff_summary)} cutoffs\n"
    )
    lines.append(
        f"Per-bucket decomposition of the {name_b} vs {name_a} pooled "
        f"log-loss gap, repeated across {len(per_cutoff_summary)} cutoffs "
        "so non-stationary patterns are visible. Verdict flags a bucket "
        f"only if it dominates on ≥ {min_dominant_bin_count}/"
        f"{len(per_cutoff_summary)} cutoffs (closes V9 retrospective "
        "W5 self-criticism).\n"
    )

    # Pooled per cutoff
    lines.append("## Pooled log-loss per cutoff\n")
    lines.append(
        f"| Cutoff | n | {name_a} | {name_b} | Δ ({name_b} − {name_a}) |"
    )
    lines.append("|---|---:|---:|---:|---:|")
    for r in per_cutoff_summary:
        lines.append(
            f"| {r['cutoff']} | {r['n']:,} | {r['pooled_a']:.4f} | "
            f"{r['pooled_b']:.4f} | {r['pooled_diff']:+.4f} |"
        )
    lines.append("")

    # Per-cutoff dominant bucket
    lines.append("## Per-cutoff dominant bucket (largest weighted-ll Δ)\n")
    lines.append("| Cutoff | Dominant bin | Δ contribution |")
    lines.append("|---|---|---:|")
    for r in per_cutoff_summary:
        lines.append(
            f"| {r['cutoff']} | `{r['biggest_bin']}` | {r['biggest_diff']:+.4f} |"
        )
    lines.append("")

    # Cross-cutoff stability check
    from collections import Counter
    bin_counts = Counter(r["biggest_bin"] for r in per_cutoff_summary)
    most_common_bin, most_common_count = bin_counts.most_common(1)[0]
    avg_diff_in_dominant = float(np.mean([
        r["biggest_diff"] for r in per_cutoff_summary
        if r["biggest_bin"] == most_common_bin
    ]))

    lines.append("## Cross-cutoff stability\n")
    lines.append(
        f"- Most-frequent dominant bin: `{most_common_bin}` "
        f"({most_common_count}/{len(per_cutoff_summary)} cutoffs)\n"
        f"- Mean Δ in that bin (only the cutoffs where it dominated): "
        f"`{avg_diff_in_dominant:+.4f}`\n"
        f"- Threshold for 'stable': ≥ {min_dominant_bin_count}/"
        f"{len(per_cutoff_summary)} cutoffs AND mean Δ > 0.001\n"
    )

    # Verdict
    lines.append("## Verdict\n")
    stable = most_common_count >= min_dominant_bin_count and avg_diff_in_dominant > 0.001
    if stable:
        lines.append(
            f"🎯 **Stable concentrated bucket**: `{most_common_bin}` dominates "
            f"{most_common_count}/{len(per_cutoff_summary)} cutoffs with mean "
            f"Δ `{avg_diff_in_dominant:+.4f}`. This is a credible calibration "
            f"target — a per-bucket isotonic / temperature on `{most_common_bin}` "
            f"would address the same locus across multiple seasons. Worth a "
            f"V9 W6-style ablation attempt (with multi-cutoff verification of "
            f"the FIX too, not just the audit).\n"
        )
    elif most_common_count >= min_dominant_bin_count:
        lines.append(
            f"🟡 **Same bin recurs but the gap is small**: `{most_common_bin}` "
            f"dominates {most_common_count}/{len(per_cutoff_summary)} cutoffs but "
            f"mean Δ is `{avg_diff_in_dominant:+.4f}` < +0.001 threshold. "
            f"Calibration tweak unlikely to clear noise. Document as "
            f"low-priority structural pattern.\n"
        )
    else:
        lines.append(
            f"❌ **Non-stationary gap**: the dominant bin varies across "
            f"cutoffs (most common `{most_common_bin}` only "
            f"{most_common_count}/{len(per_cutoff_summary)}). The gap is "
            f"structural — different rows mis-fit each season. "
            f"**No fixable bucket exists**; calibration won't help. "
            f"(This is the pattern V9 W6 confirmed; the single-cutoff "
            f"V9 W5 audit would have flagged 🎯 but multi-cutoff would "
            f"correctly say ❌.)\n"
        )

    return "\n".join(lines)


__all__ = [
    "DEFAULT_BIN_EDGES",
    "BucketStats",
    "bucket_breakdown",
    "bucket_breakdown_df",
    "compare_two_models",
    "format_audit_card",
    "format_multi_cutoff_audit_card",
]
