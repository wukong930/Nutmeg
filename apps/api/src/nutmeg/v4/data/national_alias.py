"""Measured national-team name-synonym canonicalizer for cross-source joins.

API-Football, 竞彩 (via ``zh_to_canonical``) and The Odds API sometimes spell the
same nation differently. A bare ``normalize_name`` join then silently never
matches — 2026-07-01 audit D1: API-Football returns ``Czechia`` while 竞彩 stored
``Czech Republic``, which left 44 settle rows (jingcai_sp + league_predictions +
比分) permanently UNSETTLED with the results already in-hand.

Fix: route BOTH sides of a cross-source join through ``national_match_key`` — it
maps every known spelling variant of a nation onto ONE canonical key, so the two
sides match regardless of which spelling each source used (and regardless of
which spelling API-Football happens to return on a given day). Entries are
MEASURED against real data, never guessed (see [[cross-source-team-name-mismatch]]);
extend as new mismatches are observed.
"""
from __future__ import annotations

from nutmeg.utils.team_canonical import normalize_name

# normalize_name(variant) -> canonical normalize_name. Every variant of a nation
# collapses to the same key, so a join keyed on national_match_key matches either
# spelling on either side.
_NATIONAL_ALIAS: dict[str, str] = {
    # 2026-07-01 (audit D1, measured on the stuck settle rows): API-Football
    # returns 'Czechia'; 竞彩 stores 'Czech Republic' (via zh_to_canonical).
    "czech republic": "czechia",
}


def national_match_key(name: str | None) -> str:
    """``normalize_name(name)`` collapsed through the measured national-synonym map.

    Use on BOTH sides of any cross-source team join so a nation's differing
    spellings resolve to one key. Non-national / already-aligned names pass
    through unchanged (identity), so it is safe to apply everywhere.
    """
    n = normalize_name(name or "")
    return _NATIONAL_ALIAS.get(n, n)
