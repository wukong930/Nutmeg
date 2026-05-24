#!/usr/bin/env bash
# post-v9 P1#16 — uninstall the 3 launchd jobs installed by setup_local_pipeline.sh
#
# Usage:  ./scripts/teardown_local_pipeline.sh
#
# Safe to run if jobs were never installed (bootout errors silently swallowed).
# Does NOT delete logs/launchd/ — preserves history for forensics.

set -euo pipefail

PLIST_DIR="$HOME/Library/LaunchAgents"
JOBS=("com.nutmeg.daily_odds" "com.nutmeg.daily_recommend" "com.nutmeg.weekly_settle")

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
