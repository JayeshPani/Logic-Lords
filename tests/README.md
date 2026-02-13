# Test Strategy

- `tests/contract`: schema and API contract tests
- `tests/integration`: service-to-service behavior tests
- `tests/e2e`: full workflow tests from ingestion to blockchain verification
- `tests/performance`: load and stress tests

## Step-3 AI Contract Check

```bash
python3 scripts/validate_ai_contracts.py --fail-on-invalid
python3 -m pytest -q tests/integration/test_ai_contract_validation.py

# Combined with step-2 evaluation:
make ai-check
```

## Module-4 Artifact Checks

```bash
python3 -m pytest -q tests/contract/test_storage_streaming_artifacts.py
```
