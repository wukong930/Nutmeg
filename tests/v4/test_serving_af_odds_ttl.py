"""服务路径不许按 cron 的 2h TTL 去刷 API-Football 赔率(2026-09-03)。

病情(账单证据,零推理):一次**被动**(非 🔄)`/cup-market?days=7` 在 **94 秒**里
写了 **468** 个 AF 缓存文件、把 AF 每分钟限流打红 **32** 次;单分钟峰值 307 个,
比 cron 的高峰(13:00 的 204)还大。

根因和 2026-07-17 修过的那条**一模一样**,只是发生在另一条腿上:
`_fetch_odds_safe` 把 `max_age_seconds=2h` **写死**给所有调用方,而
🚨 **TTL 是刷新触发器不是只读闸** —— `refresh=False` 照样会因为缓存超龄发真请求。
那次只给 Odds API 装了 `oa_ttl_seconds`,AF 这条腿漏掉了。

⇒ 本文件钉的是**两个方向**:服务端拿到 6h(别再自己刷),cron 仍拿 2h(别顺手关掉
它该有的自刷新)。只钉一边都会在半年后被「对齐一下」改回去。
"""
from __future__ import annotations

import inspect

from nutmeg.v4.cli import ingest_odds
from nutmeg.v4.data.sources import api_football


def test_fetch_odds_safe_no_longer_hardcodes_the_ttl():
    """🚨 承重:TTL 必须由调用方给。写死 = 服务端和 cron 共用一块表。"""
    sig = inspect.signature(ingest_odds._fetch_odds_safe)
    assert "ttl_seconds" in sig.parameters, (
        "`_fetch_odds_safe` 又把 TTL 写死了 —— 服务端会重新开始按 2h 刷 AF")
    src = inspect.getsource(ingest_odds._fetch_odds_safe)
    assert "_ODDS_CACHE_TTL_SECONDS" not in src, (
        "函数体里又出现了那个常数 ⇒ 参数形同虚设")


def test_gather_rows_default_keeps_cron_behaviour_unchanged():
    """⚠️ 对照组:默认值必须**等于原来写死的那个值**,否则这次改动顺手改了 cron。"""
    default = inspect.signature(ingest_odds._gather_rows).parameters[
        "af_odds_ttl_seconds"].default
    assert default == api_football._ODDS_CACHE_TTL_SECONDS == 2 * 3600, (
        f"默认值 {default} ≠ 原写死值 {api_football._ODDS_CACHE_TTL_SECONDS} "
        f"⇒ cron 的自刷新被这次改动动了")


def test_every_serving_handler_passes_the_serving_ttl():
    """人口**自己发现**:凡是传了 `oa_ttl_seconds=_SERVING_OA_TTL_SECONDS` 的地方
    (= 已被认定为服务路径的那些),必须同时传 AF 那条腿的。

    ⛔ 不写死「3 个 handler」—— 写死的数会掉队:明天加第 4 个服务端点,
    只补 OA 不补 AF,这条也得红。
    """
    import pathlib
    src = pathlib.Path(
        "apps/api/src/nutmeg/v4/api/routes.py").read_text(encoding="utf-8")
    lines = src.splitlines()
    oa = [i for i, ln in enumerate(lines)
          if "oa_ttl_seconds=_SERVING_OA_TTL_SECONDS" in ln]

    # 🚨 人口非平凡:找不到调用点就说明发现器坏了,不是「服务端没有付费路径」
    assert len(oa) >= 3, f"只找到 {len(oa)} 个服务调用点 —— 发现器坏了"

    missing = [i + 1 for i in oa
               if "af_odds_ttl_seconds=_SERVING_OA_TTL_SECONDS" not in lines[i + 1]]
    assert not missing, (
        f"这些服务调用点只给 Odds API 装了表、AF 那条腿裸奔(行号 {missing})—— "
        f"正是 2026-07-17 修了一半留下的那种形状")


def test_the_two_legs_share_one_serving_constant():
    """两条腿必须共用同一个服务常数,别各调各的。"""
    from nutmeg.v4.api import routes
    assert routes._SERVING_OA_TTL_SECONDS == 6 * 3600
    assert routes._SERVING_OA_TTL_SECONDS > api_football._ODDS_CACHE_TTL_SECONDS, (
        "服务端 TTL 不比 cron 的长就等于没修")
