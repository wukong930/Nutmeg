# V10 W1 Track B Day 1 — WC data ingest

_Generated 2026-05-25. 1st operational day of V10. Track B = WC sprint
on a hard deadline (2026-06-11 WC kickoff = 17 days from V10 W0)._

## What landed today

### 1. Historical fixtures (API-Football) ✓

```
data/external/cup_history/WC_2018.parquet  → 64 fixtures (2018-06-14 → 2018-07-15)
data/external/cup_history/WC_2022.parquet  → 64 fixtures (2022-11-20 → 2022-12-18)
data/external/cup_history/WC_2026.parquet  → 0 finished (expected — tournament not started)
```

Cost: **3 API-Football calls** (1 per season).

Columns: date, league, home_team, away_team, home_goals, away_goals,
status_short, round_label.

### 2. Historical closing odds (Odds API) ✓ (partial)

```
data/external/cup_odds/WC_2022.parquet     → 63/64 fixtures matched (98%)
data/external/cup_odds/WC_2018.parquet     → 0 rows
```

**WC 2018 finding**: The Odds API historical depth starts mid-2020
(per their API docs). WC 2018 (June-July 2018) predates coverage —
confirmed empty. We have fixtures + results from API-Football, just
no closing-line backtest data.

**Mitigation**: Train on WC 2022 (64 matches w/ odds) only. Use WC
2018 as "out-of-sample sanity check" without odds-based ROI scoring.

Cost: **11 calls × 10 quota = 110 quota** (0.55% of monthly 20k).

Bookmaker fallback: defaults to first available EU book per snapshot
(strict-Pinnacle filter NOT used since cup-mode prioritizes match
coverage over apples-to-apples pricing).

### 3. 2026 WC upcoming fixtures (API-Football, cached side effect) ✓

While running the 2026 season query (returned 0 finished as expected),
the API also gave us **72 NS (Not Started)** fixtures spanning
2026-06-11 → 2026-06-28 (group stage + first knockouts).

First match: **Mexico vs South Africa, 2026-06-11 19:00 UTC** (likely opener at Estadio Azteca).

Confirms 2026 is a 48-team WC (vs the 32-team 2018/2022 format), with
72 listed matches so far (probably partial — knockout brackets fill in
as group stage progresses).

### 4. National-team Elo (clubelo) ⚠️ BLOCKED

```
data/external/clubelo_national/  → empty
```

`api.clubelo.com` returned **502 Bad Gateway for all 69 nations**.
External service down. No fix on our end.

**Mitigation**: Retry tomorrow (Day 2). If still down, fall back to:
1. Use static Elo snapshot from a different source (FIFA rankings;
   eloratings.net scrape; football-data.org)
2. Compute team strength purely from WC 2022 match results + Pinnacle
   prior — not as good but workable for 64-match training set

## Quota balance after Day 1

| Source | Used today | Monthly budget | Remaining |
|---|---:|---:|---:|
| API-Football | ~4 calls | ~100/day | n/a (rate-limit-bound, not budget-bound) |
| The Odds API | 110 quota | 20,000 | **13,240** (99.4% spare for WC W2-W4) |

Well within budget.

## Per-team coverage in WC 2022 (32 nations)

```
Argentina, Australia, Belgium, Brazil, Cameroon, Canada, Costa Rica,
Croatia, Denmark, Ecuador, England, France, Germany, Ghana, Iran,
Japan, Mexico, Morocco, Netherlands, Poland, Portugal, Qatar,
Saudi Arabia, Senegal, Serbia, South Korea, Spain, Switzerland,
Tunisia, USA, Uruguay, Wales
```

All 32 from WC 2022 are in the registry. 2026 expansion to 48 brings in
~16 new nations — most should be covered by the existing 68-nation
registry but should be checked Day 2 (once clubelo is back up).

## Data quality notes

- **Odds match rate 98% (63/64)**: 1 fixture missing. Probably the
  third-place playoff or a coverage gap in Odds API at that exact
  snapshot. Worth identifying in Day 2 but not blocking.
- **Team names in odds parquet are null**: this is by design — the
  Odds API ingest joins to fixtures via `api_football_id` at training
  time, not by name string match. Names live in the fixtures parquet.
- **`bookmaker` column is null**: also by design — `bookmaker_id` is
  cached as int instead. Will resolve to specific book name at training
  time via the standard `bookmaker_id → bookmaker_name` lookup.

## Day 2 plan

1. Retry `nutmeg-ingest-national-elo` (clubelo recovery check)
2. If clubelo still down: pick a fallback Elo source (FIFA / eloratings.net)
3. Verify 2026 WC fixtures: are all 48 confirmed teams in 72 NS
   fixtures? Any drop-out / qualifier-pending matches?
4. Begin Day 2 of Track B Week 1: build the join layer
   (`fixtures + odds + elo`) into a training frame for WC 2022

## Day 1 verdict

✓ **WC 2022 ready for training** (64 matches, 63 with odds, 32 teams).
⚠️ Elo data blocked by external 502 — will retry Day 2.
✓ 2026 schedule is in our hands (72 NS fixtures cached).
✓ Quota usage minimal (110/20,000 = 0.55%).

Track B is on schedule for V10 W1 target ship 2026-05-31.
