# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""FastAPI application factory.

Run with `uvicorn app.main:create_app --factory`. A factory (rather than a module-level
`app`) means settings are only read when the server starts, not at import time.
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse

from app import __version__
from app.config import Settings, get_settings
from app.logging_config import configure_logging
from app.spa import mount_spa

# Paths exempt from the canonical-host redirect. The platform's own health checks may
# not send the public Host header, and a redirect would read as unhealthy.
_HOST_REDIRECT_EXEMPT = {"/healthz"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
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

    # Must be registered last: it catches every path the routes above don't.
    mount_spa(app, settings.static_dir)
    return app
