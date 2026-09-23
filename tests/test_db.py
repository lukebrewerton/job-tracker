# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Database plumbing: /readyz, per-request transactions, and transaction-local user scope."""

import uuid
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.db import DbSession, set_session_user
from app.main import create_app

from .conftest import PUBLIC_BASE_URL, make_settings

# --- /readyz ---------------------------------------------------------------------------


def test_readyz_ok_when_database_reachable(static_dir: Path, test_db_url: str) -> None:
    app = create_app(make_settings(static_dir, test_db_url))
    with TestClient(app, base_url=PUBLIC_BASE_URL) as c:
        resp = c.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_503_without_detail_when_database_unreachable(client: TestClient) -> None:
    resp = client.get("/readyz")
    assert resp.status_code == 503
    # No hostnames, driver messages or stack traces in the public response.
    assert resp.json() == {"status": "unavailable"}


def test_healthz_never_touches_database(client: TestClient) -> None:
    # The app's DATABASE_URL is unreachable, yet liveness is fine.
    assert client.get("/healthz").status_code == 200


# --- Transaction-local user scope (the foundation for row-level security) -------------


async def _current_user_setting(session: AsyncSession) -> str | None:
    result = await session.execute(text("SELECT current_setting('app.user_id', true)"))
    return result.scalar_one()


async def test_user_scope_visible_within_transaction(db_session: AsyncSession) -> None:
    user_id = uuid.uuid4()
    await set_session_user(db_session, user_id)
    assert await _current_user_setting(db_session) == str(user_id)


async def test_user_scope_does_not_leak_across_pooled_transactions(test_db_url: str) -> None:
    # One pooled connection, so the second transaction provably reuses the first's.
    engine = create_async_engine(test_db_url, pool_size=1, max_overflow=0)
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                await set_session_user(session, uuid.uuid4())
                pid_first = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                assert await _current_user_setting(session) is not None
            async with session.begin():
                pid_second = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                leaked = await _current_user_setting(session)
        assert pid_first == pid_second, "test must reuse the same pooled connection"
        assert leaked in (None, ""), f"app.user_id leaked into the next transaction: {leaked!r}"
    finally:
        await engine.dispose()


# --- Per-request transaction (DbSession) ------------------------------------------------


@pytest.fixture(scope="module")
async def probe_table(db_engine: AsyncEngine) -> str:
    """A scratch table whose unique constraint is only checked at COMMIT."""
    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS _tx_probe"))
        await conn.execute(
            text(
                "CREATE TABLE _tx_probe (k text, "
                "CONSTRAINT uq_tx_probe UNIQUE (k) DEFERRABLE INITIALLY DEFERRED)"
            )
        )
    return "_tx_probe"


def _app_with_probe_routes(static_dir: Path, test_db_url: str) -> FastAPI:
    app = create_app(make_settings(static_dir, test_db_url))
    router = APIRouter(prefix="/api/_probe")

    @router.post("/{key}")
    async def insert(key: str, session: DbSession) -> dict[str, str]:
        await session.execute(text("INSERT INTO _tx_probe (k) VALUES (:k)"), {"k": key})
        return {"inserted": key}

    @router.post("/{key}/fail")
    async def insert_then_fail(key: str, session: DbSession) -> None:
        await session.execute(text("INSERT INTO _tx_probe (k) VALUES (:k)"), {"k": key})
        raise RuntimeError("boom")

    @router.post("/{key}/twice")
    async def insert_twice(key: str, session: DbSession) -> dict[str, str]:
        # Violates the deferred unique constraint, which only fails at COMMIT.
        for _ in range(2):
            await session.execute(text("INSERT INTO _tx_probe (k) VALUES (:k)"), {"k": key})
        return {"inserted": key}

    # Register ahead of the SPA catch-all, which otherwise answers /api/* with a 404.
    app.router.routes[:0] = router.routes
    return app


async def _rows(db_engine: AsyncEngine, key: str) -> int:
    async with db_engine.connect() as conn:
        result = await conn.execute(text("SELECT count(*) FROM _tx_probe WHERE k = :k"), {"k": key})
        return result.scalar_one()


async def test_db_session_commits_on_success(
    static_dir: Path, test_db_url: str, db_engine: AsyncEngine, probe_table: str
) -> None:
    key = f"ok-{uuid.uuid4()}"
    with TestClient(_app_with_probe_routes(static_dir, test_db_url), base_url=PUBLIC_BASE_URL) as c:
        assert c.post(f"/api/_probe/{key}").status_code == 200
    assert await _rows(db_engine, key) == 1


async def test_db_session_rolls_back_on_error(
    static_dir: Path, test_db_url: str, db_engine: AsyncEngine, probe_table: str
) -> None:
    key = f"fail-{uuid.uuid4()}"
    app = _app_with_probe_routes(static_dir, test_db_url)
    with TestClient(app, base_url=PUBLIC_BASE_URL, raise_server_exceptions=False) as c:
        assert c.post(f"/api/_probe/{key}/fail").status_code == 500
    assert await _rows(db_engine, key) == 0


async def test_commit_failure_is_a_500_not_a_false_success(
    static_dir: Path, test_db_url: str, db_engine: AsyncEngine, probe_table: str
) -> None:
    # The commit happens before the response is sent (scope="function"), so a failure at
    # COMMIT must surface to the client instead of an already-sent 200.
    key = f"twice-{uuid.uuid4()}"
    app = _app_with_probe_routes(static_dir, test_db_url)
    with TestClient(app, base_url=PUBLIC_BASE_URL, raise_server_exceptions=False) as c:
        assert c.post(f"/api/_probe/{key}/twice").status_code == 500
    assert await _rows(db_engine, key) == 0
