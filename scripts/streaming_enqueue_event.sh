#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PSQL="${ROOT_DIR}/scripts/storage_psql.sh"

EVENT_TYPE="${EVENT_TYPE:-sensor.reading.ingested}"
AGGREGATE_TYPE="${AGGREGATE_TYPE:-asset}"
AGGREGATE_ID="${AGGREGATE_ID:-asset_bridge_zonea_1}"
EVENT_VERSION="${EVENT_VERSION:-v1}"
TRACE_ID="${TRACE_ID:-manual-trace-$(date +%s)}"
PAYLOAD_FILE="${1:-${ROOT_DIR}/data-platform/streaming/examples/sensor_reading_ingested.sample.json}"

if [ ! -f "${PAYLOAD_FILE}" ]; then
  echo "Payload file not found: ${PAYLOAD_FILE}" >&2
  exit 1
fi

PAYLOAD_JSON="$(cat "${PAYLOAD_FILE}")"

echo "Enqueuing outbox event (${EVENT_TYPE}) from ${PAYLOAD_FILE}..."
"${PSQL}" \
  -v event_type="${EVENT_TYPE}" \
  -v aggregate_type="${AGGREGATE_TYPE}" \
  -v aggregate_id="${AGGREGATE_ID}" \
  -v event_version="${EVENT_VERSION}" \
  -v trace_id="${TRACE_ID}" \
  -v payload_json="${PAYLOAD_JSON}" <<'SQL'
INSERT INTO event_outbox (
  aggregate_type,
  aggregate_id,
  event_type,
  event_version,
  payload,
  status,
  trace_id
)
VALUES (
  :'aggregate_type',
  :'aggregate_id',
  :'event_type',
  :'event_version',
  :'payload_json'::jsonb,
  'pending',
  :'trace_id'
)
RETURNING id, aggregate_type, aggregate_id, event_type, status, created_at, trace_id;
SQL
