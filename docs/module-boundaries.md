# Module Boundaries

## apps/api-gateway
- Responsibility: Unified external API facade.
- Owns: auth facade, request routing, response composition.
- Does not own: ML logic, orchestration state, chain writes.

## apps/sensor-ingestion-service
- Responsibility: ingest/validate sensor telemetry.
- Owns: protocol adapters and normalization.
- Does not own: risk scoring and workflow decisions.

## services/fuzzy-inference-service
- Responsibility: rule-based uncertainty reasoning.
- Owns: fuzzy membership sets and rule base.

## services/lstm-forecast-service
- Responsibility: time-series forecasting of failure probability.
- Owns: model lifecycle, inference, feature windows.

## services/anomaly-detection-service
- Responsibility: detect sudden abnormal structural behavior.
- Owns: Isolation Forest config/runtime and anomaly score/flag outputs.

## services/health-score-service
- Responsibility: publish canonical final AI payload for downstream systems.
- Owns: output shape mapping and risk-level band classification.

## apps/orchestration-service + agents/openclaw-agent
- Responsibility: automate operational workflow for risky assets.
- Owns: task graph execution and escalation policy.

## services/report-generation-service
- Responsibility: build structured inspection/maintenance reports.
- Owns: report schemas and evidence bundles.

## services/blockchain-verification-service
- Responsibility: hash, anchor, and verify evidence on-chain.
- Owns: chain adapter, tx tracking, proof lookup.

## apps/dashboard-web
- Responsibility: human interface for risk, actions, verification.
- Owns: UI state and visualization logic.
