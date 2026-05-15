.PHONY: help format lint check fix clean test test-unit test-integration test-contract test-e2e test-e2e-up test-e2e-down

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# --- Code quality ---

format: ## Format code with ruff
	uv run ruff format .

lint: ## Lint code with ruff
	uv run ruff check .

check: ## Check code (lint + format check) without fixing
	uv run ruff check .
	uv run ruff format --check .

fix: ## Fix linting issues automatically
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run fast test suite (unit + integration + contract, no real services)
	uv run pytest tests/unit/ tests/integration/ tests/contract/ -v

test-unit: ## Run unit tests only
	uv run pytest tests/unit/ -v

test-integration: ## Run integration tests only (in-memory SQLite)
	uv run pytest tests/integration/ -v

test-contract: ## Run contract tests only
	uv run pytest tests/contract/ -v

test-e2e-up: ## Start test infrastructure (Postgres, Redis, RabbitMQ)
	docker compose -f docker/docker-compose.test.yml up -d --wait

test-e2e-down: ## Stop test infrastructure
	docker compose -f docker/docker-compose.test.yml down

test-e2e: ## Run e2e tests against real services (start infra first with test-e2e-up)
	uv run pytest tests/e2e/ -v

test-all: test test-e2e ## Run all tests (fast + e2e)

clean: ## Remove cache and temporary files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# --- Docker ---

.PHONY: docker-build docker-up docker-down docker-base docker-logs docker-migrate docker-shell

docker-build: ## Build Docker images
	docker compose -f docker/docker-compose.yml build

docker-up: ## Start all services (backend + infra)
	docker compose -f docker/docker-compose.yml up -d

docker-down: ## Stop all services
	docker compose -f docker/docker-compose.yml down

docker-base: ## Start infrastructure services only (db, redis, minio, milvus)
	docker compose -f docker/docker-compose.base.yml up -d

docker-logs: ## Tail backend logs
	docker compose -f docker/docker-compose.yml logs -f backend

docker-migrate: ## Run Alembic migrations inside container
	docker compose -f docker/docker-compose.yml exec backend alembic upgrade head

docker-shell: ## Open a shell in the backend container
	docker compose -f docker/docker-compose.yml exec backend bash

# --- Local dev ---

.PHONY: dev worker beat

dev: ## Run local dev server
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

worker: ## Run Celery worker
	uv run celery -A app.celery_app worker --loglevel=info

beat: ## Run Celery beat scheduler
	uv run celery -A app.celery_app beat --loglevel=info
