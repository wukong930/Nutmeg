"""闸的自检:`tests/conftest.py` 那道 Odds API 出口闸,自己得是活的。

⚠️ 这个文件断言的是**闸的行为**,不是被测代码的行为。它存在的理由:那道闸
守的是一条 **fail-soft** 的路(`capture_books_for_sport` 吞掉一切异常),
⇒ 「一直绿」在这里从来不是「没在花钱」的证据 —— 必须有人证明闸真的会响。
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap


class TestTheGateFiresOnTheRealPath:
    """`capture_books_for_sport` 的缓存 miss —— 就是 2026-09-01 新开的那个口子。"""

    def test_a_failsoft_caller_hides_the_exception_but_not_the_gate(
        self, tmp_path, monkeypatch, live_odds_api_calls,
    ):
        """🚨 本闸的**核心断言**:只抛异常是抓不住这条路的。

        `capture_books_for_sport` 整段 `except Exception: return 0` ⇒ 闸抛出去的
        东西当场被吞,用例照样全绿。所以下面两条**必须同时**成立:
          · 返回 0(异常确实被吞了 ⇒ 「抛」这一半是看不见的);
          · 记录器记到了 1 次(⇒ 「记」这一半才是让它看得见的那个)。
        """
        from nutmeg.v4.data.sources import odds_api
        from nutmeg.v4.observation.book_snapshots import capture_books_for_sport

        # 复刻真实场景:测试 monkeypatch 掉 pinnacle 拉取 ⇒ 同参数缓存从没写过。
        monkeypatch.setattr(odds_api, "fetch_pinnacle_lookup", lambda *a, **k: {})
        # ⚠️ 不能改 `DEFAULT_CACHE_DIR`:它是**默认参数**,import 期就绑死了,
        #    改模块属性对 `fetch_book_lookup` 完全无效(改了会得到一个假绿的
        #    「命中真实缓存」)。改 `_cache_path` 才真的把它指到空目录。
        monkeypatch.setattr(
            odds_api, "_cache_path",
            lambda endpoint, params, cache_dir: tmp_path / "cold" / "miss.json")

        n = capture_books_for_sport(tmp_path / "obs.db", "soccer_epl", refresh=False)

        assert n == 0, "fail-soft 应当吞掉闸抛的异常(这正是问题所在)"
        assert len(live_odds_api_calls) == 1, (
            "闸没记到这次 live fetch —— 那么在 owner 机器上它就是一次真实付费请求"
        )

    def test_a_warm_cache_does_not_trip_the_gate(self, tmp_path, monkeypatch):
        """反向对照:缓存命中时闸**不该**响,否则它只是在一律拒绝而不是在判断。

        ⚠️ 没有这一条,上面那条用「闸永远抛」也能绿 —— 那样的闸测不出任何东西。
        """
        import json

        from nutmeg.v4.data.sources import odds_api

        params = {"regions": "eu", "markets": "h2h,totals", "oddsFormat": "decimal"}
        cf = odds_api._cache_path("sports/soccer_epl/odds", params, tmp_path)
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps([{"id": "cached"}]))

        got = odds_api._request("sports/soccer_epl/odds", params, cache_dir=tmp_path)

        assert got == [{"id": "cached"}]
        # 本用例**没有**申明 live_odds_api_calls ⇒ 若闸响了,teardown 会直接判红。


class TestTheProcessHoldsNoKey:
    """第 1 层:连子进程也拿不到钥匙。"""

    def test_the_env_var_is_blanked_in_this_process(self):
        assert os.environ.get("NUTMEG_ODDS_API_KEY") == ""

    def test_os_environ_beats_a_dotenv_file_on_disk(self, tmp_path):
        """🚨 按构造验,别按记忆验:owner 的 CWD 里就有 `.env`。

        `Settings` 同时读 os.environ 和 `env_file=".env"`。这一条证明**空串确实
        盖得住**磁盘上的 `.env` —— 否则第 1 层就是纸糊的,而它是唯一覆盖子进程
        (E2E 会 spawn uvicorn)的一层。
        """
        (tmp_path / ".env").write_text("NUTMEG_ODDS_API_KEY=live-key-would-cost-money\n")
        prog = textwrap.dedent("""
            import os, sys
            os.environ["NUTMEG_ODDS_API_KEY"] = ""
            sys.path.insert(0, sys.argv[1])
            from nutmeg.config import Settings
            print(repr(Settings().odds_api_key))
        """)
        src = os.path.join(os.getcwd(), "apps", "api", "src")
        out = subprocess.run(
            [sys.executable, "-B", "-c", prog, src],
            cwd=tmp_path, capture_output=True, text=True, timeout=120,
        )
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() in ("''", "None"), (
            f"磁盘上的 .env 盖过了 os.environ 的空串:{out.stdout.strip()} ⇒ "
            "第 1 层挡不住子进程"
        )


def test_the_gate_is_installed_for_every_test(request):
    """闸是 autouse 的 ⇒ 每个用例都带着它,不靠谁记得申明。"""
    assert hasattr(request.node, "_live_odds_api_recorder")


def test_a_test_that_wants_the_live_branch_can_still_override_it(tmp_path, monkeypatch):
    """闸不能把「故意验证出口行为」的用例(如熔断器组)锁死。"""
    from nutmeg.v4.data.sources import odds_api

    class _Resp:
        status_code = 200
        headers: dict[str, str] = {}

        @staticmethod
        def json():
            return [{"id": "from-fake-client"}]

    class _FakeClient:
        @staticmethod
        def get(endpoint, params=None):
            return _Resp()

    monkeypatch.setattr(odds_api, "_client", lambda: _FakeClient())
    got = odds_api._request("sports/x/odds", {"regions": "eu"}, cache_dir=tmp_path)
    assert got == [{"id": "from-fake-client"}]
