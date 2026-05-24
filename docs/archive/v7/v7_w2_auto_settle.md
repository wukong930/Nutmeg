# V7 W2 — `nutmeg-auto-settle`

_Closes the manual-input gap V6 W8's `nutmeg-record-outcome` left
open: pull yesterday's finished match scores from API-Football,
upsert into `match_outcomes`, run `settle_unsettled`. After W2 the
user's observation DB fills itself nightly — V6 W8's lineup-aware
ROI verdict can finally close after 4 weeks of accumulated data._

## What W2 ships

### 1. `nutmeg-auto-settle` CLI

```bash
# Most common: last 3 days, two leagues, write to local observation DB
nutmeg-auto-settle --leagues EPL,ESP_LA_LIGA \
    --db data/v4_observation.db --days 3

# Dry run: report what would happen without writing
nutmeg-auto-settle --leagues EPL --db data/v4_observation.db \
    --days 1 --dry-run

# Cup matches work too (V6 W11 cup IDs available via api_football)
nutmeg-auto-settle --leagues EPL,UCL --db data/v4_observation.db --days 7
```

Pipeline:
1. Walk `leagues × past N days`
2. `fetch_fixtures_for_date(d, league)` — cached, idempotent
3. Filter to `FINISHED_STATUSES = {"FT", "AET", "PEN"}`
4. Project to `(date, league, home, away, hg, ag)` rows
5. `upsert_outcome(...)` for each
6. `settle_unsettled(conn)` to close out pending parlays
7. Print summary

**Idempotent**: re-running the same window costs 0 settlements
(`upsert_outcome` overwrites with identical values; `settle_unsettled`
skips already-settled recs).

**Status filter is strict by design.** API-Football's "fixture is over"
codes are only `FT` / `AET` / `PEN`. Anything else
(`LIVE / 1H / HT / 2H / ET / P / BT / NS / PST / CANC / ABD / AWD / WO`)
gets skipped — settling against a postponed/cancelled match would
write a wrong outcome that's impossible to remove via the existing
unique constraint (and a partial live score is meaningless).

### 2. `--dry-run` mode

For verifying behavior on a fresh setup or before changing the
default leagues. Prints what would be upserted; writes nothing.
The cron recipe below uses `--dry-run` for the first daily firing
to surface mis-configurations before they pollute the DB.

### 3. Designed for local cron — NOT GH Actions

The observation DB is user-local (`data/v4_observation.db`, gitignored).
GH Actions can't write to it without committing the binary back, which
creates merge hell. **W2 is intentionally a local-cron tool.**
Example crontab line for a Linux/macOS user:

```cron
# Nightly auto-settle at 03:00 local time
0 3 * * * cd ~/Nutmeg && \
  /usr/bin/env PYTHONPATH=apps/api/src .venv/bin/python \
    -m nutmeg.v4.cli.auto_settle \
    --leagues EPL,ESP_LA_LIGA \
    --db data/v4_observation.db \
    --days 3 --quiet \
    >> /tmp/nutmeg-auto-settle.log 2>&1
```

GH Actions cron stays the data-freshness + odds canary it became in
V6 W8 + V7 W1.

### 4. Module API for tests + future reuse

The CLI is thin glue over three reusable functions in
`nutmeg.v4.cli.auto_settle`:

```python
_extract_outcome_rows(fixtures, league)        # pure parse
gather_finished_outcomes(leagues, start, end, *, cache_dir, refresh)
apply_outcomes(db_path, rows, *, dry_run)
```

A future "auto-settle inside the dashboard" feature would call these
directly without shelling out to the CLI.

## What W2 doesn't do

- **No live (in-progress) score capture.** Strict `FT/AET/PEN` filter
  means matches that finished but for which API-Football hasn't pushed
  the final status yet stay unsettled until the next run. Acceptable:
  API-Football usually updates status within minutes of the final
  whistle; the next-day cron always catches up.
- **No team-name normalization.** Match-id joins between
  `match_outcomes` and `parlay_recommendations.legs_json.match_id` rely
  on identical team strings. Since V7 W1's `nutmeg-ingest-odds` (which
  drives recommendations) AND W2's auto-settle BOTH read from
  API-Football, the names match by construction. If a user mixes
  V7-fed recommendations with hand-edited fixture CSVs containing
  different team-name spellings (e.g. "Man United" vs "Manchester
  United"), settlements won't join. Stick with the auto-fetched flow
  to avoid this.
- **No GH Actions integration.** The observation DB is local; the cron
  is local. The GH Actions daily-recommend.yml stays as a data-
  freshness canary.
- **No retro back-fill beyond `--days`.** The default 3-day window
  catches yesterday + 2 days of buffer. For a longer back-fill, pass
  `--days 30` (with `--refresh-fixtures` to bust any stale cache).

## Tests

`tests/v4/test_auto_settle.py` — 30 tests:

| Group | Coverage |
|---|---|
| `TestDateRange` (3) | Single-day, multi-day inclusive, end-before-start empty |
| `TestExtractOutcomeRows` (10) | FT/AET/PEN extract; 11 non-finished statuses skipped (parametrized); missing goals / partial goals / missing team names skipped; ISO date truncation; FINISHED_STATUSES constant |
| `TestGatherFinishedOutcomes` (2) | Mocked api_football: walks leagues × days correctly; one-day API error doesn't kill the rest |
| `TestApplyOutcomes` (5) | Writes outcomes + settles a real parlay; dry-run writes nothing; empty rows; idempotent re-run; partial settlement (one leg unknown) |

Full V4 suite: **520/520 passing** (490 prior + 30 new W2).

## Files touched in W2

```
apps/api/src/nutmeg/v4/cli/auto_settle.py     [+] nutmeg-auto-settle CLI
pyproject.toml                                [M] +nutmeg-auto-settle entry
tests/v4/test_auto_settle.py                  [+] 30 tests
docs/v7_w2_auto_settle.md                     [+] (this file)
docs/V7_ROADMAP.md                            [M] W2 ✅
```

## Recommended local crontab (with W1's odds ingest)

```cron
# ~21:00 local: refresh lineup + injury caches, pull tomorrow's odds
0 21 * * * cd ~/Nutmeg && \
  PYTHONPATH=apps/api/src .venv/bin/python \
    -m nutmeg.v4.cli.refresh_lineups \
    --leagues EPL,ESP_LA_LIGA --days 3 --include-injuries --quiet \
    >> /tmp/nutmeg-refresh.log 2>&1

# ~03:00 local: most matches done — auto-settle yesterday's results
0 3 * * * cd ~/Nutmeg && \
  PYTHONPATH=apps/api/src .venv/bin/python \
    -m nutmeg.v4.cli.auto_settle \
    --leagues EPL,ESP_LA_LIGA --db data/v4_observation.db --days 3 --quiet \
    >> /tmp/nutmeg-auto-settle.log 2>&1
```

With these two lines, the user's daily flow is:

1. (morning) Run `nutmeg-rec --auto-fetch` to see today's recommendations
2. (matchday) Place chosen bets in the 竞彩 terminal
3. (next morning) Optionally pull the ROI report — but the DB is
   already up to date from last night's auto-settle

## Next: V7 W3 — weekly ROI report cron

Extends `weekly-bench.yml` (V5 W10) to call `nutmeg-roi-report`,
`nutmeg-ab-report --weeks 4`, and `nutmeg-live-vs-backtest`. Commits
the resulting cards to `docs/weekly/`. With W1 (odds in) + W2
(outcomes in) + W3 (reports out), Track C is fully closed and the
lineup-aware ROI decision can be made on real, automated data.
