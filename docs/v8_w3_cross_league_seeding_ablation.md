# V8 W3 — Cross-league Elo/form seeding + ablation runner

_Third piece of V8's Track B closeout. V8 W2 wired cup rows into the
training frame, but the Elo/form builders' `(league, team)` state
keys meant cup-row signal collapsed to "two unseen teams at 1500".
W3 fixes that with **cross-league state seeding** (opt-in flag,
default off — preserves all V4-V7 paths) + ships
`nutmeg-cup-ablation` to run the multi-fold check. V8 W4 either
ships the cup-aware artifact (if gate passes) or documents the
negative result._

## Why cross-league seeding

V4's Elo (and form) state is keyed by `(league, team)` — Arsenal's
EPL Elo is independent of Arsenal's UCL Elo. That's correct for
league-only training: EPL state stays clean, La Liga state stays
clean.

V8 W2's `--with-cup-data` UNIONs cup rows into training. Without
seeding, a UCL Real Madrid vs Bayern Munich match looks like this
to `build_elo_features`:

```
state["UCL"]["Real Madrid"]    → 1500.0 (default; never seen in UCL)
state["UCL"]["Bayern Munich"]  → 1500.0 (default)
elo_diff = 0 + 60 (home_adv) = 60   ← signal-less prior
```

Meanwhile `state["ESP_LA_LIGA"]["Real Madrid"]` is sitting at ~1820
(after a winning season), and `state["GER_BUNDESLIGA"]["Bayern Munich"]`
at ~1850. The cup row's feature signal is zero — the GBM learns
that "all UCL matches are between two average teams." Not useful.

**Cross-league seeding** fixes this by intercepting the FIRST
lookup in a new pool. If `state[league][team]` would return the
default but the team HAS a non-default value somewhere else in
`state[*][team]`, seed the cup pool with that cross-league value
before reading. The cup row's Elo features now reflect each team's
real strength.

Update logic is unchanged — writes go to `state[league][team]`
only, so the cup pool stays separate from the domestic pool. The
team's domestic Elo isn't polluted by cross-league dynamics.

Same pattern applied to form features (`g_for`, `g_ag`, `shots`,
`shots_ag`, `sot`, `sot_ag`, `last_date`).

## What W3 ships

### 1. `nutmeg.v4.features.cross_league_state` module

```python
from nutmeg.v4.features.cross_league_state import (
    seed_elo_value,      # mutating helper for build_elo_features
    seed_form_deque,     # mutating helper for build_form_features (deque cols)
    seed_form_last_date, # mutating helper for build_form_features (last_date)
)
```

All three mutate the passed-in state dict and return the seeded value
(or the original empty/default when no cross-league source exists).

### 2. `build_elo_features` + `build_form_features` accept
   `cross_league_seed: bool = False` (default off)

```python
out = build_elo_features(df, cross_league_seed=True)
out = build_form_features(df, cross_league_seed=True)
```

When `cross_league_seed=True`, rows are sorted by `date` (not
`(league, date)`) so the most-recent cross-league state is available
when a new league pool first encounters a team.

### 3. `build_feature_frame(cross_league_seed=False)` pass-through

```python
feats = build_feature_frame(df, cross_league_seed=True)
```

Passes the flag down to Elo + form builders. Plumbing for V8 W2's
`--with-cup-data` train flag (auto-enables seeding).

### 4. `nutmeg-train --with-cup-data` auto-enables seeding

V8 W2 shipped the `--with-cup-data` flag; V8 W3 makes it
implicitly enable cross-league seeding. Cup rows need it; users
who pass `--with-cup-data` always want it.

(`--with-cup-features` alone doesn't enable seeding — adding the
5 cup feature COLUMNS to a league-only training set doesn't need
cross-league lookups.)

### 5. `WalkForwardConfig` accepts cup-ablation parameters

```python
WalkForwardConfig(
    test_cutoff=pd.Timestamp("2024-08-01"),
    cup_history_df=cup_history_df,
    cross_league_seed=True,
)
```

Two new optional fields:
- `cup_history_df: pd.DataFrame | None = None` — passes to
  `build_feature_frame` so cup feature columns get appended
- `cross_league_seed: bool = False` — passes to
  `build_feature_frame` so Elo/form use cross-league seeding

Default values preserve V5/V6/V7 walk_forward behavior exactly.

### 6. `nutmeg-cup-ablation` CLI

```bash
# Default: 4 cutoffs × 4 modes (baseline / cup_data / cup_features / cup_full)
nutmeg-cup-ablation --out docs/v8_w3_cup_ablation.md

# Tighter sweep for development
nutmeg-cup-ablation --cutoffs 2024-08-01 --modes baseline,cup_full

# Different cup pool
nutmeg-cup-ablation --cup-leagues UCL --cup-seasons 2023,2024 \
    --cutoffs 2024-08-01,2024-12-01
```

Modes:

| Mode | `--with-cup-data` | `--with-cup-features` | What's tested |
|---|:---:|:---:|---|
| `baseline` | ✗ | ✗ | V5 W12 default (control) |
| `cup_data` | ✓ | ✗ | UNION cup rows; no cup-feature COLS — does extra training data alone help? |
| `cup_features` | ✗ | ✓ | Add 5 cup cols; no UNION — sanity check (should be a no-op) |
| `cup_full` | ✓ | ✓ | Both — the production "cup-aware artifact" candidate |

For each (cutoff, mode), the runner:
1. Loads the league training data
2. Optionally UNIONs cup rows + flags cross-league seeding
3. Optionally loads cup_history_df for feature columns
4. Runs `run_walk_forward` with the assembled config
5. Records pooled log_loss / Brier / hit-rate

Ship gate: **≥ 3/4 folds show `cup_full` improving over `baseline`
by ≥ −0.001 log-loss**. Same bar V6 W6 applied to
`recent_n_injuries`. Same anti-overfit insurance V5 W5/W6/W9
wished they'd had.

Output markdown card has a pivoted table (rows = cutoffs × modes;
columns = log_loss, delta, hit-rate) and an explicit Pass/Fail
verdict at the bottom.

## How to actually run the ablation

**Prerequisite**: cup parquets ingested. Three commands the user
runs locally (or in a one-off GH Actions job with API token):

```bash
nutmeg-ingest-cup-history --leagues UCL,UEL --seasons 2021,2022,2023,2024
nutmeg-ingest-cup-odds    --leagues UCL,UEL --seasons 2021,2022,2023,2024
nutmeg-canonical-report-cup --show unmatched   # extend aliases as needed
```

Then run the ablation:

```bash
nutmeg-cup-ablation --out docs/v8_w3_cup_ablation_2026-05.md
```

Read the bottom verdict. If `Gate PASSED`, V8 W4 ships the artifact.
If `Gate NOT passed`, V8 W4 documents the negative result and Track
B closes here.

## What W3 doesn't do

- **Doesn't run the ablation itself.** The runner is shipped; the
  data accumulation + execution is a user action. (Could be wrapped
  into the daily/weekly cron later, but it's a one-off per release.)
- **Doesn't ship the cup-aware artifact.** V8 W4 — conditional on
  the gate passing.
- **Doesn't change the V5 W12 default.** All flags are opt-in; the
  production CatBoost artifact is untouched.

## Tests

`tests/v4/test_cross_league_state.py` — 23 tests:

| Group | Coverage |
|---|---|
| `TestSeedEloValue` (4) | Same-league existing kept; cross-league seed when missing; default when team unknown anywhere; default value in other pool not seeded |
| `TestSeedFormDeque` (3) | Copies non-empty history; keeps existing cup-pool value; empty when no source |
| `TestSeedFormLastDate` (3) | Cross-league max date; own value kept; None when no source |
| `TestBuildEloWithSeed` (2) | Seed off → defaults on cup row; seed on → picks up domestic Elo |
| `TestBuildFormWithSeed` (2) | Seed off → empty cup form; seed on → pulls EPL form |
| `TestPipelineCrossLeague` (2) | `build_feature_frame` accepts flag; `WalkForwardConfig` accepts cup-ablation fields |
| `TestCupAblationModes` (2) | Valid modes constant; baseline returns unchanged df |
| `TestCupAblationCLIParse` (3) | Invalid mode → 2; missing data → 1; unparseable cutoff → 2 |
| `TestFormatAblationReport` (2) | Card has ship-gate section; gate fails when no improvement |

Full V4 suite: **665/665 passing** (642 prior + 23 new W3).

## Files touched in W3

```
apps/api/src/nutmeg/v4/features/cross_league_state.py  [+] seed helpers
apps/api/src/nutmeg/v4/features/elo.py                 [M] +cross_league_seed kwarg
apps/api/src/nutmeg/v4/features/form.py                [M] +cross_league_seed kwarg
apps/api/src/nutmeg/v4/features/pipeline.py            [M] +cross_league_seed passthrough
apps/api/src/nutmeg/v4/cli/train.py                    [M] auto-enable seeding w/ --with-cup-data
apps/api/src/nutmeg/v4/eval/walk_forward.py            [M] +cup_history_df, cross_league_seed in WalkForwardConfig
apps/api/src/nutmeg/v4/cli/cup_ablation.py             [+] nutmeg-cup-ablation CLI
pyproject.toml                                         [M] +nutmeg-cup-ablation
tests/v4/test_cross_league_state.py                    [+] 23 tests
docs/V8_ROADMAP.md                                     [M] W3 ✅
docs/v8_w3_cross_league_seeding_ablation.md            [+] (this file)
```

## Next: V8 W4 — decision point

V8 W4 reads the ablation card produced by W3 and either:

- **Ship `data/v4_model_cat_cup/`** — train + persist the cup-aware
  artifact, add an A/B demo card. Ship as opt-in via the existing
  `--with-cup-data --with-cup-features` flag combination.
- **Document negative result** — write a `v6_w5_lineup_ablation.md`-
  style writeup explaining why cup data didn't translate, freeze
  Track B until V9, and move to Track D (Web UI + national-team Elo).

Either way, V8 W4 closes Track B and unblocks the rest of V8.
