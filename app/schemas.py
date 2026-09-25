# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""API request and response models.

Length limits match the database CHECK constraints (app/models.py), so a bad value is a
friendly 422 here rather than a database error. Text is trimmed; an empty optional field
is stored as null. Unknown fields are rejected, so a typo is an error, not a no-op.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.models import (
    NAME_MAX,
    NOTES_MAX,
    SHORT_TEXT_MAX,
    URL_MAX,
    InterviewMode,
    JobSource,
    JobStatus,
)
from app.timezones import TIMEZONE_MAX, is_valid_timezone
from app.urls import canonicalise_url

SAVED_WITH_APPLIED_AT = "A saved job can't have an applied date: it hasn't been applied for yet"


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip() or None
    return value


def _not_null(value: Any) -> Any:
    if value is None:
        raise PydanticCustomError("missing_value", "This field can't be empty")
    return value


def _valid_url(value: Any) -> Any:
    if isinstance(value, str):
        try:
            canonicalise_url(value)
        except ValueError as exc:
            raise PydanticCustomError("url", str(exc)) from None
    return value


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX)]
ShortText = Annotated[
    Annotated[str, StringConstraints(max_length=SHORT_TEXT_MAX)] | None,
    BeforeValidator(_blank_to_none),
]
Notes = Annotated[
    Annotated[str, StringConstraints(max_length=NOTES_MAX)] | None,
    BeforeValidator(_blank_to_none),
]
Url = Annotated[
    Annotated[str, StringConstraints(max_length=URL_MAX)] | None,
    BeforeValidator(_valid_url),
    BeforeValidator(_blank_to_none),  # runs first: trimmed, and "" becomes null
]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobCreate(_Input):
    company: Name
    role: Name
    url: Url = None
    location: ShortText = None
    source: JobSource | None = None
    salary: ShortText = None
    contact_name: ShortText = None
    contact_email: ShortText = None
    status: JobStatus = JobStatus.SAVED
    # Filled in with today's date when created as `applied` without one.
    applied_at: date | None = None
    notes: Notes = None

    @model_validator(mode="after")
    def _saved_has_no_applied_at(self) -> Self:
        if self.status == JobStatus.SAVED and self.applied_at is not None:
            raise PydanticCustomError("saved_with_applied_at", SAVED_WITH_APPLIED_AT)
        return self


class JobUpdate(_Input):
    """A partial update: only the fields sent change, and null clears an optional field.

    Status changes aren't made here (JT-26), so `status` is rejected as an unknown field.
    """

    company: Annotated[Name | None, BeforeValidator(_not_null)] = None
    role: Annotated[Name | None, BeforeValidator(_not_null)] = None
    url: Url = None
    location: ShortText = None
    source: JobSource | None = None
    salary: ShortText = None
    contact_name: ShortText = None
    contact_email: ShortText = None
    applied_at: date | None = None
    notes: Notes = None


class JobOut(BaseModel):
    id: uuid.UUID
    company: str
    role: str
    url: str | None
    location: str | None
    source: JobSource | None
    salary: str | None
    contact_name: str | None
    contact_email: str | None
    status: JobStatus
    applied_at: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    # When the status last changed (the latest status_history entry).
    last_status_change_at: datetime
    # Whole calendar days since then, in the user's time zone.
    days_since_last_change: int
    # The dashboard list this job is in, if any (the same rule as the dashboard).
    attention: Literal["needs_follow_up", "still_to_apply", "no_response"] | None


class JobPage(BaseModel):
    items: list[JobOut]
    # Jobs matching the filter and search, across all pages.
    total: int
    page: int
    page_size: int
    # Every status's count across all of the user's jobs, ignoring the filter and search.
    counts: dict[JobStatus, int]


class StatusChange(_Input):
    status: JobStatus


BULK_STATUS_MAX = 500


class BulkStatusChange(_Input):
    ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=BULK_STATUS_MAX)]
    status: JobStatus


class BulkStatusResult(BaseModel):
    updated: list[uuid.UUID]
    # Already had the status: nothing written.
    unchanged: list[uuid.UUID]
    # Not your job, or doesn't exist: never touched, and indistinguishable.
    not_found: list[uuid.UUID]


class HistoryEntry(BaseModel):
    status: JobStatus
    changed_at: datetime


class DuplicateJob(BaseModel):
    detail: str = "Already tracked"
    existing_id: uuid.UUID


class CompanyMatch(BaseModel):
    name: str  # exactly as entered
    total: int
    by_status: dict[JobStatus, int]  # non-zero statuses only


class CompanyMatches(BaseModel):
    companies: list[CompanyMatch]


# --- The current user -------------------------------------------------------------------------


def _valid_timezone(value: Any) -> Any:
    if isinstance(value, str) and not is_valid_timezone(value):
        raise PydanticCustomError(
            "timezone", "Unknown time zone: use an IANA name such as Europe/London"
        )
    return value


class Me(BaseModel):
    email: str
    timezone: str


class TimezoneUpdate(_Input):
    timezone: Annotated[
        str, StringConstraints(max_length=TIMEZONE_MAX), AfterValidator(_valid_timezone)
    ]


class TimezoneOut(BaseModel):
    timezone: str


# --- Interviews -------------------------------------------------------------------------------


class InterviewCreate(_Input):
    # Must include an offset (e.g. +01:00): without one, when it is can't be known.
    scheduled_at: AwareDatetime | None = None
    mode: InterviewMode | None = None
    round_label: ShortText = None  # free text; the UI offers presets plus "Other…"
    notes: Notes = None


class InterviewUpdate(InterviewCreate):
    """A partial update: only the fields sent change, and null clears a field."""


class InterviewOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    scheduled_at: datetime | None
    mode: InterviewMode | None
    round_label: str | None
    notes: str | None
    created_at: datetime


class JobSummary(BaseModel):
    id: uuid.UUID
    company: str
    role: str
    status: JobStatus


class InterviewWithJob(InterviewOut):
    job: JobSummary


class InterviewGroups(BaseModel):
    upcoming: list[InterviewWithJob]  # soonest first
    not_yet_scheduled: list[InterviewWithJob]  # active jobs only, oldest first
    past: list[InterviewWithJob]  # most recent first


# --- Dashboard --------------------------------------------------------------------------------


class DashboardCounts(BaseModel):
    active: int  # saved + applied + interviewing + offer
    saved: int
    applied_ever: int  # jobs with an applied date, whatever their status now
    interviewing: int
    offer: int
    rejected_at_application: int
    rejected_after_interview: int  # the job was `interviewing` at some point
    no_response: int
    withdrawn: int
    accepted: int


class StaleJobOut(BaseModel):
    id: uuid.UUID
    company: str
    role: str
    status: JobStatus
    last_status_change_at: datetime
    # Whole calendar days in the user's time zone.
    days_since_last_change: int


class DashboardThresholds(BaseModel):
    stale_after_days: int
    no_response_after_days: int


class DashboardOut(BaseModel):
    counts: DashboardCounts
    # Each list is oldest first, and a job is in at most one of them.
    needs_follow_up: list[StaleJobOut]
    still_to_apply: list[StaleJobOut]
    no_response_candidates: list[StaleJobOut]
    upcoming_interviews: list[InterviewWithJob]  # the next few, soonest first
    upcoming_interviews_total: int
    thresholds: DashboardThresholds
