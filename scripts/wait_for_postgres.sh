#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="${INFRAGUARD_DB_CONTAINER:-infraguard-postgres}"
DB_USER="${POSTGRES_USER:-infraguard}"
DB_NAME="${POSTGRES_DB:-infraguard}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-120}"

echo "Waiting for PostgreSQL to become ready..."
start_ts="$(date +%s)"

while true; do
  if ! docker inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
    now_ts="$(date +%s)"
    elapsed="$((now_ts - start_ts))"
    if [ "${elapsed}" -ge "${MAX_WAIT_SECONDS}" ]; then
      echo "PostgreSQL container not found after ${MAX_WAIT_SECONDS}s: ${CONTAINER_NAME}" >&2
      exit 1
    fi

    sleep 2
    continue
  fi

  if docker exec "${CONTAINER_NAME}" pg_isready -U "${DB_USER}" -d "${DB_NAME}" >/dev/null 2>&1; then
    echo "PostgreSQL is ready."
    exit 0
  fi

  now_ts="$(date +%s)"
  elapsed="$((now_ts - start_ts))"
  if [ "${elapsed}" -ge "${MAX_WAIT_SECONDS}" ]; then
    echo "Timed out waiting for PostgreSQL after ${MAX_WAIT_SECONDS}s." >&2
    exit 1
  fi

  sleep 2
done
