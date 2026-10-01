<h1 align="center">
  <img src="branding/mark.svg" width="48" align="center" alt=""> Job Tracker
</h1>

<p align="center">
  <img alt="Development status: released" src="https://img.shields.io/badge/development_status-released-green?style=for-the-badge">
  <a href="https://github.com/lukebrewerton/job-tracker/actions/workflows/ci.yml"><img alt="CI status" src="https://img.shields.io/github/actions/workflow/status/lukebrewerton/job-tracker/ci.yml?branch=main&style=for-the-badge&label=CI"></a>
</p>

A self-hostable job application tracker. Save a job from a posting page with one click
(via the companion Firefox extension), then track it from "saved" through to an offer —
with a dashboard showing what needs following up, what's still to apply for, and what's
gone quiet.

Single user per deployment: fork it, set your own allowed email address, and host your
own instance.

## The manual

Everything else is in the manual, at **[job-tracker-docs.job-finder.dev](https://job-tracker-docs.job-finder.dev)**:

- **[Using Job Tracker](https://job-tracker-docs.job-finder.dev/using/getting-started/):** the dashboard, jobs, interviews, and
  installing it on your phone.
- **Self-hosting:** [deploying your own instance](https://job-tracker-docs.job-finder.dev/self-hosting/deploying/) (Render and
  Neon, with Google sign-in), [configuration](https://job-tracker-docs.job-finder.dev/self-hosting/configuration/), a
  [custom domain](https://job-tracker-docs.job-finder.dev/self-hosting/custom-domain/), and [backups](https://job-tracker-docs.job-finder.dev/self-hosting/backups/).
- **Development:** [running it locally](https://job-tracker-docs.job-finder.dev/development/local-development/) and
  [secret scanning](https://job-tracker-docs.job-finder.dev/development/secret-scanning/).
- **API:** [versions and releases](https://job-tracker-docs.job-finder.dev/api/versions-and-releases/) and
  [generating a client](https://job-tracker-docs.job-finder.dev/api/generating-a-client/).

The manual's source is in [`docs/`](docs/).

## Stack

FastAPI · SQLAlchemy (async) · PostgreSQL · React · TypeScript · Vite · Tailwind ·
Google sign-in (OIDC). One repo, one container: the backend serves the built frontend.

## Licence

The code is [AGPL-3.0-or-later](LICENSE). The logo and icons are © 2026 Luke Brewerton,
under [CC BY-NC-ND 4.0](LICENSES/CC-BY-NC-ND-4.0.txt): see
[licence and branding](https://job-tracker-docs.job-finder.dev/about/licence-and-branding/). See
[CONTRIBUTING.md](CONTRIBUTING.md) to contribute, and [SECURITY.md](SECURITY.md) to report
a vulnerability.
