# V8 W1 — `team_canonical` global / cross-league lookup

_First piece of V8's Track B closeout. V7 W6+W8 dropped cup
fixtures + odds onto disk with API-Football team names (e.g.
"Manchester United", "Real Madrid CF"). V8 W2 will UNION those rows
into the V4 training frame, but **the join needs canonical team names
that match the football-data.co.uk pool** ("Man United", "Real
Madrid"). W1 ships the lookup machinery — `to_v4_canonical_global`
(no league hint required) + `CUP_TEAM_ALIASES` catch-all + a
diagnostic CLI to surface unmatched names so the catch-all can be
extended._

## Why a global variant

V5 W3's `to_v4_canonical(name, league, pool, ...)` requires a league
hint because each domestic league has its own `TEAM_ALIASES` dict.
That assumption breaks for cup matches:

- **UCL Real Madrid vs Bayern Munich** — Real Madrid plays in
  La Liga, Bayern in Bundesliga; they share a match in UCL. The
  per-league lookup doesn't have a "UCL" key.
- **FA Cup Manchester City vs lower-division side** — the lower side
  may not be in any V4 pool at all.

W1's `to_v4_canonical_global(name, global_pool)` walks the union of
every league pool + an explicit `CUP_TEAM_ALIASES` catch-all dict +
falls back to the per-league dicts. Returns the first hit.

## What W1 ships

### 1. `nutmeg.utils.team_canonical` extension

```python
from nutmeg.utils.team_canonical import (
    build_global_team_pool,
    to_v4_canonical_global,
    CUP_TEAM_ALIASES,
)

pool = build_global_team_pool({
    "EPL": ["Arsenal", "Man United", ...],
    "ESP_LA_LIGA": ["Real Madrid", "Ath Madrid", ...],
    "GER_BUNDESLIGA": ["Bayern Munich", "Dortmund", ...],
})
result = to_v4_canonical_global("Manchester United", pool)
# CanonicalLookupResult(canonical='Man United', method='alias', confidence=1.0)
```

Lookup precedence:
1. Exact match against the global pool
2. Normalized exact (handles accents — "Atlético Madrid")
3. `CUP_TEAM_ALIASES` (43 hand-curated entries from API-Football
   conventions: "Manchester United", "Real Madrid CF",
   "FC Bayern Munchen", "Paris Saint Germain", etc.)
4. Per-league `TEAM_ALIASES` walk (catches names like "Borussia
   Monchengladbach" → "M'gladbach" without re-listing them in
   `CUP_TEAM_ALIASES`)
5. Fuzzy match via `difflib.SequenceMatcher` (default cutoff 0.86;
   `Man Cty` → `Man City` at ≈ 0.93)

Returns `CanonicalLookupResult(canonical, method, confidence)` — same
shape as V5 W3's `to_v4_canonical`.

### 2. `CUP_TEAM_ALIASES` catch-all (43 entries)

Hand-curated mappings from common API-Football names to V4 canonical:

- English: "Manchester United/Man Utd", "Manchester City", "Tottenham
  Hotspur", "Newcastle United", "Leicester City", "Leeds United",
  "Wolverhampton Wanderers", "Nottingham Forest", "West Ham United",
  "West Bromwich Albion"
- Spanish: "Real Madrid CF", "FC Barcelona", "Atletico Madrid",
  "Atletico de Madrid", "Athletic Club", "Athletic Bilbao"
- Italian: "AC Milan", "Internazionale/Inter Milan", "Juventus FC",
  "SSC Napoli"
- German: "FC Bayern Munchen", "Bayern Munchen", "Borussia Dortmund",
  "RB Leipzig", "Bayer 04 Leverkusen", "Bayer Leverkusen"
- French: "Paris Saint Germain", "PSG", "Olympique de Marseille",
  "Olympique Lyonnais", "AS Monaco"
- Portuguese: "FC Porto", "SL Benfica", "Sporting CP", "SC Braga"
- Dutch: "PSV Eindhoven", "AFC Ajax", "Feyenoord Rotterdam"

This is the starting set. The diagnostic CLI (below) surfaces
additional unmatched names from real cup-history parquets so the user
can extend the dict over time.

### 3. `nutmeg-canonical-report-cup` diagnostic CLI

```bash
# Scan UCL + UEL 4 seasons, report unmatched + fuzzy-only resolutions
nutmeg-canonical-report-cup --leagues UCL,UEL --seasons 2021,2022,2023,2024

# Show all rows (default), or filter
nutmeg-canonical-report-cup --leagues UCL --seasons 2024 --show fuzzy
nutmeg-canonical-report-cup --leagues UCL --seasons 2024 --show unmatched
```

Output:
```
method     external_name                    → canonical                conf
--------------------------------------------------------------------------------
exact      Arsenal                          → Arsenal                  1.00
alias      Manchester United                → Man United               1.00
alias      Real Madrid CF                   → Real Madrid              1.00
alias      FC Bayern Munchen                → Bayern Munich            1.00
unmatched  Brand New Club FC                → —                        0.00
--------------------------------------------------------------------------------
Summary: exact=12 alias=43 fuzzy=2 unmatched=3

→ Add the unmatched entries to CUP_TEAM_ALIASES in
  apps/api/src/nutmeg/utils/team_canonical.py
```

V8 W2 won't run cleanly until every cup team resolves to a non-None
canonical (or is explicitly excluded as out-of-pool). The diagnostic
flow is:

1. Run `nutmeg-ingest-cup-history` + `nutmeg-ingest-cup-odds` to
   populate parquets (V7 W6 + W8 CLIs)
2. Run `nutmeg-canonical-report-cup --show unmatched`
3. For each unmatched name: add the alias to `CUP_TEAM_ALIASES` (or
   to the appropriate per-league dict for permanent home)
4. Re-run step 2 until no unmatched remain
5. V8 W2 then UNIONs cup rows into training cleanly

## What W1 doesn't do

- **No automatic alias addition.** The unmatched names are
  human-reviewed — silent fuzzy matches caused historical bugs
  (V4-era "Real Madrid" vs "Real Sociedad" 0.79 ratio false hit
  was specifically called out in V5 W3 design). W1 keeps the same
  conservative cutoff (0.86) and requires human approval for adds.
- **No `--with-cup-data` train flag.** W1 just ships the lookup.
  V8 W2 wires the lookup INTO the training data loader.
- **No retrain.** W1 is data plumbing. W3 is the retrain.
- **No team_state cross-walk integration.** V6 W11 already shipped
  `lookup_cup_team_pair` (cross-league team_state lookup for the
  recommend path). That's complementary to W1 (which is for the
  INGEST-side team-name canonicalization).

## Tests

`tests/v4/test_team_canonical_global.py` — 24 tests:

| Group | Coverage |
|---|---|
| `TestBuildGlobalTeamPool` (5) | Unions leagues, de-dupes, sorts, empty pool, filters falsy |
| `TestGlobalLookup` (11) | Exact / normalized / CUP_TEAM_ALIASES / per-league walk / fuzzy / unmatched; empty pool / name; alias canonical not in pool falls through |
| `TestCupTeamAliasesShape` (2) | Keys are normalized; known top clubs present |
| `TestReportUnmatched` (1) | Diagnostic shape |
| `TestCanonicalReportCupCLI` (5) | `_gather_cup_team_names`, missing --data → exit 1, missing parquets → exit 1, empty seasons → exit 2, happy path with mocked pool |

Full V4 suite: **622/622 passing** (598 prior + 24 new W1).

## Files touched in W1

```
apps/api/src/nutmeg/utils/team_canonical.py           [M] +to_v4_canonical_global
                                                          +CUP_TEAM_ALIASES (43)
                                                          +build_global_team_pool
                                                          +report_unmatched_global
apps/api/src/nutmeg/v4/cli/canonical_report_cup.py    [+] diagnostic CLI
pyproject.toml                                        [M] +nutmeg-canonical-report-cup
tests/v4/test_team_canonical_global.py                [+] 24 tests
docs/V8_ROADMAP.md                                    [+] V8 plan
docs/v8_w1_team_canonical_global.md                   [+] (this file)
```

## Next: V8 W2 — cup row UNION into `load_all_matches`

W2 will:
1. Extend `nutmeg.v4.data.ingest.load_all_matches` (or wrap it) to
   optionally concat cup_history × cup_odds rows
2. Apply `to_v4_canonical_global` to map cup team names to V4
   canonical names
3. Pad V4 schema cols that cup rows don't carry (e.g. shots, corners,
   yellow/red cards → NaN; form features compute fine with NaN-aware
   builders)
4. Add `--with-cup-data` flag to `nutmeg-train` (different from W7's
   `--with-cup-features` which adds COLUMNS without ROWS)
5. Document the union semantics

Then V8 W3 runs the multi-fold ablation; W4 ships the artifact if the
ablation passes.
