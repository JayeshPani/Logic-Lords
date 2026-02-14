# OpenClaw Agent Pack

Workflow definitions for autonomous operations triggered by risk and maintenance events.

## Workflows

- `high-risk-detection.yaml`
- `follow-up-monitoring.yaml`
- `post-maintenance-verification.yaml`
- `public-safety-escalation.yaml`

## Contract Alignment

- Consumes: `asset.risk.computed`, `asset.failure.predicted`, `inspection.requested`, `maintenance.completed`
- Produces through orchestration runtime:
  - `inspection.create` command
  - `notification.dispatch` command (management then police on timeout)
  - `inspection.requested`, `maintenance.completed`

## Runtime Integration

- `apps/orchestration-service` executes these workflow policies in local runtime.
- Retry policy for `high-risk-detection` is `max_attempts: 3`.
- Safety escalation lifecycle:
  - management is notified when incident is created
  - dashboard acknowledgement closes management SLA path
  - police is auto-notified after ACK SLA timeout
