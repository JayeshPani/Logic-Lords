#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PSQL="${ROOT_DIR}/scripts/storage_psql.sh"

echo "Storage migration versions:"
"${PSQL}" -P pager=off -c "SELECT version, description, applied_at FROM schema_migrations ORDER BY applied_at;"

echo
echo "Core table row counts:"
"${PSQL}" -P pager=off <<'SQL'
SELECT 'assets' AS table_name, COUNT(*) AS row_count FROM assets
UNION ALL
SELECT 'sensor_nodes', COUNT(*) FROM sensor_nodes
UNION ALL
SELECT 'sensor_readings', COUNT(*) FROM sensor_readings
UNION ALL
SELECT 'event_outbox_pending', COUNT(*) FROM event_outbox WHERE status = 'pending'
UNION ALL
SELECT 'event_outbox_published', COUNT(*) FROM event_outbox WHERE status = 'published'
UNION ALL
SELECT 'event_outbox_failed', COUNT(*) FROM event_outbox WHERE status = 'failed'
ORDER BY table_name;
SQL

echo
echo "Outbox backlog metrics:"
"${PSQL}" -P pager=off <<'SQL'
SELECT status, event_count, oldest_event, newest_event
FROM outbox_status_metrics();
SQL
