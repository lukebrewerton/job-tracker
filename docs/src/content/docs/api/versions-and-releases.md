---
title: Versions and releases
description: How the API is versioned, what counts as a breaking change, and how releases are numbered.
---

## The API

The API lives under **`/api/v1`**. Its contract is the committed `openapi.json`, and
clients (the web app here, anything else later) generate their types from it.

- **Within a version, changes are additive only:** new endpoints, new optional request
  fields, new response fields. Clients must ignore response fields they don't know.
- **A breaking change** (removing or renaming an endpoint or field, making a request field
  required, narrowing a type or enum) goes into a **new version**, `/api/v2`, served
  alongside `/api/v1`. The old version keeps working for **3 months** after the new one
  ships, then is removed.
- CI checks every pull request with [oasdiff](https://github.com/oasdiff/oasdiff)
  (`make api-breaking`) and fails on breaking changes. A deliberate one needs the
  `breaking-api` label on the PR.

## Releases

Releases use [semantic versioning](https://semver.org), one version for the whole app,
with the **major version equal to the newest API version**: 1.x.y serves `/api/v1`, and the
release that adds `/api/v2` is 2.0.0. Minor releases add features, patch releases fix
things. To release, bump the version in `pyproject.toml`, `app/__init__.py` and
`frontend/package.json` in a PR (`make version-check` keeps them in step); when it merges,
a GitHub Release `vX.Y.Z` is created with that version's `openapi.json` attached, so a
separately released client can generate from a pinned spec. Every merge still deploys;
releases just mark versions.
