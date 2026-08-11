"""V11 P1-FE#2 + P1-FE#7 — Chinese team names for all 14 trained leagues.

Static dictionary mapping V4 canonical team names (`to_v4_canonical_*`
output) to their Chinese names. Covers ~280 teams across:

P1-FE#2 (top-5 European, shipped first):
- 英超 EPL (English Premier League) — 20 teams
- 西甲 ESP_LA_LIGA (Spanish La Liga) — 20 teams
- 意甲 ITA_SERIE_A (Italian Serie A) — 20 teams
- 德甲 GER_BUNDESLIGA (German Bundesliga) — 18 teams
- 法甲 FRA_LIGUE_1 (French Ligue 1) — 18 teams

P1-FE#7 — full coverage of the other 9 trained leagues:
- 英冠 ENG_CHAMPIONSHIP (English Championship) — 24 teams
- 西乙 ESP_SEGUNDA_DIVISION (Spanish Segunda) — 22 teams
- 意乙 ITA_SERIE_B (Italian Serie B) — 20 teams
- 德乙 GER_2_BUNDESLIGA (German 2.Bundesliga) — 18 teams
- 法乙 FRA_LIGUE_2 (French Ligue 2) — 18 teams
- 荷甲 NED_EREDIVISIE (Dutch Eredivisie) — 18 teams
- 葡超 PRT_PRIMEIRA_LIGA (Portuguese Primeira Liga) — 18 teams
- 比甲 BEL_PRO_LEAGUE (Belgian Pro League) — 16 teams
- 日职联 JPN_J1 (Japanese J1) — 20 teams

The frontend uses ``lookup_zh()`` (or its JS equivalent fetched from
``/api/v4/team-name-zh``) to render Chinese names when ``locale == 'zh'``.
Teams outside these 14 leagues fall through unchanged (English shown).

Naming conventions:
- Use mainland Chinese conventions (e.g. 曼联 not 曼徹斯特聯; 拜仁 not 拜仁慕尼黑 in cards)
- Compact display: prefer the short form people actually use
- For ambiguous abbreviations (e.g. 莱斯特/莱切) we keep them
  disambiguated where the canonical name does so
"""
from __future__ import annotations

from typing import Dict


# ============ Premier League (英超) ===================================
_EPL: Dict[str, str] = {
    "Arsenal": "阿森纳",
    "Aston Villa": "阿斯顿维拉",
    "Bournemouth": "伯恩茅斯",
    "Brentford": "布伦特福德",
    "Brighton": "布莱顿",
    "Chelsea": "切尔西",
    "Crystal Palace": "水晶宫",
    "Everton": "埃弗顿",
    "Fulham": "富勒姆",
    "Ipswich": "伊普斯维奇",
    "Leicester": "莱斯特城",
    "Liverpool": "利物浦",
    "Man City": "曼城",
    "Man United": "曼联",
    "Newcastle": "纽卡斯尔",
    "Nottingham Forest": "诺丁汉森林",
    "Southampton": "南安普顿",
    "Tottenham": "热刺",
    "West Ham": "西汉姆",
    "Wolves": "狼队",
    # Common variant spellings that survive canonical normalization
    "Manchester City": "曼城",
    "Manchester United": "曼联",
}


# ============ La Liga (西甲) ==========================================
_LA_LIGA: Dict[str, str] = {
    "Real Madrid": "皇家马德里",
    "Barcelona": "巴塞罗那",
    "Atletico Madrid": "马德里竞技",
    "Athletic Bilbao": "毕尔巴鄂",
    "Real Sociedad": "皇家社会",
    "Real Betis": "皇家贝蒂斯",
    "Sevilla": "塞维利亚",
    "Villarreal": "比利亚雷亚尔",
    "Girona": "赫罗纳",
    "Valencia": "瓦伦西亚",
    "Mallorca": "马洛卡",
    "Osasuna": "奥萨苏纳",
    "Las Palmas": "拉斯帕尔马斯",
    "Celta Vigo": "塞尔塔",
    "Espanyol": "西班牙人",
    "Getafe": "赫塔费",
    "Rayo Vallecano": "巴列卡诺",
    "Leganes": "莱加内斯",
    "Alaves": "阿拉维斯",
    "Valladolid": "巴利亚多利德",
}


# ============ Serie A (意甲) ==========================================
_SERIE_A: Dict[str, str] = {
    "Inter": "国际米兰",
    "Juventus": "尤文图斯",
    "AC Milan": "AC米兰",
    "Milan": "AC米兰",                # legacy variant
    "Napoli": "那不勒斯",
    "Atalanta": "亚特兰大",
    "Roma": "罗马",
    "Lazio": "拉齐奥",
    "Fiorentina": "佛罗伦萨",
    "Bologna": "博洛尼亚",
    "Torino": "都灵",
    "Genoa": "热那亚",
    "Monza": "蒙扎",
    "Udinese": "乌迪内斯",
    "Como": "科莫",
    "Verona": "维罗纳",
    "Cagliari": "卡利亚里",
    "Empoli": "恩波利",
    "Lecce": "莱切",
    "Parma": "帕尔马",
    "Venezia": "威尼斯",
}


# ============ Bundesliga (德甲) =======================================
_BUNDESLIGA: Dict[str, str] = {
    "Bayern Munich": "拜仁慕尼黑",
    "Bayer Leverkusen": "勒沃库森",
    "Borussia Dortmund": "多特蒙德",
    "Dortmund": "多特蒙德",            # variant
    "RB Leipzig": "莱比锡红牛",
    "Eintracht Frankfurt": "法兰克福",
    "Frankfurt": "法兰克福",            # variant
    "VfB Stuttgart": "斯图加特",
    "Stuttgart": "斯图加特",            # variant
    "Borussia Monchengladbach": "门兴格拉德巴赫",
    "Monchengladbach": "门兴格拉德巴赫", # variant
    "Hoffenheim": "霍芬海姆",
    "Mainz 05": "美因茨",
    "Mainz": "美因茨",                  # variant
    "Wolfsburg": "沃尔夫斯堡",
    "Werder Bremen": "云达不莱梅",
    "Bremen": "云达不莱梅",             # variant
    "Augsburg": "奥格斯堡",
    "Freiburg": "弗赖堡",
    "Union Berlin": "柏林联合",
    "Heidenheim": "海登海姆",
    "St. Pauli": "圣保利",
    "St Pauli": "圣保利",                # variant
    "Holstein Kiel": "霍尔斯坦基尔",
    "Bochum": "波鸿",
    "Koln": "科隆",                     # may appear in archived data
    "Cologne": "科隆",                  # English variant
}


# ============ Ligue 1 (法甲) ==========================================
_LIGUE_1: Dict[str, str] = {
    "Paris SG": "巴黎圣日耳曼",
    "Paris Saint Germain": "巴黎圣日耳曼",
    "PSG": "巴黎圣日耳曼",
    "Marseille": "马赛",
    "Monaco": "摩纳哥",
    "Lyon": "里昂",
    "Lille": "里尔",
    "Nice": "尼斯",
    "Lens": "朗斯",
    "Rennes": "雷恩",
    "Strasbourg": "斯特拉斯堡",
    "Toulouse": "图卢兹",
    "Nantes": "南特",
    "Reims": "兰斯",
    "Brest": "布雷斯特",
    "Auxerre": "欧塞尔",
    "Le Havre": "勒阿弗尔",
    "Angers": "昂热",
    "Montpellier": "蒙彼利埃",
    "Saint-Etienne": "圣埃蒂安",
    "Saint Etienne": "圣埃蒂安",
}


# ============ Championship (英冠) — 2024-25 ===========================
_CHAMPIONSHIP: Dict[str, str] = {
    "Leeds": "利兹联",
    "Leeds United": "利兹联",
    "Burnley": "伯恩利",
    "Sheffield United": "谢菲尔德联",
    "Sunderland": "桑德兰",
    "Sheffield Wednesday": "谢菲尔德星期三",
    "West Brom": "西布朗",
    "West Bromwich Albion": "西布朗",
    "Coventry": "考文垂",
    "Coventry City": "考文垂",
    "Middlesbrough": "米德尔斯堡",
    "Norwich": "诺维奇",
    "Norwich City": "诺维奇",
    "Bristol City": "布里斯托城",
    "Watford": "沃特福德",
    "Millwall": "米尔沃尔",
    "Hull City": "赫尔城",
    "Hull": "赫尔城",
    "Swansea": "斯旺西",
    "Swansea City": "斯旺西",
    "Preston": "普雷斯顿",
    "Preston North End": "普雷斯顿",
    "QPR": "女王公园巡游者",
    "Queens Park Rangers": "女王公园巡游者",
    "Stoke City": "斯托克城",
    "Stoke": "斯托克城",
    "Blackburn": "布莱克本",
    "Blackburn Rovers": "布莱克本",
    "Cardiff": "卡迪夫城",
    "Cardiff City": "卡迪夫城",
    "Luton": "卢顿",
    "Luton Town": "卢顿",
    "Derby": "德比郡",
    "Derby County": "德比郡",
    "Oxford": "牛津联",
    "Oxford United": "牛津联",
    "Portsmouth": "朴茨茅斯",
    "Plymouth": "普利茅斯",
    "Plymouth Argyle": "普利茅斯",
}


# ============ La Liga Segunda (西乙) — 2024-25 ========================
_SEGUNDA: Dict[str, str] = {
    "Levante": "莱万特",
    "Elche": "埃尔切",
    "Mirandes": "米兰德斯",
    "Racing Santander": "桑坦德竞技",
    "Racing": "桑坦德竞技",
    "Sporting Gijon": "希洪竞技",
    "Sporting": "希洪竞技",
    "Albacete": "阿尔巴塞特",
    "Almeria": "阿尔梅里亚",
    "Burgos": "布尔戈斯",
    "Cadiz": "加的斯",
    "Cartagena": "卡塔赫纳",
    "Castellon": "卡斯特利翁",
    "Cordoba": "科尔多瓦",
    # V12 W4 — teams seen live that the dict missed (promotion/reserve sides).
    # The frontend's accent/affix fold catches "Granada CF"/"Castellón"; these
    # three have no fold path (new team or reserve marker), so map explicitly.
    "Ceuta": "休达",
    "AD Ceuta": "休达",
    "Cultural Leonesa": "莱昂内萨",
    "Real Sociedad II": "皇家社会 B",
    "Deportivo La Coruna": "拉科鲁尼亚",
    "Deportivo": "拉科鲁尼亚",
    "Eibar": "埃瓦尔",
    "Eldense": "埃尔登塞",
    "Granada": "格拉纳达",
    "Huesca": "韦斯卡",
    "Malaga": "马拉加",
    "Oviedo": "奥维耶多",
    "Real Oviedo": "奥维耶多",
    "Real Zaragoza": "萨拉戈萨",
    "Zaragoza": "萨拉戈萨",
    "Tenerife": "特内里费",
    "Real Sociedad B": "皇家社会 B",
}


# ============ Serie B (意乙) — 2024-25 =================================
_SERIE_B: Dict[str, str] = {
    "Sassuolo": "萨索洛",
    "Pisa": "比萨",
    "Spezia": "斯佩齐亚",
    "Cremonese": "克雷莫纳",
    "Cesena": "切塞纳",
    "Catanzaro": "卡坦扎罗",
    "Palermo": "巴勒莫",
    "Bari": "巴里",
    "Brescia": "布雷西亚",
    "Frosinone": "弗罗西诺内",
    "Modena": "摩德纳",
    "Reggiana": "雷吉亚纳",
    "Sampdoria": "桑普多利亚",
    "Carrarese": "卡拉雷塞",
    "Cittadella": "切塔代拉",
    "Cosenza": "科森扎",
    "Juve Stabia": "尤文图斯·斯塔比亚",
    "Mantova": "曼托瓦",
    "Salernitana": "萨勒尼塔纳",
    "Sudtirol": "南蒂罗尔",
    # ── 2025-26 升降级换的 7 支(2026-08-03 补)──────────────────────────
    # ⚠️ **这 7 条不是「用赛事身份钉」出来的 —— 那条路在意乙不存在。** 三个带中文名
    # 的源全查过:竞彩历史档案 12,914 场(意甲 1,353 / 意大利杯 19 / 意超杯 3,
    # **意乙 0**)、竞彩实盘捕获 17 联赛(意乙 0)、皇冠收盘史 58 联赛(意乙 0)。
    # **竞彩不卖意乙**,所以没有可对的赛事,也就没有身份可钉。
    #
    # 那为什么还敢填?因为这里的风险结构和「join key」不同:
    #   · 意乙没有竞彩盘 ⇒ 不存在可被污染的 join(`_ZH_TO_EN` 反转出来的键
    #     永远不会被竞彩的意乙行命中,因为没有那种行)
    #   · 这是**显示名** —— 错了是卡片标签写错,肉眼可见、可改,不是静默污染
    #   · 唯一真风险是**撞车**:中文名若已指向别的队,反转字典会造出错的 join key
    # 所以填之前逐条跑了撞车检查(见 tests/v4/test_serie_b_zh_names.py):
    # 7 条在 `TEAM_NAME_ZH` / `_ZH_OVERRIDES` / 竞彩档案 / 皇冠档案里**都没被占**。
    #
    # 同一段里本来就有 9 支从未在竞彩出现过的队(桑普多利亚/南蒂罗尔/卡拉雷塞/
    # 曼托瓦/尤文图斯·斯塔比亚…),它们当初也是按标准译名写的 —— 口径一致。
    # 6 支是意大利城市名(译名唯一);Virtus Entella 取通用简称「恩泰拉」。
    "Arezzo": "阿雷佐",
    "Ascoli": "阿斯科利",
    "Avellino": "阿维利诺",
    "Benevento": "贝内文托",
    "Padova": "帕多瓦",
    "Vicenza Virtus": "维琴察",
    "Virtus Entella": "恩泰拉",
}


# ============ 2. Bundesliga (德乙) — 2024-25 ==========================
_2_BUNDESLIGA: Dict[str, str] = {
    "Hamburg": "汉堡",
    "Hamburger SV": "汉堡",
    "Hannover 96": "汉诺威 96",
    "Hannover": "汉诺威 96",
    "Hertha Berlin": "柏林赫塔",
    "Hertha BSC": "柏林赫塔",
    "Schalke 04": "沙尔克 04",
    "Schalke": "沙尔克 04",
    "Karlsruher": "卡尔斯鲁厄",
    "Karlsruher SC": "卡尔斯鲁厄",
    "Nurnberg": "纽伦堡",
    "1. FC Nurnberg": "纽伦堡",
    "Greuther Furth": "菲尔特",
    "Greuther Fürth": "菲尔特",
    "SpVgg Greuther Fürth": "菲尔特",
    "SpVgg Greuther Furth": "菲尔特",
    # 3.Liga / Relegations-Playoff opponents (2026-05-27 — Rot-Weiß Essen
    # faced Greuther Fürth in the 2.BL↔3.Liga playoff)
    "Rot-Weiß Essen": "红白埃森",
    "Rot-Weiss Essen": "红白埃森",
    "RW Essen": "红白埃森",
    "Fortuna Dusseldorf": "杜塞尔多夫",
    "Dusseldorf": "杜塞尔多夫",
    "Paderborn": "帕德博恩",
    "Magdeburg": "马格德堡",
    "1. FC Magdeburg": "马格德堡",
    "Kaiserslautern": "凯泽斯劳滕",
    "1. FC Kaiserslautern": "凯泽斯劳滕",
    "Braunschweig": "布伦瑞克",
    "Eintracht Braunschweig": "布伦瑞克",
    "Darmstadt": "达姆施塔特",
    "Darmstadt 98": "达姆施塔特",
    "Elversberg": "埃尔弗斯堡",
    "Munster": "明斯特",
    "Preussen Munster": "明斯特",
    "Regensburg": "雷根斯堡",
    "Jahn Regensburg": "雷根斯堡",
    "Ulm": "乌尔姆",
    "SSV Ulm": "乌尔姆",
    # Koln / Cologne handled in _BUNDESLIGA (cross-relegated; same translation)
}


# ============ Ligue 2 (法乙) — 2024-25 ================================
_LIGUE_2: Dict[str, str] = {
    "Lorient": "洛里昂",
    "Paris FC": "巴黎 FC",
    "Metz": "梅斯",
    "Guingamp": "甘冈",
    "Caen": "卡昂",
    "Ajaccio": "阿雅克肖",
    "Amiens": "亚眠",
    "Annecy": "阿讷西",
    "Bastia": "巴斯蒂亚",
    "Clermont": "克莱蒙",
    "Clermont Foot": "克莱蒙",
    "Dunkerque": "敦刻尔克",
    "Grenoble": "格勒诺布尔",
    "Laval": "拉瓦尔",
    "Martigues": "马蒂格",
    "Pau": "波城",
    "Pau FC": "波城",
    "Red Star": "巴黎红星",
    "Red Star FC 93": "巴黎红星",     # AF 2026-27 全名(FC 93 后缀 fold/大小写都够不到)
    "Rodez": "罗德兹",
    "Troyes": "特鲁瓦",
    "ESTAC Troyes": "特鲁瓦",
}


# ============ Eredivisie (荷甲) — 2024-25 =============================
_EREDIVISIE: Dict[str, str] = {
    "Ajax": "阿贾克斯",
    "AZ Alkmaar": "阿尔克马尔",
    "AZ": "阿尔克马尔",
    "PSV": "埃因霍温",
    "PSV Eindhoven": "埃因霍温",
    "Feyenoord": "费耶诺德",
    "Twente": "特温特",
    "FC Twente": "特温特",
    "Utrecht": "乌得勒支",
    "FC Utrecht": "乌得勒支",
    "NEC": "奈梅亨",
    "NEC Nijmegen": "奈梅亨",
    "Heerenveen": "海伦芬",
    "SC Heerenveen": "海伦芬",
    "Sparta Rotterdam": "鹿特丹斯巴达",
    "Go Ahead Eagles": "前进之鹰",
    "Fortuna Sittard": "锡塔德",
    "Heracles": "赫拉克莱斯",
    "Heracles Almelo": "赫拉克莱斯",
    "PEC Zwolle": "兹沃勒",
    "Zwolle": "兹沃勒",
    "RKC Waalwijk": "瓦尔韦克",
    "Waalwijk": "瓦尔韦克",
    "NAC Breda": "布雷达",
    "Willem II": "威廉二世",
    "Almere City": "阿尔梅勒城",
    "Groningen": "格罗宁根",
    "FC Groningen": "格罗宁根",
}


# ============ Primeira Liga (葡超) — 2024-25 / 2025-26 ==================
# Also includes LigaPro (second tier) teams that surface via the
# end-of-season Promotion Playoff (3rd-place LigaPro vs 14th-place Primeira).
_PRIMEIRA: Dict[str, str] = {
    "Porto": "波尔图",
    "FC Porto": "波尔图",
    "Benfica": "本菲卡",
    "SL Benfica": "本菲卡",
    "Sporting CP": "葡萄牙体育",
    "Sporting Lisbon": "葡萄牙体育",
    "Braga": "布拉加",
    "SC Braga": "布拉加",
    "Vitoria Guimaraes": "吉马良斯",
    "Vitoria SC": "吉马良斯",
    "Famalicao": "法马利康",
    "FC Famalicao": "法马利康",
    "Moreirense": "莫雷伦斯",
    "Boavista": "博阿维斯塔",
    "Estoril": "埃斯托里尔",
    "Estoril Praia": "埃斯托里尔",
    "Estrela Amadora": "阿马多拉之星",
    "CF Estrela Amadora": "阿马多拉之星",
    "Casa Pia": "卡萨皮亚",
    "Casa Pia AC": "卡萨皮亚",
    "Rio Ave": "里奥艾维",
    "Arouca": "阿罗卡",
    "Farense": "法伦塞",
    "AVS": "AVS 体育",  # club uses bare-initials brand; suffix added for zh consistency
    "AVS Futebol SAD": "AVS 体育",
    "Gil Vicente": "维森特",
    "Nacional": "纳西奥纳",
    "CD Nacional": "纳西奥纳",
    "Santa Clara": "圣克拉拉",
    "Maritimo": "马里迪莫",
    # ── LigaPro Promotion Playoff opponents (2026-05-27 — Torreense
    # faced Casa Pia in the 2025-26 Liga↔LigaPro playoff)
    "Torreense": "托雷恩塞",
    "SC Torreense": "托雷恩塞",
    "Tondela": "通德拉",
    "CD Tondela": "通德拉",
    "Académico Viseu": "维塞乌学院",
    "Academico Viseu": "维塞乌学院",
    "AVS Viseu": "维塞乌学院",
    "Vizela": "维泽拉",
    "FC Vizela": "维泽拉",
    "Penafiel": "佩纳菲尔",
    "FC Penafiel": "佩纳菲尔",
    "Chaves": "查韦斯",
    "GD Chaves": "查韦斯",
    "Mafra": "马夫拉",
    "CD Mafra": "马夫拉",
    "União de Leiria": "莱里亚",
    "Uniao de Leiria": "莱里亚",
    "Leiria": "莱里亚",
}


# ============ Belgian Pro League (比甲) — 2024-25 =====================
_BEL_PRO: Dict[str, str] = {
    "Club Brugge": "布鲁日",
    "Brugge": "布鲁日",
    "Anderlecht": "安德莱赫特",
    "RSC Anderlecht": "安德莱赫特",
    "Genk": "亨克",
    "KRC Genk": "亨克",
    "Gent": "根特",
    "KAA Gent": "根特",
    "Antwerp": "安特卫普",
    "Royal Antwerp": "安特卫普",
    "Standard Liege": "标准列日",
    "Standard": "标准列日",
    "Union St. Gilloise": "圣吉罗斯联",
    "Union Saint-Gilloise": "圣吉罗斯联",
    "Cercle Brugge": "布鲁日小希望",
    "Charleroi": "查勒罗瓦",
    "OH Leuven": "鲁汶",
    "Mechelen": "梅赫伦",
    "KV Mechelen": "梅赫伦",
    "Westerlo": "韦斯特洛",
    "KVC Westerlo": "韦斯特洛",
    "Sint-Truiden": "圣特勒伊登",
    "STVV": "圣特勒伊登",
    "Kortrijk": "科特赖克",
    "KV Kortrijk": "科特赖克",
    "Beerschot": "比尔肖特",
    "Dender": "登德",
}


# ============ J1 League (日职联) — 2024-25 ============================
_JPN_J1: Dict[str, str] = {
    "Vissel Kobe": "神户胜利船",
    "Sanfrecce Hiroshima": "广岛三箭",
    "Machida Zelvia": "町田泽维亚",
    "Gamba Osaka": "大阪钢巴",
    "Tokyo Verdy": "东京绿茵",
    "Kashima Antlers": "鹿岛鹿角",
    "Cerezo Osaka": "大阪樱花",
    "FC Tokyo": "FC 东京",
    "Urawa Red Diamonds": "浦和红钻",
    "Urawa Reds": "浦和红钻",
    "Nagoya Grampus": "名古屋鲸八",
    "Yokohama F. Marinos": "横滨水手",
    "Yokohama F Marinos": "横滨水手",
    "Yokohama FC": "横滨 FC",
    "Avispa Fukuoka": "福冈黄蜂",
    "Kashiwa Reysol": "柏太阳神",
    "Kawasaki Frontale": "川崎前锋",
    "Kyoto Sanga": "京都不死鸟",
    "Shonan Bellmare": "湘南海洋",
    "Albirex Niigata": "新潟天鹅",
    "Jubilo Iwata": "磐田喜悦",
    "Sagan Tosu": "鸟栖砂岩",
    "Hokkaido Consadole Sapporo": "札幌冈萨多",
    "Consadole Sapporo": "札幌冈萨多",
}


# ============ National teams (国家队 — WC / EURO / COPA America) ========
# V12 W0 (2026-05-27) — added because WC tab was displaying raw English
# names. Covers all 67 nations in NATION_CLUBELO_CODES (V8 W7) plus the
# common API-Football spelling variants. Variants point at the same
# Chinese name to keep lookup robust against source inconsistencies.
_NATIONAL_TEAMS: Dict[str, str] = {
    # ── UEFA ──────────────────────────────────────────────────
    "England": "英格兰",
    "France": "法国",
    "Spain": "西班牙",
    "Germany": "德国",
    "Italy": "意大利",
    "Netherlands": "荷兰",
    "Holland": "荷兰",
    "Portugal": "葡萄牙",
    "Belgium": "比利时",
    "Croatia": "克罗地亚",
    "Switzerland": "瑞士",
    "Austria": "奥地利",
    "Poland": "波兰",
    "Denmark": "丹麦",
    "Sweden": "瑞典",
    "Turkey": "土耳其",
    "Türkiye": "土耳其",
    "Russia": "俄罗斯",
    "Ukraine": "乌克兰",
    "Czech Republic": "捷克",
    "Czechia": "捷克",
    "Romania": "罗马尼亚",
    "Scotland": "苏格兰",
    "Wales": "威尔士",
    "Republic of Ireland": "爱尔兰",
    "Ireland": "爱尔兰",
    "Rep. Of Ireland": "爱尔兰",
    "Northern Ireland": "北爱尔兰",
    "Serbia": "塞尔维亚",
    "Greece": "希腊",
    "Norway": "挪威",
    "Hungary": "匈牙利",
    "Slovakia": "斯洛伐克",
    "Slovenia": "斯洛文尼亚",
    "Albania": "阿尔巴尼亚",
    "Bosnia and Herzegovina": "波黑",
    "Bosnia": "波黑",
    "Bosnia & Herzegovina": "波黑",
    "Bulgaria": "保加利亚",
    "Iceland": "冰岛",
    "Finland": "芬兰",
    "Georgia": "格鲁吉亚",
    "North Macedonia": "北马其顿",
    "Macedonia": "北马其顿",
    "FYR Macedonia": "北马其顿",

    # ── CONMEBOL ──────────────────────────────────────────────
    "Brazil": "巴西",
    "Argentina": "阿根廷",
    "Uruguay": "乌拉圭",
    "Colombia": "哥伦比亚",
    "Chile": "智利",
    "Peru": "秘鲁",
    "Ecuador": "厄瓜多尔",
    "Paraguay": "巴拉圭",
    "Bolivia": "玻利维亚",
    "Venezuela": "委内瑞拉",

    # ── CONCACAF ──────────────────────────────────────────────
    "USA": "美国",
    "United States": "美国",
    "Mexico": "墨西哥",
    "Canada": "加拿大",
    "Costa Rica": "哥斯达黎加",
    "Jamaica": "牙买加",
    "Honduras": "洪都拉斯",
    "Panama": "巴拿马",

    # ── AFC + AFC-cross ───────────────────────────────────────
    "Japan": "日本",
    "Korea Republic": "韩国",
    "South Korea": "韩国",
    "Australia": "澳大利亚",
    "Iran": "伊朗",
    "Saudi Arabia": "沙特阿拉伯",
    "Qatar": "卡塔尔",
    "China PR": "中国",
    "China": "中国",

    # ── CAF ───────────────────────────────────────────────────
    "Morocco": "摩洛哥",
    "Senegal": "塞内加尔",
    "Egypt": "埃及",
    "Tunisia": "突尼斯",
    "Algeria": "阿尔及利亚",
    "Nigeria": "尼日利亚",
    "Cameroon": "喀麦隆",
    "Ghana": "加纳",
    "Ivory Coast": "科特迪瓦",
    "Côte d'Ivoire": "科特迪瓦",
    # ── Extra WC 2026 candidates (not in NATION_CLUBELO_CODES yet) ──
    # Discovered 2026-05-27 when "Mexico vs South Africa" displayed
    # half-translated. Cover the most likely 48-team WC 2026 roster.
    "South Africa": "南非",
    "Cape Verde": "佛得角",
    "Cabo Verde": "佛得角",
    "Cape Verde Islands": "佛得角",  # API-Football's WC 2026 spelling
    "DR Congo": "刚果民主共和国",
    "Congo DR": "刚果民主共和国",
    "Mali": "马里",
    "Burkina Faso": "布基纳法索",
    "Zambia": "赞比亚",
    "Madagascar": "马达加斯加",
    "Comoros": "科摩罗",
    # AFC extras
    "Uzbekistan": "乌兹别克斯坦",
    "Iraq": "伊拉克",
    "Jordan": "约旦",
    "UAE": "阿联酋",
    "United Arab Emirates": "阿联酋",
    "Oman": "阿曼",
    "Indonesia": "印度尼西亚",
    "Bahrain": "巴林",
    "Kuwait": "科威特",
    "Lebanon": "黎巴嫩",
    "Syria": "叙利亚",
    "Vietnam": "越南",
    "Thailand": "泰国",
    "Palestine": "巴勒斯坦",
    "India": "印度",
    "Hong Kong": "香港",
    "Chinese Taipei": "中国台北",
    # OFC + remaining CONCACAF (likely WC 2026 playoff/inter-conf)
    "New Zealand": "新西兰",
    "Haiti": "海地",
    "Curaçao": "库拉索",
    "Curacao": "库拉索",
    "El Salvador": "萨尔瓦多",
    "Guatemala": "危地马拉",
    "Trinidad and Tobago": "特立尼达和多巴哥",
    "Trinidad": "特立尼达和多巴哥",
    "Suriname": "苏里南",
    "Nicaragua": "尼加拉瓜",
    "Cuba": "古巴",
    "Dominican Republic": "多米尼加",
}


# ============ Combined lookup =========================================
TEAM_NAME_ZH: Dict[str, str] = {}
TEAM_NAME_ZH.update(_EPL)
TEAM_NAME_ZH.update(_LA_LIGA)
TEAM_NAME_ZH.update(_SERIE_A)
TEAM_NAME_ZH.update(_BUNDESLIGA)
TEAM_NAME_ZH.update(_LIGUE_1)
# V11 P1-FE#7 — 9 additional trained leagues
TEAM_NAME_ZH.update(_CHAMPIONSHIP)
TEAM_NAME_ZH.update(_SEGUNDA)
TEAM_NAME_ZH.update(_SERIE_B)
TEAM_NAME_ZH.update(_2_BUNDESLIGA)
TEAM_NAME_ZH.update(_LIGUE_2)
TEAM_NAME_ZH.update(_EREDIVISIE)
TEAM_NAME_ZH.update(_PRIMEIRA)
TEAM_NAME_ZH.update(_BEL_PRO)
TEAM_NAME_ZH.update(_JPN_J1)
# V12 W0 (2026-05-27) — national teams (WC / EURO / Copa America)
TEAM_NAME_ZH.update(_NATIONAL_TEAMS)

# V12 W7 (2026-05-30) — gaps surfaced by a full scan of cached API-Football
# fixtures (the names API-Football actually returns). Three buckets:
#   1. J1 short names API returns that the dict only had under full names
#      (e.g. "Kashima" vs "Kashima Antlers") — the reported 神户 vs Kashima bug.
#   2. Core-league name VARIANTS the dict keys only canonically (e.g. "AS Roma"
#      vs "Roma", "VfL Wolfsburg" vs "Wolfsburg") — _zhFold can't bridge the
#      AS/VfL/Hellas/München/Utd prefixes, so add the exact API spelling.
#   3. UEFA cup clubs + Euro national teams now surfaced by the 杯赛市场模式 +
#      WC/EURO qualifiers. Famous/likely-to-appear sides only; the long tail of
#      obscure qualifying minnows falls back to the Latin name (acceptable —
#      they rarely have a Pinnacle line so rarely surface).
# NB: keys MUST be the exact strings API-Football returns (incl. accents) — the
# frontend looks up the raw name first. Do NOT alias to "Red Star" (the dict's
# "Red Star" is Paris Red Star, NOT Crvena Zvezda).
_V12_W7_CUP_AND_VARIANTS = {
    # ── UCL/UECL 资格赛小国冠军 (2026-07, 待开盘常客) ──
    "Lincoln Red Imps FC": "林肯红魔",
    "Inter Club d'Escaldes": "埃斯卡尔德斯国际",
    "Ararat-Armenia": "阿拉拉特-亚美尼亚",
    "Riga": "里加",
    "Kauno Žalgiris": "考纳斯萨尔吉里斯",
    "Drita": "德里塔",
    "Sabah FA": "萨巴赫",
    "Vardar Skopje": "瓦尔达尔",
    "Floriana": "弗洛里亚纳",
    "Tre Fiori": "特雷菲奥里",
    "Larne": "拉恩",
    "Borac Banja Luka": "巴尼亚卢卡博拉茨",
    "Levski Sofia": "索菲亚列夫斯基",
    "KI Klaksvik": "克拉克斯维克",
    "Atert Bissen": "阿特尔特比森",
    "Vikingur Reykjavik": "维京雷克雅未克",
    "Gyori ETO FC": "杰尔ETO",
    "UNA Strassen": "斯特拉森",
    "La Fiorita": "拉菲奥里塔",
    "AF Elbasani": "埃尔巴萨尼",
    "Bate Borisov": "BATE鲍里索夫",
    # 2026-07-02 补:实测 待开盘(cup-market days=7)剩余未翻译的 12 支资格赛小国队
    "Flora Tallinn": "弗洛拉塔林",          # 爱沙尼亚
    "Saburtalo": "萨布尔塔洛",              # 格鲁吉亚
    "Petrocub": "佩特罗库布",              # 摩尔多瓦 (Petrocub Hîncești)
    "Egnatia Rrogozhinë": "埃格纳蒂亚",     # 阿尔巴尼亚
    "ML Vitebsk": "维捷布斯克",            # 白俄罗斯 (Maxline Vitebsk)
    "Universitatea Craiova": "克拉约瓦大学",  # 罗马尼亚
    "Sutjeska": "苏捷斯卡",                # 黑山 (Sutjeska Nikšić)
    "Zira": "齐拉",                       # 阿塞拜疆
    "Torpedo Kutaisi": "库塔伊西鱼雷",      # 格鲁吉亚
    "GAP Connah S Quay FC": "康纳码头",     # 威尔士 (Connah's Quay Nomads)
    "Ballkani": "巴尔卡尼",                # 科索沃
    "FC Differdange 03": "迪弗当日03",      # 卢森堡
    # ── J1 (short names) ──
    "Kashima": "鹿岛鹿角",
    "Fagiano Okayama": "冈山绿雉",
    "JEF United Chiba": "千叶联",
    "Mito Hollyhock": "水户蜀葵",
    "Shimizu S-pulse": "清水心跳",
    "Urawa": "浦和红钻",
    "V-varen Nagasaki": "V法伦长崎",
    # ── Core-14 league variants (alias to the canonical zh already in dict) ──
    "AS Roma": "罗马",
    "Hellas Verona": "维罗纳",
    "Sheffield Utd": "谢菲尔德联",
    "VfL Wolfsburg": "沃尔夫斯堡",
    "SC Paderborn 07": "帕德博恩",
    "FC Andorra": "安道尔",
    "Athletic Club": "毕尔巴鄂竞技",  # La Liga — API "Athletic Club" vs dict "Athletic Bilbao"
    # ── Euro / WC qualifier national teams ──
    "Armenia": "亚美尼亚", "Azerbaijan": "阿塞拜疆", "Belarus": "白俄罗斯",
    "Cyprus": "塞浦路斯", "Estonia": "爱沙尼亚", "Faroe Islands": "法罗群岛",
    "Gibraltar": "直布罗陀", "Israel": "以色列", "Kazakhstan": "哈萨克斯坦",
    "Kosovo": "科索沃", "Latvia": "拉脱维亚", "Liechtenstein": "列支敦士登",
    "Lithuania": "立陶宛", "Luxembourg": "卢森堡", "Malta": "马耳他",
    "Moldova": "摩尔多瓦", "Montenegro": "黑山", "San Marino": "圣马力诺",
    "andorra": "安道尔",
    # ── UEFA club competitions (famous / likely-to-appear) ──
    "Bayern München": "拜仁慕尼黑", "1899 Hoffenheim": "霍芬海姆",
    "Celtic": "凯尔特人", "Rangers": "格拉斯哥流浪者",
    "Heart Of Midlothian": "哈茨", "Aberdeen": "阿伯丁",
    "Galatasaray": "加拉塔萨雷", "Fenerbahçe": "费内巴切",
    "Beşiktaş": "贝西克塔斯", "Trabzonspor": "特拉布宗体育",
    "Sivasspor": "锡瓦斯体育",
    "PAOK": "塞萨洛尼基", "Panathinaikos": "帕纳辛奈科斯",
    "Olympiakos Piraeus": "奥林匹亚科斯", "AEK Athens FC": "雅典AEK",
    "Aris": "阿里斯",
    "Shakhtar Donetsk": "顿涅茨克矿工", "Dynamo Kyiv": "基辅迪纳摩",
    "Zorya Luhansk": "卢甘斯克黎明",
    "Zenit Saint Petersburg": "圣彼得堡泽尼特", "Spartak Moscow": "莫斯科斯巴达克",
    "Lokomotiv Moscow": "莫斯科火车头",
    "Red Bull Salzburg": "萨尔茨堡红牛", "Sturm Graz": "格拉茨风暴",
    "Rapid Vienna": "维也纳快速", "Austria Vienna": "维也纳奥地利",
    "BSC Young Boys": "伯尔尼年轻人", "FC Basel 1893": "巴塞尔",
    "Servette FC": "塞尔维特", "FC Zurich": "苏黎世", "FC Lugano": "卢加诺",
    "Slavia Praha": "布拉格斯拉维亚", "Sparta Praha": "布拉格斯巴达",
    "Plzen": "比尔森胜利",
    "Dinamo Zagreb": "萨格勒布迪纳摩", "HNK Rijeka": "里耶卡",
    "FK Crvena Zvezda": "贝尔格莱德红星", "FK Partizan": "贝尔格莱德游击队",
    "Qarabag": "卡拉巴赫", "Ludogorets": "卢多戈雷茨",
    "FC Copenhagen": "哥本哈根", "FC Midtjylland": "中日德兰",
    "Brondby": "布隆德比", "Malmo FF": "马尔默",
    "Molde": "莫尔德", "Bodo/Glimt": "博德闪耀", "Brann": "布兰",
    "Club Brugge KV": "布鲁日",
    "Maccabi Tel Aviv": "特拉维夫马卡比", "Maccabi Haifa": "海法马卡比",
    "Ferencvarosi TC": "费伦茨瓦罗斯",
    "Legia Warszawa": "华沙莱吉亚", "Lech Poznan": "波兹南莱赫",
    # 2026-08-06 —— 告警「竞彩在售、但没进盘面」逮到。**整队不在词典**(属 ② 类)⇒
    # 补这里一处同时修 join 和显示;只补 `_ZH_OVERRIDES` 会变成「join 通了、卡片仍显示英文」。
    # 英文键不是按译音猜的:拿能解析的对手 `格拉斯哥流浪者→Rangers` 当锚,在 odds_snapshots
    # 里 2026-08-06 16:00 UEL 唯一命中 `Jagiellonia vs Rangers`,主客顺序也对上。
    # 中文名取竞彩官方写法「比亚韦斯托克」—— 和你在竞彩 App 里看到的一致,不自造。
    "Jagiellonia": "比亚韦斯托克",
    "Slovan Bratislava": "布拉迪斯拉发斯洛万",
    "HJK Helsinki": "赫尔辛基HJK", "Kairat Almaty": "阿拉木图凯拉特",
    "FC Astana": "阿斯塔纳", "Sheriff Tiraspol": "蒂拉斯波尔治安官",
    "Shamrock Rovers": "三叶草流浪者", "The New Saints": "新圣徒",
    # 2026-07-21 UCL Q2:整队缺席本字典 → 既显示英文名(owner 实报「队名没有完全
    # 翻译」)、又因 _ZH_TO_EN 是本字典的反转而 join 不上 Pinnacle(整场丢弃)。
    # 补在这里一处修两处;竞彩写法即 ZH 值,反转后自然可解。
    "Omonia Nicosia": "奥莫尼亚",
    # 2026-07-23 UEL Q2 同病:整队缺席 → 显示英文 + 整场丢弃。英文键取自
    # odds_snapshots 里**已存在的那条 Pinnacle 线**(`HNK Hajduk Split vs Pafos`,
    # cup_market 从 07-20 起一直在跟)—— 即 join 目标本身的拼写,不是照译音猜的。
    "Pafos": "帕福斯",
}
TEAM_NAME_ZH.update(_V12_W7_CUP_AND_VARIANTS)

# V12 W8 (2026-05-30) — market-mode league expansion (Nordic / APAC / Europe).
# Keys are the exact strings API-Football returns (verified via /teams). The 27
# clubs already in the dict (UEFA cup regulars + relegated J1 sides) are NOT
# repeated here. The handful of genuinely obscure lower-table sides that aren't
# listed fall back to the Latin name (acceptable, same policy as the cup tail).
_V12_W8_NEW_LEAGUES = {
    # ── 挪超 NOR_ELITESERIEN ──
    "Aalesund": "阿勒松", "Fredrikstad": "弗雷德里克斯塔", "Ham-Kam": "哈马卡姆",
    "KFUM Oslo": "奥斯陆KFUM", "Kristiansund BK": "克里斯蒂安松", "Lillestrom": "利勒斯特罗姆",
    "Rosenborg": "罗森博格", "Sandefjord": "桑德菲尤尔", "Sarpsborg 08 FF": "萨尔普斯堡",
    "Start": "斯塔特", "Tromso": "特罗姆瑟", "Valerenga": "瓦勒伦加", "Viking": "维京",
    # ── 瑞典超 SWE_ALLSVENSKAN ──
    "AIK Stockholm": "索尔纳AIK", "BK Hacken": "哈尔肯", "Degerfors IF": "德格福斯",
    "Djurgardens IF": "尤尔加登", "Gais": "哥德堡GAIS", "Halmstad": "哈尔姆斯塔",
    "Hammarby FF": "哈马比", "IF Brommapojkarna": "布罗马波卡纳", "IF Elfsborg": "埃尔夫斯堡",
    "IFK Goteborg": "哥德堡", "Kalmar FF": "卡尔马", "Mjallby AIF": "米亚尔比",
    "Orgryte IS": "奥格瑞特", "Sirius": "天狼星", "Vasteras SK FK": "韦斯特罗斯",
    # ── 芬超 FIN_VEIKKAUSLIIGA ──
    "AC Oulu": "奥卢", "FF Jaro": "雅罗", "Gnistan": "格尼斯坦", "Ilves": "伊尔维斯",
    "Inter Turku": "图尔库国际", "KuPS": "库奥皮奥", "Lahti": "拉赫蒂", "Mariehamn": "玛丽港",
    "SJK": "塞伊奈约基", "Turku PS": "图尔库PS", "VPS": "瓦萨",
    # ── K联赛 KOR_K_LEAGUE_1 ──
    "Bucheon FC 1995": "富川", "Daejeon Citizen": "大田市民", "FC Anyang": "安养",
    "FC Seoul": "首尔", "Gangwon FC": "江原", "Gimcheon Sangmu FC": "金泉尚武",
    "Gwangju FC": "光州", "Incheon United": "仁川联", "Jeju United FC": "济州联",
    "Jeonbuk Motors": "全北现代", "Pohang Steelers": "浦项制铁", "Ulsan Hyundai FC": "蔚山现代",
    # ── 日职乙 JPN_J2 ──
    "Biwako Shiga": "滋贺琵琶湖", "Blaublitz Akita": "秋田蓝色闪电", "Ehime FC": "爱媛",
    "FC Gifu": "岐阜", "FC Ryukyu": "琉球", "Fujieda MYFC": "藤枝", "Fukushima United": "福岛联",
    "Gainare Tottori": "鸟取", "Imabari": "今治", "Iwaki": "磐城", "Kagoshima United": "鹿儿岛联",
    "Kamatamare Sanuki": "赞岐", "Kanazawa": "金泽",
    "Kataller Toyama": "富山", "Kitakyushu": "北九州",
    "Kochi United": "高知联", "Matsumoto Yamaga": "松本山雅", "Montedio Yamagata": "山形山神",
    "Nara Club": "奈良", "Oita Trinita": "大分三神", "Omiya Ardija": "大宫松鼠", "Osaka": "FC大阪",
    "Parceiro Nagano": "长野", "Renofa Yamaguchi": "山口", "Roasso Kumamoto": "熊本",
    "Sagamihara": "相模原", "Tegevajaro Miyazaki": "宫崎", "Thespakusatsu Gunma": "群马",
    "Tochigi City": "枥木城市", "Tochigi SC": "枥木", "Tokushima Vortis": "德岛漩涡",
    "Vanraure Hachinohe": "八户", "Vegalta Sendai": "仙台维加塔", "Ventforet Kofu": "甲府风林",
    # ── 丹超 DNK_SUPERLIGA ──
    "Aarhus": "奥胡斯", "FC Fredericia": "弗雷德里西亚", "FC Nordsjaelland": "北西兰",
    "Odense": "欧登塞", "Randers FC": "兰德斯", "Silkeborg": "西尔克堡", "Sonderjyske": "南日德兰",
    "Vejle": "瓦埃勒", "Viborg": "维堡",
    # ── 澳超 AUS_A_LEAGUE ──
    "Adelaide United": "阿德莱德联", "Auckland": "奥克兰", "Brisbane Roar": "布里斯班狮吼",
    "Central Coast Mariners": "中央海岸水手", "Macarthur": "麦克阿瑟", "Melbourne City": "墨尔本城",
    "Melbourne Victory": "墨尔本胜利", "Newcastle Jets": "纽卡斯尔喷气机",
    "Perth Glory": "珀斯光荣", "Sydney": "悉尼FC", "Wellington Phoenix": "惠灵顿凤凰",
    "Western Sydney Wanderers": "西悉尼流浪者",
    # ── 苏超 SCO_PREMIERSHIP ──
    "Arbroath": "阿布罗斯", "Dundee": "邓迪", "Dundee Utd": "邓迪联", "Dunfermline": "邓弗姆林",
    "Falkirk": "福尔柯克", "Hibernian": "希伯尼安", "Kilmarnock": "基尔马诺克",
    "Livingston": "利文斯顿", "Motherwell": "马瑟韦尔", "Partick": "帕蒂克", "ST Mirren": "圣米伦",
    # ── 土超 TUR_SUPER_LIG ──
    "Alanyaspor": "阿兰亚士邦", "Antalyaspor": "安塔利亚士邦", "Başakşehir": "巴萨克塞希尔",
    "Eyüpspor": "埃于普士邦", "Fatih Karagümrük": "卡拉古鲁克", "Gaziantep FK": "加济安泰普",
    "Gençlerbirliği S.K.": "根克勒比利吉", "Göztepe": "戈兹塔佩", "Kasımpaşa": "卡瑟姆帕萨",
    "Kayserispor": "开塞利士邦", "Kocaelispor": "科贾埃利士邦", "Konyaspor": "科尼亚士邦",
    "Rizespor": "里泽士邦", "Samsunspor": "萨姆松士邦",
    # AF 队表新增 3 队(体检 2026-07-12 registry-coverage 硬缺口:3/18 zh 打不中 →
    # 整对静默丢弃风险)。竞彩拼法未知(无竞彩队表可 diff)→ 用媒体标准音译;竞彩若
    # 拼法不同,由 ingest 的「过半丢失」哨兵兜底(见 registry_coverage.py §51-53)。
    "Amed": "阿米德", "Erzurumspor FK": "埃尔祖鲁姆士邦", "Çorum FK": "乔鲁姆",
    # ── 瑞士超 SUI_SUPER_LEAGUE ──
    "FC Aarau": "阿劳", "FC Luzern": "卢塞恩", "FC ST. Gallen": "圣加仑", "FC Sion": "锡永",
    "FC Thun": "图恩", "FC Winterthur": "温特图尔", "Grasshoppers": "草蜢", "Lausanne": "洛桑",
    # ── 美职联 USA_MLS(2026-07-14 owner 补)── key = AF /teams season-2026 英文名。
    # 竞彩拼法未知(无竞彩队表可 diff)→ 标准媒体音译;竞彩若拼法不同由 ingest
    # 「过半丢失」哨兵兜底(见 sporttery.py / registry_coverage.py §51-53)。
    "Atlanta United FC": "亚特兰大联", "Austin": "奥斯汀",
    "CF Montreal": "蒙特利尔", "Charlotte": "夏洛特",
    "Chicago Fire": "芝加哥火焰", "Colorado Rapids": "科罗拉多急流",
    "Columbus Crew": "哥伦布机员", "DC United": "华盛顿联",
    "FC Cincinnati": "辛辛那提", "FC Dallas": "达拉斯",
    "Houston Dynamo": "休斯顿迪纳摩", "Inter Miami": "迈阿密国际",
    "Los Angeles FC": "洛杉矶FC", "Los Angeles Galaxy": "洛杉矶银河",
    "Minnesota United FC": "明尼苏达联", "Nashville SC": "纳什维尔",
    "New England Revolution": "新英格兰革命", "New York City FC": "纽约城",
    "New York Red Bulls": "纽约红牛", "Orlando City SC": "奥兰多城",
    "Philadelphia Union": "费城联", "Portland Timbers": "波特兰伐木者",
    "Real Salt Lake": "盐湖城皇家", "San Diego": "圣地亚哥FC",
    "San Jose Earthquakes": "圣何塞地震", "Seattle Sounders": "西雅图海湾人",
    "Sporting Kansas City": "堪萨斯城竞技", "St. Louis City": "圣路易斯城",
    "Toronto FC": "多伦多", "Vancouver Whitecaps": "温哥华白帽",
    # ── 巴甲 BRA_SERIE_A(2026-07-14 owner 补)── 同上,标准媒体译名。
    "Atletico Paranaense": "巴拉纳竞技", "Atletico-MG": "米内罗竞技", "Bahia": "巴伊亚",
    "Botafogo": "博塔弗戈", "Chapecoense-sc": "沙佩科恩斯", "Corinthians": "科林蒂安",
    "Coritiba": "库里蒂巴", "Cruzeiro": "克鲁塞罗", "Flamengo": "弗拉门戈",
    "Fluminense": "弗鲁米嫩塞", "Gremio": "格雷米奥", "Internacional": "国际",
    "Mirassol": "米拉索尔", "Palmeiras": "帕尔梅拉斯", "RB Bragantino": "布拉甘蒂诺",
    "Remo": "雷莫", "Santos": "桑托斯", "Sao Paulo": "圣保罗",
    "Vasco DA Gama": "瓦斯科达伽马", "Vitoria": "维多利亚",
    # ── 荷乙 NED_EERSTE_DIVISIE(2026-08-05 owner 补)─────────────────────────
    # ⭐ 这 13 条**不是查媒体译名写的,是推导出来的**:皇冠线史 `crown_close_history`
    # 里有荷乙的中文队名(105 场),AF 有英文名 + 日期 + 比分 ⇒ 按「同日同比分且
    # 该组合唯一」把两侧配对。**零冲突**,每条背后有 1–6 场共同比赛的证据。
    # 同 [[cross-source-team-name-mismatch]] 的固定修法:别猜,让数据自己配。
    "De Graafschap": "格拉夫",       # 3 场共同证据
    "Vitesse": "维迪斯",             # 1(season 2024,当时降在荷乙)
    "VVV Venlo": "芬洛",             # 1
    "Emmen": "埃门",                 # 3
    "Dordrecht": "多德勒支",          # 3
    "MVV": "马斯特里",               # 1
    "Roda": "罗达JC",                # 6
    "FC Volendam": "福伦丹",          # 2
    "Waalwijk": "瓦尔韦克",           # 5
    "Den Bosch": "登博思",            # 2
    "FC Eindhoven": "埃因FC",         # 5
    "FC OSS": "奥斯",                # 2
    "Helmond Sport": "海尔蒙特",       # 4
    # ⛔ `Jong Ajax` / `Jong AZ` / `Jong PSV U21` / `Jong Utrecht` 四支预备队
    # **故意没有条目** —— 皇冠 105 场荷乙里 19 个中文名一支预备队都没有,竞彩
    # 不上架它们 ⇒ 没有可抄的中文写法,编一个就是瞎猜。见 test_registry_coverage
    # 里那条逐名列出的窄豁免(不写 `Jong ` 前缀规则:那是拿语法代理测语义)。
}
TEAM_NAME_ZH.update(_V12_W8_NEW_LEAGUES)

# 体检 Wave2 (2026-07-04) — 2026-27 roster diff against the LIVE API-Football
# /teams tables for all 13 cron leagues (+J1): 27 promoted/renamed clubs the
# dict lacked entirely. Keys = exact AF spellings (same rule as V12 W7); zh =
# 竞彩惯用名 best-effort — the whole-league-loss alarm + _ZH_OVERRIDES patch
# any 竞彩-side variants when these leagues go on sale in August. The
# alias-shadowing half of the same diff (dict HAS the club under a non-AF
# spelling) is fixed in sporttery._EN_OVERRIDES, not here.
# NB: ITA_SERIE_B 2026-27 was still unpublished on AF at diff time (empty
# table) — re-run nutmeg-registry-coverage once it lists.
_W2_2026_ROSTER_ADDITIONS = {
    # ── 英冠 ENG_CHAMPIONSHIP (升班马/降级) ──
    "Birmingham": "伯明翰", "Bolton": "博尔顿", "Charlton": "查尔顿",
    "Lincoln": "林肯城", "Wrexham": "雷克斯汉姆",
    # ── 西乙 ESP_SEGUNDA_DIVISION ──
    "Castellón": "卡斯特利翁", "Celta de Vigo II": "塞尔塔B", "Sabadell": "萨瓦德尔",
    # ── 德乙 GER_2_BUNDESLIGA ──
    "Arminia Bielefeld": "比勒费尔德", "Dynamo Dresden": "德累斯顿迪纳摩",
    "Energie Cottbus": "科特布斯", "VfL Osnabrück": "奥斯纳布吕克",
    # ── 法甲/法乙 ──
    "Le Mans": "勒芒",
    "Boulogne": "布洛涅", "Dijon": "第戎", "Nancy": "南锡", "Sochaux": "索肖",
    # ── 荷甲 NED_EREDIVISIE ──
    "ADO Den Haag": "海牙", "Cambuur": "坎布尔", "Excelsior": "鹿特丹精英",
    "Telstar": "特尔斯达",
    # ── 葡超 PRT_PRIMEIRA_LIGA ──
    "Alverca": "阿尔维卡",
    # ── 比甲 BEL_PRO_LEAGUE ──
    "Lommel United": "洛默尔", "RAAL La Louvière": "拉卢维耶尔",
    "SK Beveren": "贝弗伦", "St. Truiden": "圣图尔登", "Zulte Waregem": "祖尔特瓦雷根",
    # ── 市场模式联赛 (2026-07-04 瑞超事件后 registry-coverage 扩容查出) ──
    "ST Johnstone": "圣约翰斯通",   # 苏超; AF 全大写 ST
    "AC Horsens": "霍森斯",         # 丹超升班马
    "Lyngby": "林比",               # 丹超
    "FC Vaduz": "瓦杜兹",           # 瑞士超升班马
}
TEAM_NAME_ZH.update(_W2_2026_ROSTER_ADDITIONS)

# 2026-07-05 — Polymarket 交叉校验看板 (只读研究盘) surfaces leagues the betting
# boards never touch: US NWSL 女足 + 巴西联赛. These render raw-English on the PM
# board until keyed. Keys = exact Polymarket spellings (the "W" suffix = women's,
# how Polymarket disambiguates). This board is a rotating window over ALL of
# Polymarket's football markets, so new untranslated names WILL reappear as its
# slate rotates — that's inherent to a global cross-check board, not a bug; add
# them as they surface. Only the currently-displayed dozen are keyed here.
_POLYMARKET_BOARD = {
    # ── NWSL 美国女足大联盟 (Polymarket "W" 后缀) ──
    "Angel City W": "天使城女足",
    "Houston Dash W": "休斯顿冲刺女足",
    "North Carolina Courage W": "北卡罗来纳勇气女足",
    "Orlando Pride W": "奥兰多骄傲女足",
    "Portland Thorns W": "波特兰荆棘女足",
    "Racing Louisville W": "路易斯维尔竞技女足",
    "Seattle Reign FC W": "西雅图君临女足",
    "Washington Spirit W": "华盛顿精神女足",
    # ── 巴西联赛 ──
    "Ceara": "塞阿拉",
    "Goias": "戈亚斯",
    "São Bernardo": "圣贝尔纳多",
    "Vila Nova": "维拉诺瓦",
}
TEAM_NAME_ZH.update(_POLYMARKET_BOARD)

# 2026-07-05 — UEFA 资格赛第一轮 (UCL/UEL/UECL Q1, 07-09/10 开踢) 的小国冠军.
# 竞彩每年 7 月都列这批,占满「近期赛事 → 待开盘」;数量有界(48),不是全球
# 长尾,值得译. 键 = AF 精确拼写(含重音 č/ž/ë/ī/à) —— 前端先查 raw 名,
# 大小写/fold 兜底够不到带重音或 AF 变体拼法(如 "St Joseph S Fc"). 与
# _V12_W7_CUP_AND_VARIANTS 同类,单列一块便于每年更新.
_UEFA_QUALIFIERS_2026_07 = {
    "Alashkert": "阿拉什凯尔特",
    "Aluminij": "阿卢米尼",
    "Atlètic Club d'Escaldes": "埃斯卡尔德斯竞技",
    "Bohemians": "波希米亚人",
    "CSKA Sofia": "索非亚中央陆军",
    "Caernarfon Town": "卡纳芬镇",
    "Derry City": "德里城",
    "Dečić": "德契奇",
    "Dila": "迪拉戈里",
    "Dinamo Minsk": "明斯克迪纳摩",
    "Dinamo Tbilisi": "第比利斯迪纳摩",
    "Dinamo Tirana": "地拉那迪纳摩",
    "Europa": "欧罗巴",
    "FC Levadia Tallinn": "塔林利瓦迪亚",
    "FC Santa Coloma": "圣科洛马",
    "FK Liepaja": "利耶帕亚",
    "FK Sarajevo": "萨拉热窝",
    "FK Zalgiris Vilnius": "维尔纽斯萨尔吉里斯",
    "Glentoran": "格伦托兰",
    "HNK Hajduk Split": "哈伊杜克",
    "Hamrun Spartans": "哈姆伦斯巴达",
    "Hegelmann Litauen": "黑格尔曼",
    "Kalju Nomme": "诺姆卡尔尤",
    "Linfield": "林菲尔德",
    "Malisheva": "马利舍瓦",
    "Marsaxlokk": "马萨什洛克",
    "Milsami Orhei": "米尔萨米",
    "Mornar": "莫尔纳尔",
    "NSI Runavik": "鲁纳维克",
    "Paide": "派德",
    "Penybont": "佩尼邦特",
    "Petrovac": "佩特罗瓦茨",
    "Pyunik Yerevan": "埃里温普尼克",
    "Rīgas FS": "里加RFS",
    "Shkendija": "什肯迪亚",
    "Sileks": "锡莱克斯",
    "St Joseph S Fc": "圣约瑟夫",
    "Stjarnan": "斯坦纳恩",
    "US Mondorf-les-bains": "蒙多夫",
    "Universitatea Cluj": "克卢日大学",
    "Velež": "韦莱日",
    "Vestri": "韦斯特里",
    "Vikingur Gota": "戈塔维京",
    "Virtus": "维尔图斯",
    "Vllaznia Shkodër": "弗拉兹尼亚",
    "Vojvodina": "伏伊伏丁那",
    "Yelimay Semey": "塞梅耶利迈",
    "Žilina": "日利纳",
}
TEAM_NAME_ZH.update(_UEFA_QUALIFIERS_2026_07)

# ============ AF 真实拼法别名(2026-08-06)=============================
# `zh_to_canonical` 能吐出、但本词典没有**这个拼法的键**的英文名。它们**今天就是
# 显示 bug** —— 盘面/收盘线走 AF 原始拼法(`SC Freiburg` / `VfL Bochum` /
# `1. FC Köln`),而词典只有清洗过的短名(`Freiburg` / `Bochum` / `Koln`)
# ⇒ `lookup_zh` 原样返回英文,前端显示英文。
# 同源:`sporttery._EN_OVERRIDES`(词典短名 → AF 拼法)与 `_ZH_OVERRIDES`。
#
# ⚠️ 别把这一块读成「`nutmeg-harvest-team-zh` 打印的那个结构上限」——**不是同一个
#   口径**,原来这行注释写错了。工具的 `new_key_ceiling` 用的是**语义**尺子
#   (`KnownTeams`:精确键 / `_EN_OVERRIDES` 反查 / 折叠),而这 25 条全都是词典
#   **已有球队**的另一种拼法 ⇒ 工具在改动前后都打印「结构上限 0」(实测:摘掉本块
#   的 939 键词典 → 0,现状 964 键 → 0)。25 = **精确键**口径的 26 减掉故意不要的
#   `Kyoto Sanga FC`,而 `new_key_ceiling` 的 docstring 恰恰在反对精确键口径。
#   照旧注释去跑 CLI 的人,永远复现不出「25」。
#
# ⭐ 中文名**一个都不是音译猜的,也一个都不是竞彩写法** —— 全部逐字照抄词典里
#   同一支队的现有中文名(经 `_EN_OVERRIDES` 溯源、或大小写/去重音/法定形式记号
#   折叠后的兄弟键)。这一块全是**别名键**:取竞彩写法就会让同一支队因上游拼法
#   不同而显示成两个名字,正是要修的病。11 条有两个候选的逐条注在行尾(数过,不是估的)。
#
# 🚨 2026-08-06 返工修掉的两条(它们制造了自己声称要治的病):
#   · `Kyoto Sanga FC: 京都` —— 行尾原写「词典完全没有这支队」,**假的**,词典
#     521 行就有 `Kyoto Sanga: 京都不死鸟`。⇒ 同队两名。已**删除**:实测
#     `odds_snapshots` 里 `Kyoto Sanga FC` 出现 **0** 次(盘面只用 `Kyoto Sanga`),
#     所以这个键修不了任何显示,只会把一个**死的 join 目标**
#     (`sporttery._ZH_OVERRIDES['京都']`)伪装成活的,并且把 `_enTeamForSettle`
#     从 known=false 翻成 true —— 静默关掉手工记账的结算警告。
#   · `Almere City FC: 阿尔梅勒` —— 同样假(词典 407 行有 `Almere City: 阿尔梅勒城`),
#     但这个拼法**是活的**(odds_snapshots 里只用 `Almere City FC`)⇒ 保留键、
#     中文改成词典的「阿尔梅勒城」。
#
# ℹ️ 冗余度实测(2026-08-06 合入 main 后重测,拿 dashboard.html 里**真的**
#   `zhTeam`/`_zhFold` 跑,不是照着正则推):把本块整块摘掉后,前端靠折叠仍能给出
#   一模一样中文的有 **22/25** —— 真正必需的只有 3 条:`Estrela`(折成 Estrela 不在
#   词典)、`Guimaraes`(词典键是 `Vitoria Guimaraes`,折叠够不着)、`Stade Brestois 29`。
#   ⚠️ 分支上原写「23/25(本分支 17/25)」是**在分支的窄折叠表上量的**,合入 main
#   (2634234 扩宽了 `_zhFold` 的德/荷/比记号)后口径变了 —— 参照点变了,数字就得重量。
#   **仍然全部保留**,
#   因为还有一个**不折叠**的消费者:`cli/team_assets_check.py` 用
#   `name not in TEAM_NAME_ZH` 判「卡片会显示英文名」⇒ 删掉冗余键会让那个哨兵
#   对着显示正常的队报警(假红)。别按「前端折得出来」为由删。
_AF_SPELLING_ALIASES_2026_08: dict[str, str] = {
    "1. FC Heidenheim": "海登海姆",  # ← 词典 'Heidenheim'
    "1. FC Köln": "科隆",  # ← 词典 'Koln'
    "1. FC Nürnberg": "纽伦堡",  # ← 词典 'Nurnberg'
    "AD Ceuta FC": "休达",  # ← 词典 'Ceuta'
    "Almere City FC": "阿尔梅勒城",  # ← 词典 'Almere City';竞彩「阿尔梅勒」
    "Borussia Mönchengladbach": "门兴格拉德巴赫",  # ← 词典 'Borussia Monchengladbach';竞彩「门兴」
    "Estac Troyes": "特鲁瓦",  # ← 词典 'Troyes'
    "Estrela": "阿马多拉之星",  # ← 词典 'Estrela Amadora';竞彩「阿马多拉」
    "FC Augsburg": "奥格斯堡",  # ← 词典 'Augsburg'
    "FC Schalke 04": "沙尔克 04",  # ← 词典 'Schalke 04';竞彩「沙尔克04」
    "FC St. Pauli": "圣保利",  # ← 词典 'St. Pauli'
    "FSV Mainz 05": "美因茨",  # ← 词典 'Mainz 05'
    "Fortuna Düsseldorf": "杜塞尔多夫",  # ← 词典 'Fortuna Dusseldorf';竞彩「杜塞多夫」
    "GIL Vicente": "维森特",  # ← 词典 'Gil Vicente';竞彩「吉维森特」
    "GO Ahead Eagles": "前进之鹰",  # ← 词典 'Go Ahead Eagles'
    "Granada CF": "格拉纳达",  # ← 词典 'Granada'
    "Guimaraes": "吉马良斯",  # ← 词典 'Vitoria Guimaraes'
    "PAU": "波城",  # ← 词典 'Pau';竞彩「波城FC」
    "RED Star FC 93": "巴黎红星",  # ← 词典 'Red Star';竞彩「圣旺红星」
    "SC Freiburg": "弗赖堡",  # ← 词典 'Freiburg'
    "SV Darmstadt 98": "达姆施塔特",  # ← 词典 'Darmstadt';竞彩「达姆施塔」
    "SV Elversberg": "埃尔弗斯堡",  # ← 词典 'Elversberg';竞彩「埃沃斯堡」
    "Shimizu S-Pulse": "清水心跳",  # ← 词典 'Shimizu S-pulse';竞彩「清水鼓动」
    "Stade Brestois 29": "布雷斯特",  # ← 词典 'Brest'
    "VfL Bochum": "波鸿",  # ← 词典 'Bochum'
}
TEAM_NAME_ZH.update(_AF_SPELLING_ALIASES_2026_08)

# ============ 竞彩 vote-feed 收割(机器维护)===========================
# 由 `nutmeg-harvest-team-zh --apply` 整块重写(按键排序)。**别手改**,也别在下面
# 那两行标记之间加注释或语句 —— 整块重写只吐键值对,别的都会丢;工具因此在重写前
# **先检查块里有没有这类东西,有就拒写**(`harvest_team_zh.block_extras`)。
# (标记本身不在这段散文里出现:写侧按「独占一行且全文恰好一次」定位,
#  注释里再提一次会把块的起点挪到注释上。)
#
# 收的是 `jingcai_vote` 的 (home_team, home_zh) 对:中文名是竞彩官方写法,
# 英文名是 `sporttery.zh_to_canonical` 的输出。⚠️ 那个函数**是本词典的反转**
# (+ `_ZH_OVERRIDES` / `_EN_OVERRIDES`),所以能收进来的新条目有硬上限 ——
# 只有 `_EN_OVERRIDES` 的值和 `_ZH_OVERRIDES` 里指向词典外英文名的条目,而且还得是
# 词典**整支队都没有**的(盘面拼法 ≠ 新队:`SC Freiburg` 就是词典的 `Freiburg`)。
# CLI 每次跑都把这个上限**算出来打印**,别把「0 个新名字」读成「没得收」。
#
# 与词典冲突的条目(竞彩保留 FC/CF 后缀、我们剥掉)**永远不会**落到这里 ——
# 那是编辑口径选择,工具只打印,由人决定。
#
# 🚨 2026-08-06 返工:这里原来是 `TEAM_NAME_ZH.update(...)`,而它是**全文件最后
# 一次 update** ⇒ 机器块会盖住上面所有人工联赛块,而上一段注释偏偏叫人「手工条目
# 写进上面的块里」—— 那条订正路径是个 no-op,且 harvest 的 classify 会把这种覆盖
# 读成「一致」,工具还报健康。改成 `setdefault`:**人工永远赢**,和注释说的一致。
#
# ⚠️ 为什么是 setdefault 而不是「把这一块挪到人工块前面」:`TEAM_NAME_ZH` 的**插入
# 顺序**是 `sporttery._ZH_TO_EN` 的输入(那边按 setdefault 先到先得建 中文→英文
# 反查)。把机器块挪到最前面,机器条目就会抢下反查权 —— 那正是 07-04 / 08-05 两次
# 「别名遮蔽」事故的形状(行照写、join 永死)。setdefault 两个性质都要:人工赢,
# 且机器条目留在插入顺序的末尾。
#
# 注:这一块用 `dict[str, str]` 而非文件其余部分的 `Dict[str, str]` —— 后者会新增
# 一条 ruff UP006(存量 17 条不动,但新代码不许再添)。别「统一风格」改回去。
#: 解放者杯 + 沙职球队 —— 2026-08-09 用**比分锚定**产出,不是翻译。
#:
#: ## 来源
#: `scripts/anchor_team_names_by_score.py`。竞彩档案与 API-Football 各自独立记录了
#: 同一场比赛的**终场比分**;若某场竞彩比赛在它的北京日窗内、AF 那边恰好只有**一场**
#: 同比分的比赛,两条记录说的就是同一场 ⇒ 主队对主队、客队对客队。
#: **比分不是翻译,是事实。**
#:
#: ## 为什么必须这么绕
#: 常规做法是拿竞彩自己的英文列当锚 —— **那条路是死的**:决定性检验显示
#: `jingcai_odds_history.home_team` 是**我们自己词典的回流**,词典里没有的队那列 100% 为空
#: (解放者杯 43/43 空、沙职 18/18 空)。它是镜子不是锚。
#: 而本仓红线「绝不照英文猜译名」堵死了剩下那条路。
#:
#: ## 三道闸(全部宁缺勿错方向)
#: ① 唯一性:窗口内同比分候选恰好 1 场才用,多于 1 场直接丢(丢了 29+14 场)
#: ② 重复确认:一个中文名要被 ≥2 场独立比赛指向同一英文名;
#:    或(闸②′)同场对手已被独立确认 —— 需要被确认的是**这场比赛认对了没有**,
#:    不是每个名字各自被数够次数
#: ③ 零冲突:同一中文名被指向过两个不同英文名 ⇒ 整条作废,不做多数表决
#:
#: ## 验证(这批数据唯一的正确性证据)
#: · **对照组巴甲**(词典已完整、同为南美、同样的跨日时区):三闸产出 13 条,
#:   与词典 **13/13 一致、0 冲突**。闸②′ 单独验过:它救回的 6 条也全对。
#: · 本批产出里有 8 条中文名词典本来就有 ⇒ **8/8 一致、0 冲突**。
#: · 日窗偏移是**量出来的**不是推的:−1/0/+1 三档唯一命中 4/**29**/3,偏移 0 压倒性胜出
#:   (顺带证实 `close_date` 就是比赛的北京日期)。
#: ⇒ 合计 21 条有标准答案的样本,**零错**。
#:
#: ⭐ 几条**任何翻译法都必错**、只有比分锚拿得到的:
#:    `Barcelona SC → 瓜亚基尔`(厄瓜多尔的巴塞罗那,竞彩按城市叫)、
#:    `Junior → 巴兰基亚`、`UCV → 中央大学`、`Independiente Petrolero → 石油独立`。
#: ⚠️ `# ×N` = 被多少场**独立比赛**确认。N=1 的 8 条是靠闸②′ 同场传播进来的。
#: ⛔ 还有 2 条**故意没进来**:`玻利瓦尔 → Bolívar`、`里独立 → Independ. Rivadavia`
#:    —— 各只 1 次确认,且同场对手也没锚住。未映射横幅会继续点它们的名,**那是对的**。
_LIBERTADORES_SAUDI_2026_08: dict[str, str] = {
    # ── 解放者杯(南美)37 支 ────────────────────────────
    "Boca Juniors": "博卡",                   # ×8
    "River Plate": "河床",                    # ×8
    "Cerro Porteno": "波特诺",                 # ×7
    "Deportes Tolima": "托利马",               # ×6
    "Estudiantes L.P.": "拉普大学",             # ×6
    "Emelec": "埃梅莱克",                       # ×5
    "Always Ready": "时刻准备",                 # ×5
    "Sporting Cristal": "水晶体育",             # ×5
    "America Mineiro": "米美洲",               # ×5
    "Velez Sarsfield": "萨斯菲",               # ×5
    "Talleres Cordoba": "铁路工场",             # ×5
    "Libertad Asuncion": "亚自由",             # ×4
    "Fortaleza EC": "福塔雷萨",                 # ×4
    "Colon Santa Fe": "科隆竞技",               # ×4
    "Deportivo Cali": "卡利",                 # ×3
    "LDU de Quito": "基多体大",                 # ×3
    "U. Catolica": "天主大学",                  # ×3
    "Colo Colo": "科洛科洛",                    # ×3
    "Club Nacional": "蒙国民",                 # ×3
    "Olimpia": "亚奥林",                       # ×2
    "Penarol": "佩纳罗尔",                      # ×2
    "Deportivo Tachira FC": "塔奇拉",          # ×2
    "Cusco": "库斯科",                         # ×2
    "Independiente del Valle": "德尔瓦耶",      # ×2
    "Platense": "普拉滕斯",                     # ×2
    "The Strongest": "最强者",                 # ×2
    "Barcelona SC": "瓜亚基尔",                 # ×2
    "Independiente Petrolero": "石油独立",      # ×2
    "Rosario Central": "罗萨里奥",              # ×2
    "Alianza Lima": "利马联盟",                 # ×1
    "Caracas FC": "加拉加斯",                   # ×1
    "Santa Fe": "圣菲独立",                     # ×1
    "Independiente Medellin": "麦独立",        # ×1
    "UCV": "中央大学",                          # ×1
    "Universitario": "大学体育",                # ×1
    "Deportivo La Guaira": "拉瓜伊拉",          # ×1
    "Junior": "巴兰基亚",                       # ×1
    # ── 解放者杯 · 涓流补进来的旧场次(2026-08-11)────────────────
    # 走势档案当天从 124 → 131 场,带进两支没见过的队。锚定器把它们卡在闸②
    # (各只 1 次确认,且两队**在同一场**,同场传播互相救不了)。
    #
    # ⭐ 但这一场的闸① 是**最强形态**:2023-02-10(北京日)整个解放者杯
    #   **AF 只有 1 场比赛** —— `Boston River 3:1 Zamora FC`。
    #   闸② 防的是「1:0 这种比分常见、同日多场会撞车」,而这里**没有可撞的东西**:
    #   不是「同比分唯一」,是「那天该联赛唯一」。⇒ 按闸① 收,理由写在这里。
    # ⛔ 别把这条读成「闸② 可以绕」—— 它只在「当日该联赛唯一一场」时成立,
    #   而那个条件必须**去数**(我数了:1 场),不能因为「看起来只有一场」就假设。
    "Boston River": "波士顿河",
    "Zamora FC": "萨莫拉FC",
    # ── 欧冠资格赛(2026-08-11 横幅点名)────────────────────────
    # 竞彩把它写作「采列」。⭐ 锚是**开球时刻**:那天竞彩上架 8 场欧冠、7 场已解,
    # AF 有 10 场 ⇒ 未解那场缩到 3 个候选(17:00 / 18:00 / 18:15Z),
    # 而竞彩这条记的 `kickoff_utc` 是 **18:15Z** ⇒ 唯一命中 Celje–Ararat-Armenia。
    # ⛔ 不是因为「采列听起来像 Celje」—— 那是猜。
    "Celje": "采列",
    # ── 解放者杯 · **第二轮**消歧收的 4 支 ──────────────────────
    # 第一轮判它们「候选不唯一」而丢掉;拿到上面 46 个名字之后再问同一批数据,
    # 与已知名字不相容的候选被排除,只剩一个 ⇒ 这场被钉死,名字随之确定。
    # ⭐ 其中 `玻利瓦尔`/`里独立` 在第一轮的**弱候选**里就出现过同样的答案 ——
    #   两条独立路径给出同一个结果。`科金博联` 只有 1 次(对手已知锚住了这场)。
    "Lanus": "拉努斯",                         # ×2
    "Bolívar": "玻利瓦尔",                     # ×2
    "Independ. Rivadavia": "里独立",           # ×2
    "Coquimbo Unido": "科金博联",              # ×1
    # ── 解放者杯 · **第三轮**:闸②(≥2 次确认)对「档案里只出现一次」的队
    #    永远过不了 —— 那是**数据稀缺的产物,不是锚弱**(2026-08-11)。
    #
    # 这三支在 `jingcai_odds_history` 里各只有 1 场,所以工具报「只被确认 1 次」。
    # 逐条另找了三条独立证据,三条都指同一个答案才收:
    #
    # ① **北京日精确唯一**(不是 ±1 窗口)。竞彩 `close_date` 是北京日期:
    #    03-03 那天 AF 只有 `Millonarios 2:1 Universidad Catolica`(北京 03-03 08:00);
    #    另一场同为 2:1 的 `Medellin 2:1 El Nacional` 是北京 **03-02** ⇒ 不在同一天。
    #    ⚠️ 我一开始按 ±1 天看,误以为「两场 2:1、唯一性不成立」——
    #    窗口取宽了会把本来干净的锚看成脏的。
    # ② **排除法**:`麦独立 → Independiente Medellin` 已 ×1 在册且被同场对手锚住,
    #    ⇒ `百万富翁` 不可能也是 Medellin(否则一队两名,即「劈成两个 canonical」)。
    # ③ **一场同时钉两个**:该场次两侧互为佐证,不是两次独立的巧合。
    #
    # 🚨 `Universidad Catolica` 的撞车已单独查过:AF 用**两个不同写法** ——
    #    `U. Catolica` 出现在 Copa Chile / Primera División(智利那家),
    #    `Universidad Catolica` 出现在 Copa Ecuador / Liga Pro(厄瓜多尔那家)。
    #    竞彩写「**基多**天主」= Quito ⇒ 厄瓜多尔,与后者一致。两者不会混。
    #    ⛔ 若哪天 AF 把两家都写成同一串,这条必须重测,不许沿用。
    "Millonarios": "百万富翁",                 # ×1 + 证据①②③
    "Universidad Catolica": "基多天主",        # ×1 + 证据①③(厄瓜多尔那家)
    "FBC Melgar": "梅尔加",                    # ×1 同场传播(对手 Olimpia 已在册)
    # ── 沙职 18 支 ──────────────────────────────────────
    "Al-Nassr": "利雅胜利",                     # ×22
    "Al-Hilal Saudi FC": "利雅新月",            # ×21
    "Al-Ittihad FC": "吉达联合",                # ×20
    "Al-Qadisiyah FC": "胡巴卡德",              # ×18
    "Al-Ahli Jeddah": "吉达国民",               # ×17
    "NEOM": "新未来SC",                        # ×17
    "Damac": "达马克",                         # ×17
    "Al Shabab": "利雅青年",                    # ×16
    "Al-Fayha": "迈季宽广",                     # ×16
    "Al Taawon": "布赖合作",                    # ×15
    "Al Najma": "欧奈纳伊",                     # ×15
    "Al Okhdood": "奈季沟渠",                   # ×13
    "Al-Hazm": "拉斯决心",                      # ×13
    "Al Khaleej Saihat": "赛哈海湾",            # ×13
    "Al-Ettifaq": "达曼协定",                   # ×13
    "Al Kholood": "拉斯永恒",                   # ×11
    "Al-Fateh": "穆拜征服",                     # ×11
    "Al Riyadh": "利雅得",                     # ×10
}
TEAM_NAME_ZH.update(_LIBERTADORES_SAUDI_2026_08)


# HARVEST-BEGIN
_JINGCAI_VOTE_HARVEST: dict[str, str] = {
}
# HARVEST-END
for _harvest_en, _harvest_zh in _JINGCAI_VOTE_HARVEST.items():
    TEAM_NAME_ZH.setdefault(_harvest_en, _harvest_zh)



def lookup_zh(team_name: str) -> str:
    """Return Chinese name for a canonical team, else input unchanged.

    Parameters
    ----------
    team_name : str
        V4 canonical team name (output of ``to_v4_canonical_*`` family).

    Returns
    -------
    str
        Chinese name if registered, else the input string verbatim.
        Empty / None input returns empty string.

    Examples
    --------
    >>> lookup_zh("Arsenal")
    '阿森纳'
    >>> lookup_zh("Some Unknown FC")
    'Some Unknown FC'
    >>> lookup_zh("")
    ''
    """
    if not team_name:
        return ""
    return TEAM_NAME_ZH.get(team_name, team_name)


def coverage_by_league() -> Dict[str, int]:
    """Return per-league entry count (for diagnostics + tests).

    Includes alias variants (e.g. "Manchester City" + "Man City" both
    counted), so the entry count per league can exceed the strict
    20-team roster.
    """
    return {
        # P1-FE#2 — top-5 European
        "EPL":                     len(_EPL),
        "ESP_LA_LIGA":             len(_LA_LIGA),
        "ITA_SERIE_A":             len(_SERIE_A),
        "GER_BUNDESLIGA":          len(_BUNDESLIGA),
        "FRA_LIGUE_1":             len(_LIGUE_1),
        # P1-FE#7 — 9 additional trained leagues
        "ENG_CHAMPIONSHIP":        len(_CHAMPIONSHIP),
        "ESP_SEGUNDA_DIVISION":    len(_SEGUNDA),
        "ITA_SERIE_B":             len(_SERIE_B),
        "GER_2_BUNDESLIGA":        len(_2_BUNDESLIGA),
        "FRA_LIGUE_2":             len(_LIGUE_2),
        "NED_EREDIVISIE":          len(_EREDIVISIE),
        "PRT_PRIMEIRA_LIGA":       len(_PRIMEIRA),
        "BEL_PRO_LEAGUE":          len(_BEL_PRO),
        "JPN_J1":                  len(_JPN_J1),
        # V12 W0 — WC / EURO / Copa America
        "NATIONAL_TEAMS":          len(_NATIONAL_TEAMS),
        # V12 W7 — UEFA cup clubs + Euro nations + core-league API spelling
        # variants (not attributable to one of the 14 leagues).
        "CUP_AND_VARIANTS":        len(_V12_W7_CUP_AND_VARIANTS),
        # V12 W8 — market-mode expansion leagues (Nordic / APAC / Europe).
        "MARKET_MODE_NEW_LEAGUES": len(_V12_W8_NEW_LEAGUES),
        # 体检 Wave2 — 2026-27 roster diff additions (promoted/renamed clubs).
        "W2_2026_ROSTER":          len(_W2_2026_ROSTER_ADDITIONS),
        # 2026-07-05 — Polymarket 交叉校验看板 (NWSL 女足 + 巴西).
        "POLYMARKET_BOARD":        len(_POLYMARKET_BOARD),
        # 2026-07-05 — UEFA 资格赛第一轮小国冠军.
        "UEFA_QUALIFIERS":         len(_UEFA_QUALIFIERS_2026_07),
        # 2026-08-06 — AF 真实拼法别名(词典已有球队的另一种拼法,非 harvest 上限).
        "AF_SPELLING_ALIASES":     len(_AF_SPELLING_ALIASES_2026_08),
        # 2026-08-06 — 竞彩 vote-feed 收割(nutmeg-harvest-team-zh 维护).
        "JINGCAI_VOTE_HARVEST":    len(_JINGCAI_VOTE_HARVEST),
        # 2026-08-09 — 解放者杯 + 沙职,**比分锚定**产出(见上方长注释).
        "LIBERTADORES_SAUDI":      len(_LIBERTADORES_SAUDI_2026_08),
        "TOTAL":                   len(TEAM_NAME_ZH),
    }
