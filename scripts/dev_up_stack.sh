#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${INFRA_GUARD_LOG_DIR:-/tmp/infraguard}"
HOST="${INFRA_GUARD_HOST:-127.0.0.1}"

mkdir -p "$LOG_DIR"

healthcheck() {
  local port="$1"
  local path="${2:-/health}"
  curl -fsS "http://${HOST}:${port}${path}" >/dev/null 2>&1
}

start_uvicorn() {
  local name="$1"
  local workdir="$2"
  local port="$3"
  local health_path="${4:-/health}"
  shift 4

  if healthcheck "$port" "$health_path"; then
    echo "[ok] ${name} already running on ${HOST}:${port}"
    return 0
  fi

  echo "[..] starting ${name} on ${HOST}:${port}"
  (
    cd "$workdir"
    export PYTHONUNBUFFERED=1
    for kv in "$@"; do
      export "$kv"
    done
    nohup python3 -m uvicorn src.main:app --host "$HOST" --port "$port" >"${LOG_DIR}/${name}.log" 2>&1 &
    echo "$!" >"${LOG_DIR}/${name}.pid"
  )

  for _ in $(seq 1 40); do
    if healthcheck "$port" "$health_path"; then
      echo "[ok] ${name} is healthy"
      return 0
    fi
    sleep 0.25
  done

  echo "[warn] ${name} did not become healthy in time. Log: ${LOG_DIR}/${name}.log"
  return 0
}

# Optional: set these before running for full functionality:
# - SENSOR_INGESTION_FIREBASE_DB_URL
# - API_GATEWAY_ASSISTANT_GROQ_API_KEY
# - REPORT_GENERATION_FIREBASE_STORAGE_BUCKET + REPORT_GENERATION_FIREBASE_CREDENTIALS_JSON (for evidence uploads)

start_uvicorn \
  "blockchain-verification" \
  "${ROOT_DIR}/services/blockchain-verification-service" \
  "8105" \
  "/health" \
  "BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_FALLBACK_URLS_CSV=${BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_FALLBACK_URLS_CSV:-https://ethereum-sepolia-rpc.publicnode.com,https://sepolia.gateway.tenderly.co,https://rpc.sepolia.org}"

start_uvicorn \
  "report-generation" \
  "${ROOT_DIR}/services/report-generation-service" \
  "8202" \
  "/health" \
  "REPORT_GENERATION_FIREBASE_STORAGE_BUCKET=${REPORT_GENERATION_FIREBASE_STORAGE_BUCKET:-}" \
  "REPORT_GENERATION_FIREBASE_CREDENTIALS_JSON=${REPORT_GENERATION_FIREBASE_CREDENTIALS_JSON:-}"

start_uvicorn \
  "notification-service" \
  "${ROOT_DIR}/apps/notification-service" \
  "8201" \
  "/health"

start_uvicorn \
  "orchestration-service" \
  "${ROOT_DIR}/apps/orchestration-service" \
  "8200" \
  "/health" \
  "ORCHESTRATION_NOTIFICATION_BASE_URL=${ORCHESTRATION_NOTIFICATION_BASE_URL:-http://127.0.0.1:8201}" \
  "ORCHESTRATION_REPORT_GENERATION_BASE_URL=${ORCHESTRATION_REPORT_GENERATION_BASE_URL:-http://127.0.0.1:8202}" \
  "ORCHESTRATION_BLOCKCHAIN_VERIFICATION_BASE_URL=${ORCHESTRATION_BLOCKCHAIN_VERIFICATION_BASE_URL:-http://127.0.0.1:8105}"

start_uvicorn \
  "sensor-ingestion" \
  "${ROOT_DIR}/apps/sensor-ingestion-service" \
  "8100" \
  "/health" \
  "SENSOR_INGESTION_FIREBASE_DB_URL=${SENSOR_INGESTION_FIREBASE_DB_URL:-}" \
  "SENSOR_INGESTION_FIREBASE_AUTH_TOKEN=${SENSOR_INGESTION_FIREBASE_AUTH_TOKEN:-}" \
  "SENSOR_INGESTION_FIREBASE_PATH_PREFIX=${SENSOR_INGESTION_FIREBASE_PATH_PREFIX:-infraguard}"

start_uvicorn \
  "api-gateway" \
  "${ROOT_DIR}/apps/api-gateway" \
  "${API_GATEWAY_PORT:-8090}" \
  "/health" \
  "API_GATEWAY_ORCHESTRATION_BASE_URL=${API_GATEWAY_ORCHESTRATION_BASE_URL:-http://127.0.0.1:8200}" \
  "API_GATEWAY_REPORT_GENERATION_BASE_URL=${API_GATEWAY_REPORT_GENERATION_BASE_URL:-http://127.0.0.1:8202}" \
  "API_GATEWAY_BLOCKCHAIN_VERIFICATION_BASE_URL=${API_GATEWAY_BLOCKCHAIN_VERIFICATION_BASE_URL:-http://127.0.0.1:8105}" \
  "API_GATEWAY_SENSOR_INGESTION_BASE_URL=${API_GATEWAY_SENSOR_INGESTION_BASE_URL:-http://127.0.0.1:8100}" \
  "API_GATEWAY_AUTH_BEARER_TOKENS_CSV=${API_GATEWAY_AUTH_BEARER_TOKENS_CSV:-dev-token}" \
  "API_GATEWAY_AUTH_TOKEN_ROLES_CSV=${API_GATEWAY_AUTH_TOKEN_ROLES_CSV:-dev-token:organization|operator}" \
  "API_GATEWAY_ASSISTANT_GROQ_API_KEY=${API_GATEWAY_ASSISTANT_GROQ_API_KEY:-}"

echo ""
echo "Dashboard:"
echo "  http://${HOST}:${API_GATEWAY_PORT:-8090}/dashboard"
echo ""
