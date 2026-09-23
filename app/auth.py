# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sign-in with an OIDC provider (Google by default), via Authlib.

Flow: /auth/login -> provider -> /auth/callback -> (session: JT-15) -> redirect to `next`.

- Identity is the provider's `sub`. Accounts are never merged by email, so a recycled
  email address can't inherit someone else's data.
- Access requires `email_verified` AND an email on ALLOWED_EMAILS. A refused sign-in
  creates nothing.
- Failures show one of two generic messages; the detail goes to the server log only.
"""

import html
import logging
from enum import StrEnum
from typing import Any

import httpx2
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings
from app.db import DbSession
from app.redirects import safe_next

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", include_in_schema=False)

_PROVIDER = "oidc"
_NEXT_KEY = "next"
# The login cookie only lives for the provider round trip.
_LOGIN_COOKIE_MAX_AGE = 10 * 60


class DeniedReason(StrEnum):
    NOT_AUTHORISED = "not_authorised"
    FAILED = "failed"


def install_auth(
    app: FastAPI, settings: Settings, *, transport: httpx2.AsyncBaseTransport | None = None
) -> None:
    """Register the OIDC client, the login-state cookie and the /auth routes.

    `transport` replaces the HTTP transport used to talk to the provider. Tests only: it
    lets them stand up a fake provider that issues real signed tokens.
    """
    client_kwargs: dict[str, Any] = {"scope": "openid email", "timeout": 10}
    if transport is not None:
        client_kwargs["transport"] = transport
    oauth = OAuth()
    oauth.register(
        _PROVIDER,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret.get_secret_value(),
        server_metadata_url=(
            str(settings.oidc_issuer).rstrip("/") + "/.well-known/openid-configuration"
        ),
        client_kwargs=client_kwargs,
    )
    app.state.oauth = oauth
    app.state.settings = settings

    # Signed cookie holding Authlib's state + nonce and our `next`, only for /auth/*.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        session_cookie="jt_oauth",
        max_age=_LOGIN_COOKIE_MAX_AGE,
        path="/auth",
        same_site="lax",
        https_only=settings.secure_cookies,
    )
    app.include_router(router)


def _client(request: Request) -> Any:
    return request.app.state.oauth.create_client(_PROVIDER)


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


@router.get("/login")
async def login(request: Request, next: str | None = None, switch_account: bool = False) -> Any:
    request.session.clear()
    request.session[_NEXT_KEY] = safe_next(next)
    # Built from the configured public origin, never from the request's Host header.
    redirect_uri = str(_settings(request).public_base_url).rstrip("/") + "/auth/callback"
    extra = {"prompt": "select_account"} if switch_account else {}
    return await _client(request).authorize_redirect(request, redirect_uri, **extra)


@router.get("/callback")
async def callback(request: Request, session: DbSession) -> RedirectResponse:
    next_path = safe_next(request.session.get(_NEXT_KEY))
    try:
        token = await _client(request).authorize_access_token(request)
    except Exception:
        # Cancelled consent, state mismatch/missing cookie, bad or tampered token, provider
        # unreachable... The reason is for the logs, not the page.
        logger.warning("sign-in failed during token exchange/validation", exc_info=True)
        return _denied(request, DeniedReason.FAILED)
    finally:
        request.session.clear()

    # Authlib only validates an ID token if one came back; require it explicitly.
    userinfo = token.get("userinfo")
    if not userinfo or not userinfo.get("sub"):
        logger.warning("sign-in failed: no validated ID token in the token response")
        return _denied(request, DeniedReason.FAILED)

    email = str(userinfo.get("email") or "").strip().lower()
    if userinfo.get("email_verified") is not True or email not in _settings(request).allowed_emails:
        logger.info("sign-in refused", extra={"reason": "email not verified or not allowed"})
        return _denied(request, DeniedReason.NOT_AUTHORISED)

    await _upsert_user(session, sub=str(userinfo["sub"]), email=email)
    # JT-15: create the session and set the session cookie here.
    return RedirectResponse(next_path, status_code=303)


async def _upsert_user(session: DbSession, *, sub: str, email: str) -> None:
    """Create the user, or refresh their email if it has changed. Keyed on `sub` only."""
    await session.execute(
        text(
            "INSERT INTO users (oidc_sub, email) VALUES (:sub, :email) "
            "ON CONFLICT (oidc_sub) DO UPDATE SET email = EXCLUDED.email "
            "WHERE users.email IS DISTINCT FROM EXCLUDED.email"
        ),
        {"sub": sub, "email": email},
    )


def _denied(request: Request, reason: DeniedReason) -> RedirectResponse:
    url = "/auth/denied" if reason is DeniedReason.NOT_AUTHORISED else "/auth/denied?reason=failed"
    return RedirectResponse(url, status_code=303)


_PAGES = {
    DeniedReason.NOT_AUTHORISED: (
        "This account isn't authorised",
        "The account you signed in with doesn't have access to this Job Tracker.",
        "/auth/login?switch_account=true",
        "Sign in with a different account",
    ),
    DeniedReason.FAILED: (
        "Sign-in failed",
        "Something went wrong while signing you in. Please try again.",
        "/auth/login",
        "Try again",
    ),
}


@router.get("/denied")
async def denied(reason: DeniedReason = DeniedReason.NOT_AUTHORISED) -> HTMLResponse:
    title, message, href, link = (html.escape(part) for part in _PAGES[reason])
    status = 403 if reason is DeniedReason.NOT_AUTHORISED else 400
    body = f"""<!doctype html>
<html lang="en-GB">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title} · Job Tracker</title>
    <style>
      body {{ font-family: system-ui, sans-serif; display: grid; place-items: center;
             min-height: 100dvh; margin: 0; padding: 1rem; background: #f8fafc; color: #0f172a; }}
      main {{ max-width: 28rem; text-align: center; }}
      a {{ display: inline-block; margin-top: 1rem; padding: 0.75rem 1rem; border-radius: 0.5rem;
          background: #0f172a; color: #fff; text-decoration: none; }}
    </style>
  </head>
  <body>
    <main>
      <h1>{title}</h1>
      <p>{message}</p>
      <a href="{href}">{link}</a>
    </main>
  </body>
</html>"""
    return HTMLResponse(body, status_code=status, headers={"Cache-Control": "no-store"})
