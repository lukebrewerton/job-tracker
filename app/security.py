# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross-site request forgery (CSRF) defences, applied before routing.

SameSite=Lax already stops *other sites* sending our cookie on cross-site writes. It does
not stop *sibling subdomains*: every `*.job-finder.dev` app is the same "site", so a
compromised sibling could submit a form carrying our cookie. Two cheap checks close that:

1. Origin: a state-changing request whose Origin header isn't ours is refused (403).
   Requests without an Origin (non-browser clients) fall through to the next check.
2. Content type: POST/PUT/PATCH to /api must be application/json (else 415). A cross-
   origin JSON request needs a CORS preflight, which this app never grants.
"""

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.config import Settings

_STATE_CHANGING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_NEEDS_JSON_BODY = frozenset({"POST", "PUT", "PATCH"})


def _same_origin(origin: str, settings: Settings) -> bool:
    parts = urlsplit(origin)
    return (parts.scheme, (parts.hostname or "").lower()) == settings.public_origin


def install_csrf_protection(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def csrf_protection(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        method = request.method.upper()
        if method in _STATE_CHANGING:
            origin = request.headers.get("origin")
            # "null" (sandboxed frames, some redirects) is never our origin.
            if origin is not None and not _same_origin(origin, settings):
                return JSONResponse({"detail": "Cross-origin request refused"}, status_code=403)
            if method in _NEEDS_JSON_BODY and request.url.path.startswith("/api/"):
                content_type = request.headers.get("content-type", "")
                if content_type.split(";", 1)[0].strip().lower() != "application/json":
                    return JSONResponse(
                        {"detail": "Content-Type must be application/json"}, status_code=415
                    )
        return await call_next(request)
