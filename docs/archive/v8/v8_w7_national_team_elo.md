# V8 W7 — National-team Elo via clubelo

_Track D's second piece. V6 W11 registered 4 national-team
competitions (WC, EURO, COPA_AMERICA, WC_QUAL_UEFA) but the model
had zero per-team signal for them — WC fixtures fell back to V4's
"unknown team" path (zero form + 1500 default Elo). W7 ships the
clubelo per-nation Elo ingest + lookup helpers so WC / Euro / Copa
America rows can carry a real per-nation Elo prior. **Pure data
layer + CLI; model integration is a follow-up.**_

## What W7 ships

### 1. `nutmeg.v4.data.national_team_elo` module

Mirror of the existing per-club `clubelo.py`:

```python
from nutmeg.v4.data.national_team_elo import (
    NATION_CLUBELO_CODES,           # registry of 68 nation codes
    fetch_nation_history,           # CSV → DataFrame
    build_nation_elo_lookup,        # cache_dir → dict[code, elo]
    lookup_nation_elo,              # state + team name → (code, elo)
)
```

### 2. `NATION_CLUBELO_CODES` registry (68 nations)

Curated from clubelo's per-country catalog. Covers:

- **UEFA (36)**: ENG, FRA, ESP, GER, ITA, NED, POR, BEL, CRO, SUI,
  AUT, POL, DEN, SWE, TUR, RUS, UKR, CZE, ROU, SCO, WAL, IRL, NIR,
  SRB, GRE, NOR, HUN, SVK, SVN, ALB, BIH, BUL, ISL, FIN, GEO, MKD
- **CONMEBOL (10)**: BRA, ARG, URU, COL, CHI, PER, ECU, PAR, BOL, VEN
- **CONCACAF (6)**: USA, MEX, CAN, CRC, JAM, HON
- **AFC (7)**: JPN, KOR, AUS, IRN, SAU, QAT, CHN
- **CAF (9)**: MAR, SEN, EGY, TUN, ALG, NGA, CMR, GHA, CIV

Each code has a list of common English / API-Football name variants
(e.g. `"USA": ["USA", "United States"]`, `"KOR": ["Korea Republic",
"South Korea"]`, `"CIV": ["Ivory Coast", "Côte d'Ivoire"]`). The
reverse `_NAME_TO_CODE` dict is built at import time so name lookups
are O(1).

### 3. `fetch_nation_history(code, *, client)` — CSV parser

```python
import httpx
from nutmeg.v4.data.national_team_elo import fetch_nation_history

with httpx.Client(timeout=20.0) as c:
    df = fetch_nation_history("ENG", client=c)
# Columns: code, from_date, to_date, elo
```

- Wraps `http://api.clubelo.com/<NationCode>` with `tenacity` retry
  (3 attempts, exponential backoff) — same pattern as the per-club fetcher
- 404 → empty schema-only DataFrame (clubelo returns 404 for nations
  it doesn't track yet)
- Empty body → empty frame (caller distinguishes via `len(df) == 0`)
- Invalid `From`/`To` dates → row dropped

### 4. Parquet roundtrip

```python
from nutmeg.v4.data.national_team_elo import (
    nation_cache_path, write_nation_parquet, load_nation_parquet,
)

path = nation_cache_path(Path("data/external/clubelo_national"), "ENG")
write_nation_parquet(df, path)              # → ENG.parquet
loaded = load_nation_parquet(path)
```

Per-nation parquet shape mirrors V6 W6 cup_history / V7 W8 cup_odds:
one file per (code), schema-only empty file when no data.

### 5. `build_nation_elo_lookup(cache_dir, *, as_of, codes)`

```python
state = build_nation_elo_lookup(
    Path("data/external/clubelo_national"),
    as_of=pd.Timestamp("2024-06-15"),
)
# state = {"ENG": 1903.4, "FRA": 1985.2, "BRA": 1932.8, ...}
```

- Walks every `.parquet` in `cache_dir` (or filter to `codes`)
- For each nation: picks the row where `from_date <= as_of < to_date`
  (clubelo's intervals don't overlap)
- Falls back to most-recent row when no active interval (stale cache /
  nation hasn't played recently)

### 6. `lookup_nation_elo(state, name)` — name → (code, elo)

```python
code, elo = lookup_nation_elo(state, "England")
# ("ENG", 1903.4)

code, elo = lookup_nation_elo(state, "United States")
# ("USA", 1751.0)

code, elo = lookup_nation_elo(state, "Mystery Republic")
# (None, None)
```

Precedence:
1. Exact 3-letter code match (case-insensitive)
2. Normalized-name alias via `_NAME_TO_CODE`
3. None

### 7. `nutmeg-ingest-national-elo` CLI

```bash
# All 68 registered nations (~17 seconds with 250ms throttle)
nutmeg-ingest-national-elo

# Just WC 2026 likely participants
nutmeg-ingest-national-elo --countries ENG,FRA,ESP,GER,ITA,BRA,ARG,USA,MEX

# Force re-fetch (override cache)
nutmeg-ingest-national-elo --countries ENG --refresh
```

Pipeline per nation:
1. Skip if parquet already exists (unless `--refresh`)
2. `fetch_nation_history(code)` with shared httpx client
3. Empty data → still write empty parquet (so downstream loaders
   distinguish "tried, no data" from "never tried")
4. Throttle 250ms between requests (clubelo is a free public service)

Exit codes:
- 0 — all fetches OK
- 1 — at least one fetch failed (ConnectError / 5xx / etc.)
- 2 — argparse error (no countries to fetch)

Budget: 68 HTTP calls for the full registry. clubelo doesn't enforce
a per-IP throttle but the politeness sleep is included anyway.

## What W7 doesn't do

- **No model integration.** The W7 lookup helpers are ready, but
  `build_elo_features` / `build_form_features` don't yet check the
  `nation_state` for national-team-cup rows. The integration is:
  ```python
  if competition_type_of(row.league) == "national_team_cup":
      code, elo = lookup_nation_elo(nation_state, row.home_team)
      if elo is not None:
          # use clubelo nation Elo as the seed
  ```
  This belongs in a follow-up commit alongside `cross_league_seed`'s
  next extension (V8 W4 or V9 W1 if we batch).
- **No fixture data with national teams in the training set.** Today's
  training data (`football_data_co_uk`) is league-only. WC / Euro
  fixtures would need to be ingested separately via `nutmeg-ingest-
  cup-history` + `nutmeg-ingest-cup-odds` for WC / EURO / COPA_AMERICA
  (which work via V6 W11 IDs).
- **No fuzzy match.** The lookup uses exact alias matching only.
  clubelo's nation codes are stable; misspellings should be added
  to the registry rather than silently fuzzy-matched (V4-era
  team_canonical lessons).
- **No GH Actions ingest cron.** Nation Elo updates monthly at
  most; a one-off backfill + occasional refresh is plenty. No
  daily cron need.

## Tests

`tests/v4/test_national_team_elo.py` — 31 tests:

| Group | Coverage |
|---|---|
| `TestRegistry` (4) | Known top nations present; codes are 3-letter uppercase; ≥1 alias each; reverse map built |
| `TestFetchNationHistory` (5) | CSV → DataFrame; empty body; 404 returns empty; code uppercased; invalid dates dropped |
| `TestParquetRoundtrip` (3) | Write+load; missing path empty; canonical filename uppercase |
| `TestBuildLookup` (6) | Picks active row; falls back to latest when stale; walks all parquets; subset filter; empty dir; default as_of |
| `TestLookupNationElo` (7) | Exact code; case-insensitive; full name via alias; alternate name (USA → "United States"); alias present but state missing; unknown name; empty name |
| `TestIngestCLI` (6) | Unknown code warns + continues; happy path two countries; cache skipped without --refresh; --refresh overrides; default uses full registry; fetch error → exit 1 |

Full V4 suite: **713/713 passing** (682 prior + 31 new W7).

## Files touched in W7

```
apps/api/src/nutmeg/v4/data/national_team_elo.py       [+] data layer module
apps/api/src/nutmeg/v4/cli/ingest_national_elo.py      [+] nutmeg-ingest-national-elo
pyproject.toml                                         [M] +CLI entry
tests/v4/test_national_team_elo.py                     [+] 31 tests
docs/V8_ROADMAP.md                                     [M] W7 ✅
docs/v8_w7_national_team_elo.md                        [+] (this file)
```

## Run-it-yourself

```bash
# 1. Backfill all 68 nations (~17s)
nutmeg-ingest-national-elo
# → 68 parquets in data/external/clubelo_national/

# 2. Programmatic lookup
PYTHONPATH=apps/api/src python -c "
from pathlib import Path
import pandas as pd
from nutmeg.v4.data.national_team_elo import build_nation_elo_lookup, lookup_nation_elo

state = build_nation_elo_lookup(
    Path('data/external/clubelo_national'),
    as_of=pd.Timestamp('2024-12-01'),
)
print('top 5 nations:')
for code, elo in sorted(state.items(), key=lambda kv: -kv[1])[:5]:
    print(f'  {code}: {elo:.0f}')

# Resolve common API-Football names
for name in ['Argentina', 'United States', 'Korea Republic', 'Côte d\\'Ivoire']:
    code, elo = lookup_nation_elo(state, name)
    print(f'  {name!r:25}→ {code}, {elo}')
"
```

## Next: V8 W8 — V8 ship

V8's coding work is largely done. W8 is the documentation closeout:
- `V8_HANDOFF.md` (single source of truth)
- `v8_retrospective.md` (what worked / what didn't / V9 starting points)
- `v8.0-shipped` tag

After W8, V8 is shipped. Track A (lineup verdict) + V8 W4 (cup-aware
artifact decision) remain data-gated — both will land in V9 W1 once
the user has accumulated the required data.
