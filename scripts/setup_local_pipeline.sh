#!/usr/bin/env bash
# post-v9 P1#16 — one-shot install of the local Nutmeg data pipeline (macOS).
#
# Installs 7 launchd jobs into ~/Library/LaunchAgents:
#   1. com.nutmeg.api_server                  always-on daemon — FastAPI dashboard server on 127.0.0.1:8080
#   2. com.nutmeg.morning_odds                09:00 daily — V12 W0 Plan A: fetch Asian (J1) odds
#   3. com.nutmeg.morning_recommend           10:00 daily — V12 W0 Plan A: morning wave recommendations
#   4. com.nutmeg.daily_odds                  14:00 daily — V12 W0 Plan A: afternoon European wave odds
#   5. com.nutmeg.daily_recommend             15:00 daily — afternoon wave recommendations
#   6. com.nutmeg.weekly_settle               Sunday 02:00 — settle past-week outcomes + write ROI report
#   7. com.nutmeg.weekly_gate                 Sunday 04:00 — P1#19 live-vs-backtest gate
#   8. com.nutmeg.weekly_calibration_check    Monday 03:00 — V10 W2 auto-T calibration drift check + rollback
#   9. com.nutmeg.daily_wc_predict            09:00 daily — V10 W4 WC predictions + record
#  10. com.nutmeg.daily_wc_settle             02:00 daily — V10 W4 WC outcome settle + report
#
# All read NUTMEG_API_FOOTBALL_KEY from .env via the shell wrapper
# (no plaintext key in plists). Logs go to logs/launchd/.
#
# Usage:   ./scripts/setup_local_pipeline.sh
# Re-run:  safe to re-run; bootout + bootstrap each job before installing
# Undo:    ./scripts/teardown_local_pipeline.sh
#
# Why launchd not crontab? macOS prefers launchd: (a) survives reboots
# automatically, (b) handles missed runs (RunAtLoad), (c) GUI-inspectable
# via Console.app, (d) per-job log files, (e) no fragile crontab format.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PLATFORM="$(uname -s)"
if [[ "$PLATFORM" != "Darwin" ]]; then
  echo "ERROR: this script only supports macOS (uname=$PLATFORM)" >&2
  echo "  For Linux: write a systemd unit or use crontab manually." >&2
  exit 1
fi

# Resolve absolute paths (launchd needs them; relative paths don't work)
VENV_PY="$REPO_ROOT/.venv/bin/python"
LOG_DIR="$REPO_ROOT/logs/launchd"
DB_PATH="$REPO_ROOT/data/v4_observation.db"
PLIST_DIR="$HOME/Library/LaunchAgents"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: $VENV_PY not found or not executable" >&2
  echo "  Set up the venv first (uv pip install -e .)" >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "ERROR: .env not found at $REPO_ROOT/.env" >&2
  echo "  Create it with NUTMEG_API_FOOTBALL_KEY=<your-key>" >&2
  exit 1
fi

mkdir -p "$LOG_DIR" "$PLIST_DIR"

# Helper: write a single plist atomically + bootstrap it
install_job() {
  local label="$1"
  local hour="$2"
  local minute="$3"
  local weekday="$4"   # 0-6 (0=Sun); empty for "every day"
  local script="$5"

  local plist="$PLIST_DIR/$label.plist"
  local out_log="$LOG_DIR/$label.out.log"
  local err_log="$LOG_DIR/$label.err.log"

  local calendar_xml="<key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>$hour</integer>
        <key>Minute</key><integer>$minute</integer>"
  if [[ -n "$weekday" ]]; then
    calendar_xml="$calendar_xml
        <key>Weekday</key><integer>$weekday</integer>"
  fi
  calendar_xml="$calendar_xml
    </dict>"

  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$label</string>
    <key>WorkingDirectory</key>
    <string>$REPO_ROOT</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>$script</string>
    </array>
    $calendar_xml
    <key>StandardOutPath</key>
    <string>$out_log</string>
    <key>StandardErrorPath</key>
    <string>$err_log</string>
    <key>RunAtLoad</key>
    <false/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>PYTHONPATH</key>
        <string>$REPO_ROOT/apps/api/src</string>
    </dict>
</dict>
</plist>
EOF

  # Bootstrap (idempotent — bootout first if loaded)
  launchctl bootout "gui/$UID/$label" 2>/dev/null || true
  if launchctl bootstrap "gui/$UID" "$plist" 2>/dev/null; then
    printf "  ✓ installed %s (runs %02d:%02d%s)\n" "$label" "$hour" "$minute" \
      "$([[ -n "$weekday" ]] && echo " weekday=$weekday" || echo " daily")"
  else
    printf "  ✗ failed to bootstrap %s\n" "$label" >&2
    exit 1
  fi
}

# V12 W0 (2026-05-28) — long-running daemon variant of install_job.
# Used for the FastAPI server so the dashboard is reachable any time
# without manual `uvicorn` invocations. KeepAlive=true means launchd
# auto-restarts the process if it crashes; RunAtLoad=true means it
# starts when the user logs in (and stays up across reboots once
# bootstrap'd).
#
# Differences from install_job:
#   - No StartCalendarInterval (it's a daemon, not a cron job)
#   - KeepAlive=true (auto-restart on crash)
#   - RunAtLoad=true (start immediately + on every user login)
install_daemon() {
  local label="$1"
  local cmd="$2"

  local plist="$PLIST_DIR/$label.plist"
  local out_log="$LOG_DIR/$label.out.log"
  local err_log="$LOG_DIR/$label.err.log"

  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$label</string>
    <key>WorkingDirectory</key>
    <string>$REPO_ROOT</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>$cmd</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>$out_log</string>
    <key>StandardErrorPath</key>
    <string>$err_log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>PYTHONPATH</key>
        <string>$REPO_ROOT/apps/api/src</string>
    </dict>
</dict>
</plist>
EOF

  launchctl bootout "gui/$UID/$label" 2>/dev/null || true
  if launchctl bootstrap "gui/$UID" "$plist" 2>/dev/null; then
    printf "  ✓ installed %s (daemon — RunAtLoad + KeepAlive)\n" "$label"
  else
    printf "  ✗ failed to bootstrap %s\n" "$label" >&2
    exit 1
  fi
}

# Common shell prefix for all jobs: cd + source .env so NUTMEG_API_FOOTBALL_KEY is set
ENV_PREFIX="cd $REPO_ROOT && set -a && source .env && set +a"

# V12 W0 Plan A (Option B variant) — split leagues by region so each
# wave's Pinnacle SP is captured close to that region's closing line.
#
# WHY split: morning EU SP (09:00) is ~11h pre-kickoff = early/opening line,
# far from closing. Our model was trained against closing odds, so using
# opening lines introduces systematic noise. Asian leagues (J1 weekend
# kickoffs at 12:00 CST) need a 09:00 pull to catch their closing window
# — but European leagues do NOT need to be in that pull, they're better
# served by the 14:00 cron (6h pre-kickoff = much closer to closing).
#
# Trade-off: cross-region combos (e.g., J1+EU 4-串-1) are impossible in
# any single wave under this split. User picks J1 picks in the morning,
# EU picks in the afternoon, as two separate bets. Per V12 W0 discussion
# 2026-05-28 this matches the actual user workflow.
LEAGUES_ASIAN="JPN_J1"
LEAGUES_EUROPEAN="EPL,ESP_LA_LIGA,ITA_SERIE_A,GER_BUNDESLIGA,FRA_LIGUE_1,ENG_CHAMPIONSHIP,ESP_SEGUNDA_DIVISION,ITA_SERIE_B,GER_2_BUNDESLIGA,FRA_LIGUE_2,NED_EREDIVISIE,PRT_PRIMEIRA_LIGA,BEL_PRO_LEAGUE"

# Where Job 1 drops the daily CSV that Job 2 consumes. ``$(date +%Y-%m-%d)``
# is expanded by /bin/bash at run time (not by setup_local_pipeline.sh),
# so the plist content stays stable across days.
DAILY_DIR="$REPO_ROOT/data/daily"
mkdir -p "$DAILY_DIR"   # Job 1 / Job 2 don't bother re-creating per-run
DAILY_CSV='$REPO_ROOT/data/daily/fixtures_$(date +%Y-%m-%d).csv'   # NOT expanded here — see /bin/bash -c below
# V12 W0 Plan A — morning wave CSV (J1 + future European fixtures). The
# afternoon CSV overwrites this 4 hours later (still same day file) with
# the post-J1 European-only set.
MORNING_CSV='$REPO_ROOT/data/daily/fixtures_$(date +%Y-%m-%d)_morning.csv'
# NB: launchd plists use /bin/bash -c "<string>" so the shell will expand
# $(date ...) and $REPO_ROOT at run time. We keep DAILY_CSV single-quoted
# in setup so write_plist embeds the literal string.

echo "Installing 10 launchd jobs into $PLIST_DIR ..."

# ── V12 W0 (2026-05-28) — Always-on FastAPI server (daemon) ────────────
# Why: the dashboard needs the API server running 24/7 to load. Previously
# the server was a manually-spawned uvicorn process that died when the
# user's terminal closed / the sandbox cleaned up / the laptop slept.
# Result: "❌ 抓取盘口失败 (API 暂不可用)" because the page can't reach 8080.
#
# Now: launchd manages it. RunAtLoad=true → starts at user login.
# KeepAlive=true → auto-restart if it crashes. ThrottleInterval=10s → if
# uvicorn fails to start (e.g., port in use), launchd waits 10s before
# the next retry instead of busy-looping.
#
# Bind to 127.0.0.1:8080 (localhost only — no LAN exposure). For phone
# access, separately run: `./scripts/run_local_server.sh 8080 lan` (this
# will conflict with the daemon's port; stop the daemon first with
# `launchctl bootout gui/$UID/com.nutmeg.api_server`).
install_daemon "com.nutmeg.api_server" \
  "cd $REPO_ROOT && set -a && source .env && set +a && $VENV_PY -m uvicorn nutmeg.main:app --host 127.0.0.1 --port 8080 --app-dir $REPO_ROOT/apps/api/src"

# ── V12 W0 Plan A — Morning wave (09:00 + 10:00) ───────────────────────
# Why: J1 has weekend kickoffs at 12:00-14:00 CST. The 14:00 cron is
# already too late for those. By running the ingest at 09:00 (3+ hours
# before earliest J1 kickoff), we capture Pinnacle SP near J1's closing
# window. Job 2 (morning_recommend) at 10:00 generates Wave 1 picks.
#
# Region split (Option B — locked 2026-05-28): morning_odds pulls
# JPN_J1 ONLY, not EU. Reason: EU SP at 09:00 is ~11h pre-kickoff
# (opening line). Our model is trained against closing line, so using
# 09:00 EU SP introduces systematic noise. EU waits for the 14:00 cron
# where its SP is ~6h pre-kickoff (closer to closing).
#
# Trade-off: cross-region combos (J1+EU 4-串-1) impossible in any single
# wave. User makes J1 bets in the morning, EU bets in the afternoon.
#
# Filter: --min-kickoff-buffer-minutes 30 drops fixtures already kicked
# off OR kicking off in < 30 min. With $LEAGUES_ASIAN = "JPN_J1" the
# filter mostly catches the FT case (defensive guard if cron retries
# after kickoff).
#
# Both waves write distinct sessions to the observation DB. 推荐追溯
# surfaces both under the same date.
install_job "com.nutmeg.morning_odds" \
  9 0 "" \
  "$ENV_PREFIX && REPO_ROOT=$REPO_ROOT && mkdir -p $DAILY_DIR && $VENV_PY -m nutmeg.v4.cli.ingest_odds --leagues $LEAGUES_ASIAN --min-kickoff-buffer-minutes 30 --out $MORNING_CSV"

install_job "com.nutmeg.morning_recommend" \
  10 0 "" \
  "$ENV_PREFIX && REPO_ROOT=$REPO_ROOT && $VENV_PY -m nutmeg.v4.cli.recommend --fixtures $MORNING_CSV --record-to $DB_PATH"

# Job 1: daily odds ingest (14:00 daily) — afternoon European wave
# V12 W0 Plan A (Option B): $LEAGUES_EUROPEAN = 13 European leagues
# (top 5 + 5 second-tier + Eredivisie + Liga Portugal + Belgian Pro League).
# JPN_J1 is now handled by the 09:00 morning_odds job, NOT here.
#
# post-v9 P1#20: UCL/UEL/UECL still excluded — cup ablation closed
# negative (docs/post_v9_p1_20_cup_ablation_negative.md). Cups stay
# out of cron until / unless a separate cup model ships.
#
# CRON FIX 2026-05-26: Job 1 now writes the CSV to a dated file so
# Job 2 can find it. Previously the CSV went to stdout/log (unusable
# as input). DAILY_CSV is single-quoted at install time; /bin/bash -c
# expands $(date) + $REPO_ROOT at the 14:00 firing.
#
# V12 W0 Plan A: --min-kickoff-buffer-minutes 30 filters out fixtures
# within 30 min of kickoff (no time to act). Combined with the
# European-only league list, the 14:00 CSV is naturally clean of any
# Asian leftovers — they were already handled by the morning wave.
#
# API budget under Option B: ~22 calls/day (13 EU /fixtures + ~9 /odds).
# Plus ~1-3 calls/day for the morning J1 wave. Total still well under
# free tier's 100/day.
install_job "com.nutmeg.daily_odds" \
  14 0 "" \
  "$ENV_PREFIX && REPO_ROOT=$REPO_ROOT && mkdir -p $DAILY_DIR && $VENV_PY -m nutmeg.v4.cli.ingest_odds --leagues $LEAGUES_EUROPEAN --min-kickoff-buffer-minutes 30 --out $DAILY_CSV"

# Job 2: daily recommend + record (15:00 daily — 1h after Job 1)
# Generates recommendations using the production model (V6 W7 lineup-aware
# CatBoost since P1#18 ship), records each session into the observation
# DB. This is what populates the data we need for the 4-week lineup ROI
# verdict + Layer A T calibration.
#
# CRON FIX 2026-05-26: previously this called
#   nutmeg.v4.cli.recommend --auto-fetch --leagues ...
# which doesn't exist (recommend.py only takes --fixtures + --record-to;
# --auto-fetch lives on nutmeg-rec which itself lacks --record-to).
# Now: read the CSV Job 1 just wrote.
#
# If Job 1 failed earlier (API outage etc.), Job 2 will see "no such file"
# and exit non-zero — the err log surfaces the upstream gap clearly
# instead of producing silent bad data.
install_job "com.nutmeg.daily_recommend" \
  15 0 "" \
  "$ENV_PREFIX && REPO_ROOT=$REPO_ROOT && $VENV_PY -m nutmeg.v4.cli.recommend --fixtures $DAILY_CSV --record-to $DB_PATH"

# Job 3: weekly settle (Sunday 02:00)
# Pulls past-week match results, settles open recommendations,
# refreshes the ROI report file.
install_job "com.nutmeg.weekly_settle" \
  2 0 0 \
  "$ENV_PREFIX && $VENV_PY -m nutmeg.v4.cli.auto_settle --db $DB_PATH && $VENV_PY -m nutmeg.v4.cli.ab_report --weeks 4 --db $DB_PATH --out $REPO_ROOT/docs/local_ab_report_latest.md || true"

# Job 4: weekly P1#19 gate (Sunday 04:00, 2h after settle)
# post-v9 P1#24: automate the P1#19 cross-source-aware gate.
# Compares live lineup-aware ROI to the P1#17 historical replay
# baseline. Uses --tolerance-pp 50 (cross-source noise floor per
# P1#22 — live cron uses API-Football odds; reference uses
# football-data.co.uk PSC; their snapshot-time differences alone
# cause 30-50pp ROI gap without any model issue).
#
# Output: docs/weekly/p1_19_gate_$(date +%Y-W%V).md
# Exit code: 0 within tolerance; 2 over tolerance (logged but not
# alarmed — operator should `tail` the err log on Monday morning).
BACKTEST_DB="$REPO_ROOT/data/v4_observation_backtest.db"
GATE_OUT_DIR="$REPO_ROOT/docs/weekly"
install_job "com.nutmeg.weekly_gate" \
  4 0 0 \
  "$ENV_PREFIX && mkdir -p $GATE_OUT_DIR && $VENV_PY -m nutmeg.v4.cli.live_vs_backtest --db $DB_PATH --weeks 4 --live-model-arm lineup_aware --roi-backtest-db $BACKTEST_DB --roi-backtest-arm lineup_aware --tolerance-pp 50 --out $GATE_OUT_DIR/p1_19_gate_\$(date +%Y-W%V).md || true"

# Job 5: V10 W2 weekly auto-T calibration check (Monday 03:00)
# Runs auto-rollback safety net FIRST: if the currently-deployed
# `live_T_correction.json` has post-deploy log-loss WORSE than identity
# by > 0.003, automatically revert (journal + delete artifact).
# Otherwise proposes a fresh T against the last 8 weeks of data and
# writes the proposal to the journal (action=propose). User reviews
# the report Monday morning and decides whether to ship via:
#   nutmeg-auto-calibration --apply --action=deploy --deploy-artifact <dir>
#
# Why Monday 03:00? Settle (Sunday 02:00) and Gate (Sunday 04:00)
# need to finish first — calibration uses the freshly-settled rows.
ARTIFACT_DIR="$REPO_ROOT/data/v4_model"
CALIB_OUT_DIR="$REPO_ROOT/docs/weekly"
install_job "com.nutmeg.weekly_calibration_check" \
  3 0 1 \
  "$ENV_PREFIX && mkdir -p $CALIB_OUT_DIR && $VENV_PY -m nutmeg.v4.cli.auto_calibration --db $DB_PATH --apply --auto-rollback --deploy-artifact $ARTIFACT_DIR --out $CALIB_OUT_DIR/auto_calibration_\$(date +%Y-W%V).md || true"

# Job 6: V10 W4 WC daily predict (09:00 daily during tournament)
# Re-runs nutmeg-wc-predict for today, fetches current Pinnacle odds
# (once they open), and UPSERTS each prediction into wc_predictions
# (PK = fixture_id → idempotent on repeated runs).
# Also writes a per-day JSON report under docs/wc/.
WC_OUT_DIR="$REPO_ROOT/docs/wc"
install_job "com.nutmeg.daily_wc_predict" \
  9 0 "" \
  "$ENV_PREFIX && mkdir -p $WC_OUT_DIR && $VENV_PY -m nutmeg.v4.cli.wc_predict --date \$(date +%Y-%m-%d) --fetch-current-odds --record-to $DB_PATH --out $WC_OUT_DIR/wc_\$(date +%Y-%m-%d).json --quiet || true"

# Job 7: V10 W4 WC daily settle (02:00 daily)
# Pulls finished WC fixtures from API-Football, fills outcome columns
# in wc_predictions. Runs BEFORE the calibration check so today's
# wc_predictions rows are settled before Layer A reads them.
# Then writes a fresh aggregate hit-rate / log-loss report.
install_job "com.nutmeg.daily_wc_settle" \
  2 0 "" \
  "$ENV_PREFIX && mkdir -p $WC_OUT_DIR && $VENV_PY -m nutmeg.v4.cli.wc_settle --db $DB_PATH --quiet && $VENV_PY -m nutmeg.v4.cli.wc_report --db $DB_PATH --season 2026 --out $WC_OUT_DIR/wc_report_\$(date +%Y-%m-%d).md --quiet || true"

echo ""
echo "✓ Done. Jobs are loaded. Logs:"
echo "    $LOG_DIR/com.nutmeg.api_server.{out,err}.log    ← always-on daemon"
echo "    $LOG_DIR/com.nutmeg.morning_odds.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.morning_recommend.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.daily_odds.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.daily_recommend.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.weekly_settle.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.weekly_gate.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.weekly_calibration_check.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.daily_wc_predict.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.daily_wc_settle.{out,err}.log"
echo ""
echo "Next:"
echo "  • Dashboard now reachable 24/7 at: http://127.0.0.1:8080/api/v4/dashboard"
echo "  • Verify with: ./scripts/health_check.sh"
echo "  • Inspect jobs: launchctl list | grep com.nutmeg"
echo "  • Stop the API server only: launchctl bootout gui/\$UID/com.nutmeg.api_server"
echo "  • Daily timeline: 02:00 wc_settle → 03:00 calibration → 09:00 morning_odds + wc_predict → 10:00 morning_recommend → 14:00 daily_odds → 15:00 daily_recommend"
echo "  • Weekly gate reports land at: $GATE_OUT_DIR/p1_19_gate_<ISO-week>.md"
echo "  • Weekly calibration reports land at: $CALIB_OUT_DIR/auto_calibration_<ISO-week>.md"
echo "  • Daily WC reports land at: $WC_OUT_DIR/wc_report_<YYYY-MM-DD>.md"
echo "  • Uninstall: ./scripts/teardown_local_pipeline.sh"
