# V5 W12 — Paid data decision

_Original V5 plan §W12: "evaluate paid data sources; decide on API-Football
$19/mo subscription based on 4-week observation period." Deferred to V6._

## Decision

**Defer paid-data subscription until V6.** No purchase this week.

## Reasoning

The W8 observation loop only landed at week 8 of the 12-week sprint, and
the GH Actions cron that automates `live-vs-backtest` only landed at W10.
We have, as of the W12 cutoff, **zero days of real settled bets** to
compare against backtest expectations. The original W12 acceptance
criterion ("실战 ROI (Kelly0.25, 4 weeks) ≥ +2pp") is unmeetable not because
ROI is bad but because **the measurement infrastructure didn't have time
to collect data**.

Buying $19/mo of API-Football data without any real-bet ROI signal would
amount to spending money on a hunch. The hunch is reasonable — Pinnacle's
remaining 0.005 log-loss advantage over CatBoost likely IS lineup /
injury information — but we should let the cron prove the gap is stable
in live conditions first.

## Conditions for V6 paid-data purchase

Set the trigger explicitly so the decision in 4-8 weeks doesn't need
re-litigation:

1. **Live observation runs for ≥ 4 calendar weeks** with ≥ 1 session/day
   on `closing` snapshot phase
2. **Live ROI (Kelly0.25) stabilizes above 0%** in the W8 cron weekly card
3. **Live hit-rate gap vs backtest is within ±5pp** (proves no leakage)
4. THEN — if live ROI is plateauing under +2pp and lineup-aware models in
   literature show typical +0.003-0.005 log-loss improvement, subscribe
   to API-Football for one month and run side-by-side A/B (W7 backend
   path already supports a second artifact dir)
5. Decide to renew based on whether the lineup-augmented artifact's live
   ROI is meaningfully higher

This is **not** a fixed timeline. If live ROI is already above +2pp
without lineup data, no purchase. If live ROI is negative, investigate
leakage / market drift before spending.

## What costs nothing and is still on the table

Re-evaluate periodically. Free sources that worked in V5:

- **clubelo** (W3) — live; currently 197/335 teams covered. Italy/Portugal
  slug fixes alone could push to ~250
- **football-data.co.uk** — already in use; releases new CSVs weekly

Free sources that were blocked but could be revisited:

- **understat** — could try `playwright` headless rendering
  (heavier dependency, slower; worth it if xG turns out critical)
- **fbref** — Cloudflare-blocked; the `worldfootballR_data` GitHub mirror
  publishes RDS files we couldn't parse with `pyreadr` due to encoding
  issues. Could try `rpy2` subprocess to read via real R, OR find
  someone who's published a CSV mirror
- **OddsPortal** — Cloudflare + Vue.js SPA. Playwright + stealth plugin
  feasible but brittle. Lower priority since closing-line drift didn't
  help anyway (W5)

## Cost-benefit if we did subscribe

For reference if the decision flips:

- API-Football basic plan: $19/mo
- Coverage: ~840 leagues including all of V5's targets
- Data: lineups (confirmed XI ~1 hour before kickoff), injuries, suspensions
- Integration effort: ~3-5 days
  - Adapter in `nutmeg.v4.data.sources.api_football`
  - New feature module `nutmeg.v4.features.lineups`
  - Augment `build_features_for_fixtures` to pull lineups for the
    fixture date
- Expected log-loss improvement: 0.003-0.005 (Bayesian prior from
  academic literature — Sharma et al. 2022 found ~0.005 from lineup data)

At $19/mo and a $1k bankroll, the lineup data needs to add ≈ **2% ROI**
just to pay for itself, before any actual profit. If V5's backtest ROI
holds in live conditions, this should be straightforward; if it doesn't,
the lineup add isn't going to save us.

## What V6 should NOT do

- Buy `Sportmonks` or `Opta` ($100s/month). The marginal data over
  API-Football is mostly granular event-level data, which V5's
  team-level lambda model can't usefully consume without significant
  architectural change. If V6 introduces event-level modeling (xG flow,
  in-play minutely lambdas), revisit
- Subscribe and forget — schedule a 1-month A/B with rollback path
  built in (the W7 multi-backend artifact loader already supports
  named alternatives)

## Recorded baselines (for V6 reference)

- Backend at W12: CatBoost, default `--model cat`
- log-loss 24/25: 0.9960 (vs Pinnacle 0.9904, gap 0.0056)
- ECE: 0.0120 (BETTER than Pinnacle 0.0123)
- Hit-rate: 51.12% (Pinnacle 51.24%)

When live data arrives, compare against these.
