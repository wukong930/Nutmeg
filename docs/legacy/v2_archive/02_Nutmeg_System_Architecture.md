# Nutmeg 系统架构设计 v2

## 1. 架构目标

Nutmeg 的架构目标不是单次预测，而是长期准确性提升。系统必须支持：

```text
多赛事接入
多数据源快照
比分矩阵建模
玩法概率派生
冷门识别
串关组合优化
赛后错误学习
模型版本治理
前端可解释展示
```

架构关键词：

```text
competition-agnostic
snapshot-first
score-grid-first
model-versioned
market-resolved
feedback-loop-enabled
```

---

## 2. 总体架构

```text
外部数据源
  ├─ 赛程/赛果 Provider
  ├─ 技术统计/xG Provider
  ├─ 赔率/盘口 Provider
  ├─ 伤停/阵容 Provider
  ├─ Prediction Market Provider
  └─ 新闻/发布会/文本源
        ↓
Data Ingestion Services
        ↓
Raw Data Lake / Object Storage
        ↓
Normalized PostgreSQL + TimescaleDB
        ↓
Feature Store / Feature Snapshots
        ↓
Modeling Services
  ├─ Elo Baseline
  ├─ Poisson Baseline
  ├─ Dixon-Coles v1.5
  ├─ xG Rolling Model
  ├─ ML Ensemble
  └─ Calibration Layer
        ↓
Score Probability Grid
        ↓
Market Resolver
  ├─ 1X2
  ├─ CN Handicap 1X2
  ├─ Asian Handicap
  ├─ Correct Score
  ├─ Totals
  └─ BTTS
        ↓
Risk & Optimizer Services
  ├─ Upset Detector
  ├─ Favorite Fragility
  ├─ Blowout Tail Risk
  └─ Parlay Optimizer
        ↓
Prediction API
        ↓
Next.js Frontend / Admin / Reports
        ↓
Accuracy Learning Loop
  ├─ Post-match Evaluator
  ├─ Error Classifier
  ├─ Calibration Updater
  ├─ Retraining Pipeline
  ├─ Model Comparator
  └─ Promotion Gate
```

---

## 3. 服务分层

### 3.1 Data Ingestion Layer

职责：

```text
从外部 provider 拉取数据
保存原始响应
标准化字段
建立 provider_id 映射
生成快照
检测数据缺失和冲突
```

模块：

```text
services/ingestion/
  providers/
    football_data_org.py
    api_football.py
    sportmonks.py
    the_odds_api.py
    betfair.py
    polymarket.py
    openfootball.py
  normalizers/
    fixtures.py
    teams.py
    odds.py
    lineups.py
    stats.py
  quality/
    completeness_checker.py
    conflict_detector.py
    freshness_checker.py
```

### 3.2 Raw Data Layer

所有 provider 响应必须先保存原始 JSON，避免未来字段解释变更后无法复盘。

```text
raw_provider_payloads
- payload_id
- provider
- endpoint
- request_url_hash
- response_json
- fetched_at
- entity_type
- entity_id_hint
```

### 3.3 Normalized Data Layer

标准化后写入：

```text
competitions
seasons
teams
fixtures
results
team_match_stats
player_availability_snapshots
lineup_snapshots
odds_snapshots
market_snapshots
```

### 3.4 Feature Layer

职责：

```text
生成赛前特征
确保 as-of-time 正确
保存 feature snapshot
防止赛后数据泄漏
```

特征必须带时间戳：

```text
feature_time_utc
```

预测只能使用 `feature_time_utc <= prediction_time_utc` 的数据。

### 3.5 Modeling Layer

职责：

```text
训练模型
生成 score_probability_grid
输出模型元信息
写入 prediction_snapshot
```

模块：

```text
services/modeling/
  elo/
  poisson/
  dixon_coles/
  xg_model/
  ensemble/
  calibration/
  scoring/
  registry/
```

### 3.6 Market Resolver Layer

职责：

```text
从比分矩阵派生玩法概率
解析盘口规则
计算 fair odds
生成 market_predictions
```

重点：玩法解析器不能调用模型重新预测。它只消费比分矩阵。

### 3.7 Parlay Optimizer Layer

职责：

```text
生成候选单场选项
过滤低质量选项
展开复式串关
计算注数和成本
计算组合概率和 EV
应用规则引擎
输出推荐解释
```

### 3.8 Accuracy Learning Loop

职责：

```text
赛后评估
错误分类
校准更新
模型再训练
模型版本对比
晋级/回滚
```

该层是 Nutmeg “越用越强”的核心。

---

## 4. 核心数据流

### 4.1 赛前预测流

```text
1. 拉取 fixture、team、odds、lineup、injury、stats
2. 保存 raw payload
3. 标准化写入 normalized tables
4. 生成 feature_snapshot
5. 模型生成 score_probability_grid
6. Market Resolver 派生玩法概率
7. Upset Detector 生成冷门风险
8. Parlay Optimizer 生成组合推荐
9. 写入 prediction_snapshots
10. 前端通过 API 展示
```

### 4.2 赛后学习流

```text
1. 拉取最终赛果和赛后技术统计
2. 写入 results 和 post_match_stats
3. Post-match Evaluator 对比预测与结果
4. 计算 Log Loss / Brier / calibration bucket
5. Error Classifier 打错误标签
6. 写入 model_evaluation_events
7. Weekly Training 重新训练候选模型
8. Walk-forward 回测
9. Model Comparator 比较新旧模型
10. Promotion Gate 决定是否上线
```

### 4.3 新赛事接入流

```text
1. 新增 competition_config.yaml
2. 检查 provider coverage
3. 建立 provider mapping
4. 回填历史数据
5. 数据完整性校验
6. 训练/校准 league-specific 参数
7. Beta 上线
8. 观察线上表现
9. 达标后 Production
```

---

## 5. 模块边界

### 5.1 模型不处理玩法规则

模型只输出：

```text
score_probability_grid
lambda_home
lambda_away
model_metadata
```

玩法由 Market Resolver 处理。

### 5.2 前端不计算核心概率

前端只展示 API 返回的概率，不在浏览器里重新计算核心玩法概率。前端可以做轻量格式化，不做结算逻辑。

### 5.3 LLM 不输出最终概率

LLM 只输出结构化上下文特征和解释文本。最终概率必须来自模型与校准层。

### 5.4 串关不改变单场概率

Parlay Optimizer 消费单场概率，不反向修改单场预测。

---

## 6. 部署架构

### 6.1 MVP 部署

```text
Frontend: Next.js on Vercel
API: FastAPI on Render / Railway / Fly.io / AWS ECS
Database: PostgreSQL + TimescaleDB
Object Storage: S3 / R2
Jobs: GitHub Actions Cron / Cloud Scheduler + worker
Cache: Redis
Model Artifacts: S3/R2 + MLflow optional
```

### 6.2 Production 部署

```text
API Gateway
FastAPI services
Worker pool
PostgreSQL primary + read replica
TimescaleDB for snapshots
S3/R2 raw payload storage
Redis cache
MLflow Tracking/Registry
Prometheus/Grafana
Sentry
CI/CD pipeline
```

---

## 7. 任务调度

### 7.1 常规任务

| 任务 | 频率 | 说明 |
|---|---:|---|
| fixture_sync | 每 6 小时 | 同步赛程变动 |
| odds_snapshot_sync | T-7d/T-3d/T-24h/T-6h/T-1h/临场 | 保存赔率和盘口快照 |
| injury_lineup_sync | 每 6 小时，赛前 24h 每小时 | 同步伤停与预计首发 |
| pre_match_prediction | 每次重要数据更新后 | 生成预测快照 |
| result_sync | 比赛结束后 | 同步赛果 |
| post_match_evaluation | 赛果确认后 | 计算错误与指标 |
| weekly_training | 每周 | 训练候选模型 |
| monthly_model_review | 每月 | 模型治理和晋级评审 |

### 7.2 赛前时间点

建议固定保存：

```text
T-7d
T-3d
T-24h
T-6h
T-1h
T-15m
closing
```

---

## 8. 技术栈建议

### 8.1 后端

```text
Python 3.12+
FastAPI
SQLAlchemy / SQLModel
Pydantic v2
PostgreSQL
TimescaleDB
Redis
Celery / Dramatiq / RQ
pandas / polars
numpy / scipy
scikit-learn
xgboost / lightgbm optional
MLflow optional but recommended
```

### 8.2 前端

```text
Next.js
React
TypeScript
Tailwind CSS
shadcn/ui optional
TanStack Query
Recharts / ECharts
Zod
```

### 8.3 测试

```text
pytest
pytest-asyncio
hypothesis for market resolver property tests
Playwright for frontend e2e
```

---

## 9. 可靠性设计

### 9.1 数据源失败

策略：

```text
primary provider failed → fallback provider
fallback failed → use latest valid snapshot and mark stale
stale too old → disable prediction or downgrade confidence
```

### 9.2 模型失败

策略：

```text
ensemble failed → Dixon-Coles fallback
Dixon-Coles failed → Poisson fallback
Poisson failed → market-implied probability fallback
```

### 9.3 规则解析失败

策略：

```text
不展示该玩法
记录 error_event
禁止串关使用该选项
```

---

## 10. 关键架构决策 ADR

### ADR-001: 使用比分矩阵作为唯一玩法概率源

理由：保证胜平负、让球、比分、大小球逻辑一致。

### ADR-002: 保存预测快照而不是只保存最新预测

理由：支持回测、错误分析、模型治理、避免数据泄漏。

### ADR-003: 新赛事配置化接入

理由：未来扩展日职、韩职、荷甲、欧战、国家队赛事时，不改核心系统。

### ADR-004: LLM 不直接预测概率

理由：LLM 概率不稳定、难校准、难回测。LLM 只做文本抽取和解释。

### ADR-005: 串关必须通过规则引擎

理由：不同玩法、不同地域、不同关数限制复杂，不能写死在前端。

---

## 11. 架构验收清单

- [ ] 所有预测有 `model_version`。
- [ ] 所有预测有 `prediction_time_utc`。
- [ ] 所有特征有 `feature_time_utc`。
- [ ] 所有赔率有 `snapshot_time_utc`。
- [ ] 比分矩阵概率和接近 1。
- [ ] 玩法概率只由比分矩阵派生。
- [ ] 串关组合可以展开为 atomic bets。
- [ ] 赛后可计算 Log Loss 和 Brier Score。
- [ ] 新赛事可通过配置接入。
- [ ] 模型可回滚。

