"""2026-07-20 — 竞彩价年龄标(owner 复盘发现的时间戳不同步陷阱)。

EV = P(t₁) × SP(t₂):Pinnacle 侧有 odds_update 年龄标,竞彩侧的 t₂ 此前不可见。
实锤两案:埃尔夫斯堡(让胜峰值价 1.97 定格,实价 1.79,面板 −1.3% vs 真 −9%)、
库奥皮奥(客胜绿灯只存在于 20:39 后的价上,旧价把它藏掉)。修法 = 把
jingcai_sp.captured_at 穿到卡片,>60min 且距开球 <3h 时 amber 提示点 🎯。
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

import pytest

from nutmeg.v4.observation.jingcai_sp import fetch_sp_lookup, record_jingcai_sp

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"
ROUTES = REPO / "apps/api/src/nutmeg/v4/api/routes.py"


@pytest.fixture(scope="module")
def html() -> str:
    return DASH.read_text(encoding="utf-8")


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


def _ko(minutes: float) -> str:
    return (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=minutes)).isoformat()


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
        """徽章的出场判据 —— **真调函数**,不 grep 那一行 if 怎么拼。

        ## 2026-09-01 改写的原因

        原来这条是 `assert "if (!pr || !pr.jc_captured_at || !_isJcBettable(pr)) …" in html`。
        a95888b(开赛前后三分区)**故意**把判据从 `_isJcBettable` 换成 `_hasJcSp`,
        理由写在被测代码的注释里:键在可投注上 ⇒ 卡片一进 T−5 就把**唯一的时间线索
        自己关掉**,停售卡上一个字都不说它已开赛。那个提交新增了
        `test_jc_closing_zone.py::test_freshness_badge_survives_the_gate` 守新行为,
        却漏了本条 ⇒ 同一份源码上两个测试互相打架,而红的这个守的是**已被推翻的**判据。

        ⇒ 断言过时,不是代码退化。改法不是把新拼法抄进来(下次加个参数照样红),
        而是钉**真值表**:有 SP + 有可解析时间戳 ⇒ 出;缺任一 ⇒ 不出;
        而「还能不能买」**不参与**判据。同 [[syntactic-proxy-for-semantic-property]]。
        """
        assert "function _jcFreshnessHtml(pr)" in html
        had = {"jc_home": 2.0, "jc_draw": 3.2, "jc_away": 4.1}
        hc = {"jc_hc_home": 2.0, "jc_hc_draw": 3.2, "jc_hc_away": 4.1}
        cap = _ko(-30)
        cases = {
            # ── 出徽章 ──
            "open":        {**had, "jc_captured_at": cap, "kickoff_utc": _ko(600)},
            # ⭐ 承重:T−5 之后**照出**。键回 `_isJcBettable` 的话这两条立刻红。
            "closing":     {**had, "jc_captured_at": cap, "kickoff_utc": _ko(3)},
            "kicked":      {**had, "jc_captured_at": cap, "kickoff_utc": _ko(-10)},
            "no_kickoff":  {**had, "jc_captured_at": cap},
            "handicap_sp": {**hc, "jc_captured_at": cap, "kickoff_utc": _ko(600)},
            # ── 不出徽章:没有可信的时间就闭嘴,不撒谎 ──
            "no_sp":       {"jc_captured_at": cap, "kickoff_utc": _ko(600)},
            "no_stamp":    {**had, "kickoff_utc": _ko(600)},
            "bad_stamp":   {**had, "jc_captured_at": "not-a-date", "kickoff_utc": _ko(600)},
            "partial_sp":  {"jc_home": 2.0, "jc_captured_at": cap, "kickoff_utc": _ko(600)},
        }
        src = "\n".join(_decl(html, h) for h in (
            "const _JC_KO_BUFFER_MIN", "function _hasJcSp", "function _jcKoState",
            # ⚠️ `_isJcBettable` 本身不参与判据,但要在场 —— 否则「判据退回可投注」
            # 那发空包弹会炸成 ReferenceError(假红),而不是**答错**(真红)。
            "function _isJcBettable", "function _jcFreshnessHtml"))
        r = subprocess.run(
            ["node", "-e", src + f"""
              globalThis.t = k => k; globalThis.IC = k => k;
              const cases = {json.dumps(cases)};
              const out = {{}};
              for (const [k, pr] of Object.entries(cases)) out[k] = !!_jcFreshnessHtml(pr);
              out.null_pred = !!_jcFreshnessHtml(null);
              console.log(JSON.stringify(out));"""],
            capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr[-2000:]
        got = json.loads(r.stdout.strip().split("\n")[-1])
        want = {"open": True, "closing": True, "kicked": True, "no_kickoff": True,
                "handicap_sp": True, "no_sp": False, "no_stamp": False,
                "bad_stamp": False, "partial_sp": False, "null_pred": False}
        assert got == want, (
            "徽章出场判据变了:"
            + str({k: (got[k], want[k]) for k in want if got[k] != want[k]})
            + "\n⇒ True 应出未出 = 那张卡上没有任何时间线索;"
              "False 应闭嘴却出了 = 拿不可信的时间戳当准的报。")

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
