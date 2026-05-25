#!/usr/bin/env bash
# V11 Phase 0 — one-command status check for the 4 V11 triggers.
#
# Reads existing artifacts (no API calls, no DB writes) and prints:
#   1. WC 2026 model hit-rate     (from wc_predictions table or docs/wc/*)
#   2. Layer A auto-T cycles      (from calibration_journal + docs/weekly/auto_calibration_*)
#   3. Lineup ROI 4-week verdict  (from observation DB settlements)
#   4. Cross-source caveat status (from docs/weekly/p1_19_gate_*)
#
# Then synthesizes a branch recommendation:
#   - Branch A (WC HR ≥ 55%)  → national-team expansion + MCMC
#   - Branch B (WC HR 45-55%) → domestic Layer B + Path 3+4
#   - Branch C (WC HR < 45%)  → negative postmortem + Layer B
#   - "not ready"             → wait for more data
#
# Usage:  ./scripts/v11_monitor.sh
# Exit:   0 = at least one trigger fired (V11 W1 unblocked)
#         1 = blocking error (DB corrupt, etc.)
#         2 = waiting (no triggers fired yet — normal during Phase 0)
#
# Safe to run any time; read-only.

set -uo pipefail

# Colors
RED=$'\033[0;31m'
YEL=$'\033[0;33m'
GRN=$'\033[0;32m'
CYA=$'\033[0;36m'
DIM=$'\033[2m'
BOLD=$'\033[1m'
RST=$'\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

EXIT_CODE=2  # default: waiting
TRIGGER_FIRED=0
BRANCH_RECOMMENDATION=""

section() { printf "\n${BOLD}━━ %s ━━${RST}\n" "$1"; }
ok()      { printf "  ${GRN}✓${RST} %s\n" "$1"; }
warn()    { printf "  ${YEL}⚠${RST} %s\n" "$1"; }
fail()    { printf "  ${RED}✗${RST} %s\n" "$1"; EXIT_CODE=1; }
note()    { printf "  ${DIM}• %s${RST}\n" "$1"; }
hi()      { printf "  ${CYA}▶${RST} ${BOLD}%s${RST}\n" "$1"; }

VENV_PY="$REPO_ROOT/.venv/bin/python"
DB_PATH="$REPO_ROOT/data/v4_observation.db"

if [[ ! -x "$VENV_PY" ]]; then
  echo "${RED}ERROR:${RST} $VENV_PY not found — run 'uv pip install -e .' first" >&2
  exit 1
fi

printf "${BOLD}V11 Trigger Monitor${RST} — read-only status check\n"
printf "Generated: %s\n" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')"


# ===== Trigger 1: WC 2026 model hit-rate =====
section "1. WC 2026 model hit-rate (Branch A/B/C decider)"
WC_VERDICT="not_ready"
WC_HIT_RATE=""

if [[ -f "$DB_PATH" ]]; then
  WC_STATS="$($VENV_PY -c "
import sqlite3
import sys
try:
    conn = sqlite3.connect('$DB_PATH')
    # Check wc_predictions table exists
    rows = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='wc_predictions'\").fetchall()
    if not rows:
        print('NO_TABLE')
        sys.exit(0)
    # Total + settled counts for season 2026
    total = conn.execute('SELECT COUNT(*) FROM wc_predictions WHERE season=2026').fetchone()[0]
    settled = conn.execute('SELECT COUNT(*) FROM wc_predictions WHERE season=2026 AND outcome IS NOT NULL').fetchone()[0]
    # Hit-rate (top-tip == actual)
    rows = conn.execute('''
        SELECT p_home, p_draw, p_away, outcome
        FROM wc_predictions
        WHERE season=2026 AND outcome IS NOT NULL
    ''').fetchall()
    hits = 0
    for ph, pd, pa, outc in rows:
        probs = (ph, pd, pa)
        pred = max(range(3), key=lambda i: probs[i])
        if pred == outc:
            hits += 1
    hit_rate = (hits / settled) if settled else 0
    print(f'{total} {settled} {hits} {hit_rate:.4f}')
except Exception as e:
    print(f'ERROR {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null)"

  if [[ "$WC_STATS" == "NO_TABLE" ]]; then
    note "wc_predictions table doesn't exist yet — will be created on first daily_wc_predict cron run"
  elif [[ -n "$WC_STATS" ]]; then
    TOTAL="$(echo "$WC_STATS" | awk '{print $1}')"
    SETTLED="$(echo "$WC_STATS" | awk '{print $2}')"
    HITS="$(echo "$WC_STATS" | awk '{print $3}')"
    WC_HIT_RATE="$(echo "$WC_STATS" | awk '{print $4}')"
    note "WC 2026 predictions: $TOTAL total ($SETTLED settled, $HITS hits)"
    if [[ "$SETTLED" -ge 32 ]]; then
      # 32 = roughly group stage + first round of KOs; reliable enough for verdict
      HR_PCT="$($VENV_PY -c "print(f'{$WC_HIT_RATE * 100:.1f}')")"
      if (( $(echo "$WC_HIT_RATE >= 0.55" | bc -l) )); then
        ok "hit-rate ${HR_PCT}% (≥55%) → ${BOLD}Branch A${RST} (national-team expansion + MCMC)"
        WC_VERDICT="A"
        TRIGGER_FIRED=1
      elif (( $(echo "$WC_HIT_RATE >= 0.45" | bc -l) )); then
        ok "hit-rate ${HR_PCT}% (45-55%) → ${BOLD}Branch B${RST} (domestic Layer B + Path 3+4)"
        WC_VERDICT="B"
        TRIGGER_FIRED=1
      else
        warn "hit-rate ${HR_PCT}% (<45%) → ${BOLD}Branch C${RST} (negative postmortem + Layer B + defensive)"
        WC_VERDICT="C"
        TRIGGER_FIRED=1
      fi
    elif [[ "$SETTLED" -gt 0 ]]; then
      HR_PCT="$($VENV_PY -c "print(f'{$WC_HIT_RATE * 100:.1f}')")"
      warn "$SETTLED settled (need ≥32 for reliable verdict). Current HR: ${HR_PCT}%"
    elif [[ "$TOTAL" -gt 0 ]]; then
      note "$TOTAL predictions recorded but none settled yet (tournament not started)"
    else
      note "no WC predictions recorded yet (first cron will land at 09:00 daily)"
    fi
  fi
else
  note "observation DB doesn't exist yet (cron hasn't run; expected before kickoff 2026-06-11)"
fi

# Also check filesystem reports as a fallback signal
N_WC_REPORTS=0
if [[ -d docs/wc ]]; then
  N_WC_REPORTS="$(find docs/wc -name 'wc_report_*.md' 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$N_WC_REPORTS" -gt 0 ]]; then
    LATEST="$(ls -t docs/wc/wc_report_*.md 2>/dev/null | head -1)"
    note "$N_WC_REPORTS daily report files; latest: $(basename "$LATEST")"
  fi
fi


# ===== Trigger 2: Layer A auto-T cycles =====
section "2. Layer A auto-T cycles (need ≥ 4 for credible verdict)"
N_CALIB_CYCLES=0
N_DEPLOY=0
N_ROLLBACK=0

if [[ -f "$DB_PATH" ]]; then
  CALIB_STATS="$($VENV_PY -c "
import sqlite3
try:
    conn = sqlite3.connect('$DB_PATH')
    rows = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='calibration_journal'\").fetchall()
    if not rows:
        print('NO_TABLE')
    else:
        total = conn.execute('SELECT COUNT(*) FROM calibration_journal').fetchone()[0]
        propose = conn.execute(\"SELECT COUNT(*) FROM calibration_journal WHERE action='propose'\").fetchone()[0]
        deploy = conn.execute(\"SELECT COUNT(*) FROM calibration_journal WHERE action='deploy'\").fetchone()[0]
        rollback = conn.execute(\"SELECT COUNT(*) FROM calibration_journal WHERE action='rollback'\").fetchone()[0]
        last_recorded = conn.execute('SELECT recorded_at FROM calibration_journal ORDER BY recorded_at DESC LIMIT 1').fetchone()
        last = last_recorded[0] if last_recorded else 'n/a'
        print(f'{total} {propose} {deploy} {rollback} {last}')
except Exception:
    pass
" 2>/dev/null)"

  if [[ "$CALIB_STATS" == "NO_TABLE" ]]; then
    note "calibration_journal table doesn't exist yet"
  elif [[ -n "$CALIB_STATS" ]]; then
    TOTAL="$(echo "$CALIB_STATS" | awk '{print $1}')"
    PROPOSE="$(echo "$CALIB_STATS" | awk '{print $2}')"
    DEPLOY="$(echo "$CALIB_STATS" | awk '{print $3}')"
    ROLLBACK="$(echo "$CALIB_STATS" | awk '{print $4}')"
    LAST="$(echo "$CALIB_STATS" | awk '{print $5}')"
    note "journal entries: $TOTAL total ($PROPOSE propose, $DEPLOY deploy, $ROLLBACK rollback)"
    note "last recorded: $LAST"
    N_DEPLOY=$DEPLOY
    N_ROLLBACK=$ROLLBACK
    # Cycles = propose entries (one per Monday cron firing)
    N_CALIB_CYCLES=$PROPOSE
  fi
else
  note "observation DB doesn't exist yet"
fi

# Count weekly report files as secondary signal
N_CALIB_REPORTS=0
if [[ -d docs/weekly ]]; then
  N_CALIB_REPORTS="$(find docs/weekly -name 'auto_calibration_*.md' 2>/dev/null | wc -l | tr -d ' ')"
fi
note "weekly report files: $N_CALIB_REPORTS in docs/weekly/auto_calibration_*"

if [[ "$N_CALIB_CYCLES" -ge 4 ]]; then
  ok "$N_CALIB_CYCLES cycles completed → Layer A trigger READY"
  TRIGGER_FIRED=1
  if [[ "$N_DEPLOY" -gt 0 || "$N_ROLLBACK" -gt 0 ]]; then
    hi "Layer A activity: $N_DEPLOY deploy(s), $N_ROLLBACK rollback(s) — read these in V10 retrospective"
  fi
else
  REMAINING=$((4 - N_CALIB_CYCLES))
  note "$REMAINING more Monday cycles needed before Layer A verdict is credible"
fi


# ===== Trigger 3: Lineup ROI 4-week verdict =====
section "3. Lineup ROI 4-week verdict (need ≥ 60 settlements per arm)"

if [[ -f "$DB_PATH" ]]; then
  ROI_STATS="$($VENV_PY -c "
import sqlite3
try:
    conn = sqlite3.connect('$DB_PATH')
    rows = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='settlements'\").fetchall()
    if not rows:
        print('NO_TABLE')
    else:
        total = conn.execute('SELECT COUNT(*) FROM settlements').fetchone()[0]
        # Settlements grouped by model_type (V5 W7 + post-V9 P1#17)
        rows = conn.execute('''
            SELECT COALESCE(rs.model_type, 'unknown') AS model_type, COUNT(*) AS n
            FROM settlements s
            JOIN parlay_recommendations pr ON s.recommendation_id = pr.recommendation_id
            JOIN recommendation_sessions rs ON pr.session_id = rs.session_id
            GROUP BY rs.model_type
        ''').fetchall()
        per_arm = ' / '.join(f'{r[0]}={r[1]}' for r in rows) if rows else 'no arms'
        print(f'{total}|{per_arm}')
except Exception as e:
    print(f'ERROR {e}')
" 2>/dev/null)"

  if [[ "$ROI_STATS" == "NO_TABLE" ]]; then
    note "settlements table doesn't exist yet"
  elif [[ -n "$ROI_STATS" ]]; then
    TOTAL_SETTLE="${ROI_STATS%%|*}"
    PER_ARM="${ROI_STATS#*|}"
    note "settlements: $TOTAL_SETTLE total ($PER_ARM)"
    if [[ "$TOTAL_SETTLE" -ge 60 ]]; then
      ok "$TOTAL_SETTLE settlements → enough to read 4-week ROI verdict"
      hi "next step: PYTHONPATH=apps/api/src $VENV_PY -m nutmeg.v4.cli.ab_report --weeks 4 --db $DB_PATH"
      TRIGGER_FIRED=1
    else
      REMAINING=$((60 - TOTAL_SETTLE))
      note "$REMAINING more settlements needed (cron writes ~5-15/day on EPL/La Liga match days)"
    fi
  fi
else
  note "observation DB doesn't exist yet"
fi


# ===== Trigger 4: Cross-source caveat =====
section "4. Cross-source caveat (need ROI gap ≤ 30pp from P1#19 gate)"
N_GATE_REPORTS=0
if [[ -d docs/weekly ]]; then
  N_GATE_REPORTS="$(find docs/weekly -name 'p1_19_gate_*.md' 2>/dev/null | wc -l | tr -d ' ')"
fi
note "gate report files: $N_GATE_REPORTS in docs/weekly/p1_19_gate_*"

if [[ "$N_GATE_REPORTS" -ge 1 ]]; then
  LATEST_GATE="$(ls -t docs/weekly/p1_19_gate_*.md 2>/dev/null | head -1)"
  if [[ -n "$LATEST_GATE" ]]; then
    note "latest gate: $(basename "$LATEST_GATE")"
    # Try to grep the gap number — pattern depends on the gate output format
    GAP_LINE="$(grep -E 'gap|tolerance|ROI Δ' "$LATEST_GATE" 2>/dev/null | head -1)"
    if [[ -n "$GAP_LINE" ]]; then
      note "  $GAP_LINE"
    fi
  fi
fi
note "this trigger is informational — Branch decision rests on triggers 1-3"


# ===== Branch recommendation =====
section "Branch recommendation"

case "$WC_VERDICT" in
  A)
    hi "WC HR ≥ 55% → ${BOLD}Branch A${RST} (national-team expansion + MCMC limited)"
    printf "    Phase 1 next steps:\n"
    printf "    - W1: national-team competition registry\n"
    printf "    - W2: MCMC Bayesian Poisson on national-team data ONLY\n"
    printf "    - W3: dashboard 国家队 tab + Layer B groundwork\n"
    printf "    - W4: ship v11.0-shipped\n"
    EXIT_CODE=0
    ;;
  B)
    hi "WC HR 45-55% → ${BOLD}Branch B${RST} (domestic Layer B + Path 3+4)"
    printf "    Phase 1 next steps:\n"
    printf "    - W1: Layer B (quarterly auto-retrain pipeline)\n"
    printf "    - W2: Path 3 stadium home-advantage ablation\n"
    printf "    - W3: Path 4 fatigue features ablation\n"
    printf "    - W4: ship v11.0-shipped\n"
    EXIT_CODE=0
    ;;
  C)
    hi "WC HR < 45% → ${BOLD}Branch C${RST} (negative postmortem + Layer B + defensive)"
    printf "    Phase 1 next steps:\n"
    printf "    - W1: WC failure postmortem doc\n"
    printf "    - W2: dashboard WC tab → 'experimental' label\n"
    printf "    - W3: Layer B (still ships)\n"
    printf "    - W4: Path 5 Pinnacle blend on domestic + ship\n"
    EXIT_CODE=0
    ;;
  *)
    if [[ "$TRIGGER_FIRED" -eq 1 ]]; then
      hi "Layer A or Lineup ROI trigger fired, but WC verdict not yet in"
      printf "    Default: ${BOLD}wait for WC verdict${RST} (primary decider; final 2026-07-19)\n"
      printf "    Or open V11 with Branch B as default if WC tournament delayed\n"
      EXIT_CODE=0
    else
      printf "  ${YEL}${BOLD}NOT READY${RST} — no triggers fired yet\n"
      printf "  Phase 0 status: waiting for data\n"
      printf "  Next check: weekly (recommended every Monday after the 03:00 calibration_check cron)\n"
    fi
    ;;
esac


# ===== Summary =====
section "Summary"
case $EXIT_CODE in
  0)
    printf "${GRN}${BOLD}V11 W1 UNBLOCKED${RST} — read the recommendation above + run Phase 1 decision week.\n"
    ;;
  1)
    printf "${RED}${BOLD}ERROR${RST} — at least one critical check failed (see above).\n"
    ;;
  2)
    printf "${YEL}${BOLD}WAITING${RST} — Phase 0 ongoing. Run this script weekly to track triggers.\n"
    ;;
esac

exit $EXIT_CODE
