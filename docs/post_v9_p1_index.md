# post-v9 P1 patch chain — index (#6 → #21)

_Generated 2026-05-24. 16 patches landed (some bundled into a single
commit). This is the master index — read here, drill into the per-
patch docs only when needed._

## Why a "P1 patch chain" exists

V9 shipped on 2026-05-?? after closing W1-W6. The shipped retrospective
flagged the project as **"infrastructure-complete, decision-pending"**:
all V10 ML/feature triggers required real-world data to be collected
slowly through the existing daily cron, with no remaining roadmap
work that wouldn't have been premature.

Rather than start V10 cold or sit idle, we used the time to
systematically clear a backlog of small-but-real items: deprecation
hygiene, UX polish, front-end mobile coverage, deployment friction,
and — most importantly — finding **data-purchase shortcuts** for the
two V10 data-gated triggers (lineup ROI verdict, cup ablation
verdict). Both got answered.

## TL;DR — the chain at a glance

```
P1#6   deprecation cleanup       (36 warnings → 0)              ENG
P1#7   dashboard localStorage    (record-session persistence)    UX
P1#8   sessions/latest endpoint  (real-write feedback)           UX
P1#9   ece-audit --cutoffs       (multi-season ECE)              ML
P1#10  national-team Elo verify  (clubelo /<code>)               DATA
P1#11  API token rotation cron   (90-day reminder)               OPS
P1#12  national-team Elo wired   (build_elo_features → model)    ML
P1#13  front-end tier-1          (mobile + a11y + error UX)      UX
P1#14  i18n + PWA                (中/英 toggle + manifest+SW)    UX
P1#15  Playwright + axe-core     (E2E + WCAG AA)                 QA
P1#16  local deployment pipe     (launchd jobs + scripts)        OPS
P1#17  nutmeg-roi-backtest       (4-6w wait → 30 min)            ML
P1#18  SHIP lineup-aware default (V10 trigger #2 POSITIVE)       SHIP
P1#19  live-vs-backtest gate     (CLI + exit codes)              ML
P1#20  cup ablation NEGATIVE     (V10 trigger #1 closed, $30)    SHIP
P1#21  cross-source backtest     (verdict source-dependent)      ML
P1#22  P1#19 cross-source caveat (docs-only; gate triage rules)  DOCS
P1#23  --tolerance-pp flag       (CLI+HTTP; implements P1#22 #1) ML
P1#24  weekly launchd gate job   (Sun 04:00; --tolerance-pp 50)  OPS
P1#25  V10_ROADMAP_DRAFT.md      (placeholder; triggers + sketch) DOCS
P1#26  GH Actions Playwright CI  (P1#15 work now runs in CI)     QA
P1#27  V10_HANDOFF_TEMPLATE.md   (companion to P1#25 placeholder) DOCS
P1#28  silence stale GH cron     (drop schedule on 2 workflows)  OPS
P1#29  weekly_bench autostash    (race condition fix; cards now ship) OPS
```

**Net change**: V10 has both data-gated triggers resolved (one ship,
one negative-close), the daily local pipeline runs on launchd
(replacing failed GH Actions cron), front-end is mobile + i18n +
WCAG AA, and infrastructure is in place for any future cross-source
backtesting (`--strict-bookmaker` flag, `--odds-source` flag, 5
domestic-league sport_keys on The Odds API).

---

## Patch-by-patch summary

### Foundations & hygiene (P1#6-9)

#### P1#6 — Deprecation cleanup (commit `5d8b7f4`)
36 warnings (mostly `datetime.utcnow()` and `pkg_resources`) → 0
across the codebase. No behavior change; future Python 3.13 should
not break.

#### P1#7+8+9 — V9 closeout bundle (commit `2f4a2e5`)
- **#7**: dashboard "record-session" checkbox now persisted to
  localStorage. Prior behavior reset every page refresh.
- **#8**: `/api/v4/observation/sessions/latest` returns the most-
  recent session metadata. Dashboard "✓ session #N recorded"
  feedback now reflects reality, not a fake.
- **#9**: `nutmeg-ece-audit --cutoffs YYYY-MM-DD,YYYY-MM-DD,...`
  to run ECE on N cutoffs in one shot — used by P1#21 backtest
  validation.

### V10 backlog clearance (P1#10-12)

#### P1#10 — National-team Elo verification (in commit `206fcae`)
Confirmed clubelo's `/<NationCode>` endpoint returns reasonable
country Elo for 68 registered nations. `docs/post_v9_p1_10_*.md`
documents name-resolution gaps + fix paths.

#### P1#11 — API token rotation cron (in commit `206fcae`)
Added a 90-day reminder script + scheduled task spec. Triggered
by V6 W8 doc that flagged "user advised to rotate, no confirmation".

#### P1#12 — National-team Elo wired (in commit `206fcae`)
`build_elo_features` now uses nation-state Elo for WC/Euro/Copa
America rows instead of falling back to default 1500.
`docs/post_v9_p1_12_*.md` documents the ~20-line integration.

### Front-end tier-2 work (P1#13-15)

#### P1#13 — Mobile + a11y tier-1 (commit `8d5e5bd`)
Discovered the dashboard had ZERO mobile coverage. Added:
- `viewport` meta + responsive tab nav (horizontal scroll)
- card-list fallback for recommendation tables (md:hidden vs md:table)
- ARIA roles + inputmode + live regions
- error banner + loading spinner
See `docs/post_v9_p1_13_frontend_audit.md` for the full audit.

#### P1#14 — i18n + PWA (commit `9264c22`)
- 中/英 toggle via `data-i18n` attributes + JS dictionary
  (~60 keys), choice persisted to localStorage
- PWA shell: manifest.json + service worker (offline cache)
- Add-to-home-screen tested on iOS + Android

#### P1#15 — Playwright + axe-core (commit `390403a`)
- Playwright E2E covering: 7 dashboard tabs, single/pool/recommend
  happy paths, locale toggle, record-session toggle
- axe-core WCAG AA audit: 0 violations across all 7 tabs
- Added to dev deps in `pyproject.toml`. CI integration is backlog.

### Deployment pipeline (P1#16)

#### P1#16 — Local launchd pipeline (commits `448b39f` + `e8277a5`)
Replaced 6-month-failed GH Actions daily-recommend cron (missing
`NUTMEG_API_FOOTBALL_KEY` secret was never configured) with:
- `scripts/setup_local_pipeline.sh` — installs 3 launchd jobs:
  daily_odds (14:00), daily_recommend (15:00), weekly_settle
  (Sun 02:00)
- `scripts/teardown_local_pipeline.sh` — clean uninstall
- `scripts/health_check.sh` — single command shows job status,
  last log, last successful run
- `scripts/run_local_server.sh` — convenience web-server launcher
- `docs/local_deployment_guide.md` — user-facing install guide

Hotfix `e8277a5`: `health_check.sh` had SIGPIPE false negatives
caused by `set -o pipefail` + `grep -q` + repeated `launchctl list`.
Fixed by snapshotting `launchctl list` once into a variable and
using `grep -F` (fixed-string) once per job.

### Backtest acceleration & lineup ship (P1#17-19)

#### P1#17 — `nutmeg-roi-backtest` CLI (commit `de41f15`)
Replaces the 4-6 week wait for real daily-cron lineup data. Takes
football-data.co.uk historical CSVs, walks each fixture through
BOTH the default and lineup-aware artifacts, records sessions to
a separate observation DB, then settles known outcomes. Result:
ROI verdict in ~30 minutes instead of 4-6 weeks.

#### P1#18 — SHIP lineup-aware as default (commit `8597ef1`)
With P1#17's backtest tool, validated lineup-aware ROI across 3
sub-windows (Q1/Q2/Q3 of 2024-25) on football-data PSC. All 3
positive. Final ship verdict: +20.48pp ROI over default. Flipped
all 3 production CLI defaults (`recommend`, `recommend_pool`,
`rec`) to point at `data/v4_model_cat_lineups`. **Closes V10
trigger #2 (positive ship).**

#### P1#19 — `nutmeg-live-vs-backtest` gate (commit `7e0a9b3`)
CLI to compare live-cron ROI against the P1#17 backtest ROI.
Exit codes 0/1/2 based on tolerance (default ±5pp). Wired so a
future cron can alarm when production drifts from the validation
baseline.

### Data-purchase shortcuts (P1#20)

#### P1#20 — Cup ablation NEGATIVE via Odds API (commit `09283e7`)
Bought The Odds API Starter tier ($30/mo). Backfilled 4 seasons
of UCL+UEL closing odds. Ran `nutmeg-cup-ablation` across 4
cutoffs. Result: **2 of 4 folds pass ship gate**, NOT the required
3 of 4. Cup-aware artifact does NOT ship.

Also fixed a latent bug in `cup_ablation.py` (wrong dict keys
since V8 W3 — would have returned NaN even with data).

**Closes V10 trigger #1 (negative close)**.

The 9-month wait was dissolved by $30 + 3 hours of work.
See `docs/post_v9_p1_20_cup_ablation_negative.md`.

### Cross-source validation + caveat (P1#21-22)

#### P1#21 — Cross-source backtest, verdict source-dependent
Re-ran P1#18 lineup ROI verdict on a second source (The Odds API
strict-Pinnacle snapshots). **Verdict flipped**: lineup-aware wins
+15.97pp on football-data PSC but loses -37.13pp on Odds API.

Root cause: a systematic ~3-5% price-level gap between sources
(same fixtures, same nominal bookmaker), driven by snapshot-time
differences (football-data captures at kickoff, Odds API at 23:00
UTC daily).

**Does NOT reverse P1#18 ship** — football-data was the primary
validation source, lineup-aware was trained on football-data-style
features, and live production uses a third source (API-Football's
`/odds`) whose verdict is still unknown. But adds caveat to
shipped state and a NEW V10 trigger (cross-source robustness).

Infrastructure added: `--odds-source {football_data, odds_api}`
flag + `--strict-bookmaker` flag in `nutmeg-roi-backtest`; 5
domestic-league sport_keys added to `odds_api.SPORT_KEYS`. All
reusable for future cross-source studies.

See `docs/post_v9_p1_21_cross_source_backtest.md`.

#### P1#22 — P1#19 cross-source caveat (docs-only)
Tacked an amendment onto `docs/post_v9_p1_19_live_roi_backtest_gate.md`
explaining that the 5pp default tolerance is only meaningful when
the live cron and the reference backtest use the same odds source.
In current production they don't (live=API-Football, reference=
football-data PSC), so the gate will probably trip false-positive
on cross-source noise.

Added a 3-step triage procedure for a real `exit=2` alarm
(re-run with wider tolerance; sub-check via same-source replay;
inspect hit-rate gap separately from ROI gap). No code changes.

Sets expectations BEFORE the first live alarm fires (the daily
cron is currently building toward week-4 verdict).

#### P1#23 — `--tolerance-pp` flag (implements P1#22 triage step 1)
Threaded `tolerance_pp` through `compute_gap()`, `format_report()`,
and `run()` in `nutmeg.v4.observation.live_vs_backtest`. Added:

- CLI: `nutmeg-live-vs-backtest --tolerance-pp N` (default 5.0)
- HTTP: `GET /api/v4/observation/live-vs-backtest?tolerance_pp=N`

Implements the cross-source noise-floor check from P1#22 without
needing to edit module constants or re-deploy. Negative values
rejected. Default unchanged → backwards-compatible.

8 new tests (4 module-level for `compute_gap`/`run`/`format_report`,
3 HTTP endpoint, 1 covering invalid input). Real cross-source data
verified: `--tolerance-pp 60` suppresses the ~52pp ROI gap from
the P1#21 strict-Pinnacle backtest; default `--tolerance-pp 5`
still trips with exit=2.

#### P1#24 — weekly launchd gate job (`com.nutmeg.weekly_gate`)
Added a 4th launchd job that auto-runs the P1#19 gate every
Sunday 04:00 (2h after `com.nutmeg.weekly_settle` lands the
freshly-settled data). Uses `--tolerance-pp 50` as the cross-
source noise floor per the P1#22 amendment.

Each week's report writes to
`docs/weekly/p1_19_gate_<YYYY-Www>.md`. Exit code is swallowed
via `|| true` (so launchd always sees "success") — operator
reads the gate verdict by checking the markdown file Monday
morning, not by parsing return codes.

Changes in `scripts/setup_local_pipeline.sh`, `teardown_local_pipeline.sh`,
`health_check.sh`, `docs/local_deployment_guide.md`, and test
`tests/v4/test_local_pipeline_scripts.py::test_installs_named_jobs`.

After this patch the local pipeline has 4 launchd jobs:
daily_odds (14:00), daily_recommend (15:00), weekly_settle
(Sun 02:00), weekly_gate (Sun 04:00). Re-run
`./scripts/setup_local_pipeline.sh` to install the new job.

#### P1#25 — `V10_ROADMAP_DRAFT.md` (placeholder, V10 not started)
Wrote `docs/V10_ROADMAP_DRAFT.md` as an explicit "V10 hasn't started"
placeholder. Lists 5 trigger conditions, current status of each,
and what V10 looks like *if* each trigger fires. Also enumerates 4
anti-patterns (don't start V10 to "feel productive", don't re-list
closed backlog items, don't extrapolate from 1 week of live data,
don't conflate P1#21 caveat with P1#18 being wrong).

Important because the post-v9 P1 chain has grown to 20 patches and
"what's next" was at risk of drifting into an implicit V10 sprint
without a real trigger. The draft is the structural backstop: any
future restart of weekly-cadence work has to cite which trigger
fired and what concrete deliverable accompanies it.

When V10 actually starts, this draft gets renamed (drop the
`_DRAFT` suffix) and filled in with the week-by-week plan.

#### P1#26 — GH Actions Playwright CI
Added `.github/workflows/playwright.yml`. P1#15 shipped Playwright +
axe-core tests in `tests/v4/test_e2e_playwright.py` but the existing
nutmeg-ci.yml workflow only installs the `playwright` python package
(via `uv sync --all-extras`), not the Chromium browser binary. Result:
every test in that file silently `pytest.skip`s in CI.

This workflow installs Chromium (cached via `~/.cache/ms-playwright`
keyed on `pyproject.toml` hash) and actually runs the 9 E2E tests
plus the 54 structural front-end tests (responsive a11y + i18n/PWA).

Triggers: PR/push when dashboard / static / front-end test files
change. Path filter saves ~3 min when only ML code changes. Always
runnable on demand via `workflow_dispatch`.

Upload trace artifact on failure for debugging.

Verified locally: 9/9 Playwright tests pass in 9.39s.
Verified YAML: parses cleanly, 3 triggers, single `playwright` job.

#### P1#27 — `V10_HANDOFF_TEMPLATE.md` (companion to P1#25)
Pre-wrote a fill-in skeleton at `docs/V10_HANDOFF_TEMPLATE.md` so
the handoff structure exists before V10 starts. Mirrors the V5-V9
10-section pattern with 🔲 TODO and ⬜ PLACEHOLDER markers throughout.

Includes a "How to use this template" header that codifies:
- Don't fill in just because N weeks passed (wait for a trigger)
- When trigger fires: rename `_TEMPLATE` → `_HANDOFF`, rename
  `V10_ROADMAP_DRAFT` → `V10_ROADMAP`, then start filling
- §5 (numbers) is the truth check: thin Δ means V10 was actually a
  P1 chain misnamed — rename rather than ship a thin V10
- Don't add sections; the V5-V9 pattern is mature

Paired with P1#25 this gives the project a complete "V10 starter
kit" the moment any of the 5 triggers fires.

#### P1#28 — Silence stale GH cron (validate P1#11 + clean up P1#16 fallout)
Manually triggered `monthly-token-check.yml` for the first time (P1#11
wrote it but never confirmed it actually worked). It correctly failed
on missing `NUTMEG_API_FOOTBALL_KEY` secret.

But this "fail" was a false alarm. P1#16 moved daily cron to local
launchd; the GH secret was never set, so `daily-recommend.yml` AND
`monthly-token-check.yml` had been failing every day/month for ~6
months on the Actions tab. Nobody noticed (first-failure-only emails).

Fixed both workflows:
- Drop `schedule:` triggers; keep `workflow_dispatch:` only
- Missing secret → exit 0 with `::notice` (not exit 1 with `::error`)
- daily-recommend: gate 7 subsequent steps on `has_secret == 'true'`
- monthly-token-check: gate probe step on same

Verified via fresh trigger (GH run `26367845624`): exits `success`
with clear notice. Zero false-positive failures going forward.

`nutmeg-ci.yml` + `weekly-bench.yml` + new `playwright.yml`
unaffected — none need the API-Football secret.

#### P1#29 — Weekly bench cards now actually ship (race condition fix)
Same-pattern audit as P1#28: `weekly_bench.yml` (Sun 02:00 UTC,
shipped V5 W10) had `docs/weekly/` empty for the project's entire
lifetime. Root cause: bench takes ~3 min; any commit landing on
main during that window makes the final `git push origin main`
rejected as non-fast-forward.

Fix (iterated twice):
1. First attempt (`07ef5a4`): 3-retry loop with `git pull --rebase`
   + `git push`. Final failure exits 0 with notice (not exit 1)
2. Manual verification revealed bench step writes side-effect files
   (experiment tracker journal) that block clean rebase with
   "unstaged changes" error
3. Second attempt (`a0c074c`): add `--autostash` to the pull.
   Stashes uncommitted changes, rebases, then pops the stash

End-to-end verified: GH run `26368370410` succeeded on attempt 1
with autostash. Cards `docs/weekly/2026-W21-bench.md` +
`2026-W21-multi.md` now committed to main (first bench cards ever
to actually ship from this cron).

Future Sunday 02:00 UTC runs will continue producing weekly cards;
docs/weekly/ will accumulate one cohort per week going forward.

---

## Cumulative effect on the project

### Closed V10 backlog items

| Trigger | Pre-P1 status | Post-P1 status | Resolved by |
|---|---|---|---|
| Cup ablation | "wait 9 months for forward odds accumulation" | NEGATIVE close | P1#20 ($30 + 3 hours) |
| Lineup ROI verdict | "wait 4 weeks for cron data" | POSITIVE ship w/ caveat | P1#18 (30 min backtest) |
| Cross-source robustness | not on radar | NEW trigger added | P1#21 |
| API token rotation | "advise user, no confirmation" | 90-day cron reminder | P1#11 |
| National-team Elo integration | "needs WC/Euro fixtures first" | wired with fallback | P1#12 |
| Mobile/a11y/i18n/PWA | "TODO someday" | shipped at WCAG AA | P1#13-15 |
| Local deployment friction | "GH Actions cron failing 6mo" | 3 launchd jobs | P1#16 |

### New backlog items added

| Item | Why | When to revisit |
|---|---|---|
| 4 weeks of live daily-cron data | Cross-source caveat unresolvable from backtest | Continuous |
| 3rd independent odds source comparison | Confirm direction of cross-source flip | If user wants more evidence |
| GH Actions CI integration of Playwright | P1#15 only ran locally | Slack week |

### Maintenance state of subscriptions

| Service | Cost | Used for | Status |
|---|---:|---|---|
| API-Football Pro | $19/mo | Live odds + lineups + fixtures (daily cron) | KEEP — production |
| The Odds API Starter | $30/mo | Backfill + cross-source backtests | KEEP through Jun 2026, then evaluate |

---

## How to read this index

- If a patch has a dedicated doc, it's linked. Start there for
  surgical detail.
- If a patch was bundled (P1#7-9, P1#10-12), the bundle doc has
  per-component sections.
- Commits are pinned by SHA — git history is the canonical source
  if discrepancies arise.
- Tags are at version boundaries only (`v9.0-shipped` was the
  last). The P1 chain doesn't tag — it's a continuous-improvement
  stream against `main`.

## Lesson summary across the P1 chain

1. **"Wait for data" can often be replaced with "buy the data"**
   (P1#17 internal-source acceleration; P1#20 external-source
   purchase). A 30-min check on what's purchasable should precede
   any multi-week wait.
2. **Multi-window backtest validation is necessary but not
   sufficient** (P1#21). Cross-source confirmation matters when
   the edge claim is marginal.
3. **Slack weeks turn into "infra-bankrolled" weeks** when there's
   a backlog of P1 items — front-end audit, deployment pipeline,
   cross-source validation infrastructure. None individually was
   "the next big thing", but together they form a meaningful
   maturity step.
4. **The right end-state of a maintenance-mode project is "fewer
   open questions"**, not "more shipped features". P1 closed two
   data-gated questions (cup, lineup ROI) at the cost of one new
   one (cross-source robustness) — net -1 question.
