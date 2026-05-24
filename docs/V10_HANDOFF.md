# Nutmeg V10 Handoff

_Last updated: 2026-05-25 (V10 W0 — launched)._

Single source of truth for V10 — the 4-week dual-track version
that opened on 3 simultaneous triggers and a hard external deadline
(2026 WC starts 2026-06-11). Read this first when picking up the
project; then [V10_ROADMAP.md](V10_ROADMAP.md) for the week-by-week
plan; then [V9_HANDOFF.md](V9_HANDOFF.md) for what shipped before V10.

---

## 1. What V10 is

V10 starts from a different place than V5-V8 (and even V9):

| Signal entering V10 | What it meant |
|---|---|
| 3 V10_ROADMAP_DRAFT triggers fired simultaneously (UX gap + cross-source caveat + WC deadline) | Real product demand, not "we should ship V10 because V9 finished" |
| post-v9 P1 chain delivered 25 patches between V9 ship and V10 W0 | Project maintenance + opportunistic improvements work — `post_v9_p1_index.md` is the running record |
| Local pipeline running via launchd (P1#16) + cards via weekly_bench (P1#29 fixed); WC sprint requires data ingest only | Data + ops layers ready; just need targeted code work |
| 2026-06-11 hard deadline | 17 days from V10 W0 → Track B (WC) must ship by W3 W3 day 7 |

V10 actual situation: **product polish + ML closeout + opportunistic
WC sprint**. Explicitly 4 weeks (not 12), two parallel tracks
(Track A user-facing, Track B WC).

W0 closeout: rename V10_ROADMAP_DRAFT → V10_ROADMAP, V10_HANDOFF_TEMPLATE
→ V10_HANDOFF; update post_v9_p1_index to record V10 trigger.

## 2. Tracks

| Track | Theme | V10 status |
|---|---|---|
| **A** | UX rework + Layer A auto-T calibration | 🔄 W1 in progress |
| **B** | WC sprint (data + model + dashboard) | 🔄 W1 Day 1 starting |
| **D** | Product polish (carried from V9) | Subsumed into Track A |
| **E** | Cleanup + tech debt | post-v9 P1 chain (closed at P1#30) |

## 3. Production state today (V10 W0)

| Layer | Default | Notes |
|---|---|---|
| Model backend | CatBoost (V5 W12, lineup-aware via P1#18) | Unchanged for 4 versions; will remain unchanged through V10 (Layer A only adjusts T) |
| Default artifact | `data/v4_model_cat_lineups` | P1#18 ship; P1#21 added cross-source caveat |
| Daily flow | 2 manual steps + 4 launchd jobs (P1#16, P1#24) | daily_odds + daily_recommend + weekly_settle + weekly_gate |
| Dashboard tabs | 7 | + 1 (WC) targeted for V10 W3 |
| Observation recording | Two-gate (env + per-request) | unchanged |
| CI workflows | 5 (nutmeg-ci + weekly-bench + playwright + 2 manual-only) | unchanged |
| Cup ablation | NEGATIVE-CLOSED (P1#20) | National-team data is fundamentally different from domestic cup — not a re-opening |
| Tests | 803 + ~50 from P1 chain ≈ 850 passing | V10 targets 880+ |

## 4. What V10 will ship (week by week)

### W0 — Launch ✅ (this commit)

- Renamed `V10_ROADMAP_DRAFT.md` → `V10_ROADMAP.md` with full 4-week
  dual-track plan filled in
- Renamed `V10_HANDOFF_TEMPLATE.md` → this file
- Updated `post_v9_p1_index.md` to mark V10 trigger fired
- W0 marker tag: `v10.w0`

### W1 — Parallel start

**Track A**: UX wireframe + dashboard.html rewrite (default-recommendation flow)

**Track B**: WC data ingest (fixtures + odds for WC 2018 + 2022)

Target ship: `v10.w1`, 2026-05-31.

### W2 — Build

**Track A**: `nutmeg.v4.observation.auto_calibration` module + cron + tests

**Track B**: `nutmeg.v4.model.national_team_predict` module + walk-forward validation

Target ship: `v10.w2`, 2026-06-07.

### W3 — Integrate

**Track A**: full regression + docs update

**Track B**: dashboard "WC 预测" tab + endpoint + 2026 dry run

Target ship: `v10.w3`, 2026-06-10 (1 day before WC starts).

### W4 — WC live week + monitoring

Daily WC cron + settlement; first real Layer A auto-T cycle.

Target ship: `v10.0-shipped`, 2026-06-21.

## 5. Numbers (V9 → V10 W0)

| Metric | V9 ship | V10 W0 | V10 target |
|---|---:|---:|---:|
| V4 tests passing | 803 | ~850 (from P1 chain) | 880+ |
| CLIs in pyproject | 25 | ~29 (P1#17 + P1#23 + nutmeg-roi-backtest + nutmeg-live-vs-backtest enhancements) | 30-31 |
| Dashboard tabs | 7 | 7 | 8 (+ WC) |
| Launchd jobs | 4 | 4 (after P1#24) | 5 (+ weekly_calibration_check) |
| GH workflows | 5 | 5 | 5 |
| Lineup ROI verdict | shipped w/ caveat | unchanged | Track A auto-T validates over W4 |
| Production model retraining count | 0 | 0 | 0 (Layer A is T-only) |
| Documented negative results | 6 | 6 | 6 or 7 (only if WC model walk-forward fails) |

## 6. V10 W0 — what changed in this commit

```
docs/V10_ROADMAP_DRAFT.md → docs/V10_ROADMAP.md         (rename + rewrite with 4-week plan)
docs/V10_HANDOFF_TEMPLATE.md → docs/V10_HANDOFF.md      (rename + rewrite with W0 status)
docs/post_v9_p1_index.md                                (mark V10 trigger fired, close P1 chain at #30)
```

## 7. V11 backlog (deferred from V10)

### Data-gated or research-required

1. **Q1 model improvements (Path 1-5)** — Path 3 (per-stadium home
   advantage) + Path 4 (fatigue) are low-hanging; Path 1 (live
   pre-kickoff lineup) is highest ROI but requires API tier upgrade;
   Path 2 (player-weighted injuries) needs player ratings data;
   Path 5 (Pinnacle Bayesian blend) is the "easy backstop"
2. **Q2 Layer B (quarterly walk-forward auto-retrain)** — should
   follow V10 Layer A validation; cheap path first, expensive path
   only if cheap doesn't drift-correct enough

### Operational / coverage

3. **New league coverage** (中超 / K-League / 巴甲 / 沙特联) — only
   if user demand surfaces
4. **In-play / live betting features** — fundamentally different
   problem; V12+ candidate at earliest

### V11 trigger condition

V11 starts when ≥ 1:
- WC verdict (2026-07-15 latest) shows model failed or succeeded
  meaningfully vs Pinnacle (informs next model investment)
- Cross-source caveat resolved (4 weeks of live cron data agrees
  with one of {football-data, Odds API} verdicts)
- New product surface from user

## 8. Tests

**~850/~850 V4 tests passing** at V10 W0:

```bash
PYTHONPATH=apps/api/src python -m pytest tests/v4/ -q
```

V10 will add:
- `tests/v4/test_auto_calibration.py` (Track A Layer A, ~15 tests)
- `tests/v4/test_national_team_predict.py` (Track B model, ~10 tests)
- `tests/v4/test_wc_predictions_endpoint.py` (Track B dashboard, ~5 tests)
- ~10 tests for new UX flow

## 9. Tags + milestones

| Tag | Date | Meaning |
|-----|------|---------|
| `v9.0-shipped` | 2026-05-?? | V9 closeout (entry point for V10) |
| `v9.0-shipped → V10 W0` | (post-v9 P1#6 → P1#30) | 25 P1 patches; see `post_v9_p1_index.md` |
| `v10.w0` | 2026-05-25 | Launch — templates → live docs (this commit) |
| `v10.w1` | 2026-05-31 (target) | UX rework + WC data ingested |
| `v10.w2` | 2026-06-07 (target) | Layer A auto-T + WC model |
| `v10.w3` | 2026-06-10 (target) | WC dashboard tab + dry run |
| `v10.0-shipped` | 2026-06-21 (target) | V10 closeout, including 1 WC live week |

The git log from `v9.0-shipped` to `v10.0-shipped` is the complete
record — both the post-v9 P1 chain and V10 W1-W4 weeks.

## 10. Companion files V10 will produce

- `docs/V11_ROADMAP_DRAFT.md` — at V10 ship, drafted with refreshed triggers
- `docs/V11_HANDOFF_TEMPLATE.md` — same template, V11-numbered
- `docs/v10_retrospective.md` — at V10 ship
- `docs/v10_w<N>_<topic>.md` per week
- `docs/v10_w<N>_<topic>_negative.md` only if Track B fails walk-forward

---

**Welcome to V10. The 4 weeks have started.**
