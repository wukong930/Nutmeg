"""上游队名拼法归一 —— **`odds_snapshots` 写入前的唯一收口**(2026-08-01)。

## 问题

两个上游对同一支球队用不同英文名:
  · API-Football  → `cup_market` / `predict_log`(= **盘面口径,正典**)
  · Odds API      → `closing`(收盘锚)

实测 9 个联赛共 **61** 个名字只在 closing 侧出现(`Charlotte FC` vs `Charlotte`、
`Ilves Tampere` vs `Ilves`、`FC Lahti` vs `Lahti`…)。后果:**收盘线静默叠加不
上盘面那一行** —— join 不通、CLV 少数据、EV 用不上最新的锚,而**日志全绿、没有
任何报错**。与本项目反复踩的「沉默的错误答案」同族。

## 为什么正典取 gather 侧

盘面、`TEAM_NAME_ZH` 的键、`sporttery._ZH_OVERRIDES` 的值,全部是 API-Football
口径。改 closing 去对齐 gather 只需一张表;反过来要改三处下游。

## ⚠️ 这张表怎么来的(不是猜的)

`scripts/derive_odds_name_aliases.py` 从**赛事共现**推导:同一 (联赛, 开球时刻)
上两个源写的是同一场比赛 ⇒ 主队名对主队名。两侧各 1 场的键直接对位;多场键靠
「一侧已学到」迭代钉住另一侧。一致性闸:同名指向不同目标 ⇒ 冲突,拒绝(实测 0 冲突)。

⭐ **方法自带对照组**:两侧本来就同名的 93 支球队应当映射到自己 —— 实测全部正确。
这才是敢信它推出的 54 条的理由。(2026-08-04 补到 **61 条** —— 那 7 条走的是
另一种证据「队表钉」,见文件末尾。)

⛔ **不许按模式补**。实测反例:`FC Lahti → Lahti`(去前缀)但 `Jaro → FF Jaro`
(**加**前缀);美职 10 组双拼法里 9 组「短名是正典」而 `LA Galaxy` 恰好相反。
从 N 个样本推出的命名规律,第 N+1 个就是错的 —— 与「绝不瞎猜队名」同一条红线。

⚠️ 静态表**故意的**:写入路径上做运行时推导,一次推导 bug 会把脏名字永久写进库。
静态可审、可测、可 diff;推导脚本留着当**探测器**,新分裂出现时由它报出来。
"""
from __future__ import annotations

ODDS_SOURCE_ALIASES: dict[tuple[str, str], str] = {
    ('BRA_SERIE_A', 'Atletico Mineiro'): 'Atletico-MG',   # 证据 6 场
    ('BRA_SERIE_A', 'Bragantino-SP'): 'RB Bragantino',   # 证据 5 场
    ('BRA_SERIE_A', 'Chapecoense'): 'Chapecoense-sc',   # 证据 6 场
    ('BRA_SERIE_A', 'Grêmio'): 'Gremio',   # 证据 3 场
    ('BRA_SERIE_A', 'Vasco da Gama'): 'Vasco DA Gama',   # 证据 1 场
    ('DNK_SUPERLIGA', 'AGF Aarhus'): 'Aarhus',   # 证据 2 场
    ('DNK_SUPERLIGA', 'Brondby IF'): 'Brondby',   # 证据 2 场
    ('DNK_SUPERLIGA', 'OB Odense BK'): 'Odense',   # 证据 2 场
    ('DNK_SUPERLIGA', 'Silkeborg IF'): 'Silkeborg',   # 证据 1 场
    ('DNK_SUPERLIGA', 'SonderjyskE'): 'Sonderjyske',   # 证据 2 场
    ('DNK_SUPERLIGA', 'Viborg FF'): 'Viborg',   # 证据 2 场
    ('FIN_VEIKKAUSLIIGA', 'FC Inter Turku'): 'Inter Turku',   # 证据 7 场
    ('FIN_VEIKKAUSLIIGA', 'FC Lahti'): 'Lahti',   # 证据 9 场
    ('FIN_VEIKKAUSLIIGA', 'IF Gnistan'): 'Gnistan',   # 证据 14 场
    ('FIN_VEIKKAUSLIIGA', 'IFK Mariehamn'): 'Mariehamn',   # 证据 8 场
    ('FIN_VEIKKAUSLIIGA', 'Ilves Tampere'): 'Ilves',   # 证据 12 场
    ('FIN_VEIKKAUSLIIGA', 'Jaro'): 'FF Jaro',   # 证据 8 场
    ('FIN_VEIKKAUSLIIGA', 'KuPS Kuopio'): 'KuPS',   # 证据 2 场
    ('FIN_VEIKKAUSLIIGA', 'SJK Seinäjoki'): 'SJK',   # 证据 8 场
    ('FIN_VEIKKAUSLIIGA', 'TPS Turku'): 'Turku PS',   # 证据 13 场
    ('FIN_VEIKKAUSLIIGA', 'VPS Vaasa'): 'VPS',   # 证据 5 场
    # ↓ 韩职 2 条**只有队表钉**(共现至今推不出),详见文件末尾
    ('KOR_K_LEAGUE_1', 'Jeonbuk Hyundai Motors'): 'Jeonbuk Motors',   # 队表唯一 eonbuk
    ('KOR_K_LEAGUE_1', 'Sangju Sangmu FC'): 'Gimcheon Sangmu FC',   # 队表唯一 angmu
    ('NOR_ELITESERIEN', 'Bodø/Glimt'): 'Bodo/Glimt',   # 证据 14 场
    ('NOR_ELITESERIEN', 'Fredrikstad FK'): 'Fredrikstad',   # 证据 3 场
    ('NOR_ELITESERIEN', 'HamKam'): 'Ham-Kam',   # 证据 19 场
    ('NOR_ELITESERIEN', 'IK Start'): 'Start',   # 证据 8 场
    ('NOR_ELITESERIEN', 'KFUM'): 'KFUM Oslo',   # 证据 13 场
    ('NOR_ELITESERIEN', 'SK Brann'): 'Brann',   # 证据 8 场
    ('NOR_ELITESERIEN', 'Sarpsborg FK'): 'Sarpsborg 08 FF',   # 证据 13 场
    ('NOR_ELITESERIEN', 'Viking FK'): 'Viking',   # 证据 9 场
    ('NOR_ELITESERIEN', 'Vålerenga'): 'Valerenga',   # 证据 3 场
    ('SCO_PREMIERSHIP', 'Dundee FC'): 'Dundee',   # 证据 1 场
    ('SCO_PREMIERSHIP', 'Dundee United'): 'Dundee Utd',   # 证据 1 场
    ('SCO_PREMIERSHIP', 'Falkirk F.C.'): 'Falkirk',   # 证据 1 场
    ('SCO_PREMIERSHIP', 'Hearts'): 'Heart Of Midlothian',   # 证据 1 场
    ('SCO_PREMIERSHIP', 'St Johnstone'): 'ST Johnstone',   # 证据 1 场
    ('SCO_PREMIERSHIP', 'St Mirren'): 'ST Mirren',   # 证据 1 场
    # ↓ 瑞超 5 条:共现推导与队表钉**各自独立地给出同一答案**(5/5),见文件末尾
    ('SUI_SUPER_LEAGUE', 'FC Basel'): 'FC Basel 1893',   # 共现 8 场 + 队表唯一 asel
    ('SUI_SUPER_LEAGUE', 'FC Lausanne-Sport'): 'Lausanne',   # 共现 12 场 + 队表唯一 ausanne
    ('SUI_SUPER_LEAGUE', 'FC St Gallen'): 'FC ST. Gallen',   # 共现 7 场 + 队表唯一 allen
    ('SUI_SUPER_LEAGUE', 'Grasshopper Zürich'): 'Grasshoppers',   # 共现 12 场 + 队表唯一 rasshopper
    ('SUI_SUPER_LEAGUE', 'Servette'): 'Servette FC',   # 共现 7 场 + 队表唯一 ervette
    ('SWE_ALLSVENSKAN', 'AIK'): 'AIK Stockholm',   # 证据 8 场
    ('SWE_ALLSVENSKAN', 'GAIS'): 'Gais',   # 证据 17 场
    ('SWE_ALLSVENSKAN', 'Halmstads BK'): 'Halmstad',   # 证据 19 场
    ('SWE_ALLSVENSKAN', 'Hammarby IF'): 'Hammarby FF',   # 证据 13 场
    ('SWE_ALLSVENSKAN', 'IK Sirius'): 'Sirius',   # 证据 16 场
    ('SWE_ALLSVENSKAN', 'Mjällby AIF'): 'Mjallby AIF',   # 证据 2 场
    ('SWE_ALLSVENSKAN', 'Västerås SK'): 'Vasteras SK FK',   # 证据 19 场
    ('SWE_ALLSVENSKAN', 'Örgryte IS'): 'Orgryte IS',   # 证据 8 场
    ('USA_MLS', 'Austin FC'): 'Austin',   # 证据 12 场
    ('USA_MLS', 'Charlotte FC'): 'Charlotte',   # 证据 8 场
    ('USA_MLS', 'Columbus Crew SC'): 'Columbus Crew',   # 证据 12 场
    ('USA_MLS', 'D.C. United'): 'DC United',   # 证据 17 场
    ('USA_MLS', 'Inter Miami CF'): 'Inter Miami',   # 证据 9 场
    ('USA_MLS', 'LA Galaxy'): 'Los Angeles Galaxy',   # 证据 15 场
    ('USA_MLS', 'San Diego FC'): 'San Diego',   # 证据 12 场
    ('USA_MLS', 'Seattle Sounders FC'): 'Seattle Sounders',   # 证据 12 场
    ('USA_MLS', 'St. Louis City SC'): 'St. Louis City',   # 证据 17 场
    ('USA_MLS', 'Vancouver Whitecaps FC'): 'Vancouver Whitecaps',   # 证据 18 场

    # ── 比甲(2026-08-13):Odds API 多保留 KSV/KV/SV 等法定后缀,AF 用常用名;
    # Leuven/Westerlo 反向(AF 才带前缀)。⚠️ Club Brugge 与 Cercle Brugge 同城同球场,
    # 已逐条验证四个串两两不同、赛程集合不相交。
    ('BEL_PRO_LEAGUE', 'Cercle Brugge KSV'): 'Cercle Brugge',   # 共现 2 场
    ('BEL_PRO_LEAGUE', 'Club Brugge'): 'Club Brugge KV',   # 共现 2 场
    ('BEL_PRO_LEAGUE', 'KV Kortrijk'): 'Kortrijk',   # 共现 1 场
    ('BEL_PRO_LEAGUE', 'Leuven'): 'OH Leuven',   # 共现 2 场
    ('BEL_PRO_LEAGUE', 'Lommel SK'): 'Lommel United',   # 共现 1 场
    ('BEL_PRO_LEAGUE', 'Royal Antwerp'): 'Antwerp',   # 共现 1 场
    ('BEL_PRO_LEAGUE', 'SV Zulte-Waregem'): 'Zulte Waregem',   # 共现 2 场
    ('BEL_PRO_LEAGUE', 'Sint Truiden'): 'St. Truiden',   # 共现 2 场
    ('BEL_PRO_LEAGUE', 'Union Saint-Gilloise'): 'Union St. Gilloise',   # 共现 2 场
    ('BEL_PRO_LEAGUE', 'Westerlo'): 'KVC Westerlo',   # 共现 2 场
    # ── 德乙(2026-08-13)
    ('GER_2_BUNDESLIGA', 'Hertha Berlin'): 'Hertha BSC',   # 共现 1 场
    # ── 日职(2026-08-13):大小写/连字符/词序三类差异。⚠️ Yokohama F Marinos 的
    # 变异检验证明「目标不在数据窗口里」时碰撞检测全绿 —— 靠「每条至少修好 1 键」兜住。
    ('JPN_J1', 'FC Machida Zelvia'): 'Machida Zelvia',   # 共现 2 场
    ('JPN_J1', 'Hiroshima Sanfrecce FC'): 'Sanfrecce Hiroshima',   # 共现 2 场
    ('JPN_J1', 'Kashima Antlers'): 'Kashima',   # 共现 2 场
    ('JPN_J1', 'Kyoto Purple Sanga'): 'Kyoto Sanga',   # 共现 1 场
    ('JPN_J1', 'Mito HollyHock'): 'Mito Hollyhock',   # 共现 2 场
    ('JPN_J1', 'Shimizu S Pulse'): 'Shimizu S-pulse',   # 共现 2 场
    ('JPN_J1', 'Urawa Red Diamonds'): 'Urawa',   # 共现 2 场
    ('JPN_J1', 'V-Varen Nagasaki'): 'V-varen Nagasaki',   # 共现 1 场
    ('JPN_J1', 'Yokohama F Marinos'): 'Yokohama F. Marinos',   # 共现 2 场
    # ── 荷甲(2026-08-13):closing 侧多带 FC/SC 前缀
    ('NED_EREDIVISIE', 'FC Twente Enschede'): 'Twente',   # 共现 1 场
    ('NED_EREDIVISIE', 'FC Utrecht'): 'Utrecht',   # 共现 2 场
    ('NED_EREDIVISIE', 'Go Ahead Eagles'): 'GO Ahead Eagles',   # 共现 1 场
    ('NED_EREDIVISIE', 'SC Cambuur'): 'Cambuur',   # 共现 1 场
    ('NED_EREDIVISIE', 'SC Telstar'): 'Telstar',   # 共现 2 场
    # ── 葡超(2026-08-13)。⛔ **Vitória SC → Guimaraes 已否决**:AF 在 2026-08-13
    # 把 team id 224 从 Guimaraes 改名为 Vitória SC ⇒ 映射它是把正典**回退**到
    # 已退役拼法,不是归一。同一 fixture_id 1575463 两名同源,队没错、方向错了。
    ('PRT_PRIMEIRA_LIGA', 'CF Estrela'): 'Estrela',   # 共现 2 场
    ('PRT_PRIMEIRA_LIGA', 'CS Maritimo'): 'Maritimo',   # 共现 1 场
    ('PRT_PRIMEIRA_LIGA', 'Famalicão'): 'Famalicao',   # 共现 1 场
    ('PRT_PRIMEIRA_LIGA', 'Gil Vicente'): 'GIL Vicente',   # 共现 1 场
    ('PRT_PRIMEIRA_LIGA', 'Rio Ave FC'): 'Rio Ave',   # 共现 2 场
    ('PRT_PRIMEIRA_LIGA', 'Sporting Lisbon'): 'Sporting CP',   # 共现 2 场
}

#: ⛔ 证据不足、**故意留空**的名字(探测器每次会重报)。补它们要有证据 ——
#: **不许按音译/模式填**。2026-08-04 起为空,原来那 7 条见下面的「队表钉」。
UNRESOLVED_SPLITS: tuple[tuple[str, str], ...] = ()

# ─────────────────────────────────────────────────────────────────────────────
# 第二种证据:**队表钉**(2026-08-04,韩职 2 条 + 瑞超 5 条)
#
# 用 API-Football `/teams` 的**权威当季队表**(读缓存,0 次 API 调用),
# 每条同时满足三个条件才收:
#   · 队表里对该词根**恰好一个**候选(唯一 ⇒ 不是在若干相似名里挑)
#   · 未解名**不在**队表(⇒ 它确实是外来拼法,不是并存的另一支队)
#   · 两个名字在库里**从未互相对阵**(⇒ 不是把两支真队错并成一支)
# 三条全过 7/7。
#
# ⭐ **瑞超那 5 条是双证据**:同日重跑 `derive_odds_name_aliases.py`,共现法
# 现在也能推出来(7-12 场),而且**和队表钉给出完全相同的 5 个目标名**。
# 两条互相独立的证据链对上了 —— 这比任何一条单独成立都强。
# 韩职那 2 条共现至今仍推不出(探测器把它们留在 pending),**只有队表钉**。
#
# ⚠️ 我在这条注释里写错过一次,值得留着:原文写「derive 脚本只扫了 7 个联赛,
# 韩职瑞超从来没被扫过」—— 假的。脚本是 `for lg in sorted(names)`,按**库里
# 发现的**联赛遍历。我是从「别名表里出现过 7 个联赛码」倒推出「扫描范围是 7 个」
# 的,**拿输出当范围**。同族见 [[syntactic-proxy-for-semantic-property]]:
# 断言一个机制之前,去读它/跑它,别从它的产物反推。
# (同批错的还有「FC Basel 共享 0 场」—— 那是我自己「同对手同日」的口径,
# 探测器数的是 (联赛, 开球时刻) 共现,两个数不可比。)
#
# ⚠️ 其中 2 条是**改名**不是拼法差异:Sangju Sangmu→Gimcheon(2021 迁址)、
# Jeonbuk 去掉 Hyundai(2024)。对 join 来说要的就是「同一个身份」,所以照收;
# 但记住它们是**有时间方向的** —— 2021 年前的行本来就该叫 Sangju。
#
# ⚠️ 「closing 侧孤儿 = 0」**不等于**「没有分裂了」:这个扫描是**单侧**口径,
# 只找得到「只在 closing 出现」的名字。**两侧都存在**的双拼法它看不见 ——
# 实例:WC 的 `Czechia`(10 场)与 `Czech Republic`(19 场)在 gather 侧**同时**
# 存在,那是 gather 源自己前后不一致,不归本模块管(`_alias_close` 的国家队
# 兜底已覆盖),也**没有**足够证据往这张表里塞。
# ─────────────────────────────────────────────────────────────────────────────


def canonical_league(league: str | None) -> str | None:
    """Odds API sport_key → V4 联赛码;已经是 V4 码或认不出 ⇒ 原样返回。

    ⚠️ 2026-08-01 —— **队名不是唯一分裂的东西,`league` 列自己也有两套词汇**。
    `closing_odds` 写的是 `"league": sk`,而 `sk` 上一行走的是
    `SPORT_KEYS.get(sk, sk)` 这种「宽进」写法:调用方传原始 sport_key 时它原样落库。
    实测 47 行(closing 侧 2%)的 league 是 `soccer_usa_mls` 这种,而盘面侧写
    `USA_MLS` ⇒ 本模块按 (联赛, 队名) 查表**整个静默落空**,归一变成 no-op。

    这条比队名分裂更阴:它让**修好的东西看起来还是修好的**(日志绿、测试绿),
    只是少修了 2%。放在 `canonical_team` 之前调用,别名查表才有意义。

    SPORT_KEYS 反查实测 1:1(30 条 0 个一对多),所以反查是安全的、不是猜。
    """
    if not league or not league.startswith("soccer_"):
        return league
    from nutmeg.v4.data.sources.odds_api import SPORT_KEYS
    for v4, sk in SPORT_KEYS.items():
        if sk == league:
            return v4
    return league


def canonical_team(league: str | None, name: str | None) -> str | None:
    """closing 侧拼法 → 盘面(gather)拼法。表里没有 ⇒ **原样返回,绝不猜**。

    ``league`` 传进来什么词汇都行 —— 内部先过 `canonical_league`。
    """
    if not name:
        return name
    return ODDS_SOURCE_ALIASES.get((canonical_league(league) or "", name), name)
