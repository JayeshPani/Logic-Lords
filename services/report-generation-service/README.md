# Report Generation Service

Builds structured inspection and maintenance evidence bundles for downstream verification.

## Responsibilities

- Ingest `inspection.requested` and `maintenance.completed` context events.
- Consume `report.generate` command payloads.
- Produce report bundles with source trace metadata and deterministic evidence hash.
- Emit `report.generated` event payload and `verification.record.blockchain` command payload.

## API

- `GET /health`
- `GET /metrics`
- `POST /events/inspection-requested`
- `POST /events/maintenance-completed`
- `POST /generate`

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

## Module-10 Validation

```bash
make module10-check
```

## Notes

- Evidence hashes are deterministic for identical command/context payloads and timestamp.
- Context storage is in-memory for local development and contract checks.
- `/metrics` exposes Prometheus-style counters for context ingestion and report generation paths.
