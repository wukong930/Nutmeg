# Kelly 下注:参数不确定 + 同时多注 + 相关注的正确打法

**状态:📚 参考文献 + 可落地建议 → ✅ 对抗核查过(2026-06-25)** · 记于 2026-06-24 · 加固下注层(秋天腿 +EV 时直接用)

> **出处说明**:初稿前台网搜 + 综合(2026-06-24,无核查)。**2026-06-25 两轮多 agent 对抗核查**(skeptical、专门找错):① 全量 ①②③ —— 103 agent / 3.37M token / 17 confirmed;② 焦点补查 ④⑤ —— 101 agent / 3.83M token / 22 confirmed(总 40 源、39 confirmed)。两轮 synthesize 步均死于会话 token 上限 → 人工综合已核查声明(见下「对抗核查结果」)。来源含同行评议(Baker-McHale 2013、Whitrow 2007、Smoczynski-Tomkins 2010、Busseti-Ryu-Boyd 2016、Laureti-Medo-Zhang 2010、Nekrasov)+ Thorp《Understanding Kelly》、MacLean-Ziemba-Li、Chu-Wu-Swartz。
>
> **一句话**:**用分数 Kelly(半 Kelly 起步)** —— 它一箭三雕地对冲了**参数不确定**(我们的 P 是估的)、压住**回撤**(半 Kelly 拿 75% 增长、回撤减半)。**同时多注**时不能把每注的单注 Kelly 直接相加(会过杠杆)—— 要解联合对数最优 stake 向量。**相关注/同场腿**要用联合分布、正相关就减仓;**串关用最小注**(相关估计误差大)。**这套和 Nutmeg 现有串关机器(§2 软水研究)的设计一致,本研究是验证 + 收紧。**

---

## ✅ 对抗核查结果(2026-06-25)

> 两轮对抗核查(专门找错,不是确认):先查 ①②③(17 confirmed),再焦点补查 ④⑤(22 confirmed)。**5 条方向全对**,抓出 **3 处要改**(§1 数字 / §3 外积 / §4 引用,跟 de-vig 重跑抓 odds-ratio 一个性质)。下表已就地改进。

| # | 声明 | 裁决 | 要点 / 改了什么 |
|---|---|---|---|
| ① | 半 Kelly ¾增长/半方差 + 41%/22.6% 回撤 | ⚠️ **部分对,数字改** | ¾增长是**对数正态/连续**近似、非普适(Thorp:一般离散下 `Var[ln(1+fX)]` 都不一定凸;MZL 映射「可能很差」)[3-0]。**41%/22.6% 不是文献的 Kelly 回撤** —— 就是 `1−(1−f)⁵` 复利算术,降级成「玩具直觉」;文献用「先翻倍 vs 先减半」概率(满 0.67→半 0.89) |
| ② | 估计不确定→过注;分数 Kelly≈最优收缩 | ✅ **确认**(收缩=代理) | 过注**强确认**[多条 3-0]:plug-in 系统性高估 f*、过注「又险又少赚」、真 p 常<标称、Baker-McHale「样本外差于样本内」、修法=缩仓。「半 Kelly≈最优收缩」是**实用代理**:Chu-Wu-Swartz 的 f0「近似半 Kelly」[2-1];Baker-McHale 最优收缩是**导出因子、非恒等 ½**[3-0] |
| ③ | 同时多注=解联合向量≠相加;**外积** | ✅ 核心确认 / ❌ **外积改** | 核心**强确认**[3-0]:n 个同种独立注 `f*<1/n`、单一联合优化、不能相加。**「外积」被 0-3 否决**:只在**能下整张菜单(单关+所有串关)**时精确;**只下单关的同时注 ≠ 外积**,是单注 Kelly **减一个三次项收缩**(Whitrow「近正比」) |
| ④ | 相关→联合分布、正相关减仓、串关最小注 | ✅ **确认**(焦点补查 3-0) | A-i 联合分布(Breiman「需知联合分布」)、A-ii 正相关减仓(`C=1→有效分散 m_ef=1` 坍缩)、A-iii 全 Kelly 估计误差下**实测 100% 破产 vs 分数 0%**(足/篮数据)—— 全 3-0。**A-iv 确认 `Laureti 0712.2771` 引错**[3-0]:它**假设参数已知**、讲「condensation」(no-short 约束所致,非估计误差)→ 已删。**正解引用** = Baker-McHale 2013(估计收缩,§2 已引)+ Nekrasov / arXiv 0805.3397(相关减仓) |
| ⑤ | Risk-Constrained Kelly 凸、capped 回撤 | ✅ **确认**(焦点补查 3-0 verbatim) | B-i 真方法(Busseti-Ryu-Boyd 2016)、B-ii 回撤约束 **`Prob(W^min<α)<β`**(例 α=0.7/β=0.1 =「>30% 回撤概率<10%」)、B-iii **凸**(难解概率约束 → `E[(r·b)^−λ]≤1`,作者证凸)—— 全 3-0。唯 B-iv(`λ=logβ/logα` 机制 + RCK vs 半 Kelly 谁优)votes 死于 token、从一手源抽出未三票复核(细节,不影响结论) |

**净结论(对 Nutmeg 不变)**:半 Kelly 默认、同时多注解联合向量、相关/串关强分数 Kelly —— 方向全部站得住。改的是**精度**:§1 回撤数字降级为玩具、§3 外积加条件、§4 删错引用。

---

## 0. 经典 Kelly 一行回顾
`f* = (b·p − q)/b = edge/赔率`(b=净赔率,p=胜率,q=1−p)。最大化 **E[log(财富)]** = 长期几何增长最快。**但它假设 p 已知、且每注独立顺序结算** —— 这三条在体育投注里全不成立,下面逐条修。

---

## 1. 为什么必须分数 Kelly(增长-方差权衡,有实数)

- **半 Kelly:~¾ 增长 / ~½ 方差 —— 但这是「对数正态/连续」近似,非普适**(✅ 核查:Thorp 明说该平滑权衡只在连续情形成立,一般离散下 `Var[ln(1+fX)]` 都不一定凸;MacLean-Ziemba-Li 的分数Kelly↔负幂效用映射「可能是很差的近似」)。**⚠️ 下面这俩回撤数字不是文献里的 Kelly 结果**,就是 `1−(1−f)⁵` 复利算术(连输 5 把的玩具最坏情形,仅作直觉):满 10%→**41%**、半 5%→**22.6%**。文献量下行用「先翻倍 vs 先减半」概率(满 0.67→半 0.89),不是每段回撤 %。
- **几乎所有职业玩家用分数 Kelly**;半 Kelly 最常见,边很不确定时用 1/4 Kelly。
- 分数 Kelly **让资金曲线对估计误差不敏感** —— 这正是下面 §2 的对冲。

---

## 2. 参数不确定 → 必须缩仓(p 是估的,不是已知的)

- **核心病**:Kelly 假设 p 精确已知;用**估计的 p**(我们的去 vig Pinnacle 公允)代入 → **系统性过注、样本外远差于样本内**。差几个百分点就严重过杠杆。
- **正解 = 按估计不确定性缩仓** [A]:Baker & McHale 2013《Optimal Betting Under Parameter Uncertainty》(Decision Analysis 10(3):189–199)给了**决策论的收缩因子** + 一个「信封背面」近似修正。Chu-Wu-Swartz 的 Modified Kelly 同向。
- **贝叶斯 Kelly**:把预测的不确定性纳入 → **自动缩仓**(越不确定缩越多)。**分数 Kelly 就是这个收缩的实用代理。**
- → **对 Nutmeg**:我们的 P 来自去 vig Pinnacle(估计量,且竞彩 SP 是软价),**估计误差实打实存在 → 半 Kelly 是合理默认**,边特别不确定(小样本联赛)用 1/4。

---

## 3. 同时多注 → 解联合 stake 向量,**不能把单注 Kelly 相加**

- **病**:一天一排比赛**同时结算**,共享同一个资金池。给每注它各自的**单注 Kelly** 再相加 → **总杠杆过高**(它们在抢同一个 bankroll)。
- **正解** [A]:最大化 **E[log(财富)]** over **联合 stake 向量**,受同时结算的联合结果约束 → **凸优化**(一般无闭式,可数值解)。Whitrow 2007《Algorithms for optimal allocation of bets on many simultaneous events》:多注独立时,最优注额 ≈ 正比于各注的「概率边」,**但总额要按比例压下来**。Smoczynski-Tomkins 2010 给了赛马的闭式特例。
- **独立多注「外积」要分情形**(❌ 核查 0-3 否决了无条件版):各单事件 Kelly 的**外积**只在**能下整张菜单(单关 + 所有串关组合)、独立、乘式定价**时才精确。**只下单关的同时注**(标准「同时多注」)最优 **≠ 外积、也 ≠ 各自单注 Kelly**,而是单注 Kelly **减一个三次项收缩**(只到二阶才相等 = Whitrow「近正比」)。竞彩能下串关,但不会把 2ⁿ 个组合全下 → **别套外积当通解**。
- → **对 Nutmeg**:秋天若一天有多条 +EV 单关同时打,**别把各自半 Kelly 简单相加** —— 要么数值解联合对数最优,要么近似:注额 ∝ 边、但总敞口设上限(同时注越多、总额缩越多)。这是 `combo/` 注额层该补的一块。

---

## 4. 相关注 → 算协方差,正相关减仓,串关用最小注

- **病**:Kelly 假设各注独立;**同场多腿、同球员、同叙事**会造相关风险,Kelly 默认算不到。
- **正解** [A](✅ 焦点补查 3-0):多元 Kelly 需要结果的**联合分布**(Breiman:「需知联合分布」;模型自由近似 = 全协方差阵 `u*=Σ⁻¹·超额`)。**正相关 → 有效分散坍缩(`C=1` 时 M 个资产塌成 1)→ Kelly 分数必须调小**;负相关 = 对冲、可适当加。正解引用 = **Nekrasov(多元 Kelly)+ arXiv 0805.3397**(相关减仓)。(🔧 核查:原引 `Laureti et al. 2010 / arXiv 0712.2771` **引错**[3-0] —— 那篇**假设参数已知**、讲「condensation/欠分散」(no-short 约束所致),**不是**相关-估计-误差;已删,改引 Baker-McHale 2013 当估计收缩源。)
- **串关**:要估**整串的联合命中概率(不是各腿相乘)**;且**「多数人不该对串关用 Kelly,用最小注」**(✅ 3-0)—— 全 Kelly 在估计误差下**实测 100% 破产 vs 分数 0%**(足/篮真数据,arXiv 2107.08827);腿间相关 + 联合命中概率估计误差复利放大。
- → **对 Nutmeg**:这**正是 §2 软水研究已做对的**:同场腿用**蒙特卡洛抽联合比分(不相乘)**、跨场用乘法。本研究背书该设计,并补一条:**串关注额走最小注/强分数 Kelly,别让相关估计误差吃掉边。**

---

## 5. 实用配方(一句话能执行)

1. **默认半 Kelly**(边很不确定时 1/4)—— 同时对冲估计误差 + 压回撤。
2. **同时多注**:不相加单注 Kelly;解联合对数最优 stake 向量(凸,数值),或近似「∝边 + 总敞口封顶」。
3. **相关/同场腿**:用联合分布(MC),正相关减仓;**串关用最小注**。
4. **加破产/回撤约束**(Risk-Constrained Kelly,Busseti-Ryu-Boyd 2016,凸)——设一个最大回撤上限,在该约束下求 Kelly。
5. **竞彩特例**:单注不可拆、不可选价 → 主要是「一天多条 +EV 单关」的同时多注问题(§3)+ 复式串关的相关问题(§4)。EV 是估的 → 半 Kelly 打底。

---

## 6. 对 Nutmeg 的裁决

- **现有串关机器(§2 软水研究:同场 MC 联合、跨场乘法、Kelly/破产模拟)在结构上是对的** —— 本研究用同行评议背书了它。
- **要补的两块**(秋天腿 +EV 前做):① **同时多注的联合 stake 向量**(别相加单注 Kelly,`combo/` 注额层补凸优化或「∝边+封顶」近似);② **全局默认半 Kelly + 可选破产约束**(我们的 P 是估的,这是必须的缩仓)。
- **与 DNA 一致**:不臆造边、保守缩仓、相关用联合分布 —— 都是本季一路的纪律,现在有 Kelly 文献的精确依据。
- **优先级**:这层**等秋天有 +EV 腿才用得上**(现在空仓,无腿可下)→ 归到 `parlay_soft_water_research` §8 的「有腿就几天能上」那批,不是现在建。

---

## 参考文献

### A · 同行评议
- Baker & McHale (2013). *Optimal Betting Under Parameter Uncertainty: Improving the Kelly Criterion.* Decision Analysis 10(3):189–199 — https://ideas.repec.org/a/inm/ordeca/v10y2013i3p189-199.html
- Whitrow (2007). *Algorithms for optimal allocation of bets on many simultaneous events.* (J. Royal Statistical Society C) — https://www.researchgate.net/publication/4772949
- Smoczynski & Tomkins (2010). *An explicit solution to the problem of optimizing the allocations of a bettor's wealth …* (Kelly closed form) — https://www.researchgate.net/publication/220210144_Optimal_Betting_Strategies_for_Simultaneous_Games
- Busseti, Ryu & Boyd (2016). *Risk-Constrained Kelly Gambling.* arXiv:1603.06183 — https://arxiv.org/pdf/1603.06183
- *Kelly betting on horse races with uncertainty in probability estimates.* arXiv:1701.02814 — https://arxiv.org/pdf/1701.02814
- Chu, Wu & Swartz. *Modified Kelly Criteria.* (f0 ≈ 半 Kelly 的理论依据)— https://www.sfu.ca/~tswartz/papers/kelly.pdf
- Thorp. *Understanding the Kelly Criterion.* (✅ 3-0 核查源:¾增长=连续近似、`Var[ln(1+fX)]` 非凸、`f*<1/n`、过注「又险又少赚」)— https://rybn.org/halloffame/PDFS/2008_Understanding_Kelly_New.pdf
- *Optimal sports betting strategies in practice: an experimental review.* arXiv:2107.08827 — https://arxiv.org/pdf/2107.08827

### 实务 / 模拟
- Downey — *Why fractional Kelly? Simulations of bet size with uncertainty and downside risk* — https://matthewdowney.github.io/uncertainty-kelly-criterion-optimal-bet-size.html
- Nekrasov — *Kelly criterion for multivariate portfolios: a model-free approach* (✅ 相关注正解:`u*=Σ⁻¹·超额`;估计误差→用协方差上界 underbet)— https://www.cs.miami.edu/home/burt/learning/mth649.191/docs/SSRN-id2259133.pdf
- MacLean, Thorp & Ziemba — *Good and bad properties of the Kelly criterion* — https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf
- ✅ 焦点补查 ④⑤ 新增一手源:相关→有效分散坍缩(`C=1→m_ef=1`)arXiv:0805.3397 · 有限样本估计收缩 `f*(w,L)=(2w−L)/(L+2)` arXiv:0803.1364 · Laureti-Medo-Zhang《Analysis of Kelly-optimal portfolios》(Quant. Finance 2010 / arXiv:0712.2771)—— **假设参数已知、讲 condensation,别为估计误差引它**

*相关:`docs/parlay_soft_water_research.md` §2(组合数学 + Kelly/破产机器,本研究背书并收紧)、§8(有腿几天能上)、[[forecasting_frontier_vs_market.md]](Hubáček-Šír 的「只赌方向」与此互补)。*
