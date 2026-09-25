# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Interviews: CRUD under a job, and the three groups in /api/interviews.

Cross-user isolation is in test_isolation.py. The job-and-interview rule is also tested
here within one user: your own interview under your own *other* job is a 404, which
row-level security alone wouldn't catch.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app import interviews, timezones
from app.db import set_session_user

from .isolation import new_user

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timezones, "now", lambda: NOW)


def _job(api: TestClient, company: str = "Acme", **fields: Any) -> dict[str, Any]:
    resp = api.post("/api/jobs", json={"company": company, "role": "Engineer", **fields})
    assert resp.status_code == 201, resp.text
    job: dict[str, Any] = resp.json()
    return job


def _interview(api: TestClient, job: dict[str, Any], **fields: Any) -> dict[str, Any]:
    resp = api.post(f"/api/jobs/{job['id']}/interviews", json=fields)
    assert resp.status_code == 201, resp.text
    interview: dict[str, Any] = resp.json()
    return interview


def _at(delta: timedelta) -> str:
    return (NOW + delta).isoformat()


# --- CRUD -------------------------------------------------------------------------------------


def test_every_field_is_optional(api: TestClient) -> None:
    interview = _interview(api, _job(api))
    assert interview["scheduled_at"] is None
    assert interview["mode"] is None
    assert interview["round_label"] is None
    assert interview["notes"] is None


def test_create_with_every_field(api: TestClient) -> None:
    job = _job(api)
    interview = _interview(
        api,
        job,
        scheduled_at="2026-10-02T14:00:00+01:00",
        mode="in_person",
        round_label="  Technical  ",
        notes="Bring the laptop",
    )
    assert interview["job_id"] == job["id"]
    assert datetime.fromisoformat(interview["scheduled_at"]) == datetime(
        2026, 10, 2, 13, tzinfo=UTC
    )
    assert interview["mode"] == "in_person"
    assert interview["round_label"] == "Technical"


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"scheduled_at": "2026-10-02T14:00:00"}, "scheduled_at"),  # no offset
        ({"scheduled_at": "next Tuesday"}, "scheduled_at"),
        ({"mode": "carrier_pigeon"}, "mode"),
        ({"round_label": "x" * 321}, "round_label"),
        ({"notes": "x" * 10_001}, "notes"),
        ({"outcome": "passed"}, "outcome"),
    ],
)
def test_create_validation(api: TestClient, fields: dict[str, Any], field: str) -> None:
    resp = api.post(f"/api/jobs/{_job(api)['id']}/interviews", json=fields)
    assert resp.status_code == 422
    assert field in [str(e["loc"][-1]) for e in resp.json()["detail"]]


def test_blank_text_is_stored_as_null(api: TestClient) -> None:
    assert _interview(api, _job(api), round_label="   ", notes="")["round_label"] is None


def test_adding_an_interview_does_not_change_the_job_status(api: TestClient) -> None:
    job = _job(api, status="applied")
    _interview(api, job)
    assert api.get(f"/api/jobs/{job['id']}").json()["status"] == "applied"


def test_list_for_a_job_puts_scheduled_first_by_date(api: TestClient) -> None:
    job = _job(api)
    unscheduled = _interview(api, job, round_label="Unscheduled")
    later = _interview(api, job, round_label="Later", scheduled_at=_at(timedelta(days=5)))
    sooner = _interview(api, job, round_label="Sooner", scheduled_at=_at(timedelta(days=2)))
    past = _interview(api, job, round_label="Past", scheduled_at=_at(-timedelta(days=2)))
    listed = api.get(f"/api/jobs/{job['id']}/interviews").json()
    assert [i["id"] for i in listed] == [past["id"], sooner["id"], later["id"], unscheduled["id"]]


def test_list_only_includes_that_jobs_interviews(api: TestClient) -> None:
    mine = _interview(api, _job(api, "Acme"))
    _interview(api, _job(api, "Globex"))
    assert [i["id"] for i in api.get(f"/api/jobs/{mine['job_id']}/interviews").json()] == [
        mine["id"]
    ]


def test_get_patch_delete(api: TestClient) -> None:
    job = _job(api)
    interview = _interview(api, job, mode="phone", notes="First call")
    url = f"/api/jobs/{job['id']}/interviews/{interview['id']}"
    assert api.get(url).json() == interview

    updated = api.patch(url, json={"mode": "remote", "scheduled_at": _at(timedelta(days=1))})
    assert updated.status_code == 200
    assert updated.json()["mode"] == "remote"
    assert updated.json()["notes"] == "First call"  # untouched

    assert api.patch(url, json={"notes": None, "mode": None}).json()["notes"] is None
    assert api.delete(url).status_code == 204
    assert api.get(url).status_code == 404


def test_unknown_job_or_interview_is_a_404(api: TestClient) -> None:
    job = _job(api)
    missing = uuid.uuid4()
    assert api.get(f"/api/jobs/{missing}/interviews").status_code == 404
    assert api.post(f"/api/jobs/{missing}/interviews", json={}).status_code == 404
    for method in ("GET", "PATCH", "DELETE"):
        resp = api.request(method, f"/api/jobs/{job['id']}/interviews/{missing}", json={})
        assert resp.status_code == 404, method


def test_an_interview_is_only_reachable_through_its_own_job(api: TestClient) -> None:
    interview = _interview(api, _job(api, "Acme"))
    other_job = _job(api, "Globex")
    url = f"/api/jobs/{other_job['id']}/interviews/{interview['id']}"
    for method in ("GET", "PATCH", "DELETE"):
        assert api.request(method, url, json={"notes": "x"}).status_code == 404, method
    # Still there, unchanged, under its real job.
    real = api.get(f"/api/jobs/{interview['job_id']}/interviews/{interview['id']}").json()
    assert real == interview


def test_deleting_a_job_deletes_its_interviews(api: TestClient) -> None:
    job = _job(api)
    _interview(api, job, scheduled_at=_at(timedelta(days=1)))
    api.delete(f"/api/jobs/{job['id']}")
    assert api.get("/api/interviews").json()["upcoming"] == []


async def test_the_database_rejects_an_interview_on_another_users_job(
    db_engine: AsyncEngine,
) -> None:
    """Belt and braces: the composite foreign key, even if the app got it wrong."""
    alice, _ = await new_user(db_engine)
    bob, _ = await new_user(db_engine)
    async with db_engine.connect() as conn:
        outer = await conn.begin()
        db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        try:
            await set_session_user(db, alice)
            job_id = (
                await db.execute(
                    text(
                        "INSERT INTO jobs (user_id, company, role) "
                        "VALUES (:u, 'Acme', 'Eng') RETURNING id"
                    ),
                    {"u": alice},
                )
            ).scalar_one()
            # As B, row-level security allows a row with B's user_id; only the composite
            # foreign key can reject it, because (A's job, B) matches no job.
            await set_session_user(db, bob)
            with pytest.raises(IntegrityError, match="fk_interviews_job_id_user_id_jobs"):
                async with db.begin_nested():
                    await db.execute(
                        text("INSERT INTO interviews (job_id, user_id) VALUES (:j, :u)"),
                        {"j": job_id, "u": bob},
                    )
        finally:
            await db.close()
            await outer.rollback()


# --- /api/interviews groups -------------------------------------------------------------------


def _ids(items: list[dict[str, Any]]) -> list[str]:
    return [i["id"] for i in items]


def test_grouping(api: TestClient) -> None:
    active = _job(api, "Acme", status="interviewing")
    closed = _job(api, "Globex", status="rejected")

    soon = _interview(api, active, scheduled_at=_at(timedelta(hours=2)))
    later = _interview(api, active, scheduled_at=_at(timedelta(days=3)))
    closed_upcoming = _interview(api, closed, scheduled_at=_at(timedelta(days=1)))
    exactly_now = _interview(api, active, scheduled_at=NOW.isoformat())
    earlier_today = _interview(api, active, scheduled_at=_at(-timedelta(hours=1)))
    last_week = _interview(api, closed, scheduled_at=_at(-timedelta(days=7)))
    unscheduled_first = _interview(api, active, round_label="first")
    unscheduled_second = _interview(api, active, round_label="second")
    _interview(api, closed)  # unscheduled on a closed job: in no group

    groups = api.get("/api/interviews").json()
    assert _ids(groups["upcoming"]) == [
        exactly_now["id"],
        soon["id"],
        closed_upcoming["id"],
        later["id"],
    ]
    assert _ids(groups["not_yet_scheduled"]) == [unscheduled_first["id"], unscheduled_second["id"]]
    assert _ids(groups["past"]) == [earlier_today["id"], last_week["id"]]


def test_group_items_carry_their_job(api: TestClient) -> None:
    job = _job(api, "Acme", role="Platform Engineer", status="interviewing")
    _interview(api, job, scheduled_at=_at(timedelta(days=1)), mode="remote")
    [item] = api.get("/api/interviews").json()["upcoming"]
    assert item["job"] == {
        "id": job["id"],
        "company": "Acme",
        "role": "Platform Engineer",
        "status": "interviewing",
    }
    assert item["mode"] == "remote"


def test_no_interviews_means_empty_groups(api: TestClient) -> None:
    assert api.get("/api/interviews").json() == {
        "upcoming": [],
        "not_yet_scheduled": [],
        "past": [],
    }


# --- The explicit user filter, independent of row-level security ------------------------------


async def test_data_layer_filters_by_user_even_where_rls_would_allow(
    db_engine: AsyncEngine,
) -> None:
    alice, _ = await new_user(db_engine)
    bob, _ = await new_user(db_engine)
    async with db_engine.connect() as conn:
        outer = await conn.begin()
        db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        try:
            await set_session_user(db, alice)  # RLS would show A's rows...
            job_id = (
                await db.execute(
                    text(
                        "INSERT INTO jobs (user_id, company, role, status) "
                        "VALUES (:u, 'Acme', 'Eng', 'interviewing') RETURNING id"
                    ),
                    {"u": alice},
                )
            ).scalar_one()
            made = await interviews.create(db, alice, job_id, {"scheduled_at": NOW})
            assert made is not None
            interview_id = made.id

            # ...but every function asked for B finds nothing of A's.
            assert await interviews.list_for_job(db, bob, job_id) is None
            assert await interviews.create(db, bob, job_id, {}) is None
            assert await interviews.get(db, bob, job_id, interview_id) is None
            assert await interviews.update(db, bob, job_id, interview_id, {"notes": "B"}) is None
            assert await interviews.delete(db, bob, job_id, interview_id) is False
            groups = await interviews.grouped(db, bob, now=NOW - timedelta(days=1))
            assert (groups.upcoming, groups.not_yet_scheduled, groups.past) == ([], [], [])

            still = await interviews.get(db, alice, job_id, interview_id)
            assert still is not None and still.notes is None
        finally:
            await db.close()
            await outer.rollback()
