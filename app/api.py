# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The /api router. Every data route is registered on `api_router`, never on the app.

The router itself requires a signed-in user, so a route can't forget authentication:
without a valid session every /api route returns 401 before its handler runs. Routes
take `UserDbSession` for database access (row-level security scoped to that user).
Tests enumerate every /api route to check both the 401 and cross-user isolation.
"""

from fastapi import APIRouter, Depends

from app.routes import jobs, me
from app.sessions import current_user

api_router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
api_router.include_router(jobs.router)
api_router.include_router(me.router)
