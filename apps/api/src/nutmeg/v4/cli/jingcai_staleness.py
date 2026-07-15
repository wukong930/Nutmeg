"""nutmeg-jingcai-staleness — the soft-book edge map.

竞彩 freezes its SP (~23:00 daily); Pinnacle keeps drifting to kickoff. EV can
only live where 竞彩's frozen line is STALE vs Pinnacle's close. This joins the
captured 竞彩 SP (``jingcai_sp``) with Pinnacle's CLOSING line (``odds_snapshots``,
the last observed state per fixture — the CLV foundation built in 体检 A1) and
the settled result, then buckets the gap and reports REALIZED ROI.

The honest point: a gap is NOT edge. 竞彩 can look "soft" precisely because it
froze on a price that's about to be right — that's a trap, not value. Only the
realized ROI per bucket (did betting the +EV candidates actually win?) tells us
whether this axis has anything. Sparse for weeks by design; it accrues as the
user prices matches in 市场模式.
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
from collections import defaultdict

# outcome index: 0=home, 1=draw, 2=away (matches jingcai_sp.ft_outcome)
_LABELS = ("主胜", "平局", "客胜")
_HC_LABELS = ("让胜", "让平", "让负")
_MIN_EV = 0.05  # the project's +EV betting threshold


def _devig3(h, d, a) -> tuple[float, float, float] | None:
    """3-way de-vig (WPO — corrects favourite-longshot bias) → fair
    (P_home, P_draw, P_away). Single source = ``nutmeg.v4.model.devig``. This is
    the soft-water EV measurement口径; the WPO upgrade tightens longshot fair P
    (fewer false +EV cold-traps). See ``docs/devig_method_comparison.md``."""
    from nutmeg.v4.model.devig import devig_1x2
    return devig_1x2(h, d, a)


def _pinn_close(conn: sqlite3.Connection, row: dict) -> tuple | None:
    """Pinnacle CLOSING line (last observed state): (psc_home, psc_draw, psc_away,
    psc_over, psc_under, ou_line). 1X2 for 'had'; the O/U is needed to reverse-fit
    the grid for 'hhad'. By fixture_id, then by (date, teams), then a national-team
    alias fallback (Czech Republic↔Czechia &c)."""
    cols = "psc_home, psc_draw, psc_away, psc_over, psc_under, ou_line"
    # 体检 B2 — the CLOSE must be a PRE-kickoff line; skip in-play snapshots
    # (a leading team's live line 1.06/…/53.96 would fake CLV). NULL kickoff
    # (pre-2026-07-01 rows) can't be judged → kept, as before.
    _pre_ko = "AND (kickoff_utc IS NULL OR captured_at < kickoff_utc) "
    if row.get("fixture_id"):
        r = conn.execute(
            f"SELECT {cols} FROM odds_snapshots "
            f"WHERE fixture_id=? {_pre_ko}ORDER BY captured_at DESC, id DESC LIMIT 1",
            (row["fixture_id"],)).fetchone()
        if r:
            return r
    r = conn.execute(
        f"SELECT {cols} FROM odds_snapshots "
        f"WHERE match_date=? AND home_team=? AND away_team=? {_pre_ko}"
        "ORDER BY captured_at DESC, id DESC LIMIT 1",
        (row["match_date"], row["home_team"], row["away_team"])).fetchone()
    if r:
        return r
    return _alias_close(conn, row, cols)


def _alias_close(conn: sqlite3.Connection, row: dict, cols: str) -> tuple | None:
    """National-team alias fallback when the exact (date, home, away) join misses.

    Resolve both 竞彩 names to eloratings codes and accept the freshest same-day
    odds_snapshots row whose BOTH teams resolve to the SAME (home, away) code pair —
    but only when that resolves to a UNIQUE fixture (≥2 distinct fixtures sharing
    codes → bail, never guess). Fixes spelling splits like 'Czech Republic'(竞彩) vs
    'Czechia'(Pinnacle) without the false-join risk of fuzzy matching. Club aliases
    stay autumn-gated: a non-national name → code None → return None.
    See [[cross-source-team-name-mismatch]]."""
    from nutmeg.v4.data.national_team_name_to_elo import lookup_elo_code
    hc, ac = lookup_elo_code(row["home_team"]), lookup_elo_code(row["away_team"])
    if hc is None or ac is None:
        return None
    rows = conn.execute(
        f"SELECT {cols}, home_team, away_team FROM odds_snapshots "
        "WHERE match_date=? AND (kickoff_utc IS NULL OR captured_at < kickoff_utc) "
        "ORDER BY captured_at DESC, id DESC",  # 体检 B2 — pre-kickoff only
        (row["match_date"],)).fetchall()
    hits = [r for r in rows
            if lookup_elo_code(r[6]) == hc and lookup_elo_code(r[7]) == ac]
    if not hits or len({(r[6], r[7]) for r in hits}) != 1:
        return None  # no alias match, or ambiguous (≥2 distinct fixtures) → don't guess
    return tuple(hits[0][i] for i in range(6))  # the cols, dropping the trailing names


def _hhad_pinn_and_outcome(close: tuple, row: dict) -> tuple | None:
    """For a 让球 (hhad) row: reverse-fit Pinnacle's grid from its CLOSING 1X2 +
    O/U, read the (让胜, 让平, 让负) cover P at the 竞彩 handicap line, and the
    realized covered outcome (0 让胜 / 1 让平 / 2 让负). None if not computable."""
    line = row["handicap_home"]
    if line is None or row["home_goals"] is None or row["away_goals"] is None:
        return None
    fair = _devig3(close[0], close[1], close[2])
    if fair is None:
        return None
    from nutmeg.v4.model.market_handicap import devig_over, implied_handicap_lines
    p_over = devig_over(close[3], close[4]) if (close[3] and close[4]) else None
    ou_line = close[5] if close[5] is not None else 2.5
    try:
        lines = implied_handicap_lines(
            fair[0], fair[1], fair[2], p_over, ou_line=ou_line, lines=(int(line),))
    except Exception:  # noqa: BLE001 — a fit failure still drops the row, but LOUDLY
        # 体检 W1 2026-07-15 — 同 clv_ledger:拟合失败丢行要带线值留痕,
        # 深线成串失败 = S6 测量掉队偏置,不能只让 N 无声变小。
        logging.getLogger(__name__).warning(
            "hhad 网格拟合失败(line=%s)— 该行丢弃;成串出现=深线掉队偏置", line)
        return None
    if not lines:
        return None
    _, ph, pd_, pa = lines[0]
    m = (row["home_goals"] - row["away_goals"]) + int(line)   # margin after handicap
    covered = 0 if m > 0 else (1 if m == 0 else 2)
    return (ph, pd_, pa), covered


def _ev_band(ev: float) -> str:
    if ev < 0.05:
        return "<5%(非候选)"
    if ev < 0.10:
        return "5–10%"
    if ev < 0.20:
        return "10–20%"
    return "≥20%"


def _drift_band(drift: float) -> str:
    if drift < 0.02:
        return "Pinnacle 几乎没动(<2pp)"
    if drift < 0.05:
        return "动 2–5pp"
    return "动 ≥5pp(竞彩冻结后信息多)"


def analyze(db_path: str, *, min_ev: float = _MIN_EV) -> dict:
    """Per settled 竞彩 observation: EV(Pinnacle-close-fair × 竞彩SP − 1) per
    outcome, the +EV candidates, and their realized win/ROI. Returns buckets."""
    from nutmeg.v4.observation.jingcai_sp import ensure_jingcai_sp_table, fetch_jingcai_sp

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_jingcai_sp_table(conn)
        # tolerate a fresh DB with no odds_snapshots yet — use the canonical DDL
        # so it never drifts from the real schema (it lacked kickoff_utc, which
        # the 体检 B2 pre-kickoff guard needs — a hand-copied DDL is exactly how
        # that drift happened).
        from nutmeg.v4.observation.odds_snapshots import ensure_odds_snapshots
        ensure_odds_snapshots(conn)
        rows = fetch_jingcai_sp(db_path, settled=True)
        candidates: list[dict] = []
        no_close = 0
        for r in rows:
            jc = (r["jc_home"], r["jc_draw"], r["jc_away"])
            close = _pinn_close(conn, r)
            if close is None:
                no_close += 1
                continue
            pinn_1x2 = _devig3(close[0], close[1], close[2])   # close 1X2 (for drift + had EV)
            if pinn_1x2 is None:
                no_close += 1
                continue
            pinn_cap = _devig3(r["psc_home"], r["psc_draw"], r["psc_away"])
            drift = (max(abs(pinn_1x2[i] - pinn_cap[i]) for i in range(3))
                     if pinn_cap else 0.0)
            market = r["market"] or "had"
            if market == "hhad":          # 让球: reverse-fit Pinnacle's cover P at the line
                truth = _hhad_pinn_and_outcome(close, r)
                if truth is None:
                    no_close += 1
                    continue
                p_close, covered = truth
                labels = _HC_LABELS
            else:                         # 1X2: de-vig Pinnacle close, W/D/L outcome
                p_close, covered, labels = pinn_1x2, r["ft_outcome"], _LABELS
            for i in range(3):
                sp = jc[i]
                if not sp or sp <= 1:
                    continue
                ev = p_close[i] * float(sp) - 1.0
                if ev < min_ev:
                    continue
                candidates.append({
                    "match": f'{r["home_team"]} vs {r["away_team"]}',
                    "league": r["league"] or "?", "market": market, "pick": labels[i],
                    "jc_sp": float(sp), "ev": ev, "drift": drift,
                    "won": (covered == i),
                    "profit": (float(sp) - 1.0) if covered == i else -1.0,
                })
        return {"n_settled": len(rows), "no_close": no_close, "candidates": candidates}


def _roi(cands: list[dict]) -> tuple[int, float, float]:
    """(#bets, win_rate, ROI per 1-unit stake)."""
    n = len(cands)
    if not n:
        return 0, 0.0, 0.0
    wins = sum(1 for c in cands if c["won"])
    return n, wins / n, sum(c["profit"] for c in cands) / n


def _print(report: dict, min_ev: float) -> None:
    cands = report["candidates"]
    print("=" * 64)
    print("竞彩「陈旧度」地图 — 软盘 vs Pinnacle 收盘,实战 ROI")
    print("=" * 64)
    print(f"已结算观测: {report['n_settled']}  ·  无 Pinnacle 收盘线(跳过): {report['no_close']}")
    print(f"+EV 候选(EV≥{min_ev:+.0%}): {len(cands)}\n")
    if not cands:
        print("  还没有可评估的候选 —— 在市场模式里正常定价,数据会自己累积。")
        print("  (诚实提醒:缝≠edge,要等足够样本的实战 ROI 才能下结论。)")
        return
    n, wr, roi = _roi(cands)
    print(f"全部候选:  {n} 注 · 命中率 {wr:.0%} · 实战 ROI {roi:+.1%}")
    print(f"{'  (ROI>0 才说明这条轴有东西;样本小先别当真)':}\n")

    def _bucket(key_fn, title):
        groups: dict[str, list] = defaultdict(list)
        for c in cands:
            groups[key_fn(c)].append(c)
        print(f"按{title}:")
        for k in sorted(groups):
            n, wr, roi = _roi(groups[k])
            print(f"  {k:28} {n:3} 注 · 命中 {wr:4.0%} · ROI {roi:+6.1%}")
        print()

    _bucket(lambda c: {"had": "1X2 胜平负", "hhad": "让球胜平负"}.get(
        c.get("market", "had"), c.get("market")), "玩法")
    _bucket(lambda c: c["league"], "联赛")
    _bucket(lambda c: _ev_band(c["ev"]), "EV 档")
    _bucket(lambda c: _drift_band(c["drift"]), "Pinnacle 冻结后漂移")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="竞彩 SP 陈旧度地图 (软盘 vs Pinnacle 收盘)")
    ap.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    ap.add_argument("--min-ev", type=float, default=_MIN_EV, help="+EV 候选阈值")
    ap.add_argument("--settle", action="store_true", help="先结算未结算观测再分析")
    args = ap.parse_args(argv)

    if args.settle:
        from nutmeg.v4.observation.jingcai_sp import settle_jingcai_sp
        n = settle_jingcai_sp(args.db)
        print(f"结算: 新填 {n} 场结果")
        # also settle 比分/总进球 (jingcai_exotic_sp) — best-effort, the staleness
        # map must not break if the (newer) exotic table hiccups.
        try:
            from nutmeg.v4.observation.jingcai_exotic import settle_exotic_sp
            ne = settle_exotic_sp(args.db)
            print(f"冷门玩法结算: 新填 {ne} 行(比分/总进球)")
        except Exception as e:  # noqa: BLE001 — secondary feed, never block the map
            print(f"冷门玩法结算跳过: {e}")
        # settle 散户投票表 (§1② retail-bias / autumn S2 feed) — best-effort,
        # rides the same daily settle pass so 支持率×结果 accumulates forward.
        try:
            from nutmeg.v4.observation.jingcai_vote import settle_jingcai_vote
            nv = settle_jingcai_vote(args.db)
            print(f"散户投票结算: 新填 {nv} 行(支持率×结果)")
        except Exception as e:  # noqa: BLE001 — secondary feed, never block the map
            print(f"散户投票结算跳过: {e}")
        print()

    _print(analyze(args.db, min_ev=args.min_ev), args.min_ev)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
