# Docker Local Infra

Local dependencies for development and integration tests.

## Available Stack
- `postgres` (contract schema storage)
- `redis` (optional lightweight pub/sub cache layer)
- `mosquitto` (optional MQTT broker for sensor gateway simulation)

## Notes
- Module 4 scripts (`make data-platform-*`) currently use direct Docker container commands for PostgreSQL.
- `docker-compose.local.yml` remains available for teams who prefer compose-managed local infra.
