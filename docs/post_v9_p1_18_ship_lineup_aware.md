# post-v9 P1#18 — Ship lineup-aware as production default

_The biggest model decision of the post-V9 cycle. V5 W12 set CatBoost
default; lineup-aware artifact has been opt-in since V6 W7 (≈18 months
ago). P1#17 backtest finally answered "is it worth flipping?" — yes,
by +20.48pp ROI over 35 weeks. P1#18 confirmed the signal is stable
across the season (3/3 sub-period chunks) and ships the flip._

## TL;DR

| Period | Default ROI | Lineup-aware ROI | Δ |
|---|---:|---:|---:|
| **Q1** Sep-Nov 24 (early season) | -2.58% | +13.39% | **+15.97pp** ✓ |
| **Q2** Dec-Feb 24-25 (mid season) | -28.53% | -3.53% | **+25.00pp** ✓ |
| **Q3** Mar-May 25 (late season) | -16.82% | +29.65% | **+46.47pp** ✓ |
| **All 35 weeks pooled** | -19.08% | +1.40% | **+20.48pp** |

**3/3 chunks pass — flip the default.** Default LOSES money in all
3 sub-periods of the 24/25 season. Lineup-aware is mean-positive +
beats default in every single chunk by 15-46pp.

## Why I flipped now (and not 4 months ago)

The V8 W5 ship-gate was "lineup-aware ROI verdict — pending real
data". I'd been treating that as a hard 4-6 week wait. P1#17 unlocked
it by realizing: historical CSVs (already in repo) + the same recommend
pipeline = a valid backtest if you respect training_cutoff. 30 minutes
instead of 4-6 weeks.

P1#17 alone wasn't enough to ship (V9 W5/W6 lesson: single-cutoff
verdicts can mislead — see ECE-vs-log-loss saga). P1#18 ran the same
backtest split into 3 within-season chunks. If the lineup-aware
advantage was 24/25-specific or chunk-specific, this would show. It
didn't — every chunk shows aware > default by a wide margin.

## Hit-rate diagnostics — not just luck

ROI alone is noisy. Hit-rate columns confirm the model is genuinely
predicting better, not just placing larger stakes:

| Chunk | Default predicted | Default actual | Aware predicted | Aware actual |
|---|---:|---:|---:|---:|
| Q1 | 14.97% | 14.14% | 19.61% | 18.25% |
| Q2 | 15.11% | **8.71%** | 18.98% | 15.40% |
| Q3 | 14.94% | 12.81% | 18.45% | 18.90% |
| All | 14.86% | 11.28% | 19.38% | 16.43% |

- **Default is systematically over-confident** (predicts ~15% hits,
  achieves ~11% on average; ~4pp gap)
- **Lineup-aware is also over-confident but less so** (~3pp gap), AND
  hits 5pp higher absolute rate
- Q2 is the worst stretch for both (Dec congestion + cup compresses fixture
  patterns), but lineup-aware still wins by +6.7pp actual hit-rate

## What changes (production-facing)

| Path | Before | After |
|---|---|---|
| `nutmeg-recommend --model` default | `data/v4_model` (V4 LightGBM) | `data/v4_model_cat_lineups` (V6 W7) |
| `nutmeg-recommend-pool --model` default | `data/v4_model_cat` (V5 W12) | `data/v4_model_cat_lineups` |
| `nutmeg-rec` interactive default | `data/v4_model_cat` (V5 W12) | `data/v4_model_cat_lineups` |
| `scripts/run_local_server.sh` env var | unset (API falls back to V4 LightGBM) | `NUTMEG_V4_ARTIFACT_PATH=data/v4_model_cat_lineups` |

What does NOT change:
- API server `DEFAULT_ARTIFACT_PATH` = `data/v4_model` (kept for test
  fixture compatibility; the LightGBM test artifact is what 90+ tests
  load against). Production sets `NUTMEG_V4_ARTIFACT_PATH` env to
  override, which `run_local_server.sh` now does automatically.
- Launchd `daily_recommend` job in `setup_local_pipeline.sh` —
  unchanged because it calls `nutmeg.v4.cli.recommend` which now
  defaults to lineup-aware via the CLI flip.

## Risks I'm explicitly accepting

1. **Backtest used Pinnacle closing odds, real bets use SP**.
   V5 W12 set ±4pp tolerance for the backtest-vs-live gap. Even if
   live underperforms backtest by 10pp, lineup-aware still beats
   default by 10pp.
2. **24/25 season only — 22/23 + 23/24 untested**. Can't backtest
   those without retraining the lineup-aware artifact (training_cutoff
   = 2024-08-01). The 3-chunk stability in 24/25 is the best
   substitute available. Multi-season backtest is a possible P1#19
   if user wants more confidence; would require ~hours to retrain
   on earlier cutoffs.
3. **Lineup data dependency**. Inference path checks for lineup
   lookup at predict time. If `data/api_football/lineups/*.json`
   cache is empty, the artifact silently falls back to zero
   injuries (per V6 W7 design) — the model becomes equivalent to
   default minus the lineup features. This is "safe failure mode"
   but should be monitored via daily cron logs.
4. **Default model isn't completely deprecated**. It still loads
   via `--model data/v4_model_cat` flag and via the API test fixture
   path. Just no longer the default. Future: V10 might cleanly
   delete `data/v4_model_cat` if multi-month live ROI confirms
   lineup-aware is strictly better.

## Verification plan (post-ship monitoring)

Daily cron is now (P1#16) actively accumulating REAL ROI data into
`data/v4_observation.db`. In ~4 weeks:

```bash
# Compare backtest-predicted vs live-actual ROI for lineup-aware
PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.ab_report \
    --weeks 4 --db data/v4_observation.db
```

If live ROI is within ±5pp of the backtest's +1.4% prediction →
verdict confirmed; ship was correct.

If live ROI is significantly worse (e.g. -10% absolute) → write
P1#19 retrospective; possibly revert default while investigating
backtest-vs-live gap (likely a market-price discrepancy: SP odds
not = Pinnacle closing the bot sees in the historical CSVs).

Post-P1#19 note: the direct gate now exists. Use
`nutmeg-live-vs-backtest --live-model-arm lineup_aware --roi-backtest-db
data/v4_observation_backtest.db --roi-backtest-arm lineup_aware` to compare
live lineup-aware results against the P1#17 ROI replay DB. See
[post_v9_p1_19_live_roi_backtest_gate.md](post_v9_p1_19_live_roi_backtest_gate.md).

## Files touched in P1#18

```
apps/api/src/nutmeg/v4/cli/recommend.py             [M] default → lineup-aware
apps/api/src/nutmeg/v4/cli/recommend_pool.py        [M] default → lineup-aware
apps/api/src/nutmeg/v4/cli/rec.py                   [M] 3 prompt defaults → lineup-aware
scripts/run_local_server.sh                         [M] +NUTMEG_V4_ARTIFACT_PATH default
docs/post_v9_p1_18_ship_lineup_aware.md             [+] this writeup
```

933 V4 tests still pass (no behavior change for tests; they pass
artifact paths explicitly).

## Implication for V10

V10 trigger #2 (lineup ROI verdict) was the most likely V10 starter.
**It's now answered (positive) and shipped**. So V10 starts only if:

1. Cup ablation triggers (data accumulation, ~6-9 months) — unchanged
2. Backtest-vs-live gap analysis shows backtest mis-predicted (post-P1#18
   verification) — would warrant a V10 to investigate the model further
3. New product gap surfaces (in-play / new market) — unchanged

Most likely V10 entry: scenario 1 (cup data accumulation), still in
~6-9 months. The post-v9 P1 chain has effectively answered the
biggest decision a V10 could have made.

## Decision audit trail

This is the most significant model production change since V5 W12
(2026-Q4 → 2024-Q1: 18 months of "lineup-aware is opt-in"). The
audit chain is:

- V6 W5 (lineup leak discovery + fix) → -0.0038 log-loss valid
- V6 W6 (multi-cutoff lineup ablation) → confirmed direction
- V6 W7 (trained the lineup-aware artifact, made it opt-in)
- V6 W8-W11 + V7 + V8 + V9 (kept it opt-in, gated on "real ROI data")
- post-v9 P1#16 (local pipeline finally accumulating real data)
- post-v9 P1#17 (backtest CLI; single 35-week verdict +20.48pp)
- post-v9 P1#18 (3-chunk stability verdict; SHIP)

Total elapsed: ~18 months of "code ready, waiting on data"; the data
was always available historically — I just needed to write the
backtest harness 30 minutes earlier.

Lesson for future: **when waiting on data feels permanent, check
if backtesting can substitute**. Walk-forward backtest answers the
same scientific question as live accumulation, faster and on more
samples, as long as the artifact cutoff is respected.
