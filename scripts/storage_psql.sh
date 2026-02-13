#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="${INFRAGUARD_DB_CONTAINER:-infraguard-postgres}"
DB_USER="${POSTGRES_USER:-infraguard}"
DB_NAME="${POSTGRES_DB:-infraguard}"

exec docker exec -i "${CONTAINER_NAME}" \
  psql -v ON_ERROR_STOP=1 -U "${DB_USER}" -d "${DB_NAME}" "$@"
