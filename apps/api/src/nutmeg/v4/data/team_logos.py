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
