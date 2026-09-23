# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared fixtures.

Two kinds of test:
- App tests (no database): the app is built with an unreachable DATABASE_URL. The engine
  is created lazily and never connects unless a test hits the database.
- Database tests: use the `test_db_url` / `db_engine` / `db_session` fixtures, which run
  against a dedicated `<name>_test` database, recreated and migrated once per session.
  They fail (not skip) if Postgres is unreachable: run `make up`.
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import Settings
from app.main import create_app

PUBLIC_BASE_URL = "https://job-tracker.example.test"
# Port 1 on loopback: nothing listens, so connecting fails fast.
UNREACHABLE_DB_URL = "postgresql://unused:unused@127.0.0.1:1/unused"
REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    """A minimal stand-in for Vite's dist/ output."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('app')")
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>")
    (tmp_path / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    return tmp_path


def make_settings(static_dir: Path, database_url: str = UNREACHABLE_DB_URL) -> Settings:
    return Settings(
        public_base_url=PUBLIC_BASE_URL,
        static_dir=static_dir,
        database_url=database_url,
        _env_file=None,
    )


@pytest.fixture
def settings(static_dir: Path) -> Settings:
    return make_settings(static_dir)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), base_url=PUBLIC_BASE_URL) as c:
        yield c


# --- Database ----------------------------------------------------------------------


class _DevDatabase(BaseSettings):
    """Reads DATABASE_URL from the environment or .env, like the app does."""

    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")
    database_url: str | None = None


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """Create a fresh `<dev db>_test` database, migrate it to head, return its URL."""
    raw = _DevDatabase().database_url
    if not raw:
        pytest.fail("DATABASE_URL is not set. Copy .env.example to .env, then `make up`.")
    dev = make_url(raw).set(drivername="postgresql+psycopg")
    test = dev.set(database=f"{dev.database}_test")
    maintenance = dev.set(drivername="postgresql", database="postgres")

    unreachable: str | None = None
    try:
        with psycopg.connect(
            maintenance.render_as_string(hide_password=False), autocommit=True, connect_timeout=5
        ) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{test.database}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{test.database}"')
    except psycopg.OperationalError as exc:
        unreachable = str(exc).splitlines()[0]
    if unreachable:  # fail outside the except block: a clean message, no chained traceback
        where = f"{dev.host}:{dev.port}"
        pytest.fail(f"Postgres unreachable at {where} — run `make up`. ({unreachable})")

    url = test.render_as_string(hide_password=False)
    cfg = Config(REPO_ROOT / "alembic.ini")
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    return url


@pytest.fixture(scope="session")
async def db_engine(test_db_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(test_db_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is always rolled back: tests leave no trace."""
    async with db_engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()
