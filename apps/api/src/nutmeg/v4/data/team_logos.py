"""V11 P1-FE#2 Day 2 — team logo cache + slug helpers.

Logos are downloaded into ``data/external/team_logos/`` (gitignored).
Each file is named ``<slug>.png`` where ``slug = team_slug(team_name)``.

Lookup flow at serve time:
  ``/api/v4/team-logo/{slug}`` → 200 if file exists, 404 otherwise.
  The dashboard ``<img onerror=...>`` falls back to the initials
  circle on 404, so a missing logo file is never user-visible.

Ingestion is a one-shot via ``nutmeg-ingest-team-logos`` (API-Football
``/teams?league=…&season=…`` endpoint returns ``logo`` URLs which we
fetch + cache locally).
"""
from __future__ import annotations

import re
from pathlib import Path


LOGO_CACHE_DIR = Path("data/external/team_logos")


def team_slug(team_name: str) -> str:
    """Return URL-safe slug for a team name.

    Lowercase, ASCII-fold accents, collapse whitespace + punctuation to ``_``.

    Examples
    --------
    >>> team_slug("Bayern Munich")
    'bayern_munich'
    >>> team_slug("Bayer Leverkusen")
    'bayer_leverkusen'
    >>> team_slug("Paris SG")
    'paris_sg'
    >>> team_slug("Saint-Etienne")
    'saint_etienne'
    >>> team_slug("AC Milan")
    'ac_milan'
    """
    if not team_name:
        return ""
    s = team_name.strip().lower()
    # Collapse anything non-alphanumeric to underscore
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s


def logo_path(team_name: str, *, cache_dir: Path | None = None) -> Path:
    """Return the on-disk path for a team's logo PNG."""
    base = cache_dir if cache_dir is not None else LOGO_CACHE_DIR
    return base / f"{team_slug(team_name)}.png"


def logo_exists(team_name: str, *, cache_dir: Path | None = None) -> bool:
    """True if the logo PNG has been cached locally."""
    return logo_path(team_name, cache_dir=cache_dir).exists()


# --------------------------------------------------------------------------
# 面板国旗表的 Python 读取器(2026-09-21)
# --------------------------------------------------------------------------
#: 📌 **为什么要读 HTML,而不是在 Python 侧另建一张国家队表。**
#:
#: `ingest_team_logos` 需要回答的问题是:「这支队会不会被渲成国旗?」——
#: 决定这件事的**就是** `dashboard.html` 里的 `_NATION_FLAG`(`teamLogo()`
#: 先查它、命中就直接返回旗,根本不走队徽那条路)。任何 Python 侧的代理表
#: 都只是它的**镜子**,而镜子会滞后。
#:
#: 🚨 这不是假设,是 2026-09-21 量出来的。四个候选判据跑 942 支可投注人口,
#:    真值取「面板真的会渲成国旗的 62 支」:
#:        ① `lookup_elo_code(name)`(现状)                 漏 13
#:        ② + 剥掉 `U23`/`W` 后缀再查 Elo                   漏 7
#:        ③ `name in _NATIONAL_TEAMS`                       漏 13
#:        ④ ②③ 全都用上                                     漏 3
#:    全都不完整 —— 因为它们引用的都是**手工维护、会滞后**的表
#:    (`Korea DPR` / `Kyrgyz Republic` / `Philippines` 这些拼法就不在 Elo 表里)。
#: ⇒ 直接读那张决定渲染的表,**按构造不可能漂**。
#:
#: ⚠️ 块内有注释行,所以必须**先逐行剥掉 `//` 再正则**,否则会把注释里的
#:    引号当成条目。护栏拿 node 的 `JSON.parse` 当真值对拍。
_FLAG_TABLE_START = "const _NATION_FLAG = {"
_FLAG_TABLE_END = "function teamLogo(name)"
_DASHBOARD = Path(__file__).resolve().parents[1] / "api" / "static" / "dashboard.html"
_FLAG_ENTRY = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"')


def flag_table(dashboard: Path | None = None) -> dict[str, str]:
    """`dashboard.html` 的 `_NATION_FLAG`(精确队名 → 国旗 emoji)。

    读不到文件时抛 `FileNotFoundError` —— ⛔ **故意不 fail-soft**:
    静默返回空表会让「跳过国家队」这条过滤变成 no-op,而症状是
    「多了一堆没人看的 PNG」,没人会当 bug 报。
    """
    path = dashboard or _DASHBOARD
    js = path.read_text(encoding="utf-8")
    i = js.index(_FLAG_TABLE_START)
    j = js.index(_FLAG_TABLE_END, i)
    block = "\n".join(line.split("//")[0] for line in js[i:j].splitlines())
    return dict(_FLAG_ENTRY.findall(block))


def renders_as_flag(team_name: str, *, table: dict[str, str] | None = None) -> bool:
    """这支队在面板上会被渲成国旗吗(⇒ 不该给它下队徽 PNG)。"""
    return team_name in (flag_table() if table is None else table)

