# Nutmeg 数据源与赛事接入文档 v2

## 1. 设计目标

Nutmeg 不应该只服务世界杯和五大联赛，而应该支持长期扩展：

```text
五大联赛
荷甲、葡超、英冠等欧洲联赛
日本 J 联赛
韩国 K 联赛
欧冠、欧罗巴杯、欧协联
欧洲杯、世界杯、亚洲杯、美洲杯
国内杯赛
未来更多联赛和杯赛
```

因此数据设计必须满足：

```text
provider-agnostic
competition-agnostic
time-snapshot-based
quality-aware
model-calibration-by-competition
```

---

## 2. 数据源分层

### 2.1 基础赛程/赛果数据

用途：

```text
赛事
赛季
球队
赛程
赛果
积分榜
阶段
场地
```

候选源：

| 数据源 | 角色 | 使用建议 |
|---|---|---|
| football-data.org | 基础赛程/赛果、五大联赛、荷甲、欧冠、世界杯、欧洲杯等 | MVP 或备份源 |
| API-Football | 广覆盖比赛数据 | 生产主源候选 |
| SportMonks | 广覆盖、阵容、赔率、统计、伤停 | 生产主源候选 |
| OpenFootball / football.json | 历史赛果、原型数据 | 免费历史辅助源 |

### 2.2 技术统计与 xG

用途：

```text
射门
射正
角球
控球
黄牌/红牌
xG
xGA
事件级数据
球员表现
```

候选源：

```text
SportMonks
API-Football
StatsBomb commercial / open data for research
Opta / Stats Perform enterprise
```

MVP 可先使用基础统计，后续接入真实 xG。不要长期依赖简化 xG 公式作为主特征。

### 2.3 赔率与盘口数据

用途：

```text
1X2
中国竞彩赔率，如可合法获得
亚洲让球
大小球
比分
盘口变化
closing odds
市场隐含概率
```

候选源：

| 数据源 | 用途 | 备注 |
|---|---|---|
| The Odds API | 多 bookmaker 赔率聚合 | 适合 MVP |
| SportMonks Odds | 与赛事数据整合 | 注意历史快照要自存 |
| Betfair Historical Data / Exchange API | 交易所价格与历史回测 | 适合高级市场基准 |
| Polymarket APIs | Prediction market 补充信号 | 必须考虑流动性和覆盖率 |

不要使用违反条款的爬虫抓取数据。对于 Bet365 等数据，必须通过合法授权或合规数据供应商。

### 2.4 伤停、停赛、预计首发、实际首发

用途：

```text
球员可用性
核心球员缺阵
预计首发
官方首发
轮换风险
替补落差
```

候选源：

```text
SportMonks expected lineups
SportMonks injuries and suspensions
官方俱乐部公告
可靠新闻源
```

### 2.5 文本数据

用途：

```text
发布会
新闻
德比背景
争冠/保级/欧战动机
赛程压力
教练轮换暗示
```

LLM 用于把文本转成结构化信号。

---

## 3. 数据快照原则

每类时间敏感数据都必须保存快照：

```text
odds_snapshots
lineup_snapshots
injury_snapshots
feature_snapshots
prediction_snapshots
```

禁止只保存“最新值”。原因：

```text
防止回测数据泄漏
支持赛前不同时间点预测
支持 closing odds 对比
支持错误归因
支持模型迭代
```

---

## 4. Provider 标准化设计

### 4.1 Provider Adapter 接口

```python
class ProviderAdapter:
    provider_name: str

    def fetch_competitions(self) -> list[dict]: ...
    def fetch_seasons(self, competition_id: str) -> list[dict]: ...
    def fetch_fixtures(self, competition_id: str, season: str) -> list[dict]: ...
    def fetch_fixture_detail(self, fixture_id: str) -> dict: ...
    def fetch_odds(self, fixture_id: str) -> list[dict]: ...
    def fetch_lineups(self, fixture_id: str) -> list[dict]: ...
    def fetch_injuries(self, team_id: str) -> list[dict]: ...
    def fetch_team_stats(self, fixture_id: str) -> list[dict]: ...
```

### 4.2 Provider ID 映射

```text
provider_entity_mappings
- mapping_id
- provider
- entity_type: competition/team/player/fixture
- provider_entity_id
- canonical_entity_id
- confidence
- created_at
- updated_at
```

### 4.3 名称标准化

球队名需要处理：

```text
不同语言
缩写
赞助名变更
历史名称
大小写
特殊符号
```

建议维护：

```text
team_aliases
- team_id
- alias
- language
- source
- valid_from
- valid_to
```

---

## 5. 赛事配置化接入

### 5.1 competition_config.yaml

新增赛事不改核心代码，只新增配置。

示例：荷甲

```yaml
competition_id: NED_EREDIVISIE
name: Eredivisie
country: Netherlands
region: Europe
competition_type: domestic_league
team_type: club
season_calendar: autumn_spring
provider_primary: football_data_org
provider_secondary: sportmonks
coverage_tier: A_full

model:
  base_model: club_goal_model
  calibration_scope: league
  home_advantage_mode: league_specific
  goal_distribution_mode: league_specific
  cold_start_strategy: market_prior_plus_elo

markets:
  enabled:
    - 1x2
    - asian_handicap
    - totals
    - correct_score
  cn_lottery_available: false
```

示例：日本 J1

```yaml
competition_id: JPN_J1
name: J1 League
country: Japan
region: Asia
competition_type: domestic_league
team_type: club
season_calendar: spring_autumn
provider_primary: api_football
provider_secondary: sportmonks
coverage_tier: B_medium

model:
  base_model: club_goal_model
  calibration_scope: league
  home_advantage_mode: league_specific
  goal_distribution_mode: league_specific
  cold_start_strategy: market_prior_plus_elo

quality_requirements:
  min_historical_matches: 500
  min_odds_coverage: 0.70
  min_result_coverage: 0.99
```

示例：欧罗巴杯

```yaml
competition_id: UEFA_EUROPA
name: UEFA Europa League
region: Europe
competition_type: continental_club
team_type: club
season_calendar: autumn_spring
provider_primary: sportmonks
provider_secondary: api_football
coverage_tier: A_full

model:
  base_model: cross_league_goal_model
  calibration_scope: competition_stage
  cross_league_strength_required: true
  two_leg_context_required: true

context:
  supports_group_stage: true
  supports_knockout: true
  supports_two_leg: true
  supports_neutral_final: true
```

---

## 6. 赛事难度分级

### A 类：容易接入

```text
荷甲
葡超
英冠
德乙
西乙
意乙
法乙
巴甲
```

特点：

```text
主客场联赛制稳定
历史数据相对充足
赔率市场相对活跃
模型迁移成本低
```

### B 类：中等难度

```text
日本 J1/J2
韩国 K League
中超
澳超
美职联
瑞典超
挪超
```

需要：

```text
联赛专属主场优势
联赛专属进球分布
赛季日历差异
赔率覆盖率检查
阵容/伤停覆盖率检查
```

### C 类：杯赛/欧战

```text
欧冠
欧罗巴杯
欧协联
足总杯
国王杯
德国杯
意大利杯
法国杯
```

额外上下文：

```text
单回合/两回合
首回合比分
总比分
轮换动机
淘汰赛策略
中立场
决赛
```

### D 类：国家队赛事

```text
世界杯
欧洲杯
亚洲杯
美洲杯
非洲杯
欧国联
友谊赛
```

需要独立建模：

```text
国家队 Elo
阵容强度
球员俱乐部状态
中立场
大赛经验
旅途/时差
小组赛最后一轮动机
```

---

## 7. 赛事上线流程

```text
1. Provider coverage check
2. 新增 competition_config.yaml
3. 拉取历史赛程/赛果
4. 建立 team/provider mapping
5. 校验赛程完整性
6. 校验赛果完整性
7. 校验赔率覆盖率
8. 校验盘口覆盖率
9. 校验阵容/伤停覆盖率
10. 训练 league-specific 参数
11. Walk-forward 回测
12. 校准模型
13. Beta 上线
14. 线上监控 2-4 周
15. 达标后 Production
```

### 7.1 Beta 上线标准

```text
赛程完整率 >= 98%
赛果完整率 >= 99%
至少 300 场历史样本，杯赛可降低但必须标 Beta
赔率覆盖率 >= 60%
模型可生成完整比分矩阵
玩法解析测试通过
```

### 7.2 Production 标准

```text
至少 500 场有效历史样本，或 2 个完整赛季
赛程完整率 >= 99%
赛果完整率 >= 99%
赔率覆盖率 >= 85% 优先
盘口覆盖率 >= 70% 优先
Log Loss 不劣于 baseline
Brier Score 不劣于 baseline
校准曲线无严重偏移
```

---

## 8. 数据质量评分

每场比赛生成 `data_quality_score`：

```text
fixture_quality =
  20% 赛程可信度
+ 20% 赔率覆盖度
+ 20% 阵容/伤停覆盖度
+ 20% 历史统计完整度
+ 10% provider 一致性
+ 10% 数据新鲜度
```

等级：

```text
A: >= 85
B: 70-84
C: 50-69
D: < 50
```

前端展示：

```text
数据质量 A：预测基础较完整
数据质量 C：阵容/赔率数据不足，谨慎解读
数据质量 D：不生成串关推荐
```

---

## 9. 数据泄漏防护

必须禁止：

```text
用赛后技术统计预测赛前结果
用 closing odds 回测 T-24h 预测
用实际首发回测 T-7d 预测
用比赛结束后的伤停状态预测比赛
```

实现方式：

```text
所有查询必须带 as_of_time
所有 feature_snapshot 固化
所有 backtest 使用 walk-forward
所有训练数据按时间切分
```

---

## 10. 数据源参考

本项目参考的数据源和规则资料集中在 `10_Nutmeg_Glossary_and_References.md`。开发时必须核对每个 provider 的授权条款、调用限制、历史数据保留策略和商业使用限制。

