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
