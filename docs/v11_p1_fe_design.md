# V11 Phase 0 — Frontend Premium Refresh (P1-FE Chain)

_Drafted 2026-05-25, user-confirmed all 6 design decisions. Open
phase: V11 Phase 0 (waiting for WC verdict). 7 P1 patches, ~3.5-5.5
weeks of single-developer work._

---

## 1. Decisions locked (from 2026-05-25 conversation)

| # | Decision | Notes |
|:-:|---|---|
| 1 | Dark + light theme with toggle | follows `prefer-color-scheme`; persisted to localStorage |
| 2 | Engineer-facing tabs hidden from frontend | 4 tabs removed: 录入结果, ROI 报告, 会话历史, 规则说明. Backend ops (CLI / cron) unchanged. |
| 3 | Team logos shown | API-Football `/teams`/`/leagues` provides logo URL; cached locally |
| 4 | NO bet-execution UI | No copy-bet, no place-bet buttons. Dashboard is read-only. |
| 5 | All model / parameter / training info hidden from UI | `model_type`, `temperature_T`, `gbm_rho`, `n_train`, `Kelly fraction`, `log_loss` etc. — none surfaced |
| 6 | "Dynamic recommendations" = trigger-driven, not slider-driven | When lineups publish / odds drift, recommendations auto-revise. User sees versioned diff. |
| 7 | API-Football upgraded to **Tier 2** ($29/mo, 75000 calls/day) | Unlocks full dynamic triggers across all 14 leagues |
| 8 | Pool strategy B: EV-threshold filtering | Auto-pick matches where EV > 0.05, top market per match |
| 9 | Kelly slider: 保守 / 中 / 激进 = 0.15 / 0.25 / 0.40 | UI never says "Kelly"; just "风险偏好" |
| 10 | NO cumulative "if you had followed our picks" ROI in history | Avoid implying "system makes you money" |
| 11 | WC tab visual reworked in P1-FE#1 | Functionality unchanged; styled with new design system |
| 12 | Timing: NOW, during V11 Phase 0 wait | Parallel to WC tournament; doesn't depend on Layer A data |

---

## 2. P1 patch order (final)

```
P1-FE#1 (3-4d) →  P1-FE#2 (2d)  →  P1-FE#4 (2-3d)  →
P1-FE#3 (3-4d) →  P1-FE#5 (5-7d) →  P1-FE#6 (1-2d) →  P1-FE#7 (2d, optional)
```

| # | Title | Days | Why this order |
|:-:|---|:-:|---|
| 1 | Visual system + dark/light toggle + 4-tab removal | 3-4 | Foundation; everything else builds on this |
| 2 | Team logos + 中文名 (top 5) | 2 | Immediate visual lift; small surface area |
| 4 | 今日推荐 — pool + 风险偏好 + 最低 EV 滑块 | 2-3 | Existing tab; adds 1 missing 玩法 |
| 3 | 推荐追溯 tab (replaces engineer 会话历史) | 3-4 | Reuses observation DB schema; no new ML |
| 5 | Dynamic recommendations (triggers + versioning + diff UI) | **5-7** | The biggest new system; depends on schema additions |
| 6 | Auto-refresh (Visibility API + stale banner) | 1-2 | Glue between #5's revision events and the UI |
| 7 | 中文名补全 14 联赛 (optional) | 2 | Nice-to-have; ship later if time tight |

**Total: 19-26 days = 3.5-5.5 weeks**. Single dev. Each P1 ships independently.

---

## 3. Visual design system (P1-FE#1 deliverable)

### Color tokens

```css
/* Dark theme (default) */
:root[data-theme="dark"] {
  --bg-base:        #0a0e1a;   /* near-black navy */
  --bg-surface-1:   #131826;   /* tier-1 cards */
  --bg-surface-2:   #1c2334;   /* hover / tier-2 cards */
  --bg-surface-hi:  #232c42;   /* modals / floating */
  --border-subtle:  #2a3144;
  --border-strong:  #3d4762;
  --text-primary:   #e5e7eb;
  --text-secondary: #94a3b8;
  --text-muted:     #64748b;
  --accent-gold:    #d4a574;   /* recommendation / featured */
  --accent-green:   #34d399;   /* win / positive EV */
  --accent-orange:  #f97316;   /* attention / hot */
  --accent-rose:    #f87171;   /* loss (used sparingly) */
}

/* Light theme */
:root[data-theme="light"] {
  --bg-base:        #fafaf9;   /* warm off-white */
  --bg-surface-1:   #ffffff;
  --bg-surface-2:   #f5f5f4;
  --bg-surface-hi:  #ffffff;
  --border-subtle:  #e7e5e4;
  --border-strong:  #d6d3d1;
  --text-primary:   #1c1917;
  --text-secondary: #57534e;
  --text-muted:     #78716c;
  --accent-gold:    #b88842;   /* slightly darker for light bg contrast */
  --accent-green:   #16a34a;
  --accent-orange:  #ea580c;
  --accent-rose:    #dc2626;
}
```

### Typography

```css
--font-display: 'Inter Display', 'Outfit', 'PingFang SC', 'Noto Sans SC', system-ui, sans-serif;
--font-body:    'Inter', 'PingFang SC', 'Noto Sans SC', system-ui, sans-serif;
--font-mono:    'JetBrains Mono', 'IBM Plex Mono', 'SF Mono', Menlo, monospace;
```

Type scale (rem):
```
display-xl: 2.5    /* 40px — hero numbers */
display-lg: 2.0    /* 32px — section heads */
display-md: 1.5    /* 24px — card titles */
body-lg:    1.125  /* 18px — body */
body-md:    1.0    /* 16px — default */
body-sm:    0.875  /* 14px — secondary */
caption:    0.75   /* 12px — labels */
```

Numbers (EV, odds, stake) use `--font-mono` for visual alignment.

### Spacing scale (8px base)

```
xs:   4px      sm:   8px      md:  16px     lg:  24px
xl:  32px      2xl: 48px      3xl: 64px     4xl: 96px
```

Card internal padding: `lg` (24px). Card external gap: `lg` (24px). Section gap: `2xl` (48px).

### Card spec

```css
.card-rec {
  background: var(--bg-surface-1);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 24px;
  transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1),
              box-shadow 200ms,
              border-color 200ms;
}
.card-rec:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  border-color: var(--accent-gold);
}
```

### Microinteractions

- Tab switch: 200ms ease-out fade-in
- Card hover: 200ms transform + shadow
- Number change (when recommendation updates): 400ms scale-pulse + color flash
- Loading: skeleton blocks (not spinners)
- Theme toggle: 300ms color crossfade (`transition: background-color, color 300ms`)

### Recommendation card mockup (single-leg)

```
┌──────────────────────────────────────────────────┐
│ 🔴 利物浦  vs  阿森纳  🟢                        │
│ ─────────                                        │
│ 英超 · 周六 23:30 · 主场: 安菲尔德               │
│                                                  │
│   推荐                                           │
│   主胜 (利物浦)                                  │
│   ─────────                                      │
│   ¥240                                           │
│   建议投注                                       │
│                                                  │
│   赔率 2.45     ▓▓▓▓▓▓░░░░  +12% 期望值         │
│                                                  │
└──────────────────────────────────────────────────┘
```

Big numbers ($240) in mono font, gold accent. EV bar visual not %. No "Kelly", no "log-loss", no model info.

---

## 4. Per-P1 scope detail

### P1-FE#1: Visual system + dark/light + tab cleanup (3-4 days)

**Deliverables**:
- `apps/api/src/nutmeg/v4/api/static/style.css` — new design tokens + base components
- `dashboard.html` rewrite of:
  - All 5 retained tabs (today / single / parlay / pool / WC) with new visual
  - 4 engineer tabs REMOVED from HTML (today / single / parlay / pool / WC remain; 高级 ▾ button removed since nothing left to fold)
  - Theme toggle button in header (sun / moon icon)
  - Rules info → right-bottom corner `ⓘ` popover (CSS-only)
- All "engineer info" stripped from card rendering:
  - Strip `model_type`, `gbm_rho`, `training_cutoff`, `n_train`, `snapshot_phase`, `temperature_T`
  - Replace "EV per unit 0.12" → visual bar
  - Replace "Kelly fraction" → just "建议投注 ¥XXX"
  - Replace "log-loss" / "ECE" everywhere → don't render
- localStorage theme persistence (`nutmeg-theme: dark | light`)
- WCAG re-audit pass (target 0 AA violations like V10 W3)

**Files touched**: ~5 (dashboard.html, new style.css, schemas response trimming, 1-2 small JS adjustments)

**Tests updated**: Playwright tab count 9 → 5 (or 6 with WC), color contrast assertions, theme toggle test, axe-core re-run.

### P1-FE#2: Team logos + Chinese names — top 5 leagues (2 days)

**Deliverables**:
- `data/external/team_logos/` — local cache of logo PNGs (1 per team, ~100 teams for top 5)
- New CLI `nutmeg-ingest-team-logos` (one-shot, ingests via API-Football `/teams`)
- `apps/api/src/nutmeg/v4/data/team_name_zh.py` — static dict for ~100 top-5 teams
- `lookup_zh(team_name) → str` helper
- Dashboard renders logo + name (Chinese when `lang=zh`, English when `lang=en`)
- Fallback: when logo unavailable, show team's first 2 letters in a colored circle

**API budget for one-shot ingest**: 1 call per team × ~100 teams = 100 calls. Negligible on Tier 2.

### P1-FE#4: 今日推荐 — pool + sliders (2-3 days)

**Deliverables**:
- Backend: `today-recommendations` endpoint now returns `pool` field (currently only `single` + `parlay`)
- Strategy B implementation: filter matches to `ev_per_unit > 0.05`, pick max-EV market per match, generate C(M, N) pool
- 3 new UI sliders (under existing budget input):
  - `风险偏好`: 保守 / 中 / 激进 (maps to Kelly 0.15 / 0.25 / 0.40)
  - `最低期望值`: -5% / +0% / +5% / +10% (filter threshold)
  - Existing budget slider stays
- All 3 sliders trigger debounced re-fetch (500ms; existing pattern)
- Pool result card design (M-select-N visualization with combo count)

**Schema additions**:
```python
# schemas.py TodayRecommendationsRequest
risk_preference: Literal["conservative", "balanced", "aggressive"] = "balanced"
min_ev: float = 0.05  # default +5%

# schemas.py TodayRecommendationsResponse
pool: Optional[PoolRecommendationResponse] = None  # NEW
```

### P1-FE#3: 推荐追溯 tab (3-4 days)

**Deliverables**:
- NEW dashboard tab: `推荐追溯` (replaces deleted 4 engineer tabs)
- Timeline view, grouped by date (descending; most recent on top)
- Each day shows N recommendation cards with:
  - Match info (logos + 中文 names + kickoff time)
  - What was recommended (single/parlay/pool + stake)
  - Outcome label:
    - ✓ 命中 (柔绿底, 浅金边)
    - ✗ 未命中 (灰底, 不用红)
    - ⌛ 待结算 (灰底 + 旋转图标)
- Date-range filter: last 7 days / last 30 days / all time
- Per-tab stats card at TOP (no cumulative ROI per decision; just):
  - 推荐总数 (X 注)
  - 命中数 (Y / X)
  - 命中率 (Y/X %)
- New endpoint: `GET /api/v4/observation/recommendations-history?days=N`
  - Returns per-day grouped recommendation + outcome data
  - Reuses existing `recommendation_sessions` + `parlay_recommendations` + `settlements` joins

**Backend changes**: 1 new endpoint, no schema change (data all in observation DB).

### P1-FE#5: Dynamic recommendations (5-7 days)

**Deliverables**:

**A. Trigger system** (3 days):
- New launchd job: `com.nutmeg.lineup_publish_watcher` — runs every 30 min
  - For each upcoming fixture in next 6 hours, polls API-Football `/fixtures/lineups`
  - Detects `lineup.status: published` transition
  - When detected: triggers a `regenerate_recommendation` event
- New launchd job: `com.nutmeg.odds_drift_watcher` — runs every 30 min
  - Polls `/odds` for upcoming-within-12-hours fixtures
  - Compares to last-stored Pinnacle 1X2; if KL divergence ≥ 0.05 (or any prob shifts ≥ 5pp): triggers regenerate
- New cron times: 08:00, 14:00, 20:00 daily (3 scheduled regenerations beyond event triggers)

**B. Versioning schema** (1 day):
```sql
ALTER TABLE recommendation_sessions ADD COLUMN revision_id INTEGER NOT NULL DEFAULT 1;
ALTER TABLE recommendation_sessions ADD COLUMN parent_session_id INTEGER;
ALTER TABLE recommendation_sessions ADD COLUMN trigger_reason TEXT;  -- 'scheduled'|'lineup_published'|'odds_drift'|'user_request'
ALTER TABLE recommendation_sessions ADD COLUMN trigger_details_json TEXT;
ALTER TABLE recommendation_sessions ADD COLUMN diff_summary_json TEXT;
```

`diff_summary_json` shape:
```json
{
  "changes": [
    {
      "match": "Liverpool vs Arsenal",
      "before": {"market": "1x2", "outcome": "H", "stake": 240, "odds": 2.45},
      "after":  {"market": "1x2", "outcome": "A", "stake": 180, "odds": 3.20},
      "reason": "Salah listed as bench in published lineup; away EV jumped from 0.04 to 0.11"
    }
  ]
}
```

**C. Diff UI** (2 days):
- Top of 今日推荐 tab: alert banner when latest revision differs from what user last viewed
  - "⚡ 推荐已更新 · 14:32 (上次 08:15) · 1 处变化"
  - Click → expand diff card showing per-match before/after with reason
- "更新历史" mini-timeline at bottom of dashboard (last 3-5 revisions of today's recommendation)

**D. Background recompute** (1 day):
- `regenerate_recommendation_today()` function runs the same recommend pipeline used by `today-recommendations` endpoint
- Stores new revision; computes diff vs prior revision
- Notifies frontend via stale-check endpoint (see P1-FE#6)

### P1-FE#6: Auto-refresh (1-2 days)

**Deliverables**:
- `GET /api/v4/today-recommendations/stale-check?last_revision_id=N` — lightweight, returns `{ "stale": true|false, "latest_revision_id": M, "summary": "..." }`
- Frontend ping every 60 seconds (only when tab is visible — Page Visibility API)
- When stale-check returns `stale: true`:
  - If user has been idle ≥ 5 min: silent refetch
  - If user is actively interacting: show top banner "推荐已更新 · 点击查看 ↓"
- When tab visibility changes from hidden → visible: trigger one stale-check immediately
- localStorage stores user's last-viewed `revision_id`

### P1-FE#7: 中文名补全 14 联赛 (2 days, optional)

**Deliverables**:
- Extend `team_name_zh.py` to cover ~300 teams across all 14 leagues
- Translation sources: Wikipedia interlanguage + manual curation for tricky ones (中超 + J League already have native Chinese)
- Tests for translation lookups
- Optional: extend to logos for all 14 leagues (another ~200 logo downloads)

---

## 5. API budget plan (Tier 2)

Daily call estimate after all P1 ship:

| Source | Calls/day | Notes |
|---|---:|---|
| `daily_odds` (3 scheduled cron) | ~100 | 3 × 14 leagues × ~3 odds calls/match |
| `daily_recommend` (3 scheduled cron) | ~30 | reuses fixture cache; minimal API hits |
| `lineup_publish_watcher` (every 30 min, 6hr lookahead) | ~1500-2500 | 14 leagues × ~30 matches/day × 12 polls each |
| `odds_drift_watcher` (every 30 min) | ~500-1000 | only ping fixtures within 12 hr of kickoff |
| `weekly_settle` + `weekly_gate` | ~50 | unchanged |
| `daily_wc_predict` + `daily_wc_settle` | ~30 | unchanged |
| `nutmeg-ingest-team-logos` (one-shot) | 100 | one time |
| `nutmeg-build-team-names-zh` (one-shot) | ~50 | one time |
| | | |
| **Total daily average** | **~2200-3700** | |
| **Tier 2 limit** | **75000/day** | 20-30x buffer |

Plenty of headroom. The bottleneck moves from "API budget" to "code complexity".

---

## 6. Final tab structure (post-P1-FE#1)

```
┌────────────────────────────────────────────────────────────────┐
│  Nutmeg                                  🌙 主题切换  ⚙ 设置  │
├────────────────────────────────────────────────────────────────┤
│  🎯 今日推荐  ① 单关  ② 串关  ③ 复式  ⏱ 推荐追溯  🏆 WC 2026  │
└────────────────────────────────────────────────────────────────┘
```

5 always-visible tabs + WC 2026 (conditionally shown during tournament window).

Right-bottom corner: `ⓘ` button — hover/click reveals 竞彩规则 popover.

No "高级 ▾" button (nothing left to fold).

---

## 7. Risk register

| Risk | Severity | Mitigation |
|---|:-:|---|
| Lineup watcher hits rate limit on busy match days | L | Tier 2 has 30x headroom; degrade gracefully (skip lower-priority leagues if approaching limit) |
| Dynamic recompute changes recs while user is mid-view | M | Stale banner not auto-replace; only silent refresh after 5 min idle |
| Theme switch causes layout jitter | L | All colors via CSS variables; no width/height changes |
| Logo cache stale (team relegated / promoted) | L | Re-run `nutmeg-ingest-team-logos` quarterly |
| Chinese translation table missing entries | L | Fallback to English name; log misses for human review |
| Diff logic produces noisy false-positive changes | M | Only flag changes that affect the picks (not just probability shifts < 1pp) |
| Pool auto-selection picks weird combinations | M | Strategy B requires EV > 5% AND hit_p ≥ 0.10 for inclusion; can dial both |
| Recommendation history table grows unbounded | L | Add cleanup policy at 90+ days (V12 housekeeping) |

---

## 8. Test plan

Per P1, the test additions roughly:

| Patch | New tests | Test files |
|:-:|---:|---|
| P1-FE#1 | ~15-20 | test_dashboard_visual.py, test_theme_toggle.py, update test_e2e_playwright.py |
| P1-FE#2 | ~10 | test_team_logos.py, test_team_name_zh.py |
| P1-FE#4 | ~12 | extend test_today_recommendations.py (pool + sliders) |
| P1-FE#3 | ~10 | test_recommendations_history.py (endpoint + UI) |
| P1-FE#5 | ~25-30 | test_lineup_watcher.py, test_odds_drift.py, test_recommendation_versioning.py, test_diff_renderer.py |
| P1-FE#6 | ~8 | test_stale_check.py + Playwright auto-refresh test |
| P1-FE#7 | ~5 | extend team_name_zh tests |
| | | |
| **Total new** | **~85-95** | |

Target: 1175 → ~1265 tests post-chain. Zero regression on the existing 1166.

---

## 9. Ship gates (per P1)

Each P1 ships independently when:
- All new tests pass + zero regression on existing 1166
- WCAG AA: 0 axe-core violations (maintain V10 W3 standard)
- Playwright E2E green
- Manual smoke test on local dashboard
- Doc updated (V11_HANDOFF if shipping; ship note per patch)

After **all 7 P1 ship**: tag `v11.frontend-refresh` (NOT a v11.0 ship — V11 ship still waits for WC verdict + Layer A cycles).

---

## 10. What this doc deliberately doesn't cover

- Hyperparameter tuning of the recommendation logic (no model changes)
- New ML features (stays at V10 W2 Layer A baseline)
- Mobile-native app (out of scope; this is dashboard refresh)
- Multi-language beyond zh + en (only 中英 supported via P1#14 i18n framework)
- WC tab CONTENT changes (only visual restyle in #1)

---

## 11. Sign-off

User confirmed all 12 decisions on 2026-05-25 (in conversation
following V11 Phase 0 league coverage audit).

API-Football Tier 2 upgrade ($29/mo) is the user's commitment. The
P1-FE chain WILL exceed free-tier limits — Tier 2 is mandatory.

Starting P1-FE#1 immediately after this doc commits.
