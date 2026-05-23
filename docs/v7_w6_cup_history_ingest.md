# V7 W6 — Cup historical fixture backfill

_First piece of Track B (cup-trained model). V6 W11 shipped the cup
registry + side-channel feature columns; W6 starts populating the
training data those columns will eventually drive. **Pure data
plumbing — no model training yet.** V7 W7 wires the parquets into
`feature_columns_with_cup()` + multi-fold ablation; V7 W8 ships the
opt-in cup-aware artifact._

## What W6 ships

### 1. `nutmeg.v4.data.cup_history` module

Pure data layer. Public API:

| Function | Role |
|---|---|
| `normalize_fixture(api_fixture, league, season)` | API-Football envelope → V4-schema row dict (None when not finished / partial data) |
| `gather_cup_history_for_season(league, season, *, cache_dir, refresh)` | One season-wide `/fixtures` call → list of normalized rows |
| `write_cup_history_parquet(rows, out_path)` | Write to parquet with canonical `CUP_HISTORY_COLUMNS` schema |
| `cup_history_parquet_path(out_dir, league, season)` | Canonical filename: `<out_dir>/<league>_<season>.parquet` |
| `load_cup_history_parquet(path)` | Read back; empty schema-only DataFrame when file missing |
| `load_multi_season_cup_history(out_dir, leagues, seasons)` | Concat across (league × season) combos; date column parsed to datetime |
| `derive_round_flags(df)` | Append `is_knockout` int col via V6 W11's `is_knockout_round` |

Schema (`CUP_HISTORY_COLUMNS`):

```
date              YYYY-MM-DD (datetime after multi-season load)
league            UCL / UEL / UECL / FAC / ...
home_team         API-Football's name (matches V7 W1 ingest-odds output)
away_team         same
home_goals        int (only finished matches kept)
away_goals        int
status_short      FT / AET / PEN
round_label       "Group Stage - 3" / "Round of 16" / "Final"
api_football_id   int (for cache traceability)
season            int (start year, e.g. 2024 for 2024-25)
```

The FINISHED status filter is the same one V7 W2's `auto_settle` uses
(`FT/AET/PEN`). Postponed / cancelled / abandoned / live matches are
silently dropped — for training data we want only real final scores.

### 2. `nutmeg-ingest-cup-history` CLI

```bash
# Backfill 4 seasons of UCL + UEL
nutmeg-ingest-cup-history --leagues UCL,UEL --seasons 2021,2022,2023,2024

# Single-cup ingest
nutmeg-ingest-cup-history --leagues UCL --seasons 2024

# Domestic cups
nutmeg-ingest-cup-history \
  --leagues FAC,COPA_DEL_REY,COPPA_ITALIA,DFB_POKAL,COUPE_DE_FRANCE \
  --seasons 2023,2024
```

**Refuses non-cup league codes by default** (the `--allow-non-cup`
escape hatch exists for one-off domestic-cup ingests that aren't in
`CUP_COMPETITIONS` yet). EPL etc. have football-data.co.uk training
rows; the cup ingest path is for tournaments those CSVs don't cover.

Output:
```
data/external/cup_history/
  UCL_2021.parquet
  UCL_2022.parquet
  UCL_2023.parquet
  UCL_2024.parquet
  UEL_2021.parquet
  ...
```

**Budget**: One `/fixtures` call per (league, season). UCL + UEL × 4
seasons = 8 calls. All 12 cup competitions × 4 seasons = 48 calls. Pro
plan 7500/day → easy fit. Cached by (endpoint, params); re-runs cost 0
API budget.

## What W6 doesn't do

- **No model training.** Wiring the parquets into the training
  pipeline + multi-fold validation lives in V7 W7. W6 is the data
  layer only.
- **No lineup / injury data backfill for cup matches.** The existing
  `nutmeg-ingest-lineups` CLI works for cup codes today (V6 W11 merged
  cup IDs into `API_FOOTBALL_LEAGUE_IDS`), so once you've ingested
  fixtures via W6, you can call:
  ```
  nutmeg-ingest-lineups --league UCL --season 2024 --include-injuries
  ```
  The W6 parquets are independent of lineup data — only `is_cup_match`
  / `is_knockout` / `is_two_legged` / `is_national_team_match` /
  `competition_type_id` cup-features need fixture data, and those
  don't depend on lineups.
- **No team-name reconciliation across data sources.** API-Football
  uses "Real Madrid", football-data.co.uk uses "Real Madrid", but
  some teams differ ("Man United" vs "Manchester United"). The
  `utils.team_canonical` module from V5 W3 handles this for league
  data; cup-data join is V7 W7's problem when stitching cup rows into
  the V4 training set.
- **No GH Actions integration.** Backfill is a one-shot per release;
  no daily cron needed. Run locally when you want to refresh the
  cup-data cache for a new season.

## Tests

`tests/v4/test_cup_history.py` — 29 tests:

| Group | Coverage |
|---|---|
| `TestNormalizeFixture` (9) | Full payload extract; FT/AET/PEN kept (parametrized 6 non-finished skipped); missing goals / team names / round label; ISO date truncation; season coerced to int |
| `TestGatherForSeason` (1) | Mocked `_request`: filters to finished only (FT + PEN), single API call |
| `TestParquetRoundtrip` (4) | Write+load roundtrip; empty rows still produces valid empty parquet; missing-file load returns empty schema-only DF; canonical filename |
| `TestMultiSeasonConcat` (3) | Concat across leagues × seasons (date auto-parsed); missing combos silently skipped; empty directory |
| `TestDeriveRoundFlags` (1) | Integration with V6 W11's `is_knockout_round` — Group Stage → 0, R16 + Final → 1 |
| `TestCLI` (6) | Non-cup rejected by default; `--allow-non-cup` override; per-combo parquet writes; empty leagues / unparseable seasons → exit 2; multi-season writes separate files |

Full V4 suite: **559/559 passing** (530 prior + 29 new W6).

## Files touched in W6

```
apps/api/src/nutmeg/v4/data/cup_history.py        [+] data layer module
apps/api/src/nutmeg/v4/cli/ingest_cup_history.py  [+] CLI
pyproject.toml                                    [M] +nutmeg-ingest-cup-history
tests/v4/test_cup_history.py                      [+] 29 tests
docs/V7_ROADMAP.md                                [M] W6 ✅
docs/v7_w6_cup_history_ingest.md                  [+] (this file)
```

## Next: V7 W7 — wire cup parquets into the training pipeline

Steps for W7:
1. Extend `nutmeg.v4.features.pipeline.build_feature_frame` to optionally
   accept the cup-history DataFrame and append `round_label` →
   `derive_round_flags` → 5 W11 cup feature columns
2. New `feature_columns_with_cup()` returns
   `feature_columns_with_lineups() + CUP_FEATURE_COLUMNS`
3. `nutmeg-train --with-cup-features` flag (mirrors `--with-lineups`)
4. Multi-fold ablation: 4 cutoffs × {EPL+UCL pooled, ESP_LA_LIGA+UCL
   pooled, ITA_SERIE_A+UCL, all_clubs_pool} — same methodology that
   caught V6 W5's leak
5. If 3-of-4 folds improve by ≥ −0.001 log-loss → ship opt-in
   artifact in V7 W8

The V5/V6 multi-fold validation discipline applies fully — single-cutoff
positive signals don't ship without 3+ fold confirmation.
