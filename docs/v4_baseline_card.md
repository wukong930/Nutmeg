# V4 Baseline Card

_Generated 2026-05-22 06:47 UTC_

## Configuration

- Train window:     **540** days before cutoff
- Validation window: **90** days (temperature calibration fit)
- Test cutoff:      **2024-08-01**
- Test horizon:     **400** days after cutoff
- GBM rho:          **-0.1** (DC tau correction)
- Calibration T:    MLE=1.030  GBM=0.857

## Pooled metrics across all leagues

**Full-coverage test pool (PSC available): 4,792 matches**
**GBM-eligible pool (no missing features): 4,331 matches**

| Model                            | log-loss | Brier  | hit-rate | ECE    | Δ log-loss vs Pinnacle |
|----------------------------------|---------:|-------:|---------:|-------:|-----------------------:|
| Pinnacle closing (baseline)      | 0.9942 | 0.5941 | 0.5071 | 0.0114 | +0.0000 |
|   Pinnacle (GBM-eligible)        | 0.9904 | 0.5916 | 0.5124 | 0.0123 | -0.0039 |
| **V4 GBM-λ + DC + Temp**         | 0.9987 | 0.5971 | 0.5084 | 0.0210 | +0.0045 |
| V4 GBM-λ + DC (raw)              | 0.9982 | 0.5966 | 0.5084 | 0.0171 | +0.0039 |
| V4 MLE DC + Temp                 | 1.0377 | 0.6239 | 0.4679 | 0.0232 | +0.0435 |
| V4 MLE DC (raw)                  | 1.0384 | 0.6244 | 0.4679 | 0.0276 | +0.0442 |
| Uniform 1/3                      | 1.0986 | 0.6667 | 0.4343 | 0.1009 | +0.1044 |

**Best model captures 92.3% of available signal** (uniform→Pinnacle gap = 0.1083; best closes 0.0999).

## Per-league breakdown

| League | test_n | Pinnacle | MLE DC | MLE+Temp | GBM-λ+DC | GBM+Temp | GBM Δ |
|--------|-------:|---------:|-------:|---------:|---------:|---------:|------:|
| EPL                      |   380 | 0.9664 | 1.0092 | 1.0081 | 0.9810 | 0.9858 | +0.0193 |
| ESP_LA_LIGA              |   380 | 0.9463 | 0.9900 | 0.9901 | 0.9481 | 0.9426 | -0.0037 |
| ITA_SERIE_A              |   380 | 0.9513 | 0.9815 | 0.9822 | 0.9710 | 0.9705 | +0.0191 |
| GER_BUNDESLIGA           |   306 | 0.9882 | 1.0427 | 1.0407 | 1.0011 | 1.0061 | +0.0180 |
| FRA_LIGUE_1              |   306 | 0.9550 | 1.0038 | 1.0041 | 0.9624 | 0.9624 | +0.0074 |
| ENG_CHAMPIONSHIP         |   552 | 1.0274 | 1.0395 | 1.0393 | 1.0309 | 1.0316 | +0.0042 |
| ESP_SEGUNDA_DIVISION     |   462 | 1.0126 | 1.0541 | 1.0540 | 1.0221 | 1.0191 | +0.0065 |
| ITA_SERIE_B              |   380 | 1.0494 | 1.1233 | 1.1216 | 1.0558 | 1.0559 | +0.0065 |
| GER_2_BUNDESLIGA         |   306 | 1.0604 | 1.0932 | 1.0914 | 1.0745 | 1.0840 | +0.0236 |
| FRA_LIGUE_2              |   306 | 1.0147 | 1.0741 | 1.0735 | 1.0234 | 1.0222 | +0.0076 |
| NED_EREDIVISIE           |   306 | 0.9376 | 1.0148 | 1.0116 | 0.9497 | 0.9527 | +0.0152 |
| PRT_PRIMEIRA_LIGA        |   306 | 0.9239 | 0.9942 | 0.9931 | 0.9289 | 0.9251 | +0.0012 |
| JPN_J1                   |   422 | 1.0497 | 1.0706 | 1.0698 | — | — | — |

## Interpretation

- **Pinnacle** = market closing line; ceiling for any model not using day-of info (lineups, late injuries).
- **GBM-λ + DC** uses market closing odds as features, so it naturally tracks the market. It should NOT be expected to dramatically beat Pinnacle pooled — that would imply Pinnacle is materially inefficient.
- The **practical alpha** for the user is: same probabilistic quality as Pinnacle, but with internal score-grid that enables 让球 / 大小球 / 比分 / 串关 computation that the market line alone can't.
- Per-league regressions point to where extra features (xG, lineups, schedule congestion) would add value next.
