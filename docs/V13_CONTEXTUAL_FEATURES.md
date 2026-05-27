# V13 候选: 比赛语境特征 (非 playoff)

_决策时间: 2026-05-27 · V12 W0 真实下注后系统化盘点_

---

## 0. 触发问题

用户问: "类似升降级附加赛这种, 还有什么因素 model 没考虑? 是否对赛果产生重要影响?"

`V13_PLAYOFF_AWARENESS.md` 覆盖了 playoff/barrage。这份文档覆盖**其他同质的"模型盲点"语境因素**, 按实证影响排序。

---

## 1. 全景表 (诚实分级)

| 因素 | 实证影响幅度 | Model 当前 | Pinnacle 当前 | 信号可获得性 |
|---|---|---|---|---|
| **🔴 高影响** |
| 空场/闭门处罚 | 主场胜率 -10pp (COVID 2020-21 EPL 实测) | ❌ | ✅ | 🟢 易 (UEFA + 各联赛公告) |
| 赛前 1hr 突发伤病/首发轮换 | 顶级球员临时缺阵 λ -0.15~0.25 | 🟡 V6 W7 partial | ✅ | 🟡 中 (cron 时序难) |
| **附加赛 / barrage** | 平局率 +5~10pp | ✅ P0 已 ship | ✅ | (见 V13_PLAYOFF_AWARENESS) |
| 双线作战夹击 (UCL 前后) | 联赛 λ -0.10~0.20 | 🟡 lineup 间接 | ✅ | 🟢 易 (赛程表 + 比赛安排) |
| 2 回合杯赛第二回合 | 第一回合领先方 λ -0.15~0.20 | ❌ | ✅ | 🟢 易 (cup_features 已注册) |
| **🟠 中等影响** |
| 新帅蜜月期 (前 6 场) | 胜率 +5~7pp (Bryson 2013) | ❌ | 🟡 | 🟡 中 (API-Football coach 接口) |
| 赛程密度 (≤3 天间隔) | xG -0.1 / 缺失休息日 | 🟡 V12 fatigue partial | ✅ | 🟢 已有 |
| 国际比赛日后首场 | 主场胜率 -3~5pp | ❌ | ✅ | 🟢 易 (FIFA 日历) |
| 保级直接对话 (bot3 vs bot3) | 平局率 ↑, 进球数 ↓ | ❌ | ✅ | 🟢 易 (table position) |
| 赛季最后 1-2 轮 dead rubber | mid-table 强度 ↓ | ❌ | ✅ | 🟢 易 (round_n + table) |
| 教练下课压力 | 异常 motivation, 方向不定 | ❌ | 🟡 | 🟡 中 (媒体 + sacking odds) |
| 极端天气 (>35°C / 大雪) | λ 影响 ~-0.05 | ❌ | ✅ | 🟡 中 (天气 API) |
| **🟡 低影响 / 难证伪** |
| 教练 H2H 历史 | 样本小, Pinnacle 也不信 | ❌ | 🟡 | 🟢 易但低 ROI |
| 转会窗口分心 | 个别球员效应稀释到队伍 λ 很弱 | ❌ | 🟡 | ❌ unobservable |
| 更衣室矛盾 | 实质存在但无 observable signal | ❌ | 🟡 | ❌ unobservable |
| 裁判倾向 (黄牌/点球) | 1X2/HC 影响 marginal | ❌ | 🟡 | 🟢 易但低 ROI |
| **⚫ 永远捕不到** |
| 操纵嫌疑 / 假球 | 罕见但毁灭性 | ❌ | ❌ | ❌ 只能人为 override |
| 突发战争/停摆 | Russia 2022 | ❌ | ❌ | ❌ |
| 集体感染 / 流感 | COVID-era | ❌ | 🟡 | ❌ |

---

## 2. 五个 V13 P1 候选 (高/中影响 + 信号可获得)

按 (impact × feasibility) 排序:

### Tier 1A — `is_closed_doors`

**为什么是第 1**: 影响最大 (主场胜率 -10pp), signal 最干净 (UEFA/各联赛纪律公告爬即可)

| 步骤 | 工作量 |
|---|---|
| 数据层: 新文件 `data/closed_doors.py` + 静态字典 `{(league, date, home, away): True}` | 0.5 天 |
| 特征层: `build_feature_frame` 加 `is_closed_doors` boolean | 0.3 天 |
| 训练层: `train.py --with-context-features` flag | 0.3 天 |
| 验证: walk-forward `nutmeg-context-ablation` | 0.5 天 |
| 测试 + i18n | 0.5 天 |
| **合计** | **~2 天** |

**风险**: 训练数据里这种行 < 0.2% (Russia/Italy ultras 罚 + COVID 那波)。**模型可能学不到稳定 signal**。若总 log-loss 改善 < 0.0005, 走 P0 banner 模式 (只在 dashboard 警告, 不进 feature)。

### Tier 1B — `is_2nd_leg_with_aggregate`

**为什么**: 2 回合杯赛是结构性的, signal 是确定性的 (赔率市场都心知肚明)

| 步骤 | 工作量 |
|---|---|
| 数据层: `cup_features.py` 已注册, 加 `aggregate_lead` 列 (主队净进球差) | 0.5 天 |
| 特征层: 加 `is_2nd_leg` boolean + `aggregate_lead_home` int | 0.3 天 |
| 训练层: 同 1A | 0.3 天 |
| 验证 (只看 UCL/UEL knockout subset) | 0.7 天 |
| 测试 | 0.5 天 |
| **合计** | **~2.5 天** |

**门槛**: UCL/UEL knockout subset (~120 场/季 × 4 季) log-loss 改善 ≥ 0.005。若 < 此, 不 ship feature, 改 P0 banner。

### Tier 1C — `is_dead_rubber`

**为什么**: 实证显著 + 数据现成

```python
is_dead_rubber = (
    round_n >= total_rounds - 2 AND
    home_team_position_locked AND   # 已锁定排名/无升降级悬念
    away_team_position_locked
)
```

| 步骤 | 工作量 |
|---|---|
| 数据层: `data/table_position.py` (新) — 算各队赛季末锁定时间 | 1 天 |
| 特征层 + 训练 + 验证 + 测试 | 1.5 天 |
| **合计** | **~2.5 天** |

**门槛**: dead rubber subset 上 log-loss 改善 ≥ 0.01 (因为这些比赛 model 应该最盲)。

### Tier 1D — `new_manager_within_6_games`

**为什么**: Bryson et al. (2013) 在 EPL 30 年数据上验过, 蜜月效应 +5-7pp 胜率

| 步骤 | 工作量 |
|---|---|
| 数据层: API-Football `/coaches/transfers` ingest CLI (新, ~80 LoC) | 1 天 |
| 数据层: 历史回填 (4 季 × 14 联赛 ≈ 200 个换帅事件) | 0.5 天 |
| 特征层: 加 `games_since_manager_change` int | 0.3 天 |
| 训练 + 验证 + 测试 | 1.2 天 |
| **合计** | **~3 天** |

**风险**: API-Football coach 接口的历史覆盖率 (尤其小联赛) 可能不全, 需要 manual fix 别的来源。

### Tier 1E — `is_post_international_break`

**为什么**: FIFA 日历静态可知, 影响幅度中等, 实现最简单

| 步骤 | 工作量 |
|---|---|
| 数据层: hard-coded FIFA window 日期 (跟 V13_PLAYOFF_AWARENESS 同模式) | 0.5 天 |
| 特征层 + 训练 + 测试 | 1 天 |
| **合计** | **~1.5 天** |

**门槛**: 总体 log-loss 改善 ≥ 0.001 (低门槛, 因为 signal 真实存在)。

---

## 3. 合并 ship 路径 (V13 P1 全包)

若 Tier 1A-1E 全部上, 总工程量 ~11 天 (~2 周 sprint).

**统一 ship 框架**:
- 一个 module: `apps/api/src/nutmeg/v4/features/context_features.py`
- 一个 flag: `train.py --with-context-features` (opt-in 不影响默认 artifact)
- 一个 ablation runner: `nutmeg-context-ablation` (复用 `nutmeg-cup-ablation` 框架)
- 一个新 artifact: `data/v4_model_cat_context/` (per V8 W4 模式)
- 一份 verdict doc: `docs/v13_context_ablation_verdict_<date>.md`

**Ship gate** (P1 全包):
1. 总体 multi-season log-loss 改善 ≥ 0.002 (Pinnacle gap 缩小)
2. 没有任何 subset 显著变差 (>+0.003)
3. ECE 不退化 (V9 W6 已经在临界, 不能再差)
4. Walk-forward 在 22/23 + 23/24 + 24/25 三季都改善

**Hard NO ship 条件**:
- 总体 log-loss 变差 → 全员撤回, 只保留 P0 banner
- 部分 feature 拖后腿 → 单独保留 PA, 其余落 banner

---

## 4. P2 — Per-context calibration (条件触发)

只在 P1 ship 后跑:

- 每个 context bucket (closed_doors=T/F, 2nd_leg=T/F, dead_rubber=T/F, ...) 单独 fit isotonic
- 同 V9 W6 per-league T 思路, 但 buckets 是 boolean cross-product
- 风险: bucket sample 不够 → 退回 single T

工程量: 3-5 天 (借鉴 V9 W6)。

---

## 5. 永远捕不到的因素 — 人为 override 设计

操纵嫌疑 / 战争停摆 / 集体感染 / 突发金融危机 这类**模型架构上无法 catch** 的事件, 需要:

| 设计 | 描述 |
|---|---|
| Dashboard "暂停推荐" 按钮 | 用户主动 disable 某联赛 / 某天 N 天的推荐 |
| `data/overrides.yaml` 文件 | static config, 列已知 disable 的联赛 + 日期 |
| 启动时加载 + 端点 hook | `/today-recommendations` 跳过 overrides 列表的 fixtures |

工程量: 1 天。**这个无门槛, 可以随时 ship** (P0 的 P0)。

---

## 6. 触发条件 (V13 启动)

跟 `V13_PLAYOFF_AWARENESS.md` 一样, **不要现在启动**。等 4 周 ROI verdict:

| 信号 | 行动 |
|---|---|
| 14 联赛 ROI **正且 > +5%** | ✅ 启动 V13 P1 全包 (Tier 1A-1E) |
| 14 联赛 ROI **正但 < +5%** | ⏸️ 只做 1A (closed_doors) + 1E (FIFA break), 跳过中等 ROI 改善 |
| 14 联赛 ROI **0 或负** | ❌ 不做 context features, 先回去解决基础 model |
| Banner 上下文 (playoff/closed-doors) ≥ 5 次触发且**用户未下注** | ✅ banner 起作用了, 升级到 feature |

---

## 7. 我的诚实判断

**模型不可能赶上 Pinnacle 的 closing line.** 剩 7% gap 里:
- **3-4% 是 sharps 对 late-breaking 信息的实时反应** — 我们 cron 时序结构上输, 加再多 feature 也补不全
- **2-3% 是市场聚合的 wisdom of crowds** — 我们没有 belief-aggregation 机制
- **1% 是 ML 残差** — 可以靠 P1 contextual features 慢慢蚕食

所以 V13 contextual features 的真实期望:
- 总体 log-loss 改善 **0.001 ~ 0.003** (蚕食那 1% ML 残差的一部分)
- **不是** "推翻 Pinnacle"
- **是** "在 niche subset 上模型更清醒, 给用户更靠谱的 P 估计"

V13 目标定位是 "**让 model 在 Pinnacle 也不够 sharp 的场景里相对更优**", 不是 "全面超越 Pinnacle"。

---

## TL;DR

| 项 | 值 |
|---|---|
| 范围 | 5 个非 playoff 语境因素 (closed_doors / 2nd_leg / dead_rubber / new_manager / post_intl_break) |
| 总工程量 | ~11 天 (P1 全包) + ~5 天 (P2 calibration) = **~16 天** (~3 周 sprint) |
| 真实期望 | log-loss 改善 0.001-0.003, ECE 不退化 |
| 何时启动 | 等 4 周 ROI verdict (2026-06-23 +/-) |
| 守门 | `nutmeg-context-ablation` 走 V8 W4 同款 ablation 框架 |
| 永远做不到的 | 操纵嫌疑, 战争, 突发集体感染 — 改用人为 override 设计 |
| Backup 路径 | 任何 feature ablation 不过 → 落回 P0 banner 模式 (今天 playoff 同款) |
