# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""/api/jobs: list, create, read, update and delete jobs, and company matching.

Included in `api_router`, so every route here requires a session. Another user's job,
like a missing one, is a 404: never a 403, which would confirm it exists.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AfterValidator
from pydantic_core import PydanticCustomError

from app import jobs
from app.schemas import (
    SAVED_WITH_APPLIED_AT,
    CompanyMatch,
    CompanyMatches,
    DuplicateJob,
    JobCreate,
    JobOut,
    JobPage,
    JobUpdate,
)
from app.sessions import CurrentUserDep, UserDbSession

router = APIRouter(prefix="/jobs", tags=["jobs"])

_NOT_FOUND = HTTPException(status_code=404, detail="Job not found")
_DUPLICATE: dict[int | str, dict[str, Any]] = {409: {"model": DuplicateJob}}
MIN_SEARCH_CHARS = 2
PAGE_SIZES = (25, 50, 100)


def _min_chars(value: str | None, *, length: int) -> str | None:
    if value is None:
        return None
    if length < MIN_SEARCH_CHARS:
        raise PydanticCustomError("too_short", f"Enter at least {MIN_SEARCH_CHARS} characters")
    return value


def _search_text(value: str | None) -> str | None:
    value = (value or "").strip() or None
    return _min_chars(value, length=len(value or ""))


def _page_size(value: int) -> int:
    if value not in PAGE_SIZES:
        raise PydanticCustomError("page_size", "Page size must be 25, 50 or 100")
    return value


def _company_query(value: str) -> str:
    _min_chars(value, length=len(jobs.normalise_company(value)))
    return value


def _out(row: jobs.JobRow) -> JobOut:
    job = row.job
    return JobOut(
        id=job.id,
        company=job.company,
        role=job.role,
        url=job.url,
        location=job.location,
        source=job.source,
        salary=job.salary,
        contact_name=job.contact_name,
        contact_email=job.contact_email,
        status=job.status,
        applied_at=job.applied_at,
        notes=job.notes,
        created_at=job.created_at,
        updated_at=job.updated_at,
        last_status_change_at=row.last_status_change_at,
    )


def _duplicate(exc: jobs.DuplicateJobError) -> JSONResponse:
    body = DuplicateJob(existing_id=exc.existing_id)
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


@router.get("")
async def list_jobs(
    user: CurrentUserDep,
    db: UserDbSession,
    status: jobs.StatusFilter = "active",
    q: Annotated[str | None, AfterValidator(_search_text), Query()] = None,
    sort: jobs.SortField = "created_at",
    order: jobs.SortOrder = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, AfterValidator(_page_size), Query()] = PAGE_SIZES[0],
) -> JobPage:
    """Jobs matching the filter (a status, `active` or `all`) and search, one page at a time.

    `q` searches company and role (case-insensitive, at least 2 characters). `counts`
    gives every status's total across all your jobs, ignoring the filter and search.
    """
    rows, total, counts = await jobs.list_jobs(
        db,
        user.id,
        status=status,
        search=q,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    return JobPage(
        items=[_out(r) for r in rows], total=total, page=page, page_size=page_size, counts=counts
    )


@router.post("", status_code=201, response_model=JobOut, responses=_DUPLICATE)
async def create_job(
    user: CurrentUserDep, db: UserDbSession, body: JobCreate
) -> JobOut | JSONResponse:
    """Create a job. 409 with the existing job's id if you already track this URL."""
    try:
        row = await jobs.create_job(db, user.id, body.model_dump(), today=jobs.utc_today())
    except jobs.DuplicateJobError as exc:
        return _duplicate(exc)
    return _out(row)


# Declared before /{job_id}, so "company-matches" is never parsed as a job id.
@router.get("/company-matches")
async def company_matches(
    user: CurrentUserDep,
    db: UserDbSession,
    company: Annotated[str, AfterValidator(_company_query), Query()],
) -> CompanyMatches:
    """Your jobs at companies whose name matches, by the start of a word.

    Case, punctuation and legal suffixes (Ltd, Limited, Inc…) are ignored when matching,
    so "acme" finds "ACME" and "Acme Ltd", and "ac" also finds "Accenture" (but not
    "Pacific"). Each name is returned as entered, with its own counts: nothing is merged.
    """
    matches = await jobs.company_matches(db, user.id, company)
    return CompanyMatches(
        companies=[
            CompanyMatch(name=name, total=sum(by_status.values()), by_status=by_status)
            for name, by_status in matches
        ]
    )


@router.get("/{job_id}")
async def get_job(user: CurrentUserDep, db: UserDbSession, job_id: uuid.UUID) -> JobOut:
    row = await jobs.get_job(db, user.id, job_id)
    if row is None:
        raise _NOT_FOUND
    return _out(row)


@router.patch("/{job_id}", response_model=JobOut, responses=_DUPLICATE)
async def update_job(
    user: CurrentUserDep, db: UserDbSession, job_id: uuid.UUID, body: JobUpdate
) -> JobOut | JSONResponse:
    """Change only the fields sent; null clears an optional field. Not the status (JT-26)."""
    try:
        row = await jobs.update_job(db, user.id, job_id, body.model_dump(exclude_unset=True))
    except jobs.DuplicateJobError as exc:
        return _duplicate(exc)
    except jobs.AppliedAtOnSavedJobError:
        raise RequestValidationError(
            [
                {
                    "type": "saved_with_applied_at",
                    "loc": ("body", "applied_at"),
                    "msg": SAVED_WITH_APPLIED_AT,
                    "input": body.applied_at.isoformat() if body.applied_at else None,
                }
            ]
        ) from None
    if row is None:
        raise _NOT_FOUND
    return _out(row)


@router.delete("/{job_id}", status_code=204)
async def delete_job(user: CurrentUserDep, db: UserDbSession, job_id: uuid.UUID) -> Response:
    """Delete a job permanently, with its status history and interviews."""
    if not await jobs.delete_job(db, user.id, job_id):
        raise _NOT_FOUND
    return Response(status_code=204)
