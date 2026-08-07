"""体检判定送到面板 —— 后端三态 + 前端渲染,都用行为断言(2026-08-07)。

## 为什么这条链路存在

体检的告警原本只走 `osascript` 桌面通知。**实测没送到** —— 退出码 0,
macOS 静默丢弃(通知权限库 TCC 保护,连查都查不了)。⇒ 一个上线当天就死掉、
而且**死的时候看起来完全正常**的告警通道。

面板不依赖任何系统权限,而且报告自带时间戳 ⇒ **通道自己的失效也能被看见**。
这是选它的主要理由,不是「顺手放个地方」。

## ⛔ 本文件守的核心契约

**「没红灯」和「没读到」必须是两个不同的显示。** 前端判据是 `!ok || stale`,
不是「reds 为空就绿」。后者正是本项目最贵的失败模式:
一个死掉的 cron 会让面板永远显示「全绿」。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nutmeg.v4.api import routes

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    return TestClient(app)


def _write(tmp_path, monkeypatch, *, ok=True, reds=(), new=(), gone=(),
           age_hours=1.0, detail=None, ran_at="__auto__"):
    if ran_at == "__auto__":
        ran_at = (datetime.now(UTC)
                  - timedelta(hours=age_hours)).astimezone().isoformat(timespec="seconds")
    p = tmp_path / "hc.json"
    p.write_text(json.dumps({
        "ran_at": ran_at, "ok": ok, "detail": detail, "exit_code": 1 if reds else 0,
        "reds": list(reds), "new": list(new), "gone": list(gone),
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("NUTMEG_HC_JSON", str(p))
    return p


# ------------------------------------------------------------------ 后端三态

def test_fresh_report_is_reported_as_fresh(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, reds=["10. x | y"], age_hours=2)
    d = _client().get("/api/v4/observation/health-check-latest").json()
    assert d["ok"] is True and d["stale"] is False
    assert d["reds"] == ["10. x | y"] and d["new"] == []
    assert 0 < d["age_seconds"] < 3 * 3600


def test_a_missing_report_is_not_reported_as_clean(tmp_path, monkeypatch):
    """⭐ 承重条:体检从没跑过 ⇒ **不是**「没红灯」。

    读不到就说读不到。把它当绿,面板会在 cron 根本没装的机器上显示全绿。
    """
    monkeypatch.setenv("NUTMEG_HC_JSON", str(tmp_path / "never_written.json"))
    d = _client().get("/api/v4/observation/health-check-latest").json()
    assert d["ok"] is False, "文件不存在却报 ok"
    assert d["reds"] == [] and d["detail"], "没说为什么读不到"


def test_a_stale_report_is_flagged_so_a_dead_cron_shows(tmp_path, monkeypatch):
    """⭐ 报告太旧 = cron 可能死了。**这比有红灯更要紧** —— 它意味着你什么都不会知道。"""
    _write(tmp_path, monkeypatch, reds=[], age_hours=40)
    d = _client().get("/api/v4/observation/health-check-latest").json()
    assert d["ok"] is True          # 文件读到了
    assert d["stale"] is True, "40 小时前的报告没被判成陈旧"


def test_an_unparseable_timestamp_counts_as_stale(tmp_path, monkeypatch):
    """「不知道多旧」不能当「很新」—— 那正是让死掉的 cron 看起来健在的那一步。"""
    _write(tmp_path, monkeypatch, ran_at="不是时间")
    d = _client().get("/api/v4/observation/health-check-latest").json()
    assert d["age_seconds"] is None and d["stale"] is True


def test_a_corrupt_file_says_so_instead_of_crashing(tmp_path, monkeypatch):
    p = tmp_path / "hc.json"
    p.write_text("{ 这不是 json", encoding="utf-8")
    monkeypatch.setenv("NUTMEG_HC_JSON", str(p))
    d = _client().get("/api/v4/observation/health-check-latest").json()
    assert d["ok"] is False and "读不出来" in (d["detail"] or "")


def test_the_wrapper_writes_a_json_the_endpoint_can_read(tmp_path):
    """⭐ 端到端:真跑包装器(体检脚本用桩),产出的 JSON 端点能读。

    两边各自绿、拼起来对不上,是本项目栽过的形状 —— 这里把契约两端连起来跑一次。
    """
    hc = tmp_path / "fake_hc.sh"
    hc.write_text("#!/usr/bin/env bash\n"
                  "echo '━━ 9. 某节 ━━'; echo '  ✗ 编造的红灯'\n"
                  "echo '━━ 18. 服务盘一致性 (artifact identity) ━━'; echo '  ✓ ok'\n"
                  "exit 1\n")
    hc.chmod(0o755)
    out = tmp_path / "r.md"
    js = tmp_path / "r.json"
    r = subprocess.run(
        ["bash", str(REPO / "scripts/health_check_cron.sh")],
        env={**os.environ, "NUTMEG_HC_SCRIPT": str(hc),
             "NUTMEG_HC_BASELINE": str(tmp_path / "empty.txt"),
             "NUTMEG_HC_REPORT": str(out), "NUTMEG_HC_JSON": str(js),
             "NUTMEG_HC_NOTIFY": "/usr/bin/true"},
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:600]
    assert js.exists(), "包装器没写 JSON 边车"
    raw = json.loads(js.read_text(encoding="utf-8"))
    assert raw["ok"] is True
    assert any("编造的红灯" in x for x in raw["reds"])
    assert any("编造的红灯" in x for x in raw["new"]), "空基线下它该算新增"


def test_the_early_exit_path_also_writes_json(tmp_path):
    """⭐ §18 缺席那条早退路径**也要**写 JSON。

    不写的话面板读到的是**上一次**那份(内容绿、时间戳旧)——
    而「上次绿」和「这次没跑完」在面板上长得一模一样。
    """
    hc = tmp_path / "fake_hc.sh"
    hc.write_text("#!/usr/bin/env bash\necho '━━ 1. 某节 ━━'; echo '  ✓ ok'\nexit 0\n")
    hc.chmod(0o755)
    js = tmp_path / "r.json"
    js.write_text(json.dumps({"ran_at": "2020-01-01T00:00:00+08:00", "ok": True,
                              "detail": None, "exit_code": 0,
                              "reds": [], "new": [], "gone": []}))   # 上一次的绿
    subprocess.run(
        ["bash", str(REPO / "scripts/health_check_cron.sh")],
        env={**os.environ, "NUTMEG_HC_SCRIPT": str(hc),
             "NUTMEG_HC_BASELINE": str(tmp_path / "e.txt"),
             "NUTMEG_HC_REPORT": str(tmp_path / "r.md"),
             "NUTMEG_HC_JSON": str(js), "NUTMEG_HC_NOTIFY": "/usr/bin/true"},
        capture_output=True, text=True, timeout=60)
    raw = json.loads(js.read_text(encoding="utf-8"))
    assert raw["ok"] is False, "§18 缺席却留着上一次的绿 JSON"
    assert "artifact identity" in (raw["detail"] or "") or "§18" in (raw["detail"] or "")


# ------------------------------------------------------------ 前端渲染(行为)

def _js_fn(name: str) -> str:
    js = DASH.read_text(encoding="utf-8")
    m = re.search(rf"\n(async )?function {re.escape(name)}\s*\(", js)
    assert m, f"找不到 {name} —— 被改名或删了,本护栏失效"
    start, j, depth = m.start() + 1, js.index("{", m.end()), 0
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[start:j + 1]
        j += 1
    raise AssertionError(name)


def _render(payload: dict, *, click: bool = False, fail: bool = False) -> str:
    """喂一份端点回包,跑**生产函数原文**,拿回它真正渲染出的东西。

    2026-08-07 —— `_healthDot` 从「拼 HTML 字符串」改成「建 DOM 节点」
    (理由:`title="${tip}"` 拼属性,体检判词里一个引号就截断它;而且点击行为
    要按调用方分叉,字符串 onclick 传不了闭包)。所以这个桩也从「收 innerHTML
    字符串」升级成一个极小的 DOM shim,把节点摊平成可断言的文本。

    `click=True` 时额外触发一次徽章点击,并把 showInfo 收到的内容一起返回 ——
    这才是「点得开、看得见」的行为断言。
    """
    fail_expr = ("Promise.reject(new Error('boom'))" if fail
                 else f"Promise.resolve({{ json: () => ({json.dumps(payload)}) }})")
    src = f"""
{_js_fn('_healthDot')}
{_js_fn('_showHealthCheckDetail')}
{_js_fn('loadHealthCheck')}
const API = '/api/v4';
const t = k => k;
let out = [];
let infoTitle = '', infoBody = '';
function showInfo(title, body) {{ infoTitle = title; infoBody = body; }}
function loadHealth() {{ out.push('CALLED_loadHealth'); }}
function mkEl(tag) {{
  const e = {{ tag, style: {{ cssText: '' }}, children: [], _text: '', _attrs: {{}},
    set textContent(v) {{ this._text = v; }}, get textContent() {{ return this._text; }},
    setAttribute(k, v) {{ this._attrs[k] = v; }},
    appendChild(c) {{ this.children.push(c); return c; }},
    addEventListener(ev, fn) {{ if (ev === 'click') this._click = fn; }},
    get innerHTML() {{ return flat(this); }} }};
  return e;
}}
function flat(n) {{
  if (n == null) return '';
  if (typeof n === 'string') return n;
  return (n._text || '') + (n.style ? n.style.cssText : '') + (n.title || '')
       + JSON.stringify(n._attrs || {{}}) + (n.children || []).map(flat).join(' ');
}}
global.document = {{ createElement: mkEl, createTextNode: s => ({{ _text: s }}) }};
let mounted = null;
const $ = () => ({{ replaceChildren(...n) {{ mounted = n[0]; }} }});
global.fetch = () => {fail_expr};
loadHealthCheck().then(() => {{
  out.push(flat(mounted));
  if ({str(bool(click)).lower()} && mounted && mounted._click) {{
    mounted._click();
    out.push('INFO_TITLE:' + infoTitle);
    out.push('INFO_BODY:' + infoBody);
  }}
  console.log(out.join('\\n'));
}});
"""
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:2000]
    return r.stdout


_FRESH = {"ok": True, "stale": False, "age_seconds": 3600,
          "reds": [], "new": [], "gone": [], "detail": None}


def test_pill_is_green_only_when_actually_clean():
    assert "--accent-green" in _render(_FRESH)


def test_pill_is_red_when_the_report_cannot_be_read():
    """⭐ 承重条:`ok=False` 必须红。

    这是整条链路的理由 —— 一个死掉/没装的 cron 绝不能显示成「没红灯」。
    """
    html = _render({**_FRESH, "ok": False, "detail": "体检还没跑过"})
    assert "--accent-rose" in html, f"读不到却没变红:{html[:300]}"
    assert "hc_broken" in html


def test_pill_is_red_when_the_report_is_stale_even_if_ok():
    """⭐ `ok=True` + `stale=True` ⇒ 仍然红。

    判据是 `!ok || stale`,不是二选一 —— 报告读到了但两天没更新,
    说明 cron 死了,而它最后那次的结论已经不算数。
    """
    html = _render({**_FRESH, "ok": True, "stale": True, "age_seconds": 200000})
    assert "--accent-rose" in html, "陈旧报告显示成绿/黄了"


def test_new_reds_are_red_and_known_reds_are_only_amber():
    """新增红要喊,已知红只标记 —— 天天喊的告警三天内会被关掉。"""
    new_html = _render({**_FRESH, "reds": ["9. a | b"], "new": ["9. a | b"]})
    assert "--accent-rose" in new_html and "hc_new" in new_html

    known_html = _render({**_FRESH, "reds": ["10. c | d"], "new": []})
    assert "--accent-orange" in known_html, "已知红被喊成了红"
    assert "hc_known" in known_html


def test_a_fetch_failure_is_red_not_silently_absent():
    """端点挂了 ⇒ 红。静静地什么都不显示 = 又一个「看起来没问题」。

    2026-08-07:改用共享 harness —— 它以前自带一份内联 src,`_healthDot` 改成建
    DOM 节点后那份没有 document 桩,于是**在真实代码坏掉之前先炸在自己身上**。
    测试替身各写一份 = 同一件事多处各写一份,同族。
    """
    out = _render(_FRESH, fail=True)
    assert "--accent-rose" in out, f"fetch 失败却没红:{out[:200]}"
    assert "hc_broken" in out


# ─────────────────────────────────── 2026-08-07 追加:点得开、看得见、引号打不断

class TestTheBadgeOpensADetail:
    """⭐ 起因:owner 问「体检已知红是本来就不能点开查看的吗」。

    不是设计如此,是我建的时候漏了 —— 它是个 `<button>`,但 onclick 只是
    `loadHealth()`(重新拉一次),红灯内容全在 `title` 里 ⇒
    **桌面悬停能看到、手机上完全看不到**。而这块面板主要在手机上看。
    和横幅那边刚修掉的是同一个毛病:**结论算出来了,但没送到眼睛前**。
    """

    def test_clicking_shows_the_actual_red_lines(self):
        out = _render({**_FRESH, "reds": ["10. 注册表覆盖率 | 某切片已静默降级"],
                       "new": [], "ran_at": "2026-08-07T20:00:00+08:00"}, click=True)
        assert "INFO_TITLE:hc_detail_title" in out, "点了没弹出详情"
        body = out.split("INFO_BODY:", 1)[1]
        assert "注册表覆盖率" in body, "详情里看不到红灯内容 —— 那点开就没意义"
        assert "2026-08-07T20:00:00+08:00" in body, "没显示报告时间(判不了新旧)"
        assert "hc_detail_recheck" in body, "详情里没有重新检查的入口"

    def test_a_broken_channel_click_shows_why(self):
        out = _render({**_FRESH, "ok": False, "detail": "体检还没跑过(没有 x.json)"},
                      click=True)
        body = out.split("INFO_BODY:", 1)[1]
        assert "体检还没跑过" in body

    def test_new_and_known_reds_are_separated_in_the_detail(self):
        """新增红要能一眼和已知红分开 —— 混在一起等于没分级。"""
        out = _render({**_FRESH, "reds": ["A | 新的", "B | 老的"], "new": ["A | 新的"]},
                      click=True)
        body = out.split("INFO_BODY:", 1)[1]
        assert "hc_new" in body and "hc_known" in body
        # 已知红那组不能把新增红也列一遍
        known = body.split("hc_known", 1)[1]
        assert "老的" in known and "新的" not in known

    def test_a_quote_in_a_red_message_survives_intact(self):
        """⭐ 以前 `title="${tip}"` 是**拼进属性**的 —— 判词里一个 `"` 就截断属性。
        体检输出是中文散文,保证不了没有引号。现在走属性赋值 + textContent。

        ⚠️ **这条只能证明「判词完整地走到了 textContent / title 赋值」**,
        证不了浏览器的 HTML 转义 —— 我的 DOM 桩不模拟 `textContent → innerHTML`
        的转义,靠它断言 `&lt;b&gt;` 等于**在测桩自己**。转义那半在真浏览器里
        单独验过(见 commit 说明)。⛔ 别为了让这条更"强"而给桩加转义逻辑:
        那会变成测试替身自证清白,同族「测试替身抹掉守卫」。
        """
        nasty = '10. x | 判词里有个 " 引号 <b>和标签</b>'
        out = _render({**_FRESH, "reds": [nasty]}, click=True)
        body = out.split("INFO_BODY:", 1)[1]
        assert nasty in body, "判词在中途被截断/丢失了"
        assert '10. x | 判词里有个 " 引号' in out.split("INFO_BODY:", 1)[0], \
            "徽章 title 没拿到完整判词(以前拼属性时会在第一个引号处断掉)"
