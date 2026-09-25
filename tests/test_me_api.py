# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""/api/me and per-user time zones: "today" is the user's own calendar day.

Cross-user isolation is in test_isolation.py.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app import timezones
from app.main import create_app
from app.sessions import COOKIE_NAME, CurrentUser

from .conftest import ALLOWED_EMAIL, PUBLIC_BASE_URL, make_settings
from .isolation import new_user


@pytest.fixture
async def user(db_engine: AsyncEngine) -> tuple[uuid.UUID, str]:
    return await new_user(db_engine, with_session=True, email=ALLOWED_EMAIL)


@pytest.fixture
def api(static_dir: Path, test_db_url: str, user: tuple[uuid.UUID, str]) -> Iterator[TestClient]:
    app = create_app(make_settings(static_dir, test_db_url))
    headers = {"cookie": f"{COOKIE_NAME}={user[1]}"}
    with TestClient(app, base_url=PUBLIC_BASE_URL, headers=headers) as c:
        yield c


def _at(monkeypatch: pytest.MonkeyPatch, moment: str) -> None:
    """Move the clock to an instant, given in UTC."""
    instant = datetime.fromisoformat(moment).replace(tzinfo=UTC)
    monkeypatch.setattr(timezones, "now", lambda: instant)


# --- /api/me ----------------------------------------------------------------------------------


def test_new_users_default_to_utc(api: TestClient) -> None:
    assert api.get("/api/me").json() == {"email": ALLOWED_EMAIL, "timezone": "UTC"}


def test_set_timezone(api: TestClient) -> None:
    resp = api.put("/api/me/timezone", json={"timezone": "Europe/London"})
    assert resp.status_code == 200
    assert resp.json() == {"timezone": "Europe/London"}
    assert api.get("/api/me").json()["timezone"] == "Europe/London"


@pytest.mark.parametrize(
    "timezone",
    [
        "Mars/Olympus_Mons",
        "europe/london",  # zone names are case-sensitive
        "localtime",  # loadable on some systems, but not an IANA zone name
        "../../etc/passwd",
        "",
        "Europe/" + "x" * 64,
    ],
)
def test_unknown_timezones_are_a_422(api: TestClient, timezone: str) -> None:
    resp = api.put("/api/me/timezone", json={"timezone": timezone})
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"][-1] == "timezone"
    assert api.get("/api/me").json()["timezone"] == "UTC"


def test_timezone_update_rejects_unknown_fields(api: TestClient) -> None:
    resp = api.put("/api/me/timezone", json={"timezone": "Europe/London", "email": "x@y.test"})
    assert resp.status_code == 422


# --- "Today" in the user's zone ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("moment_utc", "timezone", "today"),
    [
        # 00:30 BST on 26 September is still 25 September in UTC.
        ("2026-09-25T23:30", "Europe/London", "2026-09-26"),
        ("2026-09-25T23:30", "UTC", "2026-09-25"),
        # After the clocks go back (25 October), London is on GMT: the same day as UTC.
        ("2026-10-25T23:30", "Europe/London", "2026-10-25"),
        ("2026-10-26T00:30", "Europe/London", "2026-10-26"),
        # West of UTC, the day ends later.
        ("2026-09-26T02:00", "America/New_York", "2026-09-25"),
    ],
)
def test_created_as_applied_gets_the_users_own_date(
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    moment_utc: str,
    timezone: str,
    today: str,
) -> None:
    api.put("/api/me/timezone", json={"timezone": timezone})
    _at(monkeypatch, moment_utc)
    job: dict[str, Any] = api.post(
        "/api/jobs", json={"company": "Acme", "role": "Eng", "status": "applied"}
    ).json()
    assert job["applied_at"] == today


def test_a_date_sent_by_the_client_is_kept_as_is(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    api.put("/api/me/timezone", json={"timezone": "Europe/London"})
    _at(monkeypatch, "2026-09-25T23:30")
    job = api.post(
        "/api/jobs",
        json={"company": "Acme", "role": "Eng", "status": "applied", "applied_at": "2026-09-20"},
    ).json()
    assert job["applied_at"] == "2026-09-20"


def test_current_user_today(monkeypatch: pytest.MonkeyPatch) -> None:
    _at(monkeypatch, "2026-09-25T23:30")
    london = CurrentUser(id=uuid.uuid4(), email="a@example.test", timezone="Europe/London")
    assert london.today() == date(2026, 9, 26)
    assert CurrentUser(id=uuid.uuid4(), email="b@example.test").today() == date(2026, 9, 25)


def test_valid_timezones_are_the_iana_names() -> None:
    assert timezones.is_valid_timezone("Europe/London")
    assert timezones.is_valid_timezone("UTC")
    assert not timezones.is_valid_timezone("localtime")
