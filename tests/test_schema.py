# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Initial schema: constraints, cascades, and row-level security isolation between users.

These run against the real migrated test database, as the app's own (non-superuser,
non-BYPASSRLS) role — the only configuration in which RLS is actually enforced.
"""

import uuid
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import UnsafeDatabaseRoleError, check_role_enforces_rls, set_session_user

REPO_ROOT = Path(__file__).resolve().parent.parent
RLS_TABLES = ("jobs", "status_history", "interviews")


# --- Helpers -----------------------------------------------------------------------------


async def _scalar(session: AsyncSession, sql: str, **params: Any) -> Any:
    return (await session.execute(text(sql), params)).scalar_one()


async def _new_user(session: AsyncSession, email: str | None = None) -> uuid.UUID:
    email = email or f"{uuid.uuid4().hex[:8]}@example.test"
    return await _scalar(
        session,
        "INSERT INTO users (oidc_sub, email) VALUES (:sub, :email) RETURNING id",
        sub=uuid.uuid4().hex,
        email=email,
    )


async def _clear_user(session: AsyncSession) -> None:
    """Equivalent to no user being set for the transaction."""
    await session.execute(text("SELECT set_config('app.user_id', '', true)"))


async def _new_job(session: AsyncSession, user_id: uuid.UUID, **cols: Any) -> uuid.UUID:
    await set_session_user(session, user_id)
    values = {"company": "Acme", "role": "Engineer", **cols}
    names = ", ".join(["user_id", *values])
    binds = ", ".join([":user_id", *(f":{k}" for k in values)])
    return await _scalar(
        session,
        f"INSERT INTO jobs ({names}) VALUES ({binds}) RETURNING id",
        user_id=user_id,
        **values,
    )


async def _job_with_children(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    job_id = await _new_job(session, user_id)
    await session.execute(
        text("INSERT INTO status_history (job_id, user_id, status) VALUES (:j, :u, 'saved')"),
        {"j": job_id, "u": user_id},
    )
    await session.execute(
        text("INSERT INTO interviews (job_id, user_id, mode) VALUES (:j, :u, 'remote')"),
        {"j": job_id, "u": user_id},
    )
    return job_id


async def _count(session: AsyncSession, table: str) -> int:
    return await _scalar(session, f"SELECT count(*) FROM {table}")


# --- The role the tests (and app) run as ------------------------------------------------


async def test_connected_role_cannot_bypass_rls(db_session: AsyncSession) -> None:
    """Guards the guard: if the test role bypassed RLS, every isolation test would lie."""
    row = (
        await db_session.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
    ).one()
    assert (row.rolsuper, row.rolbypassrls) == (False, False)


@pytest.mark.parametrize(("superuser", "bypass"), [(True, False), (False, True), (True, True)])
def test_role_guard_rejects_roles_that_skip_rls(superuser: bool, bypass: bool) -> None:
    fake = SimpleNamespace(
        execute=lambda _sql: SimpleNamespace(one=lambda: ("neondb_owner", superuser, bypass))
    )
    with pytest.raises(UnsafeDatabaseRoleError, match="neondb_owner"):
        check_role_enforces_rls(fake)  # type: ignore[arg-type]


def test_role_guard_accepts_a_plain_role() -> None:
    fake = SimpleNamespace(
        execute=lambda _sql: SimpleNamespace(one=lambda: ("jobtracker_app", False, False))
    )
    check_role_enforces_rls(fake)  # type: ignore[arg-type]


# --- Row-level security is actually on ----------------------------------------------------


async def test_rls_enabled_and_forced_on_data_tables_only(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname IN ('users', 'sessions', 'jobs', 'status_history', 'interviews')"
            )
        )
    ).all()
    flags = {r.relname: (r.relrowsecurity, r.relforcerowsecurity) for r in rows}
    assert {t: flags[t] for t in RLS_TABLES} == dict.fromkeys(RLS_TABLES, (True, True))
    assert flags["users"] == (False, False)
    assert flags["sessions"] == (False, False)


# --- Fail closed: no user set -----------------------------------------------------------


async def test_no_user_set_sees_nothing(db_session: AsyncSession) -> None:
    owner = await _new_user(db_session)
    await _job_with_children(db_session, owner)
    await _clear_user(db_session)
    for table in RLS_TABLES:
        assert await _count(db_session, table) == 0, f"{table} leaked rows with no user set"


@pytest.mark.parametrize("table", RLS_TABLES)
async def test_no_user_set_cannot_insert(db_session: AsyncSession, table: str) -> None:
    owner = await _new_user(db_session)
    job_id = await _new_job(db_session, owner)
    await _clear_user(db_session)
    inserts = {
        "jobs": "INSERT INTO jobs (user_id, company, role) VALUES (:u, 'X', 'Y')",
        "status_history": "INSERT INTO status_history (job_id, user_id, status) "
        "VALUES (:j, :u, 'saved')",
        "interviews": "INSERT INTO interviews (job_id, user_id, mode) VALUES (:j, :u, 'phone')",
    }
    with pytest.raises(DBAPIError, match="row-level security"):
        async with db_session.begin_nested():
            await db_session.execute(text(inserts[table]), {"u": owner, "j": job_id})


# --- Cross-user isolation -----------------------------------------------------------------


async def test_other_user_cannot_see_update_or_delete_even_without_where(
    db_session: AsyncSession,
) -> None:
    alice = await _new_user(db_session)
    bob = await _new_user(db_session)
    await _job_with_children(db_session, alice)

    await set_session_user(db_session, bob)
    for table in RLS_TABLES:
        assert await _count(db_session, table) == 0, f"Bob can see Alice's {table}"
    # Raw SQL with no WHERE clause: RLS alone must stop these touching Alice's rows.
    updated = await db_session.execute(text("UPDATE jobs SET company = 'pwned'"))
    assert updated.rowcount == 0  # type: ignore[attr-defined]
    for table in RLS_TABLES:
        deleted = await db_session.execute(text(f"DELETE FROM {table}"))
        assert deleted.rowcount == 0, f"Bob deleted Alice's {table}"  # type: ignore[attr-defined]

    await set_session_user(db_session, alice)
    assert await _scalar(db_session, "SELECT company FROM jobs") == "Acme"
    for table in RLS_TABLES:
        assert await _count(db_session, table) == 1, f"Alice's {table} was changed by Bob"


async def test_cannot_write_rows_claiming_another_users_id(db_session: AsyncSession) -> None:
    alice = await _new_user(db_session)
    bob = await _new_user(db_session)
    await set_session_user(db_session, bob)
    with pytest.raises(DBAPIError, match="row-level security"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("INSERT INTO jobs (user_id, company, role) VALUES (:u, 'X', 'Y')"),
                {"u": alice},
            )


async def test_child_cannot_reference_another_users_job(db_session: AsyncSession) -> None:
    alice = await _new_user(db_session)
    bob = await _new_user(db_session)
    alices_job = await _new_job(db_session, alice)
    # As Bob, with Bob's user_id (so RLS's WITH CHECK passes), pointing at Alice's job:
    # the composite FK (job_id, user_id) -> jobs(id, user_id) must reject it.
    await set_session_user(db_session, bob)
    for sql in (
        "INSERT INTO status_history (job_id, user_id, status) VALUES (:j, :u, 'saved')",
        "INSERT INTO interviews (job_id, user_id, mode) VALUES (:j, :u, 'phone')",
    ):
        with pytest.raises(IntegrityError, match="fk_"):
            async with db_session.begin_nested():
                await db_session.execute(text(sql), {"j": alices_job, "u": bob})


# --- Cascades and constraints -------------------------------------------------------------


async def test_deleting_a_job_cascades_to_history_and_interviews(
    db_session: AsyncSession,
) -> None:
    user = await _new_user(db_session)
    job_id = await _job_with_children(db_session, user)
    await db_session.execute(text("DELETE FROM jobs WHERE id = :j"), {"j": job_id})
    assert await _count(db_session, "status_history") == 0
    assert await _count(db_session, "interviews") == 0


async def test_primary_keys_are_uuidv7(db_session: AsyncSession) -> None:
    user = await _new_user(db_session)
    job_id = await _new_job(db_session, user)
    assert user.version == 7
    assert job_id.version == 7


async def test_canonical_url_unique_per_user_only(db_session: AsyncSession) -> None:
    alice = await _new_user(db_session)
    bob = await _new_user(db_session)
    url = "https://example.test/jobs/1"
    await _new_job(db_session, alice, url_canonical=url)
    await _new_job(db_session, bob, url_canonical=url)  # other users may track the same job
    await _new_job(db_session, alice)  # no-URL jobs never collide
    await _new_job(db_session, alice)
    with pytest.raises(IntegrityError, match="uq_jobs_user_id_url_canonical"):
        async with db_session.begin_nested():
            await _new_job(db_session, alice, url_canonical=url)


@pytest.mark.parametrize(
    ("cols", "constraint"),
    [
        ({"status": "ghosted"}, "ck_jobs_job_status"),
        ({"source": "myspace"}, "ck_jobs_job_source"),
        ({"company": "   "}, "ck_jobs_company_not_blank"),
        ({"role": ""}, "ck_jobs_role_not_blank"),
        ({"company": "x" * 201}, "ck_jobs_company_max_len"),
        ({"notes": "x" * 10_001}, "ck_jobs_notes_max_len"),
    ],
)
async def test_job_check_constraints(
    db_session: AsyncSession, cols: dict[str, str], constraint: str
) -> None:
    user = await _new_user(db_session)
    with pytest.raises(IntegrityError, match=constraint):
        async with db_session.begin_nested():
            await _new_job(db_session, user, **cols)


async def test_email_must_be_lowercase(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_users_email_lowercase"):
        async with db_session.begin_nested():
            await _new_user(db_session, email="Luke@Example.test")


async def test_session_token_must_be_a_sha256_hex_digest(db_session: AsyncSession) -> None:
    user = await _new_user(db_session)
    with pytest.raises(IntegrityError, match="ck_sessions_token_hash_sha256_hex"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("INSERT INTO sessions (user_id, token_hash) VALUES (:u, 'raw-token')"),
                {"u": user},
            )


# --- Migrations: full round trip on an empty database -------------------------------------


@pytest.fixture
def empty_database(test_db_url: str) -> Iterator[str]:
    """A brand-new, empty database (separate from the shared test database)."""
    url = make_url(test_db_url)
    scratch = url.set(database=f"{url.database}_migrations")
    maintenance = url.set(drivername="postgresql", database="postgres")
    admin = maintenance.render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{scratch.database}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{scratch.database}"')
    try:
        yield scratch.render_as_string(hide_password=False)
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{scratch.database}" WITH (FORCE)')


def _public_tables(url: str) -> set[str]:
    plain = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain) as conn:
        rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        return {r[0] for r in rows}


def test_upgrade_downgrade_upgrade_round_trip(empty_database: str) -> None:
    cfg = Config(REPO_ROOT / "alembic.ini")
    cfg.attributes["database_url"] = empty_database
    cfg.attributes["configure_logger"] = False
    schema = {"users", "sessions", "jobs", "status_history", "interviews"}

    command.upgrade(cfg, "head")
    # Also catches migrations that "run" but silently roll back instead of committing.
    assert schema <= _public_tables(empty_database)

    command.downgrade(cfg, "base")
    assert _public_tables(empty_database) == {"alembic_version"}

    command.upgrade(cfg, "head")
    assert schema <= _public_tables(empty_database)
