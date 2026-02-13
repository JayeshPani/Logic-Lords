#!/usr/bin/env bash
set -euo pipefail

required=(
  "contracts/README.md"
  "contracts/core/event-envelope.schema.json"
  "contracts/core/command-envelope.schema.json"
  "contracts/core/ids-and-enums.md"
  "contracts/commands/inspection.create.command.schema.json"
  "contracts/sensors/sensor-payload.schema.json"
  "contracts/ml/fuzzy.infer.request.schema.json"
  "contracts/ml/anomaly.detect.request.schema.json"
  "contracts/database/schema.v1.sql"
  "contracts/database/indexes.v1.sql"
  "apps/api-gateway"
  "apps/sensor-ingestion-service"
  "apps/orchestration-service"
  "apps/dashboard-web"
  "services/fuzzy-inference-service"
  "services/fuzzy-inference-service/src/fuzzy_inference/main.py"
  "services/health-score-service/src/health_score/main.py"
  "services/lstm-forecast-service/src/lstm_forecast/main.py"
  "services/anomaly-detection-service/src/anomaly_detection/main.py"
  "services/lstm-forecast-service"
  "services/health-score-service"
  "services/anomaly-detection-service"
  "services/blockchain-verification-service"
  "agents/openclaw-agent"
  "contracts/api/openapi.yaml"
  "contracts/events/sensor.reading.ingested.schema.json"
  "contracts/events/asset.anomaly.detected.schema.json"
  "blockchain/contracts/InfraGuardVerification.sol"
)

for path in "${required[@]}"; do
  if [ ! -e "$path" ]; then
    echo "Missing: $path"
    exit 1
  fi
done

echo "Structure check passed."
