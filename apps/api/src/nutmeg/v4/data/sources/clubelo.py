"""Clubelo ELO history adapter (http://clubelo.com).

API: ``GET http://api.clubelo.com/<TeamName>`` returns CSV with columns
``Rank, Club, Country, Level, Elo, From, To`` — one row per ELO change.

V5 uses this as an INDEPENDENT ELO baseline (the existing V4 Elo is computed
internally and is per-league; clubelo is cross-country and uses its own K-factor),
providing a second view of team strength that the GBM can blend with.

Team-name expectations: clubelo uses URL-friendly names without spaces
(``ManCity``, ``ManUnited``, ``RealMadrid``, ``Atletico``). We maintain a
clubelo-specific alias dict because our team_canonical primarily targets
understat/fbref-style spellings.

The full per-team history is small (~30 KB / ~1k rows back to 1946) so we
fetch once and cache to ``data/external/clubelo/<team>.parquet``.
"""
from __future__ import annotations

import io
import logging
import time
from pathlib import Path

import httpx
import pandas as pd


log = logging.getLogger(__name__)

CLUBELO_BASE_URL = "http://api.clubelo.com"
DEFAULT_CACHE_DIR = Path("data/external/clubelo")
DEFAULT_TIMEOUT = 8.0
THROTTLE_SECONDS = 0.1  # clubelo doesn't rate-limit on the public endpoint


# V4 canonical name → clubelo URL slug. Only entries that differ from canonical.
# Clubelo URL convention: PascalCase, no spaces, ASCII.
CLUBELO_SLUGS: dict[str, str] = {
    "Man United": "ManUnited",
    "Man City": "ManCity",
    "Nott'm Forest": "Forest",
    "West Ham": "WestHam",
    "Aston Villa": "AstonVilla",
    "West Brom": "WestBrom",
    "Sheffield United": "SheffieldUnited",
    "Crystal Palace": "CrystalPalace",
    "Ath Bilbao": "Bilbao",
    "Ath Madrid": "Atletico",
    "Real Madrid": "RealMadrid",
    "Sociedad": "Sociedad",
    "Las Palmas": "LasPalmas",
    "Espanol": "Espanyol",
    "Valladolid": "Valladolid",
    "Bayern Munich": "Bayern",
    "Dortmund": "Dortmund",
    "RB Leipzig": "RBLeipzig",
    "Leverkusen": "Leverkusen",
    "Ein Frankfurt": "Frankfurt",
    "M'gladbach": "Gladbach",
    "FC Koln": "Koeln",
    "Union Berlin": "UnionBerlin",
    "Schalke 04": "Schalke",
    "Hertha": "Hertha",
    "St Pauli": "StPauli",
    # NB "Werder Bremen"/"Holstein Kiel" 原本在这里,值是错的(Bremen/Kiel → 0 行);
    # 已改正并移到下面 2026-07-15 那个块里,别在这重新加回来(重复键 = 后者胜,易踩)。
    "Le Havre": "LeHavre",
    "PSV Eindhoven": "PSV",
    "NEC Nijmegen": "Nijmegen",
    "Sparta Rotterdam": "SpartaRotterdam",
    "Go Ahead Eagles": "GoAheadEagles",
    "For Sittard": "Sittard",
    "Sp Braga": "Braga",

    # ── 2026-07-15 修正 + 补齐 ───────────────────────────────────────────────
    # 权威来源:`http://api.clubelo.com/<YYYY-MM-DD>` 一次返回全部 ~589 家俱乐部的
    # 【准确名字】+ 当前 Elo。slug 规则 = 权威名【去掉空格,保留连字符】(实测:
    # ParisSG→4592 行 / Saint-Etienne→6024 / Alkmaar→3573,而 Paris%20SG→0)。
    # 下面每一条都【逐个 fetch 验证过行数】,不是模糊匹配 —— 模糊匹配会把
    # `Club Brugge` 配到 `Cercle Brugge`(另一家俱乐部)= 静默污染。以后要补别名,
    # 先拉那个日期端点拿权威名,再验证,别猜。
    #
    # ⚠️ 前 5 条是【改正原本就错的别名】(它们一直返回空 → 静默丢特征):
    "Paris SG": "ParisSG",              # 原 "PSG" → 0 行
    "AZ Alkmaar": "Alkmaar",            # 原 "AZ" → 0 行
    "Holstein Kiel": "Holstein",        # 原 "Kiel" → 0 行
    "Werder Bremen": "Werder",          # 原 "Bremen" → 0 行
    "St Etienne": "Saint-Etienne",      # 原 "SaintEtienne" → 0 行(权威名带连字符)
    # 以下为新增(默认 slug 生成规则对不上权威名):
    "Club Brugge": "Brugge",            # ⚠️ 不是 Cercle Brugge!
    "AVS": "AVSFutebol",
    "Andorra": "AndorraCF",
    "Estrela": "EstrelaAmadora",
    "Nurnberg": "Nuernberg",            # ü→ue 转写
    "Osnabruck": "Osnabrueck",
    "Sudtirol": "Suedtirol",
    "Oud-Heverlee Leuven": "Leuven",
    "Pau FC": "Pau",
    "Sp Gijon": "Gijon",
    "St. Gilloise": "StGillis",
    "Vallecano": "RayoVallecano",
    "Virtus Entella": "Entella",
    "Waregem": "ZulteWaregem",
}


def _slug_for(team: str) -> str:
    """Convert a V4 canonical team name to the clubelo URL slug."""
    return CLUBELO_SLUGS.get(team, team.replace(" ", "").replace("'", ""))


def fetch_team_history(team: str, *, client: httpx.Client | None = None) -> pd.DataFrame:
    """Fetch full ELO history for a single team (V4 canonical name).

    Returns a DataFrame with normalized columns:
        team_canonical (str), clubelo_slug (str), country (str),
        elo (float), from_date (date), to_date (date)
    Raises httpx.HTTPStatusError on non-2xx after retries.
    """
    slug = _slug_for(team)
    url = f"{CLUBELO_BASE_URL}/{slug}"
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        resp = client.get(url)
        resp.raise_for_status()
        if not resp.text.strip():
            log.warning("Clubelo returned empty body for %s (slug=%s)", team, slug)
            return _empty_history_frame(team, slug)
        raw = pd.read_csv(io.StringIO(resp.text))
    finally:
        if owns_client:
            client.close()

    if raw.empty:
        return _empty_history_frame(team, slug)

    raw["From"] = pd.to_datetime(raw["From"], errors="coerce").dt.date
    raw["To"] = pd.to_datetime(raw["To"], errors="coerce").dt.date
    out = pd.DataFrame(
        {
            "team_canonical": team,
            "clubelo_slug": slug,
            "country": raw["Country"],
            "elo": raw["Elo"].astype(float),
            "from_date": raw["From"],
            "to_date": raw["To"],
        }
    )
    return out.dropna(subset=["from_date", "to_date", "elo"]).reset_index(drop=True)


def _empty_history_frame(team: str, slug: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "team_canonical": pd.Series(dtype="object"),
            "clubelo_slug": pd.Series(dtype="object"),
            "country": pd.Series(dtype="object"),
            "elo": pd.Series(dtype="float64"),
            "from_date": pd.Series(dtype="object"),
            "to_date": pd.Series(dtype="object"),
        }
    )


def cache_path(team: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    """Where the per-team parquet lives."""
    safe = team.replace(" ", "_").replace("'", "").replace("/", "_")
    return cache_dir / f"{safe}.parquet"


def ingest_teams(
    teams: list[str],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
    refresh_empty: bool = False,
    throttle_seconds: float = THROTTLE_SECONDS,
) -> pd.DataFrame:
    """Fetch (and cache) ELO history for every team in `teams`.

    Returns a long-format DataFrame with one row per (team, ELO change interval).
    Skip logic:
    - cached parquet exists AND refresh=False AND it has rows  → use cache
    - cached parquet exists AND refresh_empty=True AND 0 rows  → re-fetch
      (used after a rate-limit episode where some requests landed empty parquets)
    - refresh=True                                              → always re-fetch
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    refreshed_empty = 0
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        for team in teams:
            p = cache_path(team, cache_dir)
            if p.exists() and not refresh:
                cached = pd.read_parquet(p)
                if refresh_empty and cached.empty:
                    log.info("Refreshing empty cache for %s", team)
                    refreshed_empty += 1
                    # fall through to re-fetch
                else:
                    frames.append(cached)
                    continue
            try:
                df = fetch_team_history(team, client=client)
            except Exception as exc:  # noqa: BLE001 — log and continue with empty
                log.warning("Clubelo fetch failed for %s: %s", team, exc)
                df = _empty_history_frame(team, _slug_for(team))
            # ⚠️ 2026-07-15 — 绝不用【空结果】覆盖【已有的好数据】。
            # 这行以前是无条件 df.to_parquet():clubelo 限流时不报错、只回空 body →
            # fetch_team_history 返回空 frame → 直接把好数据冲成空文件。这正是 335 个
            # 缓存里 181 个(54%)变空的成因 —— 包括 Ajax(源上 5736 行)、斯图加特、
            # 佛罗伦萨、波尔图这些主力队;而模型有 clubelo_available 标志会静默降级,
            # 所以整整两个月没人发现。有了这道闸,一次 --refresh 撞上限流最多是「没更新」
            # (下次再来),而不是「把历史毁掉」——周更 cron 才敢开。
            if df.empty and p.exists():
                cached = pd.read_parquet(p)
                if not cached.empty:
                    log.warning(
                        "Clubelo returned EMPTY for %s but cache has %d rows — keeping "
                        "cache (rate-limit/blip, not a real delisting)", team, len(cached))
                    frames.append(cached)
                    time.sleep(throttle_seconds)
                    continue
            df.to_parquet(p, index=False)
            frames.append(df)
            time.sleep(throttle_seconds)
    if refresh_empty:
        log.info("Refresh-empty mode: re-fetched %d previously empty caches", refreshed_empty)
    if not frames:
        return _empty_history_frame("", "")
    return pd.concat(frames, ignore_index=True)


def elo_on_date(history: pd.DataFrame, team: str, match_date: pd.Timestamp | str) -> float | None:
    """Look up a team's clubelo ELO on a specific date.

    Returns the ELO value from the row where ``from_date <= match_date <= to_date``,
    or None if the team has no history covering that date (e.g., team didn't
    exist or was lower-division and dropped off clubelo's tracked level).
    """
    if isinstance(match_date, str):
        match_date = pd.to_datetime(match_date).date()
    elif isinstance(match_date, pd.Timestamp):
        match_date = match_date.date()
    h = history[history["team_canonical"] == team]
    if h.empty:
        return None
    mask = (h["from_date"] <= match_date) & (h["to_date"] >= match_date)
    rows = h[mask]
    if rows.empty:
        return None
    return float(rows["elo"].iloc[0])
