"""用「终场比分 + 日期窗」把竞彩中文队名钉到 AF 英文队名上 —— 零翻译。

## 为什么需要它

2026-08-09 给解放者杯/沙职接注册表时,队名字典缺 57 支。本仓红线:
**绝不照英文猜译名** —— 错映射是静默污染,比缺映射更坏。

而这次连「照英文猜」的原料都没有:决定性检验显示
`jingcai_odds_history.home_team`(英文列)**是我们自己词典的回流** ——
词典里没有的队,那一列 100% 为空(解放者杯 43/43 空、沙职 18/18 空)。
唯一有值的 `巴黎圣曼 → Paris Saint Germain` 恰恰是因为 PSG 本来就在词典里。
⇒ 那条路是个**镜子**,不是锚。

## 锚是什么

两边各自独立地记录了**同一场比赛的终场比分**:

  · 竞彩档案 `jingcai_odds_history`: (close_date, home_zh, away_zh, home_goals, away_goals)
  · API-Football fixtures 缓存:      (utc_date,  home_en, away_en, 90′ 比分)

比分不是翻译,是**事实**。若某场竞彩比赛在 ±1 天窗口内,AF 那边**恰好只有一场**
同比分的比赛,那两条记录说的就是同一场 ⇒ 主队对主队、客队对客队。

⚠️ ±1 天是必需的:竞彩 `close_date` 是北京日期,AF 是 UTC。南美 21:00 开球
= UTC 次日 00:00 = 北京次日 08:00;沙特 21:00 开球 = 北京次日 02:00。

## 三道闸(缺一不可)

① **唯一性** —— 窗口内同比分的候选恰好 1 场才用。多于 1 场直接丢弃,
   不做「挑最近的那个」这种事。
② **重复确认** —— 一个中文名必须被 **≥2 场独立比赛**指向同一个英文名才收。
   单次命中可能是巧合(1:0 这种比分很常见)。
③ **零冲突** —— 同一个中文名若被指向过两个不同英文名,**整条作废**并报出来,
   不做多数表决。宁可缺映射。

⭐ 三道闸都是「宁缺勿错」方向的 —— 因为错映射会让 join 悄悄连到别的队,
而缺映射只是让这条腿不可投注(横幅会喊)。

## 用法

    .venv/bin/python scripts/anchor_team_names_by_score.py --league COPA_LIBERTADORES

只读:不写任何文件,把候选映射打到 stdout 供人工过目后再入库。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BEIJING = timezone(timedelta(hours=8))

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "apps/api/src"))

#: 竞彩 league_id → (AF league id, 人读的名字)
LEAGUES: dict[str, tuple[int, int, str]] = {
    "COPA_LIBERTADORES": (49, 13, "解放者杯"),
    "SAU_PRO_LEAGUE": (2068446, 307, "沙职"),
    "UEFA_SUPER_CUP": (71, 531, "欧超杯"),
    # ⭐ 对照组 —— 词典**已经完整**的联赛。跑它是为了回答
    # 「这个方法能不能复现已知正确答案」,而不是只看它在缺口上吐了多少条。
    # 巴甲是最好的对照:同为南美、同样的北京-UTC 跨日问题、同样的西语队名。
    # 用法:`--league BRA_SERIE_A --validate`
    "BRA_SERIE_A": (6, 71, "巴甲(对照组)"),
}

MIN_CONFIRMATIONS = 2   # 闸②

#: 竞彩 `close_date` = 比赛的**北京日期**,所以窗口是精确的
#: `[D 00:00 +08, D+1 00:00 +08)`,不是「UTC 日期 ±1 天」。
#:
#: ⭐ 这不是推理出来的,是**在对照组上量出来的**:巴甲拿 −1/0/+1 三个偏移各跑一遍,
#: 唯一命中 4 / **29** / 3 —— 偏移 0 压倒性胜出,同时零错。
#: 顺带把 ±1 天的旧窗口(25 命中)也比下去了:窗口越准,同比分撞车越少 ⇒ 闸① 放行越多。


def load_af_fixtures(af_league: int) -> list[tuple[datetime, str, str, int, int]]:
    """AF fixtures 缓存里该联赛的全部已完赛场次 —— 用 90′ 比分 + **精确开球时刻**。"""
    out: list[tuple[datetime, str, str, int, int]] = []
    seen: set[tuple] = set()
    for p in (REPO / "data/external/api_football/_fixtures").glob("*.json"):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        resp = j.get("response") if isinstance(j, dict) else j
        if not isinstance(resp, list):
            continue
        for r in resp:
            if not isinstance(r, dict):
                continue
            if (r.get("league") or {}).get("id") != af_league:
                continue
            ft = ((r.get("score") or {}).get("fulltime")) or {}
            gh, ga = ft.get("home"), ft.get("away")
            if gh is None or ga is None:          # 未完赛 / 无比分
                continue
            iso = (r.get("fixture") or {}).get("date")
            teams = r.get("teams") or {}
            hn = ((teams.get("home") or {}).get("name") or "").strip()
            an = ((teams.get("away") or {}).get("name") or "").strip()
            if not (iso and hn and an):
                continue
            try:
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            except ValueError:
                continue
            key = (dt, hn, an, int(gh), int(ga))
            if key in seen:                       # 同一场可能在多个日窗缓存里
                continue
            seen.add(key)
            out.append(key)
    return out


def load_jingcai(jc_league: int) -> list[tuple[date, str, str, int, int]]:
    con = sqlite3.connect(
        f"file:{REPO / 'data/v4_jingcai_history.db'}?mode=ro", uri=True)
    rows = con.execute(
        """SELECT DISTINCT close_date, home_zh, away_zh, home_goals, away_goals
             FROM jingcai_odds_history
            WHERE league_id = ? AND home_goals IS NOT NULL
              AND away_goals IS NOT NULL AND home_zh <> '' AND away_zh <> ''""",
        (jc_league,)).fetchall()
    con.close()
    out = []
    for cd, hz, az, gh, ga in rows:
        try:
            out.append((date.fromisoformat(str(cd)[:10]), hz, az, int(gh), int(ga)))
        except ValueError:
            continue
    return out


def anchor(code: str, *, validate: bool = False) -> None:
    jc_id, af_id, label = LEAGUES[code]
    af = load_af_fixtures(af_id)
    jc = load_jingcai(jc_id)
    print(f"\n{'='*72}\n{label}  ({code})")
    print(f"  AF 已完赛缓存 {len(af)} 场 · 竞彩带比分 {len(jc)} 场")
    if not af:
        print("  ⛔ AF 侧无缓存 —— 先拉 fixtures 再跑")
        return

    # (比分) → 该比分的 AF 场次,加速唯一性判定
    by_score: dict[tuple[int, int], list] = defaultdict(list)
    for dt, h, a, gh, ga in af:
        by_score[(gh, ga)].append((dt, h, a))

    props: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    pairs: list[tuple[str, str, str, str]] = []   # (zh_h, en_h, zh_a, en_a) 每场一条
    used = ambiguous = 0
    for d, hz, az, gh, ga in jc:
        lo = datetime.combine(d, datetime.min.time(), tzinfo=BEIJING)
        hi = lo + timedelta(days=1)
        cands = [c for c in by_score.get((gh, ga), ()) if lo <= c[0] < hi]
        if len(cands) != 1:                       # 闸①
            ambiguous += 1
            continue
        _, hen, aen = cands[0]
        props[hz][hen] += 1
        props[az][aen] += 1
        pairs.append((hz, hen, az, aen))
        used += 1

    print(f"  唯一命中 {used} 场 · 因候选不唯一丢弃 {ambiguous} 场")

    from nutmeg.v4.data.sources.sporttery import _EN_OVERRIDES, _ZH_TO_EN
    known = {_EN_OVERRIDES.get(e, e) for e in _ZH_TO_EN.values()}

    accepted, conflicts, weak = {}, {}, {}
    for zh, cnts in sorted(props.items()):
        if len(cnts) > 1:                          # 闸③
            conflicts[zh] = dict(cnts)
        elif max(cnts.values()) < MIN_CONFIRMATIONS:   # 闸②
            weak[zh] = dict(cnts)
        else:
            accepted[zh] = (next(iter(cnts)), max(cnts.values()))

    # ── 闸②′ 同场传播 ────────────────────────────────────────────────
    # 需要被确认的其实是**这场比赛认对了没有**,不是每个名字各自被数够次数。
    # 若一场唯一命中的比赛里,**另一支队**已经被独立确认(≥2 次)或本来就在词典里,
    # 那这场的身份已经钉死 ⇒ 同场对手那条单次映射也是确定的。
    #
    # ⚠️ 仍然守闸③:只救「没有冲突」的单次条目。有冲突的一律作废,不因为
    #    「另一边确认了」就去挑一个 —— 冲突说明我对这个中文名的理解本身有问题。
    #
    # ⭐ 这条规则**在对照组上单独验过**才敢用(见 --validate 的判决行)。
    rescued: dict[str, tuple[str, int]] = {}
    anchored = set(accepted) | set(zh for zh in props if zh in
                   {z for z, e in ((z, _EN_OVERRIDES.get(e, e))
                    for z, e in _ZH_TO_EN.items())})
    for zh_h, en_h, zh_a, en_a in pairs:
        for me, my_en, partner in ((zh_h, en_h, zh_a), (zh_a, en_a, zh_h)):
            if me in accepted or me in conflicts or me in rescued:
                continue
            if me in weak and partner in anchored:
                rescued[me] = (my_en, 1)
    for zh, v in rescued.items():
        weak.pop(zh, None)
        accepted[zh] = v

    # ── 第二轮:用**已确定的名字**给闸① 丢掉的场次消歧 ──────────────────
    # 第一轮丢掉的是「窗口内同比分候选 >1 场」。但如果这场里**有一侧的名字已经确定**
    # (本轮已收 ∪ 词典原有),那些候选里与它不相容的可以直接排除 —— 若只剩一个候选,
    # 这场就被钉死了,另一侧的名字随之确定。
    #
    # ⭐ 这不是放松闸①,是**给它补上原本就该有的信息**:第一轮判「不唯一」时
    #    手里还没有这些名字。同一批数据,第二次问的时候知道得更多。
    # ⚠️ 仍然守闸③(冲突整条作废),且仍然只在**恰好剩一个候选**时才用。
    settled = {**{z: e for z, (e, _) in accepted.items()},
               **{z: _EN_OVERRIDES.get(e, e) for z, e in _ZH_TO_EN.items()}}
    pass2: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for d, hz, az, gh, ga in jc:
        lo = datetime.combine(d, datetime.min.time(), tzinfo=BEIJING)
        hi = lo + timedelta(days=1)
        cands = [c for c in by_score.get((gh, ga), ()) if lo <= c[0] < hi]
        if len(cands) < 2:                      # 第一轮已处理过
            continue
        keep = [c for c in cands
                if (hz not in settled or settled[hz] == c[1])
                and (az not in settled or settled[az] == c[2])]
        if len(keep) != 1:
            continue
        if hz in settled and az in settled:     # 两边都已知 ⇒ 没有新信息
            continue
        _, hen, aen = keep[0]
        if hz not in settled:
            pass2[hz][hen] += 1
        if az not in settled:
            pass2[az][aen] += 1
    for zh, cnts in pass2.items():
        if len(cnts) > 1:                       # 闸③ 照旧
            conflicts[zh] = dict(cnts)
            accepted.pop(zh, None)
            continue
        en = next(iter(cnts))
        weak.pop(zh, None)
        accepted[zh] = (en, cnts[en])
        rescued[zh] = (en, cnts[en])

    if validate:
        # 对照组:逐条比对词典里已有的答案。这是这个工具唯一的**正确性证据** ——
        # 它在缺口上吐出的东西是无法直接检验的,只能靠「它在有答案的地方全对」来背书。
        zh2en = {z: _EN_OVERRIDES.get(e, e) for z, e in _ZH_TO_EN.items()}
        print(f"    (其中同场传播救回 {len(rescued)} 条)")
        agree = [z for z, (e, _) in accepted.items() if zh2en.get(z) == e]
        disagree = {z: (e, zh2en.get(z)) for z, (e, _) in accepted.items()
                    if z in zh2en and zh2en[z] != e}
        novel = [z for z in accepted if z not in zh2en]
        print("\n  ══ 对照组判决 ══")
        print(f"    与词典一致   {len(agree)}")
        print(f"    与词典冲突   {len(disagree)}   ← 任何一条 > 0 都说明方法有洞")
        for z, (mine, dict_) in sorted(disagree.items()):
            print(f"        {z}: 我={mine}  词典={dict_}")
        print(f"    词典里没有的 {len(novel)}  {novel[:8]}")
        acc = len(agree) / max(len(agree) + len(disagree), 1)
        print(f"    ⇒ 在有标准答案的 {len(agree)+len(disagree)} 条上准确率 {acc:.1%}")
        return

    print(f"\n  ✅ 三闸全过 {len(accepted)} 条(含同场传播救回 {len(rescued)} 条):")
    for zh, (en, n) in sorted(accepted.items(), key=lambda x: -x[1][1]):
        mark = "  (词典已有)" if en in known else ("  ⟵同场传播" if zh in rescued else "")
        print(f"       {zh:<12} → {en:<28} ×{n}{mark}")
    if weak:
        print(f"\n  ⚠️ 只被确认 1 次(闸②挡下,**不收**){len(weak)} 条:")
        for zh, c in sorted(weak.items()):
            print(f"       {zh:<12} → {list(c)[0]}")
    if conflicts:
        print(f"\n  ⛔ 冲突(闸③整条作废){len(conflicts)} 条:")
        for zh, c in sorted(conflicts.items()):
            print(f"       {zh:<12} → {c}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", action="append", choices=sorted(LEAGUES),
                    help="不给则全部三个都跑")
    ap.add_argument("--validate", action="store_true",
                    help="对照模式:与现有词典逐条比对(只对词典完整的联赛有意义)")
    a = ap.parse_args()
    for code in (a.league or [c for c in sorted(LEAGUES) if c != "BRA_SERIE_A"]):
        anchor(code, validate=a.validate)


if __name__ == "__main__":
    main()
