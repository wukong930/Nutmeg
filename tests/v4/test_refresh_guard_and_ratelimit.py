"""刷新合并的两道安全闸(2026-08-07)。

## 为什么这个文件存在

owner 要把「盘口刷新/竞彩刷新」合并到 💴 竞彩可投注区块。审计发现合并**本身**
不增加额度(Odds API 按 sport_key 去重,合并后 9 次 = 现在分别点两次的 9 次),
但它会把单击爆发面从 ≤18 个 sport_key 推到 31 —— 而限流在**当前一半负载**下
就已经稳定触发了:2026-08-07 的 api_server.err.log 里 15 次
`errors.rateLimit` 丢弃,分属两次相隔 35 秒的手动刷新。

被丢的每一场 fixture 都变成 psc=None ⇒ 掉进「待开盘」⇒
**恰好在你要下注那一刻从可投注区消失**。所以这两道闸是合并的前置条件。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


# ───────────────────────────────────────────────── 后端:限流不再吃掉整场比赛

def _resp(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("GET", "http://x"))


class TestRateLimitIsRecognised:
    """API-Football 的**每分钟**限流是 HTTP 200 + body errors.rateLimit,不是 429。"""

    def test_rate_limit_body_is_detected(self):
        from nutmeg.v4.data.sources.api_football import _body_says_rate_limited
        assert _body_says_rate_limited(
            _resp(200, {"errors": {"rateLimit": "Too many requests"}})) is True

    def test_other_errors_are_not_retried(self):
        """只认 rateLimit。token/plan/bug 这些重试它们只是白烧配额。"""
        from nutmeg.v4.data.sources.api_football import _body_says_rate_limited
        for errs in ({"token": "bad"}, {"plan": "upgrade"}, {}, [], None):
            assert _body_says_rate_limited(_resp(200, {"errors": errs})) is False

    def test_non_json_body_is_not_rate_limited(self):
        """解析失败 ⇒ **不确定就不重试**,否则一次格式变化让每个请求退避 3 次。"""
        from nutmeg.v4.data.sources.api_football import _body_says_rate_limited
        r = httpx.Response(200, content=b"<html>nope", request=httpx.Request("GET", "http://x"))
        assert _body_says_rate_limited(r) is False

    def test_a_rate_limited_call_retries_instead_of_raising(self, tmp_path, monkeypatch):
        """⭐ 承重条:限流一次 → 退避重试 → 第二次成功 ⇒ **不丢这场比赛**。

        以前它直接落到 `errs` 检查 raise 掉 ⇒ 上层把 odds 置空 ⇒ psc=None。
        """
        from nutmeg.v4.data.sources import api_football as af
        calls = {"n": 0}

        class _FakeClient:
            def get(self, endpoint, params=None):
                calls["n"] += 1
                if calls["n"] == 1:
                    return _resp(200, {"errors": {"rateLimit": "Too many requests"}})
                return _resp(200, {"errors": [], "response": [{"ok": True}]})

        monkeypatch.setattr(af, "_client", lambda: _FakeClient())
        monkeypatch.setattr(af.time, "sleep", lambda _s: None)   # 别真睡
        out = af._request("/odds", {"fixture": 1}, cache_dir=tmp_path, refresh=True)
        assert calls["n"] == 2, "限流没触发重试"
        assert out == [{"ok": True}]


class TestRefreshFailureDoesNotEraseTheCard:
    """⭐ 显式刷新失败时回落旧缓存,而不是让这场比赛从可投注区消失。"""

    def _seed(self, tmp_path, fixture_id, rows):
        from nutmeg.v4.data.sources import api_football as af
        cf = af._cache_path("/odds", {"fixture": fixture_id}, tmp_path)
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(rows), encoding="utf-8")
        return cf

    def test_explicit_refresh_failure_serves_prior_cache(self, tmp_path, monkeypatch):
        from nutmeg.v4.data.sources import api_football as af
        prior = [{"bookmakers": [{"name": "Pinnacle", "bets": [
            {"name": "Match Winner", "values": [{"value": "Home", "odd": "1.90"}]}]}]}]
        self._seed(tmp_path, 42, prior)

        def _boom(*a, **k):
            raise af.ApiFootballError("rate limited")
        monkeypatch.setattr(af, "_request", _boom)

        out = af.fetch_odds(42, cache_dir=tmp_path, refresh=True)
        assert out == prior, (
            "刷新失败却没回落旧缓存 —— 上层会把 psc 置 None,"
            "这场比赛就在你要下注那一刻从可投注区消失了")

    def test_still_raises_when_there_is_no_prior_cache(self, tmp_path, monkeypatch):
        """没有旧线可回落时仍然上抛 —— 别把「从来没有过」伪装成「有但旧」。"""
        from nutmeg.v4.data.sources import api_football as af

        def _boom(*a, **k):
            raise af.ApiFootballError("rate limited")
        monkeypatch.setattr(af, "_request", _boom)
        with pytest.raises(af.ApiFootballError):
            af.fetch_odds(999, cache_dir=tmp_path, refresh=True)

    def test_prior_without_prices_is_not_a_fallback(self, tmp_path, monkeypatch):
        """空壳缓存(有行、无书商)不算「旧线」,不能拿它冒充可用赔率。"""
        from nutmeg.v4.data.sources import api_football as af
        self._seed(tmp_path, 7, [{"bookmakers": []}])

        def _boom(*a, **k):
            raise af.ApiFootballError("rate limited")
        monkeypatch.setattr(af, "_request", _boom)
        with pytest.raises(af.ApiFootballError):
            af.fetch_odds(7, cache_dir=tmp_path, refresh=True)


# ───────────────────────────────────────────────── 前端:连点闸(行为,不是数源码)

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


def _run_guard(script_body: str) -> str:
    js = DASH.read_text(encoding="utf-8")
    consts = (js.split("const _REFRESH_COOLDOWN_MS", 1)[1]
                .split("async function _guardedRefresh", 1)[0])
    src = f"""
const t = k => k;
const _REFRESH_COOLDOWN_MS{consts}
{_js_fn('_guardedRefresh')}
{script_body}
"""
    r = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:2000]
    return r.stdout


class TestClickGuard:
    """跑**生产函数原文**,不是数源码里有没有某个字符串。"""

    def test_second_click_while_in_flight_is_dropped(self):
        out = _run_guard("""
let ran = 0;
const slow = () => new Promise(r => setTimeout(() => { ran++; r(); }, 60));
const sts = [{ textContent: '' }];
(async () => {
  const a = _guardedRefresh('odds', slow, sts);
  const b = await _guardedRefresh('odds', slow, sts);   // 在飞时第二次
  await a;
  console.log(JSON.stringify({ ran, second: b, msg: sts[0].textContent }));
})();
""")
        d = json.loads(out)
        assert d["ran"] == 1, "并发第二次也跑了 —— 同 4 个 sport_key 会被拉两次"
        assert d["second"] is False and d["msg"] == "refresh_busy"

    def test_a_second_click_right_after_is_cooled_down(self):
        out = _run_guard("""
let ran = 0;
const sts = [{ textContent: '' }];
(async () => {
  await _guardedRefresh('odds', async () => { ran++; }, sts);
  const b = await _guardedRefresh('odds', async () => { ran++; }, sts);
  console.log(JSON.stringify({ ran, second: b, msg: sts[0].textContent }));
})();
""")
        d = json.loads(out)
        assert d["ran"] == 1, "冷却没拦住连点"
        assert d["second"] is False and d["msg"].startswith("refresh_cooldown")

    def test_the_two_buckets_are_independent(self):
        """🎯(免费,守的是 sporttery 6 小时熔断)不该被 🔄 的冷却连累。"""
        out = _run_guard("""
let ran = 0;
const sts = [{ textContent: '' }];
(async () => {
  await _guardedRefresh('odds', async () => { ran++; }, sts);
  const b = await _guardedRefresh('jingcai', async () => { ran++; }, sts);
  console.log(JSON.stringify({ ran, second: b }));
})();
""")
        d = json.loads(out)
        assert d["ran"] == 2 and d["second"] is True, "两个桶串味了"

    def test_each_entry_point_is_wired_to_the_right_bucket(self):
        """⭐ 变异检验抓到的洞:上面那条只证明**闸支持**两个桶,没证明各入口
        **接到了**哪个桶 —— 把 refreshJingcai 的 'jingcai' 改成 'odds',它照样全绿。
        「测了机制、没测接线」。

        这条是**接线断言**,贴着具体写法(不是在整个文件里搜字符串),
        改写法时要连它一起改 —— 那是有意的:接错桶会让免费的 🎯 被付费刷新的
        20 秒冷却连累,或者反过来让 🔄 逃掉限流保护。
        """
        assert "_guardedRefresh('jingcai'" in _js_fn('refreshJingcai'), \
            "🎯 刷新竞彩没接到 'jingcai' 桶"
        assert "_guardedRefresh('odds'" in _js_fn('refreshBettableOdds'), \
            "🔄 刷新盘口没接到 'odds' 桶"
        # 第 5 个入口(今日推荐 🔄)不是 function,抠不出来 —— 断言它的监听器整段
        js = DASH.read_text(encoding="utf-8")
        blk = js.split("$('#today-refresh').addEventListener(", 1)[1][:400]
        assert "_guardedRefresh(" in blk and "'odds'" in blk, \
            "今日推荐 🔄 没进闸 —— 它和可投注区的 🔄 打的是同一个 AF 每分钟配额"

    def test_the_guard_releases_even_when_the_refresh_throws(self):
        """抛异常也必须解锁 —— 否则一次网络错误会把刷新永久锁死
        (同 `#cupmkt-refresh-all` 那个「置灰后没人复位」的形状)。"""
        out = _run_guard("""
const sts = [{ textContent: '' }];
(async () => {
  try { await _guardedRefresh('odds', async () => { throw new Error('boom'); }, sts); }
  catch (_) {}
  console.log(JSON.stringify({ busy: _refreshBusy.odds }));
})();
""")
        assert json.loads(out)["busy"] is False, "抛异常后闸没解锁 —— 刷新被永久锁死"
