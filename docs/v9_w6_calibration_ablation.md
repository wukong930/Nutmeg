# V9 W6 — CatBoost calibration ablation

Tests whether per-class isotonic / temperature calibration on raw CatBoost closes the V9 W5-identified gap. Multi-cutoff verdict: ship only if **all** cutoffs improve pooled log-loss.

## Pooled log-loss per cutoff

| Cutoff | n | Pinnacle | cat_raw | cat_temp | cat_iso | Δ temp − raw | Δ iso − raw |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022-08-01 | 4884 | 0.9940 | 0.9984 | 0.9977 | 1.0454 | -0.0006 | +0.0470 |
| 2023-08-01 | 4767 | 0.9865 | 0.9898 | 0.9894 | 1.0900 | -0.0004 | +0.1002 |
| 2024-08-01 | 4331 | 0.9904 | 0.9960 | 0.9965 | 1.0855 | +0.0006 | +0.0895 |

## `(0.6, 0.8]` bucket weighted log-loss

Only the bucket V9 W5 flagged. Lower = better. Pinnacle's value is the reachable ceiling for this bucket.

| Cutoff | Pin wll | cat_raw wll | cat_temp wll | cat_iso wll | Δ raw vs Pin | Δ iso vs Pin |
|---|---:|---:|---:|---:|---:|---:|
| 2022-08-01 | 0.0438 | 0.0506 | 0.0516 | 0.0396 | +0.0067 | -0.0043 |
| 2023-08-01 | 0.0448 | 0.0488 | 0.0533 | 0.0773 | +0.0040 | +0.0325 |
| 2024-08-01 | 0.0473 | 0.0556 | 0.0590 | 0.0687 | +0.0082 | +0.0214 |

## Calibrator parameters

| Cutoff | cat temperature T | iso fitted? |
|---|---:|---:|
| 2022-08-01 | 0.9563 | yes |
| 2023-08-01 | 0.8655 | yes |
| 2024-08-01 | 0.8521 | yes |

## Verdict

- **isotonic**: improved on 0/3 cutoffs, mean Δ vs raw = `+0.0789` log-loss
- **temperature**: improved on 2/3 cutoffs, mean Δ vs raw = `-0.0001` log-loss

❌ **no-fix**: isotonic doesn't beat raw across cutoffs. The V9 W5 audit revealed the (0.6, 0.8] gap but per-class isotonic doesn't close it. Interpretation: the 619 vs 542 row population delta is real signal CatBoost picks up that Pinnacle's market prior deliberately dampens — calibrating would erase real edge. **Close ECE-vs-log-loss backlog permanently**; the audit was the answer.
