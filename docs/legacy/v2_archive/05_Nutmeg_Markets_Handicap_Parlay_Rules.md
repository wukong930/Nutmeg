# Nutmeg 玩法规则、让球与串关组合优化文档 v2

## 1. 设计原则

所有玩法概率必须从同一个比分概率矩阵派生：

```text
score_probability_grid[home_goals][away_goals]
```

Market Resolver 的职责是：

```text
读取比分矩阵
按照玩法规则计算概率
输出 fair odds
输出结算规则
```

它不训练模型，不修改概率。

---

## 2. 普通胜平负 1X2

设：

```text
x = 主队进球
y = 客队进球
P[x,y] = 比分概率
```

则：

```text
P(home_win) = sum(P[x,y] where x > y)
P(draw)     = sum(P[x,y] where x == y)
P(away_win) = sum(P[x,y] where x < y)
```

---

## 3. 中国竞彩让球胜平负

中国竞彩让球胜平负是三结果玩法：

```text
让球胜
让球平
让球负
```

设主队让球数为 `h`：

```text
adjusted_home_goals = home_goals + h
```

例如：

```text
主队 -1: h = -1
主队 +1: h = +1
```

规则：

```text
adjusted_home_goals > away_goals → 让球胜
adjusted_home_goals = away_goals → 让球平
adjusted_home_goals < away_goals → 让球负
```

公式：

```text
P(handicap_home_win) = sum(P[x,y] where x + h > y)
P(handicap_draw)     = sum(P[x,y] where x + h == y)
P(handicap_away_win) = sum(P[x,y] where x + h < y)
```

示例：主队 -1

```text
2-0 → 让球胜
1-0 → 让球平
2-1 → 让球平
0-0 → 让球负
1-1 → 让球负
```

---

## 4. 亚洲让球 Asian Handicap

亚洲让球是两方向玩法，但可能出现：

```text
全赢
半赢
走水
半输
全输
```

设主队盘口 `line`：

```text
adjusted_margin = home_goals - away_goals + line
```

### 4.1 整数盘

例如主队 -1：

```text
adjusted_margin > 0 → 主队赢盘
adjusted_margin = 0 → 走水
adjusted_margin < 0 → 主队输盘
```

### 4.2 半球盘

例如主队 -0.5：

```text
adjusted_margin > 0 → 主队赢盘
adjusted_margin < 0 → 主队输盘
无走水
```

### 4.3 四分之一盘

拆成两个半注：

```text
-0.25 = 0 和 -0.5
-0.75 = -0.5 和 -1
+0.25 = 0 和 +0.5
+0.75 = +0.5 和 +1
```

Market Resolver 输出：

```text
full_win_prob
half_win_prob
push_prob
half_loss_prob
full_loss_prob
expected_return_prob
```

示例：主队 -0.75

```text
赢 2 球或以上 → 全赢
赢 1 球 → 半赢
平或输 → 全输
```

---

## 5. 欧洲三项让球 European Handicap

三项让球与中国竞彩让球胜平负类似：

```text
Home handicap win
Handicap draw
Away handicap win
```

但不同平台的盘口表达可能不同。必须通过 provider mapping 标准化。

---

## 6. 比分玩法

### 6.1 精确比分

输出 Top N：

```text
1-1: 11.8%
1-0: 10.4%
2-1: 9.7%
0-0: 8.2%
0-1: 7.8%
```

### 6.2 中国竞彩比分选项

中国竞彩比分是有限结果 + 其它：

```text
主胜固定比分
平局固定比分
主负固定比分
胜其它
平其它
负其它
```

实现方式：

```text
if score in listed_options:
  map to exact option
else if home_goals > away_goals:
  map to 胜其它
else if home_goals == away_goals:
  map to 平其它
else:
  map to 负其它
```

### 6.3 比分展示原则

不展示“唯一预测比分”。展示：

```text
比分 Top 5
比分结构
大比分风险
尾部事件概率
```

---

## 7. 总进球与双方进球

### 7.1 总进球

```text
P(total_goals = k) = sum(P[x,y] where x + y = k)
P(over_2_5) = sum(P[x,y] where x + y > 2.5)
P(under_2_5) = sum(P[x,y] where x + y < 2.5)
```

### 7.2 双方进球 BTTS

```text
P(BTTS_yes) = sum(P[x,y] where x > 0 and y > 0)
P(BTTS_no)  = 1 - P(BTTS_yes)
```

---

## 8. 冷门规则

### 8.1 冷门类型

```text
favorite_fail_to_win       热门不胜
favorite_loss              热门输球
underdog_cover             弱队受让赢盘
favorite_fail_to_cover     热门赢球但输盘
draw_overlooked            平局被低估
low_score_trap             强队小胜/小比分陷阱
blowout_tail_risk          大比分尾部风险
```

### 8.2 热门识别

默认市场概率最高的一方为热门：

```text
favorite = argmax(market_fair_prob_1x2)
```

若无市场数据，则使用模型概率最高一方，但冷门置信度降低。

### 8.3 市场差异

```text
edge_i = model_prob_i - market_prob_i
```

冷门不是只看 KL 散度，而要看方向：

```text
市场高估热门胜率
模型提高平局概率
模型提高弱队不败概率
模型提高弱队受让概率
```

### 8.4 Favorite Fragility Score

```text
favorite_fragility =
  0.25 * favorite_not_win_prob
+ 0.20 * favorite_one_goal_win_prob
+ 0.20 * favorite_fail_cover_prob
+ 0.15 * draw_prob
+ 0.10 * low_score_prob
+ 0.10 * lineup_schedule_risk
```

### 8.5 Upset Alert 输出

```json
{
  "fixture_id": "123",
  "upset_type": "favorite_fail_to_cover",
  "target_outcome": "away +1.5",
  "model_probability": 0.641,
  "market_probability": 0.582,
  "probability_gap": 0.059,
  "favorite_fragility_score": 0.74,
  "risk_level": "medium_high",
  "explanations": [
    "热门主胜概率较高，但大胜概率不足",
    "模型认为赢 1 球概率偏高",
    "盘口较深，弱队受让方向有保护价值"
  ]
}
```

---

## 9. 串关基础概念

### 9.1 单式串关

每场只选一个结果。

示例四串一：

```text
A: 负
B: 负
C: 平
D: 胜
```

注数：

```text
1
```

### 9.2 复式串关

每场可选多个结果。

示例四串一：

```text
A: 负 / 平
B: 负
C: 平 / 负
D: 胜
```

注数：

```text
2 × 1 × 2 × 1 = 4 注
```

展开为：

```text
A负 + B负 + C平 + D胜
A负 + B负 + C负 + D胜
A平 + B负 + C平 + D胜
A平 + B负 + C负 + D胜
```

总金额：

```text
total_stake = atomic_bet_count × unit_stake × multiplier
```

---

## 10. 串关概率与收益计算

### 10.1 单个 atomic bet

设每腿概率和赔率为：

```text
p_i
o_i
```

独立近似：

```text
p_atomic = product(p_i)
odds_atomic = product(o_i)
expected_payout = stake * p_atomic * odds_atomic
EV = expected_payout - stake
ROI = EV / stake
```

### 10.2 复式组合

```text
Expected Payout = sum(expected_payout_atomic_bet)
Total Stake = atomic_bet_count × unit_stake × multiplier
EV = Expected Payout - Total Stake
ROI = EV / Total Stake
```

### 10.3 命中概率

复式命中概率是“至少一个 atomic bet 命中”的概率。若每场多个结果互斥，且不同比赛近似独立，则：

```text
P_hit = product(sum(selected_outcome_probs_per_fixture))
```

例：

```text
A: 负/平
B: 负
C: 平/负
D: 胜

P_hit = (P_A负 + P_A平) × P_B负 × (P_C平 + P_C负) × P_D胜
```

### 10.4 相关性惩罚

普通串关默认不同 fixture 近似独立，但要考虑：

```text
同一联赛同一轮相关性
天气/赛程系统性风险
同一模型误差来源
同一球队不能重复
同一场比赛不同玩法禁止或特殊处理
```

组合概率调整：

```text
p_combo_adjusted = p_combo * (1 - correlation_penalty)
```

MVP 可先使用规则型惩罚，后续学习。

---

## 11. 中国竞彩过关规则引擎

### 11.1 需要支持

```text
2串1
3串1
4串1
5串1
6串1
7串1
8串1
自由过关
混合过关
复式选项
```

### 11.2 规则约束

Rule Engine 必须支持配置：

```text
同一场比赛不同玩法不能进入同一过关组合
足球和篮球不能混串，Nutmeg MVP 只做足球
不同玩法混合时，最高关数取其中上限最低的玩法
比分玩法最高关数较低
总进球玩法最高关数低于胜平负/让球胜平负
胜平负/让球胜平负最高可支持更多关
```

具体限制以接入地区和官方规则配置为准，不能硬编码死值。

示例配置：

```yaml
cn_sporttery:
  same_fixture_multiple_markets_allowed: false
  sports_mixing_allowed: false
  max_legs_by_market:
    win_draw_loss: 8
    handicap_win_draw_loss: 8
    total_goals: 6
    correct_score: 4
    half_full_time: 4
  mixed_pass_max_rule: min_of_selected_markets
```

---

## 12. Parlay Optimizer

### 12.1 输入

```json
{
  "date_range": ["2026-05-06", "2026-05-07"],
  "competitions": ["EPL", "LA_LIGA"],
  "pass_types": ["2x1", "3x1", "4x1"],
  "unit_stake": 2,
  "max_budget": 20,
  "risk_preference": "balanced",
  "allow_multiple_outcomes_per_fixture": true,
  "allowed_markets": ["1x2", "cn_handicap_1x2"],
  "exclude_beta_competitions": true
}
```

### 12.2 输出

```json
{
  "recommendation_id": "rec_001",
  "strategy": "balanced",
  "pass_type": "4x1",
  "is_multiple": true,
  "legs": [
    {"fixture_id": "A", "market": "1x2", "outcomes": ["away_win", "draw"]},
    {"fixture_id": "B", "market": "1x2", "outcomes": ["away_win"]},
    {"fixture_id": "C", "market": "1x2", "outcomes": ["draw", "away_win"]},
    {"fixture_id": "D", "market": "1x2", "outcomes": ["home_win"]}
  ],
  "atomic_bet_count": 4,
  "unit_stake": 2,
  "total_stake": 8,
  "hit_probability": 0.316,
  "expected_payout": 8.42,
  "ev": 0.42,
  "roi": 0.0525,
  "risk_level": "medium_high",
  "explanations": [
    "A 场不建议单选负，平局保护有正边际价值",
    "C 场平/负均高于市场隐含概率",
    "B、D 两场置信度较高，保持单选"
  ]
}
```

### 12.3 候选项过滤

单场选项进入串关候选池前必须满足：

```text
data_quality >= threshold
model_confidence >= threshold
probability >= min_probability_by_strategy
model_edge >= min_edge_by_strategy
odds_available = true
market_rule_valid = true
not stale
```

### 12.4 多选边际判断

增加一个选项时必须计算：

```text
ΔHit Probability
ΔAtomic Bet Count
ΔTotal Stake
ΔExpected Payout
ΔEV
ΔROI
ΔRisk
```

只有当新增选项提升组合质量，才推荐多选。

### 12.5 推荐策略

#### 命中率优先

```text
高概率
低风险
允许适度复式保护
控制预算
```

#### 价值优先

```text
高模型优势
高 EV/ROI
不为了保险盲目加选项
```

#### 冷门保护

```text
热门脆弱
平局/弱队受让方向
风险明确标注
```

#### 成本受限最优

```text
在预算内最大化综合评分
```

### 12.6 Parlay Score

```text
parlay_score =
  0.30 * normalized_ev
+ 0.25 * normalized_hit_probability
+ 0.20 * average_model_edge
- 0.10 * correlation_penalty
+ 0.10 * data_quality
+ 0.05 * odds_stability
```

---

## 13. 测试要求

### 13.1 Market Resolver 测试

必须覆盖：

```text
1X2 概率和为 1
竞彩让球 -1/+1 规则
亚洲盘 0/-0.25/-0.5/-0.75/-1/+0.25
比分其它映射
大小球
BTTS
```

### 13.2 Parlay Optimizer 测试

必须覆盖：

```text
单式二串一展开
复式四串一展开
注数计算
总金额计算
EV 计算
ROI 计算
预算限制
同场多玩法禁止
玩法关数限制
相关性惩罚
新增选项边际判断
```

---

## 14. 禁止事项

```text
禁止自动下注
禁止保证收益表达
禁止在无数据质量情况下推荐串关
禁止同场不同玩法无建模直接相乘
禁止把赔率高当作价值高
禁止把命中率高当作长期准确
```

