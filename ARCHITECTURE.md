# Job Tracker — Architecture & Requirements

Personal job-application tracker. Single-user (per deployment), open source under
AGPL-3.0, designed so anyone can fork and self-host their own instance. Captures
context from this project's requirements/architecture discussion — kept detailed
deliberately so nothing gets lost between sessions.

## Problem statement

Applying to multiple jobs over time and losing track of what's been applied to,
what stage each application is at, and what's still outstanding. A Firefox
extension provides one-click capture from a job posting page; the web app is
where the actual tracking happens.

## Repos

Two repos, not three:

- **`job-tracker`** (this repo) — FastAPI backend + React/Vite/Tailwind frontend,
  in one repo, one deployable unit.
- **`job-tracker-extension`** (separate, built later) — Firefox WebExtension.
  Kept separate because it has a completely different toolchain (`web-ext`, AMO
  signing) and no shared code or build artifact with the main app.

An earlier draft of this design used three repos (backend / frontend /
extension), with the frontend's CI publishing a build artifact that the
backend's CI fetched during its Docker build. That was rejected: it added a
cross-repo artifact-fetch step purely to satisfy a repo-count preference, with
no actual benefit. A single repo with a multi-stage Dockerfile is simpler and
more forkable (one clone, one `docker build`, one deploy) — which matters for
an AGPL project other people might self-host.

### Why the deploy topology is single-origin

Auth is handled at the application level (see below), not via an edge proxy
like Cloudflare Access. If frontend and backend were deployed as separate
services on different subdomains, the session cookie would need to be shared
cross-site, which drags in `SameSite=None`, CORS-with-credentials, and general
cross-origin cookie complexity — real complexity with no payoff for a
single-user app. Instead: **the backend serves the built frontend as static
assets**, so there's one origin, one cookie, zero CORS configuration.

Build: a multi-stage `Dockerfile` —
1. `node` stage: `npm ci && npm run build` in `/frontend`, producing `dist/`.
2. Python stage: copies `frontend/dist` into the FastAPI app's static
   directory, serving it for all non-`/api/*` paths.

## Tech stack

- **Backend**: Python, FastAPI, SQLAlchemy (async) + Alembic for migrations.
- **Frontend**: React + Vite + Tailwind (matches the stack already used in the
  `job-finder` project, for consistency across the personal project suite).
- **Database**: PostgreSQL, hosted on Neon (free tier).
- **Auth**: Google OIDC (Authlib), app-level — see below.

## Hosting (all free tier)

| Piece | Choice | Why |
|---|---|---|
| Compute | Render (free web service) | Real free tier still exists; spins down after 15 min idle |
| Database | Neon (free Postgres) | Scale-to-zero after 5 min idle; **not** Render's free Postgres, which expires 30 days after creation + 14-day grace period, then is deleted — not viable as a persistent store |
| Edge | Cloudflare (free, DNS-proxied) | Already manages the domain; gives basic rate-limiting/DDoS absorption in front of the app for free |
| Keep-warm | cron-job.org (free, cloud-hosted) | Pings a health endpoint every ~4 min. Free, unlimited jobs, 1-minute minimum interval — comfortably inside both Render's 15-min and Neon's 5-min suspend windows, with margin. Cloud-hosted deliberately, not self-hosted (e.g. not Uptime Kuma), because of instability on home infrastructure |
| Domain | `job-tracker.job-finder.dev` | Already-owned domain, already on Cloudflare. Chosen over `job-tracker.brewerton.me` because `job-finder` is itself just another personal AGPL project (not a multi-tenant SaaS, not yet deployed), so grouping personal-suite projects under `job-finder.dev` is accurate, not misleading |

### Rejected/considered alternatives

- **Railway / Fly.io** — no real free tier as of 2026 (Railway killed its free
  plan in 2023; Fly.io ended free allowances for orgs created after Oct 2024).
- **Supabase** (DB) — free tier pauses projects after 7 days of inactivity
  (time-based degradation) vs. Neon's usage-based scale-to-zero (no hard
  pause). Neon is the better fit for something used sporadically.
- **Cloudflare Access** (auth) — would have handled the "redirect to login,
  return to original page" flow natively at the edge with zero app code, and
  was seriously considered. Rejected in favour of app-level Google OIDC to
  keep the project fully self-contained (no Cloudflare account dependency for
  anyone else self-hosting) and because the user wanted to replicate a
  Google-OIDC pattern already used in the `job-finder` project.
- **Oracle Cloud Always Free ARM VM** — considered as an always-on option to
  eliminate cold starts entirely (still available in 2026, though capped at 2
  OCPU/12GB as of August 2026, down from 4/24). Rejected: would mean owning OS
  patching/upkeep, which cuts against the "hardened" goal unless actively
  maintained. Keep-warm ping via cron-job.org was chosen instead.
- **UptimeRobot** (keep-warm) — free tier's 5-minute interval is the same as
  Neon's 5-minute suspend timeout, i.e. no margin — timing jitter would still
  cause occasional cold starts. cron-job.org's 1-minute minimum interval gives
  real margin. UptimeRobot could still be added later purely for downtime
  *alerting* (not warming) if wanted.
- **PagerDuty / Atlassian Statuspage** — neither is a synthetic/uptime
  pinger. PagerDuty is an alerting/escalation engine that needs to be *fed*
  by a monitor; Statuspage displays status, typically fed by manual updates
  or a third-party monitor's webhook. Neither actively polls a URL on a
  schedule. Also deliberately not used here even if they did, since
  Statuspage is tied to the user's whole Atlassian org — coupling this AGPL,
  self-hostable project to a personal org subscription would mean no other
  self-hoster could replicate the setup.

## Extension design

The extension is a **link-opener, not an API client** — this was the key
simplification that collapsed most of the auth-surface questions:

1. Click the browser action button on a job posting page.
2. Extension reads `tab.url` and `tab.title` only (no content script, no page
   scraping) — an earlier option to snapshot the full JD text at capture time
   (to survive link rot / postings being taken down) was explicitly declined
   in favour of simplicity.
3. Opens a new tab: `https://job-tracker.job-finder.dev/jobs/new?url=<enc>&title=<enc>`.
4. That page is a normal page in the web app, subject to the same session
   auth as any other page — if the session has expired, the app's own
   login-redirect flow handles it (see Auth below), and lands the user back
   on that exact URL post-login, form still pre-filled.

Manifest V3, `activeTab` permission only. No stored credentials, no CORS
configuration needed anywhere, because the extension never talks to the API
directly.

CI (`job-tracker-extension` repo, when built): `web-ext lint` → build → on
tag push, submit to AMO's **unlisted** signing API (self-distribution, not a
public listing) using AMO API credentials stored as a repo secret → attach
the signed `.xpi` to the GitHub release. Firefox requires Mozilla-signed
`.xpi`s even for purely personal/unlisted use; the unlisted channel returns a
signed build within minutes, so this is CI-automatable.

## Auth design

**App-level Google OIDC** (via Authlib), not Cloudflare Access, not
self-built password auth. No password storage anywhere.

### Flow

1. Unauthenticated request to any protected page → app redirects to
   `/auth/login?next=<path>`.
2. The app captures `next` **server-side from the request path that
   triggered the redirect** — never from a client-supplied value — and
   validates it is a same-origin relative path before ever redirecting to it.
   This is what prevents the endpoint being turned into an open redirect.
3. Redirect to Google's OAuth consent screen.
4. Google redirects back to `/auth/callback` with an authorization code.
5. App exchanges the code, validates the ID token, upserts the user by
   Google `sub` (subject identifier).
6. App issues its own session cookie: **HttpOnly, Secure, SameSite=Lax**,
   host-only (no `Domain=` attribute — deliberately not shared with
   `job-finder.dev` or any other subdomain, so a bug in one app's session
   handling can't affect another's, even though they're both under
   `job-finder.dev`).
7. Redirect to the validated `next` path — e.g. back to
   `/jobs/new?url=...` exactly as the extension opened it, now authenticated.

### Access control

- **No public registration.** A single allow-listed Google email address,
  configured via environment variable. Anyone forking this repo to self-host
  sets their own allow-listed email(s) — this is what makes "single-user
  per deployment" work without needing a full multi-tenant user-management
  system.

## Data model

### `users`
| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `google_sub` | text, unique | Google's stable subject identifier |
| `email` | text | |
| `created_at` | timestamptz | |

### `applications`
| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `user_id` | FK → users | |
| `company` | text, required | |
| `role` | text, required | |
| `url` | text, nullable | The job posting link, from the extension or entered manually |
| `url_canonical` | text, nullable | Tracking params stripped (`utm_*`, `refId`, `vjk`, etc.), host lowercased, fragment dropped — computed server-side for dedup |
| `location` | text, nullable | Free text — deliberately not a structured enum/city split, since job postings phrase this too inconsistently for a rigid structure to hold |
| `source` | enum, nullable | `linkedin` / `company_site` / `referral` / `recruiter` / `indeed` / `other` |
| `salary` | text, nullable | Free text (e.g. "£70-80k + bonus, negotiable") — structured min/max/currency was considered and rejected in favour of flexibility |
| `contact_name` | text, nullable | Recruiter or hiring-manager name |
| `contact_email` | text, nullable | Inline field, not a normalised `contacts` table — a separate contacts table (to dedupe a recruiter reused across multiple applications) was considered and explicitly rejected for simplicity |
| `status` | enum | `saved` → `applied` → `interviewing` → `offer` → `accepted`, with `rejected` / `withdrawn` as terminal off-ramps from any stage |
| `applied_at` | date, nullable | Null while status is still `saved` |
| `notes` | text, nullable | |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

**Constraint**: partial unique index on `(user_id, url_canonical) WHERE url_canonical IS NOT NULL`
— not a plain unique constraint, because `url_canonical` is nullable (for jobs
that came via a recruiter DM or email with no canonical posting page), and a
plain unique constraint would either reject those rows or throw a spurious
collision between two different no-URL applications.

`saved` is the default status when a record is first created — typically via
the extension, at browse time, before the user has necessarily hit "apply" on
the company's site. It moves to `applied` (with `applied_at` set) once they
actually submit. `accepted` is kept distinct from `offer` so "received an
offer" and "took it" are distinguishable once there's more than one offer live
at once.

### `status_history`
| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `application_id` | FK → applications | |
| `status` | enum | Same enum as `applications.status` |
| `changed_at` | timestamptz | |

One row inserted every time `status` changes — including an initial row at
creation time (`status = 'saved'`). This directly serves the original
"I lose track of what I've applied for" problem by giving a timeline per
application (e.g. "applied 3 weeks ago, no movement since"). Written in
**application/API code**, not a database trigger — keeps the logic in Python,
testable, in one place, rather than split between the app and the database.

Deliberately **not** storing a `status_from` column — the previous status is
always derivable by ordering `changed_at`, so storing it would be redundant
data that could drift from the truth.

### `interviews`
| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `application_id` | FK → applications | |
| `scheduled_at` | timestamptz, **nullable** | "Moved to interview stage, no date yet" is the common case — must not be forced to a fake date |
| `mode` | enum | `remote` / `in_person` / `phone` |
| `round_label` | text, nullable | Free text, e.g. "Technical screen", "Final round" |
| `notes` | text, nullable | |
| `created_at` | timestamptz | |

Moving an application to `interviewing` status doesn't require knowing the
number of stages upfront — "add an interview" just inserts a new row,
whenever a new stage is scheduled, however many times.

Deliberately **not** storing:
- A `current_round`/stage-count field on `applications` — would duplicate
  `count(interviews)` and could drift out of sync.
- A per-interview `outcome` field — `applications.status` already carries
  the overall result; a second place to track pass/fail would duplicate and
  could disagree with it. Can be added later if per-round history is
  genuinely wanted.

## CI/CD and secrets hardening

This section exists because of a specific, real GitHub Actions attack class
(`pull_request_target` + untrusted code execution) that was worked through in
detail — captured here so the rules aren't rediscovered from scratch when the
pipelines get written.

### The core rule

**Never use `pull_request_target` (or `workflow_run` off a PR build) to check
out and execute a fork's code.** Neither this repo nor the extension repo has
any actual need for it — CI (lint/test/build) uses plain `pull_request`, and
nothing privileged should ever trigger off a PR at all.

### Why `pull_request` (not `pull_request_target`) is safe by design

Two independent protections apply to `pull_request` events from a fork:

1. GitHub runs the workflow **as defined in the base branch** (e.g. `main`),
   never the version modified in the fork's PR branch — so an attacker
   editing `.github/workflows/*.yml` in their PR has no effect.
2. For a genuine fork PR, the `secrets` context is **empty** and
   `GITHUB_TOKEN` is read-only — `${{ secrets.ANYTHING }}` resolves to an
   empty string regardless of what the workflow does.

### Why `pull_request_target` is dangerous

It gets the *same* base-branch-workflow-file protection (#1 above) — editing
the YAML doesn't help an attacker here either. The actual exploit is
different: `pull_request_target` runs with **full secret access and a
write-scoped token**, in the base repo's trust context. If that workflow then
checks out and executes the PR's actual code (`actions/checkout` on the PR
head SHA, then `npm install` / `pytest` / `npm run build` / anything at all),
that execution happens with the repo's secrets sitting in the environment. A
malicious `postinstall` script, a modified test file, anything — can just
read `os.environ`/`process.env` and exfiltrate whatever's there. No workflow
YAML edit is required for this attack; the workflow file itself stays
trusted, it's the *code that workflow chooses to run* that isn't.

### Pipeline structure (to build)

Two separate workflow files per repo:

1. **CI** — triggered by `pull_request` (any branch) and `push`. Lint, test,
   build. **References zero secrets.** Since forks never get secrets on this
   trigger anyway, and nothing here touches deploy credentials, there is
   nothing to leak regardless of what a PR's code does.
2. **Deploy** — separate workflow, triggered **only** by `push` to `main`.
   Never `pull_request`, never `pull_request_target`. The Render deploy hook
   (an unauthenticated POST URL — treat it like a secret, never commit it to
   `render.yaml` or a workflow file) lives as a **GitHub Environment secret**
   (environment: `production`), with that environment's "Deployment
   branches" restricted to `main` only. This is defence in depth on top of
   the trigger restriction: even a future misconfigured workflow can't reach
   the secret unless it both declares `environment: production` *and* is
   running against `main`.

### Additional repo settings

- **Settings → Actions → General → Fork pull request workflows → "Require
  approval for all outside collaborators."** Worth enabling, but be clear on
  what it actually defends against: per GitHub's own docs, this exists to
  stop strangers burning Actions minutes (e.g. crypto-mining abuse via
  forked PRs), not as a secrets control — forks never had secrets on
  `pull_request` regardless. Enable it as cheap insurance; the real defence
  is the trigger structure above.
- Dependabot + GitHub secret scanning + CodeQL — enable on the repo (free for
  public repos).

### Vite-specific gotcha (frontend build)

Vite inlines every `VITE_*` environment variable into the shipped client
bundle **at build time**. In the multi-stage Dockerfile, only the Google
OAuth **client ID** (public, safe to ship) should reach the frontend build
stage. The OAuth **client secret** must stay backend-only, injected at
runtime — never passed as a `VITE_*` build arg, or it ends up both in the
shipped JS bundle and baked into Docker image layers.

### On forking in general

Forks get **none** of this repo's secrets, full stop — that part requires no
special handling. The only scenario where secrets are at risk from a branch
(rather than a fork) is a collaborator with **write access** to this repo
pushing a branch directly — same-repo `push`/`pull_request` events don't get
the fork restrictions above. Not a concern today (single collaborator), worth
remembering if collaborators are ever added.

## Security posture (proportionality)

Explicitly scoped to what's proportionate for an obscure single-user tool,
not a high-value target — "assume it'll be attacked" was pushed back on
during design in favour of naming what's real risk vs. what's not:

**Worth doing:**
- No public registration endpoint.
- OIDC instead of any password storage.
- HttpOnly/Secure/SameSite session cookies, host-only (not shared across
  subdomains).
- Server-validated redirect targets (open-redirect prevention on the OIDC
  `next` flow).
- Cloudflare edge in front for basic rate-limiting/DDoS absorption.
- Dependabot, secret scanning, CodeQL.
- Parameterised queries (SQLAlchemy ORM handles this by default — no raw SQL
  string interpolation).
- The CI/secrets structure above.

**Not proportionate at this scale — explicitly skipped:**
- Custom WAF rule tuning.
- Bespoke intrusion detection.
- Elaborate formal threat modelling.

Realistic exposure for an obscure personal tool is automated scanner noise,
not a targeted attacker — the list above is sized accordingly.

## License

AGPL-3.0, matching the rest of the personal project suite (including
`job-finder`, a separate, also-not-yet-deployed AGPL repo under the same
`job-finder.dev` domain).

## Open items (product-level, not architectural — resolve during build)

- Exact set of frontend pages/components beyond `/jobs/new`, `/jobs` (list/
  board), `/jobs/:id` (detail/edit) — not specified in detail yet.
- Whether the applications list is presented as a Kanban board (by `status`
  column) or a plain list/table — implied by the status-stage design but not
  explicitly decided.
- `round_label` on interviews is free text by design; no fixed taxonomy was
  defined (e.g. "Phone screen" / "Technical" / "Final") — left open
  deliberately, can be revisited if free text proves annoying in practice.
