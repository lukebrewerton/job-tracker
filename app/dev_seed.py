# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sample data for local development: `make seed EMAIL=you@example.com`.

Adds about 60 varied jobs to one existing user (sign in once first): every status,
status changes backdated so each dashboard list is populated, long names, and enough
rows to page through, plus interviews for every group on the interviews page.
Development only: it refuses to run unless ENVIRONMENT=development. Running it again
replaces its own sample jobs (marked in their notes) and never touches anything else:
not the user's other jobs, not other users.
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


# An interview: (when, mode, round label, notes).
SeedInterview = tuple[datetime | None, str | None, str | None, str | None]


class SeedError(Exception):
    pass


def _on_the_hour(at: datetime) -> datetime:
    return at.replace(minute=0, second=0, microsecond=0)


def _interviews(
    status: JobStatus,
    nth: int,
    rng: random.Random,
    *,
    now: datetime,
    created: datetime,
    changed: datetime,
    interviewed: datetime | None,
) -> list[SeedInterview]:
    """The nth job of a status's interviews: a fixed plan, so every case always appears.

    Upcoming ones today, tomorrow and later; unscheduled ones; past ones; every mode; a
    custom round; notes; and a withdrawn job's booking, which stays under Upcoming but
    whose undated interview doesn't appear under Not yet scheduled.
    """

    def past() -> datetime:
        at = changed - timedelta(days=rng.randint(1, 4), hours=rng.randint(0, 6))
        return _on_the_hour(min(max(at, created + timedelta(hours=1)), now - timedelta(hours=1)))

    def ahead(days: int, hour_offset: int = 0) -> datetime:
        return _on_the_hour(now + timedelta(days=days, hours=hour_offset))

    match status:
        case JobStatus.INTERVIEWING:
            screen: SeedInterview = (past(), "phone", "Phone screen", None)
            next_round: list[SeedInterview] = [
                (ahead(0, 3), "remote", "Technical", "Bring a laptop: pairing in Python."),
                (ahead(1), "in_person", "Hiring manager", None),
                (ahead(3), "remote", "Pairing session", None),  # a custom round
                (ahead(7), None, "Panel", None),
                (None, "remote", "Final", None),
                (None, None, None, None),
            ]
            return [screen, next_round[nth % len(next_round)]]
        case JobStatus.OFFER:
            return [(past(), "remote", "Technical", None), (past(), "in_person", "Final", None)]
        case JobStatus.REJECTED if interviewed is not None:
            return [(_on_the_hour(interviewed), "remote", "Technical", "Felt it went well.")]
        case JobStatus.WITHDRAWN if nth == 0:
            return [
                (ahead(5), "phone", "Recruiter call", "Withdrew: cancel this call."),
                (None, None, "Technical", None),
            ]
        case _:
            return []


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
            for nth in range(count):
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
                interviewed: datetime | None = None
                if status == JobStatus.REJECTED and rng.random() < 0.5:
                    # Rejected after an interview, for the dashboard's split.
                    interviewed = created + (changed - created) / 2
                    history.append((JobStatus.INTERVIEWING, interviewed))
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
                planned = _interviews(
                    status,
                    nth,
                    rng,
                    now=now,
                    created=created,
                    changed=changed,
                    interviewed=interviewed,
                )
                for when, mode, label, notes in planned:
                    await conn.execute(
                        text(
                            "INSERT INTO interviews (job_id, user_id, scheduled_at, mode, "
                            "round_label, notes) VALUES (:j, :u, :t, :m, :l, :n)"
                        ),
                        {"j": job_id, "u": user_id, "t": when, "m": mode, "l": label, "n": notes},
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
