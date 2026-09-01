"""付费 API 出口闸**自己**的牙齿(2026-09-02)。

## 为什么单开一个文件

`tests/conftest.py` 那两道闸(Odds API / API-Football)的判红**全靠 teardown 里的
`pytest.fail`** —— 因为两边的调用点大量在 fail-soft 的 `except Exception:` 里,
只抛异常会被当场吞掉、用例照绿。也就是说 teardown 那一段是整道闸的**牙齿**。

🚨 而空包弹实测:把 teardown 那段判红**整个删掉,全套照绿** —— 牙齿无人守。
同理删掉 `odds_api_history` 那一半也全绿(历史端点 **20 credits/次**,是最贵的一条)。
⇒ 闸装着,但「装了有没有用」没有任何断言。这正是本仓反复点名的形状:
**「一直绿」不是它在保护你的证据**。

## 怎么测 teardown

teardown 的红**在本进程里看不到**(它发生在用例结束之后)⇒ 起一个**内层 pytest**,
让它跑一条「踩了闸但不读记录器」的用例,断言外层看到的是红。
⚠️ 内层必须落在 `tests/v4/` 下,否则走不到仓库的 conftest 链 —— 闸就不在场,
本文件会变成一组恒绿的空断言。下面有一条自检钉这件事。
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent


def _run_inner(body: str) -> subprocess.CompletedProcess:
    """把 `body` 写成 tests/v4/ 下的一个临时用例,起内层 pytest 跑它。"""
    f = _HERE / f"_inner_probe_{uuid.uuid4().hex[:8]}.py"
    f.write_text(textwrap.dedent(body), encoding="utf-8")
    try:
        return subprocess.run(
            [sys.executable, "-B", "-m", "pytest", str(f), "-q", "--no-header", "-p",
             "no:randomly"],
            capture_output=True, text=True, cwd=_HERE.parents[1], timeout=300,
            env={"PYTHONDONTWRITEBYTECODE": "1", **_env()},
        )
    finally:
        f.unlink(missing_ok=True)


def _env() -> dict:
    import os
    return {k: v for k, v in os.environ.items()}


def test_the_harness_itself_reaches_the_gate() -> None:
    """⚠️ 先钉夹具:内层必须**真的**装上了闸。

    否则下面两条会因为「闸不在场 ⇒ 什么都没记 ⇒ 什么都没红」而恒绿 ——
    那是最坏的一种假绿:测试在,断言在,而被测的东西根本没上场。
    """
    r = _run_inner('''
        def test_probe(request):
            assert hasattr(request.node, "_live_odds_api_recorder"), "OA 闸没装上"
            assert hasattr(request.node, "_live_api_football_recorder"), "AF 闸没装上"
    ''')
    assert r.returncode == 0, f"内层没跑通(闸不在场?):\n{r.stdout[-2000:]}"


@pytest.mark.parametrize(("what", "trip"), [
    ("odds_api", "odds_api._client()"),
    ("api_football", "api_football._client()"),
])
def test_the_teardown_is_what_makes_it_red(what: str, trip: str) -> None:
    """🚨 牙齿:踩了闸**但不读记录器**的用例,必须被 teardown 判红。

    ⛔ 这条不能写成「调用 _client() 会抛」—— 抛是会抛,但调用点普遍
    fail-soft,抛出去当场被吞。真正让人看见的是 teardown。
    """
    r = _run_inner(f'''
        from nutmeg.v4.data.sources import {what}

        def test_probe():
            # fail-soft 调用点的形状:吞掉异常,用例自身**不**失败
            try:
                {trip}
            except Exception:
                pass
    ''')
    assert r.returncode != 0, (
        f"{what} 的闸被踩了却没红 —— teardown 的判红失效了:\n{r.stdout[-2000:]}")
    assert "conftest" in r.stdout or "live" in r.stdout.lower(), (
        f"红了但不是闸报的?输出:\n{r.stdout[-2000:]}")


def test_the_history_endpoint_half_is_wired() -> None:
    """💸 `odds_api_history` 是**最贵**的一条(历史端点 20 credits/次)。

    它走模块级 `httpx.get`,不经 `_client` ⇒ 闸对它是**单独一条腿**。
    空包弹实测:把那条腿删掉,全套照绿 —— 因为从来没有用例碰过它。
    """
    r = _run_inner('''
        from nutmeg.v4.data.sources import odds_api_history

        def test_probe():
            try:
                odds_api_history.httpx.get("https://api.the-odds-api.com/v4/historical/x")
            except Exception:
                pass
    ''')
    assert r.returncode != 0, (
        f"历史端点那一半没有闸 —— 20 credits/次的路裸奔:\n{r.stdout[-2000:]}")


def test_acknowledging_lets_a_gate_test_read_what_it_caught() -> None:
    """⭐ 负对照:申明了 `live_*_calls` 的用例**不**被 teardown 判红。

    没有这条,上面那两条可以靠「teardown 一律判红」通过 —— 那样任何
    验证闸本身的用例都没法写了。
    """
    r = _run_inner('''
        from nutmeg.v4.data.sources import api_football

        def test_probe(live_api_football_calls):
            try:
                api_football._client()
            except Exception:
                pass
            assert len(live_api_football_calls) == 1
    ''')
    assert r.returncode == 0, f"认领之后仍被判红:\n{r.stdout[-2000:]}"
