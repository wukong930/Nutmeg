# V9 W6 — CatBoost calibration fix attempted — **NEGATIVE result**

_The conditional follow-up to V9 W5. V9 W5's audit pointed at the
`(0.6, 0.8]` p(true) bucket as the dominant log-loss gap contributor.
V9 W6 tried two standard calibration methods. Per-class isotonic
catastrophically over-fits across all 3 cutoffs (+0.05 to +0.10
log-loss). Temperature scaling is essentially neutral (mean Δ
−0.0001). Per the W5 verdict heuristic and the W6 ablation: this is
the structural-gap interpretation. The ECE-vs-log-loss mystery is
permanently closed; no production change ships in W6._

This is the **6th documented negative result** in the project (after
V5 W5 market dynamics, V5 W6 stacker, V5 W9 per-league T, V6 W5
lineup leak, V8 W4 cup ablation block). It costs ~3-4 hours and
permanently retires a backlog item that 3 retrospectives had flagged
as "should investigate one day". The audit was the answer.

## TL;DR

| Method | Improved vs raw on N cutoffs | Mean Δ log-loss | Recommendation |
|---|---:|---:|---|
| per-class isotonic | 0 / 3 | **+0.0789** (worse) | DO NOT SHIP |
| temperature scaling | 2 / 3 | -0.0001 (noise) | DO NOT SHIP |

## What W6 tested

The V9 W5 audit found the `(0.6, 0.8]` p(true) bucket dominates the
+0.0056 log-loss gap to Pinnacle at cutoff=2024-08-01 (n=4,331). The
W6 hypothesis: per-class isotonic regression fit on the same val
window as the existing GBM temperature calibrator could compress
CatBoost's over-confident 0.6-0.8 predictions back toward Pinnacle's
range.

W6 added two CatBoost-specific calibrators to `walk_forward.py`:
- `cal_cat_temp` — scalar T fit by minimizing val log-loss
- `cal_cat_iso` — three IsotonicRegression models (one per class)
  with renormalization after independent transforms

And ran a 3-cutoff ablation via `nutmeg-cat-calibration-ablation`.

## Multi-cutoff result

### Pooled log-loss

| Cutoff | n | Pinnacle | cat_raw | cat_temp | cat_iso | Δ temp | Δ iso |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022-08-01 | 4,884 | 0.9940 | 0.9984 | 0.9977 | **1.0454** | -0.0006 | +0.0470 |
| 2023-08-01 | 4,767 | 0.9865 | 0.9898 | 0.9894 | **1.0900** | -0.0004 | +0.1002 |
| 2024-08-01 | 4,331 | 0.9904 | 0.9960 | 0.9965 | **1.0855** | +0.0006 | +0.0895 |

### Target bucket `(0.6, 0.8]` weighted log-loss

| Cutoff | Pin wll | cat_raw wll | cat_iso wll | Δ raw vs Pin | Δ iso vs Pin |
|---|---:|---:|---:|---:|---:|
| 2022-08-01 | 0.0438 | 0.0506 | **0.0396** | +0.0067 | -0.0043 |
| 2023-08-01 | 0.0448 | 0.0488 | 0.0773 | +0.0040 | +0.0325 |
| 2024-08-01 | 0.0473 | 0.0556 | 0.0687 | +0.0082 | +0.0214 |

### Fitted temperatures

| Cutoff | T |
|---|---:|
| 2022-08-01 | 0.9563 |
| 2023-08-01 | 0.8655 |
| 2024-08-01 | 0.8521 |

T values are all < 1.0 (sharper) but close — within ~15%. Standard
calibration would push T > 1 for over-confidence; the val optimizer
preferring T < 1 means **CatBoost on the val window is actually a
touch under-confident**, opposite the W5 audit's bucket-level finding.

## Reading the result

Three patterns explain the failure together:

### 1. Isotonic per-class over-fits on this scale
- Each class isotonic has unbounded DOF (one knee per training point)
- Val window = 90 days = ~600-1,000 rows after GBM alignment
- That's below the 1,000+ recommended for isotonic stability per
  Guo et al. 2017 ("On Calibration of Modern Neural Networks")
- Result: iso WAS able to fix the target bucket at cutoff=2022-08-01
  (0.0396 < 0.0506) but destroyed enough other buckets to push pooled
  log-loss up by +0.047. Other cutoffs were worse on both axes.

### 2. CatBoost's global calibration is already nearly perfect
- Fitted T ranges from 0.85 to 0.96 — within ±15% of 1.0
- Mean Δ from temperature: -0.0001 — pure noise
- This matches the V5 W12 finding that CatBoost's ECE (0.0120) is
  already slightly better than Pinnacle's (0.0123)
- Pooled-level calibration is not where the gap lives

### 3. The bucket-level pattern is non-stationary
- At cutoff=2022-08-01, iso fixed the (0.6, 0.8] bucket (-0.0110 wll)
- At cutoff=2023-08-01, iso *worsened* it (+0.0285 wll)
- At cutoff=2024-08-01, iso *worsened* it (+0.0131 wll)
- If the over-confidence pattern shifted year-to-year, no static
  fit-on-val transform can track it

## Interpretation: the structural-gap reading wins

V9 W5's audit had two candidate explanations for the (0.6, 0.8]
bucket gap:

1. **Mis-calibration** — CatBoost is systematically over-confident
   at 0.7; per-bucket calibration could compress
2. **Information gap** — CatBoost's 619 rows at 0.6-0.8 (vs
   Pinnacle's 542) are picking up signal Pinnacle deliberately
   prices in (lineups, late injuries). "Fixing" the over-confidence
   would erase real edge

W6's negative result is **strong evidence for interpretation #2**.
If interpretation #1 were dominant, we'd expect at minimum the
temperature variant to improve pooled log-loss (it doesn't, mean
Δ ≈ 0). And the year-to-year instability is incompatible with a
stable miscalibration pattern.

This is exactly the "Pinnacle has information CatBoost doesn't
access" signal the V5 W12 retrospective hypothesized but couldn't
confirm without the per-bucket decomposition.

## What does NOT ship

- ❌ No production CatBoost calibration. Raw `cat_dc` stays as the
  V5 W12 default through V9 and beyond.
- ❌ No persistent isotonic / temperature artifact alongside the
  CatBoost `.cbm` file.
- ❌ No predict-path change in `nutmeg.v4.model.persist` or
  `predict_lambdas`.

## What DOES ship

- ✅ `walk_forward.py` builds `cat_dc_temp` + `cat_dc_iso` in the
  `with_ensemble=True` codepath. Pure infrastructure addition; gives
  future researchers the ability to re-run the comparison with
  different calibration variants (e.g. Dirichlet calibration, vector
  scaling, per-bucket-only isotonic) without re-writing the harness.
- ✅ `nutmeg-cat-calibration-ablation` CLI for multi-cutoff
  ablation reuse.
- ✅ This document — the audit chain (W5 audit → W6 fix attempt →
  negative result) is now the canonical answer to anyone asking
  "why doesn't anyone fix the ECE-vs-log-loss mystery?".

## Backlog impact

**ECE-vs-log-loss mystery → CLOSED PERMANENTLY**.

Three retrospectives (V6 W12, V7 ship, V8 ship) listed this as
"should investigate one day". V9 W5 + W6 spent ~3-4 hours doing it.
Verdict: structural information gap, not a fixable miscalibration.

The V9 retrospective will note: this is what "maintenance mode"
looks like — small, contained, documented investigations of
specific historical curiosities. The cost was bounded; the
deliverable is permanent.

## What W6 could have tried but didn't

- **Per-bucket-only isotonic** (only modify rows where p ∈ (0.6, 0.8])
  Marginal benefit even if it worked — the 2022 data already shows iso
  can fix the bucket but cratesothers; a per-bucket variant would
  prevent the crater but still wouldn't help in 2023/24 where the iso
  also damages the bucket itself.
- **Dirichlet calibration** (vector-scaling generalization of T)
  More params than T but still global. Unlikely to help given T is ≈ 1.
- **Per-class temperature** (3 Ts instead of 1)
  Same crit as Dirichlet.
- **Bayesian per-bucket priors / hierarchical calibration**
  V8 backlog item; high-cost, low expected gain given the structural
  diagnosis. Deferred.

Each would be additional W7+ work. None are obviously worth it given
the W6 verdict.

## Files touched in W6

```
apps/api/src/nutmeg/v4/eval/walk_forward.py             [M] +cal_cat_temp/iso, +cat_dc_temp/iso pooled
apps/api/src/nutmeg/v4/cli/cat_calibration_ablation.py  [+] multi-cutoff ablation CLI
pyproject.toml                                          [M] +script entry
tests/v4/test_walk_forward_cat_calibration.py           [+] new tests
docs/v9_w6_calibration_ablation.md                      [+] ablation card
docs/v9_w6_calibration_negative.md                      [+] this writeup
docs/V9_ROADMAP.md                                      [M] W6 marked ✅ (negative)
```

## Next

V9 ship: `V9_HANDOFF.md` + `v9_retrospective.md` + `v9.0-shipped`
tag. The V9 retrospective should explicitly note this as the
project's 6th honest negative writeup and the close of the
ECE-vs-log-loss backlog.
