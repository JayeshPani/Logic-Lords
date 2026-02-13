# OpenClaw Agent Pack

Workflow definitions for autonomous operations triggered by risk and maintenance events.

## Workflows

- `high-risk-detection.yaml`
- `follow-up-monitoring.yaml`
- `post-maintenance-verification.yaml`

## Contract Alignment

- Consumes: `asset.risk.computed`, `asset.failure.predicted`, `inspection.requested`, `maintenance.completed`
- Produces through orchestration runtime: `inspection.create` command, `inspection.requested`, `maintenance.completed`

## Runtime Integration

- `apps/orchestration-service` executes these workflow policies in local runtime.
- Retry policy for `high-risk-detection` is `max_attempts: 3`.
