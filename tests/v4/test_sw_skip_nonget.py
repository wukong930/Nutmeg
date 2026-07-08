"""2026-07-08 — the PWA service worker must NOT intercept non-GET requests.

Bug (hit on phone / Tailscale): clicking 应用 in 手填盘口 POSTs
/recommend/market-reprice; the SW intercepted it, re-fetched the POST (fraught
with a body), the fetch failed, and the network-first catch fell to
caches.match — undefined for a POST — so respondWith(undefined) threw
"FetchEvent.respondWith received an error: Returned response is null".

Fix: non-GET requests bypass the SW entirely, and every catch-fallback miss
coerces to Response.error() so respondWith never receives null. These substring
guards keep a future edit from reintroducing the null path.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTES = REPO / "apps/api/src/nutmeg/v4/api/routes.py"


def test_sw_bypasses_non_get() -> None:
    src = ROUTES.read_text(encoding="utf-8")
    assert "if (event.request.method !== 'GET') return;" in src


def test_sw_never_responds_with_null() -> None:
    # every catch → cache-miss path coerces undefined → Response.error().
    src = ROUTES.read_text(encoding="utf-8")
    assert src.count("caches.match(event.request).then((c) => c || Response.error())") == 2
