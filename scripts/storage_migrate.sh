#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PSQL="${ROOT_DIR}/scripts/storage_psql.sh"

"${ROOT_DIR}/scripts/wait_for_postgres.sh"

echo "Applying storage runtime bootstrap migration..."
"${PSQL}" < "${ROOT_DIR}/data-platform/storage/migrations/001_storage_runtime.sql"

has_schema="$("${PSQL}" -tA -c "SELECT CASE WHEN to_regclass('public.assets') IS NULL THEN 0 ELSE 1 END;")"
if [ "${has_schema}" = "0" ]; then
  echo "Applying database contract schema (contracts/database/schema.v1.sql)..."
  "${PSQL}" < "${ROOT_DIR}/contracts/database/schema.v1.sql"
  "${PSQL}" -c "INSERT INTO schema_migrations(version, description) VALUES ('contract_schema_v1', 'contracts/database/schema.v1.sql') ON CONFLICT (version) DO NOTHING;"
else
  echo "Contract schema already present; skipping schema.v1.sql"
fi

echo "Applying contract indexes (contracts/database/indexes.v1.sql)..."
"${PSQL}" < "${ROOT_DIR}/contracts/database/indexes.v1.sql"
"${PSQL}" -c "INSERT INTO schema_migrations(version, description) VALUES ('contract_indexes_v1', 'contracts/database/indexes.v1.sql') ON CONFLICT (version) DO NOTHING;"

echo "Applying streaming runtime migration..."
"${PSQL}" < "${ROOT_DIR}/data-platform/streaming/migrations/001_outbox_runtime.sql"
"${PSQL}" -c "INSERT INTO schema_migrations(version, description) VALUES ('streaming_runtime_v1', 'data-platform/streaming/migrations/001_outbox_runtime.sql') ON CONFLICT (version) DO NOTHING;"

echo "Storage/streaming migrations applied successfully."
