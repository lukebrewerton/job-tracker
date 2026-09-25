# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""/api/jobs: create, read, update, delete, list (filter, search, sort, paging),
duplicates, and company matching. Cross-user isolation is in test_isolation.py."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app import jobs, timezones
from app.db import set_session_user
from app.models import JobStatus
from app.schemas import SAVED_WITH_APPLIED_AT

from .isolation import new_user

JOB = {"company": "Acme Ltd", "role": "Platform Engineer"}


async def _sql(engine: AsyncEngine, user_id: uuid.UUID, sql: str, **params: Any) -> None:
    """Run SQL as the user (row-level security scoped to them)."""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_id)})
        await conn.execute(text(sql), params)


def _create(api: TestClient, **fields: Any) -> dict[str, Any]:
    resp = api.post("/api/jobs", json={**JOB, **fields})
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


def _errors(resp: Any) -> list[tuple[str, str]]:
    """(field, message) for each validation error in a 422."""
    assert resp.status_code == 422, resp.text
    return [(str(e["loc"][-1]), e["msg"]) for e in resp.json()["detail"]]


# --- Create -----------------------------------------------------------------------------------


def test_create_defaults_to_saved_with_history(api: TestClient) -> None:
    job = _create(api)
    assert job["status"] == "saved"
    assert job["applied_at"] is None
    assert job["last_status_change_at"] is not None
    assert "user_id" not in job
    assert "url_canonical" not in job


def test_create_trims_text_and_stores_blank_optionals_as_null(api: TestClient) -> None:
    job = _create(api, company="  Acme  ", role=" Eng ", location="   ", notes="", salary=" £70k ")
    assert (job["company"], job["role"]) == ("Acme", "Eng")
    assert job["location"] is None
    assert job["notes"] is None
    assert job["salary"] == "£70k"


def test_create_as_applied_fills_in_today(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(timezones, "now", lambda: datetime(2026, 9, 25, 12, 0, tzinfo=UTC))
    assert _create(api, status="applied")["applied_at"] == "2026-09-25"


def test_create_as_applied_keeps_the_date_sent(api: TestClient) -> None:
    assert _create(api, status="applied", applied_at="2026-09-20")["applied_at"] == "2026-09-20"


def test_create_with_another_status_invents_no_applied_date(api: TestClient) -> None:
    assert _create(api, status="interviewing")["applied_at"] is None


def test_saved_job_cannot_have_an_applied_date(api: TestClient) -> None:
    resp = api.post("/api/jobs", json={**JOB, "applied_at": "2026-09-20"})
    assert any(SAVED_WITH_APPLIED_AT in msg for _, msg in _errors(resp))


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"company": "   "}, "company"),
        ({"role": ""}, "role"),
        ({"company": "x" * 201}, "company"),
        ({"notes": "x" * 10_001}, "notes"),
        ({"contact_email": "x" * 321}, "contact_email"),
        ({"url": "javascript:alert(1)"}, "url"),
        ({"url": "careers.acme.test/jobs/1"}, "url"),
        ({"url": "https://acme.test/" + "x" * 2048}, "url"),
        ({"source": "myspace"}, "source"),
        ({"status": "ghosted"}, "status"),
        ({"surprise": 1}, "surprise"),
    ],
)
def test_create_validation(api: TestClient, fields: dict[str, Any], field: str) -> None:
    resp = api.post("/api/jobs", json={**JOB, **fields})
    assert field in [f for f, _ in _errors(resp)]


def test_contact_email_is_free_text(api: TestClient) -> None:
    assert _create(api, contact_email="Sam at Acme (via LinkedIn)")["contact_email"]


# --- Duplicates -------------------------------------------------------------------------------


def test_same_canonical_url_is_a_409_with_the_existing_id(api: TestClient) -> None:
    first = _create(api, url="https://careers.acme.test/jobs/42")
    resp = api.post(
        "/api/jobs", json={**JOB, "url": "HTTPS://Careers.Acme.test/jobs/42/?utm_source=x#apply"}
    )
    assert resp.status_code == 409
    assert resp.json() == {"detail": "Already tracked", "existing_id": first["id"]}


def test_jobs_without_a_url_are_never_duplicates(api: TestClient) -> None:
    _create(api)
    _create(api)


def test_different_urls_are_not_duplicates(api: TestClient) -> None:
    _create(api, url="https://uk.indeed.com/viewjob?jk=aaa")
    _create(api, url="https://uk.indeed.com/viewjob?jk=bbb")


def test_patching_to_a_tracked_url_is_a_409(api: TestClient) -> None:
    first = _create(api, url="https://acme.test/jobs/1")
    second = _create(api, url="https://acme.test/jobs/2")
    resp = api.patch(f"/api/jobs/{second['id']}", json={"url": "https://acme.test/jobs/1/"})
    assert resp.status_code == 409
    assert resp.json()["existing_id"] == first["id"]


def test_patching_a_job_to_its_own_url_is_fine(api: TestClient) -> None:
    job = _create(api, url="https://acme.test/jobs/1")
    resp = api.patch(f"/api/jobs/{job['id']}", json={"url": "https://acme.test/jobs/1?utm_x=1"})
    assert resp.status_code == 200


async def test_a_racing_duplicate_is_still_a_409(
    api: TestClient, db_engine: AsyncEngine, user: tuple[uuid.UUID, str]
) -> None:
    # Simulate losing the race: the pre-check sees nothing, the unique index catches it.
    first = _create(api, url="https://acme.test/jobs/1")
    original = jobs._existing_with_url
    calls = 0

    async def miss_once(*args: Any, **kwargs: Any) -> uuid.UUID | None:
        nonlocal calls
        calls += 1
        return None if calls == 1 else await original(*args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(jobs, "_existing_with_url", miss_once)
        resp = api.post("/api/jobs", json={**JOB, "url": "https://acme.test/jobs/1"})
    assert resp.status_code == 409
    assert resp.json()["existing_id"] == first["id"]


# --- Read, update, delete ---------------------------------------------------------------------


def test_get_returns_the_job(api: TestClient) -> None:
    job = _create(api, location="London")
    assert api.get(f"/api/jobs/{job['id']}").json() == job


def test_unknown_job_is_a_404(api: TestClient) -> None:
    for method in ("GET", "PATCH", "DELETE"):
        resp = api.request(method, f"/api/jobs/{uuid.uuid4()}", json={"notes": "x"})
        assert resp.status_code == 404, method


def test_patch_changes_only_the_fields_sent(api: TestClient) -> None:
    job = _create(api, location="London", salary="£70k")
    updated = api.patch(f"/api/jobs/{job['id']}", json={"location": "Remote"}).json()
    assert updated["location"] == "Remote"
    assert updated["salary"] == "£70k"
    assert updated["updated_at"] >= job["updated_at"]


def test_patch_null_clears_an_optional_field(api: TestClient) -> None:
    job = _create(api, location="London")
    assert api.patch(f"/api/jobs/{job['id']}", json={"location": None}).json()["location"] is None


@pytest.mark.parametrize("field", ["company", "role"])
def test_patch_cannot_clear_a_required_field(api: TestClient, field: str) -> None:
    job = _create(api)
    assert field in [f for f, _ in _errors(api.patch(f"/api/jobs/{job['id']}", json={field: None}))]


def test_patch_does_not_change_status(api: TestClient) -> None:
    job = _create(api)
    resp = api.patch(f"/api/jobs/{job['id']}", json={"status": "applied"})
    assert "status" in [f for f, _ in _errors(resp)]


def test_patch_cannot_give_a_saved_job_an_applied_date(api: TestClient) -> None:
    job = _create(api)
    resp = api.patch(f"/api/jobs/{job['id']}", json={"applied_at": "2026-09-20"})
    assert _errors(resp) == [("applied_at", SAVED_WITH_APPLIED_AT)]


def test_patch_can_edit_the_applied_date_of_an_applied_job(api: TestClient) -> None:
    job = _create(api, status="applied", applied_at="2026-09-20")
    resp = api.patch(f"/api/jobs/{job['id']}", json={"applied_at": "2026-09-18"})
    assert resp.json()["applied_at"] == "2026-09-18"


def test_patch_editing_fields_does_not_count_as_movement(api: TestClient) -> None:
    job = _create(api)
    updated = api.patch(f"/api/jobs/{job['id']}", json={"notes": "Chased"}).json()
    assert updated["last_status_change_at"] == job["last_status_change_at"]


async def test_delete_removes_the_job_and_its_history(
    api: TestClient, db_engine: AsyncEngine, user: tuple[uuid.UUID, str]
) -> None:
    job = _create(api)
    assert api.delete(f"/api/jobs/{job['id']}").status_code == 204
    assert api.get(f"/api/jobs/{job['id']}").status_code == 404
    async with db_engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user[0])})
        left = await conn.execute(
            text("SELECT count(*) FROM status_history WHERE job_id = :j"), {"j": job["id"]}
        )
        assert left.scalar_one() == 0


# --- List: filters, search, counts ------------------------------------------------------------


def _companies(page: dict[str, Any]) -> list[str]:
    return [job["company"] for job in page["items"]]


@pytest.fixture
def mixed(api: TestClient) -> None:
    for status in ("saved", "applied", "interviewing", "offer", "accepted", "rejected"):
        _create(api, company=status.title(), status=status)
    _create(api, company="Withdrawn", status="withdrawn")
    _create(api, company="NoResponse", status="no_response")


@pytest.mark.usefixtures("mixed")
def test_list_defaults_to_active(api: TestClient) -> None:
    page = api.get("/api/jobs").json()
    assert sorted(_companies(page)) == ["Applied", "Interviewing", "Offer", "Saved"]
    assert page["total"] == 4


@pytest.mark.usefixtures("mixed")
def test_list_all_and_single_status(api: TestClient) -> None:
    assert api.get("/api/jobs", params={"status": "all"}).json()["total"] == 8
    rejected = api.get("/api/jobs", params={"status": "rejected"}).json()
    assert _companies(rejected) == ["Rejected"]


@pytest.mark.usefixtures("mixed")
def test_counts_cover_every_status_and_ignore_filter_and_search(api: TestClient) -> None:
    page = api.get("/api/jobs", params={"status": "offer", "q": "offer"}).json()
    assert page["total"] == 1
    assert page["counts"] == {
        "saved": 1,
        "applied": 1,
        "interviewing": 1,
        "offer": 1,
        "accepted": 1,
        "rejected": 1,
        "withdrawn": 1,
        "no_response": 1,
    }


def test_list_rejects_an_unknown_filter(api: TestClient) -> None:
    assert api.get("/api/jobs", params={"status": "closed"}).status_code == 422


def test_search_matches_company_or_role_case_insensitively(api: TestClient) -> None:
    _create(api, company="Acme", role="Engineer")
    _create(api, company="Globex", role="Platform ENGINEER")
    _create(api, company="Initech", role="Manager")
    assert sorted(_companies(api.get("/api/jobs", params={"q": "engineer"}).json())) == [
        "Acme",
        "Globex",
    ]
    assert _companies(api.get("/api/jobs", params={"q": "  initech "}).json()) == ["Initech"]


def test_search_treats_like_wildcards_literally(api: TestClient) -> None:
    _create(api, company="100% Remote Ltd")
    _create(api, company="Acme")
    assert _companies(api.get("/api/jobs", params={"q": "0%"}).json()) == ["100% Remote Ltd"]
    assert _companies(api.get("/api/jobs", params={"q": "a_"}).json()) == []


@pytest.mark.parametrize("q", ["a", " a ", "é"])
def test_search_needs_at_least_2_characters(api: TestClient, q: str) -> None:
    assert _errors(api.get("/api/jobs", params={"q": q})) == [("q", "Enter at least 2 characters")]


@pytest.mark.parametrize("q", ["", "   "])
def test_blank_search_means_no_search(api: TestClient, q: str) -> None:
    _create(api)
    assert api.get("/api/jobs", params={"q": q}).json()["total"] == 1


# --- List: sort and paging --------------------------------------------------------------------


async def test_sorting(
    api: TestClient, db_engine: AsyncEngine, user: tuple[uuid.UUID, str]
) -> None:
    a = _create(api, company="acme", role="Zed", status="applied", applied_at="2026-09-10")
    b = _create(api, company="Beta", role="Ann", status="offer", applied_at="2026-09-01")
    c = _create(api, company="Cyan", role="mid", status="saved")
    # Created c, b, a (oldest first); last status change b, a, c.
    for job, created, changed in ((a, "03", "02"), (b, "02", "01"), (c, "01", "03")):
        await _sql(
            db_engine,
            user[0],
            "UPDATE jobs SET created_at = CAST(:t AS timestamptz) WHERE id = :j",
            t=f"2026-09-{created} 12:00+00",
            j=job["id"],
        )
        await _sql(
            db_engine,
            user[0],
            "UPDATE status_history SET changed_at = CAST(:t AS timestamptz) WHERE job_id = :j",
            t=f"2026-09-{changed} 12:00+00",
            j=job["id"],
        )

    def order(sort: str, direction: str = "asc") -> list[str]:
        params = {"status": "all", "sort": sort, "order": direction}
        return _companies(api.get("/api/jobs", params=params).json())

    assert order("company") == ["acme", "Beta", "Cyan"]  # case-insensitive
    assert order("role") == ["Beta", "Cyan", "acme"]  # Ann, mid, Zed
    assert order("status") == ["Cyan", "acme", "Beta"]  # lifecycle: saved, applied, offer
    assert order("last_status_change") == ["Beta", "acme", "Cyan"]
    assert order("created_at") == ["Cyan", "Beta", "acme"]
    assert order("created_at", "desc") == ["acme", "Beta", "Cyan"]
    # No applied date sorts last in both directions.
    assert order("applied_at") == ["Beta", "acme", "Cyan"]
    assert order("applied_at", "desc") == ["acme", "Beta", "Cyan"]
    # Default: newest first.
    assert _companies(api.get("/api/jobs", params={"status": "all"}).json()) == [
        "acme",
        "Beta",
        "Cyan",
    ]


def test_paging(api: TestClient) -> None:
    for n in range(30):
        _create(api, company=f"Company {n:02}")
    params: dict[str, Any] = {"sort": "company", "order": "asc", "page_size": 25}
    first = api.get("/api/jobs", params=params).json()
    second = api.get("/api/jobs", params={**params, "page": 2}).json()
    assert (first["total"], first["page"], first["page_size"]) == (30, 1, 25)
    assert len(first["items"]) == 25
    assert _companies(second) == [f"Company {n:02}" for n in range(25, 30)]
    beyond = api.get("/api/jobs", params={**params, "page": 3}).json()
    assert (beyond["items"], beyond["total"]) == ([], 30)


@pytest.mark.parametrize("size", [25, 50, 100])
def test_page_sizes(api: TestClient, size: int) -> None:
    assert api.get("/api/jobs", params={"page_size": size}).json()["page_size"] == size


@pytest.mark.parametrize("params", [{"page_size": 10}, {"page_size": 200}, {"page": 0}])
def test_invalid_paging_is_a_422(api: TestClient, params: dict[str, Any]) -> None:
    assert api.get("/api/jobs", params=params).status_code == 422


def test_default_page_size_is_25(api: TestClient) -> None:
    assert api.get("/api/jobs").json()["page_size"] == 25


async def test_last_status_change_is_the_latest_history_entry(
    api: TestClient, db_engine: AsyncEngine, user: tuple[uuid.UUID, str]
) -> None:
    job = _create(api)
    await _sql(
        db_engine,
        user[0],
        "INSERT INTO status_history (job_id, user_id, status, changed_at) "
        "VALUES (:j, :u, 'saved', '2030-01-01 09:00+00')",
        j=job["id"],
        u=user[0],
    )
    got = api.get(f"/api/jobs/{job['id']}").json()["last_status_change_at"]
    assert got.startswith("2030-01-01T09:00:00")


# --- Company matches --------------------------------------------------------------------------


def _matches(api: TestClient, company: str) -> list[dict[str, Any]]:
    resp = api.get("/api/jobs/company-matches", params={"company": company})
    assert resp.status_code == 200, resp.text
    companies: list[dict[str, Any]] = resp.json()["companies"]
    return companies


def test_company_matches_keep_names_as_entered_and_never_merge(api: TestClient) -> None:
    _create(api, company="Acme Ltd", status="applied")
    _create(api, company="Acme Ltd", status="no_response")
    _create(api, company="ACME")
    _create(api, company="Globex")
    assert _matches(api, "acme limited") == [
        {"name": "Acme Ltd", "total": 2, "by_status": {"applied": 1, "no_response": 1}},
        {"name": "ACME", "total": 1, "by_status": {"saved": 1}},
    ]


def test_company_matches_on_the_start_of_a_word(api: TestClient) -> None:
    for company in ("Acme", "Accenture", "Pacific", "The Acorn Group"):
        _create(api, company=company)
    assert sorted(m["name"] for m in _matches(api, "ac")) == [
        "Accenture",
        "Acme",
        "The Acorn Group",
    ]


@pytest.mark.parametrize("company", ["a", " a ", "a.", "a Ltd"])
def test_company_matches_need_at_least_2_characters(api: TestClient, company: str) -> None:
    resp = api.get("/api/jobs/company-matches", params={"company": company})
    assert _errors(resp) == [("company", "Enter at least 2 characters")]


def test_no_company_matches_is_an_empty_list(api: TestClient) -> None:
    _create(api, company="Acme")
    assert _matches(api, "Globex") == []


@pytest.mark.parametrize(
    ("name", "normalised"),
    [
        ("Acme", "acme"),
        ("ACME Limited", "acme"),
        ("Acme, Inc.", "acme"),
        ("Acme Holdings Ltd.", "acme holdings"),
        ("Smith & Co", "smith"),
        ("Company", "company"),  # a lone suffix word is kept
        ("Deutsche Bahn GmbH", "deutsche bahn"),
        ("  O'Reilly   Media  ", "o reilly media"),
        ("Café Ltd", "café"),
    ],
)
def test_normalise_company(name: str, normalised: str) -> None:
    assert jobs.normalise_company(name) == normalised


@pytest.mark.parametrize(
    ("name", "query", "matches"),
    [
        ("Acme Ltd", "ACME", True),
        ("ACME", "Acme Limited", True),
        ("Accenture", "ac", True),
        ("Pacific", "ac", False),
        ("Deep Labs", "labs", True),
        ("DeepLabs", "labs", False),
        ("Deep Labs", "deep la", True),
        ("Acme", "acmex", False),
    ],
)
def test_company_matches_query(name: str, query: str, matches: bool) -> None:
    assert jobs.company_matches_query(name, query) is matches


# --- The explicit user filter, independent of row-level security ------------------------------


async def test_data_layer_filters_by_user_even_where_rls_would_allow(
    db_engine: AsyncEngine,
) -> None:
    """Row-level security is set to A, but the functions are asked for B: nothing of A's.

    Proves the explicit user filter works on its own, so RLS is a backstop, not the only
    line of defence.
    """
    alice, _ = await new_user(db_engine)
    bob, _ = await new_user(db_engine)
    async with db_engine.connect() as conn:
        outer = await conn.begin()
        db = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
        try:
            await set_session_user(db, alice)
            created = await jobs.create_job(
                db, alice, {**JOB, "url": "https://acme.test/jobs/1"}, today=date(2026, 9, 25)
            )
            job_id = created.job.id

            assert await jobs.get_job(db, bob, job_id) is None
            assert await jobs.update_job(db, bob, job_id, {"notes": "B"}) is None
            assert await jobs.delete_job(db, bob, job_id) is False
            rows, total, counts = await jobs.list_jobs(db, bob, status="all")
            assert (rows, total, sum(counts.values())) == ([], 0, 0)
            assert await jobs.company_matches(db, bob, "acme") == []
            assert await jobs.status_history(db, bob, job_id) is None
            closed = JobStatus.REJECTED
            assert await jobs.change_status(db, bob, job_id, closed, today=date.today()) is None
            bulk = await jobs.bulk_change_status(db, bob, [job_id], closed, today=date.today())
            assert (bulk.updated, bulk.not_found) == ([], [job_id])
            # A's URL is not a duplicate for B.
            url = "https://acme.test/jobs/1"
            assert await jobs._existing_with_url(db, bob, url, excluding=None) is None

            still = await jobs.get_job(db, alice, job_id)
            assert still is not None and still.job.notes is None
            assert still.job.status == JobStatus.SAVED
            history = await jobs.status_history(db, alice, job_id)
            assert history is not None and len(history) == 1
        finally:
            await db.close()
            await outer.rollback()
