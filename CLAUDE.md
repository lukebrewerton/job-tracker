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
- **API routes live on `api_router` (`app/api.py`), never on the app**: the router itself
  requires a session, so no route can forget authentication. **Every `/api` route needs an
  isolation case in `tests/isolation.py`** (what user B gets when aimed at user A's data:
  404 or empty) — CI fails otherwise.
- **CSRF** (`app/security.py`): writes from a foreign `Origin` get 403; `POST/PUT/PATCH` to
  `/api` must be `application/json` (415). Needed because SameSite=Lax treats sibling
  `*.job-finder.dev` subdomains as the same site.
- **Pages** need a session (else 302 to `/auth/login?next=…`); built files stay public.
  API docs (`/api/docs`) exist only with `ENVIRONMENT=development`.
- **Database access:** data routes take **`UserDbSession`** (`app/sessions.py`): the request's
  single transaction, committed before the response is sent, with `app.user_id` set to the
  signed-in user so row-level security only exposes their rows (unauthenticated → 401).
  Plain `DbSession` (`app/db.py`) is for the auth code only. Never commit/begin manually in
  a route.
- **Row-level security** protects `jobs`, `status_history` and `interviews` (see the initial
  migration). It only works because the app connects as `jobtracker_app`: a role that is
  **neither superuser nor BYPASSRLS** (both skip RLS entirely). `alembic/env.py` refuses to
  run otherwise. Never point `DATABASE_URL` at Neon's `neondb_owner` or Docker's
  `POSTGRES_USER`. New user-owned tables need `user_id`, RLS (`ENABLE` + `FORCE`) and a
  `user_isolation` policy in their migration, plus isolation tests.
- **Sign-in** (`app/auth.py`): OIDC via Authlib. Identity is the provider's `sub` — never
  merge accounts by email. Access needs `email_verified is True` AND an email in
  `ALLOWED_EMAILS`. Redirect targets go through `app.redirects.safe_next()`. HTTP to the
  provider uses **httpx2** (Authlib's preferred client; plain httpx is its deprecated
  fallback). Tests fake the provider with an httpx2 `MockTransport` issuing real signed
  tokens (`create_app(oidc_transport=...)`).
- **Tests that touch the database** use the `test_db_url` / `db_engine` / `db_session`
  fixtures (a separate `<db>_test` database, rebuilt and migrated per run). They need
  `make up` locally and fail — not skip — without it.
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
- **Never use `pull_request_target`**, and never let CI reference secrets.
- **Deploys:** CI also runs on push to `main`, and Render (`render.yaml`,
  `autoDeployTrigger: checksPass`) deploys a `main` commit only once every check on it
  passes. No deploy hook or secret exists. Render's health check is `/healthz` — never
  `/readyz`, which would keep Neon awake.
- **Never commit secrets.** `.env` is git-ignored; if a secret is ever committed,
  rotate it — deleting the file isn't enough.

## Common commands

Targets come in pairs per stack (`-api`, `-web`); the bare name runs both.

- `make sync` — install backend (uv) and frontend (npm ci) dependencies
- `make lock` — regenerate `uv.lock` after changing Python dependencies
- `make dev` / `make dev-web` — API on :8000 (needs `.env`) / Vite on :5173 (proxies `/api`, `/auth`)
- `make build-web` — build the frontend into `frontend/dist`
- `make up` / `make down` — local Postgres 18 in Docker (loopback only); `make db-reset` wipes it
- `make migrate` / `make migration m="…"` — apply migrations / autogenerate one from the models
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
