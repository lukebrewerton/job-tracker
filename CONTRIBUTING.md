# Contributing

Thanks for taking a look at Job Tracker. It's a personal project built to be forked and
self-hosted, but genuine contributions are welcome.

## Before opening a PR

- Read `CLAUDE.md` for conventions (tooling, formatting, testing, commit style).
- For anything non-trivial, open an issue first to discuss the approach before writing
  code. Saves both of us time if the direction needs adjusting.
- Small fixes (typos, obvious bugs) can just be a PR directly.

## Checks before submitting

- `make lint` (ruff check + ruff format --check + mypy) and `make test` must both pass
  locally — the same checks run in CI on your PR.
- If you touched the schema, include an Alembic migration.
- If you added an env var, add it to `.env.example` with a placeholder value.
- PRs are scanned for secrets (gitleaks). To catch them before you commit, turn on the
  optional pre-commit hook: `brew install gitleaks && make hooks` (see the README).

## Copyright and licensing

This project is licensed under AGPL-3.0-or-later (see `LICENSE`).

Submitting a PR does **not** transfer copyright to the project or to Luke Brewerton —
you keep copyright on code you write. By submitting a PR, you're agreeing to license
your contribution under the project's existing license (AGPL-3.0-or-later), the same
way every other contribution to this repo is licensed. The end result is a work with
multiple copyright holders, all under one license — this is how most open-source
projects without a formal Contributor License Agreement work.

Practically, this means:

- If you author an entirely new file, put your own name in its SPDX header
  (`Copyright (C) <year> <your name>` / `SPDX-License-Identifier: AGPL-3.0-or-later`),
  not the project maintainer's.
- Small fixes or edits to an existing file don't require re-attributing that file —
  headers reflect original authorship, not every contributor who's touched a file.

## What won't be merged

- Multi-tenant features (public sign-up, organisations, sharing). Each deployment is
  for one person, with access controlled by an email allow-list.
- Page scraping in the extension. It deliberately sends only the tab's URL and title.
- Hardcoded instance URLs, domains or email addresses. Everything instance-specific
  comes from configuration.

If you disagree with one of these, open an issue and make the case — they're
documented decisions, not arbitrary ones, but they're not immovable either.
