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
    "Slovan Bratislava": "布拉迪斯拉发斯洛万",
    "HJK Helsinki": "赫尔辛基HJK", "Kairat Almaty": "阿拉木图凯拉特",
    "FC Astana": "阿斯塔纳", "Sheriff Tiraspol": "蒂拉斯波尔治安官",
    "Shamrock Rovers": "三叶草流浪者", "The New Saints": "新圣徒",
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
    # ── 瑞士超 SUI_SUPER_LEAGUE ──
    "FC Aarau": "阿劳", "FC Luzern": "卢塞恩", "FC ST. Gallen": "圣加仑", "FC Sion": "锡永",
    "FC Thun": "图恩", "FC Winterthur": "温特图尔", "Grasshoppers": "草蜢", "Lausanne": "洛桑",
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
        "TOTAL":                   len(TEAM_NAME_ZH),
    }
