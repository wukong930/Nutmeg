#!/usr/bin/env python3
"""审计 jingcai_sp 存的竞彩终价 vs getFixedBonusV1 官方走势档案(逐场逐腿)。

诞生于 2026-07-19 RCA(SJK vs KuPS hhad a 腿 5.25 被手滑成 7.25 并永生化,
docs/jingcai_sp_capture_integrity_2026-07-19.md)。对窗口内**已结算**的 had+hhad
行(6 腿/场)逐腿比对官方档案,分类:

  OK_FINAL       — 我们存的 = 官方终盘(逐腿 ±0.001)
  OK_AT_CAPTURE  — ≠终盘,但 = captured_at 时刻官方在售值(之后官方又变盘)
                   → 采集时点缺口,非损坏
  FABRICATED     — ≥1 腿的值从未在该场官方走势任何一次变盘出现 → 真损坏
  MIXED_PHASE    — 各腿值都出现过,但拼不成官方任何一行(跨变盘混拼)
  LINE_MISMATCH  — hhad 让球线 ≠ 官方终盘线
  NO_OFFICIAL[_MARKET] — 官方侧枚举/队名映射缺口,无法比对

用法(中国站点限速:逐场 sleep 1s;结果缓存在 --cache-dir,重跑免网络):
  python scripts/audit_jingcai_sp_vs_fixedbonus.py --since 2026-07-01
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import time
from collections import Counter
from pathlib import Path

# 直连中国站点:清六个代理变量(httpx trust_env 会吃这些)
for _k in ("http_proxy", "https_proxy", "all_proxy",
           "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
    os.environ.pop(_k, None)

from nutmeg.v4.data.sources.sporttery_history import (  # noqa: E402
    fetch_and_parse,
    iter_match_ids,
)

BJ = dt.timedelta(hours=8)
EPS = 0.001


def load_our_rows(db: str, since: str) -> list[dict]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM jingcai_sp WHERE match_date>=? AND settled_at IS NOT NULL "
        "ORDER BY match_date, home_team, market", (since,))]
    conn.close()
    return rows


def enum_match_ids(cache: Path, begin: str, end: str) -> list[dict]:
    f = cache / f"matchlist_{begin}_{end}.json"
    if f.exists():
        return json.loads(f.read_text())
    out = list(iter_match_ids(begin, end))
    f.write_text(json.dumps(out, ensure_ascii=False))
    return out


def get_official(cache: Path, mid: int, sleep: float) -> dict | None:
    f = cache / f"{mid}.json"
    if f.exists():
        d = json.loads(f.read_text())
        return d or None
    parsed = fetch_and_parse(mid)
    f.write_text(json.dumps(parsed or {}, ensure_ascii=False))
    time.sleep(sleep)
    return parsed


def bj_str(utc_iso: str) -> str:
    """UTC ISO → 'YYYY-MM-DD HH:MM:SS' Beijing(与官方 update_dt 同格式)。"""
    t = dt.datetime.fromisoformat(utc_iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.UTC)
    return (t.astimezone(dt.UTC) + BJ).strftime("%Y-%m-%d %H:%M:%S")


def classify(ours: dict, series: list[dict], market: str) -> dict:
    jc = (ours["jc_home"], ours["jc_draw"], ours["jc_away"])
    final = series[-1]
    res: dict = {"official_final": (final["h"], final["d"], final["a"]),
                 "official_n_moves": len(series),
                 "official_final_dt": final["update_dt"]}
    if market == "hhad":
        res["official_line"] = final.get("goal_line")
        if (ours.get("handicap_home") is not None
                and final.get("goal_line") is not None
                and int(ours["handicap_home"]) != int(final["goal_line"])):
            res["class"] = "LINE_MISMATCH"
            return res
    if all(abs(a - b) < EPS for a, b in zip(jc, res["official_final"], strict=True)):
        res["class"] = "OK_FINAL"
        return res
    cap_bj = bj_str(ours["captured_at"])
    in_force = None
    for row in series:
        if row["update_dt"] and row["update_dt"] <= cap_bj:
            in_force = row
    if in_force is not None and all(
            abs(a - b) < EPS for a, b in
            zip(jc, (in_force["h"], in_force["d"], in_force["a"]), strict=True)):
        res["class"] = "OK_AT_CAPTURE"
        res["in_force"] = (in_force["h"], in_force["d"], in_force["a"])
        return res
    fabricated = [
        {"leg": leg, "ours": v, "official_final": final[leg]}
        for leg, v in zip(("h", "d", "a"), jc, strict=True)
        if not any(abs(v - row[leg]) < EPS for row in series)
    ]
    if fabricated:
        res["class"] = "FABRICATED"
        res["fabricated_legs"] = fabricated
    else:
        res["class"] = "MIXED_PHASE"
    res["in_force"] = ((in_force["h"], in_force["d"], in_force["a"])
                       if in_force else None)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--since", default="2026-07-01", help="jingcai_sp match_date 下限 (UTC)")
    ap.add_argument("--enum-begin", default=None,
                    help="官方枚举起始 Beijing 日(默认 since−1 天)")
    ap.add_argument("--enum-end", default=None, help="官方枚举结束 Beijing 日(默认今天)")
    ap.add_argument("--cache-dir", default="data/external/sporttery/fixedbonus_audit")
    ap.add_argument("--sleep", type=float, default=1.0, help="逐场限速(秒)")
    ap.add_argument("--out", default=None, help="结果 JSON 路径(默认 cache-dir 下)")
    args = ap.parse_args()

    begin = args.enum_begin or (
        dt.date.fromisoformat(args.since) - dt.timedelta(days=1)).isoformat()
    end = args.enum_end or dt.date.today().isoformat()
    cache = Path(args.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)

    ours = load_our_rows(args.db, args.since)
    print(f"范围: {len(ours)} 行已结算 jingcai_sp (≥{args.since})", flush=True)
    mids = enum_match_ids(cache, begin, end)
    print(f"官方枚举: {len(mids)} 场 ({begin}..{end})", flush=True)

    by_team: dict[tuple[str, str], list[dict]] = {}
    n_unmapped = 0
    for i, m in enumerate(mids):
        parsed = get_official(cache, m["match_id"], args.sleep)
        if (i + 1) % 50 == 0:
            print(f"  … {i + 1}/{len(mids)} fetched", flush=True)
        if not parsed:
            continue
        h, a = parsed.get("home_team"), parsed.get("away_team")
        if not (h and a):
            n_unmapped += 1
            continue
        by_team.setdefault((h, a), []).append(parsed)
    print(f"官方入册: {len(mids)} 场 · 队名未映射 {n_unmapped}(无法比对,计 NO_OFFICIAL)",
          flush=True)

    results, counts = [], Counter()
    for r in ours:
        md = dt.date.fromisoformat(r["match_date"])
        pick = None
        for c in by_team.get((r["home_team"], r["away_team"])) or []:
            try:
                cd = dt.date.fromisoformat(c.get("close_date") or "")
            except ValueError:
                continue
            if abs((cd - md).days) <= 1:
                pick = c
                break
        base = {"match_date": r["match_date"], "home_team": r["home_team"],
                "away_team": r["away_team"], "market": r["market"],
                "source": r["source"], "captured_at": r["captured_at"],
                "jc": (r["jc_home"], r["jc_draw"], r["jc_away"]),
                "handicap_home": r["handicap_home"], "league": r["league"],
                "row_id": r["id"]}
        if pick is None:
            base["class"] = "NO_OFFICIAL"
        else:
            series = (pick.get("series") or {}).get(r["market"]) or []
            if not series:
                base["class"] = "NO_OFFICIAL_MARKET"
            else:
                base.update(classify(r, series, r["market"]))
                base["official_match_id"] = pick.get("match_id")
        results.append(base)
        counts[(base["class"], r["source"], r["market"])] += 1

    out = Path(args.out) if args.out else cache / "audit_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"\n结果 → {out}\n\n==== 分类 × source × market ====")
    for (cls, src, mkt), n in sorted(counts.items()):
        print(f"  {cls:18s} {src:16s} {mkt:5s} {n:4d}")
    bad = [x for x in results
           if x["class"] in ("FABRICATED", "MIXED_PHASE", "LINE_MISMATCH")]
    print(f"\n==== 损坏/可疑清单 ({len(bad)}) ====")
    for b in bad:
        print(f"  [{b['class']}] id={b['row_id']} {b['match_date']} {b['home_team']} vs "
              f"{b['away_team']} {b['market']} src={b['source']} jc={b['jc']} "
              f"官终={b.get('official_final')} "
              f"line={b.get('handicap_home')}/{b.get('official_line')}")
        for f in b.get("fabricated_legs") or []:
            print(f"      ⚠ {f['leg']} 腿 {f['ours']} 从未出现于官方走势 "
                  f"(官终 {f['official_final']})")
    n_cmp = sum(n for (cls, _, _), n in counts.items()
                if not cls.startswith("NO_OFFICIAL"))
    n_fab = sum(n for (cls, _, _), n in counts.items() if cls == "FABRICATED")
    print(f"\n可比 {n_cmp} 行 · FABRICATED {n_fab} 行 "
          f"({(100 * n_fab / n_cmp) if n_cmp else 0:.2f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
