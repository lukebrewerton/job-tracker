# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Serve the built React SPA from the same origin as the API.

- `/assets/*` — Vite's hashed bundles, served as static files.
- Any other path not claimed by a route — a real file from the build root if one exists
  (e.g. `/favicon.ico`), otherwise `index.html` so client-side routes deep-link.

`/api/*` and `/auth/*` are never answered with the SPA: an unknown API path must be a
JSON 404, not an HTML page.

The app shell (`index.html`) is only served to a signed-in user, except on the public
front page (`/`), which shows a sign-in button when you're signed out (and is where
logout lands, so Google can't silently sign you straight back in). Signed in, `/` goes
straight to the dashboard (which is also what an installed home-screen app opens on,
and where signing in with no `next` ends up). Anywhere else, the
browser is sent to sign in and brought back to the exact URL afterwards — which is what
makes the extension's `/jobs/new?url=…` link work on a cold start. Built files stay
public: they contain no data, and the shell fetches all data from the gated API.

The shell is served with the footer's links (the manual and the source code, from
DOCS_URL and SOURCE_URL) as `<meta>` tags, so even the signed-out front page has them
without calling the gated API.
"""

from html import escape
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.sessions import CurrentUser, page_user

RESERVED_PREFIXES = ("api", "auth")
# Client-side routes served without a session. Only the front page: it holds no data.
PUBLIC_PAGES = frozenset({""})


def with_about_links(html: str, settings: Settings) -> str:
    """The app shell, with the footer's links as <meta> tags in its <head>."""
    tags = "".join(
        f'<meta name="{name}" content="{escape(str(url), quote=True)}">'
        for name, url in (
            ("jt-docs-url", settings.docs_url),
            ("jt-source-url", settings.source_url),
        )
    )
    return html.replace("</head>", tags + "</head>", 1)


def mount_spa(app: FastAPI, static_dir: Path) -> None:
    root = static_dir.resolve()
    index = root / "index.html"

    # check_dir=False: the app must still start (and serve the API) before the
    # frontend has been built, e.g. in backend-only tests and CI jobs.
    app.mount("/assets", StaticFiles(directory=root / "assets", check_dir=False), name="assets")

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    async def spa(
        path: str,
        request: Request,
        user: Annotated[CurrentUser | None, Depends(page_user)],
    ) -> FileResponse | HTMLResponse | RedirectResponse:
        if path.split("/", 1)[0] in RESERVED_PREFIXES:
            raise HTTPException(status_code=404)

        if path:
            candidate = (root / path).resolve()
            # is_relative_to blocks `..` traversal out of the build directory.
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)

        if user is not None and path == "":
            return RedirectResponse("/dashboard", status_code=302)

        if user is None and path not in PUBLIC_PAGES:
            target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(f"/auth/login?next={quote(target, safe='')}", status_code=302)

        if not index.is_file():
            raise HTTPException(status_code=404, detail="Frontend not built")
        settings: Settings = request.app.state.settings
        return HTMLResponse(
            with_about_links(index.read_text(), settings), headers={"Cache-Control": "no-cache"}
        )
