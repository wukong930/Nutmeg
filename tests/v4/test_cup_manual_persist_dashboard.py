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

import datetime as dt
import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _decl(html: str, head: str) -> str:
    """抠出一个顶层 `function …{}` 或 `const …;` 声明(同 test_jc_closing_zone.py)。"""
    i = html.index(head)
    depth, started = 0, False
    for j in range(i, len(html)):
        c = html[j]
        if c == "{":
            depth += 1
            started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return html[i:j + 1]
        elif c == ";" and not started:
            return html[i:j + 1]
    raise AssertionError(f"括号不平衡:{head}")


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
        """restore 从 **FRESH** pred 盖 `_apiSnapshot`,所以 ↩︎ 复原回到最新自动盘口。

        ⚠️ 2026-08-18:这两条**只钉「有没有这段代码」**,钉不住「快照里装了什么」。
        实际出事的正是后者(三个构造点里有一个少三个字段,字符串 grep 全绿)。
        承重的行为断言见 `TestRevertRestoresTheWholeApiLine`。
        """
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

        ## 2026-09-01 改写:从「函数头 4000 字符里 grep 那一行」改成真跑一次记账

        原来是 `html[start:start + 4000]` —— **定长窗口**。a95888b 往 `_recordBet`
        头部加了已开赛闸 + 一段注释,`odds_source:` 那行被推到 4000 字之外 ⇒ 红。
        代码没退化(那行一直在),是探针的取样窗口过时了。

        ⇒ 定长窗口和逐字匹配是同一个毛病的两种写法。改成在 node 里**真调
        `_recordBet` 并拦下 POST**,断言 body 里的 `odds_source` 就是那张卡的值。
        这样既不怕函数长胖,也能抓到「写死成常量」「读错对象」这类 grep 抓不到的形态。
        """
        # 2026-08-06:卡级「已下单」(`_spcalcRecord`/`_spcalcHcRecord`)已按 owner
        # 要求删除(recommendation_sessions 由 daily/morning_recommend cron 自动写,
        # 手动那份是重复)⇒ 📌 `_recordBet` 是**唯一**的手动记账路径。
        assert "function _spcalcRecord(" not in html, "卡级已下单回来了?溯源断言要一起回来"

        # ⭐ 两次:带溯源 / 不带。**两条都承重** —— store.py 明写「绝不默认成
        #    api_football,那等于把『没告诉我』伪装成『我查过了』」⇒ 缺失必须是
        #    显式的 null,不能被省略、也不能兜底成别的来源。
        for label, source, want in (("手填", "manual", "manual"),
                                    ("无溯源", None, None)):
            body = self._post_one_bet(html, source)
            assert body["url"].endswith("/observation/record-bet"), body["url"]
            assert "odds_source" in body["json"], (
                f"[{label}] POST body 里根本没有 `odds_source` 这个键 —— "
                f"`store._request_odds_source` 读不到,手打的价按自动源入账")
            assert body["json"]["odds_source"] == want, (
                f"[{label}] 送出的溯源是 {body['json']['odds_source']!r},应为 {want!r}")

    @staticmethod
    def _post_one_bet(html: str, odds_source: str | None) -> dict:
        """在 node 里真跑 📌 记一笔:开注额框 → 填金额 → ✓ → 拦下那次 POST。"""
        pr = {"league": "KOR_FA_CUP", "date": "2026-09-02",
              "home_team": "A", "away_team": "B",
              "jc_home": 2.1, "jc_draw": 3.4, "jc_away": 3.6,
              "kickoff_utc": (dt.datetime.now(dt.UTC)
                              + dt.timedelta(hours=6)).isoformat(),
              "p_home_1x2": 0.50, "p_draw_1x2": 0.28, "p_away_1x2": 0.22}
        if odds_source is not None:
            pr["odds_source"] = odds_source
        src = "\n".join(_decl(html, h) for h in (
            "const _JC_KO_BUFFER_MIN", "function _hasJcSp", "function _jcKoState",
            "function _recordBet"))
        harness = """
const API = 'http://stub';
globalThis.t = k => k;
// 任何 alert = 走进了某个拒绝分支(闸/缺 SP/缺 P)⇒ 夹具没造出被测条件,必须炸,
// 不能静默返回一个「没 POST」的空结果(那会让下面的断言变成假绿)。
globalThis.alert = m => { throw new Error('REJECTED: ' + m); };
let posted = null;
globalThis.fetch = async (url, opts) => {
  posted = { url, json: JSON.parse(opts.body) };
  return { ok: true, json: async () => ({ recorded: true }) };
};
const made = [];
const _mk = () => {
  const kids = {};
  const el = {
    className: '', innerHTML: '', textContent: '', disabled: false, value: '',
    title: '', style: {}, onclick: null,
    querySelector: s => (kids[s] ||= { value: '', title: '', disabled: false,
      textContent: '', style: {}, onclick: null,
      focus() {}, addEventListener() {} }),
    replaceWith() {}, focus() {}, addEventListener() {}, after() {},
  };
  made.push(el);
  return el;
};
globalThis.document = {
  createElement: _mk,
  // 卡上那个竞彩 SP 输入框(市场模式 1X2 ⇒ `.cupsp`)
  querySelector: sel => (sel.includes('cupsp') ? { value: '2.50' } : null),
};
globalThis._CUPMKT = { preds: [__PRED__] };
globalThis._SPCALC = { preds: [] };
__SRC__
const btn = { style: {}, parentElement: { querySelector: () => null }, after() {} };
_recordBet('cup', 0, 'H', '1x2', btn);
const span = made[0];
if (!span) throw new Error('没有开出注额框 —— `_recordBet` 提前返回了');
span.querySelector('.bet-stake').value = '12';
(async () => {
  await span.querySelector('.bet-ok').onclick();
  if (!posted) throw new Error('✓ 之后没有任何 POST —— 被测那条路没走到');
  console.log(JSON.stringify(posted));
})();
"""
        r = subprocess.run(
            ["node", "-e", harness.replace("__SRC__", src)
                                  .replace("__PRED__", json.dumps(pr))],
            capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, f"node 跑挂了:\n{r.stderr[-2000:]}"
        return json.loads(r.stdout.strip().split("\n")[-1])


class TestRevertRestoresTheWholeApiLine:
    """🚨 「应用手填 → 刷新 → ↩︎ 复原」之后,**整条自动线**都必须回来(2026-08-18)。

    ## 出事的形状

    `↩︎ 复原` 的实现是 `Object.assign(pr, pr._apiSnapshot)` —— 它只还原
    **快照里有的键**。快照少一个字段 ⇒ 那个字段**原地不动**,停在手填值上。

    三个 `_apiSnapshot` 构造点里,`_cupApplyStoredManual`(刷新/切 tab 时从
    localStorage 贴回那条)少了 `onex_lo_*` 和 `p_*_market`。而它紧接着就把
    `pr.onex_lo_*` 覆盖成手填线的下界 ⇒ 复原后:

        点估回到自动线   ·   下界留在手填线

    `_boardLegs` 的钳位 `Math.min(lo, p)` 只兜住**方向**,代价是**下界塌成点估、
    安全边际归零** —— 同 `market_handicap` 那条「越不可信越容易变绿」。
    实测(韩国杯主胜腿 SP 2.63):evLo 从 −20.61% 虚高到 −17.56%,**+3.05pp**,
    而 +5% 闸就建在这上面。

    ## ⭐ 为什么必须是行为断言

    原来守这里的是 `assert "pr._apiSnapshot = {" in html` —— **字符串 grep**。
    三个构造点里少一个字段,它照样全绿(实测:出事期间该断言一直是绿的)。
    「语法代理测语义属性」在本仓是明令的反模式,这条是它的又一个现场。
    ⇒ 这里在 node 里跑**真的** shipped 函数,断言**复原之后的对象状态**。
    """

    #: 复原后必须与自动线逐字相同的键。⚠️ 加字段进 `_apiSnapshot` 时同步加这里。
    _MUST_RESTORE = (
        "p_home_1x2", "p_draw_1x2", "p_away_1x2",
        "p_home_market", "p_draw_market", "p_away_market",
        "onex_lo_home", "onex_lo_draw", "onex_lo_away",
        "psc_home", "psc_draw", "psc_away", "odds_source",
    )

    @staticmethod
    def _run(html: str) -> dict:
        """在 node 里跑真代码:应用 → 刷新(贴回)→ ↩︎ 复原,回传复原后的 pred。"""
        import json
        import re
        import subprocess

        def fn(name: str) -> str:
            m = re.search(rf"\n(?:async\s+)?function {re.escape(name)}\s*\(", html)
            assert m, f"dashboard.html 里找不到 {name}"
            body = html[m.start():]
            depth = 0
            started = False
            for k, ch in enumerate(body):
                if ch == "{":
                    depth += 1
                    started = True
                elif ch == "}":
                    depth -= 1
                    if started and depth == 0:
                        return body[:k + 1]
            raise AssertionError(f"{name} 括号不平衡 —— 提取器需要更新")

        src = "\n".join(fn(n) for n in (
            "_cupManKey", "_cupManStore", "_cupManWrite", "_cupManSave",
            "_cupManForget", "_cupApplyStoredManual", "_cupManRefreshDerived",
            "_cupManualRevert",
        ))
        m_ls = re.search(r"_LS_CUPMAN\s*=\s*'([^']+)'", html)
        assert m_ls, "找不到 _LS_CUPMAN —— harness 会静默失效(见类 docstring)"
        harness = """
const API = 'http://stub';
// 🚨 必须定义 —— `_cupManWrite`/`_cupManStore` 引用它,而它们把整段包在
//    `try { } catch (_) {}` 里 ⇒ 少一个全局变量 = **静默什么都不做**,
//    夹具看起来跑通了、被测路径压根没进。2026-08-18 我第一版就栽在这。
const _LS_CUPMAN = '__LS_CUPMAN__';
const store = {};
globalThis.localStorage = {
  getItem: k => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
  removeItem: k => { delete store[k]; },
};
// 手填线的派生结果(服务端会回这些)—— 与自动线**刻意不同**,便于分辨
const MANUAL = { p_home_1x2: .50, p_draw_1x2: .28, p_away_1x2: .22,
  onex_lo_home: .48, onex_lo_draw: .26, onex_lo_away: .20, handicap_lines: [{line:-1}],
  delta_scope: 'out_of_scope' };
globalThis.fetch = async () => ({ ok: true, json: async () => MANUAL });
globalThis.renderCupMarket = () => {};
globalThis._CUPMKT = { preds: [], pending: [] };
__SRC__
// ── 自动线(API 下发的原貌)──
// ⏰ 比赛日必须**相对今天**算,不能写死。`_cupManWrite` 会剪掉 `date < today`
//    的条目(`test_prune_stale_entries` 钉的就是它)⇒ 写死一个当时的未来日期
//    是**定时炸弹**:那天一过,`_cupManSave` 静默存了个空 store,
//    `_cupApplyStoredManual` 第一行就早返回,本类三条**全部变成假绿**
//    —— 2026-09-01 实测:承重两条照常绿,只有下面那条自检红。
//    (这正是类 docstring 里那个「夹具造不出被测条件 ⇒ 假绿」的第二个现场。)
const FIXTURE_DATE = new Date(Date.now() + 864e5).toISOString().slice(0, 10);
const API_LINE = {
  home_team: 'A', away_team: 'B', date: FIXTURE_DATE, league: 'KOR_FA_CUP',
  p_home_1x2: .40, p_draw_1x2: .30, p_away_1x2: .30,
  p_home_market: .41, p_draw_market: .29, p_away_market: .30,
  onex_lo_home: .3884, onex_lo_draw: .2884, onex_lo_away: .2884,
  psc_home: 2.5, psc_draw: 3.3, psc_away: 3.3, odds_source: 'api_football',
  handicap_lines: [{ line: -1 }], ou_line: 2.5, odds_update: '2026-08-18T00:00:00Z',
};
const pr = JSON.parse(JSON.stringify(API_LINE));
_CUPMKT.preds = [pr];
// STEP 1 应用手填 —— 按 `_spcalcManualReprice`/`_cupManualReprice` 存的形状写入 localStorage
_cupManSave(pr, { h: 2.1, d: 3.4, a: 3.6, o: null, u: null, line: 2.5,
  P: [MANUAL.p_home_1x2, MANUAL.p_draw_1x2, MANUAL.p_away_1x2],
  lo: [MANUAL.onex_lo_home, MANUAL.onex_lo_draw, MANUAL.onex_lo_away],
  hc: MANUAL.handicap_lines });
// STEP 2 刷新/切 tab —— 真正的贴回路径(它会重盖 `_apiSnapshot`)
const fresh = JSON.parse(JSON.stringify(API_LINE));
_CUPMKT.preds = [fresh];
const trace = { fixture_date: FIXTURE_DATE,
  stored_keys: Object.keys(JSON.parse(localStorage.getItem(_LS_CUPMAN) || '{}')) };
_cupApplyStoredManual([fresh], () => {}, false);
trace.snapshot_stamped = !!fresh._apiSnapshot;
trace.snapshot_keys = Object.keys(fresh._apiSnapshot || {});
setTimeout(() => {
  trace.lo_before_revert = fresh.onex_lo_home;
  // ⭐ 复原**之前**哪些字段真的偏离了自动线 —— 只有这些字段的「复原断言」有判别力,
  //    其余的恒真。见 `test_the_harness_names_the_fields_it_can_discriminate`。
  trace.diverged = Object.keys(API_LINE).filter(
    k => JSON.stringify(fresh[k]) !== JSON.stringify(API_LINE[k]));
  // STEP 3 ↩︎ 复原
  _cupManualRevert(0);
  console.log(JSON.stringify({ after: _CUPMKT.preds[0], api: API_LINE, manual: MANUAL,
    trace }));
}, 60);
"""
        out = subprocess.run(
            ["node", "-e", harness.replace("__SRC__", src)
                                  .replace("__LS_CUPMAN__", m_ls.group(1))],
            capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, f"node 跑挂了:\n{out.stderr[-2000:]}"
        return json.loads(out.stdout.strip().split("\n")[-1])

    def test_harness_actually_reaches_the_path_under_test(self, html: str) -> None:
        """⭐⭐ **强**前提自检 —— 逐段证明夹具真的走到了被测那条路。

        🚨 我的第一版只断言「手填线 ≠ 自动线」,**它是绿的,而空包弹 0 红** ——
        因为 harness 少定义了全局 `_LS_CUPMAN`,`_cupManWrite`/`_cupManStore` 把整段
        包在 `try { } catch (_) {}` 里 ⇒ **静默什么都不做** ⇒ localStorage 空 ⇒
        `_cupApplyStoredManual` 第一行 `if (!m || !Array.isArray(m.P)) return;` 直接返回
        ⇒ `_apiSnapshot` 压根没被盖 ⇒ 撤销修复也没红。

        ⇒ 「夹具造不出被测条件」在**这个方向**上产生的是**假绿**,比假红更贵。
        所以自检必须逐段查中间态,不能只查输入。
        """
        r = self._run(html)
        t = r["trace"]
        assert t["stored_keys"], (
            "localStorage 里什么都没存 —— `_cupManSave` 静默失败了。"
            f"\n⏰ 先查夹具的比赛日({t.get('fixture_date')}):`_cupManWrite` 会剪掉 "
            "`date < today` 的条目,写死的日期一过期就是这个症状(2026-09-01 踩过)。")
        assert t["snapshot_stamped"], \
            "`_cupApplyStoredManual` 没有盖 `_apiSnapshot` —— 贴回路径没进"
        assert t["lo_before_revert"] == r["manual"]["onex_lo_home"], (
            f"复原**之前**下界不是手填值(实际 {t['lo_before_revert']},"
            f"手填 {r['manual']['onex_lo_home']})—— 没造出「要被复原」的状态,"
            f"后面的断言恒真")
        assert r["manual"]["onex_lo_home"] != r["api"]["onex_lo_home"], \
            "夹具的手填线和自动线一样 —— 本类全部断言恒真"

    def test_the_harness_names_the_fields_it_can_discriminate(self, html: str) -> None:
        """⚠️ 2026-09-01 —— 「在 `_MUST_RESTORE` 里」≠「这条夹具测得出来」。

        实测:把 `p_*_market` 从 `_cupApplyStoredManual` 的 `_apiSnapshot` 里删掉,
        `test_revert_restores_every_backed_up_field` **照样全绿**。原因不是断言写错,
        是**本条路径根本不动这三个字段**:市场板(`keepModelP=false`)贴回的是
        `p_*_1x2`,标准板(`keepModelP=true`)这三个连点估都不写。唯一会把
        `p_*_market` 盖成手填值的是 `_spcalcManualReprice`,而它有**自己**那份快照。

        ⇒ 那三个字段在这里是**防御性携带**,不是本夹具已覆盖的东西。
        本条把这个边界钉成可执行的事实,免得下一个人读 `_MUST_RESTORE` 时
        以为 13 个字段都有判别力(同 `first-match-is-not-the-population`:
        「列在清单里」不等于「被测到了」)。
        """
        diverged = set(self._run(html)["trace"]["diverged"])
        # ✅ 有判别力:复原前它们真的停在手填线上
        covered = {"p_home_1x2", "p_draw_1x2", "p_away_1x2",
                   "onex_lo_home", "onex_lo_draw", "onex_lo_away",
                   "psc_home", "psc_draw", "psc_away", "odds_source"}
        assert covered <= diverged, (
            f"这些字段复原前**没有**偏离自动线 ⇒ 对它们的复原断言恒真:"
            f"{sorted(covered - diverged)}")
        # ⚠️ 无判别力(见 docstring)。若哪天它们也偏离了,说明有新路径开始写它们 ——
        #    那时把它们挪进 `covered`,别把本条删掉。
        assert diverged.isdisjoint({"p_home_market", "p_draw_market", "p_away_market"}), (
            "`p_*_market` 现在会偏离了 ⇒ 有新路径在写它们,把它们挪进 covered")

    def test_revert_restores_every_backed_up_field(self, html: str) -> None:
        """🚨 承重条:复原后每个字段都必须回到自动线,一个都不许留在手填值上。"""
        r = self._run(html)
        after, api, manual = r["after"], r["api"], r["manual"]
        stuck = [k for k in self._MUST_RESTORE
                 if k in api and after.get(k) != api[k]]
        assert not stuck, (
            f"🚨 ↩︎ 复原后这些字段**没回到自动线**:{stuck}\n"
            + "\n".join(f"   {k}: 复原后={after.get(k)} 自动线={api[k]} "
                        f"手填线={manual.get(k, '(手填未涉及)')}" for k in stuck)
            + "\n   ⇒ `_apiSnapshot` 少备份了它们(`Object.assign` 只还原快照里有的键)。")

    def test_lower_bound_specifically_does_not_collapse(self, html: str) -> None:
        """具名锚:下界塌成点估 = 安全边际归零,这是 2026-08-18 那个 bug 的钱路后果。"""
        r = self._run(html)
        after, api = r["after"], r["api"]
        margin = after["p_home_1x2"] - after["onex_lo_home"]
        want = api["p_home_1x2"] - api["onex_lo_home"]
        assert abs(margin - want) < 1e-9, (
            f"🚨 复原后 1X2 主胜腿的安全边际 = {margin*100:.2f}pp,自动线应为 "
            f"{want*100:.2f}pp。边际被压缩 ⇒ evLo 虚高 ⇒ +5% 闸变松。")
