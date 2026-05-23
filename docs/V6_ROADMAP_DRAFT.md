# V6 Roadmap — Draft

_Drafted at end of V5 W12. Not yet user-approved. Replaces V5_ROADMAP.md as
the active plan when V6 starts._

## Context

V5 closed with:
- **CatBoost in production** (log-loss 0.9960 vs Pinnacle 0.9904 on 24/25)
- **Three falsified hypotheses documented** (market drift, ensemble stacker,
  per-league T) so V6 doesn't re-tread them
- **Observation + experiment-tracking infrastructure** but zero days of
  real-bet ROI data
- **ECE 0.0120 BETTER than Pinnacle** — well-calibrated; the remaining log-loss
  gap is sharpness, not bias

V6 should be **less feature-explorative** (V5 found the easy wins; remaining
features in our public data are likely correlated with what's already in
the model) and **more deployment / ROI-focused**.

## Proposed V6 themes (12 weeks)

### Theme 1: Live-bet ROI confirmation (W1-4)

The single biggest gap in V5: we can backtest but haven't proven live ROI.

- W1: Establish daily prediction cron (pre_close + closing snapshots)
  for at least 5 leagues
- W2: Build a fixture-source pipeline (manual CSV first, then explore
  paid odds APIs)
- W3: First weekly `live-vs-backtest` card with real settled bets
- W4: Decision gate — if live ROI < 0% sustained, investigate leakage
  BEFORE adding features. If ≥ 0% but < +2pp, proceed to Theme 2.
  If ≥ +2pp, treasure this and move to Theme 3.

### Theme 2: Lineup / injury data (W5-8)

Conditional on Theme 1 producing positive but sub-target ROI.

- W5: Subscribe to API-Football $19/mo; build adapter in
  `nutmeg.v4.data.sources.api_football`
- W6: New feature module `nutmeg.v4.features.lineups` —
  starting XI strength, key player missing, days-since-debut for first XI
- W7: Train CatBoost with augmented features; multi-season validate
  using existing walk_forward with new feature flag
- W8: A/B in production — `data/v4_model_cat_lineup/` vs `data/v4_model_cat/`
  for 4 weeks. Decision: keep, revert, or buy more data tier

### Theme 3: Score-grid extensions (W9-10)

Conditional on Theme 1/2 stabilizing. Move beyond 1X2 + handicap.

- W9: Correct-score market (full 9×9 grid already computed; just expose
  selection logic + Kelly for individual scores)
- W10: Over/Under derived markets (PSC has odds; we have implied probs;
  combine for value detection)

These don't add log-loss improvements but expand the bet-types we can
recommend, which materially affects ROI ceiling (more shots on goal).

### Theme 4: Operational hardening (W11-12)

- W11: Postgres migration path — SQLite is fine for one user / 50 sessions
  a day but breaks down at multi-user. Schema is already abstract enough
  that the swap is mechanical
- W12: V6 handoff. Tag `v6.0-shipped`

## Alternative emphasis (if Theme 1 surprises)

**If live ROI is already > +2pp without lineup data**, paid-data investment
is unjustified. Pivot:

- W5-6: Multi-league expansion (currently 13 leagues; football-data.co.uk
  covers ~30; adding lower-volume leagues like K1, Polish Ekstraklasa,
  Belgian Pro adds bet opportunities without adding model complexity)
- W7-8: Real-time odds streams (multi-snapshot vs open/close pair —
  unblocks the W5 drift signal that failed on sparse open-close data)
- W9-12: Continue Theme 3 + Theme 4

**If live ROI is sustained negative**, this is the most important signal —
the W5/W6/W9 ablations suggest we're already near the public-data ceiling,
so persistently negative live ROI means either:
1. Lookahead leakage in features (most likely — investigate `features/` for
   any column that could see future info)
2. Closing-line drift between PSC (Pinnacle) and the books we actually bet
   into (V5 only knew Pinnacle's price)
3. Vig structure of the books we bet into makes the gap mathematically
   unwinnable at our edge size

In that order. The fix for (1) is engineering; for (2) is data (book-specific
odds streams); for (3) is "play in different markets" or "accept and stop".

## What V6 should NOT do (V5 has tested these)

Listed here so a future contributor doesn't re-do V5's negative work:

- ❌ Re-try market-dynamics drift features (W5)
- ❌ Re-try LogReg ensemble stacker on the same 3-base setup (W6)
- ❌ Enable per-league temperature on the current 90-day val window (W9)
- ❌ Try isotonic calibration on the current val size (V4 doc §6 also called this out)
- ❌ Buy paid data sources without first having ≥ 4 weeks of live ROI

## What V6 might re-evaluate

- ⏳ understat / fbref scraping with playwright stealth — if W4 budget allows
- ⏳ worldfootballR_data CSV mirrors (community-maintained) — if anyone
  republishes the RDS dumps as CSV / parquet
- ⏳ ensemble with **independent training data** — if we can collect odds
  for OTHER books beyond Pinnacle (Bet365 closing IS in our CSV but unused),
  bases trained on different feature sets would actually be decorrelated.
  The W6 stacker failed because the bases saw identical features

## Open questions for V6 kickoff

1. Who provides the daily fixtures CSV (the human bottleneck in W1-4)?
   Automating fixture ingest is a $0 task (football-data.co.uk publishes
   fixtures + odds the day before for most leagues) and removes the
   "did the user remember to update the CSV?" failure mode
2. What's the actual bookmaker the user bets into? If it's not Pinnacle,
   the closing prices we currently use for both training AND value
   detection are subtly wrong — should be PSC for training but actual
   booked odds for the value calc
3. Is there an interest in Asian-handicap-line tracking? V4 has the column
   but it's not used as anything but a market signal
