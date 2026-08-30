"""Shared helpers for the recommendation CLIs.

Extracted V12 (post-V11 audit). ``cli/recommend.py`` (``_read_fixtures``)
and ``cli/recommend_pool.py`` (``_read_pool_fixtures``) both did the same
read-CSV + required-column-check + date-parse skeleton. Centralizing it
keeps the fixtures-CSV column contract in one place; the pool reader still
adds its own ``pick``-value validation on top.

(``cli/rec.py`` already imports the two reader functions rather than
re-implementing them, so there is no third copy.)
"""
from __future__ import annotations

import datetime as _dt
import json as _json
from pathlib import Path

import pandas as pd

# The minimal columns every recommendation fixtures CSV must carry.
def report_history_dir(out_path: str | Path) -> Path:
    """``logs/X_latest.md`` → ``logs/X_history/``。**命名规则一处定义。**

    ⚠️ 用 ``removesuffix("_latest")`` 而不是裸 ``stem`` —— 默认文件名是
    ``..._latest.md``,直接拼会得到 ``X_latest_history/``(``sigma_p_fit``
    第一版就是这么错的,它的注释里还留着那条记录)。
    """
    p = Path(out_path)
    return p.parent / f"{p.stem.removesuffix('_latest')}_history"


def write_report_with_history(
    out_path: str | Path,
    text: str,
    *,
    payload: object | None = None,
    archive: bool = True,
    today: str | None = None,
) -> Path | None:
    """写 ``_latest`` 报告 + 一份按日期命名的历史副本;返回历史目录(未归档 None)。

    ## 为什么必须留历史
    只写 ``_latest.md``(每次覆盖、零历史)= δ 仪表 2026-08 踩过的坑:prereg 写着
    「连续两周变差才回滚」,而**产物根本判不了「上周是多少」**,到评估点才发现
    手上只有一个点。同日重跑覆盖当天那份 = 当天最新读数。
    ``payload`` 非空时同时落 ``.json`` —— 给下次自比用(解析 markdown 太脆)。

    ## 为什么抽成共享函数
    2026-08-30 抽出来之前是**两份副本,而且已经分叉**:``delta_calibration``
    硬编码目录名(``--out foo.md`` 也写进 ``delta_calibration_history/``),
    ``sigma_p_fit`` 由 stem 推导。生产路径下两者恰好一致,所以谁都没发现。
    同一天另一处手维护副本掉队的代价是**静默跳过 38% 的人口**
    (见 ``scripts/backfill_closing_gap.py`` 的模块注释)。
    ⇒ 第三个消费者出现时**抽**,不是加第三份。
    """
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    if not archive:
        return None
    day = today or f"{_dt.date.today():%Y-%m-%d}"
    hist = report_history_dir(p)
    hist.mkdir(parents=True, exist_ok=True)
    (hist / f"{day}{p.suffix}").write_text(text, encoding="utf-8")
    if payload is not None:
        (hist / f"{day}.json").write_text(
            _json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return hist


BASE_REQUIRED_COLUMNS = [
    "date", "league", "home_team", "away_team",
    "psc_home", "psc_draw", "psc_away",
]


def read_fixtures_csv(
    path: str,
    *,
    extra_required: list[str] | None = None,
    label: str = "input CSV",
) -> pd.DataFrame:
    """Read a fixtures CSV, validate required columns, parse ``date``.

    Parameters
    ----------
    path : CSV path.
    extra_required : columns required beyond ``BASE_REQUIRED_COLUMNS``
        (e.g. ``["pick"]`` for the compound-pool CSV).
    label : prefix used in the missing-column error so callers keep
        distinguishable messages ("input CSV" vs "pool CSV").

    Raises
    ------
    ValueError : if any required column is absent.
    """
    df = pd.read_csv(path)
    required = list(BASE_REQUIRED_COLUMNS) + list(extra_required or [])
    for c in required:
        if c not in df.columns:
            raise ValueError(f"{label} missing required column: {c}")
    df["date"] = pd.to_datetime(df["date"])
    return df
