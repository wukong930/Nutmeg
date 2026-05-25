# V8 W3 — cup-data ablation

_Generated 2026-05-25 18:13 UTC_  _Cups: UCL, UEL_  _Seasons: [2021, 2022, 2023]_


| cutoff | mode | n_test | log_loss | Δ vs baseline | hit-rate |
|---|---|---:|---:|---:|---:|
| 2024-04-01 | baseline | 4,968 | 1.0008 | +0.0000 | 0.5064 |
| 2024-04-01 | cup_data | 4,976 | 1.0008 | -0.0000 | 0.5020 |
| 2024-04-01 | cup_features | 4,968 | 1.0008 | +0.0000 | 0.5064 |
| 2024-04-01 | cup_full | 4,976 | 1.0008 | -0.0000 | 0.5020 |

| 2024-07-01 | baseline | 4,331 | 0.9987 | +0.0000 | 0.5073 |
| 2024-07-01 | cup_data | 4,339 | 0.9975 | -0.0011 | 0.5098 |
| 2024-07-01 | cup_features | 4,331 | 0.9987 | +0.0000 | 0.5073 |
| 2024-07-01 | cup_full | 4,339 | 0.9975 | -0.0011 | 0.5098 |

## Ship gate
Per V6 W6 methodology: cup-aware artifact ships in V8 W4 only when **≥ 3/4 folds** show `cup_full` improving over `baseline` by ≥ −0.001 log-loss.

❌ Gate NOT passed (1/2 folds improved ≥ −0.001 log-loss).
→ Do NOT ship cup-aware artifact. Document negative result in V8 W4.