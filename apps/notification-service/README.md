# Notification Service

Dispatches operational alerts to field teams with template rendering, retries, and channel fallback.

## Responsibilities

- Consume `notification.dispatch` command payloads.
- Render severity-aware notification templates.
- Retry failed sends per channel and fallback to secondary channels.
- Expose dispatch status APIs and emit `notification.delivery.status` event payloads.

## API

- `GET /health`
- `GET /metrics`
- `POST /dispatch`
- `GET /dispatches`
- `GET /dispatches/{dispatch_id}`

## Run

```bash
cd apps/notification-service
python3 -m uvicorn src.main:app --reload --port 8201
```

## Environment

- `NOTIFICATION_LOG_LEVEL` (default: `INFO`)
- `NOTIFICATION_METRICS_ENABLED` (default: `true`)
- `NOTIFICATION_EVENT_PRODUCED_BY` (default: `apps/notification-service`)
- `NOTIFICATION_MAX_RETRY_ATTEMPTS` (default: `3`)
- `NOTIFICATION_FALLBACK_CHANNELS` (default: `chat,webhook,email,sms`)

## Module-11 Validation

```bash
make module11-check
```

## Notes

- Default channel adapters are stubbed as successful for local development.
- Dispatch records are stored in-memory for runtime checks and contract tests.
- `/metrics` exposes Prometheus-style counters for retries, fallback switches, and outcomes.
