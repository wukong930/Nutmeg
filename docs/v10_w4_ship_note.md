# V10 W4 Ship Note — Pre-WC Infrastructure

_Shipped: 2026-05-25 (tag `v10.w4`, 17 days before 2026-06-11 kickoff)_

---

## TL;DR

V10 W4 is the **pre-WC prep** week. With W1-W3 already shipped (UX +
WC model + Layer A + integration), W4 builds the observability +
operations layer so the tournament window (2026-06-11 → 2026-07-19)
runs autonomously:

1. **WC predictions audit log** — `wc_predictions` SQLite table keyed
   by API-Football `fixture_id`. Every prediction the system produces
   (CLI or endpoint) lands here, then gets its outcome filled when the
   match completes.
2. **`nutmeg-wc-settle`** — pulls finished WC fixtures from API-Football
   and fills outcome columns. Idempotent; skips fixtures we never
   predicted.
3. **`nutmeg-wc-report`** — markdown summary of hit-rate, log-loss,
   confidence-bucket calibration. Per-match table for diagnostic
   review.
4. **2 new launchd jobs**: `daily_wc_predict` (09:00) + `daily_wc_settle`
   (02:00). 7 jobs total now (3 daily + 2 weekly + 2 WC daily).
5. **`scripts/wc_preflight.sh`** — single-command verification: API
   keys, fixture cache, Elo freshness, CLI works, endpoint OK,
   launchd loaded, DB schema. Exit 0/1/2 for ready / failed / warnings.
6. **V10 retrospective skeleton** committed so post-tournament
   write-up is just fill-in-the-blanks, not creative writing.

Three commits, ~830 lines of code, ~470 lines of docs/scripts, 30 new
tests. No new model logic.

---

## What shipped

### Day 1: WC predictions audit log + CLI --record-to

**New module** `apps/api/src/nutmeg/v4/observation/wc_log.py`:
- `wc_predictions` table schema (denormalized — Elo + odds inlined for
  one-stop replay)
- `ensure_wc_predictions_table(db)` — idempotent CREATE IF NOT EXISTS
- `record_wc_prediction(db, prediction, *, season)` — upsert on
  `fixture_id`. Re-running with fresher Pinnacle odds REPLACES, doesn't
  append.
- `settle_wc_prediction(db, fixture_id, *, home_goals, away_goals)` —
  computes `outcome` (0/1/2) and fills outcome columns
- `fetch_wc_predictions(db, *, season=None, settled_only=False)` —
  query helper with filter flags

**CLI extension** in `apps/api/src/nutmeg/v4/cli/wc_predict.py`:
- New `--record-to <db>` flag (V10 W4 Day 1)
- After JSON output, recorder runs in a try/except — DB failure does
  NOT fail the CLI (the JSON report is the user-facing artifact)

**Tests** (`tests/v4/test_wc_log.py` — 13 new):
- TestWcLogTable: ensure idempotency, write/read roundtrip, NULL
  extras_json when prediction has only known fields
- TestUpsertSemantics: re-record replaces prior row; separate
  fixture_ids → separate rows
- TestSettleSemantics: outcome calculation for H/D/A, returns False
  for unknown fixtures, re-settle overwrites
- TestFetchFilters: season + settled_only filtering
- TestCliRecordTo: happy path persists, recorder failure doesn't
  block JSON output

### Day 2: Settle + report CLIs + 2 launchd jobs

**`nutmeg-wc-settle`** (`apps/api/src/nutmeg/v4/cli/wc_settle.py`):
- Pulls fixtures from API-Football (cache-first via existing
  `fetch_fixtures_for_league_season`)
- Filter to FT / AET / PEN statuses (reuses `auto_settle` semantics)
- Upsert outcome columns. `--dry-run`, `--seasons`, `--refresh` flags.
- Exits 0 always (idempotent; safe in cron)

**`nutmeg-wc-report`** (`apps/api/src/nutmeg/v4/cli/wc_report.py`):
- Headline metrics: log-loss + hit-rate (with baselines: 33% random,
  ~50% Pinnacle-blended ceiling, >56% anomalously high)
- Calibration-bucket table: predicted confidence vs actual hit-rate
  per bucket (5 bins, only shown when n_settled ≥ 10)
- Per-match table sorted chronologically (date / teams / probs /
  tip / final / ✓ or ✗)
- Pending matches list at the bottom

**Tests** (`tests/v4/test_wc_settle_report.py` — 17 new):
- TestExtractFinishedRows: status filter, defensive skips for
  missing goals / fixture_id
- TestSettleCli: happy path, unknown fixtures skipped, dry-run,
  missing DB, bad seasons arg
- TestRenderMarkdown: empty rows, pending-only short-circuit,
  headline + calibration + settled/pending sections
- TestReportCli: writes to file, missing DB

**Launchd** (`scripts/setup_local_pipeline.sh` — 5 → 7 jobs):
- Job 6: `com.nutmeg.daily_wc_predict` Mon-Sun 09:00
  - Runs `nutmeg-wc-predict --date $(date +%Y-%m-%d) --fetch-current-odds
    --record-to data/v4_observation.db --out docs/wc/wc_YYYY-MM-DD.json`
- Job 7: `com.nutmeg.daily_wc_settle` Mon-Sun 02:00
  - Runs `nutmeg-wc-settle --db data/v4_observation.db` then
    `nutmeg-wc-report --season 2026 --out docs/wc/wc_report_YYYY-MM-DD.md`
- Daily timeline: 02:00 wc_settle → 03:00 calibration → 09:00 wc_predict → 14:00 odds → 15:00 recommend
- teardown + health_check updated to know about both new jobs

### Day 3: Preflight + retrospective skeleton

**`scripts/wc_preflight.sh`** — 7-check pre-kickoff verification:
1. `.env` has `NUTMEG_API_FOOTBALL_KEY` + `NUTMEG_ODDS_API_KEY`
2. WC 2026 fixture cache ≥64 entries
3. Eloratings.net snapshot < 14 days old (warn at 14-30d, fail >30d)
4. `nutmeg-wc-predict --date 2026-06-11` succeeds
5. `/api/v4/predictions/wc` endpoint returns ≥1 prediction
6. 3 critical launchd jobs loaded (`daily_wc_predict`, `daily_wc_settle`,
   `weekly_calibration_check`)
7. `wc_predictions` table accessible (or noted as "will be created on
   first cron run")

Exit codes: 0 ready / 1 failed / 2 warnings-only.

**Live preflight run today (2026-05-25):**
- ✅ API keys (both present)
- ✅ 72 WC 2026 fixtures cached (≥64 required)
- ✅ 244-nation Elo snapshot fresh (0 days old)
- ✅ CLI returns 1 prediction for the opener
- ✅ Endpoint returns matching prediction
- ⚠ 3 launchd jobs not loaded (expected — user runs setup on their box)
- • DB doesn't exist yet (expected — first cron run creates it)

→ Exit code 2 (READY WITH WARNINGS), as expected pre-installation.

**V10 retrospective skeleton** (`docs/v10_retrospective.md`):
- 8 sections (TL;DR / week-by-week / numbers / wins / surprises /
  prod state / V11 backlog / sign-off)
- Numbers tables include `{XX}` placeholders for post-WC fill-in
- Pre-WC candidate text for win / surprise sections, marked for
  refinement after tournament

---

## Test status

Pre-W4 (after W3): 1057 non-Playwright + 17 Playwright = 1074
**After W4: 1095/1095 V4 non-Playwright pass** (+30 from W4 + 9
Playwright still green = 1104 total).

| Test file | Count |
|---|---:|
| `test_wc_log.py` (W4 Day 1) | 13 |
| `test_wc_settle_report.py` (W4 Day 2) | 17 |
| **W4 total** | **30** |

(The "1108/1108" claim in an earlier draft of this ship note was
off-by-13; the correct authoritative count from
`pytest tests/v4/ --ignore=tests/v4/test_e2e_playwright.py` is **1095**.
Closeout audit reconciled.)

---

## Daily timeline post-installation

When the user runs `./scripts/setup_local_pipeline.sh`, the daily
launchd schedule looks like:

```
02:00  com.nutmeg.daily_wc_settle      → pull WC outcomes, write
                                          docs/wc/wc_report_YYYY-MM-DD.md
03:00  com.nutmeg.weekly_calibration_check (Mon only) → propose new T
                                          or auto-rollback
04:00  com.nutmeg.weekly_gate (Sun only)
09:00  com.nutmeg.daily_wc_predict     → predict today's WC matches,
                                          record_to observation DB,
                                          write docs/wc/wc_YYYY-MM-DD.json
14:00  com.nutmeg.daily_odds           → fetch domestic odds
15:00  com.nutmeg.daily_recommend      → generate recs + record session
```

Settle BEFORE predict (same day) means Layer A's weekly check on
Monday sees freshly-settled rows from the prior week.

---

## Commit + tag map

| Day | Commit | Title | LoC |
|----:|:-------|:------|----:|
| 1 | (this commit) | WC log table + CLI --record-to + tests | ~410 |
| 2 | (this commit) | settle + report CLIs + launchd + tests | ~580 |
| 3 | (this commit) | preflight + retrospective skeleton + ship note | ~430 |

**Tag:** `v10.w4` shipped 2026-05-25, **17 days before** WC kickoff.
That's the full slack budget on `v10.0-shipped` (target 2026-06-21).

---

## V10 status overview — all 4 weeks shipped

| Week | Target ship | Actual ship | Days ahead |
|------|:-----------:|:-----------:|:----------:|
| W0 — Launch | 2026-05-25 | 2026-05-25 | 0 |
| W1 — UX + WC model | 2026-05-31 | 2026-05-25 | 6 |
| W2 — Layer A | 2026-06-07 | 2026-05-25 | 13 |
| W3 — Integrate | 2026-06-10 | 2026-05-25 | 16 |
| W4 — Pre-WC infra | (was: WC live week) | 2026-05-25 | **17** |

**v10.0-shipped (target 2026-06-21)**: pending WC live tournament
completion. The remaining work is reactive monitoring during
2026-06-11 → 2026-07-19, not new code. V10 *engineering* is done.

---

## What's NOT in V10 W4

- **No dashboard changes.** WC tab still uses the V10 W1 Day 5
  implementation.
- **No tournament-specific model fixes.** If WC 2026 needs format-
  specific adjustment (e.g., 48-team novelty), that's V11.
- **No retrospective fill-in.** The skeleton is committed; numbers
  fill in post-tournament.

---

## V11 trigger condition (recap)

V11 starts when ≥ 1:
- WC verdict (2026-07-15 latest) shows model failed or succeeded
  meaningfully vs Pinnacle (informs next model investment)
- 4 weekly Layer A cycles produce a credible drift verdict
- Cross-source caveat resolved (live cron agrees with one of
  football-data / Odds API)
- New product surface from user

V11 trigger isn't pulled by reaching a calendar date — it's pulled
by **information landing** that V10's monitoring infrastructure
collects.

---

## File map (W4 additions)

| File | Action | Purpose |
|---|---|---|
| `apps/api/src/nutmeg/v4/observation/wc_log.py` | new | WC predictions audit-log table + ops |
| `apps/api/src/nutmeg/v4/cli/wc_predict.py` | edit | + `--record-to` flag |
| `apps/api/src/nutmeg/v4/cli/wc_settle.py` | new | `nutmeg-wc-settle` CLI |
| `apps/api/src/nutmeg/v4/cli/wc_report.py` | new | `nutmeg-wc-report` CLI |
| `pyproject.toml` | edit | + 2 new CLI entry points |
| `scripts/setup_local_pipeline.sh` | edit | + 2 launchd jobs (5 → 7) |
| `scripts/teardown_local_pipeline.sh` | edit | + 2 jobs in cleanup list |
| `scripts/health_check.sh` | edit | + 2 jobs in status check |
| `scripts/wc_preflight.sh` | new | 7-check pre-kickoff verification |
| `tests/v4/test_wc_log.py` | new | 13 tests |
| `tests/v4/test_wc_settle_report.py` | new | 17 tests |
| `docs/v10_retrospective.md` | new | post-WC retrospective skeleton |
| `docs/v10_w4_ship_note.md` | new | this file |
