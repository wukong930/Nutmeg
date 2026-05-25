# V10 Retrospective — Layer A Calibration + WC 2026 Sprint

_Skeleton planted: 2026-05-25 (W4 prep — fill in after tournament ends)._

V10 is the first version with a **hard external deadline** (2026-06-11
WC kickoff). This skeleton is committed pre-tournament so post-WC
fill-in is just numbers + verdict, not creative writing.

---

## 1. Sprint TL;DR — fill in post-WC

**One paragraph.** What V10 was, what it shipped, the headline number,
and whether the WC model worked.

Template:

> V10 was a 4-week dual-track version: Track A closed the recommend →
> settle → learn loop with Layer A post-hoc T calibration (auto-rollback
> safety net included); Track B opened FIFA WC 2026 as a new prediction
> surface. The full project shipped 17 days ahead of schedule
> (`v10.w3` tagged 2026-05-25; W4 prep work landed by 2026-05-26).
> WC final-week hit-rate: **{XX}% over {N} matches** (target 50-52% per
> walk-forward, baseline 33% random). Layer A weekly cycles ran
> **{Y}** times during the tournament window with **{Z}** auto-T
> deploys + **{R}** auto-rollbacks. Production model: still V5 W12
> CatBoost-lineup-aware (unchanged for 6 versions in a row).

---

## 2. What V10 shipped (week-by-week recap)

### W0 (2026-05-25 → on target)

- Renamed `V10_ROADMAP_DRAFT.md → V10_ROADMAP.md`
- Renamed `V10_HANDOFF_TEMPLATE.md → V10_HANDOFF.md`
- Marked V10 trigger fired in `post_v9_p1_index.md`

### W1 — Parallel start (2026-05-25 → 6 days ahead)

**Track A (UX)**: 4 days
- Day 1: dashboard UX audit + wireframe
- Day 2: `/v4/today-recommendations` endpoint
- Day 3: 今日推荐 tab (default landing) — auto-loads recs on page open
- Day 4: 高级 ▾ fold for legacy 7 tabs

**Track B (WC sprint)**: 5 days
- Day 1: ingest WC 2018+2022 fixtures + odds
- Day 2: clubelo → eloratings.net fallback (P1#10 fix paid dividends); WC training join
- Day 3: WC model + walk-forward (log-loss 0.9802 vs 1.00 baseline)
- Day 4: `nutmeg-wc-predict` CLI + 128-row retrain
- Day 5: WC predictions endpoint + dashboard tab + dry run → ship

### W2 — Layer A end-to-end (2026-05-25 → 13 days ahead)

5-day sprint, 75 new tests, ~2275 LoC:
- Day 1: `observation.auto_calibration` core (post-T scaling, holdout fit, bootstrap p-value, journal)
- Day 2: `nutmeg-auto-calibration` CLI (propose / deploy / rollback)
- Day 3: artifact-side `live_T_correction.json` + serving wiring across 5 endpoints (mtime-cached)
- Day 4: auto-rollback safety net + `com.nutmeg.weekly_calibration_check` Mon 03:00 launchd
- Day 5: e2e integration tests + tag `v10.w2`

### W3 — Integrate (2026-05-25 → 16 days ahead)

- Fixed 4 carry-over Playwright failures (tab count 7→9 + WCAG `aria-required-children`)
- WC 2026 dry-run on 72 cached fixtures (15 opening-week predictions, all rational)
- Tag `v10.w3` shipped; **1074/1074 V4 tests pass INCLUDING Playwright**

### W4 — WC live prep (2026-05-25 → finished pre-kickoff)

- Day 1: `wc_predictions` audit log table + `nutmeg-wc-predict --record-to`
- Day 2: `nutmeg-wc-settle` (API-Football → outcomes) + `nutmeg-wc-report` (hit-rate / log-loss summary) + 2 launchd jobs
- Day 3: `scripts/wc_preflight.sh` (7-check pre-kickoff verification) + this retrospective skeleton

W4 live work (2026-06-11 → 2026-06-21): reactive only — daily cron
runs, weekly Layer A check on Monday, monitor for surprises.

---

## 3. Numbers — fill in post-WC

### Tests

| Snapshot | V4 non-Playwright | Playwright | WCAG AA violations |
|---|---:|---:|---:|
| V9 ship | 803 | (none) | 1 |
| V10 W0 | ~850 | 13 | 1 |
| V10 W1 | 1057 | 13 (4 failing) | 1 |
| V10 W2 | 1065 | 13 (4 failing) | 1 |
| V10 W3 | 1057 | 17 (all passing) | 0 |
| V10 W4 | **{XX}** | **{17}** | **0** (target) |

### CLIs

| Snapshot | CLIs in `pyproject.toml` |
|---|---:|
| V9 ship | 25 |
| V10 W2 | 31 (+ wc-predict + auto-calibration) |
| V10 W4 | **33** (+ wc-settle + wc-report) |

### Launchd jobs

| Snapshot | Jobs |
|---|---:|
| V9 ship | 4 (3 daily + 1 weekly) |
| V10 W2 | 5 (+ weekly_calibration_check) |
| V10 W4 | **7** (+ daily_wc_predict + daily_wc_settle) |

### WC 2026 model performance — fill in post-tournament

| Metric | Walk-forward target | Live actual |
|---|---:|---:|
| Hit-rate (top-tip = outcome) | 50-52% | `___%` over `__` matches |
| Log-loss | 0.9802 (WC 2022 cutoff) | `_.____` |
| Pinnacle ceiling (when odds available) | ~0.95 | `_.____` |
| Fraction matches with Pinnacle blend | unknown pre-tournament | `___%` |

### Layer A activity during WC window

| Metric | Count |
|---|---:|
| Weekly cron runs | `__` |
| Propose journal entries | `__` |
| Deploy actions (manual decision) | `__` |
| Auto-rollbacks fired | `__` |
| Final deployed T (if any) | `_.____` |

---

## 4. What worked

_Fill in 3-5 wins post-WC. Pre-WC candidate placeholders:_

1. **Eloratings.net fallback (P1#10 → V10 W1 Day 2)** — clubelo's
   per-country endpoints turned out to return empty data, but the
   eloratings.net World.tsv ships 244 nations in one HTTP call. All
   48 WC 2026 participants covered with no fallbacks.
2. **17-day lead on the WC deadline** — finishing W1-W3 in 1 day
   each meant W4 was prep-only, not crunch.
3. **Layer A's auto-rollback safety net** — fires before propose, so
   even a bad initial deploy can self-correct within a week without
   manual intervention.

_TODO post-tournament:_
- WC model actually getting calls right (or not — honestly document)
- Pinnacle blend behavior once odds opened
- Whether Layer A actually adjusted T during the tournament

## 5. What didn't work / surprises

_Fill in 2-4 candid lessons post-WC. Pre-WC candidates:_

1. **Cup ablation (P1#20) closed negative** — UCL/UEL parquets were
   ingested in V8 but a separate cup-aware artifact training showed
   no log-loss improvement vs default. National-team WC is a
   different problem (different teams, different format) so V10
   ran it as a separate track instead of resurrecting cup ablation.

_TODO post-tournament:_
- Did any week's auto-T deploy improve OR hurt log-loss vs identity?
- Were there fixtures where our top-tip was crazy-wrong + we should
  have caught it?

## 6. Production state post-V10

| Layer | State after V10 | Unchanged since |
|---|---|---|
| Model backend | CatBoost (V5 W12, lineup-aware via P1#18) | V5 W12 |
| Default artifact | `data/v4_model_cat_lineups` | P1#18 |
| Layer A post-T | **NEW** in V10 W2 — opt-in via `live_T_correction.json` | — |
| Daily cron | 5 jobs (2 daily domestic + 1 weekly settle + 1 weekly gate + 1 weekly calib) | — |
| WC cron | **NEW** in V10 W4 — 2 daily jobs (predict + settle) | — |
| Dashboard tabs | 9 (+ 今日推荐 + WC 2026) | V10 W1 |
| Observation tables | `recommendation_sessions`, `single_predictions`, `parlay_recommendations`, `match_outcomes`, `settlements`, `calibration_journal`, `wc_predictions` | V10 W4 (latest add) |

## 7. V11 backlog — refined post-V10

_Pre-WC sketch; revise based on what V10 actually surfaced:_

### Already deferred from V10

1. **Q1 model improvements (Path 1-5)** — Path 3 (per-stadium home
   advantage) + Path 4 (fatigue) are low-hanging.
2. **Q2 Layer B (quarterly walk-forward auto-retrain)** — only worth
   doing if Layer A's first real cycle shows T-only can't keep up
   with drift.
3. **In-play / live betting features** — V12+ at earliest.

### Likely new in V11 (depends on WC verdict)

- _If WC model hit-rate >55%:_ port the eloratings.net data layer
  to feed national-team leagues (Euro qualifiers, CONMEBOL qualifiers,
  Nations League) for forward-looking predictions.
- _If hit-rate 45-55%:_ document as "WC model works at expected
  level; expand coverage opportunistically."
- _If hit-rate <45%:_ flag the WC model as failed, document negative
  result, fall back to domestic-only product for V11.

## 8. Sign-off — fill in post-WC

- **V10 shipped**: 2026-06-`__` (tag `v10.0-shipped`)
- **Final ahead-of-schedule total**: `__` days
- **Recommended V11 start date**: 2026-`____-__`
