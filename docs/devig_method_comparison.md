# 去 vig 方法对比:该不该把 `_pinnacle_devig_1x2` 从朴素归一换掉?

**状态:📚 参考文献 + 可落地建议** · 记于 2026-06-24 · 派生自 [[sharp_money_market_microstructure]] §4(Štrumbelj:Shin > 朴素归一)

> **出处说明**:初稿前台网搜,后用**多 agent 深度研究重跑**(63 条逐字声明 / 15 来源)**纠错 + 补强** —— 重跑发现 Buchdahl 在 **136,876 场 Pinnacle 收盘**上的一手实测,推翻了初稿「odds-ratio 最好」的二手说法,并给出 WPO 的闭式公式(见 §2 ⚠️)。来源含同行评议(Štrumbelj 2014、Clarke-Kovalchik-Ingram 2017、Shin 1992/93、Buchdahl 一手实测)。
>
> **一句话**:**把基础/朴素归一换掉** —— 它是所有人公认最差的(无视冷门偏差)。**首选 WPO(margin∝赔率)** —— Buchdahl 在 13.7 万场 Pinnacle 上并列最佳,且有**闭式逆解 `Of=3O/(3−MO)`、零迭代**;次选 power。对 Pinnacle 这种**低抽水(~2.7%)**书,升级幅度不大,但**对冷门 + 平局腿最关键** —— 直接少掉一批「朴素归一虚高冷门 P → 假 +EV」的冷门陷阱(且只在「有明显热门」时才有差)。

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
- **Clarke-Kovalchik-Ingram 2017 [A]**(三个大数据集/多运动,log-loss/Brier/RMSE):**power 法普遍优于乘性(基础),且 ≈ 或优于 Shin**;绝不越界、单参数。**但差距很小**(ATP log-loss 0.548 power vs 0.550 乘性;gallop 上 additive 反而最优)→ FLB-aware 几个方法**彼此很近、数据集相关**。
- **Buchdahl 直接在 Pinnacle 上实测 [A 级一手,最关我们] —— 136,876 场 Pinnacle 收盘 1X2 足球(2007–2016),盲打所有「公允」结果的实现 yield**:

  | 方法 | yield(越近 0 越好) |
  |---|---|
  | Pinnacle 原始赔率(不去 vig) | **−3.36%** |
  | 等 margin(=基础/归一) | −0.56% |
  | **margin∝赔率(WPO)** | **+0.1%** ✅ |
  | **对数(=power)** | **+0.07%** ✅ |
  | odds-ratio | −0.20% |

  → **最好 = margin∝赔率(WPO)+ 对数/power,几乎并列、yield 最接近 0;等 margin 最差(无视 FLB);odds-ratio 在这批 Pinnacle 数据上反而垫底(低估了 FLB 强度)。**

> ⚠️ **多 agent 重跑纠错**:前台初稿曾据二手摘要说「odds-ratio 拟合最好」—— Buchdahl 一手数据(上表)证伪:在 Pinnacle 上 odds-ratio 是 FLB-aware 三法里**最差**的。以本表为准。

→ **结论**:基础法淘汰是铁的;**在 Pinnacle 上 WPO 与 power 并列最佳**,Shin 紧随,odds-ratio 偏弱。都比基础好。**何时才有差别:只有「有明显热门」时** —— 实测**最大赔率 < 3.45(无明显热门)时四法等价**;差异全在有热门/冷门的盘。

> **✅ 实测补全 Buchdahl 表缺的 Shin 行(2026-06-26 · 28,407 场 football-data Pinnacle 收盘 1X2 · realized logloss/Brier/ECE)**:**WPO 0.99801 < Shin 0.99807 < basic 0.99833**(logloss);配对自助 **Shin − WPO = +6e-5,95%CI [+1e-5, +1e-4](排除 0)→ Shin 在 Pinnacle 上统计显著(虽极微)差于 WPO**;ECE 同序(WPO 0.30% < Shin 0.38% < basic 0.63%);Shin 的内幕比例 **z̄=0.015**(吻合文献~0.01-0.02)。差异集中在强热门桶(minodds<1.5)。**净判:WPO 实测就是 Pinnacle 最优,Shin 不是升级 → 别换。** 上文「Shin 紧随」原是据 Štrumbelj 的一般足球结论;在 Pinnacle 直接实测后应读作「Shin 微逊 WPO」。脚本 `scratchpad/devig_1x2_measure.py`。

---

## 3. 对 Nutmeg 的具体含义(可落地)

1. **换掉 `_pinnacle_devig_1x2` 的基础归一。** 这是有同行评议背书、零争议的升级。
2. **首选 WPO(margin∝赔率)—— 它在 Pinnacle 上并列最佳,且有闭式逆解、零迭代:**
   - 3 路公允赔率:**`Of = 3·O / (3 − M·O)`**(`O`=Pinnacle 赔率,`M`=该场总 margin=ΣrΣ−1;n 路则 `Of = n·O/(n−M·O)`)。**~3 行、无求根、Buchdahl 在 136,876 场 Pinnacle 实测 yield +0.1%(并列最佳)。**
   - **次选 power**(`p_i ∝ r_i^{1/k}`,一维求根解 `k`):同样并列最佳、绝不越界;**备选 Shin**(`mberk/shin`)。三者都行,WPO 最省事。
3. **幅度要诚实:Pinnacle 抽水仅 ~2-3%**(实测 2.7%,vs bet365 5.5% / WH 7.4% / Ladbrokes 7.8%)**→ 能错配的 margin 本来就少 → 升级幅度小。** 影响最大在 **① 1X2 的冷门腿 + 平局腿;② 高赔的让球冷门**。**有明显热门时才有差(最大赔率 <3.45 则四法等价)**;主盘热门几乎无差别。
4. **方向性收益(直接关「防冷门陷阱」)**:基础归一**不收缩虚高的冷门** → **高估冷门公允 P → 高估冷门竞彩腿的 EV → 假 +EV 冷门陷阱**。换 Shin/power 把冷门公允 P 压实 → **少一批假 +EV**。这正是本季 `EV 可靠性分级(防冷门陷阱)` 那条任务的上游修法。
5. **两路盘市场分别看:**
   - **3 路 1X2**:方法差异最大(三结果 + 平局),**该升级**。
   - **2 路(亚盘 / 大小球)**:平衡线两结果近 50/50,冷门偏差极小,**基础归一近乎够用** —— 让球/大小球的 de-vig 不是优先项。**✅ 已实测落地(2026-06-26)**:在 **23,840 场 football-data Pinnacle 收盘**上,把 `devig_over` 从 basic 改走 WPO,让球重建 P 只动 **0.046pp 均值**(p99 0.22pp、极端偏盘最大 0.71pp),**三路校准零变化**(logloss Δ=−6e-6,配对自助 95%CI [−2e-5,+1e-5] 跨 0),0.05pp P ≈ 0.1pp EV vs +5% 门槛 → **约 50× 不够翻任何一注**。机制:O/U 只轻推 λ_total(对整数让球线的 cover 是二阶),已 WPO 的 1X2 split 主导。**结论:`devig_over` 维持 basic 是经实测的正确选择,别再当"不一致" bug 去追。**(对比:1X2 那条 WPO 升级该做、已做。)
6. **实现参考**:R `implied` 包 / Python `mberk/shin` 都实现了全部方法;§1 公式可直接搬进 `_pinnacle_devig_1x2`。

> **净建议**:做一个**小 PR** —— `_pinnacle_devig_1x2` 改用 **WPO 闭式**(`Of = 3O/(3−MO)`,默认)、保留基础法作对照开关,在历史 1X2 上比一比冷门腿的公允 P 变化。**零迭代、Buchdahl 在 136,876 场 Pinnacle 实测并列最佳、专治冷门假 +EV。** 这是「一次研究换一个代码升级」的典型,可在秋天软水测试前先做(让那时的 EV 口径更干净)。

---

## 参考文献

### A · 同行评议 / 一手大样本实测
- Štrumbelj (2014). *On determining probability forecasts from betting odds.* Int. J. of Forecasting 30(4):934–943 — https://www.sciencedirect.com/science/article/abs/pii/S0169207014000533
- Clarke, Kovalchik & Ingram (2017). *Adjusting Bookmaker's Odds to Allow for Overround.* American J. of Sports Science 5(6):45 — https://outlier.bet/wp-content/uploads/2023/08/2017-clarke-adjusting_bookmakers_odds.pdf
- Shin (1992, 1993). *Prices of state-contingent claims with insider traders, and the favourite-longshot bias.* Economic Journal 102:426–435 / 103:1141–1153
- **Buchdahl — *The Wisdom of the Crowd*(updated 2017)** — 4 法在 **136,876 场 Pinnacle 收盘 1X2**(2007–2016)的 yield 实测 + WPO 闭式 `Of=3O/(3−MO)` — https://www.football-data.co.uk/The_Wisdom_of_the_Crowd_updated.pdf

### 实务 / 实现
- `implied` R package(8 法:basic/shin/bb/wpo/or/power/additive/jsd,全部公式)— https://cran.r-project.org/web/packages/implied/vignettes/introduction.html
- `mberk/shin` — Python Shin implementation — https://github.com/mberk/shin
- Pinnacle Odds Dropper — *How to de-vig Pinnacle's odds*(推荐 power)— https://www.pinnacleoddsdropper.com/guides/how-to-devig-pinnacle-s-odds-for-betting-on-soft-books

*相关:[[sharp_money_market_microstructure]] §4/§7、[[score_grid_cell_calibration]](反推网格的另一半:单格不可信)、记忆 `sharp-money-timing-research`。*
