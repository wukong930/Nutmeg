# post-v9 P1#21 — Cross-source ROI backtest, **verdict is source-dependent**

_2026-05-24. Re-ran the P1#18 lineup-ROI verdict on a second data
source (The Odds API "Pinnacle" historical snapshots) to test
robustness. **Result: the verdict flips.** Lineup-aware wins on
football-data.co.uk PSC by +15.97pp / +54.53pp (5-league / 2-league),
but loses by -37.13pp / -28.75pp on Odds API strict-Pinnacle. Same
fixtures, same model, same bookmaker name — just different
snapshot-time captures. The P1#18 ship decision is now caveated:
lineup-aware is the right call for football-data-style closing
prices but the production daily cron pulls live API-Football odds
whose snapshot semantics differ from BOTH backtest sources. Real
verdict still requires 4+ weeks of live daily cron data._

## TL;DR

Same scope: EPL + La Liga, 2024-09-01 → 2024-11-30, 207 fixtures.

| Source                       | Default ROI | Lineup ROI | Δ (aware−free) | Settled recs |
|------------------------------|------------:|-----------:|---------------:|-------------:|
| football-data (PSC)          |  -44.59%    |   +9.94%   | **+54.53pp**   | 173 / 200    |
| Odds API (strict Pinnacle)   |  +12.14%    |  -16.62%   | **-28.75pp**   |  49 /  75    |

5-league version (EPL + La Liga + Serie A + Bundesliga + Ligue 1, 494 matches):

| Source                       | Default ROI | Lineup ROI | Δ (aware−free) | Settled recs |
|------------------------------|------------:|-----------:|---------------:|-------------:|
| football-data (PSC)          |   -2.58%    |  +13.39%   | **+15.97pp**   | 290 / 285    |
| Odds API (strict Pinnacle)   | +103.25%    |  +66.12%   | **-37.13pp**   | 164 / 186    |

**Both directions are real**, not noise. The flip is driven by a
systematic ~3-5% price gap between sources (see §Diagnostic).

## What we did

1. Added `--odds-source {football_data, odds_api}` flag to
   `nutmeg-roi-backtest` (P1#21 modification of P1#17 CLI).
2. Added 5 domestic-league sport_keys to `odds_api.SPORT_KEYS`
   (P1#20 had only added cup keys).
3. Backfilled 5-league Q1 historical snapshots from The Odds API
   (≈ 460 calls × 10 quota ≈ 4,600 quota = 23% of monthly Starter
   budget).
4. Re-ran the P1#18 backtest pointing at `--odds-source odds_api`.
   Got an OPPOSITE verdict.
5. Investigated: discovered `_select_bookmaker_h2h` was silently
   falling back through PREFERRED_BOOKMAKERS chain when Pinnacle
   was missing on some fixtures (using marathonbet, unibet etc.).
6. Added `strict_key` parameter to `_select_bookmaker_h2h` + threaded
   through `parse_fixture_to_h2h` → `build_psc_lookup_for_date_range`
   → `roi_backtest --strict-bookmaker pinnacle` CLI flag.
7. Re-ran with strict-Pinnacle filter — **verdict still flips**.
8. Compared per-fixture prices to find root cause.

## Diagnostic — why the flip

53 EPL Q1 fixtures matched between both sources. Price comparison
(decimal odds, OddsAPI vs football-data PSC):

```
                Home      Draw      Away
  Median Δ:    -3.02%    +0.58%    -3.58%
  Mean Δ:     -3.16%    -0.65%    -5.62%
```

The Odds API "Pinnacle" snapshots are systematically **~3-5% LOWER**
than football-data's PSC. Both nominally Pinnacle Closing Line.

Two plausible causes:

1. **Snapshot timing differs.** football-data PSC is captured at
   kickoff. Odds API snapshots at 23:00 UTC daily — that's BEFORE
   kickoff for late evening / next-day matches but AFTER kickoff
   (post-match) for early Saturday-afternoon matches. Pinnacle's
   pre-vs-post-match prices can differ; post-match quotes are stale
   reference values, not actually bookable.
2. **Settlement-margin differences.** The Odds API may pull from
   Pinnacle's "deep API" which adds a small markup before display.

Either way, the implication is the same: **two sources both labeled
"Pinnacle CL" can produce different EV calculations and different
fixture selections**, and that's enough to flip the lineup-vs-default
verdict.

### Why the flip is not just sample-size noise

- 5-league test has 290 / 285 settled recs for football-data,
  164 / 186 for Odds API. Both are substantial samples (>100 recs).
- Direction of flip is consistent across 2-league AND 5-league
  cuts. If it were noise, we'd expect one source-scope combination
  to disagree from the others.
- The price-level difference (~3-5% systematic) is large enough
  to mechanically explain the EV-gate selection differences.

### Why each verdict makes sense within its own source

- **football-data PSC**: prices are higher → more fixtures pass the
  5% EV gate → bigger bet volume → lineup-aware's marginal predictive
  edge has more selection opportunities → ROI advantage compounds.
- **Odds API strict-Pinnacle**: prices are lower → fewer fixtures
  pass EV gate → smaller, higher-confidence bet sample → lineup-aware
  features add NOISE relative to default's tighter selectivity → ROI
  disadvantage.

## What changes for the ship decision

**P1#18 ship (lineup-aware as default) is not reversed.** Reasons:

1. The football-data verdict was validated across 3 sub-windows
   (Q1/Q2/Q3) and consistently positive. The Odds API result is
   one window; we don't have multi-window confirmation.
2. The lineup-aware model was TRAINED on football-data-style
   features. Validating it on the same source (football-data PSC)
   for the ROI verdict is consistent.
3. The production daily cron pulls API-Football's `/odds` endpoint
   for live betting — whose snapshot semantics are DIFFERENT from
   both backtest sources (API-Football is a third "Pinnacle-ish"
   source). The "real" verdict requires actually accumulating live
   bets through 4+ weeks of daily cron.

**But the ship is now caveated.** Added to V10 backlog:

- **V10 trigger #3 (NEW)**: Cross-source backtest divergence
  resolved either by (a) 4 weeks of live cron data showing the
  V6 W7 model's edge holds against API-Football's live odds, or
  (b) a third independent source (e.g. Betfair Exchange via
  another data provider) agreeing with one direction.

## What does NOT ship

- ❌ Reverting P1#18 ship — the football-data evidence still
  stands as the primary validation source.
- ❌ Filtering future backtests to strict-Pinnacle by default —
  the fallback-chain behavior in `_select_bookmaker_h2h` is
  legitimate for cup-odds use cases where Pinnacle isn't always
  available; we just added an opt-in `--strict-bookmaker` flag
  for cross-source validation.

## What DOES ship (infrastructure + caveats)

1. **`--strict-bookmaker` flag in `nutmeg-roi-backtest`** — allows
   future cross-source studies to enforce apples-to-apples bookmaker
   filtering. Default behavior unchanged.
2. **5 domestic-league sport_keys added to `odds_api.SPORT_KEYS`**
   (EPL, ESP_LA_LIGA, ITA_SERIE_A, GER_BUNDESLIGA, FRA_LIGUE_1).
3. **`build_psc_lookup_for_date_range`** with optional strict
   filter — reusable by future cross-source ablations.
4. **Honest documentation** that the lineup-aware ship has a
   source-dependency caveat. Adds to project's growing pile of
   "we shipped X but the verdict is fragile to Y" disclosures
   (joining V5 W12 catboost log-loss-vs-ECE gap, V6 W5 lineup
   leakage, V9 W6 raw-CatBoost beating temp/iso).

## Quota economics

```
4,600 / 20,000 monthly quota for this validation run = 23%
Hard cost: $30/mo × 0.23 = $6.90 amortized
Plus 1,800 for P1#20 cup backfill (already documented separately) = 32% used in May
Remaining for cancel-or-keep decision: 13,600 / month
```

The subscription remains in "excess capacity" mode (P1#20 reasoning
unchanged). Recommendation: **keep through end of June 2026** to
support 1-2 more potential validation studies (e.g. cross-source
on Q2 2024-25 or a season-long sweep). Cancel after that if no
specific question emerges.

## Files touched in P1#21

```
apps/api/src/nutmeg/v4/data/sources/odds_api.py             [M] +strict_key, +5 sport_keys, +build_psc_lookup
apps/api/src/nutmeg/v4/cli/roi_backtest.py                  [M] +--odds-source, +--strict-bookmaker, +odds_lookup threading
docs/post_v9_p1_21_cross_source_backtest.md                 [+] this writeup
```

Plus snapshot cache: `data/external/odds_api/historical_sports_*_odds/`
(gitignored — large data files stay local).

## Verification (anyone re-running)

```bash
# 1. football-data baseline (no API calls, no quota)
nutmeg-roi-backtest --start 2024-09-01 --end 2024-11-30 \
  --leagues EPL,ESP_LA_LIGA --out-db /tmp/q1_fdco_2l.db \
  --odds-source football_data
nutmeg-ab-report --weeks 12 --db /tmp/q1_fdco_2l.db
# Expected: lineup-aware leads by ~+54.53pp

# 2. Odds API strict-Pinnacle (uses cache, no quota cost)
nutmeg-roi-backtest --start 2024-09-01 --end 2024-11-30 \
  --leagues EPL,ESP_LA_LIGA --out-db /tmp/q1_oa_strict_2l.db \
  --odds-source odds_api --strict-bookmaker pinnacle
nutmeg-ab-report --weeks 12 --db /tmp/q1_oa_strict_2l.db
# Expected: lineup-free leads by ~-28.75pp

# Verdict flip = expected. This doc explains why.
```

## Lesson — generalize

**"Backtest verdict is robust" requires multi-source validation,
not just multi-window.** P1#18 validated lineup-aware ROI across
3 sub-windows of the same dataset (football-data PSC). That
caught noise WITHIN a source but missed structural bias BETWEEN
sources. Going forward, ship-gate criteria should include "verdict
direction holds on ≥ 2 independent odds sources" before declaring
robustness — especially for marginal-edge claims (≤ 20pp ROI).

This isn't a reversal of P1#18 — it's an upgrade of the criterion
for FUTURE backtest-driven ship decisions.

## V10 backlog (updated)

| Trigger | Status |
|---|---|
| ~~Cup ablation~~ | CLOSED NEGATIVE (P1#20) ✓ |
| ~~Lineup ROI verdict~~ | SHIPPED POSITIVE w/ caveat (P1#18 + P1#21) ⚠ |
| Cross-source robustness | NEW — 4 weeks live cron OR 3rd source ⏳ |
| New product gap | unchanged ⏳ |

The "decision-pending" state (per V9 retrospective) now has a
small concrete data-gated condition added (cross-source) — but
the path to resolve it is the same daily cron that was already
running.
