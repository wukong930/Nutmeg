# V5 W8 — Observation loop (real-bet ROI vs backtest)

_The infrastructure to confirm in real-bet conditions that the multi-season
backtest improvements (W4 +0.0016 log-loss, W6 CatBoost +0.0033) are actually
realized — and to detect leakage early when they're not._

## What's new

### Snapshot phases (schema v2)

`recommendation_sessions` now carries two new columns:

- `snapshot_phase` — `'pre_close'` (≥ 60 min before kickoff) / `'closing'`
  (legacy default, at closing-line publish) / `'post_close'` (diagnostic
  after-the-fact capture)
- `model_type` — `'lightgbm'` or `'catboost'`, lets us A/B the two backends
  side-by-side in the same DB without losing track

Pre-W8 v1 databases are auto-migrated on the next `open_db()`: `ALTER TABLE
ADD COLUMN` with defaults `'closing'` / `'lightgbm'` so existing observations
keep working unchanged.

### CLI: `nutmeg-recommend --snapshot-phase`

```bash
# 60 min before kickoff
nutmeg-recommend --fixtures today.csv --model data/v4_model \
  --snapshot-phase pre_close --record-to data/v4_observation.db

# At closing (default — back-compat)
nutmeg-recommend --fixtures today.csv --model data/v4_model \
  --snapshot-phase closing --record-to data/v4_observation.db
```

Recommended cadence: schedule `pre_close` at T−60 minutes (cron) and `closing`
~5 minutes before kickoff. Both sessions land in the same DB tagged
appropriately; the W8 analytics path can then compare them.

### CLI: `nutmeg-live-vs-backtest`

```bash
nutmeg-live-vs-backtest --db data/v4_observation.db --weeks 4 \
  --backtest-cutoff 2024-08-01 --out docs/weekly/$(date +%Y-W%V).md
```

Pulls the last 4 weeks of **settled** recommendations from the DB, computes
realized ROI + hit-rate, runs a walk-forward backtest with the same cutoff
to get the backtest hit-rate prediction, and reports:

- Live ROI / hit-rate (settled)
- Backtest hit-rate (from `gbm_dc_temp` summary)
- Gap (hit-rate, percentage points)
- Verdict: within ±5 pp tolerance → exit 0, otherwise exit 2

Exit code 2 is wired so a weekly cron can alert when something looks off.

Optional `--snapshot-phase pre_close|closing|post_close` restricts the live
slice to one phase, letting you ask "does the pre-close model match its
backtest worse than the closing one?" — useful when checking whether late
market info matters.

## Operations playbook

**Daily:**
1. Before kickoff: pull fixtures, train an up-to-date artifact if model needs
   refresh, run `recommend --snapshot-phase closing` with `--record-to`.
2. (Optional) ≥60 min before kickoff: same command with `--snapshot-phase pre_close`.

**Day-after:**
3. Enter results: `nutmeg-record-outcome --db ... --csv yesterday.csv`. This
   auto-settles all matching parlays via the legs JSON.

**Weekly (cron, Sunday 02:00 UTC):**
4. `nutmeg-roi-report --db data/v4_observation.db --out docs/weekly/$(date +%Y-W%V)-roi.md`
5. `nutmeg-live-vs-backtest --db ... --weeks 4 --backtest-cutoff 2024-08-01 \
       --out docs/weekly/$(date +%Y-W%V)-vsbacktest.md`
6. If exit code 2: investigate. Most likely causes (in order):
   - Lookahead leakage in a recently added feature
   - Market drift since training cutoff (retrain with newer data)
   - Small-sample noise (let it run another week before reacting)
   - Real model degradation (rare; check feature distributions)

## What W8 doesn't yet do

- **Stake-aware backtest ROI**. The backtest currently outputs log-loss /
  hit-rate; comparing live ROI requires re-running the same Kelly + stake
  logic against test-set fixtures. Tracked as W9 follow-up.
- **Per-phase delta**. `pre_close` vs `closing` same-fixture comparison is
  possible with the new schema, but the analytics aren't wired yet — also W9.
- **CatBoost A/B**. The schema supports it (`model_type` column); writing
  the dashboard to surface `lightgbm` vs `catboost` slices side-by-side is
  next on the W8 follow-up list.

## Tests

15 new unit tests in `tests/v4/test_live_vs_backtest.py`:
- Schema migration: v1 → v2 round-trip, idempotency, backfill defaults
- Session insertion with explicit / default phase, invalid phase rejected
- Window filtering by date + by phase
- ROI math (4 sessions × 2 recs each, deterministic hit pattern → ROI 25%)
- BacktestSlice construction from walk_forward pooled dict
- Gap computation: within / over (positive + negative) / no-backtest path
- Markdown report contains expected sections

Plus the existing 17 observation tests in `test_observation.py` and 12 in
`test_observation_api.py` still pass against the migrated schema, confirming
back-compat. Total V4 suite: **246/246 passing**.
