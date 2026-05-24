# V6 W9 — `nutmeg-rec` 交互推荐入口

_The user-flow product CLI from the V6 scope:_

> "用户依次选 单关/串关/复式 → 输入预算 → 系统推荐最优票"

W9 turns that into a single command. The math behind each branch is
unchanged from V5 W12 / V6 W3-7; the new layer is a Chinese-localized
prompt flow that someone can run without remembering argparse syntax,
plus a new 单关 single-leg recommender that completes the trio.

## The three flows

| Flow | 命令 | 引擎 |
|---|---|---|
| 单关 (single-leg) | `nutmeg-rec --type single` | `combo.single_match.recommend_singles` (new W9) |
| 串关 (2-串-1 ~ 8-串-1 混合过关) | `nutmeg-rec --type parlay` | `combo.recommend_combinations` (V5 W7) |
| 复式 (M-select-N 复式过关) | `nutmeg-rec --type pool` | `combo.compound_pool.recommend_pool` (V6 W3) |

All three apply V6 W4 lottery rules — ¥2 quantization, ¥20k single-ticket
cap, 31.5% vig-aware EV threshold (`DEFAULT_MIN_EV_PER_UNIT = 0.05`).

## Three modes of use

### Pure interactive

```text
$ nutmeg-rec
================================================
  Nutmeg 竞彩足球 推荐 (V6 W9)
================================================

请选择投注玩法:
  [1] 单关     — 单场胜平负 / 让球胜平负
  [2] 串关     — 2串1 ~ 8串1 混合过关
  [3] 复式     — M 选 N 复式过关
  [q] 退出

你的选择 [1]: 1
请输入今日比赛 CSV 路径 [data/fixtures/today.csv]: today.csv
请输入投注资金 (¥) [1000.0]: 500
请输入模型路径 [data/v4_model_cat]:

# 单关推荐 (4 场比赛)
...
```

Every prompt has a sensible default; press Enter to accept.

### Type-only flag (rest interactive)

```bash
nutmeg-rec --type pool
# Prompts for fixtures, bankroll, N, max-total-budget
```

Useful when you've already decided the product but want help with the
detail params.

### Fully scripted

```bash
nutmeg-rec --type single \
    --fixtures data/fixtures/today.csv \
    --bankroll 500 \
    --model data/v4_model_cat \
    --out docs/today/single.md
```

Zero prompts; suitable for shell aliases or cron. (We do NOT recommend
running this in cron — placing real bets should always have a human
look at the recommendation first.)

## 单关 — the new piece

Until W9 the CLIs only covered 串关 (2-leg minimum) and 复式 (M-select-N).
The simplest 竞彩 product, 单关, didn't have a recommender. W9 ships
`combo.single_match.recommend_singles`:

For each match in the fixtures CSV:
1. `build_selections_from_match` → up to 6 candidate Selections
   (1X2 × {H, D, A} + handicap_1x2 × {H, D, A})
2. Filter by `passes_recommendation_thresholds` (drops sub-5% EV or
   sub-5% hit probability)
3. Per-selection fractional Kelly stake (default 0.25× full Kelly,
   capped at 5% of bankroll per ticket)
4. Apply ¥20k absolute lottery cap; quantize down to ¥2 multiple
5. Keep at most `top_per_match` per fixture (default 1 — never
   suggest betting BOTH H and A on the same match)
6. Global EV-descending sort

Output is a table of (比赛, 玩法, 选, 模型概率, 赔率, EV/单位, 投注)
plus 总投注 / 预期总回报.

Default behavior — `top_per_match=1` — means the user sees at most
one bet per fixture. Pass `--top-per-match 2` if you want to see the
second-best option per match too (useful when running 串关 manually
and you want optionality).

## Sample outputs

### 单关 with positive EV

```markdown
# 单关推荐 (4 场比赛)

_Generated 2026-05-23 10:00 UTC_
_Bankroll: ¥500 · 起投 ¥2_

| # | 比赛 | 玩法 | 选 | 模型概率 | 赔率 | EV/单位 | 投注 |
|---|------|------|----|---------:|-----:|--------:|-----:|
| 1 | Arsenal vs Wolves | 胜平负 | H | 80.40% | 1.50 | +20.60% | ¥22 |
| 2 | Liverpool vs Burnley | 让球胜平负 | H | 56.30% | 1.85 | +4.16% | ¥0 |

**总投注**: ¥22
**预期总回报**: ¥+4.53

> ⚠️ 系统不进行自动投注；推荐仅供参考。请按 ¥2 倍数确认 SP 后下注。
```

Note the second row: it survives the threshold filter (≥ 5% EV after
quantization) but Kelly's quantized stake rounds down to ¥0 because
the edge is small relative to bankroll. It still shows up in the table
for context, with `投注 = ¥0`.

### 串关 (existing flow)

Same as `nutmeg-recommend` output, but with Chinese labels
("内选" instead of "compound") and lottery-aware footer.

### 复式 (existing flow)

Same as `nutmeg-recommend-pool` output, with `总投注` rendered using
¥2-quantized stakes.

## Test coverage

`tests/v4/test_single_match.py` — 25 tests:

- `TestRecommendSingles` (8) — high-EV pick, low-EV no-pick, `top_per_match`,
  threshold on/off, ¥20k cap, custom rules
- `TestBestPerMatch` (3) — per-match top-K filter, range validation
- `TestFormatSingle` (2) — empty markdown ("无可下注组合"), table render
- `TestPrompts` (8) — default-on-empty, range/type validation,
  EOF-uses-default, retry on invalid
- `TestMainDispatch` (4) — `q` exits 0, bad fixtures path exits 1,
  argparse accepts all types

Full V4 suite: **418/418 passing** (393 prior + 25 new W9).

## Files touched in W9

```
apps/api/src/nutmeg/v4/combo/single_match.py   [+]
apps/api/src/nutmeg/v4/combo/__init__.py        [M] export single_match
apps/api/src/nutmeg/v4/cli/rec.py               [+]
pyproject.toml                                  [M] nutmeg-rec entry
tests/v4/test_single_match.py                   [+] (25 tests)
docs/V6_ROADMAP.md                              [M] W9 ✅
docs/v6_w9_user_flow.md                         [+] (this file)
```

## What W9 doesn't do

- **No Web UI**: the V6 roadmap mentioned "Or web UI form" — terminal CLI
  is shipped first. A web form can wrap the same backend in V6 W11+ if
  the user wants it. Keeps W9 surface area small.
- **No interactive fixture entry**: fixtures still come from a CSV.
  Typing match-by-match in the terminal isn't realistic for the daily
  flow (8+ matches × 8 odds fields = ~64 numbers per night). The CSV
  is the source of truth — generated upstream by the W8 cron + market
  scraper, or pasted by hand from the lottery's website.
- **No place-bet automation**: this CLI NEVER hits the lottery's bet-
  placement endpoint. It produces a recommendation; the user copies it
  to the terminal and confirms manually. (Stated explicitly in every
  footer: "系统不进行自动投注".)

## Next: V6 W10

Chinese dashboard refresh — translate `apps/api/src/nutmeg/v4/api/`'s
HTML/JSON output to Chinese + add rule explainers (派奖率, 浮动让球,
起投 ¥2 etc) for non-developer users. Likely a 3-4 day task.
