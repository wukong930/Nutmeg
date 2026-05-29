#!/usr/bin/env bash
# post-v9 P1#16 — uninstall the launchd jobs installed by setup_local_pipeline.sh
# V10 W2 Day 4 — added com.nutmeg.weekly_calibration_check
#
# Usage:  ./scripts/teardown_local_pipeline.sh
#
# Safe to run if jobs were never installed (bootout errors silently swallowed).
# Does NOT delete logs/launchd/ — preserves history for forensics.

set -euo pipefail

PLIST_DIR="$HOME/Library/LaunchAgents"
JOBS=(
  "com.nutmeg.api_server"             # V12 W0 — always-on FastAPI daemon
  "com.nutmeg.morning_odds"           # V12 W0 Plan A — Asian (J1)
  "com.nutmeg.morning_recommend"      # V12 W0 Plan A
  "com.nutmeg.daily_odds"
  "com.nutmeg.daily_recommend"
  "com.nutmeg.daily_settle"
  "com.nutmeg.weekly_settle"          # legacy (renamed → daily_settle 2026-05-29); boot out leftover
  "com.nutmeg.weekly_gate"
  "com.nutmeg.weekly_calibration_check"
  "com.nutmeg.daily_wc_predict"
  "com.nutmeg.daily_wc_settle"
)

echo "Uninstalling launchd jobs ..."
for job in "${JOBS[@]}"; do
  if launchctl bootout "gui/$UID/$job" 2>/dev/null; then
    echo "  ✓ booted out $job"
  else
    echo "  • $job not currently loaded (skipping bootout)"
  fi
  plist="$PLIST_DIR/$job.plist"
  if [[ -f "$plist" ]]; then
    rm "$plist"
    echo "  ✓ removed $plist"
  fi
done

echo ""
echo "Done. Logs preserved at logs/launchd/ (delete manually if you don't need them)."
echo "Re-install: ./scripts/setup_local_pipeline.sh"
