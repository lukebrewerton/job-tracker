# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Interviews: CRUD under /api/jobs/{job_id}/interviews, and /api/interviews across jobs.

A single interview is found through both the job in the URL and the current user: an
interview under the wrong job, or another user's, is a 404, like a missing one.
"""

import uuid

from fastapi import APIRouter, HTTPException, Response

from app import interviews, timezones
from app.models import Interview, Job
from app.schemas import (
    InterviewCreate,
    InterviewGroups,
    InterviewOut,
    InterviewUpdate,
    InterviewWithJob,
    JobSummary,
)
from app.sessions import CurrentUserDep, UserDbSession

job_router = APIRouter(prefix="/jobs/{job_id}/interviews", tags=["interviews"])
router = APIRouter(prefix="/interviews", tags=["interviews"])

_JOB_NOT_FOUND = HTTPException(status_code=404, detail="Job not found")
_NOT_FOUND = HTTPException(status_code=404, detail="Interview not found")


def _out(interview: Interview) -> InterviewOut:
    return InterviewOut(
        id=interview.id,
        job_id=interview.job_id,
        scheduled_at=interview.scheduled_at,
        mode=interview.mode,
        round_label=interview.round_label,
        notes=interview.notes,
        created_at=interview.created_at,
    )


def interview_with_job(interview: Interview, job: Job) -> InterviewWithJob:
    summary = JobSummary(id=job.id, company=job.company, role=job.role, status=job.status)
    return InterviewWithJob(**_out(interview).model_dump(), job=summary)


@job_router.get("")
async def list_job_interviews(
    user: CurrentUserDep, db: UserDbSession, job_id: uuid.UUID
) -> list[InterviewOut]:
    """A job's interviews: scheduled ones by date, then unscheduled ones."""
    found = await interviews.list_for_job(db, user.id, job_id)
    if found is None:
        raise _JOB_NOT_FOUND
    return [_out(i) for i in found]


@job_router.post("", status_code=201)
async def create_interview(
    user: CurrentUserDep, db: UserDbSession, job_id: uuid.UUID, body: InterviewCreate
) -> InterviewOut:
    """Add an interview. Every field is optional; the job's status doesn't change."""
    interview = await interviews.create(db, user.id, job_id, body.model_dump())
    if interview is None:
        raise _JOB_NOT_FOUND
    return _out(interview)


@job_router.get("/{interview_id}")
async def get_interview(
    user: CurrentUserDep, db: UserDbSession, job_id: uuid.UUID, interview_id: uuid.UUID
) -> InterviewOut:
    interview = await interviews.get(db, user.id, job_id, interview_id)
    if interview is None:
        raise _NOT_FOUND
    return _out(interview)


@job_router.patch("/{interview_id}")
async def update_interview(
    user: CurrentUserDep,
    db: UserDbSession,
    job_id: uuid.UUID,
    interview_id: uuid.UUID,
    body: InterviewUpdate,
) -> InterviewOut:
    """Change only the fields sent; null clears a field."""
    changes = body.model_dump(exclude_unset=True)
    interview = await interviews.update(db, user.id, job_id, interview_id, changes)
    if interview is None:
        raise _NOT_FOUND
    return _out(interview)


@job_router.delete("/{interview_id}", status_code=204)
async def delete_interview(
    user: CurrentUserDep, db: UserDbSession, job_id: uuid.UUID, interview_id: uuid.UUID
) -> Response:
    if not await interviews.delete(db, user.id, job_id, interview_id):
        raise _NOT_FOUND
    return Response(status_code=204)


@router.get("")
async def interview_groups(user: CurrentUserDep, db: UserDbSession) -> InterviewGroups:
    """All your interviews in three groups.

    - **upcoming**: from now on, soonest first (including closed jobs, so a booking you
      no longer need stays visible);
    - **not_yet_scheduled**: no date yet, on active jobs only, oldest first;
    - **past**: most recent first.
    """
    groups = await interviews.grouped(db, user.id, now=timezones.now())
    return InterviewGroups(
        upcoming=[interview_with_job(i, j) for i, j in groups.upcoming],
        not_yet_scheduled=[interview_with_job(i, j) for i, j in groups.not_yet_scheduled],
        past=[interview_with_job(i, j) for i, j in groups.past],
    )
