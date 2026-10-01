---
title: Generating a client
description: Building a typed client for the API from its OpenAPI contract.
---

The API's contract is `openapi.json` (OpenAPI 3.1). Each [release](https://github.com/lukebrewerton/job-tracker/releases)
attaches the `openapi.json` for that version, so a client released separately from the app
can generate its types from a pinned spec instead of tracking `main`.

- **TypeScript:** [openapi-typescript](https://openapi-ts.dev) generates the types, and
  [openapi-fetch](https://openapi-ts.dev/openapi-fetch/) gives a typed client. That's what
  the web app itself uses (`make types`).
- **Other languages:** [OpenAPI Generator](https://openapi-generator.tech) covers Kotlin,
  Swift and many more.

Every route needs a signed-in session, and writes must send JSON from the instance's own
origin. The API is designed for the web app's single-origin use; see
[Versions and releases](/api/versions-and-releases/) for what may change within a version.
