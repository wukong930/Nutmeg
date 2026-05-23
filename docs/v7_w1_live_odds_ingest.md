# V7 W1 — `nutmeg-ingest-odds` + `nutmeg-rec --auto-fetch`

_The first piece of V7's Track C ("remove daily friction"). Until now
every recommend session needed a hand-typed fixtures CSV containing
date / league / teams / Pinnacle 1X2 odds for every match. The CSV
generation was the most error-prone manual step in the daily flow
(typo a team name → V4 doesn't recognize it → no recommendation).
W1 automates it._

## What W1 ships

### 1. `nutmeg.v4.data.odds_parser` (pure parsing module)

Decodes API-Football's `/odds` envelope shape into our CSV row dict.
Three public helpers:

- `extract_1x2_odds(envelope, bookmaker_id) → {"H","D","A"}` or None
- `extract_over_under_25(envelope, bookmaker_id) → (over, under)` or None
- `fixture_envelope_to_csv_row(fixture, envelope, league)` — combines a
  `/fixtures` record with its `/odds` envelope into one CSV row;
  returns None when the requested bookmaker doesn't quote 1X2

Bookmaker IDs constants:

| Const | Value | Bookmaker | Why default |
|---|---:|---|---|
| `PINNACLE_BOOKMAKER_ID` | 4 | Pinnacle | Sharpest book; V4/V5/V6 trained on Pinnacle closing as ground truth |
| `BET365_BOOKMAKER_ID` | 8 | Bet365 | Common public quote; fall-back when Pinnacle isn't carried |
| `UNIBET_BOOKMAKER_ID` | 16 | Unibet | Reserve |

Pure functions only — no IO, no API. All exercised by 14 unit tests.

### 2. `nutmeg-ingest-odds` CLI

```bash
# Today's EPL + La Liga to CSV
nutmeg-ingest-odds --leagues EPL,ESP_LA_LIGA --date 2025-08-17 \
  --out today.csv

# Pipe straight into recommend (stdout default)
nutmeg-ingest-odds --leagues EPL --date 2025-08-17 | \
  nutmeg-recommend --fixtures - --bankroll 1000

# Cup competitions work (V6 W11 cup IDs already merged into api_football)
nutmeg-ingest-odds --leagues UCL,EPL --date 2025-09-15
```

Pipeline per league:
1. `fetch_fixtures_for_date(date, league)` — 1 API call per league
2. For each fixture: `fetch_odds(fixture_id)` — 1 API call per fixture
3. For each (fixture, odds): `fixture_envelope_to_csv_row(...)`
4. Write all rows as CSV with the schema `nutmeg-recommend` /
   `nutmeg-rec` already understands

**Budget**: For EPL today (~10 matches) ≈ 11 API calls; for 13
leagues × ~5 matches/day ≈ 78 calls. Pro plan 7500/day → easy fit.
**Cached** by (endpoint, params) via the existing W1 cache layer →
re-runs the same day are free.

### 3. `daily-recommend.yml` cron extension

The V6 W8 daily heartbeat (`.github/workflows/daily-recommend.yml`)
now does **three** jobs:

1. (V6 W8) Refresh lineup + injury cache for past 3 days
2. (V7 W1) Pull today's `/odds` for `EPL,ESP_LA_LIGA` → CSV
3. Upload BOTH the daily summary JSON and the new odds CSV as a single
   GH Actions artifact (`daily-<YYYY-MM-DD>`, 14-day retention)

Workflow renamed: **Daily Lineup + Odds Refresh**.

### 4. `nutmeg-rec --auto-fetch`

The interactive entry from V6 W9 gains a switch that **calls
`ingest_odds` in-process before dispatching**:

```bash
# Interactive, no fixtures CSV typed
nutmeg-rec --auto-fetch --auto-fetch-leagues EPL,ESP_LA_LIGA
# Prompts only: type → bankroll → model. Skips the fixtures-path prompt
# because args.fixtures is set to a fresh temp CSV.

# Fully scripted (no prompts at all)
nutmeg-rec --type single --auto-fetch --bankroll 500 \
  --model data/v4_model_cat --out today/single.md
```

Auto-fetch is **disabled** for the `pool` (复式) flow because pool CSVs
require a per-row `pick` column the auto-fetcher can't infer from
odds alone. Pool users still pass an explicit `--fixtures`.

The temp CSV is written to a system tempfile (logged so user can
inspect: `[auto-fetch] 临时 CSV: /tmp/nutmeg_rec_xyz.csv`).

## What W1 doesn't do

- **No bet placement.** Same line as every V6 footer: 系统不进行自动
  投注. The CSV → recommend → terminal copy step is unchanged.
- **No lottery 让球 (handicap) odds.** API-Football carries Asian
  Handicap (fractional, e.g. -0.25) but the China lottery uses
  integer handicaps. They aren't directly comparable. The
  `handicap_home` + `odds_handicap_*` columns are left blank in the
  auto-generated CSV; the user fills these manually at bet time
  when they want the handicap market.
- **No multi-snapshot odds capture.** The cron fires once a day at
  06:00 UTC, after most matches have settled. For the
  V5 W5 "drift features" idea this isn't useful (already disproved
  on open/close pairs); for live closing-line capture we'd need a
  T-30min fire instead. Defer to a future enhancement.
- **No auto-settle.** Settling outcomes still requires
  `nutmeg-record-outcome` to be called by the user. **V7 W2 will fix
  this** and close Track C's automation loop fully.

## Tests

`tests/v4/test_ingest_odds.py` — 22 tests:

| Group | Coverage |
|---|---|
| `TestExtract1x2` (8) | Happy path, missing bookmaker, multi-book selection, partial outcomes, unparseable odds, odd ≤ 1.0 sentinel, extra value labels ignored |
| `TestExtractOU25` (3) | Happy path, only other lines present, missing bookmaker |
| `TestFixtureEnvelopeToRow` (4) | Full payload, no envelope, envelope without 1X2, partial w/o O/U |
| `TestGatherRows` (3) | Two leagues × 3 fixtures via mocked `fetch_fixtures_for_date` + `fetch_odds`, Pinnacle-not-quoted skip, empty `/odds` skip |
| `TestCsvWrite` (4) | pandas roundtrip, empty-rows header-only, write to file path, CSV_COLUMNS includes lottery blanks |

Full V4 suite: **490/490 passing** (468 prior + 22 new W1).

## Files touched in W1

```
apps/api/src/nutmeg/v4/data/odds_parser.py        [+] pure parsing module
apps/api/src/nutmeg/v4/cli/ingest_odds.py         [+] nutmeg-ingest-odds CLI
apps/api/src/nutmeg/v4/cli/rec.py                 [M] --auto-fetch + _auto_fetch_to_tempfile
.github/workflows/daily-recommend.yml             [M] +ingest-odds step + artifact rename
pyproject.toml                                    [M] +nutmeg-ingest-odds entry
tests/v4/test_ingest_odds.py                      [+] 22 tests
docs/V7_ROADMAP.md                                [+] V7 plan
docs/v7_w1_live_odds_ingest.md                    [+] (this file)
```

## Next: V7 W2 — `nutmeg-auto-settle`

Pulls yesterday's final scores from API-Football `/fixtures` (status
`FT|AET|PEN`), upserts into `match_outcomes`, calls `settle_unsettled`.
Wired into the daily GH Actions cron. After W2, the observation DB
fills itself daily without user intervention. After 4 weeks of
auto-fill, the V6 W8 lineup-aware ROI verdict can finally close.
