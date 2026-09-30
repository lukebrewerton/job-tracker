# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Status changes, history and bulk updates: every rule in the status design.

Cross-user isolation is in test_isolation.py; the explicit user filter (independent of
row-level security) is in test_jobs_api.py.
"""

import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app import jobs, timezones
from app.db import set_session_user
from app.models import JobStatus

JOB = {"company": "Acme Ltd", "role": "Platform Engineer"}


def _create(api: TestClient, **fields: Any) -> dict[str, Any]:
    resp = api.post("/api/jobs", json={**JOB, **fields})
    assert resp.status_code == 201, resp.text
    job: dict[str, Any] = resp.json()
    return job


def _status(api: TestClient, job: dict[str, Any], status: str) -> dict[str, Any]:
    resp = api.post(f"/api/jobs/{job['id']}/status", json={"status": status})
    assert resp.status_code == 200, resp.text
    updated: dict[str, Any] = resp.json()
    return updated


def _history(api: TestClient, job: dict[str, Any]) -> list[str]:
    """Statuses in the job's history, newest first."""
    resp = api.get(f"/api/jobs/{job['id']}/history")
    assert resp.status_code == 200, resp.text
    return [entry["status"] for entry in resp.json()]


@pytest.fixture
def today(monkeypatch: pytest.MonkeyPatch) -> date:
    """Pin the clock: noon UTC on 25 September 2026 (the same date in UTC and London)."""
    monkeypatch.setattr(timezones, "now", lambda: datetime(2026, 9, 25, 12, tzinfo=UTC))
    return date(2026, 9, 25)


# --- Single status changes --------------------------------------------------------------------


def test_creation_and_each_change_write_a_timestamped_history_row(api: TestClient) -> None:
    # Created as interviewing, not the default: the first row records the status given.
    job = _create(api, status="interviewing")
    [entry] = api.get(f"/api/jobs/{job['id']}/history").json()
    assert entry["status"] == "interviewing"
    assert datetime.fromisoformat(entry["changed_at"]).tzinfo is not None
    before = job
    for status in ("applied", "offer", "rejected"):
        moved = _status(api, job, status)
        assert moved["status"] == status
        # A status change is movement.
        assert moved["last_status_change_at"] > before["last_status_change_at"]
        before = moved
    assert _history(api, job) == ["rejected", "offer", "applied", "interviewing"]


def test_setting_the_same_status_writes_nothing(api: TestClient) -> None:
    job = _create(api, status="applied")
    unchanged = _status(api, job, "applied")
    assert unchanged["last_status_change_at"] == job["last_status_change_at"]
    assert _history(api, job) == ["applied"]


@pytest.mark.parametrize("start", list(JobStatus))
@pytest.mark.parametrize("end", list(JobStatus))
def test_any_status_can_move_to_any_other(
    api: TestClient, start: JobStatus, end: JobStatus
) -> None:
    job = _create(api, status=start.value)
    assert _status(api, job, end.value)["status"] == end.value


@pytest.mark.parametrize(
    "body",
    [
        {"status": "ghosted"},
        # Only the status: the applied date follows from it.
        {"status": "applied", "applied_at": "2026-09-01"},
    ],
)
def test_invalid_status_change_is_a_422(api: TestClient, body: dict[str, Any]) -> None:
    job = _create(api)
    assert api.post(f"/api/jobs/{job['id']}/status", json=body).status_code == 422


def test_unknown_job_is_a_404(api: TestClient) -> None:
    missing = uuid.uuid4()
    assert api.post(f"/api/jobs/{missing}/status", json={"status": "applied"}).status_code == 404
    assert api.get(f"/api/jobs/{missing}/history").status_code == 404


# --- applied_at -------------------------------------------------------------------------------


def test_today_is_the_users_own_date(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api.put("/api/me/timezone", json={"timezone": "Europe/London"})
    # 00:30 BST on 26 September: still the 25th in UTC.
    monkeypatch.setattr(timezones, "now", lambda: datetime(2026, 9, 25, 23, 30, tzinfo=UTC))
    assert _status(api, _create(api), "applied")["applied_at"] == "2026-09-26"


def test_status_changes_follow_the_applied_date_rules(api: TestClient, today: date) -> None:
    # The rule itself is tabled in test_applied_at_for; this proves the endpoint uses it.
    job = _create(api)
    for status in ("interviewing", "offer", "rejected", "withdrawn"):
        assert _status(api, job, status)["applied_at"] is None  # no date invented
    assert _status(api, job, "applied")["applied_at"] == today.isoformat()  # filled in

    job = _create(api, status="applied", applied_at="2026-09-01")
    for status in ("interviewing", "applied", "rejected", "applied"):
        assert _status(api, job, status)["applied_at"] == "2026-09-01"  # never overwritten
    assert _status(api, job, "saved")["applied_at"] is None  # back to saved clears it
    assert _status(api, job, "applied")["applied_at"] == today.isoformat()  # applying again


def test_applied_at_for() -> None:
    today = date(2026, 9, 25)
    earlier = date(2026, 9, 1)
    assert jobs.applied_at_for(JobStatus.APPLIED, None, today=today) == today
    assert jobs.applied_at_for(JobStatus.APPLIED, earlier, today=today) == earlier
    assert jobs.applied_at_for(JobStatus.SAVED, earlier, today=today) is None
    assert jobs.applied_at_for(JobStatus.OFFER, earlier, today=today) == earlier
    assert jobs.applied_at_for(JobStatus.INTERVIEWING, None, today=today) is None


# --- Bulk -------------------------------------------------------------------------------------


def _bulk(api: TestClient, ids: list[Any], status: str) -> dict[str, list[str]]:
    resp = api.post("/api/jobs/bulk-status", json={"ids": [str(i) for i in ids], "status": status})
    assert resp.status_code == 200, resp.text
    result: dict[str, list[str]] = resp.json()
    return result


def test_bulk_updates_each_job_with_one_history_row_each(api: TestClient) -> None:
    a = _create(api, company="A", status="applied")
    b = _create(api, company="B", status="applied")
    result = _bulk(api, [a["id"], b["id"]], "no_response")
    assert result == {"updated": [a["id"], b["id"]], "unchanged": [], "not_found": []}
    for job in (a, b):
        assert _history(api, job) == ["no_response", "applied"]
        assert api.get(f"/api/jobs/{job['id']}").json()["status"] == "no_response"


def test_bulk_reports_unchanged_and_not_found_and_counts_duplicates_once(
    api: TestClient,
) -> None:
    applied = _create(api, company="A", status="applied")
    already = _create(api, company="B", status="no_response")
    missing = uuid.uuid4()
    ids = [applied["id"], applied["id"], already["id"], missing]
    result = _bulk(api, ids, "no_response")
    assert result == {
        "updated": [applied["id"]],
        "unchanged": [already["id"]],
        "not_found": [str(missing)],
    }
    assert _history(api, applied) == ["no_response", "applied"]  # one row, not two
    assert _history(api, already) == ["no_response"]


def test_bulk_applies_the_applied_at_rules(api: TestClient, today: date) -> None:
    saved = _create(api, company="A")
    applied = _create(api, company="B", status="applied", applied_at="2026-09-01")
    _bulk(api, [saved["id"], applied["id"]], "applied")
    assert api.get(f"/api/jobs/{saved['id']}").json()["applied_at"] == today.isoformat()
    assert api.get(f"/api/jobs/{applied['id']}").json()["applied_at"] == "2026-09-01"


@pytest.mark.parametrize(
    "body",
    [
        {"ids": [], "status": "no_response"},
        {"ids": [str(uuid.uuid4()) for _ in range(501)], "status": "no_response"},
        {"ids": ["not-a-uuid"], "status": "no_response"},
        {"ids": [str(uuid.uuid4())], "status": "ghosted"},
        {"ids": [str(uuid.uuid4())]},
    ],
)
def test_bulk_validation(api: TestClient, body: dict[str, Any]) -> None:
    assert api.post("/api/jobs/bulk-status", json=body).status_code == 422


def test_bulk_accepts_500_ids(api: TestClient) -> None:
    ids = [str(uuid.uuid4()) for _ in range(500)]
    assert len(_bulk(api, ids, "no_response")["not_found"]) == 500


# --- Concurrency ------------------------------------------------------------------------------


async def test_concurrent_changes_to_one_job_record_one_change(
    db_engine: AsyncEngine, user: tuple[uuid.UUID, str]
) -> None:
    """Two simultaneous "mark as applied" requests: one change, one history row.

    Without the row lock, both would see `saved` and both would record the change.
    """
    user_id = user[0]
    async with AsyncSession(db_engine) as db, db.begin():
        await set_session_user(db, user_id)
        created = await jobs.create_job(db, user_id, JOB, today=date(2026, 9, 25))
        job_id = created.job.id

    async def mark_applied() -> None:
        async with AsyncSession(db_engine) as db, db.begin():
            await set_session_user(db, user_id)
            await jobs.change_status(db, user_id, job_id, JobStatus.APPLIED, today=date.today())
            await asyncio.sleep(0.2)  # hold the transaction open while the other runs

    await asyncio.gather(mark_applied(), mark_applied())

    async with AsyncSession(db_engine) as db, db.begin():
        await set_session_user(db, user_id)
        history = await jobs.status_history(db, user_id, job_id)
        assert history is not None
        assert [h.status for h in history] == [JobStatus.APPLIED, JobStatus.SAVED]
