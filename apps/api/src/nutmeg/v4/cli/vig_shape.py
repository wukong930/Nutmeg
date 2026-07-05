"""nutmeg-vig-shape — 竞彩 逐路 vig 分解(探索 #1,只读测量).

Reads captured rows that carry BOTH a 竞彩 SP and a Pinnacle line (jingcai_vote —
which also has retail support — plus jingcai_sp), de-vigs Pinnacle with WPO to a
fair P, and reports whether 竞彩 spreads its overround evenly or shades it. The
shading test joins the vote table's retail support: does per-leg vig RISE with
retail support (竞彩 loading margin onto the crowd)?

Pre-result (no settlement needed) → runs on everything captured so far and grows
daily. EXPLORATORY: describes the market; a shading pattern is an autumn-prereg
hypothesis, never a bet trigger. Zero API calls.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from nutmeg.v4.model.devig import devig_1x2
from nutmeg.v4.model.vig_shape import VigSample, analyze, per_leg_vig


def _rows(conn: sqlite3.Connection, since: str) -> list[VigSample]:
    conn.row_factory = sqlite3.Row
    out: list[VigSample] = []
    seen: set[tuple] = set()
    # vote table first (carries retail support), then SP table (no support).
    q_vote = (
        "SELECT match_date, home_zh AS h, away_zh AS a, jc_home, jc_draw, jc_away, "
        "psc_home, psc_draw, psc_away, h_support, d_support, a_support "
        "FROM jingcai_vote WHERE pool_code='HAD' AND jc_home>1 AND jc_draw>1 "
        "AND jc_away>1 AND psc_home>1 AND psc_draw>1 AND psc_away>1 "
        "AND match_date >= ?")
    q_sp = (
        "SELECT match_date, home_team AS h, away_team AS a, jc_home, jc_draw, jc_away, "
        "psc_home, psc_draw, psc_away, NULL AS h_support, NULL AS d_support, "
        "NULL AS a_support FROM jingcai_sp WHERE market='had' AND jc_home>1 "
        "AND jc_draw>1 AND jc_away>1 AND psc_home>1 AND psc_draw>1 AND psc_away>1 "
        "AND match_date >= ?")
    for q in (q_vote, q_sp):
        for r in conn.execute(q, (since,)):
            key = (r["match_date"], r["h"], r["a"])
            if key in seen:
                continue
            fair = devig_1x2(r["psc_home"], r["psc_draw"], r["psc_away"])
            if not fair:
                continue
            sp = (r["jc_home"], r["jc_draw"], r["jc_away"])
            support = None
            if r["h_support"] is not None:
                support = (r["h_support"], r["d_support"], r["a_support"])
            seen.add(key)
            out.append(VigSample(r["match_date"], r["h"] or "?", r["a"] or "?",
                                 per_leg_vig(sp, fair), fair, sp, support))
    return out


def run(db: str | Path, since: str) -> int:
    with sqlite3.connect(str(db)) as conn:
        samples = _rows(conn, since)
    res = analyze(samples)
    print(f"竞彩 逐路 vig 分解 · 窗口 ≥{since} · N={res.n} 场(探索,只读,赛前可测)")
    if res.n == 0:
        print("N=0 — 暂无同时带 竞彩SP + Pinnacle 的捕获行。")
        return 0
    print(f"平均总 overround: {res.mean_overround*100:.1f}%\n")
    print("① 逐路平均 vig(= 逐腿 −EV = 1 − P·SP;比例定价下三路应相等):")
    for pos, v in res.by_position.items():
        print(f"   {pos}  {v*100:+.1f}%")
    print("\n② 热门腿 vs 非热门腿(sharp favourite 那路 vs 另两路):")
    print(f"   热门 {res.fav_vig*100:+.1f}% · 非热门 {res.dog_vig*100:+.1f}% "
          f"· 差 {(res.fav_vig-res.dog_vig)*100:+.1f}pp")
    print(f"\n③ 「不均度」= 场内 vig 极差(max−min)均值: {res.mean_spread*100:.1f}pp "
          f"(比例定价=0;越大越说明竞彩在偏袒某路)")
    if res.support_terciles:
        print("\n④ 剃刀 · 逐腿按散户票分三档看 vig(vig 随票升 = 竞彩把水压向人群):")
        for label, nlegs, msup, mvig in res.support_terciles:
            print(f"   {label}({nlegs}腿) 均票 {msup:.0f}% → 均 vig {mvig*100:+.1f}%")
        print("\n⑤ 控制热门度 · 只看非热门腿(剥离「热门本就贵」混淆,支持才算真剃刀):")
        if res.dog_support_terciles:
            for label, nlegs, msup, mvig in res.dog_support_terciles:
                print(f"   {label}({nlegs}腿) 均票 {msup:.0f}% → 均 vig {mvig*100:+.1f}%")
        else:
            print("   非热门腿样本不足(<6)——攒够再看")
    else:
        print("\n④ 散户票剃刀: 样本不足(需 ≥6 条带票的腿)——vote 攒够再看")
    print("\n注:P=Pinnacle WPO 去vig(捕获时,非保证收盘);正 vig=该腿对下注者不利。"
          "\n探索性——④单调升 = 「软腿在低票侧」;但须⑤(控制热门度后仍升)才排除混淆。"
          "\n即便最软腿也仍是正 vig=只定位软腿位置,不凭空造 +EV。秋季进预注册验。")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="竞彩 逐路 vig 分解(探索 #1)")
    ap.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    ap.add_argument("--since", default="2000-01-01", help="起始 match_date(默认全量)")
    args = ap.parse_args(argv)
    return run(args.db, args.since)


if __name__ == "__main__":
    raise SystemExit(main())
