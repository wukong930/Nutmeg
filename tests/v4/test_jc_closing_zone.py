"""开赛前后的三分区(2026-08-21)—— 卡片不再掉进一个标题说假话的抽屉。

## 病史

owner:「竞彩可投注的赛事卡片,在开赛前 5 分钟输入数据重新计算,卡片会消失。」

查下来**不是删除,也不是那个按钮**:「应用」走 `_cupManualReprice` → POST
`/recommend/market-reprice`(纯计算)→ 就地 `renderCupMarket(_CUPMKT.preds, …)`,
**没有任何板级重拉**。重渲时 `_isJcBettable` 拿新的 `Date.now()` 重新分区 ⇒ 卡片从
顶部「💴 竞彩可投注」搬进参考区;若它是最后一张,整块顶部被加 `hidden` ⇒ 标题一起消失。
**不点也会在 T−5 那一刻搬家** —— 按钮只是跨过 T−5 后的第一次重渲。

## 为什么这是个真问题(而不是观感问题)

参考区的表头是「**竞彩未上架** · 仅模型 / Pinnacle 参考」,而这些场**明明上架了、
正在调价**:实测竞彩卖到 T−0(`jingcai_odds_history`:**0/1,531** 条末次变盘发生在
开球后),而 **5.29%** 的末次变盘落在最后 5 分钟内,最紧的一条距开球 **12 秒**。
owner 自己手填的 74 条里 **23.0%** 发生在 T−5 或更晚。

## ⛔ owner 的原始提案(「赛后 5 分钟才消失」)被数据否掉

回放 54 个真实快照窗 / 532 场 / 70,521 条腿:重新进池 21/54 窗,**top-1 翻转 5/54,
且 5/5 的新 top-1 都是已开球买不到的场**;串关池 4 次塌陷(12→1 ×2、11→1、3→1)。
机制:那些腿从没靠 evLo 赢过,唯一通道是「已开球的场开球最早 ⇒ 重定义了『最近一期』」。

## 本次改动的边界

`_isJcBettable` **一字未动**(判据抽进 `_jcKoState`,逐字等价)⇒ 串关池 / 甜区榜 /
top-1 逐元素不变。改的只有显示分区 + 已开赛卡的记账入口。
`tests/v4/test_jc_kickoff_gate.py` 那 8 条断言一字未改而全绿 = 不变性验收。
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _fn(name: str) -> str:
    js = DASH.read_text(encoding="utf-8")
    i = js.index(name)
    depth, j, started = 0, i, False
    while j < len(js):
        if js[j] == "{":
            depth += 1
            started = True
        elif js[j] == "}":
            depth -= 1
            if started and depth == 0:
                return js[i:j + 1]
        elif js[j] == ";" and not started:
            return js[i:j + 1]
        j += 1
    return js[i:]


def _run(names: tuple[str, ...], body: str) -> str:
    r = subprocess.run(["node", "-e", "\n".join(_fn(n) for n in names) + "\n" + body],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout.strip()


_CORE = ("const _JC_KO_BUFFER_MIN", "function _hasJcSp", "function _jcKoState",
         "function _isJcBettable", "function _bettableSplit")


def _ko(minutes: float) -> str:
    return (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=minutes)).isoformat()


def _split(offsets: list[float | None], with_sp: bool = True) -> dict:
    preds = []
    for m in offsets:
        pr: dict = {"jc_home": 2, "jc_draw": 3, "jc_away": 4} if with_sp else {}
        if m is not None:
            pr["kickoff_utc"] = _ko(m)
        preds.append(pr)
    out = _run(_CORE, f"""
      const r = _bettableSplit({json.dumps(preds)});
      console.log(JSON.stringify({{bett:r.bett.map(o=>o.idx),
                                   closing:r.closing.map(o=>o.idx),
                                   rest:r.rest.map(o=>o.idx)}}));""")
    return json.loads(out)


# ── 承重 ①:池的构成没变 ────────────────────────────────────────

def test_the_pool_population_is_unchanged() -> None:
    """🚨 全案最承重的一条:`bett` 的成员与改动前**逐元素相同**。

    `_parlayPool` 只有一个调用点,喂它的 items 来自 `_isJcBettable` ⇒ 只要 `bett`
    不变,串关池 / 排序 / top-1 就不变。断言写成「跨一整条时间轴逐个比对」,
    而不是「`_isJcBettable` 这个函数还在」。
    """
    offs = [-600, -120, -5, -1, 0, 1, 4.5, 5.5, 30, 600, None]
    r = _split(offs)
    # 旧口径:有 SP 且(无开球时刻 或 ko > now + 5min)
    expect = [i for i, m in enumerate(offs) if m is None or m > 5]
    assert r["bett"] == expect, f"池的构成变了:{r['bett']} vs {expect}"


def test_every_card_lands_in_exactly_one_zone() -> None:
    """⛔ 三个分区必须是**划分**:不重不漏。漏一张 = 卡片真的消失。"""
    offs = [-600, -1, 0, 3, 30, None]
    r = _split(offs)
    allidx = sorted(r["bett"] + r["closing"] + r["rest"])
    assert allidx == list(range(len(offs))), f"有卡片丢失或重复:{r}"


# ── 承重 ②:两种「不可投注」被分开了 ─────────────────────────────

def test_closing_and_kicked_leave_the_not_listed_drawer() -> None:
    """⭐ 这就是 owner 报的那个问题:有竞彩 SP 的场**不该**落进「竞彩未上架」。"""
    r = _split([3, -10])          # T−3(还在卖) / T+10(已开赛)
    assert r["closing"] == [0, 1], f"有 SP 的场没进 closing 区:{r}"
    assert r["rest"] == [], "有竞彩 SP 的场仍落在「竞彩未上架」抽屉里"


def test_no_jingcai_sp_still_goes_to_the_reference_drawer() -> None:
    """反向:真的没上架的场**仍然**归参考区 —— 别把两件事又合并回去。"""
    r = _split([3, -10], with_sp=False)
    assert r["closing"] == [] and r["rest"] == [0, 1]


def test_the_two_states_are_distinguished() -> None:
    """「还在卖」和「已停售」必须分得开 —— 前者绿灯照常,后者关记账。"""
    st = _run(_CORE, f"""
      console.log(JSON.stringify([
        _jcKoState({{kickoff_utc:'{_ko(30)}'}}),
        _jcKoState({{kickoff_utc:'{_ko(3)}'}}),
        _jcKoState({{kickoff_utc:'{_ko(-10)}'}}),
        _jcKoState({{}}),
        _jcKoState({{kickoff_utc:'not-a-date'}})]));""")
    assert json.loads(st) == ["open", "closing", "kicked", "open", "open"]


# ── 承重 ③:已开赛卡的记账入口是**行为闸**,不是文案 ────────────────

def _record_probe(minutes: float) -> str:
    """真调 `_recordBet`:被闸拦住 ⇒ 'BLOCKED';放行 ⇒ 会走到 DOM ⇒ 'PASSED'。

    ⭐ 用「有没有走到 DOM」当判据,而不是 grep 源码里有没有那句 if ——
    后者是语法代理(本仓栽过五次)。
    """
    return _run(("const _JC_KO_BUFFER_MIN", "function _jcKoState", "function _recordBet"), f"""
      let blocked = false;
      globalThis.alert = () => {{ blocked = true; }};
      globalThis.t = (k) => k;
      globalThis._CUPMKT = {{ preds: [{{ jc_home:2, jc_draw:3, jc_away:4,
                                        kickoff_utc:'{_ko(minutes)}' }}] }};
      globalThis.document = {{ querySelector: () => {{ throw new Error('REACHED_DOM'); }} }};
      try {{ _recordBet('cup', 0, 'H', '1x2', null); }}
      catch (e) {{ if (e.message === 'REACHED_DOM') {{ console.log('PASSED'); process.exit(0); }} throw e; }}
      console.log(blocked ? 'BLOCKED' : 'RETURNED_QUIETLY');""")


def test_recording_is_blocked_after_kickoff() -> None:
    """🚨 服务端 `/observation/record-bet` 里 `kickoff` 出现 **0 次**,而台账
    (`recommendation_sessions`/`single_predictions`)**没有 kickoff 列**
    ⇒ 赛后记的注事后不可识别、不可清洗。前端必须真拦住。"""
    assert _record_probe(-10) == "BLOCKED", "已开赛仍能记账"


def test_recording_still_works_in_the_closing_window() -> None:
    """⛔ 反向断言(同样承重):T−5..T−0 竞彩**还在卖** ——
    实测 5.29% 的末次变盘落在这里 ⇒ 拦住它等于凭空砍掉一段真实下注窗口。"""
    assert _record_probe(3) == "PASSED", "还能买的窗口被误拦了"


# ── 承重 ④:唯一的时间线索不再自己关掉 ──────────────────────────

def test_freshness_badge_survives_the_gate() -> None:
    """原来 `_jcFreshnessHtml` 里是 `!_isJcBettable(pr)` ⇒ 卡片一进 T−5 就把
    **唯一的时间线索自己关掉**,停售卡上一个字都不说它已开赛。

    ⚠️ 本条第一版写成 `assert "_isJcBettable" not in body` —— 它匹配到了**我自己
    写在改动里的那句注释**,红得毫无意义。改成真调函数:已开赛的卡必须仍然出徽章。
    (同 memory `syntactic-proxy-for-semantic-property`:先写行为断言。)
    """
    out = _run(("function _hasJcSp", "function _jcFreshnessHtml"), f"""
      globalThis.t = (k) => k;
      globalThis.IC = (k) => k;
      const pr = {{ jc_home:2, jc_draw:3, jc_away:4,
                   jc_captured_at:'{_ko(-90)}', kickoff_utc:'{_ko(-10)}' }};
      const html = _jcFreshnessHtml(pr);
      console.log(JSON.stringify({{ empty: !html, len: (html || '').length }}));""")
    r = json.loads(out)
    assert not r["empty"] and r["len"] > 0, "已开赛的卡上没有任何时间线索"
