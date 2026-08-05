"""nutmeg-ingest-football-data — 把 football-data.co.uk 的赛季 CSV 拉到本地源树。

2026-08-06 owner。补上训练链条**第一步就是手动**的那个洞:在此之前
`data/historical_sources/football_data_co_uk/` 里的 CSV 全靠人手放,代码里
一个下载入口都没有(grep 零命中)。

    https://www.football-data.co.uk/mmz4281/{season}/{div}.csv
    # 公开静态文件 · 免费 · 无认证 · 无 WAF(实测 2526/D2.csv → 200, 158KB)

用法::

    nutmeg-ingest-football-data                 # 当前+下个赛季,干跑(不写盘)
    nutmeg-ingest-football-data --apply         # 真的写
    nutmeg-ingest-football-data --seasons 2627 --apply

## 这个 CLI 的验收标准不是「下载成功」,是「新增了几行」

同族教训摆在这里,每一条都在下面变成了一道闸:

* ⚠️ **404 会伪装成空结果**:该站的 404 返回的是 **1271 字节的 HTML 错误页**,
  不是空 body。只看「有没有内容」的下载器会把错误页当 CSV 存下去,而下游
  `_read_europe_csv` 报的是「missing 'Div' column」—— 和「这个联赛没数据」
  长得完全不一样,但要翻到日志底下才看得见。⇒ `_looks_like_csv` 硬闸。
* 🩹 **空 body 静默冲掉好数据**(clubelo 自毁式覆盖):远端短暂抽风返回半截
  文件,覆盖过去就永久少一截。⇒ 行数变少时**默认拒绝覆盖**。
* ⭐ **抓空集也叫成功**:报告必须说「+N 行」而不是「✓ 完成」。休赛期 +0 是
  **正确答案**(不报错),但它和「远端挂了」必须在输出里长得不一样。

## 退出码

抓取**失败**(网络/非 200/不是 CSV/拒绝缩水)→ 1,让 cron 喊。
「一行没新增」→ 0 —— 休赛期本来就该是 0,把它当失败会训练出忽略报警的习惯。
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

import httpx

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"

#: 只拉我们**训练用**的 div。别写成「把该站所有联赛都拉下来」——
#: 源树是训练语料,多出来的联赛会悄悄改变 `load_all_matches` 的口径。
#: 这 14 个对应 `ingest.LEAGUE_NAMES` 里进生产训练集的那些。
TRAINED_DIVS: tuple[str, ...] = (
    "E0", "E1",          # 英超 / 英冠
    "SP1", "SP2",        # 西甲 / 西乙
    "D1", "D2",          # 德甲 / 德乙
    "I1", "I2",          # 意甲 / 意乙
    "F1", "F2",          # 法甲 / 法乙
    "N1",                # 荷甲
    "P1",                # 葡超
    "B1",                # 比甲
)

_DEFAULT_OUT = Path("data/historical_sources/football_data_co_uk/europe")

log = logging.getLogger(__name__)


def season_codes_for(today: dt.date) -> list[str]:
    """**上一个 + 当前**赛季码(``2526`` 形式)。

    欧洲赛季 8 月开、5 月结。取两个是因为**换季那几周两边都在动**:上赛季的
    补录/勘误还在写,新赛季的文件刚开始出现。实测 2026-08-06:``2627/SP1``
    已有 5 行(西甲开赛了),而 ``2627/D2`` 还是 404(德乙首轮 08-07)。

    ⚠️ 是「上一季+当前」不是「当前+下一季」——「下一季」要等整整一年才存在,
    每次跑白打 13 个 404。第一版就写错了,靠干跑输出里那一屏 ``2728/*`` 全 404
    看出来的。
    """
    y = today.year % 100
    cur = f"{y - 1:02d}{y:02d}" if today.month < 7 else f"{y:02d}{y + 1:02d}"
    a = int(cur[:2])
    prev = f"{(a - 1) % 100:02d}{a:02d}"
    return [prev, cur]


def _looks_like_csv(body: bytes) -> bool:
    """是不是 football-data 的赛季 CSV(而不是 404 的 HTML 错误页)。

    ⚠️ 该站 404 返回 200-长度的 **HTML**,不是空 body —— 只判长度会中招。
    认头部的 ``Div,Date``(带 UTF-8 BOM),这是所有欧洲赛季文件的固定首行。
    """
    head = body[:200].lstrip(b"\xef\xbb\xbf").lstrip()
    return head[:4].upper() == b"DIV," and b"Date" in head[:120]


def _data_rows(body: bytes) -> int:
    """数据行数(去掉表头与空行)。用来判断「新增了几行」和「有没有缩水」。"""
    lines = [ln for ln in body.splitlines() if ln.strip()]
    return max(0, len(lines) - 1)


def fetch_one(season: str, div: str, *, timeout: float = 30.0) -> tuple[bytes | None, str]:
    """拉一个 (season, div)。返回 ``(body, 说明)``;body=None 表示这次不可用。

    ⚠️ 404 **不是**错误 —— 新赛季文件还没出、或该联赛该赛季不存在,都是 404。
    这跟「网络挂了」要分开:前者返回 (None, "尚未发布"),不该让 cron 变红。
    """
    url = BASE_URL.format(season=season, div=div)
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        return None, f"❌ 网络失败 {type(exc).__name__}"
    if r.status_code == 404:
        return None, "· 尚未发布(404)"
    if r.status_code != 200:
        return None, f"❌ HTTP {r.status_code}"
    if not _looks_like_csv(r.content):
        # 正是「404 伪装成空结果」那一族:站点用 200 回了一张错误页/维护页。
        return None, f"❌ 不是 CSV(首 40 字节 {r.content[:40]!r})"
    return r.content, "ok"


def sync_season(
    season: str,
    out_root: Path,
    *,
    divs: tuple[str, ...] = TRAINED_DIVS,
    apply: bool = False,
    allow_shrink: bool = False,
) -> tuple[int, int, list[str]]:
    """同步一个赛季。返回 ``(新增行数, 硬失败数, 逐行报告)``。"""
    dest_dir = out_root / season
    lines: list[str] = []
    added = failures = 0

    for div in divs:
        body, note = fetch_one(season, div)
        dest = dest_dir / f"{div}.csv"
        before = _data_rows(dest.read_bytes()) if dest.exists() else 0

        if body is None:
            if note.startswith("❌"):
                failures += 1
            lines.append(f"  {season}/{div:<4} {note}")
            continue

        after = _data_rows(body)
        delta = after - before

        if delta < 0 and not allow_shrink:
            # 🩹 clubelo 自毁式覆盖的同族:远端短暂抽风给半截文件,覆盖=永久丢数据。
            failures += 1
            lines.append(
                f"  {season}/{div:<4} ⛔ 拒绝覆盖:远端 {after} 行 < 本地 {before} 行"
                f"(要真缩水就加 --allow-shrink)")
            continue

        if delta == 0 and before:
            lines.append(f"  {season}/{div:<4} = {after} 行(无变化)")
            continue

        if apply:
            dest_dir.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".csv.tmp")
            tmp.write_bytes(body)
            tmp.replace(dest)            # 原子替换,别让半截文件被下游读到
        added += delta
        lines.append(
            f"  {season}/{div:<4} {'✍️ ' if apply else '(干跑)'} {before} → {after} 行 "
            f"(+{delta})")

    return added, failures, lines


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="拉 football-data.co.uk 赛季 CSV 到训练源树")
    p.add_argument("--seasons", help="逗号分隔的赛季码(如 2526,2627);默认当前+下一季")
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--apply", action="store_true", help="真的写盘(默认干跑)")
    p.add_argument("--allow-shrink", action="store_true",
                   help="允许用行数更少的远端文件覆盖本地(默认拒绝)")
    p.add_argument("--today", help="覆盖今天的日期(YYYY-MM-DD),测试用")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(message)s")
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    seasons = ([s.strip() for s in args.seasons.split(",") if s.strip()]
               if args.seasons else season_codes_for(today))
    out_root = Path(args.out_dir)

    total_added = total_fail = 0
    report: list[str] = []
    for season in seasons:
        added, fails, lines = sync_season(
            season, out_root, apply=args.apply, allow_shrink=args.allow_shrink)
        total_added += added
        total_fail += fails
        report.extend(lines)

    mode = "写盘" if args.apply else "干跑(加 --apply 才写)"
    print(f"football-data 同步 · 赛季 {','.join(seasons)} · {mode}")
    print("\n".join(report))
    # ⭐ 结论行说的是**新增了几行**,不是「完成」。休赛期 +0 是正确答案,
    #    但它和「远端挂了」在这一行里长得不一样。
    print(f"\n⇒ 新增 {total_added} 行 · 硬失败 {total_fail} 个")
    if total_added == 0 and total_fail == 0:
        print("   (+0 且无失败 = 去看了、确实没有新数据。休赛期的正确答案。)")
    return 1 if total_fail else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
