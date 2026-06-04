"""nutmeg-score-ev — correct-score (比分) EV from API-Football odds + model grid.

Pulls every bookmaker's correct-score market for a fixture (line-shops the best
price per scoreline), builds the model score distribution from a SHARP 1X2 + O/U
prior (de-vig → Dixon-Coles), and prints ``EV = model_P × best_odds − 1`` per
scoreline.

HONEST BY DESIGN. Correct-score is a brutal market and this tool says so:
  * margins are huge — ~30% at a single sharp book, ~60% even after line-shopping
    11 books (the composite implied probs sum to ~1.6, not 1.0);
  * the model's split into EXACT scores is an UNVALIDATED Poisson/DC assumption.
    The model has no proven edge over the sharp even on 1X2 (eval/independent_
    signal: β≤0), so on exact scores its deviations from the book are noise.
So almost every "+EV" it surfaces is model-split noise, not real edge — typically
on the very scorelines where model ≠ market, while the scorelines model AND
market agree are most likely (1-0, 2-0) come out −EV. The tool computes and
flags; it does NOT tell you to bet. The verdict block makes that unmissable.

Usage (env must be sourced for the API key):
    set -a && source .env && set +a
    nutmeg-score-ev --home Slovenia --away Cyprus --date 2026-06-04 \\
        --pin 1.386,4.7,8.12 --ou 2.5,2.0,1.84
    # skip the fixture search if you already have the id:
    nutmeg-score-ev --fixture-id 1540352 --pin 1.386,4.7,8.12 --ou 2.5,2.0,1.84
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date as _date
from typing import Any

_SCORE_RE = re.compile(r"^\s*(\d+)\s*[:\-]\s*(\d+)\s*$")


# ---------- pure core (no network — unit-tested) ------------------------

def parse_scoreline(value: Any) -> tuple[int, int] | None:
    """'2:1' / '2-1' → (2, 1) (home, away). None for 'Other' / junk."""
    m = _SCORE_RE.match(str(value))
    return (int(m.group(1)), int(m.group(2))) if m else None


def correct_score_books(
    odds_response: list[dict[str, Any]],
) -> dict[str, dict[tuple[int, int], float]]:
    """API-Football /odds response → {book: {(home, away): decimal_odds}} for the
    correct-score market only."""
    out: dict[str, dict[tuple[int, int], float]] = {}
    for item in odds_response or []:
        for bk in item.get("bookmakers", []) or []:
            name = bk.get("name") or "?"
            for bet in bk.get("bets", []) or []:
                bn = (bet.get("name") or "").lower()
                if "correct score" not in bn and "exact score" not in bn:
                    continue
                d = out.setdefault(name, {})
                for v in bet.get("values", []) or []:
                    ij = parse_scoreline(v.get("value"))
                    if ij is None:
                        continue
                    try:
                        o = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    if o > 1.0:
                        d[ij] = o  # last write wins; dupes are identical
    return out


def best_odds(
    books: dict[str, dict[tuple[int, int], float]], max_goals: int | None = None
) -> dict[tuple[int, int], tuple[float, str]]:
    """Line-shop: best (highest) decimal odds per scoreline across all books.
    ``max_goals`` (when set) restricts to scorelines the model grid can score
    (≤ max_goals each side); None keeps every quoted scoreline."""
    best: dict[tuple[int, int], tuple[float, str]] = {}
    for name, d in books.items():
        for (i, j), o in d.items():
            if max_goals is not None and (i > max_goals or j > max_goals):
                continue
            if (i, j) not in best or o > best[(i, j)][0]:
                best[(i, j)] = (o, name)
    return best


@dataclass
class ScoreEV:
    home: int
    away: int
    model_p: float
    odds: float
    book: str
    ev: float


def score_ev_rows(grid, books, *, max_goals: int) -> list[ScoreEV]:
    """Per priced scoreline: model P (from grid) × best book odds − 1, sorted by
    EV desc."""
    rows = [
        ScoreEV(i, j, float(grid[i][j]), o, bk, float(grid[i][j]) * o - 1.0)
        for (i, j), (o, bk) in best_odds(books, max_goals).items()
    ]
    rows.sort(key=lambda r: r.ev, reverse=True)
    return rows


def composite_overround(books) -> float:
    """Sum of implied probs from the line-shopped best price across EVERY quoted
    scoreline (not just grid-covered ones) — the TRUE market margin. A fair book
    would be 1.0; correct-score runs ~1.3 single-book, ~1.6 line-shopped. NOTE: do
    NOT restrict to the grid here — dropping the high-score lines (where 1xBet /
    Betano pile on) would understate the margin, which is the whole honest point."""
    return sum(1.0 / o for (o, _) in best_odds(books).values())


def consensus_1x2_devig(odds_response) -> tuple[float, float, float] | None:
    """Per-book de-vig of the Match Winner (1X2) market, averaged across books →
    consensus (P_home, P_draw, P_away). None if no book quotes a full 1X2. This is
    the automated stand-in for a hand-entered Pinnacle line (Pinnacle isn't carried
    by API-Football); a consensus is more robust than any single book."""
    accs = []
    for item in odds_response or []:
        for bk in item.get("bookmakers", []) or []:
            for bet in bk.get("bets", []) or []:
                if "match winner" not in (bet.get("name") or "").lower():
                    continue
                d = {}
                for v in bet.get("values", []) or []:
                    s = (v.get("value") or "").lower()
                    try:
                        o = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    if s == "home":
                        d["H"] = o
                    elif s == "draw":
                        d["D"] = o
                    elif s == "away":
                        d["A"] = o
                if {"H", "D", "A"} <= set(d) and all(d[k] > 1.0 for k in "HDA"):
                    inv = [1.0 / d["H"], 1.0 / d["D"], 1.0 / d["A"]]
                    tot = sum(inv)
                    accs.append([x / tot for x in inv])
    if not accs:
        return None
    m = len(accs)
    return tuple(sum(a[k] for a in accs) / m for k in range(3))


def consensus_over_devig(odds_response, line: float = 2.5) -> float | None:
    """Per-book 2-way de-vig of Goals Over/Under at ``line``, averaged → consensus
    P(over). None if no book quotes that line."""
    ovs = []
    for item in odds_response or []:
        for bk in item.get("bookmakers", []) or []:
            for bet in bk.get("bets", []) or []:
                if "over/under" not in (bet.get("name") or "").lower():
                    continue
                oo = uu = None
                for v in bet.get("values", []) or []:
                    s = str(v.get("value") or "")
                    try:
                        o = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    if s == f"Over {line:g}":
                        oo = o
                    elif s == f"Under {line:g}":
                        uu = o
                if oo and uu and oo > 1.0 and uu > 1.0:
                    ovs.append((1.0 / oo) / ((1.0 / oo) + (1.0 / uu)))
    return sum(ovs) / len(ovs) if ovs else None


# ---------- model + I/O -------------------------------------------------

def model_grid(pin: tuple[float, float, float],
               ou: tuple[float, float, float] | None, *, rho: float):
    """Sharp de-vig 1X2 (+ O/U) → Dixon-Coles score grid. Returns (grid, (λh, λa),
    devig_1x2, p_over)."""
    import numpy as np

    from nutmeg.v4.model.dixon_coles import score_grid
    from nutmeg.v4.model.market_handicap import devig_over, fit_lambdas

    oh, od, oa = pin
    inv = np.array([1.0 / oh, 1.0 / od, 1.0 / oa])
    p = inv / inv.sum()
    pov = None
    line = None
    if ou is not None:
        line, o_over, o_under = ou
        pov = devig_over(o_over, o_under)
    lh, la = (fit_lambdas(p[0], p[1], p[2], pov, ou_line=line) if line is not None
              else fit_lambdas(p[0], p[1], p[2]))
    return score_grid(lh, la, rho=rho), (lh, la), p, pov


def grid_from_devig(p1x2, p_over, *, line: float = 2.5, rho: float):
    """Dixon-Coles grid from de-vig probabilities (vs model_grid which takes odds).
    Used by the automated backtest / forward recorder where the prior comes from a
    consensus de-vig rather than a hand-entered Pinnacle line."""
    from nutmeg.v4.model.dixon_coles import score_grid
    from nutmeg.v4.model.market_handicap import fit_lambdas
    lh, la = (fit_lambdas(p1x2[0], p1x2[1], p1x2[2], p_over, ou_line=line)
              if p_over is not None else fit_lambdas(p1x2[0], p1x2[1], p1x2[2]))
    return score_grid(lh, la, rho=rho), (lh, la)


def ev_flags(odds_response, *, min_ev: float = 0.05, max_odds: float = 80.0,
             rho: float, line: float = 2.5, exclude_books=("1xBet",)):
    """The shared analysis core: correct-score market → line-shop best price (excl.
    junk books, cap odds) → model grid from consensus de-vig 1X2+O/U → list of +EV
    flags ``[{home, away, model_p, odds, book, ev}]`` sorted by EV desc. Returns
    None when the fixture lacks a correct-score market or a 1X2 to build the prior.
    Backs both the forward recorder and (validated against) the offline backtest."""
    excl = set(exclude_books)
    cs = {bk: v for bk, v in correct_score_books(odds_response).items() if bk not in excl}
    if not cs:
        return None
    p1x2 = consensus_1x2_devig(odds_response)
    if p1x2 is None:
        return None
    pov = consensus_over_devig(odds_response, line)
    grid, _ = grid_from_devig(p1x2, pov, line=line, rho=rho)
    mg = grid.shape[0] - 1
    flags = []
    for (i, j), (o, bk) in best_odds(cs, mg).items():
        if o > max_odds:
            continue
        p = float(grid[i][j])
        ev = p * o - 1.0
        if ev >= min_ev:
            flags.append({"home": i, "away": j, "model_p": p,
                          "odds": o, "book": bk, "ev": ev})
    flags.sort(key=lambda f: f["ev"], reverse=True)
    return flags


def fetch_correct_score(fixture_id: int, *, refresh: bool = False):
    """API-Football → {book: {(h,a): odds}} for the correct-score market."""
    from nutmeg.v4.data.sources import api_football as af
    return correct_score_books(af.fetch_odds(int(fixture_id), refresh=refresh))


def find_fixture(home: str, away: str, on_date: _date):
    """Search API-Football fixtures on a date for a (home, away) substring match."""
    from nutmeg.v4.data.sources import api_football as af
    for f in af.fetch_fixtures_for_date(on_date):
        h = ((f.get("teams") or {}).get("home") or {}).get("name", "")
        a = ((f.get("teams") or {}).get("away") or {}).get("name", "")
        if home.lower() in h.lower() and away.lower() in a.lower():
            return (f.get("fixture") or {}).get("id"), h, a
    return None, None, None


# ---------- CLI ---------------------------------------------------------

def _triple(s: str) -> tuple[float, ...]:
    parts = [float(x) for x in s.replace(" ", "").split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("expected 3 comma-separated numbers")
    return tuple(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Correct-score (比分) EV via API-Football odds + DC model grid"
    )
    ap.add_argument("--fixture-id", type=int, default=None,
                    help="API-Football fixture id (skips the team/date search)")
    ap.add_argument("--home", default=None, help="Home team (for fixture search)")
    ap.add_argument("--away", default=None, help="Away team (for fixture search)")
    ap.add_argument("--date", default=None, help="Match date YYYY-MM-DD (search)")
    ap.add_argument("--pin", type=_triple, required=True,
                    help="SHARP 1X2 decimal odds 'H,D,A' (e.g. Pinnacle 1.386,4.7,8.12)")
    ap.add_argument("--ou", type=_triple, default=None,
                    help="O/U 'line,over,under' (anchors λ_total; omit for 1X2-only)")
    ap.add_argument("--rho", type=float, default=None,
                    help="Dixon-Coles ρ (default: serving DEFAULT_RHO)")
    ap.add_argument("--min-ev", type=float, default=0.05, help="Flag threshold")
    ap.add_argument("--top", type=int, default=14, help="Rows to show")
    ap.add_argument("--refresh", action="store_true", help="Bypass odds cache")
    args = ap.parse_args(argv)

    from nutmeg.v4.model.market_handicap import DEFAULT_RHO
    rho = DEFAULT_RHO if args.rho is None else args.rho

    # Resolve fixture
    fid, hname, aname = args.fixture_id, args.home, args.away
    if fid is None:
        if not (args.home and args.away and args.date):
            print("ERROR: pass --fixture-id, or --home/--away/--date to search.",
                  file=sys.stderr)
            return 2
        fid, hname, aname = find_fixture(
            args.home, args.away, _date.fromisoformat(args.date))
        if fid is None:
            print(f"ERROR: no fixture found for {args.home} vs {args.away} on "
                  f"{args.date}. Pass --fixture-id directly.", file=sys.stderr)
            return 2

    books = fetch_correct_score(fid, refresh=args.refresh)
    if not books:
        print(f"No correct-score market available for fixture {fid}.",
              file=sys.stderr)
        return 1

    grid, (lh, la), p, pov = model_grid(tuple(args.pin),
                                        tuple(args.ou) if args.ou else None, rho=rho)
    mg = grid.shape[0] - 1
    rows = score_ev_rows(grid, books, max_goals=mg)
    overround = composite_overround(books)  # all scorelines = true market margin
    n_plus = sum(1 for r in rows if r.ev >= args.min_ev)

    title = f"{hname} vs {aname}" if hname else f"fixture {fid}"
    print(f"\n=== {title}  (fixture {fid}) ===")
    pov_s = f" · P(over {args.ou[0]:g})={pov * 100:.0f}%" if pov is not None else ""
    print(f"先验(sharp 去vig): 1X2 {p[0] * 100:.0f}/{p[1] * 100:.0f}/{p[2] * 100:.0f}"
          f"{pov_s} · λ 主{lh:.2f}/客{la:.2f}(总{lh + la:.2f})")
    print(f"比分盘: {len(books)} 家书 · 比价后合成抽水 "
          f"{(overround - 1) * 100:.0f}% (隐含合计 {overround:.2f}, 真实=1.00)")
    print(f"\n  {'比分':>5} {'模型P':>6} {'公平赔':>6} {'最高赔(book)':>17} {'EV':>8}")
    for r in rows[:args.top]:
        flag = " ✅" if r.ev >= args.min_ev else ("" if r.ev >= 0 else "")
        fair = (1.0 / r.model_p) if r.model_p > 0 else float("inf")
        print(f"  {r.home}-{r.away:<2} {r.model_p * 100:5.1f}% {fair:6.2f} "
              f"{r.odds:7.2f} {r.book:<10} {r.ev * 100:+7.1f}%{flag}")

    print("\n⚠️ 诚实提醒(必读):")
    print(f"   · 比分盘合成抽水 ~{(overround - 1) * 100:.0f}% → 整体是 −EV 屠宰场,"
          "数学上赢不了。")
    print(f"   · 上面 {n_plus} 条显示 +EV,但多为「模型比分拆分 ≠ 市场」的噪声:")
    print("     模型对 exact 比分无验证优势(连 1X2 都 β≤0);真favorites(1-0/2-0)"
          "通常 −EV。")
    print("   · 本工具只算+标记,不替你决定。+EV ≠ 该下。比分盘几乎永远空仓。")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
