# Nutmeg V11 Roadmap (Draft)

_Drafted 2026-05-25, after V10 ship. **Event-driven, not calendar-
driven** — V11 W1 starts when ≥1 of 4 data triggers fires, not by date.
Phase 0 (now → ~2026-07-19) is the "wait and pre-fetch" period._

---

## 1. Why V11 is different

V5 / V6 / V7 / V8 were 12-week sprints with fixed roadmaps. V10 was
4 weeks with a hard external deadline (WC 2026-06-11). **V11 has no
deadline and no fixed scope** — it cannot be planned until the WC
tournament concludes + Layer A has run a few real cycles.

So V11's structure is:

```
Phase 0  (NOW → 2026-07-19)
    Wait for data + pre-fetch low-risk groundwork
                        ↓
Phase 1  (1 week after 2026-07-19)
    Read 4 trigger sources → pick Branch A/B/C
                        ↓
Phase 2  (4 weeks)
    Execute the chosen branch → ship v11.0-shipped
```

Total V11 calendar: **~6-8 weeks** (1 week decision + 4 weeks execution
+ 1-2 weeks buffer), NOT 12. V11 is a **patch-level minor version**.

---

## 2. Phase 0 — What to do during the wait (~ 6-8 weeks)

### 2a. Watch the 4 trigger sources

| Source | What to read | Where it lands | Verdict signal |
|---|---|---|---|
| WC 2026 model hit-rate | `docs/wc/wc_report_<YYYY-MM-DD>.md` (V10 W4 daily cron) | One file per day | Tournament aggregate hit-rate ≥55% / 45-55% / <45% |
| Layer A auto-T cycles | `docs/weekly/auto_calibration_<YYYY-WNN>.md` (V10 W2 weekly cron) | One file per Monday | 4+ cycles complete; check if propose / deploy / rollback fires |
| Lineup ROI 4-week verdict | `nutmeg-ab-report --weeks 4 --db data/v4_observation.db` | Manual run weekly | Need ≥60 settlements per arm |
| Cross-source caveat | Live cron data vs P1#17 backtest | `docs/weekly/p1_19_gate_<YYYY-WNN>.md` | ROI gap shrinks below 30pp |

A single command surface for monitoring (Phase 0 deliverable):
```bash
./scripts/v11_monitor.sh   # not yet built — Phase 0 work item
```

### 2b. Pre-fetch groundwork (no risk, multi-branch reusable)

These are work items that ARE useful in ≥2 of the 3 branches, so worth
doing during the wait:

| Item | Used in | Effort |
|---|---|---|
| **Layer B scoping doc** (`docs/v11_layer_b_design.md`) — architecture + ship gate + rollback semantics | Branch A, B, C | 2-3 hr |
| **Path 3 stadium-features module skeleton** (`features/stadium_features.py` — coordinate / capacity / altitude / weather priors) | Branch B | 2-3 hr |
| **Path 4 fatigue-features module skeleton** (`features/fatigue_features.py` — 3-day / 5-day / 7-day rest intervals) | Branch B | 2-3 hr |
| **MCMC Bayesian Poisson notebook** (research-only, `notebooks/v11_mcmc_exploration.ipynb`) — fit PyMC model on WC 2018+2022 historical data, compare posterior to LightGBM | Branch A | 3-4 hr |
| **V10 retrospective `{XX}` placeholders** filled in weekly as data lands | All branches | 30 min/week |

**NOT doing in Phase 0**: production code changes. Anything that goes
into `apps/api/src/nutmeg/v4/` is Phase 2 work, gated on the branch
decision.

---

## 3. Phase 1 — The branch decision (1 week, ~2026-07-19 → 2026-07-26)

Read all 4 trigger sources, then pick the V11 theme based on the
**dominant signal**:

### Decision tree

```
WC tournament concluded?
├── YES + hit-rate ≥ 55%  →  Branch A (national-team expansion + MCMC)
├── YES + 45% ≤ HR < 55%  →  Branch B (domestic Layer B + Path 3/4)
├── YES + HR < 45%        →  Branch C (negative postmortem + Layer B)
└── NO (tournament delayed / data corrupt) → Branch B default
```

The WC hit-rate is the primary signal because:
- It's the most resource-intensive investment from V10
- It directly determines whether national-team expansion makes sense
- The other 3 signals refine the branch's W3-W4 weeks, not the theme

---

## 4. Phase 2 — Branch execution

### Branch A — National-team expansion + MCMC

**Trigger**: WC hit-rate ≥ 55%, log-loss < 0.95

**Theme**: National-team competitions are year-round (Euro qualifiers,
Copa America qualifiers, Nations League, friendlies). If our WC model
works, replicate the data layer + LightGBM × Pinnacle blend pattern
across all of them.

| Week | Deliverable |
|---|---|
| W1 | National-team competition registry — add to `competitions.py`: UEFA Euro qual / UEFA Nations League / CONMEBOL qual / AFC qual / CONCACAF qual / Friendlies; ingest historical fixtures (~500-1500 matches per tournament) |
| W2 | **MCMC Bayesian Poisson model** — PyMC / NumPyro fit on national-team data ONLY (not production CatBoost). Hierarchical: country-level latent attack/defence + tournament-level shrinkage. Produces 1X2 + handicap probs. CLI: `nutmeg-nt-predict-mcmc --competition EURO_QUAL --date YYYY-MM-DD`. Decision: when MCMC + Elo blend beats Elo-only by ≥0.005 log-loss → ship MCMC as default for that competition. |
| W3 | Dashboard "国家队" tab — replaces / augments WC tab; groups by continent + tournament. Auto-fetches today's national-team matches from API-Football. |
| W4 | Layer B groundwork (see Branch B W1 for design; here we just ship the schema + journal, not the auto-retrain trigger yet). Ship `v11.0-shipped`. |

**Ship gate**:
- MCMC component: ≥0.005 log-loss improvement vs Elo-only on held-out qualifier matches
- Overall: dashboard tab functional + no production regression

### Branch B — Domestic Layer B + Path 3/4

**Trigger**: WC hit-rate 45-55% (model behaved as walk-forward predicted)

**Theme**: WC didn't change anything; refocus on domestic improvements
that the V10 W2 retrospective backlog flagged.

| Week | Deliverable |
|---|---|
| W1 | **Layer B: quarterly auto-retrain pipeline** — `apps/api/src/nutmeg/v4/observation/auto_retrain.py` mirrors `auto_calibration.py`'s structure. Triggers: every quarter OR after X new settled rows. Ship gate: ≥0.002 log-loss improvement + bootstrap p ≤ 0.05 on held-out tail. Auto-rollback: same pattern as Layer A but on the full artifact directory. New launchd job: `com.nutmeg.quarterly_retrain` (1st of month at 06:00, Q1 = Jan/Apr/Jul/Oct). |
| W2 | Path 3 stadium home-advantage ablation — feature derived from API-Football venue.id (altitude / weather prior / capacity). Walk-forward ablation; target: -0.001 to -0.003 log-loss. Decision: ship or document. |
| W3 | Path 4 fatigue ablation — features: days-since-last-match (3/5/7 buckets) + Europa/UCL midweek penalty. Walk-forward ablation; target: -0.001 to -0.003 log-loss. Decision: ship or document. |
| W4 | Layer A real-data retrospective + Layer B first run + ship `v11.0-shipped`. |

**Ship gate** (per item):
- Layer B: pipeline implemented + 1 successful end-to-end dry-run on historical data
- Path 3: ablation reports verdict ≥ -0.001 log-loss to ship; <-0.001 means document-as-negative
- Path 4: same threshold

### Branch C — Negative postmortem + Layer B + defensive

**Trigger**: WC hit-rate < 45% (model failed)

**Theme**: Honest post-mortem + don't let it block the domestic
improvements that still make sense.

| Week | Deliverable |
|---|---|
| W1 | `docs/v11_wc_negative_postmortem.md` — failure analysis: small-sample? Pinnacle blend miscalibrated? Bracket structure (KO vs group) effects? Walk-forward overfit to 2018+2022 idiosyncrasies? Each hypothesis with evidence. |
| W2 | Dashboard WC tab → mark "experimental" + add prominent caveat banner. Schedule national-team Elo refresh cron disable (post-WC, eloratings.net updates less critical). |
| W3 | Layer B (same as Branch B W1) — this still ships because it's orthogonal to WC's failure. |
| W4 | Path 5 (Pinnacle Bayesian blend on **domestic** models, as a defensive backstop). Ship `v11.0-shipped`. |

**Ship gate**:
- Postmortem doc reviewed
- Dashboard caveat live
- Layer B operational

---

## 5. Model architecture decisions (固化 from 2026-05-25 discussion)

User explicitly accepted these positions in the V11 design discussion:

| Component | Decision | Reasoning |
|---|---|---|
| Dixon-Coles (score grid) | **Keep unchanged** | Just a score-distribution layer; not the ML model. Stable since V4. |
| CatBoost lineup-aware (production) | **Keep unchanged** | 93% of Pinnacle log-loss ceiling. 6 versions of failed replacement attempts (V5 W5/W6/W9). Remaining gap is information asymmetry (lineup-late info), not algorithm. |
| **MCMC** | **Limited application — Branch A only**. WC / Cup / National-team scope ONLY. Production CatBoost untouched. | Value: uncertainty quantification + small-sample handling. Cost too high for main production model (6-8 weeks for <0.001 log-loss improvement). |
| **Multi-agent simulation** | **Never** | Wrong product fit (we're pre-match, not in-play). Wrong data assumption (we don't have StatsBomb-level event data). No academic or industry production precedent for pre-match 1X2 betting. |
| **Layer B (quarterly auto-retrain)** | **Adopted** as V11 candidate (Branch A W4, Branch B W1, Branch C W3) | Higher-impact than MCMC for production. Same architectural pattern as Layer A (ship gate + journal + auto-rollback) but on full artifact instead of T scalar. |

This table is the V11 north star for ML architecture. If a Phase 2
decision contradicts it, we reopen this discussion.

---

## 6. Out of scope for V11 (deferred to V12+)

| Item | Why deferred |
|---|---|
| In-play / live-odds betting | Fundamentally different product; 竞彩 doesn't allow it |
| New domestic league coverage (中超 / K-League / etc.) | No user demand surfaced yet |
| Player-rating / transfer-market features | Requires StatsBomb / Opta tier data |
| Stratagem-style ensemble (5+ models stacked) | V5 W6 stacking tried, ablation failed; not worth re-trying without new evidence |
| Multi-agent simulation | Permanent rejection (see §5) |
| API tier upgrade for live lineups | Costly + user not signaling demand; revisit if domestic ROI verdict needs it |

---

## 7. Phase 0 work items (can start now)

I can begin these in this session if you confirm — they're low-risk and
useful regardless of branch:

| Item | Effort | Branch coverage |
|---|---|---|
| **V11_ROADMAP_DRAFT.md** (this file) | done | All |
| `scripts/v11_monitor.sh` — one-command status check for the 4 triggers | 1 hr | All |
| `docs/v11_layer_b_design.md` — full architecture doc for Layer B (mirrors V10 W2 Day 1's design quality) | 2-3 hr | A, B, C |
| `apps/api/src/nutmeg/v4/features/stadium_features.py` skeleton + tests | 2-3 hr | B (likely; 65% prior on Branch B) |
| `apps/api/src/nutmeg/v4/features/fatigue_features.py` skeleton + tests | 2-3 hr | B |
| `notebooks/v11_mcmc_exploration.ipynb` — research notebook | 3-4 hr | A only (~25% prior) |

Suggested ordering:
1. **v11_monitor.sh** (1 hr) — needed for Phase 0 weekly check-ins regardless
2. **v11_layer_b_design.md** (2-3 hr) — Layer B is the most cross-branch valuable
3. **stadium_features.py + fatigue_features.py** (4-6 hr) — 65% prior these get used in Branch B
4. **MCMC notebook** (3-4 hr) — lowest priority; only matters if Branch A; safer to wait until WC verdict
5. **Retrospective fill-in** (ongoing weekly task, ~30 min)

Total Phase 0 estimated: **8-13 hours** of work spread over **~8 weeks** of
wait time. Plenty of buffer.

---

## 8. V11 ship triggers (≥ 1 required to open V11 W1)

V11 W1 (= branch execution) starts when at least one of:

1. WC 2026 tournament concludes (final on 2026-07-19) — primary trigger
2. ≥ 4 Layer A weekly cycles completed (= 4 Mondays past first cron run)
3. ≥ 60 settlements per arm in observation DB
4. New user-surfaced product gap (rare; would override the 3 above)

V11 W1 cannot start before 2026-07-19 even if other triggers fire — WC
verdict is the dominant decision input. If WC tournament gets cancelled
or postponed, default to Branch B.

---

## 9. Honest acknowledgments

- This roadmap may be **wrong**. Three branches don't cover everything;
  reality might be "Branch B but with WC hit-rate 60% so do MCMC AND
  Path 3" — fine, recompose at Phase 1 decision time.
- Layer B's ship gate (≥0.002 log-loss) is **a guess**. We'll calibrate
  at Branch's W1 after seeing actual walk-forward distributions.
- **Phase 0 risk**: I'm spending 10+ hours on pre-fetch work that may
  go unused if WC hit-rate is exactly 56% and we end up in Branch A,
  not B. Acceptable risk — Layer B design doc is multi-branch reusable,
  and stadium/fatigue modules can be archived as `v11_archive/` if
  unused.
- This is a **draft**. Will be promoted to `V11_ROADMAP.md` at V11 W0
  (immediately after Phase 1 decision).

---

## 10. Next concrete step

If you approve this draft, the next concrete commit is:

```
commit: docs(v11): draft roadmap + branch structure
  - docs/V11_ROADMAP_DRAFT.md (this file)
  - docs/v11_monitoring_dashboard.md (point readers at the 4 watch sources)
  - tasks/v11_phase_0_checklist.md (operational checklist for the wait)
```

After that, you decide whether to start Phase 0 work items immediately
or just let the wait period play out.
