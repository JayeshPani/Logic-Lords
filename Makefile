.PHONY: check-structure \
	data-platform-up data-platform-down data-platform-migrate data-platform-seed data-platform-status \
	streaming-enqueue streaming-dispatch \
	module4-check module5-check module6-check module7-check module8-check module9-check module10-check module11-check module12-check \
	ai-step2 ai-step3 ai-step3-test ai-check

check-structure:
	bash scripts/check-structure.sh

PYTHON ?= python3
AI_EVAL_ARGS ?=
AI_CONTRACT_ARGS ?= --fail-on-invalid

ai-step2:
	$(PYTHON) data-platform/ml/evaluation/evaluate_all_models.py $(AI_EVAL_ARGS)

ai-step3:
	$(PYTHON) scripts/validate_ai_contracts.py $(AI_CONTRACT_ARGS)

ai-step3-test:
	$(PYTHON) -m pytest -q tests/integration/test_ai_contract_validation.py

ai-check: ai-step2 ai-step3 ai-step3-test

data-platform-up:
	bash scripts/data_platform_up.sh

data-platform-down:
	bash scripts/data_platform_down.sh

data-platform-migrate:
	bash scripts/storage_migrate.sh

data-platform-seed:
	bash scripts/storage_seed_dev.sh

data-platform-status:
	bash scripts/storage_status.sh

streaming-enqueue:
	bash scripts/streaming_enqueue_event.sh

streaming-dispatch:
	bash scripts/streaming_dispatch_outbox.sh

module4-check:
	$(PYTHON) -m pytest -q tests/contract/test_storage_streaming_artifacts.py
	$(PYTHON) -m pytest -q tests/integration/test_storage_streaming_runtime.py

module5-check:
	$(PYTHON) -m pytest -q services/fuzzy-inference-service/tests/test_fuzzy_service.py
	$(PYTHON) -m pytest -q tests/contract/test_fuzzy_inference_contracts.py

module6-check:
	$(PYTHON) -m pytest -q services/lstm-forecast-service/tests/test_lstm_forecast_service.py
	$(PYTHON) -m pytest -q tests/contract/test_lstm_forecast_contracts.py

module7-check:
	$(PYTHON) -m pytest -q services/anomaly-detection-service/tests/test_anomaly_detection_service.py
	$(PYTHON) -m pytest -q tests/contract/test_anomaly_detection_contracts.py

module8-check:
	$(PYTHON) -m pytest -q services/health-score-service/tests/test_health_score_service.py
	$(PYTHON) -m pytest -q tests/contract/test_health_score_contracts.py

module9-check:
	$(PYTHON) -m pytest -q apps/orchestration-service/tests/test_orchestration_service.py
	$(PYTHON) -m pytest -q tests/contract/test_orchestration_contracts.py

module10-check:
	$(PYTHON) -m pytest -q services/report-generation-service/tests/test_report_generation_service.py
	$(PYTHON) -m pytest -q tests/contract/test_report_generation_contracts.py

module11-check:
	$(PYTHON) -m pytest -q apps/notification-service/tests/test_notification_service.py
	$(PYTHON) -m pytest -q tests/contract/test_notification_contracts.py

module12-check:
	$(PYTHON) -m pytest -q services/blockchain-verification-service/tests/test_blockchain_verification_service.py
	$(PYTHON) -m pytest -q tests/contract/test_blockchain_verification_contracts.py
