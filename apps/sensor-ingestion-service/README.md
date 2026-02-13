# Sensor Ingestion Service

## Purpose
Receive telemetry from IoT gateways and normalize into canonical schema.

## Responsibilities
- Protocol adapters (MQTT/HTTP)
- Payload validation
- Data normalization and timestamping
- Publish `sensor.reading.ingested` event

## Out of Scope
- Risk scoring
- Workflow orchestration
