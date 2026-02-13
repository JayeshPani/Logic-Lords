#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${INFRAGUARD_DB_CONTAINER:-infraguard-postgres}"

echo "Stopping data-platform services..."
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  docker rm -f "${CONTAINER_NAME}" >/dev/null
  echo "Removed ${CONTAINER_NAME}"
else
  echo "Container not found: ${CONTAINER_NAME}"
fi
