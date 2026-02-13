-- InfraGuard index contract v1
-- Target: PostgreSQL 16+

BEGIN;

CREATE INDEX IF NOT EXISTS idx_assets_zone_status
  ON assets (zone, status);

CREATE INDEX IF NOT EXISTS idx_sensor_nodes_asset_id
  ON sensor_nodes (asset_id);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_asset_captured_at_desc
  ON sensor_readings (asset_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_sensor_captured_at_desc
  ON sensor_readings (sensor_node_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_risk_assessments_asset_evaluated_at_desc
  ON risk_assessments (asset_id, evaluated_at DESC);

CREATE INDEX IF NOT EXISTS idx_failure_forecasts_asset_generated_at_desc
  ON failure_forecasts (asset_id, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_inspection_tickets_asset_status
  ON inspection_tickets (asset_id, status);

CREATE INDEX IF NOT EXISTS idx_maintenance_actions_asset_status
  ON maintenance_actions (asset_id, status);

CREATE INDEX IF NOT EXISTS idx_verification_records_status_created_at
  ON verification_records (verification_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_event_outbox_status_next_attempt
  ON event_outbox (status, next_attempt_at);

COMMIT;
