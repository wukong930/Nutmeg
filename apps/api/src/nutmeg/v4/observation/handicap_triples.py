"""让球三元组组装器 — 〈竞彩让球 SP × Pinnacle 收盘重构 P × 让球结算结果〉.

Reads the forward-captured tables (``jingcai_sp`` hhad rows for the 竞彩让球 SP +
result, ``odds_snapshots`` line history for the Pinnacle close) and assembles, per
settled 让球 match, the EV-vs-realized truth:

    EV(让胜/让平/让负) = P(Pinnacle 收盘 de-vig, 在竞彩让球线上重构) × 竞彩让球 SP − 1

This is the 让球 half of the proprietary triple that can ONLY be captured forward
— historical 竞彩让球 SP is not recoverable from any public source (sporttery +
500 both excluded, see ``docs/parlay_soft_water_research.md`` §5). The
reconstruction MIRRORS serving exactly (``routes._model_board_handicap_lines``):
de-vig Pinnacle 1X2 + O/U → ``fit_lambdas`` → ``implied_handicap_lines`` evaluated
at the 竞彩 integer 让球 line. Settlement reuses
``observation.settlement._outcome_handicap_1x2`` (``diff = (hg+hcap) − ag``).

Pure read + compute — does NOT touch the capture or serving chain, writes no table.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from nutmeg.v4.model.market_handicap import devig_over, implied_handicap_lines
from nutmeg.v4.observation.settlement import _outcome_handicap_1x2

# 让胜 / 让平 / 让负 — the 3-way 竞彩让球 market, in jc_{home,draw,away} order.
_OUTCOME_IDX = {"H": 0, "D": 1, "A": 2}
_OUTCOME_ZH = {"H": "让胜", "D": "让平", "A": "让负"}


def _devig_1x2(h, d, a) -> list[float] | None:
    """Multiplicative de-vig of 1X2 decimal odds → fair probs. Mirrors
    ``routes._pinnacle_devig_1x2``; kept local so this observation/CLI module
    never imports the FastAPI layer. Rejects any leg ≤ 1.0 (garbage)."""
    try:
        h, d, a = float(h), float(d), float(a)
    except (TypeError, ValueError):
        return None
    if h <= 1.0 or d <= 1.0 or a <= 1.0:
        return None
    inv = [1.0 / h, 1.0 / d, 1.0 / a]
    s = sum(inv)
    return [x / s for x in inv] if s > 0 else None


@dataclass
class HandicapTriple:
    """One settled 让球 match with its three legs joined."""

    match_date: str
    league: str
    home_team: str
    away_team: str
    handicap_home: int
    jc: tuple[float, float, float]          # 竞彩让球 SP (让胜, 让平, 让负)
    p_pin: tuple[float, float, float]       # Pinnacle 收盘重构 P at the 竞彩 line
    home_goals: int
    away_goals: int
    result: str                              # "H"/"D"/"A" — handicap-adjusted outcome
    ev: tuple[float, float, float]           # per-outcome EV = p_pin × jc − 1
    pinnacle_captured_at: str                # which snapshot served as the "close"

    @property
    def best_ev_outcome(self) -> str:
        return ["H", "D", "A"][max(range(3), key=lambda k: self.ev[k])]

    @property
    def best_ev(self) -> float:
        return max(self.ev)

    @property
    def best_ev_won(self) -> bool:
        return self.best_ev_outcome == self.result


def assemble_handicap_triples(db_path: str) -> list[HandicapTriple]:
    """Join settled 竞彩让球 SP rows to their Pinnacle close + reconstruct the
    3-way 让球 P, returning one :class:`HandicapTriple` per match that has all
    three legs. Matches that can't be priced (no Pinnacle 1X2 close, fit raises,
    or the 竞彩 SP / score is incomplete) are skipped, not faked."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    jc_rows = cur.execute(
        "SELECT * FROM jingcai_sp WHERE market='hhad' "
        "AND handicap_home IS NOT NULL "
        "AND home_goals IS NOT NULL AND away_goals IS NOT NULL "
        "ORDER BY match_date, home_team"
    ).fetchall()

    triples: list[HandicapTriple] = []
    for r in jc_rows:
        jc_raw = (r["jc_home"], r["jc_draw"], r["jc_away"])
        if any(x is None for x in jc_raw):
            continue
        # Pinnacle "close" = freshest snapshot with a full 1X2 for this match.
        snap = cur.execute(
            "SELECT * FROM odds_snapshots WHERE match_date=? AND home_team=? "
            "AND away_team=? AND psc_home IS NOT NULL AND psc_draw IS NOT NULL "
            "AND psc_away IS NOT NULL ORDER BY captured_at DESC LIMIT 1",
            (r["match_date"], r["home_team"], r["away_team"]),
        ).fetchone()
        if snap is None:
            continue
        fair = _devig_1x2(snap["psc_home"], snap["psc_draw"], snap["psc_away"])
        if fair is None:
            continue
        hcap = int(r["handicap_home"])
        p_over = devig_over(snap["psc_over"], snap["psc_under"])
        ou_line = float(snap["ou_line"] or 2.5)
        try:
            # lines=[hcap] → evaluate exactly the 竞彩 line on the fitted grid.
            board = implied_handicap_lines(
                fair[0], fair[1], fair[2], p_over, ou_line=ou_line, lines=[hcap]
            )
        except Exception:  # noqa: BLE001 — an unfittable grid just drops this match
            continue
        _, ph, pd_, pa = board[0]
        p_pin = (float(ph), float(pd_), float(pa))
        jc = (float(jc_raw[0]), float(jc_raw[1]), float(jc_raw[2]))
        ev = tuple(p_pin[k] * jc[k] - 1.0 for k in range(3))
        result = _outcome_handicap_1x2(
            int(r["home_goals"]), int(r["away_goals"]), hcap
        )
        triples.append(
            HandicapTriple(
                match_date=r["match_date"],
                league=r["league"] or "",
                home_team=r["home_team"],
                away_team=r["away_team"],
                handicap_home=hcap,
                jc=jc,
                p_pin=p_pin,
                home_goals=int(r["home_goals"]),
                away_goals=int(r["away_goals"]),
                result=result,
                ev=ev,  # type: ignore[arg-type]
                pinnacle_captured_at=snap["captured_at"],
            )
        )
    con.close()
    return triples


def summarize(triples: list[HandicapTriple], *, min_ev: float = 0.05) -> dict:
    """Aggregate the betting-truth numbers: do +EV 让球 picks actually win, and
    what flat-stake ROI did they realize vs the EV that flagged them? Plus the
    Brier score of the reconstructed 让球 P against the realized outcome (a live,
    forward calibration check of the market-reverse reconstruction)."""
    n = len(triples)
    picks = [t for t in triples if t.best_ev >= min_ev]
    won = sum(1 for t in picks if t.best_ev_won)
    avg_ev = sum(t.best_ev for t in picks) / len(picks) if picks else None
    roi = None
    if picks:
        # Flat 1-unit stake on each +EV pick: +(odds−1) if it covered, else −1.
        pnl = sum(
            (t.jc[_OUTCOME_IDX[t.best_ev_outcome]] - 1.0) if t.best_ev_won else -1.0
            for t in picks
        )
        roi = pnl / len(picks)
    brier = None
    if n:
        brier = (
            sum(
                sum(
                    (t.p_pin[k] - (1.0 if _OUTCOME_IDX[t.result] == k else 0.0)) ** 2
                    for k in range(3)
                )
                for t in triples
            )
            / n
        )
    return {
        "n": n,
        "n_positive": len(picks),
        "n_positive_won": won,
        "positive_hit_rate": (won / len(picks)) if picks else None,
        "avg_positive_ev": avg_ev,
        "realized_flat_roi": roi,
        "brier_reconstructed_p": brier,
    }


def format_report(
    triples: list[HandicapTriple], *, min_ev: float = 0.05, limit: int | None = None
) -> str:
    s = summarize(triples, min_ev=min_ev)
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("让球三元组 — 〈竞彩让球 SP × Pinnacle 收盘重构 P × 让球结算〉")
    lines.append("=" * 72)
    lines.append(
        "诚实横幅:EV = P(Pinnacle 去vig 重构) × 竞彩让球 SP − 1。当前样本几乎全是"
    )
    lines.append(
        "世界杯(已知撞 −EV vig 墙),这里的价值是【验证机器 + 首批让球 EV-vs-realized】,"
    )
    lines.append("不是可下注信号。受训联赛三元组要等秋天。")
    lines.append("-" * 72)

    shown = triples if limit is None else triples[:limit]
    for t in shown:
        o = t.best_ev_outcome
        mark = "✅中" if t.best_ev_won else "❌空"
        star = " ★+EV" if t.best_ev >= min_ev else ""
        lines.append(
            f"  {t.match_date}  {t.home_team[:14]:14} {t.handicap_home:+d} "
            f"{t.away_team[:14]:14}  {t.home_goals}-{t.away_goals}  "
            f"最优={_OUTCOME_ZH[o]} P={t.p_pin[_OUTCOME_IDX[o]]:.2f} "
            f"SP={t.jc[_OUTCOME_IDX[o]]:.2f} EV={t.best_ev*100:+.1f}% "
            f"→ 实际={_OUTCOME_ZH[t.result]} {mark}{star}"
        )
    if limit is not None and len(triples) > limit:
        lines.append(f"  … 另有 {len(triples) - limit} 条未显示")

    lines.append("-" * 72)
    lines.append(f"  三元组总数: {s['n']}")
    if s["n_positive"]:
        lines.append(
            f"  +EV(≥{min_ev:+.0%})选择: {s['n_positive']} 注 | "
            f"命中 {s['n_positive_won']}/{s['n_positive']} "
            f"({s['positive_hit_rate']*100:.0f}%) | "
            f"均 EV {s['avg_positive_ev']*100:+.1f}% | "
            f"★ 实测均注 ROI {s['realized_flat_roi']*100:+.1f}%"
        )
        lines.append(
            "    ROI ≪ 均EV ⇒ 边被 vig 吃掉 / EV 虚高;ROI ≈ 均EV ⇒ 边真实(需更多样本)"
        )
    else:
        lines.append(f"  +EV(≥{min_ev:+.0%})选择: 0 注(诚实空仓 — 符合 WC −EV 预期)")
    if s["brier_reconstructed_p"] is not None:
        lines.append(
            f"  让球重构 P 的 Brier(越低越准): {s['brier_reconstructed_p']:.4f} "
            f"(3-way 满分基准 0.667;<0.6 算有信息)"
        )
    lines.append("=" * 72)
    return "\n".join(lines)
