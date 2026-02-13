# Storage Layer

## Purpose
Persistent storage for operational and analytical infrastructure health data.

## Implemented (Module 4)
- Dockerized PostgreSQL 16 runtime (direct container) with optional compose reference.
- Contract-first schema migration from:
  - `contracts/database/schema.v1.sql`
  - `contracts/database/indexes.v1.sql`
- Runtime bootstrap migration:
  - `data-platform/storage/migrations/001_storage_runtime.sql`
- Development seed data and status inspection scripts.

## Local Runbook

```bash
# Start PostgreSQL container
make data-platform-up

# Apply DB contracts + storage/streaming runtime migrations
make data-platform-migrate

# Seed a dev asset/sensor + one outbox event
make data-platform-seed

# Inspect migration versions and core table counts
make data-platform-status

# Run Module-4 checks (contract + integration)
make module4-check
```

## Notes
- `schema.v1.sql` is applied once (guarded by presence of `assets` table).
- `indexes.v1.sql` is safe to re-apply.
- The source-of-truth schema remains under `contracts/database/`.
- Default container/runtime values:
  - `INFRAGUARD_DB_CONTAINER=infraguard-postgres`
  - `INFRAGUARD_DB_IMAGE=docker.io/library/postgres:16`
  - `INFRAGUARD_DB_PORT=55432`
- If `INFRAGUARD_DB_PORT` is unavailable, startup auto-selects the next free host port.
- If the default host port is unavailable, override it:

```bash
INFRAGUARD_DB_PORT=55491 make data-platform-up
```

## Cleanup

```bash
# Stop container only (keeps named volume data)
make data-platform-down

# Stop container and remove named volume data
INFRAGUARD_DB_REMOVE_VOLUME=1 make data-platform-down
```
