# V12 市场模式 Wrap-up — 反推让球 → 记账 → 扩张 → 前端 → 世界杯统一

_归档于 2026-05-30 · 收尾 commit `31665bb`_

## 一句话

把"让球推荐"从**模型猜盘**改成**反推市场盘**——用 Pinnacle 的 1X2 + 大小球去 vig
反解出进球网格，直接读任意整数让球线的让胜/让平/让负。实测它紧贴 Pinnacle 自己的
亚盘天花板、且优于我们自己的模型；然后把这套引擎接到记账、扩张到 23 个竞彩联赛、
配齐前端，最后连世界杯让球也并进同一条路。

> 产品红线不变：**只在竞彩下注**；Pinnacle 是「聪明钱」基准、不是下注场所；改任何
> 竞彩 SP 都即时重算 EV；对 EV 诚实——单样本不当证据。

---

## 核心方法：市场反推让球（`model/market_handicap.py`, commit `c4e4247`）

1. `devig_over(o,u)` 去掉大小球两边的 vig
2. `fit_lambdas(p_h,p_d,p_a,p_over)` 用 L-BFGS-B 把 Dixon-Coles 进球网格 (λ_home, λ_away)
   拟合到「去 vig 后的 1X2 + O/U(2.5)」（权重 1X2=4、O/U=2，ρ=−0.10）
3. `implied_handicap_lines(...)` 在网格上读出每条整数让球线的三项概率

**纯市场、零模型。** 验证：能在 ~1pp 内复现 Pinnacle 自己的亚盘（J1）、4663 场欧洲赛
平均偏差 0.49pp。

### 为什么用它替掉模型（无泄漏 walk-forward，4330 场欧洲赛，24/25）

| 让球引擎 | 亚盘命中 Brier | vs Pinnacle |
|---|---|---|
| Pinnacle 亚盘（天花板） | **0.20444** | — |
| 市场反推 | 0.20452 | +0.08e-3 |
| 我们的模型网格 | 0.20690 | +2.46e-3 |

反推几乎 = 天花板，且明确优于模型。机理：反推把进球总量**锚定到大小球盘**，模型的
总量是特征推出来的、噪声更大。生产模型当时无 correction 文件（`_load_correction()` → None），
所以这场对决比的是**公平模型**，不是被削弱的版本。

---

## 这一段做了什么（按 commit）

| Commit | 内容 |
|---|---|
| `c712249` | 待开盘列表：没 Pinnacle 线的赛事只列出、不评分 |
| `e87b857` / `45ff04e` | 一级杯赛 + J1 进市场模式（Pinnacle 去 vig，不用模型） |
| `c4e4247` | **反推引擎**：J1 + 杯赛的市场隐含让球 |
| `61cd9ef` / `ea1d25e` | **记账闭环**：record(📌) → auto-settle(`--leagues auto`) → ROI；结算从未结注里自动推联赛（补上了法甲/西乙/意乙/葡超 model 注从不结算的老洞） |
| `5011792` | **做 1**：13 个模型联赛的让球也切到反推（带 model-grid 兜底） |
| `a96b311` | **做 2**：扩到 10 个新竞彩联赛（北欧/亚太/欧洲） |
| `85797a6` | 10 新联赛的中文队名（字典 601 → 740） |
| `31665bb` | **世界杯统一**：退役 Path A++，WC 让球并入市场模式 |

---

## 现在的三种服务模式

| 模式 | 覆盖 | 让球来源 |
|---|---|---|
| **模型盘** | 13 欧洲联赛 | 反推（做 1 之后，不再用模型网格） |
| **市场模式** | 22 项：J1 + J2 + 10 新联赛 + 一级杯赛 + **世界杯/欧洲杯/欧预** | 去 vig 1X2 + 反推让球 |
| **待开盘** | 任何还没出 Pinnacle 线的 | 只列出、不评分 |

`_CUP_MARKET_COMPETITIONS` 共 22 项；新增 10 联赛 ID 已 pin 测试（NOR 103 / SWE 113 /
DNK 119 / FIN 244 / KOR 292 / J2 99 / AUS 188 / SCO 179 / TUR 203 / SUI 207），
其中北欧/K 联赛/J2 走自然年赛季。

## 世界杯统一（V12 W8）

WC/EURO/WC_QUAL_UEFA 本来就在市场模式里拿反推让球。退役的 **Path A++**
（λ_total 固定 2.6 先验 + 128 场国家队模型 blend + 往竞彩 SP 上 Bayesian blend）三处都更差：
无大小球锚定、模型不加分、还往竞彩盘上 blend 磨掉边际。前端 WC tab 的让球区改成
跳转按钮（→ 市场模式），保留 1X2 赛前预测；删了 ~128 行死 JS + 7 个孤儿 i18n 键；
后端 `/recommend/wc/single` 标记 DEPRECATED。CACHE_VERSION → `nutmeg-v12-fe-w8-wc-unified`。

---

## 诚实栏（这一段最重要的部分）

- **反推 = 天花板，不是超过天花板。** 它和聪明钱一样好，不比聪明钱强。对竞彩的边际
  来自**竞彩相对 Pinnacle 的错价**，不是来自"我们比 Pinnacle 准"。
- **这一段记的 3 笔命中（神户让胜 / 钢巴让负 / 京都让负）是噪声，不是验证。**
  3 连中在这种概率下约 1/57，期望 ROI 是负的（~−4.7%），实际账面 +306% 纯属方差。
  **别因为这 3 笔就加注。** n=3 不证明任何 edge——这正是产品 DNA 要防的单样本陷阱。
- **真实下注 ROI 仍是 0 个有意义的数据点。** 记账闭环 ship 了，但要跑足数周让结算
  累积，verdict 才闭合。在那之前，"这套有用"只是机理上成立 + 单样本好看。

---

## 验证锚点（可证伪）

- `pytest tests/v4/ -q` 全绿（含 `test_market_handicap` / `test_market_handicap_tracking` /
  `test_auto_settle_pending` / `test_league_coverage::TestMarketModeExpansion` /
  `test_wc_handicap_dashboard`）
- `TEAM_NAME_ZH` = 740；`_CUP_MARKET_COMPETITIONS` = 22（含 WC/EURO/WC_QUAL_UEFA）
- daemon(8080) 重启后 `sw.js` 发 `nutmeg-v12-fe-w8-wc-unified`；
  `POST /recommend/market-handicap`（巴西 −1）回市场概率 [0.386/0.242/0.372]、对竞彩 SP 正确标让负 +EV

## 待办（低优先）

- 真实 ROI：跑数周让结算累积，再读 `nutmeg-ab-report`（唯一能闭合 value claim 的路）
- 少数生僻新联赛球队仍回退拉丁名——看到就补
- `/recommend/wc/single` 已 DEPRECATED，下个清理窗口可整段删（含 `national_team_handicap.py` Path A++）
