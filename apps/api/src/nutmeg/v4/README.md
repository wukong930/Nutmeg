# Nutmeg V4 — 清洁重构

V4 是 Nutmeg 预测管线的从零重构，**0 行依赖** legacy `nutmeg.modeling` /
`nutmeg.accuracy` / `nutmeg.recommendations`。

## 一句话现状

V4 GBM-λ + DC + Temp 模型 log-loss **0.9987**，比 Pinnacle 收盘价（市场天花板）
只差 **0.0083**，**捕获 92.3% 可提取信号**。已在某些联赛轻微优于 Pinnacle。

## 设计原则

1. **真训练，不是启发式**：scipy.optimize MLE 拟合 Dixon-Coles；lightgbm Poisson 训练 λ。
2. **Pinnacle 收盘价是硬基线**：所有模型必须在同一份 walk-forward 测试集上报 Δ。
3. **比分矩阵是内部对象**：9×9 score grid 是 universal object，1X2 / 让球 1X2
   / 大小球 / 比分都从 grid 积分得到——新增市场不需要新模型。
4. **校准被应用**：温度缩放嵌入 predict 流程，不只是写报告。
5. **组合层按 Kelly 对数增长排序**：避免 EV 排序产生的"全 Away 长尾票"。

## 目录

```
v4/
├── data/
│   ├── schema.py           # 规范 match 列定义
│   └── ingest.py           # football-data.co.uk CSV → DataFrame
├── features/
│   ├── market.py           # Pinnacle devig + AH 让球线 + O/U 隐含概率
│   ├── elo.py              # 增量 Elo per 联赛，含主场偏移
│   ├── form.py             # 6 场滚动 (goals, shots, rest_days)
│   └── pipeline.py         # 组合到一个 DataFrame
├── model/
│   ├── dixon_coles.py      # score grid 数学 + 1X2/让球/大小球积分
│   ├── dc_mle.py           # scipy MLE 拟合 attack/defense/home_adv/rho
│   └── gbm_lambda.py       # 两个 Poisson lightgbm 回归器
├── calibration/
│   ├── temperature.py      # 1-参数 softmax(log p / T)，小样本鲁棒
│   └── isotonic.py         # per-class，等 5k+ 验证样本再启用
├── eval/
│   ├── metrics.py          # log-loss / Brier / hit-rate / ECE
│   ├── baselines.py        # Pinnacle / Bet365 / avg-market / uniform 基线
│   ├── walk_forward.py     # 跨联赛汇总的训练-验证-测试切分
│   └── report.py           # Markdown 对比卡片
├── combo/
│   ├── selections.py       # 单场 → MatchInput + Selection（含 edge）
│   ├── enumerate.py        # 2-8 串 1 候选枚举（含复式）
│   ├── kelly.py            # 分数凯利（自动从 EV+hit_p 导出 b）
│   └── recommend.py        # 端到端：matches → 推荐（按对数增长排序）
└── cli/
    └── bench.py            # `python -m nutmeg.v4.cli.bench`
```

## 快速跑

```bash
cd /Users/ninoo/Nutmeg && uv sync

# 1) 跑全套 walk-forward benchmark（与 Pinnacle 比较）
PYTHONPATH=apps/api/src python -m nutmeg.v4.cli.bench

# 2) 训练 + 保存 v4 模型 artifact（~2 秒）
PYTHONPATH=apps/api/src python -m nutmeg.v4.cli.train \
  --cutoff 2025-06-01 \
  --out data/v4_model

# 3) 用训练好的模型对当天比赛输出推荐 + 落库到观测 DB
PYTHONPATH=apps/api/src python -m nutmeg.v4.cli.recommend \
  --fixtures data/demo/today_fixtures.csv \
  --model data/v4_model \
  --bankroll 1000 \
  --top-n 5 \
  --record-to data/v4_observation.db \
  --out data/demo/today_recommendations.md

# 4) 比赛结束后录入结果（自动结算所有已记录的推荐）
PYTHONPATH=apps/api/src python -m nutmeg.v4.cli.record_outcome \
  --db data/v4_observation.db --csv yesterday_results.csv

# 5) 任何时候查看累计 ROI 报告
PYTHONPATH=apps/api/src python -m nutmeg.v4.cli.roi_report \
  --db data/v4_observation.db --out docs/roi.md

# 6) 跑全套单元测试（100 cases）
PYTHONPATH=apps/api/src python -m pytest tests/v4/
```

## 当天输入 CSV 格式

每行一场比赛，必填字段：`date, league, home_team, away_team, psc_home, psc_draw, psc_away`（Pinnacle 收盘价作为模型输入）。

可选字段：`handicap_home`（中国整数让球数）+ `odds_handicap_H/D/A` 启用让球市场；`odds_1x2_H/D/A` 用户实际下注的彩票赔率（如果与 PSC 不同）；`psc_over25, psc_under25, ahch` 作为额外特征。

示例见 `data/demo/today_fixtures.csv`，对应输出见 `data/demo/today_recommendations.md`。

## HTTP API

V4 也通过 FastAPI 暴露 HTTP 接口（挂载在 `/api/v4/*`）：

```bash
# 启动 server（自动加载 data/v4_model artifact；artifact 路径可通过
# NUTMEG_V4_ARTIFACT_PATH 环境变量覆盖）
cd /Users/ninoo/Nutmeg && PYTHONPATH=apps/api/src nutmeg-api

# 健康检查
curl http://localhost:8000/api/v4/health

# 推荐
curl -X POST http://localhost:8000/api/v4/recommend \
  -H 'Content-Type: application/json' \
  -d '{
    "fixtures": [
      {"date": "2025-08-17", "league": "EPL",
       "home_team": "Arsenal", "away_team": "Liverpool",
       "psc_home": 2.85, "psc_draw": 3.40, "psc_away": 2.60}
    ],
    "bankroll": 1000.0,
    "top_n": 5
  }'
```

完整 schema 见 `nutmeg/v4/api/schemas.py`。所有可选过滤参数（`min_hit_probability`、`min_kelly_stake`、`kelly_fraction`、`include_compound` 等）都在 `RecommendRequest`。

## 多季稳健性（2026-05-22）

V4 在 3 个独立测试赛季上信号捕获率都稳定在 91.6%–92.3%：

| Test cutoff | Pinnacle | V4 GBM+Temp | Δ | 信号捕获率 |
|------------:|---------:|------------:|--:|----------:|
| 22/23 | 0.9940 | 1.0021 | +0.0081 | 92.3% |
| 23/24 | 0.9865 | 0.9959 | +0.0094 | 91.6% |
| 24/25 | 0.9904 | 0.9987 | +0.0083 | 92.3% |

详见 `docs/v4_multi_season_card.md`。

## 当前 baseline（2026-05-22）

24/25 测试赛季、13 联赛、4,331 场（GBM-可用样本）：

| Model | log-loss | hit-rate | ECE |
|-------|---------:|---------:|----:|
| Pinnacle 收盘 | 0.9904 | 51.2% | 0.012 |
| **V4 GBM-λ + DC + Temp** | **0.9987** | **50.8%** | **0.021** |
| V4 MLE DC + Temp | 1.0377 | 46.8% | 0.023 |
| Uniform 1/3 | 1.0986 | 43.4% | 0.101 |

详见 `docs/v4_baseline_card.md`（每次跑 bench 自动更新）。

## 下一步

详见 `docs/V4_HANDOFF.md` §5 "下次会话清单"。最优先：

1. `cli/recommend.py`：读"今日竞彩盘口"输入，输出推荐 JSON
2. `api/v4_routes.py`：FastAPI HTTP 接口
3. xG-lite v2 特征 + 阵容数据接入（追剩余 0.008 log-loss）
