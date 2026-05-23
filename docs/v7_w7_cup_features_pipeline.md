# V7 W7 — Cup features wired into the training pipeline

_W6 dropped per-(league, season) cup-history parquets onto disk. W7
wires them through `build_feature_frame` so the 5 V6 W11 cup
side-channel columns can be requested by `nutmeg-train`. **Plumbing
only — no model retraining yet.** Training on cup data also requires
backfilled odds, which is V7 W8 territory; W7's job is making the
pipeline ready for it._

## What W7 ships

### 1. `feature_columns_with_cup()` helper

```python
from nutmeg.v4.features.pipeline import feature_columns_with_cup

cols_a = feature_columns_with_cup(include_lineups=False)
# GBM_FEATURE_COLUMNS (39) + CUP_FEATURE_COLUMNS (5) = 44 cols

cols_b = feature_columns_with_cup(include_lineups=True)
# 39 + LINEUP_VALIDATED_COLUMNS (2) + 5 = 46 cols
```

The `include_lineups` flag is **explicit by design**. Conflating cup +
lineup wiring would `KeyError` when `--with-cup-features` is used
without the lineup cache populated. The two flags compose
independently in `nutmeg-train`.

### 2. `build_feature_frame(cup_history_df=...)` new arg

```python
from nutmeg.v4.features.pipeline import build_feature_frame
from nutmeg.v4.data.cup_history import load_multi_season_cup_history

cup_df = load_multi_season_cup_history(
    Path("data/external/cup_history"),
    leagues=["UCL", "UEL"],
    seasons=[2021, 2022, 2023, 2024],
)
feats = build_feature_frame(
    training_df,
    cup_history_df=cup_df,
)
# feats has the original cols + market/elo/form/xg-lite/clubelo +
# 5 cup cols: is_cup_match / is_knockout / is_two_legged /
# is_national_team_match / competition_type_id
```

Pipeline:
1. The new `_merge_cup_round_labels` helper left-joins cup-history's
   `round_label` onto the training frame by
   `(date, league, home_team, away_team)`
2. `build_cup_features(out, league_col="league", round_col="round_label")`
   derives the 5 columns from the joined data
3. Domestic-league rows that don't match any cup-history record emit 0
   for every cup column
4. Cup-league rows (`league` ∈ `CUP_COMPETITIONS`) that match cup-history
   pick up `is_cup_match=1` + structural flags from the registry +
   `is_knockout` from the round label

### 3. `nutmeg-train --with-cup-features` flag

```bash
# Train with cup wiring (loads V7 W6 parquets from --cup-history-dir)
nutmeg-train --model cat --cutoff 2024-08-01 \
    --with-cup-features \
    --cup-leagues UCL,UEL \
    --cup-seasons 2021,2022,2023,2024 \
    --out data/v4_model_cat_cup

# Combine with --with-lineups for both feature families
nutmeg-train --model cat --cutoff 2024-08-01 \
    --with-lineups \
    --with-cup-features \
    --out data/v4_model_cat_full
```

Flag table:

| Combination | Feature cols | Training-time data needs |
|---|---:|---|
| (neither) | 39 (V5 W12 baseline) | football-data.co.uk CSVs (in repo) |
| `--with-lineups` | 41 | + API-Football lineup cache (V6 W5 ingest) |
| `--with-cup-features` | 44 | + cup-history parquets (V7 W6 ingest) |
| both | 46 | both caches above |

Default behavior unchanged: zero flag passed → V5 W12 default.

## Why W7 ships the wiring without retraining

The cup-history parquets contain `(date, league, home, away, goals,
round_label)` — no odds, no Elo rating, no form. To meaningfully
TRAIN on cup data we need:

1. **Cup match closing odds** (`psc_home/draw/away`): not in the W6
   parquets; not in football-data.co.uk (which is league-only). Have
   to backfill via API-Football's `/odds` endpoint per cup fixture.
2. **Cup match team_state** (Elo / form / recent-goals): the V4
   pipeline computes these only for fixtures in the canonical
   training set. UCL Real Madrid vs Bayern would need team_state
   pulled from their domestic leagues via V6 W11's
   `lookup_cup_team_pair` cross-league walk.
3. **Team-name reconciliation**: API-Football uses "Real Madrid";
   football-data.co.uk uses "Real Madrid" — but some teams differ
   ("Man United" vs "Manchester United"). The team_canonical map
   needs cup-team coverage.

Each of (1), (2), (3) is a meaningful piece of work. W7 ships the
**downstream** so once those upstream pieces land, training is a flag
flip. V7 W8 + future iterations will close them.

In the meantime, training with `--with-cup-features` on the current
training set:
- Adds 5 columns to the GBM input
- Every column is 0 on every training row (since training data is
  domestic-league only and cup rows aren't merged into it yet)
- Therefore the GBM ignores them — no signal, no harm
- The flag is a no-op on log-loss, but the artifact metadata records
  `with_cup_features=True` so callers can verify the pipeline is wired

## Multi-fold ablation: deferred

V6 W6 caught a major data leak via 4-cutoff × 2-league ablation
(`recent_n_injuries` survived; 8 other lineup cols failed). The same
methodology will apply to cup features once cup rows are actually in
the training set:

| Fold | Cutoff | Train pool | Notes |
|---|---|---|---|
| 1 | 2024-01-15 | EPL + UCL | first-half-season cup data |
| 2 | 2024-01-15 | ESP_LA_LIGA + UCL | cross-league sanity |
| 3 | 2024-08-01 | EPL + UCL | second-half-season |
| 4 | 2024-08-01 | All clubs + UCL | maximum data |

Ship gate: 3-of-4 folds improve by ≥ −0.001 log-loss. Same bar V6 W6
applied; same anti-overfit insurance V5 W5/W6/W9 wished they'd had.

W7 doesn't run this ablation because the training rows aren't there
yet. V7 W8 either:
- Backfills cup odds (+ team-name reconciliation) and runs the
  ablation, OR
- Stops at W7 plumbing and pushes V7's "cup-trained model" deliverable
  to V8

## What W7 deliberately doesn't do

- **No cup odds backfill.** `nutmeg-ingest-cup-history` writes
  fixtures + scores only. Cup `/odds` would be another CLI
  (`nutmeg-ingest-cup-odds`?) — V7 W8 if scope allows.
- **No cup row integration into training frame.** The current
  `nutmeg-train` reads from `data/historical_sources/football_data_co_uk/`.
  Augmenting the frame with cup-history rows requires the missing
  upstream pieces above.
- **No team-name canonicalization for cup teams.** V5 W3's
  `team_canonical` is league-scoped; cup-team mapping is its own
  layer.
- **No retrained artifact ship.** `data/v4_model_cat_cup/` would
  ship in V7 W8 if the ablation closes. W7 just makes
  `nutmeg-train --with-cup-features` runnable.

## Tests

`tests/v4/test_cup_features_pipeline.py` — 17 tests:

| Group | Coverage |
|---|---|
| `TestFeatureColumnsWithCup` (4) | `include_lineups` flag semantics; base cols always present; count arithmetic |
| `TestMergeCupRoundLabels` (6) | Left-join preserves all rows; matched row picks up round; unmatched row → NaN round_label; empty/None cup history; ISO-string vs datetime date join |
| `TestBuildFeatureFrameCupHistory` (5) | Default flow (no cup cols); with cup history all 5 added; league rows = 0; UCL R16 row picks up knockout/two-legged/club_cup flags; empty cup history still emits cup cols via league-registry path |
| `TestTrainArgParsing` (2) | `--with-cup-features` accepted alone + combined with `--with-lineups` (argparse only — full training covered by test_e2e) |

Full V4 suite: **576/576 passing** (559 prior + 17 new W7).

## Files touched in W7

```
apps/api/src/nutmeg/v4/features/pipeline.py    [M] +feature_columns_with_cup
                                                   +cup_history_df arg
                                                   +_merge_cup_round_labels
apps/api/src/nutmeg/v4/cli/train.py            [M] +--with-cup-features
                                                   +--cup-* args
                                                   +flag-combination logic
tests/v4/test_cup_features_pipeline.py         [+] 17 tests
docs/V7_ROADMAP.md                             [M] W7 ✅
docs/v7_w7_cup_features_pipeline.md            [+] (this file)
```

## Next: V7 W8 — decision point

Two paths for V7 W8:

**Option A — push for cup-data training**: ship `nutmeg-ingest-cup-odds`,
the team_canonical cup extension, and the multi-fold ablation. Either
ship `data/v4_model_cat_cup/` artifact (if ≥3/4 folds improve) or
document the negative result. 1-2 weeks of work.

**Option B — pause Track B at plumbing, pivot to Track A**: the
4-week observation cron (V7 W1+W2+W3) is accumulating data; V7 W5's
lineup-aware ROI verdict gets first crack at deciding whether the
V6 W6 backtest improvement is real. Cup training waits until V8.

Pick at end of W7 based on how Track A data is shaping up.
