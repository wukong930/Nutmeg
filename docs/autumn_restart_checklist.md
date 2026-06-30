# 秋天重启总清单(软水攒数据 → 测 → 决策)

**状态:🗺️ 主清单(master TODO)** · 记于 2026-06-24 · **下次真起点 = 欧洲受训联赛复赛(~8 月)**

> **怎么用**:这是把散在各 doc/记忆里的「秋天要做的事」**汇成一张表**,免得忘。每条带 ① 状态 ② 是「现在能做(cheap)」还是「数据门(等秋天)」③ 详情 doc。**机器基本就位;缺的只是受训联赛的前向已结算数据。**
>
> **一句话**:现在**空仓**,因为能测的市场(6 月只有锐利 WC + 薄盘)是错的;**13 个受训欧洲联赛 8 月复赛 = 真起点**。在那之前先做完 §0 的便宜 pre-work,让秋天的 EV 口径一开始就干净。

---

## 🔔 触发信号(已自动化,无需盯)
- **CLV 账本「选中计数器」**(`clv_ledger`,每日 02:00 settle cron 跑):受训联赛 +EV 腿首次出现时自动点名。
- **数据漏哨兵**(`data_freshness`):`jingcai_sp` / `jingcai_vote` / `odds_snapshots` 停长即桌面报警 —— 保证攒数据不静默中断。
- ⚠️ **但闸门阈值要先升级**(见 §0-2),否则点名了也不可信。

---

## §0 · 现在就能做的 pre-work(便宜、不等数据,让秋天口径干净)

- [x] **WPO 去 vig**(纠正冷门偏差,治冷门假 +EV)—— ✅ 已做(commit `1d2c4df`)。`docs/devig_method_comparison.md`
- [x] **CLV 闸门升级**(⭐)—— ✅ 已做。「选中计数器 N≥15/38」→ **① 每注 CLV 的 t 检验 ② BHY-FDR 跨联赛校正 ③ 预警(N≥15)/确认(t≥2.8·过FDR·N≥200)两层**;额外硬化:**CLV 按比赛日聚类**(防同轮相关高估 t)+ 单边检验。引擎 `nutmeg.v4.model.clv_gate`(纯函数 + 14 测试,含「同一联赛单独→确认 / 混入 11 个 null→仅预警」的多重检验铁证),已接进 `nutmeg-clv-ledger`。`docs/clv_statistical_methodology.md`
- [x] ~~**仪表盘 JS 去 vig → WPO**~~ —— ❌ 划掉(前提陈旧):EV 路径早已用服务端 WPO P(`_spcalcRecalc` 只算 `P×SP−1`),JS 里唯一的 basic 归一 `_devigArgmax1x2` 只挑 argmax 标签、换 WPO 不改结果。无 sub-1pp 缺口。`记忆 devig-js-server-mismatch`
- [x] **队名 join 卫生(信 CLV 数字前的前提)** —— ✅ 现在能做的已做。CLV 那条 join(`jingcai_sp↔odds_snapshots`)双重覆盖:① **哨兵**(`nutmeg-clv-ledger` 把 `no_close` 拆「名字疑似不配/真没报价/去vig失败」+ 自动报警,commit `ec094de`)② **国家队层别名感知**(`_pinn_close` 走 elo-code 唯一配 + 补 `Czechia/Korea Republic`,commit `792683d`;真库 151→**153/153**)。哨兵实跑当场抓到 `Czech Republic↔Czechia`。**俱乐部别名仍数据门**(秋天对真拼写补,哨兵兜底不静默漏)。`记忆 cross-source-team-name-mismatch`
- [x] **(可选)⑤ Kelly 补对抗核查** —— ✅ 已做(2026-06-25,两轮多 agent 对抗核查,5 条结论 5/5 已核、39 confirmed)。抓出 3 处改:§1 回撤数字降级为玩具算术、§3「外积」加条件(0-3 否决无条件版)、§4 删错引用 Laureti(改 Baker-McHale + Nekrasov)。结论方向不变:半 Kelly 默认 + 联合 stake 向量 + 强分数/RCK。`docs/kelly_staking_uncertainty_correlation.md`

---

## §1 · 秋天核心测量(数据门:受训联赛复赛 + 攒够已结算腿)

机器已就位(`nutmeg-handicap-triples` + `jingcai_sp` 初/终 + `clv_ledger` + `jingcai_exotic_sp`),到点喂数据即出。

- [ ] **① 按联赛切软水 CLV**:13 个受训欧洲联赛**单独**量(别混 WC/杯/北欧),`jc_* × Pinnacle 收盘 × 捕获 EV`。检验竞彩 SP 在公众钱重的盘上是否真软。`parlay_soft_water_research §8`
- [ ] **② 按「散户重仓 vs 冷门」切**(🆕 来自竞彩市场研究):竞彩按国内 handle 调线 → 偏差应在**大球队/大球/热门**。**这条可能比只按联赛切更能找到偏差。** `docs/jingcai_market_microstructure.md`
  - **🟢 数据源已就位(2026-06-30)**:`com.nutmeg.sporttery_vote` 每日 3 窗(11:10/17:00/23:20,合盖醒来补跑)抓官方 `getVoteV1` → 表 `jingcai_vote`(逐场三路**散户支持率** + 票数 + 体彩自算 implied/error + 竞彩 SP + EN 规范名)。**前进式无历史 = 从今天起攒**,秋天直接有量。**分析配方**:`支持率`(或 win/draw/lose 占比)join **Pinnacle 去vig P**(❌ 不是体彩自算 `*probability` —— 循环)+ 结果 → 量「散户重压 **且** 竞彩 SP 偏离 sharp」的腿。**质量/时点**:23:20 = 终盘封盘后主窗(逐场封盘=开赛前 5 分,各不同;upsert-latest 自动保留最接近各自封盘的一版 → 23:20 主抓晚场、17:00 兜早场;凌晨开球场是已知小局限,封盘真值在窗后)。监控:已接 `data_freshness` 哨兵 + 个人中心「数据新鲜度」。`记忆 jingcai-vote-support-endpoint`
  - **⏳ 待秋天补(数据门,现在 N 太小别建)**:① `settle_jingcai_vote` —— 把比分回填进 `ft_outcome`(表已有 `home_goals/away_goals/ft_outcome/settled_at` 列,照抄 `observation/jingcai_sp.py` 的 `settle_jingcai_sp`:按日 group、normalize_name 配队、`_ft_outcome` 判结果)。这是做 §1② 分析的前置(要结果才能量"偏差 vs 真实")。② 只读展示块 —— 一个 dashboard 卡片:散户支持 vs Pinnacle 去vig P,按「大球队/大球/热门」分桶看偏差方向+幅度。两者都**攒够已结算量、真动 §1② 时再上**,现在建=空转。
- [ ] **③ 冻结缺口测试**:`CLV vs 冻结→开球时长`;H1=**深夜欧洲场缝最大**(阵容在竞彩冻结后才出)。实证后盾:Kaunitz 开球前 1–5h +9.9% vs 收盘 +3.5%。`docs/freeze_gap_test_card.md`
- [ ] **④ 初盘 vs 终盘 EV**:`jc_open_*` vs `jc_*`,哪个对 Pinnacle 更划算。(最便宜的两个之一)
- [ ] **⑤ 比分/总进球 EV**:`jingcai_exotic_sp × DC 网格 P`。**权重排序锁死:聚合/「其他」桶 ≫ 总进球 ≫ 具体比分单格**;预期比分=最厚 vig 墙。`docs/score_grid_cell_calibration.md`
- [ ] **⑥ 数据源优化:500 档案当让球收盘 benchmark**(向前用,**≠** §3 的历史回填):一旦竞彩**让球 SP 向前**有了,500 的免费收盘级**亚洲盘口直接线**(Crown≈Pinnacle 收盘 1–4pp,回溯 2013)可直接算让球 CLV → **省 Odds API 配额 + 免 DC 反推让球**。`记忆 500-historical-odds-archive`

> 全部用 §3 方法(本会话测量脚本)。**结构 ≠ 绝对 +EV**:缝最大的桶仍可能整个埋在 −11% 墙里;绝对能不能投仍是软水数据门。

---

## §1B · 秋天数据门 · 贝叶斯引擎完善(显示侧,优先级低于软水)

> **为什么单列**:它改善的是**显示的模型 P + 模型↔市场融合**,**不是下注 EV**(软水才是下注 EV)→ 优先级低于 §1;但它**确实是秋天 PENDING**(需要 held-out 数据,与软水同一个数据门),**不是 §3 的「否决不建」**。`记忆 bayesian-blend-serving-gap`

- [ ] **serving 半**:当前 `bayesian_blend` = 粗糙的 **fixed-0.6 线性平均**,与那套 sound 的**几何 pooling** eval **脱节** → 把 serving 接上几何 pooling。
- [ ] **eval 半(`independent_signal.py`)**:补 ① **held-out/CV 的 β**(别用样本内)② **bootstrap 显著性**(防小 N 假阳)③ **per-regime / per-outcome β** ④ **下注相关指标**(ECE + 甜区,非纯 logloss)⑤ **model↔market 相关性**。
- **数据门**:需 held-out 数据(秋天攒的受训联赛预测)。**现在建 = 空转**(无 held-out)。
- **模型自我体检 = 同门金丝雀(已运行,别读 N=2 噪声)**:`模型自我体检·非竞彩`(predict-log → settle → Layer A 周校准 → scoreboard)**已在跑**(2026-06-30 核实:cron 绿、`league_predictions` 116 条/113 结算、周校准出报告),但屏上数字是 **N=2 噪声** —— 116 条里 114 条是市场盘(被 `n_market_blended_excluded` 排除),纯模型只 2 条(13 训练联赛休赛)。它是**回归金丝雀 + Layer A 校准的数据源**,**不是下注 edge**(模型=前沿,见 §4)。**留着跑、零维护;等纯模型已结算 N≥~100 再回头读 log-loss vs Pinnacle**(正是 eval 半要的 held-out)。`记忆 model-self-check-data-gated`

---

## §2 · 测出 +EV 才建(决策闸门过了再动手,否则空转)

- [ ] **串关决策引擎**:EV 门 + 单关/串关建议 + 分数 Kelly + 破产模拟。**设计已想清**(`parlay_soft_water_research §2`),有腿几天能上。
- [ ] **注额层**(加固):**默认半 Kelly**(对冲 P 是估的)+ **同时多注解联合 stake 向量**(别相加单注 Kelly)+ **相关/串关最小注**。`docs/kelly_staking_uncertainty_correlation.md`
- [ ] **B2 方差校正门槛接真闸门(替换平 +5%)**:纯函数 `model/ev_threshold.py`(`门槛=5%+z·σ_P·SP`)已建,前端 v59 只**并排显示**未接线。**数据门**:攒够「竞彩 SP × 已结算结果」后,直接回测"按方差门槛过滤 vs 平 5%,实盘命中/收益是否真更好",据此定 z、σ_P 终值 + 是否替换平 5%。**动的是下注决策规则本身,务必实证后再上**(方向已 71k 场实测:σ_EV∝SP、冷门腿不确定 3–7× 甜区;量级竞彩封盘档 σ_P≈1–1.5pp)。`docs/ev_threshold_variance_2026-06-26.md`、`记忆 ev-threshold-variance-sigmap`

---

## §3 · 搁置 / 不做(有理由,别手痒去建)

- [ ] **半全场(HT/FT)** —— 搁置:需半场模型 + Pinnacle 半场盘(仅顶级联赛覆盖)。`parlay_soft_water_research §7`
- [ ] **阵容反应管道** —— 不建:阵容边温和 + 「可利用滞后」被对抗核查否决;只经冻结缺口体现。`docs/lineup_information_edge.md`
- [ ] **密采竞彩日内轨迹** —— 不建:净位移就够,初/终两点是对的粒度。`parlay_soft_water_research §6`
- [ ] **Okooo/Betfair/价格侧历史回填** —— 不建:投入大产出薄 / 竞彩价格侧历史拿不到。**注意**:这里只否「**历史**回填」;500 档案当**向前**让球 benchmark 是 §1⑥(要做,别混)。`记忆 okooo-* / 500-historical-*`
- [ ] **让球反推 95%+ 大热区 calibration** —— 暂搁:10k 回测已证让球反推对 ≤92% 热门校准良好(略 OVER 热门,反方向),**唯 95%+ regime 未测**;等这类场攒够再抽查,别预设有问题。`记忆 handicap-reconstruction-calibration-tested`

---

## §4 · 范围边界:不在本清单里(在别处,没忘 —— 都不卡软水数据门)

> 这张表只管**软水/市场量化攒数据 campaign**。下面几条是**独立轨**,故意不当 §1–§3 的行项,但在这里点名,免得「以为忘了」。

- **建模线 = 已收敛/关闭(负结论,别重追)**:文章 #6 四候选(战意 / 球员 xG / 裁判 / 赔率路径)全测完**搁置** —— 模型对 Pinnacle 1X2 收盘**零独立信号**(β≤0),校准已透。这是 pivot 到市场量化的**证据**,不是待办。(球员 xG 仅在「**实时竞彩 SP 监控**」搭起来才值得回看,而那条本身在 §3 否决。)`docs/model_improvement_findings.md` / `v12_deep_audit.md`
  - **同格 · MCMC 分层贝叶斯进球模型 = 待确认候选 `V12-8`**(替 DC MLE 骨架):V11 Phase 0 手搓 MH 在 EPL 单季 −6.4 milli log-loss、R-hat 1.058(借线收敛)。**决策准则**:NumPyro NUTS 复核 **≥3/4 季 ≥−0.005 且 R-hat<1.05 才迁移**,否则留 DC MLE(3–5 天 + ~500MB 依赖)。**但 MCMC(1.0567)仍 +0.0227 输 Pinnacle**(只是把模型↔市场差距从 +291 收窄到 +227 万分之一 nat,没越过)→ 同属建模线、被 pivot 降权。**注意 ≠ §1B 的 `bayesian_blend`**:V12-8 是换**骨架**,§1B 是 serving **融合**,同名不同物。`docs/v11_phase0_mcmc_report.md` / `V12_BACKLOG_DRAFT.md V12-8`
- **V13 产品/UI roadmap(独立轨,不卡数据)**:闭门 banner(P0)· 人为 override `data/overrides.yaml` · 半自动 SP UX(cron 稳定后)· 单关/复式 web 下注 directional_combo arm。`docs/V13_ROADMAP.md`
- **Polymarket 错价探测器(真·开放决策)**:Phase A 已上线(只读源+匹配+缺口+CLI),**B/C(面板+cron)等你看一次真实 `nutmeg-polymarket-gaps --dry-run` 再定**;若全是薄盘/翻盘排除/陈旧 = 诚实「此路不通」,停在 A。**无决策 doc,易忘。** `计划 codex-flickering-dewdrop`
- **V12 收尾 housekeeping(低优先)**:真实 ROI 靠 `nutmeg-ab-report` 攒数周 · 生僻新队拉丁名回退看到就补 · 删 DEPRECATED `/recommend/wc/single` + `national_team_handicap.py`。`docs/V12_MARKET_MODE_WRAPUP.md`

---

## 🧭 大方向(本会话研究的总结论,定 V12+)
1. **预测已到顶,市场赢了** → 别堆模型,深耕**市场量化**(CLV/冻结缺口/软水/只赌方向)。`docs/forecasting_frontier_vs_market.md`
2. **软水论无外部文献 → 我们是唯一研究者** → 自建测量栈 = 唯一证据通道,继续投。`docs/jingcai_market_microstructure.md`
3. **CLV 是记分牌,但要严格量**(t 检验 + FDR),不臆造 +EV,空仓等秋天。

*详情索引:`parlay_soft_water_research.md`(软水主文)· `freeze_gap_test_card.md` · `score_grid_cell_calibration.md` · `devig_method_comparison.md` · `clv_statistical_methodology.md` · `kelly_staking_uncertainty_correlation.md` · `lineup_information_edge.md` · `sharp_money_market_microstructure.md` · `forecasting_frontier_vs_market.md` · `jingcai_market_microstructure.md`*
