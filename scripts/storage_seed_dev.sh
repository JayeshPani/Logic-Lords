#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PSQL="${ROOT_DIR}/scripts/storage_psql.sh"

echo "Seeding development asset/sensor/outbox rows..."
"${PSQL}" <<'SQL'
WITH upsert_asset AS (
  INSERT INTO assets (
    asset_id, name, asset_type, status, zone, latitude, longitude, metadata, installed_at
  )
  VALUES (
    'asset_bridge_zonea_1',
    'Bridge Zone A Span 1',
    'bridge',
    'active',
    'zone_a',
    19.0760,
    72.8777,
    '{"owner":"city_ops","criticality":"high"}'::jsonb,
    now() - interval '365 days'
  )
  ON CONFLICT (asset_id) DO UPDATE SET
    name = EXCLUDED.name,
    status = EXCLUDED.status,
    zone = EXCLUDED.zone
  RETURNING id
),
resolved_asset AS (
  SELECT id FROM upsert_asset
  UNION ALL
  SELECT a.id FROM assets a WHERE a.asset_id = 'asset_bridge_zonea_1'
  LIMIT 1
)
INSERT INTO sensor_nodes (
  sensor_id,
  asset_id,
  gateway_id,
  firmware_version,
  status,
  calibration,
  installed_at,
  last_seen_at
)
SELECT
  'sensor_bridge_zonea_1',
  ra.id,
  'gateway_zonea_1',
  'v1.0.0',
  'active',
  '{"strain_offset":0.0,"vibration_gain":1.0}'::jsonb,
  now() - interval '300 days',
  now()
FROM resolved_asset ra
ON CONFLICT (sensor_id) DO UPDATE SET
  status = EXCLUDED.status,
  firmware_version = EXCLUDED.firmware_version,
  last_seen_at = EXCLUDED.last_seen_at;

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
  'asset',
  'asset_bridge_zonea_1',
  'sensor.reading.ingested',
  'v1',
  jsonb_build_object(
    'asset_id', 'asset_bridge_zonea_1',
    'sensor_id', 'sensor_bridge_zonea_1',
    'captured_at', now(),
    'strain', 512.0,
    'vibration', 1.12,
    'temperature', 31.0,
    'humidity', 71.2,
    'tilt', 0.03
  ),
  'pending',
  'seed-trace-asset-bridge-zonea-1'
);
SQL

echo "Seed completed."
