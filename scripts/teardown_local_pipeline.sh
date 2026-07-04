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
# 体检 Wave3 (P1#14) — the job list is DERIVED from the persisted plists, never
# hand-copied: the old 11-name array had drifted from the 21 installed jobs
# (setup_local_pipeline.sh is the only writer of com.nutmeg.*.plist, so the
# glob IS the installed set; a job added there is torn down here for free).
JOBS=()
for _plist in "$PLIST_DIR"/com.nutmeg.*.plist; do
  [[ -e "$_plist" ]] || continue
  JOBS+=("$(basename "$_plist" .plist)")
done
# Legacy label that may be loaded WITHOUT a persisted plist (renamed →
# daily_settle 2026-05-29); boot out the leftover if present.
JOBS+=("com.nutmeg.weekly_settle")

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
