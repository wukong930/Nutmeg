"""🖼️ AF 默认占位队徽必须当成「没有队徽」(2026-09-10)。

## 病史

owner:「给没有加队徽的球队加队徽」。查下来盘面 815 支俱乐部缺徽 59 支,而 59 拆开是
**两个问题**:12 支真缺(AF fixture 缓存里有身份锚定的 logo URL,已下载,0 次 API 调用),
47 支其实是 **odds_api 侧的拼法**(补别名,不是补队徽)。

顺带查出第三件:**已经下载的队徽里有一批是 AF 的默认占位图**。
实测 8 支英格兰低级别队(Broadfields United / Loughborough University / Thetford Town …)
的 PNG **逐字节相同**,而它们是 **4 个不同的 AF team id** ⇒ 不是巧合。
渲染它 = 卡片上一个空白圆,**比字母缩写更差**(缩写至少能认出是哪支队)。

## 🚨 判据必须是内容哈希,不是文件大小

本仓栽过:三个队都是 90381B,我判「同一张占位图」;查 SHA256 才发现
**236 个同尺寸文件里有 229 种内容** —— 90381 只是常见尺寸。
而这张占位图**恰好也是** 90381B,`Knowle`(真队徽)同样 90381B、哈希不同。
⇒ 按大小判会**同时误杀真徽、放过占位图**。

## ⭐ 常数由磁盘自己发现,不手抄

`_AF_PLACEHOLDER_SHA256` 写在 `routes.py` 里,但本文件**从磁盘重新算一遍**去核对它。
手抄一个哈希抄错了的症状是「占位图照常显示」—— 没人会当 bug 报。
"""
from __future__ import annotations

import collections
import hashlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LOGOS = REPO / "data/external/team_logos"


def _hash_groups() -> dict[str, list[str]]:
    g: dict[str, list[str]] = collections.defaultdict(list)
    for p in LOGOS.glob("*.png"):
        g[hashlib.sha256(p.read_bytes()).hexdigest()].append(p.stem)
    return g


@pytest.fixture(scope="module")
def groups():
    if not LOGOS.exists() or not any(LOGOS.glob("*.png")):
        pytest.skip("队徽缓存不在这个 checkout 里")
    return _hash_groups()


def test_the_constant_is_the_actual_placeholder_on_disk(groups):
    """⭐ 承重:常数必须等于磁盘上**被最多球队共用**的那个哈希。

    这条把「手抄的常数」变成「磁盘自己发现的事实」。抄错 ⇒ 立刻红。
    """
    from nutmeg.v4.api.routes import _AF_PLACEHOLDER_SHA256

    biggest, teams = max(groups.items(), key=lambda kv: len(kv[1]))
    # 🚨 人口非平凡:必须真有一组被多支队共用,否则下面的相等是空洞的
    assert len(teams) >= 3, (
        f"磁盘上最大的同内容组只有 {len(teams)} 支({teams})—— "
        f"占位图可能已经不存在了,请重新确认这条护栏还需不需要")
    assert _AF_PLACEHOLDER_SHA256 == biggest, (
        f"常数 {_AF_PLACEHOLDER_SHA256[:12]}… 与磁盘上的占位图 {biggest[:12]}…"
        f"(被 {len(teams)} 支队共用)不一致 —— 别手改常数,先查磁盘")


def test_size_is_not_a_valid_test(groups):
    """🚨 钉住那条教训:**同尺寸 ≠ 同内容**。

    这条红了说明「按大小判占位图」这个错误做法**恰好也能work**了 ——
    那时更要小心,因为它会在下一批数据上悄悄失效。
    """
    from nutmeg.v4.api.routes import _AF_PLACEHOLDER_SHA256

    ph_size = None
    same_size_other_content = []
    for h, names in groups.items():
        size = (LOGOS / f"{names[0]}.png").stat().st_size
        if h == _AF_PLACEHOLDER_SHA256:
            ph_size = size
    assert ph_size is not None, "磁盘上找不到占位图 —— 上一条应该已经红了"
    for h, names in groups.items():
        if h != _AF_PLACEHOLDER_SHA256 and (LOGOS / f"{names[0]}.png").stat().st_size == ph_size:
            same_size_other_content.append(names[0])
    assert same_size_other_content, (
        f"占位图尺寸 {ph_size}B 目前是唯一的 —— 按大小判**碰巧**也对。"
        f"⛔ 别据此改成按大小判:那在下一批数据上会同时误杀真徽、放过占位图")


class TestEndpointTreatsPlaceholderAsMissing:
    """端点必须 404,让前端 `onerror` 退回字母缩写。"""

    def _client(self):
        from fastapi.testclient import TestClient

        from nutmeg.main import app
        return TestClient(app)

    def test_placeholder_slug_404s(self, groups):
        from nutmeg.v4.api.routes import _AF_PLACEHOLDER_SHA256

        slugs = groups[_AF_PLACEHOLDER_SHA256]
        r = self._client().get(f"/api/v4/team-logo/{slugs[0]}")
        assert r.status_code == 404, (
            f"{slugs[0]} 是占位图却返回 {r.status_code} ⇒ 卡片上会显示一个空白圆")

    def test_a_real_crest_still_200s(self, groups):
        """🚨 对照:真队徽必须仍然 200。

        没有这条,「全部 404」也能让上一条通过 —— 那是把队徽整个关掉。
        """
        from nutmeg.v4.api.routes import _AF_PLACEHOLDER_SHA256

        real = next(n[0] for h, n in groups.items() if h != _AF_PLACEHOLDER_SHA256)
        r = self._client().get(f"/api/v4/team-logo/{real}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/png", (
            f"真队徽 {real} 返回 {r.status_code} —— 闸把好的也挡了")

    def test_same_size_real_crest_still_200s(self, groups):
        """⭐ 最承重:一个**和占位图同尺寸**的真队徽必须仍然 200。

        这正是「按大小判」会误杀的那一个(实测 `Knowle` 与占位图同为 90381B)。
        """
        from nutmeg.v4.api.routes import _AF_PLACEHOLDER_SHA256

        ph_size = (LOGOS / f"{groups[_AF_PLACEHOLDER_SHA256][0]}.png").stat().st_size
        victim = next((n[0] for h, n in groups.items()
                       if h != _AF_PLACEHOLDER_SHA256
                       and (LOGOS / f"{n[0]}.png").stat().st_size == ph_size), None)
        if victim is None:
            pytest.skip("当前磁盘上没有与占位图同尺寸的真队徽")
        r = self._client().get(f"/api/v4/team-logo/{victim}")
        assert r.status_code == 200, f"{victim} 与占位图同尺寸但内容不同,被误杀了"
