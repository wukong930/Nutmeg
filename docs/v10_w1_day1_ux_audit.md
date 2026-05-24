# V10 W1 Track A Day 1 — Dashboard UX audit + wireframe

_Generated 2026-05-25. Parallel with Track B Day 1 (WC ingest).
Today: audit current dashboard, design new flow. Implementation
starts Day 2._

## Audit — what's wrong today

Current `dashboard.html` (1,382 lines, 7 tabs) is **engineer-facing**.
Every primary action requires the user to be a developer:

| Tab | Required user input | Engineer-facing surface |
|---|---|---|
| 单关 | JSON textarea (固定 14 rows) + bankroll + 4 knobs | JSON textarea, "使用示例数据 (8 场)" button, "凯利分数" / "每场最多" sliders |
| 串关 | Same JSON textarea + bankroll + 5 knobs | Same JSON + "最大推荐数 / 最小命中率 / 最小凯利" inputs |
| 复式 | Same JSON + N legs + budget | Same JSON + dropdown for N |
| 录入结果 | Manual match outcome entry | OK for ops, not user product |
| ROI | Read-only stats | OK |
| 会话 | Read-only history | OK |
| 规则 | Static reference | OK |

### Concrete pain points (user-flagged)

1. **"用户给了预算金额才生成推荐"** — current 3 betting tabs all
   require bankroll as INPUT GATE. Should be ADJUSTMENT KNOB on
   existing recommendations.
2. **"前端不用把复杂的代码暴露给用户"** — the 3 JSON textareas
   each fill ~30% of viewport vertical space and are the visual
   center of attention. They should be invisible by default.
3. **Page load shows empty forms** — visiting `/dashboard` greets
   you with 3 empty JSON boxes. Should show today's actual
   recommendations immediately.
4. **3 separate game-type tabs** — user has to manually click each
   tab and re-paste JSON to see all options. Should be unified
   "today's recommendations" view that shows all 3 game types
   at once.
5. **"使用示例数据" buttons** — pure engineer affordance. No real
   user wants pre-baked 2024 demo data when WC is starting tomorrow.

## Wireframe — new flow

### Landing experience (default tab)

```
┌──────────────────────────────────────────────────────────┐
│ Nutmeg · 竞彩足球助手                  [中/English] [≡] │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  今日推荐 · 2026-05-25                                   │
│  预算 [¥ 1000 ▾]   联赛 [EPL + La Liga + ... ▾]        │
│                                                          │
│  ┌─ ① 单关 (3 注) ──────────────────────────────────┐   │
│  │ • Arsenal 主胜 @ 1.85    停 ¥45    EV +7%        │   │
│  │ • Real Madrid 让 -1.5 @ 2.10    停 ¥30   EV +9% │   │
│  │ • Bayern 平 @ 4.50    停 ¥15    EV +12%         │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─ ② 串关 推荐 (2 注 · 3串1) ─────────────────────┐   │
│  │ • Arsenal + Real + Bayern @ 5.21   停 ¥30        │   │
│  │ • Liverpool + Inter + PSG @ 4.85   停 ¥25        │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─ ③ 复式 (5 选 3) ───────────────────────────────┐   │
│  │ 候选 5 场 + 选 3 组合 = 10 注 · 总停 ¥80         │   │
│  │ 平均 EV +12%  · [展开 10 注详情 ▾]              │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─ 总计 ─────────────────────────────────────────┐   │
│  │ 推荐总停: ¥225 / ¥1000                          │   │
│  │ 加权 EV: +8.4%                                  │   │
│  │ [按方案下注] [仅看单关] [跳过今日]              │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ─────────────────────────────────────────────────────  │
│  高级 ▾  (手动 fixtures / 自定义 knobs / 录入结果 / ROI 报表) │
└──────────────────────────────────────────────────────────┘
```

### Interactions

1. **页面 load**: dashboard 立刻调用 `GET /v4/today-recommendations`
   (new endpoint, see below), 3 个 sections 同时填充。No user input.

2. **用户改预算**: 输入框失焦 → frontend 自动 re-fetch with new
   bankroll → 3 sections 重新填充。无需点 "生成" 按钮。
   (Debounce 500ms so typing isn't spammy.)

3. **用户改联赛 filter**: 同上, 但 backend 也用 filter 重新跑 auto-fetch。

4. **"高级 ▾" 折叠区**: 默认隐藏。展开后是当前 7 个 tabs 的全部
   功能 — JSON textareas / 录入结果 / ROI / 会话 / 规则。**保留**,
   只是默认收起。这样新人不被吓到, 工程师 / 高级用户仍可访问。

## New endpoint design — `GET /v4/today-recommendations`

Server-side:
```
1. fetch_today_fixtures(leagues=DEFAULT_LEAGUES, date=today)
   → 调用现有 ingest_odds 逻辑 (V7 W1 已实现)
2. for each of {single, parlay, pool}:
   call existing recommend function with bankroll=req.bankroll
3. assemble combined response:
   {
     date: "2026-05-25",
     leagues: [...],
     bankroll: 1000.0,
     single: {recommendations: [...], n: 3, total_stake: 90},
     parlay: {recommendations: [...], n: 2, total_stake: 55},
     pool:   {recommendations: [...], n: 10, total_stake: 80},
     summary: {total_stake: 225, weighted_ev: 0.084},
   }
```

Request body shape (POST instead of GET since we want bankroll + filters):
```python
class TodayRecommendationsRequest(BaseModel):
    date: str | None = None        # default today
    leagues: list[str] = ["EPL", "ESP_LA_LIGA"]
    bankroll: float = 1000.0
    include: list[str] = ["single", "parlay", "pool"]  # subset for users who want only some
    record_session: bool = False   # P1#7 dashboard checkbox semantics carry over
```

Response model:
```python
class TodayRecommendationsResponse(BaseModel):
    date: str
    leagues: list[str]
    bankroll: float
    fixtures_fetched: int
    single: SingleRecommendResponse | None
    parlay: RecommendResponse | None
    pool: PoolRecommendResponse | None
    summary: TodaySummary  # {total_stake, weighted_ev, n_recs_total}
```

Reuses existing recommend functions internally — no new ML logic.

## Implementation plan (Day 2 - Day 5)

| Day | Track A task |
|---|---|
| 2 | Build `/v4/today-recommendations` endpoint (server) + tests |
| 3 | Build new dashboard "今日推荐" tab (HTML + JS) |
| 4 | Fold current 7-tab UI into "高级 ▾" collapsible panel |
| 5 | Mobile responsive check + i18n strings + Playwright E2E |

W1 ship target: 2026-05-31 with `v10.w1` tag.

## What stays untouched

- ✅ All existing endpoints (`/recommend`, `/recommend/single`,
  `/recommend/pool`, `/predictions/upcoming`) — preserved verbatim
  so any CLI / cron job / external integration still works
- ✅ Lottery rules engine, EV gate, Kelly fraction — model layer unchanged
- ✅ i18n framework (P1#14) — just adds new keys
- ✅ PWA manifest (P1#14) — just updates the default tab pointer
- ✅ Observation recording (P1#7-8) — checkbox flows through
- ✅ Mobile + a11y compliance (P1#13) — new HTML follows same
  patterns (`md:hidden vs md:block`, ARIA roles, inputmode)

## What's deferred to V11+ (per V10 anti-patterns)

- 真实在线学习 (Layer C) — never
- Real-time push notifications when new recommendation appears — V12
- 用户账户 / 历史记录持久化 — V11+ if multi-user
- A/B test of recommendation framing (probability vs odds vs EV) — V11

## Anti-patterns we're explicitly avoiding

1. **Don't redesign the 单关/串关/复式 inner UX** — those forms work,
   just hide them behind "高级 ▾". The inner forms can be polished
   in V11 if needed.
2. **Don't auto-record observations from the "今日推荐" landing page
   without explicit user opt-in** — record_session stays gated by
   both env AND request flag (P1#7 / V9 W3 design preserved).
3. **Don't show predictions for matches without odds** — if API-Football
   returns 12 fixtures but only 8 have closing-line, only recommend
   on the 8. Edge cases like Ligue 1 morning matches without odds
   should silently drop, not throw error.
4. **Don't add a "buy bet slip" / 自动 place bet button** — explicit
   project rule (no automated betting). "[按方案下注]" is a hint, not
   a click-to-buy.

## Companion file in this commit

`docs/v10_w1_day1_ux_audit.md` (this file). No code yet.

Day 2 starts: build `/v4/today-recommendations` endpoint + tests.
