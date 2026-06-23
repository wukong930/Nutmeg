# Kelly 下注:参数不确定 + 同时多注 + 相关注的正确打法

**状态:📚 参考文献 + 可落地建议** · 记于 2026-06-24 · 加固下注层(秋天腿 +EV 时直接用)

> **出处说明**:本文为前台网搜 + 综合(多 agent 后台在本机连续 5 次休眠 wedge,改前台做以避免再卡)。来源含同行评议(Baker-McHale 2013、Whitrow 2007、Smoczynski-Tomkins 2010、Busseti-Ryu-Boyd 2016)+ 实务模拟。
>
> **一句话**:**用分数 Kelly(半 Kelly 起步)** —— 它一箭三雕地对冲了**参数不确定**(我们的 P 是估的)、压住**回撤**(半 Kelly 拿 75% 增长、回撤减半)。**同时多注**时不能把每注的单注 Kelly 直接相加(会过杠杆)—— 要解联合对数最优 stake 向量。**相关注/同场腿**要用联合分布、正相关就减仓;**串关用最小注**(相关估计误差大)。**这套和 Nutmeg 现有串关机器(§2 软水研究)的设计一致,本研究是验证 + 收紧。**

---

## 0. 经典 Kelly 一行回顾
`f* = (b·p − q)/b = edge/赔率`(b=净赔率,p=胜率,q=1−p)。最大化 **E[log(财富)]** = 长期几何增长最快。**但它假设 p 已知、且每注独立顺序结算** —— 这三条在体育投注里全不成立,下面逐条修。

---

## 1. 为什么必须分数 Kelly(增长-方差权衡,有实数)

- **半 Kelly:拿满 Kelly ~75% 的增长率,但方差/回撤减半。** 满 Kelly(单注 10%)连输 5 把 → **41% 回撤**;半 Kelly(5%)→ **22.6%**。
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
- **独立多注 + 乘式串关定价**:最优 = 各单事件 Kelly 的**外积**(先各自解,再组合)。
- → **对 Nutmeg**:秋天若一天有多条 +EV 单关同时打,**别把各自半 Kelly 简单相加** —— 要么数值解联合对数最优,要么近似:注额 ∝ 边、但总敞口设上限(同时注越多、总额缩越多)。这是 `combo/` 注额层该补的一块。

---

## 4. 相关注 → 算协方差,正相关减仓,串关用最小注

- **病**:Kelly 假设各注独立;**同场多腿、同球员、同叙事**会造相关风险,Kelly 默认算不到。
- **正解** [A]:多元 Kelly 需要结果的**联合分布**(Breiman 理论;Laureti et al. 2010 给相关情形解)。**正相关 = 等于加倍押同一个东西 → Kelly 分数必须调小**;负相关 = 对冲、可适当加。
- **串关**:要估**整串的联合命中概率(不是各腿相乘)**;且**「多数人不该对串关用 Kelly,用最小注」** —— 因为腿间相关性估计误差大,误差会复利放大。
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
- Chu, Wu & Swartz. *Modified Kelly Criteria.* — https://www.sfu.ca/~tswartz/papers/kelly.pdf
- *Optimal sports betting strategies in practice: an experimental review.* arXiv:2107.08827 — https://arxiv.org/pdf/2107.08827

### 实务 / 模拟
- Downey — *Why fractional Kelly? Simulations of bet size with uncertainty and downside risk* — https://matthewdowney.github.io/uncertainty-kelly-criterion-optimal-bet-size.html
- *Kelly criterion for multivariate portfolios: a model-free approach* (相关注) — https://www.cs.miami.edu/home/burt/learning/mth649.191/docs/SSRN-id2259133.pdf
- MacLean, Thorp & Ziemba — *Good and bad properties of the Kelly criterion* — https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf

*相关:`docs/parlay_soft_water_research.md` §2(组合数学 + Kelly/破产机器,本研究背书并收紧)、§8(有腿几天能上)、[[forecasting_frontier_vs_market.md]](Hubáček-Šír 的「只赌方向」与此互补)。*
