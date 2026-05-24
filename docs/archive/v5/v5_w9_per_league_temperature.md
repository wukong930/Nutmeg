# V5 W9 — Per-league temperature ablation

_Negative result on our current val-window size. Module retained as
infrastructure for when val windows grow large enough to support it._

## What we tried

Replace the single global temperature T in V4's calibration step with a
per-league dictionary: for each league with ≥ `min_samples` validation
matches, fit a dedicated T; for the rest, fall back to a global T fit on
the pooled validation set.

The rationale (and what the original V5 plan §模型升级 W7 anticipated):
EPL closing markets are sharper than J1 closing markets, smaller leagues
benefit from less aggressive sharpening, and one global T can't capture
those differences.

## Result

Multi-season GBM+DC log-loss + ECE, comparing global T (W4 default) vs
per-league T (with `min_samples=30` — the absolute floor `fit_temperature_1x2`
itself allows):

|        | Pinnacle | Global T   | Per-league T | Δ log-loss | Δ ECE   | Leagues fit |
|--------|---------:|-----------:|-------------:|-----------:|--------:|------------:|
| 22/23  | 0.9940   | 1.0020 / 0.0113 | 1.0049 / 0.0090 | **+0.0029** | −0.0023 | 6 |
| 23/24  | 0.9865   | 0.9951 / 0.0130 | 1.0061 / 0.0212 | **+0.0110** | +0.0082 | 11 |
| 24/25  | 0.9904   | 0.9971 / 0.0185 | 1.0011 / 0.0134 | **+0.0041** | −0.0051 | 3 |

Per-league T makes **log-loss worse in every season** (+0.0029 to +0.0110).
ECE improves in 2/3 seasons but worsens dramatically in 23/24 (where it
fitted the most leagues — 11/13).

## Why it fails on our data

The 90-day validation window leaves only ~30–50 GBM-eligible matches per
league per fold (vs the 800-sample theoretical sweet spot). With that few
samples, per-league T overfits the validation set:

- 23/24's catastrophic +0.0110 regression came with **11 leagues fitted**,
  meaning 11 extra parameters tuned on a pooled val of ~500 matches.
- 24/25's smaller +0.0041 regression only fitted **3 leagues** (the rest
  fell back to global), limiting the damage.

This is the same pattern as the W5 market-dynamics features and W6
LogisticRegression stacker: more parameters + small validation pool +
correlated features → validation overfit → test-set regression.

## Decision

1. **Roll back per-league T from the production training path.**
   `nutmeg.v4.cli.train` continues to use the global `fit_temperature_1x2`
   (default).
2. **Keep `nutmeg.v4.calibration.per_league.py` in the codebase.** The
   module is fully tested (9 unit tests) and integrated into walk_forward,
   which now reports `gbm_dc_pl_temp` as an additional row in the benchmark
   card. It's available behind no flag — just unused by default in the
   chosen production calibrator.
3. **Re-enable threshold guidance:** in `walk_forward.py` the integration
   uses `min_samples=30` so the diagnostic always emits numbers; the
   default `DEFAULT_MIN_SAMPLES_PER_LEAGUE=800` in `per_league.py` itself
   stays at 800 to reflect the safe threshold for future use when val
   windows expand.
4. **When to revisit:** when production val windows grow to ≥ 800
   matches/league (≈ 540 days of pooled history per league), the
   per-league fit should empirically beat global. Track that on the
   weekly cron `nutmeg-bench` card — the `gbm_dc_pl_temp` row will start
   beating `gbm_dc_temp` when this transition happens.

## Why this is W9 complete

- Built and unit-tested the per-league calibrator with explicit
  fallback semantics (`fit_per_league_temperature` + `PerLeagueTemperatureCalibrator`)
- Wired it into walk_forward / multi_season so the diagnostic data is
  visible on every bench run (no flag needed)
- Discovered, in a falsifiable head-to-head, that 90-day val windows are
  too small to support per-league fits without overfitting — same pattern
  as W5 / W6 stacker, ruled out a class of approaches at the current scale
- Documented the threshold (800/league) at which we'd expect this to flip,
  so the next iteration knows what to watch for

## Stack-up: W9 + previous results

|     | Strategy | Verdict |
|-----|----------|---------|
| W4 ✅ | xG-lite + clubelo features | Production win, multi-season |
| W5 ⚠️ | Market-dynamics drift | Negative, rolled back |
| W6 ⚠️ | LogReg ensemble stacker | Negative, rolled back |
| W6 ✅ | CatBoost single model (vs LightGBM) | Positive, scheduled for prod default in W7 |
| W7 ✅ | CatBoost prod migration (opt-in) | Available behind `--model cat` |
| W8 ✅ | Observation loop + snapshot phases | Production observability ready |
| W9 ⚠️ | Per-league temperature | Negative on current val window, infrastructure kept |

Two genuine positive findings (W4 features, W6 CatBoost) + three documented
negatives (W5, W6 stacker, W9). The negatives are valuable: they rule out
methods that look attractive on paper but don't survive multi-season
validation, sparing future iterations from rediscovering them.

## Tests

9 unit tests in `tests/v4/test_per_league_temperature.py`:
- Fit returns calibrator with per-league + global entries
- Below-threshold leagues fall back to global (3 leagues, 1 qualifies)
- Length-mismatch raises at fit and at predict
- Predict routes each row to its league's T (different leagues → different
  post-calibration probabilities for same raw input)
- Unknown league falls back to global cal
- Callable / `__call__` works the same as `.predict()`
- Summary contains the qualified leagues

Plus the existing 246 V4 tests still pass against the updated walk_forward
that now emits `gbm_dc_pl_temp` as an extra reporting row.

Total V4 suite: **255/255 passing**.
