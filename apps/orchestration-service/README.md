# Orchestration Service

Automates operational workflows for high-risk assets using OpenClaw-driven policies.

## Responsibilities

- Consume `asset.risk.computed` and `asset.failure.predicted` events.
- Trigger high-risk workflow automatically with retry policy.
- Produce `inspection.create` command payload and `inspection.requested` event payload.
- Dispatch management alerts and enforce acknowledgement SLA.
- Auto-escalate to police when acknowledgement SLA is missed.
- On maintenance completion, hand off to report-generation + blockchain-verification.
- Expose workflow-state APIs and maintenance completion transition.

## API

- `GET /health`
- `GET /metrics`
- `POST /events/asset-failure-predicted`
- `POST /events/asset-risk-computed`
- `GET /workflows`
- `GET /workflows/{workflow_id}`
- `GET /incidents`
- `GET /incidents/{workflow_id}`
- `POST /incidents/{workflow_id}/acknowledge`
- `POST /workflows/{workflow_id}/maintenance/completed`
- `POST /maintenance/{maintenance_id}/verification/submit`
- `GET /maintenance/{maintenance_id}/verification/state`

## Run

```bash
cd apps/orchestration-service
python3 -m uvicorn src.main:app --reload --port 8200
```

## Environment

- `ORCHESTRATION_LOG_LEVEL` (default: `INFO`)
- `ORCHESTRATION_METRICS_ENABLED` (default: `true`)
- `ORCHESTRATION_TRIGGER_RISK_LEVELS` (default: `High,Critical`)
- `ORCHESTRATION_MIN_HEALTH_SCORE` (default: `0.70`)
- `ORCHESTRATION_MIN_FAILURE_PROBABILITY` (default: `0.60`)
- `ORCHESTRATION_MAX_RETRY_ATTEMPTS` (default: `3`)
- `ORCHESTRATION_AUTHORITY_ACK_SLA_MINUTES` (default: `30`)
- `ORCHESTRATION_ESCALATION_CHECK_INTERVAL_SECONDS` (default: `30`)
- `ORCHESTRATION_NOTIFICATION_BASE_URL` (default: `http://127.0.0.1:8201`)
- `ORCHESTRATION_NOTIFICATION_TIMEOUT_SECONDS` (default: `8.0`)
- `ORCHESTRATION_MANAGEMENT_RECIPIENTS_CSV` (default: `management@infraguard.local`)
- `ORCHESTRATION_MANAGEMENT_CHANNELS_CSV` (default: `email,sms,webhook`)
- `ORCHESTRATION_POLICE_RECIPIENTS_CSV` (default: `police-control@infraguard.local`)
- `ORCHESTRATION_POLICE_CHANNELS_CSV` (default: `webhook,sms`)
- `ORCHESTRATION_REPORT_GENERATION_BASE_URL` (default: `http://127.0.0.1:8202`)
- `ORCHESTRATION_REPORT_GENERATION_TIMEOUT_SECONDS` (default: `8.0`)
- `ORCHESTRATION_BLOCKCHAIN_VERIFICATION_BASE_URL` (default: `http://127.0.0.1:8105`)
- `ORCHESTRATION_BLOCKCHAIN_VERIFICATION_TIMEOUT_SECONDS` (default: `8.0`)
- `ORCHESTRATION_EVENT_PRODUCED_BY` (default: `apps/orchestration-service`)
- `ORCHESTRATION_COMMAND_REQUESTED_BY` (default: `agents/openclaw-agent`)

## Module-9 Validation

```bash
make module9-check
```

## Notes

- Retry policy is applied when dispatching `inspection.create` command payloads.
- Incident acknowledgement endpoint is idempotent.
- Late acknowledgements are persisted for audit even after police escalation.
- Maintenance completion responses include `verification_summary` with status/error.
- Maintenance completion now transitions verification state to `awaiting_evidence`.
- Verification submission is explicit and idempotent by maintenance ID.
- Workflow state is in-memory for local development and contract validation.
- `/metrics` exposes Prometheus-style counters for trigger, retry, and failure behavior.
