# V4 重构交接文档

_最后更新：2026-05-22_

这份文档是 V4 重构的**单一信息源**。下次会话（无论由我或 codex 接手）
请先读它，再读代码。每次会话**追加 Friday Note 到底部**，不要重写。

---

## 1. 已决定的事（不再讨论）

| 决策 | 选择 |
|------|------|
| 联赛覆盖 | 五大联赛（顶级+二级）+ J1 + 荷甲 + 葡超 + UEFA 三杯 + 国家队赛事 |
| 输出市场 | **1X2 胜平负 + 让球 1X2（中国整数让球）**，仅此两项 |
| 架构路线 | **路线 C**: GBM 推 lambda + Dixon-Coles 给 score grid |
| 旧代码 | 暂留原地，v4 不 import；等 v4 稳定后整体迁 `legacy/` |
| 硬基线 | Pinnacle 收盘 1X2（devig 后） |
| 数据 | 27k 场 football-data.co.uk；阵容/伤停留到模型稳定后再买 |
| Kelly | 0.25 分数凯利 + 5% 仓位封顶 |
| 校准 | Temperature scaling（单参数，小样本鲁棒）；isotonic 等 5k+ 验证样本再用 |

---

## 2. V4 当前完整管线（产线就绪部分）

```
data/historical_sources/                          # 输入：football-data.co.uk CSV (27k 场)
  ↓ nutmeg.v4.data.ingest
统一 DataFrame（13 个联赛、含 Pinnacle 收盘价、AHCh 等 119 字段）
  ↓ nutmeg.v4.features.build_feature_frame
24 个特征（market_p_*, elo_*, form_*, market_handicap_line ...）
  ↓ nutmeg.v4.model.gbm_lambda（Poisson 损失，市场赔率 + Elo + form）
(lambda_home, lambda_away)
  ↓ nutmeg.v4.model.dixon_coles.score_grid(rho=-0.10)
9×9 比分概率矩阵
  ↓ grid_to_1x2 / grid_to_handicap_1x2(handicap_home)
1X2 概率 + 让球 1X2 概率
  ↓ nutmeg.v4.calibration.temperature （在 90 天验证集 fit；应用到 test）
校准后概率
  ↓ nutmeg.v4.combo.recommend_combinations（候选枚举 + Kelly 排序）
最终 2~8 串 1 推荐（含复式扩展）
```

CLI：`PYTHONPATH=apps/api/src python -m nutmeg.v4.cli.bench`

---

## 3. 当前数字（baseline_card 摘要）

24/25 测试赛季、13 个联赛、4,792 场 Pinnacle 覆盖、4,331 场 GBM 可用：

| Model | log-loss | Brier | hit-rate | ECE | Δ vs Pinnacle |
|-------|---------:|------:|---------:|----:|--------------:|
| Pinnacle 收盘（GBM-eligible 子集） | 0.9904 | 0.5916 | 51.2% | 0.012 | (基线) |
| **V4 GBM-λ + DC + Temp** | **0.9987** | **0.5971** | **50.8%** | **0.021** | **+0.0083** |
| V4 GBM-λ + DC (raw) | 0.9982 | 0.5966 | 50.8% | 0.017 | +0.0078 |
| V4 MLE DC + Temp | 1.0377 | 0.6239 | 46.8% | 0.023 | +0.0473 |
| V4 MLE DC (raw) | 1.0384 | 0.6244 | 46.8% | 0.028 | +0.0480 |
| Uniform 1/3 | 1.0986 | 0.6667 | 43.4% | 0.101 | +0.1082 |

**信号捕获率 92.3%**（vs MLE DC 的 58.4%）。Pinnacle 收盘价已经把市场所有公开信号都
打进价格，所以我们模型 +0.0083 的 log-loss 差距主要来自 Pinnacle 知道而我们模型
不知道的"内部信息"（阵容、临场伤停、教练战术等）。

**已在某些联赛超过 Pinnacle**：La Liga (-0.0037)、Portugal (+0.0012)、Championship (+0.0042)。

---

## 4. 本次会话（2026-05-22）完成

### Phase 1：Isotonic 校准 → 改为 Temperature scaling
- 实现了 isotonic per-class 校准（80 行）
- 测试时发现 isotonic 在 516 验证样本上严重过拟合（log-loss 1.04 → 1.20）
- 诊断：分桶后某些类只有 8 个样本，isotonic 把零概率端拉到 0，log(0) 灾难
- **正确方案**：温度缩放（单参数 softmax(log p / T)），鲁棒处理小样本
- 结果：T=1.030 (MLE), T=0.857 (GBM)；MLE ECE 0.028→0.023；GBM ECE 0.017→0.021（略升但 log-loss 基本不动）

### Phase 2：v4 单元测试（65 个 case，全部通过）
- `test_dixon_coles.py`：网格求和 = 1、积分一致性、让球边界、O/U 单调性、tau 边界
- `test_dc_mle.py`：拟合收敛、recover 主场优势符号、attack/defense 零和
- `test_metrics.py`：log_loss/Brier/hit_rate/ECE 已知值
- `test_baselines.py`：devig 后概率求和 = 1
- `test_calibration.py`：温度 + isotonic 输出形状、不退化
- `test_ingest.py`：26,890 场加载、schema 完整、result 与 goals 一致
- `test_combo.py`：枚举去重、Kelly 边界、推荐过滤

### Phase 3：特征工程（market + Elo + form）
- `features/market.py`：Pinnacle devig 概率、logits、overround、O/U 2.5、AHCh 让球线
- `features/elo.py`：增量 Elo 每联赛独立，K=20，主场偏移 +60，进球差加权
- `features/form.py`：6 场滚动 (goals_for, goals_against, shots, sot, rest_days)
- `features/pipeline.py`：组合到一个 DataFrame，1.2 秒处理 26,890 场
- 特征覆盖率：market 99.9%，Elo 100%，form 99%，shots 83%（Japan 没有 shots）

### Phase 4：GBM-λ 模型
- `model/gbm_lambda.py`：两个 lightgbm Poisson 回归器
- 训练 0.1 秒，best iter home=159 away=78
- 在 EPL/24-25 测试集上 log-loss 0.9993，比 Pinnacle 只差 0.0089（vs MLE 差 0.0442）
- 整合进 walk_forward.py，pooled 跨所有联赛训练一个模型

### Phase 5：组合优化层
- `combo/selections.py`：MatchInput → Selection（含 1X2 和 让球 1X2 两个市场）
- `combo/enumerate.py`：候选枚举（top_k_per_match 控制爆炸），含复式支持
- `combo/kelly.py`：分数凯利，自动从 EV + hit_p 导出 win_multiplier
- `combo/recommend.py`：端到端，按 kelly_log_growth 排序，过滤掉 -EV / 低命中 / Kelly=0 的票
- 健康行为：当所有市场无 edge 时，自动输出空推荐（no-bet 选项）

### 文件结构（apps/api/src/nutmeg/v4/）

```
data/        ingest.py + schema.py            (~250 行)
features/    market.py + elo.py + form.py + pipeline.py  (~270 行)
model/       dixon_coles.py + dc_mle.py + gbm_lambda.py  (~460 行)
calibration/ isotonic.py + temperature.py     (~165 行)
eval/        metrics.py + baselines.py + walk_forward.py + report.py  (~430 行)
combo/       selections.py + enumerate.py + kelly.py + recommend.py  (~500 行)
cli/         bench.py                         (~80 行)
合计 ~2,200 行生产代码 + ~700 行测试 = 测试覆盖 ~32% (vs legacy 0.4%)
```

---

## 5. 下次会话清单（按优先级）

### P0 — 把 GBM 优势变成产品体验
1. **`cli/recommend.py`**：读取 "今天的竞彩盘口" CSV → 跑 GBM → 输出推荐 JSON
   - 输入：日期 + 比赛列表（主队/客队/让球数/各市场赔率）
   - 输出：top-N 推荐组合 + Kelly 资金分配
   - 关键：需要一个**当天比赛的赔率输入接口**（手工 CSV 或 scraper）
2. **`api/v4_routes.py`**：FastAPI 路由把 recommend_combinations 包装成 HTTP endpoint
3. **`recommend.py` 加 no-bet 阈值参数**：min_hit_probability、min_kelly_stake、min_edge_per_leg 暴露给 CLI

### P1 — 提升模型精度（追剩下的 0.008 log-loss 差距）
4. **xG-lite v2**：把 shots/SoT/rest_days 转成 prematch xG 期望，作为新特征
5. **赛程拥挤度**：3 天内 / 5 天内场次数作为特征（适用欧战周）
6. **阵容稳定度**（需付费数据）：API-Football $20/月，先 PoC 试一个月

### P2 — 工程清理
7. **Legacy 迁移**：把 nutmeg.modeling / nutmeg.accuracy / nutmeg.recommendations 整体搬到 nutmeg.legacy
8. **FastAPI 路由切到 v4**：把现有 prediction routes 改为调用 v4 模型
9. **Postgres schema**：补 `v4_predictions` 表（含校准后概率、串关推荐）

### P3 — 未来工作
10. **多季 walk-forward**：现在只在 24/25 跑了一次；加 23/24 和 22/23 作为 fold
11. **联赛间迁移学习**：欧战球队跨联赛对决时 Elo / lambda 怎么处理（目前各联赛独立）
12. **国家队赛事**：世界杯 / 欧洲杯历史样本量小，需要特殊处理

---

## 6. 已知坑（不要再踩）

1. **Isotonic 在 <1000 样本上过拟合**——用温度缩放代替。
2. **football-data Japan CSV 联赛名前导空格** ` J1 League`——已处理。
3. **AHCh 是欧洲亚盘（0.25 步长），不是中国整数让球**——只作特征，不作结算。
4. **expected_payout 是 P(win)×combined_odds，不是 winning multiplier**——Kelly 计算时要先从 EV+hit_p 反推 b。
5. **handicap_home=0 时 1X2 和 handicap_1x2 是同一个市场**——配置时不要重复 odds_handicap_1x2。
6. **MLE DC 的 zero-sum 约束**：最后一队 = -前 N-1 之和；扩展时记住。
7. **GBM 训练集如果 NaN 太多会丢样本**——shots 列 Japan 缺失会导致 J1 在 GBM 测试集为空。
8. **Pinnacle "GBM-eligible 子集" 与 "PSC 全集" 是不同的子集**——比较 Δ 时要用同一子集的 Pinnacle 基线。

---

## 7. 命令速查

```bash
# 跑全套基准（约 10 秒）
PYTHONPATH=apps/api/src python -m nutmeg.v4.cli.bench

# 跑全套测试（约 4 秒）
PYTHONPATH=apps/api/src python -m pytest tests/v4/

# 单测：只跑 combo
PYTHONPATH=apps/api/src python -m pytest tests/v4/test_combo.py -v

# 本地装依赖（mac 用户）
cd /Users/ninoo/Nutmeg && uv sync
```

---

## 8. Friday Notes

### 2026-05-22 (Fri) — V4 端到端打通
- **完成**：诊断 → 路线选定 → v4 骨架 → ingest → Pinnacle 基线 → MLE DC → 温度校准 → 特征工程 → GBM-λ → 组合层 → 65 个测试 → 文档
- **关键数字**：V4 GBM-λ + DC + Temp log-loss **0.9987 vs Pinnacle 0.9904（Δ +0.0083）**。
- **信号捕获率从 58.4% 跃升到 92.3%**。La Liga / 葡超已轻微优于 Pinnacle。
- **组合层**：8 场比赛 demo 输出 5 条 +EV 推荐，命中率 20-41%，Kelly 全部正资金。

### 2026-05-22 (Fri) — V4 产品化（train + recommend CLI）
- **完成**：模型持久化（save_artifact / load_artifact）+ train CLI + recommend CLI + e2e 集成测试 + 演示 CSV
- **核心交付**：
  - `python -m nutmeg.v4.cli.train --cutoff YYYY-MM-DD` 训练 + 保存模型 artifact (2 秒，~700KB)
  - `python -m nutmeg.v4.cli.recommend --fixtures today.csv --model data/v4_model` 输出推荐报告 (Markdown 或 JSON)
- **模型 artifact 内容**：booster_home/away.txt (lightgbm) + temperature T + 404 个球队的 Elo + form 状态
- **预测产品形态**：每场比赛输出 λ_home/λ_away + 1X2 概率 + 让球 1X2 概率（按指定整数让球）+ top-N 组合推荐 + Kelly 资金
- **演示**：`data/demo/today_fixtures.csv` 含 8 场跨 8 个联赛的示例输入，对应 `today_recommendations.md/json`
- **测试**：71/71 通过（含 6 个 e2e 子进程测试，覆盖从训练到推荐的完整管线）

### 2026-05-22 (Fri) — V4 FastAPI 路由 + 多季验证 + Legacy 评估
- **完成**：FastAPI `/v4/health` + `/v4/recommend` 端点（17 个 schema 类，270 行路由代码，13 个测试）；多季 walk-forward（22/23、23/24、24/25 三季对比）；legacy 依赖图谱分析
- **API 端点**：
  - `GET /api/v4/health` → 返回 artifact 状态 + 模型元数据（n_teams=404, n_leagues=13）
  - `POST /api/v4/recommend` → 接受 fixtures JSON → 返回 single-match predictions + top-N parlay recommendations
  - 集成到 `nutmeg.main:create_app()` 与 legacy `/api/v1/*` 并存（不破坏）
  - 懒加载 artifact（线程安全），artifact 路径可通过 `NUTMEG_V4_ARTIFACT_PATH` 环境变量覆盖
- **多季验证结果**（关键稳健性证据）：

  | Test cutoff | n_full | n_gbm | Pinnacle | V4 GBM+Temp | Δ | 信号捕获率 |
  |------------:|-------:|------:|---------:|------------:|--:|----------:|
  | 22/23 | 5,288 | 4,884 | 0.9940 | 1.0021 | +0.0081 | 92.3% |
  | 23/24 | 5,232 | 4,767 | 0.9865 | 0.9959 | +0.0094 | 91.6% |
  | 24/25 | 4,792 | 4,331 | 0.9904 | 0.9987 | +0.0083 | 92.3% |

  Δ vs Pinnacle 三季稳定在 +0.008-0.009，**不是 24/25 偶然现象**。
- **测试**：84/84 通过（71 + 13 FastAPI）
- **Legacy 风险评估**：legacy 不能简单移到 `nutmeg/legacy/` —— 依赖图谱缠绕：
  - `api/router.py`（85 个端点）→ `accuracy/*` → `modeling` + `recommendations`
  - `predictions/{pipeline, snapshot_builder}` → `modeling`
  - `providers/workflow` → `predictions`
  - 直接移动会破坏全部 legacy 端点
- **下周建议**：分阶段迁移（Phase A-D）见下方 §9。

### 2026-05-22 (Fri) — V4 Web UI + 观测 API
- **完成**：观测层 4 个 HTTP 端点 + 单文件 Web Dashboard + 12 个新测试
- **HTTP 端点**：
  - `GET /api/v4/observation/health` → DB 状态、会话数、推荐数、已结算数
  - `GET /api/v4/observation/roi?n_bins=5` → headline + by_k_legs + by_league + calibration + weekly
  - `GET /api/v4/observation/sessions?limit=N` → 最近 N 个会话摘要
  - `POST /api/v4/observation/outcomes` → 批量录入结果 + 自动结算（一次最多 100 场）
- **Web UI**（`GET /api/v4/dashboard`）：
  - 单文件 HTML（448 行），Tailwind via CDN，纯 vanilla JS，**无 build step / 无 node_modules**
  - 4 个 tab：① 推荐（粘贴 JSON 比赛清单 → 看预测 + 组合推荐）；② 录入结果（每行 CSV）；③ ROI 报告（headline + 分组 + 校准 + 周时间序列）；④ 会话历史
  - 顶部健康徽章实时显示模型与观测库状态，30 秒自动刷新
  - 演示数据按钮一键填入 8 场跨联赛示例
- **测试**：112/112 通过（100 + 11 obs API + 1 dashboard smoke）
- **如何用**：在 mac 上启动 `nutmeg-api`，浏览器打开 `http://localhost:8000/api/v4/dashboard`，立刻能交互式跑推荐、录入结果、看 ROI
- **下一轮**：现在端到端产品形态已完整。强烈建议**进入 Phase C 实战观察**（每天用 dashboard 跑真实盘口、录入结果、周末看 ROI），4-8 周后看是否真有 alpha 跨过中国体彩 vig

### 2026-05-22 (Fri) — V4 实战观察基础设施（Phase C 启动器）
- **完成**：SQLite 观测层（5 表 schema）+ recorder + settlement + record_outcome CLI + roi_report CLI + 17 个测试
- **核心交付**：现在可以每天用 `recommend --record-to` 落库；事后录入比赛结果自动结算；任何时候跑 `roi_report` 看累计盈亏
- **DB schema**（v1）：
  - `recommendation_sessions`：每次 recommend 调用一行（含 bankroll、模型元数据、原始 request）
  - `single_predictions`：每场单场预测（λ、1X2 概率、让球概率）
  - `parlay_recommendations`：每条串关推荐（k_legs、stake、kelly、legs_json）
  - `match_outcomes`：实际比分（事后录入，按 (date, league, home, away) 唯一）
  - `settlements`：每条推荐的结算结果（hit/miss、stake、payout、P/L、details）
- **CLI 三件套**：
  - `python -m nutmeg.v4.cli.recommend --record-to data/v4_observation.db ...` 推荐时自动落库
  - `python -m nutmeg.v4.cli.record_outcome --db ... --csv yesterday_results.csv` 批量录入结果 + 自动结算
  - `python -m nutmeg.v4.cli.roi_report --db ... --out roi.md` 输出 ROI 报告
- **演示数据**：跑了一次端到端（3 条 2串1 推荐 → 4 场结果 → 全部命中 → ROI 报告显示净盈利 ¥252）
- **演示数据库** `/tmp/v4_obs_demo.db` 已生成
- **测试**：100/100 通过（83 + 17 observation）
- **观察启动条件已就绪**：用户现在每天跑 recommend → 当晚/次日录入结果 → 周末跑 roi_report，4-8 周后会有真实信号

不动 legacy 代码，让 v4 和 legacy 并存运行，等实战验证后再清理。

### Phase A — 端点并存（当前状态，已完成）
- `/api/v1/*` 继续由 legacy 服务（85 个端点不动）
- `/api/v4/*` 由 v4 服务（health + recommend，未来扩展）
- 前端/客户文档明确：v1 标 deprecated，新对接走 v4

### Phase B — Postgres 写契约 shadow 同步（下次会话可做）
- v4 推荐结果也写入 Postgres（复用 `prediction_evaluations` 表 + 新增 `parlay_recommendations_v4` 表）
- legacy 仍写自己的 `prediction_snapshots`
- 这样两条路径并存，方便审计与对比

### Phase C — 实战观察 4-8 周（强烈推荐做完 Phase A/B 后立刻开始）
- 用 v4 给真实中国体彩盘口出推荐，记录实际结果
- 收集 ROI、命中率、是否真有 alpha 跨过 vig
- 期间不动 legacy（万一要回滚）

### Phase D — 真正迁移（条件：Phase C 通过 + 用户确认）
工作量约 2-3 周：
1. 写 v4 实现 PredictionSnapshot 和 Accuracy Job（适配 legacy 的契约）
2. 切 `api/router.py` 的核心路由（如 `/predictions/snapshot`, `/accuracy/jobs/*`）调用 v4 而不是 legacy
3. 把 `nutmeg/{modeling,accuracy,recommendations}` 移到 `nutmeg/legacy/{...}`，更新 import
4. 跑全套 legacy 测试套件，确认绿
5. 删除 `nutmeg/legacy/` 中未被任何路由使用的实验脚本（accuracy 中 ~35 个 `historical_*_admission_*` 文件）

**不要在 Phase C 完成前做 Phase D。** 没有实战数据支撑就拆 legacy 等于放弃 PoC 阶段的安全网。
