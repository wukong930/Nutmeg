# V9 W5 — ECE-vs-log-loss per-bucket Brier audit

_Closes the V5 W12-noted mystery that 3 retrospectives (V6, V7, V8)
flagged but never investigated. CatBoost's ECE (0.0120) is BETTER than
Pinnacle's (0.0123), yet log-loss is 0.0056 WORSE. W5 decomposes the
gap by p(true\_class) bucket to determine whether it's a fixable
concentration or a structural ceiling._

## TL;DR (verdict)

**🎯 Concentrated bucket found** — but it's not a single-bucket story.

The pooled `+0.0056` log-loss gap is the SUM of 4 non-trivial bucket
contributions (2 positive, 2 negative). The largest bucket — `(0.6, 0.8]`
on `p(true_class)` — contributes `+0.0082`, more than the entire gap.

| Bucket | n_Pin | n_Cat | weighted-ll_Pin | weighted-ll_Cat | Δ (Cat − Pin) |
|---|---:|---:|---:|---:|---:|
| `[0.0, 0.2]` | 270 | 251 | 0.1153 | 0.1070 | **-0.0083** |
| `(0.2, 0.4]` | 2165 | 2164 | 0.6152 | 0.6209 | **+0.0057** |
| `(0.4, 0.6]` | 1262 | 1262 | 0.2088 | 0.2109 | **+0.0021** |
| `(0.6, 0.8]` | 542 | 619 | 0.0473 | 0.0556 | **+0.0082** |
| `(0.8, 1.0]` | 92 | 35 | 0.0037 | 0.0016 | **-0.0021** |
| **Sum** | — | — | **0.9904** | **0.9960** | **+0.0056** |

Reading the table:
- CatBoost is **better** at both extremes (very low + very high
  `p(true)`). At low `p`, CatBoost slightly under-confidently predicts
  improbable outcomes (good when they actually happen).
- CatBoost is **worse** in the middle and especially `(0.6, 0.8]`,
  where it places 619 rows vs Pinnacle's 542 — i.e. CatBoost is **too
  often** confident around 0.7 when Pinnacle declines to be.

The `+0.0082` from `(0.6, 0.8]` is the biggest single contributor and
overshoots the total gap. Two interpretations are plausible:

1. **Mis-calibration** — CatBoost's mid-high confidence (0.6-0.8)
   region is systematically over-confident, mapping rows that should
   be at p≈0.55 to p≈0.7. A per-bucket temperature would compress
   them back.
2. **Information gap** — Pinnacle simply *doesn't* go to 0.7 on
   matches where CatBoost does (it knows lineups, late injuries) so
   the 77-row population delta (619 vs 542) is the model picking up
   spurious confidence on rows Pinnacle wisely brackets at 0.5-0.6.

The V9 W5 audit cannot distinguish 1 vs 2 from numbers alone — that
needs the V9 W6 fix attempt.

## V9 W6 recommendation

**Try the cheap calibration tweak**:
- Fit a per-bucket isotonic regression specifically over the
  `p(true) ∈ (0.6, 0.8]` range, using the same OOF (out-of-fold)
  walk-forward predictions
- Re-evaluate pooled log-loss; expect either:
  - Modest improvement (~ -0.001 to -0.003): interpretation #1 wins;
    ship the calibration adjustment
  - No improvement: interpretation #2 wins; the population delta
    is the model finding signal Pinnacle's market-driven priors
    deliberately ignore, and "correcting" it would erase real edge

If the calibration tweak fails: document and **remove the
ECE-vs-log-loss mystery from the backlog permanently**. The audit
made it visible; W6 will determine which side of the line it falls.

## Why W5 was worth doing

3 retrospectives (V6 W12, V7 ship, V8 ship) listed this exact mystery
as backlog. Each time the rationale was "doesn't affect production but
might hide free lunch". Without per-bucket decomposition, neither
hypothesis was testable.

This module + audit was 1 day of work (`bucket_decomp.py` + CLI + 21
tests + write-up). Even if W6 finds no fixable gain, the audit:

- **Permanently retires** a recurring "should we look at this?" item
- Documents the bucket-population delta as the most likely structural
  explanation
- Adds a reusable analysis module — future model swaps can re-run
  `nutmeg-ece-audit --cutoff X` to instantly compare any two models'
  per-bucket calibration

## What W5 ships

### New module: `nutmeg.v4.eval.bucket_decomp`

| Function | Purpose |
|---|---|
| `bucket_breakdown(probs, y)` | Returns `list[BucketStats]` — per-bin n, avg p_true, log-loss contribution, Brier contribution |
| `bucket_breakdown_df(...)` | Same but as a DataFrame for joining |
| `compare_two_models(name_a, probs_a, name_b, probs_b, y)` | Side-by-side DataFrame with `weighted_ll_diff` (B − A) per bucket |
| `format_audit_card(...)` | Markdown card with pooled + per-bucket tables + verdict heuristic |

Default bins: `[0.0, 0.2, 0.4, 0.6, 0.8, 1.0]` (5 equal-width).
Bottom bin is left-closed `[lo, hi]`; higher bins are `(lo, hi]` to
avoid double-counting boundaries.

Bucketing variable is `p(true_class)` per row, NOT `p(argmax)`. This
makes log-loss + Brier directly decomposable: each row's loss is
fully captured by `-log(p(true))` and `(1 - p(true))^2`.

### Walk-forward returns `pooled_arrays`

`run_walk_forward(df, cfg)` now returns a `pooled_arrays` key
alongside the existing summary metrics:

```python
pooled_arrays = {
    "y_full": ...,         # all 5,019 rows including DC-only
    "y_gbm": ...,           # GBM-aligned 4,331 rows
    "pinnacle": ...,
    "pinnacle_gbm": ...,    # restricted to y_gbm rows
    "gbm_dc": ...,
    "gbm_dc_temp": ...,
    "cat_dc": ...,          # ← used by ece_audit
    "xgb_dc": ...,
    "ensemble": ...,
    "ensemble_temp": ...,
}
```

Pure additive — no caller currently reads it except the new CLI.

### New CLI: `nutmeg-ece-audit`

```bash
PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.ece_audit \
  --cutoff 2024-08-01 \
  --out docs/v9_w5_ece_audit.md
```

Runs `walk_forward` with `with_ensemble=True` (so CatBoost predictions
land in the pool), extracts `pinnacle_gbm`, `cat_dc`, `y_gbm`, calls
`format_audit_card`, writes the markdown card to `--out`, and also
prints it to stdout.

Estimated runtime ~30-60s (one full walk-forward training).

### 21 new tests (`tests/v4/test_bucket_decomp.py`)

| Group | Coverage |
|---|---|
| `TestPerRowPTrue` (2) | Per-row p(true_class) extraction uses correct column for each row's label |
| `TestBinBoundaries` (4) | Lowest bin left-closed; upper boundary inclusive; just-above goes to next bucket; p=1.0 → (0.8, 1.0] |
| `TestBucketStatsValues` (3) | log-loss = -log(mean p); Brier = (1-p)²; empty bucket → NaN |
| `TestDecompositionConsistency` (2) | **Sum of weighted log-loss across buckets == pooled log_loss** (sanity check, the whole module's correctness pivots on this) |
| `TestBucketBreakdownDF` (2) | Returns 5-row DataFrame; bin labels use `[` for first, `(` for others |
| `TestCompareTwoModels` (3) | Sum of weighted_ll equals each model's pooled; diff = B − A; n per bucket can differ between models |
| `TestFormatAuditCard` (4) | Card has all sections; concentrated/uniform verdict triggers correctly; test_label flows to title |
| `TestV9W5RegressionShape` (1) | Card is non-empty markdown with pipe tables (shape regression guard) |

**Full V4 suite: 792 passing** (771 pre-W5 + 21 new W5).

### Audit card itself

`docs/v9_w5_ece_audit.md` (the actual output) committed alongside
the module for reference / future model comparisons.

## Files touched in W5

```
apps/api/src/nutmeg/v4/eval/bucket_decomp.py      [+] new module (~120 lines, pure analysis)
apps/api/src/nutmeg/v4/eval/walk_forward.py       [M] +pooled_arrays in return dict
apps/api/src/nutmeg/v4/cli/ece_audit.py           [+] new CLI
pyproject.toml                                    [M] +nutmeg-ece-audit script entry
tests/v4/test_bucket_decomp.py                    [+] 21 tests
docs/v9_w5_ece_audit.md                           [+] audit output card
docs/v9_w5_ece_audit_writeup.md                   [+] this file
docs/V9_ROADMAP.md                                [M] W5 ✅
```

## What W5 doesn't do

- **No actual calibration fix.** W5 = audit only; W6 = (conditional)
  fix attempt. The W5 → W6 split is deliberate per V9 roadmap: don't
  spend on a fix until we know what we're fixing.
- **No multi-cutoff sanity check.** The audit was run for one cutoff
  (`2024-08-01`, the V5 W12 default). A multi-season replication
  (e.g. cutoffs 2022-08-01, 2023-08-01, 2024-08-01) would confirm
  whether the `(0.6, 0.8]` bucket pattern is stable or season-specific.
  Deferred to W6 if/when the calibration fix is actually attempted —
  cheaper to add then than now.
- **No per-class breakdown** (H/D/A). The bucketing collapses all
  three outcome classes into one `p(true_class)` axis. A separate
  audit by class might reveal e.g. "the gap is all in draws" — also
  deferred to W6.

## Next: V9 W6 (conditional)

If the V9 design principle holds ("ship when ready, not on Friday"),
W6 is either:
- A 1-day per-bucket isotonic calibration patch + multi-season
  verification, OR
- A 30-minute writeup confirming W5's "structural" interpretation

V9 ship gates W6 on whether the W6 fix attempt actually improves
pooled log-loss. If yes → ship the calibration adjustment as part of
v9.0. If no → ship v9.0 unchanged with the audit as documentation.
