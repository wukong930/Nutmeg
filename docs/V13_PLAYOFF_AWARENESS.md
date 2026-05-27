# V13 候选: Playoff / Barrage 语境感知

_决策时间: 2026-05-27 · V12 W0 第一笔真实下注的副产品_

---

## 0. 触发事件

2026-05-26 用户下注的 2 场比赛事后才发现都是 **end-of-season high-stakes**:
- 法甲 Saint-Étienne vs Nice — **Ligue 1 barrage de relegation**
- 德乙 Greuther Fürth vs Rot-Weiß Essen — **Relegations-Playoff zur 2.Bundesliga**

用户问: **"model 计算有没有考虑这个因素?"** 诚实答案: **没有**。

| 维度 | 现状 |
|---|---|
| Elo / xG-lite / form / lineup / fatigue / cup features | 都是常规联赛逻辑 |
| 没有 `is_relegation_playoff` / `is_promotion_playoff` boolean | ❌ |
| 没有 "Wembley final" / "neutral venue" 修正 | ❌ |
| Pinnacle SP 间接反映 (sharps 调价) | ⚠️ 但 vig baked-in, 无法 decompose |

具体 5-26 实战表现:
- 法甲 0-0: model 给 P_平 = 28.84% **(最低)**, 实际平 → 漏判 (playoff 风格 = 平局率偏高)
- 德乙 2-0: model 给 P_主胜 = 53.78% **(最高)**, 实际主胜 → 对了 (因为 Elo gap 够大, 不是因为 model 懂 playoff)

---

## 1. 工作分层

| 层 | 目标 | 估算 | 数据要求 | 优先级 |
|---|---|---|---|---|
| **P0** | Dashboard ⚠️ banner 提示用户 | 2-3 小时 | 无 (hard-coded 日期窗口) | ✅ **2026-05-27 已 ship** |
| **P1** | `is_relegation_playoff` / `is_promotion_playoff` boolean features 进训练集 | 2-3 天 | football-data.co.uk 历史 CSV (已有) | V13 候选 |
| **P2** | Per-playoff-bucket calibration (类似 V9 per-league T) | 3-5 天 | 同 P1 | V13 候选 |
| **P3** | 专用 playoff-aware artifact + ROI ablation | 5-7 天 | 同 P1 + 单独 walk-forward | V14 候选 (data-gated) |

---

## 2. P0 — 已 ship (2026-05-27)

**核心: `apps/api/src/nutmeg/v4/data/playoff_context.py`**

```python
@dataclass(frozen=True)
class PlayoffWindow:
    league: str         # V4 canonical, e.g. "FRA_LIGUE_1"
    start: str          # ISO YYYY-MM-DD, inclusive
    end: str            # inclusive
    context: str        # short label, e.g. "Ligue 1 barrage de relegation"
    model_bias_note: str  # why model is wrong-for-this-context

def detect_playoff(league, date) -> Optional[PlayoffWindow]: ...
```

**Windows hard-coded** (2025-26 season): 10 leagues × 1 window each.
- 法甲 / 法乙 / 德甲 / 德乙 (barrage / Relegations-Playoff)
- 英冠 (Promotion Playoff to EPL)
- 西乙 (Promotion to La Liga)
- 意乙 (Promotion + Relegation Playoffs)
- 荷甲 (Europe Playoff)
- 葡超 (Promotion Playoff)
- 比利时 Pro League (整个 Playoff Phase 自 3 月起)

**Endpoint wire-in**: `POST /api/v4/today-recommendations` 现在返回 `playoff_warnings: list[PlayoffWarning]`. 空列表 → banner 不显示; 非空 → 列每条 fixture 的语境。

**Dashboard banner**: amber/orange `playoff-banner` CSS, slide-down animation, list fixtures with context label, footer note: "训练集只见过常规联赛, 没标记 '升降级附加赛' 这种语境。建议: 把模型 P 看作下限, 谨慎参考。"

**Tests**: 14 unit + 3 integration (`tests/v4/test_playoff_context.py` + `test_today_recommendations.py::TestTodayRecommendationsPlayoffWarnings`).

**未做的事 (留 P1)**:
- 仍然是 **日期窗口**, 不是真 fixture-level label — 同一窗口内的常规联赛尾轮也会触发 ⚠️
- Windows 是 **2025-26 specific**, 季节末需要手动更新 → V13.5 加 `--year` 参数自动 roll

---

## 3. P1 — Training features (V13 候选, 2-3 天)

### 3.1 数据可获得性

football-data.co.uk 历史 CSV 在末轮通常会有 `Notes` 列或特殊文件标记 playoff matches:
- `e0-playoff-2024.csv` 等可单独抓
- 或主 CSV `Notes` 列 = "Playoff Final" / "Relegation"

**Action item**: 跑一次诊断 CLI `nutmeg-canonical-report --show playoff-rows` 看 24/25 + 23/24 哪些 CSV 行能匹配。

### 3.2 工程方案

| 步骤 | 文件 | LoC |
|---|---|---|
| 1. 数据层: 在 `data/ingest.py::load_all_matches` 加 `is_playoff` boolean | `apps/api/src/nutmeg/v4/data/ingest.py` | ~20 |
| 2. 特征层: 在 `features/pipeline.py::build_feature_frame` 暴露这两个 boolean | `apps/api/src/nutmeg/v4/features/pipeline.py` | ~10 |
| 3. 训练层: `train.py` 接受 `--with-playoff-features` flag (opt-in 同 lineup pattern) | `apps/api/src/nutmeg/v4/cli/train.py` | ~15 |
| 4. Walk-forward 验证: 跑 `nutmeg-playoff-ablation` (新 CLI, 抄 `nutmeg-cup-ablation` 框架) | `apps/api/src/nutmeg/v4/cli/playoff_ablation.py` | ~80 |
| 5. 单元 + 集成测试 | `tests/v4/test_playoff_features.py` | ~120 |

### 3.3 Ship gate (走 V13 W3 的标准)

| 验收项 | 测试 |
|---|---|
| `is_playoff=True` rows 比例 ≈ 0.5% (sanity check) | `test_playoff_features.py::test_playoff_rate` |
| 加 feature 后 multi-season log-loss **不更差** (Δ ≥ -0.001) | walk-forward |
| Pinnacle gap **缩小** (-0.001 以上) — 或 maintain 现状 | `nutmeg-playoff-ablation` |
| **Playoff-only subset** log-loss 显著改善 (≥ -0.01) | 同 |
| 不影响 lineup-aware artifact 的现有性能 | regression |

**Hard NO ship 条件**:
- 加 feature 后总体 log-loss 变差 → 不加 (V8 W4 cup 的教训)
- Playoff subset 改善 < 0.005 → 不值得加复杂度

---

## 4. P2 — Per-playoff calibration (V13 候选, 3-5 天)

V9 W6 已 ship per-league temperature scaling. 思路相同:

- 训练时分两个 calibration set: `is_playoff=True` 和 `is_playoff=False`
- 各 fit 独立 T (Platt scaling) + isotonic
- 服务时 fixture lookup → 选对应 T
- A/B: per-playoff-T artifact vs flat-T artifact 在 holdout playoff subset 上的 log-loss

**为什么独立做 P2 而不是 P1 的一部分**:
- P1 加 feature 但仍然用 flat-T 校准 → 模型可能学了 raw signal 但 calibration 还是被常规分布主导
- P2 是 "出厂校准" 层, 跟 feature 正交

**风险**: Playoff sample 太少 (~50-100 matches/季节 × 10 联赛 = ~800/季), T-fit 可能 unstable. 需要 **跨季 pool** (4-5 季合 ~3000+ matches).

---

## 5. P3 — Dedicated playoff artifact (V14+, 5-7 天)

只在 P1+P2 后还有 residual gap 才做:
- 训练单独的 `nutmeg-train --playoff-only` artifact
- 服务时 fixture 在 playoff window → route to playoff artifact, else default
- 类似 V8 cup-aware artifact 的思路, **但 V8 W4 cup ablation verdict 是 NEGATIVE**, 学到了"专用 artifact ≠ 自动 win"
- 这条路只在 P1+P2 不够时启动

---

## 6. 触发条件 (V13 启动的硬门槛)

按"先验证 P0 banner 真实有用"再扩展:

| 信号 | 行动 |
|---|---|
| 用户 4 周内 ≥ 3 次看到 banner 且 **未下注** (banner 起到风险提示作用) | ✅ 启动 V13 P1 |
| 用户 4 周内 ≥ 3 次看到 banner 但 **照常下注** | ⏸️ Banner 没用, 考虑改成 hard-gate (banner + 自动跳过 EV gate) |
| 4 周内 **0 次** banner 触发 (赛季中段) | 暂缓, 等下季 EOS |
| 14 联赛 ROI < 0 在常规联赛 | ❌ 优先级降到最低 — 先解决基础 ROI |

---

## 7. 守门 (P0 不退化的回归测试)

**已加** (今天的 PR):
- `tests/v4/test_playoff_context.py` (14 unit tests)
- `tests/v4/test_today_recommendations.py::TestTodayRecommendationsPlayoffWarnings` (3 integration tests)

**未加 (跟随 V13 P1 一起做)**:
- Playwright E2E: 模拟一次 5-26 数据, 断言 dashboard 看得到 banner DOM
- pa11y/axe a11y check on banner (color contrast vs amber on light bg)

---

## 8. 关联文档

- `docs/v12_w0_first_real_bet.md` — 触发这次设计的实战记录
- `docs/v12_half_auto_sp_workflow.md` — 第三态 "Directional combo" 设计 (相关 UX 工作)
- `docs/V13_DATA_QUALITY_UPGRADE.md` — 其他 V13 候选 (数据源升级)
- `docs/V13_EUROPEAN_EXPANSION.md` — 其他 V13 候选 (联赛扩展)
- `docs/v8_w4_cup_ablation_verdict.md` — V8 W4 cup verdict NEGATIVE — 学到的教训直接套用

---

## TL;DR

| 项 | 值 |
|---|---|
| 触发 | 2026-05-26 实战发现 model 对 playoff 完全盲 |
| P0 (已 ship) | Dashboard ⚠️ banner, hard-coded 10 联赛日期窗口 |
| P1 (V13 候选) | `is_relegation_playoff` / `is_promotion_playoff` features (2-3 天) |
| P2 (V13 候选) | Per-playoff calibration bucket (3-5 天) |
| P3 (V14+) | Dedicated playoff artifact (条件触发) |
| 何时启动 V13 P1 | 4 周观察期内 banner 真实触发且起作用 |
| 守门 | 14 + 3 测试覆盖 hard-coded windows + endpoint integration |
| 风险 | windows 是 2025-26 specific, 季节末需手动更新 |
