# 全面体检与审查评估 · 2026-07-15(第三次)

**状态:📋 方案(Phase 0–1 只读,待口令;Phase 2 修复逐项口令)**
**前作**:07-01 初检 · 07-03 二检(`docs/health_check_2026-07-03.md`,元病根 =「注册表/词典/字段清单即开关」)
**本次组织原则**:不按模块扫,**按病根家族猎** —— 围绕 2026-07-15 一天挖出的 4 个真 bug 的共同签名(**静默降级**),并以**秋季复赛**为截止线做就绪审查。

---

## 0 · 为什么现在、为什么这么组织

07-15 从一个 null 问题(clubelo 补回)顺藤摸出 4 个真 bug,**全是同一族**:

| 今天的 bug | 家族 |
|---|---|
| team_state 冻 724 天,rest_days 喂 724 | 冻结不报警 |
| football-data 的 Pinnacle 断供 **5 个月**无人知 | 上游死亡不报警 |
| crown upsert 的 SET 漏了 home_team → 补词典永远无效 | 写路径不传播 |
| train.py 温度校准静默跳过,artifact 照常出厂 | 静默跳过 |

每一个都**不崩、不叫、看着像成功**。问题不是这 4 个 —— 是**还有多少个同族的**。

## 1 · 病根分类学(猎物清单)

- **D1 冻结不报警**:资产老化无哨兵(哨兵只看采集表,不看**模型供应链**:源树/parquet/artifact 年龄)
- **D2 上游死亡不报警**:源还在发、关键列却空了(列在≠数据在)
- **D3 写路径不传播**:upsert 的 SET 漏列;词典改进传不到已有行
- **D4 静默跳过**:关键步骤 if-无-else;fail-soft 用在了不该软的路径上
- **D5 词典/注册表即开关**(07-03 元病根,已复发 ≥6 次):5 套队名系统并存、标签分裂、日期语义混用
- **D6 配置漂移**:.env 覆盖默认值、live plist ≠ setup 脚本、daemon 不热加载
- **D7 冻结时代测量污染**:2024-08 冻结盘 → 2026-07-15 换盘之间,一切被它记录/拟合的测量数据

## 2 · 方案

### Phase 0 · 盘点(只读,~20 min)
资产清单落一张表:20 个 cron、5 个 DB、数据目录树、**5 套队名系统**(TEAM_NAME_ZH / _ZH_OVERRIDES / TEAM_ALIASES / CUP_TEAM_ALIASES / national_alias)、CLI 注册面(pyproject vs 实际)、文档里所有「已完成」声明。

### Phase 1 · 七线取证(只读,并行 subagent,~2 h)

| 线 | 猎 | 方法 |
|---|---|---|
| **L1 数据供应链存活** | D1 D2 | 逐源探活 + **关键列 liveness**(不只 HTTP 200,查最近 N 行关键列非空率):clubelo 周更 / eloratings TSV / sporttery 三端点(getVote·getFixedBonus·matchcalc)/ 500 hisdata / api-football。⚠️ Odds API **只读心跳与既有日志,不打真调用**(配额已尽)。训练供应链年龄探针:football-data 树 mtime、外部 parquet 空文件计数、**artifact 年龄** |
| **L2 静默降级机械扫描** | D3 D4 | ① 全库每个 `ON CONFLICT DO UPDATE` 做 **SET-vs-INSERT 列差集**(今天在 crown 抓到一个;odds_snapshots / jingcai_sp / vote / exotic 全查)② 全部 `except-fail-soft` 分类:**采集路径=可软但须计数暴露;训练/测量路径=必须响**③ 全部 `*_available`/默认填充特征(elo=1500、form=NaN、lineup 零回退、fatigue 零回退)④ 关键步 if-无-else(温度那类) |
| **L3 训练/服务偏斜对账** | D6 | **40 特征 × {train pipeline, build_features_for_fixtures, EV 路径} 三上下文逐格来源表**。已知待确认:C1 修正仅服务侧、blend 线性 vs 几何(punch-list)、market 特征训练=football-data 收盘 vs 服务=Odds API 活线、双 artifact(cat vs cat_lineups)谁在哪被用 |
| **L4 测量仪器与冻结污染** | D7 | league_predictions / scoreboard / calibration_journal / weekly 报告 **按 artifact 时代切分**(2024-08 盘 vs 07-15 新盘);冻结时代行的隔离/打标策略;live_vs_backtest 基线是否需重置;**种子①已探**(见 §3) |
| **L5 自动化与配置漂移** | D6 | `launchctl print` × 20 逐一对账 setup 脚本(记忆:live plist 会漂);**artifact 解析链**(.env 覆盖 → 指针 → DEFAULT);`resume_odds_crons.sh` 在今天一系列变更后仍有效?;daemon 重启纪律;`_clear_proxy` 家族漏 ALL_PROXY 的全部调用点 |
| **L6 代码/仓库/DB 卫生** | — | 全套测试疆界(**Playwright 11 个常败**→ 隔离 lane 或 skip-unless-server 决策);ruff 债务**净数**(此前统计口径出过错);死代码候选(`data/v4_model` 老盘、stacker/ensemble、stadium/fatigue skeletons);仓库杂物(**根目录有个叫「0」的文件**);DB `integrity_check` + WAL 尺寸 + 备份轮转实证;`.bak` 清理策略 |
| **L7 论题与资源审查评估** | — | **边缘台账**:活的(vote×CLV,唯一)带门与读数节点;死的(软水/读盘/内部一致性/Elo 补强/情绪三角/AH 直读…)各带墓碑与「别再重跑」链接,防翻案;配额/时间烧耗;**秋季就绪记分卡**(硬门:odds cron 恢复、retrain+ingest cron、validation_days 动态化、vote 攒量) |

### Phase 2 · 判级 + 修复波次
沿 07-03 惯例:**P0(当天修)/ P1(秋前)/ P2(随秋)**;每一发现三件套(**证据 / 爆炸半径 / altitude 修法** —— 修共享 sink/canonicalizer,不逐生产者打补丁)。修复与提交**逐项口令**。

## 3 · 带进去的种子(不是白手起飞)

- ~~🔴 P0 候选~~ → **🟠 P1(已探,降级)**:`live_T_correction.json` **不存在**(find 全盘为空)→ 新盘当前干净(恒等 T)。**但** `weekly_calibration_check` cron 在跑,拟合源 = `league_predictions`(116 行**全是冻结时代记的**);W29 报告「No change」。**条件性风险**:秋天 N 涨后一旦 `--apply`,冻结时代偏差会被拟合成修正施加到新盘 → **修法 = league_predictions 加 artifact 时代戳,拟合窗过滤**。
- 🟠 **P1 候选**:`DEFAULT_ARTIFACT_PATH="data/v4_model"` 指着 **2025-06 的老 LightGBM 盘**(team_state 陈旧 410 天)。今天差点因此误诊 —— **.env 一丢/没 source,daemon 静默换服老模型,零报错**。
- 🟠 **P1 候选**:`data_freshness` 只看采集表,**不看模型供应链** —— 724 天正是从这个盲区进来的。修法 = artifact 年龄 + 训练源新鲜度探针进哨兵。
- 🟠 **P1 候选**:5 套队名系统并存 —— 第 7 次复发只是时间问题。altitude 修法 = 单一 resolver 门面 + 生成式一致性测试。
- 🟡 对账:07-03 记忆称「Wave 1-3 待做」,任务台账显示 W2-x/W3-x 已完成 —— **以代码为准裁决,更新记忆**。
- 🟡 疆界:Playwright 11 个常败测试,每轮全套都要人肉排除一次。

## 4 · 纪律

只读优先;中国站清代理(**含 ALL_PROXY**)/外站留代理;**不打烧配额的 Odds API 调用**;不碰 .env 值;cron 改动需「授权改 cron」;修复/提交/重启逐项口令;每一发现必须带可复现证据。

## 5 · 交付

本文件从「方案」长成「报告」(P0/P1/P2 表 + 波次,同 07-03 格式);记忆更新(`health-check-guardrails` 追加或裁决);修复按波次分 commit。

---

# 报告区(Phase 0–1 已完成 · 2026-07-15)

## ⭐ 执行摘要

**总判定:管道健康度高,无正在燃烧的 P0。** 19/19 cron 零漂移、CLI 注册面 59/59 闭合、4 库 integrity ok、备份轮转正常、全套测试 exit=0、供应链 7 源里 6 活 1 死(已知)。但按「静默降级」病根家族猎出 **20+ 个同族潜伏点**,并撞出**一个改变日程的发现**和**两个互相耦合的决策**。

### 三个待 owner 决策(按耦合顺序)

| # | 决策 | 背景 | 状态(2026-07-15 owner 拍板) |
|---|---|---|---|
| **D1** | **恢复 3 个 odds cron?** | 🟢 **配额已月度重置**(本次体检发现:cup_market/predict_log 两路 07-13 起每日成功调 Odds API;配额探针静默=高于报警线)→ 可比原计划**提前 ~6 周**恢复。`bash scripts/resume_odds_crons.sh`(已验证与暂停状态互为镜像)。**⚠️ 必须先定 D2** | ⏸ **待 owner 口令**(D2 已定 → 前置已清,随时可恢复;秋季欧洲复赛前为硬期限) |
| **D2** | **`v4_model_cat_lineups` 怎么处理?** | 它**今天没重训**(仍 cutoff 2024-08-01 = 冻结未愈),却是 `morning/daily_recommend` 两个 cron 的默认盘(现因缺 CSV 每日 exit 1)。**一恢复 odds cron 它们自愈复活,立刻用冻结模型往观察库写 lineup_aware 臂 → weekly_gate/ab_report 读数中毒**。三选一:①重训它(--with-lineups,一条命令)②两 cron 改指 v4_model_cat ③暂停两 cron | ✅ **选②,已执行**:recommend/rec/recommend_pool 三个 CLI 默认 + run_local_server.sh 兜底切到 `data/v4_model_cat`(cron 不传 --model,靠 editable install 吃默认值 = 零 plist 改动);roi_backtest 保留 lineups 引用作显式 A/B 工具。锁:`tests/v4/test_calibration_canon.py::TestD2RecommendDefaults` |
| **D3** | **温度口径二选一** | 服务端**从未应用** artifact 温度(评估卡的 log-loss 含 T=0.904,线上吐裸 grid P;Layer A live_T 被设计为运行时通道但文件缺失=恒等)。幅度小(ΔNLL≈0.0008)但系统性。选:①服务端接上 artifact T(live_T 叠加其上)②宣布「裸 P+Layer A」为唯一口径、评估改对齐 | ✅ **选②,正典化**:「裸 grid P + Layer A live_T」= 唯一线上口径;artifact T 只用于评估可比,routes 仅 ModelInfo 回显。正典注释入 train.py 温度段;机械锁:`tests/v4/test_calibration_canon.py::TestD3TemperatureCanon`(routes 出现次数==回显×2)。读评估 log-loss 记得差一个 T(ΔNLL≈0.0008) |

### 病根家族收获统计

D1 冻结不报警 ×3(哨兵不看模型供应链 / lineups 盘未愈 / train 默认输出目录指没人服务的 v4_model)· D2 上游死亡 ×2(polymarket keyset 422 绿灯空转 / football-data 已知)· D3 写路径不传播 ×6(upsert SET 漏列,**含今天本体自己修 crown 时漏掉 rangqiu**)· D4 静默跳过 ×8(钱路概率源劈叉零 log / 哨兵自盲 / 测量 CLI 丢行不计数…)· D6 配置漂移 ×4 · D7 测量污染 ×2(league_predictions 无时代标 / scoreboard 全史=裸 P)。

### 修复波次

- **Wave 0(当天,cheap)**:✅ **已执行 2026-07-15**(D2✅ D3✅,D1 ⏸ 待口令):
  - 钱路劈叉曝光:routes `_market_reverse_handicap_probs` 反推失败 + `_fixture_to_match_input` fit_lambdas 失败两处 except 加 warning log(行为不变,只让降级可见;顺手补了缺失的 `import logging` —— ruff 基线对比抓到的,不然曝光日志自己会 NameError 炸穿降级路径,恰是体检要防的病)
  - polymarket offset-cap 修:`fetch_soccer_game_events` 接住 422 "offset too large" → 视为到底、接受已抓近期页(events 按 startDate 升序,深页=远期);其它错误照旧抛。回归锁:`TestPolymarketOffsetCap`
  - D2/D3 执行(见决策表)+ 正典锁测试 `tests/v4/test_calibration_canon.py`(7 tests)
  - 删根目录游离「0」文件
  - 验证:新测试 7/7 过;全套 2406 passed + 1 xfailed;ruff 逐文件 vs HEAD 零新增
- **Wave 1(本周,sink 级收口)**:✅ **已执行 2026-07-15 当天**(测试锁 = `tests/v4/test_hc_wave1.py`,17 tests;全套 2431 passed):
  - **6 张表 upsert 全列收口**:wc_log 身份四列进 SET(结算列天然保留)· pinnacle_close 补 commence_utc/ingested_at + NULL-snapshot 永久冻结解除(IS NULL 分支)· crown 补 rangqiu(COALESCE)+ match_date/league_cn/home_zh/away_zh/ingested_at + **第二 UNIQUE 双 ON CONFLICT 子句**(500 换发 match_id 时迁移行,不再 IntegrityError 重复丢)· score_ev INSERT OR REPLACE → upsert 只更捕获列(改期重赛不再冲掉 won/settled_at)· jingcai_sp handicap_home COALESCE · prediction_log psc_*/kickoff_utc COALESCE(护栏从 caller 收进 sink)
  - **D7 时代过滤**:`prediction_log.CURRENT_ARTIFACT_ERA_START = 2026-07-15T07:00`(单一事实点,下次重训须更新/秋季 retrain cron 自动化);`fetch_league_predictions` 默认只吐当代(scoreboard/predict_report 两个读者自动干净);auto_calibration **两条喂料臂都卡下界**(竞彩 session 流 max(cutoff, era) + league_predictions 流 recorded_at >= era —— 只修一臂就是 R2.5 的病)。5 个 auto_calibration 测试文件的合成 fixture(now−50d 回填,跨界)加 autouse monkeypatch 把界推史前
  - **哨兵自盲**:name_sentinel fixtures 全失败 → `SentinelBlindError` + latest 文件写 ⛔ + exit 1(不再「没比赛=没错配」假绿);0 联赛可扫 → 「无结论」非 ✅;data_freshness 配额探针失败 → `(alarms, probe_failures)` 双通道,失败可见但不冒充配额报警
  - **模型供应链探针**(`check_model_supply_chain`,--no-supply 可关):artifact 年龄(trained_at_utc,缺则 mtime;>120d 报警=724 天冻结的疫苗)· 源树最新 CSV 年龄(>120d 报警;有目录无 CSV=训练无粮报警)· 空 parquet 计数(121/459 基线,只报数);报警同乘 exit-1 推送链;缺目录=跳过(CI 安全)
  - **served-with-defaults 计数**:persist 服务循环记未知队(Elo=1500+form NaN,带队名前 5)+ rest_days>45d 分布外腿数,一批一条 warning(行为不变);测量 CLI fit-drop 曝光:clv_ledger/jingcai_staleness 逐行带线值警告、handicap_triples 聚合计数、prediction_log settle join-miss 计数(别名嫌疑点名)
  - **运维脚本**:teardown 加 `TEARDOWN_EXCLUDE`(jingcai_history_trickle 不再被 glob 误删)+ 修正「setup 唯一 writer」失真注释;setup 加 disabled-job 前置闸(检测到有意暂停的 cron 诚实拒绝重跑,指路 resume_odds_crons.sh,不复活暂停件)
- **Wave 2(秋季,随重训)**:market_handicap_line 服务恒 NaN 的去留 · market close-vs-live 语义(登记为已知尺子偏斜)· retrain/ingest cron · 5 套队名系统 resolver 门面 · CLI 第三校准态统一

---

## R0 · Phase 0 盘点结果

- **cron 面**:20 个已装(3 个 odds cron 暂停中,不在列表 = 正确)。`jingcai_history_trickle` 仍在跑 —— **非僵尸**,还在合法回填(总 63,610 行,近日 5–9k/日,今日 08:59 仍在写;完成后按记忆 bootout)。
- **DB 面**:4 库 `quick_check` 全 ok;主观测库无 WAL 残留(检查点 cron 在干活);备份轮转正常(每日 03:30,留 10 份)。
- **CLI 面**:pyproject 59 注册 vs cli/ 60 模块(差值疑为 `__init__.py`,待 L5 agent 确认)。
- **杂物**:根目录空文件「0」(2026-06-03)→ 删除候选。git 未跟踪/改动 41 条(多为惯例外置物)。
- **ruff 债务净数**:729(E,F,I,B,UP,SIM 全仓)—— 存量债,零新增闸口逐 commit 把守。

## R1 · L1 数据供应链存活(7 源)

| 源 | 判定 | 证据 |
|---|---|---|
| clubelo | ✅ 活 | 探针返回 Arsenal 历史行;358 parquet,51 空(=日职,正确);周更 cron 已装 |
| eloratings | ✅ 活 | World.tsv 直读成功;`data/external/eloratings` 07-11(上周六 cron)|
| sporttery 网关 | ✅ 活 | 端到端:`jingcai_sp`/`jc_open`/`vote` 全部今日有捕获;裸探 matchcalc 403 = 缺请求头,非源死 |
| 500 hisdata | ✅ 活 | 今日回填 2,104 场(本日早些时候实证)|
| api-football | ✅ 活 | `match_outcomes` 今日 0d(settle 链端到端);`data/external/api_football` 5-30 未动 = 静态缓存,非工作路径 |
| **Odds API** | ✅ **已复活** | **配额已月度重置**:`cup_market`+`predict_log` 两路 **07-13 起每日成功写入**(今日 73+30 行);配额探针静默(耗尽时会报「credit 0」)⇒ **3 个 odds cron 可提前 ~6 周恢复** |
| football-data | ✝ 半死(已知) | Pinnacle 列 2026-01-14 起永久空;其余庄家活。无自动更新路径(仍无 ingest cron,按既定决策留秋季)|

**哨兵行为核验 ✓**:odds 暂停以 `odds_snapshots[closing] 3d STALE` 形式**可见**地报着 —— 不是静默;设计正确。

## R4 · L4 冻结时代测量污染

- `league_predictions`:**263 行**(2026-05-31 → 今日),其中**冻结时代 236 行 / 新盘时代 27 行**,**无任何版本标识列** → `weekly_calibration_check`(拟合源就是它)与 prediction-scoreboard 的读数会**混时代**。修法:era 过滤(`recorded_at < 2026-07-15T07:00Z` 视为冻结代)写进 auto_calibration 拟合窗 + scoreboard 查询;或加列打标。⚠️ 当前无 `live_T_correction.json`(新盘干净),风险是**未来第一次 --apply**。
- `calibration_journal` 7 行、`single_predictions` 36 行(同样无版本列;但属用户行为表,量小)。

## R-发现 · 新捕获的静默降级(本体线)

- **🟠 F-PM(P1)· polymarket 采集绿灯空转 4 天**:Polymarket 弃用深 offset 分页(`offset=2100 → 422 "use /events/keyset"`),翻页器越界 → 抓取中途失败 → **零写入、exit 0**。07-12 = soccer 开放事件数涨过 2100 的那天。修:接 keyset 或 cap offset + 局部成功仍提交;抓取失败必须非零退出/报警。(D2 上游契约变更 + D4 静默跳过 双料)
- **🟢 F-QUOTA(行动项)· Odds API 配额已重置**:见 R1。恢复 = `bash scripts/resume_odds_crons.sh`(需口令 + 授权改 cron);恢复后 closing 哨兵红灯应消,`pinnacle_close_history` 续采(训练锚+CLV 地基)。

## R7 · L7 论题与资源审查评估

### 边缘台账(活 1 · 死 10 —— 墓碑防翻案)

**活的(唯一)**:
| 论题 | 门 | 状态 |
|---|---|---|
| **vote × CLV(散户回避腿)** | 前向 vote 攒量 → 秋季读数(预注册 S2) | ✅ 在采(06-30 起,530 快照,今日 09:00 仍新);机器全部就位 |

**死的(各带墓碑,禁止无新证据翻案)**:
| 论题 | 判决 | 墓碑 |
|---|---|---|
| 软水(任何联赛/市场/腿/档) | null | 07-09 §H 历史判决:HAD×11+HHAD×3 全 null,竞彩=Pinnacle 影子+恒 12.9% 税;前向 P2 照跑但预期不解锁 |
| 外盘读盘玄学(诱盘/反向) | null | 3,709 场三重证伪(`asian-handicap-line-reading-null`)|
| 竞彩内部跨盘软点 | null | 比分↔HAD 差 1.58pp≈0(`jingcai-internal-crosspool-consistency-null`)|
| 模型=独立第三票 | 死 | 模型≈sharp(0.017),情绪三角关闭 |
| 外部 Elo/评分补强模型 | null | **今日**:clubelo 剂量-反应完全平(`clubelo-null-not-underestimated`)|
| 模型提前定价/预测线移动 | null | **今日实测**:分歧 vs 线移动 r≈0;353 场热门反转命中 36.8%≈随机 33% |
| 冷门=软 | 反杀 | 深冷 SP≥6 最烂(−14.1%);竞彩上架半薄场加肥 vig |
| freeze-gap 独立策略 | 太薄 | 机制 REAL 但 +5% 门槛仅 0.4% 场次;派奖哨已 web 证伪 |
| AH 直读/让球反推 | 关闭 | 三方回测 tied;唯一产出 C1 已冻结部署 |
| okooo / Sportmonks | 死/不买 | 反爬二手 / 无收盘史且贵 |

### 资源与秋季就绪记分卡

| 硬门 | 状态 |
|---|---|
| ① odds cron 恢复(实盘锚+训练锚) | 🟢 **本次体检发现配额已重置 → 现在就能恢复**(原计划等 8 月);待口令+授权改 cron |
| ② retrain/ingest cron | 🟡 秋季(validation 动态化为前置;静默出厂已有硬闸 `47435ce` 兜底) |
| ③ vote 攒量(唯一活边缘的粮) | ✅ 三窗 cron 在采 |
| ④ 预注册仪器 | ✅ v1.6 冻结,测试绿 |
| ⑤ scoreboard/校准读数前置 | 🟠 需先做 era 过滤(R4/F3),否则秋季读到混时代数字 |
| ⑥ polymarket 采集 | 🔴 keyset 分页修复(F-PM) |

**一句话评估**:管道健康度高(供应链 6/7 活、备份/哨兵/闸门运转正常),病根家族的**新增样本收敛在两处**(polymarket 空转、league_predictions 无时代标);**战略上项目已完成从「找更准的模型」到「量化人群偏差」的转向,秋天的赌注干净地压在 vote 一条线上,而本次体检把它的前置(锚、粮、仪器)全部点验了一遍。**

## R5 · L5 自动化与配置漂移(subagent 取证)

**主判定:管道高度同步 —— 19/19 交集 job 命令串(变量展开后)逐字符 MATCH;暂停三件套与 `resume_odds_crons.sh` 互为镜像(label/路径/enable+bootstrap 顺序全对,幂等);CLI 注册面 59 条 0 断链 0 孤儿;18/20 job source .env,两个不 source 的均合规。**

发现(按严重度):
1. **🟠 F-TRICKLE(P1 操作陷阱)**:`jingcai_history_trickle` 游离于装机/卸载体系 —— `teardown_local_pipeline.sh` 的 glob 会把它**永久删掉**,而 setup 不会装回;teardown 里「setup 是 com.nutmeg.* 唯一 writer」的注释已失真。缓解:它本是抓完即 bootout 的短期 campaign job(当前回填到 2024-05 窗口,距终点还有数日)。修:要么登记进 setup(带 self-bootout 注释),要么在 teardown 排除表加名。
2. **🟠 F-RERUN(P1 操作陷阱)**:「setup 可安全重跑」当前不成立 —— 三个 odds job 处于 `disabled`,重跑 setup 会在 `bootstrap` 第 2 个 job 处 `exit 1` 中断,且解决后会**复活被有意暂停的 cron**。修:setup 的 install_job 先 `launchctl enable` 或跳过 disabled;或文档注明「暂停期间禁重跑 setup,恢复只用 resume 脚本」。
3. 🟡 22/23 plist `plutil -lint` FAIL(裸 `&&` 未转义)—— **既有惯例,launchd 宽容,按记忆不修**;登记为「任何严格 plist 工具都读不了」的已知限制。
4. 🟢(设计如此)`morning/daily_recommend` 自暂停日起每日 exit 1(fixtures CSV 停在暂停日)—— fail-loud 正确行为,**恢复 odds cron 后自愈**;期间纯日志噪音。
5. 🟡 trickle 不受 `NUTMEG_SPORTTERY_ENABLED` 总开关门控(不 source .env),唯一停法是 bootout —— 与设计一致,登记为盲点。

## R2 · L2 静默降级机械扫描(subagent 取证;10 upsert + 141 宽接 + 11 降级点 + if-闸全筛)

### R2.1 upsert 差集(按危险度)

| # | 位置 | 发现 | 级 |
|---|---|---|---|
| 1 | `observation/wc_log.py:157` | wc_predictions 冲突键=fixture_id,**SET 漏 match_date/home_team/away_team**;kickoff_utc 每天刷新但派生的 match_date 不刷 → 改期跨日后两列自相矛盾;settle 镜像(:255)用首见身份写 match_outcomes,让球 rec 带下注时新身份 → **AF 改名/改期后 rec 永久 still_unknown** | **P0-verify**(WC 正在收官周) |
| 2 | `observation/pinnacle_close_history.py:56` | SET 漏 **commence_utc**(改时刻永不传播;§H CLV 地基表);附带:某行 snapshot_utc 为 NULL 则 `WHERE excluded.snapshot_utc > …` 永假 → 该行**永久冻结** | P1 |
| 3 | `observation/crown_close_history.py:85` | **今天的修复不完整**:队名补了 COALESCE,**rangqiu(让球线,喂 C1)不在 SET** —— 与被修 bug 同构;另撞第二 UNIQUE(match_date,home_zh,away_zh)时 ON CONFLICT(match_id) 不接 → 异常被吃、该行每次重抓重复丢 | P1 |
| 4 | `cli/score_ev_forward.py:103` | INSERT OR REPLACE 不含结算四列 → 改期重赛(完场→又回 UPCOMING)时 REPLACE **把已结算行的 won/settled_at 冲成 NULL** | P1 |
| 5 | `observation/jingcai_sp.py:165` | handicap_home **无 COALESCE**(同表 psc_*/jc_open_* Wave3 都加了;姊妹表 vote 的同列有)→ None 抹线 | P1 |
| 6 | `observation/prediction_log.py:102` | psc_*/kickoff_utc 无 COALESCE(空值冲 sharp 基准);当前唯一 caller 先过滤所以不可达 —— **护栏在 caller 不在 sink**(反 altitude) | P2 |

干净:polymarket_gaps、store.upsert_outcome、vote、exotic、odds_snapshots(纯追加)等 7 处。

### R2.2 关键路径静默吞(141 处宽接中筛出)

- **🔴 routes.py:687**(`_fixture_to_match_input` fit_lambdas 失败 → pass 零 log):**钱路概率源静默劈叉** —— 1X2 用 de-vig fair、grid 留在模型 λ。**P0-verify**
- **🔴 routes.py:621**(让球市场反推失败 → return None 零 log):F1 让球 EV 静默降级为模型 grid。**P0-verify**
- 🟠 routes.py:236(SP 库读失败 → 全部卡片 EV 框静默消失)
- 🟠 **name_sentinel.py:66 哨兵自盲**(取 fixtures 失败→「没比赛=没 mismatch」假绿)+ **data_freshness.py:199/211 配额探针失败 → pass**(恢复 odds cron 后就靠它确认配额,探针坏了无信号)
- 🟡 测量 CLI 逐行丢弃不计数:clv_ledger.py:96 / jingcai_staleness.py:105 / handicap_triples.py:127(grid 拟合失败丢行 → 深线系统性掉队偏置 CLV/S6,报告只见 N 变小)
- ✅ 采集侧基本达标(log+计数;ingest_national_elo 的 n_failed/n_empty 与 settlement 的 counts["errors"] 是范本)

### R2.3 服务降级点(11 个,**0 个有运维可观测信号**)

未知队→Elo 1500(persist.py:370,升班马全中,无计数)· **rest_days 无 OOD 守卫**(:400,724 事件的着火点,至今裸奔)· Pinnacle 1X2 缺→NaN(market.py:49,**连模型内旗都没有**,唯一无旗 market 族)· clubelo 空 parquet 静默跳过(:77,自毁两个月无感的通道)· lineup 零伤病/fatigue 全零/开盘 drift=0(仅模型内旗)· 训练侧有跨联赛 Elo 兜底而服务侧裸 get→1500(**不对称 skew**)。

### R2.4 静默 if-闸

- 🟠 **prediction_log.py:225 settle join-miss → continue 零计数**:队名断裂无声蚕食「模型记分板」的 N(已是 N=2 噪声级)—— clv_ledger 有 name-suspect 拆分,这里没有。
- 🟡 predict_log.py:115:Pinnacle 断供期(现在就是)整天静默跳过,无掉行计数。
- 🟡 auto_settle --quiet 压掉全部 INFO(log mtime 撒谎家族又一例)。
- ✅ auto_calibration/auto_retrain/weekly_report/clv_ledger 主闸门全部带 reason+journal,**无发现**。

### R2.5 模式确认(元发现)

> 修复习惯 =「在出事的那一列/那一个 caller 打补丁」:crown 修队名漏 rangqiu(**今天本体亲犯**)、jingcai_sp 修 psc_* 漏 handicap_home、prediction_log 护栏放 caller。**收口方式 = 以共享 sink 为单位做全列审计,一次修完一张表。**

## R3 · L3 训练/服务偏斜对账(subagent 取证 + 本体复核)

**40 特征 × {训练, 服务} 全查完;9 项偏斜按爆炸半径排序:**

1. **🟠 温度只拟合不服务(本体已复核坐实)**:`temperature_T` 全库消费点 = 训练拟合(train.py:378)+ 存盘(persist.py:122)+ **ModelInfo 回显**(routes.py:842/907/959/976)+ 评估应用(walk_forward.py:173)。**服务预测路径零应用**;唯一运行时校准 = live_T_correction.json(routes.py:179 注释自证这是设计通道)——当前缺失=恒等。⇒ **评估卡 log-loss 含 T,线上吐裸 grid P**(T=0.904<1,线上偏钝);predict_log→scoreboard 全史都是裸 P 口径。幅度小(拟合时 ΔNLL≈0.0008)。**缓解:钱路不吃模型 P**(EV had 腿= Pinnacle 去vig routes:1906;hhad=市场反推 :1681)。→ **D3 决策**
2. **🔴 `v4_model_cat_lineups` 消费环带病**:该盘**今日未重训**(cutoff 仍 2024-08-01,与 .bak 内容相同);是 `morning/daily_recommend` cron(未传 --model)与 4 个 CLI + run_local_server 的**默认**;现因喂料 CSV 死(odds 暂停)每日 exit 1 = 暂时无害;**odds cron 一恢复即自愈复活,以冻结模型写 lineup_aware 臂 → weekly_gate/ab_report 中毒**。→ **D2 决策,恢复前必须处理**
3. **🟠 market 特征:训练=收盘(PSCH/PC>2.5/AHCh)vs 服务=当前活线**(API-Football 镜像+Odds API 覆盖,TTL 缓存):模型学「收盘→结果」,服务喂随时点漂移的盘中线。尺子类偏斜(EV 锚独立),登记为已知口径。
4. **🟠 `market_handicap_line`:训练几乎全有(Pinnacle 小数收盘线),服务几乎恒 NaN**(gather 链从不产 ahch;persist.py:344 回退竞彩整数线也通常空)——8 个 market 特征之一在服务端长期失能,CatBoost 走 NaN 分支。秋季重训时决定去留。
5. 🟡 `market_total_over_2_5` 线错配:2.5 未挂时喂主亚洲线(2.25/2.75)价格但按 2.5 语义(odds_parser.py:337)。薄盘轻度失真。
6. 🟡 elo/form/rest:公式逐字等价(diff/p_home/快照重建三处对过),偏斜是**结构性快照冻结 + 无 retrain cron**(已知,秋季件);服务侧无训练侧的跨联赛 Elo 兜底(裸 get→1500,不对称)。
7. ✅ clubelo/xg_lite/league:代码零偏斜;clubelo 51/358 空 parquet 的队服务时 available=0(自愈闸+周更已就位)。
8. 🟡 C1 修正:**服务/落库 4 处 c1=True,测量路径(clv_ledger/staleness/triples)全 raw** —— 与设计注释一致,但秋季读让球台账须记口径差 δ=1.3-1.9pp。
9. 🟡 双 footgun 合流:`DEFAULT_ARTIFACT_PATH='data/v4_model'`(routes:112,.env 一丢静默服 24 特征老 LightGBM)+ `train.py DEFAULT_OUTPUT_DIR='data/v4_model'`(**裸跑 nutmeg-train 会写进没人服务的目录,静默空转**)。
10. ✅ 备份目录(.superseded/.bak×2)零代码引用 = 纯还原点;Layer B 指针休眠。

## R-验证 · 两个 P0 候选的复核结果

- **wc_log SET 漏列**:`wc_predictions` 102 行**当前零身份漂移**(kickoff日≠match_date = 0)→ 潜伏陷阱非现行火灾,**降 P1**(进 Wave 1 upsert 收口)。
- **温度不服务**:坐实(见 R3-1),幅度小 → **P1-决策(D3)**。

## R6 · L6 卫生汇总

4 库 quick_check ok · 备份每日 03:30 留 10 份 · 全套测试 **exit=0**(今日三跑三绿) · ruff 存量债 729(零新增闸口逐 commit 把守) · Playwright 11 常败待隔离 lane(P2) · 根目录「0」空文件删除候选 · `data/external/api_football` 5-30 未动=静态缓存非工作路径(settle 链经 DB 证活)。
