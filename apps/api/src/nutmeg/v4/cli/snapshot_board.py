"""nutmeg-snapshot-board — 把当前盘面落成反事实快照。

⭐ **它打本地 HTTP 端点,不自己 gather。** 记的就是浏览器拿到的同一批字节 ⇒
零重复逻辑,也不可能和用户看到的漂移。这是 2026-08-10/11 反复吃亏后的做法:
「读出来的路径 ≠ 跑着的路径」,而端点是**跑着的那条**。

代价:要求服务在跑。服务没起就**响亮地失败**(不静默写半份),
这正确 —— 半份快照比没有快照更坏。

## 🚨 「200 不等于成功」(2026-08-12 审查的 blocker)

两个盘面端点在内部抓取失败时都是 `except Exception -> rows = []`
(routes.py 的 cup-market / sp-calc 两处同构),**照样返回 HTTP 200**。
所以 `raise_for_status()` 拦不住喂料断:配额耗尽、Odds API 401 熔断、AF 429,
全都长成「200 + predictions: []」。

第一版只取 `predictions`,把响应里仅有的两个鉴别器
`fixtures_fetched` / `pending_fixtures` **当场丢掉**,然后打印
「证明这次真的跑过且盘面是空的」—— 审查用桩服务跑出来:喂料断 vs 真空盘
**逐字相同的输出、完全不可区分的库**。⇒ 现在两个都收下并落进 provenance,
那句断言也降级成陈述:**只说它真的知道的数**。

⚠️ 残余盲区(别以为补完就全绿):`fixtures_fetched=0` 依旧分不出
「AF 赛程整个取不到」和「真休赛期」—— 要彻底关掉这个家族,得让端点把
「这次吞了几次上游异常」计进响应。已记 TODO,不在本次范围。

## 配额

`refresh_odds=False`(本 CLI 从不传 True)⇒ `_gather_rows` 走缓存直到
`_SERVING_OA_TTL_SECONDS`(6h)过期。端点注释原话:「Cost is bounded by the
TTL, not by call frequency」。但要诚实:面板整天不开时,本 cron 就是那个
**刷新者**,最坏 ≤4 次刷新/天。调度按 6h 对齐,不跟 TTL 对着干。

用法:
    nutmeg-snapshot-board
    nutmeg-snapshot-board --dry-run          # 不写库
    nutmeg-snapshot-board --days 5 --note "手动:欧超杯前"

⚠️ `--dry-run` **不是干跑**:它照样把两个端点打完(要拿真实 payload 才能报数),
   所以外部刷新该花的一样花。它只保证**不写库**。
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

import httpx

from nutmeg.v4.observation.board_snapshot import _legs_from_prediction, snapshot_board

log = logging.getLogger("snapshot_board")

_DEFAULT_BASE = "http://127.0.0.1:8080/api/v4"
#: 两个盘面端点 —— 市场模式(杯赛/非训练联赛)+ 标准模式(13 个训练联赛)。
#: ⚠️ 两个都要,否则快照的人口只有半边;而「半边」在事后分析里长得跟「全部」一样。
_BOARDS = ("/predictions/cup-market", "/predictions/sp-calc")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/v4_observation.db")
    ap.add_argument("--base-url", default=_DEFAULT_BASE)
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--note", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    preds: list[dict] = []
    feed: dict[str, dict] = {}
    with httpx.Client(timeout=a.timeout) as cli:
        try:
            fe = cli.get(f"{a.base_url}/version").json().get("version")
        except Exception:                                 # noqa: BLE001
            fe = None
        for path in _BOARDS:
            try:
                r = cli.get(f"{a.base_url}{path}", params={"days": a.days})
                r.raise_for_status()
                body = r.json()
            except Exception as exc:                      # noqa: BLE001
                # ⛔ 一个端点挂了就整体失败 —— 只记半边盘面,事后会被当成全部。
                log.error("盘面端点 %s 取不到:%s", path, exc)
                return 1
            got = body.get("predictions") or []
            # ⭐ 这三个数就是「盘面空 vs 喂料断」的全部分辨力。丢掉它们,
            #   两种状态在库里永远同形(见文件头)。
            feed[path] = {
                "predictions": len(got),
                "fixtures_fetched": body.get("fixtures_fetched"),
                "pending": len(body.get("pending_fixtures") or []),
            }
            log.info("%-28s 盘面 %d 场 · 抓到 %s 场 · 待开盘 %d 场",
                     path, len(got), body.get("fixtures_fetched"),
                     feed[path]["pending"])
            preds.extend(got)

    fetched = sum(v["fixtures_fetched"] or 0 for v in feed.values())
    if a.dry_run:
        now = dt.datetime.now(dt.UTC)
        legs = sum(len(_legs_from_prediction(p, now)) for p in preds)
        log.info("[dry-run] %d 场 → %d 条腿(未写库);抓到 %d 场;FE=%s",
                 len(preds), legs, fetched, fe)
        return 0

    res = snapshot_board(preds, a.db, fe_version=fe, feed=feed, note=a.note)
    log.info("✅ 快照 #%d:%d 场 · %d 条腿(新落库 %d)· FE=%s",
             res["provenance_id"], res["matches"], res["legs"], res["inserted"], fe)
    if res["legs"] == 0:
        # ⭐ 空盘面**照样写 provenance 行** —— 「那天什么都没有」必须和
        # 「那天没跑」分得开。但**不再断言**盘面本来就是空的:那句话第一版是假的。
        if fetched:
            log.warning("⚠️ 0 条腿,但端点报抓到 %d 场 ⇒ **喂料可能断了**,不是空盘:%s",
                        fetched, feed)
        else:
            log.info("   (0 条腿 · fixtures_fetched=0;喂料状态已落 feed_json,"
                     "由回放者判断,本行不下「盘面本来就是空的」这个结论)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
