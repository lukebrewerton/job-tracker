# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Print the API's OpenAPI schema as JSON: the contract clients generate types from.

Builds the app with placeholder settings and calls `app.openapi()`, the same function
FastAPI uses to serve /api/openapi.json in development. No server, database or `.env`
is needed, so CI can run it. `make openapi` writes it to openapi.json (committed), and
`make openapi-check` fails if that file is stale. Clients generate from the file, never
from this code (see `make types`).
"""

import json
import sys
from pathlib import Path

from app.config import Settings
from app.main import create_app

# Placeholders only: nothing here connects to anything.
settings = Settings(
    public_base_url="https://job-tracker.example.test",
    database_url="postgresql://unused:unused@127.0.0.1:1/unused",
    oidc_client_id="unused",
    oidc_client_secret="unused",
    session_secret="x" * 32,
    allowed_emails="unused@example.test",
    environment="development",
    static_dir=Path("/nonexistent"),
    _env_file=None,
)
json.dump(create_app(settings).openapi(), sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
