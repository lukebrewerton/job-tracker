# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""/api/dashboard: counts, the three lists at every day boundary, and upcoming interviews.

The clock is fixed at NOW. Cross-user isolation is in test_isolation.py.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app import timezones
from app.main import create_app
from app.sessions import COOKIE_NAME

from .conftest import PUBLIC_BASE_URL, make_settings
from .isolation import _alices_busy_dashboard, _empty_dashboard

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
LISTS = ("needs_follow_up", "still_to_apply", "no_response_candidates")


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timezones, "now", lambda: NOW)


class Jobs:
    """Creates jobs through the API, then backdates their last status change."""

    def __init__(self, api: TestClient, engine: AsyncEngine, user_id: uuid.UUID) -> None:
        self.api, self.engine, self.user_id = api, engine, user_id

    async def add(
        self,
        status: str,
        *,
        changed: datetime | None = None,
        days_ago: int | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        resp = self.api.post(
            "/api/jobs", json={"company": "Acme", "role": "Engineer", "status": status, **fields}
        )
        assert resp.status_code == 201, resp.text
        job: dict[str, Any] = resp.json()
        if days_ago is not None:
            changed = NOW - timedelta(days=days_ago)
        if changed is not None:
            await self.sql(
                "UPDATE status_history SET changed_at = :t WHERE job_id = :j",
                t=changed,
                j=job["id"],
            )
        return job

    async def sql(self, statement: str, **params: Any) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.user_id', :u, true)"), {"u": str(self.user_id)}
            )
            await conn.execute(text(statement), params)


@pytest.fixture
def jobs(api: TestClient, db_engine: AsyncEngine, user: tuple[uuid.UUID, str]) -> Jobs:
    return Jobs(api, db_engine, user[0])


def _dashboard(api: TestClient) -> dict[str, Any]:
    resp = api.get("/api/dashboard")
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


def _where(api: TestClient, job: dict[str, Any]) -> list[str]:
    """Which lists the job is in."""
    board = _dashboard(api)
    return [name for name in LISTS if job["id"] in [j["id"] for j in board[name]]]


# --- The lists at each day boundary -----------------------------------------------------------


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (6, []),
        (7, ["needs_follow_up"]),
        (13, ["needs_follow_up"]),
        (14, ["no_response_candidates"]),
        (15, ["no_response_candidates"]),
    ],
)
async def test_applied_boundaries(
    api: TestClient, jobs: Jobs, days: int, expected: list[str]
) -> None:
    assert _where(api, await jobs.add("applied", days_ago=days)) == expected


@pytest.mark.parametrize(
    ("days", "expected"),
    [(6, []), (7, ["needs_follow_up"]), (14, ["needs_follow_up"]), (400, ["needs_follow_up"])],
)
async def test_offers_have_no_upper_bound(
    api: TestClient, jobs: Jobs, days: int, expected: list[str]
) -> None:
    assert _where(api, await jobs.add("offer", days_ago=days)) == expected


@pytest.mark.parametrize(
    ("days", "expected"), [(6, []), (7, ["still_to_apply"]), (400, ["still_to_apply"])]
)
async def test_saved_boundaries(
    api: TestClient, jobs: Jobs, days: int, expected: list[str]
) -> None:
    assert _where(api, await jobs.add("saved", days_ago=days)) == expected


@pytest.mark.parametrize(
    "status", ["interviewing", "accepted", "rejected", "withdrawn", "no_response"]
)
async def test_other_statuses_are_in_no_list(api: TestClient, jobs: Jobs, status: str) -> None:
    assert _where(api, await jobs.add(status, days_ago=100)) == []


async def test_days_are_the_users_own_calendar_days(api: TestClient, jobs: Jobs) -> None:
    # 23:30 UTC on 18 September is 00:30 on the 19th in London (BST).
    job = await jobs.add("applied", changed=datetime(2026, 9, 18, 23, 30, tzinfo=UTC))
    assert _where(api, job) == ["needs_follow_up"]  # UTC: 18th → 25th is 7 days
    api.put("/api/me/timezone", json={"timezone": "Europe/London"})
    assert _where(api, job) == []  # London: 19th → 25th is 6 days


async def test_editing_fields_is_not_movement(api: TestClient, jobs: Jobs) -> None:
    job = await jobs.add("applied", days_ago=10)
    api.patch(f"/api/jobs/{job['id']}", json={"notes": "Chased by email"})
    assert _where(api, job) == ["needs_follow_up"]


async def test_a_status_change_is_movement(api: TestClient, jobs: Jobs) -> None:
    job = await jobs.add("applied", days_ago=10)
    api.post(f"/api/jobs/{job['id']}/status", json={"status": "offer"})
    assert _where(api, job) == []


async def test_lists_are_oldest_first_with_their_day_counts(api: TestClient, jobs: Jobs) -> None:
    newer = await jobs.add("applied", days_ago=8, company="Newer")
    older = await jobs.add("applied", days_ago=12, company="Older")
    offer = await jobs.add("offer", days_ago=20, company="Offer")
    items = _dashboard(api)["needs_follow_up"]
    assert [i["id"] for i in items] == [offer["id"], older["id"], newer["id"]]
    assert [i["days_since_last_change"] for i in items] == [20, 12, 8]
    assert items[0] == {
        "id": offer["id"],
        "company": "Offer",
        "role": "Engineer",
        "status": "offer",
        "last_status_change_at": items[0]["last_status_change_at"],
        "days_since_last_change": 20,
    }


# --- Counts -----------------------------------------------------------------------------------


async def test_counts(api: TestClient, jobs: Jobs) -> None:
    for status in ("saved", "saved", "applied", "interviewing", "offer", "accepted"):
        await jobs.add(status)
    await jobs.add("withdrawn", applied_at="2026-09-01")
    await jobs.add("no_response", applied_at="2026-09-01")

    def rejected_via(*path: str) -> None:
        job = api.post(
            "/api/jobs", json={"company": "Acme", "role": "Engineer", "status": "applied"}
        ).json()
        for status in (*path, "rejected"):
            api.post(f"/api/jobs/{job['id']}/status", json={"status": status})

    rejected_via()  # rejected at application
    rejected_via("offer")  # never `interviewing`: at application, as the rule says
    rejected_via("interviewing")  # after interview
    rejected_via("interviewing", "offer")  # after interview

    assert _dashboard(api)["counts"] == {
        "active": 5,  # 2 saved, applied, interviewing, offer
        "saved": 2,
        # Everything but the saved jobs and the ones created straight into
        # interviewing/offer/accepted (no application recorded).
        "applied_ever": 7,
        "interviewing": 1,
        "offer": 1,
        "rejected_at_application": 2,
        "rejected_after_interview": 2,
        "no_response": 1,
        "withdrawn": 1,
        "accepted": 1,
    }


def test_a_new_user_sees_an_empty_dashboard(api: TestClient) -> None:
    board = _dashboard(api)
    assert _empty_dashboard(board)
    assert board["thresholds"] == {"stale_after_days": 7, "no_response_after_days": 14}


# --- Upcoming interviews ----------------------------------------------------------------------


async def test_upcoming_interviews_show_the_next_five(api: TestClient, jobs: Jobs) -> None:
    active = await jobs.add("interviewing")
    closed = await jobs.add("rejected")
    ids = []
    for hours, job in (
        (5, active),
        (1, closed),
        (3, active),
        (7, active),
        (2, active),
        (6, active),
    ):
        resp = api.post(
            f"/api/jobs/{job['id']}/interviews",
            json={"scheduled_at": (NOW + timedelta(hours=hours)).isoformat()},
        )
        ids.append((hours, resp.json()["id"]))
    api.post(
        f"/api/jobs/{active['id']}/interviews",
        json={"scheduled_at": (NOW - timedelta(hours=1)).isoformat()},
    )  # past
    api.post(f"/api/jobs/{active['id']}/interviews", json={})  # unscheduled

    board = _dashboard(api)
    soonest_five = [i for _, i in sorted(ids)[:5]]
    assert [i["id"] for i in board["upcoming_interviews"]] == soonest_five
    assert board["upcoming_interviews_total"] == 6
    assert board["upcoming_interviews"][0]["job"]["status"] == "rejected"  # closed jobs too


# --- Thresholds -------------------------------------------------------------------------------


@pytest.fixture
def custom_api(
    static_dir: Path, test_db_url: str, user: tuple[uuid.UUID, str]
) -> Iterator[TestClient]:
    settings = make_settings(static_dir, test_db_url).model_copy(
        update={"stale_after_days": 3, "no_response_after_days": 5}
    )
    headers = {"cookie": f"{COOKIE_NAME}={user[1]}"}
    with TestClient(create_app(settings), base_url=PUBLIC_BASE_URL, headers=headers) as c:
        yield c


async def test_thresholds_come_from_settings(custom_api: TestClient, jobs: Jobs) -> None:
    jobs.api = custom_api
    follow_up = await jobs.add("applied", days_ago=3)
    no_response = await jobs.add("applied", days_ago=5)
    board = _dashboard(custom_api)
    assert [j["id"] for j in board["needs_follow_up"]] == [follow_up["id"]]
    assert [j["id"] for j in board["no_response_candidates"]] == [no_response["id"]]
    assert board["thresholds"] == {"stale_after_days": 3, "no_response_after_days": 5}


@pytest.mark.parametrize(("stale", "no_response"), [(7, 7), (14, 7), (0, 14)])
def test_invalid_thresholds_are_rejected(static_dir: Path, stale: int, no_response: int) -> None:
    values = make_settings(static_dir).model_dump()
    values |= {"stale_after_days": stale, "no_response_after_days": no_response}
    with pytest.raises(ValidationError):
        type(make_settings(static_dir))(**values, _env_file=None)


# --- The isolation fixture really fills a dashboard -------------------------------------------


async def test_the_isolation_data_fills_every_part_of_its_owners_dashboard(
    api: TestClient, db_engine: AsyncEngine, user: tuple[uuid.UUID, str]
) -> None:
    """Otherwise B's empty dashboard in the isolation test would prove nothing."""
    async with db_engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user[0])})
        await _alices_busy_dashboard(conn, user[0])
    board = _dashboard(api)
    assert all(board[name] for name in LISTS)
    assert board["upcoming_interviews"]
    counts = board["counts"]
    assert counts["rejected_after_interview"] and counts["saved"] and counts["offer"]
