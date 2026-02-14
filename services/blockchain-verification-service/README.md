# Blockchain Verification Service

Anchors maintenance evidence hashes and tracks transaction confirmation state.

## Responsibilities

- Consume `verification.record.blockchain` command payloads.
- Submit deterministic transaction hash records for evidence anchors.
- Track confirmation progress until verified.
- Emit `maintenance.verified.blockchain` event payload when confirmed.
- Expose verification query APIs.

## API

- `GET /health`
- `GET /metrics`
- `POST /record`
- `POST /verifications/{maintenance_id}/track`
- `GET /verifications`
- `GET /verifications/{maintenance_id}`
- `POST /onchain/connect` (Sepolia RPC connectivity check for dashboard button)

## Run

```bash
cd services/blockchain-verification-service
python3 -m uvicorn src.main:app --reload --port 8105
```

## Environment

- `BLOCKCHAIN_VERIFICATION_LOG_LEVEL` (default: `INFO`)
- `BLOCKCHAIN_VERIFICATION_METRICS_ENABLED` (default: `true`)
- `BLOCKCHAIN_VERIFICATION_EVENT_PRODUCED_BY` (default: `services/blockchain-verification-service`)
- `BLOCKCHAIN_VERIFICATION_REQUIRED_CONFIRMATIONS` (default: `3`)
- `BLOCKCHAIN_VERIFICATION_INITIAL_BLOCK_NUMBER` (default: `100000`)
- `BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_URL` (required for live connect checks)
- `BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_FALLBACK_URLS_CSV` (optional comma-separated fallback endpoints)
- `BLOCKCHAIN_VERIFICATION_SEPOLIA_CHAIN_ID` (default: `11155111`)
- `BLOCKCHAIN_VERIFICATION_SEPOLIA_CONTRACT_ADDRESS` (optional contract probe target)
- `BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_TIMEOUT_SECONDS` (default: `6.0`)

## Module-12 Validation

```bash
make module12-check
```

## Notes

- Transaction hashes are deterministic per verification command payload and command ID.
- Confirmation tracking is explicit via `/verifications/{maintenance_id}/track` to model polling behavior.
- Runtime state is in-memory for local development and contract validation.
- Sepolia is the only supported network for live connect checks; Hardhat is not used.
