#!/usr/bin/env bash
# post-v9 P1#16 — launch the local FastAPI server for the dashboard.
#
# Convenience wrapper around uvicorn so you don't have to remember
# PYTHONPATH + the right module path.
#
# Usage:
#   ./scripts/run_local_server.sh           # foreground, default port 8000
#   ./scripts/run_local_server.sh 8080      # foreground, custom port
#   ./scripts/run_local_server.sh 8000 lan  # bind 0.0.0.0 so phone on LAN can reach it
#
# Then visit http://127.0.0.1:8000/api/v4/dashboard

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PORT="${1:-8000}"
HOST="127.0.0.1"
if [[ "${2:-}" == "lan" ]]; then
  HOST="0.0.0.0"
  echo "ℹ Binding 0.0.0.0 — phone on same WiFi can reach the dashboard."
  # Show the LAN IP for convenience
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo '?')"
  if [[ "$LAN_IP" != "?" ]]; then
    echo "  Dashboard URL from your phone: http://$LAN_IP:$PORT/api/v4/dashboard"
  fi
fi

# Source .env so NUTMEG_API_FOOTBALL_KEY + NUTMEG_V4_OBSERVATION_DB are set
if [[ -f .env ]]; then
  set -a; source .env; set +a
fi

# Default the observation DB if not in .env
export NUTMEG_V4_OBSERVATION_DB="${NUTMEG_V4_OBSERVATION_DB:-$REPO_ROOT/data/v4_observation.db}"
export PYTHONPATH="$REPO_ROOT/apps/api/src"

echo "Starting Nutmeg API on http://$HOST:$PORT (Ctrl-C to stop)"
echo "  Dashboard: http://$HOST:$PORT/api/v4/dashboard"
echo "  Health:    http://$HOST:$PORT/api/v4/health"
echo "  Observation DB: $NUTMEG_V4_OBSERVATION_DB"
echo ""

exec .venv/bin/uvicorn nutmeg.main:app --host "$HOST" --port "$PORT" --reload
