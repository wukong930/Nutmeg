"""2026-07-07 — 手填实时 Pinnacle 盘口跨会话持久化。

Bug: the 市场模式 手填盘口 (`_cupManualReprice` → pr._manual) lived ONLY in-memory
on _CUPMKT.preds[idx]; switchTab('upcoming') re-runs loadCupMarket every time →
replaces preds → the hand-typed line was wiped (while 竞彩 SP survived via _entered).
Fix: persist it to localStorage keyed by match identity, re-apply on passive load
(tab switch / full reload / reopen), drop it on ↩︎ 复原 or explicit 🔄 refresh.
These substring guards keep a future refactor from silently unwiring it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


class TestCupManualPersist:
    def test_localstorage_helpers_defined(self, html: str) -> None:
        assert "const _LS_CUPMAN = 'nutmeg.cupmkt.manual';" in html
        for fn in ("_cupManKey", "_cupManStore", "_cupManWrite", "_cupManSave",
                   "_cupManForget", "_cupManForgetPreds", "_cupApplyStoredManual"):
            assert f"function {fn}(" in html, fn

    def test_key_is_match_identity(self, html: str) -> None:
        # keyed by home|away|date — same identity the 竞彩 SP restore (_entered) uses.
        assert "(pr.home_team || '') + '|' + (pr.away_team || '') + '|' + (pr.date || '')" in html

    def test_reprice_persists(self, html: str) -> None:
        assert "_cupManSave(pr, { h, d, a, line, o, u," in html

    def test_revert_forgets(self, html: str) -> None:
        assert "_cupManForget(pr);" in html

    def test_load_restores_passively_and_drops_on_manual_refresh(self, html: str) -> None:
        # passive load (tab switch / reload / reopen) re-applies; explicit 🔄 drops it.
        assert "if (opts.manual) _cupManForgetPreds(body.predictions);" in html
        assert "else _cupApplyStoredManual(body.predictions);" in html

    def test_apply_backs_up_fresh_api_line_for_revert(self, html: str) -> None:
        # restore stamps _apiSnapshot from the FRESH pred so ↩︎ 复原 goes to the
        # latest auto odds, not a stale one.
        assert "pr._apiSnapshot = {" in html
        assert "pr._manual = true; pr.odds_update = null;" in html

    def test_prune_stale_entries(self, html: str) -> None:
        # entries for matches whose date < today are pruned so it can't grow forever.
        assert "if (d && d < today) delete store[k];" in html


class TestManualRestoreHealsDerived:
    """2026-07-18 — A′ 上线暴露的洞:localStorage 存的派生 board(P/hc)是**应用当时**
    的服务端 schema。重启前手填的卡被贴回旧 board → 没有 p_*_lo → 让球 EV 区间静默
    消失,badge 还写死「刚刚」,用户无从发现。修法:存的**输入**才是用户数据,派生
    结果 restore 后一律用输入重算(market-reprice 纯计算、零额度)。"""

    def test_restore_triggers_background_reprice(self, html: str) -> None:
        assert "async function _cupManRefreshDerived(" in html
        assert "if (restored.length) _cupManRefreshDerived(restored);" in html
        # 重算用的是存的输入(m.h/m.d/m.a),不是贴回的派生值
        assert "psc_home: m.h, psc_draw: m.d, psc_away: m.a," in html

    def test_refresh_respects_user_revert_race(self, html: str) -> None:
        # 重算返回前用户点了 ↩︎ 复原或 🔄 → 不把手填盖回去
        assert "if (!pr._manual) return;   // 等待期间用户点了 ↩︎ 复原或 🔄" in html

    def test_refresh_resaves_current_schema_keeping_ts(self, html: str) -> None:
        # 回存换上当前 schema 的派生值;...m 展开保留 ts(仍是用户应用的时刻)
        assert ("_cupManSave(pr, { ...m, P: [data.p_home_1x2, data.p_draw_1x2, "
                "data.p_away_1x2]," in html)

    def test_apply_stamps_real_timestamp(self, html: str) -> None:
        assert "pr._manualTs = Date.now();" in html          # 应用时刻
        assert "ts: pr._manualTs," in html                   # 持久化
        assert "pr._manualTs = m.ts || null;" in html        # restore 带回

    def test_badge_reports_real_age_not_static_just_now(self, html: str) -> None:
        # 「刚刚」不再写死在 badge 文案里 —— 三天前的快照曾照说刚刚
        assert "手填实时盘口 · 刚刚" not in html
        assert "(Date.now() - pr._manualTs) / 60000" in html
        for k in ("cupman_just_now",):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"
