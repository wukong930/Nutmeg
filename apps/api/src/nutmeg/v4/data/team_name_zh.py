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
        "TOTAL":                   len(TEAM_NAME_ZH),
    }
