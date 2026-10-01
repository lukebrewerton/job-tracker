---
title: Configuration
description: Every setting, all read from environment variables.
---

Job Tracker is configured entirely with environment variables. On Render, set them on the
service; locally, they go in `.env` (copy `.env.example`, which lists them all with
placeholder values). A missing or invalid setting stops the app at start-up, without ever
printing the values.

## Required

| Variable | What it is |
|---|---|
| `PUBLIC_BASE_URL` | The address the instance is served on, e.g. `https://jobs.example.com`. Requests on any other host are redirected here, and Google redirects back to `<PUBLIC_BASE_URL>/auth/callback`. |
| `DATABASE_URL` | The Postgres connection string for the app's role (not a superuser, no `BYPASSRLS`). Neon's `postgresql://…` form works as given. |
| `OIDC_CLIENT_ID` | The OAuth client ID. |
| `OIDC_CLIENT_SECRET` | The OAuth client secret. |
| `SESSION_SECRET` | A long random value that signs the sign-in round trip. Generate one with `openssl rand -hex 32`. Render generates it for you. |
| `ALLOWED_EMAILS` | Who may sign in: a comma-separated list of email addresses, case-insensitive. Google must also confirm the address is verified. |

## Optional

| Variable | Default | What it does |
|---|---|---|
| `OIDC_ISSUER` | `https://accounts.google.com` | The sign-in provider. Any OpenID Connect provider with discovery works. |
| `SESSION_IDLE_DAYS` | `14` | Days without use before you're signed out. |
| `SESSION_MAX_DAYS` | `90` | Days after signing in before you're signed out, however much you use it. |
| `STALE_AFTER_DAYS` | `7` | Days without a status change before a job appears in the dashboard's **Needs follow-up** or **Still to apply** lists. |
| `NO_RESPONSE_AFTER_DAYS` | `14` | Days without a status change before an applied job is suggested as **No response?** instead. |
| `ENVIRONMENT` | `production` | `development` turns on the API docs at `/api/v1/docs`. Leave it as `production` anywhere public. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
| `DOCS_URL` | `https://job-tracker-docs.job-finder.dev` | The footer's **About Job Tracker** link. |
| `SOURCE_URL` | `https://github.com/lukebrewerton/job-tracker` | The footer's **Source code** link. The app is AGPL-licensed: if you run a **modified** copy for others, point this at your own repository, so its users can get the source of the version they use. |
