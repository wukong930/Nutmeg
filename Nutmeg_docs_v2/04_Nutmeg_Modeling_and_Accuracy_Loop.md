# Nutmeg 模型设计与 Accuracy Learning Loop v2

## 1. 总原则

Nutmeg 的建模核心是：

> **先生成比分概率矩阵，再派生所有玩法；先记录每次预测，再从错误中学习；先校准概率，再谈推荐。**

模型不能只输出“主胜/平/客胜”。它必须输出：

```text
score_probability_grid
lambda_home
lambda_away
model_version
calibration_version
feature_version
uncertainty
explanation_inputs
```

---

## 2. 模型路线图

### 2.1 Model v0: Market Baseline

用途：强基准。

```text
从赔率转换为隐含概率
去除 overround
生成 market-implied 1X2 probability
作为模型对照
```

公式：

```text
raw_p_i = 1 / decimal_odds_i
overround = sum(raw_p_i)
fair_p_i = raw_p_i / overround
```

### 2.2 Model v1: Poisson Score Baseline

用途：MVP 起步。

```text
估计主队期望进球 lambda_home
估计客队期望进球 lambda_away
假设主客进球独立 Poisson
生成比分矩阵
```

```text
P(X=i, Y=j) = Pois(i; lambda_home) * Pois(j; lambda_away)
```

优点：

```text
简单
可解释
容易测试
能派生全部玩法
```

缺点：

```text
低比分相关性处理不足
极端比分尾部可能低估
不同联赛校准不足
```

### 2.3 Model v1.5: Dixon-Coles

用途：正式利用 Dixon-Coles 思想。

核心改进：

```text
球队 attack strength
球队 defense strength
主场优势
时间衰减
低比分相关性修正
```

模型结构：

```text
lambda_home = exp(mu + home_advantage + attack_home - defense_away + context_features)
lambda_away = exp(mu + attack_away - defense_home + context_features)
```

基础比分概率：

```text
P_base(x, y) = Pois(x; lambda_home) * Pois(y; lambda_away)
```

Dixon-Coles 低比分修正：

```text
P_dc(x, y) = tau(x, y, lambda_home, lambda_away, rho) * P_base(x, y)
```

常见 tau 形式：

```text
if x == 0 and y == 0: tau = 1 - lambda_home * lambda_away * rho
if x == 0 and y == 1: tau = 1 + lambda_home * rho
if x == 1 and y == 0: tau = 1 + lambda_away * rho
if x == 1 and y == 1: tau = 1 - rho
else: tau = 1
```

实现时必须：

```text
对 tau 做数值安全检查
保证概率非负
最终矩阵归一化
通过 regression test
```

时间衰减：

```text
weight_match = exp(-xi * days_since_match)
```

优化目标：

```text
minimize negative weighted log likelihood
```

### 2.4 Model v2: xG Rolling Model

用途：引入质量更高的攻防状态。

特征：

```text
rolling_xg_for
rolling_xg_against
npxG
xG differential
shots_on_target
box_entries
set_piece_xg
recent_form_decay
```

输出：

```text
lambda_home_adjustment
lambda_away_adjustment
```

### 2.5 Model v3: ML Ensemble

候选模型：

```text
LightGBM / XGBoost
Logistic regression / multinomial regression
Random forest only as baseline, not necessarily主力
Bayesian hierarchical model optional
```

推荐输出方式：

```text
预测 lambda_home / lambda_away
或预测 goal_diff_distribution / total_goals_distribution
再映射为 score grid
```

不建议直接输出唯一分类。

### 2.6 Calibration Layer

概率必须校准：

```text
temperature scaling
isotonic regression
Platt scaling for binary derived markets
Dirichlet calibration for 1X2 optional
league-specific calibration
market-specific calibration
```

校准对象：

```text
1X2
handicap outcomes
draw probability
score bucket
total goals
upset probability
```

---

## 3. 比分概率矩阵

### 3.1 矩阵定义

```text
score_probability_grid[x][y] = P(home_goals=x, away_goals=y)
```

默认 `max_goals = 8`。

需要保存：

```text
grid_json
tail_mass
lambda_home
lambda_away
model_version
prediction_time
```

### 3.2 长尾处理

普通 Poisson 容易低估 5-0、6-1、7-1 等极端比分。因此引入：

```text
Blowout / Chaos Tail Module
```

混合模型：

```text
P_final(score) =
  (1 - chaos_prob) * P_normal(score)
+ chaos_prob * P_chaos(score)
```

`chaos_prob` 由以下因素估计：

```text
实力差距
防线关键球员缺阵
门将不稳定
高压淘汰赛
强队进攻效率
弱队必须压上
红牌风险
近期防守崩盘记录
```

输出尾部指标：

```text
home_win_by_3plus
away_win_by_3plus
any_team_4plus_goals
blowout_tail_risk
```

### 3.3 7:1 这类比分如何处理

Nutmeg 不应声称能稳定赛前预测德国 7:1 巴西这种精确比分。正确目标是：

```text
识别某一方方向有价值
识别热门或弱队的崩盘风险
识别大比分尾部风险高于均值
临场时快速更新比分尾部分布
```

赛前精确比分 7:1 通常属于极低概率长尾事件。产品展示应是：

```text
异常比分风险：高/中/低
3+ 球大胜概率
4+ 球极端比分概率
```

而不是：

```text
预测比分：7-1
```

---

## 4. 特征设计

### 4.1 球队强度特征

```text
club_elo
attack_strength
defense_strength
league_strength
promoted_team_adjustment
recent_form_decay
home_advantage
away_travel_distance
```

### 4.2 状态特征

```text
last_5_points
last_5_goal_diff
last_5_xg_diff
rest_days
matches_last_14_days
european_match_recently
cup_rotation_risk
```

### 4.3 阵容特征

```text
starting_xi_strength
expected_lineup_confidence
key_player_absence_score
defender_absence_score
goalkeeper_absence_score
striker_absence_score
bench_dropoff_score
```

### 4.4 市场特征

```text
opening_prob_1x2
current_prob_1x2
closing_prob_1x2 if available and prediction_time is closing
odds_movement
line_movement
bookmaker_disagreement
exchange_liquidity
prediction_market_probability
market_delay_signal
```

### 4.5 语义特征

由 LLM 抽取但要结构化：

```text
is_derby
relegation_pressure
title_race_pressure
european_qualification_pressure
rotation_hint
manager_change_recently
morale_signal
press_conference_injury_hint
```

LLM 输出必须包含：

```text
source
confidence
evidence_text_short
extracted_at
```

---

## 5. 系统记忆设计

Nutmeg 的“记忆”不是聊天记忆，而是数据和模型记忆。

### 5.1 Prediction Memory

每次预测必须保存：

```text
prediction_snapshot_id
fixture_id
prediction_time_utc
model_version
feature_version
calibration_version
p_home
p_draw
p_away
score_grid_id
market_predictions_json
upset_scores_json
parlay_candidates_json
input_snapshot_refs
```

### 5.2 Feature Memory

```text
feature_snapshot_id
fixture_id
feature_time_utc
features_json
source_snapshot_refs
feature_version
```

### 5.3 Error Memory

赛后写入：

```text
prediction_snapshot_id
actual_home_goals
actual_away_goals
log_loss
brier_score
score_rank_of_actual_result
market_comparison
error_tags
created_at
```

### 5.4 Calibration Memory

保存：

```text
calibration_bucket
predicted_probability_range
actual_frequency
sample_size
league
market_type
model_version
```

---

## 6. Accuracy Learning Loop

### 6.1 闭环定义

```text
预测 → 记录 → 赛后评估 → 错误归因 → 再训练 → 回测 → 校准 → 模型晋级/回滚
```

### 6.2 Post-match Evaluator

职责：

```text
读取 prediction_snapshot
读取最终赛果
计算玩法结算
计算评分指标
写入 evaluation_events
```

指标：

```text
1X2 log loss
1X2 Brier score
score log loss
score top-n rank
handicap settlement calibration
upset hit/miss
parlay leg result
```

### 6.3 Error Classifier

错误标签：

```text
favorite_overestimated
underdog_underestimated
draw_underestimated
goals_overestimated
goals_underestimated
home_advantage_overestimated
lineup_miss
injury_miss
market_move_ignored
low_score_correlation_miss
blowout_tail_underestimated
league_calibration_drift
parlay_correlation_underestimated
```

### 6.4 Calibration Updater

每周或每 N 场更新：

```text
按联赛
按玩法
按概率区间
按模型版本
```

校准报告：

```text
如果预测 60%-70% 主胜的比赛实际只赢 55%，说明主胜高估
如果平局 20%-25% 区间实际 31%，说明平局低估
```

### 6.5 Weekly Retraining

步骤：

```text
1. 冻结训练数据窗口
2. 生成训练特征 as-of match kickoff
3. 训练 candidate models
4. Walk-forward backtest
5. 概率校准
6. 与 active model 对比
7. 写入 model_candidate_report
```

### 6.6 Promotion Gate

新模型上线必须满足：

```text
overall log loss 不恶化
Brier score 不恶化
至少一个核心玩法显著改善
校准曲线不恶化
冷门 precision@K 不明显下降
让球市场不明显下降
低样本联赛不异常漂移
```

若满足：

```text
candidate → shadow → canary → active
```

否则保留为实验版本。

### 6.7 Rollback

触发条件：

```text
线上 log loss 超过阈值
数据源异常导致预测异常
校准显著漂移
核心 API 错误率过高
```

回滚到上一稳定模型版本。

---

## 7. 回测设计

### 7.1 Walk-forward Backtest

禁止随机切分。

```text
train: 2021-2023
validate: 2023-2024
predict: 2024-2025
advance window
repeat
```

### 7.2 As-of-time 回测

每个样本必须指定预测时间：

```text
T-24h backtest
T-6h backtest
T-1h backtest
closing backtest
```

不同时间点不能混用数据。

### 7.3 指标

```text
Log Loss
Brier Score
Expected Calibration Error
Reliability Diagram
Sharpness
Closing Odds Comparison
CLV if odds available
Score Top-3/Top-5 Hit Rate
Handicap Settlement Accuracy
Upset Precision@K
Parlay Portfolio ROI Simulation
```

---

## 8. 冷门模型

### 8.1 冷门不是一个事件

拆分：

```text
favorite_fail_to_win
favorite_loss
underdog_cover
favorite_fail_to_cover
draw_overlooked
low_score_trap
blowout_tail_risk
```

### 8.2 Favorite Fragility Score

```text
favorite_fragility =
  w1 * favorite_not_win_prob
+ w2 * favorite_one_goal_win_prob
+ w3 * favorite_fail_cover_prob
+ w4 * draw_prob
+ w5 * low_score_prob
+ w6 * favorite_defensive_instability
+ w7 * market_overpricing_signal
```

### 8.3 Upset Score

```text
upset_score =
  35% model_market_gap
+ 25% favorite_fragility
+ 15% odds_line_movement
+ 15% lineup_schedule_shock
+ 10% style_low_score_signal
```

权重先人工设定，后续通过历史数据学习。

---

## 9. 模型输出契约

```json
{
  "fixture_id": "123",
  "prediction_time_utc": "2026-05-06T12:00:00Z",
  "model_version": "dc-v1.5.3",
  "calibration_version": "cal-2026w18",
  "lambda_home": 1.42,
  "lambda_away": 1.11,
  "score_grid": [[0.07, 0.08], [0.10, 0.11]],
  "tail_mass": 0.006,
  "p_home": 0.432,
  "p_draw": 0.279,
  "p_away": 0.289,
  "uncertainty": "medium",
  "data_quality_score": 82,
  "model_notes": {
    "primary_model": "dixon_coles",
    "fallback_used": false
  }
}
```

---

## 10. 实现优先级

### Phase 1

```text
Market baseline
Poisson baseline
Score grid
Market resolver
Basic backtest
Prediction snapshots
```

### Phase 2

```text
Dixon-Coles v1.5
Time decay
League-specific calibration
Error classifier
Accuracy dashboard
```

### Phase 3

```text
xG model
LLM semantic feature extraction
Blowout tail module
Parlay learning loop
Model promotion gate
```

---

## 11. 模型验收清单

- [ ] 比分矩阵归一化。
- [ ] 低比分修正不产生负概率。
- [ ] 玩法概率由矩阵派生。
- [ ] 回测使用 walk-forward。
- [ ] 回测使用 as-of-time 特征。
- [ ] 每个模型有版本号。
- [ ] 每个模型有训练数据范围。
- [ ] 每次预测有快照。
- [ ] 每场赛后有评估记录。
- [ ] 新模型上线前有对比报告。
- [ ] 模型可回滚。

