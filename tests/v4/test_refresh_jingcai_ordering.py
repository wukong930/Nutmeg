"""🎯 刷新竞彩 —— 「✅」必须等到**屏幕上真的是新数据**才亮(2026-08-13)。

## 起因

owner:「点击刷新之后新数据还没完全落盘的情况下,图标就显示成功了」。

查下来服务端没问题 —— `harvest_to_db` 同步写完才返回。错在前端时序:

```js
const msg = j.ok ? `✅ ${j.matches} …` : …;   // POST 一返回就写 ✅
sts.forEach(s => { s.textContent = msg; });
…
} finally {
  btns.forEach(b => { b.disabled = false; … });   // 按钮立刻放开
  loadCupMarket({manual:true});   // ← 不 await
  loadSpCalc();                   // ← 不 await
  loadJingcaiUnmapped();          // ← 不 await
}
```

⇒ 看到 ✅ 的那一刻,三个重载还在飞(`loadCupMarket` 实测 8–20s),
屏幕上还是旧 SP。**「抓取完成」被当成了「你看到的东西已经是新的」。**

## 这些测试守什么

⭐ **在 node 里跑真的 `_refreshJingcaiInner`**(从 dashboard.html 抠出来),
不是重写一份 —— 重写一份就又变成「我以为它是这个顺序」,而顺序正是被测对象。
(同 `test_zhfold_parity` 的做法。)

① ✅ 出现时,三个 loader **必须已经 resolve**
② 任一 loader 失败 ⇒ **不许写 ✅**(数据落库了,但屏幕上是旧的 —— 这是两回事)
③ 按钮必须复位 —— 即使 loader 全挂(`#cupmkt-refresh-all` 那个「首屏后永久
   disabled」的老 bug 就是这么来的)
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

DASH = Path("apps/api/src/nutmeg/v4/api/static/dashboard.html")


def _extract(name: str) -> str:
    """从 dashboard.html 抠出一个顶层 async function 的源码(含函数体)。"""
    js = DASH.read_text(encoding="utf-8")
    m = re.search(rf"\nasync function {name}\(", js)
    assert m, f"找不到 {name} —— 它被改名或删了,本护栏失效"
    start, j, depth = m.start() + 1, js.index("{", m.end()), 0
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return js[start:j + 1]


def _run(*, loader_fails: bool = False, slow_ms: int = 30) -> dict:
    """在 node 里真跑一次 `_refreshJingcaiInner`,返回事件时间线。

    三个 loader 被换成**会延迟 resolve 的桩**,并在 resolve 时记一条事件 ——
    于是「✅ 写在 loader 之前还是之后」变成一个可以直接读的事实。
    """
    src = _extract("_refreshJingcaiInner")
    harness = f"""
const EV = [];                       // 事件时间线
let statusText = '';
const btn = {{ disabled: false, innerHTML: '' }};

const $  = (sel) => sel === '#jcb-status'
  ? {{ set textContent(v) {{ statusText = v; EV.push(['status', v]); }},
       get textContent() {{ return statusText; }} }}
  : null;
const t  = (k) => k;
const IC = () => '';
const _expandIcons = (s) => s;
const API = '';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

globalThis.fetch = async () => ({{
  json: async () => ({{ ok: true, matches: 7, had: 7, hhad: 7, unmapped_teams: [] }}),
}});

const mk = (name) => async () => {{
  await sleep({slow_ms});
  EV.push(['loader', name]);
  if ({json.dumps(loader_fails)} && name === 'cupMarket') throw new Error('boom');
}};
const loadCupMarket      = mk('cupMarket');
const loadSpCalc         = mk('spCalc');
const loadJingcaiUnmapped= mk('unmapped');

{src}

_refreshJingcaiInner([btn]).then(() => {{
  console.log(JSON.stringify({{ events: EV, status: statusText,
                               disabled: btn.disabled }}));
}}).catch(e => {{ console.log(JSON.stringify({{ error: String(e) }})); }});
"""
    out = subprocess.run(["node", "-e", harness],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[:2000]
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module", autouse=True)
def _need_node():
    if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
        pytest.skip("没有 node")


def test_success_appears_only_after_every_loader_resolved() -> None:
    """🚨 承重条:写 ✅ 的那一刻,三个 loader 必须**已经跑完**。

    空包弹:把 `await Promise.allSettled([...])` 改回三行不 await 的调用
    ⇒ ✅ 会排在 loader 事件之前,这条立刻红。
    """
    r = _run()
    ev = r["events"]
    ok_at = next((i for i, (kind, v) in enumerate(ev)
                  if kind == "status" and v.startswith("✅")), None)
    assert ok_at is not None, f"根本没出现 ✅:{ev}"
    loaders_done = [i for i, (kind, _) in enumerate(ev) if kind == "loader"]
    assert len(loaders_done) == 3, f"不是三个 loader 都跑了:{ev}"
    assert max(loaders_done) < ok_at, (
        f"✅ 出现在 loader 跑完**之前** ⇒ owner 看到成功时屏幕还是旧数据。\n"
        f"时间线:{ev}")


def test_a_failed_reload_must_not_be_reported_as_success() -> None:
    """② 数据落库了,但屏幕上还是旧的 —— 那不是成功,不许写 ✅。

    空包弹:把 `bad ? … : …` 改成无条件写 ✅ ⇒ 这条红。
    """
    r = _run(loader_fails=True)
    assert not r["status"].startswith("✅"), (
        f"有 loader 失败却报了成功:{r['status']}")
    assert "⚠️" in r["status"], r["status"]


def test_button_is_released_even_when_reloads_blow_up() -> None:
    """③ 按钮复位必须在 finally —— 否则一次失败就永久置灰。

    `#cupmkt-refresh-all` 那个「首屏后永久 disabled」的老 bug 就是这么来的
    (所有权劈开:loader 开头置灰、finally 只复位它认识的那几颗)。
    """
    for fails in (False, True):
        r = _run(loader_fails=fails)
        assert r["disabled"] is False, f"loader_fails={fails} 时按钮没复位"


def test_it_does_not_write_to_the_loaders_own_status_elements() -> None:
    """📌 `#cupmkt-status` / `#spcalc-status` 归两个 loader 自己所有。

    旧版往那两块写的值会被 loader **立刻覆写** —— 写一个必定被冲掉的值,
    是这个 bug 的门面那一半。这里用行为验:harness 的 `$` 对这两个选择器
    返回 `null`,函数若还去写就会 TypeError 崩掉整次调用。
    """
    r = _run()
    assert "error" not in r, (
        f"函数仍在写 loader 自己的状态条(harness 里那两个返回 null):{r}")
    assert r["status"].startswith("✅")
