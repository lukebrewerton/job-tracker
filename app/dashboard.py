# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The dashboard: tile counts, the three "needs attention" lists and upcoming interviews.

Everything is computed from the current user's data only. Days are whole calendar days
in the user's own time zone: a change at 23:50 on Monday is one day old on Tuesday.
Only a status change counts as movement; editing other fields doesn't reset the clock.

With STALE_AFTER_DAYS = 7 and NO_RESPONSE_AFTER_DAYS = 14, a job is in at most one list:

- needs follow-up: `applied` for 7-13 days, or `offer` for 7 days or more (an offer
  is never quietly dropped, so there's no upper bound);
- no response?:    `applied` for 14 days or more;
- still to apply:  `saved` for 7 days or more.

`interviewing` jobs are in none of them: after an interview the other side almost
always gets back to you.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app import timezones
from app.jobs import ACTIVE_STATUSES, last_change
from app.models import Interview, Job, JobStatus, StatusHistory

UPCOMING_INTERVIEWS_SHOWN = 5

Attention = Literal["needs_follow_up", "still_to_apply", "no_response"]


def attention_for(
    status: JobStatus, days: int, *, stale_after_days: int, no_response_after_days: int
) -> Attention | None:
    """Which dashboard list a job belongs in, if any: the one rule, shared by the
    dashboard and the jobs list (which highlights the same jobs)."""
    if days < stale_after_days:
        return None
    if status == JobStatus.SAVED:
        return "still_to_apply"
    if status == JobStatus.OFFER:
        return "needs_follow_up"
    if status == JobStatus.APPLIED:
        return "needs_follow_up" if days < no_response_after_days else "no_response"
    return None  # interviewing, and closed jobs, need no chasing


@dataclass(frozen=True)
class Counts:
    active: int
    saved: int
    applied_ever: int
    interviewing: int
    offer: int
    rejected_at_application: int
    rejected_after_interview: int
    no_response: int
    withdrawn: int
    accepted: int


@dataclass(frozen=True)
class StaleJob:
    job: Job
    last_status_change_at: datetime
    days_since_last_change: int


@dataclass(frozen=True)
class Dashboard:
    counts: Counts
    needs_follow_up: list[StaleJob]
    still_to_apply: list[StaleJob]
    no_response_candidates: list[StaleJob]
    upcoming_interviews: list[tuple[Interview, Job]]
    upcoming_interviews_total: int


async def _counts(db: AsyncSession, user_id: uuid.UUID) -> Counts:
    by_status = dict.fromkeys(JobStatus, 0)
    rows = await db.execute(
        sa.select(Job.status, sa.func.count()).where(Job.user_id == user_id).group_by(Job.status)
    )
    by_status.update(dict(rows.tuples().all()))

    applied_ever = (
        await db.execute(
            sa.select(sa.func.count()).where(Job.user_id == user_id, Job.applied_at.is_not(None))
        )
    ).scalar_one()
    # A rejection counts as "after interview" if the job was ever `interviewing`.
    was_interviewing = (
        sa.select(StatusHistory.id)
        .where(
            StatusHistory.job_id == Job.id,
            StatusHistory.user_id == user_id,
            StatusHistory.status == JobStatus.INTERVIEWING,
        )
        .exists()
    )
    after_interview = (
        await db.execute(
            sa.select(sa.func.count()).where(
                Job.user_id == user_id, Job.status == JobStatus.REJECTED, was_interviewing
            )
        )
    ).scalar_one()

    return Counts(
        active=sum(by_status[s] for s in ACTIVE_STATUSES),
        saved=by_status[JobStatus.SAVED],
        applied_ever=applied_ever,
        interviewing=by_status[JobStatus.INTERVIEWING],
        offer=by_status[JobStatus.OFFER],
        rejected_at_application=by_status[JobStatus.REJECTED] - after_interview,
        rejected_after_interview=after_interview,
        no_response=by_status[JobStatus.NO_RESPONSE],
        withdrawn=by_status[JobStatus.WITHDRAWN],
        accepted=by_status[JobStatus.ACCEPTED],
    )


async def build(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    timezone: str,
    stale_after_days: int,
    no_response_after_days: int,
) -> Dashboard:
    now = timezones.now()
    today = timezones.date_in(now, timezone)

    last = last_change(user_id)
    last_at = sa.func.coalesce(last.c.changed_at, Job.created_at)
    candidates = await db.execute(
        sa.select(Job, last_at)
        .outerjoin(last, last.c.job_id == Job.id)
        .where(
            Job.user_id == user_id,
            Job.status.in_([JobStatus.SAVED, JobStatus.APPLIED, JobStatus.OFFER]),
        )
        .order_by(last_at, Job.id)  # oldest first
    )

    needs_follow_up: list[StaleJob] = []
    still_to_apply: list[StaleJob] = []
    no_response: list[StaleJob] = []
    lists: dict[Attention, list[StaleJob]] = {
        "needs_follow_up": needs_follow_up,
        "still_to_apply": still_to_apply,
        "no_response": no_response,
    }
    for job, changed_at in candidates.tuples():
        days = (today - timezones.date_in(changed_at, timezone)).days
        attention = attention_for(
            job.status,
            days,
            stale_after_days=stale_after_days,
            no_response_after_days=no_response_after_days,
        )
        if attention is not None:
            lists[attention].append(StaleJob(job, changed_at, days))

    upcoming = (
        sa.select(Interview, Job)
        .join(Job, (Job.id == Interview.job_id) & (Job.user_id == Interview.user_id))
        .where(Interview.user_id == user_id, Interview.scheduled_at >= now)
    )
    shown = await db.execute(
        upcoming.order_by(Interview.scheduled_at, Interview.id).limit(UPCOMING_INTERVIEWS_SHOWN)
    )
    total = (
        await db.execute(sa.select(sa.func.count()).select_from(upcoming.subquery()))
    ).scalar_one()

    return Dashboard(
        counts=await _counts(db, user_id),
        needs_follow_up=needs_follow_up,
        still_to_apply=still_to_apply,
        no_response_candidates=no_response,
        upcoming_interviews=list(shown.tuples()),
        upcoming_interviews_total=total,
    )
