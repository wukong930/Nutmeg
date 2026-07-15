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

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DASH = REPO_ROOT / "apps/api/src/nutmeg/v4/api/static/dashboard.html"

_I18N_KEYS = ("jc_unmapped_title", "jc_unmapped_why", "jc_unmapped_fix", "jc_unmapped_ago")

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
        assert "async function loadJingcaiUnmapped()" in html
        # 开页即跑 + 🎯 刷新竞彩 后重算(补完词典要能立刻看到横幅消失)
        assert "name === 'upcoming' && typeof loadJingcaiUnmapped === 'function'" in html
        assert "loadJingcaiUnmapped();          // 刚重抓过" in html

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
