# InfraGuard

AI-based urban infrastructure monitoring platform with autonomous safety escalation, organization evidence workflows, and blockchain verification.

## Current Scope
InfraGuard is implemented as a contract-first, event-driven system that combines:
- IoT telemetry ingestion (ESP32 -> Firebase -> sensor-ingestion-service)
- AI risk computation (forecast, anomaly, fuzzy inference, health score)
- Operational orchestration (inspection + maintenance lifecycle)
- Automated escalation (management acknowledgement SLA -> police escalation)
- Evidence-backed ledger verification (organization upload + explicit submit + tracking)
- Operator dashboard (risk, map, nodes, automation, maintenance, ledger)

## Key Capabilities
- Live or fallback telemetry for city assets.
- 72h risk and health visualization.
- Realtime LSTM overview feed in dashboard.
- Firebase node registry panel in dashboard (global node view).
- City Map tab with geographic rendering + fallback mode.
- Management notification + acknowledgement workflow.
- Automatic police escalation when SLA expires.
- Organization evidence upload (file + metadata), finalize (SHA-256), and explicit verification submit.
- Ledger verification status timeline (`pending/submitted/confirmed/failed`) with confirmation tracking.
- Optional MetaMask connect for operator identity attribution (wallet not required for backend verification).

## Repository Layout
- `apps/`
  - `api-gateway`: boundary API, auth/rate-limit, dashboard/static serving, upstream proxying.
  - `orchestration-service`: workflow engine, escalation state machine, verification submit trigger.
  - `notification-service`: channel dispatch, retry/fallback.
  - `sensor-ingestion-service`: Firebase telemetry read/normalize API.
  - `dashboard-web`: plain HTML/CSS/JS operator UI.
- `services/`
  - `lstm-forecast-service`, `anomaly-detection-service`, `fuzzy-inference-service`, `health-score-service`
  - `report-generation-service`: evidence hashing + verification command generation + evidence upload APIs
  - `blockchain-verification-service`: deterministic/live tx mode + verification tracking
- `firmware/esp32/firebase_dht11_mpu6050/`: ESP32 sketch for DHT11 + accelerometer -> Firebase RTDB.
- `agents/openclaw-agent/`: OpenClaw workflow definitions for automation.
- `contracts/`: OpenAPI + command/event/database schemas.
- `data-platform/`: storage, streaming, ML training/evaluation artifacts.
- `docs/`: runbooks and implementation references.
- `tests/`: contract/integration/e2e/performance suites.

## End-to-End Flows
### 1) Telemetry
1. ESP32 pushes readings into Firebase RTDB.
2. `sensor-ingestion-service` reads `latest/history` telemetry and computes derived metrics.
3. `api-gateway` exposes telemetry to dashboard via `/telemetry/{asset_id}/latest`.

### 2) Risk and Workflows
1. AI services compute forecast/anomaly/risk signals.
2. `orchestration-service` triggers incident workflows for high-risk assets.
3. Management alerts are dispatched via notification-service.
4. If ACK not received before SLA, police escalation is auto-triggered.

### 3) Evidence and Verification
1. Maintenance completes and workflow enters `awaiting_evidence` state.
2. Organization uploads evidence files and finalizes them (hash persisted).
3. Operator submits verification explicitly.
4. Report-generation builds canonical evidence payload and command.
5. Blockchain-verification records and tracks confirmations.
6. Dashboard ledger shows status/timeline.

## Dashboard Tabs
- `Overview`: KPIs + realtime LSTM panel.
- `Triage`: risk-prioritized assets.
- `Asset Detail`: gauge, components, forecast, telemetry cards.
- `Ledger`: Sepolia reachability, verification summary, track button, wallet status.
- `Automation`: incident stages + acknowledgement actions.
- `City Map`: geographic risk view.
- `Nodes`: Firebase/global node registry and node detail.
- `Maintenance`: organization evidence upload/list + submit verification + maintenance log.

## Local Development Quick Start
Run from repository root (`Cental Hack`) with separate terminals.

### 0) Optional: create and activate a Python venv
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies per module as needed (each module with `pyproject.toml` can be installed with `pip install -e <module-path>`).

### 1) Start blockchain verification service
```bash
cd services/blockchain-verification-service
python3 -m uvicorn src.main:app --reload --port 8105
```

### 2) Start report generation service (use port `8202` to match gateway/orchestration defaults)
```bash
cd services/report-generation-service
python3 -m uvicorn src.main:app --reload --port 8202
```

### 3) Start notification service
```bash
cd apps/notification-service
python3 -m uvicorn src.main:app --reload --port 8201
```

### 4) Start orchestration service
```bash
cd apps/orchestration-service
export ORCHESTRATION_NOTIFICATION_BASE_URL="http://127.0.0.1:8201"
export ORCHESTRATION_REPORT_GENERATION_BASE_URL="http://127.0.0.1:8202"
export ORCHESTRATION_BLOCKCHAIN_VERIFICATION_BASE_URL="http://127.0.0.1:8105"
python3 -m uvicorn src.main:app --reload --port 8200
```

### 5) Optional: start sensor-ingestion (for Firebase telemetry)
```bash
cd apps/sensor-ingestion-service
export SENSOR_INGESTION_FIREBASE_DB_URL="https://<project-id>-default-rtdb.<region>.firebasedatabase.app"
# export SENSOR_INGESTION_FIREBASE_AUTH_TOKEN="<optional-token>"
python3 -m uvicorn src.main:app --reload --port 8100
```

### 6) Start API gateway + dashboard
```bash
cd apps/api-gateway
export API_GATEWAY_ORCHESTRATION_BASE_URL="http://127.0.0.1:8200"
export API_GATEWAY_REPORT_GENERATION_BASE_URL="http://127.0.0.1:8202"
export API_GATEWAY_BLOCKCHAIN_VERIFICATION_BASE_URL="http://127.0.0.1:8105"
export API_GATEWAY_SENSOR_INGESTION_BASE_URL="http://127.0.0.1:8100"
export API_GATEWAY_AUTH_BEARER_TOKENS_CSV="dev-token"
export API_GATEWAY_AUTH_TOKEN_ROLES_CSV="dev-token:organization|operator"
export API_GATEWAY_ASSISTANT_GROQ_API_KEY="<your-groq-api-key>"
# optional:
# export API_GATEWAY_ASSISTANT_MODEL="llama-3.3-70b-versatile"
python3 -m uvicorn src.main:app --reload --port 8080
```

Open:
- Dashboard: `http://127.0.0.1:8080/dashboard`
- Health: `http://127.0.0.1:8080/health`

## API Gateway Highlights
Public endpoints include:
- Asset + health + forecast:
  - `GET /assets`
  - `GET /assets/{asset_id}/health`
  - `GET /assets/{asset_id}/forecast`
- Telemetry:
  - `GET /telemetry/{asset_id}/latest`
- LSTM realtime:
  - `POST /lstm/realtime/ingest`
  - `GET /lstm/realtime`
- Automation:
  - `GET /automation/incidents`
  - `GET /automation/incidents/{workflow_id}`
  - `POST /automation/incidents/{workflow_id}/acknowledge`
- Evidence + verification:
  - `POST /maintenance/{maintenance_id}/evidence/uploads`
  - `POST /maintenance/{maintenance_id}/evidence/{evidence_id}/finalize`
  - `GET /maintenance/{maintenance_id}/evidence`
  - `POST /maintenance/{maintenance_id}/verification/submit`
  - `GET /maintenance/{maintenance_id}/verification`
  - `POST /maintenance/{maintenance_id}/verification/track`
- Ledger connect:
  - `POST /blockchain/connect`
- Assistant chat:
  - `POST /assistant/chat`

## Firebase + ESP32 Setup
- Firmware sketch:
  - `firmware/esp32/firebase_dht11_mpu6050/esp32_firebase_dht11_mpu6050.ino`
- Telemetry runbook:
  - `docs/firebase-telemetry-runbook.md`

Expected Firebase RTDB shape:
```text
infraguard/
  telemetry/
    <asset_id>/
      latest
      history/<push-id>
```

## Testing and Quality Gates
Run targeted module checks:
```bash
make module9-check    # orchestration
make module10-check   # report-generation
make module11-check   # notification
make module12-check   # blockchain verification
make module13-check   # api-gateway
make module14-check   # dashboard smoke
```

Run full matrix:
```bash
make module15-check
```

AI validation gates:
```bash
make ai-check
```

## Important Runtime Notes
- Most runtime stores are intentionally in-memory for local/dev validation.
- Dashboard wallet is optional; backend service-wallet/deterministic flow remains canonical.
- Blockchain verification supports:
  - `deterministic` mode (default)
  - `live` Sepolia mode (feature-gated)
- Evidence submit requires finalized evidence items.

## Runbooks
- Firebase telemetry: `docs/firebase-telemetry-runbook.md`
- Safety escalation (management -> police): `docs/safety-escalation-runbook.md`
- Evidence upload + verification: `docs/evidence-upload-verification-runbook.md`
- Ledger + wallet integration: `docs/ledger-wallet-integration-runbook.md`
- Full technical summary: `docs/TECHNICAL_SOFTWARE_IMPLEMENTATION_SUMMARY.md`

## Deployment / Production Hardening (Next)
- Replace in-memory stores with durable persistence.
- Add background schedulers/queues for stronger retry guarantees.
- Tighten Firebase and gateway auth policies for production tokens/roles.
- Enable live Sepolia tx mode with funded service wallet and monitoring.
