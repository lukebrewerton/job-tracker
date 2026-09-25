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
from importlib.resources import files
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "UTC"
TIMEZONE_MAX = 64


@cache
def valid_timezones() -> frozenset[str]:
    """The IANA zone names, e.g. Europe/London, from the bundled tzdata package.

    Not `zoneinfo.available_timezones()`: that also scans the system's zone directory,
    which varies by host (Ubuntu's includes a `localtime` file, macOS's doesn't), so
    what counted as valid would differ between machines.
    """
    return frozenset(files("tzdata").joinpath("zones").read_text().split())


def is_valid_timezone(name: str) -> bool:
    return name in valid_timezones()


def now() -> datetime:
    """The current time. A function, so tests can move the clock."""
    return datetime.now(UTC)


def today_in(timezone: str) -> date:
    """Today's date in the zone, with daylight saving handled."""
    return now().astimezone(ZoneInfo(timezone)).date()


def date_in(moment: datetime, timezone: str) -> date:
    """The calendar date of an instant, in the zone."""
    return moment.astimezone(ZoneInfo(timezone)).date()
