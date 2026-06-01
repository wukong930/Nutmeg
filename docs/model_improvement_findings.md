# 模型改进 — "先测后定"决策索引

> 入口页。下次有人问"模型是不是该做 X / 加某特征 / 改服务层",**先看这里**——
> 多半已经用数据测过、并诚实地做了决定。源起:一篇模型评估文章的逐条走查(2026-06-01)。

## 纪律

不凭信仰加特征或改架构。每条候选先问:**有没有 Pinnacle / 竞彩还没吸收、我们能利用的残余信号?**
能廉价测的就测;测完让数据说话。我们杀过的东西(ensemble、per-league 校准、market_dynamics)都是这么死的。

## 已下结论的发现

| 发现 | 问的问题 | 结论 | 档案 |
|---|---|---|---|
| **β 独立信号** | 模型相对 Pinnacle 有没有独立信号? | **无**(1X2 收盘:加权模型单调变差,最优 β≤0)→ **不改服务层** | [`beta_independent_signal_finding.md`](beta_independent_signal_finding.md) |
| **战意 / stakes** | Pinnacle 有没有 mis-price 死亡之组? | 方向对但 **≤1.5σ**(n=210,欠采样 17×)+ **竞彩不挂** → **搁置** | [`motivation_stakes_finding.md`](motivation_stakes_finding.md) |
| **球员级 xG/xA** | 球员级比队级多挤出 edge 吗? | **数据门控**(无球员数据);回测上限低(Pinnacle 收盘已 price 阵容);真 edge 在 soft-book 滞后的**实时窗口** → **搁置** | [`player_xg_finding.md`](player_xg_finding.md) |

## 文章六条优先级 × 我们的状态

| # | 文章建议 | 我们 |
|---|---|---|
| ① | 证明模型有独立信号(β 测试) | ✅ **测了** → 无(见上)。已做成诊断 `nutmeg-beta-test` 长期追踪 |
| ② | 分市场,别只盯胜平负 | 🟡 受**竞彩菜单**限,已做 1X2 + 让球;角球/牌/BTTS 竞彩没有 |
| ③ | 用让球+大小球反推 λ → 进球分布 | ✅ **早已做且超前**(Dixon-Coles `fit_lambdas` → 网格) |
| ④ | 校准,别堆模型 | ✅ **已成熟**(温度/isotonic/ECE 审计;ECE 0.0120 优于 Pinnacle 0.0123;分联赛校准试过失败) |
| ⑤ | 看 edge 来自哪里(分桶) | 🟡 有工具(bucket_decomp/ece-audit),但**没实盘数据**做真归因 |
| ⑥ | 加市场没吸收的信息 | 战意 ❌搁置 · 球员xG ❌数据门控 · 裁判 🔴竞彩无盘口 · 赔率路径 🔴market_dynamics 已 ablation 失败 |

## 可重复诊断

```bash
python -m nutmeg.v4.cli.beta_test --output docs/beta_test_latest.md
```
每赛季 / 每次重训后复跑。报告里 **"任何 β>0 胜过 Pinnacle?"** 现在 = NO;哪天 Layer B 重训出真本事会翻成 YES。

## 元结论

这篇文章对**刚起步**的模型是金矿;对我们这个**已 93% Pinnacle、校准做透、λ 反推到位**的系统,低垂果实大多摘过了。今天这一串测下来,最大收获不是新 edge,而是**用数据把"再堆模型/特征"这条路诚实地关上了**——⑥里最值钱的两条(战意、球员xG)测完都搁置,剩下两条预判也弱。

**注意力应推回真正的瓶颈:攒实盘竞彩 ROI 数据。** 在有几百场实盘之前,模型侧没有数据支撑的提升空间了。
