#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BLOCKCHAIN_DIR="${ROOT_DIR}/blockchain"
CONTRACT_REF="contracts/InfraGuardVerification.sol:InfraGuardVerification"
FOUNDRY_IMAGE="${FOUNDRY_DOCKER_IMAGE:-ghcr.io/foundry-rs/foundry:latest}"

RPC_URL="${SEPOLIA_RPC_URL:-${BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_URL:-}}"
PRIVATE_KEY="${SEPOLIA_DEPLOYER_PRIVATE_KEY:-${DEPLOYER_PRIVATE_KEY:-}}"
EXPECTED_CHAIN_ID="11155111"

if [ -z "${RPC_URL}" ]; then
  echo "Missing RPC URL. Set SEPOLIA_RPC_URL or BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_URL." >&2
  exit 1
fi

if [ -z "${PRIVATE_KEY}" ]; then
  echo "Missing deployer key. Set SEPOLIA_DEPLOYER_PRIVATE_KEY or DEPLOYER_PRIVATE_KEY." >&2
  exit 1
fi

if ! [[ "${PRIVATE_KEY}" =~ ^0x[0-9a-fA-F]{64}$ ]]; then
  echo "Invalid private key format. Expected 0x + 64 hex characters." >&2
  exit 1
fi

run_forge() {
  local cmd
  printf -v cmd '%q ' "$@"
  cmd="forge ${cmd}"
  docker run --rm \
    -v "${ROOT_DIR}:/repo" \
    -w /repo/blockchain \
    "${FOUNDRY_IMAGE}" "${cmd}"
}

run_cast() {
  local cmd
  printf -v cmd '%q ' "$@"
  cmd="cast ${cmd}"
  docker run --rm \
    -v "${ROOT_DIR}:/repo" \
    -w /repo/blockchain \
    "${FOUNDRY_IMAGE}" "${cmd}"
}

echo "Validating Sepolia RPC chain id..."
CHAIN_ID="$(run_cast chain-id --rpc-url "${RPC_URL}" | tr -d '[:space:]')"
if [ "${CHAIN_ID}" != "${EXPECTED_CHAIN_ID}" ]; then
  echo "RPC chain id mismatch. Expected ${EXPECTED_CHAIN_ID} (Sepolia), got ${CHAIN_ID}." >&2
  exit 1
fi

mkdir -p "${BLOCKCHAIN_DIR}/abi"

echo "Building InfraGuardVerification contract..."
run_forge build --silent

echo "Deploying contract to Sepolia..."
DEPLOY_JSON="$(run_forge create "${CONTRACT_REF}" --rpc-url "${RPC_URL}" --private-key "${PRIVATE_KEY}" --broadcast --json)"

deployed_to="$(printf '%s' "${DEPLOY_JSON}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("deployedTo",""))')"
transaction_hash="$(printf '%s' "${DEPLOY_JSON}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("transactionHash",""))')"

if ! [[ "${deployed_to}" =~ ^0x[0-9a-fA-F]{40}$ ]]; then
  echo "Failed to parse deployed contract address from forge output." >&2
  echo "Output: ${DEPLOY_JSON}" >&2
  exit 1
fi

ARTIFACT_JSON="${BLOCKCHAIN_DIR}/out/InfraGuardVerification.sol/InfraGuardVerification.json"
ABI_OUT="${BLOCKCHAIN_DIR}/abi/InfraGuardVerification.abi.json"
DEPLOY_OUT="${BLOCKCHAIN_DIR}/abi/InfraGuardVerification.sepolia.deployment.json"

python3 - "${ARTIFACT_JSON}" "${ABI_OUT}" <<'PY'
import json, pathlib, sys
artifact = pathlib.Path(sys.argv[1])
abi_out = pathlib.Path(sys.argv[2])
if not artifact.exists():
    raise SystemExit(f"artifact missing: {artifact}")
payload = json.loads(artifact.read_text())
abi = payload.get("abi")
if abi is None:
    raise SystemExit("artifact missing abi")
abi_out.write_text(json.dumps(abi, indent=2) + "\n")
PY

python3 - "${DEPLOY_OUT}" "${deployed_to}" "${transaction_hash}" <<'PY'
import json, pathlib, sys
from datetime import datetime, timezone
out = pathlib.Path(sys.argv[1])
address = sys.argv[2]
tx_hash = sys.argv[3]
record = {
    "network": "sepolia",
    "chain_id": 11155111,
    "contract_name": "InfraGuardVerification",
    "contract_address": address,
    "deployment_tx_hash": tx_hash or None,
    "deployed_at": datetime.now(tz=timezone.utc).isoformat(),
}
out.write_text(json.dumps(record, indent=2) + "\n")
PY

cat <<MSG

Deployment complete.
Contract Address: ${deployed_to}
Transaction Hash: ${transaction_hash:-unknown}
ABI File: ${ABI_OUT}
Record File: ${DEPLOY_OUT}

Export this for runtime:
export BLOCKCHAIN_VERIFICATION_SEPOLIA_CONTRACT_ADDRESS="${deployed_to}"

MSG
