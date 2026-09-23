# job-tracker

A self-hostable job application tracker. Save a job from a posting page with one click
(via the companion Firefox extension), then track it from "saved" through to an offer —
with a dashboard showing what needs following up, what's still to apply for, and what's
gone quiet.

Single user per deployment: fork it, set your own allowed email address, and host your
own instance.

> **Status:** early development — not usable yet.

## Stack

FastAPI · SQLAlchemy (async) · PostgreSQL · React · TypeScript · Vite · Tailwind ·
Google sign-in (OIDC). One repo, one container: the backend serves the built frontend.

## Local development

Requires [uv](https://docs.astral.sh/uv/) (it installs the right Python for you) and
Node 24 (see `.nvmrc`; e.g. `fnm use`).

```sh
cp .env.example .env   # then edit values
make sync              # install backend and frontend dependencies
make up                # local Postgres in Docker (make down to stop)
make dev               # API on http://localhost:8000
make dev-web           # frontend on http://localhost:5173 (proxies API calls to :8000)
make lint              # ruff + mypy, oxlint + prettier
make test              # test suites
```

Requires Docker for the local database and for `make image` (the production image).
Run `make help` to list every target. More setup steps (migrations, sign-in) will be
added as those pieces land.

## Licence

[AGPL-3.0-or-later](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) for how
contributions are licensed, and [SECURITY.md](SECURITY.md) to report a vulnerability.
