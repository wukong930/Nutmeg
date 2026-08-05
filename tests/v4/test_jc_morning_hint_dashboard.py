"""2026-07-19 — 竞彩晨批提示 + 09:50 补捕窗口的防回归护栏.

Root-cause 2026-07-18(docs/jingcai_batch_opening_2026-07-18.md):竞彩把当日新场
放在北京 09:25–09:45 晨批发布(北欧等小联赛当天才上架),owner 早上看板时它们
**确实还没开售** —— 不是采集/join 缺口。两个缓解都是「别把分批开售误读成数据丢失」:
① 面板北京 11:10 前在可投注区顶部亮晨批提示;② sporttery_open cron 加 09:50 窗口,
把同日新场的首捕从 11:05 拉近到发布后 ≤26 分钟。这些 substring 守卫防止未来重构
静默拆掉任一半。
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"
SETUP = REPO / "scripts/setup_local_pipeline.sh"


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


class TestMorningHint:
    def test_helper_defined(self, html: str) -> None:
        assert "function _jcMorningHintHtml()" in html

    def test_window_closes_after_1110_beijing(self, html: str) -> None:
        # 提示只在北京 11:10 前显示(11:05 补捕 cron 收尾后不再打扰);北京=固定 UTC+8。
        assert "new Date(Date.now() + 8 * 3600e3)" in html
        assert ">= 11 * 60 + 10) return '';" in html

    def test_shown_regardless_of_whether_anything_is_bettable(self, html: str) -> None:
        """守的性质没变:**别把分批开售误读成数据丢失**,所以有没有可投注场次都要提示。

        2026-08-05 可投注区搬进全局容器 `#jc-bettable-global` ⇒ 原来的「两条分区路径」
        (有 bett / 无 bett)在新版式里塌成一处:提示挂在容器上,由 `_bettableGlobalSync`
        统一渲染。而且比原来**更强** —— 一场都没有时容器仍会因为提示而露面,
        那正是「名单还没出全」的时刻,恰恰最该看见它。
        """
        i = html.index("function _bettableGlobalSync(")
        body = html[i:html.index("\nfunction ", i + 10)]
        assert "hint.innerHTML = _jcMorningHintHtml();" in body
        # 零场次 + 有提示 ⇒ 仍然显示(!n && !hint 才隐藏)
        assert "wrap.classList.toggle('hidden', !n && !(hint && hint.innerHTML.trim()));" in body

    def test_i18n_keys_present_both_locales(self, html: str) -> None:
        # zh + en 字典各一条 + 渲染处 t() 引用 ≥1。
        assert html.count("jc_morning_hint") >= 3
        assert "t('jc_morning_hint')" in html
        assert "jc_morning_hint:  '竞彩分批上架" in html
        assert "jc_morning_hint:  '竞彩 lists same-day additions" in html

    def test_uses_sprite_icon_not_emoji(self, html: str) -> None:
        # 图标体系:提示行走 Tabler sprite(IC),不再新增 emoji 图标。
        assert "${IC('hourglass')} ${t('jc_morning_hint')}" in html


class TestOpenCronMorningWindow:
    def test_sporttery_open_has_0950_window(self) -> None:
        # sporttery_open 的 install_job 调用必须带 "9:50" 附加窗口(晨批发布实测
        # 09:24–09:44 → 09:50 首捕;11:05 保留扫尾)。按 label 切块断言,避免误配
        # 其他 job 的窗口参数。
        sh = SETUP.read_text(encoding="utf-8")
        blocks = sh.split('install_job "')
        open_block = next(b for b in blocks if b.startswith("com.nutmeg.sporttery_open"))
        assert '"9:50"' in open_block
