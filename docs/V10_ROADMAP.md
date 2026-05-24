# Nutmeg V10 Roadmap

_Started 2026-05-25 at V10 W0. 4-week mini-version, dual-track parallel
execution. Triggers fired: #3 (new product gap — UX needs rework),
#4 (cross-source robustness — gate exists but unverified on live),
plus a new time-sensitive trigger #6: **2026 FIFA World Cup starts
2026-06-11**, ~17 days from V10 W0._

## What V10 is

A **maintenance + product polish + opportunistic feature** version,
NOT a 12-week sprint. Three concrete deliverables, two parallel
tracks:

### Track A — User-facing maintenance (主线)

| Deliverable | Why |
|---|---|
| Front-end UX rework — default recommendations land on page load (no user input required); JSON / advanced settings folded away | User flagged: current dashboard is engineer-facing, not user-product. Q4 of the V10-trigger discussion |
| Layer A auto-T calibration drift correction (cron) | Q3 of the V10-trigger discussion: closes the recommend → settle → learn loop. Without it, P1#19 only alarms, can't act |

### Track B — WC sprint (并行, 时间窗口紧迫)

| Deliverable | Why |
|---|---|
| WC 2018 + 2022 historical fixtures + closing odds ingest | National-team Elo + WC competition registry already shipped (V8 W7 + P1#10-12); only data layer missing |
| WC-specific lightweight model (Elo + lineup quality + form + Pinnacle blend on ~128 historical matches) | Domestic CatBoost won't transfer (P1#20 negative); but a thin Elo-based model is feasible |
| Dashboard "WC 预测" tab + dry run on 2026 group-stage draw | User-visible deliverable for the high-visibility WC window |

### Deliberately OUT of scope (defer to V11 or later)

| Item | Why deferred |
|---|---|
| Q1 Path 1-5 model improvements (live lineup at kickoff, stadium-specific home advantage, player-weighted injuries, fatigue, Pinnacle Bayesian blend) | High ROI long-term (-0.002 to -0.005 log-loss = +3-7pp ROI) but each takes 2-6 weeks; not feasible inside a 4-week V10 |
| Q2 Layer B (quarterly walk-forward auto-retrain) | Should follow Layer A — first validate the cheap path (T-only) works; then build the expensive path (full retrain) |
| Q2 Layer C (online learning) | Never — football is slow-drifting; framework switch cost vastly exceeds benefit |
| Coverage of new leagues (中超 / K-League / 巴甲 etc.) | Out of scope unless explicit user demand |
| Postgres migration | No scale need yet |

## Why 4 weeks, not 12

V8 retrospective signed "项目接近 maintenance mode". V9 honored it.
V10 honors it further — it's a focused product + WC sprint, not
an architecture overhaul. If V10 finishes early (Track B ships
W3 instead of W4), that's a clean ship; we don't pad to fill 12
weeks.

If V10 needs to extend past W4 (e.g., WC dry run finds a model
issue worth investigating), it extends as V10 W5+ rather than
spawning a V11 — same logic as V9 W1-W6 being flexible.

## Week-by-week plan

### V10 W1 (2026-05-25 → 2026-05-31)

**Track A — UX rework**
- Audit current `apps/api/src/nutmeg/v4/api/static/dashboard.html` for
  "engineer-facing" surface (JSON textareas, manual fixture entry,
  required bankroll input)
- Wireframe new "default recommendation on page load" flow:
  - Page load → server fetches today's fixtures (auto_fetch) →
    generates recommendations with default ¥1000 bankroll →
    renders them as the primary view
  - "Adjust budget" inline input → re-runs recommendation with new bankroll
  - JSON / advanced settings move to a collapsible "高级" panel
- Ship implementation as `docs/v10_w1_ux_rework.md` writeup +
  updated dashboard.html

**Track B — WC ingest**
- Day 1: `nutmeg-ingest-cup-history --leagues WC --seasons 2018,2022`
  (fixtures + lineups, ~150 API-Football calls)
- Day 2-3: `nutmeg-ingest-cup-odds-via-odds-api --leagues WC --seasons 2018,2022`
  (closing odds, ~2,560 Odds API quota)
- Day 4: `nutmeg-ingest-national-elo` for all 68 nations (already a one-shot CLI)
- Day 5: build inventory report — how many fixtures with odds; which
  national teams missing from registry; data quality audit

**W1 ship target**: 2026-05-31, with W1 marker tag `v10.w1`.

### V10 W2 (2026-06-01 → 2026-06-07)

**Track A — Layer A auto-T calibration**
- New module `nutmeg.v4.observation.auto_calibration`
- Reads past N weeks of settled live data
- Fits a candidate temperature T using `cal_cat_temp` (V9 W6 code,
  already in `walk_forward.py`)
- Validates on held-out tail (last 2 weeks)
- Ship gate: only deploy if (a) candidate beats current T by ≥ 0.001
  log-loss on holdout, AND (b) bootstrap p < 0.1
- Auto-rollback: next 2-week window's ROI drops > 5pp vs prior → revert
- Audit log: every T change → JSON entry with data window + evidence
- New launchd job `com.nutmeg.weekly_calibration_check` (Mon 03:00)

**Track B — WC model + walk-forward**
- New module `nutmeg.v4.model.national_team_predict`
- Architecture (per Q discussion):
  - Inputs: elo_diff, lineup_quality_diff, form_diff (last 6 intl
    matches), home_adv (0 for neutral)
  - Backend: lightweight LightGBM, ~30 trees, regularized
  - Optional Bayesian blend with Pinnacle market price
- Training data: WC 2018 (64 matches) → train; WC 2022 (64 matches) → test
- Walk-forward verdict: target log-loss ≤ 1.00 (Pinnacle on WC ≈ 0.97)
- If verdict fails: don't ship the model, only ship Pinnacle-blend
  fallback for live recommendations

**W2 ship target**: 2026-06-07, with W2 marker tag `v10.w2`.

### V10 W3 (2026-06-08 → 2026-06-14)

**Track A — integration**
- Integration tests for new UX flow + Layer A cron
- Run full pytest suite, fix any regressions
- Update `docs/local_deployment_guide.md` to mention new launchd
  job + UX changes

**Track B — WC dashboard + dry run**
- New dashboard tab "WC 预测"
- New endpoint `/api/v4/predictions/wc` (returns upcoming WC fixtures
  with model probabilities)
- Dry run: generate predictions for all known 2026 group-stage
  matchups using current Elo + simulated Pinnacle odds
- Sanity check: do the predictions match informed pre-tournament
  expectations (e.g., favorites should look like favorites)?

**W3 ship target**: 2026-06-10 (1 day before WC starts), with `v10.w3`.

### V10 W4 (2026-06-15 → 2026-06-21) — WC live week

**Both tracks — monitoring**
- Daily `nutmeg-rec --auto-fetch --leagues WC` runs via launchd
- Daily settlement via `nutmeg-auto-settle` (already a job)
- Weekly P1#19 gate now meaningful since live cron has data flowing
- Layer A cron runs Mon 03:00 — first real auto-T check

**W4 ship target**: 2026-06-21, with `v10.0-shipped`.

## Trigger conditions for V11 (forward-looking)

V11 starts when ≥ 1:
1. WC verdict (post-2026-07-15): if Track B's WC predictions were
   meaningfully better/worse than Pinnacle, learn from it. If
   model held up → V11 might be Q1 Path 1-5 model improvements
2. Live cron data confirms or refutes P1#21 cross-source caveat:
   if live API-Football ROI agrees with football-data backtest →
   P1#18 lineup-aware ship is firmly validated, V11 can move on
3. New product surface from user

## Ship gates (V10-specific)

| Gate | Threshold |
|---|---|
| UX rework | User confirms default-recommendation flow feels natural; no JSON visible on main flow |
| Layer A | At least 1 successful auto-T cycle on real live data without rollback |
| WC ingest | ≥ 100/128 historical fixtures have closing odds (some 2018 matches predate Odds API coverage) |
| WC model | Walk-forward log-loss ≤ 1.00 on WC 2022 test set; OR Pinnacle blend ships as fallback |
| WC dashboard | "WC 预测" tab loads for any pre-WC user, even before any matches start |

## Numeric targets

| Metric | V9 ship | V10 target |
|---|---:|---:|
| V4 tests passing | 803 + ~50 from P1 chain ≈ 850 | 880+ |
| CLIs in pyproject.toml | 25 + 4 from P1 chain ≈ 29 | 30-31 |
| Dashboard tabs | 7 | 8 (add WC) |
| Launchd jobs | 4 (after P1#24) | 5 (add weekly_calibration_check) |
| GH Actions workflows | 5 (after P1#26) | 5 (no new) |
| Cron-driven production retrain count | 0 (since V5 W12) | 0 (Layer A only adjusts T, not retrains) |
| Documented negative results | 6 | 6 or 7 (only if WC model fails walk-forward) |

## Anti-patterns to avoid (carried from V10_ROADMAP_DRAFT)

1. **Don't try to push 51% → 55%** during V10. Q1 discussion concluded
   real ceiling is ~52%; pursuing model gains is V11+ work
2. **Don't ship Q2 Layer B** during V10. Validate Layer A first
3. **Don't auto-deploy Layer A without holdout validation**. Risk of
   chasing live ROI noise is real
4. **Don't extrapolate from 1 week of WC data**. 64 matches × 1 month
   is small; tournament dynamics differ from league
5. **Don't pad W4 with busywork**. If both tracks finish W3, ship
   `v10.0-shipped` early
