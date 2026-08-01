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
这才是敢信它推出的 54 条的理由。

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
}

#: ⛔ 共现证据不足、**故意留空**的名字(探测器每次会重报)。补它们要等更多共现
#: 数据,或人工用赛事身份逐条核实 —— **不许按音译/模式填**。
UNRESOLVED_SPLITS: tuple[tuple[str, str], ...] = (
    ("KOR_K_LEAGUE_1", "Jeonbuk Hyundai Motors"),
    ("KOR_K_LEAGUE_1", "Sangju Sangmu FC"),
    ("SUI_SUPER_LEAGUE", "FC Basel"),
    ("SUI_SUPER_LEAGUE", "FC Lausanne-Sport"),
    ("SUI_SUPER_LEAGUE", "FC St Gallen"),
    ("SUI_SUPER_LEAGUE", "Grasshopper Zürich"),
    ("SUI_SUPER_LEAGUE", "Servette"),
)


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
