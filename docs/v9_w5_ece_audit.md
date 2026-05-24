# ECE-vs-log-loss audit — cutoff=2024-08-01 (n=4331) test set

Two-model decomposition of where the pooled log-loss gap concentrates.

**Pooled** (n = 4,331)

| Model | log-loss |
|---|---:|
| Pinnacle (ceiling) | 0.9904 |
| CatBoost | 0.9960 |
| **Gap** | **+0.0056** |

## Per-bucket breakdown (binned on p(true_class))

| Bin | n_Pinnacle | n_CatBoost | avg p_Pinnacle | avg p_CatBoost | weighted-ll Pinnacle | weighted-ll CatBoost | Δ (CatBoost − Pinnacle) |
|---|---:|---:|---:|---:|---:|---:|---:|
| [0.0, 0.2] | 270 | 251 | 0.161 | 0.161 | 0.1153 | 0.1070 | -0.0083 |
| (0.2, 0.4] | 2165 | 2164 | 0.296 | 0.292 | 0.6152 | 0.6209 | +0.0057 |
| (0.4, 0.6] | 1262 | 1262 | 0.492 | 0.488 | 0.2088 | 0.2109 | +0.0021 |
| (0.6, 0.8] | 542 | 619 | 0.687 | 0.680 | 0.0473 | 0.0556 | +0.0082 |
| (0.8, 1.0] | 92 | 35 | 0.839 | 0.817 | 0.0037 | 0.0016 | -0.0021 |
| **Sum** | — | — | — | — | **0.9904** | **0.9960** | **+0.0056** |

## Verdict

🎯 **Concentrated bucket found**: bucket `(0.6, 0.8]` contributes **+0.0082** to the gap (147% of the total +0.0056).

→ V9 W6 candidate fix: calibration tweak on `p(true_class) ∈ (0.6, 0.8]`. Likely a per-bucket isotonic or temperature adjustment.
