#!/usr/bin/env bash
set -euo pipefail

TARGET="${NUTMEG_DEPLOY_TARGET:-root@156.236.76.121}"
REMOTE_DIR="${NUTMEG_REMOTE_DIR:-/opt/nutmeg}"
COMPOSE_FILE="${NUTMEG_COMPOSE_FILE:-docker-compose.vps.yml}"
DEPLOY_NGINX="${NUTMEG_DEPLOY_NGINX:-1}"
SEED_ACCURACY="${NUTMEG_SEED_ACCURACY:-0}"
PUBLIC_BASE_URL="${NUTMEG_PUBLIC_BASE_URL:-https://goodmood.mcpup.top}"

RSYNC_EXCLUDES=(
  --exclude ".git"
  --exclude ".env"
  --exclude ".venv"
  --exclude ".mypy_cache"
  --exclude ".pytest_cache"
  --exclude ".ruff_cache"
  --exclude "**/__pycache__"
  --exclude "apps/web/node_modules"
  --exclude "apps/web/.next"
  --exclude "apps/web/test-results"
  --exclude "apps/web/playwright-report"
  --exclude "apps/web/tsconfig.tsbuildinfo"
)

ssh -o BatchMode=yes "$TARGET" "mkdir -p '$REMOTE_DIR' /opt/nutmeg-backups"
rsync -az --delete "${RSYNC_EXCLUDES[@]}" ./ "$TARGET:$REMOTE_DIR/"

ssh -o BatchMode=yes "$TARGET" bash -s -- \
  "$REMOTE_DIR" "$COMPOSE_FILE" "$DEPLOY_NGINX" "$SEED_ACCURACY" <<'REMOTE'
set -euo pipefail

REMOTE_DIR="$1"
COMPOSE_FILE="$2"
DEPLOY_NGINX="$3"
SEED_ACCURACY="$4"

cd "$REMOTE_DIR"

if [ -f "$COMPOSE_FILE" ]; then
  mkdir -p /opt/nutmeg-backups
  tar -C "$(dirname "$REMOTE_DIR")" \
    -czf "/opt/nutmeg-backups/nutmeg-$(date +%Y%m%d%H%M%S).tgz" \
    "$(basename "$REMOTE_DIR")" >/dev/null 2>&1 || true
fi

if [ ! -f .env ]; then
  {
    printf "NUTMEG_ADMIN_API_TOKEN=%s\n" "$(openssl rand -hex 24)"
    printf "NUTMEG_PROVIDER_OPS_UI_TOKEN=%s\n" "$(openssl rand -hex 24)"
  } > .env
  chmod 600 .env
fi

if ! grep -q "^NUTMEG_PROVIDER_OPS_UI_TOKEN=" .env; then
  printf "NUTMEG_PROVIDER_OPS_UI_TOKEN=%s\n" "$(openssl rand -hex 24)" >> .env
  chmod 600 .env
fi

docker compose -f "$COMPOSE_FILE" build --pull
docker compose -f "$COMPOSE_FILE" up -d postgres redis
docker compose -f "$COMPOSE_FILE" exec -T postgres sh -lc '
  for migration in /docker-entrypoint-initdb.d/*.sql; do
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$migration"
  done
' < /dev/null
docker compose -f "$COMPOSE_FILE" up -d --force-recreate api web

if [ "$DEPLOY_NGINX" = "1" ]; then
  mkdir -p /opt/nutmeg-backups/nginx
  if [ -f /etc/nginx/sites-available/goodmood ]; then
    cp /etc/nginx/sites-available/goodmood \
      "/opt/nutmeg-backups/nginx/goodmood.$(date +%Y%m%d%H%M%S).conf"
  fi
  cp deploy/nginx/goodmood.mcpup.top.conf /etc/nginx/sites-available/goodmood
  ln -sfn /etc/nginx/sites-available/goodmood /etc/nginx/sites-enabled/goodmood
  nginx -t
  systemctl reload nginx
fi

if [ "$SEED_ACCURACY" = "1" ]; then
  docker compose -f "$COMPOSE_FILE" exec -T api \
    python -m nutmeg.accuracy.local_postgres_runner < /dev/null
fi

docker compose -f "$COMPOSE_FILE" ps
for attempt in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18000/api/v1/health >/tmp/nutmeg-api-health.json 2>/dev/null; then
    cat /tmp/nutmeg-api-health.json
    break
  fi
  if [ "$attempt" = "30" ]; then
    echo "Nutmeg API did not become healthy" >&2
    exit 1
  fi
  sleep 1
done
printf "\n"
REMOTE

if [ -n "$PUBLIC_BASE_URL" ]; then
  curl -fsS --connect-timeout 15 "$PUBLIC_BASE_URL/api/v1/health"
  printf "\n"
fi
