# V12 Backlog Draft

_Drafted 2026-05-26 at V11 close. Not committed — V12 hasn't been
scoped yet. This is the candidate list, prioritized for "smallest
unit of value first"._

---

## How V12 should differ from V11

V11 was event-driven without week tags. V12 should stay that way
**unless** the user explicitly wants a 12-week sprint feel. The
project is now in a state where:

- Production model has been static since V5 W12 (Layer B is the
  unblock mechanism, but its first firing is 2026-07-01)
- Real-bet ROI verdict has been data-gated since V7 ship
- The frontend is feature-complete for the user's stated needs (P1-FE
  chain closed)

So V12 has two natural shapes:
- **Shape A: passive waiter** — V12 = "between Layer B first firing
  and lineup ROI verdict". Mostly tier 2 cleanups + monitor.
- **Shape B: active research** — V12 = "now that infrastructure is
  stable, invest in new features (stadium, fatigue, MCMC)". Tier 3.

The decision between A and B is the V12 W1 question.

---

## Tier 1 — data-gated (cannot be done without real-bet data)

These are not coding tasks. They wait on the user's local cron
accumulating enough settled recommendations.

### V12-1: Lineup-aware 4-week real ROI verdict

**Status**: Waiting on the existing observation cron (V7 W1-W3 +
V6 W8) to accumulate ≥ 30 settled lineup-aware recommendations.

**Action when ready**:
```bash
nutmeg-ab-report --weeks 4 --db data/v4_observation.db
```

**Decision**: ship lineup-aware artifact as production default, or
document as a non-improvement and roll back.

**Effort**: 0 coding; 1 user command + 1 verdict doc.

### V12-2: Layer B first quarterly proposal (2026-Q3)

**Trigger**: 2026-07-01 (quarterly boundary).

**Process** (per design doc §12):
1. Cron fires `nutmeg-auto-retrain --action propose`
2. User reads `docs/quarterly/retrain_2026-Q3.md`
3. If ship gate passed + manual review approves: `--action deploy`
4. 4-week observation period; auto-rollback weekly check active
5. After 4 clean weeks, Q3 deploy is confirmed

**Effort**: ~30 min user time + ~1 hour wall-clock for the training
run (which we haven't measured yet).

### V12-3: Live-vs-backtest gap analysis

**Trigger**: When enough real-bet data exists that the V5 W11
`live_vs_backtest` endpoint produces meaningful numbers.

**Action**: read the V5 W12 verdict's "implied vs realized ROI" table
and decide if the model's calibration assumptions hold.

**Effort**: 1 day verification + writeup.

---

## Tier 2 — open since V8/V9/V10, ready to do

### V12-4: CI runs `--with-lineups` / `--with-cup-data` end-to-end

Currently: GH Actions runs core V4 tests but skips the lineup-aware
and cup-aware training paths because they need a local cache that
isn't checked in.

**Fix**: bake a small (1-2 fixture worth) lineup cache + cup parquet
into `tests/data/`; mark the existing skip conditions as "always
run in CI" instead of "skip when cache empty".

**Effort**: 1-2 days. Cleanest version uses pytest fixtures that
materialize a tiny cache at session start.

### V12-5: ECE 0.0120 vs log-loss 0.9960 mystery

The 24/25 test set shows CatBoost's ECE (0.0120) is BETTER than
Pinnacle's (0.0123), but log-loss is WORSE (+0.0056). The model is
sharper than the market in some buckets and worse in others.

**Investigation**: per-bucket Brier audit. The `bucket_decomp` module
(V9 W5) is the entry point. Tag specific (probability bin × outcome
class × league × home/away) cells where the model leaks log-loss
despite calibration looking right.

**Outcome shape**: "Here are 3 specific patterns where the model
loses bits the calibration doesn't expose; here's whether they're
addressable via training data or via feature engineering."

**Effort**: 2-3 days exploration + writeup.

### V12-6: Layer B cleanup policy

From `docs/v11_layer_b_design.md §9` (deferred):
- Keep last 4 quarterly artifacts (1 year)
- Archive 5-8 to `_archive/`
- Delete > 2 years old

**Effort**: 1 day. Cron job that runs after each successful Layer B
deploy.

### V12-7: Layer B launchd cron + auto-rollback weekly check

Deferred from V11 backlog #4 because we wanted to see one manual
deploy work before automating. Once V12-2 ships, this becomes ready.

**Effort**: 1 day. Mirror Layer A's `weekly_calibration_check` plist.

---

## Tier 3 — V12 research

### V12-8: NumPyro NUTS validation of MCMC verdict

Phase 0 #5's hand-rolled MH showed -0.0064 log-loss on one season
with R-hat at 1.058. Honest verdict: confirm with NUTS on 2-3 more
seasons before deciding.

**Action**: install NumPyro + JAX → port the same model → run on
2021/22, 2022/23, 2023/24 in addition to 2024/25.

**Effort**: 3-5 days. Adds ~500MB dependency footprint if installed.

**Decision criterion**: ≥ 3/4 seasons show ≥ -0.005 log-loss improvement
with R-hat < 1.05 → migrate; else stay on DC MLE.

### V12-9: Unify WC model with main CatBoost

V10 W1 Track B trained a separate `NationalTeamModel` for WC 2026
prediction. V11 backlog #5 wired `nation_state` into the main
CatBoost pipeline but didn't actually train a unified artifact.

**Action**: add WC + EURO + Copa America rows to the training UNION;
test on (a) league fixtures (current baseline), (b) WC walk-forward
(parity check against the separate Track B model).

**Effort**: 1-2 weeks. Includes ablation runs + ship decision.

### V12-10: Populate stadium + fatigue features

V11 Phase 0 #3 + #4 shipped skeletons (`features/stadium_features.py`,
`features/fatigue_features.py`). They're stub implementations with
27 + 44 unit tests but no data backing them.

**Action per feature**:
- **stadium**: enrich `data/external/stadiums.csv` with capacity +
  surface type per fixture's venue; wire into GBM training; ablate
- **fatigue**: build the player-level fatigue index from API-Football
  `/players` minutes data; wire into pre-match features; ablate

**Effort**: 1 week each. Stadium is the easier of the two (static data).

### V12-11: Extend `CUP_TEAM_ALIASES` for 148 unmatched cup teams

Cup ablation verdict (V11 backlog #2) noted 148 unresolved cup team
names dropped from training rows. Even if it doesn't push the ship
gate (-0.0011 won't become -0.005 just from more rows), the data
hygiene is worth fixing.

**Effort**: 2-3 hours of manual alias entry + verification.

### V12-12: National-team-cup test set for ablation framework

V11 backlog #5 wired `nation_state` through the harness but tested
on a league test set (where it has no effect). The proper test is
a national-team test set (WC 2018+2022 holdout, EURO 2024 holdout).

**Effort**: 3-4 days. Requires extending `WalkForwardConfig` to
accept a custom test-league set + computing per-WC-tournament metrics.

---

## Tier 4 — frontend follow-ups

### V12-13: Logo ingest reminder

The dashboard renders 28×28 initials circles by default. Logos only
appear after the user runs `nutmeg-ingest-team-logos` (V11 P1-FE#2
Day 2). Add a one-time onboarding tip + the command snippet.

**Effort**: 0.5 day.

### V12-14: Live odds drift indicator

V11 P1-FE#5 ships a banner when `version_hash` changes. But version_hash
collapses **pick changes** and **odds drift** into one signal. Could
split: separate "📈 odds moved" badge vs "🔄 pick changed" badge.

**Effort**: 1-2 days. Need to add odds-only fingerprint separately.

### V12-15: Mobile-app polish

The dashboard is a PWA (V8 W8 / P1#14 added manifest + SW). Install
flow works but hasn't been tested on iOS Safari extensively.

**Effort**: 0.5 day user testing + any required tweaks.

### V12-16: History tab cumulative P/L chart

V11 P1-FE#3 ships the 推荐追溯 tab with per-day counts. Could add
a cumulative P/L chart at the top (running stake vs running payout).

**Effort**: 1 day. Re-uses existing observation DB queries; just
adds a chart-rendering helper.

---

## Tier 5 — V12+ deep research

Listed for completeness; none of these should happen in V12 unless
the user explicitly asks.

| # | Item | Why it's not Tier 3 |
|---|---|---|
| 17 | Federated / online learning | V13+. Engineering complexity too high for current ROI |
| 18 | Multi-model ensembling (XGB + LGB + Cat stacker) | V5 W6 already tried this; failed ablation. Re-test only when feature set materially changes |
| 19 | Distributional shift detection (KL divergence) | V12+ research; not blocking anything |
| 20 | Per-league custom hyperparameters | The hyperparam-search infra would dominate the actual gain |

---

## What's NOT in this backlog (intentional)

- **V14+**. Too far away to plan. _(Update 2026-05-29: V13 IS now scoped —
  see `V13_ROADMAP.md` + `V13_CONTEXTUAL_FEATURES.md` / `V13_DATA_QUALITY_UPGRADE.md`
  / `V13_EUROPEAN_EXPANSION.md` / `V13_PLAYOFF_AWARENESS.md`, all gated on the
  4-week ROI verdict. This bullet predates those docs.)_
- **New game types** (e.g., totals/over-under). User's stated scope is
  1X2 + handicap only. No expansion.
- **Public deployment / multi-user**. Single-user-on-Mac is the
  deployment target.
- **Mobile-native app**. PWA is sufficient.

---

## Recommended V12 starting point

If the user wants to start V12:
1. **First week**: V12-1 + V12-2 (the data-gated ones — run the
   commands, write the verdicts). Establishes whether the production
   model + Layer A correction stack is performing as designed.
2. **Second week**: V12-4 + V12-6 + V12-7 (close the cleanup items
   from V8/V9/V10 + the Layer B follow-ups deferred from V11).
3. **Third week onwards**: branch on the V12-1 + V12-2 verdicts:
   - Both green → V12-5 (ECE mystery) or V12-10 (stadium features)
   - Either red → diagnostic deep-dive on the regression

Total V12 first-month estimate: ~1 week real work, 3 weeks elapsed
(matches V11's actual cadence — most of V11's wall-clock was waiting
on the data side, not the code side).
