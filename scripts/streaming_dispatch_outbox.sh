#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PSQL="${ROOT_DIR}/scripts/storage_psql.sh"
BATCH_SIZE="${BATCH_SIZE:-20}"

echo "Dispatching up to ${BATCH_SIZE} pending outbox events..."
"${PSQL}" -P pager=off -v batch_size="${BATCH_SIZE}" <<'SQL'
SELECT row_to_json(e)
FROM dequeue_outbox_events(:batch_size) AS e;
SQL

echo
echo "Outbox status counts after dispatch:"
"${PSQL}" -P pager=off <<'SQL'
SELECT status, COUNT(*) AS count
FROM event_outbox
GROUP BY status
ORDER BY status;
SQL
