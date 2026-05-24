# Nutmeg V8 Handoff

_Last updated: 2026-05-24 (V8 ship / `v8.0-shipped` tag)_

This document is the **single source of truth** for V8 — the 5-coding-
week sprint that finished V7's Track B groundwork and shipped Track D's
first two pieces (dashboard 单关/复式 + national-team Elo). Read this
first when picking up the project, then [V7_HANDOFF.md](V7_HANDOFF.md)
for V7's automation layer, then [V6_HANDOFF.md](V6_HANDOFF.md) for V6's
product layer, then [V5_HANDOFF.md](V5_HANDOFF.md) for the model + data
plumbing V6 inherited, then [V4_HANDOFF.md](V4_HANDOFF.md) for the
original design.

---

## 1. What V8 was

V7 closed Track C (Operational automation: daily flow 5 → 2 steps) and
shipped Track B groundwork (cup-trained model: 4 pieces of data layer +
feature wiring). What V7 left for V8:

- **Track B finish** — cup-trained model needed (1) cross-league team-
  name canonicalization, (2) cup row UNION into the training frame,
  (3) cross-league Elo/form seeding, (4) multi-fold ablation runner,
  (5) actual ablation run + artifact ship decision
- **Track A — lineup-aware ROI verdict** — code shipped V6 W8 + V7
  W1-W3, gated on 4 weeks of cron data accumulation
- **Track D — product polish** — dashboard 单关/复式 surfaces, national-
  team Elo, web form for non-terminal users

V8 (8 weeks planned, 5 coding weeks + 3 data-gated weeks) shipped the
first 4 pieces of Track B's finish, both pieces of Track D's start, and
intentionally left W4 + W5 for the data to arrive.

## 2. The three tracks (continued from V7)

| Track | Theme | Weeks | Status |
|---|---|---|---|
| **B finish** | Cup-trained model: data UNION + canonicalization + seeding + ablation runner | W1-W3 + (W4 data-gated) | Groundwork ✅, decision data-gated |
| **A close** | Lineup-aware ROI verdict | W5 data-gated | Still pending |
| **D start** | Dashboard 单关+复式 + national-team Elo | W6, W7 | ✅ shipped |

Two ship-gates are explicitly left open by design:
- **V8 W4** (cup-aware artifact decision): waits on user running the
  V8 W3 `nutmeg-cup-ablation` against ingested cup data (V7 W6 + W8
  CLIs)
- **V8 W5** (lineup-aware default flip): waits on ≥ 4 weeks of cron
  settlements (V7 W2 `nutmeg-auto-settle` + V7 W3 `nutmeg-weekly-report`)

Same patience pattern V7 used: better to ship the infrastructure and
wait for real numbers than rush a verdict on incomplete data.

## 3. Production state today

| Layer | Default | Notes |
|---|---|---|
| Model backend | CatBoost (V5 W12 default — unchanged through V6-V8) | Lineup-aware + cup-aware variants both opt-in |
| Daily flow | 2 manual steps (recommend + place bets) | V7 W3 closed the loop |
| Dashboard tabs | ① 单关 / ② 串关 / ③ 复式 / ④ 录入结果 / ⑤ ROI / ⑥ 会话 / ⑦ 规则 | V8 W6 added ① + ③; 单关 = new default landing |
| Cup data layers | History + odds + UNION-into-training + cross-league seeding | All shipped; actual training run is V8 W4 (data-gated) |
| Cup team canonicalization | `to_v4_canonical_global` + `CUP_TEAM_ALIASES` (43 entries) + `nutmeg-canonical-report-cup` | V8 W1 |
| National-team Elo | 68 nations registered via clubelo `/<NationCode>` | V8 W7 — pure data layer, model integration is V9 |

## 4. What V8 shipped (week by week)

### Track B finish

#### W1 — `team_canonical` global lookup ✅ `v8.w1`
- `to_v4_canonical_global(name, global_pool)` — no league-hint variant;
  precedence: exact → normalized → CUP_TEAM_ALIASES → per-league walk
  → fuzzy
- `CUP_TEAM_ALIASES` (43 entries hand-curated from API-Football
  conventions for top European clubs)
- `build_global_team_pool(league_pools)` union helper
- `nutmeg-canonical-report-cup` diagnostic CLI — scans cup parquets,
  reports unmatched names so user can extend the alias map
- 24 new tests
- See [v8_w1_team_canonical_global.md](archive/v8/v8_w1_team_canonical_global.md)

#### W2 — Cup row UNION + `--with-cup-data` ✅ `v8.w2`
- `nutmeg.v4.data.cup_training.build_cup_training_rows` — cup_history
  × cup_odds → V4 MATCH_COLUMNS rows
- Pad strategy for 23-of-37 V4 cols cup data doesn't carry:
  shot stats / corners / cards → NaN; alt-book odds → psc proxy;
  Asian handicap → NaN
- `union_league_and_cup` concat + date-sort helper
- `nutmeg-train --with-cup-data` flag (independent of W7's
  `--with-cup-features` — data vs features)
- 20 new tests
- See [v8_w2_cup_data_union.md](archive/v8/v8_w2_cup_data_union.md)

#### W3 — Cross-league Elo/form seeding + ablation runner ✅ `v8.w3`
- `nutmeg.v4.features.cross_league_state` — `seed_elo_value` /
  `seed_form_deque` / `seed_form_last_date` mutating helpers
- `build_elo_features` + `build_form_features` + `build_feature_frame`
  + `WalkForwardConfig` all accept `cross_league_seed: bool = False`
  (default off, all V4-V7 tests unchanged)
- `nutmeg-train --with-cup-data` auto-enables seeding
- `nutmeg-cup-ablation` CLI — 4 cutoffs × 4 modes
  (baseline / cup_data / cup_features / cup_full) + automatic
  ship-gate verdict (≥ 3/4 folds improve ≥ −0.001 log-loss)
- 23 new tests
- See [v8_w3_cross_league_seeding_ablation.md](archive/v8/v8_w3_cross_league_seeding_ablation.md)

### Track B decision — data-gated

#### W4 — Cup-aware artifact ship decision ⏳
Code shipped through W3; the actual ablation run requires:
1. `nutmeg-ingest-cup-history --leagues UCL,UEL --seasons 2021,2022,2023,2024` (~8 calls)
2. `nutmeg-ingest-cup-odds    --leagues UCL,UEL --seasons 2021,2022,2023,2024` (~1320 calls)
3. `nutmeg-canonical-report-cup --show unmatched` → extend aliases as needed
4. `nutmeg-cup-ablation --out docs/v8_w3_cup_ablation_<date>.md`

Read the ship-gate verdict at the bottom of the card. Verdict actions:
- **Gate PASSED** (≥ 3/4 folds improve ≥ −0.001) → V9 W1: train + ship
  `data/v4_model_cat_cup/` as opt-in artifact
- **Gate NOT passed** → V9 W1: document negative result (mirror the
  `v6_w5_lineup_ablation.md` structure), freeze Track B

### Track A close — data-gated

#### W5 — Lineup-aware default flip ⏳
Once `nutmeg-ab-report --weeks 4` reports ≥ 30 settlements per slice
(local cron from V7 W2 + W3 has been running ≥ 4 weeks), read the
verdict per V6 W8 decision matrix:
- aware ≥ +5pp ROI → V9 W1 flip `NUTMEG_V4_ARTIFACT_PATH` to
  `data/v4_model_cat_lineups/`
- diff < ±2pp → keep V5 W12 default; document why backtest didn't
  translate
- free ≥ +5pp → investigate (cache freshness / overfit)

### Track D start

#### W6 — Dashboard 单关 + 复式 tabs ✅ `v8.w6`
- `POST /api/v4/recommend/single` → reuses V6 W9 `recommend_singles`
- `POST /api/v4/recommend/pool` → reuses V6 W3 `recommend_pool`
- 4 new Pydantic schemas + `Literal` enum validation on `pick`
- Dashboard restructure: 7 tabs (was 5); ① 单关 = new default landing
- Per-tab sample data buttons, bankroll / Kelly / mode-specific inputs
- 17 new tests
- See [v8_w6_dashboard_single_pool.md](archive/v8/v8_w6_dashboard_single_pool.md)

#### W7 — National-team Elo ✅ `v8.w7`
- `nutmeg.v4.data.national_team_elo` — mirror of per-club `clubelo.py`
- 68 nations registered (36 UEFA + 10 CONMEBOL + 6 CONCACAF + 7 AFC
  + 9 CAF) with per-country English / API-Football alias lists
- `fetch_nation_history(code)` — clubelo `/<NationCode>` CSV parser
  with tenacity retry; 404 → empty
- `build_nation_elo_lookup(cache_dir, as_of)` — interval-aware (picks
  row where `from_date ≤ as_of < to_date`); falls back to most-recent
  when stale
- `lookup_nation_elo(state, name)` — exact code → name alias → None
  (no fuzzy match; V4-era silent-wrong-join lesson)
- `nutmeg-ingest-national-elo` CLI — 250ms throttled; skip-cached;
  ~17 seconds for full 68-nation backfill
- 31 new tests
- Model integration (build_elo_features calling lookup_nation_elo for
  national_team_cup rows) deferred to V9
- See [v8_w7_national_team_elo.md](archive/v8/v8_w7_national_team_elo.md)

#### W8 — V8 ship ✅
- This document
- V8 retrospective (below in linked file)
- Tag: `v8.0-shipped`

## 5. Numbers (V7 → V8)

| Metric | V7 ship | V8 ship | Δ |
|---|---:|---:|---:|
| V4 tests passing | 598 | **713** | +115 |
| CLIs in `pyproject.toml` | 19 | **23** | +4 (canonical-report-cup, cup-ablation, ingest-national-elo, …) |
| API endpoints | 9 | **11** | +2 (recommend/single, recommend/pool) |
| Dashboard tabs | 5 | **7** | +2 (单关, 复式) |
| Cup data layers complete | 4 | **6** | +2 (team_canonical global, cup_training UNION, cross-league seeding) |
| Nations with Elo cached | 0 | **68** (registry; ingest pending user run) | + entire registry |
| Tracks shipped | C, B groundwork | + B finish (W1-W3), D start (W6-W7) | finish + 2 new |
| Lineup ROI verdict | pending | pending (still data-gated) | unchanged |
| Cup-aware artifact | not started | code ready, decision pending data | infrastructure complete |

### Backtest (unchanged from V5 W12 → V8 ship)

V8 didn't retrain; the production CatBoost artifact stays exactly where
V5 W12 left it. All new training paths (lineup-aware, cup-data,
cup-features, cross-league-seed) are opt-in.

| Cutoff | Pinnacle | LightGBM | CatBoost (current default) |
|--------|---------:|---------:|--------------------:|
| 22/23 | 0.9940 | 1.0020 | 0.9984 |
| 23/24 | 0.9865 | 0.9951 | 0.9898 |
| 24/25 | 0.9904 | 0.9971 | **0.9960** |

V8 W4 + W5 decisions are what would move these numbers (or document
why they can't).

## 6. V8 new CLIs

```
nutmeg-canonical-report-cup     (W1) Diagnose cup-team name resolution
nutmeg-cup-ablation             (W3) Multi-fold cup-data ablation runner
nutmeg-ingest-national-elo      (W7) Backfill clubelo nation Elo histories
```

Plus 3 new train flags (W2 + W3):
```
nutmeg-train --with-cup-data           Add cup ROWS to training frame
nutmeg-train --with-cup-features       Add cup feature COLUMNS (W7)
                                        (auto cross_league_seed when
                                         --with-cup-data is set)
nutmeg-train --cup-canonical-fuzzy     Fuzzy threshold for canonicalization
```

## 7. V8 new modules

```
nutmeg.v4.data.cup_training              (W2) cup parquets → V4 schema rows
nutmeg.v4.features.cross_league_state    (W3) seed_elo / seed_form helpers
nutmeg.v4.data.national_team_elo         (W7) clubelo nation Elo data layer
nutmeg.v4.cli.canonical_report_cup       (W1)
nutmeg.v4.cli.cup_ablation               (W3)
nutmeg.v4.cli.ingest_national_elo        (W7)
```

Modified for V8:
```
nutmeg.utils.team_canonical         (W1) +to_v4_canonical_global, +CUP_TEAM_ALIASES
nutmeg.v4.cli.train                 (W2,W3) +--with-cup-data, auto seeding
nutmeg.v4.features.elo              (W3) +cross_league_seed flag
nutmeg.v4.features.form             (W3) +cross_league_seed flag
nutmeg.v4.features.pipeline         (W3) +cross_league_seed passthrough
nutmeg.v4.eval.walk_forward         (W3) +cup_history_df + cross_league_seed
nutmeg.v4.api.routes                (W6) +recommend/single + recommend/pool
nutmeg.v4.api.schemas               (W6) +4 new request/response models
nutmeg.v4.api.static/dashboard.html (W6) tab restructure + 2 new panels
```

## 8. V9 backlog

### Data-gated decisions (V9 W1)

1. **Run cup ablation** — execute the 4-step workflow documented in
   §4 W4 above; read the verdict; ship `data/v4_model_cat_cup/` or
   document negative result
2. **Read lineup verdict** — once 4 weeks of cron data exist, run
   `nutmeg-ab-report --weeks 4`; promote default or document the
   backtest-vs-live gap

### Track D continuation

3. **National-team Elo model integration**: extend `build_elo_features`
   to call `lookup_nation_elo` when `competition_type_of(row.league)
   == "national_team_cup"`. Requires national-team fixture data in
   training set (currently zero — needs `nutmeg-ingest-cup-history`
   for WC / EURO codes)
4. **Cup-feature ablation REVISIT with seeding**: V8 W3 ships
   cross-league seeding but the auto-enable only fires for
   `--with-cup-data`. If the W4 ablation reveals data-only doesn't
   help but features+seeding does, that's a separate run

### P2 — stretch

5. **Multi-snapshot odds capture** for V5 W5's drift features
6. **Bayesian hierarchical** for small-sample leagues (still untested)
7. **Per-bucket Brier breakdown** investigating CatBoost ECE < Pinnacle
   but log-loss higher mystery
8. **Auto-rotate API token reminder** (cron hitting `/status`)
9. **CI fixture cache** for `--with-lineups` / `--with-cup-data` paths

## 9. Tests

**713/713 V4 tests passing** on `v8.0-shipped`:

```bash
PYTHONPATH=apps/api/src python -m pytest tests/v4/ -q
```

V8 added 5 new test files (115 tests):

| Module | Tests | Coverage |
|---|---:|---|
| `test_team_canonical_global.py` | 24 | global pool building, lookup precedence, diagnostic CLI |
| `test_cup_training.py` | 20 | cup-history × cup-odds → V4 schema, NaN/proxy padding, canonicalize drops, train flag |
| `test_cross_league_state.py` | 23 | seed_elo / seed_form / seed_last_date; integration with build_elo / build_form; cup_ablation modes + report |
| `test_recommend_single_pool_api.py` | 17 | new endpoints schema + 503 + E2E; dashboard regex checks |
| `test_national_team_elo.py` | 31 | 68-nation registry, CSV parser, parquet roundtrip, lookup, ingest CLI |

Plus the 598 V4-V7 tests, unchanged (1 V6 W10 test updated for the
renumbered rules tab — assertion loosened to just "规则说明").

## 10. Tags + milestones

| Tag | Date | Meaning |
|-----|------|---------|
| `v7.0-shipped` | 2026-05-24 | V7 closeout (entry point for V8) |
| `v8.w1` | 2026-05-24 | team_canonical global lookup |
| `v8.w2` | 2026-05-24 | cup row UNION |
| `v8.w3` | 2026-05-24 | cross-league seeding + ablation runner |
| `v8.w6` | 2026-05-24 | dashboard 单关 + 复式 |
| `v8.w7` | 2026-05-24 | national-team Elo |
| `v8.0-shipped` | 2026-05-24 | V8 complete |

(W4 and W5 are data-gated; no commits expected until V9 W1.)

The git log from `v7.0-shipped` to `v8.0-shipped` is the complete record
of how V8 unfolded.

---

**Welcome to V9.**
