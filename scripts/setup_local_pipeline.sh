#!/usr/bin/env bash
# post-v9 P1#16 — one-shot install of the local Nutmeg data pipeline (macOS).
#
# Installs 7 launchd jobs into ~/Library/LaunchAgents:
#   1. com.nutmeg.daily_odds                  14:00 daily — fetch today's odds
#   2. com.nutmeg.daily_recommend             15:00 daily — generate recommendations + record session
#   3. com.nutmeg.weekly_settle               Sunday 02:00 — settle past-week outcomes + write ROI report
#   4. com.nutmeg.weekly_gate                 Sunday 04:00 — P1#19 live-vs-backtest gate
#   5. com.nutmeg.weekly_calibration_check    Monday 03:00 — V10 W2 auto-T calibration drift check + rollback
#   6. com.nutmeg.daily_wc_predict            09:00 daily — V10 W4 WC predictions + record
#   7. com.nutmeg.daily_wc_settle             02:00 daily — V10 W4 WC outcome settle + report
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

# Common shell prefix for all jobs: cd + source .env so NUTMEG_API_FOOTBALL_KEY is set
ENV_PREFIX="cd $REPO_ROOT && set -a && source .env && set +a"

echo "Installing 7 launchd jobs into $PLIST_DIR ..."

# Job 1: daily odds ingest (14:00 daily)
# Pulls today's odds for the 5 main domestic leagues.
# post-v9 P1#20: UCL+UEL removed — cup ablation answered negatively
# (see docs/post_v9_p1_20_cup_ablation_negative.md), forward
# accumulation no longer serves any open question. Save ~10 API calls/day.
install_job "com.nutmeg.daily_odds" \
  14 0 "" \
  "$ENV_PREFIX && $VENV_PY -m nutmeg.v4.cli.ingest_odds --leagues EPL,ESP_LA_LIGA,ITA_SERIE_A,GER_BUNDESLIGA,FRA_LIGUE_1"

# Job 2: daily recommend + record (15:00 daily)
# Generates recommendations using both default + lineup-aware models,
# records each session into the observation DB. This is what populates
# the data we need for the 4-week lineup ROI verdict.
install_job "com.nutmeg.daily_recommend" \
  15 0 "" \
  "$ENV_PREFIX && $VENV_PY -m nutmeg.v4.cli.recommend --auto-fetch --leagues EPL,ESP_LA_LIGA --record-to $DB_PATH"

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
echo "    $LOG_DIR/com.nutmeg.daily_odds.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.daily_recommend.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.weekly_settle.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.weekly_gate.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.weekly_calibration_check.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.daily_wc_predict.{out,err}.log"
echo "    $LOG_DIR/com.nutmeg.daily_wc_settle.{out,err}.log"
echo ""
echo "Next:"
echo "  • Verify with: ./scripts/health_check.sh"
echo "  • Inspect jobs: launchctl list | grep com.nutmeg"
echo "  • Daily timeline: 02:00 wc_settle → 03:00 calibration → 09:00 wc_predict → 14:00 odds → 15:00 recommend"
echo "  • Weekly gate reports land at: $GATE_OUT_DIR/p1_19_gate_<ISO-week>.md"
echo "  • Weekly calibration reports land at: $CALIB_OUT_DIR/auto_calibration_<ISO-week>.md"
echo "  • Daily WC reports land at: $WC_OUT_DIR/wc_report_<YYYY-MM-DD>.md"
echo "  • Uninstall: ./scripts/teardown_local_pipeline.sh"
