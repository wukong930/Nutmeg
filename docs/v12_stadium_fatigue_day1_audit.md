# Stadium / Fatigue 接入训练 — Day 1 数据依赖审计

_2026-05-26 · Audit before V12 integration decision_

## 一句话结论

**Fatigue 可立刻接入；Stadium 数据基础不存在，要先做 5-7 天的数据 ingest 工作才能开始**。建议**只走 Fatigue 路径**进行 Path B（接入 + ablation + 文档化）。

---

## 0. 调研方法

按"先验证后决策"的项目惯例 (V5 W6 / V8 W4 / V9 W6 都同款流程)：

1. ✅ 跑 module 自己的 unit tests — 都过
2. ✅ 阅读 module docstring — 自我声明的依赖
3. ✅ 检查 production training data 是否有需要的列
4. ✅ 在真实 EPL 24/25 数据上 smoke-test 调用
5. ✅ 输出本 verdict 文档

总耗时约 2 小时（计划是 0.5-1 天，比预期快）。

---

## 1. Fatigue Features — GREEN ✅

### 1.1 数据需求 (都已满足)

| 需求 | Production 训练数据 | 状态 |
|---|---|---|
| `date` (pd.Timestamp) | ✅ football_data CSV 有 `Date` | ✓ |
| `home_team`, `away_team` (str) | ✅ `HomeTeam`, `AwayTeam` | ✓ |
| `league` 或 `competition` | ✅ `Div` 字段 | ✓ |

**零新数据依赖** — module 设计为纯 walk-in-time-order, 用现有训练数据 in-place 即可。

### 1.2 真实数据 smoke test (EPL 24/25)

跑了 `build_fatigue_features(epl_2425_normalized)`:

```
Source: 380 EPL 24/25 fixtures
Output: 380 × 12 feature columns

Feature 触发率 (out of 380 rows):
  fatigue_home_short_rest_3day:   39 (10.3%)  ← 真实存在的赛程压缩
  fatigue_home_short_rest_5day:   84 (22.1%)  ← 圣诞周等
  fatigue_home_long_rest_14day:   39 (10.3%)  ← 国际比赛日后
  fatigue_home_third_match_8day:  19 ( 5.0%)  ← 一周三赛
  fatigue_home_matches_in_30day: 370 (97.4%)  ← 中后段都有
  fatigue_home_euro_midweek_4day:  0 ( 0.0%)  ← ⚠️ 见下
  (away 列分布相似)
```

10 个 feature 都有合理触发，**1 个 feature 触发率 = 0**（见 §1.3）。

### 1.3 已知 minor 问题：euro_midweek_4day 在纯 EPL 数据上不会触发

**原因**：football_data CSV 只有 EPL fixtures，没有 UCL/UEL 同期 fixtures。Module 的设计假设输入 DataFrame 是**全部联赛合并的时间序列**，这样一个 EPL 队周三打 UCL → 周六打 EPL 时 euro_midweek=1 才能被检测到。

**影响**：
- 不致命 — 缺这一 feature 等于 baseline 不变；CatBoost 会忽略全零列
- 但是 ablation 测试如果只在单联赛数据上跑，会少 10-15% 的潜在信号

**修复方法**（如果要做）：
- 在 `train.py` 调用 `build_fatigue_features` 时，先把 UCL/UEL fixtures（已在 `data/external/cup_history/`）UNION 进单联赛 frame，按 date 排序，跑 fatigue，最后 inner join 回 EPL 主帧
- 工程量：~1 天

**建议**: 第一次 ablation **先不加这步**，让 baseline 跑出来；如果整体 ablation 是 marginal/negative，再考虑做这个增强。

### 1.4 数据泄漏检查 — PASSED ✅

Module 实现是 `for i in range(n): ... histories[home].add(d, comp)` —— **历史在循环内逐步累加**，从不预先全部 push。任何 `i` 时刻的 `histories[team]` 只包含 `date < dates[i]` 的条目。

**Strictly forward**, no future leak. (与 V6 W5 lineup leak bug 形成对比 — 那个是直接 query `/injuries` 拿到了未来事件)。

### 1.5 接入工程量

| 步骤 | 工时估计 |
|---|---|
| 1. 在 `train.py` 加 `--with-fatigue` flag | 0.5 天 |
| 2. 在 `build_features_for_fixtures` (persist.py) 加 fatigue hook + 提供训练时缓存 | 1 天 |
| 3. 在 `predict_lambdas` 路径确保 inference 时也能算 fatigue (用 fixture cache 算 deque) | 0.5 天 |
| 4. 跑 walk-forward ablation (multi-season + 3-chunk stability, 同 P1#18) | 0.5 天 wall + 计算时间 |
| 5. 写 verdict 文档 (`docs/v12_fatigue_ablation_<date>.md`) | 0.5 天 |
| **总计** | **3 days** |

---

## 2. Stadium Features — RED 🔴

### 2.1 数据需求 (大部分都不存在)

| 需求 | 状态 | 来源 |
|---|---|---|
| `home_venue_id` 字段在 fixtures 上 | ❌ 不存在 | 需要 ingest from API-Football `/fixtures` JSON |
| `away_team_prior_venue_id` | ❌ 不存在 | 需要 per-team 跨 fixture 计算 |
| `data/external/stadiums.parquet` registry | ❌ 不存在 | 需要 ingest from API-Football `/venues` |
| Altitude (海拔) | ⚠️ 只有 12 个 high-altitude 硬编码 | 其余需 Open-Elevation API 或 GeoNames |
| Capacity (容量) | ❌ 不存在 | API-Football `/venues` 有 |
| Surface type (草皮类型) | ❌ 不存在 | 不在 API-Football, 需另寻 |

### 2.2 Module 自我承认的 "NOT in this skeleton"

直接引用 `stadium_features.py` 第 38-45 行 docstring:

> ## NOT in this skeleton (Branch B W2 deliverable)
>
> - Actual `data/external/stadiums.parquet` data file
> - API-Football `/venues` endpoint ingester
> - Open-Elevation API integration for altitude lookup
> - Travel-distance computation (uses haversine; needs lat/lon for both home and away team's previous venue)
> - Walk-forward ablation against current production

`build_stadium_features()` 设计上确实是 "venue_registry=None defaults to empty dict, returns all-NaN frame" 的 defensive 实现，**调用不会 crash，但 100% 行都是 NaN/0**。

### 2.3 接入工程量

| 步骤 | 工时估计 |
|---|---|
| 1. 写 API-Football `/venues` ingester (CLI) | 1.5 天 |
| 2. 拉 14 联赛 × ~20 队 = ~280 venues (API budget 充足) | 0.5 天 |
| 3. 拼出 stadiums.parquet schema + builder | 0.5 天 |
| 4. Altitude 补齐（Open-Elevation API for 缺失项） | 1 天 |
| 5. team→venue lookup at fixture-time + cross-fixture "where did away team play last" | 1.5 天 |
| 6. 在 `train.py` + `persist.py` 集成 stadium hook | 0.5 天 |
| 7. 跑 walk-forward ablation | 0.5 天 |
| 8. 写 verdict 文档 | 0.5 天 |
| **总计** | **6-7 days** (本质上要 ship "Branch B W2") |

### 2.4 风险加权

即使做完 6-7 天工作，预期 hit-rate 增益 ~0.1-0.3pp（参考 stadium 在公开文献的边际影响）。

**Stadium 的低收益高投入 → 不优先**。

---

## 3. 决策

按"小批量先 ship 验证 → 用真实 ablation 决定下一步"的项目方法论：

### Path 选择：**只做 Fatigue (Path B)**

理由:
1. ✅ 零新数据依赖, 工程清爽
2. ✅ Module 已经有 35 个 unit tests pass
3. ✅ Real-data smoke test 显示 10/12 features 有真实信号
4. ✅ 3 天接入 + 1 天 ablation, 总 4 天
5. ✅ 不阻塞 cron / production model
6. ✅ 即使 ablation NEGATIVE，也产出一份诚实 verdict 文档（和 V5 W6 / V8 W4 / V9 W6 同款）

### Path 排除：**Stadium 移到 V13 backlog 或 deprecate**

理由:
1. 🔴 6-7 天工作量, 大部分是 ingest 而非 ML
2. 🔴 预期增益小 (0.1-0.3pp)
3. 🔴 数据耦合多 (API-Football + Open-Elevation + 可能还要 weather)
4. ⚠️ 等 fatigue verdict 出来后再决定是否值得：如果 fatigue +0.5pp，stadium 可能没必要；如果 fatigue 0pp，stadium 也可能 0pp

---

## 4. 接下来的执行计划

### Day 2-4: Fatigue 接入 (3 天)

```bash
# Day 2 (~1 day)
# Add --with-fatigue flag to train.py
# Wire build_fatigue_features into persist.py::build_features_for_fixtures
# Train data path: compute fatigue on full historical frame
# Inference data path: maintain rolling TeamHistory cache

# Day 3 (~0.5 day wall clock + compute)
# Run walk-forward ablation: V6 W7 lineup-aware baseline vs +fatigue
# Multi-season (22/23, 23/24, 24/25) — use existing multi_season_bench.py infra

# Day 4 (~0.5 day)
# 3-chunk in-season stability test (Sep-Nov / Dec-Feb / Mar-May)
# Same harness as P1#18 for lineup-aware
# Write docs/v12_fatigue_ablation_<date>.md verdict

# Ship gate:
#   walk-forward log-loss ≥ -0.001  AND
#   3-chunk ROI ≥ -3pp per chunk
# Otherwise document as NEGATIVE and don't ship to production
```

### Stadium 进 V13 backlog

不在当前 sprint 范围。归档到 `docs/V12_BACKLOG_DRAFT.md` 的 Tier 3 (deferred features)。

---

## 5. 验收

**Day 1 audit 完成 ✓**:
- [x] 跑了 71 个现有 unit tests, 全过
- [x] 阅读两个 module docstring + 关键函数
- [x] 检查 production 训练数据 columns
- [x] 真实 EPL 数据 smoke test
- [x] Verdict 文档 (本文件)

**下一步**: 用户决定要不要走 Day 2-4 fatigue 接入。如果是 → 进 implementation。如果否 → close thread, 等 cron 数据。
