# Nutmeg 项目介绍报告

_生成时间: 2026-05-26 · 基于 commit `fecd32f`，1493 V4 测试全绿_

---

## 1. 一句话定位

**Nutmeg 是面向中国体彩竞彩足球的端到端预测+推荐+观测系统**：从 14 个联赛的实时盘口入库，到 Dixon-Coles + CatBoost 双层概率模型，到 ¥2 起投/¥20k 上限的竞彩规则推荐，再到 SQLite 观测库 + 4 周 ROI 验证闭环，全部在一个 Python repo 里 self-contained 跑完。

---

## 2. 项目背景与解决的问题

### 2.1 用户问题

普通竞彩玩家面对的核心矛盾：
- **盘口知识不足**：不会区分开盘/闭盘价、不知道 Pinnacle 与 vig
- **概率直觉差**：肉眼判 1X2 的命中率约 35%（盲猜 33%），让球更不可控
- **下注尺度失控**：没有 Kelly 框架，凭感觉押注，长期 ROI 必为负
- **缺乏跟踪闭环**：下完单就忘记结果，3 个月后说不清自己是赚是赔

### 2.2 Nutmeg 提供的解决

1. **概率层**：CatBoost-lambda + Dixon-Coles 联合给出 9×9 比分网格 → 1X2 + 让球任意线的真实命中率
2. **市场对照**：Pinnacle 盘口去 vig 后作为先验，Bayesian 融合避免过度自信
3. **决策层**：竞彩规则集成（¥2 单位、单注上限、5% EV 门槛、Kelly 分数）+ 单关/串关/复式三种玩法
4. **观测层**：每次推荐落库 → 比赛结束后自动结算 → 4 周后输出真实 ROI 报告 → 模型迭代闭环

---

## 3. 历史演进（V4 → V11 共 8 个 ship version）

| Version | Ship 日期 | 主轴 | 关键交付 |
|---|---|---|---|
| **V4** (baseline) | 2025-Q3 | 基础 ML pipeline | LightGBM-λ + DC 网格 + parlay recommender |
| **V5** | 2025-Q4 | 工程瘦身 + ML 升级 | 304→50 文件、CatBoost 接入并切默认、CI、weekly bench cron |
| **V6** | 2026-Q1 | 中国竞彩产品化 | 单关/串关/复式 3 玩法 + API-Football 阵容 + 规则固化 |
| **V7** | 2026-Q2 前 | 运营自动化 | `nutmeg-ingest-odds` + `auto-settle` + `weekly-report` 全 cron 化 |
| **V8** | 2026-Q2 | 杯赛+国家队基建 | Cup features + cross-league seeding + 68 国家 Elo + 单关/复式 API |
| **V9** | 2026-Q3 前 | 校准+ROI 验证 | bucket-decomp ECE audit + isotonic/T 校准 ablation |
| **V10** | 2026 春 | WC 2026 准备 | 国家队模型 + WC predict/settle/report 全链 + 自校准 Layer A |
| **V11** | 2026-05 | 用户体验 + Layer B | 中文名/logo/i18n/PWA + 季度自训 + Path A++ WC 让球 |

**统计**: 52 git tags, 121 commits, 8 个 `vX.0-shipped` + 33 weekly + 11 milestone tags。

---

## 4. 整体架构

### 4.1 物理布局

```
nutmeg/                           ← repo root (~26.7k LoC code + 5.5k tests)
├── apps/api/
│   ├── Dockerfile                ← 草稿（未上线）
│   └── src/nutmeg/
│       ├── main.py               ← FastAPI app factory
│       └── v4/                   ← 唯一的 production 命名空间
│           ├── api/              ← FastAPI routes + dashboard 静态
│           ├── calibration/      ← isotonic + temperature + per-league
│           ├── cli/              ← 33 个 CLI 命令
│           ├── combo/            ← 单关/串关/复式 + Kelly + 竞彩规则
│           ├── data/             ← 14 联赛数据层 + sources 适配器
│           ├── eval/             ← walk-forward + bucket-decomp + bench
│           ├── features/         ← elo/form/lineup/market/cup/xg-lite
│           ├── model/            ← LightGBM/CatBoost/XGBoost + DC + NT
│           └── observation/      ← SQLite 观测库 + auto-settle + ROI + Layer B
├── tests/v4/                     ← 82 测试文件, 1493 测试
├── scripts/                      ← 7 个 shell 工具脚本
├── data/                         ← 数据资产（部分 gitignored）
├── docs/                         ← 7,500+ 行文档（8 HANDOFF + 5 retrospective）
└── .github/workflows/            ← 5 个 CI workflow
```

### 4.2 运行时分层

```
┌──────────────────────────────────────────────────────┐
│  用户 Browser (PWA, i18n zh/en, dark mode, 9 tabs)   │
└─────────────────┬────────────────────────────────────┘
                  │ HTTP
┌─────────────────▼────────────────────────────────────┐
│  FastAPI (uvicorn) — 22 endpoints                    │
│  • /v4/dashboard (PWA shell)                         │
│  • /v4/today-recommendations  (default landing)      │
│  • /v4/recommend{,/single,/pool,/wc/single}          │
│  • /v4/predictions/{upcoming,wc}                     │
│  • /v4/observation/*  (sessions, ROI, history)       │
│  • /v4/rules, /v4/health, /v4/team-logo/*            │
└─────────┬──────────────┬─────────────┬───────────────┘
          │              │             │
   ┌──────▼──────┐ ┌─────▼────┐ ┌─────▼────────┐
   │ ML pipeline │ │ Combo    │ │ Observation  │
   │             │ │ engine   │ │              │
   │ CatBoost-λ  │ │ Kelly    │ │ SQLite       │
   │ Dixon-Coles │ │ JINGCAI  │ │ ab-report    │
   │ NT model    │ │ 单/串/复 │ │ Layer A      │
   └─────────────┘ └──────────┘ │ Layer B      │
                                └──────────────┘
                                        ▲
                                        │ launchd cron
                  ┌─────────────────────┴────────────┐
                  │  7 daily/weekly jobs             │
                  │  14:00 ingest_odds → CSV         │
                  │  15:00 recommend → record        │
                  │  Sun 02:00 settle + ab-report    │
                  │  Sun 04:00 live-vs-backtest gate │
                  │  Mon 03:00 auto-calibration      │
                  │  09:00 WC predict (tournament)   │
                  │  02:00 WC settle (tournament)    │
                  └──────────────────────────────────┘
```

---

## 5. 技术栈

### 5.1 核心依赖（pyproject.toml）

| 类别 | 包 | 用途 |
|---|---|---|
| **API** | FastAPI 0.115+, pydantic 2.8+, uvicorn | HTTP 框架 + 数据校验 |
| **DS 核心** | pandas 2.2+, numpy 2.0+, scipy 1.13+, scikit-learn 1.5+ | 数据处理 + 经典 ML |
| **GBM** | LightGBM 4.5+, CatBoost 1.2.10+, XGBoost 3.2.0+ | 3 backends, CatBoost 是 production |
| **存储** | DuckDB 1.0+, PyArrow 16+, SQLite 3 (stdlib) | parquet + 观测库 |
| **网络** | httpx 0.27+, tenacity 8.5+ | API 重试 + 抓取 |
| **配置** | python-dotenv 1.2+, pydantic-settings 2.4+ | .env 集成 |
| **特殊** | understat, pyreadr, beautifulsoup4 | 数据源适配器 |

### 5.2 开发依赖

mypy + ruff + pytest 8.2 + Playwright + axe-core（E2E + WCAG）

### 5.3 运行环境

- Python 3.12+（实际 3.13.13）
- macOS launchd（current production）/ Linux systemd（未来 VPS）
- 训练继续在本地 Mac（avoid 1.5 GB peak RAM）

---

## 6. 核心模块详解

### 6.1 `v4/data/` — 数据层（22 文件，4177 LoC）

**职责**：所有外部数据进入系统的统一入口。

| 子模块 | 内容 |
|---|---|
| `sources/api_football.py` | API-Football 适配器（含 .env token + 14 联赛 ID 映射） |
| `sources/odds_api.py` | The Odds API 适配器（V11 backlog #20 + Pinnacle 杯赛） |
| `sources/understat.py` | xG-lite 历史数据抓取（V5 W3） |
| `sources/clubelo.py` | 俱乐部 Elo 评分（V5 W4） |
| `eloratings.py` | 国家队 Elo (68 国家, V8 W7) |
| `competitions.py` | 14 联赛 + 12 杯赛 + WC/EURO 注册表 |
| `team_canonical.py` | 跨数据源队名规范化（含杯赛别名 43 entries） |
| `team_name_zh.py` | 355 中文队名 lookup table |
| `cup_training.py` | 跨联赛训练数据构造（V8 W2） |
| `wc_training_frame.py` | WC 2018+2022 训练帧（128 场） |
| `lineup_lookup_builder.py` | 阵容索引构造（V6 W7） |

### 6.2 `v4/features/` — 特征工程（13 文件，2269 LoC）

| 模块 | 特征 |
|---|---|
| `elo.py` | 队 Elo 差 + home_adv |
| `form.py` | 过去 N 场 GF/GA/SOT + cross-league seeding（V8 W3） |
| `xg_lite.py` | shots / SOT 简化版 xG（V5 W4） |
| `clubelo_features.py` | 外部俱乐部 Elo 注入 |
| `lineup_features.py` | 阵容缺席 + recent_n_injuries（V6 W5-W7） |
| `market.py` | 市场 dewedge + over 2.5 + ahch handicap line |
| `market_dynamics.py` | 开盘→闭盘漂移信号（V5 W5） |
| `cup_features.py` | 杯赛 cross-league signals（V6 W11） |
| `stadium_features.py` | ⚠️ 死码 — 写了但未接入训练 |
| `fatigue_features.py` | ⚠️ 死码 — 写了但未接入训练 |

### 6.3 `v4/model/` — ML 模型（10 文件，1891 LoC）

| 模块 | 角色 |
|---|---|
| `persist.py` | `V4Artifact` 加载/保存 + `build_features_for_fixtures` + `predict_lambdas` |
| `lgb_lambda.py` | LightGBM Poisson regression for λ_home/λ_away（V4 baseline） |
| `cat_lambda.py` | CatBoost Poisson 同上（V5 W7 production） |
| `xgb_lambda.py` | XGBoost backup（V5 W6） |
| `stacker.py` + `ensemble.py` | Multi-model stacking（V5 W6 ablation） |
| `dixon_coles.py` | 9×9 score grid + tau correction + 1X2/handicap projection |
| `national_team.py` | LightGBM 3-class WC 1X2（V10 W1 Track B） |
| `national_team_predict.py` | Elo + market_implied + bayesian_blend |
| **`national_team_handicap.py`** | **Path A++ hybrid 让球（V11 post-ship 本会话）** |

### 6.4 `v4/combo/` — 推荐引擎（8 文件，1187 LoC）

| 模块 | 内容 |
|---|---|
| `selections.py` | 6 候选 (3 1X2 + 3 handicap) per match |
| `enumerate.py` | 串关 C(M,k) 枚举 + 复式 atomic combos |
| `kelly.py` | Fractional Kelly + cap + ¥2 quantize |
| `lottery_rules.py` | **JINGCAI_DEFAULT**: stake_unit=¥2, max=¥20k, vig=31.5%, min_ev=5%, max_legs=8 |
| `single_match.py` | 单关 recommender (V8 W6) |
| `compound_pool.py` | 复式 pool recommender (V6 W3) |
| `recommend.py` | 串关 main entry + threshold filtering |

### 6.5 `v4/observation/` — 观测层（11 文件，3493 LoC）

| 模块 | 内容 |
|---|---|
| `store.py` | SQLite schema: `recommendation_sessions` / `single_predictions` / `parlay_recommendations` / `match_outcomes` / `settlements` |
| `recorder.py` | 4 个录入入口: `record_session` (parlay) / `record_single_session` / `record_pool_session` / **`record_wc_handicap_session`** |
| `settlement.py` | 比分 → handicap_1x2 → hit + payout + profit_loss |
| `live_vs_backtest.py` | P1#19 跨源 ROI 对比 gate |
| `wc_log.py` | WC-specific predictions table（V10 W4）+ **`settle_wc_prediction` 现在双写 match_outcomes**（V11 post-ship）|
| `auto_calibration.py` | **Layer A**: 每周读最近 8 周 settled 数据 → 提议新 T → 部署/回滚 (V10 W2) |
| `auto_retrain.py` | **Layer B**: 季度提议新 artifact + walk-forward gate (V11 backlog #4) |
| `bucket_decomp.py` | ECE audit per-bucket (V9 W5) |
| `recommendation_version.py` | Selection fingerprint + diff（V11 P1-FE#5） |

### 6.6 `v4/api/` — HTTP 层（4 文件，3135 LoC）

| 文件 | 内容 |
|---|---|
| `routes.py` (1855 LoC) | 主要 endpoints + dashboard 静态服务 + PWA SW |
| `observation_routes.py` (607) | 5 个观测/历史 endpoints |
| `schemas.py` (658) | 30 个 Pydantic 模型（请求/响应） |
| `static/dashboard.html` (~3000) | 单文件 PWA + i18n zh/en |

### 6.7 `v4/eval/` 和 `v4/calibration/`

- **eval/walk_forward.py**: rolling 8-week forward backtest
- **eval/bench.py**: 单季 benchmark
- **eval/multi_season_bench.py**: 4 季 ablation
- **calibration/isotonic.py + temperature.py**: post-hoc 校准
- **calibration/per_league.py**: 按联赛 T 校准

### 6.8 `v4/cli/` — 33 个用户命令（8057 LoC）

| 类别 | 命令（节选） |
|---|---|
| **数据 ingest** | `nutmeg-ingest-external`, `ingest-odds`, `ingest-lineups`, `ingest-cup-history`, `ingest-cup-odds`, `ingest-national-elo`, `ingest-team-logos` |
| **训练 + 评估** | `nutmeg-train`, `bench`, `bench-multi`, `walk-forward`, `cup-ablation`, `ece-audit`, `cat-calibration-ablation` |
| **推荐** | `nutmeg-rec` (互动), `recommend` (parlay), `recommend-pool` (复式), `rec` |
| **WC** | `wc-predict`, `wc-settle`, `wc-report` |
| **观测+结算** | `auto-settle`, `record-outcome`, `ab-report`, `roi-report`, `weekly-report`, `live-vs-backtest` |
| **自动化** | `auto-calibration`, `auto-retrain`, `experiment-diff` |
| **维护** | `canonical-report-cup`, `refresh-lineups` |
| **API** | `nutmeg-api` (uvicorn launcher) |

---

## 7. 数据流与 ML pipeline

### 7.1 训练时数据流

```
External data sources
├── football-data.co.uk CSV (5 联赛历史)
├── API-Football (14 联赛 fixtures + lineups + injuries)
├── The Odds API (杯赛 Pinnacle backfill)
├── clubelo.com (Elo)
├── understat.com (xG-lite)
└── eloratings.com (68 国家队 Elo)
        │
        ▼
data/external/*.parquet   (ingest_external + ingest_lineups + 等)
        │
        ▼
build_features_for_fixtures(artifact, df)
  ├── build_market_features        (market.py)
  ├── build_market_dynamics        (market_dynamics.py)
  ├── build_elo_features           (elo.py + cross-league seeding)
  ├── build_form_features          (form.py)
  ├── build_clubelo_features       (clubelo_features.py)
  ├── build_lineup_features        (lineup_features.py, opt-in)
  └── build_cup_features           (cup_features.py, opt-in)
        │
        ▼
λ_home, λ_away  (CatBoost Poisson)
        │
        ▼
score_grid(λ_h, λ_a, ρ=-0.10)  →  9×9 比分概率矩阵 (Dixon-Coles)
        │
        ├── grid_to_1x2          → P(H/D/A)
        ├── grid_to_handicap_1x2 → P(H/D/A | line)
        └── grid_to_over25       → P(over/under 2.5)
```

### 7.2 推荐时数据流

```
今日 fixtures + Pinnacle closing odds (CSV from ingest_odds)
        │
        ▼
predict_lambdas → score_grid → (3 markets × 6 candidates per match)
        │
        ▼
build_selections_from_match → Selection(odds, probability, edge)
        │
        ▼
passes_recommendation_thresholds   (EV ≥ 5%, hit_p ≥ 5%)
        │
        ▼
combo engine
├── 单关 (single_match.py): max-EV per fixture
├── 串关 (recommend.py):   C(M, k=2..8) 枚举, Kelly weighted
└── 复式 (compound_pool.py): M-select-N atomic combos
        │
        ▼
fractional_kelly_stake + cap_ticket_stake + quantize_stake (¥2)
        │
        ▼
SingleTicket / Parlay / PoolTicket
        │
        ▼ if record_session=True
record_session(db) → recommendation_sessions + parlay_recommendations + single_predictions
```

### 7.3 观测与结算

```
比赛结束 → API-Football 返回 home_goals/away_goals
        │
        ▼
auto-settle (nutmeg-auto-settle 或 weekly cron)
  └── upsert_outcome(match_outcomes)
        │
        ▼
settle_unsettled(db)
  └── 对每个 parlay_recommendation:
       resolve_leg_atomic_outcomes(leg, outcomes_by_match)
       compute hit/payout/profit_loss
       insert_settlement(rec_id, ...)
        │
        ▼
ab-report --weeks 4
  └── 按 model_type 分组 + per-week ROI + 累计 stake/return
```

---

## 8. 关键算法与特色功能

### 8.1 Dixon-Coles 比分网格

```python
score_grid(λ_h, λ_a, ρ=-0.10, max_goals=10) → 9×9 ndarray
```

- `pmf_h[i] × pmf_a[j]` 给独立 Poisson 联合分布
- 低分修正 (DC tau correction): `grid[0,0] *= (1 - λ_h·λ_a·ρ)`、`grid[0,1] *= (1 + λ_h·ρ)`、`grid[1,0] *= (1 + λ_a·ρ)`、`grid[1,1] *= (1 - ρ)`
- 截断后重新归一

### 8.2 让球结算

```python
_outcome_handicap_1x2(hg, ag, handicap_home):
  diff = (hg + handicap_home) - ag
  return 'H' if diff > 0 else 'A' if diff < 0 else 'D'
```

整数让球 → 让胜/让平/让负，3 个独立 outcome。

### 8.3 Bayesian Blend

```python
final = α × p_model + (1 - α) × p_market_implied
```

α 默认 0.4（域 0-1）：
- α=1 纯模型（过度自信，bench 表现差）
- α=0 纯市场（无价值）
- α=0.4 = WC ship 时 walk-forward 找到的甜蜜点

### 8.4 Path A++ WC 让球（本会话 ship）

WC 训练集只有 128 场，直接训 Poisson 模型会过拟合。设计：

```
NationalTeamModel (LightGBM 3-class) → 1X2
        ↓
Bayesian blend with Pinnacle 1X2 (α=0.4)
        ↓
Reverse-map 1X2 → (λ_h, λ_a) via KL minimization
  with λ_total fixed at WC mean ~2.6
        ↓
DC score_grid + grid_to_handicap_1x2
        ↓
Blend model HC with market HC dewedge (α=0.4)
        ↓
Kelly + EV gate → ¥2-quantized stake
```

### 8.5 Fractional Kelly

```python
f* = (p·b - q) / b   where b = odds - 1, q = 1 - p
recommended = bankroll × min(f* × kelly_fraction, max_stake_fraction)
capped = cap_ticket_stake(recommended, JINGCAI_DEFAULT)
quantized = quantize_stake(capped, ¥2)
```

默认 `kelly_fraction = 0.25` (保守 1/4 Kelly)，`max_stake_fraction = 0.05`（单注不超过 bankroll 5%）。

### 8.6 Risk Preference Dial（V11 P1-FE#4）

用户面对的高层旋钮 → 内部映射：

| 用户选项 | kelly_fraction | min_ev | 行为 |
|---|---|---|---|
| 保守 | 0.15 | +5% | 严格 EV 门槛 + 低 Kelly |
| 中（默认） | 0.25 | +5% | Pinnacle 风格 |
| 激进 | 0.40 | +5% | 更高 Kelly，需要更高 hit_p |

---

## 9. 中国竞彩规则集成

`combo/lottery_rules.py::JINGCAI_DEFAULT`:

| 字段 | 值 | 含义 |
|---|---|---|
| `stake_unit` | ¥2 | 最小投注单位 |
| `max_ticket_stake` | ¥20,000 | 单注上限 |
| `max_period_stake` | ¥200,000 | 单期上限 |
| `min_parlay_legs` | 2 | 串关下限 |
| `max_legs_per_ticket` | 8 | 串关上限（4×1 / 8 串 1 等） |
| `payout_ratio` | 0.685 | 中国体彩平均派奖率 |
| `vig` | 0.315 | 31.5% 庄家抽水 |
| `min_ev_per_unit` | 0.05 | 推荐门槛 +5% EV |
| `min_hit_probability` | 0.05 | 推荐门槛 hit-p 5% |

**所有推荐都通过这套规则过滤** — 如果计算出来 EV < 5%，无论 model 多么自信都不出推荐。

---

## 10. 观测系统与 A/B（V6 W8 + V8 + V9 W3）

### 10.1 SQLite 表结构（schema_meta v2）

```
recommendation_sessions(
  session_id, bankroll, model_cutoff, model_trained_at,
  model_type,  ← post-V11 audit fix 2026-05-26
  n_fixtures, n_recommendations, snapshot_phase,
  request_json, metadata_json, created_at
)

single_predictions(
  session_id, match_date, league, home_team, away_team,
  lambda_home, lambda_away, p_home_1x2, p_draw_1x2, p_away_1x2,
  handicap_home, p_home_handicap, p_draw_handicap, p_away_handicap
)

parlay_recommendations(
  rec_id, session_id, rank, k_legs, is_compound,
  stake_units, kelly_stake, expected_return,
  hit_probability, ev_per_unit, log_growth, legs_json
)

match_outcomes(
  match_date, league, home_team, away_team, home_goals, away_goals, recorded_at
)  -- WC outcomes ALSO live here since 2026-05-26 bridge

settlements(
  settle_id, rec_id, hit, stake, actual_payout, profit_loss, details_json
)

wc_predictions(...)  -- separate journal for WC 1X2
```

### 10.2 录入双门 (V9 W3)

```python
def _should_record_session(req_record_flag: bool) -> Optional[str]:
    # Both gates required:
    if not req_record_flag:
        return None
    return os.environ.get("NUTMEG_V4_OBSERVATION_DB")
```

- **环境**: `NUTMEG_V4_OBSERVATION_DB=data/v4_observation.db`（服务器 opt-in）
- **请求**: `record_session=True`（per-session opt-in，dashboard checkbox）

两者同时 on 才落库。

### 10.3 A/B 报表

`nutmeg-ab-report --weeks 4 --db data/v4_observation.db --model-type catboost`

按 `model_type` 分组：每周的 stake / payout / profit / ROI%，跨臂对比（V5 W12 catboost vs V6 W7 lineup-aware）。

---

## 11. 自校准（Layer A + Layer B）

### 11.1 Layer A — 每周 T 微调（V10 W2）

```
每周一 03:00 cron:
  1. 读最近 8 周 settled recommendations
  2. 计算当前 deployed live_T_correction.json 的实测 log-loss
  3. 如果 worse than identity by > 0.003 → auto-rollback (删除 correction file)
  4. 否则提议新 T （per-league × per-market）→ 写到 weekly journal
  5. 用户读 Monday morning 报告手工 ship 或忽略
```

### 11.2 Layer B — 季度自训(V11 backlog #4)

```
每季度边界 (Q1/Q4 切换、4-1、7-1、10-1) cron:
  1. nutmeg-auto-retrain --action propose
  2. 用最新数据训新 artifact
  3. 跑 walk-forward gate vs production
  4. 写 docs/quarterly/retrain_<YYYY>Q<N>.md
  5. 用户手工 review → --action deploy 或忽略
  6. Deploy 后 4 周观察期 + Layer A 自动监控
```

---

## 12. 前端 Dashboard

### 12.1 单文件 PWA

`apps/api/src/nutmeg/v4/api/static/dashboard.html`（~3000 行）：

- **i18n**: 中/英 全栈切换，localStorage 持久化
- **PWA**: manifest + service worker + 离线 cache + 5 sec auto-refresh on focus
- **A11Y**: viewport meta + aria + inputmode + live regions（pa11y/axe-core 通过）
- **响应式**: 移动 card-list vs 桌面 table 自动切换
- **9 tabs**:
  1. 🎯 今日推荐（默认 landing，含 single/parlay/pool/WC 板块）
  2. 单关 / 串关 / 复式 高级模式（手动输入 fixtures）
  3. 🏆 WC 2026（含 Path A++ 让球推荐 inline form）
  4. 📊 推荐追溯（历史 + outcome chips）
  5. 📈 ROI 报告
  6. 🔧 规则说明
  7. 高级 ▾（折叠的 engineer tools）

### 12.2 关键 UX 决策

- **默认 landing = 今日推荐**：不需要手动 paste fixtures JSON
- **3 个 slider**: bankroll / risk preference / min_ev（V11 P1-FE#4）
- **version_hash + diff badges**: 显示「推荐已更新」横幅 + 每个 rec 上的「已更新」chip（V11 P1-FE#5）
- **PWA installable**: 用户可以 "添加到主屏幕" 当原生 app 用

---

## 13. 测试体系

### 13.1 数字

- **1493 tests** (82 文件)
- **0 skipped** (所有 skipif gate 在本地都满足)
- **0 deprecation warnings**（post-v9 P1#6 清理）
- **Avg run time**: ~2 分钟全套

### 13.2 测试金字塔

```
单元 (大多数, 0.05 sec/test)
  ├── 数学正确性 (DC grid, Kelly, KL reverse-map, market dewedge)
  ├── Pydantic schema validation
  └── 纯函数 (no IO)

集成 (~30%)
  ├── 端点 HTTP via FastAPI TestClient
  ├── CLI subprocess 测试 (test_e2e.py, test_recommend_cli_model_type.py)
  ├── SQLite round-trip (recorder + settle)
  └── Cron 链路 (record → settle → ab-report)

E2E (~10, slow, gated)
  ├── tests/v4/test_e2e.py (skipif no data/historical)
  ├── tests/playwright/ (Playwright + axe-core)
  └── pa11y WCAG

CI workflows (.github/)
  ├── nutmeg-ci.yml: pytest + mypy + ruff on PR
  ├── playwright.yml: Playwright E2E
  ├── weekly-bench.yml: scheduled benchmark
  ├── monthly-token-check.yml: API token alive check
  └── daily-recommend.yml: manual workflow_dispatch (no schedule)
```

### 13.3 Mock 策略

- **NEVER mock**: DC 网格、Kelly、SQLite schema、Pydantic
- **OK mock**: API-Football, Odds API, eloratings 抓取
- **Carefully mock**: model.predict_proba (用确定性 stub) for endpoint tests

---

## 14. 数据资产

### 14.1 模型 artifacts

| 路径 | 大小 | 状态 |
|---|---|---|
| `data/v4_model_cat_lineups/` | 692 KB | **production** (P1#18 起) |
| `data/v4_model_cat/` | 488 KB | V5 W12 base CatBoost (A/B 用) |
| `data/v4_model/` | 1.3 MB | V4 LightGBM baseline (test 用) |

### 14.2 外部数据缓存（gitignored）

| 路径 | 大小 | 内容 |
|---|---|---|
| `data/external/api_football/` | ~50 MB | fixtures + lineups + injuries JSON |
| `data/external/cup_history/` | ~20 MB | UCL/UEL/WC/EURO 历史 fixtures |
| `data/external/cup_odds/` | 619 行 (V11) | Pinnacle 杯赛 odds parquet (V10 trigger #1 ready) |
| `data/external/clubelo/` | ~5 MB | 俱乐部 Elo 时间序列 |
| `data/external/eloratings/` | ~2 MB | 国家队 Elo 快照 (V10 W1 Track B Day 2) |
| `data/external/understat/` | ~10 MB | xG-lite 历史 |

### 14.3 观测库

`data/v4_observation.db`（SQLite，启动时 ~10 KB，4 周后 ~5 MB，1 年后 ~50 MB）

### 14.4 安全

- `.env` chmod 600 + gitignored
- API tokens (NUTMEG_API_FOOTBALL_KEY + NUTMEG_ODDS_API_KEY) 从不进 plist / commit / log
- V11 加了 `monthly-token-check.yml` 验证 token 还活着

---

## 15. 运维与部署

### 15.1 当前生产部署：本地 macOS + launchd

7 个 cron job（fixed today 2026-05-26）:

```
02:00 daily   com.nutmeg.daily_wc_settle             ← WC outcome + report
03:00 Mon     com.nutmeg.weekly_calibration_check    ← Layer A T 校准
04:00 Sun     com.nutmeg.weekly_gate                 ← P1#19 live-vs-backtest
04:00 Sun     com.nutmeg.weekly_settle               ← 上周结算 + ROI
09:00 daily   com.nutmeg.daily_wc_predict            ← WC predict（WC 期间）
14:00 daily   com.nutmeg.daily_odds                  ← 写今日 CSV
15:00 daily   com.nutmeg.daily_recommend             ← 读 CSV + record session
```

### 15.2 一键脚本

```bash
./scripts/setup_local_pipeline.sh      # 安装 7 个 launchd job
./scripts/teardown_local_pipeline.sh   # 卸载
./scripts/health_check.sh              # 单命令查看 pipeline 状态
./scripts/run_local_server.sh [port]   # 启 dashboard
./scripts/wc_preflight.sh              # WC 开赛前 7 项检查
./scripts/v11_monitor.sh               # 数据累积监控
```

### 15.3 未来 VPS

设计已就绪：
- Hetzner CX22 ~€6/月 是甜蜜点
- 训练继续本地 Mac (~1.5 GB peak RAM)，artifact rsync 到 VPS
- systemd unit 替代 launchd（结构同构，转写 1 天工作量）

---

## 16. 当前状态与未结悬念

### 16.1 状态

```
项目阶段:           V11 ship + 5 个 post-ship commits
                   (Path A++ + 今日整合 + recording + cron 修复 + model_type 修复)
代码:               26.7k LoC 生产 + 5.5k LoC 测试
测试:               1493/1493 pass, 0 skipped
默认模型:           V6 W7 lineup-aware CatBoost (P1#18 起)
Cron 状态:          ✅ HEALTHY (7 jobs loaded, 0 exit)
Observation DB:    1 session (今天 smoketest), 等明天 15:00 第一条真实数据
真实下注 ROI:       0 数据点 → 4 周后第一份报告
WC 2026 开幕:       2026-06-11 (16 天后)
```

### 16.2 未结悬念（按重要性）

| Tier | 项目 | 卡在哪 |
|---|---|---|
| 🔴 P0 | 真实 ROI 4 周验证 | 等 cron 累积 |
| 🔴 P0 | WC 2026 真实表现 | 等开赛 |
| 🟠 P1 | Layer B 首次季度提议 | 2026-07-01 自动触发 |
| 🟠 P1 | stadium/fatigue 死码决策 | V12 决定 ship or 删 |
| 🟡 P2 | routes.py 拆分 | V12 candidate |
| 🟡 P2 | nutmeg-rec/recommend 合并 | V12 candidate |

### 16.3 已知良好

- ✅ 全 1493 测试绿
- ✅ Cron 链路通畅（today fixed）
- ✅ Observation DB 录入正确（model_type fixed）
- ✅ Path A++ WC 让球全栈 ship
- ✅ Settle bridge 让 WC 让球能自动结算
- ✅ Today-recommendations 含 WC 板块
- ✅ Session recording 双门 + dual-write 完整

---

## 17. 关键学习与方法论资产

33 周积累出来的方法论文档（`docs/`）：

| 类型 | 数量 | 总行数 |
|---|---|---|
| HANDOFF（每 version 单一信息源） | 8 (V4-V11) | ~3,500 |
| Retrospective | 5 (V6-V8 + V9 + V11) | ~1,400 |
| Weekly writeup | 33 | ~2,200 |
| Decision doc（ship/document/reject） | 9 | ~400 |
| 总计 | **55 文件** | **~7,500 行 markdown** |

### 17.1 最有价值的 3 个"失败也是资产"案例

1. **V5 W6 Ensemble ablation**: 试 stacker 失败，明确"single CatBoost 已经触顶"
2. **V8 W4 Cup ablation NEGATIVE**: 杯赛模型不 work，省下 3 个月迭代时间
3. **V9 W6 Calibration ablation**: temperature/isotonic 都不能改善 ECE，明确 ECE-vs-log-loss 谜团是 inherent

### 17.2 工程方法论

- **每个 ship 必须有 walk-forward verdict** → 决定 ship/document/reject
- **观测系统必须 dual gate** → env + flag → 默认安全
- **诚实文档化 NEGATIVE results** → 不被遗忘地重复尝试
- **`--auto-fetch` 之类的方便 flag 不进 CLI surface** → 避免今天遇到的 cron bug

---

## 18. Repo 元信息

| 字段 | 值 |
|---|---|
| 仓库 | https://github.com/wukong930/Nutmeg |
| License | MIT (private repo) |
| Python | 3.12+（实际 3.13.13） |
| 主分支 | `main` |
| 直 push 模式 | 是 (单人开发，无 PR) |
| Latest commit | `fecd32f` (2026-05-26 17:30 UTC+8) |
| Latest tag | `v11.0-shipped` |
| Commits | 121 |
| Tags | 52 |
| Contributors | 1 (用户) + Claude assistant |
| Lines (code) | ~26,700 |
| Lines (tests) | ~5,500 |
| Lines (docs) | ~7,500 |

---

## TL;DR — 一段话

**Nutmeg 是一个 33 周演进而成的、面向中国竞彩足球的端到端预测推荐系统**。技术核心是 CatBoost 训练 Poisson λ + Dixon-Coles 比分网格 + Pinnacle 市场融合的双层概率模型；产品形态是 PWA dashboard + 9 个 tab 覆盖单关/串关/复式/WC 4 个玩法 + 中文 i18n；运维形态是 7 个 launchd cron 自动跑数据/推荐/结算/校准；质量保证是 1493 测试全绿 + 0 TODO/FIXME + Layer A/B 双层自校准。当前正等待 cron 累积第一份真实 4 周 ROI 数据 + WC 2026 开赛（16 天后）— 这俩数据点会决定项目是 ship-and-forget 还是进入 V12 新一轮迭代。
