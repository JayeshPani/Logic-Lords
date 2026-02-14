# Evidence Upload + Verification Runbook

Date: 2026-02-15

## Purpose
Run and validate the organization evidence workflow:
1. Complete maintenance.
2. Upload + finalize evidence.
3. Submit verification.
4. Track confirmations in ledger tab.

## Services and Ports
- `apps/orchestration-service` on `8200`
- `services/report-generation-service` on `8202`
- `services/blockchain-verification-service` on `8105`
- `apps/api-gateway` on `8080` (or your chosen gateway port)

## Required Environment Variables

### API Gateway
- `API_GATEWAY_ORCHESTRATION_BASE_URL=http://127.0.0.1:8200`
- `API_GATEWAY_REPORT_GENERATION_BASE_URL=http://127.0.0.1:8202`
- `API_GATEWAY_BLOCKCHAIN_VERIFICATION_BASE_URL=http://127.0.0.1:8105`
- `API_GATEWAY_AUTH_BEARER_TOKENS_CSV=dev-token`
- `API_GATEWAY_AUTH_TOKEN_ROLES_CSV=dev-token:organization|operator`

### Report Generation Service
- `REPORT_GENERATION_FIREBASE_STORAGE_BUCKET=<firebase-bucket-name>`
- `REPORT_GENERATION_FIREBASE_CREDENTIALS_JSON=<service-account-json-or-file-path>`
- Optional:
  - `REPORT_GENERATION_EVIDENCE_MAX_FILE_BYTES=20971520`
  - `REPORT_GENERATION_EVIDENCE_ALLOWED_MIME_TYPES_CSV=application/pdf,image/jpeg,image/png,image/webp,video/mp4`
  - `REPORT_GENERATION_EVIDENCE_UPLOAD_URL_TTL_SECONDS=900`

### Orchestration Service
- `ORCHESTRATION_REPORT_GENERATION_BASE_URL=http://127.0.0.1:8202`
- `ORCHESTRATION_BLOCKCHAIN_VERIFICATION_BASE_URL=http://127.0.0.1:8105`

## Startup Order
1. Start `services/report-generation-service`.
2. Start `services/blockchain-verification-service`.
3. Start `apps/orchestration-service`.
4. Start `apps/api-gateway`.
5. Open `http://127.0.0.1:8080/dashboard`.

## Happy-Path Validation
1. Trigger or open a workflow with maintenance completed (`maintenance_id` available).
2. Go to `Maintenance` tab.
3. Select a file in `Evidence File`.
4. Click `Upload & Finalize Evidence`.
5. Confirm evidence row appears with status `FINALIZED` and SHA-256 value.
6. Click `Submit Verification`.
7. Go to `Ledger` tab and click `Track Verification`.
8. Confirm verification progresses (`pending/submitted/confirmed`) with confirmation counter.

## API Smoke Commands

```bash
curl -sS -H "Authorization: Bearer dev-token" \
  http://127.0.0.1:8080/maintenance/<maintenance_id>/evidence
```

```bash
curl -sS -X POST -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{"submitted_by":"ops-dashboard"}' \
  http://127.0.0.1:8080/maintenance/<maintenance_id>/verification/submit
```

```bash
curl -sS -X POST -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{}' \
  http://127.0.0.1:8080/maintenance/<maintenance_id>/verification/track
```

## Common Failures
- `403 FORBIDDEN` on evidence endpoints:
  - token missing `organization` role in `API_GATEWAY_AUTH_TOKEN_ROLES_CSV`.
- `409 EVIDENCE_REQUIRED` on submit:
  - no finalized evidence items for that maintenance ID.
- `503` from evidence routes:
  - Firebase Storage bucket/credentials are not configured or unavailable.
- `409 VERIFICATION_LOCKED`:
  - evidence set is locked after successful report generation.
