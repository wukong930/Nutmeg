# 比分网格的单格校准:反推网格的格子可信吗?

**状态:📚 参考文献 + 决策(research reference + verdict)** · 记于 2026-06-24 · 派生自 `parlay_soft_water_research.md` §7(比分/总进球做不做)的前置缺口

> **出处说明**:本文由一次 deep-research workflow 落盘的 **24 个分级来源 / 119 条逐字声明**(覆盖 Maher、Dixon-Coles、Karlis-Ntzoufras、Koopman-Lit、Boshnakov-Kharrat-McHale、Marra、Reade-Singleton、Cain-Law-Peel 等)综合而成。workflow 因本机休眠停在最后综合步,故成文由人工从已落盘的分级声明完成;凡标 **[A]** 的为同行评议期刊原文逐字引文。
>
> **一句话裁决**:**反推 DC/泊松网格在「聚合」层(1X2,以及次一级的 O/U 总分)可信;在「单个比分格」层不可信 —— 同行评议一致:模型和博彩**都**在精确比分上无效(模型有「反向冷门偏差」、尾巴太薄),而 1X2 两者都有效。竞彩比分单格 EV 是最不可信的一类;总进球次之;**别拿单格当真,聚合/「其他」桶才靠谱。**

---

## 0. 证据强度阶梯

| 强度 | 来源 | 代表 |
|---|---|---|
| **A · 同行评议** | 期刊原文 | Dixon-Coles 1997、Karlis-Ntzoufras 2003 (JRSS-D)、Koopman-Lit 2015 (JRSS-A)、Boshnakov-Kharrat-McHale 2017 (IJF)、Reade-Singleton 2020、Cain-Law-Peel 2000、Marra 2021、Wheatcroft 2019、Foulley 2021 |
| **B · 实务工具自报** | 反推计算器 | ImpliedScore(19,381 场自报校准)、market-calibrated AFT |
| **C · 实务博客** | DC 实现教程 | penaltyblog / dashee87 / datafc 等(只用来确认公式) |

---

## 1. DC τ 修正只动 4 个格子 —— 而且现在已经不够

**[A,多源一致]** Dixon-Coles 的 τ/ρ 修正**只改 4 个低分格**:`(0-0)=1−λμρ`、`(0-1)=1+λρ`、`(1-0)=1+μρ`、`(1-1)=1−ρ`;**其它所有格子 = 独立泊松外积的精确乘积**(ρ=0 时 DC 网格完全塌回泊松)。

**关键升级证据(Marra 2021,[A],9,130 场五大联赛):** DC 的「除这 4 格外条件独立」假设**已被实证拒绝**(bootstrap p<0.001):很多格子显著偏离独立,尤其**高分尾部被独立泊松低估**(4-4 比率 52.6、3-3 99.1)。作者直接下结论:「现代足球进球依赖**不能简化成对 0-0/1-0/0-1/1-1 的调整**」。

→ **DC 把整张网格(除 4 格)钉死在独立假设上,而独立假设在尾部和很多格子上是错的。**

---

## 2. 「聚合校准好」可以和「单格全错」同时成立 —— 有理论证明

**[A] Karlis-Ntzoufras Remark 2(决定性):** 比赛结果分布 `Z = X − Y`(Skellam)**完全不依赖相关参数**。所以相关性可以**随便重新分配单个比分格 + 改总平局概率,而 1X2 边际的函数形式不变**。

> 这就是「单格 vs 聚合」缝的**数学证明**:你的网格 1X2 校准可以完美,而 2-1、1-1、0-0 这些格子在被悄悄重排。**1X2 对了 ≠ 格子对了。**

实证佐证 **[A]**:Karlis-Ntzoufras 在 CL 2000/01,行列**边际总和**对得很好(客队总分 61 观测 vs 63.1 拟合),但**单格**错得离谱(0-0:10 vs 17.3;3-2:8 vs 4.1)。

---

## 3. 从 1X2+O/U 反推:构造对,但格子欠定;且 DC 对总进球**啥也没干**

- **[A/B] 1X2 单独反推 (λ_home,λ_away) 是欠定的** —— 多组 λ 给同样的 1X2;**必须加 O/U(总分)约束才能定唯一解**。→ **我们用 1X2+O/U 反推是对的构造**(market-calibrated AFT + ImpliedScore 都这么做)。但 **「两个自由参数没法精确匹配所有输入」**(ImpliedScore 自述)—— 聚合约束之外的单格是欠定的。
- **[A] Marra 的「不可否认的局限」:DC 的 ρ 只重排 4 个低分格,而这 4 格全在 Under 2.5 区内 → DC 算出的 Under/Over 2.5 概率与独立假设(ρ=0)完全相同,不管 ρ̂ 是多少。** 即:**对总进球(O/U 2.5 这条线),DC 修正等于没做** —— 我们的总进球 P = 纯独立泊松对角线和。
- **[B] ImpliedScore 自报**(19,381 场五大联赛 2015–2026):反推网格校准偏差 EPL 最好 2.7pp、西甲重favorite最大 6.0pp、平均 <2pp;且**「简单策略在 19,381 场上无可靠正回报」**。
- **[B] market-calibrated AFT:「市场校准是预测准确度的主导因素」** —— 结构不同的进球模型只要校准到同一组赔率,表现相当。**支持我们「钉到 Pinnacle 锐利赔率」而非自己拟合 ratings 的路线。**

---

## 4. 泊松边际本身就是错的形状(分散度 + 负相关)

**[A] Boshnakov-Kharrat-McHale (IJF 2017,10 季 EPL):**
- 卡方拟合优度**拒绝泊松**做边际:主队 p=0.002、客队 p=0.0002;Weibull-count 不被拒(p=0.10/0.16)。
- **主队进球欠分散(c>1)、客队进球过分散(c<1)** —— 泊松强制方差=均值,只能等分散 → **每队的计数分布形状被系统性扭曲,单格概率随之错**。
- **依赖是负的**(Frank-copula κ=−0.456、Kendall's τ=−0.05);而**双变量泊松/对角膨胀只能表达正依赖** → DC/BP 那套可能修在**错误方向**。
- 他们的 copula-Weibull 在 **1X2(21.2%)和 O/U 2.5(15.5%)回报都单调高于独立泊松** → **形状错配在总分市场是经济上实质的,不是统计洁癖。**

---

## 5. 市场效率:精确比分**无效 + 冷门偏差 + ~12% 抽水**;1X2 有效

**[A] Reade-Singleton 2020(EPL 比分市场,决定性):**
- 「两个来源的预测对**精确比分**普遍**无效**,对**比赛结果(1X2)有效**;效率检验在比分上拒绝原假设,在结果上不拒绝」→ **强证据:信网格的聚合/结果和,别信单格。**
- 模型有**「反向冷门偏差」**:Poisson 假设**尾巴太薄,系统性低估高分/冷门比分**。
- 博彩**比分赔率有标准冷门偏差**(MZ 斜率 1.16>1),**抽水 ~12%**(远高于 1X2)。过贵冷门比分、过便宜 1-1。
- 即便模型预测在统计上**涵盖(encompass)博彩**(t=8.77),**简单下注无稳定正回报**:always-1-1 = **−21.9%**、always-1-0 = **−12.6%**(vs always-home +9.8%)。**最可能的单格都不赚。**

**[A] Cain-Law-Peel 2000(UK):** 比分市场有冷门偏差;泊松/负二项网格比博彩比分赔率更贴合实际 —— 老数据里有过某些 +EV 规则,但那是 25 年前的英国市场。

---

## 6. DC 到底帮没帮?out-of-sample 其实很边际

- **[A] Wheatcroft/JQAS 2019:** DC 按 RPS 在部分联赛**优于**独立泊松(独立泊松最差)—— 但只是 RPS、只在 1X2 序数层。
- **[A] Koopman-Lit:** 依赖参数 γ「对样本外预测准确度**影响不大**」—— 拒绝 γ=0 是 in-sample 显著,out-of-sample 边际(因为它只挪平局质量)。
- **「Application of Poisson and DC」(实务):** DC 反而让 1X2 准确度**更差**;独立泊松裸下注 +3.30% 而 DC 跑不赢 always-home。
- → **τ 修正在聚合层 out-of-sample 收益薄;它主要动平局对角线,而平局恰是最难的一类。**

---

## 7. 评估指标:用 log-loss,别迷信 RPS

**[A] Wheatcroft「反对 RPS」:** ignorance/log-loss 是**唯一既 proper 又 local** 的打分规则,只看「实际发生那个结果」的概率。评估反推网格 → **打实际比分那一格的概率**,别靠 RPS 这种 distance-aware 的(它对识别更优系统反而更弱)。

---

## 8. 对 Nutmeg 的裁决(直接喂 §7 比分/总进球)

1. **比分单格 EV:不可信,别据此下注。** 同行评议共识 = 精确比分网格单格 miscalibrated(反向冷门偏差、尾太薄)+ 博彩比分 ~12% 抽水 + 冷门偏差,且**没有任何基准模型在比分上做出稳定 +EV**。我们的反推 DC 网格继承这一切。→ 秋天测比分,**预期抽水墙比 1X2(−11%)更厚**;单格 EV 是最不该信的。
2. **「胜/平/负其他」桶 > 具体比分。** 这三个是**聚合**,比单格可信。捕获已按此设计(`jingcai_exotic` 的 3 个其他桶)—— **EV 分析时优先看桶,谨慎看具体比分。**
3. **总进球:DC 对它等于没做**(Marra)—— 我们的总进球 P = 独立泊松对角线和,继承客队进球**过分散**的形状错配。→ **总进球 EV 当近似看**;真要信总进球格子,principled 升级是 Weibull-count / 负二项边际(但那要从结果拟合,不走我们的反推路线)。
4. **反推构造本身是对的**(1X2+O/U 才能定 λ;「市场校准主导」支持钉 Pinnacle)。**网格在它被钉住的聚合层可信,越往单格钻越不可信。**
5. **不必过度工程。** 对「从 Pinnacle 反推的市场隐含网格」,没有便宜的单格修法(对角膨胀/copula 都要从结果拟合,不兼容反推)。**正解是「不信单格」,不是堆模型。** 与 DNA 一致:measure-first、不臆造 +EV。

> **净结论**:比分/总进球**捕获**仍值得(我们捕的是 SP,不是下注);但秋天 EV 跑起来时,**权重排序 = 聚合/桶 ≫ 总进球 ≫ 具体比分**,且预期比分是最厚的 vig 墙。这把 §7 那条「单格校准没验过」的缺口**填实了:验过了,结论是别信单格。**

---

## 参考文献

### A · 同行评议
- Dixon & Coles (1997). *Modelling Association Football Scores and Inefficiencies in the Football Betting Market.* JRSS-C 46(2) — https://www.academia.edu/61276617/
- Karlis & Ntzoufras (2003). *Analysis of sports data by using bivariate Poisson models.* JRSS-D (The Statistician) 52(3):381–393 — http://www2.stat-athens.aueb.gr/~jbn/papers2/08_Karlis_Ntzoufras_2003_RSSD.pdf
- Koopman & Lit (2015). *A dynamic bivariate Poisson model… EPL.* JRSS-A 178(1):167–186 — https://papers.tinbergen.nl/12099.pdf
- Boshnakov, Kharrat & McHale (2017). *A bivariate Weibull count model for forecasting association football scores.* Int. J. of Forecasting 33(2):458–466 — https://pure.manchester.ac.uk/ws/files/49399144/ijfpaper.pdf
- Reade & Singleton (2020). *Betting markets for EPL results and scorelines: evaluating a forecasting model.* Economic Issues 25(1):87–106 — https://centaur.reading.ac.uk/89738/1/reade_singleton_scorelines.pdf
- Cain, Law & Peel (2000). *The Favourite-Longshot Bias and Market Efficiency in UK Football Betting.* Scottish J. of Political Economy 47(1):25–36 — https://ideas.repec.org/a/bla/scotjp/v47y2000i1p25-36.html
- Marra (2021). *On the dependence in football match outcomes: traditional model assumptions and an alternative proposal.* arXiv:2103.07272 — https://arxiv.org/abs/2103.07272
- Wheatcroft (2019). *Evaluating probabilistic forecasts of football matches: the case against the Ranked Probability Score.* arXiv:1908.08980 — https://arxiv.org/pdf/1908.08980
- Foulley (2021). *More on verification of probability forecasts for football outcomes.* arXiv:2106.14345 — https://arxiv.org/abs/2106.14345
- *An exploration of predictive football modelling.* J. Quantitative Analysis in Sports (2019) — https://www.degruyterbrill.com/document/doi/10.1515/jqas-2019-0075/html
- *Bayesian state-space models for the modelling and prediction of EPL football.* JRSS-C 74(3):717 (2025) — https://academic.oup.com/jrsssc/article/74/3/717/7929974
- *Extending the Dixon-Coles model: an application to women's football data.* arXiv:2307.02139 — https://arxiv.org/pdf/2307.02139

### B · 实务工具(自报数据)
- ImpliedScore — *Odds to Scoreline Probabilities* calculator(反推 1X2+O/U → 比分矩阵;自报 19,381 场校准)— https://impliedscore.com/
- *A market-calibrated accelerated failure time model for in-play football forecasting.* arXiv:2605.16066 — https://arxiv.org/html/2605.16066

### C · 实务博客(仅确认公式)
- penaltyblog / dashee87 / datafc / Tam Nguyen — DC Python 实现(τ 公式、ρ≈−0.13、时间衰减 ξ)

*相关:`docs/parlay_soft_water_research.md` §7 玩法维度、[[sharp_money_market_microstructure]]、[[freeze_gap_test_card]]、记忆 `handicap-reconstruction-calibration-tested`(让球=粗聚合已验校准,与本文「单格不可信」互补)。*
