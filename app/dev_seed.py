# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sample data for local development: `make seed EMAIL=you@example.com`.

Adds about 60 varied jobs to one existing user (sign in once first): every status,
status changes backdated so each dashboard list is populated, long names, and enough
rows to page through, plus some interviews. Development only: it refuses to run unless
ENVIRONMENT=development. Running it again replaces its own sample jobs (marked in their
notes) and never touches anything else: not the user's other jobs, not other users.
"""

import asyncio
import random
import sys
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.db import create_engine
from app.models import JobStatus

SAMPLE_MARKER = "Sample job (make seed)"

COMPANIES = [
    "Acme Ltd",
    "Globex Corporation",
    "Initech",
    "Umbrella plc",
    "Hooli",
    "Stark Industries",
    "Wayne Enterprises",
    "Cyberdyne Systems",
    "Tyrell Corporation",
    "Soylent",
    "Monzo",
    "Octopus Energy",
    "The Very Long Company Name Holdings International Group Limited",
    "Accenture",
    "Pacific Data",
]
ROLES = [
    "Platform Engineer",
    "Senior Platform Engineer",
    "Site Reliability Engineer",
    "DevOps Engineer",
    "Cloud Infrastructure Engineer",
    "Staff Engineer, Developer Experience and Internal Tooling Platform",
    "Engineering Manager",
]
LOCATIONS = ["London", "Remote (UK)", "Manchester", "Hybrid, Bristol", None]

# (status, how many, range of days since the last status change)
MIX: list[tuple[JobStatus, int, tuple[int, int]]] = [
    (JobStatus.SAVED, 8, (0, 20)),
    (JobStatus.APPLIED, 18, (0, 30)),
    (JobStatus.INTERVIEWING, 6, (0, 20)),
    (JobStatus.OFFER, 3, (2, 15)),
    (JobStatus.ACCEPTED, 1, (5, 10)),
    (JobStatus.REJECTED, 12, (1, 60)),
    (JobStatus.WITHDRAWN, 4, (3, 40)),
    (JobStatus.NO_RESPONSE, 8, (15, 60)),
]


class SeedError(Exception):
    pass


async def seed(engine: AsyncEngine, email: str, *, now: datetime) -> int:
    """Replace the user's sample jobs with a fresh set. Returns how many were added."""
    rng = random.Random(42)  # the same data every run
    async with engine.begin() as conn:
        user_id = (
            await conn.execute(
                text("SELECT id FROM users WHERE email = :e"), {"e": email.strip().lower()}
            )
        ).scalar_one_or_none()
        if user_id is None:
            raise SeedError(f"No user {email!r}: sign in once first, then run this again.")
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_id)})
        await conn.execute(
            text("DELETE FROM jobs WHERE user_id = :u AND notes = :m"),
            {"u": user_id, "m": SAMPLE_MARKER},
        )

        added = 0
        for status, count, (min_days, max_days) in MIX:
            for _ in range(count):
                days = rng.randint(min_days, max_days)
                changed = now - timedelta(days=days, hours=rng.randint(0, 20))
                created = changed - timedelta(days=rng.randint(0, 30))
                applied: date | None = None
                if status != JobStatus.SAVED and rng.random() > 0.15:
                    applied = (created + timedelta(days=rng.randint(0, 3))).date()
                    applied = min(applied, changed.date())
                job_id: uuid.UUID = (
                    await conn.execute(
                        text(
                            "INSERT INTO jobs (user_id, company, role, location, status, "
                            "applied_at, notes, created_at, updated_at) "
                            "VALUES (:u, :c, :r, :l, :s, :a, :n, :t, :t) RETURNING id"
                        ),
                        {
                            "u": user_id,
                            "c": rng.choice(COMPANIES),
                            "r": rng.choice(ROLES),
                            "l": rng.choice(LOCATIONS),
                            "s": status.value,
                            "a": applied,
                            "n": SAMPLE_MARKER,
                            "t": created,
                        },
                    )
                ).scalar_one()
                history = [(JobStatus.SAVED, created)]
                if status == JobStatus.REJECTED and rng.random() < 0.5:
                    # Rejected after an interview, for the dashboard's split.
                    history.append((JobStatus.INTERVIEWING, created + (changed - created) / 2))
                if status != JobStatus.SAVED:
                    history.append((status, changed))
                for history_status, at in history:
                    await conn.execute(
                        text(
                            "INSERT INTO status_history (job_id, user_id, status, changed_at) "
                            "VALUES (:j, :u, :s, :t)"
                        ),
                        {"j": job_id, "u": user_id, "s": history_status.value, "t": at},
                    )
                if status == JobStatus.INTERVIEWING:
                    for offset_days, label in ((rng.randint(1, 10), "Technical"), (None, None)):
                        await conn.execute(
                            text(
                                "INSERT INTO interviews (job_id, user_id, scheduled_at, mode, "
                                "round_label) VALUES (:j, :u, :t, 'remote', :l)"
                            ),
                            {
                                "j": job_id,
                                "u": user_id,
                                "t": now + timedelta(days=offset_days) if offset_days else None,
                                "l": label,
                            },
                        )
                added += 1
    return added


async def _main(email: str) -> None:
    settings = Settings()
    if not settings.is_development:
        raise SeedError("Refusing to seed: ENVIRONMENT isn't development.")
    engine = create_engine(settings)
    try:
        added = await seed(engine, email, now=datetime.now(UTC))
    finally:
        await engine.dispose()
    print(f"Added {added} sample jobs for {email} (replacing any from a previous run).")


if __name__ == "__main__":
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        sys.exit("Usage: make seed EMAIL=you@example.com")
    try:
        asyncio.run(_main(sys.argv[1]))
    except SeedError as exc:
        sys.exit(str(exc))
