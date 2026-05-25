# V10 Closeout Audit

_Performed: 2026-05-25, after V10 W4 ship, before starting V11._

Systematic scan of all V10 work to find unfinished items, stale doc
claims, missing operational coverage, and forward-references that
shouldn't ship into V11. Surfaces gaps that crept in across the
4-week dual-track sprint.

---

## Audit checklist

| # | Check | Verdict |
|---|---|:-:|
| 1 | All V10 commits pushed to origin | ✅ |
| 2 | All V10 tags present (v10.w0/w1/w2/w3/w4) | ✅ |
| 3 | No TODO/FIXME/XXX in V10 new code | ✅ |
| 4 | `local_deployment_guide.md` reflects all 7 launchd jobs | ❌ → fixed |
| 5 | `V10_HANDOFF.md` test counts match `pytest tests/v4/` reality | ❌ → fixed |
| 6 | `v10_w4_ship_note.md` test/CLI counts accurate | ❌ → fixed |
| 7 | `pyproject.toml` CLI count claims match `grep -c "^nutmeg-"` (31) | ❌ → reconciled |
| 8 | `scripts/setup_local_pipeline.sh` installs all 7 jobs | ✅ |
| 9 | `scripts/teardown_local_pipeline.sh` removes all 7 | ✅ |
| 10 | `scripts/health_check.sh` checks all 7 | ✅ |
| 11 | `scripts/wc_preflight.sh` runs cleanly (5 green + 2 yellow expected) | ✅ |
| 12 | All V10 forward-references ("will ship in W4", etc.) actually shipped | ✅ |
| 13 | Dashboard WC tab JS calls `/api/v4/predictions/wc` | ✅ |
| 14 | All 4 known-failing Playwright tests now pass (W3 Day 1 fix) | ✅ |
| 15 | WCAG AA `aria-required-children` violation resolved | ✅ |
| 16 | Layer A artifact-side correction file path consistent across docs | ✅ |
| 17 | WC fixture cache (`_fixtures/`) has 2026 data accessible | ✅ |
| 18 | National-team Elo snapshot < 30 days old | ✅ (0d old) |
| 19 | `wc_predictions` table schema documented | ✅ (in `wc_log.py` docstring) |
| 20 | V10 retrospective skeleton exists for post-WC fill-in | ✅ |

---

## Issues found + fixed

### Issue #4 — `local_deployment_guide.md` documented only 4 of 7 launchd jobs

The guide was written at P1#16 (post-V9) and never updated for V10's
3 new jobs: `weekly_calibration_check` (V10 W2), `daily_wc_predict`
(V10 W4), `daily_wc_settle` (V10 W4).

**Fix applied:**
- Header table extended to 7 jobs with per-job description
- New "Daily schedule" timeline section showing the order
  (02:00 wc_settle → 03:00 calibration → 04:00 gate → 09:00 wc_predict
  → 14:00 odds → 15:00 recommend)
- New "Pre-WC kickoff verification" section pointing at `wc_preflight.sh`
- New "Operating Layer A" section with: how to read Monday's report,
  how to deploy a SHIP recommendation, how to manually rollback
- New "Operating WC 2026" section: daily report file paths +
  force-run commands
- Uninstall section updated (4 → 7 jobs)
- Files map updated with all new logs / plists / output paths

### Issues #5/#6/#7 — test/CLI count claims off

Two ship notes claimed `1108/1108` non-Playwright tests passing
post-W4 + `33` CLIs in pyproject. Actual:

| Claim | Actual | Where |
|---|---:|---|
| 1108 non-Playwright tests | **1095** | V10_HANDOFF L112 + v10_w4_ship_note L144 |
| 1112 total (incl Playwright) | **1104** | v10_w4_ship_note L145 |
| 33 CLIs | **31** | v10_w4_ship_note (referenced in initial draft) |

**Fix applied:** all three doc claims corrected to match the
authoritative pytest output + `grep -c "^nutmeg-" pyproject.toml`.
V10_HANDOFF numbers table extended with a W4 column.

The "off-by-13 / off-by-2" errors are both inflation errors
(claimed more than reality). Likely cause: I extrapolated from
"baseline +30" without re-running pytest after the closeout sweep.
Closeout audit caught it.

---

## Items NOT fixed (intentional)

### Layer A "Lineup ROI verdict — data-gated"
- The retrospective skeleton flags this as pending until WC window
  generates ≥4 weeks of settled rows. Cannot resolve pre-tournament.

### V10 retrospective's `{XX}` placeholders
- 8 placeholders for post-WC numbers in `docs/v10_retrospective.md`.
- Fill in 2026-06-21 or post-tournament.

### Daily ship-note breakdowns for W2/W3/W4
- W1 has per-day docs (`v10_w1_day1_*` through `v10_w1_day5_*`); W2/W3/W4
  don't.
- Deliberate — the W1 daily docs were heavy because Track A vs Track B
  parallel work needed deconfliction. W2-W4 ship notes (1 per week)
  are sufficient.

### `V10_ROADMAP.md` end-of-week status markers
- The roadmap is a planning doc; it was written at W0 and the ship
  notes carry the "what actually happened" record.
- Could add ✅ markers per section but it's redundant with
  `V10_HANDOFF.md`'s week-by-week status. Skipping.

### README.md mention of V10 work
- The README hasn't been updated since V9 for CLI counts / cron jobs.
- Not a closeout blocker — V10_HANDOFF is the entry point for new
  readers; README is a quick orientation.
- Deferred to V11 W0 (alongside other "general housekeeping").

---

## Pre-V11 checklist — all green

Before opening V11:

- [x] All V10 weeks tagged + pushed
- [x] All V10 ship notes consistent with reality
- [x] Local deployment guide knows about all 7 launchd jobs
- [x] WC preflight script validates pre-kickoff readiness
- [x] V10 retrospective skeleton committed for post-WC fill-in
- [x] No unresolved P0/P1 issues from V10 development

V11 is unblocked.

---

## Commit chain (this audit)

This file + the 3 fixed docs land in a single commit:
`chore(v10): closeout audit — fix stale doc claims + extend deployment guide`.

No code changes; all V10 engineering is intact at the W4 tag.
