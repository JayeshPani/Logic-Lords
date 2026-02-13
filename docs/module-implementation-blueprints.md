# Module Implementation Blueprints

## 1. Asset Registry Service
- Depends on: none
- Exposes: asset and sensor registration APIs
- Stores: assets, sensor_nodes
- Acceptance: create/list/update assets; sensor-to-asset mapping with validation

## 2. Sensor Ingestion Service
- Depends on: Asset Registry, event bus, storage
- Exposes: ingest endpoint and protocol adapters
- Publishes: sensor.reading.ingested
- Acceptance: schema validation, idempotency key support, dead-letter capture

## 3. Fuzzy Inference Service
- Depends on: sensor.reading.ingested
- Exposes: risk component API/event
- Publishes: partial risk component
- Acceptance: deterministic rule evaluation for calibrated fixtures

## 4. LSTM Forecast Service
- Depends on: historical readings store
- Exposes: 72h forecast API/event
- Publishes: asset.failure.predicted
- Acceptance: baseline model inference and confidence output

## 5. Health Score Service
- Depends on: fuzzy + forecast + anomaly outputs
- Exposes: canonical final AI output API
- Publishes: `health_score`, `failure_probability_72h`, `anomaly_flag`, `risk_level`
- Acceptance: exact output shape from AI integration spec

## 6. Anomaly Detection Service
- Depends on: normalized current signal and optional baseline window
- Exposes: anomaly score and flag API
- Publishes: anomaly insights for fuzzy and orchestration layers
- Acceptance: Isolation Forest configuration parity and deterministic fallback behavior

## 7. Orchestration Service + OpenClaw Agent
- Depends on: risk and forecast events
- Exposes: workflow state API
- Publishes: inspection.requested and maintenance workflow events
- Acceptance: high-risk workflow starts automatically with retry policy

## 8. Report Generation Service
- Depends on: inspection and maintenance data
- Exposes: report generation API
- Publishes: report-generated event
- Acceptance: structured report bundle with source trace metadata

## 9. Notification Service
- Depends on: orchestration events
- Exposes: dispatch status API
- Publishes: delivery status events
- Acceptance: template rendering + retry + channel fallback

## 10. Blockchain Verification Service
- Depends on: maintenance.completed, report bundles, smart contract
- Exposes: verification query API
- Publishes: maintenance.verified.blockchain
- Acceptance: deterministic evidence hash and tx confirmation tracking

## 11. API Gateway
- Depends on: domain services
- Exposes: consolidated public API
- Acceptance: auth, rate limit, consistent response contracts

## 12. Dashboard Web
- Depends on: API Gateway
- Exposes: operator workflows
- Acceptance: map view, asset drill-down, verification timeline

## 13. Test Matrix
- Contract tests first, then integration, then e2e, then performance
- Acceptance: each module ships with unit + contract tests before integration
