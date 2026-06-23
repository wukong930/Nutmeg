# 去 vig 方法对比:该不该把 `_pinnacle_devig_1x2` 从朴素归一换掉?

**状态:📚 参考文献 + 可落地建议** · 记于 2026-06-24 · 派生自 [[sharp_money_market_microstructure]] §4(Štrumbelj:Shin > 朴素归一)

> **出处说明**:本文为前台直接网搜 + 综合(deep-research 后台在本机休眠下不稳,故改前台做)。来源含同行评议(Štrumbelj 2014、Clarke-Kovalchik-Ingram 2017、Shin 1992/93)+ 实务(Buchdahl WoC、`implied` R 包、`mberk/shin`)。
>
> **一句话**:**把基础/朴素归一换掉** —— 它是所有人公认最差的(无视冷门偏差)。换成 **power 法**(最省事、绝不越界、≈/优于 Shin)或 **Shin 法**(足球实证最佳)。对 Pinnacle 这种**低抽水(~2-3%)**书,升级幅度不大,但**对冷门 + 平局腿最关键** —— 直接少掉一批「朴素归一虚高冷门 P → 假 +EV」的冷门陷阱。

---

## 1. 六种方法(公式可直接落地,来自 `implied` 包)

记 `r_i = 1/赔率_i`(原始隐含),`Σr = booksum`(> 1 即含 margin)。

| 方法 | 公式 | 处理冷门偏差 | 会越界? | 一句话 |
|---|---|---|---|---|
| **基础/归一** | `p_i = r_i / Σr` | ❌ 否 | 否 | **最差**(`implied` 原话:least accurate) |
| **Shin** | 内插式:假设有比例 `z` 的内幕交易者,反解 `p_i`;`z` 迭代估出 | ✅ 隐式 | 否 | Štrumbelj:足球**最佳**;`z` 对 Pinnacle 很小(~0.01) |
| **Power(=对数)** | `p_i = r_i^{1/k}`,选 `k` 使 `Σp=1` | ✅ 隐式 | **绝不** | Clarke-Kovalchik:**≈/优于 Shin**,单参数、最稳 |
| **Odds-ratio (OR)** | `p_i = r_i / (OR + r_i − OR·r_i)`,选 `OR` 使 `Σp=1` | ✅ 隐式 | 否 | Buchdahl WoC:**按实际回报拟合最好** |
| **加性** | `p_i = r_i − (Σr−1)/n` | ❌ 否 | **会负!** | 多结果/冷门时产生负概率 → **别用** |
| **WPO / 群体智慧** | `p_i = (n − M·O_i)/(n·O_i)`,`M`=margin、`O_i`=赔率 | ✅ 显式 | 否 | margin 按赔率长度加权 |

> 「会冷门偏差处理」= 给**热门让更少 margin、给冷门让更多 margin**(除基础/加性外都这么做)。基础法把 margin **平均**摊 → 系统性**高估冷门 P、低估热门 P**。

---

## 2. 谁最准?(证据,排名很近)

- **基础/归一 = 公认最差**(唯一强共识):忽略冷门偏差。`implied` 包直接标 least accurate。
- **Štrumbelj 2014 [A,IJF]**:在足球上,**Shin 隐含概率比基础归一和回归法都更准**,各 book/运动对都成立;Shin 给无偏的胜率估计,基础归一不修冷门偏差。
- **Clarke-Kovalchik-Ingram 2017 [A]**(三个大数据集/多运动):提出 **power 法**;结论 **power 法普遍优于乘性(基础),且 ≈ 或优于 Shin**;优点:**绝不产生 [0,1] 外的值、单参数、实现简单**。
- **Buchdahl「Wisdom of the Crowd」[实务]**:'margin∝赔率'、'odds-ratio'、'对数' 三法都**远胜**'等 margin'(基础);按**实际回报**,**odds-ratio 拟合最好**。

→ **结论**:基础法淘汰是铁的;Shin / power / OR / 对数四个 FLB-aware 法**彼此很近、数据集相关**。没有唯一赢家,但都比基础好。

---

## 3. 对 Nutmeg 的具体含义(可落地)

1. **换掉 `_pinnacle_devig_1x2` 的基础归一。** 这是有同行评议背书、零争议的升级。
2. **推荐 power 法**(`p_i ∝ r_i^{1/k}`,一维求根解 `k`)——
   - 单参数、绝不越界、实现 ~5 行、Clarke-Kovalchik 实测 ≈/优于 Shin。
   - 备选 **Shin**(足球实证最佳,Štrumbelj),实现可抄 `mberk/shin`(Python)。两者都行,别纠结。
3. **幅度要诚实:Pinnacle 抽水仅 ~2-3% → 能错配的 margin 本来就少 → 升级幅度小。** 影响最大在 **① 1X2 的冷门腿 + 平局腿;② 高赔的让球冷门**。主盘热门几乎无差别。
4. **方向性收益(直接关「防冷门陷阱」)**:基础归一**不收缩虚高的冷门** → **高估冷门公允 P → 高估冷门竞彩腿的 EV → 假 +EV 冷门陷阱**。换 Shin/power 把冷门公允 P 压实 → **少一批假 +EV**。这正是本季 `EV 可靠性分级(防冷门陷阱)` 那条任务的上游修法。
5. **两路盘市场分别看:**
   - **3 路 1X2**:方法差异最大(三结果 + 平局),**该升级**。
   - **2 路(亚盘 / 大小球)**:平衡线两结果近 50/50,冷门偏差极小,**基础归一近乎够用** —— 让球/大小球的 de-vig 不是优先项。
6. **实现参考**:R `implied` 包 / Python `mberk/shin` 都实现了全部方法;§1 公式可直接搬进 `_pinnacle_devig_1x2`。

> **净建议**:做一个**小 PR** —— `_pinnacle_devig_1x2` 加 power 法(默认)、保留基础法作对照开关,在历史 1X2 上比一比冷门腿的公允 P 变化。**低风险、有同行评议背书、且专治冷门假 +EV。** 这是「一次研究换一个代码升级」的典型,可在秋天软水测试前先做(让那时的 EV 口径更干净)。

---

## 参考文献

### A · 同行评议
- Štrumbelj (2014). *On determining probability forecasts from betting odds.* Int. J. of Forecasting 30(4):934–943 — https://www.sciencedirect.com/science/article/abs/pii/S0169207014000533
- Clarke, Kovalchik & Ingram (2017). *Adjusting Bookmaker's Odds to Allow for Overround.* American J. of Sports Science 5(6):45 — https://outlier.bet/wp-content/uploads/2023/08/2017-clarke-adjusting_bookmakers_odds.pdf
- Shin (1992, 1993). *Prices of state-contingent claims with insider traders, and the favourite-longshot bias.* (insider-trader de-vig model)
- *A Family of Solutions Related to Shin's Model For Probability Forecasts* — https://www.researchgate.net/publication/381565059

### 实务 / 实现
- Buchdahl — *The Wisdom of the Crowd* (margin∝odds / odds-ratio / log methods) — https://www.football-data.co.uk/The_Wisdom_of_the_Crowd_updated.pdf
- `implied` R package vignette (全部方法公式) — https://cran.r-project.org/web/packages/implied/vignettes/introduction.html
- `mberk/shin` — Python Shin implementation — https://github.com/mberk/shin

*相关:[[sharp_money_market_microstructure]] §4/§7、[[score_grid_cell_calibration]](反推网格的另一半:单格不可信)、记忆 `sharp-money-timing-research`。*
