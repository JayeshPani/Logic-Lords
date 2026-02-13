-- InfraGuard relational schema contract v1
-- Target: PostgreSQL 16+

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Shared trigger for mutable tables.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id text NOT NULL UNIQUE
    CHECK (asset_id ~ '^asset_[a-z0-9]+_[a-z0-9]+_[0-9]+$'),
  name text NOT NULL,
  asset_type text NOT NULL
    CHECK (asset_type IN ('bridge', 'road', 'tunnel', 'flyover', 'other')),
  status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'maintenance', 'retired')),
  zone text NOT NULL,
  latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  installed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sensor_nodes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sensor_id text NOT NULL UNIQUE
    CHECK (sensor_id ~ '^sensor_[a-z0-9]+_[a-z0-9]+_[0-9]+$'),
  asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
  gateway_id text,
  firmware_version text,
  status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'inactive', 'faulty', 'decommissioned')),
  calibration jsonb NOT NULL DEFAULT '{}'::jsonb,
  installed_at timestamptz,
  last_seen_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Append-only time-series table.
CREATE TABLE IF NOT EXISTS sensor_readings (
  id bigserial PRIMARY KEY,
  reading_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
  sensor_node_id uuid NOT NULL REFERENCES sensor_nodes(id) ON DELETE RESTRICT,
  captured_at timestamptz NOT NULL,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  sequence_no bigint,
  strain double precision NOT NULL,
  vibration double precision NOT NULL,
  temperature double precision NOT NULL,
  humidity double precision NOT NULL CHECK (humidity BETWEEN 0 AND 100),
  tilt double precision NOT NULL,
  raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  trace_id text,
  produced_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Append-only risk evaluation snapshots.
CREATE TABLE IF NOT EXISTS risk_assessments (
  id bigserial PRIMARY KEY,
  assessment_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
  evaluated_at timestamptz NOT NULL,
  health_score numeric(5,4) NOT NULL CHECK (health_score BETWEEN 0 AND 1),
  severity text NOT NULL CHECK (severity IN ('healthy', 'watch', 'warning', 'critical')),
  mechanical_stress numeric(5,4) NOT NULL CHECK (mechanical_stress BETWEEN 0 AND 1),
  thermal_stress numeric(5,4) NOT NULL CHECK (thermal_stress BETWEEN 0 AND 1),
  fatigue numeric(5,4) NOT NULL CHECK (fatigue BETWEEN 0 AND 1),
  environmental_exposure numeric(5,4) NOT NULL CHECK (environmental_exposure BETWEEN 0 AND 1),
  source_version text NOT NULL DEFAULT 'v1',
  trace_id text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (asset_id, evaluated_at, source_version)
);

-- Append-only forecast snapshots.
CREATE TABLE IF NOT EXISTS failure_forecasts (
  id bigserial PRIMARY KEY,
  forecast_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
  generated_at timestamptz NOT NULL,
  horizon_hours integer NOT NULL DEFAULT 72 CHECK (horizon_hours BETWEEN 1 AND 168),
  failure_probability numeric(5,4) NOT NULL CHECK (failure_probability BETWEEN 0 AND 1),
  confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  model_name text NOT NULL,
  model_version text NOT NULL,
  trace_id text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (asset_id, generated_at, horizon_hours, model_version)
);

CREATE TABLE IF NOT EXISTS inspection_tickets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id text NOT NULL UNIQUE
    CHECK (ticket_id ~ '^insp_[0-9]{8}_[0-9]+$'),
  asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
  priority text NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')),
  reason text NOT NULL,
  status text NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'assigned', 'in_progress', 'completed', 'cancelled')),
  opened_at timestamptz NOT NULL DEFAULT now(),
  assigned_to text,
  due_at timestamptz,
  closed_at timestamptz,
  trigger_event_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS maintenance_actions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  maintenance_id text NOT NULL UNIQUE
    CHECK (maintenance_id ~ '^mnt_[0-9]{8}_[0-9]+$'),
  asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
  inspection_ticket_id uuid REFERENCES inspection_tickets(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'planned'
    CHECK (status IN ('planned', 'active', 'completed', 'verified', 'failed')),
  performed_by text,
  summary text,
  started_at timestamptz,
  completed_at timestamptz,
  pre_repair_risk_score numeric(5,4) CHECK (pre_repair_risk_score BETWEEN 0 AND 1),
  post_repair_risk_score numeric(5,4) CHECK (post_repair_risk_score BETWEEN 0 AND 1),
  report_uri text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS verification_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  maintenance_action_id uuid NOT NULL UNIQUE REFERENCES maintenance_actions(id) ON DELETE CASCADE,
  maintenance_id text NOT NULL
    CHECK (maintenance_id ~ '^mnt_[0-9]{8}_[0-9]+$'),
  asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
  verification_status text NOT NULL DEFAULT 'pending'
    CHECK (verification_status IN ('pending', 'submitted', 'confirmed', 'failed')),
  evidence_hash text NOT NULL CHECK (evidence_hash ~ '^0x[0-9a-fA-F]{64}$'),
  tx_hash text CHECK (tx_hash ~ '^0x[0-9a-fA-F]{64}$'),
  network text NOT NULL,
  contract_address text NOT NULL CHECK (contract_address ~ '^0x[0-9a-fA-F]{40}$'),
  chain_id bigint NOT NULL CHECK (chain_id > 0),
  block_number bigint CHECK (block_number >= 0),
  failure_reason text,
  submitted_at timestamptz,
  confirmed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (maintenance_id)
);

-- Outbox table for reliable event publication.
CREATE TABLE IF NOT EXISTS event_outbox (
  id bigserial PRIMARY KEY,
  aggregate_type text NOT NULL,
  aggregate_id text NOT NULL,
  event_type text NOT NULL,
  event_version text NOT NULL DEFAULT 'v1',
  payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'published', 'failed')),
  retry_count integer NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
  next_attempt_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  trace_id text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_assets_updated_at
BEFORE UPDATE ON assets
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_sensor_nodes_updated_at
BEFORE UPDATE ON sensor_nodes
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_inspection_tickets_updated_at
BEFORE UPDATE ON inspection_tickets
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_maintenance_actions_updated_at
BEFORE UPDATE ON maintenance_actions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_verification_records_updated_at
BEFORE UPDATE ON verification_records
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
