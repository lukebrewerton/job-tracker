# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Database-backed sessions and the current-user dependencies.

- The cookie `__Host-jt_session` holds a random token. The database stores only its
  SHA-256 hash, so a leaked database dump contains no usable sessions.
- The `__Host-` prefix makes the browser enforce Secure, Path=/ and no Domain: the
  cookie can never be shared with another subdomain. Browsers treat http://localhost as
  secure, so this works in local development too.
- A session ends after SESSION_IDLE_DAYS without use or SESSION_MAX_DAYS after sign-in.
  `last_seen_at` is written at most hourly, not on every request.
- The allow-list is re-checked on every request: removing an email revokes all of that
  user's sessions immediately (their data is kept).

Rejections (expired, revoked, unknown) must delete rows AND clear the cookie while
returning 401. The request's own transaction rolls back on that 401, so those writes run
in a short transaction of their own, and the 401 carries the cookie-clearing header.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import DbSession, set_session_user
from app.timezones import DEFAULT_TIMEZONE, today_in

COOKIE_NAME = "__Host-jt_session"
_LAST_SEEN_RESOLUTION = timedelta(hours=1)


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: str
    timezone: str = DEFAULT_TIMEZONE  # IANA name; see app/timezones.py

    def today(self) -> date:
        """Today's date where this user is."""
        return today_in(self.timezone)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _cookie_attributes() -> dict[str, object]:
    # Secure always: required by the __Host- prefix, and fine on http://localhost.
    return {"path": "/", "secure": True, "httponly": True, "samesite": "lax"}


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_max_days * 24 * 60 * 60,
        **_cookie_attributes(),  # type: ignore[arg-type]
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, **_cookie_attributes())  # type: ignore[arg-type]


def _unauthenticated(*, clear_cookie: bool) -> HTTPException:
    headers: dict[str, str] = {}
    if clear_cookie:
        scratch = Response()
        clear_session_cookie(scratch)
        headers["set-cookie"] = scratch.headers["set-cookie"]
    return HTTPException(status_code=401, detail="Not authenticated", headers=headers)


async def create_session(db: AsyncSession, user_id: uuid.UUID, settings: Settings) -> str:
    """Start a new session (a fresh token on every sign-in); purge the user's expired ones."""
    await db.execute(
        text(
            "DELETE FROM sessions WHERE user_id = :user_id AND ("
            "created_at <= now() - make_interval(days => :max_days) OR "
            "last_seen_at <= now() - make_interval(days => :idle_days))"
        ),
        {
            "user_id": user_id,
            "max_days": settings.session_max_days,
            "idle_days": settings.session_idle_days,
        },
    )
    token = secrets.token_urlsafe(32)
    await db.execute(
        text("INSERT INTO sessions (user_id, token_hash) VALUES (:user_id, :token_hash)"),
        {"user_id": user_id, "token_hash": hash_token(token)},
    )
    return token


async def revoke_session(db: AsyncSession, token: str) -> None:
    await db.execute(text("DELETE FROM sessions WHERE token_hash = :h"), {"h": hash_token(token)})


async def _commit_separately(request: Request, sql: str, params: dict[str, object]) -> None:
    """Run a write that must survive the 401 that follows it."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as db, db.begin():
        await db.execute(text(sql), params)


async def current_user(request: Request, db: DbSession) -> CurrentUser:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise _unauthenticated(clear_cookie=False)

    settings: Settings = request.app.state.settings
    row = (
        await db.execute(
            text(
                "SELECT s.id AS session_id, s.user_id, u.email, u.timezone, "
                "s.created_at <= now() - make_interval(days => :max_days) AS too_old, "
                "s.last_seen_at <= now() - make_interval(days => :idle_days) AS idle, "
                "s.last_seen_at <= now() - make_interval(secs => :resolution) AS stale_seen "
                "FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = :h"
            ),
            {
                "h": hash_token(token),
                "max_days": settings.session_max_days,
                "idle_days": settings.session_idle_days,
                "resolution": _LAST_SEEN_RESOLUTION.total_seconds(),
            },
        )
    ).one_or_none()

    if row is None:  # unknown, tampered or already revoked
        raise _unauthenticated(clear_cookie=True)
    if row.too_old or row.idle:
        await _commit_separately(
            request, "DELETE FROM sessions WHERE id = :id", {"id": row.session_id}
        )
        raise _unauthenticated(clear_cookie=True)
    if row.email not in settings.allowed_emails:
        # Removed from the allow-list: revoke every session they have, keep their data.
        await _commit_separately(
            request, "DELETE FROM sessions WHERE user_id = :u", {"u": row.user_id}
        )
        raise _unauthenticated(clear_cookie=True)

    if row.stale_seen:
        await db.execute(
            text("UPDATE sessions SET last_seen_at = now() WHERE id = :id"),
            {"id": row.session_id},
        )
    return CurrentUser(id=row.user_id, email=row.email, timezone=row.timezone)


CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]


async def page_user(request: Request, db: DbSession) -> CurrentUser | None:
    """For full page loads: the signed-in user, or None (the caller redirects to sign-in)."""
    try:
        return await current_user(request, db)
    except HTTPException:
        return None


async def _user_db_session(user: CurrentUserDep, db: DbSession) -> AsyncSession:
    """The request's session, scoped to the signed-in user for row-level security."""
    await set_session_user(db, user.id)
    return db


# Every data route uses this. It's the same transaction as DbSession (FastAPI shares one
# instance per request), with `app.user_id` set, so RLS only exposes this user's rows.
UserDbSession = Annotated[AsyncSession, Depends(_user_db_session)]
