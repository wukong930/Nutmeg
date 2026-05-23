# V6 W10 — Chinese dashboard + rule explainers

_Translates the residual English copy in `dashboard.html` and adds a
dedicated 规则说明 tab so users understand the lottery's structural
constraints (¥2 起投, ¥20k 上限, 派奖率 68.5%, 浮动 SP, ≤8 串) without
hunting through the V4 codebase. Rules are now served dynamically from
`/api/v4/rules`, so a future tweak in `combo.lottery_rules.JINGCAI_DEFAULT`
auto-propagates to every UI surface._

## What changed

| Layer | Change |
|---|---|
| `apps/api/src/nutmeg/v4/api/schemas.py` | Add `LotteryRulesResponse` Pydantic model exposing every field of `LotteryRules` plus a Chinese `label`. |
| `apps/api/src/nutmeg/v4/api/routes.py` | New endpoint `GET /api/v4/rules` returns `JINGCAI_DEFAULT` as JSON. Single source of truth for client-side rule rendering. |
| `apps/api/src/nutmeg/v4/api/static/dashboard.html` | New tab `⑤ 规则说明` with sections 投注规则 / 派奖机制 / 推荐门槛 / 玩法说明 / 风险提示. Values populated from `/api/v4/rules` so dashboard reflects the running server. |
| same | Inline `#rules-hint` banner on the recommend tab summarises the four most important rules with a "详细规则 →" link. |
| same | Subtitle now reads "中国体彩 · 胜平负 + 让球胜平负 · 串关推荐 (单关/复式 请用 nutmeg-rec CLI)" pointing users to the V6 W9 CLI for the products the dashboard doesn't surface. |
| same | "of bankroll" English phrase replaced with "占预算 X%" everywhere it appeared. |
| same | Bankroll + min-kelly inputs snap to ¥2 (step=2, min=2). |
| same | New `loadRules()` + `renderRules()` JS; `switchTab()` helper consolidates tab activation logic (inline links like the "详细规则 →" anchor now switch tabs). |

## The /api/v4/rules contract

```json
{
  "stake_unit": 2.0,
  "max_ticket_stake": 20000.0,
  "max_period_stake": 200000.0,
  "min_parlay_legs": 2,
  "max_legs_per_ticket": 8,
  "payout_ratio": 0.685,
  "vig": 0.315,
  "min_ev_per_unit": 0.05,
  "min_hit_probability": 0.05,
  "label": "中国体彩 · 竞彩足球"
}
```

Single read endpoint; no parameters. The dashboard caches the response
after first load (`RULES` variable in `dashboard.html`) — subsequent tab
switches don't re-fetch.

## Rule tab contents

### 💰 投注规则

| 项目 | 取值 | 含义 |
|---|---|---|
| 起投单位 | ¥2 | 单注最低金额, 倍数限制 |
| 单注上限 | ¥20,000 | 每张票最大金额, 超过则系统拒单 |
| 串关下限 | 2 串 | 混合过关最少串关数 |
| 串关上限 | 8 串 | 混合过关最多串关数 |

### 🎲 派奖机制

| 项目 | 取值 | 含义 |
|---|---|---|
| 派奖率 | 68.5% | 平均派奖比例 |
| 庄家抽水 (vig) | 31.5% | = 1 - 派奖率. 对比 Pinnacle ~2.5%, 竞彩高 ~12x |

### ✅ 推荐门槛

| 项目 | 取值 | 含义 |
|---|---|---|
| 最小 EV/单位 | 5% | 票面 EV 低于此值不推荐 |
| 最小命中率 | 5% | 低命中率 + 高赔率 = 高方差, 筛掉 |
| 凯利分数 | 0.25 | 部分凯利, 防过激加仓 |
| 单注预算占比 | ≤ 5% | 单张票最高占预算 5% |

### 📋 玩法说明 (excerpt)

- **胜平负 (1X2)**: 不带让球, 单纯主队胜/平/客胜
- **让球胜平负**: 带整数让球数; 按让球后比分判定
- **浮动让球**: 让球数在下单瞬间锁定
- **浮动 SP**: 赔率在下单瞬间锁定
- **单关 / 串关 / 复式**: 三种产品入口

### ⚠️ 风险提示

- 系统仅提供参考推荐, 从不自动下单
- 派奖率 68.5% 意味着即使 +5% EV 仍有较大方差
- 建议每周 ROI 复盘, 连续 4 周 ROI 负值时停手

## What W10 doesn't do

- **No 单关 / 复式 dashboard surfaces**: the recommend tab still drives 串关
  only. 单关 + 复式 stay CLI-only via V6 W9's `nutmeg-rec`. Adding new
  dashboard tabs for the other two products would be a substantial UI
  build (separate fixture input shapes, different result layouts).
  Subtitle now explicitly directs users to the CLI for these.
- **No live odds scraping**: fixtures + odds still come from a pasted
  JSON array. Hooking up an automatic scraper is V7 territory.
- **No localized labels for league codes**: "EPL", "ESP_LA_LIGA" etc are
  still surfaced in English. Chinese names exist in the test fixtures
  (`team_canonical_map.csv`) but not bridged to the API response. Quick
  follow-up if needed.

## Tests

`tests/v4/test_rules_endpoint.py` — 10 tests:

- `TestRulesEndpoint` (5) — 200 status, values match `JINGCAI_DEFAULT`,
  label is Chinese, payout + vig = 1.0, vig is lottery-scale (≥ 10%)
- `TestDashboardChineseLocalization` (5) — rules tab present, JS wires
  up `loadRules` + fetches `/rules`, Chinese terms surface (派奖率,
  浮动让球, 浮动 SP, 起投, ¥2, ¥20,000, 庄家抽水, 凯利), no orphan
  "of bankroll" copy, step=2 on stake inputs

Full V4 suite: **428/428 passing** (418 prior + 10 new W10).

## Files touched in W10

```
apps/api/src/nutmeg/v4/api/routes.py               [M] /rules + import
apps/api/src/nutmeg/v4/api/schemas.py              [M] LotteryRulesResponse
apps/api/src/nutmeg/v4/api/static/dashboard.html   [M] ⑤ tab + hints + JS
tests/v4/test_rules_endpoint.py                    [+] 10 tests
docs/V6_ROADMAP.md                                 [M] W10 ✅
docs/v6_w10_chinese_dashboard.md                   [+] (this file)
```

## Next: V6 W11

Cup data + national teams — World Cup, Euro, UCL knockouts, FA Cup
ingest; cross-league team handling. Estimated 3-5 days.
