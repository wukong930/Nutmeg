# Nutmeg V9 Roadmap

_Generated 2026-05-24 after V8 ship + V8 W4 negative result + post-v8
P1 patches. Replaces the previous "V9 should follow V6/V7/V8 cadence"
default — V9 is explicitly different._

## Context — why V9 looks unlike V5/V6/V7/V8

V5-V8 each ran 12 weeks (V7 = 6 coding + 2 data-gated, V8 = 5 coding +
3 data-gated). Every version shipped a thick weekly cadence:
features + tests + tag every Friday.

**V9 starts from a different place**:

| Signal | What it means for V9 |
|---|---|
| V8 W4 — cup-aware artifact NOT RUNNABLE (data block) | Track B is **frozen pending data**; no code work moves it |
| V8 W5 — lineup-aware ROI verdict still pending | Track A is **gated on 4 weeks of cron settlements** |
| Post-V8 P1#4 + P1#5 already shipped | The two highest-priority code patches from V8 retrospective are done |
| V4 default model unchanged for 3 versions (V6, V7, V8) | Production is stable; no urgent model issues |
| Daily user flow at 2 manual steps (V7 Track C closeout) | Operational UX is solved |

V9's actual situation: **a handful of medium-priority code items + a
lot of waiting for data**. A 12-week sprint plan would be cargo-cult.
V9 should be a **flexible 4-6 week mini-version** that ships when
ready, not on a Friday schedule.

## Tracks — continued from V8 + one new

| Track | Theme | V9 status |
|---|---|---|
| **A** | Lineup-aware ROI verdict | ⏳ Still data-gated. V9 W1's first task: read it if data exists |
| **B** | Cup-trained model | ❄️ **FROZEN** — V8 W4 documented the API-Football historical-odds block. **Path A (forward live accumulation)** started in V9 W1 via daily cron extension; revisit in ~9 months after 1 full UCL season |
| **D** | Product polish | 4 of 6 V8 backlog items remain — model integration, UI niceties |
| **E** (new) | Cleanup + paying down debt | CI gap fixes, ECE audit, retrospectives-still-unaddressed list |

## V9 plan

### V9 W1 (this week) — already started ✅

| Theme | Status |
|---|---|
| Path A — extend daily cron to include UCL+UEL leagues | ✅ shipped (daily-recommend.yml) |
| Path C — V9_ROADMAP.md (this file) | ✅ shipped |
| Read lineup-aware ROI verdict if local cron has run ≥ 4 weeks | ⏳ user-side check |

### V9 W2 — National-team Elo model integration (Track D)

V8 W7 + post-v8 P1#4 shipped the 68-nation registry + `seed_elo_value`
wiring. What's missing: **fixture data with actual national teams** in
the training set. Steps:

1. Run `nutmeg-ingest-cup-history --leagues WC,EURO,COPA_AMERICA,WC_QUAL_UEFA --seasons 2018,2022,2024` (~3 API calls)
2. Run `nutmeg-ingest-cup-odds` for the same — expected to return 0
   per V8 W4 (history-block). Confirm fixture data alone, no odds
3. Verify cup-history parquets contain country names (e.g. "Brazil"
   not "Brazil FC")
4. Verify `lookup_nation_elo` resolves the names against the 68-code
   registry via `nutmeg-canonical-report-cup` adapted for nations
5. Document: "national-team Elo wiring verified; cannot train because
   same `/odds` block applies — frozen pending Path A accumulation"

Most likely outcome: **a second V8 W4-style negative result writeup**
("infrastructure verified end-to-end, blocked on same data layer").
That's still V9 progress — moves the verification surface to a known-
working state.

Estimated 1-2 days.

### V9 W3 — Observation recorder dashboard checkbox (Track D) ✅

Shipped. 20 new tests (759/759 V4 suite). 4-year V5 W11-era no-op
finally plumbed through. Two-gate design (env + request flag) added.
串关 endpoint now records for the first time. 单关 + 复式 tabs gained
checkboxes. See [v9_w3_recorder_checkbox.md](v9_w3_recorder_checkbox.md).

### V9 W4 — CI fixture cache (Track E) ✅

Shipped. 1.4 MB cache committed (5 EPL 24/25 fixtures + 5 lineup
payloads + 10 team-season injuries). New `test_e2e_lineup_with_cache.py`
runs `build_lineup_lookup_from_cache` → `build_recent_injury_lookup`
→ `build_lineup_features` chain end-to-end on real data in CI. Closes
the lineup half of the 3-retrospective backlog item. Cup half stays
open until V9 W1 Path A accumulates ~250 cup_odds rows (~9 months).
12 new tests (771/771 V4 suite). See
[v9_w4_ci_fixture_cache.md](v9_w4_ci_fixture_cache.md).

### V9 W5 — ECE-vs-log-loss per-bucket Brier audit (Track E)

The mystery V5 W12 first noted: CatBoost's ECE (0.0120) is BETTER than
Pinnacle's (0.0123), but log-loss is 0.0056 worse. Three retrospectives
listed it; none acted. V9 W5 does it:

1. Split test predictions by predicted-probability buckets (5 bins)
2. Compute per-bucket Brier + log-loss; compare to Pinnacle bucketed
   the same way
3. Identify which buckets contribute the excess log-loss
4. Two possible outcomes:
   - Found a fixable bucket (e.g. high-confidence draws over-predicted)
     → cheap calibration tweak in V9 W6
   - Found nothing actionable (uniform spread across buckets) →
     document + remove from backlog forever

Estimated 1-2 days investigation + maybe 1 day fix.

### V9 W6 — Conditional: calibration fix if W5 found something

Skipped if W5 was inconclusive. Otherwise: minimal calibration tweak
+ multi-season re-validation + (if confirmed) ship.

### V9 ship — closeout

`V9_HANDOFF.md` + `v9_retrospective.md` + `v9.0-shipped` tag.

The V9 retrospective should be **shorter than V6/V7/V8 retros** because
V9 itself is shorter. Maybe ~150 lines instead of ~250.

## Tag plan

| Tag | When | Status |
|---|---|---|
| `v9.w1` | Path A + V9_ROADMAP | shipped this commit |
| `v9.w2` | National-team Elo verification (probably negative writeup) | |
| `v9.w3` | Dashboard recorder checkbox | |
| `v9.w4` | CI fixture cache | |
| `v9.w5` | ECE audit | |
| `v9.w6` | (conditional) calibration fix | |
| `v9.0-shipped` | V9 closeout | |

## Numeric targets

| Metric | V8 ship | V9 target |
|---|---:|---:|
| V4 tests passing | 739 (with post-v8 patches) | 770+ |
| CLIs in pyproject | 23 | unchanged (no new CLIs likely) |
| Cup_odds parquets non-empty | 0 (V8 W4 block) | Wait — 0 at V9 ship, growing thereafter |
| Lineup ROI verdict | pending | **closed** (one way or the other) |
| ECE audit | open | **answered** (fix or freeze) |
| CI lineup-path coverage | 0% | end-to-end smoke pass |
| Production CatBoost default | unchanged through V5-V8 | likely still unchanged (V9 = maintenance) |

## Out of scope for V9

- New cup ablation attempts (frozen until Path A accumulates ~1 season)
- Postgres migration
- Multi-user / SaaS
- New markets (correct score, totals — user explicitly skipped in V6)
- Multi-snapshot odds streams (V5 W5 dormant)
- Bayesian hierarchical (V7 backlog, still not unblocked)
- Web UI rebuild beyond dashboard checkbox plumbing

## V9 design principles (new this version)

The pattern V9 explicitly adopts:

1. **Ship when ready, not on Friday**. V5-V8 had weekly cadence. V9
   has 4-6 weeks of mixed-effort items; shipping each when done is
   fine. No artificial weekly tag pressure.

2. **Expect negative results to dominate**. V9 W2 will probably be a
   negative writeup (national-team Elo wiring works but `/odds` block
   applies). V9 W5 may also be (ECE audit finds nothing fixable).
   Negative writeups are not failures — they're documentation.

3. **One real model change at most**. V9 W6 is conditional on V9 W5
   finding something. If not, V9 ships with the same V5 W12 CatBoost
   default it inherited from V8.

4. **Maintenance mode is a feature**. V8 retrospective signed: "项目
   接近 maintenance mode". V9 honors that. Code quality + technical
   debt over new features.

5. **Data-gated ⏳ stays ⏳**. Don't pretend V8 W4/W5 will close in
   V9 if they're still data-gated. V9 ship can leave open ⏳ items
   for V10; V8 ship did the same.

## When to call V10

V10 starts when one of:
- Path A cup-odds accumulation reaches enough rows to retry the
  ablation (~250+ matches, est. 9 months from now)
- A bigger product gap surfaces (user shifts to live in-play / new
  market / new game variant)
- A platform-level change (Postgres migration, multi-user, etc.)

Before that, V9 W6+ continues to be maintenance / small polish.
**Don't start V10 just because V9 finished if there's no actual
priority change.**
