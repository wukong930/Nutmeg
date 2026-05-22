# Nutmeg 前端设计规范 v2

## 1. 前端设计定位

Nutmeg 的前端不是博彩页面，而是足球预测分析工作台。设计目标：

```text
清晰展示概率
避免误导性承诺
解释模型差异
展示不确定性
支持复杂玩法但不制造混乱
让用户理解预测准确性来自哪里
```

前端设计关键词：

```text
calm
analytical
probabilistic
explainable
risk-aware
```

---

## 2. 信息架构

```text
首页 Dashboard
  ├─ 今日比赛
  ├─ 赛事筛选
  ├─ 冷门提示
  ├─ 串关快捷入口
  └─ 模型状态

比赛详情 Match Detail
  ├─ 比赛头部
  ├─ 胜平负概率
  ├─ 市场对比
  ├─ 让球玩法
  ├─ 比分倾向
  ├─ 冷门分析
  ├─ 关键因素
  ├─ 赔率/盘口走势
  └─ 模型元信息

冷门榜 Upset Radar
  ├─ 热门不胜
  ├─ 热门输盘
  ├─ 平局被低估
  ├─ 弱队受让
  └─ 大比分尾部风险

串关优化器 Parlay Optimizer
  ├─ 自动推荐
  ├─ 用户自选评估
  ├─ 复式展开
  ├─ 预算/关数/风险设置
  └─ 推荐解释

准确性 Accuracy Lab
  ├─ 模型表现
  ├─ 联赛表现
  ├─ 校准曲线
  ├─ 错误类型
  └─ 模型版本

赛事管理 Competition Admin
  ├─ 赛事状态
  ├─ 数据质量
  ├─ Provider 覆盖
  └─ Beta/Production 状态
```

---

## 3. 视觉原则

### 3.1 概率优先

每个结论必须带概率。例如：

```text
推荐：主队不败 68.4%
```

不要写：

```text
主队稳了
```

### 3.2 不确定性显性化

每个预测都显示：

```text
置信度
数据质量
更新时间
模型版本
```

### 3.3 风险表达克制

避免刺激性文案：

```text
禁止：稳胆、必中、包中、稳赚、重仓、梭哈
允许：概率较高、模型优势、风险中等、数据质量较低
```

### 3.4 一致性

同一场比赛所有模块的概率必须一致。前端不能用不同来源计算出互相矛盾的概率。

---

## 4. 设计 Token

### 4.1 颜色语义

| Token | 用途 |
|---|---|
| `color.prob.high` | 高概率 |
| `color.prob.medium` | 中概率 |
| `color.prob.low` | 低概率 |
| `color.risk.low` | 低风险 |
| `color.risk.medium` | 中风险 |
| `color.risk.high` | 高风险 |
| `color.edge.positive` | 模型高于市场 |
| `color.edge.negative` | 模型低于市场 |
| `color.status.beta` | Beta 赛事/模型 |
| `color.status.stale` | 数据过期 |

具体颜色可由设计系统定义，但必须保证色盲友好，不依赖颜色单独传递信息。

### 4.2 字体层级

```text
Page title: 24-32px
Section title: 18-20px
Card title: 16px
Probability number: 22-28px
Body: 14px
Meta: 12px
```

---

## 5. 组件规范

### 5.1 ProbabilityBar

用途：展示 1X2 概率或玩法概率。

Props：

```ts
type ProbabilityBarProps = {
  items: Array<{
    label: string;
    probability: number;
    marketProbability?: number;
    isHighlighted?: boolean;
  }>;
  showMarketComparison?: boolean;
};
```

规则：

- 概率和应接近 100%。
- 若有市场概率，显示差值。
- 差值用百分点表达：`+4.2pp`。

### 5.2 MatchPredictionCard

展示：

```text
比赛信息
开赛时间
胜平负概率
冷门标签
数据质量
模型版本
```

状态：

```text
scheduled
live_locked
finished
evaluated
stale
beta
```

### 5.3 ScoreTopList

展示比分 Top N。

规则：

- 默认 Top 5。
- 不用“预测比分”作为标题，使用“比分倾向”。
- 显示尾部风险入口。

### 5.4 HandicapPanel

Tab：

```text
中国竞彩让球
亚洲让球
欧洲三项让球
```

中国竞彩让球展示：

```text
让胜 / 让平 / 让负
```

亚洲盘展示：

```text
全赢 / 半赢 / 走水 / 半输 / 全输
```

禁止混淆两者。

### 5.5 UpsetBadge

类型：

```text
热门不胜
热门输盘
平局被低估
弱队受让
大比分尾部
```

必须点击后显示解释。

### 5.6 ParlayTicketCard

展示：

```text
组合类型
每场选项
是否复式
注数
总金额
命中概率
EV
ROI
风险等级
推荐解释
规则合法性
```

若组合风险高，必须显示：

```text
该组合命中概率较低，任一单式注失误都会影响返还。
```

### 5.7 AccuracyMetricCard

展示：

```text
Log Loss
Brier Score
Calibration Error
样本数
时间窗口
模型版本
```

避免只展示命中率。

---

## 6. 页面设计

### 6.1 Dashboard

#### 模块

```text
顶部筛选：日期、赛事、模型状态
今日比赛列表
冷门雷达摘要
串关推荐入口
模型健康状态
```

#### 比赛列表字段

```text
时间
赛事
主队 vs 客队
胜平负概率
市场差异最大项
冷门标签
数据质量
```

### 6.2 Match Detail

#### Header

```text
主队 vs 客队
赛事 / 轮次 / 开赛时间
模型版本 / 预测时间 / 数据质量
```

#### 1X2 Section

展示：

```text
模型概率
市场概率
差值
fair odds
```

#### Handicap Section

分 tab 展示，不混用术语。

#### Score Section

展示：

```text
比分 Top 5
竞彩比分映射
胜其它/平其它/负其它
尾部事件
```

#### Upset Section

展示：

```text
冷门类型
冷门方向
概率差
热门脆弱度
触发原因
风险提示
```

#### Explanation Section

解释分组：

```text
模型因素
市场因素
阵容因素
赛程因素
不确定因素
```

### 6.3 Upset Radar

筛选：

```text
日期
赛事
冷门类型
最低概率差
最低数据质量
```

排序：

```text
upset_score
probability_gap
favorite_fragility
risk_level
```

### 6.4 Parlay Optimizer

#### 输入区

```text
预算
单注金额
关数
策略
是否允许复式
玩法范围
赛事范围
风险偏好
```

#### 输出区

展示多个方案：

```text
稳健型
平衡型
价值型
冷门观察型
高波动型
```

每个方案展示：

```text
注数
金额
命中概率
预期返还
EV
ROI
风险等级
解释
```

#### 用户自选评估

用户可以添加：

```text
比赛
玩法
一个或多个选项
```

系统实时显示：

```text
注数变化
金额变化
命中概率变化
EV/ROI 变化
不推荐原因
```

### 6.5 Accuracy Lab

模块：

```text
模型版本选择
时间窗口
联赛筛选
玩法筛选
核心指标
校准曲线
错误类型分布
模型晋级记录
```

---

## 7. 文案规范

### 7.1 推荐表达

使用：

```text
模型认为该方向概率高于市场。
该选项有一定保护价值。
该场存在热门赢不了盘口的风险。
```

避免：

```text
稳赢
稳赚
必红
稳胆
爆杀
梭哈
```

### 7.2 比分表达

使用：

```text
比分倾向
最可能比分组合
尾部比分风险
```

避免：

```text
最终比分就是 2-1
```

### 7.3 串关表达

使用：

```text
组合命中概率
组合风险等级
复式会增加注数和总金额
```

避免：

```text
最佳稳赚串
```

---

## 8. 前端技术结构

```text
apps/web/
  app/
    dashboard/
    fixtures/[fixtureId]/
    upsets/
    parlays/
    accuracy/
    competitions/
  components/
    probability/
    match/
    handicap/
    score/
    upset/
    parlay/
    accuracy/
  lib/
    api.ts
    format.ts
    probability.ts
    schemas.ts
  types/
    api.ts
  tests/
```

### 8.1 API Client

使用 TanStack Query：

```ts
useFixturesQuery(filters)
useFixturePredictionQuery(fixtureId)
useUpsetsQuery(filters)
useParlayRecommendMutation()
useParlayEvaluateMutation()
useAccuracySummaryQuery(filters)
```

### 8.2 Schema 校验

使用 Zod 校验 API 响应。

---

## 9. 无障碍与国际化

### 9.1 无障碍

- 概率条必须有文字百分比。
- 风险等级不能只依赖颜色。
- 图表提供 tooltip 和文本摘要。

### 9.2 国际化

MVP 支持中文，后续英文。

术语映射：

```text
胜平负 = 1X2
让球胜平负 = Handicap 1X2
亚洲让球 = Asian Handicap
串关 = Parlay / Accumulator
复式 = Multiple selections / Combination ticket
```

---

## 10. 前端验收清单

- [ ] 比赛列表可按日期和赛事筛选。
- [ ] 单场页展示胜平负、让球、比分、冷门。
- [ ] 中国竞彩让球与亚洲盘显示不同结构。
- [ ] 比分不显示为唯一确定结果。
- [ ] 串关页支持复式展开。
- [ ] 串关页显示注数、金额、命中概率、EV、ROI。
- [ ] 所有预测显示模型版本和更新时间。
- [ ] Beta/数据质量低时有提示。
- [ ] Accuracy 页面不只展示命中率。
- [ ] 没有“稳赚/必中”等违规文案。

