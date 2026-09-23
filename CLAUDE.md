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
- Frontend: React · TypeScript · Vite · Tailwind v4 · TanStack Query + Table · React Router
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
  `# SPDX-License-Identifier: AGPL-3.0-or-later` for Python, `//` for TypeScript.
- **British spelling** in prose, comments and UI copy.
- The entity is a **job** everywhere (table, API, routes) — never "application".

## Git and CI

- Branches: `<type>/JT-<n>` — conventional-commit type + Jira key, e.g. `feat/JT-25`.
- Commit subjects: conventional-commit style, imperative mood.
- Everything reaches `main` through a PR; CI must pass.
- **Never use `pull_request_target`**, and never let CI reference secrets. Deploys run
  only from `push` to `main`, through the `production` environment.
- **Never commit secrets.** `.env` is git-ignored; if a secret is ever committed,
  rotate it — deleting the file isn't enough.

## Common commands

- `make sync` — create/update the virtualenv from `uv.lock`
- `make lock` — regenerate `uv.lock` after changing dependencies
- `make dev` — run the API with auto-reload on http://localhost:8000 (needs `.env`)
- `make lint` — `ruff check` + `ruff format --check` + `mypy`
- `make format` — `ruff check --fix` + `ruff format`
- `make test` — pytest

## Definition of done (every change)

1. `make lint` and `make test` pass (and the frontend checks, once it exists).
2. Alembic migration included if the schema changed.
3. Any new env var added to `.env.example` (placeholder only); no real secret staged.
4. SPDX headers on new source files.
