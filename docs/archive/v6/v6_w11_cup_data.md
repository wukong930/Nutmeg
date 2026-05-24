# V6 W11 — Cup data + national teams

_Adds the structural support for UCL / UEL / UECL / FA Cup / DFB-Pokal /
Copa del Rey / Coppa Italia / Coupe de France / World Cup / Euro /
Copa America / WC qualifiers without retraining the model. Side-channel
feature columns + cross-league team_state lookup let cup matches enter
the recommend pipeline today using V5 W12 / V6 W7 artifacts; backfilling
cup-trained models is V7 territory._

## Why side-channel, not retrain

The V5 / V6 model was trained on 13 domestic league competitions
(`EPL ... J1`). Cup tournaments add four structural complications:

1. **Cross-league pairings** — UCL Real Madrid (ESP_LA_LIGA) vs Bayern
   (GER_BUNDESLIGA). The `team_state` dict is keyed by `(league, team)`,
   so without intervention `team_state["UCL"]["Real Madrid"]` is empty.
2. **Knockout structure** — single-elimination rounds change risk/reward
   compared to round-robin league play.
3. **Two-legged ties** — UCL R16/QF/SF are home + away aggregate; first-leg
   tactics differ from second-leg, and aggregate context matters.
4. **National-team product** — World Cup / Euro use national squads whose
   recent-match sample is tiny (10-15 matches/year vs 38+ for a league).

A naive "retrain on cup data" would suffer high variance from the small
cup sample. Instead W11 keeps the league-trained model as the dominant
signal and exposes cup-ness as **side-channel features** the GBM can
learn a downweight on once we eventually retrain with mixed data.
Until then, predictions for cup matches use the league-derived team
state via cross-league lookup — biased toward "ignore the cup context"
but at least functional.

## What W11 ships

### 1. Competition registry — `nutmeg.v4.data.competitions`

| Code | Type | API-Football ID | Two-legged | Notes |
|---|---|---:|---|---|
| `UCL` | club_cup | 2 | ✓ | UEFA Champions League |
| `UEL` | club_cup | 3 | ✓ | UEFA Europa League |
| `UECL` | club_cup | 848 | ✓ | UEFA Conference League |
| `FAC` | club_cup | 45 | — | FA Cup (single-leg + replays) |
| `COPA_DEL_REY` | club_cup | 143 | — | |
| `COPPA_ITALIA` | club_cup | 137 | ✓ | |
| `DFB_POKAL` | club_cup | 81 | — | |
| `COUPE_DE_FRANCE` | club_cup | 66 | — | |
| `WC` | national_team_cup | 1 | — | FIFA World Cup |
| `EURO` | national_team_cup | 4 | — | UEFA European Championship |
| `COPA_AMERICA` | national_team_cup | 9 | — | |
| `WC_QUAL_UEFA` | national_team_cup | 32 | — | Group round-robin |

Helpers:
- `is_cup_competition(code)` — True for any of the above
- `is_national_team_competition(code)` — World Cup / Euro / Copa / WC qualifiers
- `is_club_cup_competition(code)` — UCL / UEL / domestic cups
- `competition_type_of(code)` — Literal["league", "club_cup", "national_team_cup"]
- `competition_type_id(code)` — 0/1/2 numeric encoding (GBM categorical)
- `has_two_legged_format(code)` — competition structural flag
- `is_knockout_round(round_label)` — heuristic on API-Football round strings ("Round of 16", "Quarter-finals", "Final" → True)
- `display_zh(code)` — Chinese display label for dashboards

### 2. API-Football integration

`API_FOOTBALL_LEAGUE_IDS` now merges domestic league IDs + cup IDs from
the registry. `league_id("UCL")` → 2; `league_id("WC")` → 1.

This means **the existing V6 W8 daily-refresh CLI works for cups
without code changes**:

```bash
nutmeg-refresh-lineups --leagues EPL,UCL,FAC --days 7 --include-injuries
```

Will pull EPL fixtures + UCL fixtures + FA Cup fixtures into the same
cache directory.

### 3. Cup features — `nutmeg.v4.features.cup_features`

Five new side-channel columns:

| Column | Type | Domestic league row | Cup match (e.g. UCL R16) | WC Final row |
|---|---|---:|---:|---:|
| `is_cup_match` | 0/1 | 0 | 1 | 1 |
| `is_knockout` | 0/1 | 0 | 1 | 1 |
| `is_two_legged` | 0/1 | 0 | 1 | 0 |
| `is_national_team_match` | 0/1 | 0 | 0 | 1 |
| `competition_type_id` | 0/1/2 | 0 | 1 | 2 |

`build_cup_features(df)` appends all 5 to a fixture DataFrame. The
existing training data has all rows with `league` ∈ domestic codes, so
every column emits 0 → existing artifact's predictions unchanged.
**No retraining needed for W11.** Wiring the columns into
`feature_columns_with_cup()` is deferred to V7 (alongside
cup-data training-set construction).

### 4. Cross-league team_state lookup

`find_team_state_cross_league(team_state, team_name, preferred_league=None)`
walks every league in `team_state` to find a team. Falls back to the
preferred-league hint first when supplied.

`lookup_cup_team_pair(team_state, league_code, home, away)` is the
production helper: for league fixtures it stays strict (no
cross-search); for cup fixtures it walks all leagues:

```python
# Domestic
h, a = lookup_cup_team_pair(state, "ESP_LA_LIGA", "Real Madrid", "Getafe")
# Both come from state["ESP_LA_LIGA"]

# Cross-league cup
h, a = lookup_cup_team_pair(state, "UCL", "Real Madrid", "Bayern Munich")
# h ← state["ESP_LA_LIGA"]["Real Madrid"]
# a ← state["GER_BUNDESLIGA"]["Bayern Munich"]
```

When a cup team isn't in any league's state (lower-division team in FA
Cup, qualifier-round nations) the lookup returns `None`. Callers should
gracefully default to "no team-specific signal" — same path V4 already
uses for unseen teams.

## What W11 doesn't do

- **No cup-trained model.** Wiring `is_cup_match` etc into
  `feature_columns_with_cup()` and retraining is V7. The W11 artifact
  delta is zero rows — existing tests pass unchanged (468 / 468).
- **No live national-team Elo.** clubelo's national-team endpoint
  (`http://api.clubelo.com/<NationCode>`) exists; ingesting it into a
  separate `national_team_state` dict is a future deliverable. For
  national-team-cup predictions today, the model effectively returns
  unconditional λ defaults.
- **No two-legged aggregate context.** The structural `is_two_legged`
  flag fires for any UCL leg, but the model can't tell first-leg from
  second-leg or condition on aggregate goal differential. Adding leg
  index + aggregate features requires a UCL-specific fixture join V7
  will tackle.
- **No cup-specific dashboard surfaces.** The dashboard's recommend
  textarea takes any league code in the JSON payload, including the new
  cup codes. The model handles them via the same code path as league
  matches (with cross-league team lookup falling back gracefully).

## Tests

`tests/v4/test_cup_features.py` — 40 tests:

| Group | Coverage |
|---|---|
| `TestCompetitionRegistry` (7) | Known cup codes, dataclass shape, is_cup/national/club partitioning, fall-through to "league", type_id encoding, has_two_legged_format |
| `TestKnockoutRoundDetection` (13 via parametrize) | English / "round of 16" / hyphenation variants → True; group-stage / NaN → False |
| `TestApiFootballCupIds` (4) | Cup IDs merged into API_FOOTBALL_LEAGUE_IDS, league_id("UCL")=2, etc. Domestic leagues unchanged |
| `TestDeriveCupFeaturesSingle` (5) | League row all-zero, UCL group, UCL R16, WC Final, no-round-label case |
| `TestBuildCupFeaturesDataFrame` (3) | All 5 columns appended, no-round-column graceful path, original df untouched |
| `TestCrossLeagueTeamLookup` (6) | Preferred-league hint, fall-back walking, None when missing, cup pair resolution, league strict-keying |
| `TestDisplayZh` (2) | Chinese label for known cups, fall-back to code for unknown |

Full V4 suite: **468/468 passing** (428 prior + 40 new W11).

## Files touched in W11

```
apps/api/src/nutmeg/v4/data/competitions.py       [+] registry + helpers
apps/api/src/nutmeg/v4/data/sources/api_football.py [M] merge cup IDs into API_FOOTBALL_LEAGUE_IDS
apps/api/src/nutmeg/v4/features/cup_features.py   [+] 5 feature cols + cross-league lookup
tests/v4/test_cup_features.py                     [+] 40 tests
docs/V6_ROADMAP.md                                [M] W11 ✅
docs/v6_w11_cup_data.md                           [+] (this file)
```

## Next: V6 W12 — ship

`V6_HANDOFF.md`, retrospective, `v6.0-shipped` tag. The remaining
deliverable is documentation + closeout — no new feature code.
