# V13 Roadmap — 候选总索引 + Decision Tree

_整合时间: 2026-05-27 · V12 W0 (第一笔真实下注) 之后_

---

## 0. 一句话定位

**V13 路线图已就位, 但执行权交给 4 周真实下注 ROI verdict (2026-06-23 +/-)**。

V12 W0 起算 4 周, `nutmeg-ab-report` 输出后才决定 V13 走哪条线 / 是否启动。期间只做 P0 级别的"防御性"小补丁 (今天 ship 的 playoff banner 就是)。

---

## 1. V13 候选四大主线

| 主线 | 详细 doc | 状态 | 工程量 |
|---|---|---|---|
| **A. 数据质量升级** (Pinnacle/竞彩 多源对齐) | `V13_DATA_QUALITY_UPGRADE.md` | Draft | TBD |
| **B. 联赛覆盖扩展** (欧洲 only, 不做中超/南美) | `V13_EUROPEAN_EXPANSION.md` | Draft (Plan A/B/C) | 2-9 天 |
| **C. Playoff 语境感知** | `V13_PLAYOFF_AWARENESS.md` | **P0 已 ship** (2026-05-27) | P1: 2-3 天; P2: 3-5 天 |
| **D. 比赛语境特征 (非 playoff)** | `V13_CONTEXTUAL_FEATURES.md` | Draft, 5 features | ~11 天 (全包) |

**E (隐式)**: 真实下注 ROI 验证 — 不在 V13 工作量内, 是 V13 启动的**前提**。

---

## 2. Decision Tree — 哪条线在什么 ROI 下启动

```
                       4 周 ROI verdict (2026-06-23)
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
   ROI > +5%                 0 ≤ ROI ≤ +5%               ROI < 0
   "Model work"            "Edge < vig"                "Model 不 work"
        │                         │                         │
        ▼                         ▼                         ▼
  ┌─────────────┐          ┌─────────────┐         ┌─────────────┐
  │ 启动 V13    │          │ 暂停扩张     │         │ 回到原点     │
  │ 全包        │          │ 只补 P0 类   │         │ 不做 V13     │
  │             │          │              │         │              │
  │ A → B → C   │          │ - 只做 C/D   │         │ - 跑 V11     │
  │ → D 顺序    │          │   P0 banner  │         │   Layer B    │
  │             │          │ - 跑 ECE     │         │   auto-      │
  │ ~6-8 周     │          │   audit      │         │   retrain    │
  │             │          │ - 等下个     │         │ - 暂停 SP    │
  │             │          │   4 周       │         │   推荐       │
  │             │          │ ~3 天        │         │ ~5 天        │
  └─────────────┘          └─────────────┘         └─────────────┘
```

---

## 3. 启动顺序逻辑 (假设 V13 启动)

按"前置依赖 + 风险递增"排:

### Week 1-2: V13 W1-W2 — A (数据质量)
- 前置: 没有
- 风险: 低
- ROI: 修底层, 后面 B/C/D 全部受益
- 输出: 多源 SP 一致性诊断 + 异常报警 cron

### Week 3-4: V13 W3-W4 — B Plan A (Tier 1 联赛)
- 前置: A 稳定 7 天 (跑 cron 看 0 错误)
- 风险: 低 (Tier 1 联赛 = 苏超/希超/土超/苏甲, 数据同质)
- 输出: 14 → 18 联赛, 守门测试通过

### Week 5-6: V13 W5-W6 — C P1 (playoff features)
- 前置: B 跑 4 天 ROI 不掉
- 风险: 中 (V8 W4 cup 教训: feature 加进训练不一定 win)
- Ship gate: walk-forward Δ ≥ -0.001
- Backup: 失败 → 保留 P0 banner

### Week 7-8: V13 W7-W8 — D P1 (其他 contextual features)
- 前置: C verdict (无论 ship 与否)
- 风险: 中
- Ship gate: 同 C
- Backup: 失败 → P0 banner (closed_doors / dead_rubber 各加 banner)

### Week 9+ (V13 W9-W12 / V14 起手): C P2 + D P2 (calibration)
- 前置: P1 至少一个 ship
- 风险: 高 (V9 W6 calibration 在临界)

---

## 4. Hard NO ship 条件 (跨所有候选)

任何一条触发 → **整个 V13 暂停, 回去解决前置问题**:

1. 总体 multi-season log-loss 变差 ≥ +0.001
2. ECE 比当前 (0.0120) 退化 ≥ +0.003
3. Pinnacle gap 扩大 ≥ +0.0005
4. CI Weekly Bench cron 连续 2 周失败
5. 真实下注 ROI 在 V13 ship 后 4 周内**降低 ≥ 5pp**

V8 W4 cup-aware ablation NEGATIVE 是先例, V13 任何 sub-feature 都得跨这道线。

---

## 5. 永远 deferred (不做)

| 项 | 为什么不做 |
|---|---|
| 中超 / 中甲 | 用户明确拒绝 (V13_EUROPEAN_EXPANSION §0) |
| 南美联赛 (巴甲, 阿甲, 等) | 同上 |
| UEFA Cup competitions 训练数据 | V8 W4 verdict NEGATIVE (cross-league seed 不修) |
| 单关 + 复式 web 下注 record_session | post-V8 P1#5 已 ship |
| 教练 H2H 历史 / 球迷氛围分 / 转会窗口分心 | `V13_CONTEXTUAL_FEATURES.md` §1 标记 "样本小, 难证伪" |
| 全自动竞彩 SP 爬虫 | 合规风险 + V12 W3 已选半自动方案 |

---

## 6. 4 周 ROI verdict — 怎么读

`nutmeg-ab-report --weeks 4` 在 2026-06-23 (假设无 break) 跑后看:

| 字段 | 含义 |
|---|---|
| `n_settled_recommendations` | 4 周内已结算推荐数 (需要 ≥ 30 才 statistical meaningful) |
| `roi_pp` | (total_payout - total_stake) / total_stake × 100 |
| `roi_pp_by_arm["model_recommended"]` | 严格 +EV gate 通过的 arm |
| `roi_pp_by_arm["user_directional_combo"]` | V12 W0 ship 的新 arm |
| `live_vs_backtest_gap` | 实战 ROI vs walk-forward 回测 ROI 差 |

**3 种 verdict 的具体阈值**:

```
ROI > +5%      AND  gap ≤ ±4pp      → 启动 V13 全包
ROI 0 ~ +5%    OR   gap > ±4pp      → 暂停扩张, 只做 P0
ROI < 0        OR   gap > ±8pp      → 回原点, 不做 V13
```

**Edge case**: n_settled < 30 → 不能 verdict, 延长观察 4 周。

---

## 7. P0 类工作 (无论 verdict 都做, 防御性)

这些是"模型坏不了, 用户体验改善"的小补丁, 4 周观察期可以做:

| 项 | 工程量 | 状态 |
|---|---|---|
| Playoff banner (P0) | ✅ 2026-05-27 ship | done |
| Closed-doors banner (P0) | ~1 天 | TODO |
| 人为 override 设计 (`data/overrides.yaml`) | ~1 天 | TODO |
| 半自动 SP UX (V12 W3) | 3-4 天 | TODO (cron 数据稳定后启动) |
| 单关/复式 web 下注 directional_combo arm | ~0.5 天 | TODO (跟 V12 W3 一起) |

---

## 8. 验证 — 怎么知道这份路线图是 sane 的

可证伪点 (按重要性):

| 测试 | 期望 |
|---|---|
| `nutmeg-ab-report --weeks 4` 6-23 跑 | 至少 ≥ 30 settled recs, 走 verdict tree |
| 4 份 V13 候选 doc 都在 docs/ | ✅ 已确认 |
| V12 W0 first-bet session 在 observation DB | ✅ Session #4 已 record |
| Playoff banner 在浏览器实际渲染 | 等 5-30 之后的法甲附加赛 fixture 触发 (cron 数据) |
| `tests/v4/test_playoff_context.py` 14/14 pass | ✅ 已确认 |

---

## TL;DR

| 项 | 值 |
|---|---|
| V13 候选总数 | 4 主线 (A/B/C/D) + 5 个 P0 类小补丁 |
| 总工程量 | ~6-8 周 (V13 全包) 或 ~3 天 (只 P0) 或 ~5 天 (放弃 V13) |
| **何时决定** | **2026-06-23 +/- 看 4 周 ROI verdict** |
| 永远 deferred | 中超 / 南美 / UCL 训练 / 全自动 SP 爬虫 |
| 路线图原则 | "先验证 model 真能赚钱, 再决定怎么扩" — 不学 V6-V8 那种 12-周 sprint 的盲目节奏 |
| 跟以前 version 的区别 | V5-V8 是**功能扩张驱动**; V13 起步是**真实 ROI 驱动**, **能不开新线就不开** |

---

## 相关文档

- `docs/V13_DATA_QUALITY_UPGRADE.md` — 主线 A 详细
- `docs/V13_EUROPEAN_EXPANSION.md` — 主线 B 详细
- `docs/V13_PLAYOFF_AWARENESS.md` — 主线 C 详细 (P0 已 ship)
- `docs/V13_CONTEXTUAL_FEATURES.md` — 主线 D 详细
- `docs/v12_w0_first_real_bet.md` — V12 W0 起算点
- `docs/v12_half_auto_sp_workflow.md` — V12 W3 候选 (跟 P0 类小补丁并行)
