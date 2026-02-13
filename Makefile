.PHONY: check-structure \
	data-platform-up data-platform-down data-platform-migrate data-platform-seed data-platform-status \
	streaming-enqueue streaming-dispatch \
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
