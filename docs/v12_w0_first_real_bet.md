# V12 W0 — 第一笔真实数据落库

_2026-05-26 (下注日) · 2026-05-27 (结算 + 录入日)_

## 一句话总结

**V5 ship 时设的最终 KPI — "真实下注 ROI 验证" — 现在有第一个数据点。**

---

## 实战记录

### 比赛 (2026-05-26)

| 联赛 | 主队 | 客队 | 实际比分 | 实际 1X2 | 实际 HC -1 |
|---|---|---|:---:|:---:|:---:|
| 法甲 (FRA_LIGUE_1) | Saint-Étienne | Nice | 0-0 | 平 | 让负 |
| 德乙 (GER_2_BUNDESLIGA) | SpVgg Greuther Fürth | Rot-Weiß Essen | 2-0 | 主胜 | 让胜 |

### 下注

```
策略:  user_directional_combo
       (选 model 信号方向最强的 2 个 outcome 组合, 接受 -EV)

Leg 1: 法甲 让负 (-1) @ 1.51   model_P = 64.18%  (model 最强信号)
Leg 2: 德乙 让胜 (-1) @ 3.00   model_P = 31.65%  (model 次强信号)

Combo odds:    1.51 × 3.00 = 4.53
Combo P (indep): 0.6418 × 0.3165 = 20.32%
Combo EV:        20.32% × 4.53 − 1 = −7.97%

Stake:  500 倍 × ¥2 = ¥1000
Result: ✅ HIT
Payout: ¥4530  (¥1000 × 4.53)
P/L:    +¥3530
```

---

## Model 校准对照

Model 在 4 个 outcome 上的预测 vs 实际:

| 比赛 | 市场 | 实际 | Model 给的 P | 命中? |
|---|---|---|---:|---|
| 法甲 | 1X2 平 | 0-0 = 平 | 28.84% (model 最低值) | ⚠️ Model 偏低估了平局 |
| 法甲 | HC -1 让负 | 0-0 → diff=-1 → 让负 | **64.18%** (model 最高值) | ✅ Model 对了 |
| 德乙 | 1X2 主胜 | 2-0 = 主胜 | **53.78%** (model 最高值) | ✅ Model 对了 |
| 德乙 | HC -1 让胜 | 2-0 → diff=+1 → 让胜 | **31.65%** (model 第二高) | ✅ Model 对了 |

4 个市场 model 方向: **3 对 1 漏** (法甲 1X2 平局漏判)。

---

## Model 视角: 这单值得下吗?

**Model 单关分析** (每条单独计算 EV):

| 选项 | 模型 P | 市场 P | Δ | EV/unit @ 竞彩 SP |
|---|---:|---:|---:|---:|
| 法甲 让负 | 64.18% | 58.63% | +5.55pp | −3.08% |
| 德乙 让胜 | 31.65% | 29.52% | +2.14pp | −5.04% |

两条都没过 +5% EV 门槛 → Model 单关引擎说 **no-bet**。

**Combo 期望** (100 笔下注 × 同样组合):

```
20.3 笔命中    回收 ¥9,060 × 20.3 = ¥183,918 / 100 = ¥1,839 per bet
79.7 笔不中    损失 ¥1,000 per bet
                                                     
Expected ROI = −7.97%      ←   long-term 每¥1000 期望亏 ¥80
```

**今天单次结果: +¥3530 (ROI +353%)** — 是 1/4.92 概率事件的命中, 不是 model 错的证据。

---

## 用户的 Directional Combo 策略 vs Model 严格 +EV gate

| 维度 | Model 严格策略 | 用户 Directional Combo |
|---|---|---|
| 触发条件 | 单 outcome EV ≥ +5% | 选 model 信号最强的 K 个 outcome 串联 |
| 长期期望 | 应有 +ROI (理论上) | ≤ 0 (vig 通常 > model edge) |
| 今天下了几单 | 0 | 1 |
| 适用前提 | model 真有 ≥ +5% EV signal | 接受 -EV 换"参与感"/方向赌 |
| Mental model | 严格的概率投资 | 介于赌博与策略之间的中间地带 |

**4 周后真正的对照**: 不是 model_recommended (今天 0 笔) vs user_directional_combo, 而是看 user_directional_combo 一条 arm 的累计 ROI:
- 跑了 30+ 笔后, ROI 是 -8% (符合 model 期望) 还是 0 / 正 / 更负?
- 如果 -8% → 接受现实, vig 比 model edge 大, 策略不可持续
- 如果 0 / 正 → model 的概率估计可能保守, 有 systematic edge
- 如果 < -10% → model 的"信号方向"也不可靠

---

## Bug 副产品: stake_units 语义陷阱

录入这笔时第一次把 `stake_units=500` (理解为"500 倍"), `kelly_stake=1000`. 结果 settlement 算:
- `unit_money = 1000/500 = ¥2`
- `payout = ¥2 × 4.53 = ¥9.06` ❌ (应该是 ¥4530)

**根因**: V4 schema 里 `stake_units = atomic combinations`, 不是 "倍数". 单式 N-leg 都是 `stake_units=1`. 倍数体现在 `kelly_stake`.

**已修**:
1. UPDATE 这笔 `stake_units=500 → 1`, re-run settle → 正确得到 ¥3530
2. recorder.py 顶部加 ⚠️ CRITICAL 段落 + 示例表 (commit `[next]`)
3. 同样的陷阱 2026-05-26 在 record_wc_handicap_session 也修过 (`fc21ed1`)

---

## V12 W3 (半自动 SP UX) 设计需要加的东西

**之前 doc 只设计了 "+EV gate 通过 → 推荐 / 不通过 → no-bet"** 两态.

**根据今天的实战, 第三态需要显式化**: **Directional signal (no +EV)**

```
Dashboard 今日推荐 tab 卡片应该长这样:

①  法甲: Saint-Étienne vs Nice
   Model: λ_h=1.31 λ_a=1.30
   
   [用户输入竞彩 SP 完毕后]
   
   ✓ +EV 推荐: 无 (所有 6 outcome EV < 5%)
   
   ⚠️ Directional signal (model 最看好的 3 个, 但都 -EV):
      1. 让负     (P=64% EV=-3.1%)  ← model 最强方向信号
      2. 客胜     (P=35% EV=-2.8%)
      3. 让平     (P=28% EV=-7.4%)
   
   [✗ 严格 +EV gate: 不下注]
   [⚠️ Directional combo: 接受 -EV, 选 #1+#2 串关]   ← 知情用户的选项
```

这样:
- 严格用户继续看 +EV gate, no-bet 时不下
- 灵活用户可以选 directional combo, 系统**记录到 directional_combo arm**
- 4 周后 ab-report 两条 arm 都有数据

---

## 仓库状态

```
Session #4 in data/v4_observation.db (gitignored, 本地only):
  - model_type = user_directional_combo
  - n_fixtures = 2, n_recommendations = 1
  - 1 parlay_recommendation: k_legs=2, stake_units=1, kelly_stake=1000
  - 1 settlement: hit=1, stake=1000, payout=4530, profit_loss=+3530
```

明天 14:00 cron 跑出来 (如果 14 联赛有比赛), `model_type=catboost` 那条 arm 也开始填。

**正式开局: 2026-05-26**.
