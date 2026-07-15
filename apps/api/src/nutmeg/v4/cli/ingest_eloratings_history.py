"""nutmeg-ingest-eloratings-history — 逐场【赛前】Elo 回填(时点,零泄漏)。

为什么存在(2026-07-15):`nutmeg-ingest-eloratings` 抓的 World.tsv 是**当下**排行榜,
没有时间维度。于是 WC walk-forward 用 2026 年的 Elo 去预测 2018 年的球 —— 未来函数,
且同一份快照贴给两个赛季 → 两季共有的 24 队 24/24 Elo 相同 → 模型区分不了 2018-法国
和 2022-法国,纯模型 log-loss 1.0983 ≈ 均匀先验 1.0986(什么都没学到)。详见
`tests/v4/test_national_team_predict.py::TestWalkForwardOnWC` 的 docstring。

本 CLI 抓 eloratings.net 的**逐场结果**档案,还原每场比赛的【赛前】Elo:

    https://www.eloratings.net/{year}_results.tsv   (免费 · 无认证 · 无 WAF)

    data/external/eloratings_history/matches_{year}.parquet

⚠️ 陷阱 1 — 源文件给的是【赛后】Elo,直接用照样泄漏本场结果。列 9 是本场 Elo 涨跌
(对主队;Elo 零和 → 客队取反),所以还原:

    home_elo_pre = home_elo_post − change
    away_elo_pre = away_elo_post + change

定性依据:法国 2018 首场(3/23 2:3 负哥伦比亚,change=−14,主队列=1974)→
1974−(−14)=1988,正是 `2018_start.tsv` 里 FR 的值(=2017 年末);而 1974 不是。
端到端验证见 tests/v4/test_eloratings_history.py(重建法国 2018 全年 1988→2092,
与独立来源 2018.tsv 分毫不差,逐场 post[N]==pre[N+1] 无断链)。

⚠️ 陷阱 2 — 别复用 `ingest_eloratings.parse_world_tsv`:年份档案比 World.tsv **多一个
前导涨跌列**,喂进去会【静默返回 0 行】(0 行不报错,只是数据凭空消失)。

源 TSV 列(tab 分隔,无表头):
    0=年 1=月 2=日 3=主队码 4=客队码 5=主球 6=客球 7=赛事码 8=场地国
    9=本场Elo涨跌(主队) 10=主队Elo(赛后) 11=客队Elo(赛后) 12/13=排名涨跌 14/15=排名
赛事码 `WC` = 世界杯(每届正好 64 场);队码是 **2 字母**(FR/HR/AR,不是 FRA)。
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import httpx
import pandas as pd

log = logging.getLogger("ingest_eloratings_history")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RESULTS_URL = "https://www.eloratings.net/{year}_results.tsv"
_DEFAULT_OUT = Path("data/external/eloratings_history")

_COLUMNS = [
    "date", "season", "tournament", "venue_code",
    "home_code", "away_code", "home_goals", "away_goals",
    "home_elo_pre", "away_elo_pre", "home_elo_post", "away_elo_post",
    "elo_change", "home_rank", "away_rank",
]


def _num(s: str) -> float:
    """eloratings 用 U+2212 减号(−)而不是 ASCII '-',直接 float() 会炸。"""
    return float(s.strip().replace("−", "-").replace("+", "") or 0)


def parse_results_tsv(text: str, season: int) -> pd.DataFrame:
    """`{year}_results.tsv` → 逐场 frame,含还原出的【赛前】Elo。

    解析不干净的行整行跳过(源档案偶有空行/残行)。返回的 elo_*_pre 才是可用于
    预测的特征;elo_*_post 一并保留只为可审计(pre = post − change 的还原过程)。
    """
    rows: list[dict] = []
    for line in text.splitlines():
        p = line.split("\t")
        if len(p) < 12:
            continue
        try:
            chg = _num(p[9])
            home_post, away_post = _num(p[10]), _num(p[11])
            rows.append({
                "date": f"{int(p[0]):04d}-{int(p[1]):02d}-{int(p[2]):02d}",
                "season": season,
                "tournament": p[7].strip(),
                "venue_code": p[8].strip(),
                "home_code": p[3].strip(),
                "away_code": p[4].strip(),
                "home_goals": int(p[5]),
                "away_goals": int(p[6]),
                # ⚠️ 核心:源给赛后值,减掉本场涨跌才是赛前(Elo 零和 → 客队取反)
                "home_elo_pre": home_post - chg,
                "away_elo_pre": away_post + chg,
                "home_elo_post": home_post,
                "away_elo_post": away_post,
                "elo_change": chg,
                "home_rank": int(_num(p[14])) if len(p) > 14 and p[14].strip() else None,
                "away_rank": int(_num(p[15])) if len(p) > 15 and p[15].strip() else None,
            })
        except (ValueError, IndexError):
            continue
    return pd.DataFrame(rows, columns=_COLUMNS)


def fetch_results_tsv(year: int, *, timeout: float = 25.0) -> str:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(RESULTS_URL.format(year=year))
        resp.raise_for_status()
        return resp.text


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="回填 eloratings 逐场【赛前】Elo(时点,零泄漏)")
    p.add_argument("--year", type=int, action="append", required=True,
                   help="赛季年份,可重复 (--year 2018 --year 2022)")
    p.add_argument("--tournament", default=None,
                   help="只留该赛事码 (如 WC = 世界杯,每届 64 场);默认全留")
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--from-file", default=None,
                   help="离线:读本地 TSV 而不联网(只在 --year 单值时有意义)")
    args = p.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for year in args.year:
        try:
            text = (Path(args.from_file).read_text(encoding="utf-8", errors="replace")
                    if args.from_file else fetch_results_tsv(year))
        except Exception as exc:  # noqa: BLE001 — fail-soft per year, 其余年份继续
            log.error("  ✗ %s 抓取失败: %s", year, exc)
            continue
        df = parse_results_tsv(text, year)
        if args.tournament:
            df = df[df["tournament"] == args.tournament].reset_index(drop=True)
        if df.empty:
            # 0 行不是"没事" —— 多半是 schema 漂了(见模块 docstring 陷阱 2)
            log.error("  ✗ %s 解析出 0 行 — 源 schema 可能变了,别当成空档案", year)
            continue
        dest = out_dir / f"matches_{year}.parquet"
        df.to_parquet(dest, index=False)
        total += len(df)
        log.info("  ✓ %s → %s (%d 场, %s)", year, dest.name, len(df),
                 f"赛事={args.tournament}" if args.tournament else "全赛事")
    log.info("=" * 56)
    log.info("共 %d 场落盘于 %s", total, out_dir)
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
