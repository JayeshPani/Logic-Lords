# System Architecture

## Data Flow

1. Sensor nodes publish readings.
2. Ingestion validates and normalizes payloads.
3. Readings are persisted and forwarded through event stream.
4. AI services compute failure probability and anomaly score.
5. Fuzzy inference computes final risk score.
6. Orchestration triggers inspections for high-risk assets.
7. Maintenance events produce pre/post evidence bundle.
8. Verification service anchors evidence hash to blockchain.
9. Dashboard exposes live risk, forecasts, and verification status.

## Integration Style

- Synchronous: API gateway for query and command interfaces.
- Asynchronous: event contracts for module decoupling.

## Trust Model

- Operational state in database.
- Immutable verification fingerprints on blockchain.
