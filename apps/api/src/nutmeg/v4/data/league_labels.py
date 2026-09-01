"""Canonical league labels for cross-writer grouping (体检 2026-07-02).

``jingcai_sp`` has TWO writers with different league vocabularies: the
sporttery capture stores 竞彩 Chinese abbreviations (英超/芬超/世界杯…) while
the dashboard 记一笔 path (source=market_mode) stores V4 EN league codes
(EPL/FIN_VEIKKAUSLIIGA/WC…). Grouping by the RAW string therefore splits one
league into two groups — it dilutes per-league N and adds a spurious member
to the CLV-gate BHY-FDR family (measured 2026-07-02: 芬超 40 rows +
FIN_VEIKKAUSLIIGA 8 rows were ONE league in two gate groups).

Fix at the shared READER (the same altitude rule as ``national_match_key``:
repair the join/grouping layer once, not each producer). Canonical form = the
竞彩 Chinese abbreviation — dominant in captured rows and what the ledger
prints. Unknown labels pass through unchanged (fail-open: never lose a group,
a NEW synonym shows up as its own group and is added here when observed —
pre-read label audit in docs/autumn_prereg_analysis_plan.md §8).
"""
from __future__ import annotations

# V4 EN league code → 竞彩 Chinese abbrev. The first 13 are the production
# artifact's training universe (team_state.json union of data/v4_model +
# data/v4_model_cat) — also the pre-registered confirmatory family
# (docs/autumn_prereg_analysis_plan.md §2).
_EN_TO_CN: dict[str, str] = {
    "EPL": "英超",
    "ENG_CHAMPIONSHIP": "英冠",
    "ESP_LA_LIGA": "西甲",
    "ESP_SEGUNDA_DIVISION": "西乙",
    "GER_BUNDESLIGA": "德甲",
    "GER_2_BUNDESLIGA": "德乙",
    "ITA_SERIE_A": "意甲",
    "ITA_SERIE_B": "意乙",
    "FRA_LIGUE_1": "法甲",
    "FRA_LIGUE_2": "法乙",
    "NED_EREDIVISIE": "荷甲",
    "PRT_PRIMEIRA_LIGA": "葡超",
    # ⭐ 2026-08-05 补漏。本表上面那句注释说自己取自「v4_model ∪ v4_model_cat 的
    # team_state」—— 那个并集是 **14** 个(生产 artifact v4_model_cat 有 14,含
    # BEL_PRO_LEAGUE;旧 lgb 的 v4_model 只有 13),而表里一直只有 13。
    # 后果**不是**少一行文案:中文轨 `classify_league('比甲')` 落到 `unknown`
    # ⇒ `is_domestic_club_league` 判 False ⇒ 比甲的 cron 行(占 86% 的中文轨)
    # 整个掉出 δ 的 P3 预注册计数 —— 正是本文件 `classify_league` docstring 里
    # 拿丹超举的那个「活例」,只是活例本身就在表里躺着没人发现。
    # 中文缩写不是猜的:仓库内两处**独立**映射都写 比甲(dashboard 的联赛字典 +
    # team_name_zh 的「比甲 BEL_PRO_LEAGUE (Belgian Pro League) — 16 teams」)。
    # ⚠️ 竞彩(sporttery)自己写什么标签**尚未观测到**(比甲休赛期,库里 0 行),
    # 所以只补 EN→CN,**不编**中文同义词。真标签冒出来时 `check_league_labels`
    # 会把它报成 unknown/劈开,那时照证据补进 `_CN_SYNONYM`。
    "BEL_PRO_LEAGUE": "比甲",
    "JPN_J1": "日职",
    # 🚨 2026-08-17 补 —— **它一直缺着**,而缺的后果不是「少个显示名」:
    # `DOMESTIC_LEAGUES_CN` 是从 `_EN_TO_CN.values()` **推导**出来的 ⇒ 中文轨的
    # `日乙` 落进 `unknown` ⇒ `is_domestic_club_league("日乙")` = False,
    # 而 `is_domestic_club_league("JPN_J2")` = True(EN 轨走竞赛注册表,判 league)。
    # **同一个联赛按写法落进不同层**,校准报表把日乙的行归进「大赛」。
    # 与 docstring 里那个 丹超 活例**同族**,只是这个有活数据(库里 8 行)。
    # 证据(不照名字猜):这 8 行的队伍是 Omiya Ardija / Albirex Niigata /
    # Montedio Yamagata / Tochigi City / Tokushima Vortis / Sagan Tosu /
    # Blaublitz Akita / Kataller Toyama —— **全是 J2 俱乐部**。
    "JPN_J2": "日乙",
    # non-trained labels OBSERVED in jingcai_sp (exploratory-only leagues)
    "WC": "世界杯",
    "FIN_VEIKKAUSLIIGA": "芬超",
    "SWE_ALLSVENSKAN": "瑞超",
    "KOR_K_LEAGUE_1": "韩职",   # sporttery 缩写 = 韩职 (体检 2026-07-03)
    # 2026-07-25 — 表落后于现实的 5 对。前 3 对在 jingcai_sp 里**实测撞上了**
    # (两种标签同时存在 = 同一联赛被劈成两组,正是本模块开头描述的那个病):
    "NOR_ELITESERIEN": "挪超",   # 挪超 Tromso/KFUM/Rosenborg ∪ NOR_… Molde/Viking
    "UCL": "欧冠",               # 欧冠 KI Klaksvik/Omonia ∪ UCL Kairat/The New Saints
    "UEL": "欧罗巴",             # ⭐ 最硬证据:两边**同一批队**(Vojvodina、CSKA Sofia)
    # 后 2 对是**防御性**补:BRA_SERIE_A / USA_MLS 目前在 jingcai_sp 里尚未出现
    # (这两个联赛还没被手填过),但 market_mode 一写就是 EN 代码 —— 队伍池已核实
    # (巴甲 Botafogo/Vitoria/Bahia;美职 Chicago Fire/St. Louis City/Seattle)。
    "BRA_SERIE_A": "巴甲",
    "USA_MLS": "美职",
    # 补(2026-08-05 owner)。中文写法**实证**自 `crown_close_history.league_cn`:
    # 「荷乙」105 行、「英联赛杯」23 行 —— 不是照着联赛全名意译的。
    "NED_EERSTE_DIVISIE": "荷乙",
    "EFL_CUP": "英联赛杯",
    # 补(2026-08-09 owner)。中文写法**实证**自 `jingcai_odds_history.league_cn`
    # —— 直接 SELECT DISTINCT 出来的,三个联赛各只有一种写法:
    # 「解放者杯」(league_id=49, 124 场)、「欧超杯」(71, 2 场)、「沙职」(2068446, 154 场)。
    # ⭐ 不是照联赛全名意译的(意译会得到「南美解放者杯」「欧洲超级杯」「沙特职业联赛」,
    #    三个都对不上)—— 同「绝不照英文猜译名」那条红线的联赛版。
    "COPA_LIBERTADORES": "解放者杯",
    "UEFA_SUPER_CUP": "欧超杯",
    "SAU_PRO_LEAGUE": "沙职",
    # 补(2026-08-16)。中文写法**双源实证**,不是意译:
    #   · 竞彩实抓 `leagueAbbName` = 「英社区盾」(全称是「英格兰社区盾杯」)
    #   · `jingcai_odds_history.league_cn` 已有 **66 行**「英社区盾」(往年同赛事)
    # ⭐ 取**缩写**而非全称 —— 同 英联赛杯/解放者杯/欧超杯/沙职 的既有惯例;
    #   意译会得到「英格兰社区盾杯」,和两个源都对不上。
    "COMMUNITY_SHIELD": "英社区盾",
    # 补(2026-08-18)。中文写法**实证**自竞彩 `jingcai_sp.league`(直接抓到「韩国杯」),
    # 不是意译(意译会得「韩国足总杯」,对不上)。AF id=294 已 live 核 + 2026-08-19
    # FC Anyang vs Jeju United(Round of 16)钉死。
    # ⭐ 杯赛 **≠** 韩职(K联赛,KOR_K_LEAGUE_1):Anyang/Jeju 虽是 K1 俱乐部,但这是**独立
    #   赛事**,映射到「韩职」= 静默污染分组(同「绝不猜」红线的反例)。
    "KOR_FA_CUP": "韩国杯",
    # 补(2026-09-01)。中文写法**三源实证**,不是意译(意译会得「日本联赛杯」全称):
    #   · `jingcai_odds_history.league_cn` 「日联赛杯」123 场(2021-2025)
    #   · `crown_close_history.league_cn`  「日联赛杯」27 场
    #   · `jingcai_sp.league`              「日联赛杯」2 行(即 2026-09-02 那场)
    "JPN_LEAGUE_CUP": "日联赛杯",
    # 天皇杯(2026-09-01)。⚠️ 两个源写法不同,都实证过:
    #   · `jingcai_odds_history.league_cn` = 「日天皇杯」66 场 ← 竞彩口径 = 规范形
    #   · `crown_close_history.league_cn`  = 「天皇杯」 7 场  ← 进 _CN_SYNONYM
    "JPN_EMPEROR_CUP": "日天皇杯",
}

# Chinese synonyms (full names / variants) → the same canonical abbrev.
# Only VERIFIED-or-defensive entries; anything else passes through fail-open.
_CN_SYNONYM: dict[str, str] = {
    "瑞典超级联赛": "瑞超",   # observed in jingcai_vote.league_cn 2026-07-02
    "日职联": "日职",
    "日本联赛杯": "日联赛杯",   # jingcai_vote.league_cn 实测 2 行用全称(2026-09-01)
    "天皇杯": "日天皇杯",        # crown_close_history.league_cn 实测 7 场用短名(2026-09-01)          # common variant of the J1 abbrev
}

#: The confirmatory universe (canonical CN form) — the production artifact's
#: training face. Pre-registered: only these leagues can CONFIRM.
#: 2026-08-05:13 → 14,补 比甲。理由同上面 `_EN_TO_CN` 里那段 —— 生产 artifact
#: 的 team_state 一直有 BEL_PRO_LEAGUE,是本表当初漏了,不是预注册故意排除它。
#: ⚠️ 日职**留着**:JPN_J1 在两个 artifact 的 team_state 里都在 ⇒ 它属于**训练**
#: 面。服务侧 V12 W7 把 J1 移出模型盘走市场模式(OOD),那是**服务集**的事;
#: 两个集合本来就不必相等,别拿服务集去删训练集(我差点这么干)。
TRAINED_LEAGUES_CN: frozenset[str] = frozenset({
    "英超", "英冠", "西甲", "西乙", "德甲", "德乙",
    "意甲", "意乙", "法甲", "法乙", "荷甲", "葡超", "比甲", "日职",
})

# ── 「国内俱乐部联赛」谓词(prereg v1.8 §2 P3,2026-07-27)────────────────────
# 为什么要在这里加:δ₋₂ 的 P3 检验必须**只用俱乐部联赛计数** —— δ 是在国内联赛
# (football-data 各国 CSV + 皇冠)上拟合的,大赛不在那个人口里。实测教训:
# 2026-07 捕到的 15 场 −2 里 **10 场是世界杯**,而世界杯小组赛的实力悬殊场次
# 血洗率异常(5-0/5-0/4-0),拿它们验 δ₋₂ 等于在另一个人口上验。
#
# ⚠️ **不能裸用 `competitions.competition_type_of`** —— 它只认 EN code。本表的
# league 列是**双轨**的(cron 写中文占 86%),中文标签进去会对**所有东西**返回
# "league",世界杯/欧冠/欧罗巴全部被静默算成联赛。我差点就这么写了。
#
# 设计:**allowlist + fail-CLOSED**。分组用的 `canonical_league` 是 fail-open
# (不丢组),但**计数一个预注册人口时 fail-open 是错的** —— 一个没见过的标签
# 宁可不计,也不能默认当联赛混进去。新联赛出现时它会掉出计数,这是**响亮的
# 少数**(N 涨得比预期慢),不是静默污染。
_NON_DOMESTIC_CN: frozenset[str] = frozenset({
    "世界杯", "欧洲杯", "美洲杯", "亚洲杯", "非洲杯", "世预赛", "欧国联",  # 国家队
    "欧冠", "欧罗巴", "欧协联",                                           # 洲际俱乐部杯
    # ⭐ 第三类:**国内**俱乐部杯赛。本集合原来的注释只写了上面两类,而 P3 要的是
    # 「国内俱乐部**联赛**」—— 国内杯赛既不是国家队也不是洲际杯,却同样不在
    # δ 的拟合人口里(δ 拟合在 football-data 各国**联赛** CSV 上)。
    # 2026-08-05:新上线的 `check_league_labels` 探针**第一天**就把 巴西杯 报成
    # unknown(14 行,08-02~08-06)—— 证据:对手是 Santos/Gremio/Mirassol 等俱乐部,
    # 且 巴甲 在同一张表里另有标签;结构对应物 `COPA_DEL_REY` 在竞赛注册表里正是
    # `club_cup`。EN 轨走 `CUP_COMPETITIONS` 本来就排除它,这里是把中文轨对齐。
    "巴西杯",
    # 同类第二条(2026-08-05):英联赛杯也是**国内俱乐部杯赛** ⇒ 不进 δ 的拟合
    # 人口。它在 `CUP_COMPETITIONS` 里注册为 `club_cup`,EN 轨本来就排除,这里
    # 把中文轨对齐。⚠️ 同批注册的「荷乙」**不加** —— 它是国内俱乐部**联赛**,
    # 正是 P3 该计数的那种人口(虽然模型没训练它,但训练与否不是本表的判据)。
    "英联赛杯",
    # 同类第三/四条(2026-08-09):解放者杯=南美洲际杯赛、欧超杯=欧洲洲际杯赛,
    # 两者 EN 轨都在 `CUP_COMPETITIONS` 里本来就排除,这里把中文轨对齐。
    # ⚠️ 同批注册的「沙职」**不加** —— 国内俱乐部联赛,与荷乙同理。
    "解放者杯",
    "欧超杯",
    # 同类第五条(2026-08-16):社区盾是**国内俱乐部杯赛**(英超冠军 vs 足总杯冠军)
    # ⇒ 不进 δ 的拟合人口(δ 拟合在各国**联赛** CSV 上)。
    # 它在 `CUP_COMPETITIONS` 里注册为 `club_cup`,EN 轨本来就排除,这里对齐中文轨。
    "英社区盾",
    # 同类第六条(2026-08-17):亚冠精英 = AFC Champions League Elite,**洲际**俱乐部
    # 杯赛 ⇒ 不进 δ 的拟合人口(δ 拟合在各国**联赛** CSV 上),与 解放者杯/欧超杯 同理。
    # 证据:库里那 2 行是 `Gangwon FC`(韩)vs `Gamba Osaka`(日)—— **跨国俱乐部对阵**,
    # 不可能是任何一国的国内联赛。
    # ⚠️ 它没有对应的 EN 键(我们不采集这项赛事),所以只在中文轨登记;
    #    若将来 EN 轨也出现,`CUP_COMPETITIONS` 要同步注册。
    "亚冠精英",
    # 同类第七条(2026-08-18):韩国杯 = 韩国足总杯(KOR_FA_CUP),**国内俱乐部杯赛**
    # ⇒ 不进 δ 的拟合人口(δ 拟合在各国**联赛** CSV 上)。它在 `CUP_COMPETITIONS` 里
    # 注册为 club_cup(AF id=294),EN 轨本来就排除,这里对齐中文轨。
    # ⚠️ 同批的 KOR_K_LEAGUE_1(韩职)**不加** —— 它是国内俱乐部**联赛**,正是 P3 该计的人口。
    # ⚠️ 只加 `_EN_TO_CN` 不加这里 = 杯赛被 classify_league 算成 'domestic' ⇒ 悄悄混入
    #    P3 联赛人口(2026-08-18 注册时实测到,幸亏对照既有杯赛才发现)。
    "韩国杯",
    # 同类第八条(2026-09-01):日联赛杯 = J联赛杯(JPN_LEAGUE_CUP),**国内俱乐部杯赛**。
    # 🚨 这一条是本次注册里**唯一会静默污染数据**的:`DOMESTIC_LEAGUES_CN` 是从
    #   `_EN_TO_CN.values()` **减去本集合**推导的 ⇒ 只补 _EN_TO_CN 不补这里,
    #   `classify_league("日联赛杯")` 会返回 `domestic`,一个跨 J1/J2/J3 的淘汰杯
    #   就**悄悄混进 δ 校准的国内联赛人口**。数字会动,什么都不报错。
    "日联赛杯",
    "日天皇杯",     # 同上:国内俱乐部杯赛,**不是**国内联赛(δ 人口)
    # 同类第八/九条(2026-08-24)—— 起因:桌面推送「捕获表停长,某 cron 可能死了」,
    # 查下来**没有 cron 死**,是 `data_freshness` 的 label_alarms 同乘那条非零退出,
    # 而报的是这两个「标签表不认识」。
    #
    # 德国杯 = DFB_POKAL,**国内俱乐部杯赛** ⇒ 不进 δ 的拟合人口(δ 拟合在各国**联赛** CSV 上)。
    #   证据(不是意译):`jingcai_sp` 的「德国杯」行与 `odds_snapshots` 的 `DFB_POKAL`
    #   **同场 join 44 行**(2026-08-23);`CUP_COMPETITIONS` 里 DFB_POKAL 正是 `club_cup`,
    #   EN 轨本来就排除,这里对齐中文轨。
    "德国杯",
    # 德超杯 = 德国超级杯(DFL-Supercup),**国内俱乐部杯赛** ⇒ 同上排除。
    #   证据:库里只有一场 —— `Borussia Dortmund vs Bayern München` 2026-08-22;
    #   AF leagues 缓存里德国男足只有**一个**超级杯条目 `id=529 'Super Cup' (Germany, Cup)`,
    #   其余候选全排除(1137 Supercup der Frauen 女足 / 715 DFB Junioren Pokal 青年 /
    #   947 DFB Pokal - Women 女足)。结构对应物:`UEFA_SUPER_CUP` 在注册表里正是 `club_cup`。
    # ⚠️ 它**没有**对应的 EN 键(我们不采集这项赛事)⇒ 只在中文轨登记,同「亚冠精英」;
    #    若将来 EN 轨也出现,`CUP_COMPETITIONS` 要同步注册。
    # ⛔ 特意**没有**发明一个 `GER_SUPER_CUP` 塞进 `_EN_TO_CN` —— 判「认识」走的是本集合
    #    (`classify_league` 中文轨),塞 `_EN_TO_CN` 既不生效又会假装我们服务这项赛事。
    "德超杯",
})

#: 已知的国内俱乐部联赛(canonical CN)—— P3 计数的合法人口(中文轨)。
DOMESTIC_LEAGUES_CN: frozenset[str] = frozenset(
    set(_EN_TO_CN.values()) | set(_CN_SYNONYM.values())
) - _NON_DOMESTIC_CN


def classify_league(label: str | None) -> str:
    """``'domestic'`` | ``'excluded'`` | ``'unknown'`` —— P3 计数的三态判定。

    **三态而非布尔**,因为两种「不计入」的后果完全不同:
      · ``excluded`` = 已知的大赛/洲际杯 → 本来就该排除,静默即可
      · ``unknown``  = 没见过的标签 → **必须被报出来**。丹超(DNK_SUPERLIGA)
        就是活例:它是国内联赛、竞彩也上架,但 ``_EN_TO_CN`` 没收录中文缩写
        ⇒ cron 写的中文行会掉出计数。悄悄少算 N 和悄悄混入错人口一样坏。

    双轨:EN code 走 V4 竞赛注册表(``CUP_COMPETITIONS`` 列全了杯赛/国家队);
    中文走 allowlist —— ⚠️ **中文绝不能裸用 `competition_type_of`**,它只认 EN,
    中文进去会对**所有东西**返回 ``"league"``,世界杯/欧冠会被算成联赛(实测)。
    """
    from nutmeg.v4.data.competitions import CUP_COMPETITIONS, competition_type_of

    s = str(label or "").strip()
    if not s:
        return "unknown"
    if s.isascii() and s.isupper():                 # EN code 轨
        if s in CUP_COMPETITIONS:
            return "excluded"
        return "domestic" if competition_type_of(s) == "league" else "excluded"
    cn = canonical_league(s)                        # 中文轨
    if cn in _NON_DOMESTIC_CN:
        return "excluded"
    return "domestic" if cn in DOMESTIC_LEAGUES_CN else "unknown"


def is_domestic_club_league(label: str | None) -> bool:
    """P3 计数是否计入该标签。``unknown`` 一律**不计入**(fail-closed)——
    与 `canonical_league` 的 fail-open **故意相反**:那个给分组用(丢组比多组坏),
    这个给**预注册计数**用(混入错人口比少算坏)。用 `classify_league` 看清原因。
    """
    return classify_league(label) == "domestic"


def canonical_league(label: str | None) -> str:
    """RAW league label (any writer's vocabulary) → canonical CN abbrev.

    Fail-open: an unmapped label returns itself (stripped) so no group is ever
    silently dropped — a new synonym surfaces as its own group and gets added
    to the tables above when observed."""
    if not label or not str(label).strip():
        return "(未标联赛)"
    s = str(label).strip()
    return _EN_TO_CN.get(s) or _CN_SYNONYM.get(s) or s


def league_filter_variants(labels) -> set[str]:
    """把一组联赛(任一轨的写法)展开成**所有等价的 RAW 写法**,给 ``WHERE league
    IN (…)`` 用。

    ⭐ 为什么需要它:``canonical_league`` 只在**行拿到手之后**才能用,而
    ``WHERE`` 是在拿到手之前跑的。2026-08-05 我自己踩了这个坑 —— 拿 13 个 V4
    代码查 ``jingcai_sp`` 得到 0 行,而 cron 写的是中文,86% 的行根本没被问到。
    **0 行长得和「没有数据」一模一样**,我差一点就据此说「管道坏了」。
    这是本项目反复出现的「分不出『没有』和『没去看』」。

    ⚠️ 回填**不能**替代它:回填只是把两轨并成一轨,拿**另一轨**的写法去查照样 0 行。

    传字符串会被当成可迭代的字符序列 —— 那正是 [[health-check-guardrails]] 里
    「``leagues="all"`` 退化成子串判断」那个洞,所以这里直接拒绝。
    """
    if isinstance(labels, str):
        raise TypeError("league_filter_variants 要一组标签,不是单个字符串 "
                        "(字符串会退化成逐字符迭代)")
    want = {canonical_league(x) for x in labels}
    out: set[str] = set()
    for raw, cn in list(_EN_TO_CN.items()) + list(_CN_SYNONYM.items()):
        if cn in want:
            out.add(raw)
    # 规范形自己也是一种合法写法(cron 就直接写它)
    out |= want
    return out


def audit_label_tracks(labels) -> dict[str, list]:
    """观测到的一组 RAW 标签 → ``{"split": [...], "unknown": [...]}``。

    ``split``   同一个规范联赛出现了 **>1 种写法**(= 本模块开头描述的那个病:
                一个联赛被劈成两组,per-league N 被稀释)。
    ``unknown`` ``classify_league`` 判不出来的标签。``classify_league`` 的
                docstring 早就写着 unknown「**必须被报出来**」,但在 2026-08-05
                之前**没有任何地方调它来报** —— 设计好的警报从来没接线,
                同「检查的前提没人检查」那一族。

    纯函数,不碰 DB;调用方(``data_freshness.check_league_labels``)负责取标签。
    """
    if isinstance(labels, str):
        raise TypeError("audit_label_tracks 要一组标签,不是单个字符串")
    by_canon: dict[str, set[str]] = {}
    unknown: set[str] = set()
    for raw in labels:
        s = str(raw or "").strip()
        if not s:
            continue
        by_canon.setdefault(canonical_league(s), set()).add(s)
        if classify_league(s) == "unknown":
            unknown.add(s)
    split = sorted(
        (cn, sorted(v)) for cn, v in by_canon.items() if len(v) > 1
    )
    return {"split": split, "unknown": sorted(unknown)}
