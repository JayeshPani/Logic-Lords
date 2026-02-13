# Event Topics

- sensor.reading.ingested
- asset.risk.computed
- asset.failure.predicted
- asset.anomaly.detected
- inspection.requested
- maintenance.completed
- maintenance.verified.blockchain

## Postgres Notification Channel

- `infraguard_outbox`: emitted for each inserted outbox row by trigger `trg_event_outbox_notify_insert`.
