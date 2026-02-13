#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="${INFRAGUARD_DB_CONTAINER:-infraguard-postgres}"
IMAGE="${INFRAGUARD_DB_IMAGE:-docker.io/library/postgres:16}"
DB_USER="${POSTGRES_USER:-infraguard}"
DB_PASSWORD="${POSTGRES_PASSWORD:-infraguard}"
DB_NAME="${POSTGRES_DB:-infraguard}"
DB_PORT="${INFRAGUARD_DB_PORT:-55432}"
VOLUME_NAME="${INFRAGUARD_DB_VOLUME:-infraguard_postgres_data}"

if docker inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
  if [ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER_NAME}")" = "true" ]; then
    echo "PostgreSQL container already running: ${CONTAINER_NAME}"
  else
    echo "Starting existing PostgreSQL container: ${CONTAINER_NAME}"
    docker start "${CONTAINER_NAME}" >/dev/null
  fi
else
  # Defensive cleanup for daemon states where name conflicts appear but lookup is stale.
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  echo "Creating PostgreSQL container: ${CONTAINER_NAME}"
  docker run -d \
    --name "${CONTAINER_NAME}" \
    -e "POSTGRES_USER=${DB_USER}" \
    -e "POSTGRES_PASSWORD=${DB_PASSWORD}" \
    -e "POSTGRES_DB=${DB_NAME}" \
    -p "${DB_PORT}:5432" \
    -v "${VOLUME_NAME}:/var/lib/postgresql/data" \
    "${IMAGE}" >/dev/null
fi

"${ROOT_DIR}/scripts/wait_for_postgres.sh"
docker ps --filter "name=^/${CONTAINER_NAME}$" --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
