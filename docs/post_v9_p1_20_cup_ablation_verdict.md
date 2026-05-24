# V8 W3 — cup-data ablation

_Generated 2026-05-24 14:36 UTC_  _Cups: UCL, UEL_  _Seasons: [2021, 2022, 2023, 2024]_


| cutoff | mode | n_test | log_loss | Δ vs baseline | hit-rate |
|---|---|---:|---:|---:|---:|
| 2024-01-15 | baseline | 4,950 | 1.0017 | +0.0000 | 0.5014 |
| 2024-01-15 | cup_data | 4,958 | 0.9992 | -0.0025 | 0.5071 |
| 2024-01-15 | cup_features | 4,950 | 1.0017 | +0.0000 | 0.5014 |
| 2024-01-15 | cup_full | 4,958 | 0.9992 | -0.0025 | 0.5071 |

| 2024-05-01 | baseline | 4,709 | 0.9963 | +0.0000 | 0.5109 |
| 2024-05-01 | cup_data | 4,717 | 0.9969 | +0.0005 | 0.5143 |
| 2024-05-01 | cup_features | 4,709 | 0.9963 | +0.0000 | 0.5109 |
| 2024-05-01 | cup_full | 4,717 | 0.9969 | +0.0005 | 0.5143 |

| 2024-08-01 | baseline | 4,331 | 0.9971 | +0.0000 | 0.5077 |
| 2024-08-01 | cup_data | 4,339 | 0.9985 | +0.0014 | 0.5091 |
| 2024-08-01 | cup_features | 4,331 | 0.9971 | +0.0000 | 0.5077 |
| 2024-08-01 | cup_full | 4,339 | 0.9985 | +0.0014 | 0.5091 |

| 2024-12-01 | baseline | 2,729 | 1.0029 | +0.0000 | 0.5060 |
| 2024-12-01 | cup_data | 2,729 | 1.0014 | -0.0015 | 0.5112 |
| 2024-12-01 | cup_features | 2,729 | 1.0029 | +0.0000 | 0.5060 |
| 2024-12-01 | cup_full | 2,729 | 1.0014 | -0.0015 | 0.5112 |

## Ship gate
Per V6 W6 methodology: cup-aware artifact ships in V8 W4 only when **≥ 3/4 folds** show `cup_full` improving over `baseline` by ≥ −0.001 log-loss.

❌ Gate NOT passed (2/4 folds improved ≥ −0.001 log-loss).
→ Do NOT ship cup-aware artifact. Document negative result in V8 W4.