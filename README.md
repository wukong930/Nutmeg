# Nutmeg

Nutmeg is a football probability prediction platform. The system produces calibrated
1X2 and Asian-handicap probabilities for European top-flight + second-tier leagues,
J1, and the UEFA cups, then surfaces those into single-match predictions and
2–8 parlay recommendations with Kelly bankroll sizing.

**Important:** Nutmeg does not implement automated betting, wallets, payments, or
profit-certainty claims. Outputs are probabilities and educational recommendations.

## Current State (V5 in progress)

| | Status |
|---|---|
| Production model | V4: GBM-λ (LightGBM Poisson) + Dixon-Coles score grid + Temperature scaling |
| Validated log-loss (24/25 test) | **0.9987** vs Pinnacle closing **0.9904** (Δ +0.0083) |
| Signal capture rate | **92.3%** (vs uniform→Pinnacle gap) |
| Multi-season stability | 22/23 + 23/24 + 24/25 all show Δ +0.008–0.009 |
| Tests | 112/112 V4 unit + integration |
| Frontend | Single-page V4 dashboard at `/api/v4/dashboard` (no Node build) |

V5 is the active development line: data extension (free xG / market dynamics),
ensemble (XGBoost + CatBoost + LogReg stacker), Bayesian hierarchical for
small-sample leagues, observation loop, and aggressive code thinning. See
[docs/V5_ROADMAP.md](docs/V5_ROADMAP.md) for the 12-week plan.

## Quick Start

```bash
# Install dependencies (requires libomp on macOS: `brew install libomp`)
uv sync --all-extras

# Run V4 benchmark (~10 s on M-class Mac)
PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.bench

# Run V4 tests
PYTHONPATH=apps/api/src .venv/bin/python -m pytest tests/v4/

# Start the API + dashboard
NUTMEG_V4_ARTIFACT_PATH=data/v4_model .venv/bin/python -m nutmeg.main
# then open http://localhost:8000/api/v4/dashboard
```

## Project Layout

```
apps/api/src/nutmeg/
  main.py            # FastAPI app, V4 router only
  config.py          # Minimal pydantic settings
  v4/                # V4 prediction kernel
    data/            # CSV ingest + canonical schema
    features/        # market / Elo / form features (+ xG, market-dynamics planned)
    model/           # GBM-λ + Dixon-Coles + (planned: ensemble + hierarchical)
    calibration/     # Temperature scaling
    eval/            # walk-forward, baselines, metrics
    combo/           # parlay enumeration + Kelly sizing
    observation/     # SQLite session / recommendation / outcome / ROI tracking
    api/             # /api/v4/* routes + dashboard.html
    cli/             # bench / train / recommend / record-outcome / roi-report
configs/competitions/  # league metadata
data/historical_sources/   # football-data.co.uk CSV (27k matches, 13 leagues)
data/v4_model/             # serialized V4 booster + team state + temperature
docs/
  V4_HANDOFF.md         # V4 design + Phase A–D notes
  V5_ROADMAP.md         # active 12-week plan
  v4_baseline_card.md   # current benchmark numbers
  v4_multi_season_card.md
  legacy/               # archived V2/V3 docs
tests/v4/               # 112 unit + integration tests
```

## Key Commands

| Command | What it does |
|---|---|
| `nutmeg-api` | Start FastAPI + dashboard on :8000 |
| `nutmeg-bench` | Single-season (24/25) walk-forward benchmark |
| `nutmeg-bench-multi` | 22/23 + 23/24 + 24/25 multi-season benchmark |
| `nutmeg-train` | Train V4 artifact and save under `data/v4_model/` |
| `nutmeg-recommend` | Read today fixtures CSV → output parlay recommendations |
| `nutmeg-record-outcome` | Batch ingest match results → auto-settle bets |
| `nutmeg-roi-report` | ROI / hit-rate / calibration card from observation DB |

## Data Sources

| Source | Purpose | Status |
|---|---|---|
| football-data.co.uk | Historical results + Pinnacle closing odds | ✅ committed (~12 MB CSV) |
| understat | xG / shot-level data | ⏳ W3 (free) |
| clubelo | Independent ELO baseline | ⏳ W3 (free) |
| OddsPortal | Opening odds (drift signal) | ⏳ W3 (free) |
| API-Football | Lineups + injuries | ❓ W12 decision (paid $19/mo) |

## Repository

- GitHub: https://github.com/wukong930/Nutmeg
- Baseline tag: `v4.0-frozen` (V4 production state, pre-V5 refactor)
- Weekly tags: `v5.w1`, `v5.w2`, … (every Friday during V5 development)

## License & Disclaimers

Educational and research use only. Outputs are probabilistic; no claim of
profitability. Users must comply with local laws regarding sports prediction
and any associated activities.
