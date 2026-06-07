"""V12 W3 — 竞彩 SP live calculator (single 1X2): markup + i18n + JS-hook guard.

The calculator is pure client-side: model P (from the today response's
``single_match_predictions``) × the user-entered 竞彩 SP → live EV / Kelly,
recorded to the observation DB only when the user clicks 已下单. Recompute
on every SP keystroke needs no server round-trip (P is market-agnostic).

These tests guard the dashboard markup, JS hooks, and i18n completeness
against accidental removal. The numeric contract is covered elsewhere:
``test_today_recommendations.test_single_match_predictions_populated_for_spcalc``
(model P + psc reach the client) and the /recommend/single endpoint tests
(server-authoritative stake math on record).
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DASH = REPO_ROOT / "apps/api/src/nutmeg/v4/api/static/dashboard.html"
ROUTES = REPO_ROOT / "apps/api/src/nutmeg/v4/api/routes.py"


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


class TestSpCalcMarkup:
    def test_section_present(self, html):
        assert 'id="today-spcalc-section"' in html
        assert 'id="today-spcalc-list"' in html

    def test_model_vs_market_1x2_shown(self, html):
        """V13 — each model-board outcome row shows the Pinnacle de-vig market
        1X2 (`市`/`Mkt`) next to the model P, for an at-a-glance divergence
        check. Transparency only — the recommendation still uses model P."""
        assert "const Mkt = (() => {" in html        # client-side de-vig
        assert "t('spcalc_mkt')" in html
        for k in ("spcalc_mkt", "spcalc_mkt_tip"):
            assert html.count(k + ":") >= 2, f"i18n {k!r} missing from a locale"

    def test_pending_fixtures_render(self, html):
        # V12 W6 — 待开盘 section: renderTodaySpCalc takes a `pending` arg and
        # builds non-interactive 待开盘 cards (no SP inputs) for fixtures whose
        # Pinnacle line hasn't opened.
        assert "renderTodaySpCalc(preds, bankroll, kelly, minEv, pending)" in html
        assert "pendingCardHtml" in html
        assert "spcalc_pending_title" in html
        assert "spcalc_pending_badge" in html
        # Loader threads body.pending_fixtures into the renderer.
        assert "body.pending_fixtures" in html

    def test_cup_market_section_present(self, html):
        # V12 W7 — 🏆 杯赛市场模式: user-triggered, Pinnacle de-vig priced.
        assert 'id="cupmkt-section"' in html
        assert 'id="cupmkt-list"' in html

    def test_cup_market_has_refresh_odds_button(self, html):
        """V13 — 市场模式 gets a 🔄 刷新盘口 button that forces a live Pinnacle
        pull (refresh_odds=true); the plain 加载 button stays cache-only."""
        assert 'id="cupmkt-refresh"' in html
        assert "loadCupMarket({refreshOdds:true})" in html
        assert "'?days=3&refresh_odds=true'" in html
        assert "async function loadCupMarket(opts = {})" in html

    def test_cup_market_label_drops_cups_j1_text(self, html):
        """V13 — 市场模式 now covers J1/J2/cups/WC/10 expansion leagues, so the
        misleading '(杯赛 + 日职联)' / '· Cups + J1' parenthetical was dropped."""
        assert "杯赛 + 日职联" not in html
        assert "· Cups + J1" not in html
        assert "(cups + J1)" not in html

    def test_cup_market_preserves_sp_on_refresh(self, html):
        """V13 — a 市场模式 refresh must KEEP the user's hand-typed 竞彩 SP +
        让球线 (it used to wipe them on every re-render). renderCupMarket now
        mirrors the model board's capture-before / restore-after pattern."""
        # The keyed restore lookup now appears in BOTH renderers (model + cup).
        phrase = "_entered[pr.home_team + '|' + pr.away_team + '|' + pr.date]"
        assert html.count(phrase) >= 2
        # Cup-market restore touches the cup-specific SP input classes.
        assert ".cupsp[data-idx=" in html
        assert ".cuphcsp[data-idx=" in html
        # V14 — the FULL board lives in 近期赛事 (manual 加载 button restored); the
        # 今日推荐 💠 block is a read-only mirror, and loadCupMarket also auto-loads.
        assert 'onclick="loadCupMarket()"' in html
        assert "if (typeof loadCupMarket === 'function') loadCupMarket();" in html
        assert "async function loadCupMarket" in html
        assert "function renderCupMarket" in html
        assert "function _cupRecalc" in html
        assert "/predictions/cup-market" in html
        # market-mode badge (NOT model P) + 90-min settle caveat in the hint
        assert "cupmkt_badge" in html
        assert "90 分钟" in html

    def test_js_hooks_present(self, html):
        for fn in (
            "function renderTodaySpCalc(",
            "function _spcalcRecalc(",
            "async function _spcalcRecord(",
            "function _spcalcStake(",
        ):
            assert fn in html, f"missing JS function: {fn}"

    def test_hosted_in_upcoming_tab(self, html):
        # V12 W3 — the calculator moved to its own 近期赛事 tab, fed by
        # loadSpCalc → GET /predictions/sp-calc (3-day window), NOT the
        # today-recommendations loader.
        assert 'data-tab="upcoming"' in html          # nav button
        assert 'id="tab-upcoming"' in html            # tab panel
        assert "function loadSpCalc(" in html
        assert "/predictions/sp-calc" in html
        assert "renderTodaySpCalc(body.predictions" in html
        # and it's NO LONGER rendered from the today loader
        assert "renderTodaySpCalc(body.single_match_predictions" not in html

    def test_record_posts_to_single_with_record_session(self, html):
        # 已下单 records the placed bet (once) via /recommend/single.
        assert "/recommend/single" in html
        assert "record_session: true" in html

    def test_kelly_formula_mirrors_jingcai(self, html):
        # edge/(SP-1) fractional Kelly + 5% cap + ¥2 quantize.
        assert "edge / (sp - 1.0)" in html
        assert "bankroll * 0.05" in html
        assert "Math.floor(stake / 2) * 2" in html

    def test_refresh_odds_button_wired(self, html):
        # 🔄 刷新盘口: button + handler + client→server flag plumbing.
        assert 'id="today-spcalc-refresh"' in html
        assert "function _spcalcRefreshOdds(" in html
        assert "refreshOdds: true" in html          # handler → loadToday
        assert "refresh_odds: true" in html          # loadToday → request body

    def test_typed_sp_preserved_across_rerender(self, html):
        # renderTodaySpCalc snapshots/restores entered SP so 刷新 doesn't wipe it.
        assert "_entered" in html

    def test_handicap_block_wired(self, html):
        # V12 W3 让球: line selector + per-line P + handicap SP inputs + record.
        assert 'id="spcalc-hcline-${idx}"' in html
        assert "class=\"spcalc-hcsp" in html
        for fn in ("function _spcalcHcLine(", "function _spcalcHcRecalc(",
                   "async function _spcalcHcRecord(", "function _spcalcHcP("):
            assert fn in html, f"missing handicap fn: {fn}"
        # handicap record posts handicap_home + odds_handicap_* (not odds_1x2).
        assert "handicap_home: line" in html
        assert "odds_handicap_H: oh" in html


class TestSpCalcI18n:
    REQUIRED_KEYS = [
        "h_today_spcalc", "today_spcalc_hint", "spcalc_n_matches",
        "spcalc_enter_sp", "spcalc_record_btn", "spcalc_pick", "spcalc_suggest",
        "spcalc_nobet", "spcalc_recorded", "spcalc_recorded_btn",
        "spcalc_record_err", "spcalc_need_all_sp", "spcalc_jc", "spcalc_fair",
        "spcalc_refresh_btn", "spcalc_refreshing",
        "spcalc_hc_toggle", "spcalc_hc_line", "spcalc_hc_level",
        "spcalc_hc_h", "spcalc_hc_d", "spcalc_hc_a", "spcalc_hc_pickline",
        # V12 W6 — 待开盘 (Pinnacle not open)
        "spcalc_pending_title", "spcalc_pending_hint", "spcalc_pending_badge",
        # V12 W7 — 🏆 杯赛市场模式 (full board lives in 近期赛事)
        "cupmkt_load_btn", "cupmkt_hint", "h_cupmkt", "cupmkt_empty", "cupmkt_badge",
        # V14 — 💠 市场模式预测 (read-only mirror on 今日推荐)
        "h_mktpred", "mktpred_empty",
    ]

    def test_each_key_defined_in_both_locales(self, html):
        # Each key must be defined in BOTH the zh and en dict (the dict entry
        # is `key:` — distinct from the data-i18n="key" / t('key') uses).
        for k in self.REQUIRED_KEYS:
            assert html.count(k + ":") >= 2, (
                f"i18n key {k!r} missing from zh or en dict (found "
                f"{html.count(k + ':')} dict entries, need 2)"
            )


class TestSpCalcCacheBust:
    def test_cache_version_in_v12_fe_family(self):
        # Assert only the stable `nutmeg-v*` prefix, NOT a week/feature slug —
        # the slug changes on every bump (w3-spcalc → … → v13-jc-diag), so
        # pinning the week/slug makes the test break on each ship (it did, 3×).
        src = ROUTES.read_text(encoding="utf-8")
        assert "const CACHE_VERSION = 'nutmeg-v" in src, (
            "SW CACHE_VERSION missing or not in the nutmeg-v* family"
        )


class TestSpCalcPolish:
    """V12 W4 — 近期赛事 card polish: league 中文 label + accent color,
    group-by-league, kickoff date+time + chronological sort, team-name
    accent/affix fold for API-spelling variants."""

    def test_league_label_helpers(self, html):
        assert "const LEAGUE_ZH" in html
        assert "function zhLeague(" in html
        # all 14 trained leagues' 中文 labels present in the map
        for zh in ("英超", "西甲", "意甲", "德甲", "法甲", "英冠", "西乙",
                   "意乙", "德乙", "法乙", "荷甲", "葡超", "比甲", "日职联"):
            assert zh in html, f"LEAGUE_ZH missing {zh}"

    def test_league_color_helpers(self, html):
        assert "const LEAGUE_COLOR" in html
        assert "function leagueColor(" in html

    def test_group_by_league_render(self, html):
        # Cards group under colored league headers, ordered + sorted by kickoff.
        for s in ("spcalc-lg-group", "spcalc-lg-head", "byLeague",
                  "zhLeague(lg)", "leagueColor(lg)", "cardHtml(o.pr, o.idx)"):
            assert s in html, f"grouping markup missing: {s}"

    def test_kickoff_display_and_sort(self, html):
        assert "function _fmtKickoff(" in html
        assert "function _kickoffMs(" in html
        # card top-right now shows kickoff (date+time); old "league · date"
        # span removed (league moved to the group header).
        assert "${_fmtKickoff(pr)}" in html
        assert "${pr.league} · ${pr.date}" not in html

    def test_team_name_accent_affix_fold(self, html):
        # zhTeam falls back to a folded key on exact miss (e.g. "Granada CF" →
        # "Granada", "Castellón" → "Castellon") so API-spelling variants resolve.
        assert "function _zhFold(" in html
        assert "_zhFold(name)" in html

    def test_missing_teams_added_to_dict(self):
        from nutmeg.v4.data.team_name_zh import TEAM_NAME_ZH as D
        assert D.get("Ceuta") == "休达"
        assert D.get("Cultural Leonesa")          # present (non-empty)
        assert D.get("Real Sociedad II")          # reserve side mapped


class TestParlayBasket:
    """V12 W5 — 串关篮子: tick 「串」 across matches → combined EV/Kelly →
    记录串关 POSTs the exact legs to /recommend/parlay (double-gated)."""

    def test_basket_markup_present(self, html):
        for s in ('id="parlay-basket"', 'id="parlay-legs"', 'id="parlay-summary"',
                  'id="parlay-record-btn"', 'class="spcalc-parlay-cb"'):
            assert s in html, f"missing basket markup: {s}"

    def test_basket_js_hooks(self, html):
        for fn in ("function _parlayToggle(", "function _parlayRender(",
                   "async function _parlayRecord(", "function _parlayClear(",
                   "function _parlayRestore("):
            assert fn in html, f"missing parlay fn: {fn}"

    def test_checkbox_on_1x2_rows(self, html):
        # Each 1X2 outcome row carries the parlay toggle wired to _parlayToggle.
        assert 'onchange="_parlayToggle(${idx}' in html

    def test_records_to_parlay_endpoint(self, html):
        assert "/recommend/parlay" in html
        # explicit legs + double-gate flag
        assert "market_type: '1x2'" in html
        assert "record_session: true" in html

    def test_wired_into_calculator(self, html):
        # SP edits refresh the basket; re-render re-checks legs.
        assert "_parlayRestore();" in html
        assert "if (typeof _parlayRender === 'function') _parlayRender();" in html

    def test_combined_math_is_product(self, html):
        # ∏P and ∏SP (parlay hit prob + odds) computed client-side for display.
        assert "prodP *= P" in html
        assert "prodSP *= sp" in html
        # stake reuses the single-leg Kelly helper on the combined P + odds
        assert "_spcalcStake(prodP, prodSP, bankroll, kelly)" in html

    def test_i18n_keys_both_locales(self, html):
        for k in ("parlay_title", "parlay_clear", "parlay_record_btn", "parlay_need_2",
                  "parlay_legs", "parlay_combined_p", "parlay_combined_odds",
                  "parlay_recorded", "parlay_add", "parlay_cb"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"


class TestTwoBoardToday:
    """V12 W5 — 今日推荐 split into 🌍 国际盘口推荐 (Pinnacle, auto) + 💴 竞彩盘口
    推荐 (priced at the 竞彩 SP filled in 近期赛事). Same engine, two odds sources;
    the today renderers are parameterized by a DOM prefix to serve both boards."""

    def test_board_headers_present(self, html):
        assert 'data-i18n="board_intl"' in html
        assert 'data-i18n="board_jc"' in html

    def test_jc_board_sections(self, html):
        for s in ('id="jc-single-section"', 'id="jc-parlay-section"', 'id="jc-pool-section"',
                  'id="jc-single-list"', 'id="jc-parlay-list"', 'id="jc-pool-list"',
                  'id="jc-generate"', 'id="jc-status"'):
            assert s in html, f"missing 竞彩 board markup: {s}"

    def test_renderers_parameterized_by_prefix(self, html):
        assert "function renderTodaySingle(single, pfx = 'today')" in html
        assert "function renderTodayParlay(parlay, pfx = 'today')" in html
        assert "function renderTodayPool(pool, pfx = 'today')" in html
        assert "$('#' + pfx + '-single-list')" in html

    def test_parlay_legs_translate_team_names(self, html):
        """V13 — parlay legs carry only match_id (LEAGUE_Home_vs_Away); they
        must strip the league prefix, split on _vs_, and zhTeam() each side.
        Regression: the old split('|') delimiter was wrong → showed the raw
        English match_id with no translation."""
        assert "l.match_id.split('|').slice(0, 2)" not in html   # bug gone
        assert "raw.includes('_vs_') ? raw.split('_vs_')" in html
        assert "${zhTeam(parts[0])} <span class=\"text-muted\">vs</span> ${zhTeam(parts[1])}" in html  # noqa: E501

    def test_jc_loader_wired(self, html):
        assert "function loadJingcaiBoard(" in html
        assert "function _collectJingcaiFixtures(" in html
        assert "/recommend/jingcai" in html
        # 竞彩 board reuses the shared renderers with pfx='jc'
        assert "renderTodaySingle(body.single, 'jc')" in html
        assert "renderTodayParlay(body.parlay, 'jc')" in html
        assert "renderTodayPool(body.pool, 'jc')" in html
        # collects 竞彩 odds_1x2 + 让球 from the 近期赛事 calculator state
        assert "fx.odds_1x2_H = oh" in html
        assert "fx.odds_handicap_H = hh" in html

    def test_jc_collects_both_boards(self, html):
        # Regression (the long debug saga): the 竞彩 board must collect SP from
        # BOTH the 模型模式 (_SPCALC, .spcalc-*) AND the 市场模式 (_CUPMKT, .cup*;
        # 杯赛 + J1/日职). It used to read only _SPCALC, so 竞彩 SP entered on a
        # 市场模式 (e.g. 日职) card — where the user actually bets — was invisible
        # to the generator → the misleading "先去近期赛事填竞彩 SP".
        assert "_collectBoard(_SPCALC.preds, 'spcalc-sp'" in html
        assert "_collectBoard(_CUPMKT.preds, 'cupsp'" in html

    def test_two_board_i18n_keys(self, html):
        for k in ("board_intl", "board_intl_hint", "board_jc", "board_jc_hint",
                  "jc_generate", "jc_need_sp", "jc_computing", "jc_recs", "jc_none"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"


class TestManualReverseCalc:
    """V12 W8c — 🧮 手动反推计算器: type Pinnacle 盘口 by hand (incl. the O/U
    line) → POST /recommend/market-handicap → reverse 让球 + EV. The fallback
    for fixtures the API never quoted a line for (e.g. some J1 matchdays)."""

    def test_form_present(self, html):
        assert 'id="manual-reverse"' in html
        for fld in ("mrev-p1", "mrev-px", "mrev-p2", "mrev-ouline",
                    "mrev-over", "mrev-under", "mrev-hcap",
                    "mrev-jh", "mrev-jd", "mrev-ja", "mrev-result"):
            assert f'id="{fld}"' in html, f"missing input #{fld}"

    def test_handler_defined_and_wired(self, html):
        assert "async function manualReverseCalc()" in html
        assert 'onclick="manualReverseCalc()"' in html

    def test_handler_posts_with_ou_line(self, html):
        # Must send the user's O/U line so the server fits the right total.
        assert "/recommend/market-handicap" in html
        assert "ou_line: ouline" in html
        assert "handicap_home: hcap" in html

    def test_ouline_defaults_to_quarter(self, html):
        # Pinnacle's J1 main total is usually a quarter line — default 2.25.
        assert 'id="mrev-ouline" type="number" inputmode="decimal" step="0.25" value="2.25"' in html

    def test_i18n_keys_present_both_locales(self, html):
        for k in ("mrev_title", "mrev_hint", "mrev_pin1x2", "mrev_ou",
                  "mrev_hcap_lbl", "mrev_jc_hc", "mrev_calc", "mrev_fair",
                  "mrev_let_labels", "mrev_1x2_labels", "mrev_err_inputs",
                  "mrev_err_hcap", "mrev_calculating", "mrev_no_ou"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"

    # V12 W8d — 📌 记一笔 (record the manual bet to the observation DB)
    def test_record_button_and_league_field(self, html):
        assert 'id="mrev-record-btn"' in html
        assert 'onclick="manualReverseRecord()"' in html
        assert 'id="mrev-league"' in html        # real league → auto-settle
        assert 'id="mrev-record-status"' in html

    def test_record_handler_posts_with_record_flag(self, html):
        assert "function _mrevBuildBody(record)" in html
        assert "async function manualReverseRecord()" in html
        assert "record_session: record" in html
        # records the real league (not the throwaway 'MANUAL' compute sentinel)
        assert "record ? (gv('mrev-league') || 'MANUAL') : 'MANUAL'" in html
        # honest feedback when the server-side gate is off
        assert "data.recorded" in html

    def test_record_i18n_both_locales(self, html):
        for k in ("mrev_record", "mrev_record_ok", "mrev_record_off",
                  "mrev_league_lbl"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"


class TestTodayInlineRecord:
    """V12 W8i — 今日推荐 single cards get an inline 竞彩 SP + 📌 control so a pick
    can be recorded (and then auto-settled / win-loss tracked) without leaving
    the landing page. The card echoes psc_* from the ticket; the server
    recomputes P on record (never trusts a client P)."""

    def test_sp_input_and_record_button_present(self, html):
        assert 'class="today-rec-sp' in html       # per-card 竞彩 SP input
        assert 'id="today-rec-btn-' in html         # per-card 📌
        assert "_todayRecCalc(" in html             # live EV-at-SP recompute
        assert "_todayRecRecord(" in html           # record handler wired

    def test_record_row_only_on_today_landing(self, html):
        # Not duplicated onto the reused 'jc' board (would clash on data-i ids).
        assert "const showRec = (pfx === 'today')" in html

    def test_routes_1x2_to_single_and_handicap_to_market(self, html):
        # 1x2 → /recommend/single ; 让球 → /recommend/market-handicap.
        assert "/recommend/single" in html
        assert "/recommend/market-handicap" in html
        assert "tk.market_type === 'handicap_1x2'" in html

    def test_client_gate_mirrors_5pct_discipline(self, html):
        assert "_TODAY_REC_GATE = 0.05" in html
        assert "ev >= _TODAY_REC_GATE" in html

    def test_record_posts_opt_in_flag(self, html):
        # Both record branches must opt in to the double-gate.
        assert html.count("record_session: true") >= 1

    def test_handicap_record_threads_outcome_and_line(self, html):
        # 让球 record sends the chosen outcome's 竞彩 odds + the handicap line.
        assert "'odds_handicap_' + tk.outcome" in html
        assert "handicap_home: tk.handicap_home" in html

    def test_i18n_keys_both_locales(self, html):
        for k in ("today_rec_jcsp", "today_rec_btn", "today_rec_done",
                  "today_rec_gateoff"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"

    def test_cache_version_bumped_in_family(self):
        txt = ROUTES.read_text(encoding="utf-8")
        # Just assert a CACHE_VERSION constant in the stable nutmeg-v* family —
        # not a specific week/slug (that pin broke on every legitimate bump).
        assert "const CACHE_VERSION = 'nutmeg-v" in txt


class TestSelfCheckScoreboard:
    """V12 W8j — 推荐追溯 gets a 模型自我体检 card: non-竞彩 prediction accuracy
    + Layer A calibration status, fed by /observation/prediction-scoreboard."""

    def test_card_markup_present(self, html):
        assert 'id="scoreboard-body"' in html
        assert 'data-i18n="h_scoreboard"' in html

    def test_js_wired_to_endpoint(self, html):
        assert "function renderScoreboard" in html
        assert "async function loadScoreboard" in html
        assert "/observation/prediction-scoreboard" in html

    def test_loads_with_history_tab(self, html):
        # loadScoreboard() fires when the 推荐追溯 tab loads.
        assert "async function loadHistory() {\n  loadScoreboard();" in html

    def test_shows_pinnacle_baseline_and_delta(self, html):
        # Honest: hit-rate ships next to the Pinnacle baseline + the Δ.
        assert "sb_vs_pin" in html
        assert "sb_delta" in html
        assert "sb_honest" in html

    def test_calibration_status_rendered(self, html):
        assert "sb_cal_never" in html
        assert "Layer A" in html

    def test_i18n_keys_both_locales(self, html):
        for k in ("h_scoreboard", "sub_scoreboard", "sb_settled", "sb_model_hit",
                  "sb_logloss", "sb_delta", "sb_cal_never", "sb_honest",
                  "sb_accumulating"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"

    def test_auto_refreshes_on_visibility(self, html):
        # Returning to a visible 推荐追溯 refreshes the card via the existing
        # Visibility API hook (slow-moving data → no polling interval).
        assert "_todayCurrentTab === 'history' && typeof loadScoreboard" in html


class TestTodayPredictionBoard:
    """V12 W8k BUGFIX — the 今日推荐 single board shows model PREDICTIONS
    (argmax + confidence + market-agreement flag), not EV-vs-Pinnacle picks."""

    def test_devig_argmax_helper_present(self, html):
        assert "function _devigArgmax1x2" in html

    def test_card_shows_model_confidence_not_stake(self, html):
        # renderTodaySingle's body now shows model confidence % (a prediction),
        # not a 建议投注 stake / fake-EV bar. (Other cards — 单关 tab, parlay —
        # legitimately still show stakes; this asserts the prediction body.)
        assert "today_pred_conf" in html
        # AUDIT FIX (D4): assert the two behavioral tokens — model confidence %
        # rendered, labelled by predConfLabel — WITHOUT pinning the exact newline
        # + 12-space indentation between them. The old multi-line substring broke
        # on any prettier/whitespace reformat with zero behavior change. The money
        # invariant (prediction board → stake==0, ev==0) is guarded behaviorally
        # by test_today_recommendations::TestTodayPredictionBoardW8k.
        assert "(t.probability * 100).toFixed(0)}%" in html   # model confidence %
        assert "${predConfLabel}" in html                     # as a prediction label

    def test_market_agreement_3tier_confidence(self, html):
        # V12 W8m — model↔sharp agreement is a 3-tier confidence badge, not a
        # binary ✓/⚠️: 一致 → 高把握; 分歧+模型仍自信 → 信市场; 分歧+近五五开 → 观望.
        assert "today_conf_agree" in html
        assert "today_conf_tossup" in html
        assert "today_conf_trust" in html
        assert "_sa === t.outcome" in html              # agree tier
        assert "t.probability >= _TODAY_CONF_HI" in html  # confident-disagree split
        assert "_TODAY_CONF_HI = 0.50" in html

    def test_count_label_is_prediction_not_stake(self, html):
        assert "today_pred_count" in html
        assert "注 · 总投注 ${fmtMoney(single.total_stake)}" not in html

    def test_section_title_renamed_to_prediction(self, html):
        assert "单关预测" in html

    def test_i18n_keys_both_locales(self, html):
        for k in ("today_pred_count", "today_pred_conf", "today_conf_agree",
                  "today_conf_tossup", "today_conf_trust"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"


class TestRecordBetPin:
    """V14 #2+#3 — 记此注: a 📌 per outcome row in BOTH boards (标准 spcalc +
    市场 cup) and BOTH markets (胜平负 1X2 + 让球) lets the user record the
    EXACT outcome they bet at the entered 竞彩 SP with their real stake (incl
    −EV). Inline stake box → POST /observation/record-bet (server dual-gate).
    This gives the two modes feature parity (#2) and outcome-level choice (#3).
    """

    def test_record_helper_defined(self, html):
        assert "function _recordBet(mode, idx, outcome, market, btn)" in html
        # posts to the dedicated per-outcome endpoint with the session gate on
        assert "API + '/observation/record-bet'" in html
        assert "record_session: true," in html
        # server-authoritative: we send odds (竞彩 SP) + model P + stake + line
        assert "market_type: market, handicap_home: hcLine, outcome," in html

    def test_pin_on_all_four_rows(self, html):
        """One 📌 per board × market — the core of #2 (parity) + #3 (choice)."""
        for call in (
            "_recordBet('spcalc',${idx},'${o}','1x2',this)",       # 标准 胜平负
            "_recordBet('spcalc',${idx},'${o}','handicap',this)",  # 标准 让球
            "_recordBet('cup',${idx},'${o}','1x2',this)",          # 市场 胜平负
            "_recordBet('cup',${idx},'${o}','handicap',this)",     # 市场 让球
        ):
            assert call in html, f"missing 📌 wiring: {call}"
        assert html.count('onclick="_recordBet(') == 4

    def test_neg_ev_allowed_but_warned(self, html):
        """−EV is recordable (user's real bet) but the confirm turns red/⚠."""
        assert "const warn = ev < 0;" in html
        assert "#e11d48" in html            # red confirm button on −EV
        assert "t('bet_neg_ev')" in html

    def test_reads_sp_and_line_with_guards(self, html):
        # odds come from the row's 竞彩 SP input; bail if absent
        assert "if (!(odds > 1.0)) { alert(t('bet_need_sp')); return; }" in html
        # handicap path requires a 让球线 first (collector needs it)
        assert "alert(t('spcalc_hc_pickline')); return;" in html

    def test_i18n_keys_both_locales(self, html):
        for k in ("bet_record", "bet_stake", "bet_need_sp", "bet_neg_ev",
                  "bet_recorded", "bet_gate_off"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"


class TestParlayLegMarketBadge:
    """Every parlay/pool LEG must show a [让球]/[胜平负] market badge. A 让球 leg
    reuses the same H/D/A codes as 胜平负 (主胜/平/客胜), so without the badge a
    让球主胜 renders as a bare 主胜 — exactly the user-reported bug (浦和红钻
    主胜 @ 4.00 was really 让球主胜; the 4.00 odds gave it away). Guards ALL leg
    renderers (今日 + 复式 + 快速串关 + 推荐追溯 + legacy) against regression.
    """

    def test_no_bare_leg_outcome_without_market_badge(self, html):
        import re
        lines = html.splitlines()
        bad = []
        for i, ln in enumerate(lines):
            if re.search(r"outcomeLabel\((?:l|s)\.outcome\)", ln):
                window = "\n".join(lines[max(0, i - 9):i + 11])
                if not any(tok in window for tok in (
                    "market_type === 'handicap_1x2'",
                    "market_type === '1x2'",
                    "marketLabel",
                )):
                    bad.append(i + 1)
        assert not bad, f"leg outcome rendered with no 市场 badge near line(s) {bad}"

    def test_today_and_quick_renderers_have_badge(self, html):
        # The 5 leg renderers fixed/confirmed: today parlay+pool, quick
        # parlay+pool, legacy pool — all key off l.market_type for the badge.
        assert html.count("l.market_type === 'handicap_1x2' ? '让球'") >= 5

    def test_agree_chip_suppressed_for_handicap_ticket(self, html):
        # renderTodaySingle's 市场同意/信市场 chip is a 1X2 model↔sharp argmax
        # signal. On the 竞彩盘口推荐 (jc) board a ticket can be handicap_1x2; a
        # 1X2 argmax (_devigArgmax1x2) vs a 让球 outcome — or "信市场: 主胜" on a
        # 让胜 pick — is 张冠李戴. Must be gated to 1X2 tickets only.
        assert "? _devigArgmax1x2(t.psc_home, t.psc_draw, t.psc_away) : null" in html
        idx = html.index("_devigArgmax1x2(t.psc_home")
        assert "t.market_type === '1x2'" in html[idx - 130:idx]


class TestJingcaiSliderWiring:
    """风险偏好 + 最低期望值 sliders must drive the 竞彩盘 (jingcai), not just the
    国际盘. The jingcai backend uses risk_preference→Kelly and filters ev≥min_ev,
    but loadJingcaiBoard hardcoded min_ev:0.05 and sent no risk_preference → both
    sliders were silently ignored on the board that sizes/gates REAL bets.
    """

    def test_jingcai_request_reads_both_sliders(self, html):
        # the jc request body reads the SAME sliders the 国际盘 does
        assert "risk_preference: _readRiskPreference()" in html
        assert "min_ev: _readMinEv()" in html
        # the old hardcoded jc body is gone
        assert "min_ev: 0.05, record_session: false" not in html

    def test_slider_change_reprices_jingcai_when_shown(self, html):
        assert "function _jcIsShown()" in html
        assert "if (_jcIsShown()) loadJingcaiBoard();" in html


class TestMarketOddsFreshness:
    """市场模式盘口新鲜度 (A) + 手动反推 nudge (B). API-Football mirrors Pinnacle
    only every few hours, so the de-vig prior can trail Pinnacle.com. Each cup
    card shows the snapshot age; when stale it turns amber + links to the manual
    reverse calc so the user can type the LIVE Pinnacle line.
    """

    def test_freshness_helpers_defined_and_wired(self, html):
        assert "function _oddsFreshnessHtml(pr)" in html
        assert "function _openManualReverse()" in html
        assert "const iso = pr && pr.odds_update;" in html       # reads the field
        assert "${_oddsFreshnessHtml(pr)}" in html               # rendered in _cupCardHtml

    def test_stale_threshold_and_nudge(self, html):
        assert "const _ODDS_STALE_MIN = 120;" in html
        assert "mins < _ODDS_STALE_MIN" in html                  # fresh vs stale branch
        # stale branch nudges to the manual reverse calc
        assert "onclick=\"_openManualReverse()\"" in html
        assert "getElementById('manual-reverse')" in html

    def test_i18n_keys_both_locales(self, html):
        for k in ("odds_age_prefix", "odds_min_ago", "odds_hr_ago",
                  "odds_stale_note", "odds_manual_link"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"


class TestManualReverseCalcFix:
    """手动反推计算器曾卡在"计算中"不出结果: the render called nv('mrev-j1')
    but nv is local to _mrevBuildBody — a ReferenceError, and the render sat
    OUTSIDE the try/catch → uncaught → permanent 计算中. Fix: _mrevBuildBody
    returns j1/jx/j2, the render uses them, and the whole fetch+render is wrapped
    in one try/catch so no render-time throw can ever hang it again.
    """

    def test_buildbody_returns_1x2_odds(self, html):
        assert "const j1 = nv('mrev-j1'), jx = nv('mrev-jx'), j2 = nv('mrev-j2');" in html
        assert "ok: true, p1, px, p2, hcap, ouline, over, under, jh, jd, ja, j1, jx, j2," in html

    def test_render_uses_destructured_odds_not_scoped_nv(self, html):
        # render uses the destructured j1/jx/j2 — NOT an out-of-scope nv()
        assert "${row(x2Labels[0], fair1x2[0], j1)}" in html
        assert "jh, jd, ja, j1, jx, j2, body } = built;" in html
        # nv('mrev-j1') now appears ONLY in _mrevBuildBody (not in the render)
        assert html.count("nv('mrev-j1')") == 1

    def test_render_inside_trycatch(self, html):
        # within manualReverseCalc, the data-driven render (market_implied_p) must
        # sit BEFORE the single catch — i.e. inside the try, so it can't hang.
        seg = html[html.index("async function manualReverseCalc()"):
                   html.index("async function manualReverseRecord()")]
        assert seg.count("} catch (e) { return fail(e.message); }") == 1
        assert seg.index("data.market_implied_p") < seg.index("} catch (e) { return fail(e.message); }")  # noqa: E501


class TestCupManualReprice:
    """V14 — per-card 手填实时 Pinnacle (1X2 + 大小球) → 就地重算. The card gets an
    inline panel; Apply POSTs the live line to /recommend/market-reprice, swaps the
    returned de-vig 1X2 + 让球 board into _CUPMKT.preds[idx], and renderCupMarket
    re-prices in place (preserving typed 竞彩 SP). Revert restores the API line.
    """

    def test_panel_inputs_present_in_card(self, html):
        seg = html[html.index("function _cupCardHtml(pr, idx)"):
                   html.index("function _cupRecalc(idx)")]
        for el in ("cupman-${idx}", "cupman-h-${idx}", "cupman-d-${idx}", "cupman-a-${idx}",
                   "cupman-line-${idx}", "cupman-o-${idx}", "cupman-u-${idx}",
                   "cupman-status-${idx}"):
            assert el in seg, f"manual panel missing {el}"
        assert "_cupManualReprice(${idx})" in seg
        assert "_cupManualRevert(${idx})" in seg
        # inputs pre-fill with the card's current API values
        assert "value=\"${_v(pr.psc_home)}\"" in seg
        assert "value=\"${_v(pr.ou_line)}\"" in seg

    def test_reprice_posts_and_mutates_pred(self, html):
        seg = html[html.index("async function _cupManualReprice(idx)"):
                   html.index("function _cupManualRevert(idx)")]
        assert "/recommend/market-reprice" in seg
        assert "pr.handicap_lines = data.handicap_lines;" in seg
        assert "pr._manual = true;" in seg
        assert "pr._apiSnapshot" in seg          # backs up API line for revert
        assert "renderCupMarket(_CUPMKT.preds, _CUPMKT.pending" in seg
        assert "data.overround" in seg           # fat-finger vig check surfaced

    def test_revert_restores_api_snapshot(self, html):
        seg = html[html.index("function _cupManualRevert(idx)"):
                   html.index("function renderCupMarket(preds, pending)")]
        assert "Object.assign(pr, pr._apiSnapshot)" in seg
        assert "delete pr._manual" in seg
        assert "renderCupMarket(_CUPMKT.preds, _CUPMKT.pending" in seg

    def test_pending_stored_and_manual_badge(self, html):
        assert "_CUPMKT.pending = pending;" in html       # kept for in-place re-render
        # freshness badge flips to the manual indicator when overridden
        assert "if (pr && pr._manual) {" in html
        assert "t('cupman_badge')" in html

    def test_i18n_keys_both_locales(self, html):
        for k in ("cupman_toggle", "cupman_toggle_on", "cupman_hint", "cupman_apply",
                  "cupman_revert", "cupman_err_1x2", "cupman_vig", "cupman_badge"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"


class TestMarketBoardOnToday:
    """V14 — 今日推荐 gets a DISPLAY-ONLY 💠 市场模式盘口推荐 block (#mktpred): the
    de-vig BEST pick per cup/J1, a read-only mirror of 国际盘's prediction list,
    ordered 🌍→💠→💴. The FULL interactive board (#cupmkt-section) stays in 近期赛事
    (its 加载/🔄 buttons restored). loadCupMarket renders BOTH; auto-loads on landing.
    """

    def test_board_header_ordered_intl_mkt_jc(self, html):
        i_intl = html.index('data-i18n="board_intl"')
        i_mkt = html.index('data-i18n="board_mkt"')
        i_jc = html.index('data-i18n="board_jc"')
        assert i_intl < i_mkt < i_jc

    def test_lean_block_in_today_full_board_in_upcoming(self, html):
        i_today = html.index('id="tab-today"')
        i_upcoming = html.index('id="tab-upcoming"')
        # lean mirror lives on 今日推荐 …
        assert html.count('id="mktpred-section"') == 1
        assert i_today < html.index('id="mktpred-section"') < i_upcoming
        # … and the FULL interactive board is back in 近期赛事
        assert html.count('id="cupmkt-section"') == 1
        assert html.index('id="cupmkt-section"') > i_upcoming

    def test_full_board_load_button_restored_in_upcoming(self, html):
        assert 'id="cupmkt-load"' in html
        assert html.index('id="cupmkt-load"') > html.index('id="tab-upcoming"')

    def test_mkt_card_is_rich_interactive(self, html):
        # V14 — the 市场模式 card is now the SAME rich INTERACTIVE card as 国际盘:
        # de-vig best pick + inline 竞彩 SP (was display-only; user asked to match
        # 国际盘). Full coverage in TestMarketRichCard.
        seg = html[html.index("function _mktPredCardHtml(pr, idx)"):
                   html.index("function _mktBest")]
        assert "outcomeLabel(best)" in seg                 # de-vig best pick
        assert 'class="mkt-rec-sp' in seg                  # inline 竞彩 SP (interactive)
        assert "_mktRecCalc(" in seg                        # SP → live EV

    def test_loadcupmarket_renders_both(self, html):
        assert "renderMarketPred(body.predictions);" in html   # mirror render wired
        assert "if (typeof loadCupMarket === 'function') loadCupMarket();" in html  # auto-load

    def test_i18n_keys_both_locales(self, html):
        for k in ("board_mkt", "board_mkt_hint", "h_mktpred", "mktpred_empty"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"


class TestMarketPoll:
    """V14 — 市场模式 joins the 国际盘 60s auto-poll (cache read, today tab + visible),
    so both boards refresh together. The re-render PRESERVES typed 竞彩 SP + 让球线."""

    def test_poll_refreshes_both_boards(self, html):
        seg = html[html.index("_todayPollTimer = setInterval"):
                   html.index("_todayPollTimer = setInterval") + 400]
        assert "loadTodayRecommendations();" in seg          # 国际盘
        assert "loadCupMarket === 'function') loadCupMarket();" in seg   # 市场模式 too

    def test_renderMarketPred_preserves_typed_sp(self, html):
        seg = html[html.index("function renderMarketPred"):
                   html.index("function renderCupMarket")]
        # capture-before + restore-after typed 竞彩 SP / 让球线 across the re-render
        assert "const _kept = {};" in seg
        assert ".mkt-rec-sp[data-i=" in seg
        assert "inp.value = e.sp; _mktRecCalc(i);" in seg     # restore SP + recompute EV
        assert 'select[data-hcuid="mkt' in seg                # restore 让球线 too


class TestMarketRichCard:
    """V14 — 市场模式 cards upgraded to the SAME rich layout as 国际盘's single card:
    logos + 大号 P% + 胜平负 badge + 让球 selector + inline 竞彩 SP + 📌. ISOLATED
    record path (_mktRec*) so the 国际盘 money path (_todayRec*) is untouched."""

    def test_rich_card_elements(self, html):
        seg = html[html.index("function _mktPredCardHtml(pr, idx)"):
                   html.index("function _mktBest")]
        assert "badge-gold" in seg and "胜平负 ·" in seg        # pick badge
        assert "num-display text-2xl" in seg                    # big P%
        assert "t('today_pred_conf')" in seg                    # 置信 label
        assert "t('mkt_sharp_chip')" in seg                     # 市场盘·公允 chip (not 市场同意)
        assert 'class="mkt-rec-sp' in seg and "_mktRecCalc(" in seg   # inline 竞彩 SP
        assert "_mktRecRecord(" in seg                          # 📌 记这笔

    def test_mkt_record_handlers_defined(self, html):
        assert "let _MKTPRED_CARDS = [];" in html
        assert "const _MKT_REC_GATE = 0.05;" in html
        for fn in ("function _mktRecCalc(i)", "async function _mktRecRecord(i)"):
            assert fn in html, f"missing {fn}"
        # records the 1X2 pick at the typed 竞彩 SP via /recommend/single
        seg = html[html.index("async function _mktRecRecord"):
                   html.index("async function _mktRecRecord") + 1400]
        assert "/recommend/single" in seg and "record_session: true" in seg
        assert "ev >= _MKT_REC_GATE" in html        # same +5% gate

    def test_intl_record_path_untouched(self, html):
        # the 国际盘 money path must still use its own state + ids (not shared)
        assert "_TODAY_SINGLES[i]" in html
        assert "function _todayRecCalc(i)" in html
        assert 'class="today-rec-sp' in html
        assert "mkt_sharp_chip:" in html and html.count("mkt_sharp_chip:") >= 2


class TestMarketStrengthFilter:
    """V14 — 市场模式 "藏五五开, 留强势": the lean block shows only matches where the
    sharp 1X2 clearly leans (|P(home)-P(away)| >= _MKT_STRONG_MIN); near coin-flips
    fold away. A CONFIDENCE filter on the PREDICTION — explicitly NOT +EV (betting
    Pinnacle's own de-vig line at Pinnacle is -vig; +EV is only on the 竞彩盘)."""

    def test_strength_helpers_defined(self, html):
        assert "const _MKT_STRONG_MIN = 0.15;" in html
        assert "function _mktStrength(pr)" in html
        assert "Math.abs((pr.p_home_1x2 || 0) - (pr.p_away_1x2 || 0))" in html

    def test_splits_strong_vs_tossup(self, html):
        seg = html[html.index("function renderMarketPred"):
                   html.index("function renderCupMarket")]
        assert "_mktStrength(pr) >= _MKT_STRONG_MIN" in seg     # strong = shown
        assert "_mktStrength(pr) < _MKT_STRONG_MIN" in seg      # toss-up = folded
        assert "<details" in seg and "mkt_tossup_fold" in seg   # folded away

    def test_hint_flags_not_plus_ev(self, html):
        # the honest framing must be present: high-confidence PREDICTION, not +EV
        assert html.count("mkt_strong_n:") >= 2
        assert html.count("mkt_tossup_fold:") >= 2
        assert "非 +EV" in html        # zh hint disclaims +EV
        assert "NOT +EV" in html       # en hint disclaims +EV


class TestHandicapPrediction:
    """V14 — 让球胜平负 PREDICTION on BOTH the 国际盘 (today single) and the 市场模式
    lean block: a per-match INTERNATIONAL Asian-Handicap line selector (half-line,
    2-way cover/not — NOT the 竞彩 integer 3-way) over asian_handicap_lines.
    Display-only (Polymarket prep)."""

    def test_helpers_defined(self, html):
        for fn in ("function _hcPredHtml(uid, lines)", "function _hcPredPick(uid)",
                   "function _hcPredBalancedLine(lines)", "function _hcPredRow(lp)"):
            assert fn in html, f"missing {fn}"

    def test_default_is_balanced_line(self, html):
        # default line = argmin |p_home − p_away| (the sharp-implied fair spread)
        assert "Math.abs(l.p_home - l.p_away) < Math.abs(b.p_home - b.p_away)" in html

    def test_wired_into_market_lean_block(self, html):
        seg = html[html.index("function _mktPredCardHtml(pr, idx)"):
                   html.index("function renderMarketPred")]
        # V14 — international Asian Handicap (half-line), NOT the 竞彩 integer board
        assert "_hcPredHtml('mkt' + idx, pr.asian_handicap_lines)" in seg

    def test_wired_into_intl_single_today_only(self, html):
        # 国际盘 (renderTodaySingle) shows it ONLY for pfx='today' (showRec), not 竞彩盘
        seg = html[html.index("function renderTodaySingle"):
                   html.index("function _todayRecCalc")]
        assert "showRec ? _hcPredHtml('today' + i, t.asian_handicap_lines || []) : ''" in seg

    def test_is_half_line_two_way_not_integer(self, html):
        # the AH row is 2-way (cover/not, no 让平) on HALF lines (主-0.5/主+1.5 …)
        seg = html[html.index("function _hcPredRow"):
                   html.index("function _hcPredHtml")]
        assert "lp.p_home >= lp.p_away" in seg          # 2-way best, no draw cell
        assert "t('ah_home')" in seg and "t('ah_away')" in seg
        assert "function _ahLineLabel" in html          # 主±X.X half-line labels
        assert "lp.source === 'mkt'" in seg             # real-vs-DC source tag

    def test_selector_reads_handicap_lines(self, html):
        seg = html[html.index("function _hcPredHtml(uid, lines)"):
                   html.index("function _hcPredPick")]
        assert "_HCPRED[uid] = lines;" in seg                # registered for the picker
        assert "lines.map(l => `<option value=\"${l.line}\"" in seg
        assert "onchange=\"_hcPredPick('${uid}')\"" in seg

    def test_i18n_hcpred_label_both_locales(self, html):
        assert html.count("hcpred_label:") >= 2


class TestEvReliability:
    """V14 — EV reliability grading (anti-longshot-trap). A +EV on a deep
    longshot (the Belgium-Tunisia 0-5 case: Tunisia ~11% @9.4 showed +8% EV)
    must NOT read as a clean 'go' — de-vigging extreme odds is noisy. Every EV
    display now carries a 🟢甜区 / 🟡边缘 / ⚠️冷门 tag by the OUTCOME's P."""

    def test_grader_defined(self, html):
        assert "function _evRelTier(" in html
        assert "function _evRelTag(" in html

    def test_thresholds_present(self, html):
        # deep-longshot floor (mirrors the Polymarket detector's LONGSHOT_FLOOR
        # 0.15) + super-short-favourite ceiling + the sweet/edge tiers.
        assert "return 'cold'" in html and "return 'chalk'" in html
        assert "return 'sweet'" in html and "return 'edge'" in html
        assert "p < 0.15" in html
        assert "p > 0.77" in html
        # V14 (Feature B) — the calibrated trap band [0.15,0.20) carved out of edge.
        assert "return 'overpriced'" in html
        assert "p < 0.20" in html
        assert "overpriced: '⛔'" in html

    def test_wired_into_all_ev_calc_surfaces(self, html):
        # EVERY live SP→EV calc surface tags the EV by the OUTCOME's P.
        assert "_evRelTag(tk.probability)" in html   # 今日推荐 国际盘 single card
        assert "_evRelTag(pBest" in html             # 今日推荐 市场模式 lean (+sharp_flip)
        assert "_evRelTag(p)" in html                # 反推计算器 per-outcome row
        # 近期赛事 (_cupRecalc 1X2 + _cupHcRecalc 让球) + SP计算器 (_spcalcRecalc
        # 1X2 + _spcalcHcRecalc 让球) — all four iterate outcomes as P[o]. The two
        # 近期赛事 ones now also pass the per-fixture sharp_flip (Phase B).
        assert html.count("_evRelTag(P[o]") >= 4

    def test_bare_checkmark_greenlight_removed(self, html):
        # the old "✅ on ANY +5% EV" (which green-lit longshots) is gone — the
        # reliability tag replaces it, so a longshot +EV gets ⚠️, not ✅.
        assert "ev >= 0.05 ? ' ✅' : ''" not in html

    def test_i18n_keys_both_locales(self, html):
        for k in ("rel_sweet", "rel_edge", "rel_overpriced", "rel_cold", "rel_chalk",
                  "rel_sweet_hint", "rel_edge_hint", "rel_overpriced_hint",
                  "rel_cold_hint", "rel_chalk_hint"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"


class TestNationFlags:
    """V14 — national teams render a flag emoji instead of a crest/initials
    circle. WC 2026 opens Mexico vs South Africa, so those must carry flags; the
    UK home nations use Unicode subdivision flags (no ISO country code)."""

    def test_flag_map_and_branch_present(self, html):
        assert "const _NATION_FLAG = {" in html
        assert "_NATION_FLAG[name]" in html        # teamLogo branches on it
        assert 'class="team-flag"' in html          # flag render path
        assert ".team-flag {" in html               # CSS

    def test_key_nations_have_flag_entries(self, html):
        for nation in ('"Mexico":', '"South Africa":', '"Spain":', '"Japan":',
                       '"England":', '"Scotland":', '"China":', '"Venezuela":'):
            assert nation in html, f"national flag entry {nation} missing"


class TestKeptList:
    """V14 — 反推计算器 保留列表: compute a match → 📌 保留 → accumulates into a
    list sorted by best EV, each row deletable + clearable. Replaces the
    (removed) 1X2-only batch textarea; reuses the single-match 1X2 + 让球 calc."""

    def test_markup_present(self, html):
        assert 'id="mrev-keep-btn"' in html
        assert 'onclick="mrevKeptSave()"' in html
        assert 'id="mrev-kept-list"' in html
        assert 'onclick="mrevKeptClear()"' in html

    def test_functions_defined(self, html):
        for fn in ("function mrevKeptSave(", "function mrevKeptRender(",
                   "function mrevKeptDelete(", "function mrevKeptClear("):
            assert fn in html, f"{fn} missing"
        assert "mrevKeptDelete(${r.id})" in html       # per-row delete wired
        assert "_evRelTag(r.fair)" in html              # reliability tag in list

    def test_capture_reuses_both_markets(self, html):
        # 保留 stashes legs from BOTH the 让球 (hcP) and 1X2 (fair1x2) results
        assert "_addLeg(hcLabels[0], hcP[0], jh)" in html
        assert "_addLeg(x2Labels[0], fair1x2[0], j1)" in html

    def test_old_batch_removed(self, html):
        assert "batchReverseCalc" not in html
        assert 'id="mrevb-input"' not in html

    def test_i18n_keys_both_locales(self, html):
        for k in ("mrevk_keep", "mrevk_title", "mrevk_clear"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"


class TestSharpFlipGuard:
    """V14 Phase B — sharp-flip guard wired into the market-mode EV tag: when
    Pinnacle disagrees with Betfair+SBOBET on the favourite, the EV reliability
    tag downgrades to ⚠️ sharp 分歧 (the de-vig prior is suspect there)."""

    def test_evreltag_has_flip_branch(self, html):
        assert "function _evRelTag(p, flip)" in html
        assert "if (flip) {" in html
        assert "t('rel_flip')" in html

    def test_flip_threaded_into_market_mode_handlers(self, html):
        # 市场模式 lean card + 近期赛事 1X2 + 让球 all pass the per-fixture flag
        assert "_evRelTag(pBest, pr && pr.sharp_flip)" in html
        assert "_evRelTag(P[o], pr && pr.sharp_flip)" in html
        assert "_evRelTag(P[o], (_CUPMKT.preds[idx] || {}).sharp_flip)" in html

    def test_i18n_keys_both_locales(self, html):
        for k in ("rel_flip", "rel_flip_hint"):
            assert html.count(k + ":") >= 2, f"i18n key {k!r} missing from a locale"
