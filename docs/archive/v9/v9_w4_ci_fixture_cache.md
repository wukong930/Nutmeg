# V9 W4 — CI fixture cache for the lineup pipeline

_V6 W5/W6, V7, V8 retrospectives all flagged the same CI gap: the
`--with-lineups` training path never ran in GH Actions because the
API-Football cache lives at `data/external/api_football/` (gitignored).
The lineup-aware code path had zero end-to-end smoke. V9 W4 fixes
this with a 1.4 MB committed cache subset under `tests/v4/fixtures/
api_football_min/`._

## What W4 ships

### The committed cache

```
tests/v4/fixtures/api_football_min/
  _fixtures/
    1d6db7efb432.json    # 5 EPL 2024 fixtures (slice of full season)
  _fixtures_lineups/
    <12 hash>.json × 5   # one per fixture, 2-team lineup payload
  _injuries/
    <12 hash>.json × 10  # one per (team, season=2024)
```

| Metric | Value |
|---|---|
| Files | 16 |
| Total size | **1.4 MB** |
| Coverage | 5 EPL 24/25 fixtures, 10 unique teams |
| Hash scheme | Identical to production (sha1[:12] of sorted params) |

The cache is **bit-identical to what `nutmeg-ingest-lineups` produces**
in production, just trimmed to 5 fixtures. No mocking, no synthetic
JSON — real API-Football responses.

### Test surface

`tests/v4/test_e2e_lineup_with_cache.py` — 12 tests:

| Group | Coverage |
|---|---|
| `TestCacheLayout` (4) | Cache dir exists, 3 subdirs present, total size < 2 MB, fixtures file has 5 entries |
| `TestBuildLineupLookupFromCache` (3) | Lookup built non-empty, keys match `<league>__<date>__<home>__<away>` V4 format, lineup payload has populated `startXI` |
| `TestBuildRecentInjuryLookup` (2) | V6 W6 validated lookup built non-empty, values are int tuples |
| `TestBuildLineupFeaturesIntegration` (2) | End-to-end: `build_lineup_features` populates all 9 V6 W2 cols + 2 V6 W6 cols; `lineup_available=1` confirms the path worked |
| `TestCacheTraceability` (1) | Hash for (league=39, season=2024) is stable (`1d6db7efb432`) |

**Tests don't skip when cache missing** — they fail visibly with a
clear "re-bake via the one-shot script" pointer. If anyone accidentally
deletes the fixture files, CI catches it.

## What W4 doesn't do

- **No full `nutmeg-train --with-lineups` E2E in CI.** That would
  require a tiny football-data.co.uk historical tree committed too
  (multi-MB). The lineup *pipeline* is now CI-covered; the *training*
  end of the chain remains skipped (existing `test_e2e.py` pattern).
- **No cup-data CI coverage.** V8 W4 documented that cup historical
  odds aren't available; there's nothing to cache. When Path A
  (forward live accumulation, V9 W1) produces ≥ 250 cup matches,
  V9.x or V10 can bake a cup-odds subset too.
- **No multi-season cache.** Only 2024 EPL. La Liga 23/24 was the
  V6 W6 ablation comparator; could add as a second tier but adds
  weight without much marginal coverage for CI smoke purposes.

## How to extend / re-bake the cache

If a fixture or lineup format changes upstream, re-bake the test
cache from the current `data/external/api_football/` cache via this
one-shot script:

```python
from pathlib import Path
import json, shutil
from nutmeg.v4.data.sources import api_football

src = Path("data/external/api_football")
dst = Path("tests/v4/fixtures/api_football_min")
dst.mkdir(parents=True, exist_ok=True)

# 1. Pick 5 finished fixtures from EPL 24/25 with lineup data
fix_src = api_football._cache_path("/fixtures", {"league": 39, "season": 2024}, src)
full = json.loads(fix_src.read_text())
picked = []
for f in full:
    if f.get("fixture", {}).get("status", {}).get("short") != "FT":
        continue
    fid = f["fixture"]["id"]
    lup = api_football._cache_path("/fixtures/lineups", {"fixture": fid}, src)
    if lup.exists():
        picked.append((fid, f, lup))
    if len(picked) >= 5:
        break

# 2. Write the trimmed fixtures file
fix_dst = api_football._cache_path("/fixtures", {"league": 39, "season": 2024}, dst)
fix_dst.parent.mkdir(parents=True, exist_ok=True)
fix_dst.write_text(json.dumps([f for _, f, _ in picked], indent=2, ensure_ascii=False))

# 3. Copy lineup files + team injury files
(dst / "_fixtures_lineups").mkdir(exist_ok=True, parents=True)
(dst / "_injuries").mkdir(exist_ok=True, parents=True)
team_ids = set()
for fid, f, lup in picked:
    shutil.copy(lup, dst / "_fixtures_lineups" / lup.name)
    team_ids.add(f["teams"]["home"]["id"])
    team_ids.add(f["teams"]["away"]["id"])
for tid in team_ids:
    inj = api_football._cache_path("/injuries", {"team": tid, "season": 2024}, src)
    if inj.exists():
        shutil.copy(inj, dst / "_injuries" / inj.name)
```

## Files touched in W4

```
tests/v4/fixtures/api_football_min/_fixtures/<hash>.json       [+] 5-fixture slice
tests/v4/fixtures/api_football_min/_fixtures_lineups/×5        [+] real lineups
tests/v4/fixtures/api_football_min/_injuries/×10               [+] real injuries
tests/v4/test_e2e_lineup_with_cache.py                         [+] 12 tests
docs/v9_w4_ci_fixture_cache.md                                 [+] (this file)
docs/V9_ROADMAP.md                                             [M] W4 ✅
```

Full V4 suite: **771/771 passing** (759 prior + 12 new W4).

## Three-retrospective pay-down

V6 W12 retro: "CI doesn't exercise lineup-aware path."
V7 retrospective: "CI lineup-path fixture cache — V9 should batch this."
V8 retrospective: "CI still doesn't exercise --with-cup-data / --with-lineups."

V9 W4 closes the lineup half. The cup half stays open until cup_odds
forward accumulation produces enough data (V9 W1 Path A, ~9 months).

## Next: V9 W5 — ECE-vs-log-loss audit

The other 3-retrospective backlog item: CatBoost ECE (0.0120) is
slightly BETTER than Pinnacle (0.0123) but log-loss is 0.0056 worse.
Per-bucket Brier decomposition would say whether this gap is fixable
or random.
