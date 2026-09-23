# CLAUDE.md — Job Tracker

Operating context for Claude Code working in this repo. If `ARCHITECTURE.md` exists
alongside this file, read it first — it's the full design record (kept local, not
committed). If `CLAUDE.local.md` exists, read that too.

## What this is

A self-hostable, **single-user-per-deployment** job application tracker. A Firefox
extension (separate repo, `job-tracker-extension`) opens `/jobs/new?url=…&title=…` on
the user's own instance; this app is where the tracking happens. Anyone can fork and
host their own instance — nothing instance-specific (domains, emails) is hardcoded.

## Stack

- Python 3.14 · FastAPI · Pydantic v2 · SQLAlchemy 2.x **async** (psycopg 3) · Alembic
- PostgreSQL (Neon in production, Docker Compose locally)
- Auth: app-level OIDC via Authlib (Google by default), DB-backed sessions
- Frontend (`frontend/`): React · TypeScript 7 · Vite · Tailwind v4 · TanStack Query + Table ·
  React Router · Node 24 (`.nvmrc`) · npm
- Frontend tooling: **oxlint** (type-aware via `oxlint-tsgolint`, which also type-checks) ·
  **prettier** (+ Tailwind class sorting). Not ESLint: typescript-eslint doesn't support TS 7 yet
- One repo, one deployable: a multi-stage Dockerfile builds the frontend and the backend
  serves it, so everything is single-origin (one cookie, no CORS)
- Tooling: **uv** (env/deps) · **ruff** (lint *and* format — there is no Black) ·
  **mypy** (pragmatic, not `--strict`) · pytest

## Conventions

- **Config via env vars only** (12-factor). Every var the code reads is added to
  `.env.example` with a placeholder, in the same change that introduces it.
- **Dependencies via uv, always locked.** `uv add <pkg>` / `uv add --dev <pkg>`, then
  commit the updated `uv.lock`. The Docker build uses `uv sync --frozen`.
- **All schema changes via Alembic.** Enums are `native_enum=False` (text + CHECK), not
  native Postgres enums.
- **SPDX header** as the first lines of every authored source file (before any
  docstring): `# Copyright (C) 2026 Luke Brewerton` /
  `# SPDX-License-Identifier: AGPL-3.0-or-later` for Python, `//` for TypeScript, `/* */` for
  CSS, `<!-- -->` for HTML (after the doctype).
- **British spelling** in prose, comments and UI copy.
- The entity is a **job** everywhere (table, API, routes) — never "application".

## Git and CI

- Branches: `<type>/JT-<n>` — conventional-commit type + Jira key, e.g. `feat/JT-25`.
- Commit subjects: conventional-commit style, imperative mood.
- Everything reaches `main` through a PR; CI must pass.
- CI (`.github/workflows/ci.yml`) runs jobs `lint-api`, `test-api`, `lint-web`, `test-web`,
  `docker-build`, `secrets-scan` — each calls the matching `make` target. Job names are
  required status checks: don't rename them without updating the ruleset.
- **Never use `pull_request_target`**, and never let CI reference secrets. Deploys run
  only from `push` to `main`, through the `production` environment.
- **Never commit secrets.** `.env` is git-ignored; if a secret is ever committed,
  rotate it — deleting the file isn't enough.

## Common commands

Targets come in pairs per stack (`-api`, `-web`); the bare name runs both.

- `make sync` — install backend (uv) and frontend (npm ci) dependencies
- `make lock` — regenerate `uv.lock` after changing Python dependencies
- `make dev` / `make dev-web` — API on :8000 (needs `.env`) / Vite on :5173 (proxies `/api`, `/auth`)
- `make build-web` — build the frontend into `frontend/dist`
- `make up` / `make down` — local Postgres 18 in Docker (loopback only); `make db-reset` wipes it
- `make image` / `make image-run` — build and run the production image locally (uses `.env`)
- `make lint` — ruff + mypy, and oxlint (type-aware, incl. type-check) + prettier --check
- `make format` — ruff fix/format and prettier --write
- `make secrets-scan` — gitleaks over the full git history (pinned Docker image, same as CI)
- `make hooks` / `make hooks-off` — opt in/out of the pre-commit secrets hook (needs
  `brew install gitleaks`)
- `make test` — pytest with JUnit + coverage reports in `reports/` (git-ignored), and frontend
  tests once they exist

## Definition of done (every change)

1. `make lint` and `make test` pass (both stacks).
2. Alembic migration included if the schema changed.
3. Any new env var added to `.env.example` (placeholder only); no real secret staged.
4. SPDX headers on new source files.
