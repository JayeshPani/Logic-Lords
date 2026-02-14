# Ledger + Service Wallet Runbook

## Scope
- Canonical verification path is backend-ledger (`orchestration -> report-generation -> blockchain-verification`).
- Dashboard wallet is optional and used for operator attribution only.
- Default tx mode is deterministic; live Sepolia writes are feature-gated.

## Phase 1 (Deterministic) Startup
1. Start `report-generation-service`.
2. Start `blockchain-verification-service`.
3. Start `orchestration-service`.
4. Start `api-gateway`.
5. Open dashboard and complete a maintenance workflow.

Expected:
- `POST /workflows/{workflow_id}/maintenance/completed` returns `verification_summary`.
- `GET /maintenance/{maintenance_id}/verification` returns proxied verification record.
- `POST /maintenance/{maintenance_id}/verification/track` increments confirmations until `confirmed`.

## Required Environment Variables

### Orchestration
- `ORCHESTRATION_REPORT_GENERATION_BASE_URL` (default `http://127.0.0.1:8202`)
- `ORCHESTRATION_REPORT_GENERATION_TIMEOUT_SECONDS` (default `8.0`)
- `ORCHESTRATION_BLOCKCHAIN_VERIFICATION_BASE_URL` (default `http://127.0.0.1:8105`)
- `ORCHESTRATION_BLOCKCHAIN_VERIFICATION_TIMEOUT_SECONDS` (default `8.0`)

### API Gateway
- `API_GATEWAY_BLOCKCHAIN_VERIFICATION_BASE_URL`
- `API_GATEWAY_BLOCKCHAIN_VERIFICATION_FALLBACK_URLS_CSV`
- `API_GATEWAY_BLOCKCHAIN_VERIFICATION_TIMEOUT_SECONDS` (default `8.0`)

### Blockchain Verification
- `BLOCKCHAIN_VERIFICATION_TX_MODE` (`deterministic` or `live`; default `deterministic`)
- `BLOCKCHAIN_VERIFICATION_SIGNER_PRIVATE_KEY` (required only in `live`)
- `BLOCKCHAIN_VERIFICATION_GAS_LIMIT` (default `250000`)
- `BLOCKCHAIN_VERIFICATION_MAX_GAS_GWEI` (default `30`)
- `BLOCKCHAIN_VERIFICATION_TRACK_INTERVAL_SECONDS` (default `20`)
- `BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_URL`
- `BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_FALLBACK_URLS_CSV`

## Phase 2 (Live Sepolia) Enablement
1. Install blockchain service live dependencies:
   - `pip install '.[live]'` in `services/blockchain-verification-service`
2. Fund service wallet on Sepolia.
3. Set:
   - `BLOCKCHAIN_VERIFICATION_TX_MODE=live`
   - `BLOCKCHAIN_VERIFICATION_SIGNER_PRIVATE_KEY=<service-wallet-private-key>`
4. Restart blockchain verification service.
5. Trigger maintenance completion and inspect:
   - `verification_status`
   - `tx_hash`
   - `confirmations/required_confirmations`

Rollback:
- Set `BLOCKCHAIN_VERIFICATION_TX_MODE=deterministic` and restart service.

## Dashboard Operator Flow
1. Open `Ledger` tab.
2. Click `Connect Sepolia` for RPC reachability.
3. Click `Track Verification` to trigger confirmation tracking.
4. Optional: click `Connect Wallet` to add operator identity context.
