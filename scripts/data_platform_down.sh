#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${INFRAGUARD_DB_CONTAINER:-infraguard-postgres}"
VOLUME_NAME="${INFRAGUARD_DB_VOLUME:-infraguard_postgres_data}"
REMOVE_VOLUME="${INFRAGUARD_DB_REMOVE_VOLUME:-0}"

echo "Stopping data-platform services..."
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  docker rm -f "${CONTAINER_NAME}" >/dev/null
  echo "Removed ${CONTAINER_NAME}"
else
  echo "Container not found: ${CONTAINER_NAME}"
fi

if [ "${REMOVE_VOLUME}" = "1" ]; then
  if docker volume ls --format '{{.Name}}' | grep -q "^${VOLUME_NAME}$"; then
    docker volume rm "${VOLUME_NAME}" >/dev/null
    echo "Removed volume ${VOLUME_NAME}"
  else
    echo "Volume not found: ${VOLUME_NAME}"
  fi
fi
