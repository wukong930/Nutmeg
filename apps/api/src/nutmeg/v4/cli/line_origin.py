"""nutmeg-line-origin — 竞彩 线源残差分解(探索 #2,只读测量).

For every match where we have BOTH a Pinnacle line HISTORY (≥2 odds_snapshots, so
open→close movement is observable) AND a 竞彩 SP, split the 竞彩-vs-sharp gap into
its two orthogonal causes:

    total (竞彩 − Pinnacle_close) = staleness (open − close) + domestic (竞彩 − open)

Staleness = the freeze-gap (S1); domestic = the price-side retail/home bias (S2).
The question this answers, which no size-only vig number can: when 竞彩 sits off
the sharp truth, is it because it's STALE (fixable with a fresher line) or because
domestic money set it off-sharp from the START (a different, standing edge)?

Cross-source join (odds_snapshots × jingcai_*) has no shared fixture_id, so it
goes by name+date routed through ``national_match_key`` with a poison-on-collision
guard. Pre-result (no settlement) → grows daily. EXPLORATORY, zero API, no bets.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from nutmeg.v4.data.national_alias import national_match_key
from nutmeg.v4.model.devig import devig_1x2
from nutmeg.v4.model.line_origin import LineOriginSample, analyze

_POISON = object()  # sentinel: a key two different matches collided on → drop it


def _key(date: str, home: str, away: str) -> tuple[str, str, str]:
    return (date, national_match_key(home), national_match_key(away))


def _pinnacle_open_close(conn: sqlite3.Connection, since: str) -> dict[tuple, tuple]:
    """Per match key → (open_p, close_p, band_lo, band_hi, home, away).

    open/close/band are ALL computed over PRE-KICKOFF snapshots only (a row with
    kickoff_utc absent can't be judged → kept). open = earliest such snapshot;
    close = latest; band = per-leg (min, max) de-vigged fair P over them — the
    full range the sharp line traversed, which is what staleness gets credited
    with. An in-play snapshot must not widen that band any more than it may
    become the close: it would hand staleness credit for a range the pre-match
    market never offered, shrinking the irreducible-domestic residual toward a
    false zero. Each snapshot is WPO-de-vigged inside the loop; un-de-viggable
    snapshots are skipped. Needs ≥2 distinct valid **pre-kickoff** captures —
    counting in-play rows there would let a degenerate 1-pre-KO sample pass
    (open==close, band collapsed to a point). See tests/v4/test_reader_kickoff_guard.py.
    """
    rows = conn.execute(
        "SELECT match_date, home_team, away_team, captured_at, kickoff_utc, "
        "psc_home, psc_draw, psc_away FROM odds_snapshots "
        "WHERE psc_home>1 AND psc_draw>1 AND psc_away>1 AND match_date >= ? "
        "ORDER BY captured_at",
        (since,),
    ).fetchall()
    acc: dict[tuple, dict] = {}
    for md, h, a, cap, ko, ph, pd, pa in rows:
        k = _key(md, h, a)
        cur = acc.get(k)
        if cur is _POISON:
            continue
        if cur is not None and cur["raw"] != (h, a):
            acc[k] = _POISON  # two different matches share this key → unusable
            continue
        fair = devig_1x2(ph, pd, pa)
        if not fair:
            continue
        if cur is None:
            cur = acc[k] = {"raw": (h, a), "h": h, "a": a, "caps": set(),
                            "open": None, "close": None, "lo": None, "hi": None}
        # ONE pre-kickoff gate for BOTH the band and the close — they must never
        # drift apart. An in-play snapshot (a leading team's degenerate
        # 1.06/…/53.96 line) is not a price the sharp market ever offered on the
        # pre-match question, so it may neither become the close NOR widen the
        # band that staleness gets credited with.
        #
        # ⚠️ 2026-09-02 实测的**真实严重性**(原提交只有叙述、没有数字):
        #   2026-06 起 1,939 个合格样本里,带滚球快照的只有 **2 场**,
        #   band 真被撑宽的 **1 场(0.1%)** —— Augsburg vs FC Schalke 04,
        #   主胜 band 宽度 0.017 → 0.028(×1.6)。
        #   ⭐ 而那一场恰好就是 `closing_odds` 那个**写入侧竞态**造出来的行
        #   (captured_at 比 kickoff 晚 2s),该竞态已于同日根除。
        #   ⇒ 本闸今天的实际影响 ≈ 0;它的价值是**纵深防御**:回填、换源、
        #     或下一个写入侧 bug 都可能再把滚球行喂进来,而那时它已经在这儿了。
        #   ⛔ 别据此把它删掉 —— 0.1% 是「上游刚被修好」的结果,不是「不会发生」。
        before_ko = (ko is None) or (cap < ko)
        if not before_ko:
            continue
        # ⚠️ 2026-09-02 —— `caps` 也搬进闸内。原来它在闸**之前**加,于是
        #    「≥2 个不同快照」这条充足性判据会把**喂不进计算的行**算进分母:
        #    1 个赛前 + 3 个滚球 ⇒ caps=4 过关,而 band/open/close 全部来自那 1 个
        #    赛前快照 ⇒ open==close、band 退化成一个点,一个**退化样本冒充充足样本**。
        #    ⭐ 实测(2026-08 起 1,419 场):靠滚球行凑够 ≥2 的 **0 场** ⇒ 今天零代价;
        #    改的是**规则的自洽**(本函数 docstring 自己说「一道闸管全部」),
        #    以及那个将来会咬人的口子。同族:分母里混进了分子用不了的行。
        cur["caps"].add(cap)
        if cur["lo"] is None:
            cur["lo"], cur["hi"] = list(fair), list(fair)
        else:
            for i in range(3):
                cur["lo"][i] = min(cur["lo"][i], fair[i])
                cur["hi"][i] = max(cur["hi"][i], fair[i])
        if cur["open"] is None or cap < cur["open"][0]:
            cur["open"] = (cap, fair)
        if cur["close"] is None or cap > cur["close"][0]:
            cur["close"] = (cap, fair)

    out: dict[tuple, tuple] = {}
    for k, cur in acc.items():
        if cur is _POISON or len(cur["caps"]) < 2 or cur["close"] is None:
            continue
        out[k] = (cur["open"][1], cur["close"][1],
                  tuple(cur["lo"]), tuple(cur["hi"]), cur["h"], cur["a"])
    return out


def _jingcai(conn: sqlite3.Connection, since: str) -> dict[tuple, tuple]:
    """Per match key → (jc_fair_p, support|None). vote table first (has support)."""
    q_vote = (
        "SELECT match_date, home_team, away_team, jc_home, jc_draw, jc_away, "
        "h_support, d_support, a_support FROM jingcai_vote WHERE pool_code='HAD' "
        "AND jc_home>1 AND jc_draw>1 AND jc_away>1 AND match_date >= ?")
    q_sp = (
        "SELECT match_date, home_team, away_team, jc_home, jc_draw, jc_away, "
        "NULL, NULL, NULL FROM jingcai_sp WHERE market='had' AND jc_home>1 "
        "AND jc_draw>1 AND jc_away>1 AND match_date >= ?")
    out: dict[tuple, tuple] = {}
    seen_raw: dict[tuple, tuple] = {}
    for q in (q_vote, q_sp):
        for md, h, a, jh, jd, ja, hs, ds, as_ in conn.execute(q, (since,)):
            if not h or not a:
                continue
            k = _key(md, h, a)
            if out.get(k) is _POISON:
                continue
            if k in out and seen_raw.get(k) != (h, a):
                out[k] = _POISON  # collision across different matches
                continue
            if k in out:
                continue  # already have this exact match (vote wins over sp)
            fair = devig_1x2(jh, jd, ja)
            if not fair:
                continue
            support = (hs, ds, as_) if hs is not None else None
            out[k] = (fair, support)
            seen_raw[k] = (h, a)
    return {k: v for k, v in out.items() if v is not _POISON}


def run(db: str | Path, since: str) -> int:
    with sqlite3.connect(str(db)) as conn:
        pins = _pinnacle_open_close(conn, since)
        jcs = _jingcai(conn, since)
    samples: list[LineOriginSample] = []
    for k, (op, cl, lo, hi, h, a) in pins.items():
        jc = jcs.get(k)
        if jc is None or jc is _POISON:
            continue
        fair, support = jc
        samples.append(LineOriginSample(k[0], h, a, fair, op, cl, lo, hi, support))

    res = analyze(samples)
    print(f"竞彩 线源残差分解 · 窗口 ≥{since} · N={res.n} 场"
          f"(有 Pinnacle 线史 + 竞彩 SP;探索,只读,赛前可测)")
    if res.n == 0:
        print("N=0 — 暂无同时有 Pinnacle 多快照线史 + 竞彩 SP 的比赛。")
        return 0
    print("\n把 竞彩 与 sharp 的缺口拆成:陈旧(可用某个旧 Pinnacle 锚解释)vs 本土"
          "(竞彩落在 Pinnacle 整个已观测区间之外,任何陈旧锚都解释不了)。\n")
    print("① 平均量级(逐腿绝对值,pp):")
    print(f"   陈旧度 |开−收|(sharp 自身位移)       {res.mean_abs_staleness*100:.1f}pp")
    print(f"   总缺口 |竞−收|(竞彩距 sharp 真值)     {res.mean_abs_total*100:.1f}pp")
    print(f"   ★不可约本土 |竞在区间外|(诚实下限)   {res.mean_abs_irreducible*100:.1f}pp")
    print(f"\n② 有多少腿「陈旧解释不了」(竞彩落在 Pinnacle 整个区间之外): "
          f"{res.frac_legs_outside_band*100:.0f}%")
    print(f"   本土占比 = |不可约本土| / |总缺口| = {res.domestic_share*100:.0f}%")
    verdict = ("本土偏差为主 → 软水确是「国内钱把线推离 sharp」,非陈旧可解释"
               if res.domestic_share > 0.55 else
               "陈旧为主 → 竞彩多落在 sharp 已走过的区间内,软水主要是冻结缺口"
               if res.domestic_share < 0.35 else "两者相当,难一言以蔽之")
    print(f"   → {verdict}")
    print("\n③ 逐路不可约本土残差(带符号;正=竞彩隐含概率在 sharp 整个区间之上):")
    for pos, v in res.by_position_irreducible.items():
        print(f"   {pos}  {v*100:+.1f}pp")
    if res.support_terciles:
        print("\n④ 诚实剃刀 · 不可约本土残差按散户票分档(排除陈旧后仍存在的偏袒):")
        for label, nlegs, msup, mdom in res.support_terciles:
            print(f"   {label}({nlegs}腿) 均票 {msup:.0f}% → 不可约本土 {mdom*100:+.1f}pp")
        print("   (高票腿更正 = 竞彩把隐含概率推到 sharp 区间之上,往人群那边,陈旧解释不了)")
    else:
        print("\n④ 散户票分档: 样本不足(需 ≥6 条带票的腿)——vote 攒够再看")
    print("\n注:band=每腿全「赛前」快照 WPO 去vig 公允 P 的 min/max(滚球快照不计入);"
          "竞彩落区间内=让陈旧全占,"
          "只算落在区间外的部分为本土(最保守)。P=WPO,非保证收盘绝对水平。"
          "\n探索性——分解软水成因,不造 +EV;秋季线史攒厚再复读。")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="竞彩 线源残差分解(探索 #2)")
    ap.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    ap.add_argument("--since", default="2000-01-01", help="起始 match_date(默认全量)")
    args = ap.parse_args(argv)
    return run(args.db, args.since)


if __name__ == "__main__":
    raise SystemExit(main())
