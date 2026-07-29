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

## 🚨 复赛第一件事:恢复 odds cron —— 它现在是**仅存的 Pinnacle 源**

2026-07-15 实测:**football-data.co.uk 从 2026-02 起永久停发 Pinnacle**(`PSCH/PSCD/PSCA` 列还在但全空;全联赛同步归零:英超 0/145 · 西甲 0/166 · 德甲 0/129 · 意甲 0/156;其他庄家全满;同期 schema 120→132 列重排庄家名单)。**全库有 Pinnacle 的最后一天 = 2026-01-14。**

生产模型 40 特征里 8 个 market 特征(`market_p_*`/`market_logit_*`/`market_overround`)**全部**来自这三列,且它们是主力特征 → **训练行从此永远卡在 2026-01-14,不再增长**。

⇒ 因配额暂停的 3 个 odds cron(`bash scripts/resume_odds_crons.sh`)抓的 `pinnacle_close_history`,**从「CLV 地基」升级为「CLV 地基 + 模型训练的唯一锚」**。复赛前不恢复 = 两样一起断。详见 `记忆 pinnacle-dead-in-footballdata-2026-01`。

**皇冠评估完毕 + 已回填 —— 但结论和当初设想的不一样**(`docs/crown_anchor_evaluation_2026-07-15.md`)。
- ✅ **线是好线**:两个配对 bootstrap 都打平(①线本身 0.9674 vs 0.9683 ②Pinnacle 训的模型**服务时**改喂皇冠 0.9594 vs 0.9604,CI 均跨 0)。⚠️「Crown≈Pinnacle **1–4pp**」是**尾部**,典型=中位 **0.6pp**。
- ✅ **已回填** 2026-01-14→07-15:**2,104 场**,表 3,709→5,813,缺口回收 **829/2,115 = 39.2%**(比分一致 100%)。
- ⛔ **但【不要】把皇冠行混进训练集** —— 已用数字否掉(该文 §9):缺口期**所有 Pinnacle 列一起死**,`market_total_over_2_5`(**第 4 重要特征**)皇冠只有 **21%** 是 2.5 线 → 填=编造、留 NaN=残缺;而收益仅 **+2.7%** 的行。判例:同日 clubelo 覆盖翻倍 = 剂量-反应完全平。**训练行卡在 2026-01-14 可以接受**(team_state 新鲜度不依赖赔率,已解冻)。
- 🚨 **它解决不了【实盘锚】** —— 500 是赛后档案,EV 要赛前活线 ⇒ **上面那句「必须恢复 odds cron」不因此打折。**
- ✅ **它真正的位置 = 下面的 §1-⑥(CLV)**:500 档案**就是竞彩比赛列表** → 按定义 100% 覆盖我们下注的宇宙(「密度只有 60%」在 CLV 场景**不是缺点**)+ 免费不烧配额。**库里那 2,104 场是 §1 CLV 的料,不是训练集的料。**

### 连带:retrain / ingest cron 推迟到这时一起装(2026-07-15 决定)
今天已手工完成一次解冻(见 §0 最后一条),但**没装 cron**,因为现在装等于装一个明知会崩的东西:
- `--validation-days 227` 是**钉死在 2026-01-14 这个日期上的 hack**(要 cutoff 取满让 `team_state` 新鲜,又要验证窗跨过 01-14 才有 Pinnacle)。秋天 cutoff 一前移,窗口整体滑进无 Pinnacle 区 → **val 为空,温度校准必崩**。必须改成动态值,或换 Pinnacle 源。
- football-data **没有 ingest CLI**(2526 那 13 个 CSV 是手工 curl 的),要装 cron 得先写抓取器。
- 每次 retrain 后 daemon 需 `launchctl kickstart -k`(`_artifact_cache` 常驻内存)。Layer B 的 `live_artifact_pointer.json` 能免重启,但 `write_artifact_pointer()` 要求真实 ship-gate p 值,解冻式重训没有 → 别为了用它编数字。

---

## §0 · 现在就能做的 pre-work(便宜、不等数据,让秋天口径干净)

- [x] **WPO 去 vig**(纠正冷门偏差,治冷门假 +EV)—— ✅ 已做(commit `1d2c4df`)。`docs/devig_method_comparison.md`
- [x] **CLV 闸门升级**(⭐)—— ✅ 已做。「选中计数器 N≥15/38」→ **① 每注 CLV 的 t 检验 ② BHY-FDR 跨联赛校正 ③ 预警(N≥15)/确认(t≥2.8·过FDR·N≥200)两层**;额外硬化:**CLV 按比赛日聚类**(防同轮相关高估 t)+ 单边检验。引擎 `nutmeg.v4.model.clv_gate`(纯函数 + 14 测试,含「同一联赛单独→确认 / 混入 11 个 null→仅预警」的多重检验铁证),已接进 `nutmeg-clv-ledger`。`docs/clv_statistical_methodology.md`
- [x] ~~**仪表盘 JS 去 vig → WPO**~~ —— ❌ 划掉(前提陈旧):EV 路径早已用服务端 WPO P(`_spcalcRecalc` 只算 `P×SP−1`),JS 里唯一的 basic 归一 `_devigArgmax1x2` 只挑 argmax 标签、换 WPO 不改结果。无 sub-1pp 缺口。`记忆 devig-js-server-mismatch`
- [x] **队名 join 卫生(信 CLV 数字前的前提)** —— ✅ 现在能做的已做。CLV 那条 join(`jingcai_sp↔odds_snapshots`)双重覆盖:① **哨兵**(`nutmeg-clv-ledger` 把 `no_close` 拆「名字疑似不配/真没报价/去vig失败」+ 自动报警,commit `ec094de`)② **国家队层别名感知**(`_pinn_close` 走 elo-code 唯一配 + 补 `Czechia/Korea Republic`,commit `792683d`;真库 151→**153/153**)。哨兵实跑当场抓到 `Czech Republic↔Czechia`。**俱乐部别名仍数据门**(秋天对真拼写补,哨兵兜底不静默漏)。`记忆 cross-source-team-name-mismatch`
- [x] **(可选)⑤ Kelly 补对抗核查** —— ✅ 已做(2026-06-25,两轮多 agent 对抗核查,5 条结论 5/5 已核、39 confirmed)。抓出 3 处改:§1 回撤数字降级为玩具算术、§3「外积」加条件(0-3 否决无条件版)、§4 删错引用 Laureti(改 Baker-McHale + Nekrasov)。结论方向不变:半 Kelly 默认 + 联合 stake 向量 + 强分数/RCK。`docs/kelly_staking_uncertainty_correlation.md`
- [x] **秋季分析预注册(⭐ 防 forking-paths,§0 收尾件)** —— ✅ 已做(2026-07-02)。闸门管住了联赛间多重检验,但**分析菜单本身**(联赛×切片×玩法×时点=上百种组合)的自由度没人管 → 数据到达前把「确认性(P1 合并 + P2 逐联赛闸门,唯一动钱入口)vs 次级预指定(S1 冻结缺口/S2 散户逆向/S3 玩法差/S4 初终盘/S5 B2 方差门槛,自成 FDR family)vs 探索性(禁动钱)」+ 解锁流程 + kill 规则 + 读数前置全部写死。**顺带修了真雷**:`jingcai_sp` 双 writer 联赛标签分裂(芬超 vs FIN_VEIKKAUSLIIGA 同联赛两组 → 稀释 N + FDR family 多算成员)→ `league_labels.canonical_league` 归一进 `clv_ledger`(fail-open,读数前标签审计兜底)。`docs/autumn_prereg_analysis_plan.md`

- [x] **生产 artifact 解冻(⭐ 2026-07-15,读 scoreboard 的前置)** —— ✅ 已做。查 clubelo 时撞见:生产 CatBoost 的 `team_state`(Elo + 12 个 form 特征)**冻在 2024-05**,381 队全部;服务时 `rest_days` 算出 **724 天**(训练只见过 3–14)= 分布外;`training_cutoff` 还是 2024-08-01,连源里已有的 24/25 赛季都没学;40 特征里 **26 个是冻的**(elo 4 + form 12 + xg_lite 10),只有 market 8 + clubelo 5 + league 新鲜。**不是钱的 bug**(`routes.py:1876` docstring 铁证 `EV = P(Pinnacle de-vig) × 竞彩SP − 1`,下注不经模型)**是尺子的 bug** —— `prediction-scoreboard` 一直在给戴镣铐的模型打分,而 §1 秋季计划正是去读它。
  修法:补 25/26 赛季 13 联赛 CSV → 重训(`--validation-days 227`,见上方 🚨)→ 换盘 + `launchctl kickstart -k`。结果:`team_state` **724 天 → 45 天**(= 赛季末,休赛期正确值;秋季首轮 `rest_days` ≈ 76 天 = 训练里每个赛季首轮的正常量级)· 队数 **381→445**(多出的 64 队是升班马,老快照里根本没有 → 只能吃 elo=1500 默认 + form 全 NaN)· `n_train` **21,469→29,347**(+37%)· 温度 0.9004→0.9039(几乎没动 = 校准性格稳)。`/health` 已验证上线。可回滚:`data/v4_model_cat.superseded-20260715`。`记忆 production-artifact-frozen-724d`
- [x] **clubelo 补回 = null(别再补外部 Elo)** —— ✅ 已测,封档。干净对照(唯一变量 clubelo 48.8%→82.4%)下**剂量-反应完全平坦**:数据一字节没变的西甲移动 0.0048(= 全局重训的噪声地板),剂量拉满的意甲(0→100%)移动 0.0050 **且方向错**;池化层 4 模型 3 个变差。因 `market_p_*` 已是特征,**Pinnacle 价格对球队强弱的编码远胜 Elo = 冗余**。生产 CatBoost **0.9952 vs Pinnacle 0.9942 = 仍然输** → 主轴(模型=前沿,赢不了收盘线)加固而非推翻。新卡 `docs/v4_baseline_card_clubelo_restored.md`(旧卡留着做对比)。`记忆 clubelo-null-not-underestimated`

- [ ] **§6 名字哨兵改双层解析(🆕 2026-07-28 加入 —— 假阳性率已高到会让人开始忽略它)**

  **病情(已定位到行,不是猜)**:哨兵与它要监督的 overlay **用了不同的解析深度**。
  - 哨兵 `cli/name_sentinel.py:121`:`h, a = _norm_team(home), _norm_team(away)` → `if (h, a, diso) in lk: continue` —— **单层**
  - overlay `data/sources/odds_api.py:601-609`:`exact = (_norm_team(...), ...)` 之后还有 `hks, ch = [exact[0]], _club_core(home)` —— **双层**

  ⇒ 只要第一层没中,哨兵就报「疑似错配」,而 overlay 靠第二层**照常匹配成功**。

  **证据**:2026-07-28 体检报 2 条,**2/2 全是假阳性** ——
  `Bodo/Glimt → Bodø/Glimt`(挪超 ø)、`Dundee Utd → Dundee United`(苏超缩写)。
  实测两边**根本没有同时使用两种拼写**(`Bodø/Glimt` 和 `Dundee United` 在
  `jingcai_sp` 里 0 行),且 Bodo/Glimt 的 6 行竞彩数据 **psc 补录 6/6 全成功**。
  加上此前记录的 3/8,累计假阳性已占多数。

  **为什么要修(这才是重点)**:哨兵的价值**全部**在于「它响 = 真有事」。
  一旦大多数报警是假的,人就会开始跳过它 —— 那时一次**真**的 join 断裂会静默通过,
  而这个哨兵存在的唯一理由就是防这个。**狼来了的哨兵比没有哨兵更危险。**

  **修法**:把哨兵的匹配判定改成**复用 overlay 那套完全相同的多层 key 构造**
  (理想是抽成一个共享函数,两边都调 —— 「修共享 sink 别逐生产者打补丁」的同一条
  altitude 规则),而不是在哨兵里再抄一遍 `_club_core`(抄一遍 = 下次 overlay 加
  第三层时又漂)。

  **验收**:改完重跑,今天这 2 条应当消失;同时**必须造一个真断裂的用例**证明它
  仍然会响(否则「修好」可能只是把哨兵改哑了)。

- [ ] **Playwright `networkidle` flaky(🆕 2026-07-28 加入)**

  **病情**:`tests/v4/test_e2e_playwright.py::test_dashboard_loads_with_title` 用
  `page.wait_for_load_state("networkidle")` 等页面就绪。但面板自 V11 P1-FE#6 起有
  **自动刷新轮询**(Visibility API 驱动)—— 一个持续发请求的页面**按定义永远到不了
  networkidle**,能不能过全看轮询恰好落在哪。2026-07-28 全套里红了一次,**单独重跑
  3/3 全过**;diff 只有 4 个 δ 常数 + 2 个测试文件,碰不到页面加载。

  **为什么要修(和 §6 哨兵同一个道理)**:间歇性红的测试会训练人跳过它。一旦养成
  「playwright 红了?重跑一下就好」的习惯,**一次真的前端回归也会被同样处理掉**。
  flaky 测试的危害不是它红,是它**教会你忽略红色**。

  **修法**:把 `networkidle` 换成 `domcontentloaded` + **显式等目标元素**
  (`expect(page.locator(...)).to_be_visible()`)。轮询页面本来就不该用 networkidle ——
  这不是调参数,是选错了等待条件。全文件扫一遍,其他用例若有同样写法一并改。

  **验收**:连跑 10 次全绿;并且**故意把某个断言的目标元素改名,确认它会红** ——
  否则「修好」可能只是把等待条件放宽到什么都不检查了(与 §6 哨兵验收同构的陷阱)。

- [ ] **日职 δ **单独**测(🆕 2026-07-29 加入 —— ⚠️ 要花额度,开之前先看 §「不要混」)**

  **可得性已确认(零成本,查的是现有缓存)**:`data/external/odds_api/historical_
  sports_soccer_japan_j_league_odds/` 里有历史快照样本,**Pinnacle 在**,
  `h2h` + `totals` 两个市场都有,`sport_key = soccer_japan_j_league` 已映射
  (`odds_api.py:131`)。⚠️ 只有 J1;J2 是 Odds API 根本没有,别去找。

  **缺口规模**:竞彩日职让球 571 场,其中 **±1 线 570 场(−1: 360 · +1: 210)**,
  分布在 **260 个不同比赛日**(2021-08-03 → 2025-07-27)。football-data
  **不覆盖日本** ⇒ 这批在 v2.0 的 4,934 场里一场都没有,且不是 bug、补不回来。

  ## ⛔ 不要混进欧洲那条 δ —— 这是硬阻塞

  现在 δ 的口径是 **football-data 的 `PSCH/PSCD/PSCA`(Pinnacle 收盘)**;
  Odds API 给的是**某时间戳的快照**(样本里 Pinnacle `last_update` 是开球前
  8 分 29 秒)。**两者不是同一个量。** A′ 当初做过换锚检验(皇冠 vs Pinnacle,
  −1 线 +4.2 vs +4.6pp)才敢说「换锚不变形」—— 日职这批没有任何检验支撑。

  ⚠️ 而且混进去**不可分离**:δ₋₁ 会变成 3,131 场 football-data 锚 + 360 场
  Odds API 锚的加权平均,**你再也无法回答「换锚有没有让它变形」**。

  ## 为什么仍值得做(但作为**独立**测量)

  混着做只买到 ~1pp 的下界改善(+1 线 SE 0.0101→~0.0096),不值 1 万额度。
  但**单独**做买到的是**新信息**:日职是竞彩常年上架的联赛,自成一个人口 ——
  若它的 δ 与欧洲显著不同,那本身就是发现,而且它与 σ_P v2.1 问的是同一个
  问题(**校准量是否依赖人口**)。σ_P 那边已经测到国内联赛 vs 杯赛差 1.6×。

  ## 成本 + 一个已知会引爆的坑

  历史端点单价 = `10 × markets × regions` = 10×2×1 = **20 credits/次**。260 个
  比赛日、同日不同开球时刻要分批取近收盘 ⇒ **2–3 次/日 = 10,400–15,600 credits**,
  是该 key 全部 20,000 额度的**一半到四分之三**。

  ⚠️ **`记忆 odds-api-historical-pricing-and-empty-window-trap` 会在这里全面引爆**:
  该时段没赛事时端点**不报错**,返回**最近可得快照**。260 个日期里只要有一批取回
  错误时段而消费方没按 `commence_time` 严格卡窗 ⇒ **静默污染**。抓取器必须先写
  窗口闸门 + 拒绝计数,再花第一分钱。

  ## 预注册天然干净

  数据**要花钱才拿得到** ⇒ 判据可以现在钉死,而评估数据此刻不在手上
  (与 σ_P v2.1 同一个成色来源,和 δ v2.0「已看过数」那种不干净情形相反)。
  开做之前先写 prereg:锚口径怎么声明、日职 vs 欧洲的同源性怎么判、
  什么结果算「不同人口」、以及**不达标就不部署**。

  **验收**:① 窗口闸门的拒绝计数 > 0 时能看见(不是静默丢);② 日职 δ 与欧洲 δ
  的对比走同源性检验而不是眼看;③ 无论结果如何,**都不混进现有常数**。

---

## §1 · 秋天核心测量(数据门:受训联赛复赛 + 攒够已结算腿)

机器已就位(`nutmeg-handicap-triples` + `jingcai_sp` 初/终 + `clv_ledger` + `jingcai_exotic_sp`),到点喂数据即出。

> ⚖️ **确认性/探索性边界以 `docs/autumn_prereg_analysis_plan.md`(预注册 v1.1)为准**:下列 ①–⑦ 里只有「逐联赛 CLV 闸门(P2)」能解锁资金;②③④ 对应预注册 S2/S1/S4(次级,不动钱)、**⑦=探索性(禁动钱·自成 FDR·不进 P2,新发现不得塞进冻结的确认性 S 假设)**;v1.1(2026-07-04)增 **S6 让球切分偏差复现 + C1 修正式冻结**(网格在 |h|=1 让胜 +2.8pp/让平 −3.1pp 切偏,让负=锚分毫不差;C1=让胜→让平挪 δ=2.8pp,**S6 过 FDR 才准进服务端**;禁再试 rho/亚盘直读;源 `docs/ah_vs_grid_three_way_backtest_2026-07-04.md` 附录);数据到达后改口径必须在预注册 Changelog 留痕且只对未读数据生效。

- [ ] **① 按联赛切软水 CLV**:13 个受训欧洲联赛**单独**量(别混 WC/杯/北欧),`jc_* × Pinnacle 收盘 × 捕获 EV`。检验竞彩 SP 在公众钱重的盘上是否真软。`parlay_soft_water_research §8`
- [ ] **② 按「散户重仓 vs 冷门」切**(🆕 来自竞彩市场研究):竞彩按国内 handle 调线 → 偏差应在**大球队/大球/热门**。**这条可能比只按联赛切更能找到偏差。** `docs/jingcai_market_microstructure.md`
  - **🟢 数据源已就位(2026-06-30)**:`com.nutmeg.sporttery_vote` 每日 3 窗(11:10/17:00/23:20,合盖醒来补跑)抓官方 `getVoteV1` → 表 `jingcai_vote`(逐场三路**散户支持率** + 票数 + 体彩自算 implied/error + 竞彩 SP + EN 规范名)。**前进式无历史 = 从今天起攒**,秋天直接有量。**分析配方**:`支持率`(或 win/draw/lose 占比)join **Pinnacle 去vig P**(❌ 不是体彩自算 `*probability` —— 循环)+ 结果 → 量「散户重压 **且** 竞彩 SP 偏离 sharp」的腿。**质量/时点**:23:20 = 终盘封盘后主窗(逐场封盘=开赛前 5 分,各不同;upsert-latest 自动保留最接近各自封盘的一版 → 23:20 主抓晚场、17:00 兜早场;凌晨开球场是已知小局限,封盘真值在窗后)。监控:已接 `data_freshness` 哨兵 + 个人中心「数据新鲜度」。`记忆 jingcai-vote-support-endpoint`
  - **⏳ 待秋天补(数据门,现在 N 太小别建)**:① `settle_jingcai_vote` —— 把比分回填进 `ft_outcome`(表已有 `home_goals/away_goals/ft_outcome/settled_at` 列,照抄 `observation/jingcai_sp.py` 的 `settle_jingcai_sp`:按日 group、normalize_name 配队、`_ft_outcome` 判结果)。这是做 §1② 分析的前置(要结果才能量"偏差 vs 真实")。② 只读展示块 —— 一个 dashboard 卡片:散户支持 vs Pinnacle 去vig P,按「大球队/大球/热门」分桶看偏差方向+幅度。两者都**攒够已结算量、真动 §1② 时再上**,现在建=空转。
- [ ] **③ 冻结缺口测试**:`CLV vs 冻结→开球时长`;H1=**深夜欧洲场缝最大**(阵容在竞彩冻结后才出)。实证后盾:Kaunitz 开球前 1–5h +9.9% vs 收盘 +3.5%。`docs/freeze_gap_test_card.md`
- [ ] **④ 初盘 vs 终盘 EV**:`jc_open_*` vs `jc_*`,哪个对 Pinnacle 更划算。(最便宜的两个之一)
- [ ] **⑤ 比分/总进球 EV**:`jingcai_exotic_sp × DC 网格 P`。**权重排序锁死:聚合/「其他」桶 ≫ 总进球 ≫ 具体比分单格**;预期比分=最厚 vig 墙。`docs/score_grid_cell_calibration.md`
- [ ] **⑥ 数据源优化:500 档案当收盘 benchmark ⬅ 升级为皇冠的【主用途】(2026-07-15)**。原写「向前用」,现在**数据已在库**:`crown_close_history` **5,813 行 · 2024-08-01→2026-07-14**(2026-07-15 回填了 2,104 场)。皇冠 = 锐利收盘价**已实测**(和 Pinnacle 配对打平,CI 跨 0;⚠️「1–4pp」是尾部,典型中位 **0.6pp**)。**它在 CLV 场景比 Odds API 更合适**:500 档案**就是竞彩比赛列表**(URL 里 `jczq`)→ 按定义 **100% 覆盖我们下注的宇宙**;**免费不烧配额**;还给**亚洲盘口直接线** → 免 DC 反推让球。**待做**:接进 `clv_ledger` 当第二/免配额锚 + 复赛后装每日增量 cron。**join 必走 `utils/team_canonical.to_v4_canonical` + 比分硬闸门**(别造新别名表、别模糊匹配)。`docs/crown_anchor_evaluation_2026-07-15.md` §10
- [ ] **⑦ 按「竞彩选择的 overround 带」切软水**(🆕 2026-07-07 只读实测,**探索性·禁动钱**):竞彩选场系统性挑**高效市场**(上架 Pinnacle overround **2.9%** vs 拒绝 **7.1%**,剔 WC 仍 4.0 vs 7.3,小国欧战资格赛被跳=薄到 10%)= **0/33 软水 null 的隐藏变量已量化**——能投的宇宙 by construction = 足球最高效子集,我们一直在池塘最清那半捞。秋季两件:
  - **(a) 描述性复跑**(免动钱·免预注册):国内联赛复赛后重跑「竞彩上架 vs 我们追踪 · Pinnacle overround」,确认这条选择边界**不是 WC 档期假象**(本期 78 场拒绝里多数是 WC/小国欧战)。脚本照本会话:`jingcai_sp ↔ odds_snapshots` 按 date+归一队名 join,每场取近收盘一条快照算 overround=1/H+1/D+1/A−1。
  - **(b) 探索性边缘切片**(⚠️ **禁动钱·自成 FDR·不进 P2**):把 ① 的逐联赛 CLV **按竞彩上架场的 overround 带**再切一刀(超流动 ~2.5% vs 半流动 ~3.7–5%),测残余软水是否**集中在半流动在校联赛带**(H:边缘只来自方向性散户偏差 / freeze-gap,**不来自市场薄**)。**这是对 P2 确认性数据的新切轴 = forking-path 风险 → 只作探索性;若出假设须另立预注册**(同 S2 候选纪律,发现期数据不得回喂确认性检验)。
  - **🔒 已定死的反向结论(别手痒)**:**冷门 ≠ 软**。拒绝集那些薄场(overround 6–10%)= 不确定 = 方差陷阱(σ_EV 巨大,`记忆 ev-threshold-variance-sigmap`);竞彩真上架半薄场多半自己加最肥 vig = **最硬水**。**软水搜索不往冷门转**,竞彩跳过薄场 ≈ 替我们挡方差。选择 ≠ 结果 alpha(死路,别挖)。
  - **Forward-only 守卫**(不急):竞彩几乎不越出可追踪联赛(142 场只 1 漏)→ 要守的是让 `odds_snapshots` 始终是竞彩菜单**超集**;把「竞彩菜单 vs 我们追踪」覆盖 diff 并进 `nutmeg-registry-coverage`(`记忆 health-check-guardrails`),秋季联赛轮换若竞彩上架了我们没跟的会主动报。`记忆 jingcai-selection-function-measured`
- [ ] **⑧ A-3 冻结带进闸 = 条件项,触发才做(2026-07-18 与 owner 定)**。背景:A-2 显示已上线(`7e1391a` v100:EV ± = A′ δ ⊕ 冻结带平方和 + ⏳徽章,**判闸零改动**);A-1 测量 `docs/freeze_gap_measurement_2026-07-18.md`(σ_主(h)=0.79pp×h^0.31,41% 凌晨场中位缺口 6h)。**默认不做**:冻结漂移=零均值逐场独立噪声(实测均值偏移 −0.04pp),≠ δ 那种跨票同向的系统性校准偏差 → 理论落点是仓位/门槛分级,不是硬下界;能过现闸的腿本来 ~0.4% 场次,改判区间一季碰不到几张。**两个触发信号(任一出现才启动)**:
  - **(a) 反模式信号**:秋季实盘反复(≥3 次)出现「绿灯、但 ⏳ 大到不敢下」的真实犹豫 —— 说明在用口头补丁替代定价 = 滑向「绿灯+口头禁令」反模式(A′ 判例,`记忆 handicap-reconstruction-calibration-tested`),该显性化进闸;
  - **(b) 赢家诅咒信号**:回测或实盘发现**现闸绿灯票**里,长缺口(>4h)场的实现 ROI 显著差于短缺口场(方向一致 + 过显著性)—— 零均值噪声在「只挑显示 +EV」的选择效应下真的在咬人(与 ③ 的 CLV-vs-冻结时长测量共用数据,读数口径以 ③ 为准)。
  - **触发后的形态(锁死,防走样)**:σ_freeze(距开球) **并入门槛分级的 σ_EV**(与冷门陷阱 `记忆 ev-threshold-variance-sigmap` 同一机制),**不是**「点估−2σ 硬下界」;属 S1×S5 家族,动手前:①预注册修订(v1.8)②先用历史推荐账本 × 冻结缺口回测「会砍哪些票、砍得对不对」。不触发 = 不做,A-2 的显示已把信息给全。
- [ ] **⑨ δ₂(±2 让球线)部署决定 + 秋季重测**(测量已完成 2026-07-20,`docs/handicap_delta2_measurement_2026-07-20.md`):−2 双锚交叉验证——让胜(净胜3+)**+6.4±2.5pp 高估**且 P̄≈39% 落甜区 = 现有护栏(冷门门槛/δ₁ 带)全罩不住,幻影 EV +12~20% 可直接过闸;让负 −4.3±2.7 低估;A′ 同管线 ±1 自检重现(fd +4.34 vs A′ +4.6)。**待决**:(a) δ₋₂ 按 A′ 形态部署(让胜 −0.064/让负 +0.043/判闸下界,进闸须 **prereg v1.8**,owner 口令);(b) **+2 不出常数**(N≈40+42 两锚量级 4~15pp 钉不住,方向同家族)→ 涓流 P1 回填 25-26 数据后重测;±3+ 继续未校准。⚠️皇冠 join 用中文名+日期(match_id 不同 id 空间)。

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
- [ ] **B2 方差校正门槛接真闸门(替换平 +5%)**:纯函数 `model/ev_threshold.py`(`门槛=5%+z·σ_P·SP`)已建,前端 v59 只**并排显示**未接线。**数据门**:攒够「竞彩 SP × 已结算结果」后,直接回测"按方差门槛过滤 vs 平 5%,实盘命中/收益是否真更好",据此定 z、σ_P 终值 + 是否替换平 5%。**动的是下注决策规则本身,务必实证后再上**(方向已 71k 场实测:σ_EV∝SP、冷门腿不确定 3–7× 甜区;量级竞彩封盘档 σ_P≈1–1.5pp)。**🆕 σ_P 有了 τ 维度(2026-07-02 快照轨迹实测)**:σ_P(τ) 从贴收盘 1.16pp 单调爬到 4 天前 3.3pp,freeze-gap 时窗(3–24h)≈收盘档 1.4–1.8×——B2 公式的 σ_P 应取 σ_P(τ) 曲线而非常数;恒等映射无过杆系统性成分(fav 漂移 +0.8pp 全桶同号但 t<2.8=暗示性,登记探索性),漂移修正模型不建。`docs/close_drift_measurement_2026-07-02.md`(`scripts/measure_close_drift.py` 秋季重跑出联赛别曲线)、`docs/ev_threshold_variance_2026-06-26.md`、`记忆 ev-threshold-variance-sigmap`

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
- **Polymarket 错价探测器(决策已落,2026-07-01)**:Phase A 早上线(只读源+匹配+缺口+CLI)。**真实 dry-run 已跑**(154 足球盘→5 配到 fixture→15 缺口,**今天全 low-tier**:France-Sweden 客胜「+11.3%」被 `longshot:8pp` 自动降级,其余 `within_tick` —— 正是 MOSS 缺的方差守卫)。**决策 = 开 C(cron),但定位「只读测量」非下注**(Polymarket 对 CN 有地域+法律墙;价值 = 攒 model/Pinnacle-vs-Polymarket 缺口时间序列,交叉校验我们自己的线 + 日后按 tier 算 realized 命中率)。`com.nutmeg.polymarket_gaps` 10:00/16:00/23:30 三窗、record+settle 一遍过、**强制走代理**(外网,净 launchd 环境够不着;代理挂则当天 fail-soft 0 行)、已 kickstart 实证写 15 行。**B(面板块)仍可选/缓**。Off-switch:`launchctl bootout …/com.nutmeg.polymarket_gaps`。`计划 codex-flickering-dewdrop`
- **V12 收尾 housekeeping(低优先)**:真实 ROI 靠 `nutmeg-ab-report` 攒数周 · 生僻新队拉丁名回退看到就补 · 删 DEPRECATED `/recommend/wc/single` + `national_team_handicap.py`。`docs/V12_MARKET_MODE_WRAPUP.md`

---

## 🧭 大方向(本会话研究的总结论,定 V12+)
1. **预测已到顶,市场赢了** → 别堆模型,深耕**市场量化**(CLV/冻结缺口/软水/只赌方向)。`docs/forecasting_frontier_vs_market.md`
2. **软水论无外部文献 → 我们是唯一研究者** → 自建测量栈 = 唯一证据通道,继续投。`docs/jingcai_market_microstructure.md`
3. **CLV 是记分牌,但要严格量**(t 检验 + FDR),不臆造 +EV,空仓等秋天。

*详情索引:`parlay_soft_water_research.md`(软水主文)· `freeze_gap_test_card.md` · `score_grid_cell_calibration.md` · `devig_method_comparison.md` · `clv_statistical_methodology.md` · `kelly_staking_uncertainty_correlation.md` · `lineup_information_edge.md` · `sharp_money_market_microstructure.md` · `forecasting_frontier_vs_market.md` · `jingcai_market_microstructure.md`*
