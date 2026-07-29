"""竞彩 ↔ football-data 队名别名**诊断**(只读,不改任何映射表)。2026-07-29

## ⚠️ 首跑结论已被推翻 —— 读之前先看这段

本脚本第一次跑出「28 个别名建议收」,**那个前提是错的**:那 28 个里的
`Manchester United→Man United`、`Nottingham Forest→Nott'm Forest` 等
**`TEAM_ALIASES` 里本来就有**。真正的根因是
`handicap_delta_homogeneity.py` 用了**裸 `normalize_name`**,把
`to_v4_canonical` 的**别名层整个跳过**了(与记忆「跨源 join 别裸
normalize_name」是同一条规则)。改走解析器后 join 命中 **41% → 67%**,
`TEAM_ALIASES` **一条新别名都没加**。

⇒ 本脚本保留的价值是**找真正缺失的别名**(解析器也解不出来的),
不是它首跑时以为的那 28 个。用它之前先确认调用方已经走了解析器。

## 为什么做这个

追 δ₊₁ 的功效时撞见:真实竞彩 ±1 让球线共 **7,381** 场,join 只命中 **3,038(41%)**,
未中 4,343 场里 **99% 是队名不认识**(只有 1% 是日期没对上),而不认识的独立名字只有
**87 个** —— 且全是 football-data 的经典缩写惯例(`AC Milan`→`Milan`、
`Manchester United`→`Man United`、`Nottingham Forest`→`Nott'm Forest`…)。

⇒ **δ₊₁ 独立确立所需的数据今天就在硬盘上**:+1 线补回 1,543 场 ⇒ 约 2,623 场,
而 80% 功效的目标是 2,616。不必等 2.7 年,也不必在「部分合并 / 完全合并」之间取舍。

## ⚠️ 红线:绝不瞎猜队名

错映射 = **静默 join 污染,比缺失更糟**。所以本脚本**不做任何字符串模糊匹配**,
两道独立的证据链:

**① 候选来自「赛事身份」,不是名字相似度。** 若竞彩说「AC Milan vs Juventus @ 3-10」
   而 football-data 同日有「X vs Juventus」,则 X 是 AC Milan 的候选 —— 这是**对手+日期**
   锚定出来的,与两个名字长得像不像无关。

**② 比分硬闸验证。** 每个候选别名会启用一批比赛;要求这些比赛**两侧比分完全一致**。
   一个错映射几乎不可能在几十场上连续通过比分校验。现有样本这道闸的拒绝率是
   **0.00%** —— 说明它现在没在做功,补别名之后它才第一次真正承重。

判据(**先声明**):`N ≥ 20 场` **且** `比分一致率 = 100%` **且** `候选唯一` 才建议收。
任一不满足 → 列出但**不建议**,交人工看。

只读:不写 `TEAM_ALIASES`、不写库、不改任何 δ。
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handicap_delta_homogeneity import load_football_data  # noqa: E402

from nutmeg.utils.team_canonical import normalize_name as nn  # noqa: E402

_MIN_N = 20            # 判据:至少这么多场才够下结论
_DAY_SLACK = (0, -1, 1)


def load_jingcai(db: str) -> list[dict]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    with conn:
        rows = conn.execute(
            "SELECT match_id, close_date, home_team, away_team, goal_line, league_cn, "
            "home_goals, away_goals FROM jingcai_odds_history WHERE market='hhad' "
            "AND goal_line IS NOT NULL AND home_goals IS NOT NULL "
            "ORDER BY match_id, seq").fetchall()
    out = {}
    for r in rows:
        if r["goal_line"] is None or abs(int(r["goal_line"])) != 1:
            continue
        out[r["match_id"]] = dict(r)          # 同 match_id 取末条 = 终盘
    return list(out.values())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="竞彩↔football-data 别名诊断(只读)")
    ap.add_argument("--db", default="data/v4_jingcai_history.db")
    args = ap.parse_args(argv)

    # ⚠️ load_football_data 现在返回 (索引, 原始队名池);池给 to_v4_canonical 用,
    # 本脚本只需索引 —— 它的职责是找**解析器也解不出来**的名字。
    fd, _raw_pool = load_football_data()
    fd_names = {k[0] for k in fd} | {k[1] for k in fd}
    by_away: dict = defaultdict(list)         # (away, date) → [(home, fh, fa)]
    by_home: dict = defaultdict(list)
    for (h, a, d), (_psc, _ov, _un, fh, fa) in fd.items():
        by_away[(a, d)].append((h, fh, fa))
        by_home[(h, d)].append((a, fh, fa))

    jc = load_jingcai(args.db)
    print(f"竞彩 ±1 让球线 {len(jc)} 场 · football-data 索引 {len(fd)} 场 / "
          f"{len(fd_names)} 个规范化队名\n")

    # ── 候选生成:靠**对手+日期**锚定,不靠名字相似度 ────────────────────
    #: unknown_norm → Counter{candidate_fd_norm: 票数}
    votes: dict = defaultdict(Counter)
    #: (unknown, candidate) → [(比分一致?, 竞彩原名, 联赛)]
    evid: dict = defaultdict(list)
    unmatched = 0
    for m in jc:
        h, a = nn(m["home_team"] or ""), nn(m["away_team"] or "")
        if not h or not a:
            continue
        d0 = dt.date.fromisoformat(m["close_date"][:10])
        if any((h, a, d0 + dt.timedelta(days=o)) in fd for o in _DAY_SLACK):
            continue                          # 已经能 join,不需要别名
        unmatched += 1
        hk, ak = h in fd_names, a in fd_names
        for o in _DAY_SLACK:
            d = d0 + dt.timedelta(days=o)
            if ak and not hk:                 # 客队已知 → 反解主队
                for cand, fh, fa in by_away.get((a, d), []):
                    votes[h][cand] += 1
                    evid[(h, cand)].append(
                        ((fh, fa) == (m["home_goals"], m["away_goals"]),
                         m["home_team"], m["league_cn"]))
            elif hk and not ak:               # 主队已知 → 反解客队
                for cand, fh, fa in by_home.get((h, d), []):
                    votes[a][cand] += 1
                    evid[(a, cand)].append(
                        ((fh, fa) == (m["home_goals"], m["away_goals"]),
                         m["away_team"], m["league_cn"]))
    print(f"未 join 的场次 {unmatched} · 靠对手锚定出候选的未知名字 {len(votes)} 个\n")

    accept, review = [], []
    for unk, cands in votes.items():
        # ⚠️ 候选必须**唯一**:一个未知名字锚出两个不同球队 = 有歧义,一律不收
        top = cands.most_common()
        solid = [(c, n) for c, n in top if n >= 5]     # 票数太少的候选先滤掉噪声
        raw = evid[(unk, top[0][0])][0][1] if evid[(unk, top[0][0])] else unk
        lg = Counter(x[2] for x in evid[(unk, top[0][0])]).most_common(1)
        lg = lg[0][0] if lg else "?"
        if len(solid) != 1:
            review.append((raw, unk, "候选不唯一", top[:3], 0, 0.0, lg))
            continue
        cand, _ = solid[0]
        ev = evid[(unk, cand)]
        n = len(ev)
        ok = sum(1 for hit, _, _ in ev if hit)
        rate = ok / n if n else 0.0
        row = (raw, cand, n, rate, lg)
        if n >= _MIN_N and rate == 1.0:
            accept.append(row)
        else:
            reason = "场次不足" if n < _MIN_N else f"比分不一致 {n - ok} 场"
            review.append((raw, unk, reason, [(cand, n)], n, rate, lg))

    accept.sort(key=lambda r: -r[2])
    print("=" * 78)
    print(f"✅ 通过判据(N≥{_MIN_N} 且 比分一致率 100% 且 候选唯一)—— **建议收**")
    print("=" * 78)
    print(f"{'竞彩写法':<30}{'football-data 写法':<26}{'N':>5}{'一致率':>8}  联赛")
    for raw, cand, n, rate, lg in accept:
        print(f"{raw:<30}{cand:<26}{n:>5}{rate:>8.0%}  {lg}")
    print(f"\n合计 {len(accept)} 个别名,可启用 {sum(r[2] for r in accept)} 场匹配")

    print("\n" + "=" * 78)
    print("⚠️ 未通过 —— **不建议自动收,交人工看**")
    print("=" * 78)
    review.sort(key=lambda r: -r[4])
    for raw, _unk, reason, top, n, rate, lg in review[:25]:
        cands = " / ".join(f"{c}×{v}" for c, v in top)
        print(f"  {str(raw):<28}{reason:<18}N={n:<5}一致率 {rate:>4.0%}  候选: {cands}  [{lg}]")
    if len(review) > 25:
        print(f"  … 另有 {len(review) - 25} 个")
    print("\n⚠️ 本脚本**只诊断,不改任何映射表**。收哪些由 owner 定;"
          "收完后 δ 样本翻倍 = 新测量,须重新预注册再评。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
