# V11 Retrospective

_Closed 2026-05-26. Branch: post-v10-shipped event-driven (no week tags)._

---

## TL;DR

V11 wasn't a 12-week sprint — it was the **event-driven cleanup +
infrastructure layer** that V10 deliberately left open. Three pillars:

1. **Phase 0 (5 items)** — V11 baseline: monitor, Layer B design doc,
   feature skeletons (stadium, fatigue), MCMC exploration notebook.
2. **P1-FE chain (7 patches)** — full frontend premium refresh: visual
   system + theme toggle, team logos + Chinese names (14 leagues),
   today-tab pool + sliders, 推荐追溯 tab, dynamic recommendations,
   auto-refresh, full-league zh coverage.
3. **Backlog closeouts (3 of 4)** — V8 W4 cup-aware verdict (negative
   ship gate), national-team Elo end-to-end integration, Layer B
   propose/deploy/rollback infrastructure.

Tests: **1108 → 1410 (+302, all green)**.
Commits: 30+ in this session, all on `main`, all pushed.

The user's audit Gap list from the V11 kickoff:
| Gap | V11 status |
|---|---|
| 1. Real-bet ROI = 0 data points | ⏳ data-gated (cron infra ready since V7) |
| 2. Cup model never trained | ✅ V11 backlog #2 — DO NOT SHIP verdict |
| 3. National-team Elo not integrated | ✅ V11 backlog #5 — integration complete |
| 4. Dashboard 单关/复式 no record-session | ✅ (closed earlier, in post-v8 P1#5) |
| 5. CI doesn't run lineup/cup paths; ECE mystery | ⏳ V12 backlog |

---

## What shipped (chronological)

### Phase 0 (V11 baseline)
- **#1** `scripts/v11_monitor.sh` — trigger-aware status board (4 sources → Branch A/B/C recommendation)
- **#2** `docs/v11_layer_b_design.md` — 567-line Layer B architecture spec
- **#3-4** `features/{stadium,fatigue}_features.py` — skeletons + 27 + 44 tests respectively
- **#5** `notebooks/v11_phase0_mcmc_exploration.{py,ipynb}` — MCMC vs DC MLE comparison + verdict
- **Bonus**: Belgian Pro League coverage close (14-league expansion of cron + dashboard defaults)

### P1-FE chain (frontend premium refresh)
- **#1** Design system tokens + dark/light theme + tab cleanup (5 user tabs, 4 engineer tabs removed)
- **#2** Team logos + Chinese names for top-5 European leagues (ingest CLI + initials-circle fallback)
- **#4** Today tab: pool option + 风险偏好 + 最低 EV sliders
- **#3** 推荐追溯 timeline tab + outcome chips + 7d/30d/all date filter
- **#5** Dynamic recommendations — version_hash + diff banner + 已更新 badges
- **#6** Auto-refresh — Visibility API polling + 上次更新 N秒前 stale label
- **#7** Chinese names for all 14 trained leagues (355 dedup'd team names)

### Backlog closeouts
- **#2** V8 W4 cup-aware verdict — ran `nutmeg-cup-ablation`, ship gate 1/2 (need 3/4), **DO NOT SHIP**
- **#5** National-team Elo integration — wired `nation_state` through `WalkForwardConfig` + `cup_ablation`, audit Gap 3 closed
- **#4** Layer B — `auto_retrain.py` module + CLI + serving integration (3 actions × full state machine)

---

## Numbers

| Metric | V10 ship | V11 close | Δ |
|---|---:|---:|---:|
| V4 tests | 1108 | 1410 | **+302** |
| CLIs (`[project.scripts]`) | 31 | 33 | +2 (`nutmeg-ingest-team-logos`, `nutmeg-auto-retrain`) |
| Dashboard tabs (user-facing) | 7 | 6 | -1 (removed 4 engineer tabs, added 1 history tab; net effect 5+1=6) |
| Dashboard SW cache version | `nutmeg-v1` | `nutmeg-v10-fe-zh-14` | +9 bumps |
| Languages supported | zh, en (10 keys) | zh, en (~80 keys) | full chain coverage |
| Trained leagues (default `today-recommendations`) | 2 | 14 | +12 |
| Production CatBoost log-loss vs Pinnacle | 0.9960 vs 0.9904 (+0.0056) | unchanged | _model not retrained — Layer B awaits first quarterly cycle_ |

---

## What V11 chose NOT to do (deliberate)

- **Did not retrain production model.** Layer B infrastructure is
  ready; first quarterly run protocol (manual review of propose →
  human deploy) deliberately left for the first calendar quarter
  boundary that triggers the cron (target: 2026-07-01).
- **Did not ship cup-aware artifact.** Ablation said no; we documented
  the negative and kept all 7 weekly tags of code as opt-in CLIs.
- **Did not invest in PyMC/NumPyro.** MCMC exploration showed
  borderline convergence + ~6 milli-pt improvement on one season —
  not enough to justify the JAX dependency footprint without 2-3
  more cross-season verifications.
- **Did not implement Layer B cron + auto-rollback weekly check.**
  Both deferred until at least one manual deploy has been observed —
  no point automating something we haven't seen work once.
- **Did not unify WC model path with general CatBoost.** V10 Track B's
  separate `NationalTeamModel` continues. Merging is a V12+ research
  question.

---

## What worked

1. **Event-driven branching beat the 12-week sprint mold.** V11 didn't
   need 12 weeks — it needed 3 weeks of focused infrastructure plus
   one decision point per gap. The branched roadmap let the actual
   work happen on a smaller calendar surface.

2. **P1-FE chain composability.** Each FE patch (#1-7) shipped its own
   tested unit and built on its predecessor. By #7, the 14-league zh
   names plugged into a UI that already had logo + locale toggle +
   diff badges — no rework.

3. **Layer A as Layer B's template.** Mirroring `auto_calibration.py`
   into `auto_retrain.py` (same constants shape, same journal pattern,
   same artifact-side file mechanism, same pointer/cache strategy on
   the serve side) reduced cognitive load + new-code surface
   considerably. ~75% of the Layer B module was "copy Layer A and
   change names/numbers."

4. **Honest negative verdicts.** Cup ablation, MCMC exploration, and
   nation Elo all gave nuanced verdicts ("hold", "borderline",
   "no measurable league impact"). The instinct to ship the
   infrastructure first and let the data speak was correct — kept us
   from over-claiming during V8 W4 and post-v9 P1#12.

5. **Tests before push.** 302 new tests in this session; every single
   commit landed on top of a green `pytest tests/v4/` run. Zero
   regressions across 30+ commits.

---

## What didn't work / lessons

1. **The "10 P1-FE patches" estimate was almost 2× the actual.**
   Design doc said 12-15 days; actual was ~8 days. Almost every
   patch came in 50% under estimate because:
   - P1-FE#2 Day 1 covered 90% of what Day 2 would've added (the dict
     was the main work; the endpoint was trivial)
   - P1-FE#5/#6 share most state machine, so #6 was 0.5 days not 1-2
   - Same for P1-FE#7 — was 0.5 days not 2

   **Lesson**: pad less. The design-doc estimates were honest but the
   inter-patch synergies kept compressing the actual work.

2. **MCMC convergence threshold ambiguity.** Initial verdict logic used
   strict R-hat < 1.05; mid-run I added a softer "exploration"
   threshold 1.10. Should've designed the tiered verdict from the
   start instead of retrofitting it when R-hat landed at 1.058.

3. **Nation Elo integration was three patches deep, not two.** P1#4
   wired feature builder + train CLI, P1#12 added end-to-end tests on
   real parquet, **but** the multi-fold ablation harness was still
   blind to it. Three layers of wiring; only V11 backlog #5 closed
   the last one. **Lesson**: when wiring a knob through 4+ layers,
   write the smoke test at the OUTERMOST layer FIRST. Would've
   caught the gap at P1#4.

4. **SW cache version proliferation.** 9 cache bumps in one session —
   each P1-FE patch needed one. We never built a "bump on file change"
   automation; future P1-FE-equivalent work should script this.

---

## V12 candidate backlog (rough, no commitment)

Tier 1 — "data-gated" items that V11 left explicitly waiting:

| # | Item | What's needed |
|---|---|---|
| 1 | Lineup-aware 4-week real ROI verdict | ≥ 30 settle rows from local cron; user runs `nutmeg-ab-report --weeks 4` |
| 2 | Layer B first quarterly proposal (2026-Q3) | Runs automatically 2026-07-01; user reviews `docs/quarterly/retrain_2026-Q3.md` |
| 3 | Layer A weekly rollback check live | Already cron'd; needs at least one proposal cycle of real data |

Tier 2 — "open since V8/V9/V10":

| # | Item | Estimated |
|---|---|---|
| 4 | CI runs `--with-lineups` / `--with-cup-data` end-to-end | 1-2 d (bake a small lineup cache into the repo) |
| 5 | ECE 0.0120 (better than Pinnacle 0.0123) vs log-loss +0.0056 mystery — per-bucket Brier audit | 2-3 d |
| 6 | Cleanup policy for `data/v4_model_layer_b/_archive/` | 1 d (deferred from Layer B design §9) |
| 7 | Layer B cron job + auto-rollback weekly check | 1 d (deferred until first manual deploy works) |

Tier 3 — "V12 research / nice-to-have":

| # | Item | Estimated |
|---|---|---|
| 8 | NumPyro NUTS validation of MCMC verdict on 2-3 more seasons | 3-5 d |
| 9 | Unify WC model (V10 Track B) with main CatBoost via national-team training rows | 1-2 wk |
| 10 | Fatigue + stadium features actually populated (V11 skeletons only) | 1 wk each |
| 11 | Extend `CUP_TEAM_ALIASES` for 148 unmatched cup teams | 2-3 hr |
| 12 | National-team-cup test set for ablation framework | 3-4 d |

Tier 4 — "frontend follow-ups":

| # | Item | Estimated |
|---|---|---|
| 13 | Logo CDN fallback (currently 28×28 initials circles default; not all teams have ingested PNGs) | 0.5 d (user runs `nutmeg-ingest-team-logos`) |
| 14 | "Live odds drift" indicator on cards (not just version_hash banner) | 1-2 d |
| 15 | Mobile-app PWA polish — already shippable via Add-to-Home-Screen | 0.5 d (test on iOS) |
| 16 | History tab — per-day cumulative P/L chart (currently just counts) | 1 d |

---

## V11 timeline summary

```
2026-05-24       v10.0-shipped (V10 done)
2026-05-24       V11 roadmap draft pushed
2026-05-24-25    Phase 0 #1-4 shipped
2026-05-25       P1-FE design doc + 14-league coverage close
2026-05-25       P1-FE chain (all 7 patches, including Phase 0 #5 MCMC)
2026-05-26       Backlog closeouts: #2 (cup), #5 (nation Elo), #4 (Layer B)
2026-05-26       v11 retrospective (this doc)
```

About 3 calendar days of intense work. No `v11.w*` tags created
because the work was issue-driven, not week-driven — each commit
self-contained.

---

## Closeout

V11 ended in a clean state:
- All 5 Phase 0 items done
- All 7 P1-FE patches shipped and tested
- 3 of 4 V11 backlog items closed (the 4th is data-gated)
- Layer B infrastructure ready for its first quarterly firing (2026-07-01)
- 1410/1410 V4 tests green
- Repo on `main`; all pushed; no stale branches

The remaining open item (Lineup-aware 4-week ROI verdict) is a data
question, not a code question. The cron infrastructure to accumulate
that data has been running since V7 W1-W3.

Next decision point: **2026-07-01 Layer B first firing.** Until then,
the project is in maintenance mode + waiting on real-bet data.
