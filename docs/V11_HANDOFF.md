# Nutmeg V11 Handoff

_Last updated: 2026-05-26 (V11 ship / `v11.0-shipped` tag)._

Single source of truth for V11 — the **event-driven cleanup + infrastructure
layer** that V10 deliberately deferred. Read this first when picking up the
project; then [V12_BACKLOG_DRAFT.md](V12_BACKLOG_DRAFT.md) for what's next;
then [V10_HANDOFF.md](V10_HANDOFF.md) for the WC sprint context, and back
through V9 / V8 / V7 / V6 / V5 / V4.

---

## 1. What V11 was

V11 starts from a different place than V5-V10:

| Signal entering V11 | What it meant |
|---|---|
| V10 shipped (5 ship tags + WC infrastructure live) | The 4-week dual-track sprint closed; no new external deadline pressing |
| User-requested audit identified 5 gaps after `v8.0-shipped` | Honest pre-V11 inventory of what was incomplete despite "infrastructure ready" claims |
| 33 weekly tags + 5 ship tags accumulated since V5 | Repo + project architecture mature; what's missing is not "more weekly work" but specific decision-gated closeouts |
| Frontend visual debt accumulated through V6-V10 | "小作坊感" — needed full refresh, not incremental polish |
| Real-bet ROI still 0 data points after 33 weeks | Data accumulation, not code, is the rate-limiter |

V11's actual situation: **clean up what V8/V9/V10 deliberately left open,
ship the frontend premium refresh the user demanded, build the
infrastructure that unblocks V12 decision points** (Layer B for model
retraining, version-hashing for dynamic recs).

Explicitly **NOT** a 12-week sprint. No `v11.w*` tags created; every commit
self-contained. About **3 calendar days of intense work**, ~30 commits, all
on `main`, all pushed.

---

## 2. Tracks (continued from V10)

| Track | Theme | V11 outcome |
|---|---|---|
| **A** | Lineup-aware ROI verdict | ⏳ Still data-gated (V7 cron continues; V12-1 will run the verdict) |
| **B** | Cup-trained model | 🔴 **DO NOT SHIP** verdict (V11 backlog #2 — gate failed 1/2 folds) |
| **D** | Frontend product polish | ✅ P1-FE chain complete (7 patches; full premium refresh) |
| **E** (continued) | Cleanup + infrastructure | ✅ Phase 0 (5 items) + 3/4 backlog closeouts |
| **F** (new) | Model auto-refresh infrastructure | ✅ Layer B propose/deploy/rollback ready for first quarterly firing 2026-07-01 |

V8 W4 (cup-aware verdict) and Gap 3 (national-team Elo integration) both
closed in V11 — both as **negative or null results** with documented
infrastructure preserved as opt-in.

---

## 3. Production state today (`v11.0-shipped`)

| Layer | Default | Notes |
|---|---|---|
| Model backend | CatBoost lineup-aware (V5 W12 + P1#18 ship, unchanged) | **6 versions static now**; Layer B's first firing 2026-07-01 is the unblock |
| Default artifact | `data/v4_model_cat_lineups` | + new ability to redirect via `live_artifact_pointer.json` (Layer B) |
| Daily flow | 2 manual steps + 7 launchd jobs | Same as V10 W4; no new cron in V11 |
| Dashboard tabs | 6 user-facing | 5 from V11 P1-FE#1 (today / WC / single / parlay / pool) + 1 from V11 P1-FE#3 (📜 推荐追溯) |
| Dashboard theme | Dark/light toggle | V11 P1-FE#1 — persisted to localStorage |
| Dashboard i18n | zh / en parity | 14-league team-name dict (355 entries) shipped V11 P1-FE#7 |
| Dynamic recs | Version hash + diff banner | V11 P1-FE#5/#6 — 60s auto-refresh when tab visible |
| Observation recording | Two-gate (unchanged from V9 W3) | V11 didn't touch the recording path |
| CI workflows | 5 (unchanged) | nutmeg-ci / weekly-bench / playwright + 2 manual |
| Cup ablation verdict | 🔴 DO NOT SHIP (V11 backlog #2) | Re-test trigger: API tier upgrade enabling 2015-2020 cup backfill |
| National-team Elo | ✅ Fully integrated end-to-end | All 4 layers wired (V8 W7 + P1#4 + P1#12 + V11 backlog #5) |
| Layer B (auto-retrain) | Ready, first firing 2026-07-01 | Manual review of `--action=propose` → `--action=deploy` |
| Tests | **1410/1410** V4 tests passing | +302 from V10 ship (1108) |

---

## 4. What V11 shipped (chronological)

### Phase 0 — V11 baseline (5 items)

| # | Deliverable | Tests |
|---|---|---:|
| 1 | `scripts/v11_monitor.sh` — trigger-aware status board | n/a (shell script) |
| 2 | `docs/v11_layer_b_design.md` — 567-line Layer B architecture spec | n/a (doc) |
| 3 | `features/stadium_features.py` skeleton | +27 |
| 4 | `features/fatigue_features.py` skeleton | +44 |
| 5 | `notebooks/v11_phase0_mcmc_exploration.{py,ipynb}` + verdict doc | +18 |

**Bonus**: Belgian Pro League coverage close — 14th league added to model
training scope; cron + dashboard defaults updated.

### P1-FE chain — frontend premium refresh (7 patches)

| # | Deliverable | Tests |
|---|---|---:|
| 1 | Design system tokens + dark/light theme + tab cleanup (4 engineer tabs → hidden; 5 user tabs visible) | +24 |
| 2 | Team logos (`nutmeg-ingest-team-logos` CLI) + Chinese names top-5 leagues | +49 |
| 3 | 推荐追溯 timeline tab + outcome chips + 7d/30d/all filter | +37 |
| 4 | Today tab: pool option + risk/EV sliders (3-way segmented controls) | +27 |
| 5 | Dynamic recommendations — version_hash + diff banner + 已更新 badges | +38 |
| 6 | Auto-refresh — Visibility API polling + 上次更新 N秒前 stale label | +15 |
| 7 | Chinese names for all 14 trained leagues (355 dedup'd team names) | +10 |

Visual surface area changed: ~14 SW cache version bumps; ~80 i18n keys per
locale (up from ~10 at V10 ship).

### Backlog closeouts

| # | Item | Outcome |
|---|---|---|
| 2 | V8 W4 cup-aware verdict | 🔴 DO NOT SHIP — 1/2 folds passed (need 3/4); 7 weekly tags of cup code preserved as opt-in CLI |
| 5 | National-team Elo integration | ✅ Closed — `nation_state` now threaded through `WalkForwardConfig` + `cup_ablation` (4-layer wiring complete) |
| 4 | Layer B implementation | ✅ Shipped — propose/deploy/rollback state machine + artifact pointer + serving integration |
| 3 | Lineup-aware 4-week ROI verdict | ⏳ data-gated (V12-1) |

---

## 5. Numbers (V10 ship → V11 ship)

| Metric | V10 ship | V11 ship | Δ |
|---|---:|---:|---:|
| V4 tests passing | 1108 | **1410** | +302 |
| `[project.scripts]` CLIs | 31 | **33** | +2 (`nutmeg-ingest-team-logos`, `nutmeg-auto-retrain`) |
| Dashboard tabs (user-facing) | 7 | 6 | -1 (deleted 4 engineer tabs, added 1 history tab) |
| Dashboard SW cache version | `nutmeg-v1` | `nutmeg-v10-fe-zh-14` | +9 bumps |
| i18n keys per locale | ~10 | ~80 | +70 |
| Default trained leagues (today endpoint) | 2 | **14** | +12 |
| Launchd jobs | 7 | 7 | 0 (Layer B's cron deferred to V12) |
| Documented negative results | 6 | **7** | +1 (cup ablation V11) |
| Production model retraining count | 0 | 0 | 0 (Layer B is the unblock, fires 2026-07-01) |
| Audit gaps closed | (5 open at V11 kickoff) | 3 closed / 2 data-gated | -3 |

**Production CatBoost log-loss vs Pinnacle**: 0.9960 vs 0.9904 (+0.0056) —
**unchanged from V5 W12 baseline.** Model is static; calibration drift is
Layer A's job, model refresh is Layer B's job (first firing pending).

---

## 6. Architectural state at V11 ship

### Two-layer correction stack now complete

```
Raw match features
       ↓
[ Layer B candidate or default artifact ]  ← swapped quarterly via live_artifact_pointer.json
       ↓
   (λ_h, λ_a)
       ↓
[ Layer A T correction ]                    ← swapped weekly via live_T_correction.json
       ↓
  Final 1X2 probabilities
       ↓
       Dashboard / CLI / recommendation pipeline
```

- **Layer A** (V10 W2): post-hoc T scalar; weekly cron `weekly_calibration_check`
- **Layer B** (V11 backlog #4): full model swap; quarterly cron pending V12-7

Both layers honor `mtime`-cached `_artifact_path()` resolution in
`api/routes.py` → no server restart needed for either deploy.

### Frontend = stable feature-complete

Per V11 P1-FE design doc lock-in (2026-05-25 user decisions):
- ✅ Visual polish (premium feel, dark/light theme)
- ✅ Hide all engineer info (no model/parameter/training visible)
- ✅ Only betting recommendation tabs (engineer tabs deleted from frontend)
- ✅ Team logos + Chinese translations
- ✅ NO bet-execution UI (just recommendation surface)
- ✅ Win/loss tracking (推荐追溯 tab with outcome chips)
- ✅ Dynamic recommendations (trigger-driven via version_hash, not slider-driven)
- ✅ Auto-refresh on visible tab

The only remaining frontend Tier 4 items in V12 backlog are low-priority
polish (logo onboarding hint, mobile PWA polish, P/L chart).

---

## 7. The 5-gap V11 audit (entry state vs exit state)

The user's V11 kickoff audit identified 5 gaps after `v8.0-shipped`. V11
exit state:

| Gap | V11 kickoff | V11 exit |
|---|---|---|
| 1. Real-bet ROI = 0 data points | 🔴 (33 weeks accumulated; 0 settled) | ⏳ V12-1 — runs when ≥30 settle |
| 2. Cup model never trained end-to-end | 🟠 (infrastructure ready, ablation never run) | ✅ **CLOSED** — verdict: DO NOT SHIP |
| 3. National-team Elo not integrated into model | 🟠 (data layer shipped V8 W7; build_elo_features falls back to 1500) | ✅ **CLOSED** — fully wired through 4 layers |
| 4. Dashboard 单关/复式 missing record-session checkboxes | (already closed pre-V11 in post-v8 P1#5) | ✅ unchanged |
| 5. CI doesn't run lineup/cup paths; ECE-vs-log-loss mystery | 🟡 (3 retrospectives noted it; "slack week" never came) | ⏳ V12-4 + V12-5 |

3 of 5 closed in V11. 2 remain — both are V12 candidates explicitly listed
in `V12_BACKLOG_DRAFT.md`. Neither is a coding gap; #1 needs data
accumulation, #5 needs investigative ML work.

---

## 8. Tests

**1410/1410 V4 tests passing** at V11 ship:

```bash
PYTHONPATH=apps/api/src:. .venv/bin/pytest tests/v4/
```

V11 added 302 tests, broken down by patch:

| Patch | Tests added | Theme |
|---|---:|---|
| Phase 0 #3 (stadium features) | 27 | feature-builder skeleton |
| Phase 0 #4 (fatigue features) | 44 | feature-builder skeleton |
| Phase 0 #5 (MCMC notebook) | 18 | MCMC module + verdict template |
| P1-FE#1 (theme + tabs) | 24 | structural + accessibility |
| P1-FE#2 (logos + zh top-5) | 49 | dict + endpoint + dashboard wiring |
| P1-FE#3 (推荐追溯 tab) | 37 | endpoint + outcome chips + UI |
| P1-FE#4 (today pool + sliders) | 27 | schema + pool builder + slider wiring |
| P1-FE#5 (dynamic recs) | 38 | version hash + diff helper + UI badges |
| P1-FE#6 (auto-refresh) | 15 | polling + visibility hook |
| P1-FE#7 (zh 14 leagues) | 10 | dict + coverage |
| Backlog #2 (cup ablation) | 0 | verdict-only |
| Backlog #5 (nation Elo passthrough) | 7 | WalkForwardConfig + CLI flag |
| Backlog #4 (Layer B) | 45 | retrain module + CLI + serving |
| Other (i18n key updates etc) | 6 | absorbed in adjacent patches |
| **Total** | **+302** | |

No regressions. Zero V4 tests removed.

---

## 9. Tags + milestones

| Tag | Date | Meaning |
|-----|------|---------|
| `v10.0-shipped` | 2026-05-25 | V10 closeout — WC sprint + Layer A live |
| `v11.0-shipped` | 2026-05-26 | V11 closeout (this handoff) — frontend refresh + backlog #2/#4/#5 |

**No weekly tags within V11** — all work was issue-driven, not week-driven.
Git log from `v10.0-shipped` to `v11.0-shipped` is the complete record (29
commits in V11 + early V11 work that pre-dated the v10.0-shipped tag).

---

## 10. Companion files V11 produced

- `docs/v11_retrospective.md` — full V11 closeout retro
- `docs/V12_BACKLOG_DRAFT.md` — 20-item V12 candidate list, 5 tiers
- `docs/v11_layer_b_design.md` — Layer B architecture spec (Phase 0 #2)
- `docs/v11_p1_fe_design.md` — P1-FE chain design + 12 user-confirmed decisions
- `docs/v11_phase0_league_coverage_audit.md` — 14-league coverage expansion
- `docs/v11_phase0_mcmc_report.md` — auto-generated MCMC verdict
- `docs/v8_w4_cup_aware_verdict.md` — V8 W4 closeout (DO NOT SHIP)
- `docs/v11_cup_ablation_20260526.md` — cup-ablation auto-gen card
- `docs/v11_nation_elo_ablation_20260526.md` — nation-Elo passthrough card
- `docs/v11_backlog5_nation_elo_verdict.md` — Gap 3 closeout

---

## 11. V12 backlog (deferred from V11)

See `docs/V12_BACKLOG_DRAFT.md` for the full 5-tier breakdown. Headlines:

### Tier 1 — data-gated (cannot be code-fixed)
1. **V12-1** Lineup-aware 4-week ROI verdict (needs ≥30 settle rows)
2. **V12-2** Layer B first quarterly proposal (2026-07-01)
3. **V12-3** Live-vs-backtest gap analysis (when enough real data)

### Tier 2 — V8/V9/V10 leftovers, ready to do
4. CI runs `--with-lineups` / `--with-cup-data` (~1-2 d)
5. ECE-vs-log-loss mystery (per-bucket Brier audit, ~2-3 d)
6. Layer B cleanup policy + auto-rollback cron (~1 d each)

### Tier 3 — V12 research
8-12: NumPyro NUTS, WC-CatBoost unification, stadium/fatigue
features populated, alias extensions, national-team test set

### Recommended V12 start
- Week 1: V12-1 + V12-2 (data-gated verdicts)
- Week 2: V12-4 / V12-6 / V12-7 (cleanups)
- Week 3+: branch on the V12-1 + V12-2 verdicts

---

## 12. Next decision point

**2026-07-01 — Layer B first quarterly firing**.

Process:
1. Cron fires `nutmeg-auto-retrain --action=propose --apply`
2. Output: `docs/quarterly/retrain_2026-Q3.md`
3. User reads the verdict card + ship-gate evaluation
4. If passed gates + manual review approves:
   ```bash
   nutmeg-auto-retrain --action=deploy --apply \
     --candidate data/v4_model_layer_b/v_2026-Q3 \
     --artifact-base data/v4_model_cat_lineups
   ```
5. 4-week observation period; auto-rollback weekly check active (V12-7 needs to ship first)

Between now and that date:
- Project is in **maintenance + waiting on real-bet data** mode
- Existing cron jobs continue (daily_odds + daily_recommend + weekly checks)
- No new development required unless user surfaces specific demand

---

## 13. What V11 deliberately did NOT do

These are documented choices, not oversights:

- **Did NOT retrain production model.** V5 W12 CatBoost stays as default;
  Layer B's first manual deploy is gated on the 2026-07-01 cron + user
  review.
- **Did NOT ship cup-aware artifact.** Ablation said no; the 7 weekly
  tags of cup code remain as opt-in CLIs.
- **Did NOT invest in PyMC/NumPyro.** MCMC exploration showed borderline
  convergence + ~6 milli-pt improvement on one season; deferred to
  V12-8 with multi-season verification.
- **Did NOT implement Layer B's quarterly cron + auto-rollback weekly
  check.** Both deferred until at least one manual deploy has been
  observed (V12-7).
- **Did NOT unify WC model path with general CatBoost.** V10 Track B's
  separate `NationalTeamModel` continues; merging is V12-9.
- **Did NOT populate stadium / fatigue features.** Skeletons + tests
  shipped (V11 Phase 0); actual data backing them is V12-10.

---

## 14. Welcome to V11 closeout state

The project is in a stable, clean state:
- All Phase 0 work done
- All P1-FE patches shipped and tested
- 3 of 4 V11 backlog items closed; 1 data-gated
- Layer B infrastructure ready for its first quarterly firing
- 1410/1410 V4 tests green
- Repo on `main`; all pushed; tagged `v11.0-shipped`
- No stale branches; no half-finished work

The next decision point is **2026-07-01** (Layer B first firing). Until
then, the project is intentionally idle on the code side and waiting on
the data side (real-bet observation accumulation since V7).

If picking up the project for V12, start at `docs/V12_BACKLOG_DRAFT.md`.

---

**V11 closed. v11.0-shipped at HEAD.**
