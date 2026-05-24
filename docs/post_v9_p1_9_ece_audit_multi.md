# Multi-cutoff ECE-vs-log-loss audit — 3 cutoffs

Per-bucket decomposition of the CatBoost vs Pinnacle pooled log-loss gap, repeated across 3 cutoffs so non-stationary patterns are visible. Verdict flags a bucket only if it dominates on ≥ 2/3 cutoffs (closes V9 retrospective W5 self-criticism).

## Pooled log-loss per cutoff

| Cutoff | n | Pinnacle | CatBoost | Δ (CatBoost − Pinnacle) |
|---|---:|---:|---:|---:|
| 2022-08-01 | 4,884 | 0.9940 | 0.9984 | +0.0044 |
| 2023-08-01 | 4,767 | 0.9865 | 0.9898 | +0.0033 |
| 2024-08-01 | 4,331 | 0.9904 | 0.9960 | +0.0056 |

## Per-cutoff dominant bucket (largest weighted-ll Δ)

| Cutoff | Dominant bin | Δ contribution |
|---|---|---:|
| 2022-08-01 | `(0.2, 0.4]` | +0.0287 |
| 2023-08-01 | `(0.2, 0.4]` | +0.0085 |
| 2024-08-01 | `(0.6, 0.8]` | +0.0082 |

## Cross-cutoff stability

- Most-frequent dominant bin: `(0.2, 0.4]` (2/3 cutoffs)
- Mean Δ in that bin (only the cutoffs where it dominated): `+0.0186`
- Threshold for 'stable': ≥ 2/3 cutoffs AND mean Δ > 0.001

## Verdict

🎯 **Stable concentrated bucket**: `(0.2, 0.4]` dominates 2/3 cutoffs with mean Δ `+0.0186`. This is a credible calibration target — a per-bucket isotonic / temperature on `(0.2, 0.4]` would address the same locus across multiple seasons. Worth a V9 W6-style ablation attempt (with multi-cutoff verification of the FIX too, not just the audit).
