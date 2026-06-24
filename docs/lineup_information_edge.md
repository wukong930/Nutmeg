# 阵容/伤停信息边:真实但温和,只在冻结缝里对我们有用

**状态:📚 参考文献 + 决策(裁决:别建大机器,归冻结缺口)** · 记于 2026-06-24

> **出处说明**:多 agent 深度研究跑完搜索 + 抓取 + **部分对抗核查**(会话 token 上限中断在合并前)。**关键:对抗核查把「市场吸收阵容信息有滞后 → 可利用窗口」这条强论点否决了(0-3 / 1-2 refuted)** —— 所以本文比直觉更**保守**。标 [confirmed]/[refuted]/[未核完] 区分核查状态。
>
> **一句话裁决**:阵容公布**是真实的市场移动事件**,但**单球员幅度温和**(顶级外场球员缺阵 ≈ 0.4–0.5 联赛积分/场),且**sharp 市场基本高效吸收**(「有可利用滞后」被对抗核查否决)。对我们唯一有用的口子**不是「市场慢」,而是「竞彩冻在阵容公布前」** —— 即冻结缺口。**别建复杂阵容机器;冻结缺口捕获已覆盖;预期温和、非大边。**

---

## 1. 阵容/伤停**是**真实信息事件 [confirmed]
- **Fischer & Schmal(Economic Inquiry 2025)**:精英球员缺阵公告**移动赔率**(117,174 odds / 32 books;COVID 强制缺阵的德甲/意甲准自然实验)。[confirmed 3-0] —— 球员可用性 = 离散、可定价的信息冲击。

## 2. 但「可利用滞后」被对抗核查**否决** ⚠️ [refuted]
- 「市场不立即重定价,先惯性后滞后反应 → 留可利用窗口」这条 —— **核查 0-3 / 1-2 否决**。即:**没有稳的证据说 sharp 市场吸收阵容信息够慢、能让你套利。**
- 佐证(未核完):进球这种离散冲击下,**Betfair 交易所快速且完全**调整,无残余错价 → sharp 市场对大新闻吸收充分。

## 3. 单球员幅度温和 [未核完,但多源一致]
- 每球员胜率影响 ≈ **eLPAR**(expected league points above replacement):**顶级(~99 评分)外场球员最多 ≈ 0.4–0.5 联赛积分/场,多数换人远小于此。** → **一个球员动盘有限**,除非真正关键位(顶级前锋/门将)。

## 4. 阵容信息**有模型价值**,但变现成边要去相关 [未核完]
- 含阵容的 Skellam/FIFA-rating 模型校准更好(Brier **0.58 vs 0.65** climatology);含首发 22 人的模型 match-result **F1 0.47 vs 0.39**(博彩赔率基线)→ **阵容信息带市场没完全反映的信号。**
- 但 **Hubáček**:模型准 ≠ 盈利,**盈利要和博彩去相关、不是堆准确率**;**Constantinou**:最优下注阈值**季季剧变、事前不可知** → 回测边不可靠。**→ 「阵容模型更准」离「打赢市场」还隔着去相关 + 阈值不稳两道坎。**

---

## 5. 对 Nutmeg 的裁决

1. **别建复杂「阵容反应」机器。** sharp 市场基本高效吸收(§2),单球员幅度温和(§3),变现要去相关(§4)—— 投入大、边不确定,是典型的坑。
2. **唯一对我们有用的口子 = 冻结缺口(已设计)。** 不是因为「市场慢」,而是因为**竞彩冻在阵容公布前**:深夜欧洲场竞彩 23:00 冻死,首发 02:00–04:00 才出,Pinnacle 把首发进收盘 → 竞彩冻在「无阵容旧价」上。**这正是 `freeze_gap_test_card` 已经在测的;阵容只是它背后的信息源之一。**
3. **幅度要诚实**:即便冻结缺口里有阵容信息,**也被 §3 的温和幅度封顶** —— 只有**真正关键球员**(顶级前锋/门将)在**冻结后**确认缺阵的深夜欧洲场,才值得注意。不是普遍大边。
4. **不新增捕获**:我们已有 V6 阵容**特征**进模型 + 冻结缺口捕获。**阵容这条不需要额外管道** —— 秋天冻结缺口测试若显示「深夜欧洲场缝最大」,阵容就是它的一部分解释,顺带验证,无需单列。

> **净结论**:阵容信息真实但温和,市场吸收充分(强论点被对抗核查否决),**对软水的价值只经由冻结缺口体现且被幅度封顶。** 结论 = **归入冻结缺口,别单独建机器**。与 DNA(measure-first、不为不确定的边提前建)一致。

---

## 参考文献
- Fischer & Schmal (2025, *Economic Inquiry*). *Pricing in response to new information: betting markets* (精英缺阵 → 赔率) — https://onlinelibrary.wiley.com/doi/10.1111/ecin.13258
- *Information and Efficiency: Goal Arrival in Soccer Betting* (Betfair 快速完全吸收) — https://www.researchgate.net/publication/228338838
- Lineup-aware Skellam / FIFA-ratings 模型(Brier 0.58) — https://arxiv.org/pdf/1807.07536
- 首发 22 人 match-result 模型(F1 0.47 vs 0.39) — https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0284318
- Hubáček, Šourek & Železný (2019). *…gradient boosted trees*(去相关才盈利) — http://ida.felk.cvut.cz/zelezny/pubs/ijf.2019.pdf
- Constantinou (2022). AH efficiency(阈值季季剧变) — https://arxiv.org/abs/2003.09384

*相关:[[freeze_gap_test_card]](阵容是它的信息源)、[[sharp_money_market_microstructure]] §3(阵容时钟)、`docs/parlay_soft_water_research.md`。*
