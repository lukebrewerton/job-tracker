# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""/api/me: the signed-in user, and their time zone.

The frontend reads the browser's zone on load and, if it differs from the stored one,
saves it here: there is no setting to manage. Only ever touches the current user's row.
"""

import sqlalchemy as sa
from fastapi import APIRouter

from app.models import User
from app.schemas import Me, TimezoneOut, TimezoneUpdate
from app.sessions import CurrentUserDep, UserDbSession

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def get_me(user: CurrentUserDep) -> Me:
    return Me(email=user.email, timezone=user.timezone)


@router.put("/timezone")
async def set_timezone(
    user: CurrentUserDep, db: UserDbSession, body: TimezoneUpdate
) -> TimezoneOut:
    """Store your IANA time zone (e.g. Europe/London), used for server-side dates."""
    await db.execute(sa.update(User).where(User.id == user.id).values(timezone=body.timezone))
    return TimezoneOut(timezone=body.timezone)
