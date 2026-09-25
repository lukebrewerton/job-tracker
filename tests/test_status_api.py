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


def test_creating_a_job_writes_its_initial_history(api: TestClient) -> None:
    assert _history(api, _create(api, status="interviewing")) == ["interviewing"]


def test_each_change_writes_a_history_row(api: TestClient) -> None:
    job = _create(api)
    for status in ("applied", "interviewing", "rejected"):
        assert _status(api, job, status)["status"] == status
    assert _history(api, job) == ["rejected", "interviewing", "applied", "saved"]


def test_history_entries_carry_a_timestamp(api: TestClient) -> None:
    job = _create(api)
    [entry] = api.get(f"/api/jobs/{job['id']}/history").json()
    assert entry["status"] == "saved"
    assert datetime.fromisoformat(entry["changed_at"]).tzinfo is not None


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


def test_a_status_change_is_movement(api: TestClient) -> None:
    job = _create(api)
    moved = _status(api, job, "applied")
    assert moved["last_status_change_at"] > job["last_status_change_at"]


def test_unknown_status_is_a_422(api: TestClient) -> None:
    job = _create(api)
    assert api.post(f"/api/jobs/{job['id']}/status", json={"status": "ghosted"}).status_code == 422


def test_status_change_rejects_other_fields(api: TestClient) -> None:
    job = _create(api)
    resp = api.post(
        f"/api/jobs/{job['id']}/status", json={"status": "applied", "applied_at": "2026-09-01"}
    )
    assert resp.status_code == 422


def test_unknown_job_is_a_404(api: TestClient) -> None:
    missing = uuid.uuid4()
    assert api.post(f"/api/jobs/{missing}/status", json={"status": "applied"}).status_code == 404
    assert api.get(f"/api/jobs/{missing}/history").status_code == 404


# --- applied_at -------------------------------------------------------------------------------


def test_becoming_applied_fills_in_today(api: TestClient, today: date) -> None:
    job = _create(api)
    assert _status(api, job, "applied")["applied_at"] == today.isoformat()


def test_today_is_the_users_own_date(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api.put("/api/me/timezone", json={"timezone": "Europe/London"})
    # 00:30 BST on 26 September: still the 25th in UTC.
    monkeypatch.setattr(timezones, "now", lambda: datetime(2026, 9, 25, 23, 30, tzinfo=UTC))
    assert _status(api, _create(api), "applied")["applied_at"] == "2026-09-26"


def test_an_existing_applied_date_is_never_overwritten(api: TestClient, today: date) -> None:
    job = _create(api, status="applied", applied_at="2026-09-01")
    for status in ("interviewing", "applied", "rejected", "applied"):
        assert _status(api, job, status)["applied_at"] == "2026-09-01"


def test_going_back_to_saved_clears_the_applied_date(api: TestClient, today: date) -> None:
    job = _create(api, status="applied", applied_at="2026-09-01")
    assert _status(api, job, "saved")["applied_at"] is None
    # Applying again later records the new date.
    assert _status(api, job, "applied")["applied_at"] == today.isoformat()


@pytest.mark.parametrize("status", ["interviewing", "offer", "rejected", "withdrawn"])
def test_other_statuses_invent_no_applied_date(api: TestClient, status: str) -> None:
    assert _status(api, _create(api), status)["applied_at"] is None


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


def test_bulk_reports_unchanged_and_not_found(api: TestClient) -> None:
    applied = _create(api, company="A", status="applied")
    already = _create(api, company="B", status="no_response")
    missing = uuid.uuid4()
    result = _bulk(api, [applied["id"], already["id"], missing], "no_response")
    assert result == {
        "updated": [applied["id"]],
        "unchanged": [already["id"]],
        "not_found": [str(missing)],
    }
    assert _history(api, already) == ["no_response"]


def test_bulk_counts_duplicate_ids_once(api: TestClient) -> None:
    job = _create(api, status="applied")
    result = _bulk(api, [job["id"], job["id"]], "no_response")
    assert result["updated"] == [job["id"]]
    assert _history(api, job) == ["no_response", "applied"]


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
