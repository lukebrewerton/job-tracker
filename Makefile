.PHONY: help sync sync-api sync-web lock dev dev-web build-web \
	lint lint-api lint-web format format-api format-web test test-api test-web

WEB := frontend

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Setup -------------------------------------------------------------------

sync: sync-api sync-web ## Install backend and frontend dependencies from the lockfiles

sync-api: ## Create/update the Python virtualenv from uv.lock
	uv sync --frozen

sync-web: ## Install frontend dependencies from package-lock.json
	cd $(WEB) && npm ci

lock: ## Regenerate uv.lock from pyproject.toml (run after changing Python deps)
	uv lock

# --- Run ---------------------------------------------------------------------

dev: ## Run the API with auto-reload on http://localhost:8000 (reads .env)
	uv run uvicorn app.main:create_app --factory --reload

dev-web: ## Run the Vite dev server on http://localhost:5173 (proxies /api, /auth to :8000)
	cd $(WEB) && npm run dev

build-web: ## Build the frontend into frontend/dist
	cd $(WEB) && npm run build

# --- Quality -----------------------------------------------------------------

lint: lint-api lint-web ## Lint, format-check and type-check everything

lint-api: ## ruff check + ruff format --check + mypy
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

lint-web: ## oxlint (type-aware, incl. type-check) + prettier --check
	cd $(WEB) && npm run lint
	cd $(WEB) && npm run format:check

format: format-api format-web ## Auto-fix lint issues and format everything

format-api: ## ruff check --fix + ruff format
	uv run ruff check --fix .
	uv run ruff format .

format-web: ## prettier --write
	cd $(WEB) && npm run format

test: test-api test-web ## Run all test suites

test-api: ## Run the backend tests (pytest)
	uv run pytest

test-web: ## Run the frontend tests
	@echo "No frontend tests yet (Vitest arrives with the API client, JT-30)."
