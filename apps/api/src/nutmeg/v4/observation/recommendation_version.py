"""V11 P1-FE#5 — recommendation version hashing.

Each recommendation set gets a deterministic fingerprint computed from
its picks. The frontend stores the last-seen fingerprint in
localStorage; when polling returns a different one, the user gets a
"推荐已更新" banner with a per-recommendation diff (which leg moved).

Two levels of fingerprint:

  - ``selection_fingerprint(legs) -> str``: 12-char SHA1 hex of the
    sorted ``(match_id, market_type, outcome)`` tuples in one
    recommendation. Stable: re-ordering legs doesn't change the hash,
    flipping an outcome does.
  - ``version_hash(...) -> str``: 12-char SHA1 hex covering every
    selection_fingerprint plus the fixture odds digest. Used as the
    one-stop "did anything change since the last poll" signal.

We don't include stake / probability / EV in the hash because those
move continuously (model probability drifts every refresh); we only
care about whether the *picks* changed. Odds drift is captured
separately so the UI can highlight "same picks, but odds moved".
"""
from __future__ import annotations

import hashlib
from typing import Any, Iterable


_HASH_LEN = 12


def _sha1_short(payload: bytes) -> str:
    return hashlib.sha1(payload).hexdigest()[:_HASH_LEN]


def _normalize_selection(d: dict[str, Any]) -> tuple[str, str, str]:
    """Extract the identity 3-tuple of a leg / single ticket / pool leg.

    All three response shapes carry ``match_id``, ``market_type``, and
    ``outcome``. Anything missing → empty string so hashes still stabilize.
    """
    return (
        str(d.get("match_id") or ""),
        str(d.get("market_type") or ""),
        str(d.get("outcome") or ""),
    )


def selection_fingerprint(items: Iterable[dict[str, Any]]) -> str:
    """Fingerprint a list of (match_id, market_type, outcome) tuples.

    Used by:
      - parlay_recommendations: items = each leg's first selection
      - single_recommendations: items = each ticket (1 leg per ticket)
      - pool tickets: items = each leg of the ticket

    Sorted before hashing so leg order doesn't matter.
    """
    triples = sorted({_normalize_selection(d) for d in items})
    payload = "|".join(f"{m}::{mk}::{o}" for m, mk, o in triples).encode()
    return _sha1_short(payload)


def _parlay_leg_to_dict(leg: Any) -> dict[str, Any]:
    """Pull the (match_id, market_type, outcome) for ONE parlay leg.

    Parlay legs hold a `selections` list — for top-1 picks each leg has
    exactly one selection. We use the FIRST selection's outcome (the
    primary pick); ties don't affect the fingerprint.
    """
    if hasattr(leg, "model_dump"):
        d = leg.model_dump()
    elif isinstance(leg, dict):
        d = leg
    else:
        d = {}
    sels = d.get("selections") or []
    primary = sels[0] if sels else {}
    if hasattr(primary, "model_dump"):
        primary = primary.model_dump()
    return {
        "match_id":    d.get("match_id"),
        "market_type": d.get("market_type"),
        "outcome":     primary.get("outcome") if isinstance(primary, dict) else None,
    }


def parlay_recommendation_fingerprint(rec: Any) -> str:
    """Fingerprint one parlay RecommendationResponse-shaped object."""
    if hasattr(rec, "model_dump"):
        d = rec.model_dump()
    elif isinstance(rec, dict):
        d = rec
    else:
        d = {}
    legs = d.get("legs") or []
    return selection_fingerprint(_parlay_leg_to_dict(l) for l in legs)


def single_ticket_fingerprint(t: Any) -> str:
    """Fingerprint one SingleTicketResponse-shaped object. Single ticket
    has match_id + market_type + outcome at the top level — equivalent
    to a 1-leg parlay."""
    if hasattr(t, "model_dump"):
        d = t.model_dump()
    elif isinstance(t, dict):
        d = t
    else:
        d = {}
    return selection_fingerprint([d])


def pool_ticket_fingerprint(t: Any) -> str:
    """Fingerprint one PoolTicketResponse: list of (match_id, market, outcome) legs."""
    if hasattr(t, "model_dump"):
        d = t.model_dump()
    elif isinstance(t, dict):
        d = t
    else:
        d = {}
    legs = d.get("legs") or []
    return selection_fingerprint([
        (l.model_dump() if hasattr(l, "model_dump") else (l if isinstance(l, dict) else {}))
        for l in legs
    ])


def fixtures_odds_digest(fixtures: Iterable[Any]) -> str:
    """Capture the closing-line odds across the requested fixtures.

    When odds drift (any one moves > 5%), the digest changes too — the
    frontend can flag "odds moved" even if the picks are identical.
    Sorted by (date, league, home, away) for determinism.
    """
    rows: list[tuple] = []
    for f in fixtures:
        d = f.model_dump() if hasattr(f, "model_dump") else (f if isinstance(f, dict) else {})
        rows.append((
            str(d.get("date") or ""),
            str(d.get("league") or ""),
            str(d.get("home_team") or ""),
            str(d.get("away_team") or ""),
            float(d.get("psc_home") or d.get("odds_1x2_H") or 0.0),
            float(d.get("psc_draw") or d.get("odds_1x2_D") or 0.0),
            float(d.get("psc_away") or d.get("odds_1x2_A") or 0.0),
        ))
    rows.sort()
    parts = []
    for d, lg, h, a, oh, od, oa in rows:
        # Round to 4 decimals so jitter in float math doesn't flip the hash
        parts.append(f"{d}|{lg}|{h}|{a}|{oh:.4f}|{od:.4f}|{oa:.4f}")
    return _sha1_short("\n".join(parts).encode())


def version_hash(
    *,
    single_fingerprints: Iterable[str] = (),
    parlay_fingerprints: Iterable[str] = (),
    pool_fingerprints: Iterable[str] = (),
    odds_digest: str = "",
) -> str:
    """Top-level "did anything change" hash.

    Combines all per-rec fingerprints + the odds digest into a single
    short hash. Stable: re-ordering recs by EV doesn't matter because
    each component is independently fingerprinted from its pick set.
    """
    payload = "||".join([
        "single:"  + ",".join(sorted(single_fingerprints)),
        "parlay:"  + ",".join(sorted(parlay_fingerprints)),
        "pool:"    + ",".join(sorted(pool_fingerprints)),
        "odds:"    + odds_digest,
    ]).encode()
    return _sha1_short(payload)
