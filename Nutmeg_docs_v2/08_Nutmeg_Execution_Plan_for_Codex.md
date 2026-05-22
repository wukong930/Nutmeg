# Nutmeg 项目执行开发文档 v2

## 1. 开发总目标

实现一个可运行的 Nutmeg MVP：

```text
可以导入比赛数据
可以生成比分矩阵
可以派生胜平负/让球/比分概率
可以生成冷门提示
可以生成二串一/三串一/四串一和复式串关评估
可以记录预测快照
可以赛后评估模型表现
可以通过前端查看结果
```

---

## 2. 推荐开发顺序

```text
Phase 0: 仓库初始化与基础设施
Phase 1: 数据库与领域模型
Phase 2: 数据接入模拟器与标准化
Phase 3: Poisson/Dixon-Coles 模型 MVP
Phase 4: Market Resolver
Phase 5: Parlay Optimizer
Phase 6: Accuracy Learning Loop MVP
Phase 7: API
Phase 8: Frontend
Phase 9: 测试、文档、上线准备
Phase 10: 数据源生产化与模型迭代
```

---

## 3. Phase 0：仓库初始化

### T0.1 创建 Monorepo

目标结构：

```text
nutmeg/
  apps/web
  apps/api
  services
  packages/shared
  db/migrations
  tests
  docs
```

验收：

- `docker-compose up` 能启动 PostgreSQL、Redis、API。
- `pnpm dev` 或 `npm run dev` 能启动前端。
- `pytest` 能跑空测试。

### T0.2 配置工具链

后端：

```text
Python 3.12
FastAPI
SQLAlchemy
Pydantic
pytest
ruff
mypy optional
```

前端：

```text
Next.js
TypeScript
Tailwind
TanStack Query
Zod
Playwright
```

---

## 4. Phase 1：数据库与领域模型

### T1.1 实现核心表 migration

基于 `06_Nutmeg_Database_and_API_Spec.md`。

优先实现：

```text
competitions
seasons
teams
fixtures
results
odds_snapshots
feature_snapshots
model_versions
score_probability_grids
prediction_snapshots
market_predictions
upset_alerts
parlay_recommendations
parlay_legs
parlay_atomic_bets
prediction_evaluations
```

验收：

- migration 成功。
- FK 正确。
- 关键索引存在。
- seed 数据可插入。

### T1.2 实现 Pydantic Domain Models

```text
Competition
Team
Fixture
OddsSnapshot
FeatureSnapshot
PredictionSnapshot
ScoreGrid
MarketPrediction
ParlayRecommendation
```

---

## 5. Phase 2：数据接入模拟器

MVP 先不要依赖真实 API。先实现本地 mock provider，确保系统逻辑可跑。

### T2.1 Mock Fixture Provider

输出：

```text
赛事
球队
赛程
赛果
```

### T2.2 Mock Odds Provider

输出：

```text
1X2 odds
CN handicap odds
Asian handicap odds
snapshot_time
```

### T2.3 Normalizer

把 provider 数据标准化写入数据库。

验收：

- 能导入至少 20 场模拟比赛。
- 能导入至少 3 个赔率快照时间点。

---

## 6. Phase 3：模型 MVP

### T3.1 Poisson Score Model

输入：

```text
home_strength
away_strength
home_advantage
league_goal_baseline
```

输出：

```text
lambda_home
lambda_away
score_grid
```

验收：

- score grid 概率和在 `[0.999, 1.001]`。
- 支持 max_goals=8。
- 保存 `score_probability_grids`。

### T3.2 Dixon-Coles v1.5 Skeleton

实现：

```text
attack/defense parameters
home advantage
time decay placeholder
rho low-score adjustment
```

MVP 可以使用简化拟合，但接口要完整。

验收：

- 0-0、1-0、0-1、1-1 概率被 tau 修正。
- 修正后概率非负。
- 矩阵归一化。
- 有单元测试覆盖。

### T3.3 Prediction Snapshot Writer

每次预测写入：

```text
score_probability_grids
prediction_snapshots
```

---

## 7. Phase 4：Market Resolver

### T4.1 1X2 Resolver

从 score grid 计算主胜、平、客胜。

### T4.2 CN Handicap 1X2 Resolver

支持：

```text
h = -3 到 +3
```

### T4.3 Asian Handicap Resolver

支持：

```text
0
±0.25
±0.5
±0.75
±1
±1.25
±1.5
±1.75
±2
```

输出：

```text
full_win
half_win
push
half_loss
full_loss
```

### T4.4 Correct Score Resolver

输出：

```text
score_top_5
listed_score_options
胜其它/平其它/负其它
```

验收：

- 所有玩法概率来自同一个 score grid。
- 测试覆盖典型比分矩阵。

---

## 8. Phase 5：Parlay Optimizer

### T5.1 Candidate Generator

从 market_predictions 生成候选项。

过滤条件：

```text
data_quality
probability
model_edge
odds_available
market_valid
```

### T5.2 Atomic Bet Expander

输入复式：

```text
A: 负/平
B: 负
C: 平/负
D: 胜
```

输出 4 个 atomic bets。

### T5.3 Cost Calculator

计算：

```text
atomic_bet_count
total_stake
max_payout
expected_payout
EV
ROI
hit_probability
```

### T5.4 Rule Engine

实现配置：

```text
same_fixture_multiple_markets_allowed
max_legs_by_market
mixed_pass_max_rule
max_budget
```

### T5.5 Recommendation Ranker

实现策略：

```text
hit_rate_first
value_first
upset_protection
budget_optimized
```

验收：

- 复式注数正确。
- 预算限制有效。
- 同场多玩法限制有效。
- 输出解释文本。

---

## 9. Phase 6：Accuracy Learning Loop MVP

### T6.1 Post-match Evaluator

输入：

```text
prediction_snapshot
result
```

输出：

```text
log_loss
brier_score
actual_score_probability
score_rank
```

### T6.2 Error Classifier

实现规则型错误标签：

```text
favorite_overestimated
draw_underestimated
underdog_underestimated
goals_overestimated
goals_underestimated
handicap_miss
```

### T6.3 Backtest Runner

支持：

```text
时间窗口
联赛筛选
模型版本筛选
```

### T6.4 Accuracy Summary API

输出：

```text
log_loss
brier_score
ece
sample_size
by_competition
by_market
```

验收：

- 比赛结束后可以生成 evaluation。
- Accuracy 页面有数据可显示。

---

## 10. Phase 7：API

实现：

```text
GET /fixtures
GET /fixtures/{fixture_id}/prediction
GET /fixtures/{fixture_id}/score-grid
GET /upsets
POST /parlays/recommend
POST /parlays/evaluate
GET /accuracy/summary
GET /competitions
```

验收：

- OpenAPI 文档可访问。
- Pydantic schema 校验。
- 错误状态清楚。

---

## 11. Phase 8：前端

Phase 8 必须同时遵循：

```text
07_Nutmeg_Frontend_Design_Spec.md
Nutmeg_Frontend_Design_Spec.md
```

其中 `Nutmeg_Frontend_Design_Spec.md` 是前端 v2.1 详细设计规范，补充了 Quant Sports Lab 视觉方向、专业图表组件、FE-01 至 FE-08 实施里程碑，以及 MVP 前端验收清单。后续所有前端开发和 UI 验收必须将该文档列为主要参考。

### T8.1 Dashboard

- 比赛列表。
- 筛选。
- 预测卡片。

### T8.2 Match Detail

- 胜平负。
- 让球。
- 比分。
- 冷门。
- 市场对比。

### T8.3 Upset Radar

- 冷门榜。
- 冷门类型筛选。

### T8.4 Parlay Optimizer

- 自动推荐。
- 用户自选评估。
- 复式展开。
- 注数/金额/EV/ROI。

### T8.5 Accuracy Lab

- 模型指标。
- 联赛分层。
- 错误类型。

验收：

- 页面可用。
- 概率显示一致。
- 无误导性文案。
- 与 `Nutmeg_Frontend_Design_Spec.md` 的 MVP Frontend Acceptance Checklist 对齐。

补充前端实施顺序：

```text
FE-01: Design tokens and layout shell
FE-02: Match list MVP
FE-03: Match detail MVP
FE-04: Market visualization
FE-05: Upset Watch
FE-06: Parlay Lab MVP
FE-07: Accuracy Lab MVP
FE-08: Copy and compliance pass
```

---

## 12. Phase 9：测试与上线准备

### 12.1 单元测试

覆盖：

```text
score grid
market resolver
asian handicap settlement
cn handicap settlement
correct score mapping
parlay expansion
ev calculation
rule engine
post-match evaluator
```

### 12.2 集成测试

测试完整流：

```text
导入比赛 → 生成预测 → 派生玩法 → 生成串关 → 写入结果 → 评估模型
```

### 12.3 E2E 测试

Playwright：

```text
打开首页
进入比赛详情
生成串关推荐
查看 Accuracy
```

---

## 13. Phase 10：生产数据源与模型迭代

### T10.1 接入 football-data.org

用途：基础赛程/赛果。

### T10.2 接入 The Odds API / SportMonks Odds

用途：赔率和盘口快照。

### T10.3 接入 SportMonks Lineups / Injuries

用途：阵容与伤停。

### T10.4 Weekly Training Pipeline

实现定期训练、回测、校准、模型晋级候选。

---

## 14. Codex 任务模板

每个任务给 Codex 时使用：

```text
任务：实现 [模块名]
参考文档：[文档文件名]
输入：[数据结构/API]
输出：[数据结构/API]
约束：
- 不要实现自动下注
- 所有概率必须可追溯到 prediction_snapshot
- 所有玩法概率必须从 score_grid 派生
- 添加单元测试
验收：
- pytest 通过
- 类型检查通过
- 示例数据可运行
```

---

## 15. 里程碑

### Milestone 1: 可运行预测链路

```text
mock data → poisson score grid → 1X2/让球/比分 → API → 前端展示
```

### Milestone 2: 串关与冷门

```text
upset detector → parlay optimizer → 复式展开 → 前端展示
```

### Milestone 3: 记忆与学习

```text
prediction snapshots → results → evaluation → accuracy dashboard
```

### Milestone 4: 生产数据源

```text
真实 provider 接入 → 数据质量 → 联赛配置 → Beta 上线
```

### Milestone 5: Dixon-Coles 与校准

```text
DC v1.5 → 回测 → calibration → model governance
```

---

## 16. Definition of Done

一个功能完成必须满足：

```text
代码实现
单元测试
API schema
错误处理
日志
文档更新
无误导性文案
可追溯 prediction/model version
```
