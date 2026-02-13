# Orchestration Service

Automates operational workflows for high-risk assets using OpenClaw-driven policies.

## Responsibilities

- Consume `asset.risk.computed` and `asset.failure.predicted` events.
- Trigger high-risk workflow automatically with retry policy.
- Produce `inspection.create` command payload and `inspection.requested` event payload.
- Expose workflow-state APIs and maintenance completion transition.

## API

- `GET /health`
- `GET /metrics`
- `POST /events/asset-failure-predicted`
- `POST /events/asset-risk-computed`
- `GET /workflows`
- `GET /workflows/{workflow_id}`
- `POST /workflows/{workflow_id}/maintenance/completed`

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
- `ORCHESTRATION_EVENT_PRODUCED_BY` (default: `apps/orchestration-service`)
- `ORCHESTRATION_COMMAND_REQUESTED_BY` (default: `agents/openclaw-agent`)

## Module-9 Validation

```bash
make module9-check
```

## Notes

- Retry policy is applied when dispatching `inspection.create` command payloads.
- Workflow state is in-memory for local development and contract validation.
- `/metrics` exposes Prometheus-style counters for trigger, retry, and failure behavior.
