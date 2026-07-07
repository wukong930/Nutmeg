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
