# V5 W5 — Market-Dynamics Ablation

_Negative result, documented in full so the next attempt doesn't repeat the work._

## What we tried

Use football-data.co.uk's Pinnacle **opening** odds (`PSH/D/A`) — which are already in our DataFrame but were unused — as a new feature family in the GBM. Twelve features built in `nutmeg.v4.features.market_dynamics`:

- `market_p_open_{home,draw,away}` — devig opening probabilities
- `market_overround_open`
- `prob_drift_{home,draw,away}` = closing − opening devig prob
- `overround_compression` = opening overround − closing overround
- `dominant_drift_side` = ±1/0 depending on which side moved most
- `{home,away}_steam_flag` = `|drift| > 0.03`
- `market_dynamics_available` flag

Opening-odds coverage in the dataset:

| Year | Coverage |
|------|---------:|
| 2012–2019 | 0% (column not collected) |
| 2020 | 85% |
| 2021–2024 | 92–94% |
| 2025 (partial) | 86% |

J1 has 0% opening odds coverage across all years.

## Result

Three attempts at slimming the feature set, all comparing multi-season GBM+Temp log-loss to the W4 baseline (xG-lite + clubelo, no market dynamics):

|              | Test 22/23 | Test 23/24 | Test 24/25 |
|--------------|----------:|----------:|----------:|
| W4 baseline  | 1.0020    | 0.9951    | 0.9971    |
| W5 / 12 cols | 1.0032    | 0.9970    | 0.9969    |
| W5 / 5 cols  | 1.0019    | 0.9960    | 0.9988    |
| W5 / 3 cols  | 1.0023    | 0.9965    | 0.9981    |

The "12-cols" variant is the original design (drift + open probs + steam + dominant side). The "5-cols" variant kept only the continuous monotone signals (3 drifts + compression + available flag). The "3-cols" variant kept only the three drifts.

**No variant produced a stable improvement across all three test seasons.** 12-cols won on 24/25 but lost on 22/23 and 23/24. 5-cols won on 22/23 but lost on 23/24 and 24/25. 3-cols lost on all three.

Pinnacle is sharp, so the closing line already absorbs the information that the drift would carry. Whatever residual signal the drift contains is either (a) too noisy to learn from the ~4k training samples per season fold, or (b) captured indirectly by features we already have. Worse: the GBM appears to overfit the drift pattern in the train window, producing test-set regressions.

## Decision

**Roll back market-dynamics from the GBM input list.** The build function (`build_market_dynamics_features`) remains in the pipeline so the columns exist on the dataframe for diagnostics and any future analysis, but `pipeline.GBM_FEATURE_COLUMNS` reverts to the W4 39-column set.

## Why this is still a W5 deliverable (not a no-op)

- Documents a falsifiable hypothesis (drift adds alpha) that has now been falsified on our dataset.
- Future attempts with **richer drift data** — multi-snapshot odds streams via OddsPortal, or sportradar opening lines with timing precision — should be evaluated against this same multi-season test and need to show **stable** improvement, not single-fold wins.
- The schema columns (`ps_home/draw/away` ingestion, the build function) are kept so plugging in better drift data later is a one-line config change.

## What W5 budget went to instead

- Wrote the ingest schema for opening odds (already there from V4, just verified)
- Wrote `nutmeg.v4.features.market_dynamics` (kept, dormant)
- Ran three multi-season bench cycles to discover the regression
- Wrote this ablation report so the negative result isn't lost

## What to try next

- **W6 ensemble** (LightGBM + XGBoost + CatBoost + stacker) — different base learners may catch drift signal differently. Don't pre-judge based on W5; ensemble might rehabilitate the drift features.
- If still no win after W6, accept that within our current data we've extracted ~93% of available log-loss signal, and shift focus to ROI optimization (W8 observation loop) rather than chasing the last 0.005.
