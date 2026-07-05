"""nutmeg-sentiment-triangle — 竞彩 情绪三角(探索 #4,只读测量).

Joins the three vertices per match — model P (league_predictions), sharp P
(Pinnacle WPO de-vig, from the co-captured vote row), retail sentiment (竞彩
支持比例) — plus the settled outcome, and asks whether the MODEL confirms or
contradicts the crowd-avoided (= 竞彩-soft, #2) leg.

Cross-source join goes by name+date through ``national_match_key`` with a
poison-on-collision guard (no shared fixture_id). EXPLORATORY, zero API, no bets.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from nutmeg.v4.data.national_alias import national_match_key
from nutmeg.v4.model.devig import devig_1x2
from nutmeg.v4.model.sentiment_triangle import TriangleSample, analyze

_POISON = object()


def _key(date: str, home: str, away: str) -> tuple[str, str, str]:
    return (date, national_match_key(home), national_match_key(away))


def _norm(t: tuple[float, float, float]) -> tuple[float, float, float] | None:
    s = sum(t)
    if s <= 0:
        return None
    return (t[0] / s, t[1] / s, t[2] / s)


def _model_p(conn: sqlite3.Connection, since: str) -> dict[tuple, tuple]:
    """key → model P (主,平,客), poison on collision."""
    out: dict[tuple, tuple] = {}
    seen: dict[tuple, tuple] = {}
    rows = conn.execute(
        "SELECT match_date, home_team, away_team, p_home, p_draw, p_away "
        "FROM league_predictions WHERE p_home>0 AND match_date >= ?", (since,))
    for md, h, a, ph, pd, pa in rows:
        if not h or not a:
            continue
        k = _key(md, h, a)
        if out.get(k) is _POISON:
            continue
        if k in out and seen.get(k) != (h, a):
            out[k] = _POISON
            continue
        mp = _norm((ph, pd, pa))
        if mp:
            out[k] = mp
            seen[k] = (h, a)
    return {k: v for k, v in out.items() if v is not _POISON}


def _samples(conn: sqlite3.Connection, since: str) -> list[TriangleSample]:
    models = _model_p(conn, since)
    out: list[TriangleSample] = []
    seen: set[tuple] = set()
    rows = conn.execute(
        "SELECT match_date, home_team, away_team, h_support, d_support, a_support, "
        "psc_home, psc_draw, psc_away, ft_outcome FROM jingcai_vote "
        "WHERE pool_code='HAD' AND h_support IS NOT NULL AND psc_home>1 "
        "AND psc_draw>1 AND psc_away>1 AND match_date >= ?", (since,))
    for md, h, a, hs, ds, as_, ph, pd, pa, out_ in rows:
        if not h or not a:
            continue
        k = _key(md, h, a)
        if k in seen:
            continue
        model_p = models.get(k)
        if model_p is None or model_p is _POISON:
            continue
        sharp_p = devig_1x2(ph, pd, pa)
        retail_p = _norm((hs or 0.0, ds or 0.0, as_ or 0.0))
        if not sharp_p or not retail_p:
            continue
        seen.add(k)
        outcome = int(out_) if out_ is not None else None
        out.append(TriangleSample(md, h or "?", a or "?", model_p, sharp_p, retail_p, outcome))
    return out


def run(db: str | Path, since: str) -> int:
    with sqlite3.connect(str(db)) as conn:
        samples = _samples(conn, since)
    res = analyze(samples)
    print(f"竞彩 情绪三角(model/sharp/retail)· 窗口 ≥{since} · N={res.n} 场"
          f"(已结算 {res.n_settled};探索,只读)")
    if res.n == 0:
        print("N=0 — 暂无同时有 模型P + Pinnacle + 散户票 的比赛。")
        return 0
    print("\n① 三顶点两两背离(TV,0=重合 1=完全不同;看模型更靠 sharp 还是靠人群):")
    print(f"   模型↔sharp   {res.mean_d_model_sharp:.3f}")
    print(f"   sharp↔散户   {res.mean_d_sharp_retail:.3f}")
    print(f"   模型↔散户   {res.mean_d_model_retail:.3f}")
    closer = ("模型更靠 sharp(与人群更远)—— 好:模型是独立于人群的第三票"
              if res.mean_d_model_sharp < res.mean_d_model_retail else
              "模型更靠人群(与 sharp 更远)—— 警:模型可能带了人群偏差")
    print(f"   → {closer}")
    print(f"\n② 人群是离群点(模型&sharp 一致、人群偏离)的场占比: "
          f"{res.crowd_outlier_frac*100:.0f}%")
    print("\n③ 人群回避腿(= 竞彩软腿)的命中,按模型是否背书拆分(已结算):")
    print("   —— 模型背书组(模型 P ≥ sharp,认同软腿被低估):")
    _leg_line(res.confirm_n, res.confirm_wins, res.confirm_sharp_base)
    print("   —— 模型反对组(模型 P < sharp,与人群同侧压低软腿):")
    _leg_line(res.contra_n, res.contra_wins, res.contra_sharp_base)
    print("\n注:sharp=WPO 去vig=真值;retail=支持比例(票额情绪,非校准 P,仅比方向)。"
          "EV 永远是 sharp × 竞彩SP,模型只作第三票给软腿信号定级,不入 EV。"
          f"\n★ N={res.n_settled} 太小,只描述方向、锁工具;秋季样本到再复读判显著。探索性,不动钱。")
    return 0


def _leg_line(n: int, wins: int, sharp_base: float) -> None:
    if n == 0:
        print("      (本组 0 场)")
        return
    wr = wins / n
    surprise = wr - sharp_base
    tag = ("跑赢 sharp 基线" if surprise > 0.02
           else "跑输 sharp 基线" if surprise < -0.02 else "≈ sharp 基线")
    print(f"      {wins}/{n} 命中 = {wr*100:.0f}% · sharp 基线 {sharp_base*100:.0f}% "
          f"· 差 {surprise*100:+.0f}pp（{tag}）")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="竞彩 情绪三角(探索 #4)")
    ap.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    ap.add_argument("--since", default="2000-01-01", help="起始 match_date(默认全量)")
    args = ap.parse_args(argv)
    return run(args.db, args.since)


if __name__ == "__main__":
    raise SystemExit(main())
