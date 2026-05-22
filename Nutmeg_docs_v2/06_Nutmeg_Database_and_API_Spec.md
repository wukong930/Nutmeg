# Nutmeg 数据库与 API 技术文档 v2

## 1. 设计原则

数据库必须支持：

```text
多 provider
多赛事
时间快照
比分矩阵
玩法派生
串关展开
赛后评估
模型版本治理
```

核心原则：

```text
所有时间敏感数据必须带 snapshot_time_utc
所有预测必须带 prediction_time_utc
所有特征必须带 feature_time_utc
所有模型输出必须带 model_version
```

---

## 2. PostgreSQL Schema

### 2.1 competitions

```sql
CREATE TABLE competitions (
  competition_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  country TEXT,
  region TEXT,
  competition_type TEXT NOT NULL,
  team_type TEXT NOT NULL,
  season_calendar TEXT,
  provider_primary TEXT,
  provider_secondary TEXT,
  coverage_tier TEXT,
  model_status TEXT DEFAULT 'inactive',
  config_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

### 2.2 seasons

```sql
CREATE TABLE seasons (
  season_id TEXT PRIMARY KEY,
  competition_id TEXT REFERENCES competitions(competition_id),
  name TEXT NOT NULL,
  start_date DATE,
  end_date DATE,
  current_matchday INT,
  status TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

### 2.3 teams

```sql
CREATE TABLE teams (
  team_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  country TEXT,
  team_type TEXT NOT NULL,
  founded INT,
  venue_name TEXT,
  metadata_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

### 2.4 provider_entity_mappings

```sql
CREATE TABLE provider_entity_mappings (
  mapping_id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  provider_entity_id TEXT NOT NULL,
  canonical_entity_id TEXT NOT NULL,
  confidence NUMERIC DEFAULT 1.0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(provider, entity_type, provider_entity_id)
);
```

### 2.5 fixtures

```sql
CREATE TABLE fixtures (
  fixture_id TEXT PRIMARY KEY,
  competition_id TEXT REFERENCES competitions(competition_id),
  season_id TEXT REFERENCES seasons(season_id),
  stage TEXT,
  round TEXT,
  matchday INT,
  home_team_id TEXT REFERENCES teams(team_id),
  away_team_id TEXT REFERENCES teams(team_id),
  kickoff_time_utc TIMESTAMPTZ NOT NULL,
  venue TEXT,
  neutral_venue BOOLEAN DEFAULT false,
  leg_type TEXT,
  aggregate_context_json JSONB DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'scheduled',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_fixtures_kickoff ON fixtures(kickoff_time_utc);
CREATE INDEX idx_fixtures_competition ON fixtures(competition_id);
```

### 2.6 results

```sql
CREATE TABLE results (
  fixture_id TEXT PRIMARY KEY REFERENCES fixtures(fixture_id),
  home_goals INT NOT NULL,
  away_goals INT NOT NULL,
  halftime_home_goals INT,
  halftime_away_goals INT,
  result_1x2 TEXT NOT NULL,
  settled_at TIMESTAMPTZ,
  source TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

### 2.7 team_match_stats

```sql
CREATE TABLE team_match_stats (
  stat_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  team_id TEXT REFERENCES teams(team_id),
  shots INT,
  shots_on_target INT,
  possession NUMERIC,
  corners INT,
  yellow_cards INT,
  red_cards INT,
  xg NUMERIC,
  xa NUMERIC,
  source TEXT,
  updated_at TIMESTAMPTZ,
  UNIQUE(fixture_id, team_id, source)
);
```

---

## 3. 快照表

### 3.1 raw_provider_payloads

```sql
CREATE TABLE raw_provider_payloads (
  payload_id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  entity_type TEXT,
  entity_id_hint TEXT,
  response_json JSONB NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_raw_payload_provider_time ON raw_provider_payloads(provider, fetched_at DESC);
```

### 3.2 odds_snapshots

```sql
CREATE TABLE odds_snapshots (
  odds_snapshot_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  provider TEXT NOT NULL,
  bookmaker TEXT,
  market_type TEXT NOT NULL,
  line NUMERIC,
  side TEXT,
  outcome TEXT NOT NULL,
  decimal_odds NUMERIC NOT NULL,
  raw_implied_probability NUMERIC,
  fair_probability NUMERIC,
  overround NUMERIC,
  liquidity NUMERIC,
  spread NUMERIC,
  snapshot_time_utc TIMESTAMPTZ NOT NULL,
  is_opening BOOLEAN DEFAULT false,
  is_closing BOOLEAN DEFAULT false,
  payload_id BIGINT REFERENCES raw_provider_payloads(payload_id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_odds_fixture_market_time ON odds_snapshots(fixture_id, market_type, snapshot_time_utc DESC);
```

### 3.3 player_availability_snapshots

```sql
CREATE TABLE player_availability_snapshots (
  availability_snapshot_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  team_id TEXT REFERENCES teams(team_id),
  player_id TEXT,
  player_name TEXT,
  status TEXT NOT NULL,
  reason TEXT,
  expected_return_date DATE,
  source TEXT,
  source_confidence NUMERIC,
  snapshot_time_utc TIMESTAMPTZ NOT NULL,
  payload_id BIGINT REFERENCES raw_provider_payloads(payload_id)
);
```

### 3.4 lineup_snapshots

```sql
CREATE TABLE lineup_snapshots (
  lineup_snapshot_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  team_id TEXT REFERENCES teams(team_id),
  lineup_type TEXT NOT NULL,
  player_id TEXT,
  player_name TEXT,
  position TEXT,
  probability_start NUMERIC,
  is_starter BOOLEAN,
  source TEXT,
  snapshot_time_utc TIMESTAMPTZ NOT NULL
);
```

### 3.5 feature_snapshots

```sql
CREATE TABLE feature_snapshots (
  feature_snapshot_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  feature_time_utc TIMESTAMPTZ NOT NULL,
  feature_version TEXT NOT NULL,
  features_json JSONB NOT NULL,
  source_snapshot_refs JSONB DEFAULT '{}',
  data_quality_score NUMERIC,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_feature_fixture_time ON feature_snapshots(fixture_id, feature_time_utc DESC);
```

---

## 4. 模型与预测表

### 4.1 model_versions

```sql
CREATE TABLE model_versions (
  model_version TEXT PRIMARY KEY,
  model_family TEXT NOT NULL,
  status TEXT NOT NULL,
  training_start_date DATE,
  training_end_date DATE,
  feature_version TEXT,
  calibration_version TEXT,
  artifact_uri TEXT,
  metrics_json JSONB DEFAULT '{}',
  params_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  activated_at TIMESTAMPTZ
);
```

### 4.2 score_probability_grids

```sql
CREATE TABLE score_probability_grids (
  score_grid_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  prediction_time_utc TIMESTAMPTZ NOT NULL,
  model_version TEXT REFERENCES model_versions(model_version),
  calibration_version TEXT,
  max_goals INT NOT NULL DEFAULT 8,
  grid_json JSONB NOT NULL,
  tail_mass NUMERIC NOT NULL DEFAULT 0,
  lambda_home NUMERIC,
  lambda_away NUMERIC,
  chaos_prob NUMERIC,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### 4.3 prediction_snapshots

```sql
CREATE TABLE prediction_snapshots (
  prediction_snapshot_id BIGSERIAL PRIMARY KEY,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  prediction_time_utc TIMESTAMPTZ NOT NULL,
  model_version TEXT REFERENCES model_versions(model_version),
  feature_snapshot_id BIGINT REFERENCES feature_snapshots(feature_snapshot_id),
  score_grid_id BIGINT REFERENCES score_probability_grids(score_grid_id),
  p_home NUMERIC NOT NULL,
  p_draw NUMERIC NOT NULL,
  p_away NUMERIC NOT NULL,
  uncertainty TEXT,
  data_quality_score NUMERIC,
  explanation_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_prediction_fixture_time ON prediction_snapshots(fixture_id, prediction_time_utc DESC);
```

### 4.4 market_predictions

```sql
CREATE TABLE market_predictions (
  market_prediction_id BIGSERIAL PRIMARY KEY,
  prediction_snapshot_id BIGINT REFERENCES prediction_snapshots(prediction_snapshot_id),
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  market_type TEXT NOT NULL,
  line NUMERIC,
  side TEXT,
  outcome TEXT NOT NULL,
  probability NUMERIC NOT NULL,
  fair_odds NUMERIC,
  settlement_rule_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_market_predictions_fixture ON market_predictions(fixture_id, market_type, line);
```

---

## 5. 冷门与串关表

### 5.1 upset_alerts

```sql
CREATE TABLE upset_alerts (
  upset_alert_id BIGSERIAL PRIMARY KEY,
  prediction_snapshot_id BIGINT REFERENCES prediction_snapshots(prediction_snapshot_id),
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  upset_type TEXT NOT NULL,
  target_market_type TEXT,
  target_line NUMERIC,
  target_outcome TEXT,
  model_probability NUMERIC,
  market_probability NUMERIC,
  probability_gap NUMERIC,
  favorite_fragility_score NUMERIC,
  upset_score NUMERIC,
  risk_level TEXT,
  explanation_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### 5.2 parlay_recommendations

```sql
CREATE TABLE parlay_recommendations (
  parlay_recommendation_id BIGSERIAL PRIMARY KEY,
  strategy TEXT NOT NULL,
  pass_type TEXT NOT NULL,
  is_multiple BOOLEAN DEFAULT false,
  unit_stake NUMERIC NOT NULL,
  multiplier INT DEFAULT 1,
  total_atomic_bets INT NOT NULL,
  total_stake NUMERIC NOT NULL,
  hit_probability NUMERIC,
  expected_payout NUMERIC,
  expected_value NUMERIC,
  roi NUMERIC,
  risk_score NUMERIC,
  risk_level TEXT,
  correlation_penalty NUMERIC,
  recommendation_score NUMERIC,
  rule_valid BOOLEAN DEFAULT true,
  explanation_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### 5.3 parlay_legs

```sql
CREATE TABLE parlay_legs (
  parlay_leg_id BIGSERIAL PRIMARY KEY,
  parlay_recommendation_id BIGINT REFERENCES parlay_recommendations(parlay_recommendation_id),
  leg_index INT NOT NULL,
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  market_type TEXT NOT NULL,
  line NUMERIC,
  selected_outcomes_json JSONB NOT NULL,
  probabilities_json JSONB NOT NULL,
  odds_json JSONB,
  confidence TEXT,
  data_quality_score NUMERIC
);
```

### 5.4 parlay_atomic_bets

```sql
CREATE TABLE parlay_atomic_bets (
  atomic_bet_id BIGSERIAL PRIMARY KEY,
  parlay_recommendation_id BIGINT REFERENCES parlay_recommendations(parlay_recommendation_id),
  outcomes_json JSONB NOT NULL,
  stake NUMERIC NOT NULL,
  probability NUMERIC,
  odds_product NUMERIC,
  expected_payout NUMERIC,
  expected_value NUMERIC,
  result_status TEXT,
  settled_at TIMESTAMPTZ
);
```

---

## 6. 赛后评估表

### 6.1 prediction_evaluations

```sql
CREATE TABLE prediction_evaluations (
  evaluation_id BIGSERIAL PRIMARY KEY,
  prediction_snapshot_id BIGINT REFERENCES prediction_snapshots(prediction_snapshot_id),
  fixture_id TEXT REFERENCES fixtures(fixture_id),
  actual_home_goals INT NOT NULL,
  actual_away_goals INT NOT NULL,
  actual_result_1x2 TEXT NOT NULL,
  log_loss_1x2 NUMERIC,
  brier_score_1x2 NUMERIC,
  actual_score_probability NUMERIC,
  actual_score_rank INT,
  market_comparison_json JSONB DEFAULT '{}',
  error_tags_json JSONB DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### 6.2 model_backtest_runs

```sql
CREATE TABLE model_backtest_runs (
  backtest_run_id BIGSERIAL PRIMARY KEY,
  model_version TEXT REFERENCES model_versions(model_version),
  train_window_json JSONB,
  test_window_json JSONB,
  competitions_json JSONB,
  metrics_json JSONB NOT NULL,
  calibration_json JSONB DEFAULT '{}',
  report_uri TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### 6.3 model_promotion_events

```sql
CREATE TABLE model_promotion_events (
  promotion_event_id BIGSERIAL PRIMARY KEY,
  candidate_model_version TEXT REFERENCES model_versions(model_version),
  previous_model_version TEXT REFERENCES model_versions(model_version),
  decision TEXT NOT NULL,
  reason_json JSONB DEFAULT '{}',
  decided_by TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## 7. API 设计

Base URL:

```text
/api/v1
```

### 7.1 获取比赛列表

```http
GET /api/v1/fixtures?date=2026-05-06&competition_id=EPL
```

响应：

```json
{
  "items": [
    {
      "fixture_id": "fix_123",
      "competition": "Premier League",
      "kickoff_time_utc": "2026-05-06T19:00:00Z",
      "home_team": {"team_id": "ars", "name": "Arsenal"},
      "away_team": {"team_id": "liv", "name": "Liverpool"},
      "prediction": {
        "p_home": 0.418,
        "p_draw": 0.265,
        "p_away": 0.317,
        "confidence": "medium",
        "model_version": "dc-v1.5.3",
        "prediction_time_utc": "2026-05-06T12:00:00Z"
      },
      "badges": ["draw_overlooked"]
    }
  ]
}
```

### 7.2 获取单场详情

```http
GET /api/v1/fixtures/{fixture_id}/prediction
```

响应包含：

```text
fixture
prediction_snapshot
score_top_n
market_predictions
odds_comparison
upset_alerts
explanations
model_metadata
```

### 7.3 获取比分矩阵

```http
GET /api/v1/fixtures/{fixture_id}/score-grid
```

响应：

```json
{
  "fixture_id": "fix_123",
  "max_goals": 8,
  "grid": [[0.07, 0.08], [0.10, 0.11]],
  "tail_mass": 0.006,
  "lambda_home": 1.42,
  "lambda_away": 1.11
}
```

### 7.4 获取冷门榜

```http
GET /api/v1/upsets?date=2026-05-06&type=favorite_fail_to_cover
```

### 7.5 生成串关推荐

```http
POST /api/v1/parlays/recommend
```

请求：

```json
{
  "date": "2026-05-06",
  "pass_types": ["2x1", "3x1", "4x1"],
  "strategy": "balanced",
  "unit_stake": 2,
  "max_budget": 20,
  "allow_multiple_outcomes_per_fixture": true,
  "allowed_markets": ["1x2", "cn_handicap_1x2"],
  "exclude_beta_competitions": true
}
```

### 7.6 评估用户自选串关

```http
POST /api/v1/parlays/evaluate
```

请求：

```json
{
  "pass_type": "4x1",
  "unit_stake": 2,
  "legs": [
    {"fixture_id": "A", "market_type": "1x2", "outcomes": ["away_win", "draw"]},
    {"fixture_id": "B", "market_type": "1x2", "outcomes": ["away_win"]},
    {"fixture_id": "C", "market_type": "1x2", "outcomes": ["draw", "away_win"]},
    {"fixture_id": "D", "market_type": "1x2", "outcomes": ["home_win"]}
  ]
}
```

### 7.7 模型表现

```http
GET /api/v1/accuracy/summary?model_version=active&competition_id=EPL&window=90d
```

响应：

```json
{
  "log_loss": 0.982,
  "brier_score": 0.192,
  "ece": 0.034,
  "sample_size": 420,
  "by_market": {
    "1x2": {"log_loss": 0.982},
    "cn_handicap_1x2": {"log_loss": 1.041}
  }
}
```

---

## 8. API 约束

- API 必须返回 `model_version`。
- API 必须返回 `prediction_time_utc`。
- API 必须返回 `data_quality_score`。
- 串关 API 必须返回规则合法性。
- 如果数据过期，API 必须返回 `stale: true`。
- 如果模型 fallback，API 必须返回 `fallback_used: true`。

---

## 9. 测试要求

### 9.1 数据库

- migration 可重复执行。
- foreign key 正确。
- 关键查询有索引。
- 不允许没有时间戳的快照数据。

### 9.2 API

- 所有响应通过 Pydantic schema。
- 预测概率和为 1。
- 玩法概率和正确。
- 串关注数正确。
- 数据过期时返回 stale。

