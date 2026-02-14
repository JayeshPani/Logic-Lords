# Dashboard Web

## Purpose
Operational and governance UI for risk status and maintenance verification.

## Implemented Views
- City risk map with severity + probability visual encoding
- Infrastructure health gauge with risk decomposition bars
- Sensor telemetry cards with micro-bar trends
- 72-hour failure forecast line/area chart
- Maintenance audit log with verification status
- Blockchain verification summary panel
- Sepolia connect button for live on-chain connectivity checks
- MetaMask wallet connect button for operator identity on Sepolia

## Architecture (Separation of Concerns)
- `index.html`: semantic page structure only
- `src/styles.css`: design tokens, layout, component styling, animations
- `src/config.js`: constants, thresholds, palette mappings
- `src/api.js`: API transport and fallback strategy
- `src/state.js`: view-model derivation and formatting helpers
- `src/visualization.js`: chart and map rendering functions
- `src/ui.js`: DOM binding/render orchestration
- `src/main.js`: app bootstrap, refresh cycle, interaction handlers

## Data Sources
- API Gateway (same-origin via `/dashboard`):
  - `GET /assets`
  - `GET /assets/{asset_id}/health`
  - `GET /assets/{asset_id}/forecast?horizon_hours=72`
  - `GET /telemetry/{asset_id}/latest`
  - `GET /maintenance/{maintenance_id}/verification`
  - `GET /health`
  - `POST /blockchain/connect`
- Graceful fallback to local mock data when API is unavailable

## Run
1. Start API Gateway:
```bash
cd apps/api-gateway
python3 -m uvicorn src.main:app --reload --port 8080
```
2. Open dashboard:
```text
http://127.0.0.1:8080/dashboard
```

3. For live Sepolia connect button, also run blockchain verification service:
```bash
export BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_URL=\"https://sepolia.infura.io/v3/<your-key>\"
# Optional: use a real deployed contract address, or unset this variable.
# export BLOCKCHAIN_VERIFICATION_SEPOLIA_CONTRACT_ADDRESS=\"0x1111111111111111111111111111111111111111\"
cd services/blockchain-verification-service
python3 -m uvicorn src.main:app --reload --port 8105
```

Contract deployment helper (no Hardhat):
```bash
bash blockchain/scripts/deploy_sepolia_foundry.sh
```

4. For wallet button:
- Install MetaMask in browser.
- Select/import an account.
- Ensure chain is Sepolia (wallet can switch automatically when you click `Connect Wallet`).

5. For live DHT11 + accelerometer telemetry cards:
```bash
cd apps/sensor-ingestion-service
export SENSOR_INGESTION_FIREBASE_DB_URL="https://<project-id>-default-rtdb.firebaseio.com"
# export SENSOR_INGESTION_FIREBASE_AUTH_TOKEN="<optional-token>"
python3 -m uvicorn src.main:app --reload --port 8100

cd ../../apps/api-gateway
export API_GATEWAY_SENSOR_INGESTION_BASE_URL="http://127.0.0.1:8100"
python3 -m uvicorn src.main:app --reload --port 8090
```

ESP32 sketch path:
- `firmware/esp32/firebase_dht11_mpu6050/esp32_firebase_dht11_mpu6050.ino`

## Validation
```bash
make module14-check
```
