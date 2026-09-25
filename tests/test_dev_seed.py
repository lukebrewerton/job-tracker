# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The development seed command: it only ever touches one user's own sample jobs."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app import dev_seed
from app.dev_seed import SAMPLE_MARKER, SeedError, seed

from .conftest import make_settings
from .isolation import new_user

NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)


async def _rows(engine: AsyncEngine, user_id: Any, sql: str) -> list[Any]:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_id)})
        return list((await conn.execute(text(sql))).all())


async def _email(engine: AsyncEngine, user_id: Any) -> str:
    async with engine.begin() as conn:
        found = await conn.execute(text("SELECT email FROM users WHERE id = :u"), {"u": user_id})
        return str(found.scalar_one())


async def test_seeds_a_varied_set_for_the_user(db_engine: AsyncEngine) -> None:
    user, _ = await new_user(db_engine)
    added = await seed(db_engine, await _email(db_engine, user), now=NOW)
    statuses = dict(
        await _rows(db_engine, user, "SELECT status, count(*) FROM jobs GROUP BY status")
    )
    assert added == 60 == sum(statuses.values())
    assert set(statuses) == {
        "saved",
        "applied",
        "interviewing",
        "offer",
        "accepted",
        "rejected",
        "withdrawn",
        "no_response",
    }
    # Every job has history; saved jobs never have an applied date (the database agrees).
    orphans = await _rows(
        db_engine,
        user,
        "SELECT id FROM jobs j WHERE NOT EXISTS "
        "(SELECT 1 FROM status_history h WHERE h.job_id = j.id)",
    )
    assert orphans == []


async def test_running_again_replaces_only_its_own_sample_jobs(db_engine: AsyncEngine) -> None:
    user, _ = await new_user(db_engine)
    other, _ = await new_user(db_engine)
    email = await _email(db_engine, user)
    for owner in (user, other):
        async with db_engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.user_id', :u, true)"), {"u": str(owner)}
            )
            await conn.execute(
                text("INSERT INTO jobs (user_id, company, role) VALUES (:u, 'Real', 'Job')"),
                {"u": owner},
            )

    await seed(db_engine, email, now=NOW)
    await seed(db_engine, email, now=NOW)

    mine = await _rows(db_engine, user, "SELECT notes FROM jobs")
    assert sum(1 for (notes,) in mine if notes == SAMPLE_MARKER) == 60  # not 120
    assert sum(1 for (notes,) in mine if notes is None) == 1  # the real job survives
    assert len(await _rows(db_engine, other, "SELECT id FROM jobs")) == 1  # untouched


async def test_an_unknown_user_is_an_error(db_engine: AsyncEngine) -> None:
    with pytest.raises(SeedError, match="sign in once first"):
        await seed(db_engine, "nobody@example.test", now=NOW)


def test_refuses_outside_development(monkeypatch: pytest.MonkeyPatch, static_dir: Path) -> None:
    production = make_settings(static_dir).model_copy(update={"environment": "production"})
    monkeypatch.setattr(dev_seed, "Settings", lambda: production)
    with pytest.raises(SeedError, match="isn't development"):
        import asyncio

        asyncio.run(dev_seed._main("anyone@example.test"))
