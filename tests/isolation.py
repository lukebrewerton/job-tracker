# Copyright (C) 2026 Luke Brewerton
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross-user isolation harness.

Every /api route must have an `IsolationCase` registered in `CASES`: how to create user
A's data, and what user B must get back when they aim the route at it (404 for a single
item — never 403, which would confirm it exists — an empty result for lists and
aggregates, or a custom check). Whatever B gets, A's rows must be unchanged afterwards.
`test_isolation.py` fails the build if any /api route has no case.

Adding an API route? Register its case here in the same PR:

    register(IsolationCase("GET", "/api/jobs/{job_id}", arrange=_alices_job, expect=NOT_FOUND))
"""

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.sessions import COOKIE_NAME

from .conftest import ALLOWED_EMAIL

NOT_FOUND: Literal["not_found"] = "not_found"
EMPTY: Literal["empty"] = "empty"
CUSTOM: Literal["custom"] = "custom"

# User A's data, read as A, to prove B's request changed none of it.
_OWNED_TABLES = ("jobs", "status_history", "interviews")

# Framework-provided documentation routes (development only), not data routes.
DOC_PATHS = frozenset({"/api/openapi.json", "/api/docs", "/api/docs/oauth2-redirect"})

# Creates user A's data, with row-level security scoped to A; returns path params.
Arrange = Callable[[AsyncConnection, uuid.UUID], Awaitable[dict[str, Any]]]
# For CUSTOM: asserts on B's response, given the path params arrange returned.
Check = Callable[[Any, dict[str, Any]], None]


@dataclass(frozen=True)
class IsolationCase:
    method: str
    path: str  # the route template, e.g. "/api/jobs/{job_id}"
    arrange: Arrange
    expect: Literal["not_found", "empty", "custom"]
    # A dict, or a function of the params (A's from `arrange`, B's from `arrange_bob`).
    body: dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]] | None = None
    query: dict[str, str] | None = None
    # For EMPTY: how to tell a response holds none of A's data.
    is_empty: Callable[[Any], bool] = lambda payload: payload in ([], {}, None)
    check: Check | None = None
    # Creates B's own data (row-level security scoped to B), e.g. to mix B's IDs in.
    arrange_bob: Arrange | None = None
    # Which IDs go in the URL, from the params; by default the params themselves.
    path_params: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    # Names an extra scenario for a route that already has its main case.
    variant: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.method, self.path)


CASES: dict[tuple[str, str], IsolationCase] = {}
# More scenarios for routes that already have their main case in CASES.
EXTRA_CASES: list[IsolationCase] = []


def register(case: IsolationCase, registry: dict[tuple[str, str], IsolationCase] = CASES) -> None:
    if case.key in registry:
        raise ValueError(f"Duplicate isolation case for {case.key}")
    registry[case.key] = case


def register_extra(case: IsolationCase) -> None:
    if not case.variant:
        raise ValueError(f"An extra case for {case.key} needs a variant name")
    EXTRA_CASES.append(case)


def api_routes(app: FastAPI) -> set[tuple[str, str]]:
    """Every (method, path) under /api, including routes on included (nested) routers."""
    routes: set[tuple[str, str]] = set()
    for route in iter_route_contexts(app.routes):
        path, methods = route.path, route.methods
        if not path or not methods or not path.startswith("/api/") or path in DOC_PATHS:
            continue
        routes |= {(m, path) for m in methods - {"HEAD", "OPTIONS"}}
    return routes


def openapi_routes(app: FastAPI) -> set[tuple[str, str]]:
    """The same set according to the OpenAPI schema: an independent cross-check."""
    return {
        (method.upper(), path)
        for path, operations in app.openapi().get("paths", {}).items()
        if path.startswith("/api/")
        for method in operations
    }


async def new_user(
    engine: AsyncEngine, *, with_session: bool = False, email: str | None = None
) -> tuple[uuid.UUID, str]:
    """A user (and optionally a session); returns (user_id, raw session token or "")."""
    token = f"isolation-{uuid.uuid4()}" if with_session else ""
    async with engine.begin() as conn:
        user_id: uuid.UUID = (
            await conn.execute(
                text("INSERT INTO users (oidc_sub, email) VALUES (:s, :e) RETURNING id"),
                {"s": f"sub-{uuid.uuid4()}", "e": email or f"{uuid.uuid4().hex[:10]}@example.test"},
            )
        ).scalar_one()
        if with_session:
            await conn.execute(
                text("INSERT INTO sessions (user_id, token_hash) VALUES (:u, :h)"),
                {"u": user_id, "h": hashlib.sha256(token.encode()).hexdigest()},
            )
    return user_id, token


async def _snapshot(engine: AsyncEngine, user_id: uuid.UUID) -> dict[str, list[Any]]:
    """The user's own `users` row, and every row they own, read as that user."""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_id)})
        snapshot = {
            table: list(
                (await conn.execute(text(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id")))
                .scalars()
                .all()
            )
            for table in _OWNED_TABLES
        }
        # Not under row-level security, so selected by id.
        user_row = await conn.execute(
            text("SELECT to_jsonb(u) FROM users u WHERE id = :u"), {"u": user_id}
        )
        snapshot["users"] = list(user_row.scalars().all())
        return snapshot


async def run_case(client: TestClient, engine: AsyncEngine, case: IsolationCase) -> None:
    """Create A's data, then aim the route at it as B: B learns nothing, A's data is intact."""
    alice, _ = await new_user(engine)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(alice)})
        params = await case.arrange(conn, alice)
    before = await _snapshot(engine, alice)
    # B must be a genuinely signed-in, allowed user: otherwise the allow-list check turns
    # every request into a 401, and cases would "pass" without testing isolation at all.
    bob, bob_token = await new_user(engine, with_session=True, email=ALLOWED_EMAIL)
    if case.arrange_bob is not None:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(bob)})
            params |= await case.arrange_bob(conn, bob)

    body = case.body(params) if callable(case.body) else case.body
    resp = client.request(
        case.method,
        case.path.format(**(case.path_params(params) if case.path_params else params)),
        headers={"cookie": f"{COOKIE_NAME}={bob_token}"},
        params=case.query,
        json=body if case.method in {"POST", "PUT", "PATCH"} else None,
    )
    where = f"{case.method} {case.path}" + (f" ({case.variant})" if case.variant else "")
    assert resp.status_code != 401, f"{where}: B's session was rejected; isolation untested"
    if case.expect == NOT_FOUND:
        assert resp.status_code == 404, f"{where}: expected 404, got {resp.status_code}"
    elif case.expect == EMPTY:
        assert resp.status_code == 200, f"{where}: expected 200, got {resp.status_code}"
        assert case.is_empty(resp.json()), f"{where}: leaked {resp.json()!r}"
    else:
        assert case.check is not None, f"{where}: a CUSTOM case needs a check"
        case.check(resp, params)
    assert await _snapshot(engine, alice) == before, f"{where}: changed A's data"


# --- Cases: /api/jobs (JT-25) -------------------------------------------------------------

ALICES_URL = "https://careers.acme.test/jobs/42?utm_source=linkedin"


async def _alices_job(conn: AsyncConnection, alice: uuid.UUID) -> dict[str, Any]:
    """One job of A's at Acme, with its initial history row."""
    job_id = (
        await conn.execute(
            text(
                "INSERT INTO jobs (user_id, company, role, url, url_canonical, status) "
                "VALUES (:u, 'Acme Ltd', 'Platform Engineer', :url, :canonical, 'applied') "
                "RETURNING id"
            ),
            {"u": alice, "url": ALICES_URL, "canonical": "https://careers.acme.test/jobs/42"},
        )
    ).scalar_one()
    await conn.execute(
        text("INSERT INTO status_history (job_id, user_id, status) VALUES (:j, :u, 'applied')"),
        {"j": job_id, "u": alice},
    )
    return {"job_id": job_id}


def _no_jobs_listed(page: Any) -> bool:
    return page["items"] == [] and page["total"] == 0 and not any(page["counts"].values())


def _created_as_bobs_own(resp: Any, params: dict[str, Any]) -> None:
    # A's URL is not a duplicate for B: B's job is created, and it is a new job.
    assert resp.status_code == 201, f"expected 201, got {resp.status_code}: {resp.text}"
    assert resp.json()["id"] != str(params["job_id"])


for _case in (
    IsolationCase(
        "GET", "/api/jobs", _alices_job, EMPTY, query={"status": "all"}, is_empty=_no_jobs_listed
    ),
    IsolationCase(
        "GET",
        "/api/jobs/company-matches",
        _alices_job,
        EMPTY,
        query={"company": "Acme"},
        is_empty=lambda payload: payload == {"companies": []},
    ),
    IsolationCase("GET", "/api/jobs/{job_id}", _alices_job, NOT_FOUND),
    IsolationCase(
        "PATCH", "/api/jobs/{job_id}", _alices_job, NOT_FOUND, body={"notes": "B was here"}
    ),
    IsolationCase("DELETE", "/api/jobs/{job_id}", _alices_job, NOT_FOUND),
    IsolationCase(
        "POST",
        "/api/jobs",
        _alices_job,
        CUSTOM,
        body={"company": "Acme Ltd", "role": "Platform Engineer", "url": ALICES_URL},
        check=_created_as_bobs_own,
    ),
):
    register(_case)


# --- Cases: /api/me (JT-48) ---------------------------------------------------------------

ALICES_TIMEZONE = "Asia/Tokyo"


async def _alice_in_tokyo(conn: AsyncConnection, alice: uuid.UUID) -> dict[str, Any]:
    await conn.execute(
        text("UPDATE users SET timezone = :tz WHERE id = :u"), {"tz": ALICES_TIMEZONE, "u": alice}
    )
    return {}


def _bobs_own_profile(resp: Any, params: dict[str, Any]) -> None:
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"email": ALLOWED_EMAIL, "timezone": "UTC"}


def _bobs_own_timezone(resp: Any, params: dict[str, Any]) -> None:
    # B's own zone is set; the snapshot proves A's row is untouched.
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"timezone": "America/New_York"}


for _case in (
    IsolationCase("GET", "/api/me", _alice_in_tokyo, CUSTOM, check=_bobs_own_profile),
    IsolationCase(
        "PUT",
        "/api/me/timezone",
        _alice_in_tokyo,
        CUSTOM,
        body={"timezone": "America/New_York"},
        check=_bobs_own_timezone,
    ),
):
    register(_case)


# --- Cases: status changes and history (JT-26) --------------------------------------------


async def _bobs_own_job(conn: AsyncConnection, bob: uuid.UUID) -> dict[str, Any]:
    job_id = (
        await conn.execute(
            text(
                "INSERT INTO jobs (user_id, company, role, status) "
                "VALUES (:u, 'Globex', 'Engineer', 'applied') RETURNING id"
            ),
            {"u": bob},
        )
    ).scalar_one()
    return {"bobs_job_id": job_id}


def _only_bobs_job_changed(resp: Any, params: dict[str, Any]) -> None:
    # A's job is "not found" to B; B's own job is updated. The snapshot proves none of
    # A's jobs or history rows changed.
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "updated": [str(params["bobs_job_id"])],
        "unchanged": [],
        "not_found": [str(params["job_id"])],
    }


for _case in (
    IsolationCase("GET", "/api/jobs/{job_id}/history", _alices_job, NOT_FOUND),
    IsolationCase(
        "POST", "/api/jobs/{job_id}/status", _alices_job, NOT_FOUND, body={"status": "rejected"}
    ),
    IsolationCase(
        "POST",
        "/api/jobs/bulk-status",
        _alices_job,
        CUSTOM,
        arrange_bob=_bobs_own_job,
        body=lambda p: {"ids": [str(p["job_id"]), str(p["bobs_job_id"])], "status": "no_response"},
        check=_only_bobs_job_changed,
    ),
):
    register(_case)


# --- Cases: interviews (JT-27) ------------------------------------------------------------


async def _alices_interviews(conn: AsyncConnection, alice: uuid.UUID) -> dict[str, Any]:
    """A's job, with one interview in each group: upcoming, not yet scheduled, and past."""
    params = await _alices_job(conn, alice)
    ids = []
    for scheduled in ("now() + interval '3 days'", "NULL", "now() - interval '3 days'"):
        ids.append(
            (
                await conn.execute(
                    text(
                        "INSERT INTO interviews (job_id, user_id, scheduled_at, mode) "
                        f"VALUES (:j, :u, {scheduled}, 'phone') RETURNING id"
                    ),
                    {"j": params["job_id"], "u": alice},
                )
            ).scalar_one()
        )
    return {**params, "interview_id": ids[0]}


def _no_interviews(groups: Any) -> bool:
    return groups == {"upcoming": [], "not_yet_scheduled": [], "past": []}


def _under_bobs_own_job(params: dict[str, Any]) -> dict[str, Any]:
    return {"job_id": params["bobs_job_id"], "interview_id": params["interview_id"]}


_ONE_INTERVIEW = "/api/jobs/{job_id}/interviews/{interview_id}"
_INTERVIEW_BODIES = {"GET": None, "PATCH": {"notes": "B was here"}, "DELETE": None}

for _case in (
    IsolationCase("GET", "/api/interviews", _alices_interviews, EMPTY, is_empty=_no_interviews),
    IsolationCase("GET", "/api/jobs/{job_id}/interviews", _alices_interviews, NOT_FOUND),
    IsolationCase(
        "POST",
        "/api/jobs/{job_id}/interviews",
        _alices_interviews,
        NOT_FOUND,
        body={"mode": "phone"},
    ),
    *(
        IsolationCase(method, _ONE_INTERVIEW, _alices_interviews, NOT_FOUND, body=body)
        for method, body in _INTERVIEW_BODIES.items()
    ),
):
    register(_case)

# A's interview put under one of B's own jobs is still not B's.
for _method, _body in _INTERVIEW_BODIES.items():
    register_extra(
        IsolationCase(
            _method,
            _ONE_INTERVIEW,
            _alices_interviews,
            NOT_FOUND,
            body=_body,
            arrange_bob=_bobs_own_job,
            path_params=_under_bobs_own_job,
            variant="A's interview under B's own job",
        )
    )


# --- Cases: dashboard (JT-28) -------------------------------------------------------------


async def _alices_busy_dashboard(conn: AsyncConnection, alice: uuid.UUID) -> dict[str, Any]:
    """A's data in every part of the dashboard: each list, each count, and interviews."""
    params = await _alices_interviews(conn, alice)  # an applied job with interviews
    for status, days_ago, was_interviewing in (
        ("saved", 10, False),  # still to apply
        ("applied", 10, False),  # needs follow-up
        ("applied", 30, False),  # no response?
        ("offer", 30, False),  # needs follow-up
        ("rejected", 5, True),  # rejected after interview
    ):
        job_id = (
            await conn.execute(
                text(
                    "INSERT INTO jobs (user_id, company, role, status, applied_at) "
                    "VALUES (:u, 'Initech', 'Engineer', :s, :applied) RETURNING id"
                ),
                {"u": alice, "s": status, "applied": None if status == "saved" else date.today()},
            )
        ).scalar_one()
        for history_status in ("interviewing", status) if was_interviewing else (status,):
            await conn.execute(
                text(
                    "INSERT INTO status_history (job_id, user_id, status, changed_at) "
                    "VALUES (:j, :u, :s, now() - make_interval(days => :d))"
                ),
                {"j": job_id, "u": alice, "s": history_status, "d": days_ago},
            )
    return params


def _empty_dashboard(payload: Any) -> bool:
    return (
        not any(payload["counts"].values())
        and payload["needs_follow_up"] == []
        and payload["still_to_apply"] == []
        and payload["no_response_candidates"] == []
        and payload["upcoming_interviews"] == []
        and payload["upcoming_interviews_total"] == 0
    )


register(
    IsolationCase("GET", "/api/dashboard", _alices_busy_dashboard, EMPTY, is_empty=_empty_dashboard)
)
