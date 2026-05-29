#!/usr/bin/env bash
# post-v9 P1#16 — rotate the launchd log files in logs/launchd/.
#
# Usage:   ./scripts/rotate_logs.sh [max_lines] [keep_lines]
#            max_lines  default 5000 — rotate any *.log exceeding this
#            keep_lines default 2000 — lines kept after rotation
#
# Wired into the com.nutmeg.daily_settle cron (02:00 daily) so the logs
# never grow unbounded. Also safe to run by hand any time; it only ever
# touches logs/launchd/*.log and never deletes a file.
#
# WHY copytruncate (tail → rewrite in place), NOT `mv`:
#   The com.nutmeg.api_server daemon keeps its err/out log open for its
#   whole lifetime (launchd StandardErrorPath / StandardOutPath, opened
#   O_APPEND). If we renamed the file and created a fresh one, the daemon's
#   file descriptor would still point at the old (now-unlinked) inode — it
#   would keep writing there forever and the new file would stay empty
#   until the next daemon restart. Truncating in place (`cat tmp > file`)
#   preserves the inode, so the daemon's fd stays valid and new lines land
#   after the kept tail. This is exactly logrotate's `copytruncate` mode.
#   The only cost is a tiny race: a line written in the millisecond between
#   `tail` reading and `cat` overwriting can be lost. For 02:00 housekeeping
#   on a localhost daemon that is an acceptable trade-off.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$REPO_ROOT/logs/launchd"
MAX_LINES="${1:-5000}"
KEEP_LINES="${2:-2000}"

if [[ ! -d "$LOG_DIR" ]]; then
  echo "rotate_logs: no log dir at $LOG_DIR (nothing to do)"
  exit 0
fi

# Guard against a fat-fingered invocation that would grow files.
if (( KEEP_LINES >= MAX_LINES )); then
  echo "rotate_logs: keep_lines ($KEEP_LINES) must be < max_lines ($MAX_LINES)" >&2
  exit 1
fi

rotated=0
shopt -s nullglob
for f in "$LOG_DIR"/*.log; do
  lines="$(wc -l < "$f" 2>/dev/null | tr -d ' ')"
  [[ -z "$lines" ]] && continue
  if (( lines > MAX_LINES )); then
    tmp="$(mktemp "${TMPDIR:-/tmp}/nutmeg_rotate.XXXXXX")" || continue
    if tail -n "$KEEP_LINES" "$f" > "$tmp" 2>/dev/null; then
      # copytruncate: rewrite in place so the daemon's open fd stays valid.
      cat "$tmp" > "$f"
      printf "  rotated %s (%s → %s lines)\n" "$(basename "$f")" "$lines" "$KEEP_LINES"
      rotated=$((rotated + 1))
    fi
    rm -f "$tmp"
  fi
done

if (( rotated == 0 )); then
  echo "rotate_logs: no logs over $MAX_LINES lines"
else
  echo "rotate_logs: rotated $rotated file(s) in $LOG_DIR"
fi
exit 0
