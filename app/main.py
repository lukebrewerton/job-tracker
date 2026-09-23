# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI application factory.

Run with `uvicorn app.main:create_app --factory`. A factory (rather than a module-level
`app`) means settings are only read when the server starts, not at import time.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text

from app import __version__
from app.auth import install_auth
from app.config import Settings, get_settings
from app.db import create_engine, create_sessionmaker
from app.logging_config import configure_logging
from app.spa import mount_spa

logger = logging.getLogger(__name__)

# Long enough to ride out a Neon cold start (~2s median), short enough to answer promptly.
_READYZ_TIMEOUT_SECONDS = 5

# Paths exempt from the canonical-host redirect. The platform's own health checks may
# not send the public Host header, and a redirect would read as unhealthy.
_HOST_REDIRECT_EXEMPT = {"/healthz"}


def create_app(
    settings: Settings | None = None, *, oidc_transport: httpx2.AsyncBaseTransport | None = None
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        lifespan=lifespan,
        title="Job Tracker",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    @app.middleware("http")
    async def redirect_to_public_host(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Compare hostnames only: ports differ legitimately in local dev (Vite proxy).
        host = (request.url.hostname or "").lower()
        if host != settings.public_host and request.url.path not in _HOST_REDIRECT_EXEMPT:
            target = str(settings.public_base_url).rstrip("/") + request.url.path
            if request.url.query:
                target += "?" + request.url.query
            return RedirectResponse(target, status_code=308)
        return await call_next(request)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        """Liveness only — never touches the database (keeps Neon free to suspend)."""
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False, response_model=None)
    async def readyz(request: Request) -> dict[str, str] | JSONResponse:
        """Readiness: can we reach the database? Manual/diagnostic use only.

        Never point a poller (keep-warm, Render health check) here: every call wakes Neon.
        Failure detail is logged, never returned — it could leak hosts or driver errors.
        """
        try:
            async with asyncio.timeout(_READYZ_TIMEOUT_SECONDS):
                async with request.app.state.engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
        except Exception:
            logger.warning("readyz: database unavailable", exc_info=True)
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ok"}

    install_auth(app, settings, transport=oidc_transport)

    # Must be registered last: it catches every path the routes above don't.
    mount_spa(app, settings.static_dir)
    return app
