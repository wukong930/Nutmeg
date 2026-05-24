# Local Deployment Guide

_post-v9 P1#16. Replaces the broken GitHub Actions cron with a
reliable local-machine pipeline. macOS-specific (uses launchd)._

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

## What gets installed (3 jobs)

| Job | When | What it does |
|---|---|---|
| `com.nutmeg.daily_odds` | 14:00 daily | Fetch today's odds for 5 leagues + UCL + UEL (Path A accumulation for cup-odds parquets) |
| `com.nutmeg.daily_recommend` | 15:00 daily | Generate EPL + La Liga recommendations, record session into observation DB |
| `com.nutmeg.weekly_settle` | Sunday 02:00 | Settle past-week match outcomes + refresh `docs/local_ab_report_latest.md` |

All 3 read `NUTMEG_API_FOOTBALL_KEY` from `.env` at run time
(no plaintext key in plist files).

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
  ✓ com.nutmeg.weekly_settle loaded (last exit=0, pid=-)

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

## V10 trigger conditions — when can we ship V10?

Both triggers are now actually trackable via `health_check.sh`:

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

(The weekly_settle job also writes `docs/local_ab_report_latest.md`
automatically every Sunday — just open that file.)

## Uninstall

```bash
./scripts/teardown_local_pipeline.sh
```

Removes the 3 launchd jobs + their plists. Logs in `logs/launchd/`
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
  setup_local_pipeline.sh        # install 3 launchd jobs
  teardown_local_pipeline.sh     # uninstall (preserves logs)
  health_check.sh                # single-command status
  run_local_server.sh            # launch FastAPI uvicorn

docs/
  local_deployment_guide.md      # this file
  local_ab_report_latest.md      # written by weekly_settle each Sun 02:00

logs/launchd/                    # per-job stdout + stderr (auto-created)
  com.nutmeg.daily_odds.{out,err}.log
  com.nutmeg.daily_recommend.{out,err}.log
  com.nutmeg.weekly_settle.{out,err}.log

~/Library/LaunchAgents/          # the actual plists (installed)
  com.nutmeg.daily_odds.plist
  com.nutmeg.daily_recommend.plist
  com.nutmeg.weekly_settle.plist
```
