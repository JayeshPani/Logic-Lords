# Streaming Layer

## Purpose
Event bus backbone for decoupled communication across services.

## Implemented (Module 4)
- Event topic catalog in `topics.md`.
- PostgreSQL outbox runtime migration:
  - `data-platform/streaming/migrations/001_outbox_runtime.sql`
- Outbox enqueue/dispatch scripts:
  - `scripts/streaming_enqueue_event.sh`
  - `scripts/streaming_dispatch_outbox.sh`

## Local Runbook

```bash
# Enqueue sample event from JSON payload
make streaming-enqueue

# Dispatch pending outbox events
make streaming-dispatch
```

## Runtime Pattern
- Producers write integration events to `event_outbox` table in DB transaction.
- Dispatcher reads pending rows via `dequeue_outbox_events(batch_size)`.
- Dispatched rows are marked as `published`.
- Insert trigger emits `pg_notify('infraguard_outbox', ...)` for reactive consumers.
