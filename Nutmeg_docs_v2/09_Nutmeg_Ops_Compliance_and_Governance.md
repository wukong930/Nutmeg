# Nutmeg 运维、合规与模型治理文档 v2

## 1. 文档目标

Nutmeg 涉及比赛预测、赔率、串关分析，因此必须从第一版就设计：

```text
数据授权
合规边界
模型治理
线上监控
错误回滚
安全策略
风险提示
```

本项目的核心原则：

> Nutmeg 是概率预测与分析工具，不是自动投注系统，不承诺收益。

---

## 2. 合规边界

### 2.1 允许做的事

```text
展示比赛概率预测
展示模型与市场差异
展示玩法概率
展示冷门风险
展示串关组合评估
展示历史回测表现
解释模型依据
```

### 2.2 禁止做的事

```text
自动下注
代客投注
资金托管
承诺盈利
使用“稳赚/必中/包中”文案
面向未成年人推广
绕过数据源条款抓取数据
提供规避监管的投注执行方案
```

### 2.3 风险提示

所有串关、赔率、金额相关页面必须显示：

```text
本工具仅提供概率分析与研究参考，不保证结果，不构成投注建议。足球比赛存在高不确定性，请理性使用。
```

---

## 3. 数据授权与来源治理

### 3.1 Provider Registry

维护：

```text
provider_name
allowed_use
commercial_use_allowed
rate_limit
historical_data_allowed
redistribution_allowed
terms_url
last_reviewed_at
owner
```

### 3.2 数据源使用策略

```text
优先使用官方 API / 授权 API
不使用违反 ToS 的爬虫
保留原始 provider 响应
记录每个数据点的 source
对不同 provider 冲突做标记
```

### 3.3 数据保留

```text
raw payload: 按合同允许范围保存
normalized snapshots: 长期保存用于回测
user-generated parlay evaluations: 可按用户隐私策略保存/删除
logs: 按安全策略保存
```

---

## 4. 模型治理

### 4.1 Model Registry

每个模型版本必须记录：

```text
model_version
model_family
training_data_range
feature_version
calibration_version
hyperparameters
metrics
artifact_uri
status
created_at
activated_at
```

### 4.2 模型状态

```text
experimental
candidate
shadow
canary
active
retired
rolled_back
```

### 4.3 上线门槛

新模型不能因为某一个指标提升就上线。至少检查：

```text
overall log loss
overall brier score
calibration error
by-competition performance
by-market performance
upset precision@K
handicap settlement performance
parlay simulation performance
sample size
```

### 4.4 回滚策略

触发条件：

```text
线上指标快速恶化
核心联赛概率异常
比分矩阵归一化错误
数据源异常导致大范围预测错误
API 错误率超过阈值
```

回滚步骤：

```text
1. 将 active_model_version 指向上一稳定版本
2. 暂停 candidate 发布
3. 标记异常预测
4. 生成 incident report
```

---

## 5. 线上监控

### 5.1 数据监控

指标：

```text
fixture_sync_success_rate
odds_snapshot_freshness
lineup_snapshot_freshness
provider_error_rate
provider_latency
missing_odds_rate
missing_result_rate
stale_prediction_count
```

### 5.2 模型监控

指标：

```text
prediction_count
probability_sum_error
score_grid_negative_probability_count
fallback_model_usage_rate
average_uncertainty
data_quality_distribution
calibration_drift
post_match_log_loss_rolling
post_match_brier_rolling
```

### 5.3 串关监控

指标：

```text
recommendation_count
average_atomic_bets
average_total_stake_displayed
rule_invalid_count
high_risk_recommendation_ratio
parlay_simulated_roi
leg_failure_distribution
```

### 5.4 前端监控

```text
page_load_time
api_error_rate
component_error_boundary_count
user_action_dropoff
```

---

## 6. 告警策略

### P0

```text
错误概率展示
比分矩阵产生负概率
所有预测失效
数据库不可用
误展示自动投注/保证收益文案
```

### P1

```text
主要数据源失败
预测快照过期
模型 fallback 使用率过高
赔率快照缺失严重
```

### P2

```text
单个赛事数据质量下降
部分页面图表异常
非核心 provider 延迟
```

---

## 7. 安全策略

### 7.1 API 安全

```text
rate limiting
auth for admin endpoints
input validation
SQL injection prevention
CORS allowlist
secrets in environment manager
```

### 7.2 数据安全

```text
provider API keys 不进仓库
日志不打印 secret
用户数据最小化
备份加密
```

### 7.3 LLM 安全

LLM 输入可能来自网页和新闻。必须防止 prompt injection：

```text
把外部文本当作数据，不当作指令
LLM 输出必须经过 schema validation
LLM 不允许写入最终概率
LLM 不允许触发交易/投注动作
```

---

## 8. 数据质量与降级

### 8.1 数据质量低时

如果：

```text
data_quality_score < 50
```

则：

```text
不进入串关推荐
前端显示低质量提示
可显示基础概率但降低置信度
```

### 8.2 数据过期时

如果赔率或阵容超过新鲜度阈值：

```text
stale: true
```

前端显示：

```text
部分数据未及时更新，预测仅供参考。
```

### 8.3 Provider 冲突

不同 provider 对赛程/赛果/赔率有冲突时：

```text
记录 conflict_event
使用 trusted provider priority
降低 data_quality_score
```

---

## 9. 用户与内容安全

### 9.1 用户年龄与风险

如果未来开放公开产品，应考虑：

```text
年龄声明
风险提示
限制未成年人导向内容
避免赌博诱导设计
```

### 9.2 文案审核

禁用词：

```text
稳赚
必中
包中
稳胆
梭哈
重仓
提款
暴富
```

替代表达：

```text
概率较高
模型优势
风险较高
数据质量不足
不确定性较大
```

---

## 10. Incident Report 模板

```text
事件时间：
影响范围：
触发告警：
根因：
用户影响：
临时处理：
永久修复：
是否影响历史预测评估：
是否需要模型回滚：
负责人：
```

---

## 11. 合规验收清单

- [ ] 不实现自动下注。
- [ ] 不使用保证收益文案。
- [ ] 所有金额/串关页面有风险提示。
- [ ] 所有数据源有授权记录。
- [ ] 不违反 provider ToS。
- [ ] LLM 不直接输出最终概率。
- [ ] 模型版本可追踪。
- [ ] 模型可回滚。
- [ ] 数据质量低时不推荐串关。
- [ ] API 密钥不入库不入仓库。

