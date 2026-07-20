"""2026-07-20 — 个人中心密钥轮换(owner 需求)。

碰的是全系统唯一真正敏感的东西,所以铁律先行:
  ① **write-only** —— 没有任何端点回传完整 key;
  ② **永不入日志** —— 只记 which + last4;
  ③ 写 .env 前备份、原子替换、chmod 600、**只动目标行**。
这些断言是那三条铁律的执行版:任何一条被未来重构悄悄拆掉,这里就红。
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi import HTTPException

from nutmeg.v4.api import admin

REPO = Path(__file__).resolve().parents[2]
SECRET = "SUPERSECRET_test_key_abcd1234"      # 测试用假 key(非真凭据)


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment line\n"
        "NUTMEG_API_FOOTBALL_KEY=old_football_key_9999\n"
        "NUTMEG_ODDS_API_KEY=old_odds_key_8888\n"
        "\n"
        "NUTMEG_SPORTTERY_ENABLED=1\n",
        encoding="utf-8")
    env.chmod(0o600)
    monkeypatch.setattr(admin, "_REPO", tmp_path)
    return tmp_path


class TestEnvWriteIsSurgical:
    def test_replaces_only_target_line(self, fake_repo):
        admin._write_env_key("NUTMEG_ODDS_API_KEY", SECRET)
        body = (fake_repo / ".env").read_text(encoding="utf-8")
        assert f"NUTMEG_ODDS_API_KEY={SECRET}" in body
        # 其余行逐字保留(含注释、空行、顺序、另一把 key)
        assert "# comment line" in body
        assert "NUTMEG_API_FOOTBALL_KEY=old_football_key_9999" in body
        assert "NUTMEG_SPORTTERY_ENABLED=1" in body
        assert "old_odds_key_8888" not in body          # 旧值确实被换掉

    def test_backs_up_before_write(self, fake_repo):
        admin._write_env_key("NUTMEG_ODDS_API_KEY", SECRET)
        baks = list(fake_repo.glob(".env.bak-*"))
        assert len(baks) == 1
        assert "old_odds_key_8888" in baks[0].read_text(encoding="utf-8")  # 可回滚
        assert baks[0].stat().st_mode & 0o777 == 0o600                    # 备份也要 600

    def test_env_stays_600(self, fake_repo):
        admin._write_env_key("NUTMEG_ODDS_API_KEY", SECRET)
        assert (fake_repo / ".env").stat().st_mode & 0o777 == 0o600

    def test_appends_when_absent(self, fake_repo):
        admin._write_env_key("NUTMEG_BRAND_NEW_KEY", SECRET)
        assert f"NUTMEG_BRAND_NEW_KEY={SECRET}" in (fake_repo / ".env").read_text()

    def test_refuses_when_env_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(admin, "_REPO", tmp_path)   # 无 .env
        with pytest.raises(HTTPException) as e:
            admin._write_env_key("NUTMEG_ODDS_API_KEY", SECRET)
        assert e.value.status_code == 500               # 拒绝凭空创建


class TestValidation:
    @pytest.mark.parametrize("bad", ["", "   ", "short", "a" * 201,
                                     "has\nnewline_padding", "空格中文key_x"])
    def test_rejects_bad_shapes(self, bad):
        with pytest.raises(HTTPException) as e:
            admin._validate_key(bad)
        assert e.value.status_code == 400
        assert bad.strip()[:6] not in str(e.value.detail) or not bad.strip()  # 报错不回显 key

    def test_strips_and_accepts(self):
        assert admin._validate_key(f"  {SECRET}  ") == SECRET


class TestNeverLeaks:
    @staticmethod
    def _local_req():
        """真实的「本机浏览器」请求 —— 让 _require_same_machine 也真跑一遍。"""
        return type("R", (), {"headers": {"host": "127.0.0.1:8080"},
                              "client": type("C", (), {"host": "127.0.0.1"})()})()

    def test_response_carries_only_mask(self, fake_repo, monkeypatch, caplog):
        monkeypatch.setattr(admin, "_require_admin_write", lambda *a, **k: None)
        with caplog.at_level(logging.DEBUG):
            out = admin.admin_rotate_key(request=self._local_req(), which="odds_api",
                                         key=SECRET, x_nutmeg_admin="1")
        blob = repr(out)
        assert SECRET not in blob                       # ① 响应不含 key
        assert out["masked"] == {"present": True, "last4": SECRET[-4:],
                                 "length": len(SECRET)}
        assert out["restart_required"] is True
        assert SECRET not in caplog.text                # ② 日志不含 key
        assert SECRET[-4:] in caplog.text               # 但留 last4 供审计

    def test_rejects_unknown_target(self, fake_repo, monkeypatch):
        monkeypatch.setattr(admin, "_require_admin_write", lambda *a, **k: None)
        with pytest.raises(HTTPException) as e:
            admin.admin_rotate_key(request=self._local_req(), which="anthropic",
                                   key=SECRET, x_nutmeg_admin="1")
        assert e.value.status_code == 400               # 白名单外一律拒绝

    def test_status_endpoint_still_masks(self):
        src = (REPO / "apps/api/src/nutmeg/v4/api/admin.py").read_text(encoding="utf-8")
        # 读方向不许出现任何回传完整 key 的路径
        assert '"api_football": _key_masked(' in src
        assert '"odds_api": _key_masked(' in src


class TestGatedLikeRestart:
    def test_endpoint_uses_the_same_triple_gate(self):
        src = (REPO / "apps/api/src/nutmeg/v4/api/admin.py").read_text(encoding="utf-8")
        i = src.index("def admin_rotate_key(")
        body = src[i:i + 1200]
        assert "_require_admin_write(request, x_nutmeg_admin)" in body

    def test_frontend_never_prefills_and_clears(self):
        html = (REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html").read_text(
            encoding="utf-8")
        assert 'type="password" autocomplete="off"' in html
        assert "if (inp) inp.value = '';    // 无论成败都清空" in html
        assert "'X-Nutmeg-Admin': '1'" in html
        for k in ("admin_sec_keys", "admin_key_restart", "admin_key_confirm"):
            assert html.count(k + ":") >= 2, f"i18n {k} 缺一个语言"


class TestPhoneExcluded:
    """2026-07-20 owner:「把手机排除掉」。

    ⚠️ 关键背景:`tailscale serve` 是反向代理 —— 手机来的请求最终以 127.0.0.1
    抵达,所以 `_require_localhost` 对手机是**放行**的(两个重启按钮本来就要这样)。
    密钥轮换分量更重,故加 `_require_same_machine`:回环 IP + Host 是 localhost
    + 无任何代理转发头,三条全中才算「本机浏览器」。"""

    class _Req:
        def __init__(self, headers, host="127.0.0.1"):
            self.headers = headers
            self.client = type("C", (), {"host": host})()

    def test_local_browser_passes(self):
        for h in ("127.0.0.1:8080", "localhost:8080"):
            admin._require_same_machine(self._Req({"host": h}))   # 不抛 = 放行

    @pytest.mark.parametrize("headers", [
        {"host": "ninoomacbook-pro.taile49317.ts.net"},          # 手机走 ts.net 域名
        {"host": "127.0.0.1:8080", "x-forwarded-for": "100.64.0.9"},
        {"host": "127.0.0.1:8080", "x-forwarded-proto": "https"},
        {"host": "127.0.0.1:8080", "tailscale-user-login": "u@example.com"},
    ])
    def test_proxied_request_rejected(self, headers):
        with pytest.raises(HTTPException) as e:
            admin._require_same_machine(self._Req(headers))
        assert e.value.status_code == 403
        assert "本机浏览器" in str(e.value.detail)

    def test_endpoint_applies_the_stricter_gate(self):
        src = (REPO / "apps/api/src/nutmeg/v4/api/admin.py").read_text(encoding="utf-8")
        i = src.index("def admin_rotate_key(")
        body = src[i:i + 1200]
        assert "_require_same_machine(request)" in body, "手机排除闸被摘掉了"

    def test_restart_buttons_keep_the_looser_gate(self):
        """对照组:重启仍允许手机(owner 要在手机上能重启)—— 别把这条一起收紧。"""
        src = (REPO / "apps/api/src/nutmeg/v4/api/admin.py").read_text(encoding="utf-8")
        i = src.index("def admin_restart_api(")
        assert "_require_same_machine" not in src[i:i + 600]

    def test_frontend_disables_card_when_not_local(self):
        html = (REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html").read_text(
            encoding="utf-8")
        assert "const canRotate = _admEnabled && localHost;" in html
        assert "].includes(location.hostname)) return;   // 手机/远程" in html
        assert html.count("admin_key_localonly:") == 2
