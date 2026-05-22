# Nutmeg Frontend Design Specification

Version: v2.1  
Document type: Frontend design specification  
Project: Nutmeg  
Primary goal: Improve football match prediction accuracy over time  
Default style direction: Quant Sports Lab  
Default theme: Light-first, dark-mode-ready  
Audience: General football fans + data-oriented users  
Density: Medium-density professional dashboard  
Brand personality: Smart, calm, football-native, probability-first, slightly playful  
Mobile: Mobile-first with desktop power views  
Internationalization: Chinese first, English UI-ready

---

## 1. Design Positioning

Nutmeg is not a traditional football news site, not a betting site, and not a “magic prediction” product.

Nutmeg is a **football prediction intelligence dashboard**. Its interface must help users understand:

1. What the model predicts.
2. How confident the model is.
3. Why the model reached that probability.
4. How the model differs from the market.
5. What risks could make the prediction wrong.
6. How past predictions performed.
7. Whether the system is improving over time.

The frontend should make probability reasoning visible. Professional visual elements should not be decorative; they should explain the model’s reasoning chain.

Recommended product sentence:

> Nutmeg turns football match data into transparent probabilities, market comparisons, upset alerts, score distributions, and parlay risk analysis.

Do not position Nutmeg as:

- A guaranteed winning tool.
- A betting automation product.
- A “sure pick” recommendation app.
- A gambling-style odds board.
- A black-box AI oracle.

---

## 2. Core Visual Philosophy

### 2.1 Probability-first

Every major prediction should be shown as probability, not as a single deterministic call.

Bad:

```text
推荐：主胜
```

Good:

```text
主胜 42.8% · 平局 28.4% · 客胜 28.8%
模型倾向：主队小优，但不确定性较高
```

### 2.2 Traceable reasoning

A user should be able to follow the chain:

```text
Raw Data → Features → Score Grid → Market Resolver → Risk/Parlay Analysis → Explanation
```

This is the main reason to add “professional-looking elements” such as derivation chains, model traces, probability charts, and calibration views.

### 2.3 Accuracy over excitement

Visual emphasis should reward correctness, uncertainty, and transparency.

Avoid:

- Flashing red/green betting signals.
- “必中”, “稳胆”, “绝杀”, “稳赚”.
- Oversized odds or payout numbers.
- Casino-like colors and animations.
- Fake certainty.

Use:

- Probability bands.
- Confidence labels.
- Model version badges.
- Data quality badges.
- Calibration charts.
- Explanation trails.
- Backtest panels.

---

## 3. Recommended Visual Direction

### 3.1 Style name

**Quant Sports Lab**

Visual references in spirit:

- Sports analytics lab.
- Quant dashboard.
- Football tactics board.
- Model monitoring console.
- Clean SaaS product.

The feel should be:

```text
Professional, calm, data-rich, football-aware, not gambling-heavy.
```

### 3.2 Theme strategy

Default:

```text
Light theme
```

Reserved:

```text
Dark professional mode
```

Reason:

- Light mode is easier for general users and Chinese text-heavy pages.
- Dark mode is suitable for expert analysis, live dashboards, and odds/movement monitoring.
- The design system should define tokens for both from day one, even if MVP only ships light mode.

### 3.3 Density

Default page density:

```text
Medium-density professional dashboard
```

Avoid low-density marketing pages as the main product experience. Avoid extremely dense betting-board layouts for the MVP.

---

## 4. Professional Visual Elements

This section defines the visual elements that should make Nutmeg feel professional and trustworthy.

### 4.1 Prediction Derivation Chain

Component name:

```text
PredictionTrace
```

Purpose:

Show how Nutmeg moved from data to prediction.

Recommended visual structure:

```text
Data Snapshot
  ↓
Feature Engine
  ↓
Score Probability Grid
  ↓
Market Resolver
  ↓
Upset / Parlay Analysis
  ↓
User Explanation
```

Compact horizontal version:

```text
Data → Features → Score Grid → Markets → Risk → Explanation
```

Expanded version:

```text
[Data Snapshot]
- Fixture data
- Odds snapshots
- Team form
- Injuries / lineups
- Market liquidity

[Feature Engine]
- Elo / team strength
- Rolling xG
- Rest days
- Home advantage
- League calibration

[Score Grid]
- λ_home
- λ_away
- Top score probabilities
- Tail risk

[Market Resolver]
- 1X2
- Chinese handicap 1X2
- Asian handicap
- Correct score

[Risk Analysis]
- Upset score
- Favorite fragility
- Market gap
- Data quality
```

Design rules:

- Use step chips, not heavy diagrams on every card.
- On match detail pages, show compact trace by default and allow expansion.
- Each step should show status: `ready`, `partial`, `missing`, `stale`, `estimated`.
- Missing data should be visible, not hidden.

Example UI copy:

```text
Prediction Trace
数据快照：完整 · 特征：已生成 · 比分矩阵：已校准 · 玩法解析：完成 · 解释：可用
```

---

### 4.2 Score Probability Heatmap

Component name:

```text
ScoreGridHeatmap
```

Purpose:

Show the model’s underlying score distribution.

Why it matters:

The score grid is the single source from which 1X2, handicap, correct score, upset, and parlay probabilities are derived. Showing it makes the product more credible.

Default compact display:

```text
Top 5 scores:
1-1  11.8%
1-0  10.4%
2-1   9.7%
0-0   8.9%
0-1   7.8%
```

Advanced display:

A grid where rows are home goals and columns are away goals.

```text
        Away 0   Away 1   Away 2   Away 3
Home 0   8.9%     7.8%     3.2%     0.9%
Home 1  10.4%    11.8%     5.1%     1.4%
Home 2   6.8%     9.7%     4.3%     1.2%
Home 3   2.9%     4.1%     2.0%     0.6%
```

Design rules:

- Do not show a huge matrix on mobile by default.
- Use top-score list on mobile and full heatmap behind “Advanced”.
- Highlight the top 3 score cells.
- Show tail mass if max goals are capped.
- Include a tooltip: “比分概率是底层模型输出，不代表单一确定预测。”

Recommended derived summary:

```text
比分结构
- 小比分倾向：中高
- 平局集中：0-0 / 1-1
- 大比分尾部风险：低
```

---

### 4.3 Probability Triptych

Component name:

```text
ProbabilityTriptych
```

Purpose:

Present 1X2 probability clearly.

Default layout:

```text
主胜 42.8% | 平局 28.4% | 客胜 28.8%
```

Use a three-segment probability bar.

Must include:

- Model probability.
- Market probability, if available.
- Difference in percentage points.
- Last updated time.
- Model version.

Example:

```text
模型概率
主胜 42.8%   平局 28.4%   客胜 28.8%

市场去水概率
主胜 40.1%   平局 29.7%   客胜 30.2%

差异
主胜 +2.7pp   平局 -1.3pp   客胜 -1.4pp
```

Design rules:

- Use “pp” for percentage-point difference in expert mode.
- For general users, show “高于市场 2.7 个百分点”.
- Never hide the draw probability.
- Avoid making the largest probability look like a guaranteed result.

---

### 4.4 Market Gap Divergence Chart

Component name:

```text
MarketGapChart
```

Purpose:

Show where the model disagrees with the market.

Example:

```text
主胜   +2.7pp
平局   -1.3pp
客胜   -1.4pp
```

For handicap:

```text
主队 -1 让胜   -4.8pp
让平           +2.1pp
让负           +2.7pp
```

Design rules:

- Use a diverging bar centered at zero.
- Positive gap means model probability is higher than market probability.
- Negative gap means model probability is lower than market probability.
- Add tooltip explaining that market gap is not automatically a betting edge.

Required warning:

```text
市场分歧只表示模型与市场观点不同，不代表结果必然发生。
```

---

### 4.5 Odds / Line Movement Timeline

Component name:

```text
MarketMovementTimeline
```

Purpose:

Show how odds and handicap lines changed over time.

Supported views:

```text
Opening
T-72h
T-24h
T-6h
T-1h
Closing
```

Examples:

```text
Asian Handicap Line
T-72h: 主队 -0.5
T-24h: 主队 -0.75
T-6h:  主队 -1.0
T-1h:  主队 -0.75
```

```text
1X2 Market Probability
主胜: 44% → 47% → 45%
平局: 28% → 27% → 29%
客胜: 28% → 26% → 26%
```

Design rules:

- Use a line chart for probabilities.
- Use stepped labels for handicap line movement.
- Show stale data warning if last snapshot is old.
- Keep this component secondary on general match cards, primary in expert mode.

Professional use:

This is one of the strongest “pro” elements because it shows Nutmeg understands prediction as a time-aware process, not a static pre-match guess.

---

### 4.6 Favorite Fragility Panel

Component name:

```text
FavoriteFragilityPanel
```

Purpose:

Explain why a favorite may be vulnerable.

Example output:

```text
热门脆弱度：72 / 100
冷门类型：热门赢不了盘口

触发因素：
- 主队只赢 1 球概率较高：24.8%
- 平局概率高于市场：+4.1pp
- 盘口从 -1 降到 -0.75
- 主队 4 天前刚踢欧战
- 客队低比分防守能力较好
```

Recommended visualization:

- Primary: score number + label.
- Secondary: contribution bars.
- Optional: small risk matrix.

Avoid using a radar chart as the default. Radar charts look professional but are often harder to read. Contribution bars are more useful.

Good visual:

```text
平局压力        ███████░░░  68
盘口偏深        ██████░░░░  61
轮换风险        ████████░░  75
低比分倾向      ██████░░░░  59
市场高估热门    ███████░░░  70
```

---

### 4.7 Risk Waterfall

Component name:

```text
RiskWaterfall
```

Purpose:

Show how different risk factors adjust the baseline view.

Example:

```text
Baseline favorite strength        61%
Lineup risk                       -3.5pp
Fixture congestion                -2.1pp
Market drift                      -1.6pp
Low-score tendency                -2.8pp
Adjusted favorite win probability 51.0%
```

Use cases:

- Match detail explanation.
- Upset Watch page.
- Parlay leg risk explanation.

Design rules:

- Do not overstate causal certainty.
- Label this as “model contribution estimate”.
- Use positive/negative contribution bars.

---

### 4.8 Parlay Expansion Tree

Component name:

```text
ParlayExpansionTree
```

Purpose:

Make multi-selection parlays understandable.

Example user input:

```text
A: 负 / 平
B: 负
C: 平 / 负
D: 胜
```

Expanded atomic bets:

```text
1. A负 + B负 + C平 + D胜
2. A负 + B负 + C负 + D胜
3. A平 + B负 + C平 + D胜
4. A平 + B负 + C负 + D胜
```

Visual layout:

```text
A: 负 ─┬─ C: 平 ─ D: 胜
       └─ C: 负 ─ D: 胜
A: 平 ─┬─ C: 平 ─ D: 胜
       └─ C: 负 ─ D: 胜
```

Must show:

```text
注数
单注金额
总金额
组合命中概率
预期返还
EV
ROI
风险等级
```

Design rule:

This component is mandatory for multi-selection parlays. Users must see why total stake increases.

---

### 4.9 Parlay Payout Distribution

Component name:

```text
ParlayPayoutDistribution
```

Purpose:

Show outcome distribution instead of only max payout.

Useful buckets:

```text
0 return
Partial return, if applicable
Break-even range
Positive return
Max theoretical return
```

For traditional all-or-nothing parlays, this may be simple. For compound/free-pass or multiple atomic bets, payout distribution becomes more important.

Design rules:

- Do not over-emphasize max payout.
- Show total stake and hit probability near the payout chart.
- Label high-risk parlays clearly.

---

### 4.10 Calibration and Accuracy Charts

Component names:

```text
CalibrationCurve
BrierTrend
LogLossTrend
PredictionBucketChart
```

Purpose:

Show whether Nutmeg is actually becoming more accurate.

These charts belong in:

```text
Accuracy Lab
Model Performance page
Admin / internal dashboard
Optional public transparency panel
```

Recommended charts:

1. Calibration curve.
2. Brier score trend by week.
3. Log loss trend by model version.
4. Prediction bucket reliability.
5. Market comparison by league.
6. Upset Precision@K.
7. Handicap settlement calibration.

Example copy:

```text
当模型给出 60%-70% 主胜概率时，历史实际主胜率为 64.2%。
```

Design rule:

Accuracy charts are not decorative. They are the proof layer of the product.

---

### 4.11 Model Fingerprint

Component name:

```text
ModelFingerprint
```

Purpose:

Show the exact prediction context.

Fields:

```text
Model: poisson_v1.0 / dixon_coles_v1.5 / ensemble_v1
Feature version
Calibration version
Prediction time
Data snapshot time
Odds snapshot time
Competition calibration scope
Data quality score
```

Example:

```text
Model v: poisson_v1.0
Feature v: features_2026_05_06
Calibration v: cal_epl_2026_w18
Prediction: 2026-05-06 18:30 UTC
Data quality: 86/100
```

Design rules:

- Show compact badge on cards.
- Show full details in expanded model panel.
- This should be visible enough for trust, but not dominate general pages.

---

### 4.12 Data Quality Badge

Component name:

```text
DataQualityBadge
```

Purpose:

Communicate prediction reliability constraints.

Statuses:

```text
High
Medium
Low
Partial
Stale
Beta competition
```

Examples:

```text
数据质量：高
赔率快照：T-1h 可用
阵容：预计首发未确认
伤停：部分缺失
赛事模型：Production
```

Design rule:

Low data quality must reduce visual confidence. Do not show an assertive recommendation when data quality is poor.

---

### 4.13 Scenario Toggle / What-if Panel

Component name:

```text
ScenarioPanel
```

Purpose:

Let users understand sensitivity.

Examples:

```text
如果主力前锋缺阵：主胜 42.8% → 38.6%
如果盘口从 -0.75 降到 -0.5：弱队受让价值下降
如果预计首发确认：数据质量从 76 → 88
```

This can be a later-stage feature, but the design should reserve space for it.

---

## 5. Information Architecture

### 5.1 Main navigation

Recommended primary navigation:

```text
Matches
Upset Watch
Parlay Lab
Accuracy Lab
Competitions
Model Notes
```

Chinese labels:

```text
比赛
冷门观察
串关实验室
准确性实验室
赛事
模型说明
```

### 5.2 Page hierarchy

MVP pages:

1. Match list.
2. Match detail.
3. Upset Watch.
4. Parlay Lab.
5. Accuracy Lab.
6. Competition settings / coverage page.

Post-MVP pages:

1. Model version history.
2. Backtest explorer.
3. Data source health.
4. Competition onboarding status.
5. Scenario analysis.
6. Expert score grid page.

---

## 6. Core Page Specifications

## 6.1 Match List Page

Purpose:

Allow users to scan upcoming fixtures and identify interesting matches.

Primary elements:

```text
- Date selector
- Competition filter
- Match card list
- Prediction status filter
- Data quality filter
- Upset risk filter
- Market gap filter
```

Match card must include:

```text
Competition
Kickoff time
Home team
Away team
1X2 probability triptych
Main handicap line
Top score hint
Upset risk badge
Data quality badge
Model version / prediction time
```

Optional expert mode card elements:

```text
Market gap
Odds movement indicator
Favorite fragility score
Line movement mini sparkline
```

Card example:

```text
Premier League · 20:30
Arsenal vs Liverpool

模型概率：主胜 42.8 · 平 28.4 · 客胜 28.8
主盘口：Arsenal -0.25
冷门观察：中
数据质量：高
更新：T-6h · model ensemble_v1
```

Design rules:

- Keep match cards scannable.
- Do not show too many charts on the list page.
- Use small sparklines and badges only.

---

## 6.2 Match Detail Page

Purpose:

Explain a single match deeply.

Recommended sections:

```text
1. Match header
2. Main prediction summary
3. Prediction derivation chain
4. 1X2 probability comparison
5. Handicap markets
6. Correct score / score grid
7. Market movement
8. Upset analysis
9. Key drivers / risk waterfall
10. Model fingerprint
11. Historical similar matches, later-stage
```

Suggested layout desktop:

```text
Left column, 65%:
- Match header
- Main probability panel
- Market resolver panels
- Score grid
- Market movement timeline

Right column, 35%:
- PredictionTrace
- FavoriteFragilityPanel
- DataQualityBadge
- ModelFingerprint
- KeyDrivers
```

Mobile layout:

```text
1. Header
2. Probability summary
3. Tabs: 1X2 / Handicap / Score / Upset / Model
4. Expandable trace
5. Compact charts
```

Important design rule:

Do not hide uncertainty. If prediction is close, say it is close.

Example copy:

```text
模型倾向：主队小优，但三项概率接近。本场不适合表达为单一强结论。
```

---

## 6.3 Upset Watch Page

Purpose:

Identify matches where the favorite may be overestimated or where handicap risk is high.

Primary filters:

```text
Date
Competition
Upset type
Favorite fragility
Market gap
Data quality
```

Upset types:

```text
Favorite fail to win
Favorite loss
Underdog cover
Favorite fail to cover
Low-score trap
Blowout tail risk
```

Card must include:

```text
Match
Favorite
Favorite win probability
Market favorite probability
Probability gap
Favorite fragility score
Upset type
Main triggers
Data quality
```

Example card:

```text
冷门观察：热门赢不了盘口
主队胜率仍最高，但让 -1.5 打穿概率不足。

热门脆弱度：72/100
模型 vs 市场：主队让胜 -6.4pp
关键因素：低比分倾向、盘口偏深、轮换风险
```

Design rule:

Use “观察” instead of “推荐”.

---

## 6.4 Parlay Lab Page

Purpose:

Analyze and optimize 2-leg, 3-leg, 4-leg, and multi-selection parlays.

Primary modes:

```text
System Recommended
User Selected
Budget Optimized
Upset Protection
Value First
Hit Rate First
```

Required inputs:

```text
Pass type: 2x1 / 3x1 / 4x1 / free pass
Unit stake
Budget
Allowed competitions
Allowed markets
Risk preference
Single-selection or multi-selection
```

Required outputs:

```text
Legs
Selected outcomes
Atomic bet count
Total stake
Hit probability
Expected payout
EV
ROI
Risk score
Correlation penalty
Explanation
```

Multi-selection display example:

```text
四串一复式
A: 负 / 平
B: 负
C: 平 / 负
D: 胜

注数：4
单注：2 元
总金额：8 元
组合命中概率：31.6%
预期返还：8.42 元
EV：+0.42 元
ROI：+5.25%
风险等级：中高
```

Mandatory warning copy:

```text
串关会放大波动。任意关键场次错误都可能导致组合失败。
```

Design rule:

The Parlay Lab must show cost expansion clearly. Multi-selection should never look free.

---

## 6.5 Accuracy Lab Page

Purpose:

Show whether Nutmeg is improving.

Sections:

```text
1. Model performance summary
2. Calibration curve
3. Brier score trend
4. Log loss trend
5. Market comparison
6. Upset Precision@K
7. Handicap accuracy
8. Competition-level performance
9. Model version history
10. Error type breakdown
```

Example summary:

```text
Model version: ensemble_v1.2
Evaluation window: last 1,200 matches
Brier score: 0.182
Log loss: 0.944
Calibration: good in 40%-70% buckets, overconfident above 75%
```

Design rule:

This page proves that Nutmeg’s goal is accuracy. It should not be hidden as an admin-only concept forever. A simplified public version can become a trust-building feature.

---

## 7. Component System

### 7.1 Component naming conventions

Use clear domain names:

```text
MatchCard
MatchHeader
ProbabilityTriptych
MarketGapChart
ScoreGridHeatmap
PredictionTrace
FavoriteFragilityPanel
RiskWaterfall
MarketMovementTimeline
HandicapResolverPanel
CorrectScorePanel
ParlayBuilder
ParlayExpansionTree
ParlayEvaluationPanel
DataQualityBadge
ModelFingerprint
CalibrationCurve
BrierTrend
LogLossTrend
```

### 7.2 Probability display components

All probability components must support:

```text
value
label
source: model / market / blended
timestamp
modelVersion
confidence
```

Format:

```text
42.8%
```

Rules:

- Use one decimal place for main probabilities.
- Use two decimals only in expert mode or API views.
- Use whole numbers for risk scores.
- Use “pp” for probability point differences in expert mode.

### 7.3 Badge components

Badges:

```text
ModelVersionBadge
DataQualityBadge
RiskBadge
CompetitionStatusBadge
MarketStatusBadge
CalibrationBadge
BetaBadge
```

Tone:

- Quiet by default.
- Informative, not alarming.
- High-risk badge should be noticeable but not casino-like.

---

## 8. Visual Tokens

### 8.1 Color tokens

Use semantic tokens, not raw colors in components.

Light theme:

```css
:root {
  --bg-primary: #F8FAF8;
  --bg-surface: #FFFFFF;
  --bg-surface-muted: #F1F5F2;
  --text-primary: #17211B;
  --text-secondary: #5C6B61;
  --text-muted: #8A978E;
  --border-subtle: #DDE5DF;

  --brand-primary: #167A4A;
  --brand-primary-strong: #0D5F39;
  --brand-soft: #E4F4EC;

  --info: #2563EB;
  --info-soft: #EAF1FF;

  --warning: #B7791F;
  --warning-soft: #FFF4D8;

  --risk: #B84A4A;
  --risk-soft: #FBEAEA;

  --neutral: #6B7280;
  --neutral-soft: #F3F4F6;
}
```

Dark theme reserved:

```css
[data-theme="dark"] {
  --bg-primary: #0B1110;
  --bg-surface: #111A17;
  --bg-surface-muted: #18231F;
  --text-primary: #ECF4EF;
  --text-secondary: #A8B7AE;
  --text-muted: #718078;
  --border-subtle: #26342E;

  --brand-primary: #32D17D;
  --brand-primary-strong: #5BE89A;
  --brand-soft: #123B28;

  --info: #60A5FA;
  --info-soft: #10233D;

  --warning: #FBBF24;
  --warning-soft: #382B0B;

  --risk: #F87171;
  --risk-soft: #3A1616;

  --neutral: #9CA3AF;
  --neutral-soft: #1F2937;
}
```

### 8.2 Color usage rules

```text
Green: brand, selected states, positive data health
Blue: model/system information
Amber: uncertainty, watch, market divergence
Red: risk, not loss stimulation
Gray: secondary context
```

Do not use red and green as pure win/loss signals without labels, because this can look like gambling UX and may hurt accessibility.

### 8.3 Typography

Recommended fonts:

```text
Chinese: system-ui, PingFang SC, Microsoft YaHei, Noto Sans SC
English/numbers: Inter, SF Pro, system-ui
```

Use tabular numbers for probabilities, odds, and scores:

```css
font-variant-numeric: tabular-nums;
```

Type scale:

```text
Display: 32 / 40
Page title: 24 / 32
Section title: 18 / 26
Card title: 16 / 24
Body: 14 / 22
Small: 12 / 18
Micro: 11 / 16
```

Probability number sizes:

```text
Hero probability: 28-36px
Card probability: 16-20px
Table probability: 13-14px
```

### 8.4 Spacing

Use 4px base scale:

```text
4, 8, 12, 16, 20, 24, 32, 40, 48
```

Cards:

```text
Desktop padding: 20-24px
Mobile padding: 14-16px
Card radius: 14-18px
Panel radius: 20px
```

### 8.5 Shadows and borders

Use subtle borders rather than heavy shadows.

```css
--shadow-card: 0 8px 24px rgba(15, 23, 18, 0.06);
--shadow-floating: 0 16px 40px rgba(15, 23, 18, 0.12);
```

Professional dashboards should feel precise, not glossy.

---

## 9. Chart Guidelines

### 9.1 Recommended chart library

For React/Next.js implementation, recommended choices:

```text
Recharts: simple MVP charts
visx: more customized professional charts
ECharts: powerful but heavier
D3: only for advanced custom visualizations
```

MVP recommendation:

```text
Use Recharts for speed, keep components abstract enough to replace later.
```

### 9.2 Chart types and use cases

| Chart | Use case | Priority |
|---|---|---|
| Segmented probability bar | 1X2 probabilities | MVP |
| Diverging bar | model vs market gap | MVP |
| Heatmap | score grid | MVP / expert |
| Sparkline | odds movement mini view | MVP |
| Line chart | odds/probability movement | MVP |
| Contribution bars | risk drivers | MVP |
| Waterfall | adjusted probability explanation | Post-MVP |
| Calibration curve | model reliability | MVP for Accuracy Lab |
| Brier/log-loss trend | accuracy improvement | MVP for Accuracy Lab |
| Tree/expanded list | parlay atomic expansion | MVP |
| Distribution chart | parlay payout distribution | Post-MVP |

### 9.3 Chart rules

- Every chart must have a clear title.
- Every chart must show units.
- Every chart must include timestamp or evaluation window if time-sensitive.
- Avoid 3D charts.
- Avoid decorative radar charts as primary analytics.
- Avoid pie charts for 1X2; use segmented bars instead.
- Avoid chart colors that imply certainty.

---

## 10. Market and Rule Display Standards

### 10.1 1X2

Display:

```text
主胜 / 平局 / 客胜
```

English-ready:

```text
Home / Draw / Away
```

### 10.2 Chinese lottery handicap 1X2

Display:

```text
主队 -1：让胜 / 让平 / 让负
主队 +1：让胜 / 让平 / 让负
```

Must explain:

```text
中国竞彩让球胜平负是三结果玩法，和亚洲让球不同。
```

### 10.3 Asian handicap

Display possible settlements:

```text
全赢
半赢
走水
半输
全输
```

For line examples:

```text
主队 -0.75
全赢：赢 2 球或以上
半赢：赢 1 球
全输：平或输
```

### 10.4 Correct score

Default display:

```text
Top 5 scores
```

Advanced:

```text
Score grid heatmap
Chinese correct score categories, if relevant
Other home win / other draw / other away win
```

### 10.5 Parlay

Always show:

```text
Pass type
Selected legs
Atomic bet count
Unit stake
Total stake
Hit probability
Expected payout
EV
ROI
Risk level
```

Do not show only expected payout.

---

## 11. Microcopy Rules

### 11.1 Approved language

Use:

```text
模型倾向
概率较高
风险中等
冷门观察
热门脆弱度
市场分歧
数据质量
预测时间
模型版本
历史校准表现
```

### 11.2 Avoid language

Avoid:

```text
稳赚
必中
稳胆
包红
锁定
神单
无脑上
必出冷门
```

### 11.3 Risk copy

Every parlay page should include:

```text
串关会放大波动。组合命中概率通常显著低于单场概率。
```

Every upset page should include:

```text
冷门观察表示模型识别到热门方向风险，不代表冷门一定发生。
```

Every score page should include:

```text
精确比分属于低概率事件，Top 5 比分也不代表确定结果。
```

---

## 12. Responsive Design

### 12.1 Breakpoints

```text
Mobile: 0-639px
Tablet: 640-1023px
Desktop: 1024-1439px
Wide: 1440px+
```

### 12.2 Mobile priorities

Mobile should show:

```text
1. Match identity
2. Main 1X2 probabilities
3. Data quality and prediction time
4. Key risk badge
5. Tabs for deeper views
```

Hide behind expansion:

```text
Full score grid
Full derivation chain
Long market movement chart
Model fingerprint details
```

### 12.3 Desktop priorities

Desktop should support analytical layout:

```text
Multi-column match detail
Persistent side model panel
Charts visible without excessive scrolling
Parlay builder side-by-side with evaluation
```

---

## 13. Frontend Technical Architecture

Recommended stack:

```text
Next.js
TypeScript
React
Tailwind CSS or CSS Modules with design tokens
Recharts for MVP charts
Zod for API response validation
TanStack Query for data fetching
```

Recommended folder structure:

```text
frontend/
  app/
    matches/
    matches/[fixtureId]/
    upset-watch/
    parlay-lab/
    accuracy-lab/
    competitions/
  components/
    domain/
      match/
      probability/
      market/
      score-grid/
      parlay/
      accuracy/
      model/
    ui/
      badge/
      card/
      tabs/
      tooltip/
      table/
  lib/
    api/
    formatting/
    charts/
    probability/
    tokens/
  styles/
    tokens.css
    globals.css
```

### 13.1 API validation

Frontend should validate important API payloads using schemas.

Example:

```ts
const PredictionSnapshotSchema = z.object({
  fixtureId: z.string(),
  predictionTime: z.string(),
  modelVersion: z.string(),
  featureVersion: z.string().optional(),
  calibrationVersion: z.string().optional(),
  probabilities: z.object({
    home: z.number(),
    draw: z.number(),
    away: z.number(),
  }),
});
```

### 13.2 Formatting helpers

Must centralize:

```text
formatProbability
formatProbabilityPointDiff
formatOdds
formatStake
formatModelVersion
formatKickoffTime
formatRiskLevel
```

Avoid formatting probabilities ad hoc in components.

---

## 14. Example Data Contracts

### 14.1 Match prediction summary

```json
{
  "fixtureId": "fixture_123",
  "competition": "Premier League",
  "kickoffTimeUtc": "2026-05-06T19:30:00Z",
  "homeTeam": {
    "id": "team_ars",
    "name": "Arsenal"
  },
  "awayTeam": {
    "id": "team_liv",
    "name": "Liverpool"
  },
  "prediction": {
    "predictionTimeUtc": "2026-05-06T12:00:00Z",
    "modelVersion": "poisson_v1.0",
    "featureVersion": "features_2026_05_06",
    "calibrationVersion": "cal_epl_v1",
    "dataQuality": {
      "score": 86,
      "label": "High"
    },
    "oneXTwo": {
      "home": 0.428,
      "draw": 0.284,
      "away": 0.288
    },
    "marketOneXTwo": {
      "home": 0.401,
      "draw": 0.297,
      "away": 0.302
    },
    "topScores": [
      { "score": "1-1", "probability": 0.118 },
      { "score": "1-0", "probability": 0.104 },
      { "score": "2-1", "probability": 0.097 }
    ],
    "upset": {
      "type": "favorite_fail_to_cover",
      "score": 72,
      "label": "Medium High"
    }
  }
}
```

### 14.2 Parlay evaluation

```json
{
  "parlayId": "parlay_456",
  "passType": "4x1",
  "unitStake": 2,
  "atomicBetCount": 4,
  "totalStake": 8,
  "hitProbability": 0.316,
  "expectedPayout": 8.42,
  "ev": 0.42,
  "roi": 0.0525,
  "riskLevel": "medium_high",
  "legs": [
    {
      "fixtureId": "A",
      "selectedOutcomes": ["away_win", "draw"]
    },
    {
      "fixtureId": "B",
      "selectedOutcomes": ["away_win"]
    },
    {
      "fixtureId": "C",
      "selectedOutcomes": ["draw", "away_win"]
    },
    {
      "fixtureId": "D",
      "selectedOutcomes": ["home_win"]
    }
  ],
  "atomicBets": [
    ["A:away_win", "B:away_win", "C:draw", "D:home_win"],
    ["A:away_win", "B:away_win", "C:away_win", "D:home_win"],
    ["A:draw", "B:away_win", "C:draw", "D:home_win"],
    ["A:draw", "B:away_win", "C:away_win", "D:home_win"]
  ]
}
```

---

## 15. Accessibility

Requirements:

- Charts must not rely only on color.
- Probability bars must include text labels.
- Risk badges must include text, not just color.
- All interactive chart elements should have accessible labels.
- Use sufficient contrast in light and dark themes.
- Support keyboard navigation in tabs, filters, dropdowns, and parlay builder.
- Tooltips must also be accessible through focus, not only hover.

---

## 16. Empty, Loading, and Error States

### 16.1 Missing prediction

```text
本场预测尚未生成。
原因：缺少必要数据或模型任务未完成。
```

### 16.2 Low data quality

```text
本场数据质量较低，概率仅供观察。
缺失项：预计首发、最新伤停、盘口快照。
```

### 16.3 Stale odds

```text
盘口数据可能已过期，最后快照时间：T-18h。
```

### 16.4 Beta competition

```text
该赛事模型处于 Beta 阶段，历史样本较少，置信度较低。
```

---

## 17. Implementation Milestones for Codex

### FE-01: Design tokens and layout shell

Implement:

```text
- Light theme tokens
- Dark theme token placeholders
- App shell
- Navigation
- Card, Badge, Tabs, Tooltip, Table primitives
```

Acceptance:

```text
- Theme tokens are centralized
- No raw hardcoded colors in domain components
- Layout works on mobile and desktop
```

### FE-02: Match list MVP

Implement:

```text
- MatchCard
- ProbabilityTriptych compact
- DataQualityBadge
- RiskBadge
- Competition/date filters
```

### FE-03: Match detail MVP

Implement:

```text
- MatchHeader
- ProbabilityTriptych full
- PredictionTrace compact
- TopScores panel
- ModelFingerprint compact
```

### FE-04: Market visualization

Implement:

```text
- MarketGapChart
- HandicapResolverPanel
- ScoreGridHeatmap compact + advanced
- MarketMovementTimeline basic
```

### FE-05: Upset Watch

Implement:

```text
- Upset list
- FavoriteFragilityPanel
- Risk contribution bars
- Upset explanation drawer
```

### FE-06: Parlay Lab MVP

Implement:

```text
- ParlayBuilder
- Multi-selection leg UI
- ParlayExpansionTree
- ParlayEvaluationPanel
- Stake and atomic bet display
```

### FE-07: Accuracy Lab MVP

Implement:

```text
- CalibrationCurve
- BrierTrend
- LogLossTrend
- Model version selector
- Evaluation window display
```

### FE-08: Copy and compliance pass

Implement:

```text
- Remove forbidden language
- Add risk notices
- Add model timestamp and version everywhere
- Add data quality messaging
```

---

## 18. MVP Frontend Acceptance Checklist

The MVP frontend is acceptable only when:

```text
[ ] Match list shows probabilities, not deterministic picks.
[ ] Match detail shows 1X2, handicap, score, model version, and prediction time.
[ ] Correct score is shown as Top N probabilities, not one fixed score.
[ ] Chinese handicap and Asian handicap are visually distinguished.
[ ] Upset Watch says “observation/risk”, not guaranteed upset.
[ ] Parlay Lab shows atomic bet count and total stake for multi-selection.
[ ] Parlay Lab shows hit probability, EV, ROI, and risk level.
[ ] Accuracy Lab shows at least one calibration or backtest metric.
[ ] Low-quality or stale data is visible to users.
[ ] No guaranteed-profit or betting automation language appears.
[ ] UI works on mobile.
[ ] Design tokens are centralized.
[ ] Charts have labels and accessible fallbacks.
```

---

## 19. Final Design Recommendation

Adopt the default direction:

```text
Main style: A+B hybrid
Default theme: light
Reserved theme: dark
Audience: general fans + data users
Density: medium professional
Brand: smart, slightly playful, quant-football feel
Mobile-first: yes
English-ready: yes
```

Add professional elements, but prioritize explanatory value:

```text
Must-have professional elements:
- Prediction derivation chain
- Score probability heatmap
- Market gap chart
- Odds / line movement timeline
- Favorite fragility panel
- Parlay expansion tree
- Model fingerprint
- Calibration charts

Use carefully:
- Waterfall charts
- Scenario analysis
- Payout distribution
- Full expert score grids

Avoid as primary elements:
- Decorative radar charts
- Casino-like odds boards
- Flashy win/loss animations
- Overconfident recommendation banners
```

The strongest visual identity for Nutmeg is not a flashy football graphic. It is the feeling that every number is traceable, every conclusion is probabilistic, and every mistake becomes part of the system’s learning loop.

