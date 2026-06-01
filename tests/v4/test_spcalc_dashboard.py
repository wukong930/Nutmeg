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
        assert 'onclick="loadCupMarket()"' in html
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
        # V12 W7 — 🏆 杯赛市场模式
        "cupmkt_load_btn", "cupmkt_hint", "h_cupmkt", "cupmkt_empty", "cupmkt_badge",
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
        # Assert the V12 front-end weekly family prefix, not a specific week or
        # feature slug — the slug changes on every bump (w3-spcalc →
        # w3-upcoming-tab → w4-upcoming-polish …), so pinning the week/slug
        # makes the test break on each ship (it did, twice).
        src = ROUTES.read_text(encoding="utf-8")
        assert "nutmeg-v12-fe-w" in src, (
            "SW CACHE_VERSION not in the V12 front-end (nutmeg-v12-fe-w*) family"
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
        assert "${zhTeam(parts[0])} <span class=\"text-muted\">vs</span> ${zhTeam(parts[1])}" in html

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
        # Stays in the nutmeg-v12-fe-w family (pinned by another test).
        assert "nutmeg-v12-fe-w8" in txt


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
        assert "(t.probability * 100).toFixed(0)}%</div>\n            " \
               "<div class=\"text-xs text-muted mt-0.5\">${predConfLabel}" in html

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
