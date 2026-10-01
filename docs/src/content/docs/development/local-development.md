---
title: Local development
description: Running Job Tracker on your own machine, and the commands you'll use.
---

## The stack

FastAPI · SQLAlchemy (async) · PostgreSQL · React · TypeScript · Vite · Tailwind ·
Google sign-in (OIDC). One repo, one container: the backend serves the built frontend.

## Setting up

Requires [uv](https://docs.astral.sh/uv/) (it installs the right Python for you), Node 24
(see `.nvmrc`; e.g. `fnm use`), and Docker, for the local database and for `make image`
(the production image).

```sh
cp .env.example .env   # then edit values
make sync              # install backend and frontend dependencies
make up                # local Postgres in Docker, with the app's DB role (make down to stop)
make migrate           # apply database migrations
make dev               # API on http://localhost:8000
make dev-web           # frontend on http://localhost:5173 (proxies API calls to :8000)
make lint              # ruff + mypy, oxlint + prettier, and licence checks
make test              # test suites (needs `make up`: API tests use a real Postgres)
make openapi types     # after changing the API: regenerate openapi.json, then the frontend types
```

For sign-in to work locally, create a separate Google OAuth client with the redirect URI
`http://localhost:8000/auth/callback`, and set `PUBLIC_BASE_URL=http://localhost:8000`
and `ENVIRONMENT=development` in `.env` (see [Configuration](/self-hosting/configuration/)).
`make seed EMAIL=you@example.com` then adds about 60 sample jobs, with interviews, to your
local account (sign in once first).

Run `make help` to list every target.

## This manual

The manual lives in `docs/` (Markdown, built with [Starlight](https://starlight.astro.build)).
`make sync-docs` installs its dependencies, `make docs` previews it on
`http://localhost:4321`, and `make docs-build` builds it, failing on broken links.

## Contributing

See [CONTRIBUTING.md](https://github.com/lukebrewerton/job-tracker/blob/main/CONTRIBUTING.md) for how to contribute and how contributions are
licensed.
