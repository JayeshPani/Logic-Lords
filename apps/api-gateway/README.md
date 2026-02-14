# API Gateway

Unified HTTP facade for dashboard, mobile, and external consumers.

## Responsibilities

- Enforce auth and rate limits at the boundary.
- Expose contract-aligned public APIs.
- Aggregate read models from domain-service outputs.
- Return consistent success and error envelopes.

## API

- `GET /health` (public)
- `GET /metrics`
- `GET /assets`
- `POST /assets`
- `GET /assets/{asset_id}`
- `GET /assets/{asset_id}/health`
- `GET /assets/{asset_id}/forecast`
- `GET /telemetry/{asset_id}/latest`
- `GET /maintenance/{maintenance_id}/verification`
- `POST /maintenance/{maintenance_id}/verification/track`
- `POST /maintenance/{maintenance_id}/evidence/uploads`
- `POST /maintenance/{maintenance_id}/evidence/{evidence_id}/finalize`
- `GET /maintenance/{maintenance_id}/evidence`
- `POST /maintenance/{maintenance_id}/verification/submit`
- `POST /blockchain/connect`
- `GET /automation/incidents`
- `GET /automation/incidents/{workflow_id}`
- `POST /automation/incidents/{workflow_id}/acknowledge`

## Run

```bash
cd apps/api-gateway
python3 -m uvicorn src.main:app --reload --port 8080
```

## Environment

- `API_GATEWAY_LOG_LEVEL` (default: `INFO`)
- `API_GATEWAY_METRICS_ENABLED` (default: `true`)
- `API_GATEWAY_AUTH_ENABLED` (default: `true`)
- `API_GATEWAY_AUTH_BEARER_TOKENS_CSV` (default: `dev-token`)
- `API_GATEWAY_AUTH_TOKEN_ROLES_CSV` (default: `dev-token:organization|operator`)
- `API_GATEWAY_RATE_LIMIT_ENABLED` (default: `true`)
- `API_GATEWAY_RATE_LIMIT_REQUESTS` (default: `60`)
- `API_GATEWAY_RATE_LIMIT_WINDOW_SECONDS` (default: `60`)
- `API_GATEWAY_BLOCKCHAIN_VERIFICATION_BASE_URL` (default: `http://127.0.0.1:8105`)
- `API_GATEWAY_BLOCKCHAIN_VERIFICATION_FALLBACK_URLS_CSV` (default: `http://127.0.0.1:8235,http://127.0.0.1:8123`)
- `API_GATEWAY_BLOCKCHAIN_CONNECT_TIMEOUT_SECONDS` (default: `15.0`)
- `API_GATEWAY_BLOCKCHAIN_VERIFICATION_TIMEOUT_SECONDS` (default: `8.0`)
- `API_GATEWAY_SENSOR_INGESTION_BASE_URL` (default: `http://127.0.0.1:8100`)
- `API_GATEWAY_SENSOR_TELEMETRY_TIMEOUT_SECONDS` (default: `8.0`)
- `API_GATEWAY_REPORT_GENERATION_BASE_URL` (default: `http://127.0.0.1:8202`)
- `API_GATEWAY_REPORT_GENERATION_TIMEOUT_SECONDS` (default: `15.0`)
- `API_GATEWAY_ORCHESTRATION_BASE_URL` (default: `http://127.0.0.1:8200`)
- `API_GATEWAY_ORCHESTRATION_TIMEOUT_SECONDS` (default: `8.0`)

## Module-13 Validation

```bash
make module13-check
```

## Notes

- Uses in-memory read models for local module validation.
- Maintenance verification endpoints are proxied from blockchain-verification service (not static store data).
- Error responses follow contract `ErrorResponse` envelope.
- Contract tests validate gateway output against `contracts/api/openapi.yaml` component schemas.
