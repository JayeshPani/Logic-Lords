# Implementation Sequence (Module-Wise)

Build modules in this order to preserve clean dependencies and minimize rework.

1. `contracts/` (API + events + core data definitions)
2. `services/asset-registry-service`
3. `apps/sensor-ingestion-service`
4. `data-platform/storage` and `data-platform/streaming`
5. `services/fuzzy-inference-service`
6. `services/lstm-forecast-service`
7. `services/anomaly-detection-service`
8. `services/health-score-service`
9. `agents/openclaw-agent` and `apps/orchestration-service`
10. `services/report-generation-service`
11. `apps/notification-service`
12. `blockchain/contracts` and `services/blockchain-verification-service`
13. `apps/api-gateway`
14. `apps/dashboard-web`
15. `tests/` full test matrix
16. `infra/` deployment and observability hardening

## Definition of Done Per Module

- Clear input/output contract
- Unit tests for core logic
- Contract tests for integrations
- Structured logs and metrics
- README updated with runbook
