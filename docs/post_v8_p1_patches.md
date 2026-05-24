# Post-V8 P1 patches — National Elo integration + recorder for 单关 / 复式

_Tag-less patches landed after `v8.0-shipped`. Both are independent
of the data-gated V8 W4 (cup ablation) and V8 W5 (lineup verdict)
decisions; they close the two highest-priority V9 P1 items from the
V8 retrospective._

## P1#4 — National-team Elo wired into `build_elo_features`

V8 W7 shipped the data layer (68 nation registry + `lookup_nation_elo`
helper) but didn't wire it into the Elo feature builder — WC / EURO
fixtures still fell back to V4's default 1500 "unknown team" Elo.

P1#4 closes that gap with ~30 lines of code + 11 tests.

### Change

`seed_elo_value` (in `nutmeg.v4.features.cross_league_state`) gained two
new kwargs:

```python
def seed_elo_value(
    state, league, team, default,
    *,
    nation_state: dict[str, float] | None = None,
    is_national_team_league: bool = False,
) -> float:
```

Lookup precedence (extended from V8 W3):
1. `state[league][team]` if already populated
2. **(NEW)** When `is_national_team_league=True` AND `nation_state` is provided
   → `lookup_nation_elo(nation_state, team)`. Hits seed the pool.
3. Walk every other league pool for a non-default value (V8 W3 cross-league seeding)
4. Default

`build_elo_features` accepts `nation_state` kwarg; passes through to seed.
`build_feature_frame` passes through. `nutmeg-train` gains
`--nation-elo-cache-dir` flag which calls `build_nation_elo_lookup` to
construct the dict.

### Sanity check

```python
df = pd.DataFrame([
    {'date': pd.Timestamp('2024-08-01'), 'league': 'EPL',
     'home_team': 'Arsenal', 'away_team': 'Liverpool',
     'home_goals': 2, 'away_goals': 1},
    {'date': pd.Timestamp('2024-11-15'), 'league': 'WC',
     'home_team': 'Brazil', 'away_team': 'Argentina',
     'home_goals': 1, 'away_goals': 1},
])

# Before: WC row Elo = 1500.0 / 1500.0
build_elo_features(df, cross_league_seed=False)

# After: WC row Elo = 1950.0 (Brazil) / 1990.0 (Argentina)
build_elo_features(df, cross_league_seed=True,
                    nation_state={'BRA': 1950.0, 'ARG': 1990.0})
```

### Run-it-yourself

```bash
# 1. Populate the nation Elo cache (~17 seconds)
nutmeg-ingest-national-elo

# 2. Train with national-team Elo seeding (assumes you've also run
#    nutmeg-ingest-cup-history for WC/EURO/COPA fixtures)
nutmeg-train --model cat \
  --with-cup-data \
  --cup-leagues UCL,UEL,WC,EURO,COPA_AMERICA \
  --nation-elo-cache-dir data/external/clubelo_national \
  --out data/v4_model_cat_full
```

### Tests

`tests/v4/test_national_elo_integration.py` — 11 tests:
- `seed_elo_value` nation_state path: hit / alias / skipped-when-not-NT /
  skipped-when-state-None / existing-pool-wins / unknown-team-falls-through
- `build_elo_features` integration: default unchanged / nation_state
  without cross_league_seed is no-op / both flags wire correctly /
  partial nation_state falls back per-team
- `build_feature_frame` passthrough sanity

## P1#5 — Recorder for 单关 / 复式 sessions + auto-record env-var

V8 W6 shipped the `/api/v4/recommend/single` and `/recommend/pool` endpoints
but didn't wire them into the observation DB. Users who placed bets via
the dashboard's new 单关 / 复式 tabs got no entry in `nutmeg-ab-report`
or `nutmeg-roi-report` — only 串关 (the V4 W8 path) was covered.

P1#5 adds two new recorder functions + an env-var-driven auto-record on
the endpoints + a schema fix.

### Schema fix — `PoolLegResponse`

`PoolTicketResponse.legs` previously used `SelectionResponse` which had
only `outcome / odds / probability / edge`. Settlement needs `match_id +
market_type` per leg. New `PoolLegResponse` includes both fields. The
endpoint emits the richer type.

This is a small backward-compatible API change (the response field gained
two fields; existing clients reading only `outcome / odds / probability /
edge` continue to work).

### Recorder additions

`nutmeg.v4.observation.recorder`:

```python
def record_single_session(db_path, *, request, response, snapshot_phase="closing"):
    # Each ticket → 1 parlay_recommendations row with k_legs=1, is_compound=False
    # legs_json uses V4 shape: [{match_id, market_type, selections: [{...}]}]
    # metadata.session_kind = "single"

def record_pool_session(db_path, *, request, response, snapshot_phase="closing"):
    # Each stake>0 ticket → 1 row with k_legs=N, is_compound=True
    # legs_json keeps match_id per leg
    # Zero-stake (diagnostic) tickets are skipped
    # metadata.session_kind = "pool"
    # metadata.pool_n / pool_n_combinations
```

Both write through the existing `insert_session` + `insert_parlay_recommendation`
helpers, so V4 W8 settlement (`_outcome_1x2` / `_outcome_handicap_1x2`)
handles them without modification.

### Env-var auto-record

```bash
# Set the env var, run the API → /recommend/single + /pool auto-record
export NUTMEG_V4_OBSERVATION_DB=data/v4_observation.db
nutmeg-api
```

When the var is unset (default), endpoints stay stateless — existing
behavior preserved. Recording failures are logged but never break the
recommendation response (exception caught and swallowed).

The choice of env-var (rather than a request body field) was deliberate:
a client-controlled DB path would be a write-anywhere security hole.

### Tests

`tests/v4/test_recorder_single_pool.py` — 15 tests:
- `record_single_session` (6): session row + ticket count, k_legs=1 +
  not-compound, stake_units quantized to 2, legs_json settleable shape,
  metadata.session_kind="single", empty-tickets edge case
- `record_pool_session` (5): selected-only filter (stake>0), k_legs=N +
  is_compound=True, metadata.session_kind="pool" + pool_n, match_id
  preserved per leg, n_fixtures=m semantics
- Endpoint auto-record (3): single E2E with env-var → DB written; pool
  E2E with env-var → DB written; env-var unset → no DB
- `PoolLegResponse` schema (1): /pool endpoint actually emits match_id
  + market_type per leg

## Joint stats

| Metric | Before P1 patches | After P1 patches |
|---|---:|---:|
| V4 tests passing | 713 | **739** (+26) |
| New files | — | 2 (test files) |
| Modified modules | — | 5 (cross_league_state, elo, pipeline, train CLI, routes, schemas, recorder) |
| New CLI flags | — | 1 (`nutmeg-train --nation-elo-cache-dir`) |
| New env vars | — | 1 (`NUTMEG_V4_OBSERVATION_DB`) |
| New API schemas | — | 1 (`PoolLegResponse`) |

## What these patches don't do

- **Dashboard checkbox still wired to nothing.** The existing 串关 tab's
  "记录到观测库" checkbox has been a no-op since V5 — not changed here.
  The V8 W6 new 单关 / 复式 tabs also don't have a checkbox. Recording
  now happens server-side via the env var; UI surface for opt-in
  per-session recording is a follow-up.
- **No CLI auto-record path.** `nutmeg-rec --auto-fetch` (V7 W1) and
  `nutmeg-recommend-pool` CLIs don't auto-record either. Their existing
  `--record-to` flag covers 串关; equivalent single + pool CLI flags
  are a follow-up if anyone uses them programmatically.
- **National-team Elo still needs fixtures to exercise.** Code path is
  ready; training rows in the V4 corpus don't include national-team
  matches. To verify the integration on real data, the user runs
  `nutmeg-ingest-cup-history --leagues WC,EURO --seasons 2022,2024`
  first.

## Commit

`feat(post-v8): national-team Elo seeding + observation recorder for single+pool`
