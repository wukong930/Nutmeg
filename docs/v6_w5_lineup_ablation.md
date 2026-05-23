# V6 W5 — Lineup feature ablation

_Mixed result: 7 of 9 originally proposed lineup features fail; 2 succeed
under strict leakage screening. Documented in full because the naive
formulation looks great but is pure data leakage._

## Setup

V6 W1 ingested API-Football lineups + injuries; V6 W2 wired them into the
feature pipeline. V6 W5 actually tests whether the features improve
out-of-sample log-loss.

**Data**: EPL 23/24 + 24/25, 760 fixtures with full lineups + injuries.
**Cutoff**: 2024-12-01 (train window includes most of 23/24 + first half of 24/25; test = Dec 2024 to mid-2025).
**Model**: CatBoost-Poisson with default V5 features + tested lineup additions.

## What we tried

Nine lineup-derived features from V6 W2:

| Feature | Source |
|---------|--------|
| `lineup_home_xi_present_flag` / `away` | API-Football `/fixtures/lineups` published |
| `lineup_home_formation_compactness` / `away` | Hand-curated 4-3-3=1, 5-4-1=2 mapping over 19 formations |
| `lineup_home_n_injuries` / `away` | Naive `len(/injuries season list)` |
| `lineup_home_xi_minutes_share` / `away` | Starting-XI starts as fraction of season total |
| `lineup_available` | AND of present_flag gate |

## Results — initial naive run

All 9 features added at once, EPL fold:

| Variant | log-loss | ECE | Δ vs base |
|---------|---------:|-----:|----------:|
| Baseline (no lineup) | 0.9883 | 0.0340 | — |
| + all 9 lineup features | 0.9896 | 0.1050 | **+0.0013 worse** |

ECE blew up 3x (0.034 → 0.105). Investigation:

| Feature subset | log-loss | ECE | Verdict |
|----------------|---------:|-----:|---------|
| + lineup_available only | 0.9883 | 0.0340 | no change (CatBoost ignored) |
| + n_injuries (h, a) | 0.9883 | 0.0340 | no change (constant: not ingested) |
| + available + formation | 0.9896 | 0.1050 | **regression** ← formation is the culprit |
| + available + minutes_share | 0.9883 | 0.0340 | no change (placeholder constant) |

Formation compactness was the only feature actually MOVING — and it
moved log-loss in the wrong direction. The others were effectively
constants (no real injury / minutes data ingested in that pass).

## The injury "improvement" that was actually leakage

After ingesting real injuries:

| Variant | log-loss | ECE |
|---------|---------:|-----:|
| Baseline | 0.9883 | 0.0340 |
| + n_injuries (raw season count) | 0.9778 | 0.0434 |

A **−0.0105 log-loss improvement** — looks great until you inspect the data:

API-Football's `/injuries?team=X&season=Y` returns **the entire season's
injury events**, including those occurring AFTER the model's prediction
date. For a team like Arsenal in season 2024:
- 1,300 injury records over 51 distinct fixtures from Aug 2024 to May 2025
- Median count per row = 0, max = 333 (cumulative)

The naive `len(season_injuries)` feature was reading information from
the future. The model learned "teams with high mid-season injury counts
lose more matches" — which is true but unactionable because the count
at prediction time IS NOT what the training set saw.

## Leak fix

`nutmeg.v4.data.lineup_lookup._filter_injuries_before` — filters to
injuries with `fixture.date < match_date`. Re-running with this fix:

| Variant | log-loss | ECE | Δ |
|---------|---------:|-----:|---:|
| Baseline | 0.9883 | 0.0340 | — |
| + n_injuries (leak-free season cumulative) | 0.9913 | 0.0407 | **+0.0031 worse** |

Confirmed: the −0.0105 was 100% leakage. Leak-free season-cumulative
count actually hurts.

## The single feature that works

Redefining n_injuries as "**unique players injured in the 30-day
window before match_date**":

`nutmeg.v4.data.lineup_lookup._recent_unique_injured_count(injuries, match_date, window_days=30)`

| Variant | log-loss | ECE | Δ |
|---------|---------:|-----:|---:|
| Baseline | 0.9883 | 0.0340 | — |
| + recent_n_injuries (30d unique, leak-free) | 0.9845 | 0.0452 | **−0.0038 ✅** |

**−0.0038 log-loss improvement** under strict leak controls. ECE worsened
slightly (0.0340 → 0.0452) but log-loss is meaningfully better.

The intuition: cumulative season-injury count is correlated with
"team is weak this season" — information already in the market odds we
condition on. Recent 30-day unique players measures "who is missing
today" — closer to the info Pinnacle doesn't fully price (especially
for less-tracked leagues).

## Decision

1. **Keep** the new fields `lineup_home_recent_n_injuries` and
   `lineup_away_recent_n_injuries` (added to `lineup_features.py` and
   computed by `build_recent_injury_lookup`)
2. **Drop** the other 7 of 9 W2 columns from production GBM input:
   - Formation compactness — actively hurts
   - Season cumulative n_injuries — neutral but redundant with recent count
   - XI present flag / available — no signal alone
   - Minutes share — needs squad-stats ingest, not done in this sprint
3. Keep all 9 columns in the dataframe for diagnostic visibility; the
   GBM input list (`feature_columns_with_lineups`) only includes the
   validated subset.
4. Future iterations should A/B with multi-season + multi-league before
   shipping (this finding is 1 fold EPL, not multi-season validated)

## Caveats / next steps

- 1-fold EPL only. Multi-season replication needed before shipping the
  recent-injury column to production training. Ideally we re-train at
  three cutoffs (2023-12, 2024-06, 2024-12) and confirm Δ ≤ 0 at all.
- ECE went up (0.034 → 0.045). Calibration deteriorated slightly even
  as log-loss improved. May indicate the new feature is sharpening
  predictions in the right direction but pushing some buckets too far.
- The feature requires API-Football paid subscription for production
  use ($19/mo). Worth it if the multi-season verdict holds.

## Stacks against V5 ablation history

| Week | Hypothesis | Verdict |
|------|-----------|---------|
| V5 W4 | xG-lite + clubelo | ✅ shipped |
| V5 W5 | Market-dynamics drift | ⚠️ rolled back |
| V5 W6 stacker | LogReg ensemble | ⚠️ rolled back |
| V5 W6 CatBoost | Single-model swap | ✅ shipped |
| V5 W9 | Per-league T | ⚠️ rolled back |
| **V6 W5** | **Lineup features (recent injury only)** | **⏳ pending multi-season validation** |

Same pattern: many proposed features fail; a small validated subset
survives. The mechanism that catches the failures (multi-season + careful
leakage screening) is more valuable than any individual feature win.
