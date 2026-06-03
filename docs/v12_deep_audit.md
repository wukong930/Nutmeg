# Nutmeg V4 只读审计报告

**审计范围**:`apps/api/src/nutmeg/v4/`(下注辅助核心)+ `tests/v4/` + 观测库 `data/v4_observation.db` + 本地部署脚本/launchd。
**方法**:6 lane 深度排查 + 对抗验证(每条发现至少 1 名独立验证员尝试证伪)。审计员只读,未改动任何文件、未提交、未重启 daemon。
**日期**:2026-06-03。

---

## 1. 执行摘要

**一句话定位**:上周拔掉的"EV-vs-Pinnacle"根因**没拔干净**——同一个把"模型 vs sharp 噪声"当 +EV 卖的 bug 仍活在复式(pool)路径和 predict_report 里;与此同时,结算记账有一个会把每一笔赢钱缩水甚至记成亏损的算账 bug,而整条 Layer A 自校准回路因为部署目录写错,在生产上是个静默空操作。

**最严重的 3 件事(全是 🔴 资金/概率正确性)**:

1. **结算少算每一笔赢钱**(Lane C):`record_single/parlay_session` 把 `stake_units` 错算成 `int(stake // 2.0)`(金额/2)而不是组合数 1。亏注照算对,**只有赢注被按 ≈stake/2 倍率缩水**——一笔 ¥10 @2.0 中奖会被记成 ¥4 回报、净亏 ¥6。一旦任何 >¥2 的单关/串关经 API 结算,ROI 报表会系统性低估战绩,直接误导用户得出"+5% 边际不存在、别下了"的错误结论。

2. **EV-vs-Pinnacle 根因仍活在复式路径**(Lane B/D):`_pick_to_selection`(routes.py:1129)和 CLI `recommend_pool.py` 在缺竞彩 SP 时拿 `psc_*`(原始带 vig 的 Pinnacle 收盘价)当下注赔率。`/recommend/pool` 会对一场竞彩还没开盘的比赛算出虚构 +EV 并真金 Kelly 下注。这正是 commit 53a7dc8 自称"eradicate"的 bug,但那次只改了单关/串关的 `_fixture_to_match_input`,复式这条平行路径被漏掉,且**回归测试只覆盖单关/串关,完全不测 pool**。

3. **Layer A 自校准在生产上是装饰品**(Lane F):serving 读 `NUTMEG_V4_ARTIFACT_PATH=data/v4_model_cat`,但所有 8 处 `--deploy-artifact` 和文档手动部署都写 `data/v4_model`(不同目录、不同模型、非 symlink)。fit T → 过闸 → 写 JSON → 记审计全跑通、报告"无需重启",但 serving 永远读不到这个文件,correction 恒为 identity T=1.0;auto-rollback 也指向错目录,安全网同样落空。

---

## 2. 确认发现

按严重性排序。所有发现均经对抗验证 confirmed(唯一例外见 C-2,标注了验证分歧)。

### 🔴 bug(资金/概率正确性,逻辑跑通但数字错)

---

**B1. 单式结算少算每一笔赢钱:`stake_units = int(stake//2.0)` 应为组合数 1**
`apps/api/src/nutmeg/v4/observation/recorder.py:189`(record_single_session)、`:294`(record_parlay_session);经 `settlement.py:118,135` 错误放大。

- **证据**:`stake_units = int(stake // 2.0) if stake > 0 else 0`。单式 = 恰好 1 个原子组合,`stake_units` 必须为 1。结算 `unit_money = kelly_stake / stake_units`,但 1 腿票只枚举 `n_combos_total=1`。复现:¥10 @2.0 中奖记 `stake_units=5`、kelly=10 → `unit_money=2.0` → payout=`1×2.0×2.0=¥4`、profit=**−6.0(被结算成亏损)**,真实应为 payout ¥20、profit +¥10。
- **不对称且阴险**:亏注永远算对(`total_stake = unit_money×stake_units = kelly_stake`),**只有赢注被缩水** ≈stake/2 倍(¥1000 中奖只赔 ¥7 而非 ¥3500)。ROI 报表单边压低赢面。
- **为何重要**:这是产品唯一的真实反馈信号。它会让用户误判 +5% EV 边际不存在而停止下注——和 EV-vs-Pinnacle 同一危害等级:逻辑跑通、结算完成、报表渲染,但数字静默错误。recorder 自己的 docstring(18-50 行)恰好把正确值(单式 `stake_units=1`)和这个错误行(`stake_units=500 ← 当成倍数`)都写明了,代码却正好掉进自己警告的坑。兄弟函数 `record_wc_handicap_session:419`、`record_market_handicap_session:528` 已硬编码 `stake_units=1`,证明这两处是回归而非设计。
- **现状**:暂未在生产爆雷——库里 5 笔已结算全是 ¥2 单注(`int(2//2)=1` 撞对)+ 1 笔 ¥1000 二串经 legacy `record_session` 路径(信任引擎给的 `stake_units=1`)。**任何 >¥2 的单关/串关经 API 结算的瞬间触发。**
- **修**:单式 recorder 硬编码 `stake_units=1`(倍数留在 kelly_stake)。注意:`test_parlay_endpoint.py:164` 和 `test_recorder_single_pool.py:103` 当前**断言了错误值**(把作者的误解钉死了),修的同时要改这两个测试。
- **复现**:
  ```
  PYTHONPATH=apps/api/src .venv/bin/python -c "import json; from nutmeg.v4.observation.settlement import _settle_one; print(_settle_one({'stake_units':5,'kelly_stake':10.0,'legs_json':json.dumps([{'match_id':'EPL_A_vs_B','market_type':'1x2','selections':[{'outcome':'H','odds':2.0,'probability':0.5,'edge':0.1}]}])},{'EPL_A_vs_B':{'home_goals':1,'away_goals':0}}))"
  # → actual_payout=4.0 profit_loss=-6.0  (应为 20.0 / +10.0)
  ```

---

**B2. 复式 pool 路径 EV-vs-Pinnacle bug 仍 LIVE:`_pick_to_selection` / CLI `_row_to_selection` 拿 psc_* 当下注赔率**
`apps/api/src/nutmeg/v4/api/routes.py:1124-1129` + `apps/api/src/nutmeg/v4/cli/recommend_pool.py:97-98`(测试缺口:`tests/v4/test_recommend_single_pool_api.py:186-242`)。

- **证据**(已亲自读码核实):缺 `odds_1x2_*` 时 `odds = row[psc_col]`,而正下方的让球分支(1151-1155)在缺赔率时正确 `raise` ——**同一函数里让球拒绝 Pinnacle 兜底、1X2 却静默兜底**,是疏漏不是设计。psc_* 是原始带 vig 的 Pinnacle 收盘价(schemas.py:28),既非竞彩线也未去 vig。`edge = P×odds−1` → 模型 P × Pinnacle 赔率 − 1 = 模型 vs sharp 分歧(噪声)。
- **端到端复现(验证员实跑,只读)**:三场 psc-only fixture(无任何竞彩赔率)经 `/recommend/pool` → HTTP 200、3 张已下注票、`total_stake ¥12`、每腿 `bet_odds == psc_*`、组合 EV +0.458 越过 +5%/5%-hit 闸门并 Kelly 下注。同请求补上真实竞彩 away SP 后 EV 转 −0.548、¥0 下注,**证明 +EV 完全来自 Pinnacle 替换**。
- **git 归因**:`git show 53a7dc8`("eradicate EV-vs-Pinnacle root")只改了 `_fixture_to_match_input`;`git blame` 确认 1124-1129 自 3cb2575(2026-05-24)起从未被那次 fix 触碰。commit message 自称关闭"高级 单关/复式 tabs",实际只关了单关。
- **为何重要**:团队以为已根除的 bug 仍在 `/recommend/pool` 真金下注,违反产品核心 DNA(绝不下注 Pinnacle 分歧)。
- **现状/边界(诚实)**:自动今日看板(`_build_today_pool`)**安全**——它先跑已修复的 `recommend_single`,psc-only fixture 会被先过滤掉。**仅直连 `/recommend/pool`(高级复式 tab 的自由 JSON)可触达**。且因模型把 psc 当强特征,model P 通常被锚向 sharp,大多数 psc-only 票 EV≈−0.3 被闸门挡掉;只有模型残差性地与极端 Pinnacle 线分歧时才下注——但这恰恰就是 fix 要消灭的噪声。
- **修**:`_pick_to_selection` 和 CLI 的 1X2 分支应像让球分支一样 `raise`;`gt=1.0` 的 schema 改不到根,逻辑必须改。

---

**B3. predict_report 把 70%-Pinnacle 混合后的 P 当"模型"去和 Pinnacle 比,称作"模型 vs sharp"**
`apps/api/src/nutmeg/v4/api/routes.py:1421-1429`(写)→ `apps/api/src/nutmeg/v4/cli/predict_report.py:47-52,118-135`(评分)。

- **证据**:`_calc_predictions`(predict_log.py:86 就用它填 `league_predictions`)对 playoff/barrage fixture 把 served 1X2 向 Pinnacle 混合:`a=0.3`,`ph = 0.3*model + 0.7*pinnacle`。该混合 P 原样存进 `league_predictions.p_*`(prediction_log.py:117-119),且 `market_mode` 默认 False(schemas.py:129),与纯模型行无法区分。predict_report 直接 `_model_p(r)=[r['p_home'],...]` 算 Δlog-loss 和分歧记分牌。
- **两种失真**:(1) playoff 行 P 是 70% Pinnacle → 模型 log-loss 被拉向 Pinnacle → Δ 美化模型;(2) 混合后的 pick 塌缩到 Pinnacle 的 pick → 这些行几乎从不进"分歧场",**模型在它最弱的 OOD 比赛上从未被真正拿去和 sharp 对账**。数值复现:model=[.30,.30,.40](选 AWAY)、pin=[.55,.27,.18](选 HOME)→ 存储 P=[.475,.279,.246](选 HOME);HOME 赢时 stored logloss=0.744 vs 真模型 1.204 vs Pinnacle 0.598。
- **为何重要**:这份报告的头条("Δlog-loss 模型−Pinnacle"+"分歧场……模型的背离是噪声,别下注它")是唯一诚实检验模型能否胜过 sharp 的工具,而它恰好被污染。更糟:同样被污染的 `market_mode=0` 列还喂进 `auto_calibration.load_calibration_pairs`(其 `WHERE market_mode=0` 过滤拦不住 playoff 混合行),**泄漏进会调整 served 概率、进而影响真实竞彩 EV 的校准拟合**——这是直接资金路径。
- **现状(诚实)**:今日 2026-06-03 detect_playoff 对 **ESP_SEGUNDA、ITA_SERIE_B、NED_EREDIVISIE、PRT_PRIMEIRA** 4 个联赛触发(原 finding 列的 FRA/GER/BEL 窗口已在 06-02 结束,**已纠正为 4 个而非 8 个**)。库里现有 2 行预测日志均为 2026-05-31 ESP_SEGUNDA、在窗口(06-01 起)之前、经核实为纯模型未混合 → 污染目前是**潜伏未实现**,但活跃窗口的下一次 predict-log 就会开始写入污染行。
- **修**:report 评分前对 playoff/barrage 行排除或单独标注;`_calc_predictions` 给混合行打 `market_mode=True`(或单独标志)以便下游识别。

### 🟠 risk(记账/覆盖/误操作正确性,不直接错算资金)

---

**R1. 市场模式 best_stake 对 EV≤0 的"最优"腿仍记 ¥2,写入负 expected_return**
`apps/api/src/nutmeg/v4/api/routes.py:1705-1720`。

- **证据**:`best_stake = max(float(k.recommended_stake), 2.0)`——Kelly 对 EV≤0 返回 0,这里强行抬到 ¥2;`pick_expected_return = best_stake * float(ev[best])`,`ev[best]` 可能为负。一场让球三个 outcome 全 −EV(竞彩 31.5% 抽水下是**默认而非边角**)时,`best=max(...)` 选出最不亏的负 EV 腿,以 ¥2 写入负 expected_return 到观测库(`model_type=market_handicap`),且这段**不走** `passes_recommendation_thresholds`。
- **为何重要**:污染 ROI/settle/校准回测样本——`settle_unsettled` 只跳过 `stake_units<=0`,会结算这条 −EV ¥2 行;`roi.py:40-166` 全部是无过滤的 settlements JOIN,这条负行进入头条 ROI、分联赛 ROI、校准桶、周 P/L。验证员实测:写入 `expected_return=-0.198`、被结算为 profit −2.0。注释辩称"用户实际会下就要追踪",但记录被标成系统"最优/推荐"腿,与真正 +EV 推荐在无过滤的 ROI 群体里无法区分。
- **修**:对全 −EV 的比赛不记录"推荐"腿,或单独打标排除出推荐质量统计;若要追踪用户实下,与系统推荐分表。

---

**R2. Gold-standard 池化指标(0.9960/0.9904/0.9971)未对真实 artifact 钉死——无任何 drift guard**
`tests/v4/test_live_vs_backtest.py:334-346`、`test_experiment_tracker.py:28,116-151`、`test_walk_forward_cat_calibration.py:180-181`、`docs/v4_baseline_card.md:22`。

- **证据**:每一处 0.9960/0.9971 字面量都是**喂进抽取器的 INPUT dict**,断言只检验"读 dict 又吐回 dict"。无任何测试加载 `data/v4_model`、对留出帧跑 predict、断言池化 log-loss ≈ 基线卡值。唯一跑真实模型的 `test_walk_forward_cat_calibration` 其 docstring 明说只验"形状+存在,不验数值"。`bench.py` 是**生成/覆盖**基线卡(无 assert/threshold),git status 显示该卡已被改动 → 退化会被直接重写进卡里。
- **为何重要**:产品前提是"与 Pinnacle 同等概率质量"。若重训/特征管线变更/校准 T 漂移让池化 log-loss 从 0.9971 悄悄退化到 1.05,**测试套件无一失败、CI 全绿**,但真实概率漂移、每个下游 EV 都错。
- **修**:加一个端到端 drift guard:加载生产 artifact → 对固定留出集算池化 log-loss → 断言在基线卡值容差内。

---

**R3. predict_report 从不排除 market_mode 行,与自己的 schema 契约矛盾**
`apps/api/src/nutmeg/v4/observation/prediction_log.py:49-51` vs `apps/api/src/nutmeg/v4/cli/predict_report.py:96-136`。

- **证据**:schema 注释明写"market_mode 行是 Pinnacle de-vig,不是独立模型输出——report 把它们排除出 模型-vs-sharp 比较"。但 `grep market_mode predict_report.py` **零命中**。`auto_calibration.py:263` 有 `WHERE market_mode=0` 守卫,证明这是既定模式,predict_report 没跟。
- **为何重要 / 为何是 risk 而非 bug**:当前 cron 路径只写 `market_mode=0` 行(库里实测 `SELECT market_mode,COUNT(*)` → 仅 `0|2`),所以暂不爆;但一旦任何 `market_mode=1` 行进表(未来 writer / 手动 ingest / 把杯赛市场路径接进 predict_log),report 会把 Pinnacle de-vig 当"模型"和 Pinnacle 比 → 保证 Δ≈0 的"模型≈sharp"纯属同义反复。大家以为存在的保护并不存在。(注:B3 的 playoff 混合行是 `market_mode=0`,即便补上这个守卫也拦不住,两者需分别修。)
- **修**:predict_report 的取数加 `WHERE market_mode=0`,并与 B3 的 playoff 标注配合。

---

**R4. Layer B deploy 不复检 ship-gate:`do_deploy` 无条件 `decision=True` 直接 swap 生产 pointer**
`apps/api/src/nutmeg/v4/cli/auto_retrain.py:239-301`。

- **证据**:`evaluate_ship_gate` 只在 `do_propose`(:181)调用。`do_deploy()` 从 CLI `--log-loss-before/after/--p-value/--n-train` 读运营者手填数字,算完直接 `write_artifact_pointer(...)` + `record_retrain_journal(..., decision=True, reason="deployed via CLI")`,**全程不重新评估 candidate**。验证员实跑:candidate 明显更差(before=0.1/after=9.9/p=0.99)仍写出 pointer 且 journal `decision=1`,pointer 甚至忠实记录 `ship_gate_log_loss_delta=-9.8` 却照 ship。
- **为何重要 / 为何是 risk**:ship-gate 在 Layer B 与真正换模型解耦,纯属 propose 阶段建议;手贴错/贴旧/数字与 candidate 不符都会静默换上生产模型、污染下注概率。**Layer B 当前休眠无 cron**,故仅人为误操作风险而非自动触发。对照:兄弟 Layer A 在 deploy 时会因 `not should_apply` 拒写(auto_calibration.py:416-421),Layer B 把这个守卫丢了。design 自己的风险表(v11_layer_b_design.md:536)把 ship gate 列为"blocks"——本应是主动拦截器。
- **修**:`do_deploy` 应对 candidate **重新跑 evaluate_ship_gate**,不过则拒绝,而非信任 CLI 入参。

---

**R5. auto_calibration 测试全绿是假阳性:同一 tmp_path 既当 deploy 目标又当读取源**
`tests/v4/test_auto_calibration_serving.py:30-77,223-263`。

- **证据**:24 项全过,但每个用例 `write_artifact_correction(tmp_path)` 后直接 `load_artifact_correction(tmp_path)`(同目录);CLI 用例 `--deploy-artifact` 也指向同一自建 tmp。**没有任何用例设 `NUTMEG_V4_ARTIFACT_PATH` 到 A 目录、却 deploy 到 B 目录、再断言 serving 读不到**——结构上无法暴露 F1。
- **为何重要**:绿测给了"Layer A serving 集成已验证"的错误信心,而真正的生产 wiring(env=`data/v4_model_cat` vs cron=`data/v4_model`)恰是覆盖盲区。这就是 F1 能长期潜伏的原因。(纠正:原 finding 称 `grep NUTMEG_V4_ARTIFACT_PATH` 为空,实际 l.334 有设置;但它指向同目录,盲区依然成立。)
- **修**:加一个 env≠deploy-dir 的端到端用例,断言 serving 读不到写到别处的 correction。

### 🟡 debt(误导性文档/技术债/脆测试,不算错但侵蚀正确性)

---

**D1. Layer A 部署落到 serving 永不读的目录 → 整条自校准回路 silent no-op**
`scripts/setup_local_pipeline.sh:373` + `routes.py:118,173` + `docs/local_deployment_guide.md:211`。

> **注**:此条 finding 原标 bug,验证确认机制为真;但三名验证员一致指出其**资金影响当前为潜伏(latent)**——库里 journal 仅 1 行 propose、闸门从未通过("0 pairs < 30 min")、磁盘上无 `live_T_correction.json`,故无任何今日下注偏离基线。考虑到"闸门通过即必然空操作"的确定性 + 已亲自核实目录错配,我在报表中列为**最高优先级的 P0**,但严重性按"尚未实现的资金损失"归 debt/risk 边界。机制确凿无疑。

- **证据**(已亲自读码核实):serving `_artifact_path()` 读 `NUTMEG_V4_ARTIFACT_PATH=data/v4_model_cat`(.env:5),`_load_correction()` 从该目录读 `live_T_correction.json`。但全部 8 处 `--deploy-artifact` + 文档手动部署都写 `data/v4_model`(脚本 :373 硬编码,文档 :211/:228,自我验证还 `cat data/v4_model/live_T_correction.json`)。两目录不同模型(`data/v4_model` 无 model_type=旧 LightGBM;`data/v4_model_cat`=CatBoost)、非 symlink、realpath 不等。`write_artifact_correction` 只要 `art_dir.is_dir()` 就成功,所以写文件成功、记 deploy、报告"无需重启",但 serving 从 `data/v4_model_cat` 读到 None → `apply_correction_to_probs` 恒 identity T=1.0;auto-rollback 也读 `data/v4_model`,安全网同样脱节。
- **机制纠正(诚实)**:周 cron 的 argv 缺 `--action`,默认 `propose`,所以 cron 本身其实不写文件(`--deploy-artifact` 被忽略);真正的静默空操作 deploy 是**文档让运营者手跑的 `--action=deploy` 那一步**。结论不变:T 永不进下注概率。
- **修**:把所有 `--deploy-artifact` 改为 `data/v4_model_cat`(或让部署读同一个 `NUTMEG_V4_ARTIFACT_PATH`);R5 的端到端测试会防回归。

---

**D2. PoolFixturePick odds Optional + "缺省回退 Pinnacle"注释 + 无 psc-only pool 测试 = B2 的复发温床**
`apps/api/src/nutmeg/v4/api/schemas.py:32-35`。

- **证据**:`# Lottery odds (what the player actually bets at). Default to Pinnacle if absent.` 配 `odds_1x2_H/D/A: Optional[float]=Field(None,gt=1.0)`,`PoolFixturePick` 继承之。回归类 `TestNoPinnacleFallbackForRecommendation` 有 single/parlay 的 psc-only 用例但**无 pool 对应**;`_good_pool_fixture` 永远带 `odds_1x2_H=2.50`,使存活的 `_pick_to_selection` 兜底对 CI 不可见。
- **为何重要**:陈旧注释编码了制造原 bug 的心智模型,正是它"授权"了 B2;加上缺 pool 回归测试,修了 B2 也会再退化。
- **修**:删/改注释为"缺竞彩 1X2 SP 则不可下注";加 `test_pool_psc_only_yields_no_recommendation`。

---

**D3. 陈旧 schema 注释把已杀死的 EV-vs-Pinnacle 行为写成既定契约**
`apps/api/src/nutmeg/v4/api/schemas.py:32`。

- **证据**:同上行注释"Default to Pinnacle if absent",与 `_fixture_to_match_input` docstring(routes.py:506-552)"We deliberately do NOT substitute Pinnacle"**直接矛盾**。git blame 显示注释自 V4 基线(ebe6460)起从未随 de-fallback 更新。
- **为何重要**:维护者读 schema 会以为 Pinnacle 兜底是设计契约,从而在别处重新引入、或把已修好的单关代码"改回" bug。几乎可以肯定就是它催生了 pool 路径的兜底。
- **修**:与 D2 合并处理。

---

**D4. 脆性测试钉死多行 JS 源码片段(含换行+12 空格缩进)而非行为**
`tests/v4/test_spcalc_dashboard.py:474-475`。

- **证据**:`assert "...toFixed(0)}%</div>\n            <div class=\"text-xs text-muted mt-0.5\">${predConfLabel}" in html`——逐字符匹配含换行和恰好 12 空格缩进的 HTML/JS 子串。`TestTodayPredictionBoard` 全类都是 HTML 子串存在性断言,从不带数据执行渲染、不验 argmax。
- **为何重要 / 为何只是 debt**:这是"今日单关看板显示模型预测(argmax)而非 EV-vs-Pinnacle"修复的回归测试,任何 prettier/缩进/换行重排都会在行为不变下破测,诱导维护者"直接改字符串"而丢掉守卫。**但真正的资金不变量**(单关=argmax、ev==0、stake==0)由 `_argmax_prediction_tickets`(routes.py:1748-1789)实现,并由 `test_today_recommendations.py::TestTodayPredictionBoardW8k` 行为化守卫(已实跑 2 passed)——所以破这条只丢表现层冒烟,不动资金不变量。
- **修**:改为断言渲染后的 DOM 行为或服务端 argmax 字段。

---

**D5. weekly_gate / predict_report 文件名用 `%Y-W%V` → ISO 周边界年份前缀错误**
`~/Library/LaunchAgents/com.nutmeg.weekly_gate.plist:13`(+ `scripts/setup_local_pipeline.sh:360`)。

- **证据**:`%V` 是 ISO 周号但 `%Y` 是日历年。`date -j -f %Y-%m-%d 2027-01-01 +%Y-W%V` → `2027-W53`,而 2027-01-01 实为 ISO 2026 第 53 周,应配 `%G-W%V` 得 `2026-W53`。gate 周日跑(Weekday=0),Sun 2027-01-03 → 标 `2027-W53` 实为 ISO 2026-W53。
- **纠正(诚实)**:原 finding 列的 `predict_report.py:21` 其实用 `$(date +%F)` 无此 bug;但**漏报了同样的孪生 bug** `setup_local_pipeline.sh:377`(auto_calibration 文件名,已落盘 `docs/weekly/auto_calibration_2026-W23.md`)。
- **为何重要 / 为何 debt**:纯文件名/报表 artifact,不影响下注/概率/DB;但每年新年附近周度证据记录被错放年份、可能被次年同名 run 覆盖。
- **修**:`%Y` → `%G`(plist:13 + setup_local_pipeline.sh:360,377)。

### Lane A 让球先验技术债(已文档化,非隐藏 bug,留档)

**national_team_handicap.lambdas_from_1x2 固定 λ_total=2.6 → 让球 P 可偏 ~5pp**
`apps/api/src/nutmeg/v4/model/national_team_handicap.py:100-121`。验证确认机制为真但**正确分类为 debt**:(a) 模块 docstring 明确这是 128 场 WC 无可靠 O/U 的有意取舍;(b) α=0.4 Bayesian blend 把到达 EV/Kelly 的偏差从 5pp 削到 ~2.08pp,且方向保守(抑制边际好注而非放行坏注);(c) 新的 `market_handicap.fit_lambdas`(模型盘+J1/杯赛走的那条)用 2D L-BFGS-B 把 λ_total 锚到真实 O/U,精确复原 (2.4,1.0)、已无此问题;(d) 该 endpoint 已标 `[DEPRECATED V12 W8 → 市场模式]`(routes.py:2688),dashboard 不再调用。**留作已知技术债,无需立即动。**

---

## 3. 风险表(严重性 × 现状)

| # | 发现 | 严重性 | 是否已爆 | 触发条件 | 资金路径 |
|---|------|--------|----------|----------|----------|
| B1 | 单式结算少算赢钱(stake//2) | 🔴 bug | 潜伏(5 笔全 ¥2 撞对) | 任何 >¥2 单关/串关经 API 结算 | **直接**:ROI/P&L 单边压低 |
| B2 | 复式 pool EV-vs-Pinnacle 兜底 | 🔴 bug | 可触发(已端到端复现下注) | 直连 `/recommend/pool` 提交 psc-only 票 | **直接**:真金 Kelly 下注虚构 +EV |
| B3 | predict_report playoff 混合 P 当模型 | 🔴 bug | 潜伏(活跃窗口下次 predict-log 即写污染) | 4 联赛活跃窗口 + playoff fixture | **间接**:泄漏进校准→served 概率 |
| D1 | Layer A 部署目录错配 silent no-op | 🟡(机制确凿) | 潜伏(闸门尚未通过) | 闸门通过 / 运营者手动 deploy | 间接:T 永不进概率(目前 T=1.0 无害) |
| R1 | 市场模式负 EV 记 ¥2 | 🟠 risk | 已发生(实测写入负行) | 三 outcome 全 −EV(常态) | 记账:污染 ROI/校准样本 |
| R2 | 池化指标无 drift guard | 🟠 risk | 持续敞口 | 重训/特征/校准漂移 | 间接:概率退化 CI 不报 |
| R3 | predict_report 不排除 market_mode | 🟠 risk | 潜伏(库里仅 market_mode=0) | 任何 market_mode=1 行进表 | 报表:同义反复 Δ≈0 |
| R4 | Layer B deploy 不复检 ship-gate | 🟠 risk | 潜伏(Layer B 休眠) | 运营者手动 deploy 错数字 | 间接:换上未过闸模型 |
| R5 | auto_calibration 测试假阳性 | 🟠 risk | 持续(掩盖 D1) | — | 覆盖盲区(掩盖 D1) |
| D2/D3 | schema 兜底注释 + 缺 pool 测试 | 🟡 debt | 持续 | — | B2 的复发温床 |
| D4 | 脆性 JS 源码片段测试 | 🟡 debt | 持续 | 任何 JS 重排 | 无(资金不变量另有守卫) |
| D5 | `%Y-W%V` 年份前缀 | 🟡 debt | 每年新年 1 次 | 跨 ISO 周/年边界 | 无(纯文件名) |

---

## 4. 优先级行动清单

### P0 — 资金/概率安全,立刻修

1. **B1 单式结算 stake_units**:`record_single_session` / `record_parlay_session` 改 `stake_units=1`;同步改 `test_parlay_endpoint.py:164`、`test_recorder_single_pool.py:103` 这两个**钉死了错误值**的测试。这是当前最确定会算错钱的 bug,且任何 >¥2 真实下注一结算就爆。
2. **B2 复式 Pinnacle 兜底**:`_pick_to_selection`(routes.py:1129)+ CLI `recommend_pool.py:97-98` 的 1X2 分支改为像让球分支一样 `raise`;**同时**加 `test_pool_psc_only_yields_no_recommendation`(否则 D2 会让它再退化)。
3. **B3 predict_report playoff 污染**:report 评分前排除/标注 playoff 混合行;并修 `auto_calibration` 泄漏(给混合行打 `market_mode`/独立标志),因为它有**直接的 served-概率资金路径**。
4. **D1 Layer A 部署目录**:把所有 `--deploy-artifact data/v4_model` 改为 `data/v4_model_cat`,并加 R5 的端到端测试防回归。机制确凿,虽当前潜伏,但闸门通过即必然空操作——属"部署正确性",归 P0。

### P1 — 记账/覆盖正确性

5. **R1 市场模式负 EV 记 ¥2**:全 −EV 比赛不记"推荐"腿,或与系统推荐分表,清出 ROI/校准群体。
6. **R3 predict_report 加 `WHERE market_mode=0`**(与 B3 配合)。
7. **R4 Layer B deploy 复检 ship-gate**:`do_deploy` 对 candidate 重跑 `evaluate_ship_gate`,不过则拒。
8. **R2 池化指标 drift guard**:加端到端测试,对真实 artifact + 固定留出集断言 log-loss ≈ 基线卡。
9. **R5 auto_calibration env≠deploy-dir 端到端用例**(同时落实 D1 防回归)。

### P2 — 文档债/脆测试

10. **D2+D3** schema 注释改写为"缺竞彩 SP 不可下注",与 D2 的 pool 回归测试一起。
11. **D5** `%Y-W%V` → `%G-W%V`(plist:13 + setup_local_pipeline.sh:360,**377**)。
12. **D4** 脆性 JS 片段测试改为 DOM 行为/服务端 argmax 字段断言。
13. **Lane A 让球先验**:留作已知技术债,endpoint 已 deprecated,无需立即动。

---

## 5. 诚实战略评估

**到哪了**:核心建模引擎是成熟的。模型对 Pinnacle 1X2 收盘**零独立信号**(β 测试:最优 β≤0,加权只会更差),校准已成熟(ECE 0.0120 < Pinnacle 0.0123),文章 #6 的四个候选特征(战意/球员 xG/裁判/赔率路径)全测完搁置。这意味着**建模这条线已经收敛**——不是"还能再榨边际",而是"已经证明在 1X2 收盘上榨不出超越 sharp 的边际"。这是一个诚实且有价值的负结论。

**什么已证 / 未证**:
- ✅ **已证**:概率质量与 Pinnacle 同级(校准 + log-loss);模型对 sharp 无独立 alpha;市场模式(去 vig 反推网格)在让球上数学正确(`fit_lambdas` 精确复原 λ)。
- ❌ **未证(全项目最大悬念)**:**真实下注 ROI 完全没验证**。观测库只有 ~5 笔已结算下注 + 2 行预测日志。这才是产品的终极问题——"+5% EV 门槛在真实竞彩 SP 上到底赚不赚钱"——而样本量根本不足以回答。

**唯一真瓶颈**:**不是模型,是观测/记账回路的可信度**。这次审计最刺眼的事实是:本来用来回答"ROI 悬念"的那条回路,**自己是坏的**——
- B1 让每一笔赢钱被记小甚至记成亏损;
- R1 把不该下的负 EV 注塞进 ROI;
- D1 让本该自我纠偏的 T 校准变成空操作;
- R2/R5 让"已验证"的绿测其实是结构性盲区。

换句话说:**你现在就算开始大量真实下注,记账层也会给你一个系统性悲观且被污染的 ROI 数字**,让你无法判断 +5% 边际到底成不成立。在修好 B1/R1 之前积累的任何结算样本都是脏的,等于白积累。

**下一步力气该放哪(明确建议)**:
1. **先修 P0 的 B1 + R1**(记账正确性),否则后面所有下注样本作废;
2. **再修 D1**(让自校准真正上线,否则模型 frozen 后概率会无人纠偏地漂移);
3. **然后才是真正该投入的地方——攒真实结算样本**。模型不需要再调了(β/校准/文章 #6 已经证明这点);需要的是**让记账可信 + 跑足够多的真实下注**,把"ROI 悬念"从未知变成已知。这是唯一能推进产品的杠杆。

**反直觉的一句话**:这个项目的风险不在"模型不够好",而在"用来证明模型够好的那套观测设施有 bug,且这些 bug 全是同一家族——逻辑跑通、报告变绿、数字静默错误"。包括团队以为已经根除的 EV-vs-Pinnacle,这次在 pool 和 predict_report 里又抓到两处活体。**把这个家族清干净 + 让记账可信,比任何建模改进都更接近产品的真问题。**

---

**审计员声明**:全程只读。未编辑文件、未 git 提交、未重启 daemon、未改动观测库。所有载荷性数学复现经独立验证员对抗证伪;本报告已纠正原始 findings 中 3 处事实偏差(B3 的活跃联赛数 8→4、D5 的 predict_report.py:21 非 bug 且漏报 setup_local_pipeline.sh:377 孪生 bug、R5 的 grep 非空)。Lane C 的"复式 pool 结算"(`record_pool_session:597`)经验证:**底层 bug 为真但原 finding 的机制/复现/修法描述有误**——pool 票每腿仅 1 个 selection(`n_combos_total=1`),正确 `stake_units` 应为 1 而非"per-leg selection 数之积",欠估倍率是完整的 stake//2(非 2×);该路径当前无已结算 pool 注,潜伏未爆。