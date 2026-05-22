#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${NUTMEG_SMOKE_CONTAINER_NAME:-nutmeg-postgres-smoke-$$}"
IMAGE="${NUTMEG_SMOKE_POSTGRES_IMAGE:-postgres:16}"
DATABASE_NAME="${NUTMEG_SMOKE_DATABASE:-nutmeg}"
DATABASE_USER="${NUTMEG_SMOKE_USER:-nutmeg}"
DATABASE_PASSWORD="${NUTMEG_SMOKE_PASSWORD:-nutmeg}"
PYTHON_BIN="${PYTHON:-.venv/bin/python}"

cleanup() {
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}

trap cleanup EXIT

docker run \
  --name "${CONTAINER_NAME}" \
  -e POSTGRES_USER="${DATABASE_USER}" \
  -e POSTGRES_PASSWORD="${DATABASE_PASSWORD}" \
  -e POSTGRES_DB="${DATABASE_NAME}" \
  -p 127.0.0.1::5432 \
  -d "${IMAGE}" >/dev/null

for _ in $(seq 1 30); do
  if docker exec "${CONTAINER_NAME}" pg_isready \
    -U "${DATABASE_USER}" \
    -d "${DATABASE_NAME}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker exec "${CONTAINER_NAME}" pg_isready \
  -U "${DATABASE_USER}" \
  -d "${DATABASE_NAME}" >/dev/null 2>&1; then
  echo "Postgres smoke container did not become ready." >&2
  exit 1
fi

HOST_PORT="$(docker port "${CONTAINER_NAME}" 5432/tcp | head -n 1 | sed -E 's/.*:([0-9]+)$/\1/')"
export NUTMEG_DATABASE_URL="postgresql://${DATABASE_USER}:${DATABASE_PASSWORD}@localhost:${HOST_PORT}/${DATABASE_NAME}"

"${PYTHON_BIN}" -m nutmeg.accuracy.postgres_smoke "$@"
