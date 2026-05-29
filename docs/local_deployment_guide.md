# Local Deployment Guide

_post-v9 P1#16 (initial); V10 W2/W4 extended to 7 jobs covering Layer A
auto-T calibration + WC 2026 predict/settle. macOS-specific (uses
launchd)._

## Why local instead of GH Actions?

The V9 W1 daily-recommend.yml workflow was failing every day since
ship because `NUTMEG_API_FOOTBALL_KEY` was never added as a repo
secret. Even if fixed, GH Actions:

- Only **fetches** data (doesn't generate recommendations or record sessions)
- Uploads CSV/JSON as **14-day artifacts** (need manual download to persist)
- No path to persist the SQLite observation DB long-term

Local launchd jobs:
- Run on your own Mac (always with the .env key)
- Write directly to `data/external/cup_odds/` + `data/v4_observation.db`
- Survive reboots (launchd handles missed runs)
- GUI-inspectable via Console.app
- Per-job log files in `logs/launchd/`

## What gets installed (7 jobs)

| # | Job | When | What it does |
|---|---|---|---|
| 1 | `com.nutmeg.daily_odds` | 14:00 daily | Fetch today's odds for 5 domestic leagues (post-P1#20: UCL/UEL removed since cup ablation closed negative) |
| 2 | `com.nutmeg.daily_recommend` | 15:00 daily | Generate EPL + La Liga recommendations, record session into observation DB |
| 3 | `com.nutmeg.daily_settle` | 02:00 daily | Settle finished-match outcomes + refresh `docs/local_ab_report_latest.md` (was Sunday-only `weekly_settle`; daily since 2026-05-29) |
| 4 | `com.nutmeg.weekly_gate` | Sunday 04:00 | Run P1#19 live-vs-backtest gate (cross-source-aware, `--tolerance-pp 50` per P1#22 noise floor); write report to `docs/weekly/p1_19_gate_<ISO-week>.md` |
| 5 | `com.nutmeg.weekly_calibration_check` | Monday 03:00 | **V10 W2** Layer A drift check + auto-rollback. Runs `nutmeg-auto-calibration --apply --auto-rollback --deploy-artifact data/v4_model`. If a deployed correction is hurting log-loss → revert; otherwise propose a fresh T. Writes `docs/weekly/auto_calibration_<ISO-week>.md`. |
| 6 | `com.nutmeg.daily_wc_predict` | 09:00 daily | **V10 W4** WC predictions for today, pulls Pinnacle odds when available, upserts into `wc_predictions` table. Writes `docs/wc/wc_<YYYY-MM-DD>.json`. |
| 7 | `com.nutmeg.daily_wc_settle` | 02:00 daily | **V10 W4** Pulls finished WC fixtures from API-Football, fills outcome columns in `wc_predictions`, then writes a fresh tournament-wide report to `docs/wc/wc_report_<YYYY-MM-DD>.md`. |

All read `NUTMEG_API_FOOTBALL_KEY` from `.env` at run time
(no plaintext key in plist files). Job 6 also uses `NUTMEG_ODDS_API_KEY`
if `--fetch-current-odds` is on (silently skipped when not set).

### Daily schedule (post-installation)

```
02:00  daily_settle         (settle finished outcomes + ROI report — daily)
       daily_wc_settle      (V10 W4 — pull WC outcomes + write report)
03:00  weekly_calibration_check  (Monday only — Layer A T drift check)
04:00  weekly_gate          (Sunday only — P1#19 live-vs-backtest)
09:00  daily_wc_predict     (V10 W4 — predict today's WC matches)
14:00  daily_odds           (fetch domestic odds)
15:00  daily_recommend      (generate domestic recs + record session)
```

The order matters: WC settle runs at 02:00 so Monday's 03:00 Layer A
check sees freshly-settled outcomes.

## One-time setup (5 minutes)

```bash
# 1. Verify .env is correct
cat .env | grep NUTMEG_API_FOOTBALL_KEY    # should show your 32-char key

# 2. Verify the venv is set up
.venv/bin/python --version                  # should be 3.12+

# 3. Install the launchd jobs
./scripts/setup_local_pipeline.sh

# 4. Verify everything is healthy
./scripts/health_check.sh
```

Expected `health_check.sh` output right after setup (before any
cron has fired):

```
━━ 1. API key (.env) ━━
  ✓ .env present and NUTMEG_API_FOOTBALL_KEY looks valid (len=32)

━━ 2. launchd jobs ━━
  ✓ com.nutmeg.daily_odds loaded (last exit=0, pid=-)
  ✓ com.nutmeg.daily_recommend loaded (last exit=0, pid=-)
  ✓ com.nutmeg.daily_settle loaded (last exit=0, pid=-)
  ✓ com.nutmeg.weekly_gate loaded (last exit=0, pid=-)
  ✓ com.nutmeg.weekly_calibration_check loaded (last exit=0, pid=-)
  ✓ com.nutmeg.daily_wc_predict loaded (last exit=0, pid=-)
  ✓ com.nutmeg.daily_wc_settle loaded (last exit=0, pid=-)

━━ 3. Cup odds accumulation (Path A — V10 trigger #1) ━━
  • 8 parquet files in data/external/cup_odds/
  ⚠ 0 rows total — Path A has accumulated nothing yet
  • needs ≥250 rows to retry cup ablation (V10 trigger). Today: 0

━━ 4. Observation DB (Lineup ROI — V10 trigger #2) ━━
  ✗ data/v4_observation.db not found — no Lineup ROI accumulation has happened yet
```

The "✗" failures are EXPECTED before the cron has fired. They'll
become "✓" over time:
- Cup odds row count grows by ~5-15 per day (UCL/UEL match days)
- Observation DB appears tomorrow after the 15:00 `daily_recommend` runs

### Pre-WC kickoff verification (V10 W4)

Before 2026-06-11, run the WC-specific preflight check:

```bash
./scripts/wc_preflight.sh
```

This is a separate 7-check script that validates:

1. `.env` has both `NUTMEG_API_FOOTBALL_KEY` and `NUTMEG_ODDS_API_KEY`
2. WC 2026 fixture cache has ≥64 entries
3. National-team Elo snapshot < 14 days old
4. `nutmeg-wc-predict --date 2026-06-11` succeeds
5. `/api/v4/predictions/wc` endpoint returns ≥1 prediction
6. WC + Layer A launchd jobs loaded
7. Observation DB has the `wc_predictions` table (or will create one on first run)

Exit codes: 0 = ready, 1 = blockers, 2 = warnings only.

## Daily / weekly usage

### See current status anytime
```bash
./scripts/health_check.sh
```

### Run the dashboard for browsing recommendations
```bash
./scripts/run_local_server.sh
# Then open http://127.0.0.1:8000/api/v4/dashboard
```

### Run dashboard accessible from your phone (same WiFi)
```bash
./scripts/run_local_server.sh 8000 lan
# Script prints "http://<your-lan-ip>:8000/api/v4/dashboard"
# Open that URL on your phone
```

### Manually trigger a job (don't wait for the scheduled time)
```bash
launchctl kickstart -k gui/$UID/com.nutmeg.daily_recommend
# Wait ~30 seconds, check the log:
tail -f logs/launchd/com.nutmeg.daily_recommend.out.log
```

### Inspect a failed run
```bash
# Look at stderr
tail -50 logs/launchd/com.nutmeg.daily_odds.err.log

# Or check launchctl state
launchctl list | grep com.nutmeg
# Format: PID  LAST_EXIT_CODE  LABEL
# - PID '-' means not currently running
# - LAST_EXIT_CODE: 0 = healthy, non-zero = failed (check err log)
```

## V10 ship trigger conditions (historical)

Both triggers below were tracked via `health_check.sh` during V10
development. V10 has now shipped (all 4 weeks tagged 2026-05-25);
the triggers still apply as ongoing operational thresholds.

| Trigger | Current threshold | When |
|---|---|---|
| Path A cup ablation retry | ≥ 250 rows in cup_odds parquets | ~6-9 months of daily cron (UCL/UEL match days only contribute) |
| Lineup ROI 4-week verdict | ≥ 60 settlements (≥30 per arm) in observation DB | ~4-6 weeks if daily_recommend runs every day |

Run `./scripts/health_check.sh` weekly; the script prints current
progress + threshold for each.

When the lineup ROI verdict is ready:
```bash
PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.ab_report \
  --weeks 4 --db data/v4_observation.db
```

(The daily_settle job also writes `docs/local_ab_report_latest.md`
automatically every day at 02:00 — just open that file.)

## Operating Layer A (V10 W2 — post-hoc T calibration)

Layer A is a post-hoc temperature scalar applied to the model's 1X2
probabilities at serving time. It's an OPT-IN production lever:
serving uses identity (T=1.0) until you explicitly deploy a
correction. The weekly cron only PROPOSES; you decide whether to ship.

### Reading the Monday morning report

After `weekly_calibration_check` fires (Mon 03:00), open
`docs/weekly/auto_calibration_<YYYY-WNN>.md`. Three possible
verdicts:

1. **🛑 HOLD** — not enough data, OR ship gate didn't pass. Do nothing.
2. **✅ SHIP** — ship gate passed; T_new recommended. Decide whether to deploy.
3. **🔄 AUTO-ROLLBACK** — a previously-deployed correction is now
   hurting log-loss. The cron already deleted the artifact file
   (`live_T_correction.json`); no action needed; next request serves
   T=1.0 again.

### Deploying a SHIP recommendation

```bash
# Re-run the same propose with --action=deploy to actually ship
nutmeg-auto-calibration \
  --db data/v4_observation.db \
  --apply \
  --action deploy \
  --deploy-artifact data/v4_model

# Verify the artifact file landed
cat data/v4_model/live_T_correction.json
```

The serving layer (`/api/v4/recommend*`, `/api/v4/predictions/upcoming`,
etc.) reads the correction file on each request via mtime cache — no
server restart needed.

### Manual rollback

```bash
nutmeg-auto-calibration \
  --db data/v4_observation.db \
  --apply \
  --action rollback \
  --deploy-artifact data/v4_model
```

Removes the correction file + writes a `rollback` journal entry.
Auto-rollback (in the weekly cron) is preferred — manual rollback is
for cases where you spot a problem before Monday.

## Operating WC 2026 (V10 W4 — daily predict + settle)

### Reading daily WC reports

Every morning during the tournament window (2026-06-11 → 2026-07-19),
the system writes:

- `docs/wc/wc_<YYYY-MM-DD>.json` — predictions for today's WC matches
  (from the 09:00 cron)
- `docs/wc/wc_report_<YYYY-MM-DD>.md` — tournament-wide hit-rate +
  log-loss + calibration buckets (from the 02:00 settle cron)

Open the most recent report file to see live model performance.

### Force-running a WC predict

```bash
launchctl kickstart -k gui/$UID/com.nutmeg.daily_wc_predict
tail -f logs/launchd/com.nutmeg.daily_wc_predict.out.log
```

### Force-running a WC settle (catch up)

```bash
launchctl kickstart -k gui/$UID/com.nutmeg.daily_wc_settle
```

The settle CLI is idempotent on `fixture_id` — re-running a date
that's already settled is a no-op. Catch-up over multi-day gaps:
the same cron command pulls the full season's fixtures every run.

## Uninstall

```bash
./scripts/teardown_local_pipeline.sh
```

Removes all 7 launchd jobs + their plists. Logs in `logs/launchd/`
are preserved for forensics; delete manually if you don't need them.

## What about my laptop being off?

launchd handles this via `RunAtLoad` semantics — if your Mac is off
at 14:00 but you boot it up at 15:30, the missed 14:00 run fires
when launchd next gets a chance (within a few minutes of login).

If you're away for >24 hours, you'll miss some days. The cron has
no concept of "catch up the missed days" — it just resumes the
schedule from the next valid window.

For a truly always-on solution (NAS, VPS, Raspberry Pi etc.):
- Copy the same shell scripts (they're cross-Unix)
- Replace launchd with systemd (Linux) or just plain cron
- Same observation DB schema works anywhere SQLite does

## Troubleshooting

### "launchctl: command not found"
Not on macOS. This script requires macOS (launchd is Apple-specific).
On Linux, use systemd or plain crontab; the underlying Python CLIs
work the same.

### Daily recommend logs say "Insufficient fixtures"
Normal on days with no matches in EPL/La Liga (mid-week, off-season).
The cron still fires; it just produces 0 recommendations that day.

### `data/v4_observation.db` not created
- Check `logs/launchd/com.nutmeg.daily_recommend.err.log` for errors
- Try a manual trigger: `launchctl kickstart -k gui/$UID/com.nutmeg.daily_recommend`
- Verify the venv is set up correctly: `.venv/bin/python -c "import nutmeg.v4.cli.recommend"`

### API rate limit hit (HTTP 429)
- API-Football free tier: 100 requests/day
- The daily job does ~15-20 requests; well under
- If hit, check `/api/v4/health` or `nutmeg-api` `/health` endpoint
  for current rate-limit state
- Monthly token-check (GH Actions) also shows current consumption

## Files

```
scripts/
  setup_local_pipeline.sh        # install 7 launchd jobs
  teardown_local_pipeline.sh     # uninstall (preserves logs)
  health_check.sh                # single-command status (all 7 jobs)
  run_local_server.sh            # launch FastAPI uvicorn
  wc_preflight.sh                # V10 W4 — pre-WC kickoff verification

docs/
  local_deployment_guide.md      # this file
  local_ab_report_latest.md      # written by daily_settle each day 02:00
  weekly/p1_19_gate_<YYYY-Www>.md       # written by weekly_gate each Sun 04:00
  weekly/auto_calibration_<YYYY-Www>.md # V10 W2 — written by weekly_calibration_check each Mon 03:00
  wc/wc_<YYYY-MM-DD>.json               # V10 W4 — written by daily_wc_predict each 09:00
  wc/wc_report_<YYYY-MM-DD>.md          # V10 W4 — written by daily_wc_settle each 02:00

logs/launchd/                    # per-job stdout + stderr (auto-created)
  com.nutmeg.daily_odds.{out,err}.log
  com.nutmeg.daily_recommend.{out,err}.log
  com.nutmeg.daily_settle.{out,err}.log
  com.nutmeg.weekly_gate.{out,err}.log
  com.nutmeg.weekly_calibration_check.{out,err}.log
  com.nutmeg.daily_wc_predict.{out,err}.log
  com.nutmeg.daily_wc_settle.{out,err}.log

~/Library/LaunchAgents/          # the actual plists (installed)
  com.nutmeg.daily_odds.plist
  com.nutmeg.daily_recommend.plist
  com.nutmeg.daily_settle.plist
  com.nutmeg.weekly_gate.plist
  com.nutmeg.weekly_calibration_check.plist
  com.nutmeg.daily_wc_predict.plist
  com.nutmeg.daily_wc_settle.plist
```
