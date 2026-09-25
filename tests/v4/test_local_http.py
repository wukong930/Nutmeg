"""本机 daemon 探针必须**不走代理**(2026-09-25)。

病:macOS 上 `urllib` 会读系统代理;owner 的例外列表里没有 127.0.0.1 ⇒ 体检探本机 daemon
的请求绕进了代理软件。机器暗唤醒 2 秒后补跑体检,代理还没醒 ⇒ ConnectionResetError 假红
(第 18 项)。这里用「环境变量指向一个没人监听的代理」模拟「代理没醒」—— macOS 上环境变量
优先于系统代理,所以这是同一条代码路径。
"""
from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from nutmeg.v4.cli.local_http import is_loopback, urlopen_local

REPO = Path(__file__).resolve().parents[2]

_ROUTES = {
    "/api/v4/health": {"artifact_is_expected": True, "artifact_path": "data/v4_model_cat",
                       "artifact_base_path": "data/v4_model_cat",
                       "trained_at_utc": "2026-09-15T08:34:01+00:00", "model_type": "catboost"},
    "/api/v4/observation/jingcai-unmapped": {"ok": True, "unmapped": [], "n_matches": 0},
    "/api/v4/team-name-zh": {},
}


@pytest.fixture
def stub():
    """本机桩 daemon:记下被请求过的路径(用来证明探针真的打到了它)。"""
    hits: list[str] = []

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            hits.append(path)
            if path not in _ROUTES:
                self.send_response(404); self.end_headers(); return
            body = json.dumps(_ROUTES[path]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", hits
    srv.shutdown(); srv.server_close()


@pytest.fixture
def dead_proxy(monkeypatch):
    """环境代理指向一个没人监听的端口 —— 模拟「代理软件还没醒」。"""
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    url = f"http://127.0.0.1:{port}"
    for k in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(k, url)
    for k in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(k, raising=False)
    return url


@pytest.mark.parametrize("url,expected", [
    ("http://127.0.0.1:8080/api/v4/health", True),
    ("http://127.9.9.9/x", True),
    ("http://localhost:8080/x", True),
    ("http://[::1]:8080/x", True),
    ("http://10.0.0.5:8080/x", False),
    ("http://192.168.1.2/x", False),
    ("https://api.example.com/x", False),
])
def test_is_loopback(url, expected) -> None:
    assert is_loopback(url) is expected


def test_the_dead_proxy_really_breaks_a_plain_urlopen(stub, dead_proxy) -> None:
    """空包弹:先证明这个环境下**默认**的 urlopen 会被代理带坏 —— 否则下面几条是空测试。"""
    base, hits = stub
    with pytest.raises((urllib.error.URLError, OSError)):
        urllib.request.urlopen(f"{base}/api/v4/health", timeout=3)
    assert "/api/v4/health" not in hits, "请求绕进了代理,根本没到桩 daemon"


def test_urlopen_local_goes_direct_under_a_dead_proxy(stub, dead_proxy) -> None:
    base, hits = stub
    with urlopen_local(f"{base}/api/v4/health", timeout=3) as r:
        assert json.loads(r.read())["artifact_is_expected"] is True
    assert hits == ["/api/v4/health"]


def test_non_loopback_targets_keep_the_default_opener(monkeypatch) -> None:
    """⛔ 不替远端目标做「禁代理」的决定 —— 那里可能真的只有代理能出去。"""
    seen = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: seen.append((req, timeout)) or "sentinel")
    assert urlopen_local("https://api.example.com/x", timeout=2) == "sentinel"
    assert seen == [("https://api.example.com/x", 2)]


def test_the_artifact_identity_probe_survives_a_dead_proxy(stub, dead_proxy) -> None:
    """第 18 项:2026-09-25 就是这里假红的。"""
    from nutmeg.v4.cli import artifact_identity as ai
    base, hits = stub
    rows = ai.daemon_rows(url=f"{base}/api/v4/health", timeout=3)
    assert rows[0].severity == ai.OK, rows
    assert "/api/v4/health" in hits


def test_the_dict_vintage_probe_survives_a_dead_proxy(stub, dead_proxy, monkeypatch) -> None:
    """同一个坑的第二份拷贝(data_freshness.check_dict_vintage)。

    源码侧桩掉(只测 daemon 侧那一跳);并**断言桩真的被请求到了** —— 否则源码侧提前
    返回时,「没有『取不到』」这条会空洞地成立。
    """
    from nutmeg.v4.cli import data_freshness as df
    from nutmeg.v4.cli import ingest_sporttery
    from nutmeg.v4.data.sources import sporttery
    # ⚠️ 必须**非空**:源码侧拿到 [] 会直接返回「没有竞彩缓存」,根本走不到 daemon 那一跳
    #    (第一版就是这样空洞地「通过」的 —— 被下面的 hits 断言当场逮住)。
    monkeypatch.setattr(sporttery, "fetch_lottery_matches",
                        lambda **k: [{"home_cn": "甲", "away_cn": "乙"}])
    monkeypatch.setattr(ingest_sporttery, "summarize_unmapped", lambda m: {"unmapped": []})
    base, hits = stub
    info, _alarms = df.check_dict_vintage(f"{base}/api/v4", timeout=3)
    assert "/api/v4/observation/jingcai-unmapped" in hits and "/api/v4/team-name-zh" in hits, hits
    assert not any("活 API 取不到" in line for line in info), info


def test_no_module_probes_loopback_with_a_bare_urlopen() -> None:
    """人口自己发现:任何同时含 `urllib.request.urlopen(` 和回环字面量的源码文件都算嫌疑
    (下一个本机探针别再踩同一个坑)。local_http 本身是那个替身,除外。"""
    src = REPO / "apps/api/src"
    users = [p for p in src.rglob("*.py") if "urlopen_local" in p.read_text(encoding="utf-8")]
    assert len(users) >= 3, f"人口非平凡:用 urlopen_local 的文件只有 {len(users)} 个"
    bad = [str(p.relative_to(REPO)) for p in src.rglob("*.py")
           if p.name != "local_http.py"
           and "urllib.request.urlopen(" in (t := p.read_text(encoding="utf-8"))
           and ("127.0.0.1" in t or "localhost" in t)]
    assert not bad, f"这些文件用裸 urlopen 探本机,会被系统代理带坏:{bad}"
