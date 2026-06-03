# V10 W2 Ship Note — Layer A Auto-T Calibration End-to-End

_Shipped: 2026-05-25 (tag `v10.w2`, ahead of 2026-06-07 target)_

---

## TL;DR

V10 W2 closes the recommend → settle → learn loop with **Layer A**:
a post-hoc temperature scalar on the model's 1X2 probabilities that
the system can re-fit weekly, deploy to the serving layer without a
restart, and auto-rollback if a deploy starts hurting.

**5 days, 1 module, 1 CLI, 1 launchd job, 67 new tests, ~1500 lines.**

The production model (CatBoost + lineup-aware, unchanged since V5 W12)
still produces the same `(λ_home, λ_away)` per match. Layer A only
adjusts the post-grid `(P_H, P_D, P_A)` triple via a single T scalar.
No retraining — that's the V11+ Layer B.

---

## Architecture

### Data flow

```
[Daily cron]
  recommend → settle → outcomes pile up in v4_observation.db
                                                      ↓
[Monday 03:00 launchd]                                ↓
  com.nutmeg.weekly_calibration_check                 ↓
    └─→ nutmeg-auto-calibration                       ↓
         --apply --auto-rollback                      ↓
         --deploy-artifact data/v4_model_cat              ↓
                                                      ↓
         ┌──────────────────────────────┬─────────────┘
         │                              │
         ▼                              ▼
    Active correction?            No correction yet
         │                              │
         ▼                              ▼
  evaluate_active_correction      propose_drift_correction
         │                              │
    delta > threshold?            holdout gate?
   ┌─────┴─────┐                  ┌─────┴─────┐
   ▼           ▼                  ▼           ▼
 ROLLBACK    KEEP +              SHIP        HOLD
   │         re-baseline          │           │
   │         propose               │           │
   ▼                               ▼           ▼
 delete artifact +              user runs   journal only
 journal "rollback"             --action=deploy
                                explicitly
```

### Serving (5 endpoints)

`routes.py` `_load_correction()` is mtime-cached per artifact path.
On each request:

```python
correction = _load_correction()
# 1) per-fixture single_preds
ph, pd, pa = apply_correction_to_probs(grid_to_1x2(grid), correction)
# 2) combo / single recommenders
recs = recommend_combinations(inputs, ..., correction=correction)
rec  = recommend_singles(matches, ..., correction=correction)
# 3) pool selections
sel  = _pick_to_selection(row, ..., correction=correction)
```

`None` correction → identity passthrough (backward compatible with all
pre-W2 callers). When `live_T_correction.json` lands on disk, the
mtime cache picks it up on the very next request — no uvicorn restart.

---

## What shipped (commit + tag map)

| Day | Commit | Title | LoC | Tests |
|----:|:-------|:------|-----:|------:|
| 1 | `17b1252` | `feat(v10/w2): Day 1 — auto_calibration module (Layer A core)` | ~460 | 22 |
| 2 | `1659952` | `feat(v10/w2): Day 2 — nutmeg-auto-calibration CLI` | ~250 | 10 |
| 3 | `d5823be` | `feat(v10/w2): Day 3 — artifact-side T correction + serving integration` | ~645 | 24 |
| 4 | `7e928cb` | `feat(v10/w2): Day 4 — weekly launchd cron + auto-rollback safety net` | ~640 | 11 |
| 5 | (this) | `feat(v10/w2): Day 5 — integration tests + tag v10.w2` | ~280 | 8 |

**Tag:** `v10.w2` (target 2026-06-07; shipped 2026-05-25 — 13 days ahead).

---

## CLI surface

```bash
# Dry-run propose (no journal, no artifact)
nutmeg-auto-calibration --db data/v4_observation.db

# Record proposal in journal
nutmeg-auto-calibration --db data/v4_observation.db --apply

# Deploy: write live_T_correction.json when ship gate passes
nutmeg-auto-calibration --db data/v4_observation.db --apply \
    --action=deploy --deploy-artifact data/v4_model_cat

# Rollback: delete live_T_correction.json + journal rollback
nutmeg-auto-calibration --db data/v4_observation.db --apply \
    --action=rollback --deploy-artifact data/v4_model_cat

# Weekly cron: auto-rollback FIRST, then propose if not reverted
nutmeg-auto-calibration --db data/v4_observation.db --apply \
    --auto-rollback --deploy-artifact data/v4_model_cat \
    --out docs/weekly/auto_calibration_$(date +%Y-W%V).md
```

**Exit codes:**
- `0` — success (proposed / deployed / rolled-back)
- `1` — setup error (DB missing, journal/artifact write failed)
- `2` — ship gate PASSED but not yet deployed (`--action != deploy`)
  → caller can use this to know "run `--action=deploy` next"

---

## Ship gate (both must pass)

| Check | Threshold | Why |
|---|---:|:---|
| Holdout log-loss Δ ≥ 0.001 | conservative | Don't chase noise on small samples |
| Bootstrap p-value ≤ 0.10 | one-sided | Resampling-based; T_new must beat T_old reliably |

The gate is intentionally weak in absolute terms — Layer A's job is
**drift correction**, not "improve the model". Small but consistent
gains are the right targets.

---

## Auto-rollback safety net

**Trigger condition:** post-deploy log-loss with deployed T exceeds
log-loss with identity (T=1.0) by more than 0.003 on ≥1 settled pair.

**Action:** delete `live_T_correction.json`, write `action=rollback`
journal entry with the bad delta, write a markdown report. The
propose flow is short-circuited that week.

**Why log-loss not ROI:** ROI on weekly samples is too noisy. Log-loss
is what the temperature scalar actually optimizes — if T is hurting
log-loss, it's by definition the wrong T.

---

## Tests (67 new across 4 files)

```
tests/v4/test_auto_calibration.py            22 — Day 1 core
tests/v4/test_auto_calibration_cli.py        10 — Day 2 CLI
tests/v4/test_auto_calibration_serving.py    24 — Day 3 artifact + routes
tests/v4/test_auto_calibration_rollback.py   11 — Day 4 evaluate + auto-rollback flag
tests/v4/test_auto_calibration_e2e.py         8 — Day 5 lifecycle integration
```

Day 5's e2e suite covers:
- Bootstrap (empty DB → "insufficient data" journal entry)
- Deploy cycle (data → propose → deploy → artifact written)
- Auto-rollback (bad T deployed → cron reverts + journals)
- Mtime cache invalidation (fresh deploy live without server restart)
- 3-action journal audit trail (propose → deploy → rollback in order)
- Launchd plist content sanity (label + schedule + flags)

All 67 pass. Full V4 non-Playwright suite: **1065/1065**.

---

## Production wiring checklist

Before flipping Layer A "on" in production, the user needs:

1. ✅ Launchd jobs installed via `./scripts/setup_local_pipeline.sh`
   (this now includes `com.nutmeg.weekly_calibration_check`)
2. ⏳ Settled rows accumulating in `data/v4_observation.db`
   (V7 W1-W3 cron, ongoing)
3. ⏳ First Monday after install: `docs/weekly/auto_calibration_*.md`
   will land — review it before approving a `--action=deploy`
4. ⏳ Once a T is deployed, monitor `data/v4_model_cat/live_T_correction.json`
   metadata — if `n_holdout` is low or `p_value` is near 0.10, the
   next weekly check might propose a different T

---

## What's NOT in V10 W2

- **No model retraining.** Layer A is T-only. Layer B (quarterly
  auto-retrain) is V11+, gated on Layer A's first real cycle showing
  drift correction works.
- **No per-league T.** Single global T scalar. Per-league would be
  Layer A-2 if we see league-specific drift patterns.
- **No handicap-specific T.** Same T applies to handicap_1x2 as 1X2
  because the underlying score grid is shared. If handicap shows a
  different drift signature, that's a future investigation.
- **No retraining trigger.** The CLI only proposes T adjustments. If
  drift is too large for T to correct (e.g., new league dynamics), a
  human still has to decide to retrain the model.

---

## Open questions for W3+

1. **First-week numbers**: what does `--auto-rollback` do on an empty
   journal? (Tested: it falls through to propose normally.)
2. **WC dry-run**: 2026-06-11 kickoff is 17 days out — Track B W3 day
   is "WC dry run" which validates the predict CLI on the actual
   fixture list. Layer A doesn't run on WC because we have ~0 settled
   WC pairs in the observation DB.
3. **Lineup ROI verdict**: still data-gated (P1#18). The weekly cron
   needs to accumulate ≥4 weeks of settled lineup-aware sessions
   before `nutmeg-ab-report --weeks 4` returns a verdict.

---

## File map

| Module | Path | Purpose |
|---|---|---|
| Observation | `apps/api/src/nutmeg/v4/observation/auto_calibration.py` | Core math + journal + artifact I/O + auto-rollback eval |
| CLI | `apps/api/src/nutmeg/v4/cli/auto_calibration.py` | `nutmeg-auto-calibration` entry point + markdown renderers |
| Serving | `apps/api/src/nutmeg/v4/api/routes.py` | `_load_correction()` + apply_correction at 5 callsites |
| Combo | `apps/api/src/nutmeg/v4/combo/selections.py` | `build_selections_from_match(match, *, correction=None)` |
| Combo | `apps/api/src/nutmeg/v4/combo/recommend.py` | `recommend_combinations(..., correction=None)` |
| Combo | `apps/api/src/nutmeg/v4/combo/single_match.py` | `recommend_singles(..., correction=None)` |
| Launchd | `scripts/setup_local_pipeline.sh` | 5th job: weekly calibration check |
| Launchd | `scripts/teardown_local_pipeline.sh` | Bootout the 5th job |
| Launchd | `scripts/health_check.sh` | Status check for the 5th job |

Tests live in `tests/v4/test_auto_calibration*.py`.
