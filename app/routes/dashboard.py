# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""/api/dashboard: everything the dashboard shows, in one call."""

from dataclasses import asdict

from fastapi import APIRouter, Request

from app import dashboard
from app.config import Settings
from app.routes.interviews import interview_with_job
from app.schemas import (
    DashboardCounts,
    DashboardOut,
    DashboardThresholds,
    StaleJobOut,
)
from app.sessions import CurrentUserDep, UserDbSession

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _stale(item: dashboard.StaleJob) -> StaleJobOut:
    job = item.job
    return StaleJobOut(
        id=job.id,
        company=job.company,
        role=job.role,
        status=job.status,
        last_status_change_at=item.last_status_change_at,
        days_since_last_change=item.days_since_last_change,
    )


@router.get("")
async def get_dashboard(request: Request, user: CurrentUserDep, db: UserDbSession) -> DashboardOut:
    """Tile counts, the three "needs attention" lists and the next interviews.

    Days are whole calendar days in your time zone; only status changes count as
    movement. The thresholds used are returned too, for the UI's wording.
    """
    settings: Settings = request.app.state.settings
    data = await dashboard.build(
        db,
        user.id,
        timezone=user.timezone,
        stale_after_days=settings.stale_after_days,
        no_response_after_days=settings.no_response_after_days,
    )
    return DashboardOut(
        counts=DashboardCounts(**asdict(data.counts)),
        needs_follow_up=[_stale(j) for j in data.needs_follow_up],
        still_to_apply=[_stale(j) for j in data.still_to_apply],
        no_response_candidates=[_stale(j) for j in data.no_response_candidates],
        upcoming_interviews=[interview_with_job(i, j) for i, j in data.upcoming_interviews],
        upcoming_interviews_total=data.upcoming_interviews_total,
        thresholds=DashboardThresholds(
            stale_after_days=settings.stale_after_days,
            no_response_after_days=settings.no_response_after_days,
        ),
    )
