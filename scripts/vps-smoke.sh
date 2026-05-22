#!/usr/bin/env bash
set -euo pipefail

TARGET="${NUTMEG_DEPLOY_TARGET:-root@156.236.76.121}"
REMOTE_DIR="${NUTMEG_REMOTE_DIR:-/opt/nutmeg}"
COMPOSE_FILE="${NUTMEG_COMPOSE_FILE:-docker-compose.vps.yml}"
PUBLIC_BASE_URL="${NUTMEG_PUBLIC_BASE_URL:-https://goodmood.mcpup.top}"
CHECK_CAUSA="${NUTMEG_CHECK_CAUSA:-1}"

ssh -o BatchMode=yes "$TARGET" bash -s -- \
  "$REMOTE_DIR" "$COMPOSE_FILE" "$CHECK_CAUSA" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"
COMPOSE_FILE="$2"
CHECK_CAUSA="$3"

cd "$REMOTE_DIR"

docker compose -f "$COMPOSE_FILE" ps
curl -fsS http://127.0.0.1:18000/api/v1/health
printf "\n"
curl -fsS http://127.0.0.1:18000/api/v1/fixtures \
  | python3 -c 'import json,sys; data=json.load(sys.stdin); print("fixtures", len(data["items"]))'
curl -fsS 'http://127.0.0.1:18000/api/v1/accuracy/summary?market=1x2' \
  | python3 -c 'import json,sys; data=json.load(sys.stdin); print("accuracy_sample_size", data["sample_size"])'
curl -fsS http://127.0.0.1:13000/dashboard \
  | python3 -c 'import sys; html=sys.stdin.read(); print("dashboard_bytes", len(html))'

if [ "$CHECK_CAUSA" = "1" ]; then
  if docker ps -a --format '{{.Names}}' | grep -qi causa; then
    echo "unexpected causa container found" >&2
    exit 1
  fi
fi
REMOTE

if [ -n "$PUBLIC_BASE_URL" ]; then
  curl -fsS --connect-timeout 15 "$PUBLIC_BASE_URL/api/v1/health"
  printf "\n"
  curl -fsS --connect-timeout 15 "$PUBLIC_BASE_URL/dashboard" \
    | python3 -c 'import sys; html=sys.stdin.read(); print("public_dashboard_bytes", len(html))'
fi
