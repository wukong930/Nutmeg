# Nutmeg V6 Roadmap

_Generated 2026-05-23 after V5 ship + user requirements deep-dive_

This replaces `V6_ROADMAP_DRAFT.md`. The draft was scoped before the
requirements interview at end-of-V5; this version reflects the actual
product needs the user confirmed.

## Why V6 exists (different from V5)

V5 was a **science / engineering refactor** — improve the model, clean up
the codebase, build observability. By the end of V5 the model is sharp
(CatBoost log-loss 0.9960, ECE 0.0120 better than Pinnacle) but the
**product gap remains huge**:

- ✅ V5 predicts 1X2 and handicap 1X2
- ❌ V5 does NOT support China lottery (`竞彩足球`) rules natively:
  - No M-select-N (`M选N`) compound betting
  - No floating handicap / floating SP capture
  - No `¥2` minimum stake quantization
  - No vig-aware EV thresholds (lottery vig is ~31%, not Pinnacle 2.5%)
  - No lineup / injury features (Pinnacle's information advantage)

V6 closes these. It is **product-led**: every week builds something the
user can immediately use to place better bets.

## Scope (locked from end-of-V5 user interview)

| Item | Decision |
|---|---|
| Game | 中国体彩 · 竞彩足球 (`China Sports Lottery, jincai zuqiu`) |
| Markets | **胜平负 + 让球胜平负 only**. No correct score, no totals (O/U), no half-time/full-time |
| Parlay | Single + 2-串-1 to 8-串-1 + mixed parlay (1X2 with handicap) |
| Compound | **Both kinds**: in-match compound (1 match → multiple outcomes) + M-select-N compound parlay |
| Stake | ¥2 minimum unit; stake must be 2's multiple |
| Handicap | **Floating** — locked at bet submission, settles on that snapshot |
| SP | **Floating** — locked at bet submission |
| Max parlay legs | 8 (mixed parlay rules) |
| Vig | 31% (lottery payout ratio ~69%) — EV thresholds adjusted accordingly |
| User flow | User picks market type (single / parlay / compound) → enters budget → system recommends optimal tickets in that category only |
| Odds source | **API-Football Pro** ($19/month, paid by user, ~7.5k requests/day, includes lineups/injuries/multi-book odds). 中国竞彩 SP still requires manual entry or future native source |
| Lineup data | API-Football confirmed XI ~1 hour pre-kickoff |

## 12-week plan

### P0 — China lottery rules + native odds source (W1-4)

| W | Theme | Deliverable | Estimate |
|---|---|---|---|
| **V6 W1** | API-Football adapter | `sources/api_football.py` for fixtures/lineups/injuries/odds. Token via `.env` (gitignored). End-to-end test pulling yesterday EPL data. | 4-5d |
| **V6 W2** | Lineup features | `features/lineups.py` — starting XI presence flags + key player missing + first-XI minutes-played momentum. Integration into `pipeline.py` + `build_features_for_fixtures`. | 4-5d |
| **V6 W3** | M-select-N compound parlay | `combo/compound_pool.py` — generate C(M,N) combinations + Kelly per-combo + ¥2 quantization. CLI: `nutmeg-recommend --pool --n N --m M`. | 4-5d |
| **V6 W4** | China lottery rules | Floating handicap capture in observation (handicap snapshot at bet placement); ¥31% vig EV threshold; max-parlay-stake ¥20k cap; mixed-parlay-8-legs validator. | 3-4d |

### P1 — Model upgrade with lineups + live validation (W5-8)

| W | Theme | Deliverable | Estimate |
|---|---|---|---|
| **V6 W5** | CatBoost retrain with lineups | Multi-season validation; ablation on `with-lineups` vs `without-lineups`. Acceptance: ≥ -0.002 log-loss improvement multi-season. | 3-4d |
| **V6 W6** | Production artifact migration | New artifact with lineup features; backward-compat path so old artifact still loads; A/B in `recommend.py`. | 2-3d |
| **V6 W7** | Real-bet observation onboarding | User starts daily `nutmeg-recommend --snapshot-phase pre_close` + `closing` workflow; weekly cron analytics. | 1d setup + waiting |
| **V6 W8** | Live ROI gate | After 4 weeks of real bets, decide: continue features OR investigate leakage OR claim victory. | 2d analysis |

### P2 — Product polish + handoff (W9-12)

| W | Theme | Deliverable | Estimate |
|---|---|---|---|
| **V6 W9** | User-flow product CLI | Three-step CLI: `nutmeg-rec` interactive (single / 串关 / 复式) → budget → ticket recommendation. Or web UI form. | 4-5d |
| **V6 W10** | Chinese dashboard | Translate dashboard.html + add rule explainers (派奖率, 浮动让球, 起投¥2 etc) | 3-4d |
| **V6 W11** | Cup data + national teams | World Cup, Euro, UCL knockout, FA Cup ingest; cross-league team handling | 3-5d |
| **V6 W12** | V6_HANDOFF + ship | Documentation, retrospective, `v6.0-shipped` tag | 2d |

## Quantitative targets

| Metric | V5 ship | V6 target |
|---|---:|---:|
| log-loss (24/25, GBM-eligible) | 0.9960 | ≤ **0.9930** (with lineups) |
| ECE | 0.0120 | ≤ 0.0150 (allow small regression for log-loss gain) |
| Markets supported | 1X2 + handicap | + M-select-N compound + ¥2 quantization |
| Real-bet ROI (4-week Kelly0.25, vig 31%) | no data | ≥ **+5pp**¹ |
| Real-bet vs backtest hit-rate gap | no data | ≤ ±5pp |

¹ At 31% vig the EV threshold is much harsher than Pinnacle's 2.5%; +5pp ROI represents a strong, sustainable edge after the lottery's house take.

## Reusing V5 negative findings

V6 must **not** retry these without changed conditions:

- ❌ Market-dynamics drift (W5 — pinned still-disabled). Will only revisit if multi-snapshot odds streams come online (API-Football provides snapshot-time odds; collecting drift across snapshots is possible but requires multi-call infrastructure).
- ❌ LogReg ensemble stacker (W6 — pinned still-disabled). Will revisit only if non-correlated bases become available (e.g., one base trained on lineup features, another on pure form, etc.).
- ❌ Per-league temperature (W9 — pinned still-disabled). Will revisit when validation windows exceed 800 matches/league.

## Out of scope for V6

- Correct score recommendation (user explicitly skipped — "太难命中")
- Totals (O/U 2.5/3.5) recommendation (user skipped)
- Half-time/full-time recommendation (user skipped)
- Postgres migration (W11 of V5_ROADMAP_DRAFT — V6 stays on SQLite)
- Multi-user / SaaS (single user is the target)

## Risks tracked

1. **API-Football scrape rate**: 7.5k requests/day is plenty for 13 leagues × 10 fixtures × 5 endpoints (fixtures, odds, lineup home/away, injuries) = ~650 requests/day. Headroom 10× — comfortable.
2. **Lineup data arrives < 1 hour before kickoff**: model retraining on lineups means production `recommend` needs the lineup endpoint hit within the prediction window. Build a 15-minute polling job for fixtures starting in next 2 hours.
3. **API key rotation**: token currently in `.env`; user advised to rotate after V5 conversation log. V6 W1 makes the system tolerant of mid-week key change (`load_dotenv` re-runs per CLI invocation, no caching of the key value).
4. **Vig 31% reality check**: at 31% the model needs to be ≥ 31% accurate (per-bet) just to break even before any edge. CatBoost ECE 0.0120 + log-loss 0.9960 gives us **some** edge against Pinnacle (vig 2.5%) but the gap vs lottery is much larger. **If V6 W8 shows sustained negative live ROI, the conclusion is "lottery markets aren't beatable at our edge size" — accept and pivot to exchange-style books**, not "throw more features at it".

## Active artifact paths after V6

- `data/v4_model_cat/` — V5 CatBoost (current production)
- `data/v4_model_cat_lineup/` — V6 W6 deliverable (CatBoost + lineups)
- `data/external/api_football/` — V6 W1+ raw API responses (gitignored)
- `data/v4_observation.db` — production observation (V5 W8 + V6 W4 floating-handicap fields)

## Tag plan

| Tag | When |
|---|---|
| `v6.w1` | API-Football adapter end-to-end test passes |
| `v6.w4` | China lottery rules + M-select-N shipped |
| `v6.w8` | Live ROI gate decision recorded |
| `v6.0-shipped` | V6 W12 close, V6_HANDOFF written |
