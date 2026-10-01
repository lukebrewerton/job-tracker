# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The /api/v1 router. Every data route is registered on `api_router`, never on the app.

The router itself requires a signed-in user, so a route can't forget authentication:
without a valid session every /api route returns 401 before its handler runs. Routes
take `UserDbSession` for database access (row-level security scoped to that user).
Tests enumerate every /api route to check both the 401 and cross-user isolation.

Versioning (manual: API → Versions and releases): within a version, changes are additive only. A
breaking change goes into a new version served alongside the old one, which keeps
working for 3 months, and the app's major version moves with it.
"""

from fastapi import APIRouter, Depends

from app.routes import dashboard, interviews, jobs, me
from app.sessions import current_user

# The newest API version served. The app's major version must match it (make version-check).
API_VERSION = 1
API_PREFIX = f"/api/v{API_VERSION}"

api_router = APIRouter(prefix=API_PREFIX, dependencies=[Depends(current_user)])
api_router.include_router(jobs.router)
api_router.include_router(me.router)
api_router.include_router(interviews.job_router)
api_router.include_router(interviews.router)
api_router.include_router(dashboard.router)
