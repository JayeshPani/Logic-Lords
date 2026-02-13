-- Storage runtime bootstrap objects (idempotent).
-- Applied after contract schema migration.

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
  id bigserial PRIMARY KEY,
  version text NOT NULL UNIQUE,
  description text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

COMMIT;
