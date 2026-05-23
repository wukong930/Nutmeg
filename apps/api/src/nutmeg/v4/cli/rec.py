"""nutmeg-rec — interactive entry for 竞彩 推荐 (V6 W9).

The user-facing wrapper that walks a single person through the daily
decision:

    单关 / 串关 / 复式  →  比赛 CSV  →  资金  →  系统推荐票

Behind the scenes this dispatches to the same engines as the
non-interactive CLIs (`nutmeg-recommend` for 串关, `nutmeg-recommend-pool`
for 复式, the new `combo.single_match` for 单关) — so the math is
identical. The value-add is a Chinese-localized interactive prompt
flow that someone can run from terminal without remembering argparse
syntax.

Modes:

  1. Pure interactive (no flags)
       nutmeg-rec
     Walks every prompt.

  2. Type-only flag (rest interactive)
       nutmeg-rec --type single
     Skips the type prompt; asks for fixtures + bankroll.

  3. Fully scripted (all flags)
       nutmeg-rec --type single --fixtures today.csv --bankroll 1000
     No prompts; runs and exits. Useful for cron / `nutmeg-rec` -ish
     bash aliases.

Output is always Markdown printed to stdout; pipe to a file or use
`--out`.

Note: this CLI never PLACES bets — only generates recommendations.
The user copies them into the lottery terminal themselves.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from nutmeg.v4.combo import recommend_combinations
from nutmeg.v4.combo.compound_pool import recommend_pool
from nutmeg.v4.combo.lottery_rules import JINGCAI_DEFAULT, MAX_LEGS_PER_TICKET
from nutmeg.v4.combo.selections import MatchInput
from nutmeg.v4.combo.single_match import recommend_singles
from nutmeg.v4.model.dixon_coles import (
    grid_to_1x2,
    grid_to_handicap_1x2,
    score_grid,
)
from nutmeg.v4.model.persist import (
    build_features_for_fixtures,
    load_artifact,
    predict_lambdas,
)

# Re-use the recommend CLI's fixture reader + selection builders to keep
# the formats in lockstep.
from nutmeg.v4.cli.recommend import _read_fixtures, _row_to_match_input
from nutmeg.v4.cli.recommend_pool import _read_pool_fixtures, _row_to_selection


BANNER = """\
================================================
  Nutmeg 竞彩足球 推荐 (V6 W9)
================================================
"""

TYPE_MENU = """\
请选择投注玩法:
  [1] 单关     — 单场胜平负 / 让球胜平负
  [2] 串关     — 2串1 ~ 8串1 混合过关
  [3] 复式     — M 选 N 复式过关
  [q] 退出
"""


# ---------- Prompt helpers (factored for testability) ----------------------

def _prompt(prompt_text: str, *, default: Optional[str] = None,
            reader: Callable[[str], str] = input) -> str:
    """Read a line from stdin with optional default. Returns trimmed string.

    `reader` is `input` by default — tests monkeypatch it with a queue.
    """
    suffix = f" [{default}]" if default is not None else ""
    while True:
        try:
            raw = reader(f"{prompt_text}{suffix}: ").strip()
        except EOFError:
            # Cron / non-interactive shells: treat as "use default"
            return default if default is not None else ""
        if raw:
            return raw
        if default is not None:
            return default
        # No default + empty input: re-prompt
        print("  (please enter a value)", file=sys.stderr)


def _prompt_float(prompt_text: str, *, default: float,
                  reader: Callable[[str], str] = input) -> float:
    while True:
        raw = _prompt(prompt_text, default=str(default), reader=reader)
        try:
            return float(raw)
        except ValueError:
            print(f"  ⚠ '{raw}' 不是有效数字，请重输", file=sys.stderr)


def _prompt_int(prompt_text: str, *, default: int, lo: int, hi: int,
                reader: Callable[[str], str] = input) -> int:
    while True:
        raw = _prompt(prompt_text, default=str(default), reader=reader)
        try:
            v = int(raw)
        except ValueError:
            print(f"  ⚠ '{raw}' 不是有效整数，请重输", file=sys.stderr)
            continue
        if not (lo <= v <= hi):
            print(f"  ⚠ 范围必须是 [{lo}, {hi}]，请重输", file=sys.stderr)
            continue
        return v


def _prompt_choice(prompt_text: str, choices: list[str], *,
                   default: Optional[str] = None,
                   reader: Callable[[str], str] = input) -> str:
    while True:
        raw = _prompt(prompt_text, default=default, reader=reader).lower()
        if raw in choices:
            return raw
        print(f"  ⚠ 必须是 {choices} 中之一，请重输", file=sys.stderr)


# ---------- Formatters -----------------------------------------------------

def _format_single(rec, bankroll: float, n_fixtures: int) -> str:
    lines = []
    lines.append(f"# 单关推荐 ({n_fixtures} 场比赛)")
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append(f"_Bankroll: ¥{bankroll:.0f} · 起投 ¥{JINGCAI_DEFAULT.stake_unit:.0f}_")
    lines.append("")
    if not rec.selected_tickets:
        lines.append("**无可下注组合** — 今日所有市场未通过 EV / 命中率门槛 (建议 no-bet)。")
        return "\n".join(lines)
    lines.append("| # | 比赛 | 玩法 | 选 | 模型概率 | 赔率 | EV/单位 | 投注 |")
    lines.append("|---|------|------|----|---------:|-----:|--------:|-----:|")
    for i, t in enumerate(rec.selected_tickets, 1):
        sel = t.selection
        market = "胜平负" if sel.market_type == "1x2" else "让球胜平负"
        # match_id format: "LEAGUE_HomeTeam_vs_AwayTeam"
        match_label = sel.match_id.split("_", 1)[-1].replace("_vs_", " vs ")
        lines.append(
            f"| {i} | {match_label} | {market} | {sel.outcome} | "
            f"{sel.probability:.2%} | {sel.odds:.2f} | {sel.edge:+.2%} | ¥{t.stake:.0f} |"
        )
    lines.append("")
    lines.append(f"**总投注**: ¥{rec.total_stake:.0f}  ")
    lines.append(f"**预期总回报**: ¥{rec.total_expected_return:+.2f}")
    lines.append("")
    lines.append("> ⚠️ 系统不进行自动投注；推荐仅供参考。请按 ¥2 倍数确认 SP 后下注。")
    return "\n".join(lines)


def _format_parlay(recs, bankroll: float, n_fixtures: int) -> str:
    lines = []
    lines.append(f"# 串关推荐 ({n_fixtures} 场比赛)")
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append(f"_Bankroll: ¥{bankroll:.0f}_")
    lines.append("")
    if not recs:
        lines.append("**无 +EV 串关组合** — 今日所有 2-串-1 ~ 8-串-1 票未通过门槛 (建议 no-bet)。")
        return "\n".join(lines)
    for r in recs:
        p = r.parlay
        compound = " (内选)" if p.is_compound else ""
        lines.append(f"### #{r.rank} — {p.k} 串 1{compound}")
        lines.append(f"- 命中率: **{p.hit_probability:.2%}**")
        lines.append(f"- EV/单位: **{p.ev_per_unit:+.2%}**")
        lines.append(f"- 投注: **¥{r.kelly.recommended_stake:.0f}** (Kelly {r.kelly.capped_kelly:.1%})")
        lines.append(f"- 预期回报: ¥{r.kelly.expected_return:+.2f}")
        for leg in p.legs:
            sels = " 或 ".join(
                f"{s.outcome}@{s.odds:.2f} (p={s.probability:.0%})"
                for s in leg.selections
            )
            market_label = "胜平负" if leg.market_type == "1x2" else "让球胜平负"
            lines.append(f"  - `{leg.match_id}` [{market_label}] → {sels}")
        lines.append("")
    total_stake = sum(r.kelly.recommended_stake for r in recs)
    total_er = sum(r.kelly.expected_return for r in recs)
    lines.append(f"**总投注**: ¥{total_stake:.0f} ({total_stake/bankroll:.1%} of bankroll)  ")
    lines.append(f"**预期总回报**: ¥{total_er:+.2f}")
    lines.append("")
    lines.append("> ⚠️ 系统不进行自动投注；推荐仅供参考。")
    return "\n".join(lines)


def _format_pool(rec, bankroll: float, max_budget: Optional[float]) -> str:
    lines = []
    lines.append(f"# 复式过关推荐 ({rec.m} 选 {rec.n})")
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    bud = f"¥{max_budget:.0f}" if max_budget else "无限制"
    lines.append(f"_Bankroll: ¥{bankroll:.0f} · 起投 ¥{JINGCAI_DEFAULT.stake_unit:.0f} · 总预算: {bud}_")
    lines.append("")
    lines.append(f"共 {rec.n_combinations} 张候选, 选中 {len(rec.selected_tickets)} 张:")
    lines.append("")
    if not rec.selected_tickets:
        lines.append("**无可下注组合** — 所有 N 串 1 票 EV ≤ 0 或 Kelly 仓位 < ¥2 (建议 no-bet)。")
        return "\n".join(lines)
    lines.append("| # | 命中率 | 总赔率 | EV/单位 | 投注 | 预期回报 | 选项 |")
    lines.append("|--:|-------:|-------:|--------:|-----:|---------:|------|")
    for i, t in enumerate(rec.selected_tickets, 1):
        legs_label = " + ".join(
            f"{leg.match_id.split('_', 1)[-1].replace('_vs_', '/')}:{leg.outcome}"
            for leg in t.legs
        )
        lines.append(
            f"| {i} | {t.hit_probability:.2%} | "
            f"{t.combined_odds:.2f} | {t.ev_per_unit:+.2%} | "
            f"¥{t.stake:.0f} | ¥{t.expected_return:+.2f} | {legs_label} |"
        )
    lines.append("")
    lines.append(f"**总投注**: ¥{rec.total_stake:.0f}  ")
    lines.append(f"**预期总回报**: ¥{rec.total_expected_return:+.2f}")
    lines.append("")
    lines.append("> ⚠️ 系统不进行自动投注；推荐仅供参考。")
    return "\n".join(lines)


# ---------- Per-type runners ----------------------------------------------

def _run_single(args, reader: Callable[[str], str]) -> str:
    fixtures_path = args.fixtures or _prompt(
        "请输入今日比赛 CSV 路径",
        default="data/fixtures/today.csv",
        reader=reader,
    )
    bankroll = args.bankroll if args.bankroll is not None else _prompt_float(
        "请输入投注资金 (¥)",
        default=1000.0,
        reader=reader,
    )
    model_path = args.model or _prompt(
        "请输入模型路径",
        default="data/v4_model_cat",
        reader=reader,
    )

    fixtures = _read_fixtures(fixtures_path)
    artifact = load_artifact(model_path)
    feats = build_features_for_fixtures(artifact, fixtures)
    lambdas = predict_lambdas(artifact, feats)
    gbm_rho = float(artifact.metadata.get("gbm_rho", -0.10))

    matches: list[MatchInput] = []
    for i, row in fixtures.iterrows():
        mi = _row_to_match_input(row, lambdas[i, 0], lambdas[i, 1], gbm_rho)
        if mi:
            matches.append(mi)

    rec = recommend_singles(
        matches,
        bankroll=bankroll,
        top_per_match=args.top_per_match,
    )
    return _format_single(rec, bankroll, n_fixtures=len(fixtures))


def _run_parlay(args, reader: Callable[[str], str]) -> str:
    fixtures_path = args.fixtures or _prompt(
        "请输入今日比赛 CSV 路径",
        default="data/fixtures/today.csv",
        reader=reader,
    )
    bankroll = args.bankroll if args.bankroll is not None else _prompt_float(
        "请输入投注资金 (¥)",
        default=1000.0,
        reader=reader,
    )
    model_path = args.model or _prompt(
        "请输入模型路径",
        default="data/v4_model_cat",
        reader=reader,
    )
    k_min = args.k_min if args.k_min is not None else _prompt_int(
        "串关组合数下限",
        default=2, lo=2, hi=MAX_LEGS_PER_TICKET,
        reader=reader,
    )
    k_max = args.k_max if args.k_max is not None else _prompt_int(
        "串关组合数上限",
        default=min(MAX_LEGS_PER_TICKET, max(2, k_min + 2)),
        lo=k_min, hi=MAX_LEGS_PER_TICKET,
        reader=reader,
    )
    include_compound = args.include_compound
    if not include_compound:
        ans = _prompt_choice(
            "是否包含内选组合 (单场多选, 不是复式过关)? (y/n)",
            choices=["y", "n"], default="n", reader=reader,
        )
        include_compound = ans == "y"

    fixtures = _read_fixtures(fixtures_path)
    artifact = load_artifact(model_path)
    feats = build_features_for_fixtures(artifact, fixtures)
    lambdas = predict_lambdas(artifact, feats)
    gbm_rho = float(artifact.metadata.get("gbm_rho", -0.10))

    inputs: list[MatchInput] = []
    for i, row in fixtures.iterrows():
        mi = _row_to_match_input(row, lambdas[i, 0], lambdas[i, 1], gbm_rho)
        if mi:
            inputs.append(mi)

    recs = recommend_combinations(
        inputs,
        bankroll=bankroll,
        k_min=k_min, k_max=k_max,
        top_n_recommendations=args.top_n,
        include_compound=include_compound,
    )
    return _format_parlay(recs, bankroll, n_fixtures=len(fixtures))


def _run_pool(args, reader: Callable[[str], str]) -> str:
    fixtures_path = args.fixtures or _prompt(
        "请输入复式比赛 CSV 路径 (需含 pick 列)",
        default="data/fixtures/pool.csv",
        reader=reader,
    )
    bankroll = args.bankroll if args.bankroll is not None else _prompt_float(
        "请输入投注资金 (¥)",
        default=1000.0,
        reader=reader,
    )
    model_path = args.model or _prompt(
        "请输入模型路径",
        default="data/v4_model_cat",
        reader=reader,
    )
    fixtures = _read_pool_fixtures(fixtures_path)
    m = len(fixtures)
    n = args.pool_n if args.pool_n is not None else _prompt_int(
        f"复式: 每张票串关数 N (池中 {m} 场)",
        default=min(3, m), lo=1, hi=min(m, MAX_LEGS_PER_TICKET),
        reader=reader,
    )
    if args.max_total_budget is not None:
        max_budget: Optional[float] = args.max_total_budget
    else:
        raw = _prompt(
            "复式总预算上限 ¥ (留空 = 无限制)",
            default="", reader=reader,
        )
        max_budget = float(raw) if raw else None

    artifact = load_artifact(model_path)
    feats = build_features_for_fixtures(artifact, fixtures)
    lambdas = predict_lambdas(artifact, feats)
    gbm_rho = float(artifact.metadata.get("gbm_rho", -0.10))

    selections = []
    for i, row in fixtures.iterrows():
        sel = _row_to_selection(row, lambdas[i, 0], lambdas[i, 1], gbm_rho)
        if sel is not None:
            selections.append(sel)

    rec = recommend_pool(
        selections, n=n,
        bankroll=bankroll,
        max_total_budget=max_budget,
    )
    return _format_pool(rec, bankroll, max_budget)


# ---------- CLI entrypoint -------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="V6 W9 — 竞彩 单关/串关/复式 交互推荐入口",
    )
    p.add_argument("--type", choices=["single", "parlay", "pool"], default=None,
                   help="跳过类型菜单, 直接走指定流程")
    p.add_argument("--fixtures", default=None, help="比赛 CSV")
    p.add_argument("--model", default=None, help="V4 artifact 路径")
    p.add_argument("--bankroll", type=float, default=None)
    p.add_argument("--out", default=None, help="输出 markdown 文件 (默认 stdout)")

    # parlay-specific
    p.add_argument("--k-min", type=int, default=None, help="串关下限 (parlay)")
    p.add_argument("--k-max", type=int, default=None, help="串关上限 (parlay)")
    p.add_argument("--top-n", type=int, default=10, help="parlay top-N 推荐数")
    p.add_argument("--include-compound", action="store_true",
                   help="parlay 加入内选 (多选合一)")

    # single-specific
    p.add_argument("--top-per-match", type=int, default=1,
                   help="single 每场最多推荐多少注 (默认 1)")

    # pool-specific
    p.add_argument("--pool-n", type=int, default=None,
                   help="复式: 每张票 N 串 1")
    p.add_argument("--max-total-budget", type=float, default=None,
                   help="复式: 总预算上限 ¥")
    return p


def main(argv: list[str] | None = None,
         reader: Callable[[str], str] = input) -> int:
    args = _build_parser().parse_args(argv)

    bet_type = args.type
    if bet_type is None:
        print(BANNER, file=sys.stderr)
        print(TYPE_MENU, file=sys.stderr)
        choice = _prompt_choice(
            "你的选择",
            choices=["1", "2", "3", "q"],
            default="1",
            reader=reader,
        )
        if choice == "q":
            print("再见 👋", file=sys.stderr)
            return 0
        bet_type = {"1": "single", "2": "parlay", "3": "pool"}[choice]

    try:
        if bet_type == "single":
            out = _run_single(args, reader)
        elif bet_type == "parlay":
            out = _run_parlay(args, reader)
        elif bet_type == "pool":
            out = _run_pool(args, reader)
        else:  # pragma: no cover - argparse already enforced
            raise ValueError(f"unknown bet type: {bet_type}")
    except FileNotFoundError as e:
        print(f"ERROR: 找不到文件 — {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"ERROR: 输入有误 — {e}", file=sys.stderr)
        return 1

    if args.out:
        out_p = Path(args.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(out, encoding="utf-8")
        print(f"已写入 {out_p}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
