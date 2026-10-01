---
title: Deploying your own instance
description: Running your own Job Tracker on Render and Neon's free tiers, with Google sign-in.
---

Job Tracker is one Docker container: the backend serves the built frontend, so there's a
single address and a single sign-in cookie. The repo includes a [Render](https://render.com)
Blueprint (`render.yaml`): one Docker web service on the free plan, backed by a
[Neon](https://neon.tech) Postgres database.

Each deployment can have a few users (whoever is in `ALLOWED_EMAILS`), and every user only
ever sees their own jobs: the database enforces it with row-level security.

## 1. Database (Neon)

Create a project, then, in the SQL Editor (not the Roles page), create a dedicated app role
that is **not** a superuser and has **no `BYPASSRLS`**, and make it the database owner.
Either attribute would silently switch off the per-user row-level security, and the
migrations refuse to run as a role that has one.

Use the app role's **direct** (non-pooled) connection string as `DATABASE_URL`.

## 2. Sign-in (Google)

In Google Cloud, create an OAuth client (type **Web application**) with the redirect URI
`<your public URL>/auth/callback`. Its client ID and secret go in `OIDC_CLIENT_ID` and
`OIDC_CLIENT_SECRET`.

## 3. Render

**New → Blueprint →** your fork of the repo. Enter the values it asks for:
`PUBLIC_BASE_URL`, `DATABASE_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` and
`ALLOWED_EMAILS`. `SESSION_SECRET` is generated for you. Every setting is described in
[Configuration](/self-hosting/configuration/).

Render deploys each commit on `main` only after all of its CI checks pass, and the database
migrations run on every start.

## Staying awake (optional)

Render's free plan stops an idle service after about 15 minutes, and the next visit waits
while it starts again; the app shows "Waking up…" meanwhile. To avoid that, have an
external scheduler (such as [cron-job.org](https://cron-job.org)) request
`<your public URL>/healthz` every few minutes.

Render's health check also uses `/healthz`, which never touches the database. So Neon can
still scale to zero when you're not using the app, and its free tier goes further.

## Next steps

- [Use your own domain](/self-hosting/custom-domain/), optionally behind Cloudflare.
- [Set up nightly backups](/self-hosting/backups/).
