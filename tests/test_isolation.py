# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every /api route: requires a session, and never exposes another user's data.

The real app's routes are enumerated automatically (nested routers included). The
harness is also exercised against test-only probe routes, to prove it catches an
unprotected route, a leaking route, and a route with no isolation case.
"""

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.api import api_router
from app.main import create_app
from app.sessions import UserDbSession, current_user

from .conftest import PUBLIC_BASE_URL, make_settings
from .isolation import (
    CASES,
    EMPTY,
    NOT_FOUND,
    IsolationCase,
    api_routes,
    openapi_routes,
    register,
    run_case,
)

# --- The real app ---------------------------------------------------------------------------


@pytest.fixture
def app(static_dir: Path, test_db_url: str) -> FastAPI:
    return create_app(make_settings(static_dir, test_db_url))


def test_every_api_route_has_an_isolation_case(app: FastAPI) -> None:
    missing = api_routes(app) - CASES.keys()
    assert not missing, f"/api routes with no isolation case in tests/isolation.py: {missing}"


def test_no_isolation_case_for_a_route_that_does_not_exist(app: FastAPI) -> None:
    stale = CASES.keys() - api_routes(app)
    assert not stale, f"Isolation cases for routes that don't exist: {stale}"


def test_route_walk_agrees_with_openapi(app: FastAPI) -> None:
    # Guards the walker itself: if FastAPI's routing internals change and it starts
    # missing nested routes, this disagreement shows up here.
    assert api_routes(app) == openapi_routes(app)


def _fill(path: str) -> str:
    return path.format_map({k: str(uuid.uuid4()) for k in _placeholders(path)})


def _placeholders(path: str) -> list[str]:
    return [part[1:-1].split(":")[0] for part in path.split("/") if part.startswith("{")]


_REAL_API_ROUTES = sorted(api_routes(create_app(make_settings(Path("/")))))


@pytest.mark.parametrize(
    "method_path",
    _REAL_API_ROUTES or [pytest.param(None, marks=pytest.mark.skip("no /api routes yet"))],
)
def test_every_api_route_requires_a_session(
    app: FastAPI, method_path: tuple[str, str] | None
) -> None:
    assert method_path is not None
    method, path = method_path
    with TestClient(app, base_url=PUBLIC_BASE_URL) as c:
        body: dict[str, object] | None = {} if method in {"POST", "PUT", "PATCH"} else None
        resp = c.request(method, _fill(path), json=body)
    assert resp.status_code == 401, f"{method} {path}: {resp.status_code} without a session"


@pytest.mark.parametrize(
    "case",
    list(CASES.values()) or [pytest.param(None, marks=pytest.mark.skip("no /api routes yet"))],
    ids=lambda c: f"{c.method} {c.path}" if c else "none",
)
async def test_other_users_data_is_never_exposed(
    app: FastAPI, db_engine: AsyncEngine, case: IsolationCase | None
) -> None:
    assert case is not None
    with TestClient(app, base_url=PUBLIC_BASE_URL) as c:
        await run_case(c, db_engine, case)


# --- The harness itself, against probe routes ----------------------------------------------


def _probe_router(*, leaky: bool = False) -> APIRouter:
    # Same protection as the real api_router: its dependencies (the session check).
    router = APIRouter(prefix="/api/_probe", dependencies=api_router.dependencies)

    @router.get("/jobs/{job_id}")
    async def get_job(job_id: uuid.UUID, db: UserDbSession) -> dict[str, Any]:
        if leaky:  # a bug: answers without checking ownership
            return {"id": str(job_id)}
        row = (
            await db.execute(text("SELECT id, company FROM jobs WHERE id = :j"), {"j": job_id})
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=404)
        return {"id": str(row.id), "company": row.company}

    @router.get("/jobs")
    async def list_jobs(db: UserDbSession) -> list[dict[str, Any]]:
        rows = (await db.execute(text("SELECT id, company FROM jobs"))).all()
        return [{"id": str(r.id), "company": r.company} for r in rows]

    return router


def _app_with(static_dir: Path, test_db_url: str, router: APIRouter) -> FastAPI:
    app = create_app(make_settings(static_dir, test_db_url))
    app.include_router(router)
    # include_router appends after the SPA catch-all; move the probe routes ahead of it.
    app.router.routes.insert(0, app.router.routes.pop())
    return app


async def _alices_job(conn: AsyncConnection, alice: uuid.UUID) -> dict[str, Any]:
    job_id = (
        await conn.execute(
            text(
                "INSERT INTO jobs (user_id, company, role) VALUES (:u, 'Acme', 'Eng') RETURNING id"
            ),
            {"u": alice},
        )
    ).scalar_one()
    return {"job_id": job_id}


def _probe_cases() -> dict[tuple[str, str], IsolationCase]:
    cases: dict[tuple[str, str], IsolationCase] = {}
    register(IsolationCase("GET", "/api/_probe/jobs/{job_id}", _alices_job, NOT_FOUND), cases)
    register(IsolationCase("GET", "/api/_probe/jobs", _alices_job, EMPTY), cases)
    return cases


@pytest.fixture
def probe_client(static_dir: Path, test_db_url: str) -> Iterator[TestClient]:
    app = _app_with(static_dir, test_db_url, _probe_router())
    with TestClient(app, base_url=PUBLIC_BASE_URL) as c:
        yield c


def test_route_walk_sees_routes_on_included_routers(static_dir: Path, test_db_url: str) -> None:
    app = _app_with(static_dir, test_db_url, _probe_router())
    assert {("GET", "/api/_probe/jobs/{job_id}"), ("GET", "/api/_probe/jobs")} <= api_routes(app)
    assert api_routes(app) == openapi_routes(app)


def test_harness_flags_a_route_without_a_case(static_dir: Path, test_db_url: str) -> None:
    app = _app_with(static_dir, test_db_url, _probe_router())
    cases = _probe_cases()
    del cases[("GET", "/api/_probe/jobs")]
    probe_routes = {r for r in api_routes(app) if r[1].startswith("/api/_probe/")}
    assert probe_routes - cases.keys() == {("GET", "/api/_probe/jobs")}


def test_routes_on_the_api_router_require_a_session(probe_client: TestClient) -> None:
    resp = probe_client.get(f"/api/_probe/jobs/{uuid.uuid4()}")
    assert resp.status_code == 401


def test_api_router_itself_requires_a_session() -> None:
    assert any(dep.dependency is current_user for dep in api_router.dependencies)


def test_even_a_route_with_no_dependencies_of_its_own_is_protected(
    static_dir: Path, test_db_url: str
) -> None:
    # A careless route that takes no session/db parameter at all must still be gated by
    # the router, not by its own signature.
    router = APIRouter(prefix="/api/_probe", dependencies=api_router.dependencies)

    @router.get("/careless")
    async def careless() -> dict[str, str]:
        return {"secret": "should never be served without a session"}

    app = _app_with(static_dir, test_db_url, router)
    with TestClient(app, base_url=PUBLIC_BASE_URL) as c:
        assert c.get("/api/_probe/careless").status_code == 401


@pytest.mark.parametrize("key", list(_probe_cases()))
async def test_harness_passes_an_isolated_route(
    probe_client: TestClient, db_engine: AsyncEngine, key: tuple[str, str]
) -> None:
    await run_case(probe_client, db_engine, _probe_cases()[key])


async def test_harness_catches_a_leaking_route(
    static_dir: Path, test_db_url: str, db_engine: AsyncEngine
) -> None:
    app = _app_with(static_dir, test_db_url, _probe_router(leaky=True))
    case = _probe_cases()[("GET", "/api/_probe/jobs/{job_id}")]
    with (
        TestClient(app, base_url=PUBLIC_BASE_URL) as c,
        pytest.raises(AssertionError, match="expected 404, got 200"),
    ):
        await run_case(c, db_engine, case)
