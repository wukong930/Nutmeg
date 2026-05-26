# V13 候选: 欧洲联赛覆盖扩展

_决策时间: 2026-05-26 · 用户明确拒绝中超 + 南美联赛, 只扩欧洲范围_

---

## 0. 用户决策

```
✗ 中超 (CSL / CL1)          ← 放弃
✗ 南美联赛 (巴甲/阿甲等)    ← 放弃  
✓ 欧洲联赛                    ← 候选扩展范围
✓ 欧洲杯赛 (UCL/UEL/UECL)    ← 候选扩展范围
```

**底线**: 现有 14 联赛范围内的比赛必须 100% 识别 (今天 BEL_PRO_LEAGUE bug 已修, 加 guardrail 防御)。

---

## 1. 现有 14 联赛 (Production set, 2026-05-26)

| 类别 | 联赛 | 国家 | API-Football ID | 训练数据来源 |
|---|---|---|---:|---|
| **Top 5** | EPL | 英国 | 39 | football-data E0 |
| | ESP_LA_LIGA | 西班牙 | 140 | football-data SP1 |
| | ITA_SERIE_A | 意大利 | 135 | football-data I1 |
| | GER_BUNDESLIGA | 德国 | 78 | football-data D1 |
| | FRA_LIGUE_1 | 法国 | 61 | football-data F1 |
| **二级** | ENG_CHAMPIONSHIP | 英国 | 40 | football-data E1 |
| | ESP_SEGUNDA_DIVISION | 西班牙 | 141 | football-data SP2 |
| | ITA_SERIE_B | 意大利 | 136 | football-data I2 |
| | GER_2_BUNDESLIGA | 德国 | 79 | football-data D2 |
| | FRA_LIGUE_2 | 法国 | 62 | football-data F2 |
| **其他欧洲** | NED_EREDIVISIE | 荷兰 | 88 | football-data N1 |
| | PRT_PRIMEIRA_LIGA | 葡萄牙 | 94 | football-data P1 |
| | BEL_PRO_LEAGUE | 比利时 | 144 | football-data B1 |
| **亚洲** | JPN_J1 | 日本 | 98 | football-data JPN |

---

## 2. V13 候选扩展 (按优先级)

### Tier 1 — football-data.co.uk 已经覆盖, 工程成本低

football-data.co.uk 是我们核心训练数据源, 它免费提供 CSV 包含历史比赛 + 全套 closing odds。已经在文件系统但**目前 load_all_matches 不读**的联赛:

| 联赛 | 国家 | 复盘原因不读 | 估计 ROI 影响 |
|---|---|---|---|
| **苏格兰超** (SC0) | 苏格兰 | 历史训练逻辑只读 E0/SP1/I1/D1/F1 等 | +1pp 覆盖, signal 应类似 EPL 二级 |
| **苏格兰甲** (SC1) | 苏格兰 | 同上 | +0.5pp 覆盖 |
| **希腊超** (G1) | 希腊 | 同上 | +0.5pp 覆盖 |
| **土耳其超** (T1) | 土耳其 | 同上, 数据质量高 | +1.5pp 覆盖 |

**工程**: ~2 天
- 在 `data/__init__.py::load_all_matches` 加新文件路径
- 在 `api_football.py::_DOMESTIC_LEAGUE_IDS` 加 4 个 ID
- 在 `competitions.py` 加 league enum 项
- 在 `data/team_canonical.py` 加 4 国队名规范化
- 在 `data/team_name_zh.py` 加中文名 (~100 个队)
- 在 `setup_local_pipeline.sh` LEAGUES 加 4 项
- 跑 walk-forward 验证: 现有模型加这 4 个联赛 train, log-loss 不能掉

**风险**: 低
- 都是欧洲 top-flight, signal 跟现有 14 同质
- football-data.co.uk 已经收集 (无新数据源)

### Tier 2 — football-data.co.uk 已有但**赛季短/数据少**

| 联赛 | 国家 | 数据量 | 复盘 |
|---|---|---|---|
| 奥甲 (AUT) | 奥地利 | ~180 场/赛季 | 数据量足够 |
| 瑞士超 (SWZ) | 瑞士 | ~180 场/赛季 | 数据量足够 |
| 丹超 (DNK) | 丹麦 | ~180 场/赛季 | 数据量足够 |
| 瑞超 (SWE) | 瑞典 | ~240 场/赛季 | 春秋赛季, 注意 cutoff |
| 挪超 (NOR) | 挪威 | ~240 场/赛季 | 春秋赛季 |
| 芬超 (FIN) | 芬兰 | ~150 场/赛季 | 数据偏少 |
| 波超 (POL) | 波兰 | ~240 场/赛季 | 数据量足够 |
| 俄超 (RUS) | 俄罗斯 | ~240 场/赛季 | ⚠️ 制裁/数据连续性 |

**工程**: ~3-4 天
- 与 Tier 1 同样的步骤, 但要处理"春秋赛季 vs 跨年赛季"的混合
- 现有 `load_all_matches` 默认按 "<YY>YY" 跨年命名, 春秋赛季需要新读法

**风险**: 中
- 小联赛的 Pinnacle odds 可能更稀疏 (5-10% 的比赛没 closing odds)
- 战术风格 + 球员质量差异大于 Top 5, model transfer 可能下降

### Tier 3 — UEFA Cup Competitions

**重要历史**: V8 W4 `nutmeg-cup-ablation` verdict **NEGATIVE**:

```
Verdict (docs/v8_w4_cup_ablation_verdict.md):
  添加 UCL/UEL 训练数据 → log-loss WORSE by +0.0023
  原因: cup matches 球队选择 (强队对强队) 偏离常态分布,
        cross-league seed (用国内联赛 Elo seed cup) 不能修
  Decision: DO NOT SHIP cup-aware artifact
```

**所以 UCL/UEL 不应该再加进训练集**。但可以单独支持识别 + 推荐:

| 路径 | 状态 |
|---|---|
| **A. 加 UCL/UEL 到 cron 的 ingest_odds --leagues** (只 query, 不训练) | ⚠️ 可做, 但模型对 cup 信号弱 |
| **B. 单独 cup-only model** (类似 WC 那个 NationalTeamModel) | 5-7 天, 不确定收益 |
| **C. Path A++ style: cup 用 Pinnacle market 主导 + 模型微调** | 2-3 天, 借鉴 WC 让球的设计 |

**建议**: V13 不做 cup。让 UCL/UEL 留给 V14 或永久 deferred。

---

## 3. 推荐的 V13 范围 (如果走)

### Plan A — 保守 (4 联赛, ~2 天)

只加 Tier 1: **苏超 + 希超 + 土超 + 苏甲**。

| 字段 | 值 |
|---|---|
| 联赛数 | 14 → 18 |
| 工程量 | 2 天 |
| 风险 | 低 |
| 覆盖增益 | +3-4pp (一年大约 200-400 场新覆盖) |
| 模型风险 | 训练数据同质, 不会掉 log-loss |

### Plan B — 标准 (8 联赛, ~5 天)

Tier 1 + 部分 Tier 2: 4 个 Tier 1 + **奥甲 + 瑞士超 + 丹超 + 波超**。

| 字段 | 值 |
|---|---|
| 联赛数 | 14 → 22 |
| 工程量 | 5 天 |
| 风险 | 中 |
| 覆盖增益 | +6-8pp (一年 +600-1000 场) |
| 模型风险 | 个别小联赛可能让 log-loss 微跌 (-0.001 ~ +0.001) |

### Plan C — 激进 (12 联赛, ~7-9 天)

Tier 1 + 大部分 Tier 2 (排除俄超因制裁): 12 个新联赛。

| 字段 | 值 |
|---|---|
| 联赛数 | 14 → 26 |
| 工程量 | 7-9 天 |
| 风险 | 中-高 |
| 覆盖增益 | +10-12pp |
| 模型风险 | 春秋赛季 + 小联赛混合, 需要重新调参 |

---

## 4. 触发条件 (什么时候启动 V13)

**不要现在就启动**。理由 (按重要性):

1. **4 周真实下注 ROI 数据未到** — 决定值不值得扩范围的根本依据
2. **明天 cron 修复完才有数据流** — 至少等一周看 cron 稳定性
3. **fatigue ablation 没跑完** — 那是先于扩联赛的 model 验证

**等什么信号出现再启动 V13**:

| 信号 | 说明 | 行动 |
|---|---|---|
| 14 联赛 ROI **正且 > +5%** | 模型在已有联赛能赚钱 | ✅ 启动 V13 Plan A → B |
| 14 联赛 ROI **正但 < +5%** | edge 太小被 vig 吃 | ⏸️ 先改 model 不扩联赛 |
| 14 联赛 ROI **0 或负** | 模型不 work | ❌ 完全不扩, 回去解决 model 问题 |
| 每天 5+ 个比赛在 14 联赛外 (经常被竞彩列出) | 覆盖率痛点显著 | ⚠️ 考虑 Plan A 加 1-2 联赛 |

---

## 5. 何时不启动

- **如果生产模型 ROI 不证明** → 扩联赛只是扩大亏损面
- **如果工程时间紧张** → 与其加 4 联赛, 不如完善单关推荐 UX
- **如果用户日下注 < 3 场** → 当前覆盖率够用, 扩联赛收益递减

---

## 6. Done Criteria (V13 真正 ship 的标准)

无论选 A/B/C, V13 ship gate:

1. ✅ 所有新联赛通过 `test_league_coverage.py` 守门
2. ✅ Walk-forward log-loss 比 14-league baseline 不更差 (Δ ≥ -0.001)
3. ✅ 3-chunk in-season stability test (P1#18 同款)
4. ✅ 每联赛至少 3 个赛季历史训练数据
5. ✅ team_canonical 处理新联赛球队名 (跨数据源队名匹配)
6. ✅ 中文名 dict 覆盖率 > 90%
7. ✅ Cron 实际 query 这些联赛 + 7 天观察期 0 错误

---

## TL;DR

| 项 | 值 |
|---|---|
| 范围 | **欧洲联赛 + 欧洲杯赛 only** (中超/南美/AFC 都不做) |
| Tier 1 推荐 | 苏超/希超/土超/苏甲 (+4 联赛, 2 天工程) |
| Tier 2 候选 | 奥甲/瑞士超/丹超/波超 等 (+4-6, 中等风险) |
| Cup 竞赛 | V8 W4 ablation NEGATIVE, 不加 |
| **何时启动** | 等 4 周 ROI verdict; 现在不做 |
| **守门** | `tests/v4/test_league_coverage.py` 已 ship (today fix) |
| **底线** | "能识别没识别" — Belgium bug 已修, 加 5 个 regression 测试 |
