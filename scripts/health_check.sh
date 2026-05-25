#!/usr/bin/env bash
# post-v9 P1#16 — local-deployment health check.
# Single command answering: "is my Nutmeg pipeline accumulating data?"
#
# Usage:  ./scripts/health_check.sh
# Exit:   0 = healthy, 1 = at least one critical check failed.
#
# Checks (printed to stdout in a friendly format):
#   1. .env present + NUTMEG_API_FOOTBALL_KEY set
#   2. launchd jobs status (loaded? last run? errors?)
#   3. Cup_odds parquet row counts (forward Path A progress)
#   4. Observation DB session/settlement counts
#   5. Lineup ROI 4-week eligibility check
#   6. Disk usage of the data tree
#
# Designed to be safe to run any time; no side effects.

set -uo pipefail

# Colors
RED=$'\033[0;31m'
YEL=$'\033[0;33m'
GRN=$'\033[0;32m'
DIM=$'\033[2m'
RST=$'\033[0m'
BOLD=$'\033[1m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

EXIT_CODE=0

section() { printf "\n${BOLD}━━ %s ━━${RST}\n" "$1"; }
ok()      { printf "  ${GRN}✓${RST} %s\n" "$1"; }
warn()    { printf "  ${YEL}⚠${RST} %s\n" "$1"; }
fail()    { printf "  ${RED}✗${RST} %s\n" "$1"; EXIT_CODE=1; }
note()    { printf "  ${DIM}• %s${RST}\n" "$1"; }


# ===== 1. .env =====
section "1. API key (.env)"
if [[ -f .env ]]; then
  KEY="$(grep -E '^NUTMEG_API_FOOTBALL_KEY=' .env | head -1 | cut -d= -f2- | tr -d '"' || true)"
  if [[ -n "${KEY:-}" && ${#KEY} -ge 30 ]]; then
    ok ".env present and NUTMEG_API_FOOTBALL_KEY looks valid (len=${#KEY})"
  else
    fail ".env present but NUTMEG_API_FOOTBALL_KEY missing or too short"
  fi
else
  fail ".env not found at repo root"
fi


# ===== 2. launchd jobs =====
section "2. launchd jobs"
JOBS=(
  "com.nutmeg.daily_odds"
  "com.nutmeg.daily_recommend"
  "com.nutmeg.weekly_settle"
  "com.nutmeg.weekly_gate"
  "com.nutmeg.weekly_calibration_check"
)
# Snapshot launchctl list ONCE (avoid SIGPIPE issues with grep -q + pipefail
# + repeated large-output pipes that previously caused false negatives).
LIST_SNAPSHOT="$(launchctl list 2>/dev/null || true)"
ANY_LOADED=0
for job in "${JOBS[@]}"; do
  # Use grep -F (fixed-string) so the . in com.nutmeg... isn't a regex wildcard.
  line="$(printf '%s\n' "$LIST_SNAPSHOT" | grep -F "$job" || true)"
  if [[ -n "$line" ]]; then
    ANY_LOADED=1
    pid="$(printf '%s' "$line" | awk '{print $1}')"
    last_exit="$(printf '%s' "$line" | awk '{print $2}')"
    if [[ "$last_exit" == "0" || "$pid" != "-" ]]; then
      ok "$job loaded (last exit=$last_exit, pid=$pid)"
    else
      warn "$job loaded but last exit=$last_exit (non-zero, check logs)"
    fi
  else
    warn "$job not loaded (run ./scripts/setup_local_pipeline.sh)"
  fi
done
if [[ $ANY_LOADED -eq 0 ]]; then
  fail "No launchd jobs installed — data pipeline is NOT running"
fi


# ===== 3. Cup odds parquets =====
section "3. Cup odds accumulation (Path A — V10 trigger #1)"
if command -v python3 >/dev/null 2>&1 && [[ -d data/external/cup_odds ]]; then
  TOTAL_ROWS="$(.venv/bin/python -c "
import pandas as pd
from pathlib import Path
total = 0
for p in sorted(Path('data/external/cup_odds').glob('*.parquet')):
    try:
        total += len(pd.read_parquet(p))
    except Exception:
        pass
print(total)
" 2>/dev/null || echo "?")"

  N_FILES="$(find data/external/cup_odds -name '*.parquet' 2>/dev/null | wc -l | tr -d ' ')"
  note "$N_FILES parquet files in data/external/cup_odds/"
  if [[ "$TOTAL_ROWS" == "0" ]]; then
    warn "0 rows total — Path A has accumulated nothing yet"
    note "needs ≥250 rows to retry cup ablation (V10 trigger). Today: 0"
  elif [[ "$TOTAL_ROWS" -ge 250 ]]; then
    ok "$TOTAL_ROWS rows accumulated — V10 trigger #1 READY"
  else
    PCT=$(( TOTAL_ROWS * 100 / 250 ))
    note "$TOTAL_ROWS / 250 rows ($PCT% of cup-ablation trigger threshold)"
  fi
else
  warn "Could not check cup_odds (no python or directory missing)"
fi


# ===== 4. Observation DB =====
section "4. Observation DB (Lineup ROI — V10 trigger #2)"
DB="data/v4_observation.db"
if [[ -f "$DB" ]]; then
  STATS="$(.venv/bin/python -c "
import sqlite3
import sys
try:
    conn = sqlite3.connect('$DB')
    sess = conn.execute('SELECT COUNT(*) FROM recommendation_sessions').fetchone()[0]
    recs = conn.execute('SELECT COUNT(*) FROM parlay_recommendations').fetchone()[0]
    outc = conn.execute('SELECT COUNT(*) FROM match_outcomes').fetchone()[0]
    settled = conn.execute('SELECT COUNT(*) FROM settlements').fetchone()[0]
    # First + last session date for age estimation
    first_last = conn.execute(
        'SELECT MIN(created_at), MAX(created_at) FROM recommendation_sessions'
    ).fetchone()
    print(f'{sess} {recs} {outc} {settled} {first_last[0] or \"-\"} {first_last[1] or \"-\"}')
except Exception as e:
    print(f'ERROR {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null)" || STATS=""

  if [[ -n "$STATS" ]]; then
    SESS="$(echo "$STATS" | awk '{print $1}')"
    RECS="$(echo "$STATS" | awk '{print $2}')"
    OUTC="$(echo "$STATS" | awk '{print $3}')"
    SETTLED="$(echo "$STATS" | awk '{print $4}')"
    FIRST="$(echo "$STATS" | awk '{print $5}')"
    LAST="$(echo "$STATS" | awk '{print $6}')"
    note "sessions: $SESS · recommendations: $RECS · outcomes: $OUTC · settled: $SETTLED"
    note "first session: $FIRST · last session: $LAST"
    if [[ "$SETTLED" -ge 60 ]]; then
      ok "$SETTLED settlements — enough to read 4-week ROI verdict"
      note "next step: PYTHONPATH=apps/api/src .venv/bin/python -m nutmeg.v4.cli.ab_report --weeks 4 --db $DB"
    elif [[ "$SESS" -gt 0 ]]; then
      warn "$SETTLED settlements (need ≥60 for verdict; ≥30/side)"
    else
      warn "DB exists but 0 sessions — recommend step never ran"
    fi
  else
    fail "Observation DB exists but couldn't query (corrupt? schema mismatch?)"
  fi
else
  fail "$DB not found — no Lineup ROI accumulation has happened yet"
fi


# ===== 5. Disk usage =====
section "5. Disk usage"
if [[ -d data/ ]]; then
  DSIZE="$(du -sh data/ 2>/dev/null | awk '{print $1}')"
  note "data/ total: $DSIZE"
fi
if [[ -d ~/Library/Caches/ms-playwright ]]; then
  PWSIZE="$(du -sh ~/Library/Caches/ms-playwright 2>/dev/null | awk '{print $1}')"
  note "Playwright cache (~/Library/Caches/ms-playwright): $PWSIZE"
fi


# ===== Summary =====
section "Summary"
if [[ $EXIT_CODE -eq 0 ]]; then
  printf "${GRN}${BOLD}HEALTHY${RST} — pipeline is set up and (where applicable) accumulating data.\n"
else
  printf "${RED}${BOLD}NOT HEALTHY${RST} — at least one critical check failed (see above).\n"
  printf "  ${DIM}Run ./scripts/setup_local_pipeline.sh to install the launchd jobs.${RST}\n"
fi

exit $EXIT_CODE
