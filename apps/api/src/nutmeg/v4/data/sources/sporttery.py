"""中国体育彩票 (竞彩) odds source — the soft-book SP feed.

竞彩 publishes its frozen SP (胜平负/让球/比分/半全场) through a PUBLIC, no-auth
consumer JSON endpoint used by the official site/app:

    https://webapi.sporttery.cn/gateway/uniform/football/getMatchCalculatorV1.qry

This is the OTHER gateway route — the ``/gateway/jc/...`` one sits behind a
Tencent WAF (403 from any non-browser client), but ``/gateway/uniform/...`` is
served cleanly to plain HTTP clients, even from a foreign datacenter IP. No
cookie, no token, no WAF circumvention — we read the same public odds the app
shows everyone.

Used ONLY for personal, local, low-frequency analysis (the 竞彩 staleness map).
Read-only — never touches the user's betting account. FAIL-SOFT by design: any
network/parse/endpoint-change failure logs a warning and returns ``[]`` so a
broken scrape can never take down the rest of the pipeline. The endpoint is
undocumented and internal — treat a sudden empty/changed response as "they moved
it", not an error to crash on.
"""
from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH

log = logging.getLogger(__name__)

# ── WAF 熔断(2026-07-20,晚间高频窗上线的前置护栏)────────────────────────
# 端点是公开无认证的(没有账号可封),最坏情形 = 家庭 IP 被 WAF 临时 403/429。
# 一旦被拦,**继续按点撞墙**会把临时节流熬成长期黑名单 —— 所以见 403/429 就静音
# 6 小时(≈"安静的半天",次日 09:50/11:05 常规窗自然恢复)。
# ⚠️ 与 odds_api 的内存熔断不同:sporttery 抓取跑在**一次性 cron 进程**里,内存
# 状态出了进程就没了 —— 熔断必须落盘才跨进程有效。
_BREAKER_HOURS = 6.0
_BREAKER_FILE = "sporttery_breaker.json"


def _breaker_path(cache_dir: str | Path) -> Path:
    return Path(cache_dir) / _BREAKER_FILE


def breaker_remaining(cache_dir: str | Path) -> float:
    """熔断剩余秒数;0.0 = 关闭(允许请求)。文件损坏/缺失 → 0.0(fail-open)。"""
    try:
        raw = json.loads(_breaker_path(cache_dir).read_text(encoding="utf-8"))
        return max(0.0, float(raw.get("until", 0)) - time.time())
    except (OSError, ValueError, TypeError):
        return 0.0


def _trip_breaker(cache_dir: str | Path, status: int) -> None:
    p = _breaker_path(cache_dir)
    with contextlib.suppress(OSError):
        p.parent.mkdir(parents=True, exist_ok=True)
        _tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
        _tmp.write_text(json.dumps({
            "until": time.time() + _BREAKER_HOURS * 3600.0,
            "status": status,
            "tripped_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }), encoding="utf-8")
        _tmp.replace(p)
    log.warning(
        "sporttery WAF 熔断:HTTP %s → 静音 %.0f 小时(%s);"
        "这是限流/拦截信号,别绕过 —— 到点自然恢复",
        status, _BREAKER_HOURS, p)


def reset_breaker(cache_dir: str | Path) -> None:
    """手动关闭熔断(测试 / owner 确认拦截已解除时用)。"""
    with contextlib.suppress(OSError):
        _breaker_path(cache_dir).unlink(missing_ok=True)


_BASE = "https://webapi.sporttery.cn"
_ENDPOINT = "/gateway/uniform/football/getMatchCalculatorV1.qry"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.lottery.gov.cn/",
    "Origin": "https://www.lottery.gov.cn",
}
_DEFAULT_CACHE = "data/external/sporttery"

# 竞彩 中文全名 → our canonical (API-Football English) name, reversed from the
# display dict (740 entries → ~98% of 竞彩 teams). A few 竞彩-only names the dict
# lacks can be patched here; unmapped teams are skipped (logged) by the ingest.
_ZH_TO_EN: dict[str, str] = {}
for _en, _zh in TEAM_NAME_ZH.items():
    _ZH_TO_EN.setdefault(_zh, _en)
_ZH_OVERRIDES: dict[str, str] = {
    # 解放者杯 —— 竞彩的**简写**(2026-08-09,比分锚定产出)。这 5 支队词典里**有**,
    # 只是竞彩用了更短的写法 ⇒ 属于 ① 类:补 override,**不动** team_name_zh.py。
    # ⭐ 这 5 条本身就是锚定器的又一层背书:它在不知道词典内容的情况下,
    #   把「帕梅拉斯」认成了词典里写作「帕尔梅拉斯」的那支队。
    # 撞车检查:5 个中文名在 TEAM_NAME_ZH 值集合与本表里都没被别的队占用(0 冲突)。
    "帕梅拉斯": "Palmeiras",                  # ×17 · 词典写作「帕尔梅拉斯」
    "米竞技": "Atletico-MG",                 # ×10 · 词典写作「米内罗竞技」
    "巴竞技": "Atletico Paranaense",         # ×6 · 词典写作「巴拉纳竞技」
    "布拉干RB": "RB Bragantino",             # ×3 · 词典写作「布拉甘蒂诺」
    "弗鲁米嫩": "Fluminense",                 # ×3 · 词典写作「弗鲁米嫩塞」
    # 竞彩-only Chinese names absent from TEAM_NAME_ZH. value = the LIVE
    # odds_snapshots/gather name. Both paren widths — the 竞彩 feed is inconsistent.
    #
    # 欧冠资格赛 2026-08-04(面板报「竞彩在售、但没进盘面 2/7」)—— 这两支队
    # **词典里有**,只是竞彩用了另一种中文写法,所以属于 ① 类(补 override,
    # 不动 team_name_zh.py):
    #   Slovan Bratislava  → 词典写「布拉迪斯拉发斯洛万」,竞彩写「布拉迪斯拉发」
    #   Union St. Gilloise → 词典写「圣吉罗斯联」,      竞彩写「圣吉尔联合」
    # ⭐ 英文值**照抄 odds_snapshots 里那条线**(join 目标本身),不是按音译写的。
    #   注意是 `Union St. Gilloise`(带点)而**不是** `Union Saint-Gilloise` ——
    #   TEAM_NAME_ZH 两种都有,但实盘那条线用的是前者。
    # ⭐ 配对靠**赛事身份**不是猜:两场里已解析的那一侧(米亚尔比=Mjallby AIF /
    #   博德闪耀=Bodo/Glimt)在 2026-08-04 UCL 各只有**唯一**一个对手,
    #   对手就是这两个名字。撞车检查:两个中文名在 TEAM_NAME_ZH / _ZH_OVERRIDES /
    #   竞彩档案 / 皇冠档案里**都没被别的队占用**(0 冲突)。
    # ✅ 同时确认过这不是「Pinnacle 没覆盖资格赛」那种情况 —— 两场的 psc 都在
    #   odds_snapshots 里(08-04 03:24Z 抓取,2.08/3.62/3.18 与 2.07/3.8/3.08),
    #   所以补词典**确实能让它们进盘面**。
    # 葡超 2026-08-08(横幅报「队名解不出 2/52」)—— 同样是 ① 类:
    #   Academico Viseu → 词典写「维塞乌学院」,竞彩写「维塞乌」
    #   Nacional        → 词典写「纳西奥纳」,  竞彩写「葡萄牙国民」
    # ⭐ 英文值取自**两条独立锚且一致**:服务端下发的赛程(Benfica vs Academico Viseu /
    #   Santa Clara vs Nacional)与 odds_snapshots(各 11 行)。不是按译音写的。
    #   ⚠️ odds_api 侧还有「Académico de Viseu」带重音的写法,**没用它** ——
    #   join 目标必须是盘面 `_gather_rows` 真在用的那个拼法。
    # ⭐ 撞车检查:两个中文名在 TEAM_NAME_ZH / _ZH_OVERRIDES 里都没被别的队占用(0 冲突);
    #   两个英文值在 odds_snapshots 各出现 11 次(「值必须在盘面出现过」那条断言)。
    # 📌 顺带记一笔(不改,零影响):TEAM_NAME_ZH 里 `AVS Viseu → 维塞乌学院` 是第三个
    #   指向同一中文的键,而 AVS 是另一家俱乐部(Vila das Aves)。它在 odds_snapshots
    #   里从没出现过,反转也没选中它(`zh_to_canonical('维塞乌学院') == 'Academico Viseu'`),
    #   所以是**惰性**的。哪天 AVS 真上盘面,它会变成一条静默死 join。
    "维塞乌": "Academico Viseu",
    "葡萄牙国民": "Nacional",
    "布拉迪斯拉发": "Slovan Bratislava",
    "圣吉尔联合": "Union St. Gilloise",
    "刚果(金)": "Congo DR",
    "刚果（金）": "Congo DR",
    # 2026-08-07 面板报「竞彩在售、但没进盘面 6/39」。查完 12 支队,**没有一支
    # 缺在 team_name_zh.py** —— 全是竞彩换了另一种中文写法,所以整批都是 ① 类。
    # ⭐ 英文值照抄 odds_snapshots 里那条线(join 目标本身),配对靠**赛事身份**:
    #   长崎航海    ← 2026-08-09 JPN_J1 `V-varen Nagasaki vs Kyoto Sanga`,
    #                 锚=京都不死鸟(已解析),当日 J1 唯一以它为客的场次。
    #                 主词典写「V法伦长崎」。
    #   PSV埃因霍温 ← 2026-08-08 NED_EREDIVISIE `PSV Eindhoven vs Fortuna Sittard`。
    #   福图纳锡塔德 ↑ 同一场。这场两侧都没解析,靠**排除法**定的:当日荷甲 4 场,
    #                 另 3 场(AZ/ADO、前进之鹰/威廉二世、奈梅亨/特尔斯达)两侧
    #                 都已在词典、都进了盘面,只剩这一场。主词典写「埃因霍温」「锡塔德」。
    #   里斯本竞技  ← 2026-08-08 PRT_PRIMEIRA_LIGA `Estrela vs Sporting CP`,
    #                 锚=阿马多拉(本表已有 → Estrela)。主词典写「葡萄牙体育」。
    #                 ⚠️ 别和 `Sporting`/`Sporting Gijon`→希洪竞技 搞混,是不同队。
    #   德累斯顿    ← 2026-08-09 GER_2_BUNDESLIGA `1. FC Nürnberg vs Dynamo Dresden`,
    #                 锚=纽伦堡(已解析)。主词典写「德累斯顿迪纳摩」。
    # 撞车检查:这 5 个中文名在 TEAM_NAME_ZH 值集合与本表里都没被别的队占用(0 冲突)。
    #
    # ── 日乙两条(2026-08-08 补)。⚠️ 我上一版在这里写了三条「故意不补」的理由,
    #    2026-08-07 逐条实测,**三条全部不成立**。留着原文当反面教材:
    #
    #   ❌①「JPN_J2 在 odds_snapshots 历史总行数 = 0 ⇒ Pinnacle 不覆盖」
    #      —— 行数对,因果错。该表最早一行 = 2026-06-10,而 J2 赛季 06-07 打完、
    #      08-08 才重开 ⇒ **采集窗口与休赛期完全错开**,0 行被时间窗解释干净。
    #      本地 AF 赔率缓存里 league_id=99 有 22 条,**22/22 带 Pinnacle**。
    #      ⭐ 通用教训:**采集窗口比对象生命周期短时,「总行数 0」和「不存在」
    #      长得一模一样** —— 同族见 curl-404 伪装成空结果 / 「零新增 ≠ 扫完了」。
    #   ❌②「补了也进不了盘面 —— 没有 psc 就算不出 EV」
    #      —— 缺 Odds API sport_key 不封死:荷乙 `NED_EERSTE_DIVISIE` 同样
    #      `SPORT_KEYS→None`(odds_api.py:158-163 还拿 JPN_J2 当先例),却靠
    #      **AF 的 Pinnacle 镜像**拿到了 53 行。而且这两场根本没被丢弃 ——
    #      实测 `/predictions/cup-market` 里 10 场日乙**全在**「待开盘」。
    #   ❌③「栃木城有真歧义」—— 库内有锚,只是我没去 AF fixture 缓存找:
    #      fixture 1606605 = `Montedio Yamagata vs Tochigi City` 2026-08-09,
    #      日期/主队/联赛三项全对上;且 2026 J2 的 20 队含 Tochigi City、
    #      **不含 Tochigi SC**。(按赛季成立,不是全局别名。)
    #      ⚠️ 还有:我原文写的「栃木城」(栃 U+6803)**竞彩数据里根本不存在**,
    #      实盘 feed 写的是「枥木城」(枥 U+67A5)。所以只补 feed 里真实出现的那个。
    #
    #   真实成因 = **上游 AF 此刻不给日乙赛前赔率**(实拉 fixture 1606596@19.1h
    #   / 1606601@23.3h 均 0 条;阳性对照 J1 fixture 1554007@46.3h 得 14 家含
    #   Pinnacle;同窗口跨联赛 J2 0/10 而其余 14 个联赛 100%)。补词典解决的是
    #   **竞彩 SP 挂得上挂不上**,与赔率有无是两条独立的链。
    #
    #   锚(都不是猜的):
    #   大宫松鼠RB  ← AF fixture 1606601 `Omiya Ardija vs Albirex Niigata`
    #                 2026-08-08,对手侧 新潟天鹅→Albirex Niigata 已解析;
    #                 且竞彩 feed 自带的 AbbName 就是「大宫松鼠」(主词典能解)。
    #                 主词典写「大宫松鼠」,竞彩 2026 赛季起加了 RB 后缀
    #                 (红牛收购;竞彩自己的档案到 2025-12-07 都还写不带 RB 的)。
    #   枥木城      ← AF fixture 1606605(见上)。主词典写「枥木城市」,
    #                 竞彩这个是去掉「市」的短写法。
    "大宫松鼠RB": "Omiya Ardija",
    "枥木城": "Tochigi City",
    "长崎航海": "V-varen Nagasaki",
    "PSV埃因霍温": "PSV Eindhoven",
    "福图纳锡塔德": "Fortuna Sittard",
    "里斯本竞技": "Sporting CP",
    "德累斯顿": "Dynamo Dresden",
    # 芬超 Veikkausliiga — 竞彩 uses descriptive 中文 (坦佩雷山猫=Tampere Lynx=Ilves,
    # 赫尔辛基火花=Helsinki Spark=Gnistan) that TEAM_NAME_ZH lacks. Aligned to the live
    # 市场模式 (cup-market) gather name by pairing each 竞彩 match to its fixture
    # (体检 2026-06-13) so the 竞彩 SP pre-fills. 芬超 is market-mode (no model).
    "坦佩雷山猫": "Ilves",
    "TPS图尔库": "Turku PS",
    "国际图尔库": "Inter Turku",
    "AC奥卢": "AC Oulu",
    "赫尔辛基": "HJK Helsinki",
    "赫尔辛基火花": "Gnistan",
    # 韩职 K League 1 — 竞彩 word order / renames TEAM_NAME_ZH lacks. Aligned to
    # the live gather (KOR_K_LEAGUE_1 fixtures 2026-07-04/05, 体检 2026-07-03):
    # these 6 unmapped sides silently dropped ALL 6 on-sale 韩职 matches (the
    # already-mapped 浦项/全北/蔚山… made every pair half-broken). NB 济州SK is
    # the club's rename; API-Football still lists it as Jeju United FC.
    "安养FC": "FC Anyang",
    "富川FC": "Bucheon FC 1995",
    "江原FC": "Gangwon FC",
    "首尔FC": "FC Seoul",
    "光州FC": "Gwangju FC",
    "济州SK": "Jeju United FC",
    # 巴甲 + 美职(2026-07-25 owner 实报,哨兵同时点名 2/31)。三个都**不是**「整队
    # 不在字典」,而是竞彩换了写法 —— 字典里分别是 国际 / 圣地亚哥FC / 达拉斯,
    # 竞彩写 巴西国际(加国别前缀,大概为了和 国际米兰 区分)/ 圣迭戈FC(译名不同)/
    # 达拉斯FC(加 FC 后缀)。所以修在这里,不动 team_name_zh.py。
    # EN 值全部照抄 odds_snapshots 里已有的那条线(join 目标本身),按「同日 + 已确认
    # 对手当锚」验过:2026-07-25 Atletico Paranaense vs Internacional(KO 21:30Z)、
    # 2026-07-26 San Diego vs FC Dallas(KO 01:30Z)。半角 FC(U+0046 U+0043),
    # 非全角 —— 已查码点,没踩 刚果(金) 那个双宽坑。
    # ⚠️ San Diego 在库里有两种拼写:gather 侧 `San Diego`、closing/OA 侧
    # `San Diego FC`。这里取 gather 名(卡片和主 join 走它);closing 那条线靠
    # _club_core 兜底(fc 是 token,两边都折成 sandiego)—— 2026-07-23 加的。
    "巴西国际": "Internacional",
    "圣迭戈FC": "San Diego",
    "达拉斯FC": "FC Dallas",
    # 瑞超 Allsvenskan — 竞彩 2026-07-04 上架 7 场,6 场因竞彩中文拼法≠字典键而
    # 整对静默丢弃(哈尔姆斯塔德≠哈尔姆斯塔、AIK索尔纳≠索尔纳AIK 词序、IFK哥德堡
    # ≠哥德堡、哥德堡盖斯≠哥德堡GAIS,余者缺竞彩写法)。半联赛丢失不触发整联赛
    # 报警(Elfsborg 场活着)= 「半坏」盲区实锤。EN 值逐一对 AF SWE_ALLSVENSKAN
    # 2026 队表验证(live diff 2026-07-04)。
    "哈尔姆斯塔德": "Halmstad",
    "代格福什": "Degerfors IF",
    "厄尔格里特": "Orgryte IS",
    "IFK哥德堡": "IFK Goteborg",
    "AIK索尔纳": "AIK Stockholm",
    "赫根": "BK Hacken",
    "佐加顿斯": "Djurgardens IF",
    "布鲁马波卡纳": "IF Brommapojkarna",
    "哥德堡盖斯": "Gais",
    # 挪超 NOR_ELITESERIEN 2026-07-11 — 竞彩用传统译名,TEAM_NAME_ZH 用音译 →
    # 4/8 在售挪超场因主/客中文名≠字典键整对静默丢弃(腓特烈斯塔≠弗雷德里克斯塔、
    # 奥勒松≠阿勒松、斯达≠斯塔特、桑纳菲尤尔≠桑德菲尤尔、汉坎≠哈马卡姆;特罗姆瑟/
    # 瓦勒伦加/莫尔德/布兰… 已映射,半联赛丢失不触发整联赛报警 = 又一「半坏」盲区)。
    # owner 实报「腓特烈 vs 利勒斯特 20:00 不在可投注列表」。EN 值 = TEAM_NAME_ZH 既有
    # 规范键,逐一对竞彩英文 abbr(FRD/AAE/STR/SJD/HKM)核对(live diff 2026-07-11)。
    # 第 5 个复现「词典即开关」的联赛(韩职/瑞超/UCL-Q/UEL-Q 之后)。
    "腓特烈斯塔": "Fredrikstad",
    "奥勒松": "Aalesund",
    "斯达": "Start",
    "桑纳菲尤尔": "Sandefjord",
    "汉坎": "Ham-Kam",
    # 欧冠资格赛 UCL Q1 2026-07-07 — 竞彩上架 3 场,2 场因竞彩中文名≠字典键整对静默
    # 丢弃(克拉克斯维克/萨巴赫/新圣徒已映射,余 3 队缺)。EN 值逐一对 odds_snapshots
    # 的 UCL 拼写验证(Pinnacle 已有全部 3 场线,live diff 2026-07-07)。
    "比森阿泰尔": "Atert Bissen",
    "雷克雅未克维京人": "Vikingur Reykjavik",
    "杰尔": "Gyori ETO FC",
    # NB UCL Q2 2026-07-21 的 奥莫尼亚 **不在这里** —— 那队是整队缺席 TEAM_NAME_ZH,
    # 补进显示字典即可(反转自动给出 ZH→EN),放这里反而只修 join、不修显示。
    # 本表的契约始终是:**仅**收 TEAM_NAME_ZH 已有该队、但竞彩另用一种中文写法的情况。
    # 欧联资格赛 UEL Q1 2026-07-09 — 竞彩上架 2 场,主队中文名≠字典键 → 整场静默丢弃
    # (客队 德里城/日利纳 已映射):🎯 刷新 unmapped=2,jingcai_sp 只剩数小时前的
    # market_mode 旧行,面板 SP 与官网对不上(owner 实报)。EN 值 = 库内 AF gather 名
    # (jingcai_sp market_mode 行 + cup-market 端点同名,live diff 2026-07-09)。
    "索菲亚中央陆军": "CSKA Sofia",
    "斯普利特海杜克": "HNK Hajduk Split",
    # 美职联 USA_MLS 2026-07-14 — 注册当天竞彩上架 4 场,2 场整对静默丢弃。两个病因:
    # (a) 竞彩保留拉丁后缀(蒙特利尔CF/多伦多FC),TEAM_NAME_ZH 却砍掉了(蒙特利尔/
    # 多伦多)—— 且我们自己不一致(洛杉矶FC/圣地亚哥FC 保留了后缀);(b) 波特兰竞彩
    # 写「伐木工」,我们写「伐木者」(一字之差)。owner 实报「竞彩 4 场只显示 2 场」。
    # 第 6 个复现「词典即开关」的联赛(韩职/瑞超/UCL-Q/UEL-Q/挪超之后)。
    # ⚠ 但这次的教训不是「哨兵瞎」——哨兵响了:logs/sporttery_unmapped_latest.txt
    # 11:43 已写「过半丢失: 美职 2/4」并精确点名这 3 个名字,比 owner 人肉发现早几小时。
    # 真缺口 = 可见性:告警只走易逝桌面推送(无头 launchd 看不见)+ 一个只有
    # health_check.sh 才读的文件,面板上看不到 → owner 只能靠比对竞彩 App 才发现。
    # 修这类问题请先读那个报告文件,别再造第二个检测器。
    # EN 值 = live cup-market gather 名(逐一对上, live diff 2026-07-15)。
    # ⚠ 只补已在竞彩实见的 3 个;其余 26 支 MLS 队的竞彩写法从未见过(纽约城/奥兰多城/
    # 纳什维尔/明尼苏达联… 都可能带 FC/SC 后缀)= 同类雷仍埋着。按本文件既有铁律
    # 「绝不瞎猜」不臆造拼法 —— 靠上面那份报告在它们上架当天点名,再照抄补进来。
    "蒙特利尔CF": "CF Montreal",
    "多伦多FC": "Toronto FC",
    "波特兰伐木工": "Portland Timbers",
    # 2026-07-21 兑现「上架当天照抄」:皇家盐湖城 词序颠倒 —— 竞彩「皇家盐湖城」
    # vs 字典「盐湖城皇家」(Real Salt Lake 已在 TEAM_NAME_ZH,只是词序≠),整对丢
    # (主队 Los Angeles FC 通=半坏)。EN 值 = odds_snapshots 铁证 USA_MLS 2026-07-23
    # 'Los Angeles FC' vs 'Real Salt Lake'。
    "皇家盐湖城": "Real Salt Lake",
    # 巴甲 BRA_SERIE_A 2026-07-16 — 上面那条 MLS 注释预言的姊妹雷,如期而至(两个
    # 联赛同在 07-14 注册,zh 字典写的都是「标准媒体译名」而非竞彩实际拼法)。
    # 竞彩上架 20 场丢 1 场,两个病因还是 MLS 那两个的合体:(a) 后缀词序——竞彩
    # 写「布拉干蒂诺RB」,我们写「布拉甘蒂诺」把 RB 砍了;(b) 一字之差——干 vs 甘。
    # 弗鲁米嫩塞 本就映射得上 → 一队断=整场丢(哨兵报告列整场是这个意思,不是两队都断);
    # 单场丢不触发整联赛/过半报警 = 又一例「半坏」盲区,靠 unmapped 报告点名才可见。
    # EN 值 = 实盘 gather 名,odds_snapshots 铁证:BRA_SERIE_A 2026-07-17
    # 'Fluminense' vs 'RB Bragantino',Pinnacle 线 1.95 已在库 → 补上即能算 EV。
    # 第 7 个复现「词典即开关」的联赛(韩职/瑞超/UCL-Q/UEL-Q/挪超/美职联之后)。
    # ⚠ 其余 19 支巴甲队(米内罗竞技/瓦斯科达伽马/沙佩科恩斯…)的竞彩写法仍未实见
    # = 同类雷继续埋着。同 MLS:不臆造拼法,等报告在它们上架当天点名再照抄。
    "布拉干蒂诺RB": "RB Bragantino",
    # 2026-07-21 兑现「上架当天照抄」:里莫 音译一字差 —— 竞彩「里莫」vs 字典「雷莫」
    # (Remo 已在 TEAM_NAME_ZH,里≠雷,同「干 vs 甘」型),整对丢(主队 Corinthians
    # 通=半坏)。EN 值 = odds_snapshots 铁证 BRA_SERIE_A 2026-07-23
    # 'Corinthians' vs 'Remo'。
    "里莫": "Remo",
    # ── 竞彩历史回填 name-join(2026-07-09)──— getFixedBonus/getUniformMatchResult 用
    # 缩写中文名(巴萨/皇马…),TEAM_NAME_ZH 里没有 → 补 13 受训联赛缺口。value = AF/canonical
    # EN(对齐 odds_snapshots)。genuinely 拿不准的(布城/里斯本/阿维SAD)故意留空 = 可见缺口
    # 待 Phase-2 coverage-audit 校对,绝不瞎猜(错映射=静默污染 join)。`记忆
    # jingcai-fixedbonus-history-endpoint` §H.2。
    # 西甲
    "巴萨": "Barcelona", "皇马": "Real Madrid", "马竞": "Atletico Madrid",
    "比利亚雷": "Villarreal", "巴伦西亚": "Valencia", "巴利亚多": "Valladolid",
    "拉帕马斯": "Las Palmas", "贝蒂斯": "Real Betis",
    # 英超
    "莱切斯特": "Leicester", "南安普敦": "Southampton", "诺丁汉": "Nottingham Forest",
    "维拉": "Aston Villa", "布赖顿": "Brighton", "布伦特": "Brentford",
    "西汉姆联": "West Ham", "伊普斯": "Ipswich",
    # 英冠
    "加的夫城": "Cardiff", "女王巡游": "QPR", "朴次茅斯": "Portsmouth",
    "米堡": "Middlesbrough", "西布罗姆": "West Brom", "谢周三": "Sheffield Wednesday",
    "谢菲联": "Sheffield Utd",
    # 德甲
    "拜仁": "Bayern München", "门兴": "Borussia Mönchengladbach", "沃夫斯堡": "VfL Wolfsburg",
    "不来梅": "Werder Bremen", "基尔": "Holstein Kiel", "莱红牛": "RB Leipzig",
    # 德乙
    "沙尔克04": "FC Schalke 04", "凯泽": "1. FC Kaiserslautern", "卡斯鲁厄": "Karlsruher SC",
    "不伦瑞克": "Eintracht Braunschweig", "达姆施塔": "SV Darmstadt 98",
    "埃沃斯堡": "SV Elversberg", "杜塞多夫": "Fortuna Düsseldorf", "汉诺威96": "Hannover 96",
    # 法甲/法乙
    "巴黎圣曼": "Paris Saint Germain", "斯特拉斯": "Strasbourg", "巴黎FC": "Paris FC",
    "圣旺红星": "RED Star FC 93", "波城FC": "PAU", "拉瓦勒": "Laval",
    "格勒诺布": "Grenoble", "阿纳西": "Annecy",
    # 荷甲
    "乌德勒支": "Utrecht", "阿尔克马": "AZ Alkmaar", "鹿斯巴达": "Sparta Rotterdam",
    "阿尔梅勒": "Almere City FC", "福图纳": "Fortuna Sittard", "赫拉克勒": "Heracles",
    # 2026-08-06 —— 告警「竞彩在售、但没进盘面」逮到:竞彩把 Excelsior 写作「SBV精英」,
    # 词典里这支队已有条目(`Excelsior: 鹿特丹精英`)⇒ 这是**只换了中文写法**,属 ① 类,
    # 只补这里、**不动 team_name_zh.py**(卡片继续显示「鹿特丹精英」)。
    # 英文键不是按译音猜的:拿能解析的对手 `坎布尔→Cambuur` 当锚,在 odds_snapshots 里
    # 2026-08-07 18:00 NED_EREDIVISIE 唯一命中 `Cambuur vs Excelsior`,主客顺序也对上。
    "SBV精英": "Excelsior",
    # 葡超
    "博阿维斯": "Boavista", "吉维森特": "GIL Vicente", "埃斯托里": "Estoril",
    "摩雷伦斯": "Moreirense", "法伦斯": "Farense", "葡国民": "Nacional",
    "里奥阿维": "Rio Ave", "阿马多拉": "Estrela",
    # 日职
    # ⚠️ 京都:2026-08-06 更正 `Kyoto Sanga FC` → `Kyoto Sanga`。原值把同一家俱乐部
    # **劈成两半** —— `TEAM_NAME_ZH` 早有 `Kyoto Sanga: 京都不死鸟`(= 盘面名),而这里
    # 的竞彩短名解到一个**盘面上不存在**的拼法:v4_observation.db 四张表
    # (odds_snapshots / match_outcomes / single_predictions / polymarket_gaps)
    # 只出现 `Kyoto Sanga`,`Kyoto Sanga FC` 出现 **0 次**。join 走的是精确
    # canonical EN(见 `jingcai_sp` DDL 注释「(home_team, away_team, 日期±1)」),
    # 竞彩路径上没有任何一层会剥 `FC`(`clv_ledger._norm` 只折大小写+重音,
    # `resolve_serving_name` 的 `_affix_core` 只在模型 serving 用)⇒ 原值写得进库、
    # 永远配不上,且不报错。
    #
    # 新值是**推**出来的,不是猜的(复用本文件 500-档案块那套 kickoff+已确认对手锚):
    # 2026-05-30 竞彩侧「京都 vs 柏太阳神」↔ 盘面 JPN_J1「Kyoto Sanga vs Kashiwa Reysol」;
    # 2026-06-06 「柏太阳神 vs 京都」↔「Kashiwa Reysol vs Kyoto Sanga」。柏太阳神 走
    # TEAM_NAME_ZH(不经本表)⇒ 锚独立;当日 J1 各只此一场含该对手 ⇒ 0 歧义。
    #
    # ⭐ 陷阱记一笔:`jingcai_odds_history`(657 行)和 `crown_close_history`(21 行)里
    # 满屏 `Kyoto Sanga FC`,看着像铁证 —— 但那两列的定义就是 `zh_to_canonical(*_zh)`,
    # 是**本词典自己的回流**,不是上游证据(同 [[jingcai-vote-en-side-is-our-own-dict]])。
    # 真正的独立闭源侧是 `pinnacle_close_history`,它写的是第三种拼法
    # `Kyoto Purple Sanga`(Odds-API 原名,10 行)—— 印证 MLS 块那句「gather 与 closing
    # 拼法不一致」,同时说明**三个拼法里原值哪个都不是**。本表按块契约取 gather 侧。
    "东京FC": "FC Tokyo", "京都": "Kyoto Sanga", "名古屋鲸": "Nagoya Grampus",
    "新泻天鹅": "Albirex Niigata", "札幌冈萨": "Consadole Sapporo", "横滨FC": "Yokohama FC",
    "清水鼓动": "Shimizu S-Pulse", "町田泽维": "Machida Zelvia", "神户胜利": "Vissel Kobe",
    "鸟栖沙岩": "Sagan Tosu",

    # ── 2026-07-15 · 500 档案(`crown_close_history`)的中文变体 ─────────────────
    # 为什么单独一块:500 和 竞彩 对同一支队用**不同的中文写法**,500 更爱截断
    # (500「TPS图尔」vs 竞彩「TPS图尔库」、500「国际图尔」vs 竞彩「国际图尔库」——
    # 上面那两个竞彩写法早就在了)。`crown_close_history` 的 ingest 直接把 500 的名字
    # 喂进 zh_to_canonical → 解不出就整场落空 → CLV 侧 join 静默漏配。
    #
    # ⭐ **这 17 条是【推】出来的,不是猜的**(2026-07-15,同 [[cross-source-team-name-mismatch]]
    # 的「measured alias table」处方):对每个解不出的 500 名字,找**同一 kickoff_utc**
    # 且**对手已解析且与 jingcai_sp 一致**的那场 → 主队即得。一支队同一时刻不可能踢两场,
    # 所以不存在误配空间;实跑 17 个唯一解、**0 歧义**。
    # ⚠️ 以后补这里,请复用这个推法(`kickoff_utc` + 已确认对手当锚),**别模糊匹配**
    # (difflib 会把 Club Brugge 配成 Cercle Brugge —— 那是另一家俱乐部)。
    "TPS图尔": "Turku PS",              # 竞彩写「TPS图尔库」
    "国际图尔": "Inter Turku",           # 竞彩写「国际图尔库」
    "塞伊奈": "SJK",
    # 瑞超
    "哈尔姆斯": "Halmstad",
    "索尔纳": "AIK Stockholm",           # AIK 主场在 Solna,500 用地名
    "厄格里特": "Orgryte IS",
    "埃夫斯堡": "IF Elfsborg",
    "布鲁马波": "IF Brommapojkarna",
    # 挪超
    "克里斯蒂": "Kristiansund BK",
    "奥斯KFUM": "KFUM Oslo",
    "桑纳菲": "Sandefjord",
    "萨普斯堡": "Sarpsborg 08 FF",
    # 欧战 / 国家队(顺带捞到的,同一推法)
    "索陆军": "CSKA Sofia",              # 索非亚陆军
    "斯海杜克": "HNK Hajduk Split",
    "克拉克斯": "KI Klaksvik",
    "阿拉木图": "Kairat Almaty",
    "乌兹别克": "Uzbekistan",
    # ── 美职 USA_MLS(2026-07-31)—— 竞彩用**短名**,TEAM_NAME_ZH 存的是全称音译
    # (竞彩「华盛顿」vs 词典「华盛顿联」)。整队都在词典里 ⇒ 情形①,只补这里,
    # 不动 team_name_zh.py(卡片仍显示词典的中文,不会退化成英文名)。
    #
    # ⚠️ **每一条都是「赛事身份」钉出来的,没有一条是按音译猜的**(红线:错映射是
    # 静默污染,比缺映射更坏)。两种证据:
    #   ① 比分硬闸 —— 竞彩档案的 (日期±1 + 主客比分完全一致) 唯一命中 API-Football
    #      的 MLS fixture,读它的英文名。方法本身用**对照组验证过**:同一把尺子把
    #      已知的「洛杉矶FC→Los Angeles FC」「蒙特利尔→CF Montreal」原样重现。
    #   ② 今日赛事 —— 「夏洛特FC」:2026-08-02T00:30 芝加哥火焰(=Chicago Fire,
    #      词典已有)当天的对手在 odds_snapshots 里唯一 = Charlotte。
    # 值一律取 **cup_market(gather)侧的拼法** —— 逐条查过 odds_snapshots,各 50–72
    # 条快照佐证。⚠️ 别用 closing 源的拼法:同一支队两个上游不一致(Charlotte /
    # Charlotte FC、Seattle Sounders / …FC、Inter Miami / …CF 等 10 组),而盘面走 gather。
    "夏洛特FC": "Charlotte",
    "华盛顿": "DC United",
    "圣何塞": "San Jose Earthquakes",
    "波特兰": "Portland Timbers",
    "西雅图": "Seattle Sounders",
    "费城": "Philadelphia Union",
    "迈国际": "Inter Miami",
    # ⛔ 另有 13 个竞彩短名(亚特联/休斯敦/哥伦布/圣路易城/堪萨斯城/奥兰多/奥斯汀FC/
    # 新英格兰/明尼苏达/洛城银河/温哥华/盐湖城/芝加哥)**故意留空**:本地拿不到
    # 2025-08→2026-04 的 MLS fixture(缓存只到 2026-05),比分硬闸配不上 ⇒ 无证据。
    # 它们只出现在**历史档案**里(今日实时 33/34 已能映射),补它们只影响档案可 join 性。
    # 要补须先拉那段 MLS fixtures(花 API-Football 额度),**不许按音译补**。
}
_ZH_TO_EN.update(_ZH_OVERRIDES)

# TEAM_NAME_ZH's English keys don't all match the LIVE convention odds_snapshots /
# the frontend use (API-Football names), so a few 竞彩 rows wouldn't join the
# Pinnacle line + settler. Correct the measured synonym gaps (体检 2026-06-12,
# diffed against the live name universe). Extend when a new 竞彩 row reports
# no_close despite a played match.
_EN_OVERRIDES: dict[str, str] = {
    # National teams (WC) — TEAM_NAME_ZH's English came from the elo source, which
    # names them differently from the live WC gather.
    "Korea Republic": "South Korea",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
    "Cape Verde": "Cape Verde Islands",
    "Turkey": "Türkiye",
    # Club leagues — the gather stores RAW API-Football names (club prefixes /
    # accents / abbreviations); sporttery's reverse-map output is the cleaned
    # form. Pre-validated against fetch_teams_for_league_season over the top-5 +
    # 英冠/葡超 (体检 2026-06-12, 0 conflicts / 0 unmatched) so 竞彩 league rows
    # join the Pinnacle line when the European season resumes. Same offline diff
    # extends it for any new league.
    "Augsburg": "FC Augsburg",
    "Bayern Munich": "Bayern München",
    "Bochum": "VfL Bochum",
    "Borussia Monchengladbach": "Borussia Mönchengladbach",
    "Braga": "SC Braga",
    "Brest": "Stade Brestois 29",
    "Elversberg": "SV Elversberg",
    "Estrela Amadora": "Estrela",
    "Freiburg": "SC Freiburg",
    "Gil Vicente": "GIL Vicente",
    "Heidenheim": "1. FC Heidenheim",
    "Hoffenheim": "1899 Hoffenheim",
    "Mainz 05": "FSV Mainz 05",
    "Man City": "Manchester City",
    "Man United": "Manchester United",
    "Oxford": "Oxford United",
    # 2026-08-05 注册荷乙时又踩到「别名遮蔽」:`瓦尔韦克` 在 TEAM_NAME_ZH 里有两个
    # EN 键(荷甲时期的 `RKC Waalwijk` + AF 现在荷乙用的 `Waalwijk`),而 `_ZH_TO_EN`
    # 反转是 setdefault 先到先得 ⇒ 反查永远拿到 `RKC Waalwijk`,AF 的 `Waalwijk`
    # 变成不可达。中文名在、行照写、join 永死 —— 和 07-04 汉堡/PSV/科隆同型。
    "RKC Waalwijk": "Waalwijk",
    "Paris SG": "Paris Saint Germain",
    "Porto": "FC Porto",
    "Roma": "AS Roma",
    "Saint-Etienne": "Saint Etienne",
    "Sheffield United": "Sheffield Utd",
    "St. Pauli": "FC St. Pauli",
    "Verona": "Hellas Verona",
    "Vitoria Guimaraes": "Guimaraes",
    "Wolfsburg": "VfL Wolfsburg",
    # 体检 Wave2 (2026-07-04) — ALIAS-SHADOWING class, measured against the LIVE
    # AF 2026-27 /teams tables (13 cron leagues + J1). TEAM_NAME_ZH keeps several
    # EN alias keys per club (display robustness); the zh→EN reverse map takes
    # the FIRST alias per zh name, which is often NOT the AF spelling — so the
    # 竞彩 row was written but never joined the Pinnacle close (the invisible
    # second failure mode; 27 clubs live). key = the alias the reverse map
    # actually picks today, value = the exact AF name. Re-derive with
    # nutmeg-registry-coverage after any dict edit.
    "Hamburg": "Hamburger SV",
    "Paderborn": "SC Paderborn 07",
    "Kaiserslautern": "1. FC Kaiserslautern",
    "Magdeburg": "1. FC Magdeburg",
    "Braunschweig": "Eintracht Braunschweig",
    "Hertha Berlin": "Hertha BSC",
    "Karlsruher": "Karlsruher SC",
    "Greuther Furth": "SpVgg Greuther Fürth",
    "Koln": "1. FC Köln",
    "Nurnberg": "1. FC Nürnberg",
    "Schalke 04": "FC Schalke 04",
    "Darmstadt": "SV Darmstadt 98",
    "Granada": "Granada CF",
    "Ceuta": "AD Ceuta FC",
    "Castellon": "Castellón",
    "Clermont": "Clermont Foot",
    "Troyes": "Estac Troyes",
    "Pau": "PAU",
    "Red Star": "RED Star FC 93",   # 巴黎红星 (Ligue 2), NOT Crvena Zvezda
    "NEC": "NEC Nijmegen",
    "PSV": "PSV Eindhoven",
    "Go Ahead Eagles": "GO Ahead Eagles",
    "Académico Viseu": "Academico Viseu",
    "Club Brugge": "Club Brugge KV",
    "Mechelen": "KV Mechelen",
    "Westerlo": "KVC Westerlo",
    "Kashima Antlers": "Kashima",
    "Urawa Red Diamonds": "Urawa",
    # 2026-07-04 瑞超事件后扩查市场模式联赛(nutmeg-registry-coverage 扩容首跑):
    "Hokkaido Consadole Sapporo": "Consadole Sapporo",   # J2 26 赛季 AF 用短名
}


def zh_to_canonical(zh_name: str | None) -> str | None:
    """竞彩 Chinese full name → our canonical English name (matching the live
    odds_snapshots / settler convention), or None if unmapped."""
    if not zh_name:
        return None
    en = _ZH_TO_EN.get(zh_name.strip())
    return _EN_OVERRIDES.get(en, en) if en else None


def _cache_path(pool_codes: str, channel: str, cache_dir: str | Path) -> Path:
    d = Path(cache_dir)
    d.mkdir(parents=True, exist_ok=True)
    safe = pool_codes.replace(",", "-")
    return d / f"matchcalc_{safe}_{channel}.json"


def lottery_cache_age_seconds(
    *,
    pool_codes: str = "had,hhad",
    channel: str = "c",
    cache_dir: str | Path = _DEFAULT_CACHE,
) -> float | None:
    """上次成功抓取竞彩在售名单距今多少秒(无缓存 → None)。

    给「只读缓存」的消费者标注新鲜度用:任何基于缓存的被动展示都必须能说出「截至
    何时」,否则就是又一个「看着权威其实过期」的陷阱。公开函数是为了让 API 层不必
    去 import 本模块的私有 _cache_path/_DEFAULT_CACHE。
    """
    try:
        return time.time() - _cache_path(pool_codes, channel, cache_dir).stat().st_mtime
    except OSError:
        return None


def _request(
    pool_codes: str,
    channel: str,
    *,
    cache_dir: str | Path,
    refresh: bool,
    ttl_seconds: int | None,
    timeout: float = 15.0,
    retries: int = 3,
) -> dict | None:
    """GET the uniform endpoint with TTL cache + retries. Returns the parsed
    JSON dict, or None on any failure (logged, never raised)."""
    cache = _cache_path(pool_codes, channel, cache_dir)
    if not refresh and cache.exists() and ttl_seconds is not None:
        age = time.time() - cache.stat().st_mtime
        if age < ttl_seconds:
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass  # corrupt cache → fall through to a live fetch

    # 熔断在**缓存读之后**:被拦时仍可用缓存服务,只是不再打网络(同 odds_api 顺序)。
    remaining = breaker_remaining(cache_dir)
    if remaining > 0:
        log.warning("sporttery 熔断中,跳过抓取(剩余 %.0f 分钟)", remaining / 60)
        return None
    url = f"{_BASE}{_ENDPOINT}"
    params = {"poolCode": pool_codes, "channel": channel}
    for attempt in range(retries):
        try:
            resp = httpx.get(url, params=params, headers=_HEADERS, timeout=timeout)
            if resp.status_code in (403, 429):
                _trip_breaker(cache_dir, resp.status_code)
                return None
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                log.warning("sporttery API not success: %s", data.get("errorMessage"))
                return None
            with contextlib.suppress(OSError):
                # 体检 Wave3 (P2) — atomic write (tmp + rename) so a crash
                # mid-write can't leave a truncated JSON behind.
                _tmp = cache.with_name(f"{cache.name}.{os.getpid()}.tmp")
                _tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                _tmp.replace(cache)
            return data
        except Exception as exc:  # noqa: BLE001 — fail-soft; never raise to the caller
            if attempt < retries - 1:
                time.sleep(1.0 + attempt)
                continue
            log.warning("sporttery fetch failed (%s): %s", url, exc)
            return None
    return None


def _fetch_vote_page(
    pool_code: str, page_size: int, page_no: int, timeout: float, retries: int
) -> tuple[list[dict], int]:
    """One getVoteV1 page → (rows, total_pages). ([], 0) on failure.

    与 calculator 端点共用同一把落盘熔断(同一域名/同一 IP:被拦就是全域被拦)。"""
    if breaker_remaining(_DEFAULT_CACHE) > 0:
        log.warning("sporttery 熔断中,跳过 vote 抓取(%s)", pool_code)
        return [], 0
    url = f"{_BASE}/gateway/uniform/football/getVoteV1.qry"
    params = {"poolCode": pool_code, "pageSize": page_size, "pageNo": page_no}
    for attempt in range(retries):
        try:
            resp = httpx.get(url, params=params, headers=_HEADERS, timeout=timeout)
            if resp.status_code in (403, 429):
                _trip_breaker(_DEFAULT_CACHE, resp.status_code)
                return [], 0
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                log.warning("sporttery getVote not success (%s): %s",
                            pool_code, data.get("errorMessage"))
                return [], 0
            matches = (data.get("value") or {}).get("matches") or {}
            if not isinstance(matches, dict):
                return (matches or []), 1
            rows = matches.get("list") or []
            try:
                pages = int(matches.get("pages") or 1)
            except (TypeError, ValueError):
                pages = 1
            return rows, pages
        except Exception as exc:  # noqa: BLE001 — fail-soft; never raise to the caller
            if attempt < retries - 1:
                time.sleep(1.0 + attempt)
                continue
            log.warning("sporttery getVote fetch failed (%s): %s", url, exc)
            return [], 0
    return [], 0


def fetch_vote_support(
    pool_code: str = "HAD",
    *,
    page_size: int = 50,
    timeout: float = 15.0,
    retries: int = 3,
    max_pages: int = 10,
) -> list[dict]:
    """体彩 官方逐场三路散户支持率 (getVoteV1) for one pool — ``HAD`` (胜平负) /
    ``HHAD``,``HDC`` (让球). No-auth, same /gateway/uniform/ route as the SP feed.
    Returns the raw match rows (``value.matches.list``): each carries h/d/a
    ``*supportRate`` (票数派生支持%) + ``win/draw/lose`` counts + 竞彩 SP odds
    (h/d/a) + 体彩 ``*probability``/``*error``. This is GENUINE Chinese retail crowd
    direction — NOT 唯彩/Okooo's 必发(Betfair)-derived 买量 (= sharp money).
    FORWARD-ONLY: the endpoint serves the CURRENT day's matches (matchId/date params
    are ignored), so capture daily. Returns [] on total failure (logged, never raised).

    体检 Wave2 — PAGINATED: the old single-page-of-50 read silently dropped every
    match past #50 on a big autumn Saturday (forward-only → lost forever). Probed
    live 2026-07-04: ``value.matches.{pages,total}`` are real and pageNo works.
    Later pages are best-effort: a mid-pagination failure returns what we have
    (partial > nothing); rows are deduped by matchId across pages (the feed can
    shift between page calls). ``max_pages`` (10 → 500 matches) is a runaway cap,
    far above any real 竞彩 slate.
    """
    rows, pages = _fetch_vote_page(pool_code, page_size, 1, timeout, retries)
    if not rows:
        return []
    out: list[dict] = []
    seen: set = set()
    for r in rows:
        mid = r.get("matchId") if isinstance(r, dict) else None
        if mid is not None and mid in seen:
            continue
        if mid is not None:
            seen.add(mid)
        out.append(r)
    for page_no in range(2, min(pages, max_pages) + 1):
        more, _ = _fetch_vote_page(pool_code, page_size, page_no, timeout, retries)
        if not more:
            log.warning("sporttery getVote page %d/%d empty/failed (%s) — "
                        "returning %d rows captured so far",
                        page_no, pages, pool_code, len(out))
            break
        for r in more:
            mid = r.get("matchId") if isinstance(r, dict) else None
            if mid is not None and mid in seen:
                continue
            if mid is not None:
                seen.add(mid)
            out.append(r)
    return out


def _odds3(pool: dict | None):
    """(h, d, a) floats from a had/hhad pool, or None if incomplete/implausible."""
    if not pool:
        return None
    try:
        h, d, a = float(pool["h"]), float(pool["d"]), float(pool["a"])
    except (KeyError, TypeError, ValueError):
        return None
    # 体检 A3 — 竞彩 SP is the ×SP multiplier in EV = P×SP−1, so a freeze/placeholder
    # artifact (a '0' or '999' from the undocumented endpoint) would fabricate EV.
    # A fixed-odds decimal must exceed the stake; real 竞彩 SP measured 1.13–13.5.
    # Reject the physically-impossible (≤1.0 / non-finite / absurd) as an incomplete
    # pool rather than store a garbage line.
    if not all(math.isfinite(x) and 1.0 < x <= 1000.0 for x in (h, d, a)):
        return None
    return (h, d, a)


# 比分 (crs) 的 3 个「其他」桶键 → 竞彩标准标签
_CRS_OTHER = {"s1sh": "胜其他", "s1sd": "平其他", "s1sa": "负其他"}
_CRS_META = {"goalLine", "goalLineValue", "updateDate", "updateTime"}


def _crs_outcomes(pool: dict | None) -> dict[str, float]:
    """``{结果: SP}`` from a 比分 (crs) pool. ``s{HH}s{AA}`` → ``'H:A'``;
    ``s1sh/s1sd/s1sa`` → 胜/平/负其他. Skips the ``*f`` flag keys + metadata."""
    out: dict[str, float] = {}
    for k, v in (pool or {}).items():
        if k.endswith("f") or k in _CRS_META:
            continue
        if k in _CRS_OTHER:
            label = _CRS_OTHER[k]
        else:
            m = re.fullmatch(r"s(\d\d)s(\d\d)", k)
            if not m:
                continue
            label = f"{int(m.group(1))}:{int(m.group(2))}"
        try:
            out[label] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _ttg_outcomes(pool: dict | None) -> dict[str, float]:
    """``{'0'..'7': SP}`` from a 总进球 (ttg) pool; ``'7'`` = 7 或更多."""
    out: dict[str, float] = {}
    for k, v in (pool or {}).items():
        m = re.fullmatch(r"s(\d)", k)
        if not m:
            continue
        with contextlib.suppress(TypeError, ValueError):
            out[m.group(1)] = float(v)
    return out


def _utc_date_and_kickoff(match_date: str | None, match_time: str | None):
    """竞彩 gives the Beijing (UTC+8) calendar date + kickoff time. Convert to the
    UTC kickoff date + ISO — the gather/predictions/settler all key on the UTC date,
    so a Beijing matchDate runs one day ahead for any post-16:00-UTC kickoff and the
    row would miss the join (pre-fill + settle). Fall back to ``(match_date, None)``
    if the time is absent/malformed."""
    if not match_date or not match_time:
        return match_date, None
    try:
        bj = datetime.strptime(f"{match_date} {match_time}", "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return match_date, None
    utc = (bj - timedelta(hours=8)).replace(tzinfo=UTC)
    return utc.date().isoformat(), utc.isoformat()


def _single_by_pool(g: dict) -> dict[str, int]:
    """``{'had': 0/1, 'hhad': 0/1, ...}`` — 竞彩's per-market 单关 (single-bet)
    availability, read from ``poolList[].bettingSingle``. AUTHORITATIVE per POOL:
    probed 2026-07-08, the sub-match-level ``bettingSingle``/``bettingAllUp`` are
    ALWAYS 0 (useless), while the pool-level flag really varies (same match can be
    单关 on 胜平负 but 过关-only on 让球). Missing/garbage pool → key absent."""
    out: dict[str, int] = {}
    for p in (g.get("poolList") or []):
        code = str(p.get("poolCode") or "").strip().lower()
        bs = p.get("bettingSingle")
        if not code or bs is None:
            continue
        try:
            out[code] = int(bs)
        except (TypeError, ValueError):
            continue
    return out


def fetch_lottery_matches(
    *,
    pool_codes: str = "had,hhad",
    channel: str = "c",
    refresh: bool = False,
    ttl_seconds: int | None = 3600,
    cache_dir: str | Path = _DEFAULT_CACHE,
) -> list[dict]:
    """Current 竞彩 football matches with frozen SP. Each dict:
    ``{match_date, match_num, league_cn, home_cn, away_cn, home_en, away_en,
    had: (h,d,a)|None, hhad: (h,d,a,goalLine)|None,
    crs: {结果:SP}, ttg: {'0'..'7':SP}}``. ``*_en`` is the canonical English name
    (None if unmapped). ``crs``/``ttg`` are ``{}`` unless those poolCodes were
    requested. Returns [] on any failure (fail-soft)."""
    data = _request(pool_codes, channel, cache_dir=cache_dir, refresh=refresh,
                    ttl_seconds=ttl_seconds)
    if not data:
        return []
    out: list[dict] = []
    try:
        for grp in data.get("value", {}).get("matchInfoList", []) or []:
            for g in (grp.get("subMatchList") or []):
                had = _odds3(g.get("had"))
                hhad_pool = g.get("hhad") or {}
                hhad3 = _odds3(hhad_pool)
                hhad = None
                if hhad3 is not None:
                    try:
                        line = int(hhad_pool.get("goalLine"))
                    except (TypeError, ValueError):
                        line = None
                    if line is not None:
                        hhad = (*hhad3, line)
                home_cn = g.get("homeTeamAllName")
                away_cn = g.get("awayTeamAllName")
                mdate, kickoff_utc = _utc_date_and_kickoff(
                    g.get("matchDate"), g.get("matchTime"))
                out.append({
                    "match_date": mdate,
                    "kickoff_utc": kickoff_utc,
                    "match_num": g.get("matchNumStr"),
                    "league_cn": g.get("leagueAbbName") or g.get("leagueAllName"),
                    "home_cn": home_cn, "away_cn": away_cn,
                    "home_en": zh_to_canonical(home_cn),
                    "away_en": zh_to_canonical(away_cn),
                    "had": had, "hhad": hhad,
                    # 玩法扩展:比分 {结果:SP} + 总进球 {'0'..'7':SP}(pool 缺则空 dict)
                    "crs": _crs_outcomes(g.get("crs")),
                    "ttg": _ttg_outcomes(g.get("ttg")),
                    # 竞彩 per-market 单关可投标记 {'had':0/1,'hhad':0/1}(pool 级权威)
                    "single": _single_by_pool(g),
                })
    except Exception:  # noqa: BLE001 — a parse failure must not raise
        log.warning("sporttery parse failed", exc_info=True)
        return []
    return out
