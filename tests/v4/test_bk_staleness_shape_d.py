"""⚖️ 多书商共识陈旧提示 —— 只做「开球相对」半边(形状 D,2026-09-04 裁定)。

## 这个文件在守什么

原方案是复用 `_ODDS_STALE_MIN`(平线 120min)。实测在 **25 次真实看盘会话 ×
771 次卡片渲染**(竞彩在售 ∧ 未开球 ∧ 面板真会渲染)上,五个形状的点亮率:

    A 平线 120min ......... 63.9%     B 字面复用整条复合规则 ... 63.9%
    C  >60m ∧ 距开球<3h ... 0.8%      D  >60m ∧ 距开球<6h ..... 3.0%  ← 本实现
    E  ≥24h ............... 21.3%

否掉平线的两条理由,任一条都足够:
① **额度放大器** —— 徽章的处方是按 🔄 刷新盘口,而那颗按钮**花真钱**
   (实测 33 个批次里 6 个 / 632 行 = 27.5% 来自 serving 路径)。在 64–79% 的卡上
   点亮 + 处方是付费刷新 = 正对着本项目第一条烧钱教训。
② **它测的是时钟不是卡片** —— 离上一轮 cron +90min 点亮 65.2%,+120min 一步跳到
   100.0%;92% 的卡年龄恰等于最近两个批次时刻(批次属性,不是卡片属性)。

⇒ **本文件最承重的一条断言是「平线不许回来」**:一张 10 小时没变、但距开球还有
20 小时的卡,**不许**变琥珀。平线一旦被加回去,那条测试立刻红。

## ⚠️ 与 `keep_started` 的交互(容易漏)
2026-09-03 起卡片开赛后仍留在盘面上。若不要求 `hrsToKo > 0`,已开赛的卡会
**永久**挂琥珀 —— 而那时它既不能下注也无从更新。实测口径也正是「未开球」那批。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _fn(name: str) -> str:
    """抠生产函数原文(花括号配平)—— 不重写一份,重写就测不到真代码。"""
    js = DASH.read_text(encoding="utf-8")
    m = re.search(rf"\n(async )?function {re.escape(name)}\s*\(", js)
    assert m, f"找不到 {name} —— 它被改名或删了,本护栏失效"
    start, j, depth = m.start() + 1, js.index("{", m.end()), 0
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[start:j + 1]
        j += 1
    raise AssertionError(name)


def _const(name: str) -> str:
    """把 `const _X = <字面量>;` **原文**取过来 —— ⛔ 不在测试里照抄一个阈值。"""
    js = DASH.read_text(encoding="utf-8")
    m = re.search(rf"^const {re.escape(name)} = [0-9.]+;", js, re.M)
    assert m, f"找不到常数 {name}"
    return m.group(0)



def _disclaimer_values() -> tuple[str, str]:
    """取出中/英两份 `bk_disclaimer` 的**值**(多行 `+` 拼接,到下一个键为止)。

    ⛔ 不用全文 grep —— 见 `test_info_text_explains_what_amber_means_in_both_languages`
       的 docstring:全文 grep 会把「文案搬到用不上的键里」判成绿。
    """
    js = DASH.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"^    bk_disclaimer:", js, re.M):
        j = js.index("\n", m.end())
        while True:
            nl = js.index("\n", j + 1)
            line = js[j + 1:nl]
            # 续行一律以 `+` 开头;碰到下一个 `    key:` 就停
            if not line.lstrip().startswith("+"):
                break
            j = nl
        out.append(js[m.end():j])
    assert len(out) == 2, f"bk_disclaimer 应有中英两处,实得 {len(out)}"
    return out[0], out[1]

#: 固定时钟 —— `_bkStale` 读 `Date.now()`,不钉死就是一个随时间漂的测试。
_NOW_MS = 1788_000_000_000        # 任意固定时刻;所有 fixture 都相对它构造


def _stale(cases: list[dict]) -> list[bool]:
    """真跑生产 `_bkStale`,逐个 case 收布尔值。"""
    src = f"""
const NOW = {_NOW_MS};
Date.now = () => NOW;
//: 用生产库里的**字面形状** `2026-…T…+00:00`,不是 `toISOString()` 的 `.000Z` ——
//: 本仓踩过「两列存不同字面格式、裸比较判反」的坑,fixture 贴近真值才测得到。
const iso = (msAgo) => new Date(NOW - msAgo).toISOString().replace('.000Z', '+00:00');
{_const('_ODDS_STALE_MIN')}
{_const('_BK_KO_WINDOW_H')}
{_fn('_bkStale')}
const CASES = {json.dumps(cases)};
console.log(JSON.stringify(CASES.map(c => {{
  const pr = {{}};
  if (c.age_min !== null) pr.bk_captured_at = iso(c.age_min * 60000);
  if (c.ko_h !== null) pr.kickoff_utc = new Date(NOW + c.ko_h * 3600000).toISOString();
  return _bkStale(pr);
}})));
"""
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:2000]
    return json.loads(r.stdout)


#: 每个 case: age_min = 快照多少分钟没变, ko_h = 距开球几小时(负=已开赛), None=字段缺失
_CASES = [
    {"name": "6h没变 · 3h后开球",      "age_min": 360, "ko_h": 3,    "want": True},
    {"name": "10h没变 · 20h后开球",    "age_min": 600, "ko_h": 20,   "want": False},
    {"name": "30min没变 · 2h后开球",   "age_min": 30,  "ko_h": 2,    "want": False},
    {"name": "6h没变 · 1h前已开赛",    "age_min": 360, "ko_h": -1,   "want": False},
    {"name": "6h没变 · 无开球时刻",    "age_min": 360, "ko_h": None, "want": False},
    {"name": "6h没变 · 恰好6h后开球",  "age_min": 360, "ko_h": 6,    "want": False},
    {"name": "6h没变 · 5.9h后开球",    "age_min": 360, "ko_h": 5.9,  "want": True},
    {"name": "恰好60min · 2h后开球",   "age_min": 60,  "ko_h": 2,    "want": False},
    {"name": "61min · 2h后开球",       "age_min": 61,  "ko_h": 2,    "want": True},
    {"name": "无快照时刻",             "age_min": None, "ko_h": 2,   "want": False},
]


class TestFlatLineMustNotComeBack:
    """🚨 本次裁定的**全部内容**就是这一条。"""

    def test_no_age_whatsoever_flags_a_match_far_from_kickoff(self):
        """🚨 承重条。距开球够远时,**任何**年龄都不许点亮 —— 一分钟到一周。

        ⚠️ 这条原本只测了「10 小时没变」一个点,于是它只挡得住 **<600min 的平线**:
        对抗审查实测把规则改成 `mins > 1440 ||`(形状 E,24h 平线)后,
        整个文件 **9 条全绿**。承重的断言挡不住它要挡的东西,是本文件最贵的缺陷。
        ⇒ 改成**扫一整条年龄轴**:平线无论定在哪个刻度上都会被这条抓住。
        """
        AGES = [1, 30, 59, 60, 61, 90, 119, 120, 121, 180, 360, 600, 719, 720,
                1000, 1439, 1440, 1441, 2880, 4320, 10080]     # 1min → 7天
        got = _stale([{"age_min": a, "ko_h": 20} for a in AGES])
        # 🚨 人口非平凡:年龄轴必须真的跨过所有候选平线刻度,否则这条空洞为真
        assert max(AGES) > 1440 and len(AGES) >= 15, "年龄轴退化,断言变空洞"
        lit = [a for a, g in zip(AGES, got) if g]
        assert not lit, f"距开球 20h 却在这些年龄上点亮 = 平线回来了(刻度 {lit} 分钟)"

    def test_the_rule_does_not_inline_any_flat_threshold(self):
        """⚠️ 语法断言,只作为上面那条行为断言的补充,不单独承重。

        ⛔ 原来写的是 `"120" not in body` —— 那是把**常数的当前取值**编进了测试:
        `_ODDS_STALE_MIN` 一旦调成 90,这颗钉子就静默变成空气,而测试仍然绿。
        改成从源码**现取**那个值再断言,值变了断言跟着变。
        """
        body = _fn("_bkStale")
        assert "_ODDS_STALE_MIN" not in body, \
            "_bkStale 引用了平线常数 —— 形状 D 只用开球相对半边"
        cur = re.search(r"^const _ODDS_STALE_MIN = ([0-9]+);", DASH.read_text(encoding="utf-8"), re.M)
        assert cur, "取不到 _ODDS_STALE_MIN 的当前值,本断言失效"
        assert cur.group(1) not in body, \
            f"_bkStale 里内联了 {cur.group(1)}(= _ODDS_STALE_MIN 当前值),疑似把平线抄了进来"



class TestKickoffRelativeHalfWorks:
    def test_all_cases_match_expectations(self):
        got = _stale(_CASES)
        # 🚨 人口非平凡:两种答案都必须出现,否则「全 False」也能让逐条断言通过
        assert any(got) and not all(got), f"用例退化成单一答案:{got}"
        bad = [(c["name"], c["want"], g) for c, g in zip(_CASES, got) if g != c["want"]]
        assert not bad, "不符预期:" + "; ".join(f"{n}: 期望{w} 实得{g}" for n, w, g in bad)

    def test_started_match_never_flagged(self):
        """⚠️ 与 `keep_started` 的交互:开赛后卡片仍在盘面,不加 `hrsToKo > 0`
        它会**永久**挂琥珀 —— 那时既不能下注也无从更新。"""
        started = [{"age_min": 360, "ko_h": h} for h in (-0.1, -1, -12, -48)]
        # 🚨 人口非平凡:同一个 age_min 在**未开赛**时必须点亮,
        #    否则「已开赛不点亮」可能只是因为 _bkStale 恒 False(空洞为真)
        ctrl = _stale([{"age_min": 360, "ko_h": 3}])
        assert ctrl == [True], f"对照不成立 —— 未开赛的同龄卡也没点亮:{ctrl}"
        got = _stale(started)
        assert not any(got), f"已开赛的卡被判陈旧:{got}"

    def test_window_boundary_is_the_constant_not_a_hardcoded_6(self):
        """边界必须**跟着常数走**。把 `_BK_KO_WINDOW_H` 改成 24,距开球 20h 的卡
        就该变琥珀 —— 这条证明那个数字真的是参数,而不是散落在代码里的 6。"""
        js = DASH.read_text(encoding="utf-8")
        assert re.search(r"^const _BK_KO_WINDOW_H = 6;", js, re.M), "常数不见了或不是 6"
        src = f"""
const NOW = {_NOW_MS};
Date.now = () => NOW;
const _ODDS_STALE_MIN = 120;
const _BK_KO_WINDOW_H = 24;          // ← 只改这个数
{_fn('_bkStale')}
console.log(JSON.stringify(_bkStale({{
  bk_captured_at: new Date(NOW - 600*60000).toISOString(),
  kickoff_utc: new Date(NOW + 20*3600000).toISOString() }})));
"""
        r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[:1500]
        assert json.loads(r.stdout) is True, \
            "改大 _BK_KO_WINDOW_H 后行为没变 —— 窗口不是从这个常数读的"


class TestWiredIntoTheSummary:
    """规则对了但没接线 = 屏幕上什么都不会变。"""

    def _render(self, age_min: int, ko_h: float, spread: float = 2.0,
                *, no_bk: bool = False) -> str:
        src = f"""
const NOW = {_NOW_MS};
Date.now = () => NOW;
const t = (k) => k, IC = (k) => '[' + k + ']';
const _foldAttrs = () => '', _foldKey = () => 'k';
{_fn('_hasBk')}                       // ⭐ 生产原文,不打桩:它决定这块面板渲不渲
{_const('_ODDS_STALE_MIN')}
{_const('_BK_KO_WINDOW_H')}
{_fn('_bkAge')}
{_fn('_bkStale')}
{_fn('_bkHtml')}
const pr = {{
  bk_n: 20, bk_consensus: [0.5,0.3,0.2], bk_low: [0.45,0.28,0.18], bk_spread: [{spread},{spread},{spread}],
  jc_home: 2.0, jc_draw: 3.4, jc_away: 4.0,
  bk_captured_at: new Date(NOW - {age_min}*60000).toISOString(),
  kickoff_utc: new Date(NOW + {ko_h}*3600000).toISOString(),
}};
const NO_BK = {json.dumps(no_bk)};
if (NO_BK) {{ delete pr.bk_consensus; delete pr.bk_low; delete pr.bk_spread; delete pr.bk_n; }}
console.log(JSON.stringify(_bkHtml(pr, 0, 'sp')));
"""
        r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[:2000]
        return json.loads(r.stdout)

    #: 🚨 `#d97706` 在这张卡上有**两个用途** —— 陈旧年龄,以及离散度 ≥3pp 的表格列
    #: (`dCol = d >= 6 ? '#dc2626' : (d >= 3 ? '#d97706' : ...)`)。所以「整段 HTML 里
    #: 有没有这个色」是个**有歧义的判据**:实测线上一张不该点亮的卡也命中它(离散 4.1pp)。
    #: ⇒ 断言必须钉在 **<summary> 段内、包住年龄的那个 span** 上。
    #: 现有 fixture 用 `bk_spread=[2,2,2]` 恰好躲开了歧义,但那是运气不是设计。
    _AGE_AMBER = re.compile(r'<span style="color:#d97706">[^<]*?[\d.]+h</span>')

    def _summary(self, html: str) -> str:
        m = re.search(r"<summary[^>]*>([\s\S]*?)</summary>", html)
        assert m, f"渲不出 <summary>:{html[:300]}"
        return m.group(1)

    def test_amber_appears_only_when_stale(self):
        near = self._summary(self._render(360, 3))      # 该喊
        far = self._summary(self._render(600, 20))      # 不该喊(平线杀手)
        # 🚨 防空洞:两边都得真渲出年龄,否则「没有琥珀」空洞为真
        assert "6.0h" in near, f"近场没渲出年龄:{near[:300]}"
        assert "10.0h" in far, f"远场没渲出年龄:{far[:300]}"
        assert self._AGE_AMBER.search(near), f"该琥珀却没琥珀:{near[:400]}"
        assert not self._AGE_AMBER.search(far), \
            f"距开球 20h 却染了琥珀(平线回来了):{far[:400]}"

    def test_the_ambiguous_colour_check_would_have_been_wrong(self):
        """⭐ 钉住上一条为什么要收紧:离散 ≥3pp 时,整段 HTML **必然**含 `#d97706`,
        而那张卡**不该**被判陈旧。用「整段含不含这个色」当判据会假红。"""
        far_wide = self._render(600, 20, spread=4.0)
        assert "#d97706" in far_wide, "离散 4pp 没染色 —— 这条前提不成立了,请重看 dCol"
        assert not self._AGE_AMBER.search(self._summary(far_wide)), \
            "年龄被误染 —— 收紧后的判据本身出问题了"

    def test_amber_wraps_the_age_not_something_else(self):
        near = self._summary(self._render(360, 3))
        assert re.search(r'<span style="color:#d97706">[^<]*?6\.0h</span>', near), \
            f"琥珀没有包住年龄那一段:{near[:500]}"

    def test_no_book_data_renders_no_panel_at_all(self):
        """⭐ 让「注入生产 `_hasBk` 而不是打桩」这件事**真的承重**。

        没有这一条,把 `_hasBk` 换成 `() => true` 也全绿(实测空包弹⑬溜过) ——
        那样注入生产原文就只是个摆设。这条走「这场没有多书商数据」那条真分支:
        整块面板不许渲染,自然也不该有陈旧徽章。
        """
        # 🚨 人口非平凡:同一份 pr 带上数据时必须渲出面板,否则「没渲染」空洞为真
        with_bk = self._render(360, 3)
        assert "<summary" in with_bk, f"对照不成立 —— 有数据时也没渲出面板:{with_bk[:200]}"
        without = self._render(360, 3, no_bk=True)
        assert "<summary" not in without, f"没有多书商数据却渲出了面板:{without[:300]}"
        assert "#d97706" not in without, f"没有数据却染了陈旧色:{without[:300]}"

    def test_info_text_explains_what_amber_means_in_both_languages(self):
        """文案缺一侧,`t()` 会静默回落成 key,屏幕上出现 `bk_disclaimer` 字样。

        ⛔ 原来这里是**全文 grep**(`js.count("年龄变琥珀") == 1`)—— 那样把文案
        搬到任何一个**用不上的字典键**里,断言照样绿而屏幕上什么都没有。
        隔壁 `test_book_consensus.py` 已经用空包弹打掉过同一个错并写了处方,
        我在新文件里原地退回去了。⇒ 钉在 `bk_disclaimer` 这个**值**上。
        """
        zh, en = _disclaimer_values()
        for name, body, must in (
            ("中文", zh, ["年龄变琥珀", "它还来得及更新吗", "6.5"]),
            ("英文", en, ["What does an amber age mean?", "can it still update?", "6.5h"]),
        ):
            # 🚨 人口非平凡:先证明我真的取到了那个值,否则下面全是空洞为真
            assert len(body) > 400, f"{name} bk_disclaimer 只取到 {len(body)} 字符,取值逻辑坏了"
            for frag in must:
                assert frag in body, f"{name} bk_disclaimer 里没有「{frag}」"

    def test_disclaimer_extractor_is_not_trivially_true(self):
        """⭐ 上一条依赖 `_disclaimer_values()`;它若退化成「返回全文」,上一条就白写。
        这里证明它真的只取到那一个键的值:另一个键的独有文案**不许**出现在里面。"""
        zh, en = _disclaimer_values()
        js = DASH.read_text(encoding="utf-8")
        assert "输入竞彩 SP 看 EV" in js, "对照锚点不在了,本断言失效"
        assert "输入竞彩 SP 看 EV" not in zh, "取值越界 —— 捞进了别的键"
        assert len(zh) < len(js) / 10, "取到的疑似整段文件"
