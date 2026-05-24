# V7 W3 — `nutmeg-weekly-report` (Track C closeout)

_Bundles the three observation-driven reports (`roi-report`,
`ab-report`, `live-vs-backtest`) into one cron-friendly CLI. With
V7 W1 (odds ingest) + W2 (auto-settle) + W3 (weekly cards), the
user's daily flow is fully automated. The V6 W8 lineup-aware ROI
verdict can now close on data the system collects on its own._

## What W3 ships

### 1. `nutmeg-weekly-report` CLI

```bash
# Basic: ROI + A/B cards into docs/weekly/
nutmeg-weekly-report --db data/v4_observation.db --weeks 4

# Full: also produce live-vs-backtest gap card (alerts via exit code 2)
nutmeg-weekly-report --db data/v4_observation.db --weeks 4 \
    --backtest-cutoff 2024-08-01

# Restrict to one snapshot phase + override output dir
nutmeg-weekly-report --db data/v4_observation.db --weeks 4 \
    --backtest-cutoff 2024-08-01 \
    --snapshot-phase pre_close \
    --out-dir docs/weekly/
```

Outputs (with `--week-tag 2026-W21` as the example):

| Card | Generator | Path |
|---|---|---|
| `2026-W21-roi.md` | `nutmeg-roi-report` (V4) | docs/weekly/ |
| `2026-W21-ab.md` | `nutmeg-ab-report` (V6 W8) | docs/weekly/ |
| `2026-W21-gap.md` | `nutmeg-live-vs-backtest` (V5 W8) | docs/weekly/, only when `--backtest-cutoff` set |

Default tag is ISO week of today's UTC date (`YYYY-Www`), matching the
V5 W10 `weekly-bench.yml` card naming so all weekly artifacts sort
together in `docs/weekly/`.

### 2. Exit-code convention

Single alert hook for both the wrapper and `nutmeg-live-vs-backtest`:

| Exit | Meaning |
|---:|---|
| 0 | All cards written; gap within tolerance (or no gap check) |
| 1 | Input error (DB missing, etc.) — cron should retry / notify |
| 2 | Live ROI diverges from backtest by > tolerance — cron should alert |

The wrapper prints a single summary line even in `--quiet` mode so
cron logs always show the outcome:

```
weekly-report: wrote 3 cards (2026-W21-roi.md, 2026-W21-ab.md, 2026-W21-gap.md); exit=0
```

### 3. Module API

```python
from nutmeg.v4.cli.weekly_report import run_weekly_report, _week_tag

exit_code, paths = run_weekly_report(
    db="data/v4_observation.db",
    out_dir=Path("docs/weekly"),
    weeks=4,
    backtest_cutoff=None,
    backtest_data=None,
    snapshot_phase=None,
    week_tag=None,  # default = ISO week of today
)
# paths is {"roi": Path, "ab": Path, "gap": Path | None}
```

A future dashboard `/api/v4/observation/weekly-report` endpoint can
call this directly without shelling out.

## Recommended local crontab (closes Track C)

Combined with V7 W1's odds ingest + W2's auto-settle, this completes
the daily/weekly automation loop:

```cron
# ~21:00 local — refresh lineup + injury cache for tomorrow's predictions
0 21 * * * cd ~/Nutmeg && \
  PYTHONPATH=apps/api/src .venv/bin/python \
    -m nutmeg.v4.cli.refresh_lineups \
    --leagues EPL,ESP_LA_LIGA --days 3 --include-injuries --quiet \
    >> /tmp/nutmeg-refresh.log 2>&1

# ~03:00 local — auto-settle yesterday's finished matches
0 3 * * * cd ~/Nutmeg && \
  PYTHONPATH=apps/api/src .venv/bin/python \
    -m nutmeg.v4.cli.auto_settle \
    --leagues EPL,ESP_LA_LIGA --db data/v4_observation.db --days 3 --quiet \
    >> /tmp/nutmeg-auto-settle.log 2>&1

# Mondays ~04:00 local — write the three weekly cards
0 4 * * 1 cd ~/Nutmeg && \
  PYTHONPATH=apps/api/src .venv/bin/python \
    -m nutmeg.v4.cli.weekly_report \
    --db data/v4_observation.db --weeks 4 \
    --backtest-cutoff 2024-08-01 \
    --out-dir docs/weekly/ --quiet \
    >> /tmp/nutmeg-weekly.log 2>&1
```

After 4 weeks of this cron running, `nutmeg-ab-report` will have
≥ 30 settlements on each side (lineup-aware vs lineup-free) and the
V6 W8 ROI verdict can finally close.

## What W3 doesn't do

- **No GH Actions integration.** Same reason as W2: observation DB is
  user-local. The existing `weekly-bench.yml` stays as the CI bench-card
  cron (single-season + multi-season + experiment diff on the
  committed historical CSVs).
- **No auto-commit of weekly cards.** The CLI writes to `docs/weekly/`
  but doesn't `git add/commit/push`. The user can wire that in via
  the cron shell line if they want; we kept the CLI single-purpose.
- **No email/slack alert on exit 2.** Exit code propagates so user
  can wrap with their notifier of choice (`|| mail -s "..."`,
  Pushover hook, etc.). Building a notifier into the CLI would lock
  the user to one provider.
- **No multi-DB aggregation.** Single observation DB per invocation.
  For dual-tracking (e.g. one DB per artifact variant) just run the
  wrapper twice with different `--db` + `--out-dir`.

## Tests

`tests/v4/test_weekly_report.py` — 10 tests:

| Group | Coverage |
|---|---|
| `TestWeekTag` (4) | Default uses today; known dates (2025-08-17 → W33, 2026-01-01 → W01, 2024-12-31 → 2025-W01 ISO rollover) |
| `TestMainHappyPath` (3) | DB missing → exit 1, no-cutoff skips gap card, card content includes expected Chinese / lineup-* markers |
| `TestRunWeeklyReport` (2) | Returns paths dict; creates out_dir when missing |
| `TestExitCodePropagation` (1) | Empty / invalid DB doesn't crash the wrapper; exit code propagates |

Full V4 suite: **530/530 passing** (520 prior + 10 new W3).

## Files touched in W3

```
apps/api/src/nutmeg/v4/cli/weekly_report.py   [+] nutmeg-weekly-report CLI
pyproject.toml                                [M] +nutmeg-weekly-report entry
tests/v4/test_weekly_report.py                [+] 10 tests
docs/V7_ROADMAP.md                            [M] W3 ✅, Track C ✅
docs/v7_w3_weekly_report.md                   [+] (this file)
```

## Track C is closed

| Week | Deliverable | Status |
|---|---|---|
| V7 W1 | `nutmeg-ingest-odds` + `nutmeg-rec --auto-fetch` | ✅ |
| V7 W2 | `nutmeg-auto-settle` | ✅ |
| **V7 W3** | **`nutmeg-weekly-report` bundling** | **✅** |

User daily flow before V7: 5 manual steps. After Track C: **2 steps**
(read recommendations, place bets in lottery terminal). Everything
else — odds ingest, settlement, weekly cards — runs from local cron.

## Next: V7 W4 — accumulate data, V7 W5 — close the lineup verdict

Track A (lineup ROI decision) is gated on data. With Track C complete
the cron does the work for us. 4 weeks of nightly runs → ≥ 30 settled
recs per slice → run `nutmeg-ab-report --weeks 4` (already part of
the W3 weekly bundle) and read the verdict.

The verdict text the wrapper auto-emits, per V6 W8 spec:
- aware leads by ≥ 5pp ROI → **promote to default**
- diff within ±2pp → **keep V5 W12 default**; document why backtest
  didn't translate
- free leads by ≥ 5pp → **investigate** cache freshness / overfit
- either side n < 30 → **wait another week**
