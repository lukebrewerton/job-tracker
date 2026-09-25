.PHONY: help sync sync-api sync-web lock dev dev-web build-web up down db-reset image image-run \
	lint lint-api lint-web format format-api format-web test test-api test-web \
	secrets-scan hooks hooks-off migrate migration openapi openapi-check types types-check

WEB := frontend

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Setup -------------------------------------------------------------------

sync: sync-api sync-web ## Install backend and frontend dependencies from the lockfiles

sync-api: ## Create/update the Python virtualenv from uv.lock
	uv sync --frozen

sync-web: ## Install frontend dependencies (and the type generator's) from their lockfiles
	cd $(WEB) && npm ci
	cd $(WEB)/codegen && npm ci

lock: ## Regenerate uv.lock from pyproject.toml (run after changing Python deps)
	uv lock

# --- Run ---------------------------------------------------------------------

dev: ## Run the API with auto-reload on http://localhost:8000 (reads .env)
	uv run uvicorn app.main:create_app --factory --reload

dev-web: ## Run the Vite dev server on http://localhost:5173 (proxies /api, /auth to :8000)
	cd $(WEB) && npm run dev

build-web: ## Build the frontend into frontend/dist
	cd $(WEB) && npm run build

# --- Local database (Postgres in Docker) ---------------------------------------

up: ## Start local Postgres (reads .env) and wait until it's healthy
	docker compose up -d --wait

down: ## Stop local Postgres (data is kept)
	docker compose down

db-reset: ## DESTRUCTIVE: delete the local Postgres volume and start fresh
	docker compose down --volumes
	docker compose up -d --wait

migrate: ## Apply database migrations (alembic upgrade head) using DATABASE_URL from .env
	uv run alembic upgrade head

migration: ## Autogenerate a migration from the models: make migration m="add jobs table"
	@test -n "$(m)" || (echo 'Usage: make migration m="describe the change"' && exit 1)
	uv run alembic revision --autogenerate -m "$(m)"

# --- Production image ------------------------------------------------------------

image: ## Build the production Docker image (job-tracker:local)
	docker build -t job-tracker:local .

image-run: ## Run the production image on http://localhost:8000 with .env
	docker run --rm -p 8000:8000 --env-file .env job-tracker:local

# --- Secrets -------------------------------------------------------------------

# Same pinned image in CI and locally; the version/digest is bumped by hand.
GITLEAKS_IMAGE := ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f

secrets-scan: ## Scan the whole git history for secrets (gitleaks via Docker)
	docker run --rm -v "$(CURDIR):/repo" $(GITLEAKS_IMAGE) \
		git /repo --config /repo/.gitleaks.toml --redact --no-banner --verbose

hooks: ## Opt in: enable the pre-commit secrets hook for this clone (needs `brew install gitleaks`)
	git config core.hooksPath .githooks
	@echo "Git hooks enabled (.githooks). Disable with: make hooks-off"

hooks-off: ## Opt out: disable the repo's git hooks for this clone
	git config --unset core.hooksPath || true
	@echo "Git hooks disabled."

# --- Quality -----------------------------------------------------------------

lint: lint-api lint-web ## Lint, format-check and type-check everything

lint-api: openapi-check ## ruff check + ruff format --check + mypy, and openapi.json is current
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

lint-web: types-check ## oxlint (type-aware, incl. type-check) + prettier --check, and types are current
	cd $(WEB) && npm run lint
	cd $(WEB) && npm run format:check

# --- The API contract ----------------------------------------------------------
# openapi.json (committed) is the contract between the backend and its clients. The
# backend writes it; clients generate their types from it, never from backend code, so
# the frontend's side works unchanged if it ever moves to its own repo (JT-49).

openapi: ## Write openapi.json from the backend code (run after changing the API)
	uv run python -m app.openapi_export > openapi.json

openapi-check: ## Fail if openapi.json doesn't match the backend code
	@uv run python -m app.openapi_export | diff -q openapi.json - > /dev/null \
		|| { echo "openapi.json is out of date: run 'make openapi' and commit it."; exit 1; }

types: ## Generate frontend/src/api/schema.ts from openapi.json (run after 'make openapi')
	cd $(WEB)/codegen && npx --no-install openapi-typescript ../../openapi.json -o ../src/api/schema.ts

types-check: ## Fail if frontend/src/api/schema.ts doesn't match openapi.json
	@tmp=$$(mktemp -d) && \
		(cd $(WEB)/codegen && npx --no-install openapi-typescript ../../openapi.json -o $$tmp/schema.ts > /dev/null) && \
		diff -q $(WEB)/src/api/schema.ts $$tmp/schema.ts > /dev/null \
		|| { echo "frontend/src/api/schema.ts is out of date: run 'make types' and commit it."; exit 1; }

format: format-api format-web ## Auto-fix lint issues and format everything

format-api: ## ruff check --fix + ruff format
	uv run ruff check --fix .
	uv run ruff format .

format-web: ## prettier --write
	cd $(WEB) && npm run format

test: test-api test-web ## Run all test suites

test-api: ## Run the backend tests (pytest) with JUnit + Cobertura reports in reports/api/
	uv run pytest \
		--junitxml=reports/api/junit.xml \
		--cov=app --cov-report=term --cov-report=xml:reports/api/coverage.xml

test-web: ## Run the frontend tests (Vitest) with JUnit + Cobertura reports in reports/web/
	cd $(WEB) && npx vitest run \
		--reporter=default --reporter=junit --outputFile.junit=../reports/web/junit.xml \
		--coverage --coverage.reporter=text-summary --coverage.reporter=cobertura \
		--coverage.reportsDirectory=../reports/web/coverage
