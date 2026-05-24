# V8 W2 — Cup row UNION into the training frame

_Second piece of V8's Track B closeout. V7 W6 dropped cup fixtures
+ scores. V7 W8 dropped cup odds. V8 W1 shipped the global team-name
canonicalizer. **V8 W2 stitches them together**: cup history × cup
odds → canonicalize team names → pad V4 schema cols → UNION into the
training frame via `nutmeg-train --with-cup-data`. V8 W3 runs the
multi-fold ablation on this expanded training set._

## What W2 ships

### 1. `nutmeg.v4.data.cup_training` module

```python
from nutmeg.v4.data.cup_training import (
    build_cup_training_rows,
    union_league_and_cup,
)

cup_rows = build_cup_training_rows(
    Path("data/external/cup_history"),
    Path("data/external/cup_odds"),
    leagues=["UCL", "UEL"],
    seasons=[2021, 2022, 2023, 2024],
    league_team_df=df,        # used to build the global canonical pool
    fuzzy_threshold=0.86,
)
combined = union_league_and_cup(df, cup_rows)
# combined has MATCH_COLUMNS schema, sorted by (date, league, home_team)
```

Pipeline inside `build_cup_training_rows`:
1. `load_multi_season_cup_history` (V7 W6) → fixtures DataFrame
2. `load_multi_season_cup_odds` (V7 W8) → odds DataFrame
3. `merge_cup_fixtures_and_odds(how="inner")` (V7 W8 helper) drops
   fixtures without odds
4. Build global canonical pool from `league_team_df`
5. For each row: `to_v4_canonical_global(home_team)` +
   `to_v4_canonical_global(away_team)`; drop rows where either
   side fails to resolve (log the drop counts by reason)
6. Pad the 23-of-37 V4 schema cols cup data doesn't carry:
   - **Half-time goals** (`ht_home_goals`, `ht_away_goals`) → NaN
   - **Shot stats** (`home_shots`, `home_shots_on_target`,
     `home_corners`, `home_yellow`, `home_red` + away mirrors) → NaN
   - **Alt-book odds** (`ps_*`, `b365c_*`, `avgc_*`) → copy from
     `psc_*` (Pinnacle is the sharp; same fallback V7 W1 uses)
   - **Asian handicap** (`ahch`, `pcahh`, `pcaha`) → NaN
   - **O/U 2.5** (`psc_over25`, `psc_under25`) → from cup_odds when
     present, else NaN
7. Compute `result_1x2` from goals (deterministic)
8. Return DataFrame with exactly `MATCH_COLUMNS` schema

### 2. `nutmeg-train --with-cup-data` flag

```bash
# Train with cup-data UNIONed (rows) but no cup-feature columns
nutmeg-train --model cat --cutoff 2024-08-01 \
    --with-cup-data \
    --cup-leagues UCL,UEL \
    --cup-seasons 2021,2022,2023,2024 \
    --out data/v4_model_cat_cupdata

# Combine with --with-cup-features (W7) and --with-lineups (W6)
nutmeg-train --model cat --cutoff 2024-08-01 \
    --with-cup-data \
    --with-cup-features \
    --with-lineups \
    --out data/v4_model_cat_full
```

**`--with-cup-data` (V8 W2) and `--with-cup-features` (V7 W7) are
independent**:
- `--with-cup-data` adds **rows** (cup fixtures get UNION'd into the
  training frame)
- `--with-cup-features` adds **columns** (5 V6 W11 side-channel
  cup feature cols)
- Pass both for the full cup-trained run; either alone is a partial step

| `--with-cup-data` | `--with-cup-features` | Training rows | GBM input cols |
|:---:|:---:|---|---|
| ✗ | ✗ | league only (~50k) | 39 (V5 baseline) |
| ✗ | ✓ | league only (~50k) | 44 (+5 cup cols, all zero on league rows) |
| ✓ | ✗ | + cup rows (~52k) | 39 (cup rows still get is_cup_match info via... nothing — feature cols missing) |
| ✓ | ✓ | + cup rows | 44 (cup rows DO have is_cup_match=1) |

The "✓ data + ✗ features" combination trains correctly but loses the
cup-vs-league discriminator → mostly equivalent to "just give the GBM
more rows". Recommended runs: both off (baseline) and both on
(cup-aware artifact).

### 3. Drop diagnostics

When a cup row's team names can't resolve, `build_cup_training_rows`
logs a warning:

```
cup_training: dropped rows due to unresolved names: {'home_unresolved': 12,
'away_unresolved': 8, 'both_unresolved': 3}
(extend CUP_TEAM_ALIASES via nutmeg-canonical-report-cup)
```

The fix flow is identical to V8 W1's:
1. Run `nutmeg-canonical-report-cup --show unmatched`
2. Add aliases to `CUP_TEAM_ALIASES` in `utils.team_canonical.py`
3. Re-run train with `--with-cup-data` → drop count goes down

## What W2 doesn't do

- **No actual cup training run.** W2 ships the data pipeline; running
  the train command on real cup parquets requires the user to first
  run `nutmeg-ingest-cup-history` + `-cup-odds` (V7 W6 + W8) for the
  desired seasons. Both are local actions.
- **No multi-fold ablation.** That's V8 W3 — same methodology as
  V6 W6's `recent_n_injuries` verdict. 4 cutoffs × multiple league
  pools.
- **No artifact ship.** V8 W4 — conditional on W3's ablation passing
  the ship gate (≥ 3/4 folds improve by ≥ −0.001 log-loss).
- **No team_state cross-league lookup for cup teams' Elo.** A UCL row
  for "Real Madrid vs Bayern Munich" computes Elo via V4's existing
  per-league walker, which expects "Real Madrid" to be in
  `team_state["UCL"]` — it's not, it's in `team_state["ESP_LA_LIGA"]`.
  V6 W11's `lookup_cup_team_pair` (cross-league walk) is the helper
  for INFERENCE. For TRAINING, the same fix is needed in `build_elo_features`
  / `build_form_features`. **This is the most likely V8 W3 blocker
  to surface during ablation** — leaving it as an explicit pre-condition
  for W3 work.

## Tests

`tests/v4/test_cup_training.py` — 20 tests:

| Group | Coverage |
|---|---|
| `TestTeamPoolFromLeagueDF` (2) | Unions all leagues; empty df |
| `TestCanonicalizePair` (4) | Both resolve via alias; Real Madrid CF; one unresolved; both unresolved |
| `TestBuildCupTrainingRows` (8) | Happy path; canonical names applied; pad strategy (NaN for shot stats; psc proxy for alt-books; O/U from envelope; result_1x2 derived); O/U missing → NaN; unresolved dropped; no-odds inner-join drop; empty inputs schema-only; column dtypes |
| `TestUnionLeagueAndCup` (3) | Empty cup unchanged; None cup unchanged; concat + sort by date |
| `TestTrainWithCupDataArgparse` (3) | `--with-cup-data` alone; combined with all flags; `--cup-canonical-fuzzy` parses |

Full V4 suite: **642/642 passing** (622 prior + 20 new W2).

## Files touched in W2

```
apps/api/src/nutmeg/v4/data/cup_training.py    [+] cup → V4 schema builder
                                                   + union helper
apps/api/src/nutmeg/v4/cli/train.py            [M] +--with-cup-data
                                                   +--cup-odds-dir
                                                   +--cup-canonical-fuzzy
                                                   + UNION wiring before
                                                     build_feature_frame
tests/v4/test_cup_training.py                  [+] 20 tests
docs/V8_ROADMAP.md                             [M] W2 ✅
docs/v8_w2_cup_data_union.md                   [+] (this file)
```

## Next: V8 W3 — multi-fold ablation

W3 will:
1. Add a `walk_forward_with_cup` runner (or extend the existing
   `walk_forward.py`) that supports the `--with-cup-data` /
   `--with-cup-features` combinations
2. Run 4-cutoff × multi-league-pool ablation:
   - Fold 1: cutoff 2024-01-15, train EPL-only baseline
   - Fold 2: cutoff 2024-01-15, train EPL + UCL union
   - Fold 3: cutoff 2024-08-01, train EPL+ESP+ITA, baseline
   - Fold 4: cutoff 2024-08-01, train EPL+ESP+ITA+UCL union
3. **If first run shows NaN Elo features on cup rows** (because
   team_state[league] lookup misses cross-league teams), W3 must
   first extend `build_elo_features` to use `lookup_cup_team_pair`.
4. Ship gate: ≥ 3/4 folds improve by ≥ −0.001 log-loss → V8 W4 ships
   `data/v4_model_cat_cup/` opt-in artifact

V8 W3 + W4 close out Track B and the V8 cup-trained ML deliverable.
