# V10 W3 Ship Note — Integrate + WC Dry-Run + Full Green

_Shipped: 2026-05-25 (tag `v10.w3`, 16 days ahead of 2026-06-10 target)_

---

## TL;DR

V10 W3 is the **integration / polish** week. With Layer A (W2) and
the WC model (W1) already shipped, W3 closes out:

1. **Fixed 4 Playwright failures** carried over from V10 W1 (tab
   count drift + WCAG `aria-required-children`)
2. **WC 2026 dry-run** against the real 72-fixture cache — produced
   a 15-match opening-week reference report
3. **Full V4 test suite is GREEN** for the first time since V10 W1:
   **1074/1074 passing** (was 1057 + 4 known-failing Playwright)

Three commits, ~120 lines of code, ~280 lines of docs, no new
modules. Pure "make it ready for kickoff" work.

---

## What shipped

### Day 1: Dashboard WCAG fix + Playwright tests

**Problem:** V10 W1 added the WC + 今日推荐 tabs and put `#adv-toggle`
inside `<nav role="tablist">`. axe-core reported a critical violation
because tablists may only contain `role="tab"` children. Plus 4
Playwright tests still expected the pre-W1 7-tab layout.

**Fix** (`apps/api/src/nutmeg/v4/api/static/dashboard.html`):
- Wrapped the nav in a `<div class="flex items-end">` and moved
  `#adv-toggle` OUT of the tablist
- Removed the `<span id="adv-tabs" class="contents">` wrapper that
  was confusing axe's accessibility tree
- The 7 legacy tabs are now direct children of `nav[role="tablist"]`
  with `.adv-tab hidden` classes — JS toggles `hidden` per button
- Renamed `test_all_7_tabs_render` → `test_all_9_tabs_render` (count
  to 9)
- Updated `test_clicking_pool_tab_shows_pool_panel` to click
  `#adv-toggle` first (reveal pool tab) + assert against `#tab-today`
  as the default (V10 W1 default landing)

Both WCAG audits (en + zh) now pass cleanly.

### Day 2: WC 2026 dry-run

**Command run:**
```bash
for d in 2026-06-11 2026-06-12 2026-06-13 2026-06-14 2026-06-15; do
  nutmeg-wc-predict --date "$d" --quiet --out /tmp/wc_dryrun/"$d".json
done
```

**Result:** 15 predictions produced across 5 days, all with
rational probabilities. See [v10_w3_wc_dry_run.md](v10_w3_wc_dry_run.md)
for the full markdown table.

**Highlights:**
- Mexico vs South Africa (opener): 58% home — host + 336 Elo lead
- Spain vs Cape Verde: 53% home only — LightGBM regularizes against
  Elo-only's 95% blowout prediction
- USA vs Paraguay: 60% away — Paraguay's Elo edge outweighs +30 host
  advantage
- All 244 nations have valid Elo (P1#10 eloratings.net switch paid off)
- `source: lightgbm_only` for all 15 — Pinnacle odds haven't opened
  yet (17 days out); blend will activate automatically when they do
- Smoke-tested `/api/v4/predictions/wc?date=2026-06-11` → returns
  identical probabilities to CLI

### Day 3: Tag v10.w3

Updated `docs/V10_HANDOFF.md` (W3 row, numbers table) and wrote this
ship note. Tagged + pushed.

---

## Test status

**Before V10 W3:** 1057/1057 non-Playwright pass + 4 Playwright fail
**After V10 W3:** **1074/1074 INCLUDING Playwright** — first full
green V4 suite since V10 W1 ship

| Test file | Count | Notes |
|---|---:|---|
| All V4 non-Playwright | 1057 | unchanged |
| `test_e2e_playwright.py` | 17 (was 13 + 4 failing) | now all passing |
| `test_auto_calibration_serving.py` | 24 | W2 Day 3 |
| `test_auto_calibration_rollback.py` | 11 | W2 Day 4 |
| `test_auto_calibration_e2e.py` | 8 | W2 Day 5 |
| | | |
| **Total** | **1074 / 1074** | All green |

---

## What's NOT in V10 W3

- **No new code modules.** Pure integration / polish.
- **No new CLIs.** Still 31 in `pyproject.toml`.
- **No model retraining.** Production model unchanged since V5 W12
  (per V10 design).
- **No Pinnacle WC odds yet.** Will appear when The Odds API starts
  quoting the tournament (~5-7 days before kickoff). The
  `--fetch-current-odds` flag is ready to consume them; nothing to
  change here.

---

## Commit + tag map

| Day | Commit | Title | LoC |
|----:|:-------|:------|----:|
| 1 | (in this commit) | dashboard WCAG fix + Playwright test updates | ~50 |
| 2 | (in this commit) | WC 2026 dry-run docs (15 predictions, sanity checks) | ~180 |
| 3 | (this) | ship note + V10_HANDOFF update + tag v10.w3 | ~150 |

**Tag:** `v10.w3` (target 2026-06-10; shipped 2026-05-25 — 16 days ahead).

---

## V10 status overview

| Week | Target | Shipped | Status |
|------|:------:|:-------:|:------:|
| W0 — Launch | 2026-05-25 | 2026-05-25 | ✅ |
| W1 — UX + WC model | 2026-05-31 | 2026-05-25 | ✅ 6 days ahead |
| W2 — Layer A auto-T | 2026-06-07 | 2026-05-25 | ✅ 13 days ahead |
| W3 — Integrate | 2026-06-10 | 2026-05-25 | ✅ 16 days ahead |
| W4 — WC live week | 2026-06-21 | 2026-06-11 → 2026-06-21 | ⏳ pending kickoff |

V10 is **17 days ahead of the original schedule** entering W4. That
buys headroom for unexpected WC-week firefighting (odds shape
changes, fixture cancellations, ROI investigation).

---

## What V10 W4 will do

W4 is the **live week** — the model + UX + Layer A all run for real
against actual WC results:

1. **Daily**: WC tab auto-fetches predictions (via cron once odds
   open). User sees probabilities the morning of each matchday.
2. **Daily**: Settle WC results within ~24h of each match's final
   whistle. The `auto_settle` CLI handles this when paired with
   actual outcomes via API-Football.
3. **Weekly (Monday 03:00)**: `weekly_calibration_check` cron runs
   — first real-data check of Layer A. With 4-6 WC matches per day
   × 7 days = ~30-40 settled pairs in the journal by the first
   weekly check.
4. **Monitoring**: `nutmeg-ab-report --weeks 4` produces the
   tournament-wide ROI verdict.

Anything else (WC tab UX bugs, blend behaviour after first odds,
unforeseen Elo lookups) is reactive work, not roadmap.

---

## File map (W3 additions / changes)

| File | Action | Purpose |
|---|---|---|
| `apps/api/src/nutmeg/v4/api/static/dashboard.html` | edit | move `#adv-toggle` out of `[role="tablist"]`; use `.adv-tab` per-button class |
| `tests/v4/test_e2e_playwright.py` | edit | update 2 tests for 9-tab default-today layout |
| `docs/v10_w3_wc_dry_run.md` | new | 15-match opening-week reference report |
| `docs/v10_w3_ship_note.md` | new | this file |
| `docs/V10_HANDOFF.md` | edit | W3 row + numbers update |
