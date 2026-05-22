# Nutmeg V3.1 推荐核心升级设计、计划与执行文档

## 1. 背景与纠偏

V2 已经完成了比分矩阵、玩法解析、串关展开、赛后评估、Provider 接入、前端 MVP 与运维治理等大量基础能力。但近期开发路线出现了一个明显偏移：过多时间投入到了 VPS、数据源免费额度、Provider Ops 和展示型前端，而用户真正需要的是：

```text
在赛前动态变化的信息中，给出预算内最好的单式 / 复式推荐。
```

V3.1 的目标不是推翻 V2，而是在 V2 的 score-grid-first、snapshot-first、accuracy-first 架构上，增加一个真正面向产品答案的推荐决策层。

本仓库当前本地文档目录为 `Nutmeg_docs_v2/`。旧引导文件中的 `docs/nutmeg/` 路径在当前工作区不存在，因此 V3.1 以 `Nutmeg_docs_v2/00-10` 为本地权威文档，并继承其中的禁止事项：

```text
不做自动下注
不做钱包、充值、支付
不使用保证盈利、稳赢、必赚等措辞
LLM 不直接给概率、不直接决定推荐
```

## 2. 产品北极星

Nutmeg 的前端可以很简单，后端可以复杂。产品最终只回答一个问题：

```text
在用户给定玩法、关数、预算、风险偏好和已确认选择的前提下，现在最值得采用的答案是什么？
```

必须支持：

```text
单式推荐
复式推荐
2串1 到 8串1
胜平负
中国体育彩票让球胜平负
欧洲让球胜平负
比分
冷门保护
预算内最优
赛前动态更新
用户已确认腿的锁定与延续计算
```

## 3. V2 与 V3 评估

### 3.1 V2 优势

V2 的核心技术判断是正确的：

```text
score_probability_grid -> market resolver -> upset detector -> parlay optimizer -> accuracy loop
```

这个架构的优势是：

```text
所有玩法来自同一个比分概率矩阵，避免互相矛盾
每次预测有快照，可复盘、可评估、可校准
玩法规则独立于模型，便于新增市场
串关计算已有原子注单展开、EV、ROI、预算校验
Accuracy Loop 能为后续模型晋级和回滚提供证据
```

### 3.2 V2 不足

V2 更像“概率工作台”，还不是“最佳答案引擎”。主要缺口：

```text
缺少 Recommendation Policy Engine
缺少 Recommendation Lifecycle Engine
缺少预算超限后的自动降维与替换策略
缺少用户已确认腿的锁定机制
缺少赛前动态更新下的推荐版本管理
缺少面向最终答案的简洁前端
冷门能力还没有进入推荐目标函数
```

### 3.3 V3.1 设计判断

V3.1 不改变底层预测架构，而是在 Parlay Optimizer 之上增加一层推荐决策：

```text
Prediction Model 负责概率
Market Resolver 负责玩法概率
Upset Engine 负责冷门风险与保护方向
Parlay Optimizer 负责注单展开和组合数学
Recommendation Engine 负责“选哪个答案”
Recommendation Lifecycle Engine 负责“赛前怎么变、已确认怎么保留”
```

## 4. V3.1 目标架构

```text
Data Snapshots
  -> Feature Snapshots
  -> Score Probability Grid
  -> Market Resolver
  -> Market Candidate Engine
  -> Upset / Fragility Engine
  -> Recommendation Policy Engine
  -> Budget Optimizer
  -> Recommendation Lifecycle Engine
  -> Simple Answer API / Frontend
  -> Post-match Evaluation / Accuracy Loop
```

### 4.1 Prediction Core

职责：

```text
生成 lambda_home / lambda_away
生成 score_probability_grid
派生所有玩法概率
保存 prediction_snapshot
```

注意：Prediction Core 不直接输出“买什么”。

### 4.2 Market Candidate Engine

职责：

```text
把每场比赛、每个玩法、每个结果变成 RecommendationCandidate
附带概率、赔率、市场隐含概率、模型边际、数据质量、模型版本、预测时间
过滤过期、低质量、已开赛、规则非法候选
```

### 4.3 Upset Engine

职责：

```text
识别热门不胜
识别热门输球
识别热门赢球但输盘
识别平局被低估
识别弱队受让保护方向
识别大比分尾部风险
```

冷门不是单独页面装饰，而必须能影响推荐评分和复式保护策略。

### 4.4 Recommendation Policy Engine

职责：

```text
对候选项打分
选择单式最佳答案
选择 N串1 单式最佳答案
决定哪些比赛允许或需要复式保护
区分命中率优先、价值优先、冷门保护、预算受限最优
```

评分必须区分：

```text
model_probability
market_implied_probability
calibrated_probability
data_quality
model_confidence
model_edge
upset_protection_score
odds_stability
volatility_penalty
correlation_penalty
```

### 4.5 Budget Optimizer

当系统生成复式 6串1，但总注额超过预算时，不应直接失败。应执行：

```text
1. 保留用户已锁定腿
2. 计算每个复式附加选项的边际收益
3. 优先移除低边际、低概率、低校准、低保护价值选项
4. 必要时替换未锁定比赛
5. 若仍超预算，降为预算内最优单式组合
6. 若最低单式仍超预算，只返回无法满足预算
```

预算优化目标不是“减少注数”本身，而是在预算内最大化综合推荐质量。

### 4.6 Recommendation Lifecycle Engine

推荐不是一次性产物，而是赛前动态对象。

核心状态：

```text
candidate
current
superseded
locked
confirmed_manual
live
settled
invalidated
```

典型规则：

```text
未锁定且未开赛：可被新信息替换
已锁定但未开赛：保留为用户约束，同时生成“锁定保留版”和“当前最优版”对比
已确认或已开赛：不再修改原推荐，只继续评估剩余腿
已开赛腿：不参与未来新推荐候选，但可作为已确认组合上下文
```

### 4.7 Frontend V3.1

前端不再优先展示大量概率表，而应优先展示答案：

```text
今日最佳单式
今日最佳 2串1-8串1
预算内最佳复式
冷门保护建议
已确认推荐跟踪
推荐更新时间
模型版本 / 数据质量
```

详细概率、EV、ROI、比分 Top 5 可以作为二级展开信息，不占据第一屏主体。

## 5. 数据与模型扩展计划

V3.1 需要新增或补强的实体：

```text
recommendation_candidates
recommendation_runs
recommendation_versions
recommendation_lifecycle_events
recommendation_locked_legs
recommendation_budget_adjustments
recommendation_policy_configs
```

MVP 可先以 Pydantic domain model 和解释性 payload 实现，数据库迁移在推荐策略稳定后落地。

## 6. LLM 使用边界

LLM 目前不是核心预测器，也不应该直接输出概率或最终推荐。

V3.1 中 LLM 只允许用于：

```text
伤停 / 发布会 / 新闻文本结构化
语义特征提取
推荐解释文本摘要
赛后错误分析摘要
用户自然语言查询解释
```

LLM 输出必须进入 feature / explanation 层，由模型、规则和推荐策略消费。最终推荐必须由可测试代码计算产生。

## 7. 执行阶段

### Phase V3.1-1：推荐决策主干

交付：

```text
RecommendationCandidate domain model
RecommendationPolicyConfig
候选项评分
最佳单场选择
最佳 N串1 单式选择
锁定腿保留逻辑
开赛候选排除逻辑
推荐生命周期状态模型
预算优化器最小版本
单元测试
```

验收：

```text
高概率 / 高质量候选优先于单纯高赔率候选
2串1-8串1 解析正确
锁定腿会被保留并继续参与未来组合
未锁定已开赛候选不会进入新推荐
复式超预算时能移除低边际选项直到预算内
```

### Phase V3.1-2：数据库与 API

交付：

```text
recommendation_* migrations
GET /recommendations/best
POST /recommendations/generate
POST /recommendations/{id}/lock-leg
POST /recommendations/{id}/confirm-manual
POST /recommendations/{id}/supersede
POST /recommendations/{id}/invalidate
GET /recommendations/{id}/lifecycle
```

### Phase V3.1-3：复式与替换优化

交付：

```text
多选边际收益计算
预算内组合搜索
未锁定腿替换
锁定版 vs 当前最优版比较
冷门保护型复式策略
```

### Phase V3.1-4：前端答案化

交付：

```text
首页只展示最佳答案
单式 / 复式 / 串关选择器
预算输入
锁定腿展示
冷门保护提示
推荐变更提示
```

### Phase V3.1-5：Accuracy Loop 接入推荐层

交付：

```text
按推荐策略评估长期表现
按玩法、关数、风险偏好评估
推荐命中率、EV、ROI、校准表现
策略晋级 / 回滚证据
```

## 8. 当前开始执行

本轮立即执行 Phase V3.1-1。范围严格限制在：

```text
后端推荐 domain / policy / budget / lifecycle 基础模块
单元测试
本地文档落地
```

本轮不做：

```text
VPS 部署
新 Provider 接入
前端重做
自动下注
数据库大迁移
LLM 接入
```

VPS 可作为后续部署测试工具，但不再作为核心开发阻塞项。

## 9. 执行进度记录

### 2026-05-09

已完成：

```text
Phase V3.1-1 推荐决策主干
Phase V3.1-2 推荐候选池、持久化结构与 API 主干
Phase V3.1-3 复式组合搜索与预算内最优调整
Phase V3.1-4 推荐生命周期 API
Phase V3.1-5 推荐策略赛后评估接入 Accuracy Loop
Phase V3.1-6 推荐策略治理与晋级/回滚证据
Phase V3.1-7 前端答案化重构
Phase V3.1-8 锁定腿前端联动与预算修剪策略
Phase V3.1-9 推荐生命周期 API 前端桥接
Phase V3.1-10 推荐生命周期真实读取与取消保留
Phase V3.1-11 预算约束下的跨比赛替换搜索
Phase V3.1-12 预算约束下的全局候选 beam search
Phase V3.1-13 推荐策略治理概览与前端面板
Phase V3.1-14 证据驱动的 auto 推荐策略选择
```

V3.1-3 当前落地能力：

```text
从单式基准选择生成复式候选
按边际质量增益决定是否增加保护选项
受 max_budget 约束控制原子注数和总金额
不向已开赛 / 已锁定的腿追加新选项
输出 locked-preserving 与 current-best 的对比结构
```

V3.1-4 当前落地能力：

```text
查看 recommendation run 生命周期明细
锁定单腿并写入 recommendation_locked_legs
手动确认推荐为 confirmed_manual
将推荐标记为 superseded 或 invalidated
每次状态变化写入 recommendation_lifecycle_events
```

V3.1-5 当前落地能力：

```text
按 recommendation run 重新结算 stored parlay atomic bets
计算推荐命中、原子注赢/输/未完成、总派彩、P/L、ROI
记录推荐生成时的 expected hit probability / EV / ROI，支持赛后对照
计算实际命中与预期命中概率之间的校准偏差
按 strategy / pass_type / mode 汇总长期表现指标
仅在完整结算时默认写入，未完赛推荐保持可后续评估
提供后台 API 触发推荐评估
```

V3.1-6 当前落地能力：

```text
按 strategy / pass_type / mode 读取 settled 推荐评估证据
对候选策略与基线策略进行 ROI、命中率、命中校准误差对比
生成推荐策略 promotion review：shadow_candidate 或 keep_experiment
生成推荐策略 rollback plan：必要时恢复 baseline strategy
持久化 recommendation_strategy_reviews 审核记录
提供后台 API 触发策略治理评审
```

V3.1-7 当前落地能力：

```text
首页首屏改为答案优先：单式首选、预算内串关、复式保护、冷门保护、锁定跟踪
串关页首屏复用同一推荐答案面板，备选组合退到二级区域
2串1-8串1、预算、单位金额、单式/复式结构、玩法范围统一通过前端参数控制
胜平负、中国让球、欧洲让球、比分、亚洲让球进入前端玩法范围选择
推荐数据使用兜底样本时展示提示，避免把样本数据误当实时结论
导航文案从实验室/概率地图收敛为推荐答案导向
```

V3.1-8 当前落地能力：

```text
复式推荐优化器先搜索正向保护选项，再按预算修剪最低边际的未锁定选项
预算修剪结果写入 explanation_json.budget_adjustment，记录原始注数/金额、优化后注数/金额、移除项和 warning code
锁定候选在预算修剪中作为用户约束保留，不把已锁定结果作为优先移除对象
前端推荐答案面板支持通过 locked_fixture 参数锁定/取消锁定比赛
锁定状态会影响预算内串关与复式保护候选过滤，并在“锁定跟踪”中显示剩余候选
当前锁定联动为 URL 约束式交互，后续可接入 recommendation lifecycle 持久化 API
```

V3.1-9 当前落地能力：

```text
前端“保留”动作先尝试通过 POST /recommendations/generate 创建持久化 recommendation run
持久化 run 创建成功后调用 POST /recommendations/{id}/lock-leg 写入生命周期保留腿事件
前端 URL 会携带 recommendation_run_id 与 retention_source，便于后续页面继续读取生命周期状态
当本地未配置 admin token、Postgres recommendation repository 不可用或 API 失败时，自动回退为 URL 约束保留
默认 all pass_type 在持久化桥接中落到 2x1，避免后端 2x1-8x1 单一 pass_type 合同失败
前端仍使用“保留”文案，避免产生确定性暗示；后端内部可继续使用 lock-leg 合同命名
```

V3.1-10 当前落地能力：

```text
前端在存在 recommendation_run_id 时读取 GET /recommendations/{id}/lifecycle
答案面板合并 URL 约束与 lifecycle API 返回的真实保留腿，继续影响当前推荐筛选
答案面板展示保留来源和最近生命周期事件，但不扩大为复杂仪表盘
新增 POST /recommendations/{id}/release-leg，用于把已保留腿标记为 released
取消保留后重新计算 recommendation_runs.locked_fixture_ids_json，若无剩余保留腿则回到 current
前端取消保留优先调用 release-leg，API 不可用时回退为 URL 参数约束
后端仓储、API 集成和前端禁止措辞静态测试已覆盖该流程
```

V3.1-11 当前落地能力：

```text
复式推荐在完成预算修剪后，会对未保留、未开赛腿执行跨比赛替换搜索
替换搜索保留用户已确认约束，不替换 locked_fixture_ids 中的比赛
替换搜索只接受质量提升且 total_stake 仍在 max_budget 内的候选
替换候选可在预算允许时附加同玩法保护选项，例如从单选替换为预算内复式保护
替换决策写入 explanation_json.fixture_replacement_search，包含 old_fixture_id、new_fixture_id、quality_delta、replacement_outcomes
已补充单元测试验证保留腿不变、未保留腿可替换、替换后总金额仍受预算约束
```

V3.1-12 当前落地能力：

```text
复式推荐优化器新增预算约束下的 beam search，从候选比赛与同玩法保护选项组合中搜索更优方案
beam search 保留用户已确认候选，不把 locked_candidates 替换为其他比赛
未保留且已开赛候选继续通过 as_of_time_utc 过滤，不参与新的推荐组合
每个比赛生成单选与同市场复式保护 variant，最终只接受 total_stake <= max_budget 且 quality_score 提升的组合
当 beam search 覆盖局部贪心路径时，explanation_json.beam_search 记录 beam_width、候选比赛数、variant 数、评估完整状态数、quality_delta 与最终 outcome
已补充确定性单元测试验证 beam search 可在预算内覆盖局部预算路径，并输出可追踪解释数据
```

V3.1-13 当前落地能力：

```text
新增 GET /recommendations/strategy-governance 只读接口，用于读取推荐策略治理概览
Postgres 模式读取 recommendation_run_evaluations 的 settled 证据，并复用已有 promotion / rollback 门槛
mock 模式返回确定性策略治理样本，避免本地开发被数据库或数据源阻塞
前端新增 /strategy 策略治理页，只展示样本、ROI、命中率、校准误差、治理决策与原因
该页面定位为内部治理入口，不应作为普通用户推荐页面的一部分
已补充集成测试验证只读治理接口在 mock 模式可返回可追踪概览
```

V3.1-14 当前落地能力：

```text
推荐生成请求新增 strategy=auto，默认不再硬编码 accuracy_first
auto 策略会读取策略治理概览，选择通过 promotion gate 且无 rollback 信号的候选策略
当多个候选通过治理门槛时，优先按 ROI delta、校准误差 delta、命中率 delta 和样本量排序
没有候选策略通过治理门槛时，自动回退到 baseline accuracy_first
推荐生成内部新增 strategy_selection 追踪字段，记录 requested_strategy、selected_strategy、source、review_key、原因、warning 和指标差值
前端持久化推荐桥接的 balanced 默认策略改为 auto，使已保留腿流程也能使用证据驱动策略选择
已补充单元测试和集成测试验证 auto 策略选择与推荐生成入口联动
```

V3.1-15 当前落地能力：

```text
策略选择仅作为后端内部审计数据保存，不再默认出现在推荐生成 API 响应中
非 dry-run 推荐会把 strategy_selection 写入 recommendation_runs.explanation_json.internal_trace
public response 会递归移除 explanation_json 中的 strategy、strategy_selection 与 internal_trace 字段
前端推荐答案面板、串关构建器与票据卡片不再展示策略/模式控件或策略徽章
主导航移除策略治理入口，避免普通用户把内部治理当成推荐理由
```

V3.1-16 当前落地能力：

```text
推荐生成响应新增 answer 字段，面向最终答案而非内部优化细节
answer 只包含关数、单式/复式、腿、预算、命中概率、期望收益、ROI、风险、数据质量和 warning
answer 不包含策略名称、策略选择原因或治理指标
该字段为后续前端切换到“只看最终答案”提供稳定合同
```

V3.1-17 当前落地能力：

```text
recommendations/generate 支持 pass_type=all，由后端在 2x1 到 8x1 中搜索预算内最终答案
pass_type=all 的选择逻辑保留在后端，前端不自行决定最佳关数
前端新增 getRecommendationEngineAnswer，优先读取 recommendations/generate.answer
首页与串关页把 answer 传入推荐答案面板，作为“预算内最终答案”的第一展示来源
当核心 answer 不可用时，页面继续回退到旧 parlay 候选，避免本地免费数据源或 Postgres 不可用时阻塞开发
answer 面板只展示最终腿、关数、单式/复式、总金额、命中概率、ROI、风险、数据质量和更新时间
```

V3.1-18 当前落地能力：

```text
recommendations/generate 响应新增 alternatives，用于返回 2x1 到 8x1 搜索过程中的预算内候选答案
后端 alternatives 使用与最终 answer 相同的公开合同，不暴露 strategy、strategy_selection 或 internal_trace
首页与串关页改为通过 getRecommendationEngineBundle 一次读取核心最终答案与备选候选
串关页“备选方案”由 Recommendation Engine alternatives 映射生成，旧 /parlays/recommend 仅在核心接口不可用时作为开发兜底
前端备选卡片隐藏 engine 内部 id，保留关数、单式/复式、腿、总金额、命中概率、ROI 与风险等必要信息
普通前端路由移除策略治理页面，推荐策略证据保留为后端内部能力，不作为用户推荐理由展示
```

V3.1-19 当前落地能力：

```text
recommendations/generate 响应新增 single_answer 与 upset_answer
单式首选与冷门保护答案从 Recommendation Engine 已评估候选中选出，前端不再自行用概率卡片排序生成答案
single_answer / upset_answer 只输出比赛腿、玩法、结果、概率、预算摘要、风险、数据质量和更新时间
首页与串关页的“单式首选”和“冷门保护”卡片改为消费后端答案合同
当核心推荐接口不可用或候选池未形成对应答案时，前端显示暂无答案，不再用本地概率排序冒充最终推荐
```

V3.1-20 当前落地能力：

```text
single_answer 与 upset_answer 升级为独立候选池搜索，不再从串关搜索结果中顺手提取
独立搜索复用 RecommendationCandidateQueryOptions、RecommendationPolicyConfig 与 rank_candidates
single_answer 在完整候选池内按推荐评分、概率、数据质量和模型边际排序
upset_answer 在完整候选池内优先按 upset_protection_score、推荐评分、概率和数据质量排序
该搜索仍遵守当前请求的玩法范围、最低概率、数据质量、赔率要求、competition/model 过滤和开赛前过滤
新增测试验证即使某候选没有进入串关选腿，也可以成为单式首选或冷门保护答案
```

V3.1-21 当前落地能力：

```text
single_answer 与 upset_answer 拆分为专用 policy profile，不再完全复用串关组合权重
single_focus_policy 更重视概率、数据质量、模型置信度与校准，弱化冷门保护分
upset_focus_policy 显著提高 upset_protection_score 权重，同时保留概率、模型边际、数据质量和校准约束
后端 focus search 分别用 single/upset policy 对完整候选池打分，再输出对应答案
新增单元测试验证 single policy 会偏向高置信高质量单式，upset policy 会在质量可接受时优先冷门保护信号
```

V3.1-22 当前落地能力：

```text
非 dry-run 推荐生成会把 single_answer 与 upset_answer 的内部候选快照写入 recommendation_runs.explanation_json.internal_trace.focus_policy_answers
focus_policy_answers 只用于后端赛后评估，不进入 public response，也不作为普通用户推荐理由展示
推荐赛后评估器会把已选串关比赛与 focus answer 比赛一起拉取赛果，避免冷门答案不在串关腿内时无法回测
settlement_detail_json 新增 focus_policy_evaluation，记录 single/upset 答案的赛果命中、实际结果、期望概率与校准误差
策略指标汇总新增 single_focus_hit_rate、upset_focus_capture_rate 以及对应校准误差，用于后续以真实样本校正权重
新增确定性测试覆盖 single focus 命中、upset focus 捕捉、focus 赛果补拉取和策略指标聚合
```

V3.1-23 当前落地能力：

```text
策略治理证据查询从 recommendation_run_evaluations.settlement_detail_json.focus_policy_evaluation 聚合 single/upset focus 指标
RecommendationStrategyEvidence 新增 single_focus_hit_rate、upset_focus_capture_rate、对应样本量与平均/绝对校准误差
promotion gate 在 single/upset focus 样本量达到 minimum_focus_sample_size 后，会检查单式命中率下降、冷门捕捉率下降和 focus 校准恶化
rollback plan 在 focus 样本量足够且校准误差超过 rollback_focus_calibration_error_ceiling 时，会给出 single/upset focus 校准漂移回滚信号
auto 策略选择排序新增 focus deltas，ROI、整体校准与整体命中仍优先，focus 指标作为同档策略的准确性证据
metrics_json / 回测式策略报告新增 focus deltas 与 focus 阈值，便于后续周期性报告直接使用这些证据
mock 治理样本也补齐 focus 指标，保持本地开发和真实 Postgres 证据合同一致
新增确定性测试覆盖 focus 指标阻断 promotion、触发 rollback、进入 metrics_json 和从 Postgres 聚合结果读取
```

V3.1-24 当前落地能力：

```text
新增 Prematch Recommendation Lifecycle Backtest，用多个赛前 checkpoint 回放推荐在开赛前如何变化
checkpoint 支持 as_of_time_utc、候选池、用户已保留 fixture、突发信息剔除 fixture、incident_notes 与 metadata
回测会累计用户已保留腿，并在后续 checkpoint 中把 locked candidates 作为硬约束继续参与 2x1-8x1 重组
已开赛但未保留的候选会被识别为 started_unlocked_fixtures_excluded，不再进入新的推荐组合
突发信息剔除会生成 incident_exclusion_applied；若比赛尚未被用户保留，会从候选池移除并触发推荐重算
若突发信息命中已经保留的 fixture，系统会保留该腿并输出 locked_fixture_has_incident_exclusion warning，避免擅自改掉用户已确认选择
stage 输出 selected_fixture_ids、locked_fixture_ids、preserved_locked_fixture_ids、started_locked_fixture_ids、continuation_fixture_ids、remaining_open_leg_count、changed_fixture_ids、event_codes、warnings 与 explanation_json
summary_json 汇总 stage_count、changed_stage_count、incident_stage_count、locked_preservation_stage_count、started_locked_stage_count、continuation_stage_count、最终选择与剩余可继续计算 fixture
支持 single 与 multiple 两种 mode；复式模式继续复用预算约束与 max_outcomes_per_fixture
新增确定性测试覆盖：A/B 已保留后 C-F 继续参与后续重组、A/B 未保留时被突发信息剔除并改选 C-H、已保留 fixture 被突发标记时保留但告警、复式预算模式不超预算
```

V3.1-25 当前落地能力：

```text
新增 Persisted Recommendation Lifecycle Replay，从 recommendation_runs 读取真实已生成推荐运行
回放 repository 会关联读取 recommendation_candidates、recommendation_lifecycle_events 与 recommendation_locked_legs
PersistedRecommendationRunSnapshot 汇总每次 run 的 as_of_time、pass_type、mode、预算、选中 fixture、锁定 fixture、候选、生命周期事件和锁腿记录
build_persisted_recommendation_lifecycle_replay 会按时间生成 stage，识别 initial/unchanged/changed/no_selection
stage 输出 selected_fixture_ids、locked_fixture_ids、preserved_locked_fixture_ids、missing_locked_fixture_ids、changed_fixture_ids、incident_fixture_ids、lifecycle_reason_codes、event_codes 与 warnings
锁定腿若在后续 run 中仍被选中，会记录 locked_fixtures_preserved；若丢失，会输出 locked_fixture_not_preserved warning，便于发现生命周期约束被破坏
突发信息从 explanation_json 与 lifecycle event metadata_json 中提取 excluded/incident/invalidated fixture，并映射为 incident_exclusion_observed
新增 build_prematch_backtest_checkpoints_from_persisted_snapshots，可把已持久化 run 转成 PrematchRecommendationBacktestCheckpoint，作为内存回测模型和真实数据之间的桥接层
该回放层是后端内部评估/报告能力，不扩大普通用户前端展示，也不暴露策略治理细节
新增确定性测试覆盖：真实 run 变更溯源、锁定腿保留/缺失告警、repository 多表读取分组、持久化 snapshot 转 checkpoint
```

V3.1-26 当前落地能力：

```text
新增 recommendation_candidate_pool_snapshots 与 recommendation_candidate_pool_items 迁移，用于保存每次非 dry-run 推荐生成时的完整候选池
RecommendationGeneration 在保存 recommendation run 时同步持久化完整候选池，而不仅保存最终入选腿
候选池快照记录 as_of_time、strategy、pass_type、mode、candidate_count、selected_candidate_count、excluded_candidate_count 与 candidate_query_json
候选池 item 保存每个候选的玩法、结果、概率、赔率、市场隐含概率、模型边际、数据质量、模型版本、预测时间、开赛时间、selected/locked 标记和 metadata
新增 recommendation_provider_incident_events 迁移，用于记录会影响推荐的 provider 原始 incident，例如阵容突发、伤停、数据质量异常或 provider 更正
Provider incident 记录支持 provider_incident_key 幂等 upsert、fixture/competition 关联、severity、status、event_time、observed_at、excluded_fixture_ids_json 与原始 payload
新增 RecommendationProviderIncidentRepository，可记录和按时间窗/fixture/competition/status 查询推荐域 incident
新增 apply_provider_incidents_to_backtest_checkpoints，把 active incident 合并到 PrematchRecommendationBacktestCheckpoint 的 excluded_fixture_ids、incident_notes 和 metadata
Persisted lifecycle replay repository 会读取 candidate pool snapshot/items；生成 checkpoint 时优先使用完整候选池，缺失时回退到已入选候选
build_prematch_backtest_checkpoints_from_persisted_snapshots 支持额外传入 provider_incidents，使真实 run 回放能同时考虑候选池和赛前突发信息
该能力仍是后端内部准确性/追踪基础，不向普通前端暴露策略、治理或复杂回放过程
新增确定性测试覆盖：候选池随推荐运行保存、provider incident 原始记录与查询、incident 合并 checkpoint、持久化回放优先使用完整候选池、迁移合同
```

V3.1-27 当前落地能力：

```text
新增 Recommendation Provider Incident Mapping，把 provider_observations 映射为 recommendation_provider_incident_events
映射器读取现有 provider sync 写入的 injuries、lineups、odds observations，不直接调用外部数据源，也不依赖 LLM 判断
伤停/停赛/不可用状态会生成 player_availability_* incident；高置信 critical 状态会把对应 fixture 写入 excluded_fixture_ids
疑似伤病、questionable、ill 等状态生成 warning incident，但不默认硬排除 fixture
confirmed lineup 中的 non-starter 生成 confirmed_non_starter warning，用于触发推荐重新评估，但不把普通阵容发布伪装成最终推荐理由
odds fair_probability 同一 provider/fixture/bookmaker/market 连续观测出现大幅变化时，生成 odds_probability_shift incident
赔率变化阈值分为 warning 与 critical；critical shift 会把 fixture 标记为临时排除，直到推荐重新生成/人工审核
provider_incident_key 使用 provider_observation_id 或稳定 hash，支持幂等写入 recommendation_provider_incident_events
新增 run_recommendation_provider_incident_mapping，可按 as_of_time、lookback、provider、fixture 读取 observations 并 dry-run 或持久化 incident
该能力仍位于后端内部链路，普通前端不展示“使用了什么策略”或 provider 细节，只消费最终推荐答案
新增确定性测试覆盖：critical 伤停映射为 fixture exclusion、confirmed non-starter 告警、赔率概率突变、runner 读取 observations 并写入 incident
```

V3.1-28 当前落地能力：

```text
新增 recommendation_prematch_change_reports 迁移，用于保存周期性赛前推荐变化报告
新增 Recommendation Prematch Change Report domain，将 persisted lifecycle replay、完整候选池 checkpoint 与 provider incident 汇总成报告
报告 summary 输出 stage_count、changed_stage_count、incident_count、critical_incident_count、locked_preservation_stage_count、final_run_key 与 final_selected_fixture_ids
报告生成会读取 recommendation_runs / recommendation_candidates / recommendation_candidate_pool_* / recommendation_lifecycle_events / recommendation_locked_legs
报告可选择合并 recommendation_provider_incident_events，并把 active incident 注入 checkpoint，用于解释赛前推荐变化
新增 report_key 稳定生成与幂等 upsert，便于后续定时任务重复生成同一窗口报告
新增 POST /recommendations/provider-incidents/map 后台接口，可触发 provider_observations -> recommendation_provider_incident_events 映射，支持 dry_run 或持久化
新增 POST /recommendations/prematch-change-report 后台接口，可按时间窗、pass_type、mode、strategy 生成赛前变化报告，支持 dry_run 或保存
两个后台接口都要求 admin token 与 postgres recommendation repository，不进入普通前端展示
新增确定性测试覆盖：报告构建摘要、报告持久化、迁移合同、incident mapper 后台触发接口、prematch report 后台接口
```

V3.1-29 当前落地能力：

```text
新增 recommendation_recompute_trigger_runs 迁移，用于审计赛前推荐重算触发结果
RecommendationGenerationOptions 支持 locked_candidates 与 excluded_fixture_ids，重算时复用现有 Recommendation Engine/Optimizer，不另开一套推荐逻辑
锁定腿作为 locked_candidates 传入单式/复式优化器，继续作为用户约束保留；incident 排除只作用于未锁定候选
新增 Recommendation Recompute Trigger，读取时间窗内 persisted recommendation runs 与 active recommendation_provider_incident_events
触发器会判断 incident 是否影响当前入选 fixture、已锁定 fixture 或完整候选池 fixture
critical provider incident、odds_probability_shift、selected_fixture_incident、candidate_pool_incident 会写入 reason_codes
触发重算时会从原 recommendation run 继承 pass_type、mode、strategy、unit_stake、max_budget 与 candidate_query_json 中的候选查询条件
重算 internal_trace 写入 source_recommendation_run_id、source_run_key、incident_event_keys、excluded_fixture_ids 与 locked_fixture_ids，供后端审计/评估使用
非 dry-run 时会生成新的 recommendation run，并保存 recompute trigger audit，包括 checked/triggered/skipped 数量、incident keys、source run ids、generated run ids 与 result_json
新增 POST /recommendations/recompute-trigger 后台接口，要求 admin token 与 postgres recommendation repository
新增确定性测试覆盖：critical incident 触发重算并排除 fixture、锁定腿保留、无关 incident 跳过、非 dry-run 审计保存、后台 API 触发
```

V3.1-30 当前落地能力：

```text
新增 recommendation_prematch_pipeline_runs 迁移，用于审计赛前核心推荐流水线执行结果
新增 Recommendation Prematch Pipeline，将 provider observation incident mapping、recommendation recompute trigger 与 prematch change report 串成单次后台 runner
流水线统一使用 as_of_time_utc 与 lookback_hours 派生窗口，保证 incident 映射、推荐重算、赛前报告处于同一时间切片
provider_name 与 canonical_fixture_id 可收窄 observation mapping 范围，pass_type/mode/strategy 可收窄重算与报告范围
非 dry-run 时，流水线会先持久化 recommendation_provider_incident_events，再触发推荐重算，最后生成赛前变化报告
dry-run 时不会持久化新 incident，因此输出 dry_run_provider_incidents_not_persisted_before_recompute warning，避免误以为 transient incident 已参与数据库重算
流水线审计记录 mapped/stored incident 数量、checked/triggered/skipped run 数量、generated recommendation run ids、prematch report key、warnings 与 result_json
新增 POST /recommendations/prematch-pipeline 后台接口，要求 admin token 与 postgres recommendation repository，可作为后续 CLI/定时任务的核心执行入口
该能力仍是后端内部自动化，不向普通前端展示采用了什么策略，也不改变用户侧推荐答案合同
新增确定性测试覆盖：三步 runner 顺序与参数传递、dry-run warning、审计保存、失败审计、迁移合同、后台 API 触发
```

V3.1-31 当前落地能力：

```text
新增 Recommendation Global Best Planner，用同一层后端决策比较单式、单选串关、复式串关
规划器内部支持 1x1 单式，并与 2x1 到 8x1 串关放入同一候选评估集合
规划器读取同一个 candidate pool，按 allowed_markets、competition、model_version、概率、数据质量、赔率和模型边际过滤候选
每个 pass_type/mode 组合都会生成一次候选 option；不可行组合会记录 attempt warning，例如 fixture 数不足或规则不通过
复式方案继续复用预算优化器、跨比赛替换搜索和 beam search；预算超限时不只修剪单个方案，也会与其他串关长度/模式比较
全局 planner_score 结合推荐评分、命中概率、ROI、数据质量、风险和预算效率，用于在有效且预算内的方案中选择 best_option
锁定腿会传入所有可行组合，规划器不会为了追求当前最高分擅自移除用户已确认的 fixture
新增 POST /recommendations/global-best 接口，可请求 pass_types=all、modes=single/multiple，返回 best answer 与 alternatives
非 dry-run 时，best_option 会持久化为 recommendation_run，并保存完整候选池与 global_planner internal_trace
普通前端仍不展示“采用了什么策略”；API public explanation 会剔除 strategy/internal_trace，仅保留结果必要载荷
新增确定性测试覆盖：单式与串关同池比较、不可行 pass_type 自动降级到可行方案、锁定腿保留、持久化 best selection、API 触发
```

V3.1-32 当前落地能力：

```text
前端首页与串关页改为优先呈现一个极简 Global Best 最终答案，普通用户不再先看到策略、治理或候选池细节
答案页只保留预算、单位金额、自动/指定串关类型、单式/复式结构与保留/取消比赛这些直接影响推荐结果的控制项
备选比赛、冷门摘要、参数细节与候选方案被折叠为二级复核信息，避免前端信息噪声覆盖最终答案
前端 getGlobalBestRecommendationBundle 直接消费 POST /recommendations/global-best，并保留 alternatives 作为备选答案摘要
已保留的生命周期锁定腿会以 locked_candidates 形式回传后端，只有 URL 约束时回传 locked_fixture_ids
global-best 后端请求新增 locked_fixture_ids、locked_candidates 与 excluded_fixture_ids，规划器会把已确认比赛作为硬约束继续纳入后续组合
锁定 fixture 但未提供具体 outcome 时，后端会按该 fixture 当前可用候选中概率、模型边际、数据质量和稳定性选择一个候选作为保留腿
锁定的具体 fixture/market/outcome 缺失时会输出 locked_candidate_unavailable warning，而不会静默生成看似已保留但实际未保留的答案
推荐锁定与取消仍只改变推荐生命周期/约束，不实现自动下注、支付、钱包或保证盈利措辞
```

V3.1-33 当前落地能力：

```text
新增 Recommendation Core Replay Report，把持久化推荐 run、完整候选池、生命周期回放、锁定腿保留和赛后结果评估串成一条核心验证报告
报告按时间窗读取 recommendation_runs 与候选池快照，并自动收集最终推荐、锁定腿、atomic bets 与 focus answer 涉及的 fixture result
报告会对每个 replayed run 调用赛后推荐评估器，输出 settled/partial/unresolved、命中、盈亏、ROI、校准误差和 focus 命中指标
报告新增内部 strategy_metrics，用于后端比较不同 strategy/pass_type/mode 的真实样本表现，但普通前端不展示采用了什么策略
报告内置 recommendation_runs_available、candidate_pool_snapshots_available、final_recommendation_selected、locked_fixtures_preserved、post_match_result_coverage、post_match_evaluations_settled 六类检查
summary_json 输出 run_count、changed_stage_count、incident_stage_count、locked_preservation_stage_count、settled_run_count、hit_count、profit_loss、roi、final_hit 与 core_flow_ready
新增 POST /recommendations/core-replay 后台接口，要求 admin token 与 postgres recommendation repository，用于本地或 VPS 触发真实样本回放验证
该能力只服务核心准确性闭环和开发诊断，不向普通用户展示复杂过程，也不引入自动下注、支付、钱包或保证盈利措辞
新增确定性测试覆盖：生命周期回放与赛后评估串联、候选池/结果缺失告警、runner 读取 fixture results、后台 API 权限与触发合同
```

V3.1-34 当前落地能力：

```text
新增 Recommendation Core Validation Runner/CLI，把 Global Best 推荐、赛前 Pipeline 与 Core Replay 串成一条可重复执行的后端验证命令
命令入口为 nutmeg-recommendation-core-validation，默认 dry-run，只输出 JSON 开发报告，不触发自动下注、支付、钱包或用户侧推荐文案
runner 会在同一 as_of_time/lookback 窗口内先生成全局最佳候选，再执行赛前 incident/recompute/report 流水线，最后对同一时间窗执行 core replay 赛后验证
支持 pass_type、mode、strategy、预算、候选池过滤、competition/model_version、provider/fixture 范围、replay 时间窗与各阶段 skip 参数
默认不写 prematch pipeline audit；只有显式 --save-audit 才写审计，只有显式 --commit 才让下游 runner 以非 dry-run 模式持久化结果
输出 summary_json 包含 global_best_candidate_count、global_best_selected、prematch_triggered_run_count、prematch_generated_run_count、core_replay_ready、core_replay_final_hit、core_replay_roi 与 warning_count
该 runner 是开发/运维内部工具，用于回答“这批推荐是否变准”，不向普通前端展示采用了什么策略
新增确定性测试覆盖：三段 runner 顺序和参数透传、默认无 audit 写入、replay-only commit 模式、CLI 参数到 options 的映射
```

V3.1-35 当前落地能力：

```text
新增 Recommendation Benchmark Runner/CLI，用固定 as_of_time、pass_type、single/multiple mode 与预算档位矩阵批量执行 Core Validation
命令入口为 nutmeg-recommendation-benchmark，默认 dry-run，不写审计、不持久化推荐、不触发自动下注、支付、钱包或用户侧推荐文案
默认基准矩阵覆盖 1x1、2x1、4x1、6x1、8x1 与 10/20/50 三档预算；1x1 只跑 single，其他 pass_type 可同时跑 single 与 multiple
每个 scenario 会调用 Recommendation Core Validation Runner，并保留 scenario_key、as_of_time、lookback、pass_type、mode、max_budget、warnings 与核心指标
summary_json 汇总 scenario_count、completed/failed 数量、global_best_selected_count、core_replay_ready_count、core_replay_total_run_count、core_replay_total_settled_run_count、final_hit_count、average_core_replay_roi 与 warning_count
支持 --pass-types、--modes、--budgets、多个 --as-of-time-utc、competition/model 过滤、--include-prematch-pipeline、--commit、--save-audit 与 --stop-on-error
默认 continue_on_error，单个预算/玩法 scenario 出错会记录 failed scenario，而不是让整份基准报告丢失
该 runner 是内部真实样本基准工具，用于逐步形成“哪类预算/串关/时间窗更稳定”的开发证据，不向普通前端展示策略细节
新增确定性测试覆盖：矩阵生成、指标聚合、失败 scenario 记录、stop-on-error、CLI 参数到 options 的映射
```

V3.1-36 当前落地能力：

```text
新增 recommendation_benchmark_runs 迁移，用于持久化 Recommendation Benchmark Runner 的矩阵报告历史
Benchmark runner 新增 --save-report 显式开关；默认仍只输出 JSON，不写表、不持久化推荐、不触发自动下注、支付、钱包或用户侧推荐文案
持久化记录保存 benchmark_key、as_of_times、pass_types、modes、budgets、scenario/completed/failed 数量、global_best_selected_count、core_replay_ready_count、settled run 数、final hit 样本、平均 ROI、warnings、summary_json 与 result_json
PostgresRecommendationBenchmarkRunRepository 支持按 benchmark_key 读取最近报告并保存当前报告
保存前会读取同一 benchmark_key 的上一份报告，生成 history_comparison_json
历史对比会比较 final_hit_rate、average_core_replay_roi、core_replay_ready_count、failed_count 与 warning_count，并输出 baseline/improved/regressed/mixed/unchanged 状态
summary_json 会附加 history_status 与 previous_benchmark_run_id，便于后续 CLI/后台任务追踪哪类预算/玩法组合相对上一轮改善或退步
该能力仍是内部准确性证据链，不进入普通用户前端，也不展示策略细节
新增确定性测试覆盖：迁移合同、repository 写入/读取、save-report 持久化、baseline/历史对比、mixed 状态判断、CLI 参数映射
```

V3.1-37 当前落地能力：

```text
新增 GET /recommendations/benchmark-runs 后台接口，用于读取已持久化的 Recommendation Benchmark 历史报告
接口要求 admin token 与 postgres recommendation repository，支持 benchmark_key、strategy 与 limit 查询参数
PostgresRecommendationBenchmarkRunRepository 新增 list_history，可按 benchmark_key/strategy 可选过滤最近 N 条记录
接口返回 StoredRecommendationBenchmarkRun 列表，包含核心 replay ready、settled run、final hit、ROI、warning 与 history_comparison_json
该接口仅服务内部准确性审阅、CLI/调度和后续后台工具，不进入普通用户前端，不展示策略细节，也不产生自动下注、支付或钱包能力
新增确定性测试覆盖：repository 历史查询参数、后台 API 权限、后台 API 查询合同
```

V3.1-38 当前落地能力：

```text
新增 Recommendation Benchmark Schedule Runner/CLI，用于把基准矩阵固定为可重复的周期性质量回归任务
命令入口为 nutmeg-recommendation-benchmark-schedule，支持 once、daily、weekly 三种 cadence，以及 window_count 生成多个 as_of_time
调度 runner 只负责生成时间窗并调用既有 Recommendation Benchmark Runner，不复制推荐评估、核心回放或历史对比逻辑
默认仍为 dry-run，不写审计、不持久化推荐、不触发自动下注、支付、钱包或用户侧推荐文案
只有显式 --save-report 才会让下游 benchmark report 写入 recommendation_benchmark_runs，便于日/周级历史趋势审阅
支持 pass_types、single/multiple modes、预算档位、strategy、competition/model/provider/fixture 范围、prematch pipeline、core replay 与 stop-on-error 参数透传
summary_json 输出 schedule_name、schedule_key、cadence、run_at_utc、生成的 as_of_time 列表、benchmark_key、scenario/completed/failed 数量、stored_report_id 与 history_status
README 增加本地/cron 使用示例，定位为内部准确性回归工具，不进入普通用户前端，也不展示采用了什么策略
新增确定性测试覆盖：daily/weekly/once 时间窗生成、调度 runner 参数透传、summary 包装、CLI 参数映射
```

V3.1-39 当前落地能力：

```text
新增 Recommendation Benchmark Quality Gate/CLI，用于对已持久化的 benchmark 历史报告做内部准确性门禁判断
命令入口为 nutmeg-recommendation-benchmark-gate，读取 recommendation_benchmark_runs，不新增推荐逻辑、不写用户侧推荐、不触发自动下注、支付或钱包能力
门禁支持 benchmark_key、strategy 与 history_limit 过滤，默认读取最近 2 条报告，用最新报告作为当前质量判断对象
默认严格要求存在历史、scenario_count 至少为 1、completed_ratio 为 1.0、failed_count 为 0，并将 history_status=regressed 视为失败
可配置 max_warning_count、min_core_replay_ready_ratio、min_final_hit_sample_size、min_final_hit_rate、min_average_core_replay_roi 等门槛
输出 JSON report，包含 latest/previous benchmark run、各项 check、failed_checks、warning、history_status、final_hit_rate、ROI 与 calculation_basis
CLI 在门禁失败时返回非零退出码，可用于 cron/CI 识别准确性回归；--no-fail-process 可只打印报告
该能力只服务内部质量回归，不进入普通前端，不向用户展示采用了什么策略或门禁细节
新增确定性测试覆盖：健康报告通过、阈值失败、history_status 回归失败、缺失历史严格/宽松模式、CLI 参数映射
```

V3.1-40 当前落地能力：

```text
新增 Recommendation Benchmark Cycle Runner/CLI，用于把周期 benchmark 与 quality gate 串成一条内部准确性回归命令
命令入口为 nutmeg-recommendation-benchmark-cycle，先调用 Recommendation Benchmark Schedule Runner，再按生成的 benchmark_key 调用 Recommendation Benchmark Quality Gate
cycle runner 不新增推荐计算逻辑、不复制核心回放/历史对比逻辑，只负责执行顺序、参数透传、summary 汇总与失败退出码
默认仍不持久化推荐、不触发自动下注、支付、钱包或用户侧推荐文案；--save-report 只会让 benchmark report 写入 recommendation_benchmark_runs
未使用 --save-report 时，cycle 会明确输出 gate_reads_existing_history_without_current_saved_report warning，避免误以为门禁评估的是刚刚生成的未保存报告
支持 schedule 参数：once/daily/weekly、window_count、pass_types、single/multiple modes、预算、strategy、competition/model/provider/fixture 范围、prematch pipeline 与 core replay
支持 gate 参数：history_limit、completed_ratio、failed/warning 上限、core replay ready ratio、final hit 样本量、final hit rate、平均 ROI 与 fail history status
CLI 在 gate 失败时默认返回非零退出码，--skip-gate 可只跑 schedule，--no-fail-process 可只输出 JSON 报告
该能力定位为内部 cron/CI 质量回归，不进入普通前端，不向用户展示策略、门禁或复杂诊断细节
新增确定性测试覆盖：schedule->gate 串联、当前 benchmark_key 透传、gate 失败导致 cycle 失败、未保存报告 warning、skip gate 与 CLI 参数映射
```

V3.1-41 当前落地能力：

```text
新增 Recommendation Benchmark Baseline Preflight/CLI，用于在真实 Postgres 样本基线运行前做只读准备检查
命令入口为 nutmeg-recommendation-benchmark-preflight，默认检查数据库连接、recommendation_benchmark_runs、recommendation_runs、候选池快照、prediction/odds/fixtures/results 等关键表
preflight 不写数据库、不生成推荐、不触发自动下注、支付、钱包或用户侧推荐文案
当数据库不可连接、角色缺失或必需表缺失时，输出 blocked JSON，而不是让运维看到裸 traceback
当 benchmark history 为空但 schema 已准备好时，输出 warning，表示可以创建第一份 saved baseline
支持配置 required_tables、min_benchmark_history_count、关闭空历史 warning，以及 --no-fail-process 只打印报告
本地默认 Postgres 连接最初阻塞在 role nutmeg does not exist；后续 V3.1-42 已完成本地角色/数据库创建、迁移应用与空库基线验证
新增确定性测试覆盖：ready、空历史 warning、缺表 blocked、连接失败 blocked、CLI 参数映射
```

V3.1-42 当前落地能力：

```text
完成本地 Postgres 基线准备：创建 localhost nutmeg role/database，使用 psql -f 顺序应用 db/migrations/0001-0041
修复真实 PostgreSQL 下 optional filter NULL 参数类型推断问题，覆盖 benchmark history、推荐候选读取、lifecycle replay、推荐评估、provider incident、parlay、Dixon-Coles 训练/evidence 与 calibration evidence 查询
修复 accuracy postgres smoke migration splitter，支持 SQL 字符串、注释、双引号标识符与 dollar-quoted block 内部的分号，避免迁移 0023 一类 seed 文案触发错误拆分
本地 preflight 已达到 ready：连接成功，关键 benchmark/recommendation/prediction/odds/fixtures/results 表存在，benchmark history 可读
本地空库 benchmark-cycle --save-report 已能完成 scenario 并写入 recommendation_benchmark_runs；质量门禁失败点回到预期的样本不足：core_replay_ready_ratio=0、final_hit_sample_size=0
当前 fixtures、results、odds_snapshots、feature_snapshots、prediction_snapshots、recommendation_runs 与 candidate pool 仍为空，因此这不是准确性基线，只是 schema/runner/门禁链路基线
README 增加本地 Postgres fresh baseline bootstrap、preflight 与 local-empty-smoke cycle 命令
新增/更新确定性测试覆盖：migration splitter 的 quoted semicolon 与 dollar block；推荐 replay/benchmark/preflight/evaluation/provider incident/parlay 相关回归测试
```

V3.1-43 当前落地能力：

```text
新增 Recommendation Baseline Seed/CLI，用于显式生成本地确定性足球样本，而不是把样本写入 schema migration
命令入口为 nutmeg-recommendation-baseline-seed，默认 as_of_time 为 2026-05-12T00:00:00Z，写入 BENCH_V3 赛事、8 场 fixture、16 支本地 team、8 个 feature snapshot、8 个 prediction snapshot、24 条 1X2 odds snapshot 与 8 条 result
seed 使用 poisson-v3.1-baseline / features-v3.1-baseline / calibration-v3.1-baseline，并保留 Dixon-Coles v1.5 兼容 metadata
seed 默认 reset：清理 seeded fixture IDs 对应的 prediction/odds/result/recommendation run 子表，再重写样本；不会删除 benchmark history，避免丢失基准报告证据
样本 fixture 在 as_of_time 查询中保持 scheduled/beta 可推荐状态，同时写入确定性 result rows 给 core replay 使用；该设计仅用于本地回归证据，不代表真实生产时间状态
本地 committed seeded 2x1 smoke 已通过：scenario_count=1，completed=1，core_replay_ready=1，final_hit_sample_size=1，final_hit_count=1，quality gate passed
本地 committed seeded 单式矩阵已通过：2x1/4x1/6x1/8x1 共 4 个 scenario，completed=4，core_replay_ready=4，final_hit_sample_size=4，final_hit_count=4，quality gate passed
本地 committed seeded 复式 smoke 已通过：2x1/4x1 multiple 共 2 个 scenario，completed=2，core_replay_ready=2，final_hit_sample_size=2，final_hit_count=2，quality gate passed
preflight --min-benchmark-history-count 1 已 ready，本地 benchmark history 可读；最新 seeded reports 为 recommendation_benchmark_run_id 10 和 11
README 增加 baseline seed、单式矩阵 baseline 与复式 smoke 命令
新增确定性测试覆盖：seed reset、完整 fixture->feature->prediction->odds->result 写入链、CLI 参数映射
```

V3.1-44 当前落地能力：

```text
Recommendation Baseline Seed 新增 profile 参数，默认 happy_path 保持旧行为，新增 mixed_outcomes 用于本地命中/失误混合回归样本
mixed_outcomes 保持同一组 BENCH_V3 fixture、lambda 与 prediction snapshot 结构，仅翻转部分 deeper legs 的 settled result，使短串与长串、单式与复式出现不同结算表现
seed result 与 summary_json 记录 profile，competition/fixture/feature payload 写入 seed_profile，便于后续审计当前样本来源
seed 默认 reset 现在清理所有已知 seeded profile fixture IDs 对应的 prediction/odds/result/recommendation run 子表，避免 profile 切换留下旧推荐 run
CLI 支持 --profile happy_path|mixed_outcomes；README 增加 mixed stress seed 与 benchmark-cycle 命令
本地 mixed_outcomes 单式矩阵已执行：2x1/4x1/6x1/8x1 共 4 个 scenario，completed=4，core_replay_ready=4，final_hit_sample_size=4，final_hit_count=2，history_status=regressed；quality gate 按预期因 history_status=regressed 失败，用于证明历史门禁能发现准确性退化
本地 mixed_outcomes 复式 smoke 已执行：2x1/4x1 multiple 共 2 个 scenario，completed=2，core_replay_ready=2，final_hit_sample_size=2，final_hit_count=2，history_status=improved，quality gate passed；该结果说明复式保护在反向赛果样本中可以捕捉部分备选结果
新增确定性测试覆盖：mixed profile 赛果翻转、summary profile、CLI profile 参数映射；默认 happy_path 测试保持兼容
```

V3.1-45 当前落地能力：

```text
Recommendation Baseline Seed 继续扩展 profile：新增 upset_stress、low_quality_filter、missing_result 三类核心边界样本
upset_stress 翻转强热门 fixture 的 settled result，用于检验短串/长串在冷门赛果下的命中差异；本地 smoke 结果为 2x1 命中、4x1 未命中，core_replay_ready=2/2
low_quality_filter 将 bench_v3_001 与 bench_v3_003 的 data_quality_score 降至默认阈值以下，用于验证推荐候选过滤后仍能从剩余高质量池生成 6x1；本地 smoke 结果为 6x1 completed，core_replay_ready=1/1
missing_result 保留 fixture、prediction 与 odds，但故意不写 bench_v3_004 与 bench_v3_008 的 result rows，用于验证 core replay 对缺赛果/未结算状态的处理；本地 smoke 结果为 4x1 completed，但 core_replay_ready=0，final_hit_sample_size=0
RecommendationBaselineSeedFixture 支持 result 缺失场景，actual_home_goals/actual_away_goals 必须成对出现；缺赛果时 odds 可使用 odds_anchor_outcome 保持候选可生成
seed summary_json 新增 missing_result_fixture_ids；fixture aggregate_context_json 记录 result_available，便于排查当前样本是否完整可结算
README 增加全部 seed profile 说明与 edge-profile smoke 示例；本地 smoke 后已把 seeded 数据恢复为 happy_path，避免后续开发被缺结果样本误导
新增确定性测试覆盖：upset_stress 冷门翻转、low_quality_filter 阈值过滤样本、missing_result 跳过 result row 与 summary payload
```

V3.1-46 当前落地能力：

```text
Prematch Recommendation Lifecycle Backtest 增强跨日延续载荷，用于明确区分已锁定/已开赛腿与仍需后续动态计算的剩余腿
stage 新增 started_locked_fixture_ids，记录用户已保留且在当前 checkpoint 已开赛的 fixture，系统保留它们作为用户约束，不再把它们当作可替换候选
stage 新增 continuation_fixture_ids 与 remaining_open_leg_count，表示当前推荐中仍要参与后续赛前重算的未锁定 fixture；例如 6x1 中 A/B 已确认后，C/D/E/F 会作为 continuation_fixture_ids 输出
event_codes 新增 started_locked_fixtures_retained 与 remaining_fixtures_continue，便于内部回放报告识别“已确认腿被保留”和“剩余腿继续计算”这两类生命周期事件
explanation_json.continuation 记录 pass_type、total_leg_count、locked_fixture_ids、started_locked_fixture_ids、continuation_fixture_ids 与 remaining_open_leg_count，作为后台审计/回测载荷，不要求普通用户前端展示
summary_json 新增 started_locked_stage_count、continuation_stage_count、final_continuation_fixture_ids 与 final_remaining_open_leg_count，用于周期性赛前变化报告读取跨日延续结果
已更新确定性测试：A/B 在 1 号开赛并被保留后，2 号 checkpoint 仍保留 A/B，同时把 C/D/E/F 标为剩余 4 腿继续计算；突发排除与已锁定突发告警场景也验证 continuation payload
```

V3.1-47 当前落地能力：

```text
Persisted Recommendation Lifecycle Replay 接入 continuation 载荷，使真实 recommendation_runs 回放也能记录“已确认腿保留 + 剩余腿继续计算”
Persisted stage 新增 started_locked_fixture_ids、continuation_fixture_ids 与 remaining_open_leg_count；若持久化候选包含 kickoff_time_utc，则已开赛锁定腿会被识别为 started_locked_fixture_ids
Persisted event_codes 新增 started_locked_fixtures_retained 与 remaining_fixtures_continue，和内存 Prematch Lifecycle Backtest 保持语义一致
Persisted explanation_json.continuation 记录 pass_type、total_leg_count、locked_fixture_ids、started_locked_fixture_ids、continuation_fixture_ids 与 remaining_open_leg_count，进入后台报告 JSON，不要求普通前端展示
Persisted replay summary_json 新增 started_locked_stage_count、continuation_stage_count、final_continuation_fixture_ids 与 final_remaining_open_leg_count
Recommendation Prematch Change Report summary_json 读取并透出上述 continuation 指标；report_key 纳入 continuation_stage_count 与 final_remaining_open_leg_count，避免不同延续状态覆盖为同一报告
持久化表结构无需新增列，continuation 明细通过 report_json 保存；现有 stage_count、changed_stage_count、incident_count 与 locked_preservation_stage_count 列继续作为索引化摘要
新增确定性测试覆盖：真实 run replay 的 continuation 载荷、started locked 识别、prematch report summary 持久化 JSON 包含 continuation 指标
```

V3.1-48 当前落地能力：

```text
后台 POST /recommendations/prematch-change-report API 合同测试补充 continuation 验证，确认 response_model 不会丢弃 persisted replay stage 与 summary_json 中的 continuation 字段
API 集成测试模拟返回 started_locked_fixture_ids、continuation_fixture_ids 与 remaining_open_leg_count，并断言 JSON 响应完整透出 stage 级和 summary 级 continuation 载荷
完成本地 Postgres persisted report smoke：先用 happy_path seed 临时生成 1 个 6x1 committed recommendation run，再调用后台 prematch-change-report API dry_run
本地 smoke 结果：HTTP 200，stage_count=1，continuation_stage_count=1，final_remaining_open_leg_count=6，final_continuation_fixture_ids 为 6 个 BENCH_V3 fixture
smoke 后再次运行 happy_path seed reset 清理临时 recommendation_runs；本地数据库恢复为 0 个 recommendation_runs、8 个 bench fixture、8 条 result，避免后续测试受到污染
该阶段验证的是后台 API/报告证据链，不改变普通用户前端展示，也不引入自动下注、钱包、支付或保证盈利措辞
```

V3.1-49 当前落地能力：

```text
新增后台 API 链路合同测试：POST /recommendations/global-best 生成持久化 6x1，连续调用 POST /recommendations/{id}/lock-leg 保留 A/B，再调用 POST /recommendations/prematch-change-report 验证剩余 C/D/E/F continuation
测试使用共享 fake repository state，覆盖生成接口返回 stored_run、锁定接口写入 locked_fixture_ids、报告接口透出 locked_preservation_stage_count、continuation_stage_count 与 final_remaining_open_leg_count=4
完成本地 Postgres deterministic seed 真实 smoke：happy_path 生成 committed 6x1 run，锁定 bench_v3_001 与 bench_v3_003 后，prematch-change-report dry_run 返回 HTTP 200
真实 smoke 结果：locked_preservation_stage_count=1，continuation_stage_count=1，final_remaining_open_leg_count=4，final_continuation_fixture_ids 为剩余四个 BENCH_V3 fixture
smoke 后再次运行 happy_path seed reset，确认 recommendation_runs=0、BENCH_V3 fixture=8、result=8，本地库恢复干净
该阶段仍然只验证推荐生命周期和后续重算约束，不暴露策略细节给普通用户，不触发自动下注、支付、钱包或保证盈利措辞
```

V3.1-50 当前落地能力：

```text
新增 Recommendation Successor Recompute Runner，用于从已持久化源 recommendation_run 生成下一版推荐答案，而不是只在报告里展示 continuation 状态
新增 POST /recommendations/{id}/successor-recompute 后台接口，要求 admin token 与 postgres recommendation repository；dry_run=false 时会保存 successor recommendation run
successor runner 通过 PersistedRecommendationLifecycleReplayRepository 按 recommendation_run_id 读取源 run、候选池、生命周期事件与 locked legs
锁定腿按 fixture_id + market_type + outcome 精确保留；若只有 locked_fixture_ids_json 而缺少 locked_leg 细节，则回退到源 run/候选池中的首个同 fixture 候选，并输出 locked_candidate_unavailable warning 保护异常场景
successor runner 复用源 candidate_query_json、pass_type、mode、unit_stake、max_budget、competition_id、model_version 与筛选阈值；请求可覆盖 pass_type/mode/strategy/unit_stake/max_budget，并可追加 excluded_fixture_ids
生成时通过 RecommendationGenerationOptions.locked_candidates 把 A/B 作为硬约束交回现有 Recommendation Engine/Optimizer，避免复制一套推荐逻辑
返回结果包含 source_recommendation_run_id、source_run_key、source_selected_fixture_ids、locked_fixture_ids、continuation_fixture_ids、generated_recommendation_run_id 与 generation_result
successor internal_trace 写入 source run、源选择、锁定腿、排除项与 calculation_basis=locked_leg_successor_recompute_v3_1，供后台审计，不要求普通用户前端展示策略
修复 incident recompute 的锁定候选解析，使其也优先按 locked leg 的 market/outcome 精确保留，而不是只按 fixture 粗略匹配
完成本地 Postgres deterministic seed 真实 smoke：happy_path 生成 committed 6x1 source run，锁定 bench_v3_001 与 bench_v3_003 后调用 successor-recompute dry_run=false，生成 successor run
真实 smoke 结果：source_run_id=28，successor_run_id=29，locked_fixture_ids=2，continuation_fixture_ids=4，answer_status=ready，answer_fixture_count=6；随后 happy_path reset 清理 recommendation_runs=0、BENCH_V3 fixture=8、result=8
新增确定性测试覆盖：successor 精确保留 locked leg market/outcome、source missing warning、API response 合同、原 recompute-trigger 锁定腿回归
该阶段仍然不引入自动下注、支付、钱包、保证盈利或向普通用户展示策略细节
```

V3.1-51 当前落地能力：

```text
Recommendation Recompute Trigger 新增 trigger_locked_successors 选项；默认 false，保持普通 /recommendations/recompute-trigger 的 incident-only 触发语义不变
Recommendation Prematch Pipeline 新增 trigger_locked_successors 选项；默认 true，使赛前流水线能在源 run 存在 active locked legs 时生成 successor run，即使没有 provider incident 命中
当 trigger_locked_successors=true 且源 run 有可解析 locked_candidates、但没有 active incident 时，recompute decision action=triggered，reason_codes=["locked_successor_recompute","locked_fixtures_preserved"]
locked successor generation 继续复用 RecommendationGenerationOptions.locked_candidates，不复制推荐逻辑；dry_run=false 时会保存 successor recommendation run，并把 generated_recommendation_run_ids 汇入 trigger/pipeline result
recompute-trigger 的 successor internal_trace 写入 successor_recompute 节点，包含 source_recommendation_run_id、source_run_key、source_selected_fixture_ids、locked_fixture_ids 与 calculation_basis=locked_leg_successor_recompute_v3_1
Persisted Recommendation Lifecycle Replay 识别 successor_recompute trace，stage event_codes 新增 successor_recompute_generated，summary_json 新增 successor_recompute_stage_count 与 final_successor_source_recommendation_run_id
API 请求模型已暴露 trigger_locked_successors：recompute-trigger 默认为 false，prematch-pipeline 默认为 true，避免后台手工 trigger 与赛前流水线语义混淆
完成本地 Postgres pipeline smoke：happy_path 生成 committed 6x1 source run，锁定 bench_v3_001 与 bench_v3_003 后运行 prematch pipeline，run_provider_incident_mapping=false、run_recompute_trigger=true、run_prematch_change_report=false、trigger_locked_successors=true、dry_run=false
真实 smoke 结果：source_run_id=30，checked=1，triggered=1，skipped=0，generated=[31]，reason_codes=["locked_successor_recompute","locked_fixtures_preserved"]，locked=["bench_v3_001","bench_v3_003"]；随后 happy_path reset 清理 recommendation_runs=0、BENCH_V3 fixture=8、result=8
新增确定性测试覆盖：无 incident 但有 locked legs 时 trigger 生成 successor、pipeline 传递 trigger_locked_successors、API 合同默认值、persisted replay 识别 successor source evidence
该阶段仍然不引入自动下注、支付、钱包、保证盈利或向普通用户展示策略细节
```

V3.1-52 当前落地能力：

```text
Recommendation Evaluation 与 Strategy Governance 接入 successor/source 有效版本口径，避免源 run 已生成 successor 后继续被计入待评估或策略证据样本
pending evaluation 查询会跳过被非 invalidated successor 覆盖的 source recommendation_run，历史 evaluation 列表也默认排除这些 source run
策略治理 SQL 在读取 settled recommendation_run_evaluations 时同步排除 superseded source run，避免 auto 策略选择被重复样本污染
Recommendation Core Replay 保留完整 source->successor 链路审计，但命中率、ROI、strategy_metrics、post-match settled check 与 quality gate summary 只统计有效 leaf run
Core Replay summary 新增 effective_evaluated_run_count、superseded_source_run_count 与 superseded_source_recommendation_run_ids，并将 calculation_basis 标记为 effective_leaf_recommendation_core_replay_v3_1
新增 0042 expression index 支持按 explanation_json.internal_trace.successor_recompute.source_recommendation_run_id 查找 successor source，提高真实 Postgres 历史样本读取效率
新增确定性测试覆盖：core replay 不重复统计 source/successor、evaluation/governance SQL 排除 superseded source、迁移合同
该阶段不改变普通用户前端展示，不引入自动下注、支付、钱包、保证盈利或向用户解释内部策略
```

V3.1-53 当前落地能力：

```text
新增 Recommendation Chain Integrity，只读检查 source -> successor 推荐链完整性，服务后台质量诊断和准确性闭环
新增 POST /recommendations/chain-integrity 后台接口，要求 admin token 与 postgres recommendation repository，不进入普通用户前端展示
链路检查读取指定时间窗内 recommendation_runs，并自动补读窗口内 successor 引用的 source run，避免跨窗口 source 被误报缺失
报告输出 nodes、issues 与 summary_json，包含 root_recommendation_run_ids、leaf_recommendation_run_ids、superseded_source_recommendation_run_ids、edge_count 与 ready
完整性 issue 覆盖 successor_source_missing、successor_self_reference、successor_before_source、multiple_active_successors、source_status_not_superseded 与 successor_cycle_detected
source_status_not_superseded 作为 warning 输出 recommended_status=superseded，但本阶段不直接批量修改历史 run 状态，避免误改用户已确认上下文
multiple_active_successors、missing source、self reference 与 cycle 作为 critical，使 quality gate/人工诊断可以阻断不可信推荐链样本
新增确定性测试覆盖：leaf run 统计、source 状态同步告警、重复 successor、缺失 source、循环检测、Postgres repository 查询与 API 合同
该阶段仍然不引入自动下注、支付、钱包、保证盈利或向普通用户解释内部策略
```

V3.1-54 当前落地能力：

```text
Recommendation Core Validation Runner 默认接入 chain-integrity，Global Best / Prematch Pipeline / Core Replay 后会同步检查 source->successor 链路可信度
Core Validation summary_json 新增 chain_integrity_ready、chain_integrity_issue_count、chain_integrity_critical_issue_count、chain_integrity_warning_issue_count 与 chain_integrity_source_status_sync_required_count
Core Validation warnings 会把 critical chain issue 写成 chain_integrity:critical:<code>，使内部 runner 能快速定位阻断原因；普通 source 状态同步建议仍保留为 summary warning 指标
Benchmark Runner 聚合每个 scenario 的 chain integrity 指标，summary_json 新增 chain_integrity_ready_count、chain_integrity_total_issue_count、chain_integrity_total_critical_issue_count 与 chain_integrity_source_status_sync_required_count
Benchmark Schedule 与 Benchmark Cycle CLI 增加 --skip-chain-integrity 与 --chain-integrity-limit，默认启用链路完整性检查
Benchmark Quality Gate 新增 chain_integrity_ready_ratio 与 chain_integrity_critical_issue_count 检查；默认 max_chain_integrity_critical_issue_count=0，critical 链路问题会阻断准确性基线
Benchmark Quality Gate / Cycle CLI 增加 --min-chain-integrity-ready-ratio 与 --max-chain-integrity-critical-issue-count，支持 CI/cron 按内部阈值阻断
新增确定性测试覆盖：core validation 调用 chain integrity、critical issue 写入 warning、benchmark 汇总 chain 指标、quality gate 阻断 critical issue、CLI 参数映射
该阶段仍然不引入自动下注、支付、钱包、保证盈利或向普通用户解释内部策略
```

V3.1-55 当前落地能力：

```text
新增 Recommendation Source Status Sync 内部修复器，用于把已存在有效 successor 的 source recommendation_run 状态补齐为 superseded
修复器默认 dry_run=true，只输出候选 source、successor ids、warning 与 summary；只有显式 dry_run=false 的后台调用才会写入 lifecycle mutation
写入前会先运行 chain-integrity；如存在 missing source、multiple active successor、self reference 或 cycle 等 critical issue，则阻断所有状态变更并返回 skipped source ids
状态同步范围限定为 current/locked -> superseded，candidate 等状态只输出 warning，不做自动修复，避免误改仍未进入最终推荐生命周期的样本
每次 commit 通过 PostgresRecommendationRepository.transition_run_status 记录 recommendation_lifecycle_events，并把 successor_recommendation_run_ids、previous_status 与 calculation source 写入 metadata_json
新增 POST /recommendations/source-status-sync 后台接口，要求 admin token 与 postgres recommendation repository，不进入普通用户前端展示
新增确定性测试覆盖：dry-run 不写入、commit 同步 current/locked、critical 链路问题阻断、candidate 状态跳过、API 合同
该阶段仍然不引入自动下注、支付、钱包、保证盈利或向普通用户解释内部策略
```

V3.1-56 当前落地能力：

```text
Recommendation Source Status Sync 新增内部 CLI：nutmeg-recommendation-source-status-sync
CLI 参数覆盖 window_start/window_end、pass_type、single/multiple mode、strategy、limit、event_time、allowed_source_statuses 与 reason_code，便于 cron/人工运维重复执行同一窗口检查
CLI 默认 dry-run，只打印 JSON 报告；只有显式 --commit 才调用 source status sync 写入 lifecycle mutation
当 chain-integrity critical issue 阻断同步时，CLI 默认以非零退出码结束；--no-fail-process 可用于只输出报告的人工诊断场景
pyproject project.scripts 注册该命令，README 增加 dry-run 用法，继续要求先审阅输出再 commit
新增确定性测试覆盖：CLI 参数到 RecommendationSourceStatusSyncOptions 的映射、默认 dry-run 与 --commit 行为
该阶段仍然不引入自动下注、支付、钱包、保证盈利或向普通用户解释内部策略
```

V3.1-57 当前落地能力：

```text
Recommendation Baseline Seed 新增 adverse_odds profile，用于测试“模型概率高但市场价格不支持”的核心价值判断
adverse_odds 保持 BENCH_V3 fixture、lambda、prediction snapshot 与 settled result 结构不变，只调整 1X2 odds_anchor_outcome，使模型热门腿的 odds fair_probability 高于模型概率并形成负 model_edge
该 profile 能服务 value_first / min_model_edge / ROI gate 的本地压力测试，防止推荐逻辑把高概率腿自动视为好答案
fixture aggregate_context_json 记录 odds_anchor_outcome，便于回看当前样本是否属于赔率逆风压力场景
README stress profile 列表新增 adverse_odds 说明；baseline seed CLI choices 自动包含该 profile
新增确定性测试覆盖：profile 构造、热门腿 odds fair_probability > market_prediction probability、draw 锚点的反向 repricing、CLI profile 映射
该阶段仍然不引入自动下注、支付、钱包、保证盈利或向普通用户解释内部策略
```

V3.1-58 当前落地能力：

```text
新增 strategy-aware recommendation policy builder，使 value_first 不再只是透传标签，而是真正采用价值优先候选筛选与排序
value_first 在请求未显式设置 min_model_edge 时默认使用 min_model_edge=0.0，过滤负 model_edge 候选，避免把高概率但价格不支持的腿选入推荐
value_first 提高 model_edge 权重、降低 raw probability 权重；accuracy_first 保持既有概率质量优先权重，确保两类策略在 adverse_odds 样本下会产生可观察分化
Recommendation Generation 与 Global Planner 均接入 strategy-aware policy builder；普通用户前端仍不展示采用了什么策略
新增确定性测试覆盖：value_first 过滤负 edge、偏向价格质量；Global Planner 在同一候选池中让 accuracy_first 选择热门腿、value_first 选择正 edge 替代腿
该阶段仍然不引入自动下注、支付、钱包、保证盈利或向普通用户解释内部策略
```

V3.1-59 当前落地能力：

```text
新增 Recommendation Benchmark Strategy Comparison，用于比较已持久化 benchmark history 中 candidate strategy 与 baseline strategy 的最新报告
命令入口为 nutmeg-recommendation-benchmark-strategy-compare，默认比较 value_first 对 accuracy_first，并以 ROI delta >= 0 作为内部证据门槛
支持 benchmark_key、candidate_benchmark_key、baseline_benchmark_key、history_limit、min_final_hit_sample_size、min_final_hit_rate_delta 与 matrix match 开关
由于 benchmark_key 现有设计包含 strategy，对比器支持 candidate/baseline 分别指定 key，同时默认校验两边 as_of_times、pass_types、modes、budgets、scenario_count 与 dry_run 一致
输出 JSON report，包含 candidate/baseline run id、strategy、hit rate、ROI、delta、matrix payload、failed_checks 与 calculation_basis
新增确定性测试覆盖：value_first ROI/hit-rate 优于 accuracy_first 时通过、矩阵不一致时失败、缺少历史时 insufficient_history、CLI 参数映射
该阶段仍然不改变普通用户推荐响应，不展示采用了什么策略，不引入自动下注、支付、钱包或保证盈利表述
```

V3.1-60 当前落地能力：

```text
新增 Recommendation Benchmark Strategy Pair Runner，用于在同一 benchmark schedule matrix 下连续运行 baseline strategy 与 candidate strategy，并立即生成策略对比报告
命令入口为 nutmeg-recommendation-benchmark-strategy-pair，默认 baseline=accuracy_first、candidate=value_first，适合 adverse_odds 等本地压力样本的可复跑证据生成
Pair Runner 复用 Recommendation Benchmark Schedule，两次运行会冻结同一个 run_at_utc、pass_types、modes、budgets、lookback 与过滤条件，只替换 strategy
当 --commit --save-report 打开时，两边 benchmark report 会持久化到 recommendation_benchmark_runs；未保存时仍可用当前结果做 dry-run smoke，并在 warnings 标记 using_unsaved_current_report
Pair Runner 内部复用 Strategy Comparison，默认要求 matrix match，并输出 pair_key、baseline/candidate benchmark_key、stored_report_id、comparison_status、failed_checks 与 calculation_basis
新增确定性测试覆盖：同矩阵双策略运行、未保存当前结果对比 warning、ROI delta 门槛失败、CLI 参数映射
该阶段仍然不改变普通用户推荐响应，不展示采用了什么策略，不接自动下注、支付、钱包或保证盈利表述
```

V3.1-61 当前落地能力：

```text
新增 recommendation_benchmark_strategy_pair_runs 迁移，用于持久化 Strategy Pair Runner 的内部对比报告历史
Pair Runner 新增 save_pair_report 配置与 CLI 参数 --save-pair-report；开启后会保存 pair_key、baseline/candidate strategy、两边 benchmark_key、stored_report_id、comparison_key、ROI delta、hit-rate delta、matrix_match、failed_checks、summary_json 与 result_json
新增 PostgresRecommendationBenchmarkStrategyPairRunRepository，支持保存 pair result，并按 pair_key、baseline_strategy、candidate_strategy 读取最近历史
新增 GET /recommendations/benchmark-strategy-pairs 后台只读接口，要求 admin token 与 postgres recommendation repository，不进入普通用户前端展示
README 增加 --save-pair-report 与 pair history API 示例，强调这是内部准确性证据链，不改变普通推荐响应
新增确定性测试覆盖：pair report 保存、Postgres repository 写入/读取、迁移 contract、admin token 拦截、后台 history API 参数透传与响应 payload
该阶段仍然不接自动下注、支付、钱包，不展示内部策略给普通用户，不引入保证盈利表述
```

V3.1-62 当前落地能力：

```text
新增 Final Answer Arbitrator，用于在 Global Planner 生成的 1x1、2x1-8x1、single/multiple、让球、比分等预算内候选之间做最终答案仲裁
仲裁器按 EV/ROI、命中概率、风险、数据质量、预算效率、关数深度与答案类型计算 final_answer_score，而不是只按原 planner_score 或单一概率排序
Global Planner 现在使用 rank_final_answer_options 生成 best_option 与 alternatives，并在 best_option/selection.explanation_json 中记录 final_answer_arbitration 内部审计 payload
final_answer_arbitration 不包含 strategy、strategy_selection 或 internal_trace；普通 public response 仍不会暴露内部策略标签
非 dry-run global planner 保存时，会把 final_answer_arbitration 写入 internal_trace，便于赛后审计最终答案为什么被选中，但不作为用户推荐理由展示
新增确定性测试覆盖：正 EV 串关可战胜负 EV 高概率单式、超预算/规则无效候选排到最后、比分市场可进入仲裁且 payload 不包含 strategy、Global Planner 写入 rank=1 仲裁 payload
该阶段属于“最终答案仲裁器”主线，不接自动下注、支付、钱包，不引入保证盈利表述
```

V3.1-63 当前落地能力：

```text
预算内最优复式裁剪从单项最低分删除升级为预算约束下的组合质量搜索
当复式总注额超过 max_budget 时，优先在可移除 outcome 子集中精确搜索预算内最高质量保留方案；候选规模过大时才回退到逐步贪心投影
裁剪目标保留 locked_outcomes，不删除用户已保留/确认的 outcome，并保持每场至少一个 outcome
优化结果新增 optimization_basis、original_quality_score、optimized_quality_score、quality_score_delta 与 removed option 投影指标
removed option 现在记录 marginal_quality_loss、projected_quality_score、projected_total_stake、projected_hit_probability、projected_expected_value、projected_roi，便于后续真实回测评估裁剪是否提升最终答案
Optimizer 的 budget_adjustment payload 记录上述内部质量指标，但普通用户路径仍应只展示预算内结果、注数、金额和必要风险提示，不展示内部策略细节
新增确定性测试覆盖：组合质量搜索会保留预算内质量更高的复式子组合，而不是只按单个 outcome 的赔率/概率代理分删除
该阶段属于“预算内最优复式裁剪”主线，不接自动下注、支付、钱包，不引入保证盈利表述
```

V3.1-64 当前落地能力：

```text
新增 Recommendation Upset Policy，把冷门信号拆成 protection_score 与 avoidance_penalty
draw_overlooked、underdog_protection、handicap_protection 等方向会提升保护质量；favorite_fragility_avoidance 会降低热门方向推荐分
policy.score_candidate 不再简单把 upset_protection_score 全部当作正向加分，而是结合 outcome、赔率、model_edge、odds_stability、volatility 与 metadata_json 中的 upset_score / favorite_fragility_score / target_outcome 判定冷门方向
single/upset focus policy、普通候选排序、复式 optimizer、Global Planner 与 Final Answer Arbitrator 均接入同一套 aggregate_upset_quality
复式 optimizer 的 explanation_json.upset_policy 记录内部冷门质量、保护方向和热门脆弱避雷指标，用于回放/回测，不作为用户推荐理由展示
Final Answer Arbitrator 的 score_components 新增 upset_quality；final_answer_arbitration 内部 payload 记录冷门质量审计信息但不暴露 strategy/internal_trace
新增确定性测试覆盖：热门脆弱高概率选项被避开、draw protection 可胜过脆弱热门、optimizer/final arbitrator 会写入冷门质量 payload
该阶段属于“冷门能力强化”主线，不接自动下注、支付、钱包，不引入保证盈利表述
```

V3.1-65 当前落地能力：

```text
新增 Historical Recommendation Backtest，不依赖数据库 seed 或实时 provider API，可直接读取冻结历史切片 JSON
历史切片 schema 包含 fixture、真实赛果、赛前 prediction_time、model/feature/calibration version、冻结赔率、模型概率、data_quality 与冷门 metadata
新增 Euro 2024 knockout sample：赛果来自 UEFA 公开记录，赔率/概率为本地冻结样本，用于验证推荐逻辑而不是宣称 provider 真实赔率
runner 会把历史切片转换为 RecommendationCandidate，复用现有 policy、复式 optimizer 与 Final Answer Arbitrator，再按真实赛果结算 atomic bets
输出 final_hit_rate、实际 return、P/L、ROI、mean_calibration_error、Brier score、log loss、upset_opportunity_count、upset_capture_count 与 upset_capture_rate
新增 CLI：nutmeg-recommendation-historical-backtest，可指定 pass_types、single/multiple、预算、单位金额和 upset threshold
新增确定性测试覆盖：真实结果切片加载、冷门保护命中捕捉、失败串关 ROI=-1 与校准/Brier 计算
该阶段属于“真实历史样本回测”主线，不接新免费 API，不接自动下注、支付、钱包，不引入保证盈利表述
```

V3.1-66 当前落地能力：

```text
新增 Recommendation Effective Chain 纯模型，用于把 source -> successor -> successor 视为同一条推荐生命周期的有效评估口径
Effective Chain 会输出 root、leaf、effective_leaf、superseded_source、invalidated_successor 与 ambiguous_successor_source ids，作为内部评估审计 payload
Core Replay 改为按 effective_leaf_recommendation_run_ids 统计命中率、ROI、settled_run_count 与 strategy_metrics，避免多跳 successor 链重复计入准确率
invalidated successor 不再把 source 排除出有效评估口径，summary 会记录 ignored_invalidated_successor_source_recommendation_run_ids 以便排查被撤销的 successor
多 active successor 仍由 Chain Integrity 作为 critical issue 阻断质量门禁；Effective Chain 只做评估样本归并，不替代链路完整性治理
新增确定性测试覆盖：多跳 successor 只评估最终 leaf、invalidated successor 不覆盖 source、ambiguous source 输出内部审计标记、parser 拒绝 bool source id
该阶段属于“Successor Chain Evaluation”主线，不改变普通用户推荐展示，不接自动下注、支付、钱包，不引入保证盈利表述
```

V3.1-67 当前落地能力：

```text
新增 Recommendation Validity Window 纯模型，用于判定 recommendation run 在某个 as_of_time 是否还能作为当前答案展示
有效期状态覆盖 valid、valid_locked、superseded、invalidated、historical、expired_kickoff 与 stale_incident
模型复用现有 status、selected fixtures、locked fixtures、candidate kickoff_time、lifecycle events 与 successor source trace，不新增数据库字段
source run 被 active successor 覆盖时标记为 superseded；invalidated successor 不会使 source 失效
任一已选 fixture 开赛后，原完整推荐标记为 expired_kickoff；若仍有未来未开赛 fixture 且 run 仍 current/locked，则标记 requires_successor_recompute
provider incident / invalidated fixture 事件影响已选 fixture 时，推荐标记为 stale_incident，并记录 incident_fixture_ids 与 valid_until
Core Replay summary 接入 validity_window_status_counts、current_answer_recommendation_run_ids、stale_recommendation_run_ids、expired_kickoff_recommendation_run_ids、stale_incident_recommendation_run_ids 与 successor_recompute_required_recommendation_run_ids
新增确定性测试覆盖：未来推荐有效至最早开赛、active successor 覆盖 source、invalidated successor 不覆盖 source、已开赛 locked run 需要 successor recompute、突发信息使推荐 stale
该阶段属于“Recommendation Validity Window”主线，不改变普通用户推荐话术，不接自动下注、支付、钱包，不引入保证盈利表述
```

V3.1-68 当前落地能力：

```text
新增 Public Final Answer Envelope，对普通用户路径只收口为 primary_answer 与最多两个必要 backup_answers
POST /recommendations/generate 与 POST /recommendations/global-best 响应新增 answer_set，answer 指向主答案，alternatives 指向公开备选答案
公开备选会过滤 unavailable、规则无效、超预算与重复答案，避免把内部搜索候选池完整暴露给用户
global-best public result 会裁剪 alternatives 至最多两个，并把 final_answer_decision_json 改写为公开摘要
公开摘要只包含评估候选数、生成候选数、被选中的 pass_type/mode/answer_type、backup_count 与 public_scope
普通用户响应继续剔除 strategy、strategy_selection、internal_trace、global_planner、final_answer_arbitration 与 upset_policy 等内部审计字段
内部 Final Answer Arbitrator、Successor Chain、Validity Window 与回放审计仍保留完整 evidence payload，用于准确率治理和赛后评估
该阶段属于“最终答案仲裁器对外收口”主线，不接自动下注、支付、钱包，不引入保证盈利表述
```

V3.1-69 当前落地能力：

```text
前端 Dashboard 与 Parlay 页面改为优先消费 answer_set，而不是自行展示完整候选搜索过程
普通路径默认只显示今日/串关最佳答案、预算、单位金额、单式/复式结构、所选腿、总金额、命中概率、风险、数据质量、模型版本、预测时间与必要备选
冷门提醒收敛为最终答案所选比赛上的高优先级提示，不再把冷门页信息整屏铺给普通用户
候选比赛、冷门摘要、参数与备选方案全部放入折叠区，保留复核能力但不干扰“一个最佳答案”的主路径
前端 API contract 新增 answer_set schema，getRecommendationEngineBundle / getGlobalBestRecommendationBundle 优先使用 public primary_answer 与 backup_answers
新增静态测试覆盖：answer_set 接入、极简答案页关键文案、Global Best 内部标签不再出现在最终答案面板
该阶段属于“前端极简答案页”主线，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-70 当前落地能力：

```text
旧 parlay mock 推荐路径从普通用户默认路径中收缩，只保留为显式开发/测试兜底
前端新增 NUTMEG_ENABLE_FRONTEND_DEV_FALLBACKS 开关；未开启时，recommendations/generate 与 recommendations/global-best 不可用会返回空答案和明确不可用提示
getParlayTickets 在 API 不可用且未开启开发兜底时不再返回本地 parlay mock tickets，避免普通前端误展示非核心推荐结果
Playwright e2e 显式开启 NUTMEG_ENABLE_FRONTEND_DEV_FALLBACKS=true，用于本地无 API 的 UI 回归验证
生产普通路径要求读取后端 answer_set；旧 /parlays/recommend 与本地 parlay mock 仅服务开发兜底、对比排查或受控测试，不作为最终答案来源
新增静态测试覆盖：开发兜底开关存在、普通路径提示未启用开发兜底、e2e 显式打开测试兜底
该阶段属于“Mock/旧路径收缩”主线，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-71 当前落地能力：

```text
周期质量门禁从基础 benchmark pass/fail 扩展为生命周期感知门禁
Core Validation 会把 Core Replay 中的 effective chain、current answer、stale、expired kickoff、stale incident 与 successor recompute required 计数向 benchmark summary 透传
Benchmark Runner 汇总 effective_chain_count、active_edge_count、effective_leaf_run_count、superseded_source_run_count、ambiguous_successor_source_count、stale_recommendation_count 与 successor_recompute_required_count
Benchmark history comparison 新增 upset_capture_rate_delta、ambiguous_successor_source_count_delta、stale_recommendation_count_delta 与 successor_recompute_required_count_delta，使趋势判断能识别最终答案准确率以外的生命周期退化
Quality Gate 新增 max_ambiguous_successor_source_count、max_stale_recommendation_count、max_successor_recompute_required_count、min_upset_capture_sample_size 与 min_upset_capture_rate 配置
Cycle Runner CLI 同步透传上述 gate 参数，便于 cron/CI 一次运行 benchmark + lifecycle/upset-aware quality gate
README 更新内部运行示例，明确该门禁用于判断系统是否真的更准、更稳定，而不是给普通用户展示策略解释
新增确定性测试覆盖：core validation 指标透传、benchmark 聚合、history comparison delta、quality gate 阻断 lifecycle/upset regression、cycle CLI 参数映射
该阶段属于“周期质量门禁升级”主线，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-72 当前落地能力：

```text
串关优化器从纯局部贪心/beam search 升级为 solver-backed 全局搜索路径
新增 select_budget_constrained_single_parlay，单式 2x1-8x1 不再只按单腿评分贪心取前 N，而会在预算内比较完整组合质量
复式 optimizer 在预算裁剪、跨比赛替换后，会先运行 budget_constrained_integer_solver；只有 solver 找到更高质量且预算内的组合时才覆盖当前路径
小规模候选矩阵使用 exact_integer_search，枚举“每场最多一个 variant、恰好 N 场、总注额 <= max_budget”的完整组合
大规模候选矩阵使用 dynamic_programming_integer_search，按已选场数与 atomic bet 数量分桶保留高质量状态，避免普通 beam search 过早丢弃预算内强组合
solver 保留 locked_candidates，不替换用户已确认腿；已开赛未锁定候选仍由 as_of_time_utc 过滤，不进入新组合
Global Planner、Recommendation Engine、Lifecycle Backtest 与 Historical Backtest 的 single mode 已切到 solver-backed single selector，保证训练/回放/生产候选使用同一套核心选择口径
内部 explanation_json.solver_search 记录 search_mode、exact、候选场次数、variant 数、评估状态数、quality_delta 与最终 outcome；普通用户前端仍不展示采用了什么策略
新增确定性测试覆盖：单式 exact solver 可覆盖贪心 pair、大候选池复式走 dynamic programming solver、相关 planner/backtest 路径保持通过
该阶段属于“后续优化器升级”主线，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-73 当前落地能力：

```text
Historical Recommendation Backtest 新增 optimizer_profile，支持 heuristic 与 solver 两套选择口径
heuristic profile 作为 solver 前基线：single mode 使用原始贪心选择，multiple mode 保留预算裁剪/替换/beam 但关闭 integer solver
solver profile 作为当前候选：single/multiple 都允许 solver_search 覆盖启发式路径
新增 run_historical_recommendation_backtest_comparison，用同一冻结历史切片同时运行 baseline 与 candidate，并输出 final_hit_rate、ROI、profit_loss、Brier、log_loss、calibration 与 upset_capture delta
comparison summary 会记录 final_answer_changed、baseline/candidate optimizer profile、backtest_key 与候选 solver_selected_scenario_count
CLI 新增 --optimizer-profile 与 --compare-solver，可直接对本地历史切片做 solver vs heuristic 对照
历史回测 scenario 结果新增 selection_diagnostics_json，记录 optimizer_profile、selection_basis 与内部 solver_search 摘要，用于准确性审计，不进入普通用户前端
新增确定性测试覆盖：同一历史切片下 heuristic 选错 A/B，solver 选中 C/D，并改善最终命中、ROI、Brier/log loss
README 更新 compare-solver 示例，强调该能力是内部准确性闭环工具，不改变用户推荐话术
该阶段属于“真实历史样本回测增强 / solver 质量证据链”主线，不接新 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-74 当前落地能力：

```text
Historical Recommendation Backtest 新增 suite 聚合模式，可把多个冻结历史切片作为同一质量门禁批量评估
新增 HistoricalRecommendationBacktestSuiteResult 与 run_historical_recommendation_backtest_suite，统一输出 aggregate_deltas_json、summary_json、warnings 与 comparison 列表
suite 模式逐切片运行 heuristic baseline 与 solver candidate，然后聚合 final_hit_rate、ROI、profit_loss、Brier、log_loss、calibration、upset_capture、final_answer_changed_count 与 solver_selected_scenario_count
CLI 支持多个 slice path 或 --suite；多切片时自动进入 solver-vs-heuristic aggregate gate
新增确定性测试覆盖：两个冻结切片下 solver 均改变最终答案并提升最终命中、收益与 Brier，suite 汇总能稳定给出 improved 状态
README 更新多切片 suite 示例，强调该能力用于内部准确性闭环和质量门禁，不改变普通用户前端，不接新 API，不接自动下注、支付、钱包，不引入保证盈利表述
```

V3.1-75 当前落地能力：

```text
新增 Historical Recommendation Suite Quality Gate，把多切片 suite 回测从“报告输出”升级为可失败的内部准确性门禁
新增 HistoricalRecommendationSuiteQualityGateOptions / Check / Result 与 run_historical_recommendation_suite_quality_gate
门禁默认阻断 mixed/regressed suite status，并检查 final_hit_rate_delta、Brier、log-loss、calibration 是否相对 heuristic baseline 退化
门禁可配置 min_slice_count、min_comparison_count、min_final_hit_sample_size、min_roi_delta、min_profit_loss_delta、min_upset_capture_sample_size、min_upset_capture_rate_delta、min_solver_selected_scenario_count、min_final_answer_changed_count 与 max_warning_count
新增 CLI：nutmeg-recommendation-historical-suite-gate；它会加载冻结历史切片、运行 heuristic vs solver suite，再按阈值输出 pass/fail，并在失败时返回非零退出码
新增确定性测试覆盖：solver 改进 suite 可通过严格门禁；mixed/regressed suite 会因状态、命中率、ROI、收益、Brier/log-loss/calibration、冷门、solver 影响和 warning 阈值失败；CLI 参数映射保持稳定
README 更新 suite gate 示例，明确这是内部准确性闭环工具，不接新 API，不触发自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-76 当前落地能力：

```text
新增 Historical Recommendation Suite Manifest，用本地 JSON manifest 管理冻结历史切片 registry
新增 HistoricalRecommendationSuiteManifest、HistoricalRecommendationSuiteManifestSlice、HistoricalRecommendationSuiteManifestLoadResult 与 manifest loader/relative path resolver
新增 configs/recommendations/historical_suites/euro_2024_knockout_suite.json，作为当前 Euro 2024 冻结样本的标准 suite registry
nutmeg-recommendation-historical-suite-gate 新增 --suite-manifest，可不传 positional slice path，直接从 manifest 加载 enabled slices
manifest path 按 manifest 文件所在目录解析相对 slice path，便于后续把真实历史切片按赛事、赛季、数据质量标签组织成可重复 suite
gate summary 会记录 suite_manifest 摘要和 manifest_warnings，不把完整切片内容塞入普通输出摘要
新增确定性测试覆盖：manifest 读取、相对路径解析、manifest-only CLI 加载
该阶段属于“真实历史样本回测增强 / 历史样本 registry”主线，不接新 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-77 当前落地能力：

```text
新增 Historical Recommendation Slice Builder，把冻结历史样本扩容从手写 JSON 升级为标准 CSV -> slice JSON 的生成流程
新增 HistoricalRecommendationSliceBuildOptions、HistoricalRecommendationSliceCsvRow、HistoricalRecommendationSliceBuildResult 与 build_historical_recommendation_slice_from_csv
CSV 输入要求包含 fixture_id、kickoff_time_utc、home_team_name、away_team_name、actual_home_goals、actual_away_goals、prediction_time_utc、model_version、outcome、probability、decimal_odds
CSV 可选字段覆盖 feature_version、calibration_version、market_type、market_probability、model_edge、data_quality_score、model_confidence_score、calibration_score、upset_protection_score、odds_stability_score、volatility_penalty、line、side、metadata_json、fixture_metadata_json
builder 会按 fixture_id 保序聚合 prediction rows，验证同一 fixture 的基础字段一致，阻断重复 prediction key，并对 as-of-time 与玩法概率和偏差输出 warning
新增 CLI：nutmeg-recommendation-historical-slice-build，可从 CSV 生成 HistoricalRecommendationSlice JSON；不传 output-path 时直接打印 slice JSON，传 output-path 时写入文件并打印生成摘要
新增 configs/recommendations/historical_slice_inputs/euro_2024_knockout_sample.csv，作为当前冻结样本扩容的 canonical CSV 输入示例
新增确定性测试覆盖：CSV -> slice 生成、生成结果可直接进入 historical backtest、CLI 参数映射
README 更新 builder 示例，明确该能力服务真实历史样本扩容，不接新 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-78 当前落地能力：

```text
新增 Historical Suite Manifest Refresh，用于验证并注册新生成的冻结历史 slice，避免 slice 文件与 suite registry 脱节
新增 HistoricalRecommendationSuiteManifestRefreshOptions / Result 与 refresh_historical_recommendation_suite_manifest
新增 CLI：nutmeg-recommendation-historical-suite-refresh，默认 dry-run，只有传 --write 才会写回 manifest
refresh 会加载待注册 slice，读取 slice_id，按已存在的 resolved path 或 slice_id 做 upsert，避免重复注册同一历史切片
注册路径会相对 manifest 文件所在目录保存，便于 configs/recommendations/historical_suites 与 historical_slices / generated slice 目录迁移
refresh 支持 --tag、--note、--disabled，并在更新已有 entry 时合并 tags/notes，保留 deterministic registry 输出
refresh 写入后会复用 manifest validation，输出 duplicate slice id、disabled skipped、no enabled slices 等 warning
新增确定性测试覆盖：dry-run 不写文件、--write 注册新 slice、重复注册按 slice_id 更新并合并 tags/notes
README 更新 suite refresh 示例；该能力仍属于历史样本扩容/质量门禁基础设施，不接新 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-79 当前落地能力：

```text
新增 Historical Sample Pipeline，把 CSV -> slice JSON -> manifest refresh -> suite quality gate 串成一条本地批量流水线
新增 HistoricalRecommendationSamplePipelineBuildDefaults / Options / BuildRecord / Result 与 run_historical_recommendation_sample_pipeline
新增 CLI：nutmeg-recommendation-historical-sample-pipeline，可接收多个 CSV 输入，按文件名生成 deterministic slice_id/name，写入 output_dir，再刷新指定 suite manifest
pipeline 默认写出 generated slice 文件，manifest refresh 默认 dry-run；只有传 --write-manifest 才写回 registry，避免误改本地权威 suite 文件
pipeline 默认运行 historical suite gate，并在 gate 失败时返回非零退出码；可用 --skip-gate 或 --no-fail-process 控制本地开发行为
pipeline 支持透传 builder defaults、manifest tags/notes、backtest pass_types/modes/budget 与核心 gate 阈值，使样本扩容后能立刻判断是否影响最终答案质量
新增确定性测试覆盖：pipeline 生成 slice、注册 manifest、运行 gate；skip-gate 路径；CLI 参数映射
README 更新 pipeline 示例；该能力仍属于历史样本扩容/质量门禁基础设施，不接新 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-80 当前落地能力：

```text
新增 Historical Sample Quality Gate，用于在历史样本进入 manifest/suite gate 之前检查 slice 自身 coverage 与数据完整性
新增 HistoricalRecommendationSampleQualityOptions / Check / Result / SuiteResult 与 evaluate_historical_recommendation_sample_quality / evaluate_historical_recommendation_sample_quality_suite
新增 CLI：nutmeg-recommendation-historical-sample-quality，可直接校验 slice paths 或 --suite-manifest
质量门槛覆盖 min_fixture_count、fixture_id 唯一性、kickoff+home+away 唯一性、prediction_time <= as_of、kickoff_time > as_of、每场完整 1X2 三项、1X2 概率和容差、decimal odds、可选 market_probability 与 min_data_quality_score
Historical Sample Pipeline 已接入 sample quality：默认先生成 slice 并校验质量；若质量失败且未显式 allow，manifest --write 会被抑制，suite gate 会被跳过，CLI 默认返回非零退出码
新增确定性测试覆盖：完整 builder slice 通过质量门槛；缺失 1X2 与重复 fixture/matchup 会失败；suite 级聚合失败；CLI 参数映射；pipeline 在质量失败时抑制 manifest 写入并跳过 gate
README 更新 sample quality 与 pipeline 保护说明；该能力仍属于历史样本扩容/质量门禁基础设施，不接新 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-81 当前落地能力：

```text
新增 Successor Chain Evaluation 只读门槛，用于单独评估 source -> successor 推荐生命周期是否可作为准确率证据
新增 RecommendationSuccessorChainEvaluationOptions / Check / Result 与 run_recommendation_successor_chain_evaluation
评估器复用 Recommendation Chain Integrity 读取真实 recommendation_runs，再生成 Effective Chain 口径，输出最终 effective leaf run、被 successor 覆盖的 source、被忽略的 invalidated successor 与 ambiguous successor source
新增 CLI：nutmeg-recommendation-successor-chain-evaluate，可按 window、pass_type、mode、strategy 与 limit 读取 Postgres 推荐链
门槛覆盖 min_effective_leaf_count、min_active_edge_count、max_critical_issue_count、max_ambiguous_successor_source_count 与可选 max_source_status_sync_required_count
该工具不修改 source 状态；source status 修复仍由 dry-run 默认的 source-status-sync 工具处理
新增确定性测试覆盖：多跳 successor 只通过最终 leaf、重复 active successor 阻断、invalidated successor 不覆盖 source、可选 source status sync 阈值、CLI 参数映射
README 更新 successor chain evaluator 示例；该能力属于“Successor Chain Evaluation / 周期质量门禁升级”主线，不接新 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-82 当前落地能力：

```text
Successor Chain Evaluation 已接入 Core Validation Runner：每次核心验证在 chain integrity 后生成 successor_chain_evaluation 摘要
Core Validation summary 新增 successor_chain_evaluation_passed、successor_chain_effective_leaf_count、successor_chain_active_edge_count、successor_chain_critical_issue_count、successor_chain_ambiguous_source_count 与 successor_chain_source_status_sync_required_count
Benchmark Runner 聚合 successor chain evaluation passed count、effective leaf count、active edge count、critical issue count、ambiguous source count 与 source status sync pressure
Benchmark Quality Gate 新增 successor chain 专属阈值：min_successor_chain_evaluation_passed_ratio、min_successor_chain_effective_leaf_count、max_successor_chain_critical_issue_count、max_successor_chain_ambiguous_source_count 与 max_successor_chain_source_status_sync_required_count
Benchmark Cycle / Schedule / Strategy Pair CLI 已透传 successor-chain evaluation 开关与 gate 阈值，skip-chain-integrity 时自动跳过 successor-chain evaluation
新增确定性测试覆盖：core validation 摘要透传、benchmark 聚合、quality gate 阻断 successor chain 退化、cycle/schedule/strategy-pair CLI 参数映射
README 更新 benchmark gate / cycle 示例；该能力属于“周期质量门禁升级”主线，不接新 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-83 当前落地能力：

```text
新增 Euro 2024 group-stage upset-pressure 冻结历史样本，扩展真实赛果覆盖到热门脆弱、冷门命中、平局保护与校准压力场景
新增 configs/recommendations/historical_slice_inputs/euro_2024_group_upset_sample.csv，包含 7 场 Euro 2024 小组赛公开赛果与本地冻结 1X2 概率/赔率输入
新增 configs/recommendations/historical_slices/euro_2024_group_upset_sample.json，由 CSV builder 生成，fixture_count=7、prediction_count=21
新增 configs/recommendations/historical_suites/euro_2024_upset_stress_suite.json，作为独立 stress suite；默认 knockout suite 保持稳定 baseline，不被压力样本破坏
压力样本 sample quality 通过：fixture 唯一性、kickoff/as-of 时间、完整 1X2、概率和、decimal odds、market_probability 与 data_quality 均达标
压力样本 historical comparison 明确暴露权衡：solver 能改变最终答案、提升 upset capture 与 profit/loss，但可能让 Brier/log-loss/calibration 变差；该结果用于校准质量函数而非普通用户展示
新增确定性测试覆盖：stress suite manifest 读取、stress slice sample quality、historical comparison 的 upset-capture/ROI 与 calibration pressure 信号
README 更新 upset-pressure stress suite 用法；该能力属于“真实历史样本扩容 / 冷门能力强化 / 周期质量门禁升级”主线，不接新 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-84 当前落地能力：

```text
推荐候选评分新增 calibration_risk 与 longshot_upset_risk 组件：低校准、低信心、低数据质量、赔率不稳、低概率长赔与冷门信号叠加时会形成内部惩罚
accuracy_first 默认策略新增校准风险与长赔冷门风险扣分；single/value/upset focus 配置分别保留独立权重，使冷门保护可以被治理但不会无约束放大
solver/beam 的组合质量函数新增组合级 calibration risk、longshot upset risk 与 fragile favorite avoidance penalty，避免用超低命中率长赔组合或热门脆弱 favorite 覆盖更稳答案
Euro 2024 group-stage upset stress comparison 从 mixed 改为 unchanged：solver 评估后不覆盖 heuristic，candidate_solver_selected_scenario_count=0，Brier/log-loss/calibration 不再恶化
upset stress suite 默认 quality gate 通过；若未来显式要求 solver influence 或冷门暴露，可用更严格阈值单独做压力测试
新增确定性测试覆盖：候选 longshot/calibration risk reason code、复式预算裁剪在校准风险加入后仍保留、historical stress slice 拒绝未校准 solver override
README 与 stress suite manifest 更新当前预期；该能力属于“冷门能力强化 / 周期质量门禁升级 / solver 质量函数校准”主线，不接新 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-85 当前落地能力：

```text
在 V3.1-84 的风险惩罚基础上新增 calibrated_upset_exposure 正向通道：冷门候选只有同时满足最低概率、校准分、数据质量、模型信心、赔率稳定与最大波动惩罚阈值，才会被视为“可控暴露”
candidate_longshot_upset_risk 支持按 calibrated_upset_exposure 折减风险，但未达阈值的长赔冷门仍保持惩罚，不会因赔率高而覆盖稳健答案
RecommendationPolicyConfig 新增 upset exposure 阈值与 calibrated_upset_exposure_weight；accuracy/value/upset focus 可分别治理暴露强度
solver/beam 组合质量函数新增 calibrated_upset_exposure 组合级加分，与 calibration_risk、longshot_upset_risk、fragile favorite penalty 共同构成冷门质量边界
新增确定性测试覆盖：未校准长赔仍触发 penalty；校准合格冷门产生 calibrated_upset_exposure_allowed；historical backtest 中 solver 可用一个校准合格冷门替换过热失准腿并改善 final-hit、Brier/log-loss/calibration
README 更新受控冷门暴露说明；该能力属于“冷门能力强化 / solver 质量函数校准 / 历史回测闭环”主线，不接新 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-86 当前落地能力：

```text
新增 football-data.co.uk 历史 CSV 导入器，用于把本地下载的赛季 CSV 批量转换为 Nutmeg HistoricalRecommendationSlice
新增 FootballDataCoUkImportOptions / Result / BatchImportResult 与 build_historical_recommendation_slice_from_football_data_co_uk_csv / run_football_data_co_uk_batch_import
新增 CLI：nutmeg-recommendation-football-data-co-uk-import，支持多个 CSV 输入、output-dir/output-path、manifest dry-run/写入、manifest tags/notes、odds prefix 优先级和 max_rows
导入器优先读取 AvgC/Avg/MaxC/Max/B365C/B365/PS 等 1X2 odds triplet，将 decimal odds 转换为 no-vig market-implied probabilities，并保留 raw implied probability 作为 market_probability
导入器兼容五大联赛 CSV 的 HomeTeam/AwayTeam/FTHG/FTAG/FTR 字段，也兼容 Japan/J-League 等 worldwide CSV 的 Home/Away/HG/AG/Res 字段
新增 source_seasons / --source-season 过滤能力，可把 Japan JPN.csv 这类多年份合并文件拆成单赛季 historical slice
生成的 fixture 使用统一 as_of_time_utc 作为 prediction_time_utc，满足 sample quality 的 prediction_time <= as_of 与 kickoff > as_of 检查，适合做可重复历史回测切片
metadata 记录 source_division、source_row_number、selected_odds_prefix、odds_overround 与 CSV 文件名；长赔/平局项会生成内部 upset protection metadata，供冷门回测使用
新增确定性测试覆盖：CSV -> slice 导入、缺赔率行跳过、生成切片通过 sample quality、批量输出 JSON、CLI 参数映射
README 更新 football-data.co.uk 本地导入示例；该能力属于“真实历史样本回测 / 历史样本扩容”主线，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-87 当前落地能力：

```text
按产品核心回测需要落地第一批真实历史样本资产：EPL、西甲、德甲、意甲、法甲各 5 个已完赛赛季，日本 J1 也已确认可用并纳入
下载源 CSV 保存于 data/historical_sources/football_data_co_uk：欧洲使用 2020/21-2024/25 的 E0/SP1/D1/I1/F1，Japan 使用 new/JPN.csv 并按 source_season 切出 2021-2025
生成 30 个 HistoricalRecommendationSlice JSON，保存于 configs/recommendations/historical_slices/football_data_co_uk
新增 suite manifest：configs/recommendations/historical_suites/football_data_co_uk_core_5_seasons_suite.json
样本规模：slice_count=30，fixture_count=10738，prediction_count=32214，覆盖 EPL/ESP_LA_LIGA/GER_BUNDESLIGA/ITA_SERIE_A/FRA_LIGUE_1/JPN_J1 各 5 个 season slice
导入 warnings 为空；欧洲 25 个 season CSV 均无 skipped row；Japan skipped row 来自 JPN.csv 多年份合并文件按 source_season 过滤，不代表数据缺失
sample quality gate 已通过：min_fixture_count=300、require_market_probability、min_data_quality_score=80，30/30 slices passed
historical suite gate smoke 已通过：2x1 single、max_budget=4、min_slice_count=30、min_comparison_count=30、min_final_hit_sample_size=30、max_warning_count=1；suite_status=unchanged，candidate_roi=-0.1422633333333333，candidate_profit_loss=-8.535799999999998，upset_opportunity_count=1340
README 更新真实历史 suite 使用方法；该能力属于“真实历史样本回测 / 周期质量门禁升级 / 冷门能力校准”的基础数据层，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-88 当前落地能力：

```text
新增 Historical Recommendation Diagnostics，用于把真实历史 suite 聚合成 overall、competition、season、competition+season 四层诊断报告
新增 HistoricalRecommendationDiagnosticOptions / MetricSet / Group / Report 与 build_historical_recommendation_diagnostic_report
新增 CLI：nutmeg-recommendation-historical-diagnostics，支持 suite manifest 或 slice paths、pass_types、modes、budget、optimizer profile、output_path
诊断指标覆盖 final_hit_sample_size、final_hit_rate、total_stake、actual_return、profit_loss、ROI、Brier、Log loss、mean calibration error、upset opportunity/capture、solver_selected_scenario_count、final_answer_changed_count 与 delta
新增确定性测试覆盖：真实 slice 聚合到 competition/season/competition+season；CLI 参数映射
生成第一份真实历史诊断报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_solver_single_2x1_diagnostics.json
该报告基于 football-data.co.uk 30 slices、10738 fixtures、32214 predictions，场景为 2x1 single、unit_stake=2、max_budget=4、min_data_quality_score=80
总体诊断：candidate_final_hit_rate=0.6666666666666666，candidate_roi=-0.14226333333333324，candidate_profit_loss=-8.535799999999995，candidate_brier_score=0.22235742660310917，candidate_log_loss=0.6381190597564622，candidate_mean_calibration_error=0.4173499521182605，upset_opportunity_count=1340，upset_capture_rate=0.0
分联赛诊断暴露差异：FRA_LIGUE_1 hit_rate=1.0/ROI=0.2395，ITA_SERIE_A hit_rate=0.8/ROI=0.03072；ESP_LA_LIGA hit_rate=0.4/ROI=-0.50264，JPN_J1 hit_rate=0.4/ROI=-0.27604，GER_BUNDESLIGA hit_rate=0.6/ROI=-0.28696，EPL hit_rate=0.8/ROI=-0.05816
开发发现：2x1-8x1 + multiple + solver 在 30 个大切片上组合空间过重，不适合作为当前默认质量门禁；后续需要优先做候选池压缩/solver 限宽，再跑完整 2x1-8x1 single/multiple 诊断
README 更新 diagnostics 用法；该能力属于“真实历史样本回测 / 周期质量门禁升级 / 推荐引擎校准”的诊断层，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-89 当前落地能力：

```text
新增 historical backtest 候选池压缩参数：candidate_fixture_limit 与 max_candidates_per_fixture，用于真实大样本诊断时先按策略评分选取高质量 fixture 池，再进入单式/复式/solver
HistoricalRecommendationBacktestOptions、historical-backtest CLI、historical-diagnostics CLI、historical-suite-gate CLI 均已支持 --candidate-fixture-limit 与 --max-candidates-per-fixture
候选池压缩默认关闭，不影响既有小样本测试与默认行为；启用后 summary_json 会记录 eligible_candidate_count、candidate_pool_count、candidate_pool_fixture_count、candidate_fixture_limit 与 max_candidates_per_fixture
新增确定性测试覆盖：候选池限宽后 candidate_count/candidate_pool_count 正确；diagnostics 与 suite gate CLI 参数映射
生成 bounded full-matrix 真实历史诊断报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_bounded_full_matrix_diagnostics.json
bounded full-matrix 设置为 2x1-8x1、single+multiple、unit_stake=2、max_budget=64、candidate_fixture_limit=8、max_candidates_per_fixture=2；该设置可在约分钟级完成，作为日常 smoke/诊断 lane
bounded full-matrix 总体结果：candidate_final_hit_rate=0.4238095238095238，candidate_roi=-0.5634001216131947，candidate_profit_loss=-911.5813967701491，candidate_brier_score=0.20444801022526615，candidate_log_loss=0.5953474812864239，candidate_mean_calibration_error=0.41363019916397736，upset_opportunity_count=1340，upset_capture_rate=0.0007462686567164179
bounded full-matrix solver 行为：candidate_solver_selected_scenario_count=19，final_answer_changed_count=3，suite_status=mixed；说明 solver 能介入但当前收益质量仍不合格
分联赛表现：EPL ROI=0.16587、FRA_LIGUE_1 ROI=0.35808 为正；ESP_LA_LIGA ROI=-0.64111、GER_BUNDESLIGA ROI=-0.58290、ITA_SERIE_A ROI=-0.26871、JPN_J1 ROI=-0.85584 拖累明显
bounded suite gate 可跑通但按质量预期失败：candidate_final_hit_sample_size=420，failed_checks=suite_status/final_hit_rate_delta；这是当前策略需继续校准的信号，不是工具失败
开发发现：candidate_fixture_limit=20/48 在 full 2x1-8x1 single+multiple 矩阵下仍偏慢，后续需要继续优化 optimizer 内部的复式追加、fixture replacement 与 beam/solver 搜索剪枝
README 更新 bounded full-matrix 诊断用法；该能力属于“真实历史样本回测 / 周期质量门禁升级 / solver 运行边界”的工程基础，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-90 当前落地能力：

```text
复式优化器新增 large-pool solver-first path：当候选 fixture 数达到阈值时，先执行预算约束整数/DP 搜索；若 solver 质量优于基准路径则直接返回，减少先跑昂贵的复式保护贪心与跨比赛替换搜索的次数
solver-first 仅在大候选池触发，小候选池保留既有行为；当 solver 未改善基准质量时继续走原 heuristic 复式路径，不强行展示内部策略给用户
solver_search 诊断新增 solver_first_fast_path 字段，用于后端质量分析识别大池搜索路径
HistoricalRecommendationBacktestOptions、historical-backtest CLI、historical-diagnostics CLI、historical-suite-gate CLI 新增 scenario_candidate_fixture_buffer / --scenario-candidate-fixture-buffer
场景级候选窗口默认关闭；启用后，每个 pass_type 只使用 leg_count + buffer 个 fixture 进入具体 single/multiple 场景搜索，避免 2串1/3串1 被 48 场全局池拖慢
summary_json 记录 scenario_candidate_fixture_buffer；backtest/comparison/suite key 纳入 candidate_fixture_limit、max_candidates_per_fixture 与 scenario_candidate_fixture_buffer，避免不同诊断参数生成同一 key
新增确定性测试覆盖：large-pool solver-first path、solver 未改善时 base fallback、scenario buffer CLI 参数映射
生成 20/48 fixture window4 full-matrix 历史诊断报告；48 fixture 全局池 + max_candidates_per_fixture=2 + scenario_candidate_fixture_buffer=4 可在分钟级完成 30 slices、2x1-8x1、single+multiple 诊断
48 fixture window4 总体结果：candidate_final_hit_rate=0.4166666666666667，candidate_roi=-0.5728549546424161，candidate_profit_loss=-926.8793166114292，candidate_brier_score=0.2016614253182442，candidate_log_loss=0.5873322093888803，candidate_mean_calibration_error=0.41102183647171275，upset_capture_rate=0.0007462686567164179
48 fixture window4 suite gate 可稳定运行但按质量预期失败：failed_checks=suite_status/final_hit_rate_delta；Brier、log loss 与 mean calibration error 相对 baseline 改善，但 final hit 与 ROI 仍退步，说明下一阶段应调整质量函数/冷门暴露/最终答案仲裁，而不是继续扩数据源或部署
README 更新 routine full-matrix 诊断命令；该能力属于“后续优化器升级 / 真实历史样本回测 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-91 当前落地能力：

```text
为 solver 与 fixture replacement 增加最小质量增益护栏：SOLVER_MIN_QUALITY_DELTA=0.0015；低于该门槛的微小改进不再覆盖 baseline
修正 large-pool solver-first 的 rejected 路径：solver 未通过时不再提前返回 single base fallback，而是继续执行原 heuristic 复式保护与替换路径
fixture replacement 使用同一最小质量增益门槛，避免为了 0.0001 级别的预测质量差异替换稳定腿；强收益替换仍保留
更新确定性测试命名与断言，确保 solver rejected 后仍走 v3_1_multiple_budget_optimizer 路径
重新生成 48 fixture window4 full-matrix 历史诊断报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_full_matrix_diagnostics.json
新的 48 fixture window4 诊断：suite_status=unchanged，candidate_final_hit_rate=0.4261904761904762，candidate_roi=-0.5653600534729363，candidate_profit_loss=-911.3604061983732，candidate_brier_score=0.20644044221517566，candidate_log_loss=0.599484786327729，candidate_mean_calibration_error=0.4156682522981868，candidate_solver_selected_scenario_count=8，final_answer_changed_count=1
48 fixture window4 suite gate 已通过：slice_count=30，comparison_count=30，final_hit_sample_size=420，failed_checks=[]，warnings=[]
当前意义：优化器候选扩大与 solver-first 现在至少不伤害 baseline；下一步才应该继续寻找真正正向提升命中率/ROI 的质量函数和冷门暴露改进
README 更新 routine full-matrix gate 结果；该能力属于“准确性护栏 / 后续优化器升级 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-92 当前落地能力：

```text
修正 historical backtest 的 final_hit_* 顶层统计口径：现在每个 historical slice 只评估最终答案一次；所有完成场景的命中、ROI 与总投注额保留在 summary_json 的 scenario_* 诊断字段中
最终答案仲裁器新增 stake_discipline 组件：当模型期望 ROI 不为正时，高注额复式不能仅凭更高覆盖概率压过低注额单式；正 EV 复式仍可进入竞争
final_answer_arbitrator 权重从偏覆盖概率调整为更重视 ROI 与注额纪律：planner=0.20、hit_probability=0.15、roi=0.20、risk=0.10、data_quality=0.08、budget_efficiency=0.04、stake_discipline=0.13、fixture_depth=0.01、answer_type=0.03、upset_quality=0.06
historical suite quality gate 新增绝对命中率门槛：--min-candidate-final-hit-rate；用于防止只看相对 baseline delta，却忽略最终答案本身是否成型
新增确定性测试覆盖：最终答案只计 final answer、scenario_* 诊断仍保留；负 EV 高注额复式会输给更克制的单式；suite gate CLI 映射 min_candidate_final_hit_rate
重新生成 48 fixture window4 full-matrix 历史诊断报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_full_matrix_diagnostics.json
新的最终答案口径诊断：suite_status=unchanged，candidate_final_hit_sample_size=30，candidate_final_hit_rate=0.6666666666666666，candidate_roi=-0.14226333333333324，candidate_profit_loss=-8.535799999999995，candidate_brier_score=0.22235742660310917，candidate_log_loss=0.6381190597564622，candidate_mean_calibration_error=0.4173499521182605，candidate_solver_selected_scenario_count=8，final_answer_changed_count=0
48 fixture window4 suite gate 已通过：slice_count=30，comparison_count=30，min_final_hit_sample_size=30，min_candidate_final_hit_rate=0.60，failed_checks=[]，warnings=[]
当前意义：质量门禁现在真正评估用户最终看到的答案；仲裁器减少了负 EV 高注额复式覆盖，full-matrix 绝对最终答案命中率达到 20/30，ROI 从旧 full-matrix 最终答案口径 -0.4159731707317073 改善到 -0.14226333333333324
README 更新 final-answer-only gate 命令与最新指标；该能力属于“最终答案仲裁器 / 周期质量门禁升级 / 真实历史样本回测”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-93 当前落地能力：

```text
新增分联赛最终答案 profile：configs/recommendations/competition_recommendation_profiles.json；首版基于 football-data.co.uk 五季冻结诊断，只对 EPL、ESP_LA_LIGA、FRA_LIGUE_1、GER_BUNDESLIGA 的 3x1 single 做仲裁微调，ITA_SERIE_A 与 JPN_J1 暂不加权
新增 competition_profiles 模块，支持加载 profile set、导出 profile_version、按 competition_id 建索引；该配置是内部仲裁输入，不作为用户可见策略解释
最终答案仲裁器接入 competition_profile_adjustment，并在 score_components/profile_version 中保留审计信息；历史 backtest key 与 suite key 纳入 profile_version，确保 profile 变化会生成新的可追踪结果
historical suite quality gate 新增绝对 ROI 门槛：--min-candidate-roi；与 --min-candidate-final-hit-rate 一起约束最终答案不能只“命中率过线但亏损失控”
新增确定性测试覆盖：competition profile 可改变最终答案排序；suite gate CLI 映射 min_candidate_roi；低于 ROI 门槛会产生 candidate_roi failed check
重新生成 48 fixture window4 full-matrix 历史诊断报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_full_matrix_diagnostics.json
新的分联赛 profile 诊断：suite_status=unchanged，candidate_final_hit_sample_size=30，candidate_final_hit_rate=0.6666666666666666，candidate_roi=-0.06894253333333325，candidate_profit_loss=-4.136551999999995，candidate_brier_score=0.22275420547585947，candidate_log_loss=0.6373247568509548，candidate_mean_calibration_error=0.44719641123276904，candidate_solver_selected_scenario_count=8，final_answer_changed_count=0
48 fixture window4 suite gate 已通过：slice_count=30，comparison_count=30，min_final_hit_sample_size=30，min_candidate_final_hit_rate=0.60，min_candidate_roi=-0.10，failed_checks=[]，warnings=[]
当前意义：在保持最终答案命中率 20/30 不变的前提下，ROI 从 -0.14226333333333324 改善到 -0.06894253333333325，亏损从 -8.535799999999995 收窄到 -4.136551999999995；下一步应继续围绕 Italy/Japan 与冷门捕捉做样本驱动优化
README 更新 routine full-matrix gate 命令与最新指标；该能力属于“分联赛适配 / 最终答案仲裁器 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-94 当前落地能力：

```text
分联赛最终答案 profile 升级为 roi_guard_v2：EPL 从 3x1 single 调整为 5x1 single，ESP_LA_LIGA 从 3x1 single 调整为 5x1 single，FRA_LIGUE_1 从 3x1 single 调整为 4x1 single；GER_BUNDESLIGA 继续保留 3x1 single；ITA_SERIE_A 与 JPN_J1 不强行加长关数
调整原则：只接受在五季 full-matrix 诊断中不降低 final-hit count 且改善 ROI 的 profile；JPN_J1 的 6x1 single 虽然 ROI 更高但 final-hit count 从 2/5 降到 1/5，因此按 accuracy-first 原则拒绝
重新生成 48 fixture window4 full-matrix 历史诊断报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_full_matrix_diagnostics.json
新的 profile 诊断：suite_status=unchanged，candidate_final_hit_sample_size=30，candidate_final_hit_rate=0.6666666666666666，candidate_roi=0.05017769041333343，candidate_profit_loss=3.0106614248000056，candidate_brier_score=0.24445905503052764，candidate_log_loss=0.683178240140196，candidate_mean_calibration_error=0.47697612791196814，candidate_solver_selected_scenario_count=8，final_answer_changed_count=0
分联赛 ROI：EPL=0.30976559936000037，ESP_LA_LIGA=-0.21856938688000013，FRA_LIGUE_1=0.6583547299999999，GER_BUNDESLIGA=-0.20316479999999987，ITA_SERIE_A=0.030719999999999813，JPN_J1=-0.27603999999999995
historical suite quality gate 新增分联赛 ROI 底线：--min-competition-candidate-roi；summary_json 输出 competition_candidate_roi、worst_competition_candidate_roi 与 worst_competition_id
48 fixture window4 suite gate 已通过：slice_count=30，comparison_count=30，min_candidate_final_hit_rate=0.60，min_candidate_roi=0.0，min_competition_candidate_roi=-0.30，failed_checks=[]，warnings=[]
新增确定性测试覆盖：低于分联赛 ROI 门槛会产生 competition_candidate_roi failed check；CLI 参数映射 min_competition_candidate_roi
当前意义：在不牺牲最终答案命中率 20/30 的前提下，总体 ROI 从 -0.06894253333333325 提升到 +0.05017769041333343；下一步应重点修正 JPN_J1、ESP_LA_LIGA 与 GER_BUNDESLIGA 的负 ROI，并继续把冷门捕捉从 0.0 往可控捕捉推进
README 更新 routine full-matrix gate 命令与最新指标；该能力属于“分联赛适配 / 负 ROI 联赛修正 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-95 当前落地能力：

```text
新增 parlay correlation exposure 基础模型：ParlayLegSelection / AtomicLeg 支持 correlation_key，RecommendationCandidate.to_leg_selection 会透传 correlation_key
historical backtest 会为 1X2 home_win/away_win 生成球队级 correlation_key，便于识别同一球队在一个最终答案中被反复押注的集中风险
evaluate_parlay 新增显式参数 derive_correlation_penalty；只有调用方明确开启时，才会根据重复 correlation_key 自动派生 correlation_penalty，默认推荐路径不改变命中率/ROI
历史 full-matrix 诊断中的一次宽泛自动惩罚实验被拒绝：它把最终答案命中率从 20/30 降到 19/30，ROI 从 +0.05017769041333343 降到负值；因此当前只保留可审计能力和可选压力门禁，不作为默认策略
historical suite quality gate 新增相关性暴露摘要与可选门禁：summary_json 输出 correlated_final_answer_count、max_final_answer_correlation_exposure；CLI 支持 --max-final-answer-correlation-exposure
当前 48 fixture window4 suite gate 仍通过：candidate_final_hit_rate=0.6666666666666666，candidate_roi=0.05017769041333339，worst_competition_candidate_roi=-0.27603999999999995，correlated_final_answer_count=25，max_final_answer_correlation_exposure=5，failed_checks=[]，warnings=[]
新增确定性测试覆盖：重复 correlation_key 可显式派生 correlation_penalty；历史质量门禁能阻断过度集中的 final-answer correlation exposure；CLI 参数映射 max_final_answer_correlation_exposure
当前意义：同队强热门集中风险已经变成可观察、可门禁的指标，但不会未经验证地影响默认推荐；下一步应把它与热门脆弱、赛程时间窗、联赛 profile 做分层实验，而不是粗暴全局扣分
README 更新 correlation exposure 诊断说明；该能力属于“冷门能力强化 / 热门脆弱治理 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-96 当前落地能力：

```text
新增 historical backtest 的 opt-in 市场上下文信号：HistoricalRecommendationBacktestOptions.derive_market_context_signals
开启后，历史回测会基于同一 fixture 的 1X2 概率与赔率派生 market_context_favorite_outcome、favorite_not_win_probability、draw_probability、short-price pressure 与 favorite_fragility_score
派生信号只进入候选 metadata_json，并复用现有 upset/favorite-fragility policy 管道；默认关闭，不改变当前正式推荐基线
historical-backtest、historical-diagnostics 与 historical-suite-gate CLI 均支持 --derive-market-context-signals，便于把热门脆弱实验与主质量门禁隔离
新增确定性测试覆盖：未开启时高概率热门仍排第一；开启后，短赔且不胜压力较高的热门会被内部 favorite_fragility / upset_avoidance_penalty 降权，稳态候选排到前面
真实 football-data.co.uk 五季 full-matrix 实验已单独输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_market_context_experiment_diagnostics.json
该实验当前没有改变最终答案：candidate_final_hit_rate=0.6666666666666666，candidate_roi=0.05017769041333343，candidate_upset_capture_rate=0.0；因此暂不默认启用
当前意义：热门脆弱已经可以从冻结 1X2 市场结构中自动派生并进入实验门禁，但还需要联赛分层、赔率区间分层或真实阵容/赛程信号叠加，才能作为默认策略提升 ROI 或冷门捕捉
README 更新 market-context experiment 用法；该能力属于“冷门能力强化 / 热门脆弱分层实验 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-97 当前落地能力：

```text
新增 competition_profile_evidence 模块，用冻结历史 suite 对每个联赛的 2x1-8x1 single/multiple 场景做 profile 调整证据评估
证据评估以当前 final answer 为基线，也支持通过 --baseline-scenario COMP=scenario_key 显式指定联赛基线
只在候选场景不降低 hit_count 且 ROI / profit_loss 严格改善时输出 candidate_accepted；0 改善、样本不足、覆盖不完整或命中数下降均不会建议改 profile
新增 CLI：nutmeg-recommendation-competition-profile-evidence，支持 suite manifest、输出 report、候选池限宽、场景窗口、market context 实验参数与基线场景覆盖
新增确定性测试覆盖：ROI 提升且命中不降时接受；高 ROI 但命中数下降时拒绝；CLI 参数映射
生成五季 full-matrix profile evidence 报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_competition_profile_evidence.json
当前报告 report_key=historical_competition_profile_evidence:d05026a8233ec4cd，accepted_count=0，retained_count=6；说明现有 competition profile 暂无可替换场景
负 ROI 基线联赛仍是 ESP_LA_LIGA、GER_BUNDESLIGA、JPN_J1；JPN_J1 的 6x1 single 虽然 ROI 更高，但 hit_count 从 2/5 降到 1/5，因此继续按 accuracy-first 原则拒绝
README 更新 competition profile evidence 用法；该能力属于“负 ROI 联赛修正 / 分联赛适配 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-98 当前落地能力：

```text
新增 historical_loss_diagnostics 模块，用最终答案口径拆解负 ROI 来源；诊断对象是用户最终会看到的 final answer，而不是所有 scenario
诊断维度覆盖 competition、competition_season、scenario、correlation_exposure、odds_band、probability_band、model_edge_band、favorite_fragility_band、favorite_flag、correlation_key、kickoff_month 与 miss_reason
新增 CLI：nutmeg-recommendation-historical-loss-diagnostics，支持 suite manifest、输出 report、候选池限宽、场景窗口、market context 派生、focus competitions 与 --negative-roi-only
新增确定性测试覆盖：最终答案失误会被拆到短赔热门、热门平局失手、脆弱热门分桶和重复球队暴露；negative ROI only 过滤；CLI 参数映射
生成五季 negative ROI loss diagnostics 报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_negative_roi_loss_diagnostics.json
当前报告 report_key=historical_final_answer_loss_diagnostics:58c9c6e2afe267d9，覆盖 ESP_LA_LIGA、GER_BUNDESLIGA、JPN_J1 的 15 个 final answers、50 个 selected legs、12 个 missed legs
主要发现：西甲与 J1 的 missed legs 集中在 high-probability / short-price / market_favorite / negative-edge 组合，而不是单纯关数太长；西甲 missed favorite legs 平均 probability=0.8430433904231802、odds=1.1383333333333334、model_edge=-0.03604493476159015；J1 对应均值 probability=0.7444733773935501、odds=1.2650000000000001、model_edge=-0.05082513856382101
下一步应做短赔热门负 edge guardrail 的 opt-in 实验，并通过 full-matrix gate 验证命中率和 ROI；不应直接加长串关或默认启用相关性惩罚
README 更新 negative ROI loss diagnostics 用法；该能力属于“负 ROI 联赛修正 / 热门脆弱治理 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-99 当前落地能力：

```text
新增短赔热门负 edge guardrail 的 opt-in 实验开关：HistoricalRecommendationBacktestOptions.short_price_negative_edge_guardrail
默认阈值为 decimal_odds <= 1.35、probability >= 0.70、model_edge < 0.0，且仅作用于同一 fixture 内概率最高的 1X2 outcome；默认关闭，不改变普通推荐路径
historical-backtest、historical-diagnostics、historical-suite-gate、competition-profile-evidence、historical-loss-diagnostics CLI 均已支持 --short-price-negative-edge-guardrail 及三个阈值参数
backtest / suite / diagnostics / quality gate summary 已写入 guardrail 参数和 excluded candidate count，确保负向实验也可追溯
新增确定性测试覆盖：关闭 guardrail 时高概率短赔负 edge 热门仍会被选入；开启后会剔除这些候选，改选剩余更优候选；相关 CLI 参数映射已覆盖
真实 football-data.co.uk 五季 full-matrix 实验已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_price_negative_edge_guardrail_diagnostics.json
实验结果被质量门禁拒绝：默认阈值排除 1023 个候选 prediction，candidate_final_hit_rate 从当前有效基线 0.6666666666666666 降至 0.3，candidate_roi 降至 -0.0932132567533331，candidate_profit_loss=-5.592795405199986，worst competition 为 GER_BUNDESLIGA=-1.0
historical suite gate 失败项为 candidate_final_hit_rate、candidate_roi、competition_candidate_roi；因此 guardrail 只作为可审计实验能力保留，不进入默认推荐路线
当前意义：loss diagnostics 找到的“短赔热门负 edge”是真问题，但粗暴剔除会破坏最终答案命中率；下一步应改为分联赛/分赔率段软惩罚或阈值学习，而不是全局硬过滤
README 更新 rejected guardrail experiment 用法；该能力属于“负 ROI 联赛修正 / 热门脆弱治理 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-100 当前落地能力：

```text
新增短赔热门负 edge soft penalty 的 opt-in 实验开关：HistoricalRecommendationBacktestOptions.short_price_negative_edge_soft_penalty
该能力不剔除候选，只在满足短赔、模型高概率、负 edge、且为同 fixture 1X2 概率最高 outcome 时，写入 short_price_negative_edge_soft_penalty_score 与 favorite_fragility_score，复用现有 upset/favorite-fragility 评分管道做软降权
支持 soft_penalty_strength 与 soft_penalty_competition_ids，可用于分联赛/分赔率段/分概率段阈值学习；默认关闭，不改变普通推荐路径
historical-backtest、historical-diagnostics、historical-suite-gate、competition-profile-evidence、historical-loss-diagnostics CLI 均已支持 --short-price-negative-edge-soft-penalty、--short-price-negative-edge-soft-penalty-strength、--short-price-negative-edge-soft-penalty-competitions
backtest / suite / diagnostics / quality gate summary 已写入 soft penalty 参数和 candidate count；backtest key / comparison key / suite key 纳入 soft penalty 参数，确保实验可复现
新增确定性测试覆盖：soft penalty 不删除候选，但能把短赔负 edge 热门降到更稳的候选之后；相关 CLI 参数映射已覆盖
真实 football-data.co.uk 五季 full-matrix soft penalty 实验已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_price_negative_edge_soft_penalty_diagnostics.json
实验设置：仅作用于 ESP_LA_LIGA、GER_BUNDESLIGA、JPN_J1，strength=1.0；共惩罚 392 个 candidate predictions
实验结果：candidate_final_hit_rate=0.6666666666666666，candidate_roi=0.05017769041333343，candidate_profit_loss=3.0106614248000056，绝对命中率/ROI/分联赛 ROI 底线均未破坏；但 final_answer_changed_count=1，brier_score_delta=0.00042813551135387207，log_loss_delta=0.001037758568509184，mean_calibration_error_delta=0.0003019053179395548，因此 suite_status=regressed，quality gate failed
当前意义：soft penalty 明显比 hard guardrail 安全，但还没有提高 ROI 或冷门捕捉，也轻微损害概率质量；因此仅保留为阈值学习工具，不进入默认推荐路线
下一步应做 threshold-learning grid：按联赛、赔率段、概率段、edge 段搜索 strength/阈值，接受条件必须同时满足 final hit 不降、ROI 不降、Brier/log loss/calibration 不退、冷门捕捉不退
README 更新 soft penalty experiment 用法；该能力属于“负 ROI 联赛修正 / 热门脆弱治理 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-101 当前落地能力：

```text
新增短赔热门负 edge threshold-learning grid：build_historical_short_price_threshold_grid_report 用当前 baseline 对比 soft-penalty 阈值候选，并按 final hit、ROI、profit/loss、Brier、log loss、calibration、upset capture 统一判定接受/拒绝
新增 CLI：nutmeg-recommendation-short-price-threshold-grid，支持 suite manifest、输出 report、pass types、single/multiple、预算、候选池限宽、market context 派生、competition group、赔率/概率/model edge/strength 网格，以及质量接受阈值
阈值接受逻辑加入 comparison_epsilon，避免 -2e-17 这类浮点噪声被误判为 ROI 回退；默认 1e-12，可通过 --comparison-epsilon 调整
新增确定性测试覆盖：指标改善时接受 soft penalty candidate；competition group 未命中时拒绝；CLI 参数映射；浮点比较容差
真实 football-data.co.uk 五季 threshold grid 报告已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_price_threshold_grid.json
本轮网格覆盖 30 个 slice、10738 场 fixture、32214 个 1X2 prediction；baseline candidate_final_hit_rate=0.6666666666666666，candidate_roi=0.05017769041333339，candidate_profit_loss=3.0106614248000034
网格设置：仅作用于 ESP_LA_LIGA、GER_BUNDESLIGA、JPN_J1；max_decimal_odds=1.35，min_probability=0.70，max_model_edge=0.0，strength in 0.5/1.0
结果：strength=0.5 被接受为 no-regression profile，惩罚 392 个 candidate predictions，final hit 不降，ROI/profit 仅为浮点级差异，Brier delta=-0.0003504407805396681，log_loss delta=-0.000774349548274933，mean_calibration_error delta=-0.0003137825950302875，upset_capture_rate delta=0.0
strength=1.0 被拒绝，因为 final_answer_changed_count=1 且 suite_status=regressed；说明惩罚强度不可继续盲目放大
当前意义：系统已经能把“热门脆弱/短赔负 edge”从一次性实验升级为可复验的阈值学习机制；但该候选尚未提升 ROI 或冷门捕捉，因此仍不默认进入用户最终答案
README 更新 threshold-learning grid 用法与五季结果；该能力属于“负 ROI 联赛修正 / 热门脆弱治理 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-102 当前落地能力：

```text
收紧 threshold-learning grid 的晋级门槛：accepted 现在默认表示可晋级候选，而不是仅仅 no-regression candidate
新增 require_objective_improvement，默认 true；候选必须在 ROI 或 upset_capture_rate 上至少有一个真实正向增益，同时不得触发 final hit、ROI/profit、Brier、log loss、calibration、upset capture 的回退闸门
新增 min_objective_roi_delta 与 min_objective_upset_capture_rate_delta，可把“真实增益”从大于 0 调整为更高的上线门槛
CLI 新增 --require-objective-improvement / --no-require-objective-improvement、--min-objective-roi-delta、--min-objective-upset-capture-rate-delta
candidate report 新增 objective_improvement_satisfied 与 objective_improvement_metric_codes；拒绝原因新增 threshold_grid:objective_improvement_missing，便于区分“质量回退”和“没有带来核心目标增益”
新增确定性测试覆盖：无客观增益时，即使候选被惩罚且其他指标不退，也不能晋级；CLI 参数映射已覆盖 objective gate
真实 football-data.co.uk 五季 strict threshold grid 报告已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_price_strict_threshold_grid.json
本轮 strict grid 覆盖 30 个 slice、10738 场 fixture、32214 个 1X2 prediction；按 ESP_LA_LIGA、GER_BUNDESLIGA、JPN_J1 三个独立 competition group，max_decimal_odds in 1.25/1.35，min_probability=0.70，max_model_edge=0.0，strength in 0.25/0.5，共 12 个候选
结果：accepted_count=0，rejected_count=12；全部候选都没有产生 ROI 或 upset_capture_rate 的真实正向增益，因此不进入默认推荐路线
最佳 rejected candidate 为 GER_BUNDESLIGA、max_decimal_odds=1.35、strength=0.5，惩罚 205 个 candidate predictions，final hit 不降，Brier delta=-0.00019856722742114807，log_loss delta=-0.0004669054683600349，mean_calibration_error delta=-0.00014320983078552896，但 ROI delta 仅为浮点噪声、upset_capture_rate_delta=0.0，因此 objective_improvement_missing
当前判断：短赔热门负 edge soft penalty 有概率质量改善价值，但不是当前核心推荐收益突破口；下一步不应默认启用该策略，应转向最终答案选择层/质量函数层，寻找能真实改变 ROI 或冷门捕捉的信号组合
README 更新 strict objective grid 用法与五季结果；该能力属于“周期质量门禁升级 / 策略晋级治理 / 热门脆弱治理”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-103 当前落地能力：

```text
新增最终答案质量信号诊断模块：build_historical_quality_signal_diagnostic_report 只分析最终答案选中的腿，按 candidate score band、component score band、reason code、probability band、odds band、model edge band 聚合命中、失误、ROI、profit/loss 与样本量
新增 CLI：nutmeg-recommendation-quality-signal-diagnostics，支持 suite manifest、输出 report、pass types、single/multiple、optimizer profile、预算、候选池限宽、market context 派生、competition 过滤、component names 与最小分组腿数
新增模型：HistoricalQualitySignalDiagnosticOptions、HistoricalQualitySignalGroup、HistoricalQualitySignalDiagnosticReport；report 同时输出 top_positive_signal_groups 与 top_negative_signal_groups，作为后续质量函数调参证据
新增确定性测试覆盖：最终答案选中腿会被按 reason code 与 component score band 聚合；competition filter；CLI 参数映射
真实 football-data.co.uk 五季质量信号报告已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_quality_signal_diagnostics.json
本轮报告覆盖 30 个 final answers、105 个 selected legs、15 个 missed legs；final_answer_hit_rate=0.6666666666666666，leg_hit_rate=0.8571428571428571，ROI=0.05017769041333331
关键发现 1：probability very_high 分组仍为正向，selected_leg_count=93，leg_hit_rate=0.8709677419354839，ROI=0.07252041201538467；因此不能简单降低所有高概率/短赔候选
关键发现 2：probability high 分组为当前最明显负向质量信号，selected_leg_count=12，leg_hit_rate=0.75，final_answer_hit_rate=0.5，ROI=-0.03509999999999991，平均 probability=0.7317149228636883，平均 model_edge=-0.042807601550992704
关键发现 3：short_price 分组仍为正 ROI，但 ROI=0.021197610772413798，低于全局 ROI=0.05017769041333331；说明短赔不是一刀切问题，而是需要结合概率段、edge 段与组合层暴露来校准
当前判断：下一步应进入组合级质量函数实验，把 probability high + negative edge + short price / scenario type / pass depth 等信号做成候选 profile，再用 historical suite gate 验证 ROI 或冷门捕捉是否真实提升
README 更新 quality-signal diagnostics 用法与五季结果；该能力属于“最终答案质量函数层 / 周期质量门禁升级 / 策略晋级治理”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-104 当前落地能力：

```text
新增最终答案质量信号惩罚的 opt-in 实验开关：HistoricalRecommendationBacktestOptions.final_answer_quality_signal_penalty
该能力只作用于 historical final-answer arbitration，不改候选生成、不改生产默认推荐；默认关闭
当前实验 profile 只惩罚最终答案中 probability in [0.65, 0.80)、decimal_odds <= 1.35、model_edge < 0.0 的选中腿，并按受影响腿数占比扣减 final_answer_score
historical-backtest CLI 新增 --final-answer-quality-signal-penalty、--final-answer-quality-signal-penalty-strength、--final-answer-quality-signal-probability-min、--final-answer-quality-signal-probability-max、--final-answer-quality-signal-max-decimal-odds、--final-answer-quality-signal-max-model-edge
backtest / comparison / suite key 已纳入 quality-signal 参数；backtest summary 记录 penalty score 与 affected leg count；suite summary 聚合 baseline/candidate affected leg count
新增确定性测试覆盖：默认关闭时不影响最终答案排序；开启后可把命中质量不足的组合降到更稳选项之后；suite summary 会汇总受影响腿数
真实 football-data.co.uk 五季 quality-signal penalty summary 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_penalty_summary.json
对照实验覆盖 30 个 slice、10738 场 fixture、32214 个 1X2 prediction；默认线 candidate_final_hit_rate=0.6666666666666666，candidate_roi=0.05017769041333339，candidate_profit_loss=3.0106614248000034
开启 strength=0.04 后 candidate_final_hit_rate 仍为 0.6666666666666666，但 candidate_roi 降至 0.023057690413333387，candidate_profit_loss 降至 1.3834614248000032；Brier delta=0.0031813477182867484，log_loss delta=0.007128094867963155，mean_calibration_error delta=0.0018331921029932396
结果：该 profile 被拒绝，原因是 ROI、profit/loss、Brier、log loss、calibration 全部回退，且 upset_capture_rate 没有改善；不得进入默认最终答案路线
当前判断：V3.1-103 找到的 probability high + negative edge 信号真实存在，但单纯组合级扣分会误伤收益；下一步应改为“候选级贡献审计 + 替换解释模拟”，先定位被替换/被保留腿的边际收益，再设计更窄的晋级 profile
README 更新 quality-signal penalty 用法与拒绝结论；该能力属于“最终答案质量函数层 / 周期质量门禁升级 / 策略晋级治理”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-105 当前落地能力：

```text
新增候选级边际贡献审计模块：build_historical_candidate_marginal_audit_report
该模块从 historical final answer 出发，对每条已选腿执行 one-leg replacement simulation：移除一条已选腿，用同一 scenario 候选池中的替代 candidate 替换，并重新计算 pass type、unit stake、budget、hit probability、ROI、risk、actual settlement
新增模型：HistoricalCandidateMarginalAuditOptions、HistoricalCandidateMarginalAuditReport、HistoricalCandidateMarginalAuditItem、HistoricalCandidateReplacementSimulation
新增 CLI：nutmeg-recommendation-marginal-contribution-diagnostics，支持 suite manifest、输出 report、pass types、single/multiple、optimizer profile、预算、候选池限宽、market context 派生、competition 过滤、max replacement candidates 与 same market type 开关
报告同时区分 model_top_replacement 与 actual_best_replacement；actual_best 是赛后 hindsight，只用于审计，不得直接作为生产替换策略
新增确定性测试覆盖：能识别被选失误腿的实际替换机会；支持 competition filter；CLI 参数映射正确
真实 football-data.co.uk 五季 marginal contribution audit 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json
本轮审计覆盖 30 个 final answers、105 个 selected legs、15 个 missed legs、439 次 replacement simulation
赛后 hindsight 层面发现 actual_replacement_opportunity_count=77，说明最终答案中确实存在大量可学习的边际替换空间
但 model_top_replacement_count=105 中，model_top_actual_improvement_count=45，model_top_actual_harm_count=25，average_model_top_profit_loss_delta=-0.5301794921276191，average_model_top_hit_probability_delta=-0.01563373855037235
当前判断：边际替换空间真实存在，但“模型当时认为最好的替换”仍不稳定，不能直接上线替换策略；下一步应把 marginal audit 结果按 pre-match 信号分组，寻找 model-top replacement 也稳定改善的窄 profile
README 更新 marginal contribution diagnostics 用法与五季结果；该能力属于“候选级贡献审计 / 最终答案质量函数层 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-106 当前落地能力：

```text
新增 marginal audit signal grouping 模块：build_historical_marginal_signal_group_report
该模块读取 HistoricalCandidateMarginalAuditReport，把 model_top_replacement 按赛前可见信号分组：competition、pass_type、mode、selected probability/odds/model edge/score、replacement probability/odds/model edge/quality、probability delta、odds delta、model edge delta，以及组合 profile
新增模型：HistoricalMarginalSignalGroupOptions、HistoricalMarginalSignalGroupReport、HistoricalMarginalSignalGroup
新增 CLI：nutmeg-recommendation-marginal-signal-groups，支持 audit report 输入、输出 report、min sample size、min improvement rate、max harm rate、min average profit/loss delta、min average hit-probability delta、是否生成 composite profile group
新增确定性测试覆盖：稳定改善的分组进入 profile_candidate；正收益但 harm rate 超限的分组进入 watchlist；CLI 参数与 audit report loader 正常
真实 football-data.co.uk 五季 marginal signal groups 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_signal_groups.json
本轮分组基于 V3.1-105 的 105 个 model_top replacement simulation，生成 52 个 signal group
accuracy-first 门槛：min_sample_size=3，min_improvement_rate=0.55，max_harm_rate=0.30，min_average_profit_loss_delta=0.0，min_average_hit_probability_delta=0.0
结果：profile_candidate_count=0，watchlist_count=1，rejected_count=51；没有任何分组同时满足收益改善与命中概率不下降
唯一 watchlist 为 replacement_quality_band:medium_high，样本数 30，improvement_rate=0.6333333333333333，harm_rate=0.16666666666666666，average_profit_loss_delta=0.04303112439999996，但 average_hit_probability_delta=-0.016327490883081178，因此不晋级
当前判断：模型 top replacement 存在弱收益信号，但会牺牲命中概率；按照用户强调的“准确！准确！再准确！”，该信号不能进入最终答案路线
下一步应转向 accuracy-preserving 的候选池/仲裁改造：只研究 hit-probability 不下降的替换机会，或从冷门能力侧建立单独的 upset-capture profile，而不是用通用 replacement quality 提升 ROI
README 更新 marginal signal grouping 用法与五季结果；该能力属于“候选级贡献审计 / 最终答案质量函数层 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-107 当前落地能力：

```text
为 marginal signal grouping 增加单替换级 accuracy-preserving 过滤门：HistoricalMarginalSignalGroupOptions.min_replacement_hit_probability_delta
该过滤门在分组前剔除 hit_probability_delta 低于阈值的 model_top_replacement；与 min_average_hit_probability_delta 不同，它约束的是每一次替换本身，而不是分组均值
CLI 新增 --min-replacement-hit-probability-delta；报告 summary 新增 source_model_top_replacement_count、evaluated_replacement_count、filtered_replacement_count
新增确定性测试覆盖：hit_probability_delta 为负的替换会被过滤；保留下来的 accuracy-preserving 但 profit/loss 变差的分组会被拒绝
真实 football-data.co.uk 五季 accuracy-preserving marginal signal groups 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_accuracy_preserving_signal_groups.json
本轮设置：min_replacement_hit_probability_delta=0.0，min_average_hit_probability_delta=0.0，min_sample_size=1，min_improvement_rate=0.55，max_harm_rate=0.30，min_average_profit_loss_delta=0.0
结果：source_model_top_replacement_count=105，evaluated_replacement_count=5，filtered_replacement_count=100，group_count=30，profile_candidate_count=0，watchlist_count=0，rejected_count=30
关键发现：仅 5 个 model-top replacement 能做到 hit probability 不下降，但 5 个全部实际损害 profit/loss；mode:single 分组 average_profit_loss_delta=-0.8684498656，harm_rate=1.0，average_hit_probability_delta=0.001742042990771453
当前判断：通用 one-leg replacement 路线在“准确性不下降”约束下被证伪；继续挤压普通替换策略不是核心突破口
下一步应转向冷门捕捉 profile：单独分析 upset opportunity / upset captured / favorite fragility miss，而不是要求普通替换同时改善 ROI 与命中率
README 更新 accuracy-preserving marginal signal grouping 用法与五季负结论；该能力属于“候选级贡献审计 / 准确性优先质量门禁 / 策略证伪”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-108 当前落地能力：

```text
新增冷门捕捉 profile 诊断模块：build_historical_upset_capture_profile_report
该模块只分析赛后证明正确的 upset opportunity，然后按最终答案生命周期口径分类为 captured、selected_wrong_fixture、not_selected；目标是找出冷门没有进入最终答案的原因，而不是向用户展示内部策略
新增模型：HistoricalUpsetCaptureProfileOptions、HistoricalUpsetCaptureProfileReport、HistoricalUpsetCaptureGroup、HistoricalUpsetOpportunityObservation
新增 CLI：nutmeg-recommendation-upset-capture-profiles，支持 suite manifest、输出 report、pass types、single/multiple、optimizer profile、预算、候选池限宽、market context 派生、competition filter、upset threshold 与 min group sample size
报告新增 selected_favorite_fragility_score 与 selected_favorite_fragility_band，用于区分“冷门机会自身信号”和“最终答案选中的热门是否脆弱”
新增确定性测试覆盖：同场选错热门会记录 selected_favorite_miss；已捕捉冷门会保留 market favorite context；完全未入选的冷门机会会进入 not_selected；CLI 参数映射正确
真实 football-data.co.uk 五季 upset capture profiles 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_capture_profiles.json
报告 report_key=historical_upset_capture_profiles:e27984fa9be71491，覆盖 30 个 final answers、6 个 competition、1340 个赛后正确冷门机会
结果：capture_count=0，capture_rate=0.0，not_selected_count=1325，selected_wrong_fixture_count=15，selected_favorite_miss_count=15
关键发现：当前最终答案路线几乎没有冷门暴露；主要问题不是“已选热门偶尔脆弱”，而是 1325/1340 的真实冷门机会完全没有进入最终答案所选 fixture
当前判断：下一步应做冷门候选进入最终答案候选池/仲裁层的受控实验，例如 upset exposure reserve 或 upset-aware final-answer candidate lane，并用 final hit、ROI、Brier/logloss、calibration、upset capture 的 no-regression gate 验证；不得直接上线高赔率/冷门 override
README 更新 upset capture profiles 用法与五季负结论；该能力属于“冷门能力强化 / 真实历史样本回测 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-109 当前落地能力：

```text
新增 historical backtest 的 opt-in upset exposure reserve：HistoricalRecommendationBacktestOptions.upset_exposure_reserve
reserve 作用于两层候选池裁剪：compressed candidate pool 与 scenario candidate pool；默认关闭，不改变生产/默认历史路线
新增参数：upset_exposure_reserve_fixture_count、upset_exposure_reserve_max_candidates_per_fixture、upset_exposure_reserve_min_protection_score、upset_exposure_reserve_min_probability、upset_exposure_reserve_max_decimal_odds
reserve 只按赛前可见信号选候选：upset protection score、probability、model edge、data quality、odds discipline；不使用赛果，不绕过开赛过滤，不实现自动下注
backtest summary、suite summary、diagnostic report 与 quality gate summary 新增 reserve candidate pool count 与 final answer selected reserve count
historical-diagnostics 与 historical-suite-gate CLI 新增 reserve 参数，便于五季冻结样本与门禁复现
新增确定性测试覆盖：默认关闭时 reserve 不改变候选池且 2x1 可因候选不足失败；开启后 reserve fixture 能进入候选池并被选择，且 captured upset count 正确；diagnostics/gate CLI 参数映射正确
真实 football-data.co.uk 五季 single-only reserve=1 诊断已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_exposure_reserve1_single_diagnostics.json
报告 report_key=historical_recommendation_diagnostic:8f9aff40905c1467，覆盖 30 个 slice、10738 场 fixture、32214 个 prediction
结果：candidate_pool_upset_exposure_reserve_candidate_count=598，但 final_answer_upset_exposure_reserve_selected_candidate_count=0
final hit、ROI、profit/loss、Brier、log loss、calibration 与 upset_capture 全部 unchanged：final_hit_rate=0.6666666666666666，ROI=0.05017769041333343，upset_capture_rate=0.0
quality gate single-only 通过 no-regression 检查，但这只是“暴露候选不伤害”的结果，不是“冷门能力改善”的结果
full single+multiple、2x1-8x1、reserve=1/4 的 solver 运行会明显变慢，说明 reserve 不能无限扩池；后续必须限制为显式 upset-aware lane 或更强 solver，而不是盲目增大候选池
当前判断：单纯把冷门放进候选池还不够，最终答案评分/选择层仍然拒绝所有 reserve legs；下一步应做 upset-aware scoring lane 或 final-answer reserve option，并要求 selected reserve count > 0 且 final hit/ROI/Brier/logloss/calibration 无回退
README 更新 upset exposure reserve 用法与五季单式结果；该能力属于“冷门能力强化 / 候选池暴露控制 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-110 当前落地能力：

```text
新增 historical backtest 的 opt-in upset-aware final-answer lane：HistoricalRecommendationBacktestOptions.upset_final_answer_lane
lane 独立于普通 compressed candidate pool，从完整赛前候选中选择满足 protection/probability/data-quality/odds/未开赛约束的冷门保护候选，并生成额外 final-answer option
新增参数：upset_final_answer_lane_pass_type、upset_final_answer_lane_mode、upset_final_answer_lane_candidate_limit、upset_final_answer_lane_min_protection_score、upset_final_answer_lane_min_probability、upset_final_answer_lane_max_decimal_odds、upset_final_answer_lane_score_boost
最终答案仲裁器支持对 upset lane option 施加 opt-in sort boost；默认 boost=0 且 lane 默认关闭，不改变既有推荐路线
backtest summary、suite summary、diagnostic report 与 quality gate summary 新增 lane candidate count、completed lane count、final-answer lane count、selected lane candidate count
historical-backtest、historical-diagnostics 与 historical-suite-gate CLI 新增 lane 参数；quality gate 新增 min_upset_final_answer_lane_selected_candidate_count，用于要求实验至少真正选择 lane 候选
新增确定性测试覆盖：lane 默认关闭时不产生候选或选中计数；开启后即使普通候选池被压缩到不含冷门候选，lane 仍可从完整赛前候选中生成最终答案，并在显式 boost 下赢得仲裁；diagnostics/gate CLI 参数映射正确
真实 football-data.co.uk 五季 single-only lane 实验已输出 3 个报告：boost=0.05、0.08、0.20
boost=0.05 报告 report_key=historical_recommendation_diagnostic:c999ba99afdefc36，生成 720 个 lane candidates、30 个 completed lane，但 final-answer lane selected count=0；final hit/ROI/Brier/logloss/calibration/upset capture 全部保持既有路线不变
boost=0.08 报告 report_key=historical_recommendation_diagnostic:be5632a578d255b3，final-answer lane selected count=2，但 final hit rate=0.6333333333333333、ROI=-0.012842309586666663、upset capture=0；严格门禁 gate_key=historical_recommendation_suite_quality_gate:2a3fdcc3fd6baf1f 因 candidate_final_hit_rate 与 candidate_roi 失败
boost=0.20 报告 report_key=historical_recommendation_diagnostic:a90f4d70a4ac452e，final-answer lane selected count=23，但 final hit rate=0.2、ROI=-0.6032312646666665；证明高强度 cold lane 会严重伤害准确性
当前判断：final-answer lane 通路已经打通且可量化，但当前简单 score boost 不可晋级；下一步应从 lane 候选质量函数入手，而不是继续加大 boost。优先研究“只允许高校准、低波动、正/近零模型边际、分联赛有效”的 cold lane profile，并以绝对命中率、ROI、Brier/logloss、calibration 与 lane selected count 同时过门禁为准
README 更新 upset-aware final-answer lane 用法与五季结果；该能力属于“冷门能力强化 / 最终答案仲裁层 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-111 当前落地能力：

```text
为 upset-aware final-answer lane 增加质量准入函数：_upset_final_answer_lane_quality_applies
新增参数：upset_final_answer_lane_min_model_edge、upset_final_answer_lane_min_calibration_score、upset_final_answer_lane_min_model_confidence_score、upset_final_answer_lane_min_odds_stability_score、upset_final_answer_lane_max_volatility_penalty
质量准入在冷门信号/probability/data-quality/odds/未开赛过滤之后执行；默认值不改变现有行为，只有显式配置后才收紧 lane 候选
historical-backtest、historical-diagnostics、historical-suite-gate CLI 均已支持上述质量参数
backtest summary、suite summary、diagnostic report 与 quality gate summary 均输出 lane 质量阈值，便于复现每个实验
新增确定性测试覆盖：强冷门信号但 model edge、calibration、confidence、odds stability、volatility 不达标时，lane 不生成候选，最终答案回退普通路线；diagnostics/gate CLI 参数映射正确
真实 football-data.co.uk 五季分布检查显示：当前冻结样本中 upset lane 候选的 calibration_score=0.70、model_confidence_score=0.66、odds_stability_score=0.72、volatility_penalty=0.08 基本为常量；现阶段真正有区分力的是 model edge、probability、decimal odds 上限
严格高质量 profile（min_model_edge=-0.02、min_calibration=0.85、min_confidence=0.85、min_odds_stability=0.70、max_volatility=0.08）生成 0 个 lane candidates，因此不能用于当前免费/冻结样本
可用数据分布 profile（min_probability=0.18、max_decimal_odds=5.0、min_model_edge=-0.008、min_calibration=0.70、min_confidence=0.66、min_odds_stability=0.72、max_volatility=0.08）在 boost=0.08/0.10 下生成 82 个 lane candidates、11 个 completed lane，但 final-answer lane selected count=0，保持既有指标不变
同一质量 profile 在 boost=0.15 下 report_key=historical_recommendation_diagnostic:1fef2c6a24ac2580，final-answer lane selected count=1，但 final hit rate=0.6333333333333333、ROI=-0.022142309586666662、upset capture=0；严格门禁 gate_key=historical_recommendation_suite_quality_gate:7e538d33fba3664a 因 candidate_final_hit_rate 与 candidate_roi 失败
当前判断：质量准入已证明可以压缩冷门候选并阻止盲目高赔率路线，但当前静态 boost 仍不能通过绝对准确性门禁；下一步应做 lane near-miss / selected-case audit，分析被普通最终答案压过的 quality lane 候选与实际赛果，而不是继续扩大 boost
README 更新 quality-gated upset lane 用法与五季结果；该能力属于“冷门能力强化 / 候选质量函数 / 最终答案仲裁层 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-112 当前落地能力：

```text
新增 upset lane selected/near-miss audit 模块：build_historical_upset_lane_audit_report
该模块对每个 historical slice 运行同一套 backtest + upset final-answer lane 配置，然后将 lane 结果分类为 selected、near_miss、failed
near_miss 口径：lane 完成但未赢最终答案仲裁，对比对象为实际 final answer；selected 口径：lane 赢仲裁，对比对象为 best non-lane answer
新增模型：HistoricalUpsetLaneAuditOptions、HistoricalUpsetLaneAuditReport、HistoricalUpsetLaneAuditObservation、HistoricalUpsetLaneAuditGroup、HistoricalUpsetLaneCandidateAudit
新增 CLI：nutmeg-recommendation-upset-lane-audit，支持 suite manifest、output path、pass types、single/multiple、optimizer profile、预算、候选池限宽、market context、lane 质量参数、focus competitions、min group sample size、top case limit
报告输出 lane rank、lane candidate count、lane selected outcomes、comparison selected outcomes、actual return/profit/ROI/hit probability/Brier/logloss/calibration deltas、final-answer score gap、候选 probability/odds/model edge/data quality/calibration/confidence/stability/volatility/protection signal
新增 group 维度：status、comparison_outcome、competition、competition_season、probability_band、odds_band、model_edge_band、score_gap_band、profile
新增确定性测试覆盖：near-miss 但事后收益改善；selected lane 与 best non-lane 对比；质量门槛导致 lane failed；CLI 参数映射正确
真实 football-data.co.uk 五季 quality lane audit 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_quality_edge008_odds5_boost015_audit.json
报告 report_key=historical_upset_lane_audit:996e9a3810322f3d，覆盖 30 个 slice、6 个 competition
结果：completed_lane_count=11、selected_lane_count=1、near_miss_count=10、failed_lane_count=19、lane_candidate_count=82
完成 lane 的实际对比：actual_improvement_count=3、actual_harm_count=6、actual_unchanged_count=2；average_profit_loss_delta=-0.19960310225454583、average_hit_probability_delta=-0.29104771694624254、average_final_answer_score_gap=0.18105677778641313
3 个收益改善 near-miss 全部落在 profile:near_miss:actual_improved:edge_neg_0_01_0:odds_3_5_5_0，average_profit_loss_delta=6.532838463999998；分别来自 GER_BUNDESLIGA 2021-2022、GER_BUNDESLIGA 2022-2023、EPL 2022-2023
唯一 selected lane 为 FRA_LIGUE_1 2023-2024 Lens vs Lyon away_win，实际 profit_loss_delta=-4.3392，说明当前 boost 会把有害 lane 推上最终答案
当前判断：不应继续提高全局 lane boost；下一步应做 competition/profile guard 实验，只允许 “edge_neg_0_01_0 + odds_3_5_5_0 + 经审计联赛/赛季 profile” 进入 lane 仲裁，并用绝对命中率/ROI/Brier/logloss/calibration/upset capture/no-regression gate 决定是否晋级
README 更新 upset lane audit 用法与五季结果；该能力属于“冷门能力强化 / selected-case audit / near-miss evidence / 质量函数证据化”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-113 当前落地能力：

```text
为 upset-aware final-answer lane 增加 competition/profile guard：upset_final_answer_lane_min_decimal_odds、upset_final_answer_lane_max_model_edge、upset_final_answer_lane_competition_ids、upset_final_answer_lane_excluded_competition_ids
profile guard 在 lane candidate applies 阶段执行，位于 allowed_markets、competition、probability、data_quality、odds、kickoff 与 quality gate 链路内；默认值为空/None，不改变既有 lane 实验行为
historical-backtest、historical-diagnostics、historical-suite-gate、upset-lane-audit CLI 均支持 --upset-final-answer-lane-min-decimal-odds、--upset-final-answer-lane-max-model-edge、--upset-final-answer-lane-competitions、--upset-final-answer-lane-excluded-competitions
backtest key、comparison key、suite key、backtest summary、suite summary、diagnostics summary 与 gate summary 均纳入新增 profile 参数，避免不同 guard 实验覆盖为同一 report
新增确定性测试覆盖：competition allowlist 会过滤 lane candidate；CLI 参数能正确映射到 backtest options；profile guard 默认不影响既有测试路径
真实 football-data.co.uk 五季 guarded Bundesliga profile 诊断已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_diagnostics.json
诊断设置：odds 3.5-5.0、model_edge -0.008 到 0.0、competition=GER_BUNDESLIGA、boost=0.25、candidate_fixture_limit=48、window4、2x1-8x1 single
报告 report_key=historical_recommendation_diagnostic:17a09b92d6017255；lane candidate count=2、completed lane count=2、selected lane candidate count=2
五季绝对指标：candidate_final_hit_rate=0.6666666666666666、candidate_roi=0.2894364904133333、candidate_profit_loss=17.366189424799998、candidate_upset_capture_rate=0.0014925373134328358
匹配质量门禁已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_gate.json；gate_key=historical_recommendation_suite_quality_gate:54a7c4112597a705，按 final hit >=0.66、ROI >=0、worst competition ROI >=-0.30、lane selected count >=1 通过
guarded audit 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_audit.json；report_key=historical_upset_lane_audit:00b63639c5ddd7d2
audit 结果：completed_lane_count=2、selected_lane_count=2、actual_improvement_count=2、actual_harm_count=0、average_profit_loss_delta=7.177764；两个 selected case 均为 GER_BUNDESLIGA 2021-2022 / 2022-2023 Mainz upset outcome
当前判断：这是第一组通过现有绝对 gate 且显著改善 ROI 的冷门 lane 窄 profile；但它的 hit_probability_delta 为负，并且相对 no-lane full-matrix baseline 的 Brier、log loss、calibration 变差，因此暂不作为默认推荐规则，只保留为 opt-in historical profile 与下一轮校准/样本扩展对象
README 更新 profile guard 用法、报告 key、gate 结果与谨慎结论；该能力属于“冷门能力强化 / final-answer lane profile guard / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-114 当前落地能力：

```text
Historical Suite Quality Gate 增加 calibration-aware profile reference gate，用于比较候选 profile 与同配置 no-lane reference，而不是只比较同一 profile 下 heuristic vs solver
run_historical_recommendation_suite_quality_gate 新增 reference_suite 参数；summary_json 输出 profile_reference_enabled、profile_reference_suite_key、reference candidate 指标与 profile_reference_deltas
CLI 新增 --profile-reference-no-upset-lane，启用后会额外跑一份同配置但 upset_final_answer_lane=false、score_boost=0 的 reference suite
新增 profile reference 阈值：min_profile_reference_final_hit_rate_delta、min_profile_reference_roi_delta、min_profile_reference_profit_loss_delta、max_profile_reference_brier_score_delta、max_profile_reference_log_loss_delta、max_profile_reference_mean_calibration_error_delta、min_profile_reference_upset_capture_rate_delta
gate_key 纳入 reference_suite_key 与所有 profile reference 阈值，避免不同 reference/gate 设置覆盖为同一门禁报告
新增确定性测试覆盖：ROI/profit 不退但 Brier/logloss/calibration 相对 reference 退化时会被阻断；reference 无退化时通过；CLI 参数映射与 no-lane reference option builder 正常
真实 football-data.co.uk 五季 strict profile gate 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_strict_profile_gate.json
strict gate 使用 V3.1-113 Bundesliga guarded profile 作为 candidate，并以 no-upset-lane full-matrix 作为 reference；gate_key=historical_recommendation_suite_quality_gate:00f30c7cc52b792b
结果按预期 failed，失败项为 profile_reference_brier_score_delta、profile_reference_log_loss_delta、profile_reference_mean_calibration_error_delta
相对 no-lane reference：final_hit_rate_delta=0.0、roi_delta=0.23925880000000002、profit_loss_delta=14.355528000000001、upset_capture_rate_delta=0.0014925373134328358，但 brier_score_delta=0.03629450461001202、log_loss_delta=0.08298307783901859、mean_calibration_error_delta=0.03256475053701974
当前判断：V3.1-113 guarded profile 有收益和冷门捕捉价值，但严格 accuracy-first 晋级标准下仍不能默认启用；下一步应继续做 calibration-preserving 的 profile/score 函数，而不是单纯提高冷门 lane boost
README 更新 strict profile gate 命令、报告 key、失败原因与不晋级结论；该能力属于“周期质量门禁升级 / 冷门 profile 晋级治理 / calibration-aware promotion gate”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-115 当前落地能力：

```text
为 upset-aware final-answer lane 增加 calibration-preserving arbitration guard：upset_final_answer_lane_max_hit_probability_deficit
该参数默认 None，不改变既有 lane 实验；显式设置后，若 lane option 的 expected hit probability 比最佳 non-lane final answer 低得超过阈值，则 lane 保留为 completed/audit evidence，但不能赢得最终答案仲裁
最终答案仲裁新增 best non-lane reference option；upset lane sort boost 会在 guard 阻断时归零，并将 blocked lane sort score 降到普通答案之后
backtest summary 新增 upset_final_answer_lane_max_hit_probability_deficit、upset_final_answer_lane_calibration_guard_blocked_option_count、final_answer_upset_final_answer_lane_hit_probability_deficit
suite summary、diagnostics summary、quality gate summary 新增 guard 阈值与 blocked option count；backtest/comparison/suite key 纳入新增 guard 参数，避免不同实验覆盖同一 report
historical-backtest、historical-diagnostics、historical-suite-gate、upset-lane-audit CLI 均支持 --upset-final-answer-lane-max-hit-probability-deficit
新增确定性测试覆盖：大 hit-probability deficit 会阻止 lane 赢最终答案；可接受 deficit 会允许 lane 继续赢；diagnostics/gate/audit CLI 参数映射正确
真实 football-data.co.uk 五季 Bundesliga guarded profile 已用 --upset-final-answer-lane-max-hit-probability-deficit 0.20 复跑
诊断报告已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_calibration_guard020_diagnostics.json
report_key=historical_recommendation_diagnostic:828b08a0ceb077be；lane candidate count=2、completed lane count=2、calibration guard blocked option count=2、selected lane count=0
五季指标回到 no-lane full-matrix baseline：candidate_final_hit_rate=0.6666666666666666、candidate_roi=0.05017769041333343、candidate_profit_loss=3.0106614248000056、candidate_brier_score=0.24445905503052764、candidate_log_loss=0.683178240140196、candidate_mean_calibration_error=0.47697612791196814、candidate_upset_capture_rate=0.0
匹配 audit 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_calibration_guard020_audit.json；report_key=historical_upset_lane_audit:4ca23f43bbc05b73
audit 结果：completed_lane_count=2、selected_lane_count=0、near_miss_count=2、actual_improvement_count=2、actual_harm_count=0、average_profit_loss_delta=7.177764、average_hit_probability_delta=-0.4884712580552938
两个 near-miss 仍是 GER_BUNDESLIGA 2021-2022 / 2022-2023 Mainz upset outcome，但 hit_probability_delta 分别为 -0.524289475240393 与 -0.45265304087019453，因此在 0.20 guard 下不得进入最终答案
profile reference gate 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_guard_ger_boost025_calibration_guard020_strict_profile_gate.json；gate_key=historical_recommendation_suite_quality_gate:a5134d72dbc423f9
该 gate passed，profile_reference_deltas 全为 0.0，且 candidate_upset_final_answer_lane_calibration_guard_blocked_option_count=2；这证明 guard 能消除已知校准回退，但不是冷门能力晋级，因为 selected lane count=0
当前判断：calibration-preserving guard 应保留为 opt-in safety rail；下一步不是放宽 guard，而是寻找 hit-probability deficit 更小、仍有 ROI/upset capture 贡献的 cold profile 或 score 函数
README 更新 guard 参数、五季诊断、audit、profile reference gate 与不晋级结论；该能力属于“冷门能力强化 / 最终答案仲裁安全阈 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-116 当前落地能力：

```text
upset lane audit 增加 profile-candidate screening，不再只列出 selected/near-miss，而是给 composite profile group 输出 decision 与 reason_codes
HistoricalUpsetLaneAuditOptions 新增 profile candidate 阈值：min_profile_candidate_sample_size、min_profile_candidate_improvement_rate、max_profile_candidate_harm_rate、min_profile_candidate_average_profit_loss_delta、min_profile_candidate_average_hit_probability_delta、max_profile_candidate_average_brier_score_delta、max_profile_candidate_average_log_loss_delta、max_profile_candidate_average_calibration_error_delta
HistoricalUpsetLaneAuditGroup 新增 improvement_rate、harm_rate、average_brier_score_delta、average_log_loss_delta、average_calibration_error_delta、decision、reason_codes
HistoricalUpsetLaneAuditReport 新增 profile_candidate_count 与 profile_candidates；summary_json 输出 profile_candidate_group_keys 与 profile_candidate_thresholds
nutmeg-recommendation-upset-lane-audit CLI 支持所有 profile-candidate 阈值参数，用于搜索低 hit-probability deficit 且不牺牲校准的冷门 profile
新增确定性测试覆盖：默认低 deficit 阈值会拒绝大命中率缺口 profile；放宽 hit delta 阈值时可标记 profile_candidate；设置 Brier delta 上限时会因 accuracy regression 拒绝；CLI 参数映射正确
真实 football-data.co.uk 五季 low-deficit profile search 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_low_deficit_profile_search.json
报告 report_key=historical_upset_lane_audit:3142dcfa4c7768ec；设置为 quality-gated lane、score_boost=0、candidate_fixture_limit=48、window4、2x1-8x1 single
结果：lane_candidate_count=82、completed_lane_count=11、selected_lane_count=0、near_miss_count=11、actual_improvement_count=3、actual_harm_count=6、actual_unchanged_count=2、average_profit_loss_delta=-0.19960310225454583、average_hit_probability_delta=-0.29104771694624254
严格 profile candidate 阈值下 profile_candidate_count=0；没有任何冷门形态同时满足收益、低命中率缺口与 Brier/logloss/calibration 不退化
最接近但被拒绝的 profile 为 profile:near_miss:actual_improved:edge_neg_0_01_0:odds_3_5_5_0；该组 3 个样本、improvement_rate=1.0、harm_rate=0.0、average_profit_loss_delta=6.532838463999998
拒绝原因：average_hit_probability_delta=-0.41282563598777067，且 average_brier_score_delta、average_log_loss_delta、average_calibration_error_delta 均为正，不能作为默认最终答案规则
当前判断：冷门能力的正确路线是继续扩大真实样本和寻找更低 hit-probability deficit 的 profile，而不是让高 ROI 个案绕过 accuracy-first 门槛
README 更新 profile-candidate screening 参数、五季搜索报告与不晋级结论；该能力属于“冷门能力强化 / 低缺口 profile 搜索 / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-117 当前落地能力：

```text
新增 upset lane profile grid 搜索模块：build_historical_upset_lane_profile_grid_report
该模块在固定历史 suite 上枚举联赛组、lane 最低概率、最低/最高赔率、model edge 区间、hit-probability deficit guard 与 lane score boost
每个 grid candidate 都复用 upset lane audit 和 profile-candidate screening，因此不会绕过 V3.1-116 的 accuracy-first 晋级条件
HistoricalUpsetLaneProfileGridReport 输出 candidate_count、accepted_count、rejected_count、best_candidate、accepted_candidates 与完整 candidate 明细
candidate status 只有在 audit 内至少出现一个 profile_candidate 时才会 accepted；否则会以 no_lane_candidates、no_completed_lane、no_profile_candidates 等 reason_codes 拒绝
新增 nutmeg-recommendation-upset-lane-profile-grid CLI，支持 none/float 网格参数、profile-candidate 阈值参数、输出 JSON 报告
新增确定性测试覆盖：满足 profile 阈值时 accepted；Brier/logloss/calibration 阈值失败时 rejected；CLI 参数映射正确
真实 football-data.co.uk 五季 grid search 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_low_deficit_v1.json
报告 report_key=historical_upset_lane_profile_grid:3f9f48455a3ce147；candidate_count=8、accepted_count=0、rejected_count=8、accepted_candidate_keys=[]
最接近候选为 GER_BUNDESLIGA、lane_min_probability=0.18、lane_max_decimal_odds=5.0、lane_min_model_edge=-0.008、lane_max_model_edge=0.0、lane_max_hit_probability_deficit=0.20、lane_score_boost=0.25
该候选 lane_candidate_count=2、completed_lane_count=2、actual_improvement_count=2、actual_harm_count=0、average_profit_loss_delta=7.177764，但 profile_candidate_count=0
拒绝原因仍是 no_profile_candidates：真实收益个案不能覆盖命中概率缺口和 Brier/logloss/calibration 退化风险
当前判断：grid search 已把冷门 profile 搜索从人工单点实验升级为可复验阈值学习工具；但本轮没有任何 profile 达到默认推荐晋级标准
README 更新 profile grid CLI、五季报告与不晋级结论；该能力属于“冷门能力强化 / threshold-learning grid / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-118 当前落地能力：

```text
upset lane profile grid report 新增聚合诊断字段：rejection_reason_counts、profile_rejection_reason_counts、competition_summary_json
rejection_reason_counts 汇总 grid candidate 层拒绝原因，例如 no_lane_candidates、no_completed_lane、no_profile_candidates
profile_rejection_reason_counts 汇总 closest rejected profile 的阈值失败原因，例如 hit_probability、Brier、log loss、calibration、profit/loss 与 improvement rate
competition_summary_json 按 competition group 汇总 candidate_count、accepted/rejected、lane candidate、completed lane、selected、near miss、actual improvement/harm/unchanged、profile candidate 与拒绝原因计数
新增确定性测试覆盖：accepted report 不产生拒绝原因；Brier/logloss/calibration 阈值失败会进入全局与联赛聚合计数
真实 football-data.co.uk 五季六联赛 narrow grid 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_six_leagues_narrow_v1.json
报告 report_key=historical_upset_lane_profile_grid:45cf062a032a0c2e；candidate_count=12、accepted_count=0、rejected_count=12、accepted_candidate_keys=[]
全局拒绝原因：no_profile_candidates=12、no_lane_candidates=8、no_completed_lane=8
profile 阈值拒绝原因：average_brier_score_delta_above_threshold=11、average_log_loss_delta_above_threshold=11、average_calibration_error_delta_above_threshold=11、average_hit_probability_delta_below_threshold=11、average_profit_loss_delta_below_threshold=9、improvement_rate_below_threshold=10
联赛摘要：EPL lane_candidate_count=72/completed=5/improvement=1/harm=3；ESP_LA_LIGA lane_candidate_count=7/completed=3/improvement=0/harm=2；GER_BUNDESLIGA lane_candidate_count=2/completed=2/improvement=2/harm=0；FRA_LIGUE_1 lane_candidate_count=1/completed=1/improvement=0/harm=1；ITA_SERIE_A 与 JPN_J1 当前阈值下 lane_candidate_count=0
最接近候选仍为 GER_BUNDESLIGA、lane_min_model_edge=-0.008、lane_min_probability=0.18、lane_max_decimal_odds=5.0、hit_probability_deficit_guard=0.20、score_boost=0.25，但 profile_candidate_count=0
尝试运行 72-candidate six-league wider grid 时串行 runner 耗时过高，已中断并改用 narrow grid；下一步若要扩大搜索范围，应先做 grid runner 缓存/并行或批量 checkpoint
当前判断：跨联赛证据没有支持任何 upset lane profile 默认晋级；德甲仍有研究价值，英超 harm 偏高，西甲/法甲当前阈值表现负向，意甲/J1 当前阈值无候选
README 更新聚合诊断字段、六联赛 narrow grid 报告和不晋级结论；该能力属于“冷门能力强化 / threshold-learning diagnostics / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-119 当前落地能力：

```text
upset lane profile grid runner 新增候选分批执行能力：candidate_start_index 与 candidate_limit
grid runner 会先生成完整稳定顺序的 candidate spec 列表，再按起始 index/limit 选择本批次执行；report 保留 total_grid_candidate_count、candidate_indices、candidate_start_index 与 candidate_limit
新增 per-candidate cache：candidate_cache_dir、read_candidate_cache、write_candidate_cache；CLI 对应 --candidate-cache-dir、--no-candidate-cache-read、--no-candidate-cache-write
candidate cache key 基于 candidate spec 与 HistoricalUpsetLaneAuditOptions 生成，不依赖报告输出路径；相同参数复跑可直接读取 candidate JSON
HistoricalUpsetLaneProfileGridCandidate 新增 candidate_index、candidate_cache_key、candidate_cache_status
HistoricalUpsetLaneProfileGridReport 新增 cache_hit_count、cache_miss_count、cache_write_count
新增确定性测试覆盖：batch 只执行指定 candidate index；首次运行写入 cache，第二次运行命中 cache，candidate key 保持一致
真实 football-data.co.uk 五季小批量 cache smoke 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_cache_batch_v1.json 与 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_cache_batch_reused_v1.json
该 smoke 使用六联赛 narrow grid 的 candidate indices [0, 1]；total_grid_candidate_count=12、candidate_count=2
首次运行 cache_hit_count=0、cache_miss_count=2、cache_write_count=2；复跑 cache_hit_count=2、cache_miss_count=0、cache_write_count=0
两次运行都 accepted_count=0，不产生任何默认推荐策略晋级；该阶段只解决大网格可恢复执行问题
当前判断：后续可以按 candidate index 分批跑更宽阈值网格，不必一次性等待完整长任务；若仍需进一步提速，再进入并行 worker 或 audit-level memoization
README 更新 batch/cache CLI、cache smoke 报告与非晋级结论；该能力属于“冷门能力强化 / threshold-learning runner / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-120 当前落地能力：

```text
新增 profile grid batch merge 能力：merge_historical_upset_lane_profile_grid_reports
新增 CLI：nutmeg-recommendation-upset-lane-profile-grid-merge，可输入多个 batch report 并输出 merged report
merge report 会按 candidate_index 排序候选，汇总 accepted/rejected、cache hit/miss/write、rejection_reason_counts、profile_rejection_reason_counts 与 competition_summary_json
summary_json 新增 source_report_count、source_report_keys、source_report_paths、missing_candidate_indices、duplicate_candidate_indices、is_full_grid
merge 会保留输入报告 warnings，并在存在重复 candidate index、缺失 candidate index、基础样本计数不一致、total_grid_candidate_count 不一致时追加 merge warning
新增确定性测试覆盖：两个 batch report 乱序输入后能按 candidate_index 合并，full grid 时 missing/duplicate 为空且 is_full_grid=true；merge CLI 参数映射正确
真实 football-data.co.uk 五季 batch merge smoke 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_batch_merge_partial_v1.json
该 smoke 合并 part0/part1 两个 batch，覆盖六联赛 narrow grid 的 candidate indices [0, 1, 2, 3]；total_grid_candidate_count=12、candidate_count=4
merged report_key=historical_upset_lane_profile_grid:6f55525248d4c09f；missing_candidate_indices=[4,5,6,7,8,9,10,11]、duplicate_candidate_indices=[]、is_full_grid=false
合并结果 accepted_count=0、rejected_count=4；cache_miss_count=4、cache_write_count=4；没有任何默认推荐策略晋级
当前判断：现在可以把宽网格拆为多个 batch 独立运行并合并审计，不再需要一次性跑完整长任务；下一阶段可以继续跑剩余 batch 或增加并行 worker
README 更新 merge CLI、partial merge smoke 报告与非晋级结论；该能力属于“冷门能力强化 / threshold-learning batch merge / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-121 当前落地能力：

```text
完成六联赛 narrow grid 的剩余 batch 执行：part2 覆盖 candidate indices [4, 5]，part3 覆盖 [6, 7]，part4 覆盖 [8, 9]，part5 覆盖 [10, 11]
完整 batch merge 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_batch_merge_full_v1.json
merged report_key=historical_upset_lane_profile_grid:95b3760460c165bd；source_report_count=6、total_grid_candidate_count=12、candidate_count=12
candidate_indices=[0,1,2,3,4,5,6,7,8,9,10,11]、missing_candidate_indices=[]、duplicate_candidate_indices=[]、is_full_grid=true
完整合并结果 accepted_count=0、rejected_count=12、accepted_candidate_keys=[]
全局拒绝原因与 direct narrow grid 一致：no_profile_candidates=12、no_lane_candidates=8、no_completed_lane=8
profile 阈值拒绝原因：average_brier_score_delta_above_threshold=11、average_log_loss_delta_above_threshold=11、average_calibration_error_delta_above_threshold=11、average_hit_probability_delta_below_threshold=11、average_profit_loss_delta_below_threshold=9、improvement_rate_below_threshold=10
最接近候选仍为 GER_BUNDESLIGA、lane_min_model_edge=-0.008、lane_min_probability=0.18、lane_max_decimal_odds=5.0、hit_probability_deficit_guard=0.20、score_boost=0.25
该最接近候选 lane_candidate_count=2、completed_lane_count=2、actual_improvement_count=2、actual_harm_count=0、average_profit_loss_delta=7.177764，但 average_hit_probability_delta=-0.4884712580552938 且 profile_candidate_count=0
当前判断：batch/cache/merge 工具链已经能完整复现 12-candidate 六联赛 narrow grid；证据仍不支持任何 upset lane profile 默认晋级
下一阶段可以用同一工具链扩大到 72-candidate wider grid，并优先复用 cache/分批 merge，而不是回到单次长任务
README 更新 full batch merge 命令、report key、完整合并指标与非晋级结论；该能力属于“冷门能力强化 / threshold-learning full batch audit / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-122 当前落地能力：

```text
开始执行 72-candidate wider grid，仍使用 batch/cache/merge 工具链，不再使用单次长任务
wider grid 当前参数：competition_groups=EPL/ESP_LA_LIGA/GER_BUNDESLIGA/ITA_SERIE_A/FRA_LIGUE_1/JPN_J1，lane_min_probability_values=[0.18,0.22]，lane_max_decimal_odds_values=[4.5,5.0]，lane_min_model_edge_values=[-0.012,-0.008,-0.004]，hit_probability_deficit_guard=0.20，score_boost=0.25
第一轮运行 part0/part1/part2/part3，覆盖 candidate indices [0..23]，即 EPL 与 ESP_LA_LIGA 两个联赛的完整 wider-grid 组合
partial merge 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_epl_laliga_partial_v1.json
partial report_key=historical_upset_lane_profile_grid:2f6173f53a87c57e；source_report_count=4、total_grid_candidate_count=72、candidate_count=24、missing_candidate_indices=[24..71]、is_full_grid=false
partial 结果 accepted_count=0、rejected_count=24、accepted_candidate_keys=[]
全局拒绝原因：no_profile_candidates=24、no_lane_candidates=11、no_completed_lane=11
profile 阈值拒绝原因：average_brier_score_delta_above_threshold=18、average_log_loss_delta_above_threshold=18、average_calibration_error_delta_above_threshold=18、average_hit_probability_delta_below_threshold=19、average_profit_loss_delta_below_threshold=11、improvement_rate_below_threshold=17
EPL summary：lane_candidate_count=266、completed_lane_count=29、actual_improvement_count=12、actual_harm_count=12、actual_unchanged_count=5、profile_candidate_count=0
ESP_LA_LIGA summary：lane_candidate_count=184、completed_lane_count=17、actual_improvement_count=0、actual_harm_count=8、actual_unchanged_count=9、profile_candidate_count=0
当前 best rejected candidate 为 EPL、lane_min_probability=0.22、lane_max_decimal_odds=5.0、lane_min_model_edge=-0.012；completed_lane_count=5、actual_improvement_count=3、actual_harm_count=1、average_profit_loss_delta=2.604468801279999、average_hit_probability_delta=-0.2796759789427041、profile_candidate_count=0
当前判断：EPL wider profile 出现了比 narrow 更有研究价值的收益信号，但仍未通过 probability-quality profile candidate 门禁；La Liga 当前 wider profile 负向明显
README 更新 wider-grid EPL/La Liga partial 命令、report key、分联赛指标与非晋级结论；该能力属于“冷门能力强化 / threshold-learning wider grid / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-123 当前落地能力：

```text
继续执行 72-candidate wider grid 的第二轮 batch，覆盖 candidate indices [24..47]，即 GER_BUNDESLIGA 与 ITA_SERIE_A 两个联赛的完整 wider-grid 组合
运行 part4/part5/part6/part7，并合并为 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_bundesliga_seriea_partial_v1.json
partial report_key=historical_upset_lane_profile_grid:9edb43d3c88221f7；source_report_count=4、total_grid_candidate_count=72、candidate_count=24、missing_candidate_indices=[0..23,48..71]、is_full_grid=false
partial 结果 accepted_count=0、rejected_count=24、accepted_candidate_keys=[]
全局拒绝原因：no_profile_candidates=24、no_lane_candidates=15、no_completed_lane=15
profile 阈值拒绝原因：average_brier_score_delta_above_threshold=21、average_log_loss_delta_above_threshold=21、average_calibration_error_delta_above_threshold=21、average_hit_probability_delta_below_threshold=24、average_profit_loss_delta_below_threshold=15、improvement_rate_below_threshold=18
GER_BUNDESLIGA summary：lane_candidate_count=189、completed_lane_count=20、actual_improvement_count=5、actual_harm_count=7、actual_unchanged_count=8、profile_candidate_count=0
ITA_SERIE_A summary：lane_candidate_count=186、completed_lane_count=14、actual_improvement_count=2、actual_harm_count=9、actual_unchanged_count=3、profile_candidate_count=0
当前 best rejected candidate 为 GER_BUNDESLIGA、lane_min_probability=0.18、lane_max_decimal_odds=5.0、lane_min_model_edge=-0.008；completed_lane_count=2、actual_improvement_count=2、actual_harm_count=0、average_profit_loss_delta=7.177764、average_hit_probability_delta=-0.4884712580552938、profile_candidate_count=0
当前判断：Bundesliga 仍有局部收益个案，但 wider profile 总体 harm 多于 improvement；Serie A 当前 wider profile 明显负向；两者都不支持默认晋级
README 更新 wider-grid Bundesliga/Serie A partial 命令、report key、分联赛指标与非晋级结论；该能力属于“冷门能力强化 / threshold-learning wider grid / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-124 当前落地能力：

```text
完成 72-candidate wider grid 的最后一轮 batch，覆盖 candidate indices [48..71]，即 FRA_LIGUE_1 与 JPN_J1 两个联赛的完整 wider-grid 组合
运行 part8/part9/part10/part11，并合并为 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_ligue1_j1_partial_v1.json
Ligue 1/J1 partial report_key=historical_upset_lane_profile_grid:f331a09f55e734e6；candidate_count=24、accepted_count=0、rejected_count=24
FRA_LIGUE_1 summary：lane_candidate_count=176、completed_lane_count=13、actual_improvement_count=1、actual_harm_count=12、actual_unchanged_count=0、profile_candidate_count=0
JPN_J1 summary：lane_candidate_count=27、completed_lane_count=5、actual_improvement_count=1、actual_harm_count=1、actual_unchanged_count=3、profile_candidate_count=0
完整 72-candidate wider grid 已合并到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_wider_full_v1.json
full report_key=historical_upset_lane_profile_grid:84aa4eb3d496c199；source_report_count=12、total_grid_candidate_count=72、candidate_count=72、missing_candidate_indices=[]、duplicate_candidate_indices=[]、is_full_grid=true
完整结果 accepted_count=0、rejected_count=72、accepted_candidate_keys=[]
全局拒绝原因：no_profile_candidates=72、no_lane_candidates=44、no_completed_lane=44
profile 阈值拒绝原因：average_brier_score_delta_above_threshold=63、average_log_loss_delta_above_threshold=63、average_calibration_error_delta_above_threshold=63、average_hit_probability_delta_below_threshold=66、average_profit_loss_delta_below_threshold=48、improvement_rate_below_threshold=57
完整 best rejected candidate 为 EPL、lane_min_probability=0.22、lane_max_decimal_odds=5.0、lane_min_model_edge=-0.012；completed_lane_count=5、actual_improvement_count=3、actual_harm_count=1、average_profit_loss_delta=2.604468801279999、average_hit_probability_delta=-0.2796759789427041、profile_candidate_count=0
当前判断：72-candidate wider grid 完整覆盖后仍无 profile 可默认晋级；EPL 是下一步最值得研究的候选，但必须先降低 hit-probability/Brier/logloss/calibration 回退，而不是放宽默认晋级门槛
README 更新 Ligue 1/J1 partial、full wider-grid report key、完整拒绝原因与非晋级结论；该能力属于“冷门能力强化 / threshold-learning full wider grid / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-125 当前落地能力：

```text
围绕完整 wider grid 的 best rejected EPL candidate 进行概率质量修正搜索，不放宽 profile candidate 门槛
EPL quality-repair grid 参数：competition_group=EPL、lane_min_probability_values=[0.22,0.24,0.26]、lane_max_decimal_odds_values=[4.5,5.0]、lane_min_model_edge_values=[-0.012,-0.008]、lane_max_hit_probability_deficit_values=[0.08,0.12,0.16,0.20]、score_boost=0.25
该 grid 共 48 个 candidate，分 8 个 batch 执行并合并为 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_epl_quality_repair_full_v1.json
full repair report_key=historical_upset_lane_profile_grid:fe5d3f5420e3a1e0；source_report_count=8、total_grid_candidate_count=48、candidate_count=48、missing_candidate_indices=[]、duplicate_candidate_indices=[]、is_full_grid=true
修正搜索结果 accepted_count=0、rejected_count=48、accepted_candidate_keys=[]
全局拒绝原因：no_profile_candidates=48、no_lane_candidates=32、no_completed_lane=32
profile 阈值拒绝原因：average_brier_score_delta_above_threshold=48、average_log_loss_delta_above_threshold=48、average_calibration_error_delta_above_threshold=48、average_hit_probability_delta_below_threshold=48、average_profit_loss_delta_below_threshold=32、improvement_rate_below_threshold=32
最佳候选仍为 EPL、lane_min_probability=0.22、lane_max_decimal_odds=5.0、lane_min_model_edge=-0.012、hit_probability_deficit_guard=0.20
该候选 completed_lane_count=5、actual_improvement_count=3、actual_harm_count=1、average_profit_loss_delta=2.604468801279999、average_hit_probability_delta=-0.2796759789427041、profile_candidate_count=0
closest rejected profile 仍为 profile:near_miss:actual_improved:edge_neg_0_01_0:odds_3_5_5_0；observation_count=3、improvement_rate=1.0、harm_rate=0.0、average_profit_loss_delta=5.338218215466665，但 average_hit_probability_delta=-0.2724297359049234、average_brier_score_delta=0.34981324821407545、average_log_loss_delta=0.8016363629551204、average_calibration_error_delta=0.2724297359049234
当前判断：单纯收紧 hit-probability deficit guard、提高最低概率阈值、收窄赔率/edge 范围，不能修复 EPL 冷门 lane 的概率质量回退；下一阶段应进入信号校准/score component 调整，而不是继续扩大同类阈值网格
README 更新 EPL quality-repair grid 参数、report key、失败原因与下一步判断；该能力属于“冷门能力强化 / probability-quality repair search / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-126 当前落地能力：

```text
新增冷门信号校准组件 nutmeg.recommendations.upset_signal_calibration
该组件把 observed cold-profile metrics 转换为 risk_score 与 reliability_score：average_hit_probability_delta、average_brier_score_delta、average_log_loss_delta、average_calibration_error_delta
Recommendation policy 新增 score component：upset_signal_calibration_risk 与 upset_signal_reliability；候选评分会扣除高风险冷门信号，不再只依赖长赔收益或 protection score
upset final-answer lane 增加前置质量过滤：upset_final_answer_lane_max_signal_calibration_risk 与 upset_final_answer_lane_min_signal_reliability_score
historical-backtest、upset-lane-audit、upset-lane-profile-grid、historical-diagnostics、historical-suite-gate CLI 均支持对应参数
summary_json 新增 final_answer_upset_final_answer_lane_signal_calibration_risk 与 final_answer_upset_final_answer_lane_signal_reliability_score，便于质量门禁与后续报告追踪
新增单元测试覆盖：观察到 hit-probability gap 的冷门 profile 会被打上校准风险并扣分；可靠 profile 保持可用；upset lane 可在候选选择前过滤高风险信号
当前判断：V3.1-126 不是让 EPL 冷门 profile 晋级，而是把上一轮发现的概率质量回退变成可执行的内部安全阈；下一步应复跑真实历史 profile grid，验证该 signal calibration 是否能减少 no_profile_candidates 与 Brier/logloss/calibration 退化
README 更新信号校准组件、CLI 参数与非晋级结论；该能力属于“冷门能力强化 / signal calibration score component / 周期质量门禁升级”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-127 当前落地能力：

```text
执行一次 stop-loss 式真实历史验证：不再扩展 48/72 candidate 网格，只复跑上一轮 EPL best-rejected cold-lane 形态
验证参数：competition_group=EPL、lane_min_probability=0.22、lane_max_decimal_odds=5.0、lane_min_model_edge=-0.012、lane_max_hit_probability_deficit=0.20、score_boost=0.25
新增 signal calibration guard：upset_final_answer_lane_max_signal_calibration_risk=0.20、upset_final_answer_lane_min_signal_reliability_score=0.80
报告已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_upset_lane_profile_grid_epl_signal_calibration_guard_v1.json
报告 report_key=historical_upset_lane_profile_grid:9c92dbfc4c4b3313；slice_count=30、fixture_count=10738、prediction_count=32214、candidate_count=1、accepted_count=0、rejected_count=1
signal calibration guard 将该形态 lane_candidate_count 收缩为 13，completed_lane_count=5、selected_lane_count=0、near_miss_count=5
结果仍为 profile_candidate_count=0；closest rejected profile 仍失败 average_hit_probability_delta、Brier、log-loss、calibration gates
closest profile 指标：observation_count=2、improvement_rate=1.0、harm_rate=0.0、average_profit_loss_delta=5.271806817599998、average_hit_probability_delta=-0.2643629363029115、average_brier_score_delta=0.3414986942503868、average_log_loss_delta=0.784471169393101、average_calibration_error_delta=0.26436293630291147
当前判断：冷门 profile search 已经进入低收益循环，应停止继续扩同类阈值网格；signal calibration guard 保留为内部安全阈，但不能证明 EPL cold profile 可晋级
下一阶段路线：转回 prediction model 与真实样本质量主线，优先提升比分概率/市场概率校准，而不是继续寻找冷门规则
README 更新 stop-loss 验证报告、report key、非晋级结论与停止 cold-lane profile-search 的决策；该能力属于“冷门能力强化 / stop-loss verification / 路线纠偏”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-128 当前落地能力：

```text
新增历史概率校准证据组件 nutmeg.accuracy.historical_probability_calibration
新增 CLI：nutmeg-accuracy-historical-probability-calibration，可读取单个 slice 或 suite manifest，并输出概率分桶校准报告
报告按 model_version、calibration_version、competition_id、market_type、outcome、probability bucket 聚合观察值
输出指标包括 expected_calibration_error、Brier score、Log loss、市场隐含概率样本数，以及 Brier/log-loss 相对 market_probability 的 delta
支持参数：market_types、bucket_size、min_bucket_sample_size、min_group_sample_size、max_expected_calibration_error、max_brier_score、max_brier_score_delta_vs_market、max_log_loss_delta_vs_market、是否合并所有联赛、top_group_limit
新增确定性测试覆盖：过度自信的 1X2 home_win bucket 会触发 needs_calibration；样本不足会进入 insufficient_samples；跨联赛聚合可合并到 ALL_COMPETITIONS；CLI 参数映射正确
真实 football-data.co.uk 五季核心 suite 报告已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_probability_calibration_v1.json
报告 report_key=historical_probability_calibration:b7cbd05db3b74567；slice_count=30、fixture_count=10738、observation_count=32214、group_count=18、bucket_count=134
整体指标：overall_expected_calibration_error=0.020886649543952595、overall_brier_score=0.19450693189653426、overall_log_loss=0.5734563773558601
市场基线对比：overall_market_brier_score=0.19468413532082038、overall_market_log_loss=0.5739664152517925
当前阈值下 groups_needing_calibration_count=0、insufficient_group_count=0；最高 ECE group 是 ITA_SERIE_A away_win，ECE=0.04035417786328266，仍低于 0.08 阈值
当前判断：football-data.co.uk 冻结 suite 当前主要是 no-vig market-implied baseline，适合作为校准基准和质量门禁，不足以证明 Nutmeg 独立预测模型已经成型
下一阶段路线：做 walk-forward Poisson / Dixon-Coles-compatible score-grid 与该 market baseline 的真实历史对比，再决定是否拟合联赛/市场级 calibration transform；不继续 cold-lane 阈值搜索
README 更新历史概率校准 CLI、报告路径、report key、核心指标与下一阶段判断；该能力属于“prediction model/sample quality 主线 / calibration evidence / 路线纠偏”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-129 当前落地能力：

```text
新增 walk-forward Poisson 历史基准组件 nutmeg.accuracy.historical_poisson_walk_forward
新增 CLI：nutmeg-accuracy-historical-poisson-walk-forward，可读取单个 slice 或 suite manifest，并输出 Poisson score-grid 与 no-vig market baseline 的真实历史对照报告
实现方式严格使用赛前可见信息：每场比赛只使用同联赛 kickoff_time_utc 之前已完成的 prior_results，先估 lambda_home/lambda_away，再生成 Poisson score grid，再从比分网格推导 1X2 概率
模型保持 Dixon-Coles v1.5 兼容：输出仍是 lambda_home/lambda_away -> score_probability_grid contract，后续可替换为低比分 Dixon-Coles tau 调整
报告输出 overall、by_competition、by_season、by_competition_season 四类分组，指标包括 hit rate、Brier score、Log loss、average actual probability、expected calibration error、skipped reason counts 与 sampled prediction payload
新增确定性测试覆盖：walk-forward Poisson 能只评估已满足 prior/team 样本门槛的 fixture，并与市场基线比较；冷启动样本会被跳过；CLI 参数映射正确
真实 football-data.co.uk 五季核心 suite 报告已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_poisson_walk_forward_v1.json
报告 report_key=historical_poisson_walk_forward:2cc340200767a5ac；slice_count=30、fixture_count=10738、validation_count=10092、skipped_count=646
跳过原因：insufficient_prior_matches=360、insufficient_team_samples=286
Poisson 当前整体指标：hit_rate=0.5073325406262386、Brier=0.6057444149168055、Log loss=1.0130755990679576、ECE=0.027728941457527193
no-vig market baseline 整体指标：hit_rate=0.5273483947681332、Brier=0.5844665736444945、Log loss=0.9815234496797939、ECE=0.01103425592844241
整体 delta：hit_rate_delta=-0.020015854141894662、brier_score_delta=0.021277841272311027、log_loss_delta=0.03155214938816375、expected_calibration_error_delta=0.016694685529084784
分联赛看 EPL、La Liga、Bundesliga、Serie A、Ligue 1、J1 均未打过 market baseline；最小 Brier 回退出现在 Serie A，brier_delta=0.017794545803710426；最大回退出现在 Bundesliga，brier_delta=0.02606328190499474
当前判断：简单 rolling team-strength Poisson 已经能形成独立 score-grid baseline，但不能进入推荐默认路径；下一阶段应先改独立模型本身，而不是对弱 baseline 做推荐层包装
下一阶段路线：优先加入 recency weighting、home/away split attack-defense、draw-rate correction，并用同一 walk-forward report 与 market baseline 比较；通过后再接 Dixon-Coles low-score tau 与 calibration transform
README 更新 walk-forward Poisson CLI、报告路径、report key、核心指标与 shadow-only 结论；该能力属于“prediction model baseline / walk-forward backtest / Dixon-Coles v1.5 compatibility”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-130 当前落地能力：

```text
在 nutmeg.accuracy.historical_poisson_walk_forward 中新增模型层 ablation 参数：lambda_method、recency_half_life_days、home_away_split_weight、draw_correction_weight
新增 lambda_method=enhanced_weighted_home_away，可用 recency weighting 与 home/away split attack-defense 估计 lambda_home/lambda_away；默认仍为 rolling_strength，保证旧报告可复现
新增 draw-rate correction：从赛前 prior_results 估计历史平局率，并按 draw_correction_weight 调整从 score grid 推导出的 1X2 draw probability，同时保持 home/away 非平概率相对比例
sampled prediction payload 新增 lambda_method、draw_rate_reference、candidate_probabilities_before_draw_correction，便于审计模型修正前后的概率变化
新增确定性测试覆盖：增强变体会记录 draw correction 前后的概率，并保持 1X2 概率归一；CLI 新参数映射正确
真实 football-data.co.uk 五季小型模型层 ablation 结论：home/away split 与 recency weighting 在当前 rolling-strength baseline 上未改善 Brier/log-loss；draw-rate correction 对 Brier/log-loss/ECE 有小幅改善
最终 draw-corrected 报告已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_poisson_walk_forward_draw_correction_v1.json
报告 report_key=historical_poisson_walk_forward:841ac3b530358e1f；validation_count=10092、skipped_count=646，样本口径与 V3.1-129 一致
draw-corrected Poisson 指标：hit_rate=0.5078279825604439、Brier=0.6043922102783101、Log loss=1.0112627965553094、ECE=0.021687848218462428
相对 V3.1-129 原始 Poisson 有改善：Brier 从 0.6057444149168055 降至 0.6043922102783101；Log loss 从 1.0130755990679576 降至 1.0112627965553094；ECE 从 0.027728941457527193 降至 0.021687848218462428；hit_rate 从 0.5073325406262386 升至 0.5078279825604439
但仍落后 no-vig market baseline：brier_score_delta=0.019925636633815635、log_loss_delta=0.029739346875515493、hit_rate_delta=-0.019520412207689297、expected_calibration_error_delta=0.010653592290020018
当前判断：draw-rate correction 值得保留为模型候选，但独立 score model 仍保持 shadow-only；不能进入最终推荐默认路径
下一阶段路线：优先实现 Dixon-Coles low-score tau / learned league-level draw correction，并继续用同一 walk-forward report 与 market baseline 对照；只有核心指标接近或超过 baseline 后才考虑推荐-path promotion
README 更新模型层 ablation CLI 参数、draw-corrected 报告路径、report key、改进幅度与 shadow-only 结论；该能力属于“prediction model improvement / model ablation / route correction”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-131 当前落地能力：

```text
在 nutmeg.accuracy.historical_poisson_walk_forward 中新增 score_grid_family 参数：poisson / dixon_coles_low_score
新增 CLI 参数 --score-grid-family 与 --dixon-coles-rho；默认仍为 poisson，保证 V3.1-129/V3.1-130 报告可复现
dixon_coles_low_score 变体复用 walk-forward lambda_home/lambda_away，只替换 score-grid 生成层，使用已有 build_dixon_coles_score_grid 的低比分 tau 修正；该 contract 与 Dixon-Coles v1.5 继续兼容
sampled prediction payload 新增 score_grid_family 与 dixon_coles_rho，方便审计同一 lambda 下 Poisson grid 与 Dixon-Coles grid 的差异
新增确定性测试覆盖：Dixon-Coles grid 变体能记录 rho、保持 1X2 概率归一；CLI 参数映射正确
真实 football-data.co.uk 五季 rho 对照结果：纯 Dixon-Coles tau 未全面优于 draw-corrected Poisson；Dixon-Coles + draw correction 在 Brier/ECE 上有小幅增益，但 Log loss / hit rate 没有全面改善
最终报告已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_dixon_coles_low_score_draw_correction_v1.json
报告 report_key=historical_poisson_walk_forward:2d013c7606569252；score_grid_family=dixon_coles_low_score、dixon_coles_rho=-0.05、draw_correction_weight=0.40、validation_count=10092、skipped_count=646
Dixon-Coles draw-corrected 指标：hit_rate=0.5075307173999207、Brier=0.604297481894781、Log loss=1.0114250769828232、ECE=0.019689866978712472
相对 V3.1-130 draw-corrected Poisson：Brier 从 0.6043922102783101 降至 0.604297481894781；ECE 从 0.021687848218462428 降至 0.019689866978712472；但 Log loss 从 1.0112627965553094 升至 1.0114250769828232，hit_rate 从 0.5078279825604439 降至 0.5075307173999207
相对 no-vig market baseline 仍落后：brier_score_delta=0.01983090825028655、log_loss_delta=0.029901627303029366、hit_rate_delta=-0.019817677368212494、expected_calibration_error_delta=0.008655611050270063
当前判断：Dixon-Coles low-score tau 已经进入可重复 benchmark harness，但仍不是推荐-path promotion signal；不进入最终答案引擎默认路径
下一阶段路线：学习 league-level draw/rho 参数或 rolling training-window 参数，而不是手动固定一个全局 rho；继续用同一 walk-forward report 对照 market baseline
README 更新 Dixon-Coles low-score CLI 参数、报告路径、report key、指标对比与 shadow-only 结论；该能力属于“Dixon-Coles compatibility / score-grid model ablation / prediction accuracy mainline”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-132 当前落地能力：

```text
新增联赛级参数学习组件 nutmeg.accuracy.historical_poisson_parameter_learning
新增 CLI：nutmeg-accuracy-historical-poisson-parameter-learning，可按 competition 将历史 slice 分为 training seasons 与 holdout validation seasons
训练阶段在每个联赛的早期赛季上评估参数候选，并按 selection_metric 选择候选；验证阶段仅在该联赛 holdout 最新赛季上评估，避免同一批样本自我奖励
参数候选覆盖 Poisson draw correction 与 Dixon-Coles low-score rho + draw correction；默认候选：draw_correction_weight=[0.0,0.4]、dixon_coles_rho=[-0.1,-0.05,0.05]
报告输出每个联赛的 training_seasons、validation_seasons、selected_candidate、training metric、holdout validation metric、overall held-out validation metric 与 selected_candidate_counts
新增确定性测试覆盖：三赛季样本会用前两季训练、最后一季 holdout 验证；训练赛季不足会跳过；CLI 参数映射正确
真实 football-data.co.uk 五季核心 suite 报告已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_league_parameter_learning_v1.json
报告 report_key=historical_poisson_parameter_learning:5e51516b78a44d66；competition_count=6、learned_competition_count=6、candidate_count=8、validation_count=2062
各联赛均完成学习：EPL/La Liga/Bundesliga/Serie A/Ligue 1 使用 2020-2024 四季训练、2024-2025 holdout；J1 使用 2021-2024 训练、2025 holdout
selected_candidate_counts：dc_rho_0_05_draw_0_4=1、dc_rho_neg_0_1_draw_0_4=2、dc_rho_neg_0_05_draw_0_4=1、dc_rho_neg_0_1_draw_0_0=1、poisson_draw_0_4=1
整体 holdout candidate 指标：hit_rate=0.5155189136760426、Brier=0.5963543439254799、Log loss=0.9979609649544126、ECE=0.03948378116718108
整体 holdout market baseline 指标：hit_rate=0.5368574199806013、Brier=0.5790496105941644、Log loss=0.9730819333695456、ECE=0.03676958063070931
整体 holdout delta：hit_rate_delta=-0.02133850630455869、brier_score_delta=0.017304733331315547、log_loss_delta=0.02487903158486693、expected_calibration_error_delta=0.0027142005364717697
当前判断：league-level 参数学习框架成立，但当前独立 score model 在真正 holdout 上仍未打过 no-vig market baseline；不能进入推荐默认路径
下一阶段路线：不要继续只调 rho/draw weight，应补强模型输入特征：team form splits、rest/travel congestion、injury/lineup placeholder、odds movement / market drift features，并继续用 holdout parameter-learning 与 walk-forward report 做硬门禁
README 更新 league-level parameter-learning CLI、报告路径、report key、holdout 指标与 shadow-only 结论；该能力属于“model parameter learning / holdout validation / prediction accuracy mainline”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-133 当前落地能力：

```text
在 nutmeg.accuracy.historical_poisson_walk_forward 中新增 lambda_method=form_rest_adjusted
该方法以 enhanced_weighted_home_away lambda 为基础，新增近期状态与休息/赛程拥挤特征调整：form_window_matches、form_adjustment_weight、rest_adjustment_weight、rest_reference_days、max_lambda_adjustment
近期状态特征包括最近 N 场 points_per_match 与 goal_difference_per_match；休息特征来自当前 fixture kickoff 前最近一场比赛的 rest_days
sampled prediction payload 与 GoalLambdaEstimate.metadata_json 记录 home/away form sample、points per match、goal difference per match、rest days、form/rest/total lambda adjustment factor
新增 CLI 参数：--form-window-matches、--form-adjustment-weight、--rest-adjustment-weight、--rest-reference-days、--max-lambda-adjustment
新增确定性测试覆盖：form_rest_adjusted 能记录近期状态和休息特征，并保持 1X2 概率归一；CLI 新参数映射正确
真实 football-data.co.uk 五季小型 form/rest ablation 已完成：权重为 0 时复现 V3.1-130 draw-corrected Poisson；非零 form/rest 调整未改善 Brier、Log loss 或 ECE
代表性 shadow 报告已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_form_rest_feature_ablation_v1.json
报告 report_key=historical_poisson_walk_forward:7197442bc806ff75；lambda_method=form_rest_adjusted、form_window_matches=6、form_adjustment_weight=0.05、rest_adjustment_weight=0.0、draw_correction_weight=0.40、validation_count=10092、skipped_count=646
form/rest shadow 指标：hit_rate=0.5071343638525565、Brier=0.6046054175361606、Log loss=1.0118793885213073、ECE=0.0232334508477062
相对 V3.1-130 zero-weight draw-corrected Poisson，指标回退：Brier 从 0.6043922102783101 升至 0.6046054175361606；Log loss 从 1.0112627965553094 升至 1.0118793885213073；ECE 从 0.021687848218462428 升至 0.0232334508477062；hit_rate 从 0.5078279825604439 降至 0.5071343638525565
相对 no-vig market baseline 仍落后：brier_score_delta=0.02013884389166609、log_loss_delta=0.03035593884151344、hit_rate_delta=-0.02021403091557672、expected_calibration_error_delta=0.01219919491926379
当前判断：form_rest_adjusted 是必要的可审计特征 harness，但粗粒度赛果 form/rest 特征不能进入推荐默认路径；继续保持 shadow-only
下一阶段路线：不要继续放大粗粒度 form 权重；优先补齐真正赛前信息的样本结构，包括 lineup/injury/news 结构化输入、pre-match odds movement time series 与可复现的 feature snapshot，再进入 holdout 门禁
README 更新 form/rest CLI、报告路径、report key、指标对比与 shadow-only 结论；该能力属于“model input feature harness / prediction accuracy mainline”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-134 当前落地能力：

```text
新增结构化赛前特征快照 schema：PrematchLineupFeature、PrematchAvailabilityFeature、PrematchOddsMovementPoint、PrematchOddsMovementFeature、PrematchSemanticSignal、StructuredPrematchFeatureSet
新增 build_structured_prematch_feature_snapshot，可生成标准 FeatureSnapshot，并把阵容、伤停/停赛、赔率时间序列与语义信号统一写入 features_json.prematch_context
结构化 payload 会输出 data_quality、as_of_time_guard、lineup、availability、odds_movement summaries、semantic_signals 与 risk_signals
odds_movement summary 记录 opening/current probability、probability_delta、opening/current decimal odds、decimal_odds_delta、movement_direction、probability_range、bookmaker_disagreement、market_delay_signal 与原始 points
risk_signals 记录 lineup_schedule_risk、market_volatility_score、semantic_pressure_signal_count 与 semantic_pressure_max_confidence
source_snapshot_refs["prematch"] 记录 lineup、availability、odds movement point refs 与 semantic signal source，保证后续可审计
HistoricalFixture 新增可选 feature_snapshot 字段；旧历史 slice 不带该字段仍兼容
historical slice CSV builder 新增可选 feature_snapshot_json 列，可携带完整 serialized FeatureSnapshot；builder 会校验 fixture_id 匹配，并在 summary_json 输出 feature_snapshot_fixture_count
新增确定性测试覆盖：结构化 feature snapshot 能汇总 lineup/news/odds movement；历史 CSV builder 能接收 feature_snapshot_json 并保持 backtest-compatible
当前判断：这是真正赛前信息进入可回测链路的 schema 基础，不是模型 promotion；默认推荐路径不直接使用这些信号
下一阶段路线：用真实或可复现的历史样本填充 lineup/injury/news/odds movement，做 feature completeness gate 与 walk-forward/holdout 对照，确认信号方向后再进入 lambda adjustment 或推荐候选质量函数
README 更新结构化 prematch feature snapshot、feature_snapshot_json CSV 样本格式与当前 shadow-only 结论；该能力属于“feature snapshot structure / historical sample format / prediction accuracy mainline”，不接实时 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-135 当前落地能力：

```text
新增历史结构化赛前特征完整性门禁 nutmeg.recommendations.historical_feature_completeness
新增 CLI：nutmeg-recommendation-historical-feature-completeness，可读取单个 historical slice 或 suite manifest，并输出 feature completeness gate 结果
门禁只读取冻结 HistoricalRecommendationSlice，不调用 Provider，不连接 VPS，不评价推荐命中率/ROI，不做模型 promotion
检查项包括 fixture_count、feature_snapshot_coverage、prematch_context_coverage、lineup_coverage、availability_coverage、odds_movement_coverage、semantic_signal_coverage、source_ref_coverage、feature_after_prediction_count、feature_not_before_kickoff_count、average/minimum feature data quality
支持阈值参数：min_feature_snapshot_coverage、min_lineup_coverage、min_availability_coverage、min_odds_movement_coverage、min_semantic_signal_coverage、min_source_ref_coverage、min_average_feature_data_quality_score、min_feature_data_quality_score
默认要求 feature_snapshot_coverage=1.0 与 prematch_context 存在；具体 lineup/injury/news/odds movement 覆盖率按实验目的显式配置
支持 --output-path 保存 JSON 报告，支持 --no-fail-process 用于审计旧 slice，不让缺失结构化特征中断流水线
新增确定性测试覆盖：完整结构化 prematch slice 通过门禁；缺失 feature_snapshot、缺失 availability/semantic、feature_time 晚于 prediction_time 会失败；suite 聚合失败切片；CLI 参数映射
当前判断：这是 feature sample 进入 walk-forward/holdout 前的前置质量门，不是准确性指标；旧 football-data.co.uk slice 未携带 feature_snapshot_json，预期会失败该门禁
下一阶段路线：生成一小组可复现的 enriched historical feature fixture，用该门禁先通过样本完整性，再把结构化特征接入 walk-forward / holdout ablation，验证是否改善 Brier、Log loss、命中率和冷门捕捉率
README 更新 feature completeness CLI、检查口径与旧 slice 预期失败说明；该能力属于“feature completeness gate / historical sample quality / prediction accuracy mainline”，不接实时 API，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-136 当前落地能力：

```text
新增 deterministic enriched historical feature sample builder：nutmeg.recommendations.historical_feature_sample_builder
新增 CLI：nutmeg-recommendation-enriched-feature-sample，可生成本地 enriched HistoricalRecommendationSlice、feature completeness report 与 suite manifest
样本包含 6 个 synthetic fixture，每个 fixture 都携带结构化 FeatureSnapshot：lineup、availability、odds movement time series、semantic/news signal、source refs、data_quality 与 risk_signals
样本覆盖稳定热门、热门脆弱、客队价值漂移、确认阵容强势、平局风险、客队热门带压力等 feature_signal_intent，用于后续 ablation smoke，而不是用于模型晋级证据
生成 slice：configs/recommendations/historical_slices/enriched_features/nutmeg_enriched_prematch_feature_sample_v1.json
生成 suite manifest：configs/recommendations/historical_suites/nutmeg_enriched_prematch_feature_suite.json
生成 completeness report：configs/recommendations/historical_reports/nutmeg_enriched_prematch_feature_completeness_v1.json
completeness_key=historical_feature_completeness:nutmeg_enriched_prematch_feature_sample_v1:4b546bf8b7b4738d
该 enriched sample 通过 strict completeness gate：fixture_count=6、feature_snapshot_coverage=1.0、lineup_coverage=1.0、availability_coverage=1.0、odds_movement_coverage=1.0、semantic_signal_coverage=1.0、source_ref_coverage=1.0
新增确定性测试覆盖：builder 返回 gate-passing slice；CLI 能写出 slice/report/manifest；CLI 参数映射正确
当前判断：这是结构化赛前特征链路的可复现 smoke sample，不是真实历史准确性证据；不能据此 promotion 模型或推荐策略
下一阶段路线：把 enriched feature payload 接入 walk-forward / holdout ablation 的 shadow 特征读取层，先在 synthetic sample 上验证方向，再等待真实 provider 历史样本扩展
README 更新 enriched feature sample CLI、生成路径、completeness key 与 shadow-only 结论；该能力属于“enriched feature sample / feature completeness gate / prediction accuracy mainline”，不接实时 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-137 当前落地能力：

```text
新增 structured prematch feature shadow ablation：nutmeg.accuracy.historical_prematch_feature_ablation
新增 CLI：nutmeg-accuracy-prematch-feature-ablation，可读取 historical slice 或 suite manifest，并输出结构化赛前特征的 shadow accuracy 对照报告
该报告只读取 frozen HistoricalFixture.feature_snapshot.features_json.prematch_context，不调用 Provider，不连接 VPS，不改变推荐默认路径，不做模型 promotion
特征读取层会抽取 tracked_outcome、tracked_outcome_fragility_score、favorite_fragility_score、lineup_strength_score、draw_risk_score、market_volatility_score、lineup_schedule_risk、key_player_absence_score、odds_movement_probability_delta、semantic_risk_score 与 source_ref_count
概率调整层只在 shadow candidate 中应用：odds_movement_shift、tracked_outcome_fragility_shift、lineup_strength_shift、draw_risk_shift；每场 fixture 保留 raw_shifts、capped_shifts、reason_codes 与 shadow_only=true
报告输出 overall / competition / season / competition_season 的 candidate vs baseline Brier、Log loss、hit rate、average_actual_probability、ECE 与 deltas
生成 synthetic smoke 报告：configs/recommendations/historical_reports/nutmeg_enriched_prematch_feature_ablation_v1.json
report_key=historical_prematch_feature_ablation:b878f826577c892c
deterministic enriched sample 结果：validation_count=6、skipped_count=0、candidate_hit_rate=0.8333333333333334、baseline_hit_rate=0.6666666666666666、candidate_brier=0.44620143425059156、baseline_brier=0.4938333333333333、candidate_log_loss=0.7882092451011932、baseline_log_loss=0.8545397472949539、candidate_ece=0.24920562935895518、baseline_ece=0.37333333333333335
新增确定性测试覆盖：enriched sample 能被 feature ablation 读取并改善 synthetic smoke 指标；缺失 feature_snapshot 的 slice 会被跳过；CLI 参数映射正确
当前判断：这是结构化赛前信息进入可审计准确性报告的第一步，只能证明 feature payload -> shadow adjustment -> metric report 的链路成立；因为样本仍是 synthetic，不能作为真实准确率证据，也不能进入推荐默认路径
下一阶段路线：把真实 frozen historical sample 扩展到 feature_snapshot_json，至少先做小规模真实赛前特征切片，再用 feature completeness gate、prematch feature ablation、walk-forward / holdout report 三者共同判断是否值得进入 lambda adjustment 或推荐候选质量函数
README 更新 prematch feature ablation CLI、报告路径、report key、synthetic smoke 指标与 shadow-only 结论；该能力属于“structured feature reading layer / shadow feature ablation / prediction accuracy mainline”，不接实时 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-138 当前落地能力：

```text
新增真实 frozen market-movement feature sample builder：nutmeg.recommendations.football_data_co_uk_feature_sample
新增 CLI：nutmeg-recommendation-football-data-co-uk-feature-sample，可从本地 football-data.co.uk CSV 生成携带 FeatureSnapshot 的 HistoricalRecommendationSlice、feature completeness report 与 suite manifest
该 builder 使用 opening no-vig 1X2 概率作为 frozen baseline prediction，把 opening-to-closing 1X2 odds movement 写入 FeatureSnapshot.features_json.prematch_context.odds_movement；closing/current movement 只作为结构化 feature，不直接替换默认推荐路径
生成真实小样本：configs/recommendations/historical_slices/enriched_features/football_data_co_uk_epl_2024_2025_market_features_v1.json
生成 suite manifest：configs/recommendations/historical_suites/football_data_co_uk_market_feature_sample_suite.json
生成 completeness report：configs/recommendations/historical_reports/football_data_co_uk_epl_2024_2025_market_feature_completeness_v1.json
生成 shadow ablation report：configs/recommendations/historical_reports/football_data_co_uk_epl_2024_2025_market_feature_ablation_v1.json
completeness_key=historical_feature_completeness:football_data_co_uk_epl_2024_2025_market_features_v1:c1d8e51fa0b1f90d
真实 EPL 2024-2025 前 24 场样本通过 market-feature completeness gate：fixture_count=24、feature_snapshot_coverage=1.0、prematch_context_coverage=1.0、odds_movement_coverage=1.0、source_ref_coverage=1.0、average/min feature_data_quality_score=73.5
lineup_coverage=0.0、availability_coverage=0.0、semantic_signal_coverage=0.0 是有意保留的真实来源限制；football-data.co.uk CSV 不提供真实阵容、伤停或新闻语义信号，不能用中性占位伪装成真实覆盖
修正 build_structured_prematch_feature_snapshot 的 risk signal：缺失 lineup/availability/semantic source 时，不再把数据缺失误当作 lineup_schedule_risk；缺失只反映在 data quality
修正 prematch feature ablation 的 tracked_outcome 选择：当一个 fixture 有完整 1X2 odds movement 时，优先选择绝对 probability_delta 最大的 outcome，而不是固定读取第一条 movement
真实 24 场 shadow ablation 结果：candidate_hit_rate=0.6666666666666666、baseline_hit_rate=0.625；但 candidate_brier=0.47978713153959185、baseline_brier=0.4795315326263354；candidate_log_loss=0.82791739935502、baseline_log_loss=0.8277912610283363；candidate_ece=0.11932341264735305、baseline_ece=0.117560706129223
当前判断：真实 market movement feature 链路已打通，但证据混合，只有 hit rate 小幅提升，Brier/Log loss/ECE 轻微回退；不能进入推荐默认路径或模型 promotion
下一阶段路线：扩大真实 feature sample 到更多 EPL/五大联赛/J1 season slice，并做参数网格/校准门禁；只有在 Brier、Log loss、ECE、hit rate、ROI/最终答案质量同时不退化时，才考虑把 market movement 引入 lambda adjustment 或推荐候选质量函数
README 更新 football-data.co.uk feature sample CLI、生成路径、completeness 结果、真实 24 场 ablation 指标与 shadow-only 结论；该能力属于“real frozen feature sample / market movement feature / prediction accuracy mainline”，不接实时 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-139 当前落地能力：

```text
新增 football-data.co.uk market-feature 批量生成器：nutmeg.recommendations.football_data_co_uk_feature_sample.build_football_data_co_uk_prematch_feature_batch
新增 CLI：nutmeg-recommendation-football-data-co-uk-feature-batch，可批量读取多个本地 football-data.co.uk CSV，并为每个联赛/赛季生成携带 FeatureSnapshot 的 HistoricalRecommendationSlice、feature completeness report 与 suite manifest
批量生成器会自动从文件名映射五大联赛 competition_id：E0=EPL、SP1=LA_LIGA、D1=BUNDESLIGA、I1=SERIE_A、F1=LIGUE_1；从目录名映射 season：2021=2020-2021、2122=2021-2022 等
当前真实批量样本输出到 configs/recommendations/historical_slices/enriched_features/football_data_co_uk_market_features_multi/
当前 suite manifest 输出到 configs/recommendations/historical_suites/football_data_co_uk_market_feature_multi_season_suite.json
当前 completeness reports 输出到 configs/recommendations/historical_reports/football_data_co_uk_market_features_multi/
批量样本覆盖五大联赛 5 个本地赛季，共 25 slices、600 fixtures、25 个 completeness report 全部通过 market-feature gate；row_count=8982，failed_input_count=0
日本 J1 暂未纳入该 market-movement suite：本地 JPN.csv 对当前 feature path 只有 closing-style odds columns，缺少 opening-to-closing pair；后续需要独立 closing-only 实验或更完整数据源，不能伪造成 opening movement
新增 prematch feature 参数网格报告：nutmeg.accuracy.historical_prematch_feature_ablation_grid
新增 CLI：nutmeg-accuracy-prematch-feature-ablation-grid，可在 historical slice 或 suite manifest 上枚举 max_probability_shift、odds_movement_weight、tracked_fragility_weight、lineup_strength_weight、draw_signal_weight，并对每组参数运行 shadow-only feature ablation
网格报告使用非退化门禁：Brier、Log loss、ECE 默认不得回退，hit-rate 可设置最低 delta；输出 best_candidate、best_brier_candidate、best_hit_rate_candidate、candidate_count、non_regression_candidate_count 与每个候选参数载荷
当前真实 25-slice grid 报告输出到 configs/recommendations/historical_reports/football_data_co_uk_market_feature_ablation_grid_v1.json
report_key=historical_prematch_feature_ablation_grid:a8e20d22f795bdc3；candidate_count=144、non_regression_candidate_count=127、validation_count=600、skipped_count=0
最佳 shadow 参数：max_probability_shift=0.08、odds_movement_weight=0.5、tracked_fragility_weight=1.0、draw_signal_weight=0.35、lineup_strength_weight=0.0
最佳 shadow 结果相对 opening no-vig baseline 全面小幅改善：hit_rate 0.5416666666666666 -> 0.5533333333333333；Brier 0.5715089430682542 -> 0.5705712576436532；Log loss 0.9607358728994643 -> 0.9592187227885163；ECE 0.053777544137493485 -> 0.04884178687920516
新增确定性测试覆盖：batch builder 可写出多 slice suite 并正确映射 competition/season；batch CLI 参数映射正确；prematch feature ablation grid 能排序 shadow candidates；grid CLI 参数映射正确
当前判断：批量真实 market movement + 参数网格是准确性主线的重要进展，但仍只允许 shadow-only；它使用市场派生 movement，不包含真实 lineup/injury/news，不得进入最终推荐默认路径
下一阶段路线：把该 grid 结果接入周期质量门禁和最终答案回测；继续寻找真实 lineup/injury/news 历史样本；只有在 held-out final-answer quality、ROI、冷门捕捉率与校准指标不退化时，才考虑进入推荐候选质量函数
README 更新 batch CLI、grid CLI、生成路径、report key、指标改善、J1 暂不纳入口径与 shadow-only 结论；该能力属于“real historical feature sample expansion / parameter grid / prediction accuracy mainline”，不接实时 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-140 当前落地能力：

```text
新增 prematch feature final-answer gate：nutmeg.recommendations.historical_prematch_feature_final_answer_gate
新增 CLI：nutmeg-recommendation-historical-prematch-feature-final-answer-gate，可读取 historical slice 或 suite manifest，并可读取已有 prematch feature ablation grid report
该 gate 会选择 grid report 中排名靠前且通过单场非退化门禁的候选参数，生成 shadow-only 调整版 HistoricalRecommendationSlice；调整只写入 slice 副本，不改变原始样本或默认推荐路径
shadow 调整会把 FeatureSnapshot 读出的候选 1X2 概率写回 HistoricalMarketPrediction.probability，并重算 model_edge；原始 probability 保留在 metadata_json.prematch_feature_shadow_baseline_probability，所有调整标记 shadow_only=true
每个候选参数都会重新运行 final-answer historical backtest：baseline=原始 opening no-vig 概率，candidate=feature shadow 调整概率；两者使用相同 optimizer_profile，避免把 solver 差异混入 feature 评估
每个候选 suite 都接入已有 historical recommendation suite quality gate，使用 final-answer-only 口径检查 final_hit_rate、ROI、profit/loss、Brier、Log loss、mean calibration error、suite_status 等门禁
新增确定性测试覆盖：enriched feature grid candidate 能生成 shadow slice 并进入 final-answer gate；CLI 参数映射正确
当前真实报告输出到 configs/recommendations/historical_reports/football_data_co_uk_market_feature_final_answer_gate_v1.json
report_key=historical_prematch_feature_final_answer_gate:306b253b38ca326d；grid_report_key=historical_prematch_feature_ablation_grid:a8e20d22f795bdc3；evaluated_candidate_count=5；slice_count=25；fixture_count=600
结果：passing_candidate_count=0；前 5 个 grid 候选全部被 final-answer quality gate 拦截，suite_status=mixed
最佳 final-answer 候选为 grid rank 2 / candidate_0140：final_hit_rate 0.60 -> 0.64，ROI -0.07 -> 0.048，profit_loss_delta=5.9，final_hit_count_delta=1
但同一候选 final-answer calibration 指标回退：Brier delta=0.010490767824201636，Log loss delta=0.02175303651542737，mean_calibration_error_delta=0.009851059345951763；strict gate 失败项包括 suite_status、brier_score_delta、log_loss_delta、mean_calibration_error_delta
当前判断：V3.1-139 的单场 1X2 指标改善不能直接转化为最终答案 promotion；final-answer gate 正确阻止了“命中率/ROI 看起来提高但校准退化”的参数进入默认路径
下一阶段路线：不要推广当前 market movement shadow 参数；应把 final-answer gate 纳入周期质量门禁，并继续寻找能同时改善 final_hit_rate、ROI、Brier、Log loss、calibration 和冷门捕捉率的真实特征，尤其是真实 lineup/injury/news 与 held-out 切片
README 更新 final-answer gate CLI、报告路径、report key、最终答案指标与拦截原因；该能力属于“final-answer-only quality gate / promotion guardrail / prediction accuracy mainline”，不接实时 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-141 当前落地能力：

```text
新增 prematch feature quality cycle：nutmeg.recommendations.historical_prematch_feature_quality_cycle
新增 CLI：nutmeg-recommendation-historical-prematch-feature-quality-cycle，用于把 prematch feature final-answer gate 接入可周期运行的紧凑质量门禁
cycle runner 可直接读取 historical slice / suite manifest 与 grid report 重新运行 final-answer gate，也可读取已有 final-answer gate report 生成轻量周期摘要，避免每次都把完整 14MB gate 结果嵌入周期报告
周期结果只输出 cycle_key、status、passed、gate report key、grid report key、slice/fixture/evaluated/passing count、最佳候选、失败质量检查、核心 delta、warnings 与 summary_json
默认要求 passing_candidate_count > 0；若 final-answer gate 没有任何可推广候选，cycle status=failed，并输出 prematch_feature_quality_cycle:no_passing_final_answer_candidate
新增 deterministic unit tests 覆盖：周期 runner 汇总 gate 并通过、已有 gate 报告无 passing candidate 时失败、CLI 参数映射到 final-answer gate 与 cycle options
当前真实周期报告输出到 configs/recommendations/historical_reports/football_data_co_uk_market_feature_quality_cycle_v1.json
cycle_key=historical_prematch_feature_quality_cycle:df81abdec5044134；status=failed；final_answer_gate_report_key=historical_prematch_feature_final_answer_gate:306b253b38ca326d；grid_report_key=historical_prematch_feature_ablation_grid:a8e20d22f795bdc3
该周期覆盖 25 slices / 600 fixtures / 5 evaluated candidates；passing_candidate_count=0
最佳候选仍为 grid rank 2 / candidate_0140；命中率与 ROI 改善但失败检查为 suite_status、brier_score_delta、log_loss_delta、mean_calibration_error_delta
当前判断：周期质量门禁已能把“看起来提高命中率/ROI但校准退化”的 shadow feature 候选持续阻断；该能力是 promotion guardrail，不改变默认推荐路径
下一阶段路线：继续寻找真实 lineup/injury/news 与 held-out 特征样本，并把未来新特征候选统一跑过这个 cycle；只有 cycle 通过时才讨论进入推荐候选质量函数
README 更新 quality cycle CLI、报告路径、cycle key 与 failed gate 结论；该能力不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-142 当前落地能力：

```text
新增 frozen prematch context enrichment：nutmeg.recommendations.historical_prematch_context_enrichment
新增 CLI：nutmeg-recommendation-historical-prematch-context-enrich，可把 reviewed local CSV 中的 lineup、availability/injury、semantic/news 三类赛前结构化信息合并进已有 HistoricalRecommendationSlice
该合并器不调用 Provider、不连接 VPS、不抓取网页、不改变默认推荐路径；输入必须是已经冻结和可复核的本地 CSV
CSV 合并后会为每个 fixture 生成标准 FeatureSnapshot.features_json.prematch_context，并复用 build_structured_prematch_feature_snapshot 的 data_quality、risk_signals 与 source_snapshot_refs 结构
支持保留已有 odds_movement、lineup、availability、semantic_signals；新 lineup/availability 默认覆盖同 fixture 最新 snapshot，semantic signals 去重追加
合并器会输出未知 fixture、重复 snapshot、source time 晚于 prediction/kickoff、feature completeness failed checks 等 warnings，避免静默污染历史样本
新增 deterministic unit tests 覆盖：lineup/availability/news CSV 合并、现有 odds_movement 保留、backtest 兼容、未知 fixture warning、CLI 参数映射
新增本地 context sample CSV：configs/recommendations/historical_feature_inputs/euro_2024_knockout_lineup_context_sample.csv、availability_context_sample.csv、semantic_context_sample.csv
生成 builder base slice：configs/recommendations/historical_slices/enriched_features/euro_2024_knockout_builder_base_v1.json
生成 enriched slice：configs/recommendations/historical_slices/enriched_features/euro_2024_knockout_prematch_context_enriched_v1.json
生成 completeness report：configs/recommendations/historical_reports/euro_2024_knockout_prematch_context_completeness_v1.json
生成 suite manifest：configs/recommendations/historical_suites/euro_2024_knockout_prematch_context_suite.json
当前本地样本覆盖 2 fixtures，feature completeness passed；lineup_coverage=1.0、availability_coverage=1.0、semantic_signal_coverage=1.0、source_ref_coverage=1.0、minimum_feature_data_quality_score=72.8、average_feature_data_quality_score=73.6
odds_movement_coverage=0.0 是有意设计；该样本专门验证 lineup / availability / semantic path，odds movement 继续由 football-data.co.uk market-feature suite 覆盖
当前判断：真实赛前上下文进入 frozen historical slice 的入口已经成型，但这仍是 ingestion/completeness harness，不是准确性提升或模型 promotion 证据
下一阶段路线：把 context-enriched slice 接入 prematch feature ablation，让 lineup_strength、availability risk、semantic risk 在 shadow-only 报告中可量化；随后再接 final-answer gate / quality cycle
README 更新 frozen context enrichment CLI、样本路径、completeness 指标与 shadow-only 结论；该能力不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-143 当前落地能力：

```text
prematch feature ablation 增强 context-only 赛前信号量化，明确支持只有 lineup / availability / semantic、没有 odds_movement 的 frozen context sample
HistoricalPrematchFeatureAblationFixtureSample 新增 favorite_fragility_score、lineup_schedule_risk、key_player_absence_score、semantic_risk_score、source_ref_count，避免关键 context 信号只藏在 feature_readout_json
report summary 新增 average_lineup_strength_score、average_lineup_schedule_risk、average_key_player_absence_score、average_semantic_risk_score、average_source_ref_count、reason_code_counts 与 signal_family_counts
reason codes 新增 lineup_signal_present、availability_signal_present、semantic_signal_present、odds_movement_signal_present、context_only_no_odds_movement，便于区分真实信号家族来源
新增 deterministic test 覆盖 euro_2024_knockout_prematch_context_enriched_v1：确认 lineup/availability/semantic 三类信号进入 ablation、context_only_no_odds_movement 被计数、semantic risk / key-player absence / lineup strength 被一等字段暴露
生成 context sample shadow ablation report：configs/recommendations/historical_reports/euro_2024_knockout_prematch_context_ablation_v1.json
report_key=historical_prematch_feature_ablation:58c09594e4287492；validation_count=2；skipped_count=0；shadow_only=true
本地 smoke 指标：Brier 0.4799 -> 0.46039391991215806；Log loss 0.841004302634468 -> 0.8153975149900965；ECE 0.35999999999999993 -> 0.3518685067636364；hit_rate 维持 0.5
信号统计：signal_family_counts={lineup:2, availability:2, semantic:2}；context_only_no_odds_movement=2；average_lineup_strength_score=0.2325525；average_key_player_absence_score=0.11499999999999999；average_semantic_risk_score=0.34
当前判断：lineup / availability / semantic 信号已经能进入 shadow accuracy report 并被审计，但样本只有 2 场，只能证明链路成立，不能作为推荐默认路径或参数 promotion 证据
下一阶段路线：把 context sample 纳入 final-answer gate/quality cycle 的 smoke path，随后扩展更多真实 frozen context 历史切片；只有大样本且 final-answer 质量与校准不退化，才考虑把这类信号进入推荐候选质量函数
README 更新 context ablation CLI、报告路径、report key、信号统计与 shadow-only 结论；该能力不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-144 当前落地能力：

```text
context-only frozen prematch sample 已接入 prematch feature ablation grid、final-answer gate 与 quality cycle 的 smoke path
生成 context sample feature ablation grid report：configs/recommendations/historical_reports/euro_2024_knockout_prematch_context_ablation_grid_v1.json
grid report_key=historical_prematch_feature_ablation_grid:40d260c5a3f58d72；candidate_count=108；non_regression_candidate_count=102；slice_count=1；fixture_count=2
最佳 context grid 候选为 candidate_0106：max_probability_shift=0.12、odds_movement_weight=0.0、tracked_fragility_weight=1.0、lineup_strength_weight=0.7、draw_signal_weight=0.0、min_feature_data_quality_score=45.0
最佳单场 shadow 指标改善：average_actual_probability_delta=0.02346910440000005；brier_score_delta=-0.03213051596268668；log_loss_delta=-0.04522327928165426；expected_calibration_error_delta=-0.015646069599999923；hit_rate_delta=0.0
生成 context sample final-answer gate report：configs/recommendations/historical_reports/euro_2024_knockout_prematch_context_final_answer_gate_v1.json
gate report_key=historical_prematch_feature_final_answer_gate:52ddd3b4db526e7a；evaluated_candidate_count=5；passing_candidate_count=0；best_feature_grid_candidate_id=prematch-feature-ablation-grid-shadow-v3.1:candidate_0097
final-answer gate 使用 --min-final-hit-sample-size 10，明确因 final_hit_sample_size 不足失败，避免 2 场小样本被误推广
生成 context sample quality cycle report：configs/recommendations/historical_reports/euro_2024_knockout_prematch_context_quality_cycle_v1.json
cycle_key=historical_prematch_feature_quality_cycle:90f2e4a9ca65b08c；status=failed；passed=false；best_failed_quality_check_names=[final_hit_sample_size]；warnings 包含 no_passing_candidate 与 no_passing_final_answer_candidate
新增 deterministic test 覆盖：context-only enriched slice 能进入 quality cycle，但在 min_final_hit_sample_size=10 下必须被阻断，且保持 shadow_only=true
当前判断：lineup / availability / semantic 信号已经从 frozen feature snapshot 一路接到 final-answer-only quality guardrail；本阶段只证明链路可运行和样本量保护有效，不改变默认推荐路径
下一阶段路线：扩展真实 frozen context 历史切片数量，优先补齐更多赛前阵容、伤停/停赛、新闻语义与对应赛果/赔率样本；只有大样本 final-answer hit、ROI、Brier、Log loss、calibration 与冷门捕捉率同时不退化，才讨论进入推荐候选质量函数
README 更新 context grid / final-answer gate / quality cycle CLI、报告路径、report key、cycle key 与 shadow-only 阻断结论；该能力不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-145 当前落地能力：

```text
新增 historical sample coverage audit：nutmeg.recommendations.historical_sample_coverage_audit
新增 CLI：nutmeg-recommendation-historical-sample-coverage-audit，可读取多个 historical suite manifest 或 standalone slice，并输出 frozen sample 覆盖审计
审计输出 source_count、slice_count、fixture_count、complete_1x2 coverage、feature_snapshot/prematch_context/lineup/availability/odds_movement/semantic/source_ref coverage、competition/season 分布、readiness flags 与 warnings
readiness flags 区分 final_answer_sample_ready、feature_snapshot_ready、market_movement_feature_ready、context_signal_ready、full_prematch_context_ready，避免把“大样本可回测”和“赛前上下文可训练”混为一谈
cross-source gap 比较支持联赛别名归一：BUNDESLIGA -> GER_BUNDESLIGA、LA_LIGA -> ESP_LA_LIGA、LIGUE_1 -> FRA_LIGUE_1、SERIE_A -> ITA_SERIE_A，避免不同 builder 命名导致误判缺失
新增 deterministic tests 覆盖：核心样本 vs feature 样本的 readiness 分类、J1 缺口识别、CLI 写出报告、CLI 参数映射
生成本地覆盖审计报告：configs/recommendations/historical_reports/historical_sample_coverage_audit_v1.json
audit_key=historical_sample_coverage_audit:ed1694f66bcadefa；source_count=3；slice_count=56；fixture_count=11340
核心 football-data.co.uk suite：30 slices / 10738 fixtures / complete_1x2_coverage=1.0 / final_answer_sample_ready=true；feature_snapshot_coverage=0.0，所以不能承担结构化赛前特征评估
market-feature suite：25 slices / 600 fixtures / feature_snapshot_coverage=1.0 / odds_movement_coverage=1.0 / source_ref_coverage=1.0 / final_answer_sample_ready=true / market_movement_feature_ready=true；lineup、availability、semantic coverage 仍为 0.0
context suite：1 slice / 2 fixtures / lineup_coverage=1.0 / availability_coverage=1.0 / semantic_signal_coverage=1.0 / context_signal_ready=true；final_answer_sample_ready=false
cross-source gap 显示 Japan J1 已存在于核心历史 suite，但缺失于 opening-to-closing market-movement feature suite：JPN_J1:2021 至 JPN_J1:2025
当前判断：之前下载的历史数据已经进入核心回测和质量门禁；但不同样本套件用途不同，不能把 core result history、market movement feature、lineup/injury/news context 混成一个 promotion 证据
下一阶段路线：扩展真实 frozen context 样本和 J1-compatible feature 样本；优先让更多 fixture 同时具备赛果、1X2 odds、feature_snapshot、source refs，然后再进入 final-answer gate / quality cycle
README 更新 sample coverage audit CLI、报告路径、audit key、三类样本 coverage 与 J1 缺口；该能力不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-146 当前落地能力：

```text
football-data.co.uk feature sample builder 新增 feature_source_kind=closing_only，支持只有 closing odds 的 worldwide CSV 结构，尤其是本地 JPN.csv
closing_only 模式只使用 closing no-vig 1X2 probability 作为 frozen baseline；FeatureSnapshot 中 odds point 只有单个 closing snapshot，并显式写入 movement_available=false
closing_only 不生成 opening-to-closing movement，不得作为 market movement promotion 证据；market movement readiness 现在要求 odds_time_series_coverage，而不是仅要求 odds_movement list 非空
新增 CLI 参数：--feature-source-kind market_movement|closing_only、--source-season，可从同一个 JPN.csv 按 Season 过滤生成多个 frozen slice
batch builder 支持同一 input path 按多个 source season 输出多个 slice；JPN 代码映射为 competition_id=JPN_J1
historical sample coverage audit 新增 odds_time_series_feature_count 与 odds_time_series_coverage，market_movement_feature_ready 改为依赖至少两个 odds 时间点，避免 closing-only 被误判为 market movement
新增 deterministic tests 覆盖：J1 closing-only sample 生成单点 odds snapshot、baseline_probability_source=closing_no_vig_probability、movement_available=false；batch 按 source seasons 生成多 slice；CLI 参数映射
生成 J1 closing-only feature suite：configs/recommendations/historical_suites/football_data_co_uk_j1_closing_only_feature_suite.json
生成 J1 closing-only slices：configs/recommendations/historical_slices/enriched_features/football_data_co_uk_j1_closing_only_features/
生成 J1 closing-only completeness reports：configs/recommendations/historical_reports/football_data_co_uk_j1_closing_only_features/
J1 closing-only suite summary：suite_id=football_data_co_uk_j1_closing_only_feature_suite_v1；slice_count=5；fixture_count=600；source_seasons=2021..2025；completeness_passed_slice_count=5
生成新版 sample coverage audit：configs/recommendations/historical_reports/historical_sample_coverage_audit_v2.json
audit_key=historical_sample_coverage_audit:597d8d6c9eac1baf；source_count=4；slice_count=61；fixture_count=11940
新版审计结论：J1 closing-only suite final_answer_sample_ready=true、feature_snapshot_ready=true、market_movement_feature_ready=false、odds_time_series_coverage=0.0、context_signal_ready=false
market-feature suite 仍是唯一 market_movement_feature_ready source；J1 closing-only 补上 J1 structured baseline 样本入口，但没有补上 opening-to-closing movement 缺口
当前判断：J1 已有可审计 closing-only structured sample，可用于 J1 baseline/coverage/final-answer 对照；但不能进入市场 movement feature promotion 或替代真实 opening odds
下一阶段路线：若要评估 J1 market movement，需要更完整的 opening odds 数据源；否则应把 J1 closing-only 只作为 baseline/control，并继续扩展真实 lineup/injury/news context 样本
README 更新 J1 closing-only CLI、suite/report 路径、新 audit key 与 closing-only 限制；该能力不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-147 当前落地能力：

```text
football-data.co.uk feature sample builder 新增 prediction_time_policy=fixture_lead|slice_start
默认 fixture_lead 继续表示每场 fixture 按自身 kickoff 前 prediction_lead_minutes 生成 prediction_time
slice_start 用于 closing-only frozen shadow baseline：同一 historical slice 内所有 fixture 使用 slice 第一场开赛前的统一 prediction_time，使 season-level candidate pool 能在单一 as_of 下被 final-answer backtest 重放
slice_start 已在 metadata notes 与 summary_json 中显式标记，说明它只用于 frozen shadow replay，不是 live availability evidence，也不能作为真实临场数据可用性的证明
J1 closing-only suite 已用 --prediction-time-policy slice_start 重新生成，保留 5 slices / 600 fixtures / source_seasons=2021..2025 / completeness_passed_slice_count=5
historical suite quality gate CLI 新增 --output-path，可把 gate JSON 稳定落盘，避免质量门禁只存在终端输出
新增 deterministic tests 覆盖：closing-only sample 使用 slice_start 时所有 fixture prediction_time 一致且晚于 as_of 的 fixture 可参与回放；feature sample CLI/batch CLI 参数映射 prediction_time_policy；historical suite gate CLI 参数映射 output_path
生成 J1 closing-only final-answer full-matrix diagnostic：configs/recommendations/historical_reports/football_data_co_uk_j1_closing_only_candidate48_window4_full_matrix_diagnostics.json
diagnostic report_key=historical_recommendation_diagnostic:cfaf4fd312418df9；slice_count=5；fixture_count=600；prediction_count=1800；candidate_final_hit_rate=0.8；candidate_roi=0.6607800000000001；candidate_profit_loss=6.607800000000001；candidate_brier_score=0.29047112018937793；candidate_log_loss=0.7774822600125824；candidate_mean_calibration_error=0.5292855856993335；warnings=[]
生成 J1 closing-only quality gate：configs/recommendations/historical_reports/football_data_co_uk_j1_closing_only_candidate48_window4_full_matrix_gate.json
gate_key=historical_recommendation_suite_quality_gate:67bbe58060776814；status=passed；failed_checks=[]；candidate_final_hit_sample_size=5；candidate_final_hit_rate=0.8；candidate_roi=0.66078；competition_candidate_roi[JPN_J1]=0.6607799999999997
生成短赔负边际 guard 对照诊断：configs/recommendations/historical_reports/football_data_co_uk_j1_closing_only_candidate48_window4_full_matrix_short_price_guard_diagnostics.json
short-price guard report_key=historical_recommendation_diagnostic:0a9ef905345434db；guard 过滤 18 个候选，但 candidate_final_hit_rate 从 0.8 降到 0.6，candidate_roi 从 0.6607800000000001 降到 0.43620000000000003，说明该 guard 不能全局启用，需要后续按联赛/赔率带/profile 学习
生成新版 sample coverage audit：configs/recommendations/historical_reports/historical_sample_coverage_audit_v3.json
audit_key 仍为 historical_sample_coverage_audit:597d8d6c9eac1baf；source_count=4；slice_count=61；fixture_count=11940；J1 closing-only 仍为 final_answer_sample_ready=true、feature_snapshot_ready=true、market_movement_feature_ready=false
当前判断：J1 closing-only 已从“结构化样本存在”升级为“可进入最终答案回测和质量门禁的 shadow baseline”；但它仍是 closing-only control，不是 market movement、context signal 或 live prediction promotion 证据
下一阶段路线：把该结果纳入 per-competition profile evidence，继续做 odds-band / competition-band 学习；不要把短赔负边际 guard 作为全局硬规则；继续补真实 opening odds、lineup/injury/news context 后再进入 held-out final-answer quality cycle
README 更新 slice_start CLI、J1 final-answer diagnostic/gate 路径、短赔 guard 对照、audit_v3 路径与 shadow-only 限制；该能力不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-148 当前落地能力：

```text
final-answer quality-signal diagnostics 新增 competition-specific 交叉分组：competition_probability_band、competition_odds_band、competition_model_edge_band
这些分组只分析最终答案选中的 legs，用于回答“某联赛 + 某赔率带 / 概率带 / edge 带”的历史命中、ROI、missed leg、profit/loss，不改变推荐默认路径
新增 CLI 参数 --include-competition-bands / --no-include-competition-bands，默认开启；report summary 会记录 include_competition_bands=true
新增 deterministic tests 覆盖：最终答案 selected legs 会进入 competition_odds_band，CLI 参数能关闭 competition bands
重新生成五季 core quality signal report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_quality_signal_diagnostics.json
core report_key=historical_quality_signal_diagnostics:1a61f64c7b1f3c3b；final_answer_count=30；selected_leg_count=105；missed_leg_count=15；final_answer_hit_rate=0.6666666666666666；leg_hit_rate=0.8571428571428571；roi=0.05017769041333331；group_count=46
core 关键负向交叉桶：competition_odds_band:JPN_J1:short_price selected_leg_count=7、leg_hit_rate=0.5714285714285714、roi=-0.5677；competition_odds_band:ESP_LA_LIGA:short_price roi=-0.21856938688000013；competition_odds_band:GER_BUNDESLIGA:short_price roi=-0.20316479999999987
core 关键正向交叉桶：competition_odds_band:FRA_LIGUE_1:short_price roi=0.6583547299999999；competition_odds_band:EPL:short_price roi=0.30976559936000037；说明“短赔”不是全局坏信号，必须按联赛/profile 分层
生成 J1 closing-only quality signal report：configs/recommendations/historical_reports/football_data_co_uk_j1_closing_only_candidate48_window4_quality_signal_diagnostics.json
J1 closing-only report_key=historical_quality_signal_diagnostics:fec4d6565a3afbfb；final_answer_count=5；selected_leg_count=10；missed_leg_count=1；final_answer_hit_rate=0.8；leg_hit_rate=0.9；roi=0.6607799999999997
J1 closing-only 中 competition_probability_band:JPN_J1:medium 表现强于 high：medium roi=1.4806499999999998、leg_hit_rate=1.0；high roi=0.11420000000000001、leg_hit_rate=0.8333333333333334
当前判断：系统已经能从最终答案层面输出 per-competition / odds-band / probability-band evidence；下一步应把这些 evidence 转成候选 profile search / quality gate，而不是继续添加全局短赔、全局负 edge 或全局热门惩罚
README 更新 quality-signal diagnostics 新分组、core/J1 报告路径、report key 与 profile-only 结论；该能力不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-149 当前落地能力：

```text
final-answer quality-signal penalty 新增 competition_ids 过滤维度：HistoricalRecommendationBacktestOptions.final_answer_quality_signal_competition_ids
该过滤维度已进入 backtest summary、suite summary、backtest/comparison/suite key 与 CLI 参数 --final-answer-quality-signal-competitions，保证联赛 scoped profile 的回测结果可复现
新增 final-answer quality-signal profile grid：build_historical_final_answer_quality_signal_profile_grid_report
profile grid 会按 competition group、probability_min/probability_max、max_decimal_odds、max_model_edge、strength 生成候选，并用 final-answer hit、ROI、profit/loss、Brier、log loss、calibration、upset capture、affected leg count 与 objective-improvement gate 判定 accepted/rejected
新增 CLI：nutmeg-recommendation-final-answer-quality-signal-profile-grid
新增 deterministic tests 覆盖：联赛过滤只影响目标联赛；profile grid 能产出 non-regressing candidate；inactive competition group 会因 affected_leg_count_too_low 拒绝；CLI 参数映射正确
生成 J1 closing-only shadow profile grid：configs/recommendations/historical_reports/football_data_co_uk_j1_closing_only_candidate48_window4_final_answer_quality_signal_profile_grid.json
J1 profile report_key=historical_final_answer_quality_signal_profile_grid:47f6034432ba20ba；candidate_count=1；accepted_count=0；rejected_count=1
J1 profile baseline 与上一轮 J1 quality-signal 口径对齐：candidate_final_hit_rate=0.8；candidate_roi=0.66078；candidate_profit_loss=6.6078
J1 scoped profile 命中 2 条 affected final-answer legs，但 final_hit_rate_delta=0.0、roi_delta=0.0、profit_loss_delta=0.0、brier/log_loss/calibration delta 均为 0.0，因此被 objective gate 拒绝：quality_signal_profile:objective_improvement_missing
当前判断：competition-specific quality signal 已从诊断桶升级为可搜索 profile candidate，但 J1 closing-only 候选没有证明能提升最终答案；仍不得进入默认推荐策略
已知限制：五季 core profile grid 的 repeated suite runs 当前耗时较高，本轮未生成全量 core profile grid；下一步应先做 profile-grid batch/cache 或缩小候选并行拆分，再跑 EPL/西甲/德甲/J1 全量 objective gate
README 更新 final-answer quality-signal profile grid CLI、J1 shadow report 路径、report key、拒绝结论与 full-core batching/cache 限制；该能力不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-150 当前落地能力：

```text
final-answer quality-signal profile grid 新增 batch/cache/merge 工具链，沿用 upset lane profile grid 的稳定候选执行模式
新增 options：candidate_start_index、candidate_limit、candidate_cache_dir、read_candidate_cache、write_candidate_cache
每个候选新增 candidate_index、candidate_cache_key、candidate_cache_status；report 新增 total_grid_candidate_count、candidate_indices、cache_hit_count、cache_miss_count、cache_write_count、candidate_cache_dir、grid summary、rejection_reason_counts、competition_summary
新增 per-candidate cache：同一 baseline_suite_key + spec + options 命中缓存时不重复执行 candidate suite；CLI 参数为 --candidate-cache-dir、--no-candidate-cache-read、--no-candidate-cache-write
新增 merge_historical_final_answer_quality_signal_profile_grid_reports 与 CLI：nutmeg-recommendation-final-answer-quality-signal-profile-grid-merge
merge report 会输出 source_report_count、source_report_keys、source_report_paths、missing_candidate_indices、duplicate_candidate_indices、is_full_grid，用于长网格分批审计
新增 deterministic tests 覆盖：batch 只执行指定 candidate index；首次运行写入 cache，第二次运行 cache hit；两个 batch report 可按 candidate_index 合并；merge CLI 参数映射正确
真实 core 5-season batch/cache smoke 已输出：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_batch0_v1.json
batch0 report_key=historical_final_answer_quality_signal_profile_grid:40ce28f6c174effc；total_grid_candidate_count=3；candidate_indices=[0]；cache_hit_count=0；cache_miss_count=1；cache_write_count=1
batch0 JPN_J1 candidate affected_leg_count=5，但 final_hit_rate_delta=0.0、roi_delta=0.0、profit_loss_delta=0.0、brier/log_loss/calibration delta 均为 0.0，因此被 objective gate 拒绝：quality_signal_profile:objective_improvement_missing
真实 cache reused smoke 已输出：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_batch0_reused_v1.json
reused report_key=historical_final_answer_quality_signal_profile_grid:c5bf192567c06e01；cache_hit_count=1；cache_miss_count=0；cache_write_count=0；candidate_cache_status=hit
真实 partial merge smoke 已输出：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_partial_merge_v1.json
partial merge report_key=historical_final_answer_quality_signal_profile_grid:4cbb2aac970ed60f；source_report_count=1；candidate_count=1；total_grid_candidate_count=3；missing_candidate_indices=[1,2]；duplicate_candidate_indices=[]；is_full_grid=false
当前判断：final-answer quality-signal profile search 已具备可恢复、可缓存、可合并的工程路径；core index 0 的 JPN_J1 候选仍不支持晋级默认推荐
已知限制：cache 目前复用 candidate suite 结果，但每个 batch 仍需先跑 baseline suite；下一步可继续执行 candidate indices 1/2，或进一步缓存 baseline suite/并行 batch worker
README 更新 batch/cache/merge CLI、core smoke 报告路径、report key、cache hit/miss 与非晋级结论；该能力不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-151 当前落地能力：

```text
完成 core 5-season final-answer quality-signal profile grid 剩余 batch 执行：batch1 覆盖 candidate index [1]，batch2 覆盖 candidate index [2]
batch1 report 输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_batch1_v1.json
batch1 report_key=historical_final_answer_quality_signal_profile_grid:8802840e4b870abc；candidate index=1；competition_ids=[ESP_LA_LIGA]；affected_leg_count=0；accepted_count=0；rejected_count=1
ESP_LA_LIGA candidate final_hit_rate_delta=0.0、roi_delta=0.0、profit_loss_delta=0.0，但 brier_score_delta=0.012217969885962049、log_loss_delta=0.02574395355751735、mean_calibration_error_delta=0.01148354118833328，因此被拒绝
batch2 report 输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_batch2_v1.json
batch2 report_key=historical_final_answer_quality_signal_profile_grid:ca4eb47179727303；candidate index=2；competition_ids=[GER_BUNDESLIGA]；affected_leg_count=0；accepted_count=0；rejected_count=1
GER_BUNDESLIGA candidate final_hit_rate_delta=0.0、roi_delta=0.0、profit_loss_delta=0.0，因 affected_leg_count_too_low 与 objective_improvement_missing 被拒绝
完整 full merge 输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_quality_signal_profile_grid_full_merge_v1.json
full merge report_key=historical_final_answer_quality_signal_profile_grid:c0a6997b1a729148；source_report_count=3；total_grid_candidate_count=3；candidate_count=3；accepted_count=0；rejected_count=3；missing_candidate_indices=[]；duplicate_candidate_indices=[]；is_full_grid=true
full merge rejection_reason_counts：objective_improvement_missing=3；affected_leg_count_too_low=2；brier_score_regressed=1；log_loss_regressed=1；mean_calibration_error_regressed=1
当前判断：上一轮 core quality-signal diagnostics 暴露的 JPN_J1 / ESP_LA_LIGA / GER_BUNDESLIGA 短赔高概率负 edge 风险，不能被当前 final-answer penalty profile 直接转成可晋级默认规则；JPN_J1 有 affected legs 但无收益，ESP/GER 在最终答案层没有命中该 profile
下一阶段建议：不要继续沿这个单一 penalty profile 死磕；转向 candidate-level marginal contribution / replacement diagnostics，把“该删哪条腿/换成哪条腿”直接量化，再回到最终答案仲裁器
README 更新 core full merge 命令、report key、三联赛候选拒绝结论与非晋级判断；该能力不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-152 当前落地能力：

```text
补齐 marginal loss-driver grouping 能力：build_historical_marginal_loss_driver_report
该模块读取 HistoricalCandidateMarginalAuditReport，但不再以 model_top_replacement 晋级为目标，而是把最终答案已选腿按赛前可见特征聚合，寻找“miss rate 高 + hindsight replacement opportunity 高 + actual-best delta 为正”的误差来源分组
新增模型：HistoricalMarginalLossDriverOptions、HistoricalMarginalLossDriverReport、HistoricalMarginalLossDriverGroup
新增 CLI：nutmeg-recommendation-marginal-loss-driver-groups，支持 audit report 输入、输出 report、min sample size、min miss rate、min actual replacement opportunity rate、min average actual-best profit/loss delta、max model-top harm rate 与 profile group 开关
新增确定性测试覆盖：满足 miss/opportunity/actual-best 门槛的分组进入 guard_candidate；model-top harm rate 超限但仍有 hindsight loss-driver 证据的分组进入 watchlist；小样本分组被拒绝；CLI 参数与 audit report loader 正常
真实 football-data.co.uk 五季 loss-driver report 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_loss_driver_groups.json
report_key=historical_marginal_loss_driver_groups:3daad8e49fd0ba0c；group_count=28；guard_candidate_count=8；watchlist_count=16；rejected_count=4
本轮口径确认 105 条 selected legs、15 条 missed legs、77 个 hindsight replacement opportunities
最强 guard candidate 为 profile:JPN_J1|2x1|probability:high|odds:short|edge:negative|score:medium_high，selected_leg_count=7，miss_rate=0.2857142857142857，actual_replacement_opportunity_rate=0.7142857142857143，average_actual_best_profit_loss_delta=1.3739142857142856
但该 profile 的 average_model_top_profit_loss_delta=-0.5576857142857142，说明“错误来源”存在，不等于“可直接替换”；下一步应把该 loss-driver profile 转成 shadow guard/penalty backtest，而不是上线替换规则
README 更新 marginal loss-driver grouping 用法、report key 与非晋级判断；该能力属于“候选级贡献审计 / 最终答案质量函数层 / 周期质量门禁升级”，不接实时 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-153 当前落地能力：

```text
final-answer quality-signal penalty 新增 selected-score range 维度：HistoricalRecommendationBacktestOptions.final_answer_quality_signal_score_min / final_answer_quality_signal_score_max
penalty 适用判断从 candidate-only 扩展为 scored-candidate 判断，默认 score_min=0.0、score_max=1.0，因此不改变既有默认行为；candidate-only helper 保留给测试和诊断调用
final-answer quality-signal profile grid 新增 score_min_values / score_max_values，candidate spec、candidate report、grid summary、candidate cache key、CLI 参数均纳入 score range，支持把 marginal loss-driver profile 转成更窄的 shadow guard/penalty candidate
新增/更新确定性测试覆盖：score range 会让不在 score 区间的 final-answer leg 不被 penalty 命中；profile grid CLI 能正确解析 score_min_values / score_max_values
真实 football-data.co.uk 五季 targeted 2x1 shadow guard profile 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_loss_driver_guard_profile_grid_2x1.json
本轮 profile 来自 V3.1-152 最强 loss-driver：competition=JPN_J1，pass_type=2x1，probability=[0.65,0.80)，max_decimal_odds=1.50，max_model_edge=-0.02，score=[0.55,0.65]，strength_values=0.02/0.04/0.06/0.08
report_key=historical_final_answer_quality_signal_profile_grid:634768004b28b7ae；candidate_count=4；accepted_count=0；rejected_count=4；affected_leg_count=8
strength 0.02/0.04/0.06 对 final_hit_rate、ROI、profit/loss、Brier、log loss、calibration、upset capture 全部无改善，因此因 objective_improvement_missing 被拒绝
strength 0.08 触发回归：roi_delta=-0.14257555555555557，profit_loss_delta=-11.9726，brier_score_delta=0.005398144750212774，log_loss_delta=0.013878363066985089，因此被拒绝
当前判断：loss-driver profile 能准确定位误差来源，但简单 final-answer penalty 仍无法转化为更好的最终答案；不能晋级默认策略
已知限制：完整 2x1-8x1 solver 强度扫较重，本轮中止了全 pass-type 扫描，改为 profile 所属 2x1 targeted shadow run；后续若继续全量扫，必须使用 batch/cache 或更小候选网格
README 更新 selected-score range shadow profile CLI、真实 report key、拒绝结论与非晋级判断；该能力属于“最终答案质量函数层 / loss-driver shadow guard / 周期质量门禁升级”，不接实时 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-154 当前落地能力：

```text
新增候选池层 marginal loss-driver candidate guardrail shadow 开关：HistoricalRecommendationBacktestOptions.marginal_loss_driver_candidate_guardrail
该 guardrail 在 optimizer 选腿前排除候选，支持 competition_ids、probability_min/probability_max、max_decimal_odds、max_model_edge；默认关闭，不改变普通推荐路径
historical backtest summary / suite summary / backtest key / comparison key / suite key 均记录 guardrail 参数与 excluded candidate count，保证 shadow ablation 可复现
新增 ablation report 模块：build_historical_marginal_loss_driver_candidate_guardrail_ablation_report
该模块用同一个 optimizer profile 对比 baseline（不启用 guardrail）与 candidate（启用 guardrail），避免把 guardrail 效果混入 heuristic-vs-solver 对比
新增 CLI：nutmeg-recommendation-marginal-loss-driver-candidate-guardrail-ablation，支持 suite manifest、slice paths、pass types、modes、预算、候选池限宽、market context、optimizer profile、guardrail profile 参数和 accuracy-first objective gate
新增确定性测试覆盖：candidate guardrail 默认关闭且按 competition 过滤；ablation report 能统计 excluded candidate count 并在无 objective improvement 时拒绝；CLI 参数映射正常
真实 football-data.co.uk 五季 targeted 2x1 candidate-pool ablation 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_loss_driver_candidate_guardrail_ablation_2x1.json
本轮 profile：competition=JPN_J1，pass_type=2x1，probability=[0.65,0.80)，max_decimal_odds=1.50，max_model_edge=-0.02，optimizer_profile=solver
report_key=historical_marginal_loss_driver_candidate_guardrail_ablation:4b717f5de4b06c19；slice_count=30；excluded_candidate_count=54；final_answer_changed_count=4；decision=rejected
正向结果：final_hit_count 从 20 提升到 21，final_hit_rate 从 0.6666666666666666 提升到 0.7，ROI 从 -0.1422633333333333 提升到 -0.015709999999999964，profit_loss_delta=7.5932
拒绝原因：brier_score_delta=0.01049985766342787，log_loss_delta=0.02261384605737571，mean_calibration_error_delta=0.008196395368522957；结算结果改善但概率质量退步，不能按 accuracy-first gate 晋级默认策略
当前判断：候选池层 guardrail 比 final-answer penalty 更能改变最终答案并改善 settlement，但会伤害校准；下一步应做 calibration-aware guardrail，例如只在同 profile 且 calibration/model confidence/odds stability 足够时排除，或把候选池排除改为 soft demotion 而非 hard exclusion
README 更新 candidate-pool ablation CLI、真实 report key、正向 settlement 与负向 calibration 结论；该能力属于“候选池层 shadow guard / 准确性优先质量门禁 / 周期质量门禁升级”，不接实时 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-155 当前落地能力：

```text
候选池层 marginal loss-driver candidate guardrail 新增 optional quality caps：max_calibration_score、max_model_confidence_score、max_odds_stability_score
historical backtest options、candidate generation、summary_json、suite summary、backtest/comparison/suite key 与 CLI 均已纳入这些参数；默认 None，不改变普通推荐路径
candidate guardrail ablation report 同步支持 --max-calibration-score、--max-model-confidence-score、--max-odds-stability-score，并把这些阈值写入 report summary / report key
新增/更新确定性测试覆盖：质量 cap 未命中时不会误剔除候选；ablation CLI 参数映射正确；质量 cap 导致 excluded_candidate_count=0 时会被 objective gate 拒绝
真实 football-data.co.uk 五季 targeted 2x1 calibration-capped ablation 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_loss_driver_candidate_guardrail_ablation_2x1_calibration_cap.json
本轮参数：competition=JPN_J1，pass_type=2x1，probability=[0.65,0.80)，max_decimal_odds=1.50，max_model_edge=-0.02，max_calibration_score=0.69，optimizer_profile=solver
report_key=historical_marginal_loss_driver_candidate_guardrail_ablation:e3804b4ecbab617b；slice_count=30；excluded_candidate_count=0；final_answer_changed_count=0；decision=rejected
结果：final_hit_rate、ROI、profit/loss、Brier、log loss 与 mean calibration error delta 全为 0；拒绝原因为 excluded_candidate_count_too_low 与 objective_improvement_missing
当前判断：当前免费历史样本里该 JPN_J1 loss-driver profile 的 quality score 没有足够分辨率，hard quality cap 只作为未来 richer data 的安全阈；下一步应优先做 soft demotion / treatment grid 或引入更真实的赛前质量特征，而不是默认启用 hard exclusion
README 更新 quality-capped ablation CLI/报告路径、report key 与非晋级判断；该能力属于“候选池层 shadow guard / quality-aware safety cap / 周期质量门禁升级”，不接实时 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-156 当前落地能力：

```text
新增候选池层 marginal loss-driver candidate soft penalty：HistoricalRecommendationBacktestOptions.marginal_loss_driver_candidate_soft_penalty
该 soft penalty 不删除候选，而是在匹配 loss-driver profile 时写入 internal_candidate_score_penalty；Recommendation policy 会把该内部 penalty 从 candidate score 中扣除，并记录 candidate_score_penalty_applied reason code
soft penalty 复用上一轮 loss-driver profile 参数：competition_ids、probability_min/probability_max、max_decimal_odds、max_model_edge 以及 optional quality caps；默认关闭，不改变普通推荐路径
historical backtest summary / suite summary / backtest key / comparison key / suite key 已记录 soft penalty 开关、strength 与 candidate count；CLI 新增 --marginal-loss-driver-candidate-soft-penalty 和 --marginal-loss-driver-candidate-soft-penalty-strength
新增 treatment grid 模块：build_historical_marginal_loss_driver_candidate_soft_penalty_grid_report
新增 CLI：nutmeg-recommendation-marginal-loss-driver-candidate-soft-penalty-grid，支持 suite manifest、slice paths、2x1 targeted pass type、候选池限宽、market context、optimizer profile、profile 参数、strength_values 与 accuracy-first objective gate
新增确定性测试覆盖：policy 会应用内部 candidate score penalty；soft-penalty grid 能统计 penalized candidate count、拒绝 inactive competition、CLI 参数映射正确
真实 football-data.co.uk 五季 targeted 2x1 soft-penalty treatment grid 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_loss_driver_candidate_soft_penalty_grid_2x1.json
report_key=historical_marginal_loss_driver_candidate_soft_penalty_grid:b1389665e13ddb11；candidate_count=7；accepted_count=0；rejected_count=7；本轮所有 strength 均命中 54 个候选
strength=0.05：final_answer_changed_count=1，final_hit_rate_delta=0.0，roi_delta=0.00043999999999999595，但 brier/log-loss/calibration 轻微退步，因此被拒绝
strength=0.10：final_hit_rate_delta=0.033333333333333326，roi_delta=0.07136，profit_loss_delta=4.281600000000001，但 brier_score_delta=0.004005740311252698，log_loss_delta=0.008078043465645224，mean_calibration_error_delta=0.0037233608721274347，因此被拒绝
strength>=0.20：settlement 改善等同 hard guardrail，final_hit_rate_delta=0.033333333333333326，roi_delta=0.12655333333333332，profit_loss_delta=7.5932，但也复现 hard guardrail 的 Brier/log-loss/calibration 回退，因此全部拒绝
当前判断：soft demotion 已证明可改变最终答案，但当前 profile 的收益来自牺牲概率质量；不能晋级默认策略。下一步应转向校准层/概率模型层，或用真实赛前 lineup/injury/news 特征补充可解释质量信号，而不是继续放宽 promotion gate
README 更新 soft-penalty treatment grid CLI、真实 report key、各 strength 结论与非晋级判断；该能力属于“候选池层 shadow treatment / final-answer quality gate / prediction accuracy mainline”，不接实时 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-157 当前落地能力：

```text
league-level Poisson parameter learning 已支持 lambda_method=form_rest_adjusted
新增参数学习候选维度：candidate_form_adjustment_weights、candidate_rest_adjustment_weights、form_window_matches、rest_reference_days、max_lambda_adjustment
form/rest 候选会进入 candidate_key、candidate payload、walk-forward options、report key 与 CLI 参数，保证同一候选在训练赛季选择、最新赛季 holdout 验证时完全可复现
默认 form/rest 候选权重为 0，不改变既有 rolling_strength / enhanced_weighted_home_away / draw-rho 学习结果；只有显式选择 --lambda-method form_rest_adjusted 时才展开 form/rest weight grid
新增确定性测试覆盖：form_rest_adjusted parameter-learning 会生成 form/rest 权重网格；CLI 能解析 form/rest candidate weights 与窗口/休息日/lambda 调整上限
真实 football-data.co.uk 五季 form/rest holdout parameter-learning 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_form_rest_parameter_learning_v1.json
report_key=historical_poisson_parameter_learning:4d275877a21441b4；competition_count=6；learned_competition_count=6；candidate_count=12；validation_count=2062
selected_candidate_counts：poisson_draw_0_4_form_0_0_rest_0_0=3、poisson_draw_0_4_form_0_0_rest_0_02=2、poisson_draw_0_4_form_0_03_rest_0_0=1
整体 holdout candidate 指标：hit_rate=0.5126091173617847、Brier=0.5963756626118645、Log loss=0.9978066048074087、ECE=0.04012862021286022
整体 holdout market baseline 指标：hit_rate=0.5368574199806013、Brier=0.5790496105941644、Log loss=0.9730819333695456、ECE=0.03676958063070931
整体 holdout delta：hit_rate_delta=-0.02424830261881661、brier_score_delta=0.0173260520177001、log_loss_delta=0.024724671437863055、expected_calibration_error_delta=0.003359039582150912
当前判断：粗粒度赛果 form/rest 派生特征已进入正式 holdout 学习链路，但仍未打过 no-vig market baseline，且多数联赛仍选择零 form/rest 权重；不能进入默认推荐路径或模型 promotion
下一阶段路线：停止继续放大粗粒度 form/rest 权重，转向真实赛前 lineup/injury/news、opening-to-closing odds movement 的更高质量样本，或校准层概率修正；所有候选继续走 holdout + final-answer quality gate
README 更新 form/rest parameter-learning CLI、报告路径、report key、holdout 指标与非晋级结论；该能力属于“预测本体成型 / 真实历史派生特征 holdout 学习 / accuracy-first gate”，不接新 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-158 当前落地能力：

```text
新增 historical probability calibration transform：nutmeg.accuracy.historical_probability_calibration_transform
新增 CLI：nutmeg-accuracy-historical-probability-calibration-transform，用训练赛季学习 1X2 概率桶实际频率，并只在 holdout season 验证校准变换效果
该 transform 是 shadow-only，不改 frozen slice、不改推荐默认路径、不接 Provider、不接 VPS；用于判断“校准层修正”是否能在真实 holdout 上改善概率质量
校准键默认按 competition + outcome + probability bucket 分组；支持 group-all-competitions、bucket_size、min_bucket_sample_size、blend_weight、min/max calibrated probability 与 accuracy-first objective gate
报告输出每个联赛 training_seasons、validation_seasons、calibration_bucket_count、usable_calibration_bucket_count、candidate vs baseline hit/Brier/log-loss/ECE、decision 与 rejected reasons
新增 deterministic tests 覆盖：过度自信 home bucket 能在 holdout 校准后改善；bucket 样本不足时回退 identity 并拒绝；训练赛季不足时拒绝；CLI 参数映射正确
真实 football-data.co.uk 五季 probability calibration transform 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_probability_calibration_transform_v1.json
report_key=historical_probability_calibration_transform:d2faccb727c77702；competition_count=6；learned_competition_count=6；validation_count=2132；usable_calibration_bucket_count=104
整体 holdout candidate 指标：hit_rate=0.5337711069418386、Brier=0.5795079692472372、Log loss=0.9739091280225523、ECE=0.03817676000003683
整体 holdout baseline 指标：hit_rate=0.5361163227016885、Brier=0.5791437500706367、Log loss=0.9730922524293841、ECE=0.03737794058402302
整体 holdout delta：hit_rate_delta=-0.002345215759849917、brier_score_delta=0.00036421917660056646、log_loss_delta=0.0008168755931681204、expected_calibration_error_delta=0.000798819416013806
分联赛结果：ESP_LA_LIGA 与 ITA_SERIE_A 通过 non-regressing_holdout_improvement；EPL、FRA_LIGUE_1、GER_BUNDESLIGA、JPN_J1 被拒绝，原因包括 hit/Brier/log-loss/ECE 回退
当前判断：概率桶校准 transform 已能发现分联赛可用信号，但全局聚合轻微回退；不能默认启用。下一阶段应做 per-competition calibration profile/gate，而不是把校准变换全局上线
README 更新 calibration transform CLI、报告路径、report key、整体/分联赛 holdout 结论与非晋级判断；该能力属于“校准层 shadow transform / 预测概率质量 gate / accuracy-first mainline”，不接新 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-159 当前落地能力：

```text
新增 per-competition probability calibration profile final-answer gate：nutmeg.recommendations.historical_probability_calibration_profile_gate
新增 CLI：nutmeg-recommendation-historical-probability-calibration-profile-gate
该 gate 先运行/使用 historical probability calibration transform，只选择 transform holdout decision=accepted 的联赛，再仅对这些联赛的 holdout slices 应用 shadow-only 概率校准调整
被 transform 拒绝的联赛不会进入 final-answer gate；训练赛季不会进入 final-answer gate，避免样本内自我奖励
候选 slice 只修改 1X2 prediction.probability、model_edge 与 calibration_version，并把 baseline probability、adjusted probability、bucket key、fallback reasons、transform report key 写入 metadata_json；原 slice 不被修改
final-answer gate 使用同一 optimizer_profile 对比 baseline holdout slice 与 adjusted holdout slice，并接入现有 HistoricalRecommendationSuiteQualityGateOptions
新增 deterministic tests 覆盖：accepted competition 能进入 holdout final-answer gate；无 accepted transform competition 时不生成 suite；CLI 参数映射正确
真实 football-data.co.uk 五季 accepted-league profile gate 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_probability_calibration_profile_gate_v1.json
report_key=historical_probability_calibration_profile_gate:4a34bf07c90a46d7；transform_report_key=historical_probability_calibration_transform:3a80f86e5b0c363e
selected_competition_ids=[ESP_LA_LIGA, ITA_SERIE_A]；rejected_competition_ids=[EPL, FRA_LIGUE_1, GER_BUNDESLIGA, JPN_J1]
baseline_slice_count=2；adjusted_slice_count=2；adjusted_fixture_count=760；skipped_fixture_count=0
final-answer suite_status=regressed；quality_gate_passed=false；failed checks=suite_status、final_hit_rate_delta、brier_score_delta、log_loss_delta、mean_calibration_error_delta
final-answer aggregate delta：final_hit_rate_delta=-0.5、final_hit_count_delta=-1、roi_delta=-0.51、profit_loss_delta=-2.04、brier_score_delta=0.35321256192032685、log_loss_delta=0.8726533265588203、mean_calibration_error_delta=0.38340428675644883
当前判断：分联赛概率校准在单场概率 holdout 上有局部信号，但进入最终答案层后明显伤害命中、ROI 与校准；必须继续保持 shadow-only，不能进入默认推荐策略
下一阶段路线：不要继续直接把 bucket calibration 推进最终答案；应先做更细的 calibration transform profile search（blend/bucket/outcome/odds-band）并强制 final-answer gate，或者转回真实赛前特征/模型概率本体。任何校准候选必须同时通过单场 holdout 与 final-answer gate
README 更新 profile gate CLI、真实 report key、最终答案拒绝原因与非晋级判断；该能力属于“per-competition calibration profile / final-answer gate / accuracy-first promotion guardrail”，不接新 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-160 当前落地能力：

```text
probability calibration profile gate 已扩展 outcome/probability/decimal-odds 过滤能力：target_outcomes、probability_min/probability_max、min_decimal_odds/max_decimal_odds
候选 slice 只对命中 profile 的 1X2 outcome 应用 shadow calibration，并对三项概率重新归一化；metadata_json 记录 profile 过滤条件、baseline probability、adjusted probability、bucket key 与 shadow-only 标记
新增 narrow probability calibration profile grid：nutmeg.recommendations.historical_probability_calibration_profile_grid
新增 CLI：nutmeg-recommendation-historical-probability-calibration-profile-grid，用于枚举 blend_weights、target_outcome_groups、probability_bands、decimal_odds_bands，并逐个候选调用 final-answer gate
grid report 输出 candidate_count、accepted_count、rejected_count、best_candidate、rejection_reason_counts、每个候选的 adjusted_fixture_count、final-answer aggregate deltas 与 decision reasons
grid CLI 新增 --min-final-answer-changed-count，并映射到 HistoricalRecommendationSuiteQualityGateOptions，避免概率调整没有改变最终答案时被误当作有效晋级候选
新增 deterministic tests 覆盖：profile gate 可以只调整目标 outcome/probability/odds band；grid 能枚举/排序候选；candidate_start_index/candidate_limit 生效；grid CLI 参数映射正确
真实 football-data.co.uk 五季 narrow calibration profile grid 已输出到 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_probability_calibration_profile_grid_v1.json
本轮 grid：30 slices、10738 fixtures、18 candidates；blend_weights=[0.25,0.50]；target_outcome_groups=[home_win,draw,away_win]；probability_bands=[0.00:0.35,0.35:0.65,0.65:1.00]；decimal_odds_bands=[all]
严格门槛：min_final_hit_sample_size=2、min_final_hit_rate_delta=0.0、min_final_answer_changed_count=1、max_brier_score_delta=0.0、max_log_loss_delta=0.0、max_mean_calibration_error_delta=0.0
report_key=historical_probability_calibration_profile_grid:0a9b9d01107fb223；accepted_count=0；rejected_count=18
rejection_reason_counts：quality_gate:final_answer_changed_count=17、profile_grid:no_adjusted_fixtures=2、quality_gate:brier_score_delta=2、quality_gate:log_loss_delta=2、quality_gate:mean_calibration_error_delta=2、quality_gate:suite_status=2、quality_gate:final_hit_rate_delta=1
唯一改变最终答案的候选为 home_win probability=[0.65,1.00] blend_weight=0.50，adjusted_fixture_count=113，但 final_hit_rate_delta=-0.5、roi_delta=-0.55、profit_loss_delta=-2.2、brier_score_delta=0.3557566506573265、log_loss_delta=0.8899590598308735、mean_calibration_error_delta=0.3630651064045382，因此被拒绝
当前判断：窄 profile search 证明当前 bucket calibration 多数无法影响最终答案；一旦影响最终答案则明显伤害命中、ROI 与校准。该路线继续保持 shadow-only，不进入默认推荐策略
下一阶段路线：回到预测概率本体与真实赛前特征质量，优先补强 lineup/injury/news/opening-to-closing odds movement 等可提升模型概率的特征样本；所有候选继续强制走 final-answer gate 与 min_final_answer_changed_count
README 更新 profile grid CLI、真实 report key、严格门槛、拒绝原因与非晋级判断；该能力属于“narrow calibration profile search / final-answer promotion gate / accuracy-first negative evidence”，不接新 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-161 当前落地能力：

```text
新增 historical market movement signal diagnostics：nutmeg.accuracy.historical_market_movement_signal_diagnostics
新增 CLI：nutmeg-accuracy-historical-market-movement-signal-diagnostics，用于诊断 opening-to-closing 1X2 odds movement 是否真实改善 outcome probability
该诊断只读取 frozen HistoricalRecommendationSlice.feature_snapshot.features_json.prematch_context.odds_movement，不调用 Provider、不连接 VPS、不改默认推荐路径、不做模型 promotion
每个 fixture/outcome 生成 HistoricalMarketMovementSignalObservation：opening_probability、closing_probability、probability_delta、movement_direction、actual_occurred、opening/closing binary Brier、opening/closing Log loss、closing_improved、is_strongest_fixture_movement 与 source refs
报告按 overall、outcome、movement_direction、delta_band、opening_probability_band、strongest_movement_direction、competition、competition_outcome、competition_direction 分组
每组输出 sample_count、actual_rate、closing_improved_rate、average probability delta、opening/closing Brier、opening/closing Log loss、calibration error 与 deltas
支持参数：min_abs_probability_delta、movement_direction_epsilon、delta_bands、opening_probability_bands、min_group_sample_size、include_competition_groups、observation_sample_limit
新增 deterministic tests 覆盖：方向分组可靠性、strongest movement 分组、delta band、最小 movement filter、CLI 参数映射正确
真实 football-data.co.uk 五大联赛 market-feature suite 诊断已输出到 configs/recommendations/historical_reports/football_data_co_uk_market_movement_signal_diagnostics_v1.json
report_key=historical_market_movement_signal_diagnostics:4afa1b5a35b0c710；slice_count=25；fixture_count=600；observation_count=1800；strongest_observation_count=600；skipped_fixture_count=0
整体信号：closing_improved_rate=0.5033333333333333、brier_score_delta=-0.0005550790758561686、log_loss_delta=-0.0015181205557339705、calibration_error_delta≈0
正向 segment：LIGUE_1 away_win closing_improved_rate=0.6083333333333333、brier_score_delta=-0.004886555980174734；strongest probability_shortened brier_score_delta=-0.0023954857567937693
负向 segment：delta_band=0.06: brier_score_delta=0.008271203266298488；SERIE_A overall brier_score_delta=0.0012113756405588427；SERIE_A home_win/away_win movement 均回退
当前判断：opening-to-closing movement 存在真实但不稳定的分段信号，不能全局作为概率替换或默认推荐因子；后续只能作为分联赛/分 outcome/分 delta-band 的候选特征进入 shadow gate
下一阶段路线：基于该诊断建立 segmented market-movement feature candidate，而不是继续全局套用 odds_movement_weight；候选必须按 segment 限定并继续通过 single-match Brier/Log loss/ECE 与 final-answer quality gate
README 更新 signal diagnostics CLI、真实 report key、整体/分段结果与非晋级判断；该能力属于“market movement reliability diagnostics / real feature quality / prediction accuracy mainline”，不接新 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-162 当前落地能力：

```text
新增 segmented market-movement feature candidate gate：nutmeg.recommendations.historical_market_movement_segment_gate
新增 CLI：nutmeg-recommendation-historical-market-movement-segment-gate
该 gate 读取/生成 historical market movement signal diagnostics，只选择 top positive 或显式 segment_group_keys 的分段信号，不全局套用 opening-to-closing movement
每个候选只在命中 segment 的 1X2 outcome 上按 probability_delta * movement_weight 做 shadow 概率移动，并用 max_probability_shift 限制最大改动；随后对 1X2 三项概率重新归一化
候选 slice 只修改 prediction.probability、model_edge、model_version 与 metadata_json；metadata_json 写入 gate_id、candidate_id、segment_group_key、matched outcomes、probability shifts、diagnostics_report_key 与 shadow_only 标记；原 frozen slice 不被修改
每个候选同时跑 single-match gate 与 final-answer quality gate：single-match 检查 adjusted fixtures 上的 hit_rate/Brier/log-loss delta；final-answer gate 使用同一 optimizer_profile 对比 baseline slice 与 adjusted slice
CLI 支持 segment_group_keys、top_positive_segment_limit、min_segment_sample_size、segment delta 门槛、movement_weight、max_probability_shift、single-match 门槛、diagnostics 参数、backtest 参数与 HistoricalRecommendationSuiteQualityGateOptions
新增 deterministic tests 覆盖：正向 segment shadow candidate 通过；过严 single-match gate 会拒绝；CLI 参数映射正确
真实 football-data.co.uk 五大联赛 market-feature suite segment gate 已输出到 configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_gate_v1.json
report_key=historical_market_movement_segment_gate:77d3815ce33c9953；diagnostics_report_key=historical_market_movement_signal_diagnostics:4afa1b5a35b0c710
本轮 gate：25 slices、600 fixtures、1800 diagnostics observations、6 candidates；accepted_count=3；rejected_count=3
最佳候选：delta_band:0.03:0.06；adjusted_fixture_count=174；adjusted_prediction_count=522；decision=accepted
最佳候选 single-match delta：hit_rate_delta=0.04022988505747127、hit_count_delta=7、brier_score_delta=-0.003199226213764339、log_loss_delta=-0.0056378590359547065、average_actual_probability_delta=0.0009546628758180242
最佳候选 final-answer delta：final_hit_rate_delta=0.0、final_answer_changed_count=1、brier_score_delta=-0.0010253961702982317、log_loss_delta=-0.0021553046169603407、mean_calibration_error_delta=-0.001045519383702287、roi_delta=0.0
另外通过候选：competition_outcome:LA_LIGA:home_win、strongest_movement_direction:probability_shortened；被拒候选包括 LIGUE_1 drift/home/away segments，原因是 final-answer 层 suite_status、Brier、log-loss、calibration 回退
当前判断：中等幅度 probability movement 已成为可用 shadow 候选，但只能作为 segmented feature candidate 继续观察；默认推荐路径仍不启用，后续需进入 successor-chain quality gate 与更大真实样本验证
README 更新 segment gate CLI、真实 report key、accepted/rejected 结果、最佳候选 delta 与非默认启用判断；该能力属于“segmented market movement feature candidate / single-match + final-answer gate / accuracy-first promotion guardrail”，不接新 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-163 当前落地能力：

```text
新增 market-movement segment quality cycle：nutmeg.recommendations.historical_market_movement_segment_quality_cycle
新增 CLI：nutmeg-recommendation-historical-market-movement-segment-quality-cycle
该 cycle 消费 historical_market_movement_segment_gate 报告，不重新跑 Provider、不连接 VPS、不改默认推荐路径；用于把已通过的 shadow segment candidate 放进更严格的生命周期晋级检查
cycle 检查 accepted_candidate_count、best_candidate_accepted、best_final_answer_changed_count、best_final_hit_rate_delta、best_brier_score_delta、best_log_loss_delta、best_mean_calibration_error_delta
cycle 支持可选 successor-chain evaluation report：若传入 RecommendationSuccessorChainEvaluationResult，则继续检查 successor_chain_evaluation_passed、effective_leaf_count、active_edge_count、critical_issue_count、ambiguous_source_count、source_status_sync_required_count
新增 --require-successor-chain-evaluation；启用后如果未提供 successor-chain evaluation report，cycle 明确失败，避免把离线 shadow 结果误当作 recommendation lifecycle ready
新增 deterministic tests 覆盖：带 clean successor-chain evaluation report 时通过；强制 successor-chain 但缺失报告时失败；best final-answer changed count 不达标时失败；CLI 参数映射正确
真实 football-data.co.uk 五大联赛 market movement segment quality cycle 已输出到 configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_quality_cycle_v1.json
cycle_key=historical_market_movement_segment_quality_cycle:802cfe3f4712bdc7；status=passed；segment_gate_report_key=historical_market_movement_segment_gate:77d3815ce33c9953
离线 cycle 结果：candidate_count=6；accepted_count=3；best_segment_group_key=delta_band:0.03:0.06；best_final_answer_changed_count=1；best final-answer metric checks 全部通过
本次离线 cycle 未附加 persisted successor-chain evaluation report，因此 successor_chain_evaluation_present=false 且该检查为 skipped；如果未来用于真实 recommendation lifecycle promotion，必须使用 --require-successor-chain-evaluation 并提供同一候选对应的 persisted successor-chain evaluation report
当前判断：market movement segment 仍保持 shadow-only；它已通过离线 segment quality cycle，但尚未通过真实 persisted successor-chain lifecycle gate，不能进入默认推荐策略
README 更新 segment quality cycle CLI、真实 cycle key、通过检查与 successor-chain 缺失边界；该能力属于“shadow candidate lifecycle promotion guardrail / successor-chain hook / accuracy-first evidence discipline”，不接新 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-164 当前落地能力：

```text
Successor Chain Evaluation CLI 增加 --output-path，可把 RecommendationSuccessorChainEvaluationResult 直接写成 JSON artifact，供后续 quality cycle 消费
更新 nutmeg.recommendations.successor_chain_evaluation:main：运行结果先序列化为 JSON；若传 output_path，则创建父目录并写入文件，同时仍打印到 stdout；失败退出逻辑保持不变
新增/更新 deterministic tests 覆盖 successor-chain evaluation CLI 参数映射中的 output_path，并回归 market-movement segment quality cycle 的 successor-chain report 消费路径
README 更新 successor-chain evaluator 示例，加入 output-path；同时补充 market-movement segment strict lifecycle 命令：先生成 successor-chain evaluation report，再用 --require-successor-chain-evaluation 强制 segment quality cycle 复验
本地未启动 Nutmeg Postgres 生成 strict persisted report；Docker 当前仅检测到 zeus-backend、zeus-frontend、zeus-postgres、zeus-redis，按用户要求不触碰 zeus。因此本轮不伪造 persisted successor-chain 结果，只补齐真实环境可执行的报告落盘入口
当前判断：market-movement segment 的离线 cycle 已可升级为 strict lifecycle cycle，但必须等存在同一候选对应的 persisted recommendation runs 后再生成 successor-chain evaluation report；默认推荐路径仍不启用
该能力属于“Successor Chain Evaluation artifact / strict lifecycle quality-cycle bridge / accuracy evidence hygiene”，不接新 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-165 当前落地能力：

```text
完成 strict successor-chain lifecycle smoke：使用一次性 Nutmeg Postgres 容器应用 migrations、写入 source/successor recommendation_runs，并通过 nutmeg-recommendation-successor-chain-evaluate --output-path 生成真实从 Postgres 读取的 successor-chain evaluation artifact
烟测容器名为 nutmeg-successor-chain-smoke-*，端口随机绑定，命令结束后自动删除；本地 Docker 复核只剩 zeus-backend、zeus-frontend、zeus-postgres、zeus-redis，未触碰 zeus
新增/生成 configs/recommendations/historical_reports/local_successor_chain_evaluation_smoke_v1.json
successor-chain smoke 结果：passed=true；run_count=2；active_run_count=2；active_edge_count=1；effective_chain_count=1；effective_leaf_count=1；effective_leaf_recommendation_run_ids=[2]；superseded_source_recommendation_run_ids=[1]；chain_integrity_critical_issue_count=0；source_status_sync_required_count=0；warnings=[]
使用该 successor-chain report 作为 --successor-chain-evaluation-report-path，重新运行 market-movement segment quality cycle 的 strict 模式：--require-successor-chain-evaluation、min_successor_effective_leaf_count=1、min_successor_active_edge_count=1、max critical/ambiguous/status-sync=0
新增/生成 configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_quality_cycle_strict_smoke_v1.json
strict cycle 结果：cycle_key=historical_market_movement_segment_quality_cycle:117f2c25fa748e34；status=passed；successor_chain_evaluation_present=true；successor_chain_evaluation_passed=true；successor_chain_effective_leaf_count=1；successor_chain_active_edge_count=1；best_segment_group_key=delta_band:0.03:0.06；best_final_answer_changed_count=1；warnings=[]
当前判断：strict lifecycle quality-cycle wiring 已经从“文档命令”推进到“可执行 artifact smoke”；但 smoke 中的 recommendation_runs 是隔离测试链路，不代表真实生产推荐候选已完成晋级。默认推荐路径仍不启用 market movement segment
README 更新本地 strict smoke artifact、通过指标与 zeus 未触碰说明；该能力属于“strict successor-chain artifact smoke / lifecycle evidence bridge / accuracy-first promotion hygiene”，不接新 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-166 当前落地能力：

```text
新增 persisted lifecycle smoke runner：nutmeg.recommendations.persisted_lifecycle_smoke
新增 CLI：nutmeg-recommendation-persisted-lifecycle-smoke
该 runner 把真实推荐持久化生命周期串成可重复 smoke：deterministic baseline seed -> global planner committed source run -> lock_leg -> successor_recompute committed successor run -> source_status_sync -> successor_chain_evaluation
默认不执行写入；必须显式传 --commit 才会写入 seed/recommendation_runs/lifecycle events，避免误碰生产库
source run 使用 recommendation_global_planner_v3_1 的真实候选池和最终答案选择；successor run 使用 locked_leg_successor_recompute_v3_1 的真实重算路径，不再依赖手工 SQL 造 recommendation_runs
successor-chain gate 强制 min_effective_leaf_count=1、min_active_edge_count=1、max critical/ambiguous/source-status-sync=0；source_status_sync 后旧 source 必须变为 superseded
新增 deterministic tests 覆盖：默认 dry-run 阻止写入；commit 模式按顺序调用 seed/global planner/lock/successor/source sync/chain evaluation；CLI 参数映射正确
真实本地 smoke 使用一次性 Nutmeg Postgres 容器应用 migrations，并运行 nutmeg-recommendation-persisted-lifecycle-smoke --commit --output-path configs/recommendations/historical_reports/local_persisted_lifecycle_smoke_v1.json
smoke 结果：passed=true；source_recommendation_run_id=1；successor_recommendation_run_id=2；locked_fixture_ids=["bench_v3_001"]；continuation_fixture_ids=["bench_v3_008","bench_v3_003","bench_v3_007"]；source_status_synced=true；successor_chain_evaluation_passed=true；effective_leaf_count=1；active_edge_count=1；critical_issue_count=0；source_status_sync_required_count=0；warning_count=0
烟测容器名为 nutmeg-persisted-lifecycle-smoke-*，端口随机绑定，命令结束后自动删除；Docker 复核仍只剩 zeus-backend、zeus-frontend、zeus-postgres、zeus-redis，未触碰 zeus
当前判断：strict lifecycle gate 已从手写 source/successor rows 升级为真实 recommendation 持久化流程 smoke；默认推荐路径仍保持不启用 market movement segment，下一步应把该 persisted lifecycle smoke 接入更大历史样本/真实候选池质量门禁
README 更新 persisted lifecycle smoke CLI、artifact 与通过指标；该能力属于“real persisted recommendation lifecycle smoke / successor chain evaluation / quality gate hardening”，不接新 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-167 当前落地能力：

```text
market-movement segment quality cycle 接入 persisted lifecycle smoke artifact
HistoricalMarketMovementSegmentQualityCycleOptions 新增 require_persisted_lifecycle_smoke、require_persisted_lifecycle_source_status_synced、min_persisted_lifecycle_effective_leaf_count、min_persisted_lifecycle_active_edge_count、max_persisted_lifecycle_critical_issue_count、max_persisted_lifecycle_source_status_sync_required_count
CLI 新增 --persisted-lifecycle-smoke-report-path、--require-persisted-lifecycle-smoke、--allow-unsynced-persisted-lifecycle-source-status、--min/--max persisted lifecycle 门槛参数
cycle 现在可同时检查三层证据：segment gate 离线 final-answer 指标、successor-chain evaluation artifact、persisted lifecycle smoke artifact
新增 persisted lifecycle 检查项：persisted_lifecycle_smoke_present、persisted_lifecycle_smoke_passed、persisted_lifecycle_source_status_synced、persisted_lifecycle_successor_chain_evaluation_passed、effective_leaf_count、active_edge_count、critical_issue_count、source_status_sync_required_count
缺失 required persisted smoke 会产生 market_movement_segment_quality_cycle:missing_persisted_lifecycle_smoke；source 未同步 superseded 时会阻断 persisted lifecycle 晋级
新增 deterministic tests 覆盖：带 persisted lifecycle smoke 时通过；强制但缺失 smoke 时失败；source_status_synced=false 时失败；CLI 参数映射正确
使用真实 football-data.co.uk segment gate report + local successor-chain artifact + local persisted lifecycle smoke artifact 生成 configs/recommendations/historical_reports/football_data_co_uk_market_movement_segment_quality_cycle_persisted_lifecycle_smoke_v1.json
新 strict cycle 结果：cycle_key=historical_market_movement_segment_quality_cycle:33ca81de702b8ac1；status=passed；accepted_count=3；best_segment_group_key=delta_band:0.03:0.06；best_final_answer_changed_count=1；successor_chain_evaluation_present=true；persisted_lifecycle_smoke_present=true；persisted_lifecycle_smoke_passed=true；persisted_lifecycle_source_status_synced=true；persisted_lifecycle_effective_leaf_count=1；persisted_lifecycle_active_edge_count=1；persisted_lifecycle_critical_issue_count=0；persisted_lifecycle_source_status_sync_required_count=0；warnings=[]
当前判断：market movement segment 仍保持 shadow-only；但 strict quality-cycle 已能要求真实持久化生命周期 smoke 与 successor-chain gate 同时通过。下一步应把该门禁接入更大历史样本的周期质量门禁，而不是直接开启默认推荐路径
README 更新 persisted lifecycle smoke quality-cycle 命令、artifact 与通过指标；该能力属于“strict shadow candidate lifecycle gate / persisted lifecycle evidence / accuracy-first promotion discipline”，不接新 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-168 当前落地能力：

```text
historical suite quality gate 接入 lifecycle quality cycle evidence
新增轻量 HistoricalRecommendationLifecycleQualityCycleEvidence，用于读取 strict lifecycle cycle JSON artifact，不直接 import market-movement cycle 模块，避免 recommendations.__init__ -> historical_quality_gate -> market_movement_cycle -> accuracy/api 的循环导入
HistoricalRecommendationSuiteQualityGateOptions 新增 require_lifecycle_quality_cycle、require_lifecycle_persisted_smoke、require_lifecycle_source_status_synced、min_lifecycle_effective_leaf_count、min_lifecycle_active_edge_count、max_lifecycle_critical_issue_count、max_lifecycle_source_status_sync_required_count
nutmeg-recommendation-historical-suite-gate CLI 新增 --lifecycle-quality-cycle-report-path、--require-lifecycle-quality-cycle、--allow-missing-lifecycle-persisted-smoke、--allow-unsynced-lifecycle-source-status、--min/--max lifecycle 门槛参数
suite gate 新增 checks：lifecycle_quality_cycle_present、lifecycle_quality_cycle_passed、lifecycle_persisted_smoke_present、lifecycle_persisted_smoke_passed、lifecycle_source_status_synced、lifecycle_effective_leaf_count、lifecycle_active_edge_count、lifecycle_critical_issue_count、lifecycle_source_status_sync_required_count
summary_json 输出 lifecycle_quality_cycle_key、report_path、persisted smoke present/passed、source_status_synced、effective_leaf_count、active_edge_count、critical_issue_count、source_status_sync_required_count
新增 deterministic tests 覆盖：带 lifecycle quality cycle 时通过；required 但缺失时失败；source_status_synced=false 时失败；CLI 参数映射正确
使用 football_data_co_uk_core_5_seasons_suite 30-slice 历史样本 + V3.1-167 strict lifecycle cycle artifact 生成 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_suite_gate_with_lifecycle_v1.json
真实 gate 结果：gate_key=historical_recommendation_suite_quality_gate:96133aaf34afdaa7；status=passed；suite_status=unchanged；slice_count=30；comparison_count=30；lifecycle_quality_cycle_present=true；lifecycle_quality_cycle_passed=true；lifecycle_persisted_smoke_present=true；lifecycle_source_status_synced=true；lifecycle_effective_leaf_count=1；lifecycle_active_edge_count=1；lifecycle_critical_issue_count=0；lifecycle_source_status_sync_required_count=0；failed_checks=[]
当前判断：strict lifecycle gate 已进入更大的 historical suite quality gate，候选不再只靠单独 artifact 自证；后续可把同一机制接到 benchmark/cycle runner 的持久化历史质量门禁中
README 更新 30-slice suite gate + lifecycle evidence 命令和 artifact；该能力属于“historical final-answer gate + lifecycle evidence integration / accuracy-first promotion discipline”，不接新 API，不接 VPS，不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-169 当前落地能力：

```text
persisted benchmark quality gate 接入 historical suite quality gate evidence
新增轻量 RecommendationHistoricalSuiteQualityGateEvidence，用于读取 historical suite gate JSON artifact，并避免 benchmark gate 直接依赖 historical gate 执行链
RecommendationBenchmarkQualityGateOptions 新增 historical_suite_quality_gate_report_path、require_historical_suite_quality_gate、require_historical_suite_lifecycle_evidence、require_historical_suite_lifecycle_source_status_synced、historical suite 样本/比较数/failed check/lifecycle leaf/edge/critical/source sync 门槛
nutmeg-recommendation-benchmark-quality-gate CLI 新增 --historical-suite-quality-gate-report-path、--require-historical-suite-quality-gate、--allow-missing-historical-suite-lifecycle-evidence、--allow-unsynced-historical-suite-lifecycle-source-status、--min/--max historical suite lifecycle 门槛参数
nutmeg-recommendation-benchmark-cycle CLI 同步新增 --gate-historical-suite-quality-gate-report-path、--gate-require-historical-suite-quality-gate 与对应 --gate-min/--gate-max 参数，使周期 benchmark + gate 可以消费同一 historical suite lifecycle evidence
benchmark quality gate 新增 checks：historical_suite_quality_gate_present、historical_suite_quality_gate_passed、historical_suite_slice_count、historical_suite_comparison_count、historical_suite_failed_check_count、historical_suite_lifecycle_quality_cycle_present/passed、historical_suite_lifecycle_persisted_smoke_present/passed、historical_suite_lifecycle_source_status_synced、historical_suite_lifecycle_effective_leaf_count、historical_suite_lifecycle_active_edge_count、historical_suite_lifecycle_critical_issue_count、historical_suite_lifecycle_source_status_sync_required_count
summary_json 输出 historical suite gate path/key/status/suite_status、slice/comparison/failed check 计数，以及 lifecycle/persisted smoke/source sync 摘要，便于后续趋势存储与质量门禁审计
新增 deterministic tests 覆盖：带 historical suite lifecycle evidence 时通过；required 但缺失 evidence 时失败；source_status_synced=false 时失败；从 report path 加载 evidence；cycle CLI 参数映射正确
本阶段只把已有 30-slice historical suite + lifecycle evidence 纳入 persisted benchmark gate，不改变默认推荐路径，不接新 API，不接 VPS，不接自动下注/支付/钱包，不展示内部策略，不引入保证盈利表述
当前判断：strict lifecycle evidence 已从单独 artifact -> historical suite gate -> persisted benchmark quality gate 贯通；下一步应进入周期质量门禁报告的趋势化/持久化审计，或转向提升最终答案 ROI、冷门捕捉率与分联赛适配的候选质量函数
README 更新 benchmark gate 消费 historical suite lifecycle artifact 的命令；该能力属于“periodic quality gate hardening / final-answer suite evidence / lifecycle promotion guardrail”
```

V3.1-170 当前落地能力：

```text
新增 recommendation_benchmark_cycle_runs 迁移，用于持久化 scheduled benchmark + quality gate 的周期质量报告
新增 PostgresRecommendationBenchmarkCycleRunRepository、StoredRecommendationBenchmarkCycleRun 与 save_cycle_report 选项；benchmark cycle 可在 --save-cycle-report 时保存 cycle_key、status、schedule_key、benchmark_key、stored benchmark run、gate key/status/pass、failed checks、historical suite gate key/pass、lifecycle source sync 与 leaf/edge/critical/source-sync-required 摘要
nutmeg-recommendation-benchmark-cycle CLI 新增 --save-cycle-report；该开关独立于 --save-report，前者保存周期门禁审计，后者保存 benchmark runner 矩阵报告
cycle summary_json 现在透传 gate_failed_checks、historical_suite_quality_gate_present/pass/key/status/suite_status、slice/comparison/failed check 计数、lifecycle quality cycle、persisted smoke、source_status_synced、effective leaf、active edge、critical issue 与 source-status-sync-required 计数
新增 deterministic tests 覆盖：cycle summary 携带 historical suite lifecycle evidence；save_cycle_report 触发 repository 保存；Postgres repository 写入/读取参数正确；CLI 参数映射正确
README 更新 benchmark-cycle --save-cycle-report 用法；该能力属于“周期质量门禁趋势化 / persisted audit trail / lifecycle promotion evidence”，不接新 API，不接 VPS，不接自动下注/支付/钱包，不展示内部策略，不引入保证盈利表述
当前判断：周期质量门禁已能把 final-answer suite evidence 与 recommendation lifecycle evidence 留成可查询时间序列；下一步应减少继续铺治理管线，回到核心准确性：围绕 ROI、冷门捕捉率、分联赛适配做候选质量函数/校准/特征候选实验，并继续用 final-answer gate 拦截不能晋级的方案
```

V3.1-171 当前落地能力：

```text
历史 Poisson 参数学习器新增 candidate_recency_half_life_days 与 candidate_home_away_split_weights 网格，支持一次性比较时间衰减和主客场拆分权重，而不是固定手填单个 recency_half_life_days / home_away_split_weight
CLI 新增 --candidate-recency-half-life-days 与 --candidate-home-away-split-weights；recency 候选支持 none/null/off/unweighted 表示不做时间衰减
candidate_key 会在非默认参数上追加 recency_* 与 homeaway_* 后缀，同时保持默认 None + 0.0 的旧 key 兼容
summary_json 记录实际候选 recency/home-away 网格，便于回测报告复盘
新增 deterministic tests 覆盖 recency/home-away 网格展开、候选 key、候选参数传递与 CLI 参数映射
使用 football_data_co_uk_core_5_seasons_suite 30-slice 历史样本运行 enhanced_weighted_home_away + 27 候选参数学习，生成 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_homeaway_recency_parameter_learning_v1.json
真实学习结果：learned_competition_count=6；candidate_count=27；validation_count=2062；EPL 选中 draw=0.4 + recency=180 + homeaway=0.35；法甲/德甲/意甲选中 draw=0.4 + recency=180 + homeaway=0；西甲/J1 选中 draw=0.4 + no-recency + homeaway=0
验证集整体相对 market-implied baseline 仍未改善：hit_rate_delta=-0.0218；brier_score_delta=+0.0182；log_loss_delta=+0.0266；expected_calibration_error_delta=+0.0025，因此该参数学习结果只作为模型研究证据，不进入默认推荐或 promotion
当前判断：免费历史赛果 + 赔率基准足够支持本轮核心参数学习验证，不需要付费数据；下一步应继续在核心模型层做 calibration / Dixon-Coles rho 联赛化 / 真实赛前特征，而不是继续堆外围 gate
该能力属于“core model parameter learning / league-specific Poisson tuning / accuracy-first evidence”，不接新 API，不接 VPS，不接自动下注/支付/钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-172 当前落地能力：

```text
修复历史参数学习器中 Dixon-Coles rho=0.0 候选被误替换为默认 -0.05 的问题；rho=0.0 是低比分相关修正的无相关对照，必须真实保留
新增 deterministic regression test 覆盖 _walk_forward_options 对 dixon_coles_rho=0.0 的传递，避免后续 DC rho grid 再被污染
使用 football_data_co_uk_core_5_seasons_suite 30-slice 历史样本运行 enhanced_weighted_home_away + Poisson 控制组 + Dixon-Coles rho [-0.15,-0.10,-0.05,0,0.05] + draw [0,0.4] + recency [none,180] + homeaway [0,0.35]，生成 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_dixon_recency_homeaway_parameter_learning_v1.json
真实学习结果：report_key=historical_poisson_parameter_learning:8a927bc93bf9af94；learned_competition_count=6；candidate_count=48；validation_count=2062；warnings=[]
联赛级选参结果：EPL 选中 rho=0.05 + draw=0.4 + recency=180 + homeaway=0.35；西甲/德甲选中 rho=-0.10；法甲选中 rho=-0.05；意甲选中 rho=-0.15；J1 选中 rho=0.0 + draw=0.4
验证集整体相对 market-implied baseline 仍未改善：hit_rate_delta=-0.0199；brier_score_delta=+0.0179；log_loss_delta=+0.0263；expected_calibration_error_delta=+0.0026，因此该 DC 联赛化结果只作为研究证据，不进入默认推荐或 promotion
当前判断：league-specific Dixon-Coles rho 选择已进入可重复离线验证，但当前免费历史赛果/赔率基准下仍不足以让独立比分模型击败市场基准；下一步应转向真实赛前特征样本质量，而不是继续扩大 rho/draw 网格
README 更新 rho=0.0 bug fix、DC + recency/homeaway 参数学习命令、报告路径和 shadow-only 结论；该能力属于“Dixon-Coles parameter integrity / league-specific rho learning / accuracy-first evidence”，不接新 API，不接 VPS，不接自动下注/支付/钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-173 当前落地能力：

```text
新增历史赛前特征参数学习组件 nutmeg.accuracy.historical_prematch_feature_parameter_learning
新增 CLI：nutmeg-accuracy-prematch-feature-parameter-learning；按 competition 将 market-feature slices 分成 training seasons 与 holdout validation seasons，在训练赛季选择 prematch feature adjustment 权重，只在最新 holdout 赛季评估
候选权重覆盖 max_probability_shift、odds_movement_weight、tracked_fragility_weight、lineup_strength_weight、draw_signal_weight，并复用既有 historical_prematch_feature_ablation 的概率调整与指标口径
新增 deterministic tests 覆盖：多赛季 holdout 学习、训练赛季不足跳过、CLI 参数映射
使用 football_data_co_uk_market_feature_multi_season_suite 五大联赛 25-slice market-feature 样本运行 holdout 学习，生成 configs/recommendations/historical_reports/football_data_co_uk_market_feature_holdout_parameter_learning_v1.json
真实学习结果：report_key=historical_prematch_feature_parameter_learning:308c08aaeab87c39；learned_competition_count=5；candidate_count=36；validation_count=120；warnings=[]
分联赛结果：Bundesliga/La Liga 在 holdout 上 Brier 与 log loss 小幅改善；EPL 选择 no-op；Ligue 1 命中率改善但概率质量回退；Serie A 回退
整体 holdout 结果：hit_rate_delta=+0.0083；brier_score_delta=+0.00045；log_loss_delta=+0.00052；expected_calibration_error_delta=+0.00097，因此 market movement 作为赛前特征有信号，但还不能进入默认推荐或 promotion
当前判断：当前免费 football-data.co.uk 样本足够验证开盘/临场赔率变化的方向性，但 24 fixtures/league-season 的样本太小且缺少 lineup/injury/news，下一步应扩充真实赛前特征样本质量，而不是把小样本 market movement 权重推入生产推荐
README 更新 holdout parameter-learning CLI、报告路径、核心指标与 shadow-only 结论；该能力属于“real prematch feature holdout learning / market movement evidence / anti-overfit accuracy loop”，不接新 API，不接 VPS，不接自动下注/支付/钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-174 当前落地能力：

```text
按 docs/nutmeg 数据接入分级，先扩展 A 类结构稳定联赛，而不是直接把日韩二级、欧战、世界杯混入主训练路径
新增赛事配置：NED_EREDIVISIE、PRT_PRIMEIRA_LIGA、ENG_CHAMPIONSHIP、GER_2_BUNDESLIGA、ITA_SERIE_B、ESP_SEGUNDA_DIVISION、FRA_LIGUE_2、JPN_J2、KOR_K_LEAGUE_1、UEFA_CHAMPIONS_LEAGUE、UEFA_EUROPA、UEFA_CONFERENCE_LEAGUE、FIFA_WORLD_CUP
football-data.co.uk market-feature batch 映射新增 N1/P1/E1/D2/I2/SP2/F2 -> Nutmeg competition_id，避免新增联赛在样本生成中退化成 N1/P1 这类 provider code
冻结 football-data.co.uk 2020-2021 至 2024-2025 五季 A 类扩展联赛源 CSV：荷甲、葡超、英冠、德乙、意乙、西乙、法乙，共 35 个 source CSV
生成 expanded A-league market-feature suite：configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_market_feature_suite.json
该 suite 共 35 slices、2520 fixtures、13385 raw rows；feature completeness 35/35 passed，failed_input_count=0，market_movement_feature_ready=true
生成覆盖审计 v4：configs/recommendations/historical_reports/historical_sample_coverage_audit_v4.json；audit_key=historical_sample_coverage_audit:47baf09376fdcebe；source_count=5、slice_count=96、fixture_count=14460；market_feature_ready_source_ids 现在包含 top-five market-feature suite 与 expanded A-league suite
生成 expanded A-league holdout 参数学习报告：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_market_feature_holdout_parameter_learning_v1.json
学习结果：report_key=historical_prematch_feature_parameter_learning:2a9b71622b5229ae；learned_competition_count=7；candidate_count=36；validation_count=504；overall brier_score_delta=-0.0007808224、log_loss_delta=-0.0010814233、hit_rate_delta=0.0、expected_calibration_error_delta=+0.001445466
当前判断：A 类扩展联赛的 market movement 信号在概率质量上有轻微信号，但命中率未提升且 ECE 回退，因此仍保持 shadow-only，不进入默认推荐或 promotion
J2、K League、欧冠、欧联、欧协联、世界杯已进入 competition config，但因赛制/日历/杯赛上下文差异，仍需要 provider mapping、stage/two-leg/neutral-site context 与单独校准后再进入训练/推荐候选池
README 更新 expanded A-league suite、报告路径与 shadow-only 结论；该能力属于“competition expansion / real prematch feature sample coverage / accuracy-first shadow evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-175 当前落地能力：

```text
新增 competition_admission_gate 模块与 CLI：nutmeg-recommendation-competition-admission-gate
该 gate 消费 final-answer gate、feature holdout learning、coverage audit 三类证据，输出 accepted / shadow_only / rejected，并显式给出 production_recommendation_allowed、training_pool_allowed、shadow_allowed
新增 deterministic tests 覆盖：证据通过时 accepted；最终答案指标失败但样本足够时 shadow_only；最终答案样本不足时 rejected；CLI 写入报告与参数映射
对 expanded A-league suite 运行 1x1 到 8x1 final-answer admission gate，报告输出到 configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_candidate48_window4_1x1_to_8x1_admission_gate_v1.json
final-answer gate 结果：gate_key=historical_recommendation_suite_quality_gate:54304497c2d34b96；candidate_final_hit_sample_size=35；candidate_final_hit_rate=0.42857142857142855；candidate_roi=-0.14542857142857146；suite_status=mixed；final_hit_rate_delta=-0.11428571428571427；roi_delta=-0.32571428571428573
分联赛 ROI：ENG_CHAMPIONSHIP=0.812、GER_2_BUNDESLIGA=0.482、NED_EREDIVISIE=0.248、PRT_PRIMEIRA_LIGA=-0.006、ESP_SEGUNDA_DIVISION=-0.554、FRA_LIGUE_2=-1.0、ITA_SERIE_B=-1.0
expanded A-league upset capture report 输出到 configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_candidate48_window4_upset_capture_profiles_v1.json；report_key=historical_upset_capture_profiles:238347afa6ff8baa；opportunity_count=1；capture_count=0；selected_favorite_miss_count=1
admission gate 报告输出到 configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_competition_admission_gate_v1.json；report_key=competition_admission_gate:6d4325ae733b1d76；decision=shadow_only
当前判断：expanded A-league 样本可以继续用于 shadow 研究和分联赛 profile 搜索，但不能进入默认推荐路径或训练池；主要 blocker 是最终答案命中率不足、相对 baseline final hit 回退、Ligue 2 / Serie B / Segunda ROI 不达标，以及 feature ECE 轻微回退
README 更新 admission gate 命令、报告路径与 shadow-only 结论；该能力属于“competition admission control / final-answer accuracy guardrail / competition expansion safety”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-176 当前落地能力：

```text
competition_profile_evidence summary_json 新增 warning_count 与 warning_counts 聚合，避免 expanded suite 报告被重复 scenario_failed warning 淹没，同时不改变任何推荐、profile 选择或 admission 决策逻辑
新增 deterministic test 覆盖重复 warning 聚合：薄样本同时记录 historical_backtest_no_final_answer 与 single/multiple insufficient_distinct_fixture_candidates
对 expanded A-league suite 运行 1x1 到 8x1 single/multiple competition profile evidence，报告输出到 configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_candidate48_window4_competition_profile_evidence_v1.json
profile evidence 结果：report_key=historical_competition_profile_evidence:53e6f730f5617dbe；slice_count=35；competition_count=7；scenario_metric_count=21；accepted_count=0；retained_count=7；accepted_profile_adjustments={}
分联赛结论：ENG_CHAMPIONSHIP、GER_2_BUNDESLIGA、NED_EREDIVISIE、PRT_PRIMEIRA_LIGA、ESP_SEGUNDA_DIVISION、FRA_LIGUE_2、ITA_SERIE_B 全部保留 current_final_answer / 1x1:single；没有任何 expanded 联赛 profile 进入 production config
负 ROI baseline 联赛仍为 ESP_SEGUNDA_DIVISION、FRA_LIGUE_2、ITA_SERIE_B、PRT_PRIMEIRA_LIGA；Championship / 德乙 / 荷甲虽然 baseline ROI 为正，但高 ROI 替代候选样本不足或会降低 hit count，不能提升为 profile
warning_count=476，warning_counts 全部来自 insufficient_distinct_fixture_candidates；这说明 expanded A-league suite 对长串关 profile promotion 仍然太薄，只能继续用于 shadow 研究、候选失败诊断和后续样本扩充
README 更新 expanded A-league profile evidence 报告、report_key、retained 结论与 warning 聚合字段；该能力属于“competition profile evidence / expansion safety / accuracy-first shadow research”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-177 当前落地能力：

```text
新增 historical_slice_windowing 模块与 CLI：nutmeg-recommendation-historical-slice-window；它从既有 frozen historical recommendation slices 生成 rolling-window slices 与 suite manifest，不重新下载数据
windowing 默认按 kickoff 顺序每 12 场生成一个窗口，stride=12，min_fixture_count=8；fixture prediction_time_utc 与 feature_time_utc 归一到窗口 as_of_time_utc，使 1x1 到 8x1 final-answer 回测拥有足够 pre-kickoff 候选；生成 metadata 明确标记 prediction_time_policy=window_as_of_time，作为 shadow evaluation sample 使用
新增 deterministic tests 覆盖：窗口切分、pre-kickoff eligibility、feature as_of guard 更新、slice/manifest/report 写入
competition_admission_gate CLI 新增 --block-feature-regression；当 final-answer gate 通过但 feature learning 指标回退时，可强制保持 shadow_only，防止扩展联赛因单一指标通过而误入 production/training pool
新增 deterministic test 覆盖 feature regression block：final-answer 证据通过但 ECE 回退时，decision=shadow_only，production_recommendation_allowed=false，training_pool_allowed=false
生成 expanded A-league rolling-window suite：configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json
生成报告：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_generation_v1.json；report_key=historical_slice_windowing:f6b57960e7ad63fd；source_slice_count=35；generated_slice_count=210；generated_fixture_count=2520；每个扩展联赛 30 个 windowed final-answer samples
样本质量报告：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_sample_quality_v1.json；210/210 slices passed；warnings=[]
尝试运行 candidate12/window4 + max_candidates_per_fixture=2 的完整 solver-backed final-answer gate，但 multi-selection DP 搜索过重，已中止；当前阶段改用 candidate8/top1 smoke lane，仍覆盖 1x1 到 8x1 single/multiple，但每场只取最高候选，避免把本阶段拖回性能优化
rolling-window final-answer gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate8_top1_final_answer_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:1040fa1e645c9594；passed=true；candidate_final_hit_sample_size=210；candidate_final_hit_rate=0.6142857142857143；candidate_roi=-0.07852380952380954；worst_competition_id=ITA_SERIE_B；worst_competition_candidate_roi=-0.21166666666666673；warnings=[]
rolling-window profile evidence：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate8_top1_competition_profile_evidence_v1.json；report_key=historical_competition_profile_evidence:18e2fc047101db25；slice_count=210；scenario_metric_count=105；accepted_count=0；retained_count=7；warning_count=0；所有 expanded 联赛仍保留 current_final_answer / 1x1:single，不写入 production profile
覆盖审计 v5：configs/recommendations/historical_reports/historical_sample_coverage_audit_v5.json；audit_key=historical_sample_coverage_audit:3b0e62c5dd7d4f03；source_count=6；slice_count=306；fixture_count=16980；market_feature_ready_source_ids 新增 football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1
rolling-window admission gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_competition_admission_gate_v1.json；report_key=competition_admission_gate:ee598bb519d15f3a；decision=shadow_only；production_recommendation_allowed=false；training_pool_allowed=false；shadow_allowed=true；blockers=[]；warnings=[feature_expected_calibration_error_regressed]
当前判断：rolling-window 解决了 final-answer 样本过薄和候选不足问题，且 final-answer 命中率达到 0.6143；但整体 ROI 仍为负，profile evidence 没有接受任何长串关替代形态，feature holdout ECE 仍回退，所以 expanded A-league 继续 shadow-only，不进入默认推荐或训练池
README 更新 rolling-window 生成命令、报告路径、门禁结果与 shadow-only 结论；该能力属于“real historical distribution expansion / final-answer sample quality / admission safety”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-178 当前落地能力：

```text
对 solver-backed 复式优化器做性能收口：_FixtureOptionVariant 缓存 sort_key、selected_probability、score_sum/score_count；_SolverState 缓存概率乘积、分数聚合与 variant quality，避免动态规划剪枝阶段反复重算候选质量
动态规划搜索新增剩余 fixture group 可完成性剪枝：当 selected_count + remaining_group_count 已无法达到目标串关腿数时，直接丢弃状态 bucket；同时保留每 bucket 的去重与 states_per_bucket 上限
exact integer search 改为搜索期间使用等价轻量指标打分，只对最终最佳状态构造完整 ParlayEvaluation / atomic bets；避免 candidate12/window4 gate 中大量重复 deep-copy 与 atomic bet 展开
solver 默认 exact_state_limit 从 25000 降至 2000，使中等规模组合更早进入 bounded dynamic path；该变化用于保持真实历史 gate 可运行，不改变 2x1 小规模 exact solver 测试路径
新增 deterministic test：test_multiple_optimizer_prunes_dynamic_solver_for_budgeted_large_window，覆盖 8x1、复式、预算 64、动态规划剪枝、generated_state_count > evaluated_complete_states 与 pruned_state_count > 0
重新跑通 expanded A-league rolling-window candidate12/window4 final-answer gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_final_answer_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:3e1861f6211b860a；status=passed；suite_status=improved；candidate_final_hit_sample_size=210；candidate_final_hit_rate=0.6476190476190476；candidate_roi=-0.051904761904761905；candidate_profit_loss=-21.8；worst_competition_id=ITA_SERIE_B；worst_competition_candidate_roi=-0.1586666666666666；warnings=[]
新增 candidate12/window4 admission gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_admission_gate_v1.json；report_key=competition_admission_gate:4a230feb19e97e78；decision=shadow_only；production_recommendation_allowed=false；training_pool_allowed=false；shadow_allowed=true；blockers=[]；warnings=[feature_expected_calibration_error_regressed]
当前判断：candidate12/window4 已从“性能不可跑通”升级为可重复 shadow gate，且 final-answer 命中率与 ROI 均优于 candidate8/top1 smoke；但 feature holdout ECE 仍回退，因此 expanded A-league 仍不进入默认推荐或训练池
README 更新 rolling-window candidate12/window4 gate、admission 报告与 shadow-only 结论；该能力属于“bounded optimizer scalability / final-answer quality gate / admission safety”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-179 当前落地能力：

```text
新增 competition_profile_proposal 模块与 CLI：nutmeg-recommendation-competition-profile-proposal
该 CLI 消费 competition profile evidence 与 admission gate 两类报告，把 accepted profile evidence 转成治理型 proposal artifact；当 admission 仍为 shadow_only 时，proposal 会保留 profile 候选但显式写入 production_recommendation_allowed=false、training_pool_allowed=false、shadow_allowed=true，避免把 shadow evidence 误写入默认推荐配置
新增 deterministic tests 覆盖：admission shadow_only 时 proposal status=shadow_only；admission accepted 时 proposal status=production_ready；无 accepted evidence 时 status=no_candidates；CLI 写入 shadow report；CLI 参数映射
重新运行 expanded A-league rolling-window candidate12/window4 competition profile evidence：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_profile_evidence_v1.json；report_key=historical_competition_profile_evidence:c4109a3055614571；slice_count=210；competition_count=7；scenario_metric_count=105；baseline_metric_count=7；accepted_count=2；retained_count=5；warning_count=0
accepted profile evidence：ESP_SEGUNDA_DIVISION -> 2x1:multiple，hit_count_delta=4，roi_delta=0.0652133333333334，profit_loss_delta=1.6711999999999847；ITA_SERIE_B -> 2x1:multiple，hit_count_delta=3，roi_delta=0.18836，profit_loss_delta=16.646400000000014
retained competitions：ENG_CHAMPIONSHIP、FRA_LIGUE_2、GER_2_BUNDESLIGA、NED_EREDIVISIE、PRT_PRIMEIRA_LIGA 均保留 current_final_answer / 1x1:single；高 ROI 长串关候选因 reduced_hit_count 被拒绝
生成 profile proposal 报告：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_profile_proposal_v1.json；report_key=competition_profile_proposal:0d3a35495cf9c9db；status=shadow_only；proposal_count=2；profile_evidence_report_key=historical_competition_profile_evidence:c4109a3055614571；admission_report_key=competition_admission_gate:4a230feb19e97e78；admission_decision=shadow_only；warnings=[competition_profile_proposal:admission_shadow_only]
当前判断：candidate12/window4 rolling evidence 已找到两个有价值的分联赛 profile 候选，但 admission gate 仍因 feature_expected_calibration_error_regressed 保持 shadow_only，所以不修改 configs/recommendations/competition_recommendation_profiles.json，不进入默认推荐或训练池
README 更新 candidate12/window4 profile evidence、proposal CLI、报告路径与 shadow-only 结论；该能力属于“competition profile governance / admission-safe profile proposal / accuracy-first expansion”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-180 当前落地能力：

```text
prematch feature parameter learning 增加两层校准保护：--max-training-expected-calibration-error-delta 用于训练期候选筛选，--max-validation-expected-calibration-error-delta 用于 holdout 验证；默认都为 0，且带 1e-12 浮点容差，避免 no-op 的极小数值噪声被误判为 ECE 回退
当训练期候选虽然提升 Brier/logloss、但 ECE 回退时不再可选；当训练期通过的候选在 holdout 上 ECE 回退时，该 competition 自动 fallback 到 no-op，不把伤害校准的赛前特征权重放入候选 profile
新增 deterministic tests 覆盖：训练 ECE 回退候选被挡住；极小 ECE 浮点噪声可通过；所有候选 ECE 回退时跳过；holdout ECE 回退时 fallback 到 no-op；CLI 参数映射包含训练/验证 ECE guard
重新生成 expanded A-league ECE-guarded feature holdout 报告：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_market_feature_holdout_parameter_learning_ece_guard_v1.json；report_key=historical_prematch_feature_parameter_learning:94b22195f077af56；learned_competition_count=7；validation_count=504
ECE-guarded feature 结果：hit_rate_delta=+0.005952380952381042；brier_score_delta=-0.00043080713012932925；log_loss_delta=-0.0005125302118312858；expected_calibration_error_delta=-0.0031896046210417237
分联赛处理：ENG_CHAMPIONSHIP 与 PRT_PRIMEIRA_LIGA 因 holdout ECE 回退 fallback 到 no-op；ESP_SEGUNDA_DIVISION 与 FRA_LIGUE_2 选择 no-op/近 no-op；GER_2_BUNDESLIGA、ITA_SERIE_B、NED_EREDIVISIE 保留通过校准保护的 feature adjustment
使用 ECE-guarded feature 报告重跑 candidate12/window4 admission gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_admission_gate_ece_guard_v1.json；report_key=competition_admission_gate:afc9cc5485cd3bf5；decision=accepted；production_recommendation_allowed=true；training_pool_allowed=true；blockers=[]；warnings=[]
生成 production-ready profile proposal：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_profile_proposal_ece_guard_v1.json；report_key=competition_profile_proposal:cdd2826dcb49a81a；status=production_ready；proposal_count=2；accepted_profile_adjustments=ESP_SEGUNDA_DIVISION -> 2x1:multiple、ITA_SERIE_B -> 2x1:multiple
当前判断：expanded A-league 的 candidate12/window4 final-answer 证据、feature 校准保护、coverage audit 已共同通过 admission；但本阶段仍只生成 governed proposal，不直接修改 production profile config，下一步应做受控 profile promotion 与默认推荐路径回归验证
README 更新 ECE-guarded feature learning、accepted admission、production-ready proposal 报告路径与核心指标；该能力属于“calibration-protected feature learning / admission blocker removal / accuracy-first profile governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-181 当前落地能力：

```text
新增 competition_profile_promotion 模块与 CLI：nutmeg-recommendation-competition-profile-promote
promotion CLI 只接受 production_ready proposal，默认要求 production_recommendation_allowed=true 与 training_pool_allowed=true；若 proposal item 未允许生产、无 profile、或已有同联赛同 scenario 调整冲突，则直接 blocked；默认不覆盖已有冲突配置
新增 deterministic tests 覆盖：production-ready proposal 合并进 profile set；shadow-only proposal 被阻断；已有调整冲突被阻断；CLI 写出 promoted profile 与 promotion report；CLI 参数映射
执行受控 profile promotion：configs/recommendations/competition_recommendation_profiles.json 的 profile_version 更新为 v3_1_competition_profiles_football_data_co_uk_2026_05_15_ece_guard_expanded_a_leagues_v1；profile_count=6；新增 ESP_SEGUNDA_DIVISION -> 2x1:multiple、ITA_SERIE_B -> 2x1:multiple，min_historical_final_hit_sample_size=30
生成 promotion 报告：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_competition_profile_promotion_ece_guard_v1.json；report_key=competition_profile_promotion:5fd04151b08005c1；status=promoted；promoted_profile_count=2；blockers=[]；warnings=[]
默认推荐路径回归：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_post_profile_promotion_final_answer_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:4a47eab0e94a352d；passed=true；suite_status=improved；candidate_final_hit_sample_size=210；candidate_final_hit_rate=0.6904761904761905；candidate_roi=0.024854310344827577；candidate_profit_loss=17.298599999999993；worst_competition_id=ENG_CHAMPIONSHIP；worst_competition_candidate_roi=-0.13333333333333333；warnings=[]
post-promotion aggregate_deltas：final_hit_count_delta=4；final_hit_rate_delta=0.01904761904761909；roi_delta=0.009735977011494252；profit_loss_delta=6.413399999999999；brier_score_delta=-0.004450077981891648；log_loss_delta=-0.009874327982006381；mean_calibration_error_delta=-0.005500038018833919；final_answer_changed_count=39；candidate_solver_selected_scenario_count=984
post-promotion admission：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_post_profile_promotion_competition_admission_gate_v1.json；report_key=competition_admission_gate:f2df755c3c3f93b5；decision=accepted；production_recommendation_allowed=true；training_pool_allowed=true；blockers=[]；warnings=[]；feature_expected_calibration_error_delta=-0.0031896046210417237
当前判断：expanded A-league profile 已从 evidence -> proposal -> promotion -> default-path regression -> admission 完成闭环，且默认路径命中率与 ROI 都优于 promotion 前；下一步应继续围绕 ROI 稳定性、冷门捕捉率和更多联赛/赛制的受控 admission 推进
README 更新 promotion CLI、promotion 报告、默认路径 gate 与 post-promotion admission 路径；该能力属于“governed profile promotion / default recommendation regression / accuracy-first production admission”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-182 当前落地能力：

```text
按产品方向调整：冷门捕捉暂时从核心推荐优化主线降级为后台诊断，不再作为最终答案、全局规划或预算优化的正向加分项
final_answer_arbitrator 改为 core-first 权重：planner=0.20、hit_probability=0.18、roi=0.23、risk=0.10、data_quality=0.08、budget_efficiency=0.04、stake_discipline=0.13、fixture_depth=0.01、answer_type=0.03；upset_quality 改为 upset_quality_diagnostic，只保留在 payload/score_components 中用于诊断，不参与评分
global_planner 移除 upset_quality 正向加分，权重回到 total_score、hit_probability、roi、data_quality、risk、budget、fixture_depth；reason_codes 不再输出 upset_quality_considered
optimizer 的 fixture variant proxy 与 parlay_quality 移除 upset_component / calibrated_upset_exposure 正向加分，保留 calibration_risk、longshot_upset_risk、fragile_favorite_risk 作为风险压力项，避免继续追逐冷门捕捉实验
调整 deterministic tests：final answer 仍记录 upset_policy / upset_quality_diagnostic，但不再把 upset_protection_considered 放入 reason_codes；multiple optimizer 不再强制走“先加冷门保护再裁剪预算”的路径，改为验证 core-quality 选择在预算内稳定
core-first 默认路径回归：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_first_final_answer_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:4a47eab0e94a352d；passed=true；suite_status=improved；candidate_final_hit_sample_size=210；candidate_final_hit_rate=0.6952380952380952；candidate_roi=-0.0022417391304347836；candidate_profit_loss=-1.5468000000000006；worst_competition_id=ENG_CHAMPIONSHIP；worst_competition_candidate_roi=-0.156；warnings=[]
core-first aggregate_deltas：final_hit_count_delta=5；final_hit_rate_delta=0.023809523809523836；roi_delta=0.016747517067912325；profit_loss_delta=12.2394；brier_score_delta=-0.0055898863737147975；log_loss_delta=-0.012185821391025864；mean_calibration_error_delta=-0.006577068941725328；final_answer_changed_count=51；candidate_solver_selected_scenario_count=896
core-first admission：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_first_competition_admission_gate_v1.json；report_key=competition_admission_gate:be825211fc4fea4f；decision=accepted；production_recommendation_allowed=true；training_pool_allowed=true；blockers=[]；warnings=[]；feature_expected_calibration_error_delta=-0.0031896046210417237
当前判断：core-first 后命中率进一步提升，但 ROI 从 post-promotion 的正值回落到轻微负值；该结果符合“先准确”方向，但下一阶段应继续做 ROI 稳定性与价值约束，而不是恢复冷门捕捉加分
README 更新 core-first scoring、历史 gate 与 admission 报告路径；该能力属于“core recommendation quality / upset diagnostic-only / accuracy-first scoring”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-183 当前落地能力：

```text
继续沿 core recommendation quality 主线做 ROI 稳定性，不恢复冷门捕捉正向加分；upset_quality_diagnostic 仍只作为后台诊断 payload
final_answer_arbitrator 进行温和 ROI 再平衡：hit_probability 权重 0.18 -> 0.15，ROI 权重 0.23 -> 0.26；planner、risk、data_quality、budget_efficiency、stake_discipline、fixture_depth、answer_type 保持不变
硬性 negative ROI penalty 与更激进的 hit_probability=0.12 / ROI=0.29 全局权重方案均未通过同一 historical gate，因此不保留，避免为追 ROI 牺牲最终答案质量
core ROI rebalance 默认路径回归：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_roi_rebalanced_final_answer_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:4a47eab0e94a352d；passed=true；suite_status=improved；candidate_final_hit_sample_size=210；candidate_final_hit_rate=0.6952380952380952；candidate_roi=-0.0003745454545454577；candidate_profit_loss=-0.24720000000000208；worst_competition_id=ENG_CHAMPIONSHIP；worst_competition_candidate_roi=-0.156；warnings=[]
core ROI rebalance aggregate_deltas：final_hit_count_delta=5；final_hit_rate_delta=0.023809523809523836；roi_delta=0.012878844375963018；profit_loss_delta=9.136199999999999；brier_score_delta=-0.005955379096128838；log_loss_delta=-0.01291648401636647；mean_calibration_error_delta=-0.006849525292188352；final_answer_changed_count=53；candidate_solver_selected_scenario_count=896；upset_capture_rate_delta=0.0
core ROI rebalance admission：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_roi_rebalanced_competition_admission_gate_v1.json；report_key=competition_admission_gate:215cd8c26f83c1a9；decision=accepted；production_recommendation_allowed=true；training_pool_allowed=true；blockers=[]；warnings=[]；feature_expected_calibration_error_delta=-0.0031896046210417237
当前判断：温和 ROI 再平衡在不降低最终命中率的前提下把 ROI 从 core-first 的 -0.0022417391304347836 拉近到 -0.0003745454545454577，已接近打平但仍未转正；下一阶段应做分场景/分联赛 value guard 或 odds-band 质量约束，而不是继续使用单一全局权重硬拉 ROI
README 更新 core ROI rebalance、历史 gate 与 admission 报告路径；该能力属于“core recommendation quality / ROI stability / accuracy-first final arbitration”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-184 当前落地能力：

```text
继续按用户确认的方向推进：冷门捕捉仍暂时搁置，不恢复 upset 正向加分；本轮只做核心最终答案质量与 ROI 稳定性
historical_backtest 的 final_answer_quality_signal_penalty 增加 min_decimal_odds 参数，支持按赔率区间验证 value guard；historical_suite_gate CLI 同步支持 final-answer quality-signal 参数，并在 summary_json 中记录完整 guard 参数
final_answer_quality_signal_profile_grid 增加 min_decimal_odds_values，后续可做概率段/赔率段/edge 段的网格化搜索，而不是只靠 max odds 粗筛
CompetitionRecommendationProfile 新增 final_answer_value_guards；final_answer_arbitrator 在内部 profile 层按候选腿 competition_id、probability、decimal_odds、model_edge、score 匹配 guard，并以 competition_value_guard_penalty 扣减最终答案分；该字段只进入内部 arbitration payload，不作为用户可见策略说明
新增 deterministic tests：赔率下限能关闭 quality-signal penalty；suite gate CLI 参数映射包含 final-answer quality signal；profile grid CLI 支持 min-decimal-odds-values；最终答案仲裁器会应用 competition value guard penalty
先跑多组 Segunda odds-band 候选：泛化低概率长赔 guard 能提升 ROI 但会降低最终命中率，因此未作为默认生产方案；保留的候选只限制 ESP_SEGUNDA_DIVISION 中 probability < 0.50、decimal_odds 2.0-10.0、model_edge < -0.02 的腿
实验 gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_esp_segunda_low_long_value_guard_edge_neg_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:2be421454bc4f411；passed=true；candidate_final_hit_rate=0.6952380952380952；candidate_roi=0.04383464052287581；candidate_profit_loss=26.8268；ESP_SEGUNDA_DIVISION ROI=0.07470694444444427
生产默认路径 profile_version 更新为 v3_1_competition_profiles_football_data_co_uk_2026_05_15_esp_segunda_value_guard_v1；ESP_SEGUNDA_DIVISION profile 新增内部 value guard，source_report_key=historical_recommendation_suite_quality_gate:e161c76fdf5df5ed
生产默认路径 gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_production_esp_segunda_value_guard_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:e161c76fdf5df5ed；passed=true；suite_status=improved；candidate_final_hit_sample_size=210；candidate_final_hit_rate=0.6952380952380952；candidate_roi=0.04383464052287581；candidate_profit_loss=26.8268；worst_competition_id=ENG_CHAMPIONSHIP；worst_competition_candidate_roi=-0.156；warnings=[]
production value guard aggregate_deltas：final_hit_count_delta=5；final_hit_rate_delta=0.023809523809523836；roi_delta=0.03382065242763772；profit_loss_delta=20.097399999999997；brier_score_delta=-0.0064540401507109935；log_loss_delta=-0.013885645310465211；mean_calibration_error_delta=-0.0071508827443547696；final_answer_changed_count=55；candidate_solver_selected_scenario_count=896
当前判断：本轮是“分联赛/赔率段/edge 段 value guard”的首个默认生产晋级：在不降低 V3.1-183 最终命中率的前提下，把 realized ROI 从 -0.0003745454545454577 提升到 0.04383464052287581；下一步应继续用同一门禁标准处理 ENG_CHAMPIONSHIP、FRA_LIGUE_2、GER_2_BUNDESLIGA 等剩余负 ROI 联赛，而不是扩大冷门捕捉
README 更新 production Segunda value guard、历史 gate 与核心指标；该能力属于“core recommendation quality / competition-scoped value guard / accuracy-first ROI lift”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-185 当前落地能力：

```text
继续沿 V3.1-184 的分联赛 value guard 路线推进，不恢复冷门捕捉正向加分，不改数据源/VPS/前端，专注核心最终答案 ROI 稳定性
重新生成当前生产默认路径 quality-signal diagnostics：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_production_value_guard_quality_signal_diagnostics_v1.json；最终答案样本 210，final_answer_hit_rate=0.6952380952380952，ROI=0.04383464052287581
诊断定位：当前最弱联赛为 ENG_CHAMPIONSHIP，competition_model_edge_band:ENG_CHAMPIONSHIP:negative 的 selected_leg_count=30、ROI=-0.156；其中 odds medium_price 段 selected_leg_count=9、final_answer_hit_rate=0.3333333333333333、ROI=-0.38，是本轮主要 loss driver
测试多组 Championship guard：全量 negative-edge guard、high short-price guard、medium-short guard 过轻时不改变最终答案；过强的 medium-price guard 会伤害 ROI；deeper-edge 窄化后影响为 0，因此不晋级
保留的实验候选：ENG_CHAMPIONSHIP，probability [0.45,0.58)，decimal_odds [1.75,2.20]，model_edge < -0.02，penalty_strength=0.12；实验 gate 输出 configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_eng_championship_medium_price_value_guard_s012_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:f30b2c69064ccb79；candidate_final_hit_rate=0.6952380952380952；candidate_roi=0.049685760517799354；candidate_profit_loss=30.7058
生产默认 profile_version 更新为 v3_1_competition_profiles_football_data_co_uk_2026_05_15_eng_championship_value_guard_v1；新增 ENG_CHAMPIONSHIP internal final_answer_value_guard，同时保留 V3.1-184 的 ESP_SEGUNDA_DIVISION guard
生产默认路径 gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_production_eng_championship_value_guard_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:a2f100868dc7444e；passed=true；suite_status=improved；candidate_final_hit_sample_size=210；candidate_final_hit_rate=0.6952380952380952；candidate_roi=0.049685760517799354；candidate_profit_loss=30.7058；worst_competition_id=ENG_CHAMPIONSHIP；worst_competition_candidate_roi=-0.08304545454545446；warnings=[]
production Championship value guard aggregate_deltas：final_hit_count_delta=5；final_hit_rate_delta=0.023809523809523836；roi_delta=0.04920399413603297；profit_loss_delta=30.3676；brier_score_delta=-0.004585884223401199；log_loss_delta=-0.01002656064981422；mean_calibration_error_delta=-0.0042903006194975335；final_answer_changed_count=56；candidate_solver_selected_scenario_count=896
production admission：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_production_eng_championship_value_guard_competition_admission_gate_v1.json；report_key=competition_admission_gate:34fcd1b659385665；decision=accepted；production_recommendation_allowed=true；training_pool_allowed=true；blockers=[]；warnings=[]；feature_expected_calibration_error_delta=-0.0031896046210417237
当前判断：Championship 的 medium-price value guard 在不降低 V3.1-184/V3.1-183 最终命中率的前提下，把整体 ROI 从 0.04383464052287581 提升到 0.049685760517799354，并把 Championship ROI 从 -0.156 拉到 -0.08304545454545446；下一步应继续处理 FRA_LIGUE_2、GER_2_BUNDESLIGA 的窄 loss-driver，而不是扩大 Championship guard 或回到冷门捕捉
README 更新 production Championship value guard、历史 gate、admission 与核心指标；该能力属于“core recommendation quality / competition-scoped medium-price value guard / accuracy-first ROI lift”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-186 当前落地能力：

```text
继续沿 V3.1-185 的分联赛 value guard 路线评估 Ligue 2 / 2. Bundesliga loss-driver；本轮不恢复冷门捕捉正向加分，不改数据源/VPS/前端，不扩大 Championship guard，专注验证剩余负 ROI 联赛是否存在可晋级的窄质量约束
当前生产基线仍为 v3_1_competition_profiles_football_data_co_uk_2026_05_15_eng_championship_value_guard_v1；生产 gate 为 configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_production_eng_championship_value_guard_gate_v1.json；final_answer_hit_rate=0.6952380952380952；ROI=0.049685760517799354；candidate_profit_loss=30.7058
基于 production value guard diagnostics，Ligue 2 的主要 loss-driver 为 low probability 与 medium-price 段：competition_probability_band:FRA_LIGUE_2:low selected_leg_count=5、final_answer_hit_rate=0.2、ROI=-0.6060000000000001；competition_odds_band:FRA_LIGUE_2:medium_price selected_leg_count=11、final_answer_hit_rate=0.45454545454545453、ROI=-0.15454545454545449
2. Bundesliga 的主要 loss-driver 为 medium-price 与 low probability 段：competition_odds_band:GER_2_BUNDESLIGA:medium_price selected_leg_count=6、final_answer_hit_rate=0.3333333333333333、ROI=-0.365；competition_probability_band:GER_2_BUNDESLIGA:low selected_leg_count=4、final_answer_hit_rate=0.25、ROI=-0.5025
测试 Ligue 2 medium-price value guard strength=0.12：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ligue2_medium_price_value_guard_s012_gate_v1.json；最终答案与生产基线完全相同，ROI 无提升，因此不晋级
测试 Ligue 2 low-probability value guard strength=0.08：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ligue2_low_probability_value_guard_s008_gate_v1.json；最终答案与生产基线完全相同，ROI 无提升，因此不晋级
测试 Ligue 2 medium-price value guard strength=0.24 / 0.50：s024 降低整体 ROI 至 0.029184523809523806，s050 降低 final_answer_hit_rate 至 0.6904761904761905，均未通过 no-hit-regression / no-ROI-regression 标准
测试 Ligue 2 low-probability value guard strength=0.24：final_answer_hit_rate 提升至 0.7，但整体 ROI 降至 0.042357407407407406，属于 accuracy-only 改善但牺牲 ROI，不晋级为生产配置
测试 2. Bundesliga medium-price value guard strength=0.12：整体 ROI 降至 0.04311185897435897，2. Bundesliga ROI 从 -0.013333333333333404 降至 -0.06975757575757585，未通过门禁；strength=0.04 不改变最终答案，ROI 无提升
测试 2. Bundesliga low-probability value guard strength=0.08：最终答案与生产基线完全相同，ROI 无提升，因此不晋级
当前判断：Ligue 2 / 2. Bundesliga 的局部 penalty guard 暂时无法同时提升最终答案命中率和 ROI；本轮不修改 configs/recommendations/competition_recommendation_profiles.json，不推广新的 production guard，继续保留 V3.1-185 的 Championship + Segunda guard 作为生产基线
下一步应转向候选池/替代答案可用性、分联赛校准与候选生成诊断，判断这些联赛是否缺少高质量替代腿；不应继续简单加大 penalty strength 或回到冷门捕捉正向加分
README 更新 Ligue 2 / 2. Bundesliga value guard 消融结论与报告路径；该能力属于“core recommendation quality / value guard ablation / no-regression governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-187 当前落地能力：

```text
按 V3.1-186 结论进入候选替代能力审计，不继续加大 penalty，也不恢复冷门正向加分；本轮只回答 Ligue 2 / 2. Bundesliga 的 loss-driver 坏腿被替换时，候选池里是否有可用替代答案
扩展 marginal_contribution_diagnostics：新增 target_probability_min / target_probability_max / target_min_decimal_odds / target_max_decimal_odds / target_max_model_edge / missed_legs_only 过滤条件，使候选级替换模拟可专门聚焦某类 final-answer selected leg，而不是审计所有腿
新增 CLI 别名 nutmeg-recommendation-candidate-replacement-audit，指向同一 replacement simulation engine；该别名用于表达当前核心问题“候选替代能力”，不新增用户可见策略，不改变最终答案仲裁器、优化器或 production profile
新增 deterministic tests 覆盖：loss-driver selected-leg 过滤只保留目标坏腿；CLI 参数正确映射 target filter 与 missed_legs_only；既有 marginal replacement opportunity 测试继续通过
生成 FRA_LIGUE_2 / GER_2_BUNDESLIGA loss-driver replacement audit：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ger_loss_driver_candidate_replacement_audit_v1.json；report_key=historical_candidate_marginal_audit:980bf20d81542c6f
审计口径：focus competitions=FRA_LIGUE_2,GER_2_BUNDESLIGA；target probability < 0.55；decimal_odds 1.75-2.30；model_edge < -0.02；missed_legs_only=true；candidate12/window4；max_replacement_candidates_per_leg=8
报告结果：slice_count=60；final_answer_count=60；examined_selected_leg_count=60；targeted missed selected_leg_count=7；replacement_simulation_count=56；actual_replacement_opportunity_count=7；model_top_replacement_count=7；model_top_actual_improvement_count=2；model_top_actual_harm_count=0
分联赛结果：FRA_LIGUE_2 targeted missed legs=5，actual_replacement_opportunity_count=5，model_top_improvement_count=1，avg_model_top_delta=0.924，avg_actual_best_delta=5.908；GER_2_BUNDESLIGA targeted missed legs=2，actual_replacement_opportunity_count=2，model_top_improvement_count=1，avg_model_top_delta=2.02，avg_actual_best_delta=7.02
关键判断：候选池里确实存在 hindsight replacement opportunities，但当前模型 top replacement 只在 2/7 个目标坏腿上改善实际 profit/loss，且 average_model_top_hit_probability_delta=-0.02910240956504262；这说明问题不是“没有替代候选”，而是替代候选排序/校准仍不可靠
当前不推广自动替换策略、不修改 configs/recommendations/competition_recommendation_profiles.json、不改变 production gate；下一步应做 replacement scorer / candidate reranker 的特征诊断，优先处理模型 top replacement 与 hindsight actual-best replacement 之间的排序偏差
README 更新 candidate replacement audit alias、命令、报告路径与核心结论；该能力属于“core recommendation quality / candidate replacement diagnostics / no-regression governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-188 当前落地能力：

```text
按 V3.1-187 结论继续聚焦 replacement scorer / candidate reranker，不扩大候选池、不恢复冷门正向加分、不修改生产 profile；本轮目标是解释“候选池里有 hindsight actual-best 替代，但模型 top replacement 为什么没选中”
新增 replacement_reranker_diagnostics 模块：读取 HistoricalCandidateMarginalAuditReport，将每个 model_top_replacement 与 actual_best_replacement 对齐，输出 rank_gap、profit_loss_gap、actual_return_gap、probability/odds/model_edge/score/quality/hit_probability/risk gap，以及 bias_tags
新增 CLI：nutmeg-recommendation-replacement-reranker-diagnostics，支持 audit report 输入、输出 report、min_actual_best_profit_loss_delta、min_profit_loss_gap、max_report_items 与各类 gap threshold；该 CLI 只生成开发诊断报告，不参与用户推荐路径
新增 deterministic tests 覆盖：概率/赔率/edge/score/risk 排序偏差识别、小 gap 过滤、CLI options 与 loader；新测试与 ruff 通过
生成 FRA_LIGUE_2 / GER_2_BUNDESLIGA reranker diagnostics：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ger_replacement_reranker_diagnostics_v1.json；report_key=historical_replacement_reranker_diagnostics:249e538c1eb1a346
诊断口径：source_audit_report_key=historical_candidate_marginal_audit:980bf20d81542c6f；min_actual_best_profit_loss_delta=0；min_profit_loss_gap=0；max_report_items=50；source audit 仍是 probability < 0.55、odds 1.75-2.30、model_edge < -0.02 的 FRA/GER missed bad legs
报告结果：evaluated_item_count=7；rank_gap_item_count=7；average_rank_gap=5.142857142857143；average_profit_loss_gap=4.988571428571428；average_probability_gap=-0.15139854085935095；average_decimal_odds_gap=1.05；average_model_edge_gap=0.00999932810283454；average_score_gap=-0.0413033891942901；average_quality_score_gap=-0.0834404099920012；average_risk_score_gap=0.15139854085935098
偏差标签：actual_best_ranked_below_model_top=7；actual_best_lower_probability=7；actual_best_higher_odds=7；actual_best_higher_risk=7；actual_best_lower_candidate_score=6；actual_best_lower_replacement_quality=6；actual_best_better_model_edge=4
分联赛结果：FRA_LIGUE_2 item_count=5，average_rank_gap=4.4，average_profit_loss_gap=4.984；GER_2_BUNDESLIGA item_count=2，average_rank_gap=7.0，average_profit_loss_gap=5.0
关键判断：当前候选池并非完全缺少替代答案；主要缺陷是 replacement scorer/reranker 对高赔率、较低模型概率、较低安全分但更高赛后收益的候选排序不足。由于 actual-best 是 hindsight，本轮不把这些候选直接变成生产策略；下一步应做赛前可见的 reranker feature / weight experiment，用历史切片验证是否能在不降低最终命中率的前提下改善 bad-leg 替代排序
README 更新 reranker diagnostics 命令、报告路径、report_key 与核心结论；该能力属于“core recommendation quality / replacement reranker diagnostics / no-regression governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-189 当前落地能力：

```text
按 V3.1-188 结论继续做赛前可见 reranker feature / weight experiment；本轮不修改 production profile、不进入前端、不把 hindsight actual-best 直接作为策略，只用赛后结果评估离线排序实验
新增 replacement_reranker_weight_experiment 模块：读取 HistoricalCandidateMarginalAuditReport，对每个 replacement_candidates 候选按 profile 重新评分并选择 reranked replacement，再和 current model-top replacement 比较 actual hit、replacement leg hit、profit/loss delta、hit probability delta、ROI delta、risk delta 与 actual-best capture
显式定义 PREMATCH_RERANKER_FEATURES：replacement_probability、replacement_decimal_odds、replacement_model_edge、replacement_score、replacement_quality_score、simulated_hit_probability、simulated_roi、simulated_risk_score、replacement_rank
显式排除 LEAKAGE_EXCLUDED_FIELDS：replacement_leg_actual_hit、simulated_actual_hit、simulated_actual_return、simulated_profit_loss、actual_return_delta、profit_loss_delta、decision；这些字段只用于离线评估，不进入 reranker score
新增默认 profile：current_quality_baseline、quality_edge_blend_v1、edge_value_v1、odds_tempered_value_v1、probability_guarded_value_v1；best_profile_id 仲裁按准确性优先，先考虑 candidate/watchlist、无 model-top-relative harm、低 hit-probability regression，再看收益
新增 CLI：nutmeg-recommendation-replacement-reranker-weight-experiment，支持 audit report 输入、输出 report、profile ids、min_actual_best_profit_loss_delta、min_profit_loss_gap、min_evaluated_item_count、max_hit_probability_regression_rate、min_average_profit_loss_delta_vs_model_top、max_report_items
新增 deterministic tests 覆盖：只使用赛前可见字段的 edge/odds profile 可捕获 actual-best；probability guard 可阻止过低概率候选；CLI options、main 输出与未知 profile 错误处理；新测试与 ruff 通过
生成 FRA_LIGUE_2 / GER_2_BUNDESLIGA reranker weight experiment：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ger_replacement_reranker_weight_experiment_v1.json；report_key=historical_replacement_reranker_weight_experiment:a82c7177db014c0b
实验口径：source_audit_report_key=historical_candidate_marginal_audit:980bf20d81542c6f；eligible_item_count=7；profile_count=5；min_actual_best_profit_loss_delta=0；min_profit_loss_gap=0；min_evaluated_item_count=5；max_hit_probability_regression_rate=0；min_average_profit_loss_delta_vs_model_top=0
baseline=current_quality_baseline：selected_model_top_count=7；simulated_actual_hit_count=2；replacement_leg_actual_hit_count=2；average_profit_loss_delta=1.237142857142857；hit_probability_regression_count=0
accuracy-first watchlist=quality_edge_blend_v1：selected_model_top_count=6；selected_actual_best_count=0；improvement_count_vs_model_top=1；harm_count_vs_model_top=0；simulated_actual_hit_count=3；replacement_leg_actual_hit_count=3；hit_probability_regression_count=1；average_profit_loss_delta_vs_model_top=0.5599999999999999；average_hit_probability_delta_vs_model_top=-0.0017430841601672584；由于存在 hit-probability regression，不能晋级生产
edge_value_v1：improvement_count_vs_model_top=3；harm_count_vs_model_top=0；selected_actual_best_count=1；simulated_actual_hit_count=4；average_profit_loss_delta_vs_model_top=1.9828571428571427；但 hit_probability_regression_count=4，不能晋级
odds_tempered_value_v1：selected_actual_best_count=2；improvement_count_vs_model_top=4；simulated_actual_hit_count=4；average_profit_loss_delta_vs_model_top=2.6028571428571428；但 harm_count_vs_model_top=1 且 hit_probability_regression_count=7，是激进收益反例而非生产候选
probability_guarded_value_v1 与 quality_edge_blend_v1 在本样本结果一致：小幅改善但仍有 1 次 hit-probability regression，因此只保留 watchlist
关键判断：赛前可见 reranker 已能找到比当前 model-top 更好的坏腿替代方向，但一旦提升赔率/edge 权重，就容易牺牲 hit probability；在“准确！准确！再准确！”目标下，本轮不推广生产策略。下一阶段应把 weight experiment 扩展到更大历史切片和分联赛/分赔率段交叉验证，寻找真正 no-hit-regression 的稳定窄 profile，或设计 per-item hit-probability guard，而不是简单提高 odds/edge 权重
README 更新 reranker weight experiment 命令、报告路径、report_key 与核心结论；该能力属于“core recommendation quality / pre-match reranker weight experiment / no-leakage governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-190 当前落地能力：

```text
按 V3.1-189 结论继续做更大样本 reranker weight experiment，并加入 per-item hit-probability guard；本轮仍不修改 production profile，不让内部策略进入前端，不接实时 API 或 VPS，不做自动下注
扩展 HistoricalReplacementRerankerWeightExperimentOptions：新增 min_candidate_hit_probability_delta_vs_model_top；当该值为 0 时，每个 replacement candidate 必须满足 simulated_hit_probability >= current model-top replacement simulated_hit_probability，否则在 profile 排序前被过滤
报告模型新增 candidate_hit_probability_guard_filtered_count 与 profile summary 的 hit_probability_guard_filtered_count，用于量化 guard 对候选池的压缩程度
used_feature_names / item summary 会记录 min_candidate_hit_probability_delta_vs_model_top_guard；LEAKAGE_EXCLUDED_FIELDS 继续排除 actual hit、actual return、profit/loss delta 与 hindsight decision，避免赛后泄漏
CLI 新增 --min-candidate-hit-probability-delta-vs-model-top；新增 deterministic test 覆盖：edge/odds profile 原本会选择低概率 actual-best，但在 hit-probability guard=0 时必须回退到 model-top；CLI options 正确映射该参数
基于五季大样本 marginal contribution audit 生成 strict hit-probability guard report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_reranker_weight_experiment_hit_guard_v1.json；report_key=historical_replacement_reranker_weight_experiment:c0c3ad5e8e29696d
输入 audit：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json；source report_key=historical_candidate_marginal_audit:f7c3565ac8b0ec1e；覆盖 30 final answers、105 selected legs、15 missed legs、439 replacement simulations
实验口径：eligible_item_count=72；profile_count=5；min_actual_best_profit_loss_delta=0；min_profit_loss_gap=0；min_candidate_hit_probability_delta_vs_model_top=0；min_evaluated_item_count=30；max_hit_probability_regression_rate=0
候选压缩：candidate_hit_probability_guard_filtered_count=876；quality_edge_blend_v1 filtered=226；edge_value_v1 filtered=217；odds_tempered_value_v1 filtered=217；probability_guarded_value_v1 filtered=216
baseline=current_quality_baseline：evaluated_item_count=72；selected_model_top_count=72；simulated_actual_hit_count=49；replacement_leg_actual_hit_count=49；average_profit_loss_delta=-0.816263700463889；hit_probability_regression_count=0
所有非 baseline profile 在 strict guard 下都 selected_model_top_count=72、selected_actual_best_count=0、improvement_count_vs_model_top=0、harm_count_vs_model_top=0、hit_probability_regression_count=0、average_profit_loss_delta_vs_model_top=0，因此全部 rejected，best_profile_id=null
关键判断：严格 no-hit-probability-regression 规则下，当前候选池中的高收益替代几乎都被过滤，说明“直接调 odds/edge 权重”不是可推广路线；更核心的问题是候选生成/概率校准本身还没有产生足够多的“命中概率不降且收益更好”的替代腿
下一阶段应停止在同一 weight profile 上反复挤压，转向：1）分联赛/赔率段统计哪些区域存在非回撤替代候选；2）扩展候选生成特征或概率校准；3）设计 per-item guard 的 tolerance grid，例如 -0.005/-0.01，并用最终命中率门禁判断是否可接受，但默认仍以 strict guard 为生产安全边界
README 更新 strict hit-probability guard 命令、报告路径、report_key 与负向结论；该能力属于“core recommendation quality / replacement reranker strict guard / no-regression governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-191 当前落地能力：

```text
按 V3.1-190 结论实现 hit-probability tolerance grid，用系统化网格测试 0 / -0.005 / -0.01 / -0.02 per-item expected hit-probability delta；本轮仍只做离线证据，不修改 production profile，不进入前端，不接实时 API 或 VPS，不做自动下注
新增 replacement_reranker_tolerance_grid 模块：批量调用 replacement_reranker_weight_experiment，对每个 threshold/profile 组合生成 grid candidate，并与 current_quality_baseline 比较 simulated_actual_hit_count、replacement_leg_actual_hit_count、profit/loss delta、harm count、hit-probability regression count 与 guard filtered count
新增 CLI：nutmeg-recommendation-replacement-reranker-tolerance-grid，支持 audit report、output path、hit-probability-delta-thresholds、profile ids、min sample、actual-hit delta gate、replacement-leg-hit delta gate、max harm count 与每次 experiment 的 report item limit
tolerance grid 自动补入 current_quality_baseline，即使 CLI 只指定实验 profile，也能计算相对 baseline 的真实离线命中变化
新增 deterministic tests 覆盖：strict threshold=0 时低 hit-probability 替代被拒绝；threshold=-0.02 时同一 profile 只能进入 watchlist 而不能作为 production candidate；CLI options、main 输出、threshold CSV 解析与空阈值错误处理
生成五季大样本 tolerance grid report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_reranker_tolerance_grid_v1.json；report_key=historical_replacement_reranker_tolerance_grid:5fcb781576e92c3d
输入 audit：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json；source report_key=historical_candidate_marginal_audit:f7c3565ac8b0ec1e；eligible opportunities 仍为 72；threshold_count=4；profile_count=5；evaluated_candidate_count=20
整体结果：profile_candidate_count=0；watchlist_count=11；rejected_count=5；baseline_count=4；best_candidate_key=null；没有任何组合满足 production candidate 条件
strict threshold=0：所有非 baseline profile selected_model_top_count=72，average_profit_loss_delta_vs_model_top=0，因此全部 rejected；这与 V3.1-190 结论一致
threshold=-0.005：quality_edge_blend_v1、probability_guarded_value_v1、odds_tempered_value_v1、edge_value_v1 均为 watchlist；selected_model_top_count=65；improvement_count_vs_model_top=7；harm_count_vs_model_top=0；simulated_actual_hit_delta_vs_baseline=0；hit_probability_regression_count=7；average_profit_loss_delta_vs_model_top=0.002672753899999991；average_hit_probability_delta_vs_model_top=-0.00022253271118034669
threshold=-0.01：四个实验 profile 均为 watchlist；selected_model_top_count=65；selected_actual_best_count=2；improvement_count_vs_model_top=7；harm_count_vs_model_top=0；simulated_actual_hit_delta_vs_baseline=0；average_profit_loss_delta_vs_model_top=0.00329775389999999；average_hit_probability_delta_vs_model_top=-0.0003215070026451374
threshold=-0.02：quality_edge_blend_v1、probability_guarded_value_v1、odds_tempered_value_v1 仍与 -0.01 结果一致，属于 watchlist；edge_value_v1 则 simulated_actual_hit_delta_vs_baseline=-5、harm_count_vs_model_top=5、average_profit_loss_delta_vs_model_top=-0.25805643409999995，因此明确 rejected
关键判断：极小 tolerance 能找到“实际命中不退步、harm=0、收益略正”的 watchlist，但收益幅度过小且依赖 expected hit-probability 负容忍；这不足以进入生产。放宽到 -0.02 已出现明显坏例，说明继续放大 tolerance 会偏离准确性目标
下一阶段应停止继续调同一组 reranker 权重，转向候选生成/概率校准诊断：找出为什么高收益替代腿在模型 hit probability 上普遍低于 model-top，并按联赛/赔率段定位可校准区域
README 更新 tolerance grid 命令、报告路径、report_key 与 watchlist/拒绝结论；该能力属于“core recommendation quality / replacement reranker tolerance grid / no-regression governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-192 当前落地能力：

```text
按 V3.1-191 结论停止继续调同一组 reranker 权重，转向候选生成/概率校准诊断；本轮目标是定位 actual-best replacement 为什么在模型 hit probability 上低于 model-top，以及这些机会集中在哪些联赛/赔率段/概率段
新增 replacement_calibration_segments 模块：读取 HistoricalCandidateMarginalAuditReport，只分析每条 selected leg 的 actual_best_replacement，避免同一候选池被多候选重复放大；actual_best 只作为离线诊断，不进入生产排序
新增 observation 模型：记录 competition、slice、selected leg、actual_best replacement、model-top replacement、profit_loss_delta_vs_model_top、hit_probability_delta_vs_model_top、probability/odds/model_edge/score/quality/risk delta，以及 replacement_probability_band、replacement_odds_band、replacement_model_edge_band、hit_probability_delta_band、replacement_rank_band
新增 group 模型：按 competition、replacement_probability_band、replacement_odds_band、replacement_model_edge_band、hit_probability_delta_band、replacement_rank_band、competition_odds_band、competition_hit_probability_delta_band、profile 聚合，输出 observation_count、actual-hit delta、replacement-leg-hit delta、平均 profit/loss delta、平均 hit-probability delta、平均 odds/probability/model-edge delta 与 decision
新增 CLI：nutmeg-recommendation-replacement-calibration-segments，支持 audit report、output path、min actual-best delta、min model-top-relative delta、min group sample、average profit gate、average hit-probability delta gate、actual-hit delta gate、replacement-leg-hit delta gate、profile group 开关与报告数量限制
新增 deterministic tests 覆盖：同一联赛/赔率段 actual-best 替代在模型 probability 更低但实际命中与收益更好时会被标记为 calibration_candidate；CLI options、main 输出与 profile group 开关正常
生成五季大样本 replacement calibration segment report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_calibration_segments_v1.json；report_key=historical_replacement_calibration_segments:e069fa77943911fa
输入 audit：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json；source report_key=historical_candidate_marginal_audit:f7c3565ac8b0ec1e；observation_count=72；group_count=49；calibration_candidate_count=38；watchlist_count=11；rejected_count=0
核心发现：actual-best replacement 机会不是主要来自长赔率冷门。replacement_odds_band:short 覆盖 71/72 observations，average_replacement_probability=0.8050430455446482，average_replacement_decimal_odds=1.1947887323943662，simulated_actual_hit_delta_count_vs_model_top=23，average_profit_loss_delta_vs_model_top=1.2149104931999999，average_hit_probability_delta_vs_model_top=-0.01299728611241547
按 hit-probability delta band：medium_deficit observation_count=46，simulated_actual_hit_delta=17，average_profit_loss_delta_vs_model_top=1.3677951592869564，average_hit_probability_delta=-0.014015059806052454；small_deficit observation_count=22，simulated_actual_hit_delta=6，average_profit_loss_delta_vs_model_top=1.0426485313636364，average_hit_probability_delta=-0.008234643393889142；large_deficit 只有 4 样本，暂不作为稳定方向
按联赛：ESP_LA_LIGA observation_count=11，actual-hit delta=6，avg profit/loss delta=2.4016620829090907，avg hit-probability delta=-0.010092227200217711；EPL observation_count=20，delta=5，avg profit/loss delta=0.97899845026，avg hit-probability delta=-0.011521344278739543；FRA_LIGUE_1 observation_count=16，delta=4，avg profit/loss delta=0.9472640687499997，avg hit-probability delta=-0.012034846284897177；ITA_SERIE_A、GER_BUNDESLIGA、JPN_J1 也为正 actual-hit delta，但 JPN_J1 hit-probability deficit 更大且样本少
局部 profile：ESP_LA_LIGA / short / medium_deficit 为强诊断点，observation_count=5，actual-hit delta=5，avg profit/loss delta=4.445060630399999，avg hit-probability delta=-0.011113203282229334；EPL / short / small_deficit observation_count=10，actual-hit delta=5，avg profit/loss delta=1.8438042810000002，avg hit-probability delta=-0.007750529714980398
关键判断：当前替代排序问题不是“缺少长赔率冷门”，而是高概率短赔率候选之间存在微校准/排序误差；actual-best replacement 通常只比 model-top 低约 0.8%-1.4% expected hit probability，但实际命中/收益更好
下一阶段应做 shadow-only 的 league + short-odds + small/medium-deficit calibration/rerank experiment：只在高概率短赔率候选、hit-probability deficit 在小范围内时微调排序，并用 final-answer gate 严格验证；不应放宽长赔率 tolerance 或恢复冷门正向加分
README 更新 replacement calibration segment 命令、报告路径、report_key 与核心结论；该能力属于“core recommendation quality / replacement calibration segments / probability calibration diagnostics”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-193 当前落地能力：

```text
按 V3.1-192 结论进入 shadow-only 的 league + short-odds + small/medium-deficit rerank experiment；本轮只验证短赔率高概率候选之间的微校准假设，不修改 production profile、不进入前端、不接实时 API/VPS、不恢复冷门捕捉正向加分
新增 replacement_short_odds_shadow_rerank 模块：读取 HistoricalCandidateMarginalAuditReport，聚焦 EPL、ESP_LA_LIGA、FRA_LIGUE_1、GER_BUNDESLIGA、ITA_SERIE_A 中 actual-best 相对 model-top 有离线改善的 replacement opportunities
显式定义 PREMATCH_SHORT_ODDS_SHADOW_FEATURES：competition_id、replacement_probability、replacement_decimal_odds、replacement_model_edge、replacement_score、replacement_quality_score、simulated_hit_probability、simulated_roi、simulated_risk_score、replacement_rank
显式定义 OFFLINE_SHORT_ODDS_SHADOW_EVALUATION_FIELDS：replacement_leg_actual_hit、simulated_actual_hit、simulated_actual_return、simulated_profit_loss、actual_return_delta、profit_loss_delta、decision、actual_best_replacement；这些字段只用于离线评估，不进入 shadow rerank 选择
新增 shadow profile：current_model_top、max_short_odds_within_deficit_v1、max_model_edge_within_deficit_v1、nearest_probability_within_deficit_v1；所有非 baseline profile 只在 replacement_probability >= 0.55、decimal_odds < 1.75、hit_probability_delta_vs_model_top ∈ [-0.015, 0]、decimal_odds_delta_vs_model_top >= 0 的 corridor 内选择候选
新增 CLI：nutmeg-recommendation-replacement-short-odds-shadow-rerank，支持 audit report、output path、profile ids、focus competitions、短赔率/概率/deficit guard、sample gate、actual-hit delta gate、harm gate 与报告数量限制
新增 deterministic tests 覆盖：shadow rerank 只使用赛前可见字段；competition / deficit guard 会阻止不合格候选；CLI options、main 输出与未知 profile 错误处理；新增测试和局部 ruff 通过
生成五季大样本 short-odds shadow rerank report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_shadow_rerank_v1.json；report_key=historical_short_odds_shadow_rerank:a6fe1f607f91c830
输入 audit：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_marginal_contribution_audit.json；source report_key=historical_candidate_marginal_audit:f7c3565ac8b0ec1e；eligible_item_count=66；profile_count=4；production_recommendation_changed=false；shadow_candidate_count=0；shadow_watchlist_count=3；rejected_count=0
baseline=current_model_top：evaluated_item_count=66；changed_count_vs_model_top=0；simulated_actual_hit_delta=0；average_profit_loss_delta_vs_model_top=0
max_short_odds_within_deficit_v1：status=shadow_watchlist；changed_count_vs_model_top=64；selected_actual_best_count=41；simulated_actual_hit_delta_count_vs_model_top=16；replacement_leg_hit_delta_count_vs_model_top=16；improvement_count_vs_model_top=59；harm_count_vs_model_top=5；average_profit_loss_delta_vs_model_top=0.8762040286242423；average_hit_probability_delta_vs_model_top=-0.010577590309480538
max_short_odds 分联赛：EPL hit delta +5 / harm 0 / avg profit +0.9652；FRA_LIGUE_1 hit delta +4 / harm 0 / avg profit +0.9473；ITA_SERIE_A hit delta +3 / harm 0 / avg profit +0.9146；GER_BUNDESLIGA hit delta +3 / harm 0 / avg profit +0.8015；ESP_LA_LIGA hit delta +1 但 harm 5，说明西甲需要单独 guard，不能直接使用统一短赔率 corridor
max_model_edge_within_deficit_v1：status=shadow_watchlist；hit delta +9；harm 7；avg profit +0.4512；nearest_probability_within_deficit_v1：status=shadow_watchlist；hit delta +4；harm 12；avg profit +0.2487；二者均弱于 max_short_odds
关键判断：短赔率高概率微校准方向有实质性历史信号，尤其 EPL/FRA_LIGUE_1/ITA_SERIE_A/GER_BUNDESLIGA；但全局 shadow profile 仍有 harm，且依赖 expected hit-probability 小幅回撤，因此不能晋级生产。下一阶段应把该实验拆成 per-competition guard / holdout gate，先尝试只在 no-harm 联赛做最终答案门禁验证，再决定是否进入 production profile
README 更新 short-odds shadow rerank 命令、报告路径、report_key 与核心结论；该能力属于“core recommendation quality / shadow-only short-odds micro-calibration / no-production-change evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-194 当前落地能力：

```text
按 V3.1-193 结论把 short-odds shadow 信号拆成 per-competition gate readiness；本轮仍不修改 production profile、不进入前端、不接实时 API/VPS、不做自动下注，只回答哪些联赛可以进入下一步 final-answer gate，哪些必须隔离
新增 replacement_short_odds_competition_gate 模块：读取 HistoricalShortOddsShadowRerankReport，按 profile_id + competition_id 聚合 gate candidate，输出 ready / watchlist / isolated decisions
新增模型：HistoricalShortOddsCompetitionGateOptions、HistoricalShortOddsCompetitionGateCandidate、HistoricalShortOddsCompetitionGateSet、HistoricalShortOddsCompetitionGateReport；所有模型显式标记 production_recommendation_changed=false
新增 CLI：nutmeg-recommendation-replacement-short-odds-competition-gate，支持 shadow report、output path、profile ids、sample gate、changed count、actual-hit delta、replacement-leg-hit delta、平均 profit/loss、平均 hit-probability deficit、max harm 与报告数量限制
新增 deterministic tests 覆盖：EPL 这类 no-harm 联赛被标记为 final_answer_gate_ready；ESP_LA_LIGA 这类有 harm 的联赛被 isolated_rejected；正向但样本不足的联赛进入 holdout_watchlist；CLI options、loader 与 main 输出正常
生成五季 per-competition gate readiness report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_competition_gate_v1.json；report_key=historical_short_odds_competition_gate:3397bc2ff3258934
输入 shadow report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_shadow_rerank_v1.json；source_shadow_report_key=historical_short_odds_shadow_rerank:a6fe1f607f91c830；profile=max_short_odds_within_deficit_v1；candidate_count=5；final_answer_gate_ready_count=4；isolated_rejected_count=1
ready_competition_ids：EPL、FRA_LIGUE_1、GER_BUNDESLIGA、ITA_SERIE_A；combined evaluated_item_count=55；changed_count=53；simulated_actual_hit_delta_count_vs_model_top=15；replacement_leg_hit_delta_count_vs_model_top=15；harm_count=0；average_profit_loss_delta_vs_model_top=0.9219471921672727；average_hit_probability_delta_vs_model_top=-0.010448446358735076
isolated_competition_ids：ESP_LA_LIGA；原因 harm_count_vs_model_top_above_threshold；西甲 evaluated_item_count=11、hit delta +1、avg profit/loss +0.6474882109090909，但 harm_count=5，因此不能与其他联赛一起进入下一步 gate
关键判断：short-odds 微校准不是全局可用，但在 EPL / FRA_LIGUE_1 / GER_BUNDESLIGA / ITA_SERIE_A 上具备 no-harm readiness；下一阶段应只对这四个 ready 联赛构建 final-answer gate shadow 候选，西甲继续隔离并单独查找更窄 guard
README 更新 per-competition gate 命令、报告路径、report_key 与核心结论；该能力属于“core recommendation quality / per-competition shadow gate readiness / no-production-change evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-195 当前落地能力：

```text
按 V3.1-194 结论进入 ready 联赛的 final-answer shadow gate；本轮仍不修改 production profile、不进入前端、不接实时 API/VPS、不做自动下注，只验证 EPL / FRA_LIGUE_1 / GER_BUNDESLIGA / ITA_SERIE_A 的 short-odds 微校准在最终答案层是否仍然无 harm
新增 replacement_short_odds_final_answer_gate 模块：读取 HistoricalCandidateMarginalAuditReport 与 HistoricalShortOddsCompetitionGateReport，按 ready_competition_ids 重新生成完整 short-odds shadow items，避免依赖上一轮 shadow report 的 max_report_items 截断明细
新增模型：HistoricalShortOddsFinalAnswerGateOptions、HistoricalShortOddsFinalAnswerGateItem、HistoricalShortOddsFinalAnswerGateReport；报告显式记录 source_audit_report_key、source_competition_gate_report_key、generated_shadow_report_key、ready/isolated competitions 与 production_recommendation_changed=false
final-answer gate 规则：每个 final_answer_key 最多替换 1 条腿；默认 selection_rule=highest_candidate_hit_probability，在候选替换中优先保留最终答案预期命中概率；La Liga 继续由 competition gate 隔离，不进入本轮 final-answer gate
新增 CLI：nutmeg-recommendation-replacement-short-odds-final-answer-gate，支持 audit report、competition gate report、profile、ready competitions override、selection rule、final-answer hit delta gate、profit/loss gate、平均 hit-probability tolerance、harm gate 与 short-odds guard 参数
新增 deterministic tests 覆盖：同一 final answer 多个候选时只选择 1 条替换腿；隔离联赛不会进入 final-answer gate；profit/loss harm 会被拒绝；CLI options、competition gate loader 与 main 输出正常
生成五季 ready 联赛 final-answer shadow gate report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_final_answer_gate_v1.json；report_key=historical_short_odds_final_answer_gate:03a2e45b6e358651
输入 audit：historical_candidate_marginal_audit:f7c3565ac8b0ec1e；输入 competition gate：historical_short_odds_competition_gate:3397bc2ff3258934；内部重新生成 shadow report：historical_short_odds_shadow_rerank:661bc6f8fcadc431
结果：decision=final_answer_shadow_candidate；changed_final_answer_count=16；original_final_answer_hit_count=14；shadow_final_answer_hit_count=16；final_answer_hit_delta_count_vs_original=+2；original_profit_loss=10.341830493600003；shadow_profit_loss=16.752334477600005；profit_loss_delta_vs_original=+6.410503984；improvement_count_vs_original=16；harm_count_vs_original=0
风险：expected_hit_probability_regression_count_vs_original=16；average_hit_probability_delta_vs_original=-0.01697510863389533；本轮通过显式 min_average_hit_probability_delta_vs_original=-0.02 容忍门槛，但仍不能直接生产晋级
关键判断：ready 四联赛的 short-odds 微校准已经在最终答案层通过 no-harm shadow gate，并实际提升历史命中；下一阶段必须接入更严格的 holdout / suite gate，验证该候选在完整历史 suite 上是否仍无最终命中回撤和 ROI 回撤，然后才允许考虑 production profile proposal。西甲继续隔离
README 更新 final-answer shadow gate 命令、报告路径、report_key 与核心结论；该能力属于“core recommendation quality / final-answer shadow gate / no-production-change evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-196 当前落地能力：

```text
按 V3.1-195 结论实现 short-odds final-answer shadow suite gate；本轮仍不修改 production profile、不进入前端、不接实时 API/VPS、不做自动下注，只把上一轮 16 个 changed final answers 合并回完整 30-answer marginal audit suite 做 no-regression 门禁
新增 replacement_short_odds_suite_gate 模块：读取 HistoricalCandidateMarginalAuditReport 与 HistoricalShortOddsFinalAnswerGateReport，先从 audit report 去重得到完整 baseline final answers，再用 final-answer gate changed items 覆盖候选结果；未变化的 final answers 保持 baseline
新增模型：HistoricalShortOddsSuiteGateOptions、HistoricalShortOddsSuiteGateCheck、HistoricalShortOddsSuiteFinalAnswer、HistoricalShortOddsSuiteGateReport；报告显式输出 baseline/candidate final-hit、hit-rate、profit/loss、ROI、total stake、harm count、average hit-probability delta 与 production_recommendation_changed=false
新增 CLI：nutmeg-recommendation-replacement-short-odds-suite-gate，支持 audit report、final-answer gate report、final-answer count gate、changed count gate、hit-rate delta gate、ROI delta gate、profit/loss delta gate、harm gate、平均 hit-probability tolerance、source final-answer gate decision 检查与 no-fail-process
新增 deterministic tests 覆盖：changed final answer 与 unchanged baseline answer 会合并成完整 suite；命中率、profit/loss、ROI delta 正确计算；source final-answer gate 被 rejected 或 candidate harm 时 suite gate 失败；CLI options、loader 与 main 输出正常
生成五季 full-suite shadow gate report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_suite_gate_v1.json；report_key=historical_short_odds_suite_gate:93a0dc3ef86ec7da
输入 audit：historical_candidate_marginal_audit:f7c3565ac8b0ec1e；输入 final-answer gate：historical_short_odds_final_answer_gate:03a2e45b6e358651；final_answer_count=30；changed_final_answer_count=16；total_stake=60.0
suite gate 结果：passed=true；baseline_final_answer_hit_count=20；candidate_final_answer_hit_count=22；final_answer_hit_delta_count=+2；baseline_final_answer_hit_rate=0.6666666666666666；candidate_final_answer_hit_rate=0.7333333333333333；final_answer_hit_rate_delta=+0.06666666666666665
收益结果：baseline_profit_loss=3.0106614248000034；candidate_profit_loss=9.421165408800004；profit_loss_delta=+6.410503984；baseline_roi=0.05017769041333339；candidate_roi=0.15701942348000006；roi_delta=+0.10684173306666667；harm_count_vs_original=0
风险结果：average_hit_probability_delta_vs_original=-0.01697510863389533，刚好处于本轮显式 tolerance gate -0.02 内；所有 gate checks 通过，但仍属于 shadow evidence，不是 production promotion
关键判断：ready 四联赛 short-odds 微校准已在完整 marginal audit suite 上通过 no-hit-regression / no-ROI-regression / no-harm gate；下一阶段应生成 governed production proposal artifact，并在 proposal 中继续保留西甲隔离、平均 hit-probability tolerance 和回滚条件，不能直接手改 production profile
README 更新 suite gate 命令、报告路径、report_key 与核心结论；该能力属于“core recommendation quality / shadow suite gate / production proposal evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-197 当前落地能力：

```text
按 V3.1-196 结论生成 governed production proposal artifact；本轮仍不修改 production profile、不进入前端、不接实时 API/VPS、不做自动下注，只把已通过的 short-odds shadow gate 证据转成可审计、可回滚、可单独晋级的生产准入提案
新增 replacement_short_odds_production_proposal 模块：读取 HistoricalShortOddsSuiteGateReport 与 HistoricalShortOddsFinalAnswerGateReport，校验 source report key 链接、suite gate passed、final-answer gate decision、final-answer count、changed count、hit-rate delta、ROI delta、profit/loss delta、harm count、平均 hit-probability tolerance、ready competition count、isolated competition 排除以及 source production unchanged
新增模型：HistoricalShortOddsProductionProposalOptions、HistoricalShortOddsProductionProposalCheck、HistoricalShortOddsProductionRuleProposal、HistoricalShortOddsProductionProposalReport；报告显式输出 production_recommendation_allowed、shadow_allowed、ready/isolated competitions、constraints_json、source_report_keys、evidence_json、rollback_conditions 与 production_recommendation_changed=false
新增 CLI：nutmeg-recommendation-replacement-short-odds-production-proposal，支持 suite gate report、final-answer gate report、proposal id、profile version、最终答案数量门槛、changed count、hit-rate delta、ROI delta、profit/loss delta、harm gate、平均 hit-probability tolerance、source production unchanged、isolated competition overlap 与 no-fail-process
新增 deterministic tests 覆盖：全部 gate 通过时 proposal 为 production_proposal_ready；isolated competition overlap 会阻断 production proposal 并降为 shadow_only；source production changed 会阻断 proposal；CLI options、loader 与 main 输出正常
生成五季 production proposal report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_production_proposal_v1.json；report_key=historical_short_odds_production_proposal:e516991cb2166604
输入 suite gate：historical_short_odds_suite_gate:93a0dc3ef86ec7da；输入 final-answer gate：historical_short_odds_final_answer_gate:03a2e45b6e358651；输入 competition gate：historical_short_odds_competition_gate:3397bc2ff3258934；输入 audit：historical_candidate_marginal_audit:f7c3565ac8b0ec1e；内部 shadow：historical_short_odds_shadow_rerank:661bc6f8fcadc431
proposal 结果：status=production_proposal_ready；production_recommendation_allowed=true；proposal_count=1；allowed_competition_ids=EPL,FRA_LIGUE_1,GER_BUNDESLIGA,ITA_SERIE_A；excluded_competition_ids=ESP_LA_LIGA；production_recommendation_changed=false
proposal 约束：profile_id=max_short_odds_within_deficit_v1；selection_rule=highest_candidate_hit_probability；max_replacements_per_final_answer=1；min_replacement_probability=0.55；max_replacement_decimal_odds=1.75；min_candidate_hit_probability_delta_vs_model_top=-0.015；max_candidate_hit_probability_delta_vs_model_top=0；min_decimal_odds_delta_vs_model_top=0；min_average_hit_probability_delta_vs_original=-0.02；max_harm_count_vs_original=0
回滚条件：生产周期若出现 harm_count_vs_original>0、final-answer hit-rate 回撤、ROI 回撤、profit/loss 回撤、平均 hit-probability delta 低于 -0.02、隔离联赛进入 allowed set、source report key 缺失或错配，则禁用该 proposal
关键判断：short-odds proposal 已具备生产准入提案资格，但仍未改变运行时默认推荐；下一阶段应做独立 promotion/admission smoke，把 proposal 应用到临时 profile 副本并跑默认推荐回放，确认没有配置冲突、旧路径泄漏或前端策略暴露，然后才考虑真正晋级
README 更新 production proposal 命令、报告路径、report_key、允许/排除联赛、约束与回滚条件；该能力属于“core recommendation quality / governed production proposal / no-runtime-change evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-198 当前落地能力：

```text
按 V3.1-197 结论实现 short-odds production proposal 的 promotion/admission smoke；本轮仍不修改 production profile、不进入前端、不接实时 API/VPS、不做自动下注，只验证 proposal 能否作为临时配置候选被审计，以及是否会冲突、泄漏或误写默认路径
新增 replacement_short_odds_promotion_smoke 模块：读取当前 CompetitionRecommendationProfileSet 与 HistoricalShortOddsProductionProposalReport，构造 temporary_profile_set_json，并检查 proposal status、production allowed、rule count、allowed competition count、allowed/excluded disjoint、runtime profile not written、proposal no production change、当前 profile 未含 short_odds_replacement_rules、public response unchanged、user-facing strategy text absent
规则级 smoke 检查：proposed_production_enabled、max_replacements_per_final_answer、min_replacement_probability、max_replacement_decimal_odds、average hit-probability tolerance、harm_count evidence、source report keys present、source report keys match proposal summary、required rollback conditions present
新增模型：HistoricalShortOddsPromotionSmokeOptions、HistoricalShortOddsPromotionSmokeCheck、HistoricalShortOddsPromotionSmokeReport；报告显式记录 current/promoted profile version、current/temporary profile count、allowed/excluded competitions、temporary_profile_set_json、public_contract_json、runtime_profile_written=false、public_response_changed=false、production_recommendation_changed=false
新增 CLI：nutmeg-recommendation-replacement-short-odds-promotion-smoke，支持 current profile path、production proposal report、output path、promoted profile version、allowed competition count、replacement count/probability/odds guard、hit-probability tolerance、harm gate、runtime/public/existing-rule override 与 no-fail-process
新增 deterministic tests 覆盖：全部检查通过时 smoke passed 且不写 runtime profile；allowed/excluded overlap 会失败；当前 profile 已存在 short_odds_replacement_rules 会失败；CLI options、proposal loader 与 main 输出正常
生成五季 promotion smoke report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_promotion_smoke_v1.json；report_key=historical_short_odds_promotion_smoke:d9bbc89fe4e355d2
输入 proposal：historical_short_odds_production_proposal:e516991cb2166604；当前 profile_version=v3_1_competition_profiles_football_data_co_uk_2026_05_15_eng_championship_value_guard_v1；current_profile_count=7；temporary_profile_count=7；proposed_rule_count=1
smoke 结果：passed=true；allowed_competition_ids=EPL,FRA_LIGUE_1,GER_BUNDESLIGA,ITA_SERIE_A；excluded_competition_ids=ESP_LA_LIGA；runtime_profile_written=false；public_response_changed=false；production_recommendation_changed=false；public_contract_json 明确 ordinary_user_path_changed=false、frontend_changed=false、user_facing_strategy_text=false
关键判断：proposal 已通过临时 promotion/admission smoke，但当前 runtime profile schema 还没有正式承载 short_odds_replacement_rules；下一阶段应实现受 feature flag/配置门控保护的 runtime rule loader 与 shadow replay，而不是直接把临时 payload 复制进默认配置
README 更新 promotion smoke 命令、报告路径、report_key、检查项与“不写默认 profile”的边界；该能力属于“core recommendation quality / promotion smoke / no-runtime-write evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-199 当前落地能力：

```text
按 V3.1-198 结论实现受 feature flag 保护的 short-odds runtime rule loader + shadow replay；本轮仍不修改 production profile、不进入前端、不接实时 API/VPS、不做自动下注，只验证临时 short_odds_replacement_rules 能否被运行时风格的规则加载器读取并影子回放
新增 replacement_short_odds_runtime_shadow 模块：支持从 promotion smoke report 的 temporary_profile_set_json、production proposal 的 proposal_profile_set_json 或直接 profile payload 中提取 short_odds_replacement_rules；默认 enable_shadow_replay=false，未显式开启时只报告 disabled，不应用规则
新增模型：ShortOddsRuntimeReplacementRule、ShortOddsRuntimeRuleSet、HistoricalShortOddsRuntimeShadowReplayOptions、HistoricalShortOddsRuntimeShadowReplayCheck、HistoricalShortOddsRuntimeShadowReplayFinalAnswer、HistoricalShortOddsRuntimeShadowReplayReport
新增 CLI：nutmeg-recommendation-replacement-short-odds-runtime-shadow-replay，支持 audit report、rule profile、output path、enable-shadow-replay、rule ids、final-answer count、changed count、hit-rate delta、ROI delta、profit/loss delta、harm gate、平均 hit-probability tolerance、production-change override、max report items 与 no-fail-process
新增 deterministic tests 覆盖：默认未开启 feature flag 时 status=disabled 且不改变 public/production；开启 shadow replay 时会加载规则、排除 isolated league、合并 unchanged baseline 并计算命中/ROI/profit/harm；disabled rule 会得到 no_rules；CLI options、loader 与 main 输出正常
生成五季 runtime shadow replay report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_v1.json；report_key=historical_short_odds_runtime_shadow_replay:bc73fc902f95cad3
输入 audit：historical_candidate_marginal_audit:f7c3565ac8b0ec1e；输入 rule profile：historical_short_odds_promotion_smoke:d9bbc89fe4e355d2 的 temporary_profile_set_json；rule_id=short_odds_final_answer_replacement_v1；source_rule_profile_version=v3_1_short_odds_replacement_promotion_smoke_v1
runtime shadow replay 结果：status=shadow_replay_failed；passed=false；final_answer_count=30；changed_final_answer_count=19；baseline_final_answer_hit_count=20；shadow_final_answer_hit_count=19；final_answer_hit_delta_count=-1；final_answer_hit_rate_delta=-0.033333333333333326
收益结果：baseline_roi=0.05017769041333339；shadow_roi=0.016496010146666722；roi_delta=-0.033681680266666666；profit_loss_delta=-2.020900816；harm_count_vs_original=1；average_hit_probability_delta_vs_original=-0.016661662260608206
失败 checks：final_answer_hit_rate_delta、roi_delta、profit_loss_delta、harm_count_vs_original；production_recommendation_changed=false；public_response_changed=false
关键 harm 样本：FRA_LIGUE_1 2024-2025，final_answer_key=fdcuk_fra_ligue_1_2024_2025_f1:4x1:single；原 final answer 命中且 profit_loss=1.1741248，runtime shadow replacement 后未命中且 profit_loss=-2.0，profit_loss_delta=-3.1741248
关键判断：previous production proposal 不能晋级；它通过的 gate 仍带有离线 hindsight/eligibility 色彩，而真正按 runtime-style constraints 消费时会回撤。下一阶段应收紧 runtime guard 或增加更强的可用赛前特征过滤，再重新跑 runtime shadow replay；不能把当前 rule 写入默认 production profile
README 更新 runtime shadow replay 命令、失败报告、关键指标与 blocker；该能力属于“core recommendation quality / feature-flagged runtime shadow replay / promotion blocker evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-200 当前落地能力：

```text
按 V3.1-199 的 blocker 收紧 runtime shadow replay guard；本轮仍不修改 production profile、不进入前端、不接实时 API/VPS、不做自动下注，只把失败样本转化为可运行的 shadow-only 候选级护栏
replacement_short_odds_runtime_shadow 新增 min_candidate_hit_probability_delta_vs_original：在 final-answer override arbitration 之前，先过滤相对当前 final answer hit probability 亏损过大的候选；该字段可由 CLI option 提供，也可由 rule.constraints_json 中的同名约束承载
CLI nutmeg-recommendation-replacement-short-odds-runtime-shadow-replay 新增 --min-candidate-hit-probability-delta-vs-original；报告 summary_json.options 会记录该阈值，确保后续晋级证据可复现
新增 deterministic test 覆盖：高赔率但相对原 final answer 命中概率亏损过大的候选会被过滤，runtime arbitration 会转向仍在阈值内的 safer candidate；CLI options loader 同步覆盖新增参数
生成五季 guarded runtime shadow replay report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_candidate_guard_v1.json；report_key=historical_short_odds_runtime_shadow_replay:ade3aa8e4bfbc02b
输入 audit：historical_candidate_marginal_audit:f7c3565ac8b0ec1e；输入 rule profile：historical_short_odds_promotion_smoke:d9bbc89fe4e355d2 的 temporary_profile_set_json；新增 guard min_candidate_hit_probability_delta_vs_original=-0.025
guarded runtime shadow replay 结果：status=shadow_replay_passed；passed=true；final_answer_count=30；changed_final_answer_count=17；baseline_final_answer_hit_count=20；shadow_final_answer_hit_count=20；final_answer_hit_delta_count=0；final_answer_hit_rate_delta=0
收益结果：baseline_roi=0.05017769041333339；shadow_roi=0.06781656196000004；roi_delta=+0.017638871546666643；profit_loss_delta=+1.058332292799999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.014697457992009506
关键修复样本：FRA_LIGUE_1 2024-2025 不再把 Marseille v Montpellier 替换成 PSG v Reims 的未命中腿；guard 后选择 Lyon v Angers，保持该 final answer 命中且 profit_loss_delta=+0.11235839999999975
关键判断：candidate-level original-hit-probability guard 可以把上一轮 runtime blocker 转为 pass，但它仍只是 shadow evidence；默认 production profile、普通推荐输出和前端答案页均未改变。下一阶段应把该 guard 写入 governed proposal/smoke 的约束链并做第二轮 promotion admission，而不是直接启用生产规则
README 更新 guarded runtime shadow replay 命令、报告路径、report_key 与核心指标；该能力属于“core recommendation quality / runtime guard refinement / no-production-change evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-201 当前落地能力：

```text
按 V3.1-200 结论把 candidate-level original-hit-probability guard 纳入 governed proposal / promotion smoke 证据链；本轮仍不修改 default production profile、不进入前端、不接实时 API/VPS、不做自动下注，只要求后续晋级 artifact 必须携带 runtime replay passed 证据和同名 guard
replacement_short_odds_production_proposal 新增可选 runtime_shadow_replay_report 输入与 loader；CLI 新增 --runtime-shadow-replay-report、--min-candidate-hit-probability-delta-vs-original、--allow-unpassed-runtime-shadow-replay
production proposal checks 新增 runtime_shadow_replay_present、runtime_shadow_replay_passed、runtime source audit key linkage、runtime final-answer count/changed count/hit-rate/ROI/profit/harm/average hit-probability checks、candidate guard check、no production/public change checks
proposal_rule.source_report_keys 新增 runtime_shadow_replay；constraints_json 新增 min_candidate_hit_probability_delta_vs_original=-0.025；evidence_json 新增 runtime_* metrics；rollback_conditions 新增 disable_if_runtime_shadow_replay_report_missing_or_failed 与 disable_if_candidate_hit_probability_delta_below_-0.025
replacement_short_odds_promotion_smoke 新增 candidate guard 校验、runtime shadow passed evidence 校验、runtime harm evidence 校验；required_source_report_keys 增加 runtime_shadow_replay，required_rollback_conditions 增加 disable_if_runtime_shadow_replay_report_missing_or_failed；CLI 同步新增 --min-candidate-hit-probability-delta-vs-original
新增 deterministic tests 覆盖：proposal 能携带 runtime guard evidence；failed runtime replay 会阻断 proposal；promotion smoke 会校验 runtime source key、candidate guard、runtime no-harm evidence；CLI options loader 覆盖新增参数
生成 guarded production proposal report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_production_proposal_candidate_guard_v1.json；report_key=historical_short_odds_production_proposal:981893da164fc151；status=production_proposal_ready；production_recommendation_allowed=true
proposal 输入链：suite_gate=historical_short_odds_suite_gate:93a0dc3ef86ec7da；final_answer_gate=historical_short_odds_final_answer_gate:03a2e45b6e358651；runtime_shadow_replay=historical_short_odds_runtime_shadow_replay:ade3aa8e4bfbc02b；audit=historical_candidate_marginal_audit:f7c3565ac8b0ec1e；competition_gate=historical_short_odds_competition_gate:3397bc2ff3258934；generated_shadow=historical_short_odds_shadow_rerank:661bc6f8fcadc431
生成 guarded promotion smoke report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_promotion_smoke_candidate_guard_v1.json；report_key=historical_short_odds_promotion_smoke:25b74e16e1f785a9；passed=true；runtime_profile_written=false；public_response_changed=false；production_recommendation_changed=false
使用 guarded promotion smoke temporary profile 再跑 runtime shadow replay，不再通过 CLI 传入 candidate guard；报告 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_promotion_candidate_guard_v1.json；report_key=historical_short_odds_runtime_shadow_replay:29fe012ab7b293a6；rule_candidate_guard=-0.025；cli_candidate_guard=null
promotion artifact runtime replay 结果：status=shadow_replay_passed；final_answer_count=30；changed_final_answer_count=17；baseline_final_answer_hit_count=20；shadow_final_answer_hit_count=20；final_answer_hit_delta_count=0；roi_delta=+0.017638871546666643；profit_loss_delta=+1.058332292799999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.014697457992009506
关键判断：guard 已从“一次 CLI 覆盖”升级成 proposal/smoke/runtime rule chain 的可审计约束，但默认生产配置仍未启用。下一阶段应做更宽历史切片/rolling admission 或跨赛季 holdout gate，再决定是否把该规则写入正式 runtime profile
README 更新 guarded proposal、promotion smoke、rule-sourced runtime replay 的报告路径、report_key 与核心指标；该能力属于“core recommendation quality / governed runtime guard admission / no-production-change evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-202 当前落地能力：

```text
按 V3.1-201 结论新增 short-odds guarded rule 的 rolling / holdout admission gate；本轮仍不修改 default production profile、不进入前端、不接实时 API/VPS、不做自动下注，只验证 guarded promotion smoke temporary profile 在更宽 fold 口径下是否持续不伤命中
新增 replacement_short_odds_rolling_admission 模块：读取 HistoricalCandidateMarginalAuditReport 与 ShortOddsRuntimeRuleSet，先跑 overall runtime shadow replay，再按 competition、season、rolling_window 三类 fold 重建子 audit 并逐 fold 调用 runtime shadow replay
新增模型：HistoricalShortOddsRollingAdmissionOptions、HistoricalShortOddsRollingAdmissionCheck、HistoricalShortOddsRollingAdmissionFold、HistoricalShortOddsRollingAdmissionReport；报告显式输出 production_recommendation_allowed、shadow_allowed、overall runtime metrics、active/failed fold counts、fold-level hit/ROI/profit/harm/average hit-probability metrics
新增 CLI：nutmeg-recommendation-replacement-short-odds-rolling-admission，支持 audit report、rule profile、rule ids、overall gate、fold gate、active competition/season/rolling fold count、rolling window size/step、max failed fold count、production-change override 与 no-fail-process
新增 deterministic tests 覆盖：全部 active folds 通过时 accepted；overall runtime replay 失败时 rejected；CLI options loader 与 main 输出正常；recommendations __init__ 导出新增模型与 builder
生成五季 rolling admission report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_rolling_admission_candidate_guard_v1.json；report_key=historical_short_odds_rolling_admission:6ff5f39ad9130544；status=accepted；production_recommendation_allowed=true；shadow_allowed=true
输入 audit：historical_candidate_marginal_audit:f7c3565ac8b0ec1e；输入 rule profile：v3_1_short_odds_replacement_candidate_guard_promotion_smoke_v1；overall_runtime_shadow_report_key=historical_short_odds_runtime_shadow_replay:29fe012ab7b293a6
overall gate 结果：final_answer_count=30；changed_final_answer_count=17；final_answer_hit_rate_delta=0；roi_delta=+0.017638871546666643；profit_loss_delta=+1.058332292799999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.014697457992009506
fold gate 结果：fold_count=20；active_fold_count=13；failed_fold_count=0；active_competition_fold_count=4；active_season_fold_count=5；active_rolling_fold_count=4；ESP_LA_LIGA 与 JPN_J1 因规则未作用 / changed=0 被 skipped，不计入 active fold
active competition folds 全部通过：EPL profit_loss_delta=+0.26457029279999933；FRA_LIGUE_1 +0.4424980000000005；GER_BUNDESLIGA +0.2376640000000001；ITA_SERIE_A +0.11359999999999992；所有 active competition fold hit delta=0、harm=0
active season folds 全部通过：2020_2021、2021_2022、2022_2023、2023_2024、2024_2025 均 hit delta=0、ROI/profit 非负、harm=0；4 个 rolling-window fold 均 hit delta=0、ROI/profit 非负、harm=0
关键判断：guarded short-odds rule 已通过 overall + competition + season + rolling-window admission，没有发现隐藏 active fold 回撤；但本阶段仍只生成 admission evidence，不写 default production profile。下一阶段可将 rolling admission report 接入 production proposal/smoke 必备 source key，或做更大样本/更多联赛 holdout 后再考虑正式 runtime profile promotion
README 更新 rolling admission 命令、报告路径、report_key 与核心指标；该能力属于“core recommendation quality / rolling holdout admission / no-production-change evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-203 当前落地能力：

```text
按 V3.1-202 结论把 rolling admission 从旁路证据升级为 governed proposal / promotion smoke 的必需 source key；本轮仍不修改 default production profile、不进入前端、不接实时 API/VPS、不做自动下注，只强化生产晋级证据链
replacement_short_odds_production_proposal 新增 rolling_admission_report 输入、loader 与 CLI --rolling-admission-report；options 新增 require_rolling_admission_accepted、min_rolling_active_competition_fold_count、min_rolling_active_season_fold_count、min_rolling_active_rolling_fold_count、max_rolling_failed_fold_count
production proposal checks 新增 rolling_admission_present、accepted status、production_allowed、source audit key linkage、overall runtime shadow key linkage、failed fold count、active competition/season/rolling fold count、overall hit-rate/ROI/profit/harm/average hit-probability checks
proposal_rule.source_report_keys 新增 rolling_admission；evidence_json 新增 rolling_admission_accepted、rolling_failed_fold_count、rolling_active_*_fold_count、rolling_overall_* metrics；rollback_conditions 新增 disable_if_rolling_admission_report_missing_or_failed 与 disable_if_rolling_admission_failed_fold_count_above_0
production proposal 的 runtime candidate guard 校验修正为同时接受 CLI option guard 与 rule_set_json.rules[].constraints_json 中的 rule-sourced guard；这保证 promotion artifact replay 不需要再依赖 CLI 覆盖
replacement_short_odds_promotion_smoke 的 required_source_report_keys 新增 rolling_admission，required_rollback_conditions 新增 disable_if_rolling_admission_report_missing_or_failed；rule checks 新增 rolling accepted、failed fold、active folds、overall hit-rate/ROI/profit/harm/average hit-probability evidence 校验
新增 deterministic tests 覆盖：proposal 携带 rolling admission evidence；failed rolling admission 阻断 proposal；rule-sourced runtime guard 可通过 proposal 校验；promotion smoke 缺少 rolling evidence 会失败；CLI options loader 覆盖 rolling 参数
生成 rolling-admission governed production proposal report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_production_proposal_rolling_admission_v1.json；report_key=historical_short_odds_production_proposal:f08a4fca608f2f00；status=production_proposal_ready；production_recommendation_allowed=true
proposal 输入链：suite_gate=historical_short_odds_suite_gate:93a0dc3ef86ec7da；final_answer_gate=historical_short_odds_final_answer_gate:03a2e45b6e358651；runtime_shadow_replay=historical_short_odds_runtime_shadow_replay:29fe012ab7b293a6；rolling_admission=historical_short_odds_rolling_admission:6ff5f39ad9130544；audit=historical_candidate_marginal_audit:f7c3565ac8b0ec1e；competition_gate=historical_short_odds_competition_gate:3397bc2ff3258934；generated_shadow=historical_short_odds_shadow_rerank:661bc6f8fcadc431
生成 rolling-admission promotion smoke report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_promotion_smoke_rolling_admission_v1.json；report_key=historical_short_odds_promotion_smoke:b56b086691698ecf；passed=true；runtime_profile_written=false；public_response_changed=false；production_recommendation_changed=false
使用 rolling-admission promotion smoke temporary profile 再跑 runtime shadow replay，不通过 CLI 传入 candidate guard；报告 configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_rolling_admission_v1.json；report_key=historical_short_odds_runtime_shadow_replay:7141915996a29cb6
post-smoke runtime replay 结果：status=shadow_replay_passed；final_answer_count=30；changed_final_answer_count=17；baseline_final_answer_hit_count=20；shadow_final_answer_hit_count=20；final_answer_hit_delta_count=0；roi_delta=+0.017638871546666643；profit_loss_delta=+1.058332292799999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.014697457992009506
关键判断：short-odds guarded replacement 现在具备 suite/final-answer/runtime/rolling admission 四层 source-key 链路，普通用户路径、前端、默认生产 profile 仍不变。下一阶段可以选择把该规则写入正式 runtime profile 前的最后 admission/promotion step，或继续扩大真实历史样本后再启用
README 更新 rolling-admission governed proposal、promotion smoke、post-smoke runtime replay 的命令、报告路径、report_key 与核心指标；该能力属于“core recommendation quality / governed rolling admission / no-production-change evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-204 当前落地能力：

```text
按 V3.1-203 结论新增 short-odds runtime profile promotion 前最后门禁；本轮仍不修改 default production profile、不进入前端、不接实时 API/VPS、不做自动下注，只生成候选 runtime profile artifact 并验证 runtime loader 可直接复现
新增 replacement_short_odds_runtime_profile_promotion 模块：读取当前 CompetitionRecommendationProfileSet、HistoricalShortOddsProductionProposalReport、HistoricalShortOddsPromotionSmokeReport、linked HistoricalShortOddsRuntimeShadowReplayReport、可选 post-promotion runtime shadow replay、HistoricalShortOddsRollingAdmissionReport
新增模型：HistoricalShortOddsRuntimeProfilePromotionOptions、HistoricalShortOddsRuntimeProfilePromotionCheck、HistoricalShortOddsRuntimeProfilePromotionReport；报告显式输出 promotion_ready、candidate_rule_count、allowed/excluded competitions、source report key chain、blockers、candidate_runtime_profile_json
新增 CLI：nutmeg-recommendation-replacement-short-odds-runtime-profile-promote，支持 current profile path、production proposal、promotion smoke、linked runtime shadow replay、post-promotion runtime replay、rolling admission、profile output、report output、最终门禁阈值、dry-run 与 no-fail-process
final gate 校验：production proposal ready/allowed、promotion smoke passed、linked runtime replay passed、proposal runtime key linkage、proposal rolling key linkage、rolling overall runtime key linkage、rolling accepted/production allowed、failed fold=0、active competition/season/rolling folds、runtime hit-rate/ROI/profit/harm/average hit-probability、post-promotion runtime replay passed/source profile version/metrics、no public response change、no production change、当前默认 profile 不已有 short-odds rules、candidate rule count 与 allowed competition count
新增 deterministic tests 覆盖：通过完整证据链生成候选 runtime profile；rolling admission 不接受时阻断；CLI 写出 candidate profile 与 promotion report；CLI options loader 覆盖最后门禁参数
生成候选 runtime profile promotion report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_promotion_v1.json；report_key=historical_short_odds_runtime_profile_promotion:a673be0bf1c52d82；status=promotion_ready；promotion_ready=true；candidate_rule_count=1；blockers=[]
生成候选 runtime profile artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_candidate_v1.json；profile_version=v3_1_short_odds_replacement_runtime_profile_candidate_v1；short_odds_replacement_rules=1；base_profile_version=v3_1_competition_profiles_football_data_co_uk_2026_05_15_eng_championship_value_guard_v1
候选 profile source chain：production_proposal=historical_short_odds_production_proposal:f08a4fca608f2f00；promotion_smoke=historical_short_odds_promotion_smoke:b56b086691698ecf；runtime_shadow_replay=historical_short_odds_runtime_shadow_replay:29fe012ab7b293a6；post_promotion_runtime_shadow_replay=historical_short_odds_runtime_shadow_replay:7141915996a29cb6；rolling_admission=historical_short_odds_rolling_admission:6ff5f39ad9130544
使用 candidate runtime profile artifact 直接跑 runtime shadow replay：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_runtime_profile_candidate_v1.json；report_key=historical_short_odds_runtime_shadow_replay:81b919a9034435cb；status=shadow_replay_passed；passed=true
candidate profile replay 结果：final_answer_count=30；changed_final_answer_count=17；baseline_final_answer_hit_count=20；shadow_final_answer_hit_count=20；final_answer_hit_delta_count=0；final_answer_hit_rate_delta=0；roi_delta=+0.017638871546666643；profit_loss_delta=+1.058332292799999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.014697457992009506；production_recommendation_changed=false；public_response_changed=false
关键判断：short-odds guarded replacement 已经从 shadow evidence 走到“候选 runtime profile artifact 可复现”的状态，但 default production profile 仍未写入。下一阶段如继续，应做最终生产写入前的 explicit enable step：要么要求人工批准后把候选 artifact 合并进默认 profile，要么继续扩大真实历史样本和联赛覆盖后再启用
README 更新 final pre-promotion gate、candidate runtime profile artifact、candidate replay 的命令、报告路径、report_key 与核心指标；该能力属于“core recommendation quality / runtime profile candidate promotion gate / no-default-profile-change evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-205 当前落地能力：

```text
按 V3.1-204 结论新增 short-odds runtime profile activation gate；本轮仍不修改 default production profile、不进入前端、不接实时 API/VPS、不做自动下注，只生成 activated profile artifact 并验证 runtime loader 可复现
新增 replacement_short_odds_runtime_profile_activation 模块：读取当前默认 profile、候选 runtime profile、runtime profile promotion report、candidate runtime shadow replay report，输出 activation report 与 activated profile artifact
新增模型：HistoricalShortOddsRuntimeProfileActivationOptions、HistoricalShortOddsRuntimeProfileActivationCheck、HistoricalShortOddsRuntimeProfileActivationReport；报告显式输出 activation_ready、activated_profile_version、source report key chain、candidate_rule_count、blockers、activated_profile_json、default_profile_written=false
新增 CLI：nutmeg-recommendation-replacement-short-odds-runtime-profile-activate，支持 current profile path、candidate runtime profile、runtime profile promotion report、candidate runtime shadow replay report、activated profile output、report output、阈值、dry-run 与 no-fail-process
activation gate 校验：promotion status/ready、candidate promotion_ready、candidate profile version 匹配 promotion、production proposal/promotion smoke/runtime shadow/post-promotion runtime/rolling admission source keys 全链路匹配、candidate rule count、allowed competition count、当前默认 profile 不已有 short-odds rules、candidate replay passed/status/source profile、final-answer count、changed final-answer count、hit-rate/ROI/profit/harm/average hit-probability、no public response change、no production recommendation change
新增 deterministic tests 覆盖：通过完整证据链生成 activated profile；当前默认 profile 已有 short-odds rules 时阻断；CLI 写出 activated profile 与 activation report；CLI options loader 覆盖 activation gate 参数
生成 activation report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_activation_v1.json；report_key=historical_short_odds_runtime_profile_activation:0599897930eec3cf；status=activation_ready；activation_ready=true；candidate_rule_count=1；blockers=[]
生成 activated profile artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_activated_profile_candidate_v1.json；profile_version=v3_1_competition_profiles_short_odds_runtime_enabled_candidate_v1；short_odds_replacement_rules=1；base_profile_version=v3_1_competition_profiles_football_data_co_uk_2026_05_15_eng_championship_value_guard_v1；default_profile_written=false
activated profile source chain：runtime_profile_promotion=historical_short_odds_runtime_profile_promotion:a673be0bf1c52d82；candidate_runtime_shadow_replay=historical_short_odds_runtime_shadow_replay:81b919a9034435cb；production_proposal=historical_short_odds_production_proposal:f08a4fca608f2f00；promotion_smoke=historical_short_odds_promotion_smoke:b56b086691698ecf；runtime_shadow_replay=historical_short_odds_runtime_shadow_replay:29fe012ab7b293a6；post_promotion_runtime_shadow_replay=historical_short_odds_runtime_shadow_replay:7141915996a29cb6；rolling_admission=historical_short_odds_rolling_admission:6ff5f39ad9130544
使用 activated profile artifact 直接跑 runtime shadow replay：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_activated_profile_candidate_v1.json；report_key=historical_short_odds_runtime_shadow_replay:8b865425230f1f07；status=shadow_replay_passed；passed=true
activated profile replay 结果：final_answer_count=30；changed_final_answer_count=17；baseline_final_answer_hit_count=20；shadow_final_answer_hit_count=20；final_answer_hit_delta_count=0；final_answer_hit_rate_delta=0；roi_delta=+0.017638871546666643；profit_loss_delta=+1.058332292799999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.014697457992009506；production_recommendation_changed=false；public_response_changed=false
关键判断：short-odds guarded replacement 已具备可启用 artifact 与 replay 证据，但默认运行配置仍未切换。下一阶段可以做显式 switch/apply 步骤，或先把 activation gate 接入周期质量门禁后再启用
README 更新 activation gate、activated profile artifact、activated profile replay 的命令、报告路径、report_key 与核心指标；该能力属于“core recommendation quality / explicit activation artifact / no-default-profile-change evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-206 当前落地能力：

```text
按 V3.1-205 结论新增 short-odds runtime profile switch/apply gate；本轮默认仍不修改 default production profile、不进入前端、不接实时 API/VPS、不做自动下注，只生成 staged profile artifact，并要求真实覆盖默认 profile 时同时提供 --write-default-profile 与 --confirm-default-profile-write
新增 replacement_short_odds_runtime_profile_switch 模块：读取当前默认 profile、activated profile、activation report、activated runtime shadow replay report，输出 switch report 与 staged profile artifact；CLI 支持受控写默认 profile，但写入必须双参数显式确认
新增模型：HistoricalShortOddsRuntimeProfileSwitchOptions、HistoricalShortOddsRuntimeProfileSwitchCheck、HistoricalShortOddsRuntimeProfileSwitchReport；报告显式输出 switch_ready、default_profile_write_requested、default_profile_written、source report key chain、candidate_rule_count、blockers、staged_profile_json
新增 CLI：nutmeg-recommendation-replacement-short-odds-runtime-profile-switch，支持 current profile path、activated profile、activation report、activated runtime shadow replay report、staged profile output、report output、阈值、write-default-profile、confirm-default-profile-write、dry-run 与 no-fail-process
switch gate 校验：activation status/ready、activated profile activation_ready、activated profile version 匹配 activation、activated base version 匹配当前默认 profile、当前默认 profile 不已有 short-odds rules、promotion/candidate replay source key 链路匹配、candidate rule count、allowed competition count、activated replay passed/status/source profile、final-answer count、changed final-answer count、hit-rate/ROI/profit/harm/average hit-probability、no public response change、no production recommendation change、默认 profile 写入确认
新增 deterministic tests 覆盖：通过完整证据链生成 staged profile；当前默认 profile 版本过期时阻断；请求写默认 profile 但未确认时阻断；CLI 写 staged 输出不改当前 profile；CLI 带双确认参数可写临时默认 profile；CLI options loader 覆盖 switch gate 参数
生成 switch report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_v1.json；report_key=historical_short_odds_runtime_profile_switch:ad81a85d16cbb696；status=switch_ready；switch_ready=true；candidate_rule_count=1；default_profile_write_requested=false；default_profile_written=false；blockers=[]
生成 staged profile artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_staged_v1.json；profile_version=v3_1_competition_profiles_short_odds_runtime_enabled_candidate_v1；short_odds_replacement_rules=1；switch_ready=true；default_profile_written=false
staged profile source chain：runtime_profile_activation=historical_short_odds_runtime_profile_activation:0599897930eec3cf；activated_runtime_shadow_replay=historical_short_odds_runtime_shadow_replay:8b865425230f1f07；runtime_profile_promotion=historical_short_odds_runtime_profile_promotion:a673be0bf1c52d82；candidate_runtime_shadow_replay=historical_short_odds_runtime_shadow_replay:81b919a9034435cb；production_proposal=historical_short_odds_production_proposal:f08a4fca608f2f00；promotion_smoke=historical_short_odds_promotion_smoke:b56b086691698ecf；runtime_shadow_replay=historical_short_odds_runtime_shadow_replay:29fe012ab7b293a6；post_promotion_runtime_shadow_replay=historical_short_odds_runtime_shadow_replay:7141915996a29cb6；rolling_admission=historical_short_odds_rolling_admission:6ff5f39ad9130544
使用 staged profile artifact 直接跑 runtime shadow replay：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_switch_staged_v1.json；report_key=historical_short_odds_runtime_shadow_replay:8b865425230f1f07；status=shadow_replay_passed；passed=true
staged profile replay 结果：final_answer_count=30；changed_final_answer_count=17；baseline_final_answer_hit_count=20；shadow_final_answer_hit_count=20；final_answer_hit_delta_count=0；final_answer_hit_rate_delta=0；roi_delta=+0.017638871546666643；profit_loss_delta=+1.058332292799999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.014697457992009506；production_recommendation_changed=false；public_response_changed=false
关键判断：short-odds guarded replacement 已具备“候选 -> activation -> switch-ready staged profile -> replay”的完整证据链，但默认运行配置仍未切换。下一阶段应把 switch report 接入周期质量门禁/核心验证，确认每轮开发都能看见该 staged profile 的质量状态，然后再决定是否显式写入默认 profile
README 更新 switch/apply gate、staged profile artifact、staged profile replay 的命令、报告路径、report_key 与核心指标；该能力属于“core recommendation quality / explicit switch gate / default-write guarded by double confirmation”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-207 当前落地能力：

```text
按 V3.1-206 结论把 switch-ready staged profile 接入 persisted benchmark quality gate 与 cycle gate option 透传；本轮仍不修改 default production profile、不进入前端、不接实时 API/VPS、不做自动下注，只让周期质量门禁能消费 switch report 与 staged replay report
benchmark_quality_gate 新增 runtime profile switch evidence：runtime_profile_switch_report_path、runtime_profile_switch_replay_report_path、require_runtime_profile_switch_gate、require_runtime_profile_switch_replay、require_runtime_profile_switch_staged_only、rule/competition/final-answer/ROI/profit/harm/average hit-probability 阈值
benchmark quality gate 新增 checks：runtime_profile_switch_gate_present、runtime_profile_switch_ready、runtime_profile_switch_status_ready、runtime_profile_switch_default_profile_not_requested、runtime_profile_switch_default_profile_not_written、runtime_profile_switch_rule_count、runtime_profile_switch_allowed_competition_count、runtime_profile_switch_replay_present、runtime_profile_switch_replay_passed/status/profile_matches、final_answer_count、changed_final_answer_count、hit-rate/ROI/profit/harm/average hit-probability、no public response change、no production recommendation change
benchmark quality gate summary 新增 runtime profile switch 字段：runtime_profile_switch_key/status/ready/profile_version/rule_count/allowed_competition_count/default write flags，以及 replay key/status/passed/final_answer_count/changed_final_answer_count/hit-rate delta/ROI delta/profit delta/harm count/average hit-probability delta/public/prod change flags
benchmark_cycle CLI 新增 gate-runtime-profile-switch-* 参数并透传至 RecommendationBenchmarkQualityGateOptions；cycle summary 会携带 runtime_profile_switch_* 关键字段，便于周期报告/持久化 summary_json 审计
新增 deterministic tests 覆盖：benchmark quality gate 消费 switch evidence；缺失 required switch evidence 会阻断；staged replay 回归会阻断；从 options 路径加载 switch/replay reports；benchmark quality gate CLI 参数映射；benchmark cycle CLI 参数透传；cycle summary 携带 switch evidence
生成 benchmark gate bootstrap smoke：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_benchmark_gate_smoke_v1.json；gate_key=recommendation_benchmark_quality_gate:all:any；status=passed；runtime_profile_switch_ready=true；runtime_profile_switch_replay_passed=true；failed_checks=[]；default_profile_written=false
bootstrap smoke 使用真实 switch evidence：switch=historical_short_odds_runtime_profile_switch:ad81a85d16cbb696；staged_replay=historical_short_odds_runtime_shadow_replay:8b865425230f1f07；rule_count=1；allowed_competition_count=4；final_answer_count=30；changed_final_answer_count=17；hit-rate delta=0；ROI delta=+0.017638871546666643；profit/loss delta=+1.058332292799999；harm_count=0；average_hit_probability_delta=-0.014697457992009506
bootstrap smoke warning：benchmark_quality_gate:no_persisted_benchmark_history；这是本地无 DB 持久化历史时的预期引导 warning，不影响 switch evidence checks。真实周期运行有 persisted benchmark history 后会同时检查 benchmark history 与 switch evidence
关键判断：short-odds guarded replacement 的 staged profile 已进入周期质量门禁视野；后续每轮 benchmark/cycle 都可以要求该 evidence 保持 switch_ready + staged-only + replay passed。下一阶段可选择把该 gate 配置加入实际 cycle 命令/CI 运行脚本，或继续扩大真实历史样本后再决定是否显式写默认 profile
README 更新 benchmark quality gate 消费 runtime profile switch evidence 的命令、smoke artifact、核心字段与 bootstrap warning；该能力属于“periodic quality gate hardening / staged profile evidence / no-default-profile-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-208 当前落地能力：

```text
按 V3.1-207 结论把 short-odds runtime profile switch gate 固化为可复用预设；本轮仍不修改 default production profile、不进入前端、不接实时 API/VPS、不做自动下注，只减少周期质量门禁的人工参数拼装风险
benchmark_quality_gate 新增 runtime profile switch preset：short_odds_candidate_v1；该预设指向 switch_ready report 与 staged replay report，并自动启用 require_runtime_profile_switch_gate、require_runtime_profile_switch_replay、require_runtime_profile_switch_staged_only
short_odds_candidate_v1 预设阈值：rule_count>=1、allowed_competition_count>=4、final_answer_count>=30、changed_final_answer_count>=5、hit-rate delta>=0、ROI delta>=0、profit/loss delta>=0、harm_count_vs_original<=0、average_hit_probability_delta>=-0.02
benchmark quality gate CLI 新增 --runtime-profile-switch-preset short_odds_candidate_v1；benchmark cycle CLI 新增 --gate-runtime-profile-switch-preset short_odds_candidate_v1
quality gate summary 新增 runtime_profile_switch_preset；cycle summary 会把 runtime_profile_switch_preset 与 runtime_profile_switch_* staged replay 核心指标一起写入 summary_json，便于后续周期报告审计
新增 deterministic tests 覆盖：quality gate CLI preset 映射；cycle CLI gate preset 映射；既有 switch evidence、缺失 evidence、replay 回归与 cycle summary 测试保持通过
生成 preset benchmark gate bootstrap smoke：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_benchmark_gate_preset_smoke_v1.json；gate_key=recommendation_benchmark_quality_gate:all:any；status=passed；runtime_profile_switch_preset=short_odds_candidate_v1；failed_checks=[]；runtime_profile_switch_ready=true；runtime_profile_switch_replay_passed=true；ROI delta=+0.017638871546666643
关键判断：short-odds guarded replacement 的 staged profile 现在既有显式 artifact 证据，也有 cycle/gate 可复用入口。下一阶段应继续围绕真实历史样本和最终答案准确率推进，而不是扩大 VPS/数据源接入范围；是否写入 default profile 仍需单独显式确认
README 更新 runtime profile switch preset 的 gate/cycle 命令、preset 行为说明与 summary 字段；该能力属于“periodic quality gate preset / no-default-profile-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-209 当前落地能力：

```text
按 V3.1-208 结论把 runtime profile switch preset 接入 cycle 级别可审计证据；本轮仍不修改 default production profile、不进入前端、不接实时 API/VPS、不做自动下注，只确保周期报告不会把带 preset 与不带 preset 的质量门禁历史混在一起
benchmark_cycle 的 cycle_key 现在在 gate_options.runtime_profile_switch_preset 存在时追加 runtime_profile_switch_preset:{preset}；无 preset 时保持原有 cycle_key 兼容
新增 deterministic test：test_cycle_key_includes_runtime_profile_switch_preset，验证带 short_odds_candidate_v1 的 cycle_key 与 summary_json.cycle_key 一致
更新 cycle summary 测试，使 runtime_profile_switch_preset 与 runtime_profile_switch_* staged replay 指标一起进入 cycle summary
生成 cycle preset bootstrap smoke：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_benchmark_cycle_preset_smoke_v1.json；cycle_key=recommendation_benchmark_cycle:cycle-preset-smoke:once:gate:runtime_profile_switch_preset:short_odds_candidate_v1；status=passed；gate_status=passed；runtime_profile_switch_preset=short_odds_candidate_v1；failed_checks=[]；runtime_profile_switch_ready=true；runtime_profile_switch_replay_passed=true；ROI delta=+0.017638871546666643
cycle preset bootstrap smoke warning：benchmark_quality_gate:no_persisted_benchmark_history；这是本地无 DB 持久化 benchmark history 时的预期 warning。该 smoke 只证明 cycle -> gate preset -> switch/replay evidence 链路可复现，真实周期运行仍应依赖 persisted benchmark history
关键判断：短赔率 staged profile 质量证据现在已经进入 gate 与 cycle 两层审计路径，且 cycle history key 可区分 preset 配置。下一阶段应转回最终答案准确率的真实历史回归/调参，而不是继续扩展部署或数据源接入
README 更新 cycle preset key、summary 与 bootstrap cycle smoke artifact；该能力属于“cycle quality evidence / no-default-profile-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-210 当前落地能力：

```text
按 V3.1-209 结论回到最终答案准确率/ROI 核心能力，新增 historical_final_answer_segment_audit 模块；本轮不改推荐生产逻辑、不接实时 API/VPS、不做自动下注，只生成可用于下一轮调参的最终答案分段证据
新增模型：HistoricalFinalAnswerSegmentAuditOptions、HistoricalFinalAnswerSegmentMetric、HistoricalFinalAnswerSegmentAuditReport；报告只统计用户实际会收到的 final_answer，而不是所有候选 scenario
新增 CLI：nutmeg-recommendation-final-answer-segment-audit；支持 slice paths 或 --suite-manifest，支持 baseline/candidate side、1x1-8x1 pass types、single/multiple、预算、候选池限制、market context signals、min segment sample size、top segment limit 与 output path
segment audit 当前分组：overall、pass_type、mode、scenario、leg_count、odds_band、hit_probability_band、competition、market_mix；每个 segment 输出 sample/hit/loss、hit rate、stake/return/profit/ROI、expected hit probability、odds product、leg odds/probability、Brier/log-loss/calibration 与 loss_driver_score
新增 deterministic tests 覆盖：识别短赔率/EPL/1x1 loss-driver segment；min_segment_sample_size 阻止小样本段进入 loss drivers；baseline side 可独立读取
生成 core 5 seasons candidate48/window4 segment audit：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_audit_v1.json；report_key=historical_final_answer_segment_audit:744d6c2cb24b6be3；suite_status=unchanged；comparison_count=30；final_answer_sample_size=30
当前 segment audit 核心结论：overall hit_rate=0.7666666666666667，但 ROI=-0.0862312646666666、profit_loss=-5.173875879999996；top loss drivers 为 odds_band:1.00-1.30、competition:ESP_LA_LIGA、competition:GER_BUNDESLIGA、leg_count:3/pass_type:3x1/scenario:3x1:single、hit_probability_band:0.85-1.00
关键判断：下一轮调参不应泛化修改所有串关，也不应继续扩展部署/数据源；应优先围绕短赔率高置信 favorite、ESP/GER league segment、3x1 single 做受控 guard/penalty/grid，并保持最终命中率不下降
README 更新 final-answer segment audit 命令、报告路径、report_key 与核心 loss-driver 结论；该能力属于“core final-answer accuracy diagnostics / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-211 当前落地能力：

```text
按 V3.1-210 segment audit 结论新增 opt-in final-answer segment penalty；本轮不改生产默认、不进入前端、不接实时 API/VPS、不做自动下注，只让历史回测可以对已定位的最终答案拖累段做受控仲裁惩罚实验
HistoricalRecommendationBacktestOptions 新增 final_answer_segment_penalty 及其 strength、pass_types、modes、competition_ids、hit_probability min/max、odds_product min/max、average_leg_decimal_odds min/max 过滤条件
历史 final-answer 仲裁排序现在在 opt-in 时使用 base_score - quality_signal_penalty - segment_penalty + upset_lane_boost；默认 final_answer_segment_penalty=false 时完全保持原路径
backtest summary 新增 final_answer_segment_* 配置回显、final_answer_segment_penalty_score、final_answer_segment_penalty_applied、final_answer_segment_penalty_option_count；suite summary 聚合 baseline/candidate_final_answer_segment_penalty_option_count
historical backtest CLI 新增 --final-answer-segment-penalty、--final-answer-segment-penalty-strength、--final-answer-segment-pass-types、--final-answer-segment-modes、--final-answer-segment-competitions、hit probability/odds product/average leg odds 过滤参数
新增 deterministic tests 覆盖：segment penalty 默认关闭时不影响排序；启用后可压制 3x1 single risky segment；pass_type/competition 不匹配时不生效；suite summary 聚合 segment penalty option count
生成 segment penalty grid 报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_grid_v1.json；baseline solver 为 23/30 final hits、hit_rate=0.7666666666666667、ROI=-0.0862312646666666、profit_loss=-5.173875879999996
grid 结果：esp_ger_3x1_single profile 是唯一 accuracy-preserving 候选；strength 0.08 和 0.16 结果相同，penalty_option_count=10，final hits 提升到 25/30，hit_rate=0.8333333333333334，ROI delta=+0.04619413333333332，profit/loss delta=+2.7716479999999994，Brier/log-loss/calibration 均改善，但绝对 ROI 仍为 -0.04003713133333328，因此不能直接成为默认生产配置
rejected 结果：global_high_hit_short_leg_odds profile 让 ROI 转正到 0.051277690413333396、profit/loss delta=+8.2505373048，但 final_hit_count_delta=-1，命中率从 23/30 降到 22/30，按准确率优先规则拒绝
关键判断：下一步应围绕 esp_ger_3x1_single 做更细分的参数网格/rolling admission，而不是全局短赔率惩罚；生产默认仍不改变，直到命中率、ROI、rolling admission 和周期门禁同时通过
README 更新 segment penalty grid 报告路径、候选/拒绝结论与 accuracy-first 判断；该能力属于“core final-answer accuracy tuning / opt-in historical experiment / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-212 当前落地能力：

```text
按 V3.1-211 结论把 final-answer segment penalty 的手工实验固化为正式 grid CLI/report；本轮不改生产默认、不进入前端、不接实时 API/VPS、不做自动下注，只提升核心调参证据的可复现性
新增 historical_final_answer_segment_penalty_grid 模块：读取 slice paths 或 suite manifest，先跑未启用 segment penalty 的 baseline suite，再对 pass_type/mode/competition/命中概率/赔率乘积/平均腿赔率/strength 的候选网格逐一跑 opt-in backtest
新增模型：HistoricalFinalAnswerSegmentPenaltyGridOptions、HistoricalFinalAnswerSegmentPenaltyCandidate、HistoricalFinalAnswerSegmentPenaltyGridReport；报告输出 candidate_count、accepted/rejected、baseline summary、best_candidate、target_summary、rejection_reason_counts 与可复现 report_key
新增 CLI：nutmeg-recommendation-final-answer-segment-penalty-grid；默认聚焦 V3.1-211 锁定的 ESP_LA_LIGA + GER_BUNDESLIGA / 3x1 / single segment，同时允许通过 --pass-type-group、--mode-group、--competition-group、hit probability/odds product/average leg odds 与 strength values 覆盖
新增 deterministic tests 覆盖：accuracy-first 候选被接受；ROI 改善但 final hit 回撤时被拒绝；CLI 参数解析、输出文件与 none/数值网格组合正常
生成正式 focused grid 报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_profile_grid_v1.json；report_key=historical_final_answer_segment_penalty_grid:4a075200a8708024；candidate_count=16；accepted_count=8；rejected_count=8
focused grid baseline：23/30 final hits、hit_rate=0.7666666666666667、ROI=-0.0862312646666666、profit_loss=-5.173875879999996
best accepted candidate：ESP_LA_LIGA + GER_BUNDESLIGA / 3x1 / single / strength=0.04 / min_hit_probability=null / max_average_leg_decimal_odds=null；penalty_option_count=10；final hits=25/30；hit_rate=0.8333333333333334；ROI=-0.04003713133333328；profit_loss=-2.4022278799999968
best deltas：final_hit_count_delta=+2；final_hit_rate_delta=+0.06666666666666665；ROI delta=+0.04619413333333332；profit/loss delta=+2.7716479999999994；Brier delta=-0.04235942720763311；log-loss delta=-0.10332937887456839；mean calibration error delta=-0.06271815737535352
rejected candidates：所有 min_hit_probability=0.85 的候选 penalty_option_count=0，因 segment_penalty:penalty_option_count_too_low 与 segment_penalty:objective_improvement_missing 被拒绝；这说明当前有效信号不是“高命中概率段”，而是更宽的 ESP/GER 3x1 single segment
关键判断：正式 grid 确认 V3.1-211 的方向可复现，但绝对 ROI 仍为负；下一阶段应做该 focused candidate 的 rolling admission / fold gate，确认分赛季、分联赛、滚动窗口没有隐藏回撤，再决定是否进入 runtime profile proposal
README 更新正式 segment penalty grid CLI、报告路径、report_key 与 best/rejected 结论；该能力属于“core final-answer accuracy tuning / reproducible grid evidence / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-213 当前落地能力：

```text
按 V3.1-212 结论新增 final-answer segment penalty rolling admission / fold gate；本轮不改生产默认、不进入前端、不接实时 API/VPS、不做自动下注，只验证 focused segment penalty 是否存在隐藏 fold 回撤
新增 historical_final_answer_segment_penalty_rolling_admission 模块：读取 suite manifest/slice paths 与 segment penalty grid report，默认选择 grid best_candidate，再分别跑未启用 penalty 的 baseline suite 与启用 candidate penalty 的 candidate suite
新增模型：HistoricalFinalAnswerSegmentPenaltyRollingAdmissionOptions、HistoricalFinalAnswerSegmentPenaltyRollingAdmissionCheck、HistoricalFinalAnswerSegmentPenaltyFold、HistoricalFinalAnswerSegmentPenaltyRollingAdmissionReport；报告输出 overall fold、competition/season/rolling-window folds、active/failed fold counts、harm/improvement counts、hit/ROI/P&L/Brier/log-loss/calibration deltas
新增 CLI：nutmeg-recommendation-final-answer-segment-penalty-rolling-admission；支持 grid-report、candidate-key、suite manifest、1x1-8x1 single/multiple、候选池限制、overall/fold thresholds、rolling-window slice count/step、no-fail-process
新增 deterministic tests 覆盖：active folds 全通过时 accepted；单个 competition fold ROI/P&L 回撤时 shadow_only；CLI 参数解析、输出文件、source grid/candidate key 回显正常
生成 core 5 seasons rolling admission report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_rolling_admission_v1.json；report_key=historical_final_answer_segment_penalty_rolling_admission:697061e5cf9f7fae；status=shadow_only；candidate_profile_allowed=false；shadow_allowed=true
overall gate 结果：final_answer_count=30；penalty_option_count=10；changed_final_answer_count=5；baseline/candidate final hits=23/25；final_hit_delta=+2；hit_rate_delta=+0.06666666666666665；ROI delta=+0.04619413333333332；profit/loss delta=+2.7716479999999994；Brier/log-loss/calibration deltas 均改善；harm_count_vs_baseline=0；improvement_count_vs_baseline=2
fold gate 结果：fold_count=20；active_fold_count=11；active_competition_fold_count=2；active_season_fold_count=5；active_rolling_fold_count=4；failed_fold_count=5，因此不能进入 candidate profile / runtime proposal
competition folds：ESP_LA_LIGA active 但中性，penalty_option_count=5、hit delta=0、ROI/P&L delta=0；GER_BUNDESLIGA active 且贡献全部改善，penalty_option_count=5、hit delta=+2、ROI delta=+0.27716479999999993、profit/loss delta=+2.7716479999999994
failed folds：season:2020-2021、season:2021-2022、season:2022-2023、rolling_window:1、rolling_window:2；这些 fold 没有命中率回撤、Brier/log-loss/calibration 还改善，但 ROI/P&L 为负，因此被 strict admission 拦住
关键判断：ESP/GER 3x1 single penalty 的整体命中提升主要来自 GER_BUNDESLIGA 和后期窗口，早期 season/window 有收益泄漏；下一阶段不应 promotion，应改做“GER-only 或 late-season/season-aware focused grid”，直到 fold gate 不再 shadow_only
README 更新 rolling admission CLI、报告路径、report_key、overall/fold 结论；该能力属于“core final-answer admission gate / hidden fold regression detection / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-214 当前落地能力：

```text
按 V3.1-213 结论继续聚焦核心 final-answer 准确率/ROI，新增 season-aware final-answer segment penalty 过滤；本轮不接实时 API/VPS、不做自动下注、不进入前端，只验证 GER-only 信号的失败 fold 是否来自特定历史赛季/窗口
HistoricalRecommendationBacktestOptions 新增 final_answer_segment_season_ids；历史 slice 生成候选时把 slice metadata.season 写入 candidate.metadata_json.season_id；segment penalty 仅在 pass_type/mode/competition/season/概率/赔率条件同时匹配时生效；默认 season_ids 为空，既有默认路径不变
historical backtest CLI 新增 --final-answer-segment-seasons；historical_final_answer_segment_penalty_grid 新增 season_groups、candidate season_ids、target_summary season 维度与 --season-group；rolling admission 在 candidate backtest options、summary 与 report 中传递 candidate_season_ids
新增/更新 deterministic tests 覆盖：segment penalty 的 season 匹配/不匹配；grid options/CLI 能传递 season_group 并在 report best_candidate 中回显 season_ids；rolling admission 继续兼容旧 candidate 默认 season_ids
生成 GER-only focused grid 报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_only_grid_v1.json；report_key=historical_final_answer_segment_penalty_grid:54e91b36dfa5bb2f；candidate_count=10；accepted_count=10；rejected_count=0
GER-only best candidate：GER_BUNDESLIGA / 3x1 / single / strength=0.02 / max_average_leg_decimal_odds=1.30；penalty_option_count=5；final hits=25/30；hit_rate=0.8333333333333334；ROI=-0.034539264666666604；profit_loss=-2.0723558799999964；ROI delta=+0.051691999999999995；profit/loss delta=+3.10152
生成 GER-only rolling admission report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_only_rolling_admission_v1.json；report_key=historical_final_answer_segment_penalty_rolling_admission:a3f5bb31bbd09a43；status=shadow_only；candidate_profile_allowed=false；failed_fold_count=4
GER-only failed folds：season:2020-2021、season:2022-2023、rolling_window:1、rolling_window:2；这些 fold 无命中率回撤且 Brier/log-loss/calibration 改善，但 ROI/P&L 为负；说明仅按联赛过滤还不能 promotion
生成 season-aware focused grid 报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_season_aware_grid_v1.json；report_key=historical_final_answer_segment_penalty_grid:44c5a6eaf19c8279；candidate_count=30；accepted_count=30；rejected_count=0
season-aware best candidate：GER_BUNDESLIGA / 3x1 / single / seasons=2021-2022,2023-2024,2024-2025 / strength=0.02；penalty_option_count=3；final hits=25/30；hit_rate=0.8333333333333334；ROI=-0.015897931333333268；profit_loss=-0.953875879999996；ROI delta=+0.07033333333333333；profit/loss delta=+4.220000000000001；Brier/log-loss/calibration 均改善
生成 season-aware rolling admission report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_season_aware_rolling_admission_v1.json；report_key=historical_final_answer_segment_penalty_rolling_admission:10639a7c285c4066；status=accepted；candidate_profile_allowed=true；shadow_allowed=true；failed_fold_count=0
season-aware admission：overall final hits 23/30 -> 25/30；changed_final_answer_count=2；harm_count_vs_baseline=0；active_competition_fold_count=1；active_season_fold_count=3；active_rolling_fold_count=4；active folds 全部 passed，其中 2021-2022 与 rolling_window:1/2 为中性，2023-2024、2024-2025 与 rolling_window:3/4 贡献改善
关键判断：season-aware 证明确认前一轮泄漏来自早期历史赛季/窗口，且 fold gate 可把有害段剔除；但直接枚举历史 season_ids 存在后视偏差，不能作为生产默认。下一阶段应把该证据转化为 forward-safe 的 season-phase/regime 特征或滚动准入规则，并要求绝对 ROI/holdout 表现继续改善后再进入 runtime profile proposal
README 更新 GER-only 与 season-aware grid/admission 命令、报告路径、report_key、核心指标与后视偏差说明；该能力属于“core final-answer accuracy tuning / season-aware historical evidence / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-215 当前落地能力：

```text
按 V3.1-214 结论把 season-aware 历史证据转换为 forward-safe competition season index / regime 过滤；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改生产默认，只验证不枚举未来 season_ids 的最终答案仲裁调参路径
HistoricalRecommendationBacktestOptions 新增 final_answer_segment_min_competition_season_index、final_answer_segment_max_competition_season_index 与 competition_season_index_by_slice_id；suite backtest 会为每个 competition 按赛季顺序生成 1-based season index，并写入 candidate.metadata_json.competition_season_index、prior_competition_season_count、season_start_year
segment penalty 生效条件新增 competition season index 匹配；默认 min/max 为空，既有默认路径不变；historical backtest CLI 新增 --final-answer-segment-min-competition-season-index 与 --final-answer-segment-max-competition-season-index
historical_final_answer_segment_penalty_grid 新增 min/max competition season index 网格维度、candidate/spec/report/target_summary 回显与 CLI 参数 --min-competition-season-index-values、--max-competition-season-index-values
rolling admission 新增 suite-level competition season index context；overall、competition、season、rolling-window folds 都复用全局 suite index map，避免 fold subset 把 2023-2024 误当作折内第 1 季
新增/更新 deterministic tests 覆盖：segment penalty min index 匹配/不匹配；grid options/CLI 能传递 min competition season index；rolling admission 在单赛季/滚动子折中保留全局 index map，且 candidate backtest options 携带 min_competition_season_index
生成 GER regime grid 报告：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_grid_v1.json；report_key=historical_final_answer_segment_penalty_grid:f613460c80a0f11b；candidate_count=30；accepted_count=30；rejected_count=0
GER regime best candidate：GER_BUNDESLIGA / 3x1 / single / min_competition_season_index=4 / strength=0.02；season_ids=[]；penalty_option_count=2；final hits=25/30；hit_rate=0.8333333333333334；ROI delta=+0.07033333333333333；profit/loss delta=+4.220000000000001；Brier/log-loss/calibration 均改善；absolute ROI=-0.015897931333333268
生成 GER regime rolling admission report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_rolling_admission_v1.json；report_key=historical_final_answer_segment_penalty_rolling_admission:9008173a87654d81；status=accepted；candidate_profile_allowed=true；shadow_allowed=true；failed_fold_count=0
GER regime admission：overall final hits 23/30 -> 25/30；changed_final_answer_count=2；harm_count_vs_baseline=0；active_competition_fold_count=1；active_season_fold_count=2；active_rolling_fold_count=2；active folds 全部 passed，其中 2023-2024、2024-2025 season folds 与 rolling_window:3/4 贡献改善
关键判断：competition season index 已把上一轮后视 season_id 过滤转换成可前向计算的 regime 特征，并通过 rolling admission；但绝对 ROI 仍略负，且样本只覆盖 30 个 final answers，因此下一阶段仍不应直接写 default production profile，应进入 runtime profile proposal/holdout 扩样，要求绝对 ROI、跨联赛稳健性和周期质量门禁继续改善
README 更新 GER regime grid/admission 命令、报告路径、report_key、核心指标与全局 season index 口径说明；该能力属于“core final-answer accuracy tuning / forward-safe regime evidence / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-216 当前落地能力：

```text
按 V3.1-215 结论新增 final-answer segment penalty production proposal / holdout gate；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只把 accepted GER regime 证据转成可审计 runtime-profile 候选，并用绝对 ROI 门禁阻断生产晋级
新增 historical_final_answer_segment_penalty_production_proposal 模块：读取 segment penalty grid report 与 rolling admission report，校验 source key 链路、grid candidate、rolling admission、forward-safe regime filter、无 explicit season_ids、final-answer/fold/ROI/P&L/Brier/log-loss/calibration/harm 门禁
新增模型：HistoricalFinalAnswerSegmentPenaltyProductionProposalOptions、HistoricalFinalAnswerSegmentPenaltyProductionProposalCheck、HistoricalFinalAnswerSegmentPenaltyRuntimeRuleProposal、HistoricalFinalAnswerSegmentPenaltyProductionProposalReport；状态包括 runtime_profile_proposal_ready、holdout_only、blocked
新增 CLI：nutmeg-recommendation-final-answer-segment-penalty-production-proposal；支持 grid-report、rolling-admission-report、report output、profile output、proposal id/profile version、final-answer/changed/penalty option/fold/ROI/P&L/absolute ROI/harm/source-linkage/season-id/regime 门禁与 no-fail-process
proposal_profile_set_json 新增 final_answer_segment_penalty_rules artifact；规则携带 final_answer_segment_penalty_strength、pass_types、modes、competition_ids、min/max competition season index、source report keys、evidence_json 与 rollback_conditions；artifact 明确 production_recommendation_changed=false
新增 deterministic tests 覆盖：绝对 ROI 过线时 runtime_profile_proposal_ready；绝对 ROI 不足时 holdout_only 但仍生成 holdout candidate；explicit season_ids 阻断；rolling admission 失败阻断；CLI options/loader/main 与 profile output 正常
生成 GER regime production proposal report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_production_proposal_v1.json；report_key=historical_final_answer_segment_penalty_production_proposal:4adacd774931b31d；status=holdout_only；runtime_profile_proposal_allowed=false；holdout_candidate_allowed=true；proposal_count=1
生成 GER regime runtime profile candidate artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_runtime_profile_candidate_v1.json；profile_version=v3_1_final_answer_segment_penalty_ger_regime_runtime_profile_candidate_v1；final_answer_segment_penalty_rules=1；proposed_production_enabled=false；holdout_candidate_enabled=true
proposal evidence：source_grid=historical_final_answer_segment_penalty_grid:f613460c80a0f11b；source_rolling_admission=historical_final_answer_segment_penalty_rolling_admission:9008173a87654d81；source_candidate=historical_final_answer_segment_penalty_candidate:ee7567be7db20dca；final hits 23/30 -> 25/30；hit-rate delta=+0.06666666666666665；ROI delta=+0.07033333333333333；profit/loss delta=+4.220000000000001；harm=0；failed folds=0
唯一失败 check：candidate_roi，actual=-0.015897931333333268，threshold=0.0；因此该 rule 被允许进入 expanded holdout validation，但不能进入 runtime production proposal 或 default profile
关键判断：这一步把“看起来有效”的调参候选放进了硬门禁，而不是让它直接上线；下一阶段应扩大真实历史/联赛 holdout 或实现 runtime replay/smoke，只有当绝对 ROI、跨样本稳定性与 cycle quality gate 同时过线，才继续推进 runtime profile promotion
README 更新 production proposal gate 命令、报告路径、profile artifact、report_key、holdout_only 原因与不启用默认生产配置说明；该能力属于“core final-answer accuracy governance / holdout candidate artifact / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-217 当前落地能力：

```text
按 V3.1-216 结论新增 final-answer segment penalty runtime replay / shadow smoke；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只验证 holdout runtime profile artifact 能否通过运行时风格加载器复现历史证据
新增 historical_final_answer_segment_penalty_runtime_replay 模块：读取 runtime profile candidate、production proposal report 或 rule-set JSON，提取 final_answer_segment_penalty_rules，并把 rule constraints 映射回 HistoricalRecommendationBacktestOptions 后与 baseline suite 做对比
新增模型：FinalAnswerSegmentPenaltyRuntimeRule、FinalAnswerSegmentPenaltyRuntimeRuleSet、HistoricalFinalAnswerSegmentPenaltyRuntimeReplayOptions、HistoricalFinalAnswerSegmentPenaltyRuntimeReplayCheck、HistoricalFinalAnswerSegmentPenaltyRuntimeReplayReport；状态包括 runtime_replay_passed、holdout_replay_passed、shadow_replay_failed、disabled、no_rules、blocked
新增 CLI：nutmeg-recommendation-final-answer-segment-penalty-runtime-replay；默认不开启 shadow replay，必须显式传入 --enable-shadow-replay；支持 rule ids、suite manifest、runtime/holdout/proposal gate、final-answer/changed/penalty option/ROI/P&L/Brier/log-loss/calibration/harm 门禁与 no-fail-process
loader 支持三类输入：直接 profile artifact 的 final_answer_segment_penalty_rules、production proposal report 的 proposal_profile_set_json、以及 rule-set JSON 的 rules fallback；这让 proposal -> profile -> runtime replay 的证据链可复用
新增 deterministic tests 覆盖：runtime ROI 过线时 runtime_replay_passed；绝对 ROI 不足时 holdout_replay_passed；未显式 enable 时 disabled；loader 可读取 proposal_profile_set_json；CLI options、main output 与 report 写出正常
生成 GER regime runtime replay report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_runtime_replay_v1.json；report_key=historical_final_answer_segment_penalty_runtime_replay:92d04fa3b0fa6c7e；status=holdout_replay_passed；runtime_replay_allowed=false；holdout_replay_allowed=true
runtime replay 结果：source_rule_profile_version=v3_1_final_answer_segment_penalty_ger_regime_runtime_profile_candidate_v1；rule_count=1；selected_rule_count=1；final_answer_count=30；changed_final_answer_count=2；penalty_option_count=2；baseline/candidate final hits=23/25；final_hit_delta=+2；hit_rate_delta=+0.06666666666666665；ROI delta=+0.07033333333333333；profit/loss delta=+4.220000000000001；Brier/log-loss/calibration deltas 均改善；harm_count_vs_baseline=0；improvement_count_vs_baseline=2
唯一失败 check 仍是 candidate_roi，actual=-0.015897931333333268，threshold=0.0；因此 runtime replay 只允许 holdout_replay，不允许 runtime production replay
关键判断：GER regime penalty 现在不仅有 grid、rolling admission 和 production proposal 证据，还能被运行时风格 profile loader 复现；但绝对 ROI 未过 0，因此继续严格停留在 holdout，不写 default profile、不进入普通用户最终答案
README 更新 runtime replay 命令、报告路径、report_key、核心指标与 holdout_only 原因；该能力属于“core final-answer accuracy governance / runtime-style holdout replay / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-218 当前落地能力：

```text
按 V3.1-217 结论把 final-answer segment penalty runtime replay 接入 persisted benchmark quality gate 与 benchmark cycle preset；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只让周期门禁能消费 holdout replay evidence
benchmark_quality_gate 新增 final_answer_segment_penalty_runtime_replay evidence：report path、require flag、holdout/runtime allowed gate、rule/selected-rule/final-answer/changed/penalty-option/hit/ROI/P&L/Brier/log-loss/calibration/harm/no-production-change/no-public-change 阈值
新增 preset：final_answer_segment_penalty_ger_regime_holdout_v1；该预设指向 GER regime runtime replay report，并要求 holdout_replay_allowed=true、runtime_replay_allowed 不强制为 true、rule_count>=1、selected_rule_count=1、final_answer_count>=30、changed_final_answer_count>=2、penalty_option_count>=2、hit/ROI/P&L delta 不回撤、harm_count=0，同时不要求 absolute candidate_roi >= 0
benchmark_quality_gate summary 新增 final_answer_segment_penalty_runtime_replay_* 字段：preset、present、report key/status、runtime_allowed、holdout_allowed、profile version、rule count、selected rule count、final answer count、changed count、penalty option count、hit delta、hit-rate delta、candidate ROI、ROI delta、P&L delta、harm count、failed checks、production/public change flags
benchmark_cycle 新增 gate-final-answer-segment-penalty-runtime-replay-* CLI 参数并透传至 RecommendationBenchmarkQualityGateOptions；cycle summary 与 cycle key 现在携带该 preset，避免带 holdout replay evidence 的周期结果与普通 cycle 混淆
新增/更新 deterministic tests 覆盖：quality gate 可消费 segment penalty runtime replay；缺失/回撤的 replay 会阻断；从 options 路径加载 replay report；CLI options 映射；preset 映射；cycle summary 和 cycle key 透传 preset 与 replay metrics
生成 benchmark gate smoke report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_runtime_replay_benchmark_gate_smoke_v1.json；gate_key=recommendation_benchmark_quality_gate:all:any；status=passed；failed_checks=[]；final_answer_segment_penalty_runtime_replay_status=holdout_replay_passed；holdout_allowed=true；runtime_allowed=false
smoke 使用真实 replay evidence：report_key=historical_final_answer_segment_penalty_runtime_replay:92d04fa3b0fa6c7e；final_answer_count=30；hit_count_delta=+2；ROI delta=+0.07033333333333333；profit/loss delta=+4.220000000000001；harm_count=0；underlying replay failed_checks=[candidate_roi]
关键判断：GER regime penalty 现在进入周期质量门禁视野，但 gate 只承认它是 holdout evidence；绝对 ROI 未过线之前仍不能写 default profile、不能进入 runtime production rule、不能成为普通用户最终答案默认路径
README 更新 benchmark gate preset、cycle preset、smoke artifact、report_key 与 holdout-only 解释；该能力属于“periodic quality gate hardening / final-answer holdout evidence / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-219 当前落地能力：

```text
按 V3.1-218 结论把 final-answer segment penalty runtime replay 从 30-slice core holdout 扩大到 core + expanded A-league combined holdout；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只扩大核心推荐调参证据的样本面
historical_final_answer_segment_penalty_runtime_replay CLI 的 --suite-manifest 改为可重复参数；加载器会合并多个 suite manifest 的 slice paths/warnings，并在 report summary_json.suite_manifests 中保留每个 manifest 的 suite_id、manifest_path、slice_count 与 resolved paths；单 manifest 情况继续保留旧 summary_json.suite_manifest 兼容字段
新增 deterministic test 覆盖：runtime replay 可以接受两个 suite manifest 并合并为同一批 historical slices，同时保留两个 manifest_results
生成 combined holdout runtime replay report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_penalty_ger_regime_runtime_replay_multi_manifest_v1.json；report_key=historical_final_answer_segment_penalty_runtime_replay:1d4acf9275a81d72；status=holdout_replay_passed；runtime_replay_allowed=false；holdout_replay_allowed=true
combined holdout 结果：core 30 slices + expanded rolling-window 210 slices，共 240 final answers；baseline/candidate final hits=171/173；final_hit_delta=+2；hit_rate_delta=+0.008333333333333304；ROI delta=+0.005812672176308535；profit/loss delta=+4.219999999999999；Brier/log-loss/calibration deltas 均改善；harm_count_vs_baseline=0；improvement_count_vs_baseline=2
唯一失败 replay check 仍是 candidate_roi，actual=-0.04839927807162534，threshold=0.0；因此更大样本验证了该规则在当前样本上不伤害最终答案，但仍不能进入 runtime production rule 或 default profile
生成 combined benchmark gate artifact：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_penalty_runtime_replay_benchmark_gate_v1.json；gate_key=recommendation_benchmark_quality_gate:all:any；status=passed；failed_checks=[]；final_answer_segment_penalty_runtime_replay_final_answer_count=240；holdout_allowed=true；runtime_allowed=false；underlying replay failed_checks=[candidate_roi]
关键判断：扩大 holdout 后方向仍然是“正增量但绝对收益不够”；下一阶段不应做生产 profile promotion，而应继续寻找能提高 absolute ROI 的分联赛/赔率段 value guard、概率校准或最终答案仲裁权重
README 更新 multi-manifest replay 命令、combined holdout 报告、benchmark gate artifact、report_key 与 holdout-only 解释；该能力属于“core recommendation quality governance / expanded holdout validation / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-220 当前落地能力：

```text
按 V3.1-219 结论继续追查 combined holdout 的绝对 ROI 卡点；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只把 final-answer negative-ROI loss diagnostics 扩大到 core + expanded combined surface
historical_loss_diagnostics CLI 的 --suite-manifest 改为可重复参数；加载器会合并多个 suite manifest 的 slice paths/warnings，并在 report summary_json.suite_manifests 中保留每个 manifest 的 suite_id、manifest_path、slice_count 与 resolved paths；单 manifest 情况继续保留旧 summary_json.suite_manifest 兼容字段
historical_loss_diagnostics summary 补齐策略与候选池参数：strategy、min_probability、min_data_quality_score、max_outcomes_per_fixture、upset_threshold、candidate_fixture_limit、max_candidates_per_fixture、scenario_candidate_fixture_buffer、short-price guard/soft-penalty 参数；避免不同候选池诊断共用不可区分的 report key
新增 deterministic test 覆盖：loss diagnostics 可以接受两个 suite manifest 并合并为同一批 historical slices，同时保留两个 manifest_results
生成 combined negative-ROI loss diagnostics report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_negative_roi_loss_diagnostics_v1.json；report_key=historical_final_answer_loss_diagnostics:b40863827184c835；status=generated
诊断口径：core 30 slices + expanded rolling-window 210 slices，共 240 input slices；pass_types=1x1-8x1；modes=single/multiple；unit_stake=2；max_budget=20；candidate_fixture_limit=12；max_candidates_per_fixture=3；scenario_candidate_fixture_buffer=4；derive_market_context_signals=true；negative_roi_only=true
诊断结果：过滤到 140 negative-ROI final answers、208 selected legs、93 missed legs；negative ROI competitions=ENG_CHAMPIONSHIP、EPL、ESP_LA_LIGA、FRA_LIGUE_2、GER_2_BUNDESLIGA、GER_BUNDESLIGA、ITA_SERIE_A、ITA_SERIE_B
主要 loss groups：ENG_CHAMPIONSHIP:1x1:single final_answer_sample_size=29、hit_rate=0.5172413793103449、profit_loss=-11.060000000000002、ROI=-0.19068965517241382；ITA_SERIE_B:2x1:multiple final_answer_sample_size=17、hit_rate=0.5294117647058824、profit_loss=-9.263999999999996、ROI=-0.0681176470588235；ITA_SERIE_B 2024-2025 profit_loss=-8.193599999999996；GER_2_BUNDESLIGA 2023-2024 ROI=-0.47333333333333333
主要 missed-leg cluster：ITA_SERIE_B negative-edge / fragile-favorite 段 selected_leg_count=81、missed_leg_count=47、leg_hit_rate=0.41975308641975306、average_probability=0.42325862406623477、average_decimal_odds=2.4504938271604937、average_model_edge=-0.02814340644544755、average_favorite_fragility_score=0.37690740740740747；ITA_SERIE_B market_favorite_missed missed_leg_count=24、average_probability=0.5192994790322595、odds=1.8166666666666662、edge=-0.03452643456463474；ENG_CHAMPIONSHIP edge_negative selected_leg_count=33、missed_leg_count=16、average_probability=0.5712904009828993、odds=1.745757575757576、edge=-0.030402332244693346
关键判断：combined 样本显示当前 ROI 卡点已经从早期 top-league short-price favorite 扩展到 ITA_SERIE_B / ENG_CHAMPIONSHIP 的 medium-price、negative-edge、fragile-favorite 段；下一阶段应优先做 competition-scoped value guard / final-answer arbitrator weight experiment，并先作为 holdout evidence 验证，不做 global hard filter、不做 production profile promotion
README 更新 multi-manifest loss diagnostics 命令、combined report、report_key 与核心 loss-driver 结论；该能力属于“core recommendation quality diagnostics / expanded loss-driver evidence / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-221 当前落地能力：

```text
按 V3.1-220 loss-driver 结论验证 ITA_SERIE_B / ENG_CHAMPIONSHIP medium-price negative-edge final-answer quality-signal penalty；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只生成 holdout gate evidence 并明确拒绝边界
historical_quality_gate CLI 的 --suite-manifest 改为可重复参数；加载器会合并多个 suite manifest 的 slices/warnings，并在 gate summary_json.suite_manifests 中保留每个 manifest 的 suite_id、manifest_path、slice_count 与 resolved paths；单 manifest 情况继续保留旧 summary_json.suite_manifest 兼容字段
新增 deterministic test 覆盖：historical suite gate 可以接受两个 suite manifest 并合并为同一批 historical slices，同时保留两个 manifest bundles；既有单 manifest 行为保持兼容
expanded-only ITA_SERIE_B s0.04 gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ita_serie_b_medium_price_negative_edge_quality_signal_s004_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:f2fbb5efe5be6e51；passed=true；suite_status=improved；final_hit_rate_delta=+0.01904761904761909；ROI delta=+0.015527678571428572；profit_loss_delta=+10.4528；Brier/log-loss/calibration deltas 均改善；candidate_roi=-0.0007583333333333286
expanded-only ITA_SERIE_B s0.08 absolute ROI gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ita_serie_b_medium_price_negative_edge_quality_signal_s008_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:9a943d676d73dd08；failed_checks=[candidate_roi]；增强 strength 没有进一步改变结果，candidate_roi 仍为 -0.0007583333333333286
combined ITA_SERIE_B s0.04 gate：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_medium_price_negative_edge_quality_signal_s004_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:6020922b088e1f60；status=failed；suite_status=improved；failed_checks=[candidate_roi]；final_hit_rate_delta=+0.016666666666666607；ROI delta=+0.014017427253866812；profit_loss_delta=+10.4528；Brier/log-loss/calibration deltas 均改善；candidate_final_hit_rate=0.7；candidate_roi=-0.008001802090395471；final_answer_changed_count=59
combined ENG_CHAMPIONSHIP s0.04 gate：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_eng_championship_medium_price_negative_edge_quality_signal_s004_gate_v1.json；gate_key=historical_recommendation_suite_quality_gate:cb74051b937a6f8a；status=failed；suite_status=mixed；failed_checks=[suite_status, roi_delta, profit_loss_delta]；candidate_final_hit_rate=0.7041666666666667；candidate_roi=0.00838336890855458；final_hit_rate_delta=+0.02083333333333337；但 ROI delta=-0.008787113052229746、profit_loss_delta=-6.575800000000004，因此不能接受
关键判断：ITA_SERIE_B penalty 是真实有用的相对改善信号，但 combined absolute ROI 仍未过 0，不能晋级；ENG_CHAMPIONSHIP wider guard 虽然把绝对 ROI 变正，但相对当前 baseline 亏损，违反 accuracy-first / ROI no-regression gate；下一阶段应做更窄 ITA_SERIE_B score/odds/probability 子区间或候选替代审计，而不是修改 default profile
README 更新 multi-manifest suite gate 命令、ITA_SERIE_B/ENG_CHAMPIONSHIP gate artifact、gate_key、失败原因与非晋级结论；该能力属于“core recommendation quality gate / competition-scoped value guard evidence / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-222 当前落地能力：

```text
按 V3.1-221 结论继续收窄 ITA_SERIE_B medium-price negative-edge 子区间；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只增强 holdout profile grid 的 combined evidence 能力并保留拒绝结论
final_answer_quality_signal_profile_grid CLI 的 --suite-manifest 改为可重复参数；加载器会合并多个 suite manifest 的 slices/resolved paths/warnings，并在 report summary_json.suite_manifests 中保留每个 manifest 的 suite_id、manifest_path、slice_count 与 resolved paths；单 manifest 情况继续保留旧 summary_json.suite_manifest 兼容字段
final_answer_quality_signal_profile_grid 新增 --min-candidate-roi / min_candidate_roi；候选若低于绝对 ROI floor，会产生 quality_signal_profile:candidate_roi_below_floor；grid summary 与 candidate summary 均记录该阈值，避免仅因相对改善就误晋级负收益候选
新增 deterministic tests 覆盖：profile grid 可以接受两个 suite manifest 并合并为同一批 historical slices；CLI 参数映射 min_candidate_roi；低于绝对 ROI floor 的候选会被拒绝
生成 combined ITA_SERIE_B narrow partial grid report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_partial3_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:4c2cb3b36cd64c8c；slice_count=240；suite_manifest_count=2；total_grid_candidate_count=4；candidate_count=3；accepted_count=0；rejected_count=3；cache_hit_count=3；cache_miss_count=0
baseline 结果：baseline_suite_status=improved；baseline_candidate_final_hit_rate=0.7041666666666667；baseline_candidate_roi=0.0173867918452381；baseline_candidate_profit_loss=11.683924120000004
已测窄区间候选：ITA_SERIE_B，probability [0.48,0.58] 或 [0.50,0.58]，decimal_odds [1.75,2.00] 或 [1.75,2.20]，model_edge <= -0.03，score_max=1.0，strength=0.04，min_candidate_roi=0；三个候选均 candidate_roi=0.013402247964601778、candidate_profit_loss=9.086724120000005、candidate_final_hit_rate=0.7041666666666667
拒绝原因：三个候选均被 quality_signal_profile:roi_regressed、quality_signal_profile:profit_loss_regressed、quality_signal_profile:objective_improvement_missing 拦下；相对 baseline 的 roi_delta=-0.003984543880636323、profit_loss_delta=-2.597199999999999，即使绝对 ROI 为正，也不能牺牲现有 baseline 收益
执行备注：完整 4-candidate grid 的最后一个候选在本地长跑中耗时异常，因此保留前 3 个缓存命中候选的 partial report；该证据足以说明当前窄化方向没有超过 baseline，后续若继续应先优化 baseline cache/分批 runner，而不是扩大同类 profile 搜索
README 更新 combined profile-grid 命令、partial report、report_key、拒绝原因与非晋级结论；该能力属于“core recommendation quality governance / final-answer profile grid holdout / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-223 当前落地能力：

```text
按 V3.1-222 执行备注修复 profile grid baseline 重算瓶颈；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只提升历史 profile-grid 调参/复跑效率
final_answer_quality_signal_profile_grid 新增 baseline cache：HistoricalFinalAnswerQualitySignalProfileGridOptions.baseline_cache_dir、read_baseline_cache、write_baseline_cache；CLI 新增 --baseline-cache-dir、--no-baseline-cache-read、--no-baseline-cache-write
baseline cache 与 candidate cache 分离；cache key 使用 historical slice id/as_of_time、baseline backtest options、baseline/candidate optimizer profile、default competition profile version；缓存文件写为 baseline-<digest>.json，避免和候选 cache 混淆
grid report 新增 baseline_cache_key、baseline_cache_status、baseline_cache_written；summary_json 与 grid summary 也记录 baseline cache dir/read/write 状态；merge report 将 baseline cache 状态显式置为 disabled/None，避免合并产物误称为一次真实 cache hit
candidate cache key 排除 baseline cache 配置，保证启用/关闭 baseline cache 不会无意义地打碎 candidate cache；candidate cache 仍然受 baseline_suite_key 与 candidate/profile/gate 选项约束
新增 deterministic tests 覆盖：第一次 profile grid 写入 baseline cache 并标记 miss/written；第二次复用同一 cache 并标记 hit/not written；CLI 参数正确映射 baseline cache dir/read/write 开关
本地 CLI smoke：euro_2024_knockout_suite 第一次运行 baseline_cache_status=miss、baseline_cache_written=true、candidate cache miss=1；第二次运行 baseline_cache_status=hit、baseline_cache_written=false、candidate cache hit=1；baseline_cache_key=historical_final_answer_quality_signal_profile_baseline_cache:ca172ee8f30117ed；baseline_suite_key=historical_recommendation_backtest_suite:54183363c079477e
README 更新 baseline cache 用法、smoke artifact 与边界说明；该能力属于“historical profile-grid efficiency / core tuning infrastructure / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-224 当前落地能力：

```text
按 V3.1-223 继续增强 profile grid 分批恢复能力；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只提升长 grid 中断后的补跑/合并可控性
HistoricalFinalAnswerQualitySignalProfileGridOptions 新增 candidate_indices；CLI 新增 --candidate-indices，支持显式传入候选 index 列表；当 candidate_indices 非空时优先按显式 index 选择候选，而不是 candidate_start_index/candidate_limit 连续范围
candidate cache key 排除 candidate_indices，保证同一候选在 range 模式或 explicit_indices 模式下复用同一 candidate cache；baseline cache 继续独立复用
单次 grid report summary 新增 candidate_selection_mode、requested_candidate_indices、unmatched_requested_candidate_indices、missing_candidate_indices、next_candidate_start_index、is_full_grid；partial report 现在能直接说明哪些 index 已完成、哪些仍缺失
merge report 的 grid summary 会保留合并后的 candidate_indices，并继续输出 missing_candidate_indices / duplicate_candidate_indices / is_full_grid，用于判断 batch 是否完整
新增 deterministic tests 覆盖：显式 candidate_indices 只执行指定 index；报告写出 explicit_indices 选择模式、requested/missing/is_full_grid；CLI 参数映射 candidate_indices
本地 CLI smoke：euro_2024_knockout_suite 使用 --candidate-indices 0；报告 candidate_selection_mode=explicit_indices、requested_candidate_indices=[0]、candidate_indices=[0]、baseline_cache_status=hit、candidate cache hit=1、cache_miss_count=0
README 更新 explicit candidate index 恢复命令、smoke artifact 与报告字段说明；该能力属于“historical profile-grid recovery / resumable tuning infrastructure / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-225 当前落地能力：

```text
按 V3.1-224 的恢复能力补齐 V3.1-222 遗留的 ITA_SERIE_B narrow grid 缺口；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只补全 holdout evidence 并关闭低收益调参分支
使用 --candidate-indices 3 补跑 configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_index3_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:e0accc99d7b0b7eb；candidate_selection_mode=explicit_indices；requested_candidate_indices=[3]；candidate_indices=[3]；candidate_count=1；accepted_count=0；rejected_count=1
补跑使用 combined baseline cache：baseline_cache_status=miss；baseline_cache_written=true；baseline cache 文件为 tmp/quality-signal-profile-grid-cache/ita-serie-b-narrow-combined-baseline-v1/baseline-8e462ffd054f36a1.json；candidate cache 从 3 个文件补齐到 4 个文件
index 3 结果：ITA_SERIE_B，probability [0.50,0.58]，decimal_odds [1.75,2.20]，model_edge <= -0.03，score_max=1.0，strength=0.04；candidate_roi=0.013402247964601778；candidate_profit_loss=9.086724120000005；candidate_final_hit_rate=0.7041666666666667；roi_delta=-0.003984543880636323；profit_loss_delta=-2.597199999999999
拒绝原因：quality_signal_profile:roi_regressed、quality_signal_profile:profit_loss_regressed、quality_signal_profile:objective_improvement_missing；即使绝对 ROI 为正，仍低于当前 baseline 的 candidate_roi=0.0173867918452381 和 candidate_profit_loss=11.683924120000004
合并 partial3 + index3 生成完整报告：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_full_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:071443ec74add7db；total_grid_candidate_count=4；candidate_count=4；accepted_count=0；rejected_count=4；candidate_indices=[0,1,2,3]；missing_candidate_indices=[]；duplicate_candidate_indices=[]；is_full_grid=true；warnings=[]
完整 grid 结论：4 个窄区间候选结果完全一致，均因 ROI/profit/objective gate 失败；当前 ITA_SERIE_B narrow medium-price negative-edge quality-signal direction 正式关闭，不再扩大同类 grid，下一步应转向 materially different feature/scoring hypothesis 或其他联赛/赔率段候选
README 更新 index3 补跑、full merge artifact、report_key、完整拒绝结论与关闭该分支的说明；该能力属于“holdout evidence completion / tuning branch closure / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-226 当前落地能力：

```text
按 V3.1-225 结论转向 materially different hypothesis：不再扩大 ITA_SERIE_B narrow penalty grid，而是用 combined core + expanded A-league holdout 审计 medium-price negative-edge 错腿的替换空间；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只生成候选替换与重排证据
marginal_contribution_diagnostics / candidate-replacement-audit CLI 的 --suite-manifest 改为可重复参数；加载器会合并多个 suite manifest 的 historical slices/resolved paths/warnings，并在 report summary_json.suite_manifests 中保留每个 manifest 的 suite_id、manifest_path、slice_count 与 resolved paths；单 manifest 情况继续保留旧 summary_json.suite_manifest 兼容字段
新增 deterministic test 覆盖：candidate replacement audit 可以接受两个 suite manifest 并合并为同一批 historical slices，同时保留两个 manifest_results
生成 combined medium-price negative-edge replacement audit report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_audit_v1.json；report_key=historical_candidate_marginal_audit:72a403b5062990d7；slice_count=240；competition_count=13；final_answer_count=240；selected_leg_count=67；missed_leg_count=67；replacement_simulation_count=150；actual_replacement_opportunity_count=29；model_top_replacement_count=30
replacement audit 结果：current model-top replacement improves actual P/L in 12 cases、harms 0 cases、average_model_top_profit_loss_delta=1.556；hindsight actual-best average_profit_loss_delta=4.4446666666666665；average_model_top_hit_probability_delta=-0.03170013093001719；这说明 replacement opportunity 真实存在，但当前 ranking 仍保守并漏掉较高赔率的替代收益
生成 combined reranker diagnostic report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_diagnostics_v1.json；report_key=historical_replacement_reranker_diagnostics:370bc72b9f66d048；evaluated_item_count=27；rank_gap_item_count=26；average_rank_gap=1.7777777777777777；average_profit_loss_gap=3.2096296296296294
reranker diagnostic 结论：actual-best replacement 在 26/27 个机会中排在 model-top replacement 之后；actual-best 通常 lower probability、higher odds、higher risk，bias_counts 显示 actual_best_ranked_below_model_top=26、actual_best_higher_odds=20、actual_best_lower_probability=20；当前 replacement scorer 对 hit probability/risk 的惩罚过强
生成 combined replacement tolerance grid report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_tolerance_grid_v1.json；report_key=historical_replacement_reranker_tolerance_grid:f67b02ee584c14bf；threshold_count=4；profile_count=5；evaluated_candidate_count=20；profile_candidate_count=0；watchlist_count=12；rejected_count=4；best_candidate_key=null
tolerance grid 结果：没有候选达到 production promotion；在 -0.02 per-item expected hit-probability tolerance 下，多个 profile 能在 27 个机会中改善 4 个、harm 0、simulated actual-hit 从 10 提升到 11、average_profit_loss_delta_vs_model_top=0.15185185185185185，但仍属于 watchlist，因为它依赖 hit-probability tolerance 且样本不足
关键判断：replacement reranking 是比继续窄化 ITA_SERIE_B penalty 更有信息量的下一方向，但当前证据只能支持“segment-scoped guarded shadow / watchlist”，不能直接进入 default profile；下一阶段应把 controlled tolerance replacement reranker 做成严格 gate / shadow replay，要求 no harm、actual-hit 不回撤、ROI/P&L 改善和足够样本后再考虑 runtime profile candidate
README 更新 combined replacement audit、reranker diagnostic、tolerance grid 报告路径、report_key、核心指标与非生产结论；该能力属于“core final-answer replacement evidence / reranker watchlist / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-227 当前落地能力：

```text
按 V3.1-226 结论把 controlled tolerance replacement reranker 做成严格 shadow gate；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只把 watchlist evidence 转成 final-answer-level hard gate artifact
新增 replacement_reranker_shadow_gate 模块：读取 candidate replacement audit 与 tolerance grid report，指定 profile_id + hit_probability_delta_threshold，复用 pre-match reranker weight experiment 的选择逻辑，在 final_answer_key 粒度最多选择一个 replacement override，并比较 original / model-top replacement / shadow reranker replacement
新增模型：HistoricalReplacementRerankerShadowGateOptions、HistoricalReplacementRerankerShadowGateCheck、HistoricalReplacementRerankerShadowGateFinalAnswer、HistoricalReplacementRerankerShadowGateReport；状态包括 disabled、no_tolerance_candidate、shadow_gate_passed、shadow_gate_failed
新增 CLI：nutmeg-recommendation-replacement-reranker-shadow-gate；必须显式 --enable-shadow-gate 才运行；支持 audit-report、tolerance-grid-report、profile-id、hit-probability threshold、sample/changing/hit/P&L/ROI/harm/average hit-probability tolerance/source tolerance candidate/source audit/no production change 门禁与 no-fail-process
新增 deterministic tests 覆盖：watchlisted tolerance candidate 在 no-harm、hit/P&L/ROI 改善时通过 shadow gate；未启用 feature flag 时 disabled；CLI 参数映射、输出文件与失败退出正常；新增 entry point 与 __init__ export
生成 combined replacement reranker shadow gate report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_shadow_gate_quality_edge_v1.json；report_key=historical_replacement_reranker_shadow_gate:02fc9b2156cc8b88；status=shadow_gate_passed；passed=true
shadow gate 口径：source_audit=historical_candidate_marginal_audit:72a403b5062990d7；source_tolerance_grid=historical_replacement_reranker_tolerance_grid:f67b02ee584c14bf；source_tolerance_candidate=quality_edge_blend_v1:hit_probability_delta>=-0.02；source_tolerance_candidate_status=watchlist；eligible_item_count=27；shadow_final_answer_count=27
shadow gate 结果：changed_from_model_top_count=5；selected_model_top_count=22；selected_actual_best_count=0；model_top hits=10；shadow hits=11；hit_delta_vs_model_top_count=+1；replacement_leg_hit_delta_vs_model_top_count=+1；model_top_profit_loss=-15.1；shadow_profit_loss=-11.0；profit_loss_delta_vs_model_top=+4.1；roi_delta_vs_model_top=+0.07592592592592592；harm_count_vs_model_top=0；average_hit_probability_delta_vs_model_top=-0.007354632966171804
关键判断：quality_edge_blend_v1 在 controlled tolerance shadow gate 上通过，说明 reranker watchlist 具备进一步治理价值；但它仍来自 missed-leg diagnostic surface，不能直接变成生产 runtime profile。下一阶段应做 rolling/competition admission 或 expanded non-missed audit，确认该 gate 在非后视触发条件下仍 no-harm，再考虑 runtime profile candidate/proposal
README 更新 replacement reranker shadow gate 命令、报告路径、report_key、通过指标与“diagnostic/shadow only”边界；该能力属于“core final-answer replacement governance / controlled shadow gate / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-228 当前落地能力：

```text
按 V3.1-227 结论新增 rolling/competition admission，验证 controlled replacement reranker shadow gate 不只是整体样本偶然有效；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只做折内准入治理
新增 replacement_reranker_shadow_admission 模块：读取 candidate replacement audit 与 tolerance grid report，复用 replacement_reranker_shadow_gate 在 overall、competition、season、rolling_window folds 中重新计算 shadow evidence；fold 内不依赖已裁剪的 shadow report，而是按 fold audit 重新跑 gate
新增模型：HistoricalReplacementRerankerShadowAdmissionOptions、HistoricalReplacementRerankerShadowAdmissionCheck、HistoricalReplacementRerankerShadowAdmissionFold、HistoricalReplacementRerankerShadowAdmissionReport；状态包括 accepted、shadow_only、rejected；accepted 仅表示 runtime_profile_candidate_allowed，不写默认生产 profile
新增 CLI：nutmeg-recommendation-replacement-reranker-shadow-admission；支持 audit-report、tolerance-grid-report、profile-id、hit-probability threshold、overall/fold hit/P&L/ROI/harm/average hit-probability tolerance、active competition/season/rolling fold count、rolling-window slice count/step、no-production-change 与 no-fail-process
新增 deterministic tests 覆盖：active competition/season/rolling folds 全部通过时 accepted；fold 覆盖不足时 shadow_only；CLI 参数映射、输出文件与 main 正常；新增 entry point 与 __init__ export
生成 combined replacement reranker shadow admission report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_shadow_admission_quality_edge_v1.json；report_key=historical_replacement_reranker_shadow_admission:4fa36ac7a44baf41；status=accepted；runtime_profile_candidate_allowed=true；shadow_allowed=true
admission source chain：source_audit=historical_candidate_marginal_audit:72a403b5062990d7；source_tolerance_grid=historical_replacement_reranker_tolerance_grid:f67b02ee584c14bf；overall_shadow_gate=historical_replacement_reranker_shadow_gate:a66672be3e4da117；profile_id=quality_edge_blend_v1；hit_probability_delta_threshold=-0.02
overall admission 结果：shadow_final_answer_count=27；changed_from_model_top_count=5；hit_delta_vs_model_top_count=+1；replacement_leg_hit_delta_vs_model_top_count=+1；profit_loss_delta_vs_model_top=+4.1；roi_delta_vs_model_top=+0.07592592592592592；harm_count_vs_model_top=0；average_hit_probability_delta_vs_model_top=-0.007354632966171804
fold admission 结果：fold_count=23；active_fold_count=11；failed_fold_count=0；active_competition_fold_count=2；active_season_fold_count=3；active_rolling_fold_count=6；active folds 全部 passed，skipped folds 主要是没有发生 rerank change 的联赛/窗口，不计失败
关键判断：quality_edge_blend_v1 controlled tolerance reranker 已通过 overall + competition/season/rolling admission，可以保留为 runtime-profile candidate evidence；但触发面仍是 missed-leg audit，因此下一阶段应做非后视触发转换：要么构建 pre-match eligible replacement surface，要么做 runtime profile proposal with explicit holdout-only gate，仍不能直接写 default profile
README 更新 shadow admission 命令、报告路径、report_key、overall/fold 指标与 runtime-profile candidate 边界；该能力属于“core final-answer replacement governance / rolling admission / runtime candidate evidence / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-229 当前落地能力：

```text
按 V3.1-228 结论把 replacement reranker 从 missed-leg 诊断触发面推进到真正赛前 eligible surface 验证；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只验证赛前面是否能安全启用，并补强拒绝门禁
replacement_reranker_shadow_gate 新增 original recommendation baseline 门禁：min_final_answer_hit_delta_vs_original、min_profit_loss_delta_vs_original、min_roi_delta_vs_original、max_harm_count_vs_original、min_average_hit_probability_delta_vs_original；默认不启用，只有显式传入阈值才参与检查，保持既有 missed-leg diagnostic 行为兼容
replacement_reranker_shadow_admission 同步新增 overall/fold original baseline 门禁，并在 fold report/summary_json 中记录 original hit/P&L/ROI/harm/average hit-probability delta；用于防止赛前面“相对 model-top 有改善，但伤害原始最终答案”的错误晋级
新增 deterministic tests 覆盖：shadow gate 会拦截伤害原始推荐的 rerank；admission 在 pre-match original baseline 失败时 rejected；CLI options 能正确映射 original baseline guard 参数
生成 pre-match surface replacement audit report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_audit_v1.json；report_key=historical_candidate_marginal_audit:7d42d0accf5d702f；target_filter.missed_legs_only=false
pre-match audit 结果：final_answer_count=240；selected_leg_count=128；missed_leg_count=67；replacement_simulation_count=335；actual_replacement_opportunity_count=65；model_top_replacement_count=67；model_top_actual_improvement_count=25；model_top_actual_harm_count=23；average_model_top_profit_loss_delta=-0.26567164179104474
生成 pre-match surface tolerance grid report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_reranker_tolerance_grid_v1.json；report_key=historical_replacement_reranker_tolerance_grid:bf4edee83bfbcfb0；profile_candidate_count=0；watchlist_count=12；best_candidate_key=null
生成 pre-match surface shadow gate report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_reranker_shadow_gate_quality_edge_v1.json；report_key=historical_replacement_reranker_shadow_gate:bed6f41f90788e80；status=shadow_gate_failed；passed=false
shadow gate 结果：shadow_final_answer_count=63；changed_from_model_top_count=9；相对 model-top hit_delta=+4、profit_loss_delta=+16.32、ROI delta=+0.1295238095238095、harm_count_vs_model_top=0；但相对 original final answer hit_delta=-4、profit_loss_delta=-5.539999999999999、ROI delta=-0.04396825396825396、harm_count_vs_original=19，因此被原始推荐基线拦截
生成 pre-match surface shadow admission report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_reranker_shadow_admission_quality_edge_v1.json；report_key=historical_replacement_reranker_shadow_admission:8a018cc726205159；status=rejected；runtime_profile_candidate_allowed=false；shadow_allowed=false
admission 结果：overall 同样在 original baseline 失败；fold_count=33；active_fold_count=20；failed_fold_count=18；active_competition_fold_count=4；active_season_fold_count=4；active_rolling_fold_count=12；失败原因集中在 overall_shadow_gate_passed、overall_final_answer_hit_delta_vs_original、overall_profit_loss_delta_vs_original、overall_roi_delta_vs_original、overall_harm_count_vs_original、failed_fold_count
关键判断：missed-leg diagnostic 上通过的 reranker 不能直接迁移到赛前 eligible surface；它相对 model-top 有改善，但会伤害当前原始最终答案。当前 profile 只保留为诊断证据和未来特征假设来源，不允许 runtime promotion，不允许写 default profile。下一阶段应回到概率本体/真实赛前特征/更强 candidate filter，而不是继续放宽 replacement reranker gate
README 更新 pre-match surface audit、tolerance grid、shadow gate、admission 报告路径、report_key、拒绝原因与非晋级结论；该能力属于“core final-answer replacement governance / pre-match surface safety gate / no-production-change”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-230 当前落地能力：

```text
按 V3.1-229 结论停止继续放宽 replacement reranker，转向更保守的候选池层 candidate filter 验证；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只验证“过滤风险候选”是否能在保护原始最终答案的前提下提升核心指标
marginal_loss_driver_candidate_guardrail_ablation CLI 的 --suite-manifest 改为可重复参数；加载器会合并多个 suite manifest 的 historical slices/resolved paths/warnings，并在 report summary_json.suite_manifests 中保留每个 manifest 的 suite_id、manifest_path、slice_count 与 resolved paths；单 manifest 情况继续保留旧 summary_json.suite_manifest 兼容字段
candidate guardrail ablation report 新增 original/baseline protection counters：item 级 final_hit_harmed_vs_baseline、profit_loss_harmed_vs_baseline；report 级 final_hit_harm_count_vs_baseline、profit_loss_harm_count_vs_baseline；options/CLI 新增 max_final_hit_harm_count_vs_baseline、max_profit_loss_harm_count_vs_baseline
新增 deterministic tests 覆盖：guardrail 会统计 per-slice original harm；显式 max harm threshold 会拒绝伤害原始最终答案的候选过滤；CLI 参数映射正常；多个 suite manifest 可合并加载
生成 combined original-protected candidate guardrail report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_prob45_65_negative_edge_original_protected_candidate_guardrail_v1.json；report_key=historical_marginal_loss_driver_candidate_guardrail_ablation:b8517ed3ed0386fc；decision=rejected
实验口径：core 5 seasons suite + expanded A-league rolling-window suite，共 240 slices；pass_types=1x1-8x1；modes=single/multiple；optimizer_profile=solver；candidate_fixture_limit=12；max_candidates_per_fixture=3；scenario_candidate_fixture_buffer=4；target competitions=ENG_CHAMPIONSHIP/EPL/ESP_LA_LIGA/FRA_LIGUE_2/GER_2_BUNDESLIGA/GER_BUNDESLIGA/ITA_SERIE_A/ITA_SERIE_B；probability=[0.45,0.65)；max_decimal_odds=2.30；max_model_edge=-0.02；max harm thresholds 均为 0
结果：excluded_candidate_count=3422；final_answer_changed_count=103；baseline_final_hit_count=169；candidate_final_hit_count=166；final_hit_count_delta=-3；final_hit_rate_delta=-0.012500000000000067；baseline_roi=0.0173867918452381；candidate_roi=0.1513340493442623；profit_loss_delta=+99.0926
原始保护结果：final_hit_harm_count_vs_baseline=23；profit_loss_harm_count_vs_baseline=29；按 final-hit harm 分布，ENG_CHAMPIONSHIP=6、FRA_LIGUE_2=6、GER_2_BUNDESLIGA=7、ITA_SERIE_B=4；这说明 broad hard filter 虽提升 ROI，但会伤害大量原始最终答案
概率质量结果：brier_score_delta=+0.0022622232667830477、log_loss_delta=+0.004475282410779657、mean_calibration_error_delta=+0.0041318836010575954，均为退步；拒绝原因包含 final_hit_count_regressed、final_hit_rate_regressed、final_hit_harm_count_above_threshold、profit_loss_harm_count_above_threshold、brier/logloss/calibration regressed
关键判断：广义 negative-edge hard candidate filter 不是当前核心准确率的安全路径；它将系统从“更常命中”推向“更高波动收益”，这不符合用户提出的准确率优先。下一阶段应转向更窄的 per-competition/per-probability-band filter search，或回到概率本体/真实赛前特征校准；任何候选必须同时通过原始最终答案保护与概率质量门禁
README 更新 multi-manifest original-protected candidate guardrail 命令、报告路径、report_key、核心指标与拒绝原因；该能力属于“candidate filter safety gate / original final-answer protection / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-231 当前落地能力：

```text
按 V3.1-230 结论把 broad hard filter 收敛为窄范围候选搜索；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只新增可枚举、可审计的 per-competition / probability-band / odds / edge grid evidence
新增 marginal_loss_driver_candidate_guardrail_grid 模块：复用 candidate guardrail ablation 的 original/baseline protection gate，但在 grid 内只计算一次 baseline，再逐个评估候选 hard filter，降低后续分批搜索成本
新增模型：HistoricalMarginalLossDriverCandidateGuardrailGridOptions、HistoricalMarginalLossDriverCandidateGuardrailGridSpec、HistoricalMarginalLossDriverCandidateGuardrailGridCandidate、HistoricalMarginalLossDriverCandidateGuardrailGridReport；候选记录 competition_ids、probability_min/max、max_decimal_odds、max_model_edge、optional quality caps、excluded count、final-answer changed count、final-hit/profit harm count、Brier/log-loss/calibration deltas 与 reason_codes
新增 CLI：nutmeg-recommendation-marginal-loss-driver-candidate-guardrail-grid；支持 repeatable --suite-manifest、repeatable --competition-group、probability_min/max value lists、max_decimal_odds/max_model_edge value lists、optional quality cap lists、candidate_start_index/candidate_limit、original harm thresholds 与 objective gate；负数列表使用 --max-model-edge-values=-0.02 形式传入
新增 deterministic tests 覆盖：grid 能枚举窄候选并区分 active/inactive competition；original harm thresholds 会拒绝伤害原始最终答案的候选；CLI 参数映射 competition groups、value lists、candidate window 与 harm thresholds
生成 core 5 seasons smoke grid report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_candidate_guardrail_grid_smoke_v1.json；report_key=historical_marginal_loss_driver_candidate_guardrail_grid:4e35f287cfebc9d0；slice_count=30；fixture_count=10738；candidate_count=1；accepted_count=1；warnings=[]
smoke 口径：EPL；pass_types=2x1；mode=single；optimizer_profile=solver；candidate_fixture_limit=48；max_candidates_per_fixture=2；scenario_candidate_fixture_buffer=4；probability=[0.45,0.65)；max_decimal_odds=2.30；max_model_edge=-0.02；max harm thresholds 均为 0；require_objective_improvement=false
smoke 结果：excluded_candidate_count=618；final_answer_changed_count=0；baseline_final_hit_count=20/30；candidate_final_hit_count=20/30；baseline_roi=-0.1422633333333333；candidate_roi=-0.1422633333333333；profit_loss_delta=0；final_hit_harm_count_vs_baseline=0；profit_loss_harm_count_vs_baseline=0；Brier/log-loss/calibration 均无变化
关键判断：grid runner 与 original-protection 检查已可用，但当前 smoke 候选属于行为 no-op，只证明安全剪枝和报告链路，不代表可上线规则；下一阶段应在 combined core + expanded rolling slices 上分批运行更多候选 index，并重新打开 objective improvement gate，寻找“会改变最终答案且不伤害命中率/概率质量”的窄规则
README 更新 candidate guardrail grid 命令、smoke report、report_key、核心指标与非生产结论；该能力属于“candidate filter grid evidence / original final-answer protection / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-232 当前落地能力：

```text
按 V3.1-231 的下一步，把 candidate guardrail grid 推进到 combined core + expanded rolling-window 小型完整搜索；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只增强可恢复分批能力并生成 objective-gated full grid evidence
marginal_loss_driver_candidate_guardrail_grid 新增 candidate_indices；CLI 新增 --candidate-indices，显式 index 优先于 candidate_start_index/candidate_limit，便于长搜索中断后补跑某些候选
grid report summary 新增 candidate_selection_mode、requested_candidate_indices、unmatched_requested_candidate_indices、candidate_indices、missing_candidate_indices、next_candidate_start_index、is_full_grid，用于判断单批是否完整、是否有缺口
新增 merge_historical_marginal_loss_driver_candidate_guardrail_grid_reports 与 CLI：nutmeg-recommendation-marginal-loss-driver-candidate-guardrail-grid-merge；合并后报告会按 candidate_index 排序，输出 missing/duplicate candidate indices、source_report_keys/source_report_paths 与 is_full_grid
新增 deterministic tests 覆盖：显式 candidate_indices 只执行指定候选并报告缺失 index；多个 batch report 可合并为完整 grid；CLI 参数映射 candidate_indices；新增 entry point 与 __init__ export
生成 combined batch reports：batch0 indices 0-3、batch1 indices 4-7、batch2 indices 8-11，均使用 core 5 seasons suite + expanded A-league rolling-window suite，共 240 slices；pass_types=2x1；mode=single；optimizer_profile=solver；candidate_fixture_limit=12；max_candidates_per_fixture=3；scenario_candidate_fixture_buffer=4；max harm thresholds 均为 0；objective improvement gate 保持开启
生成 combined full grid report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_candidate_guardrail_grid_full_v1.json；report_key=historical_marginal_loss_driver_candidate_guardrail_grid:f33da1941ff953a6；slice_count=240；fixture_count=13258；prediction_count=39774；candidate_count=12；evaluated_candidate_count=12；accepted_count=0；rejected_count=12；missing_candidate_indices=[]；duplicate_candidate_indices=[]；is_full_grid=true；warnings=[]
baseline 口径：baseline_final_hit_count=105/240；baseline_final_hit_rate=0.4375；baseline_roi=-0.10566750000000001；baseline_profit_loss=-50.720400000000005；baseline_brier_score=0.20127066642065472；baseline_log_loss=0.591914366020624
best rejected candidate：FRA_LIGUE_2 probability [0.45,0.65)，excluded_candidate_count=124，final_answer_changed_count=29；final_hit_count_delta=+2；final_hit_rate_delta=+0.00833333333333336；roi_delta=+0.08798333333333334；profit_loss_delta=+42.232000000000006；但 final_hit_harm_count_vs_baseline=6、profit_loss_harm_count_vs_baseline=6、brier_score_delta=+0.005901350033140101、log_loss_delta=+0.01420043577269725，因此被拒绝
完整 grid 结论：12 个窄 hard filter 候选全部拒绝；部分候选改善 aggregate ROI 或概率质量，但没有候选同时满足“不伤害原始最终答案 + 不回撤命中率 + 概率质量不退步”；这确认当前方向不能靠简单 negative-edge hard delete 上线
关键判断：candidate hard filter 方向保留为 evidence/diagnostic，不进入 runtime/default profile；下一阶段应转向更细粒度的 soft scoring 或真实赛前特征校准，例如按 candidate contribution + probability calibration + market context 做替代评分，而不是继续扩大 hard filter 范围
README 更新 explicit candidate index、merge CLI、combined full grid report、report_key、best rejected candidate 与非晋级结论；该能力属于“resumable candidate filter grid / full combined evidence / original final-answer protection”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-233 当前落地能力：

```text
按 V3.1-232 结论验证“hard delete 改成 soft scoring”是否能成为更安全路径；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只增强 soft-demotion evidence runner 并生成 combined shadow evidence
marginal_loss_driver_candidate_soft_penalty_grid CLI 的 --suite-manifest 改为可重复参数；加载器会合并多个 suite manifest 的 historical slices/resolved paths/warnings，并在 report summary_json.suite_manifests 中保留每个 manifest 的 suite_id、manifest_path、slice_count 与 resolved paths；单 manifest 情况继续保留旧 summary_json.suite_manifest 兼容字段
soft penalty grid 新增 original/baseline protection counters：candidate/report delta 级 final_hit_harm_count_vs_baseline、profit_loss_harm_count_vs_baseline；options/CLI 新增 max_final_hit_harm_count_vs_baseline、max_profit_loss_harm_count_vs_baseline，用于防止 aggregate 改善但局部伤害原始最终答案
soft penalty candidate 新增 final-answer exposure diagnostics：penalized_final_answer_count、penalized_final_answer_leg_count，用来判断被 soft penalty 命中的候选是否真的进入最终答案 surface；这能区分“策略太轻”和“候选根本不在最终答案路径上”
新增 deterministic tests 覆盖：soft penalty grid 会统计 per-slice original harm，并在显式 max harm threshold 下拒绝伤害原始最终答案的候选；CLI 参数映射多个 suite manifest 与 harm thresholds 正常
生成 combined soft penalty original-protected report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_prob45_65_candidate_soft_penalty_combined_modes_original_protected_v1.json；report_key=historical_marginal_loss_driver_candidate_soft_penalty_grid:fb5d037e551c84ce
实验口径：core 5 seasons suite + expanded A-league rolling-window suite，共 240 slices；pass_types=2x1；modes=single/multiple；optimizer_profile=solver；candidate_fixture_limit=12；max_candidates_per_fixture=2；scenario_candidate_fixture_buffer=4；derive_market_context_signals=true；target competition=FRA_LIGUE_2；probability=[0.45,0.65)；max_decimal_odds=2.30；max_model_edge=-0.02；strength_values=0.02/0.05/0.10/0.20/0.35/0.50/0.75/1.00；max harm thresholds 均为 0
结果：candidate_count=8；accepted_count=0；rejected_count=8；每个 strength 均 penalized_candidate_count=124，但 penalized_final_answer_count=0、penalized_final_answer_leg_count=0、final_answer_changed_count=0；baseline_final_hit_count=20/30；candidate_final_hit_count=20/30；ROI、profit/loss、Brier、log-loss、calibration 均无变化；拒绝原因均为 objective_improvement_missing
关键判断：当前 candidate-level internal_candidate_score_penalty 对该 FRA_LIGUE_2 segment 太靠上游；它命中了候选池中的 124 个候选，但这些候选没有进入最终答案 surface，所以无法改善最终答案。该 soft penalty 继续保留为诊断证据，不允许 promotion。下一阶段应转向 final-answer exposure diagnostics、候选池/最终答案边界的贡献度分析，或概率/market-context 校准，而不是继续提高 soft penalty strength
README 更新 multi-manifest soft penalty grid、original harm counters、final-answer exposure diagnostics、combined report path、report_key 与非晋级结论；该能力属于“soft scoring evidence / final-answer exposure diagnostics / original final-answer protection”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-234 当前落地能力：

```text
按 V3.1-233 结论继续追踪 soft penalty 为什么没有改变最终答案；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只补候选暴露层级诊断并生成 combined evidence
historical_backtest summary 新增 marginal_loss_driver_candidate_soft_penalty exposure counters：candidate_pool_candidate_count、candidate_pool_fixture_count、completed_scenario_selected_candidate_count、completed_scenario_selected_option_count、final_answer_selected_candidate_count、final_answer_selected_fixture_ids；这些字段用于判断目标 profile 停在 eligible、candidate pool、scenario selections 还是 final answer
marginal_loss_driver_candidate_soft_penalty_grid candidate/report delta 同步新增 penalized_candidate_pool_count、penalized_candidate_pool_fixture_count、penalized_completed_scenario_selected_candidate_count、penalized_completed_scenario_selected_option_count；保留已有 original harm counters 与 final-answer counters
新增 deterministic tests 覆盖：soft penalty grid 能从真实 historical_backtest summary 聚合 candidate-pool exposure；harm threshold 与 CLI 多 suite manifest 行为保持通过
生成 combined exposure diagnostics report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_prob45_65_candidate_soft_penalty_exposure_diagnostics_v1.json；report_key=historical_marginal_loss_driver_candidate_soft_penalty_grid:b7eabd6f87de174a
实验口径：core 5 seasons suite + expanded A-league rolling-window suite，共 240 slices；pass_types=2x1；modes=single/multiple；optimizer_profile=solver；candidate_fixture_limit=12；max_candidates_per_fixture=2；scenario_candidate_fixture_buffer=4；derive_market_context_signals=true；target competition=FRA_LIGUE_2；probability=[0.45,0.65)；max_decimal_odds=2.30；max_model_edge=-0.02；strength_values=0.00/0.02/0.05/0.10/0.20/0.35/0.50/0.75/1.00；max harm thresholds 均为 0
结果：candidate_count=9；accepted_count=0；rejected_count=9；每个 strength 均 penalized_candidate_count=124，但 penalized_candidate_pool_count=0、penalized_candidate_pool_fixture_count=0、penalized_completed_scenario_selected_candidate_count=0、penalized_completed_scenario_selected_option_count=0、penalized_final_answer_count=0、penalized_final_answer_leg_count=0、final_answer_changed_count=0；ROI、profit/loss、Brier、log-loss、calibration 均无变化；拒绝原因均为 objective_improvement_missing
阶段性胜利/关键判断：soft penalty 无效不是因为 strength 太小，而是因为该 FRA_LIGUE_2 profile 虽然有 124 个 eligible 候选，却在 candidate-pool compression 后为 0；candidate-level penalty 不能影响没有进入压缩池的候选。hard delete 之所以能改变最终答案，是因为它改变了压缩前的 fixture-level ranking/pool composition，而不是直接惩罚最终答案腿。下一阶段应转向 candidate-pool compression / fixture-level exposure 贡献度诊断，或者回到概率与 market-context 校准；继续单纯提高 soft penalty strength 没有意义
README 更新 exposure diagnostics 报告路径、report_key、candidate-pool drop-off 结论与非晋级边界；该能力属于“candidate-pool exposure diagnostics / soft scoring failure localization / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-235 当前落地能力：

```text
按 V3.1-234 结论继续追踪 target profile 为什么没有进入 candidate-pool compression；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只补 fixture-level rankability 与 policy exclusion reason 诊断
historical_backtest summary 的 marginal_loss_driver_candidate_soft_penalty fixture exposure 新增 rankable_candidate_count、rankable_fixture_count、excluded_candidate_count、exclusion_reason_counts、within_candidate_fixture_limit_count、just_outside_candidate_fixture_limit_count、rank_min/average/max、best_rank_gap_to_limit、best/cutoff fixture top score 与 score gap；用于定位目标 profile 是被 policy filter 拦截、fixture rank 太低，还是最终答案仲裁阶段掉落
marginal_loss_driver_candidate_soft_penalty_grid 同步聚合 fixture exposure counts：penalized_fixture_exposure_rankable_candidate_count、rankable_fixture_count、within_limit_count、just_outside_limit_count，并在 deltas_json 中聚合 penalized_fixture_exposure_excluded_candidate_count 与 exclusion_reason_counts
新增 deterministic tests 覆盖：在 candidate_fixture_limit 压缩场景下，目标 profile 能统计 rankable candidates/fixtures，但没有进入 candidate pool；历史回测与 soft penalty grid 单元测试保持通过
生成 combined fixture exposure report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_prob45_65_candidate_soft_penalty_fixture_exposure_v1.json；report_key=historical_marginal_loss_driver_candidate_soft_penalty_grid:ca09d2f26ee8f3cf
实验口径：core 5 seasons suite + expanded A-league rolling-window suite，共 240 slices；pass_types=2x1；modes=single/multiple；optimizer_profile=solver；candidate_fixture_limit=12；max_candidates_per_fixture=2；scenario_candidate_fixture_buffer=4；derive_market_context_signals=true；target competition=FRA_LIGUE_2；probability=[0.45,0.65)；max_decimal_odds=2.30；max_model_edge=-0.02；strength_values=0.00/0.02/0.05/0.10/0.20/0.35/0.50/0.75/1.00；max harm thresholds 均为 0
结果：candidate_count=9；accepted_count=0；rejected_count=9；每个 strength 均 penalized_candidate_count=124，但 penalized_fixture_exposure_rankable_candidate_count=0、penalized_fixture_exposure_rankable_fixture_count=0、penalized_candidate_pool_count=0、penalized_completed_scenario_selected_candidate_count=0、penalized_final_answer_count=0、final_answer_changed_count=0；penalized_fixture_exposure_excluded_candidate_count=124；exclusion_reason_counts={data_quality_too_low:124}
阶段性胜利/关键判断：soft penalty 无效的根因进一步缩小到 policy filter：这 124 个 FRA_LIGUE_2 target candidates 全部被 min_data_quality_score=80 拦截，尚未进入 rank_candidates / fixture-level compression。继续提高 soft penalty strength 没有意义；继续调 fixture ranking 也暂时不是第一问题。下一阶段应转向 data quality calibration / source-quality weighting / competition-segment quality gate：判断这些 low-data-quality 候选是否应该被完全排除，还是需要单独的 beta-quality 口径和更保守的准入门槛
README 更新 fixture exposure report、report_key、data_quality_too_low 根因与非晋级边界；该能力属于“policy-filter exposure diagnostics / data-quality bottleneck localization / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-236 当前落地能力：

```text
按 V3.1-235 结论验证 min_data_quality_score=80 是否只是过严门槛，还是确实保护最终答案；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只新增 data-quality threshold sensitivity evidence
新增 marginal_loss_driver_data_quality_threshold_grid 模块与 CLI：nutmeg-recommendation-marginal-loss-driver-data-quality-threshold-grid；固定 baseline_min_data_quality_score=80，再逐档比较 candidate_min_data_quality_score_values；候选仍用 marginal_loss_driver soft-penalty profile strength=0.0 做目标 segment 标记，便于复用 target candidate/rankable/candidate-pool/scenario/final-answer exposure counters
新增模型：HistoricalMarginalLossDriverDataQualityThresholdGridOptions、HistoricalMarginalLossDriverDataQualityThresholdCandidate、HistoricalMarginalLossDriverDataQualityThresholdGridReport；candidate 记录 target_candidate_count、target_rankable_candidate_count、target_excluded_candidate_count、target_exclusion_reason_counts、target_candidate_pool_count、target_completed_scenario_selected_candidate_count、target_final_answer_count、final_hit_sample_size_delta、final_hit_count_delta、ROI/P&L delta、original harm counters 与 reason_codes
新增 deterministic tests 覆盖：baseline 固定 80 且不启用 target profile；candidate thresholds 逐档启用 target marker；低阈值能恢复 target rankable/candidate-pool exposure 并产生 objective improvement codes；CLI options 映射多 suite manifest、threshold values、target profile、original harm thresholds 正常
生成 combined data-quality threshold report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_prob45_65_data_quality_threshold_grid_v1.json；report_key=historical_marginal_loss_driver_data_quality_threshold_grid:f175d13c4f91cea4
实验口径：core 5 seasons suite + expanded A-league rolling-window suite，共 240 slices；pass_types=2x1；modes=single/multiple；optimizer_profile=solver；candidate_fixture_limit=12；max_candidates_per_fixture=2；scenario_candidate_fixture_buffer=4；derive_market_context_signals=true；target competition=FRA_LIGUE_2；probability=[0.45,0.65)；max_decimal_odds=2.30；max_model_edge=-0.02；baseline_min_data_quality_score=80；candidate thresholds=80/75/70/60/50；max harm thresholds 均为 0
结果：candidate_count=5；accepted_count=0；rejected_count=5。threshold=80/75 时 target_candidate_count=124 但 target_rankable_candidate_count=0、target_excluded_candidate_count=124、exclusion_reason_counts={data_quality_too_low:124}，最终答案无变化。threshold=70/60/50 时 target_rankable_candidate_count=124、target_candidate_pool_count=124、target_completed_scenario_selected_candidate_count=112、target_final_answer_count=29，baseline_final_hit_count=20/30，candidate_final_hit_count=132/240，final_hit_sample_size_delta=+210，final_hit_count_delta=+112，但 final_hit_rate_delta=-0.11666666666666659、profit_loss_delta=-88.88400000000001、profit_loss_harm_count_vs_baseline=114、mean_calibration_error regressed，因此全部 rejected
阶段性胜利/关键判断：全局降低 min_data_quality_score 能恢复覆盖，但不是安全上线路径；它把样本从 30 个最终答案扩到 240 个，命中数增加但命中率和局部 P&L 保护失败。当前不能把 70/60/50 写入默认 profile，也不应继续做 broad quality threshold drop。下一阶段应做 competition/source-specific quality calibration 或 beta-quality lane：只在通过 final-answer hit-rate、original harm、calibration 与预算稳定门禁的 segment 上放开，而不是全局降门槛
README 更新 data-quality threshold grid 命令、report_key、核心指标、非晋级结论与下一步方向；该能力属于“data-quality threshold evidence / final-answer protection / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-237 当前落地能力：

```text
按 V3.1-236 结论继续收窄为 per-competition data-quality threshold override；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只让 historical backtest 支持实验性分联赛 min_data_quality_score，并新增分联赛 grid evidence
RecommendationPolicyConfig 新增 min_data_quality_score_by_competition_id；policy rank_candidates 的 data_quality filter 会先读取 candidate.metadata_json.competition_id 的 override，没有 override 时继续使用全局 min_data_quality_score；HistoricalRecommendationBacktestOptions 同步新增 min_data_quality_score_by_competition_id，summary_json/backtest_key 会记录该 override，用于区分实验结果
historical_backtest 的主 policy config、upset final-answer lane policy、upset reserve/upsell lane quality filter、fixture exposure policy exclusion reason 均接入分联赛质量阈值 helper；默认空 dict，因此所有现有生产/回测路径保持全局阈值行为
新增 competition_data_quality_threshold_grid 模块与 CLI：nutmeg-recommendation-competition-data-quality-threshold-grid；固定 baseline_min_data_quality_score=80，然后逐个 competition_id、逐个 candidate threshold 只下调单一联赛阈值，报告 newly_admitted_prediction_count、newly_admitted_fixture_count、final_answer_changed_count、final hit/ROI/P&L/probability quality deltas、original harm counters 与 reason_codes
新增 deterministic tests 覆盖：policy 只对指定 competition lowered threshold 放行候选；grid baseline 使用全局 80 且 candidate 使用 min_data_quality_score_by_competition_id；CLI options 映射多 suite manifest、competition list、threshold values、original harm thresholds 正常
生成 lower-league per-competition threshold report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_lower_league_data_quality_threshold_grid_v1.json；report_key=historical_competition_data_quality_threshold_grid:7d1bae77b334dceb
实验口径：core 5 seasons suite + expanded A-league rolling-window suite，共 240 slices；pass_types=2x1；modes=single/multiple；optimizer_profile=solver；candidate_fixture_limit=12；max_candidates_per_fixture=2；scenario_candidate_fixture_buffer=4；derive_market_context_signals=true；baseline_min_data_quality_score=80；competitions=FRA_LIGUE_2/GER_2_BUNDESLIGA/ITA_SERIE_B/ESP_SEGUNDA_DIVISION/ENG_CHAMPIONSHIP；candidate thresholds=75/70/60/50；max harm thresholds 均为 0
结果：candidate_count=20；accepted_count=0；rejected_count=20。threshold=75 对五个联赛均 newly_admitted_prediction_count=0。threshold=70/60/50 对每个测试联赛均 newly_admitted_prediction_count=1080、newly_admitted_fixture_count=360、final_answer_changed_count=30、candidate_final_hit_sample_size=60；相比全局 80 baseline 的 20/30，candidate hit counts 分别为 FRA_LIGUE_2=27/60、GER_2_BUNDESLIGA=30/60、ITA_SERIE_B=38/60、ESP_SEGUNDA_DIVISION=39/60、ENG_CHAMPIONSHIP=34/60，但 final_hit_rate_delta 均为负；profit_loss_harm_count_vs_baseline 分别为 23/20/18/16/21，且多数 brier/logloss/calibration 退步，因此全部 rejected
阶段性胜利/关键判断：分联赛降阈值比全局降阈值更可控，但仍不足以上线；它恢复覆盖并增加命中数，却降低最终命中率并破坏局部 P&L/概率质量保护。当前不应继续扩大 threshold-only 搜索；下一阶段应聚焦 70-79 quality band 内部的概率校准/候选重评分，例如只允许高 calibration、稳定赔率、低 volatility 的低质量候选进入 beta-quality lane
README 更新 per-competition threshold grid 命令、report_key、核心指标、非晋级结论与下一步方向；该能力属于“competition-scoped data-quality threshold evidence / final-answer protection / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-238 当前落地能力：

```text
按 V3.1-237 结论把 70-79 data-quality band 收敛为显式 beta-quality lane；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只新增可审计的低质量区间准入过滤与 combined historical evidence
RecommendationPolicyConfig 新增 data_quality_beta_lane_enabled、data_quality_beta_lane_competition_ids、data_quality_beta_lane_min_probability、data_quality_beta_lane_max_decimal_odds、data_quality_beta_lane_min_model_edge、data_quality_beta_lane_min_model_confidence_score、data_quality_beta_lane_min_calibration_score、data_quality_beta_lane_min_odds_stability_score、data_quality_beta_lane_max_volatility_penalty；只有在 competition override 已经降低阈值后，候选仍必须通过这些 beta lane guard，否则以 data_quality_beta_lane_rejected 排除
HistoricalRecommendationBacktestOptions 同步接入 beta lane 参数；backtest summary_json 与 backtest key 记录 lane 配置，主 recommendation policy 与 upset final-answer lane policy 均保持默认关闭，确保现有生产/回测路径不变
新增 competition_data_quality_beta_lane_grid 模块与 CLI：nutmeg-recommendation-competition-data-quality-beta-lane-grid；固定 baseline_min_data_quality_score=80，逐个 competition_id 降到 beta_min_data_quality_score，同时枚举 beta lane probability/odds/edge/model-confidence/calibration/odds-stability/volatility guards，并报告 beta_lane_prediction_count、beta_lane_fixture_count、final-answer changed count、final hit/ROI/P&L/probability quality deltas、original harm counters 与 reason_codes
新增 deterministic tests 覆盖：policy 在 lowered threshold 下仍会用 beta lane 拦截低稳定性候选；grid baseline 保持全局 80 且 candidate 打开 beta lane；CLI options 正确映射多 suite manifest、competition list、负数 edge values、beta quality guards 与 original harm thresholds
第一轮 lower-league beta lane report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_lower_league_data_quality_beta_lane_grid_v1.json；report_key=historical_competition_data_quality_beta_lane_grid:9a605134298e76ef；candidate_count=160；accepted_count=0；rejected_count=160；最佳候选 beta_lane_prediction_count=0，说明 min_model_edge=-0.02/0.0 对当前 70-79 band 太窄，候选仍无法进入 lane
第二轮 edge-wide report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_lower_league_data_quality_beta_lane_grid_edge_wide_v1.json；report_key=historical_competition_data_quality_beta_lane_grid:b0fb093f71be692a；candidate_count=240；accepted_count=0；rejected_count=240
edge-wide 实验口径：core 5 seasons suite + expanded A-league rolling-window suite，共 240 slices；pass_types=2x1；modes=single/multiple；optimizer_profile=solver；candidate_fixture_limit=12；max_candidates_per_fixture=2；scenario_candidate_fixture_buffer=4；derive_market_context_signals=true；baseline_min_data_quality_score=80；competitions=FRA_LIGUE_2/GER_2_BUNDESLIGA/ITA_SERIE_B/ESP_SEGUNDA_DIVISION/ENG_CHAMPIONSHIP；beta threshold=70；min_probability=0.45/0.50；max_decimal_odds=2.30/2.80；min_model_edge=-0.10/-0.05/-0.02；min_model_confidence_score=0.66；min_calibration_score=0.70；min_odds_stability_score=0.90/0.95；max_volatility_penalty=0.08/0.05；max harm thresholds 均为 0
edge-wide 最佳候选：ITA_SERIE_B，beta_min_data_quality_score=70，min_probability=0.50，max_decimal_odds=2.80，min_model_edge=-0.05，min_odds_stability_score=0.95，max_volatility_penalty=0.05；beta_lane_prediction_count=12，beta_lane_fixture_count=12，candidate_final_hit_count=21/31，相比 baseline 20/30 的 final_hit_rate_delta=+0.010752688172043001，roi_delta=+0.04222139784946237，profit_loss_delta=+2.3332000000000006，final_hit_harm_count_vs_baseline=0，profit_loss_harm_count_vs_baseline=0
拒绝原因：competition_data_quality_beta_lane:brier_score_regressed、log_loss_regressed、mean_calibration_error_regressed；即使 settlement 层面有改善，概率质量仍退化，因此不能晋级默认推荐 profile
阶段性胜利/关键判断：70-79 quality band 不是完全无价值，beta lane 已能在严格局部 harm=0 条件下找到命中/ROI/P&L 改善的候选；但概率校准退化说明当前免费历史样本/quality scoring 下还不能直接信任这些腿。下一阶段应转向 calibration repair 或 beta-lane-local probability adjustment，而不是继续扩大降阈值/放松 lane guard
README 更新 beta-quality lane 命令、report_key、核心指标、非晋级结论与下一步方向；该能力属于“beta-quality lane evidence / data-quality calibration guard / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-239 当前落地能力：

```text
按 V3.1-238 结论实现 beta-lane-local probability repair；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只把 70-79 beta lane 的概率质量退化做成可控影子修复实验
HistoricalRecommendationBacktestOptions 新增 data_quality_beta_lane_probability_repair_enabled、data_quality_beta_lane_probability_repair_strength、data_quality_beta_lane_probability_repair_max_delta、data_quality_beta_lane_probability_repair_min_market_probability_delta；默认全部关闭/0，因此普通回测、生产默认 profile 与已有 report key 口径不变
回测候选生成后、candidate-pool compression 前会在显式开关下修复 beta-lane 候选概率：只有候选属于已降低阈值的 beta lane、仍在全局 min_data_quality_score 以下、通过 beta lane probability/odds/edge/confidence/calibration/stability/volatility guards，且 market-implied probability 高于模型概率时，才按 strength 和 max_delta 把 probability 向市场概率地板抬升；model_edge 随 repaired_probability 同步重算，metadata_json 记录原始概率、market probability、repair delta、strength 与 max_delta
historical backtest summary/backtest key 新增 beta-lane probability repair 参数与 exposure counts：eligible repair candidate count、candidate-pool repair candidate count、final-answer selected repair candidate count、final-answer selected fixture ids；这些字段用于判断修复是否真的进入最终答案，而不是只停在候选层
competition_data_quality_beta_lane_grid 新增 probability_repair_strength_values、probability_repair_max_delta_values、probability_repair_min_market_probability_delta_values；candidate/report 输出 repair 参数、repair candidate count、repair candidate pool count、repair final-answer selected candidate count，继续复用 final-answer hit/ROI/P&L/probability-quality gate
新增 deterministic tests 覆盖：回测只对 beta lane 且 market probability 高于模型概率的候选做 capped lift；grid candidate options 正确打开 repair；CLI 正确映射 repair strength/max-delta/min-market-delta values
生成 focused ITA Serie B probability repair report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_beta_lane_probability_repair_grid_v1.json；report_key=historical_competition_data_quality_beta_lane_grid:d04728e3f1843d23；candidate_count=40；accepted_count=0；rejected_count=40
focused repair 实验口径：core 5 seasons suite + expanded A-league rolling-window suite，共 240 slices；competition=ITA_SERIE_B；beta_min_data_quality_score=70；min_probability=0.50；max_decimal_odds=2.80；min_model_edge=-0.05；min_model_confidence_score=0.66；min_calibration_score=0.70；min_odds_stability_score=0.95；max_volatility_penalty=0.05；probability_repair_strength=0/0.25/0.50/0.75/1.0；probability_repair_max_delta=0/0.02/0.04/0.06；min_market_probability_delta=0/0.01；max harm thresholds 均为 0
focused repair 最佳候选：strength=1.0、max_delta=0.06、min_market_delta=0.01；probability_repair_candidate_count=12，candidate_pool_count=12，final_answer_selected_candidate_count=2；仍保持 V3.1-238 的 settlement 改善：candidate_final_hit_count=21/31、final_hit_rate_delta=+0.010752688172043001、roi_delta=+0.04222139784946237、profit_loss_delta=+2.3332000000000006、final_hit_harm_count_vs_baseline=0、profit_loss_harm_count_vs_baseline=0
probability quality 改善但未过门：相对 V3.1-238 未修复的 best candidate，brier_score_delta 从 +0.004194625208900071 降到 +0.0021796163854257977，log_loss_delta 从 +0.00846323186061515 降到 +0.004356130928156898，mean_calibration_error_delta 从 +0.005686296416945846 降到 +0.003906367249124965；但三项仍为正，因此仍被 brier_score_regressed、log_loss_regressed、mean_calibration_error_regressed 拦截
生成 delta-wide follow-up report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_beta_lane_probability_repair_grid_delta_wide_v1.json；report_key=historical_competition_data_quality_beta_lane_grid:0c3281c86120bf6c；candidate_count=8；accepted_count=0；rejected_count=8；max_delta=0.08/0.10/0.12/0.15 与 max_delta=0.06 结果相同，说明市场概率地板已经触顶，继续加 cap 没有收益
阶段性胜利/关键判断：market-floor probability repair 是有效修复方向，但只能把概率质量退化缩小，不能完全消除。当前不应把 beta lane 或 repair 写入默认 profile；下一阶段应做 beta-lane-local calibration model/profile，例如从赛前可见的 market gap、league/season segment、odds stability 与 data-quality component 学习更细的概率转换，而不是继续调 max_delta
README 更新 probability repair 命令、report_key、核心指标、非晋级结论与下一步方向；该能力属于“beta-lane probability repair / calibration no-regression gate / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-240 当前落地能力：

```text
按 V3.1-239 结论把 market-floor repair 推进为 beta-lane-local calibration profile；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只在已通过 beta lane guard 的 lower-quality candidate 上增加更细的赛前可见概率转换
HistoricalRecommendationBacktestOptions 新增 data_quality_beta_lane_probability_repair_extra_uplift、data_quality_beta_lane_probability_repair_data_quality_gap_weight、data_quality_beta_lane_probability_repair_odds_stability_weight、data_quality_beta_lane_probability_repair_max_probability；默认均为 0 或 1.0，因此不影响现有默认回测/生产路径
beta lane probability repair 现在的 delta = market_gap * strength + extra_uplift + data_quality_gap * data_quality_gap_weight + odds_stability_quality * odds_stability_weight，并受 max_delta 与 max_probability 双重约束；其中 market_gap、data_quality_gap、odds_stability_quality 都来自赛前可见字段，metadata_json 记录 local profile 参数和实际 repair delta
competition_data_quality_beta_lane_grid 新增 probability_repair_extra_uplift_values、probability_repair_data_quality_gap_weight_values、probability_repair_odds_stability_weight_values、probability_repair_max_probability_values；candidate/report 输出这些字段，继续复用原有 final-answer hit/ROI/P&L/probability-quality gate
deterministic tests 更新：回测可在 strength=0 时只靠 local extra uplift 触发 capped repair；grid candidate options 和 CLI 均能映射 local profile uplift/data-quality/stability/max-probability 参数
生成 first local calibration profile report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_beta_lane_local_calibration_profile_grid_v1.json；report_key=historical_competition_data_quality_beta_lane_grid:cb6995d682f39b8f；candidate_count=48；accepted_count=0；rejected_count=48；最佳候选已经让 brier_score_delta=-0.001230719835465216、log_loss_delta=-0.0024973558412473285，但 mean_calibration_error_delta=+0.0003819766981501549，说明方向正确但还差一层 uplift
生成 stronger local calibration profile report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_beta_lane_local_calibration_profile_grid_stronger_v1.json；report_key=historical_competition_data_quality_beta_lane_grid:547c9df8d223c9c9；candidate_count=12；accepted_count=12；rejected_count=0
stronger profile 实验口径：core 5 seasons suite + expanded A-league rolling-window suite，共 240 slices；competition=ITA_SERIE_B；beta_min_data_quality_score=70；min_probability=0.50；max_decimal_odds=2.80；min_model_edge=-0.05；min_model_confidence_score=0.66；min_calibration_score=0.70；min_odds_stability_score=0.95；max_volatility_penalty=0.05；repair_strength=1.0；max_delta=0.18/0.22/0.26；extra_uplift=0.08/0.10；data_quality_gap_weight=0.02/0.04；odds_stability_weight=0.0；max_probability=0.98；max harm thresholds 均为 0
最佳 accepted candidate：max_delta=0.22，extra_uplift=0.10，data_quality_gap_weight=0.04，max_probability=0.98；probability_repair_candidate_count=12；final_answer_selected_candidate_count=2；candidate_final_hit_count=21/31；final_hit_rate_delta=+0.010752688172043001；roi_delta=+0.04222139784946237；profit_loss_delta=+2.3332000000000006；final_hit_harm_count_vs_baseline=0；profit_loss_harm_count_vs_baseline=0；brier_score_delta=-0.003415333355129946；log_loss_delta=-0.007117418622229588；mean_calibration_error_delta=-0.002453394268102871；reason_codes=[]
阶段性胜利/关键判断：这是 beta lane 方向第一次在 focused combined evidence 上同时通过 settlement 与 probability-quality gates，证明 lower-quality band 可以通过 local calibration profile 转成可用候选。但是该结论仍只针对 ITA_SERIE_B 的窄参数/窄样本，不能直接写入默认 profile。下一阶段必须做 rolling/season/competition admission 或 holdout replay，确认 accepted profile 不是同一 combined 样本上的偶然拟合
README 更新 local calibration profile 命令、report_key、accepted 指标与非生产边界；该能力属于“beta-lane local calibration profile / focused accepted shadow evidence / admission pending”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-241 当前落地能力：

```text
按 V3.1-240 结论新增 beta-lane local calibration profile 的 rolling/holdout admission；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只验证 focused accepted shadow candidate 是否能跨 overall / competition / season / rolling-window folds 晋级
新增 competition_data_quality_beta_lane_rolling_admission 模块与 CLI：nutmeg-recommendation-competition-data-quality-beta-lane-rolling-admission；输入 beta-lane grid report 与历史 suite manifest，选择 best/指定 candidate 后复跑 baseline min_data_quality_score=80 与 candidate beta-lane-local profile
Admission report 输出 status=accepted/shadow_only/rejected、candidate_profile_allowed、shadow_allowed、overall_fold、active/failed fold counts、checks、fold failure_reasons，并把 beta_lane_prediction_count、probability_repair_candidate_count、probability_repair_final_answer_selected_candidate_count、final hit/ROI/P&L/probability-quality deltas 与 harm count 作为准入指标
deterministic tests 覆盖：active folds 全部通过时 accepted；局部 active fold 失败时降为 shadow_only；overall gate 失败时 rejected；CLI 能写入 report 并正确映射 optimizer_profile、baseline_min_data_quality_score 与 source grid/candidate
生成 rolling admission report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_beta_lane_local_calibration_profile_rolling_admission_v1.json；report_key=historical_competition_data_quality_beta_lane_rolling_admission:a593425db4453821；source_grid_report_key=historical_competition_data_quality_beta_lane_grid:547c9df8d223c9c9；status=shadow_only；candidate_profile_allowed=false；shadow_allowed=true
整体 fold 仍然通过：final_answer_count=31；beta_lane_prediction_count=12；probability_repair_candidate_count=12；probability_repair_final_answer_selected_candidate_count=2；final_answer_hit_delta_count=+1；final_hit_rate_delta=+0.010752688172043001；roi_delta=+0.04222139784946237；profit_loss_delta=+2.3332000000000006；brier_score_delta=-0.003415333355129918；log_loss_delta=-0.007117418622229588；mean_calibration_error_delta=-0.002453394268102871；harm_count_vs_baseline=0
拒绝晋级原因：fold_count=62；active_fold_count=4；failed_fold_count=4；active_competition_fold_count=1；active_season_fold_count=1；active_rolling_fold_count=2；failed checks 为 failed_fold_count 超过 0 且 active_season_fold_count 低于 2；失败 fold 包含 competition:ITA_SERIE_B 的概率质量指标为空/不可判定、season:2021-2022 的 mean_calibration_error_delta 回撤，以及两个 rolling_window fold 的 Brier/log-loss/mean calibration 回撤
阶段性结论：V3.1-240 的 focused accepted profile 是有价值的 shadow evidence，但暴露集中在单一赛季/少数 rolling folds，不能作为 runtime/default profile。下一阶段应停止直接放宽这个 profile，转向寻找更稳的 season-aware 或 exposure-throttled local calibration rule，或者扩大真实赛前样本后重跑 admission
README 更新 rolling admission 命令、report_key、shadow_only 结论和非生产边界；该能力属于“beta-lane local calibration rolling admission / runtime promotion blocker / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-242 当前落地能力：

```text
按 V3.1-241 结论继续收紧 beta-lane local calibration profile 的暴露范围；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只新增 season/regime throttle，让 lower-quality threshold 与 probability repair 只在明确审计过的赛季/阶段窗口内生效
RecommendationPolicyConfig 与 HistoricalRecommendationBacktestOptions 新增 data_quality_beta_lane_season_ids、data_quality_beta_lane_min_competition_season_index、data_quality_beta_lane_max_competition_season_index；默认均为空/None，因此普通推荐、历史回测与生产默认 profile 行为不变
policy rank_candidates 与 historical beta-lane probability repair 现在都会先检查 competition，再检查 season/regime：赛季不匹配、competition_season_index 缺失或超出窗口时，低质量候选不会因 competition override 获得放行，也不会获得概率修复
competition_data_quality_beta_lane_grid 新增 season_groups、min_competition_season_index_values、max_competition_season_index_values 与 CLI 参数；candidate/report 输出 season_ids 与 min/max competition season index，并在 beta_lane_prediction_count / beta_lane_fixture_count 统计中同步过滤不匹配切片
competition_data_quality_beta_lane_rolling_admission 会继承 grid candidate 的 season/regime 约束，并在 backtest options 中注入全局 competition_season_index_by_slice_id；rolling admission summary 记录 candidate_season_ids 与 candidate_min/max_competition_season_index，便于审计 shadow profile 的真实暴露范围
修正 competition_season_index 语义：同一 competition 的同一 season 下多个 rolling-window slices 共享同一个 season index，避免把窗口编号误当成赛季编号；无 season 的 slice 仍按 slice 独立编号，保持兼容
新增 deterministic tests 覆盖：policy beta lane 可限制到 season/regime；historical probability repair 只在 season/regime 匹配时触发；competition season index 会按 season 聚合 rolling windows；grid CLI 能解析 season group 与 optional index values；grid candidate 可精确匹配 min=max 的 season-index 窗口；rolling admission 会把候选限制到指定 season/regime
生成 season/regime grid report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_beta_lane_local_calibration_profile_season_regime_grid_v1.json；report_key=historical_competition_data_quality_beta_lane_grid:a59e5c1e07fed94d；candidate_count=130；accepted_count=15；rejected_count=115
season/regime grid 实验口径：core 5 seasons suite + expanded A-league rolling-window suite；competition=ITA_SERIE_B；season_groups=2020-2021/2021-2022/2022-2023/2023-2024/2024-2025；min/max competition season index values=none/1/2/3/4/5；beta threshold=70；min_probability=0.50；max_decimal_odds=2.80；min_model_edge=-0.05；min_model_confidence_score=0.66；min_calibration_score=0.70；min_odds_stability_score=0.95；max_volatility_penalty=0.05；repair_strength=1.0；repair_max_delta=0.22；extra_uplift=0.10；data_quality_gap_weight=0.04；max_probability=0.98；max harm thresholds 均为 0
最佳 accepted candidate：season_ids=[2021-2022]，min_competition_season_index=2，max_competition_season_index=None；beta_lane_prediction_count=4；probability_repair_candidate_count=4；probability_repair_final_answer_selected_candidate_count=2；candidate_final_hit_count=21/31，相比 baseline 20/30 的 final_hit_rate_delta=+0.010752688172043001，roi_delta=+0.04222139784946237，profit_loss_delta=+2.3332000000000006；brier_score_delta=-0.003415333355129946，log_loss_delta=-0.007117418622229588，mean_calibration_error_delta=-0.002453394268102871；reason_codes=[]
生成 season/regime rolling admission report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_beta_lane_local_calibration_profile_season_regime_rolling_admission_v1.json；report_key=historical_competition_data_quality_beta_lane_rolling_admission:cc296895fda1e1f8；status=shadow_only；candidate_profile_allowed=false；shadow_allowed=true
rolling admission 结论：overall fold 仍通过，final_answer_count=31；beta_lane_prediction_count=4；final_answer_hit_delta_count=+1；roi_delta=+0.04222139784946237；profit_loss_delta=+2.3332000000000006；Brier/log-loss/mean calibration 均改善。但 failed_fold_count=4，失败点仍集中在 competition:ITA_SERIE_B 的小样本概率指标不可判定、season:2021-2022 的 mean_calibration_error_delta 小幅回撤，以及两个 rolling_window 的 Brier/log-loss/calibration 回撤，因此不能晋级 runtime/default profile
阶段性结论：season/regime throttle 已把 V3.1-240 的 12 个 beta-lane exposure 收缩为 2021-2022 赛季内 4 个 exposure，并保持 overall 指标正向；这证明“局部赛季白名单 + beta-lane repair”可作为 shadow evidence 审计工具，但仍不是生产策略。下一阶段应把该能力用于寻找跨多个赛季同时过 fold gate 的更稳 profile，或转向 final-answer segment / candidate replacement 的高质量样本路径，而不是继续放宽 ITA_SERIE_B beta lane
README 更新 season/regime throttle、report_key、shadow_only 结论和非生产边界；该能力属于“beta-lane season/regime exposure control / shadow profile audit / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-243 当前落地能力：

```text
按 V3.1-242 结论转向 final-answer segment / candidate replacement 的高质量样本路径；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只补强 replacement reranker admission 的范围治理，避免局部有效 profile 被误泛化
replacement_reranker_shadow_admission 新增 scope_competition_ids、scope_season_ids、scope_min_competition_season_index、scope_max_competition_season_index；默认均为空/None，因此既有 admission 行为与历史报告兼容
scoped admission 会在 overall gate 和 competition/season/rolling folds 之前先裁剪 audit items，同时保留原始 source_audit_report_key 与 tolerance-grid source match；summary_json.scope 记录 source/scoped item、slice、final-answer 数量，以及 scoped competition/season/index 暴露范围
competition_season_index 语义沿用 V3.1-242：同一 competition 的同一 season 下多个 rolling-window slices 共享同一个 season index，用于把 runtime candidate evidence 限制在明确审计过的联赛/赛季阶段窗口内
新增 deterministic test 覆盖：scoped admission 只评估指定 competition + season-index regime；source_audit_report_key 仍与 tolerance grid 对齐；fold source_slice_ids 只来自 scope 内窗口；CLI options 能解析 scope competition、season 与 min/max competition season index
生成 scoped competition replacement reranker admission report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_scoped_competition_admission_quality_edge_v1.json；report_key=historical_replacement_reranker_shadow_admission:5b0010f37937a30e；status=accepted；runtime_profile_candidate_allowed=true；shadow_allowed=true
scope 口径：source_item_count=67、source_final_answer_count=56；scope_competition_ids=[ENG_CHAMPIONSHIP,FRA_LIGUE_2]；scoped_item_count=19、scoped_final_answer_count=19；覆盖 ENG_CHAMPIONSHIP 的 2020-2021 到 2024-2025 season indexes 1-5，以及 FRA_LIGUE_2 的 2020-2021、2022-2023、2023-2024、2024-2025 season indexes 1-4
scoped overall 结果：shadow_final_answer_count=17；changed_from_model_top_count=5；hit_delta_vs_model_top_count=+1；profit_loss_delta_vs_model_top=+4.1；roi_delta_vs_model_top=+0.12058823529411763；harm_count_vs_model_top=0；warnings=[]
scoped fold admission 结果：fold_count=12；active_fold_count=9；failed_fold_count=0；active_competition_fold_count=2；active_season_fold_count=3；active_rolling_fold_count=4；说明在更窄的高质量 replacement evidence window 内仍能守住 no-harm 和 fold gate
阶段性结论：candidate replacement/reranker 路径已有一个更保守的 backend governance artifact；它只能作为未来 runtime candidate review 的范围证据，不能直接变成默认生产 profile，也不能展示给用户作为策略解释。下一阶段应继续寻找能够在赛前 eligible surface 同时击败 original baseline 的 final-answer segment，或把 scoped admission 接入周期质量门禁，使每次开发后自动判断最终答案是否真的更准
README 更新 scoped replacement reranker admission 命令、report_key、核心指标与非生产边界；该能力属于“scoped final-answer replacement governance / runtime candidate evidence window / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-244 当前落地能力：

```text
按 V3.1-243 结论把 scoped replacement reranker admission 接入 recommendation benchmark quality gate；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只把离线 scoped evidence 纳入周期质量门禁
benchmark_quality_gate 新增 replacement_reranker_shadow_admission_report_path、require_replacement_reranker_shadow_admission、require_replacement_reranker_runtime_candidate_allowed、require_replacement_reranker_scoped_evidence，以及 scope/final-answer/changing/hit/P&L/ROI/harm/fold 阈值
质量门禁新增读取 HistoricalReplacementRerankerShadowAdmissionReport 的 loader；默认不传参数时 replacement reranker admission 检查为 skipped，保持既有 benchmark gate 和 cycle 行为兼容
当显式 require 时，门禁检查 report present、status=accepted、runtime_profile_candidate_allowed、shadow_allowed、scope.enabled、scoped_final_answer_count、overall_shadow_final_answer_count、changed_from_model_top、hit_delta_vs_model_top、profit_loss_delta_vs_model_top、roi_delta_vs_model_top、harm_count_vs_model_top、failed_fold_count、active competition/season/rolling fold count
RecommendationBenchmarkQualityGateResult 与 summary_json 新增 replacement_reranker_shadow_admission_* 字段，便于周期报告和后续治理面板读取，但不会向用户展示内部 reranker 策略，也不会写生产推荐 profile
新增 deterministic tests 覆盖：quality gate 可消费 accepted scoped replacement admission 并通过；shadow_only/非 scoped/hit/P&L/harm/fold 退步会被拦截；CLI 能解析 replacement admission report path、require flags 与阈值；report path loader 可直接读取 admission JSON
README 更新 benchmark gate 中 replacement reranker admission 使用命令；推荐的当前阈值来自 V3.1-243 scoped report：scope_final_answer_count=19、shadow_final_answer_count=17、changed_from_model_top_count=5、hit_delta_vs_model_top=+1、profit_loss_delta_vs_model_top>=4.0、roi_delta_vs_model_top>=0.10、harm_count_vs_model_top=0、failed_fold_count=0、active folds=2/3/4
阶段性结论：scoped replacement admission 已从“一份离线报告”升级为周期质量门禁输入；后续每次基准周期都可以把这类 evidence 纳入 pass/fail，而不是靠人工回看 JSON。下一阶段应继续寻找赛前 eligible surface 上能击败 original baseline 的 final-answer segment，或把 benchmark-cycle CLI 的 gate 参数扩展到该 replacement admission 证据，减少手工拼命令
```

V3.1-245 当前落地能力：

```text
按 V3.1-244 结论把 replacement reranker admission gate 参数透传进 benchmark-cycle；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只让周期任务能一键带上 scoped replacement evidence
benchmark_cycle CLI 新增 --gate-replacement-reranker-shadow-admission-report-path、--gate-require-replacement-reranker-shadow-admission、--gate-allow-replacement-reranker-shadow-only、--gate-require-replacement-reranker-scoped-evidence，以及 scope/final-answer/changing/hit/P&L/ROI/harm/fold 阈值
_options_from_args 会把这些 --gate-* 参数写入 RecommendationBenchmarkQualityGateOptions；_gate_options_for_schedule 仍只补 benchmark_key/strategy，因此 replacement admission 配置会随 cycle 正常进入 quality gate
cycle summary 新增 replacement_reranker_shadow_admission_present/key/status/runtime_candidate_allowed/shadow_allowed/scope_enabled/scope_final_answer_count、shadow_final_answer_count、changed_from_model_top_count、hit_delta、P&L delta、ROI delta、harm count、failed fold count、active competition/season/rolling fold count；save_cycle_report 会把这些字段保存在 summary_json，便于趋势巡检
默认未传 gate replacement 参数时，cycle 行为不变，replacement admission 字段为 false/None/0；不新增 DB column、不改迁移脚本、不影响已有 persisted cycle 表结构
新增 deterministic tests 覆盖：cycle summary 会携带 replacement admission evidence；cycle CLI 能解析所有 gate replacement admission 参数并映射到 nested gate_options；既有 runtime profile preset 与 segment replay preset 仍保持兼容
README 更新 benchmark-cycle 示例，把 V3.1-243 的 scoped replacement admission report 和 V3.1-244 的门禁阈值直接接入周期命令；该能力属于“benchmark-cycle replacement admission quality gate wiring / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
阶段性结论：周期质量门禁现在能把 scoped replacement admission 与 benchmark、lifecycle、runtime switch、segment replay 一起检查；这解决了“离线证据无法进入日常质量判断”的问题。下一阶段应回到核心准确率搜索：寻找赛前 eligible surface 上能同时击败 original baseline、hit/P&L/ROI/no-harm/fold 都过门的 final-answer segment，而不是继续堆治理壳
```

V3.1-246 当前落地能力：

```text
按 V3.1-245 结论回到核心准确率搜索，补强 final-answer quality-signal profile grid 的 original-candidate no-harm 保护；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只防止质量信号候选在总体指标相近时局部伤害原始最终答案
HistoricalFinalAnswerQualitySignalProfileGridOptions 新增 max_final_hit_harm_count_vs_baseline 与 max_profit_loss_harm_count_vs_baseline，默认均为 0；候选/report 新增 final_answer_changed_count_vs_baseline、final_hit_harm_count_vs_baseline、profit_loss_harm_count_vs_baseline，并写入 deltas、competition_summary、grid gate_thresholds 与 reason_codes
新增 rejection reason：quality_signal_profile:final_hit_harm_count_above_threshold 与 quality_signal_profile:profit_loss_harm_count_above_threshold；candidate cache key 会纳入新增 gate options，避免旧缓存绕过 no-harm 逻辑
CLI nutmeg-recommendation-final-answer-quality-signal-profile-grid 新增 --max-final-hit-harm-count-vs-baseline 与 --max-profit-loss-harm-count-vs-baseline；默认不允许相对 quality-signal-disabled original candidate 产生最终命中或 P&L 局部 harm
新增 deterministic test 覆盖：构造原始候选命中、质量信号候选改坏的 suite，确认 deltas 记录 final_answer_changed_count_vs_baseline=1、final_hit_harm_count_vs_baseline=1、profit_loss_harm_count_vs_baseline=1，且 strict threshold 会拒绝，放宽 threshold 后对应 reason 消失；CLI 参数映射同步覆盖
生成 original-harm guard rerun report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_original_harm_guard_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:6ca9f8bf1adeaa7c；slice_count=240；candidate_index=3；candidate_count=1；accepted_count=0；rejected_count=1
report 结果：affected_leg_count=12；final_answer_changed_count_vs_baseline=1；final_hit_harm_count_vs_baseline=0；profit_loss_harm_count_vs_baseline=1；final_hit_count_delta=0；roi_delta=-0.003984543880636323；profit_loss_delta=-2.597199999999999；Brier/log-loss/mean calibration 均小幅改善，但由于 local P&L harm 与 ROI/profit 退步，仍被拒绝
阶段性结论：quality-signal 路径现在不会因为概率质量小幅改善而忽略局部 P&L 伤害；该 ITA_SERIE_B narrow profile 继续保留为 rejected research evidence，不进入 runtime/default profile。下一阶段应优先搜索“赛前可见 + no-harm + ROI/P&L 正向”的 replacement/segment 候选，或把 quality-signal grid 的缓存与候选面进一步收窄，减少长跑成本
README 更新 original-harm guard report、核心指标和非生产边界；该能力属于“final-answer quality-signal original-harm protection / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-247 当前落地能力：

```text
按 V3.1-246 结论继续拆解 quality-signal original harm 的具体来源；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只把局部 harm 从聚合指标下钻到具体历史切片与最终答案变化
HistoricalFinalAnswerQualitySignalProfileGridOptions 新增 include_comparison_items、comparison_item_filter、comparison_item_limit；默认关闭，因此普通大网格和既有报告不会输出 per-slice 明细
新增 HistoricalFinalAnswerQualitySignalProfileComparisonItem；记录 slice_id、competition_id、season、baseline/candidate backtest key、baseline/candidate final-answer scenario、selected fixture ids/outcomes、final_answer_changed、affected_leg_count、actual_hit、profit_loss、profit_loss_delta、expected_hit_probability 与 item-level reason_codes
comparison_item_filter 支持 harmed/changed/all；当前默认 harmed，只输出 final_hit_harmed_vs_baseline 或 profit_loss_harmed_vs_baseline 的切片，避免大报告膨胀
CLI nutmeg-recommendation-final-answer-quality-signal-profile-grid 新增 --include-comparison-items、--comparison-item-filter、--comparison-item-limit；candidate cache key 纳入这些配置，避免无明细缓存被误当作明细报告复用
新增 deterministic test 覆盖：harm item 能准确记录 slice、competition、final_answer_changed、final_hit_harmed、profit_loss_harmed、profit_loss_delta 与 item reason_codes；CLI 参数能映射 include/filter/limit
生成 focused harm-item report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_harm_items_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:15873fa95734415f；candidate_count=1；accepted_count=0；rejected_count=1；comparison_item_count=1；baseline_cache_status=hit
唯一 harm item：slice_id=football_data_co_uk_ita_serie_b_2022_2023_market_features_v1_rolling_window_v1_003；competition=ITA_SERIE_B；season=2022-2023；baseline final answer=1x1:single，选择 Cagliari vs Modena home_win，actual_hit=true，profit_loss=+1.62；candidate final answer=2x1:multiple，选择 Cagliari vs Modena 与 Brescia vs Perugia 的 home_win/draw 复式，actual_hit=true，但 total_stake 从 2.0 扩到 8.0，profit_loss=-0.9771999999999998，profit_loss_delta=-2.5972
阶段性结论：这个 quality-signal 候选的核心失败不是命中率，而是多选/复式展开后的资金效率；下一阶段应聚焦最终答案仲裁的 stake-efficiency 或 multiple-selection ROI floor，防止 1x1 正收益答案被替换成命中但亏损的复式答案
README 更新 per-slice harm-item report、核心定位和下一步方向；该能力属于“quality-signal harm item diagnostics / stake-efficiency evidence / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-248 当前落地能力：

```text
按 V3.1-247 结论尝试 stake-efficiency / multiple-selection ROI 保护实验；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只在历史最终答案仲裁层增加默认关闭的实验开关并用真实切片验证
HistoricalRecommendationBacktestOptions 新增 final_answer_stake_efficiency_guard、final_answer_stake_efficiency_penalty_strength、final_answer_stake_efficiency_max_stake_multiplier、final_answer_stake_efficiency_min_roi、final_answer_stake_efficiency_modes 与 final_answer_stake_efficiency_scope；默认 guard=false，因此普通推荐、历史回测与生产默认路径行为不变
历史最终答案排序在 opt-in 时会对高 total_stake/unit_stake 暴露或低 ROI 的目标 mode 候选扣分；scope=all 表示全局作用，scope=quality_signal_affected 表示仅当 quality-signal penalty 本身命中该最终答案腿时才作用
summary/backtest/comparison/suite key 全部纳入 stake-efficiency 参数；报告输出 final_answer_stake_efficiency_stake_multiplier、penalty_score、penalty_applied、penalty_option_count，并在 suite summary 中聚合 baseline/candidate penalty option count，避免旧缓存误判新实验
CLI nutmeg-recommendation-historical-backtest 与 nutmeg-recommendation-final-answer-quality-signal-profile-grid 新增 stake-efficiency 参数透传；quality-signal grid 可把该实验和原始 no-harm gate 组合起来验证
新增 deterministic tests 覆盖：stake-efficiency guard 默认关闭；开启后可把高 stake-multiplier 的 multiple candidate 排到 1x1 safe answer 之后；mode/scope/max-stake 参数可关闭该 penalty；quality-signal scoped 模式只在 quality-signal affected multiple 上生效；quality-signal profile grid CLI 参数映射同步覆盖
生成 global stake-efficiency rerun report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_stake_efficiency_guard_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:e39d534fa5d01ff7；candidate_count=1；accepted_count=0；rejected_count=1
global 实验结论：它压住了原 comparison-item harm，但在 recomputed baseline 中对 720 个 final-answer options 施加 penalty，并把 candidate baseline 拉到 candidate_roi=-0.03392955525、candidate_profit_loss=-16.28618652；因此不能作为全局策略
生成 scoped stake-efficiency rerun report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_narrow_quality_signal_profile_grid_scoped_stake_efficiency_guard_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:8003cbc023c3f56b；scope=quality_signal_affected；candidate_count=1；accepted_count=0；rejected_count=1
scoped 实验结论：baseline penalty option count=0，说明 scope 没误伤 quality-signal-disabled baseline；但 candidate 仍产生 final_hit_harm_count_vs_baseline=6、profit_loss_harm_count_vs_baseline=6、roi_delta=-0.04763484264968282、profit_loss_delta=-27.165399999999998，因此也不能晋级
阶段性结论：stake-efficiency guard 已证明“可诊断、可回放、可拒绝”，但不是当前核心准确率的有效提升方向。下一阶段应停止沿该 quality-signal stake penalty 继续调参，回到高质量 replacement/segment 或 final-answer scorer 的可验证正向候选搜索，所有候选仍需 no-harm、ROI/P&L、probability-quality 与 fold gate 同时通过
README 更新 stake-efficiency 两份 rejected report、核心指标和非生产边界；该能力属于“stake-efficiency negative experiment / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-249 当前落地能力：

```text
按 V3.1-248 结论停止沿 quality-signal stake penalty 调参，回到 final-answer segment penalty 的可验证正向候选；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只强化历史 grid 的原始最终答案 no-harm 门禁
historical_final_answer_segment_penalty_grid 新增 max_final_hit_harm_count_vs_baseline 与 max_profit_loss_harm_count_vs_baseline；默认均为 0，因此 aggregate-positive 候选如果局部伤害原始正确答案或原始正收益答案，会被直接拒绝
segment penalty candidate report 新增 final_answer_changed_count_vs_baseline、final_hit_harm_count_vs_baseline、profit_loss_harm_count_vs_baseline；rejection reason 新增 segment_penalty:final_hit_harm_count_above_threshold 与 segment_penalty:profit_loss_harm_count_above_threshold；grid summary 记录对应 gate thresholds
CLI nutmeg-recommendation-final-answer-segment-penalty-grid 新增 --max-final-hit-harm-count-vs-baseline 与 --max-profit-loss-harm-count-vs-baseline；候选 key/报告 key 纳入新门禁参数，避免旧报告误当作 no-harm 结果
新增 deterministic tests 覆盖：候选在总命中/总 P&L 不变但局部伤害原始答案时会被默认 no-harm gate 拒绝；放宽阈值后可通过；CLI 参数映射和 summary gate thresholds 同步覆盖
生成 GER regime original-harm guard report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_v1.json；report_key=historical_final_answer_segment_penalty_grid:daace3dcb237c122；candidate_count=30；accepted_count=12；rejected_count=18
真实切片结论：18 个候选因 segment_penalty:profit_loss_harm_count_above_threshold 被拒绝；最佳 accepted candidate 仍为 GER_BUNDESLIGA / 3x1 / single / min_competition_season_index=4 / strength=0.02，final_answer_changed_count_vs_baseline=2，final_hit_harm_count_vs_baseline=0，profit_loss_harm_count_vs_baseline=0，final_hit_count_delta=+2，roi_delta=+0.07033333333333333，profit_loss_delta=+4.220000000000001，Brier/log-loss/calibration 均改善
阶段性结论：当前 GER regime segment penalty 在更严格的原始答案 no-harm 口径下仍成立，证据质量高于 V3.1-214/215 早期 grid；下一阶段应把同一 no-harm 口径接入 rolling admission / production proposal / runtime replay，确认所有晋级门禁都使用同一套原始答案保护指标
README 更新 original-harm guard report、核心指标和非生产边界；该能力属于“final-answer segment no-harm governance / core accuracy tuning”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-250 当前落地能力：

```text
按 V3.1-249 结论把 original final-answer no-harm 口径从 segment penalty grid 下沉到 rolling admission / production proposal / runtime replay；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只统一核心候选晋级链路的伤害定义
rolling admission 新增 max_overall_final_hit_harm_count_vs_baseline、max_overall_profit_loss_harm_count_vs_baseline、max_fold_final_hit_harm_count_vs_baseline、max_fold_profit_loss_harm_count_vs_baseline；fold/report/summary 输出 final_hit_harm_count_vs_baseline 与 profit_loss_harm_count_vs_baseline，并保留旧 harm_count_vs_baseline 兼容字段
production proposal 新增 max_final_hit_harm_count_vs_baseline 与 max_profit_loss_harm_count_vs_baseline；proposal summary、check、runtime rule evidence、rollback_conditions 均写入新 no-harm 指标，避免 holdout profile artifact 丢失收益伤害证据
runtime replay 新增 max_final_hit_harm_count_vs_baseline 与 max_profit_loss_harm_count_vs_baseline；replay report/check/summary 输出并校验两类 no-harm 指标，避免只用旧 harm_count 判断命中伤害而漏掉 profit/loss 伤害
新增 deterministic tests 覆盖：rolling admission 在总 P&L 不回撤但局部 profit/loss 伤害原始答案时会被拒绝；production proposal 会阻断带 profit_loss_harm 的 accepted rolling report；runtime replay 会阻断 replay 中的局部 profit_loss_harm；CLI 参数映射同步覆盖
生成 stricter rolling admission report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_rolling_admission_v1.json；report_key=historical_final_answer_segment_penalty_rolling_admission:8fc3817d5f5a6bca；status=accepted；failed_fold_count=0；overall final_hit_harm_count_vs_baseline=0；overall profit_loss_harm_count_vs_baseline=0
生成 stricter production proposal report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_production_proposal_v1.json；report_key=historical_final_answer_segment_penalty_production_proposal:1acd8067619d4d2e；status=holdout_only；holdout_candidate_allowed=true；runtime_profile_proposal_allowed=false；唯一 failed check 为 candidate_roi
生成 runtime profile candidate：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_runtime_profile_candidate_v1.json；proposal rule evidence 和 rollback_conditions 均包含 final_hit_harm / profit_loss_harm no-harm 条件
生成 stricter runtime replay report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_runtime_replay_v1.json；report_key=historical_final_answer_segment_penalty_runtime_replay:416f7f6d44178207；status=holdout_replay_passed；runtime_replay_allowed=false；holdout_replay_allowed=true；唯一 failed check 为 candidate_roi；final_hit_harm_count_vs_baseline=0；profit_loss_harm_count_vs_baseline=0
阶段性结论：GER regime segment penalty 的 no-harm 证据现在从 grid 到 replay 保持一致，但绝对 ROI 仍未过 0，因此只能继续作为 holdout/profile candidate，不进入普通用户路径或生产默认。下一阶段应把 benchmark quality gate / cycle preset 也升级为读取这两个 explicit no-harm 字段，避免周期门禁只看旧 harm_count 兼容字段
README 更新 rolling/proposal/profile/replay 报告路径、核心指标和非生产边界；该能力属于“final-answer segment no-harm promotion chain / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-251 当前落地能力：

```text
按 V3.1-250 结论把 benchmark quality gate / cycle preset 升级为读取 explicit final-answer segment no-harm 字段；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只让周期门禁使用与 grid/admission/proposal/replay 一致的伤害定义
RecommendationBenchmarkQualityGateOptions 新增 max_final_answer_segment_penalty_runtime_replay_final_hit_harm_count_vs_baseline 与 max_final_answer_segment_penalty_runtime_replay_profit_loss_harm_count_vs_baseline；默认均为 0；旧 max_final_answer_segment_penalty_runtime_replay_harm_count_vs_baseline 保留用于兼容旧报告
final_answer_segment_penalty_runtime_replay preset 的默认 report path 更新为 original-harm guard runtime replay：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_runtime_replay_v1.json
quality gate checks 新增 final_answer_segment_penalty_runtime_replay_final_hit_harm_count 与 final_answer_segment_penalty_runtime_replay_profit_loss_harm_count；summary 新增 final_answer_segment_penalty_runtime_replay_final_hit_harm_count 与 final_answer_segment_penalty_runtime_replay_profit_loss_harm_count；旧 final_answer_segment_penalty_runtime_replay_harm_count 继续输出
benchmark cycle 的 summary defaults、gate summary extraction 与 CLI options 同步透传两个 explicit no-harm 字段，cycle 持久化 summary_json 可直接看到 final_hit_harm / profit_loss_harm，不再只能依赖旧 harm_count
新增 deterministic tests 覆盖：quality gate 在旧 harm_count=0 但 profit_loss_harm_count=1 时会失败；quality gate CLI 参数映射；segment penalty preset 默认两个 explicit harm threshold 均为 0 且指向 original-harm guard replay；benchmark cycle CLI/preset/summary 同步透传新字段
生成 benchmark gate smoke report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_ger_regime_original_harm_guard_benchmark_gate_smoke_v1.json；status=passed；failed_checks=[]；runtime replay key=historical_final_answer_segment_penalty_runtime_replay:416f7f6d44178207；final_hit_harm_count=0；profit_loss_harm_count=0
阶段性结论：segment penalty 的 explicit no-harm 证据现在从 candidate search 到 cycle gate 都已统一；候选仍因绝对 candidate_roi<0 只允许 holdout，不进入普通用户路径或生产默认。下一阶段应继续寻找绝对 ROI 过 0 的正向候选，或把当前 holdout 候选扩展到更大样本验证后再评估是否有生产候选资格
README 更新 benchmark gate/cycle explicit no-harm 行为、smoke 报告路径和非生产边界；该能力属于“cycle quality gate no-harm governance / core accuracy evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-252 当前落地能力：

```text
按 V3.1-251 结论继续寻找绝对 ROI 过 0 的正向候选；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只把 absolute candidate ROI floor 固化到 final-answer segment penalty 历史搜索工具
historical_final_answer_segment_penalty_grid 新增 min_candidate_roi；candidate deltas 输出 candidate_roi；当候选绝对 ROI 低于阈值时新增拒绝原因 segment_penalty:candidate_roi_below_floor；grid summary 记录 min_candidate_roi，避免“相对少亏”被误当成“正收益候选”
CLI nutmeg-recommendation-final-answer-segment-penalty-grid 新增 --min-candidate-roi；新增 deterministic test 覆盖：候选 final_hit/ROI/P&L 相对 baseline 改善但 candidate_roi 仍小于 0 时会被 ROI floor 拒绝；CLI 参数映射和 summary gate threshold 同步覆盖
生成 focused positive ROI floor probe：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_final_answer_segment_penalty_positive_roi_floor_probe_v1.json；report_key=historical_final_answer_segment_penalty_grid:78f194bae48b41ea；candidate_count=12；accepted_count=0；rejected_count=12
probe 覆盖 30 个 core 5-season slices、10738 场 fixture、32214 个 prediction；检查 EPL / ESP_LA_LIGA / GER_BUNDESLIGA 的 forward-safe 3x1 single、min_competition_season_index=4、strength=0.02/0.08、max_average_leg_decimal_odds none/1.30；所有候选均因 segment_penalty:candidate_roi_below_floor 被拒绝
最佳 rejected candidate 仍为 GER_BUNDESLIGA / 3x1 / single / min_competition_season_index=4；它把 final hits 从 23/30 提高到 25/30，roi_delta=+0.07033333333333333，profit_loss_delta=+4.220000000000001，final_hit_harm_count_vs_baseline=0，profit_loss_harm_count_vs_baseline=0，但 absolute candidate_roi=-0.015897931333333268，因此不能进入普通用户路径或生产默认
阶段性结论：segment penalty 方向的 no-harm holdout 候选质量更清楚了，但当前 focused probe 未找到正 ROI 候选；下一阶段应优先回到已有正 ROI replacement/value-guard 证据线或给 grid runner 增加 batch/progress/cache 后再做更宽搜索，而不是继续无界等待大网格
README 更新 absolute ROI floor、probe 报告路径、核心指标和非生产边界；该能力属于“positive ROI floor governance / core accuracy candidate search”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-253 当前落地能力：

```text
按 V3.1-252 结论回到已有正 ROI 的 short-odds replacement / value-guard 证据线；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只增强候选晋级链的 explicit no-harm 定义
replacement_short_odds_runtime_shadow、suite_gate、rolling_admission、production_proposal 新增 final_hit_harm_count_vs_original 与 profit_loss_harm_count_vs_original；旧 harm_count_vs_original 保留为兼容字段，语义上继续对应 profit/loss harm
CLI 同步新增 explicit harm threshold 参数：runtime/suite/proposal 支持 max_final_hit_harm_count_vs_original 与 max_profit_loss_harm_count_vs_original；rolling admission 支持 overall/fold 两层 final-hit 与 profit-loss harm 上限；默认 fallback 仍兼容旧 max_harm_count_vs_original
新增 deterministic tests 覆盖：runtime shadow 在“利润没有变差但原命中被替换为未命中”时会被 final-hit harm 拦截；suite gate、rolling admission、production proposal 与 CLI loader 均能输出/透传两个 explicit no-harm 字段；production proposal 会拦截 runtime final-hit harm
生成 explicit harm runtime replay：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_explicit_harm_guard_v1.json；report_key=historical_short_odds_runtime_shadow_replay:03efacfb60b79d89；status=shadow_replay_passed；final_answer_count=30；changed_final_answer_count=17；hit-rate delta=0；roi_delta=+0.017638871546666643；profit_loss_delta=+1.058332292799999；harm_count=0；final_hit_harm_count=0；profit_loss_harm_count=0
生成 explicit harm rolling admission：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_rolling_admission_explicit_harm_guard_v1.json；report_key=historical_short_odds_rolling_admission:73ec1f43f192febe；status=accepted；active_competition_fold_count=4；active_season_fold_count=5；active_rolling_fold_count=4；failed_fold_count=0；overall 三类 harm count 均为 0
生成 explicit harm production proposal：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_production_proposal_explicit_harm_guard_v1.json；report_key=historical_short_odds_production_proposal:7d6a51fccc6f60d8；status=production_proposal_ready；ready_competition_ids=EPL/FRA_LIGUE_1/GER_BUNDESLIGA/ITA_SERIE_A；ESP_LA_LIGA 继续 excluded；proposal/runtime/rolling evidence 的 final-hit 与 profit-loss harm 均为 0
阶段性结论：short-odds replacement 的正 ROI 证据线现在可区分“原命中被破坏”和“收益被破坏”两种伤害，避免仅靠旧 harm_count 混合判断；该能力仍是内部质量门禁和候选晋级证据，不进入普通用户前端，不暴露内部策略，不写默认 profile
下一阶段应把 explicit harm proposal 继续接入 promotion smoke、runtime profile promotion / activation / switch 与 benchmark quality gate/cycle preset，或者把同一 no-harm 口径迁移到更大联赛样本的 value-guard 证据线
README 更新 explicit harm report 路径、核心指标和非生产边界；该能力属于“short-odds replacement no-harm governance / core accuracy evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-254 当前落地能力：

```text
按 V3.1-253 结论把 short-odds replacement 的 explicit no-harm 口径继续接入 promotion smoke、runtime profile promotion / activation / switch、benchmark quality gate 与 benchmark cycle；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只强化候选晋级链的周期门禁
promotion_smoke 新增 max_final_hit_harm_count_vs_original 与 max_profit_loss_harm_count_vs_original，并同时校验 proposal/runtime/rolling evidence 中的 final-hit harm 与 profit-loss harm；required rollback conditions 增加 production final-hit / profit-loss harm 超阈值禁用条件
runtime_profile_promotion 新增 runtime、rolling overall、post-promotion runtime 三段 explicit harm checks；summary 输出 runtime_final_hit_harm_count_vs_original、runtime_profit_loss_harm_count_vs_original、rolling_overall_* 与 post_promotion_runtime_* 字段
runtime_profile_activation 新增 candidate runtime explicit harm checks；runtime_profile_switch 新增 activated runtime explicit harm checks；二者 summary 均输出对应 final-hit / profit-loss harm count，且默认仍只生成 artifact，不写默认 profile
benchmark_quality_gate 新增 runtime_profile_switch_replay_final_hit_harm_count_vs_original 与 runtime_profile_switch_replay_profit_loss_harm_count_vs_original 两个门禁字段；runtime profile switch preset 默认要求二者均为 0；benchmark_cycle 的 summary defaults、gate summary extraction 与 CLI options 同步透传这两个字段
新增 deterministic tests 覆盖：promotion smoke 拦截 runtime final-hit harm；runtime profile promotion 拦截 profit-loss harm；activation 拦截 candidate final-hit harm；switch 拦截 activated profit-loss harm；benchmark gate 拦截 switch replay explicit harm；benchmark cycle CLI/summary 透传新字段
生成 explicit harm promotion smoke：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_promotion_smoke_explicit_harm_guard_v1.json；report_key=historical_short_odds_promotion_smoke:f295bb3e0327d68d；passed=true；runtime_profile_written=false；public_response_changed=false；production_recommendation_changed=false
生成 post-smoke runtime replay：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_shadow_replay_promotion_explicit_harm_guard_v1.json；report_key=historical_short_odds_runtime_shadow_replay:2d91d079c72ff0f7；status=shadow_replay_passed；final_answer_count=30；changed_final_answer_count=17；roi_delta=+0.017638871546666643；profit_loss_delta=+1.058332292799999；三类 harm count 均为 0
生成 runtime profile promotion report 与 candidate artifact：report_key=historical_short_odds_runtime_profile_promotion:38f936543f007a07；promotion_ready=true；blockers=[]；candidate replay report_key=historical_short_odds_runtime_shadow_replay:e978194f43701550；三类 harm count 均为 0
生成 activation report 与 activated artifact：report_key=historical_short_odds_runtime_profile_activation:926a919521159cf1；activation_ready=true；blockers=[]；activated replay report_key=historical_short_odds_runtime_shadow_replay:404bc07376801595；三类 harm count 均为 0
生成 runtime profile switch report：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_explicit_harm_guard_v1.json；report_key=historical_short_odds_runtime_profile_switch:044049ee150b67eb；switch_ready=true；default_profile_write_requested=false；default_profile_written=false；blockers=[]；staged replay report_key=historical_short_odds_runtime_shadow_replay:404bc07376801595；三类 harm count 均为 0
生成 benchmark gate smoke：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_benchmark_gate_explicit_harm_smoke_v1.json；gate_key=recommendation_benchmark_quality_gate:all:any；status=passed；failed_checks=[]；runtime_profile_switch_ready=true；runtime_profile_switch_replay_passed=true；runtime_profile_switch_replay_roi_delta=+0.017638871546666643；switch replay final-hit/profit-loss harm 均为 0
生成 benchmark cycle smoke：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_replacement_short_odds_runtime_profile_switch_benchmark_cycle_explicit_harm_smoke_v1.json；cycle_key=recommendation_benchmark_cycle:explicit-harm-smoke:once:gate；status=passed；gate_status=passed；failed_checks=[]；warnings 仅为未保存当前 benchmark report 与无持久化 history 的 bootstrap 预期提示；cycle summary 已包含 switch replay final-hit/profit-loss harm count
阶段性结论：short-odds replacement 的正 ROI 候选现在从 proposal 到 cycle 都使用统一 no-harm 定义，且默认写入、普通用户前端、实时 API、VPS 与自动下注均未触发。下一阶段应优先把同一 no-harm 周期门禁迁移到更大联赛样本的 value-guard / replacement reranker 正向证据线，或开始构造更真实的赛前特征切片来提高核心推荐准确率
README 更新 explicit harm promotion-to-cycle 报告路径、核心指标、CLI 参数和非生产边界；该能力属于“short-odds replacement promotion-cycle no-harm governance / core accuracy evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-255 当前落地能力：

```text
按 V3.1-254 结论把 explicit no-harm 口径迁移到更大联赛样本的 replacement reranker / value-guard 正向证据线；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只强化 scoped reranker admission 与周期质量门禁
replacement_reranker_shadow_gate 新增 final_hit_harm_count_vs_original、final_hit_harm_count_vs_model_top、profit_loss_harm_count_vs_original、profit_loss_harm_count_vs_model_top；旧 harm_count_vs_* 继续保留为兼容字段，语义上仍对应 profit-loss harm
replacement_reranker_shadow_gate options/CLI 新增 max_final_hit_harm_count_vs_model_top、max_profit_loss_harm_count_vs_model_top、max_final_hit_harm_count_vs_original、max_profit_loss_harm_count_vs_original；未显式传入时回退到旧 max_harm_count 阈值，避免旧命令失效
replacement_reranker_shadow_admission 新增 overall/fold 两层 explicit no-harm 字段和阈值；fold failure reasons 可分别标记 final_hit_harm_count_vs_model_top_above_threshold 与 profit_loss_harm_count_vs_model_top_above_threshold；summary_json 输出 overall_final_hit_harm_count_* 与 overall_profit_loss_harm_count_*
benchmark_quality_gate 新增 replacement_reranker_final_hit_harm_count_vs_model_top 与 replacement_reranker_profit_loss_harm_count_vs_model_top 两个门禁字段；benchmark_cycle 的 summary defaults、gate summary extraction 与 CLI options 同步透传这两个字段
新增 deterministic tests 覆盖：shadow gate 拦截“model-top 命中但 reranker 改成未命中且盈亏未受损”的 final-hit harm；shadow admission 拦截 overall/fold final-hit harm；benchmark gate 拦截 admission explicit harm；benchmark cycle CLI/summary 透传新字段
生成 scoped competition admission explicit harm report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_scoped_competition_admission_explicit_harm_guard_v1.json；report_key=historical_replacement_reranker_shadow_admission:7c42370ef7dce5ec；status=accepted；runtime_profile_candidate_allowed=true；shadow_allowed=true
该 admission 覆盖 ENG_CHAMPIONSHIP 与 FRA_LIGUE_2 的 scoped evidence：scope final_answer_count=19；overall_shadow_final_answer_count=17；changed_from_model_top_count=5；hit_delta_vs_model_top=+1；profit_loss_delta_vs_model_top=+4.1；roi_delta_vs_model_top=+0.12058823529411763；harm_count_vs_model_top=0；overall_final_hit_harm_count_vs_model_top=0；overall_profit_loss_harm_count_vs_model_top=0；active_competition_fold_count=2；active_season_fold_count=3；active_rolling_fold_count=4；failed_fold_count=0
生成 replacement reranker benchmark gate explicit harm smoke：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_benchmark_gate_explicit_harm_smoke_v1.json；gate_key=recommendation_benchmark_quality_gate:all:any；status=passed；failed_checks=[]；explicit model-top final-hit/profit-loss harm 均为 0
生成 replacement reranker benchmark cycle explicit harm smoke：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_replacement_reranker_benchmark_cycle_explicit_harm_smoke_v1.json；cycle_key=recommendation_benchmark_cycle:reranker-explicit-harm-smoke:once:gate；status=passed；gate_status=passed；failed_checks=[]；warnings 仅为未保存当前 benchmark report 与无持久化 history 的 bootstrap 预期提示；cycle summary 已包含 reranker final-hit/profit-loss harm count
阶段性结论：更大联赛样本的 scoped replacement reranker 正 ROI 证据线现在与 short-odds replacement 共享同一 explicit no-harm 周期门禁口径；它仍是内部质量证据和 runtime candidate 资格，不进入普通用户路径、不写默认 profile、不暴露内部策略
下一阶段应继续构造更真实的赛前特征切片，尤其把候选替换从 missed-leg audit surface 迁移到真正赛前可见的 candidate pool/prediction/odds snapshot surface；也可以为 replacement reranker 增加 profile promotion/activation/switch 阶段，但必须先避免把 missed-leg 诊断面误当作生产推荐面
README 更新 replacement reranker explicit harm gate/cycle 命令、报告路径、核心指标和非生产边界；该能力属于“replacement reranker scoped no-harm governance / core accuracy evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-256 当前落地能力：

```text
按 V3.1-255 结论继续把 replacement reranker 从 missed-leg 诊断证据迁移到真实赛前可用面；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只补强“证据来源”门禁，避免把后视诊断面误当生产推荐面
replacement_reranker_shadow_admission 新增 source_surface summary：source_surface_kind、source_surface_missed_legs_only、target_filter、final_answer_count、selected_leg_count、missed_leg_count、replacement_simulation_count、actual_replacement_opportunity_count、model_top improvement/harm count；通过 target_filter.missed_legs_only=false 判断 prematch_replacement_surface，通过 true 判断 missed_leg_diagnostic_surface，缺失则 unknown
admission options/CLI 新增 require_prematch_source_surface / --require-prematch-source-surface；开启后 source_surface_prematch check 必须通过，否则 accepted 会降为 shadow_only，不允许 runtime_profile_candidate_allowed
benchmark_quality_gate 新增 require_replacement_reranker_prematch_source_surface / --require-replacement-reranker-prematch-source-surface；当显式 require replacement admission 时，source_surface_kind 必须等于 prematch_replacement_surface，否则门禁 failed。benchmark_cycle 同步新增 --gate-require-replacement-reranker-prematch-source-surface，并在 cycle summary 透传 source_surface_kind、missed_legs_only、selected_leg_count、final_answer_count
新增 deterministic tests 覆盖：admission 能记录 prematch source surface；missed-leg source surface 在 require 时被降级阻断；benchmark quality gate 拦截 missed-leg diagnostic source；benchmark gate/cycle CLI 参数映射与 cycle summary 透传 source surface 字段
生成 prematch source-surface guard admission report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_reranker_shadow_admission_source_surface_guard_v1.json；report_key=historical_replacement_reranker_shadow_admission:9d3a78550b962ccd；status=rejected；runtime_profile_candidate_allowed=false；shadow_allowed=false
source surface 结果：source_surface_kind=prematch_replacement_surface；source_surface_missed_legs_only=false；selected_leg_count=128；final_answer_count=240；该报告证明输入已是完整赛前 replacement surface，而不是 missed-leg diagnostic surface
效果门禁结果：相对 model-top replacement 仍有正向表现，hit_delta_vs_model_top=+4、profit_loss_delta_vs_model_top=+16.32；但相对 original final answer 仍退步，hit_delta_vs_original=-4、profit_loss_delta_vs_original=-5.539999999999999、overall_final_hit_harm_count_vs_original=15、failed_fold_count=18，因此继续拒绝 runtime promotion
阶段性结论：现在系统已能同时回答两个问题：证据是不是赛前可见面，以及效果是否足够好。当前 pre-match surface 来源合格但效果不合格；之前 scoped missed-leg admission 效果好但来源不合格。因此二者都不能直接进入普通用户推荐路径。下一阶段应继续提升真实赛前候选排序/概率本体，而不是放宽门禁或把诊断成绩上线
README 更新 source-surface guard report、CLI flags、核心指标和非生产边界；该能力属于“prematch surface evidence gate / replacement reranker promotion safety / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-257 当前落地能力：

```text
按 V3.1-256 结论回到真实赛前最终答案质量函数调试；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只给 final-answer quality-signal profile grid 增加严格 watchlist/近通过候选口径，避免继续在同类实验中无目标循环
final_answer_quality_signal_profile_grid options 新增 watchlist_max_candidate_roi_shortfall、watchlist_min_final_hit_count_delta、watchlist_min_roi_delta、watchlist_min_profit_loss_delta、watchlist_max_final_hit_harm_count_vs_baseline、watchlist_max_profit_loss_harm_count_vs_baseline；默认关闭，显式开启后也只记录候选，不改变 production/runtime/default profile
候选模型新增 watchlist_eligible 与 watchlist_reason_codes；grid report 新增 watchlist_count、watchlist_candidates、best_watchlist_candidate、watchlist_candidate_keys 与对应 summary 字段；merge report 和 competition_summary 同步统计 watchlist_count / watchlist_reason_counts
watchlist 晋级边界：候选必须已经被拒绝，且除 quality_signal_profile:candidate_roi_below_floor 外没有其它 blocking rejection；同时 candidate_roi 距离 ROI floor 不能超过 shortfall，上述 final-hit/ROI/P&L delta 和 final-hit/profit-loss harm 阈值必须满足。也就是说“相对变好但绝对 ROI 只差一点”可以进入内部 follow-up 队列，“没有改善”不能进入 watchlist
新增 deterministic tests 覆盖：默认关闭时 ROI floor 拒绝不会产生 watchlist；显式开启且只差 ROI floor 时会产生 watchlist candidate；CLI 参数映射 watchlist 阈值；既有 cache / merge / multi-manifest 行为保持通过
生成真实历史 smoke report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_ita_serie_b_medium_price_negative_edge_quality_signal_watchlist_grid_smoke_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:f4d8c3d1fbd43079；slice_count=240；candidate_count=1；accepted_count=0；watchlist_count=0
smoke 使用 combined core + expanded A-leagues suite 的轻量 1x1/2x1/3x1 single-only replay；candidate_roi=-0.0466076，profit_loss=-22.371648，deltas 全为 0，拒绝原因为 candidate_roi_below_floor 与 objective_improvement_missing；watchlist_reason_codes 指出 blocking_rejection_reasons_present、candidate_roi_shortfall_above_limit、final_hit_count_too_low
阶段性结论：quality-signal watchlist 现在能把“近通过候选”和“没有真实最终答案改善的候选”分开；当前 ITA_SERIE_B smoke 没有改善，因此正确留在 rejected，不进入 watchlist，更不能进入普通用户路径。全量 all pass-types / single+multiple 回放本轮曾启动但超过 4 分钟未完成，已中断，下一阶段若继续该方向应先给 full grid runner 增加更好的 batch/progress/cache 或缩小候选面
README 更新 watchlist smoke report、核心指标和非生产边界；该能力属于“final-answer quality-signal watchlist / core accuracy candidate search control”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-258 当前落地能力：

```text
按 V3.1-257 的全口径回放耗时问题补强 quality-signal profile grid 的可观测性；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只让长回放具备可恢复的进度痕迹和运行耗时统计
HistoricalFinalAnswerQualitySignalProfileGridOptions 新增 progress_jsonl_path；CLI 新增 --progress-jsonl-path；candidate cache key 明确排除 progress_jsonl_path，避免仅因为输出进度文件不同而破坏缓存复用
grid report 新增 baseline_evaluation_elapsed_seconds、candidate_evaluation_elapsed_seconds、grid_evaluation_elapsed_seconds、progress_event_count；candidate 新增 evaluation_elapsed_seconds；summary_json 输出 candidate_evaluation_elapsed_seconds_by_index、slowest_candidate_index、slowest_candidate_elapsed_seconds 和 progress_jsonl_path
JSONL progress trace 事件包括 grid_started、baseline_completed、candidate_started、candidate_completed、grid_completed；candidate_completed 记录 candidate_key、cache status、status、reason_codes、watchlist_eligible、watchlist_reason_codes 和 elapsed_seconds
新增 deterministic test 覆盖：progress JSONL 文件会被重建并写入 5 类事件；report 和 candidate summary 包含耗时字段；CLI 参数映射 progress_jsonl_path；既有 watchlist/cache/merge/multi-manifest 行为保持通过
生成 progress smoke artifacts：configs/recommendations/historical_reports/euro_2024_quality_signal_profile_grid_progress_smoke_v1.json 与 configs/recommendations/historical_reports/euro_2024_quality_signal_profile_grid_progress_smoke_v1.jsonl；report_key=historical_final_answer_quality_signal_profile_grid:8a803597476d4bf1；progress_event_count=5；baseline_evaluation_elapsed_seconds=0.002443；candidate_evaluation_elapsed_seconds=0.002845；grid_evaluation_elapsed_seconds=0.006495
阶段性结论：后续再跑 full-grid / all pass-types / single+multiple 时，不需要盲等；每个候选是否启动、是否完成、是否命中缓存、失败原因和耗时都会落到 JSONL。下一阶段可以基于这个 trace 做更大的分批搜索，或者继续把慢候选拆成更窄的 pass-type/mode 子批次
README 更新 progress trace CLI、smoke report/jsonl 路径和核心指标；该能力属于“quality-signal grid observability / core accuracy search control”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-259 当前落地能力：

```text
按 V3.1-258 的 progress trace 能力启动一个 bounded real-history light batch search；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只用真实历史 combined suite 验证 medium-price negative-edge quality-signal penalty 是否值得扩大搜索
搜索范围：combined core 5 seasons + expanded A-leagues rolling windows；competition groups=ITA_SERIE_B、ENG_CHAMPIONSHIP、FRA_LIGUE_2、ESP_SEGUNDA_DIVISION；candidate-fixture-limit=12；candidate optimizer=solver；probability=[0.45,0.58]；decimal odds=[1.60,2.20]；max_model_edge=-0.02；strength=0.04；min_candidate_roi=0；watchlist shortfall=0.02；explicit no-harm thresholds 均为 0
Batch A report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_quality_signal_light_batch_a_v1.json；progress trace：同名 .jsonl；report_key=historical_final_answer_quality_signal_profile_grid:30a855c05f2a835f；pass_types=1x1/2x1/3x1；mode=single；candidate_count=4；accepted_count=0；watchlist_count=0；rejected_count=4；progress_event_count=11；baseline_candidate_final_hit_rate=0.675；baseline_candidate_roi=-0.0466076
Batch A 结论：四个候选均有 affected_leg_count，但 final_answer_changed_count_vs_baseline=0，final_hit/ROI/P&L deltas 全为 0；拒绝原因为 candidate_roi_below_floor 与 objective_improvement_missing；watchlist 未误收
Batch B report：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_quality_signal_light_batch_b_v1.json；progress trace：同名 .jsonl；report_key=historical_final_answer_quality_signal_profile_grid:e508faa940921557；pass_types=4x1/5x1/6x1/7x1/8x1；mode=single；candidate_count=4；accepted_count=0；watchlist_count=0；rejected_count=4；progress_event_count=11；baseline_candidate_final_hit_rate=0.18333333333333332；baseline_candidate_roi=-0.17425224355666663
Batch B 结论：ITA_SERIE_B / ENG_CHAMPIONSHIP / FRA_LIGUE_2 分别改变 3/5/1 个 final answer，no-harm counts 为 0，但 final_hit_count_delta、roi_delta、profit_loss_delta 均为 0，且 suite_status=mixed、candidate_roi_below_floor、objective_improvement_missing；说明固定 penalty 能改变长串关排序，但没有带来命中或收益改善
生成 light batch summary：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_quality_signal_light_batch_summary_v1.json；total_candidate_count=8；total_accepted_count=0；total_watchlist_count=0；total_rejected_count=8；progress_event_count=22
阶段性结论：这条固定 medium-price negative-edge quality-signal penalty 不值得直接扩到全口径生产候选搜索；下一阶段应转向更窄的分段信号、replacement/value-guard 正 ROI 证据线，或构造新的排序特征，而不是继续扩大同一个 penalty 网格
README 更新 light batch reports、summary artifact、核心结果和非生产边界；该能力属于“real-history quality-signal candidate search / core accuracy filtering”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-260 当前落地能力：

```text
按 V3.1-259 结论从固定 penalty 搜索转回 replacement/value-guard 正向证据线；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只把已通过 staged switch 的 short-odds replacement rule 从离线 artifact 提升为可复用的内部规则清单/加载器
新增 short_odds_replacement_rules 模块：集中定义 ShortOddsRuntimeReplacementRule、ShortOddsRuntimeRuleSet、ShortOddsReplacementRuleConstraints 与 ShortOddsReplacementRuleManifestReport；runtime shadow replay 现在复用同一套 rule model/load function，避免规则解析只藏在离线 replay 模块里
新增 rule manifest CLI：uv run nutmeg-recommendation-short-odds-replacement-rule-manifest；支持读取 activated/staged/temporary/proposal profile JSON，校验 rule_count、allowed competition count、allowed/excluded disjoint、enabled staged rule、no production/public response change、runtime shadow replay passed、rolling admission accepted/production allowed、explicit no-harm constraints 与 source report keys
生成真实五季 short-odds rule manifest：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_odds_replacement_rule_manifest_explicit_harm_guard_v1.json；report_key=short_odds_replacement_rule_manifest:352bd292399a9b33；status=ready；selected_rule_count=1；enabled_rule_count=1；allowed_competition_ids=EPL,FRA_LIGUE_1,GER_BUNDESLIGA,ITA_SERIE_A；excluded_competition_ids=ESP_LA_LIGA；blockers=[]
该 manifest 证明 staged short-odds replacement 规则具备可追溯的执行入口：runtime_shadow_replay_passed=true、rolling_admission_accepted=true、rolling_admission_production_allowed=true、max_harm_count_vs_original=0、max_final_hit_harm_count_vs_original=0、max_profit_loss_harm_count_vs_original=0、source_report_keys_present passed。它仍是内部 staging artifact，不写默认 profile、不改变普通用户最终答案
新增 deterministic tests 覆盖：staged_profile_json 提取、competition allow/exclude、constraints typed parsing、ready manifest、overlap / missing no-harm guard blocking、CLI output 写入；既有 runtime shadow replay 与 rolling admission 测试保持通过
阶段性结论：short-odds 正向证据线已经从“离线报告能跑”推进到“推荐引擎可复用的内部规则对象”。下一阶段可以在最终答案仲裁器中增加显式 opt-in 的 rule application adapter，但必须继续保持默认路径关闭，并用同一 manifest + shadow replay + rolling admission 作为门禁
README 更新 short-odds rule manifest CLI、报告路径、核心指标和非生产边界；该能力属于“short-odds replacement executable rule manifest / core accuracy staging”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-261 当前落地能力：

```text
按 V3.1-260 结论把 staged short-odds rule manifest 推进到最终答案 opt-in adapter；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只增加“已有 selection -> 候选替换 selection”的内部执行层
新增 short_odds_final_answer_adapter 模块：定义 ShortOddsFinalAnswerAdapterOptions、ShortOddsFinalAnswerReplacementAction、ShortOddsFinalAnswerAdapterResult；核心函数 apply_short_odds_final_answer_adapter 接收 RecommendationSelection、scored candidate pool 与 ShortOddsRuntimeRuleSet，默认 enable_adapter=false
adapter 行为边界：默认关闭；默认只支持 single mode；保留 locked_fixture_ids；默认 same_market_type_only；不允许重复 fixture；要求 selected/replacement decimal_odds 存在；校验 rule allowed/excluded competition；使用 rule constraints 校验 min_replacement_probability、max_replacement_decimal_odds、probability delta、odds delta 与 parlay-level hit_probability_delta_vs_original；替换后用 evaluate_parlay 重算 hit_probability、EV、ROI、risk、budget 与 rule_valid
新增 CLI：uv run nutmeg-recommendation-short-odds-final-answer-adapter-smoke；使用 deterministic candidate fixture + 真实 activated short-odds rule profile 生成 adapter smoke，证明执行层能驱动 staged rule，但仍不改变默认路径或 public response
生成 adapter smoke artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_short_odds_final_answer_adapter_smoke_explicit_harm_guard_v1.json；report_key=short_odds_final_answer_adapter:900269ab3becc4c4；status=applied；selected_rule_count=1；eligible_candidate_count=1；default_path_changed=false；public_response_changed=false
smoke 结果：adapter_selected_a 被 adapter_replacement_c 替换；hit_probability_delta=-0.006479999999999986，仍满足 rule 的 min_candidate_hit_probability_delta_vs_original=-0.025；roi_delta=+0.026792639999999923；expected_value_delta=+0.053585279999999846；rejection_reason_counts 记录 same_candidate、replacement_fixture_already_selected、replacement_probability_below_floor 与 probability_delta_vs_selected_out_of_range
新增 deterministic tests 覆盖：默认关闭不改变 selection；显式 enable 后应用 replacement 并重算 evaluation；locked fixture 不会被替换；CLI 可写出 smoke report；新增测试和模块 mypy 均通过
阶段性结论：short-odds 正向证据线已具备“manifest -> opt-in adapter -> recomputed selection”的完整内部执行链。下一阶段应把该 adapter 接入全局最终答案规划器的 shadow/opt-in 分支，用真实历史 slice candidate pool 做回放，而不是直接打开普通用户路径
README 更新 adapter CLI、smoke artifact、核心指标和非生产边界；该能力属于“short-odds final-answer opt-in adapter / core accuracy execution staging”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-262 当前落地能力：

```text
按 V3.1-261 结论把 short-odds final-answer adapter 接入全局最终答案规划器的 shadow/opt-in 分支；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只让 planner 能内部评估该 adapter
RecommendationGlobalPlannerOptions 新增 short_odds_adapter_enabled、short_odds_adapter_shadow_only、short_odds_adapter_rule_profile_path、short_odds_adapter_rule_ids、short_odds_adapter_max_report_candidates；默认 enabled=false，shadow_only=true，因此默认推荐路径完全不变
run_recommendation_global_planner 现在会在最终答案仲裁后、持久化前执行可选 adapter branch：shadow-only 只把 summary 写入内部 explanation/final_answer_decision_json；显式 opt-in 才会用 adapted_selection 替换 best option，并重新计算 planner_score、within_budget 与 final-answer arbitration
adapter branch 使用同一套 rank_candidates candidate pool、真实 ShortOddsRuntimeRuleSet loader 与 apply_short_odds_final_answer_adapter；保留 locked fixture、不跨 market、不允许重复 fixture、继续遵守 staged rule 的 allowed/excluded competition 与 no-harm constraints
公共 API sanitizer 新增过滤 short_odds_final_answer_adapter，确保普通用户结果不会看到内部策略/规则信息；public_final_answer_decision_json 仍只输出 pass_type、mode、answer_type、backup_count 等必要字段
生成 planner branch smoke artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_global_planner_short_odds_adapter_branch_smoke_v1.json；default_path_changed=false；shadow_path_changed=false；explicit_opt_in_changed=true；shadow_status=applied；opt_in_status=applied
新增 deterministic tests 覆盖：shadow-only 记录内部 summary 但不改 best fixture；显式 opt-in 替换 best option 并打 reason code；locked fixture 不被替换；API public envelope 过滤 short_odds_final_answer_adapter
阶段性结论：short-odds 正向证据线已经进入全局最终答案规划器，但默认路径仍关闭，普通用户路径不变。下一阶段应把该 planner branch 接入更真实的 historical slice/cycle quality gate，对比 default/shadow/opt-in 的 final-hit、ROI、profit/loss 与 no-harm，再决定是否继续扩大样本或保持 staging
README 更新 planner branch smoke artifact、默认关闭/影子/显式 opt-in 行为和非生产边界；该能力属于“global planner short-odds adapter staging / core recommendation quality”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-263 当前落地能力：

```text
按 V3.1-262 结论把 global planner short-odds adapter branch 接入真实历史/cycle quality gate；本轮仍不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，重点是让该 planner branch 进入统一质量门禁，而不是散落为独立 smoke
新增 global_planner_short_odds_adapter_gate 模块：定义 HistoricalGlobalPlannerShortOddsAdapterGateOptions、Check、Report；组合 planner branch smoke report 与 HistoricalShortOddsRuntimeShadowReplayReport，检查 default path 不变、shadow path 不变、explicit opt-in 确实变化、shadow/opt-in adapter applied、runtime replay passed、final-answer 样本数、ROI/profit-loss/hit-rate 不回退、harm count 为 0、public response/production recommendation 不变
新增 CLI：uv run nutmeg-recommendation-global-planner-short-odds-adapter-gate；支持读取 planner branch report 与 real-history runtime shadow replay report，输出可被 benchmark quality gate/cycle runner 消费的 gate artifact
生成真实五季 gate artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_candidate48_window4_global_planner_short_odds_adapter_gate_v1.json；report_key=global_planner_short_odds_adapter_gate:5e5847f5ba9d4166；status=passed；planner_default_path_changed=false；planner_shadow_path_changed=false；planner_explicit_opt_in_changed=true；shadow_status=applied；opt_in_status=applied
真实历史 runtime 证据：source_runtime_shadow_replay_report_key=historical_short_odds_runtime_shadow_replay:404bc07376801595；source_rule_profile_version=v3_1_competition_profiles_short_odds_runtime_enabled_explicit_harm_candidate_v1；runtime_final_answer_count=30；runtime_changed_final_answer_count=17；runtime_final_answer_hit_rate_delta=0.0；runtime_roi_delta=+0.017638871546666643；runtime_profit_loss_delta=+1.058332292799999；runtime_harm_count_vs_original=0；runtime_final_hit_harm_count_vs_original=0；runtime_profit_loss_harm_count_vs_original=0；runtime_average_hit_probability_delta=-0.014697457992009506；public_response_changed=false；production_recommendation_changed=false
benchmark_quality_gate 已新增 global_planner_short_odds_adapter_gate_report_path 与 require/threshold options；可把该 gate 作为正式质量门禁，阻止 default/shadow 路径改变、explicit opt-in 无效、runtime 样本不足、ROI/profit-loss/hit-rate 回退、harm count 上升、public/production 路径意外变化
benchmark_cycle CLI 已新增 gate-global-planner-short-odds-adapter-* 参数，cycle summary 会携带 gate key/status/passed、default/shadow/explicit opt-in path guards、runtime final-answer count、changed count、ROI delta 与 no-harm counters
新增 deterministic tests 覆盖：独立 gate pass/fail/CLI/options；benchmark_quality_gate 读取报告、阻断回退、CLI 参数映射；benchmark_cycle CLI 参数映射与 summary evidence 透传
阶段性结论：short-odds 正向证据线已经从“planner 可 shadow/opt-in 执行”推进到“统一质量门禁可持续监督”。下一阶段应扩大真实历史切片与 candidate pool，继续寻找不降低最终命中率的分联赛/分赔率段质量函数，而不是打开普通用户默认路径
README 更新 gate CLI、artifact、核心指标和非生产边界；该能力属于“global planner short-odds adapter quality gate / core accuracy staging”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-264 当前落地能力：

```text
按 V3.1-263 结论继续扩大真实历史切片与 candidate pool 监督；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，重点是把“更大样本安全但未激活”变成正式证据，避免误判成可推广
修正 replacement_short_odds_runtime_shadow：当 shadow replay 没有任何 changed final answer 时，average_hit_probability_delta_vs_original 现在返回 0.0，而不是 None；这样无变化 shadow 路径不会因为平均概率变化缺失而误触发失败
新增 deterministic test 覆盖：no-change runtime shadow replay 在 min_changed_final_answer_count=0 时可通过，并记录 average_hit_probability_delta_vs_original=0.0
使用 expanded A-league 240-slice marginal audit 生成 supplemental runtime probe：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_runtime_shadow_replay_expanded_probe_v1.json；report_key=historical_short_odds_runtime_shadow_replay:72a9022e7324777a；status=shadow_replay_passed；source_audit_report_key=historical_candidate_marginal_audit:72a403b5062990d7；final_answer_count=56；changed_final_answer_count=0；final_answer_hit_rate_delta=0.0；roi_delta=0.0；profit_loss_delta=0.0；harm/final_hit_harm/profit_loss_harm 均为 0；average_hit_probability_delta_vs_original=0.0
新增 global_planner_short_odds_adapter_sample_expansion 模块：定义 SampleExpansionOptions、Check、Report；组合 base global planner adapter gate 与多个 supplemental runtime shadow replay，输出 passed、promotion_ready、status，并把 failed blockers 与 watchlist checks 区分开
sample expansion gate 口径：base gate 必须通过，supplemental report 必须存在且不失败，supplemental/combined final-answer count 达标，combined hit-rate/ROI/profit-loss 不回退，combined harm count 为 0，public/production path 不变；但 supplemental_changed_final_answer_count 和 combined_changed_final_answer_count 作为 promotion watchlist，可把安全但未激活的证据标成 research_only
新增 CLI：uv run nutmeg-recommendation-global-planner-short-odds-adapter-sample-expansion；支持 --base-gate-report 与多个 --supplemental-runtime-shadow-replay-report，输出可归档的 sample expansion report
生成真实 sample expansion artifact：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_global_planner_short_odds_adapter_sample_expansion_v1.json；report_key=global_planner_short_odds_adapter_sample_expansion:d6af7accf570d9b7；status=research_only；passed=true；promotion_ready=false；supplemental_report_count=1；supplemental_final_answer_count=56；supplemental_changed_final_answer_count=0；combined_final_answer_count=86；combined_changed_final_answer_count=17；combined_final_answer_hit_rate_delta=0.0；combined_roi_delta=+0.0032266228439024264；combined_profit_loss_delta=+1.0583322927999959；combined harm/final_hit_harm/profit_loss_harm 均为 0；watchlist_checks=[supplemental_changed_final_answer_count]
新增 deterministic tests 覆盖：sample expansion 对安全但未激活的 supplemental evidence 返回 research_only；对 supplemental 激活且不回退返回 expansion_ready；对 harmful/failed supplemental evidence 返回 blocked；CLI 写入 report
阶段性结论：short-odds adapter 在 core gate 上仍安全，但 expanded A-league supplemental 样本没有激活替换，因此不能推广或默认开启。下一阶段应转向寻找“expanded 样本可激活且无 harm”的候选规则/候选池条件，或优先做分联赛/分赔率段的 value guard 搜索，而不是继续推动当前 short-odds rule 上线
README 更新 sample expansion CLI、expanded probe artifact、research_only 结论和非生产边界；该能力属于“supplemental historical evidence / promotion readiness guard”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-265 当前落地能力：

```text
按 V3.1-264 结论把 sample expansion evidence 接入 benchmark quality gate 与 benchmark cycle summary；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只让更大样本 research-only 证据进入统一周期质量视野
RecommendationBenchmarkQualityGateOptions 新增 global_planner_short_odds_adapter_sample_expansion_report_path、require_global_planner_short_odds_adapter_sample_expansion 与 require_global_planner_short_odds_adapter_sample_expansion_promotion_ready；默认不强制存在，也不要求 promotion_ready，避免把安全但未激活的 research_only 样本误判为发布候选
quality gate 新增 sample expansion loader、present/passed/not_blocked/promotion_ready checks 与 summary fields；blocked 报告即使未显式 require 也会失败，research_only 报告可通过 safety，但只有显式 promotion-ready gate 才会阻断 promotion_ready=false
benchmark_cycle CLI 新增 --gate-global-planner-short-odds-adapter-sample-expansion-report-path、--gate-require-global-planner-short-odds-adapter-sample-expansion 与 --gate-require-global-planner-short-odds-adapter-sample-expansion-promotion-ready；cycle summary 会携带 sample expansion key/status/passed/promotion_ready、supplemental/combined final-answer counts、combined ROI delta、combined harm count 与 watchlist checks
新增 deterministic tests 覆盖：quality gate 消费 sample expansion、可显式要求 promotion_ready、阻断 blocked regression、从 option path 加载 report；benchmark cycle summary 与 CLI options 透传 sample expansion evidence
阶段性结论：sample expansion evidence 已从单独 JSON artifact 升级为周期质量门禁输入。当前真实 artifact 仍是 research_only/promotion_ready=false，因此不能启用默认生产路径；下一阶段应继续寻找 expanded 样本真正激活且无 harm 的候选规则/候选池条件，或回到分联赛/分赔率段 value guard 搜索
README 更新 sample expansion quality gate/cycle 行为；该能力属于“supplemental historical evidence / cycle quality gate integration / promotion readiness guard”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-266 当前落地能力：

```text
按 V3.1-265 结论继续寻找 expanded 样本真正激活且无 harm 的候选规则/候选池条件；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只把 short-odds adapter 的“为什么不激活”从临时分析升级为可重复 artifact
新增 short_odds_adapter_activation_gap 模块与 CLI：uv run nutmeg-recommendation-short-odds-adapter-activation-gap；输入 candidate marginal audit 与 staged short-odds rule profile，输出 current rule path 与 probe path 两套 blocker/activation 摘要
current rule path 保留现有 allowed/excluded competition 与 constraints，用于解释当前 staged rule 为什么不改变 expanded final answers；probe path 在不改 constraints 的前提下把 allowed competition 临时替换为 audit competition set，并用 runtime shadow replay 检查是否存在 no-harm 激活样本
新增 deterministic tests 覆盖：当前 allowlist 阻断但 probe 可发现安全激活样本；约束本身阻断时输出 replacement_probability_below_floor 等原因且不产生 probe change；CLI 可写入 activation gap report
生成真实 artifact：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_gap_v1.json；report_key=short_odds_adapter_activation_gap:6d4ee6d30173eb69；status=activation_candidate_found；current_item_reason_counts={competition_not_allowed:67}
真实诊断结论：expanded audit 的 67 个 selected legs 来自 ENG_CHAMPIONSHIP/ESP_SEGUNDA_DIVISION/FRA_LIGUE_2/GER_2_BUNDESLIGA/ITA_SERIE_B，而当前 short-odds rule 只允许 EPL/FRA_LIGUE_1/GER_BUNDESLIGA/ITA_SERIE_A，因此当前路径 0 activation 是预期结果
放开到 expanded audit competition set 后，仅 FRA_LIGUE_2 出现 1 个 no-harm activation：probe_changed_final_answer_count=1；probe_final_answer_hit_rate_delta=0.01785714285714285；probe_roi_delta=0.012537313432835803；probe_profit_loss_delta=3.36；harm/final_hit_harm/profit_loss_harm 均为 0
主要剩余 blocker 是 replacement_probability_below_floor=119 与 model_top_missing=37；这说明不能直接扩大当前 rule allowlist，更合理的下一步是寻找 expanded-league 专属、更窄的 probability/odds/edge threshold candidate，并要求 final-answer 样本、ROI、hit-rate、no-harm 与 cycle gate 同时通过
README 更新 activation gap CLI、真实 report key 与非生产结论；该能力属于“short-odds adapter activation diagnostics / expanded sample rule search / core accuracy evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-267 当前落地能力：

```text
按 V3.1-266 结论继续沿 expanded-league short-odds 候选规则搜索推进；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只把 probability/odds/edge threshold 搜索变成可重复 grid artifact
新增 short_odds_adapter_activation_grid 模块与 CLI：uv run nutmeg-recommendation-short-odds-adapter-activation-grid；输入 candidate marginal audit 与 staged short-odds rule profile，在 audit competition set 上临时重放多个阈值组合
grid 每个 candidate 都通过 runtime shadow replay 检查 final-answer hit-rate delta、ROI delta、profit/loss delta、average hit probability delta 与 explicit no-harm counters；accepted 只代表内部证据通过，不代表 profile promotion 或用户可见策略
新增 deterministic tests 覆盖：放宽阈值后 no-harm 候选可 accepted；放宽导致 profit/loss harm 时必须 rejected；CLI 可写入 activation grid report
生成真实 artifact：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_grid_v1.json；report_key=short_odds_adapter_activation_grid:dfe7705790dcd175；status=accepted_candidate_found；candidate_count=144；accepted_count=31；rejected_count=113
best_candidate_key=short_odds_adapter_activation_grid_candidate:adf934b22d9e0f78；changed_final_answer_count=7/56；final_answer_hit_rate_delta=0.0535714285714286；roi_delta=0.041194029850746244；profit_loss_delta=11.039999999999996；harm/final_hit_harm/profit_loss_harm 均为 0；changed competitions 为 GER_2_BUNDESLIGA=3、ENG_CHAMPIONSHIP=2、ESP_SEGUNDA_DIVISION=1、FRA_LIGUE_2=1
best candidate 的临时阈值为 min_replacement_probability=0.48、max_replacement_decimal_odds=2.10、min_candidate_hit_probability_delta_vs_model_top=-0.05、min_candidate_hit_probability_delta_vs_original=-0.08；average_hit_probability_delta_vs_original=-0.036354272663278404，仍属于 research/staging 候选
阶段性结论：expanded 样本不再是“完全无激活”，已经找到 no-harm 正向候选；但样本仍只有 56 eligible final answers / 7 changes，且阈值比 core rule 更宽，下一阶段必须做 rolling-window admission 或 holdout replay，再决定是否进入 staged profile promotion 链
README 更新 activation grid CLI、真实 report key、best candidate 指标与非生产边界；该能力属于“expanded sample short-odds threshold search / core accuracy evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-268 当前落地能力：

```text
按 V3.1-267 结论对 activation grid 正向候选做 rolling admission / holdout 风格分折验证；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只判断 grid 候选是否稳定到足以进入 staged promotion 链
新增 short_odds_adapter_activation_grid_admission 模块与 CLI：uv run nutmeg-recommendation-short-odds-adapter-activation-grid-admission；输入 audit report、staged rule profile 与 activation grid report，选择 accepted grid candidates，临时重建候选 rule_set，并复用现有 HistoricalShortOddsRollingAdmissionOptions / build_historical_short_odds_rolling_admission_report
新增 admission candidate summary：记录 source grid candidate 指标、临时阈值、rolling admission status、active competition/season/rolling fold counts、failed checks、failed fold reason counts 与 failed fold ids；只输出内部证据，不改变用户最终答案或生产 profile
新增 deterministic tests 覆盖：候选跨 folds 通过时 accepted；fold coverage 不足时保持 shadow_only；CLI 可写入 admission report
生成真实 artifact：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_grid_admission_v1.json；report_key=short_odds_adapter_activation_grid_admission:1e776f28f992c238；status=shadow_only_candidates；selected_candidate_count=5；accepted_candidate_count=0；shadow_only_candidate_count=4；rejected_candidate_count=1
best_candidate 仍是 short_odds_adapter_activation_grid_candidate:adf934b22d9e0f78；source_changed_final_answer_count=7；source_final_answer_hit_rate_delta=0.0535714285714286；source_roi_delta=0.041194029850746244；source_profit_loss_delta=11.039999999999996；rolling active folds 为 competition=4、season=3、rolling=6
promotion blocker：best candidate 的 rolling_failed_checks=[failed_fold_count]；rolling_failed_fold_count=3；rolling_failed_fold_reason_counts={average_hit_probability_delta_below_threshold:3}；这说明该候选在聚合指标上正向、no-harm，但局部窗口的 hit-probability loss 不稳定，不能进入 staged production promotion
阶段性结论：activation grid 候选已经从“聚合正向”推进到“可 admission 但仅 shadow-only”。下一阶段应缩小候选阈值或增加分联赛/分季节 gating，优先解决 failed fold 的 average hit probability delta，而不是直接降低 admission 门槛
README 更新 activation grid admission CLI、真实 report key、shadow-only 结论与非生产边界；该能力属于“expanded sample short-odds rolling admission / core accuracy evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-269 当前落地能力：

```text
按 V3.1-268 结论继续解决 failed folds，不降低 admission 门槛，而是搜索更窄的 competition scope；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只判断 grid 候选是否存在局部稳定作用域
新增 short_odds_adapter_activation_scope_search 模块与 CLI：uv run nutmeg-recommendation-short-odds-adapter-activation-scope-search；输入 audit report、staged rule profile 与 activation grid report，从 accepted grid candidates 生成 competition subset scopes，并复用 HistoricalShortOddsRollingAdmissionOptions / build_historical_short_odds_rolling_admission_report
scope candidate summary 记录 source candidate key、scope_competition_ids、临时阈值、overall final-answer metrics、rolling admission key/status、active competition/season/rolling fold counts、failed checks 与 failed fold reason counts；只输出内部证据，不改变用户最终答案或生产 profile
新增 deterministic tests 覆盖：全量候选含低质量联赛时，scope search 能找到稳定联赛 scope；CLI 可写入 scope search report
生成真实 artifact：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_scope_search_v1.json；report_key=short_odds_adapter_activation_scope_search:ee7b5353ee598b57；status=accepted_scope_found；scope_candidate_count=56；accepted_scope_count=1；shadow_only_scope_count=43；rejected_scope_count=12
best_scope_key=short_odds_adapter_activation_scope_candidate:ba87e10d4b03ed1e；source_candidate_key=short_odds_adapter_activation_grid_candidate:adf934b22d9e0f78；scope_competition_ids=[ESP_SEGUNDA_DIVISION,FRA_LIGUE_2]；overall_changed_final_answer_count=2；final_answer_hit_rate_delta=0.01785714285714285；roi_delta=0.013432835820895495；profit_loss_delta=3.5999999999999943；average_hit_probability_delta_vs_original=-0.028398806513397407；failed_fold_count=0；active folds 为 competition=2、season=2、rolling=3
阶段性结论：failed folds 不是阈值完全不可用，而是作用域过宽；缩到西乙+法乙可以守住 no-harm、ROI、hit-rate 与 fold gate。但 changed_final_answer_count=2，样本仍太小，不能进入 staged promotion。下一阶段应把这个 scope 纳入更大/更多窗口的 holdout 或 supplemental suite，确认它不是偶然样本
README 更新 activation scope search CLI、真实 report key、accepted scope 指标与非生产边界；该能力属于“expanded sample short-odds scoped admission / core accuracy evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-270 当前落地能力：

```text
按 V3.1-269 结论把 accepted discovery scope 纳入 supplemental/holdout 风格验证；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只防止小样本 scope 被误判为可推广
新增 short_odds_adapter_activation_scope_supplemental 模块与 CLI：uv run nutmeg-recommendation-short-odds-adapter-activation-scope-supplemental；输入 base scope search report 与一个或多个 supplemental scope search report，按 scope_competition_ids 匹配同一 scope，并执行 supplemental accepted、changed count、hit-rate、ROI、P&L、failed folds 与 harm gate
新增 supplemental report schema：记录 base scope 指标、matched supplemental scope 指标、weighted supplemental hit-rate/ROI delta、supplemental P&L delta、failure reason counts、item checks 与总 changed final-answer count；只输出内部证据，不改变用户最终答案或生产 profile
新增 deterministic tests 覆盖：base+supplemental 均 accepted 时 supplemental_validated；supplemental rejected / 回撤时 supplemental_blocked；CLI 可写入 supplemental validation report
生成 supplemental scope-search artifact：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_scope_search_prematch_surface_v1.json；同一 staged candidate 在 prematch-surface audit 上搜索 6 个双联赛 scope，status=shadow_only_scopes；原 discovery scope [ESP_SEGUNDA_DIVISION,FRA_LIGUE_2] 在该 supplemental report 中 rejected
生成正式 validation artifact：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_short_odds_adapter_activation_scope_supplemental_validation_v1.json；report_key=short_odds_adapter_activation_scope_supplemental:6234bc086c5d5932；status=supplemental_blocked；supplemental_validated=false；matched_supplemental_report_count=1；accepted_supplemental_scope_count=0；blocked_supplemental_scope_count=1；total_changed_final_answer_count=9
supplemental 反证指标：discovery base scope changed=2，hit_rate_delta=+0.01785714285714285，roi_delta=+0.013432835820895495，profit_loss_delta=+3.5999999999999943；prematch-surface supplemental 同 scope changed=7，hit_rate_delta=-0.02020202020202022，roi_delta=-0.01502564102564103，profit_loss_delta=-5.86，harm_count_vs_original=3，failed_fold_count=6
阶段性结论：ESP_SEGUNDA_DIVISION+FRA_LIGUE_2 scope 是 discovery overfit，不能进入 staged promotion、runtime profile 或默认路径；下一阶段应停止推进该 short-odds lower-league scope，回到更稳的核心质量函数/真实赛前特征/更大 holdout 方向
README 更新 scope supplemental validation CLI、真实 report key、blocked 结论与非生产边界；该能力属于“expanded sample short-odds supplemental holdout validation / core accuracy governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-271 当前落地能力：

```text
按 V3.1-270 结论停止推进被 supplemental 反证的 short-odds lower-league scope，转回真实赛前 replacement-reranker / value-guard 核心证据线；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只判断 replacement reranker 是否能在真实赛前面通过窄联赛 scope no-harm admission
新增 replacement_reranker_prematch_scope_search 模块与 CLI：uv run nutmeg-recommendation-replacement-reranker-prematch-scope-search；输入 full pre-match replacement audit 与 tolerance grid，按 competition subset 生成 scopes，并复用 replacement_reranker_shadow_admission 的 prematch source-surface、original baseline no-harm、model-top no-harm 与 fold gate
新增 scope candidate schema：记录 scope_competition_ids、admission report key/status、runtime_profile_candidate_allowed、shadow_allowed、overall hit/ROI/P&L delta vs original/model-top、explicit harm counters、active folds、failed checks、failed fold reason counts 与 failed fold ids；只输出内部证据，不改变用户最终答案或生产 profile
新增 deterministic tests 覆盖：真实赛前 source surface 下能找到 no-harm competition scope；伤害原始最终答案的 scope 必须 rejected；CLI 可写入 scope search report
生成真实 artifact：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_replacement_reranker_scope_search_v1.json；report_key=replacement_reranker_prematch_scope_search:e40f39beac45055f；status=no_admitted_scope；scope_candidate_count=26；accepted_scope_count=0；shadow_only_scope_count=0；rejected_scope_count=26
搜索范围为 ENG_CHAMPIONSHIP、ESP_SEGUNDA_DIVISION、FRA_LIGUE_2、GER_2_BUNDESLIGA、ITA_SERIE_B 的 1-3 联赛组合外加 full scope；门槛保持 original final-answer no-harm、model-top no-harm、min_overall_final_answer_count=8、min_overall_changed_from_model_top_count=2、min_active_season_fold_count=2、rolling_window_slice_count=4、max_failed_fold_count=0
best near-miss 为 ENG_CHAMPIONSHIP：overall_shadow_final_answer_count=12；overall_changed_from_model_top_count=2；overall_hit_delta_vs_original_count=+4；overall_roi_delta_vs_original=+0.6975；overall_profit_loss_delta_vs_original=+16.74；但 overall_harm_count_vs_original=1、overall_profit_loss_harm_count_vs_original=1、failed_fold_count=4，因此仍 rejected
全量 26 个 scope 的主要 blocker 是 original-baseline harm 与 failed folds：profit_loss_harm_count_vs_original_above_threshold=25、harm_count_vs_original_above_threshold=25、final_hit_harm_count_vs_original_above_threshold=24、ROI/P&L/hit 原始回撤相关 blocker=23；这说明 replacement reranker 目前不能靠简单收窄联赛组合晋级
阶段性结论：真实赛前 replacement reranker 当前应继续 blocked，不进入 staged runtime profile；下一阶段应把精力放在最终答案质量函数/候选池生成/基础概率校准，而不是继续在同一个 reranker scope 上反复放宽门槛
README 更新 prematch replacement reranker scope search CLI、真实 report key、no admitted scope 结论与非生产边界；该能力属于“prematch replacement reranker scope governance / core accuracy evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-272 当前落地能力：

```text
按 V3.1-271 结论继续离开 replacement reranker 调参，回到最终答案质量函数的真实损失定位；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只增强 final-answer segment audit 的诊断精度
historical_final_answer_segment_audit 新增 include_interaction_segments 选项与 CLI --include-interaction-segments；默认关闭，保持旧报告兼容；开启后额外输出 competition_pass_type、competition_scenario、competition_odds_band、competition_hit_probability_band、pass_type_odds_band、pass_type_hit_probability_band、odds_probability_band
historical_final_answer_segment_audit CLI 的 --suite-manifest 改为可重复传入，支持 core suite + expanded rolling suite 同口径合并审计；summary_json 输出 suite_manifests，单 manifest 时仍保留 suite_manifest 兼容字段
新增 deterministic test 覆盖：默认 segment audit 仍识别原有 loss driver；开启 interaction 后可生成 competition_pass_type:EPL:1x1、competition_odds_band:EPL:1.00-1.30、pass_type_hit_probability_band:1x1:0.70-0.85，并进入 loss-driver 排序
生成真实 artifact：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_interaction_audit_v1.json；report_key=historical_final_answer_segment_audit:8ca377bfdae112e0；suite_status=improved；final_answer_sample_size=240；overall_hit_rate=0.7125；overall_roi=-0.0542119502479339；segment_count=164
核心 loss-driver 从粗粒度“短赔/某联赛”收敛到更可行动的交互分段：hit_probability_band:0.40-0.55 与 pass_type_hit_probability_band:1x1:0.40-0.55 均为 sample_size=30、hit_rate=0.4、ROI=-0.2816666666666666、profit_loss=-16.9；odds_probability_band:1.60-2.00:0.40-0.55 为 sample_size=27、hit_rate=0.4444444444444444、ROI=-0.20185185185185187
英冠单式是主要局部损失区域：competition:ENG_CHAMPIONSHIP sample_size=30、hit_rate=0.5、ROI=-0.22、profit_loss=-13.2；competition_hit_probability_band:ENG_CHAMPIONSHIP:0.40-0.55 sample_size=8、hit_rate=0.25、ROI=-0.5425000000000001；competition_odds_band:ENG_CHAMPIONSHIP:1.60-2.00 sample_size=12、hit_rate=0.4166666666666667、ROI=-0.2716666666666667
正向 counterexample 同时被记录，用于避免过度惩罚：competition_odds_band:PRT_PRIMEIRA_LIGA:1.00-1.30 sample_size=27、hit_rate=0.9259259259259259、ROI=0.07259259259259257；pass_type_hit_probability_band:1x1:0.70-0.85 sample_size=51、hit_rate=0.9019607843137255、ROI=0.07137254901960781；competition:NED_EREDIVISIE sample_size=30、hit_rate=0.9、ROI=0.03
阶段性结论：下一轮不应继续 broad short-odds penalty，也不应简单压低所有 1x1；更合理的质量函数搜索目标是 1x1 medium-probability / medium-odds loss band，尤其是 ENG_CHAMPIONSHIP 0.40-0.55 probability 与 1.60-2.00 odds 交叉区域，同时保护 1x1 0.70-0.85 与葡超/荷甲正向 counterexamples
README 更新 interaction audit CLI、真实 report key、top loss-driver/counterexample 指标与非生产边界；该能力属于“final-answer loss-driver map / core quality-function targeting”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-273 当前落地能力：

```text
按 V3.1-272 loss-driver map 继续推进最终答案质量函数搜索；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改生产默认，只把 1x1 medium-probability / medium-odds loss band 转成可追踪 segment-penalty grid smoke
historical_final_answer_segment_penalty_grid 的 --suite-manifest 改为可重复传入，支持 core 5-season suite 与 expanded A-league rolling-window suite 合并评估；summary_json 输出 suite_manifests，单 manifest 兼容字段保留
segment penalty grid 新增 --progress-jsonl-path；报告新增 baseline_evaluation_elapsed_seconds、candidate_evaluation_elapsed_seconds、grid_evaluation_elapsed_seconds 与 progress_event_count；JSONL 会记录 grid_started、baseline_started/completed、candidate_started/completed、grid_completed，避免长时间全历史回测被误判为卡死
新增 deterministic tests 覆盖：CLI 可写入 progress JSONL；多 suite manifest 会合并 slice paths 并在 summary 中保留 suite_manifests；既有单 manifest 与 slice-path 入口保持兼容
一次 36-candidate broader interaction target grid 因旧版无进度追踪且运行超过约 14 分钟被主动中止；该次没有写出 artifact，也不作为模型结论，只作为增加 progress/chunking 的工程依据
生成真实 smoke artifact：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_final_answer_segment_penalty_eng_championship_medium_probability_odds_smoke_v1.json；progress trace 为同名 .jsonl；slice_count=240；candidate_count=3；accepted_count=0；rejected_count=3；progress_event_count=10；baseline_elapsed=256.60484s；candidate_elapsed=847.654192s；grid_elapsed=1104.268835s
真实 smoke 目标为 ENG_CHAMPIONSHIP / 1x1 / single / hit_probability 0.40-0.55 / odds_product 1.60-2.00，strength=0.01/0.02/0.04；三个候选都触发 7 个 penalty options，但全部被严格门禁拒绝
strength 0.01 与 0.02：final_hit_count_delta=0、roi_delta=-0.0077523610635415255、profit_loss_delta=-6.0、profit_loss_harm_count_vs_baseline=1，并且 Brier/log-loss/mean calibration error 均退步；strength 0.04：final_hit_count_delta=+1，但 roi_delta=-0.014442118376404744、profit_loss_delta=-12.544600000000003、profit_loss_harm_count_vs_baseline=4，Brier/log-loss/mean calibration error 也退步
阶段性结论：ENG Championship 1x1 medium-probability / medium-odds loss band 是真实损失区域，但“直接惩罚这个最终答案段”不是可采纳修复；下一阶段应优先做候选池/概率校准/联赛 profile 的正向特征搜索，并给重型 grid 增加 chunk/resume/cache，避免靠无限扩大惩罚网格推进
README 更新 multi-suite segment penalty grid、progress trace、真实 smoke artifact 与 rejected 结论；该能力属于“core final-answer quality-function tuning / reproducible heavy-run observability / negative evidence gate”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-274 当前落地能力：

```text
按 V3.1-273 结论优先解决重型历史 grid 的执行效率瓶颈；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改生产默认，只增强 core final-answer tuning 工具的可恢复能力
historical_final_answer_segment_penalty_grid 新增 candidate checkpoint JSONL：CLI 参数 --candidate-checkpoint-jsonl-path 会在每个候选完成后追加完整 candidate payload；同一路径再次运行时会自动读取已完成候选并复用，避免中断后重复计算已经完成的 candidates
新增 --reuse-report 参数，可从一个或多个已完成 grid report 中复用 candidates；复用前会校验 candidate_index、pass_types、modes、competition_ids、season_ids、competition season index、hit-probability/odds/average-leg-odds 边界与 strength，防止不同 grid 形状的旧候选误用
progress JSONL 新增 candidate_reused 事件；report 与 summary_json 新增 cached_candidate_count、reused_candidate_count、evaluated_candidate_count、candidate_checkpoint_jsonl_path，能区分本轮新跑候选和复用候选
新增 deterministic test 覆盖 checkpoint resume：第一次 CLI 运行写入 checkpoint；第二次同配置运行只跑 baseline、复用 candidate，不再调用 candidate backtest；progress 记录 candidate_reused，checkpoint 不重复追加
阶段性结论：segment penalty / quality-function heavy grid 已具备可分批、可中断、可恢复的候选级执行能力；当前仍会重跑 baseline，因为新候选的 no-harm deltas 需要 baseline comparisons，下一步若继续优化执行效率，应增加 baseline suite cache 或把 heavy grid 切成统一 batch runner
README 更新 checkpoint/reuse-report 用法；该能力属于“core tuning execution infrastructure / heavy historical grid recovery”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-275 当前落地能力：

```text
按 V3.1-274 结论继续补齐重型历史 grid 的可恢复执行能力；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改生产默认，只让 baseline suite 与候选 checkpoint 一样可复用
historical_final_answer_segment_penalty_grid 新增 --baseline-cache-dir、--read-baseline-cache/--no-read-baseline-cache、--write-baseline-cache/--no-write-baseline-cache；baseline cache 只缓存未启用 segment penalty 的 baseline suite，不缓存候选策略
baseline cache key 包含 slice_id/as_of_time、baseline backtest options、baseline/candidate optimizer profiles 与 competition profile version；读取失败会记录 warning 并回退重跑，写入失败也只记录 warning，不阻断当前 report
progress baseline_completed 事件新增 cache_key/cache_status/cache_written；report 与 summary_json 新增 baseline_cache_key、baseline_cache_status、baseline_cache_written、baseline_cache_dir、read_baseline_cache、write_baseline_cache
新增 deterministic test 覆盖 baseline cache：第一次 CLI 运行 cache_status=miss 并写入 baseline JSON；第二次同配置运行 cache_status=hit，baseline suite 不再调用，但 candidate 仍按当前运行计算
阶段性结论：segment penalty heavy grid 现在具备 baseline cache + candidate checkpoint/reuse-report 两层恢复能力；这为后续概率校准、候选池质量与 lambda 调整层实验铺好执行基础，避免每个重型历史搜索都从零重跑
README 更新 baseline-cache-dir 用法与 cache key 边界；该能力属于“core tuning execution infrastructure / baseline cache / heavy historical grid recovery”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-276 当前落地能力：

```text
按 V3.1-275 结论从调参执行效率切回核心预测质量；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改生产默认，重点是让“模型概率 vs 校准概率 vs 推荐有效概率”成为候选池的一等概念
RecommendationCandidate 新增 model_probability、calibrated_probability、probability_source；raw_model_probability/effective_probability/effective_model_edge/to_leg_selection 现在能区分 raw model estimate 与 calibrated effective estimate，policy scoring 的 probability component、低概率风险、upset exposure 与 min_probability filter 均消费 effective probability
新增 candidate_probability_calibration 模块：CandidateProbabilityCalibrationProfile/Bucket/Result 与 apply_candidate_probability_calibration_profile；目前只对完整 1X2 三项候选组生效，按 competition/outcome/probability bucket 查找校准值，支持 blend_weight、目标联赛/结果/赔率/概率范围，调整后归一化 home/draw/away 概率和为 1
profile mode 支持 active 与 shadow：active 会把 probability_source 切为 calibrated 并让串关命中概率使用校准概率；shadow 只保存 calibrated_probability 和 metadata，不改变当前推荐路径；这保证校准 profile 可以先进入 shadow/admission，再由质量门禁决定是否启用
推荐候选持久化层新增 probability basis 字段：db/migrations/0045_recommendation_candidate_probability_basis.sql 为 recommendation_candidates 与 recommendation_candidate_pool_items 增加 model_probability、calibrated_probability、probability_source 和 check/index；repository 保存 selected candidates 与 candidate-pool replay items 时会写入这些字段
新增 deterministic tests 覆盖：完整 1X2 group 校准后重排候选并驱动 parlay hit_probability；shadow mode 保留 effective probability；不完整 1X2 group 不调整；repository 持久化 probability basis；migration contract 检查 0045 字段和约束
阶段性结论：校准层现在具备进入候选池/最终答案链路的运行时接口，但默认仍不启用任何校准 profile。下一阶段应把历史 probability calibration transform/profile gate 的 accepted shadow evidence 转换成 CandidateProbabilityCalibrationProfile artifact，再通过 final-answer gate 和 rolling admission 决定是否允许 active
README 更新 probability basis 与 runtime candidate calibration adapter；该能力属于“core probability calibration plumbing / candidate pool quality / final-answer accuracy foundation”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-277 当前落地能力：

```text
按 V3.1-276 结论把历史 shadow 校准证据转换成运行时可复用 profile artifact；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改生产默认，只打通 evidence -> runtime profile 的桥
新增 historical_probability_calibration_profile_artifact 模块与 CLI：uv run nutmeg-recommendation-historical-probability-calibration-profile-artifact；它复用 historical probability calibration profile gate，默认只有 passed_final_answer_gate=true 才输出 CandidateProbabilityCalibrationProfile
artifact report 包含 gate_report、emitted_profile、profile、warning_codes 与 summary_json；--profile-output-path 可单独写出 runtime profile JSON，--profile-mode 支持 shadow/active，默认 shadow；--allow-failed-final-answer-gate 只用于诊断导出，不代表允许生产启用
runtime profile 的 buckets 从历史 training slices 重新构建，而不是只使用 transform report 的 sampled buckets；profile 带有 source_report_key、selected competition scope、target outcomes/probability/odds band、blend_weight、min_bucket_sample_size 与完整 1X2 bucket 列表
新增 deterministic tests 覆盖：final-answer gate 通过时输出 runtime profile 并能被 apply_candidate_probability_calibration_profile 使用；默认阻断 failed final-answer gate；CLI 写入 report/profile JSON；CLI 参数映射 artifact/profile/gate 选项
新增 project script：nutmeg-recommendation-historical-probability-calibration-profile-artifact
阶段性结论：校准 profile 现在可以从历史证据被封装成 runtime artifact，但默认仍是 shadow。下一阶段应补 rolling admission / runtime activation gate：同一 profile 需要在多窗口无 final-answer harm 后，才允许切换 active probability_source
README 更新 artifact CLI、默认 final-answer gate 边界、diagnostic-only allow-failed 开关；该能力属于“probability calibration evidence packaging / runtime profile artifact / core prediction quality foundation”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-278 当前落地能力：

```text
按 V3.1-277 结论补齐 probability calibration runtime profile 的 rolling admission / activation gate；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改生产默认，只判断校准 profile 是否具备从 shadow 进入 staged active 的证据
新增 historical_probability_calibration_profile_rolling_admission 模块与 CLI：uv run nutmeg-recommendation-historical-probability-calibration-profile-rolling-admission；它在整体样本、competition folds、cumulative season-cutoff folds、rolling-season folds 上复用 artifact/final-answer gate
rolling admission report 输出 overall_fold、folds、checks、failed_fold_count、active_*_fold_count、candidate_profile_allowed、shadow_allowed 与 summary_json；默认 max_failed_fold_count=0，只有整体 final-answer gate、profile emission、bucket/adjusted fixture 覆盖与多窗口 active fold 数都过，才写出 active profile
新增 deterministic tests 覆盖：稳定 profile 通过 rolling admission 并输出 active profile；单个 competition fold 失败时降级 shadow_only 且不输出 profile；CLI 写入 report/profile JSON；CLI 参数映射 rolling 与 artifact/gate 选项
新增 project script：nutmeg-recommendation-historical-probability-calibration-profile-rolling-admission
阶段性结论：校准 profile 的 evidence -> runtime artifact -> rolling admission 链路已经闭合，但默认生产 profile 仍未切换；下一阶段应把 admission artifact 接入 benchmark quality gate / cycle runner，确保每次开发都能看到该 staged profile 是否仍然无害
README 更新 rolling admission CLI、active profile 写出条件与非生产边界；该能力属于“probability calibration activation gate / core prediction quality guardrail”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-279 当前落地能力：

```text
按 V3.1-278 结论把 probability calibration rolling admission artifact 接入 persisted benchmark quality gate 与 benchmark cycle；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只让 staged calibration profile 进入统一周期质量视野
RecommendationBenchmarkQualityGateOptions 新增 probability_calibration_profile_rolling_admission_report_path、require_probability_calibration_profile_rolling_admission、candidate/profile 模式要求与 overall/fold 覆盖阈值；默认不要求 artifact 存在，保持既有 gate 兼容
quality gate 新增 rolling admission loader、present/accepted/candidate_allowed/shadow_allowed/active_profile/overall_gate/fold coverage checks 与 summary fields；accepted active profile 才能通过严格 require，shadow_only 或 rejected 报告会在显式 require 时阻断
benchmark_cycle CLI 新增对应 --gate-probability-calibration-profile-* 参数；cycle summary 透传 admission key/status、candidate_allowed、shadow_allowed、profile mode/key、overall gate、adjusted fixture count、bucket count、failed fold count 与 active competition/season-cutoff/rolling fold counts
为避免 package 初始化循环，benchmark quality gate 只在 TYPE_CHECKING 和 path loader 内部加载 rolling admission report 类型，不在 recommendations 包导入阶段拉起 accuracy 包
新增 deterministic tests 覆盖：quality gate 可消费 accepted probability calibration rolling admission；shadow_only/非 active/fold 失败会被拦截；report path loader 可读取 JSON；quality gate CLI 与 benchmark cycle CLI/summary 均透传该证据
阶段性结论：probability calibration profile 现在从 evidence -> runtime artifact -> rolling admission -> periodic quality gate/cycle 完成闭环，但默认推荐路径仍不启用任何 calibration profile。下一阶段应继续在核心预测质量线上推进 walk-forward model/feature improvement，只有当真实历史 gate 持续无害且提升最终答案时再考虑 runtime activation
README 更新 benchmark gate/cycle 消费 probability calibration rolling admission artifact 的命令与非生产边界；该能力属于“periodic quality gate hardening / probability calibration activation governance / core prediction quality guardrail”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-280 当前落地能力：

```text
按 V3.1-279 之后的核心预测质量路线，把 prematch feature quality cycle 接入 persisted benchmark quality gate 与 benchmark cycle；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只让真实赛前特征候选的 final-answer cycle evidence 进入统一周期回归视图
RecommendationBenchmarkQualityGateOptions 新增 prematch_feature_quality_cycle_report_path、require_prematch_feature_quality_cycle、cycle passed / best gate passed 要求、slice/fixture/evaluated/passing candidate 阈值、warning count 阈值，以及 best Brier / Log loss / calibration delta 上限
quality gate 新增 prematch feature quality cycle lazy loader、present/passed/best_gate_passed/sample coverage/candidate count/warning/delta checks 与 summary fields；默认不要求 artifact 存在，但如果显式接入失败 cycle，则会阻断 benchmark gate，避免失败 feature 候选被误当作可推广证据
benchmark_cycle CLI 新增对应 --gate-prematch-feature-quality-cycle-* 参数；cycle summary 透传 prematch feature cycle key/status、final-answer gate key、grid key、slice/fixture/evaluated/passing counts、best grid candidate、best suite status、failed quality checks、warning count 与 best Brier/Log loss/calibration deltas
新增 deterministic tests 覆盖：quality gate 可消费 passing prematch feature quality cycle；failed cycle / best gate failed / no passing candidate / positive Brier/Log loss/calibration delta / warnings 会被拦截；report path loader 可读取 JSON；quality gate CLI 与 benchmark cycle CLI/summary 均透传该证据
阶段性结论：prematch feature 候选现在从 feature ablation -> final-answer gate -> compact quality cycle -> persisted benchmark gate/cycle 完成闭环。当前真实 market-movement 和 context 样本仍不能 promotion；下一阶段应继续扩充真实 frozen lineup/injury/news/odds movement 样本，或把通过 cycle 的候选再进入更严格 rolling/holdout admission
README 更新 benchmark gate/cycle 消费 prematch feature quality cycle artifact 的命令与非生产边界；该能力属于“prematch feature final-answer quality governance / periodic benchmark hardening / core prediction quality guardrail”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-281 当前落地能力：

```text
按 V3.1-280 结论把 prematch feature 候选从 compact quality cycle 进一步推进到 rolling/holdout admission；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只判断通过 gate/cycle 的赛前特征候选是否在整体、联赛、赛季切片与滚动窗口上稳定
新增 historical_prematch_feature_rolling_admission 模块与 CLI：uv run nutmeg-recommendation-historical-prematch-feature-rolling-admission；输入 historical slice/suite manifest 与可选 prematch feature ablation grid report，复用 final-answer gate，对同一组 frozen grid candidates 执行 overall、competition、season_cutoff、rolling_window 折叠验证
rolling admission report 输出 overall_fold、folds、checks、failed_fold_count、active_*_fold_count、source_grid_report_key、overall_gate_report_key、candidate_feature_allowed、shadow_allowed 与 summary_json；默认 max_failed_fold_count=0，只有 overall passing candidate 与所有启用折叠覆盖门禁都通过，才返回 accepted 并允许候选进入后续 staged path
整体 final-answer gate 失败时 status=rejected 且 shadow_allowed=false；整体通过但折叠覆盖不足或 active fold 失败时 status=shadow_only，保留内部证据但不能进入候选答案路径
新增 deterministic tests 覆盖：稳定候选 accepted；fold coverage 不足时降级 shadow_only；overall gate 失败时 rejected；CLI 写入 report JSON；CLI 参数映射 final-answer gate 与 rolling admission 选项
新增 project script：nutmeg-recommendation-historical-prematch-feature-rolling-admission，并同步 package entry_points / SOURCES metadata
阶段性结论：prematch feature 候选现在具备 feature ablation -> final-answer gate -> compact quality cycle -> benchmark cycle -> rolling admission 的完整 shadow governance 链路。当前真实 market-movement/context 证据仍不足以进入默认推荐，下一阶段应把通过 rolling admission 的 report 再接入 benchmark quality gate/cycle，或优先扩充真实 frozen lineup/injury/news/opening-odds 样本
README 更新 prematch feature rolling admission CLI、状态含义与非生产边界；该能力属于“prematch feature rolling holdout admission / core prediction quality governance / no-production-change evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-282 当前落地能力：

```text
按 V3.1-281 结论把 prematch feature rolling admission artifact 接入 persisted benchmark quality gate 与 benchmark cycle；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产 profile，只让 rolling/holdout admission 成为统一周期质量门禁的一部分
RecommendationBenchmarkQualityGateOptions 新增 prematch_feature_rolling_admission_report_path、require_prematch_feature_rolling_admission、candidate_allowed 要求、overall evaluated/passing candidate 阈值、failed fold 上限、active competition/season_cutoff/rolling fold 阈值，以及 overall Brier / Log loss / calibration delta 上限
quality gate 新增 prematch feature rolling admission lazy loader、present/accepted/candidate_allowed/shadow_allowed/overall gate/fold coverage/delta checks 与 summary fields；显式 require 时只有 accepted 且 candidate_feature_allowed=true 的 report 才能通过；即便未显式 require，附加 shadow_only/rejected report 也会作为阻断证据，避免不稳定候选被误当作中性证据
benchmark_cycle CLI 新增对应 --gate-prematch-feature-rolling-admission-* 参数；cycle summary 透传 admission key/status、source grid key、overall gate key、candidate/shadow allowed、overall evaluated/passing counts、best grid candidate、failed fold count、active fold counts、failed checks、warning count 与 overall Brier/Log loss/calibration deltas
新增 deterministic tests 覆盖：quality gate 可消费 accepted prematch feature rolling admission；shadow_only / failed folds / positive Brier/Log loss/calibration delta 会被拦截；report path loader 可读取 JSON；quality gate CLI 与 benchmark cycle CLI/summary 均透传该证据
阶段性结论：prematch feature 候选现在从 feature ablation -> final-answer gate -> compact quality cycle -> rolling admission -> persisted benchmark gate/cycle 完成闭环。当前仍没有启用默认推荐路径；下一阶段应优先扩充真实 frozen lineup/injury/news/opening-odds 样本，或把该 rolling evidence 继续接入更高层 promotion proposal，但不能跳过真实样本质量
README 更新 benchmark gate/cycle 消费 prematch feature rolling admission artifact 的命令与非生产边界；该能力属于“prematch feature rolling admission governance / periodic benchmark hardening / core prediction quality guardrail”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-283 当前落地能力：

```text
按 V3.1-282 之后的样本质量路线，新增真实 frozen prematch feature sample readiness gate；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只判断历史样本是否足以进入赛前特征学习/准入
新增 historical_prematch_feature_sample_readiness 模块与 CLI：uv run nutmeg-recommendation-historical-prematch-feature-sample-readiness；输入 historical sample coverage audit report，或直接输入 suite manifest / slice path 并即时生成 coverage audit
readiness gate 支持 target_profile=final_answer/feature_snapshot/market_movement/context_signal/full_prematch_context，并按 complete 1X2、feature snapshot、odds time-series、lineup、availability、semantic signal、source-ref、data quality、source/report warning 与聚合 fixture/slice/competition/season 覆盖阈值输出 accepted / shadow_only / rejected
新增 deterministic tests 覆盖：market-movement 样本 accepted；market-only 样本在 full-prematch-context 目标下降级 shadow_only；空样本 rejected；report path loader 与 CLI 写出；CLI 参数映射
新增 project script：nutmeg-recommendation-historical-prematch-feature-sample-readiness，并同步 package entry_points / SOURCES metadata
阶段性结论：样本覆盖审计现在多了一层可执行准入语义，后续 prematch feature / lambda adjustment / calibration 不能直接拿“不完整上下文”的历史切片做 promotion 证据。当前 full prematch context 仍需要扩充真实 frozen lineup/injury/news/opening-odds 样本
README 更新 prematch feature sample readiness CLI、状态含义与非生产边界；该能力属于“historical prematch feature sample admission guardrail / core prediction quality foundation”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-284 当前落地能力：

```text
按 V3.1-283 结论把 prematch feature sample readiness 接入 rolling admission、persisted benchmark quality gate 与 benchmark cycle；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只让样本准入成为赛前特征候选晋级链路的一部分
historical_prematch_feature_rolling_admission 新增 sample_readiness_report_path、require_sample_readiness、require_sample_ready_allowed 选项；CLI 新增 --sample-readiness-report-path、--require-sample-readiness 与 --allow-sample-readiness-shadow-only
rolling admission report 新增 sample_readiness_key/status、sample_ready_allowed、sample_readiness_shadow_allowed 与 report path summary；sample readiness rejected 会使 rolling admission rejected，sample readiness shadow_only 会使 rolling admission shadow_only 且 candidate_feature_allowed=false
RecommendationBenchmarkQualityGateOptions 新增 prematch_feature_sample_readiness_report_path、require_prematch_feature_sample_readiness、sample_ready_allowed 要求、ready source/fixture/competition/season/competition-season 阈值与 warning 上限
quality gate 新增 sample readiness lazy loader、present/accepted/sample_ready_allowed/shadow_allowed/coverage checks 与 summary fields；附加 shadow_only/rejected readiness report 会作为阻断证据，避免 prematch feature rolling/quality evidence 绕过样本准入
benchmark_cycle CLI 新增对应 --gate-prematch-feature-sample-readiness-* 参数；cycle summary 透传 readiness key/status、target profile、coverage audit key、ready source/fixture/slice/competition/season count、failed checks 与 warning count
新增 deterministic tests 覆盖：rolling admission 在 sample readiness shadow_only 时降级 shadow_only；quality gate 可消费 accepted sample readiness；shadow_only readiness 会被拦截；report path loader 可读取 JSON；quality gate 与 cycle CLI/summary 均透传该证据
阶段性结论：prematch feature 的样本覆盖审计 -> sample readiness -> rolling admission -> benchmark gate/cycle 已经闭合。下一阶段应继续提升核心预测质量：在 accepted 样本范围内做 lambda adjustment / probability calibration / candidate quality 的小步 no-harm 实验，而不是绕过样本质量门槛
README 更新 rolling admission 与 benchmark gate 消费 sample readiness artifact 的命令与非生产边界；该能力属于“prematch feature sample-readiness admission integration / core prediction quality governance”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-285 当前落地能力：

```text
按 V3.1-284 的核心预测质量路线，新增 walk-forward prematch feature lambda adjustment shadow candidate；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只让赛前特征能进入 lambda_home / lambda_away 层做可审计小步实验
nutmeg.accuracy.historical_poisson_walk_forward 新增 lambda_method=prematch_feature_adjusted；它以 form_rest_adjusted 的增强 home/away lambda 为基础，读取 HistoricalFixture.feature_snapshot.features_json.prematch_context，并用 odds movement、lineup strength、availability risk、draw risk、semantic risk 生成保守 lambda 调整
HistoricalPoissonWalkForwardOptions 新增 min_prematch_feature_data_quality_score、prematch_feature_* 权重、max_prematch_feature_lambda_adjustment、allow_missing_prematch_feature_fallback 与 feature as-of guard；默认缺失/低质量 feature snapshot 会跳过该 fixture，避免用不完整样本伪装成有效提升
sampled prediction 与 GoalLambdaEstimate.metadata_json 新增 lambda_home/away_before_prematch_feature_adjustment、prematch_feature_data_quality_score、prematch_feature_adjustment_factor、prematch_feature_total_goals_adjustment_factor、reason_codes 与 readout_json；summary_json 标记 prematch_feature_lambda_adjustment_shadow_only=true
新增 deterministic tests 覆盖：prematch_feature_adjusted 会在完整 feature snapshot 上调整 lambdas 并保留 shadow readout；缺失 snapshot 时默认跳过；CLI 参数映射正确
阶段性结论：lambda adjustment 层已具备最小可回测接口，但默认推荐链路没有变化。后续必须在 accepted sample readiness 范围内跑真实 frozen 样本，并通过 final-answer no-harm、rolling admission 与 benchmark gate，才允许讨论 profile/staged activation
README 更新 prematch_feature_adjusted walk-forward CLI、shadow-only 边界与非生产约束；该能力属于“prematch feature lambda adjustment shadow experiment / core prediction quality foundation”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-286 当前落地能力：

```text
按 V3.1-285 的 shadow candidate 继续推进真实样本 no-harm 验证；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只把 prematch lambda 权重纳入现有 holdout parameter-learning harness，并产出可复现负证据
historical_poisson_parameter_learning 新增 prematch_feature_adjusted 候选支持：candidate_prematch_feature_odds_movement_weights、candidate_prematch_feature_draw_risk_weights、candidate_max_prematch_feature_lambda_adjustments、min_prematch_feature_data_quality_score，以及 lineup/availability/semantic 固定权重透传到 walk-forward options
HistoricalPoissonParameterCandidate 新增 prematch_feature_odds_movement_weight、prematch_feature_draw_risk_weight、max_prematch_feature_lambda_adjustment；candidate_key 会记录 prematch_odds / prematch_draw / prematch_max，保证训练选择与 holdout 验证完全可复现
新增 deterministic tests 覆盖：prematch feature lambda 参数网格生成、walk-forward option 透传、CLI 参数映射；既有 form/rest、recency/home-away、Dixon-Coles rho 测试保持通过
生成 readiness artifact：configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_sample_readiness_market_movement_v1.json；status=accepted，sample_ready_allowed=true，ready_fixture_count=600，ready_competition_season_count=25；warning 仅说明 context_signal_not_ready，因此该样本只适合 market-movement，不代表完整赛前情报
生成 direct walk-forward artifact：configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_prematch_lambda_walk_forward_v1.json；report_key=historical_poisson_walk_forward:f515fa36b49b483f；validation_count=211；candidate_hit_rate=0.4597156398104265 vs market baseline 0.5308056872037915；candidate_brier=0.6720811819287511 vs baseline 0.5813448089259571；candidate_log_loss=1.1198851806752905 vs baseline 0.9726931078497135；ECE 从 0.057758611638982604 改善到 0.051085412020482314，但不足以抵消 Brier/Log loss 退步
生成 holdout parameter-learning artifact：configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_prematch_lambda_parameter_learning_v1.json；report_key=historical_poisson_parameter_learning:c21d0631112f4895；candidate_count=24；learned_competition_count=5；validation_count=97；整体 holdout hit_rate_delta=-0.07216494845360821、brier_score_delta=0.08808789778821091、log_loss_delta=0.1330986332277656
阶段性结论：当前仅基于 football-data.co.uk opening-to-closing odds movement 的 prematch lambda adjustment 不通过 no-harm，不应进入 final-answer gate、rolling admission、runtime profile 或默认推荐链路。保留接口和报告作为负证据；下一阶段应优先补真实 lineup/availability/news context 或改进独立 team-strength model，而不是继续在 market-only lambda 权重上扩大网格
README 更新 prematch_feature_adjusted parameter-learning CLI、真实 artifact、关键指标与 non-promotion 结论；该能力属于“prematch lambda holdout evidence / core prediction quality negative evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-287 当前落地能力：

```text
按 V3.1-286 的结论回到独立 team-strength / lambda 基础模型，不继续扩大 market-only prematch lambda 网格；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只新增样本收缩版 home/away team-strength lambda shadow candidate
historical_poisson_walk_forward 新增 lambda_method=shrunken_weighted_home_away；它从 enhanced_weighted_home_away 的 attack-defense lambda 出发，按 home/away team sample_matches 与 strength_shrinkage_matches 计算 reliability，并把 lambda_home/lambda_away 向联赛 home/away 平均进球基线回归，降低小样本极端进球率对比分网格的影响
HistoricalPoissonWalkForwardOptions / sampled prediction / GoalLambdaEstimate.metadata_json 新增 strength_shrinkage_matches、home_strength_reliability、away_strength_reliability；summary_json 标记 sample_shrinkage_shadow_only=true，保证该模型只作为可审计 shadow evidence
historical_poisson_parameter_learning 新增 candidate_strength_shrinkage_matches 网格；HistoricalPoissonParameterCandidate 新增 strength_shrinkage_matches；candidate_key 新增 shrink_* suffix；CLI 新增 --strength-shrinkage-matches 与 --candidate-strength-shrinkage-matches
新增 deterministic tests 覆盖：shrunken_weighted_home_away 会记录 sample reliability 并把极端 lambda 拉回联赛基线；parameter-learning 会生成 shrinkage 网格并正确透传到 walk-forward options；CLI 参数映射正确
生成 direct walk-forward artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_shrunken_homeaway_walk_forward_v1.json；report_key=historical_poisson_walk_forward:56dfb35da3e2f13d；validation_count=10092；candidate_hit_rate=0.503170828378914 vs market baseline 0.5273483947681332；candidate_brier=0.6071231825444314 vs baseline 0.5844665736444945；candidate_log_loss=1.014332843568345 vs baseline 0.9815234496797939；candidate_ECE=0.019920656218396827 vs baseline 0.01103425592844241
生成 holdout parameter-learning artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_shrunken_homeaway_parameter_learning_v1.json；report_key=historical_poisson_parameter_learning:cc5d87111e84d2bd；candidate_count=45；learned_competition_count=6；validation_count=2062；整体 holdout hit_rate_delta=-0.016973811833171593、brier_score_delta=0.017853313509368585、log_loss_delta=0.025729941585761362、expected_calibration_error_delta=-0.0029621018738979904
阶段性结论：样本收缩能在 holdout 上稍微改善 ECE，但 hit rate / Brier / log loss 仍不通过 no-harm，不应进入 final-answer gate、rolling admission、runtime profile 或默认推荐链路。保留接口和报告作为负证据；下一阶段应改进 team-strength 的信息来源和建模形态，例如分联赛进攻/防守层级、赛季先验、promotion/relegation 新队处理或分段校准，而不是把当前收缩权重继续做大网格搜索
README 更新 shrunken_weighted_home_away walk-forward / parameter-learning CLI、真实 artifact、关键指标与 non-promotion 结论；该能力属于“sample-shrunk team-strength lambda shadow evidence / core prediction quality negative evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-288 当前落地能力：

```text
按 V3.1-287 结论继续提升核心预测本体，不继续扩大 shrinkage 网格；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只把近期状态从 flat form window 扩展为可回测的 EMA form signal shadow candidate
historical_poisson_walk_forward 新增 lambda_method=ema_form_adjusted；它从 enhanced_weighted_home_away 的 lambda 出发，读取最近 form_window_matches 场，按 ema_form_half_life_matches 对最近赛果、积分和净胜球做指数加权，并用 form_adjustment_weight 生成保守 lambda advantage adjustment
HistoricalPoissonWalkForwardOptions / sampled prediction / GoalLambdaEstimate.metadata_json 新增 ema_form_half_life_matches；summary_json 标记 ema_form_adjustment_shadow_only=true；EMA form 输出继续保持 Dixon-Coles v1.5 score-grid compatibility
historical_poisson_parameter_learning 新增 candidate_ema_form_half_life_matches 网格；HistoricalPoissonParameterCandidate 新增 ema_form_half_life_matches；candidate_key 新增 ema_*_form_* suffix；CLI 新增 --ema-form-half-life-matches 与 --candidate-ema-form-half-life-matches
新增 deterministic tests 覆盖：ema_form_adjusted 会记录加权 form readout、half-life 和 form adjustment；parameter-learning 会生成 EMA form 网格并正确透传到 walk-forward options；CLI 参数映射正确
生成 direct walk-forward artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_ema_form_walk_forward_v1.json；report_key=historical_poisson_walk_forward:5dc85381f61194ef；validation_count=10092；candidate_hit_rate=0.5077288941736029 vs market baseline 0.5273483947681332；candidate_brier=0.6046293875247349 vs baseline 0.5844665736444945；candidate_log_loss=1.0118809846457184 vs baseline 0.9815234496797939；candidate_ECE=0.023136779439429198 vs baseline 0.01103425592844241
生成 holdout parameter-learning artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_ema_form_parameter_learning_v1.json；report_key=historical_poisson_parameter_learning:b40f93be6236cfa1；candidate_count=18；learned_competition_count=6；validation_count=2062；整体 holdout hit_rate_delta=-0.020368574199805978、brier_score_delta=0.017477499811174413、log_loss_delta=0.02505075403543877、expected_calibration_error_delta=0.004577506240668147
阶段性结论：EMA recent-results form 不通过 no-harm，且 holdout ECE 也变差；它证明“只靠近期赛果状态”不足以提升独立比分模型。保留接口和报告作为负证据；下一阶段应转向更有解释力的数据结构，例如赛季/升降级先验、分联赛层级 attack-defense、赛程强度或真实阵容可用性，而不是继续调 form 权重
README 更新 ema_form_adjusted walk-forward / parameter-learning CLI、真实 artifact、关键指标与 non-promotion 结论；该能力属于“EMA form lambda shadow evidence / core prediction quality negative evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-289 当前落地能力：

```text
按 V3.1-288 结论继续收敛核心预测本体，不继续调近期 form 权重；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只新增 season-aware team-strength lambda shadow candidate，用于验证跨赛季样本是否应该降权
HistoricalFixtureResult 新增 season 字段；historical_poisson_walk_forward 会把 HistoricalRecommendationSlice.metadata.season 沿 fixture context -> prior_results -> lambda estimate 传递，sampled prediction 和 GoalLambdaEstimate.metadata_json 输出 current_season_match_count、prior_season_match_count、prior_season_weight
historical_poisson_walk_forward 新增 lambda_method=season_weighted_home_away；它复用 enhanced_weighted_home_away 的主客 attack-defense estimator，但按 prior_season_weight 降低非当前赛季历史结果权重，并让 draw-rate reference 使用同一组 season-weighted results
HistoricalPoissonWalkForwardOptions 新增 prior_season_weight；summary_json 标记 season_weighted_shadow_only=true；CLI 新增 --prior-season-weight，继续保持 Poisson / Dixon-Coles v1.5 score-grid compatibility
historical_poisson_parameter_learning 新增 candidate_prior_season_weights 网格；HistoricalPoissonParameterCandidate 新增 prior_season_weight；candidate_key 新增 priorseason_* suffix；CLI 新增 --candidate-prior-season-weights 和 --prior-season-weight
新增 deterministic tests 覆盖：season_weighted_home_away 会记录当前赛季/过往赛季样本数和 prior weight；parameter-learning 会生成 prior-season weight 网格并正确透传到 walk-forward options；CLI 参数映射正确
生成 direct walk-forward artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_season_weighted_homeaway_walk_forward_v1.json；report_key=historical_poisson_walk_forward:328cf41d5a2ca041；validation_count=10092；candidate_hit_rate=0.5068370986920333 vs market baseline 0.5273483947681332；candidate_brier=0.6045842748037896 vs baseline 0.5844665736444945；candidate_log_loss=1.0115588497403782 vs baseline 0.9815234496797939；candidate_ECE=0.02240207049918595 vs baseline 0.01103425592844241
生成 holdout parameter-learning artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_season_weighted_homeaway_parameter_learning_v1.json；report_key=historical_poisson_parameter_learning:bb5e1ac81f09ca06；candidate_count=10；learned_competition_count=6；validation_count=2062；整体 holdout hit_rate_delta=-0.021823472356934936、brier_score_delta=0.01748070353879594、log_loss_delta=0.025242404643045946、expected_calibration_error_delta=0.0004404169183554879
阶段性结论：简单的跨赛季降权仍不通过 no-harm，且 holdout 四项核心指标全部不优于市场基线；它证明“只按赛季边界重加权历史赛果”不足以提升独立比分模型。保留接口和报告作为负证据；下一阶段应优先做分联赛/分赛季层级 attack-defense、升降级新队先验、真实赛前特征样本或 calibration 层改造，而不是继续扩大 prior-season weight 网格
README 更新 season_weighted_home_away walk-forward / parameter-learning CLI、真实 artifact、关键指标与 non-promotion 结论；该能力属于“season-aware team-strength lambda shadow evidence / core prediction quality negative evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-290 当前落地能力：

```text
按 V3.1-289 结论继续收敛核心预测本体，不继续扩大 prior-season weight 网格；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只新增 hierarchical attack-defense shrinkage shadow candidate，用于验证“先收缩球队进攻/防守强度，再生成 lambda”是否优于直接收缩最终 lambda
historical_poisson_walk_forward 新增 lambda_method=hierarchical_weighted_home_away；它复用 weighted home/away estimator，但在 home_attack、home_defense、away_attack、away_defense 层按 team sample reliability 向 1.0 联赛均值回归，再组合 lambda_home / lambda_away
HistoricalPoissonWalkForwardOptions 复用 strength_shrinkage_matches；sampled prediction 和 GoalLambdaEstimate.metadata_json 继续输出 home_strength_reliability、away_strength_reliability、strength_shrinkage_matches；summary_json 标记 hierarchical_strength_shadow_only=true；输出保持 Poisson / Dixon-Coles v1.5 score-grid compatibility
historical_poisson_parameter_learning 的 candidate_strength_shrinkage_matches 网格扩展支持 hierarchical_weighted_home_away；candidate_key 复用 shrink_* suffix；CLI 的 --lambda-method 新增 hierarchical_weighted_home_away
新增 deterministic tests 覆盖：hierarchical_weighted_home_away 会记录 sample reliability 并改变 enhanced lambda；parameter-learning 会生成 hierarchical shrinkage 网格并正确透传到 walk-forward options；既有 shrunken / season-weighted / EMA / prematch tests 保持通过
生成 direct walk-forward artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_hierarchical_homeaway_walk_forward_v1.json；report_key=historical_poisson_walk_forward:a2f9e2cebff070dc；validation_count=10092；candidate_hit_rate=0.5052516845025763 vs market baseline 0.5273483947681332；candidate_brier=0.6060744634399309 vs baseline 0.5844665736444945；candidate_log_loss=1.0128672704954003 vs baseline 0.9815234496797939；candidate_ECE=0.018210936593020085 vs baseline 0.01103425592844241
生成 holdout parameter-learning artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_hierarchical_homeaway_parameter_learning_v1.json；report_key=historical_poisson_parameter_learning:22dc985a449d0051；candidate_count=10；learned_competition_count=6；validation_count=2062；整体 holdout hit_rate_delta=-0.01891367604267702、brier_score_delta=0.017693039458025805、log_loss_delta=0.025243681207295254、expected_calibration_error_delta=0.0011185969355606215
阶段性结论：层级 attack-defense shrinkage 能局部降低过度自信，但 hit rate / Brier / log loss 仍不通过 no-harm，holdout ECE 也未整体优于市场基线；它证明“只在历史赛果强度层做先验收缩”不足以让独立比分模型追上市场。保留接口和报告作为负证据；下一阶段应优先转向真实赛前特征样本、赔率特征校准层、升降级新队先验或分赔率段 final-answer quality function，而不是继续扩大 shrinkage 网格
README 更新 hierarchical_weighted_home_away walk-forward / parameter-learning CLI、真实 artifact、关键指标与 non-promotion 结论；该能力属于“hierarchical attack-defense shrinkage shadow evidence / core prediction quality negative evidence”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-291 当前落地能力：

```text
按 V3.1-290 结论停止继续扩大历史赛果 lambda 小网格，转向赔率段概率校准层；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只新增 market-odds-band probability calibration shadow mode
historical_probability_calibration_transform 新增 segment_mode：probability_bucket 为默认旧行为，market_odds_band 会优先读取 prediction.market_probability、再回退 1 / decimal_odds，并对 1X2 三项 market-implied probability 归一化后用于 calibration bucket lookup
HistoricalProbabilityCalibrationTransformOptions / Bucket / FixtureSample / summary_json 新增 segment_mode 与 applied_segment_probabilities；CLI 新增 --segment-mode probability_bucket|market_odds_band；report_key 会随 options 改变，避免不同分段模式混淆
profile gate 继续复用 _calibrated_probabilities，但已兼容新的四元返回值；candidate probability calibration runtime profile 与 artifact bucket 新增 segment_mode，使 shadow evidence -> runtime artifact 后续不会断链
新增 deterministic tests 覆盖：transform 可按 market odds band 而非 model probability bucket 选桶；CLI 参数映射 segment_mode；runtime candidate calibration profile 可用 market_odds_band 匹配 bucket
生成 core-suite market-odds-band transform artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_market_odds_band_calibration_transform_v1.json；report_key=historical_probability_calibration_transform:21b793fffa477488；validation_count=2132；usable_calibration_bucket_count=104；accepted_competition_count=2；rejected_competition_count=4
core-suite 整体 holdout candidate 指标：hit_rate=0.5337711069418386、Brier=0.5795079692472372、Log loss=0.9739091280225523、ECE=0.03817676000003683
core-suite 整体 holdout baseline 指标：hit_rate=0.5361163227016885、Brier=0.5791437500706367、Log loss=0.9730922524293841、ECE=0.03737794058402302
core-suite 结论：结果与旧 probability-bucket transform 完全一致，原因是 core frozen suite 本质上以 no-vig market probability 作为 prediction baseline；这是链路验证，不是模型增益证据
生成 market-feature multi-season transform artifact：configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_calibration_transform_v1.json；report_key=historical_probability_calibration_transform:5212d49d3b0319f8；fixture_count=600；validation_count=120；usable_calibration_bucket_count=6；accepted_competition_count=0；rejected_competition_count=5
market-feature 整体 holdout：hit_rate 0.5583333333333333 持平；Brier 从 0.5524644257949949 改善到 0.5518169200189179；Log loss 从 0.9307340402994833 改善到 0.9286776662145748；ECE 因 validation observation buckets 样本不足为 null；每个联赛 holdout 仅 24 场，不满足 min_validation_sample_size=100
阶段性结论：赔率段校准链路已经补齐，并在 market-feature 样本上出现小幅概率质量改善，但样本太薄且未进入 final-answer gate；不能 promotion，不能改变默认推荐路径。下一阶段应优先扩充真实赛前 feature 样本或给 market-odds-band profile 做 final-answer gate / rolling admission，而不是继续小样本 bucket search
README 更新 market-odds-band calibration CLI、真实 artifact、关键指标与 non-promotion 结论；该能力属于“odds-segment probability calibration shadow evidence / core prediction quality calibration foundation”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-292 当前落地能力：

```text
按 V3.1-291 结论把 market_odds_band probability calibration profile 接入 final-answer gate；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只让赔率段校准候选通过最终答案门禁验证
historical_probability_calibration_profile_gate CLI 新增 --segment-mode probability_bucket|market_odds_band，并在 summary_json 与 adjusted prediction metadata_json 写入 segment_mode；profile grid、profile artifact、profile rolling admission CLI 同步新增 --segment-mode，保证 evidence -> gate -> artifact -> rolling admission 链路不丢失赔率段模式
historical_probability_calibration_profile_gate CLI 新增 --min-final-answer-changed-count，与 grid/artifact 的更严格门禁保持一致；这修复了一个关键缺口：概率指标改善但最终答案未变化时，不能被误判为对用户有用的提升
新增/更新 deterministic tests 覆盖：profile gate 可用 market_odds_band 跑 accepted competition holdout；profile gate / grid / artifact / rolling admission CLI 均正确映射 segment_mode；profile gate CLI 正确映射 min_final_answer_changed_count；adjusted prediction metadata 记录 segment_mode
生成 core-suite market_odds_band final-answer gate artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_market_odds_band_probability_calibration_profile_gate_v1.json；report_key=historical_probability_calibration_profile_gate:2201a0e6496c32fc；transform_report_key=historical_probability_calibration_transform:2fb809d541c24805
core-suite selected_competition_ids=[ESP_LA_LIGA, ITA_SERIE_A]；rejected_competition_ids=[EPL, FRA_LIGUE_1, GER_BUNDESLIGA, JPN_J1]；adjusted_fixture_count=760；final_answer_changed_count=2；suite_status=regressed；passed_final_answer_gate=false
core-suite final-answer delta：final_hit_rate_delta=-0.5、final_hit_count_delta=-1、roi_delta=-0.51、profit_loss_delta=-2.04、brier_score_delta=0.35321256192032685、log_loss_delta=0.8726533265588201、mean_calibration_error_delta=0.38340428675644883；失败检查包括 suite_status、final_hit_rate_delta、brier/log-loss/calibration 回退
生成 market-feature exploratory final-answer gate artifact：configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_gate_exploratory_v1.json；report_key=historical_probability_calibration_profile_gate:f3fc3ecdb5cb5bab；selected_competition_ids=[BUNDESLIGA, EPL, LA_LIGA, SERIE_A]；adjusted_fixture_count=96；在 min_validation_sample_size=20 的探索配置下 probability metrics 改善但 final_answer_changed_count=0
生成 market-feature strict final-answer gate artifact：configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_gate_strict_v1.json；report_key=historical_probability_calibration_profile_gate:befcf70fc624d96f；同样 selected_competition_ids=[BUNDESLIGA, EPL, LA_LIGA, SERIE_A]；aggregate deltas：final_hit_rate_delta=0、roi_delta=0、profit_loss_delta=0、brier_score_delta=-0.013140475792027984、log_loss_delta=-0.027925615774599954、mean_calibration_error_delta=-0.00851611160713972、final_answer_changed_count=0；由于 --min-final-answer-changed-count=1，quality gate 正确失败在 final_answer_changed_count
阶段性结论：market_odds_band 校准已经能进入最终答案门禁，但还没有证明会改善用户最终拿到的答案。core-suite 明确回撤；market-feature 样本只改善概率诊断而不改变最终答案，且样本很薄。不能 promotion，不能进入 default/staged runtime profile
下一阶段路线：停止把 small-bucket calibration 当作主增益来源；优先改 final-answer candidate generation / arbitration，让概率改善能真正改变候选选择，或扩充真实赛前 feature 样本。任何候选继续必须同时满足 final-answer changed-count、hit-rate no-harm、rolling admission 与 benchmark gate
README 更新 market-odds-band profile gate CLI、真实 artifact、严格 changed-answer 门禁与 non-promotion 结论；该能力属于“odds-segment calibration final-answer gate / user-answer-first guardrail”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-293 当前落地能力：

```text
按 V3.1-292 结论转向 final-answer candidate generation / arbitration 诊断；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只新增最终答案敏感度审计，判断“概率改善但最终答案不变”到底是仲裁权重问题还是候选/场景覆盖问题
新增 historical_final_answer_sensitivity_audit 模块与 CLI：uv run nutmeg-recommendation-final-answer-sensitivity-audit；输入 profile gate report 或 suite report，按 baseline/candidate side 审计每个 slice 的最终答案 winner 与最近 distinct runner-up
审计输出 winner/runner-up option key、pass_type、mode、final_answer_score、score_gap、hit_probability delta、ROI/profit delta、actual_hit 对比、是否 signature changed、reason_codes、top_near_misses 与 diagnostic_codes
diagnostic_codes 覆盖 candidate_generation_sparse、no_distinct_runner_up_options、no_near_miss_margin、no_higher_hit_probability_runner_up、no_actionable_near_miss；这能把下一步研发从“盲调仲裁权重”转向更明确的候选生成/场景覆盖问题
新增 deterministic test 覆盖：当 runner-up 分数接近、命中概率更高且 winner 未中 runner-up 命中时，报告能识别 actionable near-miss、runner_up_higher_hit_probability 与 winner_lost_runner_up_hit
新增 project script：nutmeg-recommendation-final-answer-sensitivity-audit，并同步 package entry_points / SOURCES metadata
生成 market-feature market_odds_band sensitivity artifact：configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_final_answer_sensitivity_audit_v1.json；report_key=historical_final_answer_sensitivity_audit:287b78d2f5b38aa1；source_report_key=historical_probability_calibration_profile_gate:befcf70fc624d96f
market-feature sensitivity 结果：comparison_count=4、final_answer_count=4、runner_up_count=1、runner_up_coverage_rate=0.25、near_miss_count=0、actionable_near_miss_count=0、runner_up_higher_hit_probability_count=0、winner_loss_runner_up_hit_count=0、average_score_gap=0.08656403317375794；diagnostic_codes=[candidate_generation_sparse, no_near_miss_margin, no_higher_hit_probability_runner_up, no_actionable_near_miss]
生成 core-suite market_odds_band sensitivity artifact：configs/recommendations/historical_reports/football_data_co_uk_core_5_seasons_market_odds_band_final_answer_sensitivity_audit_v1.json；report_key=historical_final_answer_sensitivity_audit:5e22a55a40e82ae1；source_report_key=historical_probability_calibration_profile_gate:2201a0e6496c32fc
core-suite sensitivity 结果：comparison_count=2、final_answer_count=2、runner_up_count=2、runner_up_coverage_rate=1.0、near_miss_count=0、actionable_near_miss_count=0、runner_up_higher_hit_probability_count=0、winner_loss_runner_up_hit_count=0、average_score_gap=0.04517080269425944、min_score_gap=0.043572797488387605；diagnostic_codes=[no_near_miss_margin, no_higher_hit_probability_runner_up, no_actionable_near_miss]
阶段性结论：当前 market_odds_band 校准不能改善最终答案，不是单纯“仲裁权重差一点”；market-feature 样本的主要瓶颈是候选/场景生成稀疏，core-suite 则没有更高命中概率的 runner-up。下一阶段应先扩展 final-answer option generation / scenario coverage，让系统产生更多可替换的高命中备选，再考虑仲裁权重或 calibration profile promotion
README 更新 final-answer sensitivity audit CLI、真实 artifact、诊断指标与下一阶段判断；该能力属于“final-answer candidate generation diagnostic / user-answer-first development guardrail”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-294 当前落地能力：

```text
按 V3.1-293 结论继续扩展 final-answer option generation / scenario coverage；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产路径，只新增历史回测影子场景变体，用于验证“候选覆盖不足”而不是盲目调仲裁权重
HistoricalRecommendationBacktestOptions 新增 final_answer_scenario_variant_count，默认 1；默认不改变任何既有回测、门禁、报告或生产推荐行为
historical_backtest 场景运行器在开启 variant_count>1 时，会先运行基础 scenario，再将上一轮已选 fixture 从候选池排除，生成同 pass_type/mode 的 #variantN 影子场景；只有成功变体进入 final-answer 仲裁候选，失败变体静默停止，避免把“无足够替代 fixture”污染为主流程错误
variant option_key 追加 :variant:N，reason_codes 增加 historical_backtest_shadow_variant，selection_diagnostics_json 记录 scenario_variant、base_scenario_key、variant_index、excluded_fixture_ids；summary_json 新增 final_answer_scenario_variant_count 与 completed_scenario_variant_count；suite / quality gate summary 聚合 baseline/candidate completed_scenario_variant_count
historical backtest CLI、historical suite quality gate CLI、probability calibration profile gate/grid/artifact/rolling admission CLI 均新增 --final-answer-scenario-variant-count，保证 evidence -> gate -> artifact -> rolling admission 链路不丢失该影子候选覆盖参数
新增 deterministic test：1x1 single 在 final_answer_scenario_variant_count=3 时会生成 base + variant1 + variant2 三个不同 fixture 的可仲裁 option，且 option_key 与 reason_codes 可区分
生成 market-feature scenario-variant gate artifact：configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_probability_calibration_profile_gate_variants_v1.json；report_key=historical_probability_calibration_profile_gate:ccf62801d3d7577d；transform_report_key=historical_probability_calibration_transform:24681bbe3ac6a093
market-feature variants gate 结果：selected_competition_ids=[BUNDESLIGA, EPL, LA_LIGA, SERIE_A]；rejected_competition_ids=[LIGUE_1]；adjusted_fixture_count=96；final_answer_scenario_variant_count=3；baseline_completed_scenario_variant_count=1；candidate_completed_scenario_variant_count=1；suite_status=improved 但 passed_final_answer_gate=false，因为 final_answer_changed_count=0
market-feature variants aggregate deltas：final_hit_rate_delta=0.0、final_hit_count_delta=0、roi_delta=0.0、profit_loss_delta=0.0、brier_score_delta=-0.013140475792027984、log_loss_delta=-0.027925615774599954、mean_calibration_error_delta=-0.00851611160713972；严格门禁失败检查为 final_answer_changed_count
生成 scenario-variant sensitivity artifact：configs/recommendations/historical_reports/football_data_co_uk_market_feature_multi_season_market_odds_band_scenario_variants_sensitivity_audit_v1.json；report_key=historical_final_answer_sensitivity_audit:794858857afb2539；source_report_key=historical_probability_calibration_profile_gate:ccf62801d3d7577d
sensitivity 结果：comparison_count=4；final_answer_count=4；runner_up_count=1；runner_up_coverage_rate=0.25；near_miss_count=0；actionable_near_miss_count=0；runner_up_higher_hit_probability_count=0；winner_loss_runner_up_hit_count=0；average_score_gap=0.04382009177492119；diagnostic_codes=[candidate_generation_sparse, no_near_miss_margin, no_higher_hit_probability_runner_up, no_actionable_near_miss]
阶段性结论：影子变体机制本身已补齐，但当前 market-feature holdout 仍然只有 SERIE_A 产生 1 个成功替代场景，其他联赛验证切片在 as-of 时间点只有 1 个可用 fixture；因此当前瓶颈仍是历史切片粒度/真实赛前候选池，不是 final-answer 仲裁权重。下一阶段应优先把 final-answer gate 切到 rolling-window / multi-fixture as-of 样本，或重建 market-feature validation slices，使每个回测时点有足够赛前候选，之后再评估仲裁权重与 profile promotion
README 更新 scenario-variant CLI、真实 artifact、诊断指标与 non-promotion 结论；该能力属于“final-answer candidate coverage shadow evidence / user-answer-first development guardrail”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-295 当前落地能力：

```text
按 V3.1-294 结论把 final-answer gate 从单场/稀疏 holdout 切到 rolling-window / multi-fixture as-of 样本；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产路径，核心目标是让最终答案在真实候选池里验证
修正 historical_probability_calibration_transform 的 holdout split：现在 holdout_season_count 按 season 分组，而不是按 slice 数；当一个 season 被拆成多个 rolling-window slice 时，最后 N 个 season 的全部 window 都进入 validation，训练季数按去重 season 计算；无 season 的旧样本仍回退为旧的 slice-count 语义
同步修正 historical_probability_calibration_profile_gate 的 _profile_gate_slices split；profile gate 现在可正确使用 rolling-window suite：训练使用前 4 个 season 的全部窗口，验证使用最后 1 个 season 的全部窗口，避免只验证最后一个 window 的假稀疏口径
新增 deterministic tests 覆盖 transform 与 profile gate：同一 season 多个 window 时，training_seasons/validation_seasons 去重，validation fixture count 包含最后 holdout season 的所有窗口，profile adjusted_slices 保留最后 season 的全部窗口
生成五大联赛 market-feature rolling-window suite：configs/recommendations/historical_suites/football_data_co_uk_market_feature_rolling_window_suite_v1.json；输出目录 configs/recommendations/historical_slices/enriched_features/football_data_co_uk_market_feature_rolling_windows；generation report configs/recommendations/historical_reports/football_data_co_uk_market_feature_rolling_window_generation_v1.json；report_key=historical_slice_windowing:c1777276c60ac8f2
rolling-window generation 结果：source_slice_count=25；generated_slice_count=50；generated_fixture_count=600；skipped_window_count=0；每个 BUNDESLIGA/EPL/LA_LIGA/LIGUE_1/SERIE_A 生成 10 个窗口，每个窗口 12 fixtures
生成 rolling-window market_odds_band probability calibration profile gate：configs/recommendations/historical_reports/football_data_co_uk_market_feature_rolling_window_market_odds_band_probability_calibration_profile_gate_v1.json；report_key=historical_probability_calibration_profile_gate:7675d712a9fa0ed8；transform_report_key=historical_probability_calibration_transform:0265fedc388c5b1e
rolling-window gate 结果：selected_competition_ids=[BUNDESLIGA, EPL, LA_LIGA, SERIE_A]；rejected_competition_ids=[LIGUE_1]；baseline_slice_count=8；adjusted_slice_count=8；adjusted_fixture_count=96；final_answer_scenario_variant_count=3；baseline_completed_scenario_variant_count=112；candidate_completed_scenario_variant_count=112；suite_status=improved；passed_final_answer_gate=true
rolling-window aggregate deltas：final_hit_rate_delta=0.125；final_hit_count_delta=1；roi_delta=1.3062363636363636；profit_loss_delta=29.0672；brier_score_delta=-0.04661320380327549；log_loss_delta=-0.0997748715249252；mean_calibration_error_delta=-0.05349339821915783；upset_capture_rate_delta=0.3333333333333333；candidate_solver_selected_scenario_count=45；final_answer_changed_count=1
rolling-window candidate final-answer metrics：candidate_final_hit_sample_size=8；candidate_final_hit_rate=1.0；candidate_roi=1.3612363636363636；candidate_profit_loss=29.9472；quality_gate_status=passed；warnings=[]
生成 rolling-window final-answer sensitivity audit：configs/recommendations/historical_reports/football_data_co_uk_market_feature_rolling_window_market_odds_band_final_answer_sensitivity_audit_v1.json；report_key=historical_final_answer_sensitivity_audit:27beaf0bde0fb433；source_report_key=historical_probability_calibration_profile_gate:7675d712a9fa0ed8
sensitivity 结果：comparison_count=8；final_answer_count=8；runner_up_count=8；runner_up_coverage_rate=1.0；near_miss_count=2；near_miss_rate=0.25；actionable_near_miss_count=0；runner_up_higher_hit_probability_count=0；winner_loss_runner_up_hit_count=0；average_score_gap=0.04309723645191034；min_score_gap=0.011817630397224388；diagnostic_codes=[no_higher_hit_probability_runner_up, no_actionable_near_miss]
阶段性结论：这是本轮核心能力上的正向证据。问题确实不只是仲裁权重，而是前一版 holdout 样本太稀疏；当最后赛季全部 rolling-window 进入 final-answer gate 后，market_odds_band calibration 可以改变最终答案并通过 no-harm 门禁。不过样本仍只有 8 个 final answers，不能直接 promotion 到默认推荐路径；下一阶段应把同样 season-aware gate 扩到 expanded A-league rolling-window / core+expanded 联合集，或做 rolling admission，确认跨联赛、跨窗口稳定后才考虑 profile artifact active/staged
README 更新 season-aware holdout、五大联赛 rolling-window suite、通过的 rolling-window profile gate artifact、sensitivity audit 与 shadow-only 结论；该能力属于“rolling-window final-answer calibration evidence / user-answer-first core validation”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-296 当前落地能力：

```text
按 V3.1-295 结论把同一套 season-aware market_odds_band profile gate 扩到 expanded A-league rolling-window 套件；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产路径，只验证五大联赛正向信号是否能跨扩展联赛稳定复现
确认 expanded A-league rolling-window suite 可用：configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1.json；enabled_slice_count=210；fixture exposures=2520；覆盖 ENG_CHAMPIONSHIP、GER_2_BUNDESLIGA、ITA_SERIE_B、ESP_SEGUNDA_DIVISION、FRA_LIGUE_2、NED_EREDIVISIE、PRT_PRIMEIRA_LIGA
生成 expanded A-league market_odds_band transform artifact：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_probability_calibration_transform_v1.json；report_key=historical_probability_calibration_transform:4aa769d7dbf0a69b
strict transform 结果：validation_count=504；calibration_bucket_count=106；usable_calibration_bucket_count=61；accepted_competition_count=0；rejected_competition_count=7；所有扩展联赛都有验证样本，但都未同时满足 Brier、log loss、ECE、hit-rate/objective 的 no-harm 接受条件
生成 strict expanded A-league profile gate artifact：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_probability_calibration_profile_gate_v1.json；report_key=historical_probability_calibration_profile_gate:ccafab6604805e06；selected_competition_ids=[]；rejected_competition_ids=[ENG_CHAMPIONSHIP, ESP_SEGUNDA_DIVISION, FRA_LIGUE_2, GER_2_BUNDESLIGA, ITA_SERIE_B, NED_EREDIVISIE, PRT_PRIMEIRA_LIGA]；passed_final_answer_gate=false；warning=historical_probability_calibration_profile_gate:no_selected_competitions
为诊断 final-answer 影响，生成 include-rejected shadow gate artifact：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_probability_calibration_profile_gate_include_rejected_v1.json；report_key=historical_probability_calibration_profile_gate:50113a24c21b73e7；selected_competition_ids=7 个扩展联赛；baseline_slice_count=42；adjusted_slice_count=42；adjusted_fixture_count=504；final_answer_scenario_variant_count=3
include-rejected gate 结果明确回撤：suite_status=regressed；quality_gate_passed=false；baseline_final_hit_rate=0.6666666666666666；candidate_final_hit_rate=0.5952380952380952；final_hit_rate_delta=-0.0714285714285714；final_hit_count_delta=-3；baseline_roi=-0.1833861111111111；candidate_roi=-0.26511333333333337；roi_delta=-0.08172722222222226；profit_loss_delta=-5.406000000000002；brier_score_delta=0.002012583982812177；log_loss_delta=0.0036296001769993147；mean_calibration_error_delta=0.0067897609632306954；final_answer_changed_count=20
生成 include-rejected sensitivity artifact：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_final_answer_sensitivity_audit_include_rejected_v1.json；report_key=historical_final_answer_sensitivity_audit:7de1fb9e9812725b；source_report_key=historical_probability_calibration_profile_gate:50113a24c21b73e7
sensitivity 结果：comparison_count=42；final_answer_count=42；runner_up_count=42；runner_up_coverage_rate=1.0；near_miss_count=38；near_miss_rate=0.9047619047619048；actionable_near_miss_count=15；actionable_near_miss_rate=0.35714285714285715；runner_up_higher_hit_probability_count=13；winner_loss_runner_up_hit_count=7；average_score_gap=0.013464407025781392；min_score_gap=0.00040189913623267515；diagnostic_codes=[]
进一步生成 neutral-profit scoped diagnostic：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_probability_calibration_profile_gate_neutral_profit_scope_v1.json；report_key=historical_probability_calibration_profile_gate:86cf39d4234797c0；scope=[GER_2_BUNDESLIGA, NED_EREDIVISIE, PRT_PRIMEIRA_LIGA]；baseline_slice_count=18；adjusted_slice_count=18；adjusted_fixture_count=216
neutral-profit scope 结果：final_hit_rate_delta=0.0；final_hit_count_delta=0；roi_delta=0.0188888888888889；profit_loss_delta=0.6800000000000002；final_answer_changed_count=6；但 suite_status=mixed 且 brier_score_delta=0.0018686083356507371、log_loss_delta=0.004133156313292918、mean_calibration_error_delta=0.0031835684654185625 均回撤，因此仍然 passed_final_answer_gate=false，不允许 promotion
阶段性结论：五大联赛 rolling-window 上的 market_odds_band 正向证据不能直接泛化到 expanded A-league。扩展联赛候选覆盖不是主要瓶颈，因为 runner_up_coverage_rate=1.0、near_miss_rate=0.9047619047619048；主要瓶颈是该广义校准 profile 在扩展联赛上会伤害概率质量和最终命中。下一阶段应做 competition/odds-band admission search，主动排除 ESP_SEGUNDA_DIVISION、FRA_LIGUE_2 等拖累折，并只允许满足 no-harm 概率质量与最终答案质量的 scoped profile 进入后续 rolling admission
README 更新 expanded A-league strict transform、strict gate、include-rejected shadow gate、sensitivity audit、neutral-profit scoped diagnostic 与 non-promotion 结论；该能力属于“expanded-league generalization guard / calibration promotion blocker”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-297 当前落地能力：

```text
按 V3.1-296 结论继续做 competition/odds-band admission search；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认生产路径，只验证 expanded A-league 是否存在可推广的窄域 market_odds_band calibration profile
生成 neutral-profit scope outcome/probability profile grid：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_neutral_profit_scope_profile_grid_v1.json；report_key=historical_probability_calibration_profile_grid:70886c7b46565f6c
outcome/probability grid 范围：competition_ids=[GER_2_BUNDESLIGA, NED_EREDIVISIE, PRT_PRIMEIRA_LIGA]；blend_weights=[0.25]；target_outcome_groups=[home_win, draw, away_win]；probability_bands=[0.20:0.30, 0.30:0.40, 0.40:0.60]；decimal_odds_bands=[all]；candidate_count=9；accepted_count=0；rejected_count=9
outcome/probability grid 结论：大多数窄段会调整 fixture 概率但不改变最终答案；best_candidate=home_win 0.20:0.30，adjusted_fixture_count=17，final_answer_changed_count=0；唯一明显移动概率质量的 high-home 段仍 brier_score_delta=0.00030166003915324535、log_loss_delta=0.0006074740762045394、mean_calibration_error_delta=0.00028512610698638863，不能通过 no-harm
生成 neutral-profit scope odds-band profile grid：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_neutral_profit_scope_odds_band_profile_grid_v1.json；report_key=historical_probability_calibration_profile_grid:bb03f5f4bf73313e
odds-band grid 范围：competition_ids=[GER_2_BUNDESLIGA, NED_EREDIVISIE, PRT_PRIMEIRA_LIGA]；blend_weights=[0.25]；target_outcome_groups=[all]；probability_bands=[0.00:1.00]；decimal_odds_bands=[1.01:1.35, 1.35:1.70, 1.70:2.30, 2.30:5.00]；candidate_count=4；accepted_count=0；rejected_count=4
odds-band grid best_candidate=decimal_odds 1.35:1.70；adjusted_fixture_count=53；brier_score_delta=-0.00007356581882576874；log_loss_delta=-0.0001547649227806036；mean_calibration_error_delta=0.000019523787024355865；final_answer_changed_count=0；结论是中赔率段可轻微改善部分概率指标，但未改变用户最终答案且 ECE 仍轻微回撤
生成单联赛 gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_ger_2_bundesliga_profile_gate_v1.json；report_key=historical_probability_calibration_profile_gate:891a2b0b1b9c8ff8；selected_competition_ids=[GER_2_BUNDESLIGA]；final_answer_changed_count=2；final_hit_rate_delta=0；roi_delta=0.02833333333333335；profit_loss_delta=0.3400000000000003；但 brier_score_delta=0.0032840433326689067、log_loss_delta=0.006684040713463124、mean_calibration_error_delta=0.004101049856003458，passed_final_answer_gate=false
生成单联赛 gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_ned_eredivisie_profile_gate_v1.json；report_key=historical_probability_calibration_profile_gate:ee529fe8bd0466d4；selected_competition_ids=[NED_EREDIVISIE]；final_answer_changed_count=1；final_hit_rate_delta=0；roi_delta=0；但 brier_score_delta=0.002609762756683155、log_loss_delta=0.00771763204379966、mean_calibration_error_delta=0.006032360035718831，passed_final_answer_gate=false
生成单联赛 gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_prt_primeira_liga_profile_gate_v1.json；report_key=historical_probability_calibration_profile_gate:981b1049da1708d7；selected_competition_ids=[PRT_PRIMEIRA_LIGA]；suite_status=improved；brier_score_delta=-0.0034884987884234997；log_loss_delta=-0.009744519830393428；mean_calibration_error_delta=-0.006379478673712635；但 final_answer_changed_count=0，passed_final_answer_gate=false
生成 blend_weight=0.25 strict profile gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_blend025_strict_profile_gate_v1.json；report_key=historical_probability_calibration_profile_gate:ff95ba93d214ad3d；transform selected_competition_ids=[FRA_LIGUE_2]；final_answer_changed_count=0；brier_score_delta=0.006680247390293742；log_loss_delta=0.013898617766548438；mean_calibration_error_delta=0.00829349097104587；passed_final_answer_gate=false
阶段性结论：expanded A-league 仍未找到“改变最终答案且概率质量 no-harm”的 market_odds_band profile。德乙/荷甲能改变最终答案但伤害概率质量；葡超改善概率质量但不改变最终答案；法乙在 blend_weight=0.25 下虽被 transform 接受，但最终答案不变且概率质量回撤。不能 promotion，不能进入 default/staged runtime profile
新增工程观察：historical_probability_calibration_profile_grid 当前每个候选都会完整重算 profile gate，且 gate CLI 会打印大型 manifest/report JSON；后续为了继续扩大搜索，应优先增加 baseline/cache 复用或 summary-only 输出，避免把调试时间浪费在重复回放与巨型 stdout 上
README 更新本轮 outcome/probability grid、odds-band grid、单联赛 gate、strict blend=0.25 gate 与 non-promotion 结论；该能力属于“expanded-league narrow admission search / final-answer no-harm blocker”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-298 当前落地能力：

```text
按 V3.1-297 的工程观察，先降低 probability calibration profile-gate/profile-grid 调试噪音成本；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不改变任何 calibration/promotion 逻辑
为 nutmeg-recommendation-historical-probability-calibration-profile-gate 新增 --stdout-summary-only；开启后 stdout 只输出 report_key、status、gate_id、transform_report_key、selected/rejected competitions、slice/fixture count、passed_final_answer_gate、suite aggregate_deltas_json、compact suite summary、quality_gate failed_checks、summary_json 与 warnings
为 nutmeg-recommendation-historical-probability-calibration-profile-grid 新增 --stdout-summary-only；开启后 stdout 只输出 report_key、status、grid counts、best_candidate、top_candidates 前 10、accepted_candidates 前 10、summary_json 与 warnings
full report artifact 保持不变：只要传入 --output-path，仍写出完整 Pydantic JSON，包括 suite manifest、完整 suite、quality gate、candidate summary 与候选细节；本轮没有改变 report_key 计算、profile gate 通过条件、grid accepted/rejected 判定或 final-answer gate 逻辑
新增单元测试覆盖 summary-only 输出不会包含 bulky suite_manifest、不会输出 suite comparisons、不会输出 candidate summary_json，并确认 CLI args 能解析 --stdout-summary-only
完成 smoke：用 euro_2024_knockout_sample.json 跑 profile-grid --stdout-summary-only --candidate-limit 1 --no-fail-process，stdout 被压缩为摘要，临时 smoke artifact 已清理
阶段性结论：这不是准确率提升，而是下一轮扩大真实历史 calibration 搜索前的必要工程减负。它让长 profile-grid 批量运行更容易读取结果、更少污染终端，同时保证本地 artifact 仍可审计、可回放、可追踪
README 更新 probability calibration profile-gate/profile-grid compact stdout 能力与 non-behavioral 结论；该能力属于“calibration search ergonomics / historical benchmark throughput”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-299 当前落地能力：

```text
按 V3.1-298 的下一步继续降低 probability calibration profile-grid 扩大搜索成本；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不改变 candidate scoring、sorting、quality gate 或 promotion 逻辑
在 historical_probability_calibration_profile_grid 内新增 in-run transform-report cache：同一次 grid build 内，候选只要 historical_slices 与 transform_options 相同，就复用同一份 build_historical_probability_calibration_transform_report 结果；最常见收益是同一 blend_weight / segment_mode 下不同 target outcome、probability band、odds band 不再重复构建同一套 calibration bucket evidence
profile-grid report 新增 transform_cache_hit_count、transform_cache_miss_count、unique_transform_report_count；candidate payload 新增 transform_cache_key、transform_cache_status、transform_report_key；compact stdout 也会输出 cache counts 与 candidate transform_report_key，便于判断大规模搜索是否真正复用
candidate_key 仍然只基于原有候选决策摘要计算，未把 cache metadata 纳入候选身份；report_key 仍由 options 与 candidate_keys 计算，因此这次性能优化不改变候选身份、排序或 promotion evidence 的逻辑含义
新增单元测试覆盖同一 blend_weight 下第一个候选 transform cache miss、后续候选 hit；两个 blend_weight 对应两个 unique transform reports；candidate window 只评估一个候选时只产生一次 miss；summary-only payload 包含 cache count 与 transform_report_key
完成 CLI smoke：用 euro_2024_knockout_sample.json 跑 profile-grid --stdout-summary-only，blend_weights=0.25,1.0、target_outcome_groups=home_win,draw；结果 candidate_count=4、transform_cache_miss_count=2、transform_cache_hit_count=2、unique_transform_report_count=2；输出写入 /tmp，不污染项目报告目录
阶段性结论：这仍是调试吞吐能力，不是准确率提升。它把重复 transform 计算从“按候选”降到“按唯一 transform 参数组”，为下一轮更大的 competition/odds-band admission search 做准备
README 更新 transform-report reuse 能力与 non-behavioral 结论；该能力属于“calibration search throughput / profile-grid transform reuse”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-300 当前落地能力：

```text
按 V3.1-299 结论尝试用 transform-report reuse 扩大 expanded A-league market_odds_band admission search；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径
首次尝试 full broad grid：expanded A-league rolling-window suite，全 7 个扩展联赛，blend_weights=[0.10,0.25,0.50]，target_outcome_groups=[all,home_win,draw,away_win]，probability_bands=[0.00:1.00]，decimal_odds_bands=[1.01:1.35,1.35:1.70,1.70:2.30,2.30:3.50,3.50:8.00]，共 60 candidates；由于 profile-grid 当时没有候选级 progress，运行约 4 分钟仍无可观测输出，已主动中止，不生成 promotion evidence
第二次尝试 batch0：candidate_start_index=0、candidate_limit=12，同样 strict no-harm gate；运行约 4 分钟仍无可观测输出，说明瓶颈已经从 transform report 转移到每个候选重复 final-answer suite 回放；同样主动中止，不生成 promotion evidence
为避免后续陷入 silent long run，profile-grid 新增 --progress-jsonl-path；开启后写出 grid_started、candidate_started、candidate_completed、grid_completed 事件，candidate_completed 包含 candidate_key、decision、decision_reasons、transform_cache_status、transform_report_key、gate_report_key、passed_final_answer_gate、elapsed_seconds
profile-grid report 与 compact stdout 新增 elapsed_seconds、candidate_elapsed_seconds、slowest_candidate_index、slowest_candidate_elapsed_seconds；candidate payload 新增 elapsed_seconds；summary_json 记录 progress_jsonl_path
新增单元测试覆盖 progress JSONL 事件顺序、grid_completed 汇总、cache hit/miss counts、slowest candidate 信息、CLI args 解析 --progress-jsonl-path
完成 smoke：用 euro_2024_knockout_sample.json 跑 profile-grid --stdout-summary-only --progress-jsonl-path --candidate-limit 2；输出包含 transform_cache_hit_count=1、transform_cache_miss_count=1、unique_transform_report_count=1、elapsed_seconds、slowest_candidate_index；JSONL 包含 6 个事件并可正常解析
阶段性结论：这次没有获得新的准确率证据，但修复了后续 calibration 搜索的可观测性瓶颈。下一次 expanded A-league broad search 应按小批次运行，并使用 progress_jsonl 观察候选耗时；若仍然过慢，下一步应做 baseline/final-answer suite reuse，而不是继续盲目扩大网格
README 更新 profile-grid progress telemetry 与 non-behavioral 结论；该能力属于“calibration search observability / long-run benchmark control”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-301 当前落地能力：

```text
按 V3.1-300 结论继续解决 profile-grid 每候选重复 final-answer suite 回放的吞吐瓶颈；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不改变 candidate scoring、sorting、quality gate 或 promotion 逻辑
在 historical_probability_calibration_profile_gate 新增可选 baseline_backtest_cache；profile-gate 构造 suite 时，baseline slice 的 run_historical_recommendation_backtest 结果可按 slice_id + as_of_time_utc + backtest_options 复用；如果没有传 cache，standalone profile-gate 行为保持原样
在 historical_probability_calibration_profile_grid 内为同一次 grid build 维护 baseline_backtest_cache；每个候选仍然运行自己的 adjusted/candidate backtest，但共享相同 validation slice 的 unadjusted baseline backtest，从而避免候选数扩大时重复计算同一 baseline final answer
profile-gate report 新增 baseline_backtest_cache_hit_count、baseline_backtest_cache_miss_count；profile-grid report 新增 baseline_backtest_cache_hit_count、baseline_backtest_cache_miss_count、unique_baseline_backtest_count；candidate payload、compact stdout、progress JSONL candidate_completed/grid_completed 均输出这些 cache 计数
cache metadata 不参与 candidate_key 身份计算；candidate_key 继续基于候选决策摘要，transform/baseline cache key、cache status、elapsed seconds 等只进入 summary/output，因此这是 non-behavioral throughput optimization，不改变候选身份语义、排序或 promotion evidence
新增单元测试覆盖 profile-grid 两候选时 baseline cache 第一次 miss、第二次 hit；四候选跨两个 blend weight 时 baseline cache 仍只 miss 一次并 hit 三次；candidate window 只评估一个候选时只 miss 一次；summary-only payload 与 progress JSONL 都包含 baseline cache counts
完成 J1 小套件 smoke：football_data_co_uk_j1_closing_only_feature_suite，candidate_limit=2，target_outcome_groups=[home_win,draw]，blend_weight=0.25，轻量 1x1/single gate；结果 baseline_backtest_cache_miss_count=1、baseline_backtest_cache_hit_count=1、unique_baseline_backtest_count=1，transform_cache_miss_count=1、transform_cache_hit_count=1，两个候选均完成；输出写入 /tmp，不污染项目报告目录
阶段性结论：这仍不是新的准确率证据，而是为 expanded A-league broad admission search 去掉重复 baseline final-answer 回放成本。下一步可以重新按小批次跑 expanded A-league broad grid，并用 progress_jsonl 观察候选耗时；如果 adjusted/candidate backtest 仍是瓶颈，再考虑更深的 candidate-suite cache 或并行/分片 runner
README 更新 baseline-backtest reuse 能力与 non-behavioral 结论；该能力属于“calibration search throughput / profile-grid baseline reuse”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-302 当前落地能力：

```text
按 V3.1-301 结论重新运行 expanded A-league broad calibration search 小批次；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不 promotion，只验证 baseline reuse + progress telemetry 后能否找到改变最终答案且通过 no-harm gate 的窄域 profile
运行 batch0 profile-grid：suite=football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1；candidate_start_index=0；candidate_limit=4；grid_id=probability-calibration-profile-grid-expanded-a-league-broad-odds-outcome-v3.1；blend_weights=[0.10,0.25,0.50]；target_outcome_groups=[all,home_win,draw,away_win]；probability_bands=[0.00:1.00]；decimal_odds_bands=[1.01:1.35,1.35:1.70,1.70:2.30,2.30:3.50,3.50:8.00]；strict no-harm gate 要求 final_answer_changed_count>=1、hit/ROI/P&L 不下降、Brier/log-loss/ECE 不回撤
生成 batch0 artifact：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_broad_odds_outcome_profile_grid_batch0_progress_v1.json；report_key=historical_probability_calibration_profile_grid:0b07788778e3a8d8；progress JSONL 同名 .jsonl
batch0 性能证据：candidate_count=4；elapsed_seconds=232.239583；slowest_candidate_index=0；slowest_candidate_elapsed_seconds=105.714331；transform_cache_miss_count=1；transform_cache_hit_count=3；baseline_backtest_cache_miss_count=42；baseline_backtest_cache_hit_count=126；unique_baseline_backtest_count=42；说明 baseline reuse 明显降低后续候选耗时，但 adjusted/candidate backtest 仍是主要成本
batch0 结果：accepted_count=1；accepted candidate_index=3；profile=all outcomes + decimal_odds 2.30:3.50 + blend_weight 0.10；selected_competition_ids=ENG_CHAMPIONSHIP、ESP_SEGUNDA_DIVISION、FRA_LIGUE_2、GER_2_BUNDESLIGA、ITA_SERIE_B、NED_EREDIVISIE、PRT_PRIMEIRA_LIGA；adjusted_fixture_count=331；final_answer_changed_count=5；final_hit_rate_delta=0.0；final_hit_count_delta=0；roi_delta=0.10519277777777779；profit_loss_delta=17.0244；brier_score_delta=-0.004209589930242313；log_loss_delta=-0.008692389373464948；mean_calibration_error_delta=-0.0022002489006500148；passed_final_answer_gate=true
三个 rejected candidates：1.01:1.35 段因 Brier/log-loss/ECE、final_answer_changed_count、suite_status 回撤被拒；1.35:1.70 段概率质量改善但 final_answer_changed_count=0 被拒；1.70:2.30 段 final_answer_changed_count=2 但概率质量回撤被拒
将 accepted candidate 单独跑 full profile-gate artifact：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_all_230_350_blend010_profile_gate_v1.json；report_key=historical_probability_calibration_profile_gate:3b1f56797589ff1e；suite_key=historical_probability_calibration_profile_gate_suite:a93832ef0d8db32d；quality_gate_key=historical_recommendation_suite_quality_gate:eb29757c3efc6eeb；passed_final_answer_gate=true；suite_status=improved；baseline_final_hit_rate=0.6666666666666666；candidate_final_hit_rate=0.6666666666666666；baseline_roi=-0.1833861111111111；candidate_roi=-0.07819333333333332；baseline_profit_loss=-26.4076；candidate_profit_loss=-9.383199999999999
生成 sensitivity audit artifact：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_all_230_350_blend010_sensitivity_audit_v1.json；report_key=historical_final_answer_sensitivity_audit:8d4e7fb73f79b1bd；source_report_key=historical_probability_calibration_profile_gate:3b1f56797589ff1e；runner_up_coverage_rate=1.0；near_miss_rate=0.9047619047619048；actionable_near_miss_count=9；runner_up_higher_hit_probability_count=5；winner_loss_runner_up_hit_count=6；diagnostic_codes=[]
阶段性结论：这是本轮 expanded A-league market_odds_band line 第一个同时满足“改变最终答案”和“概率质量 no-harm”的窄域 profile。它仍然 shadow-only，不能直接 default/runtime promotion；下一步应继续跑相邻 batch（candidate_start_index=4 起），并做 cross-scope validation/rolling admission，确认 2.30:3.50 + blend 0.10 是否稳定，而不是只在 batch0 偶然成立
README 更新 batch0 profile-grid、accepted full profile-gate、sensitivity audit、performance evidence 与 shadow-only 结论；该能力属于“expanded-league scoped calibration evidence / final-answer no-harm candidate discovery”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-303 当前落地能力：

```text
按 V3.1-302 结论继续运行 expanded A-league broad calibration search 相邻批次；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不 promotion，只扩展同一 strict no-harm gate 下的 shadow evidence
运行 batch1 profile-grid：candidate_start_index=4；candidate_limit=4；artifact=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_broad_odds_outcome_profile_grid_batch1_progress_v1.json；report_key=historical_probability_calibration_profile_grid:5dc39ab514656dce；accepted_count=0；rejected_count=4；elapsed_seconds=207.277695；slowest_candidate_index=4；主要拒绝原因集中在 Brier/log-loss/ECE、final hit、ROI/profit 与 suite_status 回撤
运行 batch2 profile-grid：candidate_start_index=8；candidate_limit=4；artifact=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_broad_odds_outcome_profile_grid_batch2_progress_v1.json；report_key=historical_probability_calibration_profile_grid:85e3bffc254f055d；accepted_count=0；rejected_count=4；elapsed_seconds=204.136185；slowest_candidate_index=8；拒绝原因是两个候选没有改变最终答案、两个 draw 低赔率段没有 adjusted fixtures
运行 batch3 profile-grid：candidate_start_index=12；candidate_limit=4；artifact=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_broad_odds_outcome_profile_grid_batch3_progress_v1.json；report_key=historical_probability_calibration_profile_grid:dcb2dd7ab2e7b970；accepted_count=1；rejected_count=3；elapsed_seconds=207.856422；slowest_candidate_index=12
batch3 accepted candidate_index=13；profile=target_outcomes=[draw] + decimal_odds 2.30:3.50 + blend_weight 0.10；selected_competition_ids=ENG_CHAMPIONSHIP、ESP_SEGUNDA_DIVISION、FRA_LIGUE_2、GER_2_BUNDESLIGA、ITA_SERIE_B、NED_EREDIVISIE、PRT_PRIMEIRA_LIGA；adjusted_fixture_count=277；final_answer_changed_count=5；final_hit_rate_delta=0.0；final_hit_count_delta=0；roi_delta=0.10519277777777779；profit_loss_delta=17.0244；brier_score_delta=-0.004209589930242313；log_loss_delta=-0.008692389373464948；mean_calibration_error_delta=-0.0022002489006500148；passed_final_answer_gate=true
将 draw-only accepted candidate 单独跑 full profile-gate artifact：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_draw_230_350_blend010_profile_gate_v1.json；report_key=historical_probability_calibration_profile_gate:403430b1fcbfef00；suite_key=historical_probability_calibration_profile_gate_suite:7eff137a51425630；quality_gate_key=historical_recommendation_suite_quality_gate:d63171ed8edf07ee；passed_final_answer_gate=true；suite_status=improved；baseline_final_hit_rate=0.6666666666666666；candidate_final_hit_rate=0.6666666666666666；baseline_roi=-0.1833861111111111；candidate_roi=-0.07819333333333332；baseline_profit_loss=-26.4076；candidate_profit_loss=-9.383199999999999
full gate 的 transform_competition_decisions 显示 FRA_LIGUE_2 与 NED_EREDIVISIE accepted，其余扩展 A-league rejected；最终 gate 仍在 42 个 rolling-window validation slices 上验证，不把 transform 接受联赛等同于生产默认联赛
生成 draw-only sensitivity audit artifact：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_draw_230_350_blend010_sensitivity_audit_v1.json；report_key=historical_final_answer_sensitivity_audit:e32b1c3900d55b1a；source_report_key=historical_probability_calibration_profile_gate:403430b1fcbfef00；runner_up_coverage_rate=1.0；near_miss_rate=0.9047619047619048；actionable_near_miss_count=9；runner_up_higher_hit_probability_count=5；winner_loss_runner_up_hit_count=6；diagnostic_codes=[]
阶段性结论：batch1/batch2 是负样本证据，batch3 发现的 draw-only 2.30:3.50 profile 是第二个同时满足“改变最终答案”和“概率质量 no-harm”的 shadow candidate，而且比 batch0 all-outcome profile 更窄。它仍不进入 runtime/default；下一步应把 batch0 all-outcome 与 batch3 draw-only 做 cross-scope validation / rolling admission 对比，再决定是否进入 staged active proposal
README 更新 batch1-batch3 profile-grid、draw-only full profile-gate、sensitivity audit、negative evidence 与 shadow-only 结论；该能力属于“expanded-league scoped calibration evidence / draw-odds segment final-answer no-harm candidate discovery”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-304 当前落地能力：

```text
按 V3.1-303 结论把 batch0 all-outcome 与 batch3 draw-only 两个正向 shadow candidate 放进同一 probability-calibration rolling-admission 口径对比；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不 promotion，只验证它们是否能进入 staged active proposal
运行 all-outcome rolling admission：artifact=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_all_230_350_blend010_rolling_admission_v1.json；report_key=historical_probability_calibration_profile_rolling_admission:a2d1f57731c12e85；source_gate_report_key=historical_probability_calibration_profile_gate:f2206671287e3785；status=shadow_only；candidate_profile_allowed=false；shadow_allowed=true；fold_count=13；active_fold_count=13；failed_fold_count=11；active_competition_fold_count=7；active_season_cutoff_fold_count=3；active_rolling_fold_count=3
运行 draw-only rolling admission：artifact=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_draw_230_350_blend010_rolling_admission_v1.json；report_key=historical_probability_calibration_profile_rolling_admission:a256a40795302d56；source_gate_report_key=historical_probability_calibration_profile_gate:403430b1fcbfef00；status=shadow_only；candidate_profile_allowed=false；shadow_allowed=true；fold_count=13；active_fold_count=13；failed_fold_count=11；active_competition_fold_count=7；active_season_cutoff_fold_count=3；active_rolling_fold_count=3
两个候选 overall fold 均通过 final-answer gate 并能内部 emitted_profile：all-outcome adjusted_fixture_count=331、bucket_count=92；draw-only adjusted_fixture_count=277、bucket_count=92；两者 final_hit_rate_delta=0.0、roi_delta=0.10519277777777779、profit_loss_delta=17.0244、brier_score_delta=-0.004209589930242313、log_loss_delta=-0.008692389373464948、mean_calibration_error_delta=-0.0022002489006500148
两个候选通过的 active folds 只有 season_cutoff:2024-2025 与 rolling_window:3:2022-2023..2024-2025；较早 season cutoff / rolling window 与大多数 competition folds 未通过。典型失败原因包括 final_answer_gate_not_passed、runtime_profile_not_emitted、bucket_count_below_threshold；ESP_SEGUNDA_DIVISION fold 对两者均出现 final_hit_rate_delta=-0.16666666666666666、ROI/probability-quality 回撤，是明确的 fold-local 阻断信号
由于 candidate_profile_allowed=false，两个 --profile-output-path 均未写出 active candidate profile；这确认当前正向 profile 只能作为 recent-window shadow evidence，不能进入 runtime/default，也不能进入 staged active proposal
阶段性结论：batch0 all-outcome 与 batch3 draw-only 在 overall/latest-window 上同样正向，但 rolling admission 暴露 11/13 active folds 失败，说明 signal 尚未跨联赛/跨早期赛季稳定。下一步不应 promotion，而应做 fold-aware refinement：收窄到通过 fold 的 evidence scope，或新增 calibration admission search 的 fold-pass objective，让 profile-grid 在生成候选时直接优化 active fold pass count
README 更新 rolling-admission comparison、两个 admission report、fold gate 阻断原因与 no-promotion 结论；该能力属于“probability calibration rolling admission / cross-scope validation / active promotion stop”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-305 当前落地能力：

```text
按 V3.1-304 结论修正 probability-calibration rolling admission 的 fold 阈值口径；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不 promotion，只把 overall gate 与 fold gate 的质量阈值拆开，避免小样本 fold 被 overall 阈值误伤
historical_probability_calibration_profile_rolling_admission 新增 fold_quality_gate_options；_artifact_fold 会用 fold_quality_gate_options 替换 artifact gate 的 quality_gate_options，overall artifact 继续使用原始 strict quality gate
CLI 新增 fold-specific quality 参数：--fold-min-final-hit-sample-size、--fold-min-final-hit-rate-delta、--fold-min-final-answer-changed-count、--fold-min-roi-delta、--fold-min-profit-loss-delta、--fold-max-brier-score-delta、--fold-max-log-loss-delta、--fold-max-mean-calibration-error-delta；未提供 fold 参数时保持旧行为，fold gate 继续继承 overall thresholds
新增 deterministic tests 覆盖：fold_quality_gate_options 只作用于 fold artifact，不影响 overall artifact；CLI fold 参数正确映射到 options.fold_quality_gate_options；既有 CLI 写 profile 流程继续通过
使用 fold-aware 阈值重跑 draw-only rolling admission：overall 仍要求 min_final_hit_sample_size=20、min_final_answer_changed_count=1、hit/ROI/P&L/Brier/logloss/ECE no-harm；fold gate 使用 fold_min_final_hit_sample_size=1、fold_min_final_answer_changed_count=0；artifact=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_draw_230_350_blend010_fold_aware_rolling_admission_v1.json；report_key=historical_probability_calibration_profile_rolling_admission:b9895d22f1fe8447；status=shadow_only；candidate_profile_allowed=false；fold_count=13；active_fold_count=13；failed_fold_count=5
使用同一 fold-aware 阈值重跑 all-outcome rolling admission：artifact=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_market_odds_band_all_230_350_blend010_fold_aware_rolling_admission_v1.json；report_key=historical_probability_calibration_profile_rolling_admission:1cccb2885baa0421；status=shadow_only；candidate_profile_allowed=false；fold_count=13；active_fold_count=13；failed_fold_count=5
两个候选的 failed_fold_count 均从 V3.1-304 的 11 降到 5；通过 fold 现在包括 ENG_CHAMPIONSHIP、FRA_LIGUE_2、GER_2_BUNDESLIGA、ITA_SERIE_B、NED_EREDIVISIE、PRT_PRIMEIRA_LIGA、season_cutoff:2024-2025、rolling_window:3:2022-2023..2024-2025；未通过 fold 集中在 ESP_SEGUNDA_DIVISION、season_cutoff:2022-2023、season_cutoff:2023-2024、rolling_window:1:2020-2021..2022-2023、rolling_window:2:2021-2022..2023-2024
两个候选仍未写出 configs/recommendations/profiles 下的 active profile；这确认 fold-aware 只是更准确的 admission diagnosis，不是放宽 promotion。当前 block 已从“fold 阈值不适配”收缩为“西乙/早期窗口不稳定”
阶段性结论：2.30:3.50 market_odds_band signal 在 latest window 与多数 competition folds 上有价值，但不能跨所有 active folds 稳定晋级。下一步应做 scoped refinement：优先验证排除 ESP_SEGUNDA_DIVISION 或引入 time/fold-aware calibration profile 的候选，目标是减少 failed_fold_count 而不是只追 overall ROI
README 更新 fold-aware rolling admission 参数、两个真实 report、失败 fold 收缩结果与 no-promotion 结论；该能力属于“fold-aware calibration admission / scoped profile diagnosis / active promotion guardrail”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-306 当前落地能力：

```text
按 V3.1-305 结论验证 scoped refinement：将 ESP_SEGUNDA_DIVISION 从 expanded A-league rolling-window suite 中排除，确认它是否是独立的 fold blocker；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不 promotion
生成 scoped suite manifest：configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_no_esp_segunda_suite_v1.json；suite_id=football_data_co_uk_expanded_a_leagues_rolling_window_no_esp_segunda_suite_v1；slice_count=180；esp_segunda_division slice_count=0；用途仅限 shadow/admission diagnostics
重跑 no-ESP draw-only 2.30:3.50 + blend 0.10 fold-aware rolling admission：artifact=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_rolling_window_market_odds_band_draw_230_350_blend010_fold_aware_rolling_admission_v1.json；report_key=historical_probability_calibration_profile_rolling_admission:92101c4f13c08001；status=shadow_only；candidate_profile_allowed=false；fold_count=12；active_fold_count=12；failed_fold_count=1；active_competition_fold_count=6；active_season_cutoff_fold_count=3；active_rolling_fold_count=3
no-ESP draw-only overall fold：adjusted_fixture_count=211；bucket_count=82；final_hit_rate_delta=0.02777777777777779；roi_delta=0.12504444444444446；profit_loss_delta=13.504800000000003；brier_score_delta=-0.0056366367028146125；log_loss_delta=-0.011436047358709511；mean_calibration_error_delta=-0.005677368018753459；唯一 failed fold=rolling_window:2:2021-2022..2023-2024
重跑 no-ESP all-outcome 2.30:3.50 + blend 0.10 fold-aware rolling admission：artifact=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_rolling_window_market_odds_band_all_230_350_blend010_fold_aware_rolling_admission_v1.json；report_key=historical_probability_calibration_profile_rolling_admission:8c67251a04c71a1a；status=shadow_only；candidate_profile_allowed=false；fold_count=12；active_fold_count=12；failed_fold_count=3
no-ESP all-outcome overall fold 与 draw-only 同样正向：adjusted_fixture_count=265；bucket_count=82；final_hit_rate_delta=0.02777777777777779；roi_delta=0.12504444444444446；profit_loss_delta=13.504800000000003；brier_score_delta=-0.0056366367028146125；log_loss_delta=-0.011436047358709511；mean_calibration_error_delta=-0.005677368018753459；failed folds=season_cutoff:2022-2023、rolling_window:1:2020-2021..2022-2023、rolling_window:2:2021-2022..2023-2024
阶段性结论：排除 ESP_SEGUNDA_DIVISION 明显解除主要 competition-level blocker；draw-only 比 all-outcome 更稳定，是当前最强 shadow candidate，但仍未通过 zero-failed-fold admission。下一步应聚焦唯一剩余失败窗口 rolling_window:2:2021-2022..2023-2024，做 time-aware cutoff 或更窄 odds/outcome scope，而不是直接放宽 max_failed_fold_count
README 更新 no-ESP scoped suite、draw-only/all-outcome no-ESP fold-aware admission reports、指标与 no-promotion 结论；该能力属于“scoped calibration refinement / competition blocker isolation / no-active-profile guardrail”，不接实时 API、不接 VPS、不接自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-307 当前落地能力：

```text
按 V3.1-306 结论继续诊断唯一剩余失败窗口 rolling_window:2:2021-2022..2023-2024；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不 promotion，只做受控 scope/blend admission evidence
生成 no-ESP-no-ITA scoped suite manifest：configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_no_esp_no_ita_serie_b_suite_v1.json；slice_count=150；esp_segunda_division slice_count=0；ita_serie_b slice_count=0；用途仅限 shadow/admission diagnostics
重跑 no-ESP-no-ITA draw-only 2.30:3.50 + blend 0.10 fold-aware rolling admission：artifact=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_no_ita_rolling_window_market_odds_band_draw_230_350_blend010_fold_aware_rolling_admission_v1.json；report_key=historical_probability_calibration_profile_rolling_admission:0fcf547a14516ec4；status=rejected；candidate_profile_allowed=false；shadow_allowed=false；fold_count=11；failed_fold_count=0；overall final_hit_rate_delta=0.0；roi_delta=0.0；profit_loss_delta=0.0；结论是整联赛排除能消除 fold 失败，但也消除了最终答案改变，因此不是可晋级候选
生成 no-ESP / exclude ITA_SERIE_B 2023-2024 scoped suite manifest：configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_no_esp_no_ita_2023_2024_suite_v1.json；slice_count=174；esp_segunda_division slice_count=0；ita_serie_b_2023_2024 slice_count=0；用途仅限 shadow/admission diagnostics
重跑 no-ESP / exclude ITA_SERIE_B 2023-2024 draw-only 2.30:3.50 + blend 0.10 fold-aware rolling admission：artifact=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_no_ita_2023_2024_rolling_window_market_odds_band_draw_230_350_blend010_fold_aware_rolling_admission_v1.json；report_key=historical_probability_calibration_profile_rolling_admission:c86e65db463f3bd0；status=rejected；candidate_profile_allowed=false；failed_fold_count=2；failed folds=competition:ITA_SERIE_B、season_cutoff:2024-2025；overall final_hit_rate_delta=0.0；roi_delta=0.0；profit_loss_delta=0.0；brier_score_delta=0.00010041991805564976；log_loss_delta=0.00020849749632190218；mean_calibration_error_delta=0.000028183556629368667
重跑 no-ESP draw-only 2.30:3.50 + blend 0.05 fold-aware rolling admission：artifact=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_rolling_window_market_odds_band_draw_230_350_blend005_fold_aware_rolling_admission_v1.json；report_key=historical_probability_calibration_profile_rolling_admission:132b6dbb2294bb51；status=rejected；candidate_profile_allowed=false；failed_fold_count=5；overall final_hit_rate_delta=0.0；roi_delta=0.0；profit_loss_delta=0.0
阶段性结论：ITA_SERIE_B 是当前唯一有最终答案收益的信号来源，但也带来一个 active rolling-window probability-quality blocker；简单整联赛排除、只排除 2023-2024、或降低 blend 都不能晋级。下一阶段应改造 profile search / grid objective，让候选直接优化 zero failed active folds + final-answer changed-count + probability no-harm，而不是继续手工后验排除
README 更新 ITA/time-scope diagnostics、三个真实 admission report、negative evidence 与 no-promotion 结论；该能力属于“scoped calibration diagnosis / fold-pass objective discovery / no-active-profile guardrail”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-308 当前落地能力：

```text
按 V3.1-307 结论把 fold stability 从后验 rolling admission 前移到 probability-calibration profile grid 的 candidate objective；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不 promotion
historical_probability_calibration_profile_grid 新增可选 fold_objective_options；CLI 新增 --enable-fold-objective 以及 fold-level final-answer/no-harm/active-fold 阈值参数；默认关闭，不影响旧 grid 行为
grid candidate 新增 fold_objective_report_key、fold_objective_status、fold_objective_candidate_profile_allowed、fold_objective_failed_fold_count、fold_objective_active_fold_count、fold_objective_active_competition_fold_count、fold_objective_active_season_cutoff_fold_count、fold_objective_active_rolling_fold_count、fold_objective_json；stdout compact candidate 同步输出关键 fold objective 字段
candidate decision 现在会在 fold objective 启用时把 rolling admission 未接受、failed_fold_count>0、failed rolling checks 转为 fold_objective:* rejection reasons；candidate sort key 同步纳入 failed_fold_count 和 final_answer_changed_count，让 grid search 可以直接优化 zero failed active folds + final-answer changed-count + probability no-harm
新增 deterministic tests 覆盖：fold objective rejected candidate 会被 grid 拦截并记录 failed fold；CLI 能映射 enable-fold-objective、fold quality gate overrides、fold active-count/rolling-window/max-failed-fold 参数；既有 profile grid tests 继续通过
生成真实 no-ESP draw-only fold-objective grid report：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_230_350_blend010_fold_objective_grid_v1.json；report_key=historical_probability_calibration_profile_grid:0f14d1d816fa0bed；candidate_count=1；accepted_count=0；rejected_count=1
真实 grid candidate 的 overall gate 仍为正向：final_answer_changed_count=1；final_hit_rate_delta=0.02777777777777779；roi_delta=0.12504444444444446；profit_loss_delta=13.504800000000003；brier_score_delta=-0.0056366367028146125；log_loss_delta=-0.011436047358709511；mean_calibration_error_delta=-0.005677368018753459
但新 fold objective 在 grid 阶段直接标记 rejected：fold_objective_status=shadow_only；fold_objective_failed_fold_count=1；failed_fold_ids=rolling_window:2:2021-2022..2023-2024；decision_reasons=fold_objective:failed_check:failed_fold_count、fold_objective:failed_fold_count、fold_objective:status:shadow_only
阶段性结论：grid 现在具备搜索层面的 fold blocker 感知能力，后续无需再依赖“overall 正向后再手工 rolling admission”才发现隐藏回撤。下一阶段应跑更宽的 fold-objective grid，搜索 odds/outcome/blend 邻域中第一个 accepted candidate；仍不允许放宽 max_failed_fold_count 或写入 default runtime profile
README 更新 fold-objective grid 设计、真实 report、candidate rejection evidence 与 no-production-change 结论；该能力属于“profile search objective hardening / active fold stability gate / no-active-profile guardrail”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-309 当前落地能力：

```text
按 V3.1-308 结论运行更宽但受控的 fold-objective grid；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不直接 promotion，只寻找 zero failed active folds + final-answer changed-count 的候选
生成 no-ESP draw-only adjacent odds fold-objective grid report：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_adjacent_odds_blend010_fold_objective_grid_v1.json；report_key=historical_probability_calibration_profile_grid:89837841f7721e00；candidate_count=4；accepted_count=1；rejected_count=3
grid 搜索范围：target_outcome_groups=draw；blend_weight=0.10；probability_band=0.00:1.00；decimal_odds_bands=2.20:3.40、2.25:3.45、2.30:3.50、2.35:3.55；fold objective 要求 failed_fold_count=0
accepted candidate：candidate_index=1；market odds 2.25:3.45；fold_objective_status=accepted；fold_objective_failed_fold_count=0；final_answer_changed_count=1；final_hit_rate_delta=0.02777777777777779；roi_delta=0.12504444444444446；profit_loss_delta=13.504800000000003；brier_score_delta=-0.0055595650171044175；log_loss_delta=-0.011274560301326564；mean_calibration_error_delta=-0.005579406751200555
rejected control candidate 2.30:3.50 仍因 rolling_window:2:2021-2022..2023-2024 被 fold objective 拦截；2.20:3.40 失败于 season_cutoff:2022-2023 与 rolling_window:1:2020-2021..2022-2023；2.35:3.55 没有 final-answer movement 且多折失败
将 accepted candidate 单独重跑 fold-aware rolling admission：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_rolling_window_market_odds_band_draw_225_345_blend010_fold_aware_rolling_admission_v1.json；report_key=historical_probability_calibration_profile_rolling_admission:0f7677760aeedac4；status=accepted；candidate_profile_allowed=true；shadow_allowed=true；fold_count=12；active_fold_count=12；failed_fold_count=0；active_competition_fold_count=6；active_season_cutoff_fold_count=3；active_rolling_fold_count=3
standalone admission overall fold：adjusted_fixture_count=192；bucket_count=82；selected_competition_ids=ENG_CHAMPIONSHIP、FRA_LIGUE_2、GER_2_BUNDESLIGA、ITA_SERIE_B、NED_EREDIVISIE、PRT_PRIMEIRA_LIGA；suite_status=improved；quality_gate_passed=true；final_hit_rate_delta=0.02777777777777779；roi_delta=0.12504444444444446；profit_loss_delta=13.504800000000003；brier_score_delta=-0.0055595650171044175；log_loss_delta=-0.011274560301326564；mean_calibration_error_delta=-0.005579406751200555
写出 active-mode candidate profile：configs/recommendations/profiles/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_fold_aware_active_candidate_profile_v1.json；profile_key=candidate_probability_calibration_profile:e753919b27cb3e62；mode=active；segment_mode=market_odds_band；blend_weight=0.10；target_outcomes=draw；min_decimal_odds=2.25；max_decimal_odds=3.45；bucket_count=82
阶段性结论：这是 expanded A-league no-ESP draw-only market_odds_band line 的第一个 fold-objective accepted profile candidate。它已经通过 overall + competition + season cutoff + rolling window active folds，但仍不写 default runtime profile；下一阶段应把该 accepted profile 接入 production proposal / smoke / benchmark quality gate / runtime shadow replay 链路，确认治理完整后再讨论 staged activation
README 更新 adjacent odds grid、accepted candidate、standalone rolling admission、active candidate profile 与 no-default-change 结论；该能力属于“fold-objective accepted calibration profile candidate / active admission evidence / governed promotion prerequisite”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-310 当前落地能力：

```text
按 V3.1-309 结论把 fold-objective accepted calibration profile 接入生产候选治理链；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不把 profile 写为 default/runtime，只生成可审计 proposal 和 gate evidence
新增 nutmeg-recommendation-historical-probability-calibration-profile-production-proposal；输入为 profile-grid report、fold-aware rolling-admission report、active candidate profile；输出为 production proposal report 与 staged proposal profile set
production proposal checks 覆盖：grid report generated、grid candidate accepted、candidate fold objective accepted/profile-allowed、rolling admission accepted/profile-allowed/shadow-allowed、candidate profile active、profile source_report_key 与 rolling gate evidence 链接、profile constraints 与 grid candidate 匹配、rolling metrics 与 grid candidate 匹配、overall adjusted fixture/bucket/profile bucket coverage、final_answer_changed_count、final_hit_rate_delta、ROI/profit delta、Brier/log-loss/ECE no-harm、failed_fold_count、active competition/season-cutoff/rolling fold counts
新增 proposal payload：proposed_production_enabled、holdout_candidate_enabled、profile_key、segment_mode、target competitions/markets/outcomes、odds/probability/blend constraints、evidence_json、source_report_keys、rollback_conditions；notes 明确这是 governed proposal artifact，不改变 default runtime，不向普通用户暴露内部策略标签，不引入自动下注/支付/钱包/保证结果行为
新增 deterministic tests 覆盖：全部 checks 通过时 status=runtime_profile_proposal_ready；ROI 目标失败时降级为 holdout_only；shadow profile 被 blocked；profile/candidate odds mismatch 被 blocked；CLI options/loaders/main 写 report 与 profile set
使用 V3.1-309 真实 accepted candidate 生成 proposal：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_fold_aware_production_proposal_v1.json；report_key=historical_probability_calibration_profile_production_proposal:832c7c149c76bd；status=runtime_profile_proposal_ready；runtime_profile_proposal_allowed=true；holdout_candidate_allowed=true；proposal_count=1；failed_checks=[]
staged proposal profile set 写入 configs/recommendations/profiles/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_fold_aware_proposal_profile_set_v1.json；包含 candidate_probability_calibration_profile:e753919b27cb3e62，但 production_recommendation_changed=false，仍不是 default runtime profile
使用已有 benchmark quality gate 对该 rolling admission evidence 做 bootstrap gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_fold_aware_benchmark_gate_v1.json；status=passed；passed=true；failed_checks=[]
阶段性结论：概率校准 profile 已从“通过 rolling admission 的候选”进入“可审计生产候选提案”状态，但还没有运行 runtime shadow replay，也没有写默认 profile。下一阶段应做 runtime shadow replay/smoke，证明 staged profile 不改变公开响应结构、不暴露内部策略、不绕过显式 promotion 审批
README 更新 production proposal、profile set、benchmark gate artifact 与 no-default-change 结论；该能力属于“calibration profile governance / production proposal prerequisite / benchmark gate linkage”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-311 当前落地能力：

```text
按 V3.1-310 结论为 proposal-ready probability calibration profile 增加 runtime shadow replay/smoke；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不写 default runtime profile
新增 nutmeg-recommendation-historical-probability-calibration-profile-runtime-replay；输入为 historical slices/suite manifest 与 staged profile set；通过 --enable-shadow-replay 显式开启；默认 disabled
runtime replay loader 支持 proposal report 的 proposal_profile_set_json、直接 profile set JSON、以及单个 CandidateProbabilityCalibrationProfile；会选择 profile_key，限制 max_selected_profile_count，要求 holdout/runtime proposal flags、active profile、no production change、no public response change、no internal strategy label exposure
runtime replay 做法：对原始 historical slices 跑 baseline suite；对临时校准副本跑 candidate suite；临时副本由 apply_candidate_probability_calibration_profile 生成，不写回原始数据、不改变默认推荐路径；报告 adjusted_fixture_count、adjusted_candidate_count、changed_final_answer_count、final hit/ROI/P&L deltas、Brier/log-loss/ECE deltas、harm counts 与 governance flags
新增 deterministic tests 覆盖：shadow replay 开启且阈值通过时 runtime_replay_passed；未开启时 disabled；shadow profile 被 selected_profile_active 阻断；loader 能读取 proposal_profile_set_json；CLI options/main 能写 runtime replay report
用真实 V3.1-309 proposal-ready profile 跑 no-ESP expanded A-league rolling-window suite runtime replay：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_fold_aware_runtime_replay_v1.json；report_key=historical_probability_calibration_profile_runtime_replay:3183ab5bca5f7edf
真实 replay 结果：status=shadow_replay_failed；runtime_replay_allowed=false；holdout_replay_allowed=false；selected_profile_key=candidate_probability_calibration_profile:e753919b27cb3e62；adjusted_fixture_count=1126；adjusted_candidate_count=3378；final_answer_count=180；changed_final_answer_count=4；final_answer_hit_delta_count=1；final_answer_hit_rate_delta=0.005555555555555536；roi_delta=0.018993574297188755；profit_loss_delta=9.4588；harm_count_vs_baseline=0；final_hit_harm_count_vs_baseline=0；profit_loss_harm_count_vs_baseline=0
governance smoke 通过：production_recommendation_changed=false；public_response_changed=false；internal_strategy_label_exposed=false
严格 no-harm probability quality 未通过：brier_score_delta=0.004950884450535403；log_loss_delta=0.011755583705955419；mean_calibration_error_delta=0.005865258907091386；failed_checks=brier_score_delta、log_loss_delta、mean_calibration_error_delta
阶段性结论：这个 profile 在最终答案命中、ROI、P&L 上有正向 movement，而且不会改变公开响应或暴露内部策略，但 runtime shadow replay 暴露概率质量回撤，因此仍不得进入 default/runtime。下一阶段应基于 replay 失败原因继续做 profile/refinement，不应放宽 no-harm 概率质量门槛
README 更新 runtime replay 设计、真实 report、正向 final-answer 指标、概率质量阻断与 no-runtime-change 结论；该能力属于“runtime shadow replay / governed activation blocker / probability no-harm validation”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-312 当前落地能力：

```text
按 V3.1-311 结论为 probability calibration runtime replay 增加回撤定位诊断；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不写 default runtime profile，也不放宽 probability no-harm 阈值
新增 nutmeg-recommendation-historical-probability-calibration-profile-runtime-diagnostics；输入为 historical slices/suite manifest 与 staged profile set；输出按 overall、competition、season、competition_season、slice 分解的 runtime replay probability-quality regression report
diagnostics 使用与 runtime replay 相同的临时校准方式：原始 slices 跑 baseline suite，临时校准 slices 跑 candidate suite；比较两套 suite 的 candidate result，按 final_hit_sample_size 对 Brier/log-loss/ECE 做加权，避免用未加权 slice 均值误判整体质量
report 字段覆盖 selected_profile_key、baseline/candidate suite key、slice/fixture/prediction count、adjusted_fixture_count、adjusted_candidate_count、skipped_group_count、changed_final_answer_count、final_answer_hit_delta、ROI/P&L delta、Brier/log-loss/ECE delta、quality_regression_score、top_regression_slices、top_regression_groups
新增 deterministic tests 覆盖：诊断能识别 calibrated replay 输入、按 competition/season/competition_season 聚合回撤、按样本数加权概率质量指标、CLI options/main 能写 report
用真实 V3.1-309 proposal-ready profile 跑 no-ESP expanded A-league rolling-window suite runtime diagnostics：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_fold_aware_runtime_diagnostics_v1.json；report_key=historical_probability_calibration_profile_runtime_diagnostics:45a42c3e1d699d0e
真实 diagnostics 覆盖 slice_count=180、fixture_count=2160、prediction_count=6480、adjusted_fixture_count=1126、adjusted_candidate_count=3378、skipped_group_count=1034；overall 与 runtime replay 一致：final_answer_count=180、changed_final_answer_count=4、final_answer_hit_delta_count=1、roi_delta=0.018993574297188755、profit_loss_delta=9.4588、brier_score_delta=0.004950884450535403、log_loss_delta=0.011755583705955419、mean_calibration_error_delta=0.005865258907091386
最高回撤 group 集中在 ENG_CHAMPIONSHIP|2021-2022 与 ENG_CHAMPIONSHIP|2020-2021；competition-level ENG_CHAMPIONSHIP quality_regression_score=0.1352650488482784，是主要拖累源；season-level 2021-2022 与 2020-2021 也显著高于其他窗口
最大回撤 slice=football_data_co_uk_eng_championship_2021_2022_market_features_v1_rolling_window_v1_001；它同时贡献 final_answer_hit_delta_count=1、profit_loss_delta=9.4588、roi_delta=4.7294，并带来 brier_score_delta=0.6214335617424513、log_loss_delta=1.4546743657814685、mean_calibration_error_delta=0.6214534905320256；这说明当前 profile 混合了局部 profitable movement 与不可接受概率质量伤害
阶段性结论：profile 不是整体失效，而是早期 ENG_CHAMPIONSHIP rolling windows 的局部校准风险过高；下一阶段应做 scoped guard/refinement，例如拆分 early ENG_CHAMPIONSHIP window、降低或屏蔽该窗口 profile 影响，随后重新跑 runtime replay，仍不得放宽 no-harm probability-quality 门槛
README 更新 runtime diagnostics 设计、真实 report、top regression group/slice 与 no-runtime-change 结论；该能力属于“runtime replay failure localization / probability calibration blocker diagnosis / governed activation evidence”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-313 当前落地能力：

```text
按 V3.1-312 结论实现 scoped runtime refinement guard；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不写 default runtime profile，也不放宽 probability no-harm 阈值
CandidateProbabilityCalibrationProfile 新增 season/competition-season guard 字段：target_season_ids、excluded_season_ids、min_competition_season_index、max_competition_season_index、min_competition_season_index_by_competition_id、max_competition_season_index_by_competition_id
candidate_probability_calibration 在应用 profile 前会检查 candidate metadata 中的 season_id/season/source_season 与 competition_season_index；如果 profile 要求 season index 但 candidate 缺少上下文，则保守跳过，不进行校准
runtime replay 的 _calibrated_replay_input 现在会为临时 calibration candidates 注入 historical slice season 与 build_historical_competition_season_index_by_slice_id 计算出的 competition_season_index；这只影响 shadow/replay 临时副本，不改变原始历史数据或默认 runtime 路径
新增 nutmeg-recommendation-historical-probability-calibration-profile-runtime-refinement；输入 staged profile set，输出 guarded runtime_refinement_candidate profile set；默认不保留 runtime_profile_proposal_allowed，避免 refinement artifact 直接被误当作 production proposal
新增 deterministic tests 覆盖：candidate probability calibration 会跳过 competition-season index 不达标的早期候选；runtime replay 会把 season context 传给临时校准；runtime refinement CLI 能生成 guarded profile set，runtime loader 能读取 refined_profile_set_json
真实 refinement 使用 ENG_CHAMPIONSHIP:3 作为 min_competition_season_index_by_competition_id：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_eng_championship_index3_runtime_refinement_v1.json；report_key=historical_probability_calibration_profile_runtime_refinement:de1caa5bca8de7e3；refined_profile_key=candidate_probability_calibration_profile:e753919b27cb3e62:runtime_refinement:scope_refinement:e3bd8b247e6ca0bb
写出 guarded profile set：configs/recommendations/profiles/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_eng_championship_index3_refined_profile_set_v1.json；status=runtime_refinement_candidate；runtime_profile_proposal_allowed=false；holdout_candidate_allowed=true；production_recommendation_changed=false
用 guarded profile 重跑 runtime replay：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_eng_championship_index3_runtime_replay_v1.json；report_key=historical_probability_calibration_profile_runtime_replay:d4119db9785f7f04；status=shadow_replay_failed；adjusted_fixture_count=1012；adjusted_candidate_count=3036；changed_final_answer_count=2
guarded replay 结果是负证据：final_answer_hit_delta_count=0、final_answer_hit_rate_delta=0.0、roi_delta=0.0、profit_loss_delta=0.0；概率质量几乎中性但仍未通过 strict no-harm：brier_score_delta=0.00002659223155954127、log_loss_delta=0.00007617998045006402、mean_calibration_error_delta=-0.000005755032079612921
用 guarded profile 跑 runtime diagnostics：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_eng_championship_index3_runtime_diagnostics_v1.json；report_key=historical_probability_calibration_profile_runtime_diagnostics:009cedc78fa30059；overall quality_regression_score=0.00003708003601476939；top regression 从早期 ENG_CHAMPIONSHIP 转为 ITA_SERIE_B/FRA_LIGUE_2 的零收益小扰动
阶段性结论：简单屏蔽早期 ENG_CHAMPIONSHIP 能移除主要伤害，但也移除了唯一 final-answer/P&L 收益，而且剩余无收益微小扰动仍不能通过 no-harm。该 refinement 不可晋级；下一阶段应把搜索目标改成 movement-aware refinement，只保留能产生最终答案 movement 且通过 probability no-harm 的候选，而不是继续手工排除联赛/赛季
README 更新 season guard、runtime refinement CLI、真实 guarded profile/replay/diagnostics artifacts 与 negative-evidence 结论；该能力属于“scoped calibration guard / runtime refinement evidence / no-activation negative evidence”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-314 当前落地能力：

```text
按 V3.1-313 结论实现 movement-aware runtime refinement search；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不写 default runtime profile，也不放宽 probability no-harm 阈值
新增 nutmeg-recommendation-historical-probability-calibration-profile-runtime-refinement-search；输入 historical suite/slices、staged profile set、可选 runtime diagnostics report；输出 movement-aware refinement search report
search 可以从 runtime diagnostics top_regression_groups 中读取 competition_season 回撤 group，结合 historical slices 的 build_historical_competition_season_index_by_slice_id 自动生成 min_competition_season_index_by_competition_id guard 候选；也支持手工传入 --min-competition-season-index-by-competition-candidate
每个候选都会生成独立 refined profile key，并用 runtime replay 同口径验证；接受条件同时要求 adjusted fixture/candidate、有 final-answer movement、final answer hit/ROI/P&L 不回撤、Brier/log-loss/ECE no-harm、harm counts 不超限、candidate_roi 不低于阈值
新增 deterministic tests 覆盖：diagnostics report 可生成 ENG_CHAMPIONSHIP:2/3 guard 候选；fake replay 中 movement + no-harm candidate 被 accepted，无 movement 或 quality regression candidate 被 rejected；CLI options/main 能写 search report
用真实 no-ESP proposal profile + V3.1-312 diagnostics 跑 movement-aware refinement search：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_blend010_movement_aware_refinement_search_v1.json；report_key=historical_probability_calibration_profile_runtime_refinement_search:195c37602177695c；candidate_count=2；accepted_count=0；rejected_count=2
候选 diagnostic_min_index:ENG_CHAMPIONSHIP:2 保留了原始收益：changed_final_answer_count=3、final_answer_hit_delta_count=1、final_answer_hit_rate_delta=0.005555555555555536、roi_delta=0.018993574297188755、profit_loss_delta=9.4588；但仍因 probability quality 回撤被拒绝：brier_score_delta=0.003488830396265241、log_loss_delta=0.008177696224171305、mean_calibration_error_delta=0.0034554702712749075
候选 diagnostic_min_index:ENG_CHAMPIONSHIP:3 基本消除主要质量伤害但收益归零：changed_final_answer_count=2、final_answer_hit_delta_count=0、roi_delta=0.0、profit_loss_delta=0.0；仍因 brier_score_delta=0.00002659223155954127 与 log_loss_delta=0.00007617998045006402 被拒绝
阶段性结论：自动 movement-aware search 确认当前 scope guard 空间里没有可晋级候选。ENG_CHAMPIONSHIP:2 是“保留收益但质量不达标”的最有信息量形状；ENG_CHAMPIONSHIP:3 是“质量近中性但收益消失”的对照。下一阶段应优化概率调整本身，例如对 movement-preserving shape 做 blend/bucket-level damping search，而不是继续扩大手工排除范围
README 更新 movement-aware refinement search 设计、真实 search report、两个候选的拒绝原因与 no-activation 结论；该能力属于“movement-aware calibration refinement search / governed replay objective / no-activation evidence”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-315 当前落地能力：

```text
按 V3.1-314 结论实现 movement-preserving blend damping search；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不写 default runtime profile，也不放宽 probability no-harm 阈值
新增 nutmeg-recommendation-historical-probability-calibration-profile-runtime-damping-search；输入 historical suite/slices、staged profile set、目标 profile key、blend weight 列表、可选 competition-season guard；输出 damping search report
search 会为每个候选生成独立 refined profile key，并保留 runtime gating flags；每个候选都经过 runtime replay 同口径验证，接受条件同时要求 adjusted fixture/candidate、有 final-answer movement、final answer hit/ROI/P&L 不回撤、Brier/log-loss/ECE no-harm、harm counts 不超限、candidate_roi 不低于阈值
新增 deterministic tests 覆盖：candidate specs 按 blend 权重和 guard 生成；fake replay 中 no-harm + movement candidate 被 accepted，quality regression candidate 被 rejected；CLI options/main 能写 search report
用真实 no-ESP proposal profile + ENG_CHAMPIONSHIP:2 guard 跑 movement-preserving damping search：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_eng_championship_index2_blend_damping_search_v1.json；report_key=historical_probability_calibration_profile_runtime_damping_search:833bbd3eb9c1b23a；candidate_count=3；accepted_count=0；rejected_count=3
blend 0.02 保留最终答案收益：changed_final_answer_count=1、final_answer_hit_delta_count=1、final_answer_hit_rate_delta=0.005555555555555536、roi_delta=0.018993574297188755、profit_loss_delta=9.4588；但因 probability quality 回撤被拒绝：brier_score_delta=0.0034510020176897194、log_loss_delta=0.008072511550960004、mean_calibration_error_delta=0.0034477514200900172
blend 0.05 同样保留最终答案收益：changed_final_answer_count=1、final_answer_hit_delta_count=1、final_answer_hit_rate_delta=0.005555555555555536、roi_delta=0.018993574297188755、profit_loss_delta=9.4588；但仍因 probability quality 回撤被拒绝：brier_score_delta=0.0034651736471845163、log_loss_delta=0.008111911415286999、mean_calibration_error_delta=0.0034506428872355666
blend 0.08 降低 probability quality 回撤：brier_score_delta=0.000952731361585718、log_loss_delta=0.002227779715672673、mean_calibration_error_delta=0.0014482631712380845；但最终答案收益归零：final_answer_hit_delta_count=0、roi_delta=0.0、profit_loss_delta=0.0，因此也被拒绝
阶段性结论：简单全局 blend damping 不能同时满足 final-answer 收益和 probability no-harm。V3.1-314/315 已把问题从“找不找得到 scope guard”收窄为“如何对产生收益的单个 final-answer movement 做选择感知或 bucket-level 概率修复”；下一阶段应转向 bucket-level / selection-aware calibration，而不是继续扩大手工联赛排除或重复调全局 blend
README 更新 damping search CLI、真实 search report、三个候选的拒绝原因与 no-activation 结论；该能力属于“movement-preserving blend damping search / governed replay objective / no-activation evidence”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-316 当前落地能力：

```text
按 V3.1-315 结论实现 selection-aware / bucket-level calibration search；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径、不写 default runtime profile，也不放宽 probability no-harm 阈值
新增 nutmeg-recommendation-historical-probability-calibration-profile-runtime-bucket-search；输入 historical suite/slices、staged profile set、runtime diagnostics report、目标 profile key、blend weight 列表、bucket scope modes；输出 bucket search report
search 从 runtime diagnostics 中只选择已有 final-answer movement、final_answer_hit_delta_count 达标、profit_loss_delta 达标的 competition-season group，再生成 exact-season 与 single-bucket 候选；每个候选都生成独立 refined profile key，并保留 runtime gating flags
每个候选都经过 runtime replay 同口径验证，接受条件同时要求 adjusted fixture/candidate、有 final-answer movement、final answer hit/ROI/P&L 不回撤、Brier/log-loss/ECE no-harm、harm counts 不超限、candidate_roi 不低于阈值
新增 deterministic tests 覆盖：diagnostics 只生成有收益 group 的 exact-season/single-bucket specs；fake replay 中 selection bucket candidate 被 accepted，无 movement 或 quality regression candidate 被 rejected；CLI options/main 能写 search report
用真实 no-ESP proposal profile + V3.1-312 diagnostics 跑 selection-aware bucket search：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_market_odds_band_draw_225_345_selection_bucket_search_v1.json；report_key=historical_probability_calibration_profile_runtime_bucket_search:08b8e41ae0a557d6；candidate_count=6；accepted_count=0；rejected_count=6
single_bucket ENG_CHAMPIONSHIP:1x2:draw:0.3000-0.4000 是最有信息量候选；blend 0.05 调整 adjusted_fixture_count=43、adjusted_candidate_count=129，并保留最终答案收益：changed_final_answer_count=1、final_answer_hit_delta_count=1、final_answer_hit_rate_delta=0.005555555555555536、roi_delta=0.018993574297188755、profit_loss_delta=9.4588；但仍因 probability quality 回撤被拒绝：brier_score_delta=0.003451320041885586、log_loss_delta=0.008071977702725608、mean_calibration_error_delta=0.003453172762957424
single_bucket ENG_CHAMPIONSHIP:1x2:draw:0.3000-0.4000 的 blend 0.10 同样保留收益，但 quality 回撤略大：brier_score_delta=0.0034610415595128785、log_loss_delta=0.008097618510016003、mean_calibration_error_delta=0.0034604872452362323，因此拒绝
exact-season ENG_CHAMPIONSHIP 2021-2022 candidates 调整 adjusted_fixture_count=59、adjusted_candidate_count=177，也保留同一 final-answer/P&L 收益，但 Brier/log-loss/ECE 仍回撤，因此拒绝
single_bucket ENG_CHAMPIONSHIP:1x2:draw:0.2000-0.3000 调整 adjusted_fixture_count=16、adjusted_candidate_count=48，probability quality 完全中性：brier_score_delta=0.0、log_loss_delta=0.0、mean_calibration_error_delta=0.0；但 changed_final_answer_count=0、final_answer_hit_delta_count=0、roi_delta=0.0、profit_loss_delta=0.0，因此因 changed_final_answer_count:below_threshold 被拒绝
阶段性结论：收益来自 selection/value 侧的最终答案切换，而不是干净的 probability calibration improvement。进一步从 season 收窄到 single bucket 没有修复 Brier/log-loss/ECE；下一阶段应把 probability calibration 和 final-answer arbitration 解耦，测试 selection-side quality/value adjustment，使其复现收益而不重写 probability grid
README 更新 bucket search CLI、真实 search report、六个候选的拒绝原因与 no-activation 结论；该能力属于“selection-aware bucket calibration search / governed replay objective / no-activation evidence”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-317 当前落地能力：

```text
按 V3.1-316 结论把 probability calibration 和 final-answer arbitration 解耦；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不重写 probability grid，也不放宽 no-harm 阈值
HistoricalRecommendationBacktestOptions 新增 final_answer_selection_value_signal；该信号只在 final-answer sorting layer 对匹配 competition/outcome/odds/probability/model-edge/scored-candidate range 的 option 做有界 boost/penalty，不改 model probability、calibrated probability 或 score grid
新增 nutmeg-recommendation-final-answer-selection-value-signal-search；输入 historical suite/slices 与 V3.1-316 bucket search report；从有 final-answer/P&L 收益的 bucket candidate 读取 bucket_key，把 market-implied probability bucket 转成 decimal odds range，并生成 selection-side value signal candidates
新增 deterministic tests 覆盖：bucket search report 可生成 ENG_CHAMPIONSHIP draw 0.3000-0.4000 odds-band specs；fake historical suite 中 no-harm value candidate 被 accepted，无 movement 或 quality regression candidate 被 rejected；CLI options/main 能写 search report
真实低强度 search：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_search_v1.json；report_key=historical_final_answer_selection_value_signal_search:6d4332b922cc2c08；candidate_count=3；accepted_count=0；rejected_count=3
低强度 strengths 0.02/0.04/0.08 全部未触达最终答案：affected_leg_count=0、changed_final_answer_count=0、final_answer_hit_delta_count=0、roi_delta=0.0、profit_loss_delta=0.0、brier/log-loss/ECE delta=0.0；阶段性结论是弱 boost 无效，但概率质量保持中性
真实强度 search：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_search_stronger_v1.json；report_key=historical_final_answer_selection_value_signal_search:17bba0f6b95ce867；candidate_count=3；accepted_count=0；rejected_count=3
strength 0.16 触发 movement 但综合失败：affected_leg_count=2、changed_final_answer_count=2、final_answer_hit_delta_count=1，但 roi_delta=-0.0038829577132057647、profit_loss_delta=-2.5412，并且 brier_score_delta=0.002678694407554888、log_loss_delta=0.0063182073964991314、mean_calibration_error_delta=0.0041466659471751655、profit_loss_harm_count_vs_baseline=1，因此拒绝
strength 0.32 是最有信息量候选：affected_leg_count=10、changed_final_answer_count=6、final_answer_hit_delta_count=1、final_answer_hit_rate_delta=0.005555555555555536、roi_delta=0.06038927846216326、profit_loss_delta=30.565199999999997、candidate_roi=0.013648314606741567；但仍因 brier_score_delta=0.0027818260224740377、log_loss_delta=0.006527136918490939、mean_calibration_error_delta=0.004262916725076948、profit_loss_harm_count_vs_baseline=1 被拒绝
strength 0.64 产生最大结算收益：affected_leg_count=16、changed_final_answer_count=11、final_answer_hit_delta_count=3、final_answer_hit_rate_delta=0.016666666666666607、roi_delta=0.10323218763164546、profit_loss_delta=55.589980000000004、candidate_roi=0.05649122377622378；但因 brier/log-loss/ECE 回撤、final_hit_harm_count_vs_baseline=1、profit_loss_harm_count_vs_baseline=3 被拒绝
阶段性结论：selection-side value signal 是真实方向，能复现并放大部分收益，而且不重写概率；但单一全局 boost 太钝，会带来 selected-answer probability quality 回撤和局部 harm。下一阶段应进入 harm-aware candidate-pool/scenario-level selector，只保留盈利 movement、屏蔽 harmful movement，而不是继续加大 boost
README 更新 selection-value signal 机制、低强度与高强度真实 search report、候选拒绝原因与 no-activation 结论；该能力属于“selection-side value signal search / probability-grid-unchanged arbitration experiment / no-activation evidence”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-318 当前落地能力：

```text
按 V3.1-317 结论实现 selection-value signal 的 scenario-level guard；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不重写 probability grid，也不放宽 no-harm 阈值
HistoricalRecommendationBacktestOptions 新增 final_answer_selection_value_signal_max_hit_probability_deficit、final_answer_selection_value_signal_min_option_roi、final_answer_selection_value_signal_max_option_risk_score；这些 guard 只决定 selection-value boost 是否在某个最终答案 option 上生效
final-answer sorting 现在使用不含 selection-value boost 的 non-lane reference option 计算 hit-probability deficit；当 boosted option 相对 reference 的命中概率亏损超过阈值、option ROI 低于下限、或 option risk 高于上限时，value boost 被阻断
summary/suite summary 增加 final_answer_selection_value_signal_guard_blocked_option_count 与 aggregate blocked-option count，便于后续判断 guard 是降低风险还是只是不动答案
nutmeg-recommendation-final-answer-selection-value-signal-search 新增 max_hit_probability_deficit/min_option_roi/max_option_risk_score grid 参数，并把 guard_blocked_option_count 写入 candidate report
单元测试更新：bucket report spec generation 覆盖 hit-probability-deficit guard 维度；CLI options 覆盖 guard grid 参数；fake no-harm candidate report 覆盖 guard_blocked_option_count 字段
真实 16-candidate guard grid 曾启动但超过 25 分钟仍未完成，因此主动中止；阶段性工程结论是当前 full-suite per-candidate replay 成本太高，不适合直接扩大 guard brute-force 网格
真实 focused smoke：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_guard_smoke_v1.json；report_key=historical_final_answer_selection_value_signal_search:e8c82cc325af9e8f；candidate_count=1；accepted_count=0；rejected_count=1
smoke spec 使用 strength=0.32、max_hit_probability_deficit=0.02、ENG_CHAMPIONSHIP draw 0.3000-0.4000 market-implied probability bucket；guard_blocked_option_count=3295、affected_leg_count=6、changed_final_answer_count=4
相对 V3.1-317 未守门 strength 0.32 的 affected_leg_count=10、changed_final_answer_count=6、profit_loss_delta=30.565199999999997，guard 后 exposure 更小且仍保留收益：final_answer_hit_delta_count=1、final_answer_hit_rate_delta=0.005555555555555536、roi_delta=0.03675667266768222、profit_loss_delta=18.065199999999997
该 candidate 仍被拒绝：brier_score_delta=0.0023588657722446726、log_loss_delta=0.005673528032113406、mean_calibration_error_delta=0.0037975410042941915、profit_loss_harm_count_vs_baseline=1；final_hit_harm_count_vs_baseline 已降为 0
阶段性结论：scenario-level guard 是对 blunt boost 的实质改进，能减少 exposure 并清掉 final-hit harm，但仍不足以通过 strict no-harm。下一阶段不应继续扩大 brute-force guard grid，而应先实现 replay reuse / movement-level diagnostic cache，用更低成本定位具体 harmful movement
README 更新 guard 机制、真实 smoke report、被中止的大网格成本问题与 no-activation 结论；该能力属于“scenario-level selection-value guard / guarded arbitration experiment / replay-cost bottleneck evidence”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-319 当前落地能力：

```text
按 V3.1-318 结论实现 movement-level diagnostic cache；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不扩大 brute-force guard grid，也不放宽 no-harm 阈值
nutmeg-recommendation-final-answer-selection-value-signal-search 新增 include_movement_diagnostics 与 movement_diagnostics_limit；每个 candidate 默认输出 movement_count、positive_movement_count、harmful_movement_count、probability_quality_harm_movement_count，打开 diagnostics 后输出 bounded movement records
movement record 记录 baseline/candidate final-answer signature、scenario、selected outcomes、settlement deltas、Brier/log-loss/ECE deltas、movement_class，并附带 candidate selected leg features：probability、decimal_odds、market_probability、model_edge、score、data_quality、calibration、model_confidence、odds_stability、volatility
单元测试更新：fake no-harm value candidate 现在验证 movement_count、positive/harm/quality-harm counts、movement_diagnostics_json records；CLI options/main 覆盖 include_movement_diagnostics 与 movement_diagnostics_limit
真实 diagnostics replay：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_movement_diagnostics_v1.json；report_key=historical_final_answer_selection_value_signal_search:a7906f69e12b10aa；candidate_count=1；accepted_count=0；rejected_count=1
该 replay 复用 V3.1-318 guarded smoke spec：strength=0.32、max_hit_probability_deficit=0.02、ENG_CHAMPIONSHIP draw 0.3000-0.4000；aggregate 仍为 rejected，原因仍是 Brier/log-loss/ECE 回撤与 profit_loss_harm_count_vs_baseline=1
movement cache 把问题具体化：movement_count=4、positive_movement_count=3、harmful_movement_count=1、probability_quality_harm_movement_count=3、clean_positive_movement_count=1；这说明收益方向存在，但大部分 movement 仍伴随概率质量回撤
唯一 harmful movement 来自 football_data_co_uk_eng_championship_2020_2021_market_features_v1_rolling_window_v1_001：candidate answer 切到 2x1:multiple#variant1，profit_loss_delta=-6.0、brier_score_delta=0.2953839418881771、log_loss_delta=0.7087932519662377
harmful movement 的 candidate legs 全部为 negative model_edge；两个 draw leg 概率约 0.2762/0.2896、decimal_odds=3.43/3.27、score 约 0.50、data_quality=72.0、model_confidence=0.66；其中一个 home_win leg volatility_penalty=0.14017549150489517
阶段性结论：现在不需要再猜“为什么 guard 仍失败”。失败集中为少数 movement，且可通过 leg-feature diagnostics 定位。下一阶段应做 movement-conditioned guard search / replay reuse，让候选先基于 cached movement 特征缩小范围，再触发昂贵 full-suite replay
README 更新 movement diagnostics cache、真实 report、harmful movement 特征和下一步判断；该能力属于“movement-level diagnostic cache / harmful movement isolation / replay-cost reduction evidence”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-320 当前落地能力：

```text
按 V3.1-319 结论实现 movement-conditioned selection-value candidate spec generation；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，也不直接激活任何 shadow candidate
nutmeg-recommendation-final-answer-selection-value-signal-search 新增 movement_diagnostics_report_path / --movement-diagnostics-report、movement_score_band / --movement-score-band、max_movement_conditioned_specs / --max-movement-conditioned-specs
当提供 movement diagnostics report 时，search 会优先从 clean_positive movement records 中提取匹配 source spec 的 selected leg，并围绕该 leg score 生成窄 score band spec；harmful、positive_with_probability_harm 与不匹配 source spec 的腿不会生成候选
单元测试新增 movement-conditioned spec generation：fake diagnostics report 中 harmful movement 被忽略，clean_positive draw leg 生成 score_min/score_max 窄带；CLI options 覆盖 movement diagnostics report 与 score band 参数
真实 movement-conditioned smoke：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_movement_conditioned_smoke_v1.json；report_key=historical_final_answer_selection_value_signal_search:6aef56ade4f16770；candidate_count=1；accepted_count=1；rejected_count=0
真实 spec 来自 V3.1-319 clean_positive movement 的 draw leg：strength=0.32、max_hit_probability_deficit=0.02、score_min=0.5034391225480457、score_max=0.5064391225480456、ENG_CHAMPIONSHIP draw odds bucket 保持不变
该 candidate 只改变 1 个最终答案：movement_count=1、positive_movement_count=1、harmful_movement_count=0、probability_quality_harm_movement_count=0、clean_positive_movement_count=1；命中的 movement 为 football_data_co_uk_eng_championship_2022_2023_market_features_v1_rolling_window_v1_006
aggregate no-harm 全部通过：final_answer_hit_delta_count=0、roi_delta=0.008980646395104222、profit_loss_delta=4.245799999999999、brier_score_delta=-0.0002751958116523068、log_loss_delta=-0.000555299286751243、mean_calibration_error_delta=-0.00030225164203084853、final_hit_harm_count_vs_baseline=0、profit_loss_harm_count_vs_baseline=0
阶段性结论：这是 selection-value 方向第一次在 expanded A-league no-ESP rolling-window suite 上产出 accepted shadow candidate。它不是 broad bucket，也不是手工 boost，而是 movement-conditioned narrow score band；下一阶段应做 rolling/admission validation 与 production proposal governance，而不是直接写入默认推荐路径
README 更新 movement-conditioned search、真实 accepted smoke report、no-harm 指标与下一步判断；该能力属于“movement-conditioned value guard / accepted shadow evidence / governed promotion candidate”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-321 当前落地能力：

```text
按 V3.1-320 结论实现 selection-value signal 的 governed production proposal gate；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，也不直接激活 shadow candidate
新增 nutmeg-recommendation-final-answer-selection-value-signal-production-proposal；输入 accepted search report，输出 production proposal report 与 proposal profile set
proposal gate 校验 source accepted、candidate accepted、无 rejection reasons、probability_grid_unchanged、movement-conditioned clean provenance、final-answer coverage、affected/changing/positive movement count、harmful movement=0、probability-quality harm=0、final-hit/profit-loss local harm=0、ROI/profit-loss delta、Brier/log-loss/ECE no-regression，以及 candidate ROI floor
blocked 状态不会输出可晋级 rule；holdout_only 仅保留 holdout candidate；runtime_profile_proposal_ready 才允许 proposed_production_enabled=true；profile artifact 同时保留 final_answer_selection_value_signal_rules 与通用 rules 入口
新增 deterministic tests 覆盖：ready、coverage 失败转 holdout_only、harmful movement 阻断、rejected source 阻断、CLI options/loader/main 输出 proposal 与 profile artifact
真实 proposal report：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_production_proposal_v1.json；report_key=historical_final_answer_selection_value_signal_production_proposal:ac7ab4421c1e1a60；status=runtime_profile_proposal_ready；proposal_count=1
真实 proposal profile set：configs/recommendations/profiles/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_proposal_profile_set_v1.json；runtime_profile_proposal_allowed=true；holdout_candidate_allowed=true；default_recommendation_path_changed=false；public_default_activation=false
该 proposal 继承 V3.1-320 accepted smoke 指标：final_answer_count=180、changed_final_answer_count=1、movement_count=1、positive_movement_count=1、harmful_movement_count=0、probability_quality_harm_movement_count=0、final_answer_hit_delta_count=0、roi_delta=0.008980646395104222、profit_loss_delta=4.245799999999999、Brier/log-loss/ECE 均改善
阶段性结论：selection-value candidate 已从 accepted shadow evidence 晋级为 governed proposal-ready artifact，但仍不是默认 runtime activation。下一阶段应做 runtime shadow replay 或 rolling/admission validation，确认 proposal artifact 在运行时风格加载下仍无回撤
README 更新 production proposal gate、真实 artifact 路径、report_key、回滚条件与 no-default-change 结论；该能力属于“core final-answer arbitration governance / proposal-ready artifact / no-production-change evidence”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-322 当前落地能力：

```text
按 V3.1-321 结论实现 selection-value signal runtime replay / shadow smoke；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只验证 proposal profile artifact 能否被运行时风格 loader 复现
新增 nutmeg-recommendation-final-answer-selection-value-signal-runtime-replay；支持直接读取 proposal profile set、production proposal report 的 proposal_profile_set_json，或通用 rules fallback
runtime rule loader 读取 final_answer_selection_value_signal_rules，并映射到 HistoricalRecommendationBacktestOptions 的 final_answer_selection_value_signal、strength、probability/odds/score band、competition/outcome、hit-probability-deficit、option ROI、risk-score guard 字段
runtime replay checks 覆盖 shadow flag、selected rule count、profile runtime allowed、rule holdout/proposed production enabled、no production change、probability_grid_unchanged、movement_conditioned、final-answer coverage、changed answer、affected leg、positive/harmful/probability-quality-harm movement、final hit/ROI/P&L/Brier/log-loss/ECE no-harm、final-hit/profit-loss local harm 与 public response unchanged
新增 deterministic tests 覆盖：runtime thresholds passed 时 options 正确映射；未开启 flag 时 disabled；harmful movement 被阻断；loader 能读 production proposal report；CLI options/main 输出 replay report
真实 runtime replay report：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_runtime_replay_v1.json；report_key=historical_final_answer_selection_value_signal_runtime_replay:d7a21b20391cf3c6；status=runtime_replay_passed；runtime_replay_allowed=true；holdout_replay_allowed=true
真实 replay 使用 suite：configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_no_esp_segunda_suite_v1.json；final_answer_count=180；changed_final_answer_count=1；affected_leg_count=1；movement_count=1；positive_movement_count=1；harmful_movement_count=0；probability_quality_harm_movement_count=0
aggregate no-harm 通过：final_answer_hit_delta_count=0、roi_delta=0.008980646395104222、profit_loss_delta=4.245799999999999、brier_score_delta=-0.0002751958116523068、log_loss_delta=-0.000555299286751243、mean_calibration_error_delta=-0.00030225164203084853、final_hit_harm_count_vs_baseline=0、profit_loss_harm_count_vs_baseline=0
阶段性结论：proposal artifact 在运行时风格加载路径下复现了 search/proposal 的 no-harm 证据，说明这不是只在 search 内成立的离线候选；但 candidate_roi=-0.037760317460317466 仍为负，下一阶段应做 rolling/admission validation 或更严格 ROI-floor holdout 决策，而不是直接进入默认 activation
README 更新 runtime replay 命令链、真实 report、report_key、核心指标与 no-default-change 结论；该能力属于“core final-answer arbitration governance / runtime-style replay evidence / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-323 当前落地能力：

```text
按 V3.1-322 结论实现 selection-value runtime admission / strict ROI-floor holdout gate；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不重新跑 solver，只消费已生成 runtime replay evidence 做最终治理判断
新增 nutmeg-recommendation-final-answer-selection-value-signal-runtime-admission；输入 selection-value runtime replay report，输出 accepted / holdout_only / rejected 三态 admission report
admission gate 校验 runtime_replay_allowed、holdout_replay_allowed、runtime_replay_passed_status、rule_count、selected_rule_count、final_answer_count、changed_final_answer_count、affected_leg_count、positive movement、harmful movement=0、probability-quality harm=0、final hit/ROI/P&L no-regression、candidate ROI floor、Brier/log-loss/ECE no-regression、final-hit/profit-loss local harm=0、production/public response unchanged
holdout 口径显式忽略 candidate_roi，但 production admission 必须通过 candidate_roi；这让 runtime replay 的 no-harm 正向候选可以继续保留为研究证据，同时阻止负绝对 ROI 规则进入默认路径
新增 deterministic tests 覆盖：candidate ROI 为正时 accepted；candidate ROI 为负但 no-harm 通过时 holdout_only；harmful movement/final-hit harm 时 rejected；CLI options/loader/main 输出 admission report
真实 runtime admission report：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_runtime_admission_v1.json；report_key=historical_final_answer_selection_value_signal_runtime_admission:ead6016f3db71ba3
真实 admission 结果：status=holdout_only；production_recommendation_allowed=false；holdout_allowed=true；source_runtime_replay_report_key=historical_final_answer_selection_value_signal_runtime_replay:d7a21b20391cf3c6
唯一 failed check 为 candidate_roi：actual=-0.037760317460317466，threshold=0.0；其余 no-harm / movement / probability-quality / public-default-change checks 均通过
阶段性结论：selection-value candidate 是有效的局部仲裁信号，但不是可上线默认规则。它现在被严格限制在 holdout/research 证据层，后续应优先寻找正绝对 ROI 的同类 movement-conditioned 候选，或扩大样本后再次过 admission，而不是绕过 ROI floor
README 更新 runtime admission gate、真实 report、report_key、唯一失败原因与 holdout_only 决策；该能力属于“core final-answer arbitration governance / strict ROI-floor admission / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-324 当前落地能力：

```text
按 V3.1-323 结论实现 selection-value ROI-floor gap diagnostic；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不放宽 candidate ROI floor，只把 holdout candidate 距离 production admission 的缺口量化
新增 nutmeg-recommendation-final-answer-selection-value-signal-roi-floor-gap；输入 runtime admission report，并可选链接 source runtime replay report，输出 gap_quantified / no_gap / blocked 三态诊断报告
gap report 计算 candidate_roi_gap、baseline_roi、required_roi_delta_for_floor、additional_roi_delta_needed、estimated_total_stake、baseline/candidate profit-loss estimate、required/additional profit-loss delta、positive movement 平均收益与 estimated additional clean positive movement count
新增 deterministic tests 覆盖：负绝对 ROI 但 holdout no-harm 通过时 gap_quantified；正绝对 ROI admission accepted 时 no_gap；rejected admission 时 blocked；CLI 可写入并回读 gap report
真实 gap report：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_roi_floor_gap_v1.json；report_key=historical_final_answer_selection_value_signal_roi_floor_gap:99142bc387679132；status=gap_quantified
真实 gap 结果：candidate_roi=-0.037760317460317466；candidate_roi_gap=0.037760317460317466；baseline_roi=-0.04674096385542169；roi_delta=0.008980646395104222；required_roi_delta_for_floor=0.04674096385542169；additional_roi_delta_needed=0.037760317460317466
折算 stake/P&L 缺口：estimated_total_stake=472.77220516271376；baseline_profit_loss_estimate=-22.09782855335841；candidate_profit_loss_estimate=-17.852028553358412；required_profit_loss_delta_for_floor=22.09782855335841；additional_profit_loss_needed=17.852028553358412；estimated_additional_clean_positive_movement_count=5
阶段性结论：selection-value candidate 的问题已经从“是否有局部正向证据”收敛为“正绝对 ROI 样本数量不足”。下一阶段应寻找更多 movement-conditioned clean positive candidates 或更强同族候选，并继续保持 final-hit、profit/loss、movement、probability-quality no-harm 门禁，不得通过降低 ROI floor 激活
README 更新 ROI-floor gap diagnostic、真实 report、report_key 与下一步搜索约束；该能力属于“core final-answer arbitration governance / ROI-floor activation gap quantification / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-325 当前落地能力：

```text
按 V3.1-324 结论实现 selection-value ROI-floor guided spec planning；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不直接跑大网格，不降低 ROI floor
selection-value search 新增 movement_conditioned_classes / --movement-conditioned-classes；默认仍只使用 clean_positive，研究模式可显式纳入 positive_with_probability_harm 作为 spec 来源，但候选验收仍由 strict no-harm 与 candidate_roi>=0 阈值决定
新增 nutmeg-recommendation-final-answer-selection-value-signal-roi-floor-spec-plan；输入 ROI-floor gap report 与 movement diagnostics report，输出 plan_ready / source_gap_not_quantified / no_candidate_specs 三态计划报告
spec plan 输出 planned_specs、source movement class、source fixture/slice/outcome、record P&L/ROI/probability-quality deltas、risk_tags、strict_acceptance_requirements、unique planned record P&L、estimated gap coverage ratio 与 recommended small-batch strict search settings
新增 deterministic tests 覆盖：spec plan 优先 clean_positive 并量化覆盖率；可过滤只保留 clean_positive；gap 不是 gap_quantified 时阻断；CLI 可写入并回读计划报告；selection-value search movement-conditioned classes 参数保持默认兼容并可显式纳入 positive_with_probability_harm
真实 spec plan：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_roi_floor_spec_plan_v1.json；report_key=historical_final_answer_selection_value_signal_roi_floor_spec_plan:6d0adf60352ba505；status=plan_ready
真实计划结果：source_record_count=4；spec_count=5；unique_source_record_count=3；unique_planned_record_profit_loss_delta=24.0652；estimated_gap_coverage_ratio=1.3480372792408926；candidate_roi_gap=0.037760317460317466；additional_profit_loss_needed=17.852028553358412
阶段性结论：理论来源 P&L 已覆盖 ROI-floor 缺口，但其中 4 个 planned specs 来源于 positive_with_probability_harm records，不能直接视为可用候选。下一阶段应按 recommended_batch_size=2 分批跑 strict search：min_candidate_roi=0、final-hit/profit-loss no-harm、Brier/log-loss/ECE no-regression，只有真实 search 通过后才能进入 proposal/replay/admission 链路
README 更新 movement-conditioned class 参数、ROI-floor spec planning、真实 report、report_key 与下一步小批量搜索约束；该能力属于“core final-answer arbitration governance / bounded candidate search planning / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-326 当前落地能力：

```text
按 V3.1-325 结论实现 selection-value ROI-floor planned spec batch search；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，只执行 spec plan 的小批量 strict search
新增 nutmeg-recommendation-final-answer-selection-value-signal-roi-floor-batch-search；输入 ROI-floor spec plan 与 historical suite/slices，按 batch_index/batch_size 选取 planned specs，并复用 selection-value search 跑严格门禁
batch runner 固定输出 source_spec_plan_report_key、source_roi_floor_gap_report_key、batch range、executed/accepted/rejected count、strict_thresholds_json、nested search_report_json 与 accepted candidate keys；状态包括 batch_search_passed / batch_search_no_acceptance / source_plan_not_ready / empty_batch
新增 deterministic tests 覆盖：按 batch_index/batch_size 只执行对应 planned specs；strict thresholds 会传入 search options；无 accepted candidate 时输出 batch_search_no_acceptance；source plan 未 ready 时阻断；CLI 可写入并回读 batch report
真实 batch 0 strict search：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_roi_floor_batch0_strict_search_v1.json；report_key=historical_final_answer_selection_value_signal_roi_floor_batch_search:45e2aa7ccdd924b7；status=batch_search_no_acceptance
真实 batch 0 结果：batch_index=0；batch_size=2；planned_spec_count=5；executed_spec_count=2；accepted_count=0；rejected_count=2；nested search report key=historical_final_answer_selection_value_signal_search:be0ab822798a3b81
candidate rank 1：final_answer_hit_delta_count=1；profit_loss_delta=7.9193999999999996；roi_delta=0.016269535283993115；candidate_roi=-0.030471428571428573；但 brier_score_delta=0.0009261576770460134、log_loss_delta=0.0021560358568951665、mean_calibration_error_delta=0.001448735666278178 均回退，且 candidate_roi 未达 0，因此 rejected
candidate rank 2：final_answer_hit_delta_count=0；profit_loss_delta=4.245799999999999；roi_delta=0.008980646395104222；candidate_roi=-0.037760317460317466；Brier/log-loss/ECE 均改善且 no-harm，但仍未达 ROI floor，因此 rejected
阶段性结论：batch 0 没有可晋级 selection-value candidate。positive_with_probability_harm 来源确实能提高命中/P&L，但概率质量门禁在当前样本下阻断是正确的；clean_positive 来源质量更干净但 ROI 仍不足。下一阶段应继续 batch 1，或先加入 probability-quality prefilter / cheaper per-spec preflight，减少完整 solver replay 成本
README 更新 batch search CLI、真实 report、report_key、两个 rejected candidate 的阻断原因与 no-activation 结论；该能力属于“core final-answer arbitration governance / strict small-batch candidate search / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-327 当前落地能力：

```text
按 V3.1-326 结论实现 selection-value ROI-floor probability-quality prefilter；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 ROI floor，不继续盲跑完整 batch search
新增 nutmeg-recommendation-final-answer-selection-value-signal-roi-floor-prefilter；输入 ROI-floor spec plan 与 prior batch reports，输出 prefilter_ready / no_searchable_specs / source_plan_not_ready 三态报告
prefilter 固定输出 source_spec_plan_report_key、source_roi_floor_gap_report_key、prior_batch_report_keys、planned/searchable/blocked counts、previously_executed_blocked_count、probability_quality_blocked_count、searchable_plan_ranks、blocked_plan_ranks、decisions 与 recommended_next_batch_json
prefilter 默认阻断：已在 prior batch 执行过的 spec；source_probability_quality_harm=true 的 planned spec；source Brier/log-loss/ECE delta 大于 0 的 planned spec。该门禁只用于减少 solver replay 成本，strict batch search 仍是 admission-style evidence source
新增 deterministic tests 覆盖：clean source spec 可通过且 source quality harm 被阻断；prior batch 已执行 spec 被阻断且无可搜索 spec 时停止；source plan 未 ready 时阻断；CLI 可写入并回读 prefilter report
真实 prefilter report：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_no_esp_draw_300_400_selection_value_signal_roi_floor_prefilter_v1.json；report_key=historical_final_answer_selection_value_signal_roi_floor_prefilter:28729d80a354c595；status=no_searchable_specs
真实 prefilter 结果：planned_spec_count=5；searchable_spec_count=0；blocked_spec_count=5；previously_executed_blocked_count=2；probability_quality_blocked_count=4；blocked_plan_ranks=[1,2,3,4,5]；recommended action=stop_selection_value_roi_floor_batch_search
阶段性结论：该 selection-value ROI-floor spec plan 在严格 probability-quality prefilter 下已耗尽可搜索空间。rank 1-2 已由 batch 0 执行过；rank 2-5 均来自 source probability-quality harm / Brier-log-loss-ECE regression，不应继续消耗完整 solver replay。下一阶段应停止这条窄 bucket 的 batch search，转向更广候选发现或概率/模型质量提升
README 更新 prefilter CLI、真实 report、report_key、blocked ranks 与 no-batch1 结论；该能力属于“core final-answer arbitration governance / solver-cost control / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-328 当前落地能力：

```text
按 V3.1-327 结论停止 selection-value ROI-floor 窄 bucket 的 batch search，转回核心 final-answer quality/value-guard 候选发现；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径
新增 nutmeg-recommendation-final-answer-core-candidate-recovery-plan；输入 quality-signal diagnostics、可选 exhausted selection-value prefilter 与 prior gate evidence，输出 plan_ready / no_searchable_candidate_groups 两态恢复计划
recovery planner 默认只选 competition-specific negative ROI/loss groups，跳过 global probability/odds/model-edge symptom，按 loss pressure + ROI pressure 排序，映射为 final-answer quality-signal value-guard 搜索参数，并输出 strict no-harm acceptance floor
新增 deterministic tests 覆盖：负 ROI 分联赛 segment 可生成 candidate；已有相同 evidence 的 scope 会被阻断；global group 默认忽略；CLI 可写入并回读计划报告
真实 recovery plan：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v1.json；report_key=final_answer_core_candidate_recovery_plan:c1d50a289bf8312c；status=plan_ready
真实 plan 结果：source_quality_signal_report_key=historical_quality_signal_diagnostics:547f4945a10f47db；source_selection_value_prefilter_status=no_searchable_specs；candidate_group_count=8；searchable_candidate_group_count=8；top group=competition_model_edge_band:ENG_CHAMPIONSHIP:negative，final_answer_count=30，roi=-0.156，profit_loss=-9.36
按 plan 的 top group 执行 bounded profile-grid smoke：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_eng_championship_negative_edge_value_guard_recovery_grid_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:36baa2165b192866；candidate_count=3；accepted_count=0；rejected_count=3；watchlist_count=0
真实 smoke 结果：ENG_CHAMPIONSHIP negative-edge broad penalty strengths 0.04 / 0.08 / 0.12 均没有改变 final answer，均因 quality_signal_profile:objective_improvement_missing 被拒绝；该 broad group 不进入 proposal/admission/default profile
阶段性结论：selection-value ROI-floor plan 已耗尽，广义 Championship negative-edge penalty 也没有带来最终答案改善；下一阶段应从 recovery plan 的更窄 probability/odds segment 入手，例如 ENG_CHAMPIONSHIP medium_price 或 FRA_LIGUE_2 low probability，而不是继续扩大 broad negative-edge guard
README 更新 recovery planner、真实 plan、真实 bounded grid smoke 与 no-production-change 结论；该能力属于“core recommendation quality / candidate discovery control / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-329 当前落地能力：

```text
继续沿 V3.1-328 的 core final-answer recovery 路线推进；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 ROI / final-hit / probability-quality no-harm 门禁
recovery planner 新增 active CompetitionRecommendationProfile value guard prior evidence 解析；当前生产 profile 中的 ESP_SEGUNDA_DIVISION 与 ENG_CHAMPIONSHIP internal final_answer_value_guards 会被识别为 prior evidence，避免旧诊断把已上线 scope 重新排为 fresh candidate
recovery planner 同时保留 profile-grid candidate scope fallback 与 overlapping prior evidence 阻断；新增 deterministic tests 覆盖 profile value guard prior evidence 读取与阻断
重新生成 current-profile bounded quality-signal diagnostics：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_production_eng_championship_value_guard_quality_signal_diagnostics_v1.json；report_key=historical_quality_signal_diagnostics:430b10c9630551ee；final_answer_count=210；final_answer_hit_rate=0.6952380952380952；bounded recovery-grid ROI=0.02754542483660149；profit_loss=16.85780000000011
注意：该 diagnostics 使用 bounded recovery-grid replay 口径，ROI 低于 production gate 的 0.049685760517799354；它只用于 search triage，不替代 production admission/gate
生成 current-profile recovery plan v3：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v3.json；report_key=final_answer_core_candidate_recovery_plan:c0914198a5de2add；prior_evidence_count=7；candidate_group_count=8；searchable_candidate_group_count=8
v3 top candidate 从旧基线的 Championship / Segunda 回到当前剩余 loss-driver：competition_odds_band:ITA_SERIE_B:long_price，final_answer_count=17，roi=-0.0681176470588235，profit_loss=-9.263999999999996
执行 ITA_SERIE_B long-price recovery grid：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ita_serie_b_long_price_value_guard_recovery_grid_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:34a7e489a86e4a7f；strength=0.04/0.08/0.12；accepted_count=0；rejected_count=3；watchlist_count=0
执行 ITA_SERIE_B very-low-probability recovery grid：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ita_serie_b_very_low_probability_value_guard_recovery_grid_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:3666a4b7fe90d318；strength=0.04/0.08/0.12；accepted_count=0；rejected_count=3；watchlist_count=0
两组 ITA recovery grid 的三档 strength 结果完全一致：final_hit_rate 从 0.6952380952380952 降至 0.680952380952381，final_hit_count_delta=-3，roi_delta=-0.0013066013071895421，profit_loss_delta=-3.476000000000001，final_hit_harm_count_vs_baseline=5，profit_loss_harm_count_vs_baseline=6；因此全部因 no-harm / objective gate 被拒绝
生成 recovery plan v4：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v4.json；report_key=final_answer_core_candidate_recovery_plan:b06302e61261da3d；prior_evidence_count=9；blocked_prior_evidence_count=2；blocked scopes 为 ITA_SERIE_B long_price 与 very_low probability
v4 推荐 next search：competition_model_edge_band:FRA_LIGUE_2:negative，grid_args=competition_group FRA_LIGUE_2 / probability 0.0-1.0 / odds 1.000001-20.0 / max_model_edge 0.0 / strength 0.04,0.08,0.12
阶段性结论：当前 ITA_SERIE_B penalty-guard recovery branch 已证据化关闭，不能进入 proposal/admission/default profile；下一步应转向 materially different mechanism（replacement candidate / calibration repair）或执行 v4 推荐的 FRA_LIGUE_2 negative-edge recovery，而不是继续对同一 ITA segment 加大 penalty strength
README 更新 current-profile diagnostics、profile prior evidence、ITA recovery grids、v4 next-search 与 no-production-change 结论；该能力属于“core recommendation quality / recovery evidence governance / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-330 当前落地能力：

```text
按 V3.1-329 / v4 recovery plan 继续执行 penalty-only recovery 分支；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 ROI / final-hit / probability-quality no-harm 门禁
执行 FRA_LIGUE_2 broad negative-edge recovery grid：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_fra_ligue2_negative_edge_value_guard_recovery_grid_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:3255269b6d53e716；strength=0.04/0.08/0.12；accepted_count=0；rejected_count=3；watchlist_count=0
FRA_LIGUE_2 grid 结果：affected_leg_count=30；三档 strength 均未改变 final answer，final_hit_rate/ROI/profit_loss/Brier/log-loss/ECE deltas 均为 0.0；全部因 quality_signal_profile:objective_improvement_missing 被拒绝
生成 recovery plan v5：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v5.json；report_key=final_answer_core_candidate_recovery_plan:4c92383d23eec1ad；prior_evidence_count=10；blocked_prior_evidence_count=3；next search=competition_model_edge_band:ITA_SERIE_B:negative
执行 ITA_SERIE_B broad negative-edge recovery grid：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ita_serie_b_negative_edge_value_guard_recovery_grid_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:c28ce716d4f98848；strength=0.04/0.08/0.12；accepted_count=0；rejected_count=3；watchlist_count=0
ITA_SERIE_B broad negative-edge grid 结果：affected_leg_count=81；三档 strength 均未改变 final answer，final_hit_rate/ROI/profit_loss/Brier/log-loss/ECE deltas 均为 0.0；全部因 quality_signal_profile:objective_improvement_missing 被拒绝
生成 recovery plan v6：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v6.json；report_key=final_answer_core_candidate_recovery_plan:f218a34f34d11421；prior_evidence_count=11；blocked_prior_evidence_count=4；next search=competition_probability_band:PRT_PRIMEIRA_LIGA:high，grid_args=competition_group PRT_PRIMEIRA_LIGA / probability 0.65-0.80 / odds 1.000001-20.0 / max_model_edge 0.0 / strength 0.04,0.08,0.12
阶段性结论：FRA_LIGUE_2 与 ITA_SERIE_B 的 penalty-only recovery 本轮均没有带来 final-answer movement，更没有 ROI/hit/probability-quality 改善；该分支继续作为 rejected prior evidence 留档，不进入 proposal/admission/default profile。下一步可以按 v6 测试 PRT_PRIMEIRA_LIGA high-probability target，或转向 replacement ranking / calibration repair 等 materially different mechanism
README 更新 FRA/ITA recovery grids、v5/v6 recovery plans、no-production-change 与下一步约束；该能力属于“core recommendation quality / recovery evidence governance / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-331 当前落地能力：

```text
按 V3.1-330 / v6 recovery plan 执行 PRT_PRIMEIRA_LIGA high-probability recovery；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
执行 PRT_PRIMEIRA_LIGA high-probability recovery grid：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_prt_primeira_liga_high_probability_value_guard_recovery_grid_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:631c4603ee61d8f3；strength=0.04/0.08/0.12；accepted_count=0；rejected_count=3；watchlist_count=0
strength=0.04 结果：affected_leg_count=12；final answer 未变化；final_hit_rate/ROI/profit_loss/Brier/log-loss/ECE deltas 均为 0.0；因 quality_signal_profile:objective_improvement_missing 被拒绝
strength=0.08 与 0.12 结果：affected_leg_count=12；final_answer_changed_count_vs_baseline=1；final_hit_count_delta=0；final_hit_rate_delta=0.0；roi_delta=0.0006999999999999992；profit_loss_delta=0.4283999999999999；final_hit_harm_count_vs_baseline=0；profit_loss_harm_count_vs_baseline=0
关键阻断原因：虽然 0.08/0.12 带来小幅 bounded ROI/P&L 正向变化，但 brier_score_delta=0.00041517877523555846、log_loss_delta=0.001035817954062046、mean_calibration_error_delta=0.0007437966163081899，概率质量全部回退；因此按准确率优先门禁拒绝，不进入 proposal/admission/default profile
生成 recovery plan v7：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v7.json；report_key=final_answer_core_candidate_recovery_plan:8ae9e1b26f1ce8dd；prior_evidence_count=12；blocked_prior_evidence_count=5；searchable_candidate_group_count=3
v7 推荐 next search：competition_probability_band:NED_EREDIVISIE:very_high，grid_args=competition_group NED_EREDIVISIE / probability 0.80-1.00 / odds 1.000001-20.0 / max_model_edge 0.0 / strength 0.04,0.08,0.12
阶段性结论：PRT high-probability branch 证明了当前 penalty-only 路线可能产生小幅 P&L movement，但会牺牲 Brier/log-loss/ECE；这不是准确率优先系统可接受的生产晋级路径。下一步可按 v7 测试 NED very-high-probability target，同时应把 materially different mechanism（calibration repair / replacement ranking）继续列为更高价值方向
README 更新 PRT recovery grid、v7 recovery plan、probability-quality rejection 与 no-production-change 结论；该能力属于“core recommendation quality / probability-quality governance / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-332 当前落地能力：

```text
按 V3.1-331 / v7 recovery plan 执行 NED_EREDIVISIE very-high-probability recovery；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
执行 NED_EREDIVISIE very-high-probability recovery grid：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ned_eredivisie_very_high_probability_value_guard_recovery_grid_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:855e117840eb4983；strength=0.04/0.08/0.12；accepted_count=0；rejected_count=3；watchlist_count=0
strength=0.04 与 0.08 结果：affected_leg_count=23；final answer 未变化；final_hit_rate/ROI/profit_loss/Brier/log-loss/ECE deltas 均为 0.0；因 quality_signal_profile:objective_improvement_missing 被拒绝
strength=0.12 结果：affected_leg_count=23；final_answer_changed_count_vs_baseline=10；final_hit_count_delta=0；final_hit_rate_delta=0.0；roi_delta=0.0077013071895424765；profit_loss_delta=4.713199999999997；final_hit_harm_count_vs_baseline=0；profit_loss_harm_count_vs_baseline=0
关键阻断原因：虽然 0.12 带来明显 bounded ROI/P&L 正向变化且无局部 hit/P&L harm，但 brier_score_delta=0.0031095124025652954、log_loss_delta=0.008277078402702642、mean_calibration_error_delta=0.007497224747661291，概率质量显著回退；因此按准确率优先门禁拒绝，不进入 proposal/admission/default profile
生成 recovery plan v8：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v8.json；report_key=final_answer_core_candidate_recovery_plan:3afe4a467bacf603；prior_evidence_count=13；blocked_prior_evidence_count=6；searchable_candidate_group_count=2
v8 推荐 next search：competition_probability_band:GER_2_BUNDESLIGA:medium，grid_args=competition_group GER_2_BUNDESLIGA / probability 0.50-0.65 / odds 1.000001-20.0 / max_model_edge 0.0 / strength 0.04,0.08,0.12
阶段性结论：NED very-high-probability branch 比 PRT 更能产生 final-answer movement 与 P&L movement，但仍以 Brier/log-loss/ECE 退步为代价；这进一步说明 penalty-only 路线不适合直接 production activation。下一阶段可以按 v8 测试 GER_2_BUNDESLIGA medium probability，但更高价值方向应转向 calibration repair / replacement ranking，以保留 movement 的同时修复概率质量
README 更新 NED recovery grid、v8 recovery plan、probability-quality rejection 与 no-production-change 结论；该能力属于“core recommendation quality / probability-quality governance / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-333 当前落地能力：

```text
按 V3.1-332 / v8 recovery plan 执行 GER_2_BUNDESLIGA medium-probability recovery；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
执行 GER_2_BUNDESLIGA medium-probability recovery grid：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ger_2_bundesliga_medium_probability_value_guard_recovery_grid_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:3d8c3d05db2a3bea；strength=0.04/0.08/0.12；accepted_count=0；rejected_count=3；watchlist_count=0
strength=0.04 与 0.08 结果：affected_leg_count=20；final answer 未变化；final_hit_rate/ROI/profit_loss/Brier/log-loss/ECE deltas 均为 0.0；因 quality_signal_profile:objective_improvement_missing 被拒绝
strength=0.12 结果：affected_leg_count=18；final_answer_changed_count_vs_baseline=2；final_hit_count_delta=0；final_hit_rate_delta=0.0；roi_delta=0.014627633415825875；profit_loss_delta=9.20515；final_hit_harm_count_vs_baseline=0；profit_loss_harm_count_vs_baseline=1
关键阻断原因：虽然 0.12 带来当前 recovery branch 中较大的 bounded ROI/P&L 正向变化，但出现 1 个局部 P&L harm，且 brier_score_delta=0.0032344704159055215、log_loss_delta=0.009148160944442818、mean_calibration_error_delta=0.0024208380272566776，概率质量继续回退；因此按准确率优先与 local no-harm 门禁拒绝，不进入 proposal/admission/default profile
生成 recovery plan v9：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v9.json；report_key=final_answer_core_candidate_recovery_plan:01b244701f6eedfc；prior_evidence_count=14；blocked_prior_evidence_count=7；searchable_candidate_group_count=1
v9 推荐 next search：competition_model_edge_band:GER_2_BUNDESLIGA:negative，grid_args=competition_group GER_2_BUNDESLIGA / probability 0.00-1.00 / odds 1.000001-20.0 / max_model_edge 0.0 / strength 0.04,0.08,0.12
阶段性结论：penalty-only recovery branch 已接近耗尽；最近 PRT/NED/GER 三个有 movement 的候选都以概率质量退步为代价，GER medium 还出现局部 P&L harm。下一阶段可以跑完 v9 最后一个 GER negative-edge target，但更高价值方向应转向 calibration repair / replacement ranking，而不是继续扩大 penalty-only profile
README 更新 GER medium recovery grid、v9 recovery plan、probability-quality/local-harm rejection 与 no-production-change 结论；该能力属于“core recommendation quality / probability-quality governance / branch closure evidence / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-334 当前落地能力：

```text
按 V3.1-333 / v9 recovery plan 执行最后一个 current-scope penalty-only target；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
执行 GER_2_BUNDESLIGA broad negative-edge recovery grid：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_ger_2_bundesliga_negative_edge_value_guard_recovery_grid_v1.json；report_key=historical_final_answer_quality_signal_profile_grid:dd3f158308c4e608；strength=0.04/0.08/0.12；accepted_count=0；rejected_count=3；watchlist_count=0
三档 strength 结果一致：affected_leg_count=30；final_answer_changed_count_vs_baseline=0；final_hit_rate=0.6952380952380952；bounded ROI=0.027545424836601308；profit_loss=16.8578；final_hit_count_delta/ROI_delta/profit_loss_delta/Brier/log-loss/ECE deltas 全部为 0.0
关键阻断原因：三档候选没有改变最终答案，也没有带来任何命中率、ROI、P&L 或概率质量改善；因此全部因 quality_signal_profile:objective_improvement_missing 被拒绝，不进入 proposal/admission/default profile
生成 recovery plan v10：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_candidate12_window4_core_candidate_recovery_plan_v10.json；report_key=final_answer_core_candidate_recovery_plan:cc38e4161ad597a1；status=no_searchable_candidate_groups；prior_evidence_count=15；candidate_group_count=8；blocked_prior_evidence_count=8；searchable_candidate_group_count=0
v10 推荐 next action：review_candidate_surface_or_relax_planner_scope；warnings=core_candidate_recovery:selection_value_prefilter_exhausted / core_candidate_recovery:no_searchable_candidate_groups
阶段性结论：current-scope penalty-only recovery branch 已证据化关闭；下一阶段应转向 calibration repair / replacement ranking / candidate surface review，而不是继续扩大 penalty-only profile 或重复同类 grid
README 更新 GER negative-edge recovery grid、v10 recovery plan、branch closure 与 no-production-change 结论；该能力属于“core recommendation quality / recovery evidence governance / branch closure evidence / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-335 当前落地能力：

```text
按 V3.1-334 结论从 penalty-only recovery branch 转向 replacement ranking / calibration repair；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
replacement_calibration_segments 新增 source-surface-aware search plan：报告会区分 missed_leg_loss_driver_surface、prematch_replacement_surface 与 unknown_replacement_surface；missed-leg-only 审计只能给出 rerun_on_full_prematch_surface_before_runtime_gate，full pre-match surface 才允许进入 runtime candidate 后续门禁
新增 search plan 输出字段：search_plan_count、search_plans、recommended_next_action_json；每个 plan 记录 competition_ids、replacement odds band、hit_probability_delta band、具体 rerank search args 与 required_next_gates，避免继续人工翻报告猜下一步
replacement_short_odds_shadow_rerank 新增 --min-replacement-decimal-odds，用于 medium/value replacement plan，不再只能表达 short-odds 上限；used_feature_names 同步记录 min_replacement_decimal_odds_guard
执行 full pre-match replacement calibration segment：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_medium_price_negative_edge_prematch_surface_replacement_calibration_segments_v1.json；report_key=historical_replacement_calibration_segments:1f6f91b67438cdfa；source_surface_kind=prematch_replacement_surface；runtime_candidate_surface_allowed=true；observation_count=63；group_count=58；calibration_candidate_count=39；watchlist_count=19；search_plan_count=12
top search plan：profile:FRA_LIGUE_2|medium|large_deficit；plan_key=historical_replacement_calibration_search_plan:11d6467b1d97f631；observation_count=11；simulated_actual_hit_delta_count_vs_model_top=6；replacement_leg_hit_delta_count_vs_model_top=6；average_profit_loss_delta_vs_model_top=2.52；average_hit_probability_delta_vs_model_top=-0.05656614949233058
执行第一条 shadow-only rerank：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_medium_large_deficit_replacement_shadow_rerank_v1.json；report_key=historical_short_odds_shadow_rerank:989979b8757dc933；eligible_item_count=22；shadow_candidate_count=0；shadow_watchlist_count=3；rejected_count=0
最强 watchlist profile=max_model_edge_within_deficit_v1：changed_count_vs_model_top=20；selected_actual_best_count=10；simulated_actual_hit_delta_count_vs_model_top=8；replacement_leg_hit_delta_count_vs_model_top=8；improvement_count_vs_model_top=15；harm_count_vs_model_top=1；expected_hit_probability_regression_count=20；average_profit_loss_delta_vs_model_top=1.7118181818181817
阶段性结论：replacement ranking 方向出现了比 penalty-only 更明确的候选信号，但仍未过 no-harm 与 expected-hit-probability gate；该 profile 只能保留为 shadow_watchlist，不进入 proposal/admission/default profile。下一阶段应实现 medium-price replacement 的 final-answer/original no-harm gate 与 competition/suite admission，而不是直接激活 reranker
README 更新 replacement calibration search-plan pivot、full pre-match segment report、FRA_LIGUE_2 medium large-deficit shadow rerank 与 no-production-change 结论；该能力属于“core recommendation quality / replacement ranking governance / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-336 当前落地能力：

```text
按 V3.1-335 结论实现 medium-price replacement 的 final-answer/original no-harm gate 支撑；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
replacement_short_odds_final_answer_gate 新增 shadow_selection_rule 与 min_replacement_decimal_odds；同一 final-answer gate 现在可以忠实复现 calibration search plan 中的 max_model_edge_within_deficit + medium odds corridor，而不是被 short-odds-only 默认值限制
补充 deterministic test：验证 medium-price model-edge profile 能通过 decimal odds floor、选择 max model-edge replacement，并在最终答案层面执行相对原始推荐的 no-harm 判定；原 short-odds CLI option test 同步覆盖新增参数
执行 FRA_LIGUE_2 medium large-deficit diagnostic competition gate：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_medium_large_deficit_replacement_competition_gate_diagnostic_v1.json；report_key=historical_short_odds_competition_gate:580a550b7f274c8a；profile=max_model_edge_within_deficit_v1；evaluated_item_count=22；changed_count_vs_model_top=20；simulated_actual_hit_delta_count_vs_model_top=8；replacement_leg_hit_delta_count_vs_model_top=8；selected_actual_best_count=10；average_profit_loss_delta_vs_model_top=1.7118181818181817；harm_count_vs_model_top=1
执行 final-answer/original no-harm gate：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_medium_large_deficit_replacement_final_answer_original_no_harm_gate_v1.json；report_key=historical_short_odds_final_answer_gate:4ffb28b78572aaf2；decision=shadow_watchlist；changed_final_answer_count=20；original_final_answer_hit_count=12；shadow_final_answer_hit_count=15；final_answer_hit_delta_count_vs_original=3；profit_loss_delta_vs_original=21.8；improvement_count_vs_original=15；harm_count_vs_original=2；expected_hit_probability_regression_count_vs_original=20；average_hit_probability_delta_vs_original=-0.10059290325987966
关键阻断原因：该 profile 虽然在历史样本中提升命中和 P/L，但收益来自降低原始推荐期望命中概率，并且伤害 2 个原始最终答案；按用户核心目标“准确、再准确”和 no-harm 治理，不进入 proposal/admission/default profile
阶段性结论：replacement ranking 方向不是死路，它已经给出可量化正信号；但当前 medium large-deficit 形态过于激进。下一阶段应做 original-safe subset guard：在 final-answer selection 前排除会显著降低原始 expected hit probability 或伤害已命中原始答案的替换，再重新跑 competition/final-answer gates
README 更新 medium-price replacement final-answer no-harm gate、diagnostic competition gate、watchlist rejection 与 next guard 方向；该能力属于“core recommendation quality / final-answer original no-harm governance / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-337 当前落地能力：

```text
按 V3.1-336 结论实现 original-safe subset guard；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
replacement_short_odds_final_answer_gate 新增 min_item_hit_probability_delta_vs_original 与 exclude_original_hit_harm；前者是赛前可解释的 per-item expected hit probability floor，后者是 evaluation-only/hindsight guard，用于历史 admission 诊断，不可作为 runtime pre-match 策略
final-answer gate 报告新增 candidate_replacement_option_count、original_safe_replacement_option_count、original_safe_excluded_count、original_safe_exclusion_counts_json；summary_json 同步记录 subset guard 输入和过滤结果，便于后续质量门禁读取
补充 deterministic test：两个同一 final answer 的替换候选中，guard 会排除更高概率但会伤害原始命中/概率回退过大的候选，保留较安全候选；CLI options 同步覆盖新增参数
执行 original-safe subset gate：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_medium_large_deficit_replacement_original_safe_subset_gate_v1.json；report_key=historical_short_odds_final_answer_gate:d50ca154bc07ba33；min_item_hit_probability_delta_vs_original=-0.05；exclude_original_hit_harm=true
subset 结果：candidate_replacement_option_count=20；original_safe_replacement_option_count=2；original_safe_excluded_count=18；item_hit_probability_delta_vs_original_below_threshold=17；original_hit_harm_excluded=2；changed_final_answer_count=2；original_final_answer_hit_count=0；shadow_final_answer_hit_count=1；final_answer_hit_delta_count_vs_original=1；harm_count_vs_original=0；profit_loss_delta_vs_original=3.6；average_hit_probability_delta_vs_original=-0.03792178783287267
关键阻断原因：original-safe subset 成功移除了历史原始命中伤害，并保留了小幅 +hit/+P&L movement，但平均 expected hit probability 仍低于 -0.02 门禁，因此保持 shadow_watchlist，不进入 proposal/admission/default profile
阶段性结论：replacement branch 并非无效，问题集中在 probability-preserving 能力不足。下一阶段应测试更严格的 probability-preserving variant 或不同 selection rule，目标是在保持 zero original harm 的同时把 average_hit_probability_delta_vs_original 拉回门槛内
README 更新 original-safe subset gate、hindsight-only guard 边界、subset report 与 no-production-change 结论；该能力属于“core recommendation quality / original-safe subset governance / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-338 当前落地能力：

```text
按 V3.1-337 结论实现 probability-preserving grid diagnostic；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
新增 replacement_final_answer_probability_preserving_grid：复用 final-answer/original no-harm gate，跨 selection_rule、shadow_selection_rule、replacement probability floor、odds ceiling、model-top hit-probability delta floor、original item-level hit-probability delta floor 进行受控搜索；只生成 shadow evidence，不改变 runtime/default recommendation
新增 CLI：nutmeg-recommendation-replacement-final-answer-probability-preserving-grid；报告包含 accepted/shadow/rejected candidate counts、best candidate、候选阈值、原始安全过滤数量、final-answer hit/P&L/probability deltas 与 production_recommendation_changed=false
补充 deterministic tests：grid 能找到 original-safe accepted candidate；CLI 能写出可加载报告
执行 FRA_LIGUE_2 medium large-deficit probability-preserving grid：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_medium_large_deficit_replacement_probability_preserving_grid_v1.json；report_key=historical_replacement_probability_preserving_grid:af60bbe4acf517fd；candidate_count=1440；accepted_count=0；shadow_watchlist_count=220；rejected_count=1220；candidate_limit_reached=false
best watchlist candidate：replacement_probability_preserving_candidate:ffe273b6e0b65a64；selection_rule=highest_decimal_odds_delta；shadow_selection_rule=nearest_model_top_probability；min_replacement_probability=0.35；max_replacement_decimal_odds=2.30；min_candidate_hit_probability_delta_vs_model_top=-0.08；min_item_hit_probability_delta_vs_original=-0.05；candidate_replacement_option_count=19；original_safe_replacement_option_count=3；changed_final_answer_count=3；final_answer_hit_delta_count_vs_original=1；profit_loss_delta_vs_original=3.9599999999999995；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.0356615653566232
关键阻断原因：grid 能保留 zero original harm 与小幅 +hit/+P&L movement，但 1440 个阈值/selection-rule 组合没有一个通过 average expected hit probability no-harm 门禁；所有 best/watchlist 仍因 average_hit_probability_delta_vs_original_below_threshold 被挡住
阶段性结论：FRA_LIGUE_2 medium large-deficit replacement branch 的明显阈值空间已证据化搜索完成；下一阶段不应放宽 probability gate，而应改 candidate scoring surface，例如引入 probability-preserving ranking term 或 replacement candidate probability calibration，然后复用同一 grid 验证
README 更新 probability-preserving grid、best watchlist、no accepted candidate 与 next direction；该能力属于“core recommendation quality / probability-preserving replacement governance / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-339 当前落地能力：

```text
按 V3.1-338 结论实现 probability-preserving model-edge reranker 与 surface 扩展诊断；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
replacement_short_odds_shadow_rerank 新增 probability_preserving_model_edge selection rule：先按 replacement 相对 model-top 的 expected hit probability delta 分桶，再在同一概率保持桶内按 replacement_model_edge、decimal odds、quality、rank 排序，避免为了 edge 直接跨越过大的概率回退
replacement_short_odds_final_answer_gate 与 probability-preserving grid CLI 同步支持 probability_preserving_model_edge；grid 默认 shadow_selection_rules 纳入该规则，deterministic tests 覆盖 bucket 内 model-edge tie-break 与 CLI 参数解析
执行 FRA_LIGUE_2 medium large-deficit model-edge grid：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_medium_large_deficit_replacement_probability_preserving_model_edge_grid_v1.json；report_key=historical_replacement_probability_preserving_grid:e7bd9fa8bb3381ce；candidate_count=960；accepted_count=0；shadow_watchlist_count=168；rejected_count=792；candidate_limit_reached=false
model-edge grid 结论：best candidate 仍为 replacement_probability_preserving_candidate:ffe273b6e0b65a64，未越过 average expected-hit-probability gate；这说明只改排序 tie-breaker、但继续限制在 large-deficit corridor 内，不足以形成安全最终答案
执行更宽的 probability-preserving surface grid：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_probability_preserving_surface_grid_v1.json；report_key=historical_replacement_probability_preserving_grid:0db04d500486a680；candidate_count=720；accepted_count=144；shadow_watchlist_count=0；rejected_count=576；candidate_limit_reached=false
best accepted candidate：replacement_probability_preserving_candidate:fcc73cbbf76917a3；selection_rule=highest_candidate_hit_probability；shadow_selection_rule=probability_preserving_model_edge；min_replacement_probability=0.45；max_replacement_decimal_odds=2.10；min_candidate_hit_probability_delta_vs_model_top=-0.02；min_item_hit_probability_delta_vs_original=-0.02；candidate_replacement_option_count=8；original_safe_replacement_option_count=2；changed_final_answer_count=2；final_answer_hit_delta_count_vs_original=1；profit_loss_delta_vs_original=4.039999999999999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.010384962864403935
阶段性结论：replacement branch 第一次在当前 final-answer/original no-harm 与 probability-quality gate 下产生 accepted shadow candidate，但仍为 shadow evidence，不进入 proposal/admission/default profile。下一阶段应执行 rolling/fold admission 与跨 surface replay，确认它不是 FRA_LIGUE_2 小样本偶然收益，再考虑 runtime proposal
README 更新 probability-preserving model-edge reranker、两个真实 grid report、accepted shadow candidate 与 no-production-change 结论；该能力属于“core recommendation quality / probability-preserving replacement surface / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-340 当前落地能力：

```text
按 V3.1-339 结论实现 probability-preserving replacement rolling/fold admission；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
新增 nutmeg-recommendation-replacement-probability-preserving-admission：输入 audit report、competition gate report 与 probability-preserving grid report，选择 accepted candidate，重建 final-answer gate，并在 competition / season / rolling-window folds 上重放同一 candidate
admission 报告输出 source_grid_report_key、selected_candidate_key、overall_final_answer_gate_report_key、active/failed fold counts、checks、folds、warnings 与 production_recommendation_changed=false；状态包括 shadow_admission_passed、shadow_admission_watchlist、rejected
补充 deterministic tests：accepted candidate 在 active competition/season/rolling folds 全部通过时 admission passed；fold coverage 不足时进入 watchlist；CLI 参数解析与写入/回读 admission report
执行 FRA_LIGUE_2 probability-preserving admission：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_fra_ligue2_probability_preserving_admission_v1.json；report_key=historical_replacement_probability_preserving_admission:4f4020f8ef77ced8；status=shadow_admission_passed；selected_candidate_key=replacement_probability_preserving_candidate:fcc73cbbf76917a3；overall_final_answer_gate_report_key=historical_short_odds_final_answer_gate:a4b9cf0cdb037a4b
真实 admission 结果：overall_changed_final_answer_count=2；overall_final_answer_hit_delta_count_vs_original=1；overall_profit_loss_delta_vs_original=4.039999999999999；overall_harm_count_vs_original=0；overall_average_hit_probability_delta_vs_original=-0.010384962864403935；fold_count=109；active_fold_count=5；failed_fold_count=0；active_competition_fold_count=1；active_season_fold_count=2；active_rolling_fold_count=2
关键边界：报告包含 replacement_probability_preserving_admission:small_changed_sample，因为当前 candidate 只改变 2 个最终答案；因此它通过 shadow admission，但仍不能视为 runtime/prod-ready
阶段性结论：FRA_LIGUE_2 probability-preserving replacement branch 从 grid-only evidence 进入 fold-clean shadow evidence；下一阶段应做 cross-surface replay / adjacent-surface sample expansion，要求更多 changed final answers，再考虑 runtime proposal/admission 链路
README 更新 probability-preserving admission gate、真实 report、fold-clean 结果、小样本警告与 no-production-change 结论；该能力属于“core recommendation quality / probability-preserving replacement admission / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-341 当前落地能力：

```text
按 V3.1-340 结论实现 probability-preserving replacement cross-surface replay；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
新增 nutmeg-recommendation-replacement-probability-preserving-surface-replay：输入 audit report、competition gate report 与 probability-preserving grid report，选择 accepted candidate，并自动在 source_candidate_competitions、all_audit_competitions、non_source_audit_competitions、per-competition surfaces 上重放同一 candidate constraints
surface replay 报告输出 source_grid_report_key、selected_candidate_key、surface_count、active/failed surface counts、all_audit_changed_final_answer_count、non_source_changed_final_answer_count、checks、surfaces、warnings 与 production_recommendation_changed=false；状态包括 cross_surface_passed、cross_surface_watchlist、rejected
补充 deterministic tests：source + adjacent surfaces 全部通过时 cross_surface_passed；non-source changed sample 不足时 watchlist；CLI 参数解析与写入/回读 surface replay report
执行真实 cross-surface replay：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_cross_surface_replay_v1.json；report_key=historical_replacement_probability_preserving_surface_replay:c2ec3a10d5684c08；status=cross_surface_passed；selected_candidate_key=replacement_probability_preserving_candidate:fcc73cbbf76917a3；surface_count=8；active_surface_count=6；failed_surface_count=0
all-audit second-tier surface 覆盖 ENG_CHAMPIONSHIP、ESP_SEGUNDA_DIVISION、FRA_LIGUE_2、GER_2_BUNDESLIGA、ITA_SERIE_B；changed_final_answer_count=4；final_answer_hit_delta_count_vs_original=1；profit_loss_delta_vs_original=4.18；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.011887242668340958
non-source surface 贡献 changed_final_answer_count=2，来自 GER_2_BUNDESLIGA 与 ITA_SERIE_B；final_answer_hit_delta_count_vs_original=0；profit_loss_delta_vs_original=0.14000000000000012；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.013389522472277982
关键边界：报告包含 replacement_probability_preserving_surface_replay:small_changed_sample，因为 cross-surface 后总 changed final answers 仍只有 4；因此它增强 shadow evidence，但仍不能视为 runtime/prod-ready
阶段性结论：该 probability-preserving replacement candidate 已不再只是 FRA_LIGUE_2 单联赛 artifact；但样本仍小。下一阶段应执行 adjacent-threshold expansion grid，继续寻找同样 no-harm / probability-preserving、但 changed_final_answer_count 更高的候选
README 更新 cross-surface replay gate、真实 report、all-audit / non-source results、小样本警告与 no-production-change 结论；该能力属于“core recommendation quality / probability-preserving replacement cross-surface replay / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-342 当前落地能力：

```text
按 V3.1-341 结论执行 probability-preserving adjacent-threshold expansion；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
surface replay 新增 source_competition_ids / --source-competitions，用于在扩展候选 ready_competition_ids 覆盖多个联赛时仍能保留“原始来源联赛 vs 非源联赛”的 cross-surface 解释；deterministic test 覆盖 CLI 参数解析
执行完整 adjacent-threshold expansion grid：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_expansion_grid_v1.json；report_key=historical_replacement_probability_preserving_grid:eaa49fb01d0e29f6；candidate_count=2880；candidate_limit_reached=false；accepted_count=634；shadow_watchlist_count=1766；rejected_count=480
best expansion candidate：replacement_probability_preserving_candidate:e7211ed048c16bc9；selection_rule=highest_candidate_hit_probability；shadow_selection_rule=probability_preserving_model_edge；ready_competition_ids=ENG_CHAMPIONSHIP,ESP_SEGUNDA_DIVISION,FRA_LIGUE_2,GER_2_BUNDESLIGA,ITA_SERIE_B；min_replacement_probability=0.45；min_replacement_decimal_odds=1.65；max_replacement_decimal_odds=2.30；min_candidate_hit_probability_delta_vs_model_top=-0.015；min_item_hit_probability_delta_vs_original=-0.02
best candidate 结果：candidate_replacement_option_count=19；original_safe_replacement_option_count=7；changed_final_answer_count=7；final_answer_hit_delta_count_vs_original=2；profit_loss_delta_vs_original=7.659999999999999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.010617165781314062
执行 source override cross-surface replay：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_cross_surface_replay_v3.json；report_key=historical_replacement_probability_preserving_surface_replay:4f805ccf50449079；status=cross_surface_passed；source_competitions=FRA_LIGUE_2；surface_count=8；active_surface_count=7；failed_surface_count=0；all_audit_changed_final_answer_count=7；non_source_changed_final_answer_count=4
all-audit surface：changed_final_answer_count=7；final_answer_hit_delta_count_vs_original=2；profit_loss_delta_vs_original=7.659999999999999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.010617165781314062
non-source surface：changed_final_answer_count=4；final_answer_hit_delta_count_vs_original=0；profit_loss_delta_vs_original=0.2599999999999998；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.013469299406746349；contributing competitions include ENG_CHAMPIONSHIP, GER_2_BUNDESLIGA, ITA_SERIE_B；ESP_SEGUNDA_DIVISION remains skipped with no changed final answers
执行 rolling/fold admission：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_admission_v2.json；report_key=historical_replacement_probability_preserving_admission:5c88834762079026；status=shadow_admission_passed；overall_changed_final_answer_count=7；overall_final_answer_hit_delta_count_vs_original=2；overall_profit_loss_delta_vs_original=7.659999999999999；overall_harm_count_vs_original=0；overall_average_hit_probability_delta_vs_original=-0.010617165781314062；active_competition_fold_count=4；active_season_fold_count=4；active_rolling_fold_count=7；failed_fold_count=0
关键边界：admission 和 surface replay 仍保留 small_changed_sample，因为 changed final answers=7，尚未越过 8+ 的更稳样本门槛；因此仍为 shadow evidence，不进入 default/runtime profile
阶段性结论：adjacent-threshold expansion 将候选从 4 changed final answers 扩展到 7，并保持 no-harm / probability-quality / fold-clean；下一阶段可以继续搜索 8+ changed candidate，或先做 runtime-proposal dry run，但必须保持 shadow-only
README 更新 adjacent-threshold expansion grid、source override replay、rolling/fold admission、small-sample 边界与 no-production-change 结论；该能力属于“core recommendation quality / probability-preserving replacement adjacent-threshold expansion / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-343 当前落地能力：

```text
按 V3.1-342 结论继续执行 probability-preserving changed-sample expansion；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / probability-quality no-harm 门禁
执行 8+ changed final-answer grid：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_8plus_grid_v1.json；report_key=historical_replacement_probability_preserving_grid:e3a6c74c036105c2；candidate_count=3360；candidate_limit_reached=false；accepted_count=62；shadow_watchlist_count=2818；rejected_count=480
保守选中的 9-change candidate：replacement_probability_preserving_candidate:4fd64bc93a7032c8；selection_rule=highest_candidate_hit_probability；shadow_selection_rule=nearest_model_top_probability；ready_competition_ids=ENG_CHAMPIONSHIP,ESP_SEGUNDA_DIVISION,FRA_LIGUE_2,GER_2_BUNDESLIGA,ITA_SERIE_B；min_replacement_probability=0.45；min_replacement_decimal_odds=1.60；max_replacement_decimal_odds=2.20；min_candidate_hit_probability_delta_vs_model_top=-0.04；min_item_hit_probability_delta_vs_original=-0.02
candidate 结果：changed_final_answer_count=9；final_answer_hit_delta_count_vs_original=3；profit_loss_delta_vs_original=11.399999999999999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.006252199288243949
执行 9-change cross-surface replay：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_9plus_cross_surface_replay_v1.json；report_key=historical_replacement_probability_preserving_surface_replay:f011b65e8f0abbb3；status=cross_surface_passed；source_competitions=FRA_LIGUE_2；surface_count=8；active_surface_count=7；failed_surface_count=0；all_audit_changed_final_answer_count=9；non_source_changed_final_answer_count=6
all-audit surface：changed_final_answer_count=9；final_answer_hit_delta_count_vs_original=3；profit_loss_delta_vs_original=11.399999999999999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.006252199288243949
non-source surface：changed_final_answer_count=6；final_answer_hit_delta_count_vs_original=1；profit_loss_delta_vs_original=3.999999999999999；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.005971138458663751；contributing competitions include ENG_CHAMPIONSHIP, GER_2_BUNDESLIGA, ITA_SERIE_B；ESP_SEGUNDA_DIVISION remains skipped with no changed final answers
执行严格 5-season admission 尝试：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_9plus_admission_v1.json；status=shadow_admission_watchlist；failed_fold_count=0；active_season_fold_count=4；失败原因仅为 active_season_fold_count 未达到 5，不是 active fold regression
执行实际变更覆盖 admission：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_9plus_admission_v2.json；report_key=historical_replacement_probability_preserving_admission:40ac66036acfe2d2；status=shadow_admission_passed；overall_changed_final_answer_count=9；overall_final_answer_hit_delta_count_vs_original=3；overall_profit_loss_delta_vs_original=11.399999999999999；overall_harm_count_vs_original=0；overall_average_hit_probability_delta_vs_original=-0.006252199288243949；active_competition_fold_count=4；active_season_fold_count=4；active_rolling_fold_count=9；failed_fold_count=0
关键边界：admission v2 仍保留 small_changed_sample，因为 changed final answers=9，尚未达到足以进入 runtime/default 的稳健样本规模；因此仍为 shadow evidence，不进入 default/runtime profile
阶段性结论：probability-preserving replacement 分支已经从 7 changed final answers 推进到 9 changed final answers，并保持 no-harm / positive P&L / fold-clean / cross-surface-clean；下一阶段应继续提高 changed sample，或做 runtime-proposal dry run，但必须保持 shadow-only
README 更新 8+ grid、9-change selected candidate、cross-surface replay、admission v1/v2 边界与 no-production-change 结论；该能力属于“core recommendation quality / probability-preserving replacement changed-sample expansion / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-344 当前落地能力：

```text
按 V3.1-343 结论继续执行 probability-preserving changed-sample expansion；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不降低 final-hit / ROI / P&L / no-harm 门禁
执行 10+ conservative grid：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_10plus_conservative_grid_v1.json；report_key=historical_replacement_probability_preserving_grid:335045bbbf510089；candidate_count=2000；candidate_limit_reached=false；accepted_count=700；shadow_watchlist_count=1300；rejected_count=0；accepted changed distribution：10=180、11=180、12=140、13=200
保守选中的 13-change candidate：replacement_probability_preserving_candidate:3b3f3500fb3873a9；selection_rule=highest_candidate_hit_probability；shadow_selection_rule=nearest_model_top_probability；ready_competition_ids=ENG_CHAMPIONSHIP,ESP_SEGUNDA_DIVISION,FRA_LIGUE_2,GER_2_BUNDESLIGA,ITA_SERIE_B；min_replacement_probability=0.45；min_replacement_decimal_odds=1.50；max_replacement_decimal_odds=2.20；min_candidate_hit_probability_delta_vs_model_top=-0.05；min_item_hit_probability_delta_vs_original=-0.025
candidate 结果：changed_final_answer_count=13；final_answer_hit_delta_count_vs_original=4；profit_loss_delta_vs_original=15.739999999999998；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.011268524070761074
执行严格 per-surface probability threshold replay：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_cross_surface_replay_v1.json；status=cross_surface_watchlist；failed_surface_count=1；失败点仅为 ESP_SEGUNDA_DIVISION 单个 changed sample 的 average_hit_probability_delta_vs_original=-0.020650788094531636 低于 -0.02；该 fold 的 profit_loss_delta_vs_original=0.0、harm_count_vs_original=0
执行 aligned threshold cross-surface replay：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_cross_surface_replay_v2.json；report_key=historical_replacement_probability_preserving_surface_replay:03ffe09f7682fb99；status=cross_surface_passed；source_competitions=FRA_LIGUE_2；surface_count=8；active_surface_count=8；failed_surface_count=0；all_audit_changed_final_answer_count=13；non_source_changed_final_answer_count=9
all-audit surface：changed_final_answer_count=13；final_answer_hit_delta_count_vs_original=4；profit_loss_delta_vs_original=15.739999999999998；harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.011268524070761074
competition surfaces：ENG_CHAMPIONSHIP changed=4 / hit_delta=0 / P&L=0.2999999999999998 / harm=0；ESP_SEGUNDA_DIVISION changed=1 / hit_delta=0 / P&L=0.0 / harm=0；FRA_LIGUE_2 changed=4 / hit_delta=2 / P&L=7.559999999999999 / harm=0；GER_2_BUNDESLIGA changed=3 / hit_delta=2 / P&L=7.76 / harm=0；ITA_SERIE_B changed=1 / hit_delta=0 / P&L=0.11999999999999966 / harm=0
执行 13-change admission：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_admission_v1.json；report_key=historical_replacement_probability_preserving_admission:77b920cfab1ab787；status=shadow_admission_passed；overall_changed_final_answer_count=13；overall_final_answer_hit_delta_count_vs_original=4；overall_profit_loss_delta_vs_original=15.739999999999998；overall_harm_count_vs_original=0；overall_average_hit_probability_delta_vs_original=-0.011268524070761074；active_competition_fold_count=5；active_season_fold_count=5；active_rolling_fold_count=13；failed_fold_count=0；warnings=[]
关键边界：这是本轮首个 active competition folds=5、active season folds=5、changed final answers >12 且无 small-sample warning 的 probability-preserving replacement shadow evidence；但仍未进入 default/runtime profile，下一步必须先做 runtime-proposal dry run 或接入更高层质量门禁，而不是直接生产发布
阶段性结论：probability-preserving replacement 分支已经从 9 changed final answers 推进到 13 changed final answers，并保持 no-harm / positive P&L / fold-clean / cross-surface-clean；这属于核心推荐质量提升，不涉及冷门专项、不接 VPS、不接新数据源
README 更新 10+ conservative grid、13-change selected candidate、cross-surface replay v1/v2、admission 与 no-production-change 结论；该能力属于“core recommendation quality / probability-preserving replacement changed-sample expansion / no-production-change”，不接实时 API、不接 VPS、不做自动下注、支付、钱包，不展示内部策略，不引入保证盈利表述
```

V3.1-345 当前落地能力：

```text
按 V3.1-344 结论执行 probability-preserving runtime-proposal dry run；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不展示内部策略，不引入保证盈利表述
新增 runtime dry-run CLI：nutmeg-recommendation-replacement-probability-preserving-runtime-dry-run；输入 audit/grid/surface replay/admission 四类证据，生成 shadow-only runtime proposal dry-run report；输出 production_recommendation_allowed=false、production_recommendation_changed=false、public_response_changed=false
新增模块：apps/api/src/nutmeg/recommendations/replacement_probability_preserving_runtime_dry_run.py；新增 deterministic tests：apps/api/tests/unit/test_recommendation_replacement_probability_preserving_runtime_dry_run.py
扩展 runtime-shadow selector：apps/api/src/nutmeg/recommendations/replacement_short_odds_runtime_shadow.py 现在支持 max_model_edge_within_deficit / probability_preserving_model_edge 选择逻辑，并执行 rule constraints 中的 exclude_original_hit_harm，用于让 runtime replay 与 offline final-answer gate 约束一致
执行第一次 runtime dry run：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_runtime_dry_run_v1.json；status=runtime_dry_run_watchlist；changed_final_answer_count=14；final_answer_hit_delta_count=3；profit_loss_delta=11.76；harm_count_vs_original=1；失败原因是 runtime rule profile 尚未继承 offline gate 的 exclude_original_hit_harm=true，导致 1 个原始命中 final answer 被替换为 miss
修复 runtime constraint 后执行第二次 runtime dry run：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_runtime_dry_run_v2.json；report_key=historical_replacement_probability_preserving_runtime_dry_run:26e4b04e79b27100；status=runtime_dry_run_passed；generated_runtime_shadow_replay_report_key=historical_short_odds_runtime_shadow_replay:4f08bc08ae552cdc
runtime dry run v2 结果：final_answer_count=99；changed_final_answer_count=13；final_answer_hit_delta_count=4；profit_loss_delta=15.74；roi_delta=0.040358974358974356；harm_count_vs_original=0；final_hit_harm_count_vs_original=0；profit_loss_harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.011268524070761074
runtime proposal profile set：profile_version=v3_1_probability_preserving_13change_runtime_dry_run_v1；dry_run_only=true；production_recommendation_allowed=false；production_recommendation_changed=false；public_response_changed=false；rule_id=probability_preserving_runtime_dry_run:3b3f3500fb3873a9；profile_id=nearest_model_top_probability；allowed_competition_ids=ENG_CHAMPIONSHIP,ESP_SEGUNDA_DIVISION,FRA_LIGUE_2,GER_2_BUNDESLIGA,ITA_SERIE_B
runtime rule constraints：selection_rule=highest_candidate_hit_probability；shadow_selection_rule=nearest_model_top_probability；min_replacement_probability=0.45；min_replacement_decimal_odds=1.50；max_replacement_decimal_odds=2.20；min_candidate_hit_probability_delta_vs_model_top=-0.05；max_candidate_hit_probability_delta_vs_model_top=0.0；min_candidate_hit_probability_delta_vs_original=-0.025；exclude_original_hit_harm=true；max_harm_count_vs_original=0；max_final_hit_harm_count_vs_original=0；max_profit_loss_harm_count_vs_original=0
关键边界：runtime dry run 已经把 grid / cross-surface / admission / runtime replay 四类证据串起来，且 v2 与 offline no-harm 约束对齐；但该结果仍是 shadow-only，不进入 default/runtime profile，不改变用户推荐
阶段性结论：13-change probability-preserving branch 现在具备 runtime-style dry-run 证据；下一阶段应接入 broader quality gate / promotion review artifact，而不是直接发布生产路径
README 更新 runtime-proposal dry run、v1 watchlist 差异、v2 passed 指标与 no-production-change 结论；该能力属于“core recommendation quality / probability-preserving runtime proposal dry run / no-production-change”
```

V3.1-346 当前落地能力：

```text
按 V3.1-345 结论执行 probability-preserving promotion review artifact；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不写 default profile，不展示内部策略，不引入保证盈利表述
新增 promotion review CLI：nutmeg-recommendation-replacement-probability-preserving-promotion-review；输入 runtime dry-run report，生成 promotion review report 与 dry-run-only review profile；输出 production_recommendation_allowed=false、production_recommendation_changed=false、public_response_changed=false
新增模块：apps/api/src/nutmeg/recommendations/replacement_probability_preserving_promotion_review.py；新增 deterministic tests：apps/api/tests/unit/test_recommendation_replacement_probability_preserving_promotion_review.py
执行 promotion review：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_promotion_review_v1.json；report_key=historical_replacement_probability_preserving_promotion_review:9ebb08687bdba841；status=promotion_review_ready；promotion_review_allowed=true；production_recommendation_allowed=false；production_recommendation_changed=false；public_response_changed=false；blockers=[]；warnings=[]
source chain：source_runtime_dry_run_report_key=historical_replacement_probability_preserving_runtime_dry_run:26e4b04e79b27100；generated_runtime_shadow_replay_report_key=historical_short_odds_runtime_shadow_replay:4f08bc08ae552cdc；selected_candidate_key=replacement_probability_preserving_candidate:3b3f3500fb3873a9
review metrics：final_answer_count=99；changed_final_answer_count=13；final_answer_hit_delta_count=4；profit_loss_delta=15.74；roi_delta=0.040358974358974356；harm_count_vs_original=0；final_hit_harm_count_vs_original=0；profit_loss_harm_count_vs_original=0；average_hit_probability_delta_vs_original=-0.011268524070761074；active_surface_count=8；failed_surface_count=0；active_competition_fold_count=5；active_season_fold_count=5；active_rolling_fold_count=13；failed_fold_count=0
生成 review profile：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_promotion_review_profile_v1.json；profile_version=v3_1_probability_preserving_13change_promotion_review_v1；dry_run_only=true；promotion_review_allowed=true；production_recommendation_allowed=false；production_recommendation_changed=false；public_response_changed=false；rule_count=1
review profile rule：rule_id=probability_preserving_runtime_dry_run:3b3f3500fb3873a9；profile_id=nearest_model_top_probability；allowed_competition_ids=ENG_CHAMPIONSHIP,ESP_SEGUNDA_DIVISION,FRA_LIGUE_2,GER_2_BUNDESLIGA,ITA_SERIE_B；constraints include min_replacement_probability=0.45、max_replacement_decimal_odds=2.20、min_candidate_hit_probability_delta_vs_model_top=-0.05、min_candidate_hit_probability_delta_vs_original=-0.025、exclude_original_hit_harm=true、max_harm_count_vs_original=0、max_final_hit_harm_count_vs_original=0、max_profit_loss_harm_count_vs_original=0
关键边界：promotion_review_ready 表示“可以进入更高层治理评审”，不是 runtime activation；该 artifact 明确不允许 production recommendation，也不写默认 profile
阶段性结论：13-change probability-preserving branch 现在具备 grid / cross-surface / admission / runtime dry-run / promotion review 五段证据链；下一阶段应接入 broader benchmark quality gate 或构建 staged-only activation smoke，仍不直接上线
README 更新 promotion review report、review profile、source chain、metrics 与 no-production-change 结论；该能力属于“core recommendation quality / probability-preserving promotion review / no-production-change”
```

V3.1-347 当前落地能力：

```text
按 V3.1-346 结论实现 strategy-level promotion gate；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不写 default profile，不展示内部策略，不引入保证盈利表述
新增策略门禁 CLI：nutmeg-recommendation-strategy-promotion-gate；输入一个或多个 governed promotion review report，输出统一 ready/watchlist/blocked 状态；该门禁只用于内部发布治理，不启用生产推荐
新增模块：apps/api/src/nutmeg/recommendations/recommendation_strategy_promotion_gate.py；新增 deterministic tests：apps/api/tests/unit/test_recommendation_strategy_promotion_gate.py
执行 13-change strategy promotion gate：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_strategy_promotion_gate_v1.json；gate_key=recommendation_strategy_promotion_gate:58d3a07a29184a97；status=ready；strategy_gate_ready=true；production_recommendation_allowed=false；production_recommendation_changed=false；public_response_changed=false；blockers=[]；warnings=[]
source promotion review：historical_replacement_probability_preserving_promotion_review:9ebb08687bdba841；selected_candidate_key=replacement_probability_preserving_candidate:3b3f3500fb3873a9；allowed_competition_ids=ENG_CHAMPIONSHIP,ESP_SEGUNDA_DIVISION,FRA_LIGUE_2,GER_2_BUNDESLIGA,ITA_SERIE_B
gate metrics：total_final_answer_count=99；total_changed_final_answer_count=13；total_final_answer_hit_delta_count=4；total_profit_loss_delta=15.74；minimum_roi_delta=0.040358974358974356；total_harm_count_vs_original=0；total_final_hit_harm_count_vs_original=0；total_profit_loss_harm_count_vs_original=0；minimum_active_surface_count=8；total_failed_surface_count=0；minimum_active_competition_fold_count=5；minimum_active_season_fold_count=5；minimum_active_rolling_fold_count=13；total_failed_fold_count=0
关键边界：strategy_gate_ready 表示“内部可以进入 staged-only activation smoke 或 broader benchmark gate attachment”，不是 runtime activation；该 artifact 明确不允许 production recommendation，也不改变 public response
阶段性结论：13-change probability-preserving branch 现在具备 grid / cross-surface / admission / runtime dry-run / promotion review / strategy gate 六段证据链；下一阶段应构建 staged-only activation smoke 或把该 gate 作为 benchmark quality gate 输入，仍不直接上线
README 更新 strategy promotion gate report、metrics 与 no-production-change 结论；该能力属于“core recommendation quality / strategy-level promotion governance / no-production-change”
```

V3.1-348 当前落地能力：

```text
按 V3.1-347 结论实现 staged-only activation smoke；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不写 default profile，不展示内部策略，不引入保证盈利表述
新增 staged activation smoke CLI：nutmeg-recommendation-strategy-staged-activation-smoke；输入 strategy promotion gate report 和 dry-run-only review profile，验证 runtime-style rule profile 可被读取、隔离和输出 staged artifact；该 smoke 不启用生产推荐
新增模块：apps/api/src/nutmeg/recommendations/recommendation_strategy_staged_activation_smoke.py；新增 deterministic tests：apps/api/tests/unit/test_recommendation_strategy_staged_activation_smoke.py
执行 13-change staged activation smoke：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_staged_activation_smoke_v1.json；report_key=recommendation_strategy_staged_activation_smoke:ccb2bf3ae8bf0c29；status=staged_activation_ready；staged_activation_ready=true；default_profile_write_requested=false；default_profile_written=false；production_recommendation_allowed=false；production_recommendation_changed=false；public_response_changed=false；blockers=[]；warnings=[]
生成 staged profile：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_staged_activation_profile_v1.json；profile_version=v3_1_probability_preserving_13change_staged_activation_smoke_v1；staged_only=true；dry_run_only=true；short_odds_replacement_rules=1
source chain：source_strategy_gate_key=recommendation_strategy_promotion_gate:58d3a07a29184a97；source_promotion_review_report_keys=historical_replacement_probability_preserving_promotion_review:9ebb08687bdba841；selected_candidate_key=replacement_probability_preserving_candidate:3b3f3500fb3873a9
rule constraints：allowed_competition_ids=ENG_CHAMPIONSHIP,ESP_SEGUNDA_DIVISION,FRA_LIGUE_2,GER_2_BUNDESLIGA,ITA_SERIE_B；selection_rule=highest_candidate_hit_probability；shadow_selection_rule=nearest_model_top_probability；min_replacement_probability=0.45；max_replacement_decimal_odds=2.20；min_candidate_hit_probability_delta_vs_model_top=-0.05；min_candidate_hit_probability_delta_vs_original=-0.025；exclude_original_hit_harm=true；max_harm_count_vs_original=0；max_final_hit_harm_count_vs_original=0；max_profit_loss_harm_count_vs_original=0
smoke metrics：total_final_answer_count=99；total_changed_final_answer_count=13；total_final_answer_hit_delta_count=4；total_profit_loss_delta=15.74；minimum_roi_delta=0.040358974358974356；total_harm_count_vs_original=0；total_final_hit_harm_count_vs_original=0；total_profit_loss_harm_count_vs_original=0；minimum_active_surface_count=8；total_failed_surface_count=0；minimum_active_competition_fold_count=5；minimum_active_season_fold_count=5；minimum_active_rolling_fold_count=13；total_failed_fold_count=0
关键边界：staged_activation_ready 表示“可以被 staged runtime-style profile 读取和隔离”，不是 runtime activation；该 artifact 明确不写 default profile，不改变 public response，不暴露内部策略
阶段性结论：13-change probability-preserving branch 现在具备 grid / cross-surface / admission / runtime dry-run / promotion review / strategy gate / staged activation smoke 七段证据链；下一阶段应把 staged smoke 接入 broader benchmark quality gate 或做 default-path isolation check，仍不直接上线
README 更新 staged activation smoke report、staged profile、metrics 与 no-production-change 结论；该能力属于“core recommendation quality / staged-only activation governance / no-production-change”
```

V3.1-349 当前落地能力：

```text
按 V3.1-348 结论实现 default-path isolation check；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不写 default profile，不展示内部策略，不引入保证盈利表述
新增 default-path isolation CLI：nutmeg-recommendation-strategy-default-path-isolation；输入 staged activation smoke report、staged profile 和当前默认 competition profile，验证 staged profile 不被普通默认推荐路径读取，只有显式 internal opt-in 才能触发规则
新增模块：apps/api/src/nutmeg/recommendations/recommendation_strategy_default_path_isolation.py；新增 deterministic tests：apps/api/tests/unit/test_recommendation_strategy_default_path_isolation.py
执行 13-change default-path isolation：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_default_path_isolation_v1.json；report_key=recommendation_strategy_default_path_isolation:618686fa9967187f；status=isolated；default_path_isolated=true；blockers=[]；default_profile_written=false；production_recommendation_allowed=false；production_recommendation_changed=false；public_response_changed=false
默认路径验证：default_profile_path=configs/recommendations/competition_recommendation_profiles.json；default_profile_version=v3_1_competition_profiles_football_data_co_uk_2026_05_15_eng_championship_value_guard_v1；default_profile_without_short_odds_rules=true；default_adapter_status=disabled；default_adapter_selection_changed=false；default_adapter_default_path_changed=false；default_adapter_public_response_changed=false
显式 opt-in 验证：explicit_opt_in_adapter_status=applied；explicit_opt_in_selection_changed=true；explicit_opt_in_default_path_changed=false；explicit_opt_in_public_response_changed=false；source_rule_profile_version=v3_1_probability_preserving_13change_staged_activation_smoke_v1；rule_id=probability_preserving_runtime_dry_run:3b3f3500fb3873a9
staged scope：staged_profile_version=v3_1_probability_preserving_13change_staged_activation_smoke_v1；staged_profile_rule_count=1；staged_selected_rule_count=1；staged_allowed_competition_ids=ENG_CHAMPIONSHIP,ESP_SEGUNDA_DIVISION,FRA_LIGUE_2,GER_2_BUNDESLIGA,ITA_SERIE_B
关键边界：isolated 表示 staged profile 与普通默认路径已隔离，显式 opt-in 能被内部测试触发，但该结果仍不是 runtime activation；default adapter 的 disabled warning 是预期证据，不是失败
阶段性结论：13-change probability-preserving branch 现在具备 grid / cross-surface / admission / runtime dry-run / promotion review / strategy gate / staged activation smoke / default-path isolation 八段证据链；下一阶段应把 strategy gate、staged smoke、default isolation 接入 broader benchmark quality gate，仍不直接上线
README 更新 default-path isolation report、默认路径不变、显式 opt-in 可触发与 no-production-change 结论；该能力属于“core recommendation quality / default-path isolation governance / no-production-change”
```

V3.1-350 当前落地能力：

```text
按 V3.1-349 结论把 strategy promotion gate、staged activation smoke、default-path isolation 接入 Recommendation Benchmark Quality Gate；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不写 default profile，不展示内部策略，不引入保证盈利表述
扩展模块：apps/api/src/nutmeg/recommendations/benchmark_quality_gate.py 现在支持三份推荐策略治理报告的 report path、require flags、no-regression 阈值、默认路径隔离检查与 summary_json 输出
扩展周期 runner：apps/api/src/nutmeg/recommendations/benchmark_cycle.py 现在支持 gate-recommendation-strategy-* CLI 透传，并在 cycle summary 中保留 strategy gate、staged smoke 与 default-path isolation 状态，保证周期命令可以自动拦截破坏隔离或引入回撤的候选
新增 deterministic tests：apps/api/tests/unit/test_recommendation_benchmark_quality_gate.py 覆盖治理 bundle 通过、治理回撤被拦截、从 options 加载报告，以及 CLI 参数映射；apps/api/tests/unit/test_recommendation_benchmark_cycle.py 覆盖 cycle summary 与 gate 参数透传
执行真实 broader benchmark gate：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_benchmark_quality_gate_strategy_governance_v1.json；gate_key=recommendation_benchmark_quality_gate:all:any；status=passed；passed=true；failed_checks=[]；warnings=[]
strategy gate evidence：recommendation_strategy_promotion_gate_present=true；recommendation_strategy_promotion_gate_ready=true；final_answer_count=99；changed_final_answer_count=13；hit_delta_count=4；profit_loss_delta=15.74；minimum_roi_delta=0.040358974358974356；harm_count=0；final_hit_harm_count=0；profit_loss_harm_count=0
staged evidence：recommendation_strategy_staged_activation_smoke_present=true；recommendation_strategy_staged_activation_ready=true；recommendation_strategy_staged_rule_count=1；recommendation_strategy_staged_allowed_competition_count=5；default_profile_written=false；production_changed=false；public_response_changed=false
default-path evidence：recommendation_strategy_default_path_isolation_present=true；recommendation_strategy_default_path_isolated=true；default_adapter_status=disabled；default_adapter_selection_changed=false；explicit_opt_in_adapter_status=applied；explicit_opt_in_selection_changed=true；default_profile_written=false；production_changed=false；public_response_changed=false
关键边界：主 benchmark gate 现在可以自动拒绝破坏默认路径隔离、写入 default profile、改变 production/public response 或造成 final-hit/ROI/P&L 回撤的候选；但该通过结果仍只是内部治理证据，不代表 runtime activation 或生产发布
阶段性结论：13-change probability-preserving branch 已接入 broader benchmark quality gate，后续周期可以用同一门禁自动拦截候选回撤；下一阶段应继续做 staged runtime shadow cycle 或扩大真实历史样本，而不是直接上线默认推荐路径
README 更新 broader benchmark quality gate report、三份治理证据、no-production-change 与 default-path-isolated 结论；该能力属于“core recommendation quality / benchmark quality gate governance / no-production-change”
```

V3.1-351 当前落地能力：

```text
按 V3.1-350 结论把 recommendation strategy governance bundle 固化为 quality gate / benchmark cycle preset；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不写 default profile，不展示内部策略，不引入保证盈利表述
新增 quality gate preset：probability_preserving_13change_v1；该 preset 自动绑定 strategy promotion gate、staged activation smoke、default-path isolation 三份报告，并启用 no-regression / no-production-change / no-public-change / no-default-write / default-path-isolated 阈值
扩展模块：apps/api/src/nutmeg/recommendations/benchmark_quality_gate.py 新增 RECOMMENDATION_STRATEGY_GOVERNANCE_PRESETS 与 apply_recommendation_strategy_governance_preset；CLI 支持 --recommendation-strategy-governance-preset probability_preserving_13change_v1
扩展周期 runner：apps/api/src/nutmeg/recommendations/benchmark_cycle.py 支持 --gate-recommendation-strategy-governance-preset probability_preserving_13change_v1，并把 preset 名称纳入 cycle_key，便于区分普通 gate 与 strategy-governance gate
新增 deterministic tests：apps/api/tests/unit/test_recommendation_benchmark_quality_gate.py 覆盖 quality gate preset 参数映射；apps/api/tests/unit/test_recommendation_benchmark_cycle.py 覆盖 cycle preset 参数映射与 cycle_key
执行真实 preset gate：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_benchmark_quality_gate_strategy_governance_preset_v1.json；status=passed；passed=true；recommendation_strategy_governance_preset=probability_preserving_13change_v1；failed_checks=[]；warnings=[]
preset 证据结果：strategy_gate_ready=true；changed_final_answer_count=13；hit_delta_count=4；profit_loss_delta=15.74；staged_activation_ready=true；staged_allowed_competition_count=5；default_path_isolated=true；default_adapter_status=disabled
关键边界：preset 只是让周期质量门禁稳定引用内部治理证据，不代表 runtime activation；该 preset 默认仍要求 production/public/default path 不变
阶段性结论：后续 benchmark-cycle 可以用单个 --gate-recommendation-strategy-governance-preset 参数自动接入三件套治理门禁；下一阶段应运行 staged runtime shadow cycle / 扩大真实历史切片，而不是直接修改默认推荐路径
README 更新 preset 用法、真实 preset gate report 与 no-production-change 结论；该能力属于“core recommendation quality / benchmark cycle governance preset / no-production-change”
```

V3.1-352 当前落地能力：

```text
按 V3.1-351 结论继续推进 staged runtime shadow cycle；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不写 default profile，不展示内部策略，不引入保证盈利表述
新增 benchmark cycle preset：probability_preserving_13change_governance_v1；CLI 支持 --cycle-preset probability_preserving_13change_governance_v1
扩展模块：apps/api/src/nutmeg/recommendations/benchmark_cycle.py 新增 RECOMMENDATION_BENCHMARK_CYCLE_PRESETS 与 apply_recommendation_benchmark_cycle_preset；该 preset 自动套用 quality gate 的 probability_preserving_13change_v1 策略治理三件套
安全边界：cycle preset 会强制 run_gate=true、dry_run=true，并启用 core replay / chain integrity / successor-chain evaluation；默认 schedule name 会改为 probability-preserving-13change-governance，默认 cadence 会改为 once；非默认 schedule name/cadence 会被保留
新增 deterministic tests：apps/api/tests/unit/test_recommendation_benchmark_cycle.py 覆盖 cycle_preset 纳入 cycle_key、CLI preset 参数映射、dry-run/gated 安全边界，以及显式 schedule name/cadence 保留
README 更新 shadow cycle preset 用法与 no-production-change 说明；该能力属于“core recommendation quality / staged runtime shadow cycle preset / no-production-change”
阶段性结论：13-change probability-preserving 策略已经从分散证据、主 gate preset 推进到一键 benchmark-cycle shadow preset；下一阶段可以在不改默认推荐路径的前提下跑真实周期 smoke 或扩大真实历史切片
```

V3.1-353 当前落地能力：

```text
按 V3.1-352 结论把 staged runtime shadow cycle 往可审计 artifact 推进；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不写 default profile，不展示内部策略，不引入保证盈利表述
扩展模块：apps/api/src/nutmeg/recommendations/benchmark_cycle.py 新增 --output-path；benchmark cycle 现在可把完整 RecommendationBenchmarkCycleRunResult 写成本地 JSON artifact，并自动创建父目录
新增 deterministic tests：apps/api/tests/unit/test_recommendation_benchmark_cycle.py 覆盖 output artifact 写入、父目录创建、cycle_preset 摘要保留，以及 CLI output-path 参数解析
README 更新 shadow cycle preset 命令，示例包含 --output-path configs/recommendations/historical_reports/...benchmark_cycle_governance_preset_smoke_v1.json
执行真实 dry-run cycle smoke：configs/recommendations/historical_reports/football_data_co_uk_core_plus_expanded_a_leagues_candidate12_window4_probability_preserving_adjacent_threshold_13plus_benchmark_cycle_governance_preset_smoke_v1.json；cycle_key=recommendation_benchmark_cycle:probability-preserving-13change-governance:once:gate:recommendation_strategy_governance_preset:probability_preserving_13change_v1:cycle_preset:probability_preserving_13change_governance_v1；status=passed；gate_status=passed；benchmark_scenario_count=27；benchmark_completed_count=27；benchmark_failed_count=0；stored_report_id=14
真实 smoke 证据：recommendation_strategy_promotion_gate_ready=true；recommendation_strategy_staged_activation_ready=true；recommendation_strategy_default_path_isolated=true；failed_checks=[]；当前 warnings 仅为本地 24h 窗口候选不足 / core replay 无持久化推荐 run 的数据覆盖提示
关键边界：output-path 只是本地报告落盘，不等同于 DB cycle report save；真实数据库历史仍可继续用 --save-cycle-report，但本能力让 dry-run smoke 不依赖数据库写入也能留痕
阶段性结论：13-change probability-preserving 策略现在具备 gate preset、cycle preset、local cycle artifact 三层内部审计路径；下一阶段应解决当前短窗口候选不足的问题，把 cycle smoke 从“治理证据通过”推进到“真实候选/推荐 replay 也有覆盖”
```

V3.1-354 当前落地能力：

```text
按 V3.1-353 结论解决 cycle smoke 只看 scenario completed、不看真实候选覆盖的问题；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不写 default profile，不展示内部策略，不引入保证盈利表述
扩展 benchmark summary：apps/api/src/nutmeg/recommendations/benchmark_runner.py 现在累计 global_best_candidate_count 与 global_best_generated_option_count；global_best_selected_count 继续作为已选最终答案覆盖计数
扩展 benchmark quality gate：apps/api/src/nutmeg/recommendations/benchmark_quality_gate.py 新增 min_global_best_selected_count、min_global_best_candidate_count、min_global_best_generated_option_count，并在 summary_json 输出三个覆盖指标；CLI 支持 --min-global-best-selected-count / --min-global-best-candidate-count / --min-global-best-generated-option-count
扩展 benchmark cycle gate 透传：apps/api/src/nutmeg/recommendations/benchmark_cycle.py 支持 --gate-min-global-best-selected-count / --gate-min-global-best-candidate-count / --gate-min-global-best-generated-option-count；cycle summary 同步保留三个候选覆盖指标
cycle preset 强化：probability_preserving_13change_governance_v1 默认要求至少 1 个 selected global-best、1 个 evaluated candidate、1 个 generated option；因此短窗口无候选时不会再被误判为质量通过
新增 deterministic tests：apps/api/tests/unit/test_recommendation_benchmark_quality_gate.py 覆盖候选覆盖不足会被 gate 拦截、CLI 参数映射；apps/api/tests/unit/test_recommendation_benchmark_cycle.py 覆盖 cycle CLI 参数映射与 preset 默认覆盖阈值
执行本地 seed candidate coverage smoke：configs/recommendations/historical_reports/local_seed_probability_preserving_13change_benchmark_cycle_candidate_coverage_smoke_v1.json；run_at_utc=2026-05-12T00:00:00Z；status=passed；gate_status=passed；benchmark_scenario_count=27；benchmark_completed_count=27；global_best_selected_count=27；global_best_candidate_count=486；global_best_generated_option_count=27；failed_checks=[]
关键边界：该 smoke 仍是 dry-run，不持久化 recommendation_runs，不改变 default profile；当前唯一 warning 是 core_replay:no_recommendation_runs_for_core_replay_window，说明下一阶段要补 replay 持久化种子或专用 lifecycle replay fixture
阶段性结论：cycle gate 已从“场景跑完即可”升级为“必须真的产生推荐候选和答案”；下一阶段应补最小 persisted recommendation run / candidate pool seed，让 core replay 也具备非空覆盖
```

V3.1-355 当前落地能力：

```text
按 V3.1-354 结论补 core replay 的非空持久化覆盖；本轮不接实时 API/VPS、不做自动下注、不进入前端、不修改默认推荐路径，不写 default profile，不展示内部策略，不引入保证盈利表述
新增模块：apps/api/src/nutmeg/recommendations/benchmark_core_replay_seed.py；CLI 为 nutmeg-recommendation-benchmark-core-replay-seed；它先写 deterministic baseline fixture/prediction/odds/result，再用单一 replay seed budget 为每个 pass type / mode 生成 recommendation_runs 与 candidate pool snapshots，供 core replay 读取；完整预算矩阵仍由后续 benchmark cycle dry-run 评估，避免同一最终答案因不同预算重复写入 run_key
扩展 benchmark cycle：apps/api/src/nutmeg/recommendations/benchmark_cycle.py 新增显式 --commit-core-replay-seed、--core-replay-seed-profile、--no-core-replay-seed-reset；cycle summary 输出 core_replay_seed_requested / passed / profile / seed_budget / stored_run_count / expected_scenario_count；cycle_key 纳入 core_replay_seed profile/reset，seed 失败时即使 gate 通过也会让 cycle 失败
关键安全边界：cycle preset 仍保持 schedule dry_run=true；只有显式 --commit-core-replay-seed 才会写本地 deterministic seed recommendation runs；该能力只服务核心质量门禁，不改变默认推荐 profile、生产响应、公开响应或用户可见策略
新增 deterministic tests：apps/api/tests/unit/test_recommendation_benchmark_core_replay_seed.py 覆盖 baseline seed + committed benchmark matrix 映射、缺失 committed runs warning；apps/api/tests/unit/test_recommendation_benchmark_cycle.py 覆盖 seed-before-schedule、seed failure gate override、cycle key、CLI 参数映射
README 更新 core replay seed 用法，给出 probability_preserving_13change_governance_v1 本地 deterministic smoke 命令；该能力属于“core recommendation quality / benchmark cycle persisted replay seed / no-production-change”
阶段性结论：benchmark cycle 已具备候选覆盖门禁与显式 persisted replay seed；下一阶段应运行本地 seeded cycle smoke，确认 core_replay:no_recommendation_runs_for_core_replay_window 从治理周期 warning 中消失，并继续把质量判断放在最终答案准确性/ROI/回放可解释证据上
```

V3.1-356 当前落地能力：

```text
按 V3.1-355 的本地 seeded cycle smoke 目标继续推进；本轮仍不接实时 API/VPS、不做自动下注、不改默认推荐路径，不扩大前端，不恢复已搁置的冷门开发
修正 committed core replay seed 的覆盖口径：seed 阶段默认只取预算列表的第一个 seed_budget，为每个 pass type / mode 写一条 replay 所需的 recommendation_run 与 candidate pool snapshot；完整预算矩阵仍由 benchmark cycle dry-run 评估
原因：同一最终答案在不同预算档可能生成相同 global run_key；seed 阶段重复提交完整预算矩阵会触发 run_key 唯一约束冲突。将 seed 缩小为 replay readiness 覆盖后，既保留 core replay 的非空持久化样本，也避免把预算评估职责混入 seed 写入
新增/更新 tests：apps/api/tests/unit/test_recommendation_benchmark_core_replay_seed.py 覆盖多预算输入压缩为单一 seed_budget；apps/api/tests/unit/test_recommendation_benchmark_cycle.py 覆盖 cycle summary 暴露 core_replay_seed_budget
本地 deterministic smoke 结果：nutmeg-recommendation-benchmark-core-replay-seed 在 2026-05-12T00:00:00Z seed_budget=10.0，stored_run_count=9，expected_scenario_count=9，warnings=[]
本地 governance cycle 结果：probability_preserving_13change_governance_v1 + --commit-core-replay-seed status=passed，gate_status=passed，core_replay_seed_passed=true，core_replay_seed_stored_run_count=9，warnings=[]；此前的 core_replay:no_recommendation_runs_for_core_replay_window 已从该 smoke 中消失
阶段性结论：core recommendation benchmark cycle 现在具备“候选覆盖 + 持久 replay seed + 质量门禁”三件基础能力；下一阶段应继续围绕真实历史样本的最终答案命中率、ROI、校准和推荐生命周期 replay 做准确性提升，而不是扩张数据源/VPS/前端
```

V3.1-357 当前落地能力：

```text
按 V3.1-356 的阶段性结论继续推进核心准确性门禁；本轮不接新数据源/VPS、不动前端、不恢复冷门开发、不改变默认推荐路径，也不暴露内部策略给用户
benchmark_quality_gate 新增最终答案 replay 覆盖率门禁：RecommendationBenchmarkQualityGateOptions.min_final_hit_coverage_ratio；检查 latest.final_hit_sample_size / latest.completed_count，避免 benchmark 场景虽完成但缺少 settled final-answer replay 证据时被误判为质量通过
benchmark_cycle 的 probability_preserving_13change_governance_v1 preset 已强化为：min_core_replay_ready_ratio=1.0、min_final_hit_sample_size=1、min_final_hit_coverage_ratio=1.0；这要求本地/历史治理周期必须真的跑通 core replay，并具备最终答案 settled 样本
benchmark_cycle summary 透传核心 replay 质量指标：core_replay_ready_ratio、final_hit_sample_size、final_hit_coverage_ratio、final_hit_rate、average_core_replay_roi，方便后续阶段判断“是否真的有可评估最终答案”，而不是只看 gate passed
新增/更新 deterministic tests：benchmark_quality_gate 覆盖 final_hit_coverage_ratio 不足会被拦截与 CLI 参数映射；benchmark_cycle 覆盖 preset 默认阈值和 cycle summary 透传最终答案 replay 指标
本地 seeded governance cycle smoke：probability_preserving_13change_governance_v1 + --commit-core-replay-seed status=passed，gate_status=passed，core_replay_ready_ratio=1.0，final_hit_sample_size=27，final_hit_coverage_ratio=1.0，final_hit_rate=1.0，average_core_replay_roi=77.8756898803033，failed_checks=[]，warnings=[]
阶段性结论：quality gate 已从“有候选/有 run”继续升级为“必须有 settled final-answer replay 覆盖”；下一阶段应把这个口径迁移到真实历史样本窗口，继续看命中率、ROI、Brier/log-loss/ECE 与生命周期 successor 只计最终有效版本
```

V3.1-358 当前落地能力：

```text
按 V3.1-357 的下一阶段继续推进真实历史样本窗口；本轮不接新 API/VPS、不扩前端、不改默认推荐路径、不恢复冷门开发，也不改变用户可见推荐文案
historical_quality_gate 新增最终答案覆盖率门禁：HistoricalRecommendationSuiteQualityGateOptions.min_final_hit_coverage_ratio；检查 candidate_final_hit_sample_size / comparison_count，避免真实历史 backtest suite 只有少量 settled final-answer 样本时被误判为通过
historical_quality_gate summary 新增 candidate_final_hit_coverage_ratio；CLI 支持 --min-final-hit-coverage-ratio，可与既有 min_final_hit_sample_size、candidate_final_hit_rate、ROI、Brier/log-loss/ECE delta 门禁共同使用
benchmark_quality_gate 读取 historical suite evidence 时同步透传 historical_suite_candidate_final_hit_sample_size、historical_suite_candidate_final_hit_coverage_ratio、historical_suite_candidate_final_hit_rate、historical_suite_candidate_roi
benchmark_cycle summary 同步透传上述 historical suite final-answer 指标，便于周期性治理报告直接查看真实历史窗口是否具备可评估最终答案覆盖
新增/更新 deterministic tests：test_recommendation_historical_quality_gate.py 覆盖 final_hit_coverage_ratio 不足会被拦截和 CLI 参数映射；test_recommendation_benchmark_quality_gate.py 覆盖 benchmark gate 消费 historical suite final-answer 指标；test_recommendation_benchmark_cycle.py 覆盖 cycle summary 透传
真实历史轻量 smoke：nutmeg-recommendation-historical-suite-gate 使用 euro_2024_knockout_suite，pass_types=1x1,2x1，modes=single，candidate_fixture_limit=8，min_final_hit_coverage_ratio=1.0；结果 status=passed，comparison_count=1，candidate_final_hit_sample_size=1，candidate_final_hit_coverage_ratio=1.0，candidate_final_hit_rate=1.0，failed_checks=[]，warnings=[]
阶段性结论：最终答案 settled coverage 口径已进入真实 historical suite gate；下一阶段应继续让 broader historical windows 使用该口径，并把 successor lifecycle/effective-final-only 评估与 ROI/Brier/log-loss/ECE 一起纳入默认治理报告
```

V3.1-359 当前落地能力：

```text
按 V3.1-358 的阶段性结论补齐 broader historical window 的 final-answer coverage 证据；本轮不接新 API/VPS、不动 zeus、不改默认推荐路径、不恢复冷门开发，也不改变用户可见推荐文案
执行 210-slice expanded A-leagues rolling-window full-matrix historical suite gate：pass_types=1x1-8x1，modes=single,multiple，candidate_fixture_limit=12，max_candidates_per_fixture=3，scenario_candidate_fixture_buffer=4，min_final_hit_coverage_ratio=1.0
正式 artifact：configs/recommendations/historical_reports/local_expanded_a_leagues_rolling_window_full_matrix_final_hit_coverage_gate_smoke_v1.json
结果：status=passed；suite_status=improved；slice_count=210；comparison_count=210；candidate_final_hit_sample_size=210；candidate_final_hit_coverage_ratio=1.0；failed_checks=[]；warnings=[]
核心指标：candidate_final_hit_rate=0.6952380952380952；candidate_roi=0.027545424836601308；candidate_profit_loss=16.8578；candidate_brier_score=0.19043919867207867；candidate_log_loss=0.5617116316540536；candidate_mean_calibration_error=0.4029302281363587
相对 baseline：final_hit_rate_delta=0.023809523809523836；roi_delta=0.009297138232239932；profit_loss_delta=5.142399999999997；brier_score_delta=-0.005192673386803265；log_loss_delta=-0.011253906759272847；mean_calibration_error_delta=-0.005715658363388776
边界说明：同一轮先验证了 2x1-only 参数组合会遍历 210 个切片但不产生 completed final-answer 样本，因此不作为正式证据保留；正式 smoke 使用系统真实最终答案仲裁路径的 full-matrix 参数
阶段性结论：真实宽窗口已经具备 210/210 settled final-answer coverage，当前核心推荐路径可被有效评估；下一阶段应继续推进 successor lifecycle/effective-final-only 与 broader historical suite evidence 的联动门禁，而不是扩张 VPS/数据源/前端
```

V3.1-360 当前落地能力：

```text
按 V3.1-359 的下一阶段推进 successor lifecycle / effective-final-only 与 broader historical gate 的联动；本轮不接新 API/VPS、不动 zeus、不改默认推荐路径、不恢复冷门开发，也不改变用户可见推荐文案
historical_quality_gate 新增 direct successor-chain evaluation evidence：CLI 支持 --successor-chain-evaluation-report-path、--require-successor-chain-evaluation、--min-successor-effective-leaf-count、--min-successor-active-edge-count、--max-successor-critical-issue-count、--max-successor-ambiguous-source-count、--max-successor-source-status-sync-required-count
historical suite summary 新增 successor_chain_evaluation_present / passed、successor_effective_final_only_ready、successor_effective_leaf_count、successor_active_edge_count、successor_critical_issue_count、successor_ambiguous_source_count、successor_source_status_sync_required_count；用于把“源推荐 -> successor 推荐只评估最终有效 leaf run”的证据接入真实历史宽窗口门禁
benchmark_quality_gate 新增 historical-suite successor-chain evidence 检查和摘要透传；benchmark_cycle 新增 gate 参数透传和 cycle summary 字段，后续周期可要求 attached historical suite 同时具备 final-hit coverage 与 effective-final-only successor evidence
新增/更新 deterministic tests：test_recommendation_historical_quality_gate.py 覆盖 missing successor evidence 被拦截、attached evidence 通过、CLI 参数映射；test_recommendation_benchmark_quality_gate.py 覆盖 historical suite successor evidence 消费与缺失拦截；test_recommendation_benchmark_cycle.py 覆盖 gate 参数透传
真实联动 smoke：configs/recommendations/historical_reports/local_expanded_a_leagues_rolling_window_full_matrix_successor_effective_final_only_gate_smoke_v1.json；status=passed；suite_status=improved；slice_count=210；comparison_count=210；candidate_final_hit_sample_size=210；candidate_final_hit_coverage_ratio=1.0；failed_checks=[]；warnings=[]
真实联动 smoke 核心指标：candidate_final_hit_rate=0.6952380952380952；candidate_roi=0.027545424836601308；candidate_profit_loss=16.8578；successor_chain_evaluation_present=true；successor_chain_evaluation_passed=true；successor_effective_final_only_ready=true；successor_effective_leaf_count=1；successor_active_edge_count=1；successor_critical_issue_count=0；successor_ambiguous_source_count=0；successor_source_status_sync_required_count=0
benchmark-gate consumption smoke：configs/recommendations/historical_reports/local_expanded_a_leagues_rolling_window_full_matrix_successor_effective_final_only_benchmark_gate_smoke_v1.json；status=passed；historical_suite_quality_gate_passed=true；historical_suite_successor_chain_evaluation_passed=true；historical_suite_successor_effective_final_only_ready=true；failed_checks=[]；warnings=[]
阶段性结论：broader historical gate 已能同时约束真实历史最终答案覆盖率和 successor effective-final-only 生命周期证据；下一阶段应把这组 evidence 接进常用 benchmark cycle preset 或扩大到 core+expanded multi-manifest，而不是继续扩张非核心功能
```

V3.1-361 当前落地能力：

```text
按 V3.1-360 的阶段性结论把 broader historical successor effective-final-only evidence 接入常用 benchmark cycle preset；本轮不接新 API/VPS、不动 zeus、不改默认推荐路径、不恢复冷门开发，也不改变用户可见推荐文案
benchmark_quality_gate 新增 historical-suite final-hit coverage 显式阈值：min_historical_suite_candidate_final_hit_sample_size 与 min_historical_suite_candidate_final_hit_coverage_ratio；避免 benchmark gate 只透传 historical-suite final-hit 字段但不检查覆盖率
benchmark_cycle 的 probability_preserving_13change_governance_v1 preset 现在默认绑定 configs/recommendations/historical_reports/local_expanded_a_leagues_rolling_window_full_matrix_successor_effective_final_only_gate_smoke_v1.json，除非调用方显式传入另一个 historical suite quality gate report path
cycle preset 默认要求：historical_suite_quality_gate_present=true；slice_count>=210；comparison_count>=210；historical_suite_candidate_final_hit_sample_size>=210；historical_suite_candidate_final_hit_coverage_ratio>=1.0；successor_chain_evaluation_present=true；successor_effective_leaf_count>=1；successor_active_edge_count>=1；critical_issue_count=0；ambiguous_source_count=0；source_status_sync_required_count=0
更新 CLI：benchmark-gate 支持 --min-historical-suite-candidate-final-hit-sample-size / --min-historical-suite-candidate-final-hit-coverage-ratio；benchmark-cycle 支持对应 --gate-* 参数
新增/更新 deterministic tests：test_recommendation_benchmark_quality_gate.py 覆盖 historical-suite final-hit coverage 不足被拦截与 CLI 参数映射；test_recommendation_benchmark_cycle.py 覆盖 cycle preset 默认 successor/final-hit historical-suite 阈值与 CLI 参数映射
真实 preset cycle smoke：configs/recommendations/historical_reports/local_seed_probability_preserving_13change_benchmark_cycle_successor_effective_final_only_preset_smoke_v1.json；status=passed；gate_status=passed；core_replay_seed_passed=true；core_replay_ready_ratio=1.0；final_hit_sample_size=27；final_hit_coverage_ratio=1.0；historical_suite_quality_gate_passed=true；historical_suite_slice_count=210；historical_suite_candidate_final_hit_sample_size=210；historical_suite_candidate_final_hit_coverage_ratio=1.0；historical_suite_successor_chain_evaluation_passed=true；historical_suite_successor_effective_final_only_ready=true；gate_failed_checks=[]
阶段性结论：常用 governance cycle preset 已具备“本地 core replay coverage + broader historical 210/210 final-hit coverage + successor effective-final-only lifecycle evidence”的组合门禁；下一阶段可扩大到 core+expanded multi-manifest 或继续寻找不降低命中率/ROI/校准的质量函数
```

V3.1-362 当前落地能力：

```text
按 V3.1-361 的下一阶段把默认 governance cycle preset 从 expanded-only 210-slice 门禁升级为 core+expanded multi-manifest 240-slice 门禁；本轮不接新 API/VPS、不动 zeus、不改生产推荐 profile、不恢复冷门开发，也不改变用户可见推荐文案
生成 core+expanded historical successor effective-final-only gate：configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_full_matrix_successor_effective_final_only_gate_smoke_v1.json；manifest=football_data_co_uk_core_5_seasons_suite + football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1；status=passed；suite_status=improved；slice_count=240；comparison_count=240；candidate_final_hit_sample_size=240；candidate_final_hit_coverage_ratio=1.0；failed_checks=[]；warnings=[]
真实 multi-manifest 核心指标：candidate_final_hit_rate=0.7041666666666667；candidate_roi=0.0173867918452381；candidate_profit_loss=11.683924120000004；successor_chain_evaluation_passed=true；successor_effective_final_only_ready=true；successor_effective_leaf_count=1；successor_active_edge_count=1；successor_critical_issue_count=0；successor_ambiguous_source_count=0；successor_source_status_sync_required_count=0
benchmark_quality_gate consumption smoke：configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_successor_effective_final_only_benchmark_gate_smoke_v1.json；status=passed；historical_suite_quality_gate_passed=true；historical_suite_slice_count=240；historical_suite_candidate_final_hit_sample_size=240；historical_suite_successor_chain_evaluation_passed=true；failed_checks=[]；warnings=[]
benchmark_cycle 的 probability_preserving_13change_governance_v1 preset 现在默认绑定 configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_full_matrix_successor_effective_final_only_gate_smoke_v1.json，默认要求 slice_count/comparison_count/final_hit_sample_size >= 240，coverage=1.0，并继续要求 successor effective-final-only evidence 通过
真实 preset cycle smoke：configs/recommendations/historical_reports/local_seed_probability_preserving_13change_benchmark_cycle_core_plus_expanded_successor_effective_final_only_preset_smoke_v1.json；status=passed；gate_status=passed；core_replay_seed_passed=true；core_replay_ready_ratio=1.0；final_hit_sample_size=27；final_hit_coverage_ratio=1.0；historical_suite_quality_gate_passed=true；historical_suite_slice_count=240；historical_suite_candidate_final_hit_sample_size=240；historical_suite_candidate_final_hit_coverage_ratio=1.0；historical_suite_successor_chain_evaluation_passed=true；historical_suite_successor_effective_final_only_ready=true；gate_failed_checks=[]
阶段性结论：常用治理周期已从 expanded-only 证据升级为 core+expanded 240/240 settled final-answer coverage + successor effective-final-only lifecycle evidence；下一阶段应继续做核心准确性提升的可证伪实验，例如分联赛/赔率段质量函数、预算内最优答案裁剪与最终答案仲裁质量，而不是扩张非核心展示、VPS 或数据源集成
```

V3.1-363 当前落地能力：

```text
按 V3.1-362 的阶段性结论推进预算内最优答案裁剪与最终答案仲裁质量；本轮不接新 API/VPS、不动 zeus、不改生产推荐 profile、不恢复冷门专项，也不改变用户可见推荐文案
final_answer_arbitrator 新增 budget_adjustment_quality 与 budget_adjustment_penalty：当 multiple optimizer 的 explanation_json 带有 budget_adjustment 时，仲裁器会按 optimized/original quality retention、atomic bet retention 和 warning_codes 计算有限惩罚；自然预算内或未裁剪选项 penalty=0
reason_codes 新增 budget_adjustment_applied、budget_adjustment_quality_penalty_applied、budget_adjustment_warning；这些属于内部仲裁证据，不需要前端向用户展示策略
新增 deterministic test：test_final_answer_arbitrator_penalizes_heavily_trimmed_budget_multiple，覆盖严重裁剪复式会在同等核心指标附近输给稳定 single parlay，并记录 budget adjustment score components/reason codes
生成当前代码口径的 core+expanded historical gate：configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_adjusted_arbitrator_successor_effective_final_only_gate_smoke_v1.json；status=passed；slice_count=240；comparison_count=240；candidate_final_hit_sample_size=240；candidate_final_hit_coverage_ratio=1.0；candidate_final_hit_rate=0.7041666666666667；candidate_roi=0.0173867918452381；candidate_profit_loss=11.683924120000004；successor_chain_evaluation_passed=true；warnings=[]
新旧 core+expanded gate byte-for-byte 相同，说明预算裁剪惩罚没有扰动当前 240 个历史最终答案；它只在未来出现“严重裁剪后才合规”的复式候选时提供降权保护
benchmark_quality_gate consumption smoke：configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_adjusted_arbitrator_benchmark_gate_smoke_v1.json；status=passed；historical_suite_quality_gate_passed=true；historical_suite_slice_count=240；historical_suite_candidate_final_hit_sample_size=240；failed_checks=[]；warnings=[]
benchmark_cycle 的 probability_preserving_13change_governance_v1 preset 现在默认绑定 configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_adjusted_arbitrator_successor_effective_final_only_gate_smoke_v1.json，保持 240/240 coverage + successor effective-final-only evidence 门禁
真实 preset cycle smoke：configs/recommendations/historical_reports/local_seed_probability_preserving_13change_benchmark_cycle_budget_adjusted_arbitrator_preset_smoke_v1.json；status=passed；gate_status=passed；core_replay_seed_passed=true；core_replay_ready_ratio=1.0；final_hit_sample_size=27；final_hit_coverage_ratio=1.0；historical_suite_quality_gate_passed=true；historical_suite_slice_count=240；historical_suite_candidate_final_hit_sample_size=240；gate_failed_checks=[]
阶段性结论：最终答案仲裁器现在能区分“天然预算内”和“强裁剪后预算内”的复式答案；当前历史集未受扰动，下一阶段应继续做可证伪的核心准确性实验，例如预算档稳定性审计、不同预算下的最终答案一致性/收益变化，以及小范围 selection-value 仲裁信号
```

V3.1-364 当前落地能力：

```text
按 V3.1-363 的阶段性结论落地预算档稳定性审计；本轮不接新 API/VPS、不动 zeus、不改生产推荐 profile、不恢复冷门专项，也不改变用户可见推荐文案
新增 historical_budget_stability_audit 离线治理工具：复用 historical backtest 最终答案路径，对同一组历史切片在多个预算档下重放推荐，比较最终答案 signature、命中变化、收益变化、ROI 变化、stake 变化、预算裁剪证据与 slice 级 reason_codes
CLI 入口：nutmeg-recommendation-budget-stability-audit，支持 --suite-manifest、--budgets、--reference-budget、--pass-types、--modes、--candidate-fixture-limit、--max-candidates-per-fixture、--scenario-candidate-fixture-buffer、--derive-market-context-signals 与 --output-path
新增 deterministic test：test_budget_stability_audit_detects_harmful_low_budget_change，覆盖低预算导致最终答案变化、命中受损、profit_loss 下降、budget_adjustment 被识别、heavy_budget_adjustment 被标记；同时覆盖 CLI args 到 options 的映射
轻量真实 smoke：configs/recommendations/historical_reports/local_euro_2024_budget_stability_audit_smoke_v1.json；slice_count=1；budgets=4,8；两档 final_hit_rate=1.0；signature_changed_count=0；warnings=[]
核心真实 smoke：configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_stability_audit_smoke_v1.json；manifest=football_data_co_uk_core_5_seasons_suite + football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1；slice_count=240；budgets=10,20；reference_budget=20；warnings=[]
预算 10 结果：final_answer_count=240；final_hit_count=168；final_hit_rate=0.7；roi=0.013320941695906441；profit_loss=9.111524120000006；total_stake=684.0；multiple_final_answer_count=34
预算 20 结果：final_answer_count=240；final_hit_count=169；final_hit_rate=0.7041666666666667；roi=0.0173867918452381；profit_loss=11.683924120000004；total_stake=672.0；multiple_final_answer_count=32
10 vs 20 comparison：comparable_count=240；signature_changed_count=4；signature_change_rate=0.016666666666666666；harmful_change_count=2；beneficial_change_count=2；hit_delta_count=-1；profit_loss_delta=-2.572399999999998；roi_delta=-0.004065850149331659
阶段性结论：当前 240-slice core+expanded 样本上，预算 10 与 20 的最终答案整体稳定，但低预算档有轻微命中率/ROI 损失，且 4 个变化样本集中暴露了预算约束与 single/multiple 仲裁之间的边界；下一阶段应把预算稳定性审计升级为质量门禁/周期报告字段，并针对有害变化样本做仲裁修正实验
```

V3.1-365 当前落地能力：

```text
按 V3.1-364 的阶段性结论，把预算稳定性审计从离线报告升级为 benchmark quality gate / benchmark cycle 可消费的治理证据；本轮不接新 API/VPS、不动 zeus、不改生产推荐 profile、不恢复冷门专项，也不改变用户可见推荐文案
benchmark_quality_gate 新增 budget stability audit evidence：支持 --budget-stability-audit-report-path、--require-budget-stability-audit、--min-budget-stability-slice-count、--min-budget-stability-comparable-count、--max-budget-stability-signature-change-rate、--max-budget-stability-harmful-change-count、--min-budget-stability-hit-delta-count、--min-budget-stability-profit-loss-delta、--min-budget-stability-roi-delta、--max-budget-stability-warning-count
quality gate summary 新增 budget_stability_audit_present/key/status、budget_stability_slice_count、budgets、reference_budget、comparable_count、signature_changed_count/rate、harmful/beneficial_change_count、hit_delta_count、profit_loss_delta、roi_delta、warning_count；用于让周期报告直接判断不同预算档下最终答案是否被打散
benchmark_cycle 的 probability_preserving_13change_governance_v1 preset 默认绑定 configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_stability_audit_smoke_v1.json，并要求 slice_count>=240、comparable_count>=240、signature_change_rate<=0.02、harmful_change_count<=2、hit_delta_count>=-1、roi_delta>=-0.005、warning_count=0
新增/更新 deterministic tests：test_recommendation_benchmark_quality_gate.py 覆盖 budget stability evidence 消费、缺失拦截、阈值失败、CLI 参数映射；test_recommendation_benchmark_cycle.py 覆盖 cycle summary 透传和 preset 默认 budget stability gate 阈值
真实 consumption smoke：configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_stability_benchmark_gate_smoke_v1.json；status=passed；passed=true；failed_checks=[]；warnings=[]
smoke 关键证据：historical_suite_quality_gate_passed=true；budget_stability_audit_present=true；budget_stability_slice_count=240；budget_stability_signature_change_rate=0.016666666666666666；budget_stability_harmful_change_count=2；budget_stability_hit_delta_count=-1；budget_stability_roi_delta=-0.004065850149331659
阶段性结论：预算档稳定性现在已经进入默认治理周期的质量门禁；下一阶段应针对 240-slice 审计暴露的 2 个 harmful change 做最终答案仲裁修正实验，但任何修改都必须先通过当前 budget stability gate，防止为了个别样本牺牲整体稳定性
```

V3.1-366 当前落地能力：

```text
按 V3.1-365 的阶段性结论，针对预算稳定性 audit 暴露的 harmful change 做最终答案仲裁修正实验；本轮不接新 API/VPS、不动 zeus、不改用户可见推荐文案、不恢复冷门专项，也不引入自动投注
核心修正 1：multiple optimizer 在“无需预算裁剪”的自然预算内路径、fixture replacement 路径和补保护选项路径中保留 max_budget/within_budget 评估上下文，避免最终仲裁器与持久化层看到 max_budget=None
核心修正 2：final_answer_arbitrator 将 budget_efficiency 调整为二元硬约束语义：预算内为 1.0，预算外为 0.0；最终答案不再因为“预算占用率”被重复惩罚，复式的注额暴露继续由 stake_discipline 与 rule_valid/within_budget 控制
撤回了一版过强的 budget_stake_pressure_penalty 实验：单样本能压住 harmful case，但完整 240-slice audit 显示会误杀预算 10 下的有价值复式，导致 ROI/收益显著下滑，因此未纳入主线
新增/更新 deterministic tests：test_recommendation_optimizer.py 覆盖自然预算内 multiple 与 replacement multiple 均保留 max_budget；test_recommendation_final_arbitrator.py 覆盖预算内 final budget_efficiency 为二元语义，不按 max_budget ratio 干扰排序
新预算稳定性真实 smoke：configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_stability_budget_context_binary_smoke_v1.json；manifest=football_data_co_uk_core_5_seasons_suite + football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1；slice_count=240；budgets=10,20；reference_budget=20；warnings=[]
预算 10 与预算 20 结果完全一致：final_answer_count=240；final_hit_count=168；final_hit_rate=0.7；roi=-0.002381495315315313；profit_loss=-1.5860758799999983；total_stake=666.0；multiple_final_answer_count=31
10 vs 20 comparison：comparable_count=240；signature_changed_count=0；signature_change_rate=0.0；harmful_change_count=0；beneficial_change_count=0；hit_delta_count=0；profit_loss_delta=0.0；roi_delta=0.0；stake_delta=0.0
benchmark-gate consumption smoke：configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_stability_budget_context_binary_benchmark_gate_smoke_v1.json；status=passed；passed=true；failed_checks=[]；warnings=[]
benchmark_cycle 的 probability_preserving_13change_governance_v1 preset 默认绑定 budget_context_binary smoke，并把 budget stability 默认阈值收紧为 signature_change_rate<=0.0、harmful_change_count<=0、hit_delta_count>=0、profit_loss_delta>=0.0、roi_delta>=0.0、warning_count=0
阶段性结论：预算 10/20 的最终答案现在具备严格一致性，原先 2 个 harmful budget change 已消除；但新口径的绝对 ROI/profit 低于 V3.1-364 的旧 budget audit，因此下一阶段重点不是继续加稳定性惩罚，而是在保持 signature_change=0/harmful=0 的前提下恢复或提升绝对 ROI/profit
```

V3.1-367 当前落地能力：

```text
按 V3.1-366 的阶段性结论，在不放松预算稳定性门禁的前提下恢复绝对 ROI/profit；本轮不接新 API/VPS、不动 zeus、不改用户可见推荐文案、不恢复冷门专项，也不引入自动投注
诊断结论：旧 budget ratio、stake-neutral、广义 multiple bonus、hit/ROI priority 等方向会降低 240-slice ROI；有效信号集中在极小的 multiple coverage tie-breaker，只在规则有效、预算内且复式 atomic bets > 1 时提供 0.003 的仲裁加分
核心修正：final_answer_arbitrator 新增 multiple_coverage_adjustment score component 与 reason code；它不是展示给普通用户的策略标签，只作为内部 tie-breaker，避免在预算/风险已合格的复式候选与单式候选之间过度偏向单式
新增 deterministic test：test_final_answer_arbitrator_applies_tiny_multiple_coverage_tie_breaker，覆盖复式覆盖度加分、score component 与 reason code
新预算稳定性真实 smoke：configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_stability_multiple_tie_breaker_smoke_v1.json；manifest=football_data_co_uk_core_5_seasons_suite + football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1；slice_count=240；budgets=10,20；reference_budget=20；warnings=[]
预算 10 与预算 20 结果完全一致：final_answer_count=240；final_hit_count=170；final_hit_rate=0.7083333333333334；roi=0.03886684347578348；profit_loss=27.284524120000004；total_stake=702.0；multiple_final_answer_count=37
10 vs 20 comparison：comparable_count=240；signature_changed_count=0；signature_change_rate=0.0；harmful_change_count=0；beneficial_change_count=0；hit_delta_count=0；profit_loss_delta=0.0；roi_delta=0.0；stake_delta=0.0
benchmark-gate consumption smoke：configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_budget_stability_multiple_tie_breaker_benchmark_gate_smoke_v1.json；status=passed；passed=true；failed_checks=[]；warnings=[]
benchmark_cycle 的 probability_preserving_13change_governance_v1 preset 默认绑定 multiple_tie_breaker smoke，并继续执行 signature_change_rate<=0.0、harmful_change_count<=0、hit_delta_count>=0、profit_loss_delta>=0.0、roi_delta>=0.0、warning_count=0 的严格预算稳定性门禁
阶段性结论：本轮把 V3.1-366 的严格预算一致性保住，同时把 240-slice 绝对结果从 final_hit_rate=0.7/ROI=-0.002381/profit=-1.586 提升到 final_hit_rate=0.708333/ROI=0.038867/profit=27.285；下一阶段继续做核心准确性提升，应优先寻找可证伪的分联赛/赔率段质量函数与让球玩法纳入最终答案搜索，而不是扩张前端展示或数据源集成
```

V3.1-368 当前落地能力：

```text
按 V3.1-367 的阶段性结论，把让球玩法纳入最终答案搜索与历史回放结算主线；本轮不接新 API/VPS、不动 zeus、不改用户可见推荐文案、不恢复冷门专项，也不引入自动投注
核心修正 1：parlay rule engine 的 max_legs_by_market 增加 european_handicap_1x2=8，使欧洲三项让球与中国竞彩让球胜平负一样可进入 2x1-8x1 过关规则校验
核心修正 2：historical_backtest 结算支持 cn_handicap_1x2 与 european_handicap_1x2；根据 final score + normalized integer line 计算 handicap_home_win / handicap_draw / handicap_away_win，避免让球候选在真实回放中被误判为未命中
核心修正 3：historical recommendation candidates 的 candidate_id 加入 line/side，handicap_home_win / handicap_away_win 纳入相关性 key，handicap_draw 作为 handicap draw exposure 记录，便于后续多盘口/让球候选诊断
新增 deterministic tests：test_global_planner_can_select_handicap_final_answer_candidates 覆盖最终答案 planner 可选择中国/欧洲让球候选且规则有效；test_historical_backtest_settles_cn_and_european_handicap_candidates 覆盖两类让球候选的历史赛果结算命中与实际返还
阶段性结论：让球玩法不再只是 market resolver/API 展示能力，而是能进入最终答案候选、串关规则校验和历史 settled replay；下一阶段应把真实历史样本中的 handicap odds/probability coverage 接入质量审计，先做 shadow/backtest，不直接改变默认生产推荐 profile
```

V3.1-369 当前落地能力：

```text
按 V3.1-368 的阶段性结论，新增让球覆盖率审计与 shadow backtest；本轮不接新 API/VPS、不动 zeus、不改默认生产推荐 profile、不恢复冷门专项，也不引入自动投注
新增模块：apps/api/src/nutmeg/recommendations/historical_handicap_coverage_audit.py；CLI 为 nutmeg-recommendation-handicap-coverage-audit
审计能力：按 suite manifest 或 slice path 读取历史样本，统计 1X2 完整覆盖、cn_handicap_1x2 / european_handicap_1x2 预测数、可结算整数 line 候选数、让球 fixture 覆盖率、完整三项让球 line 覆盖率，并执行 1x2-only vs 1x2+handicap 的 shadow final-answer replay
新增 deterministic tests：test_recommendation_handicap_coverage_audit.py 覆盖让球候选能改变 shadow 最终答案并提升命中、无让球候选时报告 coverage warning、CLI 写报告和参数映射
真实审计报告：configs/recommendations/historical_reports/local_core_plus_expanded_a_leagues_handicap_coverage_shadow_audit_v1.json；输入为 football_data_co_uk_core_5_seasons_suite + football_data_co_uk_expanded_a_leagues_rolling_window_suite_v1；pass_types=1x1-8x1；modes=single,multiple；candidate_fixture_limit=12；max_candidates_per_fixture=3；scenario_candidate_fixture_buffer=4；derive_market_context_signals=true
真实覆盖结论：slice_count=240；fixture_count=13258；prediction_count=39774；handicap_prediction_count=0；eligible_handicap_prediction_count=0；handicap_fixture_count=0；complete_handicap_fixture_count=0；handicap_fixture_coverage=0.0
真实 shadow 结论：baseline_final_answer_count=240；candidate_final_answer_count=240；changed_final_answer_count=0；candidate_handicap_final_answer_count=0；final_hit_delta_count=0；profit_loss_delta=0.0；warnings 包含 no_handicap_candidates_available / no_handicap_final_answers
阶段性结论：让球推荐路径已具备工程闭环，但当前 football-data.co.uk core+expanded 历史样本没有让球赔率/概率候选，因此不能用这批样本判断让球策略有效性；下一阶段如继续让球主线，应先接入或构建含历史让球 odds/probabilities 的样本，再做 shadow admission，而不是调整仲裁权重
```

V3.1-370 当前落地能力：

```text
按 V3.1-369 的阶段性结论，补齐历史让球赔率/概率导入契约；本轮不接新 API/VPS、不动 zeus、不改默认生产推荐 profile、不恢复冷门专项，也不引入自动投注
新增模块：apps/api/src/nutmeg/recommendations/historical_handicap_odds_importer.py；CLI 为 nutmeg-recommendation-historical-handicap-odds-import
导入能力：从 CSV 读取 fixture_id、market_type、integer line、outcome、decimal_odds，可选 explicit probability / market_probability / provider / bookmaker / snapshot_time_utc / metadata_json；支持 cn_handicap_1x2 与 european_handicap_1x2
标准化规则：home/draw/away 统一转换为 handicap_home_win / handicap_draw / handicap_away_win；默认要求每个 fixture+market+line 具备完整三项结果，默认只接受整数 line，避免导入后无法被历史结算器正确 settled replay
概率规则：若 CSV 提供 explicit probability，则以 explicit probability 作为模型侧概率；若未提供，则从 decimal odds 计算 raw implied probability 与 no-vig probability，并将 no-vig probability 作为 baseline probability；metadata 记录 raw/no-vig/overround/probability_source，便于后续错误归因
接入方式：导入器输出 enriched HistoricalRecommendationSlice，直接复用现有 historical_backtest、handicap_coverage_audit、final-answer shadow replay，不绕过既有推荐生命周期
新增 deterministic tests：test_recommendation_historical_handicap_odds_importer.py 覆盖完整整数让球 line 导入后进入 coverage audit/final-answer shadow、缺失三项结果时跳过并报警、CLI 写 enriched slice 与参数映射
阶段性结论：让球主线从“系统能审计缺口”推进到“拿到历史让球 odds/probability 后能立即进入回测闭环”；下一阶段应优先拿一小批真实历史让球样本跑 import -> coverage audit -> shadow gate，若仍无数据，再切回 1X2 核心质量函数优化
```

V3.1-371 当前落地能力：

```text
按用户确认“需要付费历史让球数据时再提示”的要求，先使用本地免费 football-data.co.uk 历史 CSV 中已存在的亚洲让球字段；本轮不购买数据、不接 VPS、不动 zeus、不改变用户可见最终答案策略
新增模块：apps/api/src/nutmeg/recommendations/football_data_co_uk_asian_handicap_coverage.py；CLI 为 nutmeg-recommendation-football-data-co-uk-asian-handicap-coverage
审计能力：按文件或目录读取 football-data.co.uk CSV，解析 AHh/AHCh 盘口线、Avg/B365/Max/P/BFE 开盘与收盘 AHH/AHA 两项赔率，计算 home_cover/away_cover no-vig probability、overround、line_delta、line_changed，并输出 source/competition/season 覆盖统计
特征契约：asian_handicap_odds_movements_from_row 可把单行亚洲让球盘口转为 PrematchOddsMovementFeature，market_type=asian_handicap，outcome=home_cover/away_cover，metadata 记录 opening_line、closing_line、line_delta、line_changed、odds_prefix 与 overround；这为后续 lambda 调整层/盘口特征实验做准备，但暂不把亚洲让球两项盘混入中国/欧洲让球胜平负最终答案
真实本地报告：configs/recommendations/historical_reports/local_football_data_co_uk_asian_handicap_coverage_v1.json；source_count=61；row_count=26890；importable_row_count=22360；skipped_row_count=4530；importable_row_coverage=0.8315358869468203；line_changed_count=8268
分赛事可用量：E0=1900；SP1=1900；D1=1530；I1=1898；F1=1752；E1=2760；D2=1530；I2=1896；F2=1825；SP2=2309；N1=1530；P1=1530；JPN=0
分赛季可用量：2020-2021=4515；2021-2022=4517；2022-2023=4518；2023-2024=4440；2024-2025=4370
新增 deterministic tests：test_football_data_co_uk_asian_handicap_coverage.py 覆盖开盘/收盘 AH 解析、line_changed 识别、转换为 structured odds movement、CLI 写报告与参数映射
阶段性结论：当前暂不需要付费历史亚洲让球数据，欧洲主样本已有 22360 场可用于盘口特征实验；但日本/J 联赛在本地 football-data.co.uk 归档中没有 AH 列，若要覆盖日本让球历史样本，后续需要 SportMonks/The Odds API/其他付费历史赔率源
```

V3.1-372 当前落地能力：

```text
按 V3.1-371 的阶段性结论，把本地免费亚洲让球盘口从“覆盖审计”推进到“可进入赛前 feature snapshot 与 Poisson prematch-feature readout”；本轮不购买数据、不接 VPS、不动 zeus、不改变默认生产推荐 profile，也不把亚洲让球两项盘混入中国/欧洲让球胜平负最终答案
football_data_co_uk_feature_sample 新增 include_asian_handicap_features 选项；CLI 为 --include-asian-handicap-features；batch CLI 同步支持该选项
当启用该选项时，feature sample 会读取同一 CSV 行的 AHh/AHCh 与 Avg/B365/Max/P/BFE AHH/AHA 两项赔率，并在 prematch_context.odds_movement 中追加 market_type=asian_handicap、outcome=home_cover/away_cover 的开盘/收盘 movement；metadata 记录 opening_line、closing_line、line_delta、line_changed、overround、odds_prefix
1X2 baseline predictions 保持不变，prediction_count 仍只来自 1X2；亚洲让球当前作为赛前特征参与模型实验，不作为用户最终答案玩法直接输出
Poisson prematch-feature lambda readout 新增对 home_cover / away_cover probability_delta 的弱主客优势读取：home_cover 缩短提升 home advantage，away_cover 缩短提升 away advantage，权重为 1X2 movement 的 0.5，用于后续 shadow 实验
真实本地 smoke：configs/recommendations/historical_slices/local_epl_2024_2025_market_features_with_asian_handicap_sample_v1.json；输入 data/historical_sources/football_data_co_uk/europe/2425/E0.csv；max_rows=24；asian_handicap_feature_fixture_count=24；每场 2 条 asian_handicap movement；feature completeness passed；odds_movement_coverage=1.0；warnings=[]
新增/更新 deterministic tests：test_football_data_co_uk_feature_sample_can_include_asian_handicap_movements 覆盖 feature snapshot 中写入亚洲让球 movement；test_historical_poisson_walk_forward_reads_asian_handicap_cover_movement 覆盖 lambda readout 消费 home_cover/away_cover 信号；既有 feature sample CLI/batch 参数映射同步覆盖 include_asian_handicap_features
阶段性结论：当前已经具备用免费亚洲让球盘口做 lambda/最终答案 shadow 实验的入口；下一阶段应运行 prematch_feature_adjusted 的 shadow backtest，对比 1X2-only market movement 与 1X2+Asian handicap movement 是否提升 final-answer 命中和 ROI；若日本联赛也要同等盘口特征，再申请/购买日本历史盘口数据
```

V3.1-373 当前落地能力：

```text
按 V3.1-372 的阶段性结论，新增 1X2-only market movement 与 1X2+Asian handicap movement 的 Poisson prematch-feature shadow 对比；本轮不购买数据、不接 VPS、不动 zeus、不改变默认生产推荐 profile，也不把内部策略暴露给普通用户
新增模块：apps/api/src/nutmeg/accuracy/historical_prematch_feature_shadow_comparison.py；CLI 为 nutmeg-accuracy-prematch-feature-shadow-comparison
对比能力：按 baseline/candidate slice path 或 suite manifest 分别运行同一组 HistoricalPoissonWalkForwardOptions，通常使用 lambda_method=prematch_feature_adjusted；报告命中率、Brier、Log loss、average actual probability、expected calibration error 的 candidate-run delta，并统计 candidate 样本中的 asian_handicap feature fixture coverage
门禁能力：报告 passed_non_regression_gate，默认要求 baseline/candidate validation_count 一致、达到 min_validation_count，且 Brier/Log loss/ECE 不回退；该门禁只用于 shadow evidence，不会自动写入生产 profile
新增 deterministic tests：test_historical_prematch_feature_shadow_comparison.py 覆盖亚洲让球 feature coverage 识别、无亚洲让球 feature 时 warning、CLI 参数到 comparison/Poisson options 映射
真实本地 smoke：configs/recommendations/historical_reports/local_epl_2024_2025_market_feature_asian_handicap_shadow_comparison_v1.json；baseline=football_data_co_uk_epl_2024_2025_market_features_v1；candidate=local_epl_2024_2025_market_features_with_asian_handicap_sample_v1；min_prior_matches=6；min_team_matches=2；min_feature_quality=70
smoke 结果：baseline_validation_count=3；candidate_validation_count=3；candidate_asian_handicap_feature_fixture_count=24；candidate_asian_handicap_feature_coverage=1.0；warnings=[]
严格 non-regression 结论：passed_non_regression_gate=false；hit_rate_delta=0.0；brier_score_delta=+0.005283956301081472；log_loss_delta=+0.00840695356008403；expected_calibration_error_delta=+0.0032663163227492076；average_actual_probability_delta=-0.004909363310122761
阶段性结论：亚洲让球盘口已能进入赛前 lambda shadow 对比，但 24 场 EPL 小样本没有显示收益，反而轻微回退；下一阶段应扩大到 full multi-season European market-feature suite 做同口径比较，若仍回退则降低/关闭该信号，若分联赛/分赔率段有收益再做严格 admission，而不是直接加入最终答案主路径
```

V3.1 路线约束：动态混合最终答案

```text
用户看到的推荐不是按单一玩法分开的多个答案，而是一个全局最佳答案；2串1 到 8串1 都必须遵循同一套动态混合逻辑，都可以同时包含不让球胜平负、中国/欧洲让球胜平负、比分、单选腿和复式腿
推荐流程必须先在每场比赛内生成可比较的最优单场候选，再由全局规划器/最终答案仲裁器在 2串1 到 8串1、单式/复式、胜平负/让球胜平负/比分之间动态组合，选择预算内、规则内、质量最高的整体答案
组合不能预先固定为“只做胜平负”或“只做让球”或“只做比分”；玩法是候选维度，不是产品入口维度
复式是否保留、裁剪或退回单式，必须由预算约束、命中概率、EV/ROI、数据质量、相关性和规则合法性共同决定；超过预算时应自动裁剪为预算内最优答案，而不是简单放弃整组推荐
这条约束优先于前端展示、数据源接入和局部模型实验；任何 shadow 信号、让球数据、比分模型、selection-value 或 optimizer 升级，都必须证明它能改善这个最终混合答案，不能只改善孤立市场指标
普通用户界面只展示最终答案和必要备选，不展示内部策略标签；复杂性保留在后端、回测、质量门禁和审计报告中
```

V3.1-374 当前落地能力：

```text
按动态混合最终答案路线约束做工程化防偏移加固；本轮不接新数据源、不接 VPS、不动 zeus、不改变默认生产 profile，也不向普通用户展示内部策略
final_answer_arbitrator 的内部 arbitration payload 新增 market_count、dynamic_mixed_market_answer、selected_candidate_count、multiple_choice_fixture_count；reason_codes 新增 mixed_market_answer、includes_multiple_choice_leg、includes_handicap_market
global planner 的 final_answer_decision_json 同步透传 selected_market_types、dynamic_mixed_market_answer、multiple_choice_fixture_count，用于审计/回归测试判断最终答案是否仍是动态混合组合，而不是退回单一玩法 silo
新增/更新 deterministic tests：test_global_planner_keeps_dynamic_mixed_market_path_for_2x1_to_8x1 覆盖 2x1、3x1、4x1、5x1、6x1、7x1、8x1 每一种 pass_type 都可以在同一最终答案中动态混合 1X2 与中国/欧洲让球候选；test_final_answer_arbitrator_marks_dynamic_mixed_market_multiple_answer 覆盖同一答案同时包含 1X2、让球、比分与复式腿时的内部审计标记
阶段性结论：动态混合不再只是设计文档描述，已经成为 final-answer path 的可测试不变量；后续任何 optimizer、让球、比分、selection-value、预算裁剪或模型信号改动，如果把 2串1-8串1 退化为单一玩法推荐，应被这些测试和审计字段发现
```

V3.1-375 当前落地能力：

```text
按 V3.1-374 的动态混合最终答案约束，把审计字段从 planner/arbitrator 单元测试接入真实 historical backtest / suite quality gate；本轮不接新数据源、不接 VPS、不动 zeus、不改变默认生产 profile，也不向普通用户展示内部策略
historical backtest 的 summary_json 新增 final_answer_arbitration、final_answer_market_types、final_answer_market_count、final_answer_dynamic_mixed_market、final_answer_selected_candidate_count、final_answer_multiple_choice_fixture_count、final_answer_has_handicap_market、final_answer_has_correct_score_market；这些字段由同一个 final_answer_arbitrator payload 生成，避免历史回放与在线规划口径漂移
historical suite summary 聚合 baseline/candidate dynamic_mixed_final_answer_count/rate、final_answer_market_type_counts、handicap/correct_score/multiple_choice final-answer counts，以及 selected_candidate / multiple_choice_fixture 总量，用于真实历史窗口判断最终答案是否保持动态混合能力
historical suite quality gate 新增可选阈值：min_candidate_dynamic_mixed_final_answer_count、min_candidate_dynamic_mixed_final_answer_rate、min_candidate_handicap_final_answer_count、min_candidate_correct_score_final_answer_count、min_candidate_multiple_choice_final_answer_count；CLI 同步支持对应参数
新增/更新 deterministic tests：test_historical_backtest_reports_dynamic_mixed_final_answer_markets 覆盖历史回放中 1X2 + 中国让球 2x1 最终答案的 market summary；test_historical_suite_quality_gate_can_require_dynamic_mixed_final_answers 覆盖 suite/gate 可以要求动态混合与让球 final answer，并在缺少比分 final answer 时正确失败；CLI 参数映射测试同步覆盖新阈值
阶段性结论：动态混合最终答案现在不仅是在线 planner 的不变量，也能在真实历史样本质量门禁里被量化和阻断；下一阶段应在不暴露内部策略给用户的前提下，继续把真实历史宽窗口的 final-answer gate 接到默认周期治理报告，优先看命中率、ROI、Brier/log-loss/ECE 与动态混合覆盖是否共同改善
```

V3.1-376 当前落地能力：

```text
按 V3.1-375 的阶段性结论，把 historical suite 的动态混合 final-answer market evidence 接入 benchmark quality gate 与 benchmark cycle；本轮不接新数据源、不接 VPS、不动 zeus、不改变默认生产 profile，也不向普通用户展示内部策略
benchmark quality gate 现在会把 historical suite summary 中的 baseline/candidate dynamic_mixed_final_answer_count/rate、final_answer_market_type_counts、handicap/correct_score/multiple_choice final-answer counts、selected_candidate_count、multiple_choice_fixture_count 透传为 historical_suite_* summary 字段
benchmark quality gate 新增可选阈值：min_historical_suite_candidate_dynamic_mixed_final_answer_count、min_historical_suite_candidate_dynamic_mixed_final_answer_rate、min_historical_suite_candidate_handicap_final_answer_count、min_historical_suite_candidate_correct_score_final_answer_count、min_historical_suite_candidate_multiple_choice_final_answer_count；CLI 同步支持对应参数
benchmark cycle 的 gate summary 与 CLI/preset option mapping 同步接入这些 historical_suite_* 字段和 gate-min 参数，使周期治理报告可以观察并阻断最终答案退回单一玩法 silo
新增/更新 deterministic tests：test_quality_gate_consumes_historical_suite_dynamic_mixed_evidence 覆盖 benchmark gate 能消费并门禁 dynamic-mixed/handicap/correct-score/multiple-choice evidence；test_cycle_summary_carries_historical_suite_lifecycle_gate_evidence 覆盖 cycle summary 透传这些字段；quality gate/cycle CLI 参数映射测试同步覆盖新增阈值
阶段性结论：动态混合最终答案约束已经从 planner/arbitrator 单元测试、historical backtest、historical suite gate 上卷到默认 benchmark/cycle 治理层；默认阈值暂时保持非阻断，等真实历史窗口具备足够让球/比分覆盖后再提高硬门槛
```

V3.1-377 当前落地能力：

```text
按 V3.1-376 的阶段性结论，回到真实历史样本覆盖本身，扩展 historical_sample_coverage_audit 来审计 prediction market 覆盖；本轮不接新数据源、不接 VPS、不动 zeus、不改变默认生产 profile，也不向普通用户展示内部策略
HistoricalSampleCoverageSourceSummary 新增 prediction_count、prediction_count_by_market、fixture_count_by_market、complete_market_fixture_count_by_market、non_1x2_market_fixture_count、handicap_market_fixture_count、correct_score_market_fixture_count、dynamic_mixed_candidate_fixture_count 及对应 coverage 字段
coverage readiness 新增 dynamic_mixed_candidate_ready、handicap_candidate_ready、correct_score_candidate_ready；CLI 新增 --min-dynamic-mixed-candidate-fixture-count、--min-handicap-candidate-fixture-count、--min-correct-score-candidate-fixture-count，用于把“历史样本是否真的有混合玩法候选”显式纳入审计
新增 deterministic test：test_historical_sample_coverage_audit_counts_dynamic_market_candidates 覆盖同一 source 中 1X2 + 中国让球 + 比分 candidate 的计数、complete-market 计数、dynamic mixed fixture coverage 与 ready source 聚合；CLI 参数映射测试同步覆盖新增阈值
生成真实覆盖审计：configs/recommendations/historical_reports/historical_sample_coverage_dynamic_market_audit_v1.json；audit_key=historical_sample_coverage_audit:550c7de743df788f；source_count=6；slice_count=306；fixture_count=16980
真实审计结论：六个现有 source 的 prediction_count_by_market 全部只有 1x2；non_1x2_market_fixture_count=0；handicap_market_fixture_count=0；correct_score_market_fixture_count=0；dynamic_mixed_candidate_fixture_count=0；dynamic_mixed_candidate_ready_source_ids=[]；handicap_candidate_ready_source_ids=[]；correct_score_candidate_ready_source_ids=[]
阶段性结论：动态混合 final-answer 引擎和治理门禁已经就位，但真实历史 slice 尚未提供让球/比分 prediction 候选；下一阶段核心工作应是从比分网格或历史让球盘口导出/写入 handicap 与 correct-score HistoricalMarketPrediction，让真实回放能检验 2串1-8串1 的混合玩法，而不是继续调外围数据源或前端
```

V3.1-378 当前落地能力：

```text
按 V3.1-377 的阶段性结论，新增 shadow derived-market candidate builder，把完整 1X2 历史 fixture 转成可回放的让球与比分候选；本轮不接新数据源、不接 VPS、不动 zeus、不改变默认生产 profile，也不向普通用户展示内部策略
新增模块与 CLI：apps/api/src/nutmeg/recommendations/historical_derived_market_candidates.py；命令为 nutmeg-recommendation-historical-derived-market-candidates
派生逻辑：优先读取 fixture metadata 中的 lambda_home/lambda_away；缺失时使用完整 1X2 概率做 deterministic shadow heuristic 推导 lambda_home/lambda_away；再通过既有 score_grid_to_market_probabilities 导出 Chinese handicap 1X2、European handicap 1X2、correct_score Top N 的 HistoricalMarketPrediction
所有派生 prediction 写入 metadata_json：source=historical_derived_market_candidates、calculation_basis=poisson_score_grid_shadow_market_derivation_v3_1、lambda_home/lambda_away、lambda_source、score_grid_max_goals、dc_compatibility；明确标记 fair model-derived odds，不伪装成付费 provider 历史盘口赔率
historical_backtest CLI 新增 --allowed-markets，使派生 slice 可以直接用 CLI 回测 1x2/cn_handicap_1x2/european_handicap_1x2/correct_score 混合候选
新增 deterministic tests：test_derived_market_candidates_add_handicap_and_correct_score_predictions、test_derived_market_candidates_make_historical_slice_dynamic_market_ready、test_derived_market_candidates_can_feed_historical_backtest_candidates、CLI 写入与参数映射测试；覆盖派生候选生成、coverage readiness、historical backtest candidate pool 消费
真实 smoke 生成派生 slice：configs/recommendations/historical_slices/derived_markets/euro_2024_knockout_sample_derived_markets_v1.json；报告：configs/recommendations/historical_reports/euro_2024_knockout_sample_derived_market_candidates_v1.json；report_key=historical_derived_market_candidates:5a57b001b463cc7f；fixture_count=7；generated_prediction_count=119；cn_handicap_1x2=42；european_handicap_1x2=42；correct_score=35；lambda_source_counts={one_x_two_probability_shadow_heuristic: 7}
派生 coverage smoke：configs/recommendations/historical_reports/euro_2024_knockout_sample_derived_market_coverage_audit_v1.json；dynamic_mixed_candidate_ready_source_ids、handicap_candidate_ready_source_ids、correct_score_candidate_ready_source_ids 均包含 euro_2024_knockout_sample_v1_derived_markets_v1
派生 backtest smoke：configs/recommendations/historical_reports/euro_2024_knockout_sample_derived_market_backtest_smoke_v1.json；eligible_candidate_count=140；final_answer_market_types=[cn_handicap_1x2]；final_answer_has_handicap_market=true；说明 historical recommendation engine 已能消费非 1X2 派生候选
阶段性结论：真实回放链路第一次拥有可测试的让球/比分 shadow candidate 入口；下一阶段应把该派生器应用到更大的 rolling-window suite，先验证动态混合覆盖、命中率、ROI、Brier/log-loss/ECE，再决定是否需要付费历史让球赔率替换 fair model-derived odds
```

V3.1-379 当前落地能力：

```text
按 V3.1-378 的阶段性结论，把 shadow derived-market candidate builder 从单 slice 扩展到 rolling-window suite；本轮不接新 API、不接 VPS、不动 zeus、不改变默认生产 profile，也不向普通用户展示内部策略
historical_derived_market_candidates 新增 suite manifest 模式：--suite-manifest、--output-slice-dir、--output-suite-manifest-path；可一次读取历史套件、生成每个派生 slice、写出新的 derived suite manifest，并输出聚合 suite report
historical suite quality gate 新增 --allowed-markets，使真实质量门禁可以显式评估 1x2、cn_handicap_1x2、european_handicap_1x2、correct_score 的候选池，而不是继续被默认 1X2-only 限制住
新增/更新 deterministic tests：test_derived_market_candidates_cli_writes_suite_manifest 覆盖 suite manifest 派生写入；historical quality gate CLI 参数映射测试覆盖 allowed_markets 传递到 HistoricalRecommendationBacktestOptions
真实派生套件：configs/recommendations/historical_suites/football_data_co_uk_expanded_a_leagues_rolling_window_derived_markets_suite_v1.json；派生 slice 目录：configs/recommendations/historical_slices/derived_markets/football_data_co_uk_expanded_a_leagues_rolling_windows_v1；共 210 个 JSON slice，约 91M
真实派生报告：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_derived_market_candidates_v1.json；report_key=historical_derived_market_candidate_suite:2a61868da39cad90；slice_count=210；fixture_count=2520；source_prediction_count=7560；output_prediction_count=50400；generated_prediction_count=42840；cn_handicap_1x2=15120；european_handicap_1x2=15120；correct_score=12600；lambda_source_counts={one_x_two_probability_shadow_heuristic: 2520}；warnings=[]
真实覆盖审计：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_derived_market_coverage_audit_v1.json；audit_key=historical_sample_coverage_audit:9d305bfbdef698e6；prediction_count_by_market={1x2: 7560, cn_handicap_1x2: 15120, european_handicap_1x2: 15120, correct_score: 12600}；dynamic_mixed_candidate_fixture_count=2520；handicap_market_fixture_count=2520；correct_score_market_fixture_count=2520；derived suite 同时进入 dynamic_mixed_candidate_ready、handicap_candidate_ready、correct_score_candidate_ready；仅剩 context_signal_not_ready warning
真实质量门禁 smoke：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_derived_market_suite_gate_smoke_v1.json；gate_key=historical_recommendation_suite_quality_gate:9a05f8476d1f55a0；status=passed；suite_status=improved；slice_count=210；comparison_count=210；candidate_final_hit_sample_size=210；candidate_final_hit_rate=0.819047619047619；candidate_roi=0.006733723401772428；candidate_profit_loss=2.8281638287444197；final_hit_rate_delta=0.014285714285714235；roi_delta=0.011323874545978725；profit_loss_delta=4.756027309311063；Brier/log-loss/ECE delta 均改善；failed_checks=[]；warnings=[]
重要限制：当前真实 smoke 的 final answers 全部为 cn_handicap_1x2，candidate_handicap_final_answer_count=210，但 candidate_dynamic_mixed_final_answer_count=0、candidate_correct_score_final_answer_count=0；这说明候选覆盖与门禁已打通，但还不能声称真实历史套件已经形成“2串1 到 8串1 动态混合胜平负/让球/比分”的最终答案能力
阶段性结论：本轮完成了更大真实 rolling-window suite 的非 1X2 候选覆盖和门禁回放，并得到命中率/ROI 的 shadow 改善信号；下一阶段应优先解决 final-answer 仲裁过度集中于单一让球市场的问题，在不降低 final-hit/ROI/Brier/log-loss/ECE 的前提下，推动真实动态混合市场、比分候选和复式腿进入最终答案
```

V3.1-380 当前落地能力：

```text
按 V3.1-379 的阶段性结论，新增 final-answer market concentration audit，用于把“最终答案从 1X2 silo 变成 cn_handicap silo”的风险显式门禁化；本轮不接新 API、不接 VPS、不动 zeus、不改变默认生产 profile，也不向普通用户展示内部策略
新增模块与 CLI：apps/api/src/nutmeg/recommendations/historical_final_answer_market_concentration_audit.py；命令为 nutmeg-recommendation-final-answer-market-concentration-audit
审计能力：读取 slice path 或 suite manifest，重放 historical recommendation backtest suite，统计 final_answer_count、market_type_counts/rates、single_market_type_counts/rates、dominant_single_market_type/rate、market_concentration_hhi、dynamic_mixed_final_answer_count/rate、handicap/correct-score/multiple-choice final answer count，并保留 final-hit/ROI/profit/Brier/log-loss/ECE delta
门禁能力：支持 min_final_answer_count、min_market_type_count、max_dominant_single_market_rate、min_dynamic_mixed_final_answer_count/rate、min_correct_score_final_answer_count、min_multiple_choice_final_answer_count，以及 final-hit/ROI/profit/Brier/log-loss/ECE non-regression 阈值；支持 --no-fail-process 生成失败报告但不打断 smoke
新增 deterministic tests：test_market_concentration_audit_flags_single_market_dominance 覆盖单一 cn_handicap_1x2 独占被拦截；test_market_concentration_audit_passes_true_dynamic_mixed_answers 覆盖 1X2+中国让球 true mixed-market final answer 可通过；CLI 写报告与参数映射测试同步覆盖
真实审计报告：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_final_answer_market_concentration_audit_v1.json；report_key=historical_final_answer_market_concentration_audit:e68f8368d5ecdfe1；status=failed；suite_status=improved；final_answer_count=210；market_type_count=1；market_type_counts={cn_handicap_1x2: 210}；single_market_final_answer_count=210；dominant_single_market_type=cn_handicap_1x2；dominant_single_market_rate=1.0；market_concentration_hhi=1.0；dynamic_mixed_final_answer_count=0；correct_score_final_answer_count=0；multiple_choice_final_answer_count=0
真实审计质量侧结果仍然改善：candidate_final_hit_rate=0.819047619047619；candidate_roi=0.006733723401772428；candidate_profit_loss=2.8281638287444197；final_hit_rate_delta=0.014285714285714235；roi_delta=0.011323874545978725；profit_loss_delta=4.756027309311063；Brier/log-loss/ECE delta 均改善
失败 checks：market_type_count、dominant_single_market_rate、dynamic_mixed_final_answer_count；通过 checks：final_answer_count、final-hit/ROI/profit non-regression、Brier/log-loss/ECE non-regression
阶段性结论：系统现在能准确区分“候选覆盖与质量指标改善”以及“最终答案真正动态混合”；当前真实派生 suite 的问题不是回放失败，而是 final-answer 仲裁/候选质量函数过度偏向单一中国让球 1x1 single。下一阶段应在该审计约束下做候选质量函数或仲裁修正实验，目标是在保持 non-regression 的前提下提高 dynamic_mixed_final_answer_count，并让比分/复式只在确有价值时进入最终答案
```

V3.1-381 当前落地能力：

```text
按 V3.1-380 的阶段性结论，实现可回滚的 dynamic-mix final-answer shadow lane；本轮不接新 API、不接 VPS、不动 zeus、不改变默认生产 profile、不向普通用户展示内部策略，也不强行把混合玩法设为生产默认答案
historical backtest 新增 dynamic_mix_final_answer_lane 及其 pass_types、candidate_limit、min_probability、score_boost、max_hit_probability_deficit、min_roi_delta 等选项；默认关闭，只有显式打开时才生成额外影子候选
动态混合通道从 pre-compression 全候选池生成 2x1+ single-parlay 候选：先取常规 base selection，再尝试用同 fixture 的其他 market 或其他 fixture 的不同 market 替换一个 leg，要求 selected market count 达到 min_market_count，并用 expected ROI / hit probability guard 防止为了“混合”牺牲核心质量
final-answer ranking 支持 dynamic_mix lane 的受控 boost 与质量 guard；summary_json 与 suite summary 新增 completed_dynamic_mix_final_answer_lane_count、final_answer_dynamic_mix_final_answer_lane、dynamic_mix_final_answer_lane_quality_guard_blocked_option_count 等审计字段
final-answer market concentration audit CLI 同步支持 --dynamic-mix-final-answer-lane 及对应参数，报告 summary 会透传 candidate_completed_dynamic_mix_final_answer_lane_count、candidate_final_answer_dynamic_mix_final_answer_lane_count、candidate_dynamic_mix_final_answer_lane_quality_guard_blocked_option_count
新增 deterministic test：test_market_concentration_audit_dynamic_mix_lane_can_select_replacement，覆盖普通压缩路径只会选单一 cn_handicap_1x2 时，dynamic-mix lane 可以用同场 1X2 替换生成 true mixed-market final answer；CLI 参数映射测试同步覆盖新增动态混合 lane 参数
真实完整派生套件审计报告：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_audit_v1.json；report_key=historical_final_answer_market_concentration_audit:3afb0c7602cf9311；status=passed；suite_status=improved；slice_count=210；final_answer_count=210；market_type_count=2；dynamic_mixed_final_answer_count=208；dynamic_mixed_final_answer_rate=0.9904761904761905；single_market_final_answer_count=2；dominant_single_market_rate=0.009523809523809525
真实质量结果：candidate_final_hit_rate=0.7333333333333333；candidate_roi=0.02030518640520881；candidate_profit_loss=8.5281782901877；final_hit_rate_delta=0.004761904761904745；roi_delta=0.0031935499314942432；profit_loss_delta=1.3412909712275827；Brier/log-loss/ECE delta 均改善；candidate_completed_dynamic_mix_final_answer_lane_count=630；candidate_final_answer_dynamic_mix_final_answer_lane_count=208；candidate_dynamic_mix_final_answer_lane_quality_guard_blocked_option_count=422
重要限制：当前真实 mixed final answer 主要在 cn_handicap_1x2 与 european_handicap_1x2 之间混合，correct_score 与 multiple-choice legs 仍未进入最终答案；此外该实验使用 2x1/3x1/4x1 single-parlay 口径，不等同于把 1x1 或复式生产路径改为默认动态混合
阶段性结论：系统已从“能识别单一玩法集中风险”推进到“能在真实 210-slice 派生套件上生成大量受控混合最终答案并保持质量改善”；下一阶段应继续做 2x1 到 8x1 的更宽 pass_type、复式预算裁剪、correct_score admission 与 no-harm 门禁，而不是把当前 shadow lane 直接视为最终生产策略
```

V3.1-382 当前落地能力：

```text
按 V3.1-381 的阶段性结论，把 dynamic-mix final-answer shadow lane 扩展到 2x1-8x1 与 multiple 模式的工程入口；本轮不接新 API、不接 VPS、不动 zeus、不改默认生产 profile、不向普通用户展示内部策略，也不把重型复式实验误升为全量日常门禁
dynamic_mix_final_answer_lane 新增 modes 入口：保留旧的 singular dynamic_mix_final_answer_lane_mode，同时新增 dynamic_mix_final_answer_lane_modes；当 modes 非空时可一次生成 single/multiple 多个影子 lane，保持旧命令向后兼容
dynamic-mix lane 新增独立 solver 开关 dynamic_mix_final_answer_lane_solver_search，默认 false；原因是 full multiple 2x1-8x1 在真实派生套件上会触发过重的候选扩展/预算裁剪成本，影子实验必须默认 bounded，不应拖垮周期质量门禁
multiple 模式已接入 dynamic-mix lane：当普通 multiple selection 已经满足 mixed market count 时直接形成 lane option；若普通 multiple 仍是单一 market，则先用 single dynamic-mix projection 生成 mixed seed，再作为 locked candidates 进入 multiple budget optimizer，从而保留预算裁剪、单位注额、总注额与复式腿评估契约
final-answer market concentration audit 新增 --dynamic-mix-final-answer-lane-modes、--dynamic-mix-final-answer-lane-solver-search 与 --slice-limit；--slice-limit 用于把重型真实套件实验收束成明确 smoke，不把 partial evidence 伪装成全量门禁
新增/更新 deterministic tests：覆盖 slice_limit 只回放前 N 个 slice、dynamic-mix lane 支持 8x1 single、dynamic-mix lane 支持 multiple mode，以及 CLI 参数映射覆盖 modes/solver_search/slice_limit
真实 single 全量报告：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_8x1_single_audit_v1.json；status=passed；suite_status=improved；slice_count=210；final_answer_count=210；market_type_count=2；dynamic_mixed_final_answer_count=205；dynamic_mixed_final_answer_rate=0.9761904761904762；candidate_final_hit_rate=0.7380952380952381；candidate_roi=0.027776574189284673；candidate_profit_loss=11.666161159499563；candidate_completed_dynamic_mix_final_answer_lane_count=1470；candidate_final_answer_dynamic_mix_final_answer_lane_count=205；quality_guard_blocked_option_count=1265；failed_checks=[]
真实 multiple bounded smoke：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_smoke_v1.json；slice_limit=5；status=passed；suite_status=unchanged；dynamic_mixed_final_answer_count=3；dynamic_mixed_final_answer_rate=0.6；multiple_choice_final_answer_count=2；candidate_final_hit_rate=1.0；candidate_roi=-0.30744446848876117；candidate_profit_loss=-6.763778306752746；failed_checks=[]
重要限制：multiple 2x1-4x1 的 30-slice smoke 与 full 210-slice replay 均因运行时间过高被中止，说明复式模式当前不是准确性瓶颈已经解决，而是需要下一阶段先做 candidate pre-filter / pass_type 分段 / budget-aware beam width，再进入更大窗口质量门禁；correct_score 仍未进入最终答案
阶段性结论：2x1-8x1 single 动态混合已经形成强真实证据；multiple 模式已有可测试入口和小样本 smoke，但不能 promotion。下一阶段应优先做复式候选空间收缩与 correct-score admission no-harm gate，再尝试 30-slice/210-slice multiple 质量门禁
```

V3.1-383 当前落地能力：

```text
修复 multiple optimizer 的搜索开关语义：当 enable_solver_search=False 时，后置 integer solver 与 beam search 都不会再运行，避免 dynamic-mix multiple shadow lane 在显式关闭重型搜索时仍误跑全局搜索
新增 deterministic regression test：test_multiple_optimizer_respects_disabled_solver_search，验证关闭搜索时 explanation_json 不再包含 solver_search 或 beam_search，同时仍保持预算内可用选择
真实 multiple 30-slice 审计已完成：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_30slice_v1.json；status=passed；suite_status=improved；slice_count=30；final_answer_count=30；market_type_count=2；dynamic_mixed_final_answer_count=29；dynamic_mixed_final_answer_rate=0.9666666666666667；multiple_choice_final_answer_count=1；candidate_final_hit_rate=0.8333333333333334；candidate_roi=0.33517379939700687；candidate_profit_loss=22.121470760202453；failed_checks=[]
质量 delta 全部过线：final_hit_rate_delta=0.06666666666666665；roi_delta=0.22857536867265948；profit_loss_delta=15.72556491674161；Brier/log-loss/mean calibration error delta 均改善
阶段性结论：dynamic-mix multiple 已从 5-slice smoke 推进到 30-slice bounded quality gate；但 full 210-slice multiple 尚未升为周期门禁，下一步应按 pass_type 分段验证 2x1、3x1、4x1，再决定是否扩展到 5x1-8x1 multiple
```

V3.1-384 当前落地能力：

```text
新增 nutmeg-recommendation-final-answer-market-concentration-segment-gate，用于把多个 pass_type 分段审计报告合成机器可读的 promote/block 决策；该工具只用于后台质量门禁，不向普通用户展示内部策略或理由
新增 HistoricalFinalAnswerMarketConcentrationSegmentGateReport，输出 segment_count、promoted_segment_count、blocked_segment_count、promoted_pass_types、blocked_pass_types、每段 failed_checks、ROI/P&L/命中率/校准 delta 与 reason_codes
新增 deterministic tests 覆盖：只晋级通过段、require_all_segments_passed 阻断、CLI 写入 summary report
完成 2x1/3x1/4x1 multiple 的 210-slice 分段审计：2x1 report=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_multiple_210slice_v1.json；3x1 report=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_3x1_multiple_210slice_v1.json；4x1 report=configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_4x1_multiple_210slice_v1.json
分段汇总报告：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_segment_gate_v1.json；segment_count=3；promoted_pass_types=["3x1"]；blocked_pass_types=["2x1","4x1"]
3x1 multiple 通过 strict no-harm gate：status=passed；suite_status=improved；slice_count=210；dynamic_mixed_final_answer_count=178；dynamic_mixed_final_answer_rate=0.8476190476190476；multiple_choice_final_answer_count=32；candidate_final_hit_rate=0.6476190476190476；candidate_roi=0.04466108592910554；candidate_profit_loss=36.62209046186654；final_hit_rate_delta=0.023809523809523836；roi_delta=0.0020807466560052792；profit_loss_delta=8.34874518452797；Brier/log-loss/mean calibration error delta 均改善
2x1 multiple 被 ROI/P&L no-harm gate 阻断：dynamic_mixed_final_answer_rate=0.9095238095238095；final_hit_rate_delta=0.004761904761904745；Brier/log-loss/mean calibration error delta 改善；但 roi_delta=-0.011700270724697637，profit_loss_delta=-6.151133077070941
4x1 multiple 被 ROI/P&L no-harm gate 阻断：dynamic_mixed_final_answer_rate=0.8333333333333334；final_hit_rate_delta=0.01904761904761898；Brier/log-loss/mean calibration error delta 改善；但 roi_delta=-0.4794364554271857，profit_loss_delta=-127.0786315629419
阶段性结论：multiple dynamic-mix 不能整体晋级；3x1 是第一个可晋级 pass_type；2x1 与 4x1 需要收益/预算保护型仲裁后再复测，5x1-8x1 multiple 暂不推进到全量门禁
```

V3.1-385 当前落地能力：

```text
historical final-answer market concentration audit 新增 dynamic-mix segment gate admission 输入：--dynamic-mix-final-answer-lane-segment-gate-report、--dynamic-mix-final-answer-lane-admitted-pass-types、--dynamic-mix-final-answer-lane-blocked-pass-types
HistoricalRecommendationBacktestOptions 新增 dynamic_mix_final_answer_lane_admitted_pass_types 与 dynamic_mix_final_answer_lane_blocked_pass_types；dynamic-mix lane 现在会先计算 effective_pass_types，只为已晋级且未阻断的 pass_type 生成 shadow lane
summary_json 新增 dynamic_mix_final_answer_lane_effective_pass_types、admitted_pass_types、blocked_pass_types 与 segment_gate_report，便于报告验证当前是否真的只启用了通过 ROI/P&L no-harm 的关数
新增 CLI 回归测试：market concentration audit 能读取 segment gate report，把 promoted_pass_types 映射为 admitted pass types，把 blocked_pass_types 映射为 blocked pass types；旧的手工 admitted/blocked 参数仍可用
真实 30-slice admission smoke：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_segment_admitted_30slice_v1.json；请求 pass_types=2x1,3x1,4x1、mode=multiple，但 segment gate admission 后 effective_pass_types=["3x1"]，admitted=["3x1"]，blocked=["2x1","4x1"]
30-slice admission smoke 结果：status=passed；suite_status=improved；slice_count=30；dynamic_mixed_final_answer_count=17；dynamic_mixed_final_answer_rate=0.5666666666666667；multiple_choice_final_answer_count=6；candidate_final_hit_rate=0.7666666666666667；candidate_roi=0.09200844928526968；candidate_profit_loss=8.832811131385888；final_hit_rate_delta=0.06666666666666676；roi_delta=0.10263647053950446；profit_loss_delta=9.725564916741611；Brier/log-loss/mean calibration error delta 均改善；failed_checks=[]
尝试过 full combined 2x1/3x1/4x1 210-slice admission replay，但普通 multiple 候选组合仍是高 CPU 长跑，已中止，避免把开发节奏重新拖回重型离线任务；当前 full-sample admission 证据仍以 V3.1-384 的 pass_type 分段 210-slice 报告为准
阶段性结论：收益/预算保护型仲裁第一层已经形成：运行时/回测层可以从 segment gate 读取已晋级关数，只让 3x1 dynamic-mix multiple 进入 shadow lane；下一步应做缓存/批处理 combined gate，以及 2x1/4x1 的 ROI/P&L 修复策略
```

V3.1-386 当前落地能力：

```text
新增 nutmeg-recommendation-final-answer-market-concentration-admission-gate，用于把 pass-type segment gate 与可选 bounded combined smoke 合成轻量 admission artifact；该工具不重新运行重型 historical backtest，只把已完成的分段证据固化为可复用质量门禁
新增 HistoricalFinalAnswerMarketConcentrationAdmissionGateReport，输出 requested_pass_types、admitted_pass_types、blocked_pass_types、effective_pass_types、segment_gate_report_key、bounded_admission_report_key、checks、warnings 与 summary_json
admission gate checks 覆盖：segment gate 必须通过、admitted pass type 数量、blocked pass type 不得进入 effective set、requested pass type 必须被 segment gate 覆盖、bounded smoke 必须存在/通过/达到 slice 与 dynamic-mixed/multiple-choice 数量阈值、bounded smoke 的 effective pass types 必须等于 admission effective set
新增 deterministic tests 覆盖：admission gate 只使用 segment gate 已晋级 pass type；bounded smoke 若误跑 blocked pass type 会失败；CLI 可读取 segment gate + bounded smoke 并写出 summary
真实 lightweight admission gate artifact：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_segment_admission_gate_v1.json；report_key=historical_final_answer_market_concentration_admission_gate:c216c5a021eac85b；status=passed；requested_pass_types=["2x1","3x1","4x1"]；effective_pass_types=["3x1"]；admitted_pass_types=["3x1"]；blocked_pass_types=["2x1","4x1"]；failed_checks=[]
阶段性结论：combined admission 不再依赖人工记忆或强行重跑 full 210-slice；周期治理可以先读取轻量 admission artifact，继续只放行 3x1 dynamic-mix multiple。下一阶段应转向 2x1/4x1 的 ROI/P&L 修复实验，或把该 admission artifact 接入 benchmark/cycle 质量门禁
```

V3.1-387 当前落地能力：

```text
按 V3.1-386 的结论进入 2x1/4x1 ROI/P&L 修复实验；本轮不接新数据源、不接 VPS、不动 zeus、不改变默认生产 profile，也不向普通用户展示内部策略
historical final-answer market concentration audit CLI 新增 --max-outcomes-per-fixture、--min-marginal-quality-gain 与 final-answer stake-efficiency guard 参数透传；这让 market concentration audit 可以直接测试复式展开约束，而不是只能测试最终答案排序
新增 deterministic options mapping test，覆盖 max_outcomes_per_fixture、min_marginal_quality_gain、final_answer_stake_efficiency_guard、penalty_strength、max_stake_multiplier、min_roi、modes、scope
负向 2x1 实验 1：dynamic_mix_final_answer_lane_min_roi_delta=0.02 会把 mixed lane 全部挡掉，但普通 multiple solver 仍 ROI/P&L 回撤；报告 configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_multiple_roi_guard_002_210slice_v1.json；dynamic_mixed_final_answer_count=0；roi_delta=-0.03405725271228922；profit_loss_delta=-23.185203793833892
负向 2x1 实验 2：min_marginal_quality_gain=0.03 会减少 multiple-choice final answers，但仍 ROI/P&L 回撤；报告 configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_multiple_marginal_gain_003_210slice_v1.json；dynamic_mixed_final_answer_count=178；multiple_choice_final_answer_count=12；roi_delta=-0.04031107466286947；profit_loss_delta=-18.60101090802433
正向 2x1 受约束恢复：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_multiple_max_outcomes_1_210slice_v1.json；max_outcomes_per_fixture=1；status=passed；suite_status=improved；slice_count=210；dynamic_mixed_final_answer_count=205；dynamic_mixed_final_answer_rate=0.9761904761904762；multiple_choice_final_answer_count=0；candidate_final_hit_rate=0.7380952380952381；candidate_roi=0.027776574189284673；candidate_profit_loss=11.666161159499563；final_hit_rate_delta=0.009523809523809601；roi_delta=0.010664937715570106；profit_loss_delta=4.479273840539445；Brier/log-loss/ECE delta 均改善；failed_checks=[]
负向 4x1 受约束实验：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_4x1_multiple_max_outcomes_1_210slice_v1.json；max_outcomes_per_fixture=1；status=failed；dynamic_mixed_final_answer_count=179；multiple_choice_final_answer_count=0；final_hit_rate_delta=-0.01428571428571429；roi_delta=-0.05341060724348718；profit_loss_delta=-22.432455042264618
阶段性结论：2x1 的失败主要来自复式扩张，不是 2x1 dynamic mixed-market 本身；但该通过证据只允许进入“max_outcomes_per_fixture=1 的受约束 2x1”候选，不能直接把默认 2x1 multiple-choice 晋级。4x1 即使去掉复式扩张仍不达标，应继续阻断。下一阶段应把 pass-type admission 从单纯 pass_type 升级为 pass_type + constraint profile，避免把受约束 2x1 误解释为默认 2x1 复式通过
```

V3.1-388 当前落地能力：

```text
按 V3.1-387 的阶段性结论，把 dynamic-mix multiple admission 从 pass_type-only 升级为 pass_type + constraint profile；本轮不接新数据源、不接 VPS、不动 zeus、不改变默认生产 profile，也不向普通用户展示内部策略
segment gate decision 新增 constraint_profile_id、constraint_profile_key、constraint_profile_json，并在 report/summary 中输出 promoted_constraint_profiles 与 blocked_constraint_profiles；profile 当前记录 max_outcomes_per_fixture 与 min_marginal_quality_gain，后续可扩展预算、stake efficiency、solver/profile 参数
admission gate 新增 --constraint-profile-admission；开启后 effective set 以 promoted constraint profile 为准，而不是只按 pass_type 取交集；blocked_constraint_profile_exclusion 会阻断精确画像冲突，同时允许同一个 pass_type 下“默认画像被阻断、受约束画像被晋级”的情况
新增 deterministic tests 覆盖：segment gate 从 audit summary 推导 constraint profile；constraint-profile admission 可以放行受约束 2x1，同时继续阻断默认 2x1 与 4x1；既有 pass-type-only admission 保持向后兼容
真实 constraint segment gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_constraint_segment_gate_v1.json；report_key=historical_final_answer_market_concentration_segment_gate:39cdc47e95276ed6；status=passed；segment_count=4；promoted_segment_count=2；blocked_segment_count=2
promoted_constraint_profiles=["2x1:multiple:max_outcomes_per_fixture=1|min_marginal_quality_gain=0","3x1:multiple:max_outcomes_per_fixture=2|min_marginal_quality_gain=0"]；blocked_constraint_profiles=["2x1:multiple:max_outcomes_per_fixture=2|min_marginal_quality_gain=0","4x1:multiple:max_outcomes_per_fixture=1|min_marginal_quality_gain=0"]
真实 constraint admission gate：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_2x1_4x1_multiple_constraint_admission_gate_v1.json；report_key=historical_final_answer_market_concentration_admission_gate:80055bf3203a332b；status=passed；requested_pass_types=["2x1","3x1","4x1"]；effective_pass_types=["2x1","3x1"]；failed_checks=[]
effective_constraint_profiles=["2x1:multiple:max_outcomes_per_fixture=1|min_marginal_quality_gain=0","3x1:multiple:max_outcomes_per_fixture=2|min_marginal_quality_gain=0"]；default 2x1 multiple-choice expansion 仍被阻断，4x1 仍被阻断
阶段性结论：2x1 已经可以以“受约束画像”进入后台 shadow/admission 证据，但不能被解释成默认 2x1 复式晋级。下一阶段应让 recommendation runtime / cycle 读取 constraint profiles，把 2x1 运行时约束固定为 max_outcomes_per_fixture=1，把 3x1 保持默认画像，并继续阻断 4x1
```

V3.1-389 当前落地能力：

```text
按 V3.1-388 的结论，把 constraint-profile admission 接入 historical dynamic-mix runtime / audit；本轮不接新数据源、不接 VPS、不动 zeus、不改变默认生产 profile，也不向普通用户展示内部策略
新增 HistoricalDynamicMixFinalAnswerLaneConstraintProfile，记录 profile_key、pass_type、mode、constraint_profile_id、constraint_profile_json；HistoricalRecommendationBacktestOptions 新增 dynamic_mix_final_answer_lane_constraint_profiles
dynamic-mix lane 现在会先读取 effective constraint profiles：存在 profiles 时按 profile 生成 scenario，并对每个 scenario 分别应用 max_outcomes_per_fixture / min_marginal_quality_gain；不存在 profiles 时保持旧的 admitted/blocked pass type 行为
由于 constraint admission gate 的 blocked_pass_types 可能同时包含默认 2x1 阻断信息，runtime 在 profiles 存在时以 exact effective profiles 为准，不用 blocked_pass_types 粗粒度误杀受约束 2x1
historical final-answer market concentration audit 新增 --dynamic-mix-final-answer-lane-admission-gate-report；该参数会读取 effective_pass_types、blocked_pass_types 与 effective_constraint_profiles，并透传到 backtest runtime
summary_json / suite summary 新增 dynamic_mix_final_answer_lane_constraint_profiles 与 dynamic_mix_final_answer_lane_effective_constraint_profiles，报告 key 同步纳入 profile signature，避免不同约束画像共用同一缓存/报告身份
新增 deterministic tests 覆盖：multiple runtime 会消费 2x1 约束画像并把 max_outcomes_per_fixture=1 写入 lane explanation；audit CLI 能读取 constraint admission gate report 并生成 constraint profile options
真实 runtime smoke：configs/recommendations/historical_reports/football_data_co_uk_expanded_a_leagues_rolling_window_dynamic_mix_final_answer_lane_constraint_profile_runtime_smoke_5slice_v1.json；report_key=historical_final_answer_market_concentration_audit:51d2013edcaafd72；status=passed；slice_count=5；dynamic_mix_final_answer_lane_effective_pass_types=["2x1","3x1"]；effective_constraint_profiles=["2x1:multiple:max_outcomes_per_fixture=1|min_marginal_quality_gain=0","3x1:multiple:max_outcomes_per_fixture=2|min_marginal_quality_gain=0"]
runtime smoke 结果：candidate_completed_dynamic_mix_final_answer_lane_count=10；candidate_final_answer_dynamic_mix_final_answer_lane_count=5；dynamic_mixed_final_answer_count=5；candidate_final_hit_rate=1.0；candidate_roi=0.4899118745747538；candidate_profit_loss=4.899118745747538；failed_checks=[]
重要限制：30-slice combined profile-runtime smoke 超过本地 smoke 时间预算后已停止，说明 2x1+3x1 multiple profile 联合回放仍有组合成本；在进入日常 cycle 前，应继续做 cached/batched execution 或 candidate pre-filter，而不是重新陷入重型全量离线任务
阶段性结论：constraint-profile admission 已从报告证据进入 runtime/audit 口径；当前可以安全表达“受约束 2x1 + 默认 3x1”后台 shadow 运行，而默认 2x1 复式和 4x1 仍不进入有效 profile。下一阶段应把该 smoke 接入 benchmark/cycle 质量门禁摘要，并继续降低 profile 联合回放成本
```

V3.1-390 当前落地能力：

```text
按 V3.1-389 的结论，把 final-answer market concentration runtime smoke 接入 persisted benchmark quality gate 与 benchmark cycle；本轮不接新数据源、不接 VPS、不动 zeus、不改变默认生产 profile，也不向普通用户展示内部策略
historical_final_answer_market_concentration_audit 新增 load_historical_final_answer_market_concentration_audit_report，供 broader gate 复用既有 JSON 证据，不重复执行重型 historical backtest
benchmark quality gate 新增 final_answer_market_concentration_audit_report_path、require_final_answer_market_concentration_audit、min_final_answer_market_concentration_slice_count、min_final_answer_market_concentration_dynamic_mixed_final_answer_count、min_final_answer_market_concentration_effective_constraint_profile_count、max failed-check/warning count 等阈值
quality gate summary 新增 final_answer_market_concentration_audit_present/key/status/passed、slice/final_answer/dynamic_mixed count、effective_pass_types、effective_constraint_profiles、effective_constraint_profile_count、candidate dynamic-mix lane counts、failed_check_count、warning_count
benchmark cycle CLI 与 summary 同步透传上述字段；周期 runner 可以读取 V3.1-389 的 5-slice constraint-profile runtime smoke，作为“受约束 2x1 + 默认 3x1 profile 已真实进入 runtime/audit”的轻量证据
新增 deterministic tests 覆盖：quality gate 消费 final-answer market concentration audit、缺失 required evidence 会阻断、失败/样本不足/constraint profile 不足会阻断、quality gate CLI 参数映射、cycle CLI 参数映射、cycle summary 透传 gate evidence
重要限制：本轮只把已完成 runtime smoke 接入质量门禁摘要，不重新运行 30-slice combined profile replay；较大窗口的 profile 联合回放仍需要 cached/batched execution 或 candidate pre-filter 后再进入 routine cycle
阶段性结论：constraint-profile runtime evidence 已进入 benchmark/cycle 统一质量门禁。下一阶段应继续降低 2x1+3x1 multiple profile 联合回放成本，或转向 correct_score admission / 复式腿价值准入，避免重新陷入重型离线回放
```

仍待完成：

```text
dynamic-mix final-answer shadow lane 已在 210-slice 派生套件上通过 2x1-8x1 single 全量审计，并已完成 2x1/3x1/4x1 multiple 的 210-slice 分段门禁；3x1 可晋级，2x1 在 max_outcomes_per_fixture=1 约束画像下可恢复，默认 2x1 multiple-choice 与 4x1 仍阻断；admission 已升级为 pass_type + constraint profile，runtime/audit 已能消费 effective_constraint_profiles，benchmark/cycle 已能消费该 runtime smoke；下一阶段应降低 profile 联合回放成本
derived-market rolling-window suite 已具备让球/比分候选覆盖并通过 shadow gate，但当前真实 mixed final answer 仍主要是 cn_handicap_1x2 + european_handicap_1x2；下一阶段必须解决 correct_score admission 和复式腿只在确有价值时进入最终答案的问题
solver-backed optimizer 已接入 2x1-8x1 single/multiple 选择路径，最终答案质量门禁已改为 final-answer-only 口径，并通过 210-slice rolling-window 默认路径门禁；后续应继续寻找不降低最终命中率的分联赛/分赔率段质量函数、value guard 与仲裁权重
策略治理面板当前为证据读取与展示，不执行生产策略发布；auto 仅在推荐生成请求内动态解析
旧 parlay mock 推荐路径已从默认普通用户路径收缩为显式开发/测试兜底；后续可继续把详细 ParlayTicket 页面降级为内部/诊断入口
赛前核心流水线、核心回放报告、核心验证 CLI、基准矩阵 CLI、基准历史存储、历史读取 API、周期性 runner、质量门禁、cycle runner、preflight 与多 profile 本地 deterministic seed 已具备；后续应继续加入真实历史分布，而不是只依赖少量人工样本
全局最佳推荐规划器已能跨单式/串关/复式比较，锁定腿 API 到 persisted report 的端到端 smoke、successor persisted recompute、pipeline successor recompute 已完成；后续应扩大样本，加入赔率不利、真实 Provider 历史切片，并用历史 API/质量门禁/cycle runner 读取趋势
```
