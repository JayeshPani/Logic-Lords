#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${INFRA_GUARD_LOG_DIR:-/tmp/infraguard}"
HOST="${INFRA_GUARD_HOST:-127.0.0.1}"

API_GATEWAY_PORT="${API_GATEWAY_PORT:-8090}"

mkdir -p "$LOG_DIR"

# Load optional .env files so you don't need to export variables in the terminal.
set -a
if [[ -f "${ROOT_DIR}/.env" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
fi
if [[ -f "${ROOT_DIR}/apps/api-gateway/.env" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/apps/api-gateway/.env"
fi
set +a

pids=()

cleanup() {
  local code="$?"
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  exit "$code"
}

trap cleanup INT TERM EXIT

start_uvicorn_bg() {
  local name="$1"
  local workdir="$2"
  local port="$3"
  shift 3

  echo "[..] ${name} -> http://${HOST}:${port}"
  (
    cd "$workdir"
    export PYTHONUNBUFFERED=1
    for kv in "$@"; do
      export "$kv"
    done
    python3 -m uvicorn src.main:app --host "$HOST" --port "$port" >"${LOG_DIR}/${name}.log" 2>&1
  ) &

  local pid="$!"
  pids+=("$pid")
}

# Defaults. Override by exporting these before running:
# - SENSOR_INGESTION_FIREBASE_DB_URL
# - SENSOR_INGESTION_FIREBASE_AUTH_TOKEN
# - API_GATEWAY_ASSISTANT_GROQ_API_KEY
# - REPORT_GENERATION_FIREBASE_STORAGE_BUCKET
# - REPORT_GENERATION_FIREBASE_CREDENTIALS_JSON

start_uvicorn_bg \
  "blockchain-verification" \
  "${ROOT_DIR}/services/blockchain-verification-service" \
  "8105" \
  "BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_FALLBACK_URLS_CSV=${BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_FALLBACK_URLS_CSV:-https://ethereum-sepolia-rpc.publicnode.com,https://sepolia.gateway.tenderly.co,https://rpc.sepolia.org}"

start_uvicorn_bg \
  "report-generation" \
  "${ROOT_DIR}/services/report-generation-service" \
  "8202" \
  "REPORT_GENERATION_FIREBASE_STORAGE_BUCKET=${REPORT_GENERATION_FIREBASE_STORAGE_BUCKET:-}" \
  "REPORT_GENERATION_FIREBASE_CREDENTIALS_JSON=${REPORT_GENERATION_FIREBASE_CREDENTIALS_JSON:-}"

start_uvicorn_bg \
  "notification-service" \
  "${ROOT_DIR}/apps/notification-service" \
  "8201"

start_uvicorn_bg \
  "orchestration-service" \
  "${ROOT_DIR}/apps/orchestration-service" \
  "8200" \
  "ORCHESTRATION_NOTIFICATION_BASE_URL=${ORCHESTRATION_NOTIFICATION_BASE_URL:-http://127.0.0.1:8201}" \
  "ORCHESTRATION_REPORT_GENERATION_BASE_URL=${ORCHESTRATION_REPORT_GENERATION_BASE_URL:-http://127.0.0.1:8202}" \
  "ORCHESTRATION_BLOCKCHAIN_VERIFICATION_BASE_URL=${ORCHESTRATION_BLOCKCHAIN_VERIFICATION_BASE_URL:-http://127.0.0.1:8105}"

start_uvicorn_bg \
  "sensor-ingestion" \
  "${ROOT_DIR}/apps/sensor-ingestion-service" \
  "8100" \
  "SENSOR_INGESTION_FIREBASE_DB_URL=${SENSOR_INGESTION_FIREBASE_DB_URL:-}" \
  "SENSOR_INGESTION_FIREBASE_AUTH_TOKEN=${SENSOR_INGESTION_FIREBASE_AUTH_TOKEN:-}" \
  "SENSOR_INGESTION_FIREBASE_PATH_PREFIX=${SENSOR_INGESTION_FIREBASE_PATH_PREFIX:-infraguard}"

start_uvicorn_bg \
  "api-gateway" \
  "${ROOT_DIR}/apps/api-gateway" \
  "${API_GATEWAY_PORT}" \
  "API_GATEWAY_ORCHESTRATION_BASE_URL=${API_GATEWAY_ORCHESTRATION_BASE_URL:-http://127.0.0.1:8200}" \
  "API_GATEWAY_REPORT_GENERATION_BASE_URL=${API_GATEWAY_REPORT_GENERATION_BASE_URL:-http://127.0.0.1:8202}" \
  "API_GATEWAY_BLOCKCHAIN_VERIFICATION_BASE_URL=${API_GATEWAY_BLOCKCHAIN_VERIFICATION_BASE_URL:-http://127.0.0.1:8105}" \
  "API_GATEWAY_SENSOR_INGESTION_BASE_URL=${API_GATEWAY_SENSOR_INGESTION_BASE_URL:-http://127.0.0.1:8100}" \
  "API_GATEWAY_AUTH_BEARER_TOKENS_CSV=${API_GATEWAY_AUTH_BEARER_TOKENS_CSV:-dev-token}" \
  "API_GATEWAY_AUTH_TOKEN_ROLES_CSV=${API_GATEWAY_AUTH_TOKEN_ROLES_CSV:-dev-token:organization|operator}" \
  "API_GATEWAY_ASSISTANT_GROQ_API_KEY=${API_GATEWAY_ASSISTANT_GROQ_API_KEY:-}"

echo ""
echo "[ok] stack launched (logs in ${LOG_DIR})"
echo "Dashboard:"
echo "  http://${HOST}:${API_GATEWAY_PORT}/dashboard"
echo ""

wait
