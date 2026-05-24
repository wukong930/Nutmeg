# V10 Roadmap — **DRAFT** (no trigger fired yet, project in maintenance mode)

_Created at post-v9 P1#25. **This is a placeholder.** V10 has not
started. It will not start "because V9 finished" — V9_ROADMAP and
v9_retrospective both explicitly built that decision into the
project's contract._

## Status: stand-by

| Decision | State |
|---|---|
| Is V10 active? | **No** |
| Code being written under V10 banner? | **None** (post-v9 P1 chain continues instead) |
| Trigger fired? | **None of the 4 below** |
| Earliest realistic start | When ≥ 1 trigger fires + a real product/data question accompanies it |

## Triggers — what would actually start V10

Each trigger has a clear measurable. **V10 starts only when ≥ 1 is
both fired AND accompanied by a concrete next deliverable** (not
just "data accumulated" but "data accumulated AND the question it
unblocks has a specific ship target").

### Trigger 1 — Cup ablation re-test on fresh data — ❌ CLOSED NEGATIVE

Originally V8 W4 deferred ("9 months of Path A live odds accumulation").
**P1#20 closed this in 3 hours by buying The Odds API ($30 + 4 seasons
backfill).** 4-fold ablation result: 2/4 folds pass ship gate (needed
3/4). Cup-aware artifact does NOT ship.

Re-opens only if: a structurally different cup-feature design surfaces
(not the same UNION approach). No work pending.

### Trigger 2 — Lineup-aware ROI verdict — ⚠️ SHIPPED WITH CAVEAT

Originally V6 W7 backlog. **P1#17/P1#18 closed via historical replay:
lineup-aware wins +20.48pp ROI on football-data PSC.** Production
default flipped at P1#18.

**P1#21 added a caveat**: the same backtest on Odds API strict-Pinnacle
gives the OPPOSITE verdict (-37.13pp). Both verdicts internally
consistent; verdict is source-dependent. Live cron uses a 3rd source
(API-Football). Whether the production ship is "correct" requires
real live data — which is now Trigger 4 below.

### Trigger 3 — New product gap surfaces — ⏳ NOT FIRED

Examples that would qualify:
- User wants live in-play recommendations (current is pre-match)
- User wants a market we haven't built: correct-score, totals,
  Asian handicap selections beyond what 单关 covers
- User wants multi-user / SaaS support
- A second user shows up with different requirements

None of these are on the radar. Status checked at every post-v9 P1
patch — still nothing.

### Trigger 4 — Cross-source robustness from live data — ⏳ WAITING

New from P1#21. The lineup-aware ship is caveated until either:
- 4+ weeks of live daily-cron settlements confirm direction (the
  `weekly_gate` launchd job at P1#24 will surface this automatically
  every Sunday 04:00 with a 50pp noise-floor tolerance)
- A 3rd independent odds source (e.g. Betfair Exchange via another
  provider) backtest produces the SAME direction as football-data

Currently the daily cron has been running ~1 week (post-P1#16
local pipeline). Earliest data-driven verdict: 3+ weeks from now.

### Trigger 5 — Platform-level change — ⏳ NOT FIRED

Examples: Postgres migration, deployment to a hosted server, multi-tenant.
Out of scope unless a hosting / scale need forces it.

## What V10 looks like by trigger (sketches only)

### If Trigger 3 (product gap) — V10 = product version
- New 12-week cadence like V6 ("中国竞彩 product")
- Concrete user-visible deliverable each week
- Probably a new game type or a hosted deployment
- Builds on the 4-job launchd cron + observation DB foundations

### If Trigger 4 (cross-source verdict) → POSITIVE confirmation
- V10 = "validate-and-celebrate version"
- ~2-4 weeks
- Lock down the lineup-aware artifact as permanent default (P1#18 → permanent)
- Maybe retrain on Q1 2026 data + run cup-half of CI cache pay-down (V9 W4 backlog)
- Write a real V5-style "shipped" handoff

### If Trigger 4 → NEGATIVE (4-week live data disagrees with backtest)
- V10 = investigation version, NOT a sprint
- Mirror V9 W5/W6 structure: audit then attempt fix
- Likely outcome: 7th project negative-result writeup
- Revert P1#18? Maybe. Or document why live disagreed (stake-sizing? Kelly fraction? bookmaker price-shading?) without reverting

### If Trigger 5 (platform) — V10 = infrastructure version
- Postgres migration: 2-3 weeks of pure ops
- Hosted deploy: depends on user's hosting choice
- Multi-user: needs auth, rate limiting, billing — probably a V10 + V11 split

## Out-of-scope for V10 regardless of which trigger fires

These remain unchanged from V9_ROADMAP and earlier:

- Bayesian hierarchical (V7 backlog; no triggering need)
- Multi-snapshot odds streams (V5 W5 dormant; replaced by cross-source backtest in P1#21)
- Web UI rebuild beyond mobile/i18n/PWA polish (P1#13-15 already
  paid that down)
- New markets the user explicitly skipped (correct-score, totals)
- Anything that requires Node.js / Next.js — V5 W2 deleted that
  entire surface; decision still stands

## Post-v9 P1 chain — what to do while waiting

P1#6 → P1#24 is the canonical pattern for "between versions" work:
small docs-or-code patches, each independently shippable, none
requiring a multi-week sprint plan. See
[post_v9_p1_index.md](post_v9_p1_index.md) for the master list.

Reasonable P1 candidates that don't require triggers:

| Candidate | Type | Size | Why it's OK as P1, not V10 |
|---|---|---|---|
| ECE-vs-log-loss DEEPER dive (post V9 W6) | ML | 2-4h | V9 W6 closed the standard-fix path; only worth re-opening if a research result suggests a non-standard approach |
| GH Actions Playwright CI | QA | ~1h | Slack-week item; no scientific value |
| Bookmaker-price feature investigation | ML | 1-2d | Possible follow-up to P1#21 — but unclear what to do with the finding |
| Documentation: V10_HANDOFF_TEMPLATE | DOCS | ~30min | Pre-write the handoff structure for whoever-future-self that triggers V10 |

If 6 months pass with no trigger fired and the P1 chain has grown
to 30+ patches, consider writing a `v9_to_v10_long_quiet_summary.md`
just to acknowledge the project entered a *very* long maintenance
mode. Doesn't change behavior — just keeps the historical record clean.

## Anti-patterns to avoid

1. **Starting a V10 W1 just to feel productive.** V8 retrospective
   signed maintenance mode. V9 retrospective doubled down. P1 patches
   are the legitimate output of maintenance mode; "V10 W1" without
   a trigger is cargo-cult.

2. **Re-listing closed backlog items as V10 candidates.** Cup
   ablation (Trigger 1, closed negative), lineup ROI verdict (Trigger
   2, shipped with caveat), ECE mystery (V9 W6, closed negative).
   Don't write a V10 plan that re-investigates these without new evidence.

3. **Extrapolating from 1 week of live data.** P1#24's weekly gate
   will start producing reports next Sunday. The first 2-3 reports
   will have tiny samples and meaningless ROI swings. **Wait for week 4+.**

4. **Conflating "P1#21 added a caveat" with "P1#18 was wrong".** P1#18
   is the ship decision based on the primary source. P1#21 added a
   confidence interval around that decision. Either Trigger 4
   confirmation OR a 3rd-source backtest moves the verdict — not
   another reading of the same P1#21 data.

## Closing observation

V10 will either start small (Trigger 4 verdict close) or start
specifically (Trigger 3 product change). It is unlikely to ever
start as a "12-week V6-style sprint" because the V9 retrospective's
"earned the right to slow down" claim is genuine: every signal still
points to maintenance mode.

The most likely V10 is: **2-4 weeks, single concrete deliverable,
triggered by a clear data or product event, then back to
maintenance.** That's a healthy steady state for a project this
mature.

---

_When V10 actually starts, this draft gets renamed to
`docs/V10_ROADMAP.md` with the trigger identified at the top and
the concrete week-by-week plan filled in._
