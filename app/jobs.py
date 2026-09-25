# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Data access for jobs: every function takes the current user and filters by it.

Row-level security (the request's `app.user_id`) is the backstop, not the only line of
defence: a query here that forgot its user filter would still see only this user's
rows, but no query here relies on that.
"""

import re
import uuid
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobStatus, StatusHistory
from app.urls import canonicalise_url

ACTIVE_STATUSES = frozenset(
    {JobStatus.SAVED, JobStatus.APPLIED, JobStatus.INTERVIEWING, JobStatus.OFFER}
)
StatusFilter = Literal["active", "all"] | JobStatus
SortField = Literal["company", "role", "status", "last_status_change", "applied_at", "created_at"]
SortOrder = Literal["asc", "desc"]

_URL_UNIQUE_INDEX = "uq_jobs_user_id_url_canonical"
# Status sorts in lifecycle order, not alphabetically.
_STATUS_ORDER = {status: rank for rank, status in enumerate(JobStatus)}


class DuplicateJobError(Exception):
    def __init__(self, existing_id: uuid.UUID) -> None:
        super().__init__(f"Already tracked as {existing_id}")
        self.existing_id = existing_id


class AppliedAtOnSavedJobError(Exception):
    """An applied date was set on a job that is still `saved`."""


@dataclass(frozen=True)
class JobRow:
    job: Job
    last_status_change_at: datetime


def utc_today() -> date:
    return datetime.now(UTC).date()


def _last_change(user_id: uuid.UUID) -> sa.Subquery:
    """Each of the user's jobs with its latest status change."""
    return (
        sa.select(
            StatusHistory.job_id,
            sa.func.max(StatusHistory.changed_at).label("changed_at"),
        )
        .where(StatusHistory.user_id == user_id)
        .group_by(StatusHistory.job_id)
        .subquery()
    )


def _select_rows(user_id: uuid.UUID) -> tuple[sa.Select[Any], sa.ColumnElement[datetime]]:
    last = _last_change(user_id)
    last_at = sa.func.coalesce(last.c.changed_at, Job.created_at)
    query = (
        sa.select(Job, last_at.label("last_status_change_at"))
        .outerjoin(last, last.c.job_id == Job.id)
        .where(Job.user_id == user_id)
        .execution_options(populate_existing=True)  # always the row as it is now
    )
    return query, last_at


def _like_pattern(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def list_jobs(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: StatusFilter = "active",
    search: str | None = None,
    sort: SortField = "created_at",
    order: SortOrder = "desc",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[JobRow], int, dict[JobStatus, int]]:
    """One page of jobs, the number matching in total, and every status's count."""
    query, last_at = _select_rows(user_id)
    if status == "active":
        query = query.where(Job.status.in_(ACTIVE_STATUSES))
    elif status != "all":
        query = query.where(Job.status == status)
    if search:
        pattern = _like_pattern(search)
        query = query.where(
            sa.or_(Job.company.ilike(pattern, escape="\\"), Job.role.ilike(pattern, escape="\\"))
        )

    total = (
        await db.execute(sa.select(sa.func.count()).select_from(query.subquery()))
    ).scalar_one()

    status_rank = sa.case(_STATUS_ORDER, value=Job.status)
    column: sa.SQLColumnExpression[Any] = {
        "company": sa.func.lower(Job.company),
        "role": sa.func.lower(Job.role),
        "status": status_rank,
        "last_status_change": last_at,
        "applied_at": Job.applied_at,
        "created_at": Job.created_at,
    }[sort]
    direction = sa.asc if order == "asc" else sa.desc
    query = (
        query.order_by(direction(column).nulls_last(), direction(Job.id))
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    rows = [JobRow(job, last) for job, last in (await db.execute(query)).tuples()]

    counts = dict.fromkeys(JobStatus, 0)
    by_status = await db.execute(
        sa.select(Job.status, sa.func.count()).where(Job.user_id == user_id).group_by(Job.status)
    )
    counts.update(dict(by_status.tuples().all()))
    return rows, total, counts


async def get_job(db: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> JobRow | None:
    query, _ = _select_rows(user_id)
    row = (await db.execute(query.where(Job.id == job_id))).tuples().one_or_none()
    return JobRow(*row) if row else None


async def _existing_with_url(
    db: AsyncSession, user_id: uuid.UUID, url_canonical: str, *, excluding: uuid.UUID | None
) -> uuid.UUID | None:
    query = sa.select(Job.id).where(Job.user_id == user_id, Job.url_canonical == url_canonical)
    if excluding is not None:
        query = query.where(Job.id != excluding)
    return (await db.execute(query)).scalar_one_or_none()


async def _write_checking_url(db: AsyncSession, job: Job, apply: Callable[[], None]) -> None:
    """Apply changes and flush them in a savepoint, so a concurrent duplicate becomes
    DuplicateJobError instead of failing the request's whole transaction.

    The duplicate check before the write covers the normal case. This catches two
    requests racing past it: the unique index rejects the second. `apply` makes the
    changes *inside* the savepoint, because opening one first flushes anything pending.
    """
    try:
        async with db.begin_nested():
            apply()
            await db.flush()
    except IntegrityError as exc:
        if _URL_UNIQUE_INDEX not in str(exc.orig) or job.url_canonical is None:
            raise
        existing = await _existing_with_url(db, job.user_id, job.url_canonical, excluding=job.id)
        if existing is None:
            raise
        raise DuplicateJobError(existing) from None


async def record_status(db: AsyncSession, job: Job) -> None:
    """Write a status_history row for the job's current status."""
    db.add(StatusHistory(job_id=job.id, user_id=job.user_id, status=job.status))
    await db.flush()


async def create_job(
    db: AsyncSession, user_id: uuid.UUID, fields: Mapping[str, Any], *, today: date
) -> JobRow:
    """Create a job and its initial status history row.

    Raises DuplicateJobError if this user already tracks the same canonical URL.
    """
    job = Job(user_id=user_id, **fields)
    if job.url:
        job.url_canonical = canonicalise_url(job.url)
        if existing := await _existing_with_url(db, user_id, job.url_canonical, excluding=None):
            raise DuplicateJobError(existing)
    if job.status == JobStatus.APPLIED and job.applied_at is None:
        job.applied_at = today

    await _write_checking_url(db, job, lambda: db.add(job))
    await record_status(db, job)
    row = await get_job(db, user_id, job.id)
    assert row is not None
    return row


async def update_job(
    db: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID, changes: Mapping[str, Any]
) -> JobRow | None:
    """Apply a partial update. None if the job isn't this user's (or doesn't exist).

    Raises DuplicateJobError if the new URL is already tracked by another of the user's
    jobs, and AppliedAtOnSavedJobError if an applied date is set on a saved job.
    """
    job = (
        await db.execute(sa.select(Job).where(Job.id == job_id, Job.user_id == user_id))
    ).scalar_one_or_none()
    if job is None:
        return None
    if changes.get("applied_at") is not None and job.status == JobStatus.SAVED:
        raise AppliedAtOnSavedJobError

    changes = dict(changes)
    if "url" in changes:
        url_canonical = canonicalise_url(changes["url"]) if changes["url"] else None
        if url_canonical and (
            existing := await _existing_with_url(db, user_id, url_canonical, excluding=job.id)
        ):
            raise DuplicateJobError(existing)
        changes["url_canonical"] = url_canonical

    def apply() -> None:
        for field, value in changes.items():
            setattr(job, field, value)

    await _write_checking_url(db, job, apply)
    return await get_job(db, user_id, job.id)


async def delete_job(db: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    """Hard delete (history and interviews cascade). False if it isn't this user's job."""
    deleted = await db.execute(
        sa.delete(Job).where(Job.id == job_id, Job.user_id == user_id).returning(Job.id)
    )
    return deleted.scalar_one_or_none() is not None


# --- Company matching (the new-job "already tracked jobs here" warning) ---------------------

# Removed from the end of a name before matching only, so "ACME Limited" matches "Acme".
# Names are always stored and shown exactly as entered.
_LEGAL_SUFFIXES = frozenset(
    {
        "ltd",
        "limited",
        "plc",
        "llp",
        "inc",
        "incorporated",
        "llc",
        "corp",
        "corporation",
        "co",
        "company",
        "gmbh",
    }
)
_NOT_WORD = re.compile(r"[\W_]+")
COMPANY_QUERY_MIN_CHARS = 2


def normalise_company(name: str) -> str:
    """The form used for matching: lowercase words, no punctuation or legal suffix."""
    words = _NOT_WORD.sub(" ", name.lower()).split()
    while len(words) > 1 and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


def company_matches_query(name: str, query: str) -> bool:
    """True if the normalised query starts a word of the normalised name.

    "ac" matches "Acme Ltd" and "Accenture", but not "Pacific".
    """
    return f" {normalise_company(name)}".find(f" {normalise_company(query)}") != -1


async def company_matches(
    db: AsyncSession, user_id: uuid.UUID, query: str
) -> list[tuple[str, dict[JobStatus, int]]]:
    """Each distinct company name (as entered) matching the query, with its jobs by status.

    Names are never merged: "Acme Ltd" and "ACME" are separate entries, so two different
    companies with similar names are never counted together.
    """
    rows = await db.execute(
        sa.select(Job.company, Job.status, sa.func.count())
        .where(Job.user_id == user_id)
        .group_by(Job.company, Job.status)
    )
    matches: dict[str, dict[JobStatus, int]] = defaultdict(dict)
    for company, status, count in rows.tuples():
        if company_matches_query(company, query):
            matches[company][status] = count
    return sorted(matches.items(), key=lambda item: (-sum(item[1].values()), item[0].lower()))
