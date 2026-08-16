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
    # ── 德乙(2026-08-13 + 08-14 残余孤儿)
    ('GER_2_BUNDESLIGA', 'FC Energie Cottbus'): 'Energie Cottbus',   # 共现 2 场
    ('GER_2_BUNDESLIGA', 'Greuther Fürth'): 'SpVgg Greuther Fürth',   # 共现 2 场
    ('GER_2_BUNDESLIGA', 'Hertha Berlin'): 'Hertha BSC',   # 共现 1 场
    # ── 法乙(2026-08-14):**本联赛此前 0 条别名**。8 条全部两侧共现 2 槽。
    # ⚠️ 我给探测 agent 的线索只列了 2 条(Red Star / Dunkerque),它自己枚举出 8 条 ——
    # 「照着线索查」会漏 6 条。**枚举优先于线索**。
    ('FRA_LIGUE_2', 'Annecy FC'): 'Annecy',   # 共现 2 场
    ('FRA_LIGUE_2', 'Clermont'): 'Clermont Foot',   # 共现 2 场
    ('FRA_LIGUE_2', 'Pau FC'): 'PAU',   # 共现 2 场
    ('FRA_LIGUE_2', 'Red Star'): 'RED Star FC 93',   # 共现 2 场
    ('FRA_LIGUE_2', 'Rodez AF'): 'Rodez',   # 共现 2 场
    ('FRA_LIGUE_2', 'Stade Lavallois'): 'Laval',   # 共现 2 场
    ('FRA_LIGUE_2', 'Stade de Reims'): 'Reims',   # 共现 2 场
    ('FRA_LIGUE_2', 'USL Dunkerque'): 'Dunkerque',   # 共现 2 场
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
    # ⭐ FC Zwolle → PEC Zwolle 是**改名**不是拼法差异(维基 FC_Zwolle 重定向到
    # PEC_Zwolle),同 Sangju Sangmu→Gimcheon。同槽共享 6 个逐字相同的 Pinnacle
    # 三元组,同槽负对照 0 个。
    ('NED_EREDIVISIE', 'FC Zwolle'): 'PEC Zwolle',   # 共现 2 场
    ('NED_EREDIVISIE', 'Go Ahead Eagles'): 'GO Ahead Eagles',   # 共现 1 场
    ('NED_EREDIVISIE', 'SC Cambuur'): 'Cambuur',   # 共现 1 场
    ('NED_EREDIVISIE', 'SC Telstar'): 'Telstar',   # 共现 2 场
    # ── 葡超(2026-08-13)。⛔ **Vitória SC → Guimaraes 已否决**:AF 在 2026-08-13
    # 把 team id 224 从 Guimaraes 改名为 Vitória SC ⇒ 映射它是把正典**回退**到
    # 已退役拼法,不是归一。同一 fixture_id 1575463 两名同源,队没错、方向错了。
    # 🚨 `derive_odds_name_aliases.py --emit` 今天对葡超/荷甲的**唯一**建议就是那条
    # 被否决的 Vitória SC → Guimaraes,而把下面真正该补的 4 条列在「未收敛」里。
    # ⇒ **推导器的输出不能照抄**,必须逐条过证伪。
    ('PRT_PRIMEIRA_LIGA', 'Académico de Viseu'): 'Academico Viseu',   # 共现 2 场
    # ⚠️ Braga 是本批最危险的一条:AF 名册含 braga 词根的有 6 条(含 SC Braga B),
    # 且**没有一条**字面是 'Braga'。已查 SC Braga B 的实际赛程在 L457(葡四级),
    # 从不出现在葡超。另:'Braga' 这个串在 OA 缓存里同时出现在欧联(15 场)——
    # **联赛维度在这里又一次承重**。
    ('PRT_PRIMEIRA_LIGA', 'Braga'): 'SC Braga',   # 共现 2 场
    ('PRT_PRIMEIRA_LIGA', 'CF Estrela'): 'Estrela',   # 共现 2 场
    ('PRT_PRIMEIRA_LIGA', 'CS Maritimo'): 'Maritimo',   # 共现 1 场
    ('PRT_PRIMEIRA_LIGA', 'Famalicão'): 'Famalicao',   # 共现 1 场
    ('PRT_PRIMEIRA_LIGA', 'Gil Vicente'): 'GIL Vicente',   # 共现 1 场
    ('PRT_PRIMEIRA_LIGA', 'Moreirense FC'): 'Moreirense',   # 共现 2 场
    ('PRT_PRIMEIRA_LIGA', 'Rio Ave FC'): 'Rio Ave',   # 共现 2 场
    ('PRT_PRIMEIRA_LIGA', 'Sporting Lisbon'): 'Sporting CP',   # 共现 2 场
    # ── 英超(2026-08-14 预埋,首场 08-21)。⚠️ Coventry City / Leeds United **也出现在
    # EFL_CUP 的盘面**里 —— 本条只作用于 EPL 键;杯赛要另立条目(见文末 📌)。
    ('EPL', 'Coventry City'): 'Coventry',
    ('EPL', 'Leeds United'): 'Leeds',
    # ── 西甲(2026-08-14 预埋,首场 08-15)。含 4 条**纯重音**:OA 带重音、AF 不带,
    # NFKD 折叠后逐字相等且当季队表内唯一。不补这几条 = 同一行的另一条腿仍劈着 = 半修。
    ('ESP_LA_LIGA', 'Alavés'): 'Alaves',
    ('ESP_LA_LIGA', 'Athletic Bilbao'): 'Athletic Club',
    ('ESP_LA_LIGA', 'Atlético Madrid'): 'Atletico Madrid',
    ('ESP_LA_LIGA', 'Deportivo La Coruña'): 'Deportivo La Coruna',
    ('ESP_LA_LIGA', 'Elche CF'): 'Elche',
    ('ESP_LA_LIGA', 'Málaga'): 'Malaga',
    ('ESP_LA_LIGA', 'Real Racing Club de Santander'): 'Racing Santander',
    # ── 意甲(2026-08-14 预埋,首场 08-22)
    ('ITA_SERIE_A', 'Inter Milan'): 'Inter',
    # ── 法甲(2026-08-14 预埋,首场 08-21)。⚠️ Le Mans/Brest 那场是**两侧同时劈**——
    # 我的初版配对脚本对这种形态静默输出 0 条(判据是「恰好一侧对上」)。
    ('FRA_LIGUE_1', 'Brest'): 'Stade Brestois 29',
    ('FRA_LIGUE_1', 'Le Mans FC'): 'Le Mans',
    ('FRA_LIGUE_1', 'RC Lens'): 'Lens',
    ('FRA_LIGUE_1', 'Troyes'): 'Estac Troyes',
    # ── 英冠(2026-08-14 预埋,**今晚 19:00Z 首场**)。⚠️ 5 个名字里 4 个也出现在
    # EFL_CUP 盘面,本条只作用于英冠键。
    ('ENG_CHAMPIONSHIP', 'Blackburn Rovers'): 'Blackburn',
    ('ENG_CHAMPIONSHIP', 'Cardiff City'): 'Cardiff',
    ('ENG_CHAMPIONSHIP', 'Lincoln City'): 'Lincoln',
    ('ENG_CHAMPIONSHIP', 'Queens Park Rangers'): 'QPR',
    ('ENG_CHAMPIONSHIP', 'Swansea City'): 'Swansea',
    # ── 2026-08-15 首批真实 closing 落盘后暴露的 2 条(08-14 预埋时 closing 侧 0 行,
    #    这两个名字根本没出现过 ⇒ 预埋不可能覆盖到它们)。
    # ⚠️ `West Ham United`/`Wolverhampton Wanderers` 我 08-14 只建了 **EFL_CUP** 键 ——
    #    赛季一开,同样两支队出现在英冠盘面,而 `(联赛,名)` 是精确键 ⇒ 杯赛条目救不了联赛。
    #    ⭐ 教训:**同一支队每进入一个新赛事,都要单独建键**;
    #       「已经在别的联赛补过了」不构成覆盖。
    # ── 08-15 首个英冠比赛日:8 场两侧基数相等,4 场精确相同,
    #    剩 4 对**两侧同时劈** ⇒ 靠**排除法**唯一配对(3 对前缀唯一 + 第 4 对被迫)。
    # ⚠️ 「前缀关系」只是**提示不是证据**(`Sheffield Utd` 不是 `Sheffield United` 的前缀,
    #    第 4 对正是靠排除法而非前缀定的)—— 语法代理测不了语义属性。
    # 🚨 这 8 条的目标与 EFL_CUP 段落**逐字相同**,却必须重建一遍:
    #    `(联赛,名)` 是精确键,杯赛条目对联赛零作用。
    #    ⇒ 见 `test_alias_gap_when_same_name_plays_in_another_league` —— 那条护栏
    #      就是为了**开赛前**就发现这一族,而不是等首个比赛日的数据丢了才发现。
    ('ENG_CHAMPIONSHIP', 'Birmingham City'): 'Birmingham',
    ('ENG_CHAMPIONSHIP', 'Bolton Wanderers'): 'Bolton',
    ('ENG_CHAMPIONSHIP', 'Charlton Athletic'): 'Charlton',
    ('ENG_CHAMPIONSHIP', 'Derby County'): 'Derby',
    ('ENG_CHAMPIONSHIP', 'Norwich City'): 'Norwich',
    ('ENG_CHAMPIONSHIP', 'Preston North End'): 'Preston',
    ('ENG_CHAMPIONSHIP', 'Sheffield United'): 'Sheffield Utd',
    ('ENG_CHAMPIONSHIP', 'West Bromwich Albion'): 'West Brom',
    ('ENG_CHAMPIONSHIP', 'West Ham United'): 'West Ham',   # 劈开键 + 指纹 1
    # ⭐ 08-16 补:**由昨天新加的那条护栏抓出来的第一条**。
    # `Wrexham AFC` 08-14 我同样只建了 EFL_CUP 键;08-17 的英冠场次
    # (`Cardiff vs Wrexham AFC`)gather 侧跟上后,
    # `test_alias_gap_when_same_name_plays_in_another_league` 当场红。
    # ⇒ 护栏按设计工作:**数据一变得可判它就响**,不用等我去数。
    ('ENG_CHAMPIONSHIP', 'Wrexham AFC'): 'Wrexham',
    # ⚠️ 本条指纹 = 0(closing 逐次调价、gather 只有少数快照,三元组对不上),
    #    靠的是**劈开键本身**(对手 `Blackburn` 两侧精确相同)+ 一条独立的开球时刻锚:
    #    竞彩北京 08-15 03:00 = UTC 08-14T19:00,AF ±90min 内含 `Blackburn` 的恰好 1 场
    #    `L40 Championship Wolves vs Blackburn`。
    ('ENG_CHAMPIONSHIP', 'Wolverhampton Wanderers'): 'Wolves',
    # ── 土超(2026-08-15):**此前 0 条**。5 条全是**变音符**差异
    #    (OA 用 ASCII 化拼法,AF 用土耳其语正字法)。
    # ⚠️ 注意不是纯 NFKD 折叠:`Besiktas JK`→`Beşiktaş` 还掉了后缀 `JK`,
    #    `Gazişehir Gaziantep`→`Gaziantep FK` 是**改名**(俱乐部 2021 年改回 Gaziantep FK)。
    #    ⇒ 逐条都过了劈开键 + 指纹(5/5 正对照 ≥1、同槽错配 0)。
    ('TUR_SUPER_LIG', 'Basaksehir'): 'Başakşehir',
    ('TUR_SUPER_LIG', 'Besiktas JK'): 'Beşiktaş',
    ('TUR_SUPER_LIG', 'Gazişehir Gaziantep'): 'Gaziantep FK',
    ('TUR_SUPER_LIG', 'Goztepe'): 'Göztepe',
    ('TUR_SUPER_LIG', 'Kasimpasa SK'): 'Kasımpaşa',
    # ── 🩸 联赛杯(2026-08-14):**此前 0 条,而它一直在流血**。
    # closing 侧 70 个名字里 **37 个叠不上** gather 侧(交集仅 33/70)——
    # 08-08 那一轮 934 行里有整整两个开球槽的比赛全程双记。
    # ⚠️ 上面英超/英冠段落的注释早就写着「这些名字也出现在 EFL_CUP 盘面」,
    # 但**只留了注释没建条目** ⇒ 又一次「警告写在注释里、闸没写在代码里」。
    #
    # 证据分两类,**16 条靠指纹的那批各自带了负对照**:
    #   · 21 条 = 跨源劈开键(同槽恰好一侧对上,另一侧即待补)
    #   · 16 条 = 同槽**两侧同时劈**,淘汰法够不着,靠共享 Pinnacle 三元组定案。
    #     ⭐ 负对照 8/8 通过:正对照 1–3 个共享三元组,而同槽全部 19 个错配一律 **0** 个
    #     ⇒ 该判据既不假绿也不假红。⛔ 只有共享数 >0 且 argmax 唯一才收。
    # ⚠️ 'Wimbledon' → 'AFC Wimbledon':历史上有两支温布尔登(老温布尔登已迁为
    #    MK Dons),已查全库仅存 AFC Wimbledon 一支,无撞车。
    # ⚠️ 'Sheffield United' → 'Sheffield Utd':全库同时存在 Sheffield Wednesday,
    #    两个串互不为前缀/子串,无歧义。
    ('EFL_CUP', 'Accrington Stanley'): 'Accrington ST',        # 指纹 3
    ('EFL_CUP', 'Birmingham City'): 'Birmingham',              # 指纹 2
    ('EFL_CUP', 'Blackburn Rovers'): 'Blackburn',              # 劈开键
    ('EFL_CUP', 'Bolton Wanderers'): 'Bolton',                 # 劈开键
    ('EFL_CUP', 'Bradford City'): 'Bradford',                  # 劈开键
    ('EFL_CUP', 'Bromley FC'): 'Bromley',                      # 劈开键
    ('EFL_CUP', 'Cardiff City'): 'Cardiff',                    # 劈开键
    ('EFL_CUP', 'Charlton Athletic'): 'Charlton',              # 指纹 1
    ('EFL_CUP', 'Cheltenham Town'): 'Cheltenham',              # 指纹 1
    ('EFL_CUP', 'Chesterfield FC'): 'Chesterfield',            # 劈开键
    ('EFL_CUP', 'Colchester United'): 'Colchester',            # 劈开键
    ('EFL_CUP', 'Crewe Alexandra'): 'Crewe',                   # 指纹 3
    ('EFL_CUP', 'Derby County'): 'Derby',                      # 指纹 1
    ('EFL_CUP', 'Doncaster Rovers'): 'Doncaster',              # 指纹 3
    ('EFL_CUP', 'Grimsby Town'): 'Grimsby',                    # 劈开键
    ('EFL_CUP', 'Huddersfield Town'): 'Huddersfield',          # 指纹 3
    ('EFL_CUP', 'Leicester City'): 'Leicester',                # 指纹 1
    ('EFL_CUP', 'Lincoln City'): 'Lincoln',                    # 指纹 1
    ('EFL_CUP', 'Northampton Town'): 'Northampton',            # 指纹 1
    ('EFL_CUP', 'Norwich City'): 'Norwich',                    # 劈开键
    ('EFL_CUP', 'Oldham Athletic'): 'Oldham',                  # 劈开键
    ('EFL_CUP', 'Peterborough United'): 'Peterborough',        # 劈开键
    ('EFL_CUP', 'Plymouth Argyle'): 'Plymouth',                # 劈开键
    ('EFL_CUP', 'Preston North End'): 'Preston',               # 指纹 3
    ('EFL_CUP', 'Queens Park Rangers'): 'QPR',                 # 劈开键
    ('EFL_CUP', 'Rotherham United'): 'Rotherham',              # 指纹 3
    ('EFL_CUP', 'Sheffield United'): 'Sheffield Utd',          # 劈开键
    ('EFL_CUP', 'Shrewsbury Town'): 'Shrewsbury',              # 劈开键
    ('EFL_CUP', 'Stockport County FC'): 'Stockport County',    # 指纹 3
    ('EFL_CUP', 'Swansea City'): 'Swansea',                    # 指纹 2
    ('EFL_CUP', 'West Bromwich Albion'): 'West Brom',          # 指纹 3
    ('EFL_CUP', 'West Ham United'): 'West Ham',                # 劈开键
    ('EFL_CUP', 'Wigan Athletic'): 'Wigan',                    # 劈开键
    ('EFL_CUP', 'Wimbledon'): 'AFC Wimbledon',                 # 劈开键
    ('EFL_CUP', 'Wolverhampton Wanderers'): 'Wolves',          # 劈开键
    ('EFL_CUP', 'Wrexham AFC'): 'Wrexham',                     # 劈开键
    ('EFL_CUP', 'Wycombe Wanderers'): 'Wycombe',               # 劈开键
    # ── 西乙(2026-08-14 预埋,首场今晚 18:30Z)。🚨 本联赛三件事:
    # ① `Celta Vigo` → `Celta de Vigo II`:OA 把**塞尔塔 B 队**写成一队的简称。
    #    一队在西甲(AF league 140)、B 队在西乙(141),两个 league key 天然隔离 ——
    #    **(联赛,名) 的联赛维度在这里是承重的,不是装饰**。见 test_celta_league_isolation。
    # ② `Girona FC`:一队**自己降级**到西乙(AF 547 轨迹 140→141),不是 B 队。
    # ③ 含 4 条纯重音(Almería/Córdoba/Leganés/Sporting Gijón)——
    #    不补则 11 条别名只修好 7/11 场。
    ('ESP_SEGUNDA_DIVISION', 'Almería'): 'Almeria',
    ('ESP_SEGUNDA_DIVISION', 'Andorra CF'): 'FC Andorra',
    ('ESP_SEGUNDA_DIVISION', 'Burgos CF'): 'Burgos',
    ('ESP_SEGUNDA_DIVISION', 'CD Castellón'): 'Castellón',
    ('ESP_SEGUNDA_DIVISION', 'CD Eldense'): 'Eldense',
    ('ESP_SEGUNDA_DIVISION', 'Celta Vigo'): 'Celta de Vigo II',
    ('ESP_SEGUNDA_DIVISION', 'Cádiz CF'): 'Cadiz',
    ('ESP_SEGUNDA_DIVISION', 'Córdoba'): 'Cordoba',
    ('ESP_SEGUNDA_DIVISION', 'Girona FC'): 'Girona',
    ('ESP_SEGUNDA_DIVISION', 'Leganés'): 'Leganes',
    ('ESP_SEGUNDA_DIVISION', 'Real Sociedad B'): 'Real Sociedad II',
    ('ESP_SEGUNDA_DIVISION', 'Real Valladolid CF'): 'Valladolid',
    ('ESP_SEGUNDA_DIVISION', 'SD Eibar'): 'Eibar',
    ('ESP_SEGUNDA_DIVISION', 'Sabadell FC'): 'Sabadell',
    ('ESP_SEGUNDA_DIVISION', 'Sporting Gijón'): 'Sporting Gijon',
    # ── 解放者杯(2026-08-14):OA 带巴西州后缀(-RJ/-SP),AF 不带。
    # 负对照:同槽全部错配一律 0 个共享三元组。
    ('COPA_LIBERTADORES', 'Corinthians-SP'): 'Corinthians',   # 共现 2 场
    ('COPA_LIBERTADORES', 'Flamengo-RJ'): 'Flamengo',   # 共现 1 场
    ('COPA_LIBERTADORES', 'LDU Quito'): 'LDU de Quito',   # 共现 2 场
    # ── 沙特联(2026-08-14):一条纯大小写、一条纯连字符。
    # ⚠️ 已专查利雅得族:全库含 'Riyadh' 词根的**只有这两个串**
    # (`利雅得青年`/Al Shabab 那类不含该词根)⇒ 不构成撞车。
    ('SAU_PRO_LEAGUE', 'Al-Riyadh'): 'Al Riyadh',   # 共现 1 场
    ('SAU_PRO_LEAGUE', 'Neom'): 'NEOM',   # 共现 2 场
    # ── 意乙(2026-08-14 预埋,首场 08-22)
    ('ITA_SERIE_B', 'Cesena FC'): 'Cesena',
    ('ITA_SERIE_B', 'Südtirol'): 'Sudtirol',
    ('ITA_SERIE_B', 'US Catanzaro 1929'): 'Catanzaro',
    ('ITA_SERIE_B', 'Vicenza'): 'Vicenza Virtus',
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
