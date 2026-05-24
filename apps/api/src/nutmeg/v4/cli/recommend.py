"""V4 recommend CLI — daily product entry point.

Usage:
    python -m nutmeg.v4.cli.recommend \
        --fixtures path/to/today.csv \
        --model data/v4_model \
        --bankroll 1000 \
        [--out recommendations.json] \
        [--format md|json]

Input CSV columns (one row per match):
  date              YYYY-MM-DD
  league            canonical name (must match training, e.g. EPL, ESP_LA_LIGA)
  home_team         must match training spelling
  away_team
  psc_home          Pinnacle (or proxy) 1X2 odds — required
  psc_draw
  psc_away
  handicap_home     China integer handicap (e.g. -1, 0, +1). Empty = no handicap market.
  odds_1x2_H/D/A    lottery 1X2 odds (what the player actually bets at)
  odds_handicap_H/D/A   lottery handicap-1X2 odds (when handicap_home present)
  psc_over25        Pinnacle O/U 2.5 odds (optional, used as feature)
  psc_under25       (optional)
  ahch              European Asian handicap closing line (optional feature)

Output:
  Markdown report (default) or JSON listing top-N recommended combinations
  with stake, Kelly amount, hit probability, EV, leg breakdown.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from nutmeg.v4.combo import MatchInput, recommend_combinations
from nutmeg.v4.model.dixon_coles import grid_to_1x2, grid_to_handicap_1x2, score_grid
from nutmeg.v4.model.persist import (
    build_features_for_fixtures,
    load_artifact,
    predict_lambdas,
)


def _read_fixtures(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = ["date", "league", "home_team", "away_team",
                "psc_home", "psc_draw", "psc_away"]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"input CSV missing column: {c}")
    df["date"] = pd.to_datetime(df["date"])
    return df


def _row_to_match_input(row, lambdas_h: float, lambdas_a: float, gbm_rho: float) -> MatchInput | None:
    """Convert a fixtures row + GBM lambdas to a MatchInput for the combo layer."""
    odds_1x2 = None
    if "odds_1x2_H" in row.index:
        h, d, a = row["odds_1x2_H"], row["odds_1x2_D"], row["odds_1x2_A"]
        if not (pd.isna(h) or pd.isna(d) or pd.isna(a)):
            odds_1x2 = {"H": float(h), "D": float(d), "A": float(a)}

    odds_hc = None
    handicap = None
    if "handicap_home" in row.index and not pd.isna(row["handicap_home"]):
        handicap = int(row["handicap_home"])
        if "odds_handicap_H" in row.index:
            h, d, a = row.get("odds_handicap_H"), row.get("odds_handicap_D"), row.get("odds_handicap_A")
            if not (pd.isna(h) or pd.isna(d) or pd.isna(a)):
                odds_hc = {"H": float(h), "D": float(d), "A": float(a)}

    if not odds_1x2 and not odds_hc:
        return None  # no markets to bet on

    return MatchInput(
        match_id=f"{row['league']}_{row['home_team']}_vs_{row['away_team']}",
        lambda_home=float(lambdas_h),
        lambda_away=float(lambdas_a),
        rho=gbm_rho,
        handicap_home=handicap if odds_hc else None,
        odds_1x2=odds_1x2,
        odds_handicap_1x2=odds_hc,
    )


def _format_markdown(
    fixtures: pd.DataFrame,
    lambdas: np.ndarray,
    recs,
    gbm_rho: float,
    bankroll: float,
    artifact_meta: dict,
) -> str:
    lines = []
    lines.append("# 今日推荐组合 (V4)")
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append(f"_Model trained at: {artifact_meta.get('trained_at_utc', '?')}, cutoff: {artifact_meta.get('training_cutoff', '?')}_")
    lines.append(f"_Bankroll: ¥{bankroll:.0f}_")
    lines.append("")

    lines.append("## 单场预测")
    lines.append("")
    lines.append("| 比赛 | λ_home | λ_away | P(主) | P(平) | P(客) | 让球数 | P(让胜) | P(让平) | P(让负) |")
    lines.append("|------|-------:|-------:|------:|------:|------:|-------:|--------:|--------:|--------:|")
    for i, row in fixtures.iterrows():
        lh, la = lambdas[i]
        grid = score_grid(lh, la, rho=gbm_rho)
        p_h, p_d, p_a = grid_to_1x2(grid)
        if "handicap_home" in row.index and not pd.isna(row["handicap_home"]):
            hk = int(row["handicap_home"])
            hp_h, hp_d, hp_a = grid_to_handicap_1x2(grid, handicap_home=hk)
            hp_h_s = f"{hp_h:.2%}"; hp_d_s = f"{hp_d:.2%}"; hp_a_s = f"{hp_a:.2%}"
            hc_s = str(hk)
        else:
            hp_h_s = hp_d_s = hp_a_s = "—"; hc_s = "—"
        lines.append(
            f"| {row['home_team']:<14} vs {row['away_team']:<14} | "
            f"{lh:.2f} | {la:.2f} | "
            f"{p_h:.2%} | {p_d:.2%} | {p_a:.2%} | {hc_s} | "
            f"{hp_h_s} | {hp_d_s} | {hp_a_s} |"
        )
    lines.append("")

    lines.append(f"## 串关推荐 (top {len(recs)})")
    lines.append("")
    if not recs:
        lines.append("**无 +EV 组合：今日所有市场无值得下注的机会**（系统建议 no-bet）。")
        lines.append("")
        return "\n".join(lines)

    for r in recs:
        p = r.parlay
        compound = " (复式)" if p.is_compound else ""
        lines.append(f"### #{r.rank} — {p.k} 串 1{compound}")
        lines.append(f"- 命中率: **{p.hit_probability:.1%}**")
        lines.append(f"- EV/单位: **{p.ev_per_unit:+.1%}**")
        lines.append(f"- Kelly 推荐资金: **¥{r.kelly.recommended_stake:.2f}** ({r.kelly.capped_kelly:.1%} of bankroll)")
        lines.append(f"- 预期回报: ¥{r.kelly.expected_return:+.2f}")
        lines.append(f"- 投入单位数 (复式): {r.stake_units}")
        lines.append("")
        lines.append("  **各场选择**:")
        for leg in p.legs:
            sels_str = " OR ".join(
                f"{s.outcome}@{s.odds:.2f} (模型概率 {s.probability:.0%})"
                for s in leg.selections
            )
            market_label = "胜平负" if leg.market_type == "1x2" else "让球胜平负"
            lines.append(f"  - `{leg.match_id}` [{market_label}] → {sels_str}")
        lines.append("")

    total_stake = sum(r.kelly.recommended_stake for r in recs)
    total_ev = sum(r.kelly.expected_return for r in recs)
    lines.append(f"### 汇总")
    lines.append(f"- 总投入: ¥{total_stake:.2f} ({total_stake/bankroll:.1%} of bankroll)")
    lines.append(f"- 预期总回报: ¥{total_ev:+.2f}")
    lines.append("")
    lines.append("> ⚠️ 系统不进行自动投注；推荐仅供参考。")
    return "\n".join(lines)


def _format_json(fixtures, lambdas, recs, bankroll, artifact_meta):
    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": {
            "trained_at_utc": artifact_meta.get("trained_at_utc"),
            "training_cutoff": artifact_meta.get("training_cutoff"),
        },
        "bankroll": bankroll,
        "n_fixtures": len(fixtures),
        "single_match_predictions": [
            {
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "league": row["league"],
                "date": str(row["date"].date()) if hasattr(row["date"], "date") else str(row["date"]),
                "lambda_home": float(lambdas[i, 0]),
                "lambda_away": float(lambdas[i, 1]),
            }
            for i, row in fixtures.iterrows()
        ],
        "recommendations": [
            {
                "rank": r.rank,
                "k_legs": r.parlay.k,
                "is_compound": r.parlay.is_compound,
                "stake_units": r.stake_units,
                "kelly_recommended_stake": r.kelly.recommended_stake,
                "kelly_capped_fraction": r.kelly.capped_kelly,
                "expected_return": r.kelly.expected_return,
                "hit_probability": r.parlay.hit_probability,
                "ev_per_unit": r.parlay.ev_per_unit,
                "log_growth": r.kelly_log_growth,
                "legs": [
                    {
                        "match_id": leg.match_id,
                        "market_type": leg.market_type,
                        "selections": [
                            {
                                "outcome": s.outcome,
                                "probability": s.probability,
                                "odds": s.odds,
                                "edge": s.edge,
                            }
                            for s in leg.selections
                        ],
                    }
                    for leg in r.parlay.legs
                ],
            }
            for r in recs
        ],
    }
    return json.dumps(out, indent=2, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V4 daily recommendation CLI")
    parser.add_argument("--fixtures", required=True, help="Today's fixture CSV")
    # post-v9 P1#18: default flipped from V5 W12 CatBoost ('data/v4_model')
    # to V6 W7 lineup-aware CatBoost. Decision rationale: 3-chunk 24/25
    # backtest (Sep-Nov / Dec-Feb / Mar-May) shows lineup-aware leads
    # default by +16/+25/+46pp ROI consistently (all 3 chunks). Default
    # actually LOSES money in all 3 sub-periods (-2.6/-28.5/-16.8% ROI)
    # while lineup-aware is mean-positive. See docs/post_v9_p1_18_ship_lineup_aware.md.
    parser.add_argument("--model", default="data/v4_model_cat_lineups", help="Trained artifact directory")
    parser.add_argument("--bankroll", type=float, default=1000.0)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-hit-probability", type=float, default=0.05)
    parser.add_argument("--min-kelly-stake", type=float, default=2.0)
    parser.add_argument("--kelly-fraction", type=float, default=0.25)
    parser.add_argument("--max-stake-fraction", type=float, default=0.05)
    parser.add_argument("--include-compound", action="store_true",
                        help="Enumerate 复式 legs (default off; turn on for fuller search)")
    parser.add_argument("--out", default=None, help="Output file path (default: stdout)")
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--record-to", default=None,
                        help="Optional SQLite path to record this recommendation session for later ROI tracking")
    parser.add_argument(
        "--snapshot-phase",
        choices=("pre_close", "closing", "post_close"),
        default="closing",
        help="Which market phase this recommendation snapshot reflects. "
        "'pre_close' for ≥60 min before kickoff, 'closing' (default) at "
        "closing-line publish, 'post_close' for diagnostic after-the-fact "
        "snapshots. Used by W8 live_vs_backtest to compare same-fixture "
        "predictions across phases.",
    )
    args = parser.parse_args(argv)

    fixtures = _read_fixtures(args.fixtures)
    artifact = load_artifact(args.model)

    feats = build_features_for_fixtures(artifact, fixtures)
    lambdas = predict_lambdas(artifact, feats)

    # Build MatchInputs
    inputs: list[MatchInput] = []
    gbm_rho = artifact.metadata.get("gbm_rho", -0.10)
    for i, row in fixtures.iterrows():
        mi = _row_to_match_input(row, lambdas[i, 0], lambdas[i, 1], gbm_rho)
        if mi:
            inputs.append(mi)

    recs = recommend_combinations(
        inputs,
        bankroll=args.bankroll,
        k_min=2, k_max=8,
        top_n_recommendations=args.top_n,
        min_hit_probability=args.min_hit_probability,
        min_kelly_stake=args.min_kelly_stake,
        kelly_fraction=args.kelly_fraction,
        max_stake_fraction=args.max_stake_fraction,
        include_compound=args.include_compound,
    )

    if args.format == "md":
        out = _format_markdown(fixtures, lambdas, recs, gbm_rho, args.bankroll, artifact.metadata)
    else:
        out = _format_json(fixtures, lambdas, recs, args.bankroll, artifact.metadata)

    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(out)

    # Optional: record session to observation DB for ROI tracking
    if args.record_to:
        from nutmeg.v4.observation import record_session
        # Build the same JSON response structure used by the API
        from datetime import datetime, timezone
        single_preds = []
        for i, row in fixtures.iterrows():
            from nutmeg.v4.model.dixon_coles import score_grid, grid_to_1x2, grid_to_handicap_1x2
            lh, la = lambdas[i]
            grid = score_grid(float(lh), float(la), rho=gbm_rho)
            ph, pd_, pa = grid_to_1x2(grid)
            entry = {
                "date": str(row["date"].date()) if hasattr(row["date"], "date") else str(row["date"]),
                "league": row["league"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "lambda_home": float(lh),
                "lambda_away": float(la),
                "p_home_1x2": float(ph),
                "p_draw_1x2": float(pd_),
                "p_away_1x2": float(pa),
                "handicap_home": int(row["handicap_home"]) if "handicap_home" in row.index and not pd.isna(row["handicap_home"]) else None,
            }
            if entry["handicap_home"] is not None:
                hph, hpd, hpa = grid_to_handicap_1x2(grid, handicap_home=entry["handicap_home"])
                entry["p_home_handicap"] = float(hph)
                entry["p_draw_handicap"] = float(hpd)
                entry["p_away_handicap"] = float(hpa)
            single_preds.append(entry)
        recommendations_json = []
        for r in recs:
            recommendations_json.append({
                "rank": r.rank,
                "k_legs": r.parlay.k,
                "is_compound": r.parlay.is_compound,
                "stake_units": r.stake_units,
                "kelly_recommended_stake": r.kelly.recommended_stake,
                "expected_return": r.kelly.expected_return,
                "hit_probability": r.parlay.hit_probability,
                "ev_per_unit": r.parlay.ev_per_unit,
                "log_growth": r.kelly_log_growth,
                "legs": [
                    {"match_id": leg.match_id, "market_type": leg.market_type,
                     "selections": [
                         {"outcome": s.outcome, "odds": float(s.odds),
                          "probability": float(s.probability), "edge": float(s.edge)}
                         for s in leg.selections
                     ]}
                    for leg in r.parlay.legs
                ],
            })
        response_dict = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": {"training_cutoff": artifact.metadata.get("training_cutoff"),
                      "trained_at_utc": artifact.metadata.get("trained_at_utc")},
            "bankroll": args.bankroll,
            "n_fixtures": len(fixtures),
            "n_recommendations": len(recs),
            "single_match_predictions": single_preds,
            "recommendations": recommendations_json,
        }
        request_dict = {
            "fixtures_path": args.fixtures,
            "n_fixtures": len(fixtures),
            "bankroll": args.bankroll,
            "top_n": args.top_n,
            "min_hit_probability": args.min_hit_probability,
            "min_kelly_stake": args.min_kelly_stake,
        }
        session_id = record_session(
            args.record_to,
            request=request_dict,
            response=response_dict,
            snapshot_phase=args.snapshot_phase,
        )
        print(
            f"Recorded session #{session_id} (phase={args.snapshot_phase}) to {args.record_to}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
