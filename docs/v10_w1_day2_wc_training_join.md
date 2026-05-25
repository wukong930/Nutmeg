# V10 W1 Track B Day 2 — clubelo failure + eloratings.net fallback + WC training join

_Generated 2026-05-25. Continues from Day 1 (WC fixtures + odds ingested).
Today: solve the Elo blocker, build the training data join._

## Discovery — clubelo's `/<NationCode>` endpoint is empty

Day 1 left an external 502 from `api.clubelo.com`. Retried today:

| Request | Response |
|---|---|
| `GET http://api.clubelo.com/ENG` | HTTP 200, **empty data** (CSV header only) |
| `GET http://api.clubelo.com/Argentina` | HTTP 200, empty |
| All 69 nations | `ok=0, empty=69, failed=0` |

**Root cause**: `/<NationCode>` is a **CLUB FILTER**, not a national-team
Elo endpoint. ENG returns "clubs in England" (Liverpool, Arsenal etc.)
when used as a date-suffix call (e.g., `/2025-05-25` works); using it
as `/ENG` returns nothing because `ENG` is being parsed as a date.

**P1#10's "verification"** confirmed HTTP 200; it didn't verify the
payload had national-team rows. The lesson: validation checks must
include "is the data USEFUL", not just "did the endpoint respond".

## Fallback — eloratings.net

`https://www.eloratings.net/World.tsv` is the canonical international-
football Elo source. TSV format, no auth, public:

```
rank  ?  code  current_elo  ?  prev_elo  ...
1     1  ES    2165         1  2189      (Spain)
2     2  AR    2113         1  2172      (Argentina)
3     3  FR    2081         1  2135      (France)
4     4  EN    2020         1  2213      (England)
5     5  BR    1984         1  2195      (Brazil)
```

**244 nations** in the feed (way more than we need).

Action: ad-hoc scraper saves to
`data/external/eloratings/eloratings_<date>.parquet` (~7KB). Not yet
a CLI / cron — V10 W1 only needs one snapshot.

## Coverage check — WC 2026 48 teams

| Status | Count |
|---|---:|
| WC 2026 participating teams (from API-Football cache) | 48 |
| Mappable to eloratings code | **48 ✓** |
| Missing | 0 |

Top 10 by Elo at V10 W1 W0:
```
1   Spain          2165
2   Argentina      2113
3   France         2081
4   England        2020
5   Brazil         1984
5   Portugal       1984    (tie)
7   Colombia       1975
8   Netherlands    1961
9   Ecuador        1933
10  Croatia        1930
```

Bottom 5 in WC 2026:
```
77  Haiti          1532
79  South Africa   1524
82  Ghana          1503
90  Curaçao        1436
95  Qatar          1425
```

## Mapping module: `nutmeg.v4.data.national_team_name_to_elo`

API-Football names → eloratings 2-letter codes. Edge cases worth
calling out:

| API-Football name | eloratings code | Why |
|---|---|---|
| `Scotland` | `SQ` | `SC` is Seychelles in eloratings (P1#10 latent trap) |
| `Türkiye` | `TR` | API-Football uses Turkish official; alias `Turkey → TR` kept |
| `Wales` | `WA` | Not `WL` |
| `Bosnia & Herzegovina` | `BA` | Note ampersand |
| `Congo DR` | `CD` | Democratic Republic of Congo (not the Republic of Congo `CG`) |

Total entries: 52 (48 from WC 2026 + 4 from WC 2018 only: Russia, Peru,
Iceland, Nigeria).

## Training join — `nutmeg.v4.data.wc_training_frame`

`build_wc_training_frame(season=2022)` returns a flat DataFrame:

```
date         | league | season | home_team | away_team | home_goals | away_goals
| home_elo | away_elo | elo_diff | home_elo_rank | away_elo_rank
| psc_home | psc_draw | psc_away | api_football_id | status_short | round_label
```

Joins 3 sources:
1. `data/external/cup_history/WC_{season}.parquet` (V7 W6 ingest, has results)
2. `data/external/cup_odds/WC_{season}.parquet` (P1#20 ingest, may be empty pre-2020)
3. `data/external/eloratings/eloratings_*.parquet` (this Day 2)

Defensive defaults:
- Missing odds parquet → `psc_*` columns all NaN (workable for 2018)
- Missing team in Elo map → Elo cols None (model layer Day 3 handles)
- Missing fixtures parquet → `FileNotFoundError` with `nutmeg-ingest-cup-history` hint

## Verification — coverage results

After fixing 4 historical-team mappings (RU/PE/IS/NG):

| Season | Total fixtures | Both Elos | With odds | With results |
|---|---:|---:|---:|---:|
| WC 2018 | 64 | **64/64 ✓** | 0/64 (Odds API pre-2020 gap) | 64/64 |
| WC 2022 | 64 | **64/64 ✓** | 63/64 (98%) | 64/64 |
| **Combined** | **128** | **128/128 ✓** | **63/128** | **128/128** |

**Best-quality training rows (Elo + odds + result): 63.**
**Full training rows (Elo + result, no odds): 128.**

Day 3 model decision: train two models on different subsets.
- Elo-only model on 128 rows (broader, no market signal)
- Elo + market-blend model on 63 rows (smaller, includes Pinnacle)
- Ensemble at predict time

## Tests

10 new tests in `tests/v4/test_wc_training_frame.py`:

- **TestNameToEloCode** (5): top-teams covered, Scotland=SQ trap,
  Türkiye/Turkey aliasing, unknown returns None, all 48 WC 2026
  teams mappable
- **TestBuildWcTrainingFrameIntegration** (3, skipif data missing):
  full WC 2022 coverage, elo_diff math, column ordering
- **TestLoadEloSnapshot** (1, skipif): basic shape
- **TestMissingFixtures** (1): defensive FileNotFoundError

All pass: 10/10. Integration tests gracefully skip if local data
isn't ingested.

## Updated quota balance

| Source | Day 2 usage | Cumulative day 1+2 | Monthly budget |
|---|---:|---:|---:|
| API-Football | 0 (clubelo only this morning) | ~4 | rate-limit not budget |
| The Odds API | 0 | 110 | 20,000 (still 99.5% spare) |
| Eloratings.net | 1 TSV scrape, ~5KB | — | unlimited public |

## Files this session

```
apps/api/src/nutmeg/v4/data/national_team_name_to_elo.py       [+] mapping (52 entries)
apps/api/src/nutmeg/v4/data/wc_training_frame.py               [+] join builder
tests/v4/test_wc_training_frame.py                              [+] 10 tests
data/external/eloratings/eloratings_2026-05-25.parquet         [+ local, gitignored]
docs/v10_w1_day2_wc_training_join.md                            [+] this writeup
```

## Tomorrow — Day 3 plan

Day 3 + 4 of Track B = WC model build:

1. **`nutmeg.v4.model.national_team_predict` module** (Day 3-4)
   - Architecture: LightGBM with 4-6 features (elo_diff, log market
     prob if available, recent international form ±n matches, home_adv)
   - Train on WC 2022's 63-rows-with-odds set; test on remainder
   - Walk-forward: train 2018 → predict 2022 (small but real)
   - Target: log-loss ≤ 1.00 (Pinnacle WC ≈ 0.97)

2. **Pinnacle Bayesian blend fallback** (Day 4)
   - If model log-loss > 1.00, ship blend: `0.6 * model + 0.4 * market`
   - Per Q1 discussion this is "cheating" but acceptable for V10
     proof-of-concept

3. **Dashboard "WC 预测" tab** (Day 5)
   - New endpoint `GET /v4/predictions/wc?date=2026-06-11`
   - Returns upcoming WC fixtures with model probabilities
   - Dashboard tab feeds from it

W1 ship target: 2026-05-31. Currently 2/5 days into Track B; on schedule.
