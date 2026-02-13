# InfraGuard

AI-based urban infrastructure health monitoring platform with autonomous orchestration and blockchain verification.

## Goals

- Continuously monitor roads, bridges, and related assets with IoT sensors.
- Predict near-term failure risk with hybrid AI models.
- Trigger autonomous operational workflows via OpenClaw.
- Record maintenance evidence and verification on blockchain.

## Architecture Summary

- `apps/`: external-facing applications and operational services.
- `services/`: core intelligence and domain services.
- `agents/`: OpenClaw workflow definitions.
- `contracts/`: API, event, and data contracts.
- `blockchain/`: smart contracts and chain integration assets.
- `data-platform/`: storage, streaming, and ML data foundations.
- `infra/`: local and cloud deployment assets.
- `tests/`: contract, integration, e2e, and performance test scaffolds.

## Core Principles

- Separation of concerns by bounded modules.
- Contract-first integration (API + event schemas).
- Event-driven interoperability.
- Traceable, auditable workflows.
- Progressive implementation with stable interfaces.

## Start Here

1. Read `PROJECT_PLAN.md` for scope and implementation phases.
2. Read `IMPLEMENTATION_SEQUENCE.md` for step-by-step module build order.
3. Review `docs/module-boundaries.md` before coding any service.
4. Use `docs/module-implementation-blueprints.md` for module-level execution details.
5. Verify AI feature parity in `docs/ai-integration-alignment.md`.
6. Run local AI flow using `docs/ai-pipeline-runbook.md`.
7. Activate trained-model runtime using `scripts/activate_trained_runtime.sh`.
8. Run step-2 model evaluation using `data-platform/ml/evaluation/evaluate_all_models.py`.
9. Run step-3 contract assertions using `scripts/validate_ai_contracts.py --fail-on-invalid`.
10. Run step-2 + step-3 in one command using `make ai-check`.
11. Bring up Module-4 storage layer using `make data-platform-up && make data-platform-migrate`.
12. Validate Module-4 contracts + runtime behavior using `make module4-check`.
13. Validate Module-5 fuzzy service contracts and observability using `make module5-check`.
14. Validate Module-6 forecast service contracts and observability using `make module6-check`.
15. Validate Module-7 anomaly service contracts and observability using `make module7-check`.
16. Validate Module-8 health-score service contracts and observability using `make module8-check`.
17. Validate Module-9 orchestration service contracts and workflow automation using `make module9-check`.
