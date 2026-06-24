# CLV 统计方法论:N≥15/38 的闸门站得住吗?

**状态:📚 参考文献 + 决策(裁决:闸门太松,要改)→ ✅ 已实现** · 记于 2026-06-24 · 回答秋天「选中计数器」闸门的统计依据

> **✅ 已落地(2026-06-24)**:§4 改法已实现为 `nutmeg.v4.model.clv_gate`(cluster-robust t 检验 + BHY-FDR + 预警/确认两层),接进 `nutmeg-clv-ledger`,14 个单测含多重检验铁证(同一联赛单独跑→确认;混入 11 个 null 联赛→降级仅预警)。额外硬化:**CLV 按比赛日聚类**(防同轮相关把 t 吹大)+ 单边检验 + meat 相对零守卫。

> **出处说明**:多 agent 深度研究跑完搜索 + 抓取 + **对抗式核查**(11 条声明 3-0 confirmed),仅最后合并因**会话 token 上限**(每次 deep-research ~100 agent / ~2M token)中断 —— 由人工从已核查声明综合。凡标 **[3-0]** 为对抗核查全票通过。
>
> **一句话裁决**:**`N≥15 / N≥38` 的选中计数器闸门在统计上远远不够。** 同行评议实测:一个**真实 +EV** 策略在 **672 注**时只有 1.34 SD、**p=0.089(不显著)**[3-0]。15–38 注离确认边差着两个数量级。而且秋天要「按 13 个联赛切 CLV 找软的」= **多重检验**,p=0.05 的单测门槛会系统性造假阳,得抬到 **t≈2.8–3.0(p≈0.5%)** 并做 FDR 校正。**改法在 §4。**

---

## 1. 显著性由样本量决定(Kaunitz,bootstrap 零分布)[3-0]
| 注数 | 距随机均值 | p |
|---|---|---|
| 56,435(收盘) | **10.82 SD** | <十亿分之一 |
| 6,994(临场) | 4.80 SD | <百万分之一 |
| **672(真金+纸面)** | **1.34 SD** | **0.089 — 不显著** |

→ **边是真的,672 注却过不了 p=0.05。** 这是对 N≥15/38 闸门最直接的证伪。

## 2. CLV 比 ROI 省注,但仍不是 15–38
- **Buchdahl**:CLV 确认技能**远比 ROI 省注**;但**没有正 CLV ≠ 没有技能**(源头问题,§3)。对 ROI,他**不到 1,000 注不认真看技能**,且荐 **p<0.001** 门槛。
- **「~50 注」的出处**(bet2invest 博客):一个**已知 2% yield** 的人 ~50 注达高置信(1/10,000)—— 但前提是**已知 yield + 低方差的每注 CLV**,不是数选中腿。
- **DataGolf**:5,000 注以下随机性显著;10,000 注时纯运气仍能造 2–3% ROI 偏差;**区分两个模型要数千注**。→ 「几十注定边」是民间传说。

## 3. CLV 不是万能(源头问题,Buchdahl)
信息**领先**市场的人(originator)**初期不显 CLV**(他的信息还没进线)。所以 CLV 是**强但非充分**的技能证据:正 CLV ⇒ 大概率有边;**零/负 CLV ⇏ 没边**。

## 4. 最大的隐藏坑:多重检验(秋天「按联赛切」直接踩)
**[3-0 ×多条]** 当你**同时筛很多**联赛/策略:
- **单测 t=2.0(p=0.05)不够。** Harvey-Liu-Zhu:挑出来的因子要 **t>3.0** 才算真;校正门槛 Bonferroni t>3.78、Holm t>3.64、**BHY(FDR)t>3.39**,综合最低 **t≈2.8(p≈0.5%)**。
- **Deflated Sharpe(Bailey-López de Prado)**:零边时**期望最大 Sharpe 也 >0**,且随试验数 N 增长 —— **「13 个联赛里最软的那个」在「全无边」假设下本就该出现**,不是边。用 EVT 收缩门槛。
- **方法选择**:金融场景荐 **FDR(BHY)**(控假阳**比例**)而非 Bonferroni(控**绝对个数**,太严)。

→ **秋天「13 个受训联赛各切 CLV,看哪个软」= 13 重检验。** 直接拿 p=0.05 挑「正 CLV 联赛」≈ 在挑多重检验的赢家。

---

## 5. 对 Nutmeg 闸门的裁决 + 改法

**现状闸门**(`parlay_soft_water_research` §7/§8):选中计数器 `N→15`(+5% 边)/ `38`(+3%),选中腿 CLV 真为正 → 动手。

**问题**:① 15/38 远不足以统计确认(§1);② 数「选中腿计数」不等于检验「平均 CLV 的 t 值」;③ 跨 13 联赛筛 = 多重检验,p=0.05 造假阳(§4)。

**改法(秋天上线前先改闸门,便宜):**
1. **闸门改成检验「每注 CLV 的 t 统计量」**,不是数选中腿数:`t = mean(CLV) / (sd(CLV)/√N)`。
2. **门槛抬到 ≈ p<0.005(t≈2.8),不是 p=0.05** —— 因为同时筛 13 联赛;再用 **BHY/FDR** 跨联赛校正,挑出的「软联赛」才不是噪声。
3. **N 要到几百注、不是几十** —— 真边在 672 注都可能 p=0.089;15/38 只能当**「值得细看」的预警**,不是**「确认有边」**。把这两层分开:预警(N≥15)→ 观察;确认(t>2.8 且 FDR 过关且 N 够)→ 才动手下注。
4. **ROI 别单独信**(要数千注);**CLV 当主指标**(省注),但配 §3 的 caveat(源头不显 CLV)。

> **净结论**:闸门方向对(CLV 是记分牌、要正),但**阈值太松 + 没做多重检验校正**。秋天前把「计数器」升级成「**t 检验 + FDR 跨联赛校正 + 预警/确认两层**」—— 一个纯逻辑的小改,直接防住「把多重检验的运气赢家当软水」。与 DNA(不臆造边)一致,且现在有 Harvey-Liu-Zhu / deflated-Sharpe 的同行评议背书。

---

## 参考文献
- Kaunitz et al. (2017, PLOS ONE). *Beating the bookies…* (bootstrap 零分布, 672 注 p=0.089) — https://arxiv.org/abs/1710.02824
- Harvey, Liu & Zhu (2016, RFS). *…and the Cross-Section of Expected Returns* (多重检验, t>3.0/2.8) — https://www.nber.org/system/files/working_papers/w20592/w20592.pdf
- Harvey & Liu. *Backtesting* (单测 vs BHY 收益门槛, 4.4% vs 7.4%/yr) — https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF
- Bailey & López de Prado. *The Deflated Sharpe Ratio* (期望最大 Sharpe under null, EVT) — https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
- Sullivan, Timmermann & White. *Data-Snooping…* (Reality Check bootstrap) — https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf
- Romano & Wolf (2005). *Stepwise Multiple Testing…* (依赖结构 bootstrap) — http://www-stat.wharton.upenn.edu/~steele/Courses/956/Resource/MultipleComparision/RomanoWolf05.pdf
- Buchdahl interview (CLV 比 ROI 省注; ROI 需 1,000 注; p<0.001) — https://sharpbetting.co.uk/articles/interview-with-joseph-buchdahl
- DataGolf — *How sharp are bookmakers* (数千注才能区分模型) — https://datagolf.com/how-sharp-are-bookmakers

*相关:`docs/parlay_soft_water_research.md` §7/§8(闸门定义)、[[sharp_money_market_microstructure]](CLV=技能)、记忆 `soft-water-leg-finding-measured`。*
