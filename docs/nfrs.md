# Non-Functional Requirements

- Ingestion latency: p95 < 2s from receive to persist
- Risk update latency: p95 < 10s from reading to score
- Availability target: 99.9% for core APIs
- Audit integrity: 100% chain anchoring for completed maintenance records
- Observability: tracing across ingestion -> AI -> orchestration -> verification
