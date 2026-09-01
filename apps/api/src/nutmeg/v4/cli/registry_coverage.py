"""nutmeg-registry-coverage — 「注册表/词典/字段清单即开关」的结构性疫苗.

体检 2026-07-03 元结论:24 条 P1 里过半是同一病根 — a league/team missing from
ONE registry (SPORT_KEYS / zh↔EN dict / AF league IDs / team tables) silently
degrades that slice, and the existing alarms only cover "全无" not "半坏"
(韩职 SP、韩职 sport key、瑞超队名、德乙 14/19 打不中 … all instances).

This tool diffs EVERY cell of the (cron league × registry) grid against the
LIVE API-Football team tables:

  • AF league-id registered        (league_id resolves)
  • Odds-API sport key registered  (SPORT_KEYS — the fresher-line overlay +
                                    closing-anchor reach)
  • AF team table non-empty        (current season; empty = AF not published
                                    yet OR a cached-empty bug)
  • zh↔EN dict reachability        (every AF team name reachable from some
                                    竞彩 中文名 through sporttery's reverse map
                                    + _EN_OVERRIDES — the invisible second
                                    failure mode: row written, join dead)

Run it after ANY dict/registry edit and let health_check.sh run it weekly.
Read-only; uses the AF cache (network only when a table is missing/stale-empty
per the fetch TTL, or with --refresh).

Exit code: 0 = no hard gaps (empty tables are WARN — AF publishes rosters on
its own schedule); 1 with --gate when any registry cell is missing or any
published team is dict-unreachable.
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

# The cron league set — MUST mirror LEAGUES_EUROPEAN + LEAGUES_ASIAN in
# scripts/setup_local_pipeline.sh (tests/v4/test_registry_coverage.py has a
# tripwire that parses the script and asserts equality, so a cron-league edit
# that forgets this list goes red).
CRON_LEAGUES: tuple[str, ...] = (
    "EPL", "ESP_LA_LIGA", "ITA_SERIE_A", "GER_BUNDESLIGA", "FRA_LIGUE_1",
    "ENG_CHAMPIONSHIP", "ESP_SEGUNDA_DIVISION", "ITA_SERIE_B",
    "GER_2_BUNDESLIGA", "FRA_LIGUE_2", "NED_EREDIVISIE", "PRT_PRIMEIRA_LIGA",
    "BEL_PRO_LEAGUE",
    "JPN_J1",
)

# 竞彩-common market-mode leagues (V12 W8 expansion — served via Pinnacle
# de-vig, no model). 2026-07-04 lesson: 瑞超 sat OUTSIDE the coverage scope,
# and 竞彩 listed 7 matches whose zh spellings missed the dict → 6 silently
# dropped. NB the offline zh-reachability check can be GREEN while 竞彩's own
# spellings still miss (no 竞彩 roster endpoint exists to diff against) — the
# ingest-time 过半丢失 alarm is the catcher for that; this scope extension
# catches the OTHER cells (sport key / AF id / empty table / EN drift).
MARKET_MODE_LEAGUES: tuple[str, ...] = (
    "NOR_ELITESERIEN", "SWE_ALLSVENSKAN", "FIN_VEIKKAUSLIIGA",
    "DNK_SUPERLIGA", "KOR_K_LEAGUE_1", "JPN_J2", "AUS_A_LEAGUE",
    "SCO_PREMIERSHIP", "TUR_SUPER_LIG", "SUI_SUPER_LEAGUE",
    "USA_MLS", "BRA_SERIE_A",   # 补(2026-07-14)美洲市场模式
    # 补(2026-08-05)。荷乙的 sport-key 单元会报 warn —— 那是**预期**的:
    # Odds API 没有这个 sport(见 odds_api.SPORT_KEYS 注释),同 JPN_J2。
    "NED_EERSTE_DIVISIE",
    # 补(2026-08-09 owner)。三个各带一个**不同**的预期 warn/gap:
    #   · 解放者杯 → 双源齐(Odds API active=True + AF 14 家含 Pinnacle),但队名字典缺 46;
    #   · 欧超杯   → sport-key 单元会 warn(Odds API 无此 sport,同 JPN_J2/荷乙),AF 镜像供线;
    #   · 沙职     → sport key 有但休赛期 active=False;⚠️ AF **不给赔率**(上赛季已完赛
    #                的 5 场也 0/5)⇒ Odds API 是它唯一的鲜线源,字典缺 18。
    "COPA_LIBERTADORES", "UEFA_SUPER_CUP", "SAU_PRO_LEAGUE",
)

#: 已服务但**故意不进**覆盖率检查的赛事 → 理由。
#:
#: ⭐ 2026-08-09 加。起因:我给三个新赛事接完线,这个工具照样全绿 ——
#: 因为它从**手写元组**迭代,新赛事它压根**没去看**。`CRON_LEAGUES` 有 tripwire
#: (解析 setup 脚本比对),`MARKET_MODE_LEAGUES` 一直**没有** ⇒ 静默漂移。
#: 本仓同族第 N 次:「分不出『没有缺口』和『没去看那一格』」。
#:
#: 现在的规矩:`_CUP_MARKET_COMPETITIONS` 里每一个有 AF id 的赛事,
#: 要么进 `MARKET_MODE_LEAGUES`,要么在这里写明**为什么不查**。
#: 测试 `test_registry_coverage.py::test_every_served_competition_is_either_checked_or_excused`
#: 强制这个二选一 —— 下次加赛事的人必须做一个**有意识**的选择,不能默默漏掉。
#:
#: ⚠️ 这里的条目不是「不重要」,是「这个工具的这套单元格对它没意义」:
#: 洲际/国内杯赛没有固定的赛季队表,`fetch_teams_for_league_season` 对它们
#: 要么返回一个随轮次变化的集合、要么白烧 AF 额度。解放者杯是**例外**
#: (小组赛 32 队,是个真队表)所以进了上面的清单。
OUT_OF_SCOPE: dict[str, str] = {
    "UCL":  "洲际杯赛,无固定赛季队表",
    "UEL":  "洲际杯赛,无固定赛季队表",
    "UECL": "洲际杯赛,无固定赛季队表",
    "WC":   "国家队赛事,四年一届",
    "EURO": "国家队赛事,四年一届",
    "COPA_AMERICA": "国家队赛事",
    "WC_QUAL_UEFA": "国家队预选赛,队表=会员协会",
    "FAC":            "国内杯赛,参赛队跨多级联赛",
    "EFL_CUP":        "国内杯赛,92 家 EFL 俱乐部",
    "COPA_DEL_REY":   "国内杯赛,参赛队跨多级联赛",
    "COPPA_ITALIA":   "国内杯赛,参赛队跨多级联赛",
    "DFB_POKAL":      "国内杯赛,参赛队跨多级联赛",
    "COUPE_DE_FRANCE": "国内杯赛,参赛队跨多级联赛",
    # 补(2026-08-18)— 韩国杯 KOR_FA_CUP:同 FAC/EFL_CUP,国内淘汰杯,AF 全表 64 队跨
    # K1/K2/K3/业余,52 支不在 zh 字典 —— 证据不足**不能猜**(⛔ 红线,错名比缺名更坏)。
    # ⚠️ 2026-08-18 更正上面那句「证据不足」——**它是事实错误**。
    # 实测 `data/v4_jingcai_history.db` 的 `jingcai_odds_history.home_zh/away_zh`:
    #   `大邱FC` 518+404 行 · `水原三星` 140 行 · `城南FC` 128 行
    # ⇒ 竞彩**确实用过**这些中文串,证据是有的,只是在**另一个库**里没去看。
    # 该说的是:「中文串**有**,但同表 **0 行带英文侧**(三者 has_en 全为 0)
    #   ⇒ 映射读不出来」。结论(不猜、留豁免)不变,**理由不同**。
    # ⭐ 这个区别要紧:「没有证据」会让人停止寻找;「有中文串但配不上英文名」
    #   指向正确路径 —— `scripts/anchor_team_names_by_score.py`(比分/开球时刻锚),
    #   而不是补词典、也不是放弃。同「把『没有』说成『没去看』」那一族。
    # 竞彩只上架 K1 对阵(实测 2026-08-19 Anyang×Jeju,两队已可达);下级队若真进竞彩,
    # ingest-time「过半丢失」哨兵会响。exit 条件:竞彩开始上架下级队且能照官方写法补 zh 时,
    # 再决定是否移进 MARKET_MODE_LEAGUES。（同 FAC:AF id 有、但全表队检查对它无意义。）
    # ⭐ 2026-08-18 补记:它现在**在** `_CUP_MARKET_COMPETITIONS` 里被服务了(走「竞彩
    # 在售+手填 Pinnacle」——两条自动线源都实测干涸,见 routes.py 该处注释)。所以它
    # 正好落在本字典的定义上「**已服务**但队表那格无意义」,和 FAC/EFL_CUP 完全同形。
    "KOR_FA_CUP":     "国内杯赛,参赛队跨多级联赛(K1~业余),竞彩只列 K1;下级队无 zh 证据",
    "JPN_LEAGUE_CUP": "国内杯赛,参赛队跨 J1/J2/J3,无固定赛季队表;Odds API 无 sport key",
    # 它**在** MARKET_MODE_LEAGUES 里(sport-key / AF-id 两格有意义),
    # 只有队表那一格对它无意义 —— 一年一场、两支队。
    "UEFA_SUPER_CUP": "一年一场两队,队表检查无意义",
}

#: ⛔ 窄豁免:**中文名不存在**,不是「还没补」。
#:
#: 2026-08-05 注册荷乙时,本护栏当场逮到 17 支球队没有中文名 —— 正是它该做的。
#: 其中 13 支从皇冠线史推导出了中文名(见 `team_name_zh._V12_W8_NEW_LEAGUES` 里
#: 那段)。剩下这 4 支是**预备队**,证据说它们的中文名根本不存在:
#:
#:   `crown_close_history` 里 荷乙 105 场、19 个不同的中文队名,**一支预备队都
#:   没有** ⇒ 竞彩不上架它们 ⇒ 它们永远不会成为一条可投注的腿 ⇒ 没有可抄的
#:   中文写法。编一个是瞎猜(而错的队名会静默污染 join,比缺名字更坏)。
#:
#: ⚠️ 为什么**逐条列名**而不是写 `name.startswith("Jong ")`:那是拿「名字里有
#: 没有某串字符」代替「它是不是一支竞彩不上架的预备队」—— 同一个反复出现的
#: 错误(见 [[syntactic-proxy-for-semantic-property]])。前缀规则会顺手放行任何
#: 未来叫 Jong 开头的**一队**,而这四个名字变了就该重新报警。
#:
#: 若哪天竞彩真的上架了预备队,ingest 侧的「整联赛丢失 / 过半未映射」报警会响。
NO_CHINESE_NAME_EXISTS: frozenset[str] = frozenset({
    "Jong Ajax", "Jong AZ", "Jong PSV U21", "Jong Utrecht",
})

#: ⭐ 2026-08-10 从 `tests/v4/test_registry_coverage.py` 搬过来 —— 它原来只有测试认,
#: CLI 不认 ⇒ **测试绿、体检红**,而红的那条恰恰是早已接受的永久状态。
#: 这和紧接着的 `NO_JINGCAI_ANCHOR` 是同一个病(白名单只装在一半的消费方上),
#: 上一批只修了新加的那一半,这次收口。两个白名单现在都是**单一真相源**。

#: AF 队表里有、但竞彩**从未上架过**的球队 → 没有任何锚可以拿到它们的中文名。
#:
#: ⭐ 2026-08-09 加。给解放者杯/沙职补队名时,`scripts/anchor_team_names_by_score.py`
#: 用**比分锚定**把竞彩上架过的队全部钉住了(50/50、18/18、4/4,见 team_name_zh.py
#: 里那段长注释)。剩下的这些队竞彩一场都没卖过 ⇒ 档案里根本没有它们的中文名,
#: 而本仓红线「绝不照英文猜译名」堵死了唯一剩下的路。
#:
#: ⚠️ 它们**不属于**上面的 `NO_CHINESE_NAME_EXISTS` —— 那个白名单是「这支队真的没有中文名」
#: (荷兰的 Jong 预备队),而这些队当然有中文名,只是**我们的数据里没有**。
#: 把两者混在一起会让「没有」和「没去看」再一次分不出来。
#:
#: 🚨 这个白名单**不是**降低标准:`tests/v4/test_registry_coverage.py` 里的
#: `test_jingcai_listed_teams_are_fully_reachable` 在**会下注的人口**上断言 100%,
#: 那才是真正会花钱的那条闸。这里放行的全是不可能出现在竞彩腿上的队。
#:
#: ⛔ 往这里加名字前先问:这支队竞彩真的没上架过吗?(去 jingcai_odds_history 数一遍。)
#: 如果上架过而解析不出,那是**真缺口**,该去跑锚定器,不是往这里加一行。
NO_JINGCAI_ANCHOR: dict[str, tuple[str, ...]] = {
    "COPA_LIBERTADORES": (
        "Argentinos JRS", "Universidad Catolica", "Club Guarani", "2 de Mayo",
        "O'Higgins", "Huachipato", "Juventud", "Liverpool Montevideo",
        "Carabobo FC", "Nacional Potosí",   # ⚠️ 带重音 —— 我第一版敲成 Potosi 当场红了
    ),
    "SAU_PRO_LEAGUE": ("Al-Faisaly FC", "Abha", "Al Diriyah"),
}


def check_league(league: str, *, refresh: bool = False) -> dict:
    """One coverage row: registry cells + dict-unreachable AF team names."""
    import contextlib

    from nutmeg.v4.data.sources import odds_api
    from nutmeg.v4.data.sources.api_football import (
        ApiFootballError,
        fetch_teams_for_league_season,
        league_id,
        season_for_date,
    )
    from nutmeg.v4.data.sources.sporttery import _EN_OVERRIDES, _ZH_TO_EN

    row: dict = {"league": league, "af_id": None, "sport_key": None,
                 "n_teams": None, "unreachable": [], "excused": [], "error": None}
    with contextlib.suppress(Exception):  # missing registry entry IS the finding
        row["af_id"] = league_id(league)
    row["sport_key"] = odds_api.SPORT_KEYS.get(league)
    if row["af_id"] is None:
        return row
    season = season_for_date(datetime.now(UTC).date(), league)
    try:
        teams = fetch_teams_for_league_season(league, season, refresh=refresh)
    except ApiFootballError as e:
        row["error"] = str(e)[:120]
        return row
    names = sorted(t["team"]["name"] for t in teams)
    row["n_teams"] = len(names)
    reachable = {_EN_OVERRIDES.get(en, en) for en in _ZH_TO_EN.values()}
    # ⚠️ 白名单里的队竞彩**从没上架过** ⇒ 它们解析不出掉不了任何一条腿。
    # 报成硬缺口会让这个工具**永远红**,而永远红的体检最后没人看
    # (「假红比假绿更贵」)。测试 `test_registry_coverage.py` 与本模块共用
    # 这同一个 `NO_JINGCAI_ANCHOR` —— 单一真相源,两边不会各说各话。
    excused = set(NO_JINGCAI_ANCHOR.get(league, ())) | set(NO_CHINESE_NAME_EXISTS)
    row["unreachable"] = [n for n in names if n not in reachable and n not in excused]
    row["excused"] = sorted(n for n in names if n in excused)
    return row


def run(leagues, *, refresh: bool = False) -> tuple[list[dict], list[str], list[str]]:
    """→ (rows, hard_gaps, warnings). Hard gap = a registry cell missing or a
    published team the dict can't reach; warning = empty/unfetched table."""
    rows, gaps, warns = [], [], []
    for lg in leagues:
        r = check_league(lg, refresh=refresh)
        rows.append(r)
        if r["af_id"] is None:
            gaps.append(f"{lg}: AF league-id 未注册 (_DOMESTIC_LEAGUE_IDS)")
        if r["sport_key"] is None:
            # A missing sport key is only a HARD gap for cron leagues (the
            # fresher-line overlay/closing anchor need it). Market-mode
            # leagues price off the AF mirror by design — warn, don't gate.
            if lg in CRON_LEAGUES:
                gaps.append(f"{lg}: Odds-API sport key 未注册 (SPORT_KEYS)")
            else:
                warns.append(f"{lg}: 无 Odds-API sport key (市场模式走 AF 镜像, 设计内)")
        if r["error"]:
            warns.append(f"{lg}: AF /teams 拉取失败 — {r['error']}")
        elif r["n_teams"] == 0:
            warns.append(f"{lg}: AF 队表为空 (当季未发布? TTL 会自动重试)")
        if r["unreachable"]:
            gaps.append(
                f"{lg}: {len(r['unreachable'])}/{r['n_teams']} 队 zh 字典打不中 → "
                + ", ".join(r["unreachable"][:6])
                + (" …" if len(r["unreachable"]) > 6 else "")
            )
    return rows, gaps, warns


def render(rows: list[dict], gaps: list[str], warns: list[str]) -> str:
    lines = [f"# 注册表覆盖率 diff (cron 联赛 × SPORT_KEYS × AF 队表 × zh 字典) "
             f"— {datetime.now(UTC).date()}", ""]
    for r in rows:
        ok_id = "✓" if r["af_id"] else "✗"
        ok_sk = "✓" if r["sport_key"] else "✗"
        if r["error"]:
            teams = "拉取失败"
        elif r["n_teams"] is None:
            teams = "—"
        elif r["n_teams"] == 0:
            teams = "空表⚠"
        else:
            teams = f"{r['n_teams']}队"
        dic = ("—" if not r["n_teams"]
               else ("✓ 全可达" if not r["unreachable"]
                     else f"✗ {len(r['unreachable'])} 打不中"))
        lines.append(f"  {r['league']:22} AF_id {ok_id} · sport_key {ok_sk} · "
                     f"队表 {teams:8} · zh字典 {dic}")
    lines.append("")
    if gaps:
        lines.append("硬缺口 (该切片已静默降级):")
        lines += [f"  ✗ {g}" for g in gaps]
    if warns:
        lines.append("警告:")
        lines += [f"  ⚠ {w}" for w in warns]
    if not gaps and not warns:
        lines.append("判定: ✓ 注册表全格覆盖,无静默降级切片。")
    elif not gaps:
        lines.append("判定: ✓ 无硬缺口 (仅待发布队表)。")
    else:
        lines.append("判定: ✗ 有硬缺口 — 修对应注册表/字典后重跑。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="注册表覆盖率 diff — 缺格即报")
    p.add_argument("--leagues", default=None,
                   help="逗号分隔联赛码 (默认 = cron 全集)")
    p.add_argument("--refresh", action="store_true", help="强制重拉 AF 队表")
    p.add_argument("--gate", action="store_true",
                   help="有硬缺口时 exit 1 (给 health_check/cron 用)")
    args = p.parse_args(argv)

    leagues = ([s.strip() for s in args.leagues.split(",") if s.strip()]
               if args.leagues else list(CRON_LEAGUES) + list(MARKET_MODE_LEAGUES))
    rows, gaps, warns = run(leagues, refresh=args.refresh)
    print(render(rows, gaps, warns))
    return 1 if (args.gate and gaps) else 0


if __name__ == "__main__":
    sys.exit(main())
