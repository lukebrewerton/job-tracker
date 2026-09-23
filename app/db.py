# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Database plumbing: engine, declarative base, and per-request sessions.

Every request that touches the database runs in exactly one transaction: committed when
the route returns, rolled back on any exception. The session dependency uses
`scope="function"` so the commit happens *before* the response is sent — a failed commit
becomes a 500, never a false 200.

Row-level security (JT-12) keys off the `app.user_id` setting. It is set with
`set_config(..., is_local => true)`, i.e. only for the current transaction, so it can
never leak to another request through the connection pool.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings

# Deterministic constraint names, so Alembic autogenerate produces stable, reviewable
# migrations (and constraints can be dropped by name).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_engine(settings: Settings) -> AsyncEngine:
    """Engine tuned for Neon, which suspends after 5 min idle and drops connections."""
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,  # detect connections Neon closed while suspended
        pool_recycle=240,  # recycle before Neon's 5-minute suspend
        pool_size=5,
        connect_args={"connect_timeout": 10},  # absorbs a Neon cold start (~2s)
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def set_session_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Scope the current transaction to `user_id` for row-level security."""
    await session.execute(
        text("SELECT set_config('app.user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )


async def _db_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session, session.begin():
        yield session


# Unscoped session: no `app.user_id`, so RLS-protected tables return nothing. Only the
# auth code (users, sessions) uses this directly. The user-scoped variant builds on it
# once there is a current user (JT-15).
DbSession = Annotated[AsyncSession, Depends(_db_session, scope="function")]
