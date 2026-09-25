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
make up                # local Postgres in Docker, with the app's DB role (make down to stop)
make migrate           # apply database migrations
make dev               # API on http://localhost:8000
make dev-web           # frontend on http://localhost:5173 (proxies API calls to :8000)
make lint              # ruff + mypy, oxlint + prettier
make test              # test suites (needs `make up`: API tests use a real Postgres)
make openapi types     # after changing the API: regenerate openapi.json, then the frontend types
```

Requires Docker for the local database and for `make image` (the production image).
Run `make help` to list every target. More setup steps (sign-in) will be added as those
pieces land.

## Deploying your own instance

The repo includes a [Render](https://render.com) Blueprint (`render.yaml`): one Docker web
service on the free plan, backed by a [Neon](https://neon.tech) Postgres database.

1. **Database (Neon).** Create a project, then — in the SQL Editor, not the Roles page —
   create a dedicated app role that is **not** a superuser and has **no BYPASSRLS** (either
   would silently disable the per-user row-level security), and make it the database owner.
   Use its **direct** (non-pooled) connection string as `DATABASE_URL`. Migrations refuse to
   run as a role that would bypass row-level security.
2. **Sign-in (Google).** Create an OAuth client (Web application) with the redirect URI
   `<your public URL>/auth/callback`.
3. **Render.** New → Blueprint → this repo. Enter the values it prompts for
   (`PUBLIC_BASE_URL`, `DATABASE_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`,
   `ALLOWED_EMAILS`); `SESSION_SECRET` is generated for you. Render deploys each commit on
   `main` only after all its CI checks pass. Migrations run on every start.

Render's health check uses `/healthz`, which never touches the database — so Neon can
scale to zero when you're not using the app.

## Secret scanning

Every PR is scanned for secrets (API keys, private keys, passwords, …) with
[gitleaks](https://github.com/gitleaks/gitleaks); a PR that contains one can't be merged.
You can run the same scan over the whole history locally with `make secrets-scan`
(needs Docker).

### Optional pre-commit hook

CI only sees a secret after it has been pushed — and in a public repo, that means it's
already exposed and must be rotated. The optional pre-commit hook catches it on your
machine first, by scanning your staged changes before each commit.

Git hooks are never cloned or pushed, so this is **opt-in, per clone**:

```sh
brew install gitleaks   # or see https://github.com/gitleaks/gitleaks#installing
make hooks              # turn the hook on for this clone
make hooks-off          # turn it off again
```

- If a secret is found, the commit is stopped and the finding is shown (redacted).
- If the hook is on but gitleaks isn't installed, the commit is stopped with a message
  explaining how to install it or turn the hook off.
- To skip the hook for a single commit: `git commit --no-verify` (CI still checks).
- Genuine false positives can be allow-listed in `.gitleaks.toml`, with a comment
  explaining why.

## Licence

[AGPL-3.0-or-later](LICENSE). See [CONTRIBUTING.md](CONTRIBUTING.md) for how
contributions are licensed, and [SECURITY.md](SECURITY.md) to report a vulnerability.
