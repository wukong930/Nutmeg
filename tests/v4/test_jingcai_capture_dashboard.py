"""体检 — silent 竞彩 SP staleness capture wired into the spcalc recompute."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


class TestJingcaiCapture:
    def test_helper_defined(self, html):
        assert "function _jcStaleCapture(" in html

    def test_wired_into_both_modes(self, html):
        # 标准模式 (_SPCALC/_spcalcRecalc) AND 市场模式 (_CUPMKT/_cupRecalc) both
        # capture every pre-kickoff re-price
        assert "_jcStaleCapture(_SPCALC.preds[idx], 'spcalc-sp'" in html
        assert "_jcStaleCapture(_CUPMKT.preds[idx], 'cupsp'" in html

    def test_handicap_wired_both_modes(self, html):
        # 让球 (hhad) capture wired into both boards' handicap recompute
        assert "function _jcStaleCaptureHc(" in html
        assert "_jcStaleCaptureHc(_SPCALC.preds[idx], 'spcalc-hcsp'" in html
        assert "_jcStaleCaptureHc(_CUPMKT.preds[idx], 'cuphcsp'" in html
        assert "market: 'hhad', handicap_home: line" in html

    def test_posts_to_endpoint(self, html):
        assert "/observation/jingcai-sp" in html

    def test_debounced_and_silent(self, html):
        assert "_jcCapT" in html and "setTimeout" in html  # debounced
        assert ".catch(() => {})" in html                  # fire-and-forget

    def test_only_complete_1x2_captured(self, html):
        assert "if (!(oh && od && oa)) return;" in html

    def test_skips_official_prefill(self, html):
        # Render pre-fills the input with the attached 竞彩 SP; re-capturing it as
        # market_mode re-stamps the official feed (the "🎯 refreshed but didn't
        # update" bug). Only a genuine override (value ≠ attached) may write.
        assert "_eq(oh, pr.jc_home) && _eq(od, pr.jc_draw) && _eq(oa, pr.jc_away)) return;" in html
        assert "line === pr.jc_hc_line && _eq(oh, pr.jc_hc_home)" in html

    def test_preserve_only_genuine_overrides(self, html):
        # The 4th-layer "刷新了却没更新" root cause: renderCupMarket/renderTodaySpCalc
        # preserved the displayed 竞彩 SP across a re-render, but the displayed value
        # IS the (now-stale) server pre-fill — so a 🎯 刷新竞彩 fetching a FRESHER
        # pre-fill got clobbered by the value being "preserved". Fix: preserve only a
        # genuine override (value ≠ the pre-fill p.jc_*), letting the fresh pre-fill win.
        assert "const _isPf = (v, pf) => pf != null" in html
        assert "if (el && el.value && !_isPf(el.value, pf)) bucket[o] = el.value;" in html  # both boards
        assert "String(lsel.value) !== String(p.jc_hc_line)) bucket.hcline" in html

    def test_manual_refresh_fresh_wins(self, html):
        # 用户要「手动刷新后以刷新数据为主」: 手动刷新(🔄/🎯/加载)带 manual:true →
        # loadCupMarket 置 _CUPMKT._freshWins → renderCupMarket 跳过 _entered 保留 →
        # 服务端新数据(Pinnacle + 竞彩 + 让球)全胜出、重算显示。静默 60s 轮询不带
        # manual → 仍保留正在输入的值,避免后台抹掉手输。
        assert "_CUPMKT._freshWins = !!opts.manual;" in html
        assert "const _freshWins = _CUPMKT._freshWins; _CUPMKT._freshWins = false;" in html
        assert "if (!_freshWins) {" in html
        assert "loadCupMarket({manual:true})" in html                    # 加载 + 🎯 刷新竞彩
        assert "loadCupMarket({refreshOdds:true, manual:true})" in html  # 🔄 刷新盘口

    def test_cache_bumped(self):
        # Format-based (not pinned to one slug): _FE_VERSION must follow the
        # nutmeg-vN-fe-<slug> convention so the SW cache-busts each deploy.
        import re
        routes = (REPO / "apps/api/src/nutmeg/v4/api/routes.py").read_text()
        assert re.search(r'_FE_VERSION = "nutmeg-v\d+-fe-[a-z0-9-]+"', routes)
