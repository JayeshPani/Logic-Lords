# Report Generation Service

Builds structured inspection and maintenance evidence bundles for downstream verification.

## Responsibilities

- Ingest `inspection.requested` and `maintenance.completed` context events.
- Consume `report.generate` command payloads.
- Produce report bundles with source trace metadata and deterministic evidence hash.
- Emit `report.generated` event payload and `verification.record.blockchain` command payload.
- Provide evidence upload/finalize/list APIs backed by Firebase Storage.

## API

- `GET /health`
- `GET /metrics`
- `POST /events/inspection-requested`
- `POST /events/maintenance-completed`
- `POST /generate`
- `POST /maintenance/{maintenance_id}/evidence/uploads`
- `POST /maintenance/{maintenance_id}/evidence/{evidence_id}/finalize`
- `GET /maintenance/{maintenance_id}/evidence`
- `POST /maintenance/{maintenance_id}/evidence/{evidence_id}/delete`

## Run

```bash
cd services/report-generation-service
python3 -m uvicorn src.main:app --reload --port 8104
```

## Environment

- `REPORT_GENERATION_LOG_LEVEL` (default: `INFO`)
- `REPORT_GENERATION_METRICS_ENABLED` (default: `true`)
- `REPORT_GENERATION_EVENT_PRODUCED_BY` (default: `services/report-generation-service`)
- `REPORT_GENERATION_COMMAND_REQUESTED_BY` (default: `services/report-generation-service`)
- `REPORT_GENERATION_BLOCKCHAIN_NETWORK` (default: `sepolia`)
- `REPORT_GENERATION_BLOCKCHAIN_CONTRACT_ADDRESS` (default: `0x1111111111111111111111111111111111111111`)
- `REPORT_GENERATION_BLOCKCHAIN_CHAIN_ID` (default: `11155111`)
- `REPORT_GENERATION_FIREBASE_STORAGE_BUCKET` (required for live uploads)
- `REPORT_GENERATION_FIREBASE_PROJECT_ID` (optional)
- `REPORT_GENERATION_FIREBASE_CREDENTIALS_JSON` (inline JSON or file path)
- `REPORT_GENERATION_EVIDENCE_UPLOAD_URL_TTL_SECONDS` (default: `900`)
- `REPORT_GENERATION_EVIDENCE_MAX_FILE_BYTES` (default: `20971520`)
- `REPORT_GENERATION_EVIDENCE_ALLOWED_MIME_TYPES_CSV` (default: `application/pdf,image/jpeg,image/png,image/webp,video/mp4`)

## Module-10 Validation

```bash
make module10-check
```

## Notes

- Evidence hashes are deterministic for identical command/context payloads and timestamp.
- Maintenance verification generation requires at least one finalized evidence item.
- Context storage is in-memory for local development and contract checks.
- `/metrics` exposes Prometheus-style counters for context ingestion and report generation paths.
