# ERD (v1)

## Table Ownership

- `assets`: master record for monitored infrastructure assets.
- `sensor_nodes`: sensor device metadata and lifecycle state.
- `sensor_readings`: append-only telemetry facts.
- `risk_assessments`: append-only health score snapshots.
- `failure_forecasts`: append-only 72h failure predictions.
- `inspection_tickets`: orchestration-driven inspection workflow tickets.
- `maintenance_actions`: execution and lifecycle of maintenance work.
- `verification_records`: blockchain anchoring state for maintenance evidence.
- `event_outbox`: reliable async publication queue.

## Relationships

- `sensor_nodes.asset_id -> assets.id`
- `sensor_readings.asset_id -> assets.id`
- `sensor_readings.sensor_node_id -> sensor_nodes.id`
- `risk_assessments.asset_id -> assets.id`
- `failure_forecasts.asset_id -> assets.id`
- `inspection_tickets.asset_id -> assets.id`
- `maintenance_actions.asset_id -> assets.id`
- `maintenance_actions.inspection_ticket_id -> inspection_tickets.id`
- `verification_records.maintenance_action_id -> maintenance_actions.id`
- `verification_records.asset_id -> assets.id`

## Data Strategy

- Append-only: `sensor_readings`, `risk_assessments`, `failure_forecasts`.
- Mutable workflow state: `inspection_tickets`, `maintenance_actions`, `verification_records`.
- Immutable verification anchors: `evidence_hash`, `tx_hash`, network metadata in `verification_records`.

## Physical Contract

- SQL schema: `schema.v1.sql`
- SQL indexes: `indexes.v1.sql`
