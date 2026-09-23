.PHONY: help sync lock lint format test

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

sync: ## Create/update the local virtualenv from uv.lock
	uv sync --frozen

lock: ## Regenerate uv.lock from pyproject.toml (run after changing deps)
	uv lock

lint: ## Lint + format-check + type-check (ruff check, ruff format --check, mypy)
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

format: ## Auto-fix lint issues and format the code
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run the test suite
	uv run pytest
