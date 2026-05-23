# Nutmeg V5 路线图

_最后更新：2026-05-23_

V5 是在 V4（GBM-λ + Dixon-Coles + Temperature scaling）基础上的**演进**，不是推倒重来。V4 内核被多季验证（22/23、23/24、24/25 log-loss 均稳定 +0.008 vs Pinnacle），保留作为永久 fallback；V5 扩展数据维度（免费 xG / 市场动态）+ 模型 Ensemble + 工程瘦身。

## 为什么做 V5

- V4 端到端打通后 log-loss 卡在 **0.9987**（Pinnacle 0.9904，差 +0.0083），多季稳定但**进度停滞**
- 代码严重臃肿：`apps/api/src/nutmeg/` 共 304 文件 / ~224k 行，legacy `accuracy/` + `recommendations/` + 旧 modeling/features/api/ 重复了 V4 已覆盖的工作；`pyproject.toml` 暴露 **196+ 个 CLI 命令**
- V4 路线图的 P1（xG、阵容）在等付费数据，但 **understat / fbref / clubelo / OddsPortal 这些免费源完全未利用**
- 单一 LightGBM 模型，未尝试 Ensemble / Bayesian 分层
- 无 R&D 闭环：缺少 A/B 对比、实战 vs 回测 gap 监控

## 目标（12 周内）

1. **工程**：代码文件数减少 ≥ 80%；Git 化 + 推 wukong930/Nutmeg；GH Actions 自动化 CI 实验框架
2. **预测**：log-loss 从 0.9987 → ≤ **0.9937**（累计降 0.005，逼近 Pinnacle 0.9904）；多季稳定
3. **实战**：4 周连续实盘观察，ROI（Kelly0.25）≥ **+2pp**；实战与回测 gap ≤ ±4pp（无 leakage）

**核心路径**：保留 V4 内核 → 数据扩展 60% + Ensemble 25% + 工程优化 15%。

## 12 周路线图

| 周 | 主题 | 关键产出 | 验收 |
|----|------|---------|------|
| W1 | Git 化 + 基线锁定 | git init、push GitHub、`tag v4.0-frozen` | 远程仓库可见，baseline 落盘 |
| W2 | 激进瘦身 | 删除 legacy 280+ 文件 | 文件数 ≤50；V4 测试 100% 绿；log-loss = 0.9987 ± 1e-4 |
| W3 | 外部数据 ingest 铺底 | understat / clubelo / OddsPortal 入库 | 英超≥95%、J1=0%（接受） |
| W4 ✅ | xG-lite + clubelo 特征 | `features/{xg_lite,clubelo_features}.py` + pipeline 集成 | **达成：24/25 log-loss 0.9987 → 0.9971（−0.0016）**；多季稳定改善 |
| W5 ⚠️ | 市场动态 ablation | `features/market_dynamics.py` 框架就绪但 dormant | **负面结果**：drift 特征在 3 季验证中无法稳定降 log-loss；见 [v5_w5_ablation.md](v5_w5_ablation.md) |
| W6 ✅ (mixed) | Ensemble ablation | xgb+cat+stacker 全部接入 walk_forward；`--with-ensemble` 比较 | **stacker 失败但 CatBoost 单模型胜出**（平均 -0.0033 vs LightGBM，三季全胜），见 [v5_w6_ablation.md](v5_w6_ablation.md)。W7 迁 prod 用 CatBoost。|
| W7 ✅ | CatBoost prod 迁移 | `--model cat`、artifact 多后端、e2e 测试 | CatBoost 可作 prod 选项（W6 已证 -0.0033 多季稳定改善）；默认暂留 lgb 给 W8 观察期 |
| W7+ | Bayesian 分层（推迟） | MAP per-league offset | 推迟到 W9 — 先做 W8 实战 |
| W8 | 实战观察循环 | 双快照（闭盘前/后）+ live_vs_backtest | 每周自动 ROI gap 报告 |
| W9 | 校准微调 | 让球独立 T + per-league T | ECE ≤ 0.020 |
| W10 | 实验追踪自动化 | GH Actions + `experiment_tracker` | 每周 `docs/weekly/<YYYY-WW>.md` 自动 push |
| W11 | 路由收敛 + 产品化 | 删 v1 路由，`/api/v4/predictions/upcoming` | 单一 v4 API |
| W12 | 评估与扩展决策 | V5_HANDOFF；决定是否买 API-Football | 实战 ROI ≥ +2pp 即解锁付费数据 |

**回退点**：每周一个 git tag `v5.w<n>`，恶化时 `git reset --hard v5.w<n-1>` 重做。

## 数据源（W3 实测结果）

W3 实测：抓取生态比预期严苛，仅 1/4 免费源可用。

| 源 | 状态 | 说明 |
|----|------|------|
| **clubelo** | ✅ **可用** | HTTP CSV API 公开；335 个 V4 队 ~60-75% 命中（顶级联赛 ≥ 90%，下级联赛缺失） |
| understat | 🚫 阻塞 | 站点已转 JS-rendered；`understat` 包 + httpx scrape 均失效 |
| fbref | 🚫 阻塞 | 所有 UA 返回 HTTP 403（Cloudflare） |
| OddsPortal | 🚫 暂缓 | Cloudflare + JS shell；用 football-data.co.uk B365 开盘赔率替代 |
| API-Football | ❓ W12 决策 | $19/月，含 xG + 阵容；实战 ROI 不足 +2pp 才考虑 |

**W3 实际交付**：
- `nutmeg.v4.data.sources.clubelo`：完整可用（fetch / cache / date-lookup）
- `nutmeg.v4.data.sources.{understat,fbref,oddsportal}`：留 stub + 错误信息指向解决方案
- `nutmeg.utils.team_canonical`：8 个联赛的命名映射 + 模糊匹配（86% 阈值）
- `nutmeg.v4.cli.ingest_external`：统一 CLI，写 `docs/v5_external_data_coverage.md`
- 48 个新单元测试（22 team_canonical + 12 clubelo + 14 ingest CLI）

**W4 调整**：xG 走"xG-lite"路线（用 V4 已有的 `home_shots` / `home_shots_on_target` 构造 prematch xG 期望），不再等付费数据。这是 V4_HANDOFF 原 P1 计划，被验证更务实。

**统一 join key**：`(competition_code, home_canonical, away_canonical, date_local)`；`utils/team_canonical.py` 处理命名差异。

## 模型升级（W4-7）

- **W4 xG 特征**：`xg_for/against_rolling_6`、`xg_minus_goals_diff_n`（regression-to-mean）、`xg_based_elo`、`xg_available` 旗标
- **W5 市场动态**：`prob_drift_*` (close − open)、`overround_compression`、`handicap_line_drift`、`steam_flag`。**严格防 leakage**：`feature_availability_minutes_before_kickoff ≥ 30`
- **W6 Ensemble**：LightGBM + XGBoost + CatBoost → LogisticRegression stacker（在 1X2 概率层融合，不在 lambda 层避免几何不一致）
- **W7 Bayesian 分层**：`scipy.optimize.minimize` MAP（不引 PyMC），仅服务 J1、葡超、Championship 小样本联赛

## 评估闭环（W8-10）

- **实验追踪**：CSV + git tag（每次 train 落 `data/v4_model/experiments/<sha>/card.md`）；不引 MLflow
- **自动 walk-forward**：GH Actions cron 每周日 02:00 UTC，产物 push `docs/weekly/<YYYY-WW>.md`
- **A/B head-to-head**：`v4/eval/walk_forward.py` 接受 `models: list[ModelProfile]`
- **实战 vs 回测 gap**：每周一 cron，gap > ±5pp 自动创 issue

## 风险与权衡

1. **xG 覆盖率不全**：J1≈0% → `xg_available` 旗标让 GBM 自学权重
2. **Ensemble 训练成本**：3 base + stacker ≈ 4× 时间，但 4k 样本 × 30 特征仍 < 5 min。**验收 ≥ +0.001 才并入**
3. **lookahead leakage**：W5 引入 opening odds 必须严格 `availability_minutes_before_kickoff ≥ 30`
4. **OddsPortal 反爬**：playwright + 随机 UA + 2s 间隔；降级到 B365 opening odds
5. **激进瘦身风险**：W2 期间 grep 强制无依赖才删；每天 commit 可回滚
6. **Bayesian 是否值得**：W7 末改善 < 0.005 则砍掉
7. **付费数据决策**：W12 末实盘 ROI ≥ +2pp 已达标则不必立即买；卡在 0-1pp 再花 $19/月接 1 个月 A/B

## 验收标准（按周）

| 阶段 | 指标 | 目标 |
|------|------|------|
| W1 end | GitHub 远程可见 | baseline tag 已推 |
| W2 end | `apps/api/src/nutmeg/` 文件数 | 304 → ≤ 50 |
| W2 end | log-loss (24/25) | = 0.9987 ± 0.0001 |
| W2 end | V4 测试通过率 | 112/112 |
| W4 end | log-loss (xG-covered 联赛) | ≤ 0.9957 |
| W5 end | log-loss (24/25, 全集) | ≤ 0.9937 |
| W6 end | Ensemble vs 单 GBM | ≥ +0.001 |
| W6 end | ECE | ≤ 0.020 |
| W8 end | 实盘 ROI（flat 1u，4 周） | ≥ 0% |
| W12 end | 实盘 ROI（Kelly0.25，4 周） | ≥ +2pp |
| W12 end | 实盘 vs 回测 ROI gap | ≤ ±4pp |

## GitHub 推送节奏

- **W1 D1**：git init + push main + tag `v4.0-frozen` ✅
- **每周末**：`git tag v5.w<n>` push origin
- **W10 起**：GH Actions 每周日自动 push 周报
- **主分支保护**：W10 后每个 PR 必须 CI 绿

## 参考

- V4 详细设计：[V4_HANDOFF.md](V4_HANDOFF.md)
- V4 baseline 数字：[v4_baseline_card.md](v4_baseline_card.md)
- V4 多季稳健性：[v4_multi_season_card.md](v4_multi_season_card.md)
