#!/usr/bin/env bash
set -euo pipefail

TARGET="${NUTMEG_DEPLOY_TARGET:-root@156.236.76.121}"
REMOTE_DIR="${NUTMEG_REMOTE_DIR:-/opt/nutmeg}"
CRON_SCHEDULE="${NUTMEG_PROVIDER_RUNTIME_CRON_SCHEDULE:-*/30 * * * *}"
LIVE_PROBE="${NUTMEG_PROVIDER_RUNTIME_LIVE_PROBE:-false}"
INCIDENT_THRESHOLD="${NUTMEG_PROVIDER_RUNTIME_INCIDENT_THRESHOLD:-P1}"
RETENTION_DAYS="${NUTMEG_PROVIDER_RUNTIME_RETENTION_DAYS:-90}"
CRON_FILE="/etc/cron.d/nutmeg-provider-runtime-monitoring"
CRON_SCHEDULE_B64="$(printf '%s' "$CRON_SCHEDULE" | base64 | tr -d '\n')"

ssh -o BatchMode=yes "$TARGET" bash -s -- \
  "$REMOTE_DIR" "$CRON_SCHEDULE_B64" "$LIVE_PROBE" "$INCIDENT_THRESHOLD" "$RETENTION_DAYS" "$CRON_FILE" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"
CRON_SCHEDULE="$(printf '%s' "$2" | base64 -d)"
LIVE_PROBE="$3"
INCIDENT_THRESHOLD="$4"
RETENTION_DAYS="$5"
CRON_FILE="$6"

cd "$REMOTE_DIR"
mkdir -p "$REMOTE_DIR/logs"

cat > "$CRON_FILE" <<CRON
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
$CRON_SCHEDULE root cd $REMOTE_DIR && NUTMEG_PROVIDER_RUNTIME_LIVE_PROBE=$LIVE_PROBE NUTMEG_PROVIDER_RUNTIME_RECORD_INCIDENT=true NUTMEG_PROVIDER_RUNTIME_INCIDENT_THRESHOLD=$INCIDENT_THRESHOLD NUTMEG_PROVIDER_RUNTIME_RETENTION_DAYS=$RETENTION_DAYS NUTMEG_PROVIDER_RUNTIME_INCIDENT_SOURCE=vps_cron $REMOTE_DIR/scripts/provider-runtime-monitoring-local.sh $REMOTE_DIR >> $REMOTE_DIR/logs/provider-runtime-monitoring.log 2>&1
CRON

chmod 0644 "$CRON_FILE"

if command -v systemctl >/dev/null 2>&1; then
  systemctl reload cron 2>/dev/null || systemctl reload crond 2>/dev/null || true
fi

echo "nutmeg_provider_runtime_monitoring_cron_installed $CRON_FILE"
cat "$CRON_FILE"
REMOTE
