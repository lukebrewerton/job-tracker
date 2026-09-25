# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Data access for interviews: every function takes the current user and filters by it.

A single interview is only ever found through **both** its job and its user, so another
user's interview can't be reached by putting it under one of your own jobs. Interview
rows carry their job's user_id; the composite foreign key (job_id, user_id) →
jobs(id, user_id) makes a mismatch impossible in the database too.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs import ACTIVE_STATUSES
from app.models import Interview, Job


async def _owns_job(db: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    found = await db.execute(sa.select(Job.id).where(Job.id == job_id, Job.user_id == user_id))
    return found.scalar_one_or_none() is not None


def _select_one(user_id: uuid.UUID, job_id: uuid.UUID, interview_id: uuid.UUID) -> sa.Select[Any]:
    return sa.select(Interview).where(
        Interview.id == interview_id,
        Interview.job_id == job_id,
        Interview.user_id == user_id,
    )


async def list_for_job(
    db: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> list[Interview] | None:
    """A job's interviews: scheduled ones by date, then unscheduled ones, oldest first.

    None if it isn't this user's job.
    """
    if not await _owns_job(db, user_id, job_id):
        return None
    rows = await db.execute(
        sa.select(Interview)
        .where(Interview.job_id == job_id, Interview.user_id == user_id)
        .order_by(Interview.scheduled_at.asc().nulls_last(), Interview.created_at, Interview.id)
    )
    return list(rows.scalars())


async def get(
    db: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID, interview_id: uuid.UUID
) -> Interview | None:
    result = await db.execute(_select_one(user_id, job_id, interview_id))
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID, fields: Mapping[str, Any]
) -> Interview | None:
    """Add an interview to a job. None if it isn't this user's job.

    Deliberately doesn't change the job's status: that stays a choice the user makes.
    """
    if not await _owns_job(db, user_id, job_id):
        return None
    interview = Interview(job_id=job_id, user_id=user_id, **fields)
    db.add(interview)
    await db.flush()
    await db.refresh(interview)
    return interview


async def update(
    db: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    interview_id: uuid.UUID,
    changes: Mapping[str, Any],
) -> Interview | None:
    """Apply a partial update. None if the interview isn't under this user's job."""
    interview = await get(db, user_id, job_id, interview_id)
    if interview is None:
        return None
    for field, value in changes.items():
        setattr(interview, field, value)
    await db.flush()
    return interview


async def delete(
    db: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID, interview_id: uuid.UUID
) -> bool:
    deleted = await db.execute(
        sa.delete(Interview)
        .where(
            Interview.id == interview_id,
            Interview.job_id == job_id,
            Interview.user_id == user_id,
        )
        .returning(Interview.id)
    )
    return deleted.scalar_one_or_none() is not None


@dataclass(frozen=True)
class Groups:
    upcoming: list[tuple[Interview, Job]]  # soonest first
    not_yet_scheduled: list[tuple[Interview, Job]]  # active jobs only, oldest first
    past: list[tuple[Interview, Job]]  # most recent first


async def grouped(db: AsyncSession, user_id: uuid.UUID, *, now: datetime) -> Groups:
    """All the user's interviews, with their jobs, in the three groups.

    "Upcoming" starts at `now`: an interview earlier today is past. It includes closed
    jobs, so an interview still booked on a job since rejected stays visible (to be
    deleted) rather than silently vanishing. Unscheduled ones only count for active jobs.
    """
    base = (
        sa.select(Interview, Job)
        .join(Job, (Job.id == Interview.job_id) & (Job.user_id == Interview.user_id))
        .where(Interview.user_id == user_id)
    )
    upcoming = await db.execute(
        base.where(Interview.scheduled_at >= now).order_by(Interview.scheduled_at, Interview.id)
    )
    unscheduled = await db.execute(
        base.where(Interview.scheduled_at.is_(None), Job.status.in_(ACTIVE_STATUSES)).order_by(
            Interview.created_at, Interview.id
        )
    )
    past = await db.execute(
        base.where(Interview.scheduled_at < now).order_by(
            Interview.scheduled_at.desc(), Interview.id.desc()
        )
    )
    return Groups(
        upcoming=list(upcoming.tuples()),
        not_yet_scheduled=list(unscheduled.tuples()),
        past=list(past.tuples()),
    )
