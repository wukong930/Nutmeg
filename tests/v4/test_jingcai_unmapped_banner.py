"""2026-07-15 — 竞彩未映射横幅(被动可见性): 端点契约 + 面板挂载 + i18n 完整性。

背景(别把这个横幅当可有可无的装饰删掉): 竞彩当天上架 4 场美职联,面板只显示 2 场,
owner 靠人肉比对竞彩 App 才发现。检测器 ``summarize_unmapped`` 其实早就算对了、并在
11:43 精确点名了那 2 场 3 个错名字 —— 但结论只发到易逝的桌面推送(无头 launchd 里
看不见)和一个只有 health_check.sh 才读的文件,**面板上一个字都没有**。缺的是可见性,
不是检测。这个横幅就是那块补丁,所以这些测试守的是「结论能不能到达 owner 的眼睛」。

判据故意复用同一个纯函数 ``summarize_unmapped``,不另立第二套口径 —— 若将来有人想
再造一个检测器,先读 sporttery.py 的 _ZH_OVERRIDES 注释块。
"""
from __future__ import annotations

import json as _json
import re
import subprocess as _sp
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DASH = REPO_ROOT / "apps/api/src/nutmeg/v4/api/static/dashboard.html"

_I18N_KEYS = ("jc_unmapped_title", "jc_unmapped_why", "jc_unmapped_fix", "jc_unmapped_ago",
              "jc_unmapped_gone", "jc_unmapped_partial")

# 今日实盘的「修复前」状态(10 场在售,美职 4 场里 2 场因队名对不上被整场丢弃)
_MATCHES_WITH_GAP = [
    {"league_cn": "巴甲", "home_cn": "博塔弗戈", "away_cn": "桑托斯",
     "home_en": "Botafogo", "away_en": "Santos"},
    {"league_cn": "美职", "home_cn": "蒙特利尔CF", "away_cn": "多伦多FC",
     "home_en": None, "away_en": None},
    {"league_cn": "美职", "home_cn": "芝加哥火焰", "away_cn": "温哥华白帽",
     "home_en": "Chicago Fire", "away_en": "Vancouver Whitecaps"},
    {"league_cn": "美职", "home_cn": "圣路易斯城", "away_cn": "堪萨斯城竞技",
     "home_en": "St. Louis City", "away_en": "Sporting Kansas City"},
    {"league_cn": "美职", "home_cn": "西雅图海湾人", "away_cn": "波特兰伐木工",
     "home_en": "Seattle Sounders", "away_en": None},
]


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


class TestEndpoint:
    def test_names_the_dropped_matches(self, monkeypatch):
        """点名被丢的场,而不是只给个计数 —— 计数逼 owner 反推,名字直接可抄进词典。"""
        from nutmeg.v4.api import routes
        from nutmeg.v4.data.sources import sporttery

        monkeypatch.setattr(sporttery, "fetch_lottery_matches",
                            lambda **kw: list(_MATCHES_WITH_GAP))
        monkeypatch.setattr(sporttery, "lottery_cache_age_seconds", lambda **kw: 1352.0)
        r = routes.jingcai_unmapped_endpoint()

        assert r.ok is True
        assert r.n_matches == 5
        assert len(r.unmapped) == 2
        pairs = {(u["home_cn"], u["away_cn"]) for u in r.unmapped}
        assert ("蒙特利尔CF", "多伦多FC") in pairs
        assert ("西雅图海湾人", "波特兰伐木工") in pairs
        assert r.partial == ["美职 2/4"]     # 同一口径:半数即报
        assert r.gone == []
        assert r.age_seconds == 1352         # 新鲜度必须给,否则又是「看着权威其实过期」

    def test_quiet_when_everything_maps(self, monkeypatch):
        """全映射 → unmapped 空,横幅该消失(补完词典后必须自动闭嘴,否则会被无视)。"""
        from nutmeg.v4.api import routes
        from nutmeg.v4.data.sources import sporttery

        clean = [dict(m, home_en="X", away_en="Y") for m in _MATCHES_WITH_GAP]
        monkeypatch.setattr(sporttery, "fetch_lottery_matches", lambda **kw: clean)
        monkeypatch.setattr(sporttery, "lottery_cache_age_seconds", lambda **kw: 10.0)
        r = routes.jingcai_unmapped_endpoint()
        assert r.ok is True
        assert r.unmapped == []

    def test_fail_soft_on_empty_cache(self, monkeypatch):
        """无缓存 → ok=False 而非抛异常:横幅缺席 ≫ 整个近期赛事页炸掉。"""
        from nutmeg.v4.api import routes
        from nutmeg.v4.data.sources import sporttery

        monkeypatch.setattr(sporttery, "fetch_lottery_matches", lambda **kw: [])
        r = routes.jingcai_unmapped_endpoint()
        assert r.ok is False
        assert r.unmapped == []

    def test_never_hits_the_network_on_page_load(self, monkeypatch):
        """被动横幅必须只读缓存:每次开页都去打竞彩官网既不礼貌也没必要
        (主动抓取是 🎯 刷新竞彩 的活)。守 ttl 极大 + refresh=False 这个契约。"""
        from nutmeg.v4.api import routes
        from nutmeg.v4.data.sources import sporttery

        seen: dict = {}

        def _spy(**kw):
            seen.update(kw)
            return []

        monkeypatch.setattr(sporttery, "fetch_lottery_matches", _spy)
        routes.jingcai_unmapped_endpoint()
        assert seen.get("refresh") is False
        assert seen.get("ttl_seconds", 0) >= 10**8   # 大到永不过期 = 只认缓存


class TestDashboardWiring:
    def test_banner_mounted_in_upcoming_tab(self, html: str):
        assert 'id="jc-unmapped-banner"' in html
        # 必须在近期赛事 tab 里(owner 比对竞彩 App 的就是这一页),且默认隐藏
        upcoming = html.split('id="tab-upcoming"', 1)[1]
        assert 'id="jc-unmapped-banner"' in upcoming.split('id="tab-', 1)[0]
        banner = upcoming.split('id="jc-unmapped-banner"', 1)[1][:200]
        assert "hidden" in banner

    def test_loader_wired_to_tab_and_refresh(self, html: str):
        """开页即跑 + 🎯 刷新竞彩 后重算(补完词典要能立刻看到横幅消失)。

        ⚠️ 2026-08-13 放宽:上一版断言的是
        `"loadJingcaiUnmapped();          // 刚重抓过" in html` ——
        **逐字符的源码行,连注释和那串空格都算**。修 🎯 的时序 bug 时
        (把三个 loader 挪进 `await Promise.allSettled([...])`)它立刻假红,
        而接线**一点没坏**。语法代理测语义属性,今天第三次。
        ⇒ 改成「刷新函数体里**调了**它」,不锁调用点长什么样。
        ⭐ 真正的时序(✅ 必须等三个 loader 跑完)由
        `tests/v4/test_refresh_jingcai_ordering.py` **在 node 里跑真函数**来守。
        """
        assert "async function loadJingcaiUnmapped()" in html
        assert "name === 'upcoming' && typeof loadJingcaiUnmapped === 'function'" in html
        body = html.split("async function _refreshJingcaiInner(", 1)[1]
        body = body.split("\n}", 1)[0]
        assert "loadJingcaiUnmapped(" in body, (
            "🎯 刷新竞彩 之后不再重算未映射横幅 ⇒ 补完词典横幅不会消失")

    def test_external_names_never_reach_innerhtml(self, html: str):
        """竞彩队名是外部数据、本文件没有 HTML 转义器 → 必须走 textContent 建 DOM。"""
        fn = html.split("async function loadJingcaiUnmapped()", 1)[1].split("\n}", 1)[0]
        assert "li.textContent" in fn
        # 只看真代码:注释里提到 innerHTML(解释为何不用它)不算违规
        code = "\n".join(ln for ln in fn.splitlines()
                         if not ln.strip().startswith("//"))
        assert "innerHTML" not in code

    def test_i18n_complete_in_both_locales(self, html: str):
        zh = html.split("const I18N = {", 1)[1].split("  en: {", 1)[0]
        en = html.split("  en: {", 1)[1]
        for k in _I18N_KEYS:
            assert f"{k}:" in zh, f"中文字典缺 {k}"
            assert f"{k}:" in en, f"英文字典缺 {k}"


# ─────────────────────────────────────────────────────────────────────────────
# 2026-08-07 追加 —— 三件,都是被实测推翻后补上的
#
# 起因:owner 问「这提示会不会一直显示」。查下去发现横幅**自己的措辞是错的**:
# 它说「队名对不上词典 → 整场丢弃(join 不了 Pinnacle,算不了 EV)」,而实测
# `/predictions/cup-market` 里 10 场日乙**全在**「待开盘」—— 盘面行来自
# API-Football 的**英文**数据,跟中文词典是两条独立的链。
# 真实成因是上游 AF 此刻不给日乙赛前赔率(实拉 0 条 + 阳性对照 J1 得 14 家书商
# + 同窗口跨联赛 J2 0/10 而其余 14 个联赛 100%)。
# ─────────────────────────────────────────────────────────────────────────────



def _render_banner(payload: dict) -> str:
    """喂一份端点回包,跑**生产函数原文**,拿回它真正塞进横幅的文字。

    行为断言,不是「源码里有没有某个字符串」—— 后者正是本项目栽过最多次的形状。
    """
    html = DASH.read_text(encoding="utf-8")
    body = html.split("async function loadJingcaiUnmapped()", 1)[1]
    # 取到函数结束(与 test_external_names_never_reach_innerhtml 同一个切法)
    fn = "async function loadJingcaiUnmapped()" + body.split("\n}", 1)[0] + "\n}"
    src = f"""
const texts = [];
function mkEl() {{
  return {{ className:'', style:{{}}, _t:'',
            set textContent(v) {{ this._t = v; texts.push(v); }},
            get textContent() {{ return this._t; }},
            appendChild(){{}} }};
}}
const banner = {{ classList:{{ add(){{}}, remove(){{}} }},
                  replaceChildren(...n) {{ banner._n = n; }} }};
global.document = {{ createElement: mkEl }};
const $ = () => banner;
const API = '';
const t = k => k;                     // i18n 键原样返回,便于断言「用了哪个键」
{fn}
global.fetch = () => Promise.resolve({{ json: () => ({_json.dumps(payload)}) }});
loadJingcaiUnmapped().then(() => console.log(JSON.stringify(texts)));
"""
    r = _sp.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:2000]
    return "\n".join(_json.loads(r.stdout or "[]"))


_ONE_GAP = {"ok": True, "n_matches": 39, "age_seconds": 120,
            "unmapped": [{"league_cn": "日乙", "home_cn": "甲", "away_cn": "乙"}],
            "gone": [], "partial": []}


class TestEscalationSignalsReachTheScreen:
    """⭐ `gone`/`partial` 后端一直在算,2026-08-07 之前前端**一个字都没渲染**。

    为什么这条重要:这两个信号对**半修**特别脆。一个联赛在售 2 场、只补好其中
    一场,`gone` 就从 2/2 变 1/2 而归零 —— 窟窿还在,而「整联赛级别」的提示没了。
    看得见它,才知道自己只修了一半。
    """

    def test_gone_league_is_named_on_screen(self):
        out = _render_banner({**_ONE_GAP, "gone": ["日乙"]})
        assert "jc_unmapped_gone" in out, "整联赛全丢却没在横幅上说"
        assert "日乙" in out

    def test_partial_league_is_named_on_screen(self):
        out = _render_banner({**_ONE_GAP, "partial": ["韩职"]})
        assert "jc_unmapped_partial" in out and "韩职" in out

    def test_no_escalation_line_when_neither_fires(self):
        """没升级信号时不能凭空多一行 —— 天天出现的红字三天内会被无视。"""
        out = _render_banner(_ONE_GAP)
        assert "jc_unmapped_gone" not in out and "jc_unmapped_partial" not in out

    def test_the_half_fix_trap_is_real(self):
        """把「半修会打掉 gone」这件事**钉成可执行的证据**,而不是留在注释里。

        端点侧行为:同联赛 2 场全丢 ⇒ gone 有它;修好 1 场 ⇒ gone 空。
        """
        from nutmeg.v4.cli.ingest_sporttery import summarize_unmapped
        both_bad = [
            {"league_cn": "日乙", "home_cn": "a", "away_cn": "b", "home_en": None, "away_en": None},
            {"league_cn": "日乙", "home_cn": "c", "away_cn": "d", "home_en": None, "away_en": None},
        ]
        assert summarize_unmapped(both_bad)["gone"] == ["日乙"]

        half = [dict(both_bad[0], home_en="X", away_en="Y"), both_bad[1]]
        s = summarize_unmapped(half)
        assert len(s["unmapped"]) == 1, "还有一场没修好,却不在名单里"
        assert s["gone"] == [], (
            "本断言不是在要求这个行为『正确』,而是把它**记录成已知陷阱**:"
            "修一半会让『整联赛级别』的信号静默消失。哪天它变了,来改这条测试。")


def _i18n_value(html: str, locale: str, key: str) -> str:
    """抠出**某一条** i18n 键的值。

    ⭐ 为什么不直接在整个字典里 `in`:2026-08-07 变异检验实测,
    「zh 字典里有没有『重启』」这条断言**杀不掉**「把 jc_unmapped_fix 里那句
    重启警告删掉」的变异 —— 因为字典别处也有这两个字,全局搜永远绿。
    断言必须贴着**被测的那一条**,否则它守的是「文件里存在这个词」,
    不是「这条文案说了这件事」。同族:语法代理测语义属性。
    """
    zh = html.split("const I18N = {", 1)[1].split("  en: {", 1)[0]
    en = html.split("  en: {", 1)[1]
    block = zh if locale == "zh" else en
    m = re.search(rf"\n\s*{re.escape(key)}\s*:\s*'", block)
    assert m, f"{locale} 字典里找不到 {key}"
    i = m.end()
    j = block.index("',", i)
    return block[i:j]


class TestBannerDoesNotClaimTheMatchIsDropped:
    """⛔ 横幅**不能**再说「整场丢弃」。

    这不是措辞洁癖:一条骗人的诊断说明会把人引到错的地方去修。实测反例 ——
    2026-08-07 横幅点名 2 场日乙,而 cup-market 里 10 场日乙全在「待开盘」。
    (这条是对**文案本身**的断言;文案就是被测对象,所以不算「语法代理」。)
    """

    def test_zh_and_en_dropped_wording_is_gone(self, html: str):
        assert "整场丢弃" not in _i18n_value(html, "zh", "jc_unmapped_why")
        assert "WHOLE match is dropped" not in _i18n_value(html, "en", "jc_unmapped_why")

    def test_both_locales_say_it_may_still_be_on_the_board(self, html: str):
        """⚠️ 这条是**金丝雀**,钉的是承载主张的那个短语,不是「值里出现过某三个字」。

        变异检验实测:光断言 `"待开盘" in value` **杀不掉**「把主张句删掉」——
        同一条值里的举例(「10 场日乙全都在待开盘区」)也含这三个字,断言照绿。
        改文案时要连这条一起改,那是**有意为之**:上一版文案在盘面上撒了三周谎,
        谎话的代价高过一次改测试的麻烦。真正有牙的是隔壁那条否定式断言
        (不许再说「整场丢弃」),它对措辞不敏感。
        """
        assert "「待开盘」里" in _i18n_value(html, "zh", "jc_unmapped_why"), \
            "中文 why 没说清『比赛可能就在待开盘里』"
        assert "sitting in 待开盘" in _i18n_value(html, "en", "jc_unmapped_why"), \
            "英文 why 没说清 the match may be sitting in 待开盘"

    def test_both_locales_warn_a_restart_is_required(self, html: str):
        """`_ZH_TO_EN` 在 import 时建好、uvicorn 无 --reload ⇒ 不重启横幅会继续
        点名已经修好的队名,而且长得和「词典没修好」一模一样。"""
        assert "重启" in _i18n_value(html, "zh", "jc_unmapped_fix"), \
            "中文修法说明没提『必须重启 API』"
        assert "restart" in _i18n_value(html, "en", "jc_unmapped_fix").lower(), \
            "英文修法说明没提 restart"


class TestJ2OverridesAreAnchoredNotGuessed:
    """日乙两条 override。锚 = AF fixture 1606601 / 1606605,不是照英文猜的译名。"""

    def test_both_resolve(self):
        from nutmeg.v4.data.sources.sporttery import zh_to_canonical
        assert zh_to_canonical("大宫松鼠RB") == "Omiya Ardija"
        assert zh_to_canonical("枥木城") == "Tochigi City"

    def test_the_key_uses_the_character_the_feed_actually_sends(self):
        """🚨 枥(U+67A5) vs 栃(U+6803) —— 两个字在多数字体里几乎一样,但不是同一个。

        原注释写的是「栃木城」,而实盘 feed 写的是「枥木城」。照原注释复制粘贴
        会补出一条**永远匹配不上**的键,且不报错。这条把字面钉在码点上。
        """
        from nutmeg.v4.data.sources.sporttery import _ZH_OVERRIDES
        assert "枥木城" in _ZH_OVERRIDES
        assert [hex(ord(c)) for c in "枥木城"] == ["0x67a5", "0x6728", "0x57ce"]
        assert "栃木城" not in _ZH_OVERRIDES, (
            "补了竞彩数据里根本不存在的写法 = 死键。要补先去 feed 里确认这个字符串真出现过。")

    def test_values_are_exact_keys_of_the_canonical_dict(self):
        """值必须是盘面真用的拼法。这里用 TEAM_NAME_ZH 精确键当判据 ——
        ⛔ 不能改用 odds_snapshots 行数:日乙休赛期正好错开我们的采集窗口,
        「总行数 0」在那种情况下和「拼法是错的」长得一模一样。"""
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH
        for zh in ("大宫松鼠RB", "枥木城"):
            from nutmeg.v4.data.sources.sporttery import _ZH_OVERRIDES
            assert _ZH_OVERRIDES[zh] in TEAM_NAME_ZH

    def test_the_two_j2_fixtures_now_resolve_end_to_end(self):
        """端到端:用 2026-08-08/09 那两场的**真实中文写法**跑判据,应当零缺口。"""
        from nutmeg.v4.cli.ingest_sporttery import summarize_unmapped
        from nutmeg.v4.data.sources.sporttery import zh_to_canonical
        real = [
            {"league_cn": "日乙", "home_cn": "大宫松鼠RB", "away_cn": "新潟天鹅"},
            {"league_cn": "日乙", "home_cn": "山形山神", "away_cn": "枥木城"},
        ]
        for m in real:
            m["home_en"] = zh_to_canonical(m["home_cn"])
            m["away_en"] = zh_to_canonical(m["away_cn"])
        s = summarize_unmapped(real)
        assert s["unmapped"] == [] and s["gone"] == [], f"仍有缺口:{s}"
