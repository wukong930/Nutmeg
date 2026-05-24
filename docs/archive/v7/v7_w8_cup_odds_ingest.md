# V7 W8 — Cup historical odds backfill

_Last upstream piece of Track B. V7 W6 dropped cup fixtures + scores
onto disk; V7 W7 wired the side-channel feature columns through the
training pipeline. **V7 W8 closes the data gap**: per-fixture
Pinnacle (or sharp-book) closing odds for the same cup matches.
Joined with W6 fixtures via `merge_cup_fixtures_and_odds`, the
output is training-frame-shaped — ready for V8's cup-aware
artifact ablation + (potential) ship._

## What W8 ships

### 1. `nutmeg.v4.data.cup_odds` module

Pure data layer mirroring V7 W6's `cup_history` module so the two
parquet stores compose symmetrically.

| Function | Role |
|---|---|
| `normalize_odds_envelope(env, fixture_id, league, season, *, bookmaker_id)` | API-Football `/odds` envelope → cup-odds row dict (None when no Pinnacle quote) |
| `write_cup_odds_parquet(rows, out_path)` | Persist with `CUP_ODDS_COLUMNS` schema |
| `cup_odds_parquet_path(out_dir, league, season)` | Canonical name `<league>_<season>.parquet` (mirrors W6) |
| `load_cup_odds_parquet(path)` | Read back; empty schema-only when missing |
| `load_multi_season_cup_odds(out_dir, leagues, seasons)` | Concat across combos |
| `merge_cup_fixtures_and_odds(fixtures_df, odds_df, *, how="inner")` | Join W6 fixtures + W8 odds on `api_football_id`; produces the row shape `build_feature_frame(cup_history_df=...)` consumes |

Schema (`CUP_ODDS_COLUMNS`):

```
api_football_id   join key with cup_history
league            UCL / UEL / UECL / FAC / ...
season            season start year
bookmaker_id      which book this quote came from (Pinnacle = 4)
psc_home          1X2 home odds
psc_draw          1X2 draw odds
psc_away          1X2 away odds
psc_over25        O/U 2.5 over (None when book doesn't carry)
psc_under25       O/U 2.5 under
```

### 2. `nutmeg-ingest-cup-odds` CLI

```bash
# Backfill UCL + UEL 4 seasons of Pinnacle odds
nutmeg-ingest-cup-odds --leagues UCL,UEL --seasons 2021,2022,2023,2024

# Use Bet365 instead (id=8)
nutmeg-ingest-cup-odds --leagues UCL --seasons 2024 --bookmaker-id 8

# Custom paths
nutmeg-ingest-cup-odds --leagues UCL --seasons 2024 \
    --cup-history-dir my/fixtures \
    --out-dir my/odds
```

Pipeline:
1. Read W6 fixtures parquet → list of `api_football_id`
2. For each: `fetch_odds(fid)` (cached; re-runs free)
3. Parse via `odds_parser.extract_1x2_odds` + `extract_over_under_25`
4. Skip fixtures without the requested book's 1X2 quote (common
   for older qualifying matches; logged as "skipped, no quote")
5. Write per-(league, season) parquet
6. Per-combo summary table on stderr (kept / skipped counts)

**Budget**: ~1 `/odds` call per cup fixture. UCL 125 × 4 = 500;
UEL 205 × 4 = 820. Total ~1320 calls for a typical 4-season UCL+UEL
backfill. Pro plan 7500/day → fits comfortably. Cached, so re-runs
free.

**Prereq**: must run `nutmeg-ingest-cup-history` (V7 W6) first — the
fixtures parquet drives the loop. CLI logs a warning and writes an
empty parquet if the W6 parquet is missing (doesn't crash, lets the
user notice + run W6).

### 3. `merge_cup_fixtures_and_odds` — the bridge to V7 W7

```python
from nutmeg.v4.data.cup_history import load_multi_season_cup_history
from nutmeg.v4.data.cup_odds import (
    load_multi_season_cup_odds,
    merge_cup_fixtures_and_odds,
)
from nutmeg.v4.features.pipeline import build_feature_frame

fixtures = load_multi_season_cup_history(
    Path("data/external/cup_history"),
    leagues=["UCL", "UEL"], seasons=[2021, 2022, 2023, 2024],
)
odds = load_multi_season_cup_odds(
    Path("data/external/cup_odds"),
    leagues=["UCL", "UEL"], seasons=[2021, 2022, 2023, 2024],
)
cup_rows = merge_cup_fixtures_and_odds(fixtures, odds, how="inner")
# cup_rows now has: date / league / home_team / away_team / goals /
#                   round_label / psc_home/draw/away / psc_over25/under25
# Ready for build_feature_frame's domestic-rows + cup-rows union path
# (V8 deliverable).
```

Default `how="inner"` drops fixtures without odds — the right
default for training. Pass `how="left"` for diagnostic visibility on
"which fixtures have no quote".

## What W8 doesn't do

- **Doesn't UNION cup rows into the training frame.** V7 W7 ships the
  cup-feature wiring (`build_feature_frame(cup_history_df=...)`)
  but the actual training data still comes from
  `data/historical_sources/football_data_co_uk/`. Augmenting
  `load_all_matches` to also concat cup-data rows is a V8 task —
  the missing piece is `team_state` reconciliation (cup teams need
  Elo / form from their domestic-league context).
- **Doesn't extend `team_canonical`** for cup-specific name mismatches.
  API-Football and football-data.co.uk team names usually align, but
  edge cases ("Man United" vs "Manchester United") will appear when
  cup data joins league data. V8 task: scan + map.
- **Doesn't run the multi-fold ablation.** Same reason as W7 — needs
  the cup row union first. The 4-fold methodology is documented in
  v7_w7 and v6_w6; V8 executes.
- **Doesn't ship `data/v4_model_cat_cup/`.** V8 deliverable once the
  upstream is closed.

## Tests

`tests/v4/test_cup_odds.py` — 22 tests:

| Group | Coverage |
|---|---|
| `TestNormalizeOddsEnvelope` (5) | Full payload extract, no envelope → None, missing book → None, no O/U still keeps row with None cols, custom bookmaker_id recorded |
| `TestParquetRoundtrip` (4) | Write+load roundtrip, empty rows valid, missing-path empty load, canonical filename mirrors W6 |
| `TestMultiSeasonConcat` (3) | Concat across (leagues × seasons), missing combos skipped, empty dir |
| `TestMergeFixturesAndOdds` (3) | Inner join drops oddless fixtures, left join keeps all (with NaN odds), empty inputs return empty |
| `TestCLI` (7) | Non-cup rejected, happy path writes parquet, skips fixtures w/o quote, missing W6 parquet warns + continues, multi-combo writes separate files, empty/unparseable seasons → exit 2 |

Full V4 suite: **598/598 passing** (576 prior + 22 new W8).

## Files touched in W8

```
apps/api/src/nutmeg/v4/data/cup_odds.py             [+] data layer module
apps/api/src/nutmeg/v4/cli/ingest_cup_odds.py       [+] nutmeg-ingest-cup-odds
pyproject.toml                                      [M] +nutmeg-ingest-cup-odds
tests/v4/test_cup_odds.py                           [+] 22 tests
docs/V7_ROADMAP.md                                  [M] W8 ✅
docs/v7_w8_cup_odds_ingest.md                       [+] (this file)
```

## Track B status

| Week | Deliverable | Status |
|---|---|---|
| V6 W11 | Cup competition registry + 5 side-channel feature cols | ✅ |
| V7 W6 | `nutmeg-ingest-cup-history` (fixtures + scores) | ✅ |
| V7 W7 | `feature_columns_with_cup()` + `build_feature_frame` wiring | ✅ |
| **V7 W8** | **`nutmeg-ingest-cup-odds` (Pinnacle 1X2 + O/U)** | **✅** |
| V8 | Cup row UNION into training frame + team_canonical extension + multi-fold ablation + cup-aware artifact ship | future |

V7's Track B mission is "lay the groundwork for cup-trained
predictions." All four pieces of groundwork shipped (registry +
fixtures + features wiring + odds). What's missing for actual
training is the UPSTREAM bridge: making `nutmeg-train`'s
`load_all_matches` aware of cup row sources alongside the
football-data.co.uk CSVs. That's V8 territory.

## V7 status — feature work complete

| Track | Status |
|---|---|
| Track C (live odds + auto-settle + weekly bundle) | ✅ shipped |
| Track A (lineup-aware ROI verdict) | Pending data accumulation (4-week cron run) |
| Track B (cup-trained model groundwork) | ✅ all 4 pieces shipped (V6 W11 + V7 W6/W7/W8) |

Next: **V7 ship** — `V7_HANDOFF.md` + retrospective + `v7.0-shipped`
tag. The remaining code work in V7 (lineup-aware default flip, cup
union into training) is gated on data and a future iteration.
