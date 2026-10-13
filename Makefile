# speech-bridge developer tasks. Run `make help` for the list.
.DEFAULT_GOAL := help
SHELL := /bin/bash

PYTHON ?= python3
TF     ?= terraform
TF_DIR ?= infra/terraform/modules
IMAGE  ?= speech-bridge:latest

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------ Python --
.PHONY: install
install: ## Install runtime + dev dependencies
	$(PYTHON) -m pip install -r speech_engine/requirements.txt -r requirements-dev.txt

.PHONY: run
run: ## Run the API locally with autoreload
	uvicorn speech_engine.main:app --reload --host 0.0.0.0 --port $${PORT:-8000}

.PHONY: live
live: ## Run live microphone transcription client
	./run_live_hebrew.sh

.PHONY: benchmark
benchmark: ## Run Hebrew models benchmark matrix
	./scripts/compare_hebrew.sh --model all

.PHONY: record
record: ## Record voice and benchmark all models
	./scripts/record_and_test.sh

.PHONY: download
download: ## Download Whisper model with progress bar (make download MODEL=large-v3)
	./scripts/download_model.py $(MODEL)

.PHONY: test
test: ## Run the pytest suite
	pytest -q

.PHONY: lint
lint: ## Lint with ruff
	ruff check speech_engine tests

.PHONY: fmt
fmt: ## Auto-format with ruff
	ruff format speech_engine tests
	ruff check --fix speech_engine tests

.PHONY: typecheck
typecheck: ## Static type-check with mypy
	mypy speech_engine

.PHONY: check
check: lint typecheck test ## Run all Python quality gates

# ------------------------------------------------------------------ Docker --
.PHONY: docker-build
docker-build: ## Build the container image
	docker build -t $(IMAGE) .

.PHONY: docker-run
docker-run: ## Run the container image
	docker run --rm -p 8000:8000 --env-file .env -v model-cache:/models $(IMAGE)

.PHONY: compose-up
compose-up: ## Start via docker compose
	docker compose up --build

# --------------------------------------------------------------- Terraform --
.PHONY: tf-fmt
tf-fmt: ## Check Terraform formatting
	$(TF) fmt -check -recursive infra/terraform

.PHONY: tf-validate
tf-validate: ## Validate every Terraform module
	@for d in $(TF_DIR)/*; do \
		echo "== validate $$d =="; \
		$(TF) -chdir=$$d init -backend=false -input=false >/dev/null && \
		$(TF) -chdir=$$d validate || exit 1; \
	done

.PHONY: tf-plan-%
tf-plan-%: ## Plan a cloud module, e.g. `make tf-plan-aws` (needs creds + tfvars)
	$(TF) -chdir=$(TF_DIR)/$* init -input=false
	$(TF) -chdir=$(TF_DIR)/$* plan -var-file=$(CURDIR)/infra/terraform/envs/$*.tfvars
