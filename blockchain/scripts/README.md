# Blockchain Scripts

## Deploy to Sepolia (No Hardhat)

Use Dockerized Foundry deployment script:

```bash
bash blockchain/scripts/deploy_sepolia_foundry.sh
```

### Required environment variables

```bash
export BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_URL="https://sepolia.infura.io/v3/<PROJECT_ID>"
export SEPOLIA_DEPLOYER_PRIVATE_KEY="0x<64_hex_private_key>"
```

Accepted aliases:
- RPC: `SEPOLIA_RPC_URL` or `BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_URL`
- private key: `SEPOLIA_DEPLOYER_PRIVATE_KEY` or `DEPLOYER_PRIVATE_KEY`

### Outputs

After successful deployment:
- ABI: `blockchain/abi/InfraGuardVerification.abi.json`
- Deployment record: `blockchain/abi/InfraGuardVerification.sepolia.deployment.json`

Then export runtime address:

```bash
export BLOCKCHAIN_VERIFICATION_SEPOLIA_CONTRACT_ADDRESS="<deployed_address>"
```
