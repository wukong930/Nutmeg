# 全面体检 2026-07-03 — 「拉取最新盘口/SP」链路全解剖

**方法**:7 个并行只读审计 agent(数据源/存储结算/引擎数学/主 API/观测 API/前端/运维哨兵),狩猎清单 = 本周实测的 5 个新鲜度 bug(瑞超队名、韩职字典、韩职 sport key、大田源顶、北京午夜日期窗)的 7 个类;免打扰清单 = 已实测关闭项。关键发现经协调人抽查对抗验证(3/3 坐实)。**触发动机**:用户报"拉取最新 SP 反复出问题"。

**总账**:P0 ×2(全在监控层)· P1 ×2 簇 + 若干独立 · P2 若干。**线上决策路径(WPO→EV→闸门)数值验证干净,无一处在决策时刻捏造主 EV**——毒集中在:记录/追踪层、八月引信的注册表层、和"坏了没人知道"的监控层。

---

## P0(现在就存在的盲区,近期必踩)

**P0-1 `data_freshness` 对 7/1 后新增的所有捕获流全盲** — `CAPTURE_TABLES` 只有 5 表单库:closing 锚(source=closing 被同表其他 writer 的 max() 顶绿)、polymarket_gaps(整表不在)、score_ev_forward.db(别库)、jc_open_*/jingcai_exotic(子流)全部无哨兵。proxy 挂(常态)→ polymarket 三窗静默 0 行无限期无人知;forward-only 数据按天永久丢。

**P0-2 全系统唯一推送报警(osascript)寄生在 daily_settle 链尾** — daily_settle 自己死 = 报警系统整体死,退回"几周后偶然发现"模式(wc_settle 死三周的前科机制原样保留)。无外部心跳。

## P1 簇 A — ou_line 全链丢失(算错数,不止显示;今天已在发生)

6e3611f 只修了 4+ 处中的 1 处。仍缺:
- `routes.py:558/1534/1671` 三个内部跳点(dataframe 列缺/`_fixture_rows_to_inputs` 不传【已复验 → None】/`_calc_predictions` 不回显)→ 标准模式让球反推全按 2.5 锚;
- `SingleTicketResponse` 无 ou_line 字段 → 前端 `dashboard.html:3818` 记录时硬编 2.5 → **📌 记此注入库的 P/EV/注额本身是错的**(今天 WC 15/22 场真线 ≠2.5,现行伤害);
- 前端 `_cupHcRecord`(5256)不带 ou_line、残留 `|| 2.5` 回落(5044/5301/6221)。

## P1 簇 B — 「注册表即开关」八月引信群(韩职 bug 的批量同胞)

- **zh↔EN 队名字典对 6 个秋季联赛从未验证**,离线 diff 实测:德乙 14/19 队打不中、比甲 10/20、法乙 8/19、荷甲 6/18(含 PSV)、意乙 4/20、西乙 4/22 + 已验证联赛升降级漂移(汉堡/科隆…)。第二种坏法(中文在、EN≠AF 名 → 行照写但永远 join 不上收盘)**对整联赛报警隐形**;
- **SPORT_KEYS 缺 daily cron 13 联赛中的 8 个**(英冠/西乙/意乙/德乙/法乙/荷甲/葡超/比甲)→ 鲜线叠加对它们从未运行;
- **closing_odds plist 硬编 `--sports WC`** → WC 结束(~7/19)后收盘链整体停摆,秋季 CLV 门(唯一放钱开关)无锚;
- **vote 采集固定单页 50 无翻页** → 秋季大周六第 51 场起散户数据永久丢;
- 空队表永久缓存(TUR/AUS 2026 已缓存成 `[]`)→ 秋季别名验证 diff 会拿到假绿灯。

## P1 独立项(按伤害排序)

| # | 位置 | 缺陷 | 时效 |
|---|---|---|---|
| 1 | `closing_odds.py:90` | **今日 c5e805f 回归**:club-core 毒化 None 进消费循环(try 外)→ 一撞崩整轮收盘捕获【已复验】 | 潜伏,一触即发 |
| 2 | `observation_routes.py:563` | `POST /observation/outcomes` 零守卫写端点 + 错误结算不可逆(无重结算工具) | 休眠攻击面 |
| 3 | `admin.py:117` | 新鲜度检查非只读连接 → DB 路径配错时创建 0 字节假库,把"库丢失"伪装成"正常但空" | 条件触发 |
| 4 | `handicap_triples.py` | **双 P1**:让球软水账本用 basic 去vig(让负 +3.9pp 幻影 EV)+ 全系统唯一漏 kickoff 守卫的收盘读者 | 秋季测量地基 |
| 5 | `auto_calibration.py:216` | Layer A 校准对被非模型概率污染(40 对里 9 条:手工全零 P/市场去vig P) | 秋季 holdout 一到即毒 T |
| 6 | `ev_tier_calibration.py:89` | CLI 索引已退役 tier 一跑必崩 KeyError + 用 basic 去vig 测非 serving 口径 | 测量线已死 |
| 7 | `compound_pool.py:180` | 相关票各自独立 Kelly 相加(合成例:总敞口 30.9% bankroll,6× 超单票帽) | §2 解锁前必修 |
| 8 | `ingest_odds.py:274` | 市场模式 🔄 的 OA 强刷 ×7 天循环重复拉同一份日期无关 feed(~140 点/次,6/7 浪费) | 现行浪费 |
| 9 | `routes.py:1647` | 标准模式整批 try → 单场毒化清空整板("今天没比赛"假象) | 秋季触发 |
| 10 | dashboard 786/6066 | 今日推荐「刷新」不带 refresh_odds(handler 当 click 用)+「刚刚更新」= 页面时刻非盘口时刻 + 两板无盘口年龄显示 | 现行误导 |
| 11 | dashboard 4756 | 记录时把手填竞彩 SP 捏造成 Pinnacle(`pr.psc_home \|\| oh`)→ 零售线当 sharp 锚入库毒 CLV | 现行伤害 |
| 12 | worktree 未合并 | 后台日期审计修的 2 处(ingest_odds/rec 本地日期)还在 worktree;score_ev_forward.py:67 + wc_predict plist 是第 3/4 处 | 合盖补跑触发 |
| 13 | 配额零报警 | AF 日用量/OA 信用点只有拉取式面板,耗尽 = 叠加静默回落陈旧线(EV 卡悄悄变错) | 条件触发 |
| 14 | teardown:13 / health_check §2 | 卫星脚本只知 11/21、7/21 个任务(唯一真 source 漂移) | 操作时触发 |

## P2 精选(全清单见各 agent 报告)

🎯 刷新竞彩 docstring 与代码矛盾(protect_manual=False 覆盖手填)· record-bet 无幂等(失败重试=双记账)· `nutmeg-api` 入口绑 0.0.0.0 · prediction_log AET 比分回退 · vote UPSERT 清 SP · psc 无条件覆盖 · protect_manual 挡初盘 · observation_routes 全文件 0 日志 + 整板 fail-soft 无痕 · clv_ledger 分档表缺新档行(边缘 15-25% 蒸发)· sharp_consensus 第三个 devig 实现(冷门 EV 符号翻转级)· dc_home_cover_prob 整数线 push 未拒 · 整联赛丢失报警只进没人读的 out.log · daily_settle 链 `2>/dev/null` 吞哨兵 traceback · eloratings parquet 无年龄哨兵 · AF/OA 缓存写非原子+损坏不自愈 · 两板手填保留规则相反 · cron 健康按计数不按 label 集合。

## 干净带过(逐项核过,别重查)

devig WPO 公式/守卫/单源 ✓ · asian_total push 三族对暴力枚举全等 ✓ · clv_gate 统计 vs scipy 一致 + 零方差不伪造 CONFIRM ✓ · B2 公式与文档一致 ✓ · 结算让球符号/90 分钟 ✓ · odds_snapshots sink 守卫 ✓ · 日期锚 routes/observation_routes 全 UTC ✓ · SW network-first ✓ · i18n 字典 zh/en 413 键同步 ✓ · live plist 21/21 与脚本一致 ✓ · 备份/轮转活着 ✓ · daemon 跑的是最新代码 ✓。

## 修复波次(建议)

- **Wave 0(立即,微小)**:①closing_odds 循环加 `if e is None: continue`(拆我今天的雷);②合并 worktree 的 2 处 CLI 日期修复。
- **Wave 1(本周,钱相关)**:簇 A ou_line 全链(3 跳点+ticket schema+前端 3 处)· P0-1/P0-2 哨兵扩表+外部心跳 · 独立 #2/#3/#11(写保护三件)· #8 OA 强刷提出天循环。
- **Wave 2(八月前,引信群)**:簇 B 全部(字典 6 联赛对 AF 队表批量补齐 + SPORT_KEYS 8 键 + closing plist 改在季联赛 + vote 翻页 + 空队表 TTL)+ #4/#5/#6 测量工具三件 + #9 整板脆性 + 「注册表覆盖率 diff」纳入 health_check 常规项。
- **Wave 3(加固)**:P2 清单按次序消化。

**元结论**:本周五连击 + 本次 24 条 P1 里,**超过一半是同一病根的变体——「注册表/词典/字段清单即开关」,缺一项 = 该切片静默降级,且现有报警只覆盖"全无"不覆盖"半坏"**。Wave 2 的"注册表覆盖率 diff"体检项是对整个类的结构性疫苗。
