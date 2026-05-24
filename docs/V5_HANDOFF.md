# Nutmeg V5 Handoff

_Last updated: 2026-05-23 (V5 W12 / `v5.0-shipped` tag)_

This document is the **single source of truth** for V5 — the 12-week refactor
that picked up where [V4_HANDOFF.md](V4_HANDOFF.md) left off. Read this
first when picking up the project, then [V4_HANDOFF.md](V4_HANDOFF.md) for
the V4 design details that V5 inherits.

---

## 1. What V5 was

V4 had landed (log-loss 0.9987 vs Pinnacle 0.9904, multi-season validated),
but the codebase was bloated and three obvious-on-paper improvements were
sitting un-tried: xG features, market drift, ensemble. V5 (12 weeks) was a
**science-led refactor**: improve where evidence supports it, document
falsified hypotheses so future work doesn't re-tread them, and build the
observability scaffolding so improvements actually compound.

## 2. Production state today

| Layer | Default | Notes |
|---|---|---|
| Model backend | **CatBoost** (`--model cat`) | W12 default flip. `--model lgb` kept as fallback. |
| Calibration | Global temperature scaling | Per-league T (W9) built and integrated but **disabled by default** (val window too small) |
| Features | 39 columns: market + Elo + form + xG-lite + clubelo | xG-lite is shots-derived (W4); clubelo from W3 cache |
| Recommendation flow | DC 9×9 grid → 1X2 + handicap → Kelly parlay enumeration | Unchanged from V4 |
| API surface | `/api/v4/*` only | v1 removed in W2; W11 added `predictions/upcoming` + `live-vs-backtest` |
| Frontend | Single-file `/api/v4/dashboard` | Next.js frontend removed in W2 |
| Observation DB | SQLite, schema v2 (`snapshot_phase` + `model_type`) | Auto-migrates v1 DBs |
| Automation | Weekly cron (`weekly-bench.yml`) | Sunday 02:00 UTC; commits weekly cards |

## 3. Current numbers (24/25 test season, GBM-eligible 4,331 matches)

| Model | log-loss | Brier | hit-rate | ECE | Δ vs Pinnacle |
|-------|---------:|------:|---------:|----:|--------------:|
| Pinnacle (ceiling) | 0.9904 | 0.5916 | 0.5124 | 0.0123 | — |
| V4 LightGBM + DC + Temp | 0.9971 | 0.5961 | 0.5077 | 0.0185 | +0.0067 |
| **V5 CatBoost + DC** (W12 default) | **0.9960** | **0.5950** | **0.5112** | **0.0120** | **+0.0056** |
| V5 XGBoost + DC | 0.9963 | 0.5953 | 0.5121 | 0.0153 | +0.0059 |
| V5 LogReg stacker (disabled) | 0.9989 | 0.5971 | 0.5050 | 0.0203 | +0.0085 |

CatBoost ECE (0.0120) is actually **better than Pinnacle's** (0.0123) —
calibration is excellent even though log-loss is still 0.0056 above.

Multi-season stability (multi-season card):

| Cutoff | Pinnacle | LightGBM | CatBoost | Δ (Cat − Pin) |
|--------|---------:|---------:|---------:|--------------:|
| 22/23 | 0.9940 | 1.0020 | 0.9984 | +0.0044 |
| 23/24 | 0.9865 | 0.9951 | 0.9898 | +0.0033 |
| 24/25 | 0.9904 | 0.9971 | 0.9960 | +0.0056 |

CatBoost beats LightGBM in **every season tested** (average improvement
−0.0033 log-loss). Signal capture rate is ~93%; the remaining ~0.005
log-loss gap to Pinnacle is information Pinnacle has (lineups, late
injuries) that V5 doesn't.

## 4. What worked (positive results, shipped)

### W4 — xG-lite + clubelo features
- **+10 cols (xG-lite)**: shots/SoT-derived xG proxy, including
  regression-to-mean signal (xG minus actual goals)
- **+5 cols (clubelo)**: independent cross-country ELO from `clubelo.com`
  cache (W3 ingest)
- Multi-season log-loss improvement: 22/23 ≈ 0, 23/24 −0.0008, 24/25 −0.0016
- Critical implementation detail: missing data → placeholder + `*_available`
  flag, so rows with NaN inputs don't crash the GBM dropna
- File: `nutmeg.v4.features.{xg_lite,clubelo_features}`

### W6 — CatBoost single model
- Three Poisson regressors trained side-by-side on identical features
- CatBoost wins because it natively handles `league` as a categorical
  (LightGBM and XGBoost see only numeric columns; can't replicate
  league-conditioned scoring efficiently)
- Multi-season: **−0.0033 log-loss avg vs LightGBM**, beat in all 3 seasons
- Files: `nutmeg.v4.model.{cat_lambda,gbm_lambda,xgb_lambda}.py`

### W7 — CatBoost production migration
- `V4Artifact.model_type` discriminator + lazy CatBoost import
- `nutmeg-train --model {lgb,cat}` flag (W12: default flipped to `cat`)
- `predict_lambdas` dispatches per backend
- File: `nutmeg.v4.model.persist`

### W8 — Observation loop
- SQLite schema v2 with `snapshot_phase` (`pre_close | closing | post_close`)
  and `model_type` columns; auto-migrates pre-W8 v1 databases
- `nutmeg-recommend --snapshot-phase pre_close` for ≥60-min-before-kickoff captures
- `nutmeg-live-vs-backtest --weeks 4 --backtest-cutoff 2024-08-01` CLI
- Exits non-zero (code 2) when live hit-rate diverges from backtest by > 5pp
- Files: `nutmeg.v4.observation.{store,recorder,live_vs_backtest}`

### W10 — Experiment tracking + weekly CI
- `nutmeg-bench --track` writes versioned snapshots to
  `data/v4_model/experiments/<sha>_<ts>/{metadata,pooled}.json + card.md`
- `nutmeg-experiment-diff` enumerates / diffs experiments
- GH Actions weekly cron runs bench + multi-season + diff, commits cards
  to `docs/weekly/<YYYY-WW>-{bench,multi,diff}.md` automatically
- Files: `nutmeg.v4.eval.experiment_tracker`, `.github/workflows/weekly-bench.yml`

### W11 — API surface consolidation
- `POST /api/v4/predictions/upcoming` — lightweight prediction-only endpoint
  (no Kelly, no parlay) for dashboards
- `GET /api/v4/observation/live-vs-backtest` — read-only HTTP wrapper around
  W8's CLI
- `HealthResponse.model_type` + `ModelInfo.model_type` so callers see backend
- `RecommendRequest.snapshot_phase: Literal[...]` typed validation

### W12 — CatBoost default flip
- `nutmeg-train` default is now `--model cat`
- Existing automation that didn't specify `--model` now produces CatBoost
  artifacts automatically
- `--model lgb` remains available for A/B and rollback

## 5. What didn't work (negative results, documented)

These are all **falsifiable hypotheses that V5 disproved on our data**.
Documented in detail so future iterations don't re-derive them.

### W5 — Market dynamics drift features
- **Tried**: opening odds (PSH/PSD/PSA) vs closing → drift signals
- **Result**: 3/3 seasons worse (log-loss +0.0012 to +0.0029 over W4)
- **Why**: Pinnacle is sharp → closing already absorbs drift information;
  what's left is noise the GBM overfits on
- **Status**: Module `nutmeg.v4.features.market_dynamics` kept as dormant
  framework; GBM input list does NOT include drift columns
- See [v5_w5_ablation.md](archive/v5/v5_w5_ablation.md)

### W6 — LogReg ensemble stacker
- **Tried**: LightGBM + XGBoost + CatBoost outputs → 9-dim logits → LogReg
- **Result**: 3/3 seasons worse than every single base (log-loss +0.0029 to +0.0092)
- **Why**: 3 bases trained on same features → highly correlated logits →
  9-dim LogReg on ~500-1000 val rows overfits
- **Status**: `nutmeg.v4.model.stacker` kept; `WalkForwardConfig.with_ensemble`
  flag wires it in but defaults False
- See [v5_w6_ablation.md](archive/v5/v5_w6_ablation.md)

### W9 — Per-league temperature
- **Tried**: per-league T fit (instead of one global T)
- **Result**: 3/3 seasons worse log-loss (+0.0029 to +0.0110)
- **Why**: 90-day val window leaves ~30-50 matches per league — too few to
  fit a per-league T without overfitting val. Theoretical sweet spot is
  ≥800/league (DEFAULT_MIN_SAMPLES_PER_LEAGUE)
- **Status**: `nutmeg.v4.calibration.per_league` kept; walk_forward emits
  `gbm_dc_pl_temp` diagnostic row so the next iteration can spot when val
  windows have grown enough to enable
- See [v5_w9_per_league_temperature.md](archive/v5/v5_w9_per_league_temperature.md)

### Shared pattern

W5, W6 stacker, and W9 all failed the same way: **more parameters + small
val pool + correlated inputs → overfit on validation set, regression on
test**. Single-shot fits on small val are dangerous; future iterations
adding any per-segment / per-feature-group parameterization should
explicitly multi-season-validate before shipping.

## 6. Codebase structure

```
apps/api/src/nutmeg/
  main.py              FastAPI app, only /api/v4/* routes
  config.py            Minimal pydantic settings (env, paths, log level)
  utils/
    team_canonical.py  External-source → V4 team name mapping (W3)
  v4/
    api/
      routes.py        /v4/{health, recommend, predictions/upcoming, dashboard}
      observation_routes.py  /v4/observation/*
      schemas.py       Pydantic v2 request/response models
      static/dashboard.html  Single-file vanilla-JS UI
    data/
      ingest.py        football-data.co.uk CSV → canonical DataFrame
      schema.py        MATCH_COLUMNS — the canonical schema
      sources/
        clubelo.py     Working (W3)
        understat.py   Stub (blocked — JS-rendered site)
        fbref.py       Stub (blocked — HTTP 403)
        oddsportal.py  Stub (blocked — Cloudflare SPA)
      external_schema.py  DuckDB-friendly column lists
    features/
      market.py        Pinnacle devig (W3 bugfix for /0)
      market_dynamics.py  Drift (W5 disabled in pipeline)
      elo.py           Per-league internal ELO
      form.py          Rolling 6-match stats (W4 added shots_against)
      xg_lite.py       Shots-derived xG proxy (W4 ACTIVE)
      clubelo_features.py  Cross-country ELO features (W4 ACTIVE)
      pipeline.py      GBM_FEATURE_COLUMNS = 39 cols
    model/
      gbm_lambda.py    LightGBM Poisson (V4 default → W12 fallback)
      xgb_lambda.py    XGBoost Poisson (W6, in --with-ensemble)
      cat_lambda.py    CatBoost Poisson (W12 default)
      stacker.py       LogReg ensemble (W6, disabled by default)
      dixon_coles.py   Score grid + 1X2/handicap conversion
      dc_mle.py        Legacy MLE baseline (still in bench card)
      persist.py       Multi-backend V4Artifact (W7 model_type dispatch)
    calibration/
      temperature.py   Global T (W12 default)
      per_league.py    Per-league T (W9 disabled in pipeline)
      isotonic.py      Available but unused (overfits on small val)
    combo/
      selections.py    MatchInput, Selection
      enumerate.py     Combo candidate generation
      kelly.py         Fractional Kelly w/ caps
      recommend.py     Top-N ranking by log growth
    observation/
      store.py         SQLite schema v2 (W8 auto-migration)
      recorder.py      record_session with snapshot_phase
      settlement.py    Auto-settle on outcome upsert
      roi.py           ROI / hit-rate / calibration aggregators
      live_vs_backtest.py  Live slice + backtest gap calc (W8)
    eval/
      walk_forward.py  Time-strict 3-way split + per-league + ensemble
      multi_season.py  Run walk_forward at multiple cutoffs (W6 ensemble cols)
      experiment_tracker.py  Track + diff bench runs (W10)
      report.py        Bench card formatter (W6 added ensemble rows)
      multi_season_report.py  Multi-cutoff comparison card
      metrics.py       log-loss, Brier, ECE, hit-rate, encode_labels
      baselines.py     Pinnacle devig + uniform
    cli/
      bench.py         --with-ensemble, --track (W10)
      multi_season_bench.py   --with-ensemble
      train.py         --model cat (W12 default) | lgb (fallback)
      recommend.py     --snapshot-phase, --record-to
      record_outcome.py
      roi_report.py
      ingest_external.py  --source clubelo --refresh-empty
      live_vs_backtest.py  exit 2 when over tolerance
      experiment_diff.py  --list, --a / --b SHA prefix

configs/competitions/        15 league YAMLs (unused at runtime; metadata only)
data/historical_sources/     27k football-data.co.uk CSVs (~12 MB, committed)
data/v4_model/               LightGBM artifact (committed W1, lgb fallback)
data/v4_model_cat/           CatBoost artifact (NOT committed; train locally)
data/external/clubelo/       Per-team ELO parquets (gitignored, 335 teams)
data/v4_model/experiments/   Tracked bench runs (gitignored)
docs/
  V4_HANDOFF.md              V4 design (READ FIRST AFTER THIS)
  V5_HANDOFF.md              This file
  V5_ROADMAP.md              12-week plan with per-week verdicts
  v4_baseline_card.md        Latest single-season bench (auto-refreshed)
  v4_multi_season_card.md    Multi-cutoff bench (auto-refreshed)
  v5_external_data_coverage.md   clubelo coverage card
  v5_w{5,6,7,8,9,10,11,12}_*.md  Per-week ablation / migration writeups
  weekly/                    GH Actions auto-pushed cards
  legacy/v2_archive/         Pre-V4 design docs (archived in W2)
tests/v4/                    282 unit + integration tests
```

**Total LoC** (apps/api/src/nutmeg/): ~6,500 lines + ~3,500 lines tests.
Down from 224k LoC pre-W2 (−97% if counted line-for-line).

## 7. Common operations

### Daily prediction workflow

```bash
# Refresh CatBoost artifact (once per week or after a feature change)
nutmeg-train --cutoff $(date +%Y-%m-%d) --out data/v4_model_cat

# Generate today's recommendations (closing-line snapshot)
nutmeg-recommend --fixtures today.csv --model data/v4_model_cat \
  --bankroll 1000 --top-n 5 --record-to data/v4_observation.db

# Day-after: record outcomes (auto-settles)
nutmeg-record-outcome --db data/v4_observation.db --csv yesterday.csv

# Weekly: ROI report + live-vs-backtest
nutmeg-roi-report --db data/v4_observation.db --out roi.md
nutmeg-live-vs-backtest --db data/v4_observation.db --weeks 4 \
  --backtest-cutoff 2024-08-01 --out live_vs_backtest.md
```

### Bench + experiment tracking

```bash
# Run the full bench with ensemble + tracking
nutmeg-bench --with-ensemble --track

# See all tracked experiments
nutmeg-experiment-diff --list

# Diff the latest two
nutmeg-experiment-diff
```

### Backend A/B

```bash
nutmeg-train --model cat --out data/v4_model_cat
nutmeg-train --model lgb --out data/v4_model_lgb

# Compare per-fixture predictions
diff <(nutmeg-recommend --model data/v4_model_cat ... --format json) \
     <(nutmeg-recommend --model data/v4_model_lgb ... --format json)
```

## 8. Outstanding work for V6 / future iterations

Listed by likely value, highest first.

1. **Live odds ingest** — currently `recommend` requires user-supplied
   fixtures CSV with closing odds. Auto-fetching from a tractable source
   (sportradar, the-odds-api.com paid tier, or an offshore book API) would
   close the loop. OddsPortal (the originally-planned free source) is
   Cloudflare-blocked; budget another data-source bake-off for V6.
2. **Live odds streams** — beyond static fixtures, capturing multi-snapshot
   odds during the betting window would let W5's market-dynamics drift
   features get a fair shake on real multi-point streams (not just open/close)
3. **Lineup / injury data** — Pinnacle's remaining advantage over us is
   day-of info. API-Football $19/mo includes this; the W12 paid-data
   decision deferred this until W8 observation cron has ≥4 weeks of real
   ROI data to justify the spend
4. **Bayesian hierarchical for small-sample leagues** — W7+ original plan,
   still untested. Larger val windows (or larger overall data) may
   unblock it
5. **Real-time `/predictions/upcoming` cache** — current endpoint is
   stateless. Caching by `(fixture-hash, model_type)` would help dashboards
6. **CatBoost ECE 0.0120 < Pinnacle 0.0123** is an interesting result —
   we have BETTER calibration but worse log-loss. The model is sharper in
   the wrong places. Investigate per-bucket Brier breakdown to find where

## 9. Known sharp edges

1. **CatBoost serializes binary `.cbm`** — not human-readable. To inspect
   model structure, load via `cb.CatBoostRegressor().load_model(path)` and
   use `.get_feature_importance()`
2. **clubelo cache is fragile** — `--refresh-empty` recovers from rate-limit
   damage but full refresh hits ~3-5s/team for non-existent slugs (Italy,
   Portugal teams sometimes mismatched). See `CLUBELO_SLUGS` in
   `sources/clubelo.py`
3. **xG-lite formula constants** (`NON_SOT_WEIGHT=0.04, SOT_WEIGHT=0.30`)
   are hand-calibrated to league-average xG ≈ 1.4. If goal scoring rates
   shift, re-fit
4. **walk_forward's `per_league=30 min_samples` is bench-only** — production
   `train.py` uses the global `fit_temperature_1x2`. Don't conflate the two
5. **Test fixture `data/v4_model/`** is the LightGBM baseline from W1. Many
   tests assume lightgbm artifact files. Either pin tests to `--model lgb`
   or regenerate the committed artifact with CatBoost (W12 + W13?)

## 10. Tests

282/282 V4 tests passing on `v5.0-shipped`:

```bash
PYTHONPATH=apps/api/src python -m pytest tests/v4/ -q
```

By module:
- 13 dixon_coles + 19 dc_mle (legacy baselines)
- 4 ingest + 19 metrics + baselines
- 7 features + 12 xg_lite + 10 clubelo_features + 13 market_dynamics
- 22 team_canonical + 12 clubelo + 14 ingest_external
- 11 calibration + 9 per_league_temperature
- 9 combo
- 17 observation + 16 observation_api + 15 live_vs_backtest
- 7 xgb_lambda + 7 cat_lambda + 12 stacker
- 16 experiment_tracker
- 10 e2e (6 lightgbm + 4 catboost)
- 20 api + 16 observation_api (W11 additions)

## 11. Tags and milestones

| Tag | Meaning |
|-----|---------|
| `v4.0-frozen` | V4 baseline pre-V5 refactor (log-loss 0.9987) |
| `v5.w2` | After aggressive cleanup (304 → 49 .py files) |
| `v5.w3` | clubelo + ingest framework |
| `v5.w4` | xG-lite + clubelo features production |
| `v5.w5` | market-dynamics ablation (negative) |
| `v5.w6` | ensemble ablation + CatBoost win |
| `v5.w7` | CatBoost prod migration opt-in |
| `v5.w8` | observation loop + snapshot phases |
| `v5.w9` | per-league T ablation (negative) |
| `v5.w10` | experiment tracking + weekly cron |
| `v5.w11` | API consolidation |
| `v5.w12` | CatBoost default + handoff |
| `v5.0-shipped` | V5 complete, in production |

Each commit message documents what was added/removed and why. Reading the
commit log in order from `v4.0-frozen` to `v5.0-shipped` is a complete
record of how V5 unfolded.

---

**Welcome to V6.**
