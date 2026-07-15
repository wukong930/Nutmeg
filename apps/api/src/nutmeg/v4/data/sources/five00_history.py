"""500彩票 免费历史收盘档案(hisdata 静态 XML)。

免费/无认证/UTF-8,回溯 2013。皇冠(`hg`)去vig ≈ Pinnacle 收盘(2026-07-09 交叉验
N=36,median 0.62pp;`记忆 500-historical-odds-archive`)。给 Crown 1X2 + 让球线 +
让球1X2 + O/U + 结果,**无竞彩 SP**。用于免费收盘替代 / C1 让球修正校准(不受 Odds API
配额限)。China 站 → **清代理**。抓公开静态文件、非官方 API。FAIL-SOFT。
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import time
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import httpx

log = logging.getLogger(__name__)

_BASE = "https://www.500.com/static/public/jczq/xml/hisdata"
_UA = {"User-Agent": "Mozilla/5.0"}
_BJ = ZoneInfo("Asia/Shanghai")


def _kickoff_utc(matchdate: str | None, matchtime: str | None) -> str | None:
    """XML 的 ``matchdate`` + ``matchtime``(**都是北京时间**)→ UTC ISO 串。

    ⚠️ 为什么需要这个:XML 里有三个日期语义,别混(2026-07-15 实测):
      · ``matchnumdate`` = **竞彩期号日/投注日** ← 存进 ``crown_close_history.match_date``
      · ``matchdate`` + ``matchtime`` = **北京**开赛日 + 时刻
      · 而 ``jingcai_sp.match_date`` = **UTC 开赛日**(实测每行都严格 == kickoff_utc.date())

    对欧洲晚场(北京凌晨开),期号日**碰巧**等于 UTC 日 → 直接拿 match_date 去 join
    看着能用;但对北京上午开的美洲场(美职足/解放者杯/跨洲赛事),期号日比 UTC 日**早
    一天** → 静默漏配。实测样本:美国vs波黑 北京 07-02 08:00 → UTC 日 07-02,期号日
    07-01。这正是 CLV 侧 join 只有 58.9% 的首因(±1 天放宽能到 78.3%,但那是钝器)。

    ⇒ 本函数给出**精确**的对齐键。**别改 ``match_date`` 的含义** —— 它(=期号日)恰好
    对得上 football-data 的当地日期,那条 join 的 1,838 场比分 100% 一致就是证据;
    改它会打断那边。**加字段,不改字段。**
    """
    if not matchdate or not matchtime:
        return None
    try:
        naive = _dt.datetime.strptime(f"{matchdate} {matchtime}", "%Y-%m-%d %H:%M")
    except ValueError:
        log.warning("500 hisdata: 无法解析开赛时刻 matchdate=%r matchtime=%r", matchdate, matchtime)
        return None
    return naive.replace(tzinfo=_BJ).astimezone(_dt.UTC).isoformat()


def _clear_proxy() -> None:
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(k, None)


def _triple(s: str | None) -> tuple[float, float, float] | None:
    """'1.27,6.50,10.00' → (1.27, 6.50, 10.00); None if junk (any odd ≤ 1)."""
    try:
        h, d, a = (float(x) for x in s.split(","))
    except (ValueError, AttributeError):
        return None
    return (h, d, a) if h > 1 and d > 1 and a > 1 else None


def _ou(s: str | None) -> tuple[float, float, float] | None:
    """'0.95,3/3.5,0.95' → (over_decimal, line, under_decimal).

    500 的大小球/亚盘赔是**香港/让步赔**(~0.6–1.3),与 europe(decimal)不同 → +1 转
    decimal 以喂 ``devig_over`` / ``fit_lambdas``(它们要 >1 的 decimal)。分盘线 '3/3.5'
    取两邻线均。守卫 HK 合理区间,越界(疑似已是 decimal 或垃圾)= None。"""
    try:
        parts = s.split(",")
        over, under = float(parts[0]), float(parts[2])
        line_s = parts[1]
        if "/" in line_s:
            lo, hi = line_s.split("/")
            line = (float(lo) + float(hi)) / 2
        else:
            line = float(line_s)
    except (ValueError, IndexError, AttributeError):
        return None
    if not (0.3 < over < 2.0 and 0.3 < under < 2.0):
        return None
    return (over + 1.0, line, under + 1.0)


def fetch_hisdata(date_iso: str, *, timeout: float = 25.0,
                  retries: int = 3) -> tuple[ET.Element | None, ET.Element | None]:
    """(match_root, odds_root) for ``date_iso`` ('YYYY-MM-DD'), or (None, None) parts
    on 404 / failure. Clears the proxy (China site). Logged, never raised."""
    _clear_proxy()
    y, m, d = date_iso.split("-")
    mmdd = f"{m}{d}"
    roots: list[ET.Element | None] = []
    for fn in ("match.xml", "odds.xml"):
        url = f"{_BASE}/{y}/{mmdd}/{fn}"
        root: ET.Element | None = None
        for attempt in range(retries):
            try:
                r = httpx.get(url, timeout=timeout, headers=_UA)
                if r.status_code == 200:
                    root = ET.fromstring(r.content)
                    break
                if r.status_code == 404:
                    break  # 无当日档案
            except Exception:  # noqa: BLE001 — fail-soft
                if attempt < retries - 1:
                    time.sleep(1.0 + attempt)
                    continue
                log.warning("500 hisdata fetch failed (%s %s)", date_iso, fn, exc_info=True)
        roots.append(root)
    return roots[0], roots[1]


def parse_hisdata(match_root: ET.Element | None,
                  odds_root: ET.Element | None) -> list[dict]:
    """Join match.xml + odds.xml by ``match id`` → per-match records. Only matches with
    a Crown 1X2 quote AND a final score are returned::

        [{match_id, date, league_cn, home_zh, away_zh, home_goals, away_goals,
          rangqiu(int|None),                # 让球线 (竞彩式整数, home handicap)
          crown_1x2(h,d,a),                 # 皇冠 1X2 decimal (sharp close ≈ Pinnacle)
          crown_ou(over,line,under)|None,   # 大小球 (Crown 优先, 回退 avg/其它庄)
          rq_avg(h,d,a)|None}]              # 让球1X2 市场均值 (直接 3-way 让球赔)
    """
    if match_root is None or odds_root is None:
        return []
    odds: dict[str, dict] = {}
    for om in odds_root.iter("match"):
        rec: dict = {}
        eu = om.find("europe")
        if eu is not None:
            rec["crown_1x2"] = _triple(eu.get("hg"))
        rq = om.find("rq")
        if rq is not None:
            rec["rq_avg"] = _triple(rq.get("avg"))
        dxq = om.find("dxq")
        if dxq is not None:
            for bk in ("hg", "avg", "bet365", "am", "lb", "wl"):
                parsed = _ou(dxq.get(bk))
                if parsed:
                    rec["crown_ou"] = parsed
                    break
        odds[om.get("id")] = rec

    out: list[dict] = []
    for mm in match_root.iter("match"):
        score = mm.get("score") or ""
        if ":" not in score:
            continue
        try:
            hg_, ag_ = (int(x) for x in score.split(":"))
        except ValueError:
            continue
        od = odds.get(mm.get("id"), {})
        if not od.get("crown_1x2"):
            continue
        rq_raw = mm.get("rangqiu")
        try:
            rangqiu = int(rq_raw) if rq_raw not in (None, "") else None
        except ValueError:
            rangqiu = None
        out.append({
            "match_id": mm.get("id"),
            # ⚠️ 期号日(投注日),**不是**开赛日 —— 对齐 jingcai_sp 请用下面的 kickoff_utc。
            "date": mm.get("matchnumdate") or mm.get("matchdate"),
            "kickoff_utc": _kickoff_utc(mm.get("matchdate"), mm.get("matchtime")),
            "league_cn": mm.get("league"),
            "home_zh": mm.get("homename"), "away_zh": mm.get("awayname"),
            "home_goals": hg_, "away_goals": ag_,
            "rangqiu": rangqiu,
            "crown_1x2": od["crown_1x2"],
            "crown_ou": od.get("crown_ou"),
            "rq_avg": od.get("rq_avg"),
        })
    return out
