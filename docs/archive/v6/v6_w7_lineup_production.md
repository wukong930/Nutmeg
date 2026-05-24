# V6 W7 — Lineup-aware production artifact

_Ships the V6 W6 validated `recent_n_injuries` features into the production
training + inference path. Lineup-aware artifact is opt-in (`--with-lineups`)
so the V5 W12 CatBoost default remains untouched until live A/B confirms
the multi-fold improvement holds in real bets._

## What's new

### `nutmeg-train --with-lineups`

```bash
nutmeg-train --model cat --cutoff 2024-08-01 \
    --with-lineups \
    --lineup-leagues EPL,ESP_LA_LIGA \
    --lineup-seasons 2023,2024 \
    --out data/v4_model_cat_lineups
```

Flag behavior:
- `--with-lineups` enables the V6 W6 validated feature subset
  (`lineup_home/away_recent_n_injuries`)
- `--lineup-leagues` (default `EPL,ESP_LA_LIGA`) chooses which V4 canonical
  league codes to pull lineup caches for; only fixtures matching these
  leagues + seasons populate the lookup
- `--lineup-seasons` (default `2023,2024`) chooses which season-start
  years; combined with `--lineup-leagues` this caps the API-Football
  cache walk

The training-time loop:
1. Builds `lineup_lookup` and `recent_injury_lookup` from
   `data/external/api_football/` (populated by `nutmeg-ingest-lineups`)
2. Threads both through `build_feature_frame`
3. Uses `feature_columns_with_lineups()` as the GBM input list (V5 baseline
   39 cols + the 2 validated lineup cols)
4. Persists `with_lineups=True` + the lineup league/season list in the
   artifact's `metadata.json`

Default behavior (no `--with-lineups`) is unchanged: V5 W12 CatBoost
defaults.

### `build_features_for_fixtures` accepts lineup lookups

Inference path (`nutmeg-recommend`, `/api/v4/recommend`, dashboard) is
backward-compatible: lineup-aware artifacts automatically run
`build_lineup_features` even when the caller doesn't supply a lookup —
in that case rows get `recent_n_injuries = 0` (zero-injury graceful
default).

This means a user with a lineup-aware artifact but no real-time API
access still gets predictions; they're slightly biased toward
"no recent injuries" but otherwise sound.

### Metadata persistence

`V4Artifact.metadata` gains three keys when trained with `--with-lineups`:
- `with_lineups: bool` — distinguishes lineup vs lineup-free artifacts
- `lineup_leagues: list[str]` — which leagues the training cache covered
- `lineup_seasons: list[int]` — which season-start years

These metadata fields let downstream tooling (W8 observation cron, A/B
script, dashboard) report "this prediction came from the lineup-aware
artifact" rather than guessing from disk path.

## A/B demo

Same 8-match demo CSV, two artifacts:

| Match | Cat λh | Lineup λh | Cat λa | Lineup λa |
|-------|--------:|----------:|--------:|----------:|
| Arsenal vs Liverpool | 1.230 | 1.297 | 1.375 | 1.365 |
| Real Madrid vs Getafe | 2.274 | 2.219 | 0.788 | 0.790 |
| Inter vs Fiorentina | 1.703 | 1.555 | 0.973 | 1.117 |
| Bayern Munich vs Koln | 3.251 | 3.116 | 0.774 | 0.775 |
| Paris SG vs Nice | 2.213 | 2.087 | 0.779 | 0.847 |
| Ajax vs AZ Alkmaar | 1.752 | 1.671 | 1.113 | 1.175 |
| Porto vs Benfica | 1.542 | 1.435 | 0.962 | 1.194 |
| Leeds vs Burnley | 1.555 | 1.406 | 1.054 | 1.152 |

The lineup-aware artifact tends to predict slightly **more parity**
(lower home λ, higher away λ across most matches). The biggest
swing is Porto vs Benfica where the away λ jumps 0.962 → 1.194,
consistent with the W6 finding that recent injuries dampen the
home-team scoring expectation.

Demo-time inference uses zero-injury defaults (the demo fixtures CSV
isn't in the API-Football cache), so these differences come purely
from the artifact's TRAINING having seen lineup-aware data. In live
production, the user would also pass a fresh `recent_injury_lookup`
covering today's fixtures.

## Decision: default stays without lineups

The W5 W12 CatBoost default remains unchanged. Reasons:

1. The lineup-aware artifact requires API-Football paid subscription
   ($19/mo) to populate the lookup; not every user has it
2. The V6 W6 −0.0020 mean log-loss improvement is from BACKTEST. The
   W8 observation cron needs ≥ 4 weeks of real settled bets to confirm
   it translates to live ROI improvement
3. The lineup-aware artifact is larger (~250 KB CatBoost binary) and
   slightly slower (~5 ms extra per batch); switch only when the
   benefit is confirmed

The lineup artifact ships as an **opt-in** path. Users with API access
who want the V6 win can train one. The cron weekly bench can A/B both
artifacts against the same test set.

## Tests

3 new tests in `tests/v4/test_e2e.py::TestE2ECatBoostLineups` — skipped
when the API-Football cache isn't populated (so CI without the cache
still passes; running locally with cache populated gives full coverage):

- `test_artifact_metadata_marks_with_lineups` — `metadata["with_lineups"]
  == True`, `metadata["lineup_leagues"]` contains EPL
- `test_feature_columns_include_recent_injuries` — both
  `lineup_home/away_recent_n_injuries` are in the persisted
  `feature_columns` list
- `test_recommend_works_with_lineup_artifact` — `nutmeg-recommend` on
  the lineup artifact returns valid lambdas for the demo fixtures
  (proves the inference path gracefully handles missing live lineup
  lookup)

Total V4 suite: **378/378 passing** (375 V6 W6 + 3 V6 W7).

## Next: V6 W8

Live observation — point both `data/v4_model_cat/` and
`data/v4_model_cat_lineups/` at the daily recommend cron, accumulate
≥ 4 weeks of settlements, then decide via `nutmeg-live-vs-backtest`
whether to switch the default.

## What V6 W7 doesn't do

- **No automatic injury ingest at inference time.** The recommend CLI
  reads the API-Football cache that's already on disk. A separate cron
  task is needed to refresh the cache nightly so today's predictions
  see today's injury list. Defer to a small `nutmeg-refresh-lineups`
  CLI in V6 W8 (~10 lines of glue).
- **No multi-season cards refreshed.** The current
  `docs/v4_multi_season_card.md` doesn't reflect the lineup artifact;
  re-running the weekly cron with both artifacts is V6 W8 work.
- **No production dashboard switch.** The dashboard still serves the
  V5 W12 default. Switching is a 1-line `NUTMEG_V4_ARTIFACT_PATH`
  env var change; intentionally not done here.
