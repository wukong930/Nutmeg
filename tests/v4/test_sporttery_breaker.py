"""2026-07-20 — 竞彩晚间跟盘窗(17:00-23:30 每 30 分)的前置护栏。

端点公开无认证(没有账号可封),最坏情形 = 家庭 IP 被 WAF 临时 403/429。危险不在
被拦一次,而在**继续按点撞墙**把临时节流熬成长期黑名单。故:见 403/429 静音 6h。
⚠️ 与 odds_api 的内存熔断不同 —— sporttery 抓取跑在一次性 cron 进程里,熔断
必须**落盘**才跨进程有效(内存版出了进程就没了 = 形同虚设)。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from nutmeg.v4.data.sources import sporttery

REPO = Path(__file__).resolve().parents[2]
SETUP = REPO / "scripts/setup_local_pipeline.sh"


class TestBreakerPersistsAcrossProcesses:
    def test_closed_by_default(self, tmp_path):
        assert sporttery.breaker_remaining(tmp_path) == 0.0

    def test_trip_writes_file_and_blocks(self, tmp_path):
        sporttery._trip_breaker(tmp_path, 403)
        remaining = sporttery.breaker_remaining(tmp_path)
        assert 0 < remaining <= sporttery._BREAKER_HOURS * 3600
        # 落盘 = 下一个 cron 进程(全新解释器)也能读到
        raw = json.loads((tmp_path / sporttery._BREAKER_FILE).read_text(encoding="utf-8"))
        assert raw["status"] == 403 and raw["until"] > time.time()

    def test_expired_file_reads_as_closed(self, tmp_path):
        (tmp_path / sporttery._BREAKER_FILE).write_text(
            json.dumps({"until": time.time() - 1, "status": 429}), encoding="utf-8")
        assert sporttery.breaker_remaining(tmp_path) == 0.0

    def test_corrupt_file_fails_open(self, tmp_path):
        # 熔断文件损坏不该让采集永久瘫痪 —— fail-open(宁可多抓,不可自锁)
        (tmp_path / sporttery._BREAKER_FILE).write_text("{not json", encoding="utf-8")
        assert sporttery.breaker_remaining(tmp_path) == 0.0

    def test_reset(self, tmp_path):
        sporttery._trip_breaker(tmp_path, 429)
        sporttery.reset_breaker(tmp_path)
        assert sporttery.breaker_remaining(tmp_path) == 0.0


class TestRequestPathHonorsBreaker:
    def test_open_breaker_skips_network(self, tmp_path, monkeypatch):
        sporttery._trip_breaker(tmp_path, 403)
        called = []
        monkeypatch.setattr(sporttery.httpx, "get",
                            lambda *a, **k: called.append(1))
        out = sporttery._request("had", "c", cache_dir=tmp_path,
                                 refresh=True, ttl_seconds=None)
        assert out is None and not called       # 一个网络请求都不许发

    def test_403_trips_and_returns_none(self, tmp_path, monkeypatch):
        class _Resp:
            status_code = 403
            def raise_for_status(self): raise AssertionError("不该走到这")
        monkeypatch.setattr(sporttery.httpx, "get", lambda *a, **k: _Resp())
        out = sporttery._request("had", "c", cache_dir=tmp_path,
                                 refresh=True, ttl_seconds=None)
        assert out is None
        assert sporttery.breaker_remaining(tmp_path) > 0   # 已静音,不再重试撞墙


class TestEveningWindowCron:
    def test_job_installed_with_windows(self):
        src = SETUP.read_text(encoding="utf-8")
        assert 'install_job "com.nutmeg.sporttery_evening"' in src
        # 17:00 主窗 + 12 个补窗 = 每 30 分钟到 23:00
        assert '"17:30 18:00 18:30 19:00 19:30 20:00 20:30 21:00 21:30 22:00 22:30 23:00"' in src

    def test_uses_jitter_and_refresh(self):
        src = SETUP.read_text(encoding="utf-8")
        assert "--jitter-seconds 120" in src   # 打散整点指纹
        assert "--phase close --refresh" in src  # 跟盘要真抓,不吃 TTL 缓存

    def test_cli_exposes_jitter(self):
        cli = (REPO / "apps/api/src/nutmeg/v4/cli/ingest_sporttery.py").read_text(
            encoding="utf-8")
        assert '"--jitter-seconds"' in cli
