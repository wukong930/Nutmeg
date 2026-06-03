"""nutmeg-recommend-pool — M-select-N compound parlay recommendation (V6 W3).

Workflow:
1. User supplies M matches (CSV) with closing odds + their pre-decided
   outcome per match (column `pick`: 1x2_H/D/A or hc_H/D/A)
2. System loads V4/V5 artifact, computes per-match probabilities, builds
   one Selection per (match, pick) row
3. Enumerates all C(M, N) tickets, sizes each with independent Kelly,
   quantizes to ¥2 multiples
4. Optionally rescales the whole pool to fit `--max-total-budget`
5. Outputs Markdown or JSON ticket recommendation

Example fixtures CSV (M=4 matches, each pre-picked):

    date,league,home_team,away_team,psc_home,psc_draw,psc_away,handicap_home,odds_1x2_H,odds_1x2_D,odds_1x2_A,odds_handicap_H,odds_handicap_D,odds_handicap_A,pick
    2025-08-17,EPL,Arsenal,Liverpool,2.20,3.40,3.40,,1.85,3.20,4.00,,,,1x2_H
    2025-08-17,EPL,Man City,Brighton,1.50,4.50,6.00,,1.45,4.30,7.00,,,,1x2_H
    2025-08-17,ESP_LA_LIGA,Real Madrid,Getafe,1.30,5.50,9.00,-1,1.30,5.50,9.00,1.95,3.40,3.85,hc_H
    2025-08-17,ITA_SERIE_A,Inter,Roma,2.05,3.50,3.70,,1.90,3.40,4.10,,,,1x2_H

Usage:

    nutmeg-recommend-pool --fixtures pool.csv --n 3 --bankroll 1000 \\
        --max-total-budget 200 --out tickets.md
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from nutmeg.v4.combo.compound_pool import (
    MAX_LEGS_PER_TICKET,
    STAKE_UNIT_CNY,
    PoolTicket,
    recommend_pool,
)
from nutmeg.v4.combo.selections import Selection
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


VALID_PICKS = {"1x2_H", "1x2_D", "1x2_A", "hc_H", "hc_D", "hc_A"}


def _read_pool_fixtures(path: str) -> pd.DataFrame:
    # V12: shared base reader (cli/_shared.py) + pool-specific `pick` column
    # and pick-value validation layered on top.
    from nutmeg.v4.cli._shared import read_fixtures_csv

    df = read_fixtures_csv(path, extra_required=["pick"], label="pool CSV")
    bad = df[~df["pick"].isin(VALID_PICKS)]
    if len(bad) > 0:
        raise ValueError(
            f"invalid pick values in rows {list(bad.index)}: "
            f"each pick must be one of {sorted(VALID_PICKS)}"
        )
    # build_features_for_fixtures requires several optional columns; fill
    # NaN defaults so the pool CSV doesn't need to carry O/U + Asian-handicap
    # market data that the user has no opinion on anyway.
    for optional_col in ("psc_over25", "psc_under25", "ahch"):
        if optional_col not in df.columns:
            df[optional_col] = float("nan")
    return df


def _row_to_selection(
    row: pd.Series,
    lambda_h: float,
    lambda_a: float,
    gbm_rho: float,
) -> Optional[Selection]:
    """Convert one pool row to ONE Selection based on the user's `pick`."""
    pick = row["pick"]
    grid = score_grid(float(lambda_h), float(lambda_a), rho=gbm_rho)
    match_id = f"{row['league']}_{row['home_team']}_vs_{row['away_team']}"

    if pick.startswith("1x2_"):
        outcome = pick.split("_", 1)[1]
        ph, pd_, pa = grid_to_1x2(grid)
        prob = {"H": ph, "D": pd_, "A": pa}[outcome]
        odds_col = f"odds_1x2_{outcome}"
        odds = row.get(odds_col)
        if odds is None or pd.isna(odds):
            # AUDIT FIX (B2): no 竞彩 SP → not bettable. Do NOT fall back to
            # psc_* (vigged Pinnacle); that = the EV-vs-Pinnacle noise bug.
            # The hc_X branch below already raises — match it.
            raise ValueError(
                f"row {match_id}: pick={pick} but odds_1x2_{outcome} missing (no Pinnacle fallback)"
            )
        return Selection(
            match_id=match_id,
            market_type="1x2",
            outcome=outcome,
            probability=float(prob),
            odds=float(odds),
        )

    # hc_X
    if pd.isna(row.get("handicap_home")):
        raise ValueError(
            f"row {match_id}: pick={pick} requires handicap_home column to be set"
        )
    handicap_home = int(row["handicap_home"])
    outcome = pick.split("_", 1)[1]
    hp_h, hp_d, hp_a = grid_to_handicap_1x2(grid, handicap_home=handicap_home)
    prob = {"H": hp_h, "D": hp_d, "A": hp_a}[outcome]
    odds_col = f"odds_handicap_{outcome}"
    odds = row.get(odds_col)
    if odds is None or pd.isna(odds):
        raise ValueError(
            f"row {match_id}: pick={pick} but odds_handicap_{outcome} missing"
        )
    return Selection(
        match_id=match_id,
        market_type="handicap_1x2",
        outcome=outcome,
        probability=float(prob),
        odds=float(odds),
    )


def _format_markdown(rec, fixtures, n: int, bankroll: float, max_budget: float | None) -> str:
    lines = []
    lines.append(f"# 复式过关推荐 ({rec.m} 选 {rec.n})")
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append(f"_Bankroll: ¥{bankroll:.0f}_  ¥{STAKE_UNIT_CNY:.0f}/张起投; max-budget: "
                 f"{'¥' + format(max_budget, '.0f') if max_budget else '无限制'}")
    lines.append("")

    lines.append("## 池中比赛")
    lines.append("")
    lines.append("| 比赛 | 玩法 | 选项 | 模型概率 | 赔率 | EV/单位 |")
    lines.append("|------|------|------|---------:|-----:|--------:|")
    for _, row in fixtures.iterrows():
        # Re-derive the leg the user picked (just for display)
        pick = row["pick"]
        market = "胜平负" if pick.startswith("1x2_") else "让球胜平负"
        outcome = pick.split("_", 1)[1]
        match_label = f"{row['home_team']} vs {row['away_team']}"
        lines.append(f"| {match_label} | {market} | {outcome} | — | — | — |")
    lines.append("")

    lines.append(f"## 推荐票 (共 {rec.n_combinations} 张, 选中 {len(rec.selected_tickets)} 张)")
    lines.append("")
    if not rec.selected_tickets:
        lines.append("**无可下注组合**（所有 N 串 1 票 EV ≤ 0 或 Kelly 仓位 < ¥2 起投）。")
        lines.append("")
        return "\n".join(lines)

    lines.append("| # | 命中率 | 总赔率 | EV/单位 | 投注 | 预期回报 | 选项 |")
    lines.append("|--:|-------:|-------:|--------:|-----:|---------:|------|")
    for i, t in enumerate(rec.selected_tickets, 1):
        legs_label = " + ".join(
            f"{leg.match_id.split('_vs_')[0].split('_', 1)[-1]}-vs-"
            f"{leg.match_id.split('_vs_')[-1]}:{leg.outcome}"
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
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V6 W3 M-select-N compound parlay")
    p.add_argument("--fixtures", required=True,
                   help="CSV: M matches with date,league,teams,odds,handicap_home,pick")
    # post-v9 P1#18: flipped to lineup-aware (see docs/post_v9_p1_18_ship_lineup_aware.md)
    p.add_argument("--model", default="data/v4_model_cat_lineups", help="Artifact dir")
    p.add_argument("--n", type=int, required=True,
                   help=f"Legs per ticket (1..{MAX_LEGS_PER_TICKET})")
    p.add_argument("--bankroll", type=float, default=1000.0)
    p.add_argument("--max-total-budget", type=float, default=None,
                   help="If set, rescale all stakes to fit this total")
    p.add_argument("--kelly-fraction", type=float, default=0.25)
    p.add_argument("--max-stake-fraction", type=float, default=0.05,
                   help="Per-ticket cap as fraction of bankroll")
    p.add_argument("--out", default=None)
    p.add_argument("--format", choices=["md", "json"], default="md")
    args = p.parse_args(argv)

    fixtures = _read_pool_fixtures(args.fixtures)
    m = len(fixtures)
    if m < args.n:
        print(f"ERROR: --n={args.n} but only {m} matches in pool", file=sys.stderr)
        return 2

    art = load_artifact(args.model)
    feats = build_features_for_fixtures(art, fixtures)
    lambdas = predict_lambdas(art, feats)
    gbm_rho = float(art.metadata.get("gbm_rho", -0.10))

    selections: list[Selection] = []
    for i, row in fixtures.iterrows():
        sel = _row_to_selection(row, lambdas[i, 0], lambdas[i, 1], gbm_rho)
        if sel is None:
            print(f"WARN: skipping row {i} (no valid selection)", file=sys.stderr)
            continue
        selections.append(sel)

    rec = recommend_pool(
        selections, n=args.n,
        bankroll=args.bankroll,
        max_total_budget=args.max_total_budget,
        kelly_fraction=args.kelly_fraction,
        max_stake_fraction_per_ticket=args.max_stake_fraction,
    )

    if args.format == "json":
        payload = {
            "m": rec.m, "n": rec.n, "n_combinations": rec.n_combinations,
            "total_stake": rec.total_stake,
            "total_expected_return": rec.total_expected_return,
            "tickets": [
                {
                    "legs": [
                        {"match_id": l.match_id, "market_type": l.market_type,
                         "outcome": l.outcome, "odds": l.odds, "probability": l.probability}
                        for l in t.legs
                    ],
                    "hit_probability": t.hit_probability,
                    "combined_odds": t.combined_odds,
                    "ev_per_unit": t.ev_per_unit,
                    "stake": t.stake,
                    "expected_return": t.expected_return,
                }
                for t in rec.selected_tickets
            ],
        }
        out = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        out = _format_markdown(rec, fixtures, args.n, args.bankroll, args.max_total_budget)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
