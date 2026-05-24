# post-v9 P1#19 — Live ROI vs ROI-backtest gate

_First follow-up after P1#18 flipped production to the lineup-aware artifact._

## Goal

P1#18 shipped lineup-aware because the P1#17 historical ROI replay showed a
large edge over lineup-free. The next risk is not "can the model run?" but
"does live performance stay close to the historical replay once real
recommendations accumulate?"

P1#19 adds a direct gate for that question:

```bash
PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.live_vs_backtest \
  --db data/v4_observation.db \
  --weeks 4 \
  --live-model-arm lineup_aware \
  --roi-backtest-db data/v4_observation_backtest.db \
  --roi-backtest-arm lineup_aware \
  --out docs/weekly/<YYYY-Www>-lineup-live-vs-roi-backtest.md
```

The CLI exits:

| Exit | Meaning |
|---:|---|
| 0 | live ROI and hit-rate are within the 5pp tolerance |
| 1 | setup/input error |
| 2 | live-vs-reference gap exceeds tolerance |

## What changed

`nutmeg.v4.observation.live_vs_backtest` now supports:

- `model_arm` filtering on the live observation slice:
  `all`, `lineup_aware`, or `lineup_free`
- `roi_backtest_slice_from_db(...)`, which reads a DB produced by
  `nutmeg-roi-backtest` and turns the selected arm into a reference slice
- ROI gap comparison when the reference is an ROI replay DB
- existing walk-forward hit-rate comparison remains backward compatible

The HTTP endpoint also accepts `model_arm`, but it still does not run a
backtest inline. The CLI remains the quality-gate path.

## Why this matters

The old live-vs-backtest check compared live hit-rate to walk-forward model
hit-rate. That is useful, but it does not test the full recommendation stack:
selection, parlay construction, Kelly stake sizing, and settlement payout.

The ROI replay DB does test that stack. Comparing live lineup-aware results
against the P1#17 replay is the most direct guard after the production flip.

## Scope boundaries

This patch does not:

- change the production model
- change recommendation ranking
- fetch new data
- touch VPS deployment
- add automatic betting or profit guarantees

It only makes the post-P1#18 validation loop executable.

## Tests

New coverage in `tests/v4/test_live_vs_backtest.py`:

- live slice filtering by lineup-aware / lineup-free model arm
- ROI-backtest DB reference extraction
- ROI gap tolerance behavior
- markdown report rendering for ROI replay references

`tests/v4/test_observation_api.py` also covers the new `model_arm` query
parameter on the read-only observation endpoint.

## P1#22 amendment — cross-source caveat (5pp is not the right tolerance for cross-source)

After P1#21 documented that the **same model on the same fixtures**
can show a 30-50pp ROI gap purely because of bookmaker-snapshot
timing differences (football-data PSC vs The Odds API "Pinnacle"
historical snapshots), the 5pp default tolerance here needs a
caveat:

> **5pp is the right tolerance only when the live data source and
> the reference-backtest data source are the same.**

In production today they are NOT the same:

| Slot | Source |
|---|---|
| Live daily cron | API-Football `/odds` endpoint (snapshot ≈ 6h before kickoff) |
| P1#17/P1#18 backtest replay | football-data.co.uk PSC (snapshot ≈ at kickoff) |
| P1#21 cross-source backtest | The Odds API historical (snapshot at 23:00 UTC daily) |

The price-level gap between the three sources is enough on its own
to push the ROI gap past 5pp without any model-quality change. So
the gate will likely trigger `exit=2` even when the lineup-aware
model is performing exactly as expected — a false-positive class
this design didn't originally account for.

### How to read a real `exit=2` going forward

Three triage paths when the gate trips:

1. **Re-run with a "noise floor" tolerance** of ±50pp first. If it
   still trips, that's a real model/data issue worth investigating.
   If it doesn't, the trip was almost certainly cross-source noise.
   Shipped in P1#23 as a `--tolerance-pp N` flag (CLI) and a
   `tolerance_pp` query parameter (HTTP endpoint). Example:
   `nutmeg-live-vs-backtest --tolerance-pp 50 ...`
2. **Run a same-source apples-to-apples sub-check**: re-run the
   P1#21 cross-source backtest restricted to the same date window
   the live data covers. If the cross-source backtest's lineup-vs-
   default verdict still matches the live arm's measured P/L
   direction, the model is fine.
3. **Check hit-rate gap separately**. Hit-rate is less sensitive
   to bookmaker price differences than ROI is, because Kelly-stake
   sizing amplifies price differences. Hit-rate gap > 5pp is more
   likely to indicate a real model issue than ROI gap > 5pp alone.

### When the cross-source caveat dissolves

The clean fix is to **point the daily cron at the same source as
the validation backtest**. Two possible paths:

- **Path A (cheap)**: keep using API-Football for live odds; also
  backfill football-data.co.uk PSC values for the same fixtures
  post-hoc and store them alongside the recommendation; build a
  same-source `nutmeg-roi-backtest --odds-source football_data`
  parallel observation DB so the gate compares apples-to-apples.
- **Path B (cleanest, more work)**: switch the live cron to fetch
  closing prices from football-data's free historical CSVs after
  each match round; this loses real-time betting capability but
  makes the gate trustworthy. Probably not worth it for the
  current product shape.

Neither is urgent because the gate already runs and tests pass;
the action item is just "when reviewing a P1#19 alert, apply the
3-path triage above before concluding anything is broken."

### Document trail

- P1#17: built the historical replay tool (`docs/post_v9_p1_17_lineup_roi_backtest.md`)
- P1#18: shipped lineup-aware as default (`docs/post_v9_p1_18_ship_lineup_aware.md`)
- P1#19: this gate (above)
- P1#21: discovered the cross-source ROI gap is large
  (`docs/post_v9_p1_21_cross_source_backtest.md`)
- P1#22: this amendment
