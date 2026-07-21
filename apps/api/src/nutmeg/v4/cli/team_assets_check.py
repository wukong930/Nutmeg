"""新队「三件套」覆盖哨兵 — 队名翻译 + 队徽(2026-07-21)。

同一支新队要显示正确,得同时命中三套**互不相干**的机制:

  ① join 映射  `_ZH_TO_EN`(= `TEAM_NAME_ZH` 的反转)  缺 → 竞彩整场丢弃,算不了 EV
  ② 队名翻译  `TEAM_NAME_ZH`                          缺 → 卡片显示英文名
  ③ 队徽      `data/external/team_logos/<slug>.png`   缺 → 落回首字母圆圈

⚠️ **本工具只查 ②③**。① **早就有哨兵而且是对的**(`ingest_sporttery.summarize_unmapped`
→ `logs/sporttery_unmapped_latest.txt` + 面板常驻横幅 + `/observation/jingcai-unmapped`,
health_check 第 11 节)—— 别在这里重造第二套判据(见 `记忆 dashboard-icon-system`)。

**和 ① 那个哨兵的关键分工:它是反应式的**(竞彩已经上架、场已经被丢了才报),
**本工具是预测式的** —— 读的是**未来赛程**(`odds_snapshots` 里 kickoff 还没到的场),
在竞彩上架**之前**就点名哪些队缺件。欧战资格赛每轮都带一批新小球会,提前一天补完,
竞彩上架当天就不会再瞎。

②③ 都**不影响钱**(EV 算得对不对只取决于 ①+Pinnacle 线),所以本工具**只发 ⚠ 不发 ✗**,
不该让 health_check 变红。

纯离线:只读本地 DB + 本地字典 + 本地目录,**零 API 配额**。
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3

from nutmeg.v4.data.team_logos import logo_exists, team_slug
from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH


def collect_upcoming_teams(db: str, *, days: int) -> dict[str, tuple[str, str]]:
    """→ {EN 队名: (联赛, 最近一场 kickoff_utc)},取未来 ``days`` 天的赛程。"""
    now = dt.datetime.now(dt.UTC)
    until = (now + dt.timedelta(days=days)).isoformat()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT DISTINCT home_team, away_team, league, kickoff_utc FROM odds_snapshots "
            "WHERE kickoff_utc >= ? AND kickoff_utc <= ? ORDER BY kickoff_utc",
            (now.isoformat(), until),
        ).fetchall()
    finally:
        conn.close()
    teams: dict[str, tuple[str, str]] = {}
    for home, away, league, kickoff in rows:
        for name in (home, away):
            if name:
                teams.setdefault(name, (league or "?", kickoff or ""))
    return teams


def audit(teams: dict[str, tuple[str, str]]) -> tuple[list[str], list[str]]:
    """→ (缺中文名的队, 缺队徽的队),各自按 kickoff 升序。"""
    by_kickoff = sorted(teams, key=lambda n: (teams[n][1], n))
    no_zh = [n for n in by_kickoff if n not in TEAM_NAME_ZH]
    no_logo = [n for n in by_kickoff if not logo_exists(n)]
    return no_zh, no_logo


def render(teams: dict[str, tuple[str, str]], no_zh: list[str], no_logo: list[str],
           *, days: int, limit: int = 12) -> str:
    """人读报告。health_check 只 grep ⚠ 行,别改前缀。"""
    lines = [f"新队三件套 · 未来 {days} 天 {len(teams)} 队(① join 另见第 11 节哨兵)"]

    def _block(names: list[str], label: str, consequence: str, fix: str) -> None:
        if not names:
            lines.append(f"  ✓ {label}:全覆盖")
            return
        lines.append(f"  ⚠ {label}:缺 {len(names)} 队 — {consequence}")
        for name in names[:limit]:
            league, kickoff = teams[name]
            lines.append(f"      [{league}] {name}  开球 {kickoff[:16]}")
        if len(names) > limit:
            lines.append(f"      … 另 {len(names) - limit} 队")
        lines.append(f"      补法:{fix}")

    _block(
        no_zh, "② 队名翻译", "卡片显示英文名;且竞彩若上架该场会因反转字典缺键而整场丢弃",
        "⚠️ 这是**风险预报,不是待办清单** —— 官方中文写法只能等竞彩上架后照抄"
        "(第 11 节哨兵会点名),或用 sporttery.py 那套「同日 + 已确认对手当锚」推出来。"
        "**绝不照英文猜译名**:错映射=静默污染 join,比缺映射更坏(缺了至少哨兵会响)",
    )
    _block(
        no_logo, "③ 队徽", "落回首字母圆圈(仅显示,不影响 EV)",
        "nutmeg-ingest-team-logos --league <CODE> --season <YEAR>;"
        "单队可从本地 fixture 缓存取 logo URL 直下,零配额",
    )
    if no_logo:
        lines.append("      slug 示例:" + ", ".join(
            f"{n}→{team_slug(n)}.png" for n in no_logo[:2]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="新队三件套覆盖哨兵(队名翻译 + 队徽)")
    p.add_argument("--db", default="data/v4_observation.db", help="observation DB")
    p.add_argument("--days", type=int, default=7, help="向前看几天的赛程(默认 7)")
    p.add_argument("--limit", type=int, default=12, help="每类最多点名几队(默认 12)")
    args = p.parse_args(argv)

    teams = collect_upcoming_teams(args.db, days=args.days)
    if not teams:
        print(f"新队三件套 · 未来 {args.days} 天无赛程(休赛期?)— 无可查")
        return 0
    no_zh, no_logo = audit(teams)
    print(render(teams, no_zh, no_logo, days=args.days, limit=args.limit))
    return 0  # ②③ 不影响钱 → 永不 fail,只发 ⚠


if __name__ == "__main__":
    raise SystemExit(main())
