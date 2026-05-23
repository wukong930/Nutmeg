# Nutmeg V7 Handoff

_Last updated: 2026-05-24 (V7 ship / `v7.0-shipped` tag)_

This document is the **single source of truth** for V7 — the 6-coding-
week sprint that closed V6's automation gaps and laid the groundwork
for V8's cup-trained model. Read this first when picking up the
project, then [V6_HANDOFF.md](V6_HANDOFF.md) for V6's product layer,
then [V5_HANDOFF.md](V5_HANDOFF.md) for the model + data plumbing V6
inherited, then [V4_HANDOFF.md](V4_HANDOFF.md) for the original V4
design.

---

## 1. What V7 was

V6 shipped the user-facing product (`nutmeg-rec`, 单关/串关/复式, China
lottery rules, Chinese dashboard, lineup-aware artifact, cup
registry). But the **daily user flow still had 5 manual steps** and
**three V6 verdicts were data-gated**:

- The lineup-aware artifact (V6 W7) needed 4 weeks of real-bet A/B
  data — V6 W8 shipped the cron infrastructure, but `record_outcome`
  was manual so the DB barely filled.
- The cup registry (V6 W11) had 5 side-channel feature columns but
  zero training data.
- The 4-week ROI verdict (V6 W8) couldn't close without auto-settle.

V7 (8 weeks planned, 6 coding weeks + 2 data-gated weeks) was
**operational**: close the automation loop, lay the data groundwork
for cup training, let the verdicts close themselves.

## 2. The three tracks

V7 ran in parallel tracks rather than sequential weeks, because
Track A is data-gated and shouldn't block Track B work:

| Track | Theme | Weeks | Status |
|---|---|---|---|
| **C** | 实时盘口 + auto-settle + 周报 (eliminate daily manual steps) | W1 → W3 | ✅ shipped |
| **A** | Lineup-aware ROI verdict (V6 W8 leftover) | W4 → W5 | ⏳ pending data (4-week cron run) |
| **B** | Cup-trained model groundwork | W6 → W8 | ✅ all 4 pieces shipped, V8 closes ablation |

Track C produced the immediate UX win (5 manual steps → 2). Track B
produced the multi-week foundation for cup ML. Track A is intentionally
patient — V5's pattern was "rush a verdict → ship a false positive";
V7 made the data-gathering machinery instead.

## 3. Production state today

| Layer | Default | Notes |
|---|---|---|
| Model backend | CatBoost (V5 W12 default) | Lineup-aware variant (V6 W7) opt-in; ROI verdict pending |
| Daily odds ingest | `nutmeg-ingest-odds` → CSV | Pinnacle 1X2 + O/U from API-Football; cached |
| Interactive entry | `nutmeg-rec --auto-fetch` | Skips manual CSV; runs odds ingest in-process |
| Daily settlement | `nutmeg-auto-settle` (local cron) | Pulls FT/AET/PEN results, upserts outcomes, calls `settle_unsettled` |
| Weekly reports | `nutmeg-weekly-report` (local cron) | Bundles `roi-report` + `ab-report` + `live-vs-backtest` into `docs/weekly/<YYYY-Www>-*.md` |
| GH Actions daily cron | 06:00 UTC heartbeat + odds CSV artifact | Refreshes lineup cache + uploads `_daily_odds_<date>.csv` |
| Cup history data | `data/external/cup_history/<league>_<season>.parquet` | UCL/UEL/FAC/COPA/COPPA/DFB/COUPE/WC/EURO/COPA_AMERICA/UECL/WC_QUAL_UEFA — fixtures + scores |
| Cup odds data | `data/external/cup_odds/<league>_<season>.parquet` | Pinnacle 1X2 + O/U for the same fixtures |
| Cup features | `feature_columns_with_cup(include_lineups=...)` | 5 side-channel cols; gated by `--with-cup-features` train flag |

## 4. What V7 shipped (week by week)

### Track C

#### W1 — `nutmeg-ingest-odds` + `nutmeg-rec --auto-fetch` ✅ `v7.w1`
- `data.odds_parser`: pure parsing for API-Football `/odds`; Pinnacle/
  Bet365/Unibet bookmaker constants
- `nutmeg-ingest-odds`: leagues × `/fixtures` × `/odds` → CSV in the
  shape recommend / rec expect. Cached → re-runs free
- `nutmeg-rec --auto-fetch`: skips the fixtures-path prompt; calls
  ingest in-process, writes temp CSV
- GH Actions daily cron extended: uploads `_daily_odds_<date>.csv`
- 22 new tests
- See [v7_w1_live_odds_ingest.md](v7_w1_live_odds_ingest.md)

#### W2 — `nutmeg-auto-settle` ✅ `v7.w2`
- `nutmeg-auto-settle`: walks leagues × past N days `/fixtures`,
  filters to FT/AET/PEN, upserts `match_outcomes`, runs
  `settle_unsettled`. Idempotent. `--dry-run` mode
- Strict status filter (no LIVE/PST/CANC fabrications)
- **Local-cron tool by design** — observation DB is user-local; GH
  Actions can't write to it
- 30 new tests
- See [v7_w2_auto_settle.md](v7_w2_auto_settle.md)

#### W3 — `nutmeg-weekly-report` (Track C closeout) ✅ `v7.w3`
- `nutmeg-weekly-report`: bundles `roi-report` + `ab-report` +
  `live-vs-backtest` into one call; outputs `<YYYY-Www>-{roi,ab,gap}.md`
- Exit code 2 propagates from `live-vs-backtest` when gap >
  tolerance — single hook for cron alerting
- ISO-week tag matches V5 W10 naming
- 10 new tests
- See [v7_w3_weekly_report.md](v7_w3_weekly_report.md)

### Track B

#### W6 — Cup historical fixtures → parquet ✅ `v7.w6`
- `data.cup_history` module: `normalize_fixture` (envelope → row),
  parquet roundtrip, `load_multi_season_cup_history`,
  `derive_round_flags`
- `nutmeg-ingest-cup-history` CLI: 1 `/fixtures` call per (league,
  season); refuses non-cup codes by default
- Output: `data/external/cup_history/<league>_<season>.parquet` with
  10-col schema (date, league, teams, goals, status, round_label,
  api_football_id, season)
- 29 new tests
- See [v7_w6_cup_history_ingest.md](v7_w6_cup_history_ingest.md)

#### W7 — `feature_columns_with_cup()` + pipeline wiring ✅ `v7.w7`
- `feature_columns_with_cup(include_lineups=False/True)` — cup wiring
  explicitly independent of lineup wiring
- `build_feature_frame(cup_history_df=...)` — left-joins round_label,
  appends 5 V6 W11 cup cols
- `nutmeg-train --with-cup-features` + `--cup-leagues` /
  `--cup-seasons` / `--cup-history-dir` flags
- Flag combination matrix:
  - neither → 39 cols (V5 W12 baseline)
  - `--with-lineups` → 41 cols
  - `--with-cup-features` → 44 cols
  - both → 46 cols
- 17 new tests
- See [v7_w7_cup_features_pipeline.md](v7_w7_cup_features_pipeline.md)

#### W8 — Cup historical odds backfill ✅ `v7.w8`
- `data.cup_odds` module mirroring W6: `normalize_odds_envelope`,
  parquet roundtrip, `load_multi_season_cup_odds`,
  `merge_cup_fixtures_and_odds` (inner/left)
- `nutmeg-ingest-cup-odds` CLI: reads W6 fixture IDs, calls `/odds`
  per fixture, writes per-(league, season) parquet with Pinnacle 1X2
  + O/U
- Budget: ~1320 calls for UCL+UEL × 4 seasons
- 22 new tests
- See [v7_w8_cup_odds_ingest.md](v7_w8_cup_odds_ingest.md)

### Track A — pending

#### W4 — 4-week ROI accumulation ⏳
Code already shipped (V6 W8 + V7 W1+W2+W3). The local cron does the
work; the user just waits.

#### W5 — Lineup-aware ROI decision ⏳
Once `nutmeg-ab-report --weeks 4` reports ≥ 30 settlements/side, read
the verdict per the V6 W8 decision matrix:
- aware ≥ +5pp → promote `data/v4_model_cat_lineups/` to default
- diff < ±2pp → keep V5 W12 default; document why backtest didn't
  translate
- free ≥ +5pp → investigate cache freshness / overfit
- < 30 either side → wait another week

## 5. Daily user flow (V6 → V7)

| Step | V6 ship | V7 ship |
|---|---|---|
| Morning: pull today's odds | Manually type fixtures CSV from lottery website | `nutmeg-rec --auto-fetch` ← runs ingest_odds in-process |
| Morning: see recommendations | `nutmeg-rec` (asks for CSV path) | Same; CSV step skipped |
| Matchday: place bets | Manual in lottery terminal | Same |
| Evening: record outcomes | `nutmeg-record-outcome` typed per match | Cron line at 03:00 (`nutmeg-auto-settle`) |
| Monday: ROI / A/B check | Manually run 3 CLIs | Cron line at Mon 04:00 (`nutmeg-weekly-report`) |
| **Steps requiring user attention** | **5** | **2** |

Recommended local crontab (`docs/v7_w3_weekly_report.md` has the full
recipe):

```cron
0 21 * * *  …refresh_lineups  --leagues EPL,ESP_LA_LIGA --days 3 --include-injuries
0  3 * * *  …auto_settle      --leagues EPL,ESP_LA_LIGA --db data/v4_observation.db --days 3
0  4 * * 1  …weekly_report    --db data/v4_observation.db --weeks 4 --backtest-cutoff 2024-08-01
```

## 6. Numbers

### Quantitative deltas

| Metric | V6 ship | V7 ship | Δ |
|---|---:|---:|---:|
| V4 tests passing | 468 | **598** | +130 |
| CLIs in `pyproject.toml` | 14 | **19** | +5 (ingest-odds, auto-settle, weekly-report, ingest-cup-history, ingest-cup-odds) |
| Daily manual user steps | 5 | **2** | -3 |
| Data sources backfilled | 0 cup | **2 cup** (history + odds) | +2 |
| Documented Track B groundwork pieces | 1 (V6 W11) | **4** (V6 W11 + V7 W6/W7/W8) | +3 |
| Live-data → A/B card latency | ≥ 1 week (manual) | **≤ 1 day** (cron) | -6 days |

### Backtest (unchanged from V5/V6)

V7 didn't retrain; the production CatBoost artifact stays exactly
where V5 W12 left it. The lineup-aware variant remains opt-in; the
cup-trained variant remains future work.

| Cutoff | Pinnacle | LightGBM | CatBoost (current default) | Δ (Cat − Pin) |
|--------|---------:|---------:|--------------------:|--------------:|
| 22/23 | 0.9940 | 1.0020 | 0.9984 | +0.0044 |
| 23/24 | 0.9865 | 0.9951 | 0.9898 | +0.0033 |
| 24/25 | 0.9904 | 0.9971 | 0.9960 | +0.0056 |

## 7. New CLIs (V7 additions)

```
nutmeg-ingest-odds         (V7 W1) Daily /odds → fixtures CSV
nutmeg-auto-settle         (V7 W2) Yesterday's results → observation DB
nutmeg-weekly-report       (V7 W3) ROI + A/B + gap → docs/weekly/
nutmeg-ingest-cup-history  (V7 W6) Cup /fixtures → parquet
nutmeg-ingest-cup-odds     (V7 W8) Cup /odds → parquet

nutmeg-rec --auto-fetch    (V7 W1) Wrapper flag, skips fixtures prompt
nutmeg-train --with-cup-features (V7 W7) Adds 5 cup cols to GBM input
```

Plus the 14 V6 CLIs (nutmeg-rec, nutmeg-recommend, nutmeg-recommend-pool,
nutmeg-record-outcome, nutmeg-roi-report, nutmeg-ab-report,
nutmeg-live-vs-backtest, nutmeg-ingest-lineups, nutmeg-refresh-lineups,
nutmeg-train, nutmeg-bench, nutmeg-bench-multi,
nutmeg-experiment-diff, nutmeg-ingest-external).

## 8. New modules (V7 additions)

```
nutmeg.v4.data.odds_parser         (W1) Pure /odds envelope parser
nutmeg.v4.data.cup_history         (W6) Cup fixture parquet store
nutmeg.v4.data.cup_odds            (W8) Cup odds parquet store
nutmeg.v4.cli.ingest_odds          (W1)
nutmeg.v4.cli.auto_settle          (W2)
nutmeg.v4.cli.weekly_report        (W3)
nutmeg.v4.cli.ingest_cup_history   (W6)
nutmeg.v4.cli.ingest_cup_odds      (W8)
```

Modified for V7:
```
nutmeg.v4.cli.rec               (W1) +--auto-fetch
nutmeg.v4.cli.train             (W7) +--with-cup-features + cup args
nutmeg.v4.features.pipeline     (W7) +feature_columns_with_cup, +cup_history_df arg
.github/workflows/daily-recommend.yml (W1) +ingest-odds step + odds artifact
```

## 9. V8 backlog

### Track A — close the lineup verdict (gated on 4 weeks of cron data)
Reading the W3 weekly cards. If aware ≥ +5pp: flip
`NUTMEG_V4_ARTIFACT_PATH` default. Code path already exists.

### Track B — finish cup-trained model
Three pieces remain:
1. **`team_canonical` cup extension**: scan W6+W8 parquets for team
   names not in the V5 W3 canonical map; backfill
2. **Cup row UNION into `load_all_matches`**: extend `nutmeg-train`'s
   data loader to optionally concat W6 fixtures × W8 odds + apply
   `lookup_cup_team_pair` for cross-league team_state lookups
3. **Multi-fold ablation**: 4 cutoffs × multi-league pools; ship
   gate ≥ 3/4 folds improve by ≥ −0.001 log-loss. Same methodology
   as V6 W6's `recent_n_injuries` verdict
4. (if 3 passes) Ship `data/v4_model_cat_cup/` opt-in artifact

Estimated 2-3 weeks.

### P2 — stretch / opportunistic

These don't gate Tracks A or B but ship value if cycles allow:

- **National-team Elo** via clubelo `/<NationCode>` endpoint. Unblocks
  WC / Euro / Copa America predictions (currently fall back to
  unknown-team path).
- **API token rotation reminder**: monthly cron hitting `/status` +
  warning when last-rotated > 90 days.
- **Web UI for `nutmeg-rec`**: form wrapping `/api/v4/recommend`,
  `/api/v4/rules`, `/api/v4/predictions/upcoming` for non-terminal
  users.
- **CI lineup-path fixture**: small EPL+La Liga lineup cache baked
  into the repo so GH Actions exercises `--with-lineups` (currently
  skipped when cache empty).
- **Dashboard 单关 / 复式 surfaces**: V6 W9 left these CLI-only.
  Adding a tab + UI for each would close the dashboard's product
  scope gap.

### From V6 backlog still relevant

- **Multi-snapshot odds capture** (T-2h, T-1h, T-30min, T-0min) to
  give V5 W5's market-dynamics features a fair shake. Needs a
  separate cron + storage layer.
- **Bayesian hierarchical for small-sample leagues**. V5 W7+ original
  plan, still untested.
- **CatBoost ECE 0.0120 < Pinnacle 0.0123 with log-loss still 0.0056
  higher** — investigate per-bucket Brier breakdown.

## 10. Tests

**598/598 V4 tests passing** on `v7.0-shipped`:

```bash
PYTHONPATH=apps/api/src python -m pytest tests/v4/ -q
```

V7 additions across 6 new test files:

| Module | Tests | Coverage |
|---|---:|---|
| `test_ingest_odds.py` | 22 | extract_1x2/OU25, fixture envelope → row, _gather_rows, CSV roundtrip |
| `test_auto_settle.py` | 30 | date range, finished-status filter (8 statuses parametrized), gather + API errors, DB end-to-end, dry-run, idempotency, partial settlement |
| `test_weekly_report.py` | 10 | ISO week tag, DB missing → exit 1, card content, paths-dict, exit-code propagation |
| `test_cup_history.py` | 29 | normalize_fixture (8 parametrized statuses), parquet roundtrip, multi-season concat, derive_round_flags, CLI |
| `test_cup_features_pipeline.py` | 17 | feature_columns_with_cup semantics, _merge_cup_round_labels, build_feature_frame integration, train CLI arg parsing |
| `test_cup_odds.py` | 22 | normalize_odds_envelope, parquet roundtrip, multi-season concat, merge_cup_fixtures_and_odds, CLI |

Plus the 468 V4–V6 tests, unchanged.

## 11. Tags + milestones

| Tag | Date | Meaning |
|-----|------|---------|
| `v6.0-shipped` | 2026-05-23 | V6 closeout (entry point for V7) |
| `v7.w1` | 2026-05-23 | nutmeg-ingest-odds + --auto-fetch |
| `v7.w2` | 2026-05-23 | nutmeg-auto-settle |
| `v7.w3` | 2026-05-24 | nutmeg-weekly-report (Track C closeout) |
| `v7.w6` | 2026-05-24 | Cup historical fixtures → parquet |
| `v7.w7` | 2026-05-24 | feature_columns_with_cup + pipeline wiring |
| `v7.w8` | 2026-05-24 | Cup historical odds backfill |
| `v7.0-shipped` | 2026-05-24 | V7 complete |

The git log from `v6.0-shipped` to `v7.0-shipped` is the complete
record of how V7 unfolded.

---

**Welcome to V8.**
