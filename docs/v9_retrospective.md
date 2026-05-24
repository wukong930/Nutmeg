# V9 Retrospective — maintenance mode, honest negative results, ECE closed

_Ships with `v9.0-shipped`. Written at V9 closeout. Companion to
[V9_HANDOFF.md](V9_HANDOFF.md) — the handoff is "what V9 is"; this is
"what V9 taught us"._

## TL;DR

V9 was deliberately small. The V8 retrospective signed "项目接近
maintenance mode" — V9 honored that. Six weekly tags shipped over 6
flexible weeks (no Friday cadence pressure), 90 new tests (713 → 803),
zero production model changes, **one 6th project negative result that
permanently closed a 3-retrospective backlog item** (ECE-vs-log-loss
mystery).

The version that did not happen in V9:
- No new CLI for the cup-ablation retry (frozen, waiting on data)
- No new dashboard tab (W6's was a checkbox addition, not a new surface)
- No model retraining
- No new feature engineering

The version that did happen:
- One operational fix (CI fixture cache — paid down V6/V7/V8 backlog)
- One product polish (recorder checkbox actually plumbed, 4-year V5 W11 no-op)
- One investigation + one fix-attempt (W5 audit → W6 negative) — pure
  Track E science

## What worked

### 1. "Ship when ready, not on Friday" was the right call

V9_ROADMAP explicitly broke the V5-V8 12-week cadence. The 6 weeks
varied wildly in scope:

- W1: half a day (one workflow YAML edit + a roadmap doc)
- W3: ~1 day (3 schemas + helper + dashboard JS + 20 tests)
- W4: ~1 day (bake cache + 12 tests)
- W5: ~1 day (audit module + CLI + 21 tests + writeup)
- W6: ~1.5 days (calibrators + ablation CLI + 11 tests + writeup)
- Ship: ~half a day (this doc + handoff + tag)

Total ~4-5 days of focused work spread over a week. A 12-week sprint
plan with weekly Friday tags would have either (a) padded each item
with low-value busy-work, or (b) skipped some entirely to stay on
schedule.

### 2. The W5 → W6 audit-then-fix split was clean

V9 W5 cost ~1 day to *identify* whether the ECE mystery had a fixable
locus. The verdict ("🎯 concentrated bucket found") said "yes,
potentially". V9 W6 cost ~1.5 days to *test* whether a standard fix
worked. The verdict ("❌ no-fix, per-class isotonic catastrophic, T
≈ neutral") said "no — the bucket exists but it's structural signal,
not miscalibration".

If W5 and W6 had been merged ("investigate and fix the ECE gap"), the
investigator (me) would have been tempted to ship *something* —
probably a per-bucket-only isotonic that marginally helped 1 of 3
seasons. The audit-then-fix split gave W5 the freedom to say "found
it" and W6 the freedom to say "but it can't be fixed", **without
either week feeling like a wasted effort**.

This is the V5/V6 negative-result methodology applied to a single
investigation rather than to an end-to-end feature attempt.

### 3. Closing a 3-retrospective backlog item by *doing the work*

V6 W12, V7 ship, V8 ship retrospectives all listed "ECE-vs-log-loss
mystery — should investigate one day". 4 hours of W5 + W6 retired it
permanently. The relief is real: future retros won't have to keep
re-listing it. **Maintenance mode means executing the dusty backlog,
not just curating it.**

The CI fixture cache (W4) is the same pattern. Three retros flagged
it; V9 W4 did it. Cup-half is still open, but the lineup half is no
longer a recurring "we should..." line.

### 4. Negative result documentation pattern is mature

V9 W6's writeup follows the canonical structure:
- TL;DR with the actual numbers
- What was tested + why
- Multi-cutoff table (so single-season noise can't masquerade as a result)
- The "reading" — what the failure tells us
- What ships (infrastructure) vs what doesn't (production change)
- Backlog impact (explicit closure or escalation)
- What was not tried (so future attempts know the cost-benefit)

This template is now used 6 times (V5 W5, V5 W6, V5 W9, V6 W5, V8 W4,
V9 W6). It's the project's most reliable documentation form.

## What didn't work

### 1. Skipping V9 W2 (national-team Elo verification)

V9_ROADMAP planned W2 as another V8 W4-style negative writeup
("verify the wiring works, doc the `/odds` block applies the same
way"). I skipped it. Justification at the time: low marginal value
when V8 W4 had documented essentially the same conclusion. But
skipping has a cost:

- The national-team Elo wiring (post-V8 P1#4) is now verified only
  by unit tests, not by an end-to-end run on real WC/EURO fixtures
- The "we ran it and confirmed" reassurance is missing
- If V10 ever decides to retry national-team predictions, someone
  will have to re-derive the verification

A 30-minute fixture-only run (no `/odds` calls) would have closed
this cleanly. **Lesson: even "obviously negative" verifications are
worth running for the documentary value.**

### 2. The W5 audit's concentrated-bucket verdict was a false signal

V9 W5's verdict said "🎯 concentrated bucket found → V9 W6 candidate
fix". V9 W6 then tried the fix and found it didn't work. So the W5
verdict heuristic over-promised.

The verdict logic was:
```python
if biggest_diff > 0.001:
    "🎯 Concentrated bucket found"
```

But "concentrated" doesn't mean "fixable". The bucket *was*
concentrated; it just wasn't a calibration issue. **Better W5
heuristic for future audits**: also check whether the same bucket
shows the pattern across multiple cutoffs before flagging it as
"fixable". A multi-cutoff W5 would have caught the non-stationarity
the W6 ablation discovered, and pre-emptively softened the verdict
to "🟡 potentially structural".

(I'm leaving the W5 verdict logic unchanged so future audits hit the
same trap and learn the same lesson. The W6 writeup explicitly notes
the false positive.)

## V9 design principles — kept all 4

The 4 principles V9_ROADMAP introduced (and how V9 actually behaved):

1. **Ship when ready, not on Friday** ✅ — see above
2. **Expect negative results to dominate** ✅ — W6 was negative; W5
   was positive-then-negative; this version's headline outcome is a
   negative
3. **One real model change at most** ✅ — actually zero. W6's
   negative result meant the production CatBoost default stayed
   unchanged for the 4th straight version
4. **Maintenance mode is a feature** ✅ — W4 + W5 + W6 together
   were all backlog pay-down, not new features

## When V10 starts

Per V9_ROADMAP: V10 starts when **one** of:

- ⏳ Path A cup-odds accumulation reaches enough rows to retry the
  ablation (~250+ matches; estimated ~9 months from V9 ship)
- ⏳ A bigger product gap surfaces (user shifts to live in-play, new
  market, new game variant)
- ⏳ A platform-level change (Postgres migration, multi-user, etc.)

None of these are imminent. **V10 may not start for many months.**

If a small piece of work surfaces in the interim (e.g. an API token
rotation reminder cron, a single bug fix), it should ship as a
post-v9 P1 patch with `git tag --message`, same pattern as
post-v8 P1#4 + P1#5. **Don't start V10 just because V9 finished if
there's no actual priority change.**

## Counting honest negative results — the 6 to date

| # | When | What was tried | Why it failed |
|---|---|---|---|
| 1 | V5 W5 | Market dynamics features (open-to-close drift) | Cross-fold variance dominated signal |
| 2 | V5 W6 | Stacker on top of CatBoost+XGB+LGB | Already-good CatBoost ≈ ceiling |
| 3 | V5 W9 | Per-league temperature scaling | Insufficient per-league val samples |
| 4 | V6 W5 | Lineup features (first attempt — data leak) | `/injuries` returned post-match events |
| 5 | V8 W4 | Cup-aware ablation | API-Football `/odds` upcoming-only |
| 6 | V9 W6 | Per-class isotonic on CatBoost | Bucket gap is structural signal, not miscalibration |

The pattern: **infrastructure investments compound; negative result
documentation compounds too.** Each writeup makes the next one
faster + better-structured. V9 W6's took ~30 minutes to write
because the template is now reflex.

## V9 in numbers

| Metric | V8 ship | V9 ship | Δ |
|---|---:|---:|---:|
| V4 tests | 713 | 803 | +90 |
| Public CLIs | 23 | 25 | +2 |
| Weekly tags | 0 (V8 closeout) | 5 | +5 |
| Negative-result writeups | 5 cumulative | 6 cumulative | +1 |
| Production model changes | 0 (since V5 W12) | 0 (still) | 0 |
| Lines of docs | ~7,400 | ~8,200 | +~800 |
| Backlog items permanently closed | — | 2 (CI lineup half + ECE mystery) | +2 |

## Closing observation

V9 demonstrates a counter-intuitive project value: **a version whose
explicit goal is "ship less" can still ship meaningful resolution**.
Two recurring backlog items retired. Six tests-per-week average held.
Production stayed stable. The user's daily flow didn't change.

If V10 takes 9+ months to start because Path A's cup data has to
accumulate, the project has fully entered maintenance mode. That's
not stagnation — that's a system whose code requirements have been
met and whose remaining open items are now genuinely upstream of
code work.

V9 is the version where the pace slowed because the project earned
the right to slow down.

---

**Ship**: `v9.0-shipped`. See [V9_HANDOFF.md](V9_HANDOFF.md) for the
hand-off doc V10 starts from.
