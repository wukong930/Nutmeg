#!/usr/bin/env bash
# V10 W4 Day 3 — single-command pre-WC verification.
#
# Run this before WC 2026 kickoff (2026-06-11) to confirm everything is
# wired up: env vars, fixture cache, Elo snapshot freshness, CLI works,
# dashboard endpoint, launchd jobs loaded.
#
# Exit codes:
#   0 — fully green, ready for kickoff
#   1 — at least one critical check failed (cannot operate)
#   2 — soft warnings only (operational but suboptimal — e.g., stale
#       Elo snapshot, no Pinnacle odds yet)
#
# Usage:  ./scripts/wc_preflight.sh
#
# Safe to re-run; no side effects.

set -uo pipefail

# Colors
RED=$'\033[0;31m'
YEL=$'\033[0;33m'
GRN=$'\033[0;32m'
DIM=$'\033[2m'
BOLD=$'\033[1m'
RST=$'\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

EXIT_CODE=0
WARN_ONLY=0

section() { printf "\n${BOLD}━━ %s ━━${RST}\n" "$1"; }
ok()      { printf "  ${GRN}✓${RST} %s\n" "$1"; }
warn()    { printf "  ${YEL}⚠${RST} %s\n" "$1"; WARN_ONLY=1; }
fail()    { printf "  ${RED}✗${RST} %s\n" "$1"; EXIT_CODE=1; }
note()    { printf "  ${DIM}• %s${RST}\n" "$1"; }

VENV_PY="$REPO_ROOT/.venv/bin/python"
DB_PATH="$REPO_ROOT/data/v4_observation.db"


# ===== 1. .env + API key =====
section "1. API key (.env)"
if [[ -f .env ]]; then
  KEY="$(grep -E '^NUTMEG_API_FOOTBALL_KEY=' .env | head -1 | cut -d= -f2- | tr -d '"' || true)"
  if [[ -n "${KEY:-}" && ${#KEY} -ge 30 ]]; then
    ok ".env present and NUTMEG_API_FOOTBALL_KEY looks valid (len=${#KEY})"
  else
    fail ".env present but NUTMEG_API_FOOTBALL_KEY missing or too short"
  fi
  ODDS_KEY="$(grep -E '^NUTMEG_ODDS_API_KEY=' .env | head -1 | cut -d= -f2- | tr -d '"' || true)"
  if [[ -n "${ODDS_KEY:-}" && ${#ODDS_KEY} -ge 20 ]]; then
    ok "NUTMEG_ODDS_API_KEY present (len=${#ODDS_KEY}) — Pinnacle blend will activate when odds open"
  else
    warn "NUTMEG_ODDS_API_KEY not set — WC predict will use source=lightgbm_only"
  fi
else
  fail ".env not found at repo root"
fi


# ===== 2. WC 2026 fixtures cached =====
section "2. WC 2026 fixture cache"
if [[ -d data/external/api_football/_fixtures ]]; then
  N_WC_2026="$($VENV_PY -c "
import json
from pathlib import Path
count = 0
for f in Path('data/external/api_football/_fixtures').glob('*.json'):
    try:
        data = json.loads(f.read_text())
        if isinstance(data, list):
            for fx in data:
                league = (fx.get('league') or {})
                if league.get('id') == 1 and league.get('season') == 2026:
                    count += 1
    except Exception:
        pass
print(count)
" 2>/dev/null || echo 0)"
  if [[ "$N_WC_2026" -ge 64 ]]; then
    ok "$N_WC_2026 WC 2026 fixtures in cache (expected ≥64 for 48-team format)"
  elif [[ "$N_WC_2026" -gt 0 ]]; then
    warn "$N_WC_2026 WC 2026 fixtures cached (expected ≥64) — KO bracket may not be filled in yet"
  else
    fail "0 WC 2026 fixtures in cache — run: nutmeg-ingest-cup-history --leagues WC --seasons 2026"
  fi
else
  fail "data/external/api_football/_fixtures/ does not exist"
fi


# ===== 3. National-team Elo snapshot =====
section "3. National-team Elo snapshot"
if [[ -d data/external/eloratings ]]; then
  LATEST_SNAP="$(ls -t data/external/eloratings/eloratings_*.parquet 2>/dev/null | head -1)"
  if [[ -n "$LATEST_SNAP" ]]; then
    SNAP_NAME="$(basename "$LATEST_SNAP")"
    SNAP_MTIME=$(date -r "$LATEST_SNAP" +%s)
    NOW=$(date +%s)
    AGE_DAYS=$(( (NOW - SNAP_MTIME) / 86400 ))
    N_NATIONS="$($VENV_PY -c "
import pandas as pd
print(len(pd.read_parquet('$LATEST_SNAP')))
" 2>/dev/null || echo 0)"

    if [[ "$AGE_DAYS" -le 14 ]]; then
      ok "$SNAP_NAME ($N_NATIONS nations, ${AGE_DAYS}d old)"
    elif [[ "$AGE_DAYS" -le 30 ]]; then
      warn "$SNAP_NAME is ${AGE_DAYS}d old — re-run nutmeg-ingest-national-elo before kickoff"
    else
      fail "$SNAP_NAME is ${AGE_DAYS}d old — Elo data stale; refresh immediately"
    fi
  else
    fail "No eloratings_*.parquet snapshots found"
  fi
else
  fail "data/external/eloratings/ does not exist"
fi


# ===== 4. WC predict CLI works =====
section "4. nutmeg-wc-predict CLI"
TMP_OUT="$(mktemp)"
if PYTHONPATH=apps/api/src $VENV_PY -m nutmeg.v4.cli.wc_predict \
   --date 2026-06-11 --quiet --out "$TMP_OUT" 2>/dev/null; then
  N_PREDS="$($VENV_PY -c "
import json
data = json.loads(open('$TMP_OUT').read())
print(data.get('n_fixtures', 0))
" 2>/dev/null || echo 0)"
  if [[ "$N_PREDS" -ge 1 ]]; then
    ok "CLI returned $N_PREDS predictions for 2026-06-11 opener"
  else
    warn "CLI ran but returned 0 predictions for 2026-06-11"
  fi
else
  fail "nutmeg-wc-predict failed for 2026-06-11"
fi
rm -f "$TMP_OUT"


# ===== 5. Dashboard endpoint =====
section "5. /api/v4/predictions/wc endpoint"
ENDPOINT_OK="$(PYTHONPATH=apps/api/src $VENV_PY -c "
import os
os.environ['NUTMEG_V4_ARTIFACT_PATH'] = 'data/v4_model'
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nutmeg.v4.api import v4_router
app = FastAPI()
app.include_router(v4_router, prefix='/api')
client = TestClient(app)
r = client.get('/api/v4/predictions/wc?date=2026-06-11')
print('OK' if r.status_code == 200 and r.json().get('n_fixtures', 0) >= 1 else 'FAIL')
" 2>/dev/null || echo FAIL)"
if [[ "$ENDPOINT_OK" == "OK" ]]; then
  ok "/api/v4/predictions/wc returns ≥1 prediction for 2026-06-11"
else
  fail "/api/v4/predictions/wc not returning data for the opener"
fi


# ===== 6. Launchd jobs loaded =====
section "6. Launchd jobs"
JOBS=(
  "com.nutmeg.daily_wc_predict"
  "com.nutmeg.daily_wc_settle"
  "com.nutmeg.weekly_calibration_check"
)
LIST_SNAP="$(launchctl list 2>/dev/null || true)"
for job in "${JOBS[@]}"; do
  if printf '%s\n' "$LIST_SNAP" | grep -F -q "$job"; then
    ok "$job loaded"
  else
    warn "$job not loaded — run ./scripts/setup_local_pipeline.sh"
  fi
done


# ===== 7. wc_predictions table accessible =====
section "7. Observation DB schema"
if [[ -f "$DB_PATH" ]]; then
  TABLE_OK="$($VENV_PY -c "
import sqlite3
try:
    conn = sqlite3.connect('$DB_PATH')
    rows = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='wc_predictions'\").fetchall()
    print('OK' if rows else 'NO_TABLE')
except Exception:
    print('FAIL')
" 2>/dev/null || echo FAIL)"
  case "$TABLE_OK" in
    OK)
      N_PREDS="$($VENV_PY -c "
import sqlite3
print(sqlite3.connect('$DB_PATH').execute('SELECT COUNT(*) FROM wc_predictions').fetchone()[0])
" 2>/dev/null || echo 0)"
      ok "wc_predictions table exists ($N_PREDS rows so far)"
      ;;
    NO_TABLE)
      note "wc_predictions table missing — will be created on first record_to call"
      ;;
    FAIL)
      fail "Observation DB exists but couldn't query"
      ;;
  esac
else
  note "$DB_PATH not found — will be created by first cron run"
fi


# ===== Summary =====
section "Summary"
if [[ $EXIT_CODE -eq 0 && $WARN_ONLY -eq 0 ]]; then
  printf "${GRN}${BOLD}READY FOR KICKOFF${RST} — all systems green for 2026-06-11.\n"
elif [[ $EXIT_CODE -eq 0 ]]; then
  printf "${YEL}${BOLD}READY WITH WARNINGS${RST} — operational but address yellow items.\n"
  EXIT_CODE=2
else
  printf "${RED}${BOLD}NOT READY${RST} — at least one critical check failed (see above).\n"
fi

exit $EXIT_CODE
