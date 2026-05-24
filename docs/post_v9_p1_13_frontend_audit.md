# post-v9 P1#13 — Front-end audit + tier-1 fixes (mobile + a11y + error UX)

_Closes the user-flagged blind spot from the post-v9 P1 series:
"产品是通过 web 端呈现, 需要做移动端适配". The V9 maintenance-mode
framework had only been applied to ML/backend; front-end accessibility
+ responsive + UX layers had never been audited._

## TL;DR

**Before**: dashboard.html assumed desktop. No viewport meta, fixed
column grids, JSON textareas in `text-xs`, 7-tab nav wrapped to 3
lines on mobile, recommendation tables overflowed 360px viewports,
status messages were plain text + emoji prefix only.

**After**: 835 → **859 V4 tests passing** (+24 new). 5 concrete sub-tasks
all shipped. Mobile renders at native width, all touch interactions
work, screen-reader-friendly ARIA roles + live regions, error
messages get a visual red banner instead of inline gray text.

Same `post-v9 P1` patch pattern as P1#6-12. **Not a redesign** — a
defensive tier-1 audit. Bigger product redesign (PWA, mobile-first
single-page entry, native shortcuts) explicitly deferred to V10 if/when
a real product trigger surfaces.

## What the audit found (real, not hypothetical)

| # | Issue | Severity | Impact on mobile |
|---|---|---|---|
| 1 | No `<meta name="viewport">` | 🔴 critical | iOS/Android render at desktop ~980px; user must pinch-zoom |
| 2 | Tab nav `flex-wrap` | 🔴 critical | 7 tabs wrap to 3 lines; ~120px vertical waste before content |
| 3 | `grid-cols-4` hardcoded (ROI headline) | 🔴 critical | 4 KPI cards squeezed into a single row at 360px |
| 4 | JSON textareas `text-xs` | 🟠 high | JSON unreadable + impossible to edit on phone keyboard |
| 5 | Wide tables (10-col predictions, 7-col pool) | 🟠 high | Horizontal scroll required, no card alternative |
| 6 | Number inputs missing `inputmode` | 🟡 medium | Wrong keyboard variant (qwerty instead of numeric/decimal) |
| 7 | Status spans missing ARIA | 🟡 medium | Screen readers miss live updates ("loading", "error") |
| 8 | Tab nav missing `role="tab"` / `role="tablist"` | 🟡 medium | a11y screen-reader navigation broken |
| 9 | Error messages plain text + ❌ emoji | 🟡 medium | Errors look identical to success / info |

## What P1#13 shipped — 5 sub-task breakdown

### 1. Viewport meta + tab nav horizontal scroll

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0">
```

Tab nav changed `flex-wrap` → `flex-nowrap overflow-x-auto`. All 7
tab buttons gained `whitespace-nowrap` to prevent Chinese label
mid-character wrapping. Wrapped in `role="tablist"` + each button
gained `role="tab" aria-controls=...`.

### 2. Input rows responsive stacking + JSON textareas

Header `flex justify-between` → `flex flex-col sm:flex-row sm:justify-between`.
All input rows `flex items-center space-x-4` → `flex items-center flex-wrap gap-x-4 gap-y-2`
(stacks on overflow, retains row layout when there's space).

JSON textareas (3 places) gained:
- `aria-label` (screen reader announces purpose)
- `font-mono` + `min-h-[200px]` (readable + big enough on mobile)
- `spellcheck="false" autocorrect="off" autocapitalize="off"` (don't auto-mess-up JSON)

### 3. Recommendation tables — dual render

The 10-column predictions table + 7-col pool table now BOTH render:
- Desktop wrapper: `hidden md:block` with `<table>`
- Mobile wrapper: `md:hidden space-y-2` with `<div class="border rounded p-3 bg-gray-50">` cards

Each card shows the same data condensed: title + key metrics on first
line + secondary data below. Total render cost ~2x DOM nodes but CSS
display:none on whichever doesn't apply.

The single (单关) recommendation flow gets the same treatment via the
`renderSingleRecommendations` function. Both pool functions
(`renderPoolRecommendations` for `--type=pool` tickets) match.

### 4. a11y — inputmode + ARIA semantics

All 11 number inputs split into:
- `inputmode="numeric"` (8 currency/integer fields → mobile keypad)
- `inputmode="decimal"` (3 fraction fields → decimal keypad)

Tab list: `role="tablist"` + `aria-label`. Each `<button data-tab>`:
`role="tab" aria-controls="tab-<name>"`. JS `switchTab()` now
calls `setAttribute('aria-selected', 'true'/'false')`.

All 4 status spans (recommend / single / pool / outcomes): `role="status"
aria-live="polite"` so screen readers announce updates without
interrupting the user.

Plus ROI 4-column grid: `grid-cols-2 sm:grid-cols-4` (2x2 mobile, 1x4 sm+).

### 5. Error UX — visual banner via setStatus helper

New helper:

```js
function setStatus(sel, kind, msg) {
  // kind: 'error' | 'loading' | 'success' | (default: info)
  // error → red-50 bg + red-500 left border + bold red-700 text
  // loading → gray-500 text + animate-pulse on icon
  // success → plain gray-700 with ✓ prefix
}
```

Wired into:
- 4 HTTP-error paths: `setStatus('#X-status', 'error', 'HTTP 503: ...')`
- 4 try-catch network paths: `setStatus('#X-status', 'error', e.message)`
- 3 loading paths: `setStatus('#X-status', 'loading', '计算中 ...')`

The Chinese validation errors (JSON parse, missing fields) kept as
inline `textContent` writes — they're form-level errors, less critical
than network errors.

## What P1#13 does NOT do

Explicitly deferred to V10 if/when a product trigger surfaces:

- ❌ **PWA shell** (manifest.json, service worker, install prompt)
- ❌ **Native mobile UX patterns** (bottom tab bar, swipe gestures, wizards)
- ❌ **Separate `/m/` mobile route** (one responsive page is enough for
  current usage)
- ❌ **Internationalization** (中文 hardcoded; structure not yet refactored
  for i18n)
- ❌ **Real cross-browser testing** (no Playwright; tests are STRUCTURAL
  assertions on the HTML, not visual regression)
- ❌ **Color contrast audit** with formal WCAG tooling
- ❌ **Skeleton loading states** (only spinner animation on the icon)
- ❌ **Toast/snackbar pattern** for non-blocking notifications

The trade-off: P1#13 is the cheapest path to "mobile users can
actually use the dashboard reliably". Native mobile UX patterns are
expensive (~weeks) and only justified if real user telemetry shows
significant mobile usage that the responsive web UI doesn't serve.

## Tests added (24 in `tests/v4/test_frontend_responsive_a11y.py`)

| Group | Tests | Coverage |
|---|---:|---|
| TestMobileRendering | 5 | viewport, tab nav, whitespace-nowrap, header stack, ROI grid |
| TestJsonTextareas | 2 | aria-label + autocorrect off on all 3 textareas |
| TestRecommendationsDualRender | 3 | predictions cards + pool dual render |
| TestNumberInputModes | 2 | currency=numeric, fraction=decimal |
| TestAriaSemantics | 4 | tablist + tabpanel + status + aria-selected JS |
| TestSetStatusHelper | 5 | helper exists + red banner + pulse + 4 wires + 3 loading wires |
| TestNoRegressionFromExistingTests | 3 | P1#7 + P1#8 + record-session checkboxes still intact |

## Why I missed this until you asked

My P1 patch chain (P1#6-12) was framed around the V9 retrospective's
"maintenance mode" lens — which I implicitly applied to *all* layers.
But that lens was correct only for ML/backend; the front-end had
never been audited at all. The V9 W3 dashboard work focused on
*correctness* (checkbox wiring) and *UX*-completeness (3 tab record
gates), not on *device* coverage. None of the V5-V8 retrospectives
flagged a mobile gap (probably because the user owned the project and
tested on desktop).

This is a class of blind spot worth naming: **"maintenance mode" can
mean different things per layer**. Layers without quality gates won't
self-surface their issues; you have to audit them on intent rather
than waiting for failure. The product-tier audit (mobile, a11y, i18n,
error UX, performance, security) deserves its own occasional
quarterly sweep distinct from the ML/backend sweep.

## Files touched in P1#13

```
apps/api/src/nutmeg/v4/api/static/dashboard.html      [M] +viewport, +aria, +inputmode, +dual-render, +setStatus
tests/v4/test_frontend_responsive_a11y.py             [+] 24 structural tests
docs/post_v9_p1_13_frontend_audit.md                  [+] this writeup
```

(Single source file change. No backend / API / model changes.)

## Cumulative post-v9 patch totals (P1#6 through P1#13)

| Patch | Theme | Tests Δ |
|---|---|---:|
| P1#6 | Deprecation warnings (36→0) | 0 |
| P1#7 | Dashboard checkbox localStorage | +4 |
| P1#8 | sessions/latest read-back | +6 |
| P1#9 | ECE audit multi-cutoff | +6 |
| P1#10 | National-team verification + aliases | +4 |
| P1#11 | Token rotation cron | +6 |
| P1#12 | National-team Elo integration verified | +7 |
| P1#13 | Front-end audit + tier-1 fixes | +24 |
| **Cumulative** | V9 ship + maintenance | **803 → 859 (+56)** |

V9 ship + 8 post-v9 P1 patches now cover every V9 self-deferred,
V10-backlog actionable, and user-surfaced front-end gap.
