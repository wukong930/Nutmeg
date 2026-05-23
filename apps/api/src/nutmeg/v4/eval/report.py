"""Generate the V4 baseline comparison card."""
from __future__ import annotations

from datetime import datetime, timezone


def _delta(model: float, baseline: float) -> str:
    return "{:+.4f}".format(model - baseline)


def _row(name, m, baseline_ll, bold=False):
    if m is None:
        return None
    n_name = ("**" + name + "**") if bold else name
    return "| {0:<32} | {1:.4f} | {2:.4f} | {3:.4f} | {4:.4f} | {5:>7} |".format(
        n_name, m["log_loss"], m["brier"], m["hit_rate"], m["ece"],
        _delta(m["log_loss"], baseline_ll),
    )


def format_card(result):
    if not result.get("per_league"):
        return "# V4 Baseline Card\n\n(no results)\n"

    cfg = result.get("cfg", {})
    pooled = result["pooled"]
    cals = result.get("calibrators", {})
    pin = pooled["pinnacle"]
    pin_gbm = pooled.get("pinnacle_gbm")
    mle = pooled["mle_dc"]
    mle_t = pooled.get("mle_dc_temp")
    gbm = pooled.get("gbm_dc")
    gbm_t = pooled.get("gbm_dc_temp")
    uni = pooled["uniform"]

    lines = []
    lines.append("# V4 Baseline Card")
    lines.append("")
    lines.append("_Generated " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + "_")
    lines.append("")
    lines.append("## Configuration")
    lines.append("")
    lines.append("- Train window:     **{}** days before cutoff".format(cfg.get("train_window_days", "?")))
    lines.append("- Validation window: **{}** days (temperature calibration fit)".format(cfg.get("validation_window_days", "?")))
    lines.append("- Test cutoff:      **{}**".format(cfg.get("test_cutoff", "?")))
    lines.append("- Test horizon:     **{}** days after cutoff".format(cfg.get("test_horizon_days", "?")))
    lines.append("- GBM rho:          **{}** (DC tau correction)".format(cfg.get("gbm_rho", "?")))
    if cals.get("mle_T"):
        lines.append("- Calibration T:    MLE={:.3f}  GBM={:.3f}".format(cals["mle_T"], cals.get("gbm_T") or 0))
    lines.append("")

    lines.append("## Pooled metrics across all leagues")
    lines.append("")
    lines.append("**Full-coverage test pool (PSC available): {:,} matches**".format(pooled.get("test_n_full", 0)))
    if pooled.get("test_n_gbm"):
        lines.append("**GBM-eligible pool (no missing features): {:,} matches**".format(pooled["test_n_gbm"]))
    lines.append("")
    lines.append("| Model                            | log-loss | Brier  | hit-rate | ECE    | Δ log-loss vs Pinnacle |")
    lines.append("|----------------------------------|---------:|-------:|---------:|-------:|-----------------------:|")
    rows = []
    rows.append(_row("Pinnacle closing (baseline)", pin, pin["log_loss"]))
    if pin_gbm:
        rows.append(_row("  Pinnacle (GBM-eligible)", pin_gbm, pin["log_loss"]))
    if gbm_t:
        rows.append(_row("V4 GBM-λ + DC + Temp", gbm_t, pin["log_loss"], bold=True))
    if gbm:
        rows.append(_row("V4 GBM-λ + DC (raw)", gbm, pin["log_loss"]))
    # V5 W6: alternative bases + ensemble (only present if walk-forward ran with_ensemble=True)
    xgb = pooled.get("xgb_dc")
    cat = pooled.get("cat_dc")
    ens = pooled.get("ensemble")
    ens_t = pooled.get("ensemble_temp")
    if xgb:
        rows.append(_row("V5 XGBoost + DC", xgb, pin["log_loss"]))
    if cat:
        rows.append(_row("V5 CatBoost + DC", cat, pin["log_loss"], bold=True))
    if ens:
        rows.append(_row("V5 Ensemble (stacker)", ens, pin["log_loss"]))
    if ens_t:
        rows.append(_row("V5 Ensemble + Temp", ens_t, pin["log_loss"]))
    if mle_t:
        rows.append(_row("V4 MLE DC + Temp", mle_t, pin["log_loss"]))
    rows.append(_row("V4 MLE DC (raw)", mle, pin["log_loss"]))
    rows.append(_row("Uniform 1/3", uni, pin["log_loss"]))
    for r in rows:
        if r:
            lines.append(r)
    lines.append("")

    best = gbm_t or gbm or mle_t or mle
    best_baseline = pin_gbm if (gbm_t or gbm) else pin
    gap = best["log_loss"] - best_baseline["log_loss"]
    total = uni["log_loss"] - best_baseline["log_loss"]
    pct = (1 - gap / total) * 100 if total > 0 else 0
    lines.append("**Best model captures {:.1f}% of available signal** (uniform→Pinnacle gap = {:.4f}; best closes {:.4f}).".format(pct, total, total - gap))
    lines.append("")

    lines.append("## Per-league breakdown")
    lines.append("")
    lines.append("| League | test_n | Pinnacle | MLE DC | MLE+Temp | GBM-λ+DC | GBM+Temp | GBM Δ |")
    lines.append("|--------|-------:|---------:|-------:|---------:|---------:|---------:|------:|")
    for r in result["per_league"]:
        p = r["pinnacle"]["log_loss"]
        mle = r["mle_dc"]["log_loss"]
        mt = r["mle_dc_temp"]["log_loss"] if r.get("mle_dc_temp") else None
        g = r["gbm_dc"]["log_loss"] if r.get("gbm_dc") else None
        gt = r["gbm_dc_temp"]["log_loss"] if r.get("gbm_dc_temp") else None
        gbm_delta = gt - p if gt is not None else None
        lines.append("| {0:<24} | {1:>5} | {2:.4f} | {3:.4f} | {4} | {5} | {6} | {7} |".format(
            r["league"], r["test_n"], p, mle,
            "{:.4f}".format(mt) if mt is not None else "—",
            "{:.4f}".format(g)  if g  is not None else "—",
            "{:.4f}".format(gt) if gt is not None else "—",
            "{:+.4f}".format(gbm_delta) if gbm_delta is not None else "—",
        ))
    lines.append("")

    lines.append("## Interpretation")
    lines.append("")
    lines.append("- **Pinnacle** = market closing line; ceiling for any model not using day-of info (lineups, late injuries).")
    lines.append("- **GBM-λ + DC** uses market closing odds as features, so it naturally tracks the market. It should NOT be expected to dramatically beat Pinnacle pooled — that would imply Pinnacle is materially inefficient.")
    lines.append("- The **practical alpha** for the user is: same probabilistic quality as Pinnacle, but with internal score-grid that enables 让球 / 大小球 / 比分 / 串关 computation that the market line alone can't.")
    lines.append("- Per-league regressions point to where extra features (xG, lineups, schedule congestion) would add value next.")
    lines.append("")
    return "\n".join(lines)
