# V12 W3 候选: 半自动 SP 输入工作流

_2026-05-26 · 用户明确选择 "半自动 (手填 SP 数字)" 方案_

---

## 0. 用户决策

> "半自动 (手填 SP 数字)，我接受"

排除两个极端:
- ❌ **全自动爬虫** (jingcai.lottery.gov.cn / 500w.com) — 反爬复杂, 合规风险
- ❌ **全手动** (现在 dashboard 单关 tab 输入 JSON) — 烦, 容易出错

接受**半自动 (B)**: dashboard 自动从 cron 拉今天的比赛 + 预填 λ 和 P(H/D/A), 用户**只输竞彩 SP 数字** (1X2 + 让球数 + 让球 SP)。

---

## 1. 现状 (V12 当前)

| 步骤 | 谁做 | 工具 |
|---|---|---|
| 1. 拉今日 fixtures + Pinnacle SP | cron 自动 | `ingest_odds → CSV` |
| 2. 用 model 算 λ + P(H/D/A) | cron 自动 | `recommend.py` |
| 3. 看到竞彩 app 列的比赛 | 用户手动 | 体彩 app |
| 4. 把竞彩 SP 输入系统 | **用户手动** | **dashboard 单关 tab → JSON 粘贴** ⚠️ 痛点 |
| 5. 系统给 EV + Kelly 推荐 | 系统自动 | `single_match.py` |
| 6. 用户下注 + 记录 session | 用户去竞彩 app 下注 | 自动 record_session |

**痛点 4** 现在的体验:
- 打开 dashboard → 单关 tab
- 看到一个空 JSON textarea
- 自己拼出 fixture JSON (date / league / home / away / psc_* / odds_1x2_* / handicap_home / odds_handicap_*)
- 这些字段一半是 cron 已有的 (date/league/home/away/psc_*), 一半是用户要填的
- 字段名要正确, 否则系统报 422 验证错

---

## 2. 目标体验 (V12 W3 ship 后)

**打开 dashboard → 今日推荐 tab → 看到一个"已识别比赛"列表**:

```
🎯 今日推荐 (cron 识别了 3 场)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

① 法甲: Saint-Étienne vs Nice                          19:00 (Tue)
   模型: λ_h=1.31 λ_a=1.30  →  P(主) 35.8%  P(平) 28.8%  P(客) 35.3%
   Pinnacle: 主胜 2.45 · 平 3.40 · 客胜 2.85    (vig 4.2%)
   
   📊 1X2 / 让球 输入 (输完点 [计算]):
   ┌────────────────────────────────────────────────┐
   │ 不让球    主胜 [    ]  平 [    ]  客胜 [    ]   │
   │ 让球     [   球]  让胜 [    ] 让平 [    ] 让负[]│
   │                              [✓ 计算 EV + Kelly] │
   └────────────────────────────────────────────────┘
   
② 德乙: SpVgg Greuther vs Rot-Weiß Essen                14:30 (Tue)
   模型: λ_h=1.89 λ_a=1.14  →  P(主) 53.8%  P(平) 24.5%  P(客) 21.7%
   ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**填完 SP 之后**, 点 [计算], 同一张卡片**就地展开**显示推荐:

```
① 法甲: Saint-Étienne vs Nice  ✓ 已计算 (19:23 输入)

   ✅ 不下注 (6/6 outcomes 没过 +5% EV 门槛)
   
   最接近的 outcome:
   • 让负 EV = -3.1%  (SP 1.51, 需要 ≥ 1.64)
   • 客胜 EV = -2.8%  (SP 2.75, 需要 ≥ 2.97)
   
   [记录到观测库] [跳过]
```

或者 (如果有 +EV):

```
① 法甲: ...
   
   ⭐ 推荐 1 注:
   ┌─────────────────────────────────────────┐
   │ 让胜 @ 3.40  ←  EV +8.2%  Kelly 1.8%   │
   │ 建议金额: ¥36  (按 ¥1000 bankroll)     │
   └─────────────────────────────────────────┘
   
   [☑ 记录到观测库] [复制下注信息] [跳过]
```

---

## 3. 工程量

| 步骤 | 工时估计 |
|---|---|
| **A. 后端 endpoint** `/api/v4/today-with-predictions` | 1 天 |
| - 读今天的 cron CSV (cron 已经写好) | |
| - 跑 `predict_lambdas` + `score_grid` + `grid_to_1x2` | |
| - 返回每场: λ + P(H/D/A) + Pinnacle SP + match identifiers | |
| **B. 前端: 今日推荐 tab "已识别比赛" 卡片列表** | 1.5 天 |
| - 调 `/today-with-predictions` | |
| - 渲染每场: 模型预测 + 输入 form | |
| - inline 计算 (借鉴 WC 让球 form 的设计) | |
| - 输入校验 + 计算后展开 (借鉴现有 single match tab) | |
| **C. 测试 + 文档** | 0.5 天 |
| **D. SW cache version bump + i18n keys** | 0.5 天 |
| **总计** | **3-4 天** |

---

## 4. 设计细节

### 4.1 后端 endpoint

`GET /api/v4/today-with-predictions?date=YYYY-MM-DD`

返回:
```json
{
  "date": "2026-05-26",
  "n_fixtures": 2,
  "fixtures": [
    {
      "date": "2026-05-26",
      "league": "FRA_LIGUE_1",
      "home_team": "Saint Etienne",
      "away_team": "Nice",
      "psc_home": 2.29, "psc_draw": 3.55, "psc_away": 3.12,
      "psc_over25": 1.79, "psc_under25": 2.07,
      "lambda_home": 1.31,
      "lambda_away": 1.30,
      "p_home_1x2": 0.3582,
      "p_draw_1x2": 0.2884,
      "p_away_1x2": 0.3535,
      "model_type": "catboost",
      "model_cutoff": "2024-08-01"
    },
    ...
  ]
}
```

**Implementation**: 复用现有 `today_recommendations` 逻辑, 但只到 `predict_lambdas` 这一步, **不进 combo engine** (那需要竞彩 SP, 这里还没填).

### 4.2 前端 form

复用 V11 P1-FE Path A++ WC 让球 form 的设计模式:
- `<details>` 折叠 (默认展开 since today tab 是 landing)
- 4 个 input fields per outcome (1X2 主/平/客 + handicap 数字 + handicap 主/平/客 = 7 inputs)
- 点 [计算] → AJAX POST to `/api/v4/recommend/single` (or 现有 endpoint)
- inline 渲染结果 (recommendation card 或 "不下注" 消息)

### 4.3 数据流

```
cron 14:00:    ingest_odds → CSV
cron 15:00:    recommend.py 试图算 → 但 CSV 缺竞彩 SP → 0 recommendations
                                    (这是 OK 的, 我们就要 0)
用户打开 dashboard:
   ↓ GET /today-with-predictions
   读 CSV + predict_lambdas → 返回 λ + P
   ↓ 浏览器渲染列表
用户输入 SP + 点 [计算]:
   ↓ POST /recommend/single 带完整 fixture
   重新跑 single_match (这次 SP 齐全)
   ↓ 返回真实推荐
用户点 [记录到观测库]:
   ↓ POST 设 record_session=true
   session 落 DB
```

### 4.4 Edge cases

| Case | 处理 |
|---|---|
| 今天 0 场 cron 识别 | 显示 "今天无可识别比赛" + 链接到高级 tab 手动输入 |
| 比赛已经开赛 (过了 kickoff) | 灰显 + "已开赛, 不再推荐" |
| 用户输入非法 SP (e.g. -1, 0.5) | 客户端校验 (HTML5 number + min/step) |
| 用户保存 session 后又改 SP | 第二次保存生成新 session_id (不覆盖) |
| 用户切到其他 tab 再回来 | localStorage 保存输入到位 |
| 网络错误 | inline 红字, 输入数据保留 |

---

## 5. 触发条件 (什么时候启动)

**等明天 cron 真实数据起来之后启动 V12 W3**。优先级:

1. **明天 (5-27 14:00 + 15:00)** — 看新 cron 是否真的写 CSV + 落 DB
2. **5-28 至 5-31** — 4 天观察期, 确认 cron 每天稳定
3. **6-1 启动 V12 W3** — 用户已有"输入 SP" 的真实需求, 那时候 UX 改进有 ROI

或者 (更快路径): 用户**今天就开始用现有 dashboard 单关 tab** 手动输入, 体验一下痛点。然后再决定 V12 W3 优先级。

---

## 6. Done Criteria

| 验收项 | 测试 |
|---|---|
| 后端 endpoint `/today-with-predictions` 返回正确 JSON | `tests/v4/test_today_with_predictions.py` |
| Dashboard 渲染卡片列表 (新, V12 W3) | `tests/v4/test_dashboard_today_cards.py` |
| inline 输入 SP → 算 EV → 显示推荐 | Playwright E2E |
| `min_ev=5%` 门槛保护正确 (no-bet on negative EV) | unit + integration |
| 记录到观测库 checkbox 工作 | integration |
| 全套 1508 + N 新测试 | `pytest tests/v4/` |

---

## TL;DR

| 项 | 值 |
|---|---|
| 目标 | 半自动 — cron 预填 + 用户只输 SP |
| 工程量 | 3-4 天 |
| 何时做 | 明天 cron 数据起来后 (5-30 之后) |
| 设计 | 借鉴 V11 post-ship 的 WC 让球 form 模式 |
| 影响范围 | dashboard 今日推荐 tab + 1 新 endpoint |
| 不做的事 | 爬虫 / 全自动 SP 抓取 |
