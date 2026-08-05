"""2026-07-07 — 手填实时 Pinnacle 盘口跨会话持久化。

Bug: the 市场模式 手填盘口 (`_cupManualReprice` → pr._manual) lived ONLY in-memory
on _CUPMKT.preds[idx]; switchTab('upcoming') re-runs loadCupMarket every time →
replaces preds → the hand-typed line was wiped (while 竞彩 SP survived via _entered).
Fix: persist it to localStorage keyed by match identity, re-apply on EVERY load
(tab switch / full reload / reopen / 🔄 / 🎯); only ↩︎ 复原 drops it.
These substring guards keep a future refactor from silently unwiring it.

2026-07-23 — 语义修正:原设计「显式 🔄 刷新 = 用户要鲜价 → 清掉手填」(而且是从
localStorage 永久删)。owner 实报该行为有害:手填 Pinnacle 正是因为自动线不可信
(欧战资格赛吃 AF 镜像、水位 14.5%),刷一下竞彩价就把手填抹了;🎯 只刷竞彩 SP
更没理由动 Pinnacle 侧。且「不要覆盖了」本有专门按钮(↩︎),🔄 再做一遍等于
**没有任何办法在保留覆盖的前提下刷新**。
"""
from __future__ import annotations

import re
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
                   "_cupManForget", "_cupApplyStoredManual"):
            assert f"function {fn}(" in html, fn

    def test_key_is_match_identity(self, html: str) -> None:
        # keyed by home|away|date — same identity the 竞彩 SP restore (_entered) uses.
        assert "(pr.home_team || '') + '|' + (pr.away_team || '') + '|' + (pr.date || '')" in html

    def test_reprice_persists(self, html: str) -> None:
        assert "_cupManSave(pr, { h, d, a, line, o, u," in html

    def test_revert_forgets(self, html: str) -> None:
        assert "_cupManForget(pr);" in html

    def test_every_load_restores_manual_including_explicit_refresh(self, html: str) -> None:
        """🔄/🎯 只换数据,手填照旧贴回 —— 想回自动线走 ↩︎。
        无分支 = 没有任何一条加载路径会绕过恢复。"""
        assert "_cupApplyStoredManual(body.predictions);" in html
        assert "if (opts.manual) _cupManForgetPreds" not in html

    def test_batch_forget_is_gone(self, html: str) -> None:
        """批量遗忘函数已删:它只被刷新路径用,而刷新不该毁手填。留着 = 死代码 +
        下一个人照着接回去的邀请。单条遗忘(_cupManForget,↩︎ 用)必须还在。"""
        assert "_cupManForgetPreds" not in html
        assert "function _cupManForget(pr)" in html

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
        """⚠️ 本断言按设计变红过**两次**,两次都是同一个原因:形参表加了一个参数
        (2026-07-30 加 `rerender`,2026-08-05 加 `keepModelP`)。

        两次都不是「后台重算没了」——「restore 会触发后台重算」这个性质自始至终
        成立,红的只是我把它写成了「签名逐字等于这一串」。这是
        [[syntactic-proxy-for-semantic-property]] 里那条:**断言值别连带断言结构**。
        同一根线绊两次就该改写法,不是改字面量:现在钉死**前两个形参及其顺序**
        (它们是被调用方真正依赖的契约),后面加参数不再误报。
        行为侧另有覆盖:`test_spcalc_manual_pin.py` 里的
        `test_background_refit_honours_the_flag` 真跑这个函数,断言重渲发生了一次。
        """
        assert re.search(r"async function _cupManRefreshDerived\(pairs, rerender\b", html)
        assert re.search(r"if \(restored\.length\) _cupManRefreshDerived\(restored, rerender\b",
                         html), "restore 不再触发后台重算"
        # 重算用的是存的输入(m.h/m.d/m.a),不是贴回的派生值
        assert "psc_home: m.h, psc_draw: m.d, psc_away: m.a," in html
        # ⭐ 重算完必须重渲调用方那块板(否则那块板永远显示旧 schema 派生值)
        assert "if (rerender) rerender();" in html

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


class TestManualStaleWarning:
    """2026-07-23 — 手填超时提醒。

    同日改掉「🔄 刷新抹掉手填」之后,手填会一直压着自动线直到点 ↩︎ ——
    所以「压了多久」必须自己会喊,否则一个上午填的快照能安静地喂一整天 EV。
    """

    def test_uses_the_two_existing_thresholds_not_a_third(self, html: str) -> None:
        """① 复用自动线的 _ODDS_STALE_MIN(120);② 复用竞彩价年龄标那条
        「>60min 且距开球<3h」的复合规则。发明第三个阈值 = 用户要记三个数。"""
        assert "stale = mins > _ODDS_STALE_MIN || (mins > 60 && hrsToKo < 3);" in html
        assert "const _ODDS_STALE_MIN = 120;" in html

    def test_warns_amber_with_a_tip_not_silently(self, html: str) -> None:
        # 变黄 + 给出下一步(重新核对 / ↩︎ 复原),而不是只变个颜色。
        assert "cupman_stale_tip" in html
        assert html.count("cupman_stale_tip:") == 2, "中英各一条文案"

    def test_fresh_manual_stays_green(self, html: str) -> None:
        # 没超时仍是绿色 ✏️ —— 提醒只在该响的时候响,否则就成了背景噪音。
        assert 'style="color:#059669">✏️ ${t(\'cupman_badge\')}${age}</div>' in html

    def test_no_kickoff_time_never_triggers_the_compound_rule(self, html: str) -> None:
        """拿不到开球时刻 → hrsToKo=Infinity → 复合条件恒假,只剩 120min 那根线。
        不装懂:不知道什么时候开球,就别按「临场」判。"""
        assert "const hrsToKo = isNaN(ko) ? Infinity : (ko - Date.now()) / 3600000;" in html


class TestManualAppliesToBothBoardsOnTheSameTab:
    """2026-07-30 —— 手填**跨板**贴回。

    Bug: `_cupApplyStoredManual` 只在 `loadCupMarket` 里调,而「近期赛事」tab 上
    **上下叠着两块板** —— SP 计算器(`#today-spcalc-section`,`/predictions/sp-calc`,
    3 天窗)和市场模式(`#cupmkt-section`,`/predictions/cup-market`,7 天窗)。
    ⇒ 同一场比赛,上面用 AF 镜像线、下面用手填的真 Pinnacle 线,**两个 EV 摆在
    一屏上**,而 ⚠️「盘口存疑」徽章在上面那块照亮不误(它读 `pr.psc_*`)。
    """

    def test_spcalc_loader_applies_the_stored_manual_fill(self, html: str) -> None:
        # 2026-08-05:调用点加了第三参 keepModelP ⇒ 逐字断言误报。守的性质是
        # 「loadSpCalc 会贴手填」,不是「实参恰好两个」。第三参本身由
        # test_spcalc_manual_pin.py::test_loadspcalc_passes_the_flag 单独钉。
        assert re.search(r"_cupApplyStoredManual\(body\.predictions, _spRerender\b", html), (
            "loadSpCalc 又不贴手填了 —— 同一 tab 两块板会各算各的 EV")

    def test_spcalc_card_shows_the_manual_badge(self, html: str) -> None:
        """⚠️ 贴数据必须同时给标记 —— 只贴不标 = 静默覆盖,比不贴更坏。

        `_oddsFreshnessHtml` 的 `_manual` 分支就是 ✏️ 徽章 + 真实年龄 + 陈旧告警。
        """
        assert "${_oddsFreshnessHtml(pr)}${_jcFreshnessHtml(pr)}" in html
        # 两块板都要有:cup 卡(原有)+ spcalc 卡(本次新增)
        assert html.count("${_oddsFreshnessHtml(pr)}${_jcFreshnessHtml(pr)}") == 2, (
            "少了一块板 —— 手填在那块板上就是没有标记的静默覆盖")

    def test_refresh_derived_rerenders_the_calling_board_not_always_cup(self, html: str) -> None:
        """派生数据后台重算完,要重渲**调用方**那块板。

        原来尾部硬编码 `renderCupMarket`。SP 计算器板接上来之后若不改,那块板会
        一直显示 localStorage 里那份**可能是旧 schema** 的派生值 —— 正是
        2026-07-18 「贴回的旧 board 没有 p_*_lo,让球 EV 区间静默消失」那个洞。
        """
        # 同上:钉前两个形参及顺序,不钉形参个数(见 test_restore_triggers_background_reprice)
        assert re.search(r"async function _cupManRefreshDerived\(pairs, rerender\b", html)
        assert "if (rerender) rerender();" in html
        assert "else renderCupMarket(_CUPMKT.preds, _CUPMKT.pending || []);" in html

    def test_the_surviving_record_path_forwards_provenance(self, html: str) -> None:
        """⭐ 手填一旦能到这块板,记账就**必须**带 `odds_source`。

        `store._request_odds_source` 从 `fixtures[].odds_source` 读它落进
        `recommendation_sessions.odds_source`。漏掉 ⇒ 手打的价按自动源入账,
        而 store.py 明写「绝不默认成 api_football —— 那等于把『没告诉我』伪装成
        『我查过了』」。改这条之前本板不可能有手填,所以漏了不说谎;现在会。
        """
        # 2026-08-06 改写:卡级「已下单」(`_spcalcRecord`/`_spcalcHcRecord`)已按
        # owner 要求删除(recommendation_sessions 由 daily/morning_recommend cron
        # 自动写,手动那份是重复)。⇒ 📌 `_recordBet` 成了**唯一**的手动记账路径,
        # 溯源断言必须跟着搬过来,否则删掉那两个函数的同时就静默丢了 provenance。
        assert "function _spcalcRecord(" not in html, "卡级已下单回来了?溯源断言要一起回来"
        start = html.index("function _recordBet(")
        body = html[start:start + 4000]
        assert "odds_source: pr.odds_source ?? null" in body, (
            "_recordBet 记账漏了溯源 —— 手填价会被记成自动抓取的")
