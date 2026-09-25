# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Each user's time zone, for calendar dates the server decides (what "today" is).

Timestamps need none of this: they're absolute moments, returned with an offset, and
each client shows them in its own zone. Only server-side dates do, e.g. the applied_at
fallback and the dashboard's day boundaries. A deployment can have several users in
different zones, so the zone is stored per user (users.timezone), never per deployment.
"""

from datetime import UTC, date, datetime
from functools import cache
from zoneinfo import ZoneInfo, available_timezones

DEFAULT_TIMEZONE = "UTC"
TIMEZONE_MAX = 64


@cache
def valid_timezones() -> frozenset[str]:
    """The IANA zone names, e.g. Europe/London (not odd-but-loadable ones like localtime)."""
    return frozenset(available_timezones())


def is_valid_timezone(name: str) -> bool:
    return name in valid_timezones()


def now() -> datetime:
    """The current time. A function, so tests can move the clock."""
    return datetime.now(UTC)


def today_in(timezone: str) -> date:
    """Today's date in the zone, with daylight saving handled."""
    return now().astimezone(ZoneInfo(timezone)).date()
