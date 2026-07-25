"""2026-07-20 — 竞彩价年龄标(owner 复盘发现的时间戳不同步陷阱)。

EV = P(t₁) × SP(t₂):Pinnacle 侧有 odds_update 年龄标,竞彩侧的 t₂ 此前不可见。
实锤两案:埃尔夫斯堡(让胜峰值价 1.97 定格,实价 1.79,面板 −1.3% vs 真 −9%)、
库奥皮奥(客胜绿灯只存在于 20:39 后的价上,旧价把它藏掉)。修法 = 把
jingcai_sp.captured_at 穿到卡片,>60min 且距开球 <3h 时 amber 提示点 🎯。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from nutmeg.v4.observation.jingcai_sp import fetch_sp_lookup, record_jingcai_sp

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"
ROUTES = REPO / "apps/api/src/nutmeg/v4/api/routes.py"


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


class TestServerSide:
    def test_lookup_carries_captured_at(self, tmp_path):
        db = tmp_path / "obs.db"
        assert record_jingcai_sp(
            db, match_date="2026-07-19", home_team="IF Elfsborg", away_team="Sirius",
            jc_home=3.45, jc_draw=3.65, jc_away=1.77)   # booksum 带内(真实终盘)
        row = fetch_sp_lookup(db, market="had")[("2026-07-19", "IF Elfsborg", "Sirius")]
        # 长度是**故意钉死**的:元组按位取用,悄悄重排会静默错位。加列时更新这里
        # 就是那道「你确实想改形状」的确认。6 → 7(2026-07-25 尾部加
        # single_available);captured_at 仍在 [5],位置没动。
        assert len(row) == 7 and isinstance(row[5], str) and row[5]  # captured_at ISO

    def test_attach_uses_older_of_had_hhad(self):
        # 保守报龄:had/hhad 若分叉,取较旧的捕获时刻(风险在旧的那侧)
        src = ROUTES.read_text(encoding="utf-8")
        assert "p.jc_captured_at = min(stamps)" in src

    def test_schema_field(self):
        from nutmeg.v4.api.schemas import __dict__ as _  # noqa: F401
        src = (REPO / "apps/api/src/nutmeg/v4/api/schemas.py").read_text(encoding="utf-8")
        assert "jc_captured_at: str | None = None" in src


class TestDashboardBadge:
    def test_helper_defined_and_gated(self, html):
        assert "function _jcFreshnessHtml(pr)" in html
        # 只对可投注卡显示;无时间戳不撒谎
        assert "if (!pr || !pr.jc_captured_at || !_isJcBettable(pr)) return '';" in html

    def test_amber_condition_is_1h_and_3h_to_ko(self, html):
        assert "const stale = mins > 60 && hrsToKo < 3;" in html

    def test_wired_into_both_mode_cards(self, html):
        # 市场模式:跟在 Pinnacle 新鲜度行后;标准模式:头部下方
        assert "${_oddsFreshnessHtml(pr)}${_jcFreshnessHtml(pr)}" in html
        assert html.count("${_jcFreshnessHtml(pr)}") >= 2

    def test_icon_system_and_i18n(self, html):
        assert html.count("jc_price_age:") >= 2
        assert html.count("jc_age_stale_tip:") >= 2
        # 图标走 sprite(项目体系),不用 emoji
        assert "${IC('yuan')} ${t('jc_price_age')}" in html
