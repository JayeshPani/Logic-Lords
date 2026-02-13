# Contracts Catalog

This folder is the integration source of truth for InfraGuard.

## Core Contracts

- `core/event-envelope.schema.json`: shared envelope for all published events.
- `core/command-envelope.schema.json`: shared envelope for internal commands.
- `core/ids-and-enums.md`: canonical IDs, enums, and versioning policy.

## API Contracts

- `api/openapi.yaml`: external API surface through API gateway.

## Event Contracts

- `events/sensor.reading.ingested.schema.json`
- `events/asset.risk.computed.schema.json`
- `events/asset.failure.predicted.schema.json`
- `events/asset.anomaly.detected.schema.json`
- `events/inspection.requested.schema.json`
- `events/maintenance.completed.schema.json`
- `events/maintenance.verified.blockchain.schema.json`

## Command Contracts

- `commands/inspection.create.command.schema.json`
- `commands/notification.dispatch.command.schema.json`
- `commands/report.generate.command.schema.json`
- `commands/verification.record.blockchain.command.schema.json`

## Device Payload Contracts

- `sensors/sensor-payload.schema.json`: raw payload from sensor gateway to ingestion.

## ML Contracts

- `ml/fuzzy.infer.request.schema.json`
- `ml/fuzzy.infer.response.schema.json`
- `ml/anomaly.detect.request.schema.json`
- `ml/anomaly.detect.response.schema.json`
- `ml/health.score.request.schema.json`
- `ml/health.score.response.schema.json`
- `ml/forecast.request.schema.json`
- `ml/forecast.response.schema.json`

## Database Contracts

- `database/schema.v1.sql`: canonical PostgreSQL schema for v1.
- `database/indexes.v1.sql`: canonical index set for v1.
- `database/erd.md`: logical data model and ownership boundaries.
