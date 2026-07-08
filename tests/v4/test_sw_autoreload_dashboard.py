"""2026-07-08 — the page auto-reloads when a newer service worker takes control.

Follow-up to the non-GET SW bypass (test_sw_skip_nonget). Even with that bypass,
iOS WebKit can throw "Load failed" on the FIRST POST fired against a page whose
controlling SW just updated — the old controller lingers for the page's lifetime,
so the request rides a half-swapped pipe. Fix: listen for `controllerchange` and
reload once, so the freshest page+SW are always paired (手填盘口「应用」then works
without a manual close+reopen of the PWA).

Guards asserted so a refactor can't silently drop them:
  - `_swHadController` skips the first-ever install (fresh install ≠ update → no
    reload, no spurious first-visit flash)
  - `_swReloading` one-shot flag prevents a reload loop
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DASH = REPO / "apps/api/src/nutmeg/v4/api/static/dashboard.html"


def test_controllerchange_listener_present() -> None:
    src = DASH.read_text(encoding="utf-8")
    assert "navigator.serviceWorker.addEventListener('controllerchange'" in src


def test_reload_guards_present() -> None:
    src = DASH.read_text(encoding="utf-8")
    # skip first-ever install; one-shot flag against reload loops; then reload.
    assert "const _swHadController = !!navigator.serviceWorker.controller;" in src
    assert "if (_swReloading || !_swHadController) return;" in src
    assert "window.location.reload();" in src
