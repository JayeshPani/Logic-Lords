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
python3 -m pytest -q tests/integration/test_storage_streaming_runtime.py

# Combined contract + runtime validation:
make module4-check
```

## Module-5 Contract Checks

```bash
python3 -m pytest -q services/fuzzy-inference-service/tests/test_fuzzy_service.py
python3 -m pytest -q tests/contract/test_fuzzy_inference_contracts.py

# Combined service + contract validation:
make module5-check
```

## Module-6 Contract Checks

```bash
python3 -m pytest -q services/lstm-forecast-service/tests/test_lstm_forecast_service.py
python3 -m pytest -q tests/contract/test_lstm_forecast_contracts.py

# Combined service + contract validation:
make module6-check
```

## Module-7 Contract Checks

```bash
python3 -m pytest -q services/anomaly-detection-service/tests/test_anomaly_detection_service.py
python3 -m pytest -q tests/contract/test_anomaly_detection_contracts.py

# Combined service + contract validation:
make module7-check
```

## Module-8 Contract Checks

```bash
python3 -m pytest -q services/health-score-service/tests/test_health_score_service.py
python3 -m pytest -q tests/contract/test_health_score_contracts.py

# Combined service + contract validation:
make module8-check
```

## Module-9 Contract Checks

```bash
python3 -m pytest -q apps/orchestration-service/tests/test_orchestration_service.py
python3 -m pytest -q tests/contract/test_orchestration_contracts.py

# Combined service + contract validation:
make module9-check
```

## Module-10 Contract Checks

```bash
python3 -m pytest -q services/report-generation-service/tests/test_report_generation_service.py
python3 -m pytest -q tests/contract/test_report_generation_contracts.py

# Combined service + contract validation:
make module10-check
```

## Module-11 Contract Checks

```bash
python3 -m pytest -q apps/notification-service/tests/test_notification_service.py
python3 -m pytest -q tests/contract/test_notification_contracts.py

# Combined service + contract validation:
make module11-check
```

## Module-12 Contract Checks

```bash
python3 -m pytest -q services/blockchain-verification-service/tests/test_blockchain_verification_service.py
python3 -m pytest -q tests/contract/test_blockchain_verification_contracts.py

# Combined service + contract validation:
make module12-check
```

## Module-13 Contract Checks

```bash
python3 -m pytest -q apps/api-gateway/tests/test_api_gateway.py
python3 -m pytest -q tests/contract/test_api_gateway_contracts.py

# Combined service + contract validation:
make module13-check
```
