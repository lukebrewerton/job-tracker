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

## Backups

Optional, and off until you configure it. A scheduled GitHub Actions workflow
(`.github/workflows/backup.yml`) backs the database up every night:

1. `pg_dump` (custom format, zstd-compressed), without session rows;
2. restores the dump into a throwaway Postgres in the same run and compares row counts,
   so a backup that can't be restored fails loudly instead of being kept;
3. encrypts it with [age](https://age-encryption.org) to your public key;
4. uploads it to any S3-compatible bucket (Cloudflare R2, AWS S3, Backblaze B2, MinIO…),
   under `daily/`, and on the 1st of the month under `monthly/` too.

The job is skipped unless the `BACKUP_BUCKET` variable is set. Don't want backups? Don't
set it. There's nothing to delete or disable.

### Setting it up

1. **A key pair.** `brew install age`, then `age-keygen -o job-tracker-backup.key`. It
   prints the public key (`age1…`). Keep the key file somewhere safe, such as a password
   manager: without it, the backups can't be decrypted. It never goes to GitHub.
2. **A read-only database role.** In the Neon SQL Editor (or `psql` as the database owner),
   with your own password and the name of your app's role:

   ```sql
   CREATE ROLE jobtracker_backup LOGIN PASSWORD '<a long random password>'
     NOSUPERUSER BYPASSRLS NOCREATEDB NOCREATEROLE;
   -- The app role owns the tables, so the grants are made as it.
   GRANT <app_role> TO CURRENT_USER;
   SET ROLE <app_role>;
   GRANT USAGE ON SCHEMA public TO jobtracker_backup;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO jobtracker_backup;
   GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO jobtracker_backup;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO jobtracker_backup;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO jobtracker_backup;
   RESET ROLE;
   REVOKE <app_role> FROM CURRENT_USER;
   ```

   `BYPASSRLS` is needed: without it `pg_dump` can't read tables that have row-level
   security. The role can only read. Use its **direct** (non-pooled) connection string.
3. **A bucket.** For Cloudflare R2: create a bucket, then add
   - lifecycle rules: delete objects under `daily/` after 35 days, and under `monthly/`
     after 395 days (13 months);
   - a bucket lock rule: objects can't be deleted within 7 days of upload;
   - an API token with **Object Read & Write** on that bucket only.

   Other providers have equivalents (S3 lifecycle rules and Object Lock, for example).
4. **GitHub.** In the repo's settings:
   - Environments → New environment `backup` → deployment branches: `main` only. Add
     the secrets `BACKUP_DATABASE_URL` (the role's connection string),
     `BACKUP_S3_ACCESS_KEY_ID` and `BACKUP_S3_SECRET_ACCESS_KEY`.
   - Secrets and variables → Actions → Variables (repository): `BACKUP_BUCKET`,
     `BACKUP_AGE_RECIPIENT` (the `age1…` public key), `BACKUP_S3_ENDPOINT` (for R2,
     `https://<account id>.r2.cloudflarestorage.com`; leave unset for AWS S3), and
     optionally `BACKUP_S3_REGION` (defaults to `auto`, which R2 wants).
5. **Try it.** Actions → Backup → Run workflow. The run's summary shows the file and its
   row counts.

GitHub pauses scheduled workflows in a public repo after 60 days without activity; it
emails you, and one click re-enables it.

### Restoring

Download a backup from the bucket, then, with local Postgres running (`make up`):

```sh
make restore FILE=job-tracker-2026-09-30T0217Z.dump.age KEY=path/to/job-tracker-backup.key
```

It decrypts the file and restores it into a separate local database, `jobtracker_restore`
(recreated each time, never the one `make dev` uses), to inspect with
`docker compose exec postgres psql -U <user> -d jobtracker_restore`. To recover
production, restore the same way into a fresh database and point `DATABASE_URL` at it
(the dump holds no roles or grants, so run `pg_restore --no-owner` as your app role).

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

The code is AGPL-3.0-or-later; the logo and icons are not (see [Branding](#branding)).

## Branding

The Job Tracker logo and icons (`branding/`, and the icons in `frontend/public/`) are
© 2026 Luke Brewerton, licensed under
[CC BY-NC-ND 4.0](LICENSES/CC-BY-NC-ND-4.0.txt): you may share them unchanged, with
credit, for non-commercial purposes, but not modify them.

They identify this project. Running your own instance of it is fine, logo and all. If
you fork it and change the app, please use your own logo and name, so nobody mistakes
your version for this one.
